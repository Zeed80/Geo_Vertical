"""
Модуль для автоматического дополнения недостающих точек пояса
для образования правильной геометрии (квадрат с углами 90°)
"""

import logging
from typing import Any

import numpy as np
import pandas as pd

from .planar_orientation import extract_reference_station_xy, sort_points_clockwise
from .survey_registration import rotate_points_around_z

logger = logging.getLogger(__name__)


def complete_belt_to_square(
    belt_points: pd.DataFrame,
    tower_faces: int = 4,
    height_tolerance: float = 0.15,
    target_height: float | None = None
) -> pd.DataFrame:
    """
    Дополняет пояс недостающими точками для образования квадрата с углами 90°

    Логика:
    1. Если точек меньше, чем граней башни, добавляем недостающие
    2. Точки должны образовать правильный многоугольник в плоскости XY
    3. Все точки на одной высоте (target_height, если указана, иначе средняя высота существующих точек)

    Args:
        belt_points: DataFrame с точками пояса (колонки: x, y, z, name, belt)
        tower_faces: Количество граней башни (4 = квадрат, 3 = треугольник и т.д.)
        height_tolerance: Допуск по высоте для определения одной плоскости
        target_height: Целевая высота для новых точек (если None, используется средняя высота существующих)

    Returns:
        DataFrame с дополненными точками пояса
    """
    if belt_points.empty:
        return belt_points.copy()

    if len(belt_points) >= tower_faces:
        # Точок достаточно, не дополняем
        return belt_points.copy()

    logger.info(f"Дополнение пояса: текущее количество точек={len(belt_points)}, "
               f"нужно={tower_faces}")

    # Вычисляем высоту для новых точек
    if target_height is not None:
        avg_height = target_height
        logger.info(f"Использована целевая высота для новых точек: {avg_height:.3f} м")
    else:
        avg_height = belt_points['z'].mean()
        logger.info(f"Использована средняя высота существующих точек: {avg_height:.3f} м")

    # Получаем координаты точек в плоскости XY
    xy_points = belt_points[['x', 'y']].values

    # Находим центр пояса
    center = xy_points.mean(axis=0)

    # Вычисляем радиус пояса (среднее расстояние от центра до точек)
    distances = np.linalg.norm(xy_points - center, axis=1)
    radius = np.mean(distances)

    if radius < 1e-6:
        logger.warning(f"Радиус пояса слишком мал: {radius:.6f}м, пропускаем дополнение")
        return belt_points.copy()

    # Вычисляем углы существующих точек относительно центра
    angles_existing = []
    for xy in xy_points:
        dx = xy[0] - center[0]
        dy = xy[1] - center[1]
        angle = np.arctan2(dy, dx)
        angles_existing.append(angle)

    angles_existing = np.array(angles_existing)

    # Нормализуем углы к [0, 2π]
    angles_existing = angles_existing % (2 * np.pi)

    # Углы для полного многоугольника
    angle_step = 2 * np.pi / tower_faces
    target_angles = np.array([i * angle_step for i in range(tower_faces)])

    # Определяем, какие углы уже есть
    angle_matches = []
    for target_angle in target_angles:
        # Находим ближайший существующий угол
        angle_diffs = np.abs(angles_existing - target_angle)
        angle_diffs = np.minimum(angle_diffs, 2 * np.pi - angle_diffs)  # Учитываем цикличность

        min_diff_idx = np.argmin(angle_diffs)
        min_diff = angle_diffs[min_diff_idx]

        # Если угол достаточно близок (в пределах 10°), считаем что точка есть
        if min_diff < np.radians(15):
            angle_matches.append((target_angle, True, min_diff_idx))
        else:
            angle_matches.append((target_angle, False, None))

    # Добавляем недостающие точки
    result_points = belt_points.copy()
    next_point_num = len(belt_points) + 1

    for target_angle, has_point, existing_idx in angle_matches:
        if not has_point:
            # Вычисляем координаты новой точки
            x_new = center[0] + radius * np.cos(target_angle)
            y_new = center[1] + radius * np.sin(target_angle)
            z_new = avg_height

            # Создаем новую точку
            new_point = {
                'name': f'Доп_{next_point_num}',
                'x': x_new,
                'y': y_new,
                'z': z_new,
                'belt': belt_points.iloc[0]['belt'] if 'belt' in belt_points.columns else None
            }

            # Копируем остальные колонки из первой точки
            for col in belt_points.columns:
                if col not in ['name', 'x', 'y', 'z', 'belt']:
                    new_point[col] = belt_points.iloc[0][col]

            # Добавляем к результату
            result_points = pd.concat([result_points, pd.DataFrame([new_point])], ignore_index=True)
            logger.info(f"Добавлена точка пояса: угол={np.degrees(target_angle):.1f}°, "
                       f"координаты=({x_new:.3f}, {y_new:.3f}, {z_new:.3f})")
            next_point_num += 1

    return result_points


def complete_belts_to_squares(
    data: pd.DataFrame,
    tower_faces: int = 4,
    height_tolerance: float = 0.15
) -> pd.DataFrame:
    """
    Дополняет все пояса в данных недостающими точками для образования правильной геометрии

    Args:
        data: DataFrame с точками, содержащий колонку 'belt'
        tower_faces: Количество граней башни
        height_tolerance: Допуск по высоте

    Returns:
        DataFrame с дополненными точками
    """
    if 'belt' not in data.columns:
        logger.warning("Колонка 'belt' не найдена, пропускаем дополнение")
        return data.copy()

    # Группируем по поясам
    belt_numbers = sorted(data['belt'].dropna().unique())

    result_data = []

    for belt_num in belt_numbers:
        belt_points = data[data['belt'] == belt_num].copy()

        # Дополняем пояс
        completed_belt = complete_belt_to_square(
            belt_points,
            tower_faces,
            height_tolerance
        )

        result_data.append(completed_belt)
        logger.info(f"Пояс {belt_num}: было {len(belt_points)} точек, стало {len(completed_belt)} точек")

    # Объединяем все пояса
    if result_data:
        result = pd.concat(result_data, ignore_index=True)
    else:
        result = data.copy()

    return result


def create_section_at_height(
    data: pd.DataFrame,
    target_height: float,
    target_belt: int,
    tower_faces: int = 4,
    height_tolerance: float = 0.15
) -> pd.DataFrame | None:
    """
    Создает полную секцию (квадрат/многоугольник) на указанной высоте

    Если на высоте target_height недостаточно точек для образования полной секции,
    создаются недостающие точки для образования правильного многоугольника.

    Args:
        data: DataFrame с точками
        target_height: Высота, на которой нужно создать секцию
        target_belt: Номер пояса, к которому относятся новые точки
        tower_faces: Количество граней башни (4 = квадрат)
        height_tolerance: Допуск по высоте для поиска точек на том же уровне

    Returns:
        DataFrame с новыми точками или None, если секция уже полная или невозможно создать
    """
    if data.empty:
        logger.warning("Данные пусты, невозможно создать секцию")
        return None

    # Находим все точки на указанной высоте
    points_at_height = data[
        np.abs(data['z'] - target_height) <= height_tolerance
    ].copy()

    logger.info(f"На высоте {target_height:.3f} м найдено {len(points_at_height)} точек")

    # Если точек достаточно, возвращаем пустой DataFrame
    if len(points_at_height) >= tower_faces:
        logger.info(f"Секция на высоте {target_height:.3f} м уже полная ({len(points_at_height)} точек)")
        return pd.DataFrame()

    # Если точек нет вообще, пытаемся использовать близкие по высоте точки для определения центра и радиуса
    if len(points_at_height) == 0:
        logger.warning(f"На высоте {target_height:.3f} м нет точек. Пытаемся использовать точки пояса {target_belt}")
        if 'belt' in data.columns:
            belt_points = data[data['belt'] == target_belt].copy()
            if len(belt_points) > 0:
                # Используем среднюю высоту пояса для определения центра и радиуса
                avg_belt_height = belt_points['z'].mean()
                logger.info(f"Используем среднюю высоту пояса {target_belt}: {avg_belt_height:.3f} м")
                points_at_height = belt_points.copy()
            else:
                logger.error(f"Не найдено точек пояса {target_belt} для создания секции")
                return None
        else:
            logger.error("Колонка 'belt' не найдена, невозможно создать секцию")
            return None

    # Вычисляем центр и радиус на основе существующих точек
    xy_points = points_at_height[['x', 'y']].values

    if len(xy_points) == 0:
        logger.error("Не найдено точек для определения центра и радиуса")
        return None

    center = xy_points.mean(axis=0)

    # Вычисляем радиус как среднее расстояние от центра до существующих точек
    distances = np.linalg.norm(xy_points - center, axis=1)
    radius = np.mean(distances)

    if radius < 1e-6:
        logger.warning(f"Радиус слишком мал: {radius:.6f}м, используем значение по умолчанию")
        # Пытаемся найти радиус из других точек того же пояса
        if 'belt' in data.columns:
            belt_points = data[data['belt'] == target_belt].copy()
            if len(belt_points) > 0:
                belt_xy = belt_points[['x', 'y']].values
                belt_center = belt_xy.mean(axis=0)
                belt_distances = np.linalg.norm(belt_xy - belt_center, axis=1)
                radius = np.mean(belt_distances)
                center = belt_center
                logger.info(f"Использован радиус из других точек пояса {target_belt}: {radius:.3f} м")

        if radius < 1e-6:
            logger.error("Не удалось определить радиус для создания секции")
            return None

    # Вычисляем углы существующих точек
    angles_existing = []
    for xy in xy_points:
        dx = xy[0] - center[0]
        dy = xy[1] - center[1]
        angle = np.arctan2(dy, dx)
        angles_existing.append(angle)

    angles_existing = np.array(angles_existing)
    angles_existing = angles_existing % (2 * np.pi)

    # Углы для полного многоугольника
    angle_step = 2 * np.pi / tower_faces
    target_angles = np.array([i * angle_step for i in range(tower_faces)])

    # Определяем, какие углы уже есть
    angle_matches = []
    for target_angle in target_angles:
        angle_diffs = np.abs(angles_existing - target_angle)
        angle_diffs = np.minimum(angle_diffs, 2 * np.pi - angle_diffs)
        min_diff_idx = np.argmin(angle_diffs)
        min_diff = angle_diffs[min_diff_idx]

        if min_diff < np.radians(15):
            angle_matches.append((target_angle, True, min_diff_idx))
        else:
            angle_matches.append((target_angle, False, None))

    # Создаем недостающие точки
    new_points_list = []

    # Вычисляем правильный point_index - находим максимальный существующий
    max_point_index = 0
    if 'point_index' in data.columns:
        valid_indices = pd.to_numeric(data['point_index'], errors='coerce')
        if valid_indices.notna().any():
            max_point_index = int(valid_indices.max())

    point_counter = 0
    for target_angle, has_point, existing_idx in angle_matches:
        if not has_point:
            # Вычисляем координаты новой точки
            x_new = center[0] + radius * np.cos(target_angle)
            y_new = center[1] + radius * np.sin(target_angle)
            z_new = target_height  # Используем точно указанную высоту

            # Вычисляем правильный point_index
            point_counter += 1
            new_point_index = max_point_index + point_counter

            # Создаем новую точку
            new_point = {
                'name': f'Секция_{target_height:.2f}_{new_point_index}',
                'x': x_new,
                'y': y_new,
                'z': z_new,
                'belt': target_belt,
                'point_index': new_point_index
            }

            # Копируем остальные колонки из первой точки данных
            for col in data.columns:
                if col not in ['name', 'x', 'y', 'z', 'belt', 'point_index']:
                    if len(data) > 0:
                        new_point[col] = data.iloc[0][col] if pd.notna(data.iloc[0][col]) else None
                    else:
                        new_point[col] = None

            new_points_list.append(new_point)
            logger.info(f"Создана точка секции: угол={np.degrees(target_angle):.1f}°, "
                       f"координаты=({x_new:.3f}, {y_new:.3f}, {z_new:.3f}), пояс={target_belt}, point_index={new_point_index}")

    if new_points_list:
        new_points_df = pd.DataFrame(new_points_list)
        logger.info(f"Создано {len(new_points_df)} новых точек для секции на высоте {target_height:.3f} м")
        return new_points_df
    else:
        logger.info("Все точки секции уже существуют, новые точки не созданы")
        return pd.DataFrame()


