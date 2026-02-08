"""Hashtag taxonomy and deterministic tagging with optional AI fallback."""
from __future__ import annotations

import re
from typing import Optional

G0_TAGS = ["#Россия", "#Мир"]
G1_DISTRICTS = ["#ЦФО", "#СЗФО", "#ЮФО", "#СКФО", "#ПФО", "#УФО", "#СФО", "#ДФО"]
R0_TAGS = [
    "#Политика",
    "#Общество",
    "#Экономика",
    "#Спорт",
    "#ТехнологииМедиа",
    "#Образование",
    "#Искусство",
    "#Авто",
]

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

    if language != "ru" and not is_russia:
        g0 = "#Мир"
    else:
        if is_russia and not is_world:
            g0 = "#Россия"
        elif is_world and not is_russia:
            g0 = "#Мир"
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
        if g1 is None:
            g1 = "#ЦФО"

    needs_ai = False
    if g0 == "#Россия":
        if g1 is None:
            needs_ai = True
        elif g1 == "#ЦФО" and (g2 is None or g3 is None):
            needs_ai = True

    return {"g0": g0, "g1": g1, "g2": g2, "g3": g3, "needs_ai": needs_ai}


def detect_rubric_tags(title: str, text: str) -> dict:
    combined = f"{title} {text}".lower()
    for tag, keywords in RUBRIC_KEYWORDS.items():
        for keyword in keywords:
            if keyword in combined:
                return {"r0": tag, "needs_ai": False}
    return {"r0": "#Общество", "needs_ai": True}


def get_allowlist() -> dict:
    return {
        "g0": list(G0_TAGS),
        "g1": list(G1_DISTRICTS),
        "g2": list(CFO_REGIONS),
        "g3": list(CFO_CITIES),
        "r0": list(R0_TAGS),
    }


def _validate_allowed(tag: Optional[str], allow: list[str]) -> Optional[str]:
    if not tag:
        return None
    tag = normalize_tag(tag)
    return tag if tag in allow else None


async def build_hashtags(
    title: str,
    text: str,
    language: str = "ru",
    ai_client=None,
    level: int = 0,
) -> list[str]:
    geo = detect_geo_tags(title, text, language=language)
    rubric = detect_rubric_tags(title, text)

    allow = get_allowlist()
    g0 = _validate_allowed(geo.get("g0"), allow["g0"])
    g1 = _validate_allowed(geo.get("g1"), allow["g1"])
    g2 = _validate_allowed(geo.get("g2"), allow["g2"])
    g3 = _validate_allowed(geo.get("g3"), allow["g3"])
    r0 = _validate_allowed(rubric.get("r0"), allow["r0"])

    needs_ai = bool(geo.get("needs_ai") or rubric.get("needs_ai"))

    if ai_client and level >= 1 and needs_ai:
        detected = {"g0": g0, "g1": g1, "g2": g2, "g3": g3, "r0": r0}
        ai_result, _usage = await ai_client.classify_hashtags(title, text, allow, detected, level=level)
        g0 = g0 or _validate_allowed(ai_result.get("g0"), allow["g0"])
        g1 = g1 or _validate_allowed(ai_result.get("g1"), allow["g1"])
        g2 = g2 or _validate_allowed(ai_result.get("g2"), allow["g2"])
        g3 = g3 or _validate_allowed(ai_result.get("g3"), allow["g3"])
        r0 = r0 or _validate_allowed(ai_result.get("r0"), allow["r0"])

    if g0 == "#Россия" and g1 is None:
        g1 = "#ЦФО"
    if g0 == "#Россия" and g1 == "#ЦФО" and g2 is None:
        g2 = "#Москва"
    if g0 == "#Россия" and g1 == "#ЦФО" and g3 is None:
        g3 = "#Москва"
    if r0 is None:
        r0 = "#Общество"

    tags = [g0]
    if g0 == "#Россия":
        tags.append(g1)
        if g1 == "#ЦФО":
            tags.extend([g2, g3])
    tags.append(r0)

    return [tag for tag in tags if tag]


def build_hashtags_en(tags_ru: list[str]) -> list[str]:
    g0 = "#World"
    r0 = "#News"
    for tag in tags_ru:
        if tag == "#Россия":
            g0 = "#Russia"
        if tag in EN_RUBRIC_MAP:
            r0 = EN_RUBRIC_MAP[tag]
    return [g0, r0]
