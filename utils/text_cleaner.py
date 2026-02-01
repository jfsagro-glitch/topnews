"""
Очистка текста от HTML и лишних элементов
"""
import re
import os
from html import unescape
from bs4 import BeautifulSoup
import logging

# Универсальные ключевые слова для строк навигации/служебных блоков
NAVIGATION_KEYWORDS = {
    'главное', 'россия', 'мир', 'политика', 'общество', 'происшествия', 'конфликты',
    'преступность', 'экономика', 'спорт', 'наука', 'культура', 'технологии', 'ценности',
    'путешествия', 'жизни', 'вернуться', 'обычную', 'ленту', 'войти', 'реклама', 'все',
    'новости', 'редакция', 'контакты', 'подписка', 'подписаться', 'rss', 'search', 'menu',
    'mobile', 'канал', 'telegram', 'vk', 'вконтакте', 'одноклассники', 'rutube', 'tiktok',
    'youtube', 'dzen', 'mail', 'smi2', 'картина', 'дня', 'лента', 'добра', 'partners',
    'partnerов', 'пресс-релизы', 'promo', 'школа', 'окно', 'россию', 'rt', 'programmy',
    'текущие', 'закупки', 'партнеров', 'обсудить', 'оцени', 'соглашение', 'cookies'
}

SOCIAL_DOMAINS = (
    'vk.com', 'vkvideo', 'telegram', 't.me', 'ok.ru', 'youtube', 'rutube', 'max.ru',
    'smi2.ru', 'twitter', 'instagram', 'facebook', 'zen.yandex', 'dzen.ru'
)

NAVIGATION_PATTERNS = [
    re.compile(r'^\d{1,2}:\d{2}(,\s*\d{1,2}\s+[а-я]+\s+\d{4})?(\s+[а-я]+)?$', re.IGNORECASE),
    re.compile(r'вернуться в обычную ленту', re.IGNORECASE),
    re.compile(r'что думаешь\?\s*оцени', re.IGNORECASE),
    re.compile(r'ошибка в тексте\?', re.IGNORECASE),
    re.compile(r'нашли опечатку', re.IGNORECASE),
    re.compile(r'сегодня в сми', re.IGNORECASE),
    re.compile(r'новости сми2', re.IGNORECASE),
    re.compile(r'лента новостей', re.IGNORECASE),
    re.compile(r'картина дня', re.IGNORECASE),
    re.compile(r'последние новости', re.IGNORECASE),
    re.compile(r'материалы по теме', re.IGNORECASE),
    re.compile(r'похожие материалы', re.IGNORECASE),
    re.compile(r'english\s+deutsch\s+français', re.IGNORECASE),
    re.compile(r'автономная некоммерческая организация', re.IGNORECASE),
    re.compile(r'главный редактор', re.IGNORECASE),
    re.compile(r'адрес редакции', re.IGNORECASE),
    re.compile(r'телефон:\s*\+7', re.IGNORECASE),
]

logger = logging.getLogger(__name__)