def _get_belt_levels(points: pd.DataFrame, belt_ref: int) -> np.ndarray:
    if 'belt' not in points.columns:
        return np.array([])
    ref = points[points['belt'] == belt_ref]
    if ref.empty:
        return np.array([])
    return ref['z'].values


def _snap_z(values: np.ndarray, targets: np.ndarray) -> np.ndarray:
    if len(targets) == 0:
        return values
    snapped = []
    for v in values:
        idx = int(np.argmin(np.abs(targets - v)))
        snapped.append(targets[idx])
    return np.array(snapped)


def _merge_candidates(cand_a: pd.DataFrame, cand_c: pd.DataFrame, tolerance: float) -> pd.DataFrame:
    if cand_a is None or cand_a.empty:
        return cand_c.copy()
    if cand_c is None or cand_c.empty:
        return cand_a.copy()
    res = []
    used_c = set()
    a_xyz = cand_a[['x','y','z']].values
    c_xyz = cand_c[['x','y','z']].values
    for i, pa in enumerate(a_xyz):
        z_mask = np.isclose(c_xyz[:,2], pa[2], atol=1e-4)
        idxs = np.where(z_mask)[0]
        if len(idxs) == 0:
            res.append(cand_a.iloc[i])
            continue
        diffs = c_xyz[idxs,:2] - pa[:2]
        dists = np.linalg.norm(diffs, axis=1)
        jrel = int(np.argmin(dists))
        j = idxs[jrel]
        if dists[jrel] <= tolerance:
            xm = (pa[0] + c_xyz[j,0]) / 2.0
            ym = (pa[1] + c_xyz[j,1]) / 2.0
            zm = pa[2]
            row = cand_a.iloc[i].copy()
            row['x'] = xm; row['y'] = ym; row['z'] = zm
            res.append(row)
            used_c.add(j)
        else:
            res.append(cand_a.iloc[i])
    for j in range(len(c_xyz)):
        if j not in used_c:
            res.append(cand_c.iloc[j])
    return pd.DataFrame(res).reset_index(drop=True)


def _validate_belt_polygon(belt_df: pd.DataFrame, faces: int, belt_num: int) -> dict[str, Any]:
    """
    Проверяет правильность многоугольника пояса.

    Для правильной усеченной пирамиды все пояса должны быть правильными многоугольниками:
    - Все точки должны быть на примерно одинаковом расстоянии от центра
    - Углы между соседними точками должны быть примерно равны (360° / n)

    Args:
        belt_df: DataFrame с точками пояса (колонки: x, y, z)
        faces: Количество граней башни (3, 4, 5, 6+)
        belt_num: Номер пояса для логирования

    Returns:
        Словарь с результатами проверки: {'valid': bool, 'radius_std': float, 'angle_std': float, 'warnings': List[str]}
    """
    if belt_df.empty or len(belt_df) < 3:
        return {'valid': False, 'radius_std': 0.0, 'angle_std': 0.0, 'warnings': ['Недостаточно точек для проверки']}

    # Вычисляем центр пояса
    center = belt_df[['x', 'y']].mean().values

    # Вычисляем расстояния от центра до точек
    xy_points = belt_df[['x', 'y']].values
    distances = np.linalg.norm(xy_points - center, axis=1)
    radius_mean = np.mean(distances)
    radius_std = np.std(distances)
    radius_cv = radius_std / radius_mean if radius_mean > 1e-9 else float('inf')

    # Вычисляем углы точек относительно центра
    angles = np.arctan2(xy_points[:, 1] - center[1], xy_points[:, 0] - center[0])
    angles = angles % (2 * np.pi)
    angles_sorted = np.sort(angles)

    # Вычисляем углы между соседними точками
    angle_diffs = np.diff(angles_sorted)
    # Добавляем угол между последней и первой точкой (с учетом замкнутости)
    angle_diffs = np.append(angle_diffs, (angles_sorted[0] + 2 * np.pi) - angles_sorted[-1])

    # Ожидаемый угол между соседними точками для правильного многоугольника
    expected_angle = 2 * np.pi / len(belt_df)
    angle_std = np.std(angle_diffs)
    angle_cv = angle_std / expected_angle if expected_angle > 1e-9 else float('inf')

    # Проверяем качество многоугольника
    warnings = []
    valid = True

    # Проверка расстояний (коэффициент вариации должен быть < 0.1 для правильного многоугольника)
    if radius_cv > 0.1:
        warnings.append(f"Высокий разброс расстояний от центра: CV={radius_cv:.3f} (ожидается < 0.1)")
        valid = False

    # Проверка углов (стандартное отклонение должно быть < 0.1 радиан для правильного многоугольника)
    if angle_std > 0.1:
        warnings.append(f"Высокий разброс углов между точками: std={np.degrees(angle_std):.1f}° (ожидается < 5.7°)")
        valid = False

    # Проверка количества точек (должно быть равно количеству граней для правильного многоугольника)
    if len(belt_df) != faces:
        warnings.append(f"Количество точек ({len(belt_df)}) не равно количеству граней ({faces})")
        # Это не критично, но стоит отметить

    if valid:
        logger.info(f"[validate_belt] Пояс {belt_num}: правильный многоугольник (радиус CV={radius_cv:.3f}, угол std={np.degrees(angle_std):.2f}°)")
    else:
        logger.warning(f"[validate_belt] Пояс {belt_num}: проблемы с геометрией: {', '.join(warnings)}")

    return {
        'valid': valid,
        'radius_mean': radius_mean,
        'radius_std': radius_std,
        'radius_cv': radius_cv,
        'angle_mean': expected_angle,
        'angle_std': angle_std,
        'angle_cv': angle_cv,
        'warnings': warnings
    }


def _drop_duplicates_vs_existing(existing: pd.DataFrame, generated: pd.DataFrame, tolerance: float) -> pd.DataFrame:
    if generated is None or generated.empty:
        return generated
    if existing is None or existing.empty:
        return generated
    ex = existing[['x','y','z']].values
    keep_rows = []
    for _, row in generated.iterrows():
        p = np.array([row['x'], row['y'], row['z']])
        dists = np.linalg.norm(ex - p, axis=1)
        if np.min(dists) > tolerance:
            keep_rows.append(row)
    if not keep_rows:
        return pd.DataFrame(columns=generated.columns)
    return pd.DataFrame(keep_rows).reset_index(drop=True)


def complete_missing_belt(points: pd.DataFrame,
                          faces: int = 4,
                          target_belt: int | None = None,
                          rotation_center: np.ndarray | None = None,
                          rotation_step_deg: float | None = None,
                          tolerance: float = 0.15) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Достроить недостающий пояс на основе соседних поясов поворотом ±step.
    Возвращает (merged_points, generated_points).
    """
    if points is None or points.empty:
        return points, pd.DataFrame()
    data = points.copy()
    if 'belt' not in data.columns:
        return data, pd.DataFrame()
    belts_present = sorted([int(b) for b in data['belt'].dropna().unique()])
    if target_belt is None:
        for b in range(1, faces+1):
            if b not in belts_present:
                target_belt = b
                break
    if target_belt is None:
        return data, pd.DataFrame()
    prev_belt = target_belt - 1 if target_belt > 1 else faces
    next_belt = target_belt + 1 if target_belt < faces else 1
    belt_prev = data[data['belt'] == prev_belt].copy()
    belt_next = data[data['belt'] == next_belt].copy()
    if belt_prev.empty and belt_next.empty:
        return data, pd.DataFrame()
    if rotation_center is None:
        rotation_center = data[['x','y','z']].mean().values
    if rotation_step_deg is None or rotation_step_deg <= 0:
        rotation_step_deg = 360.0 / (float(faces) * 2.0)
    step_rad = np.radians(rotation_step_deg)
    gen_prev = pd.DataFrame()
    gen_next = pd.DataFrame()
    if not belt_prev.empty:
        gen_prev = rotate_points_around_z(belt_prev, -step_rad, rotation_center)
    if not belt_next.empty:
        gen_next = rotate_points_around_z(belt_next, step_rad, rotation_center)
    for df in (gen_prev, gen_next):
        if not df.empty:
            df['belt'] = target_belt
            df['is_generated'] = True
    z_levels = _get_belt_levels(data, 1)
    for df in (gen_prev, gen_next):
        if not df.empty and len(z_levels) > 0:
            snapped = _snap_z(df['z'].values, z_levels)
            df['z'] = snapped
    candidates = _merge_candidates(gen_prev, gen_next, tolerance)
    if candidates.empty:
        return data, pd.DataFrame()
    clean = _drop_duplicates_vs_existing(data, candidates, tolerance)

    if clean.empty:
        logger.warning("[rotation] После удаления дублей не осталось точек для добавления")
        return data, pd.DataFrame()

    merged = pd.concat([data, clean], ignore_index=True)

    # Проверка геометрии достроенного пояса
    b_mask = (merged['belt'] == target_belt)
    if b_mask.any():
        b_target = merged[b_mask].copy()

        # Проверяем углы
        angle_check = _check_belt_angles(b_target, faces, angle_tolerance_deg=5.0)
        logger.info(f"[rotation] Проверка углов пояса {target_belt}: {angle_check['message']}")
        if not angle_check['valid']:
            logger.warning(f"[rotation] Углы пояса {target_belt} отклоняются от ожидаемых более чем на 5°")

        # Проверяем расстояния
        distance_check = _check_belt_distances(b_target, distance_tolerance=0.2)
        logger.info(f"[rotation] Проверка расстояний пояса {target_belt}: {distance_check['message']}")
        if not distance_check['valid']:
            logger.warning(f"[rotation] Расстояния между точками пояса {target_belt} неравномерны")

    return merged, clean


def complete_missing_belt_interpolation(
    points: pd.DataFrame,
    faces: int,
    target_belt: int,
    tolerance: float = 0.15
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Достроить недостающий пояс через интерполяцию между соседними поясами.

    Алгоритм:
    1. Находит соседние пояса для целевого пояса
    2. Для каждой точки на соседних поясах находит соответствующую точку
    3. Интерполирует позицию точки достроенного пояса между соседними поясами
    4. Использует линейную интерполяцию в плоскости XY и по высоте

    Args:
        points: DataFrame с точками (должна быть колонка 'belt')
        faces: Количество граней башни
        target_belt: Номер целевого пояса для достройки
        tolerance: Допуск для удаления дублей

    Returns:
        Кортеж (merged_points, generated_points): объединенные данные и сгенерированные точки
    """
    logger = logging.getLogger(__name__)
    if points is None or points.empty:
        logger.warning("[interpolation] Пустые входные данные — пропуск")
        return points, pd.DataFrame()

    data = points.copy()
    if 'belt' not in data.columns:
        logger.warning("[interpolation] Колонка 'belt' отсутствует — пропуск")
        return data, pd.DataFrame()

    # Определяем соседние пояса
    neighbor_belts = _find_neighbor_belts(data, target_belt, faces)

    if len(neighbor_belts) < 2:
        logger.warning(f"[interpolation] Недостаточно соседних поясов для достройки пояса {target_belt}: найдено {len(neighbor_belts)}, требуется минимум 2")
        return data, pd.DataFrame()

    # Используем первые два соседних пояса
    belt1_num = neighbor_belts[0]
    belt2_num = neighbor_belts[1]

    logger.info(f"[interpolation] Используются соседние пояса: {belt1_num} и {belt2_num} для достройки пояса {target_belt}")

    # Получаем пояса
    b1 = data[data['belt'] == belt1_num].copy()
    b2 = data[data['belt'] == belt2_num].copy()

    if b1.empty or b2.empty:
        logger.warning(f"[interpolation] Недостаточно данных по поясам: belt{belt1_num}={len(b1)}, belt{belt2_num}={len(b2)} — пропуск")
        return data, pd.DataFrame()

    # Сортируем пояса по углу
    b1_s = _sort_belt_points_geometric(b1)
    b2_s = _sort_belt_points_geometric(b2)

    # Находим соответствие между точками поясов
    matches = _match_points_between_belts(b1_s, b2_s)

    if len(matches) == 0:
        logger.warning("[interpolation] Не удалось найти соответствия между поясами, используется простое сопоставление по индексу")
        n = min(len(b1_s), len(b2_s))
        matches = [(i, i % len(b2_s)) for i in range(n)]

    logger.info(f"[interpolation] Найдено {len(matches)} соответствий между поясами {belt1_num} и {belt2_num}")

    # Интерполируем точки
    pts = []
    for i, (source_idx, target_idx) in enumerate(matches):
        p1 = b1_s.iloc[source_idx]
        p2 = b2_s.iloc[target_idx]

        p1_xyz = np.array([p1['x'], p1['y'], p1['z']], dtype=float)
        p2_xyz = np.array([p2['x'], p2['y'], p2['z']], dtype=float)

        # Определяем веса интерполяции на основе позиции целевого пояса
        # Если целевой пояс находится между belt1 и belt2, используем линейную интерполяцию
        # Предполагаем, что пояса расположены последовательно
        if abs(target_belt - belt1_num) < abs(target_belt - belt2_num):
            # Целевой пояс ближе к belt1
            weight1 = 0.7
            weight2 = 0.3
        elif abs(target_belt - belt2_num) < abs(target_belt - belt1_num):
            # Целевой пояс ближе к belt2
            weight1 = 0.3
            weight2 = 0.7
        else:
            # Целевой пояс посередине
            weight1 = 0.5
            weight2 = 0.5

        # Интерполируем координаты
        target_xyz = weight1 * p1_xyz + weight2 * p2_xyz

        row = {
            'x': float(target_xyz[0]),
            'y': float(target_xyz[1]),
            'z': float(target_xyz[2]),
            'name': f"B{target_belt}_I{i+1}",
            'belt': target_belt,
            'is_generated': True
        }
        if 'is_station' in data.columns:
            row['is_station'] = False
        pts.append(row)

    candidates = pd.DataFrame(pts)
    if candidates.empty:
        logger.warning("[interpolation] Кандидаты пусты — ничего не добавлено")
        return data, pd.DataFrame()

    # Удаление дублей и слияние
    clean = _drop_duplicates_vs_existing(data, candidates, tolerance)
    logger.info(f"[interpolation] После удаления дублей: добавляется {len(clean)} точек")

    if clean.empty:
        logger.warning("[interpolation] После удаления дублей не осталось точек для добавления")
        return data, pd.DataFrame()

    merged = pd.concat([data, clean], ignore_index=True)

    # Проверка геометрии достроенного пояса
    b_mask = (merged['belt'] == target_belt)
    if b_mask.any():
        b_target = merged[b_mask].copy()

        # Проверяем углы
        angle_check = _check_belt_angles(b_target, faces, angle_tolerance_deg=5.0)
        logger.info(f"[interpolation] Проверка углов пояса {target_belt}: {angle_check['message']}")
        if not angle_check['valid']:
            logger.warning(f"[interpolation] Углы пояса {target_belt} отклоняются от ожидаемых более чем на 5°")

        # Проверяем расстояния
        distance_check = _check_belt_distances(b_target, distance_tolerance=0.2)
        logger.info(f"[interpolation] Проверка расстояний пояса {target_belt}: {distance_check['message']}")
        if not distance_check['valid']:
            logger.warning(f"[interpolation] Расстояния между точками пояса {target_belt} неравномерны")

    return merged, clean


