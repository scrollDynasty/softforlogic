"""
Умные селекторы для парсинга Schneider FreightPower
Система с fallback селекторами для надежности
"""

from typing import Dict, List
import re
from functools import lru_cache

class SelectorManager:
    """Менеджер селекторов с автоматическим обнаружением"""
    
    def __init__(self):
        # Предкомпилированные регулярные выражения для скорости
        self.COMPILED_PATTERNS = {
            'load_id': re.compile(r'SNI-\d+|LOAD-\d+|\d{8,}|REF[\d\-]+', re.IGNORECASE),
            'price': re.compile(r'\$[\d,]+\.?\d*'),
            'miles': re.compile(r'(\d+)\s*mile', re.IGNORECASE),
            'deadhead': re.compile(r'(\d+)\s*(?:DH|Dead|Empty)', re.IGNORECASE),
            'rate_per_mile': re.compile(r'\$(\d+\.?\d*)/mile', re.IGNORECASE),
            'location': re.compile(r'([A-Z]{2})\s*,?\s*([A-Z]{2,})', re.IGNORECASE),
            'date': re.compile(r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2}')
        }
        
        # Умные селекторы с множественными вариантами
        self.SMART_SELECTORS = {
            'load_items': [
                # Schneider-специфичные селекторы
                "[data-testid='load-card']",
                "[data-testid='freight-row']",
                ".load-card, .freight-card",
                ".shipment-card, .shipment-row",
                
                # Общие селекторы для таблиц
                "tr[data-load-id]",
                "tr:has(td):not(:first-child)",
                "tbody tr",
                ".data-row, .table-row",
                
                # Селекторы для списков
                ".load-item, .freight-item",
                "[class*='load'][class*='row']",
                "[class*='freight'][class*='item']",
                
                # Fallback селекторы
                "div:has(text()[contains(., 'SNI-')])",
                "div:has(text()[contains(., '$')])",
                ".row:has(.miles, .rate)"
            ],
            
            'load_id': [
                # Schneider load ID селекторы
                "[data-testid='load-id']",
                "[data-testid='reference']",
                "[data-testid='load-number']",
                
                # Общие селекторы ID
                ".load-number, .reference-number",
                ".load-id, .shipment-id",
                "[class*='load-id'], [class*='reference']",
                
                # Селекторы по позиции
                "td:first-child, .id-column",
                ".first-column, .col-id",
                
                # Fallback селекторы
                "*:contains('SNI-')",
                "*:contains('LOAD-')",
                "span:matches('^[A-Z]{3}-\\d+')"
            ],
            
            'pickup_location': [
                "[data-testid='pickup-location']",
                "[data-testid='origin']",
                ".origin, .pickup",
                ".pickup-location, .origin-location",
                "[class*='pickup'], [class*='origin']",
                "td:nth-child(2), .pickup-column",
                ".location:first-of-type",
                "*:contains('Pickup:')",
                "*:contains('Origin:')"
            ],
            
            'delivery_location': [
                "[data-testid='delivery-location']",
                "[data-testid='destination']",
                ".destination, .delivery",
                ".delivery-location, .destination-location",
                "[class*='delivery'], [class*='destination']",
                "td:nth-child(3), .delivery-column",
                ".location:last-of-type",
                "*:contains('Delivery:')",
                "*:contains('Destination:')"
            ],
            
            'miles': [
                "[data-testid='miles']",
                "[data-testid='distance']",
                ".distance, .total-miles",
                ".miles, .mileage",
                "[class*='miles'], [class*='distance']",
                "td:has-text('mi'), .miles-column",
                "*:contains('miles')",
                "*:matches('\\d+\\s*mi')"
            ],
            
            'deadhead': [
                "[data-testid='deadhead']",
                "[data-testid='empty-miles']",
                ".deadhead-miles, .empty-miles",
                ".deadhead, .dh",
                "[class*='deadhead'], [class*='empty']",
                "td:has-text('DH'), .deadhead-column",
                "*:contains('DH')",
                "*:contains('Empty')",
                "*:contains('Deadhead')"
            ],
            
            'rate': [
                "[data-testid='rate']",
                "[data-testid='price']",
                ".rate-amount, .price",
                ".rate, .amount",
                "[class*='rate'], [class*='price']",
                "td:has-text('$'), .rate-column",
                ".currency, .money",
                "*:contains('$')"
            ],
            
            'equipment': [
                "[data-testid='equipment']",
                "[data-testid='trailer-type']",
                ".trailer-type, .equipment-type",
                ".equipment, .trailer",
                "[class*='equipment'], [class*='trailer']",
                "td:contains('Van'), .equipment-column",
                "*:contains('Van')",
                "*:contains('Reefer')",
                "*:contains('Flatbed')"
            ],
            
            'pickup_date': [
                "[data-testid='pickup-date']",
                "[data-testid='ready-date']",
                ".pickup-datetime, .ready-date",
                ".pickup-date, .date",
                "[class*='pickup'][class*='date']",
                "td:matches('\\d{1,2}[/-]\\d{1,2}'), .date-column",
                "*:contains('Ready:')",
                ".datetime, .timestamp"
            ]
        }
        
        self.selector_success_rates = {}
        
    @lru_cache(maxsize=1000)
    def extract_number_cached(self, text: str, pattern_name: str) -> float:
        """Кешированное извлечение чисел с предкомпилированными паттернами"""
        if not text:
            return None
            
        pattern = self.COMPILED_PATTERNS.get(pattern_name)
        if pattern:
            match = pattern.search(text)
            if match:
                # Извлекаем первое число из группы
                for group in match.groups():
                    if group:
                        try:
                            return float(group.replace(',', ''))
                        except ValueError:
                            continue
                # Если нет групп, берем весь матч
                try:
                    matched_text = match.group(0)
                    # Убираем все кроме цифр, точек и запятых
                    clean_text = re.sub(r'[^\d.,]', '', matched_text)
                    return float(clean_text.replace(',', ''))
                except ValueError:
                    pass
        return None
    
    async def find_elements_smart(self, page, selector_group: str) -> List:
        """Умный поиск элементов с fallback селекторами"""
        selectors = self.SMART_SELECTORS.get(selector_group, [])
        
        for i, selector in enumerate(selectors):
            try:
                elements = await page.query_selector_all(selector)
                if elements:
                    # Обновляем статистику успешности селектора
                    self.selector_success_rates[selector] = self.selector_success_rates.get(selector, 0) + 1
                    
                    # Если это не первый селектор, логируем для оптимизации
                    if i > 0:
                        logger.info(f"🎯 Селектор '{selector}' сработал после {i} попыток")
                    
                    return elements
            except Exception as e:
                # Селектор не сработал, пробуем следующий
                continue
        
        logger.warning(f"⚠️ Не найдены элементы для группы: {selector_group}")
        return []
    
    async def auto_discover_selectors(self, page) -> Dict[str, List[str]]:
        """Автоматическое обнаружение новых селекторов"""
        discovered_selectors = {}
        
        try:
            # Поиск контейнеров с данными о грузах
            potential_containers = await page.query_selector_all(
                "[class*='load'], [class*='freight'], [class*='shipment'], "
                "[data-*='load'], tr, .row, div:has(text()[contains(., '$')])"
            )
            
            for container in potential_containers[:10]:  # Ограничиваем проверку
                try:
                    text_content = await container.text_content()
                    if text_content and self.looks_like_load_data(text_content):
                        # Получаем селектор для этого элемента
                        selector = await container.evaluate("""
                            el => {
                                let selector = el.tagName.toLowerCase();
                                if (el.id) selector += '#' + el.id;
                                if (el.className) {
                                    const classes = el.className.split(' ').filter(c => c.length > 0);
                                    if (classes.length > 0) {
                                        selector += '.' + classes.join('.');
                                    }
                                }
                                return selector;
                            }
                        """)
                        
                        if 'load_items' not in discovered_selectors:
                            discovered_selectors['load_items'] = []
                        discovered_selectors['load_items'].append(selector)
                        
                except Exception:
                    continue
            
            # Удаляем дубликаты
            for key in discovered_selectors:
                discovered_selectors[key] = list(set(discovered_selectors[key]))
            
            if discovered_selectors:
                logger.info(f"🔍 Обнаружены новые селекторы: {discovered_selectors}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка автоматического обнаружения селекторов: {e}")
        
        return discovered_selectors
    
    def looks_like_load_data(self, text: str) -> bool:
        """Определяет, содержит ли текст данные о грузе"""
        if not text or len(text) < 10:
            return False
            
        indicators = [
            'mile', 'pickup', 'delivery', 'deadhead', 'SNI-', 'LOAD-',
            '$', 'van', 'reefer', 'flatbed', 'DH', 'origin', 'destination'
        ]
        
        text_lower = text.lower()
        matches = sum(1 for indicator in indicators if indicator.lower() in text_lower)
        
        # Дополнительные проверки
        has_money = '$' in text
        has_miles = any(word in text_lower for word in ['mile', 'mi'])
        has_location = any(pattern.search(text) for pattern in [
            self.COMPILED_PATTERNS['location']
        ])
        
        # Груз должен содержать минимум 2 индикатора + деньги или мили
        return matches >= 2 and (has_money or has_miles or has_location)
    
    def get_best_selectors(self, selector_group: str, limit: int = 3) -> List[str]:
        """Получение лучших селекторов на основе статистики успешности"""
        selectors = self.SMART_SELECTORS.get(selector_group, [])
        
        # Сортируем по успешности
        sorted_selectors = sorted(
            selectors,
            key=lambda s: self.selector_success_rates.get(s, 0),
            reverse=True
        )
        
        return sorted_selectors[:limit]
    
    def update_selector_performance(self, selector: str, success: bool) -> None:
        """Обновление статистики производительности селектора"""
        if success:
            self.selector_success_rates[selector] = self.selector_success_rates.get(selector, 0) + 1
        # Для неуспешных селекторов можно реализовать отрицательную статистику
    
    def get_selector_statistics(self) -> Dict:
        """Получение статистики использования селекторов"""
        return {
            'total_selectors': sum(len(selectors) for selectors in self.SMART_SELECTORS.values()),
            'used_selectors': len(self.selector_success_rates),
            'success_rates': self.selector_success_rates,
            'most_successful': sorted(
                self.selector_success_rates.items(),
                key=lambda x: x[1],
                reverse=True
            )[:5]
        }

# Глобальный экземпляр менеджера селекторов
selector_manager = SelectorManager()