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
            
            # Ожидание загрузки формы поиска с увеличенным таймаутом
            form_selectors = [
                "form",
                "[data-testid='search-form']",
                ".search-form",
                "#search-form",
                "form[name='searchForm']"
            ]
            
            form_found = False
            for selector in form_selectors:
                try:
                    await page.wait_for_selector(selector, timeout=15000)
                    form_found = True
                    logger.info(f"✅ Найдена форма поиска: {selector}")
                    break
                except Exception:
                    continue
            
            if not form_found:
                logger.warning("⚠️ Форма поиска не найдена, попытка продолжить без неё")
                # Попробуем найти отдельные поля поиска
                await asyncio.sleep(3)
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
            
            logger.info("✅ Параметры поиска грузов настроены успешно")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка настройки параметров поиска грузов: {e}")
            return False

    async def _set_capacity_type(self, page: Page, capacity_type: str) -> None:
        """Настройка типа перевозки (транспорта)"""
        try:
            # Поиск селектора типа перевозки
            capacity_selectors = [
                "select[name*='capacity']",
                "select[name*='equipment']",
                "select[name*='trailer']",
                "[data-testid='capacity-select']",
                ".capacity-type select"
            ]
            
            for selector in capacity_selectors:
                try:
                    element = await page.wait_for_selector(selector, timeout=3000)
                    if element:
                        await element.select_option(label=capacity_type)
                        logger.info(f"✅ Тип перевозки установлен: {capacity_type}")
                        return
                except Exception:
                    continue
            
            logger.warning(f"⚠️ Не удалось установить тип перевозки: {capacity_type}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка настройки типа перевозки: {e}")

    async def _set_location(self, page: Page, location_type: str, location: str) -> None:
        """Настройка места отправления или назначения"""
        try:
            # Поиск поля ввода места
            location_selectors = [
                "input[name*='origin']",
                "input[name*='destination']",
                "input[placeholder*='Origin']",
                "input[placeholder*='Destination']",
                "[data-testid='origin-input']",
                "[data-testid='destination-input']",
                ".origin-location input",
                ".destination-location input"
            ]
            
            for selector in location_selectors:
                try:
                    element = await page.wait_for_selector(selector, timeout=3000)
                    if element:
                        await element.clear()
                        await element.type(location)
                        await asyncio.sleep(1)
                        
                        # Выбор из выпадающего списка если появился
                        try:
                            await page.wait_for_selector(".autocomplete-option, .dropdown-item", timeout=2000)
                            await page.click(".autocomplete-option:first-child, .dropdown-item:first-child")
                        except:
                            await element.press("Enter")
                        
                        logger.info(f"✅ Место {location_type} установлено: {location}")
                        break
                except Exception:
                    continue
            
        except Exception as e:
            logger.error(f"❌ Ошибка настройки места {location_type}: {e}")

    async def _set_radius(self, page: Page, location_type: str, radius: int) -> None:
        """Настройка радиуса поиска"""
        try:
            # Поиск селектора радиуса
            radius_selectors = [
                f"select[name*='{location_type}'][name*='radius']",
                f".{location_type}-radius select",
                f"[data-testid='{location_type}-radius']"
            ]
            
            for selector in radius_selectors:
                try:
                    element = await page.wait_for_selector(selector, timeout=3000)
                    if element:
                        await element.select_option(value=str(radius))
                        logger.info(f"✅ Радиус {location_type} установлен: {radius} миль")
                        return
                except Exception:
                    continue
                    
        except Exception as e:
            logger.error(f"❌ Ошибка настройки радиуса {location_type}: {e}")

    async def _set_date(self, page: Page, date_type: str, date_value: str) -> None:
        """Настройка дат отправления или доставки"""
        try:
            # Поиск полей дат
            date_selectors = [
                f"input[name*='{date_type}']",
                f"[data-testid='{date_type}']",
                f"input[placeholder*='{date_type.replace('_', ' ').title()}']"
            ]
            
            # Установка даты
            for selector in date_selectors:
                try:
                    element = await page.wait_for_selector(selector, timeout=3000)
                    if element:
                        await element.clear()
                        await element.type(date_value)
                        await asyncio.sleep(0.5)
                        logger.info(f"✅ Дата {date_type} установлена: {date_value}")
                        break
                except Exception:
                    continue
            
        except Exception as e:
            logger.error(f"❌ Ошибка настройки даты {date_type}: {e}")

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
