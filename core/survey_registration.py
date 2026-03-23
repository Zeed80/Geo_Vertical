"""
Модуль для объединения съемок с разных точек стояния
Реализует преобразование Гельмерта и регистрацию по поясам
"""

import logging

import numpy as np
import pandas as pd
from scipy.optimize import least_squares

from core.planar_orientation import domain_signed_angle_rad

logger = logging.getLogger(__name__)


def rotation_matrix_euler(omega: float, phi: float, kappa: float) -> np.ndarray:
    """
    Создает матрицу поворота из углов Эйлера (ω, φ, κ)

    Используется последовательность поворотов: Rx(ω) → Ry(φ) → Rz(κ)

    Args:
        omega: угол поворота вокруг оси X (радианы)
        phi: угол поворота вокруг оси Y (радианы)
        kappa: угол поворота вокруг оси Z (радианы)

    Returns:
        Матрица поворота 3×3
    """
    # Матрицы поворота вокруг каждой оси
    Rx = np.array([
        [1, 0, 0],
        [0, np.cos(omega), -np.sin(omega)],
        [0, np.sin(omega), np.cos(omega)]
    ])

    Ry = np.array([
        [np.cos(phi), 0, np.sin(phi)],
        [0, 1, 0],
        [-np.sin(phi), 0, np.cos(phi)]
    ])

    Rz = np.array([
        [np.cos(kappa), -np.sin(kappa), 0],
        [np.sin(kappa), np.cos(kappa), 0],
        [0, 0, 1]
    ])

    # Композиция поворотов: R = Rz * Ry * Rx
    R = Rz @ Ry @ Rx

    return R


def helmert_transform_points(points: np.ndarray, params: np.ndarray) -> np.ndarray:
    """
    Применяет преобразование Гельмерта к точкам

    Args:
        points: массив точек (N×3), каждая строка [x, y, z]
        params: параметры преобразования [Tx, Ty, Tz, omega, phi, kappa, s]

    Returns:
        Преобразованные точки (N×3)
    """
    # Детальное логирование для отладки
    logger.info("=== НАЧАЛО ПРЕОБРАЗОВАНИЯ ГЕЛЬМЕРТА ===")
    logger.info("Входные параметры:")
    logger.info(f"  points: {points.shape}")
    logger.info(f"  params: {params}")
    logger.info(f"  Тип params: {type(params)}")

    # Проверяем, что params - это массив numpy
    if not isinstance(params, np.ndarray):
        if isinstance(params, dict) and 'params' in params:
            # Если передан словарь с ключом 'params', извлекаем массив
            params_array = params['params']
            logger.info(f"Извлечен массив из словаря: {params_array}")
            logger.info(f"Тип массива: {type(params_array)}")
            return helmert_transform_points(points, params_array)
        else:
            error_msg = f"params должен быть массивом numpy, получен {type(params)}"
            logger.error(error_msg)
            raise ValueError(error_msg)

    # Проверяем размерность массива параметров
    if len(params) < 7:
        error_msg = f"Массив параметров должен содержать 7 элементов, получено {len(params)}: {params}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    Tx, Ty, Tz = params[0], params[1], params[2]
    omega, phi, kappa = params[3], params[4], params[5]
    scale = params[6]

    logger.info("Распарсенные параметры:")
    logger.info(f"  Tx={Tx:.6f}, Ty={Ty:.6f}, Tz={Tz:.6f}")
    logger.info(f"  ω={np.degrees(omega):.6f}°, φ={np.degrees(phi):.6f}°, κ={np.degrees(kappa):.6f}°")
    logger.info(f"  s={scale:.6f}")

    # Вектор переноса
    T = np.array([Tx, Ty, Tz])

    # Матрица поворота
    R = rotation_matrix_euler(omega, phi, kappa)

    # Преобразование: X' = s * R * X + T
    transformed = (scale * (R @ points.T)).T + T

    logger.info("Преобразование применено успешно")
    logger.info(f"Результат: {transformed.shape}")

    return transformed


def compute_helmert_parameters(points_source: np.ndarray, points_target: np.ndarray) -> dict:
    """
    Вычисляет параметры преобразования Гельмерта из пар точек методом наименьших квадратов

    Args:
        points_source: исходные точки (N×3)
        points_target: целевые точки (N×3), соответствующие исходным

    Returns:
        Словарь с параметрами преобразования и метриками качества:
        - params: [Tx, Ty, Tz, omega, phi, kappa, s]
        - rmse: среднеквадратичная ошибка
        - residuals: остаточные невязки для каждой точки
        - residuals_3d: остаточные невязки по каждой координате
    """
    if len(points_source) != len(points_target):
        raise ValueError("Количество исходных и целевых точек должно совпадать")

    if len(points_source) < 3:
        raise ValueError("Для вычисления преобразования Гельмерта нужно минимум 3 точки")

    # Центрируем точки для улучшения численной стабильности
    center_source = points_source.mean(axis=0)
    center_target = points_target.mean(axis=0)

    points_source_centered = points_source - center_source
    points_target_centered = points_target - center_target

    # Вычисляем начальное приближение масштаба
    scale_src = np.sqrt(np.sum(points_source_centered ** 2))
    scale_tgt = np.sqrt(np.sum(points_target_centered ** 2))
    if scale_src > 1e-6:
        initial_scale = scale_tgt / scale_src
    else:
        initial_scale = 1.0

    # Начальное приближение параметров
    # Перенос: разность центров
    initial_T = center_target - initial_scale * center_source

    # Начальные углы (близкие к нулю для итерационного уточнения)
    initial_params = np.array([
        initial_T[0],     # Tx
        initial_T[1],     # Ty
        initial_T[2],     # Tz
        0.0,              # omega (начальное приближение)
        0.0,              # phi (начальное приближение)
        0.0,              # kappa (начальное приближение)
        initial_scale     # s (начальное приближение)
    ])

    # Функция ошибки для минимизации
    def error_function(params):
        transformed = helmert_transform_points(points_source, params)
        residuals = transformed - points_target
        return residuals.flatten()

    # Решение методом наименьших квадратов с использованием Levenberg-Marquardt
    result = least_squares(
        error_function,
        initial_params,
        method='lm',  # Levenberg-Marquardt для нелинейной задачи
        max_nfev=1000,
        ftol=1e-9,
        xtol=1e-9,
        gtol=1e-9
    )

    if not result.success:
        logger.warning(f"Оптимизация преобразования Гельмерта не сошлась: {result.message}")

    final_params = result.x

    # Вычисляем итоговые метрики качества
    transformed_final = helmert_transform_points(points_source, final_params)
    residuals_3d = transformed_final - points_target
    residuals = np.linalg.norm(residuals_3d, axis=1)
    rmse = np.sqrt(np.mean(residuals ** 2))

    logger.info(f"Преобразование Гельмерта: RMSE={rmse:.6f} м, масштаб={final_params[6]:.6f}")

    return {
        'params': final_params,
        'rmse': rmse,
        'residuals': residuals,
        'residuals_3d': residuals_3d,
        'success': result.success,
        'message': result.message
    }


