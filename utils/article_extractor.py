"""
Extract full article text from HTML content.
"""
import logging
from html.parser import HTMLParser
from typing import Optional

logger = logging.getLogger(__name__)


class TextExtractor(HTMLParser):
    """Simple HTML parser to extract main text content."""
    
    def __init__(self):
        super().__init__()
        self.text_parts = []
        self.skip_tags = {'script', 'style', 'noscript', 'meta', 'link', 'head'}
        self.in_skip_tag = False
        self.current_tag = None
        
    def handle_starttag(self, tag, attrs):
        self.current_tag = tag.lower()
        if self.current_tag in self.skip_tags:
            self.in_skip_tag = True
    
    def handle_endtag(self, tag):
        if tag.lower() in self.skip_tags:
            self.in_skip_tag = False
        # Add newline after block elements
        if tag.lower() in {'p', 'div', 'article', 'section', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'td', 'tr'}:
            if self.text_parts and self.text_parts[-1].strip():
                self.text_parts.append('\n')
    
    def handle_data(self, data):
        if not self.in_skip_tag:
            text = data.strip()
            if text:
                self.text_parts.append(text)
                self.text_parts.append(' ')
    
    def get_text(self) -> str:
        """Get extracted text."""
        text = ''.join(self.text_parts)
        # Clean up multiple spaces and newlines
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        return '\n'.join(lines)


async def extract_article_text(html_content: str, max_length: int = 5000) -> Optional[str]:
    """
    Extract main article text from HTML.
    
    Args:
        html_content: HTML content of the page
        max_length: Maximum length of extracted text
        
    Returns:
        Extracted text or None if extraction failed
    """
    try:
        parser = TextExtractor()
        parser.feed(html_content)
        text = parser.get_text()
        
        if not text or len(text) < 50:
            logger.debug("Extracted text too short, not useful")
            return None
        
        # Return up to max_length characters
        return text[:max_length]
    except Exception as e:
        logger.warning(f"Error extracting article text: {e}")
        return None
