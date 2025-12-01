@echo off
chcp 65001 >nul
echo ╔════════════════════════════════════════════╗
echo ║   GeoVertical Analyzer - Установщик       ║
echo ║   Быстрая установка (без Shapefile)       ║
echo ╚════════════════════════════════════════════╝
echo.

REM Проверка Python
echo [1/5] Проверка Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Python не найден!
    echo.
    echo Установите Python 3.8+ с: https://www.python.org/downloads/
    echo Отметьте "Add Python to PATH" при установке!
    pause
    exit /b 1
)
python --version
echo ✓ Python найден
echo.

REM Проверка версии
echo [2/5] Проверка версии Python...
python -c "import sys; exit(0 if sys.version_info >= (3, 8) else 1)"
if %errorlevel% neq 0 (
    echo ❌ Требуется Python 3.8+
    pause
    exit /b 1
)
echo ✓ Версия подходит
echo.

REM Создание venv
echo [3/5] Создание виртуального окружения...
if exist venv (
    echo Удаление старого окружения...
    rmdir /s /q venv
)
python -m venv venv
if %errorlevel% neq 0 (
    echo ❌ Ошибка создания venv
    pause
    exit /b 1
)
echo ✓ venv создан
echo.

REM Активация
echo [4/5] Активация venv...
call venv\Scripts\activate.bat
echo ✓ venv активирован
echo.

REM Установка зависимостей
echo [5/5] Установка зависимостей...
echo Это займёт 2-5 минут...
echo.

python -m pip install --upgrade pip setuptools wheel --quiet

echo → Устанавливаем минимальный набор...
pip install -r requirements-minimal.txt

echo → Устанавливаем 3D редактор (PyQtGraph + PyOpenGL)...
pip install pyqtgraph>=0.13.0 PyOpenGL>=3.1.5 --quiet

if %errorlevel% neq 0 (
    echo ❌ Ошибка установки зависимостей
    echo.
    echo Попробуйте установить вручную:
    echo   1. venv\Scripts\activate
    echo   2. pip install -r requirements-minimal.txt
    pause
    exit /b 1
)

echo.
echo ✓ Все зависимости установлены!
echo.

REM Проверка
echo ════════════════════════════════════════════
echo Проверка компонентов:
echo ════════════════════════════════════════════
python -c "import PyQt6; print('✓ PyQt6')" 2>nul || echo ❌ PyQt6
python -c "import pyqtgraph; print('✓ PyQtGraph')" 2>nul || echo ❌ PyQtGraph
python -c "import OpenGL; print('✓ PyOpenGL')" 2>nul || echo ❌ PyOpenGL
python -c "import numpy; print('✓ NumPy')" 2>nul || echo ❌ NumPy
python -c "import pandas; print('✓ pandas')" 2>nul || echo ❌ pandas
python -c "import matplotlib; print('✓ matplotlib')" 2>nul || echo ❌ matplotlib
python -c "import ezdxf; print('✓ ezdxf')" 2>nul || echo ❌ ezdxf
python -c "import plotly; print('✓ plotly')" 2>nul || echo ❌ plotly
python -c "import sklearn; print('✓ scikit-learn')" 2>nul || echo ❌ scikit-learn
python -c "import pytest; print('✓ pytest')" 2>nul || echo ❌ pytest

echo.
echo ════════════════════════════════════════════
echo ✅ УСТАНОВКА ЗАВЕРШЕНА!
echo ════════════════════════════════════════════
echo.
echo Поддерживаемые форматы:
echo   ✓ CSV/TXT
echo   ✓ DXF
echo   ✓ Trimble (JXL, JOB)
echo   ✓ GeoJSON (через встроенную поддержку)
echo.
echo Для запуска:
echo   run.bat
echo.
echo или:
echo   venv\Scripts\activate
echo   python main.py
echo.

choice /C YN /M "Запустить программу сейчас?"
if errorlevel 2 goto end
if errorlevel 1 (
    echo.
    python main.py
)

:end
pause
