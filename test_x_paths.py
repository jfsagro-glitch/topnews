"""
Тест различных путей RSSHub для X/Twitter
"""
import asyncio
from net.http_client import get_http_client

async def test_x_paths():
    client = await get_http_client()
    
    username = 'elonmusk'
    paths = [
        f'/twitter/user/{username}',
        f'/x/user/{username}',
        f'/twitter/{username}',
        f'/x/{username}',
    ]
    
    base = 'https://rsshub-production-a367.up.railway.app'
    
    print("Тест различных путей для X/Twitter:")
    print("=" * 60)
    
    for path in paths:
        url = f"{base}{path}"
        print(f"\n🔍 Пробую: {path}")
        try:
            resp = await client.get(url, retries=1)
            if resp.status_code == 200:
                print(f"  ✅ Работает! (200 OK, {len(resp.text)} bytes)")
                # Check if it's RSS
                if '<?xml' in resp.text[:100] or '<rss' in resp.text[:100]:
                    print(f"  📰 RSS feed найден")
                break
            else:
                print(f"  ❌ Статус: {resp.status_code}")
        except Exception as e:
            print(f"  ❌ Ошибка: {e}")
    
    print("\n" + "=" * 60)

if __name__ == '__main__':
    asyncio.run(test_x_paths())
