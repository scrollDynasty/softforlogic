import asyncio
import time
import re
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from playwright.async_api import Page, ElementHandle

from ..utils.logger import logger
from ..utils.rate_calculator import RateCalculator
from ..utils.performance_monitor import PerformanceMonitor
from .selectors import selector_manager

class LoadParser:
    def __init__(self, config: Dict):
        self.config = config
        self.performance = PerformanceMonitor()
        
        # Умные селекторы с fallback вариантами
        self.SMART_SELECTORS = {
            'load_items': [
                "[data-testid='load-card']",
                ".load-item, .freight-row",
                "tr[data-load-id]",
                ".shipment-row",
                "[class*='load'][class*='row']",
                "tr:has(td)",
                ".freight-item"
            ],
            'load_id': [
                "[data-testid='load-id']",
                ".load-number, .reference-number",
                "[class*='load-id'], [class*='reference']",
                "td:first-child, .id-column",
                "[data-testid='reference']",
                ".load-reference"
            ],
            'pickup_location': [
                "[data-testid='pickup-location']",
                ".origin, .pickup",
                "[class*='pickup'], [class*='origin']",
                "td:nth-child(2), .pickup-column",
                ".pickup-location"
            ],
            'delivery_location': [
                "[data-testid='delivery-location']",
                ".destination, .delivery",
                "[class*='delivery'], [class*='destination']",
                "td:nth-child(3), .delivery-column",
                ".delivery-location"
            ],
            'miles': [
                "[data-testid='miles']",
                ".distance, .total-miles",
                "[class*='miles'], [class*='distance']",
                "td:nth-child(4), .miles-column",
                ".total-distance"
            ],
            'deadhead': [
                "[data-testid='deadhead']",
                ".deadhead-miles, .empty-miles",
                "[class*='deadhead'], [class*='empty']",
                "td:nth-child(5), .deadhead-column",
                ".empty-miles"
            ],
            'rate': [
                "[data-testid='rate']",
                ".rate-amount, .price",
                "[class*='rate'], [class*='price']",
                "td:nth-child(6), .rate-column",
                ".load-rate"
            ],
            'equipment': [
                "[data-testid='equipment']",
                ".trailer-type, .equipment-type",
                "[class*='equipment'], [class*='trailer']",
                "td:nth-child(7), .equipment-column",
                ".trailer-type"
            ],
            'pickup_date': [
                "[data-testid='pickup-date']",
                ".pickup-datetime, .ready-date",
                "[class*='pickup'][class*='date']",
                "td:nth-child(8), .date-column",
                ".ready-date"
            ]
        }
    
    async def set_search_filters(self, location: str, max_deadhead: int, min_miles: int) -> bool:
        """Настройка фильтров поиска"""
        try:
            logger.info(f"🔧 Настройка фильтров: {location}, max DH: {max_deadhead}, min miles: {min_miles}")
            # Здесь будет логика настройки фильтров на сайте
            # Пока что просто логируем
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка настройки фильтров: {e}")
            return False
    
    async def scan_loads_page(self, page: Page) -> List[Dict]:
        """Сканирование страницы с грузами"""
        try:
            start_time = time.time()
            
            # Поиск контейнеров с грузами
            load_elements = await self.find_elements_smart(page, 'load_items')
            
            if not load_elements:
                logger.warning("⚠️ Грузы не найдены на странице")
                return []
            
            logger.info(f"🔍 Найдено {len(load_elements)} грузов для анализа")
            
            # Параллельная обработка грузов
            tasks = []
            for element in load_elements:
                task = asyncio.create_task(self.extract_load_data(element))
                tasks.append(task)
            
            # Ожидание всех задач с ограничением времени
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=30
            )
            
            # Фильтрация результатов
            loads = []
            for result in results:
                if isinstance(result, dict) and result:
                    loads.append(result)
                elif isinstance(result, Exception):
                    logger.error(f"❌ Ошибка извлечения данных груза: {result}")
            
            duration = (time.time() - start_time) * 1000
            await self.performance.track_scan_performance(duration)
            
            logger.info(f"✅ Обработано {len(loads)} грузов за {duration:.0f}ms")
            return loads
            
        except asyncio.TimeoutError:
            logger.error("⏰ Таймаут сканирования страницы")
            return []
        except Exception as e:
            logger.error(f"❌ Ошибка сканирования страницы: {e}")
            return []
    
    async def find_elements_smart(self, page: Page, selector_group: str) -> List[ElementHandle]:
        """Умный поиск элементов с fallback селекторами через SelectorManager"""
        return await selector_manager.find_elements_smart(page, selector_group)
    
    async def extract_load_data(self, load_element: ElementHandle) -> Optional[Dict]:
        """Извлечение данных груза"""
        try:
            load_data = {}
            
            # Извлечение ID груза
            load_id = await self._extract_text_smart(load_element, 'load_id')
            if not load_id:
                logger.debug("⚠️ ID груза не найден, пропускаем")
                return None
            
            load_data['id'] = load_id.strip()
            
            # Извлечение остальных полей
            load_data['pickup'] = await self._extract_text_smart(load_element, 'pickup_location')
            load_data['delivery'] = await self._extract_text_smart(load_element, 'delivery_location')
            load_data['equipment'] = await self._extract_text_smart(load_element, 'equipment')
            load_data['pickup_date'] = await self._extract_text_smart(load_element, 'pickup_date')
            
            # Извлечение и парсинг числовых значений
            miles_text = await self._extract_text_smart(load_element, 'miles')
            load_data['miles'] = RateCalculator.parse_miles_from_text(miles_text) if miles_text else 0
            
            deadhead_text = await self._extract_text_smart(load_element, 'deadhead')
            load_data['deadhead'] = RateCalculator.parse_deadhead_from_text(deadhead_text) if deadhead_text else 0
            
            rate_text = await self._extract_text_smart(load_element, 'rate')
            load_data['rate'] = RateCalculator.parse_rate_from_text(rate_text) if rate_text else None
            
            # Добавление временной метки
            load_data['timestamp'] = datetime.now().isoformat()
            
            # Валидация данных
            if not self._validate_load_data(load_data):
                logger.debug(f"⚠️ Некорректные данные груза {load_data.get('id')}, пропускаем")
                return None
            
            return load_data
            
        except Exception as e:
            logger.error(f"❌ Ошибка извлечения данных груза: {e}")
            return None
    
    async def _extract_text_smart(self, element: ElementHandle, selector_group: str) -> Optional[str]:
        """Умное извлечение текста с fallback селекторами"""
        selectors = self.SMART_SELECTORS.get(selector_group, [])
        
        for selector in selectors:
            try:
                # Попытка найти элемент внутри контейнера груза
                found_element = await element.query_selector(selector)
                if found_element:
                    text = await found_element.text_content()
                    if text and text.strip():
                        return text.strip()
            except Exception:
                continue
        
        return None
    
    def _validate_load_data(self, load_data: Dict) -> bool:
        """Валидация данных груза"""
        required_fields = ['id', 'pickup', 'delivery']
        
        # Проверка обязательных полей
        for field in required_fields:
            if not load_data.get(field):
                return False
        
        # Проверка числовых значений
        miles = load_data.get('miles', 0)
        deadhead = load_data.get('deadhead', 0)
        
        if miles <= 0 or deadhead < 0:
            return False
        
        # Проверка на разумные значения
        if miles > 3000 or deadhead > 500:
            return False
        
        return True
    
    async def calculate_profitability(self, deadhead: int, miles: int, rate: float) -> float:
        """Расчет прибыльности груза"""
        return RateCalculator.calculate_minimum_rate(deadhead, miles)
    
    async def filter_profitable_loads(self, loads: List[Dict]) -> List[Dict]:
        """Фильтрация прибыльных грузов"""
        try:
            profitable_loads = []
            criteria = self.config['search_criteria']
            
            for load in loads:
                # Проверка критериев
                if not self._meets_criteria(load, criteria):
                    continue
                
                # Расчет прибыльности
                analysis = RateCalculator.calculate_comprehensive_profitability(load)
                
                if analysis.is_profitable:
                    load['analysis'] = {
                        'rate_per_mile': analysis.rate_per_mile,
                        'profitability_score': analysis.profitability_score,
                        'priority': analysis.priority,
                        'total_miles': analysis.total_miles,
                        'deadhead_ratio': analysis.deadhead_ratio,
                        'profit_margin': analysis.profit_margin
                    }
                    profitable_loads.append(load)
                    
                    # Логирование найденного груза
                    logger.log_load_found(
                        load['id'], 
                        analysis.rate_per_mile, 
                        analysis.profitability_score
                    )
            
            logger.info(f"💰 Найдено {len(profitable_loads)} прибыльных грузов из {len(loads)}")
            return profitable_loads
            
        except Exception as e:
            logger.error(f"❌ Ошибка фильтрации грузов: {e}")
            return []
    
    def _meets_criteria(self, load: Dict, criteria: Dict) -> bool:
        """Проверка соответствия критериям поиска"""
        try:
            miles = load.get('miles', 0)
            deadhead = load.get('deadhead', 0)
            
            # Проверка минимального расстояния
            if miles < criteria.get('min_total_miles', 200):
                return False
            
            # Проверка максимального deadhead
            if deadhead > criteria.get('max_deadhead_miles', 250):
                return False
            
            # Проверка исключенных состояний
            excluded_states = criteria.get('excluded_states', [])
            pickup = load.get('pickup', '').upper()
            delivery = load.get('delivery', '').upper()
            
            for state in excluded_states:
                if state in pickup or state in delivery:
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка проверки критериев: {e}")
            return False
    
    async def get_load_details(self, load_id: str, page: Page) -> Optional[Dict]:
        """Получение детальной информации о грузе"""
        try:
            # Здесь будет логика перехода на страницу деталей груза
            # Пока что возвращаем базовую информацию
            logger.debug(f"🔍 Получение деталей груза: {load_id}")
            return None
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения деталей груза {load_id}: {e}")
            return None
    
    async def screenshot_on_error(self, error_context: str, page: Page) -> str:
        """Создание скриншота при ошибке"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot_path = f"screenshots/error_{error_context}_{timestamp}.png"
            
            # Создание директории если не существует
            import os
            os.makedirs("screenshots", exist_ok=True)
            
            # Создание скриншота
            await page.screenshot(path=screenshot_path, full_page=True)
            
            logger.info(f"📸 Скриншот сохранен: {screenshot_path}")
            return screenshot_path
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания скриншота: {e}")
            return ""
    
    async def auto_discover_selectors(self, page: Page) -> Dict:
        """Автоматическое обнаружение новых селекторов"""
        try:
            discovered_selectors = {}
            
            # Поиск контейнеров с данными о грузах
            potential_containers = await page.query_selector_all(
                "[class*='load'], [class*='freight'], [class*='shipment'], "
                "[data-*='load'], tr, .row"
            )
            
            for container in potential_containers:
                # Анализ содержимого контейнера
                text_content = await container.text_content()
                if text_content and self._looks_like_load_data(text_content):
                    selector = await container.evaluate("""
                        el => {
                            let selector = el.tagName.toLowerCase();
                            if (el.className) {
                                selector += '.' + el.className.split(' ').join('.');
                            }
                            return selector;
                        }
                    """)
                    
                    if 'load_items' not in discovered_selectors:
                        discovered_selectors['load_items'] = []
                    discovered_selectors['load_items'].append(selector)
            
            logger.info(f"🔍 Обнаружено {len(discovered_selectors.get('load_items', []))} новых селекторов")
            return discovered_selectors
            
        except Exception as e:
            logger.error(f"❌ Ошибка обнаружения селекторов: {e}")
            return {}
    
    def _looks_like_load_data(self, text: str) -> bool:
        """Определяет, содержит ли текст данные о грузе"""
        if not text:
            return False
        
        indicators = ['mile', 'pickup', 'delivery', 'deadhead', 'SNI-', 'LOAD-', '$']
        matches = sum(1 for indicator in indicators if indicator.lower() in text.lower())
        
        return matches >= 2

    async def navigate_to_search_page(self, page: Page) -> bool:
        """Переход на страницу поиска"""
        try:
            logger.info("🔍 Переход на страницу поиска...")
            
            # Переход на главную страницу после авторизации
            await page.goto("https://freightpower.schneider.com/carrier/app/home", wait_until='networkidle', timeout=30000)
            await asyncio.sleep(2)
            
            # Поиск и клик по ссылке Search
            search_selectors = [
                "a[href*='search']",
                "a:has-text('Search')",
                "[data-testid='search-link']",
                ".nav-link:has-text('Search')",
                "nav a:has-text('Search')"
            ]
            
            search_clicked = False
            for selector in search_selectors:
                try:
                    search_element = await page.wait_for_selector(selector, timeout=5000)
                    if search_element:
                        await search_element.click()
                        await page.wait_for_load_state('networkidle')
                        search_clicked = True
                        logger.info("✅ Переход в раздел Search выполнен")
                        break
                except Exception:
                    continue
            
            if not search_clicked:
                # Альтернативный способ - прямой переход по URL
                try:
                    await page.goto("https://freightpower.schneider.com/carrier/app/search", wait_until='networkidle', timeout=30000)
                    logger.info("✅ Прямой переход на страницу поиска")
                    search_clicked = True
                except Exception as e:
                    logger.error(f"❌ Не удалось перейти на страницу поиска: {e}")
            
            return search_clicked
            
        except Exception as e:
            logger.error(f"❌ Ошибка перехода на страницу поиска: {e}")
            return False

    def get_user_search_criteria(self) -> Dict:
        """Получение параметров поиска грузов от пользователя с понятной терминологией"""
        print("\n" + "="*60)
        print("🔍 НАСТРОЙКА ПАРАМЕТРОВ ПОИСКА ГРУЗОВ")
        print("="*60)
        print("Введите параметры для поиска доступных грузов:")
        print("(Оставьте пустым для пропуска параметра)")
        print("="*60)
        
        criteria = {}
        
        # Тип перевозки
        capacity_type = input("Тип перевозки (Dry Van, Reefer, Flatbed, Power Only): ").strip()
        if capacity_type:
            criteria['capacity_type'] = capacity_type
        
        # Место погрузки
        origin_location = input("Место погрузки (город, штат): ").strip()
        if origin_location:
            criteria['origin_location'] = origin_location
        
        # Радиус поиска от места погрузки
        origin_radius = input("Радиус поиска от места погрузки (25-250 миль, по умолчанию 100): ").strip()
        if origin_radius:
            try:
                criteria['origin_radius'] = int(origin_radius)
            except ValueError:
                criteria['origin_radius'] = 100
        
        # Место разгрузки
        destination_location = input("Место разгрузки (город, штат или 'Anywhere'): ").strip()
        if destination_location:
            criteria['destination_location'] = destination_location
        
        # Радиус поиска от места разгрузки
        destination_radius = input("Радиус поиска от места разгрузки (25-250 миль, по умолчанию 100): ").strip()
        if destination_radius:
            try:
                criteria['destination_radius'] = int(destination_radius)
            except ValueError:
                criteria['destination_radius'] = 100
        
        # Дата готовности к погрузке ОТ
        pickup_date_from = input("Дата готовности к погрузке ОТ (MM/DD/YYYY): ").strip()
        if pickup_date_from:
            criteria['pickup_date_from'] = pickup_date_from
        
        # Дата готовности к погрузке ДО
        pickup_date_to = input("Дата готовности к погрузке ДО (MM/DD/YYYY): ").strip()
        if pickup_date_to:
            criteria['pickup_date_to'] = pickup_date_to
        
        # Дата доставки ОТ
        delivery_date_from = input("Дата доставки ОТ (MM/DD/YYYY): ").strip()
        if delivery_date_from:
            criteria['delivery_date_from'] = delivery_date_from
        
        # Дата доставки ДО
        delivery_date_to = input("Дата доставки ДО (MM/DD/YYYY): ").strip()
        if delivery_date_to:
            criteria['delivery_date_to'] = delivery_date_to
        
        # Вывод настроенных параметров
        print("="*60)
        print("✅ Параметры поиска грузов настроены:")
        for key, value in criteria.items():
            display_key = {
                'capacity_type': 'Тип перевозки',
                'origin_location': 'Место погрузки',
                'origin_radius': 'Радиус от места погрузки',
                'destination_location': 'Место разгрузки', 
                'destination_radius': 'Радиус от места разгрузки',
                'pickup_date_from': 'Дата готовности ОТ',
                'pickup_date_to': 'Дата готовности ДО',
                'delivery_date_from': 'Дата доставки ОТ',
                'delivery_date_to': 'Дата доставки ДО'
            }.get(key, key)
            print(f"  {display_key}: {value}")
        print("="*60)
        
        return criteria

    async def setup_user_filters(self, page: Page, user_criteria: Dict) -> bool:
        """Настройка пользовательских фильтров поиска грузов с улучшенной обработкой ошибок"""
        try:
            logger.info("⚙️ Настройка параметров поиска грузов...")
            
            # Ожидание полной загрузки страницы
            await page.wait_for_load_state('networkidle', timeout=30000)
            await asyncio.sleep(3)
            
            # Ожидание загрузки формы поиска с увеличенным таймаутом
            form_selectors = [
                # Основные селекторы формы поиска на Schneider FreightPower
                "form[name*='search']",
                "form[id*='search']",
                "[data-testid*='search']",
                # Селекторы по структуре страницы поиска грузов
                "form:has(select):has(input)",
                "div:has(select[name*='capacity'])",
                "div:has(input[placeholder*='Origin'])",
                "div:has(input[name*='origin'])",
                "div:has(select[name*='equipment'])",
                ".search-form",
                "#search-form",
                ".search-container",
                ".filter-form",
                # Общие селекторы
                "form",
                "main form",
                ".container form",
                ".content form",
                # Селекторы по наличию специфичных элементов
                "*:has(select:contains('Dry Van'))",
                "*:has(input[placeholder*='City'])",
                "*:has(button:contains('Search'))",
                # Fallback селекторы
                "[role='form']",
                "form[name='searchForm']",
                "[class*='search']",
                "[id*='search']"
            ]
            
            form_found = False
            found_selector = None
            
            # Сначала пробуем быстрый поиск
            for selector in form_selectors:
                try:
                    element = await page.query_selector(selector)
                    if element:
                        is_visible = await element.is_visible()
                        if is_visible:
                            form_found = True
                            found_selector = selector
                            logger.info(f"✅ Найдена форма поиска (быстрый поиск): {selector}")
                            break
                except Exception:
                    continue
            
            # Если быстрый поиск не сработал, пробуем с ожиданием
            if not form_found:
                logger.info("🔍 Быстрый поиск формы не удался, пробуем с ожиданием...")
                for selector in form_selectors:
                    try:
                        await page.wait_for_selector(selector, timeout=5000)
                        form_found = True
                        found_selector = selector
                        logger.info(f"✅ Найдена форма поиска (с ожиданием): {selector}")
                        break
                    except Exception:
                        continue
            
            # Если форма все еще не найдена, пробуем найти любые элементы поиска
            if not form_found:
                logger.info("🔍 Форма поиска не найдена, ищем отдельные элементы...")
                
                # Ищем любые элементы, связанные с поиском
                search_elements = [
                    "select[name*='capacity']",
                    "select:has(option:contains('Dry Van'))",
                    "input[name*='origin']",
                    "input[placeholder*='Origin']",
                    "button:contains('Search')",
                    "select[name*='equipment']"
                ]
                
                elements_found = 0
                for selector in search_elements:
                    try:
                        element = await page.query_selector(selector)
                        if element:
                            is_visible = await element.is_visible()
                            if is_visible:
                                elements_found += 1
                                logger.info(f"✅ Найден элемент поиска: {selector}")
                    except Exception:
                        continue
                
                if elements_found > 0:
                    logger.info(f"✅ Найдено {elements_found} элементов поиска, продолжаем...")
                    form_found = True
                else:
                    logger.warning("⚠️ Элементы поиска не найдены, попытка продолжить...")
            
            if not form_found:
                logger.warning("⚠️ Форма поиска не найдена, попытка продолжить без неё")
                await asyncio.sleep(5)  # Увеличенная пауза
            else:
                await asyncio.sleep(2)
            
            # Настройка типа перевозки
            if user_criteria.get('capacity_type'):
                await self._set_capacity_type(page, user_criteria['capacity_type'])
            
            # Настройка места погрузки
            if user_criteria.get('origin_location'):
                await self._set_location(page, 'origin', user_criteria['origin_location'])
            
            # Настройка радиуса поиска от места погрузки
            if user_criteria.get('origin_radius'):
                await self._set_radius(page, 'origin', user_criteria['origin_radius'])
            
            # Настройка места разгрузки
            if user_criteria.get('destination_location'):
                await self._set_location(page, 'destination', user_criteria['destination_location'])
            
            # Настройка радиуса поиска от места разгрузки
            if user_criteria.get('destination_radius'):
                await self._set_radius(page, 'destination', user_criteria['destination_radius'])
            
            # Настройка даты готовности к погрузке ОТ
            if user_criteria.get('pickup_date_from'):
                await self._set_date(page, 'pickup_from', user_criteria['pickup_date_from'])
            
            # Настройка даты готовности к погрузке ДО
            if user_criteria.get('pickup_date_to'):
                await self._set_date(page, 'pickup_to', user_criteria['pickup_date_to'])
            
            # Настройка даты доставки ОТ
            if user_criteria.get('delivery_date_from'):
                await self._set_date(page, 'delivery_from', user_criteria['delivery_date_from'])
            
            # Настройка даты доставки ДО
            if user_criteria.get('delivery_date_to'):
                await self._set_date(page, 'delivery_to', user_criteria['delivery_date_to'])
            
            # Выполняем поиск после настройки всех параметров
            await self._execute_search_button(page)
            
            logger.info("✅ Параметры поиска грузов настроены успешно")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка настройки параметров поиска грузов: {e}")
            return False

    async def _set_capacity_type(self, page: Page, capacity_type: str) -> None:
        """Настройка типа перевозки (транспорта) с улучшенным поиском"""
        try:
            logger.info(f"🚛 Настройка типа перевозки: {capacity_type}")
            
            # Ожидание загрузки элементов
            await asyncio.sleep(2)
            
            # Расширенный список селекторов для поиска типа перевозки
            capacity_selectors = [
                # Основные селекторы для Schneider FreightPower
                "select[id*='capacity']",
                "select[name*='capacity']",
                "select[data-testid*='capacity']",
                "select[class*='capacity']",
                
                # Общие селекторы для выпадающих списков оборудования
                "select[name*='equipment']",
                "select[id*='equipment']",
                "select[class*='equipment']",
                "select[name*='trailer']",
                "select[id*='trailer']",
                "select[class*='trailer']",
                "select[name*='truck']",
                "select[name*='vehicle']",
                
                # Селекторы по содержимому опций (самые надежные)
                "select:has(option[value*='Dry Van'])",
                "select:has(option:contains('Dry Van'))",
                "select:has(option:contains('Reefer'))",
                "select:has(option:contains('Flatbed'))",
                "select:has(option:contains('Van'))",
                
                # Селекторы по placeholder или label
                "select[placeholder*='equipment']",
                "select[placeholder*='capacity']",
                "select[aria-label*='equipment']",
                "select[aria-label*='capacity']",
                
                # Структурные селекторы
                ".capacity-type select",
                ".equipment-type select",
                ".trailer-type select",
                "[data-testid='capacity-select']",
                "[data-testid='equipment-select']",
                
                # Позиционные селекторы (первый select часто тип оборудования)
                "form select:first-of-type",
                "form select:nth-of-type(1)",
                ".form-group:first-of-type select",
                
                # Общие селекторы
                "select",  # Последний fallback - все селекты
            ]
            
            success = False
            
            # Сначала пробуем найти селект быстрым поиском
            for selector in capacity_selectors:
                try:
                    elements = await page.query_selector_all(selector)
                    for element in elements:
                        if not element:
                            continue
                            
                        # Проверяем видимость элемента
                        is_visible = await element.is_visible()
                        if not is_visible:
                            continue
                        
                        # Получаем опции селекта
                        options = await element.query_selector_all('option')
                        if not options:
                            continue
                            
                        option_texts = []
                        option_values = []
                        for option in options:
                            text = await option.text_content()
                            value = await option.get_attribute('value')
                            option_texts.append(text.strip() if text else "")
                            option_values.append(value.strip() if value else "")
                        
                        # Проверяем, есть ли в опциях типы оборудования
                        equipment_keywords = ['dry van', 'reefer', 'flatbed', 'van', 'trailer', 'truck']
                        has_equipment = any(
                            keyword in ' '.join(option_texts).lower() 
                            for keyword in equipment_keywords
                        )
                        
                        if not has_equipment and selector != "select":  # Пропускаем если нет типов оборудования (кроме fallback)
                            continue
                            
                        logger.info(f"🔍 Найден селект типа перевозки ({selector}): {option_texts}")
                        
                        # Пытаемся установить значение разными способами
                        success = await self._try_set_select_value(element, capacity_type, option_texts, option_values)
                        
                        if success:
                            logger.info(f"✅ Тип перевозки установлен: {capacity_type}")
                            return
                        else:
                            logger.debug(f"⚠️ Не удалось установить '{capacity_type}' в селекте с опциями: {option_texts}")
                            
                except Exception as e:
                    logger.debug(f"Селектор '{selector}' не сработал: {e}")
                    continue
            
            # Если быстрый поиск не сработал, пробуем с ожиданием
            if not success:
                logger.info("🔍 Быстрый поиск не удался, пробуем с ожиданием...")
                for selector in capacity_selectors[:10]:  # Ограничиваем количество для ожидания
                    try:
                        element = await page.wait_for_selector(selector, timeout=3000)
                        if element:
                            is_visible = await element.is_visible()
                            if not is_visible:
                                continue
                                
                            options = await element.query_selector_all('option')
                            option_texts = []
                            option_values = []
                            for option in options:
                                text = await option.text_content()
                                value = await option.get_attribute('value')
                                option_texts.append(text.strip() if text else "")
                                option_values.append(value.strip() if value else "")
                            
                            logger.info(f"🔍 Найден селект (с ожиданием): {option_texts}")
                            
                            success = await self._try_set_select_value(element, capacity_type, option_texts, option_values)
                            
                            if success:
                                logger.info(f"✅ Тип перевозки установлен: {capacity_type}")
                                return
                                
                    except Exception as e:
                        logger.debug(f"Селектор '{selector}' не сработал с ожиданием: {e}")
                        continue
            
            logger.warning(f"⚠️ Не удалось найти селект для типа перевозки: {capacity_type}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка настройки типа перевозки: {e}")
    
    async def _try_set_select_value(self, element, target_value: str, option_texts: list, option_values: list) -> bool:
        """Попытка установить значение в селекте разными способами"""
        try:
            # Способ 1: по точному тексту
            try:
                await element.select_option(label=target_value)
                return True
            except Exception:
                pass
            
            # Способ 2: по значению
            try:
                await element.select_option(value=target_value)
                return True
            except Exception:
                pass
            
            # Способ 3: поиск похожей опции по тексту
            for option_text in option_texts:
                if target_value.lower() in option_text.lower() or option_text.lower() in target_value.lower():
                    try:
                        await element.select_option(label=option_text)
                        logger.info(f"✅ Использована похожая опция: '{option_text}' для '{target_value}'")
                        return True
                    except Exception:
                        continue
            
            # Способ 4: поиск по частичному совпадению (для "Dry Van")
            if "dry" in target_value.lower() and "van" in target_value.lower():
                for option_text in option_texts:
                    if "dry" in option_text.lower() and "van" in option_text.lower():
                        try:
                            await element.select_option(label=option_text)
                            logger.info(f"✅ Найдена опция Dry Van: '{option_text}'")
                            return True
                        except Exception:
                            continue
            
            # Способ 5: поиск по значению с частичным совпадением
            for i, (value, text) in enumerate(zip(option_values, option_texts)):
                if (target_value.lower() in value.lower() or 
                    target_value.lower() in text.lower() or
                    any(word in text.lower() for word in target_value.lower().split())):
                    try:
                        if value:
                            await element.select_option(value=value)
                        else:
                            await element.select_option(index=i)
                        logger.info(f"✅ Использована опция по частичному совпадению: '{text}' (value='{value}')")
                        return True
                    except Exception:
                        continue
            
            return False
            
        except Exception as e:
            logger.debug(f"Ошибка при установке значения в селект: {e}")
            return False

    async def _set_location(self, page: Page, location_type: str, location: str) -> None:
        """Настройка места отправления или назначения"""
        try:
            # Определяем селекторы в зависимости от типа локации
            if location_type.lower() == 'origin':
                location_selectors = [
                    # Селекторы для Origin на основе реальной структуры
                    "input[name*='origin']",
                    "input[id*='origin']",
                    "input[placeholder*='Origin']",
                    "input[placeholder*='Romeoville']",
                    "[data-testid*='origin']",
                    ".origin input",
                    ".origin-location input",
                    # Селекторы по позиции (Origin обычно первое поле)
                    "form input[type='text']:nth-of-type(1)",
                    "form input:first-of-type",
                    # Общие селекторы
                    "input[name*='pickup']",
                    "input[placeholder*='pickup']"
                ]
            else:  # destination
                location_selectors = [
                    # Селекторы для Destination на основе реальной структуры
                    "input[name*='destination']",
                    "input[id*='destination']",
                    "input[placeholder*='Destination']",
                    "input[placeholder*='Dayville']",
                    "[data-testid*='destination']",
                    ".destination input",
                    ".destination-location input",
                    # Селекторы по позиции (Destination обычно второе поле)
                    "form input[type='text']:nth-of-type(2)",
                    # Общие селекторы
                    "input[name*='delivery']",
                    "input[placeholder*='delivery']"
                ]
            
            success = False
            for selector in location_selectors:
                try:
                    element = await page.wait_for_selector(selector, timeout=3000)
                    if element:
                        # Проверяем, что это правильное поле
                        placeholder = await element.get_attribute('placeholder')
                        name = await element.get_attribute('name')
                        element_id = await element.get_attribute('id')
                        
                        logger.info(f"🔍 Найдено поле: placeholder='{placeholder}', name='{name}', id='{element_id}'")
                        
                        # Очищаем поле и вводим новое значение
                        await element.click()
                        await element.clear()
                        await asyncio.sleep(0.5)
                        await element.type(location)
                        await asyncio.sleep(1.5)
                        
                        # Ждем появления выпадающего списка автодополнения
                        try:
                            # Различные селекторы для выпадающих списков автодополнения
                            autocomplete_selectors = [
                                ".autocomplete-option",
                                ".dropdown-item",
                                ".suggestion",
                                ".typeahead-option",
                                "[role='option']",
                                ".ui-menu-item",
                                ".location-option"
                            ]
                            
                            autocomplete_found = False
                            for ac_selector in autocomplete_selectors:
                                try:
                                    await page.wait_for_selector(ac_selector, timeout=2000)
                                    await asyncio.sleep(0.5)
                                    await page.click(f"{ac_selector}:first-child")
                                    autocomplete_found = True
                                    logger.info(f"✅ Выбрана опция из автодополнения для {location_type}")
                                    break
                                except Exception:
                                    continue
                            
                            if not autocomplete_found:
                                # Если автодополнение не найдено, нажимаем Enter
                                await element.press("Enter")
                                logger.info(f"✅ Нажат Enter для подтверждения {location_type}")
                                
                        except Exception:
                            # Fallback - просто нажимаем Enter
                            await element.press("Enter")
                            logger.info(f"✅ Fallback: нажат Enter для {location_type}")
                        
                        await asyncio.sleep(1)
                        
                        # Проверяем, что значение установлено
                        current_value = await element.input_value()
                        if current_value and (location.lower() in current_value.lower() or current_value.lower() in location.lower()):
                            logger.info(f"✅ Место {location_type} установлено: {location} (текущее значение: {current_value})")
                            success = True
                            break
                        else:
                            logger.warning(f"⚠️ Значение не установилось корректно для {location_type}: ожидалось '{location}', получено '{current_value}'")
                            
                except Exception as e:
                    logger.debug(f"Селектор '{selector}' не сработал для {location_type}: {e}")
                    continue
            
            if not success:
                logger.warning(f"⚠️ Не удалось установить место {location_type}: {location}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка настройки места {location_type}: {e}")

    async def _set_radius(self, page: Page, location_type: str, radius: int) -> None:
        """Настройка радиуса поиска с поддержкой счетчиков (кнопки +/-)"""
        try:
            logger.info(f"🔧 Настройка радиуса {location_type} на {radius} миль...")
            
            # Сначала пробуем найти поле радиуса как счетчик (stepper/spinner)
            success = await self._set_radius_stepper(page, location_type, radius)
            
            # Если счетчик не сработал, пробуем обычный select
            if not success:
                success = await self._set_radius_select(page, location_type, radius)
            
            if not success:
                logger.warning(f"⚠️ Не удалось установить радиус {radius} для {location_type}")
                    
        except Exception as e:
            logger.error(f"❌ Ошибка настройки радиуса {location_type}: {e}")
    
    async def _set_radius_stepper(self, page: Page, location_type: str, radius: int) -> bool:
        """Настройка радиуса через кнопки +/- (stepper/spinner)"""
        try:
            # Определяем селекторы для поиска полей радиуса и кнопок
            if location_type.lower() == 'origin':
                field_selectors = [
                    # Селекторы для Origin Radius поля
                    "input[name*='origin'][name*='radius']",
                    "input[id*='origin'][id*='radius']",
                    "[data-testid*='origin-radius'] input",
                    ".origin-radius input",
                    "input[placeholder*='radius']:first-of-type",
                    "input[type='number']:first-of-type",
                    # Поиск по позиции - первое числовое поле после origin
                    "form input[type='number']:first-of-type",
                    "form input[min='25'][max='250']:first-of-type"
                ]
            else:  # destination
                field_selectors = [
                    # Селекторы для Destination Radius поля
                    "input[name*='destination'][name*='radius']",
                    "input[id*='destination'][id*='radius']",
                    "[data-testid*='destination-radius'] input",
                    ".destination-radius input",
                    "input[placeholder*='radius']:nth-of-type(2)",
                    "input[type='number']:nth-of-type(2)",
                    # Поиск по позиции - второе числовое поле после destination
                    "form input[type='number']:nth-of-type(2)",
                    "form input[min='25'][max='250']:nth-of-type(2)"
                ]
            
            # Ищем поле радиуса
            radius_field = None
            for selector in field_selectors:
                try:
                    radius_field = await page.wait_for_selector(selector, timeout=2000)
                    if radius_field:
                        logger.info(f"🎯 Найдено поле радиуса {location_type}: {selector}")
                        break
                except Exception:
                    continue
            
            if not radius_field:
                logger.debug(f"🔍 Поле радиуса {location_type} не найдено как stepper")
                return False
            
            # Получаем текущее значение
            current_value_str = await radius_field.get_attribute('value') or await radius_field.input_value()
            try:
                current_value = int(current_value_str) if current_value_str else 25  # Начальное значение по умолчанию
            except ValueError:
                current_value = 25
            
            logger.info(f"📊 Текущее значение радиуса {location_type}: {current_value}")
            
            # Если значение уже правильное, ничего не делаем
            if current_value == radius:
                logger.info(f"✅ Радиус {location_type} уже установлен: {radius}")
                return True
            
            # Ищем кнопки +/- рядом с полем
            plus_button = None
            minus_button = None
            
            # Селекторы для кнопок увеличения/уменьшения
            plus_selectors = [
                # Рядом с полем радиуса
                f"{field_selectors[0]} + button",  # Кнопка сразу после поля
                f"{field_selectors[0]} ~ button:contains('+')",
                f"{field_selectors[0]} ~ button[aria-label*='increase']",
                f"{field_selectors[0]} ~ button[title*='increase']",
                # В том же контейнере
                f"{field_selectors[0]} .. button:contains('+')",
                f"{field_selectors[0]} .. button[class*='plus']",
                f"{field_selectors[0]} .. button[class*='increment']",
                # Общие селекторы
                "button:contains('+'):visible",
                "button[class*='plus']:visible",
                "button[class*='increment']:visible",
                "button[aria-label*='increase']:visible"
            ]
            
            minus_selectors = [
                # Рядом с полем радиуса
                f"{field_selectors[0]} + button:contains('-')",
                f"{field_selectors[0]} ~ button:contains('-')",
                f"{field_selectors[0]} ~ button[aria-label*='decrease']",
                f"{field_selectors[0]} ~ button[title*='decrease']",
                # В том же контейнере
                f"{field_selectors[0]} .. button:contains('-')",
                f"{field_selectors[0]} .. button[class*='minus']",
                f"{field_selectors[0]} .. button[class*='decrement']",
                # Общие селекторы
                "button:contains('-'):visible",
                "button[class*='minus']:visible",
                "button[class*='decrement']:visible",
                "button[aria-label*='decrease']:visible"
            ]
            
            # Ищем кнопку + 
            for selector in plus_selectors:
                try:
                    plus_button = await page.query_selector(selector)
                    if plus_button:
                        # Проверяем, что кнопка видима и кликабельна
                        is_visible = await plus_button.is_visible()
                        if is_visible:
                            logger.info(f"🎯 Найдена кнопка '+' для {location_type}: {selector}")
                            break
                except Exception:
                    continue
            
            # Ищем кнопку -
            for selector in minus_selectors:
                try:
                    minus_button = await page.query_selector(selector)
                    if minus_button:
                        # Проверяем, что кнопка видима и кликабельна
                        is_visible = await minus_button.is_visible()
                        if is_visible:
                            logger.info(f"🎯 Найдена кнопка '-' для {location_type}: {selector}")
                            break
                except Exception:
                    continue
            
            # Если кнопки не найдены, пробуем найти их по DOM-структуре
            if not plus_button or not minus_button:
                # Ищем родительский контейнер поля
                parent_container = await radius_field.evaluate("""
                    field => {
                        let parent = field.parentElement;
                        while (parent && parent !== document.body) {
                            const buttons = parent.querySelectorAll('button');
                            if (buttons.length >= 2) {
                                return parent;
                            }
                            parent = parent.parentElement;
                        }
                        return null;
                    }
                """)
                
                if parent_container:
                    # Ищем кнопки в контейнере
                    buttons = await parent_container.query_selector_all('button')
                    for button in buttons:
                        text = await button.text_content()
                        if '+' in text and not plus_button:
                            plus_button = button
                        elif '-' in text and not minus_button:
                            minus_button = button
            
            # Если кнопки не найдены, возвращаем False
            if not plus_button:
                logger.debug(f"🔍 Кнопка '+' для радиуса {location_type} не найдена")
                return False
            
            # Определяем, нужно увеличивать или уменьшать
            if current_value < radius:
                # Нужно увеличивать
                clicks_needed = radius - current_value
                button_to_use = plus_button
                action = "увеличение"
            else:
                # Нужно уменьшать
                clicks_needed = current_value - radius
                button_to_use = minus_button
                action = "уменьшение"
                if not minus_button:
                    logger.warning(f"⚠️ Кнопка '-' для уменьшения радиуса {location_type} не найдена")
                    return False
            
            logger.info(f"🔄 {action} радиуса {location_type} с {current_value} до {radius} ({clicks_needed} кликов)")
            
            # Кликаем нужное количество раз
            for i in range(clicks_needed):
                try:
                    await button_to_use.click()
                    await page.wait_for_timeout(200)  # Небольшая пауза между кликами
                    
                    # Проверяем новое значение каждые несколько кликов
                    if i % 5 == 4:  # Каждые 5 кликов
                        new_value_str = await radius_field.get_attribute('value') or await radius_field.input_value()
                        try:
                            new_value = int(new_value_str) if new_value_str else current_value
                            logger.info(f"📊 Прогресс: {new_value} (клик {i+1}/{clicks_needed})")
                            if new_value == radius:
                                logger.info(f"✅ Достигнуто целевое значение радиуса {location_type}: {radius}")
                                return True
                        except ValueError:
                            pass
                            
                except Exception as e:
                    logger.error(f"❌ Ошибка при клике по кнопке {action}: {e}")
                    return False
            
            # Финальная проверка значения
            final_value_str = await radius_field.get_attribute('value') or await radius_field.input_value()
            try:
                final_value = int(final_value_str) if final_value_str else current_value
                if final_value == radius:
                    logger.info(f"✅ Радиус {location_type} успешно установлен через stepper: {radius}")
                    return True
                else:
                    logger.warning(f"⚠️ Радиус {location_type} установлен неточно: {final_value} вместо {radius}")
                    return False
            except ValueError:
                logger.warning(f"⚠️ Не удалось прочитать финальное значение радиуса {location_type}")
                return False
                
        except Exception as e:
            logger.debug(f"🔍 Ошибка настройки радиуса {location_type} через stepper: {e}")
            return False
    
    async def _set_radius_select(self, page: Page, location_type: str, radius: int) -> bool:
        """Настройка радиуса через обычный select (fallback)"""
        try:
            # Поиск селектора радиуса на основе реальной структуры сайта
            if location_type.lower() == 'origin':
                radius_selectors = [
                    # Селекторы для Origin Radius
                    "select[name*='origin'][name*='radius']",
                    "select[id*='origin'][id*='radius']",
                    "[data-testid*='origin-radius']",
                    ".origin-radius select",
                    # Селекторы по позиции (Origin radius обычно первый)
                    "form select[name*='radius']:first-of-type",
                    # Общие селекторы радиуса
                    "select:has(option[value='25']):has(option[value='250'])",
                    "select:has(option:contains('25mi')):has(option:contains('250mi'))"
                ]
            else:  # destination
                radius_selectors = [
                    # Селекторы для Destination Radius
                    "select[name*='destination'][name*='radius']",
                    "select[id*='destination'][id*='radius']", 
                    "[data-testid*='destination-radius']",
                    ".destination-radius select",
                    # Селекторы по позиции (Destination radius обычно второй)
                    "form select[name*='radius']:nth-of-type(2)",
                    # Общие селекторы радиуса
                    "select:has(option[value='25']):has(option[value='250'])",
                    "select:has(option:contains('25mi')):has(option:contains('250mi'))"
                ]
            
            for selector in radius_selectors:
                try:
                    element = await page.wait_for_selector(selector, timeout=3000)
                    if element:
                        # Получаем список доступных опций
                        options = await element.query_selector_all('option')
                        option_values = []
                        option_texts = []
                        for option in options:
                            value = await option.get_attribute('value')
                            text = await option.text_content()
                            option_values.append(value.strip() if value else "")
                            option_texts.append(text.strip() if text else "")
                        
                        logger.info(f"🔍 Найденные опции радиуса для {location_type}: values={option_values}, texts={option_texts}")
                        
                        # Пытаемся установить радиус разными способами
                        radius_str = str(radius)
                        
                        # Способ 1: по значению
                        try:
                            await element.select_option(value=radius_str)
                            logger.info(f"✅ Радиус {location_type} установлен по значению: {radius}")
                            return True
                        except Exception:
                            pass
                        
                        # Способ 2: по тексту с 'mi'
                        try:
                            await element.select_option(label=f"{radius}mi")
                            logger.info(f"✅ Радиус {location_type} установлен по тексту: {radius}mi")
                            return True
                        except Exception:
                            pass
                        
                        # Способ 3: поиск похожей опции
                        for i, (value, text) in enumerate(zip(option_values, option_texts)):
                            if (radius_str in value or radius_str in text or 
                                f"{radius}mi" in text or f"{radius}" in text):
                                try:
                                    if value:
                                        await element.select_option(value=value)
                                    else:
                                        await element.select_option(index=i)
                                    logger.info(f"✅ Радиус {location_type} установлен через похожую опцию: '{text}' (value='{value}')")
                                    return True
                                except Exception:
                                    continue
                        
                        logger.warning(f"⚠️ Не удалось установить радиус {radius} для {location_type}. Доступные опции: {option_texts}")
                            
                except Exception as e:
                    logger.debug(f"Селектор '{selector}' не сработал для радиуса {location_type}: {e}")
                    continue
            
            return False
                    
        except Exception as e:
            logger.debug(f"🔍 Ошибка настройки радиуса {location_type} через select: {e}")
            return False

    async def _set_date(self, page: Page, date_type: str, date_value: str) -> None:
        """Настройка дат отправления или доставки"""
        try:
            # Конвертируем формат даты из DD.MM.YYYY в MM/DD/YYYY
            formatted_date = self._format_date(date_value)
            
            # Определяем селекторы в зависимости от типа даты
            if 'pickup' in date_type.lower() or 'from' in date_type.lower():
                date_selectors = [
                    # Селекторы для дат отправления (Pick-Up Date)
                    "input[name*='pickup'][name*='from']",
                    "input[name*='pickup'][name*='start']",
                    "input[id*='pickup'][id*='from']",
                    "input[placeholder*='Aug 21']",
                    "input[placeholder*='pickup']",
                    "[data-testid*='pickup-from']",
                    "[data-testid*='pickup-start']",
                    # Селекторы по позиции (первая дата)
                    "form input[type='date']:first-of-type",
                    "form input[placeholder*='Aug']:first-of-type",
                    # Общие селекторы дат
                    "input[name*='date']:first-of-type",
                    ".date-picker:first-of-type input"
                ]
            elif 'pickup' in date_type.lower() and ('to' in date_type.lower() or 'end' in date_type.lower()):
                date_selectors = [
                    # Селекторы для дат отправления ДО (Pick-Up Date To)
                    "input[name*='pickup'][name*='to']",
                    "input[name*='pickup'][name*='end']",
                    "input[id*='pickup'][id*='to']",
                    "input[placeholder*='Aug 23']",
                    "[data-testid*='pickup-to']",
                    "[data-testid*='pickup-end']",
                    # Селекторы по позиции (вторая дата)
                    "form input[type='date']:nth-of-type(2)",
                    "form input[placeholder*='Aug']:nth-of-type(2)"
                ]
            elif 'delivery' in date_type.lower() or 'destination' in date_type.lower():
                if 'from' in date_type.lower() or 'start' in date_type.lower():
                    date_selectors = [
                        # Селекторы для дат доставки ОТ
                        "input[name*='delivery'][name*='from']",
                        "input[name*='delivery'][name*='start']",
                        "input[id*='delivery'][id*='from']",
                        "input[placeholder*='delivery']",
                        "[data-testid*='delivery-from']",
                        # Селекторы по позиции (третья дата)
                        "form input[type='date']:nth-of-type(3)"
                    ]
                else:  # delivery to
                    date_selectors = [
                        # Селекторы для дат доставки ДО
                        "input[name*='delivery'][name*='to']",
                        "input[name*='delivery'][name*='end']",
                        "input[id*='delivery'][id*='to']",
                        "input[placeholder*='Aug 29']",
                        "[data-testid*='delivery-to']",
                        # Селекторы по позиции (четвертая дата)
                        "form input[type='date']:nth-of-type(4)"
                    ]
            else:
                # Общие селекторы дат
                date_selectors = [
                    f"input[name*='{date_type}']",
                    f"[data-testid='{date_type}']",
                    f"input[placeholder*='{date_type.replace('_', ' ').title()}']",
                    "input[type='date']",
                    "input[placeholder*='Aug']"
                ]
            
            success = False
            for selector in date_selectors:
                try:
                    element = await page.wait_for_selector(selector, timeout=3000)
                    if element:
                        # Получаем информацию о поле
                        placeholder = await element.get_attribute('placeholder')
                        name = await element.get_attribute('name')
                        element_id = await element.get_attribute('id')
                        input_type = await element.get_attribute('type')
                        
                        logger.info(f"🔍 Найдено поле даты: type='{input_type}', placeholder='{placeholder}', name='{name}', id='{element_id}'")
                        
                        # Очищаем поле и устанавливаем дату
                        await element.click()
                        await element.clear()
                        await asyncio.sleep(0.5)
                        
                        # Вводим дату в зависимости от типа поля
                        if input_type == 'date':
                            # Для полей типа date используем формат YYYY-MM-DD
                            iso_date = self._convert_to_iso_date(date_value)
                            await element.fill(iso_date)
                        else:
                            # Для текстовых полей используем MM/DD/YYYY
                            await element.type(formatted_date)
                        
                        await asyncio.sleep(0.5)
                        await element.press("Tab")  # Переходим к следующему полю для подтверждения
                        
                        # Проверяем, что дата установлена
                        current_value = await element.input_value()
                        if current_value:
                            logger.info(f"✅ Дата {date_type} установлена: {formatted_date} (текущее значение: {current_value})")
                            success = True
                            break
                        else:
                            logger.warning(f"⚠️ Дата не установилась для {date_type}")
                            
                except Exception as e:
                    logger.debug(f"Селектор '{selector}' не сработал для даты {date_type}: {e}")
                    continue
            
            if not success:
                logger.warning(f"⚠️ Не удалось установить дату {date_type}: {date_value}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка настройки даты {date_type}: {e}")
    
    def _format_date(self, date_str: str) -> str:
        """Конвертирует дату из формата DD.MM.YYYY в MM/DD/YYYY"""
        try:
            if '.' in date_str:
                day, month, year = date_str.split('.')
                return f"{month.zfill(2)}/{day.zfill(2)}/{year}"
            elif '/' in date_str:
                return date_str  # Уже в правильном формате
            else:
                return date_str
        except Exception:
            return date_str
    
    def _convert_to_iso_date(self, date_str: str) -> str:
        """Конвертирует дату в формат ISO (YYYY-MM-DD)"""
        try:
            if '.' in date_str:
                day, month, year = date_str.split('.')
                return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
            elif '/' in date_str:
                month, day, year = date_str.split('/')
                return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
            else:
                return date_str
        except Exception:
            return date_str

    async def _execute_search_button(self, page: Page) -> None:
        """Поиск и клик по кнопке поиска после настройки всех параметров"""
        try:
            logger.info("🔍 Поиск кнопки для выполнения поиска...")
            
            # Селекторы для кнопки поиска
            search_button_selectors = [
                # Основные селекторы кнопки поиска
                "button[type='submit']",
                "input[type='submit']",
                "button:contains('Search')",
                "button:contains('Find')",
                "button:contains('Go')",
                # Селекторы по тексту на русском
                "button:contains('Поиск')",
                "button:contains('Найти')",
                # Селекторы по ID и классам
                "button[id*='search']",
                "button[class*='search']",
                "button[name*='search']",
                "[data-testid*='search-button']",
                ".search-button",
                "#search-button",
                # Общие селекторы кнопок в форме
                "form button:last-of-type",
                "form input[type='submit']:last-of-type",
                ".btn-primary",
                ".btn-search",
                # Fallback селекторы
                "button[role='button']:last-of-type",
                ".button:last-of-type"
            ]
            
            success = False
            for selector in search_button_selectors:
                try:
                    element = await page.wait_for_selector(selector, timeout=2000)
                    if element:
                        # Проверяем, что элемент видим и кликабелен
                        is_visible = await element.is_visible()
                        is_enabled = await element.is_enabled()
                        
                        if is_visible and is_enabled:
                            # Получаем текст кнопки для подтверждения
                            button_text = await element.text_content()
                            logger.info(f"🔍 Найдена кнопка поиска: '{button_text}' (селектор: {selector})")
                            
                            # Кликаем по кнопке
                            await element.click()
                            await asyncio.sleep(2)  # Ждем начала поиска
                            
                            logger.info("✅ Кнопка поиска нажата, запущен поиск грузов")
                            success = True
                            break
                        else:
                            logger.debug(f"Кнопка найдена, но не кликабельна: visible={is_visible}, enabled={is_enabled}")
                            
                except Exception as e:
                    logger.debug(f"Селектор '{selector}' не сработал для кнопки поиска: {e}")
                    continue
            
            if not success:
                logger.warning("⚠️ Не удалось найти кнопку поиска, попробуем нажать Enter на последнем активном поле")
                # Fallback - нажимаем Enter на активном элементе
                try:
                    await page.keyboard.press("Enter")
                    await asyncio.sleep(2)
                    logger.info("✅ Нажат Enter для запуска поиска")
                except Exception as e:
                    logger.error(f"❌ Не удалось запустить поиск: {e}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка выполнения поиска: {e}")

    async def execute_search(self, page: Page) -> bool:
        """Выполнение поиска доступных грузов с оптимизацией"""
        try:
            logger.info("🔍 Выполнение поиска доступных грузов...")
            
            # Поиск кнопки поиска с оптимизированными селекторами
            search_selectors = [
                "button[type='submit']",
                "button:has-text('Search')",
                "button:has-text('Find Loads')",
                "input[type='submit'][value*='Search']",
                "[data-testid='search-button']",
                ".search-button"
            ]
            
            search_button = None
            for selector in search_selectors:
                try:
                    search_button = await page.wait_for_selector(selector, timeout=3000)
                    if search_button and await search_button.is_visible():
                        break
                except Exception:
                    continue
            
            if search_button:
                await search_button.click()
                logger.info("✅ Поиск запущен")
                
                # Ожидание результатов с оптимизированным таймаутом
                await page.wait_for_selector(
                    ".results, .load-results, [data-testid='search-results']", 
                    timeout=15000  # Увеличен таймаут
                )
                
                logger.info("✅ Результаты поиска загружены")
                return True
            else:
                logger.error("❌ Кнопка поиска не найдена")
                return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка выполнения поиска: {e}")
            return False

    async def scan_search_results(self, page: Page) -> List[Dict]:
        """Сканирование результатов поиска"""
        try:
            logger.info("🔍 Сканирование результатов поиска...")
            
            # Ожидание загрузки результатов
            await page.wait_for_selector(".results, .load-results, [data-testid='search-results']", timeout=10000)
            await asyncio.sleep(2)
            
            # Используем существующую логику сканирования
            loads = await self.scan_loads_page(page)
            
            logger.info(f"✅ Найдено {len(loads)} грузов в результатах поиска")
            return loads
            
        except Exception as e:
            logger.error(f"❌ Ошибка сканирования результатов поиска: {e}")
            return []

    async def refresh_search_results(self, page: Page) -> bool:
        """Обновление результатов поиска"""
        try:
            # Обновление страницы
            await page.reload(wait_until='networkidle')
            await asyncio.sleep(1)
            
            # Или поиск кнопки обновления
            refresh_selectors = [
                "button:has-text('Refresh')",
                "[data-testid='refresh-button']",
                ".refresh-button"
            ]
            
            for selector in refresh_selectors:
                try:
                    button = await page.wait_for_selector(selector, timeout=2000)
                    if button:
                        await button.click()
                        await page.wait_for_load_state('networkidle')
                        return True
                except Exception:
                    continue
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка обновления результатов поиска: {e}")
            return False

    async def parse_load_results(self, page: Page) -> List[Dict]:
        """Парсинг результатов поиска грузов с улучшенной терминологией"""
        try:
            logger.info("📊 Анализ результатов поиска грузов...")
            
            loads = []
            
            # Поиск элементов грузов
            load_elements = await page.query_selector_all(
                ".load-item, .freight-item, [data-testid='load-card'], .result-row"
            )
            
            for element in load_elements:
                try:
                    load_data = {}
                    
                    # Извлечение информации о грузе
                    origin = await element.query_selector(".origin, .pickup-location")
                    if origin:
                        load_data['pickup_location'] = await origin.text_content()
                    
                    destination = await element.query_selector(".destination, .delivery-location")
                    if destination:
                        load_data['delivery_location'] = await destination.text_content()
                    
                    rate = await element.query_selector(".rate, .price, .pay")
                    if rate:
                        load_data['freight_rate'] = await rate.text_content()
                    
                    distance = await element.query_selector(".distance, .miles")
                    if distance:
                        load_data['total_miles'] = await distance.text_content()
                    
                    pickup_date = await element.query_selector(".pickup-date, .ready-date")
                    if pickup_date:
                        load_data['pickup_date'] = await pickup_date.text_content()
                    
                    delivery_date = await element.query_selector(".delivery-date, .due-date")
                    if delivery_date:
                        load_data['delivery_date'] = await delivery_date.text_content()
                    
                    equipment = await element.query_selector(".equipment, .trailer-type")
                    if equipment:
                        load_data['equipment_type'] = await equipment.text_content()
                    
                    weight = await element.query_selector(".weight")
                    if weight:
                        load_data['cargo_weight'] = await weight.text_content()
                    
                    if load_data:
                        loads.append(load_data)
                        
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка парсинга груза: {e}")
                    continue
            
            logger.info(f"✅ Найдено грузов: {len(loads)}")
            return loads
            
        except Exception as e:
            logger.error(f"❌ Ошибка парсинга результатов: {e}")
            return []
