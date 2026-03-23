"""
Общие утилиты для работы с точками башни.

Канонические реализации функций, используемых в нескольких модулях:
- _build_is_station_mask: маска точек стояния
- _decode_part_memberships: декодирование принадлежности к частям
- _row_belongs_to_part: проверка принадлежности строки к части
- _filter_points_by_part: фильтрация точек по части башни
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd


def build_is_station_mask(series: pd.Series) -> pd.Series:
    """Преобразует серию значений is_station в булеву маску.

    Обрабатывает строковые ('true'/'false'/'1'/'0'/'yes'/'no'),
    числовые и NaN-значения.
    """
    result = pd.Series(False, index=series.index, dtype=bool)
    null_mask = series.isna()
    string_mask = series.map(lambda value: isinstance(value, str))

    if string_mask.any():
        lowered = series[string_mask].str.strip().str.lower()
        mapping = {
            'true': True, 'false': False,
            '1': True, '0': False,
            'yes': True, 'no': False,
        }
        result.loc[string_mask] = lowered.map(mapping).fillna(False).astype(bool)

    other_mask = ~(null_mask | string_mask)
    if other_mask.any():
        result.loc[other_mask] = series.loc[other_mask].astype(bool)

    return result


def build_flag_mask(
    data_or_series: pd.DataFrame | pd.Series,
    column_name: str,
) -> pd.Series:
    """Build a normalized boolean mask for an arbitrary point flag column."""
    if isinstance(data_or_series, pd.Series):
        series = data_or_series
        index = data_or_series.index
    else:
        index = data_or_series.index
        if column_name not in data_or_series.columns:
            return pd.Series(False, index=index, dtype=bool)
        series = data_or_series[column_name]
    return build_is_station_mask(series).reindex(index, fill_value=False)


def build_is_auxiliary_mask(data_or_series: pd.DataFrame | pd.Series) -> pd.Series:
    """Build a normalized mask for auxiliary survey points."""
    return build_flag_mask(data_or_series, 'is_auxiliary')


def build_is_control_mask(data_or_series: pd.DataFrame | pd.Series) -> pd.Series:
    """Build a normalized mask for control-only duplicate points."""
    return build_flag_mask(data_or_series, 'is_control')


def build_non_working_tower_mask(data: pd.DataFrame) -> pd.Series:
    """Mask rows that must be excluded from tower-face calculations."""
    station_mask = build_flag_mask(data, 'is_station')
    auxiliary_mask = build_flag_mask(data, 'is_auxiliary')
    control_mask = build_flag_mask(data, 'is_control')
    return station_mask | auxiliary_mask | control_mask


def build_working_tower_mask(data: pd.DataFrame) -> pd.Series:
    """Mask rows that represent working tower points."""
    return ~build_non_working_tower_mask(data)


def normalize_tower_point_flags(data: pd.DataFrame) -> pd.DataFrame:
    """Ensure all service point flags exist and are normalized to bool."""
    result = data.copy()
    for column_name in ('is_station', 'is_auxiliary', 'is_control'):
        result[column_name] = build_flag_mask(result, column_name)
    return result


def decode_part_memberships(value) -> list[int]:
    """Декодирует JSON-строку или список принадлежности точки к частям башни."""
    if value is None:
        return []
    if isinstance(value, float) and np.isnan(value):
        return []
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except Exception:
            return []
    elif isinstance(value, (list, tuple, set)):
        decoded = list(value)
    else:
        return []
    memberships: list[int] = []
    for item in decoded:
        try:
            memberships.append(int(item))
        except (TypeError, ValueError):
            continue
    return memberships


def row_belongs_to_part(row: pd.Series, part_num: int) -> bool:
    """Проверяет, принадлежит ли строка данных к указанной части башни.

    Порядок проверки:
    1. tower_part_memberships (расширенная принадлежность)
    2. tower_part + is_part_boundary (граничные точки относятся к обеим частям)
    """
    memberships = []
    if 'tower_part_memberships' in row and pd.notna(row.get('tower_part_memberships')):
        memberships = decode_part_memberships(row.get('tower_part_memberships'))
    if memberships:
        return part_num in memberships
    raw_value = row.get('tower_part', 1)
    if raw_value is None or (isinstance(raw_value, float) and np.isnan(raw_value)):
        raw_value = 1
    try:
        base_part = int(raw_value)
    except (TypeError, ValueError):
        return False
    if base_part <= 0:
        base_part = 1
    if bool(row.get('is_part_boundary', False)):
        return part_num in (base_part, base_part + 1)
    return base_part == part_num


def filter_points_by_part(data: pd.DataFrame, part_num: int) -> pd.DataFrame:
    """Фильтрует DataFrame, оставляя только точки указанной части башни."""
    if 'tower_part_memberships' in data.columns:
        mask = data.apply(lambda row: row_belongs_to_part(row, part_num), axis=1)
        return data[mask].copy()
    return data[data['tower_part'] == part_num].copy()
