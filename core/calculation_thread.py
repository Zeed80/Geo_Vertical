"""
Асинхронные расчеты через QThread
"""

import logging
from typing import Optional, Dict, Any
import pandas as pd
from PyQt6.QtCore import QThread, pyqtSignal

from core.services.calculation_service import CalculationService
from core.exceptions import (
    CalculationError,
    InsufficientDataError,
    InvalidCoordinatesError,
    GroupingError,
    CoordinateTransformError,
)

logger = logging.getLogger(__name__)


class CalculationThread(QThread):
    """
    Поток для асинхронного выполнения расчетов вертикальности и прямолинейности
    
    Сигналы:
        calculation_finished(results): Расчеты успешно завершены
        progress(percent, message): Прогресс расчетов
        error(error_message): Ошибка расчетов
        finished(): Расчеты завершены (успешно или с ошибкой)
    """
    
    calculation_finished = pyqtSignal(dict)  # results
    progress = pyqtSignal(int, str)  # percent, message
    error = pyqtSignal(str)  # error_message
    finished = pyqtSignal()
    
    def __init__(
        self,
        raw_data: pd.DataFrame,
        table_data: pd.DataFrame,
        epsg_code: Optional[int],
        height_tolerance: float,
        center_method: str,
        use_assigned_belts: bool = True,
        parent=None
    ):
        """
        Инициализация потока расчетов
        
        Args:
            raw_data: Исходные данные (для отображения)
            table_data: Данные из таблицы (для расчетов)
            epsg_code: EPSG код системы координат
            height_tolerance: Допуск группировки по высоте
            center_method: Метод расчета центра пояса
            use_assigned_belts: Использовать назначенные пояса
            parent: Родительский объект
        """
        super().__init__(parent)
        self.raw_data = raw_data
        self.table_data = table_data
        self.epsg_code = epsg_code
        self.height_tolerance = height_tolerance
        self.center_method = center_method
        self.use_assigned_belts = use_assigned_belts
        self._cancelled = False
        
        # Создаем сервис расчетов
        self.calculation_service = CalculationService()
    
    def cancel(self):
        """Отменить расчеты"""
        self._cancelled = True
        logger.info("Расчеты отменены пользователем")
    
    def run(self):
        """Выполнение расчетов в отдельном потоке"""
        try:
            self.progress.emit(5, "Подготовка данных...")
            
            if self._cancelled:
                self.error.emit("Расчеты отменены")
                self.finished.emit()
                return
            
            # Проверка данных
            if self.table_data is None or self.table_data.empty:
                raise InsufficientDataError(
                    required=1, 
                    actual=0, 
                    message="Нет данных для расчета"
                )
            
            self.progress.emit(10, "Валидация данных...")
            
            if self._cancelled:
                self.error.emit("Расчеты отменены")
                self.finished.emit()
                return
            
            # Подготовка данных (трансформация координат)
            self.progress.emit(20, "Трансформация координат...")
            
            if self.epsg_code:
                self.calculation_service.crs_manager.set_original_crs(self.epsg_code)
            working_data = self.calculation_service.crs_manager.prepare_for_calculations(
                self.table_data
            )
            
            if self._cancelled:
                self.error.emit("Расчеты отменены")
                self.finished.emit()
                return
            
            # Выполняем расчеты через process_tower_data
            self.progress.emit(30, "Группировка точек по поясам...")
            
            from core.calculations import process_tower_data
            
            # Выполняем расчеты с кэшированием
            results = process_tower_data(
                working_data,
                self.height_tolerance,
                self.center_method,
                use_assigned_belts=self.use_assigned_belts,
                use_cache=True
            )
            
            if self._cancelled:
                self.error.emit("Расчеты отменены")
                self.finished.emit()
                return
            
            if not results['valid']:
                raise CalculationError("Не удалось выполнить расчеты: результаты невалидны")
            
            self.progress.emit(80, f"Найдено {len(results['centers'])} поясов")
            
            if self._cancelled:
                self.error.emit("Расчеты отменены")
                self.finished.emit()
                return
            
            # Проверка нормативов
            self.progress.emit(90, "Проверка нормативов...")
            
            # Проверяем нормативы
            vertical_check = self.calculation_service._check_verticality_normatives(results)
            straightness_check = self.calculation_service._check_straightness_normatives(results)
            
            results['vertical_check'] = vertical_check
            results['straightness_check'] = straightness_check
            
            if self._cancelled:
                self.error.emit("Расчеты отменены")
                self.finished.emit()
                return
            
            self.progress.emit(100, "Расчеты завершены")
            self.calculation_finished.emit(results)
            logger.info(
                f"Расчет завершен: Поясов - {len(centers_df)}; "
                f"Вертикальность: ✓{vertical_check['passed']} ✗{vertical_check['failed']}; "
                f"Прямолинейность: ✓{straightness_check['passed']} ✗{straightness_check['failed']}"
            )
            
        except (InsufficientDataError, InvalidCoordinatesError, GroupingError, CoordinateTransformError) as e:
            error_msg = f"Ошибка при выполнении расчетов: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self.error.emit(error_msg)
        except CalculationError as e:
            error_msg = f"Ошибка расчета: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self.error.emit(error_msg)
        except Exception as e:
            error_msg = f"Неожиданная ошибка при выполнении расчетов: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self.error.emit(error_msg)
        finally:
            self.finished.emit()

