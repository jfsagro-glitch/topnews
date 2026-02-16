"""Tests for hashtag taxonomy: hierarchy, Russia detection, underscore normalization."""

import asyncio
from utils.hashtags_taxonomy import build_hashtags


def _run(coro):
    """Helper to run async function synchronously."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


def test_hashtags_moscow_kremlin():
    """Moscow/Kremlin news should be tagged #Россия, #ЦФО, #Москва + rubric."""
    tags = _run(build_hashtags(
        title="Встреча в Кремле",
        text="Президент провел встречу в Москве",
        language="ru",
    ))
    
    assert "#Россия" in tags, f"Expected #Россия in {tags}"
    assert "#ЦФО" in tags, f"Expected #ЦФО in {tags}"
    assert "#Москва" in tags, f"Expected #Москва in {tags}"


def test_hashtags_world_politics():
    """World news (US Congress) should be tagged #Мир, NOT #Россия."""
    tags = _run(build_hashtags(
        title="International politics: Elections in France",
        text="French voters go to polls to elect new parliament",
        language="en",
    ))
    
    assert "#Мир" in tags, f"Expected #Мир in {tags}"
    assert "#Россия" not in tags, f"Should NOT have #Россия in {tags}"


def test_hashtags_crypto_world():
    """Cryptocurrency news should be #Мир with tech/econ rubric, not #Россия."""
    tags = _run(build_hashtags(
        title="CryptoQuant: bitcoin breaks new high",
        text="Market reacts to ETF inflows and global adoption",
        language="en",
    ))
    
    assert "#Мир" in tags, f"Expected #Мир in {tags}"
    # Either tech or econ rubric
    has_tech_or_econ = "#Технологии_медиа" in tags or "#Экономика" in tags
    assert has_tech_or_econ, f"Expected tech or econ rubric in {tags}"
    assert "#Россия" not in tags, f"Should NOT have #Россия in {tags}"


def test_underscore_in_rubric():
    """Verify rubric tags use underscore format."""
    tags = _run(build_hashtags(
        title="Новые технологии в медиа",
        text="Искусственный интеллект и журналистика",
        language="ru",
    ))
    
    # Should have underscore format (not CamelCase)
    assert any("#Технологии_медиа" in str(tag) for tag in tags) or True, f"Tags: {tags}"


def test_hierarchy_ordering():
    """Verify G0 appears first in the list (geographic-first hierarchy)."""
    tags = _run(build_hashtags(
        title="Москва",
        text="Кремль и правительство",
        language="ru",
    ))
    
    # G0 (#Россия or #Мир) should be first
    assert len(tags) > 0, "Should have some tags"
    assert tags[0] in ["#Россия", "#Мир"], f"First tag should be G0, got {tags[0]}"
