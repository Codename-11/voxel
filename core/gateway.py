"""OpenClaw gateway client for Voxel."""

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Generator, Optional, Union
import requests

log = logging.getLogger("voxel.core.gateway")


# ---------------------------------------------------------------------------
# Stream event types
# ---------------------------------------------------------------------------

@dataclass
class TextChunk:
    """A piece of streamed text content."""
    text: str


@dataclass
class ToolCallStart:
    """First chunk of a tool call (includes id and function name)."""
    id: str
    name: str


@dataclass
class ToolCallDone:
    """Fully accumulated tool call with complete arguments JSON."""
    id: str
    name: str
    arguments: str  # JSON string


@dataclass
class StreamDone:
    """End-of-stream summary with accumulated text and tool calls."""
    full_text: str
    tool_calls: list[dict] = field(default_factory=list)  # [{id, name, arguments}]
    finish_reason: str = "stop"


StreamEvent = Union[TextChunk, ToolCallStart, ToolCallDone, StreamDone]


class OpenClawClient:
    """Communicates with the OpenClaw gateway API."""

    def __init__(self, base_url: str, token: str, agent_id: str = "daemon",
                 system_context: str = ""):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.agent_id = agent_id
        self.session_key = f"agent:{agent_id}:companion"
        self.system_context = system_context

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "x-openclaw-session-key": self.session_key,
            "x-openclaw-scopes": "operator.read,operator.write",
        }

    def _build_dynamic_context(self, state: Optional[dict] = None) -> str:
        """Build system context with optional live device state."""
        parts: list[str] = []
        if self.system_context:
            parts.append(self.system_context)
        if state:
            status_line = (
                f"\n[Device: battery={state.get('battery', '?')}%, "
                f"wifi={'yes' if state.get('connected') else 'no'}, "
                f"mood={state.get('mood', 'neutral')}, "
                f"state={state.get('state', 'IDLE')}, "
                f"agent={state.get('agent', 'daemon')}]"
            )
            parts.append(status_line)
        return "\n".join(parts)

    def _build_messages(self, message: str,
                        history: Optional[list[dict]] = None,
                        device_state: Optional[dict] = None) -> list[dict]:
        """Build the messages array for a chat completions request.

        Includes system context (if set), conversation history (if provided),
        and the current user message.
        """
        messages: list[dict] = []
        context = self._build_dynamic_context(device_state)
        if context:
            messages.append({"role": "system", "content": context})
        if history:
            for entry in history:
                role = entry.get("role", "")
                text = entry.get("text", "")
                if role in ("user", "assistant") and text:
                    messages.append({"role": role, "content": text})
        messages.append({"role": "user", "content": message})
        return messages

    def send_message(self, message: str,
                     history: Optional[list[dict]] = None,
                     device_state: Optional[dict] = None) -> Optional[str]:
        """Send a message to the agent and get the response.

        Uses the chat completions endpoint in non-streaming mode.
        If system_context is set, prepends it as a system message.
        If history is provided, includes prior conversation turns.
        If device_state is provided, appends live device status to the system context.
        Returns the assistant's response text, or None on failure.
        """
        messages = self._build_messages(message, history, device_state=device_state)
        log.info("Gateway: sending to %s (agent=%s, %d chars, %d messages in context)",
                 self.base_url, self.agent_id, len(message), len(messages))

        t0 = time.perf_counter()
        try:
            resp = requests.post(
                f"{self.base_url}/v1/chat/completions",
                headers=self._headers(),
                json={
                    "model": f"openclaw:{self.agent_id}",
                    "stream": False,
                    "messages": messages,
                },
                timeout=120,
            )
            resp.raise_for_status()
            elapsed_ms = (time.perf_counter() - t0) * 1000
            data = resp.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            if content:
                log.info("Gateway: response received (%d chars) in %.0fms", len(content), elapsed_ms)
                log.debug("Gateway response: %.100s", content)
            else:
                log.warning("Gateway: empty response after %.0fms", elapsed_ms)
            return content or None
        except requests.Timeout:
            log.error("Gateway request timed out (120s)")
            return None
        except requests.HTTPError as e:
            # Log the response body for auth/scope errors
            body = ""
            try:
                body = e.response.text[:200] if e.response else ""
            except Exception:
                pass
            log.error("Gateway HTTP %s: %s", e.response.status_code if e.response else "?", body or str(e))
            return None
        except requests.RequestException as e:
            log.error("Gateway request failed: %s", e)
            return None

    def send_message_stream(
        self,
        message: str,
        history: Optional[list[dict]] = None,
        tools: Optional[list[dict]] = None,
        device_state: Optional[dict] = None,
    ) -> Generator[StreamEvent, None, None]:
        """Stream a response from the agent, yielding events as they arrive.

        Makes a POST to /v1/chat/completions with stream=True and reads
        Server-Sent Events line by line.  Falls back to non-streaming
        send_message() if the stream response is empty or errors out.

        Yields:
            TextChunk      — incremental content tokens
            ToolCallStart  — first appearance of a tool call (id + name)
            ToolCallDone   — completed tool call (accumulated arguments)
            StreamDone     — final summary with full text and tool calls
        """
        messages = self._build_messages(message, history, device_state=device_state)

        log.info(
            "Gateway: streaming to %s (agent=%s, %d chars, %d messages in context)",
            self.base_url, self.agent_id, len(message), len(messages),
        )
        t0 = time.perf_counter()

        body: dict = {
            "model": f"openclaw:{self.agent_id}",
            "stream": True,
            "messages": messages,
        }
        if tools:
            body["tools"] = tools

        try:
            resp = requests.post(
                f"{self.base_url}/v1/chat/completions",
                headers=self._headers(),
                json=body,
                timeout=120,
                stream=True,
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            log.error("Gateway stream request failed after %.0fms: %s", elapsed_ms, e)
            yield from self._fallback_stream(message)
            return

        # ---- SSE parsing state ----
        full_text: list[str] = []
        # Accumulate tool calls by index: {index: {id, name, arguments}}
        tool_acc: dict[int, dict] = {}
        finish_reason = "stop"
        got_any_data = False

        try:
            for raw_bytes in resp.iter_lines(decode_unicode=True):
                # iter_lines strips newlines; raw_bytes is a str when
                # decode_unicode=True.  Empty strings are blank lines
                # (SSE record separators).
                if raw_bytes is None:
                    continue
                line = raw_bytes  # already decoded

                if not line:
                    # Blank line — SSE record boundary, nothing to do.
                    continue

                if not line.startswith("data: "):
                    log.debug("Gateway SSE: ignoring line: %.80s", line)
                    continue

                payload = line[6:]  # strip "data: " prefix

                if payload == "[DONE]":
                    log.debug("Gateway SSE: stream done")
                    break

                try:
                    chunk = json.loads(payload)
                except json.JSONDecodeError:
                    log.debug("Gateway SSE: bad JSON: %.120s", payload)
                    continue

                got_any_data = True
                choices = chunk.get("choices", [])
                if not choices:
                    continue

                choice = choices[0]
                delta = choice.get("delta", {})

                # Finish reason (may appear on the last real chunk)
                if choice.get("finish_reason"):
                    finish_reason = choice["finish_reason"]

                # --- Text content ---
                content = delta.get("content")
                if content:
                    full_text.append(content)
                    log.debug("Gateway SSE chunk: %.60s", content)
                    yield TextChunk(text=content)

                # --- Tool calls ---
                tc_deltas = delta.get("tool_calls")
                if tc_deltas:
                    for tc in tc_deltas:
                        idx = tc.get("index", 0)
                        if idx not in tool_acc:
                            tool_acc[idx] = {"id": "", "name": "", "arguments": ""}

                        entry = tool_acc[idx]

                        # id and name arrive on the first chunk for this index
                        if tc.get("id"):
                            entry["id"] = tc["id"]
                        fn = tc.get("function", {})
                        if fn.get("name"):
                            entry["name"] = fn["name"]
                            log.debug("Gateway SSE: tool call start: %s", fn["name"])
                            yield ToolCallStart(id=entry["id"], name=entry["name"])
                        if fn.get("arguments"):
                            entry["arguments"] += fn["arguments"]

        except requests.RequestException as e:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            log.error("Gateway stream read error after %.0fms: %s", elapsed_ms, e)
            if not got_any_data:
                yield from self._fallback_stream(message)
                return

        # If the stream connected but returned no data, fall back
        if not got_any_data:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            log.warning("Gateway: stream was empty after %.0fms, falling back to non-streaming", elapsed_ms)
            yield from self._fallback_stream(message)
            return

        # Yield completed tool calls
        completed_tools: list[dict] = []
        for idx in sorted(tool_acc):
            tc = tool_acc[idx]
            completed_tools.append(tc)
            log.debug("Gateway: tool call complete: %s (id=%s)", tc["name"], tc["id"])
            yield ToolCallDone(id=tc["id"], name=tc["name"], arguments=tc["arguments"])

        result_text = "".join(full_text)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        log.info("Gateway: stream complete in %.0fms (%d chars, %d tool calls)",
                 elapsed_ms, len(result_text), len(completed_tools))

        yield StreamDone(
            full_text=result_text,
            tool_calls=completed_tools,
            finish_reason=finish_reason,
        )

    def _fallback_stream(self, message: str) -> Generator[StreamEvent, None, None]:
        """Fall back to non-streaming send_message and emit equivalent events."""
        log.info("Gateway: using non-streaming fallback")
        text = self.send_message(message)
        if text:
            yield TextChunk(text=text)
            yield StreamDone(full_text=text, tool_calls=[], finish_reason="stop")
        else:
            yield StreamDone(full_text="", tool_calls=[], finish_reason="error")

    def set_agent(self, agent_id: str):
        """Switch the active agent."""
        self.agent_id = agent_id
        self.session_key = f"agent:{agent_id}:companion"
        log.info(f"Switched to agent: {agent_id}")

    def health_check(self) -> bool:
        """Check if the gateway is reachable."""
        try:
            resp = requests.get(
                f"{self.base_url}/v1/models",
                headers=self._headers(),
                timeout=5,
            )
            return resp.status_code == 200
        except requests.RequestException:
            return False
