"""
Операции с секциями башни
Автоматическое определение секций и добавление недостающих точек
"""

import json
import logging

import numpy as np
import pandas as pd

from core.point_utils import (
    build_is_station_mask as _build_is_station_mask,
    build_working_tower_mask as _build_working_tower_mask,
)
from core.section_state import SECTION_BUILD_HEIGHT_TOLERANCE

logger = logging.getLogger(__name__)


def _legacy_find_section_levels(
    data: pd.DataFrame,
    height_tolerance: float = SECTION_BUILD_HEIGHT_TOLERANCE,
) -> list[float]:
    """
    Находит уровни секций по высотам точек на всех поясах

    Args:
        data: DataFrame с точками (должен содержать колонки 'z' и 'belt')
        height_tolerance: Допуск для группировки высот (метры)

    Returns:
        Список высот секций (отсортированный по возрастанию)
    """
    if data.empty or 'z' not in data.columns or 'belt' not in data.columns:
        return []

    # Исключаем точки standing из определения уровней секций
    data_for_levels = data[_build_working_tower_mask(data)].copy()

    # Собираем все высоты точек (без точек standing)
    all_heights = data_for_levels['z'].values

    if len(all_heights) == 0:
        return []

    # Сортируем высоты
    sorted_heights = np.sort(all_heights)

    # Группируем близкие высоты
    section_levels = []
    current_level = sorted_heights[0]
    current_group = [current_level]

    for height in sorted_heights[1:]:
        if height - current_level <= height_tolerance:
            # Добавляем в текущую группу
            current_group.append(height)
        else:
            # Завершаем текущую группу и начинаем новую
            # Используем медиану вместо среднего для более устойчивого результата
            section_levels.append(np.median(current_group))
            current_level = height
            current_group = [height]

    # Добавляем последнюю группу
    if current_group:
        section_levels.append(np.median(current_group))

    logger.info(f"Найдено {len(section_levels)} уровней секций: {[f'{h:.2f}' for h in section_levels]}")

    return section_levels


