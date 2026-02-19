"""
Валидация AI-сгенерированных текстов новостей.
"""
import logging

logger = logging.getLogger(__name__)


def validate_news_text(text: str) -> str:
    """
    Проверяет соответствие текста новости требованиям по длине и формату.
    
    Args:
        text: Текст новости для проверки
        
    Returns:
        "ok" - текст соответствует требованиям
        "too_short" - текст слишком короткий (< 60 слов)
        "too_long" - текст слишком длинный (> 150 слов)
        "sentence_too_long" - одно из предложений длиннее 12 слов
    """
    if not text or not text.strip():
        return "too_short"
    
    words = text.split()
    word_count = len(words)

    if word_count < 60:
        logger.warning(f"Text too short: {word_count} words (minimum 60)")
        return "too_short"

    if word_count > 150:
        logger.warning(f"Text too long: {word_count} words (maximum 150)")
        return "too_long"

    # Проверка длины предложений
    sentences = [s.strip() for s in text.split(".") if s.strip()]
    for i, sentence in enumerate(sentences, 1):
        sentence_words = len(sentence.split())
        if sentence_words > 12:
            logger.warning(
                f"Sentence {i} too long: {sentence_words} words (maximum 12). "
                f"Sentence: '{sentence[:50]}...'"
            )
            return "sentence_too_long"

    return "ok"
