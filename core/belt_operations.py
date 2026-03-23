"""
Модуль для работы с поясами башни
Функции создания линий поясов и выравнивания точек
"""

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def create_belt_plane(points: pd.DataFrame) -> dict:
    """
    Создание плоскости пояса по точкам методом наименьших квадратов

    Плоскость представляется уравнением: ax + by + cz + d = 0

    Args:
        points: DataFrame с колонками x, y, z

    Returns:
        Словарь с параметрами плоскости:
            - a, b, c, d: коэффициенты уравнения плоскости
            - center: центр плоскости (x, y, z)
            - normal: нормаль к плоскости (nx, ny, nz)
            - rmse: среднеквадратичная ошибка аппроксимации
    """
    if len(points) < 3:
        raise ValueError("Для создания плоскости нужно минимум 3 точки")

    # Координаты точек
    xyz = points[['x', 'y', 'z']].values

    # Центр масс
    center = xyz.mean(axis=0)

    # Центрируем точки
    xyz_centered = xyz - center

    # SVD для определения нормали к плоскости
    _, _, vh = np.linalg.svd(xyz_centered)
    normal = vh[-1]  # Последняя строка V^T - это нормаль

    # Нормализуем нормаль
    normal = normal / np.linalg.norm(normal)

    # Коэффициенты плоскости
    a, b, c = normal
    d = -np.dot(normal, center)

    # Вычисляем RMSE
    distances = np.abs(a * xyz[:, 0] + b * xyz[:, 1] + c * xyz[:, 2] + d)
    rmse = np.sqrt(np.mean(distances**2))

    return {
        'a': a,
        'b': b,
        'c': c,
        'd': d,
        'center': tuple(center),
        'normal': tuple(normal),
        'rmse': rmse
    }


def fit_circle_3d(points: pd.DataFrame) -> dict:
    """
    Аппроксимация окружности в 3D по точкам

    Сначала находим плоскость, затем проецируем точки на эту плоскость
    и аппроксимируем окружностью

    Args:
        points: DataFrame с колонками x, y, z

    Returns:
        Словарь с параметрами окружности:
            - center: центр окружности в 3D (x, y, z)
            - radius: радиус окружности
            - normal: нормаль к плоскости окружности
            - rmse: среднеквадратичная ошибка
    """
    if len(points) < 3:
        raise ValueError("Для аппроксимации окружности нужно минимум 3 точки")

    # Находим плоскость
    plane = create_belt_plane(points)

    # Координаты точек
    xyz = points[['x', 'y', 'z']].values

    # Проецируем точки на плоскость
    projected = project_points_to_plane(xyz, plane)

    # Центр масс проецированных точек
    center = projected.mean(axis=0)

    # Радиусы от центра
    radii = np.linalg.norm(projected - center, axis=1)
    radius = radii.mean()

    # RMSE
    rmse = np.sqrt(np.mean((radii - radius)**2))

    return {
        'center': tuple(center),
        'radius': radius,
        'normal': plane['normal'],
        'rmse': rmse
    }


def project_point_to_plane(point: np.ndarray, plane: dict) -> np.ndarray:
    """
    Проекция точки на плоскость

    Args:
        point: координаты точки [x, y, z]
        plane: параметры плоскости (a, b, c, d)

    Returns:
        Координаты проецированной точки [x', y', z']
    """
    a, b, c, d = plane['a'], plane['b'], plane['c'], plane['d']

    # Расстояние от точки до плоскости (со знаком)
    distance = (a * point[0] + b * point[1] + c * point[2] + d) / np.sqrt(a**2 + b**2 + c**2)

    # Проекция
    projected = point - distance * np.array([a, b, c])

    return projected


def project_points_to_plane(points: np.ndarray, plane: dict) -> np.ndarray:
    """
    Проекция массива точек на плоскость

    Args:
        points: массив координат точек (N x 3)
        plane: параметры плоскости

    Returns:
        Массив проецированных точек (N x 3)
    """
    return np.array([project_point_to_plane(p, plane) for p in points])


