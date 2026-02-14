import asyncio

from utils.hashtags_taxonomy import build_hashtags


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_hashtags_moscow_kremlin():
    tags = _run(build_hashtags(
        title="Москва, Кремль объявил новые меры",
        text="Кремль сообщил о решениях правительства",
        language="ru",
    ))
    assert "#Россия" in tags
    assert "#ЦФО" in tags
    assert "#Москва" in tags


def test_hashtags_world_politics():
    tags = _run(build_hashtags(
        title="White House and US Congress discuss budget",
        text="Leaders meet in Washington",
        language="en",
    ))
    assert "#Мир" in tags
    assert "#Политика" in tags
    assert "#Россия" not in tags


def test_hashtags_crypto_world():
    tags = _run(build_hashtags(
        title="CryptoQuant: bitcoin breaks new high",
        text="Market reacts to ETF inflows",
        language="en",
    ))
    assert "#Мир" in tags
    assert "#Технологии_медиа" in tags or "#Экономика" in tags
    assert "#Россия" not in tags"""Tests for strict hashtag taxonomy: hierarchy, no #Новости, dedup."""
from utils.hashtags_taxonomy import TagPack, build_ordered_hashtags, validate_allowlist, make_allowlist


def test_world_only_two_tags():
    allow = make_allowlist()
    tp = TagPack(g0="#Мир", g1="#ЦФО", g2="#Москва", g3="#Москва", r0="#Общество")
    tp = validate_allowlist(tp, allow)
    assert build_ordered_hashtags(tp) == ["#Мир", "#Общество"]


def test_moscow_no_duplicate():
    allow = make_allowlist()
    tp = TagPack(g0="#Россия", g1="#ЦФО", g2="#Москва", g3="#Москва", r0="#Общество")
    tp = validate_allowlist(tp, allow)
    tags = build_ordered_hashtags(tp)
    assert tags.count("#Москва") == 1


def test_never_news_tag():
    allow = make_allowlist()
    tp = TagPack(g0="#Россия", g1="#ЦФО", g2="#Москва", g3="#Москва", r0="#Новости")
    tp = validate_allowlist(tp, allow)
    tags = build_ordered_hashtags(tp)
    assert "#Новости" not in tags
    assert tp.r0 == "#Общество"
