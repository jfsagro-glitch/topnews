"""
Unit-тесты для проверки целостности промта пересказа новостей.
"""
import pytest
from core.ai.prompts.news_rewrite_prompt import NEWS_REWRITE_PROMPT, NEWS_REWRITE_PROMPT_VERSION
from core.ai.validation import validate_news_text


class TestNewsRewritePromptIntegrity:
    """Тесты целостности системного промта"""
    
    def test_prompt_version_exists(self):
        """Версия промта должна быть задана"""
        assert NEWS_REWRITE_PROMPT_VERSION
        assert isinstance(NEWS_REWRITE_PROMPT_VERSION, str)
        assert len(NEWS_REWRITE_PROMPT_VERSION) > 0
    
    def test_prompt_exists(self):
        """Промт должен быть задан"""
        assert NEWS_REWRITE_PROMPT
        assert isinstance(NEWS_REWRITE_PROMPT, str)
        assert len(NEWS_REWRITE_PROMPT) > 0
    
    def test_prompt_contains_word_count_rules(self):
        """Промт должен содержать правила по объёму текста"""
        assert "от 60 до 150 слов" in NEWS_REWRITE_PROMPT
        assert "Оптимальный объём текста — 80–90 слов" in NEWS_REWRITE_PROMPT
    
    def test_prompt_contains_sentence_length_rule(self):
        """Промт должен содержать правило длины предложений"""
        assert "не более 12 слов" in NEWS_REWRITE_PROMPT
    
    def test_prompt_contains_all_required_rules(self):
        """Промт должен содержать все необходимые правила"""
        required_phrases = [
            "Начни текст с одной короткой фразы до 7 слов",
            "Удали все повторы",
            "Удали все гиперссылки",
            "от 60 до 150 слов",
            "Оптимальный объём текста — 80–90 слов",
            "меньше 60 слов — дополни",
            "превышает 150 слов — сократи",
            "не более 12 слов",
            "легко произноситься",
            "Избегай сложных оборотов и канцелярита",
            "Не добавляй оценок и личных мнений",
            "Сохраняй фактическую точность",
            "готов для озвучивания в новостном радиоэфире"
        ]
        
        for phrase in required_phrases:
            assert phrase in NEWS_REWRITE_PROMPT, f"Missing required phrase: {phrase}"
    
    def test_prompt_has_min_number_of_rules(self):
        """Промт должен содержать минимум 13 строк с правилами"""
        # Подсчитываем количество переносов строк (правила отделены переносами)
        lines = [line.strip() for line in NEWS_REWRITE_PROMPT.split('\n') if line.strip()]
        assert len(lines) >= 13, f"Expected at least 13 rules, found {len(lines)}"


class TestNewsTextValidation:
    """Тесты функции валидации текста"""
    
    def test_validation_ok(self):
        """Текст соответствующий всем требованиям должен проходить валидацию"""
        # Текст из 80 слов с короткими предложениями (до 12 слов)
        text = (
            "Президент подписал новый закон о технологиях. "
            "Документ был одобрен парламентом на прошлой неделе. "
            "Закон регулирует использование искусственного интеллекта в государственных системах. "
            "Эксперты считают это важным шагом вперёд. "
            "Новые правила вступят в силу с первого января. "
            "Компании получат полгода на адаптацию к требованиям. "
            "Министерство разработало специальные методические рекомендации. "
            "Они помогут бизнесу быстрее внедрить изменения. "
            "Правительство выделило средства на обучение специалистов. "
            "Программа охватит более десяти тысяч человек."
        )
        assert validate_news_text(text) == "ok"
    
    def test_validation_too_short(self):
        """Короткий текст (< 60 слов) должен отклоняться"""
        text = "Это очень короткий текст новости. Всего несколько слов."
        assert validate_news_text(text) == "too_short"
    
    def test_validation_too_long(self):
        """Длинный текст (> 150 слов) должен отклоняться"""
        text = " ".join(["слово"] * 151)
        assert validate_news_text(text) == "too_long"
    
    def test_validation_sentence_too_long(self):
        """Предложение длиннее 12 слов должно отклоняться"""
        # Создаём текст с достаточным количеством слов (> 60), но одно предложение длинное (13 слов)
        long_sentence = "Президент Российской Федерации подписал важный новый федеральный закон о регулировании современных цифровых технологий"
        short_sentences = ". ".join(["Это хорошая новость для граждан"] * 12) + "."
        text = long_sentence + ". " + short_sentences
        assert validate_news_text(text) == "sentence_too_long"
    
    def test_validation_empty_text(self):
        """Пустой текст должен отклоняться"""
        assert validate_news_text("") == "too_short"
        assert validate_news_text("   ") == "too_short"
        assert validate_news_text(None) == "too_short"
    
    def test_validation_exact_boundaries(self):
        """Тест граничных значений: 60 и 150 слов"""
        # Ровно 60 слов - OK (создаём предложения по 10 слов)
        sentences_60 = [" ".join([f"слово{j}" for j in range(i*10, i*10+10)]) for i in range(6)]
        text_60 = ". ".join(sentences_60) + "."
        assert validate_news_text(text_60) == "ok"
        
        # 59 слов - too_short
        sentences_59 = [" ".join([f"слово{j}" for j in range(i*10, i*10+10)]) for i in range(5)]
        sentences_59.append(" ".join([f"слово{j}" for j in range(50, 59)]))
        text_59 = ". ".join(sentences_59) + "."
        assert validate_news_text(text_59) == "too_short"
        
        # 150 слов - OK (создаём предложения по 10 слов)
        sentences_150 = [" ".join([f"с{j}" for j in range(i*10, i*10+10)]) for i in range(15)]
        text_150 = ". ".join(sentences_150) + "."
        assert validate_news_text(text_150) == "ok"
        
        # 151 слово - too_long (создаём предложения по 10 слов, последнее 11)
        sentences_151 = [" ".join([f"с{j}" for j in range(i*10, i*10+10)]) for i in range(15)]
        sentences_151.append("слово")
        text_151 = ". ".join(sentences_151) + "."
        assert validate_news_text(text_151) == "too_long"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
