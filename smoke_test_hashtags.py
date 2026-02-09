"""Smoke tests for hashtag taxonomy."""
from __future__ import annotations

import asyncio

from utils.hashtags_taxonomy import build_hashtags, get_allowlist


def _allowed_set() -> set[str]:
    allow = get_allowlist()
    all_tags = set()
    for key in ("g0", "g1", "g2", "g3", "r0"):
        all_tags.update(allow.get(key, []))
    return all_tags


async def _run() -> None:
    allow = _allowed_set()

    def assert_allowed(tag_list: list[str]) -> None:
        for tag in tag_list:
            assert tag in allow

    tags = await build_hashtags("В Москве открылся форум", "В Москве прошла встреча.")
    assert tags[0] == "#Россия"
    assert tags[1] == "#ЦФО"
    assert tags[2] == "#Москва"
    assert tags[3].startswith("#")
    assert_allowed(tags)

    tags = await build_hashtags("В Тверской области обновили трассу", "В Тверской области завершили ремонт.")
    assert tags[0] == "#Россия"
    assert tags[1] == "#ЦФО"
    assert tags[2] == "#ТверскаяОбласть"
    assert tags[3] == "#Тверь"
    assert_allowed(tags)

    tags = await build_hashtags("В Берлине прошла конференция", "В Берлине обсудили вопросы безопасности.")
    assert tags[0] == "#Мир"
    assert tags[-1].startswith("#")
    assert_allowed(tags)


if __name__ == "__main__":
    asyncio.run(_run())
    print("HASHTAG SMOKE OK")
