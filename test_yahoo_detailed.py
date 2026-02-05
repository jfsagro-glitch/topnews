"""
Детальный тест сбора новостей с Yahoo
"""
import asyncio
from config.config import SOURCES_CONFIG
from sources.source_collector import SourceCollector
from db.database import NewsDatabase

async def test_yahoo_detailed():
    print("=" * 70)
    print("ДЕТАЛЬНЫЙ ТЕСТ YAHOO NEWS")
    print("=" * 70)
    
    # Создаем collector
    db = NewsDatabase()
    collector = SourceCollector(db=db)
    
    # Найдем Yahoo в конфиге
    print("\n📋 Поиск Yahoo в конфиге...")
    yahoo_found = False
    for cat, cfg in SOURCES_CONFIG.items():
        for src in cfg.get('sources', []):
            if 'yahoo' in src.lower():
                print(f"  ✅ Найден в категории '{cat}': {src}")
                yahoo_found = True
    
    if not yahoo_found:
        print("  ❌ Yahoo не найден в конфиге!")
        return
    
    # Проверим, как источник добавляется в SourceCollector
    print(f"\n📡 Источники в SourceCollector (_configured_sources):")
    yahoo_sources = [s for s in collector._configured_sources if 'yahoo' in s[0].lower() or 'yahoo' in s[1].lower()]
    if yahoo_sources:
        for fetch_url, source_name, category, src_type in yahoo_sources:
            print(f"  ✅ {source_name} ({src_type})")
            print(f"     URL: {fetch_url}")
            print(f"     Category: {category}")
    else:
        print("  ❌ Yahoo НЕ ДОБАВЛЕН в _configured_sources!")
        print(f"\n     Все источники ({len(collector._configured_sources)}):")
        for fetch_url, source_name, category, src_type in collector._configured_sources:
            print(f"       - {source_name} ({src_type})")
    
    # Попробуем собрать с Yahoo напрямую
    print(f"\n📊 Попытка сбора новостей...")
    try:
        news = await collector.collect_all()
        
        yahoo_news = [n for n in news if n.get('source', '').lower() == 'news.yahoo.com']
        print(f"  Всего собрано: {len(news)} новостей")
        print(f"  Из Yahoo: {len(yahoo_news)} новостей")
        
        if yahoo_news:
            print(f"\n✅ Примеры новостей с Yahoo:")
            for item in yahoo_news[:3]:
                print(f"\n  📰 {item.get('title', 'N/A')[:80]}")
                print(f"     Source: {item.get('source', 'N/A')}")
                print(f"     Category: {item.get('category', 'N/A')}")
                print(f"     URL: {item.get('url', 'N/A')[:80]}")
        else:
            print(f"\n❌ Новостей с Yahoo не найдено в собранных новостях!")
            print(f"   Источники в результатах: {set(n.get('source') for n in news)}")
            
    except Exception as e:
        print(f"  ❌ Ошибка сбора: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 70)

if __name__ == '__main__':
    asyncio.run(test_yahoo_detailed())
