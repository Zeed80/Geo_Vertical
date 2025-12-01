"""
Загрузчик данных из различных форматов Trimble
Поддерживает: JobXML, CSV экспорт, текстовые координатные файлы, бинарные JOB файлы
"""

import pandas as pd
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional, Dict, List
import re
import struct
import logging

logger = logging.getLogger(__name__)


class TrimbleJobXMLLoader:
    """
    Загрузчик для Trimble JobXML формата
    
    JobXML - это текстовый XML формат, который Trimble использует для экспорта данных.
    Можно получить через: Trimble Business Center → Export → JobXML
    """
    
    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        self.points = []
        self.metadata = {}
    
    def load(self) -> pd.DataFrame:
        """Загружает данные из JobXML файла"""
        try:
            tree = ET.parse(self.file_path)
            root = tree.getroot()
            
            # Ищем точки в XML
            # Типичная структура JobXML:
            # <JOBFile>
            #   <FieldBook>
            #     <PointRecord>
            #       <Name>PT1</Name>
            #       <Grid>
            #         <North>...</North>
            #         <East>...</East>
            #         <Elevation>...</Elevation>
            #       </Grid>
            #     </PointRecord>
            #   </FieldBook>
            # </JOBFile>
            
            # Вариант 1: PointRecord с Grid координатами
            for point in root.findall('.//PointRecord'):
                try:
                    name = point.find('.//Name')
                    grid = point.find('.//Grid')
                    
                    if grid is not None:
                        north = grid.find('North')
                        east = grid.find('East')
                        elev = grid.find('Elevation')
                        
                        if north is not None and east is not None and north.text and east.text:
                            self.points.append({
                                'point_id': name.text if name is not None else f'PT_{len(self.points)+1}',
                                'x': float(east.text),
                                'y': float(north.text),
                                'z': float(elev.text) if (elev is not None and elev.text) else 0.0
                            })
                except Exception as e:
                    logger.debug(f"Error parsing PointRecord: {e}")
                    continue
            
            # Вариант 2: Point с Grid координатами (используется в Reductions)
            if not self.points:
                for point in root.findall('.//Point'):
                    try:
                        name = point.find('Name')
                        grid = point.find('Grid')
                        
                        if grid is not None:
                            north = grid.find('North')
                            east = grid.find('East')
                            elev = grid.find('Elevation')
                            
                            # Проверяем, что координаты не пустые
                            if (north is not None and east is not None and 
                                north.text and east.text and 
                                north.text.strip() and east.text.strip()):
                                self.points.append({
                                    'point_id': name.text if (name is not None and name.text) else f'PT_{len(self.points)+1}',
                                    'x': float(east.text),
                                    'y': float(north.text),
                                    'z': float(elev.text) if (elev is not None and elev.text and elev.text.strip()) else 0.0
                                })
                    except Exception as e:
                        logger.debug(f"Error parsing Point with Grid: {e}")
                        continue
            
            # Вариант 3: Point с WGS84 координатами
            if not self.points:
                for point in root.findall('.//Point'):
                    try:
                        name = point.find('Name')
                        wgs84 = point.find('WGS84')
                        
                        if wgs84 is not None:
                            lat = wgs84.find('Latitude')
                            lon = wgs84.find('Longitude')
                            height = wgs84.find('Height')
                            
                            if lat is not None and lon is not None:
                                # Примечание: для WGS84 может потребоваться трансформация координат
                                self.points.append({
                                    'point_id': name.text if (name is not None and name.text) else f'PT_{len(self.points)+1}',
                                    'x': float(lon.text),
                                    'y': float(lat.text),
                                    'z': float(height.text) if (height is not None and height.text) else 0.0
                                })
                    except Exception as e:
                        logger.debug(f"Error parsing Point with WGS84: {e}")
                        continue
            
            if not self.points:
                raise ValueError("В JobXML файле не найдено точек с координатами")
            
            logger.info(f"Загружено {len(self.points)} точек из JobXML")
            
            return self._to_dataframe()
            
        except ET.ParseError as e:
            raise ValueError(f"Ошибка парсинга JobXML: {str(e)}")
        except Exception as e:
            raise ValueError(f"Ошибка чтения JobXML: {str(e)}")
    
    def _to_dataframe(self) -> pd.DataFrame:
        """Конвертирует точки в DataFrame"""
        df = pd.DataFrame(self.points)
        result = df[['x', 'y', 'z']].copy()
        result['name'] = df['point_id']
        return result


