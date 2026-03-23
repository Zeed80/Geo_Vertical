"""
Модуль математических расчетов для анализа вертикальности и прямолинейности мачт
"""

import hashlib
import json
import logging
from typing import Any, Literal, Union

import numpy as np
import pandas as pd
from scipy import stats

from core.section_operations import _build_section_entries
from core.point_utils import (
    build_flag_mask as _build_flag_mask,
    build_working_tower_mask as _build_working_tower_mask,
    build_is_station_mask as _build_is_station_mask,
)
from core.point_utils import (
    decode_part_memberships as _decode_part_memberships,
)
from core.point_utils import (
    filter_points_by_part as _filter_points_by_part,
)
from core.import_grouping import estimate_composite_split_height
from core.straightness_calculations import build_straightness_profiles

logger = logging.getLogger(__name__)

# Кэш для результатов расчетов (ограничен по размеру)
_calculation_cache: dict[str, Any] = {}
_cache_access_order: list[str] = []  # Порядок доступа для LRU
_cache_max_size = 50  # Максимум 50 записей в кэше (увеличено для лучшей производительности)

SECTION_GROUPING_HEIGHT_LEVELS = 'height_levels'
SECTION_GROUPING_ASSIGNED_SECTIONS = 'assigned_sections'
SectionGroupingMode = Literal['height_levels', 'assigned_sections']
_SECTION_GROUPING_MODES = {
    SECTION_GROUPING_HEIGHT_LEVELS,
    SECTION_GROUPING_ASSIGNED_SECTIONS,
}


def invalidate_cache():
    """
    Инвалидирует весь кэш расчетов
    Полезно при изменении данных или параметров
    """
    global _calculation_cache, _cache_access_order
    _calculation_cache.clear()
    _cache_access_order.clear()
    logger.debug("Кэш расчетов очищен")


def _normalize_cache_value(value: Any) -> Any:
    """Normalize complex values into hash-stable scalars/strings."""
    if value is None:
        return "<NA>"
    if isinstance(value, np.ndarray):
        value = value.tolist()
    if isinstance(value, set):
        value = sorted(value)
    if isinstance(value, tuple):
        value = list(value)
    if isinstance(value, (list, dict)):
        try:
            return json.dumps(value, ensure_ascii=False, sort_keys=True)
        except TypeError:
            return str(value)
    try:
        if pd.isna(value):
            return "<NA>"
    except TypeError:
        pass
    return value


def _build_cache_signature_frame(points: pd.DataFrame | None) -> pd.DataFrame:
    """Build a normalized frame for cache hashing that includes row identity."""
    if points is None:
        return pd.DataFrame({"_row_index": pd.Series(dtype="object")})

    signature = points.copy().reset_index(drop=False).rename(columns={"index": "_row_index"})
    bool_columns = {"is_station", "is_auxiliary", "is_control", "is_part_boundary"}

    for column_name in list(signature.columns):
        series = signature[column_name]
        if column_name in bool_columns:
            signature[column_name] = _build_flag_mask(signature, column_name).astype(np.int8)
            continue
        if pd.api.types.is_bool_dtype(series):
            signature[column_name] = series.fillna(False).astype(np.int8)
            continue
        if pd.api.types.is_numeric_dtype(series):
            signature[column_name] = pd.to_numeric(series, errors="coerce")
            continue
        signature[column_name] = series.map(_normalize_cache_value)

    return signature.reindex(sorted(signature.columns), axis=1)


def _make_calculation_cache_key(
    points: pd.DataFrame,
    height_tolerance: float,
    center_method: str,
    grouping_marker: str,
) -> str:
    """Create a stable cache key that reflects both geometry and point semantics."""
    signature = _build_cache_signature_frame(points)
    try:
        data_hash = hashlib.md5(
            pd.util.hash_pandas_object(signature, index=False).values.tobytes()
        ).hexdigest()
    except Exception:
        data_hash = hashlib.md5(
            signature.to_csv(index=False).encode("utf-8")
        ).hexdigest()
    params_str = f"{height_tolerance}_{center_method}_{grouping_marker}"
    return f"{data_hash}_{params_str}"


def _get_cache_key(points: pd.DataFrame, height_tolerance: float, center_method: str, use_assigned_belts: bool) -> str:
    """Создает ключ кэша на основе параметров и данных"""
    # Пустые/неполные наборы данных тоже должны давать стабильный ключ и не падать.
    required_cols = {'x', 'y', 'z'}
    if points is None or not required_cols.issubset(points.columns):
        data_hash = hashlib.md5(
            f"{0 if points is None else len(points)}_{sorted(points.columns.tolist()) if points is not None else []}".encode()
        ).hexdigest()
        params_str = f"{height_tolerance}_{center_method}_{use_assigned_belts}"
        return f"{data_hash}_{params_str}"

    # Используем хеш данных и параметров для создания ключа
    try:
        data_hash = hashlib.md5(
            pd.util.hash_pandas_object(points[['x', 'y', 'z']]).values.tobytes()
        ).hexdigest()
    except Exception:
        # Fallback: используем простой хеш размера и суммы
        x_sum = points['x'].sum() if 'x' in points.columns else 0
        y_sum = points['y'].sum() if 'y' in points.columns else 0
        z_sum = points['z'].sum() if 'z' in points.columns else 0
        data_hash = hashlib.md5(
            f"{len(points)}_{x_sum}_{y_sum}_{z_sum}".encode()
        ).hexdigest()
    params_str = f"{height_tolerance}_{center_method}_{use_assigned_belts}"
    return f"{data_hash}_{params_str}"


def group_points_by_height(
    points: pd.DataFrame,
    tolerance: float = 0.1,
    use_assigned_belts: bool = False
) -> dict[float, pd.DataFrame]:
    """
    Группирует точки по поясам на основе высоты или назначенных поясов

    Args:
        points: DataFrame с колонками ['x', 'y', 'z'], опционально ['belt']
        tolerance: Допуск группировки по высоте (метры)
        use_assigned_belts: Использовать назначенные пояса вместо автогруппировки

    Returns:
        Словарь {средняя_высота: точки_пояса}
    """
    if points.empty:
        return {}

    working_mask = _build_working_tower_mask(points)
    working_points = points[working_mask]
    if len(working_points) != len(points):
        logger.info("Из группировки по поясам исключены нерабочие точки мачты")

    # Если есть назначенные пояса и нужно их использовать (оптимизировано)
    if use_assigned_belts and 'belt' in working_points.columns and working_points['belt'].notna().any():
        groups = {}
        # Используем groupby для более эффективной группировки
        for belt_num, belt_points in working_points.groupby('belt'):
            if pd.notna(belt_num):
                avg_height = belt_points['z'].mean()
                groups[avg_height] = belt_points  # Не копируем, используем view
        return groups

    # Иначе автоматическая группировка по высоте (оптимизировано)
    # Используем numpy для векторных операций вместо итераций
    z_values = working_points['z'].values
    sorted_indices = np.argsort(z_values)
    sorted_z = z_values[sorted_indices]

    # Векторная группировка по высоте
    groups = {}
    current_group_indices = []
    current_height = None

    for i, idx in enumerate(sorted_indices):
        z_val = sorted_z[i]
        if current_height is None:
            current_height = z_val
            current_group_indices = [idx]
        elif abs(z_val - current_height) <= tolerance:
            current_group_indices.append(idx)
        else:
            # Сохраняем текущую группу (без копирования, используем view)
            group_points = working_points.loc[current_group_indices]
            avg_height = group_points['z'].mean()
            groups[avg_height] = group_points  # Не копируем, используем view

            # Начинаем новую группу
            current_height = z_val
            current_group_indices = [idx]

    # Сохраняем последнюю группу
    if current_group_indices:
        group_points = working_points.loc[current_group_indices]
        avg_height = group_points['z'].mean()
        groups[avg_height] = group_points

    return groups


