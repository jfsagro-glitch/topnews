import codecs
import re

# Read file
with codecs.open('utils/text_cleaner.py', 'r', 'utf-8') as f:
    content = f.read()

# Find the location after "text = unescape(text)"
old_block = """        # Убираем HTML entities
        text = unescape(text)
        
        # Очищаем от множественных пробелов"""

new_block = """        # Убираем HTML entities
        text = unescape(text)
        
        # Фильтруем мусорный текст от РИА Новости
        junk_patterns = [
            r'Регистрация пройдена успешно',
            r'Пожалуйста.*перейдите по ссылке из письма',
            r'Отправить еще раз',
            r'Войти через',
            r'Авторизуйтесь'
        ]
        for pattern in junk_patterns:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)
        
        # Очищаем от множественных пробелов"""

content = content.replace(old_block, new_block)

# Write file
with codecs.open('utils/text_cleaner.py', 'w', 'utf-8') as f:
    f.write(content)

print("Done!")
