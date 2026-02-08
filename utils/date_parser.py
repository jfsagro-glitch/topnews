"""Date parsing helpers for news pages."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo
import os
from typing import Optional

from bs4 import BeautifulSoup

DATE_PATTERNS = [
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
    "%d.%m.%Y %H:%M",
    "%d.%m.%Y",
]

URL_DATE_RE = re.compile(r"/(20\d{2})/(\d{2})/(\d{2})/")

_PROJECT_TZ_NAME = os.getenv("PROJECT_TIMEZONE", "UTC")


def _get_project_tz() -> ZoneInfo:
    try:
        return ZoneInfo(_PROJECT_TZ_NAME)
    except Exception:
        return ZoneInfo("UTC")


def _parse_date_str(value: str) -> Optional[datetime]:
    if not value:
        return None
    raw = value.strip()
    try:
        if raw.endswith("Z"):
            raw = raw.replace("Z", "+00:00")
        return datetime.fromisoformat(raw)
    except Exception:
        pass

    try:
        return parsedate_to_datetime(raw)
    except Exception:
        pass

    for fmt in DATE_PATTERNS:
        try:
            return datetime.strptime(raw, fmt)
        except Exception:
            continue
    return None


def _normalize_to_utc(dt: datetime) -> datetime:
    if dt.tzinfo:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    project_tz = _get_project_tz()
    local_dt = dt.replace(tzinfo=project_tz)
    return local_dt.astimezone(timezone.utc).replace(tzinfo=None)


def parse_published_at(html: str, url: str | None = None) -> Optional[datetime]:
    """Parse published date from HTML using meta/time/JSON-LD/URL."""
    info = _parse_published_info_impl(html, url)
    if info.get("published_at"):
        return info.get("published_at")
    if info.get("published_date"):
        try:
            return datetime.fromisoformat(info.get("published_date"))
        except Exception:
            return None
    return None


def parse_published_info(html: str, url: str | None = None) -> dict:
    """Deprecated: kept for compatibility with older callers."""
    _ = parse_published_at(html, url)
    return _parse_published_info_impl(html, url)


def _parse_published_info_impl(html: str, url: str | None = None) -> dict:
    """Return published fields + confidence + source label."""
    if not html:
        return {
            "published_at": None,
            "published_date": None,
            "published_time": None,
            "published_confidence": "none",
            "published_source": None,
        }

    soup = BeautifulSoup(html, "html.parser")

    meta_candidates = [
        ("property", "article:published_time", "meta:article:published_time", "high"),
        ("property", "og:published_time", "meta:og:published_time", "high"),
        ("itemprop", "datePublished", "meta:itemprop:datePublished", "high"),
        ("name", "datePublished", "meta:name:datePublished", "high"),
        ("name", "pubdate", "meta:name:pubdate", "medium"),
        ("name", "publishdate", "meta:name:publishdate", "medium"),
        ("name", "date", "meta:name:date", "medium"),
    ]
    for attr, val, source, confidence in meta_candidates:
        tag = soup.find("meta", attrs={attr: val})
        if tag and tag.get("content"):
            dt = _parse_date_str(tag.get("content"))
            if dt:
                return _build_info_from_datetime(dt, confidence, source)

    time_tag = soup.find("time")
    if time_tag and time_tag.get("datetime"):
        dt = _parse_date_str(time_tag.get("datetime"))
        if dt:
            return _build_info_from_datetime(dt, "medium", "time:datetime")

    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(script.string or "")
        except Exception:
            continue
        nodes = data if isinstance(data, list) else [data]
        for node in nodes:
            if not isinstance(node, dict):
                continue
            if node.get("@type") in ("NewsArticle", "Article", "Report"):
                dt = _parse_date_str(node.get("datePublished") or node.get("dateModified"))
                if dt:
                    return _build_info_from_datetime(dt, "medium", "jsonld:datePublished")

    if url:
        url_date = parse_url_date(url)
        if url_date:
            return {
                "published_at": None,
                "published_date": url_date.isoformat(),
                "published_time": None,
                "published_confidence": "low",
                "published_source": "url:date",
            }

    return {
        "published_at": None,
        "published_date": None,
        "published_time": None,
        "published_confidence": "none",
        "published_source": None,
    }


def split_date_time(dt: datetime) -> tuple[str, str | None]:
    """Return date and time strings (YYYY-MM-DD, HH:MM) in project TZ."""
    local_dt = to_project_tz(dt)
    date_str = local_dt.strftime("%Y-%m-%d")
    time_str = local_dt.strftime("%H:%M") if local_dt.time() else None
    return date_str, time_str


def parse_url_date(url: str | None) -> Optional[datetime.date]:
    if not url:
        return None
    match = URL_DATE_RE.search(url)
    if not match:
        return None
    try:
        return datetime.strptime("-".join(match.groups()), "%Y-%m-%d").date()
    except Exception:
        return None


def parse_datetime_value(value: object) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _normalize_to_utc(value)
    if isinstance(value, str):
        dt = _parse_date_str(value)
        if dt:
            return _normalize_to_utc(dt)
    return None


def to_project_tz(dt: datetime) -> datetime:
    project_tz = _get_project_tz()
    if dt.tzinfo:
        return dt.astimezone(project_tz)
    utc_dt = dt.replace(tzinfo=timezone.utc)
    return utc_dt.astimezone(project_tz)


def get_project_now() -> datetime:
    return datetime.now(tz=_get_project_tz())


def _build_info_from_datetime(dt: datetime, confidence: str, source: str) -> dict:
    normalized = _normalize_to_utc(dt)
    pub_date, pub_time = split_date_time(normalized)
    return {
        "published_at": normalized,
        "published_date": pub_date,
        "published_time": pub_time,
        "published_confidence": confidence,
        "published_source": source,
    }
