"""OpenClaw gateway client for Voxel."""

import logging
from typing import Optional
import requests

log = logging.getLogger("voxel.core.gateway")


class OpenClawClient:
    """Communicates with the OpenClaw gateway API."""

    def __init__(self, base_url: str, token: str, agent_id: str = "daemon"):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.agent_id = agent_id
        self.session_key = f"agent:{agent_id}:companion"

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "x-openclaw-session-key": self.session_key,
        }

    def send_message(self, message: str) -> Optional[str]:
        """Send a message to the agent and get the response.

        Uses the chat completions endpoint in non-streaming mode.
        Returns the assistant's response text, or None on failure.
        """
        try:
            resp = requests.post(
                f"{self.base_url}/v1/chat/completions",
                headers=self._headers(),
                json={
                    "model": f"openclaw:{self.agent_id}",
                    "stream": False,
                    "messages": [{"role": "user", "content": message}],
                },
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            return content or None
        except requests.Timeout:
            log.error("Gateway request timed out")
            return None
        except requests.RequestException as e:
            log.error(f"Gateway request failed: {e}")
            return None

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
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=5,
            )
            return resp.status_code == 200
        except requests.RequestException:
            return False