def apply_helmert_transform(points: pd.DataFrame, transform_params: dict, rotation_center: np.ndarray | None = None) -> pd.DataFrame:
    """
    Применяет преобразование Гельмерта к DataFrame с точками

    Args:
        points: DataFrame с колонками x, y, z
        transform_params: словарь с параметрами преобразования (из compute_helmert_parameters)
        rotation_center: опционально, центр поворота (если указан, поворот будет вокруг этого центра, а не начала координат)

    Returns:
        DataFrame с преобразованными координатами
    """
    # Детальное логирование для отладки
    logger.info("=== НАЧАЛО ПРИМЕНЕНИЯ ПРЕОБРАЗОВАНИЯ ГЕЛЬМЕРТА ===")
    logger.info("Входные параметры:")
    logger.info(f"  points: {len(points)} точек")
    logger.info(f"  transform_params: {transform_params}")
    logger.info(f"  rotation_center: {rotation_center}")

    if 'params' not in transform_params:
        error_msg = "transform_params должен содержать ключ 'params'"
        logger.error(error_msg)
        raise ValueError(error_msg)

    params = transform_params['params']
    logger.info(f"Параметры преобразования: Tx={params[0]:.6f}, Ty={params[1]:.6f}, Tz={params[2]:.6f}, "
               f"ω={np.degrees(params[3]):.6f}°, φ={np.degrees(params[4]):.6f}°, κ={np.degrees(params[5]):.6f}°, s={params[6]:.6f}")

    # Извлекаем координаты
    xyz = points[['x', 'y', 'z']].values
    logger.info(f"Форма массива координат: {xyz.shape}")

    # Если указан центр поворота, применяем поворот вокруг центра
    if rotation_center is not None:
        logger.info(f"Применение поворота вокруг центра: ({rotation_center[0]:.3f}, {rotation_center[1]:.3f}, {rotation_center[2]:.3f})")
        # ВАЖНО: params[0:3] (T) содержит T_corrected (без компенсации центра),
        # так как поворот вокруг центра применяется явно в этой функции

        Tx, Ty, Tz = params[0], params[1], params[2]
        omega, phi, kappa = params[3], params[4], params[5]
        scale = params[6]

        # Матрица поворота
        R = rotation_matrix_euler(omega, phi, kappa)

        # Вектор переноса (это T_corrected)
        T = np.array([Tx, Ty, Tz])

        # Правильная формула поворота вокруг центра:
        # P' = center + s * R * (P - center) + T_corrected
        xyz_relative = xyz - rotation_center  # Относительные координаты
        xyz_rotated_relative = (scale * (R @ xyz_relative.T)).T  # Поворот и масштаб относительно центра
        xyz_transformed = xyz_rotated_relative + rotation_center + T  # Перенос обратно и применение T_corrected
    else:
        # Стандартное преобразование вокруг начала координат
        xyz_transformed = helmert_transform_points(xyz, params)

    logger.info("Преобразование применено успешно")

    # Создаем результат
    result = points.copy()
    result['x'] = xyz_transformed[:, 0]
    result['y'] = xyz_transformed[:, 1]
    result['z'] = xyz_transformed[:, 2]

    logger.info(f"Результат создан: {len(result)} точек")

    return result