def resolve_section_grouping_mode(
    section_grouping_mode: str | None = SECTION_GROUPING_HEIGHT_LEVELS,
    use_assigned_belts: bool | None = None,
) -> SectionGroupingMode:
    """Resolve canonical section grouping mode while keeping legacy compatibility."""
    if section_grouping_mode is None:
        resolved = (
            SECTION_GROUPING_ASSIGNED_SECTIONS
            if use_assigned_belts
            else SECTION_GROUPING_HEIGHT_LEVELS
        )
    else:
        resolved = str(section_grouping_mode)

    if resolved not in _SECTION_GROUPING_MODES:
        raise ValueError(f"Unsupported section_grouping_mode: {resolved}")

    if use_assigned_belts is True:
        return SECTION_GROUPING_ASSIGNED_SECTIONS
    if use_assigned_belts is False and section_grouping_mode is None:
        return SECTION_GROUPING_HEIGHT_LEVELS
    return resolved  # type: ignore[return-value]


def _get_cache_key(
    points: pd.DataFrame,
    height_tolerance: float,
    center_method: str,
    section_grouping_mode: SectionGroupingMode,
) -> str:
    """Create a stable cache key that also includes the section grouping mode."""
    required_cols = {'x', 'y', 'z'}
    if points is None or not required_cols.issubset(points.columns):
        data_hash = hashlib.md5(
            f"{0 if points is None else len(points)}_{sorted(points.columns.tolist()) if points is not None else []}".encode()
        ).hexdigest()
        params_str = f"{height_tolerance}_{center_method}_{section_grouping_mode}"
        return f"{data_hash}_{params_str}"

    try:
        data_hash = hashlib.md5(
            pd.util.hash_pandas_object(points[['x', 'y', 'z']]).values.tobytes()
        ).hexdigest()
    except Exception:
        x_sum = points['x'].sum() if 'x' in points.columns else 0
        y_sum = points['y'].sum() if 'y' in points.columns else 0
        z_sum = points['z'].sum() if 'z' in points.columns else 0
        data_hash = hashlib.md5(
            f"{len(points)}_{x_sum}_{y_sum}_{z_sum}".encode()
        ).hexdigest()

    params_str = f"{height_tolerance}_{center_method}_{section_grouping_mode}"
    return f"{data_hash}_{params_str}"


def _get_cache_key(
    points: pd.DataFrame,
    height_tolerance: float,
    center_method: str,
    section_grouping_mode: SectionGroupingMode,
) -> str:
    """Create a stable cache key that reflects geometry, flags and row identity."""
    return _make_calculation_cache_key(
        points,
        height_tolerance,
        center_method,
        str(section_grouping_mode),
    )


def _cluster_points_by_z(
    points: pd.DataFrame,
    tolerance: float,
) -> dict[float, pd.DataFrame]:
    """Fallback z clustering that preserves original DataFrame index labels."""
    if points.empty:
        return {}

    sorted_points = points.sort_values('z')
    groups: dict[float, pd.DataFrame] = {}
    current_labels: list[Any] = []
    current_height: float | None = None

    for idx, row in sorted_points.iterrows():
        z_val = float(row['z'])
        if current_height is None:
            current_height = z_val
            current_labels = [idx]
            continue

        if abs(z_val - current_height) <= tolerance:
            current_labels.append(idx)
            current_height = z_val
            continue

        group_points = points.loc[current_labels]
        groups[float(group_points['z'].mean())] = group_points
        current_labels = [idx]
        current_height = z_val

    if current_labels:
        group_points = points.loc[current_labels]
        groups[float(group_points['z'].mean())] = group_points

    return groups


def _summarize_straightness_profiles(straightness_profiles: list[dict]) -> dict[str, Any]:
    """Aggregate canonical straightness profiles into a single summary payload."""
    summary = {
        'max_deflection_mm': 0.0,
        'passed': 0,
        'failed': 0,
        'violations': [],
    }

    for profile in straightness_profiles:
        part_number = int(profile.get('part_number', 1))
        belt = int(profile.get('belt', 0))
        tolerance_mm = float(profile.get('tolerance_mm', 0.0))
        section_length_m = float(profile.get('section_length_m', 0.0))
        summary['max_deflection_mm'] = max(
            summary['max_deflection_mm'],
            float(profile.get('max_deflection_mm', 0.0)),
        )

        for point in profile.get('points', []):
            deviation_mm = float(point.get('deflection_mm', 0.0))
            if abs(deviation_mm) <= tolerance_mm:
                summary['passed'] += 1
                continue

            summary['failed'] += 1
            summary['violations'].append(
                {
                    'part_number': part_number,
                    'belt': belt,
                    'height_m': float(point.get('z', 0.0)),
                    'deviation_mm': deviation_mm,
                    'tolerance_mm': tolerance_mm,
                    'section_length_m': section_length_m,
                }
            )

    return summary


def group_points_by_height(
    points: pd.DataFrame,
    tolerance: float = 0.1,
    section_grouping_mode: str = SECTION_GROUPING_HEIGHT_LEVELS,
    use_assigned_belts: bool | None = None,
) -> dict[float, pd.DataFrame]:
    """Group working tower points either by section heights or by legacy assigned sections."""
    if points.empty:
        return {}

    resolved_mode = resolve_section_grouping_mode(section_grouping_mode, use_assigned_belts)
    working_points = points[_build_working_tower_mask(points)]
    if len(working_points) != len(points):
        logger.info("РР· РіСЂСѓРїРїРёСЂРѕРІРєРё РїРѕ СЃРµРєС†РёСЏРј РёСЃРєР»СЋС‡РµРЅС‹ РЅРµСЂР°Р±РѕС‡РёРµ С‚РѕС‡РєРё РјР°С‡С‚С‹")

    if (
        resolved_mode == SECTION_GROUPING_ASSIGNED_SECTIONS
        and 'belt' in working_points.columns
        and working_points['belt'].notna().any()
    ):
        groups = {}
        numeric_belts = pd.to_numeric(working_points['belt'], errors='coerce')
        grouped_points = working_points.loc[numeric_belts.notna()].copy()
        if grouped_points.empty:
            return {}
        grouped_points['belt'] = numeric_belts.loc[grouped_points.index].astype(int)
        for _, belt_points in grouped_points.groupby('belt'):
            groups[float(belt_points['z'].mean())] = belt_points
        return groups

    groups = {}
    for entry in _build_section_entries(working_points, base_tolerance=tolerance):
        row_indices = list(entry.get('rows', {}).keys())
        if not row_indices:
            continue
        groups[float(entry['height'])] = working_points.loc[row_indices]

    if groups:
        return groups

    return _cluster_points_by_z(working_points, tolerance)


