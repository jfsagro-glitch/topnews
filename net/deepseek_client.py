"""
DeepSeek API client for AI summarization.
OPTIMIZED: Uses caching, budget guard, optimized prompts.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import logging
import time
import uuid
from typing import Optional

# Circuit breaker: after N consecutive failures, open for cooldown; no retries when open
CB_FAILURE_THRESHOLD = int(os.getenv("AI_CIRCUIT_FAILURE_THRESHOLD", "3"))
CB_COOLDOWN_SEC = int(os.getenv("AI_CIRCUIT_COOLDOWN_SEC", "300"))
CB_MAX_RETRIES = 2

import httpx

from core.services.collection_stop import get_global_collection_stop_state

from config.config import (
    DEEPSEEK_API_ENDPOINT,
    AI_SUMMARY_TIMEOUT,
    AI_MAX_INPUT_CHARS,
    AI_MAX_INPUT_CHARS_HASHTAGS,
    AI_SUMMARY_MIN_CHARS,
    DEEPSEEK_INPUT_COST_PER_1K_TOKENS_USD,
    DEEPSEEK_OUTPUT_COST_PER_1K_TOKENS_USD,
)
from config.config import SUMMARY_MIN_CHARS
from utils.text_cleaner import clean_html, truncate_text

logger = logging.getLogger(__name__)

HASHTAG_PROMPT_VERSION = 3

COMMON_HASHTAGS_RU = {
    "#мир", "#россия", "#москва", "#подмосковье", "#новости", "#политика",
    "#экономика", "#общество", "#спорт", "#культура",
}
COMMON_HASHTAGS_EN = {
    "#world", "#russia", "#moscow", "#news", "#politics", "#economy",
    "#society", "#sports", "#culture",
}


def compact_text(text: str, max_chars: int, strategy: str = "start_mid_end") -> str:
    if not text:
        return ""
    cleaned = clean_html(text) if "<" in text and ">" in text else text
    if len(cleaned) <= max_chars:
        return cleaned
    if strategy != "start_mid_end":
        if max_chars <= 0:
            return ""
        safe = max(0, int(max_chars) - 3)
        if safe <= 0:
            return "..."[: max(0, int(max_chars))]
        return truncate_text(cleaned, max_length=safe)

    if max_chars <= 0:
        return ""
    sep_len = len("\n...\n") * 2  # head->mid and mid->tail
    chunk = max(1, (int(max_chars) - sep_len) // 3)

    while True:
        head = cleaned[:chunk]
        tail = cleaned[-chunk:]
        middle_start = max(0, (len(cleaned) // 2) - (chunk // 2))
        middle = cleaned[middle_start:middle_start + chunk]
        joined = f"{head}\n...\n{middle}\n...\n{tail}"
        if len(joined) <= max_chars or chunk <= 1:
            break
        chunk -= 1

    if len(joined) <= max_chars:
        return joined

    safe = max(0, int(max_chars) - 3)
    if safe <= 0:
        return "..."[: max(0, int(max_chars))]
    return truncate_text(cleaned, max_length=safe)


def _fingerprint(text: str) -> str:
    """Stable hash of text for cache key normalization (better hit rate)."""
    t = (text or "").strip().encode("utf-8", "ignore")
    return hashlib.sha256(t).hexdigest()


def _estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // 4)


def _build_messages(title: str, text: str) -> list[dict]:
    system_prompt = (
        "Кратко перескажи новость для радионовостей. "
        "Только факты из текста, без домыслов. "
        "1-2 абзаца, предложения до 12 слов. "
        "В конце укажи источник текстом."
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
        "Извлеки только основной текст новости. "
        "Удали меню, списки, рекламу, ссылки и дубли заголовка. "
        "Верни 1-2 абзаца фактов без пояснений."
    )
    user_content = f"Заголовок: {title}\n\nИзвлеченный текст:\n{raw_text}"
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]


def _build_hashtags_messages(title: str, text: str, language: str, candidates: list[str]) -> list[dict]:
    system_prompt = (
        "Верни СТРОГО JSON объект {\"hashtags\":[\"#...\",...]}. "
        "Без текста вне JSON. Выбери 6-8 тегов из кандидатов, "
        "язык хештегов: {lang}."
    )
    candidates_block = ", ".join(candidates[:20]) if candidates else ""
    user_content = (
        f"Заголовок: {title}\n\n"
        f"Текст: {text}\n\n"
        f"Кандидаты: {candidates_block}"
    )
    return [
        {"role": "system", "content": system_prompt.format(lang=language)},
        {"role": "user", "content": user_content},
    ]


def _build_hashtags_classify_messages(
    title: str,
    text: str,
    allowed: dict,
    detected: dict,
) -> list[dict]:
    allowed_lines = [
        f"g0: {', '.join(allowed.get('g0', []))}",
        f"g1: {', '.join(allowed.get('g1', []))}",
        f"g2: {', '.join(allowed.get('g2', []))}",
        f"g3: {', '.join(allowed.get('g3', []))}",
        f"r0: {', '.join(allowed.get('r0', []))}",
    ]
    detected_lines = [
        f"g0: {detected.get('g0')}",
        f"g1: {detected.get('g1')}",
        f"g2: {detected.get('g2')}",
        f"g3: {detected.get('g3')}",
        f"r0: {detected.get('r0')}",
    ]
    system_prompt = (
        "Верни ТОЛЬКО JSON объект вида "
        "{\"g0\":\"#Россия|#Мир\",\"g1\":\"#ЦФО|...|null\"," 
        "\"g2\":\"#...|null\",\"g3\":\"#...|null\",\"r0\":\"#Политика|...\"}. "
        "Значения только из allow-list или null. "
        "Если g0 = #Мир, то g1/g2/g3 должны быть null."
    )
    user_content = (
        f"Заголовок: {title}\n\n"
        f"Текст: {text}\n\n"
        "Allow-list:\n"
        + "\n".join(allowed_lines)
        + "\n\nDetected:\n"
        + "\n".join(detected_lines)
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]


def _parse_hashtags_json(raw: str) -> tuple[list[str], bool]:
    import json

    if not raw:
        return [], False
    raw = raw.strip()
    try:
        data = json.loads(raw)
    except Exception:
        return [], False

    if isinstance(data, dict):
        data = data.get("hashtags")

    if not isinstance(data, list):
        return [], False
    tags = []
    for item in data:
        if not isinstance(item, str):
            continue
        tag = item.strip()
        if not tag:
            continue
        if not tag.startswith("#"):
            tag = "#" + tag
        if tag not in tags:
            tags.append(tag)
    return tags, True


def _parse_hashtags_classification(raw: str) -> tuple[dict, bool]:
    import json

    if not raw:
        return {}, False
    raw = raw.strip()
    try:
        data = json.loads(raw)
    except Exception:
        return {}, False

    if not isinstance(data, dict):
        return {}, False
    return data, True


def _is_only_common_tags(tags: list[str], language: str) -> bool:
    common = COMMON_HASHTAGS_RU if language == "ru" else COMMON_HASHTAGS_EN
    filtered = [t.lower() for t in tags if t]
    return bool(filtered) and all(t in common for t in filtered)


class DeepSeekClient:
    def __init__(self, api_key: str = None, endpoint: str = DEEPSEEK_API_ENDPOINT, db=None):
        self.api_key = api_key if api_key and api_key.strip() else None
        self.endpoint = endpoint
        self.db = db
        
        # Initialize cache and budget managers if DB provided
        self.cache = None
        self.budget = None
        if db:
            try:
                from net.llm_cache import LLMCacheManager
                from core.services.ai_budget import AIBudgetManager
                self.cache = LLMCacheManager(db)
                self.budget = AIBudgetManager(db)
                logger.info("LLM cache and budget guard enabled")
            except Exception as e:
                logger.warning(f"Failed to initialize LLM cache/budget: {e}")
        
        self._cb_failures = 0
        self._cb_open_until = 0.0

        env_key_at_init = os.getenv('DEEPSEEK_API_KEY')
        logger.info(
            f"DeepSeekClient initialized. "
            f"Env DEEPSEEK_API_KEY exists: {env_key_at_init is not None}, "
            f"Env var length: {len(env_key_at_init) if env_key_at_init else 0}, "
            f"Cache: {self.cache is not None}, Budget guard: {self.budget is not None}"
        )

    def _circuit_open(self) -> bool:
        if self._cb_open_until <= 0:
            return False
        if time.time() < self._cb_open_until:
            return True
        self._cb_open_until = 0.0
        self._cb_failures = 0
        return False

    def _record_success(self) -> None:
        self._cb_failures = 0

    def _record_failure(self) -> None:
        self._cb_failures = (self._cb_failures or 0) + 1
        if self._cb_failures >= CB_FAILURE_THRESHOLD:
            self._cb_open_until = time.time() + CB_COOLDOWN_SEC
            logger.warning(f"AI circuit breaker OPEN for {CB_COOLDOWN_SEC}s (failures={self._cb_failures})")

    def get_circuit_state(self) -> dict:
        open_ = self._cb_open_until > 0 and time.time() < self._cb_open_until
        return {"open": open_, "failures": self._cb_failures or 0, "open_until_ts": self._cb_open_until}

    async def summarize(self, title: str, text: str, level: int = 3, checksum: str | None = None) -> tuple[Optional[str], dict]:
        request_id = str(uuid.uuid4())[:8]

        if get_global_collection_stop_state().enabled:
            return None, {
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "cache_hit": False,
                "skipped_by_global_stop": True,
            }

        # Length gate: skip summary for short items (saves tokens, minimal quality impact)
        if text and len(text.strip()) < SUMMARY_MIN_CHARS:
            return None, {
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "cache_hit": False,
                "too_short": True,
            }
        
        # Check if AI level is 0 (disabled) - only in sandbox
        from config.config import APP_ENV
        if APP_ENV == 'sandbox' and level == 0:
            logger.info(f"[{request_id}] AI summary disabled (level=0)")
            return None, {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "cache_hit": False, "disabled": True}
        
        # Get LLM profile for level (always default to 3 in prod)
        from core.services.access_control import get_llm_profile
        if APP_ENV == 'sandbox':
            profile = get_llm_profile(level, 'summary')
            logger.debug(f"[{request_id}] Using AI level {level}: {profile.get('description', 'N/A')}")
        else:
            # Prod uses default level 3
            profile = get_llm_profile(3, 'summary')
            logger.debug(f"[{request_id}] Prod mode: Using default level 3")
        
        # Always try to read API key from environment first (for Railway support)
        env_key = os.getenv('DEEPSEEK_API_KEY')
        api_key = (env_key or self.api_key or '').strip()
        
        if not api_key:
            logger.error(
                f"[{request_id}] DeepSeek API key not configured! "
                f"Env DEEPSEEK_API_KEY exists: {env_key is not None}, "
                f"Env var empty: {env_key == ''}, "
                f"Instance key set: {bool(self.api_key)}. "
                f"Please add DEEPSEEK_API_KEY to environment variables."
            )
            return None, {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "cache_hit": False}

        cleaned = compact_text(text, AI_MAX_INPUT_CHARS)
        if not cleaned:
            return None, {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "cache_hit": False}
        if len(cleaned) < AI_SUMMARY_MIN_CHARS:
            return None, {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "cache_hit": False, "too_short": True}

        # Cache key by fingerprint of compacted text for better hit rate
        fp = _fingerprint(cleaned)
        cache_checksum = checksum if checksum else fp

        # Check cache
        if self.cache:
            cache_key = self.cache.generate_cache_key('summarize', title, cleaned, level=level, checksum=cache_checksum)
            cached = self.cache.get(cache_key)
            if cached:
                logger.info(f"[{request_id}] Cache HIT for summarize")
                if self.budget:
                    self.budget.record_usage(tokens_in=0, tokens_out=0, cost_usd=0.0, calls=1, cache_hit=True)
                return cached['response'], {
                    "input_tokens": cached['input_tokens'],
                    "output_tokens": cached['output_tokens'],
                    "total_tokens": cached['input_tokens'] + cached['output_tokens'],
                    "cache_hit": True
                }

        if self._circuit_open():
            return None, {
                "input_tokens": 0, "output_tokens": 0, "total_tokens": 0,
                "cache_hit": False, "circuit_open": True,
            }

        estimated_tokens = _estimate_tokens(cleaned)
        if self.budget and not self.budget.budget_ok("summary", estimated_tokens=estimated_tokens):
            logger.warning(f"[{request_id}] Daily budget exceeded, skipping LLM call")
            return None, {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "cache_hit": False, "budget_exceeded": True}

        payload = {
            "model": profile.get('model', 'deepseek-chat'),
            "messages": _build_messages(title, cleaned),
            "temperature": profile.get('temperature', 0.7),
            "max_tokens": profile.get('max_tokens', 800),
        }
        
        # Add optional parameters
        if 'top_p' in profile:
            payload['top_p'] = profile['top_p']
        
        logger.info(f"[{request_id}] API call: summarize (level={level}, max_tokens={payload['max_tokens']})")

        backoff = 0.8
        for attempt in range(1, CB_MAX_RETRIES + 1):
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
                        total_tokens = _estimate_tokens(cleaned)
                        input_tokens = total_tokens
                        output_tokens = 0
                    
                    # Calculate cost and update budget
                    cost_usd = (input_tokens * DEEPSEEK_INPUT_COST_PER_1K_TOKENS_USD / 1000 +
                                output_tokens * DEEPSEEK_OUTPUT_COST_PER_1K_TOKENS_USD / 1000)
                    
                    if self.budget:
                        self.budget.record_usage(
                            tokens_in=input_tokens,
                            tokens_out=output_tokens,
                            cost_usd=cost_usd,
                            calls=1,
                            cache_hit=False,
                        )
                    
                    logger.info(f"[{request_id}] summarize: {input_tokens}+{output_tokens}={total_tokens} tokens, ${cost_usd:.4f}")
                    
                    # Store in cache
                    result_text = truncate_text(summary.strip(), max_length=800)
                    if self.cache:
                        cache_key = self.cache.generate_cache_key('summarize', title, cleaned, level=level, checksum=cache_checksum)
                        self.cache.set(cache_key, 'summarize', result_text, input_tokens, output_tokens, ttl_hours=72)
                    
                    self._record_success()
                    token_usage = {
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "total_tokens": total_tokens,
                        "cache_hit": False,
                        "cost_usd": cost_usd
                    }
                    return result_text, token_usage

                try:
                    error_data = response.json()
                    error_msg = error_data.get('error', {}).get('message', response.text[:500])
                    logger.error(
                        f"DeepSeek API error: status={response.status_code}, "
                        f"error={error_msg}, attempt={attempt}/3"
                    )
                except:
                    logger.error(
                        f"DeepSeek API error: status={response.status_code}, "
                        f"response={response.text[:500]}, attempt={attempt}/3"
                    )
            except (httpx.TimeoutException, asyncio.TimeoutError):
                logger.warning(f"DeepSeek API timeout (attempt {attempt}/3)")
            except Exception as e:
                logger.error(f"DeepSeek API exception (attempt {attempt}/3): {e}")

            await asyncio.sleep(backoff)
            backoff *= 2

        self._record_failure()
        return None, {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    async def translate_text(self, text: str, target_lang: str = 'ru', checksum: str | None = None) -> tuple[Optional[str], dict]:
        """Translate text to target language using DeepSeek."""
        token_usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

        if get_global_collection_stop_state().enabled:
            return None, {**token_usage, "skipped_by_global_stop": True}

        if not text:
            return None, token_usage

        if self.cache:
            cache_key = self.cache.generate_cache_key('translate', '', text, target_lang=target_lang, checksum=checksum)
            cached = self.cache.get(cache_key)
            if cached:
                if self.budget:
                    self.budget.record_usage(tokens_in=0, tokens_out=0, cost_usd=0.0, calls=1, cache_hit=True)
                return cached['response'], {
                    "input_tokens": cached['input_tokens'],
                    "output_tokens": cached['output_tokens'],
                    "total_tokens": cached['input_tokens'] + cached['output_tokens'],
                    "cache_hit": True,
                }
        if self.budget and not self.budget.budget_ok("translate", estimated_tokens=_estimate_tokens(text)):
            return None, token_usage

        if self._circuit_open():
            return None, {**token_usage, "circuit_open": True}

        env_key = os.getenv('DEEPSEEK_API_KEY')
        api_key = (env_key or self.api_key or '').strip()
        if not api_key:
            return None, token_usage

        system_prompt = (
            "Переведи текст на целевой язык. "
            "Сохраняй факты, имена и числа. "
            "Не добавляй пояснений и комментариев."
        )
        payload = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Язык: {target_lang}\n\n{text}"},
            ],
            "temperature": 0.2,
            "max_tokens": 800,
        }

        try:
            async with httpx.AsyncClient(timeout=AI_SUMMARY_TIMEOUT) as client:
                response = await client.post(
                    self.endpoint,
                    headers={"Authorization": f"Bearer {api_key}"},
                    json=payload,
                )
            if response.status_code == 200:
                data = response.json()
                translated = data["choices"][0]["message"]["content"].strip()
                usage = data.get("usage", {})
                input_tokens = int(usage.get("prompt_tokens", 0) or 0)
                output_tokens = int(usage.get("completion_tokens", 0) or 0)
                total_tokens = int(usage.get("total_tokens", 0) or 0)
                if total_tokens == 0:
                    total_tokens = _estimate_tokens(text)
                    input_tokens = total_tokens
                    output_tokens = 0

                cost_usd = (input_tokens * DEEPSEEK_INPUT_COST_PER_1K_TOKENS_USD / 1000 +
                            output_tokens * DEEPSEEK_OUTPUT_COST_PER_1K_TOKENS_USD / 1000)
                if self.budget:
                    self.budget.record_usage(
                        tokens_in=input_tokens,
                        tokens_out=output_tokens,
                        cost_usd=cost_usd,
                        calls=1,
                        cache_hit=False,
                    )

                if self.cache:
                    cache_key = self.cache.generate_cache_key('translate', '', text, target_lang=target_lang, checksum=checksum)
                    self.cache.set(cache_key, 'translate', translated, input_tokens, output_tokens, ttl_hours=72)

                self._record_success()
                return translated, {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": total_tokens,
                    "cache_hit": False,
                    "cost_usd": cost_usd,
                }

        except Exception as e:
            logger.debug(f"Translate failed: {e}")

        self._record_failure()
        return None, token_usage

    async def generate_hashtags(
        self,
        title: str,
        text: str,
        language: str = 'ru',
        level: int = 3,
        checksum: str | None = None,
        candidates: list[str] | None = None,
    ) -> tuple[list[str], dict]:
        """Generate hashtags as JSON array for the given language."""
        token_usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

        if get_global_collection_stop_state().enabled:
            return [], {**token_usage, "skipped_by_global_stop": True}

        if not text or not title:
            return [], token_usage

        text = compact_text(text, AI_MAX_INPUT_CHARS_HASHTAGS)

        candidates = candidates or []
        candidates_key = ",".join(candidates[:20])

        if self.cache:
            cache_key = self.cache.generate_cache_key(
                'hashtags',
                title,
                text,
                language=language,
                level=level,
                checksum=checksum,
                prompt_version=HASHTAG_PROMPT_VERSION,
                candidates=candidates_key
            )
            cached = self.cache.get(cache_key)
            if cached:
                if self.budget:
                    self.budget.record_usage(tokens_in=0, tokens_out=0, cost_usd=0.0, calls=1, cache_hit=True)
                return cached['response'], {
                    "input_tokens": cached['input_tokens'],
                    "output_tokens": cached['output_tokens'],
                    "total_tokens": cached['input_tokens'] + cached['output_tokens'],
                    "cache_hit": True,
                }
        if self.budget and not self.budget.budget_ok("hashtags_ai", estimated_tokens=_estimate_tokens(text)):
            return [], token_usage

        if self._circuit_open():
            return [], {**token_usage, "circuit_open": True}

        env_key = os.getenv('DEEPSEEK_API_KEY')
        api_key = (env_key or self.api_key or '').strip()
        if not api_key:
            return [], token_usage

        from core.services.access_control import get_llm_profile
        profile = get_llm_profile(level, 'hashtags')
        if profile.get('disabled'):
            return [], token_usage

        max_tokens = min(int(profile.get('max_tokens', 120) or 120), 120)
        temperature = min(float(profile.get('temperature', 0.2) or 0.2), 0.3)

        payload = {
            "model": profile.get('model', 'deepseek-chat'),
            "messages": _build_hashtags_messages(title, text, language, candidates),
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if 'top_p' in profile:
            payload['top_p'] = profile['top_p']

        try:
            async with httpx.AsyncClient(timeout=AI_SUMMARY_TIMEOUT) as client:
                response = await client.post(
                    self.endpoint,
                    headers={"Authorization": f"Bearer {api_key}"},
                    json=payload,
                )
            if response.status_code == 200:
                data = response.json()
                raw = data["choices"][0]["message"]["content"]
                tags, valid = _parse_hashtags_json(raw)

                if not valid or not tags:
                    repair_payload = {
                        "model": profile.get('model', 'deepseek-chat'),
                        "messages": [
                            {
                                "role": "system",
                                "content": (
                                    "Исправь ответ и верни СТРОГО JSON объект вида "
                                    "{\"hashtags\":[\"#...\",...]}. Без текста вне JSON."
                                )
                            },
                            {"role": "user", "content": raw or ""},
                        ],
                        "temperature": 0.0,
                        "max_tokens": max_tokens,
                    }
                    if 'top_p' in profile:
                        repair_payload['top_p'] = profile['top_p']
                    repair = await client.post(
                        self.endpoint,
                        headers={"Authorization": f"Bearer {api_key}"},
                        json=repair_payload,
                    )
                    if repair.status_code == 200:
                        repaired = repair.json()["choices"][0]["message"]["content"]
                        tags, _ = _parse_hashtags_json(repaired)

                if _is_only_common_tags(tags, language) and len(text) > 300:
                    if candidates:
                        added = 0
                        for candidate in candidates:
                            tag = candidate.strip()
                            if not tag:
                                continue
                            if not tag.startswith("#"):
                                tag = "#" + tag
                            if tag not in tags:
                                tags.append(tag)
                                added += 1
                            if len(tags) >= 8 or added >= 3:
                                break

                if len(tags) > 8:
                    tags = tags[:8]

                usage = data.get("usage", {})
                input_tokens = int(usage.get("prompt_tokens", 0) or 0)
                output_tokens = int(usage.get("completion_tokens", 0) or 0)
                total_tokens = int(usage.get("total_tokens", 0) or 0)
                if total_tokens == 0:
                    total_tokens = _estimate_tokens(text)
                    input_tokens = total_tokens
                    output_tokens = 0

                cost_usd = (input_tokens * DEEPSEEK_INPUT_COST_PER_1K_TOKENS_USD / 1000 +
                            output_tokens * DEEPSEEK_OUTPUT_COST_PER_1K_TOKENS_USD / 1000)
                if self.budget:
                    self.budget.record_usage(
                        tokens_in=input_tokens,
                        tokens_out=output_tokens,
                        cost_usd=cost_usd,
                        calls=1,
                        cache_hit=False,
                    )

                if self.cache:
                    cache_key = self.cache.generate_cache_key(
                        'hashtags',
                        title,
                        text,
                        language=language,
                        level=level,
                        checksum=checksum,
                        prompt_version=HASHTAG_PROMPT_VERSION,
                        candidates=candidates_key
                    )
                    self.cache.set(cache_key, 'hashtags', tags, input_tokens, output_tokens, ttl_hours=72)

                self._record_success()
                return tags, {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": total_tokens,
                    "cache_hit": False,
                    "cost_usd": cost_usd,
                }
        except Exception as e:
            logger.debug(f"Hashtags failed: {e}")

        self._record_failure()
        return [], token_usage

    async def classify_hashtags(
        self,
        title: str,
        text: str,
        allowed_taxonomy: dict,
        detected: dict,
        level: int = 1,
    ) -> tuple[dict, dict]:
        """Classify hashtags using a fixed taxonomy. Returns dict with g0/g1/g2/g3/r0."""
        token_usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

        if get_global_collection_stop_state().enabled:
            return {}, {**token_usage, "skipped_by_global_stop": True}

        if not text and not title:
            return {}, token_usage

        text = compact_text(text, AI_MAX_INPUT_CHARS_HASHTAGS)
        if not text and not title:
            return {}, token_usage

        taxonomy_fp = hashlib.md5(
            json.dumps(allowed_taxonomy or {}, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        detected_fp = hashlib.md5(
            json.dumps(detected or {}, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()

        if self.cache:
            cache_key = self.cache.generate_cache_key(
                'hashtags_classify',
                title,
                text,
                level=level,
                taxonomy=taxonomy_fp,
                detected=detected_fp,
            )
            cached = self.cache.get(cache_key)
            if cached:
                if self.budget:
                    self.budget.record_usage(tokens_in=0, tokens_out=0, cost_usd=0.0, calls=1, cache_hit=True)
                return cached['response'], {
                    "input_tokens": cached['input_tokens'],
                    "output_tokens": cached['output_tokens'],
                    "total_tokens": (cached['input_tokens'] or 0) + (cached['output_tokens'] or 0),
                    "cache_hit": True,
                }

        if self.budget and not self.budget.budget_ok("hashtags_ai", estimated_tokens=_estimate_tokens(text)):
            return {}, token_usage

        if self._circuit_open():
            return {}, {**token_usage, "circuit_open": True}

        env_key = os.getenv('DEEPSEEK_API_KEY')
        api_key = (env_key or self.api_key or '').strip()
        if not api_key:
            return {}, token_usage

        from core.services.access_control import get_llm_profile
        profile = get_llm_profile(level, 'hashtags')
        if profile.get('disabled'):
            return {}, token_usage

        payload = {
            "model": profile.get('model', 'deepseek-chat'),
            "messages": _build_hashtags_classify_messages(title, text, allowed_taxonomy, detected),
            "temperature": 0.0,
            "max_tokens": min(int(profile.get('max_tokens', 120) or 120), 120),
        }
        if 'top_p' in profile:
            payload['top_p'] = profile['top_p']

        try:
            async with httpx.AsyncClient(timeout=AI_SUMMARY_TIMEOUT) as client:
                response = await client.post(
                    self.endpoint,
                    headers={"Authorization": f"Bearer {api_key}"},
                    json=payload,
                )
            if response.status_code == 200:
                data = response.json()
                raw = data["choices"][0]["message"]["content"]
                result, valid = _parse_hashtags_classification(raw)
                if not valid:
                    return {}, token_usage

                usage = data.get("usage", {})
                token_usage = {
                    "input_tokens": int(usage.get("prompt_tokens", 0) or 0),
                    "output_tokens": int(usage.get("completion_tokens", 0) or 0),
                    "total_tokens": int(usage.get("total_tokens", 0) or 0),
                }
                if self.budget:
                    cost_usd = (
                        token_usage["input_tokens"] * DEEPSEEK_INPUT_COST_PER_1K_TOKENS_USD / 1000
                        + token_usage["output_tokens"] * DEEPSEEK_OUTPUT_COST_PER_1K_TOKENS_USD / 1000
                    )
                    self.budget.record_usage(
                        tokens_in=token_usage["input_tokens"],
                        tokens_out=token_usage["output_tokens"],
                        cost_usd=cost_usd,
                        calls=1,
                        cache_hit=False,
                    )

                if self.cache:
                    cache_key = self.cache.generate_cache_key(
                        'hashtags_classify',
                        title,
                        text,
                        level=level,
                        taxonomy=taxonomy_fp,
                        detected=detected_fp,
                    )
                    self.cache.set(
                        cache_key,
                        'hashtags_classify',
                        result,
                        token_usage["input_tokens"],
                        token_usage["output_tokens"],
                        ttl_hours=72,
                    )
                self._record_success()
                return result, token_usage
        except Exception as e:
            logger.debug(f"Hashtag classification failed: {e}")

        self._record_failure()
        return {}, token_usage

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

        if get_global_collection_stop_state().enabled:
            return None, {**token_usage, "skipped_by_global_stop": True}
        
        env_key = os.getenv('DEEPSEEK_API_KEY')
        api_key = (env_key or self.api_key or '').strip()
        
        if not api_key:
            logger.debug("DeepSeek API key not configured, skipping AI category verification")
            return None, token_usage

        text = compact_text(text, 1000)
        if not text:
            return None, token_usage

        if self.cache:
            cache_key = self.cache.generate_cache_key(
                'category_verify',
                title,
                text,
                current_category=current_category,
            )
            cached = self.cache.get(cache_key)
            if cached:
                if self.budget:
                    self.budget.record_usage(tokens_in=0, tokens_out=0, cost_usd=0.0, calls=1, cache_hit=True)
                return cached['response'], {
                    "input_tokens": cached['input_tokens'],
                    "output_tokens": cached['output_tokens'],
                    "total_tokens": (cached['input_tokens'] or 0) + (cached['output_tokens'] or 0),
                    "cache_hit": True,
                }

        if self.budget and not self.budget.budget_ok("category", estimated_tokens=_estimate_tokens(text)):
            return None, token_usage

        if self._circuit_open():
            return None, {**token_usage, "circuit_open": True}

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
                if self.budget:
                    cost_usd = (
                        token_usage["input_tokens"] * DEEPSEEK_INPUT_COST_PER_1K_TOKENS_USD / 1000
                        + token_usage["output_tokens"] * DEEPSEEK_OUTPUT_COST_PER_1K_TOKENS_USD / 1000
                    )
                    self.budget.record_usage(
                        tokens_in=token_usage["input_tokens"],
                        tokens_out=token_usage["output_tokens"],
                        cost_usd=cost_usd,
                        calls=1,
                        cache_hit=False,
                    )
                
                # Validate response
                valid_categories = ['moscow', 'moscow_region', 'world', 'russia']
                if category in valid_categories:
                    if category != current_category:
                        logger.info(f"AI corrected category: {current_category} -> {category}")
                    if self.cache:
                        cache_key = self.cache.generate_cache_key(
                            'category_verify',
                            title,
                            text,
                            current_category=current_category,
                        )
                        self.cache.set(cache_key, 'category_verify', category, token_usage["input_tokens"], token_usage["output_tokens"], ttl_hours=72)
                    self._record_success()
                    return category, token_usage
                else:
                    logger.warning(f"AI returned invalid category: {category}")
                    return None, token_usage
            
            logger.warning(f"DeepSeek category API error: status={response.status_code}")
            
        except Exception as e:
            logger.debug(f"AI category verification failed: {e}")
        
        self._record_failure()
        return None, token_usage
    
    async def extract_clean_text(self, title: str, raw_text: str, level: int = 3) -> tuple[Optional[str], dict]:
        """
        Use AI to extract clean article text, removing navigation/garbage.
        
        Args:
            title: Article title
            raw_text: Raw extracted text with possible garbage
            
        Returns:
            Tuple of (clean article text or None, token usage dict)
        """
        token_usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

        if get_global_collection_stop_state().enabled:
            return None, {**token_usage, "skipped_by_global_stop": True}
        
        env_key = os.getenv('DEEPSEEK_API_KEY')
        api_key = (env_key or self.api_key or '').strip()
        
        if not api_key:
            logger.debug("DeepSeek API key not configured, skipping AI text extraction")
            return None, token_usage

        if not raw_text or len(raw_text) < 50:
            return None, token_usage

        # Sandbox: apply cleanup profile
        try:
            from config.railway_config import APP_ENV
        except (ImportError, ValueError):
            from config.config import APP_ENV
        from core.services.access_control import get_llm_profile

        if APP_ENV == "sandbox" and level == 0:
            return None, token_usage

        profile = get_llm_profile(level if APP_ENV == "sandbox" else 3, 'cleanup')

        raw_text = compact_text(raw_text, AI_MAX_INPUT_CHARS)
        if not raw_text:
            return None, token_usage

        model_name = profile.get('model', 'deepseek-chat')
        effective_level = level if APP_ENV == "sandbox" else 3
        if self.cache:
            cache_key = self.cache.generate_cache_key(
                'extract_clean_text',
                title,
                raw_text,
                level=effective_level,
                model=model_name,
            )
            cached = self.cache.get(cache_key)
            if cached:
                if self.budget:
                    self.budget.record_usage(tokens_in=0, tokens_out=0, cost_usd=0.0, calls=1, cache_hit=True)
                return cached['response'], {
                    "input_tokens": cached['input_tokens'],
                    "output_tokens": cached['output_tokens'],
                    "total_tokens": (cached['input_tokens'] or 0) + (cached['output_tokens'] or 0),
                    "cache_hit": True,
                }

        if self.budget and not self.budget.budget_ok("cleanup", estimated_tokens=_estimate_tokens(raw_text)):
            return None, token_usage

        if self._circuit_open():
            return None, {**token_usage, "circuit_open": True}

        payload = {
            "model": model_name,
            "messages": _build_text_extraction_messages(title, raw_text),
            "temperature": profile.get('temperature', 0.2),
            "max_tokens": profile.get('max_tokens', 500),
        }
        if 'top_p' in profile:
            payload['top_p'] = profile['top_p']

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
                if self.budget:
                    cost_usd = (
                        token_usage["input_tokens"] * DEEPSEEK_INPUT_COST_PER_1K_TOKENS_USD / 1000
                        + token_usage["output_tokens"] * DEEPSEEK_OUTPUT_COST_PER_1K_TOKENS_USD / 1000
                    )
                    self.budget.record_usage(
                        tokens_in=token_usage["input_tokens"],
                        tokens_out=token_usage["output_tokens"],
                        cost_usd=cost_usd,
                        calls=1,
                        cache_hit=False,
                    )
                
                # Validate that we got meaningful text
                if clean_text and len(clean_text) >= 50:
                    logger.debug(f"AI extracted clean text: {len(clean_text)} chars")
                    if self.cache:
                        cache_key = self.cache.generate_cache_key(
                            'extract_clean_text',
                            title,
                            raw_text,
                            level=effective_level,
                            model=model_name,
                        )
                        self.cache.set(
                            cache_key,
                            'extract_clean_text',
                            clean_text,
                            token_usage["input_tokens"],
                            token_usage["output_tokens"],
                            ttl_hours=72,
                        )
                    self._record_success()
                    return clean_text, token_usage
                else:
                    logger.debug("AI extraction returned text too short")
                    return None, token_usage
            
            logger.warning(f"DeepSeek text extraction API error: status={response.status_code}")
            
        except Exception as e:
            logger.debug(f"AI text extraction failed: {e}")
        
        self._record_failure()
        return None, token_usage
