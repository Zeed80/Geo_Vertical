@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

:: Отключаем лишний шум от pip
set PIP_DISABLE_PIP_VERSION_CHECK=1

set "SCRIPT_DIR=%~dp0"
pushd "%SCRIPT_DIR%" >nul 2>&1

call :print_header
call :check_python
if errorlevel 1 goto fail

call :prepare_venv
if errorlevel 1 goto fail

call :activate_venv
if errorlevel 1 goto fail

call :update_build_tools

:: === ПРЯМАЯ УСТАНОВКА ТЯЖЕЛЫХ ПАКЕТОВ ===
call :install_gdal_direct
if errorlevel 1 goto fail

:: === УСТАНОВКА ОСТАЛЬНЫХ ПАКЕТОВ (включая dbfread) ===
call :install_main_packages
if errorlevel 1 goto fail

call :verify_installation

echo.
echo ========================================================
echo Установка полностью завершена!
echo ========================================================
call :offer_launch
goto end

:fail
echo.
echo [КРИТИЧЕСКАЯ ОШИБКА] Установка прервана.
echo.
echo Если ошибка "HTTP error 404" — возможно, для вашей версии Python
echo еще нет скомпилированного пакета GDAL.
echo Скрипт поддерживает Python 3.10, 3.11, 3.12.

:end
popd >nul
pause
exit /b 0

:: -----------------------------------------------------------------
:print_header
echo.
echo ==============================================
echo GeoVertical Analyzer - Установка
echo ==============================================
echo.
exit /b 0

:: -----------------------------------------------------------------
:check_python
echo [1/7] Проверка Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo Python не найден!
    exit /b 1
)

:: Получаем версию Python в формате "311" (без точек)
for /f "delims=" %%i in ('python -c "import sys; print(f'{sys.version_info.major}{sys.version_info.minor}')"') do set PY_VER=%%i

echo Ваш Python ID: %PY_VER%

if "%PY_VER%" neq "310" if "%PY_VER%" neq "311" if "%PY_VER%" neq "313" (
    echo [ОШИБКА] Этот скрипт поддерживает только Python 3.10, 3.11 или 3.12.
    exit /b 1
)
exit /b 0

:: -----------------------------------------------------------------
:prepare_venv
echo [2/7] Подготовка venv...
if exist venv (
    echo Виртуальное окружение найдено.
) else (
    echo Создание venv...
    python -m venv venv
    if errorlevel 1 exit /b 1
)
exit /b 0

:: -----------------------------------------------------------------
:activate_venv
echo [3/7] Активация...
call "venv\Scripts\activate.bat"
if errorlevel 1 exit /b 1
exit /b 0

:: -----------------------------------------------------------------
:update_build_tools
echo [4/7] Обновление pip...
python -m pip install --upgrade pip setuptools wheel --quiet
exit /b 0

:: -----------------------------------------------------------------
:install_gdal_direct
echo [5/7] Установка GDAL и Fiona (Direct)...

:: Базовая ссылка на репозиторий
set "BASE_URL=https://github.com/cgohlke/geospatial-wheels/releases/download/v2024.9.22"

set "GDAL_WHL=GDAL-3.9.2-cp%PY_VER%-cp%PY_VER%-win_amd64.whl"
set "FIONA_WHL=Fiona-1.10.1-cp%PY_VER%-cp%PY_VER%-win_amd64.whl"
set "SHAPELY_WHL=shapely-2.0.6-cp%PY_VER%-cp%PY_VER%-win_amd64.whl"

echo Скачивание и установка %GDAL_WHL% ...
python -m pip install "%BASE_URL%/%GDAL_WHL%"
if errorlevel 1 (
    echo [ОШИБКА] Не удалось установить GDAL.
    exit /b 1
)

echo Скачивание и установка %FIONA_WHL% ...
python -m pip install "%BASE_URL%/%FIONA_WHL%"
if errorlevel 1 (
    echo [ОШИБКА] Не удалось установить Fiona.
    exit /b 1
)

echo Скачивание и установка %SHAPELY_WHL% ...
python -m pip install "%BASE_URL%/%SHAPELY_WHL%"
:: Shapely не критичен, если упадет - поставится с PyPI
if errorlevel 1 echo Попробуем стандартный Shapely позже...

exit /b 0

:: -----------------------------------------------------------------
:install_main_packages
echo [6/7] Установка GeoPandas, dbfread и остальных библиотек...

:: Сначала GeoPandas
python -m pip install geopandas
if errorlevel 1 exit /b 1

:: Добавил dbfread в конец списка
set "PKGS=PyQt6 PyQt6-WebEngine pyqtgraph PyOpenGL numpy scipy matplotlib pandas pyproj openpyxl reportlab ezdxf Pillow plotly scikit-learn python-docx pytest dbfread"
echo Установка пакетов...
python -m pip install %PKGS% --quiet
pip install -r requirements.txt


if errorlevel 1 exit /b 1

exit /b 0

:: -----------------------------------------------------------------
:verify_installation
echo [7/7] Финальная проверка...
set "ERR=0"
python -c "import osgeo.gdal; print('GDAL OK')" || set "ERR=1"
python -c "import geopandas; print('GeoPandas OK')" || set "ERR=1"
python -c "import dbfread; print('dbfread OK')" || set "ERR=1"

if "%ERR%"=="1" (
    echo [ОШИБКА] Проверка модулей не пройдена.
    exit /b 1
)
exit /b 0

:: -----------------------------------------------------------------
:offer_launch
choice /C YN /M "Запустить main.py сейчас?"
if errorlevel 2 exit /b 0
python main.py
exit /b 0