def register_belt_survey(
    belt1_points: pd.DataFrame,
    belt2_points: pd.DataFrame,
    matched_point_pair: tuple[int, int],
    tower_faces: int = 4,
    rotation_angle_deg: float | None = None,
    rotation_direction: int = 1,
    all_points_second_survey: pd.DataFrame | None = None
) -> dict:
    """
    Регистрирует съемку пояса с двух точек стояния
    Поворачивает ВСЮ вторую съемку вокруг общего центра на указанный угол

    Args:
        belt1_points: точки пояса из первой съемки
        belt2_points: точки пояса из второй съемки
        matched_point_pair: пара индексов (idx1, idx2) совпадающей точки
                           idx1 - индекс в belt1_points (после reset_index)
                           idx2 - индекс в belt2_points (после reset_index)
        tower_faces: количество граней башни (для расчета угла поворота, если не указан явно)
        rotation_angle_deg: угол поворота в градусах (если None, то 360°/tower_faces)
        rotation_direction: направление поворота (1 = по часовой, -1 = против часовой)
        all_points_second_survey: все точки второй съемки (для вычисления общего центра)

    Returns:
        Словарь с параметрами преобразования и метриками качества
    """
    # Детальное логирование для отладки
    logger.info("=== НАЧАЛО РЕГИСТРАЦИИ ПОЯСА ===")
    logger.info("Входные параметры:")
    logger.info(f"  belt1_points: {len(belt1_points)} точек")
    logger.info(f"  belt2_points: {len(belt2_points)} точек")
    logger.info(f"  matched_point_pair: {matched_point_pair}")
    logger.info(f"  tower_faces: {tower_faces}")
    logger.info(f"  rotation_angle_deg: {rotation_angle_deg}")
    logger.info(f"  rotation_direction: {rotation_direction}")
    logger.info(f"  all_points_second_survey: {len(all_points_second_survey) if all_points_second_survey is not None else None} точек")

    if len(belt1_points) == 0 or len(belt2_points) == 0:
        error_msg = f"Оба набора точек пояса должны быть непустыми. belt1={len(belt1_points)}, belt2={len(belt2_points)}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    idx1, idx2 = matched_point_pair
    logger.info(f"Индексы совпадающей точки: idx1={idx1}, idx2={idx2}")

    if idx1 >= len(belt1_points) or idx2 >= len(belt2_points):
        error_msg = f"Индексы совпадающей точки выходят за границы. idx1={idx1} (max={len(belt1_points)-1}), idx2={idx2} (max={len(belt2_points)-1})"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Получаем совпадающие точки (для определения соответствия)
    point1 = belt1_points.iloc[idx1]
    point2 = belt2_points.iloc[idx2]

    p1 = np.array([point1['x'], point1['y'], point1['z']])
    p2 = np.array([point2['x'], point2['y'], point2['z']])

    # Вычисляем базовый угол поворота
    # Если угол указан явно, используем его, иначе вычисляем автоматически
    if rotation_angle_deg is not None:
        base_angle_deg = abs(rotation_angle_deg)
        logger.info(f"Использован указанный угол поворота: {base_angle_deg:.1f}°")
    else:
        # Проверяем, что количество граней корректное
        if tower_faces <= 0:
            raise ValueError(f"Некорректное количество граней башни: {tower_faces}. Должно быть положительным числом.")

        # Для 4-гранной башни угол должен быть ровно 90° в плане (плоскость XY)
        base_angle_deg = 360.0 / tower_faces
        logger.info(f"Угол поворота пояса рассчитан автоматически: {base_angle_deg:.1f}° ({tower_faces} граней)")

    base_angle_rad = np.radians(base_angle_deg)

    # Получаем все координаты точек поясов
    xyz1 = belt1_points[['x', 'y', 'z']].values
    xyz2 = belt2_points[['x', 'y', 'z']].values

    # ВАЖНО: Центры поясов в плоскости XY (для поворота вокруг центра пояса)
    # Центры должны быть на одной высоте (средняя высота пояса)
    center1_xy = xyz1[:, :2].mean(axis=0)  # Центр в плоскости XY
    center2_xy = xyz2[:, :2].mean(axis=0)
    avg_height1 = xyz1[:, 2].mean()
    avg_height2 = xyz2[:, 2].mean()
    center1 = np.array([center1_xy[0], center1_xy[1], avg_height1])
    center2 = np.array([center2_xy[0], center2_xy[1], avg_height2])

    # ВАЖНО: Для правильного поворота точек целевого пояса нужно использовать центр самого пояса.
    # Это обеспечит точное совпадение точек пояса после трансформации.
    # Для остальных поясов трансформация также будет корректной, так как поворот выполняется
    # вокруг фиксированного центра, а сдвиг вычисляется для совмещения базовой точки.
    center2_for_transform = center2
    logger.info(f"Центр целевого пояса 2 для трансформации (XY): ({center2_xy[0]:.3f}, {center2_xy[1]:.3f}), H={avg_height2:.3f}")

    # Логируем центр всей второй съемки для информации (но не используем для трансформации)
    if all_points_second_survey is not None and len(all_points_second_survey) > 0:
        all_xyz2 = all_points_second_survey[['x', 'y', 'z']].values
        center_all_xy = all_xyz2[:, :2].mean(axis=0)
        avg_height_all = all_xyz2[:, 2].mean()
        logger.info(f"Центр ВСЕХ точек второй съемки (XY): ({center_all_xy[0]:.3f}, {center_all_xy[1]:.3f}), H={avg_height_all:.3f} (для справки)")
        logger.info("Используется центр ЦЕЛЕВОГО ПОЯСА для трансформации (не всей съемки)")

    logger.info(f"Центр первого пояса (XY): ({center1_xy[0]:.3f}, {center1_xy[1]:.3f}), H={avg_height1:.3f}")
    logger.info(f"Центр второго пояса (XY): ({center2_xy[0]:.3f}, {center2_xy[1]:.3f}), H={avg_height2:.3f}")

    # Пробуем оба направления поворота и выбираем оптимальное
    # Если направление указано явно, используем только его
    best_rmse = float('inf')
    best_params = None
    best_direction = None

    # Список направлений для проверки
    directions_to_try = [rotation_direction] if rotation_direction != 0 else [1, -1]

    for direction in directions_to_try:  # 1 = по часовой, -1 = против часовой
        angle = direction * base_angle_rad

        # ВАЖНО: Для метода 2 используем заданный угол, а не вычисленный динамически
        # Матрица поворота вокруг вертикальной оси Z (в плоскости XY)
        cos_a = np.cos(angle)
        sin_a = np.sin(angle)
        R_z = np.array([
            [cos_a, -sin_a, 0],
            [sin_a, cos_a, 0],
            [0, 0, 1]
        ])

        # ВАЖНО: Поворот должен выполняться вокруг центра ВСЕЙ второй съемки, а не начала координат
        # Формула поворота вокруг центра: P' = center + R @ (P - center) = R @ P + center - R @ center
        # Затем добавляем сдвиг для совмещения базовой точки p2 с p1

        # 1. Поворачиваем базовую точку вокруг центра: p2_rotated = center2_for_transform + R_z @ (p2 - center2_for_transform)
        p2_relative = p2 - center2_for_transform  # Относительные координаты
        p2_rotated = center2_for_transform + R_z @ p2_relative  # Поворот вокруг центра

        # 2. Вычисляем сдвиг для совмещения повернутой базовой точки с целевой
        # T_corrected = p1 - p2_rotated
        T_corrected = p1 - p2_rotated

        # 3. Для преобразования Гельмерта нужно учесть, что поворот вокруг центра
        # Преобразование: P' = R_z @ (P - center2_for_transform) + center2_for_transform + T_corrected
        # Раскрываем: P' = R_z @ P - R_z @ center2_for_transform + center2_for_transform + T_corrected
        #            P' = R_z @ P + (center2_for_transform - R_z @ center2_for_transform + T_corrected)

        # Итоговый вектор переноса для формулы Гельмерта:
        # ВАЖНО: helmert_transform_points использует полную матрицу R = Rz * Ry * Rx,
        # но нам нужен только поворот вокруг Z. Поэтому мы вычисляем T_helmert так,
        # чтобы компенсировать поворот вокруг начала координат в helmert_transform_points
        # и получить эффект поворота вокруг center2_for_transform

        # Для поворота вокруг центра: P' = center + Rz @ (P - center) + T_corrected
        # Раскрываем: P' = center + Rz @ P - Rz @ center + T_corrected
        #            P' = Rz @ P + (center - Rz @ center + T_corrected)

        # Но helmert_transform_points применяет: P' = R @ P + T, где R = Rz @ Ry @ Rx
        # Для omega=0, phi=0, kappa=angle: R = Rz, так что это правильно

        T_helmert_for_standard = center2_for_transform - R_z @ center2_for_transform + T_corrected

        # ВАЖНО: Проверяем формулу поворота вокруг центра вручную для базовой точки
        p2_test = helmert_transform_points(p2.reshape(1, -1), {'params': np.array([T_helmert_for_standard[0], T_helmert_for_standard[1], T_helmert_for_standard[2], 0.0, 0.0, angle, 1.0])})[0]
        p2_test_expected = center2_for_transform + R_z @ (p2 - center2_for_transform) + T_corrected
        test_error = np.linalg.norm(p2_test - p1)
        test_error_expected = np.linalg.norm(p2_test_expected - p1)
        logger.info(f"Проверка формулы: p2_test ошибка={test_error:.6f}м, p2_test_expected ошибка={test_error_expected:.6f}м")

        # Применяем преобразование к точкам пояса для оценки качества
        # Используем T_helmert_for_standard для helmert_transform_points
        xyz2_helmert = helmert_transform_points(xyz2, {'params': np.array([T_helmert_for_standard[0], T_helmert_for_standard[1], T_helmert_for_standard[2], 0.0, 0.0, angle, 1.0])})

        # Проверяем трансформацию базовой точки
        p2_transformed_check = helmert_transform_points(p2.reshape(1, -1), {'params': np.array([T_helmert_for_standard[0], T_helmert_for_standard[1], T_helmert_for_standard[2], 0.0, 0.0, angle, 1.0])})[0]
        base_error = np.linalg.norm(p2_transformed_check - p1)
        logger.info(f"Проверка базовой точки после трансформации: ошибка={base_error:.6f}м")

        # Сравниваем с точками первого пояса - находим ближайшие соответствия
        total_distance = 0.0
        matched_pairs = 0

        for pt2 in xyz2_helmert:
            min_dist = float('inf')
            for pt1 in xyz1:
                dist = np.linalg.norm(pt1 - pt2)
                if dist < min_dist:
                    min_dist = dist
            total_distance += min_dist
            matched_pairs += 1

        # Также проверяем расстояние между центрами
        center2_helmert = xyz2_helmert.mean(axis=0)
        center_distance = np.linalg.norm(center1 - center2_helmert)

        # Среднее расстояние до ближайших точек
        mean_distance = total_distance / matched_pairs if matched_pairs > 0 else center_distance

        # Комбинированная метрика - приоритет точности совмещения
        rmse = mean_distance + 0.2 * center_distance

        if rmse < best_rmse:
            best_rmse = rmse
            best_direction = direction

            # Сохраняем параметры для применения к полной съемке
            # Параметры: [Tx, Ty, Tz, omega, phi, kappa, s]
            # ВАЖНО: Для apply_helmert_transform с rotation_center нужно использовать T_corrected,
            # а не T_helmert_for_standard, так как там поворот вокруг центра применяется явно
            best_params = np.array([
                T_corrected[0],     # Tx (используем T_corrected для apply_helmert_transform с rotation_center)
                T_corrected[1],     # Ty
                T_corrected[2],     # Tz
                0.0,                # omega (поворот вокруг X не нужен)
                0.0,                # phi (поворот вокруг Y не нужен)
                angle,              # kappa (поворот вокруг Z) - ИСПОЛЬЗУЕМ ЗАДАННЫЙ УГОЛ
                1.0                 # s (масштаб без изменений)
            ])
            best_rotation_center = center2_for_transform  # Сохраняем центр поворота

            # Логируем процесс поворота
            logger.info(f"Поворот в плоскости XY на заданный угол {np.degrees(angle):.2f}° (метод 2) вокруг центра: "
                       f"p1=({p1[0]:.3f}, {p1[1]:.3f}, {p1[2]:.3f}), "
                       f"p2=({p2[0]:.3f}, {p2[1]:.3f}, {p2[2]:.3f}), "
                       f"center=({center2_for_transform[0]:.3f}, {center2_for_transform[1]:.3f}, {center2_for_transform[2]:.3f}), "
                       f"T_corrected=({T_corrected[0]:.3f}, {T_corrected[1]:.3f}, {T_corrected[2]:.3f})")

    # Вычисляем фактический угол поворота с учетом направления
    actual_angle_rad = best_direction * base_angle_rad
    actual_angle_deg = np.degrees(actual_angle_rad)

    logger.info(f"Регистрация по поясу: угол={actual_angle_deg:.1f}° ({base_angle_deg:.1f}° * {best_direction}), "
                f"направление={'по часовой' if best_direction > 0 else 'против часовой'}, "
                f"RMSE={best_rmse:.6f} м")

    # Проверяем корректность преобразования базовой точки с использованием apply_helmert_transform
    # Создаем временный DataFrame для проверки
    p2_df = pd.DataFrame({'x': [p2[0]], 'y': [p2[1]], 'z': [p2[2]]})
    test_params = {'params': best_params}
    p2_transformed_df = apply_helmert_transform(p2_df, test_params, rotation_center=best_rotation_center)
    p2_transformed = np.array([p2_transformed_df.iloc[0]['x'], p2_transformed_df.iloc[0]['y'], p2_transformed_df.iloc[0]['z']])
    error_at_base = np.linalg.norm(p2_transformed - p1)
    logger.info(f"Ошибка совмещения базовой точки после преобразования (с rotation_center): {error_at_base:.6f} м")
    if error_at_base > 1e-6:
        logger.warning(f"Базовая точка не совпала точно! Ожидалось попадание в p1, получили расстояние {error_at_base:.6f} м")

    return {
        'params': best_params,
        'rmse': best_rmse,
        'angle_deg': actual_angle_deg,  # Фактический угол с учетом направления
        'direction': best_direction,
        'matched_point': (idx1, idx2),
        'visualization_data': None,  # Будем строить линии после объединения
        'rotation_center': best_rotation_center  # Центр поворота для правильного применения трансформации
    }