def _legacy_add_missing_points_for_sections(
    data: pd.DataFrame,
    section_levels: list[float],
    height_tolerance: float = SECTION_BUILD_HEIGHT_TOLERANCE,
) -> pd.DataFrame:
    """
    Добавляет недостающие точки на поясах для всех секций

    Логика:
    1. Для каждого уровня секции проверяем, есть ли точка на каждом поясе
    2. Если на поясе нет точки на этом уровне, добавляем её
    3. Координаты X,Y берем из соседних точек пояса (интерполяция)

    Args:
        data: Исходные данные с точками
        section_levels: Список высот секций
        height_tolerance: Допуск для определения, есть ли точка на уровне

    Returns:
        DataFrame с добавленными точками
    """
    if data.empty or not section_levels:
        return data.copy()

    result_data = data.copy()

    # Исключаем точки стояния (с belt=None или is_station=True)
    data_without_station = data.copy()
    if 'is_station' in data.columns:
        data_without_station['is_station'] = _build_is_station_mask(data_without_station['is_station'])
        data_without_station = data_without_station[~data_without_station['is_station']]

    available_belts = sorted(data_without_station['belt'].dropna().unique())

    added_count = 0

    for section_height in section_levels:
        logger.info(f"Обработка уровня секции Z={section_height:.3f}м")

        for belt_num in available_belts:
            belt_num = int(belt_num)

            # Проверяем, есть ли точка на этом поясе на данном уровне (без точек standing)
            belt_points = data_without_station[data_without_station['belt'] == belt_num]

            # Ищем точку близкую к уровню секции
            height_diffs = np.abs(belt_points['z'].values - section_height)

            if len(height_diffs) > 0 and np.min(height_diffs) <= height_tolerance:
                # Точка уже есть на этом уровне
                continue

            # Точки нет - нужно добавить
            logger.info(f"  Добавляем точку на пояс {belt_num} на высоте {section_height:.3f}м")

            # Интерполируем X,Y координаты из соседних точек пояса
            if len(belt_points) < 2:
                logger.warning(f"  На поясе {belt_num} недостаточно точек для интерполяции")
                continue

            # Сортируем точки пояса по высоте
            belt_points_sorted = belt_points.sort_values('z')

            # Находим точки выше и ниже уровня секции
            points_below = belt_points_sorted[belt_points_sorted['z'] < section_height]
            points_above = belt_points_sorted[belt_points_sorted['z'] > section_height]

            if points_below.empty or points_above.empty:
                # Экстраполяция из ближайших точек
                if points_below.empty:
                    # Берем две самые нижние точки
                    if len(belt_points_sorted) < 2:
                        continue
                    p1 = belt_points_sorted.iloc[0]
                    p2 = belt_points_sorted.iloc[1]
                else:
                    # Берем две самые верхние точки
                    if len(belt_points_sorted) < 2:
                        continue
                    p1 = belt_points_sorted.iloc[-2]
                    p2 = belt_points_sorted.iloc[-1]
            else:
                # Интерполяция между ближайшими точками
                p1 = points_below.iloc[-1]  # Ближайшая снизу
                p2 = points_above.iloc[0]   # Ближайшая сверху

            # Линейная интерполяция/экстраполяция
            if abs(p2['z'] - p1['z']) < 1e-6:
                # Точки на одной высоте
                new_x = (p1['x'] + p2['x']) / 2
                new_y = (p1['y'] + p2['y']) / 2
            else:
                t = (section_height - p1['z']) / (p2['z'] - p1['z'])
                new_x = p1['x'] + t * (p2['x'] - p1['x'])
                new_y = p1['y'] + t * (p2['y'] - p1['y'])

            # Генерируем имя для новой точки
            new_name = f"S{int(section_height)}_B{belt_num}"

            # Вычисляем правильный point_index - пересчитываем каждый раз, так как result_data обновляется
            max_point_index = 0
            if 'point_index' in result_data.columns:
                valid_indices = pd.to_numeric(result_data['point_index'], errors='coerce')
                if valid_indices.notna().any():
                    max_point_index = int(valid_indices.max())

            # Создаем новую точку с правильным point_index
            new_point_index = max_point_index + 1
            new_point_dict = {
                'name': new_name,
                'x': new_x,
                'y': new_y,
                'z': section_height,
                'belt': belt_num,
                'point_index': new_point_index
            }

            # Копируем остальные колонки из первой точки данных (если есть)
            if len(result_data) > 0:
                first_row = result_data.iloc[0]
                for col in result_data.columns:
                    if col not in ['name', 'x', 'y', 'z', 'belt', 'point_index']:
                        new_point_dict[col] = first_row[col] if pd.notna(first_row[col]) else None

            new_point = pd.DataFrame([new_point_dict])

            # Добавляем к результату
            result_data = pd.concat([result_data, new_point], ignore_index=True)
            added_count += 1

            logger.info(f"    Добавлена точка '{new_name}' на ({new_x:.3f}, {new_y:.3f}, {section_height:.3f}) с point_index={new_point_index}")

    logger.info(f"Добавлено {added_count} точек для секций")

    return result_data


