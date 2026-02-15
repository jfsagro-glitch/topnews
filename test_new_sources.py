"""Test new sources configuration"""
import asyncio
import sys
import os
sys.path.insert(0, '.')

# Set dummy tokens to avoid config validation errors
os.environ['BOT_TOKEN'] = 'test_token'
os.environ['APP_ENV'] = 'sandbox'
os.environ['TELEGRAM_CHANNEL_ID'] = '-1001234567890'
os.environ['REDIS_URL'] = 'redis://localhost:6379'
os.environ['DEEPSEEK_API_KEY'] = 'test_key'

from config.railway_config import SOURCES_CONFIG, CATEGORIES

def test_config():
    print("=" * 50)
    print("CATEGORIES:")
    print("=" * 50)
    for key, value in CATEGORIES.items():
        print(f"  {key}: {value}")
    
    print("\n" + "=" * 50)
    print("NEW SOURCES CONFIGURATION:")
    print("=" * 50)
    
    # World Premium
    print("\n🌍 World Premium (Reuters, AP, FT, Politico):")
    world_premium = SOURCES_CONFIG.get('world_premium', {})
    print(f"  Category: {world_premium.get('category')}")
    print(f"  Timeout: {world_premium.get('timeout')}s")
    print(f"  Retry: {world_premium.get('retry')}")
    print(f"  Sources ({len(world_premium.get('sources', []))} total):")
    for src in world_premium.get('sources', []):
        print(f"    - {src}")
    
    # Tech/AI/Crypto
    print("\n💻 Tech/AI/Crypto (TechCrunch, The Verge, CoinDesk, Wired):")
    tech = SOURCES_CONFIG.get('tech_ai_crypto', {})
    print(f"  Category: {tech.get('category')}")
    print(f"  Timeout: {tech.get('timeout')}s")
    print(f"  Retry: {tech.get('retry')}")
    print(f"  AI Hashtags Level: {tech.get('ai_hashtags_level')}")
    print(f"  Entity Extraction: {tech.get('enable_entity_extraction')}")
    print(f"  Priority Keywords: {', '.join(tech.get('priority_keywords', []))}")
    print(f"  Sources ({len(tech.get('sources', []))} total):")
    for src in tech.get('sources', []):
        print(f"    - {src}")
    
    # Finance/Markets
    print("\n📊 Finance/Markets (Trading Economics, Bloomberg):")
    finance = SOURCES_CONFIG.get('finance_markets', {})
    print(f"  Category: {finance.get('category')}")
    print(f"  Timeout: {finance.get('timeout')}s")
    print(f"  Retry: {finance.get('retry')}")
    print(f"  Summary Only: {finance.get('summary_only')}")
    print(f"  AI Summary Min Chars: {finance.get('ai_summary_min_chars')}")
    print(f"  Sources ({len(finance.get('sources', []))} total):")
    for src in finance.get('sources', []):
        print(f"    - {src}")
    
    # Russia
    print("\n🇷🇺 Russia (updated with Meduza):")
    russia = SOURCES_CONFIG.get('russia', {})
    print(f"  Category: {russia.get('category')}")
    print(f"  Strong Markers: {', '.join(russia.get('strong_markers', []))}")
    meduza = [s for s in russia.get('sources', []) if 'meduza' in s.lower()]
    print(f"  Meduza added: {'✓' if meduza else '✗'}")
    if meduza:
        print(f"    - {meduza[0]}")
    
    # Twitter RSSHub
    print("\n🐦 Twitter RSSHub (Elon Musk, Pavel Durov, Donald Trump):")
    twitter = SOURCES_CONFIG.get('twitter_rsshub', {})
    print(f"  Category: {twitter.get('category')}")
    print(f"  Source Type: {twitter.get('src_type')}")
    print(f"  Min Likes: {twitter.get('min_likes')}")
    print(f"  Min Retweets: {twitter.get('min_retweets')}")
    print(f"  Ignore Replies: {twitter.get('ignore_replies')}")
    print(f"  Sources ({len(twitter.get('sources', []))} total):")
    for src in twitter.get('sources', []):
        print(f"    - {src}")
    
    print("\n" + "=" * 50)
    print("Total source groups:", len(SOURCES_CONFIG))
    print("=" * 50)

if __name__ == '__main__':
    test_config()
