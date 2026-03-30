"""Voxel MCP server — JSON-RPC 2.0 over stdio or SSE.

No external MCP SDK required. Uses only stdlib + websockets (already a project
dependency). Connects to the Voxel backend via WebSocket on port 8080 and
translates MCP tool/resource calls into the existing WS command protocol.

Transports:
    stdio  — for Claude Code, Codex CLI (local subprocess)
    sse    — for OpenClaw gateway, remote agents (HTTP on configurable port)
"""

from __future__ import annotations

import asyncio
import json
import logging
import signal
import sys
import threading
import uuid
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any

log = logging.getLogger("voxel.mcp")

SERVER_INFO = {
    "name": "voxel",
    "version": "0.1.0",
}

SERVER_CAPABILITIES = {
    "tools": {},
    "resources": {},
}

DEFAULT_WS_URL = "ws://localhost:8080"
DEFAULT_SSE_PORT = 8082

# ---------------------------------------------------------------------------
# WebSocket bridge to Voxel backend
# ---------------------------------------------------------------------------


class VoxelBridge:
    """Bridge between MCP tools and the Voxel backend via WebSocket."""

    def __init__(self, ws_url: str = DEFAULT_WS_URL):
        self.ws_url = ws_url
        self.state: dict[str, Any] = {}
        self.history: list[dict] = []
        self._ws: Any = None  # websockets connection
        self._read_task: asyncio.Task | None = None
        self._reconnect_delay = 1.0
        self._max_reconnect_delay = 30.0
        self._running = True

    async def connect(self) -> None:
        """Connect to the Voxel backend WebSocket and start reading state."""
        self._running = True
        self._read_task = asyncio.create_task(self._connect_loop())

    async def _connect_loop(self) -> None:
        """Maintain a persistent connection with auto-reconnect."""
        import websockets

        delay = self._reconnect_delay
        while self._running:
            try:
                log.info("Connecting to backend at %s", self.ws_url)
                async with websockets.connect(self.ws_url) as ws:
                    self._ws = ws
                    delay = self._reconnect_delay  # reset on success
                    log.info("Connected to backend")
                    await self._read_loop(ws)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                self._ws = None
                if not self._running:
                    break
                log.warning(
                    "Backend connection lost (%s), reconnecting in %.0fs",
                    exc, delay,
                )
                await asyncio.sleep(delay)
                delay = min(delay * 2, self._max_reconnect_delay)

    async def _read_loop(self, ws: Any) -> None:
        """Read state pushes from the backend."""
        async for raw in ws:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            msg_type = data.get("type")
            if msg_type == "state":
                self.state = data
            elif msg_type == "chat_history":
                self.history = data.get("messages", [])
            elif msg_type == "transcript":
                # Append individual transcript messages to local history
                self.history.append(data)

    async def send_command(self, cmd: dict) -> None:
        """Send a JSON command to the backend."""
        if self._ws is None:
            log.warning("Cannot send command — not connected to backend")
            return
        try:
            await self._ws.send(json.dumps(cmd))
        except Exception as exc:
            log.warning("Failed to send command: %s", exc)

    async def get_state(self) -> dict:
        """Return the latest device state snapshot."""
        return dict(self.state)

    async def close(self) -> None:
        """Shut down the bridge."""
        self._running = False
        if self._read_task and not self._read_task.done():
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass
        if self._ws:
            await self._ws.close()
            self._ws = None


# ---------------------------------------------------------------------------
# JSON-RPC 2.0 handler
# ---------------------------------------------------------------------------