class TrimbleCSVLoader:
    """
    Загрузчик для CSV файлов, экспортированных из Trimble
    
    Trimble может экспортировать данные в CSV через:
    - Trimble Business Center → Export → CSV
    - Trimble Access → Export → Text File
    """
    
    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
    
    def load(self) -> pd.DataFrame:
        """Загружает CSV файл от Trimble"""
        try:
            # Пробуем различные варианты структуры CSV от Trimble
            
            # Вариант 1: Стандартный CSV с заголовками
            try:
                df = pd.read_csv(self.file_path)
                return self._parse_trimble_csv(df)
            except:
                pass
            
            # Вариант 2: CSV без заголовков
            try:
                df = pd.read_csv(self.file_path, header=None)
                return self._parse_trimble_csv_no_header(df)
            except:
                pass
            
            # Вариант 3: Текстовый файл с пробелами
            try:
                df = pd.read_csv(self.file_path, delim_whitespace=True)
                return self._parse_trimble_csv(df)
            except:
                pass
            
            raise ValueError("Не удалось распознать формат Trimble CSV")
            
        except Exception as e:
            raise ValueError(f"Ошибка чтения Trimble CSV: {str(e)}")
    
    def _parse_trimble_csv(self, df: pd.DataFrame) -> pd.DataFrame:
        """Парсит CSV с заголовками"""
        # Типичные названия колонок в Trimble CSV:
        # Point Name, Northing, Easting, Elevation
        # или Point ID, North, East, Elev
        # или Name, Y, X, Z
        
        col_map = {}
        
        # Ищем колонки для X (Easting)
        for col in df.columns:
            col_lower = col.lower()
            if any(name in col_lower for name in ['east', 'x', 'longitude', 'lon']):
                col_map['x'] = col
            elif any(name in col_lower for name in ['north', 'y', 'latitude', 'lat']):
                col_map['y'] = col
            elif any(name in col_lower for name in ['elev', 'z', 'height', 'altitude']):
                col_map['z'] = col
            elif any(name in col_lower for name in ['point', 'name', 'id']):
                col_map['id'] = col
        
        if 'x' not in col_map or 'y' not in col_map:
            raise ValueError("Не найдены колонки с координатами X, Y")
        
        result = pd.DataFrame()
        result['x'] = pd.to_numeric(df[col_map['x']], errors='coerce')
        result['y'] = pd.to_numeric(df[col_map['y']], errors='coerce')
        result['z'] = pd.to_numeric(df[col_map.get('z', col_map['x'])], errors='coerce') if 'z' in col_map else 0.0
        
        # Добавляем названия точек
        if 'id' in col_map:
            result['name'] = df[col_map['id']].astype(str)
        else:
            result['name'] = [f'Точка {i+1}' for i in range(len(result))]
        
        # Удаляем строки с NaN
        result = result.dropna(subset=['x', 'y'])
        
        logger.info(f"Загружено {len(result)} точек из Trimble CSV")
        
        return result
    
    def _parse_trimble_csv_no_header(self, df: pd.DataFrame) -> pd.DataFrame:
        """Парсит CSV без заголовков (предполагаем порядок: ID, Y, X, Z или X, Y, Z)"""
        n_cols = len(df.columns)
        
        if n_cols >= 3:
            # Пробуем определить, есть ли колонка с ID
            first_col = df.iloc[:, 0]
            
            # Если первая колонка - текст, то это ID
            if first_col.dtype == object:
                result = pd.DataFrame()
                result['x'] = pd.to_numeric(df.iloc[:, 2], errors='coerce')
                result['y'] = pd.to_numeric(df.iloc[:, 1], errors='coerce')
                result['z'] = pd.to_numeric(df.iloc[:, 3], errors='coerce') if n_cols >= 4 else 0.0
                result['name'] = df.iloc[:, 0].astype(str)
            else:
                # Нет ID, только координаты
                result = pd.DataFrame()
                result['x'] = pd.to_numeric(df.iloc[:, 0], errors='coerce')
                result['y'] = pd.to_numeric(df.iloc[:, 1], errors='coerce')
                result['z'] = pd.to_numeric(df.iloc[:, 2], errors='coerce') if n_cols >= 3 else 0.0
                result['name'] = [f'Точка {i+1}' for i in range(len(result))]
            
            result = result.dropna(subset=['x', 'y'])
            
            logger.info(f"Загружено {len(result)} точек из Trimble CSV (без заголовков)")
            
            return result
        else:
            raise ValueError("Недостаточно колонок в CSV файле")


