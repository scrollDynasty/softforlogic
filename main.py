#!/usr/bin/env python3
"""
🚛 Система Мониторинга Грузоперевозок Schneider
Автоматический поиск и отслеживание доступных грузов для логистических компаний
"""

import asyncio
import json
import os
import sys
import time
import signal
from datetime import datetime
from typing import Dict, Optional
import argparse

# Глобальная переменная для корректного завершения
schneider_parser_instance = None

def setup_encoding():
    """Настройка кодировки для корректной работы с Unicode на Windows"""
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    if sys.platform.startswith('win'):
        os.system('chcp 65001 > nul')
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

def ask_user_session_restore():
    """Спрашивает пользователя о восстановлении сессии"""
    try:
        print("\n" + "="*60)
        print("🔐 НАСТРОЙКА СЕССИИ АВТОРИЗАЦИИ")
        print("="*60)
        print("Обнаружена сохраненная сессия входа в систему.")
        print("Выберите действие:")
        print("  1️⃣  Использовать сохраненную сессию (быстрый запуск)")
        print("  2️⃣  Выполнить новый вход в систему (более надежно)")
        print("="*60)
        
        while True:
            choice = input("Ваш выбор (1/2): ").strip()
            if choice == "1":
                print("✅ Будет использована сохраненная сессия")
                return True
            elif choice == "2":
                print("✅ Будет выполнен новый вход в систему")
                return False
            else:
                print("❌ Неверный выбор. Введите 1 или 2")
    except KeyboardInterrupt:
        print("\n🛑 Операция прервана пользователем")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Ошибка ввода: {e}")
        print("⚠️ Будет выполнен новый вход в систему")
        return False

# Добавление пути к модулям
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.utils.logger import logger
from src.utils.performance_monitor import PerformanceMonitor
from src.utils.error_handler import ErrorHandler
from src.utils.recovery_system import RecoverySystem, AdaptiveMonitoring, BackupManager
from src.auth.schneider_auth import SchneiderAuth
from src.parser.load_parser import LoadParser
from src.parser.load_monitor import LoadMonitor
from src.telegram.telegram_bot import TelegramNotifier
from src.database.db_manager import DatabaseManager
from src.tests.test_integration import IntegrationTests

