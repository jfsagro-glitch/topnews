"""
Очистка текста от HTML и лишних элементов
"""
import re
import os
from html import unescape
from bs4 import BeautifulSoup
import logging

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

        # Берём текст
        text = soup.get_text(separator=' ')
        
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
            # Обрывки предложений в конце
            r'[а-я]+:\s*[а-я\s]+$',  # "домам: удар в Сартане"
        ]
        for pattern in junk_patterns:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)
        
        # Очищаем от множественных пробелов и переводов строк
        text = re.sub(r'\s+', ' ', text)  # Множественные пробелы → один
        text = text.strip()
        
        return text
    except Exception as e:
        logger.error(f"Error cleaning HTML: {e}")
        return html_text


def extract_first_paragraph(text: str, min_length: int = 30) -> str:
    """
    Извлекает первый осмысленный абзац (компактный)
    """
    if not text:
        return ""
    
    # Убираем лишние пробелы
    text = text.strip()
    
    # Убираем неполные предложения в конце (обрывки)
    # Если текст заканчивается на : или обрывается на предлог
    text = re.sub(r'[а-яА-Я]+:\s*[а-яА-Я\s]+$', '', text)
    
    # Разбиваем на предложения по точке
    sentences = [s.strip() for s in text.split('.') if s.strip()]
    
    # Собираем предложения пока не достигнем нормальной длины (150-200 символов)
    result = []
    current_length = 0
    
    for sentence in sentences:
        if not sentence:
            continue
        # Пропускаем слишком короткие фрагменты (обычно это мусор)
        if len(sentence) < 20:
            continue
        if current_length > 150:  # Остановимся на разумной длине
            break
        result.append(sentence)
        current_length += len(sentence) + 1
    
    if result:
        return '. '.join(result) + '.' if result else text[:200]
    
    return text[:200] if len(text) > 200 else text


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


def truncate_for_copy(text: str, max_length: int = 3000) -> str:
    """
    Hard limit for COPY button response (3000 chars)
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
    # Убираем категории-префиксы из заголовков Lenta.ru
    title = re.sub(r'^(Уход за собой|Политика|Украина|Экономика|Недвижимость):\s*', '', title, flags=re.IGNORECASE)
    title = re.sub(r'^(Забота о себе|Из жизни|Среда обитания):\s*', '', title, flags=re.IGNORECASE)
    title = re.sub(r'Lenta\.ru\s*', '', title, flags=re.IGNORECASE)
    
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
    
    paragraph = extract_first_paragraph(text)
    paragraph = truncate_text(paragraph, max_length=400)  # Компактнее
    
    # Экранируем спецсимволы для Markdown
    title = escape_markdown(title)
    paragraph = escape_markdown(paragraph)
    source_name = escape_markdown(source_name)
    
    # Компактное форматирование
    message = f"*{title}*\n"
    
    if paragraph:
        # Убираем лишние пробелы
        paragraph = paragraph.strip()
        message += f"\n{paragraph}\n"
    
    # Inline информация о источнике и категории (одна строка)
    message += f"\n_{source_name}_ • {category}"
    
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

