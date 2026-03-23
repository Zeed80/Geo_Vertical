"""
Экспорт данных GeoVertical в формат GeoJSON
"""

import json
import logging

import pandas as pd

from core.exceptions import DataValidationError, ExportError

logger = logging.getLogger(__name__)


def export_data_to_geojson(
    data: pd.DataFrame,
    file_path: str,
    epsg_code: int | None = None,
    include_metadata: bool = True
) -> None:
    """
    Экспортирует данные точек в формат GeoJSON

    Args:
        data: DataFrame с колонками ['x', 'y', 'z', 'name'] и опционально ['belt', 'is_station']
        file_path: Путь для сохранения GeoJSON файла
        epsg_code: EPSG код системы координат (опционально)
        include_metadata: Включать ли метаданные в файл

    Raises:
        ExportError: При ошибке экспорта
        DataValidationError: При некорректных данных
    """
    if data is None or data.empty:
        raise DataValidationError("Нет данных для экспорта")

    required_cols = ['x', 'y', 'z', 'name']
    if not all(col in data.columns for col in required_cols):
        raise DataValidationError(f"Отсутствуют необходимые колонки: {required_cols}")

    try:
        # Создаем структуру GeoJSON
        geojson = {
            "type": "FeatureCollection",
            "features": []
        }

        # Добавляем CRS, если указан EPSG
        if epsg_code:
            geojson["crs"] = {
                "type": "name",
                "properties": {
                    "name": f"urn:ogc:def:crs:EPSG::{epsg_code}"
                }
            }

        # Преобразуем точки в GeoJSON features
        for idx, row in data.iterrows():
            feature = {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [float(row['x']), float(row['y']), float(row['z'])]
                },
                "properties": {
                    "name": str(row['name']),
                }
            }

            # Добавляем дополнительные свойства
            if 'belt' in data.columns and pd.notna(row.get('belt')):
                feature["properties"]["belt"] = int(row['belt'])

            if 'is_station' in data.columns and pd.notna(row.get('is_station')):
                feature["properties"]["is_station"] = bool(row['is_station'])

            # Добавляем другие атрибуты
            for col in data.columns:
                if col not in ['x', 'y', 'z', 'name', 'belt', 'is_station']:
                    value = row[col]
                    if pd.notna(value):
                        # Преобразуем numpy типы в Python типы
                        if hasattr(value, 'item'):
                            value = value.item()
                        feature["properties"][col] = value

            geojson["features"].append(feature)

        # Добавляем метаданные, если нужно
        if include_metadata:
            geojson["metadata"] = {
                "exported_by": "GeoVertical Analyzer",
                "point_count": len(data),
                "epsg_code": epsg_code
            }

        # Сохраняем в файл
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(geojson, f, ensure_ascii=False, indent=2)

        logger.info(f"Данные экспортированы в GeoJSON: {file_path} ({len(data)} точек)")

    except (OSError, ValueError, KeyError) as e:
        raise ExportError(f"Ошибка экспорта в GeoJSON: {e!s}") from e

