"""
Расширенный тест Nitter инстансов
"""
import asyncio
from net.http_client import get_http_client

async def test_nitter_extended():
    client = await get_http_client()
    
    # Более полный список публичных Nitter инстансов
    nitter_instances = [
        'nitter.net',
        'nitter.privacydev.net',
        'nitter.poast.org',
        'nitter.cz',
        'nitter.it',
        'nitter.unixfox.eu',
        'nitter.domain.glass',
        'nitter.lucabased.xyz',
    ]
    
    test_username = 'elonmusk'
    
    print("=" * 70)
    print(f"ТЕСТ NITTER ИНСТАНСОВ для @{test_username}")
    print("=" * 70)
    
    working = []
    
    for instance in nitter_instances:
        # Try both /rss and without /rss
        for path_format in [f'/{test_username}/rss', f'/{test_username}']:
            url = f'https://{instance}{path_format}'
            print(f"\n🔍 {instance}{path_format}")
            try:
                resp = await client.get(url, retries=1)
                if resp.status_code == 200:
                    is_xml = '<?xml' in resp.text[:200]
                    is_rss = '<rss' in resp.text[:500]
                    is_html = '<html' in resp.text[:500].lower()
                    
                    print(f"  ✅ 200 OK | XML:{is_xml} RSS:{is_rss} HTML:{is_html} | {len(resp.text)} bytes")
                    
                    if is_rss or (is_xml and not is_html):
                        print(f"  ✅✅ RSS FEED НАЙДЕН!")
                        working.append((instance, path_format))
                        break
                else:
                    print(f"  ❌ {resp.status_code}")
            except Exception as e:
                error_msg = str(e)[:80]
                print(f"  ❌ {error_msg}")
        
        if working and working[-1][0] == instance:
            break  # Found working instance, stop
    
    print("\n" + "=" * 70)
    if working:
        print(f"✅ РАБОЧИЕ ИНСТАНСЫ:")
        for inst, path in working:
            print(f"  - https://{inst}{path}")
            print(f"    Формат: https://{inst}/{{username}}/rss")
        return working[0]
    else:
        print("❌ Ни один Nitter инстанс не работает")
        return None

if __name__ == '__main__':
    asyncio.run(test_nitter_extended())
