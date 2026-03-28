"""
РњРѕРґСѓР»СЊ РјР°С‚РµРјР°С‚РёС‡РµСЃРєРёС… СЂР°СЃС‡РµС‚РѕРІ РґР»СЏ Р°РЅР°Р»РёР·Р° РІРµСЂС‚РёРєР°Р»СЊРЅРѕСЃС‚Рё Рё РїСЂСЏРјРѕР»РёРЅРµР№РЅРѕСЃС‚Рё РјР°С‡С‚
"""

import copy
import hashlib
import json
import logging
from typing import Any, Literal, Union

import numpy as np
import pandas as pd
from scipy import stats

from core.import_grouping import estimate_composite_split_height
from core.point_utils import (
    build_flag_mask as _build_flag_mask,
)
from core.point_utils import (
    build_is_station_mask as _build_is_station_mask,
)
from core.point_utils import (
    build_working_tower_mask as _build_working_tower_mask,
)
from core.point_utils import (
    decode_part_memberships as _decode_part_memberships,
)
from core.point_utils import (
    filter_points_by_part as _filter_points_by_part,
)
from core.section_operations import _build_section_entries
from core.straightness_calculations import build_straightness_profiles

logger = logging.getLogger(__name__)

# РљСЌС€ РґР»СЏ СЂРµР·СѓР»СЊС‚Р°С‚РѕРІ СЂР°СЃС‡РµС‚РѕРІ (РѕРіСЂР°РЅРёС‡РµРЅ РїРѕ СЂР°Р·РјРµСЂСѓ)
_calculation_cache: dict[str, Any] = {}
_cache_access_order: list[str] = []  # РџРѕСЂСЏРґРѕРє РґРѕСЃС‚СѓРїР° РґР»СЏ LRU
_cache_max_size = 50  # РњР°РєСЃРёРјСѓРј 50 Р·Р°РїРёСЃРµР№ РІ РєСЌС€Рµ (СѓРІРµР»РёС‡РµРЅРѕ РґР»СЏ Р»СѓС‡С€РµР№ РїСЂРѕРёР·РІРѕРґРёС‚РµР»СЊРЅРѕСЃС‚Рё)

SECTION_GROUPING_HEIGHT_LEVELS = 'height_levels'
SECTION_GROUPING_ASSIGNED_SECTIONS = 'assigned_sections'
SectionGroupingMode = Literal['height_levels', 'assigned_sections']
_SECTION_GROUPING_MODES = {
    SECTION_GROUPING_HEIGHT_LEVELS,
    SECTION_GROUPING_ASSIGNED_SECTIONS,
}


def _clone_calculation_result(result: dict[str, Any]) -> dict[str, Any]:
    """Return an isolated copy so UI layers cannot mutate cached state."""
    return copy.deepcopy(result)


