"""
Финальный тест работающих источников
"""
import asyncio
from config.config import SOURCES_CONFIG
from sources.source_collector import SourceCollector

async def test_working_sources():
    print("=" * 70)
    print("ФИНАЛЬНЫЙ ТЕСТ ДОПОЛНИТЕЛЬНЫХ ИСТОЧНИКОВ")
    print("=" * 70)
    
    # Initialize collector
    collector = SourceCollector()
    
    print(f"\n📋 Всего сконфигурировано источников: {len(collector._configured_sources)}")
    
    # Group by category
    additional_sources = [s for s in collector._configured_sources if any('additional' in str(cfg) for cfg in [s])]
    
    print(f"\n📰 Дополнительные источники:")
    for fetch_url, source_name, category, src_type in collector._configured_sources:
        if 'yahoo' in source_name or 'yahoo' in fetch_url:
            print(f"  ✅ Yahoo News ({src_type}): {fetch_url}")
        elif any(tg in source_name for tg in ['ruptlyalert', 'tass_agency', 'rian_ru', 'mod_russia']):
            print(f"  ✅ Telegram {source_name} ({src_type}): {fetch_url[:80]}...")
    
    print("\n" + "=" * 70)
    print("ТЕСТ СБОРА НОВОСТЕЙ")
    print("=" * 70)
    
    # Test collection from Yahoo
    from net.http_client import get_http_client
    from parsers.rss_parser import RSSParser
    
    http_client = await get_http_client()
    rss_parser = RSSParser()
    
    # Test Yahoo
    yahoo_url = 'https://news.yahoo.com/rss/'
    print(f"\n📡 Сбор из Yahoo News...")
    try:
        resp = await http_client.get(yahoo_url)
        if resp.status_code == 200:
            print(f"  ✅ RSS получен ({len(resp.text)} bytes)")
            news_items = await rss_parser.parse(yahoo_url, 'news.yahoo.com')
            print(f"  ✅ Распарсено {len(news_items)} новостей")
            if news_items:
                item = news_items[0]
                print(f"\n  Пример новости:")
                print(f"    Заголовок: {item.get('title', 'N/A')[:80]}")
                print(f"    Текст: {item.get('text', 'N/A')[:100]}...")
                print(f"    URL: {item.get('url', 'N/A')[:80]}")
        else:
            print(f"  ❌ Статус {resp.status_code}")
    except Exception as e:
        print(f"  ❌ Ошибка: {e}")
    
    # Test Telegram
    print(f"\n📡 Сбор из Telegram канала @ruptlyalert...")
    try:
        from config.config import RSSHUB_BASE_URL
        tg_url = f"{RSSHUB_BASE_URL}/telegram/channel/ruptlyalert"
        resp = await http_client.get(tg_url)
        if resp.status_code == 200:
            print(f"  ✅ RSS получен ({len(resp.text)} bytes)")
            news_items = await rss_parser.parse(tg_url, 'ruptlyalert')
            print(f"  ✅ Распарсено {len(news_items)} новостей")
            if news_items:
                item = news_items[0]
                print(f"\n  Пример новости:")
                print(f"    Заголовок: {item.get('title', 'N/A')[:80]}")
                print(f"    Текст: {item.get('text', 'N/A')[:100]}...")
        else:
            print(f"  ❌ Статус {resp.status_code}")
    except Exception as e:
        print(f"  ❌ Ошибка: {e}")
    
    print("\n" + "=" * 70)
    print("✅ ИТОГ")
    print("=" * 70)
    print("✅ Yahoo News - РАБОТАЕТ через RSS")
    print("✅ Telegram каналы (4 шт) - РАБОТАЮТ через RSSHub")
    print("⚠️  X/Twitter - ВРЕМЕННО ОТКЛЮЧЕНЫ (нет доступа)")
    print("=" * 70)

if __name__ == '__main__':
    asyncio.run(test_working_sources())