def complete_missing_belt_mirror(points: pd.DataFrame,
                                 faces: int,
                                 target_belt: int,
                                 point_a: np.ndarray,
                                 point_b: np.ndarray,
                                 source_belt: int = 1,
                                 tolerance: float = 0.15) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Достроение пояса через зеркальное отражение точек исходного пояса (по умолчанию 1)
    относительно вертикальной плоскости, проходящей через две заданные точки point_a и point_b.

    Плоскость: нормаль n = normalize(perp((point_b - point_a)_xy)), опорная точка p0 = point_a.
    Зеркалирование: p' = p - 2 n ((p - p0)·n). Компонента Z не меняется (n_z = 0).
    """
    logger = logging.getLogger(__name__)
    if points is None or points.empty:
        logger.warning("[mirror] Пустые входные данные — пропуск")
        return points, pd.DataFrame()
    data = points.copy()
    if 'belt' not in data.columns:
        logger.warning("[mirror] Колонка 'belt' отсутствует — пропуск")
        return data, pd.DataFrame()

    src = data[data['belt'] == source_belt].copy()
    if src.empty:
        logger.warning(f"[mirror] Исходный пояс {source_belt} пуст — пропуск")
        return data, pd.DataFrame()

    a = np.array(point_a, dtype=float)
    b = np.array(point_b, dtype=float)
    v = b[:2] - a[:2]
    if np.linalg.norm(v) < 1e-9:
        logger.warning("[mirror] Слишком близкие точки для построения плоскости — пропуск")
        return data, pd.DataFrame()
    n_xy = np.array([-v[1], v[0]], dtype=float)
    n_xy = n_xy / np.linalg.norm(n_xy)
    n = np.array([n_xy[0], n_xy[1], 0.0], dtype=float)
    p0 = np.array([a[0], a[1], 0.0], dtype=float)

    logger.info(f"[mirror] Плоскость: p0={p0.tolist()}, n={n.tolist()}, target_belt={target_belt}, source_belt={source_belt}")

    pts = []
    for i, row in src.reset_index(drop=True).iterrows():
        p = np.array([row['x'], row['y'], row['z']], dtype=float)
        w = np.array([p[0] - p0[0], p[1] - p0[1], 0.0], dtype=float)
        proj = float(np.dot(w, n))
        p_mirror_xy = np.array([p[0], p[1], 0.0], dtype=float) - 2.0 * proj * n
        p_new = np.array([p_mirror_xy[0], p_mirror_xy[1], p[2]], dtype=float)
        if i < 5:
            logger.debug(f"[mirror] i={i}: src={p.tolist()} -> dst={p_new.tolist()}")
        pts.append({
            'x': float(p_new[0]),
            'y': float(p_new[1]),
            'z': float(p_new[2]),
            'name': f"B{target_belt}_G{i+1}",
            'belt': target_belt,
            'is_generated': True,
        })

    candidates = pd.DataFrame(pts)
    if candidates.empty:
        logger.warning("[mirror] Кандидаты пусты — ничего не добавлено")
        return data, pd.DataFrame()

    clean = _drop_duplicates_vs_existing(data, candidates, tolerance)
    logger.info(f"[mirror] Зеркально сгенерировано: всего={len(candidates)}, к добавлению={len(clean)}")
    merged = pd.concat([data, clean], ignore_index=True)
    return merged, clean


def _project_point_to_xy(point_3d: np.ndarray) -> np.ndarray:
    """
    Проецирует точку на плоскость XY, игнорируя Z координату.

    Args:
        point_3d: Точка в 3D [x, y, z] или [x, y]

    Returns:
        Точка в плоскости XY [x, y]
    """
    if len(point_3d) >= 2:
        return np.array([point_3d[0], point_3d[1]], dtype=float)
    return point_3d.copy()


def _project_direction_to_xy(direction: np.ndarray) -> np.ndarray:
    """
    Проецирует направление на плоскость XY, гарантируя, что Z компонента равна 0.

    Args:
        direction: Вектор направления [dx, dy, dz] или [dx, dy]

    Returns:
        Вектор направления в плоскости XY [dx, dy] (нормализованный)
    """
    if len(direction) >= 2:
        dir_xy = np.array([direction[0], direction[1]], dtype=float)
        norm = np.linalg.norm(dir_xy)
        if norm < 1e-9:
            return np.array([1.0, 0.0])  # fallback
        return dir_xy / norm
    return direction.copy()


def _find_line_intersection_xy(
    line1_start: np.ndarray,
    line1_dir: np.ndarray,
    line2_start: np.ndarray,
    line2_dir: np.ndarray,
    eps: float = 1e-9
) -> np.ndarray | None:
    """
    Находит пересечение двух линий в плоскости XY.

    Линии заданы как:
    - Линия 1: line1_start + t * line1_dir
    - Линия 2: line2_start + s * line2_dir

    Все координаты должны быть в плоскости XY (только X и Y компоненты).

    Args:
        line1_start: Начальная точка первой линии [x, y]
        line1_dir: Направление первой линии [dx, dy] (нормализованное)
        line2_start: Начальная точка второй линии [x, y]
        line2_dir: Направление второй линии [dx, dy] (нормализованное)
        eps: Точность для проверки параллельности

    Returns:
        Точка пересечения [x, y] или None, если линии параллельны
    """
    # Явно проецируем на плоскость XY
    p = _project_point_to_xy(line1_start)
    d = _project_direction_to_xy(line1_dir)
    q = _project_point_to_xy(line2_start)
    e = _project_direction_to_xy(line2_dir)

    # Проверяем, что направления нормализованы
    d_norm = np.linalg.norm(d)
    e_norm = np.linalg.norm(e)
    if d_norm < eps or e_norm < eps:
        logger.warning(f"[intersection_xy] Нулевое направление: d_norm={d_norm}, e_norm={e_norm}")
        return None

    # Решаем систему: p + t*d = q + s*e
    # Преобразуем в: t*d - s*e = q - p
    A = np.array([[d[0], -e[0]], [d[1], -e[1]]], dtype=float)
    b = q - p
    det = np.linalg.det(A)

    if abs(det) < eps:
        # Линии параллельны или почти параллельны
        logger.debug(f"[intersection_xy] Линии параллельны: det={det:.2e}")
        return None

    try:
        sol = np.linalg.solve(A, b)
        t = sol[0]

        # Вычисляем точку пересечения на первой линии
        intersection = p + t * d

        # Валидация: проверяем, что точка действительно на второй линии
        # Вычисляем параметр s для второй линии
        diff = intersection - q
        if np.linalg.norm(e) > eps:
            # Проекция на направление второй линии
            s = np.dot(diff, e) / np.linalg.norm(e)
            # Проверяем, что точка близка ко второй линии
            point_on_line2 = q + s * e
            dist_to_line2 = np.linalg.norm(intersection - point_on_line2)

            if dist_to_line2 > eps * 10:
                logger.warning(f"[intersection_xy] Точка пересечения не на второй линии: dist={dist_to_line2:.2e}")
                return None

        return intersection
    except np.linalg.LinAlgError:
        logger.warning("[intersection_xy] Ошибка при решении системы уравнений")
        return None


def _line_intersection_2d(p: np.ndarray, d: np.ndarray, q: np.ndarray, e: np.ndarray) -> np.ndarray | None:
    """
    Пересечение двух линий p + t d и q + s e в 2D; возвращает точку или None (почти параллельны).

    Устаревшая функция, используйте _find_line_intersection_xy для явной работы в плоскости XY.
    """
    return _find_line_intersection_xy(p, d, q, e)


def complete_missing_belt_parallel(points: pd.DataFrame,
                                   faces: int,
                                   target_belt: int,
                                   dir1_xy: np.ndarray,
                                   dir2_xy: np.ndarray,
                                   tolerance: float = 0.15) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Достроить недостающий пояс через пересечения параллельных линий к двум заданным направлениям.
    dir1_xy, dir2_xy — направления (в XY) для 1-й и 2-й групп соответственно.
    Возвращает (merged_points, generated_points).
    """
    if points is None or points.empty:
        return points, pd.DataFrame()
    data = points.copy()
    if 'belt' not in data.columns:
        return data, pd.DataFrame()
    # соседи
    prev_belt = target_belt - 1 if target_belt > 1 else faces
    next_belt = target_belt + 1 if target_belt < faces else 1
    belt_prev = data[data['belt'] == prev_belt].copy()
    belt_next = data[data['belt'] == next_belt].copy()
    if belt_prev.empty or belt_next.empty:
        return data, pd.DataFrame()
    # нормализуем направления
    d1 = np.array([dir1_xy[0], dir1_xy[1]], dtype=float)
    d2 = np.array([dir2_xy[0], dir2_xy[1]], dtype=float)
    if np.linalg.norm(d1) < 1e-9 or np.linalg.norm(d2) < 1e-9:
        return data, pd.DataFrame()
    d1 = d1 / np.linalg.norm(d1)
    d2 = d2 / np.linalg.norm(d2)
    # сортировка точек в каждом поясе по углу вокруг их центроидов для грубого соответствия индексов
    def sort_belt(belt_df: pd.DataFrame) -> pd.DataFrame:
        return sort_points_clockwise(
            belt_df,
            station_xy=extract_reference_station_xy(data),
        ).reset_index(drop=True)
    belt_prev_s = sort_belt(belt_prev)
    belt_next_s = sort_belt(belt_next)
    n = min(len(belt_prev_s), len(belt_next_s))
    # пересечения
    pts = []
    for i in range(n):
        a = belt_prev_s.iloc[i]
        c = belt_next_s.iloc[i]
        p = np.array([a['x'], a['y']], dtype=float)
        q = np.array([c['x'], c['y']], dtype=float)
        inter = _line_intersection_2d(p, d1, q, d2)
        if inter is None:
            # fallback: взять среднюю точку по XY
            inter = (p + q) / 2.0
        row = {
            'x': float(inter[0]),
            'y': float(inter[1]),
            'z': float(a['z']),  # временно, выровняем ниже
            'name': f"B{target_belt}_G{i+1}",
            'belt': target_belt,
            'is_generated': True
        }
        pts.append(row)
    candidates = pd.DataFrame(pts)
    # Выравнивание Z по поясу 1
    z_levels = _get_belt_levels(data, 1)
    if not candidates.empty and len(z_levels) > 0:
        candidates['z'] = _snap_z(candidates['z'].values, z_levels)
    # Удаление дублей и слияние
    clean = _drop_duplicates_vs_existing(data, candidates, tolerance)
    merged = pd.concat([data, clean], ignore_index=True)
    return merged, clean


