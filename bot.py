"""
Основной Telegram бот для публикации новостей
"""
import logging
import time
from net.deepseek_client import DeepSeekClient
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters,
    ContextTypes, ConversationHandler
)
from telegram.constants import ParseMode
import asyncio
from config.config import TELEGRAM_TOKEN, TELEGRAM_CHANNEL_ID, CHECK_INTERVAL_SECONDS, ADMIN_IDS
from db.database import NewsDatabase
from utils.text_cleaner import format_telegram_message
from sources.source_collector import SourceCollector

logger = logging.getLogger(__name__)


class NewsBot:
    """Основной класс Telegram бота"""
    
    def __init__(self):
        self.application = None
        self.db = NewsDatabase()
        
        # DeepSeek client (initialize early for use in SourceCollector)
        self.deepseek_client = DeepSeekClient()
        
        # AI category verification toggle (can be controlled via button)
        from config.config import AI_CATEGORY_VERIFICATION_ENABLED
        self.ai_verification_enabled = AI_CATEGORY_VERIFICATION_ENABLED
        
        # SourceCollector with optional AI verification
        self.collector = SourceCollector(db=self.db, ai_client=self.deepseek_client, bot=self)
        
        self.is_running = True
        self.is_paused = False
        self.collection_lock = asyncio.Lock()  # Prevent concurrent collection cycles
        
        # Cache for recently published news (for AI button)
        self.news_cache = {}  # news_id -> {'title', 'text', 'source', 'url'}
        
        # Global category filter (None = show all)
        self.category_filter = None  # 'world', 'russia', 'moscow_region', or None
        
        # Rate limiting for AI summarize requests (per user per minute)
        self.user_ai_requests = {}  # {user_id: [timestamp1, timestamp2, ...]}

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
        self.application.add_handler(CommandHandler("filter", self.cmd_filter))
        self.application.add_handler(CommandHandler("sync_deepseek", self.cmd_sync_deepseek))
        self.application.add_handler(CommandHandler("update_stats", self.cmd_update_stats))
        
        # Обработчик текстовых сообщений (эмодзи-кнопки)
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_emoji_buttons))
        
        # Обработчик inline кнопок
        self.application.add_handler(CallbackQueryHandler(self.button_callback))
        
        logger.info("Application created successfully")
        return self.application

    # Persistent reply keyboard for chats (anchored at bottom)
    REPLY_KEYBOARD = ReplyKeyboardMarkup(
        [['🔄', '📊', '🔍', '⏸️', '▶️']], resize_keyboard=True
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
            "/filter - Фильтровать новости по категориям\n"
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
        ai_usage = self.db.get_ai_usage()
        
        # Calculate realistic costs based on token counts
        # DeepSeek pricing: input $0.14/M, output $0.28/M tokens
        # Approximate 60% input, 40% output for text operations
        input_tokens = int(ai_usage['total_tokens'] * 0.6)
        output_tokens = int(ai_usage['total_tokens'] * 0.4)
        input_cost = (input_tokens / 1_000_000.0) * 0.14
        output_cost = (output_tokens / 1_000_000.0) * 0.28
        estimated_cost = input_cost + output_cost
        
        status_text = (
            f"📊 Статус бота:\n\n"
            f"Статус: {'⏸️ PAUSED' if self.is_paused else '✅ RUNNING'}\n"
            f"Всего опубликовано: {stats['total']}\n"
            f"За сегодня: {stats['today']}\n"
            f"Интервал проверки: {CHECK_INTERVAL_SECONDS} сек\n\n"
            f"🧠 ИИ использование (автоматический учет):\n"
            f"Всего запросов: {ai_usage['total_requests']}\n"
            f"Всего токенов: {ai_usage['total_tokens']:,}\n"
            f"Расчетная стоимость: ${estimated_cost:.4f}\n\n"
            f"📝 Пересказы: {ai_usage['summarize_requests']} запр., {ai_usage['summarize_tokens']:,} токенов\n"
            f"🏷️ Категории: {ai_usage['category_requests']} запр., {ai_usage['category_tokens']:,} токенов\n"
            f"✨ Очистка текста: {ai_usage['text_clean_requests']} запр., {ai_usage['text_clean_tokens']:,} токенов"
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
    
    async def cmd_sync_deepseek(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /sync_deepseek - показать текущую статистику и инструкцию"""
        ai_usage = self.db.get_ai_usage()
        
        # Calculate costs
        input_tokens = int(ai_usage['total_tokens'] * 0.6)
        output_tokens = int(ai_usage['total_tokens'] * 0.4)
        input_cost = (input_tokens / 1_000_000.0) * 0.14
        output_cost = (output_tokens / 1_000_000.0) * 0.28
        estimated_cost = input_cost + output_cost
        
        text = (
            f"📊 Текущая статистика в боте:\n\n"
            f"Запросов: {ai_usage['total_requests']}\n"
            f"Токенов: {ai_usage['total_tokens']:,}\n"
            f"Стоимость: ${estimated_cost:.4f}\n\n"
            f"🔄 Для синхронизации с реальными данными DeepSeek:\n\n"
            f"1️⃣ Откройте https://platform.deepseek.com/usage\n"
            f"2️⃣ Посмотрите данные:\n"
            f"   • API requests\n"
            f"   • Tokens\n" 
            f"   • Monthly expenses\n\n"
            f"3️⃣ Отправьте команду:\n"
            f"/update_stats <requests> <tokens> <cost>\n\n"
            f"Пример:\n"
            f"/update_stats 1331 413515 0.04"
        )
        await update.message.reply_text(text)
    
    async def cmd_update_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /update_stats - синхронизировать с реальными данными DeepSeek"""
        try:
            # Если нет аргументов - показать текущие данные и инструкцию
            if not context.args or len(context.args) < 3:
                current = self.db.get_ai_usage()
                await update.message.reply_text(
                    f"📊 Текущие данные в боте:\n\n"
                    f"Запросов: {current['total_requests']}\n"
                    f"Токенов: {current['total_tokens']:,}\n"
                    f"Стоимость: ${current['total_cost_usd']:.4f}\n\n"
                    f"🔄 Для синхронизации используйте:\n"
                    f"/update_stats <requests> <tokens> <cost>\n\n"
                    f"Пример:\n"
                    f"/update_stats 1661 515627 0.06\n\n"
                    f"⚠️ Данные берите из DeepSeek:\n"
                    f"https://platform.deepseek.com/usage"
                )
                return
            
            requests = int(context.args[0])
            tokens = int(context.args[1])
            cost = float(context.args[2])
            
            # Get current stats
            current = self.db.get_ai_usage()
            
            # Use new sync method to set absolute values
            success = self.db.sync_ai_usage_with_deepseek(requests, tokens, cost)
            
            if success:
                await update.message.reply_text(
                    f"✅ Синхронизировано с DeepSeek!\n\n"
                    f"Было:\n"
                    f"📊 {current['total_requests']} → {requests} запросов\n"
                    f"🔢 {current['total_tokens']:,} → {tokens:,} токенов\n"
                    f"💰 ${current['total_cost_usd']:.4f} → ${cost:.4f}\n\n"
                    f"✨ Дальше учет идет автоматически!\n"
                    f"📈 Эти данные сохраняются и НЕ сбрасываются"
                )
            else:
                await update.message.reply_text("❌ Ошибка при синхронизации")
                
        except ValueError:
            await update.message.reply_text(
                "❌ Ошибка формата! Используйте числа.\n\n"
                "Пример: /update_stats 1661 515627 0.06"
            )
        except Exception as e:
            logger.error(f"Error updating stats: {e}")
            await update.message.reply_text(f"❌ Ошибка: {e}")
    
    async def cmd_filter(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /filter"""
        # Создаем inline кнопки для выбора категорий
        ai_status = "✅" if self.ai_verification_enabled else "❌"
        keyboard = [
            [
                InlineKeyboardButton("#Мир", callback_data="filter_world"),
                InlineKeyboardButton("#Россия", callback_data="filter_russia"),
            ],
            [
                InlineKeyboardButton("#Москва", callback_data="filter_moscow"),
                InlineKeyboardButton("#Подмосковье", callback_data="filter_moscow_region"),
                InlineKeyboardButton("Все новости", callback_data="filter_all"),
            ],
            [
                InlineKeyboardButton(f"AI {ai_status}", callback_data="toggle_ai"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        ai_status_text = "включена" if self.ai_verification_enabled else "отключена"
        await update.message.reply_text(
            "Выберите категорию для фильтрации новостей в канале:\n\n"
            "#Мир - Новости со всего мира\n"
            "#Россия - Новости России\n"
            "#Москва - Новости Москвы\n"
            "#Подмосковье - Новости Московской области\n"
            "Все новости - Показывать все\n\n"
            f"🤖 AI верификация: {ai_status_text}",
            reply_markup=reply_markup
        )
    
    async def handle_emoji_buttons(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик эмодзи-кнопок"""
        text = update.message.text
        
        if text == '🔄':
            await self.cmd_sync(update, context)
        elif text == '📊':
            await self.cmd_status(update, context)
        elif text == '🔍':
            await self.cmd_filter(update, context)
        elif text == '⏸️':
            await self.cmd_pause(update, context)
        elif text == '▶️':
            await self.cmd_resume(update, context)
    
    async def cmd_filter(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /filter - выбор категорий для фильтрации"""
        # Создаем inline кнопки для выбора категорий
        ai_status = "✅" if self.ai_verification_enabled else "❌"
        keyboard = [
            [
                InlineKeyboardButton("#Мир", callback_data="filter_world"),
                InlineKeyboardButton("#Россия", callback_data="filter_russia"),
            ],
            [
                InlineKeyboardButton("#Москва", callback_data="filter_moscow"),
                InlineKeyboardButton("#Подмосковье", callback_data="filter_moscow_region"),
                InlineKeyboardButton("Все новости", callback_data="filter_all"),
            ],
            [
                InlineKeyboardButton(f"AI {ai_status}", callback_data="toggle_ai"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        ai_status_text = "включена" if self.ai_verification_enabled else "отключена"
        await update.message.reply_text(
            "Выберите категорию для фильтрации новостей в канале:\n\n"
            "#Мир - Новости со всего мира\n"
            "#Россия - Новости России\n"
            "#Москва - Новости Москвы\n"
            "#Подмосковье - Новости Московской области\n"
            "Все новости - Показывать все\n\n"
            f"🤖 AI верификация: {ai_status_text}",
            reply_markup=reply_markup
        )
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик нажатия на кнопку"""
        query = update.callback_query
        
        if query.data == "toggle_ai":
            # Переключение AI верификации
            self.ai_verification_enabled = not self.ai_verification_enabled
            status = "включена" if self.ai_verification_enabled else "отключена"
            emoji = "✅" if self.ai_verification_enabled else "❌"
            
            await query.answer(f"{emoji} AI верификация {status}", show_alert=False)
            await query.edit_message_text(
                text=f"{emoji} AI верификация категорий {status}\n\n"
                     f"DeepSeek {'теперь будет проверять' if self.ai_verification_enabled else 'больше не будет проверять'} "
                     "правильность определения категорий новостей."
            )
            return
        
        elif query.data.startswith("filter_"):
            # Фильтрация по категориям
            filter_type = query.data.replace("filter_", "")
            self.category_filter = filter_type if filter_type != 'all' else None
            
            filter_names = {
                'world': '#Мир',
                'russia': '#Россия',
                'moscow': '#Москва',
                'moscow_region': '#Подмосковье',
                'all': 'Все новости'
            }
            
            await query.answer(f"✅ Фильтр установлен: {filter_names.get(filter_type, 'Неизвестно')}", show_alert=False)
            await query.edit_message_text(
                text=f"✅ Установлена фильтрация: {filter_names.get(filter_type, 'Неизвестно')}\n\n"
                     "Новости будут отправляться в канал только выбранной категории."
            )
            return
        
        else:
            data = query.data or ""
            if ":" not in data:
                await query.answer("❌ Неизвестная команда", show_alert=False)
                return

            action, id_str = data.split(":", 1)
            if not id_str.isdigit():
                await query.answer("❌ Некорректный ID", show_alert=False)
                return

            news_id = int(id_str)
            user_id = query.from_user.id

            news = self.db.get_news_by_id(news_id) or self.news_cache.get(news_id)
            if not news:
                await query.answer("❌ Новость не найдена", show_alert=False)
                return

            category_tag = self._get_category_emoji(news.get('category', 'russia'))

            if action == "ai":
                try:
                    from config.config import AI_SUMMARY_MAX_REQUESTS_PER_MINUTE

                    now = time.time()
                    timestamps = self.user_ai_requests.get(user_id, [])
                    timestamps = [t for t in timestamps if now - t < 60]
                    if len(timestamps) >= AI_SUMMARY_MAX_REQUESTS_PER_MINUTE:
                        await query.answer("⏳ Слишком много запросов. Подождите минуту.", show_alert=False)
                        return
                    timestamps.append(now)
                    self.user_ai_requests[user_id] = timestamps

                    await query.answer("⏳ Генерирую пересказ...", show_alert=False)
                    logger.info(f"AI summarize requested for news_id={news_id} by user={user_id}")

                    cached_summary = self.db.get_cached_summary(news_id)
                    if cached_summary:
                        await context.bot.send_message(
                            chat_id=user_id,
                            text=(
                                f"🤖 Пересказ сгенерирован ИИ\n\n{cached_summary}\n\n"
                                f"📰 Источник: {news.get('source', '')}\n{news.get('url', '')}"
                            ),
                            disable_web_page_preview=True,
                            disable_notification=True
                        )
                        return

                    lead_text = news.get('lead_text') or news.get('text', '') or news.get('title', '')
                    from config.config import DEEPSEEK_INPUT_COST_PER_1K_TOKENS_USD, DEEPSEEK_OUTPUT_COST_PER_1K_TOKENS_USD

                    news_url = news.get('url', '')
                    logger.debug(f"Calling DeepSeek: lead_text_len={len(lead_text)}, title='{news.get('title', '')[:30]}', url={bool(news_url)}")
                    summary, token_usage = await self._summarize_with_deepseek(lead_text, news.get('title', ''), url=news_url)
                    logger.debug(f"DeepSeek response: summary={bool(summary)}, tokens={token_usage.get('total_tokens', 0)}")

                    if summary:
                        # Calculate cost based on input and output tokens
                        input_cost = (token_usage['input_tokens'] / 1000.0) * DEEPSEEK_INPUT_COST_PER_1K_TOKENS_USD
                        output_cost = (token_usage['output_tokens'] / 1000.0) * DEEPSEEK_OUTPUT_COST_PER_1K_TOKENS_USD
                        cost_usd = input_cost + output_cost
                        
                        self.db.add_ai_usage(tokens=token_usage['total_tokens'], cost_usd=cost_usd, operation_type='summarize')
                        self.db.save_summary(news_id, summary)
                        
                        await context.bot.send_message(
                            chat_id=user_id,
                            text=(
                                f"🤖 Пересказ сгенерирован ИИ\n\n{summary}\n\n"
                                f"📰 Источник: {news.get('source', '')}\n{news.get('url', '')}"
                            ),
                            disable_web_page_preview=True,
                            disable_notification=True
                        )
                    else:
                        logger.warning(f"AI summarize failed for news_id={news_id}, no summary returned")
                        await context.bot.send_message(
                            chat_id=user_id,
                            text="ИИ временно недоступен. Попробуйте позже.",
                            disable_web_page_preview=True,
                            disable_notification=True
                        )
                    
                except Exception as e:
                    logger.error(f"Error in AI summarize for news_id={news_id}: {e}", exc_info=True)
                    try:
                        await context.bot.send_message(
                            chat_id=user_id,
                            text=f"❌ Ошибка при генерации пересказа: {str(e)[:100]}",
                            disable_web_page_preview=True,
                            disable_notification=True
                        )
                    except:
                        pass
                
                return

            await query.answer("❌ Неизвестная команда", show_alert=False)
    
    async def _fetch_full_article(self, url: str, fallback_text: str) -> str:
        """
        Try to fetch full article text from URL.
        Falls back to provided text if fetch fails.
        
        Args:
            url: URL to fetch
            fallback_text: Fallback text if fetch fails
            
        Returns:
            Full article text or fallback text
        """
        try:
            import httpx
            from utils.article_extractor import extract_article_text
            
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                response = await client.get(url)
                response.raise_for_status()
                
                extracted = await extract_article_text(response.text, max_length=5000)
                if extracted and len(extracted) > len(fallback_text):
                    logger.debug(f"Fetched full article: {len(extracted)} chars")
                    return extracted
                    
        except Exception as e:
            logger.debug(f"Could not fetch full article from {url}: {e}")
        
        return fallback_text

    async def _summarize_with_deepseek(self, text: str, title: str, url: str = None) -> tuple[str | None, dict]:
        """
        Call DeepSeek API to summarize news.
        
        Args:
            text: Article text to summarize
            title: Article title
            url: Optional URL to fetch full article from
            
        Returns:
            Tuple of (summary string or None, token usage dict)
        """
        try:
            # Try to fetch full article if URL provided
            if url:
                text = await self._fetch_full_article(url, text)
            
            summary, token_usage = await self.deepseek_client.summarize(title=title, text=text)
            if summary:
                logger.debug(f"DeepSeek summary created: {summary[:50]}...")
            return summary, token_usage
        except Exception as e:
            logger.error(f"DeepSeek error: {e}")
            return None, {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    async def _send_to_admins(self, message: str, keyboard: InlineKeyboardMarkup, news_id: int):
        """Отправляет новость всем админам в личные сообщения"""
        for admin_id in ADMIN_IDS:
            try:
                await self.application.bot.send_message(
                    chat_id=admin_id,
                    text=message,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=keyboard,
                    disable_web_page_preview=True,
                    disable_notification=True  # Без звука, чтобы не спамить
                )
                logger.debug(f"Sent news to admin {admin_id}")
            except Exception as e:
                logger.warning(f"Failed to send to admin {admin_id}: {e}")
    
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
                # Проверяем фильтр по категориям
                if self.category_filter and news.get('category') != self.category_filter:
                    logger.debug(f"Skipping news (category filter): {news.get('title')[:50]}")
                    continue
                
                # Проверяем дубликат по заголовку (защита от одной новости на разных источниках)
                if self.db.is_similar_title_published(news.get('title', '')):
                    logger.debug(f"Skipping similar title: {news.get('title')[:50]}")
                    continue
                
                # Попытка атомарно зарегистрировать новость в БД
                news_id = self.db.add_news(
                    url=news['url'],
                    title=news.get('title', ''),
                    source=news.get('source', ''),
                    category=news.get('category', ''),
                    lead_text=news.get('text', '') or ''
                )

                if not news_id:
                    logger.debug(f"Skipping duplicate URL: {news.get('url')}")
                    continue
                
                # Проверяем фильтр по категориям
                news_category = news.get('category', 'russia')
                if self.category_filter and news_category != self.category_filter:
                    logger.debug(f"Skipping news due to category filter: {news_category}")
                    continue

                # Формируем сообщение
                category_emoji = self._get_category_emoji(news_category)
                message = format_telegram_message(
                    title=news.get('title', 'No title'),
                    text=news.get('text', ''),
                    source_name=news.get('source', 'Unknown'),
                    source_url=news.get('url', ''),
                    category=category_emoji
                )
                
                # Сохраняем в кэш для ИИ кнопки
                self.news_cache[news_id] = {
                    'title': news.get('title', 'No title'),
                    'text': news.get('text', ''),
                    'lead_text': news.get('text', ''),
                    'url': news.get('url', ''),
                    'source': news.get('source', 'Unknown'),
                    'category': news_category
                }

                # Создаем кнопку только ИИ пересказа (без кнопки категории)
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("ИИ", callback_data=f"ai:{news_id}")]
                ])

                try:
                    # Debug: логируем без реального токена/URL
                    logger.debug(f"Sending message (chat_id hidden)")
                    # Публикуем в канал
                    sent = await self.application.bot.send_message(
                        chat_id=TELEGRAM_CHANNEL_ID,
                        text=message,
                        parse_mode=ParseMode.MARKDOWN,
                        reply_markup=keyboard,
                        disable_web_page_preview=True
                    )

                    # Сохраняем message_id для связи с news_id
                    if sent and hasattr(sent, 'message_id'):
                        self.db.set_telegram_message_id(news_id, sent.message_id)

                    published_count += 1
                    logger.info(f"Published: {news['title'][:50]}")
                    
                    # Отправляем админам в личку с кнопкой "ИИ"
                    await self._send_to_admins(message, keyboard, news_id)

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
        """Возвращает категорию с эмодзи и хештегом"""
        from config.config import CATEGORIES
        return CATEGORIES.get(category, 'Новости')
    
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
