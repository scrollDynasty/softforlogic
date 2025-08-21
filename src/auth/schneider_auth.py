import asyncio
import json
import os
import time
import random
from typing import Optional, Dict, List
from playwright.async_api import Page, Browser, BrowserContext, TimeoutError as PlaywrightTimeoutError
import pickle

from ..utils.logger import logger
from ..utils.performance_monitor import PerformanceMonitor

class SchneiderAuth:
    def __init__(self, config: Dict):
        self.config = config
        self.login_url = config['schneider']['login_url']
        self.email = config['schneider']['email']
        self.password = config['schneider']['password']
        self.user_agents = config['schneider']['user_agents']
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.session_cookies_file = "data/session_cookies.pkl"
        self.is_authenticated = False
        self.last_session_check = 0
        self.session_check_interval = 30 * 60  # 30 минут
        self.performance = PerformanceMonitor()
        
    async def initialize_browser(self) -> bool:
        """Инициализация браузера с оптимизированными настройками и обработкой ошибок"""
        max_attempts = 3
        
        for attempt in range(max_attempts):
            try:
                logger.info(f"🌐 Инициализация браузера (попытка {attempt + 1}/{max_attempts})...")
                
                # Закрытие предыдущего браузера если есть
                await self.close()
                
                from playwright.async_api import async_playwright
                
                self.playwright = await async_playwright().start()
                
                # Создание браузера с оптимизированными настройками
                browser_args = self.config['browser']['extra_args'].copy()
                
                # Дополнительные аргументы для стабильности
                additional_args = [
                    '--disable-blink-features=AutomationControlled',
                    '--disable-web-security',
                    '--disable-features=VizDisplayCompositor',
                    '--disable-ipc-flooding-protection',
                    '--disable-renderer-backgrounding',
                    '--disable-backgrounding-occluded-windows',
                    '--disable-background-timer-throttling',
                    '--force-color-profile=srgb',
                    '--metrics-recording-only',
                    '--disable-background-networking',
                    '--disable-default-apps',
                    '--disable-extensions',
                    '--no-first-run',
                    '--no-default-browser-check',
                    '--disable-logging',
                    '--disable-gpu-logging',
                    '--silent'
                ]
                
                # Добавляем дополнительные аргументы если их нет
                for arg in additional_args:
                    if arg not in browser_args:
                        browser_args.append(arg)
                
                self.browser = await self.playwright.chromium.launch(
                    headless=self.config['browser']['headless'],
                    args=browser_args,
                    slow_mo=100  # Небольшая задержка для стабильности
                )
                
                # Создание контекста с настройками для медленных соединений
                self.context = await self.browser.new_context(
                    viewport={
                        'width': self.config['browser']['viewport_width'],
                        'height': self.config['browser']['viewport_height']
                    },
                    user_agent=self.rotate_user_agent(),
                    ignore_https_errors=True,
                    java_script_enabled=not self.config['browser'].get('disable_javascript', False),
                    accept_downloads=False,
                    bypass_csp=True,
                    locale='en-US',
                    timezone_id='America/New_York',
                    # Настройки для медленных соединений и VPN
                    extra_http_headers={
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                        'Accept-Language': 'en-US,en;q=0.5',
                        'Accept-Encoding': 'gzip, deflate',
                        'Connection': 'keep-alive',
                        'Upgrade-Insecure-Requests': '1',
                    }
                )
                
                # Создание страницы
                self.page = await self.context.new_page()
                
                # Оптимизация настроек страницы
                try:
                    await self.performance.optimize_browser_settings(self.page)
                except Exception as perf_error:
                    logger.warning(f"⚠️ Ошибка оптимизации производительности: {perf_error}")
                
                # Блокировка ненужных ресурсов для ускорения (НЕ блокируем CSS!)
                if self.config['browser'].get('disable_images', True):
                    await self.page.route('**/*.{png,jpg,jpeg,gif,webp,svg,ico}', lambda route: route.abort())
                    # НЕ блокируем CSS файлы - они нужны для правильного отображения полей ввода!
                    # await self.page.route('**/*.{css}', lambda route: route.abort())
                
                # Добавляем дополнительные настройки для медленных соединений
                await self.page.set_extra_http_headers({
                    'Cache-Control': 'no-cache',
                    'Pragma': 'no-cache'
                })
                
                # Увеличиваем таймауты для VPN соединений
                base_timeout = self.config['browser']['timeout_seconds'] * 1000
                page_load_timeout = self.config['browser'].get('page_load_timeout_seconds', 60) * 1000
                element_timeout = self.config['browser'].get('element_wait_timeout_seconds', 30) * 1000
                
                self.page.set_default_timeout(element_timeout)
                self.page.set_default_navigation_timeout(page_load_timeout)
                
                # Логируем настройки для диагностики
                logger.info(f"🔧 Настройки таймаутов: навигация={page_load_timeout}ms, элементы={element_timeout}ms")
                if self.config['browser'].get('vpn_mode'):
                    logger.info("🌐 Режим VPN активирован")
                if self.config['browser'].get('slow_connection_mode'):
                    logger.info("🐌 Режим медленного соединения активирован")
                
                # Проверка работоспособности браузера
                await self.page.goto('data:text/html,<html><body>Test</body></html>')
                
                logger.info("✅ Браузер инициализирован успешно")
                return True
                
            except Exception as e:
                logger.error(f"❌ Ошибка инициализации браузера (попытка {attempt + 1}): {e}")
                
                # Попытка очистки перед повторной попыткой
                try:
                    await self.close()
                except:
                    pass
                
                if attempt < max_attempts - 1:
                    await asyncio.sleep(5 * (attempt + 1))
                    continue
        
        logger.error("❌ Все попытки инициализации браузера исчерпаны")
        return False
    
    def rotate_user_agent(self) -> str:
        """Ротация User-Agent для избежания блокировок"""
        return random.choice(self.user_agents)
    
    async def login(self, max_attempts: int = 3) -> bool:
        """Выполнение входа в систему грузоперевозок с оптимизацией производительности"""
        for attempt in range(max_attempts):
            try:
                start_time = time.time()
                logger.info(f"🔐 Попытка входа в систему {attempt + 1}/{max_attempts}...")
                
                # Пропуск восстановления сессии по запросу пользователя
                if not self.config.get('restore_session', True):
                    logger.info("🔄 Пропускаем восстановление сессии по запросу пользователя")
                else:
                    # Попытка восстановления сессии
                    if await self.restore_session():
                        elapsed = (time.time() - start_time) * 1000
                        logger.info(f"✅ Сессия восстановлена за {elapsed:.0f}мс")
                        return True
                
                # Выполнение полного входа в систему
                logger.info("🔐 Начинаем новый вход в систему...")
                if await self.perform_full_login():
                    elapsed = (time.time() - start_time) * 1000
                    if elapsed > 60000:  # Более 60 секунд
                        logger.warning(f"🐌 Медленный вход в систему: {elapsed:.0f}мс")
                    else:
                        logger.info(f"✅ Успешный вход в систему за {elapsed:.0f}мс")
                    return True
                
            except Exception as e:
                logger.error(f"❌ Ошибка входа в систему (попытка {attempt + 1}): {e}")
                if attempt < max_attempts - 1:
                    wait_time = (attempt + 1) * 5
                    logger.info(f"⏳ Ожидание {wait_time} сек перед следующей попыткой...")
                    await asyncio.sleep(wait_time)
        
        return False

    async def perform_full_login(self) -> bool:
        """Выполнение полного процесса авторизации с оптимизацией"""
        try:
            # Переход на страницу входа
            if not await self.navigate_to_login():
                return False
            
            # Заполнение данных для входа
            if not await self.fill_login_form():
                return False
            
            # Отправка формы
            if not await self.submit_login_form():
                return False
            
            # Обработка двухфакторной аутентификации
            if await self.check_2fa_required():
                logger.info("🔐 Требуется подтверждение входа по SMS")
                if not await self.handle_2fa():
                    return False
            
            # Проверка успешного входа
            return await self.verify_login_success()
            
        except Exception as e:
            logger.error(f"❌ Ошибка процесса входа: {e}")
            return False

    async def safe_query_selector_all(self, selector: str, max_retries: int = None) -> List:
        """Безопасный поиск элементов с обработкой потери контекста"""
        if max_retries is None:
            max_retries = self.config['browser'].get('context_recovery_attempts', 3)
            
        for attempt in range(max_retries):
            try:
                # Проверяем, что страница активна
                await self.page.wait_for_function("document.readyState !== 'uninitialized'", timeout=5000)
                
                elements = await self.page.query_selector_all(selector)
                return elements
                
            except Exception as e:
                if "Execution context was destroyed" in str(e) or "navigation" in str(e).lower():
                    logger.warning(f"⚠️ Контекст потерян при поиске '{selector}' (попытка {attempt + 1}/{max_retries}): {e}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(2)
                        try:
                            # Проверяем, что страница все еще доступна
                            current_url = self.page.url
                            if not current_url or current_url == "about:blank":
                                # Перезагружаем страницу
                                await self.page.goto(self.login_url, wait_until='networkidle', timeout=30000)
                                await self.wait_for_page_ready()
                        except Exception as reload_error:
                            logger.warning(f"⚠️ Ошибка восстановления страницы: {reload_error}")
                        continue
                else:
                    logger.warning(f"⚠️ Ошибка поиска элементов '{selector}': {e}")
                    break
        
        return []

    async def safe_element_interaction(self, element, action: str, *args, **kwargs):
        """Безопасное взаимодействие с элементом"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # Проверяем, что элемент все еще присоединен к DOM (используем правильный метод)
                try:
                    # Попытка получить атрибут для проверки доступности элемента
                    await element.get_attribute("class")
                except Exception:
                    logger.warning(f"⚠️ Элемент недоступен при выполнении {action}")
                    return False
                
                # Выполняем действие
                if action == "type":
                    await element.type(*args, **kwargs)
                elif action == "clear":
                    await element.clear()
                elif action == "click":
                    await element.click(**kwargs)
                elif action == "get_attribute":
                    return await element.get_attribute(*args)
                elif action == "is_visible":
                    return await element.is_visible()
                
                return True
                
            except Exception as e:
                if "Execution context was destroyed" in str(e) or "detached" in str(e).lower():
                    logger.warning(f"⚠️ Элемент недоступен при {action} (попытка {attempt + 1}/{max_retries}): {e}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(1)
                        continue
                else:
                    logger.warning(f"⚠️ Ошибка взаимодействия с элементом ({action}): {e}")
                    break
        
        return False

    async def wait_for_page_ready(self) -> bool:
        """Ожидание полной готовности страницы включая CSS стили"""
        try:
            # Ожидание загрузки DOM
            await self.page.wait_for_function("document.readyState === 'complete'", timeout=15000)
            
            # Ожидание загрузки CSS стилей
            await self.page.wait_for_function(
                """
                () => {
                    // Проверяем, что есть загруженные стили
                    if (document.styleSheets.length === 0) return false;
                    
                    // Проверяем, что все стили загружены
                    for (let i = 0; i < document.styleSheets.length; i++) {
                        try {
                            const sheet = document.styleSheets[i];
                            if (sheet.href && !sheet.cssRules) return false;
                        } catch (e) {
                            // Игнорируем ошибки CORS для внешних стилей
                            continue;
                        }
                    }
                    return true;
                }
                """,
                timeout=20000
            )
            
            # Дополнительное ожидание для стабильности
            await asyncio.sleep(2)
            logger.info("✅ Страница и стили полностью загружены")
            return True
            
        except Exception as e:
            logger.warning(f"⚠️ Ошибка ожидания готовности страницы: {e}")
            return False

    async def navigate_to_login(self) -> bool:
        """Переход на страницу входа в систему с оптимизацией загрузки для VPN соединений"""
        max_attempts = 3
        
        for attempt in range(max_attempts):
            try:
                logger.info(f"🔗 Переход на страницу входа (попытка {attempt + 1}/{max_attempts})")
                
                # Переход на страницу с увеличенными таймаутами для VPN
                await self.page.goto(
                    self.login_url, 
                    wait_until='networkidle',  # Ждем полной загрузки для VPN
                    timeout=60000  # Увеличенный таймаут для медленных соединений
                )
                
                # Ожидание полной загрузки всех ресурсов
                await self.page.wait_for_load_state('networkidle', timeout=30000)
                
                # Дополнительное ожидание для загрузки стилей и скриптов
                await asyncio.sleep(3)
                
                # Проверка успешной загрузки
                if "schneider" in self.page.url.lower():
                    logger.info("✅ Страница входа загружена успешно")
                    
                    # Ожидание полной готовности страницы и стилей
                    if await self.wait_for_page_ready():
                        return True
                    else:
                        logger.warning("⚠️ Страница загружена, но стили могут быть не готовы")
                        return True  # Продолжаем работу даже если стили не полностью загружены
                    
            except Exception as e:
                logger.error(f"❌ Ошибка загрузки страницы входа: {e}")
                if attempt < max_attempts - 1:
                    logger.info(f"🔄 Повторная попытка через 5 секунд...")
                    await asyncio.sleep(5)
        
        return False

    async def fill_login_form(self) -> bool:
        """Заполнение формы входа с улучшенным поиском полей"""
        max_attempts = 3
        
        for attempt in range(max_attempts):
            try:
                logger.info(f"📝 Заполнение формы входа (попытка {attempt + 1}/{max_attempts})")
                
                # Ожидание появления формы входа
                await asyncio.sleep(2)
                
                # Заполнение email с множественными селекторами
                email_filled = False
                email_selectors = [
                    "input[type='email']",
                    "input[name='email']", 
                    "input[name='username']",
                    "input[name='login']",
                    "input[id='email']",
                    "input[id='username']",
                    "input[id*='email']",
                    "input[id*='username']",
                    "input[placeholder*='email' i]",
                    "input[placeholder*='Email' i]",
                    "input[placeholder*='username' i]",
                    "input[placeholder*='Username' i]",
                    "input[class*='email']",
                    "input[class*='username']",
                    "input[class*='login']",
                    "#email",
                    "#username", 
                    "#login",
                    ".email-input",
                    ".username-input",
                    ".login-input",
                    "input[data-testid*='email']",
                    "input[data-testid*='username']"
                ]
                
                # Сначала попробуем найти все возможные поля ввода для диагностики
                # с обработкой ошибки потери контекста при VPN подключении
                input_retry_attempts = 3
                for input_attempt in range(input_retry_attempts):
                    try:
                        # Используем безопасный поиск элементов
                        all_inputs = await self.safe_query_selector_all("input")
                        logger.info(f"🔍 Найдено {len(all_inputs)} полей ввода на странице")
                        
                        for i, input_field in enumerate(all_inputs[:10]):  # Показываем первые 10
                            try:
                                # Прямое получение атрибутов без дополнительных проверок
                                field_type = await input_field.get_attribute("type") or "text"
                                field_name = await input_field.get_attribute("name") or ""
                                field_id = await input_field.get_attribute("id") or ""
                                field_placeholder = await input_field.get_attribute("placeholder") or ""
                                field_class = await input_field.get_attribute("class") or ""
                                
                                logger.debug(f"  Поле {i+1}: type='{field_type}', name='{field_name}', id='{field_id}', placeholder='{field_placeholder}', class='{field_class}'")
                            except Exception as e:
                                logger.debug(f"  Поле {i+1}: ошибка получения атрибутов - {e}")
                        break  # Успешно получили поля
                        
                    except Exception as e:
                        if "Execution context was destroyed" in str(e) or "navigation" in str(e).lower():
                            logger.warning(f"⚠️ Контекст страницы потерян (попытка {input_attempt + 1}/{input_retry_attempts}): {e}")
                            if input_attempt < input_retry_attempts - 1:
                                await asyncio.sleep(2)
                                # Попробуем перезагрузить страницу
                                try:
                                    await self.page.reload(wait_until='networkidle', timeout=30000)
                                    await asyncio.sleep(3)
                                except Exception as reload_error:
                                    logger.warning(f"⚠️ Ошибка перезагрузки страницы: {reload_error}")
                                continue
                        else:
                            logger.warning(f"⚠️ Не удалось получить список полей ввода: {e}")
                            break
                
                for selector in email_selectors:
                    try:
                        logger.debug(f"🔍 Пробуем селектор: {selector}")
                        email_field = await self.page.wait_for_selector(selector, timeout=3000)
                        if email_field and await email_field.is_visible():
                            await email_field.clear()
                            await email_field.type(self.email, delay=50)
                            email_filled = True
                            logger.info(f"✅ Email введен успешно через селектор: {selector}")
                            break
                    except Exception as e:
                        logger.debug(f"❌ Селектор {selector} не сработал: {e}")
                        continue
                
                if not email_filled:
                    # Попробуем универсальный подход - найти любое текстовое поле
                    # с обработкой ошибки потери контекста
                    universal_retry_attempts = 3
                    for universal_attempt in range(universal_retry_attempts):
                        try:
                            logger.info(f"🔍 Пробуем универсальный поиск текстового поля (попытка {universal_attempt + 1}/{universal_retry_attempts})...")
                            
                            # Используем безопасный поиск текстовых полей
                            text_inputs = await self.safe_query_selector_all("input[type='text'], input[type='email'], input:not([type])")
                            for input_field in text_inputs:
                                try:
                                    # Используем безопасные методы взаимодействия
                                    if await self.safe_element_interaction(input_field, "is_visible"):
                                        await self.safe_element_interaction(input_field, "clear")
                                        await self.safe_element_interaction(input_field, "type", self.email, delay=50)
                                        email_filled = True
                                        logger.info("✅ Email введен через универсальный поиск")
                                        break
                                except Exception:
                                    continue
                            
                            if email_filled:
                                break  # Успешно заполнили поле
                                
                        except Exception as e:
                            if "Execution context was destroyed" in str(e) or "navigation" in str(e).lower():
                                logger.warning(f"⚠️ Контекст потерян при универсальном поиске (попытка {universal_attempt + 1}/{universal_retry_attempts}): {e}")
                                if universal_attempt < universal_retry_attempts - 1:
                                    await asyncio.sleep(2)
                                    try:
                                        await self.page.reload(wait_until='networkidle', timeout=30000)
                                        await asyncio.sleep(3)
                                    except Exception as reload_error:
                                        logger.warning(f"⚠️ Ошибка перезагрузки при универсальном поиске: {reload_error}")
                                    continue
                            else:
                                logger.warning(f"⚠️ Ошибка универсального поиска: {e}")
                                break
                    
                    if not email_filled:
                        try:
                            logger.error(f"❌ Универсальный поиск не удался: {e}")
                        except Exception as e:
                            logger.error(f"❌ Универсальный поиск не удался: {e}")
                
                if not email_filled:
                    logger.error("❌ Не удалось найти поле для ввода email")
                    # Сохраним скриншот для диагностики
                    try:
                        screenshot_path = f"screenshots/email_field_not_found_{int(time.time())}.png"
                        await self.page.screenshot(path=screenshot_path)
                        logger.info(f"📸 Скриншот сохранен: {screenshot_path}")
                    except Exception as e:
                        logger.warning(f"⚠️ Не удалось сохранить скриншот: {e}")
                    continue
                
                await asyncio.sleep(1)
                
                # Заполнение пароля
                password_filled = False
                password_selectors = [
                    "input[type='password']",
                    "input[name='password']",
                    "input[id='password']",
                    "input[placeholder*='password' i]",
                    "input[placeholder*='Password' i]"
                ]
                
                for selector in password_selectors:
                    try:
                        password_field = await self.page.wait_for_selector(selector, timeout=5000)
                        if password_field:
                            await password_field.clear()
                            await password_field.type(self.password, delay=50)
                            password_filled = True
                            logger.info("✅ Пароль введен успешно")
                            break
                    except Exception:
                        continue
                
                if not password_filled:
                    logger.error("❌ Не удалось найти поле для ввода пароля")
                    continue
                
                return True
                
            except Exception as e:
                logger.error(f"❌ Ошибка заполнения формы: {e}")
                if attempt < max_attempts - 1:
                    await asyncio.sleep(2)
        
        return False

    async def handle_2fa(self) -> bool:
        """Обработка двухфакторной аутентификации с улучшенным UX"""
        try:
            logger.info("🔐 Начинаем процесс подтверждения входа...")
            
            # Этап 1: Отправка SMS-кода
            logger.info("📱 Шаг 1: Отправка кода подтверждения на телефон")
            if not await self.send_2fa_code():
                return False
            
            # Этап 2: Ввод кода
            logger.info("📱 Шаг 2: Ввод кода подтверждения")
            
            max_attempts = 3
            for attempt in range(max_attempts):
                try:
                    # Запрос кода у пользователя
                    phone_hint = self.get_phone_hint()
                    print(f"\n🔐 Подтверждение входа (Попытка {attempt + 1}/{max_attempts})")
                    print(f"📱 SMS-код отправлен на ваш телефон ({phone_hint})")
                    print(f"📱 Введите полученный 6-значный код:")
                    
                    code = input("Код подтверждения: ").strip()
                    
                    if len(code) != 6 or not code.isdigit():
                        print("❌ Код должен состоять из 6 цифр")
                        continue
                    
                    # Ввод кода в форму
                    if await self.submit_2fa_code(code):
                        logger.info("✅ Подтверждение входа успешно!")
                        return True
                    else:
                        print("❌ Неверный код. Попробуйте еще раз.")
                        
                except KeyboardInterrupt:
                    logger.info("🛑 Операция прервана пользователем")
                    return False
                except Exception as e:
                    logger.error(f"❌ Ошибка ввода кода: {e}")
            
            logger.error("❌ Превышено количество попыток ввода кода")
            return False
            
        except Exception as e:
            logger.error(f"❌ Ошибка двухфакторной аутентификации: {e}")
            return False
    
    async def _navigate_to_login_with_retry(self) -> bool:
        """Переход на страницу входа с повторными попытками"""
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                logger.info(f"🔗 Переход на страницу входа (попытка {attempt + 1}/{max_attempts})")
                await self.page.goto(self.login_url, wait_until='networkidle', timeout=30000)
                
                # Проверяем, что страница загружена
                await self.page.wait_for_load_state('domcontentloaded')
                
                # Дополнительное ожидание для полной загрузки
                await asyncio.sleep(2)
                
                logger.info("✅ Страница входа загружена")
                return True
                
            except Exception as e:
                logger.warning(f"⚠️ Ошибка загрузки страницы (попытка {attempt + 1}): {e}")
                if attempt < max_attempts - 1:
                    await asyncio.sleep(5)
                    continue
        
        return False

    async def _fill_login_fields_with_retry(self) -> bool:
        """Заполнение полей входа с повторными попытками"""
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                logger.info(f"📝 Заполнение полей входа (попытка {attempt + 1}/{max_attempts})")
                
                # Ожидание появления полей формы
                await self.page.wait_for_load_state('domcontentloaded')
                await asyncio.sleep(2)
                
                # Поиск поля email с расширенным списком селекторов
                email_selectors = [
                    'input[type="email"]',
                    'input[name="email"]',
                    'input[name="username"]',
                    'input[name="login"]',
                    'input[id*="email"]',
                    'input[id*="username"]',
                    'input[placeholder*="email" i]',
                    'input[placeholder*="Email" i]',
                    'input[placeholder*="username" i]',
                    '#email',
                    '#username',
                    '.email-input',
                    '.username-input'
                ]
                
                email_field = None
                for selector in email_selectors:
                    try:
                        email_field = await self.page.wait_for_selector(selector, timeout=3000)
                        if email_field and await email_field.is_visible():
                            logger.debug(f"📧 Найдено поле email: {selector}")
                            break
                    except:
                        continue
                
                if email_field:
                    await email_field.fill('')  # Clear field
                    await email_field.fill(self.email)
                    logger.info("✅ Email заполнен")
                else:
                    logger.warning("⚠️ Поле email не найдено")
                    if attempt < max_attempts - 1:
                        continue
                    return False
                
                # Поиск поля password с расширенным списком селекторов
                password_selectors = [
                    'input[type="password"]',
                    'input[name="password"]',
                    'input[name="passwd"]',
                    'input[id*="password"]',
                    'input[id*="passwd"]',
                    'input[placeholder*="password" i]',
                    'input[placeholder*="Password" i]',
                    '#password',
                    '#passwd',
                    '.password-input'
                ]
                
                password_field = None
                for selector in password_selectors:
                    try:
                        password_field = await self.page.wait_for_selector(selector, timeout=3000)
                        if password_field and await password_field.is_visible():
                            logger.debug(f"🔑 Найдено поле пароля: {selector}")
                            break
                    except:
                        continue
                
                if password_field:
                    await password_field.fill('')  # Clear field
                    await password_field.fill(self.password)
                    logger.info("✅ Пароль заполнен")
                    return True
                else:
                    logger.warning("⚠️ Поле пароля не найдено")
                    if attempt < max_attempts - 1:
                        continue
                    return False
                    
            except Exception as e:
                logger.error(f"❌ Ошибка заполнения полей (попытка {attempt + 1}): {e}")
                if attempt < max_attempts - 1:
                    await asyncio.sleep(3)
                    continue
        
        return False

    async def _fill_login_fields(self) -> None:
        """Заполнение полей входа (legacy метод для совместимости)"""
        await self._fill_login_fields_with_retry()
    
    async def submit_login_form(self) -> bool:
        """Отправка формы входа с улучшенным поиском кнопки"""
        try:
            logger.info("🚀 Отправка формы входа")
            
            # Селекторы для кнопки входа
            submit_selectors = [
                "button[type='submit']",
                "input[type='submit']",
                "button[name='submit']",
                "button:has-text('Sign In')",
                "button:has-text('Log In')",
                "button:has-text('Login')",
                "[data-testid='login-button']",
                ".login-button"
            ]
            
            for selector in submit_selectors:
                try:
                    submit_button = await self.page.wait_for_selector(selector, timeout=5000)
                    if submit_button and await submit_button.is_visible():
                        await submit_button.click()
                        logger.info("✅ Форма входа отправлена")
                        await asyncio.sleep(3)  # Ожидание обработки
                        return True
                except Exception:
                    continue
            
            # Попытка отправки через Enter
            try:
                await self.page.keyboard.press('Enter')
                logger.info("✅ Форма отправлена через Enter")
                await asyncio.sleep(3)
                return True
            except Exception:
                pass
            
            logger.error("❌ Не удалось найти кнопку отправки формы")
            return False
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки формы входа: {e}")
            return False

    async def check_2fa_required(self) -> bool:
        """Проверка необходимости двухфакторной аутентификации"""
        try:
            # Ожидание возможных элементов 2FA
            await asyncio.sleep(2)
            
            # Получаем текст страницы для поиска характерных фраз
            page_content = await self.page.content()
            page_text = await self.page.text_content('body') if await self.page.query_selector('body') else ""
            
            # Ключевые фразы, указывающие на страницу 2FA
            twofa_text_indicators = [
                "Welcome Carriers!",
                "Send Code",
                "Call Me", 
                "verification code",
                "Enter your verification code",
                "Number on File"
            ]
            
            # Проверяем наличие характерного текста
            for indicator in twofa_text_indicators:
                if indicator.lower() in page_text.lower():
                    logger.info(f"🔐 Обнаружен индикатор 2FA: '{indicator}'")
                    return True
            
            # Селекторы элементов 2FA
            twofa_selectors = [
                'button:has-text("Send Code")',
                'button:has-text("Call Me")',
                'input[placeholder*="code" i]',
                'input[placeholder*="verification" i]',
                '[data-testid="2fa"]',
                '.two-factor',
                '.verification',
                '#verification-code',
                'input[name*="code"]',
                'input[id*="code"]'
            ]
            
            for selector in twofa_selectors:
                try:
                    element = await self.page.wait_for_selector(selector, timeout=1000)
                    if element and await element.is_visible():
                        logger.info(f"🔐 Обнаружен элемент 2FA: {selector}")
                        return True
                except Exception:
                    continue
            
            # Проверяем URL на наличие признаков 2FA
            current_url = self.page.url.lower()
            if any(keyword in current_url for keyword in ['2fa', 'verification', 'verify', 'code']):
                logger.info(f"🔐 Обнаружен 2FA по URL: {current_url}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"❌ Ошибка проверки 2FA: {e}")
            return False

    def get_phone_hint(self) -> str:
        """Получение подсказки номера телефона"""
        return "XXX-XXX-5898"  # Placeholder

    async def send_2fa_code(self) -> bool:
        """Отправка SMS-кода для двухфакторной аутентификации"""
        try:
            logger.info("📱 Поиск кнопки отправки кода...")
            
            # Селекторы для кнопки отправки кода
            send_code_selectors = [
                'button:has-text("Send Code")',
                'button:has-text("Send SMS")',
                'button:has-text("Send")',
                'input[value*="Send Code"]',
                'input[type="submit"][value*="Send"]',
                '.send-code-button',
                '[data-testid="send-code"]'
            ]
            
            for selector in send_code_selectors:
                try:
                    send_button = await self.page.wait_for_selector(selector, timeout=3000)
                    if send_button and await send_button.is_visible():
                        logger.info(f"✅ Найдена кнопка отправки кода: {selector}")
                        await send_button.click()
                        logger.info("📱 Кнопка 'Send Code' нажата")
                        
                        # Ожидание отправки кода
                        await asyncio.sleep(3)
                        
                        # Проверяем, появилось ли поле для ввода кода
                        code_field_selectors = [
                            'input[placeholder*="code" i]',
                            'input[placeholder*="verification" i]',
                            'input[name*="code"]'
                        ]
                        
                        for code_selector in code_field_selectors:
                            try:
                                code_field = await self.page.wait_for_selector(code_selector, timeout=5000)
                                if code_field and await code_field.is_visible():
                                    logger.info("✅ Поле для ввода кода появилось, SMS отправлен")
                                    return True
                            except:
                                continue
                        
                        # Если поле не появилось, но кнопка была нажата, считаем успешным
                        logger.info("✅ Кнопка отправки кода была нажата")
                        return True
                        
                except Exception:
                    continue
            
            # Попытка найти кнопку "Call Me" как альтернативу
            call_me_selectors = [
                'button:has-text("Call Me")',
                'button:has-text("Call")',
                'input[value*="Call Me"]'
            ]
            
            for selector in call_me_selectors:
                try:
                    call_button = await self.page.wait_for_selector(selector, timeout=2000)
                    if call_button and await call_button.is_visible():
                        logger.info(f"✅ Найдена кнопка вызова: {selector}")
                        await call_button.click()
                        logger.info("📞 Кнопка 'Call Me' нажата")
                        await asyncio.sleep(3)
                        return True
                except Exception:
                    continue
            
            logger.error("❌ Не удалось найти кнопку отправки кода")
            
            # Создаем скриншот для отладки
            try:
                screenshot_path = f"screenshots/send_code_not_found_{int(time.time())}.png"
                await self.page.screenshot(path=screenshot_path)
                logger.info(f"📸 Скриншот сохранен: {screenshot_path}")
            except Exception:
                pass
            
            return False
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки SMS-кода: {e}")
            return False

    async def submit_2fa_code(self, code: str) -> bool:
        """Отправка 2FA кода"""
        try:
            # Поиск поля для ввода кода
            code_selectors = [
                'input[placeholder*="code" i]',
                'input[placeholder*="verification" i]',
                'input[name*="code"]',
                'input[id*="code"]',
                'input[type="text"]',
                'input[type="number"]',
                '[data-testid="2fa-input"]'
            ]
            
            code_field = None
            for selector in code_selectors:
                try:
                    code_field = await self.page.wait_for_selector(selector, timeout=5000)
                    if code_field and await code_field.is_visible():
                        logger.info(f"✅ Найдено поле для ввода кода: {selector}")
                        break
                except:
                    continue
            
            if code_field:
                await code_field.fill(code)
                logger.info(f"✅ Код введен: {code}")
                
                # Поиск кнопки подтверждения
                verify_selectors = [
                    'button:has-text("Verify")',
                    'button:has-text("Verify Code")',
                    'button:has-text("Submit")',
                    'button[type="submit"]',
                    '[data-testid="verify-button"]'
                ]
                
                for selector in verify_selectors:
                    try:
                        verify_button = await self.page.wait_for_selector(selector, timeout=5000)
                        if verify_button and await verify_button.is_visible():
                            await verify_button.click()
                            logger.info("✅ Код отправлен на проверку")
                            
                            # Ожидание результата
                            await asyncio.sleep(5)
                            return await self.verify_login_success()
                    except Exception:
                        continue
                
                # Попытка отправки через Enter
                try:
                    await code_field.press('Enter')
                    await asyncio.sleep(5)
                    return await self.verify_login_success()
                except Exception:
                    pass
            
            return False
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки 2FA кода: {e}")
            return False

    async def restore_session(self) -> bool:
        """Восстановление сохраненной сессии"""
        try:
            if not os.path.exists(self.session_cookies_file):
                return False
                
            with open(self.session_cookies_file, 'rb') as f:
                cookies = pickle.load(f)
                
            if cookies:
                await self.context.add_cookies(cookies)
                
                # Проверка действительности сессии
                await self.page.goto(self.config['schneider']['dashboard_url'], timeout=15000)
                await asyncio.sleep(3)
                
                current_url = self.page.url.lower()
                
                # Проверяем, попали ли мы на дашборд (успешная сессия)
                if "dashboard" in current_url or "home" in current_url or "loads" in current_url:
                    self.is_authenticated = True
                    logger.info("✅ Сессия восстановлена успешно")
                    return True
                
                # Проверяем, попали ли мы на страницу 2FA (частично действительная сессия)
                if await self.check_2fa_required():
                    logger.info("🔐 Сессия частично восстановлена, требуется 2FA")
                    # Обрабатываем 2FA
                    if await self.handle_2fa():
                        self.is_authenticated = True
                        logger.info("✅ Сессия восстановлена после 2FA")
                        return True
                    else:
                        logger.error("❌ Не удалось пройти 2FA при восстановлении сессии")
                        return False
                
                # Проверяем, остались ли мы на странице входа (недействительная сессия)
                if "login" in current_url:
                    logger.info("⚠️ Сессия недействительна, требуется новый вход")
                    # Очищаем недействительную сессию
                    await self.clear_invalid_session()
                    return False
                
                # Если попали на неизвестную страницу, логируем это
                logger.warning(f"⚠️ Неожиданная страница при восстановлении сессии: {current_url}")
                    
        except Exception as e:
            logger.error(f"❌ Ошибка восстановления сессии: {e}")
            # При ошибке восстановления сессии очищаем её
            try:
                await self.clear_invalid_session()
            except Exception as cleanup_error:
                logger.error(f"❌ Ошибка очистки сессии: {cleanup_error}")
            
        return False
    
    async def handle_cloudflare_challenge(self) -> bool:
        """Обход Cloudflare challenge"""
        try:
            # Проверка наличия Cloudflare
            cloudflare_selectors = [
                '#challenge-form',
                '.cf-browser-verification',
                '#cf-please-wait',
                'iframe[src*="cloudflare"]'
            ]
            
            for selector in cloudflare_selectors:
                try:
                    element = await self.page.wait_for_selector(selector, timeout=5000)
                    if element:
                        logger.info("🛡️ Cloudflare challenge detected, waiting...")
                        
                        # Ожидание прохождения challenge
                        await asyncio.sleep(5)
                        
                        # Дополнительное ожидание если нужно
                        try:
                            await self.page.wait_for_selector('body:not(.cf-browser-verification)', timeout=30000)
                        except:
                            pass
                        
                        return True
                except:
                    continue
            
            return False
            
        except Exception as e:
            logger.error(f"❌ Ошибка обработки Cloudflare: {e}")
            return False
    
    async def verify_login_success(self) -> bool:
        """Проверка успешности входа с улучшенной логикой"""
        try:
            # Ожидание перенаправления после входа
            await asyncio.sleep(3)
            
            # Проверка на ошибки входа
            error_selectors = [
                '.error-message',
                '.alert-error',
                '.login-error',
                '[data-testid="error"]',
                '.invalid-credentials',
                'div:has-text("Invalid")',
                'div:has-text("Error")',
                'div:has-text("incorrect")',
                'div:has-text("failed")'
            ]
            
            for selector in error_selectors:
                try:
                    error_element = await self.page.wait_for_selector(selector, timeout=2000)
                    if error_element and await error_element.is_visible():
                        error_text = await error_element.text_content()
                        logger.error(f"❌ Обнаружена ошибка входа: {error_text}")
                        return False
                except:
                    continue
            
            # Проверка URL на успешный вход
            current_url = self.page.url
            success_url_patterns = [
                'dashboard',
                'home',
                'main',
                'loads',
                'freight',
                'freightpower.schneider.com/loads',
                'freightpower.schneider.com/dashboard',
                '/app/',
                '/portal/'
            ]
            
            for pattern in success_url_patterns:
                if pattern in current_url.lower():
                    logger.info(f"✅ Успешный вход обнаружен по URL: {current_url}")
                    return True
            
            # Селекторы успешного входа (расширенный список)
            success_selectors = [
                '[data-testid="dashboard"]',
                '[data-testid="user-menu"]',
                '.dashboard',
                '.main-content',
                '.user-menu',
                '.logout-button',
                '.user-profile',
                '.navigation',
                '.nav-menu',
                'a[href*="logout"]',
                'a[href*="signout"]',
                'button:has-text("Logout")',
                'button:has-text("Sign Out")',
                'button:has-text("Выйти")',
                '.header-user',
                '.user-dropdown',
                '#user-menu',
                '#logout'
            ]
            
            # Проверка элементов успешного входа
            for selector in success_selectors:
                try:
                    element = await self.page.wait_for_selector(selector, timeout=3000)
                    if element and await element.is_visible():
                        logger.info(f"✅ Элемент успешного входа найден: {selector}")
                        return True
                except:
                    continue
            
            # Проверка отсутствия полей входа (значит мы уже вошли)
            login_selectors = [
                'input[type="password"]',
                'input[name="password"]',
                'button:has-text("Sign In")',
                'button:has-text("Login")'
            ]
            
            login_elements_found = False
            for selector in login_selectors:
                try:
                    element = await self.page.wait_for_selector(selector, timeout=2000)
                    if element and await element.is_visible():
                        login_elements_found = True
                        break
                except:
                    continue
            
            if not login_elements_found:
                logger.info("✅ Поля входа не найдены - вероятно успешный вход")
                return True
            
            # Проверка заголовка страницы
            title = await self.page.title()
            if title and 'login' not in title.lower() and 'sign in' not in title.lower():
                logger.info(f"✅ Заголовок страницы указывает на успешный вход: {title}")
                return True
            
            logger.warning("⚠️ Не удалось определить успешность входа")
            return False
            
        except Exception as e:
            logger.error(f"❌ Ошибка проверки успешности входа: {e}")
            return False
    
    async def check_session(self) -> bool:
        """Проверка активности сессии с улучшенной валидацией"""
        try:
            current_time = time.time()
            
            # Проверяем не слишком ли часто
            if current_time - self.last_session_check < 60:  # Минимум 1 минута между проверками
                return self.is_authenticated
            
            self.last_session_check = current_time
            
            logger.info("🔍 Проверка валидности сессии...")
            
            # Попытка перехода на защищенную страницу с грузами
            try:
                await self.page.goto("https://freightpower.schneider.com/loads", 
                                   wait_until='networkidle', timeout=15000)
                
                # Проверяем, не перенаправило ли нас на страницу входа
                current_url = self.page.url
                if "login" in current_url.lower() or "signin" in current_url.lower():
                    logger.warning("⚠️ Сессия недействительна - перенаправление на страницу входа")
                    self.is_authenticated = False
                    return False
                
                # Проверяем наличие элементов, характерных для авторизованного пользователя
                try:
                    # Ждем появления элементов страницы с грузами
                    await self.page.wait_for_selector('[data-testid="load-card"], .load-item, .freight-item', 
                                                    timeout=10000)
                    logger.info("✅ Сессия валидна - доступ к странице с грузами подтвержден")
                    self.is_authenticated = True
                    return True
                    
                except Exception:
                    # Если элементы не найдены, проверяем другие признаки авторизации
                    try:
                        # Проверяем наличие навигационного меню или профиля пользователя
                        await self.page.wait_for_selector('.nav-menu, .user-profile, [data-testid="user-menu"]', 
                                                        timeout=5000)
                        logger.info("✅ Сессия валидна - навигационные элементы найдены")
                        self.is_authenticated = True
                        return True
                    except Exception:
                        logger.warning("⚠️ Сессия недействительна - отсутствуют элементы авторизованного пользователя")
                        self.is_authenticated = False
                        return False
                        
            except Exception as e:
                logger.error(f"❌ Ошибка при проверке страницы с грузами: {e}")
                # Fallback - проверяем основную страницу
                try:
                    await self.page.goto(self.login_url, wait_until='networkidle', timeout=10000)
                    if await self.verify_login_success():
                        self.is_authenticated = True
                        return True
                    else:
                        self.is_authenticated = False
                        return False
                except Exception as fallback_error:
                    logger.error(f"❌ Ошибка fallback проверки: {fallback_error}")
                    self.is_authenticated = False
                    return False
                
        except Exception as e:
            logger.error(f"❌ Критическая ошибка проверки сессии: {e}")
            self.is_authenticated = False
            return False
    
    async def refresh_session(self) -> bool:
        """Переавторизация при необходимости"""
        try:
            logger.info("🔄 Обновление сессии...")
            self.is_authenticated = False
            
            # Очистка cookies
            await self.context.clear_cookies()
            
            # Повторная авторизация
            return await self.login()
            
        except Exception as e:
            logger.error(f"❌ Ошибка обновления сессии: {e}")
            return False
    
    async def save_session_cookies(self) -> bool:
        """Сохранение сессии"""
        try:
            os.makedirs(os.path.dirname(self.session_cookies_file), exist_ok=True)
            
            cookies = await self.context.cookies()
            
            with open(self.session_cookies_file, 'wb') as f:
                pickle.dump(cookies, f)
            
            logger.debug("✅ Сессия сохранена")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения сессии: {e}")
            return False
    
    async def load_session_cookies(self) -> bool:
        """Загрузка сохраненной сессии"""
        try:
            if not os.path.exists(self.session_cookies_file):
                return False
            
            with open(self.session_cookies_file, 'rb') as f:
                cookies = pickle.load(f)
            
            await self.context.add_cookies(cookies)
            
            logger.debug("✅ Сессия загружена")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки сессии: {e}")
            return False
    
    async def get_page(self) -> Optional[Page]:
        """Получение активной страницы"""
        return self.page
    
    async def close(self) -> None:
        """Закрытие браузера и Playwright"""
        try:
            if self.page:
                await self.page.close()
                self.page = None
            
            if self.context:
                await self.context.close()
                self.context = None
                
            if self.browser:
                await self.browser.close()
                self.browser = None
                
            if hasattr(self, 'playwright') and self.playwright:
                await self.playwright.stop()
                self.playwright = None
                
            logger.info("✅ Браузер и Playwright закрыты")
        except Exception as e:
            logger.error(f"❌ Ошибка закрытия браузера: {e}")
    
    async def is_authenticated_check(self) -> bool:
        """Проверка статуса авторизации"""
        if not self.is_authenticated:
            return False
        
        # Проверяем сессию периодически
        current_time = time.time()
        if current_time - self.last_session_check > self.session_check_interval:
            return await self.check_session()
        
        return self.is_authenticated

    async def clear_invalid_session(self) -> None:
        """Принудительная очистка недействительной сессии"""
        try:
            logger.info("🧹 Очистка недействительной сессии...")
            
            # Сброс флага авторизации
            self.is_authenticated = False
            
            # Очистка cookies в браузере
            if self.context:
                await self.context.clear_cookies()
                logger.info("✅ Cookies очищены из браузера")
            
            # Удаление файла сессии
            if os.path.exists(self.session_cookies_file):
                try:
                    os.remove(self.session_cookies_file)
                    logger.info("✅ Файл сессии удален")
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось удалить файл сессии: {e}")
            
            # Также удаляем старый файл, если он существует
            old_session_file = "session_cookies.json"
            if os.path.exists(old_session_file):
                try:
                    os.remove(old_session_file)
                    logger.info("✅ Старый файл сессии удален")
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось удалить старый файл сессии: {e}")
            
            # Сброс времени последней проверки
            self.last_session_check = 0
            
            logger.info("✅ Недействительная сессия очищена")
            
        except Exception as e:
            logger.error(f"❌ Ошибка очистки недействительной сессии: {e}")
