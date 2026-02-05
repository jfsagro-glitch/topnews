"""
Основной Telegram бот для публикации новостей
"""
import logging
import time
import os
import tempfile
import socket
from net.deepseek_client import DeepSeekClient
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters,
    ContextTypes, ConversationHandler
)
from telegram.constants import ParseMode
from telegram.error import Conflict
import asyncio
from config.config import TELEGRAM_TOKEN, TELEGRAM_CHANNEL_ID, CHECK_INTERVAL_SECONDS, ADMIN_IDS

logger = logging.getLogger(__name__)

# Import DATABASE_PATH from railway_config if available, else from config
try:
    from config.railway_config import DATABASE_PATH
except (ImportError, ValueError):
    from config.config import DATABASE_PATH

try:
    from config.railway_config import SOURCES_CONFIG as ACTIVE_SOURCES_CONFIG
except (ImportError, ValueError):
    from config.config import SOURCES_CONFIG as ACTIVE_SOURCES_CONFIG

from db.database import NewsDatabase
from utils.text_cleaner import format_telegram_message
from sources.source_collector import SourceCollector
from core.services.access_control import AILevelManager, get_llm_profile


class NewsBot:
    """Основной класс Telegram бота"""
    
    # Администраторы с полным доступом к обоим ботам
    ADMIN_IDS = [408817675, 464108692, 1592307306]
    
    def __init__(self):
        self.application = None
        self.db = NewsDatabase(db_path=DATABASE_PATH)  # Use path from config
        
        # DeepSeek client with cache and budget enabled
        self.deepseek_client = DeepSeekClient(db=self.db)
        
        # AI category verification toggle (can be controlled via button)
        from config.config import AI_CATEGORY_VERIFICATION_ENABLED
        self.ai_verification_enabled = AI_CATEGORY_VERIFICATION_ENABLED
        
        # SourceCollector with optional AI verification
        self.collector = SourceCollector(db=self.db, ai_client=self.deepseek_client, bot=self)
        
        # Initialize sources from SOURCES_CONFIG
        self._init_sources()
        
        self.is_running = True
        self.is_paused = False
        self.collection_lock = asyncio.Lock()  # Prevent concurrent collection cycles
        
        # Cache for recently published news (for AI button)
        self.news_cache = {}  # news_id -> {'title', 'text', 'source', 'url'}
        
        # Global category filter (None = show all)
        self.category_filter = None  # 'world', 'russia', 'moscow_region', or None
        
        # Rate limiting for AI summarize requests (per user per minute)
        self.user_ai_requests = {}  # {user_id: [timestamp1, timestamp2, ...]}
        
        # Instance lock (prevent double start)
        self._instance_lock_fd = None
        self._instance_lock_path = None
        self._db_instance_id = f"{socket.gethostname()}:{os.getpid()}"
        self._shutdown_requested = False

    def _is_admin(self, user_id: int) -> bool:
        """Check if user is admin (hardcoded ADMIN_IDS or config ADMIN_USER_IDS)."""
        # Hardcoded admins
        admin_ids = set(self.ADMIN_IDS)
        
        # Add admins from config
        try:
            from config.railway_config import ADMIN_USER_IDS
        except (ImportError, ValueError):
            from config.config import ADMIN_USER_IDS
        if ADMIN_USER_IDS:
            admin_ids.update(ADMIN_USER_IDS)
        
        return user_id in admin_ids

    def _has_access(self, user_id: int) -> bool:
        """Check if user has access to bot (admin or approved via invite)."""
        try:
            from config.railway_config import APP_ENV
        except (ImportError, ValueError):
            from config.config import APP_ENV
        
        # Admins always have access
        if self._is_admin(user_id):
            return True
        
        # Sandbox is open to all
        if APP_ENV == "sandbox":
            return True
        
        # Prod requires approval via invite
        return self.db.is_user_approved(str(user_id))

    def _check_access(self, handler):
        """Decorator to check user access before executing handler"""
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user_id = update.effective_user.id
            
            # /start can always be called (handles invite codes and access messages)
            if handler.__name__ == 'cmd_start':
                return await handler(update, context)
            
            # Check if user has access
            if not self._has_access(user_id):
                try:
                    from config.railway_config import APP_ENV
                except (ImportError, ValueError):
                    from config.config import APP_ENV
                
                await update.message.reply_text(
                    "🔒 Доступ к боту только по инвайту.\n\n"
                    "Для получения доступа:\n"
                    "1. Обратитесь к администратору\n"
                    "2. Получите инвайт-ссылку\n"
                    "3. Перейдите по ссылке для активации"
                )
                return
            
            # User has access, execute handler
            return await handler(update, context)
        
        return wrapper

    def _init_admins_access(self):
        """Initialize admin users with access to prod bot"""
        for admin_id in self.ADMIN_IDS:
            # Check if already approved
            if not self.db.is_user_approved(str(admin_id)):
                # Add admin with "SYSTEM" as invited_by
                from datetime import datetime
                cursor = self.db._conn.cursor()
                with self.db._write_lock:
                    cursor.execute(
                        'INSERT OR IGNORE INTO approved_users (user_id, username, first_name, invited_by, approved_at) VALUES (?, ?, ?, ?, ?)',
                        (str(admin_id), None, f"Admin {admin_id}", "SYSTEM", datetime.now().isoformat())
                    )
                    self.db._conn.commit()
                logger.info(f"Initialized admin access for user {admin_id}")

    def _get_sandbox_filter_user_id(self) -> int | None:
        """Pick a user id whose source settings control sandbox filtering."""
        try:
            from config.railway_config import ADMIN_USER_IDS
        except (ImportError, ValueError):
            from config.config import ADMIN_USER_IDS
        if ADMIN_USER_IDS:
            return ADMIN_USER_IDS[0]
        if ADMIN_IDS:
            return ADMIN_IDS[0]
        return None
    
    def _init_sources(self):
        """Инициализировать список источников из ACTIVE_SOURCES_CONFIG"""
        try:
            if not hasattr(self.db, "get_or_create_sources"):
                logger.warning("Source initialization skipped: get_or_create_sources not available")
                return
            sources_to_create = []
            
            # Собрать все источники из конфига, обрабатывая ВСЕ категории одинаково
            for category, cfg in ACTIVE_SOURCES_CONFIG.items():
                for src_url in cfg.get('sources', []):
                    # Telegram каналы - используем имя канала как код
                    if 't.me' in src_url:
                        channel = src_url.replace('https://t.me/', '').replace('http://t.me/', '').replace('@', '').strip('/')
                        if channel:
                            sources_to_create.append({'code': channel, 'title': f"@{channel}"})
                    else:
                        # Web источники (по домену)
                        domain = src_url.replace('https://', '').replace('http://', '').split('/')[0]
                        if domain:
                            sources_to_create.append({'code': domain, 'title': domain})
            
            # Убрать дубликаты
            seen_codes = set()
            unique_sources = []
            for src in sources_to_create:
                if src['code'] not in seen_codes:
                    unique_sources.append(src)
                    seen_codes.add(src['code'])
            
            # Создать или обновить в БД
            self.db.get_or_create_sources(unique_sources)
            logger.info(f"Initialized {len(unique_sources)} sources in database")
        except Exception as e:
            logger.error(f"Error initializing sources: {e}")

    def _acquire_instance_lock(self) -> bool:
        """Acquire a filesystem lock to prevent multiple bot instances."""
        try:
            lock_dir = tempfile.gettempdir()
            lock_path = os.path.join(lock_dir, "topnews_bot.lock")
            self._instance_lock_path = lock_path

            # In sandbox, always clear stale lock to avoid restart loops
            try:
                from config.config import APP_ENV
                if APP_ENV == "sandbox" and os.path.exists(lock_path):
                    os.remove(lock_path)
            except Exception:
                pass

            # If stale lock older than 6 hours, remove it
            stale_seconds = 6 * 3600
            if os.path.exists(lock_path):
                try:
                    mtime = os.path.getmtime(lock_path)
                    if time.time() - mtime > stale_seconds:
                        logger.warning("Stale instance lock found. Removing.")
                        os.remove(lock_path)
                except Exception:
                    pass

            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_RDWR)
            self._instance_lock_fd = fd
            os.write(fd, str(os.getpid()).encode("utf-8"))
            return True
        except FileExistsError:
            logger.error("Another bot instance appears to be running. Exiting.")
            return False
        except Exception as e:
            logger.error(f"Failed to acquire instance lock: {e}")
            return False

    def _release_instance_lock(self):
        """Release filesystem instance lock."""
        try:
            if self._instance_lock_fd is not None:
                os.close(self._instance_lock_fd)
                self._instance_lock_fd = None
            if self._instance_lock_path and os.path.exists(self._instance_lock_path):
                os.remove(self._instance_lock_path)
        except Exception as e:
            logger.debug(f"Failed to release instance lock: {e}")

    def create_application(self) -> Application:
        """Создает и конфигурирует Telegram Application"""
        
        self.application = Application.builder().token(TELEGRAM_TOKEN).build()
        
        # Регистрируем обработчики команд с проверкой доступа
        self.application.add_handler(CommandHandler("start", self._check_access(self.cmd_start)))
        self.application.add_handler(CommandHandler("help", self._check_access(self.cmd_help)))
        self.application.add_handler(CommandHandler("sync", self._check_access(self.cmd_sync)))
        self.application.add_handler(CommandHandler("status", self._check_access(self.cmd_status)))
        self.application.add_handler(CommandHandler("pause", self._check_access(self.cmd_pause)))
        self.application.add_handler(CommandHandler("resume", self._check_access(self.cmd_resume)))
        self.application.add_handler(CommandHandler("filter", self._check_access(self.cmd_filter)))
        self.application.add_handler(CommandHandler("sync_deepseek", self._check_access(self.cmd_sync_deepseek)))
        self.application.add_handler(CommandHandler("update_stats", self._check_access(self.cmd_update_stats)))
        self.application.add_handler(CommandHandler("debug_sources", self._check_access(self.cmd_debug_sources)))
        self.application.add_handler(CommandHandler("my_selection", self._check_access(self.cmd_my_selection)))
        
        # Обработчик текстовых сообщений (эмодзи-кнопки)
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_emoji_buttons))
        
        # Обработчик inline кнопок
        self.application.add_handler(CallbackQueryHandler(self.button_callback))

        # Global error handler
        self.application.add_error_handler(self.on_error)
        
        logger.info("Application created successfully")
        return self.application

    # Persistent reply keyboard for chats (anchored at bottom)
    # For regular users
    REPLY_KEYBOARD = ReplyKeyboardMarkup(
        [['🔄', '✉️', '⏸️', '▶️'], ['⚙️ Настройки']], resize_keyboard=True, one_time_keyboard=False
    )
    
    # For sandbox admin users - includes Management button
    REPLY_KEYBOARD_ADMIN = ReplyKeyboardMarkup(
        [['🔄', '✉️', '⏸️', '▶️'], ['⚙️ Настройки', '🛠 Управление']], resize_keyboard=True, one_time_keyboard=False
    )
    
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /start"""
        try:
            from config.railway_config import APP_ENV
        except (ImportError, ValueError):
            from config.config import APP_ENV
        
        user_id = update.message.from_user.id
        username = update.message.from_user.username
        first_name = update.message.from_user.first_name
        
        # Проверка инвайт-кода (если передан через deep link)
        if context.args and len(context.args) > 0:
            invite_code = context.args[0]
            
            # Попытка использовать инвайт
            if self.db.use_invite(invite_code, str(user_id), username, first_name):
                await update.message.reply_text(
                    "✅ Инвайт-код успешно активирован!\n\n"
                    "Теперь у вас есть доступ к боту. Используйте /help для списка команд.",
                    reply_markup=self.REPLY_KEYBOARD
                )
                return
            else:
                await update.message.reply_text(
                    "❌ Неверный или уже использованный инвайт-код.\n\n"
                    "Получите новый инвайт от администратора."
                )
                return
        
        # Проверка доступа
        if not self._has_access(user_id):
            await update.message.reply_text(
                "🔒 Доступ к боту только по инвайту.\n\n"
                "Для получения доступа:\n"
                "1. Обратитесь к администратору\n"
                "2. Получите инвайт-ссылку\n"
                "3. Перейдите по ссылке для активации"
            )
            return
        
        is_admin = self._is_admin(user_id)
        env_marker = "\n🧪 SANDBOX" if APP_ENV == "sandbox" else ""
        
        # Choose keyboard based on admin status and environment
        keyboard = self.REPLY_KEYBOARD_ADMIN if (APP_ENV == "sandbox" and is_admin) else self.REPLY_KEYBOARD
        
        await update.message.reply_text(
            "👋 Добро пожаловать в News Aggregator Bot!" + env_marker + "\n\n"
            "Используйте /help для списка команд",
            reply_markup=keyboard
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
            "⚙️ Нажмите кнопку 'Настройки' внизу для доступа к:\n"
            "  • Фильтр по категориям\n"
            "  • Управление источниками новостей\n\n"
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
    
    async def cmd_debug_sources(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /debug_sources - показать все источники в БД"""
        if update.message.from_user.id not in ADMIN_IDS:
            await update.message.reply_text("❌ Доступно только администраторам")
            return
        
        all_sources = self.db.get_all_sources()
        if not all_sources:
            await update.message.reply_text("📭 В БД нет новостей ни от одного источника")
            return
        
        text = "📋 Все источники в БД:\n\n"
        total = 0
        for source, count in all_sources.items():
            text += f"• {source}: {count}\n"
            total += count
        text += f"\n📊 Всего новостей: {total}"
        await update.message.reply_text(text)
    
    async def cmd_my_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /my_selection - показать выбранные новости и экспортировать"""
        user_id = update.message.from_user.id
        selected = self.db.get_user_selections(user_id)
        
        if not selected:
            await update.message.reply_text("📭 У вас нет выбранных новостей.\n\nВыберите новости, нажав 📌 под новостью в канале.")
            return
        
        # Показать количество и кнопки действий
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📄 Экспорт в DOC", callback_data="export_doc")],
            [InlineKeyboardButton("🗑 Очистить выбранное", callback_data="clear_selection")]
        ])
        
        await update.message.reply_text(
            f"📌 Выбрано новостей: {len(selected)}\n\n"
            f"Нажмите кнопку ниже для экспорта в документ.",
            reply_markup=keyboard
        )
    
    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /status"""
        stats = self.db.get_stats()
        ai_usage = self.db.get_ai_usage()

        source_health = getattr(self.collector, "source_health", {})
        last_collected = getattr(self.collector, "last_collected_counts", {})
        def _status_icon(key: str, collected: int = None) -> str:
            # Зеленый если источник здоров И собрал хотя бы 1 новость
            # Или если collected > 0 независимо от health
            if collected is not None and collected > 0:
                return "🟢"
            return "🟢" if source_health.get(key) else "🔴"

        # Telegram channels overview
        telegram_sources = ACTIVE_SOURCES_CONFIG.get('telegram', {}).get('sources', [])
        channel_keys = []
        channel_labels = []
        for src in telegram_sources:
            channel = src.replace('https://t.me/', '').replace('http://t.me/', '').replace('@', '').strip('/')
            if channel:
                # SourceCollector stores Telegram source_name as short channel (e.g. 'mash')
                channel_keys.append(channel)
                channel_labels.append(channel)
        channel_counts = self.db.get_source_counts(channel_keys) if channel_keys else {}
        channels_text = ""
        if channel_labels:
            lines = []
            for channel, key in zip(channel_labels, channel_keys):
                published_count = channel_counts.get(key, 0)
                collected_count = last_collected.get(key, 0)
                # Зеленый если собрано > 0, иначе красный
                icon = "🟢" if collected_count > 0 else "🔴"
                lines.append(f"{icon} {channel}: {collected_count}")
            channels_text = "\n📡 Каналы Telegram:\n" + "\n".join(lines) + "\n"

        # Site sources overview (all non-telegram sources)
        # Group by domain to avoid duplicates (same domain from multiple categories)
        site_domains = {}  # domain -> label (first occurrence)
        for category_key, cfg in ACTIVE_SOURCES_CONFIG.items():
            if category_key == 'telegram':
                continue
            for src in cfg.get('sources', []):
                domain = src.replace('https://', '').replace('http://', '').split('/')[0]
                if domain.endswith('t.me') or domain in site_domains:
                    continue
                site_domains[domain] = domain
        
        site_keys = list(site_domains.keys())
        site_counts = self.db.get_source_counts(site_keys) if site_keys else {}
        sites_text = ""
        if site_keys:
            lines = []
            for key in sorted(site_keys):
                published_count = site_counts.get(key, 0)
                collected_count = last_collected.get(key, 0)
                # Зеленый если собрано > 0, иначе красный
                icon = "🟢" if collected_count > 0 else "🔴"
                lines.append(f"{icon} {key}: {collected_count}")
            sites_text = "\n🌐 Сайты:\n" + "\n".join(lines)
        
        # Calculate realistic costs based on token counts
        # DeepSeek pricing: input $0.14/M, output $0.28/M tokens
        # Approximate 60% input, 40% output for text operations
        input_tokens = int(ai_usage['total_tokens'] * 0.6)
        output_tokens = int(ai_usage['total_tokens'] * 0.4)
        input_cost = (input_tokens / 1_000_000.0) * 0.14
        output_cost = (output_tokens / 1_000_000.0) * 0.28
        estimated_cost = input_cost + output_cost
        
        # Get daily budget info from BudgetGuard
        daily_budget_text = ""
        if self.deepseek_client.budget:
            try:
                daily_cost = self.deepseek_client.budget.get_daily_cost()
                daily_limit = self.deepseek_client.budget.daily_limit_usd
                percentage = (daily_cost / daily_limit * 100) if daily_limit > 0 else 0
                is_economy = self.deepseek_client.budget.is_economy_mode()
                
                budget_icon = "🟢"
                if percentage >= 100:
                    budget_icon = "🔴"
                elif percentage >= 80:
                    budget_icon = "🟡"
                
                daily_budget_text = (
                    f"\n💰 Дневной бюджет LLM:\n"
                    f"{budget_icon} ${daily_cost:.4f} / ${daily_limit:.2f} ({percentage:.1f}%)\n"
                    f"{'⚠️ Режим экономии активен' if is_economy else ''}\n"
                )
            except Exception as e:
                logger.error(f"Error getting budget info: {e}")
        
        # Get cache stats
        cache_text = ""
        if self.deepseek_client.cache:
            try:
                stats = self.deepseek_client.cache.get_stats()
                hit_rate = (stats['hits'] / stats['total'] * 100) if stats['total'] > 0 else 0
                cache_text = (
                    f"\n💾 LLM кэш:\n"
                    f"Хиты: {stats['hits']} / {stats['total']} ({hit_rate:.1f}%)\n"
                    f"Записей: {stats['size']}\n"
                )
            except Exception as e:
                logger.error(f"Error getting cache stats: {e}")
        
        status_text = (
            f"📊 Статус бота:\n\n"
            f"Статус: {'⏸️ PAUSED' if self.is_paused else '✅ RUNNING'}\n"
            f"Всего опубликовано: {stats['total']}\n"
            f"За сегодня: {stats['today']}\n"
            f"Интервал проверки: {CHECK_INTERVAL_SECONDS} сек\n"
            f"───────────────────────────────\n"
            f"🧠 ИИ использование (всего):\n"
            f"Всего запросов: {ai_usage['total_requests']}\n"
            f"Всего токенов: {ai_usage['total_tokens']:,}\n"
            f"Расчетная стоимость: ${estimated_cost:.4f}\n\n"
            f"📝 Пересказы: {ai_usage['summarize_requests']} запр., {ai_usage['summarize_tokens']:,} токенов\n"
            f"🏷️ Категории: {ai_usage['category_requests']} запр., {ai_usage['category_tokens']:,} токенов\n"
            f"✨ Очистка текста: {ai_usage['text_clean_requests']} запр., {ai_usage['text_clean_tokens']:,} токенов\n"
            f"{daily_budget_text}"
            f"{cache_text}"
            f"───────────────────────────────"
            f"{channels_text}"
            f"───────────────────────────────"
            f"{sites_text}"
        )
        await update.message.reply_text(status_text, disable_web_page_preview=True)
    
    async def cmd_pause(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /pause - приостановить новости для пользователя"""
        user_id = update.message.from_user.id
        self.db.set_user_paused(str(user_id), True)
        await update.message.reply_text("⏸️ Новости приостановлены для вас\n\nСбор продолжается, но вы не получаете уведомления.\nНажмите ▶️ для возобновления.")
    
    async def cmd_resume(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /resume - возобновить новости для пользователя"""
        user_id = update.message.from_user.id
        self.db.set_user_paused(str(user_id), False)
        await update.message.reply_text("▶️ Новости возобновлены!\n\nТеперь вы снова получаете уведомления о новостях.")
    
    async def cmd_management(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """🛠 Management menu (sandbox admin only)"""
        try:
            from config.railway_config import APP_ENV
        except (ImportError, ValueError):
            from config.config import APP_ENV
        
        user_id = update.message.from_user.id
        
        # Check if sandbox and admin
        if APP_ENV != "sandbox":
            await update.message.reply_text("❌ Management available only in sandbox")
            return
        
        is_admin = self._is_admin(user_id)
        if not is_admin:
            await update.message.reply_text("❌ Доступно только администраторам")
            return
        
        # Show management menu with Users option (AI moved to Settings)
        keyboard = [
            [InlineKeyboardButton("👥 Пользователи и инвайты", callback_data="mgmt:users")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "🛠 Управление ботом\n\n"
            "Выберите раздел:",
            reply_markup=reply_markup
        )
    
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
        user_id = update.message.from_user.id

        # Check if waiting for invite recipient
        if not hasattr(self, '_pending_invites'):
            self._pending_invites = {}
        
        # Old invite text input handler removed - now using share buttons

        # Custom export period input (hours)
        if context.user_data.get("awaiting_export_hours"):
            raw = (text or "").strip()
            try:
                hours = int(raw)
                if hours < 1 or hours > 24:
                    raise ValueError("hours out of range")
            except Exception:
                await update.message.reply_text(
                    "❌ Укажите число часов от 1 до 24.\n"
                    "Пример: 4"
                )
                return

            context.user_data["awaiting_export_hours"] = False
            await self._export_news_period(update.effective_user.id, context, hours=hours)
            return
        
        if text == '🔄':
            await self.cmd_sync(update, context)
        elif text == '✉️':
            # Отправить в личку (Мои новости)
            await self.cmd_my_selection(update, context)
        elif text == '⏸️':
            await self.cmd_pause(update, context)
        elif text == '▶️':
            await self.cmd_resume(update, context)
        elif text == '⚙️ Настройки':
            await self.cmd_settings(update, context)
        elif text == '🛠 Управление':
            await self.cmd_management(update, context)
    
    async def cmd_settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """⚙️ Меню настроек"""
    async def cmd_settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """⚙️ Меню настроек"""
        user_id = update.message.from_user.id
        is_admin = self._is_admin(user_id)
        
        keyboard = [
            [InlineKeyboardButton("🧰 Фильтр", callback_data="settings:filter")],
            [InlineKeyboardButton("📰 Источники", callback_data="settings:sources:0")],
            [InlineKeyboardButton("🤖 AI переключатели", callback_data="ai:management")],
            [InlineKeyboardButton("📥 Экспорт новостей", callback_data="export_menu")],
            [InlineKeyboardButton("📊 Статус бота", callback_data="show_status")],
        ]
        
        # Add global collection control buttons for admins
        if is_admin:
            is_stopped = self.db.is_collection_stopped()
            if is_stopped:
                keyboard.append([InlineKeyboardButton("🔄 Восстановить сбор", callback_data="collection:restore")])
            else:
                keyboard.append([InlineKeyboardButton("🛑 Остановить сбор", callback_data="collection:stop")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "⚙️ Настройки",
            reply_markup=reply_markup
        )
    
    async def cmd_filter(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /filter - выбор категорий для фильтрации"""
        # Создаем inline кнопки для выбора категорий
        ai_status = "✅" if self.ai_verification_enabled else "❌"
        
        # Get user selection count
        user_id = update.message.from_user.id
        selection_count = len(self.db.get_user_selections(user_id))
        
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
            ],
            [
                InlineKeyboardButton("📥 Unload", callback_data="export_menu"),
            ],
            [
                InlineKeyboardButton("📊 Статус бота", callback_data="show_status"),
            ],
            [
                InlineKeyboardButton(f"📄 Мои новости ({selection_count})", callback_data="show_my_selection"),
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
        
        # ==================== COLLECTION CONTROL CALLBACKS ====================
        if query.data == "collection:stop":
            # Stop global collection
            await query.answer()
            user_id = query.from_user.id
            if not self._is_admin(user_id):
                await query.edit_message_text("❌ Только администраторы могут остановить сбор")
                return
            
            self.db.set_collection_stopped(True)
            await query.edit_message_text(
                "🛑 Сбор новостей остановлен глобально\n\n"
                "Все боты перестали собирать новости.\n"
                "Используйте кнопку Восстановить для запуска.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔄 Восстановить сбор", callback_data="collection:restore")
                ]])
            )
            return
        
        if query.data == "collection:restore":
            # Restore global collection
            await query.answer()
            user_id = query.from_user.id
            if not self._is_admin(user_id):
                await query.edit_message_text("❌ Только администраторы могут восстановить сбор")
                return
            
            self.db.set_collection_stopped(False)
            # Unpause the user who pressed restore
            self.db.set_user_paused(str(user_id), False)
            
            await query.edit_message_text(
                "🔄 Сбор новостей восстановлен!\n\n"
                "Боты снова собирают новости в фоне.\n"
                "Новости возобновлены для вас."
            )
            return
        
        # ==================== SETTINGS CALLBACKS ====================
        if query.data == "settings:filter":
            # Показать меню фильтра
            await query.answer()
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
                ],
                [
                    InlineKeyboardButton("⬅️ Назад", callback_data="settings:back"),
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            ai_status_text = "включена" if self.ai_verification_enabled else "отключена"
            await query.edit_message_text(
                text=(
                    "🧰 Фильтр\n\n"
                    "#Мир - Новости со всего мира\n"
                    "#Россия - Новости России\n"
                    "#Москва - Новости Москвы\n"
                    "#Подмосковье - Новости Московской области\n"
                    "Все новости - Показывать все\n\n"
                    f"🤖 AI верификация: {ai_status_text}"
                ),
                reply_markup=reply_markup
            )
            return
        
        if query.data.startswith("settings:sources:"):
            # Показать список источников
            await query.answer()
            page = int(query.data.split(":")[-1])
            await self._show_sources_menu(query, page)
            return
        
        if query.data.startswith("settings:src_toggle:"):
            # Переключить источник
            parts = query.data.split(":")
            source_id = int(parts[2])
            page = int(parts[3]) if len(parts) > 3 else 0
            
            user_id = query.from_user.id
            new_state = self.db.toggle_user_source(user_id, source_id)
            
            await query.answer(f"{'✅ Включено' if new_state else '❌ Отключено'}", show_alert=False)
            await self._show_sources_menu(query, page)
            return
        
        if query.data.startswith("settings:src_page:"):
            # Пагинация источников
            page = int(query.data.split(":")[-1])
            await query.answer()
            await self._show_sources_menu(query, page)
            return
        
        if query.data == "settings:back":
            # Вернуться к меню настроек
            await query.answer()
            keyboard = [
                [InlineKeyboardButton("🧰 Фильтр", callback_data="settings:filter")],
                [InlineKeyboardButton("📰 Источники", callback_data="settings:sources:0")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                text="⚙️ Настройки",
                reply_markup=reply_markup
            )
            return
        
        # ==================== AI MANAGEMENT CALLBACKS (ALL ADMINS) ====================
        if query.data == "ai:management":
            # Show AI levels management screen (works on prod too)
            await query.answer()
            await self._show_ai_management(query)
            return
        
        if query.data.startswith("ai:inc:"):
            # Increment AI level
            module = query.data.split(":")[-1]
            await self._handle_ai_level_change(query, module, action="inc")
            return
        
        if query.data.startswith("ai:dec:"):
            # Decrement AI level
            module = query.data.split(":")[-1]
            await self._handle_ai_level_change(query, module, action="dec")
            return
        
        if query.data.startswith("ai:set:"):
            # Set AI level directly
            parts = query.data.split(":")
            module = parts[2]
            level = int(parts[3])
            await self._handle_ai_level_change(query, module, action="set", level=level)
            return
        
        # ==================== MANAGEMENT CALLBACKS (SANDBOX ADMIN ONLY) ====================
        # Check if sandbox for all management operations
        if query.data.startswith("mgmt:"):
            try:
                from config.railway_config import APP_ENV
            except (ImportError, ValueError):
                from config.config import APP_ENV
            
            # Management only in sandbox (but allow send_invite to check separately)
            if APP_ENV != "sandbox" and not query.data.startswith("mgmt:send_invite:"):
                await query.answer("❌ Управление доступно только в песочнице", show_alert=True)
                return
        
        if query.data.startswith("mgmt:send_invite:"):
            # Show share options for invite (works in sandbox only)
            await query.answer()
            try:
                from config.railway_config import APP_ENV
            except (ImportError, ValueError):
                from config.config import APP_ENV
            
            if APP_ENV != "sandbox":
                await query.edit_message_text("❌ Отправка инвайтов доступна только в песочнице")
                return
            
            # Extract invite code from callback data
            invite_code = query.data.split(":", 2)[2]
            logger.info(f"Preparing to share invite {invite_code}")
            
            # Get PROD bot username (инвайт должен вести на прод бота)
            try:
                from config.railway_config import BOT_PROD_USERNAME
            except (ImportError, ValueError):
                try:
                    from config.config import BOT_PROD_USERNAME
                except ImportError:
                    BOT_PROD_USERNAME = "Tops_News_bot"  # Default prod bot
            
            if not BOT_PROD_USERNAME:
                BOT_PROD_USERNAME = "Tops_News_bot"
            
            # Формируем правильную ссылку на ПРОД бота
            invite_link = f"https://t.me/{BOT_PROD_USERNAME}?start={invite_code}"
            
            # Красивое сообщение с эмодзи (без ссылки на бота)
            from urllib.parse import quote
            share_text = quote(
                f"🎁 Приглашение в News Aggregator Bot!\n\n"
                f"✨ Используйте этот инвайт-код для регистрации:\n"
                f"👉 {invite_code}\n\n"
                f"🚀 Перейти: {invite_link}"
            )
            
            share_url = f"https://t.me/share/url?url={invite_link}&text={share_text}"
            
            keyboard = [
                [InlineKeyboardButton("📤 Поделиться инвайтом", url=share_url)],
                [InlineKeyboardButton("⬅️ Назад", callback_data="mgmt:users")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                text=(
                    f"📤 Отправка инвайта\n\n"
                    f"Нажмите кнопку 'Поделиться' и выберите контакт из Telegram\n\n"
                    f"📌 Код инвайта: <code>{invite_code}</code>\n"
                    f"🔗 Ссылка: <code>{invite_link}</code>"
                ),
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
            
            return
        
        if query.data == "mgmt:users":
            # Show users and invites management screen
            await query.answer()
            await self._show_users_management(query)
            return
        
        if query.data.startswith("mgmt:ai:dec:"):
            # Decrement AI level
            module = query.data.split(":")[-1]
            await self._handle_ai_level_change(query, module, action="dec")
            return
        
        if query.data.startswith("mgmt:ai:set:"):
            # Set AI level directly
            parts = query.data.split(":")
            module = parts[2]
            level = int(parts[3])
            await self._handle_ai_level_change(query, module, action="set", level=level)
            return
        
        if query.data == "mgmt:back":
            # Back to management main menu
            await query.answer()
            keyboard = [
                [InlineKeyboardButton("🤖 AI переключатели", callback_data="ai:management")],
                [InlineKeyboardButton("👥 Пользователи и инвайты", callback_data="mgmt:users")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                text="🛠 Управление ботом\n\nВыберите раздел:",
                reply_markup=reply_markup
            )
        
            return
        
        if query.data == "mgmt:new_invite":
            # Create new invite
            admin_id = str(query.from_user.id)
            invite_code = self.db.create_invite(admin_id)
            
            if invite_code:
                # Get bot username for link
                try:
                    from config.railway_config import BOT_PROD_USERNAME
                except (ImportError, ValueError):
                    try:
                        from config.config import BOT_PROD_USERNAME
                    except ImportError:
                        BOT_PROD_USERNAME = None
                
                if not BOT_PROD_USERNAME:
                    # Fallback: try to get from bot info
                    bot_info = await self.application.bot.get_me()
                    bot_username = bot_info.username
                else:
                    bot_username = BOT_PROD_USERNAME
                
                invite_link = f"https://t.me/{bot_username}?start={invite_code}"
                
                # Show invite in popup with Send button
                keyboard = [
                    [InlineKeyboardButton("📤 Отправить пользователю", callback_data=f"mgmt:send_invite:{invite_code}")],
                    [InlineKeyboardButton("⬅️ Назад", callback_data="mgmt:users")],
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    text=(
                        f"🎉 Новый инвайт-код создан!\n\n"
                        f"📌 Код: `{invite_code}`\n\n"
                        f"🔗 Ссылка для пользователя:\n"
                        f"`{invite_link}`\n\n"
                        f"Нажмите кнопку ниже для отправки инвайта пользователю."
                    ),
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            else:
                await query.answer("❌ Ошибка при создании инвайта", show_alert=True)
            
            return
        
        if query.data == "mgmt:users_list":
            # Show detailed list of users and invites
            approved_users = self.db.get_approved_users()
            unused_invites = self.db.get_unused_invites()
            used_invites = self.db.get_unused_invites()  # In reality we need to get all invites
            
            # Build text list
            text = "📋 Список пользователей и инвайтов\n\n"
            
            if approved_users:
                text += f"✅ Одобренные пользователи ({len(approved_users)}):\n"
                for user_id, username, first_name, approved_at in approved_users[:10]:  # Show max 10
                    name = first_name or username or user_id
                    text += f"  • {name} (ID: {user_id})\n"
                if len(approved_users) > 10:
                    text += f"  ... и ещё {len(approved_users) - 10}\n"
            else:
                text += "✅ Одобренные: нет\n"
            
            text += "\n"
            
            if unused_invites:
                text += f"📨 Активные инвайты ({len(unused_invites)}):\n"
                for code, created_by, created_at in unused_invites[:10]:
                    text += f"  • {code}\n"
                if len(unused_invites) > 10:
                    text += f"  ... и ещё {len(unused_invites) - 10}\n"
                for invite in pending_invites[-3:]:  # Show last 3
                    if invite.get("used"):
                        text += f"  • {invite.get('code', 'unknown')} (юзер: {invite.get('used_by', '?')})\n"
            
            if not approved_users and pending_count == 0 and used_count == 0:
                text += "(пусто)"
            
            # Back button
            keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="mgmt:users")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(text=text, reply_markup=reply_markup)
            return

        if query.data == "noop":
            await query.answer()
            return
        # ==================== OTHER CALLBACKS ====================
        if query.data == "show_status":
            # Показать статус бота
            await query.answer()
            user_id = query.from_user.id
            
            # Получить статус
            stats = self.db.get_stats()
            ai_usage = self.db.get_ai_usage()
            source_health = getattr(self.collector, "source_health", {})
            
            # For Telegram channels, always show green (all are working)
            def _status_icon(key: str) -> str:
                # Telegram channels are always active
                if key.startswith('t.me/') or '.t.me' in key:
                    return "🟢"
                return "🟢" if source_health.get(key) else "🔴"

            # Telegram channels - собираем из ВСЕХ категорий конфига
            channel_keys = []
            channel_labels = []
            for category_key, category_config in ACTIVE_SOURCES_CONFIG.items():
                for src in category_config.get('sources', []):
                    # Проверяем, является ли источник Telegram каналом
                    if 't.me' in src.lower():
                        channel = src.replace('https://t.me/', '').replace('http://t.me/', '').replace('@', '').strip('/')
                        if channel and channel not in channel_labels:  # Избегаем дубликатов
                            channel_keys.append(f"t.me/{channel}")
                            channel_labels.append(channel)
            
            channel_counts = self.db.get_source_counts(channel_keys) if channel_keys else {}
            channels_text = ""
            if channel_labels:
                lines = []
                for channel, key in zip(channel_labels, channel_keys):
                    lines.append(f"{_status_icon(key)} {channel}: {channel_counts.get(key, 0)}")
                channels_text = "\n📡 Каналы Telegram:\n" + "\n".join(lines) + "\n"

            # Собираем ВСЕ веб-источники из всех категорий конфига
            # Используем ту же логику, что и в source_collector для извлечения source_name
            from urllib.parse import urlparse
            all_web_sources = set()
            for category_key, category_config in ACTIVE_SOURCES_CONFIG.items():
                if category_key != 'telegram':  # Пропускаем телеграм, его уже обработали
                    for src in category_config.get('sources', []):
                        parsed = urlparse(src)
                        domain = parsed.netloc.lower()
                        # Пропускаем X/Twitter (они отключены) и Telegram
                        if not domain or any(x in domain for x in ['t.me', 'telegram', 'x.com', 'twitter.com']):
                            continue
                        # Используем домен как source_name (как в source_collector)
                        all_web_sources.add(domain)
            
            # Получаем счетчики из БД
            all_sources_counts = self.db.get_all_sources()
            
            # Формируем полный список веб-источников
            sites_text = ""
            if all_web_sources:
                lines = []
                for source in sorted(all_web_sources):
                    count = all_sources_counts.get(source, 0)
                    # Показываем все источники, даже если count=0
                    lines.append(f"{_status_icon(source)} {source}: {count}")
                sites_text = "\n🌐 Веб-источники:\n" + "\n".join(lines) + "\n"
            
            # Calculate cost
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
                f"Интервал проверки: {CHECK_INTERVAL_SECONDS} сек\n"
                f"───────────────────────────────\n"
                f"🧠 ИИ использование (накопительное):\n"
                f"Всего запросов: {ai_usage['total_requests']}\n"
                f"Всего токенов: {ai_usage['total_tokens']:,}\n"
                f"Расчетная стоимость: ${estimated_cost:.4f}\n\n"
                f"📝 Пересказы: {ai_usage['summarize_requests']} запр., {ai_usage['summarize_tokens']:,} токенов\n"
                f"🏷️ Категории: {ai_usage['category_requests']} запр., {ai_usage['category_tokens']:,} токенов\n"
                f"✨ Очистка текста: {ai_usage['text_clean_requests']} запр., {ai_usage['text_clean_tokens']:,} токенов\n\n"
                f"💡 Обновить из DeepSeek: /update_stats\n"
                f"───────────────────────────────"
                f"{channels_text}"
                f"{sites_text}"
                f"───────────────────────────────"
            )
            
            await context.bot.send_message(
                chat_id=user_id,
                text=status_text,
                disable_web_page_preview=True
            )
            return
        
        if query.data == "show_my_selection":
            # Показать выбранные новости с кнопками экспорта
            user_id = query.from_user.id
            selected = self.db.get_user_selections(user_id)
            
            if not selected:
                await query.answer("📭 У вас нет выбранных новостей", show_alert=True)
                return
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📄 Экспорт в DOC", callback_data="export_doc")],
                [InlineKeyboardButton("🗑 Очистить выбранное", callback_data="clear_selection")]
            ])
            
            await query.answer()
            await context.bot.send_message(
                chat_id=user_id,
                text=f"📌 Выбрано новостей: {len(selected)}\n\nНажмите кнопку ниже для экспорта в документ.",
                reply_markup=keyboard
            )
            return

        if query.data == "export_menu":
            await query.answer()
            user_id = query.from_user.id

            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("⏱ 1 час", callback_data="export_period:1"),
                    InlineKeyboardButton("⏱ 2 часа", callback_data="export_period:2"),
                    InlineKeyboardButton("⏱ 3 часа", callback_data="export_period:3"),
                ],
                [
                    InlineKeyboardButton("⏱ 6 часов", callback_data="export_period:6"),
                    InlineKeyboardButton("⏱ 12 часов", callback_data="export_period:12"),
                    InlineKeyboardButton("⏱ 24 часа", callback_data="export_period:24"),
                ],
                [
                    InlineKeyboardButton("🧩 Custom", callback_data="export_period:custom"),
                ]
            ])

            await context.bot.send_message(
                chat_id=user_id,
                text=(
                    "📥 Unload: выберите период выгрузки (макс. 24 часа).\n"
                    "Можно выбрать фиксированный период или Custom для своего значения."
                ),
                reply_markup=keyboard
            )
            return

        if query.data.startswith("export_period:"):
            await query.answer()
            period = query.data.split(":", 1)[1]
            user_id = query.from_user.id

            if period == "custom":
                context.user_data["awaiting_export_hours"] = True
                await context.bot.send_message(
                    chat_id=user_id,
                    text="🧩 Введите период в часах (1–24). Пример: 4"
                )
                return

            try:
                hours = int(period)
            except ValueError:
                await context.bot.send_message(chat_id=user_id, text="❌ Некорректный период")
                return

            await self._export_news_period(user_id, context, hours=hours)
            return
        
        if query.data == "export_doc":
            # Экспорт выбранных новостей в DOC
            user_id = query.from_user.id
            await query.answer("📄 Генерирую документ...", show_alert=False)
            
            try:
                doc_file = await self._generate_doc_file(user_id)
                if doc_file:
                    count = len(self.db.get_user_selections(user_id))
                    await context.bot.send_document(
                        chat_id=user_id,
                        document=open(doc_file, 'rb'),
                        filename="selected_news.docx",
                        caption=f"📰 Ваши выбранные новости ({count} шт.)"
                    )
                    # Удалить временный файл
                    import os
                    os.remove(doc_file)
                    
                    # Очистить выбранные новости после отправки
                    self.db.clear_user_selections(user_id)
                    await context.bot.send_message(
                        chat_id=user_id,
                        text="✅ Документ отправлен!\n\n📌 Выбранные новости очищены. Начните новую подборку!"
                    )
                else:
                    await context.bot.send_message(user_id, "❌ Ошибка при создании документа")
            except Exception as e:
                logger.error(f"Error generating doc: {e}")
                await context.bot.send_message(user_id, f"❌ Ошибка: {str(e)[:100]}")
            return
        
        elif query.data == "clear_selection":
            # Очистить выбранные новости
            user_id = query.from_user.id
            count = len(self.db.get_user_selections(user_id))
            self.db.clear_user_selections(user_id)
            await query.answer(f"🗑 Очищено {count} новостей", show_alert=False)
            await query.edit_message_text("✅ Выбранные новости очищены")
            return
        
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
                    from config.config import AI_SUMMARY_MAX_REQUESTS_PER_MINUTE, APP_ENV
                    
                    # Check AI summary level (global setting)
                    from core.services.access_control import AILevelManager
                    ai_manager = AILevelManager(self.db)
                    summary_level = ai_manager.get_level('global', 'summary')
                    
                    if summary_level == 0:
                        await query.answer("⚠️ AI пересказ отключён администратором", show_alert=True)
                        return

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
                        # Check if already selected
                        is_selected = self.db.is_news_selected(user_id, news_id)
                        select_btn_text = "✅ Выбрано" if is_selected else "📌 Выбрать"
                        
                        await context.bot.send_message(
                            chat_id=user_id,
                            text=(
                                f"🤖 Пересказ сгенерирован ИИ\n\n{cached_summary}\n\n"
                                f"📰 Источник: {news.get('source', '')}\n{news.get('url', '')}"
                            ),
                            disable_web_page_preview=True,
                            disable_notification=True,
                            reply_markup=InlineKeyboardMarkup([[
                                InlineKeyboardButton(select_btn_text, callback_data=f"select:{news_id}")
                            ]])
                        )
                        return

                    lead_text = news.get('lead_text') or news.get('text', '') or news.get('title', '')
                    from config.config import DEEPSEEK_INPUT_COST_PER_1K_TOKENS_USD, DEEPSEEK_OUTPUT_COST_PER_1K_TOKENS_USD

                    news_url = news.get('url', '')
                    logger.debug(f"Calling DeepSeek: lead_text_len={len(lead_text)}, title='{news.get('title', '')[:30]}', url={bool(news_url)}")
                    summary, token_usage = await self._summarize_with_deepseek(lead_text, news.get('title', ''), url=news_url, user_id=user_id)
                    logger.debug(f"DeepSeek response: summary={bool(summary)}, tokens={token_usage.get('total_tokens', 0)}")

                    if summary:
                        # Calculate cost based on input and output tokens
                        input_cost = (token_usage['input_tokens'] / 1000.0) * DEEPSEEK_INPUT_COST_PER_1K_TOKENS_USD
                        output_cost = (token_usage['output_tokens'] / 1000.0) * DEEPSEEK_OUTPUT_COST_PER_1K_TOKENS_USD
                        cost_usd = input_cost + output_cost
                        
                        self.db.add_ai_usage(tokens=token_usage['total_tokens'], cost_usd=cost_usd, operation_type='summarize')
                        self.db.save_summary(news_id, summary)
                        
                        # Check if already selected
                        is_selected = self.db.is_news_selected(user_id, news_id)
                        select_btn_text = "✅ Выбрано" if is_selected else "📌 Выбрать"
                        
                        await context.bot.send_message(
                            chat_id=user_id,
                            text=(
                                f"🤖 Пересказ сгенерирован ИИ\n\n{summary}\n\n"
                                f"📰 Источник: {news.get('source', '')}\n{news.get('url', '')}"
                            ),
                            disable_web_page_preview=True,
                            disable_notification=True,
                            reply_markup=InlineKeyboardMarkup([[
                                InlineKeyboardButton(select_btn_text, callback_data=f"select:{news_id}")
                            ]])
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
            
            elif action == "select":
                # Добавить/убрать новость из выбранных
                user_id = query.from_user.id
                
                if self.db.is_news_selected(user_id, news_id):
                    # Убрать из выбранных
                    self.db.remove_user_selection(user_id, news_id)
                    await query.answer("✅ Убрано из выбранных", show_alert=False)
                    # Обновить кнопку
                    new_keyboard = InlineKeyboardMarkup([
                        [
                            InlineKeyboardButton("🤖 ИИ", callback_data=f"ai:{news_id}"),
                            InlineKeyboardButton("📌 Выбрать", callback_data=f"select:{news_id}")
                        ]
                    ])
                else:
                    # Добавить в выбранные
                    self.db.add_user_selection(user_id, news_id)
                    await query.answer("✅ Добавлено в выбранные", show_alert=False)
                    # Обновить кнопку
                    new_keyboard = InlineKeyboardMarkup([
                        [
                            InlineKeyboardButton("🤖 ИИ", callback_data=f"ai:{news_id}"),
                            InlineKeyboardButton("✅ Выбрано", callback_data=f"select:{news_id}")
                        ]
                    ])
                
                # Обновить кнопки в сообщении
                try:
                    await query.edit_message_reply_markup(reply_markup=new_keyboard)
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

    async def _summarize_with_deepseek(self, text: str, title: str, url: str = None, user_id: int = None) -> tuple[str | None, dict]:
        """
        Call DeepSeek API to summarize news.
        
        Args:
            text: Article text to summarize
            title: Article title
            url: Optional URL to fetch full article from
            user_id: User ID to get AI level preference (sandbox only)
            
        Returns:
            Tuple of (summary string or None, token usage dict)
        """
        try:
            from config.config import APP_ENV
            
            # Try to fetch full article if URL provided
            if url:
                text = await self._fetch_full_article(url, text)
            
            # Get AI level for summary (global setting)
            from core.services.access_control import AILevelManager
            ai_manager = AILevelManager(self.db)
            level = ai_manager.get_level('global', 'summary')
            
            summary, token_usage = await self.deepseek_client.summarize(title=title, text=text, level=level)
            if summary:
                logger.debug(f"DeepSeek summary created (level={level}): {summary[:50]}...")
            return summary, token_usage
        except Exception as e:
            logger.error(f"DeepSeek error: {e}")
            return None, {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    async def _send_to_admins(self, message: str, keyboard: InlineKeyboardMarkup, news_id: int, news_data: dict = None):
        """Отправляет новость всем админам в личные сообщения, учитывая их настройки источников и паузу"""
        for admin_id in ADMIN_IDS:
            try:
                # Проверяем, не поставил ли пользователь на паузу
                if self.db.is_user_paused(str(admin_id)):
                    logger.debug(f"Skipping news for admin {admin_id}: user is paused")
                    continue
                
                # Проверяем фильтр по источникам для этого админа
                if news_data:
                    # Получаем список включённых источников для админа
                    enabled_source_ids = self.db.get_enabled_source_ids_for_user(str(admin_id))
                    
                    # Если админ имеет список включённых источников
                    if enabled_source_ids is not None:
                        # Построить mapping source_code -> source_id
                        sources = self.db.list_sources()
                        code_to_id = {src['code']: src['id'] for src in sources}
                        
                        # Проверяем, включен ли источник этой новости
                        source = news_data.get('source', '')
                        source_id = code_to_id.get(source)
                        
                        # Если источник не найден в БД или отключен - пропускаем
                        if source_id and source_id not in enabled_source_ids:
                            logger.debug(f"Skipping news for admin {admin_id}: source {source} is disabled")
                            continue
                
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
        # Check global collection stop flag
        if self.db.is_collection_stopped():
            logger.info("Collection is stopped globally, skipping")
            return 0
        
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

            # Sandbox: apply source settings to collected news
            try:
                from config.railway_config import APP_ENV
            except (ImportError, ValueError):
                from config.config import APP_ENV
            if APP_ENV == "sandbox":
                filter_user_id = self._get_sandbox_filter_user_id()
                if filter_user_id:
                    news_items = self._filter_news_by_user_sources(news_items, str(filter_user_id))
            
            published_count = 0
            max_publications = 40  # Лимит публикаций за цикл (защита от rate limiting)
            
            # Кэш заголовков в текущей сессии (защита от дубликатов за весь цикл сбора)
            session_titles = set()  # normalized titles for duplicate detection
            
            # Публикуем каждую новость
            for news in news_items:
                # Проверяем лимит публикаций
                if published_count >= max_publications:
                    logger.info(f"Reached publication limit ({max_publications}), stopping")
                    break
                
                # Проверяем фильтр по источникам для пользователя (система admin_ids)
                # TELEGRAM_CHANNEL_ID - основной канал, где видят все подписчики
                # Но админы в ADMIN_IDS могут видеть разные выборки
                # На данный момент - выдача всем одинаковая (глобальная)
                
                # Проверяем фильтр по категориям
                if self.category_filter and news.get('category') != self.category_filter:
                    logger.debug(f"Skipping news (category filter): {news.get('title')[:50]}")
                    continue
                
                # Проверяем дубликат в текущей сессии (быстрая проверка)
                import re
                title = news.get('title', '')
                normalized = re.sub(r'[^\w\s]', '', title.lower())
                if normalized in session_titles:
                    logger.debug(f"Skipping duplicate in session: {title[:50]}")
                    continue
                session_titles.add(normalized)
                
                # Проверяем дубликат по заголовку в БД (защита от одной новости на разных источниках)
                if self.db.is_similar_title_published(title, threshold=0.85):  # Increased threshold to 0.85
                    logger.debug(f"Skipping similar title: {title[:50]}")
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

                # Check if we need auto-summarization for lenta.ru and ria.ru (cleanup_level=5)
                from core.services.access_control import AILevelManager
                ai_manager = AILevelManager(self.db)
                cleanup_level = ai_manager.get_level('global', 'cleanup')
                
                source = news.get('source', '').lower()
                news_text = news.get('text', '')
                
                # Debug logging for auto-summarization trigger
                is_lenta_or_ria = 'lenta.ru' in source or 'ria.ru' in source
                logger.debug(f"Auto-summarize check: cleanup_level={cleanup_level}, source={source}, is_lenta_or_ria={is_lenta_or_ria}")
                
                # Auto-summarize lenta.ru and ria.ru when cleanup_level=5
                if cleanup_level == 5 and is_lenta_or_ria:
                    logger.info(f"Auto-summarizing {source} (cleanup_level=5)")
                    try:
                        # Get or generate summary
                        cached_summary = self.db.get_cached_summary(news_id)
                        if cached_summary:
                            logger.debug(f"Using cached summary for {news_id}")
                            news_text = cached_summary
                        else:
                            # Generate summary (1-2 sentences)
                            full_text = news_text if news_text else news.get('title', '')
                            summary_level = ai_manager.get_level('global', 'summary')
                            
                            from core.services.access_control import get_llm_profile
                            profile = get_llm_profile(summary_level, 'summary')
                            
                            logger.debug(f"Summary profile for level {summary_level}: {profile}")
                            
                            if not profile.get('disabled'):
                                prompt = f"Перескажи эту новость в 1-2 предложениях очень кратко:\n\n{full_text[:2000]}"
                                
                                summary = await self.llm_client.summarize(
                                    prompt,
                                    max_tokens=profile.get('max_tokens', 150),
                                    temperature=profile.get('temperature', 0.5)
                                )
                                
                                if summary:
                                    self.db.cache_summary(news_id, summary)
                                    news_text = summary
                                    logger.info(f"Generated auto-summary for {source}: {summary[:50]}...")
                                else:
                                    logger.warning(f"Summarization returned empty result for {source}")
                            else:
                                logger.debug(f"Summary is disabled (level={summary_level})")
                    except Exception as e:
                        logger.error(f"Error auto-summarizing {source}: {e}", exc_info=True)
                
                # Формируем сообщение
                news_category = news.get('category', 'russia')
                category_emoji = self._get_category_emoji(news_category)
                
                # Debug: логируем текст перед форматированием
                text_preview = news_text[:100] if news_text else "(no text)"
                logger.debug(f"Formatting message: title={news.get('title', '')[:40]}... text={text_preview}...")
                
                message = format_telegram_message(
                    title=news.get('title', 'No title'),
                    text=news_text,
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

                # Создаем кнопки: ИИ пересказ и Выбрать
                keyboard = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("🤖 ИИ", callback_data=f"ai:{news_id}"),
                        InlineKeyboardButton("📌 Выбрать", callback_data=f"select:{news_id}")
                    ]
                ])

                try:
                    # ВРЕМЕННО ОТКЛЮЧЕНА: пересылка новостей в канал
                    logger.info(f"[STUB] Would publish to channel: {news['title'][:50]}")
                    
                    # Сохраняем news_id как опубликованную (для корректной статистики)
                    published_count += 1
                    
                    # Отправляем админам в личку с кнопкой "ИИ" и учётом их настроек источников
                    await self._send_to_admins(message, keyboard, news_id, news)

                    # Задержка между публикациями (защита от Telegram rate limiting)
                    await asyncio.sleep(0.5)  # Меньше задержка так как не отправляем в канал

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

        try:
            from config.config import APP_ENV
            if APP_ENV == "sandbox":
                self.db.reset_bot_lock()
        except Exception:
            pass

        if not self._acquire_instance_lock():
            return

        if not self.db.acquire_bot_lock(self._db_instance_id, ttl_seconds=600):
            self._release_instance_lock()
            return
        
        # Инициализируем админов в БД (при первом запуске)
        self._init_admins_access()
        
        # Создаем приложение
        self.create_application()
        
        # Запускаем периодический сбор в фоне
        collection_task = asyncio.create_task(self.run_periodic_collection())
        
        # Запускаем приложение
        await self.application.initialize()
        await self.application.start()

        try:
            from config.railway_config import TG_MODE, WEBHOOK_BASE_URL, WEBHOOK_PATH, WEBHOOK_SECRET, PORT
        except (ImportError, ValueError):
            from config.config import TG_MODE, WEBHOOK_BASE_URL, WEBHOOK_PATH, WEBHOOK_SECRET, PORT

        if TG_MODE == "webhook":
            if not WEBHOOK_BASE_URL:
                raise ValueError("WEBHOOK_BASE_URL is required for TG_MODE=webhook")
            webhook_url = WEBHOOK_BASE_URL.rstrip('/') + WEBHOOK_PATH
            await self.application.updater.start_webhook(
                listen="0.0.0.0",
                port=PORT,
                url_path=WEBHOOK_PATH.lstrip('/'),
                webhook_url=webhook_url,
                secret_token=WEBHOOK_SECRET,
            )
            logger.info(f"Bot started with webhook: {webhook_url}")
        else:
            await self.application.updater.start_polling()
            logger.info("Bot started with polling")
        
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
            self.db.release_bot_lock(self._db_instance_id)
            self._release_instance_lock()

    async def _shutdown_due_to_conflict(self, reason: str):
        """Shutdown bot immediately on 409 Conflict (duplicate instance)."""
        if self._shutdown_requested:
            return
        self._shutdown_requested = True
        logger.error(f"Shutting down due to конфликт: {reason}")
        try:
            self.is_running = False
            if self.application and self.application.updater:
                await self.application.updater.stop()
            if self.application:
                await self.application.stop()
                await self.application.shutdown()
        except Exception as e:
            logger.debug(f"Error during конфликт shutdown: {e}")
        finally:
            self.db.release_bot_lock(self._db_instance_id)
            self._release_instance_lock()
            os._exit(0)

    async def on_error(self, update: object, context: ContextTypes.DEFAULT_TYPE):
        """Global error handler for the bot."""
        err = getattr(context, "error", None)
        if isinstance(err, Conflict) or (err and "Conflict: terminated by other getUpdates request" in str(err)):
            await self._shutdown_due_to_conflict(str(err))
    async def _generate_doc_file(self, user_id: int) -> str | None:
        """
        Generate DOC file with selected news for user.
        Format: Title -> URL -> Tag -> Text (clean, minimal formatting)
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            Path to generated file or None if error
        """
        try:
            from docx import Document
            from docx.shared import Pt
            from docx.enum.text import WD_ALIGN_PARAGRAPH
            import tempfile
            
            selected_ids = self.db.get_user_selections(user_id)
            if not selected_ids:
                return None
            
            # Create document with normal style throughout
            doc = Document()
            
            # Add header with generation date
            from datetime import datetime
            header_para = doc.add_paragraph(f"Создано: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
            header_para.alignment = WD_ALIGN_PARAGRAPH.LEFT
            
            # Set default font for entire document (Times New Roman, 12pt)
            style = doc.styles['Normal']
            style.font.name = 'Times New Roman'
            style.font.size = Pt(12)
            
            # Add each news
            for idx, news_id in enumerate(selected_ids):
                # Get news from DB or cache
                news = self.db.get_news_by_id(news_id) or self.news_cache.get(news_id)
                if not news:
                    continue
                
                # Add spacing between articles (not separator lines)
                if idx > 0:
                    doc.add_paragraph()
                
                # 1. Title
                title = news.get('title', 'Без заголовка').strip()
                title_para = doc.add_paragraph(title)
                for run in title_para.runs:
                    run.font.name = 'Times New Roman'
                    run.font.size = Pt(12)
                    run.font.bold = False
                    run.font.color.rgb = None
                
                # 2. URL
                url = news.get('url', '').strip()
                if url:
                    url_para = doc.add_paragraph(url)
                    for run in url_para.runs:
                        run.font.name = 'Times New Roman'
                        run.font.size = Pt(12)
                        run.font.color.rgb = None
                
                # 3. Tag (without emoji, just the hashtag)
                category = news.get('category', 'russia')
                category_map = {
                    'world': '#Мир',
                    'russia': '#Россия',
                    'moscow': '#Москва',
                    'moscow_region': '#Подмосковье',
                }
                tag = category_map.get(category, '#Россия')
                tag_para = doc.add_paragraph(tag)
                for run in tag_para.runs:
                    run.font.name = 'Times New Roman'
                    run.font.size = Pt(12)
                    run.font.bold = False
                    run.font.color.rgb = None
                
                # 4. Text (AI summary if exists, otherwise original text)
                summary = self.db.get_cached_summary(news_id)
                text = summary if summary else news.get('text', news.get('lead_text', 'Текст недоступен'))
                text = text.strip()
                
                # Clean text: remove emoji and extra formatting
                import re
                text = re.sub(r'[😀-🙏🌀-🗿🚀-🛿]', '', text)  # Remove emoji
                text = re.sub(r'📰|🔗|💬|✉️|✅|❌|🤖|📄|📌|🌍|🇷🇺|🏛️|🏘️', '', text)  # Remove specific emoji
                text = re.sub(r'Источник:|Ссылка:|Тег:|Категория:|пересказ:|ИИ:|Оригинальный текст:', '', text, flags=re.IGNORECASE)  # Remove labels
                text = re.sub(r'\s+', ' ', text).strip()  # Clean up whitespace
                
                if text:
                    text_para = doc.add_paragraph(text)
                    for run in text_para.runs:
                        run.font.name = 'Times New Roman'
                        run.font.size = Pt(12)
                        run.font.bold = False
                        run.font.color.rgb = None
            
            # Save to temp file
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.docx')
            doc.save(temp_file.name)
            temp_file.close()
            
            return temp_file.name
            
        except Exception as e:
            logger.error(f"Error generating DOC file: {e}", exc_info=True)
            return None

    async def _export_news_period(self, user_id: int, context: ContextTypes.DEFAULT_TYPE, hours: int) -> None:
        """Export news from the last N hours to Excel and send to user."""
        from datetime import datetime, timedelta

        try:
            end_dt = datetime.now()
            start_dt = end_dt - timedelta(hours=hours)

            news_items = self.db.get_news_in_period(start_dt, end_dt)
            if not news_items:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"📭 За последние {hours} ч. новостей нет."
                )
                return

            excel_file = self._generate_excel_file_for_period(news_items)
            if not excel_file:
                await context.bot.send_message(chat_id=user_id, text="❌ Не удалось создать Excel")
                return

            filename = f"news_export_{hours}h_{end_dt.strftime('%Y%m%d_%H%M')}.xlsx"
            await context.bot.send_document(
                chat_id=user_id,
                document=open(excel_file, 'rb'),
                filename=filename,
                caption=f"📥 Unload: новости за последние {hours} ч. ({len(news_items)} шт.)"
            )

            import os
            os.remove(excel_file)

        except Exception as e:
            logger.error(f"Error exporting Excel: {e}")
            await context.bot.send_message(chat_id=user_id, text="❌ Ошибка при выгрузке")

    def _generate_excel_file_for_period(self, news_items: list) -> str | None:
        """Generate Excel file for news items list."""
        try:
            from openpyxl import Workbook
            from openpyxl.utils import get_column_letter
            import tempfile

            wb = Workbook()
            ws = wb.active
            ws.title = "News"

            headers = [
                "Время новости",
                "Источник",
                "Ссылка",
                "Заголовок",
                "Содержание новости",
                "Хештэг"
            ]
            ws.append(headers)

            category_map = {
                'world': '#Мир',
                'russia': '#Россия',
                'moscow': '#Москва',
                'moscow_region': '#Подмосковье',
            }

            for news in news_items:
                content = news.get('ai_summary') or news.get('lead_text') or ""
                content = str(content).strip()
                tag = category_map.get(news.get('category', 'russia'), '#Россия')
                ws.append([
                    news.get('published_at', ''),
                    news.get('source', ''),
                    news.get('url', ''),
                    news.get('title', ''),
                    content,
                    tag
                ])

            # Set column widths for readability
            col_widths = [20, 25, 50, 60, 80, 15]
            for i, width in enumerate(col_widths, start=1):
                ws.column_dimensions[get_column_letter(i)].width = width

            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx')
            wb.save(temp_file.name)
            temp_file.close()
            return temp_file.name
        except Exception as e:
            logger.error(f"Error generating Excel file: {e}")
            return None
    
    async def _show_sources_menu(self, query, page: int = 0):
        """Показать меню источников с пагинацией"""
        sources = self.db.list_sources()
        user_id = str(query.from_user.id)
        user_enabled = self.db.get_user_source_enabled_map(user_id)
        
        # Пагинация
        PAGE_SIZE = 8
        total_pages = (len(sources) + PAGE_SIZE - 1) // PAGE_SIZE
        page = max(0, min(page, total_pages - 1))
        
        start = page * PAGE_SIZE
        end = start + PAGE_SIZE
        page_sources = sources[start:end]
        
        # Построить клавиатуру
        keyboard = []
        for src in page_sources:
            source_id = src['id']
            title = src['title']
            # Если нет записи в user_source_settings -> считаем True
            enabled = user_enabled.get(source_id, True)
            icon = "✅" if enabled else "⬜️"
            btn_text = f"{icon} {title}"
            keyboard.append([
                InlineKeyboardButton(btn_text, callback_data=f"settings:src_toggle:{source_id}:{page}")
            ])
        
        # Пагинация кнопок
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("⬅️", callback_data=f"settings:src_page:{page-1}"))
        nav_buttons.append(InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="noop"))
        if page < total_pages - 1:
            nav_buttons.append(InlineKeyboardButton("➡️", callback_data=f"settings:src_page:{page+1}"))
        
        if nav_buttons:
            keyboard.append(nav_buttons)
        
        # Кнопка "Назад"
        keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="settings:back")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            text=f"📰 Источники новостей (страница {page+1}/{total_pages})\n\n✅ = включено\n⬜️ = отключено",
            reply_markup=reply_markup
        )
    
    def _filter_news_by_user_sources(self, news_items: list, user_id=None) -> list:
        """
        Отфильтровать новости по включённым для пользователя источникам.
        Если user_id=None или у пользователя все источники включены - возвращаем все.
        """
        if not user_id:
            return news_items
        
        enabled_source_ids = self.db.get_enabled_source_ids_for_user(user_id)
        
        # Если None -> все включены
        if enabled_source_ids is None:
            return news_items
        
        # Преобразовать source_ids в set для быстрого поиска
        enabled_ids_set = set(enabled_source_ids)
        
        # Построить mapping source_code/title -> source_id
        sources = self.db.list_sources()
        code_to_id = {src['code']: src['id'] for src in sources}
        
        filtered = []
        for news in news_items:
            source = news.get('source', '')
            # Попробовать найти source_id по code или title
            source_id = code_to_id.get(source)
            if source_id and source_id in enabled_ids_set:
                filtered.append(news)
            elif not source_id:
                # Если источник не найден в БД - включаем его (по умолчанию)
                filtered.append(news)
        
        return filtered

    async def _show_ai_management(self, query):
        """Show AI levels management screen"""
        try:
            try:
                from config.railway_config import APP_ENV
            except (ImportError, ValueError):
                from config.config import APP_ENV
            
            from core.services.access_control import AILevelManager
            
            user_id = str(query.from_user.id)
            
            # Check admin
            is_admin = self._is_admin(int(user_id))
            if not is_admin:
                await query.answer("❌ Доступ запрещён", show_alert=True)
                return
            
            # Get AI level manager
            ai_manager = AILevelManager(self.db)
            
            # Get current levels (global settings)
            hashtags_level = ai_manager.get_level('global', 'hashtags')
            cleanup_level = ai_manager.get_level('global', 'cleanup')
            summary_level = ai_manager.get_level('global', 'summary')
            
            # Build UI
            def level_text(level: int) -> str:
                return "OFF" if level == 0 else str(level)
            
            def level_icon(level: int) -> str:
                return "⬜️" if level == 0 else "✅"
            
            keyboard = []
            
            # Hashtags
            keyboard.append([InlineKeyboardButton(
                f"{level_icon(hashtags_level)} 🏷 Хештеги (AI): {level_text(hashtags_level)}",
                callback_data="noop"
            )])
            keyboard.append([
                InlineKeyboardButton("−", callback_data="ai:dec:hashtags"),
                InlineKeyboardButton("OFF", callback_data="ai:set:hashtags:0"),
                InlineKeyboardButton("+", callback_data="ai:inc:hashtags"),
            ])
            
            # Cleanup
            keyboard.append([InlineKeyboardButton(
                f"{level_icon(cleanup_level)} 🧹 Очистка (AI): {level_text(cleanup_level)}",
                callback_data="noop"
            )])
            keyboard.append([
                InlineKeyboardButton("−", callback_data="ai:dec:cleanup"),
                InlineKeyboardButton("OFF", callback_data="ai:set:cleanup:0"),
                InlineKeyboardButton("+", callback_data="ai:inc:cleanup"),
            ])
            
            # Summary
            keyboard.append([InlineKeyboardButton(
                f"{level_icon(summary_level)} 📝 Пересказ (AI): {level_text(summary_level)}",
                callback_data="noop"
            )])
            keyboard.append([
                InlineKeyboardButton("−", callback_data="ai:dec:summary"),
                InlineKeyboardButton("OFF", callback_data="ai:set:summary:0"),
                InlineKeyboardButton("+", callback_data="ai:inc:summary"),
            ])
            
            # Back button
            keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="settings:back")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            text = (
                "🤖 Управление AI модулями (ГЛОБАЛЬНЫЕ)\n\n"
                "Уровни 0-5:\n"
                "• 0 = выключено (no LLM calls)\n"
                "• 1-2 = быстрый/экономный режим\n"
                "• 3 = стандартный (по умолчанию)\n"
                "• 4-5 = максимальное качество\n\n"
                "⚡️ Очистка level=5: автоматический пересказ\n"
                "   для lenta.ru и ria.ru (1-2 предложения)\n\n"
                "Используйте − и + для настройки уровня,\n"
                "или OFF для полного отключения.\n\n"
                "⚠️ Настройки применяются к ПРОДУ и ПЕСОЧНИЦЕ"
            )
            
            await query.edit_message_text(text=text, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"AI management error: {e}")
            await query.answer("❌ Ошибка меню AI", show_alert=True)
    
    async def _handle_ai_level_change(self, query, module: str, action: str, level: int = None):
        """Handle AI level change (inc/dec/set) - uses global settings"""
        try:
            from config.railway_config import APP_ENV
        except (ImportError, ValueError):
            from config.config import APP_ENV
        from core.services.access_control import AILevelManager
        
        user_id = str(query.from_user.id)
        
        # Check admin
        is_admin = self._is_admin(int(user_id))
        if not is_admin:
            await query.answer("❌ Доступ запрещён", show_alert=True)
            return
        
        # Get AI level manager
        ai_manager = AILevelManager(self.db)
        
        # Perform action on GLOBAL settings (affects both prod and sandbox)
        if action == "inc":
            new_level = ai_manager.inc_level('global', module)
        elif action == "dec":
            new_level = ai_manager.dec_level('global', module)
        elif action == "set":
            ai_manager.set_level('global', module, level)
            new_level = level
        else:
            await query.answer("❌ Invalid action", show_alert=True)
            return
        
        # Show feedback
        await query.answer(f"✅ {module}: {new_level}")
        
        # Re-render screen
        await self._show_ai_management(query)

    async def _show_users_management(self, query):
        """Show users and invites management screen"""
        try:
            from config.railway_config import APP_ENV
        except (ImportError, ValueError):
            from config.config import APP_ENV

        user_id = query.from_user.id

        # Check admin
        is_admin = self._is_admin(user_id)
        if not is_admin:
            await query.answer("❌ Доступ запрещён", show_alert=True)
            return

        # For prod, sandbox restriction should not apply (admins can manage both)
        # Get invites and approved users from DB
        unused_invites = self.db.get_unused_invites()
        approved_users = self.db.get_approved_users()

        # Build UI
        keyboard = []

        # Users section
        keyboard.append([InlineKeyboardButton("👥 Одобренные пользователи", callback_data="noop")])
        if approved_users:
            keyboard.append([InlineKeyboardButton(f"({len(approved_users)} чел.)", callback_data="noop")])
        else:
            keyboard.append([InlineKeyboardButton("(нет)", callback_data="noop")])

        # Invites section
        keyboard.append([InlineKeyboardButton("📨 Активные инвайты", callback_data="noop")])
        if unused_invites:
            keyboard.append([InlineKeyboardButton(f"({len(unused_invites)} инвайтов)", callback_data="noop")])
        else:
            keyboard.append([InlineKeyboardButton("(нет)", callback_data="noop")])

        # Action buttons
        keyboard.append([
            InlineKeyboardButton("➕ Создать инвайт", callback_data="mgmt:new_invite"),
            InlineKeyboardButton("👁️ Список", callback_data="mgmt:users_list"),
        ])

        # Back button
        keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="mgmt:back")])

        reply_markup = InlineKeyboardMarkup(keyboard)

        text = (
            "👥 Управление пользователями и инвайтами\n\n"
            f"✅ Одобренные: {len(approved_users)} чел.\n"
            f"📨 Активные инвайты: {len(unused_invites)}\n\n"
            "Используйте кнопки ниже для управления."
        )

        await query.edit_message_text(text=text, reply_markup=reply_markup)

