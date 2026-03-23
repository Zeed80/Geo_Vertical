"""
Загрузчик данных из формата FieldGenius
Поддерживает:
- RAW файлы с вычислением координат из полярных измерений
- INI файлы с метаданными проекта
- DBF файлы с координатами точек
- Комплексная загрузка проектов FieldGenius
"""

import configparser
import logging
import math
import re
from pathlib import Path
from typing import Any

import pandas as pd

from core.exceptions import DataLoadError, DataValidationError, FileFormatError

logger = logging.getLogger(__name__)

# Попытка импорта dbfread
try:
    from dbfread import DBF
    DBF_AVAILABLE = True
except ImportError:
    DBF_AVAILABLE = False
    logger.warning("Библиотека dbfread не установлена. Загрузка DBF файлов будет недоступна.")


class FieldGeniusRAWLoader:
    """
    Загрузчик для FieldGenius RAW формата

    FieldGenius RAW - это текстовый формат, содержащий сырые данные съемки
    с полярными измерениями (азимут, зенитный угол, наклонное расстояние).
    """

    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        self.epsg_code: int | None = None
        self.points: list[dict] = []
        self.stations: dict[str, dict] = {}  # Словарь станций: {OP1: {x, y, z, hi}}
        self.coordinate_system: str | None = None

    def load(self) -> pd.DataFrame:
        """
        Загружает данные из RAW файла

        Returns:
            DataFrame с колонками: x, y, z, name

        Raises:
            DataLoadError: При ошибке загрузки
            FileFormatError: Если файл не является FieldGenius RAW
        """
        try:
            # Проверяем, что это FieldGenius RAW файл
            if not self._is_fieldgenius_file():
                raise FileFormatError("Файл не является FieldGenius RAW форматом")

            # Парсим RAW файл
            self._parse_raw_file()

            # Вычисляем координаты точек
            self._calculate_all_points()

            # Нормализуем координаты станции: устанавливаем X=0, Y=0 и применяем обратное смещение к точкам
            self._normalize_station_coordinates()

            # Добавляем точки станций в результат
            self._add_stations_to_points()

            if not self.points:
                raise DataValidationError("Не найдено точек для загрузки")

            # Создаем DataFrame
            result = pd.DataFrame(self.points)

            # Переименовываем колонки для стандартизации
            if 'point_name' in result.columns:
                result['name'] = result['point_name']
            elif 'name' not in result.columns:
                result['name'] = [f'Точка {i+1}' for i in range(len(result))]

            # Убеждаемся, что есть колонки x, y, z
            required_cols = ['x', 'y', 'z']
            for col in required_cols:
                if col not in result.columns:
                    raise DataValidationError(f"Отсутствует колонка {col} в результате")

            # Удаляем строки с NaN
            result = result.dropna(subset=['x', 'y', 'z'])

            # Нормализуем высоты: если есть отрицательные, сдвигаем все точки вверх
            # ВАЖНО: станция всегда в (0, 0, 0), смещение применяется только к точкам башни
            z_offset = 0.0
            if 'is_station' in result.columns:
                tower_points_mask = ~result['is_station'].fillna(False).astype(bool)

                if tower_points_mask.any():
                    # Находим минимальную Z среди точек башни (исключая станцию)
                    tower_z_values = result.loc[tower_points_mask, 'z']
                    min_z = tower_z_values.min() if len(tower_z_values) > 0 else 0.0

                    if min_z < 0:
                        z_offset = abs(min_z) + 0.1  # Добавляем небольшой запас

                        # Применяем смещение только к точкам башни
                        result.loc[tower_points_mask, 'z'] = result.loc[tower_points_mask, 'z'] + z_offset

                        logger.info(f"Высоты нормализованы: добавлено смещение {z_offset:.3f}м для устранения отрицательных значений "
                                  f"(применено только к точкам башни, станция остается в (0, 0, 0))")

                # Убеждаемся, что станция всегда в (0, 0, 0)
                station_mask = result['is_station'].fillna(False).astype(bool)
                if station_mask.any():
                    result.loc[station_mask, 'x'] = 0.0
                    result.loc[station_mask, 'y'] = 0.0
                    result.loc[station_mask, 'z'] = 0.0

            logger.info(f"Загружено {len(result)} точек из FieldGenius RAW файла (включая {len(self.stations)} станций)")

            # Валидация результата: проверяем, что станция в (0, 0, 0)
            if 'is_station' in result.columns:
                station_mask = result['is_station'].fillna(False).astype(bool)
                if station_mask.any():
                    station_rows = result[station_mask]
                    for idx, station_row in station_rows.iterrows():
                        station_x = float(station_row['x'])
                        station_y = float(station_row['y'])
                        station_z = float(station_row['z'])
                        station_name = str(station_row.get('name', 'Unknown'))

                        # Проверяем, что X=0, Y=0 и Z=0
                        if abs(station_x) > 1e-3 or abs(station_y) > 1e-3 or abs(station_z) > 1e-3:
                            logger.error(f"Валидация не прошла: станция {station_name} имеет координаты ({station_x:.6f}, {station_y:.6f}, {station_z:.6f}) "
                                       f"вместо (0, 0, 0)")
                            # Исправляем координаты
                            result.at[idx, 'x'] = 0.0
                            result.at[idx, 'y'] = 0.0
                            result.at[idx, 'z'] = 0.0
                            logger.warning(f"Координаты станции {station_name} исправлены на (0, 0, 0)")
                        else:
                            logger.debug(f"Валидация пройдена: станция {station_name} в (0, 0, 0)")

            # Возвращаем все колонки, включая is_station если есть
            return_cols = ['x', 'y', 'z', 'name']
            if 'is_station' in result.columns:
                return_cols.append('is_station')

            return result[return_cols]

        except (FileFormatError, DataValidationError):
            raise
        except Exception as e:
            raise DataLoadError(f"Ошибка загрузки FieldGenius RAW: {e!s}") from e

    def _is_fieldgenius_file(self) -> bool:
        """Проверяет, является ли файл FieldGenius RAW форматом"""
        try:
            with open(self.file_path, encoding='utf-8', errors='ignore') as f:
                first_line = f.readline().strip()
                return first_line.startswith('--FieldGenius')
        except Exception:
            return False

    def _parse_raw_file(self):
        """Парсит RAW файл построчно"""
        try:
            with open(self.file_path, encoding='utf-8', errors='ignore') as f:
                current_hi = 0.0  # Высота инструмента по умолчанию
                current_op = None  # Текущая станция

                for line_num, line in enumerate(f, 1):
                    line = line.strip()

                    # Пропускаем пустые строки и комментарии
                    if not line or line.startswith('--'):
                        continue

                    # Парсим различные типы записей
                    if line.startswith('SS,'):
                        self._parse_ss_record(line)
                    elif line.startswith('OC,'):
                        current_op = self._parse_oc_record(line)
                        # Сохраняем текущую высоту инструмента для станции
                        if current_op and current_op in self.stations:
                            self.stations[current_op]['hi'] = current_hi
                    elif line.startswith('SP,'):
                        # Setup Point - может содержать координаты станции
                        self._parse_sp_record(line, current_op)
                    elif line.startswith('BR,'):
                        # Backsight - может содержать координаты референсной точки
                        self._parse_br_record(line, current_op)
                    elif line.startswith('CS,'):
                        self._parse_cs_record(line)
                    elif line.startswith('LS,'):
                        current_hi = self._parse_ls_record(line)
                        # Обновляем высоту инструмента для текущей станции
                        if current_op and current_op in self.stations:
                            self.stations[current_op]['hi'] = current_hi

        except (OSError, UnicodeDecodeError) as e:
            raise DataLoadError(f"Ошибка чтения RAW файла: {e!s}") from e

    def _parse_ss_record(self, line: str):
        """
        Парсит запись SS (Survey Shot)

        Формат: SS,OP1,FP4,AR0.11455,ZE89.57387,SD71.6006,--
        """
        try:
            parts = line.split(',')
            if len(parts) < 6:
                logger.debug(f"Неполная SS запись: {line}")
                return

            op = parts[1].strip()  # Observation Point (станция)
            fp = parts[2].strip()  # Fore Point (точка)

            # Извлекаем AR (Azimuth Reading)
            ar_match = re.search(r'AR([0-9.+-]+)', parts[3])
            ar = float(ar_match.group(1)) if ar_match else None

            # Извлекаем ZE (Zenith Angle)
            ze_match = re.search(r'ZE([0-9.+-]+)', parts[4])
            ze = float(ze_match.group(1)) if ze_match else None

            # Извлекаем SD (Slope Distance)
            sd_match = re.search(r'SD([0-9.+-]+)', parts[5])
            sd = float(sd_match.group(1)) if sd_match else None

            if ar is None or ze is None or sd is None:
                logger.debug(f"Не удалось извлечь данные из SS записи: {line}")
                return

            # Сохраняем измерение
            if not hasattr(self, '_ss_measurements'):
                self._ss_measurements = []

            self._ss_measurements.append({
                'op': op,
                'fp': fp,
                'ar': ar,
                'ze': ze,
                'sd': sd
            })

        except (ValueError, AttributeError, IndexError) as e:
            logger.debug(f"Ошибка парсинга SS записи: {line}, {e}")

    def _parse_oc_record(self, line: str) -> str | None:
        """
        Парсит запись OC (Occupation) - координаты станции

        Формат: OC,OP1,N 0.0000,E 0.0000,EL0.0000,--

        Returns:
            Имя станции (OP) или None
        """
        try:
            parts = line.split(',')
            if len(parts) < 5:
                logger.debug(f"Неполная OC запись: {line}")
                return None

            op = parts[1].strip()  # Observation Point

            # Извлекаем N (Northing)
            n_match = re.search(r'N\s*([0-9.+-]+)', parts[2])
            n = float(n_match.group(1)) if n_match else 0.0

            # Извлекаем E (Easting)
            e_match = re.search(r'E\s*([0-9.+-]+)', parts[3])
            e = float(e_match.group(1)) if e_match else 0.0

            # Извлекаем EL (Elevation)
            el_match = re.search(r'EL([0-9.+-]+)', parts[4])
            el = float(el_match.group(1)) if el_match else 0.0

            # Сохраняем координаты станции
            self.stations[op] = {
                'x': e,  # Easting -> X
                'y': n,  # Northing -> Y
                'z': el,  # Elevation -> Z
                'hi': 0.0  # Высота инструмента (будет обновлена из LS)
            }

            return op

        except (ValueError, AttributeError, IndexError) as e:
            logger.debug(f"Ошибка парсинга OC записи: {line}, {e}")
            return None

    def _parse_cs_record(self, line: str):
        """
        Парсит запись CS (Coordinate System)

        Формат: CS,CO3,ZGUTM Zones NAD83,ZNUTM83-11,DN
        """
        try:
            parts = line.split(',')
            if len(parts) >= 4:
                # Извлекаем информацию о системе координат
                cs_info = parts[2].strip()
                zone_info = parts[3].strip()

                self.coordinate_system = f"{cs_info} {zone_info}"

                # Извлекаем EPSG код
                self.epsg_code = self._extract_epsg_from_cs(cs_info, zone_info)

        except (ValueError, AttributeError, IndexError) as e:
            logger.debug(f"Ошибка парсинга CS записи: {line}, {e}")

    def _parse_ls_record(self, line: str) -> float:
        """
        Парсит запись LS (Level Setup) - высота инструмента

        Формат: LS,HI1.600,HR0.000
        """
        try:
            # Извлекаем HI (Height of Instrument)
            hi_match = re.search(r'HI([0-9.+-]+)', line)
            if hi_match:
                return float(hi_match.group(1))
            return 0.0
        except (ValueError, AttributeError) as e:
            logger.debug(f"Ошибка парсинга LS записи: {line}, {e}")
            return 0.0

    def _parse_sp_record(self, line: str, current_op: str | None):
        """
        Парсит запись SP (Setup Point) - может содержать координаты станции

        Формат: SP,PN2,N 0.0000,E 0.0000,EL0.0000,--
        """
        try:
            parts = line.split(',')
            if len(parts) < 5:
                return

            # Извлекаем N (Northing)
            n_match = re.search(r'N\s*([0-9.+-]+)', parts[2])
            n = float(n_match.group(1)) if n_match else None

            # Извлекаем E (Easting)
            e_match = re.search(r'E\s*([0-9.+-]+)', parts[3])
            e = float(e_match.group(1)) if e_match else None

            # Извлекаем EL (Elevation)
            el_match = re.search(r'EL([0-9.+-]+)', parts[4])
            el = float(el_match.group(1)) if el_match else None

            # Если координаты не нулевые и есть текущая станция, обновляем её координаты
            if current_op and current_op in self.stations:
                if n is not None and e is not None and el is not None:
                    # Обновляем только если текущие координаты нулевые или новые не нулевые
                    if (self.stations[current_op]['x'] == 0.0 and self.stations[current_op]['y'] == 0.0 and
                        self.stations[current_op]['z'] == 0.0) or (e != 0.0 or n != 0.0 or el != 0.0):
                        self.stations[current_op]['x'] = e
                        self.stations[current_op]['y'] = n
                        self.stations[current_op]['z'] = el
                        logger.debug(f"Обновлены координаты станции {current_op} из SP записи: ({e}, {n}, {el})")

        except (ValueError, AttributeError, IndexError) as e:
            logger.debug(f"Ошибка парсинга SP записи: {line}, {e}")

    def _parse_br_record(self, line: str, current_op: str | None):
        """
        Парсит запись BR (Backsight) - может содержать информацию о референсной точке

        Формат: BR,OP1,BP2,AR0.00000,ZE90.24058,SD71.0610
        """
        try:
            # BR записи обычно содержат измерения на референсную точку
            # Если координаты станции нулевые, можно попытаться вычислить их из backsight
            # Но для этого нужна информация о координатах референсной точки, которой может не быть
            # Пока просто логируем
            logger.debug(f"Найдена BR запись для станции {current_op}: {line}")
        except Exception as e:
            logger.debug(f"Ошибка парсинга BR записи: {line}, {e}")

    def _normalize_station_coordinates(self):
        """
        Нормализует координаты станции: устанавливает X=0, Y=0, Z=0, пересчитывает точки башни относительно станции.

        ВАЖНО: Пересчет выполняется на основе исходных полярных измерений, чтобы сохранить правильное
        относительное расположение точек относительно станции.

        Если станция не находится в (0, 0, 0), эта функция:
        1. Запоминает смещение станции
        2. Устанавливает координаты станции в (0, 0, 0)
        3. Пересчитывает все точки башни относительно станции (0, 0, 0) используя исходные полярные измерения
        """
        if not hasattr(self, '_ss_measurements') or not self._ss_measurements:
            # Если нет измерений, просто устанавливаем станцию в (0, 0, 0) и смещаем точки
            for op_name, station_data in self.stations.items():
                station_x = station_data['x']
                station_y = station_data['y']
                station_z = station_data['z']

                if abs(station_x) > 1e-6 or abs(station_y) > 1e-6 or abs(station_z) > 1e-6:
                    logger.info(f"Нормализация координат станции {op_name}: станция перемещается в (0, 0, 0)")
                    # Применяем обратное смещение ко всем точкам башни
                    for point in self.points:
                        if point.get('station') == op_name and not point.get('is_station', False):
                            point['x'] = point['x'] - station_x
                            point['y'] = point['y'] - station_y
                            point['z'] = point['z'] - station_z

                station_data['x'] = 0.0
                station_data['y'] = 0.0
                station_data['z'] = 0.0
            return

        # Пересчитываем точки башни относительно станции (0, 0, 0) используя исходные полярные измерения
        for op_name, station_data in self.stations.items():
            station_x = station_data['x']
            station_y = station_data['y']
            station_z = station_data['z']

            # Проверяем, нужно ли нормализовать координаты
            needs_normalization = abs(station_x) > 1e-6 or abs(station_y) > 1e-6 or abs(station_z) > 1e-6

            if needs_normalization:
                logger.info(f"Нормализация координат станции {op_name}: "
                          f"станция перемещается в (0, 0, 0) из ({station_x:.3f}, {station_y:.3f}, {station_z:.3f}). "
                          f"Точки башни пересчитываются относительно станции (0, 0, 0) на основе полярных измерений")

                # Удаляем все точки башни для этой станции из self.points
                # Они будут пересчитаны заново относительно (0, 0, 0)
                self.points = [p for p in self.points
                              if not (p.get('station') == op_name and not p.get('is_station', False))]

                # Пересчитываем все точки башни для этой станции относительно (0, 0, 0)
                for measurement in self._ss_measurements:
                    if measurement['op'] == op_name:
                        fp = measurement['fp']

                        # Вычисляем координаты точки относительно станции (0, 0, 0)
                        point_coords = self._calculate_point_coordinates(
                            station_x=0.0,
                            station_y=0.0,
                            station_z=0.0,
                            hi=station_data.get('hi', 0.0),
                            azimuth=measurement['ar'],
                            zenith=measurement['ze'],
                            slope_distance=measurement['sd']
                        )

                        self.points.append({
                            'x': point_coords[0],
                            'y': point_coords[1],
                            'z': point_coords[2],
                            'point_name': fp,
                            'station': op_name,
                            'is_station': False
                        })

                logger.info(f"Пересчитано {len([p for p in self.points if p.get('station') == op_name and not p.get('is_station', False)])} точек башни для станции {op_name}")

            # Всегда устанавливаем координаты станции в (0, 0, 0)
            station_data['x'] = 0.0
            station_data['y'] = 0.0
            station_data['z'] = 0.0

    def _add_stations_to_points(self):
        """Добавляет точки станций в список точек с пометкой is_station=True"""
        for op_name, station_data in self.stations.items():
            # Проверяем координаты станции
            station_x = station_data['x']
            station_y = station_data['y']
            station_z = station_data['z']

            # Валидация: проверяем, что X=0 и Y=0
            if abs(station_x) > 1e-6 or abs(station_y) > 1e-6:
                logger.warning(f"Станция {op_name} имеет нестандартные координаты XY: ({station_x:.6f}, {station_y:.6f}). "
                             f"Ожидается (0, 0). Координаты будут установлены в (0, 0, {station_z:.6f})")
                station_data['x'] = 0.0
                station_data['y'] = 0.0

            # Проверяем, что координаты станции не все нулевые
            if station_x == 0.0 and station_y == 0.0 and station_z == 0.0:
                logger.debug(f"Станция {op_name} имеет нулевые координаты - возможно, координаты не были установлены в файле")

            # Добавляем точку станции
            self.points.append({
                'x': station_data['x'],
                'y': station_data['y'],
                'z': station_data['z'],
                'point_name': op_name,
                'station': op_name,
                'is_station': True
            })
            logger.info(f"Добавлена точка станции {op_name}: ({station_data['x']:.6f}, {station_data['y']:.6f}, {station_data['z']:.6f})")

    def _extract_epsg_from_cs(self, cs_info: str, zone_info: str) -> int | None:
        """
        Извлекает EPSG код из информации о системе координат

        Примеры:
        - UTM Zone 11 NAD83 -> EPSG:26911
        - UTM Zone 11 WGS84 -> EPSG:32611
        - ZNUTM83-11 -> EPSG:26911 (UTM Zone 11 NAD83)
        """
        try:
            # Объединяем обе строки для поиска
            combined = f"{cs_info} {zone_info}"

            # Ищем UTM зону в различных форматах
            # Формат 1: ZNUTM83-11 (UTM Zone 11 NAD83)
            utm_match = re.search(r'ZNUTM\d+-(\d+)', combined, re.IGNORECASE)
            if utm_match:
                zone = int(utm_match.group(1))
                # Проверяем датум в строке
                if '83' in combined or 'NAD83' in combined:
                    if 1 <= zone <= 23:
                        return 26900 + zone
                elif '84' in combined or 'WGS84' in combined:
                    if 1 <= zone <= 60:
                        return 32600 + zone

            # Формат 2: UTM Zone 11 или UTM Zone11
            utm_match = re.search(r'UTM[^\d]*Zone[^\d]*(\d+)', combined, re.IGNORECASE)
            if not utm_match:
                # Формат 3: просто UTM и число
                utm_match = re.search(r'UTM[^\d]*(\d+)', combined, re.IGNORECASE)

            if utm_match:
                zone = int(utm_match.group(1))

                # Определяем датум
                if 'NAD83' in combined or '83' in combined:
                    # NAD83 UTM: EPSG 26901-26923 (зоны 1-23)
                    if 1 <= zone <= 23:
                        return 26900 + zone
                elif 'WGS84' in combined or '84' in combined:
                    # WGS84 UTM: EPSG 32601-32660 (зоны 1-60 северное полушарие)
                    if 1 <= zone <= 60:
                        return 32600 + zone

            # Если не нашли, возвращаем None
            logger.debug(f"Не удалось определить EPSG для: {cs_info} {zone_info}")
            return None

        except (ValueError, AttributeError) as e:
            logger.debug(f"Ошибка извлечения EPSG: {e}")
            return None

    def _calculate_all_points(self):
        """Вычисляет координаты всех точек из SS измерений"""
        if not hasattr(self, '_ss_measurements'):
            return

        # Проверяем наличие станций с ненулевыми координатами
        stations_with_coords = {op: st for op, st in self.stations.items()
                               if not (st['x'] == 0.0 and st['y'] == 0.0 and st['z'] == 0.0)}

        # Если все станции имеют нулевые координаты, используем относительные координаты
        use_relative_coords = not stations_with_coords
        if use_relative_coords:
            logger.warning("Все станции имеют нулевые координаты. Будет использован режим относительных координат")
            # Сначала вычисляем все точки относительно (0,0,0) для получения относительных координат
            relative_points = []
            for measurement in self._ss_measurements:
                op = measurement['op']
                fp = measurement['fp']

                if op not in self.stations:
                    continue

                station = self.stations[op]
                # Вычисляем относительные координаты точки от станции (0,0,0)
                point_coords = self._calculate_point_coordinates(
                    station_x=0.0,
                    station_y=0.0,
                    station_z=0.0,
                    hi=station.get('hi', 0.0),
                    azimuth=measurement['ar'],
                    zenith=measurement['ze'],
                    slope_distance=measurement['sd']
                )
                relative_points.append({
                    'coords': point_coords,
                    'op': op,
                    'fp': fp,
                    'station': station
                })

            # Устанавливаем координаты станции в (0, 0, 0)
            if relative_points:
                # Находим самую нижнюю точку (минимальная Z координата) для определения смещения
                lowest_point = min(relative_points, key=lambda p: p['coords'][2])
                lowest_coords = lowest_point['coords']
                lowest_station = lowest_point['station']

                # Устанавливаем координаты станции: X=0, Y=0, Z=0 (начало координат)
                z_offset_for_tower = 0.0  # Смещение по Z для точек башни
                for op, station in self.stations.items():
                    if station['x'] == 0.0 and station['y'] == 0.0 and station['z'] == 0.0:
                        # Устанавливаем станцию: X=0, Y=0, Z=0 (начало координат XYZ)
                        station['x'] = 0.0  # ВСЕГДА 0
                        station['y'] = 0.0  # ВСЕГДА 0
                        station['z'] = 0.0  # ВСЕГДА 0

                        # Вычисляем смещение по Z для точек башни
                        # Если самая нижняя точка имеет отрицательную Z, нужно сместить все точки вверх
                        if lowest_coords[2] < 0:
                            z_offset_for_tower = abs(lowest_coords[2]) + 0.1  # Добавляем небольшой запас

                        logger.info(f"Координаты станции {op} установлены в (0, 0, 0) - начало координат XYZ. "
                                  f"Точки башни будут смещены по Z на {z_offset_for_tower:.3f}м для устранения отрицательных высот")

                # Используем уже вычисленные относительные координаты из relative_points
                # Они были вычислены относительно (0, 0, 0), что соответствует нашей станции
                for rel_point in relative_points:
                    op = rel_point['op']
                    fp = rel_point['fp']
                    coords = rel_point['coords']

                    # Применяем смещение по Z к точкам башни, если нужно
                    point_z = coords[2] + z_offset_for_tower

                    self.points.append({
                        'x': coords[0],  # Уже относительно (0, 0, 0) по X
                        'y': coords[1],  # Уже относительно (0, 0, 0) по Y
                        'z': point_z,  # Скорректированная Z с учетом смещения
                        'point_name': fp,
                        'station': op,
                        'is_station': False
                    })
            return

        # Обычный режим - станции имеют координаты
        for measurement in self._ss_measurements:
            op = measurement['op']
            fp = measurement['fp']

            # Получаем координаты станции
            if op not in self.stations:
                logger.debug(f"Станция {op} не найдена для точки {fp}")
                continue

            station = self.stations[op]

            # Вычисляем координаты точки
            point_coords = self._calculate_point_coordinates(
                station_x=station['x'],
                station_y=station['y'],
                station_z=station['z'],
                hi=station.get('hi', 0.0),
                azimuth=measurement['ar'],
                zenith=measurement['ze'],
                slope_distance=measurement['sd']
            )

            # Сохраняем точку
            self.points.append({
                'x': point_coords[0],
                'y': point_coords[1],
                'z': point_coords[2],
                'point_name': fp,
                'station': op,
                'is_station': False  # Это не точка станции
            })

    def _calculate_point_coordinates(
        self,
        station_x: float,
        station_y: float,
        station_z: float,
        hi: float,
        azimuth: float,
        zenith: float,
        slope_distance: float
    ) -> tuple[float, float, float]:
        """
        Вычисляет координаты точки из полярных измерений

        Args:
            station_x, station_y, station_z: Координаты станции
            hi: Высота инструмента (Height of Instrument)
            azimuth: Азимут в градусах (0-360)
            zenith: Зенитный угол в градусах (0-180)
            slope_distance: Наклонное расстояние

        Returns:
            Кортеж (x, y, z) координат точки
        """
        # Преобразуем углы в радианы
        az_rad = math.radians(azimuth)
        ze_rad = math.radians(zenith)

        # Вычисляем горизонтальное расстояние
        horizontal_distance = slope_distance * math.sin(ze_rad)

        # Вычисляем приращения координат
        delta_x = horizontal_distance * math.sin(az_rad)
        delta_y = horizontal_distance * math.cos(az_rad)

        # Вычисляем приращение высоты
        # Вертикальное расстояние = SD * cos(ZE) - HI
        delta_z = slope_distance * math.cos(ze_rad) - hi

        # Вычисляем координаты точки
        x = station_x + delta_x
        y = station_y + delta_y
        z = station_z + delta_z

        return (x, y, z)


