"""
Интеграционные тесты системы Schneider Parser
"""

import asyncio
import time
from typing import Dict, List
from datetime import datetime

from ..utils.logger import logger
from ..auth.schneider_auth import SchneiderAuth
from ..parser.load_parser import LoadParser
from ..telegram.telegram_bot import TelegramNotifier
from ..database.db_manager import DatabaseManager
from ..utils.performance_monitor import PerformanceMonitor
from ..utils.rate_calculator import RateCalculator

class IntegrationTests:
    """Класс для проведения интеграционных тестов"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.auth = SchneiderAuth(config)
        self.parser = LoadParser(config)
        self.telegram = TelegramNotifier(
            config['telegram']['bot_token'],
            config['telegram']['chat_id']
        )
        self.db = DatabaseManager(config['database']['path'])
        self.performance = PerformanceMonitor()
        
    async def run_full_test_suite(self) -> bool:
        """Полный набор тестов системы"""
        test_results = {}
        
        logger.info("🧪 Запуск полного набора тестов...")
        
        # Тест инициализации базы данных
        test_results['database_init'] = await self.test_database_initialization()
        
        # Тест авторизации
        test_results['auth'] = await self.test_authentication()
        
        # Тест парсинга (только если авторизация прошла)
        if test_results['auth']:
            test_results['parsing'] = await self.test_parsing_functionality()
        else:
            test_results['parsing'] = False
            
        # Тест Telegram уведомлений
        test_results['telegram'] = await self.test_telegram_notifications()
        
        # Тест базы данных
        test_results['database'] = await self.test_database_operations()
        
        # Тест производительности
        test_results['performance'] = await self.test_performance_metrics()
        
        # Тест калькулятора ставок
        test_results['rate_calculator'] = await self.test_rate_calculator()
        
        # Сводный отчет
        all_passed = all(test_results.values())
        
        report = "🧪 РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ:\\n"
        for test_name, result in test_results.items():
            emoji = "✅" if result else "❌"
            report += f"{emoji} {test_name.upper().replace('_', ' ')}: {'PASSED' if result else 'FAILED'}\\n"
        
        if all_passed:
            report += "\\n🟢 ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО"
        else:
            report += "\\n🔴 ОБНАРУЖЕНЫ ПРОБЛЕМЫ"
            
        await self.telegram.send_status_update(report)
        logger.info(report.replace('\\n', '\n'))
        
        return all_passed
    
    async def test_database_initialization(self) -> bool:
        """Тест инициализации базы данных"""
        try:
            logger.info("🧪 Тестирование инициализации базы данных...")
            
            result = await self.db.init_database()
            if result:
                logger.info("✅ База данных инициализирована успешно")
                return True
            else:
                logger.error("❌ Ошибка инициализации базы данных")
                return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка теста базы данных: {e}")
            return False
    
    async def test_authentication(self) -> bool:
        """Тест авторизации"""
        try:
            logger.info("🧪 Тестирование авторизации...")
            
            # Инициализация браузера
            if not await self.auth.initialize_browser():
                logger.error("❌ Ошибка инициализации браузера")
                return False
            
            # Попытка авторизации
            result = await self.auth.login()
            if result:
                logger.info("✅ Авторизация прошла успешно")
                return True
            else:
                logger.error("❌ Ошибка авторизации")
                return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка теста авторизации: {e}")
            return False
    
    async def test_parsing_functionality(self) -> bool:
        """Тест парсинга с тестовыми данными"""
        try:
            logger.info("🧪 Тестирование функций парсинга...")
            
            # Получение страницы
            page = await self.auth.get_page()
            if not page:
                logger.error("❌ Не удалось получить страницу")
                return False
            
            # Переход на страницу поиска
            await page.goto("https://freightpower.schneider.com/loads", 
                          wait_until='networkidle', timeout=30000)
            
            # Проверка загрузки элементов
            load_elements = await self.parser.find_elements_smart(page, 'load_items')
            if not load_elements:
                logger.warning("⚠️ Грузы не найдены (возможно, страница пуста)")
                return True  # Не ошибка, если нет грузов
            
            # Тест извлечения данных
            test_load = load_elements[0]
            load_data = await self.parser.extract_load_data(test_load)
            
            required_fields = ['id', 'pickup', 'delivery', 'miles', 'deadhead']
            missing_fields = [field for field in required_fields if not load_data.get(field)]
            
            if missing_fields:
                logger.warning(f"⚠️ Отсутствуют поля: {missing_fields}")
                return False
            
            logger.info(f"✅ Парсинг работает: найдено {len(load_elements)} грузов")
            return True
                
        except Exception as e:
            logger.error(f"❌ Ошибка теста парсинга: {e}")
            return False
    
    async def test_telegram_notifications(self) -> bool:
        """Тест Telegram уведомлений"""
        try:
            logger.info("🧪 Тестирование Telegram уведомлений...")
            
            # Тест соединения
            if not await self.telegram.test_connection():
                logger.error("❌ Ошибка соединения с Telegram")
                return False
            
            # Тест отправки сообщения
            test_message = f"🧪 Тестовое сообщение - {datetime.now().strftime('%H:%M:%S')}"
            result = await self.telegram.send_status_update(test_message)
            
            if result:
                logger.info("✅ Telegram уведомления работают")
                return True
            else:
                logger.error("❌ Ошибка отправки Telegram сообщения")
                return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка теста Telegram: {e}")
            return False
    
    async def test_database_operations(self) -> bool:
        """Тест операций с базой данных"""
        try:
            logger.info("🧪 Тестирование операций с базой данных...")
            
            # Тестовые данные
            test_load_data = {
                'id': 'TEST-12345',
                'pickup': 'Chicago, IL',
                'delivery': 'Detroit, MI',
                'rate': 1200.0,
                'miles': 280,
                'deadhead': 50,
                'equipment': 'Van',
                'pickup_date': '2024-01-15 08:00'
            }
            
            test_analysis = {
                'total_miles': 330,
                'rate_per_mile': 3.64,
                'profitability_score': 2.4,
                'is_profitable': True
            }
            
            # Тест проверки новизны
            is_new = await self.db.is_load_new(test_load_data['id'], 'test_hash')
            if not is_new:
                logger.info("✅ Проверка дубликатов работает")
            
            # Тест сохранения
            save_result = await self.db.mark_as_sent(test_load_data, test_analysis)
            if not save_result:
                logger.error("❌ Ошибка сохранения в базу данных")
                return False
            
            # Тест получения статистики
            stats = await self.db.get_daily_stats()
            if not isinstance(stats, dict):
                logger.error("❌ Ошибка получения статистики")
                return False
            
            logger.info("✅ Операции с базой данных работают")
            return True
                
        except Exception as e:
            logger.error(f"❌ Ошибка теста базы данных: {e}")
            return False
    
    async def test_performance_metrics(self) -> bool:
        """Тест метрик производительности"""
        try:
            logger.info("🧪 Тестирование метрик производительности...")
            
            # Тест отслеживания времени сканирования
            start_time = time.time()
            pass  # Убрана задержка для ускорения  # Симуляция работы
            scan_time = int((time.time() - start_time) * 1000)
            
            await self.performance.track_scan_performance(scan_time)
            
            # Тест отслеживания системных ресурсов
            resources = await self.performance.track_system_resources()
            
            if not isinstance(resources, dict):
                logger.error("❌ Ошибка получения системных ресурсов")
                return False
            
            # Тест получения отчета
            report = await self.performance.get_performance_report()
            
            if not isinstance(report, dict):
                logger.error("❌ Ошибка получения отчета производительности")
                return False
            
            logger.info("✅ Мониторинг производительности работает")
            return True
                
        except Exception as e:
            logger.error(f"❌ Ошибка теста производительности: {e}")
            return False
    
    async def test_rate_calculator(self) -> bool:
        """Тест калькулятора ставок"""
        try:
            logger.info("🧪 Тестирование калькулятора ставок...")
            
            # Тестовые данные
            deadhead = 50
            miles = 250
            rate = 1500.0
            
            # Тест расчета минимальной ставки
            min_rate = RateCalculator.calculate_minimum_rate(deadhead, miles)
            if min_rate != (deadhead + miles) * 1.7:
                logger.error("❌ Ошибка расчета минимальной ставки")
                return False
            
            # Тест проверки прибыльности
            is_profitable, analysis = RateCalculator.is_load_profitable(
                deadhead, miles, rate
            )
            
            if not isinstance(analysis, dict):
                logger.error("❌ Ошибка анализа прибыльности")
                return False
            
            required_fields = ['total_miles', 'rate_per_mile', 'profitability_score']
            if not all(field in analysis for field in required_fields):
                logger.error("❌ Отсутствуют поля в анализе прибыльности")
                return False
            
            # Тест расчета затрат на топливо
            fuel_cost = RateCalculator.calculate_fuel_costs(300)
            if fuel_cost <= 0:
                logger.error("❌ Ошибка расчета затрат на топливо")
                return False
            
            logger.info("✅ Калькулятор ставок работает корректно")
            return True
                
        except Exception as e:
            logger.error(f"❌ Ошибка теста калькулятора: {e}")
            return False
    
    async def cleanup(self) -> None:
        """Очистка после тестов"""
        try:
            if self.auth:
                await self.auth.close()
            logger.info("✅ Очистка после тестов завершена")
        except Exception as e:
            logger.error(f"❌ Ошибка очистки: {e}")