import asyncio

from utils.hashtags_taxonomy import build_hashtags


def _run(coro):
    return asyncio.run(coro)


def test_no_moscow_duplicate():
    tags = _run(build_hashtags("Москва", "Москва, Москва", language="ru"))
    assert tags.count("#Москва") == 1


def test_world_only_two_tags():
    tags = _run(build_hashtags("США ввели санкции", "США объявили новые меры", language="ru"))
    assert tags[0] == "#Мир"
    assert "#Россия" not in tags
    assert len(tags) == 2
    assert tags[1] == "#Общество"


def test_no_hash_novosti():
    tags = _run(build_hashtags("Новости дня", "Экономика и общество", language="ru"))
    assert "#Новости" not in tags


def test_r0_always_present():
    tags = _run(build_hashtags("Нейтральный заголовок", "", language="ru"))
    assert "#Общество" in tags
