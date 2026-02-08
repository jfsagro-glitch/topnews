"""
DeepSeek API client for AI summarization.
OPTIMIZED: Uses caching, budget guard, optimized prompts.
"""
from __future__ import annotations

import asyncio
import os
import logging
import uuid
from typing import Optional

import httpx

from config.config import (
    DEEPSEEK_API_ENDPOINT, 
    AI_SUMMARY_TIMEOUT,
    DEEPSEEK_INPUT_COST_PER_1K_TOKENS_USD,
    DEEPSEEK_OUTPUT_COST_PER_1K_TOKENS_USD
)
from utils.text_cleaner import truncate_text

logger = logging.getLogger(__name__)

MAX_INPUT_CHARS = 3500
HASHTAG_PROMPT_VERSION = 2

COMMON_HASHTAGS_RU = {
    "#мир", "#россия", "#москва", "#подмосковье", "#новости", "#политика",
    "#экономика", "#общество", "#спорт", "#культура",
}
COMMON_HASHTAGS_EN = {
    "#world", "#russia", "#moscow", "#news", "#politics", "#economy",
    "#society", "#sports", "#culture",
}


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
    # Ты — редактор радионовостей (полный промпт с гарантией качества)
    system_prompt = (
        "Ты — редактор радионовостей.\n\n"
        "Перепиши новость, строго соблюдая правила:\n"
        "1. Начни с одной короткой фразы до 7 слов, передающей суть\n"
        "2. Используй только информацию из исходного текста\n"
        "3. Ничего не додумывай и не добавляй от себя\n"
        "4. Удали повторы, ссылки и второстепенные детали\n"
        "5. Объём: 100–150 слов (30–40 секунд при чтении вслух)\n"
        "6. Каждое предложение — не длиннее 12 слов\n"
        "7. Предложения должны легко произноситься вслух\n"
        "8. Не используй деепричастия, причастия и пассивный залог\n"
        "9. Не используй канцеляризмы и формализмы\n"
        "10. Стиль — сухой, информационный, радионовости\n"
        "11. Не используй оценку. Только факты\n"
        "12. Прямые цитаты, если есть, приводи дословно в кавычках\n"
        "13. В конце укажи источник текстом (без ссылки)\n\n"
        "Если информации недостаточно — сделай максимально краткий пересказ без домыслов."
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


def _build_hashtags_messages(title: str, text: str, language: str, candidates: list[str]) -> list[dict]:
    system_prompt = (
        "Ты выбираешь лучшие хештеги для новости. "
        "Верни СТРОГО JSON объект вида {\"hashtags\":[\"#...\",...]}. "
        "Без комментариев и без текста вне JSON. "
        "Выбери 6-8 тегов, избегай общих и пустых тегов. "
        "Если текст длинный, обязательно включи 2-3 конкретных сущности, "
        "предпочтительно из списка кандидатов. "
        "Язык хештегов: {lang}."
    )
    candidates_block = ", ".join(candidates[:20]) if candidates else ""
    user_content = (
        f"Заголовок: {title}\n\n"
        f"Текст: {text[:1800]}\n\n"
        f"Кандидаты: {candidates_block}"
    )
    return [
        {"role": "system", "content": system_prompt.format(lang=language)},
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
                from net.llm_cache import LLMCacheManager, BudgetGuard
                self.cache = LLMCacheManager(db)
                self.budget = BudgetGuard(db, daily_limit_usd=float(os.getenv('DAILY_LLM_BUDGET_USD', '1.0')))
                logger.info("LLM cache and budget guard enabled")
            except Exception as e:
                logger.warning(f"Failed to initialize LLM cache/budget: {e}")
        
        env_key_at_init = os.getenv('DEEPSEEK_API_KEY')
        logger.info(
            f"DeepSeekClient initialized. "
            f"Env DEEPSEEK_API_KEY exists: {env_key_at_init is not None}, "
            f"Env var length: {len(env_key_at_init) if env_key_at_init else 0}, "
            f"Cache: {self.cache is not None}, Budget guard: {self.budget is not None}"
        )

    async def summarize(self, title: str, text: str, level: int = 3, checksum: str | None = None) -> tuple[Optional[str], dict]:
        request_id = str(uuid.uuid4())[:8]
        
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
        
        # Check budget limit
        if self.budget and not self.budget.can_make_request():
            logger.warning(f"[{request_id}] Daily budget exceeded, skipping LLM call")
            return None, {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "cache_hit": False, "budget_exceeded": True}
        
        # Check cache
        if self.cache:
            cache_key = self.cache.generate_cache_key('summarize', title, text, level=level, checksum=checksum)
            cached = self.cache.get(cache_key)
            if cached:
                logger.info(f"[{request_id}] Cache HIT for summarize")
                return cached['response'], {
                    "input_tokens": cached['input_tokens'],
                    "output_tokens": cached['output_tokens'],
                    "total_tokens": cached['input_tokens'] + cached['output_tokens'],
                    "cache_hit": True
                }
        
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

        text = _truncate_input(text)
        if not text:
            return None, {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "cache_hit": False}

        payload = {
            "model": profile.get('model', 'deepseek-chat'),
            "messages": _build_messages(title, text),
            "temperature": profile.get('temperature', 0.7),
            "max_tokens": profile.get('max_tokens', 800),
        }
        
        # Add optional parameters
        if 'top_p' in profile:
            payload['top_p'] = profile['top_p']
        
        logger.info(f"[{request_id}] API call: summarize (level={level}, max_tokens={payload['max_tokens']})")

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
                    
                    # Calculate cost and update budget
                    cost_usd = (input_tokens * DEEPSEEK_INPUT_COST_PER_1K_TOKENS_USD / 1000 +
                                output_tokens * DEEPSEEK_OUTPUT_COST_PER_1K_TOKENS_USD / 1000)
                    
                    if self.budget:
                        self.budget.add_cost(cost_usd)
                    
                    logger.info(f"[{request_id}] summarize: {input_tokens}+{output_tokens}={total_tokens} tokens, ${cost_usd:.4f}")
                    
                    # Store in cache
                    result_text = truncate_text(summary.strip(), max_length=800)
                    if self.cache:
                        cache_key = self.cache.generate_cache_key('summarize', title, text, level=level, checksum=checksum)
                        self.cache.set(cache_key, 'summarize', result_text, input_tokens, output_tokens, ttl_hours=72)
                    
                    # Return summary and token usage dict
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

        return None, {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    async def translate_text(self, text: str, target_lang: str = 'ru', checksum: str | None = None) -> tuple[Optional[str], dict]:
        """Translate text to target language using DeepSeek."""
        token_usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

        if not text:
            return None, token_usage

        # Check budget limit
        if self.budget and not self.budget.can_make_request():
            return None, token_usage

        if self.cache:
            cache_key = self.cache.generate_cache_key('translate', '', text, target_lang=target_lang, checksum=checksum)
            cached = self.cache.get(cache_key)
            if cached:
                return cached['response'], {
                    "input_tokens": cached['input_tokens'],
                    "output_tokens": cached['output_tokens'],
                    "total_tokens": cached['input_tokens'] + cached['output_tokens'],
                    "cache_hit": True,
                }

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
                    self.budget.add_cost(cost_usd)

                if self.cache:
                    cache_key = self.cache.generate_cache_key('translate', '', text, target_lang=target_lang, checksum=checksum)
                    self.cache.set(cache_key, 'translate', translated, input_tokens, output_tokens, ttl_hours=72)

                return translated, {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": total_tokens,
                    "cache_hit": False,
                    "cost_usd": cost_usd,
                }

        except Exception as e:
            logger.debug(f"Translate failed: {e}")

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

        if not text or not title:
            return [], token_usage

        text = _truncate_input(text, max_chars=1800)

        if self.budget and not self.budget.can_make_request():
            return [], token_usage

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
                return cached['response'], {
                    "input_tokens": cached['input_tokens'],
                    "output_tokens": cached['output_tokens'],
                    "total_tokens": cached['input_tokens'] + cached['output_tokens'],
                    "cache_hit": True,
                }

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
                    self.budget.add_cost(cost_usd)

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

                return tags, {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": total_tokens,
                    "cache_hit": False,
                    "cost_usd": cost_usd,
                }
        except Exception as e:
            logger.debug(f"Hashtags failed: {e}")

        return [], token_usage

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

        payload = {
            "model": profile.get('model', 'deepseek-chat'),
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
