"""Tests for the WebSocket protocol — message format, handlers, and state push.

Tests the server.py handler functions and message format/parsing without
starting a real WebSocket server. Uses AsyncMock for WebSocket connections.
"""

from __future__ import annotations

import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# We need to mock certain imports before importing server.py components
# to avoid triggering audio init, gateway init, etc.


# ── Helpers ─────────────────────────────────────────────────────────────────


@pytest.fixture
def event_loop():
    """Provide a fresh event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


def run_async(coro, loop=None):
    """Run an async coroutine synchronously."""
    if loop is None:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()
    return loop.run_until_complete(coro)


@pytest.fixture(autouse=True)
def reset_server_state():
    """Reset server state between tests to avoid cross-contamination."""
    import server

    # Save original state
    original_ui_state = dict(server._ui_state)
    original_clients = set(server._clients)
    original_chat_history = list(server._chat_history)

    yield

    # Restore original state
    server._ui_state.update(original_ui_state)
    server._clients.clear()
    server._clients.update(original_clients)
    server._chat_history.clear()
    server._chat_history.extend(original_chat_history)


def _make_ws() -> AsyncMock:
    """Create a mock WebSocket connection."""
    ws = AsyncMock()
    ws.send = AsyncMock()
    return ws


# ── 1. State push message format ───────────────────────────────────────────


def test_state_push_has_required_fields():
    """The state push message should contain all required fields."""
    import server

    msg = {"type": "state", **server._ui_state}

    assert msg["type"] == "state"
    assert "mood" in msg
    assert "style" in msg
    assert "speaking" in msg
    assert "amplitude" in msg
    assert "battery" in msg
    assert "state" in msg
    assert "agent" in msg
    assert "connected" in msg
    assert "brightness" in msg
    assert "volume" in msg
    assert "displayMode" in msg
    assert "inputMode" in msg
    assert "agents" in msg


def test_state_push_default_values():
    """Default state values should be sensible."""
    import server

    assert server._ui_state["mood"] == "neutral"
    assert server._ui_state["style"] == "kawaii"
    assert server._ui_state["speaking"] is False
    assert server._ui_state["amplitude"] == 0.0
    assert server._ui_state["battery"] == 100
    assert server._ui_state["state"] == "IDLE"


# ── 2. broadcast function ──────────────────────────────────────────────────


def test_broadcast_sends_to_all_clients():
    """broadcast() should send JSON to every connected client."""
    import server

    ws1 = _make_ws()
    ws2 = _make_ws()
    server._clients.add(ws1)
    server._clients.add(ws2)

    try:
        run_async(server.broadcast({"type": "test", "value": 42}))

        ws1.send.assert_called_once()
        ws2.send.assert_called_once()

        sent1 = json.loads(ws1.send.call_args[0][0])
        assert sent1["type"] == "test"
        assert sent1["value"] == 42
    finally:
        server._clients.discard(ws1)
        server._clients.discard(ws2)


def test_broadcast_no_clients_is_noop():
    """broadcast() with no clients should not raise."""
    import server

    server._clients.clear()
    # Should not raise
    run_async(server.broadcast({"type": "state", "mood": "happy"}))


def test_broadcast_handles_client_errors():
    """broadcast() should not fail if one client errors."""
    import server

    ws_good = _make_ws()
    ws_bad = _make_ws()
    ws_bad.send.side_effect = Exception("connection closed")
    server._clients.add(ws_good)
    server._clients.add(ws_bad)

    try:
        # Should not raise despite one client failing
        run_async(server.broadcast({"type": "state", "mood": "happy"}))
        ws_good.send.assert_called_once()
    finally:
        server._clients.discard(ws_good)
        server._clients.discard(ws_bad)


# ── 3. send_to function ────────────────────────────────────────────────────


def test_send_to_specific_client():
    """send_to() should send JSON to a specific client."""
    import server

    ws = _make_ws()
    run_async(server.send_to(ws, {"type": "chat_history", "messages": []}))

    ws.send.assert_called_once()
    sent = json.loads(ws.send.call_args[0][0])
    assert sent["type"] == "chat_history"
    assert sent["messages"] == []


def test_send_to_swallows_errors():
    """send_to() should not raise on send failure."""
    import server

    ws = _make_ws()
    ws.send.side_effect = Exception("broken pipe")

    # Should not raise
    run_async(server.send_to(ws, {"type": "state"}))


# ── 4. handle_message — set_mood ───────────────────────────────────────────


def test_handle_set_mood():
    """set_mood command should update _ui_state['mood']."""
    import server

    ws = _make_ws()
    server._clients.add(ws)

    try:
        msg = {"type": "set_mood", "mood": "happy"}
        run_async(server.handle_message(msg, ws))

        assert server._ui_state["mood"] == "happy"
    finally:
        server._clients.discard(ws)


def test_handle_set_mood_defaults_to_neutral():
    """set_mood without a mood field should default to 'neutral'."""
    import server

    ws = _make_ws()
    server._clients.add(ws)

    try:
        msg = {"type": "set_mood"}
        run_async(server.handle_message(msg, ws))

        assert server._ui_state["mood"] == "neutral"
    finally:
        server._clients.discard(ws)


# ── 5. handle_message — set_style ──────────────────────────────────────────


def test_handle_set_style():
    """set_style command should update _ui_state['style']."""
    import server

    ws = _make_ws()
    server._clients.add(ws)

    try:
        msg = {"type": "set_style", "style": "retro"}
        run_async(server.handle_message(msg, ws))

        assert server._ui_state["style"] == "retro"
    finally:
        server._clients.discard(ws)


# ── 6. handle_message — set_state ──────────────────────────────────────────


def test_handle_set_state():
    """set_state command should transition the state machine."""
    import server
    from states.machine import State

    ws = _make_ws()
    server._clients.add(ws)

    try:
        msg = {"type": "set_state", "state": "LISTENING"}
        run_async(server.handle_message(msg, ws))

        assert server.sm.state == State.LISTENING
    finally:
        # Reset back to IDLE
        server.sm.transition(State.IDLE)
        server._clients.discard(ws)


def test_handle_set_state_unknown():
    """set_state with unknown state should not crash."""
    import server

    ws = _make_ws()
    server._clients.add(ws)

    try:
        msg = {"type": "set_state", "state": "NONEXISTENT"}
        # Should not raise
        run_async(server.handle_message(msg, ws))
    finally:
        server._clients.discard(ws)


# ── 7. handle_message — button events ──────────────────────────────────────


def test_handle_button_cancel_during_thinking():
    """Button cancel during THINKING should cancel pipeline."""
    import server
    from states.machine import State

    ws = _make_ws()
    server._clients.add(ws)
    server.sm.transition(State.THINKING)

    try:
        msg = {"type": "button", "button": "cancel"}
        run_async(server.handle_message(msg, ws))

        assert server.sm.state == State.IDLE
    finally:
        server.sm.transition(State.IDLE)
        server._clients.discard(ws)


def test_handle_button_cancel_during_speaking():
    """Button cancel during SPEAKING should cancel pipeline."""
    import server
    from states.machine import State

    ws = _make_ws()
    server._clients.add(ws)
    server.sm.transition(State.SPEAKING)

    try:
        msg = {"type": "button", "button": "cancel"}
        run_async(server.handle_message(msg, ws))

        assert server.sm.state == State.IDLE
    finally:
        server.sm.transition(State.IDLE)
        server._clients.discard(ws)


def test_handle_button_menu_toggle():
    """Button menu should toggle MENU state."""
    import server
    from states.machine import State

    ws = _make_ws()
    server._clients.add(ws)

    try:
        msg = {"type": "button", "button": "menu"}
        run_async(server.handle_message(msg, ws))

        assert server.sm.state == State.MENU

        # Toggle off
        run_async(server.handle_message(msg, ws))
        assert server.sm.state == State.IDLE
    finally:
        server.sm.transition(State.IDLE)
        server._clients.discard(ws)


def test_handle_button_left_right_emitted():
    """Button left/right should be broadcast to clients."""
    import server

    ws = _make_ws()
    server._clients.add(ws)

    try:
        msg = {"type": "button", "button": "left"}
        run_async(server.handle_message(msg, ws))

        # Should have broadcast a button event
        calls = ws.send.call_args_list
        sent_msgs = [json.loads(c[0][0]) for c in calls]
        button_msgs = [m for m in sent_msgs if m.get("type") == "button"]
        assert len(button_msgs) >= 1
        assert button_msgs[0]["button"] == "left"
    finally:
        server._clients.discard(ws)


# ── 8. handle_message — set_setting ────────────────────────────────────────


def test_handle_set_setting_brightness():
    """set_setting for brightness should update and clamp."""
    import server

    ws = _make_ws()
    server._clients.add(ws)

    try:
        msg = {"type": "set_setting", "section": "display", "key": "brightness", "value": 150}
        run_async(server.handle_message(msg, ws))

        # Should be clamped to 100
        assert server._ui_state["brightness"] <= 100
    finally:
        server._clients.discard(ws)


def test_handle_set_setting_volume():
    """set_setting for volume should update."""
    import server

    ws = _make_ws()
    server._clients.add(ws)

    try:
        msg = {"type": "set_setting", "section": "audio", "key": "volume", "value": 50}
        run_async(server.handle_message(msg, ws))

        # Volume should be updated
        assert server._ui_state["volume"] == 50
    finally:
        server._clients.discard(ws)


# ── 9. Transcript message format ───────────────────────────────────────────


def test_emit_transcript_format():
    """emit_transcript should broadcast a correctly formatted message."""
    import server

    ws = _make_ws()
    server._clients.add(ws)

    try:
        run_async(server.emit_transcript("user", "hello world", status="done"))

        calls = ws.send.call_args_list
        sent_msgs = [json.loads(c[0][0]) for c in calls]
        transcript_msgs = [m for m in sent_msgs if m.get("type") == "transcript"]

        assert len(transcript_msgs) == 1
        msg = transcript_msgs[0]
        assert msg["role"] == "user"
        assert msg["text"] == "hello world"
        assert msg["status"] == "done"
        assert "timestamp" in msg
    finally:
        server._clients.discard(ws)


def test_emit_transcript_partial_status():
    """emit_transcript with 'partial' status should be formatted correctly."""
    import server

    ws = _make_ws()
    server._clients.add(ws)

    try:
        run_async(server.emit_transcript("assistant", "Hello wo", status="partial"))

        calls = ws.send.call_args_list
        sent_msgs = [json.loads(c[0][0]) for c in calls]
        transcript_msgs = [m for m in sent_msgs if m.get("type") == "transcript"]

        assert len(transcript_msgs) == 1
        assert transcript_msgs[0]["status"] == "partial"
    finally:
        server._clients.discard(ws)


# ── 10. Chat history ───────────────────────────────────────────────────────


def test_get_chat_history_returns_messages():
    """get_chat_history should return current chat history."""
    import server

    ws = _make_ws()
    server._clients.add(ws)

    # Pre-populate chat history
    server._chat_history.clear()
    server._append_chat("user", "hi")
    server._append_chat("assistant", "hello!")

    try:
        msg = {"type": "get_chat_history"}
        run_async(server.handle_message(msg, ws))

        # Find the chat_history message sent to this client
        calls = ws.send.call_args_list
        sent_msgs = [json.loads(c[0][0]) for c in calls]
        history_msgs = [m for m in sent_msgs if m.get("type") == "chat_history"]

        assert len(history_msgs) >= 1
        messages = history_msgs[0]["messages"]
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[0]["text"] == "hi"
        assert messages[1]["role"] == "assistant"
        assert messages[1]["text"] == "hello!"
    finally:
        server._chat_history.clear()
        server._clients.discard(ws)


def test_append_chat_caps_at_limit():
    """Chat history should be capped at CHAT_LIMIT."""
    import server

    server._chat_history.clear()
    for i in range(server.CHAT_LIMIT + 10):
        server._append_chat("user", f"message {i}")

    assert len(server._chat_history) == server.CHAT_LIMIT
    # Oldest messages should have been dropped
    assert server._chat_history[0]["text"] != "message 0"


# ── 11. handle_message — text_input ────────────────────────────────────────


def test_text_input_ignored_when_not_idle():
    """text_input should be ignored if state machine is not IDLE."""
    import server
    from states.machine import State

    ws = _make_ws()
    server._clients.add(ws)
    server.sm.transition(State.THINKING)

    try:
        msg = {"type": "text_input", "text": "hello"}
        run_async(server.handle_message(msg, ws))
        # Should NOT have started a pipeline (state is THINKING)
        assert server._pipeline_task is None or server._pipeline_task.done()
    finally:
        server.sm.transition(State.IDLE)
        server._clients.discard(ws)


def test_text_input_empty_ignored():
    """Empty text_input should be ignored."""
    import server

    ws = _make_ws()
    server._clients.add(ws)

    try:
        msg = {"type": "text_input", "text": "   "}
        run_async(server.handle_message(msg, ws))
        assert server._pipeline_task is None or server._pipeline_task.done()
    finally:
        server._clients.discard(ws)


# ── 12. handle_message — ping/pong ─────────────────────────────────────────


def test_ping_responds_with_pong():
    """ping message should broadcast pong."""
    import server

    ws = _make_ws()
    server._clients.add(ws)

    try:
        msg = {"type": "ping"}
        run_async(server.handle_message(msg, ws))

        calls = ws.send.call_args_list
        sent_msgs = [json.loads(c[0][0]) for c in calls]
        pong_msgs = [m for m in sent_msgs if m.get("type") == "pong"]
        assert len(pong_msgs) >= 1
    finally:
        server._clients.discard(ws)


# ── 13. emit_reaction format ───────────────────────────────────────────────


def test_emit_reaction_format():
    """emit_reaction should broadcast a reaction message with the emoji."""
    import server

    ws = _make_ws()
    server._clients.add(ws)

    try:
        run_async(server.emit_reaction("\U0001f60a"))

        calls = ws.send.call_args_list
        sent_msgs = [json.loads(c[0][0]) for c in calls]
        reaction_msgs = [m for m in sent_msgs if m.get("type") == "reaction"]

        assert len(reaction_msgs) == 1
        assert reaction_msgs[0]["emoji"] == "\U0001f60a"
    finally:
        server._clients.discard(ws)


# ── 14. set_agent validation ───────────────────────────────────────────────


def test_set_agent_unknown_ignored():
    """set_agent with unknown agent_id should be ignored."""
    import server

    ws = _make_ws()
    server._clients.add(ws)
    original_agent = server._ui_state["agent"]

    try:
        msg = {"type": "set_agent", "agent": "nonexistent_agent_12345"}
        run_async(server.handle_message(msg, ws))

        # Agent should not have changed
        assert server._ui_state["agent"] == original_agent
    finally:
        server._clients.discard(ws)


# ── 15. _clamp_percent ─────────────────────────────────────────────────────


def test_clamp_percent():
    """_clamp_percent should clamp values to 0-100."""
    import server

    assert server._clamp_percent(-10) == 0
    assert server._clamp_percent(0) == 0
    assert server._clamp_percent(50) == 50
    assert server._clamp_percent(100) == 100
    assert server._clamp_percent(200) == 100
    assert server._clamp_percent(50.7) == 50
