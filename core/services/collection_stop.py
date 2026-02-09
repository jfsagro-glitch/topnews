"""Global collection stop flag (sandbox-only) stored in Redis."""
from __future__ import annotations

import logging
import os
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

STOP_KEY = "jur:stop:global:sandbox"
STOP_BY_KEY = "jur:stop:global:sandbox:by"
STOP_REASON_KEY = "jur:stop:global:sandbox:reason"
DEFAULT_TTL_SEC = 3600

_redis_client = None


def is_sandbox() -> bool:
    return (os.getenv("APP_ENV", "prod") or "prod").strip().lower() == "sandbox"


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


def get_global_collection_stop() -> bool:
    if not is_sandbox():
        return False
    client = _get_redis_client()
    if client is None:
        return False
    try:
        value = client.get(STOP_KEY)
        return value == "1"
    except Exception as exc:
        logger.debug(f"Redis get stop flag failed: {exc}")
        return False


def get_global_collection_stop_status() -> Tuple[bool, Optional[int]]:
    if not is_sandbox():
        return False, None
    client = _get_redis_client()
    if client is None:
        return False, None
    try:
        value = client.get(STOP_KEY)
        if value != "1":
            return False, None
        ttl = client.ttl(STOP_KEY)
        ttl_value = ttl if isinstance(ttl, int) and ttl >= 0 else None
        return True, ttl_value
    except Exception as exc:
        logger.debug(f"Redis get stop status failed: {exc}")
        return False, None


def set_global_collection_stop(
    enabled: bool,
    ttl_sec: int = DEFAULT_TTL_SEC,
    reason: str | None = None,
    by: str | None = None,
) -> None:
    if not is_sandbox():
        return
    client = _get_redis_client()
    if client is None:
        return
    try:
        if enabled:
            ttl = max(60, int(ttl_sec)) if ttl_sec else DEFAULT_TTL_SEC
            client.set(STOP_KEY, "1", ex=ttl)
            if by:
                client.set(STOP_BY_KEY, by, ex=ttl)
            if reason:
                client.set(STOP_REASON_KEY, reason, ex=ttl)
        else:
            client.delete(STOP_KEY)
            client.delete(STOP_BY_KEY)
            client.delete(STOP_REASON_KEY)
    except Exception as exc:
        logger.debug(f"Redis set stop flag failed: {exc}")
