#!/bin/bash
# ============================================
# GeoVertical Analyzer - Установщик для Linux/macOS
# ============================================

set -e  # Остановка при ошибке

echo ""
echo "╔════════════════════════════════════════════╗"
echo "║   GeoVertical Analyzer - Установщик       ║"
echo "║   Версия 1.2.0                             ║"
echo "╚════════════════════════════════════════════╝"
echo ""

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Проверка Python
echo "[1/6] Проверка наличия Python..."
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ ОШИБКА: Python 3 не найден!${NC}"
    echo ""
    echo "Установите Python 3.8 или выше:"
    echo "  Ubuntu/Debian: sudo apt-get install python3 python3-pip python3-venv"
    echo "  Fedora/RHEL:   sudo dnf install python3 python3-pip"
    echo "  macOS:         brew install python3"
    echo ""
    exit 1
fi

python3 --version
echo -e "${GREEN}✓ Python найден${NC}"
echo ""

# Проверка версии Python
echo "[2/6] Проверка версии Python..."
python3 -c "import sys; exit(0 if sys.version_info >= (3, 8) else 1)" || {
    echo -e "${RED}❌ ОШИБКА: Требуется Python 3.8 или выше!${NC}"
    echo "Текущая версия слишком старая."
    exit 1
}
echo -e "${GREEN}✓ Версия Python подходит${NC}"
echo ""

# Обновление pip
echo "[3/6] Обновление pip..."
python3 -m pip install --upgrade pip --quiet || {
    echo -e "${RED}❌ Не удалось обновить pip${NC}"
    exit 1
}
echo -e "${GREEN}✓ pip обновлен${NC}"
echo ""

# Создание виртуального окружения
echo "[4/6] Создание виртуального окружения..."
if [ -d "venv" ]; then
    echo -e "${YELLOW}Виртуальное окружение уже существует${NC}"
    read -p "Пересоздать виртуальное окружение? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Удаление старого окружения..."
        rm -rf venv
        python3 -m venv venv
    fi
else
    python3 -m venv venv
fi

if [ ! -d "venv" ]; then
    echo -e "${RED}❌ Не удалось создать виртуальное окружение${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Виртуальное окружение создано${NC}"
echo ""

# Активация виртуального окружения
echo "Активация виртуального окружения..."
source venv/bin/activate
echo -e "${GREEN}✓ Виртуальное окружение активировано${NC}"
echo ""

# Установка базовых зависимостей
echo "[5/6] Установка базовых зависимостей..."
echo "Это может занять несколько минут..."
echo ""

echo "→ Установка PyQt6 (графический интерфейс)..."
pip install 'PyQt6>=6.7.0' --quiet
echo -e "${GREEN}✓ PyQt6 установлен${NC}"

echo "→ Установка PyQt6-WebEngine (веб-компоненты)..."
pip install 'PyQt6-WebEngine>=6.7.0' --quiet
echo -e "${GREEN}✓ PyQt6-WebEngine установлен${NC}"

echo "→ Установка NumPy (вычисления)..."
pip install 'numpy>=1.21.0' --quiet
echo -e "${GREEN}✓ NumPy установлен${NC}"

echo "→ Установка SciPy (статистика)..."
pip install 'scipy>=1.7.0' --quiet
echo -e "${GREEN}✓ SciPy установлен${NC}"

echo "→ Установка matplotlib (графики)..."
pip install 'matplotlib>=3.5.0' --quiet
echo -e "${GREEN}✓ matplotlib установлен${NC}"

echo "→ Установка pandas (данные)..."
pip install 'pandas>=1.3.0' --quiet
echo -e "${GREEN}✓ pandas установлен${NC}"

echo "→ Установка pyproj (координаты)..."
pip install 'pyproj>=3.2.0' --quiet
echo -e "${GREEN}✓ pyproj установлен${NC}"

echo "→ Установка openpyxl (Excel)..."
pip install 'openpyxl>=3.0.0' --quiet
echo -e "${GREEN}✓ openpyxl установлен${NC}"

echo "→ Установка reportlab (PDF)..."
pip install 'reportlab>=3.6.0' --quiet
echo -e "${GREEN}✓ reportlab установлен${NC}"

echo "→ Установка ezdxf (DXF файлы)..."
pip install 'ezdxf>=0.17.0' --quiet
echo -e "${GREEN}✓ ezdxf установлен${NC}"

echo "→ Установка Pillow (изображения)..."
pip install 'Pillow>=9.0.0' --quiet
echo -e "${GREEN}✓ Pillow установлен${NC}"

echo "→ Установка shapely (геометрия)..."
pip install 'shapely>=1.8.0' --quiet
echo -e "${GREEN}✓ shapely установлен${NC}"

echo "→ Установка plotly (интерактивные 3D графики)..."
pip install 'plotly>=5.0.0' --quiet
echo -e "${GREEN}✓ plotly установлен${NC}"

echo "→ Установка scikit-learn (кластеризация)..."
pip install 'scikit-learn>=1.0.0' --quiet
echo -e "${GREEN}✓ scikit-learn установлен${NC}"