def _legacy_get_section_lines(
    data: pd.DataFrame,
    section_levels: list[float],
    height_tolerance: float = SECTION_BUILD_HEIGHT_TOLERANCE,
) -> list[dict]:
    """
    Получить линии секций для визуализации

    Важно: Для каждой высоты создается ТОЛЬКО ОДНА секция, даже если точки принадлежат разным частям.
    Для граничных секций сохраняется информация о принадлежности ко всем частям.

    Returns:
        Список словарей с информацией о линиях секций:
        [
            {
                'height': float,  # Высота секции
                'points': [(x, y, z), ...],  # Точки на всех поясах на этом уровне
                'belt_nums': [1, 2, 3, ...],  # Номера поясов
                'tower_part': int,  # Основная часть
                'tower_part_memberships': [int, ...],  # Принадлежность к частям (для граничных)
                'is_part_boundary': bool  # Является ли граничной секцией
            },
            ...
        ]
    """
    if data.empty or not section_levels:
        return []

    # Исключаем точки standing из визуализации
    logger.info(f"Входных данных для get_section_lines: всего {len(data)} точек")
    data_without_station = data.copy()
    if 'is_station' in data.columns:
        data_without_station['is_station'] = _build_is_station_mask(data_without_station['is_station'])
        data_without_station = data_without_station[~data_without_station['is_station']]
        logger.info(f"Исключено {len(data) - len(data_without_station)} точек standing")

    logger.info(f"Данных для линий секций: всего точек {len(data_without_station)}, поясов {data_without_station['belt'].nunique()}")

    section_lines = []

    # Дедуплицируем section_levels по высоте (на случай, если есть дубликаты)
    deduplicated_levels = []
    seen_heights = set()
    for level_height in section_levels:
        # Проверяем, не создали ли мы уже секцию на близкой высоте
        is_duplicate = False
        for seen_height in seen_heights:
            if abs(level_height - seen_height) <= height_tolerance:
                is_duplicate = True
                logger.debug(f"Пропущен дубликат уровня {level_height:.3f}м (близко к {seen_height:.3f}м)")
                break
        if not is_duplicate:
            deduplicated_levels.append(level_height)
            seen_heights.add(level_height)

    logger.info(f"Дедупликация уровней: было {len(section_levels)}, стало {len(deduplicated_levels)}")

    # Сортируем дедуплицированные уровни по высоте для правильной нумерации
    sorted_deduplicated_levels = sorted(deduplicated_levels)

    for section_num, section_height in enumerate(sorted_deduplicated_levels):
        # Находим все точки близкие к этому уровню
        height_mask = np.abs(data_without_station['z'].values - section_height) <= height_tolerance
        level_points = data_without_station[height_mask]

        logger.info(f"  Уровень {section_height:.3f}м: найдено {len(level_points)} точек в пределах tolerance={height_tolerance}")
        if len(level_points) > 0:
            belts_found = sorted(level_points['belt'].dropna().unique().tolist())
            logger.info(f"    Найдены пояса на этом уровне: {belts_found}")
            logger.debug("    Детали по точкам:")
            for belt_num in belts_found:
                belt_points = level_points[level_points['belt'] == belt_num]
                logger.debug(f"      Пояс {belt_num}: {len(belt_points)} точек (высоты: {belt_points['z'].tolist()})")

        if level_points.empty:
            continue

        # Сортируем по номеру пояса, затем по высоте для дедупликации точек на одном поясе
        level_points_sorted = level_points.sort_values(['belt', 'z'])

        # Дедуплицируем точки по поясам - на каждом поясе должна быть одна точка
        points_by_belt: dict[int, tuple[float, float, float]] = {}
        belt_nums_set = set()

        for _, point in level_points_sorted.iterrows():
            if pd.notna(point['belt']):
                belt_num = int(point['belt'])
                belt_nums_set.add(belt_num)
                # Если для этого пояса еще нет точки, добавляем её
                # Если есть, используем точку, ближайшую к section_height
                if belt_num not in points_by_belt:
                    points_by_belt[belt_num] = (point['x'], point['y'], point['z'])
                else:
                    # Сравниваем расстояние до целевой высоты
                    existing_z = points_by_belt[belt_num][2]
                    if abs(point['z'] - section_height) < abs(existing_z - section_height):
                        points_by_belt[belt_num] = (point['x'], point['y'], point['z'])

        points = list(points_by_belt.values())
        belt_nums = sorted(belt_nums_set)

        if len(points) > 0:  # Только если есть точки
            section_info = {
                'height': section_height,
                'points': points,
                'belt_nums': belt_nums
            }

            # Определяем принадлежность секции к частям из данных точек
            all_parts = set()
            part_counts = {}
            segment_counts = {}
            is_boundary = False

            if not level_points.empty:
                # Собираем информацию о частях из всех точек на этом уровне
                if 'tower_part' in level_points.columns:
                    for _, point_row in level_points.iterrows():
                        part_val = point_row.get('tower_part')
                        if pd.notna(part_val):
                            try:
                                part_num = int(part_val)
                                all_parts.add(part_num)
                                part_counts[part_num] = part_counts.get(part_num, 0) + 1
                            except (TypeError, ValueError):
                                pass

                if 'tower_part_memberships' in level_points.columns:
                    for _, point_row in level_points.iterrows():
                        memberships_val = point_row.get('tower_part_memberships')
                        if pd.notna(memberships_val):
                            try:
                                if isinstance(memberships_val, str):
                                    memberships = json.loads(memberships_val)
                                elif isinstance(memberships_val, (list, tuple)):
                                    memberships = list(memberships_val)
                                else:
                                    memberships = []
                                all_parts.update(int(p) for p in memberships if p is not None)
                                if len(memberships) > 1:
                                    is_boundary = True
                            except (TypeError, ValueError, json.JSONDecodeError):
                                pass

                if 'is_part_boundary' in level_points.columns:
                    if level_points['is_part_boundary'].any():
                        is_boundary = True

                if 'segment' in level_points.columns:
                    for _, point_row in level_points.iterrows():
                        segment_val = point_row.get('segment')
                        if pd.notna(segment_val):
                            try:
                                segment_num = int(segment_val)
                                segment_counts[segment_num] = segment_counts.get(segment_num, 0) + 1
                                if 'tower_part' not in section_info:
                                    all_parts.add(segment_num)
                            except (TypeError, ValueError):
                                pass

            # Определяем основную часть (наиболее часто встречающуюся)
            if all_parts:
                primary_part = max(all_parts, key=lambda p: part_counts.get(p, 0)) if part_counts else min(all_parts)
                section_info['tower_part'] = primary_part

                # Если секция принадлежит нескольким частям - это граничная
                if len(all_parts) > 1:
                    is_boundary = True
                    section_info['tower_part_memberships'] = sorted(list(all_parts))
                    section_info['is_part_boundary'] = True
                    logger.debug(f"  Граничная секция на высоте {section_height:.3f}м: части {sorted(all_parts)}")
                else:
                    # Если одна часть, всё равно сохраняем memberships для консистентности
                    section_info['tower_part_memberships'] = sorted(list(all_parts))
                    section_info['is_part_boundary'] = is_boundary
            elif segment_counts:
                # Используем segment как часть
                primary_segment = max(segment_counts.keys(), key=lambda s: segment_counts[s])
                section_info['segment'] = primary_segment
                section_info['tower_part'] = primary_segment
                section_info['tower_part_memberships'] = [primary_segment]
                section_info['is_part_boundary'] = is_boundary
            else:
                # Если нет информации о частях, устанавливаем значения по умолчанию
                section_info['tower_part'] = None
                section_info['tower_part_memberships'] = None
                section_info['is_part_boundary'] = False

            # Добавляем segment, если есть
            if segment_counts and 'segment' not in section_info:
                primary_segment = max(segment_counts.keys(), key=lambda s: segment_counts[s])
                section_info['segment'] = primary_segment

            # Сохраняем также дополнительную информацию о частях, если она есть в данных
            # Это важно для сохранения информации при пересчете
            if not level_points.empty:
                # Пробуем извлечь segment_name из первой точки, если он там есть
                first_point = level_points.iloc[0]
                if 'segment_name' in first_point.index and pd.notna(first_point.get('segment_name')):
                    section_info['segment_name'] = first_point.get('segment_name')

                # Сохраняем section_name, если есть
                if 'section_name' in first_point.index and pd.notna(first_point.get('section_name')):
                    section_info['section_name'] = first_point.get('section_name')

            # Присваиваем сквозную нумерацию секции (на основе отсортированного списка высот)
            # section_num уже определен выше в цикле enumerate
            section_info['section_num'] = section_num

            section_lines.append(section_info)
            logger.info(f"  Секция на высоте {section_height:.3f}м: {len(points)} точек, часть(и): {sorted(all_parts) if all_parts else 'не определена'}")

    logger.info(f"Создано {len(section_lines)} линий секций для визуализации (уникальных по высоте)")

    return section_lines


