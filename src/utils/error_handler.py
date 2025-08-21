import asyncio
import traceback
import time
from typing import Dict, Optional
from collections import defaultdict
from datetime import datetime

from .logger import logger

class ErrorHandler:
    def __init__(self, telegram_notifier, db_manager):
        self.telegram = telegram_notifier
        self.db = db_manager
        self.error_counts = defaultdict(int)
        self.last_error_time = defaultdict(float)
        self.recovery_attempts = 0
        self.max_recovery_attempts = 3
        
    async def handle_auth_error(self, error: Exception) -> bool:
        """Обработка ошибок авторизации"""
        error_msg = str(error)
        logger.error(f"🔐 Ошибка авторизации: {error_msg}")
        
        # Логирование ошибки
        await self.db.log_error(
            error_type="AuthenticationError",
            error_message=error_msg,
            stack_trace=traceback.format_exc(),
            context="authentication"
        )
        
        if "2FA" in error_msg:
            print("🔐 2FA код требуется. Проверьте консоль...")
            return await self.request_2fa_input()
        elif "blocked" in error_msg.lower():
            await self.telegram.send_error_alert("🚫 IP заблокирован! Проверьте VPN соединение")
            return False
        elif "credentials" in error_msg.lower():
            await self.telegram.send_error_alert("❌ Неверные учетные данные")
            return False
        elif "cloudflare" in error_msg.lower():
            await self.telegram.send_error_alert("🛡️ Cloudflare блокировка! Попробуйте позже")
            return False
            
        return True
    
    async def handle_parsing_error(self, error: Exception, page_url: str) -> bool:
        """Обработка ошибок парсинга"""
        error_type = type(error).__name__
        self.error_counts[error_type] += 1
        
        # Логирование ошибки
        await self.db.log_error(
            error_type=error_type,
            error_message=str(error),
            stack_trace=traceback.format_exc(),
            context="parsing"
        )
        
        # Критическое количество ошибок
        if self.error_counts[error_type] > 10:
            screenshot_path = await self.take_debug_screenshot(page_url)
            await self.telegram.send_error_alert(
                f"🔥 Критическая ошибка парсинга: {error_type}\n"
                f"Количество: {self.error_counts[error_type]}\n"
                f"URL: {page_url}",
                screenshot_path
            )
            
        # Автоматическое восстановление
        if self.error_counts[error_type] > 5:
            logger.warning(f"🔄 Попытка автоматического восстановления после {error_type}")
            await asyncio.sleep(30)  # Пауза перед повторной попыткой
            
        return True
    
    async def handle_network_error(self, error: Exception) -> bool:
        """Обработка сетевых ошибок"""
        error_msg = str(error)
        logger.error(f"🌐 Сетевая ошибка: {error_msg}")
        
        # Логирование ошибки
        await self.db.log_error(
            error_type="NetworkError",
            error_message=error_msg,
            stack_trace=traceback.format_exc(),
            context="network"
        )
        
        if "timeout" in error_msg.lower():
            logger.warning("⏰ Таймаут сети - повторная попытка с увеличенным таймаутом")
            await asyncio.sleep(10)
            return True
        elif "connection" in error_msg.lower():
            logger.warning("🔌 Ошибка соединения - проверка интернет-соединения")
            return await self.check_connectivity()
        elif "rate limit" in error_msg.lower():
            logger.warning("🚫 Превышен лимит запросов - ожидание")
            await asyncio.sleep(60)  # Ждем минуту
            return True
        elif "ssl" in error_msg.lower():
            logger.warning("🔒 SSL ошибка - попытка обхода")
            return True
            
        return False
    
    async def handle_browser_error(self, error: Exception) -> bool:
        """Обработка ошибок браузера"""
        error_msg = str(error)
        logger.error(f"🌐 Ошибка браузера: {error_msg}")
        
        # Логирование ошибки
        await self.db.log_error(
            error_type="BrowserError",
            error_message=error_msg,
            stack_trace=traceback.format_exc(),
            context="browser"
        )
        
        if "crashed" in error_msg.lower():
            logger.warning("💥 Браузер упал - перезапуск")
            return True
        elif "context" in error_msg.lower():
            logger.warning("🔄 Ошибка контекста браузера - пересоздание")
            return True
        elif "page" in error_msg.lower():
            logger.warning("📄 Ошибка страницы - перезагрузка")
            return True
            
        return False
    
    async def handle_database_error(self, error: Exception) -> bool:
        """Обработка ошибок базы данных"""
        error_msg = str(error)
        logger.error(f"💾 Ошибка БД: {error_msg}")
        
        # Логирование ошибки
        await self.db.log_error(
            error_type="DatabaseError",
            error_message=error_msg,
            stack_trace=traceback.format_exc(),
            context="database"
        )
        
        if "locked" in error_msg.lower():
            logger.warning("🔒 БД заблокирована - ожидание")
            await asyncio.sleep(5)
            return True
        elif "corrupt" in error_msg.lower():
            logger.error("💥 БД повреждена - требуется восстановление")
            await self.telegram.send_error_alert("💥 База данных повреждена!")
            return False
        elif "full" in error_msg.lower():
            logger.warning("💾 БД заполнена - очистка старых записей")
            await self.db.cleanup_old_records()
            return True
            
        return False
    
    async def handle_telegram_error(self, error: Exception) -> bool:
        """Обработка ошибок Telegram"""
        error_msg = str(error)
        logger.error(f"📱 Ошибка Telegram: {error_msg}")
        
        # Логирование ошибки
        await self.db.log_error(
            error_type="TelegramError",
            error_message=error_msg,
            stack_trace=traceback.format_exc(),
            context="telegram"
        )
        
        if "bot token" in error_msg.lower():
            logger.error("🔑 Неверный токен бота")
            return False
        elif "chat" in error_msg.lower():
            logger.error("💬 Ошибка чата")
            return False
        elif "rate limit" in error_msg.lower():
            logger.warning("🚫 Превышен лимит Telegram - ожидание")
            await asyncio.sleep(60)
            return True
            
        return False
    
    async def request_2fa_input(self) -> bool:
        """Запрос ввода 2FA кода"""
        try:
            print("\n🔐 2FA Authentication Required")
            print("📱 Please check your authenticator app and enter the 6-digit code:")
            
            # Ожидание ввода с timeout
            code = await asyncio.wait_for(
                asyncio.to_thread(input, "2FA Code: "),
                timeout=120  # 2 минуты на ввод
            )
            
            if len(code) == 6 and code.isdigit():
                logger.info("✅ 2FA код получен")
                return True
            else:
                logger.error("❌ Неверный формат 2FA кода")
                return False
                
        except asyncio.TimeoutError:
            logger.error("⏰ Таймаут ввода 2FA кода")
            return False
        except Exception as e:
            logger.error(f"❌ Ошибка ввода 2FA: {e}")
            return False
    
    async def check_connectivity(self) -> bool:
        """Проверка интернет-соединения"""
        try:
            import aiohttp
            
            async with aiohttp.ClientSession() as session:
                async with session.get('https://www.google.com', timeout=10) as response:
                    if response.status == 200:
                        logger.info("✅ Интернет-соединение работает")
                        return True
                    else:
                        logger.error("❌ Проблемы с интернет-соединением")
                        return False
                        
        except Exception as e:
            logger.error(f"❌ Ошибка проверки соединения: {e}")
            return False
    
    async def take_debug_screenshot(self, page_url: str) -> Optional[str]:
        """Создание скриншота для отладки"""
        try:
            from playwright.async_api import async_playwright
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot_path = f"screenshots/debug_{timestamp}.png"
            
            # Создание директории
            import os
            os.makedirs("screenshots", exist_ok=True)
            
            # Создание скриншота через отдельный браузер
            playwright = await async_playwright().start()
            browser = await playwright.chromium.launch(headless=True)
            page = await browser.new_page()
            
            await page.goto(page_url, timeout=30000)
            await page.screenshot(path=screenshot_path, full_page=True)
            
            await browser.close()
            await playwright.stop()
            
            logger.info(f"📸 Debug скриншот сохранен: {screenshot_path}")
            return screenshot_path
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания debug скриншота: {e}")
            return None
    
    async def full_recovery_sequence(self, parser_instance) -> bool:
        """Полная процедура восстановления"""
        try:
            logger.info("🔄 Начинаем процедуру восстановления...")
            
            # Увеличение счетчика попыток
            self.recovery_attempts += 1
            
            if self.recovery_attempts > self.max_recovery_attempts:
                await self.telegram.send_error_alert(
                    "🆘 КРИТИЧЕСКАЯ ОШИБКА: Система не может восстановиться!\n"
                    "Требуется ручное вмешательство."
                )
                return False
            
            # 1. Остановка всех активных процессов
            await self.stop_all_processes(parser_instance)
            
            # 2. Очистка кеша и временных файлов
            await self.cleanup_temp_files()
            
            # 3. Переинициализация браузера
            await self.reinitialize_browser(parser_instance)
            
            # 4. Повторная авторизация
            if not await parser_instance.auth.login():
                raise Exception("Failed to re-authenticate during recovery")
            
            # 5. Проверка работоспособности
            test_result = await self.run_system_test(parser_instance)
            if not test_result:
                raise Exception("System test failed after recovery")
            
            logger.info("✅ Восстановление завершено успешно")
            await self.telegram.send_status_update("🟢 Система восстановлена и работает")
            
            # Сброс счетчика попыток
            self.recovery_attempts = 0
            return True
            
        except Exception as e:
            logger.error(f"❌ Попытка восстановления {self.recovery_attempts} не удалась: {e}")
            
            # Увеличиваем задержку с каждой попыткой
            delay = 30 * (2 ** self.recovery_attempts)
            await asyncio.sleep(delay)
            
            # Рекурсивная попытка восстановления
            return await self.full_recovery_sequence(parser_instance)
    
    async def stop_all_processes(self, parser_instance) -> None:
        """Остановка всех активных процессов"""
        try:
            logger.info("🛑 Остановка всех процессов...")
            
            # Остановка мониторинга
            if hasattr(parser_instance, 'monitor'):
                await parser_instance.monitor.stop_monitoring()
            
            # Закрытие браузера
            if hasattr(parser_instance, 'auth'):
                await parser_instance.auth.close()
            
            logger.info("✅ Все процессы остановлены")
            
        except Exception as e:
            logger.error(f"❌ Ошибка остановки процессов: {e}")
    
    async def cleanup_temp_files(self) -> None:
        """Очистка временных файлов"""
        try:
            import os
            import glob
            
            # Очистка временных файлов браузера
            temp_dirs = [
                "/tmp/.com.google.Chrome*",
                "/tmp/.org.chromium.Chromium*",
                "~/.cache/chromium",
                "~/.cache/google-chrome"
            ]
            
            for pattern in temp_dirs:
                try:
                    for path in glob.glob(os.path.expanduser(pattern)):
                        if os.path.isdir(path):
                            import shutil
                            shutil.rmtree(path, ignore_errors=True)
                except Exception:
                    pass
            
            logger.info("🧹 Временные файлы очищены")
            
        except Exception as e:
            logger.error(f"❌ Ошибка очистки временных файлов: {e}")
    
    async def reinitialize_browser(self, parser_instance) -> None:
        """Переинициализация браузера"""
        try:
            logger.info("🔄 Переинициализация браузера...")
            
            # Создание нового экземпляра браузера
            await parser_instance.auth.initialize_browser()
            
            logger.info("✅ Браузер переинициализирован")
            
        except Exception as e:
            logger.error(f"❌ Ошибка переинициализации браузера: {e}")
            raise
    
    async def run_system_test(self, parser_instance) -> bool:
        """Запуск системного теста"""
        try:
            logger.info("🧪 Запуск системного теста...")
            
            # Тест авторизации
            if not await parser_instance.auth.is_authenticated_check():
                logger.error("❌ Тест авторизации не пройден")
                return False
            
            # Тест доступа к странице
            page = await parser_instance.auth.get_page()
            if not page:
                logger.error("❌ Тест доступа к странице не пройден")
                return False
            
            # Тест парсинга (базовый)
            try:
                await page.goto("https://freightpower.schneider.com/loads", timeout=10000)
                logger.info("✅ Системный тест пройден")
                return True
            except Exception as e:
                logger.error(f"❌ Тест парсинга не пройден: {e}")
                return False
            
        except Exception as e:
            logger.error(f"❌ Ошибка системного теста: {e}")
            return False
    
    async def handle_critical_error(self, error: Exception, parser_instance) -> None:
        """Обработка критических ошибок"""
        error_msg = str(error)
        logger.critical(f"💥 КРИТИЧЕСКАЯ ОШИБКА: {error_msg}")
        
        # Логирование критической ошибки
        await self.db.log_error(
            error_type="CriticalError",
            error_message=error_msg,
            stack_trace=traceback.format_exc(),
            context="critical"
        )
        
        # Отправка уведомления
        await self.telegram.send_error_alert(
            f"💥 КРИТИЧЕСКАЯ ОШИБКА СИСТЕМЫ!\n\n"
            f"Ошибка: {error_msg}\n"
            f"Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"Система пытается восстановиться автоматически..."
        )
        
        # Попытка автоматического восстановления
        try:
            await self.full_recovery_sequence(parser_instance)
        except Exception as recovery_error:
            logger.critical(f"💥 Восстановление не удалось: {recovery_error}")
            await self.telegram.send_error_alert(
                "🆘 АВТОМАТИЧЕСКОЕ ВОССТАНОВЛЕНИЕ НЕ УДАЛОСЬ!\n"
                "Требуется ручное вмешательство."
            )
    
    def get_error_statistics(self) -> Dict:
        """Получение статистики ошибок"""
        return {
            'total_errors': sum(self.error_counts.values()),
            'error_types': dict(self.error_counts),
            'recovery_attempts': self.recovery_attempts,
            'last_errors': dict(self.last_error_time)
        }