def invalidate_cache():
    """
    РРЅРІР°Р»РёРґРёСЂСѓРµС‚ РІРµСЃСЊ РєСЌС€ СЂР°СЃС‡РµС‚РѕРІ
    РџРѕР»РµР·РЅРѕ РїСЂРё РёР·РјРµРЅРµРЅРёРё РґР°РЅРЅС‹С… РёР»Рё РїР°СЂР°РјРµС‚СЂРѕРІ
    """
    global _calculation_cache, _cache_access_order
    _calculation_cache.clear()
    _cache_access_order.clear()
    logger.debug("РљСЌС€ СЂР°СЃС‡РµС‚РѕРІ РѕС‡РёС‰РµРЅ")


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
        logger.info("Р ВР В· Р С–РЎР‚РЎС“Р С—Р С—Р С'РЎР‚Р С•Р Р†Р С”Р С' Р С—Р С• РЎРѓР ВµР С”РЎвЂ Р С'РЎРЏР С Р С'РЎРѓР С”Р В»РЎР‹РЎвЂЎР ВµР Р…РЎвЂ№ Р Р…Р ВµРЎР‚Р В°Р В±Р С•РЎвЂЎР С'Р Вµ РЎвЂљР С•РЎвЂЎР С”Р С' Р СР В°РЎвЂЎРЎвЂљРЎвЂ№")

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
    Р'С‹С‡РёСЃР»СЏРµС‚ С†РµРЅС‚СЂ РїРѕСЏСЃР°

    Args:
        points: DataFrame СЃ С‚РѕС‡РєР°РјРё РїРѕСЏСЃР°
        method: РњРµС‚РѕРґ СЂР°СЃС‡РµС‚Р° ('mean' - СЃСЂРµРґРЅРµРµ, 'lsq' - РњРќРљ)

    Returns:
        РљРѕСЂС‚РµР¶ (x_С†РµРЅС‚СЂ, y_С†РµРЅС‚СЂ, z_СЃСЂРµРґРЅСЏСЏ)
    """
    if points.empty:
        return (0.0, 0.0, 0.0)

    if method == 'mean':
        x_center = points['x'].mean()
        y_center = points['y'].mean()
        z_avg = points['z'].mean()
    elif method == 'lsq':
        # Р”Р»СЏ РєСЂСѓРіР»С‹С… РїРѕСЏСЃРѕРІ - Р°РїРїСЂРѕРєСЃРёРјР°С†РёСЏ РѕРєСЂСѓР¶РЅРѕСЃС‚СЊСЋ
        x_center = points['x'].median()
        y_center = points['y'].median()
        z_avg = points['z'].mean()
    else:
        raise ValueError(f"Unknown method: {method}")

    return (x_center, y_center, z_avg)


def approximate_tower_axis(centers: pd.DataFrame) -> dict[str, Union[float, bool]]:
    """
    РЎС‚СЂРѕРёС‚ Р»РёРЅРµР№РЅСѓСЋ Р°РїРїСЂРѕРєСЃРёРјР°С†РёСЋ РѕСЃРё Р±Р°С€РЅРё С‡РµСЂРµР· С†РµРЅС‚СЂС‹ РїРѕСЏСЃРѕРІ

    РћСЃСЊ РїСЂРµРґСЃС‚Р°РІР»СЏРµС‚СЃСЏ РєР°Рє РїСЂСЏРјР°СЏ РІ 3D: (x, y) = (x0, y0) + t*(dx, dy)
    РіРґРµ t РїСЂРѕРїРѕСЂС†РёРѕРЅР°Р»РµРЅ РІС‹СЃРѕС‚Рµ z

    Args:
        centers: DataFrame СЃ С†РµРЅС‚СЂР°РјРё РїРѕСЏСЃРѕРІ (x, y, z)

    Returns:
        РЎР»РѕРІР°СЂСЊ СЃ РїР°СЂР°РјРµС‚СЂР°РјРё РѕСЃРё
    """
    if len(centers) < 2:
        return {
            'x0': 0.0, 'y0': 0.0, 'z0': 0.0,
            'dx': 0.0, 'dy': 0.0, 'dz': 1.0,
            'valid': False
        }

    # Р›РёРЅРµР№РЅР°СЏ СЂРµРіСЂРµСЃСЃРёСЏ x(z) Рё y(z)
    z = centers['z'].values
    x = centers['x'].values
    y = centers['y'].values

    # Р РµРіСЂРµСЃСЃРёСЏ РґР»СЏ x
    slope_x, intercept_x, r_x, p_x, se_x = stats.linregress(z, x)

    # Р РµРіСЂРµСЃСЃРёСЏ РґР»СЏ y
    slope_y, intercept_y, r_y, p_y, se_y = stats.linregress(z, y)

    # z0 - РјРёРЅРёРјР°Р»СЊРЅР°СЏ РІС‹СЃРѕС‚Р° (РѕСЃРЅРѕРІР°РЅРёРµ)
    z0 = z.min()
    x0 = intercept_x + slope_x * z0
    y0 = intercept_y + slope_y * z0

    # Предупреждение при плохом качестве линейной аппроксимации
    warnings = []
    r2_x = r_x ** 2
    r2_y = r_y ** 2
    if r2_x < 0.9 or r2_y < 0.9:
        warnings.append(
            f"Ось башни плохо аппроксимирована прямой "
            f"(R²_x={r2_x:.3f}, R²_y={r2_y:.3f}). "
            f"Возможна значительная кривизна конструкции или выброс данных."
        )

    return {
        'x0': x0,           # Координата X в основании
        'y0': y0,           # Координата Y в основании
        'z0': z0,           # Высота основания
        'dx': slope_x,      # Наклон оси по X
        'dy': slope_y,      # Наклон оси по Y
        'dz': 1.0,          # Направление по Z
        'r_x': r_x,         # Коэффициент корреляции X
        'r_y': r_y,         # Коэффициент корреляции Y
        'r2_x': r2_x,       # Коэффициент детерминации X
        'r2_y': r2_y,       # Коэффициент детерминации Y
        'valid': True,
        'warnings': warnings,
    }


def calculate_local_coordinate_system(
    centers: pd.DataFrame,
    standing_point: dict[str, float] | None,
    lower_belt_points: pd.DataFrame | None = None
) -> dict[str, Union[tuple[float, float, float], bool]]:
    """
    Р'С‹С‡РёСЃР»СЏРµС‚ СѓРЅРёРІРµСЂСЃР°Р»СЊРЅСѓСЋ Р»РѕРєР°Р»СЊРЅСѓСЋ СЃРёСЃС‚РµРјСѓ РєРѕРѕСЂРґРёРЅР°С‚ РґР»СЏ СЂР°СЃС‡РµС‚Р° РІРµСЂС‚РёРєР°Р»СЊРЅРѕСЃС‚Рё

    РђР»РіРѕСЂРёС‚Рј СѓРЅРёРІРµСЂСЃР°Р»РµРЅ РґР»СЏ Р»СЋР±РѕР№ С„РѕСЂРјС‹ Р±Р°С€РЅРё (3-РіСЂР°РЅРЅР°СЏ, 4-РіСЂР°РЅРЅР°СЏ, n-РіСЂР°РЅРЅР°СЏ,
    СѓСЃРµС‡РµРЅРЅР°СЏ РїСЂРёР·РјР°, РїСЂРёР·РјР° Рё С‚.Рї.) Рё РЅРµ Р·Р°РІРёСЃРёС‚ РѕС‚ РєРѕР»РёС‡РµСЃС‚РІР° РіСЂР°РЅРµР№.
    РСЃРїРѕР»СЊР·СѓРµС‚ С‚РѕР»СЊРєРѕ С†РµРЅС‚СЂС‹ СЃРµРєС†РёР№ РґР»СЏ РѕРїСЂРµРґРµР»РµРЅРёСЏ РѕСЂРёРµРЅС‚Р°С†РёРё.

    Р›РѕРіРёРєР° (РїСЂРёРѕСЂРёС‚РµС‚С‹):
    1. Р•СЃР»Рё РµСЃС‚СЊ С‚РѕС‡РєРё РЅРёР¶РЅРµРіРѕ РїРѕСЏСЃР° (>= 3 С‚РѕС‡РµРє) - РёСЃРїРѕР»СЊР·СѓРµРј РіР»Р°РІРЅС‹Рµ РѕСЃРё РёРЅРµСЂС†РёРё
       РґР»СЏ РѕРїСЂРµРґРµР»РµРЅРёСЏ РѕСЂРёРµРЅС‚Р°С†РёРё X, Y РЅР° РѕСЃРЅРѕРІРµ РіРµРѕРјРµС‚СЂРёРё СЃРµС‡РµРЅРёСЏ Р±Р°С€РЅРё
    2. Р•СЃР»Рё РЅРµС‚ С‚РѕС‡РµРє РїРѕСЏСЃР°, РЅРѕ РµСЃС‚СЊ С‚РѕС‡РєР° standing - РёСЃРїРѕР»СЊР·СѓРµРј РЅР°РїСЂР°РІР»РµРЅРёРµ
       РѕС‚ standing Рє С†РµРЅС‚СЂСѓ РЅРёР¶РЅРµР№ СЃРµРєС†РёРё
    3. Р•СЃР»Рё РЅРёС‡РµРіРѕ РЅРµС‚ - РёСЃРїРѕР»СЊР·СѓРµРј СЃС‚Р°РЅРґР°СЂС‚РЅСѓСЋ РѕСЂРёРµРЅС‚Р°С†РёСЋ (РіР»РѕР±Р°Р»СЊРЅС‹Рµ РѕСЃРё X, Y)

    РџСЂРµРёРјСѓС‰РµСЃС‚РІР°:
    - РЈРЅРёРІРµСЂСЃР°Р»РµРЅ РґР»СЏ Р»СЋР±РѕР№ С„РѕСЂРјС‹ Рё РєРѕР»РёС‡РµСЃС‚РІР° РіСЂР°РЅРµР№ (3, 4, n)
    - РќРµ С‚СЂРµР±СѓРµС‚ Р·РЅР°РЅРёСЏ РєРѕР»РёС‡РµСЃС‚РІР° РіСЂР°РЅРµР№
    - РЈСЃС‚РѕР№С‡РёРІ Рє РѕС‚СЃСѓС‚СЃС‚РІРёСЋ С‚РѕС‡РєРё standing
    - РСЃРїРѕР»СЊР·СѓРµС‚ РіРµРѕРјРµС‚СЂРёСЋ Р±Р°С€РЅРё РґР»СЏ РѕРїС‚РёРјР°Р»СЊРЅРѕР№ РѕСЂРёРµРЅС‚Р°С†РёРё

    Args:
        centers: DataFrame СЃ С†РµРЅС‚СЂР°РјРё СЃРµРєС†РёР№ (x, y, z)
        standing_point: РЎР»РѕРІР°СЂСЊ СЃ РєРѕРѕСЂРґРёРЅР°С‚Р°РјРё С‚РѕС‡РєРё standing (РёСЃРїРѕР»СЊР·СѓРµС‚СЃСЏ РєР°Рє fallback)
        lower_belt_points: DataFrame СЃ С‚РѕС‡РєР°РјРё РЅРёР¶РЅРµРіРѕ РїРѕСЏСЃР° РґР»СЏ РѕРїСЂРµРґРµР»РµРЅРёСЏ РѕСЂРёРµРЅС‚Р°С†РёРё (РѕРїС†РёРѕРЅР°Р»СЊРЅРѕ)

    Returns:
        РЎР»РѕРІР°СЂСЊ СЃ РїР°СЂР°РјРµС‚СЂР°РјРё Р»РѕРєР°Р»СЊРЅРѕР№ СЃРёСЃС‚РµРјС‹ РєРѕРѕСЂРґРёРЅР°С‚:
        {
            'origin': (x, y, z),  # Р¦РµРЅС‚СЂ РЅРёР¶РЅРµР№ СЃРµРєС†РёРё
            'x_axis': (x, y, 0),  # Р•РґРёРЅРёС‡РЅС‹Р№ РІРµРєС‚РѕСЂ РѕСЃРё X
            'y_axis': (x, y, 0),  # Р•РґРёРЅРёС‡РЅС‹Р№ РІРµРєС‚РѕСЂ РѕСЃРё Y
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

    # РќР°С…РѕРґРёРј С†РµРЅС‚СЂ РЅРёР¶РЅРµР№ СЃРµРєС†РёРё (РјРёРЅРёРјР°Р»СЊРЅР°СЏ Z)
    bottom_idx = centers['z'].idxmin()
    bottom_center = centers.loc[bottom_idx]
    origin = np.array([bottom_center['x'], bottom_center['y'], bottom_center['z']])

    # РџР РРћР РРўР•Рў 1: РћСЂРёРµРЅС‚РёСЂСѓРµРј РѕСЃРё РїРѕ РЅР°РїСЂР°РІР»РµРЅРёСЋ Рє РїРµСЂРІРѕР№ С‚РѕС‡РєРµ СЃС‚РѕСЏРЅРёСЏ
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
                "Р›РѕРєР°Р»СЊРЅР°СЏ РЎРљ: РѕСЃСЊ X РЅР°РїСЂР°РІР»РµРЅР° РѕС‚ С‚РѕС‡РєРё СЃС‚РѕСЏРЅРёСЏ Рє С†РµРЅС‚СЂСѓ РЅРёР¶РЅРµР№ СЃРµРєС†РёРё"
            )

            return {
                'origin': tuple(origin),
                'x_axis': tuple(x_axis),
                'y_axis': tuple(y_axis),
                'valid': True,
            }

    # РџР РРћР РРўР•Рў 2: РСЃРїРѕР»СЊР·СѓРµРј РіР»Р°РІРЅС‹Рµ РѕСЃРё РЅРёР¶РЅРµРіРѕ РїРѕСЏСЃР° (РµСЃР»Рё РґРѕСЃС‚СѓРїРЅС‹)
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
                    "Р›РѕРєР°Р»СЊРЅР°СЏ РЎРљ: РёСЃРїРѕР»СЊР·РѕРІР°РЅС‹ РіР»Р°РІРЅС‹Рµ РѕСЃРё РЅРёР¶РЅРµРіРѕ РїРѕСЏСЃР° (С‚РѕС‡РµРє: %d)",
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
                f"РќРµ СѓРґР°Р»РѕСЃСЊ РІС‹С‡РёСЃР»РёС‚СЊ РіР»Р°РІРЅС‹Рµ РѕСЃРё РЅРёР¶РЅРµРіРѕ РїРѕСЏСЃР°: {e}, РёСЃРїРѕР»СЊР·СѓРµРј fallback"
            )

    # РџР РРћР РРўР•Рў 3: Р•СЃР»Рё РЅРёС‡РµРіРѕ РЅРµ РґРѕСЃС‚СѓРїРЅРѕ - СЃС‚Р°РЅРґР°СЂС‚РЅР°СЏ РѕСЂРёРµРЅС‚Р°С†РёСЏ
    logger.warning("РСЃРїРѕР»СЊР·СѓСЋС‚СЃСЏ СЃС‚Р°РЅРґР°СЂС‚РЅС‹Рµ РіР»РѕР±Р°Р»СЊРЅС‹Рµ РѕСЃРё РґР»СЏ Р»РѕРєР°Р»СЊРЅРѕР№ РЎРљ")
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
    ???????????? ?????????? ?????????? ??????? ? ????????? ??????? ?????????.

    ???????????? ?????????????? ???????? ????????? ?????? ?????? ??????
    ???????????? ?????? ?????? ??????????????? ????? ?????. ????????????????
    ??? ?? ??? ??????????? ???????? ? `axis`, ?? ?? ???????????? ??? ???????
    ????????? ??? ???????? ??????????.
    """
    del axis, standing_point

    if centers.empty or not local_cs['valid']:
        result = centers.copy()
        result['deviation'] = 0.0
        result['deviation_x'] = 0.0
        result['deviation_y'] = 0.0
        return result

    result = centers.copy()
    deviations: list[float] = []
    deviations_x: list[float] = []
    deviations_y: list[float] = []

    x_axis = np.array(local_cs['x_axis'], dtype=float)
    y_axis = np.array(local_cs['y_axis'], dtype=float)
    baseline_by_part: dict[int, np.ndarray] = {}

    for _, row in result.sort_values('z').iterrows():
        memberships = _decode_part_memberships(row.get('tower_part_memberships'))
        if memberships:
            part_key = int(memberships[0])
        else:
            try:
                part_key = int(row.get('tower_part', 1) or 1)
            except (TypeError, ValueError):
                part_key = 1
        if part_key <= 0:
            part_key = 1
        baseline_by_part.setdefault(
            part_key,
            np.array([row['x'], row['y'], row['z']], dtype=float),
        )

    for _, row in result.iterrows():
        memberships = _decode_part_memberships(row.get('tower_part_memberships'))
        if memberships:
            part_key = int(memberships[0])
        else:
            try:
                part_key = int(row.get('tower_part', 1) or 1)
            except (TypeError, ValueError):
                part_key = 1
        if part_key <= 0:
            part_key = 1

        point = np.array([row['x'], row['y'], row['z']], dtype=float)
        baseline_point = baseline_by_part.get(part_key, point)
        deviation_vector = point - baseline_point
        deviation_vector[2] = 0.0

        deviation_x = float(np.dot(deviation_vector, x_axis))
        deviation_y = float(np.dot(deviation_vector, y_axis))
        total_deviation = float(np.linalg.norm(deviation_vector))

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
    Р'С‹С‡РёСЃР»СЏРµС‚ СЂР°СЃСЃС‚РѕСЏРЅРёРµ РѕС‚ С‚РѕС‡РєРё РґРѕ РїСЂСЏРјРѕР№ РІ 3D

    Args:
        point: РљРѕРѕСЂРґРёРЅР°С‚С‹ С‚РѕС‡РєРё (x, y, z)
        line_point: РўРѕС‡РєР° РЅР° РїСЂСЏРјРѕР№
        line_direction: РќР°РїСЂР°РІР»СЏСЋС‰РёР№ РІРµРєС‚РѕСЂ РїСЂСЏРјРѕР№

    Returns:
        Р Р°СЃСЃС‚РѕСЏРЅРёРµ РѕС‚ С‚РѕС‡РєРё РґРѕ РїСЂСЏРјРѕР№
    """
    p = np.array(point)
    l0 = np.array(line_point)
    l = np.array(line_direction)

    # Нормализуем направляющий вектор
    norm = np.linalg.norm(l)
    if norm < 1e-10:
        raise ValueError("Degenerate line direction: zero-length vector")
    l = l / norm

    # Р'РµРєС‚РѕСЂ РѕС‚ С‚РѕС‡РєРё РЅР° РїСЂСЏРјРѕР№ РґРѕ С‚РѕС‡РєРё
    v = p - l0

    # РџСЂРѕРµРєС†РёСЏ v РЅР° РЅР°РїСЂР°РІР»РµРЅРёРµ РїСЂСЏРјРѕР№
    proj = np.dot(v, l) * l

    # РџРµСЂРїРµРЅРґРёРєСѓР»СЏСЂРЅР°СЏ СЃРѕСЃС‚Р°РІР»СЏСЋС‰Р°СЏ
    perp = v - proj

    # Р Р°СЃСЃС‚РѕСЏРЅРёРµ
    distance = np.linalg.norm(perp)

    return distance