class SchneiderParser:
    def __init__(self, config_path: str = "config/config.json", restore_session: bool = True):
        self.config_path = config_path
        self.config = self.load_config()
        self.is_running = False
        self.restore_session = restore_session
        self.shutdown_event = asyncio.Event()  # Добавляем событие для корректного завершения
        self.running_tasks = set()  # Отслеживание активных задач
        
        # Инициализация компонентов
        self.auth = None
        self.parser = None
        self.monitor = None
        self.telegram = None
        self.db = None
        self.performance = None
        self.error_handler = None
        self.recovery_system = None
        self.adaptive_monitoring = None
        self.backup_manager = None
        self.integration_tests = None
        
    def load_config(self) -> Dict:
        """Загрузка конфигурации"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # Загрузка переменных окружения
            self.load_environment_variables(config)
            
            logger.info("✅ Конфигурация загружена успешно")
            return config
            
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки конфигурации: {e}")
            sys.exit(1)
    
    def load_environment_variables(self, config: Dict) -> None:
        """Загрузка переменных окружения с валидацией"""
        try:
            from dotenv import load_dotenv
            load_dotenv("config/.env")
            
            # Telegram
            telegram_token = os.getenv('TELEGRAM_BOT_TOKEN')
            telegram_chat = os.getenv('TELEGRAM_CHAT_ID')
            
            if telegram_token and telegram_token != "your_bot_token_here":
                config['telegram']['bot_token'] = telegram_token
            if telegram_chat and telegram_chat != "your_chat_id_here":
                config['telegram']['chat_id'] = telegram_chat
            
            # Schneider - критически важные переменные
            schneider_email = os.getenv('SCHNEIDER_EMAIL')
            schneider_password = os.getenv('SCHNEIDER_PASSWORD')
            
            if schneider_email:
                config['schneider']['email'] = schneider_email
            if schneider_password:
                config['schneider']['password'] = schneider_password
            
            # Валидация критических учетных данных
            self.validate_credentials(config)
            
            logger.info("✅ Переменные окружения загружены")
            
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки переменных окружения: {e}")
            raise
    
    def validate_credentials(self, config: Dict) -> None:
        """Валидация учетных данных"""
        errors = []
        
        # Проверка Schneider credentials
        if not config.get('schneider', {}).get('email'):
            errors.append("Schneider email не настроен")
        elif config['schneider']['email'] == "primecargoload@gmail.com":
            logger.warning("⚠️ Используются стандартные учетные данные Schneider")
        
        if not config.get('schneider', {}).get('password'):
            errors.append("Schneider password не настроен")
        elif config['schneider']['password'] == "Primecargo2024$":
            logger.warning("⚠️ Используется стандартный пароль Schneider")
        
        # Проверка Telegram credentials
        if not config.get('telegram', {}).get('bot_token'):
            errors.append("Telegram bot token не настроен")
        elif config['telegram']['bot_token'] == "your_bot_token_here":
            errors.append("Telegram bot token не изменен с шаблона")
            
        if not config.get('telegram', {}).get('chat_id'):
            errors.append("Telegram chat ID не настроен")
        elif config['telegram']['chat_id'] == "your_chat_id_here":
            errors.append("Telegram chat ID не изменен с шаблона")
        
        if errors:
            error_msg = "Критические ошибки конфигурации:\n" + "\n".join(f"- {error}" for error in errors)
            logger.error(f"❌ {error_msg}")
            raise Exception(f"Configuration validation failed: {'; '.join(errors)}")
        
        logger.info("✅ Валидация учетных данных пройдена")
    
    async def initialize_components(self) -> bool:
        """Инициализация всех компонентов системы"""
        try:
            logger.info("🔧 Инициализация компонентов системы...")
            
            # 1. Инициализация базы данных
            self.db = DatabaseManager(self.config['database']['path'])
            if not await self.db.init_database():
                raise Exception("Failed to initialize database")
            
            # 2. Инициализация Telegram
            self.telegram = TelegramNotifier(
                self.config['telegram']['bot_token'],
                self.config['telegram']['chat_id']
            )
            
            # Тест соединения с Telegram
            if not await self.telegram.test_connection():
                logger.warning("⚠️ Telegram соединение не установлено")
            
            # 3. Инициализация мониторинга производительности
            self.performance = PerformanceMonitor()
            
            # 4. Инициализация обработчика ошибок
            self.error_handler = ErrorHandler(self.telegram, self.db)
            
            # 5. Инициализация системы восстановления и адаптивного мониторинга
            self.recovery_system = RecoverySystem(self)
            self.adaptive_monitoring = AdaptiveMonitoring()
            self.backup_manager = BackupManager(self.config['database']['path'])
            
            # 6. Инициализация авторизации
            self.auth = SchneiderAuth(self.config)
            if not await self.auth.initialize_browser():
                raise Exception("Failed to initialize browser")
            
            # 7. Инициализация парсера
            self.parser = LoadParser(self.config)
            
            # 8. Инициализация мониторинга
            self.monitor = LoadMonitor(self.config, self.parser, self.telegram, self.db)
            
            # 9. Инициализация интеграционных тестов
            self.integration_tests = IntegrationTests(self.config)
            
            logger.info("✅ Все компоненты инициализированы успешно")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации компонентов: {e}")
            await self.error_handler.handle_critical_error(e, self)
            return False
    
    async def authenticate(self) -> bool:
        """Авторизация с обработкой ошибок и мониторингом производительности"""
        try:
            logger.info("🔐 Начинаем авторизацию (попытка 1/3)...")
            
            # Передаем параметр restore_session в метод login
            success = await self.auth.login()
            
            if success:
                logger.info("✅ Авторизация успешна")
                return True
            else:
                logger.error("❌ Авторизация не удалась")
                return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка авторизации: {e}")
            return False
    
    async def setup_search_filters(self) -> bool:
        """Настройка фильтров поиска (устарело - теперь используются пользовательские фильтры)"""
        try:
            logger.info("⚙️ Пропуск настройки стандартных фильтров - используются пользовательские")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка настройки фильтров: {e}")
            return False
    
    async def start_monitoring(self) -> None:
        """Запуск расширенного мониторинга с адаптивностью и восстановлением"""
        try:
            logger.info("🚀 Запуск расширенного мониторинга грузов...")
            
            # Получение страницы
            page = await self.auth.get_page()
            if not page:
                raise Exception("No active page available")
            
            # Запуск мониторинга с системой восстановления
            while self.is_running:
                try:
                    # Проверка необходимости восстановления
                    if await self.adaptive_monitoring.should_trigger_recovery():
                        logger.warning("🚨 Запуск процедуры восстановления...")
                        recovery_success = await self.recovery_system.full_recovery_sequence()
                        
                        if not recovery_success:
                            logger.error("💥 Восстановление не удалось, остановка системы")
                            break
                            
                        # Получение новой страницы после восстановления
                        page = await self.auth.get_page()
                        if not page:
                            raise Exception("No page available after recovery")
                    
                    # Получение адаптивных настроек
                    strategy = await self.adaptive_monitoring.adjust_scanning_strategy()
                    logger.info(f"🎯 Адаптивные настройки: интервал={strategy['interval']}с, "
                              f"параллельность={strategy['concurrent_requests']}")
                    
                    # Обновление настроек мониторинга
                    self.monitor.current_scan_interval = strategy['interval']
                    self.monitor.max_concurrent_requests = strategy['concurrent_requests']
                    
                    # Запуск мониторинга
                    await self.monitor.start_monitoring(page)
                    
                except Exception as e:
                    logger.error(f"❌ Ошибка в цикле мониторинга: {e}")
                    
                    # Обновление метрик адаптивного мониторинга
                    await self.adaptive_monitoring.update_metrics(
                        response_time=30.0,  # Высокое время = ошибка
                        loads_found=0,
                        errors=1,
                        success=False
                    )
                    
                    # Пауза перед повторной попыткой
                    await asyncio.sleep(30)
            
        except Exception as e:
            logger.error(f"❌ Критическая ошибка мониторинга: {e}")
            await self.error_handler.handle_critical_error(e, self)
    
    async def run_daily_maintenance(self) -> None:
        """Ежедневное обслуживание системы"""
        while self.is_running:
            try:
                await asyncio.sleep(24 * 60 * 60)  # 24 часа
                
                logger.info("🧹 Запуск ежедневного обслуживания...")
                
                # Очистка старых записей
                deleted_count = await self.db.cleanup_old_records()
                logger.info(f"🧹 Удалено {deleted_count} старых записей")
                
                # Создание резервной копии через BackupManager
                if self.config['database']['backup_enabled']:
                    backup_success = await self.backup_manager.create_daily_backup()
                    if backup_success:
                        logger.info("✅ Ежедневный бэкап создан успешно")
                    else:
                        logger.error("❌ Ошибка создания бэкапа")
                
                # Отправка ежедневного отчета
                if self.config['telegram']['enable_daily_reports']:
                    daily_stats = await self.db.get_daily_stats()
                    await self.telegram.send_daily_report(daily_stats)
                
                # Отправка отчета о производительности
                perf_report = await self.performance.get_performance_report()
                await self.telegram.send_performance_report(perf_report)
                
                logger.info("✅ Ежедневное обслуживание завершено")
                
            except Exception as e:
                logger.error(f"❌ Ошибка ежедневного обслуживания: {e}")
    
    async def run_status_updates(self) -> None:
        """Отправка статусных обновлений"""
        while self.is_running:
            try:
                await asyncio.sleep(60 * 60)  # Каждый час
                
                # Получение статистики
                monitoring_stats = await self.monitor.get_monitoring_stats()
                performance_stats = await self.performance.get_performance_report()
                adaptation_report = await self.adaptive_monitoring.get_adaptation_report()
                
                # Формирование расширенного статуса
                status_msg = f"""📊 HOURLY STATUS REPORT

