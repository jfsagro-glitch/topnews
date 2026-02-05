"""
Финальная проверка всех источников перед деплоем
"""
from bot import NewsBot
from config.config import SOURCES_CONFIG

def test_all_sources():
    print("=" * 80)
    print("ФИНАЛЬНАЯ ПРОВЕРКА ПЕРЕД ДЕПЛОЕМ")
    print("=" * 80)
    
    # Создаем бот (инициализирует источники)
    print("\n🔧 Инициализирую бот...")
    bot = NewsBot()
    
    # Получаем источники из БД
    sources_in_db = bot.db.list_sources()
    print(f"✅ Загружено источников в БД: {len(sources_in_db)}")
    
    # Получаем источники из конфига
    total_config_sources = 0
    for category, cfg in SOURCES_CONFIG.items():
        count = len(cfg.get('sources', []))
        total_config_sources += count
        print(f"   - Категория '{category}': {count} источников")
    
    print(f"✅ Всего в конфиге: {total_config_sources} источников")
    
    # Проверяем дополнительные источники
    print("\n📡 ДОПОЛНИТЕЛЬНЫЕ ИСТОЧНИКИ:")
    print("-" * 80)
    
    additional_expected = {
        'news.yahoo.com': ('Yahoo News', 'additional'),
        'ruptlyalert': ('@ruptlyalert', 'additional'),
        'tass_agency': ('@tass_agency', 'additional'),
        'rian_ru': ('@rian_ru', 'additional'),
        'mod_russia': ('@mod_russia', 'additional'),
    }
    
    found = {}
    for src in sources_in_db:
        code = src.get('code', '')
        if code in additional_expected:
            found[code] = src
    
    for code, (title, category) in additional_expected.items():
        if code in found:
            src = found[code]
            print(f"✅ {src.get('title')} (код: {code})")
        else:
            print(f"❌ ОТСУТСТВУЕТ: {title} (код: {code})")
    
    print(f"\n✅ Найдено: {len(found)}/{len(additional_expected)}")
    
    # Показываем все остальные источники
    print("\n📰 ОСТАЛЬНЫЕ ИСТОЧНИКИ:")
    print("-" * 80)
    
    other_sources = [s for s in sources_in_db if s.get('code') not in additional_expected]
    for src in sorted(other_sources, key=lambda x: x.get('title', '')):
        print(f"  - {src.get('title')} (код: {src.get('code')})")
    
    print(f"\n✅ Остальных источников: {len(other_sources)}")
    
    # Итоговая статистика
    print("\n" + "=" * 80)
    print("✅ ИТОГОВАЯ СТАТИСТИКА")
    print("=" * 80)
    print(f"📊 Всего источников в БД: {len(sources_in_db)}")
    print(f"📊 Дополнительные источники: {len(found)}/5 ✅" if len(found) == 5 else f"📊 Дополнительные источники: {len(found)}/5 ❌")
    print(f"📊 Остальные источники: {len(other_sources)}")
    
    # Проверяем Telegram каналы
    telegram_sources = [s for s in sources_in_db if s.get('code', '').startswith(('@', 'mash', 'bazabazon', 'shot_shot', 'ruptlyalert', 'tass_agency', 'rian_ru', 'mod_russia'))]
    telegram_count = len([s for s in sources_in_db if '@' in s.get('title', '') or s.get('code') in ['ruptlyalert', 'tass_agency', 'rian_ru', 'mod_russia', 'mash', 'bazabazon', 'shot_shot']])
    print(f"📱 Telegram каналов всего: {telegram_count}")
    
    print("\n" + "=" * 80)
    if len(found) == 5:
        print("✅ ВСЕ ИСТОЧНИКИ ЗАГРУЖЕНЫ! ГОТОВ К ДЕПЛОЮ")
    else:
        print("⚠️ НЕКОТОРЫЕ ИСТОЧНИКИ ОТСУТСТВУЮТ!")
    print("=" * 80)

if __name__ == '__main__':
    test_all_sources()
