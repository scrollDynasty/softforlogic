import asyncio
import time
import re
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from playwright.async_api import Page, ElementHandle

from ..utils.logger import logger
from ..utils.rate_calculator import RateCalculator
from ..utils.performance_monitor import PerformanceMonitor
from ..utils.gemini_form_filler import GeminiFormFiller
from .selectors import selector_manager

class LoadParser:
    def __init__(self, config: Dict):
        self.config = config
        self.performance = PerformanceMonitor()
        
        # Инициализация AI помощника для заполнения форм
        self.ai_form_filler = None
        if config.get('ai', {}).get('enable_ai_form_filling', False):
            gemini_api_key = config.get('ai', {}).get('gemini_api_key')
            if gemini_api_key:
                try:
                    self.ai_form_filler = GeminiFormFiller(gemini_api_key)
                    logger.info("🤖 AI помощник для заполнения форм активирован")
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось инициализировать AI помощника: {e}")
            else:
                logger.warning("⚠️ API ключ Gemini не найден в конфигурации")
        
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
            
            # Проверяем текущее состояние страницы
            try:
                current_url = page.url
                logger.info(f"📍 Текущий URL: {current_url}")
                
                # Если уже на странице поиска, не нужно переходить
                if 'search' in current_url.lower():
                    logger.info("✅ Уже находимся на странице поиска")
                    return True
                    
            except Exception as e:
                logger.warning(f"⚠️ Не удалось получить текущий URL: {e}")
            
            # Быстрый переход на главную страницу после авторизации
            logger.info("📍 Переход на главную страницу...")
            try:
                await page.goto("https://freightpower.schneider.com/carrier/app/home", wait_until='domcontentloaded', timeout=15000)
                logger.info("✅ Главная страница загружена")
                
                # Проверяем, что страница действительно загрузилась
                await page.wait_for_timeout(500)
                page_title = await page.title()
                logger.info(f"📄 Заголовок страницы: {page_title}")
                
            except Exception as e:
                logger.error(f"❌ Ошибка загрузки главной страницы: {e}")
                return False
            
            # Сначала попробуем прямой переход - это быстрее и надежнее
            try:
                logger.info("🚀 Попытка прямого перехода на страницу поиска...")
                await page.goto("https://freightpower.schneider.com/carrier/app/search", wait_until='domcontentloaded', timeout=15000)
                
                # Проверяем, что попали на правильную страницу
                await page.wait_for_timeout(1000)  # Небольшая пауза для загрузки
                current_url = page.url
                if 'search' in current_url.lower():
                    logger.info("✅ Прямой переход на страницу поиска успешен")
                    
                    # Дополнительная проверка загрузки элементов страницы
                    try:
                        await page.wait_for_selector("body", timeout=3000)
                        page_title = await page.title()
                        logger.info(f"📄 Заголовок страницы поиска: {page_title}")
                    except Exception as e:
                        logger.warning(f"⚠️ Страница поиска загрузилась не полностью: {e}")
                    
                    return True
                else:
                    logger.warning(f"⚠️ Неожиданный URL после перехода: {current_url}")
            except Exception as e:
                logger.warning(f"⚠️ Прямой переход не удался: {e}")
            
            # Если прямой переход не сработал, ищем ссылку на поиск
            logger.info("🔍 Поиск ссылки на страницу поиска...")
            search_selectors = [
                "a[href*='search']",
                "a:has-text('Search')",
                "[data-testid='search-link']",
                ".nav-link:has-text('Search')",
                "nav a:has-text('Search')"
            ]
            
            search_clicked = False
            for i, selector in enumerate(search_selectors, 1):
                try:
                    logger.info(f"🔍 Проверяем селектор {i}/{len(search_selectors)}: {selector}")
                    search_element = await page.wait_for_selector(selector, timeout=2000)  # Уменьшили таймаут
                    if search_element:
                        logger.info(f"✅ Найден элемент поиска: {selector}")
                        await search_element.click()
                        await page.wait_for_load_state('domcontentloaded', timeout=10000)
                        search_clicked = True
                        logger.info("✅ Переход в раздел Search выполнен")
                        break
                except Exception as e:
                    logger.info(f"⚠️ Селектор {selector} не найден: {e}")
                    continue
            
            if not search_clicked:
                logger.error("❌ Не удалось найти ссылку на поиск и выполнить прямой переход")
                
                # Последняя попытка - проверим, может мы всё-таки на правильной странице
                try:
                    current_url = page.url
                    if 'schneider.com' in current_url:
                        logger.info(f"🔍 Финальная проверка URL: {current_url}")
                        if 'search' in current_url.lower() or 'load' in current_url.lower():
                            logger.info("✅ Возможно, мы всё-таки на странице поиска/грузов")
                            return True
                except Exception:
                    pass
                    
                return False
            
            return True
            
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
        """Настройка пользовательских фильтров поиска грузов с помощью AI"""
        try:
            # Проверяем, доступен ли AI помощник
            if self.ai_form_filler:
                logger.info("🤖 Запуск AI-настройки параметров поиска грузов...")
                
                # Используем AI для заполнения формы
                success = await self.ai_form_filler.fill_search_form(page, user_criteria)
                
                if success:
                    logger.info("✅ Параметры поиска грузов настроены успешно с помощью AI")
                    return True
                else:
                    logger.warning("⚠️ AI не смог настроить все параметры, используем fallback метод")
            else:
                logger.info("🔧 AI помощник недоступен, используем fallback метод")
            
            # В случае неудачи или отсутствия AI используем fallback метод
            return await self._fallback_setup_filters(page, user_criteria)
            
        except Exception as e:
            logger.error(f"❌ Ошибка настройки параметров поиска: {e}")
            # В случае ошибки используем fallback метод
            return await self._fallback_setup_filters(page, user_criteria)

    async def _fallback_setup_filters(self, page: Page, user_criteria: Dict) -> bool:
        """Fallback метод настройки фильтров без AI (упрощенная версия)"""
        try:
            logger.info("🔧 Использование fallback метода настройки фильтров...")
            
            # Быстрое ожидание загрузки страницы
            await page.wait_for_load_state('domcontentloaded', timeout=8000)
            
            # Пытаемся найти и заполнить основные поля быстро
            success_count = 0
            total_attempts = 0
            
            # Попытка настройки типа перевозки
            if user_criteria.get('capacity_type'):
                total_attempts += 1
                if await self._quick_set_capacity_type(page, user_criteria['capacity_type']):
                    success_count += 1
            
            # Попытка настройки места отправления
            if user_criteria.get('origin_location'):
                total_attempts += 1
                if await self._quick_set_location(page, 'origin', user_criteria['origin_location']):
                    success_count += 1
            
            # Попытка настройки места назначения
            if user_criteria.get('destination_location'):
                total_attempts += 1
                if await self._quick_set_location(page, 'destination', user_criteria['destination_location']):
                    success_count += 1
            
            # Попытка выполнить поиск
            total_attempts += 1
            if await self._quick_execute_search(page):
                success_count += 1
            
            success_rate = success_count / total_attempts if total_attempts > 0 else 0
            logger.info(f"📊 Fallback настройка: {success_count}/{total_attempts} ({success_rate:.1%})")
            
            return success_rate >= 0.5  # Считаем успешным если выполнено 50%+ действий
            
        except Exception as e:
            logger.error(f"❌ Ошибка fallback настройки: {e}")
            return False

    async def _quick_set_capacity_type(self, page: Page, capacity_type: str) -> bool:
        """Быстрая настройка типа перевозки"""
        try:
            # Простые селекторы для быстрого поиска
            selectors = ["select:first-of-type", "select[name*='equipment']", "select[name*='capacity']"]
            
            for selector in selectors:
                try:
                    element = await page.wait_for_selector(selector, timeout=3000)
                    if element:
                        await element.select_option(label=capacity_type)
                        return True
                except:
                    continue
            return False
        except:
            return False

    async def _quick_set_location(self, page: Page, location_type: str, location: str) -> bool:
        """Быстрая настройка локации"""
        try:
            # Простые селекторы для поиска полей локации
            if location_type == 'origin':
                selectors = ["input[placeholder*='Origin']", "input[placeholder*='From']", "input[name*='origin']"]
            else:
                selectors = ["input[placeholder*='Destination']", "input[placeholder*='To']", "input[name*='destination']"]
            
            for selector in selectors:
                try:
                    element = await page.wait_for_selector(selector, timeout=3000)
                    if element:
                        await element.fill(location)
                        return True
                except:
                    continue
            return False
        except:
            return False

    async def _quick_execute_search(self, page: Page) -> bool:
        """Быстрый поиск кнопки поиска"""
        try:
            selectors = ["button[type='submit']", "input[type='submit']", "button:contains('Search')", "button:contains('Find')"]
            
            for selector in selectors:
                try:
                    element = await page.wait_for_selector(selector, timeout=3000)
                    if element:
                        await element.click()
                        return True
                except:
                    continue
            return False
        except:
            return False

    async def _set_capacity_type(self, page: Page, capacity_type: str) -> None:
        """Настройка типа перевозки (транспорта)"""
        try:
            logger.info(f"🚛 Настройка типа перевозки: {capacity_type}")
            
            # Расширенные селекторы для Schneider FreightPower
            capacity_selectors = [
                # Основные селекторы для Schneider
                "select[data-testid*='equipment']",
                "select[data-testid*='capacity']",
                "select[data-testid*='trailer']",
                "select[name*='equipmentType']",
                "select[name*='capacity']",
                "select[name*='equipment']",
                "select[id*='capacity']",
                "select[id*='equipment']",
                "select[id*='trailer']",
                # Селекторы по содержимому опций (наиболее надежные)
                "select:has(option[value*='DRY_VAN'])",
                "select:has(option[value*='Dry Van'])",
                "select:has(option:contains('Dry Van'))",
                "select:has(option:contains('Reefer'))",
                "select:has(option:contains('Flatbed'))",
                "select:has(option:contains('Power Only'))",
                # Селекторы по классам
                ".equipment-select select",
                ".capacity-select select",
                ".trailer-type select",
                "[class*='equipment'] select",
                "[class*='capacity'] select",
                # Fallback селекторы
                "form select:first-of-type",
                ".form-group:first-of-type select",
                "div:has(label:contains('Equipment')) select",
                "div:has(label:contains('Capacity')) select"
            ]
            
            for selector in capacity_selectors:
                try:
                    element = await page.wait_for_selector(selector, timeout=1500)  # Уменьшили таймаут
                    if element:
                        # Проверяем, есть ли нужная опция в селекте
                        options = await element.query_selector_all('option')
                        option_data = []
                        
                        for option in options:
                            value = await option.get_attribute('value')
                            text = await option.text_content()
                            option_data.append({
                                'value': value.strip() if value else "",
                                'text': text.strip() if text else ""
                            })
                        
                        option_texts = [opt['text'] for opt in option_data]
                        logger.info(f"🔍 Найденные опции: {option_texts}")
                        
                        # Пытаемся установить значение разными способами
                        success = False
                        
                        # Способ 1: точное совпадение по тексту
                        for opt in option_data:
                            if opt['text'].lower() == capacity_type.lower():
                                try:
                                    await element.select_option(label=opt['text'])
                                    success = True
                                    logger.info(f"✅ Установлено точное совпадение: '{opt['text']}'")
                                    break
                                except Exception:
                                    continue
                        
                        # Способ 2: точное совпадение по значению
                        if not success:
                            for opt in option_data:
                                if opt['value'].lower() == capacity_type.lower():
                                    try:
                                        await element.select_option(value=opt['value'])
                                        success = True
                                        logger.info(f"✅ Установлено по значению: '{opt['value']}'")
                                        break
                                    except Exception:
                                        continue
                        
                        # Способ 3: частичное совпадение
                        if not success:
                            capacity_lower = capacity_type.lower()
                            for opt in option_data:
                                text_lower = opt['text'].lower()
                                value_lower = opt['value'].lower()
                                
                                if (capacity_lower in text_lower or text_lower in capacity_lower or
                                    capacity_lower in value_lower or value_lower in capacity_lower):
                                    try:
                                        if opt['text']:
                                            await element.select_option(label=opt['text'])
                                        else:
                                            await element.select_option(value=opt['value'])
                                        success = True
                                        logger.info(f"✅ Установлено частичное совпадение: '{opt['text']}' для '{capacity_type}'")
                                        break
                                    except Exception:
                                        continue
                        
                        # Способ 4: специальные сокращения для Schneider
                        if not success:
                            type_mappings = {
                                'dry van': ['dry van', 'dryvan', 'van', 'dry_van'],
                                'reefer': ['reefer', 'refrigerated', 'temp controlled'],
                                'flatbed': ['flatbed', 'flat bed', 'flat'],
                                'power only': ['power only', 'power', 'bobtail']
                            }
                            
                            search_terms = type_mappings.get(capacity_type.lower(), [capacity_type.lower()])
                            
                            for opt in option_data:
                                text_lower = opt['text'].lower()
                                value_lower = opt['value'].lower()
                                
                                for term in search_terms:
                                    if term in text_lower or term in value_lower:
                                        try:
                                            if opt['text']:
                                                await element.select_option(label=opt['text'])
                                            else:
                                                await element.select_option(value=opt['value'])
                                            success = True
                                            logger.info(f"✅ Установлено через маппинг: '{opt['text']}' для '{capacity_type}'")
                                            break
                                        except Exception:
                                            continue
                                if success:
                                    break
                        
                        if success:
                            return
                        else:
                            logger.warning(f"⚠️ Не удалось установить '{capacity_type}' в селекте. Доступные опции: {option_texts}")
                            
                except Exception as e:
                    logger.debug(f"Селектор '{selector}' не сработал: {e}")
                    continue
            
            logger.warning(f"⚠️ Не удалось найти селект для типа перевозки: {capacity_type}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка настройки типа перевозки: {e}")

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
                    element = await page.wait_for_selector(selector, timeout=1500)  # Уменьшили таймаут
                    if element:
                        # Проверяем, что это правильное поле
                        placeholder = await element.get_attribute('placeholder')
                        name = await element.get_attribute('name')
                        element_id = await element.get_attribute('id')
                        
                        logger.info(f"🔍 Найдено поле: placeholder='{placeholder}', name='{name}', id='{element_id}'")
                        
                        # Очищаем поле и вводим новое значение
                        await element.click()
                        await element.clear()
                        await page.wait_for_timeout(200)  # Было 500
                        await element.type(location)
                        await page.wait_for_timeout(800)  # Было 1500
                        
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
                                    await page.wait_for_selector(ac_selector, timeout=1500)  # Уменьшили таймаут
                                    await page.wait_for_timeout(200)  # Было 500
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
                        
                        await page.wait_for_timeout(300)  # Было 1000
                        
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
        """Настройка радиуса поиска через кнопки +/-"""
        try:
            logger.info(f"🎯 Настройка радиуса {location_type}: {radius} миль")
            
            # Определяем селекторы для поиска элементов радиуса
            if location_type.lower() == 'origin':
                # Селекторы для Origin Radius (обычно первый)
                base_selectors = [
                    "[data-testid*='origin-radius']",
                    "[id*='origin'][id*='radius']",
                    "[class*='origin'][class*='radius']",
                    ".radius-control:first-of-type",
                    ".origin-radius",
                    # Общие селекторы по позиции
                    ".radius-control:nth-of-type(1)",
                    "[class*='radius']:nth-of-type(1)"
                ]
            else:  # destination
                # Селекторы для Destination Radius (обычно второй)
                base_selectors = [
                    "[data-testid*='destination-radius']",
                    "[id*='destination'][id*='radius']",
                    "[class*='destination'][class*='radius']",
                    ".radius-control:nth-of-type(2)",
                    ".destination-radius",
                    # Общие селекторы по позиции
                    "[class*='radius']:nth-of-type(2)"
                ]

            # Поиск контейнера с элементами управления радиусом
            radius_container = None
            current_value = 100  # Значение по умолчанию
            
            for base_selector in base_selectors:
                try:
                    container = await page.wait_for_selector(base_selector, timeout=2000)
                    if container:
                        radius_container = container
                        logger.info(f"✅ Найден контейнер радиуса: {base_selector}")
                        break
                except Exception:
                    continue
            
            if not radius_container:
                # Попробуем найти по кнопкам +/-
                try:
                    plus_buttons = await page.query_selector_all("button:has-text('+'), .btn-plus, [class*='plus'], [data-action='increase']")
                    minus_buttons = await page.query_selector_all("button:has-text('-'), .btn-minus, [class*='minus'], [data-action='decrease']")
                    
                    if plus_buttons and minus_buttons:
                        # Определяем какие кнопки относятся к нужному радиусу
                        target_index = 0 if location_type.lower() == 'origin' else 1
                        if target_index < len(plus_buttons) and target_index < len(minus_buttons):
                            plus_btn = plus_buttons[target_index]
                            minus_btn = minus_buttons[target_index]
                            
                            # Пытаемся найти текущее значение рядом с кнопками
                            parent = await plus_btn.query_selector('xpath=..')
                            if parent:
                                value_elements = await parent.query_selector_all("span, input, .value, [class*='value']")
                                for elem in value_elements:
                                    text = await elem.text_content()
                                    if text and text.strip().isdigit():
                                        current_value = int(text.strip())
                                        break
                            
                            # Вычисляем разность и нажимаем кнопки
                            difference = radius - current_value
                            
                            if difference > 0:
                                # Нужно увеличить - нажимаем +
                                for _ in range(abs(difference) // 25):  # Обычно шаг 25
                                    await plus_btn.click()
                                    await page.wait_for_timeout(100)  # Минимальная задержка
                            elif difference < 0:
                                # Нужно уменьшить - нажимаем -
                                for _ in range(abs(difference) // 25):
                                    await minus_btn.click()
                                    await page.wait_for_timeout(100)
                            
                            logger.info(f"✅ Радиус {location_type} установлен через кнопки +/-: {radius}")
                            return
                            
                except Exception as e:
                    logger.debug(f"Не удалось найти кнопки +/-: {e}")
            
            # Если нашли контейнер, ищем в нем элементы управления
            if radius_container:
                # Поиск кнопок + и - внутри контейнера
                try:
                    plus_btn = await radius_container.query_selector("button:has-text('+'), .btn-plus, [class*='plus']")
                    minus_btn = await radius_container.query_selector("button:has-text('-'), .btn-minus, [class*='minus']")
                    
                    if plus_btn and minus_btn:
                        # Ищем текущее значение
                        value_elem = await radius_container.query_selector("span, input, .value, [class*='value']")
                        if value_elem:
                            text = await value_elem.text_content()
                            if text and text.strip().replace('mi', '').strip().isdigit():
                                current_value = int(text.strip().replace('mi', '').strip())
                        
                        # Вычисляем разность
                        difference = radius - current_value
                        
                        if difference > 0:
                            # Увеличиваем
                            clicks_needed = abs(difference) // 25
                            for _ in range(clicks_needed):
                                await plus_btn.click()
                                await page.wait_for_timeout(100)
                        elif difference < 0:
                            # Уменьшаем
                            clicks_needed = abs(difference) // 25
                            for _ in range(clicks_needed):
                                await minus_btn.click()
                                await page.wait_for_timeout(100)
                        
                        logger.info(f"✅ Радиус {location_type} установлен: {radius}")
                        return
                        
                except Exception as e:
                    logger.debug(f"Ошибка работы с кнопками в контейнере: {e}")
            
            # Fallback: попробуем старый метод с селектами (если есть)
            select_selectors = [
                f"select[name*='{location_type}'][name*='radius']",
                f"select[id*='{location_type}'][id*='radius']",
                "select:has(option[value='25']):has(option[value='250'])"
            ]
            
            for selector in select_selectors:
                try:
                    element = await page.wait_for_selector(selector, timeout=1000)
                    if element:
                        await element.select_option(value=str(radius))
                        logger.info(f"✅ Радиус {location_type} установлен через селект: {radius}")
                        return
                except Exception:
                    continue
            
            logger.warning(f"⚠️ Не удалось найти элементы управления радиусом для {location_type}: {radius}")
                    
        except Exception as e:
            logger.error(f"❌ Ошибка настройки радиуса {location_type}: {e}")

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
                    element = await page.wait_for_selector(selector, timeout=1500)  # Уменьшили таймаут
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
                        await page.wait_for_timeout(200)  # Было 500
                        
                        # Вводим дату в зависимости от типа поля
                        if input_type == 'date':
                            # Для полей типа date используем формат YYYY-MM-DD
                            iso_date = self._convert_to_iso_date(date_value)
                            await element.fill(iso_date)
                        else:
                            # Для текстовых полей используем MM/DD/YYYY
                            await element.type(formatted_date)
                        
                        await page.wait_for_timeout(200)  # Было 500
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
                    element = await page.wait_for_selector(selector, timeout=1000)  # Уменьшили таймаут
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
                            await page.wait_for_timeout(800)  # Было 2000 - ждем начала поиска
                            
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
                    await page.wait_for_timeout(800)  # Было 2000
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
            await page.wait_for_selector(".results, .load-results, [data-testid='search-results']", timeout=8000)  # Уменьшили таймаут
            await page.wait_for_timeout(800)  # Было 2000
            
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
            await page.wait_for_timeout(500)  # Было 1000
            
            # Или поиск кнопки обновления
            refresh_selectors = [
                "button:has-text('Refresh')",
                "[data-testid='refresh-button']",
                ".refresh-button"
            ]
            
            for selector in refresh_selectors:
                try:
                    button = await page.wait_for_selector(selector, timeout=1000)  # Уменьшили таймаут
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
