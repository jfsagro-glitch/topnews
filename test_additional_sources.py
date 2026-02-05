"""
Тест дополнительных источников (Yahoo, Telegram, X)
"""
import asyncio
import sys
from config.config import RSSHUB_BASE_URL

async def test_sources():
    try:
        from net.http_client import get_http_client
        
        print("=" * 60)
        print("ТЕСТ ДОПОЛНИТЕЛЬНЫХ ИСТОЧНИКОВ")
        print("=" * 60)
        
        # Test Yahoo News RSS
        yahoo_url = 'https://news.yahoo.com/rss/'
        print(f"\n✅ Yahoo News: {yahoo_url}")
        
        # Test Telegram channels via RSSHub
        telegram_channels = [
            'ruptlyalert',
            'tass_agency',
            'rian_ru',
            'mod_russia'
        ]
        print(f"\n✅ Telegram каналы через RSSHub ({RSSHUB_BASE_URL}):")
        for channel in telegram_channels:
            url = f"{RSSHUB_BASE_URL}/telegram/channel/{channel}"
            print(f"  - {channel}: {url}")
        
        # Test X/Twitter accounts via RSSHub
        x_accounts = [
            'kadmitriev',
            'MedvedevRussia',
            'realDonaldTrump',
            'elonmusk',
            'durov',
            'JDVance'
        ]
        print(f"\n✅ X/Twitter аккаунты через RSSHub ({RSSHUB_BASE_URL}):")
        for username in x_accounts:
            url = f"{RSSHUB_BASE_URL}/twitter/user/{username}"
            print(f"  - @{username}: {url}")
        
        # Try to fetch one example from each type
        print("\n" + "=" * 60)
        print("ПРОВЕРКА ДОСТУПНОСТИ (примеры)")
        print("=" * 60)
        
        http_client = await get_http_client()
        
        # Test Yahoo
        print(f"\n📡 Тест Yahoo News RSS...")
        try:
            resp = await http_client.get(yahoo_url)
            if resp.status_code == 200:
                print(f"✅ Yahoo News доступен (200 OK, {len(resp.text)} bytes)")
            else:
                print(f"❌ Yahoo News вернул статус {resp.status_code}")
        except Exception as e:
            print(f"❌ Yahoo News ошибка: {e}")
        
        # Test Telegram example
        tg_url = f"{RSSHUB_BASE_URL}/telegram/channel/ruptlyalert"
        print(f"\n📡 Тест Telegram канала ruptlyalert...")
        try:
            resp = await http_client.get(tg_url)
            if resp.status_code == 200:
                print(f"✅ Telegram @ruptlyalert доступен (200 OK, {len(resp.text)} bytes)")
            else:
                print(f"❌ Telegram @ruptlyalert вернул статус {resp.status_code}")
        except Exception as e:
            print(f"❌ Telegram @ruptlyalert ошибка: {e}")
        
        # Test X/Twitter example
        x_url = f"{RSSHUB_BASE_URL}/twitter/user/elonmusk"
        print(f"\n📡 Тест X/Twitter аккаунта @elonmusk...")
        try:
            resp = await http_client.get(x_url)
            if resp.status_code == 200:
                print(f"✅ X @elonmusk доступен (200 OK, {len(resp.text)} bytes)")
            else:
                print(f"❌ X @elonmusk вернул статус {resp.status_code}")
        except Exception as e:
            print(f"❌ X @elonmusk ошибка: {e}")
        
        print("\n" + "=" * 60)
        print("✅ Тест завершен")
        print("=" * 60)
        
    except Exception as e:
        print(f"❌ Ошибка теста: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(test_sources())
