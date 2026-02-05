"""
Тест Yahoo RSS и альтернативных решений для X
"""
import asyncio
from net.http_client import get_http_client

async def test_yahoo_and_x():
    client = await get_http_client()
    
    print("=" * 60)
    print("ТЕСТ YAHOO NEWS RSS")
    print("=" * 60)
    
    # Test Yahoo RSS
    yahoo_urls = [
        'https://news.yahoo.com/rss/',
        'https://www.yahoo.com/news/rss',
        'https://news.yahoo.com/rss/world',
    ]
    
    for url in yahoo_urls:
        print(f"\n🔍 Пробую: {url}")
        try:
            resp = await client.get(url, retries=1)
            if resp.status_code == 200:
                has_rss = '<?xml' in resp.text[:200] or '<rss' in resp.text[:200]
                print(f"  ✅ Статус: {resp.status_code}, RSS: {has_rss}, Размер: {len(resp.text)} bytes")
                if has_rss:
                    print(f"  ✅ РАБОТАЕТ!")
                    break
            else:
                print(f"  ❌ Статус: {resp.status_code}")
        except Exception as e:
            print(f"  ❌ Ошибка: {e}")
    
    print("\n" + "=" * 60)
    print("ТЕСТ NITTER (альтернатива X/Twitter)")
    print("=" * 60)
    
    # Test Nitter instances
    nitter_instances = [
        'nitter.poast.org',
        'nitter.privacydev.net',
        'nitter.net',
    ]
    
    test_username = 'elonmusk'
    
    for instance in nitter_instances:
        url = f'https://{instance}/{test_username}/rss'
        print(f"\n🔍 Пробую Nitter: {instance}")
        print(f"  URL: {url}")
        try:
            resp = await client.get(url, retries=1)
            if resp.status_code == 200:
                has_rss = '<?xml' in resp.text[:200] or '<rss' in resp.text[:200]
                print(f"  ✅ Статус: {resp.status_code}, RSS: {has_rss}")
                if has_rss:
                    print(f"  ✅ РАБОТАЕТ! Используем {instance}")
                    print(f"  Формат: https://{instance}/{{username}}/rss")
                    return instance
            else:
                print(f"  ❌ Статус: {resp.status_code}")
        except Exception as e:
            print(f"  ❌ Ошибка: {str(e)[:100]}")
    
    print("\n" + "=" * 60)
    return None

if __name__ == '__main__':
    asyncio.run(test_yahoo_and_x())
