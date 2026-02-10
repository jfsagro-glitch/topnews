"""Hashtag taxonomy and deterministic tagging with optional AI fallback."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

G0_TAGS = ["#Россия", "#Мир"]
G1_DISTRICTS = ["#ЦФО", "#СЗФО", "#ЮФО", "#СКФО", "#ПФО", "#УФО", "#СФО", "#ДФО"]
R0_TAGS = [
    "#Политика",
    "#Общество",
    "#Экономика",
    "#Спорт",
    "#Технологии_медиа",
    "#ТехнологииМедиа",
    "#Образование",
    "#Искусство",
    "#Авто",
]
# Canonical r0 set; #Новости is NEVER allowed
R0_ALLOWED = {
    "#Политика",
    "#Общество",
    "#Экономика",
    "#Спорт",
    "#Технологии_медиа",
    "#ТехнологииМедиа",
    "#Образование",
    "#Искусство",
    "#Авто",
}

CFO_REGIONS = [
    "#Москва",
    "#МосковскаяОбласть",
    "#БелгородскаяОбласть",
    "#БрянскаяОбласть",
    "#ВладимирскаяОбласть",
    "#ВоронежскаяОбласть",
    "#ИвановскаяОбласть",
    "#КалужскаяОбласть",
    "#КостромскаяОбласть",
    "#КурскаяОбласть",
    "#ЛипецкаяОбласть",
    "#ОрловскаяОбласть",
    "#РязанскаяОбласть",
    "#СмоленскаяОбласть",
    "#ТамбовскаяОбласть",
    "#ТверскаяОбласть",
    "#ТульскаяОбласть",
    "#ЯрославскаяОбласть",
]

CFO_CITIES = [
    "#Москва",
    "#Красногорск",
    "#Белгород",
    "#Брянск",
    "#Владимир",
    "#Воронеж",
    "#Иваново",
    "#Калуга",
    "#Кострома",
    "#Курск",
    "#Липецк",
    "#Орёл",
    "#Рязань",
    "#Смоленск",
    "#Тамбов",
    "#Тверь",
    "#Тула",
    "#Ярославль",
]

CFO_REGION_ALIASES = {
    "#Москва": ["москва", "москвы", "москве"],
    "#МосковскаяОбласть": ["московская область", "московской области", "подмосковье"],
    "#БелгородскаяОбласть": ["белгородская область", "белгородской области"],
    "#БрянскаяОбласть": ["брянская область", "брянской области"],
    "#ВладимирскаяОбласть": ["владимирская область", "владимирской области"],
    "#ВоронежскаяОбласть": ["воронежская область", "воронежской области"],
    "#ИвановскаяОбласть": ["ивановская область", "ивановской области"],
    "#КалужскаяОбласть": ["калужская область", "калужской области"],
    "#КостромскаяОбласть": ["костромская область", "костромской области"],
    "#КурскаяОбласть": ["курская область", "курской области"],
    "#ЛипецкаяОбласть": ["липецкая область", "липецкой области"],
    "#ОрловскаяОбласть": ["орловская область", "орловской области", "орелская область", "орелской области"],
    "#РязанскаяОбласть": ["рязанская область", "рязанской области"],
    "#СмоленскаяОбласть": ["смоленская область", "смоленской области"],
    "#ТамбовскаяОбласть": ["тамбовская область", "тамбовской области"],
    "#ТверскаяОбласть": ["тверская область", "тверской области"],
    "#ТульскаяОбласть": ["тульская область", "тульской области"],
    "#ЯрославскаяОбласть": ["ярославская область", "ярославской области"],
}

CFO_CITY_ALIASES = {
    "#Москва": ["москва", "москве", "москвы"],
    "#Красногорск": ["красногорск", "красногорске"],
    "#Белгород": ["белгород", "белгороде"],
    "#Брянск": ["брянск", "брянске"],
    "#Владимир": ["владимир", "владимире"],
    "#Воронеж": ["воронеж", "воронеже"],
    "#Иваново": ["иваново"],
    "#Калуга": ["калуга", "калуге"],
    "#Кострома": ["кострома", "костроме"],
    "#Курск": ["курск", "курске"],
    "#Липецк": ["липецк", "липецке"],
    "#Орёл": ["орел", "орёл", "орле", "орле"],
    "#Рязань": ["рязан", "рязани"],
    "#Смоленск": ["смоленск", "смоленске"],
    "#Тамбов": ["тамбов", "тамбове"],
    "#Тверь": ["тверь", "твери"],
    "#Тула": ["тула", "туле"],
    "#Ярославль": ["ярославль", "ярославле"],
}

REGION_CAPITALS = {
    "#БелгородскаяОбласть": "#Белгород",
    "#БрянскаяОбласть": "#Брянск",
    "#ВладимирскаяОбласть": "#Владимир",
    "#ВоронежскаяОбласть": "#Воронеж",
    "#ИвановскаяОбласть": "#Иваново",
    "#КалужскаяОбласть": "#Калуга",
    "#КостромскаяОбласть": "#Кострома",
    "#КурскаяОбласть": "#Курск",
    "#ЛипецкаяОбласть": "#Липецк",
    "#ОрловскаяОбласть": "#Орёл",
    "#РязанскаяОбласть": "#Рязань",
    "#СмоленскаяОбласть": "#Смоленск",
    "#ТамбовскаяОбласть": "#Тамбов",
    "#ТверскаяОбласть": "#Тверь",
    "#ТульскаяОбласть": "#Тула",
    "#ЯрославскаяОбласть": "#Ярославль",
    "#МосковскаяОбласть": "#Красногорск",
}

CITY_TO_REGION = {
    "#Красногорск": "#МосковскаяОбласть",
    "#Белгород": "#БелгородскаяОбласть",
    "#Брянск": "#БрянскаяОбласть",
    "#Владимир": "#ВладимирскаяОбласть",
    "#Воронеж": "#ВоронежскаяОбласть",
    "#Иваново": "#ИвановскаяОбласть",
    "#Калуга": "#КалужскаяОбласть",
    "#Кострома": "#КостромскаяОбласть",
    "#Курск": "#КурскаяОбласть",
    "#Липецк": "#ЛипецкаяОбласть",
    "#Орёл": "#ОрловскаяОбласть",
    "#Рязань": "#РязанскаяОбласть",
    "#Смоленск": "#СмоленскаяОбласть",
    "#Тамбов": "#ТамбовскаяОбласть",
    "#Тверь": "#ТверскаяОбласть",
    "#Тула": "#ТульскаяОбласть",
    "#Ярославль": "#ЯрославскаяОбласть",
}

WORLD_MARKERS = [
    "берлин", "германи", "сша", "китай", "франц", "итал", "испан",
    "британ", "англи", "украин", "израил", "турц", "париж", "лондон",
    "евросоюз", "нато", "оон",
]

RUSSIA_MARKERS = ["россия", "рф", "российск", "федерац"]

RUBRIC_KEYWORDS = {
    "#Политика": ["выбор", "президент", "госду", "дум", "кремл", "мэр", "губернатор", "закон", "санкц"],
    "#Общество": ["жител", "городск", "село", "обществен", "соц", "медицина", "здоровье", "пожар", "авар", "чп", "погиб"],
    "#Экономика": ["эконом", "инфляц", "рубл", "доллар", "финанс", "банк", "бюджет", "рынок"],
    "#Спорт": ["спорт", "матч", "чемпион", "лига", "кубок", "хокке", "футбол"],
    "#ТехнологииМедиа": ["технолог", "айти", "it", "цифров", "интернет", "связ", "медиа", "соцсет"],
    "#Образование": ["школ", "вуз", "университет", "экзамен", "учени", "студент", "образован"],
    "#Искусство": ["культур", "музе", "театр", "выставк", "искусств", "концерт"],
    "#Авто": ["авто", "дтп", "машин", "водител", "шоссе", "трасс"],
}

EN_RUBRIC_MAP = {
    "#Политика": "#Politics",
    "#Общество": "#Society",
    "#Экономика": "#Economy",
    "#Спорт": "#Sports",
    "#ТехнологииМедиа": "#TechMedia",
    "#Образование": "#Education",
    "#Искусство": "#Culture",
    "#Авто": "#Auto",
}


def normalize_tag(text: str) -> str:
    cleaned = (text or "").strip().replace("_", "")
    cleaned = re.sub(r"\s+", "", cleaned)
    if not cleaned:
        return ""
    if not cleaned.startswith("#"):
        cleaned = "#" + cleaned
    return cleaned


def _normalize_key(tag: str) -> str:
    normalized = normalize_tag(tag)
    normalized = normalized.casefold().replace("ё", "е")
    return normalized


def _find_alias(text_lower: str, aliases: dict[str, list[str]]) -> Optional[str]:
    for tag, names in aliases.items():
        for name in names:
            if name in text_lower:
                return tag
    return None


def detect_geo_tags(title: str, text: str, language: str = "ru") -> dict:
    language = (language or "ru").lower()
    combined = f"{title} {text}".lower()

    g0 = None
    g1 = None
    g2 = None
    g3 = None

    is_world = any(marker in combined for marker in WORLD_MARKERS)
    is_russia = any(marker in combined for marker in RUSSIA_MARKERS)

    region_tag = _find_alias(combined, CFO_REGION_ALIASES)
    city_tag = _find_alias(combined, CFO_CITY_ALIASES)

    if region_tag or city_tag:
        is_russia = True

    if is_world and not is_russia:
        g0 = "#Мир"
    elif is_russia and not is_world:
        g0 = "#Россия"
    else:
        g0 = "#Россия" if language == "ru" else "#Мир"

    if g0 == "#Россия":
        if region_tag or city_tag:
            g1 = "#ЦФО"
        if region_tag:
            g2 = region_tag
        if city_tag:
            g3 = city_tag
        if g2 is None and g3:
            if g3 == "#Москва":
                g2 = "#Москва"
            else:
                g2 = CITY_TO_REGION.get(g3)
        if g2 == "#Москва" and not g3:
            g3 = "#Москва"
        if g2 and not g3:
            g3 = REGION_CAPITALS.get(g2)
    return {"g0": g0, "g1": g1, "g2": g2, "g3": g3, "needs_ai": False}


def detect_rubric_tags(title: str, text: str) -> dict:
    combined = f"{title} {text}".lower()
    for tag, keywords in RUBRIC_KEYWORDS.items():
        for keyword in keywords:
            if keyword in combined:
                return {"r0": tag, "needs_ai": False}
    return {"r0": "#Общество", "needs_ai": False}


@dataclass
class TagPack:
    """Canonical hashtag pack: g0 (always), g1/g2/g3 (optional), r0 (always)."""
    g0: str
    g1: Optional[str] = None
    g2: Optional[str] = None
    g3: Optional[str] = None
    r0: str = "#Общество"


# g0: Russia only on strong signals; else #Мир. Crypto/tech global bias -> #Мир.
_RUSSIA_STRONG = re.compile(
    r"\b(росси(я|и|ю|ей)|рф|москва|санкт[-\s]?петербург|петербург|кремл(ь|я)|госдума|совфед|цб\s*рф|"
    r"минфин|роскомнадзор|фсб|мвд|суд\s*рф|россиянин|московск(ая|ой)|петербургск(ая|ой))\b",
    re.IGNORECASE,
)
_CRYPTO_TECH_GLOBAL = re.compile(
    r"\b(ethereum|eth|bitcoin|btc|solana|ton|web3|blockchain|дефай|defi|nft|vitalik|бутерин|sec|binance|"
    r"openai|ai|ии|ml|llm|нейросет)\b",
    re.IGNORECASE,
)


def _detect_r0(title: str, text: str) -> str:
    t = (title or "") + "\n" + (text or "")
    t = t.lower()
    r0 = "#Общество"
    if re.search(r"\b(выбор|санкц|президент|правитель|парламент)\b", t):
        r0 = "#Политика"
    elif re.search(r"\b(рынок|инфляц|рубл|доллар|эконом)\b", t):
        r0 = "#Экономика"
    elif re.search(r"\b(матч|гол|лига|чемпион)\b", t):
        r0 = "#Спорт"
    elif re.search(r"\b(ии|ai|openai|технолог|медиа|интернет)\b", t):
        r0 = "#Технологии_медиа"
    elif re.search(r"\b(школ|университет|образован)\b", t):
        r0 = "#Образование"
    elif re.search(r"\b(выставк|театр|кино|искусств)\b", t):
        r0 = "#Искусство"
    elif re.search(r"\b(авто|tesla|bmw|mercedes|toyota)\b", t):
        r0 = "#Авто"
    return r0


def _detect_g0_strict(title: str, text: str, r0: str) -> str:
    """Default #Мир; #Россия only on strong Russia markers. Crypto/tech without Russia -> #Мир."""
    payload = (title or "") + "\n" + (text or "")
    if not payload.strip():
        return "#Мир"
    has_russia = _RUSSIA_STRONG.search(payload) is not None
    has_crypto_tech = _CRYPTO_TECH_GLOBAL.search(payload) is not None
    if has_crypto_tech and not has_russia:
        return "#Мир"
    if has_russia:
        return "#Россия"
    return "#Мир"


