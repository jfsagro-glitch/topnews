"""
Адаптация main.py для Railway deployment
Поддерживает как локальный запуск, так и Railway
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
    print(f"⚠️ Railway config not available or incomplete: {e}")
    print("Falling back to local .env configuration...")
    from config.config import TELEGRAM_TOKEN, TELEGRAM_CHANNEL_ID

from utils.logger import setup_logger
from bot import NewsBot

# Настраиваем логирование
logger = setup_logger()


async def main():
    """Главная функция"""
    logger.info("=" * 50)
    logger.info("Telegram News Aggregation Bot Starting on Railway")
    logger.info("=" * 50)
    logger.info(f"Telegram Channel ID: {TELEGRAM_CHANNEL_ID}")
    
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
