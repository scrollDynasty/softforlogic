#!/bin/bash

# Отключаем AI Navigator и запускаем систему
export DISABLE_AI_NAVIGATOR=true

echo "🚀 Запуск системы без AI Navigator..."
echo "⚠️  AI Navigator отключен для ускорения работы"
echo ""

# Активируем виртуальное окружение если оно есть
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Запускаем main.py
python3.12 main.py