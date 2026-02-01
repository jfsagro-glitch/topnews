"""
Extract full article text from HTML content using trafilatura for intelligent content extraction.
Falls back to simple parsing if trafilatura unavailable.
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Try to import trafilatura for intelligent content extraction
try:
    import trafilatura
    TRAFILATURA_AVAILABLE = True
except ImportError:
    TRAFILATURA_AVAILABLE = False
    logger.debug("trafilatura not available, using fallback parser")


async def extract_article_text(html_content: str, max_length: int = 5000) -> Optional[str]:
    """
    Extract main article text from HTML using trafilatura if available,
    falls back to simple parsing otherwise.
    
    Args:
        html_content: HTML content of the page
        max_length: Maximum length of extracted text
        
    Returns:
        Extracted text or None if extraction failed
    """
    try:
        text = None
        
        # Try trafilatura first (best for news articles)
        if TRAFILATURA_AVAILABLE:
            try:
                text = trafilatura.extract(
                    html_content,
                    include_comments=False,
                    include_tables=False,
                    include_images=False,
                    include_links=False,
                    with_metadata=False,
                    favor_precision=True,
                    favor_recall=False,
                    no_fallback=False
                )
                if text:
                    # Filter out navigation lists and short fragments
                    lines = [l.strip() for l in text.split('\n') if l.strip()]
                    
                    # Remove lines that are likely city lists (many short words)
                    filtered_lines = []
                    for line in lines:
                        # Skip very short lines
                        if len(line) < 40:
                            continue
                        
                        # Skip lines with too many capital words in a row (city/region lists)
                        words = line.split()
                        if len(words) > 5:
                            capital_ratio = sum(1 for w in words if w and w[0].isupper()) / len(words)
                            if capital_ratio > 0.7:  # More than 70% capitalized = likely list
                                continue
                        
                        # Skip navigation keywords
                        nav_keywords = ['истории эфир', 'новости чтиво', 'выберите город', 
                                       'жесткое заявление', 'соцсети в ярости', 'опасные пилюли',
                                       'шокирующие откровения', 'дело эпштейна', 'новый удар']
                        if any(kw in line.lower() for kw in nav_keywords):
                            continue
                        
                        # Skip lines that are just other news headlines (contain clickbait patterns)
                        clickbait_patterns = [':', 'признался', 'разоблачение', 'откровения']
                        if len(line) < 150 and sum(1 for p in clickbait_patterns if p in line.lower()) >= 2:
                            continue
                        
                        filtered_lines.append(line)
                    
                    if filtered_lines:
                        # Take only first 2-3 paragraphs (actual news content)
                        text = '\n'.join(filtered_lines[:3])
                    else:
                        text = None
                    
                    if text:
                        logger.debug(f"trafilatura extracted {len(text)} chars")
            except Exception as e:
                logger.debug(f"trafilatura extraction failed: {e}")
        
        # Fallback to simple parser if trafilatura failed or unavailable
        if not text:
            text = _extract_simple(html_content)
        
        if not text or len(text) < 50:
            logger.debug("Extracted text too short")
            return None
        
        # Return up to max_length characters
        return text[:max_length]
        
    except Exception as e:
        logger.warning(f"Error extracting article text: {e}")
        return None


def _extract_simple(html_content: str) -> Optional[str]:
    """
    Simple fallback HTML parser to extract main text content.
    Filters out common noise patterns.
    """
    try:
        import re
        from html import unescape
        from html.parser import HTMLParser
        
        # Remove script, style, and common noise tags
        html = re.sub(r'<script[^>]*>.*?</script>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<noscript[^>]*>.*?</noscript>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<nav[^>]*>.*?</nav>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<header[^>]*>.*?</header>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<footer[^>]*>.*?</footer>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<aside[^>]*>.*?</aside>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<div[^>]*class="[^"]*(?:sidebar|nav|ad|comment|related|recommend)[^"]*"[^>]*>.*?</div>', '', html, flags=re.DOTALL | re.IGNORECASE)
        
        # Extract text from article/main/content divs first (higher priority)
        main_match = re.search(r'<(?:article|main|div[^>]*class="[^"]*(?:article|main|content|body)[^"]*")[^>]*>(.*?)</(?:article|main|div)>', html, re.DOTALL | re.IGNORECASE)
        if main_match:
            html = main_match.group(1)
        
        # Remove HTML tags but keep structure
        text = re.sub(r'<[^>]+>', '\n', html)
        text = unescape(text)
        
        # Clean up whitespace
        lines = [line.strip() for line in text.split('\n') if line.strip() and len(line.strip()) > 2]
        
        # Remove very short lines and apply multiple filters
        filtered_lines = []
        for line in lines:
            # Skip very short lines
            if len(line) < 40:
                continue
            
            # Skip lines with too many capital words (city/region lists like "Балашиха Богородский Воскресенск")
            words = line.split()
            if len(words) > 5:
                capital_ratio = sum(1 for w in words if w and w[0].isupper()) / len(words)
                if capital_ratio > 0.7:
                    continue
            
            # Skip navigation/menu lines and other news headlines
            nav_keywords = ['истории эфир', 'новости чтиво', 'выберите город', 'поиск',
                           'политика эксклюзив', 'общество', 'шокирующие откровения',
                           'жесткое заявление', 'дело эпштейна', 'новый удар', 
                           'соцсети в ярости', 'опасные пилюли', 'правда о полисе',
                           'накачали и бросили']
            if any(kw in line.lower() for kw in nav_keywords):
                continue
            
            # Skip clickbait headlines (short + contains colon or multiple trigger words)
            clickbait_count = sum(1 for p in [':', 'признался', 'разоблачение', 'откровения', 'правда'] 
                                 if p in line.lower())
            if len(line) < 150 and clickbait_count >= 2:
                continue
            
            filtered_lines.append(line)
        
        # Take only first 2-3 paragraphs of actual content
        if filtered_lines:
            return '\n'.join(filtered_lines[:3])
        return None
        
    except Exception as e:
        logger.warning(f"Simple extraction failed: {e}")
        return None
