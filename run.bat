@echo off
chcp 65001 >nul
REM Скрипт для запуска GeoVertical Analyzer на Windows

echo ====================================
echo  GeoVertical Analyzer
echo  Запуск приложения...
echo ====================================
echo.

REM Проверяем наличие виртуального окружения
if exist venv\Scripts\activate.bat (
    echo Активируем виртуальное окружение...
    call venv\Scripts\activate.bat
)

REM Запускаем приложение
python main.py

REM Если произошла ошибка
if %errorlevel% neq 0 (
    echo.
    echo ====================================
    echo  ОШИБКА ЗАПУСКА!
    echo ====================================
    echo.
    echo Возможные причины:
    echo 1. Не установлен Python
    echo 2. Не установлены зависимости
    echo.
    echo Попробуйте установить зависимости:
    echo   pip install -r requirements.txt
    echo.
    pause
)

