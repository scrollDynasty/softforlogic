"""
Система восстановления и адаптивного мониторинга
"""

import asyncio
import time
import os
import shutil
from datetime import datetime
from typing import Dict, Optional
from collections import defaultdict

from .logger import logger
from .performance_monitor import PerformanceMonitor

class RecoverySystem:
    """Система автоматического восстановления"""
    
    def __init__(self, parser_instance):
        self.parser = parser_instance
        self.recovery_attempts = 0
        self.max_recovery_attempts = 3
        self.last_recovery_time = 0
        self.recovery_cooldown = 300  # 5 минут между попытками
        
    async def full_recovery_sequence(self) -> bool:
        """Полная процедура восстановления"""
        try:
            # Проверка cooldown
            if time.time() - self.last_recovery_time < self.recovery_cooldown:
                logger.warning(f"⏳ Recovery cooldown active, waiting...")
                return False
            
            logger.info("🔄 Начинаем процедуру восстановления...")
            self.last_recovery_time = time.time()
            
            # 1. Остановка всех активных процессов
            await self.stop_all_processes()
            
            # 2. Очистка кеша и временных файлов
            await self.cleanup_temp_files()
            
            # 3. Переинициализация браузера
            await self.reinitialize_browser()
            
            # 4. Повторная авторизация
            if not await self.parser.auth.login():
                raise Exception("Failed to re-authenticate during recovery")
            
            # 5. Проверка работоспособности
            test_result = await self.run_system_test()
            if not test_result:
                raise Exception("System test failed after recovery")
            
            logger.info("✅ Восстановление завершено успешно")
            await self.parser.telegram.send_status_update("🟢 Система восстановлена и работает")
            
            self.recovery_attempts = 0
            return True
            
        except Exception as e:
            self.recovery_attempts += 1
            logger.error(f"Recovery attempt {self.recovery_attempts} failed: {e}")
            
            if self.recovery_attempts >= self.max_recovery_attempts:
                await self.parser.telegram.send_error_alert(
                    "🆘 КРИТИЧЕСКАЯ ОШИБКА: Система не может восстановиться!\\n"
                    "Требуется ручное вмешательство."
                )
                return False
            
            # Увеличиваем задержку с каждой попыткой
            delay = 30 * (2 ** self.recovery_attempts)
            logger.info(f"⏳ Ожидание {delay} секунд перед следующей попыткой...")
            pass  # Убрана задержка для ускорения
            return await self.full_recovery_sequence()
    
    async def stop_all_processes(self) -> None:
        """Остановка всех активных процессов"""
        try:
            logger.info("🛑 Остановка активных процессов...")
            
            # Остановка мониторинга
            if hasattr(self.parser, 'monitor') and self.parser.monitor:
                await self.parser.monitor.stop_monitoring()
            
            # Пауза для завершения процессов
            pass  # Убрана задержка для ускорения
            
            logger.info("✅ Активные процессы остановлены")
            
        except Exception as e:
            logger.error(f"❌ Ошибка остановки процессов: {e}")
    
    async def cleanup_temp_files(self) -> None:
        """Очистка кеша и временных файлов"""
        try:
            logger.info("🧹 Очистка временных файлов...")
            
            # Очистка скриншотов старше 1 часа
            screenshots_dir = "screenshots"
            if os.path.exists(screenshots_dir):
                current_time = time.time()
                for filename in os.listdir(screenshots_dir):
                    file_path = os.path.join(screenshots_dir, filename)
                    if os.path.isfile(file_path):
                        file_age = current_time - os.path.getmtime(file_path)
                        if file_age > 3600:  # 1 час
                            os.remove(file_path)
            
            # Очистка старых логов
            logs_dir = "logs"
            if os.path.exists(logs_dir):
                current_time = time.time()
                for filename in os.listdir(logs_dir):
                    if filename.endswith('.log'):
                        file_path = os.path.join(logs_dir, filename)
                        file_age = current_time - os.path.getmtime(file_path)
                        if file_age > 7 * 24 * 3600:  # 7 дней
                            os.remove(file_path)
            
            logger.info("✅ Временные файлы очищены")
            
        except Exception as e:
            logger.error(f"❌ Ошибка очистки файлов: {e}")
    
    async def reinitialize_browser(self) -> None:
        """Переинициализация браузера"""
        try:
            logger.info("🔄 Переинициализация браузера...")
            
            # Закрытие старого браузера
            if hasattr(self.parser.auth, 'browser') and self.parser.auth.browser:
                await self.parser.auth.close()
            
            # Пауза перед переинициализацией
            pass  # Убрана задержка для ускорения
            
            # Новая инициализация
            if not await self.parser.auth.initialize_browser():
                raise Exception("Failed to reinitialize browser")
            
            logger.info("✅ Браузер переинициализирован")
            
        except Exception as e:
            logger.error(f"❌ Ошибка переинициализации браузера: {e}")
            raise
    
    async def run_system_test(self) -> bool:
        """Быстрая проверка работоспособности системы"""
        try:
            logger.info("🧪 Проверка работоспособности системы...")
            
            # Проверка авторизации
            if not self.parser.auth.is_authenticated:
                return False
            
            # Проверка доступности страницы
            page = await self.parser.auth.get_page()
            if not page:
                return False
            
            # Попытка загрузки главной страницы
            await page.goto("https://freightpower.schneider.com/loads", 
                          timeout=30000, wait_until='networkidle')
            
            # Проверка наличия элементов на странице
            body = await page.query_selector('body')
            if not body:
                return False
            
            logger.info("✅ Система работоспособна")
            return True
            
        except Exception as e:
            logger.error(f"❌ Система не работоспособна: {e}")
            return False

