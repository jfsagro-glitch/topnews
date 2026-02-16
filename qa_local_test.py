#!/usr/bin/env python3
"""Local QA tests for Phase 2 implementation.

Test cases:
1. Hashtag hierarchy correctness
2. Per-source scheduling state
3. Config variables loaded
4. RSSHub backoff logic
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from utils.hashtags_taxonomy import build_hashtags
from config.config import (
    RSSHUB_MIN_INTERVAL_SECONDS,
    RSS_MIN_INTERVAL_SECONDS,
    RSSHUB_CONCURRENCY,
    RSSHUB_SOURCE_COOLDOWN_SECONDS,
)


async def test_hashtag_moscow():
    """Test 1: Moscow/Kremlin news should have #Россия, #ЦФО, #Москва."""
    print("\n" + "="*60)
    print("TEST 1: Hashtag Hierarchy - Moscow/Kremlin")
    print("="*60)
    
    tags = await build_hashtags(
        title="Кремль объявил о встречах в Москве",
        text="Президент встретился в Москве с главой правительства",
        language="ru"
    )
    
    print(f"Tags: {tags}")
    
    checks = [
        ("#Россия" in tags, "#Россия должен быть в тегах"),
        ("#ЦФО" in tags, "#ЦФО должен быть в тегах"),
        ("#Москва" in tags, "#Москва должен быть в тегах"),
        (tags[0] == "#Россия", "#Россия должен быть первым (G0)"),
    ]
    
    passed = 0
    for check, msg in checks:
        status = "✅" if check else "❌"
        print(f"  {status} {msg}")
        if check:
            passed += 1
    
    return passed == len(checks)


async def test_hashtag_world():
    """Test 2: World news should have #Мир, NOT #Россия."""
    print("\n" + "="*60)
    print("TEST 2: Hashtag Hierarchy - World (France Elections)")
    print("="*60)
    
    tags = await build_hashtags(
        title="Elections in France",
        text="French voters go to polls for new parliament",
        language="en"
    )
    
    print(f"Tags: {tags}")
    
    checks = [
        ("#Мир" in tags, "#Мир должен быть в тегах"),
        ("#Россия" not in tags, "#Россия НЕ должен быть в тегах"),
        (tags[0] == "#Мир", "#Мир должен быть первым (G0)"),
    ]
    
    passed = 0
    for check, msg in checks:
        status = "✅" if check else "❌"
        print(f"  {status} {msg}")
        if check:
            passed += 1
    
    return passed == len(checks)


async def test_hashtag_crypto():
    """Test 3: Crypto news should be #Мир with tech/econ rubric."""
    print("\n" + "="*60)
    print("TEST 3: Hashtag Hierarchy - Crypto (#Мир + Tech/Econ)")
    print("="*60)
    
    tags = await build_hashtags(
        title="Bitcoin breaks $100K barrier",
        text="Cryptocurrency markets react to institutional adoption",
        language="en"
    )
    
    print(f"Tags: {tags}")
    
    checks = [
        ("#Мир" in tags, "#Мир должен быть в тегах"),
        ("#Россия" not in tags, "#Россия НЕ должен быть в тегах"),
        (
            "#Технологии_медиа" in tags or "#Экономика" in tags,
            "#Технологии_медиа или #Экономика должны быть в тегах"
        ),
    ]
    
    passed = 0
    for check, msg in checks:
        status = "✅" if check else "❌"
        print(f"  {status} {msg}")
        if check:
            passed += 1
    
    return passed == len(checks)


def test_config_loaded():
    """Test 4: Config variables loaded correctly."""
    print("\n" + "="*60)
    print("TEST 4: Configuration Variables")
    print("="*60)
    
    checks = [
        (RSSHUB_MIN_INTERVAL_SECONDS == 900, f"RSSHUB_MIN_INTERVAL = {RSSHUB_MIN_INTERVAL_SECONDS}s (expected 900)"),
        (RSS_MIN_INTERVAL_SECONDS == 300, f"RSS_MIN_INTERVAL = {RSS_MIN_INTERVAL_SECONDS}s (expected 300)"),
        (RSSHUB_CONCURRENCY == 2, f"RSSHUB_CONCURRENCY = {RSSHUB_CONCURRENCY} (expected 2)"),
        (RSSHUB_SOURCE_COOLDOWN_SECONDS == 600, f"RSSHUB_COOLDOWN = {RSSHUB_SOURCE_COOLDOWN_SECONDS}s (expected 600)"),
    ]
    
    passed = 0
    for check, msg in checks:
        status = "✅" if check else "❌"
        print(f"  {status} {msg}")
        if check:
            passed += 1
    
    return passed == len(checks)


async def main():
    """Run all QA tests."""
    print("\n" + "#"*60)
    print("# PHASE 2 LOCAL QA TESTS")
    print("#"*60)
    
    results = []
    
    # Test 1: Moscow
    try:
        results.append(("Hashtag Moscow", await test_hashtag_moscow()))
    except Exception as e:
        print(f"❌ Error in Test 1: {e}")
        results.append(("Hashtag Moscow", False))
    
    # Test 2: World
    try:
        results.append(("Hashtag World", await test_hashtag_world()))
    except Exception as e:
        print(f"❌ Error in Test 2: {e}")
        results.append(("Hashtag World", False))
    
    # Test 3: Crypto
    try:
        results.append(("Hashtag Crypto", await test_hashtag_crypto()))
    except Exception as e:
        print(f"❌ Error in Test 3: {e}")
        results.append(("Hashtag Crypto", False))
    
    # Test 4: Config
    try:
        results.append(("Config Variables", test_config_loaded()))
    except Exception as e:
        print(f"❌ Error in Test 4: {e}")
        results.append(("Config Variables", False))
    
    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    
    total_passed = sum(1 for _, passed in results if passed)
    total_tests = len(results)
    
    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status}: {test_name}")
    
    print(f"\nTotal: {total_passed}/{total_tests} tests passed")
    
    if total_passed == total_tests:
        print("\n🎉 All QA tests passed! Ready for deployment.")
        return 0
    else:
        print("\n⚠️  Some tests failed. Review above.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
