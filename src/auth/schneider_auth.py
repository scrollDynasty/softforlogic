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
                
                # Создание контекста с настройками
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
                    timezone_id='America/New_York'
                )
                
                # Создание страницы
                self.page = await self.context.new_page()
                
                # Оптимизация настроек страницы
                try:
                    await self.performance.optimize_browser_settings(self.page)
                except Exception as perf_error:
                    logger.warning(f"⚠️ Ошибка оптимизации производительности: {perf_error}")
                
                # Установка таймаутов
                timeout_ms = self.config['browser']['timeout_seconds'] * 1000
                self.page.set_default_timeout(timeout_ms)
                self.page.set_default_navigation_timeout(timeout_ms)
                
                # Блокировка ненужных ресурсов для ускорения
                if self.config['browser'].get('disable_images', True):
                    await self.page.route('**/*.{png,jpg,jpeg,gif,webp,svg,ico}', lambda route: route.abort())
                    await self.page.route('**/*.{css}', lambda route: route.abort())
                
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
    
    async def login(self) -> bool:
        """Авторизация на сайте Schneider с улучшенной обработкой ошибок"""
        max_attempts = 3
        
        for attempt in range(max_attempts):
            try:
                start_time = time.time()
                logger.info(f"🔐 Попытка авторизации {attempt + 1}/{max_attempts}...")
                
                # Проверка браузера
                if not self.page or not self.browser:
                    logger.warning("⚠️ Браузер не инициализирован, переинициализация...")
                    if not await self.initialize_browser():
                        raise Exception("Failed to initialize browser")
                
                # Попытка загрузки сохраненной сессии только при первой попытке
                if attempt == 0 and await self.load_session_cookies():
                    logger.info("🔄 Попытка восстановления сессии...")
                    if await self.check_session():
                        logger.info("✅ Сессия восстановлена успешно")
                        await self.performance.log_performance_metrics(
                            "session_restore", (time.time() - start_time) * 1000, True
                        )
                        return True
                    else:
                        logger.info("⚠️ Сессия недействительна, выполняем полную авторизацию")
                        await self.context.clear_cookies()  # Очищаем недействительные cookies
                
                # Полная авторизация
                logger.info("🔐 Начинаем полную авторизацию...")
                
                # Переход на страницу входа с повторными попытками
                if not await self._navigate_to_login_with_retry():
                    raise Exception("Failed to navigate to login page")
                
                # Обработка Cloudflare если есть
                if await self.handle_cloudflare_challenge():
                    logger.info("✅ Cloudflare challenge пройден")
                
                # Поиск и заполнение полей входа
                if not await self._fill_login_fields_with_retry():
                    raise Exception("Failed to fill login fields")
                
                # Нажатие кнопки входа
                if not await self._submit_login_with_retry():
                    raise Exception("Failed to submit login form")
                
                # Ожидание результата авторизации
                await asyncio.sleep(3)
                
                # Обработка 2FA если требуется
                if await self._check_2fa_required():
                    logger.info("🔐 Требуется 2FA авторизация")
                    if not await self.handle_2fa():
                        logger.error("❌ 2FA авторизация не удалась")
                        if attempt < max_attempts - 1:
                            continue
                        return False
                
                # Проверка успешности входа
                if await self._verify_login_success():
                    self.is_authenticated = True
                    await self.save_session_cookies()
                    
                    duration = (time.time() - start_time) * 1000
                    await self.performance.log_performance_metrics("login", duration, True)
                    
                    logger.info(f"✅ Авторизация успешна за {duration:.0f}ms")
                    return True
                else:
                    logger.warning(f"⚠️ Попытка {attempt + 1} не удалась - проверка не пройдена")
                    if attempt < max_attempts - 1:
                        await asyncio.sleep(5 * (attempt + 1))  # Увеличивающаяся задержка
                        continue
                    
            except PlaywrightTimeoutError as e:
                logger.error(f"⏰ Таймаут при авторизации (попытка {attempt + 1}): {e}")
                if attempt < max_attempts - 1:
                    await asyncio.sleep(10 * (attempt + 1))
                    continue
                    
            except Exception as e:
                logger.error(f"❌ Ошибка авторизации (попытка {attempt + 1}): {e}")
                await self.performance.log_performance_metrics("login", 0, False, str(e))
                if attempt < max_attempts - 1:
                    await asyncio.sleep(5 * (attempt + 1))
                    continue
        
        logger.error("❌ Все попытки авторизации исчерпаны")
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
    
    async def _submit_login_with_retry(self) -> bool:
        """Отправка формы входа с повторными попытками"""
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                logger.info(f"🚀 Отправка формы входа (попытка {attempt + 1}/{max_attempts})")
                
                # Расширенный список селекторов кнопок
                submit_selectors = [
                    'button[type="submit"]',
                    'input[type="submit"]',
                    'button:has-text("Sign In")',
                    'button:has-text("Login")',
                    'button:has-text("Log In")',
                    'button:has-text("Войти")',
                    'button:has-text("Submit")',
                    '[data-testid="login-button"]',
                    '[data-testid="submit-button"]',
                    '.login-button',
                    '.submit-button',
                    '#login-button',
                    '#submit-button',
                    'form button',
                    'form input[type="submit"]'
                ]
                
                submit_button = None
                for selector in submit_selectors:
                    try:
                        submit_button = await self.page.wait_for_selector(selector, timeout=3000)
                        if submit_button and await submit_button.is_visible() and await submit_button.is_enabled():
                            logger.debug(f"🔘 Найдена кнопка входа: {selector}")
                            break
                    except:
                        continue
                
                if submit_button:
                    # Скролл к кнопке если нужно
                    await submit_button.scroll_into_view_if_needed()
                    await asyncio.sleep(1)
                    
                    # Клик по кнопке
                    await submit_button.click()
                    logger.info("✅ Форма входа отправлена через кнопку")
                    return True
                else:
                    # Попытка отправки через Enter в поле пароля
                    password_field = await self.page.query_selector('input[type="password"]')
                    if password_field:
                        await password_field.focus()
                        await self.page.keyboard.press('Enter')
                        logger.info("✅ Форма отправлена через Enter")
                        return True
                    else:
                        logger.warning("⚠️ Кнопка входа и поле пароля не найдены")
                        if attempt < max_attempts - 1:
                            await asyncio.sleep(2)
                            continue
                        return False
                    
            except Exception as e:
                logger.error(f"❌ Ошибка отправки формы (попытка {attempt + 1}): {e}")
                if attempt < max_attempts - 1:
                    await asyncio.sleep(3)
                    continue
        
        return False

    async def _submit_login(self) -> None:
        """Отправка формы входа (legacy метод для совместимости)"""
        await self._submit_login_with_retry()
    
    async def _check_2fa_required(self) -> bool:
        """Проверка необходимости 2FA"""
        try:
            # Селекторы для страницы 2FA (Send Code кнопка или поле для кода)
            twofa_selectors = [
                # Кнопки отправки кода
                'button:has-text("Send Code")',
                'button:has-text("Call Me")',
                # Поля для ввода кода
                'input[placeholder*="code" i]',
                'input[placeholder*="Code" i]',
                'input[name*="code"]',
                'input[id*="code"]',
                '[data-testid="2fa-input"]',
                '.two-factor-input',
                # Текст, указывающий на 2FA
                'text="Welcome Carriers!"',
                'text="Click Send Code or Call Me"'
            ]
            
            for selector in twofa_selectors:
                try:
                    element = await self.page.wait_for_selector(selector, timeout=3000)
                    if element:
                        logger.info("🔐 2FA требуется")
                        return True
                except:
                    continue
            
            # Дополнительная проверка по тексту на странице
            try:
                page_content = await self.page.content()
                if ("Welcome Carriers!" in page_content and 
                    "Send Code" in page_content and 
                    "Number on File" in page_content):
                    logger.info("🔐 2FA страница обнаружена по содержимому")
                    return True
            except:
                pass
            
            return False
            
        except Exception as e:
            logger.error(f"❌ Ошибка проверки 2FA: {e}")
            return False
    
    async def handle_2fa(self) -> bool:
        """Обработка полного процесса 2FA: Send Code -> Enter Code -> Verify"""
        max_attempts = 3
        
        try:
            logger.info("🔐 Начинаем обработку 2FA...")
            
            # Этап 1: Нажатие кнопки "Send Code"
            logger.info("📱 Этап 1: Отправка кода на телефон")
            if not await self._send_2fa_code():
                logger.error("❌ Не удалось отправить код 2FA")
                return False
            
            # Этап 2: Ожидание и ввод кода
            logger.info("📱 Этап 2: Ввод кода верификации")
            
            for attempt in range(max_attempts):
                try:
                    print(f"\n🔐 2FA Code Required (Attempt {attempt + 1}/{max_attempts})")
                    print("📱 SMS код должен прийти на ваш телефон (XXX-XXX-5898)")
                    print("📱 Введите полученный код:")
                    
                    # Ожидание ввода с timeout
                    code = await asyncio.wait_for(
                        asyncio.to_thread(input, "2FA Code: "),
                        timeout=180  # 3 минуты на ввод (учитывая доставку SMS)
                    )
                    
                    if len(code) >= 4 and code.isdigit():  # SMS коды могут быть 4-8 цифр
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
                            # Очистка поля и ввод кода
                            await code_field.clear()
                            await code_field.fill(code)
                            logger.info(f"✅ Код введен: {code}")
                            
                            # Этап 3: Нажатие кнопки "Verify Code"
                            logger.info("📱 Этап 3: Подтверждение кода")
                            if await self._verify_2fa_code():
                                # Проверка успешности
                                await asyncio.sleep(5)  # Дополнительное ожидание
                                
                                if await self._verify_login_success():
                                    logger.info("✅ 2FA авторизация успешна!")
                                    return True
                                else:
                                    logger.warning("⚠️ 2FA код принят, но вход не подтвержден")
                                    # Продолжаем попытки
                            else:
                                logger.error("❌ Не удалось нажать кнопку Verify Code")
                        else:
                            logger.error("❌ Поле для ввода 2FA кода не найдено")
                            # Делаем скриншот для отладки
                            await self.page.screenshot(path="screenshots/2fa_error.png")
                    else:
                        print("❌ Неверный формат. Введите код из цифр (4-8 символов)")
                        
                except asyncio.TimeoutError:
                    logger.error("⏰ Таймаут ожидания ввода 2FA кода")
                    return False
                except Exception as e:
                    logger.error(f"❌ Ошибка при обработке 2FA (попытка {attempt + 1}): {e}")
                    if attempt < max_attempts - 1:
                        await asyncio.sleep(3)
                        continue
            
            logger.error("❌ Все попытки ввода 2FA кода исчерпаны")
            return False
            
        except Exception as e:
            logger.error(f"❌ Критическая ошибка 2FA: {e}")
            return False
    
    async def _send_2fa_code(self) -> bool:
        """Отправка 2FA кода на телефон"""
        try:
            # Селекторы для кнопки "Send Code"
            send_code_selectors = [
                'button:has-text("Send Code")',
                'input[value="Send Code"]',
                'button[type="submit"]:has-text("Send")',
                'a:has-text("Send Code")'
            ]
            
            send_button = None
            for selector in send_code_selectors:
                try:
                    send_button = await self.page.wait_for_selector(selector, timeout=5000)
                    if send_button and await send_button.is_visible():
                        logger.info(f"✅ Найдена кнопка Send Code: {selector}")
                        break
                except:
                    continue
            
            if send_button:
                logger.info("📱 Нажимаем кнопку Send Code...")
                await send_button.click()
                
                # Ожидание изменения страницы
                await asyncio.sleep(3)
                
                # Проверяем, что появилось поле для ввода кода
                await asyncio.sleep(2)
                page_content = await self.page.content()
                
                if "Enter your verification code" in page_content or "Verify Code" in page_content:
                    logger.info("✅ Код отправлен, появилось поле для ввода")
                    return True
                else:
                    logger.warning("⚠️ Кнопка нажата, но поле для ввода не появилось")
                    # Делаем скриншот для отладки
                    await self.page.screenshot(path="screenshots/after_send_code.png")
                    return True  # Продолжаем попытку
            else:
                logger.error("❌ Кнопка Send Code не найдена")
                # Делаем скриншот для отладки
                await self.page.screenshot(path="screenshots/send_code_not_found.png")
                return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка отправки 2FA кода: {e}")
            return False
    
    async def _verify_2fa_code(self) -> bool:
        """Подтверждение 2FA кода"""
        try:
            # Селекторы для кнопки "Verify Code"
            verify_selectors = [
                'button:has-text("Verify Code")',
                'input[value="Verify Code"]',
                'button:has-text("Verify")',
                'button:has-text("Submit")',
                'button[type="submit"]'
            ]
            
            verify_button = None
            for selector in verify_selectors:
                try:
                    verify_button = await self.page.wait_for_selector(selector, timeout=5000)
                    if verify_button and await verify_button.is_visible():
                        logger.info(f"✅ Найдена кнопка Verify Code: {selector}")
                        break
                except:
                    continue
            
            if verify_button:
                logger.info("✅ Нажимаем кнопку Verify Code...")
                await verify_button.click()
                
                # Ожидание обработки
                await asyncio.sleep(3)
                return True
            else:
                logger.warning("⚠️ Кнопка Verify Code не найдена, пробуем Enter")
                await self.page.keyboard.press('Enter')
                await asyncio.sleep(3)
                return True
                
        except Exception as e:
            logger.error(f"❌ Ошибка подтверждения 2FA кода: {e}")
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
    
    async def _verify_login_success(self) -> bool:
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
        """Проверка активности сессии"""
        try:
            current_time = time.time()
            
            # Проверяем не слишком ли часто
            if current_time - self.last_session_check < 60:  # Минимум 1 минута между проверками
                return self.is_authenticated
            
            self.last_session_check = current_time
            
            # Переход на главную страницу
            await self.page.goto(self.login_url, wait_until='networkidle')
            
            # Проверка авторизации
            if await self._verify_login_success():
                self.is_authenticated = True
                return True
            else:
                self.is_authenticated = False
                return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка проверки сессии: {e}")
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
