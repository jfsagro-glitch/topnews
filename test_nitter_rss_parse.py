"""
Тест парсинга RSS из Nitter
"""
import asyncio
import feedparser
from net.http_client import get_http_client

async def test_nitter_rss_parsing():
    http_client = await get_http_client()
    
    # Инстансы, которые вернули 200 OK
    working_instances = [
        'nitter.it',
        'nitter.cz',
        'nitter.net',
    ]
    
    test_accounts = [
        'elonmusk',
        'realDonaldTrump',
        'MedvedevRussia',
    ]
    
    print("=" * 60)
    print("ТЕСТ ПАРСИНГА RSS ИЗ NITTER")
    print("=" * 60)
    
    for instance in working_instances:
        print(f"\n📡 Тестирую {instance}...")
        
        for account in test_accounts:
            rss_url = f"https://{instance}/{account}/rss"
            
            try:
                resp = await http_client.get(rss_url, retries=2)
                
                if resp.status_code == 200:
                    content = resp.text
                    
                    # Проверяем, это RSS или HTML
                    is_rss = '<rss' in content.lower() or '<feed' in content.lower()
                    has_items = '<item>' in content or '<entry>' in content
                    
                    print(f"  @{account}: ", end="")
                    
                    if is_rss and has_items:
                        # Пробуем распарсить
                        feed = feedparser.parse(content)
                        entries = len(feed.entries) if hasattr(feed, 'entries') else 0
                        
                        if entries > 0:
                            print(f"✅ {entries} твитов")
                            # Показать первый твит
                            first = feed.entries[0]
                            title = first.get('title', '')[:60]
                            print(f"    Пример: {title}...")
                        else:
                            print(f"⚠️ RSS валидный, но 0 записей")
                    else:
                        print(f"❌ Не RSS (HTML страница, {len(content)} bytes)")
                else:
                    print(f"  @{account}: ❌ HTTP {resp.status_code}")
                    
            except Exception as e:
                print(f"  @{account}: ❌ {type(e).__name__}: {str(e)[:50]}")
    
    print("\n" + "=" * 60)
    print("РЕКОМЕНДАЦИИ:")
    print("=" * 60)
    print("Если нашлись работающие инстансы - добавим поддержку с fallback")
    print("Если нет - оставим X аккаунты отключенными")

if __name__ == '__main__':
    asyncio.run(test_nitter_rss_parsing())