def _section_working_data(data: pd.DataFrame) -> pd.DataFrame:
    return data[_build_working_tower_mask(data)].copy()


def _extract_tower_parts(data: pd.DataFrame) -> list[int]:
    from core.point_utils import decode_part_memberships as _decode_part_memberships

    parts: set[int] = set()
    if 'tower_part_memberships' in data.columns:
        for value in data['tower_part_memberships'].dropna():
            parts.update(_decode_part_memberships(value))

    if not parts and 'tower_part' in data.columns:
        part_values = pd.to_numeric(data['tower_part'], errors='coerce').dropna()
        parts.update(int(value) for value in part_values if int(value) > 0)

    return sorted(parts)


def _iter_section_groups(data: pd.DataFrame) -> list[tuple[int | None, pd.DataFrame]]:
    from core.point_utils import filter_points_by_part as _filter_points_by_part

    parts = _extract_tower_parts(data)
    if not parts:
        return [(None, data.copy())]

    groups: list[tuple[int | None, pd.DataFrame]] = []
    for part_num in parts:
        part_data = _filter_points_by_part(data, part_num)
        if not part_data.empty:
            groups.append((part_num, part_data.copy()))
    return groups or [(None, data.copy())]


def _build_section_entries(
    data: pd.DataFrame,
    base_tolerance: float = SECTION_BUILD_HEIGHT_TOLERANCE,
) -> list[dict]:
    """Build section entries by grouping points at each height level.

    Uses ``height_level`` column when available (from sorting pipeline),
    otherwise falls back to rank-based iteration over belt tracks.

    Improvements over previous implementation:
    - Groups by height_level instead of rank — handles unequal point counts per belt
    - Tolerance formula: ``max(base, spread * 1.5)`` (not ``0.35 + spread/2``)
    - Merge uses ``min(tol_a, tol_b)`` to prevent transitivity issues
    - Recalculates tolerance after each merge
    """
    working = _section_working_data(data)
    if working.empty or 'z' not in working.columns:
        return []

    # Determine belt column: prefer face_track, fall back to belt
    belt_col = 'belt'
    if 'face_track' in working.columns:
        ft_vals = pd.to_numeric(working['face_track'], errors='coerce').dropna()
        if not ft_vals.empty and ft_vals.max() > 0:
            belt_col = 'face_track'

    if belt_col not in working.columns:
        return []

    entries: list[dict] = []
    for part_num, group in _iter_section_groups(working):
        numeric_belts = pd.to_numeric(group[belt_col], errors='coerce')
        group = group.loc[numeric_belts.notna() & (numeric_belts > 0)].copy()
        if group.empty:
            continue
        group[belt_col] = numeric_belts.loc[group.index].astype(int)

        # --- height_level-based grouping (preferred) ---
        if 'height_level' in group.columns:
            hl_vals = pd.to_numeric(group['height_level'], errors='coerce')
            valid_hl = hl_vals.notna() & (hl_vals > 0)
            if valid_hl.any():
                entries.extend(
                    _entries_from_height_levels(group.loc[valid_hl], belt_col, part_num, base_tolerance)
                )
                continue

        # --- fallback: rank-based iteration (legacy behaviour) ---
        entries.extend(
            _entries_from_rank_iteration(group, belt_col, part_num, base_tolerance)
        )

    if not entries:
        return []

    # Sort by height and merge nearby entries
    entries.sort(key=lambda e: e['height'])
    merged = _merge_section_entries(entries, base_tolerance)

    for entry in merged:
        entry['parts'] = sorted(int(v) for v in entry['parts'])
        entry['belt_nums'] = sorted(int(v) for v in entry['belt_nums'])

    return merged


