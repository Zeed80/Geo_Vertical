"""
Модуль автоматической фильтрации точек башни
Геометрический анализ для выделения точек башни из общих геодезических данных
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Tuple, Optional
from scipy.spatial.distance import pdist, squareform
from scipy.cluster.hierarchy import fcluster, linkage
from sklearn.cluster import DBSCAN
import logging

logger = logging.getLogger(__name__)


class PointFilter:
    """
    Фильтр точек для автоматического выделения точек башни
    
    Алгоритм:
    1. Группировка по высоте (находим пояса)
    2. Геометрический анализ каждого пояса
    3. Определение оси башни
    4. Исключение выбросов
    """
    
    def __init__(self, 
                 height_tolerance: float = 0.15,
                 min_points_per_belt: int = 1,
                 max_points_per_belt: int = 20,
                 circularity_threshold: float = 0.0,
                 axis_deviation_threshold: float = 100.0):
        """
        Args:
            height_tolerance: Допуск группировки по высоте (м)
            min_points_per_belt: Минимум точек на поясе
            max_points_per_belt: Максимум точек на поясе
            circularity_threshold: Порог "круглости" пояса (0-1)
            axis_deviation_threshold: Допустимое отклонение центра пояса от оси (м)
        """
        self.height_tolerance = height_tolerance
        self.min_points = min_points_per_belt
        self.max_points = max_points_per_belt
        self.circularity_threshold = circularity_threshold
        self.axis_deviation_threshold = axis_deviation_threshold
        
        self.analysis_results = {}
    
    def analyze_and_filter(self, data: pd.DataFrame) -> Tuple[pd.DataFrame, Dict]:
        """
        Автоматический анализ и фильтрация точек
        
        Args:
            data: DataFrame с колонками x, y, z
            
        Returns:
            (filtered_data, analysis_info)
            - filtered_data: Отфильтрованные точки башни
            - analysis_info: Информация об анализе
        """
        logger.info(f"Анализ {len(data)} точек для выделения башни")
        
        # Шаг 1: Группировка по высоте
        belts = self._group_by_height(data)
        logger.info(f"Найдено {len(belts)} потенциальных поясов")
        
        # Шаг 2: Анализ геометрии каждого пояса
        valid_belts = []
        rejected_belts = []
        
        for belt_id, belt_points in belts.items():
            is_valid, reason, metrics = self._analyze_belt_geometry(belt_points)
            
            if is_valid:
                valid_belts.append({
                    'belt_id': belt_id,
                    'points': belt_points,
                    'metrics': metrics
                })
            else:
                rejected_belts.append({
                    'belt_id': belt_id,
                    'points': belt_points,
                    'reason': reason,
                    'metrics': metrics
                })
        
        logger.info(f"Валидных поясов: {len(valid_belts)}, отклонено: {len(rejected_belts)}")
        
        # Шаг 3: Определение оси башни (только если все пояса с несколькими точками)
        all_multi_point = all(len(belt['points']) > 1 for belt in valid_belts)
        tower_axis = None
        
        if len(valid_belts) >= 2 and all_multi_point:
            tower_axis, outlier_belts = self._find_tower_axis(valid_belts)
            
            # Исключаем пояса, далекие от оси
            for outlier in outlier_belts:
                valid_belts = [b for b in valid_belts if b['belt_id'] != outlier['belt_id']]
                rejected_belts.append(outlier)
            
            logger.info(f"Ось башни определена, исключено выбросов: {len(outlier_belts)}")
        else:
            if not all_multi_point:
                logger.info("Пропущено определение оси (есть пояса с одной точкой - центры поясов)")
            else:
                logger.warning("Недостаточно поясов для определения оси башни")
        
        # Шаг 4: Формирование результата
        if valid_belts:
            filtered_indices = []
            for belt in valid_belts:
                filtered_indices.extend(belt['points'].index.tolist())
            
            filtered_data = data.loc[filtered_indices].copy()
            
            # Добавляем метку "belt_id" для группировки
            for belt in valid_belts:
                filtered_data.loc[belt['points'].index, 'belt_id'] = belt['belt_id']
        else:
            filtered_data = pd.DataFrame(columns=data.columns)
            logger.warning("Не найдено валидных поясов башни!")
        
        # Информация об анализе
        analysis_info = {
            'total_points': len(data),
            'filtered_points': len(filtered_data),
            'total_belts_found': len(belts),
            'valid_belts': len(valid_belts),
            'rejected_belts': len(rejected_belts),
            'tower_axis': tower_axis,
            'valid_belt_details': valid_belts,
            'rejected_belt_details': rejected_belts,
            'filter_params': {
                'height_tolerance': self.height_tolerance,
                'min_points': self.min_points,
                'max_points': self.max_points,
                'circularity_threshold': self.circularity_threshold
            }
        }
        
        self.analysis_results = analysis_info
        
        return filtered_data, analysis_info
    
    def _group_by_height(self, data: pd.DataFrame) -> Dict[int, pd.DataFrame]:
        """Группировка точек по высоте используя DBSCAN"""
        heights = data['z'].values.reshape(-1, 1)
        
        # DBSCAN кластеризация по высоте
        clustering = DBSCAN(eps=self.height_tolerance, min_samples=1).fit(heights)
        labels = clustering.labels_
        
        # Группируем по меткам кластеров
        belts = {}
        for label in set(labels):
            if label == -1:  # Шум в DBSCAN
                continue
            
            mask = labels == label
            belt_points = data[mask].copy()
            
            # Сортируем по высоте для ID (нижние пояса - меньшие ID)
            mean_height = belt_points['z'].mean()
            belts[label] = belt_points
        
        # Переназначаем ID по высоте (снизу вверх)
        sorted_belts = sorted(belts.items(), key=lambda x: x[1]['z'].mean())
        renumbered_belts = {i: belt for i, (_, belt) in enumerate(sorted_belts)}
        
        return renumbered_belts
    
    def _analyze_belt_geometry(self, belt_points: pd.DataFrame) -> Tuple[bool, str, Dict]:
        """
        Анализ геометрии пояса для определения, является ли он поясом башни
        
        Returns:
            (is_valid, rejection_reason, metrics)
        """
        n_points = len(belt_points)
        
        # Метрики
        metrics = {
            'n_points': n_points,
            'height_mean': belt_points['z'].mean(),
            'height_std': belt_points['z'].std()
        }
        
        # Проверка 1: Количество точек
        if n_points < self.min_points:
            return False, f"Слишком мало точек ({n_points} < {self.min_points})", metrics
        
        if n_points > self.max_points:
            return False, f"Слишком много точек ({n_points} > {self.max_points})", metrics
        
        # Проверка 2: Высота точек пояса должна быть примерно одинаковой
        if metrics['height_std'] > self.height_tolerance:
            return False, f"Большой разброс по высоте (σ={metrics['height_std']:.3f}m)", metrics
        
        # Проверка 3: Геометрический анализ (точки образуют окружность?)
        xy_points = belt_points[['x', 'y']].values
        
        # Для поясов с одной точкой - особый случай (центры поясов)
        if n_points == 1:
            metrics['center_x'] = xy_points[0, 0]
            metrics['center_y'] = xy_points[0, 1]
            metrics['radius_mean'] = 0.0
            metrics['radius_std'] = 0.0
            metrics['circularity'] = 1.0  # Устанавливаем максимальную круглость
            metrics['angular_uniformity'] = 1.0
            # Все проверки пройдены для пояса из одной точки
            return True, "", metrics
        
        # Центр масс (для поясов с несколькими точками)
        center = xy_points.mean(axis=0)
        metrics['center_x'] = center[0]
        metrics['center_y'] = center[1]
        
        # Радиусы от центра
        radii = np.linalg.norm(xy_points - center, axis=1)
        metrics['radius_mean'] = radii.mean()
        metrics['radius_std'] = radii.std()
        
        # Коэффициент вариации радиусов (мера "круглости")
        if metrics['radius_mean'] > 0:
            cv_radius = metrics['radius_std'] / metrics['radius_mean']
            metrics['circularity'] = 1.0 - min(cv_radius, 1.0)  # 1.0 = идеальная окружность
        else:
            metrics['circularity'] = 0.0
        
        # Проверка 4: "Круглость" пояса (смягченная проверка)
        # Пропускаем для поясов с малым количеством точек И если threshold = 0
        if n_points >= 4 and self.circularity_threshold > 0 and metrics['circularity'] < self.circularity_threshold:
            # Даем второй шанс: если радиусы примерно одинаковые
            cv_radius = metrics['radius_std'] / metrics['radius_mean'] if metrics['radius_mean'] > 0 else 1.0
            if cv_radius > 0.5:  # Очень высокий разброс радиусов
                return False, f"Точки не образуют окружность (circularity={metrics['circularity']:.2f})", metrics
        
        # Проверка 5: Точки не должны быть слишком близко друг к другу (не дубликаты)
        if n_points > 1:
            distances = pdist(xy_points)
            min_distance = distances.min()
            metrics['min_point_distance'] = min_distance
            
            if min_distance < 0.01:  # Меньше 1 см
                return False, "Точки слишком близко (возможно дубликаты)", metrics
        
        # Проверка 6: Угловое распределение точек (для башен с секциями)
        if n_points >= 3:
            angles = np.arctan2(xy_points[:, 1] - center[1], 
                              xy_points[:, 0] - center[0])
            angles = np.sort(angles)
            
            # Разница между соседними углами
            angle_diffs = np.diff(angles)
            angle_diffs = np.append(angle_diffs, 2*np.pi + angles[0] - angles[-1])
            
            # Средняя разница и std
            expected_angle = 2 * np.pi / n_points
            angle_std = np.std(angle_diffs)
            metrics['angular_uniformity'] = 1.0 - min(angle_std / expected_angle, 1.0)
        
        # Все проверки пройдены!
        return True, "", metrics
    
    def _find_tower_axis(self, valid_belts: List[Dict]) -> Tuple[Optional[Dict], List[Dict]]:
        """
        Определение вертикальной оси башни и исключение выбросов
        
        Returns:
            (axis_params, outlier_belts)
        """
        if len(valid_belts) < 2:
            return None, []
        
        # Собираем центры поясов
        centers = np.array([[belt['metrics']['center_x'], 
                           belt['metrics']['center_y'],
                           belt['metrics']['height_mean']] 
                          for belt in valid_belts])
        
        # Средний центр (примерная ось башни)
        mean_center = centers[:, :2].mean(axis=0)
        
        # Расстояния центров поясов от средней оси
        deviations = np.linalg.norm(centers[:, :2] - mean_center, axis=1)
        
        # Параметры оси
        axis_params = {
            'center_x': mean_center[0],
            'center_y': mean_center[1],
            'deviation_mean': deviations.mean(),
            'deviation_std': deviations.std(),
            'deviation_max': deviations.max()
        }
        
        # Находим выбросы (пояса, далекие от оси)
        outliers = []
        for i, (belt, deviation) in enumerate(zip(valid_belts, deviations)):
            if deviation > self.axis_deviation_threshold:
                outlier = belt.copy()
                outlier['reason'] = f"Далеко от оси башни (отклонение {deviation:.2f}m)"
                outliers.append(outlier)
                logger.debug(f"Пояс {belt['belt_id']} исключен как выброс (deviation={deviation:.2f}m)")
        
        return axis_params, outliers
    
    def get_classification(self, data: pd.DataFrame) -> pd.Series:
        """
        Возвращает классификацию точек
        
        Returns:
            Series с метками: 'tower' (башня), 'rejected' (отклонено), 'unknown' (неизвестно)
        """
        if not self.analysis_results:
            return pd.Series(['unknown'] * len(data), index=data.index)
        
        classification = pd.Series(['rejected'] * len(data), index=data.index)
        
        # Помечаем точки башни
        for belt in self.analysis_results['valid_belt_details']:
            classification.loc[belt['points'].index] = 'tower'
        
        return classification
    
    def get_summary(self) -> str:
        """Возвращает текстовое резюме анализа"""
        if not self.analysis_results:
            return "Анализ не выполнен"
        
        info = self.analysis_results
        
        summary = f"""