def get_allowlist() -> dict:
    return {
        "g0": list(G0_TAGS),
        "g1": list(G1_DISTRICTS),
        "g2": list(CFO_REGIONS),
        "g3": list(CFO_CITIES),
        "r0": list(R0_TAGS),
    }


def make_allowlist(config=None) -> dict:
    """Return allowlist as dict of sets; optional config for TAX_G2/TAX_G3."""
    base = get_allowlist()
    out = {k: set(v) for k, v in base.items()}
    out["r0"] = set(R0_ALLOWED)  # ensure #Новости never in
    if config is not None and hasattr(config, "TAX_G2"):
        out["g2"] = set(getattr(config, "TAX_G2", []))
    if config is not None and hasattr(config, "TAX_G3"):
        out["g3"] = set(getattr(config, "TAX_G3", []))
    return out


def validate_allowlist(tp: TagPack, allow: dict) -> TagPack:
    """Drop any tag outside allowlist; if g2==g3 (normalized), drop g3. Never allow #Новости."""
    g0 = tp.g0 if tp.g0 in allow.get("g0", set()) else "#Мир"
    r0 = tp.r0 if tp.r0 in allow.get("r0", set()) else "#Общество"
    g1 = tp.g1 if tp.g1 is None or tp.g1 in allow.get("g1", set()) else None
    g2 = tp.g2 if tp.g2 is None or tp.g2 in allow.get("g2", set()) else None
    g3 = tp.g3 if tp.g3 is None or tp.g3 in allow.get("g3", set()) else None
    if g2 and g3 and _normalize_key(g2) == _normalize_key(g3):
        g3 = None
    return TagPack(g0=g0, g1=g1, g2=g2, g3=g3, r0=r0)


