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


class DeepSeekClient:
    def __init__(self, api_key: str = None, endpoint: str = DEEPSEEK_API_ENDPOINT):
        # Don't use config-time DEEPSEEK_API_KEY for parameter default
        # It may be empty during import; we'll read from environment at request time
        self.api_key = api_key if api_key and api_key.strip() else None
        self.endpoint = endpoint

    async def summarize(self, title: str, text: str) -> tuple[Optional[str], int]:
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
                    total_tokens = int(usage.get("total_tokens", 0) or 0)
                    if total_tokens == 0:
                        total_tokens = _estimate_tokens(text)
                    return truncate_text(summary.strip(), max_length=800), total_tokens

                logger.warning(
                    "DeepSeek API error: status=%s", response.status_code
                )
            except (httpx.TimeoutException, asyncio.TimeoutError):
                logger.warning("DeepSeek API timeout (attempt %s)", attempt)
            except Exception as e:
                logger.error("DeepSeek API error: %s", e)

            await asyncio.sleep(backoff)
            backoff *= 2

        return None, 0
