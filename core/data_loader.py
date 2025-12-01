"""
Модуль загрузки геоданных из различных форматов
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Optional, Tuple
import json
import logging

from core.exceptions import (
    DataLoadError,
    FileFormatError,
    DataValidationError,
    TrimbleError,
    TrimbleParsingError,
    FieldGeniusError,
    FieldGeniusParsingError,
)

logger = logging.getLogger(__name__)

try:
    from core.trimble_loader import load_trimble_data
    TRIMBLE_AVAILABLE = True
except ImportError:
    TRIMBLE_AVAILABLE = False

try:
    from core.fieldgenius_loader import (
        FieldGeniusRAWLoader,
        FieldGeniusINILoader,
        FieldGeniusDBFLoader,
        FieldGeniusProjectLoader
    )
    FIELDGENIUS_AVAILABLE = True
except ImportError:
    FIELDGENIUS_AVAILABLE = False


class DataLoader:
    """Базовый класс для загрузки данных"""
    
    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        self.epsg_code = None
        self.data = None
        
    def load(self) -> pd.DataFrame:
        """Загружает данные из файла"""
        raise NotImplementedError
        
    def detect_format(self) -> str:
        """Определяет формат файла"""
        return self.file_path.suffix.lower()


class CSVLoader(DataLoader):
    """Загрузчик CSV файлов"""
    
    def load(self) -> pd.DataFrame:
        """
        Загружает данные из CSV
        
        Ожидаемые колонки: x, y, z (или X, Y, Z, или Height)
        """
        try:
            df = None
            # Пробуем разные разделители
            for sep in [',', ';', '\t']:
                try:
                    candidate = pd.read_csv(self.file_path, sep=sep)
                except (IOError, OSError, pd.errors.EmptyDataError, pd.errors.ParserError) as e:
                    logger.debug(f"Не удалось прочитать CSV с разделителем '{sep}': {e}")
                    continue

                if candidate.empty and len(candidate.columns) == 0:
                    continue

                if len(candidate.columns) >= 3:
                    df = candidate
                    break

            if df is None:
                raise FileFormatError("Не удалось прочитать CSV: неизвестный формат или неверный разделитель")
            
            # Нормализуем названия колонок
            df.columns = df.columns.str.lower().str.strip()
            
            # Ищем колонки с координатами
            x_col = self._find_column(df, ['x', 'lon', 'longitude', 'east', 'easting'])
            y_col = self._find_column(df, ['y', 'lat', 'latitude', 'north', 'northing'])
            z_col = self._find_column(df, ['z', 'h', 'height', 'elevation', 'alt', 'altitude'])
            
            if not all([x_col, y_col, z_col]):
                # Если не нашли названия, используем первые три колонки
                if len(df.columns) >= 3:
                    x_col, y_col, z_col = df.columns[:3]
                else:
                    raise DataValidationError("Не удалось определить колонки координат")
            
            # Ищем колонку с названиями точек
            name_col = self._find_column(df, ['name', 'point_name', 'id', 'point_id', 'label', 'code'])
            
            # Создаем стандартизированный DataFrame
            result = pd.DataFrame({
                'x': pd.to_numeric(df[x_col], errors='coerce'),
                'y': pd.to_numeric(df[y_col], errors='coerce'),
                'z': pd.to_numeric(df[z_col], errors='coerce')
            })
            
            # Добавляем названия точек
            if name_col:
                result['name'] = df[name_col].astype(str)
            else:
                # Генерируем автоматически
                result['name'] = [f'Точка {i+1}' for i in range(len(result))]
            
            # Удаляем строки с NaN
            result = result.dropna()
            
            # Пробуем извлечь EPSG из метаданных (если есть)
            self._try_extract_epsg(df)
            
            self.data = result
            return result
            
        except (FileFormatError, DataValidationError) as e:
            raise
        except (IOError, OSError, pd.errors.EmptyDataError, pd.errors.ParserError, ValueError) as e:
            raise DataLoadError(f"Ошибка загрузки CSV: {str(e)}") from e
    
    def _find_column(self, df: pd.DataFrame, names: list) -> Optional[str]:
        """Ищет колонку по списку возможных названий"""
        for name in names:
            for col in df.columns:
                if name in col.lower():
                    return col
        return None
    
    def _try_extract_epsg(self, df: pd.DataFrame):
        """Пытается извлечь EPSG код из метаданных"""
        for col in df.columns:
            if 'epsg' in col.lower() and not df[col].empty:
                try:
                    self.epsg_code = int(df[col].iloc[0])
                    break
                except (ValueError, IndexError, KeyError) as e:
                    logger.debug(f"Не удалось извлечь EPSG из колонки {col}: {e}")
                    pass


class GeoJSONLoader(DataLoader):
    """Загрузчик GeoJSON файлов"""
    
    def load(self) -> pd.DataFrame:
        """Загружает данные из GeoJSON"""
        try:
            import geopandas as gpd
            
            # Загружаем GeoJSON
            gdf = gpd.read_file(self.file_path)
            
            # Извлекаем EPSG
            if gdf.crs:
                self.epsg_code = gdf.crs.to_epsg()
            
            # Извлекаем координаты
            points = []
            for idx, row in gdf.iterrows():
                geom = row.geometry
                if geom.geom_type == 'Point':
                    x, y = geom.x, geom.y
                    z = geom.z if geom.has_z else 0.0
                    
                    # Пробуем найти высоту в атрибутах
                    if z == 0.0:
                        for attr in ['z', 'Z', 'height', 'Height', 'elevation', 'Elevation']:
                            if attr in row and pd.notna(row[attr]):
                                z = float(row[attr])
                                break
                    
                    # Извлекаем название точки
                    name = None
                    for attr in ['name', 'Name', 'NAME', 'point_name', 'id', 'ID', 'label', 'code']:
                        if attr in row and pd.notna(row[attr]):
                            name = str(row[attr])
                            break
                    
                    if not name:
                        name = f'Точка {len(points)+1}'
                    
                    points.append({'x': x, 'y': y, 'z': z, 'name': name})
            
            result = pd.DataFrame(points)
            self.data = result
            return result
            
        except ImportError as e:
            raise DataLoadError("Для работы с GeoJSON требуется установить geopandas") from e
        except (IOError, OSError, ValueError, KeyError, AttributeError) as e:
            raise DataLoadError(f"Ошибка загрузки GeoJSON: {str(e)}") from e


class ShapefileLoader(DataLoader):
    """Загрузчик Shapefile"""
    
    def load(self) -> pd.DataFrame:
        """Загружает данные из Shapefile"""
        try:
            import geopandas as gpd
            
            # Загружаем Shapefile
            gdf = gpd.read_file(self.file_path)
            
            # Извлекаем EPSG
            if gdf.crs:
                self.epsg_code = gdf.crs.to_epsg()
            
            # Извлекаем координаты
            points = []
            for idx, row in gdf.iterrows():
                geom = row.geometry
                if geom.geom_type == 'Point':
                    x, y = geom.x, geom.y
                    z = geom.z if geom.has_z else 0.0
                    
                    # Пробуем найти высоту в атрибутах
                    if z == 0.0:
                        for attr in ['z', 'Z', 'height', 'Height', 'elevation', 'Elevation', 'ELEV']:
                            if attr in row and pd.notna(row[attr]):
                                z = float(row[attr])
                                break
                    
                    # Извлекаем название точки
                    name = None
                    for attr in ['name', 'Name', 'NAME', 'point_name', 'id', 'ID', 'label', 'code']:
                        if attr in row and pd.notna(row[attr]):
                            name = str(row[attr])
                            break
                    
                    if not name:
                        name = f'Точка {len(points)+1}'
                    
                    points.append({'x': x, 'y': y, 'z': z, 'name': name})
            
            result = pd.DataFrame(points)
            self.data = result
            return result
            
        except ImportError as e:
            raise DataLoadError("Для работы с Shapefile требуется установить geopandas") from e
        except (IOError, OSError, ValueError, KeyError, AttributeError) as e:
            raise DataLoadError(f"Ошибка загрузки Shapefile: {str(e)}") from e


class DXFLoader(DataLoader):
    """Загрузчик DXF файлов"""
    
    def load(self) -> pd.DataFrame:
        """Загружает данные из DXF"""
        try:
            import ezdxf
            
            # Загружаем DXF
            doc = ezdxf.readfile(self.file_path)
            msp = doc.modelspace()
            
            # Извлекаем точки
            points = []
            for entity in msp:
                if entity.dxftype() == 'POINT':
                    x, y, z = entity.dxf.location
                    # Пробуем извлечь название из атрибутов
                    name = None
                    if hasattr(entity.dxf, 'layer'):
                        name = entity.dxf.layer
                    if not name:
                        name = f'Точка {len(points)+1}'
                    points.append({'x': x, 'y': y, 'z': z, 'name': name})
                elif entity.dxftype() == 'INSERT' and hasattr(entity.dxf, 'insert'):
                    # Блоки с вставками
                    x, y, z = entity.dxf.insert
                    # Используем имя блока как название точки
                    name = entity.dxf.name if hasattr(entity.dxf, 'name') else f'Точка {len(points)+1}'
                    points.append({'x': x, 'y': y, 'z': z, 'name': name})
            
            if not points:
                raise DataValidationError("В DXF не найдено точек")
            
            result = pd.DataFrame(points)
            self.data = result
            return result
            
        except ImportError as e:
            raise DataLoadError("Для работы с DXF требуется установить ezdxf") from e
        except (IOError, OSError, ValueError, AttributeError) as e:
            raise DataLoadError(f"Ошибка загрузки DXF: {str(e)}") from e
        except Exception as e:
            # Обработка специфичных ошибок ezdxf
            import ezdxf
            if isinstance(e, (ezdxf.DXFStructureError, ezdxf.DXFValueError)):
                error_msg = f"Ошибка структуры DXF файла: {str(e)}"
                logger.error(error_msg, exc_info=True)
                raise DataLoadError(error_msg) from e
            error_msg = f"Неожиданная ошибка загрузки DXF: {type(e).__name__}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            raise DataLoadError(error_msg) from e


def load_data_from_file(file_path: str) -> Tuple[pd.DataFrame, Optional[int]]:
    """
    Автоматически определяет формат и загружает данные
    
    Args:
        file_path: Путь к файлу
        
    Returns:
        Кортеж (DataFrame с данными, EPSG код или None)
    """
    path = Path(file_path)
    extension = path.suffix.lower()
    
    loader_map = {
        '.csv': CSVLoader,
        '.txt': CSVLoader,
        '.geojson': GeoJSONLoader,
        '.json': GeoJSONLoader,
        '.shp': ShapefileLoader,
        '.dxf': DXFLoader
    }
    
    # Добавляем поддержку Trimble форматов
    trimble_extensions = ['.job', '.jxl', '.jobxml', '.xml']
    if extension in trimble_extensions and TRIMBLE_AVAILABLE:
        try:
            data = load_trimble_data(file_path)
            return data, None  # EPSG определяется отдельно для Trimble
        except NotImplementedError as e:
            # Для .job файлов выводим сообщение с инструкцией
            raise
        except (TrimbleError, TrimbleParsingError, IOError, OSError) as e:
            # Если не удалось загрузить как Trimble, пробуем другие загрузчики
            if extension == '.txt':
                pass  # Попробуем стандартный CSVLoader
            else:
                raise TrimbleError(f"Ошибка загрузки Trimble файла: {str(e)}") from e
    
    # Добавляем поддержку FieldGenius форматов
    if FIELDGENIUS_AVAILABLE:
        # Проверяем, является ли путь папкой проекта FieldGenius
        if path.is_dir():
            try:
                # Проверяем наличие INI файла в папке
                ini_files = list(path.glob('*.ini'))
                if ini_files:
                    # Это папка проекта FieldGenius
                    loader = FieldGeniusProjectLoader(file_path)
                    data = loader.load()
                    return data, loader.epsg_code
            except (FieldGeniusError, FieldGeniusParsingError, IOError, OSError) as e:
                logger.debug(f"Не удалось загрузить как проект FieldGenius: {e}")
                # Продолжаем с другими загрузчиками
        
        # Обработка .ini файлов (проекты FieldGenius)
        if extension == '.ini':
            try:
                loader = FieldGeniusProjectLoader(file_path)
                data = loader.load()
                return data, loader.epsg_code
            except (FieldGeniusError, FieldGeniusParsingError, IOError, OSError) as e:
                raise FieldGeniusError(f"Ошибка загрузки проекта FieldGenius из INI: {str(e)}") from e
        
        # Обработка .dbf файлов (базы данных FieldGenius)
        if extension == '.dbf':
            try:
                loader = FieldGeniusDBFLoader(file_path)
                data = loader.load()
                return data, loader.epsg_code
            except (FieldGeniusError, FieldGeniusParsingError, IOError, OSError) as e:
                raise FieldGeniusError(f"Ошибка загрузки FieldGenius DBF файла: {str(e)}") from e
        
        # Обработка .raw файлов (RAW данные FieldGenius)
        if extension == '.raw':
            try:
                loader = FieldGeniusRAWLoader(file_path)
                # Проверяем, что это действительно FieldGenius файл
                if loader._is_fieldgenius_file():
                    data = loader.load()
                    return data, loader.epsg_code
                else:
                    # Если не FieldGenius, пробуем другие загрузчики или выдаем ошибку
                    raise FileFormatError("Файл .raw не является FieldGenius форматом")
            except (FieldGeniusError, FieldGeniusParsingError, IOError, OSError) as e:
                raise FieldGeniusError(f"Ошибка загрузки FieldGenius RAW файла: {str(e)}") from e
    
    loader_class = loader_map.get(extension)
    if not loader_class:
        raise FileFormatError(f"Неподдерживаемый формат файла: {extension}")
    
    loader = loader_class(file_path)
    data = loader.load()
    
    return data, loader.epsg_code


def validate_data(data: pd.DataFrame, check_outliers: bool = True) -> Tuple[bool, str]:
    """
    Валидирует загруженные данные с расширенной проверкой
    
    Args:
        data: DataFrame с данными
        check_outliers: Проверять ли выбросы
        
    Returns:
        Кортеж (валидность, сообщение об ошибке)
    """
    if data.empty:
        return False, "Данные пусты"
    
    required_cols = ['x', 'y', 'z', 'name']
    if not all(col in data.columns for col in required_cols):
        return False, f"Отсутствуют необходимые колонки ({', '.join(required_cols)})"
    
    # Проверяем только числовые колонки на NaN
    if data[['x', 'y', 'z']].isnull().any().any():
        return False, "Данные содержат пропущенные значения координат"
    
    if len(data) < 3:
        return False, "Недостаточно точек для анализа (минимум 3)"
    
    # Проверка на разумные значения координат
    if (data['z'] < 0).any():
        return False, "Обнаружены отрицательные высоты"
    
    # Проверка на бесконечные значения
    if np.isinf(data[['x', 'y', 'z']]).any().any():
        return False, "Обнаружены бесконечные значения координат"
    
    # Проверка на очень большие значения (возможные ошибки)
    max_reasonable = 1e6  # 1000 км
    if (data[['x', 'y']].abs() > max_reasonable).any().any():
        return False, f"Обнаружены координаты, превышающие разумные значения ({max_reasonable} м)"
    
    max_height = 1e4  # 10 км
    if (data['z'] > max_height).any():
        return False, f"Обнаружены высоты, превышающие разумные значения ({max_height} м)"
    
    # Проверка на выбросы (опционально)
    if check_outliers and len(data) > 3:
        outliers = _detect_outliers(data)
        if len(outliers) > len(data) * 0.5:  # Если больше 50% точек - выбросы
            return False, f"Обнаружено слишком много выбросов ({len(outliers)} из {len(data)} точек). Проверьте данные."
    
    return True, "Данные валидны"


def _detect_outliers(data: pd.DataFrame, threshold: float = 3.0) -> pd.Index:
    """
    Обнаруживает выбросы в данных используя метод Z-score
    
    Args:
        data: DataFrame с данными
        threshold: Порог Z-score для определения выбросов
        
    Returns:
        Индексы выбросов
    """
    try:
        import numpy as np
        from scipy import stats
        
        # Вычисляем Z-score для координат
        z_scores = np.abs(stats.zscore(data[['x', 'y', 'z']], nan_policy='omit'))
        
        # Точка считается выбросом, если хотя бы одна координата превышает порог
        outliers_mask = (z_scores > threshold).any(axis=1)
        outliers = data.index[outliers_mask]
        
        return outliers
    except Exception as e:
        logger.debug(f"Не удалось обнаружить выбросы: {e}")
        return pd.Index([])

