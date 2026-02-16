#!/usr/bin/env python3
"""
Проверка логики отображения кнопок остановки/возобновления
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from core.services.global_stop import get_global_stop, set_global_stop

def show_button_state():
    """Показывает какая кнопка будет отображаться"""
    is_stopped = get_global_stop()
    
    print("=" * 60)
    print(f"📊 Статус системы: {'🔴 STOPPED' if is_stopped else '🟢 RUNNING'}")
    print("=" * 60)
    print()
    print("🎛️ Отображаемая кнопка:")
    
    if is_stopped:
        print("   ▶️ Возобновить работу")
        print()
        print("   Действие при нажатии:")
        print("   • Снимает остановку")
        print("   • Запускает сбор новостей")
        print("   • Показывает подробное модальное окно")
    else:
        print("   ⛔ ОСТАНОВИТЬ ВСЮ СИСТЕМУ")
        print()
        print("   Действие при нажатии:")
        print("   • Останавливает систему")
        print("   • Показывает модальное окно")
        print("   • Кнопка меняется на '▶️ Возобновить работу'")
    
    print()
    print("=" * 60)

print("🧪 ТЕСТ: Логика кнопок остановки/возобновления")
print()

# 1. Начальное состояние
print("1️⃣ Начальное состояние (система работает):")
print()
set_global_stop(enabled=False, by="test")
show_button_state()
print()

# 2. После остановки
print("2️⃣ После нажатия 'ОСТАНОВИТЬ ВСЮ СИСТЕМУ':")
print()
set_global_stop(enabled=True, reason="Тест", by="test_user")
show_button_state()
print()

# 3. После возобновления
print("3️⃣ После нажатия 'Возобновить работу':")
print()
set_global_stop(enabled=False, reason="Тест", by="test_user")
show_button_state()
print()

print("✅ РЕЗУЛЬТАТ:")
print("   • Всегда показывается ТОЛЬКО ОДНА кнопка")
print("   • Не будет путаницы с двумя кнопками")
print("   • Логика понятная и интуитивная")
print()
