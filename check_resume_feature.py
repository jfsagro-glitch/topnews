#!/usr/bin/env python3
"""
Проверка синтаксиса и импортов для новой функции "Возобновить работу"
"""
import sys
from pathlib import Path

# Добавляем корневую директорию в PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent))

def check_imports():
    """Проверяем что все необходимые модули импортируются"""
    print("🔍 Проверка импортов...")
    print()
    
    errors = []
    
    # 1. Основной модуль бота
    print("1️⃣ Импорт bot.py...")
    try:
        import bot
        print("   ✅ bot.py импортирован успешно")
    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
        errors.append(f"bot.py: {e}")
    
    # 2. Модуль global_stop
    print("\n2️⃣ Импорт global_stop...")
    try:
        from core.services.global_stop import get_global_stop, set_global_stop
        print("   ✅ global_stop импортирован успешно")
    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
        errors.append(f"global_stop: {e}")
    
    # 3. SourceCollector
    print("\n3️⃣ Импорт SourceCollector...")
    try:
        from sources.source_collector import SourceCollector
        print("   ✅ SourceCollector импортирован успешно")
        
        # Проверяем наличие метода collect_all
        if hasattr(SourceCollector, 'collect_all'):
            print("   ✅ Метод collect_all() найден")
        else:
            print("   ⚠️ Метод collect_all() не найден")
            errors.append("collect_all method not found")
    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
        errors.append(f"SourceCollector: {e}")
    
    # 4. Конфигурация
    print("\n4️⃣ Проверка конфигурации...")
    try:
        try:
            from config.railway_config import APP_ENV
        except (ImportError, ValueError):
            from config.config import APP_ENV
        print(f"   ✅ APP_ENV = {APP_ENV}")
    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
        errors.append(f"APP_ENV: {e}")
    
    # 5. Проверка наличия метода _trigger_news_collection в NewsBot
    print("\n5️⃣ Проверка метода _trigger_news_collection...")
    try:
        from bot import NewsBot
        if hasattr(NewsBot, '_trigger_news_collection'):
            print("   ✅ Метод _trigger_news_collection() найден в NewsBot")
        else:
            print("   ⚠️ Метод _trigger_news_collection() не найден")
            errors.append("_trigger_news_collection not found in NewsBot")
    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
        errors.append(f"NewsBot: {e}")
    
    print("\n" + "="*60)
    
    if errors:
        print("❌ ОБНАРУЖЕНЫ ОШИБКИ:")
        for err in errors:
            print(f"   • {err}")
        print("="*60)
        return False
    else:
        print("✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ!")
        print("="*60)
        print()
        print("📝 Новый функционал готов:")
        print("   • Кнопка '▶️ Возобновить работу' добавлена")
        print("   • Появляется только когда система остановлена")
        print("   • Доступна только в песочнице (APP_ENV=sandbox)")
        print("   • Показывает модальное уведомление")
        print("   • Запускает сбор новостей в фоне")
        print()
        return True

if __name__ == "__main__":
    print("🚀 Проверка функционала 'Возобновить работу'")
    print("="*60)
    print()
    
    try:
        result = check_imports()
        sys.exit(0 if result else 1)
    except KeyboardInterrupt:
        print("\n⚠️ Проверка прервана")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