def _entries_from_height_levels(
    group: pd.DataFrame,
    belt_col: str,
    part_num: int | None,
    base_tolerance: float,
) -> list[dict]:
    """Build section entries using height_level column."""
    hl_series = pd.to_numeric(group['height_level'], errors='coerce').astype(int)
    entries: list[dict] = []
    for level in sorted(hl_series.unique()):
        level_points = group[hl_series == level]
        rows = {idx: level_points.loc[idx] for idx in level_points.index}
        heights = [float(r['z']) for r in rows.values()]
        belt_nums = {int(r[belt_col]) for r in rows.values()}
        spread = (max(heights) - min(heights)) if len(heights) > 1 else 0.0
        entries.append({
            'height': float(np.mean(heights)),
            'tolerance': max(base_tolerance, spread * 1.5),
            'parts': {int(part_num)} if part_num is not None else set(),
            'rows': rows,
            'belt_nums': belt_nums,
        })
    return entries


def _entries_from_rank_iteration(
    group: pd.DataFrame,
    belt_col: str,
    part_num: int | None,
    base_tolerance: float,
) -> list[dict]:
    """Legacy fallback: build entries by iterating ranks across belt tracks."""
    from typing import Any

    belts = sorted(int(v) for v in group[belt_col].unique())
    tracks = {belt: group[group[belt_col] == belt].sort_values('z') for belt in belts}
    max_len = max((len(t) for t in tracks.values()), default=0)
    entries: list[dict] = []

    for rank in range(max_len):
        rows: dict[Any, pd.Series] = {}
        heights: list[float] = []
        belt_nums: set[int] = set()
        for belt_num, track in tracks.items():
            if rank >= len(track):
                continue
            row = track.iloc[rank]
            rows[row.name] = row
            heights.append(float(row['z']))
            belt_nums.add(int(belt_num))
        if not rows:
            continue
        spread = (max(heights) - min(heights)) if len(heights) > 1 else 0.0
        entries.append({
            'height': float(np.mean(heights)),
            'tolerance': max(base_tolerance, 0.35 + spread / 2.0),
            'parts': {int(part_num)} if part_num is not None else set(),
            'rows': rows,
            'belt_nums': belt_nums,
        })
    return entries