def _sort_belt_points_geometric(belt_df: pd.DataFrame, preserve_index: bool = False) -> pd.DataFrame:
    """
    Сортирует точки пояса по углу относительно центра пояса.

    Алгоритм:
    1. Вычисляет центр пояса в плоскости XY
    2. Вычисляет углы всех точек относительно центра
    3. Сортирует точки по углу (от 0 до 2π)
    4. Нормализует углы к диапазону [0, 2π]

    Args:
        belt_df: DataFrame с точками пояса (колонки: x, y, z)
        preserve_index: Если True, сохраняет исходные индексы (не сбрасывает их)

    Returns:
        Отсортированный DataFrame с точками пояса
    """
    if belt_df.empty:
        return belt_df.copy()

    return sort_points_clockwise(
        belt_df,
        preserve_index=preserve_index,
    )

    # Вычисляем центр пояса в плоскости XY
    center = belt_df[['x', 'y']].mean().values

    # Вычисляем углы всех точек относительно центра
    xy_points = belt_df[['x', 'y']].values
    angles = np.arctan2(xy_points[:, 1] - center[1], xy_points[:, 0] - center[0])

    # Нормализуем углы к диапазону [0, 2π]
    angles = angles % (2 * np.pi)

    # Сортируем по углу
    order = np.argsort(angles)

    if preserve_index:
        # Сохраняем исходные индексы
        return belt_df.iloc[order]
    else:
        # Сбрасываем индексы
        return belt_df.iloc[order].reset_index(drop=True)


def _get_belt_face_direction(belt_df: pd.DataFrame, point_idx: int) -> np.ndarray:
    """
    Определяет направление грани пояса от точки с индексом point_idx к следующей точке.

    Грань - это линия между соседними точками пояса, образующая замкнутый многоугольник.
    Для последней точки грань идет к первой точке (замкнутость пояса).

    Args:
        belt_df: DataFrame с точками пояса, отсортированный по углу (должен быть отсортирован)
        point_idx: Индекс точки в отсортированном DataFrame (позиционный индекс, не индекс DataFrame)

    Returns:
        Нормализованный вектор направления грани в плоскости XY [dx, dy]
    """
    if belt_df.empty or point_idx < 0 or point_idx >= len(belt_df):
        return np.array([1.0, 0.0])  # fallback: направление по оси X

    # Получаем текущую точку
    current_point = belt_df.iloc[point_idx]
    current_xy = np.array([current_point['x'], current_point['y']], dtype=float)

    # Определяем следующую точку (с учетом замкнутости)
    next_idx = (point_idx + 1) % len(belt_df)
    next_point = belt_df.iloc[next_idx]
    next_xy = np.array([next_point['x'], next_point['y']], dtype=float)

    # Вычисляем направление грани
    face_direction = next_xy - current_xy
    norm = np.linalg.norm(face_direction)

    if norm < 1e-9:
        # Точки слишком близки, возвращаем fallback
        return np.array([1.0, 0.0])

    # Нормализуем вектор
    return face_direction / norm


def _get_face_bisector(belt_df: pd.DataFrame, point_idx: int) -> np.ndarray:
    """
    Вычисляет биссектрису угла между гранями для точки с индексом point_idx.

    Для правильной усеченной пирамиды перпендикуляр должен быть направлен к биссектрисе
    угла между гранями (к центру следующего угла многоугольника).

    Args:
        belt_df: DataFrame с точками пояса, отсортированный по углу (должен быть отсортирован)
        point_idx: Индекс точки в отсортированном DataFrame (позиционный индекс, не индекс DataFrame)

    Returns:
        Нормализованный вектор биссектрисы угла между гранями в плоскости XY [dx, dy]
    """
    if belt_df.empty or point_idx < 0 or point_idx >= len(belt_df):
        return np.array([1.0, 0.0])  # fallback

    if len(belt_df) < 2:
        return np.array([1.0, 0.0])  # fallback

    # Получаем текущую точку
    current_point = belt_df.iloc[point_idx]
    current_xy = np.array([current_point['x'], current_point['y']], dtype=float)

    # Определяем предыдущую точку (с учетом замкнутости)
    prev_idx = (point_idx - 1) % len(belt_df)
    prev_point = belt_df.iloc[prev_idx]
    prev_xy = np.array([prev_point['x'], prev_point['y']], dtype=float)

    # Определяем следующую точку (с учетом замкнутости)
    next_idx = (point_idx + 1) % len(belt_df)
    next_point = belt_df.iloc[next_idx]
    next_xy = np.array([next_point['x'], next_point['y']], dtype=float)

    # Вычисляем направление предыдущей грани (от предыдущей точки к текущей)
    face_dir_prev = current_xy - prev_xy
    norm_prev = np.linalg.norm(face_dir_prev)
    if norm_prev < 1e-9:
        return np.array([1.0, 0.0])  # fallback
    face_dir_prev = face_dir_prev / norm_prev

    # Вычисляем направление текущей грани (от текущей точки к следующей)
    face_dir_current = next_xy - current_xy
    norm_current = np.linalg.norm(face_dir_current)
    if norm_current < 1e-9:
        return np.array([1.0, 0.0])  # fallback
    face_dir_current = face_dir_current / norm_current

    # Вычисляем биссектрису угла между гранями
    # Биссектриса = нормализованная сумма направлений граней
    bisector = face_dir_prev + face_dir_current
    norm_bisector = np.linalg.norm(bisector)

    if norm_bisector < 1e-9:
        # Грани противоположны, биссектриса перпендикулярна
        bisector = np.array([-face_dir_current[1], face_dir_current[0]])
        norm_bisector = np.linalg.norm(bisector)
        if norm_bisector < 1e-9:
            return np.array([1.0, 0.0])  # fallback

    return bisector / norm_bisector


def _build_perpendicular_line(point_xy: np.ndarray, bisector: np.ndarray, center_xy: np.ndarray | None = None) -> np.ndarray:
    """
    Строит направление линии перпендикулярно биссектрисе угла между гранями.

    Для правильной усеченной пирамиды перпендикуляр должен быть направлен к биссектрисе
    угла между гранями (к центру следующего угла многоугольника), а затем повернут
    на 90 градусов для получения направления наружу от центра.

    Args:
        point_xy: Координаты точки в плоскости XY [x, y]
        bisector: Нормализованный вектор биссектрисы угла между гранями [dx, dy]
        center_xy: Опциональные координаты центра пояса для определения правильного направления

    Returns:
        Нормализованный вектор направления перпендикуляра [dx, dy], направленный наружу от центра
    """
    # Перпендикуляр к биссектрисе = поворот биссектрисы на 90 градусов
    # Используем два варианта поворота (по и против часовой стрелки)
    rotation_90_ccw = np.array([
        [0.0, -1.0],
        [1.0, 0.0]
    ])
    rotation_90_cw = np.array([
        [0.0, 1.0],
        [-1.0, 0.0]
    ])

    # Вычисляем оба варианта перпендикуляра
    perp_direction_ccw = rotation_90_ccw @ bisector
    perp_direction_cw = rotation_90_cw @ bisector

    # Выбираем правильное направление на основе центра (если указан)
    if center_xy is not None:
        # Вектор от центра к точке (радиус-вектор, направлен наружу)
        radius_vector = point_xy - center_xy
        radius_norm = np.linalg.norm(radius_vector)
        if radius_norm > 1e-9:
            radius_vector = radius_vector / radius_norm

            # Для правильной пирамиды перпендикуляр должен быть направлен наружу от центра
            # Выбираем вариант, который больше направлен наружу (имеет большее скалярное произведение с радиусом)
            dot_ccw = np.dot(perp_direction_ccw, radius_vector)
            dot_cw = np.dot(perp_direction_cw, radius_vector)

            # Выбираем вариант, который больше направлен наружу (положительное скалярное произведение)
            if dot_ccw >= 0 and dot_cw >= 0:
                # Оба направлены наружу, выбираем тот, который больше
                perp_direction = perp_direction_ccw if dot_ccw >= dot_cw else perp_direction_cw
            elif dot_ccw >= 0:
                # Только ccw направлен наружу
                perp_direction = perp_direction_ccw
            elif dot_cw >= 0:
                # Только cw направлен наружу
                perp_direction = perp_direction_cw
            else:
                # Оба направлены к центру, выбираем тот, который меньше направлен к центру
                perp_direction = perp_direction_ccw if abs(dot_ccw) < abs(dot_cw) else perp_direction_cw
                # Разворачиваем, чтобы направить наружу
                perp_direction = -perp_direction
                logger.debug(f"[build_perp] Оба варианта были направлены к центру, развернут: dot_ccw={dot_ccw:.3f}, dot_cw={dot_cw:.3f}")
        else:
            perp_direction = perp_direction_ccw  # fallback
    else:
        perp_direction = perp_direction_ccw  # fallback

    # Дополнительная проверка: убеждаемся, что перпендикуляр направлен наружу от центра
    if center_xy is not None:
        radius_vector = point_xy - center_xy
        radius_norm = np.linalg.norm(radius_vector)
        if radius_norm > 1e-9:
            radius_vector = radius_vector / radius_norm
            dot_product = np.dot(perp_direction, radius_vector)

            # Если перпендикуляр все еще направлен к центру, разворачиваем
            if dot_product < 0:
                perp_direction = -perp_direction
                logger.debug(f"[build_perp] Развернут перпендикуляр: dot={dot_product:.3f}, было направлено к центру")

    # Нормализуем (на всякий случай)
    norm = np.linalg.norm(perp_direction)
    if norm < 1e-9:
        # Если получился нулевой вектор, возвращаем перпендикуляр напрямую
        perp_direction = np.array([-bisector[1], bisector[0]])
        norm = np.linalg.norm(perp_direction)
        if norm < 1e-9:
            return np.array([1.0, 0.0])  # fallback

    return perp_direction / norm