def clean_html(html_text: str) -> str:
    """
    Очищает HTML от тегов и лишних элементов
    Убирает множественные пробелы и переносы
    """
    if not html_text:
        return ""
    
    try:
        # Удаляем скрипты и стили
        # Если передали путь к файлу — откроем файл, иначе используем строковое представление
        if isinstance(html_text, str) and os.path.exists(html_text):
            try:
                with open(html_text, 'r', encoding='utf-8', errors='ignore') as fh:
                    content = fh.read()
            except Exception:
                content = str(html_text)
        else:
            content = str(html_text)

        # If input doesn't contain HTML tags, treat as plain text to avoid
        # BeautifulSoup MarkupResemblesLocatorWarning when content looks like a filename.
        if '<' not in content and '>' not in content:
            text = unescape(content)
            text = re.sub(r'\s+', ' ', text).strip()
            return text

        soup = BeautifulSoup(content, 'html.parser')

        for tag in soup(['script', 'style', 'noscript']):
            tag.decompose()

        # Берём текст с сохранением границ блоков
        text = soup.get_text(separator='\n')
        
        # Убираем HTML entities
        text = unescape(text)

        # Фильтруем мусорный текст от РИА Новости (формы регистрации)
        junk_patterns = [
            r'Регистрация пройдена успешно',
            r'Пожалуйста.*перейдите по ссылке из письма',
            r'Отправить еще раз',
            r'Войти через',
            r'Авторизуйтесь',
            # Меню навигации Lenta.ru
            r'Главное Россия Мир Бывший СССР Экономика Силовые структуры',
            r'Наука и техника Авто Культура Спорт Интернет и СМИ',
            r'Ценности Путешествия Из жизни Среда обитания Забота о себе',
            r'Теперь вы знаете Войти Эксклюзивы Статьи Галереи Видео',
            r'Спецпроекты Исследования Мини-игры Архив Лента добра',
            r'Хочешь видеть только',
            # Дополнительная навигация Lenta.ru
            r'Уход за собой:\s*Забота о себе:\s*Lenta\.ru',
            r'Политика:\s*Ценности Путешествия',
            r'Украина:\s*Ценности Путешествия',
            r'хорошие новости\? Жми!',
            r'Вернуться в обычную ленту\?',
            r'Реклама\.?\s*Реклама\.?',
            r'Забота о себе\s+хорошие новости',
            r'Среда обитания\s+Забота о себе',
            r'Путешествия\s+Из жизни\s+Среда обитания',
            r'Внешний вид:\s*Ценности:\s*Lenta\.ru',
            r'Ценности\s+Все\s+Стиль\s+Внешний вид\s+Явления\s+Роскошь\s+Личности',
            r'Ценности\s+Все\s+Стиль\s+Внешний вид',
            r'\d{2}:\d{2},\s*\d{1,2}\s+[а-я]+\s+\d{4}\s+Ценности',
            r'Преступная Россия:\s*Силовые структуры:\s*Lenta\.ru',
            r'Мир\s+Все\s+Политика\s+Общество\s+Происшествия\s+Конфликты\s+Преступность',
            r'Бывший СССР\s+Все\s+Прибалтика\s+Украина\s+Белоруссия\s+Молдавия\s+Закавказье\s+Средняя Азия',
            r'\d{2}:\d{2},\s*\d{1,2}\s+[а-я]+\s+\d{4}\s+(Мир|Бывший СССР)',
            # VK Видео реклама
            r'\d+\+\.\s*ООО\s*[«"]Единое Видео[»"]',
            r'VK\s+Видео:\s*vkvideo\.ru',
            r'Соглашение:\s*vkvideo\.ru/legal',
            r'VK\s*-\s*ВК',
            r'erid:\s*[a-zA-Z0-9]+',
            # Навигация рубрик
            r'Россия\s+Все\s+Общество\s+Политика\s+Происшествия\s+Регионы',
            r'Москва\s+69-я параллель\s+Моя страна',
            r'Общество\s+Политика\s+Происшествия',
            # Метаданные автора
            r'\([^)]*редактор[^)]*\)',
            r'\([^)]*корреспондент[^)]*\)',
            r'\([^)]*журналист[^)]*\)',
            # Фото кредиты
            r'Фото:\s*[A-Za-z\s]+/\s*Reuters',
            r'Фото:\s*[A-Za-z\s]+/\s*ТАСС',
            r'Фото:\s*[A-Za-z\s]+/\s*РИА Новости',
            # Интерактивные элементы
            r'Что думаешь\?\s*Оцени!\s*Обсудить',
            r'Оцени!\s*Обсудить',
            r'Нашли опечатку\?\s*Нажмите\s*Ctrl\+Enter',
            # Блок "Последние новости"
            r'Последние новости\s+[А-Яа-я0-9\s:,–—]+\d{2}:\d{2}',
            r'Все новости\s+Редакция\s+Реклама',
            # Футер Lenta.ru
            r'Редакция\s+Реклама\s+Контакты\s+Пресс-релизы',
            r'Техподдержка\s+Спецпроекты\s+Вакансии\s+RSS',
            r'Правовая информация\s+Мини-игры',
            r'–\d{4}\s+ООО\s*[«"]Лента\.Ру[»"]',
            r'©\s*\d{4}\s+ООО\s*[«"]Лента\.Ру[»"]',
            # "Лента добра" элемент
            r'\d+\+\s*Лента добра деактивирована',
            r'Добро пожаловать в реальный мир',
            r'Лента добра деактивирована',
            # Cookie notice
            r'На сайте используются cookies',
            r'Продолжая использовать сайт',
            r'вы принимаете условия\s*Ok',
            # Новые материалы
            r'Новые материалы\s+Все новости',
            # Ранее сообщалось (ссылки)
            r'Ранее сообщалось\s*,\s*что',
            # Общее меню навигации сайтов
            r'Недвижимость: Экономика: Lenta\.ru',
            r'(Главное|Россия|Мир|Бывший СССР|Экономика|Недвижимость):\s*(Экономика|Lenta\.ru|Главное)',
            r'Войти\s+Эксклюзивы\s+Статьи',
            r'Галереи\s+Видео\s+Спецпроекты',
            # 360.ru навигация
            r'Все новости Истории Эфир Суперчат 360 Спецпроекты',
            r'Подмосковье Балашиха Богородский Воскресенск Дмитров Истра Котельники',
            r'Красногорск Лобня Мытищи Наро-Фоминский Одинцово Павловский Посад',
            r'Подольск Пушкинский Солнечногорск Химки Чехов Королев Реутов Коломна Раменский',
            r'\|\s*360\.ru\s*Все новости',
            r'Суперчат 360\s+Спецпроекты\s+Подмосковье',
            # RIAMO навигация
            r'Новости Подмосковья, события Московской области \| РИАМО',
            r'Гибель пациентов интерната в Кузбассе Специальная военная операция',
            r'Атака США на Венесуэлу Все темы',
            r'Специальная военная операция на Украине',
            r'\|\s*РИАМО\s*Гибель',
            # mosregtoday.ru навигация
            r'Свежие новости Московской области на сегодня \| Подмосковье Сегодня',
            r'Новости Чтиво Эксклюзивы Выберите город поиск',
            r'Чума XXI века\? Новый случай оспы обезьян взбудоражил',
            r'От знака на трассе до мировой истории',
            r'Выберите город поиск Новости Общество',
            r'Актуально Беспилотник по жилым',
            r'На что променяли легендарную простоту',
            r'Маткапитал взлетит до небес',
            r'Пенсионерка продала две квартиры',
            r'Защита снята: что происходит',
            r'Тайный список богачей',
            r'Роспотребнадзор и врачей России',
            r'Беспилотник по жилым домам',
            r'Родители не пустили — и спасли жизнь',
            r'Аннушка уже разлила масло',
            r'Украина готова к предметному разговору',
            r'Звонок в память о первом президенте',
            r'Праздник длиной в километр',
            r'Появились подробности жизни умершей',
            r'Владельцы не найдены',
            # Общие шаблоны для всех новостных сайтов
            r'\d{2}\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+\d{4},\s+\d{2}:\d{2}\s+Актуально',
            r'сегодня в \d{2}:\d{2}\s+(Здравоохранение|Общество|Экономика)',
            r'Все темы\s+сегодня в \d{2}:\d{2}',
            # Временные метки и счётчики
            r'Сегодня \d{2}:\d{2}',
            r'\d{2}\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+\d{4},\s+\d{2}:\d{2}\s+(Общество|Экономика|Здравоохранение|Актуально)',
            r'\s+0\s+0\s+0\s+',  # Счётчики лайков/просмотров
            r'\s+\d+\s+\d+\s+\d+\s+Фото:',
            # Фото и пресс-службы
            r'Фото:\s*Пресс-служба',
            r'Фото:\s*[А-Яа-я\s-]+администрации',
            r'Пресс-служба администрации',
            r'СВИДЕТЕЛЬСТВО О РЕГИСТРАЦИИ СМИ',
            r'ПРАВА НА ВСЕ МАТЕРИАЛЫ',
            r'ИЗДАТЕЛЬСКИЙ ДОМ "ПОДМОСКОВЬЕ"',
            r'Новости О редакции Статьи Рекламодателям Спецпроекты Газеты Контактная информация',
            r'Политика обработки и защиты персональных данных',
            r'Materialy dostupny po licenzii',
            # Обрывки предложений в конце
            r'[а-я]+:\s*[а-я\s]+$',  # "домам: удар в Сартане"
            # TASS (ТАСС) мусор
            r'ТАСС\s*-\s*информационное агентство',
            r'ТАСС\s*/\s*[А-Я\s]+\s*-',
            r'Фото:\s*ТАСС',
            r'©\s*ТАСС',
            r'тасс\.ру\s+Все материалы',
            # Gazeta.ru (Газета.ру) мусор
            r'Газета\.Ru\s*—\s*новости',
            r'Подробнее на Gazeta\.Ru',
            r'©\s*Gazeta\.Ru',
            r'Фото:\s*[А-Яа-я\s/]+Gazeta\.Ru',
            # RBC (РБК) мусор
            r'РБК\s*—\s*новости',
            r'©\s*РБК',
            r'Фото:\s*РБК',
            r'www\.rbc\.ru\s+Главная',
            r'Подписаться на РБК',
            # Kommersant (Коммерсантъ) мусор
            r'Коммерсантъ\s*—\s*издательский дом',
            r'©\s*АО\s*"Коммерсантъ"',
            r'Фото:\s*Коммерсантъ',
            r'kommersant\.ru\s+Главная',
            # Interfax (Интерфакс) мусор
            r'Интерфакс\s*-\s*Россия',
            r'©\s*Интерфакс',
            r'Подробнее на Интерфакс',
            r'interfax\.ru\s+Все новости',
            # Dzen (Дзен) мусор
            r'Яндекс\.Дзен\s*—\s*персональная лента',
            r'dzen\.ru\s+Подписаться',
            r'Читать на Дзен',
            r'Ещё от автора',
            # Ren.tv (РЕН ТВ) мусор
            r'РЕН\s*ТВ\s*—\s*новости',
            r'©\s*РЕН\s*ТВ',
            r'ren\.tv\s+Главная',
            # Iz.ru (Известия) мусор
            r'Известия\s*—\s*новости',
            r'©\s*Известия',
            r'iz\.ru\s+Все новости',
            # RT (Russia Today) мусор
            r'RT\s*на\s*русском',
            r'РТ\s*на\s*русском',
            r'©\s*RT',
            r'©\s*РТ',
            r'russian\.rt\.com\s+Главная',
            r'Канал RT на Telegram\.me',
            r'Вконтакте\s+Twitter\s+RT Russian',
            r'Канал RT на Max\.ru',
            r'в rutube группа на Одноклассники\.ru',
            r'в Дзен rss в TikTok',
            r'ENG\s+DE\s+FR\s+العربية\s+ESP\s+RS\s+RTД\s+Search\s+Menu\s+mobile',
            r'БРИКС\s+Внешняя политика\s+Европа\s+Африка\s+Ближний Восток\s+Палестино-израильский конфликт\s+Азия\s+Санкции\s+ИноТВ\s+Выборы в США\s+—\s+\d{4}',
            r'Search Menu mobile',
            r'Новости\s+Мир\s+Россия\s+Бывший СССР\s+Экономика\s+Спорт\s+Наука\s+Без политики',
            r'Мнения\s+ИноТВ\s+Фото\s+Видео',
            r'Спецоперация на Украине',
            r'Военные преступления на Украине',
            r'Карта помощи Украина',
            r'Белоруссия\s+Молдавия\s+Прибалтика\s+Закавказье',
            r'Короткая ссылка',
            r'Ошибка в тексте\?\s*Выделите её и нажмите «Ctrl \+ Enter»',
            r'Сегодня в СМИ',
            r'Лента новостей',
            r'Картина дня\s+\d{2}:\d{2}',
            r'Новости СМИ2',
            r'English\s+Deutsch\s+Français\s+العربية\s+Español\s+Српски\s+RTД',
            r'RUPTLY',
            r'Окно в Россию',
            r'Школа RT',
            r'Пресс-релизы\s+О канале\s+Промо RT: Избранное',
            r'Программы RT\s+Контакты\s+Текущие закупки RT',
            r'Написать в редакцию\s+Новости партнёров',
            r'Системы рекомендаций',
            r'18\+\s*RT',
            r'©\s*Автономная некоммерческая организация «ТВ-Новости»',
            r'Сетевое издание rt\.com зарегистрировано',
            r'Главный редактор:',
            r'Адрес редакции:',
            r'Телефон: \+7\s*\d{3}\s*\d{3}-\d{2}-\d{2}',
            r'(?s:в Дзен\s+В мире.*?файлы cookies\s+Подтвердить)',
            # Универсальные блоки навигации/листинги
            r'(?s:Последние новости.*?Все новости)',
            r'(?s:Лента новостей.*?Все новости)',
            r'(?s:Картина дня.*?Все новости)',
            r'(?s:Новости партнёров.*?Все новости)',
            r'(?s:Новости партнеров.*?Все новости)',
            r'(?s:Материалы по теме.*?Все новости)',
            r'(?s:Читайте также.*?Все новости)',
            r'(?s:Смотрите также.*?Все новости)',
            r'(?s:Похожие материалы.*?Все новости)',
            # Универсальные соцсети/навигация
            r'Вконтакте\s+Twitter\s+Facebook\s+Instagram',
            r'ВКонтакте\s+Twitter\s+Facebook\s+Instagram',
            r'ВКонтакте\s+Одноклассники\s+Telegram\s+YouTube',
            r'YouTube\s+Telegram\s+Дзен\s+TikTok',
            r'RSS\s+Search\s+Menu',
            r'Поиск\s+Меню',
            # regions.ru мусор
            r'Regions\.ru\s*—\s*новости регионов',
            r'©\s*Regions\.ru',
            # Общие паттерны для всех сайтов
            r'©\s*\d{4}',  # Copyright с годом
            r'Все права защищены',
            r'Использование материалов',
            r'При цитировании',
            r'Редакция не несет ответственности',
            r'Мнение редакции',
            r'может не совпадать',
            r'Подписывайтесь на наш канал',
            r'Следите за новостями',
            r'Больше новостей на',
            r'Читайте также:',
            r'Смотрите также:',
            r'Ранее сообщалось:',
            # Формы подписки и соцсети
            r'Подписаться на рассылку',
            r'Введите ваш e-mail',
            r'Следите за нами в',
            r'Facebook\s*Instagram\s*Twitter',
            r'ВКонтакте\s*Одноклассники\s*Telegram',
            # Навигация и футеры
            r'О проекте\s*Контакты\s*Реклама',
            r'Редакция\s*Авторы\s*RSS',
            r'Пользовательское соглашение',
            r'Политика конфиденциальности',
        ]
        for pattern in junk_patterns:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)
        
        # Дополнительная универсальная фильтрация строк навигации/служебных блоков
        text = _filter_navigation_lines(text)

        # Очищаем от множественных пробелов и переводов строк
        text = re.sub(r'\s+', ' ', text)  # Множественные пробелы → один
        text = text.strip()
        
        return text
    except Exception as e:
        logger.error(f"Error cleaning HTML: {e}")
        return html_text


