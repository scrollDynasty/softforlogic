import sqlite3
import asyncio
import os
import json
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import asdict
import aiosqlite

from ..utils.logger import logger

class DatabaseManager:
    def __init__(self, db_path: str = "data/loads.db"):
        self.db_path = db_path
        self._ensure_data_directory()
        
    def _ensure_data_directory(self):
        """Создание директории для базы данных"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
    
    async def init_database(self) -> bool:
        """Создание всех необходимых таблиц"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # Таблица отправленных грузов
                await db.execute('''
                    CREATE TABLE IF NOT EXISTS sent_loads (
                        load_id TEXT PRIMARY KEY,
                        load_hash TEXT UNIQUE,
                        sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        pickup_location TEXT,
                        delivery_location TEXT,
                        rate REAL,
                        miles INTEGER,
                        deadhead INTEGER,
                        profitability_score REAL,
                        equipment_type TEXT,
                        pickup_date TEXT,
                        status TEXT DEFAULT 'sent',
                        priority TEXT DEFAULT 'MEDIUM'
                    )
                ''')
                
                # Таблица статистики мониторинга
                await db.execute('''
                    CREATE TABLE IF NOT EXISTS monitoring_stats (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        loads_found INTEGER DEFAULT 0,
                        loads_sent INTEGER DEFAULT 0,
                        avg_scan_time_ms INTEGER DEFAULT 0,
                        errors_count INTEGER DEFAULT 0,
                        session_active BOOLEAN DEFAULT 1,
                        memory_usage REAL DEFAULT 0,
                        cpu_usage REAL DEFAULT 0
                    )
                ''')
                
                # Таблица логов ошибок
                await db.execute('''
                    CREATE TABLE IF NOT EXISTS error_log (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        error_type TEXT,
                        error_message TEXT,
                        stack_trace TEXT,
                        screenshot_path TEXT,
                        context TEXT
                    )
                ''')
                
                # Таблица производительности
                await db.execute('''
                    CREATE TABLE IF NOT EXISTS performance_log (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        operation TEXT,
                        duration_ms REAL,
                        success BOOLEAN,
                        details TEXT
                    )
                ''')
                
                # Индексы для ускорения запросов
                await db.execute('CREATE INDEX IF NOT EXISTS idx_sent_loads_timestamp ON sent_loads(sent_at)')
                await db.execute('CREATE INDEX IF NOT EXISTS idx_sent_loads_hash ON sent_loads(load_hash)')
                await db.execute('CREATE INDEX IF NOT EXISTS idx_monitoring_stats_timestamp ON monitoring_stats(timestamp)')
                await db.execute('CREATE INDEX IF NOT EXISTS idx_error_log_timestamp ON error_log(timestamp)')
                
                await db.commit()
                logger.info("✅ База данных инициализирована успешно")
                return True
                
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации БД: {e}")
            return False
    
    async def is_load_new(self, load_id: str, load_hash: str) -> bool:
        """Проверка, является ли груз новым"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute(
                    'SELECT 1 FROM sent_loads WHERE load_id = ? OR load_hash = ?',
                    (load_id, load_hash)
                )
                result = await cursor.fetchone()
                return result is None
                
        except Exception as e:
            logger.error(f"❌ Ошибка проверки нового груза: {e}")
            return True  # В случае ошибки считаем груз новым
    
    async def mark_as_sent(self, load_data: dict, analysis: dict) -> bool:
        """Отметка груза как отправленного"""
        try:
            load_hash = self.generate_load_hash(load_data)
            
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute('''
                    INSERT INTO sent_loads (
                        load_id, load_hash, pickup_location, delivery_location,
                        rate, miles, deadhead, profitability_score, equipment_type,
                        pickup_date, priority
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    load_data.get('id'),
                    load_hash,
                    load_data.get('pickup'),
                    load_data.get('delivery'),
                    load_data.get('rate'),
                    load_data.get('miles'),
                    load_data.get('deadhead'),
                    analysis.get('profitability_score', 0),
                    load_data.get('equipment'),
                    load_data.get('pickup_date'),
                    analysis.get('priority', 'MEDIUM')
                ))
                
                await db.commit()
                logger.debug(f"✅ Груз {load_data.get('id')} отмечен как отправленный")
                return True
                
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения груза в БД: {e}")
            return False
    
    def generate_load_hash(self, load_data: dict) -> str:
        """Генерация хеша груза для предотвращения дубликатов"""
        # Создаем строку из ключевых полей
        key_fields = [
            str(load_data.get('id', '')),
            str(load_data.get('pickup', '')),
            str(load_data.get('delivery', '')),
            str(load_data.get('rate', '')),
            str(load_data.get('miles', '')),
            str(load_data.get('deadhead', ''))
        ]
        
        hash_string = '|'.join(key_fields)
        return hashlib.md5(hash_string.encode()).hexdigest()
    
    async def cleanup_old_records(self, days: int = 7) -> int:
        """Очистка старых записей"""
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            
            async with aiosqlite.connect(self.db_path) as db:
                # Очистка старых отправленных грузов
                cursor = await db.execute(
                    'DELETE FROM sent_loads WHERE sent_at < ?',
                    (cutoff_date.isoformat(),)
                )
                loads_deleted = cursor.rowcount
                
                # Очистка старых логов ошибок
                cursor = await db.execute(
                    'DELETE FROM error_log WHERE timestamp < ?',
                    (cutoff_date.isoformat(),)
                )
                errors_deleted = cursor.rowcount
                
                # Очистка старых записей производительности
                cursor = await db.execute(
                    'DELETE FROM performance_log WHERE timestamp < ?',
                    (cutoff_date.isoformat(),)
                )
                perf_deleted = cursor.rowcount
                
                await db.commit()
                
                total_deleted = loads_deleted + errors_deleted + perf_deleted
                logger.info(f"🧹 Очищено {total_deleted} старых записей")
                return total_deleted
                
        except Exception as e:
            logger.error(f"❌ Ошибка очистки БД: {e}")
            return 0
    
    async def get_daily_stats(self) -> dict:
        """Получение статистики за день"""
        try:
            today = datetime.now().date()
            start_date = datetime.combine(today, datetime.min.time())
            end_date = datetime.combine(today, datetime.max.time())
            
            async with aiosqlite.connect(self.db_path) as db:
                # Статистика отправленных грузов
                cursor = await db.execute('''
                    SELECT COUNT(*) as total_sent,
                           AVG(profitability_score) as avg_profitability,
                           AVG(rate) as avg_rate,
                           SUM(miles) as total_miles
                    FROM sent_loads 
                    WHERE sent_at BETWEEN ? AND ?
                ''', (start_date.isoformat(), end_date.isoformat()))
                
                loads_stats = await cursor.fetchone()
                
                # Статистика мониторинга
                cursor = await db.execute('''
                    SELECT SUM(loads_found) as total_found,
                           SUM(loads_sent) as total_sent_monitoring,
                           AVG(avg_scan_time_ms) as avg_scan_time,
                           SUM(errors_count) as total_errors
                    FROM monitoring_stats 
                    WHERE timestamp BETWEEN ? AND ?
                ''', (start_date.isoformat(), end_date.isoformat()))
                
                monitoring_stats = await cursor.fetchone()
                
                # Статистика ошибок
                cursor = await db.execute('''
                    SELECT COUNT(*) as total_errors,
                           COUNT(DISTINCT error_type) as unique_error_types
                    FROM error_log 
                    WHERE timestamp BETWEEN ? AND ?
                ''', (start_date.isoformat(), end_date.isoformat()))
                
                error_stats = await cursor.fetchone()
                
                return {
                    'date': today.isoformat(),
                    'loads_sent': loads_stats[0] if loads_stats else 0,
                    'avg_profitability': loads_stats[1] if loads_stats else 0,
                    'avg_rate': loads_stats[2] if loads_stats else 0,
                    'total_miles': loads_stats[3] if loads_stats else 0,
                    'loads_found': monitoring_stats[0] if monitoring_stats else 0,
                    'avg_scan_time_ms': monitoring_stats[2] if monitoring_stats else 0,
                    'total_errors': error_stats[0] if error_stats else 0,
                    'unique_error_types': error_stats[1] if error_stats else 0
                }
                
        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики: {e}")
            return {}
    
    async def log_monitoring_cycle(self, stats: dict) -> bool:
        """Логирование цикла мониторинга"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute('''
                    INSERT INTO monitoring_stats (
                        loads_found, loads_sent, avg_scan_time_ms,
                        errors_count, session_active, memory_usage, cpu_usage
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    stats.get('loads_found', 0),
                    stats.get('loads_sent', 0),
                    stats.get('avg_scan_time_ms', 0),
                    stats.get('errors_count', 0),
                    stats.get('session_active', True),
                    stats.get('memory_usage', 0),
                    stats.get('cpu_usage', 0)
                ))
                
                await db.commit()
                return True
                
        except Exception as e:
            logger.error(f"❌ Ошибка логирования мониторинга: {e}")
            return False
    
    async def log_error(self, error_type: str, error_msg: str, 
                       stack_trace: str = "", screenshot_path: str = "", 
                       context: str = "") -> bool:
        """Логирование ошибки"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute('''
                    INSERT INTO error_log (
                        error_type, error_message, stack_trace, 
                        screenshot_path, context
                    ) VALUES (?, ?, ?, ?, ?)
                ''', (error_type, error_msg, stack_trace, screenshot_path, context))
                
                await db.commit()
                return True
                
        except Exception as e:
            logger.error(f"❌ Ошибка логирования ошибки: {e}")
            return False
    
    async def log_performance(self, operation: str, duration_ms: float, 
                            success: bool = True, details: str = "") -> bool:
        """Логирование производительности"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute('''
                    INSERT INTO performance_log (
                        operation, duration_ms, success, details
                    ) VALUES (?, ?, ?, ?)
                ''', (operation, duration_ms, success, details))
                
                await db.commit()
                return True
                
        except Exception as e:
            logger.error(f"❌ Ошибка логирования производительности: {e}")
            return False
    
    async def get_performance_report(self, hours: int = 24) -> dict:
        """Получение отчета о производительности"""
        try:
            cutoff_time = datetime.now() - timedelta(hours=hours)
            
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute('''
                    SELECT operation,
                           COUNT(*) as count,
                           AVG(duration_ms) as avg_duration,
                           MIN(duration_ms) as min_duration,
                           MAX(duration_ms) as max_duration,
                           SUM(CASE WHEN success THEN 1 ELSE 0 END) as success_count
                    FROM performance_log 
                    WHERE timestamp > ?
                    GROUP BY operation
                    ORDER BY avg_duration DESC
                ''', (cutoff_time.isoformat(),))
                
                results = await cursor.fetchall()
                
                report = {
                    'period_hours': hours,
                    'operations': []
                }
                
                for row in results:
                    operation, count, avg_dur, min_dur, max_dur, success_count = row
                    success_rate = (success_count / count) * 100 if count > 0 else 0
                    
                    report['operations'].append({
                        'operation': operation,
                        'count': count,
                        'avg_duration_ms': avg_dur,
                        'min_duration_ms': min_dur,
                        'max_duration_ms': max_dur,
                        'success_rate_percent': success_rate
                    })
                
                return report
                
        except Exception as e:
            logger.error(f"❌ Ошибка получения отчета производительности: {e}")
            return {}
    
    async def get_db_size_mb(self) -> float:
        """Получение размера базы данных в МБ"""
        try:
            if os.path.exists(self.db_path):
                size_bytes = os.path.getsize(self.db_path)
                return size_bytes / (1024 * 1024)
            return 0
        except Exception as e:
            logger.error(f"❌ Ошибка получения размера БД: {e}")
            return 0
    
    async def backup_database(self, backup_path: str = None) -> bool:
        """Создание резервной копии базы данных"""
        try:
            if backup_path is None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_path = f"data/backup_loads_{timestamp}.db"
            
            os.makedirs(os.path.dirname(backup_path), exist_ok=True)
            
            # Копирование файла БД
            import shutil
            shutil.copy2(self.db_path, backup_path)
            
            logger.info(f"✅ Резервная копия создана: {backup_path}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания резервной копии: {e}")
            return False