def _find_corresponding_point_on_belt1(
    neighbor_point: pd.Series,
    neighbor_belt_sorted: pd.DataFrame,
    belt1_sorted: pd.DataFrame,
    neighbor_belt_center: np.ndarray,
    belt1_center: np.ndarray
) -> tuple[int, pd.Series]:
    """
    Находит соответствующую точку на поясе 1 для точки соседнего пояса.

    Использует геометрическое сопоставление:
    - Угол относительно центра пояса (основной критерий)
    - Расстояние от центра (вторичный критерий)

    Args:
        neighbor_point: Точка на соседнем поясе (Series с x, y, z)
        neighbor_belt_sorted: Отсортированный DataFrame соседнего пояса
        belt1_sorted: Отсортированный DataFrame пояса 1
        neighbor_belt_center: Центр соседнего пояса [x, y]
        belt1_center: Центр пояса 1 [x, y]

    Returns:
        Кортеж (index, point): позиционный индекс и точка на поясе 1
    """
    if belt1_sorted.empty:
        raise ValueError("Пояс 1 пуст")

    # Вычисляем угол точки соседнего пояса относительно центра соседнего пояса
    neighbor_xy = np.array([neighbor_point['x'], neighbor_point['y']])
    neighbor_angle = np.arctan2(
        neighbor_xy[1] - neighbor_belt_center[1],
        neighbor_xy[0] - neighbor_belt_center[0]
    )
    neighbor_angle = neighbor_angle % (2 * np.pi)

    # Вычисляем расстояние от центра
    neighbor_distance = np.linalg.norm(neighbor_xy - neighbor_belt_center)

    # Нормализуем расстояния для метрики
    belt1_distances = np.linalg.norm(belt1_sorted[['x', 'y']].values - belt1_center, axis=1)
    max_distance = np.max(belt1_distances) if len(belt1_distances) > 0 else 1.0
    if max_distance < 1e-9:
        max_distance = 1.0

    # Ищем точку на поясе 1 с наиболее близким углом
    best_score = float('inf')
    best_idx = 0

    for idx, (_, belt1_point) in enumerate(belt1_sorted.iterrows()):
        belt1_xy = np.array([belt1_point['x'], belt1_point['y']])

        # Угол относительно центра пояса 1
        belt1_angle = np.arctan2(
            belt1_xy[1] - belt1_center[1],
            belt1_xy[0] - belt1_center[0]
        )
        belt1_angle = belt1_angle % (2 * np.pi)

        # Разница углов (учитываем циклическую природу)
        angle_diff = abs(belt1_angle - neighbor_angle)
        angle_diff = min(angle_diff, 2 * np.pi - angle_diff)
        angle_score = angle_diff / np.pi  # Нормализуем к [0, 1]

        # Разница расстояний
        belt1_distance = np.linalg.norm(belt1_xy - belt1_center)
        distance_diff = abs(belt1_distance - neighbor_distance) / max_distance
        distance_score = min(distance_diff, 1.0)

        # Комбинированная метрика (угол важнее расстояния)
        total_score = 0.7 * angle_score + 0.3 * distance_score

        if total_score < best_score:
            best_score = total_score
            best_idx = idx

    logger.debug(
        f"[find_corresponding] neighbor_angle={np.degrees(neighbor_angle):.1f}°, "
        f"best_idx={best_idx}, best_score={best_score:.4f}"
    )

    return best_idx, belt1_sorted.iloc[best_idx]


def _find_corresponding_point(
    source_point: pd.Series,
    target_belt_df: pd.DataFrame,
    weight_angle: float = 0.4,
    weight_distance: float = 0.4,
    weight_height: float = 0.2
) -> tuple[int, pd.Series]:
    """
    Находит соответствующую точку на целевом поясе для заданной точки исходного пояса.

    Использует комбинированную метрику:
    - Угол относительно центра пояса (weight_angle)
    - Расстояние от центра пояса (weight_distance)
    - Высота точки (weight_height)

    Args:
        source_point: Точка исходного пояса (Series с x, y, z)
        target_belt_df: DataFrame с точками целевого пояса
        weight_angle: Вес угла в метрике (по умолчанию 0.4)
        weight_distance: Вес расстояния в метрике (по умолчанию 0.4)
        weight_height: Вес высоты в метрике (по умолчанию 0.2)

    Returns:
        Кортеж (index, point): индекс и точка на целевом поясе
    """
    if target_belt_df.empty:
        raise ValueError("Целевой пояс пуст")

    # Вычисляем центр исходного пояса (для нормализации)
    source_xy = np.array([source_point['x'], source_point['y']])

    # Вычисляем центр целевого пояса
    target_center = target_belt_df[['x', 'y']].mean().values

    # Вычисляем характеристики исходной точки
    source_angle = np.arctan2(source_xy[1] - target_center[1], source_xy[0] - target_center[0])
    source_angle = source_angle % (2 * np.pi)
    source_distance = np.linalg.norm(source_xy - target_center)
    source_height = float(source_point['z'])

    # Нормализуем расстояния для метрики
    target_distances = np.linalg.norm(target_belt_df[['x', 'y']].values - target_center, axis=1)
    max_distance = np.max(target_distances) if len(target_distances) > 0 else 1.0
    if max_distance < 1e-9:
        max_distance = 1.0

    # Вычисляем метрику для каждой точки целевого пояса
    best_score = float('inf')
    best_idx = 0

    for idx, (_, target_point) in enumerate(target_belt_df.iterrows()):
        target_xy = np.array([target_point['x'], target_point['y']])

        # Угол относительно центра
        target_angle = np.arctan2(target_xy[1] - target_center[1], target_xy[0] - target_center[0])
        target_angle = target_angle % (2 * np.pi)

        # Разница углов (учитываем циклическую природу)
        angle_diff = abs(target_angle - source_angle)
        angle_diff = min(angle_diff, 2 * np.pi - angle_diff)
        angle_score = angle_diff / np.pi  # Нормализуем к [0, 1]

        # Разница расстояний
        target_distance = np.linalg.norm(target_xy - target_center)
        distance_diff = abs(target_distance - source_distance) / max_distance
        distance_score = min(distance_diff, 1.0)  # Ограничиваем до 1

        # Разница высот
        target_height = float(target_point['z'])
        height_diff = abs(target_height - source_height)
        # Нормализуем высоту (предполагаем, что разница высот не превышает 100 м)
        height_score = min(height_diff / 100.0, 1.0)

        # Комбинированная метрика
        total_score = (
            weight_angle * angle_score +
            weight_distance * distance_score +
            weight_height * height_score
        )

        if total_score < best_score:
            best_score = total_score
            best_idx = idx

    return best_idx, target_belt_df.iloc[best_idx]


def _match_points_between_belts(
    source_belt_df: pd.DataFrame,
    target_belt_df: pd.DataFrame,
    weight_angle: float = 0.4,
    weight_distance: float = 0.4,
    weight_height: float = 0.2
) -> list[tuple[int, int]]:
    """
    Находит соответствие между точками двух поясов.

    Использует жадный алгоритм для оптимального сопоставления:
    1. Для каждой точки исходного пояса находит ближайшую точку на целевом поясе
    2. Использует комбинированную метрику (угол, расстояние, высота)
    3. Учитывает циклическую природу пояса

    Args:
        source_belt_df: DataFrame с точками исходного пояса
        target_belt_df: DataFrame с точками целевого пояса
        weight_angle: Вес угла в метрике (по умолчанию 0.4)
        weight_distance: Вес расстояния в метрике (по умолчанию 0.4)
        weight_height: Вес высоты в метрике (по умолчанию 0.2)

    Returns:
        Список кортежей (source_idx, target_idx) - соответствия между точками
    """
    if source_belt_df.empty or target_belt_df.empty:
        return []

    # Сортируем оба пояса по углу для лучшего сопоставления
    source_sorted = _sort_belt_points_geometric(source_belt_df)
    target_sorted = _sort_belt_points_geometric(target_belt_df)

    matches = []
    used_target_indices = set()

    # Для каждой точки исходного пояса находим соответствующую точку на целевом
    for source_idx, (_, source_point) in enumerate(source_sorted.iterrows()):
        # Находим все возможные соответствия
        candidate_scores = []

        for target_idx, (_, target_point) in enumerate(target_sorted.iterrows()):
            if target_idx in used_target_indices:
                continue

            # Вычисляем метрику соответствия
            source_xy = np.array([source_point['x'], source_point['y']])
            target_xy = np.array([target_point['x'], target_point['y']])

            # Центр для нормализации
            center = target_sorted[['x', 'y']].mean().values

            # Угол
            source_angle = np.arctan2(source_xy[1] - center[1], source_xy[0] - center[0]) % (2 * np.pi)
            target_angle = np.arctan2(target_xy[1] - center[1], target_xy[0] - center[0]) % (2 * np.pi)
            angle_diff = abs(target_angle - source_angle)
            angle_diff = min(angle_diff, 2 * np.pi - angle_diff)
            angle_score = angle_diff / np.pi

            # Расстояние
            source_dist = np.linalg.norm(source_xy - center)
            target_dist = np.linalg.norm(target_xy - center)
            max_dist = max(source_dist, target_dist, 1.0)
            distance_score = abs(source_dist - target_dist) / max_dist

            # Высота
            height_score = abs(float(source_point['z']) - float(target_point['z'])) / 100.0
            height_score = min(height_score, 1.0)

            # Комбинированная метрика
            total_score = (
                weight_angle * angle_score +
                weight_distance * distance_score +
                weight_height * height_score
            )

            candidate_scores.append((target_idx, total_score))

        # Выбираем лучшее соответствие
        if candidate_scores:
            candidate_scores.sort(key=lambda x: x[1])
            best_target_idx, best_score = candidate_scores[0]

            # Используем соответствие только если метрика достаточно хорошая
            if best_score < 0.5:  # Порог для хорошего соответствия
                matches.append((source_idx, best_target_idx))
                used_target_indices.add(best_target_idx)
            else:
                # Если соответствие плохое, используем циклическое соответствие
                target_idx = source_idx % len(target_sorted)
                if target_idx not in used_target_indices:
                    matches.append((source_idx, target_idx))
                    used_target_indices.add(target_idx)

    return matches


def _calculate_belt_angles(belt_df: pd.DataFrame) -> np.ndarray:
    """
    Вычисляет углы между соседними точками пояса в плоскости XY.

    Args:
        belt_df: DataFrame с точками пояса (должен быть отсортирован по углу)

    Returns:
        Массив углов в градусах между соседними точками (включая циклический переход)
    """
    if len(belt_df) < 2:
        return np.array([])

    # Получаем координаты точек
    xy_points = belt_df[['x', 'y']].values
    center = xy_points.mean(axis=0)

    # Вычисляем углы для всех точек
    angles = []
    for xy in xy_points:
        dx = xy[0] - center[0]
        dy = xy[1] - center[1]
        angle = np.arctan2(dy, dx)
        angles.append(angle)

    angles = np.array(angles)
    angles = angles % (2 * np.pi)

    # Вычисляем углы между соседними точками
    angle_diffs = []
    for i in range(len(angles)):
        next_i = (i + 1) % len(angles)
        diff = angles[next_i] - angles[i]
        # Нормализуем к диапазону [0, 2π]
        if diff < 0:
            diff += 2 * np.pi
        angle_diffs.append(diff)

    # Конвертируем в градусы
    return np.degrees(angle_diffs)


def _check_belt_angles(belt_df: pd.DataFrame, faces: int, angle_tolerance_deg: float = 5.0) -> dict:
    """
    Проверяет правильность углов между соседними точками пояса.

    Args:
        belt_df: DataFrame с точками пояса
        faces: Количество граней башни (ожидаемый угол = 360° / faces)
        angle_tolerance_deg: Допустимое отклонение угла в градусах

    Returns:
        Словарь с результатами проверки
    """
    if len(belt_df) < 2:
        return {
            'valid': False,
            'expected_angle': 360.0 / faces if faces > 0 else 0.0,
            'mean_angle': 0.0,
            'mean_deviation': 0.0,
            'max_deviation': 0.0,
            'angles': np.array([]),
            'message': 'Недостаточно точек для проверки углов'
        }

    # Сортируем точки по углу
    sorted_belt = _sort_belt_points_geometric(belt_df)

    # Вычисляем углы
    angles_deg = _calculate_belt_angles(sorted_belt)

    if len(angles_deg) == 0:
        return {
            'valid': False,
            'expected_angle': 360.0 / faces if faces > 0 else 0.0,
            'mean_angle': 0.0,
            'mean_deviation': 0.0,
            'max_deviation': 0.0,
            'angles': np.array([]),
            'message': 'Не удалось вычислить углы'
        }

    # Ожидаемый угол
    expected_angle = 360.0 / faces if faces > 0 else 0.0

    # Вычисляем отклонения
    deviations = np.abs(angles_deg - expected_angle)
    mean_angle = np.mean(angles_deg)
    mean_deviation = np.mean(deviations)
    max_deviation = np.max(deviations)

    # Проверяем валидность
    valid = max_deviation <= angle_tolerance_deg

    result = {
        'valid': valid,
        'expected_angle': expected_angle,
        'mean_angle': mean_angle,
        'mean_deviation': mean_deviation,
        'max_deviation': max_deviation,
        'angles': angles_deg,
        'message': f"Ожидаемый угол: {expected_angle:.2f}°, средний: {mean_angle:.2f}°, максимальное отклонение: {max_deviation:.2f}°"
    }

    if not valid:
        result['message'] += f" (превышен порог {angle_tolerance_deg}°)"

    return result


