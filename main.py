"""
Главный точка входа приложения
Поддерживает как локальный запуск, так и Railway deployment
"""
import asyncio
import logging
import sys
import os

# Добавляем текущую директорию в путь
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Пытаемся использовать Railway конфиг, если доступен, иначе обычный
try:
    from config.railway_config import TELEGRAM_TOKEN, TELEGRAM_CHANNEL_ID
    print("✅ Using Railway configuration")
except (ValueError, ImportError) as e:
    print(f"Using local configuration...")
    from config.config import TELEGRAM_TOKEN, TELEGRAM_CHANNEL_ID

from utils.logger import setup_logger
from bot import NewsBot

# Настраиваем логирование
logger = setup_logger()


async def main():
    """Главная функция"""
    logger.info("=" * 50)
    logger.info("Telegram News Aggregation Bot Starting")
    logger.info("=" * 50)
    
    try:
        bot = NewsBot()
        await bot.start()
    
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    asyncio.run(main())