class FieldGeniusINILoader:
    """
    Загрузчик для FieldGenius INI файлов

    Парсит конфигурационные файлы проектов FieldGenius и извлекает метаданные.
    """

    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        self.config = configparser.ConfigParser()
        self.metadata: dict[str, Any] = {}

    def load(self) -> dict[str, Any]:
        """
        Загружает метаданные из INI файла

        Returns:
            Словарь с метаданными проекта:
            - version: версия FieldGenius
            - project_type: тип проекта
            - raw_file: путь к RAW файлу
            - survey_csv: путь к survey.csv
            - settings: настройки проекта
            - codegroups: кодовые группы
        """
        try:
            # Читаем INI файл
            self.config.read(self.file_path, encoding='utf-8')

            # Извлекаем версию
            if self.config.has_section('VERSION'):
                self.metadata['version'] = self.config.get('VERSION', 'VersionNumber', fallback=None)

            # Извлекаем информацию о файлах
            if self.config.has_section('FILES'):
                self.metadata['project_type'] = self.config.get('FILES', 'ProjectType', fallback=None)
                raw_file = self.config.get('FILES', 'RAW', fallback=None)
                if raw_file:
                    # Путь к RAW файлу относительно папки с INI
                    raw_path = self.file_path.parent / raw_file
                    # Проверяем существование с учетом регистра (Windows не чувствителен к регистру)
                    if not raw_path.exists():
                        # Пробуем найти файл без учета регистра
                        raw_name_lower = raw_file.lower()
                        for f in self.file_path.parent.iterdir():
                            if f.is_file() and f.name.lower() == raw_name_lower:
                                raw_path = f
                                break
                    self.metadata['raw_file'] = str(raw_path) if raw_path.exists() else None
                else:
                    self.metadata['raw_file'] = None

                survey_csv = self.config.get('FILES', 'FCF', fallback=None)
                if survey_csv:
                    csv_path = self.file_path.parent / survey_csv
                    self.metadata['survey_csv'] = str(csv_path) if csv_path.exists() else None
                else:
                    self.metadata['survey_csv'] = None

            # Извлекаем настройки
            if self.config.has_section('SETTINGS'):
                self.metadata['settings'] = {
                    'length_unit': self.config.get('SETTINGS', 'LengthUnit', fallback=None),
                    'length_prec': self.config.get('SETTINGS', 'LengthPrec', fallback=None),
                    'angle_unit': self.config.get('SETTINGS', 'AngleUnit', fallback=None),
                    'angle_prec': self.config.get('SETTINGS', 'AnglePrec', fallback=None),
                }

            # Извлекаем кодовые группы
            if self.config.has_section('CODEGROUPS'):
                group_count = self.config.getint('CODEGROUPS', 'GroupCount', fallback=0)
                self.metadata['codegroups'] = {}
                for i in range(1, group_count + 1):
                    section_name = f'CODEGROUP{i:02d}'
                    if self.config.has_section(section_name):
                        group_name = self.config.get(section_name, 'Name', fallback=f'Group{i}')
                        item_count = self.config.getint(section_name, 'ItemCount', fallback=0)
                        items = []
                        for j in range(1, item_count + 1):
                            item_key = f'Item{j:02d}'
                            if self.config.has_option(section_name, item_key):
                                items.append(self.config.get(section_name, item_key))
                        self.metadata['codegroups'][group_name] = items

            logger.info(f"Загружены метаданные из INI файла: {self.file_path}")
            return self.metadata

        except (configparser.Error, OSError) as e:
            raise DataLoadError(f"Ошибка загрузки INI файла: {e!s}") from e

    def get_raw_file_path(self) -> str | None:
        """Возвращает путь к RAW файлу, если он указан"""
        if not self.metadata:
            self.load()
        return self.metadata.get('raw_file')

    def get_survey_csv_path(self) -> str | None:
        """Возвращает путь к survey.csv файлу, если он указан"""
        if not self.metadata:
            self.load()
        return self.metadata.get('survey_csv')


