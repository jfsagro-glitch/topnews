"""Tests for strict hashtag taxonomy: hierarchy, no #Новости, dedup."""
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
