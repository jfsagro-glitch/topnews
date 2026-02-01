"""
Инициализация БД для Railway
Запускается перед основным приложением
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db.database import NewsDatabase
from utils.logger import setup_logger

logger = setup_logger()

def init_database():
    """Инициализирует БД если её ещё нет"""
    try:
        logger.info("Initializing database for Railway...")
        
        # Создаем директории если нужны
        os.makedirs('db', exist_ok=True)
        os.makedirs('logs', exist_ok=True)
        
        # Инициализируем БД
        db = NewsDatabase()
        
        logger.info("✅ Database initialized successfully")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to initialize database: {e}", exc_info=True)
        return False

if __name__ == '__main__':
    success = init_database()
    sys.exit(0 if success else 1)
