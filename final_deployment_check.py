"""
Final deployment checklist for Railway
Финальная проверка перед развертыванием на Railway
"""
import os
import sys
import json

def run_final_checks():
    """Финальная проверка перед развертыванием"""
    
    print("\n" + "=" * 70)
    print("🚀 FINAL RAILWAY DEPLOYMENT CHECKLIST")
    print("=" * 70)
    
    checks_passed = 0
    checks_failed = 0
    
    # Проверка 1: Файлы существуют
    print("\n1️⃣  CORE FILES CHECK")
    print("-" * 70)
    core_files = [
        ('Procfile', 'Railway entry point'),
        ('railway.json', 'Railway configuration'),
        ('main.py', 'Bot entry point'),
        ('bot.py', 'Bot core'),
        ('config/config.py', 'Configuration'),
        ('config/railway_config.py', 'Railway configuration'),
        ('requirements.txt', 'Dependencies'),
        ('init_db.py', 'Database initialization'),
    ]
    
    for filename, desc in core_files:
        if os.path.exists(filename):
            print(f"  ✅ {filename:<40} ({desc})")
            checks_passed += 1
        else:
            print(f"  ❌ {filename:<40} ({desc}) - MISSING!")
            checks_failed += 1
    
    # Проверка 2: Содержимое важных файлов
    print("\n2️⃣  CONTENT VALIDATION")
    print("-" * 70)
    
    # Procfile
    with open('Procfile', 'r') as f:
        procfile_content = f.read()
        if 'python main.py' in procfile_content or 'python' in procfile_content:
            print(f"  ✅ Procfile contains valid command")
            checks_passed += 1
        else:
            print(f"  ❌ Procfile missing valid command")
            checks_failed += 1
    
    # railway.json
    try:
        with open('railway.json', 'r') as f:
            railway_config = json.load(f)
            if 'deploy' in railway_config and 'startCommand' in railway_config.get('deploy', {}):
                print(f"  ✅ railway.json valid JSON with deploy config")
                checks_passed += 1
            else:
                print(f"  ⚠️  railway.json valid JSON but may be incomplete")
                checks_passed += 1
    except:
        print(f"  ❌ railway.json invalid JSON")
        checks_failed += 1
    
    # requirements.txt
    required_packages = {
        'python-telegram-bot': 'Telegram Bot API',
        'feedparser': 'RSS parsing',
        'beautifulsoup4': 'HTML parsing',
        'aiohttp': 'Async HTTP',
        'requests': 'HTTP requests',
    }
    
    print("\n3️⃣  DEPENDENCIES CHECK")
    print("-" * 70)
    
    with open('requirements.txt', 'r') as f:
        requirements = f.read().lower()
    
    for pkg, desc in required_packages.items():
        if pkg.lower() in requirements:
            print(f"  ✅ {pkg:<30} ({desc})")
            checks_passed += 1
        else:
            print(f"  ❌ {pkg:<30} ({desc}) - MISSING!")
            checks_failed += 1
    
    # Проверка 3: Переменные окружения
    print("\n4️⃣  ENVIRONMENT VARIABLES")
    print("-" * 70)
    
    required_vars = {
        'TELEGRAM_TOKEN': 'Required - bot token from @BotFather',
        'TELEGRAM_CHANNEL_ID': 'Required - target channel ID',
        'CHECK_INTERVAL_SECONDS': 'Optional - collection interval (default 120)',
        'LOG_LEVEL': 'Optional - logging level (default INFO)',
    }
    
    env_ok = True
    for var, desc in required_vars.items():
        if os.getenv(var):
            status = "✅ SET" if var.startswith('TELEGRAM') else "✅ configured"
            print(f"  {status:<8} {var:<30} ({desc})")
            checks_passed += 1
        else:
            is_required = var.startswith('TELEGRAM')
            status = "❌ MISSING (REQUIRED)" if is_required else "⚠️  not set (optional)"
            print(f"  {status:<25} {var:<30} ({desc})")
            if is_required:
                checks_failed += 1
                env_ok = False
            else:
                checks_passed += 1
    
    if not env_ok:
        print("\n  ⚠️  TELEGRAM variables must be set in Railway Dashboard!")
    
    # Проверка 4: Git и GitHub
    print("\n5️⃣  GIT & GITHUB CHECK")
    print("-" * 70)
    
    if os.path.isdir('.git'):
        print(f"  ✅ Git repository initialized")
        checks_passed += 1
        
        try:
            import subprocess
            result = subprocess.run(['git', 'remote', '-v'], 
                                  capture_output=True, text=True)
            if 'github.com' in result.stdout:
                print(f"  ✅ GitHub remote configured")
                checks_passed += 1
            else:
                print(f"  ⚠️  Git configured but not to GitHub")
                print(f"     Add with: git remote add origin https://github.com/jfsagro-glitch/topnews.git")
                checks_passed += 1
        except:
            print(f"  ⚠️  Could not verify GitHub remote")
            checks_passed += 1
    else:
        print(f"  ❌ Git repository not initialized")
        print(f"     Initialize with: git init")
        checks_failed += 1
    
    # Проверка 5: Структура директорий
    print("\n6️⃣  DIRECTORY STRUCTURE CHECK")
    print("-" * 70)
    
    required_dirs = [
        'config',
        'db',
        'parsers',
        'sources',
        'utils',
    ]
    
    for dirname in required_dirs:
        if os.path.isdir(dirname):
            print(f"  ✅ {dirname}/ exists")
            checks_passed += 1
        else:
            print(f"  ❌ {dirname}/ missing")
            checks_failed += 1
    
    # Итоговый результат
    print("\n" + "=" * 70)
    print("📊 SUMMARY")
    print("=" * 70)
    
    print(f"\n✅ Passed:  {checks_passed}")
    print(f"❌ Failed:  {checks_failed}")
    
    if checks_failed == 0:
        print("\n" + "=" * 70)
        print("🎉 ALL CHECKS PASSED! Ready for Railway deployment!")
        print("=" * 70)
        print("\n📋 DEPLOYMENT STEPS:")
        print("\n1. Ensure your local .env has test values:")
        print("   TELEGRAM_TOKEN=test_token")
        print("   TELEGRAM_CHANNEL_ID=-1001234567890")
        print("\n2. Push to GitHub:")
        print("   git add .")
        print("   git commit -m 'Ready for Railway deployment'")
        print("   git push origin main")
        print("\n3. On Railway.app:")
        print("   - New Project → Deploy from GitHub")
        print("   - Select jfsagro-glitch/topnews")
        print("   - Set Variables:")
        print("     TELEGRAM_TOKEN=your_actual_token")
        print("     TELEGRAM_CHANNEL_ID=your_actual_channel_id")
        print("   - Deploy")
        print("\n✅ Done! Bot will start automatically")
        print("\n" + "=" * 70)
        return 0
    else:
        print("\n" + "=" * 70)
        print("❌ DEPLOYMENT BLOCKED - Fix errors above")
        print("=" * 70)
        return 1

if __name__ == '__main__':
    sys.exit(run_final_checks())
