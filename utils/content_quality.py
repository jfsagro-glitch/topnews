"""
Content quality scoring utilities.
"""
from __future__ import annotations

import hashlib
import re
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from typing import Tuple

SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
NOISE_PHRASES = (
    "подпис", "реклам", "telegram", "t.me", "vk", "ok.ru", "youtube",
    "читайте также", "смотрите также", "подробнее", "реклама", "партнер",
    "поделиться", "войти", "зарегистр", "новости партнеров",
    "материалы по теме", "похожие материалы", "нашли опечатку",
    "что думаешь", "комментируй", "подпишись", "главное", "картина дня",
)


def compute_checksum(text: str) -> str:
    """Return sha256 checksum for text."""
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def compute_url_hash(url: str) -> str:
    """Return sha256 checksum for normalized URL."""
    raw = (url or "").strip()
    if not raw:
        return hashlib.sha256(b"").hexdigest()

    parts = urlsplit(raw)
    scheme = (parts.scheme or "").lower()
    netloc = (parts.netloc or "").lower()
    path = parts.path or ""
    query = parts.query or ""
    if query:
        query_pairs = parse_qsl(query, keep_blank_values=True)
        filtered = []
        for key, value in query_pairs:
            key_lower = key.lower()
            if key_lower.startswith("utm_"):
                continue
            if key_lower in {"fbclid", "gclid", "yclid", "mc_cid", "mc_eid"}:
                continue
            filtered.append((key, value))
        query = urlencode(sorted(filtered)) if filtered else ""

    normalized = urlunsplit((scheme, netloc, path, query, ""))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def detect_language(text: str, title: str = "") -> str:
    """Detect language based on Cyrillic vs Latin ratio."""
    sample = f"{title} {text}".strip()
    if not sample:
        return "ru"
    cyr = sum(1 for c in sample if "а" <= c.lower() <= "я" or c.lower() == "ё")
    lat = sum(1 for c in sample if "a" <= c.lower() <= "z")
    if lat > cyr * 1.2:
        return "en"
    return "ru"


def content_quality_score(text: str, title: str = "") -> Tuple[float, dict]:
    """Score content quality from 0.0 to 1.0.

    Heuristics:
    - length and sentence count add score
    - noise phrase ratio and repeated lines reduce score
    """
    raw = (text or "").strip()
    if not raw:
        return 0.0, {"reason": "empty"}

    length = len(raw)
    sentences = [s.strip() for s in SENTENCE_SPLIT_RE.split(raw) if s.strip()]
    sentence_count = len(sentences)

    # Noise ratio based on phrases
    lower = raw.lower()
    noise_hits = sum(1 for p in NOISE_PHRASES if p in lower)
    noise_ratio = min(1.0, noise_hits / max(1, sentence_count))

    # Repetition ratio based on duplicate lines
    lines = [l.strip() for l in raw.splitlines() if l.strip()]
    unique_lines = set(lines)
    repeat_ratio = 0.0
    if lines:
        repeat_ratio = 1.0 - (len(unique_lines) / len(lines))

    # Score components
    length_score = min(1.0, length / 900.0) * 0.5
    sentence_score = min(1.0, sentence_count / 5.0) * 0.3
    penalty = (noise_ratio * 0.1) + (repeat_ratio * 0.1)

    score = max(0.0, min(1.0, length_score + sentence_score - penalty))

    return score, {
        "length": length,
        "sentence_count": sentence_count,
        "noise_ratio": noise_ratio,
        "repeat_ratio": repeat_ratio,
    }


def is_low_quality(score: float, threshold: float = 0.55) -> bool:
    return score < threshold
