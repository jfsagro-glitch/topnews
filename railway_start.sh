#!/bin/bash
# Railway startup script
# Этот скрипт запускается Railway при развертывании

set -e  # Exit on any error

echo "🚀 Starting TopNews Bot on Railway..."

# Создаем необходимые директории
mkdir -p db logs

# Инициализируем БД если нужно
echo "📦 Initializing database..."
python -c "
from db.database import NewsDatabase
db = NewsDatabase()
print('✅ Database ready')
"

# Запускаем бота
echo "🤖 Starting bot..."
python main.py