def _filter_navigation_lines(text: str) -> str:
    """Удаляет строки навигации, футеров и соцблоков по универсальным правилам"""
    lines = text.splitlines()
    filtered = []
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        lower = line.lower()

        # Пропускаем строки с явными паттернами
        if any(pattern.search(lower) for pattern in NAVIGATION_PATTERNS):
            continue
        if any(domain in lower for domain in SOCIAL_DOMAINS):
            continue

        tokens = re.findall(r'[а-яa-z0-9]+', lower)
        if tokens:
            nav_matches = sum(1 for token in tokens if token in NAVIGATION_KEYWORDS)
            if nav_matches >= max(3, int(len(tokens) * 0.7)):
                continue

        filtered.append(line)

    return '\n'.join(filtered)


def extract_first_paragraph(text: str, min_length: int = 30, max_length: int = 250) -> str:
    """
    Извлекает первый осмысленный абзац без мусора.
    Пропускает обрывки, фрагменты с двоеточиями, короткие предложения.
    
    Args:
        text: исходный текст
        min_length: минимальная длина предложения (обычно = 20 для фильтрации мусора)
        max_length: максимальная длина результата в символах
    """
    if not text:
        return ""
    
    # Убираем лишние пробелы
    text = text.strip()
    
    # Убираем неполные предложения в конце (обрывки вроде "домам: удар в Сартане")
    text = re.sub(r'\s*[а-яА-Я]+:\s*[а-яА-Я\s\-а-яА-Я]*$', '', text)
    
    # Убираем служебные фрагменты типа "Фото:", "Источник:", "Смотрите также:"
    text = re.sub(r'(Фото|Источник|Смотрите также|Читайте также|Ранее сообщалось|Подробнее):\s*.*$', '', text, flags=re.IGNORECASE)
    
    # Разбиваем на предложения по точке, вопросу, восклицанию
    sentences = re.split(r'[.!?]+', text)
    sentences = [s.strip() for s in sentences if s.strip()]
    
    # Собираем предложения, пропуская мусор
    result = []
    current_length = 0
    
    for sentence in sentences:
        if not sentence:
            continue
        
        # Фильтры мусора:
        # 1. Слишком короткие фрагменты (обычно ошибки парсинга)
        if len(sentence) < 20:
            continue
        
        # 2. Только служебные слова или числа
        word_tokens = re.findall(r'[а-яА-Яa-zA-Z]+', sentence)
        if len(word_tokens) < 5:  # Минимум 5 слов в предложении
            continue
        
        # 3. Предложения с высоким процентом цифр (обычно это мусор типа "22326")
        digit_ratio = len(re.findall(r'\d+', sentence)) / max(1, len(word_tokens))
        if digit_ratio > 0.3:
            continue
        
        # 4. Предложения, заканчивающиеся на двоеточие (фрагменты)
        if sentence.rstrip().endswith(':'):
            continue
        
        # 5. Очень длинные предложения (обычно ошибки HTML парсинга)
        if len(sentence) > 500:
            continue
        
        # Проверяем, не превышен ли лимит
        if current_length + len(sentence) > max_length:
            break
        
        result.append(sentence)
        current_length += len(sentence) + 1
    
    # Формируем результат
    if result:
        paragraph = '. '.join(result) + '.'
        # Обрезаем если всё ещё превышает max_length
        if len(paragraph) > max_length:
            return truncate_text(paragraph, max_length)
        return paragraph
    
    # Fallback: берём первые max_length символов
    return truncate_text(text, max_length)


