"""
Hermes Agent client — tries REST API first, falls back to CLI subprocess.

The REST API base is the dashboard at localhost:9119.
Endpoint paths are inferred from Hermes Agent v0.16+ architecture;
adjust BASE_* constants if the actual API differs.
"""

import subprocess
import sys
from typing import Any

import httpx

from hermas.config import config

_API_GOALS = "/api/goals"
_API_GOAL_STATUS = "/api/goals/status"
_API_GOAL_ACTION = "/api/goals/{action}"  # pause | resume | clear


class HermesClient:
    def __init__(self, base_url: str | None = None) -> None:
        self._base = base_url or config.hermes_url
        self._http = httpx.Client(base_url=self._base, timeout=30)

    # --- goal operations ---

    def run_goal(self, goal: str) -> dict[str, Any]:
        """Start autonomous goal execution."""
        try:
            r = self._http.post(_API_GOALS, json={"goal": goal, "profile": config.profile})
            r.raise_for_status()
            return r.json()
        except Exception:
            return self._cli("goal", goal)

    def goal_status(self) -> dict[str, Any]:
        try:
            r = self._http.get(_API_GOAL_STATUS)
            r.raise_for_status()
            return r.json()
        except Exception:
            return self._cli("goal", "status")

    def goal_pause(self) -> dict[str, Any]:
        return self._goal_action("pause")

    def goal_resume(self) -> dict[str, Any]:
        return self._goal_action("resume")

    def goal_clear(self) -> dict[str, Any]:
        return self._goal_action("clear")

    def _goal_action(self, action: str) -> dict[str, Any]:
        try:
            r = self._http.post(_API_GOAL_ACTION.format(action=action))
            r.raise_for_status()
            return r.json()
        except Exception:
            return self._cli("goal", action)

    # --- internal ---

    def is_running(self) -> bool:
        """Return True if Hermes Agent is reachable."""
        try:
            self._http.get("/", timeout=3).raise_for_status()
            return True
        except Exception:
            return False

    def _cli(self, *args: str) -> dict[str, Any]:
        cmd = self._hermes_cmd(*args)
        result = subprocess.run(cmd, capture_output=True, text=True)
        return {
            "output": result.stdout.strip(),
            "error": result.stderr.strip(),
            "returncode": result.returncode,
        }

    @staticmethod
    def _hermes_cmd(*args: str) -> list[str]:
        if sys.platform == "win32":
            return ["hermes.cmd", *args]
        return ["hermes", *args]