🔍 Loads Scanned: {monitoring_stats.get('scan_count', 0)}
📤 Notifications Sent: {monitoring_stats.get('loads_sent_total', 0)}
⏱ Avg Scan Time: {monitoring_stats.get('avg_response_time', 0):.2f}s
💾 Memory Usage: {performance_stats.get('system_resources', {}).get('avg_memory_percent', 0):.1f}%
🖥 CPU Usage: {performance_stats.get('system_resources', {}).get('avg_cpu_percent', 0):.1f}%
🟢 Session Status: {'Active' if monitoring_stats.get('is_monitoring') else 'Inactive'}
⚡️ Uptime: {monitoring_stats.get('uptime_hours', 0):.1f}h

🎯 ADAPTIVE MONITORING:
📈 Success Rate: {adaptation_report.get('success_rate', 0):.1%}
🐌 Avg Response: {adaptation_report.get('avg_response_time', 0):.1f}s
⚠️ Error Count: {adaptation_report.get('error_count', 0)}
📊 Adaptation Level: {adaptation_report.get('adaptation_level', 'UNKNOWN')}

Last Update: {datetime.now().strftime('%H:%M:%S')}"""
                
                await self.telegram.send_status_update(status_msg)
                
            except Exception as e:
                logger.error(f"❌ Ошибка отправки статуса: {e}")
    
    async def main(self) -> None:
        """Главная функция приложения с улучшенной обработкой ошибок и завершения"""
        startup_success = False
        monitoring_task = None
        maintenance_task = None
        status_task = None
        
        try:
            logger.info("🚛 Система мониторинга грузоперевозок Schneider запускается...")
            
            # Проверка системных требований
            await self.check_system_requirements()
            
            # Инициализация компонентов
            logger.info("🔧 Инициализация компонентов системы...")
            if not await self.initialize_components():
                raise Exception("Ошибка инициализации компонентов")
            
            # Авторизация с оптимизированными таймаутами
            logger.info("🔐 Выполнение входа в систему...")
            if not await self.authenticate():
                await self.diagnose_auth_failure()
                raise Exception("Ошибка входа в систему после всех попыток")
            
            # Настройка фильтров поиска
            logger.info("⚙️ Настройка параметров поиска грузов...")
            if not await self.setup_search_filters():
                logger.warning("⚠️ Не удалось настроить все параметры поиска")
            
            # Отправка уведомления о успешном запуске
            startup_message = (
                "🚀 Система мониторинга грузов запущена!\n\n"
                f"📧 Учетная запись: {self.config['schneider']['email']}\n"
                f"🌐 Сайт: {self.config['schneider']['login_url']}\n"
                f"⚙️ Режим работы браузера: {'Скрытый' if self.config['browser']['headless'] else 'Видимый'}\n"
                f"🔄 Интервал сканирования: {self.config['monitoring']['fast_scan_interval_seconds']} сек"
            )
            await self.telegram.send_status_update(startup_message)
            
            startup_success = True
            logger.info("✅ Система успешно запущена и готова к работе")
            
            # Установка флага запуска
            self.is_running = True
            
            # Создание и запуск задач с отслеживанием
            monitoring_task = asyncio.create_task(self.start_monitoring())
            maintenance_task = asyncio.create_task(self.run_daily_maintenance())
            status_task = asyncio.create_task(self.run_status_updates())
            
            self.running_tasks.update([monitoring_task, maintenance_task, status_task])
            
            # Ожидание завершения или сигнала остановки
            try:
                done, pending = await asyncio.wait(
                    [monitoring_task, maintenance_task, status_task, 
                     asyncio.create_task(self.shutdown_event.wait())],
                    return_when=asyncio.FIRST_COMPLETED
                )
                
                # Отмена оставшихся задач
                for task in pending:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                        
            except asyncio.CancelledError:
                logger.info("🛑 Получен сигнал завершения работы")
            
        except KeyboardInterrupt:
            logger.info("🛑 Получен сигнал остановки от пользователя...")
        except Exception as e:
            error_msg = str(e)
            logger.error(f"❌ Критическая ошибка системы: {error_msg}")
            
            # Отправка детального сообщения об ошибке
            if not startup_success:
                detailed_error = (
                    f"💥 ОШИБКА ЗАПУСКА СИСТЕМЫ МОНИТОРИНГА\n\n"
                    f"❌ Описание ошибки: {error_msg}\n"
                    f"⏰ Время возникновения: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                    f"🔧 Возможные причины:\n"
                    f"• Проблемы с подключением к интернету\n"
                    f"• Неверные данные для входа в систему\n"
                    f"• Блокировка IP-адреса службой безопасности\n"
                    f"• Изменения в интерфейсе сайта Schneider\n"
                    f"• Проблемы с работой браузера\n\n"
                    f"🔄 Система попытается восстановить работу автоматически..."
                )
                
                if self.telegram:
                    try:
                        await self.telegram.send_error_alert(detailed_error)
                    except Exception as telegram_error:
                        logger.error(f"❌ Ошибка отправки уведомления: {telegram_error}")
        
        finally:
            # Корректное завершение всех задач
            await self.cleanup_all_tasks()
            await self.cleanup()

    async def check_system_requirements(self) -> None:
        """Проверка системных требований"""
        try:
            logger.info("🔍 Проверка системных требований...")
            
            # Проверка доступности интернета
            import aiohttp
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get('https://www.google.com', timeout=10) as response:
                        if response.status != 200:
                            raise Exception("Internet connectivity check failed")
                logger.info("✅ Интернет-соединение работает")
            except Exception as e:
                raise Exception(f"No internet connection: {e}")
            
            # Проверка доступности Schneider сайта
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(self.config['schneider']['login_url'], timeout=15) as response:
                        if response.status not in [200, 403]:  # 403 может быть от Cloudflare
                            raise Exception(f"Schneider site returned status {response.status}")
                logger.info("✅ Сайт Schneider доступен")
            except Exception as e:
                logger.warning(f"⚠️ Проблемы с доступностью сайта Schneider: {e}")
            
            # Проверка наличия необходимых директорий
            required_dirs = ['data', 'logs', 'screenshots', 'backups']
            for dir_name in required_dirs:
                if not os.path.exists(dir_name):
                    os.makedirs(dir_name, exist_ok=True)
                    logger.info(f"📁 Создана директория: {dir_name}")
            
            logger.info("✅ Системные требования выполнены")
            
        except Exception as e:
            logger.error(f"❌ Ошибка проверки системных требований: {e}")
            raise

    async def diagnose_auth_failure(self) -> None:
        """Диагностика причин неудачи авторизации"""
        try:
            logger.info("🔍 Диагностика проблем авторизации...")
            
            diagnosis = []
            
            # Проверка учетных данных
            if not self.config.get('schneider', {}).get('email'):
                diagnosis.append("❌ Email не настроен")
            if not self.config.get('schneider', {}).get('password'):
                diagnosis.append("❌ Пароль не настроен")
            
            # Проверка браузера
            if not self.auth or not self.auth.browser:
                diagnosis.append("❌ Браузер не инициализирован")
            
            # Проверка доступности сайта
            try:
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    async with session.get(self.config['schneider']['login_url'], timeout=10) as response:
                        if response.status != 200:
                            diagnosis.append(f"⚠️ Сайт возвращает статус {response.status}")
            except Exception as e:
                diagnosis.append(f"❌ Сайт недоступен: {e}")
            
            if diagnosis:
                diagnosis_msg = "🔍 ДИАГНОСТИКА ПРОБЛЕМ АВТОРИЗАЦИИ:\n" + "\n".join(diagnosis)
                logger.error(diagnosis_msg)
                
                if self.telegram:
                    await self.telegram.send_error_alert(diagnosis_msg)
            
        except Exception as e:
            logger.error(f"❌ Ошибка диагностики: {e}")
    
    async def cleanup_all_tasks(self) -> None:
        """Корректное завершение всех активных задач"""
        try:
            logger.info("🧹 Завершение активных задач...")
            
            # Отмена всех активных задач
            for task in self.running_tasks.copy():
                if not task.done():
                    task.cancel()
                    try:
                        await asyncio.wait_for(task, timeout=5.0)
                    except (asyncio.CancelledError, asyncio.TimeoutError):
                        pass
                    except Exception as e:
                        logger.warning(f"⚠️ Ошибка завершения задачи: {e}")
                        
            self.running_tasks.clear()
            logger.info("✅ Все задачи завершены корректно")
            
        except Exception as e:
            logger.error(f"❌ Ошибка завершения задач: {e}")

    async def cleanup(self) -> None:
        """Очистка ресурсов при завершении"""
        try:
            logger.info("🧹 Очистка системных ресурсов...")
            
            self.is_running = False
            
            # Остановка мониторинга
            if self.monitor:
                logger.info("🛑 Остановка мониторинга...")
                try:
                    await asyncio.wait_for(self.monitor.stop_monitoring(), timeout=10.0)
                except asyncio.TimeoutError:
                    logger.warning("⚠️ Таймаут остановки мониторинга")
            
            # Закрытие браузера
            if self.auth:
                try:
                    await asyncio.wait_for(self.auth.close(), timeout=10.0)
                except asyncio.TimeoutError:
                    logger.warning("⚠️ Таймаут закрытия браузера")
            
            # Отправка уведомления о завершении
            if self.telegram:
                try:
                    await asyncio.wait_for(
                        self.telegram.send_status_update("🛑 Система мониторинга грузов остановлена"), 
                        timeout=5.0
                    )
                except asyncio.TimeoutError:
                    logger.warning("⚠️ Таймаут отправки уведомления")
            
            logger.info("✅ Очистка ресурсов завершена")
            
        except Exception as e:
            logger.error(f"❌ Ошибка очистки ресурсов: {e}")
    
    async def test_mode(self) -> None:
        """Расширенный тестовый режим с полным набором тестов"""
        try:
            logger.info("🧪 Запуск в расширенном тестовом режиме...")
            
            # Инициализация компонентов
            if not await self.initialize_components():
                raise Exception("Component initialization failed")
            
            # Запуск полного набора интеграционных тестов
            test_results = await self.integration_tests.run_full_test_suite()
            
            if test_results:
                logger.info("✅ Все тесты пройдены успешно")
                await self.telegram.send_status_update(
                    "🧪✅ ПОЛНЫЙ ТЕСТОВЫЙ РЕЖИМ ЗАВЕРШЕН УСПЕШНО\n"
                    "Все системы работают корректно!"
                )
            else:
                logger.error("❌ Некоторые тесты не пройдены")
                await self.telegram.send_error_alert(
                    "🧪❌ ТЕСТОВЫЙ РЕЖИМ: Обнаружены проблемы\n"
                    "Проверьте логи для подробностей"
                )
            
        except Exception as e:
            logger.error(f"❌ Критическая ошибка тестового режима: {e}")
            await self.telegram.send_error_alert(f"🧪💥 Критическая ошибка тестирования: {e}")
        finally:
            await self.cleanup()

def signal_handler(signum, frame):
    """Обработчик сигналов для корректного завершения работы системы"""
    logger.info(f"📡 Получен сигнал {signum}, инициируется корректное завершение работы...")
    if schneider_parser_instance:
        schneider_parser_instance.shutdown_event.set()
        logger.info("🛑 Сигнал завершения отправлен системе мониторинга")
    else:
        logger.warning("⚠️ Экземпляр системы не найден, выполняется немедленное завершение")
        sys.exit(0)

def main():
    """Точка входа в приложение"""
    # Настройка кодировки для корректной работы с Unicode
    setup_encoding()
    
    parser = argparse.ArgumentParser(description='Schneider FreightPower Load Parser')
    parser.add_argument('--test', action='store_true', help='Запуск в тестовом режиме')
    parser.add_argument('--config', default='config/config.json', help='Путь к конфигурационному файлу')
    parser.add_argument('--debug', action='store_true', help='Включить отладочный режим')
    parser.add_argument('--websocket-only', action='store_true', help='Использовать только WebSocket мониторинг')
    parser.add_argument('--screenshots', action='store_true', help='Включить создание скриншотов при ошибках')
    parser.add_argument('--no-session-restore', action='store_true', help='Не восстанавливать сохраненную сессию')
    
    args = parser.parse_args()
    
    # Настройка обработчиков сигналов
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Определение необходимости восстановления сессии
    restore_session = True
    if args.no_session_restore:
        restore_session = False
    else:
        # Проверяем наличие файла сессии
        session_file = "session_cookies.json"
        if os.path.exists(session_file):
            try:
                with open(session_file, 'r') as f:
                    session_data = json.load(f)
                    if session_data and len(session_data) > 0:
                        # Есть сохраненная сессия - спрашиваем пользователя
                        restore_session = ask_user_session_restore()
                    else:
                        restore_session = False
            except Exception as e:
                print(f"⚠️ Ошибка чтения файла сессии: {e}")
                restore_session = False
        else:
            # Файла сессии нет - новая авторизация
            restore_session = False
    
    # Создание экземпляра парсера с параметром восстановления сессии
    global schneider_parser_instance
    schneider_parser_instance = SchneiderParser(args.config, restore_session=restore_session)
    
    # Применение аргументов командной строки
    if args.debug:
        schneider_parser_instance.config['logging']['level'] = 'DEBUG'
        logger.info("🐛 Включен режим отладки")
    
    if args.screenshots:
        schneider_parser_instance.config['monitoring']['screenshot_on_error'] = True
        logger.info("📸 Включено создание скриншотов при ошибках")
    
    if args.websocket_only:
        schneider_parser_instance.config['monitoring']['primary_mode'] = 'websocket'
        logger.info("🌐 Включен только WebSocket мониторинг")
    
    # Запуск приложения
    if args.test:
        asyncio.run(schneider_parser_instance.test_mode())
    else:
        asyncio.run(schneider_parser_instance.main())

if __name__ == "__main__":
    main()