def calculate_belt_center(points: pd.DataFrame, method: str = 'mean') -> tuple[float, float, float]:
    """
    Вычисляет центр пояса

    Args:
        points: DataFrame с точками пояса
        method: Метод расчета ('mean' - среднее, 'lsq' - МНК)

    Returns:
        Кортеж (x_центр, y_центр, z_средняя)
    """
    if points.empty:
        return (0.0, 0.0, 0.0)

    if method == 'mean':
        x_center = points['x'].mean()
        y_center = points['y'].mean()
        z_avg = points['z'].mean()
    elif method == 'lsq':
        # Для круглых поясов - аппроксимация окружностью
        x_center = points['x'].median()
        y_center = points['y'].median()
        z_avg = points['z'].mean()
    else:
        raise ValueError(f"Unknown method: {method}")

    return (x_center, y_center, z_avg)


def approximate_tower_axis(centers: pd.DataFrame) -> dict[str, Union[float, bool]]:
    """
    Строит линейную аппроксимацию оси башни через центры поясов

    Ось представляется как прямая в 3D: (x, y) = (x0, y0) + t*(dx, dy)
    где t пропорционален высоте z

    Args:
        centers: DataFrame с центрами поясов (x, y, z)

    Returns:
        Словарь с параметрами оси
    """
    if len(centers) < 2:
        return {
            'x0': 0.0, 'y0': 0.0, 'z0': 0.0,
            'dx': 0.0, 'dy': 0.0, 'dz': 1.0,
            'valid': False
        }

    # Линейная регрессия x(z) и y(z)
    z = centers['z'].values
    x = centers['x'].values
    y = centers['y'].values

    # Регрессия для x
    slope_x, intercept_x, r_x, p_x, se_x = stats.linregress(z, x)

    # Регрессия для y
    slope_y, intercept_y, r_y, p_y, se_y = stats.linregress(z, y)

    # z0 - минимальная высота (основание)
    z0 = z.min()
    x0 = intercept_x + slope_x * z0
    y0 = intercept_y + slope_y * z0

    return {
        'x0': x0,           # Координата X в основании
        'y0': y0,           # Координата Y в основании
        'z0': z0,           # Высота основания
        'dx': slope_x,      # Наклон оси по X
        'dy': slope_y,      # Наклон оси по Y
        'dz': 1.0,          # Направление по Z
        'r_x': r_x,         # Коэффициент корреляции X
        'r_y': r_y,         # Коэффициент корреляции Y
        'valid': True
    }


def calculate_local_coordinate_system(
    centers: pd.DataFrame,
    standing_point: dict[str, float] | None,
    lower_belt_points: pd.DataFrame | None = None
) -> dict[str, Union[tuple[float, float, float], bool]]:
    """
    Вычисляет универсальную локальную систему координат для расчета вертикальности

    Алгоритм универсален для любой формы башни (3-гранная, 4-гранная, n-гранная,
    усеченная призма, призма и т.п.) и не зависит от количества граней.
    Использует только центры секций для определения ориентации.

    Логика (приоритеты):
    1. Если есть точки нижнего пояса (>= 3 точек) - используем главные оси инерции
       для определения ориентации X, Y на основе геометрии сечения башни
    2. Если нет точек пояса, но есть точка standing - используем направление
       от standing к центру нижней секции
    3. Если ничего нет - используем стандартную ориентацию (глобальные оси X, Y)

    Преимущества:
    - Универсален для любой формы и количества граней (3, 4, n)
    - Не требует знания количества граней
    - Устойчив к отсутствию точки standing
    - Использует геометрию башни для оптимальной ориентации

    Args:
        centers: DataFrame с центрами секций (x, y, z)
        standing_point: Словарь с координатами точки standing (используется как fallback)
        lower_belt_points: DataFrame с точками нижнего пояса для определения ориентации (опционально)

    Returns:
        Словарь с параметрами локальной системы координат:
        {
            'origin': (x, y, z),  # Центр нижней секции
            'x_axis': (x, y, 0),  # Единичный вектор оси X
            'y_axis': (x, y, 0),  # Единичный вектор оси Y
            'valid': bool
        }
    """
    if centers.empty or len(centers) < 1:
        return {
            'origin': (0.0, 0.0, 0.0),
            'x_axis': (1.0, 0.0, 0.0),
            'y_axis': (0.0, 1.0, 0.0),
            'valid': False
        }

    # Находим центр нижней секции (минимальная Z)
    bottom_idx = centers['z'].idxmin()
    bottom_center = centers.loc[bottom_idx]
    origin = np.array([bottom_center['x'], bottom_center['y'], bottom_center['z']])

    # ПРИОРИТЕТ 1: Ориентируем оси по направлению к первой точке стояния
    if standing_point is not None:
        station_pos = np.array([
            standing_point.get('x', 0.0),
            standing_point.get('y', 0.0),
            standing_point.get('z', 0.0),
        ])

        direction_xy = origin[:2] - station_pos[:2]
        norm_dir = np.linalg.norm(direction_xy)
        if np.isfinite(norm_dir) and norm_dir > 1e-6:
            x_axis_2d = direction_xy / norm_dir
            y_axis_2d = np.array([-x_axis_2d[1], x_axis_2d[0]])

            x_axis = np.array([x_axis_2d[0], x_axis_2d[1], 0.0])
            y_axis = np.array([y_axis_2d[0], y_axis_2d[1], 0.0])

            logger.info(
                "Локальная СК: ось X направлена от точки стояния к центру нижней секции"
            )

            return {
                'origin': tuple(origin),
                'x_axis': tuple(x_axis),
                'y_axis': tuple(y_axis),
                'valid': True,
            }

    # ПРИОРИТЕТ 2: Используем главные оси нижнего пояса (если доступны)
    if lower_belt_points is not None and len(lower_belt_points) >= 3:
        try:
            belt_xy = lower_belt_points[['x', 'y']].values
            belt_center_xy = belt_xy.mean(axis=0)
            centered_xy = belt_xy - belt_center_xy

            if len(centered_xy) >= 2:
                cov_matrix = np.cov(centered_xy.T)
                eigenvalues, eigenvectors = np.linalg.eig(cov_matrix)
                idx = eigenvalues.argsort()[::-1]
                eigenvectors = eigenvectors[:, idx]

                x_axis_2d = eigenvectors[:, 0]
                norm_x = np.linalg.norm(x_axis_2d)
                if norm_x > 1e-6:
                    x_axis_2d = x_axis_2d / norm_x
                else:
                    x_axis_2d = np.array([1.0, 0.0])

                y_axis_2d = np.array([-x_axis_2d[1], x_axis_2d[0]])
                x_axis = np.array([x_axis_2d[0], x_axis_2d[1], 0.0])
                y_axis = np.array([y_axis_2d[0], y_axis_2d[1], 0.0])

                logger.info(
                    "Локальная СК: использованы главные оси нижнего пояса (точек: %d)",
                    len(lower_belt_points),
                )

                return {
                    'origin': tuple(origin),
                    'x_axis': tuple(x_axis),
                    'y_axis': tuple(y_axis),
                    'valid': True,
                }
        except Exception as e:
            logger.warning(
                f"Не удалось вычислить главные оси нижнего пояса: {e}, используем fallback"
            )

    # ПРИОРИТЕТ 3: Если ничего не доступно - стандартная ориентация
    logger.warning("Используются стандартные глобальные оси для локальной СК")
    return {
        'origin': tuple(origin),
        'x_axis': (1.0, 0.0, 0.0),
        'y_axis': (0.0, 1.0, 0.0),
        'valid': True,
    }


