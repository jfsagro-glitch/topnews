"""
Lead extraction utilities for news items.
Extracts clean, meaningful first paragraph from news content.
"""
from __future__ import annotations

import re
from typing import Iterable

from utils.text_cleaner import clean_html, truncate_text

# Phrases that indicate noise/ads/navigation/service messages
STOP_PHRASES = (
    'подпис', 'реклам', 'telegram', 't.me', 'vk', 'вконтакте', 'ok.ru', 'youtube',
    '©', 'cookie', 'все права', 'читайте также', 'смотрите также', 'подробнее',
    'источник:', 'реклама', 'партнер', 'поделиться', 'войти', 'зарегистр',
    'читать далее', 'читать больше', 'читать полностью', 'подпишитесь',
    'новости партнеров', 'материалы по теме', 'похожие материалы',
    'нашли опечатку', 'ошибка в тексте', 'оцени новость', 'что думаешь',
    'комментируй', 'следи', 'подписывайся', 'поделись', 'лайк', 'репост',
    'все новости', 'главное', 'картина дня', 'последние новости', 'вернуться',
    'главное сейчас', 'интересное рядом', 'лучшее за день', 'видео',
    'фото:', 'видео:', '@', '#', 'автор:', 'редактор:', 'корреспондент:',
    'иллюстрация:', 'скриншот:', 'материалы по теме', 'более подробно'
)

# Extra patterns for clean filtering
MIN_PARAGRAPH_LEN = 50  # Minimum length for meaningful paragraph
MAX_STOP_WORDS = 3  # Max stop words allowed in paragraph

SENTENCE_SPLIT_RE = re.compile(r'(?<=[.!?])\s+')
URL_RE = re.compile(r'https?://\S+|www\.\S+|bit\.ly/\S+')
MULTISPACE_RE = re.compile(r'\s+')
EMAIL_RE = re.compile(r'\S+@\S+\.\S+')
PHONE_RE = re.compile(r'\+?7\s*\(?\d{3}\)?[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}')


def _is_noise_line(line: str, min_len: int = MIN_PARAGRAPH_LEN) -> bool:
    """
    Check if a line is noise/ad/navigation content.
    Returns True if line should be skipped.
    """
    if len(line) < min_len:
        return True
    
    lower = line.lower()
    
    # Count stop phrases in the line
    stop_count = sum(1 for phrase in STOP_PHRASES if phrase in lower)
    if stop_count > 0:
        return True
    
    # Lines starting with service keywords
    if any(lower.startswith(phrase) for phrase in ('читать', 'подробнее', 'источник', 'реклама')):
        return True
    
    # Lines that are mostly URLs or emails
    if len(re.findall(URL_RE, line)) > 2 or re.search(EMAIL_RE, line):
        return True
    
    # Lines with multiple phone numbers (spam)
    if len(re.findall(PHONE_RE, line)) > 1:
        return True
    
    # Lines that are too short but have emoji/special chars (usually junk)
    if len(line) < 60 and any(ord(c) > 127 for c in line if c not in 'АБВГДЕЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯабвгдежзийклмнопрстуфхцчшщъыьэюяЁё '):
        return True
    
    return False


def clean_text(text: str) -> str:
    """
    Clean raw text by removing URLs, emails, noise and normalizing spaces.
    Returns clean, readable paragraph text.
    """
    if not text:
        return ""

    # Remove URLs and emails
    text = URL_RE.sub('', text)
    text = EMAIL_RE.sub('', text)
    
    # Remove phone numbers
    text = PHONE_RE.sub('', text)
    
    # Remove multiple spaces
    text = MULTISPACE_RE.sub(' ', text)
    
    # Remove leading/trailing whitespace
    text = text.strip()
    
    return text