class TrimbleTextLoader:
    """
    Загрузчик для текстовых координатных файлов от Trimble
    Поддерживает различные текстовые форматы экспорта
    """
    
    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
    
    def load(self) -> pd.DataFrame:
        """Загружает текстовый файл с координатами"""
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            points = []
            
            for line in lines:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                # Пробуем различные паттерны
                # Паттерн 1: ID N E Z
                match = re.match(r'(\S+)\s+([\d.-]+)\s+([\d.-]+)\s+([\d.-]+)', line)
                if match:
                    points.append({
                        'point_id': match.group(1),
                        'x': float(match.group(3)),  # East
                        'y': float(match.group(2)),  # North
                        'z': float(match.group(4))
                    })
                    continue
                
                # Паттерн 2: N E Z (без ID)
                match = re.match(r'([\d.-]+)\s+([\d.-]+)\s+([\d.-]+)', line)
                if match:
                    points.append({
                        'point_id': f'PT_{len(points)+1}',
                        'x': float(match.group(2)),
                        'y': float(match.group(1)),
                        'z': float(match.group(3))
                    })
                    continue
            
            if not points:
                raise ValueError("Не удалось распознать координаты в текстовом файле")
            
            df = pd.DataFrame(points)
            result = df[['x', 'y', 'z']].copy()
            result['name'] = df['point_id']
            
            logger.info(f"Загружено {len(result)} точек из текстового файла")
            
            return result
            
        except Exception as e:
            raise ValueError(f"Ошибка чтения текстового файла: {str(e)}")


