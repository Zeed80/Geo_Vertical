"""
Сервис расчетов - выполнение расчетов вертикальности и прямолинейности
"""

import logging
from typing import Optional, Dict, Any

import numpy as np
import pandas as pd

from core.calculations import process_tower_data, group_points_by_height, _build_is_station_mask
from core.normatives import NormativeChecker
from utils.coordinate_systems import CoordinateSystemManager
from core.exceptions import (
    CalculationError,
    InsufficientDataError,
    InvalidCoordinatesError,
    GroupingError,
    CoordinateTransformError,
)

logger = logging.getLogger(__name__)


class CalculationService:
    """
    Сервис для выполнения расчетов вертикальности и прямолинейности
    
    Отвечает за:
    - Выполнение расчетов на основе данных
    - Проверку нормативов
    - Подготовку данных для расчетов (трансформация координат)
    """
    
    def __init__(self):
        """Инициализация сервиса расчетов"""
        self.crs_manager = CoordinateSystemManager()
        self.normative_checker = NormativeChecker()
    
    def calculate(
        self,
        raw_data: pd.DataFrame,
        table_data: pd.DataFrame,
        epsg_code: Optional[int],
        height_tolerance: float,
        center_method: str,
        use_assigned_belts: bool = True
    ) -> Dict[str, Any]:
        """
        Выполняет расчеты вертикальности и прямолинейности
        
        Args:
            raw_data: Исходные данные (для отображения)
            table_data: Данные из таблицы (для расчетов)
            epsg_code: EPSG код системы координат
            height_tolerance: Допуск группировки по высоте
            center_method: Метод расчета центра пояса
            use_assigned_belts: Использовать назначенные пояса
            
        Returns:
            Словарь с результатами расчетов:
            {
                'valid': bool,
                'belts': Dict,
                'centers': pd.DataFrame,
                'axis': Dict,
                'local_cs': Dict,
                'standing_point': Dict,
                'vertical_check': Dict,
                'straightness_check': Dict
            }
            
        Raises:
            CalculationError: При ошибке расчетов
        """
        if table_data is None or table_data.empty:
            raise InsufficientDataError(required=1, actual=0, message="Нет данных для расчета")
        
        try:
            logger.info("Начало выполнения расчетов")
            
            # Подготавливаем данные (переводим в метры если нужно)
            if epsg_code:
                self.crs_manager.set_original_crs(epsg_code)
            working_data = self.crs_manager.prepare_for_calculations(table_data)
            
            # Выполняем расчеты
            results = process_tower_data(
                working_data,
                height_tolerance,
                center_method,
                use_assigned_belts=use_assigned_belts,
                use_cache=True
            )
            
            if not results['valid']:
                reason = self._describe_invalid_dataset(working_data, height_tolerance, use_assigned_belts)
                logger.error("Сервис расчетов: результаты невалидны. %s", reason)
                raise CalculationError(f"Не удалось выполнить расчеты: {reason}")
            
            # Проверяем нормативы
            vertical_check = self._check_verticality_normatives(results)
            straightness_check = self._check_straightness_normatives(results)
            
            results['vertical_check'] = vertical_check
            results['straightness_check'] = straightness_check
            
            logger.info(
                f"Расчет завершен: Поясов - {len(results['centers'])}; "
                f"Вертикальность: ✓{vertical_check['passed']} ✗{vertical_check['failed']}; "
                f"Прямолинейность: ✓{straightness_check['passed']} ✗{straightness_check['failed']}"
            )
            
            return results
            
        except (InsufficientDataError, InvalidCoordinatesError, GroupingError, CoordinateTransformError) as e:
            error_msg = f"Ошибка при выполнении расчетов: {str(e)}"
            logger.error(error_msg, exc_info=True)
            raise CalculationError(error_msg) from e
        except Exception as e:
            error_msg = f"Неожиданная ошибка при выполнении расчетов: {type(e).__name__}: {str(e)}"
            logger.critical(error_msg, exc_info=True)
            raise CalculationError(error_msg) from e

    def _describe_invalid_dataset(
        self,
        data: Optional[pd.DataFrame],
        height_tolerance: float,
        use_assigned_belts: bool
    ) -> str:
        """Формирует понятное описание причины невалидного результата."""
        if data is None or data.empty:
            return "после подготовки данных отсутствуют точки башни"

        required_columns = ['x', 'y', 'z']
        missing = [col for col in required_columns if col not in data.columns]
        if missing:
            return f"нет обязательных колонок: {', '.join(missing)}"

        working = data.copy()
        removed_stations = 0
        if 'is_station' in working.columns:
            try:
                station_mask = _build_is_station_mask(working['is_station'])
                removed_stations = int(station_mask.sum())
                working = working[~station_mask]
            except Exception:
                pass

        if working.empty:
            total = len(data)
            return f"все {total} записей помечены как точки стояния и исключены из расчёта"

        coord_frame = working[['x', 'y', 'z']]
        invalid_coords = (~np.isfinite(coord_frame)).any(axis=1)
        if invalid_coords.any():
            return f"обнаружено {int(invalid_coords.sum())} точек с нечисловыми координатами"

        try:
            belt_groups = group_points_by_height(
                data,
                tolerance=height_tolerance,
                use_assigned_belts=use_assigned_belts
            )
        except Exception as exc:
            return f"ошибка группировки по высоте: {exc}"

        if not belt_groups:
            if removed_stations:
                return "после исключения точек стояния не осталось точек для формирования поясов"
            return "не удалось сформировать ни одного пояса по заданному допуску высоты"

        return "не удалось построить центры поясов — проверьте корректность данных"
    
    def _check_verticality_normatives(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Проверяет нормативы вертикальности
        
        Returns:
            Словарь с результатами проверки:
            {
                'passed': int,
                'failed': int,
                'violations': List[Dict]
            }
        """
        if not results['valid'] or results['centers'].empty:
            return {'passed': 0, 'failed': 0, 'violations': []}
        
        try:
            centers = results['centers']
            
            # Используем метод NormativeChecker для проверки всех отклонений
            deviations = centers['deviation'].tolist()
            heights = centers['z'].tolist()
            
            check_result = self.normative_checker.check_vertical_deviations(deviations, heights)
            
            # Преобразуем результат в нужный формат
            violations = []
            for item in check_result.get('non_compliant', []):
                violations.append({
                    'belt_height': item.get('height', 0.0),
                    'deviation': item.get('deviation', 0.0),
                    'normative': item.get('tolerance', 0.0)
                })
            
            return {
                'passed': check_result.get('passed', 0),
                'failed': check_result.get('failed', 0),
                'violations': violations
            }
            
        except Exception as e:
            error_msg = f"Ошибка при проверке нормативов вертикальности: {type(e).__name__}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {'passed': 0, 'failed': 0, 'violations': []}
    
    def _check_straightness_normatives(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Проверяет нормативы прямолинейности
        
        Returns:
            Словарь с результатами проверки:
            {
                'passed': int,
                'failed': int,
                'violations': List[Dict]
            }
        """
        if not results['valid'] or results['centers'].empty:
            return {'passed': 0, 'failed': 0, 'violations': []}
        
        try:
            centers = results['centers']
            
            # Извлекаем данные для проверки
            deflections = []
            heights = []
            section_lengths = []
            
            for idx, row in centers.iterrows():
                deviation = row.get('straightness_deviation', 0.0)
                section_length = row.get('section_length', 0.0)
                
                if section_length > 0:
                    deflections.append(deviation)
                    heights.append(row.get('z', 0.0))
                    section_lengths.append(section_length)
            
            if not deflections:
                return {'passed': 0, 'failed': 0, 'violations': []}
            
            # Используем метод NormativeChecker для проверки всех отклонений
            # Берем первую длину секции (все должны быть одинаковыми)
            section_length = section_lengths[0] if section_lengths else 0.0
            check_result = self.normative_checker.check_straightness_deviations(deflections, section_length)
            
            # Преобразуем результат в нужный формат
            violations = []
            for i, item in enumerate(check_result.get('non_compliant', [])):
                violations.append({
                    'belt_height': heights[i] if i < len(heights) else 0.0,
                    'deviation': item.get('deflection', 0.0),
                    'section_length': section_length,
                    'normative': item.get('tolerance', 0.0)
                })
            
            return {
                'passed': check_result.get('passed', 0),
                'failed': check_result.get('failed', 0),
                'violations': violations
            }
            
        except Exception as e:
            error_msg = f"Ошибка при проверке нормативов прямолинейности: {type(e).__name__}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {'passed': 0, 'failed': 0, 'violations': []}