def compute_rotation_from_plane(
    belt1_points: pd.DataFrame,
    belt2_points: pd.DataFrame,
    matched_point_pair: tuple[int, int]
) -> tuple[np.ndarray, float]:
    """
    Вычисляет параметры поворота на основе плоскости, определенной по точкам пояса

    Логика:
    1. Соединяем точки на одном поясе между съемками
    2. Определяем плоскость по этим точкам
    3. Используем эту плоскость для поворота

    Args:
        belt1_points: точки пояса из первой съемки
        belt2_points: точки пояса из второй съемки
        matched_point_pair: пара индексов (idx1, idx2) совпадающей точки

    Returns:
        Кортеж (normal_vector, angle_deg):
        - normal_vector: вектор нормали плоскости
        - angle_deg: угол поворота в градусах
    """
    idx1, idx2 = matched_point_pair

    if idx1 >= len(belt1_points) or idx2 >= len(belt2_points):
        raise ValueError(f"Индексы выходят за границы: idx1={idx1}, belt1={len(belt1_points)}, idx2={idx2}, belt2={len(belt2_points)}")

    # Получаем совпадающие точки
    point1 = belt1_points.iloc[idx1]
    point2 = belt2_points.iloc[idx2]

    p1 = np.array([point1['x'], point1['y'], point1['z']])
    p2 = np.array([point2['x'], point2['y'], point2['z']])

    logger.info("Вычисление поворота по плоскости:")
    logger.info(f"  Точка из первой съемки: ({p1[0]:.3f}, {p1[1]:.3f}, {p1[2]:.3f})")
    logger.info(f"  Точка из второй съемки: ({p2[0]:.3f}, {p2[1]:.3f}, {p2[2]:.3f})")

    # Создаем объединенный набор точек пояса
    # Используем все точки с обоих съемок для более точного определения плоскости
    all_belt_points = []

    # Добавляем все точки с первого пояса
    for i, (_, point) in enumerate(belt1_points.iterrows()):
        all_belt_points.append([point['x'], point['y'], point['z']])

    # Добавляем все точки со второго пояса
    for i, (_, point) in enumerate(belt2_points.iterrows()):
        all_belt_points.append([point['x'], point['y'], point['z']])

    all_points = np.array(all_belt_points)
    logger.info(f"  Всего точек для определения плоскости: {len(all_points)}")

    # Определяем плоскость методом наименьших квадратов
    # Уравнение плоскости: ax + by + cz + d = 0
    # Нормаль к плоскости: (a, b, c)

    # Вычисляем центр масс точек
    center = all_points.mean(axis=0)
    logger.info(f"  Центр масс: ({center[0]:.3f}, {center[1]:.3f}, {center[2]:.3f})")

    # Центрируем точки
    centered_points = all_points - center

    # Вычисляем матрицу ковариации
    cov_matrix = np.cov(centered_points.T)

    # SVD для определения нормали к плоскости
    # Нормаль - это собственный вектор, соответствующий минимальному собственному значению
    _, _, vh = np.linalg.svd(cov_matrix)
    normal = vh[-1]  # Последняя строка V^T - это нормаль

    # Нормализуем нормаль
    normal = normal / np.linalg.norm(normal)

    logger.info(f"  Нормаль к плоскости: ({normal[0]:.6f}, {normal[1]:.6f}, {normal[2]:.6f})")

    # Вычисляем угол поворота на основе нормали
    # Проекция нормали на плоскость XY
    normal_xy = np.array([normal[0], normal[1], 0])
    normal_xy = normal_xy / np.linalg.norm(normal_xy)

    # Угол между проекцией нормали и осью Y
    # Это угол поворота от оси Y к нормали
    angle_rad = np.arctan2(normal_xy[0], normal_xy[1])

    # Преобразуем в градусы
    angle_deg = np.degrees(angle_rad)

    # Корректируем угол, чтобы он был в диапазоне [0, 360)
    if angle_deg < 0:
        angle_deg += 360

    logger.info(f"  Угол поворота: {angle_deg:.2f}°")

    return normal, angle_deg