def truncate_text(text: str, max_length: int = 500) -> str:
    """
    Обрезает текст до максимальной длины
    """
    if len(text) <= max_length:
        return text
    
    # Обрезаем по слову
    truncated = text[:max_length]
    last_space = truncated.rfind(' ')
    if last_space > 0:
        truncated = truncated[:last_space]
    
    return truncated + '...'


def truncate_for_telegram(text: str, max_length: int = 1000) -> str:
    """
    Hard limit for telegram message (1000 chars)
    """
    if len(text) <= max_length:
        return text
    
    truncated = text[:max_length]
    last_space = truncated.rfind(' ')
    if last_space > max_length // 2:
        truncated = truncated[:last_space]
    
    return truncated.rstrip() + '...'


def format_telegram_message(title: str, text: str, source_name: str, 
                           source_url: str, category: str) -> str:
    """
    Форматирует новость в сообщение для Telegram (компактное, красивое)
    Оптимизировано для отображения в канале без scroll
    """
    # Убираем категории-префиксы из заголовков Lenta.ru и других источников
    title = re.sub(r'^(Уход за собой|Политика|Украина|Экономика|Недвижимость|Общество|Культура|Спорт|Наука|Технологии|Преступная Россия|Силовые структуры|Прибалтика|Бывший СССР|Мир):\s*', '', title, flags=re.IGNORECASE)
    title = re.sub(r'^(Забота о себе|Из жизни|Среда обитания|Ценности|Путешествия):\s*', '', title, flags=re.IGNORECASE)
    title = re.sub(r'Lenta\.ru\s*', '', title, flags=re.IGNORECASE)
    title = re.sub(r'(ТАСС|РБК|Газета\.Ru|Коммерсантъ|Известия|RT|Интерфакс|Дзен)\s*[—–-]\s*', '', title, flags=re.IGNORECASE)
    
    # Фильтруем явные команды и URLs
    if not title or len(title) < 15:  # Минимум 15 символов
        return ""
    
    if title.startswith("/"):
        return ""  # Похоже на команду
    
    # Список UI фраз которые должны быть отфильтрованы
    noise_phrases = [
        'все темы', 'выберите', 'категория', 'подписка',
        'меню', 'навигация', 'войти', 'зарегистр', 'реклама',
        'больше', 'ещё', 'далее', 'читать', 'свернуть', 'развернуть',
        'поделиться', 'ошибка', 'загруж',
    ]
    
    title_lower = title.lower()
    for phrase in noise_phrases:
        if phrase in title_lower:
            return ""  # Похоже на UI элемент
    
    # Очищаем текст
    text = clean_html(text) if text else ""
    
    # Убираем дублирование заголовка в тексте
    normalized_title = ' '.join(title.lower().split())
    normalized_text = ' '.join(text.lower().split())
    if normalized_text.startswith(normalized_title):
        # Удаляем заголовок из начала текста
        text = text[len(title):].strip()
        text = text.lstrip('|:.-').strip()
    
    # Выбираем лид через lead_extractor
    from utils.lead_extractor import clean_text as clean_lead_text, choose_lead
    lead_candidates = [clean_lead_text(text)] if text else []
    paragraph = choose_lead(lead_candidates, max_len=800)
    if not paragraph and text:
        paragraph = truncate_text(text, max_length=800)
    
    # Экранируем спецсимволы для Markdown
    title = escape_markdown(title)
    paragraph = escape_markdown(paragraph)
    source_name = escape_markdown(source_name)
    source_url = escape_markdown(source_url)
    
    # Компактное форматирование (требуемый формат)
    message = f"{title}\n"
    if paragraph:
        paragraph = paragraph.strip()
        message += f"\n{paragraph}\n"
    message += f"\nИсточник: {source_name}\n{source_url}\n\n{category}"
    
    # Hard limit for telegram (1000 chars)
    message = truncate_for_telegram(message, max_length=1000)
    
    return message


def escape_markdown(text: str) -> str:
    """
    Экранирует специальные символы Markdown
    """
    # Экранируем только критические символы для Markdown
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`']
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text

