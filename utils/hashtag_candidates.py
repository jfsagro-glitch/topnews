"""Heuristic hashtag candidate extraction."""
from __future__ import annotations

import re
from collections import Counter

RU_STOPWORDS = {
    "и", "в", "на", "с", "по", "о", "об", "от", "до", "за", "из", "у", "для",
    "как", "это", "что", "то", "бы", "были", "будет", "будут", "уже", "еще",
    "со", "или", "но", "же", "ли", "при", "без", "над", "под", "после",
    "сегодня", "вчера", "заявил", "заявила", "сообщили", "сообщил", "поэтому",
}

EN_STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "there", "their",
    "was", "were", "are", "been", "into", "over", "under", "about", "after",
    "before", "today", "yesterday", "says", "said", "reported", "reports",
}

WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9]+")
RU_ENTITY_RE = re.compile(r"(?:[А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+)*)")
EN_ENTITY_RE = re.compile(r"(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)")


def _normalize_term(term: str) -> str:
    cleaned = re.sub(r"[^A-Za-zА-Яа-яЁё0-9\s]", "", term).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


def _to_hashtag(term: str) -> str:
    cleaned = _normalize_term(term)
    if not cleaned:
        return ""
    return "#" + cleaned.replace(" ", "")


def _extract_entities(text: str, language: str) -> list[str]:
    if not text:
        return []
    regex = RU_ENTITY_RE if language == "ru" else EN_ENTITY_RE
    entities = []
    for match in regex.findall(text):
        cleaned = _normalize_term(match)
        if not cleaned or len(cleaned) < 3:
            continue
        entities.append(cleaned)
    return entities


def _extract_keywords(text: str, language: str) -> Counter:
    if not text:
        return Counter()
    tokens = WORD_RE.findall(text)
    stop = RU_STOPWORDS if language == "ru" else EN_STOPWORDS
    filtered = []
    for token in tokens:
        word = token.lower()
        if word.isdigit() or len(word) < 3 or word in stop:
            continue
        filtered.append(word)
    return Counter(filtered)


def extract_hashtag_candidates(title: str, text: str, language: str = "ru") -> dict:
    """Return candidate hashtags based on heuristics.

    Returns dict with "candidates" list ordered by priority.
    """
    language = (language or "ru").lower()
    combined = f"{title}\n{text}".strip()
    if not combined:
        return {"candidates": []}

    sample_text = combined[:4000]
    entities = _extract_entities(title or "", language)
    if len(entities) < 6:
        entities += _extract_entities(sample_text, language)

    keywords = _extract_keywords(sample_text, language)
    for word in WORD_RE.findall(title or ""):
        if word:
            keywords[word.lower()] += 2

    candidates: list[str] = []
    seen = set()

    for entity in entities:
        tag = _to_hashtag(entity)
        if tag and tag.lower() not in seen:
            candidates.append(tag)
            seen.add(tag.lower())
        if len(candidates) >= 12:
            break

    for keyword, _count in keywords.most_common(20):
        tag = _to_hashtag(keyword)
        if tag and tag.lower() not in seen:
            candidates.append(tag)
            seen.add(tag.lower())
        if len(candidates) >= 20:
            break

    return {"candidates": candidates}
