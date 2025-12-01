"""
GeoVertical Analyzer - Главный файл приложения

Программа для геодезического контроля антенно-мачтовых сооружений
Анализ вертикальности и прямолинейности по нормативам СП 70.13330.2012
"""

import sys
import logging
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QCoreApplication
from PyQt6.QtGui import QGuiApplication
from gui.main_window import MainWindow
from utils.logging_config import setup_logging, configure_third_party_logging, get_logger
from core import __version__


def main():
    """Точка входа в приложение"""
    
    # Настройка логирования
    setup_logging(
        level=logging.INFO,      # Уровень для консоли
        console=True,            # Вывод в консоль
        file=True,               # Сохранение в файл
        file_level=logging.DEBUG # Детальные логи в файле
    )
    configure_third_party_logging()
    
    logger = get_logger(__name__)
    logger.info(f"Запуск GeoVertical Analyzer v{__version__}")
    
    try:
        # Включаем настройки HiDPI, если они поддерживаются текущей версией Qt
        if hasattr(Qt.ApplicationAttribute, "AA_EnableHighDpiScaling"):
            QCoreApplication.setAttribute(
                Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True
            )
        if hasattr(Qt.ApplicationAttribute, "AA_UseHighDpiPixmaps"):
            QCoreApplication.setAttribute(
                Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True
            )
        if hasattr(Qt, "HighDpiScaleFactorRoundingPolicy"):
            QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
                Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
            )
        
        # Создаем приложение
        app = QApplication(sys.argv)
        app.setApplicationName('GeoVertical Analyzer')
        app.setOrganizationName('GeoAnalysis')
        logger.debug("Qt Application создано")
        
        # Устанавливаем стиль
        app.setStyle('Fusion')
        logger.debug("Стиль установлен: Fusion")
        
        # Создаем и показываем главное окно
        window = MainWindow()
        window.show()
        logger.info("Главное окно открыто")
        
        # Запускаем цикл обработки событий
        exit_code = app.exec()
        logger.info(f"Приложение завершено с кодом {exit_code}")
        sys.exit(exit_code)
        
    except Exception as e:
        logger.critical(f"Критическая ошибка при запуске приложения: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()

