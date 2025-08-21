import asyncio
import json
import os
import time
import random
from typing import Optional, Dict, List
from playwright.async_api import Page, Browser, BrowserContext
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
        """Инициализация браузера с оптимизированными настройками"""
        try:
            from playwright.async_api import async_playwright
            
            self.playwright = await async_playwright().start()
            
            # Создание браузера с оптимизированными настройками
            self.browser = await self.playwright.chromium.launch(
                headless=self.config['browser']['headless'],
                args=self.config['browser']['extra_args']
            )
            
            # Создание контекста с настройками
            self.context = await self.browser.new_context(
                viewport={
                    'width': self.config['browser']['viewport_width'],
                    'height': self.config['browser']['viewport_height']
                },
                user_agent=self.rotate_user_agent(),
                ignore_https_errors=True
            )
            
            # Создание страницы
            self.page = await self.context.new_page()
            
            # Оптимизация настроек страницы
            await self.performance.optimize_browser_settings(self.page)
            
            # Установка таймаутов
            self.page.set_default_timeout(self.config['browser']['timeout_seconds'] * 1000)
            
            logger.info("✅ Браузер инициализирован успешно")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации браузера: {e}")
            return False
    
    def rotate_user_agent(self) -> str:
        """Ротация User-Agent для избежания блокировок"""
        return random.choice(self.user_agents)
    
    async def login(self) -> bool:
        """Авторизация на сайте Schneider"""
        try:
            start_time = time.time()
            
            # Попытка загрузки сохраненной сессии
            if await self.load_session_cookies():
                logger.info("🔄 Попытка восстановления сессии...")
                if await self.check_session():
                    logger.info("✅ Сессия восстановлена успешно")
                    await self.performance.log_performance_metrics(
                        "session_restore", (time.time() - start_time) * 1000, True
                    )
                    return True
            
            # Полная авторизация
            logger.info("🔐 Начинаем полную авторизацию...")
            
            # Переход на страницу входа
            await self.page.goto(self.login_url, wait_until='networkidle')
            
            # Обработка Cloudflare если есть
            if await self.handle_cloudflare_challenge():
                logger.info("✅ Cloudflare challenge пройден")
            
            # Поиск и заполнение полей входа
            await self._fill_login_fields()
            
            # Нажатие кнопки входа
            await self._submit_login()
            
            # Обработка 2FA если требуется
            if await self._check_2fa_required():
                if not await self.handle_2fa():
                    logger.error("❌ 2FA авторизация не удалась")
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
                logger.error("❌ Авторизация не удалась")
                return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка авторизации: {e}")
            await self.performance.log_performance_metrics("login", 0, False, str(e))
            return False
    
    async def _fill_login_fields(self) -> None:
        """Заполнение полей входа"""
        try:
            # Поиск поля email
            email_selectors = [
                'input[type="email"]',
                'input[name="email"]',
                'input[id*="email"]',
                'input[placeholder*="email" i]',
                'input[placeholder*="Email" i]'
            ]
            
            email_field = None
            for selector in email_selectors:
                try:
                    email_field = await self.page.wait_for_selector(selector, timeout=5000)
                    if email_field:
                        break
                except:
                    continue
            
            if email_field:
                await email_field.fill(self.email)
                logger.debug("✅ Email заполнен")
            else:
                logger.warning("⚠️ Поле email не найдено")
            
            # Поиск поля password
            password_selectors = [
                'input[type="password"]',
                'input[name="password"]',
                'input[id*="password"]',
                'input[placeholder*="password" i]',
                'input[placeholder*="Password" i]'
            ]
            
            password_field = None
            for selector in password_selectors:
                try:
                    password_field = await self.page.wait_for_selector(selector, timeout=5000)
                    if password_field:
                        break
                except:
                    continue
            
            if password_field:
                await password_field.fill(self.password)
                logger.debug("✅ Пароль заполнен")
            else:
                logger.warning("⚠️ Поле пароля не найдено")
                
        except Exception as e:
            logger.error(f"❌ Ошибка заполнения полей входа: {e}")
    
    async def _submit_login(self) -> None:
        """Отправка формы входа"""
        try:
            # Поиск кнопки входа
            submit_selectors = [
                'button[type="submit"]',
                'input[type="submit"]',
                'button:has-text("Sign In")',
                'button:has-text("Login")',
                'button:has-text("Войти")',
                '[data-testid="login-button"]',
                '.login-button',
                '#login-button'
            ]
            
            submit_button = None
            for selector in submit_selectors:
                try:
                    submit_button = await self.page.wait_for_selector(selector, timeout=5000)
                    if submit_button:
                        break
                except:
                    continue
            
            if submit_button:
                await submit_button.click()
                logger.debug("✅ Форма входа отправлена")
            else:
                # Попытка отправки через Enter
                await self.page.keyboard.press('Enter')
                logger.debug("✅ Форма отправлена через Enter")
                
        except Exception as e:
            logger.error(f"❌ Ошибка отправки формы входа: {e}")
    
    async def _check_2fa_required(self) -> bool:
        """Проверка необходимости 2FA"""
        try:
            # Селекторы для 2FA
            twofa_selectors = [
                'input[placeholder*="code" i]',
                'input[placeholder*="Code" i]',
                'input[name*="code"]',
                'input[id*="code"]',
                '[data-testid="2fa-input"]',
                '.two-factor-input'
            ]
            
            for selector in twofa_selectors:
                try:
                    element = await self.page.wait_for_selector(selector, timeout=3000)
                    if element:
                        logger.info("🔐 2FA требуется")
                        return True
                except:
                    continue
            
            return False
            
        except Exception as e:
            logger.error(f"❌ Ошибка проверки 2FA: {e}")
            return False
    
    async def handle_2fa(self) -> bool:
        """Обработка 2FA с интеллектуальным ожиданием"""
        max_attempts = 3
        
        for attempt in range(max_attempts):
            try:
                print(f"\n🔐 2FA Authentication Required (Attempt {attempt + 1}/{max_attempts})")
                print("📱 Please check your authenticator app and enter the 6-digit code:")
                
                # Ожидание ввода с timeout
                code = await asyncio.wait_for(
                    asyncio.to_thread(input, "2FA Code: "),
                    timeout=120  # 2 минуты на ввод
                )
                
                if len(code) == 6 and code.isdigit():
                    # Поиск поля для ввода кода
                    code_selectors = [
                        'input[placeholder*="code" i]',
                        'input[placeholder*="Code" i]',
                        'input[name*="code"]',
                        'input[id*="code"]',
                        '[data-testid="2fa-input"]'
                    ]
                    
                    code_field = None
                    for selector in code_selectors:
                        try:
                            code_field = await self.page.wait_for_selector(selector, timeout=5000)
                            if code_field:
                                break
                        except:
                            continue
                    
                    if code_field:
                        await code_field.fill(code)
                        
                        # Поиск кнопки подтверждения
                        verify_selectors = [
                            'button:has-text("Verify")',
                            'button:has-text("Submit")',
                            'button[type="submit"]',
                            '[data-testid="verify-button"]'
                        ]
                        
                        verify_button = None
                        for selector in verify_selectors:
                            try:
                                verify_button = await self.page.wait_for_selector(selector, timeout=5000)
                                if verify_button:
                                    break
                            except:
                                continue
                        
                        if verify_button:
                            await verify_button.click()
                        else:
                            await self.page.keyboard.press('Enter')
                        
                        # Проверка успешности
                        await asyncio.sleep(3)
                        
                        if await self._verify_login_success():
                            print("✅ 2FA verification successful!")
                            return True
                        else:
                            print("❌ Invalid 2FA code, please try again")
                    else:
                        print("❌ 2FA input field not found")
                else:
                    print("❌ Invalid format. Please enter exactly 6 digits")
                    
            except asyncio.TimeoutError:
                print("⏰ 2FA input timeout")
                
        print("🚫 2FA authentication failed after maximum attempts")
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
        """Проверка успешности входа"""
        try:
            # Селекторы успешного входа
            success_selectors = [
                '[data-testid="dashboard"]',
                '.dashboard',
                '.user-menu',
                '.logout-button',
                'a[href*="logout"]',
                'button:has-text("Logout")',
                'button:has-text("Выйти")'
            ]
            
            for selector in success_selectors:
                try:
                    element = await self.page.wait_for_selector(selector, timeout=5000)
                    if element:
                        return True
                except:
                    continue
            
            # Проверка URL
            current_url = self.page.url
            if 'dashboard' in current_url or 'home' in current_url:
                return True
            
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