def compute_rotation_from_belt_connections(
    belt1_points: pd.DataFrame,
    belt2_points: pd.DataFrame,
    matched_point_pair: tuple[int, int]
) -> tuple[float, np.ndarray, dict]:
    """
    Вычисляет параметры поворота на основе соединения точек с поясами

    Логика:
    1. Соединяем точку с первого импорта с точкой на том же уровне на другом поясе в первом импорте
    2. Соединяем точку соединения с точкой на другом поясе на том же уровне на втором импорте
    3. Через эти линии строим плоскости, которые определяют угол поворота
    4. Возвращаем угол поворота, матрицу поворота и информацию для визуализации линий

    Args:
        belt1_points: точки пояса из первой съемки
        belt2_points: точки пояса из второй съемки
        matched_point_pair: пара индексов (idx1, idx2) совпадающей точки

    Returns:
        Кортеж (angle_deg, rotation_matrix, visualization_data):
        - angle_deg: угол поворота в градусах
        - rotation_matrix: матрица поворота 3x3
        - visualization_data: словарь с данными для отрисовки линий
    """
    idx1, idx2 = matched_point_pair

    if idx1 >= len(belt1_points) or idx2 >= len(belt2_points):
        raise ValueError(f"Индексы выходят за границы: idx1={idx1}, belt1={len(belt1_points)}, idx2={idx2}, belt2={len(belt2_points)}")

    # Получаем совпадающие точки
    point1 = belt1_points.iloc[idx1]
    point2 = belt2_points.iloc[idx2]

    p1 = np.array([point1['x'], point1['y'], point1['z']])
    p2 = np.array([point2['x'], point2['y'], point2['z']])

    logger.info("Вычисление поворота на основе соединения с поясами:")
    logger.info(f"  Точка из первой съемки: ({p1[0]:.3f}, {p1[1]:.3f}, {p1[2]:.3f})")
    logger.info(f"  Точка из второй съемки: ({p2[0]:.3f}, {p2[1]:.3f}, {p2[2]:.3f})")

    # Находим точку на том же уровне, что и p1, но с другой съемки (belt2)
    min_height_diff = float('inf')
    closest_same_level_idx = None
    closest_same_level_point = None

    for i, (_, point) in enumerate(belt2_points.iterrows()):
        point_belt2 = np.array([point['x'], point['y'], point['z']])
        height_diff = abs(point_belt2[2] - p1[2])

        if height_diff < min_height_diff:
            min_height_diff = height_diff
            closest_same_level_idx = i
            closest_same_level_point = point_belt2

    if closest_same_level_point is None:
        logger.warning("Не найдено точки на том же уровне в belt2")
        return None, np.eye(3), {}

    logger.info(f"  Точка на том же уровне (belt2): ({closest_same_level_point[0]:.3f}, {closest_same_level_point[1]:.3f}, {closest_same_level_point[2]:.3f})")

    # Находим точку на том же уровне, что и p2, но с первой съемки (belt1)
    min_height_diff = float('inf')
    closest_same_level_belt1_idx = None
    closest_same_level_belt1_point = None

    for i, (_, point) in enumerate(belt1_points.iterrows()):
        point_belt1 = np.array([point['x'], point['y'], point['z']])
        height_diff = abs(point_belt1[2] - p2[2])

        if height_diff < min_height_diff:
            min_height_diff = height_diff
            closest_same_level_belt1_idx = i
            closest_same_level_belt1_point = point_belt1

    if closest_same_level_belt1_point is None:
        logger.warning("Не найдено точки на том же уровне в belt1")
        return None, np.eye(3), {}

    logger.info(f"  Точка на том же уровне (belt1): ({closest_same_level_belt1_point[0]:.3f}, {closest_same_level_belt1_point[1]:.3f}, {closest_same_level_belt1_point[2]:.3f})")

    # Создаем два вектора:
    # Вектор 1: от p1 к точке на том же уровне в belt2
    v1 = closest_same_level_point - p1

    # Вектор 2: от p2 к точке на том же уровне в belt1
    v2 = closest_same_level_belt1_point - p2

    logger.info(f"  Вектор 1 (p1 -> тот же уровень в belt2): ({v1[0]:.3f}, {v1[1]:.3f}, {v1[2]:.3f})")
    logger.info(f"  Вектор 2 (p2 -> тот же уровень в belt1): ({v2[0]:.3f}, {v2[1]:.3f}, {v2[2]:.3f})")

    # Вычисляем угол между проекциями векторов на плоскость XY
    v1_xy = np.array([v1[0], v1[1], 0])
    v2_xy = np.array([v2[0], v2[1], 0])

    # Нормализуем векторы
    v1_xy_norm = np.linalg.norm(v1_xy)
    v2_xy_norm = np.linalg.norm(v2_xy)

    if v1_xy_norm < 1e-6 or v2_xy_norm < 1e-6:
        logger.warning("Один из векторов имеет нулевую проекцию на плоскость XY")
        return None, np.eye(3), {}

    v1_xy_normalized = v1_xy / v1_xy_norm
    v2_xy_normalized = v2_xy / v2_xy_norm

    # Вычисляем угол между векторами
    dot_product = np.dot(v1_xy_normalized, v2_xy_normalized)
    det = v1_xy_normalized[0] * v2_xy_normalized[1] - v1_xy_normalized[1] * v2_xy_normalized[0]

    angle_rad = np.arctan2(det, dot_product)
    angle_deg = np.degrees(angle_rad)

    # Корректируем угол в диапазон [0, 360)
    if angle_deg < 0:
        angle_deg += 360

    logger.info(f"  Угол поворота: {angle_deg:.2f}°")

    # Создаем матрицу поворота вокруг оси Z
    angle_rad = np.radians(angle_deg)
    cos_a = np.cos(angle_rad)
    sin_a = np.sin(angle_rad)
    rotation_matrix = np.array([
        [cos_a, -sin_a, 0],
        [sin_a, cos_a, 0],
        [0, 0, 1]
    ])

    # Сохраняем данные для визуализации
    visualization_data = {
        'line1': {
            'start': p1,
            'end': closest_same_level_point,
            'label': 'Линия 1: p1 -> тот же уровень в belt2'
        },
        'line2': {
            'start': p2,
            'end': closest_same_level_belt1_point,
            'label': 'Линия 2: p2 -> тот же уровень в belt1'
        },
        'matched_points': {
            'p1': p1,
            'p2': p2
        },
        'angle_deg': angle_deg
    }

    return angle_deg, rotation_matrix, visualization_data


