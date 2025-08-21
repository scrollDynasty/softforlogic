#!/usr/bin/env python3
"""
Тест для проверки 2FA функционала
"""

import asyncio
import sys
import os
import json

# Добавление пути к модулям
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.utils.logger import logger
from src.auth.schneider_auth import SchneiderAuth

async def test_2fa():
    """Тест 2FA авторизации"""
    try:
        # Загрузка конфигурации
        with open('config/config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        # Загрузка переменных окружения
        from dotenv import load_dotenv
        load_dotenv("config/.env")
        
        schneider_email = os.getenv('SCHNEIDER_EMAIL')
        schneider_password = os.getenv('SCHNEIDER_PASSWORD')
        
        if schneider_email:
            config['schneider']['email'] = schneider_email
        if schneider_password:
            config['schneider']['password'] = schneider_password
        
        logger.info("🧪 Начинаем тест 2FA авторизации...")
        
        # Создание объекта авторизации
        auth = SchneiderAuth(config)
        
        try:
            # Инициализация браузера
            logger.info("🌐 Инициализация браузера...")
            if await auth.initialize_browser():
                logger.info("✅ Браузер инициализирован")
                
                # Попытка авторизации
                logger.info("🔐 Попытка авторизации с 2FA...")
                success = await auth.login()
                
                if success:
                    logger.info("🎉 Тест 2FA пройден успешно!")
                    
                    # Проверяем доступ к страницам грузов
                    logger.info("🚛 Проверка доступа к страницам грузов...")
                    try:
                        await auth.page.goto("https://freightpower.schneider.com/loads", 
                                           wait_until='networkidle', timeout=30000)
                        logger.info("✅ Доступ к страницам грузов получен!")
                    except Exception as e:
                        logger.error(f"❌ Ошибка доступа к страницам грузов: {e}")
                else:
                    logger.error("❌ Тест 2FA провален!")
                    
            else:
                logger.error("❌ Не удалось инициализировать браузер")
                
        finally:
            # Закрытие браузера
            if auth.browser:
                await auth.browser.close()
                logger.info("🔒 Браузер закрыт")
                
    except Exception as e:
        logger.error(f"❌ Критическая ошибка теста: {e}")

if __name__ == "__main__":
    asyncio.run(test_2fa())