def calculate_vertical_deviation_with_local_cs(
    centers: pd.DataFrame,
    axis: dict[str, Any],
    local_cs: dict[str, Any],
    standing_point: dict[str, float]
) -> pd.DataFrame:
    """
    Вычисляет отклонения от вертикали в локальной системе координат

    Новая логика:
    1. Строим ось башни через центры секций
    2. Раскладываем отклонения на оси X и Y локальной системы координат
    3. Ось X: проекция на линию от точки стояния через центр нижней секции
    4. Ось Y: перпендикулярно оси X в горизонтальной плоскости

    Args:
        centers: DataFrame с центрами секций
        axis: Параметры аппроксимированной оси башни
        local_cs: Параметры локальной системы координат
        standing_point: Координаты точки стояния

    Returns:
        DataFrame с добавленными колонками 'deviation', 'deviation_x', 'deviation_y'
    """
    if not axis['valid'] or centers.empty or not local_cs['valid']:
        result = centers.copy()
        result['deviation'] = 0.0
        result['deviation_x'] = 0.0
        result['deviation_y'] = 0.0
        return result

    result = centers.copy()
    deviations = []
    deviations_x = []
    deviations_y = []

    local_origin = np.array(local_cs['origin'])
    x_axis = np.array(local_cs['x_axis'])
    y_axis = np.array(local_cs['y_axis'])

    for idx, row in result.iterrows():
        point = np.array([row['x'], row['y'], row['z']])

        # Вычисляем точку на оси башни на высоте текущей секции
        z_diff = row['z'] - axis['z0']
        axis_point = np.array([
            axis['x0'] + axis['dx'] * z_diff,
            axis['y0'] + axis['dy'] * z_diff,
            row['z']
        ])

        # Вектор отклонения от оси
        deviation_vector = point - axis_point

        # Проецируем отклонение на оси локальной СК (только в XY плоскости)
        deviation_vector[2] = 0  # Обнуляем Z компоненту

        # Раскладываем на оси локальной СК
        deviation_x = np.dot(deviation_vector, x_axis)
        deviation_y = np.dot(deviation_vector, y_axis)

        # Суммарное горизонтальное отклонение
        total_deviation = np.linalg.norm(deviation_vector)

        deviations.append(total_deviation)
        deviations_x.append(deviation_x)
        deviations_y.append(deviation_y)

    result['deviation'] = deviations
    result['deviation_x'] = deviations_x
    result['deviation_y'] = deviations_y

    return result


def point_to_line_distance_3d(point: tuple[float, float, float],
                               line_point: tuple[float, float, float],
                               line_direction: tuple[float, float, float]) -> float:
    """
    Вычисляет расстояние от точки до прямой в 3D

    Args:
        point: Координаты точки (x, y, z)
        line_point: Точка на прямой
        line_direction: Направляющий вектор прямой

    Returns:
        Расстояние от точки до прямой
    """
    p = np.array(point)
    l0 = np.array(line_point)
    l = np.array(line_direction)

    # Нормализуем направляющий вектор
    l = l / np.linalg.norm(l)

    # Вектор от точки на прямой до точки
    v = p - l0

    # Проекция v на направление прямой
    proj = np.dot(v, l) * l

    # Перпендикулярная составляющая
    perp = v - proj

    # Расстояние
    distance = np.linalg.norm(perp)

    return distance


def distance_to_line_3d(
    point: tuple[float, float, float],
    line_point: tuple[float, float, float],
    line_direction: tuple[float, float, float],
) -> float:
    """
    Совместимый публичный алиас для расчета расстояния от точки до прямой в 3D.
    """
    return point_to_line_distance_3d(point, line_point, line_direction)


def calculate_vertical_deviation(centers: pd.DataFrame, axis: dict[str, Any]) -> pd.DataFrame:
    """
    Вычисляет горизонтальные отклонения центров от оси (отклонение от вертикали)

    Args:
        centers: DataFrame с центрами поясов
        axis: Параметры аппроксимированной оси

    Returns:
        DataFrame с добавленной колонкой 'deviation'
    """
    if not axis['valid'] or centers.empty:
        centers['deviation'] = 0.0
        return centers

    # Оптимизированная версия с векторными операциями numpy
    result = centers.copy()

    # Векторные вычисления для всех точек одновременно
    z_diff = result['z'].values - axis['z0']
    x_axis = axis['x0'] + axis['dx'] * z_diff
    y_axis = axis['y0'] + axis['dy'] * z_diff

    # Горизонтальное отклонение (векторно)
    x_diff = result['x'].values - x_axis
    y_diff = result['y'].values - y_axis
    deviations = np.sqrt(x_diff**2 + y_diff**2)

    result['deviation'] = deviations
    return result


