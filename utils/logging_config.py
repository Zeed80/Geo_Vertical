"""
Конфигурация логирования для GeoVertical Analyzer

Уровни логирования:
- DEBUG: Детальная информация для отладки
- INFO: Общая информация о работе программы
- WARNING: Предупреждения о потенциальных проблемах
- ERROR: Ошибки, не приводящие к остановке программы
- CRITICAL: Критические ошибки, требующие немедленного внимания
"""

import logging
import logging.handlers
from pathlib import Path
from datetime import datetime


# Создаем директорию для логов, если её нет
LOGS_DIR = Path(__file__).parent.parent / 'logs'
LOGS_DIR.mkdir(exist_ok=True)


def setup_logging(level=logging.INFO, console=True, file=True, file_level=logging.DEBUG):
    """
    Настройка системы логирования
    
    Args:
        level: Уровень логирования для консоли
        console: Выводить логи в консоль
        file: Сохранять логи в файл
        file_level: Уровень логирования для файла
    """
    
    # Создаем корневой логгер
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    
    # Очищаем существующие обработчики
    root_logger.handlers.clear()
    
    # Формат логов - очень подробный для файла
    detailed_formatter = logging.Formatter(
        fmt='%(asctime)s.%(msecs)03d | %(levelname)-8s | [%(name)s] %(funcName)s():%(lineno)d | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Средняя детальность для консоли
    simple_formatter = logging.Formatter(
        fmt='%(asctime)s | %(levelname)-8s | %(message)s',
        datefmt='%H:%M:%S'
    )
    
    # Консольный обработчик
    if console:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(simple_formatter)
        root_logger.addHandler(console_handler)
    
    # Файловый обработчик (rotation)
    if file:
        # Основной лог-файл с rotation
        file_handler = logging.handlers.RotatingFileHandler(
            filename=LOGS_DIR / 'geovertical.log',
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(file_level)
        file_handler.setFormatter(detailed_formatter)
        root_logger.addHandler(file_handler)
        
        # Файл только с ошибками
        error_handler = logging.handlers.RotatingFileHandler(
            filename=LOGS_DIR / 'errors.log',
            maxBytes=5 * 1024 * 1024,  # 5 MB
            backupCount=3,
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(detailed_formatter)
        root_logger.addHandler(error_handler)
        
        # Файл с операциями 3D редактора (отдельно для удобства)
        editor_handler = logging.handlers.RotatingFileHandler(
            filename=LOGS_DIR / 'editor_3d.log',
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=3,
            encoding='utf-8'
        )
        editor_handler.setLevel(logging.DEBUG)
        editor_handler.setFormatter(detailed_formatter)
        # Фильтр только для логов из gui.point_editor_3d
        editor_handler.addFilter(lambda record: 'point_editor_3d' in record.name)
        root_logger.addHandler(editor_handler)
    
    # Логгируем старт приложения
    logger = logging.getLogger(__name__)
    logger.info('='*70)
    logger.info('GeoVertical Analyzer - Логирование инициализировано')
    logger.info(f'Уровень консоли: {logging.getLevelName(level)}')
    logger.info(f'Уровень файла: {logging.getLevelName(file_level)}')
    logger.info(f'Директория логов: {LOGS_DIR.absolute()}')
    logger.info('='*70)


def get_logger(name: str) -> logging.Logger:
    """
    Получить логгер для модуля
    
    Args:
        name: Имя модуля (обычно __name__)
        
    Returns:
        Настроенный логгер
    """
    return logging.getLogger(name)


# Настройка логирования для сторонних библиотек
def configure_third_party_logging():
    """Настройка уровней логирования для сторонних библиотек"""
    
    # Отключаем или уменьшаем детальность логов сторонних библиотек
    logging.getLogger('matplotlib').setLevel(logging.WARNING)
    logging.getLogger('PIL').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('shapely').setLevel(logging.WARNING)
    logging.getLogger('fiona').setLevel(logging.WARNING)
    logging.getLogger('pyproj').setLevel(logging.WARNING)


class ContextFilter(logging.Filter):
    """
    Фильтр для добавления контекстной информации в логи
    Может быть расширен для добавления пользовательской информации
    """
    
    def filter(self, record):
        # Добавляем дополнительную информацию в record
        record.app_name = 'GeoVertical'
        return True


def log_exception(logger: logging.Logger, exc: Exception, message: str = "Исключение"):
    """
    Логирование исключения с полной информацией
    
    Args:
        logger: Логгер
        exc: Исключение
        message: Дополнительное сообщение
    """
    logger.error(f"{message}: {type(exc).__name__}: {str(exc)}", exc_info=True)


# Примеры использования в других модулях:
"""
# В начале модуля:
from utils.logging_config import get_logger
logger = get_logger(__name__)

# В коде:
logger.debug("Детальная информация для отладки")
logger.info("Информационное сообщение")
logger.warning("Предупреждение")
logger.error("Ошибка")
logger.critical("Критическая ошибка")

# При обработке исключений:
try:
    # код
except Exception as e:
    logger.exception("Описание ошибки")  # Автоматически добавит stack trace
"""

