# ============================================
# GeoVertical Analyzer - Установщик PowerShell
# ============================================

Write-Host ""
Write-Host "╔════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║   GeoVertical Analyzer - Установщик       ║" -ForegroundColor Cyan
Write-Host "║   Версия 1.0.0                             ║" -ForegroundColor Cyan
Write-Host "╚════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# Проверка прав администратора
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "⚠ Внимание: Скрипт запущен без прав администратора" -ForegroundColor Yellow
    Write-Host "Некоторые операции могут не выполниться" -ForegroundColor Yellow
    Write-Host ""
}

# Проверка Python
Write-Host "[1/6] Проверка наличия Python..." -ForegroundColor Green
try {
    $pythonVersion = python --version 2>&1
    Write-Host "✓ $pythonVersion" -ForegroundColor Green
    
    # Проверка версии
    $version = python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
    if ([float]$version -lt 3.8) {
        Write-Host "❌ Требуется Python 3.8 или выше!" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "❌ Python не найден!" -ForegroundColor Red
    Write-Host "Скачайте с: https://www.python.org/downloads/" -ForegroundColor Yellow
    exit 1
}
Write-Host ""

# Обновление pip
Write-Host "[2/6] Обновление pip..." -ForegroundColor Green
python -m pip install --upgrade pip --quiet
Write-Host "✓ pip обновлен" -ForegroundColor Green
Write-Host ""

# Создание виртуального окружения
Write-Host "[3/6] Создание виртуального окружения..." -ForegroundColor Green
if (Test-Path "venv") {
    Write-Host "Виртуальное окружение существует" -ForegroundColor Yellow
    $recreate = Read-Host "Пересоздать? (y/n)"
    if ($recreate -eq "y") {
        Remove-Item -Recurse -Force venv
        python -m venv venv
    }
} else {
    python -m venv venv
}
Write-Host "✓ Виртуальное окружение готово" -ForegroundColor Green
Write-Host ""

# Активация окружения
Write-Host "Активация виртуального окружения..." -ForegroundColor Green
& "venv\Scripts\Activate.ps1"
Write-Host ""

# Установка зависимостей
Write-Host "[4/6] Установка базовых зависимостей..." -ForegroundColor Green
Write-Host "Это может занять несколько минут..." -ForegroundColor Yellow
Write-Host ""

$dependencies = @(
    "PyQt6>=6.7.0",
    "PyQt6-WebEngine>=6.7.0",
    "numpy>=1.21.0",
    "scipy>=1.7.0",
    "matplotlib>=3.5.0",
    "pandas>=1.3.0",
    "pyproj>=3.2.0",
    "openpyxl>=3.0.0",
    "reportlab>=3.6.0",
    "ezdxf>=0.17.0",
    "Pillow>=9.0.0",
    "shapely>=1.8.0",
    "pytest>=7.0.0"
)

$installed = 0
$failed = 0

foreach ($dep in $dependencies) {
    $name = $dep -replace ">=.*", ""
    Write-Host "→ Установка $name..." -NoNewline
    
    try {
        pip install $dep --quiet 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-Host " ✓" -ForegroundColor Green
            $installed++
        } else {
            Write-Host " ❌" -ForegroundColor Red
            $failed++
        }
    } catch {
        Write-Host " ❌" -ForegroundColor Red
        $failed++
    }
}

Write-Host ""
Write-Host "Установлено: $installed из $($dependencies.Count)" -ForegroundColor Cyan
Write-Host ""

# Опциональные зависимости
Write-Host "[5/6] Опциональные зависимости..." -ForegroundColor Green
Write-Host "GDAL требуется только для работы с Shapefile" -ForegroundColor Yellow
$installGDAL = Read-Host "Установить GDAL? (y/n)"

if ($installGDAL -eq "y") {
     Write-Host "Попытка установки GDAL..." -ForegroundColor Yellow
    pip install GDAL --quiet 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "⚠ Не удалось установить GDAL из PyPI" -ForegroundColor Yellow
        Write-Host "Пробую зеркало lfd.uci.edu..." -ForegroundColor Yellow
        pip install GDAL --quiet --only-binary GDAL --extra-index-url https://download.lfd.uci.edu/pythonlibs/wheels --trusted-host download.lfd.uci.edu 2>&1 | Out-Null
    }

    if ($LASTEXITCODE -eq 0) {
        Write-Host "✓ GDAL установлен" -ForegroundColor Green
        pip install geopandas>=0.10.0 --quiet 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "✓ GeoPandas установлен" -ForegroundColor Green
        } else {
            Write-Host "⚠ GeoPandas установить не удалось. Выполните вручную: pip install geopandas" -ForegroundColor Yellow
        }
    } else {
        Write-Host "⚠ Автоматическая установка GDAL не удалась" -ForegroundColor Yellow
        Write-Host "" 
        Write-Host "Для установки вручную:" -ForegroundColor Cyan
        Write-Host "1. Скачайте wheel с: https://www.lfd.uci.edu/~gohlke/pythonlibs/#gdal"
        Write-Host "2. pip install GDAL-xxx.whl" -ForegroundColor Cyan
        Write-Host "3. pip install geopandas" -ForegroundColor Cyan
    }
}
Write-Host ""

# Проверка установки
Write-Host "[6/6] Проверка установки..." -ForegroundColor Green
Write-Host "════════════════════════════════════════════" -ForegroundColor Cyan

$modules = @(
    "PyQt6",
    "numpy",
    "scipy",
    "matplotlib",
    "pandas",
    "pyproj",
    "openpyxl",
    "reportlab",
    "ezdxf",
    "shapely",
    "pytest"
)

foreach ($module in $modules) {
    python -c "import $module" 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✓ $module" -ForegroundColor Green
    } else {
        Write-Host "❌ $module" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "Опциональные:" -ForegroundColor Yellow
python -c "import osgeo" 2>&1 | Out-Null
if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ GDAL" -ForegroundColor Green
} else {
    Write-Host "○ GDAL (не установлен)" -ForegroundColor Gray
}

python -c "import geopandas" 2>&1 | Out-Null
if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ GeoPandas" -ForegroundColor Green
} else {
    Write-Host "○ GeoPandas (не установлен)" -ForegroundColor Gray
}

Write-Host ""
Write-Host "════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "✅ УСТАНОВКА ЗАВЕРШЕНА!" -ForegroundColor Green
Write-Host "════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""
Write-Host "Для запуска программы используйте:" -ForegroundColor Cyan
Write-Host "  .\run.bat" -ForegroundColor White
Write-Host ""
Write-Host "или:" -ForegroundColor Cyan
Write-Host "  venv\Scripts\Activate.ps1" -ForegroundColor White
Write-Host "  python main.py" -ForegroundColor White
Write-Host ""

# Предложение запуска
$launch = Read-Host "Запустить программу сейчас? (y/n)"
if ($launch -eq "y") {
    Write-Host ""
    Write-Host "Запуск GeoVertical Analyzer..." -ForegroundColor Green
    python main.py
}

Write-Host ""
Write-Host "Спасибо за использование GeoVertical Analyzer!" -ForegroundColor Cyan
Write-Host ""