async def handle_jsonrpc(request: dict, bridge: VoxelBridge) -> dict | None:
    """Process a single JSON-RPC 2.0 request and return the response."""
    from mcp.tools import TOOLS, RESOURCES, handle_tool, handle_resource

    req_id = request.get("id")
    method = request.get("method", "")
    params = request.get("params", {})

    log.debug("JSON-RPC request: method=%s id=%s", method, req_id)

    # --- Lifecycle ---

    if method == "initialize":
        return _result(req_id, {
            "protocolVersion": "2024-11-05",
            "serverInfo": SERVER_INFO,
            "capabilities": SERVER_CAPABILITIES,
        })

    if method == "notifications/initialized":
        # Client acknowledgment — no response needed
        return None

    if method == "ping":
        return _result(req_id, {})

    # --- Tools ---

    if method == "tools/list":
        return _result(req_id, {"tools": TOOLS})

    if method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})
        try:
            content = await handle_tool(tool_name, arguments, bridge)
            return _result(req_id, {"content": content, "isError": False})
        except Exception as exc:
            log.exception("Tool %s failed", tool_name)
            return _result(req_id, {
                "content": [{"type": "text", "text": f"Error: {exc}"}],
                "isError": True,
            })

    # --- Resources ---

    if method == "resources/list":
        return _result(req_id, {"resources": RESOURCES})

    if method == "resources/read":
        uri = params.get("uri", "")
        try:
            contents = await handle_resource(uri, bridge)
            return _result(req_id, {
                "contents": [{"uri": uri, "text": c["text"]} for c in contents],
            })
        except Exception as exc:
            log.exception("Resource %s read failed", uri)
            return _error(req_id, -32603, str(exc))

    # --- Unknown method ---
    log.warning("Unknown method: %s", method)
    return _error(req_id, -32601, f"Method not found: {method}")


def _result(req_id: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _error(req_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


# ---------------------------------------------------------------------------
# Stdio transport
# ---------------------------------------------------------------------------


async def run_stdio(bridge: VoxelBridge) -> None:
    """Run MCP over stdin/stdout (one JSON-RPC message per line)."""
    log.info("Starting stdio transport")
    await bridge.connect()

    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    loop = asyncio.get_event_loop()
    await loop.connect_read_pipe(lambda: protocol, sys.stdin.buffer)

    try:
        while True:
            line = await reader.readline()
            if not line:
                break
            line = line.strip()
            if not line:
                continue
            try:
                request = json.loads(line)
            except json.JSONDecodeError as exc:
                log.warning("Invalid JSON on stdin: %s", exc)
                continue

            response = await handle_jsonrpc(request, bridge)
            if response is not None:
                out = json.dumps(response) + "\n"
                sys.stdout.buffer.write(out.encode())
                sys.stdout.buffer.flush()
    except asyncio.CancelledError:
        pass
    finally:
        await bridge.close()
        log.info("Stdio transport stopped")


# ---------------------------------------------------------------------------
# SSE transport (stdlib http.server)
# ---------------------------------------------------------------------------


class _SSEState:
    """Shared state for the SSE HTTP server."""

    def __init__(self, bridge: VoxelBridge, loop: asyncio.AbstractEventLoop):
        self.bridge = bridge
        self.loop = loop
        # Map session_id -> list of pending response dicts
        self.sessions: dict[str, list[dict]] = {}
        self.session_events: dict[str, threading.Event] = {}
        self.lock = threading.Lock()


class _SSEHandler(BaseHTTPRequestHandler):
    """HTTP handler for MCP SSE transport.

    GET  /sse      — opens an Server-Sent Events stream
    POST /message  — receives JSON-RPC requests, responses sent via SSE
    GET  /health   — simple health check
    """

    server: "_SSEServer"

    def log_message(self, fmt: str, *args: Any) -> None:
        log.debug(fmt, *args)

    # -- Health check -------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._send_json(200, {"status": "ok", "server": SERVER_INFO})
            return

        if self.path == "/sse":
            self._handle_sse()
            return

        self.send_error(404)

    # -- SSE stream ---------------------------------------------------------

    def _handle_sse(self) -> None:
        session_id = str(uuid.uuid4())
        sse_state: _SSEState = self.server.sse_state

        with sse_state.lock:
            sse_state.sessions[session_id] = []
            sse_state.session_events[session_id] = threading.Event()

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        # Send the endpoint event so the client knows where to POST
        self._write_sse_event("endpoint", f"/message?session_id={session_id}")

        try:
            while True:
                event = sse_state.session_events.get(session_id)
                if event is None:
                    break
                # Wait for messages (with timeout so we can send keepalives)
                triggered = event.wait(timeout=15.0)
                if triggered:
                    event.clear()
                    with sse_state.lock:
                        pending = list(sse_state.sessions.get(session_id, []))
                        if session_id in sse_state.sessions:
                            sse_state.sessions[session_id].clear()
                    for msg in pending:
                        self._write_sse_event("message", json.dumps(msg))
                else:
                    # Keepalive comment
                    try:
                        self.wfile.write(b":keepalive\n\n")
                        self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError):
                        break
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            with sse_state.lock:
                sse_state.sessions.pop(session_id, None)
                sse_state.session_events.pop(session_id, None)
            log.debug("SSE session %s closed", session_id)

    def _write_sse_event(self, event: str, data: str) -> None:
        payload = f"event: {event}\ndata: {data}\n\n"
        self.wfile.write(payload.encode())
        self.wfile.flush()

    # -- Message endpoint ---------------------------------------------------

    def do_POST(self) -> None:  # noqa: N802
        if not self.path.startswith("/message"):
            self.send_error(404)
            return

        # Parse session_id from query string
        from urllib.parse import urlparse, parse_qs
        qs = parse_qs(urlparse(self.path).query)
        session_id = qs.get("session_id", [None])[0]

        sse_state: _SSEState = self.server.sse_state

        if session_id is None or session_id not in sse_state.sessions:
            self._send_json(400, {"error": "Invalid or missing session_id"})
            return

        # Read request body
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b""

        try:
            request = json.loads(body)
        except json.JSONDecodeError:
            self._send_json(400, {"error": "Invalid JSON"})
            return

        # Process the JSON-RPC request asynchronously
        future = asyncio.run_coroutine_threadsafe(
            handle_jsonrpc(request, sse_state.bridge),
            sse_state.loop,
        )
        response = future.result(timeout=30.0)

        if response is not None:
            with sse_state.lock:
                if session_id in sse_state.sessions:
                    sse_state.sessions[session_id].append(response)
                event = sse_state.session_events.get(session_id)
                if event:
                    event.set()

        self._send_json(202, {"status": "accepted"})

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    # -- Helpers ------------------------------------------------------------

    def _send_json(self, code: int, data: Any) -> None:
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)


