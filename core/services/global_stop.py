"""Global stop API with async event signaling.

This module wraps collection_stop.py and adds asyncio.Event-based signaling
for real-time pause/resume without polling.

The global stop is stored in Redis (via collection_stop module) and can be:
- Toggled via admin UI in the bot
- Disabled by deleting the Redis key 'jur:stop:global'
- Queried/set via this module's API

DO NOT disable global stop by editing this file. Use Redis key deletion or admin UI.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional, Tuple

from .collection_stop import (
    get_global_collection_stop,
    get_global_collection_stop_status,
    set_global_collection_stop,
    _get_redis_client,
)

logger = logging.getLogger(__name__)

# Configuration
REDIS_POLL_INTERVAL_SEC = 2  # How often to check Redis for state changes

# Global asyncio event for signaling stop/resume across tasks
_global_stop_event: Optional[asyncio.Event] = None
_monitor_task: Optional[asyncio.Task] = None


async def init_global_stop_event() -> None:
    """Initialize the global stop event and start monitoring Redis state.
    
    This should be called once at bot startup to enable async wait functions.
    The function is idempotent - calling it multiple times is safe and will
    only initialize once.
    
    The initialization starts a background monitoring task that periodically
    checks Redis and updates the asyncio.Event. This task runs for the lifetime
    of the application and will be automatically cancelled when the event loop
    is shut down.
    """
    global _global_stop_event, _monitor_task
    
    if _global_stop_event is not None:
        logger.debug("Global stop event already initialized")
        return
    
    _global_stop_event = asyncio.Event()
    
    # Set initial state based on Redis
    if get_global_stop():
        _global_stop_event.set()
    else:
        _global_stop_event.clear()
    
    # Start background task to monitor Redis and update event
    _monitor_task = asyncio.create_task(_monitor_redis_state())
    logger.info("Global stop event initialized with Redis monitoring")


async def _monitor_redis_state() -> None:
    """Background task to monitor Redis and update the asyncio.Event.
    
    This task runs indefinitely, checking Redis every REDIS_POLL_INTERVAL_SEC seconds
    and synchronizing the asyncio.Event with the Redis state. The task will be
    automatically cancelled when the event loop shuts down or when the application exits.
    
    No explicit cleanup is required as the task is designed to run for the application's
    lifetime and handle cancellation gracefully.
    """
    global _global_stop_event
    
    while True:
        try:
            current_redis_state = get_global_stop()
            event_is_set = _global_stop_event.is_set() if _global_stop_event else False
            
            # Sync event with Redis state
            if current_redis_state and not event_is_set:
                _global_stop_event.set()
                logger.info("🔴 Global stop activated (from Redis)")
            elif not current_redis_state and event_is_set:
                _global_stop_event.clear()
                logger.info("🟢 Global stop cleared (from Redis)")
            
            # Check every REDIS_POLL_INTERVAL_SEC seconds
            await asyncio.sleep(REDIS_POLL_INTERVAL_SEC)
        except asyncio.CancelledError:
            logger.info("Global stop monitor task cancelled")
            break
        except Exception as exc:
            logger.error(f"Error in global stop monitor: {exc}", exc_info=True)
            await asyncio.sleep(5)


async def wait_global_stop() -> None:
    """Wait until global stop becomes active.
    
    Returns immediately if already stopped, otherwise blocks until stop is activated.
    Use with asyncio.wait_for() to add timeout.
    """
    if _global_stop_event is None:
        # Fallback to polling if event not initialized
        while not get_global_stop():
            await asyncio.sleep(1)
        return
    
    await _global_stop_event.wait()


async def wait_for_resume() -> None:
    """Wait until global stop becomes inactive (resumed).
    
    Returns immediately if not stopped, otherwise blocks until resumed.
    """
    if _global_stop_event is None:
        # Fallback to polling if event not initialized
        while get_global_stop():
            await asyncio.sleep(1)
        return
    
    # Wait for event to be cleared
    while _global_stop_event.is_set():
        await asyncio.sleep(0.5)


def get_global_stop() -> bool:
    """Check if global stop is currently active.
    
    Returns True if system is stopped, False otherwise.
    Queries Redis via collection_stop module.
    """
    return get_global_collection_stop()


def set_global_stop(enabled: bool, ttl_sec: Optional[int] = 3600, reason: Optional[str] = None, by: Optional[str] = None) -> None:
    """Set the global stop state.
    
    Args:
        enabled: True to stop, False to resume
        ttl_sec: Time-to-live in seconds (default 3600, None for no expiry)
        reason: Optional reason for the stop
        by: Optional user/process that triggered the stop
    
    Note: This updates Redis and signals the asyncio.Event if initialized.
    """
    # Update Redis state
    set_global_collection_stop(enabled=enabled, ttl_sec=ttl_sec, reason=reason, by=by)
    
    # Immediately update event state if initialized
    global _global_stop_event
    if _global_stop_event is not None:
        if enabled:
            _global_stop_event.set()
            logger.info(f"🔴 Global stop SET by={by}, reason={reason}")
        else:
            _global_stop_event.clear()
            logger.info(f"🟢 Global stop CLEARED by={by}")


def toggle_global_stop(ttl_sec: Optional[int] = 3600, reason: Optional[str] = None, by: Optional[str] = None) -> bool:
    """Toggle the global stop state.
    
    Returns the new state (True if now stopped, False if now resumed).
    """
    current = get_global_stop()
    new_state = not current
    set_global_stop(new_state, ttl_sec=ttl_sec, reason=reason, by=by)
    return new_state


def get_global_stop_status_str() -> Tuple[bool, str]:
    """Get user-friendly status string.
    
    Returns:
        Tuple of (is_stopped, status_message)
    """
    stopped, ttl_remaining = get_global_collection_stop_status()
    
    if stopped:
        if ttl_remaining is not None and ttl_remaining > 0:
            minutes = ttl_remaining // 60
            return True, f"🔴 STOPPED (expires in {minutes}m)"
        else:
            return True, "🔴 STOPPED (no expiry)"
    else:
        return False, "🟢 RUNNING"


def is_redis_available() -> bool:
    """Check if Redis connection is available.
    
    Returns True if Redis client can be obtained, False otherwise.
    """
    client = _get_redis_client()
    if client is None:
        return False
    
    try:
        # Try a simple ping
        client.ping()
        return True
    except Exception:
        return False