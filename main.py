#!/usr/bin/env python3
"""
🚛 Schneider FreightPower Load Parser
Высокопроизводительный автоматический парсер для мониторинга грузов
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

# Добавление пути к модулям
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.utils.logger import logger
from src.utils.performance_monitor import PerformanceMonitor
from src.utils.error_handler import ErrorHandler
from src.auth.schneider_auth import SchneiderAuth
from src.parser.load_parser import LoadParser
from src.parser.load_monitor import LoadMonitor
from src.telegram.telegram_bot import TelegramNotifier
from src.database.db_manager import DatabaseManager

class SchneiderParser:
    def __init__(self, config_path: str = "config/config.json"):
        self.config_path = config_path
        self.config = self.load_config()
        self.is_running = False
        
        # Инициализация компонентов
        self.auth = None
        self.parser = None
        self.monitor = None
        self.telegram = None
        self.db = None
        self.performance = None
        self.error_handler = None
        
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
        """Загрузка переменных окружения"""
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
            
            # Schneider
            schneider_email = os.getenv('SCHNEIDER_EMAIL')
            schneider_password = os.getenv('SCHNEIDER_PASSWORD')
            
            if schneider_email:
                config['schneider']['email'] = schneider_email
            if schneider_password:
                config['schneider']['password'] = schneider_password
            
            logger.info("✅ Переменные окружения загружены")
            
        except Exception as e:
            logger.warning(f"⚠️ Ошибка загрузки переменных окружения: {e}")
    
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
            
            # 5. Инициализация авторизации
            self.auth = SchneiderAuth(self.config)
            if not await self.auth.initialize_browser():
                raise Exception("Failed to initialize browser")
            
            # 6. Инициализация парсера
            self.parser = LoadParser(self.config)
            
            # 7. Инициализация мониторинга
            self.monitor = LoadMonitor(self.config, self.parser, self.telegram, self.db)
            
            logger.info("✅ Все компоненты инициализированы успешно")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации компонентов: {e}")
            await self.error_handler.handle_critical_error(e, self)
            return False
    
    async def authenticate(self) -> bool:
        """Авторизация в системе"""
        try:
            logger.info("🔐 Начинаем авторизацию...")
            
            if not await self.auth.login():
                raise Exception("Authentication failed")
            
            logger.info("✅ Авторизация успешна")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка авторизации: {e}")
            await self.error_handler.handle_auth_error(e)
            return False
    
    async def setup_search_filters(self) -> bool:
        """Настройка фильтров поиска"""
        try:
            criteria = self.config['search_criteria']
            
            success = await self.parser.set_search_filters(
                location=criteria['default_pickup_location'],
                max_deadhead=criteria['max_deadhead_miles'],
                min_miles=criteria['min_total_miles']
            )
            
            if success:
                logger.info("✅ Фильтры поиска настроены")
            else:
                logger.warning("⚠️ Ошибка настройки фильтров")
            
            return success
            
        except Exception as e:
            logger.error(f"❌ Ошибка настройки фильтров: {e}")
            return False
    
    async def start_monitoring(self) -> None:
        """Запуск мониторинга"""
        try:
            logger.info("🚀 Запуск мониторинга грузов...")
            
            # Получение страницы
            page = await self.auth.get_page()
            if not page:
                raise Exception("No active page available")
            
            # Запуск мониторинга
            await self.monitor.start_monitoring(page)
            
        except Exception as e:
            logger.error(f"❌ Ошибка запуска мониторинга: {e}")
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
                
                # Создание резервной копии
                if self.config['database']['backup_enabled']:
                    await self.db.backup_database()
                
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
                
                # Формирование статуса
                status_msg = f"""📊 HOURLY STATUS REPORT

🔍 Loads Scanned: {monitoring_stats.get('scan_count', 0)}
📤 Notifications Sent: {monitoring_stats.get('loads_sent_total', 0)}
⏱ Avg Scan Time: {monitoring_stats.get('avg_response_time', 0):.2f}s
💾 Memory Usage: {performance_stats.get('system_resources', {}).get('avg_memory_percent', 0):.1f}%
🖥 CPU Usage: {performance_stats.get('system_resources', {}).get('avg_cpu_percent', 0):.1f}%
🟢 Session Status: {'Active' if monitoring_stats.get('is_monitoring') else 'Inactive'}
⚡️ Uptime: {monitoring_stats.get('uptime_hours', 0):.1f}h

