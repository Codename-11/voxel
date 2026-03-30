"""OpenClaw WebSocket gateway client.

Uses the OpenClaw JSON-RPC WebSocket protocol (matching PinchChat/agents-browser)
instead of the HTTP REST API. This is the preferred connection method because:

  1. Proper scope declaration (operator.read/write) at connect time
  2. Real-time streaming responses via chat events
  3. Session persistence across messages
  4. Tool call events and approval flows

Protocol:
  Client → Gateway:  {type: "req", id, method, params}
  Gateway → Client:  {type: "res", id, ok, payload}  (response to request)
  Gateway → Client:  {type: "event", event, payload}  (unsolicited push)

Connect handshake:
  1. Server sends connect.challenge event (with optional nonce)
  2. Client sends connect request with auth, scopes, role
  3. Server responds with ok + gateway info

Chat flow:
  1. Client sends chat.send {sessionKey, message}
  2. Server pushes chat events: delta (streaming), final (done), error
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import AsyncGenerator, Optional

log = logging.getLogger("voxel.core.gateway_ws")

# Protocol version
PROTOCOL_VERSION = 3

# Default scopes for operator access
DEFAULT_SCOPES = [
    "operator.read",
    "operator.write",
    "operator.admin",
    "operator.approvals",
]

# App identity
APP_VERSION = "0.1.0"


def _gen_id(prefix: str = "req") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class OpenClawWSClient:
    """WebSocket client for the OpenClaw gateway protocol.

    Maintains a persistent connection with automatic reconnection.
    Supports both blocking (send_message) and streaming (send_message_stream)
    patterns.
    """

    def __init__(self, url: str, token: str, agent_id: str = "daemon",
                 auth_mode: str = "token"):
        # Convert http:// to ws://
        ws_url = url.replace("http://", "ws://").replace("https://", "wss://")
        if not ws_url.endswith("/"):
            ws_url += "/"
        self.ws_url = ws_url
        self.token = token
        self.agent_id = agent_id
        self.auth_mode = auth_mode  # "token" or "password"
        self.session_key = f"agent:{agent_id}:companion"

        self._ws = None
        self._connected = False
        self._pending: dict[str, asyncio.Future] = {}
        self._event_handlers: list = []
        self._receive_task: asyncio.Task | None = None
        self._chat_queue: asyncio.Queue | None = None

    @property
    def connected(self) -> bool:
        return self._connected

    async def connect(self) -> bool:
        """Connect to the gateway and complete the handshake.

        Returns True if connected and authenticated successfully.
        """
        try:
            import websockets
        except ImportError:
            log.error("websockets package not installed")
            return False

        try:
            log.info("Gateway WS: connecting to %s", self.ws_url)
            self._ws = await websockets.connect(
                self.ws_url,
                open_timeout=10,
                close_timeout=5,
                additional_headers={
                    "Origin": self.ws_url.replace("ws://", "http://").replace("wss://", "https://").rstrip("/"),
                },
            )

            # Start receive loop
            self._chat_queue = asyncio.Queue()
            self._receive_task = asyncio.create_task(self._receive_loop())

            # Wait for connect.challenge (up to 5s)
            challenge_received = asyncio.Event()
            nonce = [None]

            def _on_challenge(event, payload):
                if event == "connect.challenge":
                    nonce[0] = payload.get("nonce") if isinstance(payload, dict) else None
                    challenge_received.set()

            self._event_handlers.append(_on_challenge)
            try:
                await asyncio.wait_for(challenge_received.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                log.warning("Gateway WS: no challenge received, proceeding anyway")
            finally:
                self._event_handlers.remove(_on_challenge)

            # Send connect request
            auth = ({"password": self.token} if self.auth_mode == "password"
                    else {"token": self.token})

            result = await self._request("connect", {
                "minProtocol": PROTOCOL_VERSION,
                "maxProtocol": PROTOCOL_VERSION,
                "client": {
                    "id": "webchat",
                    "version": APP_VERSION,
                    "platform": "web",
                    "mode": "webchat",
                },
                "role": "operator",
                "scopes": DEFAULT_SCOPES,
                "caps": [],
                "commands": [],
                "permissions": {},
                "auth": auth,
                "locale": "en",
                "userAgent": f"voxel/{APP_VERSION}",
            })

            self._connected = True
            log.info("Gateway WS: connected (protocol=%s, result=%s)",
                     result.get("protocol", "?") if result else "?",
                     result)
            return True

        except Exception as e:
            log.error("Gateway WS: connect failed: %s", e)
            self._connected = False
            return False

    async def disconnect(self) -> None:
        """Close the WebSocket connection."""
        self._connected = False
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except (asyncio.CancelledError, Exception):
                pass
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
        self._ws = None
        log.info("Gateway WS: disconnected")

    async def send_message(self, message: str,
                           history: Optional[list[dict]] = None) -> Optional[str]:
        """Send a message and wait for the complete response.

        Blocks until the full response is received or an error occurs.
        Returns the assistant's response text, or None on failure.
        """
        if not self._connected or not self._ws:
            log.warning("Gateway WS: not connected")
            return None

        log.info("Gateway WS: sending to %s (%d chars)",
                 self.agent_id, len(message))

        # Send message via sessions.send (chat.send requires device pairing)
        try:
            await self._request("sessions.send", {
                "sessionKey": self.session_key,
                "text": message,
            })
        except Exception as e:
            log.error("Gateway WS: chat.send failed: %s", e)
            return None

        # Collect streaming response from chat events
        full_text = []
        try:
            while True:
                event = await asyncio.wait_for(
                    self._chat_queue.get(), timeout=120.0,
                )
                state = event.get("state", "")
                if state == "delta":
                    text = self._extract_text(event.get("message", {}))
                    if text:
                        full_text.append(text)
                elif state == "final":
                    # Final message has the complete text
                    text = self._extract_text(event.get("message", {}))
                    if text:
                        full_text = [text]  # replace with final
                    break
                elif state in ("error", "aborted"):
                    err = event.get("error", "Unknown error")
                    log.error("Gateway WS: chat error: %s", err)
                    break
        except asyncio.TimeoutError:
            log.error("Gateway WS: response timeout (120s)")
            return None

        result = "".join(full_text) if full_text else None
        if result:
            log.info("Gateway WS: response received (%d chars)", len(result))
        else:
            log.warning("Gateway WS: empty response")
        return result

    async def send_message_stream(self, message: str) -> AsyncGenerator[dict, None]:
        """Send a message and yield streaming events.

        Yields dicts with keys: type ("text", "tool_start", "tool_done", "done", "error"),
        plus type-specific data (text, name, arguments, etc.).
        """
        if not self._connected or not self._ws:
            log.warning("Gateway WS: not connected")
            yield {"type": "error", "error": "Not connected"}
            return

        try:
            await self._request("chat.send", {
                "sessionKey": self.session_key,
                "message": message,
                "deliver": False,
                "idempotencyKey": _gen_id("msg"),
            })
        except Exception as e:
            yield {"type": "error", "error": str(e)}
            return

        while True:
            try:
                event = await asyncio.wait_for(
                    self._chat_queue.get(), timeout=120.0,
                )
            except asyncio.TimeoutError:
                yield {"type": "error", "error": "Timeout"}
                return

            state = event.get("state", "")
            msg = event.get("message", {})

            if state == "delta":
                text = self._extract_text(msg)
                if text:
                    yield {"type": "text", "text": text}

                # Check for tool calls in delta
                tool_calls = msg.get("tool_calls", [])
                for tc in tool_calls:
                    if tc.get("status") == "running":
                        yield {"type": "tool_start", "name": tc.get("name", "")}
                    elif tc.get("status") == "done":
                        yield {"type": "tool_done", "name": tc.get("name", ""),
                               "result": tc.get("result", "")}

            elif state == "final":
                text = self._extract_text(msg)
                yield {"type": "done", "text": text or ""}
                return

            elif state in ("error", "aborted"):
                yield {"type": "error", "error": event.get("error", state)}
                return

    def set_agent(self, agent_id: str) -> None:
        """Switch the active agent."""
        self.agent_id = agent_id
        self.session_key = f"agent:{agent_id}:companion"
        log.info("Gateway WS: switched to agent %s", agent_id)

    async def health_check(self) -> bool:
        """Check if the gateway connection is alive."""
        if not self._connected or not self._ws:
            return False
        try:
            await self._ws.ping()
            return True
        except Exception:
            return False

    # ── Internal protocol ─────────────────────────────────────────────

    async def _request(self, method: str, params: dict,
                       timeout: float = 30.0) -> dict:
        """Send a JSON-RPC request and wait for the matching response."""
        req_id = _gen_id("req")
        msg = {
            "type": "req",
            "id": req_id,
            "method": method,
            "params": params,
        }

        future = asyncio.get_event_loop().create_future()
        self._pending[req_id] = future

        try:
            await self._ws.send(json.dumps(msg))
            result = await asyncio.wait_for(future, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            self._pending.pop(req_id, None)
            raise
        except Exception:
            self._pending.pop(req_id, None)
            raise

    async def _receive_loop(self) -> None:
        """Background task: dispatch incoming messages."""
        try:
            async for raw in self._ws:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                msg_type = msg.get("type")

                if msg_type == "res":
                    # Response to a pending request
                    req_id = msg.get("id")
                    future = self._pending.pop(req_id, None)
                    if future and not future.done():
                        if msg.get("ok"):
                            future.set_result(msg.get("payload", {}))
                        else:
                            future.set_exception(
                                Exception(msg.get("error", msg.get("payload", "Unknown error")))
                            )

                elif msg_type == "event":
                    event_name = msg.get("event", "")
                    payload = msg.get("payload", {})

                    # Route chat events to the queue
                    if event_name == "chat":
                        if self._chat_queue:
                            await self._chat_queue.put(payload)

                    # Notify registered handlers
                    for handler in self._event_handlers:
                        try:
                            handler(event_name, payload)
                        except Exception:
                            pass

        except Exception as e:
            if self._connected:
                log.warning("Gateway WS: receive loop error: %s", e)
                self._connected = False

    @staticmethod
    def _extract_text(message: dict) -> str:
        """Extract text content from a chat message payload."""
        # Direct content field
        content = message.get("content")
        if isinstance(content, str):
            return content

        # Content array (OpenAI format)
        if isinstance(content, list):
            parts = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    parts.append(part.get("text", ""))
                elif isinstance(part, str):
                    parts.append(part)
            return "".join(parts)

        # Fallback: text field
        return message.get("text", "")
