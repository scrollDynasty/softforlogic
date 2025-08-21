#!/usr/bin/env python3
"""
Тестовый скрипт для проверки авторизации Schneider
"""

import asyncio
import sys
import os

# Добавление пути к модулям
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.utils.logger import logger
from src.auth.schneider_auth import SchneiderAuth
import json

async def test_authentication():
    """Тестирование авторизации"""
    try:
        logger.info("🧪 Запуск теста авторизации...")
        
        # Загрузка конфигурации
        with open('config/config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        # Загрузка переменных окружения
        from dotenv import load_dotenv
        load_dotenv("config/.env")
        
        # Обновление конфигурации из переменных окружения
        schneider_email = os.getenv('SCHNEIDER_EMAIL')
        schneider_password = os.getenv('SCHNEIDER_PASSWORD')
        
        if schneider_email:
            config['schneider']['email'] = schneider_email
        if schneider_password:
            config['schneider']['password'] = schneider_password
        
        # Создание экземпляра авторизации
        auth = SchneiderAuth(config)
        
        # Инициализация браузера
        logger.info("🌐 Инициализация браузера...")
        if not await auth.initialize_browser():
            logger.error("❌ Не удалось инициализировать браузер")
            return False
        
        logger.info("✅ Браузер инициализирован")
        
        # Попытка авторизации
        logger.info("🔐 Попытка авторизации...")
        if await auth.login():
            logger.info("✅ Авторизация прошла успешно!")
            
            # Проверка сессии
            if await auth.check_session():
                logger.info("✅ Сессия активна")
            else:
                logger.warning("⚠️ Сессия неактивна")
            
            success = True
        else:
            logger.error("❌ Авторизация не удалась")
            success = False
        
        # Закрытие браузера
        await auth.close()
        
        return success
        
    except Exception as e:
        logger.error(f"❌ Ошибка теста авторизации: {e}")
        return False

if __name__ == "__main__":
    result = asyncio.run(test_authentication())
    if result:
        print("🎉 Тест авторизации пройден успешно!")
        sys.exit(0)
    else:
        print("💥 Тест авторизации провален!")
        sys.exit(1)