class _SSEServer(HTTPServer):
    """HTTPServer subclass that carries SSE state."""

    sse_state: _SSEState


async def run_sse(bridge: VoxelBridge, port: int = DEFAULT_SSE_PORT) -> None:
    """Run MCP over HTTP with Server-Sent Events."""
    log.info("Starting SSE transport on port %d", port)
    await bridge.connect()

    loop = asyncio.get_event_loop()
    sse_state = _SSEState(bridge, loop)

    server = _SSEServer(("0.0.0.0", port), _SSEHandler)
    server.sse_state = sse_state

    # Run the blocking HTTP server in a thread
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    log.info("SSE server listening on http://0.0.0.0:%d", port)

    # Wait until cancelled
    stop = asyncio.Event()

    def _signal_handler() -> None:
        stop.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            pass

    try:
        await stop.wait()
    except asyncio.CancelledError:
        pass
    finally:
        server.shutdown()
        await bridge.close()
        log.info("SSE transport stopped")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def main_async(transport: str, ws_url: str, port: int) -> None:
    """Run the MCP server with the specified transport."""
    bridge = VoxelBridge(ws_url)

    if transport == "stdio":
        await run_stdio(bridge)
    elif transport == "sse":
        await run_sse(bridge, port)
    else:
        log.error("Unknown transport: %s", transport)
        sys.exit(1)


def main() -> None:
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Voxel MCP Server — expose device tools to AI agents",
    )
    parser.add_argument(
        "--transport", "-t",
        choices=["stdio", "sse"],
        default="stdio",
        help="Transport mode (default: stdio)",
    )
    parser.add_argument(
        "--port", "-p",
        type=int,
        default=DEFAULT_SSE_PORT,
        help=f"SSE HTTP port (default: {DEFAULT_SSE_PORT})",
    )
    parser.add_argument(
        "--ws-url",
        default=DEFAULT_WS_URL,
        help=f"Voxel backend WebSocket URL (default: {DEFAULT_WS_URL})",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable DEBUG logging",
    )
    args = parser.parse_args()

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        stream=sys.stderr,
    )

    try:
        asyncio.run(main_async(args.transport, args.ws_url, args.port))
    except KeyboardInterrupt:
        pass
