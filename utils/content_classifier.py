"""
Классификатор новостей по содержанию
Определяет категорию на основе анализа текста
"""
import re
from typing import Optional


class ContentClassifier:
    """Классифицирует новости по содержанию"""
    
    # Ключевые слова для каждой категории
    KEYWORDS = {
        'moscow': [
            # Город Москва
            r'\bмоскв[аеуы]\b',
            r'\bстолиц[аеуы]\b',
            r'\bмэр москвы\b',
            r'\bсобянин\b',
            r'\bкремл[ьяе]\b',
            r'\bкрасн[ая|ой|ую] площад',
            r'\bмосковск[ая|ий|ого] мэр',
            r'\bцентр[е]? москвы\b',
            r'\bгорожан[е]? москвы\b',
            r'\bжител[ии|ей] москвы\b',
            r'\bмосков москвы\b',
            r'\bстолич',
        ],
        'moscow_region': [
            # Подмосковье
            r'\bподмосковь[ея]\b',
            r'\bмосковск[ая|ой|ую] област',
            r'\bмо\b',
            r'\bмособласт',
            r'\bмосрег',
            r'\bодинцов',
            r'\bхимк',
            r'\bкоролёв',
            r'\bбалаших',
            r'\bлюберц',
            r'\bмытищ',
            r'\bпушкин[о]',
            r'\bсергиев',
            r'\bдмитров',
            r'\bвоскресенск',
            r'\bподольск',
            r'\bжуковск',
            r'\bногинск',
            r'\bщёлков',
            r'\bклин\b',
            r'\bистр[аы]\b',
            r'\bнаро-фоминск',
            r'\bсерпухов',
            r'\bступин',
            r'\bкашир',
            r'\bзарайск',
            r'\bколомн',
            r'\bегорьевск',
            r'\bэлектросталь',
            r'\bорехово-зуев',
            r'\bпавловск[ий]? посад',
            r'\bреутов',
            r'\bкрасногорск',
            r'\bлобн[яы]\b',
            r'\bдолгопрудн',
            r'\bдзержинск',
            r'\bжелезнодорожн',
            r'\bфрязин',
            r'\bивантеевк',
            r'\bщербинк',
            r'\bтроицк\b',
            r'\bвидное\b',
            r'\bдомодедов',
            r'\bчехов',
            r'\bселятин',
            r'\bапрелевк',
            r'\bкубинк',
            r'\bнахабин',
            r'\bдедовск',
            r'\bсолнечногорск',
            r'\bзеленоград',
        ],
        'world': [
            # Международные события
            r'\bсша\b',
            r'\bамерик[аеи]',
            r'\bтрамп',
            r'\bбайден',
            r'\bевроп[аеы]',
            r'\bес\b',
            r'\bнато\b',
            r'\bукраин[аеы]',
            r'\bзеленск',
            r'\bкиев',
            r'\bкита[йя]',
            r'\bпекин',
            r'\bяпони[яи]',
            r'\bкоре[яи]',
            r'\bиран',
            r'\bиранск',
            r'\bтегеран',
            r'\bхамас',
            r'\bизраил',
            r'\bтель-авив',
            r'\bпалестин',
            r'\bсири[яи]',
            r'\bасад',
            r'\bтурци[яи]',
            r'\bанкар',
            r'\bердоган',
            r'\bгермани[яи]',
            r'\bберлин',
            r'\bшольц',
            r'\bфранци[яи]',
            r'\bпариж',
            r'\bмакрон',
            r'\bбритани[яи]',
            r'\bлондон',
            r'\bчерчилль',
            r'\bитали[яи]',
            r'\bрим\b',
            r'\bиспани[яи]',
            r'\bмадрид',
            r'\bпольш[аеы]',
            r'\bваршав',
            r'\bприбалтик',
            r'\bлатви[яи]',
            r'\bлитв[аы]',
            r'\bэстони[яи]',
            r'\bбелорусс',
            r'\bминск',
            r'\bказахстан',
            r'\bастан',
            r'\bузбекистан',
            r'\bташкент',
            r'\bиндокитай',
            r'\bвьетнам',
            r'\bтаиланд',
            r'\bафганистан',
            r'\bкабул',
            r'\bпакистан',
            r'\bиндия\b',
            r'\bдели\b',
            r'\bмумбаи',
            r'\bбразили',
            r'\bаргентин',
            r'\bмексик',
            r'\bканад',
            r'\bоттав',
            r'\bавстрали',
            r'\bсидней',
            
            # Португалия
            r'\bпортугали[яи]',
            r'\bлиссабон',
            r'\bпорту\b',
            r'\bроналду',
            r'\bкриштиану',
            
            # Арабские страны и Ближний Восток
            r'\bсаудовск',
            r'\bэр-рияд',
            r'\bдубай',
            r'\bкатар',
            r'\bдоха',
            r'\bкувейт',
            r'\bбахрейн',
            r'\bоаэ\b',
            r'\bэмират',
            r'\bабу-даби',
            r'\bаль-насор',
            r'\bаль-хиляль',
            r'\bаль-итти',
            
            # Международный спорт (клубы, лиги, события)
            r'\bлига чемпион',
            r'\bуефа\b',
            r'\bфифа\b',
            r'\bпремьер-лига',
            r'\bла лига',
            r'\bсерия а\b',
            r'\bбундеслига',
            r'\bлига 1\b',
            r'\bчемпионат мира',
            r'\bчемпионат европы',
            r'\bевро-20',
            r'\bкубок мира',
            r'\bреал мадрид',
            r'\bбарселона',
            r'\bбавария',
            r'\bпсж\b',
            r'\bманчестер',
            r'\bливерпуль',
            r'\bювентус',
            r'\bмилан\b',
            r'\bчелси',
            r'\bарсенал',
            
            # Известные спортсмены (международные)
            r'\bмесси\b',
            r'\bмбаппе',
            r'\bнеймар',
            r'\bхаланд',
            r'\bбензема',
            r'\bмодрич',
            
            # Политика и дипломатия
            r'\bоон\b',
            r'\bмид\b',
            r'\bмеждународн',
            r'\bдипломат',
            r'\bсанкци',
            r'\bвоору?жен',  # вооружённые силы
            r'\bудар\b',
            r'\bракет',
            r'\bдрон',
            r'\bконфликт',
            r'\bвойск',
            r'\bпол[ё]т\b',
            r'\bвоенн',
        ],
    }
    
    def __init__(self):
        # Компилируем регулярные выражения для эффективности
        self.compiled_patterns = {}
        for category, patterns in self.KEYWORDS.items():
            self.compiled_patterns[category] = [
                re.compile(pattern, re.IGNORECASE | re.UNICODE)
                for pattern in patterns
            ]
    
    def classify(self, title: str, text: str = '', url: str = '') -> Optional[str]:
        """
        Классифицирует новость по содержанию
        
        Args:
            title: Заголовок новости
            text: Текст новости (необязательно)
            url: URL новости (для дополнительной проверки)
        
        Returns:
            Категория ('moscow', 'moscow_region', 'world', 'russia') или None
        """
        # Объединяем весь доступный текст для анализа
        # Заголовок весит больше, поэтому добавляем его дважды
        content = f"{title} {title} {text}".lower()
        
        # Сначала проверяем URL (более точный индикатор)
        url_category = self._classify_by_url(url)
        if url_category:
            return url_category
        
        # Подсчитываем совпадения для каждой категории
        scores = {}
        for category, patterns in self.compiled_patterns.items():
            score = 0
            for pattern in patterns:
                matches = pattern.findall(content)
                score += len(matches)
            
            if score > 0:
                scores[category] = score
        
        # Если ничего не найдено, возвращаем 'russia' по умолчанию
        if not scores:
            return 'russia'
        
        # Специальная логика: если нашли и Москву, и Подмосковье,
        # приоритет отдаём той, у которой больше упоминаний
        if 'moscow' in scores and 'moscow_region' in scores:
            # Если Подмосковье упоминается явно, оно важнее
            if scores['moscow_region'] >= scores['moscow']:
                return 'moscow_region'
            return 'moscow'
        
        # Если есть явные маркеры мировых событий (они обычно сильнее локальных),
        # они должны иметь приоритет
        if 'world' in scores:
            # Мировые события имеют вес 1.5x для приоритета
            adjusted_world_score = scores['world'] * 1.5
            best_other = max([v for k, v in scores.items() if k != 'world'], default=0)
            if adjusted_world_score > best_other:
                return 'world'
        
        # Возвращаем категорию с максимальным количеством совпадений
        best_category = max(scores.items(), key=lambda x: x[1])[0]
        
        return best_category
    
    def _classify_by_url(self, url: str) -> Optional[str]:
        """Определяет категорию по URL"""
        if not url:
            return None
        
        url_lower = url.lower()
        
        # Московская область (точные маркеры в URL)
        # Исключаем riamo.ru так как там публикуются новости разных категорий
        moscow_region_markers = (
            'moskovskaya-oblast',
            'moskovskaja-oblast',
            'podmoskovie',
            'mosobl',
            'mosreg',
            'mosregtoday',
            'mosreg.ru',
            'regions.ru',
            '360.ru/rubriki/mosobl',
        )
        if any(marker in url_lower for marker in moscow_region_markers):
            return 'moscow_region'
        
        # Москва (точные маркеры в URL)
        moscow_markers = (
            '/moscow/',
            '/moskva/',
            '-moskvy-',
            '-moskve-',
            '-moscow-',
        )
        if any(marker in url_lower for marker in moscow_markers):
            return 'moscow'
        
        return None