def visualize_belt_connections(
    belt1_points: pd.DataFrame,
    belt2_points: pd.DataFrame,
    visualization_data: dict
) -> None:
    """
    Визуализирует линии, используемые для определения поворота

    Args:
        belt1_points: точки пояса из первой съемки
        belt2_points: точки пояса из второй съемки
        visualization_data: данные для визуализации из compute_rotation_from_belt_connections
    """
    try:
        import os
        from datetime import datetime

        import matplotlib.pyplot as plt
        from mpl_toolkits.mplot3d import Axes3D

        # Создаем 3D график
        fig = plt.figure(figsize=(12, 10))
        ax = fig.add_subplot(111, projection='3d')

        # Отображаем все точки первого пояса
        xyz1 = belt1_points[['x', 'y', 'z']].values
        ax.scatter(xyz1[:, 0], xyz1[:, 1], xyz1[:, 2],
                  c='blue', marker='o', s=50, label='Первая съемка', alpha=0.7)

        # Отображаем все точки второго пояса
        xyz2 = belt2_points[['x', 'y', 'z']].values
        ax.scatter(xyz2[:, 0], xyz2[:, 1], xyz2[:, 2],
                  c='red', marker='^', s=50, label='Вторая съемка', alpha=0.7)

        # Отображаем совпадающие точки
        matched_points = visualization_data['matched_points']
        p1 = matched_points['p1']
        p2 = matched_points['p2']

        ax.scatter([p1[0]], [p1[1]], [p1[2]],
                  c='green', marker='s', s=100, label='Совпадающая точка 1')
        ax.scatter([p2[0]], [p2[1]], [p2[2]],
                  c='orange', marker='s', s=100, label='Совпадающая точка 2')

        # Рисуем линии соединения
        line1 = visualization_data['line1']
        line2 = visualization_data['line2']

        # Линия 1
        ax.plot([line1['start'][0], line1['end'][0]],
                [line1['start'][1], line1['end'][1]],
                [line1['start'][2], line1['end'][2]],
                'g-', linewidth=2, label=line1['label'])

        # Линия 2
        ax.plot([line2['start'][0], line2['end'][0]],
                [line2['start'][1], line2['end'][1]],
                [line2['start'][2], line2['end'][2]],
                'm-', linewidth=2, label=line2['label'])

        # Добавляем проекции на плоскость XY
        # Проекция линии 1
        ax.plot([line1['start'][0], line1['end'][0]],
                [line1['start'][1], line1['end'][1]],
                [0, 0],
                'g--', linewidth=1, alpha=0.5, label='Проекция линии 1 на XY')

        # Проекция линии 2
        ax.plot([line2['start'][0], line2['end'][0]],
                [line2['start'][1], line2['end'][1]],
                [0, 0],
                'm--', linewidth=1, alpha=0.5, label='Проекция линии 2 на XY')

        # Настройка графика
        ax.set_xlabel('X')
        ax.set_ylabel('Y')
        ax.set_zlabel('Z')
        ax.set_title(f'Поворот на основе соединения с поясами\nУгол поворота: {visualization_data["angle_deg"]:.2f}°')
        ax.legend()

        # Устанавливаем равные масштабы для лучшей визуализации
        max_range = max(
            np.max(xyz1[:, 0]) - np.min(xyz1[:, 0]),
            np.max(xyz1[:, 1]) - np.min(xyz1[:, 1]),
            np.max(xyz1[:, 2]) - np.min(xyz1[:, 2]),
            np.max(xyz2[:, 0]) - np.min(xyz2[:, 0]),
            np.max(xyz2[:, 1]) - np.min(xyz2[:, 1]),
            np.max(xyz2[:, 2]) - np.min(xyz2[:, 2])
        )

        mid_x = (np.max(xyz1[:, 0]) + np.min(xyz1[:, 0]) + np.max(xyz2[:, 0]) + np.min(xyz2[:, 0])) / 4
        mid_y = (np.max(xyz1[:, 1]) + np.min(xyz1[:, 1]) + np.max(xyz2[:, 1]) + np.min(xyz2[:, 1])) / 4
        mid_z = (np.max(xyz1[:, 2]) + np.min(xyz1[:, 2]) + np.max(xyz2[:, 2]) + np.min(xyz2[:, 2])) / 4

        ax.set_xlim(mid_x - max_range/2, mid_x + max_range/2)
        ax.set_ylim(mid_y - max_range/2, mid_y + max_range/2)
        ax.set_zlim(mid_z - max_range/2, mid_z + max_range/2)

        plt.tight_layout()

        # Создаем директорию для сохранения изображений, если она не существует
        output_dir = "belt_connection_visualizations"
        os.makedirs(output_dir, exist_ok=True)

        # Генерируем уникальное имя файла на основе времени
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{output_dir}/belt_connections_{timestamp}.png"

        # Сохраняем график в файл
        plt.savefig(filename, dpi=150, bbox_inches='tight')
        plt.close()  # Закрываем график, чтобы освободить память

        logger.info(f"Визуализация сохранена в файл: {filename}")

    except ImportError:
        logger.warning("Matplotlib не установлен, невозможно отобразить визуализацию")
    except Exception as e:
        logger.error(f"Ошибка при визуализации: {e!s}")


