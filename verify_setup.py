#!/usr/bin/env python3
"""
Скрипт для проверки правильности установки и конфигурации бота
"""
import os
import sys
from pathlib import Path


def check_environment():
    """Проверяет окружение"""
    print("=" * 60)
    print("🔍 ПРОВЕРКА ОКРУЖЕНИЯ TopNews Bot")
    print("=" * 60)
    
    errors = []
    warnings = []
    
    # 1. Проверка структуры директорий
    print("\n1️⃣  Проверка структуры проекта...")
    required_dirs = ['config', 'db', 'logs', 'parsers', 'sources', 'utils']
    for dir_name in required_dirs:
        if os.path.isdir(dir_name):
            print(f"   ✅ {dir_name}/")
        else:
            errors.append(f"Директория {dir_name}/ не найдена")
    
    # 2. Проверка файлов конфигурации
    print("\n2️⃣  Проверка файлов конфигурации...")
    required_files = [
        'main.py',
        'bot.py',
        'requirements.txt',
        'config/config.py',
        'db/database.py',
        'parsers/rss_parser.py',
        'parsers/html_parser.py',
        'sources/source_collector.py',
        'utils/logger.py',
        'utils/text_cleaner.py',
    ]
    for file_name in required_files:
        if os.path.isfile(file_name):
            print(f"   ✅ {file_name}")
        else:
            errors.append(f"Файл {file_name} не найден")
    
    # 3. Проверка .env
    print("\n3️⃣  Проверка конфигурации (.env)...")
    if os.path.isfile('.env'):
        print("   ✅ .env файл найден")
        with open('.env', 'r') as f:
            env_content = f.read()
            if 'TELEGRAM_TOKEN' in env_content and 'YOUR_BOT_TOKEN' not in env_content:
                print("   ✅ TELEGRAM_TOKEN установлен")
            else:
                errors.append("TELEGRAM_TOKEN не установлен или содержит плейсхолдер")
            
            if 'TELEGRAM_CHANNEL_ID' in env_content:
                print("   ✅ TELEGRAM_CHANNEL_ID установлен")
            else:
                warnings.append("TELEGRAM_CHANNEL_ID не установлен")
    else:
        if os.path.isfile('.env.example'):
            warnings.append(
                ".env файл не найден. Скопируйте .env.example в .env и заполните значения:\n"
                "   cp .env.example .env"
            )
        else:
            errors.append(".env файл не найден и .env.example не существует")
    
    # 4. Проверка зависимостей
    print("\n4️⃣  Проверка установленных пакетов...")
    required_packages = [
        'telegram',
        'feedparser',
        'requests',
        'bs4',
        'aiohttp',
    ]
    
    missing_packages = []
    for package in required_packages:
        try:
            __import__(package)
            print(f"   ✅ {package}")
        except ImportError:
            missing_packages.append(package)
            errors.append(f"Пакет {package} не установлен")
    
    if missing_packages:
        print(f"\n   💡 Чтобы установить: pip install -r requirements.txt")
    
    # 5. Проверка прав доступа
    print("\n5️⃣  Проверка прав доступа...")
    if os.access('logs', os.W_OK):
        print("   ✅ Возможно писать в logs/")
    else:
        warnings.append("Нет прав на запись в logs/")
    
    if os.access('db', os.W_OK):
        print("   ✅ Возможно писать в db/")
    else:
        warnings.append("Нет прав на запись в db/")
    
    # Вывод результатов
    print("\n" + "=" * 60)
    print("📊 РЕЗУЛЬТАТЫ ПРОВЕРКИ")
    print("=" * 60)
    
    if errors:
        print(f"\n❌ Обнаружено {len(errors)} ошибок:")
        for i, error in enumerate(errors, 1):
            print(f"   {i}. {error}")
    else:
        print("\n✅ Ошибок не найдено!")
    
    if warnings:
        print(f"\n⚠️  {len(warnings)} предупреждений:")
        for i, warning in enumerate(warnings, 1):
            print(f"   {i}. {warning}")
    
    print("\n" + "=" * 60)
    
    if errors:
        print("🔴 Статус: ОШИБКИ - исправьте перед запуском")
        return False
    elif warnings:
        print("🟡 Статус: ГОТОВ (требуется конфигурация)")
        return True
    else:
        print("🟢 Статус: ПОЛНОСТЬЮ ГОТОВ К ЗАПУСКУ")
        return True


def print_next_steps():
    """Выводит следующие шаги"""
    print("\n📝 СЛЕДУЮЩИЕ ШАГИ:")
    print("=" * 60)
    print("""
1. Если вы еще не создали бота:
   - Откройте Telegram и напишите @BotFather
   - Создайте нового бота (/newbot)
   - Скопируйте полученный токен

2. Создайте/отредактируйте .env файл:
   cp .env.example .env
   # Отредактируйте .env и заполните:
   # - TELEGRAM_TOKEN (токен от BotFather)
   # - TELEGRAM_CHANNEL_ID (ID канала)

3. Создайте Telegram канал:
   - Создайте новый приватный/публичный канал
   - Добавьте бота в канал как администратора
   - Используйте @userinfobot для получения Channel ID

4. Установите все зависимости:
   pip install -r requirements.txt

5. Запустите бота:
   python main.py

6. Тестируйте команды в Telegram:
   /help - справка
   /sync - сбор новостей
   /status - статус

📖 Дополнительная информация:
   - README.md - основная документация
   - SETUP.md - подробное руководство установки
   - ARCHITECTURE.md - архитектура системы
   - DEVELOPER.md - руководство разработчика
""")
    print("=" * 60)


if __name__ == '__main__':
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    ready = check_environment()
    print_next_steps()
    
    sys.exit(0 if ready else 1)
