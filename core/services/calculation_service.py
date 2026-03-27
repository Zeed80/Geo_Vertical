"""
Сервис расчетов - выполнение расчетов вертикальности и прямолинейности
"""

import logging
from typing import Any

import numpy as np
import pandas as pd

from core.calculations import (
    SECTION_GROUPING_ASSIGNED_SECTIONS,
    group_points_by_height,
    process_tower_data,
    resolve_section_grouping_mode,
)
from core.exceptions import (
    CalculationError,
    CoordinateTransformError,
    GroupingError,
    InsufficientDataError,
    InvalidCoordinatesError,
)
from core.normatives import NormativeChecker
from core.point_utils import (
    build_is_station_mask as _build_is_station_mask,
    build_working_tower_mask as _build_working_tower_mask,
)
from core.services.verticality_sections import build_verticality_check_from_sources
from utils.coordinate_systems import CoordinateSystemManager

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
        epsg_code: int | None,
        height_tolerance: float,
        center_method: str,
        use_assigned_belts: bool | None = None,
        section_grouping_mode: str = 'height_levels',
    ) -> dict[str, Any]:
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
            resolved_grouping_mode = resolve_section_grouping_mode(section_grouping_mode, use_assigned_belts)
            self._validate_input_data(table_data, resolved_grouping_mode)
            if epsg_code:
                self.crs_manager.set_original_crs(epsg_code)
            working_data = self.crs_manager.prepare_for_calculations(table_data)

            # Выполняем расчеты
            results = process_tower_data(
                working_data,
                height_tolerance,
                center_method,
                use_assigned_belts=use_assigned_belts,
                section_grouping_mode=resolved_grouping_mode,
                use_cache=True
            )

            if not results['valid']:
                reason = self._describe_invalid_dataset(working_data, height_tolerance, resolved_grouping_mode)
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
            error_msg = f"Ошибка при выполнении расчетов: {e!s}"
            logger.error(error_msg, exc_info=True)
            raise CalculationError(error_msg) from e
        except Exception as e:
            error_msg = f"Неожиданная ошибка при выполнении расчетов: {type(e).__name__}: {e!s}"
            logger.critical(error_msg, exc_info=True)
            raise CalculationError(error_msg) from e

    def _validate_input_data(self, data: pd.DataFrame, section_grouping_mode: str) -> None:
        """Проверяет базовую согласованность входных данных перед расчетом."""
        required_columns = ['x', 'y', 'z']
        missing = [col for col in required_columns if col not in data.columns]
        if missing:
            raise InvalidCoordinatesError(
                f"Отсутствуют обязательные колонки для расчета: {', '.join(missing)}"
            )

        coord_frame = data[['x', 'y', 'z']].apply(pd.to_numeric, errors='coerce')
        invalid_mask = (~np.isfinite(coord_frame)).any(axis=1)
        if invalid_mask.any():
            raise InvalidCoordinatesError(
                f"Обнаружено {int(invalid_mask.sum())} строк с нечисловыми координатами"
            )

        if 'belt' in data.columns:
            belt_values = data['belt'].dropna()
            if not belt_values.empty:
                belt_numeric = pd.to_numeric(belt_values, errors='coerce')
                if belt_numeric.isna().any():
                    raise GroupingError("Назначенные пояса содержат нечисловые значения")
                if (belt_numeric <= 0).any():
                    raise GroupingError("Номера поясов должны быть положительными")

                belt_numbers = sorted({int(value) for value in belt_numeric.astype(int).tolist()})
                expected = list(range(belt_numbers[0], belt_numbers[-1] + 1)) if belt_numbers else []
                missing_belts = [belt for belt in expected if belt not in belt_numbers]
                if missing_belts and section_grouping_mode == SECTION_GROUPING_ASSIGNED_SECTIONS:
                    raise GroupingError(
                        f"Нарушена непрерывность нумерации поясов: отсутствуют {missing_belts}"
                    )

        station_mask = (
            _build_is_station_mask(data['is_station'])
            if 'is_station' in data.columns
            else pd.Series(False, index=data.index)
        )
        zero_station_mask = station_mask & coord_frame['x'].round(6).eq(0.0) & coord_frame['y'].round(6).eq(0.0)
        if int(zero_station_mask.sum()) > 1:
            raise InvalidCoordinatesError("Обнаружено несколько station-точек с координатами (0, 0)")

        if 'tower_part' in data.columns:
            part_values = data.loc[_build_working_tower_mask(data), 'tower_part'].dropna()
            if not part_values.empty:
                part_numeric = pd.to_numeric(part_values, errors='coerce')
                if part_numeric.isna().any():
                    raise GroupingError("Номера частей башни содержат нечисловые значения")
                if (part_numeric <= 0).any():
                    raise GroupingError("Номера частей башни должны быть положительными")

                part_numbers = sorted({int(value) for value in part_numeric.astype(int).tolist()})
                expected_parts = list(range(part_numbers[0], part_numbers[-1] + 1)) if part_numbers else []
                missing_parts = [part for part in expected_parts if part not in part_numbers]
                if missing_parts:
                    raise GroupingError(
                        f"Нарушена непрерывность нумерации частей башни: отсутствуют {missing_parts}"
                    )

    def _describe_invalid_dataset(
        self,
        data: pd.DataFrame | None,
        height_tolerance: float,
        section_grouping_mode: str
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
        try:
            if 'is_station' in working.columns:
                station_mask = _build_is_station_mask(working['is_station'])
                removed_stations = int(station_mask.sum())
            working = working[_build_working_tower_mask(working)]
        except Exception:
            pass

        if working.empty:
            total = len(data)
            return f"все {total} записи исключены из расчета как нерабочие точки мачты"

        coord_frame = working[['x', 'y', 'z']]
        invalid_coords = (~np.isfinite(coord_frame)).any(axis=1)
        if invalid_coords.any():
            return f"обнаружено {int(invalid_coords.sum())} точек с нечисловыми координатами"

        try:
            belt_groups = group_points_by_height(
                data,
                tolerance=height_tolerance,
                section_grouping_mode=section_grouping_mode
            )
        except Exception as exc:
            return f"ошибка группировки по высоте: {exc}"

        if not belt_groups:
            if removed_stations:
                return "после исключения точек стояния не осталось точек для формирования поясов"
            return "не удалось сформировать ни одного пояса по заданному допуску высоты"

        return "не удалось построить центры поясов — проверьте корректность данных"

    def _check_verticality_normatives(self, results: dict[str, Any]) -> dict[str, Any]:
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
        if not results['valid']:
            return {'passed': 0, 'failed': 0, 'violations': []}

        try:
            centers = results.get('centers')
            check_result = build_verticality_check_from_sources(
                results.get('angular_verticality'),
                centers=centers,
                structure_type=self.normative_checker.structure_type,
            )
            if not check_result.get('total'):
                return {'passed': 0, 'failed': 0, 'violations': []}

            # Преобразуем результат в нужный формат
            violations = []
            for item in check_result.get('non_compliant', []):
                violations.append({
                    'belt_height': item.get('height', 0.0),
                    'deviation': item.get('deviation', 0.0),
                    'normative': item.get('tolerance', 0.0),
                    'section_num': item.get('section_num'),
                    'part_num': item.get('part_num'),
                })

            return {
                'passed': check_result.get('passed', 0),
                'failed': check_result.get('failed', 0),
                'violations': violations
            }

        except Exception as e:
            error_msg = f"Ошибка при проверке нормативов вертикальности: {type(e).__name__}: {e!s}"
            logger.error(error_msg, exc_info=True)
            return {'passed': 0, 'failed': 0, 'violations': []}

    def _check_straightness_normatives(self, results: dict[str, Any]) -> dict[str, Any]:
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
        if not results['valid'] or ('centers' not in results and 'straightness_summary' not in results):
            return {'passed': 0, 'failed': 0, 'violations': []}

        try:
            summary = results.get('straightness_summary')
            if isinstance(summary, dict):
                violations = []
                for violation in summary.get('violations', []):
                    violations.append({
                        'belt_height': float(violation.get('height_m', 0.0)),
                        'deviation': float(violation.get('deviation_mm', 0.0)) / 1000.0,
                        'section_length': float(violation.get('section_length_m', 0.0)),
                        'normative': float(violation.get('tolerance_mm', 0.0)) / 1000.0,
                        'part_number': int(violation.get('part_number', 1)),
                        'belt': int(violation.get('belt', 0)),
                    })

                return {
                    'passed': int(summary.get('passed', 0)),
                    'failed': int(summary.get('failed', 0)),
                    'violations': violations,
                }

            centers = results['centers']
            if centers.empty:
                return {'passed': 0, 'failed': 0, 'violations': []}

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
            error_msg = f"Ошибка при проверке нормативов прямолинейности: {type(e).__name__}: {e!s}"
            logger.error(error_msg, exc_info=True)
            return {'passed': 0, 'failed': 0, 'violations': []}

