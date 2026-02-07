"""Date parsing helpers for news pages."""
from __future__ import annotations

import json
import re
from datetime import datetime
from email.utils import parsedate_to_datetime
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


def _normalize_dt(dt: datetime) -> datetime:
    if dt.tzinfo:
        return dt.astimezone().replace(tzinfo=None)
    return dt


def parse_published_at(html: str, url: str | None = None) -> Optional[datetime]:
    """Parse published date from HTML using meta/time/JSON-LD/URL."""
    if not html:
        return None

    soup = BeautifulSoup(html, "html.parser")

    # Meta tags
    meta_candidates = [
        ("property", "article:published_time"),
        ("property", "article:modified_time"),
        ("name", "pubdate"),
        ("name", "publishdate"),
        ("name", "date"),
        ("itemprop", "datePublished"),
    ]
    for attr, val in meta_candidates:
        tag = soup.find("meta", attrs={attr: val})
        if tag and tag.get("content"):
            dt = _parse_date_str(tag.get("content"))
            if dt:
                return _normalize_dt(dt)

    # <time datetime="...">
    time_tag = soup.find("time")
    if time_tag and time_tag.get("datetime"):
        dt = _parse_date_str(time_tag.get("datetime"))
        if dt:
            return _normalize_dt(dt)

    # JSON-LD NewsArticle
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
                    return _normalize_dt(dt)

    # URL fallback
    if url:
        match = URL_DATE_RE.search(url)
        if match:
            try:
                dt = datetime.strptime("-".join(match.groups()), "%Y-%m-%d")
                return dt
            except Exception:
                pass

    return None


def split_date_time(dt: datetime) -> tuple[str, str | None]:
    """Return date and time strings (YYYY-MM-DD, HH:MM)."""
    date_str = dt.strftime("%Y-%m-%d")
    time_str = dt.strftime("%H:%M") if dt.time() else None
    return date_str, time_str
