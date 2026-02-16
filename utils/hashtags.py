"""Domain-level hashtag builder facade."""
from __future__ import annotations

from utils.hashtags_taxonomy import build_hashtags as _build_hashtags
from utils.hashtags_taxonomy import build_hashtags_en as _build_hashtags_en


async def build_hashtags(
    title: str,
    lead_text: str,
    source: str | None = None,
    existing_category: str | None = None,
    language: str = "ru",
    ai_client=None,
    level: int = 0,
    ai_call_guard=None,
) -> list[str]:
    """Build ordered, stable hashtags list.

    Args:
        title: News title.
        lead_text: Lead or clean text.
        source: Source identifier (used for chat_id routing).
        existing_category: Optional category hint (not used to force Russia).
        language: Content language.
        ai_client: Optional AI client for taxonomy fallback.
        level: AI hashtags level.
        ai_call_guard: Optional gate callback.
    """
    _ = existing_category  # Keep signature for compatibility and future hints.
    return await _build_hashtags(
        title=title,
        text=lead_text,
        language=language,
        chat_id=source,
        ai_client=ai_client,
        level=level,
        ai_call_guard=ai_call_guard,
    )


def build_hashtags_en(tags_ru: list[str]) -> list[str]:
    """Convert RU hashtags into EN counterparts."""
    return _build_hashtags_en(tags_ru)
