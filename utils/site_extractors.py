"""Site-specific extractors for high-priority sources."""
from __future__ import annotations

from bs4 import BeautifulSoup


def _extract_by_selectors(html: str, selectors: list[str]) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    for selector in selectors:
        block = soup.select_one(selector)
        if not block:
            continue
        paragraphs = [p.get_text(" ", strip=True) for p in block.find_all("p")]
        paragraphs = [p for p in paragraphs if len(p) > 40]
        if paragraphs:
            return "\n".join(paragraphs[:6])
    return None


def extract_lenta(html: str) -> str | None:
    selectors = [
        "div[itemprop='articleBody']",
        "div.topic-body__content",
        "div.topic-body",
        "article",
    ]
    return _extract_by_selectors(html, selectors)


def extract_ria(html: str) -> str | None:
    selectors = [
        "div.article__text",
        "div[itemprop='articleBody']",
        "div.article__body",
        "article",
    ]
    return _extract_by_selectors(html, selectors)
