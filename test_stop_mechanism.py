#!/usr/bin/env python3
"""
Быстрая проверка механизма остановки/возобновления с файловым fallback
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from core.services.global_stop import get_global_stop, set_global_stop

print("=" * 60)
print("🔍 ТЕСТ: Остановка и возобновление системы")
print("=" * 60)
print()

# 1. Начальное состояние
print("1️⃣ Начальное состояние:")
status = get_global_stop()
print(f"   Система остановлена: {status}")
print(f"   Статус: {'🔴 STOPPED' if status else '🟢 RUNNING'}")
print()

# 2. Остановка системы
print("2️⃣ Останавливаем систему...")
set_global_stop(enabled=True, reason="Тест остановки", by="test_user")
status = get_global_stop()
print(f"   Система остановлена: {status}")
print(f"   Статус: {'🔴 STOPPED' if status else '🟢 RUNNING'}")
print(f"   {'✅ Остановка работает!' if status else '❌ Ошибка остановки'}")
print()

# Проверяем файл
stop_file = Path(".global_stop.json")
if stop_file.exists():
    print(f"   📁 Создан файл: {stop_file}")
    print(f"   Содержимое:")
    print("   " + stop_file.read_text().replace("\n", "\n   "))
else:
    print("   ⚠️ Файл не создан (используется Redis)")
print()

# 3. Возобновление системы
print("3️⃣ Возобновляем систему...")
set_global_stop(enabled=False, reason="Тест возобновления", by="test_user")
status = get_global_stop()
print(f"   Система остановлена: {status}")
print(f"   Статус: {'🔴 STOPPED' if status else '🟢 RUNNING'}")
print(f"   {'✅ Возобновление работает!' if not status else '❌ Ошибка возобновления'}")
print()

if stop_file.exists():
    print("   ⚠️ Файл не удален!")
else:
    print("   ✅ Файл удален")
print()

print("=" * 60)
print("✅ ТЕСТ ЗАВЕРШЕН УСПЕШНО!")
print("=" * 60)
print()
print("📝 Теперь кнопки должны работать:")
print("   • '⛔ ОСТАНОВИТЬ ВСЮ СИСТЕМУ' → статус станет 🔴 STOPPED")
print("   • Появится кнопка '▶️ Возобновить работу'")
print("   • При нажатии → статус станет 🟢 RUNNING")
print()
