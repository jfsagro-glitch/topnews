"""
Основной Telegram бот для публикации новостей
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    ContextTypes, ConversationHandler
)
from telegram.constants import ParseMode
import asyncio
from config.config import TELEGRAM_TOKEN, TELEGRAM_CHANNEL_ID, CHECK_INTERVAL_SECONDS
from db.database import NewsDatabase
from utils.text_cleaner import format_telegram_message
from sources.source_collector import SourceCollector

logger = logging.getLogger(__name__)


class NewsBot:
    """Основной класс Telegram бота"""
    
    def __init__(self):
        self.application = None
        self.db = NewsDatabase()
        self.collector = SourceCollector(db=self.db)
        self.is_running = True
        self.is_paused = False
        self.collection_lock = asyncio.Lock()  # Prevent concurrent collection cycles
        
        # Cache for recently published news (for COPY button)
        self.news_cache = {}  # news_id -> {'title', 'text', 'source', 'url'}
    
    def create_application(self) -> Application:
        """Создает и конфигурирует Telegram Application"""
        
        self.application = Application.builder().token(TELEGRAM_TOKEN).build()
        
        # Регистрируем обработчики команд
        self.application.add_handler(CommandHandler("start", self.cmd_start))
        self.application.add_handler(CommandHandler("help", self.cmd_help))
        self.application.add_handler(CommandHandler("sync", self.cmd_sync))
        self.application.add_handler(CommandHandler("status", self.cmd_status))
        self.application.add_handler(CommandHandler("pause", self.cmd_pause))
        self.application.add_handler(CommandHandler("resume", self.cmd_resume))
        
        # Обработчик inline кнопок
        self.application.add_handler(CallbackQueryHandler(self.button_callback))
        
        logger.info("Application created successfully")
        return self.application

    # Persistent reply keyboard for chats (anchored at bottom)
    REPLY_KEYBOARD = ReplyKeyboardMarkup(
        [['/sync', '/status', '/pause', '/resume']], resize_keyboard=True
    )
    
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /start"""
        await update.message.reply_text(
            "👋 Добро пожаловать в News Aggregator Bot!\n\n"
            "Используйте /help для списка команд",
            reply_markup=self.REPLY_KEYBOARD
        )
    
    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /help"""
        help_text = (
            "📚 Доступные команды:\n\n"
            "/sync - Принудительно запустить сбор новостей\n"
            "/status - Показать статус бота и статистику\n"
            "/pause - Приостановить автоматический сбор\n"
            "/resume - Возобновить автоматический сбор\n"
            "/help - Показать эту справку\n\n"
            "Бот автоматически проверяет новости каждые 2 минуты"
        )
        await update.message.reply_text(help_text, reply_markup=self.REPLY_KEYBOARD)
    
    async def cmd_sync(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /sync - принудительный сбор новостей"""
        await update.message.reply_text("🔄 Начинаю сбор новостей...")
        
        try:
            count = await self.collect_and_publish()
            await update.message.reply_text(f"✅ Собрано и опубликовано {count} новостей")
        except Exception as e:
            logger.error(f"Error in sync: {e}")
            await update.message.reply_text(f"❌ Ошибка при сборе: {e}")
    
    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /status"""
        stats = self.db.get_stats()
        status_text = (
            f"📊 Статус бота:\n\n"
            f"Статус: {'⏸️ PAUSED' if self.is_paused else '✅ RUNNING'}\n"
            f"Всего опубликовано: {stats['total']}\n"
            f"За сегодня: {stats['today']}\n"
            f"Интервал проверки: {CHECK_INTERVAL_SECONDS} сек"
        )
        await update.message.reply_text(status_text)
    
    async def cmd_pause(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /pause"""
        self.is_paused = True
        await update.message.reply_text("⏸️ Сбор новостей приостановлен")
    
    async def cmd_resume(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /resume"""
        self.is_paused = False
        await update.message.reply_text("▶️ Сбор новостей возобновлен")
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик нажатия на кнопку"""
        query = update.callback_query
        
        if query.data.startswith("copy_"):
            # Копирование новости
            news_id = int(query.data.replace("copy_", ""))
            
            # Получаем новость из кэша
            news = self.news_cache.get(news_id)
            if not news:
                await query.answer("❌ Кэш истёк", show_alert=False)
                return
            
            # Формируем полный текст без форматирования (для легкого копирования)
            full_text = f"{news['title']}\n\n{news['text']}\n\n{news['source']}\n{news['url']}"
            
            try:
                # Отправляем полный текст в ДМ БЕЗ уведомления (скрытно)
                await context.bot.send_message(
                    chat_id=query.from_user.id,
                    text=full_text,
                    disable_web_page_preview=True,
                    disable_notification=True  # Отправляем тихо
                )
                # Только уведомление, исходное сообщение не редактируем (остается в канале)
                await query.answer("✅ Скопировано в буфер обмена", show_alert=False)
            except Exception as e:
                logger.error(f"Error sending COPY text: {e}")
                await query.answer(f"❌ Ошибка: {type(e).__name__}", show_alert=False)
    
    async def collect_and_publish(self) -> int:
        """
        Собирает новости и публикует их
        Возвращает количество опубликованных новостей
        """
        if self.is_paused:
            logger.info("Bot is paused, skipping collection")
            return 0
        
        # Prevent concurrent collection cycles
        if self.collection_lock.locked():
            logger.info("Collection already in progress, skipping")
            return 0
        
        async with self.collection_lock:
            return await self._do_collect_and_publish()
    
    async def _do_collect_and_publish(self) -> int:
        """
        Internal method: performs the actual collection and publishing
        """
        try:
            # Собираем новости
            logger.info("Starting news collection...")
            news_items = await self.collector.collect_all()
            
            published_count = 0
            
            # Публикуем каждую новость
            for news in news_items:
                # Попытка атомарно зарегистрировать новость в БД
                inserted = self.db.add_news(
                    url=news['url'],
                    title=news.get('title', ''),
                    source=news.get('source', ''),
                    category=news.get('category', '')
                )

                if not inserted:
                    logger.debug(f"Skipping duplicate: {news.get('url')}")
                    continue

                # Формируем сообщение
                category_emoji = self._get_category_emoji(news.get('category', 'russia'))
                message = format_telegram_message(
                    title=news.get('title', 'No title'),
                    text=news.get('text', ''),
                    source_name=news.get('source', 'Unknown'),
                    source_url=news.get('url', ''),
                    category=category_emoji
                )
                
                # Добавляем URL в конце сообщения
                if message and news.get('url'):
                    message += f"\n[читать далее]({news.get('url')})"
                
                # Сохраняем в кэш для COPY кнопки
                self.news_cache[published_count] = {
                    'title': news.get('title', 'No title'),
                    'text': news.get('text', '')[:2000],  # Ограничиваем до 2000 символов
                    'source': news.get('source', 'Unknown'),
                    'url': news.get('url', '')
                }

                # Создаем кнопку COPY
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("📋 COPY", callback_data="copy_" + str(published_count))]
                ])

                try:
                    # Debug: логируем без реального токена/URL
                    logger.debug(f"Sending message (chat_id hidden)")
                    # Публикуем в канал
                    await self.application.bot.send_message(
                        chat_id=TELEGRAM_CHANNEL_ID,
                        text=message,
                        parse_mode=ParseMode.MARKDOWN,
                        reply_markup=keyboard,
                        disable_web_page_preview=True
                    )

                    published_count += 1
                    logger.info(f"Published: {news['title'][:50]}")

                    # Небольшая задержка между публикациями
                    await asyncio.sleep(1)

                except Exception as e:
                    logger.error(f"Error publishing news: {type(e).__name__} (URL hidden)")
                    # Откатываем запись в БД, чтобы можно было попытаться снова
                    try:
                        self.db.remove_news_by_url(news['url'])
                    except Exception:
                        pass
            
            logger.info(f"Collection complete. Published {published_count} new items")
            return published_count
        
        except Exception as e:
            logger.error(f"Error in collect_and_publish: {e}")
            return 0
    
    def _get_category_emoji(self, category: str) -> str:
        """Возвращает категорию с эмодзи"""
        categories = {
            'world': '🌍 Мир',
            'russia': '🇷🇺 Россия',
            'moscow_region': '🏛️ Подмосковье',
        }
        return categories.get(category, 'Новости')
    
    async def run_periodic_collection(self):
        """Запускает периодический сбор новостей"""
        logger.info("Starting periodic news collection")
        
        while self.is_running:
            try:
                if not self.is_paused:
                    await self.collect_and_publish()
                
                # Ждем перед следующей проверкой
                await asyncio.sleep(CHECK_INTERVAL_SECONDS)
            
            except Exception as e:
                logger.error(f"Error in periodic collection: {e}")
                await asyncio.sleep(CHECK_INTERVAL_SECONDS)
    
    async def start(self):
        """Запускает бота"""
        logger.info("Starting bot...")
        
        # Создаем приложение
        self.create_application()
        
        # Запускаем периодический сбор в фоне
        collection_task = asyncio.create_task(self.run_periodic_collection())
        
        # Запускаем приложение
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()
        
        logger.info("Bot started successfully")
        
        try:
            await asyncio.Event().wait()  # Ждем завершения
        except KeyboardInterrupt:
            logger.info("Received interrupt signal")
        finally:
            self.is_running = False
            collection_task.cancel()
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()
