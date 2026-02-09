"""Helpers to compact long text inputs for LLM calls."""
from __future__ import annotations

import re
from typing import Literal

from utils.text_cleaner import clean_html, truncate_text


CompactStrategy = Literal["start_mid_end", "start_only"]


def compact_text(text: str, max_chars: int, strategy: CompactStrategy = "start_mid_end") -> str:
    if not text:
        return ""

    cleaned = clean_html(text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return ""

    if len(cleaned) <= max_chars:
        return cleaned

    if strategy == "start_mid_end":
        chunk = max(1, max_chars // 3)
        head = cleaned[:chunk]
        tail = cleaned[-chunk:]
        middle_start = max(0, (len(cleaned) // 2) - (chunk // 2))
        middle = cleaned[middle_start:middle_start + chunk]
        joined = f"{head}\n...\n{middle}\n...\n{tail}"
        return truncate_text(joined, max_length=max_chars)

    return truncate_text(cleaned, max_length=max_chars)