def _extract_candidates_from_text(text: str, min_len: int = MIN_PARAGRAPH_LEN) -> list[str]:
    """
    Extract meaningful paragraphs from text.
    Filters out noise, ads, navigation.
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    candidates: list[str] = []
    
    for line in lines:
        # Skip noise lines early
        if _is_noise_line(line, min_len):
            continue
        
        # Clean the line
        line_clean = clean_text(line)
        
        # Final checks
        if len(line_clean) < min_len:
            continue
        
        # Skip if too many stop phrases
        stop_count = sum(1 for phrase in STOP_PHRASES if phrase.lower() in line_clean.lower())
        if stop_count > 0:
            continue
        
        # Additional quality check: line should have some alphanumeric content
        if not re.search(r'[а-яёa-z0-9]', line_clean, re.IGNORECASE):
            continue
        
        candidates.append(line_clean)
    
    return candidates


def choose_lead(candidates: Iterable[str], max_len: int = 800) -> str:
    """
    Choose the best lead from candidates.
    Prefers longer, more informative paragraphs without noise.
    """
    for candidate in candidates:
        if not candidate:
            continue
        
        lead = candidate.strip()
        
        # Minimum length check
        if len(lead) < MIN_PARAGRAPH_LEN:
            continue
        
        # Skip if contains stop phrases
        if any(phrase.lower() in lead.lower() for phrase in STOP_PHRASES):
            continue
        
        # Skip if too many special characters or emoji
        special_count = sum(1 for c in lead if ord(c) > 127 and c not in 'АБВГДЕЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯабвгдежзийклмнопрстуфхцчшщъыьэюяЁё ')
        if special_count > len(lead) * 0.1:  # More than 10% special chars
            continue
        
        # This is a good lead!
        return truncate_text(lead, max_len)
    
    return ""


def _first_sentence_from_text(text: str, max_len: int = 800) -> str:
    """
    Extract first meaningful sentence from text as fallback.
    """
    text = clean_text(text)
    if len(text) < MIN_PARAGRAPH_LEN:
        return ""
    
    sentences = [s.strip() for s in SENTENCE_SPLIT_RE.split(text) if s.strip()]
    
    for sentence in sentences:
        # Must be reasonably long
        if len(sentence) < MIN_PARAGRAPH_LEN:
            continue
        
        # Must not contain stop phrases
        if any(phrase.lower() in sentence.lower() for phrase in STOP_PHRASES):
            continue
        
        # Must have mostly Cyrillic text
        cyrillic_count = sum(1 for c in sentence if c in 'АБВГДЕЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯабвгдежзийклмнопрстуфхцчшщъыьэюяЁё ')
        if cyrillic_count < len(sentence) * 0.6:  # At least 60% Cyrillic
            continue
        
        return truncate_text(sentence, max_len)
    
    return ""


def extract_lead_from_html(html: str, max_len: int = 800) -> str:
    """
    Extract clean lead from HTML by parsing and choosing first meaningful paragraph.
    """
    if not html:
        return ""

    text = clean_html(html)
    if not text:
        return ""

    # If we have very little text after cleaning, try emergency extraction
    if len(text) < MIN_PARAGRAPH_LEN:
        return ""

    candidates = _extract_candidates_from_text(text, min_len=MIN_PARAGRAPH_LEN)
    lead = choose_lead(candidates, max_len=max_len)
    if lead:
        return lead

    # Fallback 1: get first sentence
    fallback = _first_sentence_from_text(text, max_len=max_len)
    if fallback:
        return fallback
    
    # Fallback 2: Emergency - just take first ~100 chars of clean text that looks reasonable
    sentences = [s.strip() for s in SENTENCE_SPLIT_RE.split(text) if s.strip()]
    for sentence in sentences:
        if len(sentence) >= 80:  # Lower threshold for emergency
            # Quick check: not spam
            if not any(phrase in sentence.lower() for phrase in ['подписаться', 'реклама', 'читать далее']):
                return truncate_text(sentence, max_len)
    
    # Last resort: just return first 100+ chars
    if len(text) >= 100:
        # Find a reasonable break point
        break_points = [text.find('. ', 80), text.find('. ', 100), text.find(' ', 100)]
        break_point = min([p for p in break_points if p > 0], default=120)
        return text[:break_point].strip()
    
    return ""


def extract_lead_from_rss(entry, max_len: int = 800) -> str:
    """
    Extract clean lead from RSS entry summary/description.
    """
    if not entry:
        return ""

    summary = entry.get('summary', '') or entry.get('description', '')
    if not summary or len(summary) < MIN_PARAGRAPH_LEN:
        return ""

    text = clean_html(summary)
    if not text or len(text) < MIN_PARAGRAPH_LEN:
        return ""

    candidates = _extract_candidates_from_text(text, min_len=MIN_PARAGRAPH_LEN)
    lead = choose_lead(candidates, max_len=max_len)
    if lead:
        return lead

    # Fallback: get first sentence
    fallback = _first_sentence_from_text(text, max_len=max_len)
    return fallback
