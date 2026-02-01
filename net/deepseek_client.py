"""
DeepSeek API client for AI summarization.
"""
from __future__ import annotations

import asyncio
import os
import logging
from typing import Optional

import httpx

from config.config import DEEPSEEK_API_ENDPOINT, AI_SUMMARY_TIMEOUT
from utils.text_cleaner import truncate_text

logger = logging.getLogger(__name__)

MAX_INPUT_CHARS = 3500


def _truncate_input(text: str, max_chars: int = MAX_INPUT_CHARS) -> str:
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    return truncate_text(text, max_chars)


def _estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // 4)


def _build_messages(title: str, text: str) -> list[dict]:
    system_prompt = (
        "Ты помощник для пересказа новостей. "
        "Сделай краткий пересказ на русском в 3–6 предложениях. "
        "Нейтральный тон, без оценок и домыслов, без кликбейта. "
        "Сохраняй факты, числа, географию, имена. "
        "Если данных мало — честно напиши: 'В источнике мало деталей' и кратко суммируй."
    )
    user_content = f"Заголовок: {title}\n\nТекст: {text}"
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]


def _build_category_messages(title: str, text: str, current_category: str) -> list[dict]:
    """Build messages for AI category verification"""
    system_prompt = (
        "Ты помощник для классификации новостей по категориям. "
        "Определи наиболее подходящую категорию для новости.\n\n"
        "Категории:\n"
        "- moscow: новости о городе Москве (столица, Кремль, мэр Собянин, московские власти, события В Москве)\n"
        "- moscow_region: новости о Московской области/Подмосковье (города МО, губернатор МО, события в области)\n"
        "- world: международные новости (другие страны, зарубежные события, мировая политика)\n"
        "- russia: новости о России в целом (федеральная политика, регионы РФ кроме Москвы/МО, российские события)\n\n"
        "Текущая категория: {current_category}\n\n"
        "ВАЖНО: Ответь ТОЛЬКО названием категории одним словом: moscow, moscow_region, world или russia. "
        "Не добавляй пояснений или дополнительного текста."
    )
    user_content = f"Заголовок: {title}\n\nТекст: {text[:1000]}"
    return [
        {"role": "system", "content": system_prompt.format(current_category=current_category)},
        {"role": "user", "content": user_content},
    ]


def _build_text_extraction_messages(title: str, raw_text: str) -> list[dict]:
    """Build messages for AI text extraction (removing navigation/garbage)"""
    system_prompt = (
        "Ты помощник для извлечения чистого текста новости из HTML.\n\n"
        "Твоя задача: извлечь ТОЛЬКО основной текст самой новости, удалив:\n"
        "- Списки городов (Балашиха Богородский Воскресенск...)\n"
        "- Навигационные меню (Культура Все Кино Сериалы, Истории Эфир...)\n"
        "- Заголовки других новостей (Шокирующие откровения...)\n"
        "- Дублирование заголовка (если заголовок повторяется 2-3 раза)\n"
        "- Рекламу и ссылки\n\n"
        "Верни 1-2 абзаца с фактами о событии, указанном в заголовке. Не добавляй пояснений."
    )
    user_content = f"Заголовок: {title}\n\nИзвлеченный текст:\n{raw_text[:3500]}"
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]