def compute_rotation_from_connected_points(
    belt1_points: pd.DataFrame,
    belt2_points: pd.DataFrame,
    matched_point_pair: tuple[int, int]
) -> tuple[float, np.ndarray]:
    """
    Вычисляет параметры поворота на основе соединения точек на одном уровне

    Логика:
    1. Соединяем точку с первого импорта с точкой на том же уровне со второго импорта
    2. Соединяем точку с первого импорта с точкой на другом уровне со второго импорта
    3. Через эти линии определяем плоскость поворота

    Args:
        belt1_points: точки пояса из первой съемки
        belt2_points: точки пояса из второй съемки
        matched_point_pair: пара индексов (idx1, idx2) совпадающей точки

    Returns:
        Кортеж (angle_deg, rotation_matrix):
        - angle_deg: угол поворота в градусах
        - rotation_matrix: матрица поворота 3x3
    """
    idx1, idx2 = matched_point_pair

    if idx1 >= len(belt1_points) or idx2 >= len(belt2_points):
        raise ValueError(f"Индексы выходят за границы: idx1={idx1}, belt1={len(belt1_points)}, idx2={idx2}, belt2={len(belt2_points)}")

    # Получаем совпадающие точки
    point1 = belt1_points.iloc[idx1]
    point2 = belt2_points.iloc[idx2]

    p1 = np.array([point1['x'], point1['y'], point1['z']])
    p2 = np.array([point2['x'], point2['y'], point2['z']])

    logger.info("Вычисление поворота на основе соединения точек:")
    logger.info(f"  Точка из первой съемки: ({p1[0]:.3f}, {p1[1]:.3f}, {p1[2]:.3f})")
    logger.info(f"  Точка из второй съемки: ({p2[0]:.3f}, {p2[1]:.3f}, {p2[2]:.3f})")

    # Находим точку на том же уровне, что и p1, но с другой съемки
    # Ищем точку с минимальной разницей по высоте
    min_height_diff = float('inf')
    closest_same_level_idx = None
    closest_same_level_point = None

    for i, (_, point) in enumerate(belt2_points.iterrows()):
        if i == idx2:  # Пропускаем саму точку p2
            continue

        point_belt2 = np.array([point['x'], point['y'], point['z']])
        height_diff = abs(point_belt2[2] - p1[2])

        if height_diff < min_height_diff:
            min_height_diff = height_diff
            closest_same_level_idx = i
            closest_same_level_point = point_belt2

    if closest_same_level_point is None:
        logger.warning("Не найдено точки на том же уровне, что и p1")
        return None, np.eye(3)

    logger.info(f"  Точка на том же уровне: ({closest_same_level_point[0]:.3f}, {closest_same_level_point[1]:.3f}, {closest_same_level_point[2]:.3f})")

    # Находим точку на другом уровне с первой съемки
    # Ищем точку с максимальной разницей по высоте
    max_height_diff = 0
    farthest_diff_level_idx = None
    farthest_diff_level_point = None

    for i, (_, point) in enumerate(belt1_points.iterrows()):
        if i == idx1:  # Пропускаем саму точку p1
            continue

        point_belt1 = np.array([point['x'], point['y'], point['z']])
        height_diff = abs(point_belt1[2] - p2[2])

        if height_diff > max_height_diff:
            max_height_diff = height_diff
            farthest_diff_level_idx = i
            farthest_diff_level_point = point_belt1

    if farthest_diff_level_point is None:
        logger.warning("Не найдено точки на другом уровне с первой съемки")
        return None, np.eye(3)

    logger.info(f"  Точка на другом уровне: ({farthest_diff_level_point[0]:.3f}, {farthest_diff_level_point[1]:.3f}, {farthest_diff_level_point[2]:.3f})")

    # Создаем два вектора:
    # Вектор 1: от p1 к точке на том же уровне
    v1 = closest_same_level_point - p1

    # Вектор 2: от p2 к точке на другом уровне
    v2 = farthest_diff_level_point - p2

    logger.info(f"  Вектор 1 (p1 -> тот же уровень): ({v1[0]:.3f}, {v1[1]:.3f}, {v1[2]:.3f})")
    logger.info(f"  Вектор 2 (p2 -> другой уровень): ({v2[0]:.3f}, {v2[1]:.3f}, {v2[2]:.3f})")

    # Вычисляем векторное произведение для определения направления поворота
    cross_product = np.cross(v1, v2)
    cross_norm = np.linalg.norm(cross_product)

    if cross_norm < 1e-6:
        logger.warning("Векторы коллинеарны, невозможно определить направление поворота")
        return None, np.eye(3)

    # Нормализуем векторное произведение
    cross_normalized = cross_product / cross_norm

    # Определяем направление поворота (по часовой или против)
    # Если векторное произведение направлено вверх, поворот по часовой стрелке
    rotation_direction = 1 if cross_normalized[2] > 0 else -1

    logger.info(f"  Векторное произведение: ({cross_product[0]:.6f}, {cross_product[1]:.6f}, {cross_product[2]:.6f})")
    logger.info(f"  Направление поворота: {'по часовой' if rotation_direction > 0 else 'против часовой'}")

    # Вычисляем угол между векторами в плоскости XY
    # Проекция векторов на плоскость XY
    v1_xy = np.array([v1[0], v1[1], 0])
    v2_xy = np.array([v2[0], v2[1], 0])

    # Вычисляем угол между векторами
    dot_product = np.dot(v1_xy, v2_xy)
    det = v1_xy[0] * v2_xy[1] - v1_xy[1] * v2_xy[0]

    angle_rad = np.arctan2(det, dot_product)
    angle_deg = np.degrees(angle_rad)

    # Корректируем угол в зависимости от направления поворота
    if rotation_direction < 0:
        angle_deg = -angle_deg

    # Корректируем угол в диапазон [0, 360)
    if angle_deg < 0:
        angle_deg += 360

    logger.info(f"  Угол поворота: {angle_deg:.2f}°")

    # Создаем матрицу поворота вокруг оси Z
    angle_rad = np.radians(angle_deg)
    cos_a = np.cos(angle_rad)
    sin_a = np.sin(angle_rad)
    rotation_matrix = np.array([
        [cos_a, -sin_a, 0],
        [sin_a, cos_a, 0],
        [0, 0, 1]
    ])

    return angle_deg, rotation_matrix