def calculate_straightness_deviation(
    centers: pd.DataFrame,
    tower_parts_info: dict[str, Any] | None = None
) -> pd.DataFrame:
    """
    Вычисляет стрелу прогиба (отклонение от прямолинейности)

    Базовая линия строится по нижней и верхней секции части башни,
    затем измеряется расстояние каждого центра пояса до этой линии.

    Для составной башни расчет выполняется отдельно для каждой части.
    Точки на нижней и верхней секции каждой части всегда имеют отклонение 0,
    так как они являются опорными точками для построения базовой линии.

    Args:
        centers: DataFrame с центрами поясов (может содержать колонку 'tower_part')
        tower_parts_info: Информация о частях башни (опционально):
            {
                'split_height': float,  # Высота раздвоения
                'parts': [  # Список частей
                    {'part_number': 1, 'faces': 4, ...},
                    {'part_number': 2, 'faces': 3, ...}
                ]
            }

    Returns:
        DataFrame с добавленной колонкой 'straightness_deviation'
    """
    if len(centers) < 2:
        centers['straightness_deviation'] = 0.0
        centers['section_length'] = 0.0
        return centers

    result = centers.copy()
    result['straightness_deviation'] = 0.0
    result['section_length'] = 0.0

    # Проверяем, является ли башня составной
    part_numbers: list[int] = []
    if tower_parts_info and tower_parts_info.get('parts'):
        part_numbers = [
            int(part.get('part_number'))
            for part in tower_parts_info['parts']
            if part.get('part_number') is not None
        ]
    if not part_numbers and (
        ('tower_part_memberships' in centers.columns and centers['tower_part_memberships'].notna().any())
        or ('tower_part' in centers.columns and centers['tower_part'].notna().any())
    ):
        unique_parts = set()
        if 'tower_part_memberships' in centers.columns:
            for value in centers['tower_part_memberships'].dropna():
                unique_parts.update(_decode_part_memberships(value))
        if not unique_parts and 'tower_part' in centers.columns:
            unique_parts.update(centers['tower_part'].dropna().unique())
        part_numbers = [int(part) for part in unique_parts if part is not None]
    part_numbers = sorted(set(part_numbers))

    if part_numbers:
        logger.info(f"Прямолинейность: обработка частей {part_numbers}")
        processed_parts = 0
        for part_num in part_numbers:
            part_centers = _filter_points_by_part(centers, part_num)
            if len(part_centers) < 2:
                logger.warning(f"Часть {part_num}: недостаточно точек для расчета прямолинейности ({len(part_centers)})")
                continue
            processed_parts += 1

            # Сортируем по высоте
            sorted_part_centers = part_centers.sort_values('z').reset_index(drop=True)

            # Берем нижнюю и верхнюю секцию части как опорные точки
            # Находим минимальную и максимальную высоту для части (это нижняя и верхняя секция)
            min_height = sorted_part_centers['z'].min()
            max_height = sorted_part_centers['z'].max()

            # Находим центры поясов на нижней и верхней секции (с допуском 0.1 м)
            height_tolerance = 0.1
            bottom_section_centers = sorted_part_centers[
                np.abs(sorted_part_centers['z'] - min_height) <= height_tolerance
            ]
            top_section_centers = sorted_part_centers[
                np.abs(sorted_part_centers['z'] - max_height) <= height_tolerance
            ]

            # Используем средний центр нижней и верхней секции
            if len(bottom_section_centers) > 0:
                bottom = {
                    'x': bottom_section_centers['x'].mean(),
                    'y': bottom_section_centers['y'].mean(),
                    'z': bottom_section_centers['z'].mean()
                }
            else:
                bottom = sorted_part_centers.iloc[0]

            if len(top_section_centers) > 0:
                top = {
                    'x': top_section_centers['x'].mean(),
                    'y': top_section_centers['y'].mean(),
                    'z': top_section_centers['z'].mean()
                }
            else:
                top = sorted_part_centers.iloc[-1]

            # Базовая линия прямолинейности для этой части
            base_line_point = (bottom['x'], bottom['y'], bottom['z'])
            dx = top['x'] - bottom['x']
            dy = top['y'] - bottom['y']
            dz = top['z'] - bottom['z']
            base_line_direction = (dx, dy, dz)

            if np.linalg.norm(base_line_direction) < 1e-6:
                logger.warning(f"Часть {part_num}: опорные точки слишком близки")
                continue

            # Длина секции (для нормативов)
            section_length = dz

            # Оптимизированная версия с векторными операциями
            points_array = sorted_part_centers[['x', 'y', 'z']].values
            line_point_arr = np.array(base_line_point)
            line_dir_arr = np.array(base_line_direction)

            # Нормализуем направляющий вектор
            line_dir_norm = line_dir_arr / np.linalg.norm(line_dir_arr)

            # Векторные вычисления расстояний для всех точек части
            v = points_array - line_point_arr
            proj = np.dot(v, line_dir_norm)[:, np.newaxis] * line_dir_norm
            perp = v - proj
            deviations = np.linalg.norm(perp, axis=1)

            # Обновляем результаты для точек этой части
            for idx, orig_idx in enumerate(sorted_part_centers.index):
                # Проверяем, является ли точка нижней или верхней секцией
                point_z = sorted_part_centers.iloc[idx]['z']
                is_bottom_section = np.abs(point_z - min_height) <= height_tolerance
                is_top_section = np.abs(point_z - max_height) <= height_tolerance

                # Точки на нижней и верхней секции всегда имеют отклонение 0
                if is_bottom_section or is_top_section:
                    result.loc[orig_idx, 'straightness_deviation'] = 0.0
                else:
                    result.loc[orig_idx, 'straightness_deviation'] = deviations[idx]
                result.loc[orig_idx, 'section_length'] = section_length

            logger.info(f"Часть {part_num}: рассчитана прямолинейность для {len(part_centers)} поясов, длина секции: {section_length:.3f} м")

        if processed_parts == 0:
            logger.warning("Ни для одной части не удалось вычислить прямолинейность, выполняем расчет по всей башне")
        else:
            return result

    split_height = None
    if tower_parts_info and tower_parts_info.get('split_height') is not None:
        split_height = tower_parts_info['split_height']
        logger.info(f"Расчет прямолинейности по высоте раздвоения: {split_height:.3f} м")

    if split_height is not None:
        # Раздельный расчет для нижней/верхней части (совместимость со старыми данными)
        for part_num, comparator in enumerate([lambda z: z < split_height, lambda z: z >= split_height], start=1):
            part_centers = centers[comparator(centers['z'])].copy()
            if len(part_centers) < 2:
                logger.warning(f"Часть {part_num}: недостаточно точек для расчета прямолинейности ({len(part_centers)})")
                continue

            sorted_part_centers = part_centers.sort_values('z').reset_index(drop=True)

            # Берем нижнюю и верхнюю секцию части как опорные точки
            min_height = sorted_part_centers['z'].min()
            max_height = sorted_part_centers['z'].max()

            # Находим центры поясов на нижней и верхней секции (с допуском 0.1 м)
            height_tolerance = 0.1
            bottom_section_centers = sorted_part_centers[
                np.abs(sorted_part_centers['z'] - min_height) <= height_tolerance
            ]
            top_section_centers = sorted_part_centers[
                np.abs(sorted_part_centers['z'] - max_height) <= height_tolerance
            ]

            # Используем средний центр нижней и верхней секции
            if len(bottom_section_centers) > 0:
                bottom = {
                    'x': bottom_section_centers['x'].mean(),
                    'y': bottom_section_centers['y'].mean(),
                    'z': bottom_section_centers['z'].mean()
                }
            else:
                bottom = sorted_part_centers.iloc[0]

            if len(top_section_centers) > 0:
                top = {
                    'x': top_section_centers['x'].mean(),
                    'y': top_section_centers['y'].mean(),
                    'z': top_section_centers['z'].mean()
                }
            else:
                top = sorted_part_centers.iloc[-1]

            base_line_point = (bottom['x'], bottom['y'], bottom['z'])
            dx = top['x'] - bottom['x']
            dy = top['y'] - bottom['y']
            dz = top['z'] - bottom['z']
            base_line_direction = (dx, dy, dz)

            if np.linalg.norm(base_line_direction) < 1e-6:
                logger.warning(f"Часть {part_num}: опорные точки слишком близки")
                continue

            section_length = dz
            points_array = sorted_part_centers[['x', 'y', 'z']].values
            line_point_arr = np.array(base_line_point)
            line_dir_arr = np.array(base_line_direction)
            line_dir_norm = line_dir_arr / np.linalg.norm(line_dir_arr)
            v = points_array - line_point_arr
            proj = np.dot(v, line_dir_norm)[:, np.newaxis] * line_dir_norm
            perp = v - proj
            deviations = np.linalg.norm(perp, axis=1)

            # Определяем высоты нижней и верхней секции для этой части
            part_min_height = sorted_part_centers['z'].min()
            part_max_height = sorted_part_centers['z'].max()
            height_tolerance = 0.1

            for idx, orig_idx in enumerate(sorted_part_centers.index):
                # Проверяем, является ли точка нижней или верхней секцией
                point_z = sorted_part_centers.iloc[idx]['z']
                is_bottom_section = np.abs(point_z - part_min_height) <= height_tolerance
                is_top_section = np.abs(point_z - part_max_height) <= height_tolerance

                # Точки на нижней и верхней секции всегда имеют отклонение 0
                if is_bottom_section or is_top_section:
                    result.loc[orig_idx, 'straightness_deviation'] = 0.0
                else:
                    result.loc[orig_idx, 'straightness_deviation'] = deviations[idx]
                result.loc[orig_idx, 'section_length'] = section_length

        return result
    else:
        # Обычный расчет для всей башни
        sorted_centers = result.sort_values('z').reset_index(drop=True)

        # Берем нижнюю и верхнюю секцию как опорные точки
        min_height = sorted_centers['z'].min()
        max_height = sorted_centers['z'].max()

        # Находим центры поясов на нижней и верхней секции (с допуском 0.1 м)
        height_tolerance = 0.1
        bottom_section_centers = sorted_centers[
            np.abs(sorted_centers['z'] - min_height) <= height_tolerance
        ]
        top_section_centers = sorted_centers[
            np.abs(sorted_centers['z'] - max_height) <= height_tolerance
        ]

        # Используем средний центр нижней и верхней секции
        if len(bottom_section_centers) > 0:
            bottom = {
                'x': bottom_section_centers['x'].mean(),
                'y': bottom_section_centers['y'].mean(),
                'z': bottom_section_centers['z'].mean()
            }
        else:
            bottom = sorted_centers.iloc[0]

        if len(top_section_centers) > 0:
            top = {
                'x': top_section_centers['x'].mean(),
                'y': top_section_centers['y'].mean(),
                'z': top_section_centers['z'].mean()
            }
        else:
            top = sorted_centers.iloc[-1]

        # Базовая линия прямолинейности
        base_line_point = (bottom['x'], bottom['y'], bottom['z'])
        dx = top['x'] - bottom['x']
        dy = top['y'] - bottom['y']
        dz = top['z'] - bottom['z']
        base_line_direction = (dx, dy, dz)

        # Длина секции (для нормативов)
        section_length = dz

        # Оптимизированная версия с векторными операциями
        points_array = sorted_centers[['x', 'y', 'z']].values
        line_point_arr = np.array(base_line_point)
        line_dir_arr = np.array(base_line_direction)

        # Нормализуем направляющий вектор
        line_dir_norm = line_dir_arr / np.linalg.norm(line_dir_arr)

        # Векторные вычисления расстояний для всех точек
        v = points_array - line_point_arr
        proj = np.dot(v, line_dir_norm)[:, np.newaxis] * line_dir_norm
        perp = v - proj
        deviations = np.linalg.norm(perp, axis=1)

        # Определяем высоты нижней и верхней секции
        min_height = sorted_centers['z'].min()
        max_height = sorted_centers['z'].max()
        height_tolerance = 0.1

        # Обновляем результаты
        for idx, orig_idx in enumerate(sorted_centers.index):
            # Проверяем, является ли точка нижней или верхней секцией
            point_z = sorted_centers.iloc[idx]['z']
            is_bottom_section = np.abs(point_z - min_height) <= height_tolerance
            is_top_section = np.abs(point_z - max_height) <= height_tolerance

            # Точки на нижней и верхней секции всегда имеют отклонение 0
            if is_bottom_section or is_top_section:
                result.loc[orig_idx, 'straightness_deviation'] = 0.0
            else:
                result.loc[orig_idx, 'straightness_deviation'] = deviations[idx]
            result.loc[orig_idx, 'section_length'] = section_length

    return result