def distance_to_line_3d(
    point: tuple[float, float, float],
    line_point: tuple[float, float, float],
    line_direction: tuple[float, float, float],
) -> float:
    """
    РЎРѕРІРјРµСЃС‚РёРјС‹Р№ РїСѓР±Р»РёС‡РЅС‹Р№ Р°Р»РёР°СЃ РґР»СЏ СЂР°СЃС‡РµС‚Р° СЂР°СЃСЃС‚РѕСЏРЅРёСЏ РѕС‚ С‚РѕС‡РєРё РґРѕ РїСЂСЏРјРѕР№ РІ 3D.
    """
    return point_to_line_distance_3d(point, line_point, line_direction)


def calculate_vertical_deviation(centers: pd.DataFrame, axis: dict[str, Any]) -> pd.DataFrame:
    """
    ???????????? ????????? ?????????????? ???????? ??????? ???????????? ?????? ??????.
    """
    del axis

    if centers.empty:
        centers['deviation'] = 0.0
        return centers

    result = centers.copy()
    baseline_row = result.dropna(subset=['x', 'y']).sort_values('z').iloc[0]
    x_diff = result['x'].values - float(baseline_row['x'])
    y_diff = result['y'].values - float(baseline_row['y'])
    result['deviation'] = np.sqrt(x_diff**2 + y_diff**2)
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
    РџРѕР»РЅС‹Р№ С†РёРєР» РѕР±СЂР°Р±РѕС‚РєРё РґР°РЅРЅС‹С… РјР°С‡С‚С‹ (СѓРЅРёРІРµСЂСЃР°Р»СЊРЅС‹Р№ РґР»СЏ Р»СЋР±РѕР№ С„РѕСЂРјС‹ Р±Р°С€РЅРё)

    РЈРЅРёРІРµСЂСЃР°Р»СЊРЅС‹Р№ Р°Р»РіРѕСЂРёС‚Рј СЂР°Р±РѕС‚Р°РµС‚ РґР»СЏ:
    - Р›СЋР±РѕРіРѕ РєРѕР»РёС‡РµСЃС‚РІР° РіСЂР°РЅРµР№ (3, 4, n)
    - Р›СЋР±РѕР№ С„РѕСЂРјС‹ (РїСЂРёР·РјР°, СѓСЃРµС‡РµРЅРЅР°СЏ РїСЂРёР·РјР°, С†РёР»РёРЅРґСЂ Рё С‚.Рї.)
    - РќРµ С‚СЂРµР±СѓРµС‚ Р·РЅР°РЅРёСЏ РєРѕР»РёС‡РµСЃС‚РІР° РіСЂР°РЅРµР№ РёР»Рё С„РѕСЂРјС‹

    Args:
        points: DataFrame СЃ РёСЃС…РѕРґРЅС‹РјРё С‚РѕС‡РєР°РјРё
        height_tolerance: Р”РѕРїСѓСЃРє РіСЂСѓРїРїРёСЂРѕРІРєРё РїРѕ РІС‹СЃРѕС‚Рµ
        center_method: РњРµС‚РѕРґ СЂР°СЃС‡РµС‚Р° С†РµРЅС‚СЂР° РїРѕСЏСЃР°
        use_assigned_belts: РСЃРїРѕР»СЊР·РѕРІР°С‚СЊ РЅР°Р·РЅР°С‡РµРЅРЅС‹Рµ РїРѕР»СЊР·РѕРІР°С‚РµР»РµРј РїРѕСЏСЃР°
        use_cache: РСЃРїРѕР»СЊР·РѕРІР°С‚СЊ РєСЌС€РёСЂРѕРІР°РЅРёРµ СЂРµР·СѓР»СЊС‚Р°С‚РѕРІ

    Returns:
        РЎР»РѕРІР°СЂСЊ СЃ СЂРµР·СѓР»СЊС‚Р°С‚Р°РјРё РѕР±СЂР°Р±РѕС‚РєРё
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

    # РџСЂРѕРІРµСЂСЏРµРј РєСЌС€
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
                logger.debug("РСЃРїРѕР»СЊР·РѕРІР°РЅ РєСЌС€РёСЂРѕРІР°РЅРЅС‹Р№ СЂРµР·СѓР»СЊС‚Р°С‚ СЂР°СЃС‡РµС‚РѕРІ")
                return _clone_calculation_result(cached_result)
            else:
                logger.debug("РЈРґР°Р»СЏРµРј РЅРµРІР°Р»РёРґРЅС‹Р№ РєРµС€ СЂР°СЃС‡РµС‚Р° Рё РїРµСЂРµСЃС‡РёС‚С‹РІР°РµРј")
                _calculation_cache.pop(cache_key, None)
                if cache_key in _cache_access_order:
                    _cache_access_order.remove(cache_key)

    # Р“СЂСѓРїРїРёСЂСѓРµРј С‚РѕС‡РєРё РїРѕ РїРѕСЏСЃР°Рј (РёСЃРїРѕР»СЊР·СѓСЏ РЅР°Р·РЅР°С‡РµРЅРЅС‹Рµ РёР»Рё Р°РІС‚РѕРіСЂСѓРїРїРёСЂРѕРІРєСѓ)
    belts = group_points_by_height(
        points,
        tolerance=height_tolerance,
        section_grouping_mode=resolved_grouping_mode,
    )

    # Р'С‹С‡РёСЃР»СЏРµРј С†РµРЅС‚СЂС‹ РїРѕСЏСЃРѕРІ
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

    # Р”РµРґСѓРїР»РёРєР°С†РёСЏ С†РµРЅС‚СЂРѕРІ РїРѕ РІС‹СЃРѕС‚Рµ РґР»СЏ СЃРѕСЃС‚Р°РІРЅС‹С… Р±Р°С€РµРЅ
    # Р›РѕРіРёРєР°: РґР»СЏ РєР°Р¶РґРѕР№ Р°Р±СЃРѕР»СЋС‚РЅРѕР№ РІС‹СЃРѕС‚С‹ РѕСЃС‚Р°РІР»СЏРµРј С‚РѕР»СЊРєРѕ РѕРґРёРЅ С†РµРЅС‚СЂ
    # РЎР°РјР°СЏ РЅРёР¶РЅСЏСЏ СЃРµРєС†РёСЏ, РїСЂРѕРјРµР¶СѓС‚РѕС‡РЅС‹Рµ СЃРµРєС†РёРё С‡Р°СЃС‚Рё, РІРµСЂС…РЅСЏСЏ СЃРµРєС†РёСЏ С‡Р°СЃС‚Рё,
    # РґР°Р»РµРµ РЅРёР¶РЅСЏСЏ СЃРµРєС†РёСЏ СЃР»РµРґСѓСЋС‰РµР№ С‡Р°СЃС‚Рё РїСЂРѕРїСѓСЃРєР°РµС‚СЃСЏ (СЃРѕРІРїР°РґР°РµС‚ СЃ РІРµСЂС…РЅРµР№ РїСЂРµРґС‹РґСѓС‰РµР№)
    if (
        resolved_grouping_mode == SECTION_GROUPING_ASSIGNED_SECTIONS
        and not centers.empty
        and len(centers) > 1
    ):
        # РЎРѕСЂС‚РёСЂСѓРµРј РїРѕ РІС‹СЃРѕС‚Рµ
        centers = centers.sort_values('z').reset_index(drop=True)

        # Р“СЂСѓРїРїРёСЂСѓРµРј С†РµРЅС‚СЂС‹ РїРѕ РІС‹СЃРѕС‚Рµ СЃ РґРѕРїСѓСЃРєРѕРј
        # Р”Р»СЏ С†РµРЅС‚СЂРѕРІ РЅР° РѕРґРЅРѕР№ РІС‹СЃРѕС‚Рµ (СЃ РґРѕРїСѓСЃРєРѕРј) РѕСЃС‚Р°РІР»СЏРµРј С‚РѕР»СЊРєРѕ РѕРґРёРЅ
        deduplicated_centers = []
        height_tolerance_dedup = height_tolerance  # РСЃРїРѕР»СЊР·СѓРµРј С‚РѕС‚ Р¶Рµ РґРѕРїСѓСЃРє, С‡С‚Рѕ Рё РґР»СЏ РіСЂСѓРїРїРёСЂРѕРІРєРё

        i = 0
        processed_indices = set()
        while i < len(centers):
            if i in processed_indices:
                i += 1
                continue

            current_row = centers.iloc[i]
            current_z = current_row['z']

            # РќР°С…РѕРґРёРј РІСЃРµ С†РµРЅС‚СЂС‹ РЅР° СЌС‚РѕР№ Р¶Рµ РІС‹СЃРѕС‚Рµ (СЃ РґРѕРїСѓСЃРєРѕРј)
            same_height_mask = np.abs(centers['z'].values - current_z) <= height_tolerance_dedup
            same_height_positions = np.where(same_height_mask)[0].tolist()

            if len(same_height_positions) > 1:
                # Р•СЃР»Рё РµСЃС‚СЊ РЅРµСЃРєРѕР»СЊРєРѕ С†РµРЅС‚СЂРѕРІ РЅР° РѕРґРЅРѕР№ РІС‹СЃРѕС‚Рµ, СѓСЃСЂРµРґРЅСЏРµРј РєРѕРѕСЂРґРёРЅР°С‚С‹
                same_height_rows = centers.iloc[same_height_positions]
                averaged_center = {
                    'x': float(same_height_rows['x'].mean()),
                    'y': float(same_height_rows['y'].mean()),
                    'z': float(same_height_rows['z'].mean()),  # РЎСЂРµРґРЅСЏСЏ РІС‹СЃРѕС‚Р°
                    'belt_height': float(same_height_rows['belt_height'].mean()),
                    'points_count': int(same_height_rows['points_count'].sum()),
                    'tower_part': int(same_height_rows['tower_part'].min()) if same_height_rows['tower_part'].notna().any() else None,
                    'tower_part_memberships': current_row.get('tower_part_memberships')  # Р'РµСЂРµРј РёР· РїРµСЂРІРѕРіРѕ
                }
                deduplicated_centers.append(averaged_center)
                logger.debug(f"РћР±СЉРµРґРёРЅРµРЅРѕ {len(same_height_positions)} С†РµРЅС‚СЂРѕРІ РЅР° РІС‹СЃРѕС‚Рµ ~{current_z:.3f}Рј РІ РѕРґРёРЅ")
                # РћС‚РјРµС‡Р°РµРј РІСЃРµ РѕР±СЂР°Р±РѕС‚Р°РЅРЅС‹Рµ РёРЅРґРµРєСЃС‹
                processed_indices.update(same_height_positions)
                # РџРµСЂРµС…РѕРґРёРј Рє СЃР»РµРґСѓСЋС‰РµРјСѓ РЅРµРѕР±СЂР°Р±РѕС‚Р°РЅРЅРѕРјСѓ РёРЅРґРµРєСЃСѓ
                i = max(same_height_positions) + 1
            else:
                # РћРґРёРЅ С†РµРЅС‚СЂ РЅР° СЌС‚РѕР№ РІС‹СЃРѕС‚Рµ - РїСЂРѕСЃС‚Рѕ РґРѕР±Р°РІР»СЏРµРј
                deduplicated_centers.append(current_row.to_dict())
                processed_indices.add(i)
                i += 1

        if len(deduplicated_centers) < len(centers):
            logger.info(f"Р”РµРґСѓРїР»РёРєР°С†РёСЏ С†РµРЅС‚СЂРѕРІ: Р±С‹Р»Рѕ {len(centers)}, СЃС‚Р°Р»Рѕ {len(deduplicated_centers)} "
                       f"(СѓРґР°Р»РµРЅРѕ {len(centers) - len(deduplicated_centers)} РґСѓР±Р»РёРєР°С‚РѕРІ)")
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

    # РђРїРїСЂРѕРєСЃРёРјРёСЂСѓРµРј РѕСЃСЊ Р±Р°С€РЅРё
    axis = approximate_tower_axis(centers)

    # РС‰РµРј С‚РѕС‡РєСѓ standing РґР»СЏ РЅРѕРІРѕР№ СЃРёСЃС‚РµРјС‹ РєРѕРѕСЂРґРёРЅР°С‚ (РёСЃРїРѕР»СЊР·СѓРµС‚СЃСЏ РєР°Рє fallback)
    standing_point = {'x': 0.0, 'y': 0.0, 'z': 0.0}  # РџРѕ СѓРјРѕР»С‡Р°РЅРёСЋ
    if 'is_station' in points.columns:
        station_mask = _build_is_station_mask(points['is_station'])
        station_points = points[station_mask]
        if len(station_points) > 0:
            standing_point = {
                'x': station_points.iloc[0]['x'],
                'y': station_points.iloc[0]['y'],
                'z': station_points.iloc[0]['z']
            }
            logger.info(f"РќР°Р№РґРµРЅР° С‚РѕС‡РєР° standing: {standing_point}")

    # РџРѕР»СѓС‡Р°РµРј С‚РѕС‡РєРё РЅРёР¶РЅРµРіРѕ РїРѕСЏСЃР° РґР»СЏ РѕРїСЂРµРґРµР»РµРЅРёСЏ РѕСЂРёРµРЅС‚Р°С†РёРё Р»РѕРєР°Р»СЊРЅРѕР№ РЎРљ
    # (РёСЃРїРѕР»СЊР·СѓРµС‚СЃСЏ РґР»СЏ СѓРЅРёРІРµСЂСЃР°Р»СЊРЅРѕРіРѕ СЂР°СЃС‡РµС‚Р°, РЅРµ Р·Р°РІРёСЃСЏС‰РµРіРѕ РѕС‚ С„РѕСЂРјС‹ Р±Р°С€РЅРё)
    lower_belt_points = None
    if belts:
        min_height = min(belts.keys())
        lower_belt_points = belts[min_height]
        logger.info(f"РСЃРїРѕР»СЊР·СѓРµРј {len(lower_belt_points)} С‚РѕС‡РµРє РЅРёР¶РЅРµРіРѕ РїРѕСЏСЃР° РґР»СЏ СѓРЅРёРІРµСЂСЃР°Р»СЊРЅРѕР№ РѕСЂРёРµРЅС‚Р°С†РёРё Р»РѕРєР°Р»СЊРЅРѕР№ РЎРљ")

    # Р'С‹С‡РёСЃР»СЏРµРј Р»РѕРєР°Р»СЊРЅСѓСЋ СЃРёСЃС‚РµРјСѓ РєРѕРѕСЂРґРёРЅР°С‚ (СѓРЅРёРІРµСЂСЃР°Р»СЊРЅРѕ РґР»СЏ Р»СЋР±РѕР№ С„РѕСЂРјС‹ Р±Р°С€РЅРё)
    local_cs = calculate_local_coordinate_system(centers, standing_point, lower_belt_points)

    # Р'С‹С‡РёСЃР»СЏРµРј РѕС‚РєР»РѕРЅРµРЅРёСЏ РѕС‚ РІРµСЂС‚РёРєР°Р»Рё СЃ РЅРѕРІРѕР№ Р»РѕРіРёРєРѕР№
    centers_with_vertical = calculate_vertical_deviation_with_local_cs(centers, axis, local_cs, standing_point)

    # РР·РІР»РµРєР°РµРј РёРЅС„РѕСЂРјР°С†РёСЋ Рѕ С‡Р°СЃС‚СЏС… Р±Р°С€РЅРё РёР· РёСЃС…РѕРґРЅС‹С… РґР°РЅРЅС‹С…
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
            logger.info(f"РћР±РЅР°СЂСѓР¶РµРЅР° СЃРѕСЃС‚Р°РІРЅР°СЏ Р±Р°С€РЅСЏ: С‡Р°СЃС‚РµР№={len(parts_meta)}, РіСЂР°РЅРёС†С‹={split_heights if split_heights else 'РЅРµС‚'}")

    # Р'С‹С‡РёСЃР»СЏРµРј СЃС‚СЂРµР»С‹ РїСЂРѕРіРёР±Р° (СЃ СѓС‡РµС‚РѕРј С‡Р°СЃС‚РµР№, РµСЃР»Рё Р±Р°С€РЅСЏ СЃРѕСЃС‚Р°РІРЅР°СЏ)
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
                logger.info("РђРІС‚РѕРѕРїСЂРµРґРµР»РµРЅР° СЃРѕСЃС‚Р°РІРЅР°СЏ Р±Р°С€РЅСЏ РґР»СЏ РїСЂСЏРјРѕР»РёРЅРµР№РЅРѕСЃС‚Рё: split_height=%.3f Рј", float(split_height))
    centers_with_straightness = calculate_straightness_deviation(centers_with_vertical, tower_parts_info)
    straightness_profiles = build_straightness_profiles(points, tower_parts_info)
    straightness_summary = _summarize_straightness_profiles(straightness_profiles)

    # Собираем предупреждения из разных этапов расчёта
    calc_warnings: list[str] = list(axis.get('warnings') or [])
    if standing_point == {'x': 0.0, 'y': 0.0, 'z': 0.0}:
        calc_warnings.append(
            "Опорная точка (standing) не найдена — используются координаты начала координат (0, 0, 0). "
            "Для башен вдали от начала координат ориентация локальной СК может быть некорректна."
        )

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
        'warnings': calc_warnings,
        'valid': True
    }

    # РЎРѕС…СЂР°РЅСЏРµРј РІ РєСЌС€ (СЃ РѕРіСЂР°РЅРёС‡РµРЅРёРµРј СЂР°Р·РјРµСЂР° Рё LRU СЃС‚СЂР°С‚РµРіРёРµР№)
    if use_cache and cache_key is not None:
        cache_key = _get_cache_key(points, height_tolerance, center_method, resolved_grouping_mode)
        if len(_calculation_cache) >= _cache_max_size:
            # РЈРґР°Р»СЏРµРј СЃР°РјСѓСЋ СЃС‚Р°СЂСѓСЋ Р·Р°РїРёСЃСЊ (LRU - Least Recently Used)
            if _cache_access_order:
                oldest_key = _cache_access_order.pop(0)
                if oldest_key in _calculation_cache:
                    del _calculation_cache[oldest_key]
                    logger.debug(f"РЈРґР°Р»РµРЅР° СЃС‚Р°СЂР°СЏ Р·Р°РїРёСЃСЊ РёР· РєСЌС€Р° (LRU): {oldest_key[:20]}...")
            else:
                # Fallback: РµСЃР»Рё СЃРїРёСЃРѕРє РїСѓСЃС‚, СѓРґР°Р»СЏРµРј РїРµСЂРІСѓСЋ Р·Р°РїРёСЃСЊ
                oldest_key = next(iter(_calculation_cache))
                del _calculation_cache[oldest_key]

        # Р”РѕР±Р°РІР»СЏРµРј РЅРѕРІСѓСЋ Р·Р°РїРёСЃСЊ
        _calculation_cache[cache_key] = _clone_calculation_result(result)
        # РћР±РЅРѕРІР»СЏРµРј РїРѕСЂСЏРґРѕРє РґРѕСЃС‚СѓРїР°
        if cache_key in _cache_access_order:
            _cache_access_order.remove(cache_key)
        _cache_access_order.append(cache_key)
        logger.debug(f"Р РµР·СѓР»СЊС‚Р°С‚ СЃРѕС…СЂР°РЅРµРЅ РІ РєСЌС€ (СЂР°Р·РјРµСЂ РєСЌС€Р°: {len(_calculation_cache)})")

    return _clone_calculation_result(result) if use_cache else result