def align_points_to_belt(points: pd.DataFrame, belt_plane: dict) -> pd.DataFrame:
    """
    Выравнивание точек по плоскости пояса

    Проецирует все точки на заданную плоскость пояса

    Args:
        points: DataFrame с колонками x, y, z
        belt_plane: параметры плоскости пояса (из create_belt_plane)

    Returns:
        DataFrame с выровненными координатами
    """
    xyz = points[['x', 'y', 'z']].values

    # Проецируем точки на плоскость
    aligned_xyz = project_points_to_plane(xyz, belt_plane)

    # Создаем новый DataFrame
    result = points.copy()
    result['x'] = aligned_xyz[:, 0]
    result['y'] = aligned_xyz[:, 1]
    result['z'] = aligned_xyz[:, 2]

    # Добавляем информацию о смещении
    displacements = np.linalg.norm(xyz - aligned_xyz, axis=1)
    result['displacement'] = displacements

    logger.info(f"Выровнено {len(points)} точек. "
               f"Среднее смещение: {displacements.mean():.3f}м, "
               f"Макс. смещение: {displacements.max():.3f}м")

    return result


def calculate_belt_line(points: pd.DataFrame) -> dict:
    """
    Расчет параметров линии пояса (окружность/кольцо)

    Комбинирует создание плоскости и аппроксимацию окружности

    Args:
        points: DataFrame с колонками x, y, z

    Returns:
        Словарь с полной информацией о линии пояса:
            - plane: параметры плоскости
            - circle: параметры окружности
            - points_count: количество точек
            - quality_score: оценка качества аппроксимации (0-1)
    """
    if len(points) < 3:
        raise ValueError("Для расчета линии пояса нужно минимум 3 точки")

    plane = create_belt_plane(points)
    circle = fit_circle_3d(points)

    # Оценка качества (на основе RMSE относительно радиуса)
    quality_score = max(0, 1 - (circle['rmse'] / circle['radius'])) if circle['radius'] > 0 else 0

    return {
        'plane': plane,
        'circle': circle,
        'points_count': len(points),
        'quality_score': quality_score
    }


def validate_belt_geometry(points: pd.DataFrame,
                          max_height_deviation: float = 0.2,
                          max_radius_cv: float = 0.3) -> tuple[bool, str]:
    """
    Валидация геометрии пояса

    Проверяет, соответствуют ли точки требованиям пояса башни:
    - Точки должны лежать примерно в одной горизонтальной плоскости
    - Точки должны образовывать примерно окружность

    Args:
        points: DataFrame с колонками x, y, z
        max_height_deviation: максимальное стандартное отклонение по высоте (м)
        max_radius_cv: максимальный коэффициент вариации радиусов

    Returns:
        Кортеж (is_valid, message)
    """
    if len(points) < 3:
        return False, "Недостаточно точек для валидации (минимум 3)"

    # Проверка 1: Разброс по высоте
    z_std = points['z'].std()
    if z_std > max_height_deviation:
        return False, f"Большой разброс по высоте: {z_std:.3f}м (допустимо {max_height_deviation}м)"

    # Проверка 2: Окружность
    try:
        circle = fit_circle_3d(points)

        # Проверяем коэффициент вариации радиусов
        xyz = points[['x', 'y', 'z']].values
        center = np.array(circle['center'])
        radii = np.linalg.norm(xyz - center, axis=1)
        cv = radii.std() / radii.mean() if radii.mean() > 0 else 1.0

        if cv > max_radius_cv:
            return False, f"Точки не образуют окружность: CV={cv:.2f} (допустимо {max_radius_cv})"

    except Exception as e:
        return False, f"Ошибка аппроксимации окружности: {e!s}"

    return True, "Геометрия пояса валидна"


