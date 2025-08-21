import logging
import colorlog
import os
from datetime import datetime
from logging.handlers import RotatingFileHandler
import json

class Logger:
    def __init__(self, name="schneider_parser", log_level="INFO"):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(getattr(logging, log_level.upper()))
        
        # Очистка существующих обработчиков
        self.logger.handlers.clear()
        
        # Создание папки для логов
        os.makedirs("logs", exist_ok=True)
        
        # Настройка цветного вывода в консоль
        self._setup_console_handler()
        
        # Настройка файлового логгера
        self._setup_file_handler()
        
    def _setup_console_handler(self):
        """Настройка цветного вывода в консоль"""
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        
        # Цветная схема для консоли
        color_formatter = colorlog.ColoredFormatter(
            "%(log_color)s%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%H:%M:%S",
            log_colors={
                'DEBUG': 'cyan',
                'INFO': 'green',
                'WARNING': 'yellow',
                'ERROR': 'red',
                'CRITICAL': 'red,bg_white',
            }
        )
        
        console_handler.setFormatter(color_formatter)
        self.logger.addHandler(console_handler)
    
    def _setup_file_handler(self):
        """Настройка ротации файлов логов"""
        file_handler = RotatingFileHandler(
            f"logs/schneider_parser_{datetime.now().strftime('%Y%m%d')}.log",
            maxBytes=10*1024*1024,  # 10MB
            backupCount=10
        )
        file_handler.setLevel(logging.DEBUG)
        
        # Форматтер для файла
        file_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        
        file_handler.setFormatter(file_formatter)
        self.logger.addHandler(file_handler)
    
    def info(self, message):
        self.logger.info(message)
    
    def warning(self, message):
        self.logger.warning(message)
    
    def error(self, message):
        self.logger.error(message)
    
    def debug(self, message):
        self.logger.debug(message)
    
    def critical(self, message):
        self.logger.critical(message)
    
    def log_performance(self, operation: str, duration_ms: float, success: bool = True):
        """Логирование производительности операций"""
        status = "✅" if success else "❌"
        self.info(f"{status} {operation}: {duration_ms:.2f}ms")
    
    def log_load_found(self, load_id: str, rate_per_mile: float, profitability_score: float):
        """Логирование найденного груза"""
        emoji = "🟢" if profitability_score > 2.0 else "🟡"
        self.info(f"{emoji} Load {load_id}: ${rate_per_mile:.2f}/mile (Score: {profitability_score:.2f})")
    
    def log_error_with_context(self, error: Exception, context: str = ""):
        """Логирование ошибок с контекстом"""
        error_msg = f"❌ ERROR in {context}: {str(error)}"
        self.error(error_msg)
        if hasattr(error, '__traceback__'):
            import traceback
            self.debug(f"Traceback: {traceback.format_exc()}")

# Глобальный экземпляр логгера
logger = Logger()
