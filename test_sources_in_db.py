"""
Финальный тест источников в БД
"""
from bot import NewsBot
from db.database import NewsDatabase

def test_sources_in_db():
    print("=" * 70)
    print("ТЕСТ ИСТОЧНИКОВ В БД")
    print("=" * 70)
    
    # Создаем бот (это инициализирует источники)
    bot = NewsBot()
    
    # Получаем все источники из БД
    sources = bot.db.list_sources()
    
    print(f"\n✅ Всего источников в БД: {len(sources)}")
    
    # Фильтруем дополнительные источники
    expected_sources = {
        'news.yahoo.com': 'Yahoo News',
        'ruptlyalert': '@ruptlyalert',
        'tass_agency': '@tass_agency',
        'rian_ru': '@rian_ru',
        'mod_russia': '@mod_russia (Telegram)',
    }
    
    print(f"\n🔍 Проверка дополнительных источников:")
    found_count = 0
    for src in sources:
        code = src.get('code', '')
        title = src.get('title', '')
        
        # Проверяем Yahoo и Telegram каналы из дополнительных
        if code in expected_sources:
            print(f"  ✅ {title} (код: {code})")
            found_count += 1
    
    print(f"\n📊 Итого найдено: {found_count}/{len(expected_sources)}")
    
    # Покажем какие есть
    print(f"\n📋 ВСЕ источники в БД:")
    for src in sorted(sources, key=lambda x: x.get('title', '')):
        print(f"  - {src.get('title', 'N/A')} (код: {src.get('code', 'N/A')})")
    
    print("\n" + "=" * 70)
    if found_count == len(expected_sources):
        print("✅ ВСЕ ДОПОЛНИТЕЛЬНЫЕ ИСТОЧНИКИ ДОБАВЛЕНЫ!")
    else:
        print(f"⚠️ Не все источники добавлены (найдено {found_count} из {len(expected_sources)})")
    print("=" * 70)

if __name__ == '__main__':
    test_sources_in_db()
