"""Outbound webhook client — sends device events to the OpenClaw gateway.

Events are fire-and-forget (non-blocking). Failures are logged but never
crash the caller. Debouncing prevents rapid-fire events from spamming.

Config (config/default.yaml):
    webhook:
      enabled: false
      url: ""  # e.g. http://gateway-host:18789/hooks/agent
      token: ""
      events: [state_change, battery_alert, conversation_complete]
      debounce_seconds: 5
"""

import asyncio
import logging
import time
from typing import Optional

log = logging.getLogger("voxel.core.webhook")


class WebhookClient:
    """Fire-and-forget webhook poster with per-event debouncing."""

    def __init__(
        self,
        url: str = "",
        token: str = "",
        enabled_events: list[str] | None = None,
        debounce_seconds: float = 5.0,
    ):
        self.url = url
        self.token = token
        self.enabled_events = set(enabled_events or [])
        self.debounce = debounce_seconds
        self._last_sent: dict[str, float] = {}
        self._enabled = bool(url)

    def is_enabled(self, event_type: str) -> bool:
        """Check if this event type should be sent."""
        return self._enabled and (
            not self.enabled_events or event_type in self.enabled_events
        )

    async def send(
        self,
        event_type: str,
        message: str,
        data: dict | None = None,
        session_key: str = "",
    ) -> None:
        """Queue a webhook POST (fire-and-forget via thread pool).

        Silently skips if the event type is disabled or still within
        the debounce window.
        """
        if not self.is_enabled(event_type):
            return

        # Debounce — skip if we sent this event type too recently
        now = time.time()
        last = self._last_sent.get(event_type, 0)
        if now - last < self.debounce:
            return
        self._last_sent[event_type] = now

        payload: dict = {
            "message": message,
            "event": event_type,
            "device": "voxel",
            "data": data or {},
        }
        if session_key:
            payload["sessionKey"] = session_key

        loop = asyncio.get_event_loop()
        loop.run_in_executor(None, self._post, payload)

    def _post(self, payload: dict) -> None:
        """Blocking HTTP POST — runs in the default thread-pool executor."""
        import requests as req

        try:
            headers: dict[str, str] = {"Content-Type": "application/json"}
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"
            resp = req.post(self.url, json=payload, headers=headers, timeout=10)
            log.info("Webhook %s → %d", payload.get("event"), resp.status_code)
        except Exception as e:
            log.warning("Webhook failed: %s", e)
