"""
Асинхронная загрузка данных через QThread
"""

import logging
from typing import Optional, Tuple
import pandas as pd
from PyQt6.QtCore import QThread, pyqtSignal

from core.data_loader import load_data_from_file
from core.exceptions import DataLoadError, FileFormatError, DataValidationError

logger = logging.getLogger(__name__)


class DataLoadThread(QThread):
    """
    Поток для асинхронной загрузки данных из файла
    
    Сигналы:
        data_loaded(data, epsg_code): Данные успешно загружены
        progress(percent, message): Прогресс загрузки
        error(error_message): Ошибка загрузки
        finished(): Загрузка завершена (успешно или с ошибкой)
    """
    
    data_loaded = pyqtSignal(pd.DataFrame, object)  # data, epsg_code
    progress = pyqtSignal(int, str)  # percent, message
    error = pyqtSignal(str)  # error_message
    finished = pyqtSignal()
    
    def __init__(self, file_path: str, parent=None):
        super().__init__(parent)
        self.file_path = file_path
        self._cancelled = False
        
    def cancel(self):
        """Отменить загрузку"""
        self._cancelled = True
        logger.info("Загрузка данных отменена пользователем")
    
    def run(self):
        """Выполнение загрузки в отдельном потоке"""
        try:
            self.progress.emit(10, f"Начало загрузки файла: {self.file_path}")
            
            if self._cancelled:
                self.error.emit("Загрузка отменена")
                self.finished.emit()
                return
            
            # Определяем формат файла
            from pathlib import Path
            extension = Path(self.file_path).suffix.lower()
            self.progress.emit(30, f"Определен формат: {extension}")
            
            if self._cancelled:
                self.error.emit("Загрузка отменена")
                self.finished.emit()
                return
            
            # Загружаем данные
            self.progress.emit(50, "Чтение данных из файла...")
            data, epsg_code = load_data_from_file(self.file_path)
            
            if self._cancelled:
                self.error.emit("Загрузка отменена")
                self.finished.emit()
                return
            
            # Валидация данных
            from core.data_loader import validate_data
            self.progress.emit(80, "Проверка данных...")
            is_valid, message = validate_data(data)
            
            if not is_valid:
                raise DataValidationError(message)
            
            if self._cancelled:
                self.error.emit("Загрузка отменена")
                self.finished.emit()
                return
            
            self.progress.emit(100, f"Загружено {len(data)} точек")
            self.data_loaded.emit(data, epsg_code)
            logger.info(f"Данные успешно загружены: {len(data)} точек")
            
        except (DataLoadError, FileFormatError, DataValidationError) as e:
            error_msg = str(e)
            logger.error(f"Ошибка загрузки данных: {error_msg}", exc_info=True)
            self.error.emit(error_msg)
        except Exception as e:
            error_msg = f"Неожиданная ошибка при загрузке: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self.error.emit(error_msg)
        finally:
            self.finished.emit()