def _apply_straightness_for_subset(
    result: pd.DataFrame,
    subset: pd.DataFrame,
    height_tolerance: float = 0.1,
) -> None:
    """Write straightness deviations for a sorted subset without losing source indices."""
    if subset.empty:
        return

    sorted_subset = subset.sort_values('z')
    if len(sorted_subset) < 2:
        result.loc[sorted_subset.index, 'straightness_deviation'] = 0.0
        result.loc[sorted_subset.index, 'section_length'] = 0.0
        return

    min_height = float(sorted_subset['z'].min())
    max_height = float(sorted_subset['z'].max())
    bottom_section = sorted_subset[np.abs(sorted_subset['z'] - min_height) <= height_tolerance]
    top_section = sorted_subset[np.abs(sorted_subset['z'] - max_height) <= height_tolerance]

    bottom = (
        bottom_section[['x', 'y', 'z']].mean().to_numpy(dtype=float)
        if not bottom_section.empty
        else sorted_subset.iloc[0][['x', 'y', 'z']].to_numpy(dtype=float)
    )
    top = (
        top_section[['x', 'y', 'z']].mean().to_numpy(dtype=float)
        if not top_section.empty
        else sorted_subset.iloc[-1][['x', 'y', 'z']].to_numpy(dtype=float)
    )

    line_direction = top - bottom
    line_length = float(np.linalg.norm(line_direction))
    if not np.isfinite(line_length) or line_length < 1e-6:
        result.loc[sorted_subset.index, 'straightness_deviation'] = 0.0
        result.loc[sorted_subset.index, 'section_length'] = 0.0
        return

    points_array = sorted_subset[['x', 'y', 'z']].to_numpy(dtype=float)
    line_dir_norm = line_direction / line_length
    vectors = points_array - bottom
    projections = np.dot(vectors, line_dir_norm)[:, np.newaxis] * line_dir_norm
    perpendiculars = vectors - projections
    deviations = np.linalg.norm(perpendiculars, axis=1)

    support_mask = (
        np.abs(sorted_subset['z'].to_numpy(dtype=float) - min_height) <= height_tolerance
    ) | (
        np.abs(sorted_subset['z'].to_numpy(dtype=float) - max_height) <= height_tolerance
    )
    deviations[support_mask] = 0.0

    result.loc[sorted_subset.index, 'straightness_deviation'] = deviations
    result.loc[sorted_subset.index, 'section_length'] = abs(float(top[2] - bottom[2]))


def calculate_straightness_deviation(
    centers: pd.DataFrame,
    tower_parts_info: dict[str, Any] | None = None
) -> pd.DataFrame:
    """Calculate axis straightness on section centers without resetting source indices."""
    result = centers.copy()
    if len(result) < 2:
        result['straightness_deviation'] = 0.0
        result['section_length'] = 0.0
        return result

    result['straightness_deviation'] = 0.0
    result['section_length'] = 0.0

    part_numbers: list[int] = []
    if tower_parts_info and tower_parts_info.get('parts'):
        part_numbers = [
            int(part.get('part_number'))
            for part in tower_parts_info['parts']
            if part.get('part_number') is not None
        ]

    if not part_numbers and (
        ('tower_part_memberships' in centers.columns and centers['tower_part_memberships'].notna().any())
        or ('tower_part' in centers.columns and centers['tower_part'].notna().any())
    ):
        unique_parts = set()
        if 'tower_part_memberships' in centers.columns:
            for value in centers['tower_part_memberships'].dropna():
                unique_parts.update(_decode_part_memberships(value))
        if not unique_parts and 'tower_part' in centers.columns:
            unique_parts.update(centers['tower_part'].dropna().unique())
        part_numbers = [int(part) for part in unique_parts if part is not None]

    part_numbers = sorted(set(part_numbers))
    if part_numbers:
        processed_parts = 0
        for part_num in part_numbers:
            part_centers = _filter_points_by_part(centers, part_num)
            if len(part_centers) < 2:
                continue
            processed_parts += 1
            _apply_straightness_for_subset(result, part_centers)

        if processed_parts > 0:
            return result

    split_height = None
    if tower_parts_info and tower_parts_info.get('split_height') is not None:
        split_height = float(tower_parts_info['split_height'])

    if split_height is not None:
        lower_part = centers[centers['z'] < split_height].copy()
        upper_part = centers[centers['z'] >= split_height].copy()
        if len(lower_part) >= 2:
            _apply_straightness_for_subset(result, lower_part)
        if len(upper_part) >= 2:
            _apply_straightness_for_subset(result, upper_part)
        return result

    _apply_straightness_for_subset(result, centers)
    return result


