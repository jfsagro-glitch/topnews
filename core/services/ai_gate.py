from __future__ import annotations

from typing import Any


class AITickGate:
    def __init__(self, max_calls: int = 0):
        self.max_calls = max(0, int(max_calls))
        self.tick_id: str | None = None
        self.calls = 0
        self.disabled: set[str] = set()
        self._degrade_order = ["summary", "cleanup", "hashtags_ai"]
        self._degrade_index = 0

    def begin_tick(self, tick_id: str) -> None:
        if tick_id != self.tick_id:
            self.tick_id = tick_id
            self.calls = 0
            self.disabled = set()
            self._degrade_index = 0

    def can_call(self, task: str) -> bool:
        if self.max_calls <= 0:
            return True
        if task in self.disabled:
            return False
        if self.calls < self.max_calls:
            return True
        if self._degrade_index < len(self._degrade_order):
            self.disabled.add(self._degrade_order[self._degrade_index])
            self._degrade_index += 1
        return False

    def record_call(self, task: str) -> None:
        if self.max_calls <= 0:
            return
        self.calls += 1

    def get_state(self) -> dict[str, Any]:
        return {
            "tick_id": self.tick_id,
            "calls": self.calls,
            "max_calls": self.max_calls,
            "disabled": sorted(self.disabled),
        }
