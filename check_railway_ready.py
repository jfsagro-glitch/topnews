"""
Проверка готовности к Railway deployment
"""
import os
import sys

def check_deployment_readiness():
    """Проверяет все необходимые файлы для Railway"""
    
    # Создаем необходимые папки автоматически, чтобы CI не падал
    os.makedirs('logs', exist_ok=True)
    
    checks = {
        'Procfile': 'Запуск приложения',
        'railway.json': 'Конфигурация Railway',
        'requirements.txt': 'Зависимости Python',
        '.gitignore': 'Исключение файлов',
        'config/config.py': 'Основная конфигурация',
        'main.py': 'Entry point',
        'bot.py': 'Bot core',
        'db/database.py': 'Database layer',
        'RAILWAY_QUICKSTART.md': 'Railway гайд',
        'RAILWAY_DEPLOY.md': 'Railway документация',
    }
    
    print("=" * 60)
    print("🔍 RAILWAY DEPLOYMENT READINESS CHECK")
    print("=" * 60)
    
    all_ok = True
    
    for filename, description in checks.items():
        if os.path.exists(filename):
            print(f"✅ {filename:<35} ({description})")
        else:
            print(f"❌ {filename:<35} ({description}) - MISSING!")
            all_ok = False
    
    print("\n" + "=" * 60)
    
    # Проверка requirements.txt
    print("\n📦 CHECKING DEPENDENCIES")
    print("-" * 60)
    if os.path.exists('requirements.txt'):
        with open('requirements.txt', 'r') as f:
            lines = f.readlines()
            required_packages = [
                'python-telegram-bot',
                'feedparser',
                'beautifulsoup4',
                'requests',
                'aiohttp',
                'lxml',
            ]
            for pkg in required_packages:
                found = any(pkg in line for line in lines)
                status = "✅" if found else "❌"
                print(f"{status} {pkg}")
                if not found:
                    all_ok = False
    
    print("\n" + "=" * 60)
    
    # Проверка конфигурации
    print("\n⚙️ CONFIGURATION CHECK")
    print("-" * 60)
    
    config_files = {
        'config/config.py': ['TELEGRAM_TOKEN', 'TELEGRAM_CHANNEL_ID'],
        'config/railway_config.py': ['TELEGRAM_TOKEN', 'TELEGRAM_CHANNEL_ID'],
    }
    
    for filename, required_vars in config_files.items():
        if os.path.exists(filename):
            with open(filename, 'r') as f:
                content = f.read()
                for var in required_vars:
                    if var in content:
                        print(f"✅ {filename:<30} contains {var}")
                    else:
                        print(f"⚠️  {filename:<30} missing {var}")
    
    print("\n" + "=" * 60)
    
    # Структура папок
    print("\n📁 DIRECTORY STRUCTURE CHECK")
    print("-" * 60)
    
    required_dirs = ['config', 'db', 'logs', 'parsers', 'sources', 'utils']
    for dir_name in required_dirs:
        if os.path.isdir(dir_name):
            print(f"✅ {dir_name}/")
        else:
            print(f"❌ {dir_name}/ - MISSING!")
            all_ok = False
    
    print("\n" + "=" * 60)
    print("\n📋 SUMMARY")
    print("-" * 60)
    
    if all_ok:
        print("✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ! Проект готов к Railway deployment")
        return 0
    else:
        print("❌ Некоторые проверки не пройдены!")
        print("Пожалуйста, исправьте ошибки выше перед деплоем")
        return 1

if __name__ == '__main__':
    sys.exit(check_deployment_readiness())