class AdaptiveMonitoring:
    """Система адаптивного мониторинга"""
    
    def __init__(self):
        self.success_rate = 1.0
        self.avg_response_time = 2.0
        self.error_count = 0
        self.last_loads_found = 0
        self.consecutive_empty_scans = 0
        self.performance_history = []
        self.max_history_size = 100
        
    async def adjust_scanning_strategy(self) -> Dict:
        """Динамическая настройка параметров сканирования"""
        strategy = {
            'interval': 2,
            'concurrent_requests': 3,
            'timeout': 15,
            'enable_screenshots': False,
            'use_websocket': True,
            'max_retries': 3
        }
        
        # Если много ошибок - снижаем нагрузку
        if self.error_count > 5:
            strategy['interval'] = 5
            strategy['concurrent_requests'] = 1
            strategy['enable_screenshots'] = True
            strategy['max_retries'] = 1
            logger.info("📉 Снижаем интенсивность из-за ошибок")
            
        # Если медленные ответы - увеличиваем timeout и интервал
        if self.avg_response_time > 5:
            strategy['timeout'] = 30
            strategy['interval'] = max(strategy['interval'], 4)
            logger.info("🐌 Увеличиваем таймауты из-за медленных ответов")
            
        # Если нет новых грузов - снижаем частоту
        if self.consecutive_empty_scans > 10:
            strategy['interval'] = min(strategy['interval'] + 2, 10)
            strategy['use_websocket'] = False  # Переключаемся на обычное сканирование
            logger.info("😴 Снижаем частоту из-за отсутствия грузов")
        
        # Если низкий success rate - консервативные настройки
        if self.success_rate < 0.7:
            strategy['interval'] = 8
            strategy['concurrent_requests'] = 1
            strategy['timeout'] = 45
            strategy['enable_screenshots'] = True
            logger.info("⚠️ Консервативные настройки из-за низкого success rate")
        
        # Если все хорошо - оптимизируем для скорости
        if (self.success_rate > 0.95 and 
            self.avg_response_time < 3 and 
            self.error_count < 2):
            strategy['interval'] = 2
            strategy['concurrent_requests'] = 5
            strategy['timeout'] = 15
            strategy['use_websocket'] = True
            logger.info("🚀 Оптимальные настройки - максимальная производительность")
            
        return strategy
    
    async def update_metrics(self, response_time: float, loads_found: int, 
                           errors: int, success: bool) -> None:
        """Обновление метрик для адаптации"""
        
        # Обновление среднего времени ответа (экспоненциальное сглаживание)
        self.avg_response_time = (self.avg_response_time * 0.8) + (response_time * 0.2)
        
        # Обновление счетчика пустых сканирований
        if loads_found == 0:
            self.consecutive_empty_scans += 1
        else:
            self.consecutive_empty_scans = 0
            
        self.last_loads_found = loads_found
        
        # Обновление счетчика ошибок (постепенное снижение)
        if errors > 0:
            self.error_count += errors
        else:
            self.error_count = max(0, self.error_count - 0.1)
        
        # Обновление success rate
        self.performance_history.append(success)
        if len(self.performance_history) > self.max_history_size:
            self.performance_history.pop(0)
        
        if self.performance_history:
            self.success_rate = sum(self.performance_history) / len(self.performance_history)
    
    async def get_adaptation_report(self) -> Dict:
        """Получение отчета об адаптации"""
        return {
            'success_rate': self.success_rate,
            'avg_response_time': self.avg_response_time,
            'error_count': self.error_count,
            'consecutive_empty_scans': self.consecutive_empty_scans,
            'last_loads_found': self.last_loads_found,
            'performance_samples': len(self.performance_history),
            'adaptation_level': self._get_adaptation_level()
        }
    
    def _get_adaptation_level(self) -> str:
        """Определение уровня адаптации"""
        if self.success_rate > 0.95 and self.avg_response_time < 3:
            return "OPTIMAL"
        elif self.success_rate > 0.8 and self.avg_response_time < 5:
            return "GOOD"
        elif self.success_rate > 0.6:
            return "DEGRADED"
        else:
            return "CRITICAL"
    
    async def should_trigger_recovery(self) -> bool:
        """Определяет, нужно ли запускать восстановление"""
        critical_conditions = [
            self.success_rate < 0.3,  # Менее 30% успешных операций
            self.error_count > 20,    # Более 20 ошибок
            self.avg_response_time > 30,  # Очень медленные ответы
            self.consecutive_empty_scans > 50  # Очень долго нет грузов
        ]
        
        return any(critical_conditions)