def _calculate_belt_distances(belt_df: pd.DataFrame) -> np.ndarray:
    """
    Вычисляет расстояния между соседними точками пояса в плоскости XY.

    Args:
        belt_df: DataFrame с точками пояса (должен быть отсортирован по углу)

    Returns:
        Массив расстояний между соседними точками (включая циклический переход)
    """
    if len(belt_df) < 2:
        return np.array([])

    # Получаем координаты точек
    xy_points = belt_df[['x', 'y']].values

    # Вычисляем расстояния между соседними точками
    distances = []
    for i in range(len(xy_points)):
        next_i = (i + 1) % len(xy_points)
        dist = np.linalg.norm(xy_points[next_i] - xy_points[i])
        distances.append(dist)

    return np.array(distances)


def _check_belt_distances(belt_df: pd.DataFrame, distance_tolerance: float = 0.2) -> dict:
    """
    Проверяет равномерность расстояний между соседними точками пояса.

    Args:
        belt_df: DataFrame с точками пояса
        distance_tolerance: Коэффициент вариации для проверки равномерности (0.2 = 20%)

    Returns:
        Словарь с результатами проверки
    """
    if len(belt_df) < 2:
        return {
            'valid': False,
            'mean_distance': 0.0,
            'std_distance': 0.0,
            'coefficient_of_variation': 0.0,
            'distances': np.array([]),
            'message': 'Недостаточно точек для проверки расстояний'
        }

    # Сортируем точки по углу
    sorted_belt = _sort_belt_points_geometric(belt_df)

    # Вычисляем расстояния
    distances = _calculate_belt_distances(sorted_belt)

    if len(distances) == 0:
        return {
            'valid': False,
            'mean_distance': 0.0,
            'std_distance': 0.0,
            'coefficient_of_variation': 0.0,
            'distances': np.array([]),
            'message': 'Не удалось вычислить расстояния'
        }

    # Вычисляем статистику
    mean_distance = np.mean(distances)
    std_distance = np.std(distances)

    # Коэффициент вариации
    if mean_distance > 1e-9:
        coefficient_of_variation = std_distance / mean_distance
    else:
        coefficient_of_variation = float('inf')

    # Проверяем валидность
    valid = coefficient_of_variation <= distance_tolerance

    result = {
        'valid': valid,
        'mean_distance': mean_distance,
        'std_distance': std_distance,
        'coefficient_of_variation': coefficient_of_variation,
        'distances': distances,
        'message': f"Среднее расстояние: {mean_distance:.3f} м, коэффициент вариации: {coefficient_of_variation:.3f}"
    }

    if not valid:
        result['message'] += f" (превышен порог {distance_tolerance})"

    return result


def _diagnose_belt_quality(
    belt_df: pd.DataFrame,
    faces: int,
    angle_tolerance_deg: float = 5.0,
    distance_tolerance: float = 0.2
) -> dict:
    """
    Вычисляет все метрики качества достроенного пояса.

    Метрики:
    - Углы между соседними точками (отклонение от идеальных)
    - Расстояния между соседними точками (равномерность)
    - Правильность формы (близость к правильному многоугольнику)

    Args:
        belt_df: DataFrame с точками пояса
        faces: Количество граней башни
        angle_tolerance_deg: Допустимое отклонение угла в градусах
        distance_tolerance: Коэффициент вариации для расстояний

    Returns:
        Словарь с метриками качества и общей оценкой
    """
    if len(belt_df) < 2:
        return {
            'quality': 'poor',
            'angle_check': {},
            'distance_check': {},
            'metrics': {},
            'recommendations': ['Недостаточно точек для оценки качества'],
            'message': 'Недостаточно точек для оценки качества пояса'
        }

    # Проверяем углы
    angle_check = _check_belt_angles(belt_df, faces, angle_tolerance_deg)

    # Проверяем расстояния
    distance_check = _check_belt_distances(belt_df, distance_tolerance)

    # Вычисляем общую оценку качества
    quality_score = 0.0
    max_score = 2.0

    if angle_check.get('valid', False):
        quality_score += 1.0
    elif angle_check.get('max_deviation', float('inf')) <= angle_tolerance_deg * 1.5:
        quality_score += 0.5  # Частично валидно

    if distance_check.get('valid', False):
        quality_score += 1.0
    elif distance_check.get('coefficient_of_variation', float('inf')) <= distance_tolerance * 1.5:
        quality_score += 0.5  # Частично валидно

    # Определяем общую оценку
    quality_ratio = quality_score / max_score
    if quality_ratio >= 0.9:
        quality = 'excellent'
    elif quality_ratio >= 0.7:
        quality = 'good'
    elif quality_ratio >= 0.5:
        quality = 'satisfactory'
    else:
        quality = 'poor'

    # Формируем рекомендации
    recommendations = []
    if not angle_check.get('valid', False):
        recommendations.append(f"Углы отклоняются от идеальных на {angle_check.get('max_deviation', 0):.2f}° (порог: {angle_tolerance_deg}°)")
    if not distance_check.get('valid', False):
        recommendations.append(f"Расстояния неравномерны (коэффициент вариации: {distance_check.get('coefficient_of_variation', 0):.3f}, порог: {distance_tolerance})")

    if quality == 'excellent':
        recommendations.append("Геометрия пояса отличная, дополнительных действий не требуется")
    elif quality == 'good':
        recommendations.append("Геометрия пояса хорошая, возможна небольшая ручная корректировка")
    elif quality == 'satisfactory':
        recommendations.append("Геометрия пояса удовлетворительная, рекомендуется ручная проверка и корректировка")
    else:
        recommendations.append("Геометрия пояса требует исправления, рекомендуется пересоздать пояс или использовать другой метод")

    metrics = {
        'angle_mean_deviation': angle_check.get('mean_deviation', 0.0),
        'angle_max_deviation': angle_check.get('max_deviation', 0.0),
        'distance_mean': distance_check.get('mean_distance', 0.0),
        'distance_coefficient_of_variation': distance_check.get('coefficient_of_variation', 0.0),
        'quality_score': quality_score,
        'quality_ratio': quality_ratio
    }

    message = f"Качество пояса: {quality.upper()}"
    if angle_check.get('valid', False) and distance_check.get('valid', False):
        message += " (все метрики в норме)"
    else:
        message += f" (углы: {'OK' if angle_check.get('valid', False) else 'ПРОБЛЕМА'}, расстояния: {'OK' if distance_check.get('valid', False) else 'ПРОБЛЕМА'})"

    return {
        'quality': quality,
        'angle_check': angle_check,
        'distance_check': distance_check,
        'metrics': metrics,
        'recommendations': recommendations,
        'message': message
    }


def _optimize_belt_geometry(
    belt_df: pd.DataFrame,
    faces: int,
    max_iterations: int = 10,
    convergence_threshold: float = 0.01
) -> pd.DataFrame:
    """
    Оптимизирует позиции точек пояса для достижения правильной геометрии.

    Алгоритм:
    1. Вычисляет центр и радиус пояса
    2. Определяет оптимальные углы для точек (360° / faces)
    3. Итеративно корректирует позиции точек для достижения правильных углов
    4. Сохраняет высоту точек (Z координата)

    Args:
        belt_df: DataFrame с точками пояса
        faces: Количество граней башни
        max_iterations: Максимальное количество итераций оптимизации
        convergence_threshold: Порог сходимости (изменение позиций < threshold в градусах)

    Returns:
        DataFrame с оптимизированными точками пояса
    """
    if len(belt_df) < 2 or faces <= 0:
        return belt_df.copy()

    # Сортируем точки по углу, сохраняя исходные индексы
    sorted_belt = _sort_belt_points_geometric(belt_df, preserve_index=True)

    # Вычисляем центр и радиус пояса
    xy_points = sorted_belt[['x', 'y']].values
    center = xy_points.mean(axis=0)
    distances = np.linalg.norm(xy_points - center, axis=1)
    radius = np.mean(distances)

    if radius < 1e-9:
        logger.warning("[optimize] Радиус пояса слишком мал, пропускаем оптимизацию")
        return belt_df.copy()

    # Ожидаемый угол между точками
    expected_angle_deg = 360.0 / faces
    expected_angle_rad = np.radians(expected_angle_deg)

    # Вычисляем текущие углы
    angles_rad = []
    for xy in xy_points:
        dx = xy[0] - center[0]
        dy = xy[1] - center[1]
        angle = np.arctan2(dy, dx)
        angles_rad.append(angle)

    angles_rad = np.array(angles_rad)
    angles_rad = angles_rad % (2 * np.pi)

    # Оптимизация: корректируем углы для достижения правильной геометрии
    optimized_angles = angles_rad.copy()
    prev_angles = None

    for iteration in range(max_iterations):
        # Вычисляем целевые углы (равномерно распределенные)
        target_angles = np.array([i * expected_angle_rad for i in range(len(sorted_belt))])

        # Нормализуем целевые углы к диапазону [0, 2π]
        target_angles = target_angles % (2 * np.pi)

        # Находим начальный угол для выравнивания
        # Используем первый угол как опорный
        if len(optimized_angles) > 0:
            first_angle = optimized_angles[0]
            # Выравниваем целевые углы относительно первого угла
            angle_offset = first_angle - target_angles[0]
            target_angles = (target_angles + angle_offset) % (2 * np.pi)

        # Корректируем углы (смешиваем текущие и целевые)
        # Используем весовой коэффициент для плавной коррекции
        weight = 0.3  # 30% целевого угла, 70% текущего
        for i in range(len(optimized_angles)):
            # Находим ближайший целевой угол
            angle_diffs = np.abs(target_angles - optimized_angles[i])
            angle_diffs = np.minimum(angle_diffs, 2 * np.pi - angle_diffs)
            closest_target_idx = np.argmin(angle_diffs)
            target_angle = target_angles[closest_target_idx]

            # Корректируем угол
            angle_diff = target_angle - optimized_angles[i]
            # Нормализуем разницу к [-π, π]
            if angle_diff > np.pi:
                angle_diff -= 2 * np.pi
            elif angle_diff < -np.pi:
                angle_diff += 2 * np.pi

            optimized_angles[i] = optimized_angles[i] + weight * angle_diff
            optimized_angles[i] = optimized_angles[i] % (2 * np.pi)

        # Проверяем сходимость
        if prev_angles is not None:
            angle_changes = np.abs(optimized_angles - prev_angles)
            angle_changes = np.minimum(angle_changes, 2 * np.pi - angle_changes)
            max_change = np.max(angle_changes)
            max_change_deg = np.degrees(max_change)

            if max_change_deg < convergence_threshold:
                logger.info(f"[optimize] Оптимизация сошлась за {iteration + 1} итераций (максимальное изменение: {max_change_deg:.3f}°)")
                break

        prev_angles = optimized_angles.copy()

    # Создаем оптимизированные точки
    # Сохраняем соответствие между исходными индексами и позициями в отсортированном списке
    optimized_belt = sorted_belt.copy()
    original_indices = sorted_belt.index.values  # Сохраняем исходные индексы

    for i, orig_idx in enumerate(original_indices):
        angle = optimized_angles[i]
        x_new = center[0] + radius * np.cos(angle)
        y_new = center[1] + radius * np.sin(angle)
        optimized_belt.loc[orig_idx, 'x'] = x_new
        optimized_belt.loc[orig_idx, 'y'] = y_new
        # Высота сохраняется

    logger.info(f"[optimize] Оптимизировано {len(optimized_belt)} точек пояса")

    return optimized_belt