def visualize_plane_lines(
    belt1_points: pd.DataFrame,
    belt2_points: pd.DataFrame,
    matched_point_pair: tuple[int, int],
    normal_vector: np.ndarray,
    angle_deg: float
) -> None:
    """
    Визуализирует линии, используемые для определения плоскости поворота

    Args:
        belt1_points: точки пояса из первой съемки
        belt2_points: точки пояса из второй съемки
        matched_point_pair: пара индексов совпадающей точки
        normal_vector: вектор нормали к плоскости
        angle_deg: угол поворота в градусах
    """
    try:
        import matplotlib.pyplot as plt
        from mpl_toolkits.mplot3d import Axes3D

        idx1, idx2 = matched_point_pair
        point1 = belt1_points.iloc[idx1]
        point2 = belt2_points.iloc[idx2]

        p1 = np.array([point1['x'], point1['y'], point1['z']])
        p2 = np.array([point2['x'], point2['y'], point2['z']])

        # Создаем 3D график
        fig = plt.figure(figsize=(12, 10))
        ax = fig.add_subplot(111, projection='3d')

        # Отображаем все точки первого пояса
        xyz1 = belt1_points[['x', 'y', 'z']].values
        ax.scatter(xyz1[:, 0], xyz1[:, 1], xyz1[:, 2],
                  c='blue', marker='o', s=50, label='Первая съемка', alpha=0.7)

        # Отображаем все точки второго пояса
        xyz2 = belt2_points[['x', 'y', 'z']].values
        ax.scatter(xyz2[:, 0], xyz2[:, 1], xyz2[:, 2],
                  c='red', marker='^', s=50, label='Вторая съемка', alpha=0.7)

        # Выделяем совпадающие точки
        ax.scatter([p1[0]], [p1[1]], [p1[2]],
                  c='green', marker='s', s=100, label='Совпадающая точка 1')
        ax.scatter([p2[0]], [p2[1]], [p2[2]],
                  c='orange', marker='s', s=100, label='Совпадающая точка 2')

        # Создаем плоскость
        # Вычисляем центр и размеры для отображения
        all_points = np.vstack([xyz1, xyz2])
        center = all_points.mean(axis=0)
        max_range = np.max(np.abs(all_points - center)) * 1.2

        # Создаем сетку для плоскости
        xx, yy = np.meshgrid(
            np.linspace(center[0] - max_range, center[0] + max_range, 10),
            np.linspace(center[1] - max_range, center[1] + max_range, 10)
        )

        # Уравнение плоскости: ax + by + cz + d = 0
        # Нормаль: (a, b, c)
        a, b, c = normal_vector
        d = -np.dot(normal_vector, center)

        # Вычисляем z для сетки
        zz = (-a * xx - b * yy - d) / c if abs(c) > 1e-6 else 0

        # Отображаем плоскость
        ax.plot_surface(xx, yy, zz, alpha=0.2, color='yellow')

        # Отображаем вектор нормали
        ax.quiver(center[0], center[1], center[2],
                 normal_vector[0], normal_vector[1], normal_vector[2],
                 length=max_range*0.5, color='purple', arrow_length_ratio=0.1, linewidth=2)

        # Отображаем линию между совпадающими точками
        ax.plot([p1[0], p2[0]], [p1[1], p2[1]], [p1[2], p2[2]],
                'g--', linewidth=2, label='Линия совпадения')

        # Настройка графика
        ax.set_xlabel('X (м)')
        ax.set_ylabel('Y (м)')
        ax.set_zlabel('Z (м)')
        ax.set_title(f'Визуализация плоскости поворота\nУгол: {angle_deg:.2f}°')
        ax.legend()

        # Добавляем текстовую информацию
        info_text = f"Нормаль: ({normal_vector[0]:.3f}, {normal_vector[1]:.3f}, {normal_vector[2]:.3f})\n"
        info_text += f"Уравнение плоскости: {a:.3f}x + {b:.3f}y + {c:.3f}z + {d:.3f} = 0"
        ax.text2D(0.02, 0.98, info_text, transform=ax.transAxes,
                  fontsize=10, verticalalignment='top',
                  bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))

        plt.tight_layout()

        # Сохраняем график
        output_path = 'plane_visualization.png'
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        logger.info(f"Визуализация сохранена в файл: {output_path}")

        # Показываем график
        plt.show()

    except ImportError:
        logger.warning("matplotlib не установлен, пропускаем визуализацию")
    except Exception as e:
        logger.error(f"Ошибка при визуализации: {e}", exc_info=True)


def evaluate_transformation_quality(
    points_source: np.ndarray,
    points_target: np.ndarray,
    transform_params: dict
) -> dict:
    """
    Оценивает качество преобразования по парам контрольных точек

    Args:
        points_source: исходные контрольные точки (N×3)
        points_target: целевые контрольные точки (N×3)
        transform_params: параметры преобразования

    Returns:
        Словарь с метриками качества:
        - rmse: среднеквадратичная ошибка
        - max_error: максимальная ошибка
        - mean_error: средняя ошибка
        - residuals: остаточные невязки для каждой точки
        - residuals_3d: остаточные невязки по координатам
    """
    if 'params' not in transform_params:
        raise ValueError("transform_params должен содержать ключ 'params'")

    params = transform_params['params']

    # Применяем преобразование
    transformed = helmert_transform_points(points_source, params)

    # Вычисляем невязки
    residuals_3d = transformed - points_target
    residuals = np.linalg.norm(residuals_3d, axis=1)

    rmse = np.sqrt(np.mean(residuals ** 2))
    max_error = np.max(residuals)
    mean_error = np.mean(residuals)

    return {
        'rmse': rmse,
        'max_error': max_error,
        'mean_error': mean_error,
        'residuals': residuals,
        'residuals_3d': residuals_3d
    }


def shift_points_along_z(points: pd.DataFrame, delta_z: float) -> pd.DataFrame:
    """Сместить все точки по оси Z на delta_z."""
    if points is None or points.empty:
        return points
    result = points.copy()
    result['z'] = result['z'] + float(delta_z)
    return result


def translate_points_xy(points: pd.DataFrame, tx: float, ty: float) -> pd.DataFrame:
    """Перенести все точки в плоскости XY на (tx, ty)."""
    if points is None or points.empty:
        return points
    result = points.copy()
    result['x'] = result['x'] + float(tx)
    result['y'] = result['y'] + float(ty)
    return result


def rotate_points_around_z(points: pd.DataFrame, angle_rad: float, center: np.ndarray) -> pd.DataFrame:
    """Повернуть все точки вокруг оси Z на angle_rad относительно центра center (x,y,z)."""
    if points is None or points.empty:
        return points
    cx, cy, cz = float(center[0]), float(center[1]), float(center[2])
    cos_a = np.cos(angle_rad)
    sin_a = np.sin(angle_rad)
    R = np.array([[cos_a, -sin_a, 0], [sin_a, cos_a, 0], [0, 0, 1]])
    xyz = points[['x', 'y', 'z']].values
    xyz_rel = xyz - np.array([cx, cy, cz])
    xyz_rot = (R @ xyz_rel.T).T + np.array([cx, cy, cz])
    result = points.copy()
    result['x'] = xyz_rot[:, 0]
    result['y'] = xyz_rot[:, 1]
    result['z'] = xyz_rot[:, 2]
    return result


def compute_xy_signed_angle(v1_xy: np.ndarray, v2_xy: np.ndarray, direction: int) -> float:
    """Вычислить направленный угол между 2D-векторами в плоскости XY с учетом direction (1 или -1). Возвращает радианы."""
    v1 = np.array([v1_xy[0], v1_xy[1]], dtype=float)
    v2 = np.array([v2_xy[0], v2_xy[1]], dtype=float)
    if np.linalg.norm(v1) < 1e-12 or np.linalg.norm(v2) < 1e-12:
        return 0.0
    angle = float(domain_signed_angle_rad(v1, v2))
    if direction < 0:
        angle = -angle
    return float(angle)