Last Update: {datetime.now().strftime('%H:%M:%S')}"""
                
                await self.telegram.send_status_update(status_msg)
                
            except Exception as e:
                logger.error(f"❌ Ошибка отправки статуса: {e}")
    
    async def main(self) -> None:
        """Главная функция приложения"""
        try:
            logger.info("🚛 Schneider FreightPower Load Parser запускается...")
            
            # Инициализация компонентов
            if not await self.initialize_components():
                raise Exception("Component initialization failed")
            
            # Авторизация
            if not await self.authenticate():
                raise Exception("Authentication failed")
            
            # Настройка фильтров
            await self.setup_search_filters()
            
            # Отправка уведомления о запуске
            await self.telegram.send_status_update("🚀 Schneider Parser запущен и готов к работе!")
            
            # Установка флага запуска
            self.is_running = True
            
            # Запуск всех задач
            await asyncio.gather(
                self.start_monitoring(),
                self.run_daily_maintenance(),
                self.run_status_updates()
            )
            
        except KeyboardInterrupt:
            logger.info("🛑 Получен сигнал остановки...")
        except Exception as e:
            logger.error(f"❌ Критическая ошибка: {e}")
            await self.error_handler.handle_critical_error(e, self)
        finally:
            await self.cleanup()
    
    async def cleanup(self) -> None:
        """Очистка ресурсов при завершении"""
        try:
            logger.info("🧹 Очистка ресурсов...")
            
            self.is_running = False
            
            # Остановка мониторинга
            if self.monitor:
                await self.monitor.stop_monitoring()
            
            # Закрытие браузера
            if self.auth:
                await self.auth.close()
            
            # Отправка уведомления о завершении
            if self.telegram:
                await self.telegram.send_status_update("🛑 Schneider Parser остановлен")
            
            logger.info("✅ Очистка завершена")
            
        except Exception as e:
            logger.error(f"❌ Ошибка очистки: {e}")
    
    async def test_mode(self) -> None:
        """Тестовый режим"""
        try:
            logger.info("🧪 Запуск в тестовом режиме...")
            
            # Инициализация компонентов
            if not await self.initialize_components():
                raise Exception("Component initialization failed")
            
            # Авторизация
            if not await self.authenticate():
                raise Exception("Authentication failed")
            
            # Тест парсинга одной страницы
            page = await self.auth.get_page()
            if page:
                await page.goto("https://freightpower.schneider.com/loads", wait_until='networkidle')
                loads = await self.parser.scan_loads_page(page)
                
                logger.info(f"🧪 Тест парсинга: найдено {len(loads)} грузов")
                
                if loads:
                    profitable_loads = await self.parser.filter_profitable_loads(loads)
                    logger.info(f"🧪 Тест фильтрации: {len(profitable_loads)} прибыльных грузов")
            
            # Тест Telegram
            await self.telegram.send_status_update("🧪 Тестовое сообщение - система работает!")
            
            logger.info("✅ Тестовый режим завершен успешно")
            
        except Exception as e:
            logger.error(f"❌ Ошибка тестового режима: {e}")
        finally:
            await self.cleanup()

def signal_handler(signum, frame):
    """Обработчик сигналов для корректного завершения"""
    logger.info(f"📡 Получен сигнал {signum}, завершение работы...")
    sys.exit(0)

def main():
    """Точка входа в приложение"""
    parser = argparse.ArgumentParser(description='Schneider FreightPower Load Parser')
    parser.add_argument('--test', action='store_true', help='Запуск в тестовом режиме')
    parser.add_argument('--config', default='config/config.json', help='Путь к конфигурационному файлу')
    parser.add_argument('--debug', action='store_true', help='Включить отладочный режим')
    
    args = parser.parse_args()
    
    # Настройка обработчиков сигналов
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Создание экземпляра парсера
    schneider_parser = SchneiderParser(args.config)
    
    # Запуск приложения
    if args.test:
        asyncio.run(schneider_parser.test_mode())
    else:
        asyncio.run(schneider_parser.main())

if __name__ == "__main__":
    main()