class TrimbleJobBinaryLoader:
    """
    Загрузчик для бинарных JOB файлов
    
    ВАЖНО: Формат JOB является проприетарным и недокументированным!
    Этот загрузчик использует эвристический подход для извлечения координат.
    
    Для лучшего результата рекомендуется:
    1. Откройте файл в Trimble Business Center
    2. Экспортируйте в формат JobXML: File → Export → JobXML
    3. Загрузите полученный JobXML файл в эту программу
    """
    
    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        self.points = []
    
    def load(self) -> pd.DataFrame:
        """Пытается загрузить бинарный JOB файл"""
        try:
            with open(self.file_path, 'rb') as f:
                data = f.read()
            
            # Проверяем заголовок
            header = data[:40].decode('ascii', errors='ignore')
            if 'Trimble' not in header:
                raise ValueError("Файл не является Trimble JOB файлом")
            
            logger.info(f"Загрузка бинарного JOB файла: {self.file_path.name}")
            
            # Метод 1: Поиск триплетов координат (X, Y, Z как double)
            for offset in range(0, len(data) - 24, 8):
                try:
                    x = struct.unpack('<d', data[offset:offset+8])[0]
                    y = struct.unpack('<d', data[offset+8:offset+16])[0]
                    z = struct.unpack('<d', data[offset+16:offset+24])[0]
                    
                    # Фильтруем разумные координаты для геодезических съемок
                    # Координаты должны быть в разумном диапазоне для локальной системы
                    if (abs(x) < 1000 and abs(y) < 1000 and abs(z) < 1000 and
                        abs(x) > 0.01 and abs(y) > 0.01 and abs(z) > 0.01):  # Не очень маленькие числа
                        
                        # Проверяем, что это не служебные данные
                        # (не три одинаковых числа)
                        if not (abs(x - y) < 0.001 and abs(y - z) < 0.001):
                            # Дополнительная проверка: хотя бы одна координата должна быть > 1.0
                            if abs(x) > 1.0 or abs(y) > 1.0 or abs(z) > 1.0:
                                self.points.append({
                                    'point_id': f'PT_{len(self.points)+1}',
                                    'x': x,
                                    'y': y,
                                    'z': z,
                                    'offset': offset
                                })
                except:
                    pass
            
            # Метод 2: Поиск по паттерну записей
            pattern = b'\x00\x00\x00\x03\x30\x2a'
            pos = 0
            pattern_points = []
            
            while True:
                pos = data.find(pattern, pos)
                if pos == -1:
                    break
                
                # Ищем координаты после паттерна
                search_start = pos + len(pattern)
                search_end = min(pos + 200, len(data))
                
                for offset in range(search_start, search_end - 24, 4):
                    try:
                        x = struct.unpack('<d', data[offset:offset+8])[0]
                        y = struct.unpack('<d', data[offset+8:offset+16])[0]
                        z = struct.unpack('<d', data[offset+16:offset+24])[0]
                        
                        if (abs(x) < 10000 and abs(y) < 10000 and abs(z) < 10000 and
                            abs(x) + abs(y) + abs(z) > 0.1):
                            pattern_points.append({
                                'point_id': f'PT_{len(self.points) + len(pattern_points)+1}',
                                'x': x,
                                'y': y,
                                'z': z,
                                'offset': offset
                            })
                            break
                    except:
                        pass
                
                pos += 1
            
            # Объединяем результаты
            all_points = self.points + pattern_points
            
            # Удаляем дубликаты (точки с очень близкими координатами)
            unique_points = []
            for p in all_points:
                is_duplicate = False
                for up in unique_points:
                    if (abs(p['x'] - up['x']) < 0.001 and 
                        abs(p['y'] - up['y']) < 0.001 and 
                        abs(p['z'] - up['z']) < 0.001):
                        is_duplicate = True
                        break
                if not is_duplicate:
                    unique_points.append(p)
            
            self.points = unique_points
            
            if not self.points:
                raise ValueError("В JOB файле не найдено координат точек")
            
            logger.info(f"Загружено {len(self.points)} точек из JOB файла (эвристический метод)")
            logger.warning("ВНИМАНИЕ: Данные извлечены эвристическим методом из бинарного файла. "
                          "Для гарантированной точности используйте экспорт в JobXML через Trimble Business Center.")
            
            return self._to_dataframe()
            
        except Exception as e:
            logger.error(f"Ошибка загрузки JOB файла: {e}")
            raise ValueError(
                f"Не удалось загрузить бинарный JOB файл: {str(e)}\n\n"
                "РЕКОМЕНДАЦИЯ:\n"
                "1. Откройте JOB файл в Trimble Business Center\n"
                "2. Экспортируйте в JobXML: File → Export → JobXML\n"
                "3. Загрузите JobXML файл (.jxl) в программу"
            )
    
    def _to_dataframe(self) -> pd.DataFrame:
        """Конвертирует точки в DataFrame"""
        df = pd.DataFrame(self.points)
        result = df[['x', 'y', 'z']].copy()
        result['name'] = df['point_id']
        return result


def load_trimble_data(file_path: str) -> pd.DataFrame:
    """
    Универсальная функция для загрузки данных Trimble
    
    Поддерживаемые форматы:
    - .jxl, .jobxml - JobXML (экспорт из Trimble Business Center)
    - .csv - CSV экспорт
    - .txt - Текстовые координатные файлы
    - .job - Бинарные JOB файлы (требуют предварительного экспорта)
    
    Args:
        file_path: Путь к файлу
        
    Returns:
        DataFrame с колонками x, y, z
        
    Raises:
        NotImplementedError: Для бинарных JOB файлов с инструкцией по экспорту
        ValueError: Для других ошибок загрузки
    """
    path = Path(file_path)
    ext = path.suffix.lower()
    
    if ext in ['.jxl', '.jobxml', '.xml']:
        loader = TrimbleJobXMLLoader(file_path)
    elif ext == '.csv':
        loader = TrimbleCSVLoader(file_path)
    elif ext == '.txt':
        loader = TrimbleTextLoader(file_path)
    elif ext == '.job':
        loader = TrimbleJobBinaryLoader(file_path)
    else:
        raise ValueError(f"Неизвестный формат Trimble файла: {ext}")
    
    return loader.load()

