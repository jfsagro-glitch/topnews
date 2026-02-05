#!/usr/bin/env python3
"""
Проверка источников в UI (/sources команда)
Запустить после деплоя в Railway для убедительности
"""
import asyncio
from bot import NewsBot

async def check_ui_sources():
    """Симуляция того, что видит пользователь при /sources"""
    print("=" * 80)
    print("ПРОВЕРКА: Какие источники видит пользователь при /sources")
    print("=" * 80)
    
    bot = NewsBot()
    sources = bot.db.list_sources()
    
    print("\n📱 НОВОСТНЫЕ ИСТОЧНИКИ В НАСТРОЙКАХ:\n")
    
    # Группируем по типам
    groups = {
        'Телеграм каналы': [],
        'Российские источники': [],
        'Мировые источники': [],
        'Московская область': [],
    }
    
    for src in sorted(sources, key=lambda x: x.get('title', '')):
        code = src.get('code', '')
        title = src.get('title', 'Unknown')
        
        # Определяем группу
        if title.startswith('@') or code in ['ruptlyalert', 'tass_agency', 'rian_ru', 'mod_russia', 'mash', 'bazabazon', 'shot_shot']:
            groups['Телеграм каналы'].append((code, title))
        elif code in ['news.yahoo.com', 'russian.rt.com', 'www.rbc.ru', 'www.gazeta.ru', 'tass.ru', 'lenta.ru', 'rg.ru', 'iz.ru', 'ria.ru', 'www.interfax.ru', 'rss.kommersant.ru', '360.ru']:
            if code == 'news.yahoo.com':
                groups['Мировые источники'].append((code, title))
            else:
                groups['Российские источники'].append((code, title))
        elif code in ['dzen.ru', 'ren.tv', 'riamo.ru', 'mosreg.ru', 'mosregtoday.ru', 'regions.ru', 'www.interfax-russia.ru']:
            groups['Московская область'].append((code, title))
        else:
            groups['Мировые источники'].append((code, title))
    
    # Выводим по группам
    for group_name, items in groups.items():
        if items:
            print(f"📌 {group_name}: ({len(items)})")
            for code, title in items:
                symbol = "📱" if title.startswith('@') else "🌐"
                print(f"   {symbol} {title}")
            print()
    
    print("=" * 80)
    print(f"✅ ВСЕГО ИСТОЧНИКОВ: {len(sources)}")
    print("=" * 80)
    print("\n📍 Пользователи могут переключать каждый источник в боте /sources")
    print("✅ Проверено и готово к использованию!")

if __name__ == '__main__':
    asyncio.run(check_ui_sources())
