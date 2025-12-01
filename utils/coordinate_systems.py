"""
Модуль работы с координатными системами
"""

import pandas as pd
from typing import Optional, List, Tuple
import pyproj
from pyproj import CRS, Transformer
import logging

logger = logging.getLogger(__name__)


# Список популярных систем координат
COMMON_EPSG_CODES = {
    4326: "WGS 84 (GPS) - градусы",
    3857: "Web Mercator (Google Maps)",
    32601: "WGS 84 / UTM zone 1N",
    32637: "WGS 84 / UTM zone 37N (Москва)",
    32638: "WGS 84 / UTM zone 38N",
    32639: "WGS 84 / UTM zone 39N",
    32640: "WGS 84 / UTM zone 40N",
    2154: "RGF93 / Lambert-93 (Франция)",
    3395: "WGS 84 / World Mercator",
    4284: "Pulkovo 1942",
    28401: "Pulkovo 1942 / Gauss-Kruger zone 1",
    28402: "Pulkovo 1942 / Gauss-Kruger zone 2",
    28403: "Pulkovo 1942 / Gauss-Kruger zone 3",
    28404: "Pulkovo 1942 / Gauss-Kruger zone 4",
    28405: "Pulkovo 1942 / Gauss-Kruger zone 5",
    28406: "Pulkovo 1942 / Gauss-Kruger zone 6",
    28407: "Pulkovo 1942 / Gauss-Kruger zone 7",
    3576: "WGS 84 / North Pole",
}


def get_common_epsg_list() -> List[Tuple[int, str]]:
    """
    Возвращает список популярных систем координат
    
    Returns:
        Список кортежей (код EPSG, описание)
    """
    return [(code, desc) for code, desc in COMMON_EPSG_CODES.items()]


def detect_epsg(file_path: str) -> Optional[int]:
    """
    Пытается определить EPSG код из файла
    
    Args:
        file_path: Путь к файлу
        
    Returns:
        Код EPSG или None
    """
    try:
        from osgeo import ogr, osr
        
        ds = ogr.Open(file_path)
        if ds is None:
            return None
        
        layer = ds.GetLayer()
        srs = layer.GetSpatialRef()
        
        if srs:
            srs.AutoIdentifyEPSG()
            epsg_code = srs.GetAuthorityCode(None)
            if epsg_code:
                return int(epsg_code)
    except:
        pass
    
    return None


def validate_epsg(epsg_code: int) -> bool:
    """
    Проверяет валидность EPSG кода
    
    Args:
        epsg_code: Код EPSG
        
    Returns:
        True если код валиден
    """
    try:
        crs = CRS.from_epsg(epsg_code)
        return crs is not None
    except:
        return False


def get_crs_info(epsg_code: int) -> dict:
    """
    Получает информацию о системе координат
    
    Args:
        epsg_code: Код EPSG
        
    Returns:
        Словарь с информацией о СК
    """
    try:
        crs = CRS.from_epsg(epsg_code)
        return {
            'epsg': epsg_code,
            'name': crs.name,
            'type': crs.type_name,
            'unit': crs.axis_info[0].unit_name if crs.axis_info else 'unknown',
            'valid': True
        }
    except Exception as e:
        return {
            'epsg': epsg_code,
            'name': 'Unknown',
            'type': 'Unknown',
            'unit': 'unknown',
            'valid': False,
            'error': str(e)
        }


def transform_coordinates(points: pd.DataFrame, 
                         from_epsg: int, 
                         to_epsg: int) -> pd.DataFrame:
    """
    Трансформирует координаты из одной системы в другую
    
    Args:
        points: DataFrame с колонками x, y, z
        from_epsg: Исходная система координат
        to_epsg: Целевая система координат
        
    Returns:
        DataFrame с трансформированными координатами
    """
    if from_epsg == to_epsg:
        return points.copy()
    
    try:
        # Создаем трансформер
        transformer = Transformer.from_crs(
            f"EPSG:{from_epsg}",
            f"EPSG:{to_epsg}",
            always_xy=True
        )
        
        # Трансформируем координаты
        result = points.copy()
        x_new, y_new = transformer.transform(points['x'].values, points['y'].values)
        
        result['x'] = x_new
        result['y'] = y_new
        # Z координата обычно остается без изменений для плоских преобразований
        
        return result
        
    except Exception as e:
        raise ValueError(f"Ошибка трансформации координат: {str(e)}")