echo "→ Установка python-docx (Word отчеты)..."
pip install 'python-docx>=0.8.11' --quiet
echo -e "${GREEN}✓ python-docx установлен${NC}"

echo "→ Установка pytest (тестирование)..."
pip install 'pytest>=7.0.0' --quiet
echo -e "${GREEN}✓ pytest установлен${NC}"

echo ""
echo -e "${GREEN}✓ Все базовые зависимости установлены!${NC}"
echo ""

# Опциональные зависимости (GDAL)
echo "[6/6] Установка опциональных зависимостей..."
echo ""
echo "GDAL и GeoPandas требуются только для работы с Shapefile."
echo "Без них программа работает с CSV, GeoJSON и DXF файлами."
echo ""
read -p "Установить GDAL и GeoPandas? (y/n): " -n 1 -r
echo

if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo ""
    echo "Попытка установки GDAL..."
    echo ""
    
    if pip install GDAL --quiet 2>/dev/null; then
        echo -e "${GREEN}✓ GDAL установлен${NC}"
        echo "→ Установка GeoPandas..."
        if pip install 'geopandas>=0.10.0' --quiet; then
            echo -e "${GREEN}✓ GeoPandas установлен${NC}"
        else
            echo -e "${YELLOW}⚠ GeoPandas не удалось установить${NC}"
        fi
    else
        echo ""
        echo -e "${YELLOW}⚠ GDAL не удалось установить автоматически${NC}"
        echo ""
        echo "Для установки GDAL на Linux:"
        echo "  Ubuntu/Debian: sudo apt-get install gdal-bin libgdal-dev"
        echo "  Fedora/RHEL:   sudo dnf install gdal gdal-devel"
        echo ""
        echo "На macOS:"
        echo "  brew install gdal"
        echo ""
        echo "Затем установите Python пакеты:"
        echo "  pip install GDAL"
        echo "  pip install geopandas"
        echo ""
    fi
fi

echo ""

# Проверка установки
echo "════════════════════════════════════════════"
echo "Проверка установки..."
echo "════════════════════════════════════════════"
echo ""

python3 -c "import PyQt6; print('✓ PyQt6')" 2>/dev/null || echo -e "${RED}❌ PyQt6${NC}"
python3 -c "import PyQt6.QtWebEngineWidgets; print('✓ PyQt6-WebEngine')" 2>/dev/null || echo -e "${RED}❌ PyQt6-WebEngine${NC}"
python3 -c "import numpy; print('✓ NumPy')" 2>/dev/null || echo -e "${RED}❌ NumPy${NC}"
python3 -c "import scipy; print('✓ SciPy')" 2>/dev/null || echo -e "${RED}❌ SciPy${NC}"
python3 -c "import matplotlib; print('✓ matplotlib')" 2>/dev/null || echo -e "${RED}❌ matplotlib${NC}"
python3 -c "import pandas; print('✓ pandas')" 2>/dev/null || echo -e "${RED}❌ pandas${NC}"
python3 -c "import pyproj; print('✓ pyproj')" 2>/dev/null || echo -e "${RED}❌ pyproj${NC}"
python3 -c "import openpyxl; print('✓ openpyxl')" 2>/dev/null || echo -e "${RED}❌ openpyxl${NC}"
python3 -c "import reportlab; print('✓ reportlab')" 2>/dev/null || echo -e "${RED}❌ reportlab${NC}"
python3 -c "import ezdxf; print('✓ ezdxf')" 2>/dev/null || echo -e "${RED}❌ ezdxf${NC}"
python3 -c "import shapely; print('✓ shapely')" 2>/dev/null || echo -e "${RED}❌ shapely${NC}"
python3 -c "import plotly; print('✓ plotly')" 2>/dev/null || echo -e "${RED}❌ plotly${NC}"
python3 -c "import sklearn; print('✓ scikit-learn')" 2>/dev/null || echo -e "${RED}❌ scikit-learn${NC}"
python3 -c "import docx; print('✓ python-docx')" 2>/dev/null || echo -e "${RED}❌ python-docx${NC}"
python3 -c "import pytest; print('✓ pytest')" 2>/dev/null || echo -e "${RED}❌ pytest${NC}"

echo ""
echo "Опциональные:"
python3 -c "import osgeo; print('✓ GDAL')" 2>/dev/null || echo "○ GDAL (не установлен)"
python3 -c "import geopandas; print('✓ GeoPandas')" 2>/dev/null || echo "○ GeoPandas (не установлен)"

echo ""
echo "════════════════════════════════════════════"
echo -e "${GREEN}✅ УСТАНОВКА ЗАВЕРШЕНА!${NC}"
echo "════════════════════════════════════════════"
echo ""
echo "Программа готова к использованию!"
echo ""
echo "Для запуска используйте:"
echo "  ./run.sh"
echo ""
echo "или:"
echo "  source venv/bin/activate"
echo "  python3 main.py"
echo ""

# Предложение запустить программу
read -p "Запустить программу сейчас? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo ""
    echo "Запуск GeoVertical Analyzer..."
    echo ""
    python3 main.py
fi

echo ""
echo "Спасибо за использование GeoVertical Analyzer!"
echo ""