def generate_belt_circle_points(belt_line: dict, num_points: int = 50) -> np.ndarray:
    """
    Генерация точек для визуализации окружности пояса

    Args:
        belt_line: параметры линии пояса (из calculate_belt_line)
        num_points: количество точек окружности

    Returns:
        Массив координат точек окружности (num_points x 3)
    """
    circle = belt_line['circle']
    center = np.array(circle['center'])
    radius = circle['radius']
    normal = np.array(circle['normal'])

    # Создаем две ортогональные оси в плоскости окружности
    # Первая ось - произвольная перпендикулярная к нормали
    if abs(normal[2]) < 0.9:
        axis1 = np.cross(normal, np.array([0, 0, 1]))
    else:
        axis1 = np.cross(normal, np.array([1, 0, 0]))

    axis1 = axis1 / np.linalg.norm(axis1)

    # Вторая ось - перпендикулярна к нормали и первой оси
    axis2 = np.cross(normal, axis1)
    axis2 = axis2 / np.linalg.norm(axis2)

    # Генерируем точки окружности
    theta = np.linspace(0, 2 * np.pi, num_points)

    circle_points = []
    for t in theta:
        point = center + radius * (np.cos(t) * axis1 + np.sin(t) * axis2)
        circle_points.append(point)

    return np.array(circle_points)


def estimate_belt_count_from_heights(points: pd.DataFrame,
                                     height_tolerance: float = 0.15) -> int:
    """
    Оценка количества поясов по распределению высот

    Args:
        points: DataFrame с колонкой z
        height_tolerance: допуск для группировки по высоте

    Returns:
        Оценка количества поясов
    """
    from sklearn.cluster import DBSCAN

    heights = points['z'].values.reshape(-1, 1)

    # Кластеризация по высоте
    clustering = DBSCAN(eps=height_tolerance, min_samples=1).fit(heights)
    labels = clustering.labels_

    # Количество кластеров (исключая шум)
    n_clusters = len(set(labels)) - (1 if -1 in labels else 0)

    return n_clusters


