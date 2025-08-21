#!/usr/bin/env python3
"""
Стартовый скрипт для Schneider FreightPower Load Parser
с предварительной проверкой системы
"""

import asyncio
import sys
import os
from datetime import datetime

# Добавление пути к модулям
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from main import SchneiderParser
from src.utils.logger import logger

def print_banner():
    """Вывод баннера приложения"""
    banner = """
╔══════════════════════════════════════════════════════════════╗
║                🚛 SCHNEIDER FREIGHTPOWER PARSER             ║
║                                                              ║
║  Высокопроизводительный автоматический парсер грузов        ║
║  с системой восстановления и адаптивным мониторингом        ║
╚══════════════════════════════════════════════════════════════╝
    """
    print(banner)
    print(f"🕐 Время запуска: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 66)

async def pre_flight_check():
    """Предварительная проверка системы"""
    print("\n🔍 ПРЕДВАРИТЕЛЬНАЯ ПРОВЕРКА СИСТЕМЫ")
    print("-" * 40)
    
    checks = []
    
    # Проверка Python версии
    python_version = sys.version_info
    if python_version >= (3, 8):
        print(f"✅ Python версия: {python_version.major}.{python_version.minor}.{python_version.micro}")
        checks.append(True)
    else:
        print(f"❌ Python версия слишком старая: {python_version.major}.{python_version.minor}.{python_version.micro}")
        checks.append(False)
    
    # Проверка наличия конфигурационных файлов
    config_files = ['config/config.json', 'config/.env']
    for file_path in config_files:
        if os.path.exists(file_path):
            print(f"✅ Конфигурационный файл найден: {file_path}")
            checks.append(True)
        else:
            print(f"❌ Конфигурационный файл не найден: {file_path}")
            checks.append(False)
    
    # Проверка зависимостей
    required_packages = ['playwright', 'aiohttp', 'python-dotenv']
    for package in required_packages:
        try:
            __import__(package.replace('-', '_'))
            print(f"✅ Пакет установлен: {package}")
            checks.append(True)
        except ImportError:
            print(f"❌ Пакет не установлен: {package}")
            checks.append(False)
    
    # Проверка директорий
    required_dirs = ['data', 'logs', 'screenshots', 'backups']
    for dir_name in required_dirs:
        if os.path.exists(dir_name):
            print(f"✅ Директория существует: {dir_name}")
        else:
            os.makedirs(dir_name, exist_ok=True)
            print(f"📁 Директория создана: {dir_name}")
        checks.append(True)
    
    success_rate = sum(checks) / len(checks)
    print(f"\n📊 Результат проверки: {success_rate:.1%} ({sum(checks)}/{len(checks)})")
    
    if success_rate < 0.8:
        print("❌ Критические ошибки обнаружены. Запуск невозможен.")
        return False
    elif success_rate < 1.0:
        print("⚠️ Некоторые проверки не прошли, но запуск возможен.")
    else:
        print("✅ Все проверки пройдены успешно!")
    
    return True

async def run_with_recovery():
    """Запуск приложения с системой восстановления"""
    max_restarts = 3
    restart_count = 0
    
    while restart_count < max_restarts:
        try:
            print(f"\n🚀 ЗАПУСК ПРИЛОЖЕНИЯ (попытка {restart_count + 1}/{max_restarts})")
            print("-" * 50)
            
            # Создание экземпляра парсера
            parser = SchneiderParser()
            
            # Запуск основного приложения
            await parser.main()
            
            # Если дошли до этой точки без исключений, выходим
            break
            
        except KeyboardInterrupt:
            print("\n🛑 Получен сигнал остановки от пользователя")
            break
            
        except Exception as e:
            restart_count += 1
            error_msg = str(e)
            
            print(f"\n💥 КРИТИЧЕСКАЯ ОШИБКА (попытка {restart_count}/{max_restarts})")
            print(f"❌ Ошибка: {error_msg}")
            
            if restart_count < max_restarts:
                restart_delay = 30 * restart_count
                print(f"🔄 Автоматический перезапуск через {restart_delay} секунд...")
                await asyncio.sleep(restart_delay)
            else:
                print("🆘 Достигнуто максимальное количество перезапусков")
                print("💡 Рекомендуется проверить логи и конфигурацию")
                return False
    
    return True

async def main():
    """Главная функция стартового скрипта"""
    try:
        print_banner()
        
        # Предварительная проверка
        if not await pre_flight_check():
            print("\n❌ Предварительная проверка не пройдена. Выход.")
            sys.exit(1)
        
        # Запуск с восстановлением
        success = await run_with_recovery()
        
        if success:
            print("\n✅ Приложение завершило работу успешно")
            sys.exit(0)
        else:
            print("\n❌ Приложение завершило работу с ошибками")
            sys.exit(1)
            
    except Exception as e:
        print(f"\n💥 КРИТИЧЕСКАЯ ОШИБКА СТАРТОВОГО СКРИПТА: {e}")
        sys.exit(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Принудительная остановка")
        sys.exit(0)