def _merge_section_entries(entries: list[dict], base_tolerance: float) -> list[dict]:
    """Merge entries that are within tolerance of each other.

    Uses ``max(tol_a, tol_b)`` for merge decision.
    Recalculates tolerance after each merge based on actual spread.
    """
    merged: list[dict] = []
    for entry in entries:
        if not merged:
            merged.append(entry)
            continue

        current = merged[-1]
        merge_tolerance = max(float(current['tolerance']), float(entry['tolerance']))
        if abs(float(entry['height']) - float(current['height'])) > merge_tolerance:
            merged.append(entry)
            continue

        # Merge into current
        current['rows'].update(entry['rows'])
        current['parts'].update(entry['parts'])
        current['belt_nums'].update(entry['belt_nums'])

        # Recalculate height and tolerance from merged data
        merged_heights = [float(row['z']) for row in current['rows'].values()]
        current['height'] = float(np.mean(merged_heights))
        spread = (max(merged_heights) - min(merged_heights)) if len(merged_heights) > 1 else 0.0
        current['tolerance'] = max(base_tolerance, spread * 1.5)

    return merged


def _resolve_requested_section_entries(
    data: pd.DataFrame,
    section_levels: list[float],
    *,
    base_tolerance: float = SECTION_BUILD_HEIGHT_TOLERANCE,
) -> list[dict]:
    derived_entries = _build_section_entries(data, base_tolerance=base_tolerance)
    if not section_levels:
        return []

    matched_entries: list[dict] = []
    used_ids: set[int] = set()
    groups = _iter_section_groups(_section_working_data(data))

    for requested_height in sorted(section_levels):
        best_idx = None
        best_diff = None
        for idx, entry in enumerate(derived_entries):
            diff = abs(float(entry['height']) - float(requested_height))
            if diff <= max(float(entry['tolerance']), base_tolerance * 2.0):
                if best_diff is None or diff < best_diff:
                    best_idx = idx
                    best_diff = diff

        if best_idx is not None:
            if best_idx not in used_ids:
                matched_entries.append(derived_entries[best_idx])
                used_ids.add(best_idx)
            continue

        applicable_parts: list[int] = []
        for part_num, group in groups:
            if group.empty:
                continue
            z_min = float(group['z'].min())
            z_max = float(group['z'].max())
            if z_min - base_tolerance <= requested_height <= z_max + base_tolerance and part_num is not None:
                applicable_parts.append(int(part_num))

        matched_entries.append(
            {
                'height': float(requested_height),
                'tolerance': float(base_tolerance),
                'parts': sorted(applicable_parts),
                'rows': {},
                'belt_nums': [],
            }
        )

    return matched_entries


def find_section_levels(
    data: pd.DataFrame,
    height_tolerance: float = SECTION_BUILD_HEIGHT_TOLERANCE,
) -> list[float]:
    """Find section levels using vertical belt tracks instead of raw z clustering."""
    entries = _build_section_entries(data, base_tolerance=height_tolerance)
    levels = [float(entry['height']) for entry in entries]
    if levels:
        logger.info(
            "Найдено %s уровней секций по трекам belt: %s",
            len(levels),
            [f"{height:.2f}" for height in levels],
        )
        return levels

    if data.empty or 'z' not in data.columns or 'belt' not in data.columns:
        return []

    working = _section_working_data(data)
    all_heights = working['z'].to_numpy(dtype=float)
    if len(all_heights) == 0:
        return []

    sorted_heights = np.sort(all_heights)
    section_levels = []
    current_group = [float(sorted_heights[0])]
    current_level = float(sorted_heights[0])

    for height in sorted_heights[1:]:
        height = float(height)
        if height - current_level <= height_tolerance:
            current_group.append(height)
        else:
            section_levels.append(float(np.mean(current_group)))
            current_group = [height]
        current_level = height

    if current_group:
        section_levels.append(float(np.mean(current_group)))

    return section_levels


