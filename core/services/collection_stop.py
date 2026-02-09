"""Global collection stop flag stored in Redis.

Hard-stop requirements:
- If global key is set, ALL envs must stop collection/publishing/AI.
- Legacy sandbox-only key is still supported for compatibility.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

GLOBAL_STOP_KEY = "jur:stop:global"
LEGACY_SANDBOX_KEY = "jur:stop:global:sandbox"
LEGACY_SANDBOX_BY_KEY = "jur:stop:global:sandbox:by"
LEGACY_SANDBOX_REASON_KEY = "jur:stop:global:sandbox:reason"
GLOBAL_STOP_BY_KEY = "jur:stop:global:by"
GLOBAL_STOP_REASON_KEY = "jur:stop:global:reason"
DEFAULT_TTL_SEC = 3600

_redis_client = None


def is_sandbox() -> bool:
    return (os.getenv("APP_ENV", "prod") or "prod").strip().lower() == "sandbox"

def _get_app_env(app_env: str | None = None) -> str:
    return (app_env or os.getenv("APP_ENV", "prod") or "prod").strip().lower()


def _get_redis_client():
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        return None
    try:
        import redis

        _redis_client = redis.Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_timeout=1,
            socket_connect_timeout=1,
            health_check_interval=30,
        )
        return _redis_client
    except Exception as exc:
        logger.debug(f"Redis init failed: {exc}")
        return None


@dataclass(frozen=True)
class StopState:
    enabled: bool
    ttl_sec_remaining: int | None
    key: str | None


def _ttl(client, key: str) -> int | None:
    try:
        ttl_value = client.ttl(key)
        return ttl_value if isinstance(ttl_value, int) and ttl_value >= 0 else None
    except Exception:
        return None


def get_global_collection_stop_state(redis_client=None, app_env: str | None = None) -> StopState:
    """Return effective stop state for this env.

    - Global key stops everywhere.
    - Legacy sandbox key only affects sandbox.
    """
    env = _get_app_env(app_env)
    client = redis_client if redis_client is not None else _get_redis_client()
    if client is None:
        return StopState(False, None, None)
    try:
        if client.get(GLOBAL_STOP_KEY):
            return StopState(True, _ttl(client, GLOBAL_STOP_KEY), GLOBAL_STOP_KEY)
        if env == "sandbox" and client.get(LEGACY_SANDBOX_KEY):
            return StopState(True, _ttl(client, LEGACY_SANDBOX_KEY), LEGACY_SANDBOX_KEY)
    except Exception as exc:
        logger.debug(f"Redis get stop state failed: {exc}")
    return StopState(False, None, None)


def get_global_collection_stop(redis_client=None, app_env: str | None = None) -> bool:
    return get_global_collection_stop_state(redis_client=redis_client, app_env=app_env).enabled


def get_global_collection_stop_status(redis_client=None, app_env: str | None = None) -> Tuple[bool, Optional[int]]:
    state = get_global_collection_stop_state(redis_client=redis_client, app_env=app_env)
    return state.enabled, state.ttl_sec_remaining


def set_global_collection_stop(
    enabled: bool,
    ttl_sec: int | None = DEFAULT_TTL_SEC,
    reason: str | None = None,
    by: str | None = None,
) -> None:
    client = _get_redis_client()
    if client is None:
        return

    try:
        if enabled:
            ttl_value: int | None
            if ttl_sec is None or int(ttl_sec) <= 0:
                ttl_value = None
            else:
                ttl_value = max(60, int(ttl_sec))

            if ttl_value is None:
                client.set(GLOBAL_STOP_KEY, "1")
                if by:
                    client.set(GLOBAL_STOP_BY_KEY, by)
                if reason:
                    client.set(GLOBAL_STOP_REASON_KEY, reason)
            else:
                client.set(GLOBAL_STOP_KEY, "1", ex=ttl_value)
                if by:
                    client.set(GLOBAL_STOP_BY_KEY, by, ex=ttl_value)
                if reason:
                    client.set(GLOBAL_STOP_REASON_KEY, reason, ex=ttl_value)
            # Prefer global key; clear legacy sandbox-only key if present.
            client.delete(LEGACY_SANDBOX_KEY)
            client.delete(LEGACY_SANDBOX_BY_KEY)
            client.delete(LEGACY_SANDBOX_REASON_KEY)
        else:
            client.delete(GLOBAL_STOP_KEY)
            client.delete(GLOBAL_STOP_BY_KEY)
            client.delete(GLOBAL_STOP_REASON_KEY)
            # Also clear legacy sandbox-only keys to avoid confusing partial resumes.
            client.delete(LEGACY_SANDBOX_KEY)
            client.delete(LEGACY_SANDBOX_BY_KEY)
            client.delete(LEGACY_SANDBOX_REASON_KEY)
    except Exception as exc:
        logger.debug(f"Redis set stop flag failed: {exc}")


def get_global_collection_stop_meta(redis_client=None, app_env: str | None = None) -> dict:
    """Return stop state + optional metadata keys if present."""
    state = get_global_collection_stop_state(redis_client=redis_client, app_env=app_env)
    if not state.enabled or not state.key:
        return {"state": state, "by": None, "reason": None}
    client = redis_client if redis_client is not None else _get_redis_client()
    if client is None:
        return {"state": state, "by": None, "reason": None}
    try:
        if state.key == GLOBAL_STOP_KEY:
            by = client.get(GLOBAL_STOP_BY_KEY)
            reason = client.get(GLOBAL_STOP_REASON_KEY)
        else:
            by = client.get(LEGACY_SANDBOX_BY_KEY)
            reason = client.get(LEGACY_SANDBOX_REASON_KEY)
    except Exception:
        by = None
        reason = None
    return {"state": state, "by": by, "reason": reason}
