"""
Конфигурация логирования
"""
import logging
import os
from config.config import LOG_LEVEL, LOG_FILE


def setup_logger():
    """Настраивает логирование (один раз)"""
    os.makedirs(os.path.dirname(LOG_FILE) or '.', exist_ok=True)
    
    logger = logging.getLogger()
    # Prevent duplicate handlers
    if logger.handlers:
        return logger
    
    logger.setLevel(LOG_LEVEL)
    
    # Формат логов
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Файловый логировщик
    file_handler = logging.FileHandler(LOG_FILE)
    file_handler.setLevel(LOG_LEVEL)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    # Консольный логировщик
    console_handler = logging.StreamHandler()
    console_handler.setLevel(LOG_LEVEL)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    return logger


# Создаем глобальный логировщик
logger = setup_logger()