def add_missing_points_for_sections(
    data: pd.DataFrame,
    section_levels: list[float],
    height_tolerance: float = SECTION_BUILD_HEIGHT_TOLERANCE,
) -> pd.DataFrame:
    """Add missing section points using belt tracks and tower-part aware interpolation."""
    if data.empty or not section_levels:
        return data.copy()

    from core.point_utils import filter_points_by_part as _filter_points_by_part

    result_data = data.copy()
    target_entries = _resolve_requested_section_entries(
        result_data,
        section_levels,
        base_tolerance=height_tolerance,
    )
    added_count = 0

    for entry in target_entries:
        section_height = float(entry['height'])
        section_tolerance = float(entry['tolerance'])
        current_working = _section_working_data(result_data)
        groups = _iter_section_groups(current_working)
        target_parts = entry['parts'] if entry['parts'] else [None]

        for part_num in target_parts:
            if part_num is None:
                part_points = current_working.copy()
            else:
                part_points = _filter_points_by_part(current_working, int(part_num))

            if part_points.empty:
                continue

            numeric_belts = pd.to_numeric(part_points['belt'], errors='coerce').dropna()
            available_belts = sorted(int(value) for value in numeric_belts.unique())

            for belt_num in available_belts:
                belt_points = part_points[pd.to_numeric(part_points['belt'], errors='coerce') == belt_num].sort_values('z')
                if belt_points.empty:
                    continue

                height_diffs = np.abs(belt_points['z'].to_numpy(dtype=float) - section_height)
                if len(height_diffs) > 0 and float(np.min(height_diffs)) <= section_tolerance:
                    continue

                if len(belt_points) < 2:
                    continue

                points_below = belt_points[belt_points['z'] < section_height]
                points_above = belt_points[belt_points['z'] > section_height]
                if points_below.empty:
                    p1 = belt_points.iloc[0]
                    p2 = belt_points.iloc[1]
                elif points_above.empty:
                    p1 = belt_points.iloc[-2]
                    p2 = belt_points.iloc[-1]
                else:
                    p1 = points_below.iloc[-1]
                    p2 = points_above.iloc[0]

                if abs(float(p2['z']) - float(p1['z'])) < 1e-9:
                    new_x = float(p1['x'] + p2['x']) / 2.0
                    new_y = float(p1['y'] + p2['y']) / 2.0
                else:
                    ratio = (section_height - float(p1['z'])) / (float(p2['z']) - float(p1['z']))
                    new_x = float(p1['x']) + ratio * (float(p2['x']) - float(p1['x']))
                    new_y = float(p1['y']) + ratio * (float(p2['y']) - float(p1['y']))

                template_row = belt_points.iloc[0].to_dict()
                next_point_index = 0
                if 'point_index' in result_data.columns:
                    valid_indices = pd.to_numeric(result_data['point_index'], errors='coerce').dropna()
                    if not valid_indices.empty:
                        next_point_index = int(valid_indices.max())

                template_row['name'] = f"S{int(round(section_height))}_B{belt_num}" if part_num is None else f"S{int(round(section_height))}_P{int(part_num)}_B{belt_num}"
                template_row['x'] = float(new_x)
                template_row['y'] = float(new_y)
                template_row['z'] = float(section_height)
                template_row['belt'] = int(belt_num)
                template_row['is_section_generated'] = True
                if 'point_index' in result_data.columns:
                    template_row['point_index'] = next_point_index + 1
                if 'is_station' in result_data.columns:
                    template_row['is_station'] = False
                if 'tower_part' in result_data.columns and part_num is not None:
                    template_row['tower_part'] = int(part_num)
                if 'part_belt' in result_data.columns:
                    template_row['part_belt'] = int(belt_num)
                if 'tower_part_memberships' in result_data.columns and part_num is not None:
                    template_row['tower_part_memberships'] = json.dumps([int(part_num)], ensure_ascii=False)
                if 'part_belt_assignments' in result_data.columns and part_num is not None:
                    template_row['part_belt_assignments'] = json.dumps({str(int(part_num)): int(belt_num)}, ensure_ascii=False)
                if 'faces' in result_data.columns and pd.isna(template_row.get('faces')):
                    face_values = pd.to_numeric(part_points.get('faces'), errors='coerce').dropna() if 'faces' in part_points.columns else pd.Series(dtype=float)
                    if not face_values.empty:
                        template_row['faces'] = int(face_values.iloc[0])

                result_data = pd.concat([result_data, pd.DataFrame([template_row])], ignore_index=True)
                added_count += 1

    logger.info("Добавлено %s точек для секций (трековый режим)", added_count)
    return result_data


