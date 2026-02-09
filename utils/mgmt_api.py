"""Minimal management API for collection stop (sandbox-only)."""
from __future__ import annotations

from aiohttp import web

from core.services.collection_stop import (
    get_global_collection_stop_status,
    is_sandbox,
    set_global_collection_stop,
)


def _maybe_404_if_prod() -> web.Response | None:
    if not is_sandbox():
        return web.Response(status=404)
    return None


async def handle_get_stop(request: web.Request) -> web.Response:
    prod_resp = _maybe_404_if_prod()
    if prod_resp is not None:
        return prod_resp
    enabled, ttl_remaining = get_global_collection_stop_status()
    payload = {"enabled": enabled, "ttl_sec_remaining": ttl_remaining}
    return web.json_response(payload)


async def handle_post_stop(request: web.Request) -> web.Response:
    prod_resp = _maybe_404_if_prod()
    if prod_resp is not None:
        return prod_resp
    try:
        data = await request.json()
    except Exception:
        data = {}

    enabled = bool(data.get("enabled", False))
    ttl_sec = data.get("ttl_sec")
    reason = data.get("reason")
    by = data.get("by")
    ttl_value = int(ttl_sec) if isinstance(ttl_sec, int) else 3600

    set_global_collection_stop(enabled, ttl_sec=ttl_value, reason=reason, by=by)
    enabled_now, ttl_remaining = get_global_collection_stop_status()
    payload = {"enabled": enabled_now, "ttl_sec_remaining": ttl_remaining}
    return web.json_response(payload)


def create_mgmt_app() -> web.Application:
    app = web.Application()
    app.add_routes(
        [
            web.get("/mgmt/collection/stop", handle_get_stop),
            web.post("/mgmt/collection/stop", handle_post_stop),
        ]
    )
    return app


async def start_mgmt_api(bind: str, port: int):
    app = create_mgmt_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, bind, port)
    await site.start()
    return runner


async def stop_mgmt_api(runner: web.AppRunner | None) -> None:
    if runner is None:
        return
    await runner.cleanup()
