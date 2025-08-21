import asyncio
import time
import json
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from playwright.async_api import Page

from ..utils.logger import logger
from ..utils.performance_monitor import PerformanceMonitor
from .load_parser import LoadParser

class LoadMonitor:
    def __init__(self, config: Dict, parser: LoadParser, telegram_notifier, db_manager):
        self.config = config
        self.parser = parser
        self.telegram = telegram_notifier
        self.db = db_manager
        self.performance = PerformanceMonitor()
        
        # Настройки мониторинга
        self.scan_interval = config['monitoring']['fast_scan_interval_seconds']
        self.max_concurrent_requests = config['monitoring']['max_concurrent_requests']
        self.max_retry_attempts = config['monitoring']['max_retry_attempts']
        self.adaptive_scanning = config['monitoring']['adaptive_scanning']
        
        # Состояние мониторинга
        self.is_monitoring = False
        self.last_scan_time = 0
        self.scan_count = 0
        self.loads_found_total = 0
        self.loads_sent_total = 0
        self.error_count = 0
        
        # Адаптивные параметры
        self.current_scan_interval = self.scan_interval
        self.success_rate = 1.0
        self.avg_response_time = 2.0
        
    async def start_monitoring(self, page: Page) -> None:
        """Запуск мониторинга"""
        try:
            logger.info("🚀 Запуск мониторинга грузов...")
            self.is_monitoring = True
            
            # Гибридная стратегия мониторинга
            await asyncio.gather(
                self.fast_scan_monitoring(page),
                self.session_maintenance(page),
                self.performance_monitoring(),
                self.adaptive_scanning_control()
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка запуска мониторинга: {e}")
            self.is_monitoring = False
    
    async def fast_scan_monitoring(self, page: Page) -> None:
        """Быстрое сканирование (основной метод)"""
        while self.is_monitoring:
            start_time = time.time()
            
            try:
                # Адаптивный интервал на основе производительности
                if self.adaptive_scanning:
                    self.current_scan_interval = self._calculate_adaptive_interval()
                
                # Параллельное сканирование нескольких страниц
                tasks = []
                for page_num in range(1, 4):  # Сканируем первые 3 страницы
                    task = asyncio.create_task(
                        self.scan_single_page(page, page_num)
                    )
                    tasks.append(task)
                
                # Ожидание всех сканирований с timeout
                results = await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True),
                    timeout=self.config['monitoring']['max_scan_time_seconds']
                )
                
                # Обработка результатов
                all_loads = []
                for result in results:
                    if isinstance(result, list):
                        all_loads.extend(result)
                
                # Фильтрация и отправка
                await self.process_loads_batch(all_loads)
                
                # Обновление статистики
                self.scan_count += 1
                self.loads_found_total += len(all_loads)
                
                # Логирование цикла
                duration = (time.time() - start_time) * 1000
                await self._log_monitoring_cycle(len(all_loads), duration)
                
            except asyncio.TimeoutError:
                logger.warning("⏰ Таймаут сканирования - пропускаем цикл")
                self.error_count += 1
            except Exception as e:
                logger.error(f"❌ Ошибка цикла сканирования: {e}")
                self.error_count += 1
                await self._handle_scan_error(e, page)
            
            # Точный timing для интервалов
            elapsed = time.time() - start_time
            sleep_time = max(0, self.current_scan_interval - elapsed)
            await asyncio.sleep(sleep_time)
    
    async def scan_single_page(self, page: Page, page_num: int) -> List[Dict]:
        """Сканирование одной страницы"""
        try:
            # Переход на страницу с грузами
            loads_url = f"https://freightpower.schneider.com/loads?page={page_num}"
            await page.goto(loads_url, wait_until='networkidle')
            
            # Сканирование грузов
            loads = await self.parser.scan_loads_page(page)
            
            # Фильтрация прибыльных грузов
            profitable_loads = await self.parser.filter_profitable_loads(loads)
            
            logger.debug(f"📄 Страница {page_num}: {len(loads)} грузов, {len(profitable_loads)} прибыльных")
            return profitable_loads
            
        except Exception as e:
            logger.error(f"❌ Ошибка сканирования страницы {page_num}: {e}")
            return []
    
    async def process_loads_batch(self, loads: List[Dict]) -> None:
        """Пакетная обработка грузов с максимальной скоростью"""
        if not loads:
            return
        
        # Группируем задачи для параллельной обработки
        processing_tasks = []
        
        for load in loads:
            task = asyncio.create_task(
                self.process_single_load(load)
            )
            processing_tasks.append(task)
        
        # Параллельная обработка с ограничением
        semaphore = asyncio.Semaphore(5)  # Максимум 5 одновременных обработок
        
        async def bounded_process(task):
            async with semaphore:
                return await task
        
        results = await asyncio.gather(
            *[bounded_process(task) for task in processing_tasks],
            return_exceptions=True
        )
        
        # Подсчет статистики
        successful = sum(1 for r in results if r is True)
        self.loads_sent_total += successful
        
        logger.info(f"📦 Обработано пакетом: {successful}/{len(loads)} грузов отправлено")
    
    async def process_single_load(self, load_data: Dict) -> bool:
        """Обработка одного груза с максимальной скоростью"""
        try:
            # 1. Быстрая проверка на дубли (< 0.01 сек)
            load_hash = self.db.generate_load_hash(load_data)
            if not await self.db.is_load_new(load_data['id'], load_hash):
                return False
            
            # 2. Расчет прибыльности (< 0.01 сек)
            analysis = load_data.get('analysis', {})
            if not analysis:
                return False
            
            # 3. Параллельная отправка и сохранение (< 0.5 сек)
            send_task = asyncio.create_task(
                self.telegram.send_notification(load_data, analysis)
            )
            save_task = asyncio.create_task(
                self.db.mark_as_sent(load_data, analysis)
            )
            
            # Ожидание обеих операций
            send_result, save_result = await asyncio.gather(
                send_task, save_task, return_exceptions=True
            )
            
            if isinstance(send_result, Exception):
                logger.error(f"❌ Ошибка отправки уведомления: {send_result}")
                return False
                
            if isinstance(save_result, Exception):
                logger.error(f"❌ Ошибка сохранения в БД: {save_result}")
            
            logger.info(f"✅ Отправлен прибыльный груз: {load_data['id']} "
                       f"(${analysis.get('rate_per_mile', 0):.2f}/mile)")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка обработки груза {load_data.get('id', 'unknown')}: {e}")
            return False
    
    async def session_maintenance(self, page: Page) -> None:
        """Поддержка активной сессии"""
        while self.is_monitoring:
            try:
                await asyncio.sleep(self.config['monitoring']['session_check_interval_minutes'] * 60)
                
                # Проверка активности сессии
                current_url = page.url
                if 'login' in current_url or 'signin' in current_url:
                    logger.warning("⚠️ Сессия истекла, требуется переавторизация")
                    # Здесь должна быть логика переавторизации
                    break
                
                logger.debug("✅ Сессия активна")
                
            except Exception as e:
                logger.error(f"❌ Ошибка проверки сессии: {e}")
    
    async def performance_monitoring(self) -> None:
        """Мониторинг производительности"""
        while self.is_monitoring:
            try:
                await asyncio.sleep(60)  # Каждую минуту
                
                # Получение метрик производительности
                resources = await self.performance.track_system_resources()
                
                # Проверка необходимости масштабирования
                if await self.performance.should_scale_down():
                    logger.warning("🔥 Высокая нагрузка - снижаем интенсивность")
                    self.current_scan_interval = min(self.current_scan_interval * 1.5, 10)
                
                # Логирование метрик
                if resources:
                    logger.debug(f"📊 CPU: {resources.get('cpu_usage', 0):.1f}%, "
                               f"Memory: {resources.get('memory_usage', 0):.1f}%")
                
            except Exception as e:
                logger.error(f"❌ Ошибка мониторинга производительности: {e}")
    
    async def adaptive_scanning_control(self) -> None:
        """Адаптивное управление сканированием"""
        while self.is_monitoring:
            try:
                await asyncio.sleep(300)  # Каждые 5 минут
                
                # Анализ производительности
                if self.scan_count > 0:
                    self.success_rate = (self.scan_count - self.error_count) / self.scan_count
                
                # Корректировка параметров
                if self.success_rate < 0.8:
                    self.current_scan_interval = min(self.current_scan_interval * 1.2, 10)
                    logger.info(f"🔧 Снижена частота сканирования: {self.current_scan_interval:.1f}s")
                elif self.success_rate > 0.95 and self.avg_response_time < 3000:
                    self.current_scan_interval = max(self.current_scan_interval * 0.9, 1)
                    logger.info(f"🔧 Увеличена частота сканирования: {self.current_scan_interval:.1f}s")
                
            except Exception as e:
                logger.error(f"❌ Ошибка адаптивного управления: {e}")
    
    def _calculate_adaptive_interval(self) -> float:
        """Расчет адаптивного интервала сканирования"""
        base_interval = self.scan_interval
        
        # Корректировка на основе успешности
        if self.success_rate < 0.7:
            base_interval *= 1.5
        elif self.success_rate > 0.9:
            base_interval *= 0.8
        
        # Корректировка на основе времени ответа
        if self.avg_response_time > 5000:
            base_interval *= 1.3
        elif self.avg_response_time < 1000:
            base_interval *= 0.9
        
        # Ограничения
        return max(1.0, min(10.0, base_interval))
    
    async def _log_monitoring_cycle(self, loads_found: int, duration_ms: float) -> None:
        """Логирование цикла мониторинга"""
        try:
            stats = {
                'loads_found': loads_found,
                'loads_sent': 0,  # Будет обновлено позже
                'avg_scan_time_ms': duration_ms,
                'errors_count': self.error_count,
                'session_active': True,
                'memory_usage': 0,
                'cpu_usage': 0
            }
            
            # Получение системных ресурсов
            resources = await self.performance.track_system_resources()
            if resources:
                stats['memory_usage'] = resources.get('memory_usage', 0)
                stats['cpu_usage'] = resources.get('cpu_usage', 0)
            
            await self.db.log_monitoring_cycle(stats)
            
        except Exception as e:
            logger.error(f"❌ Ошибка логирования цикла мониторинга: {e}")
    
    async def _handle_scan_error(self, error: Exception, page: Page) -> None:
        """Обработка ошибок сканирования"""
        try:
            error_msg = str(error)
            
            # Логирование ошибки в БД
            await self.db.log_error(
                error_type=type(error).__name__,
                error_details=error_msg,
                stack_trace="",  # Можно добавить traceback
                context="load_monitoring"
            )
            
            # Создание скриншота при критических ошибках
            if self.config['monitoring']['screenshot_on_error']:
                screenshot_path = await self.parser.screenshot_on_error(
                    "monitoring_error", page
                )
                
                # Отправка уведомления об ошибке
                await self.telegram.send_error_alert(error_msg, screenshot_path)
            
        except Exception as e:
            logger.error(f"❌ Ошибка обработки ошибки сканирования: {e}")
    
    async def stop_monitoring(self) -> None:
        """Остановка мониторинга"""
        logger.info("🛑 Остановка мониторинга...")
        self.is_monitoring = False
    
    async def get_monitoring_stats(self) -> Dict:
        """Получение статистики мониторинга"""
        return {
            'is_monitoring': self.is_monitoring,
            'scan_count': self.scan_count,
            'loads_found_total': self.loads_found_total,
            'loads_sent_total': self.loads_sent_total,
            'error_count': self.error_count,
            'success_rate': self.success_rate,
            'current_scan_interval': self.current_scan_interval,
            'avg_response_time': self.avg_response_time,
            'uptime_hours': (time.time() - self.last_scan_time) / 3600 if self.last_scan_time else 0
        }
    
    async def websocket_monitoring(self, page: Page) -> None:
        """WebSocket мониторинг (если поддерживается)"""
        try:
            logger.info("🔌 Попытка WebSocket мониторинга...")
            
            # Здесь будет логика WebSocket подключения
            # Пока что просто логируем
            
            logger.warning("⚠️ WebSocket мониторинг не поддерживается, переключаемся на fast scan")
            
        except Exception as e:
            logger.error(f"❌ Ошибка WebSocket мониторинга: {e}")
    
    async def detect_page_changes(self, page: Page) -> bool:
        """Определение изменений на странице"""
        try:
            # Получение текущего содержимого страницы
            content = await page.content()
            
            # Простая проверка на изменения (можно улучшить)
            # Здесь должна быть логика сравнения с предыдущим состоянием
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка определения изменений страницы: {e}")
            return False