РЕЗУЛЬТАТЫ АВТОМАТИЧЕСКОЙ ФИЛЬТРАЦИИ ТОЧЕК
{'='*50}

Всего точек: {info['total_points']}
Отфильтровано для башни: {info['filtered_points']} ({info['filtered_points']/info['total_points']*100:.1f}%)
Исключено: {info['total_points'] - info['filtered_points']}

Найдено поясов: {info['total_belts_found']}
  ✓ Валидных: {info['valid_belts']}
  ✗ Отклонено: {info['rejected_belts']}

Параметры фильтрации:
  - Допуск по высоте: {info['filter_params']['height_tolerance']} м
  - Точек на пояс: {info['filter_params']['min_points']}-{info['filter_params']['max_points']}
  - Порог круглости: {info['filter_params']['circularity_threshold']}
"""
        
        if info['tower_axis']:
            axis = info['tower_axis']
            summary += f"""
Ось башни:
  - Центр: X={axis['center_x']:.3f}, Y={axis['center_y']:.3f}
  - Отклонение поясов: {axis['deviation_mean']:.3f} ± {axis['deviation_std']:.3f} м
  - Макс. отклонение: {axis['deviation_max']:.3f} м
"""
        
        # Детали валидных поясов
        if info['valid_belt_details']:
            summary += "\nВалидные пояса:\n"
            for belt in info['valid_belt_details']:
                m = belt['metrics']
                summary += f"  Пояс {belt['belt_id']}: {m['n_points']} точек на h={m['height_mean']:.2f}м, "
                summary += f"R={m['radius_mean']:.2f}м, круглость={m['circularity']:.2f}\n"
        
        # Детали отклоненных
        if info['rejected_belt_details']:
            summary += "\nОтклоненные группы:\n"
            for belt in info['rejected_belt_details'][:5]:  # Показываем первые 5
                m = belt['metrics']
                summary += f"  Группа {belt['belt_id']}: {m['n_points']} точек на h={m['height_mean']:.2f}м\n"
                summary += f"    Причина: {belt['reason']}\n"
        
        return summary


class InteractivePointSelector:
    """
    Класс для интерактивного выбора точек пользователем
    (Используется совместно с GUI)
    """
    
    def __init__(self, data: pd.DataFrame):
        self.data = data.copy()
        self.selection = pd.Series([True] * len(data), index=data.index)  # Все выбраны по умолчанию
    
    def set_selection(self, indices: List[int], selected: bool = True):
        """Установить выбор для указанных индексов"""
        self.selection.loc[indices] = selected
    
    def toggle_selection(self, indices: List[int]):
        """Переключить выбор для указанных индексов"""
        self.selection.loc[indices] = ~self.selection.loc[indices]
    
    def select_by_height_range(self, z_min: float, z_max: float, selected: bool = True):
        """Выбрать точки в диапазоне высот"""
        mask = (self.data['z'] >= z_min) & (self.data['z'] <= z_max)
        self.selection.loc[mask] = selected
    
    def select_by_radius(self, center_x: float, center_y: float, radius: float, selected: bool = True):
        """Выбрать точки в радиусе от центра"""
        distances = np.sqrt((self.data['x'] - center_x)**2 + (self.data['y'] - center_y)**2)
        mask = distances <= radius
        self.selection.loc[mask] = selected
    
    def get_selected_data(self) -> pd.DataFrame:
        """Получить выбранные точки"""
        return self.data[self.selection].copy()
    
    def get_rejected_data(self) -> pd.DataFrame:
        """Получить отклоненные точки"""
        return self.data[~self.selection].copy()
    
    def get_selection_mask(self) -> pd.Series:
        """Получить маску выбора"""
        return self.selection.copy()


def analyze_with_belt_count(data: pd.DataFrame, expected_belt_count: int, 
                            height_tolerance: float = 0.15) -> Tuple[pd.DataFrame, Dict]:
    """
    Улучшенный анализ с учетом ожидаемого количества поясов
    
    Учитывает последовательность съемки снизу вверх и точку стоянки прибора
    
    Args:
        data: DataFrame с колонками x, y, z
        expected_belt_count: Ожидаемое количество поясов
        height_tolerance: Допуск группировки по высоте
        
    Returns:
        (filtered_data, analysis_info)
    """
    from core.belt_operations import detect_instrument_station, auto_assign_belts
    from sklearn.cluster import KMeans
    
    logger.info(f"Улучшенный анализ: ожидается {expected_belt_count} поясов")
    
    # Шаг 1: Определение точки стоянки прибора
    station_idx = detect_instrument_station(data)
    
    if station_idx is not None:
        # Исключаем точку стоянки
        data_without_station = data.drop(station_idx).reset_index(drop=True)
        logger.info(f"Исключена точка стоянки прибора: индекс {station_idx}")
    else:
        data_without_station = data.copy()
    
    # Шаг 2: Группировка по высоте с K-means (более надежно при известном количестве)
    if len(data_without_station) >= expected_belt_count:
        heights = data_without_station['z'].values.reshape(-1, 1)
        
        # K-means кластеризация
        kmeans = KMeans(n_clusters=expected_belt_count, random_state=42, n_init=10)
        labels = kmeans.fit_predict(heights)
        
        # Переназначаем метки снизу вверх
        unique_labels = sorted(set(labels))
        label_heights = {}
        
        for label in unique_labels:
            mask = labels == label
            mean_height = data_without_station.loc[mask, 'z'].mean()
            label_heights[label] = mean_height
        
        # Сортируем по высоте
        sorted_labels = sorted(label_heights.items(), key=lambda x: x[1])
        label_map = {old: new for new, (old, _) in enumerate(sorted_labels)}
        
        # Назначаем пояса
        data_without_station['belt'] = [label_map[l] for l in labels]
        
        # Анализ качества группировки
        belt_stats = []
        for belt_num in range(expected_belt_count):
            belt_points = data_without_station[data_without_station['belt'] == belt_num]
            if len(belt_points) > 0:
                belt_stats.append({
                    'belt': belt_num,
                    'count': len(belt_points),
                    'mean_height': belt_points['z'].mean(),
                    'std_height': belt_points['z'].std()
                })
        
        analysis_info = {
            'method': 'kmeans_with_belt_count',
            'expected_belts': expected_belt_count,
            'found_belts': expected_belt_count,
            'station_excluded': station_idx is not None,
            'belt_stats': belt_stats,
            'total_points': len(data),
            'filtered_points': len(data_without_station)
        }
        
        return data_without_station, analysis_info
    else:
        logger.warning(f"Недостаточно точек ({len(data_without_station)}) для {expected_belt_count} поясов")
        # Fallback на автоматическую группировку
        return auto_assign_belts(data_without_station, None, height_tolerance), {
            'method': 'fallback_auto',
            'warning': 'Недостаточно точек для заданного количества поясов'
        }