def _find_best_intersection(
    p: np.ndarray,
    d: np.ndarray,
    polyline: np.ndarray,
    max_distance: float = 1000.0,
    eps: float = 1e-6
) -> np.ndarray | None:
    """
    Находит наиболее подходящее пересечение линии с полилинией.

    Улучшенная версия _intersect_line_with_polyline:
    - Проверяет, что пересечение находится в разумных пределах
    - Выбирает ближайшее пересечение к исходной точке
    - Обрабатывает граничные случаи (линия проходит через вершину)

    Args:
        p: Начальная точка линии
        d: Направление линии (нормализованный вектор)
        polyline: Массив точек полилинии shape (n, 2)
        max_distance: Максимальное расстояние для поиска пересечения
        eps: Точность для проверки параллельности

    Returns:
        Точка пересечения или None
    """
    if len(polyline) < 2:
        return None

    best_intersection = None
    best_t = float('inf')

    for i in range(len(polyline) - 1):
        seg_start = polyline[i]
        seg_end = polyline[i + 1]
        seg_dir = seg_end - seg_start

        # Проверка на параллельность
        if np.linalg.norm(seg_dir) < eps:
            continue

        # Решаем систему: p + t*d = seg_start + s*seg_dir
        A = np.array([[d[0], -seg_dir[0]], [d[1], -seg_dir[1]]], dtype=float)
        b = seg_start - p
        det = np.linalg.det(A)

        if abs(det) < eps:
            # Линии почти параллельны, проверяем, проходит ли линия через сегмент
            # Вычисляем расстояние от точки p до сегмента
            seg_vec = seg_dir
            seg_len = np.linalg.norm(seg_vec)
            if seg_len < eps:
                continue

            seg_vec_norm = seg_vec / seg_len
            to_seg_start = seg_start - p
            proj_len = np.dot(to_seg_start, seg_vec_norm)

            if 0 <= proj_len <= seg_len:
                # Точка проекции находится на сегменте
                proj_point = seg_start + proj_len * seg_vec_norm
                dist_to_seg = np.linalg.norm(p - proj_point)
                if dist_to_seg < eps * 10:  # Точка очень близко к сегменту
                    if proj_len < best_t:
                        best_t = proj_len
                        best_intersection = proj_point
            continue

        sol = np.linalg.solve(A, b)
        t = sol[0]
        s = sol[1]

        # Проверяем, что пересечение находится в сегменте и впереди по направлению
        if 0 <= s <= 1 and t > 0 and t < max_distance:
            inter = p + t * d
            if t < best_t:
                best_t = t
                best_intersection = inter

    return best_intersection


def _intersect_line_with_polyline(p: np.ndarray, d: np.ndarray, polyline: np.ndarray, eps: float = 1e-6) -> np.ndarray | None:
    """
    Найти пересечение прямой (p + t*d) с поли-линией в 2D.
    polyline: массив точек shape (n, 2).
    Возвращает точку пересечения или None.

    Использует улучшенный алгоритм _find_best_intersection.
    """
    return _find_best_intersection(p, d, polyline, max_distance=1000.0, eps=eps)


def _interpolate_belt_height(
    target_belt: int,
    neighbor_belts: list[int],
    data: pd.DataFrame,
    target_xy: np.ndarray
) -> float:
    """
    Интерполирует высоту точки достроенного пояса на основе соседних поясов.

    Алгоритм:
    1. Для каждого соседнего пояса находит ближайшую точку к target_xy
    2. Использует линейную интерполяцию между высотами соседних поясов
    3. Учитывает позицию целевого пояса относительно соседних

    Args:
        target_belt: Номер целевого пояса
        neighbor_belts: Список номеров соседних поясов
        data: DataFrame с точками всех поясов
        target_xy: Координаты точки в плоскости XY

    Returns:
        Интерполированная высота точки
    """
    if len(neighbor_belts) == 0:
        # Если нет соседних поясов, используем среднюю высоту всех точек
        if not data.empty:
            return float(data['z'].mean())
        return 0.0

    heights = []
    weights = []

    for neighbor_belt in neighbor_belts:
        neighbor_points = data[data['belt'] == neighbor_belt].copy()
        if neighbor_points.empty:
            continue

        # Находим ближайшую точку на соседнем поясе
        neighbor_xy = neighbor_points[['x', 'y']].values
        distances = np.linalg.norm(neighbor_xy - target_xy, axis=1)
        closest_idx = np.argmin(distances)
        closest_distance = distances[closest_idx]

        if closest_distance < 1e-9:
            # Точка совпадает, используем её высоту напрямую
            return float(neighbor_points.iloc[closest_idx]['z'])

        # Используем обратное расстояние как вес
        weight = 1.0 / (closest_distance + 1e-9)
        height = float(neighbor_points.iloc[closest_idx]['z'])

        heights.append(height)
        weights.append(weight)

    if len(heights) == 0:
        # Fallback: средняя высота всех точек
        if not data.empty:
            return float(data['z'].mean())
        return 0.0

    # Взвешенное среднее
    weights = np.array(weights)
    heights = np.array(heights)
    weights = weights / np.sum(weights)  # Нормализуем веса

    interpolated_height = np.sum(heights * weights)

    return float(interpolated_height)


def _find_neighbor_belts(
    data: pd.DataFrame,
    target_belt: int,
    faces: int
) -> list[int]:
    """
    Определяет соседние пояса для целевого пояса.

    Алгоритм:
    1. Находит все существующие пояса в данных
    2. Определяет предыдущий и следующий пояса относительно целевого
    3. Обрабатывает циклический случай (последний пояс → первый пояс)
    4. Возвращает список доступных соседних поясов

    Args:
        data: DataFrame с точками (должна быть колонка 'belt')
        target_belt: Номер целевого пояса для достройки
        faces: Общее количество поясов/граней башни

    Returns:
        Список номеров соседних поясов (минимум 2 для работы алгоритма)
    """
    if 'belt' not in data.columns:
        return []

    # Получаем все существующие пояса
    existing_belts = sorted([int(b) for b in data['belt'].dropna().unique() if pd.notna(b)])

    if target_belt in existing_belts:
        logger.warning(f"Пояс {target_belt} уже существует, не требуется достройка")
        return []

    # Определяем соседние пояса
    neighbors = []

    # Предыдущий пояс
    prev_belt = target_belt - 1 if target_belt > 1 else faces
    if prev_belt in existing_belts:
        neighbors.append(prev_belt)

    # Следующий пояс
    next_belt = target_belt + 1 if target_belt < faces else 1
    if next_belt in existing_belts:
        neighbors.append(next_belt)

    # Если есть только один соседний пояс, пытаемся найти другие близкие пояса
    if len(neighbors) < 2:
        # Ищем ближайшие пояса по номеру
        for belt_num in existing_belts:
            if belt_num not in neighbors and abs(belt_num - target_belt) <= 2:
                neighbors.append(belt_num)
                if len(neighbors) >= 2:
                    break

    # Сортируем по близости к целевому поясу
    neighbors.sort(key=lambda x: min(abs(x - target_belt), abs(x - target_belt + faces), abs(x - target_belt - faces)))

    logger.info(f"Найдены соседние пояса для пояса {target_belt}: {neighbors}")

    return neighbors


