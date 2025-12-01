"""
Операции с секциями башни
Автоматическое определение секций и добавление недостающих точек
"""

import numpy as np
import pandas as pd
from typing import Tuple, List, Dict
import logging
import json

logger = logging.getLogger(__name__)


def _build_is_station_mask(series: pd.Series) -> pd.Series:
    series = series.copy()
    if series.dtype == 'object':
        string_mask = series.map(lambda value: isinstance(value, str))
        if string_mask.any():
            lowered = series[string_mask].str.strip().str.lower()
            mapping = {'true': True, 'false': False, '1': True, '0': False, 'yes': True, 'no': False}
            mapped = lowered.map(mapping)
            valid_idx = mapped.dropna().index
            if len(valid_idx) > 0:
                series.loc[valid_idx] = mapped.loc[valid_idx]
        series = series.infer_objects(copy=False)
    null_mask = series.isna()
    if null_mask.any():
        series.loc[null_mask] = False
    return series.astype(bool)


def find_section_levels(data: pd.DataFrame, height_tolerance: float = 0.3) -> List[float]:
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
    data_for_levels = data.copy()
    if 'is_station' in data.columns:
        data_for_levels['is_station'] = _build_is_station_mask(data_for_levels['is_station'])
        data_for_levels = data_for_levels[~data_for_levels['is_station']]
    
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


def add_missing_points_for_sections(data: pd.DataFrame, section_levels: List[float], 
                                    height_tolerance: float = 0.3) -> pd.DataFrame:
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


def get_section_lines(data: pd.DataFrame, section_levels: List[float], 
                      height_tolerance: float = 0.3) -> List[Dict]:
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
            logger.debug(f"    Детали по точкам:")
            for belt_num in belts_found:
                belt_points = level_points[level_points['belt'] == belt_num]
                logger.debug(f"      Пояс {belt_num}: {len(belt_points)} точек (высоты: {belt_points['z'].tolist()})")
        
        if level_points.empty:
            continue
        
        # Сортируем по номеру пояса, затем по высоте для дедупликации точек на одном поясе
        level_points_sorted = level_points.sort_values(['belt', 'z'])
        
        # Дедуплицируем точки по поясам - на каждом поясе должна быть одна точка
        points_by_belt: Dict[int, Tuple[float, float, float]] = {}
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