class FieldGeniusDBFLoader:
    """
    Загрузчик для FieldGenius DBF файлов

    Загружает координаты точек из DBF файлов (основных и figures).
    """

    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        self.epsg_code: int | None = None

    def load(self) -> pd.DataFrame:
        """
        Загружает данные из DBF файла

        Returns:
            DataFrame с колонками: x, y, z, name

        Raises:
            DataLoadError: При ошибке загрузки
            FileFormatError: Если библиотека dbfread недоступна
        """
        if not DBF_AVAILABLE:
            raise FileFormatError("Библиотека dbfread не установлена. Установите её: pip install dbfread")

        try:
            # Пробуем разные кодировки
            encodings = ['utf-8', 'cp1251', 'latin1', 'cp866', 'windows-1251', 'iso-8859-1']
            dbf = None
            last_error = None

            for encoding in encodings:
                try:
                    # Пробуем открыть с игнорированием неподдерживаемых полей
                    dbf = DBF(str(self.file_path), encoding=encoding, ignore_missing_memofile=True, char_decode_errors='ignore')
                    # Проверяем, что файл читается
                    try:
                        _ = list(dbf)[:1]  # Пробуем прочитать первую запись
                        logger.debug(f"DBF файл успешно открыт с кодировкой {encoding}")
                        break
                    except Exception as read_error:
                        # Файл открылся, но не читается - возможно, пустой или поврежден
                        logger.debug(f"DBF файл открыт с кодировкой {encoding}, но не читается: {read_error}")
                        dbf = None
                        last_error = read_error
                        continue
                except (UnicodeDecodeError, Exception) as e:
                    error_str = str(e)
                    # Если ошибка связана с неподдерживаемым типом поля, пробуем другой подход
                    if 'Unknown field type' in error_str or 'field type' in error_str.lower():
                        logger.debug(f"DBF содержит неподдерживаемые поля (тип поля), пропускаем: {e}")
                        last_error = e
                        continue
                    logger.debug(f"Не удалось открыть DBF с кодировкой {encoding}: {e}")
                    last_error = e
                    continue

            if dbf is None:
                error_msg = "Не удалось открыть DBF файл ни с одной из кодировок"
                if last_error:
                    error_msg += f": {last_error}"
                raise DataLoadError(error_msg)

            # Получаем список полей
            field_names = [field.name for field in dbf.fields]
            logger.debug(f"Поля DBF файла: {field_names}")

            # Определяем поля координат (различные варианты названий)
            x_fields = ['X', 'E', 'EASTING', 'Easting', 'x', 'e']
            y_fields = ['Y', 'N', 'NORTHING', 'Northing', 'y', 'n']
            z_fields = ['Z', 'EL', 'ELEV', 'ELEVATION', 'Elevation', 'z', 'el', 'elev']
            name_fields = ['NAME', 'POINT', 'POINT_ID', 'ID', 'PNT_ID', 'Point', 'name', 'point', 'id']

            x_field = None
            y_field = None
            z_field = None
            name_field = None

            # Ищем поля координат
            for field in field_names:
                field_upper = field.upper()
                if not x_field and any(xf.upper() in field_upper for xf in x_fields):
                    x_field = field
                if not y_field and any(yf.upper() in field_upper for yf in y_fields):
                    y_field = field
                if not z_field and any(zf.upper() in field_upper for zf in z_fields):
                    z_field = field
                if not name_field and any(nf.upper() in field_upper for nf in name_fields):
                    name_field = field

            if not x_field or not y_field:
                raise DataValidationError(f"Не найдены поля координат X и Y в DBF файле. Доступные поля: {field_names}")

            # Загружаем данные
            points = []
            for record in dbf:
                try:
                    x = self._get_numeric_value(record.get(x_field))
                    y = self._get_numeric_value(record.get(y_field))
                    z = self._get_numeric_value(record.get(z_field)) if z_field else 0.0

                    # Пропускаем записи с нулевыми координатами (возможно, служебные)
                    if x == 0.0 and y == 0.0 and z == 0.0:
                        continue

                    name = str(record.get(name_field)) if name_field and record.get(name_field) else f'Точка {len(points)+1}'

                    points.append({
                        'x': x,
                        'y': y,
                        'z': z,
                        'name': name
                    })
                except (ValueError, TypeError) as e:
                    logger.debug(f"Ошибка обработки записи DBF: {e}")
                    continue

            if not points:
                raise DataValidationError("Не найдено точек с координатами в DBF файле")

            result = pd.DataFrame(points)
            logger.info(f"Загружено {len(result)} точек из DBF файла: {self.file_path}")

            return result

        except OSError as e:
            raise DataLoadError(f"Ошибка чтения DBF файла: {e!s}") from e
        except Exception as e:
            raise DataLoadError(f"Ошибка загрузки DBF файла: {e!s}") from e

    def _get_numeric_value(self, value: Any) -> float:
        """Преобразует значение в число"""
        if value is None:
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            # Удаляем пробелы и пробуем преобразовать
            value = value.strip()
            if not value:
                return 0.0
            try:
                return float(value)
            except ValueError:
                return 0.0
        return 0.0