def is_projected_crs(epsg_code: int) -> bool:
    """
    Определяет, является ли СК проекционной (метрической)
    
    Args:
        epsg_code: Код EPSG
        
    Returns:
        True если СК проекционная (метры)
    """
    try:
        crs = CRS.from_epsg(epsg_code)
        return crs.is_projected
    except:
        return False


def suggest_projected_crs(lon: float, lat: float) -> int:
    """
    Предлагает подходящую проекционную систему координат для данной точки
    
    Args:
        lon: Долгота (WGS84)
        lat: Широта (WGS84)
        
    Returns:
        Рекомендуемый код EPSG (UTM зона)
    """
    # Определяем UTM зону
    utm_zone = int((lon + 180) / 6) + 1
    
    # Северное или южное полушарие
    if lat >= 0:
        # Северное полушарие
        epsg = 32600 + utm_zone
    else:
        # Южное полушарие
        epsg = 32700 + utm_zone
    
    return epsg


def convert_to_meters(points: pd.DataFrame, epsg_code: Optional[int]) -> pd.DataFrame:
    """
    Конвертирует координаты в метры, если они в градусах
    
    Args:
        points: DataFrame с координатами
        epsg_code: Код EPSG или None
    
    Returns:
        DataFrame с координатами в метрах
    """
    # Проверяем наличие необходимых колонок
    if 'x' not in points.columns or 'y' not in points.columns:
        logger.error(f"В DataFrame отсутствуют колонки x или y. Доступные колонки: {points.columns.tolist()}")
        return points.copy()
    
    if epsg_code is None:
        # Пробуем определить автоматически
        # Если координаты в диапазоне [-180, 180] и [-90, 90], вероятно градусы
        if len(points) > 0 and (points['x'].abs().max() <= 180 and points['y'].abs().max() <= 90):
            # Центр данных
            center_lon = points['x'].mean()
            center_lat = points['y'].mean()
            
            # Определяем подходящую UTM зону
            target_epsg = suggest_projected_crs(center_lon, center_lat)
            
            # Трансформируем из WGS84
            return transform_coordinates(points, 4326, target_epsg)
        else:
            # Предполагаем, что уже в метрах
            return points.copy()
    else:
        if is_projected_crs(epsg_code):
            # Уже в метрах
            return points.copy()
        else:
            # Нужно трансформировать
            # Определяем целевую систему
            center_lon = points['x'].mean()
            center_lat = points['y'].mean()
            target_epsg = suggest_projected_crs(center_lon, center_lat)
            
            return transform_coordinates(points, epsg_code, target_epsg)


class CoordinateSystemManager:
    """
    Менеджер для управления системами координат
    """
    
    def __init__(self):
        self.current_epsg = None
        self.original_epsg = None
        self.working_epsg = None
        
    def set_original_crs(self, epsg_code: int):
        """Устанавливает исходную систему координат"""
        if validate_epsg(epsg_code):
            self.original_epsg = epsg_code
            self.current_epsg = epsg_code
        else:
            raise ValueError(f"Невалидный EPSG код: {epsg_code}")
    
    def set_working_crs(self, epsg_code: int):
        """Устанавливает рабочую систему координат (для расчетов)"""
        if validate_epsg(epsg_code):
            self.working_epsg = epsg_code
        else:
            raise ValueError(f"Невалидный EPSG код: {epsg_code}")
    
    def prepare_for_calculations(self, points: pd.DataFrame) -> pd.DataFrame:
        """
        Подготавливает данные для расчетов (переводит в метры)
        
        Args:
            points: Исходные данные
            
        Returns:
            Данные в метрической системе
        """
        if self.original_epsg is None:
            return convert_to_meters(points, None)
        
        # Если рабочая СК не задана, определяем автоматически
        if self.working_epsg is None:
            if is_projected_crs(self.original_epsg):
                self.working_epsg = self.original_epsg
            else:
                # Определяем подходящую UTM зону
                center_lon = points['x'].mean()
                center_lat = points['y'].mean()
                self.working_epsg = suggest_projected_crs(center_lon, center_lat)
        
        # Трансформируем
        return transform_coordinates(points, self.original_epsg, self.working_epsg)
    
    def get_info(self) -> dict:
        """Возвращает информацию о текущих системах координат"""
        return {
            'original': get_crs_info(self.original_epsg) if self.original_epsg else None,
            'working': get_crs_info(self.working_epsg) if self.working_epsg else None,
            'current': get_crs_info(self.current_epsg) if self.current_epsg else None
        }

