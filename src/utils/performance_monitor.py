import time
import psutil
import asyncio
from typing import Dict, List, Optional
from collections import deque
from datetime import datetime, timedelta

from .logger import logger

class PerformanceMonitor:
    def __init__(self, max_history: int = 1000):
        self.scan_times = deque(maxlen=max_history)
        self.memory_usage = deque(maxlen=max_history)
        self.cpu_usage = deque(maxlen=max_history)
        self.error_counts = deque(maxlen=max_history)
        self.start_time = time.time()
        self.last_optimization_time = 0
        
    async def track_scan_performance(self, scan_time_ms: float) -> None:
        """Отслеживание производительности сканирования"""
        self.scan_times.append(scan_time_ms)
        
        # Логирование производительности
        if scan_time_ms > 10000:  # Медленное сканирование
            logger.warning(f"🐌 Медленное сканирование: {scan_time_ms:.0f}ms")
        elif scan_time_ms < 1000:  # Быстрое сканирование
            logger.debug(f"⚡ Быстрое сканирование: {scan_time_ms:.0f}ms")
    
    async def track_system_resources(self) -> Dict:
        """Отслеживание системных ресурсов"""
        try:
            # CPU использование
            cpu_percent = psutil.cpu_percent(interval=0.1)
            self.cpu_usage.append(cpu_percent)
            
            # Память
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            self.memory_usage.append(memory_percent)
            
            # Диск
            disk_usage = psutil.disk_usage('/').percent
            
            # Сеть
            network_io = psutil.net_io_counters()
            
            resources = {
                'cpu_usage': cpu_percent,
                'memory_usage': memory_percent,
                'memory_available_mb': memory.available / (1024 * 1024),
                'disk_usage': disk_usage,
                'network_bytes_sent': network_io.bytes_sent,
                'network_bytes_recv': network_io.bytes_recv,
                'uptime_seconds': time.time() - self.start_time
            }
            
            # Логирование критических значений
            if cpu_percent > 80:
                logger.warning(f"🔥 Высокое использование CPU: {cpu_percent:.1f}%")
            if memory_percent > 85:
                logger.warning(f"🔥 Высокое использование памяти: {memory_percent:.1f}%")
            if disk_usage > 90:
                logger.warning(f"🔥 Высокое использование диска: {disk_usage:.1f}%")
            
            return resources
            
        except Exception as e:
            logger.error(f"❌ Ошибка отслеживания ресурсов: {e}")
            return {}
    
    async def get_performance_report(self) -> Dict:
        """Получение отчета о производительности"""
        try:
            # Статистика сканирования
            if self.scan_times:
                avg_scan_time = sum(self.scan_times) / len(self.scan_times)
                min_scan_time = min(self.scan_times)
                max_scan_time = max(self.scan_times)
                recent_avg = sum(list(self.scan_times)[-10:]) / min(10, len(self.scan_times))
            else:
                avg_scan_time = min_scan_time = max_scan_time = recent_avg = 0
            
            # Статистика ресурсов
            if self.cpu_usage:
                avg_cpu = sum(self.cpu_usage) / len(self.cpu_usage)
                max_cpu = max(self.cpu_usage)
            else:
                avg_cpu = max_cpu = 0
                
            if self.memory_usage:
                avg_memory = sum(self.memory_usage) / len(self.memory_usage)
                max_memory = max(self.memory_usage)
            else:
                avg_memory = max_memory = 0
            
            # Время работы
            uptime = time.time() - self.start_time
            uptime_hours = uptime / 3600
            
            # Оценка производительности
            performance_score = self._calculate_performance_score(
                avg_scan_time, avg_cpu, avg_memory
            )
            
            return {
                'scan_performance': {
                    'avg_scan_time_ms': avg_scan_time,
                    'min_scan_time_ms': min_scan_time,
                    'max_scan_time_ms': max_scan_time,
                    'recent_avg_ms': recent_avg,
                    'total_scans': len(self.scan_times)
                },
                'system_resources': {
                    'avg_cpu_percent': avg_cpu,
                    'max_cpu_percent': max_cpu,
                    'avg_memory_percent': avg_memory,
                    'max_memory_percent': max_memory
                },
                'uptime': {
                    'seconds': uptime,
                    'hours': uptime_hours,
                    'formatted': f"{int(uptime_hours)}h {int((uptime % 3600) / 60)}m"
                },
                'performance_score': performance_score,
                'recommendations': self._get_performance_recommendations(
                    avg_scan_time, avg_cpu, avg_memory
                )
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения отчета производительности: {e}")
            return {}
    
    def _calculate_performance_score(self, avg_scan_time: float, avg_cpu: float, avg_memory: float) -> float:
        """Расчет оценки производительности (0-100)"""
        score = 100
        
        # Штраф за медленное сканирование
        if avg_scan_time > 10000:
            score -= 30
        elif avg_scan_time > 5000:
            score -= 15
        elif avg_scan_time > 2000:
            score -= 5
        
        # Штраф за высокое использование CPU
        if avg_cpu > 80:
            score -= 25
        elif avg_cpu > 60:
            score -= 10
        elif avg_cpu > 40:
            score -= 5
        
        # Штраф за высокое использование памяти
        if avg_memory > 85:
            score -= 25
        elif avg_memory > 70:
            score -= 10
        elif avg_memory > 50:
            score -= 5
        
        return max(0, score)
    
    def _get_performance_recommendations(self, avg_scan_time: float, avg_cpu: float, avg_memory: float) -> List[str]:
        """Получение рекомендаций по оптимизации"""
        recommendations = []
        
        if avg_scan_time > 10000:
            recommendations.append("🔧 Увеличить интервал сканирования")
            recommendations.append("🔧 Оптимизировать селекторы")
            recommendations.append("🔧 Уменьшить количество параллельных запросов")
        
        if avg_cpu > 80:
            recommendations.append("🔥 Снизить нагрузку на CPU")
            recommendations.append("🔥 Увеличить интервалы между операциями")
        
        if avg_memory > 85:
            recommendations.append("💾 Очистить кеш и временные файлы")
            recommendations.append("💾 Перезапустить браузер")
        
        if not recommendations:
            recommendations.append("✅ Производительность в норме")
        
        return recommendations
    
    async def should_scale_down(self) -> bool:
        """Определяет, нужно ли снизить интенсивность сканирования"""
        try:
            cpu_usage = psutil.cpu_percent(interval=0.1)
            memory_usage = psutil.virtual_memory().percent
            
            # Проверяем последние значения сканирования
            if self.scan_times:
                recent_avg = sum(list(self.scan_times)[-5:]) / min(5, len(self.scan_times))
                if recent_avg > 15000:  # Очень медленное сканирование
                    return True
            
            return cpu_usage > 80 or memory_usage > 85
            
        except Exception as e:
            logger.error(f"❌ Ошибка проверки масштабирования: {e}")
            return False
    
    async def optimize_browser_settings(self, page) -> None:
        """Оптимизация настроек браузера для максимальной скорости"""
        try:
            # Отключение всех ненужных ресурсов
            await page.route('**/*.{png,jpg,jpeg,gif,css,woff,woff2,svg,ico}', 
                            lambda route: route.abort())
            await page.route('**/analytics/**', lambda route: route.abort())
            await page.route('**/tracking/**', lambda route: route.abort())
            await page.route('**/ads/**', lambda route: route.abort())
            await page.route('**/facebook.com/**', lambda route: route.abort())
            await page.route('**/google-analytics.com/**', lambda route: route.abort())
            
            # Отключение JavaScript для ненужных скриптов
            await page.add_init_script("""
                // Отключение ненужных функций
                window.console.log = () => {};
                window.console.warn = () => {};
                window.console.error = () => {};
                
                // Отключение анимаций
                const style = document.createElement('style');
                style.textContent = '* { animation: none !important; transition: none !important; }';
                document.head.appendChild(style);
            """)
            
            logger.info("✅ Настройки браузера оптимизированы")
            
        except Exception as e:
            logger.error(f"❌ Ошибка оптимизации браузера: {e}")
    
    async def get_memory_usage_mb(self) -> float:
        """Получение использования памяти в МБ"""
        try:
            process = psutil.Process()
            memory_info = process.memory_info()
            return memory_info.rss / (1024 * 1024)  # Конвертация в МБ
        except Exception as e:
            logger.error(f"❌ Ошибка получения использования памяти: {e}")
            return 0
    
    async def cleanup_memory(self) -> bool:
        """Очистка памяти"""
        try:
            # Принудительная сборка мусора
            import gc
            gc.collect()
            
            # Очистка кеша браузера (если возможно)
            # Это может быть реализовано в основном коде
            
            logger.info("🧹 Память очищена")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка очистки памяти: {e}")
            return False
    
    async def log_performance_metrics(self, operation: str, duration_ms: float, 
                                    success: bool = True, details: str = "") -> None:
        """Логирование метрик производительности"""
        try:
            # Добавляем метрики в соответствующие очереди
            if operation == "scan":
                self.scan_times.append(duration_ms)
            
            # Логирование в файл
            logger.log_performance(operation, duration_ms, success)
            
            # Проверка на аномалии
            if duration_ms > 30000:  # Очень медленная операция
                logger.warning(f"🐌 Аномально медленная операция {operation}: {duration_ms:.0f}ms")
                
        except Exception as e:
            logger.error(f"❌ Ошибка логирования метрик: {e}")
    
    async def get_system_info(self) -> Dict:
        """Получение информации о системе"""
        try:
            return {
                'platform': psutil.sys.platform,
                'cpu_count': psutil.cpu_count(),
                'cpu_freq': psutil.cpu_freq()._asdict() if psutil.cpu_freq() else {},
                'memory_total_gb': psutil.virtual_memory().total / (1024**3),
                'disk_total_gb': psutil.disk_usage('/').total / (1024**3),
                'python_version': f"{psutil.sys.version_info.major}.{psutil.sys.version_info.minor}.{psutil.sys.version_info.micro}"
            }
        except Exception as e:
            logger.error(f"❌ Ошибка получения информации о системе: {e}")
            return {}
