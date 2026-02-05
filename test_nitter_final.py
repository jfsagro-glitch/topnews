"""
Финальный тест - проверка альтернативных Nitter инстансов и форматов
"""
import asyncio
import feedparser
from net.http_client import get_http_client

async def test_all_nitter_alternatives():
    http_client = await get_http_client()
    
    # Альтернативные инстансы + разные форматы URL
    test_configs = [
        # Формат 1: /username/rss
        ('nitter.poast.org', 'elonmusk', '/rss'),
        ('nitter.privacy.com.de', 'elonmusk', '/rss'),
        ('nitter.hu', 'elonmusk', '/rss'),
        ('nitter.privacydev.net', 'elonmusk', '/rss'),
        ('nitter.pw', 'elonmusk', '/rss'),
        
        # Формат 2: /username/with_replies (sometimes has RSS)
        ('nitter.net', 'elonmusk', '/with_replies/rss'),
        
        # Формат 3: прямой RSS endpoint
        ('nitter.it', 'elonmusk', '/rss'),
        ('nitter.cz', 'elonmusk', '/rss'),
    ]
    
    print("=" * 70)
    print("ФИНАЛЬНЫЙ ТЕСТ NITTER RSS")
    print("=" * 70)
    print(f"Проверяем {len(test_configs)} конфигураций...\n")
    
    working_configs = []
    
    for instance, username, path_suffix in test_configs:
        rss_url = f"https://{instance}/{username}{path_suffix}"
        
        try:
            resp = await http_client.get(rss_url, retries=1)
            
            if resp.status_code == 200:
                content = resp.text
                
                # Проверяем RSS
                is_rss = '<rss' in content.lower() or '<feed' in content.lower()
                has_items = '<item>' in content or '<entry>' in content
                
                if is_rss and has_items:
                    feed = feedparser.parse(content)
                    entries = len(feed.entries) if hasattr(feed, 'entries') else 0
                    
                    if entries > 0:
                        print(f"✅ {instance} - {entries} постов")
                        print(f"   URL: {rss_url}")
                        working_configs.append((instance, username, path_suffix, entries))
                    else:
                        print(f"⚠️  {instance} - RSS без записей")
                else:
                    print(f"❌ {instance} - HTML вместо RSS ({len(content)} bytes)")
            else:
                print(f"❌ {instance} - HTTP {resp.status_code}")
                
        except Exception as e:
            error_msg = str(e)[:40]
            print(f"❌ {instance} - {type(e).__name__}: {error_msg}")
    
    print("\n" + "=" * 70)
    print("РЕЗУЛЬТАТЫ")
    print("=" * 70)
    
    if working_configs:
        print(f"✅ Найдено работающих инстансов: {len(working_configs)}\n")
        for instance, username, path, entries in working_configs:
            print(f"   • {instance} - {entries} постов")
        
        print("\n💡 РЕКОМЕНДАЦИЯ:")
        print("   Можно включить X через Nitter с fallback между инстансами")
        print("   НО: публичные инстансы нестабильны, могут умереть в любой момент")
    else:
        print("❌ Ни один Nitter инстанс не работает")
        print("\n💡 РЕКОМЕНДАЦИЯ:")
        print("   1. Оставить X аккаунты ОТКЛЮЧЕННЫМИ")
        print("   2. ИЛИ хостить свой Nitter инстанс")
        print("   3. ИЛИ использовать платное API X/Twitter")

if __name__ == '__main__':
    asyncio.run(test_all_nitter_alternatives())