def find_tower_axis(points: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """
    Находит вертикальную ось башни

    Алгоритм:
    1. Берет самую нижнюю точку
    2. Ищет точку над ней (близкую по XY, выше по Z)
    3. Строит вектор между ними и продлевает его

    Args:
        points: DataFrame с колонками x, y, z

    Returns:
        Кортеж (base_point, direction_vector)
        - base_point: точка начала оси (самая нижняя)
        - direction_vector: нормализованный вектор направления оси
    """
    if len(points) < 2:
        raise ValueError("Недостаточно точек для определения оси башни")

    # Исключаем возможную точку стоянки прибора
    station_idx = detect_instrument_station(points)
    working_points = points.copy()
    if station_idx is not None:
        working_points = working_points.drop(station_idx).reset_index(drop=True)
        logger.info(f"Исключена точка стоянки прибора (индекс {station_idx})")

    if len(working_points) < 2:
        working_points = points.copy()

    # Находим самую нижнюю точку
    lowest_idx = working_points['z'].idxmin()
    base_point = working_points.loc[lowest_idx, ['x', 'y', 'z']].values

    # Ищем точку над ней (близкую по XY, но выше по Z)
    other_points = working_points.drop(lowest_idx)

    # Вычисляем расстояния по XY от базовой точки
    xy_distances = np.sqrt(
        (other_points['x'] - base_point[0])**2 +
        (other_points['y'] - base_point[1])**2
    )

    # Находим точки выше базовой
    higher_points = other_points[other_points['z'] > base_point[2]]

    if len(higher_points) == 0:
        # Нет точек выше - используем аппроксимацию всех точек
        logger.warning("Нет точек выше базовой, используем аппроксимацию всех точек")
        xyz = working_points[['x', 'y', 'z']].values

        # Центр масс
        center = xyz.mean(axis=0)

        # SVD для нахождения главного направления
        centered = xyz - center
        _, _, vh = np.linalg.svd(centered)
        direction = vh[0]  # Первая главная компонента

        # Убеждаемся, что вектор направлен вверх
        if direction[2] < 0:
            direction = -direction

        return base_point, direction / np.linalg.norm(direction)

    # Среди точек выше базовой ищем ближайшую по XY
    xy_dist_higher = np.sqrt(
        (higher_points['x'] - base_point[0])**2 +
        (higher_points['y'] - base_point[1])**2
    )

    nearest_idx = xy_dist_higher.idxmin()
    upper_point = higher_points.loc[nearest_idx, ['x', 'y', 'z']].values

    # Вектор направления (от нижней к верхней)
    direction = upper_point - base_point
    direction = direction / np.linalg.norm(direction)

    logger.info(f"Ось башни: базовая точка {base_point}, направление {direction}")

    return base_point, direction


def distance_point_to_line(point: np.ndarray, line_point: np.ndarray,
                           line_direction: np.ndarray) -> float:
    """
    Вычисляет расстояние от точки до прямой в 3D

    Args:
        point: координаты точки [x, y, z]
        line_point: точка на прямой [x, y, z]
        line_direction: нормализованный вектор направления прямой

    Returns:
        Расстояние от точки до прямой
    """
    # Вектор от точки на прямой до рассматриваемой точки
    vec = point - line_point

    # Проекция vec на направление прямой
    projection_length = np.dot(vec, line_direction)

    # Ближайшая точка на прямой
    closest_point = line_point + projection_length * line_direction

    # Расстояние
    distance = np.linalg.norm(point - closest_point)

    return distance


def auto_assign_belts(points: pd.DataFrame,
                     expected_belt_count: int | None = None,
                     height_tolerance: float = 0.15) -> pd.DataFrame:
    """
    Автоматическое назначение поясов точкам

    Точки в файле идут последовательно снизу вверх:
    - Сначала все точки первого пояса
    - Потом все точки второго пояса
    - И так далее

    Алгоритм группирует точки по высоте с учетом заданного допуска.
    Нумерация поясов начинается с 1.

    Args:
        points: DataFrame с колонками x, y, z
        expected_belt_count: ожидаемое количество поясов (None = автоопределение)
        height_tolerance: допуск группировки по высоте (метры)

    Returns:
        DataFrame с добавленной колонкой belt (нумерация с 1)
    """
    from sklearn.cluster import DBSCAN, KMeans

    result = points.copy()

    if len(points) < 1:
        result['belt'] = None
        return result

    # Простая группировка по высоте
    heights = points['z'].values.reshape(-1, 1)

    if expected_belt_count is None or expected_belt_count <= 0:
        # Автоматическое определение количества поясов через DBSCAN
        clustering = DBSCAN(eps=height_tolerance, min_samples=1).fit(heights)
        labels = clustering.labels_

        # Переназначаем метки снизу вверх
        unique_labels = [l for l in sorted(set(labels)) if l != -1]

        if len(unique_labels) == 0:
            result['belt'] = None
            return result

        # Вычисляем среднюю высоту для каждой метки
        label_heights = {}
        for label in unique_labels:
            mask = labels == label
            label_heights[label] = points.loc[mask, 'z'].mean()

        # Сортируем по высоте и переназначаем с 1
        sorted_labels = sorted(label_heights.items(), key=lambda x: x[1])
        final_map = {old: new + 1 for new, (old, _) in enumerate(sorted_labels)}  # +1 для нумерации с 1

        # Назначаем пояса
        result['belt'] = [final_map.get(l) for l in labels]

        n_belts = len(unique_labels)

    else:
        # K-means с заданным количеством кластеров
        kmeans = KMeans(n_clusters=expected_belt_count, random_state=42, n_init=10)
        labels = kmeans.fit_predict(heights)

        # Переназначаем метки снизу вверх (с 1)
        unique_labels = sorted(set(labels))
        label_heights = {}

        for label in unique_labels:
            mask = labels == label
            label_heights[label] = points.loc[mask, 'z'].mean()

        # Сортируем по высоте
        sorted_labels = sorted(label_heights.items(), key=lambda x: x[1])
        final_map = {old: new + 1 for new, (old, _) in enumerate(sorted_labels)}  # +1 для нумерации с 1

        # Назначаем пояса
        result['belt'] = [final_map[l] for l in labels]

        n_belts = expected_belt_count

    n_assigned = result['belt'].notna().sum()
    logger.info(f"Назначено {n_belts} поясов для {n_assigned} точек (нумерация с 1)")

    return result


def project_point_to_belt_line(point: pd.DataFrame, belt_points: pd.DataFrame,
                               keep_height: bool = True) -> dict:
    """
    Проецирует точку на линию пояса (окружность)

    Алгоритм:
    1. Находит центр и радиус окружности пояса
    2. Проецирует точку на окружность в плоскости XY
    3. Сохраняет Z-координату точки (или использует среднюю Z пояса)

    Args:
        point: DataFrame с одной точкой (x, y, z)
        belt_points: DataFrame с точками пояса для построения окружности
        keep_height: Сохранить высоту точки (True) или использовать среднюю высоту пояса (False)

    Returns:
        Словарь с новыми координатами: {'x': new_x, 'y': new_y, 'z': new_z}
    """
    if len(belt_points) < 2:
        raise ValueError("Для построения линии пояса требуется минимум 2 точки")

    # Получаем координаты точки
    px = point['x'].iloc[0] if isinstance(point, pd.DataFrame) else point['x']
    py = point['y'].iloc[0] if isinstance(point, pd.DataFrame) else point['y']
    pz = point['z'].iloc[0] if isinstance(point, pd.DataFrame) else point['z']

    # Вычисляем центр окружности пояса (среднее по XY)
    center_x = belt_points['x'].mean()
    center_y = belt_points['y'].mean()
    center_z = belt_points['z'].mean()

    # Вычисляем средний радиус
    radii = np.sqrt((belt_points['x'] - center_x)**2 + (belt_points['y'] - center_y)**2)
    radius = radii.mean()

    # Вектор от центра к точке в плоскости XY
    dx = px - center_x
    dy = py - center_y
    distance_2d = np.sqrt(dx**2 + dy**2)

    if distance_2d < 1e-6:
        # Точка очень близко к центру, просто смещаем по X
        new_x = center_x + radius
        new_y = center_y
    else:
        # Нормализуем вектор и умножаем на радиус
        new_x = center_x + (dx / distance_2d) * radius
        new_y = center_y + (dy / distance_2d) * radius

    # Определяем Z-координату
    if keep_height:
        new_z = pz  # Сохраняем высоту точки
    else:
        new_z = center_z  # Используем среднюю высоту пояса

    logger.info(f"Точка спроецирована на пояс: ({px:.3f}, {py:.3f}, {pz:.3f}) → "
               f"({new_x:.3f}, {new_y:.3f}, {new_z:.3f}), радиус пояса: {radius:.3f}м")

    return {
        'x': new_x,
        'y': new_y,
        'z': new_z,
        'belt_center': (center_x, center_y, center_z),
        'belt_radius': radius,
        'distance_moved': np.sqrt((new_x - px)**2 + (new_y - py)**2 + (new_z - pz)**2)
    }


def detect_instrument_station(points: pd.DataFrame) -> int | None:
    """
    Определение точки стоянки прибора

    Обычно это самая нижняя точка, отстоящая отдельно от поясов башни

    Args:
        points: DataFrame с колонками x, y, z

    Returns:
        Индекс точки стоянки или None
    """
    if len(points) < 5:
        return None

    # Сортируем по высоте
    sorted_indices = points['z'].argsort()

    # Проверяем первую (самую нижнюю) точку
    lowest_idx = sorted_indices.iloc[0]
    lowest_z = points.loc[lowest_idx, 'z']

    # Проверяем, насколько она отстоит от остальных
    other_heights = points.loc[sorted_indices[1:], 'z']

    if len(other_heights) > 0:
        min_other_height = other_heights.min()
        height_diff = min_other_height - lowest_z

        # Если разница больше 1 метра, вероятно это точка стоянки
        if height_diff > 1.0:
            logger.info(f"Обнаружена возможная точка стоянки прибора: "
                       f"индекс {lowest_idx}, высота {lowest_z:.2f}м")
            return lowest_idx

    return None