class FieldGeniusProjectLoader:
    """
    Комплексный загрузчик проектов FieldGenius

    Автоматически определяет проект по .ini файлу или папке и загружает данные
    из всех доступных источников с приоритетом:
    1. .dbf файлы (если есть координаты)
    2. .raw файл (если указан в .ini)
    3. survey.csv (если есть данные)
    """

    def __init__(self, project_path: str):
        self.project_path = Path(project_path)
        self.project_dir: Path = None
        self.ini_file: Path | None = None
        self.epsg_code: int | None = None
        self.metadata: dict[str, Any] = {}

        # Определяем тип пути
        if self.project_path.is_file():
            if self.project_path.suffix.lower() == '.ini':
                self.ini_file = self.project_path
                self.project_dir = self.project_path.parent
            else:
                raise FileFormatError(f"Неподдерживаемый файл проекта: {self.project_path}")
        elif self.project_path.is_dir():
            self.project_dir = self.project_path
            # Ищем INI файл в папке
            ini_files = list(self.project_dir.glob('*.ini'))
            if ini_files:
                self.ini_file = ini_files[0]  # Берем первый найденный
                logger.info(f"Найден INI файл проекта: {self.ini_file}")
        else:
            raise FileFormatError(f"Путь не существует: {self.project_path}")

    def load(self) -> pd.DataFrame:
        """
        Загружает данные проекта из всех доступных источников

        Returns:
            DataFrame с колонками: x, y, z, name

        Raises:
            DataLoadError: При ошибке загрузки
        """
        data_sources = []

        # 1. Загружаем метаданные из INI, если есть
        if self.ini_file:
            try:
                ini_loader = FieldGeniusINILoader(str(self.ini_file))
                self.metadata = ini_loader.load()
                logger.info(f"Загружены метаданные проекта из {self.ini_file}")
            except Exception as e:
                logger.warning(f"Не удалось загрузить метаданные из INI: {e}")

        # 2. Пробуем загрузить из DBF файлов (приоритет 1)
        if self.project_dir:
            dbf_files = list(self.project_dir.glob('*.dbf'))
            # Исключаем figures файлы из основного поиска
            main_dbf_files = [f for f in dbf_files if 'figures' not in f.name.lower()]

            for dbf_file in main_dbf_files:
                try:
                    if DBF_AVAILABLE:
                        dbf_loader = FieldGeniusDBFLoader(str(dbf_file))
                        data = dbf_loader.load()
                        if len(data) > 0:
                            data_sources.append(('dbf', dbf_file, data))
                            self.epsg_code = dbf_loader.epsg_code
                            logger.info(f"Загружены данные из DBF: {dbf_file.name} ({len(data)} точек)")
                            break  # Используем первый успешный DBF
                except Exception as e:
                    logger.debug(f"Не удалось загрузить DBF {dbf_file.name}: {e}")
                    continue

        # 3. Пробуем загрузить из RAW файла (приоритет 2)
        raw_file_path = None
        if self.metadata.get('raw_file'):
            raw_file_path = Path(self.metadata['raw_file'])
            if not raw_file_path.exists():
                # Пробуем найти файл без учета регистра
                raw_name = raw_file_path.name
                for f in raw_file_path.parent.iterdir():
                    if f.is_file() and f.name.lower() == raw_name.lower():
                        raw_file_path = f
                        break
        elif self.project_dir:
            # Ищем RAW файл в папке проекта
            raw_files = list(self.project_dir.glob('*.raw'))
            if raw_files:
                raw_file_path = raw_files[0]

        if raw_file_path and raw_file_path.exists() and not data_sources:
            try:
                raw_loader = FieldGeniusRAWLoader(str(raw_file_path))
                if raw_loader._is_fieldgenius_file():
                    data = raw_loader.load()
                    if len(data) > 0:
                        data_sources.append(('raw', raw_file_path, data))
                        self.epsg_code = raw_loader.epsg_code
                        logger.info(f"Загружены данные из RAW: {raw_file_path.name} ({len(data)} точек)")
            except Exception as e:
                logger.debug(f"Не удалось загрузить RAW {raw_file_path.name}: {e}")

        # 4. Пробуем загрузить из survey.csv (приоритет 3)
        csv_file_path = None
        if self.metadata.get('survey_csv'):
            csv_file_path = Path(self.metadata['survey_csv'])
        elif self.project_dir:
            csv_files = list(self.project_dir.glob('survey.csv'))
            if csv_files:
                csv_file_path = csv_files[0]

        if csv_file_path and csv_file_path.exists() and not data_sources:
            try:
                from core.data_loader import CSVLoader
                csv_loader = CSVLoader(str(csv_file_path))
                data = csv_loader.load()
                if len(data) > 0 and 'x' in data.columns and 'y' in data.columns:
                    data_sources.append(('csv', csv_file_path, data))
                    logger.info(f"Загружены данные из CSV: {csv_file_path.name} ({len(data)} точек)")
            except Exception as e:
                logger.debug(f"Не удалось загрузить CSV {csv_file_path.name}: {e}")

        # Объединяем данные из всех источников
        if not data_sources:
            # Если нет данных, возвращаем пустой DataFrame с правильной структурой
            logger.warning(f"Не найдено данных для загрузки в проекте FieldGenius: {self.project_path}")
            logger.info("Проверьте наличие файлов: .dbf, .raw, survey.csv")
            # Возвращаем пустой DataFrame с правильными колонками
            return pd.DataFrame(columns=['x', 'y', 'z', 'name'])

        # Используем данные из первого успешного источника
        source_type, source_path, result_data = data_sources[0]
        logger.info(f"Использован источник данных: {source_type} ({source_path.name})")

        return result_data

