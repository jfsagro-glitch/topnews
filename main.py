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
    from config.railway_config import (
        BOT_TOKEN,
        BOT_TOKEN_PROD,
        BOT_TOKEN_SANDBOX,
        TELEGRAM_CHANNEL_ID,
        APP_ENV,
        TG_MODE,
        WEBHOOK_BASE_URL,
    )
    print("✅ Using Railway configuration")
except (ValueError, ImportError) as e:
    print("Using local configuration...")
    from config.config import (
        BOT_TOKEN,
        BOT_TOKEN_PROD,
        BOT_TOKEN_SANDBOX,
        TELEGRAM_CHANNEL_ID,
        APP_ENV,
        TG_MODE,
        WEBHOOK_BASE_URL,
    )

from utils.logger import setup_logger
from bot import NewsBot

# Настраиваем логирование
logger = setup_logger()


def validate_bot_token():
    warnings = []

    if APP_ENV == "prod" and BOT_TOKEN_SANDBOX and BOT_TOKEN == BOT_TOKEN_SANDBOX:
        raise RuntimeError("BOT_TOKEN matches BOT_TOKEN_SANDBOX while APP_ENV=prod")
    if APP_ENV == "sandbox" and BOT_TOKEN_PROD and BOT_TOKEN == BOT_TOKEN_PROD:
        raise RuntimeError("BOT_TOKEN matches BOT_TOKEN_PROD while APP_ENV=sandbox")

    if BOT_TOKEN_PROD and BOT_TOKEN_SANDBOX:
        expected = BOT_TOKEN_PROD if APP_ENV == "prod" else BOT_TOKEN_SANDBOX
        if BOT_TOKEN != expected:
            raise RuntimeError(f"BOT_TOKEN does not match expected token for APP_ENV={APP_ENV}")
    else:
        if not BOT_TOKEN_PROD:
            warnings.append("BOT_TOKEN_PROD is not set; token mismatch protection is limited")
        if not BOT_TOKEN_SANDBOX:
            warnings.append("BOT_TOKEN_SANDBOX is not set; token mismatch protection is limited")

    for w in warnings:
        logger.warning(w)


async def main():
    """Главная функция"""
    logger.info("=" * 50)
    logger.info("Telegram News Aggregation Bot Starting")
    logger.info("=" * 50)
    logger.info(f"APP_ENV={APP_ENV} TG_MODE={TG_MODE}")
    if TG_MODE == "webhook" and not WEBHOOK_BASE_URL:
        raise ValueError("WEBHOOK_BASE_URL is required when TG_MODE=webhook")

    validate_bot_token()

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
