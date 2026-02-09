from __future__ import annotations

import logging
from typing import Any

from config.config import (
    AI_DAILY_BUDGET_TOKENS,
    AI_DAILY_BUDGET_USD,
    AI_DAILY_MIN_RESERVE_USD,
)

logger = logging.getLogger(__name__)


class AIBudgetManager:
    def __init__(self, db):
        self.db = db
        self.daily_limit_usd = float(AI_DAILY_BUDGET_USD or 0.0)
        self.daily_limit_tokens = int(AI_DAILY_BUDGET_TOKENS or 0)
        self.min_reserve_usd = float(AI_DAILY_MIN_RESERVE_USD or 0.0)
        self._degraded_tasks: set[str] = set()

    def get_today_usage(self) -> dict[str, Any]:
        if not self.db:
            return {
                "date": None,
                "tokens_in": 0,
                "tokens_out": 0,
                "cost_usd": 0.0,
                "calls": 0,
                "cache_hits": 0,
            }
        return self.db.get_ai_usage_daily()

    def record_usage(
        self,
        tokens_in: int,
        tokens_out: int,
        cost_usd: float,
        calls: int = 1,
        cache_hit: bool = False,
    ) -> bool:
        if not self.db:
            return False
        return self.db.add_ai_usage_daily(
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost_usd,
            calls=calls,
            cache_hit=cache_hit,
        )

    def _over_budget(self, estimated_tokens: int = 0) -> bool:
        usage = self.get_today_usage()
        cost_usd = float(usage.get("cost_usd", 0.0) or 0.0)
        if self.daily_limit_usd > 0:
            limit = max(0.0, self.daily_limit_usd - self.min_reserve_usd)
            if cost_usd >= limit:
                return True

        if self.daily_limit_tokens > 0:
            used_tokens = int((usage.get("tokens_in", 0) or 0) + (usage.get("tokens_out", 0) or 0))
            if used_tokens + max(0, int(estimated_tokens)) >= self.daily_limit_tokens:
                return True

        return False

    def budget_ok(self, task: str, estimated_tokens: int = 0) -> bool:
        if self._over_budget(estimated_tokens):
            self._degraded_tasks.update({"summary", "cleanup", "hashtags_ai"})
            return task not in self._degraded_tasks
        return True

    def degrade_policy(self) -> set[str]:
        if self._over_budget(0):
            self._degraded_tasks.update({"summary", "cleanup", "hashtags_ai"})
        return set(self._degraded_tasks)

    def get_state(self) -> dict[str, Any]:
        usage = self.get_today_usage()
        degraded = self.degrade_policy()
        budget_state = "DEGRADED" if degraded else "OK"
        return {
            "budget_state": budget_state,
            "degraded_features": sorted(degraded),
            "usage": usage,
        }
