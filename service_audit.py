#!/usr/bin/env python3
"""Service audit for JURBOT (TopNews).
Read-only checks, no destructive operations.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import httpx

try:
    import redis  # type: ignore
except Exception:  # pragma: no cover - optional
    redis = None

LOG_PATH = os.path.join("logs", "audit_check.log")
REPORTS_DIR = "reports"
REPORT_MD = os.path.join(REPORTS_DIR, "service_audit.md")
REPORT_JSON = os.path.join(REPORTS_DIR, "service_audit.json")


@dataclass
class HttpCheck:
    url: str
    status: str
    status_code: int | None
    elapsed_ms: int | None
    error: str | None
    final_url: str | None = None


def setup_logger() -> logging.Logger:
    os.makedirs(os.path.dirname(LOG_PATH) or ".", exist_ok=True)
    logger = logging.getLogger("service_audit")
    logger.setLevel(logging.INFO)
    handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.handlers = [handler]
    logger.propagate = False
    return logger


def detect_environment() -> dict[str, Any]:
    env = os.environ
    railway = any(key.startswith("RAILWAY_") for key in env.keys())
    docker = os.path.exists("/.dockerenv") or bool(env.get("DOCKER"))
    return {
        "app_env": env.get("APP_ENV") or "prod",
        "railway": railway,
        "docker": docker,
        "public_base_url": env.get("PUBLIC_BASE_URL") or env.get("BASE_URL") or env.get("APP_URL"),
    }


def load_config() -> tuple[Any, str]:
    try:
        from config import railway_config as cfg  # type: ignore
        return cfg, "railway_config"
    except Exception:
        from config import config as cfg  # type: ignore
        return cfg, "config"


def parse_bot_handlers(bot_path: str) -> dict[str, bool]:
    if not os.path.exists(bot_path):
        return {"start_handler": False, "callback_handler": False, "inline_buttons": False}
    with open(bot_path, "r", encoding="utf-8") as f:
        data = f.read()
    return {
        "start_handler": "CommandHandler(\"start\"" in data or "CommandHandler('start'" in data,
        "callback_handler": "CallbackQueryHandler" in data,
        "inline_buttons": "InlineKeyboardButton" in data,
    }


def is_placeholder_token(token: str | None) -> bool:
    if not token:
        return True
    token = token.strip()
    return token == "YOUR_BOT_TOKEN" or token == ""


def token_sources(cfg: Any) -> dict[str, str | None]:
    """Return raw sources without applying selection rules (presence only)."""
    return {
        "BOT_TOKEN": getattr(cfg, "BOT_TOKEN", None),
        "TELEGRAM_TOKEN": getattr(cfg, "TELEGRAM_TOKEN", None),
        "BOT_TOKEN_PROD": getattr(cfg, "BOT_TOKEN_PROD", None),
        "BOT_TOKEN_SANDBOX": getattr(cfg, "BOT_TOKEN_SANDBOX", None),
        "APP_ENV": getattr(cfg, "APP_ENV", None),
    }


def select_effective_token(cfg: Any) -> tuple[str | None, str]:
    """
    Select token the same way app does (based on your config.py logic).
    Returns (token, selected_from).
    """
    app_env = getattr(cfg, "APP_ENV", "prod")
    bot_token_prod = getattr(cfg, "BOT_TOKEN_PROD", None)
    bot_token_sandbox = getattr(cfg, "BOT_TOKEN_SANDBOX", None)

    base = getattr(cfg, "BOT_TOKEN", None) or getattr(cfg, "TELEGRAM_TOKEN", None)
    selected_from = "BOT_TOKEN" if getattr(cfg, "BOT_TOKEN", None) else ("TELEGRAM_TOKEN" if getattr(cfg, "TELEGRAM_TOKEN", None) else "missing")

    # Prefer env-specific tokens
    if app_env == "sandbox" and bot_token_sandbox:
        return bot_token_sandbox, "BOT_TOKEN_SANDBOX"
    if app_env == "prod" and bot_token_prod:
        return bot_token_prod, "BOT_TOKEN_PROD"

    return base, selected_from


def build_rsshub_bases(base_url: str | None, mirrors: list[str] | None) -> list[str]:
    bases: list[str] = []
    for raw in [base_url] + (mirrors or []):
        if not raw:
            continue
        base = raw.strip()
        if not base:
            continue
        if not base.startswith("http"):
            base = f"https://{base}"
        base = base.rstrip("/")
        if base not in bases:
            bases.append(base)
    return bases


def resolve_source_urls(cfg: Any) -> list[dict[str, str]]:
    sources: list[dict[str, str]] = []
    sources_config = getattr(cfg, "SOURCES_CONFIG", {})
    base = getattr(cfg, "RSSHUB_BASE_URL", None)
    mirrors = getattr(cfg, "RSSHUB_MIRROR_URLS", [])
    rsshub_bases = build_rsshub_bases(base, mirrors)
    rsshub_base = rsshub_bases[0] if rsshub_bases else ""

    for _, cfg_item in sources_config.items():
        category = cfg_item.get("category", "")
        for src in cfg_item.get("sources", []):
            parsed = urlparse(src)
            domain = parsed.netloc.lower()
            entry = {"source": src, "category": category, "resolved": src, "kind": "html"}
            if "t.me" in domain or domain.endswith("t.me"):
                channel = src.replace("https://t.me/", "").replace("http://t.me/", "").replace("@", "").strip("/")
                if rsshub_base:
                    entry["resolved"] = f"{rsshub_base}/telegram/channel/{channel}"
                    entry["kind"] = "rsshub"
                else:
                    entry["kind"] = "rsshub-missing"
            elif "x.com" in domain or "twitter.com" in domain:
                username = src.replace("https://x.com/", "").replace("http://x.com/", "")
                username = username.replace("https://twitter.com/", "").replace("http://twitter.com/", "")
                username = username.replace("@", "").strip("/")
                if rsshub_base:
                    entry["resolved"] = f"{rsshub_base}/twitter/user/{username}"
                    entry["kind"] = "rsshub"
                else:
                    entry["kind"] = "rsshub-missing"
            else:
                if "rss" in src.lower() or src.lower().endswith((".xml", ".rss")):
                    entry["kind"] = "rss"
            sources.append(entry)
    return sources


def _build_httpx_kwargs(cfg: Any) -> dict[str, Any]:
    use_proxy = bool(getattr(cfg, "USE_PROXY", False))
    proxy_url = getattr(cfg, "PROXY_URL", None)
    if use_proxy and proxy_url:
        return {"trust_env": False, "proxies": proxy_url}
    return {"trust_env": True}


async def http_check(url: str, timeout_sec: float = 4.0, httpx_kwargs: dict[str, Any] | None = None) -> HttpCheck:
    start = time.time()
    try:
        kwargs = httpx_kwargs or {"trust_env": True}
        async with httpx.AsyncClient(timeout=timeout_sec, follow_redirects=True, **kwargs) as client:
            resp = await client.get(url, headers={"User-Agent": "JURBOT-AUDIT/1.0"})
        elapsed_ms = int((time.time() - start) * 1000)
        status = "OK" if resp.status_code < 400 else ("ERROR" if resp.status_code >= 500 else "WARNING")
        return HttpCheck(
            url=url,
            status=status,
            status_code=resp.status_code,
            elapsed_ms=elapsed_ms,
            error=None,
            final_url=str(resp.url),
        )
    except Exception as exc:
        elapsed_ms = int((time.time() - start) * 1000)
        return HttpCheck(url=url, status="ERROR", status_code=None, elapsed_ms=elapsed_ms, error=str(exc), final_url=None)


async def run_http_checks(
    urls: list[str],
    concurrency: int = 6,
    httpx_kwargs: dict[str, Any] | None = None,
) -> list[HttpCheck]:
    sem = asyncio.Semaphore(concurrency)

    async def _wrapped(u: str):
        async with sem:
            return await http_check(u, httpx_kwargs=httpx_kwargs)

    tasks = [asyncio.create_task(_wrapped(u)) for u in urls]
    results: list[HttpCheck] = []
    for item in await asyncio.gather(*tasks, return_exceptions=True):
        if isinstance(item, Exception):
            results.append(HttpCheck(url="unknown", status="ERROR", status_code=None, elapsed_ms=None, error=str(item), final_url=None))
        else:
            results.append(item)
    return results


def telegram_api_check(token: str, httpx_kwargs: dict[str, Any] | None = None) -> HttpCheck:
    url = f"https://api.telegram.org/bot{token}/getMe"
    start = time.time()
    try:
        kwargs = httpx_kwargs or {"trust_env": True}
        resp = httpx.get(url, timeout=5, follow_redirects=True, **kwargs)
        elapsed_ms = int((time.time() - start) * 1000)
        status = "OK" if resp.status_code == 200 else "ERROR"
        return HttpCheck(url=url, status=status, status_code=resp.status_code, elapsed_ms=elapsed_ms, error=None, final_url=str(resp.url))
    except Exception as exc:
        elapsed_ms = int((time.time() - start) * 1000)
        return HttpCheck(url=url, status="ERROR", status_code=None, elapsed_ms=elapsed_ms, error=str(exc), final_url=None)


def check_redis(redis_url: str | None) -> tuple[str, str]:
    if not redis_url:
        return "UNKNOWN", "REDIS_URL not set"
    if redis is None:
        return "UNKNOWN", "redis package not available"
    try:
        client = redis.Redis.from_url(redis_url, socket_timeout=2, socket_connect_timeout=2)
        client.ping()
        return "OK", "PING ok"
    except Exception as exc:
        return "ERROR", f"{exc}"


def read_db_tables(db_path: str) -> dict[str, Any]:
    if not os.path.exists(db_path):
        return {"exists": False}
    try:
        import sqlite3
        uri = f"file:{db_path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=5)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = sorted([row[0] for row in cur.fetchall()])
        cur.execute("SELECT name FROM sqlite_master WHERE type='index'")
        indexes = sorted([row[0] for row in cur.fetchall()])

        counts: dict[str, Any] = {}
        for name in ["published_news", "sources", "ai_usage", "source_events", "approved_users"]:
            if name in tables:
                cur.execute(f"SELECT COUNT(1) FROM {name}")
                counts[name] = cur.fetchone()[0]

        orphans: dict[str, Any] = {}
        if "user_source_settings" in tables and "sources" in tables:
            cur.execute("""
                SELECT COUNT(1)
                FROM user_source_settings us
                LEFT JOIN sources s ON s.id = us.source_id
                WHERE s.id IS NULL
            """)
            orphans["user_source_settings"] = cur.fetchone()[0]
        if "user_news_selections" in tables and "published_news" in tables:
            cur.execute("""
                SELECT COUNT(1)
                FROM user_news_selections uns
                LEFT JOIN published_news pn ON pn.id = uns.news_id
                WHERE pn.id IS NULL
            """)
            orphans["user_news_selections"] = cur.fetchone()[0]
        if "ai_summaries" in tables and "published_news" in tables:
            cur.execute("""
                SELECT COUNT(1)
                FROM ai_summaries a
                LEFT JOIN published_news pn ON pn.id = a.news_id
                WHERE pn.id IS NULL
            """)
            orphans["ai_summaries"] = cur.fetchone()[0]

        conn.close()
        return {"exists": True, "tables": tables, "indexes": indexes, "counts": counts, "orphans": orphans}
    except Exception as exc:
        return {"exists": True, "error": str(exc)}


def analyze_logs(log_paths: list[str]) -> dict[str, Any]:
    result = {"files": [], "errors": 0, "warnings": 0}
    for path in log_paths:
        if not os.path.exists(path):
            result["files"].append({"path": path, "exists": False})
            continue
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()[-500:]
            errors = sum(1 for line in lines if re.search(r"\bERROR\b", line))
            warnings = sum(1 for line in lines if re.search(r"\bWARNING\b", line))
            result["errors"] += errors
            result["warnings"] += warnings
            result["files"].append({"path": path, "exists": True, "errors": errors, "warnings": warnings})
        except Exception as exc:
            result["files"].append({"path": path, "exists": True, "error": str(exc)})
    return result


def build_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("ЖУРБОТ — Отчет об аудите услуг")
    lines.append("")
    lines.append("1. Резюме")
    lines.append("")
    lines.append(f"Общий статус: {report['overall_status']}")
    lines.append(f"Количество ошибок: {report['counts']['errors']}")
    lines.append(f"Количество предупреждений: {report['counts']['warnings']}")
    lines.append("")
    lines.append("2. Статус услуг")
    lines.append("")
    lines.append("| Сервис | Статус | Время ответа | Детали |")
    lines.append("|---|---|---|---|")
    for svc in report["services"]:
        lines.append(f"| {svc['name']} | {svc['status']} | {svc.get('response_time','-')} | {svc.get('errors','-')} |")
    lines.append("")
    lines.append("3. Токены")
    lines.append("")
    t = report.get("tokens", {})
    lines.append(f"- selected_from: {t.get('selected_from')}")
    lines.append(f"- effective_present: {t.get('effective_present')}")
    lines.append(f"- sources_present: {t.get('sources_present')}")
    lines.append("")
    lines.append("4. Статус бота (Telegram)")
    lines.append("")
    lines.append("| Имя | Telegram OK | Примечания |")
    lines.append("|---|---|---|")
    for bot in report["bots"]:
        lines.append(f"| {bot['name']} | {bot['telegram_ok']} | {bot.get('notes','-')} |")
    lines.append("")
    lines.append("5. Проверка ИИ")
    lines.append("")
    lines.append("| Поставщик | Статус | Средний ответ | Тайм-аут |")
    lines.append("|---|---|---|---|")
    for item in report["ai"]["providers"]:
        lines.append(f"| {item['provider']} | {item['status']} | {item.get('avg_ms','-')} | {item.get('timeout','-')} |")
    lines.append("")
    lines.append("6. Целостность базы данных")
    lines.append("")
    lines.append("| Проверка | Статус | Примечания |")
    lines.append("|---|---|---|")
    for item in report["database"]["checks"]:
        lines.append(f"| {item['check']} | {item['status']} | {item.get('notes','-')} |")
    lines.append("")
    lines.append("7. Источники")
    lines.append("")
    lines.append("| Source | Kind | Resolved | Status | Code | Error |")
    lines.append("|---|---|---|---|---:|---|")
    for item in report["parsing"]:
        lines.append(
            f"| {item['source']} | {item.get('kind','-')} | {item.get('resolved','-')} | {item.get('status','-')} | {item.get('status_code','-')} | {item.get('errors','-')} |"
        )
    lines.append("")
    lines.append("8. Безопасность")
    lines.append("")
    lines.append("| Проверка | Статус |")
    lines.append("|---|---|")
    for item in report["security"]:
        lines.append(f"| {item['check']} | {item['status']} |")
    lines.append("")
    lines.append("9. Критические вопросы")
    lines.append("")
    if not report["critical_issues"]:
        lines.append("Нет критических вопросов.")
    else:
        for item in report["critical_issues"]:
            lines.append(f"- {item['level']}: {item['message']}")
    lines.append("")
    lines.append(f"Сформировано: {report['generated_at']}")
    return "\n".join(lines)


def compute_overall_status(*, token_ok: bool, db_ok: bool, api_ok: bool, hard_errors: int, warnings: int) -> str:
    # Critical only if core is broken
    if not token_ok or not db_ok or not api_ok:
        return "Критический"
    if hard_errors > 0 or warnings > 0:
        return "Ухудшенный"
    return "Нормальный"


def _join_url(base: str, path: str) -> str:
    base = base.rstrip("/")
    path = path if path.startswith("/") else f"/{path}"
    return f"{base}{path}"


def main() -> int:
    logger = setup_logger()
    logger.info("Starting service audit")
    os.makedirs(REPORTS_DIR, exist_ok=True)

    env = detect_environment()
    cfg, cfg_source = load_config()
    app_env = getattr(cfg, "APP_ENV", env["app_env"])

    # tokens
    raw_sources = token_sources(cfg)
    effective_token, selected_from = select_effective_token(cfg)
    sources_present = {k: bool(v) for k, v in raw_sources.items() if k != "APP_ENV"}
    token_ok = bool(effective_token) and not is_placeholder_token(effective_token)

    # base URL for API checks
    public_base_url = env.get("public_base_url") or getattr(cfg, "PUBLIC_BASE_URL", None) or getattr(cfg, "WEBHOOK_BASE_URL", None)
    port = getattr(cfg, "PORT", 8080)
    tg_mode = getattr(cfg, "TG_MODE", "polling")
    if public_base_url:
        health_url = _join_url(str(public_base_url), "/health")
        ready_url = _join_url(str(public_base_url), "/ready")
        api_base_used = str(public_base_url)
    else:
        health_url = f"http://localhost:{port}/health"
        ready_url = f"http://localhost:{port}/ready"
        api_base_used = f"localhost:{port}"

    services: list[dict[str, Any]] = []

    httpx_kwargs = _build_httpx_kwargs(cfg)
    health_check = asyncio.run(http_check(health_url, timeout_sec=3.0, httpx_kwargs=httpx_kwargs))
    ready_check = asyncio.run(http_check(ready_url, timeout_sec=3.0, httpx_kwargs=httpx_kwargs))

    services.append({
        "name": f"API backend /health ({api_base_used})",
        "status": health_check.status if health_check.status_code else "UNKNOWN",
        "response_time": f"{health_check.elapsed_ms}ms" if health_check.elapsed_ms else "-",
        "errors": health_check.error or (f"{health_check.status_code} {health_check.final_url}" if health_check.status_code else "n/a"),
    })
    services.append({
        "name": f"API backend /ready ({api_base_used})",
        "status": ready_check.status if ready_check.status_code else "UNKNOWN",
        "response_time": f"{ready_check.elapsed_ms}ms" if ready_check.elapsed_ms else "-",
        "errors": ready_check.error or (f"{ready_check.status_code} {ready_check.final_url}" if ready_check.status_code else "n/a"),
    })

    # Mgmt API (sandbox only)
    if str(app_env) == "sandbox":
        mgmt_bind = getattr(cfg, "MGMT_BIND", "0.0.0.0")
        mgmt_port = getattr(cfg, "MGMT_PORT", 8081)
        mgmt_url = f"http://{mgmt_bind}:{mgmt_port}/mgmt/collection/stop"
        mgmt_check = asyncio.run(http_check(mgmt_url, timeout_sec=2.0, httpx_kwargs=httpx_kwargs))
        services.append({
            "name": "Mgmt API /mgmt/collection/stop",
            "status": mgmt_check.status if mgmt_check.status_code else "UNKNOWN",
            "response_time": f"{mgmt_check.elapsed_ms}ms" if mgmt_check.elapsed_ms else "-",
            "errors": mgmt_check.error or (f"{mgmt_check.status_code} {mgmt_check.final_url}" if mgmt_check.status_code else "n/a"),
        })
    else:
        services.append({
            "name": "Mgmt API /mgmt/collection/stop",
            "status": "SKIPPED",
            "response_time": "-",
            "errors": "not applicable in prod",
        })

    # Redis
    redis_status, redis_note = check_redis(getattr(cfg, "REDIS_URL", None))
    services.append({
        "name": "Redis",
        "status": "OK" if redis_status == "OK" else ("UNKNOWN" if redis_status == "UNKNOWN" else "ERROR"),
        "response_time": "-",
        "errors": redis_note,
    })

    # Database connectivity
    db_path = getattr(cfg, "DATABASE_PATH", "db/news.db")
    access_db_path = getattr(cfg, "ACCESS_DB_PATH", "db/access.db")
    db_info = read_db_tables(db_path)
    access_db_info = read_db_tables(access_db_path)

    services.append({
        "name": f"Database {db_path}",
        "status": "OK" if db_info.get("exists") and "error" not in db_info else "ERROR",
        "response_time": "-",
        "errors": db_info.get("error") or "-",
    })
    services.append({
        "name": f"Access DB {access_db_path}",
        "status": "OK" if access_db_info.get("exists") and "error" not in access_db_info else "ERROR",
        "response_time": "-",
        "errors": access_db_info.get("error") or "-",
    })

    # Bot (Telegram)
    bot_handlers = parse_bot_handlers("bot.py")
    bots: list[dict[str, Any]] = []
    if not token_ok:
        bots.append({
            "name": "effective",
            "telegram_ok": "UNKNOWN",
            "handlers_ok": "OK" if all(bot_handlers.values()) else "UNKNOWN",
            "ai_ok": "UNKNOWN",
            "notes": "effective token missing/placeholder",
        })
    else:
        tg_check = telegram_api_check(str(effective_token), httpx_kwargs=httpx_kwargs)
        bots.append({
            "name": "effective",
            "telegram_ok": "OK" if tg_check.status == "OK" else "ERROR",
            "handlers_ok": "OK" if all(bot_handlers.values()) else "UNKNOWN",
            "ai_ok": "UNKNOWN",
            "notes": f"getMe {tg_check.status_code}",
        })

    # AI providers (reachability check only)
    ai_providers: list[dict[str, Any]] = []
    deepseek_key = getattr(cfg, "DEEPSEEK_API_KEY", "")
    deepseek_endpoint = getattr(cfg, "DEEPSEEK_API_ENDPOINT", None)
    ai_timeout = getattr(cfg, "AI_SUMMARY_TIMEOUT", None)
    if deepseek_endpoint:
        check = asyncio.run(http_check(deepseek_endpoint, timeout_sec=3.0, httpx_kwargs=httpx_kwargs))
        # 401/403/405 => reachable but auth/method
        reachable = check.status_code in (200, 401, 403, 405)
        status = "OK" if reachable else ("UNKNOWN" if check.status_code is None else "ERROR")
        ai_providers.append({
            "provider": "DeepSeek",
            "status": status if deepseek_key else "UNKNOWN",
            "avg_ms": f"{check.elapsed_ms}ms" if check.elapsed_ms else "-",
            "timeout": f"{ai_timeout}s" if ai_timeout else "-",
        })
    else:
        ai_providers.append({"provider": "DeepSeek", "status": "UNKNOWN", "avg_ms": "-", "timeout": "-"})

    # Sources checks
    sources = resolve_source_urls(cfg)
    source_urls = [s["resolved"] for s in sources if s["kind"] != "rsshub-missing"]
    try:
        source_checks = asyncio.run(run_http_checks(source_urls, concurrency=6, httpx_kwargs=httpx_kwargs)) if source_urls else []
    except Exception as exc:
        logger.warning(f"Source checks failed: {exc}")
        source_checks = []
    check_map = {c.url: c for c in source_checks}

    parsing: list[dict[str, Any]] = []
    for src in sources:
        resolved = src["resolved"]
        kind = src["kind"]
        if kind == "rsshub-missing":
            parsing.append({
                "source": src["source"],
                "kind": kind,
                "resolved": resolved,
                "status": "UNKNOWN",
                "status_code": None,
                "last_loaded": "-",
                "errors": "RSSHub base missing",
            })
            continue

        check = check_map.get(resolved)
        if check is None:
            parsing.append({
                "source": src["source"],
                "kind": kind,
                "resolved": resolved,
                "status": "UNKNOWN",
                "status_code": None,
                "last_loaded": "-",
                "errors": "not checked",
            })
            continue

        parsing.append({
            "source": src["source"],
            "kind": kind,
            "resolved": resolved,
            "status": "OK" if check.status == "OK" else ("WARNING" if check.status == "WARNING" else "ERROR"),
            "status_code": check.status_code,
            "last_loaded": "-",
            "errors": check.error or "",
            "final_url": check.final_url,
        })

    # Security checks
    webhook_base = getattr(cfg, "WEBHOOK_BASE_URL", None)
    webhook_secret = getattr(cfg, "WEBHOOK_SECRET", None)

    security: list[dict[str, Any]] = []
    security.append({
        "check": "Webhook secret configured",
        "status": "OK" if (tg_mode == "webhook" and webhook_secret) or tg_mode != "webhook" else "WARNING",
    })
    security.append({
        "check": "Webhook base URL set",
        "status": "OK" if (tg_mode == "webhook" and webhook_base) or tg_mode != "webhook" else "WARNING",
    })
    security.append({
        "check": "Admin-only sandbox policy",
        "status": "OK" if str(app_env) == "sandbox" else "UNKNOWN",
    })

    # DB checks
    db_checks: list[dict[str, Any]] = []
    required_tables = ["published_news", "approved_users", "ai_usage", "source_events"]
    missing_tables = []
    if db_info.get("tables"):
        for table in required_tables:
            if table not in db_info["tables"]:
                missing_tables.append(table)
    db_checks.append({"check": "Required tables", "status": "ERROR" if missing_tables else "OK", "notes": ", ".join(missing_tables) if missing_tables else "present"})

    idx_required = ["idx_title", "idx_llm_cache_expires", "idx_source_events_source_time"]
    missing_idx = []
    if db_info.get("indexes"):
        for idx in idx_required:
            if idx not in db_info["indexes"]:
                missing_idx.append(idx)
    db_checks.append({"check": "Indexes", "status": "WARNING" if missing_idx else "OK", "notes": ", ".join(missing_idx) if missing_idx else "present"})

    if db_info.get("orphans"):
        orphan_notes = ", ".join(f"{k}={v}" for k, v in db_info["orphans"].items())
        orphan_status = "OK" if all(v == 0 for v in db_info["orphans"].values()) else "WARNING"
        db_checks.append({"check": "Orphan records", "status": orphan_status, "notes": orphan_notes})
    else:
        db_checks.append({"check": "Orphan records", "status": "UNKNOWN", "notes": "not checked"})

    # Logging
    log_analysis = analyze_logs([os.path.join("logs", "bot_prod.log"), os.path.join("logs", "bot_sandbox.log")])

    # Performance (placeholder, can be extended)
    perf = {
        "Memory usage": "UNKNOWN",
        "CPU spikes (30d)": "UNKNOWN",
        "Slow queries > 1s": "UNKNOWN",
        "Slow query log": "UNKNOWN",
    }

    # Critical issues
    critical: list[dict[str, str]] = []
    if not token_ok:
        critical.append({"level": "КРИТИЧЕСКИЙ", "message": "Effective TELEGRAM/BOT token missing or placeholder"})
    if not db_info.get("exists"):
        critical.append({"level": "КРИТИЧЕСКИЙ", "message": f"Database not found: {db_path}"})

    # Counts
    hard_errors = 0
    warnings = 0
    for svc in services:
        if svc["status"] == "ERROR":
            hard_errors += 1
        if svc["status"] == "WARNING":
            warnings += 1

    # source errors
    for p in parsing:
        if p["status"] == "ERROR":
            hard_errors += 1
        if p["status"] == "WARNING":
            warnings += 1

    if log_analysis.get("errors"):
        hard_errors += int(log_analysis.get("errors", 0))
        warnings += int(log_analysis.get("warnings", 0))

    db_ok = bool(db_info.get("exists")) and ("error" not in db_info)
    # API ok logic:
    # if public_base_url set -> we expect health+ready to be reachable (>=400 is still reachable)
    # if not set -> don't make it critical (maybe no API in this service)
    if public_base_url:
        api_ok = health_check.status_code is not None and ready_check.status_code is not None
    else:
        api_ok = tg_mode != "webhook"

    overall = compute_overall_status(
        token_ok=token_ok,
        db_ok=db_ok,
        api_ok=api_ok,
        hard_errors=hard_errors,
        warnings=warnings,
    )

    report = {
        "overall_status": overall,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "environment": {
            "app_env": str(app_env),
            "config_source": cfg_source,
            "railway": env["railway"],
            "docker": env["docker"],
            "public_base_url": public_base_url,
            "api_base_used": api_base_used,
        },
        "tokens": {
            "selected_from": selected_from,
            "effective_present": token_ok,
            "sources_present": sources_present,
        },
        "services": services,
        "bots": bots,
        "ai": {
            "providers": ai_providers,
            "budget_usd": getattr(cfg, "AI_DAILY_BUDGET_USD", None),
            "budget_tokens": getattr(cfg, "AI_DAILY_BUDGET_TOKENS", None),
        },
        "database": {
            "path": db_path,
            "checks": db_checks,
            "counts": db_info.get("counts", {}),
            "tables": db_info.get("tables", []),
        },
        "parsing": parsing,
        "security": security,
        "performance": perf,
        "critical_issues": critical,
        "counts": {"errors": hard_errors, "warnings": warnings},
        "logs": log_analysis,
    }

    md = build_markdown(report)
    with open(REPORT_MD, "w", encoding="utf-8") as f:
        f.write(md)
    with open(REPORT_JSON, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    logger.info("Audit complete")
    print(f"Audit complete. Overall status: {report['overall_status']}")
    print(f"Reports: {REPORT_MD}, {REPORT_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
