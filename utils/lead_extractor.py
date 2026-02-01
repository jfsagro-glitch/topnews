"""
Lead extraction utilities for news items.
"""
from __future__ import annotations

import re
from typing import Iterable

from utils.text_cleaner import clean_html, truncate_text

STOP_PHRASES = (
    'подпис', 'реклам', 'telegram', 't.me', 'vk', 'вконтакте', 'ok.ru',
    '©', 'cookie', 'все права', 'читайте также', 'смотрите также', 'подробнее',
    'источник:', 'реклама', 'партнер', 'поделиться', 'войти', 'зарегистр',
    'читать далее', 'читать больше', 'читать полностью', 'подпишитесь',
    'новости партнеров', 'материалы по теме', 'похожие материалы'
)

SENTENCE_SPLIT_RE = re.compile(r'(?<=[.!?])\s+')
URL_RE = re.compile(r'https?://\S+|www\.\S+')
MULTISPACE_RE = re.compile(r'\s+')


def _is_noise_line(line: str, min_len: int) -> bool:
    lower = line.lower()
    if len(line) < min_len and any(p in lower for p in STOP_PHRASES):
        return True
    if any(p in lower for p in STOP_PHRASES) and len(line) < min_len * 2:
        return True
    if lower.startswith(('читать далее', 'подробнее', 'источник:', 'реклама')):
        return True
    return False


def clean_text(text: str) -> str:
    """
    Clean raw text by removing URLs, noise lines and normalizing spaces.
    """
    if not text:
        return ""

    text = URL_RE.sub('', text)
    text = MULTISPACE_RE.sub(' ', text)
    text = text.strip()
    return text


def _extract_candidates_from_text(text: str, min_len: int) -> list[str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    candidates: list[str] = []
    for line in lines:
        if _is_noise_line(line, min_len):
            continue
        line_clean = clean_text(line)
        if len(line_clean) >= min_len:
            candidates.append(line_clean)
    return candidates


def choose_lead(candidates: Iterable[str], max_len: int = 800) -> str:
    """
    Choose the best lead from candidates.
    """
    for candidate in candidates:
        if not candidate:
            continue
        lead = candidate.strip()
        if len(lead) < 40:
            continue
        if any(p in lead.lower() for p in STOP_PHRASES):
            continue
        return truncate_text(lead, max_len)
    return ""


def _first_sentence_from_text(text: str, max_len: int) -> str:
    text = clean_text(text)
    sentences = [s.strip() for s in SENTENCE_SPLIT_RE.split(text) if s.strip()]
    for sentence in sentences:
        if len(sentence) >= 40 and not any(p in sentence.lower() for p in STOP_PHRASES):
            return truncate_text(sentence, max_len)
    return ""


def extract_lead_from_html(html: str, max_len: int = 800) -> str:
    """
    Extract lead from HTML by cleaning and choosing first meaningful paragraph.
    """
    if not html:
        return ""

    text = clean_html(html)
    if not text:
        return ""

    candidates = _extract_candidates_from_text(text, min_len=40)
    lead = choose_lead(candidates, max_len=max_len)
    if lead:
        return lead

    fallback = _first_sentence_from_text(text, max_len=max_len)
    return fallback


def extract_lead_from_rss(entry, max_len: int = 800) -> str:
    """
    Extract lead from RSS entry using summary/description.
    """
    if not entry:
        return ""

    summary = entry.get('summary', '') or entry.get('description', '')
    if not summary:
        return ""

    text = clean_html(summary)
    if not text:
        return ""

    candidates = _extract_candidates_from_text(text, min_len=40)
    lead = choose_lead(candidates, max_len=max_len)
    if lead:
        return lead

    fallback = _first_sentence_from_text(text, max_len=max_len)
    return fallback