def get_section_lines(
    data: pd.DataFrame,
    section_levels: list[float],
    height_tolerance: float = SECTION_BUILD_HEIGHT_TOLERANCE,
) -> list[dict]:
    """Build section lines from belt tracks with composite-tower awareness."""
    if data.empty or not section_levels:
        return []

    from core.point_utils import decode_part_memberships as _decode_part_memberships

    entries = _resolve_requested_section_entries(
        data,
        section_levels,
        base_tolerance=height_tolerance,
    )
    working = _section_working_data(data)
    section_lines: list[dict] = []

    for section_num, entry in enumerate(entries):
        rows_map = dict(entry.get('rows', {}))
        if not rows_map:
            tolerance = float(entry.get('tolerance', height_tolerance))
            level_points = working[np.abs(working['z'].to_numpy(dtype=float) - float(entry['height'])) <= tolerance]
            rows_map = {idx: row for idx, row in level_points.iterrows()}

        if not rows_map:
            continue

        rows_by_key: dict[tuple[int | None, int], pd.Series] = {}
        for row in rows_map.values():
            belt_value = pd.to_numeric(pd.Series([row.get('belt')]), errors='coerce').iloc[0]
            if pd.isna(belt_value):
                continue
            part_value = row.get('tower_part')
            try:
                part_key = int(part_value) if pd.notna(part_value) else None
            except (TypeError, ValueError):
                part_key = None
            key = (part_key, int(belt_value))
            existing = rows_by_key.get(key)
            if existing is None or abs(float(row['z']) - float(entry['height'])) < abs(float(existing['z']) - float(entry['height'])):
                rows_by_key[key] = row

        selected_rows = list(rows_by_key.values())
        if not selected_rows:
            continue

        points = [
            (float(row['x']), float(row['y']), float(row['z']))
            for row in selected_rows
        ]
        belt_nums = sorted(
            {
                int(pd.to_numeric(pd.Series([row.get('belt')]), errors='coerce').iloc[0])
                for row in selected_rows
                if pd.notna(pd.to_numeric(pd.Series([row.get('belt')]), errors='coerce').iloc[0])
            }
        )

        all_parts: set[int] = set()
        part_counts: dict[int, int] = {}
        segment_counts: dict[int, int] = {}
        for row in selected_rows:
            memberships = []
            if 'tower_part_memberships' in row.index and pd.notna(row.get('tower_part_memberships')):
                memberships = _decode_part_memberships(row.get('tower_part_memberships'))
            if memberships:
                for part_num in memberships:
                    all_parts.add(int(part_num))
                    part_counts[int(part_num)] = part_counts.get(int(part_num), 0) + 1

            raw_part = row.get('tower_part')
            if pd.notna(raw_part):
                try:
                    part_num = int(raw_part)
                except (TypeError, ValueError):
                    part_num = None
                if part_num is not None:
                    all_parts.add(part_num)
                    part_counts[part_num] = part_counts.get(part_num, 0) + 1

            raw_segment = row.get('segment')
            if pd.notna(raw_segment):
                try:
                    segment_num = int(raw_segment)
                except (TypeError, ValueError):
                    segment_num = None
                if segment_num is not None:
                    segment_counts[segment_num] = segment_counts.get(segment_num, 0) + 1

        section_info = {
            'height': float(entry['height']),
            'points': points,
            'belt_nums': belt_nums,
            'section_num': section_num,
        }

        if all_parts:
            primary_part = max(part_counts, key=part_counts.get) if part_counts else min(all_parts)
            section_info['tower_part'] = primary_part
            section_info['tower_part_memberships'] = sorted(all_parts)
            section_info['is_part_boundary'] = len(all_parts) > 1
        else:
            section_info['tower_part'] = None
            section_info['tower_part_memberships'] = None
            section_info['is_part_boundary'] = False

        if segment_counts:
            section_info['segment'] = max(segment_counts, key=segment_counts.get)

        first_row = selected_rows[0]
        if 'segment_name' in first_row.index and pd.notna(first_row.get('segment_name')):
            section_info['segment_name'] = first_row.get('segment_name')
        if 'section_name' in first_row.index and pd.notna(first_row.get('section_name')):
            section_info['section_name'] = first_row.get('section_name')

        section_lines.append(section_info)

    logger.info("Создано %s линий секций в трековом режиме", len(section_lines))
    return section_lines