def complete_missing_belt_parallel_lines(points: pd.DataFrame,
                                         faces: int,
                                         target_belt: int,
                                         tolerance: float = 0.15) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Достроить недостающий пояс через перпендикуляры к граням от соседних поясов и пояса 1.

    Алгоритм:
    1. Явно проецирует линии на плоскость XY (линии параллельны XY, z = const)
    2. От каждой точки соседнего пояса строит линию перпендикулярно биссектрисе угла между гранями
    3. Находит соответствующую точку на поясе 1 с использованием геометрического сопоставления
    4. От соответствующей точки пояса 1 строит аналогичную линию
    5. Находит пересечение проекций этих линий в плоскости XY
    6. Берет X и Y координаты из точки пересечения
    7. Берет Z координату от соответствующей точки пояса 1

    Особенности:
    - Использует пояс 1 как эталон для высот точек
    - Линии явно проецируются на плоскость XY (игнорируя Z координаты)
    - Соответствие точек между поясами определяется геометрически (угол + расстояние от центра)
    - Перпендикуляры направлены наружу от центра для правильной геометрии усеченной пирамиды

    Args:
        points: DataFrame с точками (должна быть колонка 'belt')
        faces: Количество граней башни (3, 4, 5, 6+)
        target_belt: Номер целевого пояса для достройки
        tolerance: Допуск для удаления дублей

    Returns:
        Кортеж (merged_points, generated_points): объединенные данные и сгенерированные точки
    """
    logger = logging.getLogger(__name__)
    if points is None or points.empty:
        logger.warning("[parallel_lines] Пустые входные данные — пропуск")
        return points, pd.DataFrame()
    data = points.copy()
    if 'belt' not in data.columns:
        logger.warning("[parallel_lines] Колонка 'belt' отсутствует — пропуск")
        return data, pd.DataFrame()

    # Проверяем наличие пояса 1 (эталонного пояса для высот)
    belt1_ref = data[data['belt'] == 1].copy()
    if belt1_ref.empty:
        logger.warning("[parallel_lines] Пояс 1 отсутствует, невозможно использовать как эталон для высот")
        return data, pd.DataFrame()

    logger.info(f"[parallel_lines] Пояс 1 найден: {len(belt1_ref)} точек, будет использован как эталон для высот")

    # Определяем соседние пояса динамически (исключая достраиваемый пояс)
    neighbor_belts = _find_neighbor_belts(data, target_belt, faces)

    if len(neighbor_belts) < 1:
        logger.warning(f"[parallel_lines] Недостаточно соседних поясов для достройки пояса {target_belt}: найдено {len(neighbor_belts)}, требуется минимум 1")
        return data, pd.DataFrame()

    # Используем первый соседний пояс (не пояс 1, если он не в списке)
    neighbor_belt_num = neighbor_belts[0]

    # Если пояс 1 не в списке соседних, добавляем его для использования
    if 1 not in neighbor_belts:
        logger.info("[parallel_lines] Пояс 1 не является соседним, но будет использован как эталон для высот")

    # Получаем соседний пояс
    neighbor_belt = data[data['belt'] == neighbor_belt_num].copy()

    if neighbor_belt.empty:
        logger.warning(f"[parallel_lines] Соседний пояс {neighbor_belt_num} пуст — пропуск")
        return data, pd.DataFrame()

    # Сортируем пояса по углу для сопоставления точек
    belt1_sorted = _sort_belt_points_geometric(belt1_ref)
    neighbor_belt_sorted = _sort_belt_points_geometric(neighbor_belt)

    logger.info(f"[parallel_lines] Отсортированы пояса: пояс 1={len(belt1_sorted)}, соседний пояс {neighbor_belt_num}={len(neighbor_belt_sorted)}")

    # Вычисляем центры поясов для определения правильного направления перпендикуляра
    belt1_center = belt1_sorted[['x', 'y']].mean().values
    neighbor_belt_center = neighbor_belt_sorted[['x', 'y']].mean().values

    logger.info(f"[parallel_lines] Центры поясов: пояс 1=({belt1_center[0]:.3f}, {belt1_center[1]:.3f}), соседний пояс=({neighbor_belt_center[0]:.3f}, {neighbor_belt_center[1]:.3f})")

    # Определяем количество точек для генерации (минимум из двух поясов)
    n_points = min(len(belt1_sorted), len(neighbor_belt_sorted))

    if n_points == 0:
        logger.warning("[parallel_lines] Нет точек для генерации")
        return data, pd.DataFrame()

    logger.info(f"[parallel_lines] Будет сгенерировано {n_points} точек для пояса {target_belt}")

    # Генерируем точки целевого пояса
    pts = []
    intersections_failed = 0

    for i in range(n_points):
        # Получаем точку на соседнем поясе
        neighbor_point = neighbor_belt_sorted.iloc[i]
        neighbor_xy = _project_point_to_xy(np.array([neighbor_point['x'], neighbor_point['y']], dtype=float))

        # Находим соответствующую точку на поясе 1 с использованием геометрического сопоставления
        belt1_idx, belt1_point = _find_corresponding_point_on_belt1(
            neighbor_point,
            neighbor_belt_sorted,
            belt1_sorted,
            neighbor_belt_center,
            belt1_center
        )

        # Явно проецируем точку пояса 1 на плоскость XY
        belt1_xy = _project_point_to_xy(np.array([belt1_point['x'], belt1_point['y']], dtype=float))
        belt1_z = float(belt1_point['z'])  # Высота от соответствующей точки пояса 1

        # Вычисляем биссектрису угла между гранями для точки на соседнем поясе
        neighbor_bisector = _get_face_bisector(neighbor_belt_sorted, i)

        # Вычисляем биссектрису угла между гранями для соответствующей точки на поясе 1
        belt1_bisector = _get_face_bisector(belt1_sorted, belt1_idx)

        # Строим линию от точки соседнего пояса перпендикулярно биссектрисе
        # Перпендикуляр направлен наружу от центра для правильной геометрии усеченной пирамиды
        neighbor_perp_dir = _build_perpendicular_line(neighbor_xy, neighbor_bisector, neighbor_belt_center)

        # Строим линию от точки пояса 1 перпендикулярно биссектрисе
        # Перпендикуляр направлен наружу от центра для правильной геометрии усеченной пирамиды
        belt1_perp_dir = _build_perpendicular_line(belt1_xy, belt1_bisector, belt1_center)

        # Явно проецируем направления на плоскость XY (гарантируем, что Z = 0)
        neighbor_perp_dir = _project_direction_to_xy(neighbor_perp_dir)
        belt1_perp_dir = _project_direction_to_xy(belt1_perp_dir)

        # Находим пересечение двух линий в плоскости XY
        # Линия 1: neighbor_xy + t * neighbor_perp_dir (параллельна XY, z = const)
        # Линия 2: belt1_xy + s * belt1_perp_dir (параллельна XY, z = const)
        intersection = _find_line_intersection_xy(
            neighbor_xy,
            neighbor_perp_dir,
            belt1_xy,
            belt1_perp_dir
        )

        if intersection is None:
            # Линии параллельны или почти параллельны, используем среднюю точку
            intersection = (neighbor_xy + belt1_xy) / 2.0
            intersections_failed += 1
            logger.debug(f"[parallel_lines] i={i}: линии параллельны, используется средняя точка")

        # X и Y координаты берем из точки пересечения в плоскости XY
        target_xy = intersection
        # Z координату берем от соответствующей точки пояса 1
        target_z = belt1_z

        if i < 5:
            logger.debug(
                f"[parallel_lines] i={i}: neighbor={neighbor_xy}, belt1={belt1_xy}, "
                f"neighbor_bisector={neighbor_bisector}, belt1_bisector={belt1_bisector}, "
                f"neighbor_perp_dir={neighbor_perp_dir}, belt1_perp_dir={belt1_perp_dir}, "
                f"intersection={target_xy}, z={target_z}"
            )

        row = {
            'x': float(target_xy[0]),
            'y': float(target_xy[1]),
            'z': target_z,
            'name': f"B{target_belt}_G{i+1}",
            'belt': target_belt,
            'is_generated': True
        }
        if 'is_station' in data.columns:
            row['is_station'] = False
        pts.append(row)
    candidates = pd.DataFrame(pts)
    if candidates.empty:
        logger.warning("[parallel_lines] Кандидаты пусты — ничего не добавлено")
        return data, pd.DataFrame()
    logger.info(f"[parallel_lines] Сформировано кандидатов: {len(candidates)}; случаев без пересечения (параллельные линии): {intersections_failed}")

    # Валидация проекций и результатов
    if len(candidates) > 0:
        # Проверяем, что все точки имеют корректные координаты
        invalid_points = []
        for idx, row in candidates.iterrows():
            if not (np.isfinite(row['x']) and np.isfinite(row['y']) and np.isfinite(row['z'])):
                invalid_points.append(idx)

        if invalid_points:
            logger.warning(f"[parallel_lines] Найдено {len(invalid_points)} точек с некорректными координатами")
            candidates = candidates.drop(invalid_points)

        # Проверяем, что пересечения находятся в разумных пределах
        if not candidates.empty:
            # Вычисляем среднее расстояние от центра пояса 1
            belt1_center = belt1_sorted[['x', 'y']].mean().values
            candidate_xy = candidates[['x', 'y']].values
            distances = np.linalg.norm(candidate_xy - belt1_center, axis=1)
            mean_distance = np.mean(distances)
            max_distance = np.max(distances)
            min_distance = np.min(distances)

            logger.info(
                f"[parallel_lines] Расстояния от центра пояса 1: "
                f"мин={min_distance:.3f} м, макс={max_distance:.3f} м, среднее={mean_distance:.3f} м"
            )

            # Проверяем, что новый пояс дальше от центра, чем пояс 1 (для усеченной пирамиды)
            belt1_distances = np.linalg.norm(belt1_sorted[['x', 'y']].values - belt1_center, axis=1)
            belt1_mean_distance = np.mean(belt1_distances)

            if mean_distance < belt1_mean_distance * 0.9:
                logger.warning(
                    f"[parallel_lines] Новый пояс находится ближе к центру, чем пояс 1 "
                    f"({mean_distance:.3f} м < {belt1_mean_distance:.3f} м). "
                    f"Возможно, неправильное направление перпендикуляров."
                )

    # Проверка правильности многоугольника
    if len(candidates) > 0:
        validation_result = _validate_belt_polygon(candidates, faces, target_belt)
        if not validation_result['valid']:
            logger.warning(f"[parallel_lines] Пояс {target_belt} не является правильным многоугольником: {', '.join(validation_result['warnings'])}")

    # Удаление дублей и слияние
    clean = _drop_duplicates_vs_existing(data, candidates, tolerance)
    logger.info(f"[parallel_lines] После удаления дублей: добавляется {len(clean)} точек")

    if clean.empty:
        logger.warning("[parallel_lines] После удаления дублей не осталось точек для добавления")
        return data, pd.DataFrame()

    merged = pd.concat([data, clean], ignore_index=True)

    # Проверка и оптимизация геометрии достроенного пояса
    b_mask = (merged['belt'] == target_belt)
    if b_mask.any():
        b_target = merged[b_mask].copy()
        xs, ys, zs = b_target['x'].values, b_target['y'].values, b_target['z'].values
        logger.info(f"[parallel_lines] Пояс {target_belt}: N={len(b_target)}, X[{xs.min():.3f},{xs.max():.3f}], Y[{ys.min():.3f},{ys.max():.3f}], Z≈{np.median(zs):.3f}")

        # Проверяем соответствие высот поясу 1 (если пояс 1 доступен)
        belt1_check = merged[merged['belt'] == 1]
        if not belt1_check.empty:
            belt1_zs = belt1_check['z'].values
            height_diff = np.abs(zs - np.median(belt1_zs))
            max_height_diff = np.max(height_diff)
            logger.info(f"[parallel_lines] Проверка высот: максимальное отклонение от пояса 1 = {max_height_diff:.3f} м")
            if max_height_diff > 0.5:
                logger.warning(f"[parallel_lines] Высоты точек пояса {target_belt} значительно отличаются от пояса 1 (макс. отклонение: {max_height_diff:.3f} м)")

        # Проверяем углы до оптимизации
        angle_check_before = _check_belt_angles(b_target, faces, angle_tolerance_deg=5.0)
        logger.info(f"[parallel_lines] Проверка углов пояса {target_belt} (до оптимизации): {angle_check_before['message']}")

        # Оптимизируем геометрию, если углы отклоняются
        if not angle_check_before['valid'] or angle_check_before['max_deviation'] > 2.0:
            logger.info(f"[parallel_lines] Оптимизация геометрии пояса {target_belt} для улучшения углов")
            b_target_optimized = _optimize_belt_geometry(b_target, faces, max_iterations=10)

            # Обновляем точки в merged
            # После pd.concat с ignore_index=True индексы сбрасываются, поэтому ищем точки по имени или координатам
            # Создаем словарь соответствия: исходная точка -> оптимизированная точка
            # Используем позиционные индексы вместо исходных индексов
            optimized_dict = {}
            for pos_idx, (orig_idx, row_orig) in enumerate(b_target.iterrows()):
                # Используем позиционный индекс для доступа к оптимизированным данным
                # b_target_optimized должен иметь те же индексы, что и b_target (благодаря preserve_index=True)
                if orig_idx in b_target_optimized.index:
                    optimized_row = b_target_optimized.loc[orig_idx]
                    optimized_dict[pos_idx] = {
                        'x': float(optimized_row['x']),
                        'y': float(optimized_row['y']),
                        'original': row_orig,
                        'original_idx': orig_idx
                    }
                else:
                    # Если индекс не найден, используем исходные координаты
                    optimized_dict[pos_idx] = {
                        'x': float(row_orig['x']),
                        'y': float(row_orig['y']),
                        'original': row_orig,
                        'original_idx': orig_idx
                    }

            # Обновляем точки в merged по позиционным индексам
            b_target_indices = b_target.index.values
            for pos_idx, opt_data in optimized_dict.items():
                if pos_idx >= len(b_target_indices):
                    continue

                merged_idx = b_target_indices[pos_idx]
                row_orig = opt_data['original']

                # Проверяем, что индекс существует в merged
                if merged_idx in merged.index:
                    merged.loc[merged_idx, 'x'] = opt_data['x']
                    merged.loc[merged_idx, 'y'] = opt_data['y']
                else:
                    # Если индекс не найден, ищем по имени или координатам
                    found = False
                    if 'name' in merged.columns and pd.notna(row_orig.get('name')):
                        name_match = merged['name'] == row_orig['name']
                        belt_match = merged['belt'] == target_belt
                        matches = merged[name_match & belt_match]
                        if len(matches) > 0:
                            found_idx = matches.index[0]
                            merged.loc[found_idx, 'x'] = opt_data['x']
                            merged.loc[found_idx, 'y'] = opt_data['y']
                            found = True

                    # Если не нашли по имени, ищем по координатам
                    if not found:
                        belt_mask = merged['belt'] == target_belt
                        if belt_mask.any():
                            merged_belt = merged[belt_mask]
                            orig_xy = np.array([row_orig['x'], row_orig['y']])
                            merged_xy = merged_belt[['x', 'y']].values
                            distances = np.linalg.norm(merged_xy - orig_xy, axis=1)
                            closest_idx_in_merged_belt = np.argmin(distances)

                            if distances[closest_idx_in_merged_belt] < 0.01:  # 1 см
                                found_idx = merged_belt.index[closest_idx_in_merged_belt]
                                merged.loc[found_idx, 'x'] = opt_data['x']
                                merged.loc[found_idx, 'y'] = opt_data['y']

            # Обновляем b_target для дальнейших проверок
            b_target = merged[b_mask].copy()

            # Проверяем углы после оптимизации
            angle_check_after = _check_belt_angles(b_target, faces, angle_tolerance_deg=5.0)
            logger.info(f"[parallel_lines] Проверка углов пояса {target_belt} (после оптимизации): {angle_check_after['message']}")

            if angle_check_after['valid']:
                logger.info(f"[parallel_lines] Оптимизация улучшила углы: отклонение уменьшилось с {angle_check_before['max_deviation']:.2f}° до {angle_check_after['max_deviation']:.2f}°")
            else:
                logger.warning(f"[parallel_lines] Оптимизация не смогла полностью исправить углы: отклонение {angle_check_after['max_deviation']:.2f}°")
        else:
            logger.info(f"[parallel_lines] Углы пояса {target_belt} уже правильные, оптимизация не требуется")

        # Проверяем расстояния
        distance_check = _check_belt_distances(b_target, distance_tolerance=0.2)
        logger.info(f"[parallel_lines] Проверка расстояний пояса {target_belt}: {distance_check['message']}")
        if not distance_check['valid']:
            logger.warning(f"[parallel_lines] Расстояния между точками пояса {target_belt} неравномерны (коэффициент вариации > 0.2)")

        # Полная диагностика качества
        quality_diagnosis = _diagnose_belt_quality(b_target, faces, angle_tolerance_deg=5.0, distance_tolerance=0.2)
        logger.info(f"[parallel_lines] Диагностика качества пояса {target_belt}: {quality_diagnosis['message']}")

        if quality_diagnosis['quality'] in ['satisfactory', 'poor']:
            logger.warning(f"[parallel_lines] Качество пояса {target_belt} требует внимания: {quality_diagnosis['quality']}")
            for rec in quality_diagnosis['recommendations']:
                logger.info(f"[parallel_lines] Рекомендация: {rec}")

    return merged, clean

