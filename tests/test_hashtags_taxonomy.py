"""Tests for hashtag taxonomy: hierarchy, Russia detection, underscore normalization."""

import asyncio
from utils.hashtags import build_hashtags


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
        title="Госдума РФ приняла закон",
        lead_text="В Кремле прошло заседание в Москве",
        source="tass",
        language="ru",
    ))

    assert tags[0] == "#Россия", f"Expected #Россия first, got {tags}"
    assert "#ЦФО" in tags, f"Expected #ЦФО in {tags}"
    assert "#Москва" in tags, f"Expected #Москва in {tags}"
    assert tags[-1] == "#Политика", f"Expected #Политика rubric in {tags}"


def test_hashtags_world_politics():
    """Europe/US politics should be tagged #Мир with politics rubric."""
    tags = _run(build_hashtags(
        title="Европа обсуждает санкции",
        lead_text="ЕС и Германия согласовали пакет мер",
        source="dw",
        language="ru",
    ))

    assert tags[0] == "#Мир", f"Expected #Мир first, got {tags}"
    assert "#Россия" not in tags, f"Should NOT have #Россия in {tags}"
    assert tags[-1] in ("#Политика", "#Общество"), f"Unexpected rubric in {tags}"


def test_hashtags_crypto_world():
    """Cryptocurrency news should be #Мир with tech/econ rubric, not #Россия."""
    tags = _run(build_hashtags(
        title="CryptoQuant: bitcoin breaks new high",
        lead_text="US investors react to ETF inflows and global adoption",
        source="coindesk",
        language="en",
    ))

    assert tags[0] == "#Мир", f"Expected #Мир first, got {tags}"
    has_tech_or_econ = "#Технологии_медиа" in tags or "#Экономика" in tags
    assert has_tech_or_econ, f"Expected tech or econ rubric in {tags}"
    assert "#Россия" not in tags, f"Should NOT have #Россия in {tags}"


def test_underscore_in_rubric():
    """Verify rubric tags use underscore format."""
    tags = _run(build_hashtags(
        title="Новые технологии в медиа",
        lead_text="Искусственный интеллект и журналистика",
        source="habr",
        language="ru",
    ))

    assert "#Технологии_медиа" in tags, f"Expected #Технологии_медиа in {tags}"


def test_hierarchy_ordering():
    """Verify G0 appears first in the list (geographic-first hierarchy)."""
    tags = _run(build_hashtags(
        title="Москва",
        lead_text="Кремль и правительство",
        source="ria",
        language="ru",
    ))
    
    # G0 (#Россия or #Мир) should be first
    assert len(tags) > 0, "Should have some tags"
    assert tags[0] in ["#Россия", "#Мир"], f"First tag should be G0, got {tags[0]}"


def test_hashtags_brics_world():
    """BRICS mention without strong Russia markers should stay #Мир."""
    tags = _run(build_hashtags(
        title="ТАСС: У БРИКС обсуждают реформу валютных расчетов",
        lead_text="Страны БРИКС рассматривают новые механизмы",
        source="tass",
        language="ru",
    ))

    assert tags[0] == "#Мир", f"Expected #Мир first, got {tags}"
    assert "#Россия" not in tags, f"Should NOT have #Россия in {tags}"