def build_ordered_hashtags(tp: TagPack) -> list[str]:
    """Strict ordering: g0, [g1?, g2?, g3?], r0. For #Мир only [g0, r0]. Dedup normalized."""
    if tp.g0 == "#Мир":
        return _dedup_ordered([tp.g0, tp.r0])
    tags = [tp.g0]
    if tp.g1:
        tags.append(tp.g1)
    if tp.g2:
        tags.append(tp.g2)
    if tp.g3:
        tags.append(tp.g3)
    tags.append(tp.r0)
    return _dedup_ordered(tags)


def build_hashtags_for_item(title: str, text: str, config=None) -> list[str]:
    """
    Single public API for hashtags: use everywhere (store, display, export).
    Returns full hierarchical list: g0, [g1?, g2?, g3?], r0.
    #Мир => [g0, r0]; #Россия => [g0, g1?, g2?, g3?, r0]. r0 always present, never #Новости.
    """
    r0 = _detect_r0(title or "", text or "")
    if r0 not in R0_ALLOWED:
        r0 = "#Общество"
    g0 = _detect_g0_strict(title or "", text or "", r0)
    g1, g2, g3 = None, None, None
    if g0 == "#Россия":
        geo = detect_geo_tags(title or "", text or "")
        allow_list = get_allowlist()
        g1 = _validate_allowed(geo.get("g1"), allow_list["g1"])
        g2 = _validate_allowed(geo.get("g2"), allow_list["g2"])
        g3 = _validate_allowed(geo.get("g3"), allow_list["g3"])
        if g2 and g3 and _normalize_key(g2) == _normalize_key(g3):
            g3 = None
        if g1 is None and (g2 or g3):
            g1 = "#ЦФО"
    tp = TagPack(g0=g0, g1=g1, g2=g2, g3=g3, r0=r0)
    allow = make_allowlist(config)
    tp = validate_allowlist(tp, allow)
    return build_ordered_hashtags(tp)