class DeepSeekClient:
    def __init__(self, api_key: str = None, endpoint: str = DEEPSEEK_API_ENDPOINT):
        # Don't use config-time DEEPSEEK_API_KEY for parameter default
        # It may be empty during import; we'll read from environment at request time
        self.api_key = api_key if api_key and api_key.strip() else None
        self.endpoint = endpoint
        
        # Log initialization for debugging
        env_key_at_init = os.getenv('DEEPSEEK_API_KEY')
        logger.info(
            f"DeepSeekClient initialized. "
            f"Env DEEPSEEK_API_KEY exists: {env_key_at_init is not None}, "
            f"Env var length: {len(env_key_at_init) if env_key_at_init else 0}"
        )

    async def summarize(self, title: str, text: str) -> tuple[Optional[str], dict]:
        # Always try to read API key from environment first (for Railway support)
        # Fall back to instance variable if set
        env_key = os.getenv('DEEPSEEK_API_KEY')
        api_key = (env_key or self.api_key or '').strip()
        
        if not api_key:
            logger.warning(
                f"DeepSeek API key not configured. "
                f"Env var exists: {env_key is not None}, "
                f"Env var empty: {env_key == ''}, "
                f"Instance key: {bool(self.api_key)}"
            )
            return None, 0

        text = _truncate_input(text)
        if not text:
            return None, 0

        payload = {
            "model": "deepseek-chat",
            "messages": _build_messages(title, text),
            "temperature": 0.7,
            "max_tokens": 500,
        }

        backoff = 0.8
        for attempt in range(1, 4):
            try:
                async with httpx.AsyncClient(timeout=AI_SUMMARY_TIMEOUT) as client:
                    response = await client.post(
                        self.endpoint,
                        headers={"Authorization": f"Bearer {api_key}"},
                        json=payload,
                    )
                if response.status_code == 200:
                    data = response.json()
                    summary = data["choices"][0]["message"]["content"]
                    usage = data.get("usage", {})
                    
                    # Get separate token counts for accurate pricing
                    input_tokens = int(usage.get("prompt_tokens", 0) or 0)
                    output_tokens = int(usage.get("completion_tokens", 0) or 0)
                    total_tokens = int(usage.get("total_tokens", 0) or 0)
                    
                    if total_tokens == 0:
                        total_tokens = _estimate_tokens(text)
                        input_tokens = total_tokens
                        output_tokens = 0
                    
                    # Return summary and token usage dict
                    token_usage = {
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "total_tokens": total_tokens
                    }
                    return truncate_text(summary.strip(), max_length=800), token_usage

                logger.warning(
                    "DeepSeek API error: status=%s", response.status_code
                )
            except (httpx.TimeoutException, asyncio.TimeoutError):
                logger.warning("DeepSeek API timeout (attempt %s)", attempt)
            except Exception as e:
                logger.error("DeepSeek API error: %s", e)

            await asyncio.sleep(backoff)
            backoff *= 2

        return None, {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    async def verify_category(self, title: str, text: str, current_category: str) -> tuple[Optional[str], dict]:
        """
        Verify and potentially correct news category using AI.
        
        Args:
            title: Article title
            text: Article text (will be truncated)
            current_category: Current category from keyword classifier
            
        Returns:
            Tuple of (verified category name or None, token usage dict)
        """
        token_usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        
        env_key = os.getenv('DEEPSEEK_API_KEY')
        api_key = (env_key or self.api_key or '').strip()
        
        if not api_key:
            logger.debug("DeepSeek API key not configured, skipping AI category verification")
            return None, token_usage

        text = _truncate_input(text, max_chars=1000)
        if not text:
            return None, token_usage

        payload = {
            "model": "deepseek-chat",
            "messages": _build_category_messages(title, text, current_category),
            "temperature": 0.3,  # Lower temperature for more deterministic classification
            "max_tokens": 20,
        }

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:  # Shorter timeout for classification
                response = await client.post(
                    self.endpoint,
                    headers={"Authorization": f"Bearer {api_key}"},
                    json=payload,
                )
            
            if response.status_code == 200:
                data = response.json()
                category = data["choices"][0]["message"]["content"].strip().lower()
                
                # Extract token usage
                usage = data.get("usage", {})
                token_usage = {
                    "input_tokens": usage.get("prompt_tokens", 0),
                    "output_tokens": usage.get("completion_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0)
                }
                
                # Validate response
                valid_categories = ['moscow', 'moscow_region', 'world', 'russia']
                if category in valid_categories:
                    if category != current_category:
                        logger.info(f"AI corrected category: {current_category} -> {category}")
                    return category, token_usage
                else:
                    logger.warning(f"AI returned invalid category: {category}")
                    return None, token_usage
            
            logger.warning(f"DeepSeek category API error: status={response.status_code}")
            
        except Exception as e:
            logger.debug(f"AI category verification failed: {e}")
        
        return None, token_usage
    
    async def extract_clean_text(self, title: str, raw_text: str) -> tuple[Optional[str], dict]:
        """
        Use AI to extract clean article text, removing navigation/garbage.
        
        Args:
            title: Article title
            raw_text: Raw extracted text with possible garbage
            
        Returns:
            Tuple of (clean article text or None, token usage dict)
        """
        token_usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        
        env_key = os.getenv('DEEPSEEK_API_KEY')
        api_key = (env_key or self.api_key or '').strip()
        
        if not api_key:
            logger.debug("DeepSeek API key not configured, skipping AI text extraction")
            return None, token_usage

        if not raw_text or len(raw_text) < 50:
            return None, token_usage

        payload = {
            "model": "deepseek-chat",
            "messages": _build_text_extraction_messages(title, raw_text),
            "temperature": 0.2,  # Low temperature for consistent extraction
            "max_tokens": 500,  # Allow up to 3-4 paragraphs for better context
        }

        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                response = await client.post(
                    self.endpoint,
                    headers={"Authorization": f"Bearer {api_key}"},
                    json=payload,
                )
            
            if response.status_code == 200:
                data = response.json()
                clean_text = data["choices"][0]["message"]["content"].strip()
                
                # Extract token usage
                usage = data.get("usage", {})
                token_usage = {
                    "input_tokens": usage.get("prompt_tokens", 0),
                    "output_tokens": usage.get("completion_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0)
                }
                
                # Validate that we got meaningful text
                if clean_text and len(clean_text) >= 50:
                    logger.debug(f"AI extracted clean text: {len(clean_text)} chars")
                    return clean_text, token_usage
                else:
                    logger.debug("AI extraction returned text too short")
                    return None, token_usage
            
            logger.warning(f"DeepSeek text extraction API error: status={response.status_code}")
            
        except Exception as e:
            logger.debug(f"AI text extraction failed: {e}")
        
        return None, token_usage
