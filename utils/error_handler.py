"""
Утилита для улучшенной обработки ошибок
"""

import logging
import traceback
from typing import Optional, Callable, Any
from functools import wraps

from core.exceptions import GeoVerticalError

logger = logging.getLogger(__name__)


def handle_errors(
    default_return: Any = None,
    log_error: bool = True,
    reraise: bool = True,
    error_message: Optional[str] = None
):
    """
    Декоратор для обработки ошибок в функциях
    
    Args:
        default_return: Значение, возвращаемое при ошибке (если reraise=False)
        log_error: Логировать ли ошибку
        reraise: Пробрасывать ли исключение дальше
        error_message: Кастомное сообщение об ошибке
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except GeoVerticalError as e:
                # Известные ошибки приложения - логируем и пробрасываем
                if log_error:
                    logger.error(f"Ошибка в {func.__name__}: {e}", exc_info=True)
                if reraise:
                    raise
                return default_return
            except Exception as e:
                # Неожиданные ошибки - логируем детально
                error_msg = error_message or f"Неожиданная ошибка в {func.__name__}"
                if log_error:
                    logger.critical(
                        f"{error_msg}: {type(e).__name__}: {str(e)}\n"
                        f"Traceback:\n{traceback.format_exc()}",
                        exc_info=True
                    )
                if reraise:
                    # Преобразуем в известное исключение приложения
                    from core.exceptions import CalculationError
                    raise CalculationError(f"{error_msg}: {str(e)}") from e
                return default_return
        return wrapper
    return decorator


def safe_execute(
    func: Callable,
    *args,
    default_return: Any = None,
    log_error: bool = True,
    error_message: Optional[str] = None,
    **kwargs
) -> Any:
    """
    Безопасное выполнение функции с обработкой ошибок
    
    Args:
        func: Функция для выполнения
        *args: Позиционные аргументы
        default_return: Значение при ошибке
        log_error: Логировать ли ошибку
        error_message: Кастомное сообщение
        **kwargs: Именованные аргументы
        
    Returns:
        Результат функции или default_return при ошибке
    """
    try:
        return func(*args, **kwargs)
    except GeoVerticalError as e:
        if log_error:
            logger.error(f"Ошибка при выполнении {func.__name__}: {e}", exc_info=True)
        return default_return
    except Exception as e:
        error_msg = error_message or f"Неожиданная ошибка при выполнении {func.__name__}"
        if log_error:
            logger.critical(
                f"{error_msg}: {type(e).__name__}: {str(e)}\n"
                f"Traceback:\n{traceback.format_exc()}",
                exc_info=True
            )
        return default_return


def format_error_message(error: Exception, context: Optional[str] = None) -> str:
    """
    Форматирует сообщение об ошибке для пользователя
    
    Args:
        error: Исключение
        context: Контекст ошибки
        
    Returns:
        Отформатированное сообщение
    """
    error_type = type(error).__name__
    error_msg = str(error)
    
    # Улучшаем сообщения для известных ошибок
    if isinstance(error, GeoVerticalError):
        if context:
            return f"{context}: {error_msg}"
        return error_msg
    
    # Для неизвестных ошибок добавляем контекст
    if context:
        return f"{context}: {error_type}: {error_msg}"
    
    return f"{error_type}: {error_msg}"


def log_critical_error(error: Exception, context: Optional[str] = None):
    """
    Логирует критическую ошибку с полным traceback
    
    Args:
        error: Исключение
        context: Контекст ошибки
    """
    context_msg = f" [{context}]" if context else ""
    logger.critical(
        f"КРИТИЧЕСКАЯ ОШИБКА{context_msg}: {type(error).__name__}: {str(error)}\n"
        f"Traceback:\n{traceback.format_exc()}",
        exc_info=True
    )

