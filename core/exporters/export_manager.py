"""
Менеджер экспорта данных в различные форматы
"""

import logging
from typing import Optional, Dict, Any
import pandas as pd
from pathlib import Path

from core.exceptions import ExportError, DataValidationError
from core.exporters.geojson_exporter import export_data_to_geojson
from core.exporters.kml_exporter import export_data_to_kml

logger = logging.getLogger(__name__)


def export_data(
    data: pd.DataFrame,
    file_path: str,
    format: str = 'auto',
    epsg_code: Optional[int] = None,
    **kwargs
) -> None:
    """
    Экспортирует данные в указанный формат
    
    Args:
        data: DataFrame с данными
        file_path: Путь для сохранения файла
        format: Формат экспорта ('auto', 'geojson', 'kml', 'csv', 'shapefile')
        epsg_code: EPSG код системы координат
        **kwargs: Дополнительные параметры для экспортеров
        
    Raises:
        ExportError: При ошибке экспорта
        DataValidationError: При некорректных данных
    """
    if data is None or data.empty:
        raise DataValidationError("Нет данных для экспорта")
    
    # Определяем формат, если auto
    if format == 'auto':
        format = Path(file_path).suffix.lower().lstrip('.')
        if format not in ['geojson', 'json', 'kml', 'csv', 'shp']:
            format = 'csv'  # По умолчанию CSV
    
    # Нормализуем формат
    format_map = {
        'json': 'geojson',
        'shp': 'shapefile'
    }
    format = format_map.get(format, format)
    
    try:
        if format == 'geojson':
            export_data_to_geojson(data, file_path, epsg_code=epsg_code, **kwargs)
        elif format == 'kml':
            export_data_to_kml(data, file_path, epsg_code=epsg_code, **kwargs)
        elif format == 'csv':
            export_data_to_csv_enhanced(data, file_path, epsg_code=epsg_code, **kwargs)
        elif format == 'shapefile':
            export_data_to_shapefile(data, file_path, epsg_code=epsg_code, **kwargs)
        else:
            raise ExportError(f"Неподдерживаемый формат экспорта: {format}")
        
        logger.info(f"Данные успешно экспортированы в {format.upper()}: {file_path}")
        
    except (ExportError, DataValidationError):
        raise
    except Exception as e:
        raise ExportError(f"Ошибка экспорта в {format}: {str(e)}") from e


def export_data_to_csv_enhanced(
    data: pd.DataFrame,
    file_path: str,
    epsg_code: Optional[int] = None,
    include_metadata: bool = True,
    include_results: Optional[Dict[str, Any]] = None
) -> None:
    """
    Экспортирует данные в расширенный CSV формат с метаданными и результатами
    
    Args:
        data: DataFrame с данными
        file_path: Путь для сохранения CSV файла
        epsg_code: EPSG код системы координат
        include_metadata: Включать ли метаданные в комментарии
        include_results: Результаты расчетов для включения в файл
        
    Raises:
        ExportError: При ошибке экспорта
        DataValidationError: При некорректных данных
    """
    if data is None or data.empty:
        raise DataValidationError("Нет данных для экспорта")
    
    try:
        with open(file_path, 'w', encoding='utf-8-sig', newline='') as f:
            # Записываем метаданные в комментариях, если нужно
            if include_metadata:
                f.write(f"# GeoVertical Analyzer Export\n")
                f.write(f"# EPSG Code: {epsg_code or 'Не указан'}\n")
                f.write(f"# Point Count: {len(data)}\n")
                if include_results:
                    centers = include_results.get('centers', pd.DataFrame())
                    if not centers.empty:
                        f.write(f"# Belts Count: {len(centers)}\n")
                f.write(f"#\n")
            
            # Экспортируем данные
            data.to_csv(f, index=False, encoding='utf-8-sig')
        
        logger.info(f"Данные экспортированы в расширенный CSV: {file_path} ({len(data)} точек)")
        
    except (IOError, OSError, ValueError, KeyError) as e:
        raise ExportError(f"Ошибка экспорта в CSV: {str(e)}") from e


def export_data_to_shapefile(
    data: pd.DataFrame,
    file_path: str,
    epsg_code: Optional[int] = None
) -> None:
    """
    Экспортирует данные в формат Shapefile
    
    Args:
        data: DataFrame с данными
        file_path: Путь для сохранения Shapefile (без расширения)
        epsg_code: EPSG код системы координат
        
    Raises:
        ExportError: При ошибке экспорта
        DataValidationError: При некорректных данных
    """
    try:
        import geopandas as gpd
        from shapely.geometry import Point
    except ImportError:
        raise ExportError(
            "Для экспорта в Shapefile требуется установить geopandas и shapely:\n"
            "pip install geopandas shapely"
        )
    
    if data is None or data.empty:
        raise DataValidationError("Нет данных для экспорта")
    
    required_cols = ['x', 'y', 'z', 'name']
    if not all(col in data.columns for col in required_cols):
        raise DataValidationError(f"Отсутствуют необходимые колонки: {required_cols}")
    
    try:
        # Создаем геометрию точек
        geometry = [Point(x, y) for x, y in zip(data['x'], data['y'])]
        
        # Создаем GeoDataFrame
        gdf = gpd.GeoDataFrame(data, geometry=geometry, crs=f"EPSG:{epsg_code}" if epsg_code else None)
        
        # Удаляем колонки x, y из атрибутов (они уже в geometry)
        gdf = gdf.drop(columns=['x', 'y'], errors='ignore')
        
        # Сохраняем в Shapefile
        gdf.to_file(file_path, driver='ESRI Shapefile', encoding='utf-8')
        
        logger.info(f"Данные экспортированы в Shapefile: {file_path} ({len(data)} точек)")
        
    except Exception as e:
        raise ExportError(f"Ошибка экспорта в Shapefile: {str(e)}") from e