def _dedup_ordered(tags: list[str]) -> list[str]:
    seen = set()
    out = []
    for t in tags:
        if not t:
            continue
        nt = _normalize_key(t)
        if nt in seen:
            continue
        seen.add(nt)
        out.append(t)
    return out


def _validate_allowed(tag: Optional[str], allow: list[str]) -> Optional[str]:
    if not tag:
        return None
    tag = normalize_tag(tag)
    return tag if tag in allow else None


def _validate_ai_result(ai_result: dict, allow: dict) -> dict | None:
    if not isinstance(ai_result, dict):
        return None
    validated = {}
    for key in ("g0", "g1", "g2", "g3", "r0"):
        raw = ai_result.get(key)
        if raw is None:
            validated[key] = None
            continue
        allowed = allow.get(key, [])
        cleaned = normalize_tag(raw)
        if cleaned not in allowed:
            return None
        validated[key] = cleaned
    return validated


async def build_hashtags(
    title: str,
    text: str,
    language: str = "ru",
    chat_id: str | None = None,
    ai_client=None,
    level: int = 0,
    ai_call_guard=None,
) -> list[str]:
    rubric = detect_rubric_tags(title, text)
    allow = get_allowlist()
    r0 = _validate_allowed(rubric.get("r0"), allow["r0"]) or "#Общество"
    if r0 not in R0_ALLOWED:
        r0 = "#Общество"
    g0 = _detect_g0_strict(title, text, r0)
    g0 = _validate_allowed(g0, allow["g0"]) or "#Мир"
    geo = detect_geo_tags(title, text, language=language)
    g1 = _validate_allowed(geo.get("g1"), allow["g1"])
    g2 = _validate_allowed(geo.get("g2"), allow["g2"])
    g3 = _validate_allowed(geo.get("g3"), allow["g3"])

    needs_ai = bool(g0 is None or r0 is None)

    if ai_client and level >= 1 and needs_ai:
        if ai_call_guard and not ai_call_guard("hashtags_ai"):
            needs_ai = False
        if needs_ai:
            detected = {"g0": g0, "g1": g1, "g2": g2, "g3": g3, "r0": r0}
            ai_result, _usage = await ai_client.classify_hashtags(title, text, allow, detected, level=level)
            validated = _validate_ai_result(ai_result, allow)
            if validated:
                g0 = g0 or validated.get("g0")
                g1 = g1 or validated.get("g1")
                g2 = g2 or validated.get("g2")
                g3 = g3 or validated.get("g3")
                r0 = r0 or validated.get("r0")

    if g0 == "#Россия" and g1 is None:
        if g2 or g3:
            g1 = "#ЦФО"
    if r0 is None or r0 not in R0_ALLOWED:
        r0 = "#Общество"

    if g0 == "#Мир":
        g1 = None
        g2 = None
        g3 = None

    # Only ЦФО has region/city taxonomy enabled for now.
    if g1 != "#ЦФО":
        g2 = None
        g3 = None

    if g2 and g3 and _normalize_key(g2) == _normalize_key(g3):
        g3 = None

    tp = TagPack(g0=g0, g1=g1, g2=g2, g3=g3, r0=r0)
    allow = {k: set(v) for k, v in get_allowlist().items()}
    allow["r0"] = R0_ALLOWED
    tp = validate_allowlist(tp, allow)
    return build_ordered_hashtags(tp)


def build_hashtags_en(tags_ru: list[str]) -> list[str]:
    en_map = {
        "#Россия": "#Russia",
        "#Мир": "#World",
        "#Москва": "#Moscow",
        "#МосковскаяОбласть": "#MoscowRegion",
        **EN_RUBRIC_MAP,
    }

    converted = []
    seen = set()
    for tag in tags_ru:
        if not tag:
            continue
        normalized = normalize_tag(tag)
        mapped = en_map.get(normalized, normalized)
        key = _normalize_key(mapped)
        if key in seen:
            continue
        seen.add(key)
        converted.append(mapped)
    return converted
