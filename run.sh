#!/bin/bash
# Скрипт для запуска GeoVertical Analyzer на Linux/macOS

echo "===================================="
echo " GeoVertical Analyzer"
echo " Запуск приложения..."
echo "===================================="
echo

# Проверяем наличие виртуального окружения
if [ -f "venv/bin/activate" ]; then
    echo "Активируем виртуальное окружение..."
    source venv/bin/activate
fi

# Запускаем приложение
python main.py

# Если произошла ошибка
if [ $? -ne 0 ]; then
    echo
    echo "===================================="
    echo " ОШИБКА ЗАПУСКА!"
    echo "===================================="
    echo
    echo "Возможные причины:"
    echo "1. Не установлен Python"
    echo "2. Не установлены зависимости"
    echo
    echo "Попробуйте установить зависимости:"
    echo "  pip install -r requirements.txt"
    echo
    read -p "Нажмите Enter для выхода..."
fi

