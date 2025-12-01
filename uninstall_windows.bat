@echo off
chcp 65001 >nul
REM ============================================
REM GeoVertical Analyzer - Деинсталлятор
REM ============================================

echo.
echo ╔════════════════════════════════════════════╗
echo ║   GeoVertical Analyzer - Удаление         ║
echo ╚════════════════════════════════════════════╝
echo.

echo Это удалит:
echo   • Виртуальное окружение (venv)
echo   • Установленные зависимости
echo.
echo Исходный код программы НЕ будет удален.
echo.

choice /C YN /M "Продолжить удаление"
if errorlevel 2 goto cancel
if errorlevel 1 goto remove

:remove
echo.
echo Удаление виртуального окружения...
if exist venv (
    rmdir /s /q venv
    echo ✓ Виртуальное окружение удалено
) else (
    echo Виртуальное окружение не найдено
)

echo.
echo ✓ Деинсталляция завершена
echo.
echo Для полного удаления программы удалите папку проекта вручную.
echo.
pause
exit /b 0

:cancel
echo.
echo Отменено
echo.
pause
exit /b 0

