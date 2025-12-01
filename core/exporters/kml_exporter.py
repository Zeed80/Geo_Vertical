"""
Экспорт данных GeoVertical в формат KML для Google Earth
"""

import logging
from typing import Optional, Dict, Any
import pandas as pd
from pathlib import Path
from datetime import datetime
import xml.etree.ElementTree as ET

from core.exceptions import ExportError, DataValidationError

logger = logging.getLogger(__name__)


def export_data_to_kml(
    data: pd.DataFrame,
    file_path: str,
    name: str = "GeoVertical Points",
    description: Optional[str] = None,
    epsg_code: Optional[int] = None
) -> None:
    """
    Экспортирует данные точек в формат KML для Google Earth
    
    Args:
        data: DataFrame с колонками ['x', 'y', 'z', 'name'] и опционально ['belt', 'is_station']
        file_path: Путь для сохранения KML файла
        name: Название слоя в KML
        description: Описание слоя
        epsg_code: EPSG код системы координат (опционально, для информации)
        
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
        # Создаем корневой элемент KML
        kml = ET.Element("kml", xmlns="http://www.opengis.net/kml/2.2")
        document = ET.SubElement(kml, "Document")
        
        # Название и описание документа
        name_elem = ET.SubElement(document, "name")
        name_elem.text = name
        
        if description:
            desc_elem = ET.SubElement(document, "description")
            desc_elem.text = description
        
        # Создаем папки для разных типов точек
        tower_folder = ET.SubElement(document, "Folder")
        tower_name = ET.SubElement(tower_folder, "name")
        tower_name.text = "Точки башни"
        
        station_folder = ET.SubElement(document, "Folder")
        station_name = ET.SubElement(station_folder, "name")
        station_name.text = "Точки стояния"
        
        # Группируем точки по поясам, если есть информация о поясах
        belt_folders: Dict[int, ET.Element] = {}
        if 'belt' in data.columns:
            for belt_num in data['belt'].dropna().unique():
                belt_folder = ET.SubElement(document, "Folder")
                belt_name_elem = ET.SubElement(belt_folder, "name")
                belt_name_elem.text = f"Пояс {int(belt_num)}"
                belt_folders[int(belt_num)] = belt_folder
        
        # Добавляем точки
        for idx, row in data.iterrows():
            # Определяем, в какую папку добавить точку
            if 'is_station' in data.columns and pd.notna(row.get('is_station')) and bool(row['is_station']):
                parent_folder = station_folder
            elif 'belt' in data.columns and pd.notna(row.get('belt')):
                belt_num = int(row['belt'])
                if belt_num in belt_folders:
                    parent_folder = belt_folders[belt_num]
                else:
                    parent_folder = tower_folder
            else:
                parent_folder = tower_folder
            
            # Создаем Placemark для точки
            placemark = ET.SubElement(parent_folder, "Placemark")
            
            # Название точки
            pm_name = ET.SubElement(placemark, "name")
            pm_name.text = str(row['name'])
            
            # Описание точки
            description_parts = []
            if 'belt' in data.columns and pd.notna(row.get('belt')):
                description_parts.append(f"Пояс: {int(row['belt'])}")
            description_parts.append(f"Высота: {float(row['z']):.3f} м")
            if epsg_code:
                description_parts.append(f"EPSG: {epsg_code}")
            
            # Добавляем другие атрибуты
            for col in data.columns:
                if col not in ['x', 'y', 'z', 'name', 'belt', 'is_station']:
                    value = row[col]
                    if pd.notna(value):
                        if hasattr(value, 'item'):
                            value = value.item()
                        description_parts.append(f"{col}: {value}")
            
            if description_parts:
                pm_desc = ET.SubElement(placemark, "description")
                pm_desc.text = "<br/>".join(description_parts)
            
            # Координаты точки (KML использует порядок: долгота, широта, высота)
            # В GeoVertical: x, y, z (обычно это восточное смещение, северное смещение, высота)
            # Для KML нужно преобразовать в долготу/широту, если это не географические координаты
            # Пока используем как есть, предполагая что координаты уже в правильной системе
            point = ET.SubElement(placemark, "Point")
            coordinates = ET.SubElement(point, "coordinates")
            # KML формат: longitude,latitude,altitude
            coordinates.text = f"{float(row['x'])},{float(row['y'])},{float(row['z'])}"
            
            # Стиль для точки стояния
            if 'is_station' in data.columns and pd.notna(row.get('is_station')) and bool(row['is_station']):
                style = ET.SubElement(placemark, "Style")
                icon_style = ET.SubElement(style, "IconStyle")
                color = ET.SubElement(icon_style, "color")
                color.text = "ff0000ff"  # Красный цвет
                scale = ET.SubElement(icon_style, "scale")
                scale.text = "1.5"
        
        # Создаем XML дерево и сохраняем
        tree = ET.ElementTree(kml)
        ET.indent(tree, space="  ")
        
        # Добавляем XML декларацию
        with open(file_path, 'wb') as f:
            f.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
            tree.write(f, encoding='utf-8', xml_declaration=False)
        
        logger.info(f"Данные экспортированы в KML: {file_path} ({len(data)} точек)")
        
    except (IOError, OSError, ValueError, KeyError, ET.ParseError) as e:
        raise ExportError(f"Ошибка экспорта в KML: {str(e)}") from e