def process_tower_data(
    points: pd.DataFrame,
    height_tolerance: float = 0.1,
    center_method: str = 'mean',
    use_assigned_belts: bool | None = None,
    section_grouping_mode: str = SECTION_GROUPING_HEIGHT_LEVELS,
    use_cache: bool = True
) -> dict[str, Any]:
    """
    Полный цикл обработки данных мачты (универсальный для любой формы башни)

    Универсальный алгоритм работает для:
    - Любого количества граней (3, 4, n)
    - Любой формы (призма, усеченная призма, цилиндр и т.п.)
    - Не требует знания количества граней или формы

    Args:
        points: DataFrame с исходными точками
        height_tolerance: Допуск группировки по высоте
        center_method: Метод расчета центра пояса
        use_assigned_belts: Использовать назначенные пользователем пояса
        use_cache: Использовать кэширование результатов

    Returns:
        Словарь с результатами обработки
    """
    required_cols = {'x', 'y', 'z'}
    if points is None or points.empty or not required_cols.issubset(points.columns):
        return {
            'valid': False,
            'belts': {},
            'centers': pd.DataFrame(),
            'axis': {'valid': False},
            'local_cs': None,
            'standing_point': {},
            'tower_parts_info': None,
            'straightness_profiles': [],
            'straightness_summary': {'max_deflection_mm': 0.0, 'passed': 0, 'failed': 0, 'violations': []},
        }

    # Проверяем кэш
    resolved_grouping_mode = resolve_section_grouping_mode(section_grouping_mode, use_assigned_belts)
    cache_key = None
    if use_cache:
        cache_key = _get_cache_key(points, height_tolerance, center_method, resolved_grouping_mode)
        cached_result = _calculation_cache.get(cache_key)
        if cached_result:
            if cached_result.get('valid', False):
                if cache_key in _cache_access_order:
                    _cache_access_order.remove(cache_key)
                _cache_access_order.append(cache_key)
                logger.debug("Использован кэшированный результат расчетов")
                return cached_result
            else:
                logger.debug("Удаляем невалидный кеш расчета и пересчитываем")
                _calculation_cache.pop(cache_key, None)
                if cache_key in _cache_access_order:
                    _cache_access_order.remove(cache_key)

    # Группируем точки по поясам (используя назначенные или автогруппировку)
    belts = group_points_by_height(
        points,
        tolerance=height_tolerance,
        section_grouping_mode=resolved_grouping_mode,
    )

    # Вычисляем центры поясов
    centers_list = []
    for section_index, (height, belt_points) in enumerate(sorted(belts.items()), start=1):
        x_c, y_c, z_c = calculate_belt_center(belt_points, center_method)
        part_memberships = set()
        if 'tower_part_memberships' in belt_points.columns:
            for value in belt_points['tower_part_memberships'].dropna():
                part_memberships.update(_decode_part_memberships(value))
        if not part_memberships and 'tower_part' in belt_points.columns:
            part_memberships.update(belt_points['tower_part'].dropna().unique())
        if 'is_part_boundary' in belt_points.columns:
            for _, point_row in belt_points.iterrows():
                if bool(point_row.get('is_part_boundary', False)):
                    base_value = point_row.get('tower_part', 1)
                    try:
                        base_part = int(base_value)
                    except (TypeError, ValueError):
                        base_part = 1
                    if base_part <= 0:
                        base_part = 1
                    part_memberships.add(base_part)
                    part_memberships.add(base_part + 1)
        centers_list.append({
            'x': x_c,
            'y': y_c,
            'z': z_c,
            'section_index': section_index,
            'section_level': float(height),
            'belt_height': height,
            'points_count': len(belt_points),
            'tower_part': min(part_memberships) if part_memberships else None,
            'tower_part_memberships': json.dumps(sorted(part_memberships), ensure_ascii=False) if part_memberships else None
        })

    centers = pd.DataFrame(centers_list)

    # Дедупликация центров по высоте для составных башен
    # Логика: для каждой абсолютной высоты оставляем только один центр
    # Самая нижняя секция, промежуточные секции части, верхняя секция части,
    # далее нижняя секция следующей части пропускается (совпадает с верхней предыдущей)
    if (
        resolved_grouping_mode == SECTION_GROUPING_ASSIGNED_SECTIONS
        and not centers.empty
        and len(centers) > 1
    ):
        # Сортируем по высоте
        centers = centers.sort_values('z').reset_index(drop=True)

        # Группируем центры по высоте с допуском
        # Для центров на одной высоте (с допуском) оставляем только один
        deduplicated_centers = []
        height_tolerance_dedup = height_tolerance  # Используем тот же допуск, что и для группировки

        i = 0
        processed_indices = set()
        while i < len(centers):
            if i in processed_indices:
                i += 1
                continue

            current_row = centers.iloc[i]
            current_z = current_row['z']

            # Находим все центры на этой же высоте (с допуском)
            same_height_mask = np.abs(centers['z'].values - current_z) <= height_tolerance_dedup
            same_height_positions = np.where(same_height_mask)[0].tolist()

            if len(same_height_positions) > 1:
                # Если есть несколько центров на одной высоте, усредняем координаты
                same_height_rows = centers.iloc[same_height_positions]
                averaged_center = {
                    'x': float(same_height_rows['x'].mean()),
                    'y': float(same_height_rows['y'].mean()),
                    'z': float(same_height_rows['z'].mean()),  # Средняя высота
                    'belt_height': float(same_height_rows['belt_height'].mean()),
                    'points_count': int(same_height_rows['points_count'].sum()),
                    'tower_part': int(same_height_rows['tower_part'].min()) if same_height_rows['tower_part'].notna().any() else None,
                    'tower_part_memberships': current_row.get('tower_part_memberships')  # Берем из первого
                }
                deduplicated_centers.append(averaged_center)
                logger.debug(f"Объединено {len(same_height_positions)} центров на высоте ~{current_z:.3f}м в один")
                # Отмечаем все обработанные индексы
                processed_indices.update(same_height_positions)
                # Переходим к следующему необработанному индексу
                i = max(same_height_positions) + 1
            else:
                # Один центр на этой высоте - просто добавляем
                deduplicated_centers.append(current_row.to_dict())
                processed_indices.add(i)
                i += 1

        if len(deduplicated_centers) < len(centers):
            logger.info(f"Дедупликация центров: было {len(centers)}, стало {len(deduplicated_centers)} "
                       f"(удалено {len(centers) - len(deduplicated_centers)} дубликатов)")
            centers = pd.DataFrame(deduplicated_centers)
            centers = centers.sort_values('z').reset_index(drop=True)

    if not centers.empty:
        centers = centers.sort_values('z').reset_index(drop=True)
        centers['section_index'] = np.arange(1, len(centers) + 1)
        if 'section_level' not in centers.columns:
            centers['section_level'] = centers['z']

    if centers.empty:
        return {
            'belts': belts,
            'centers': centers,
            'axis': {'valid': False},
            'vertical_deviations': centers,
            'straightness_deviations': centers,
            'straightness_profiles': [],
            'straightness_summary': {'max_deflection_mm': 0.0, 'passed': 0, 'failed': 0, 'violations': []},
            'valid': False
        }

    # Аппроксимируем ось башни
    axis = approximate_tower_axis(centers)

    # Ищем точку standing для новой системы координат (используется как fallback)
    standing_point = {'x': 0.0, 'y': 0.0, 'z': 0.0}  # По умолчанию
    if 'is_station' in points.columns:
        station_mask = _build_is_station_mask(points['is_station'])
        station_points = points[station_mask]
        if len(station_points) > 0:
            standing_point = {
                'x': station_points.iloc[0]['x'],
                'y': station_points.iloc[0]['y'],
                'z': station_points.iloc[0]['z']
            }
            logger.info(f"Найдена точка standing: {standing_point}")

    # Получаем точки нижнего пояса для определения ориентации локальной СК
    # (используется для универсального расчета, не зависящего от формы башни)
    lower_belt_points = None
    if belts:
        min_height = min(belts.keys())
        lower_belt_points = belts[min_height]
        logger.info(f"Используем {len(lower_belt_points)} точек нижнего пояса для универсальной ориентации локальной СК")

    # Вычисляем локальную систему координат (универсально для любой формы башни)
    local_cs = calculate_local_coordinate_system(centers, standing_point, lower_belt_points)

    # Вычисляем отклонения от вертикали с новой логикой
    centers_with_vertical = calculate_vertical_deviation_with_local_cs(centers, axis, local_cs, standing_point)

    # Извлекаем информацию о частях башни из исходных данных
    tower_parts_info = None
    working_points = points[_build_working_tower_mask(points)].copy()
    has_memberships = 'tower_part_memberships' in working_points.columns and working_points['tower_part_memberships'].notna().any()
    has_numeric_parts = 'tower_part' in working_points.columns and working_points['tower_part'].notna().any()
    if has_memberships or has_numeric_parts:
        unique_parts = set()
        if has_memberships:
            for value in working_points['tower_part_memberships'].dropna():
                unique_parts.update(_decode_part_memberships(value))
        if has_numeric_parts:
            unique_parts.update(working_points['tower_part'].dropna().unique())
        parts_meta = []
        for part_num in sorted(int(part) for part in unique_parts if part is not None):
            part_points = _filter_points_by_part(working_points, part_num)
            if part_points.empty:
                continue
            faces = part_points['belt'].nunique() if 'belt' in part_points.columns else None
            z_min = float(part_points['z'].min())
            z_max = float(part_points['z'].max())
            parts_meta.append({
                'part_number': part_num,
                'faces': faces,
                'z_min': z_min,
                'z_max': z_max
            })
        if parts_meta:
            tower_parts_info = {'parts': parts_meta}
            split_heights = []
            for idx in range(len(parts_meta) - 1):
                lower = parts_meta[idx]['z_max']
                upper = parts_meta[idx + 1]['z_min']
                split_heights.append((lower + upper) / 2.0)
            if split_heights:
                tower_parts_info['split_heights'] = split_heights
                tower_parts_info['split_height'] = split_heights[0]
            else:
                tower_parts_info['split_height'] = None
            logger.info(f"Обнаружена составная башня: частей={len(parts_meta)}, границы={split_heights if split_heights else 'нет'}")

    # Вычисляем стрелы прогиба (с учетом частей, если башня составная)
    # Keep straightness isolated from verticality: no implicit part detection here.
    if False and (tower_parts_info is None or len(tower_parts_info.get('parts', [])) <= 1) and 'belt' in working_points.columns:  # disabled on purpose
        numeric_belts = pd.to_numeric(working_points['belt'], errors='coerce').dropna()
        face_count = int(numeric_belts.nunique()) if not numeric_belts.empty else 0
        split_height = estimate_composite_split_height(
            working_points,
            num_belts=max(3, face_count or 4),
        )
        if split_height is not None:
            lower_mask = working_points['z'] < float(split_height)
            upper_mask = working_points['z'] >= float(split_height)
            if lower_mask.any() and upper_mask.any():
                points = points.copy()
                centers_with_vertical = centers_with_vertical.copy()
                points['tower_part'] = np.where(points['z'] < float(split_height), 1, 2)
                centers_with_vertical['tower_part'] = np.where(centers_with_vertical['z'] < float(split_height), 1, 2)
                points['tower_part_memberships'] = np.where(
                    points['tower_part'] == 1,
                    '[1]',
                    '[2]',
                )
                centers_with_vertical['tower_part_memberships'] = np.where(
                    centers_with_vertical['tower_part'] == 1,
                    '[1]',
                    '[2]',
                )
                tower_parts_info = {
                    'parts': [
                        {
                            'part_number': 1,
                            'faces': face_count or None,
                            'z_min': float(working_points.loc[lower_mask, 'z'].min()),
                            'z_max': float(working_points.loc[lower_mask, 'z'].max()),
                        },
                        {
                            'part_number': 2,
                            'faces': face_count or None,
                            'z_min': float(working_points.loc[upper_mask, 'z'].min()),
                            'z_max': float(working_points.loc[upper_mask, 'z'].max()),
                        },
                    ],
                    'split_height': float(split_height),
                    'split_heights': [float(split_height)],
                    'auto_detected': True,
                }
                logger.info("Автоопределена составная башня для прямолинейности: split_height=%.3f м", float(split_height))
    centers_with_straightness = calculate_straightness_deviation(centers_with_vertical, tower_parts_info)
    straightness_profiles = build_straightness_profiles(points, tower_parts_info)
    straightness_summary = _summarize_straightness_profiles(straightness_profiles)

    result = {
        'belts': belts,
        'centers': centers_with_straightness,
        'axis': axis,
        'local_cs': local_cs,
        'standing_point': standing_point,
        'tower_parts_info': tower_parts_info,
        'section_grouping_mode': resolved_grouping_mode,
        'straightness_profiles': straightness_profiles,
        'straightness_summary': straightness_summary,
        'valid': True
    }

    # Сохраняем в кэш (с ограничением размера и LRU стратегией)
    if use_cache and cache_key is not None:
        cache_key = _get_cache_key(points, height_tolerance, center_method, resolved_grouping_mode)
        if len(_calculation_cache) >= _cache_max_size:
            # Удаляем самую старую запись (LRU - Least Recently Used)
            if _cache_access_order:
                oldest_key = _cache_access_order.pop(0)
                if oldest_key in _calculation_cache:
                    del _calculation_cache[oldest_key]
                    logger.debug(f"Удалена старая запись из кэша (LRU): {oldest_key[:20]}...")
            else:
                # Fallback: если список пуст, удаляем первую запись
                oldest_key = next(iter(_calculation_cache))
                del _calculation_cache[oldest_key]

        # Добавляем новую запись
        _calculation_cache[cache_key] = result
        # Обновляем порядок доступа
        if cache_key in _cache_access_order:
            _cache_access_order.remove(cache_key)
        _cache_access_order.append(cache_key)
        logger.debug(f"Результат сохранен в кэш (размер кэша: {len(_calculation_cache)})")

    return result