class BackupManager:
    """Менеджер резервного копирования"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.backup_dir = "backups"
        os.makedirs(self.backup_dir, exist_ok=True)
        
    async def create_daily_backup(self) -> bool:
        """Создание ежедневного бэкапа"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = os.path.join(self.backup_dir, f"loads_backup_{timestamp}.db")
            
            # Копирование БД
            if os.path.exists(self.db_path):
                shutil.copy2(self.db_path, backup_path)
                logger.info(f"✅ Backup created: {backup_path}")
            
            # Очистка старых бэкапов (оставляем последние 7)
            await self.cleanup_old_backups(7)
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Backup failed: {e}")
            return False
    
    async def cleanup_old_backups(self, keep_count: int = 7) -> None:
        """Очистка старых бэкапов"""
        try:
            if not os.path.exists(self.backup_dir):
                return
            
            # Получение списка файлов бэкапов
            backup_files = []
            for filename in os.listdir(self.backup_dir):
                if filename.startswith("loads_backup_") and filename.endswith(".db"):
                    file_path = os.path.join(self.backup_dir, filename)
                    backup_files.append((file_path, os.path.getmtime(file_path)))
            
            # Сортировка по времени (новые первые)
            backup_files.sort(key=lambda x: x[1], reverse=True)
            
            # Удаление старых файлов
            for file_path, _ in backup_files[keep_count:]:
                os.remove(file_path)
                logger.info(f"🗑️ Removed old backup: {os.path.basename(file_path)}")
                
        except Exception as e:
            logger.error(f"❌ Cleanup backups failed: {e}")
    
    async def restore_from_backup(self, backup_filename: str = None) -> bool:
        """Восстановление из бэкапа"""
        try:
            if backup_filename is None:
                # Найти самый новый бэкап
                backup_files = []
                for filename in os.listdir(self.backup_dir):
                    if filename.startswith("loads_backup_") and filename.endswith(".db"):
                        file_path = os.path.join(self.backup_dir, filename)
                        backup_files.append((file_path, os.path.getmtime(file_path)))
                
                if not backup_files:
                    logger.error("❌ No backup files found")
                    return False
                
                backup_files.sort(key=lambda x: x[1], reverse=True)
                backup_path = backup_files[0][0]
            else:
                backup_path = os.path.join(self.backup_dir, backup_filename)
            
            if os.path.exists(backup_path):
                shutil.copy2(backup_path, self.db_path)
                logger.info(f"✅ Database restored from: {os.path.basename(backup_path)}")
                return True
            else:
                logger.error(f"❌ Backup file not found: {backup_path}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Restore failed: {e}")
            return False