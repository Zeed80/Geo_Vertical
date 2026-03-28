"""
Загрузчик данных из различных форматов Trimble
Поддерживает: JobXML, CSV экспорт, текстовые координатные файлы, бинарные JOB файлы
"""

import logging
import math
import re
import struct
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from core.import_models import ImportDiagnostics, LoadedSurveyData

logger = logging.getLogger(__name__)

_STATION_NAME_RE = re.compile(r'^(?:st|station)[\w-]*$', re.IGNORECASE)
_AUXILIARY_NAME_RE = re.compile(r'^(?:rp|ref|bs)[\w-]*$', re.IGNORECASE)


def _is_station_point_name(value: Any) -> bool:
    name = str(value or '').strip()
    return bool(name) and bool(_STATION_NAME_RE.match(name))


def _is_auxiliary_point_name(value: Any) -> bool:
    name = str(value or '').strip()
    return bool(name) and bool(_AUXILIARY_NAME_RE.match(name))


def _annotate_trimble_point_records(data: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Annotate Trimble points with station-block metadata while preserving record order."""
    if data.empty:
        details = {
            'multi_station_detected': False,
            'station_blocks': [],
            'auxiliary_points': [],
        }
        return data.copy(), details

    annotated = data.copy()
    annotated['source_order'] = np.arange(1, len(annotated) + 1, dtype=int)
    annotated['is_station'] = annotated['name'].map(_is_station_point_name)
    annotated['is_auxiliary'] = annotated['name'].map(_is_auxiliary_point_name)
    annotated['is_control'] = False
    annotated['survey_station_name'] = pd.NA
    annotated['survey_station_order'] = pd.NA

    station_blocks: list[dict[str, Any]] = []
    auxiliary_points: list[str] = []
    current_station_name: str | None = None
    current_station_order: int | None = None
    current_block: dict[str, Any] | None = None

    for idx, row in annotated.iterrows():
        point_name = str(row.get('name', '')).strip()
        if bool(row.get('is_station', False)):
            current_station_order = len(station_blocks) + 1
            current_station_name = point_name or f'station_{current_station_order}'
            current_block = {
                'station_name': current_station_name,
                'station_order': current_station_order,
                'start_record': int(row['source_order']),
                'end_record': int(row['source_order']),
                'point_count': 1,
            }
            station_blocks.append(current_block)
        elif current_block is not None:
            current_block['end_record'] = int(row['source_order'])
            current_block['point_count'] = int(current_block['point_count']) + 1

        if current_station_order is not None:
            annotated.at[idx, 'survey_station_name'] = current_station_name
            annotated.at[idx, 'survey_station_order'] = current_station_order

        if bool(row.get('is_auxiliary', False)):
            auxiliary_points.append(point_name)

    details = {
        'multi_station_detected': len(station_blocks) > 1,
        'station_blocks': station_blocks,
        'auxiliary_points': auxiliary_points,
    }
    return annotated, details


def _deduplicate_multi_station_points(
    df: pd.DataFrame,
    *,
    xy_tol: float = 0.30,
    z_tol: float = 0.50,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """
    Для данных с несколькими стояниями находит одинаковые физические точки,
    измеренные с разных инструментальных стояний, и помечает избыточные
    измерения как is_control=True.

    Критерий «лучшего» измерения: наименьшее горизонтальное расстояние
    от точки до её стояния. Более близкое стояние = более точное измерение.

    Параметры:
        xy_tol: максимальное горизонтальное расстояние (м) для признания дублем
        z_tol:  максимальная разность по Z (м) для признания дублем

    Возвращает (df_с_пометками, stats_dict).
    """
    result = df.copy()
    if 'is_control' not in result.columns:
        result['is_control'] = False

    stats: dict[str, Any] = {
        'multi_station_dedup_applied': False,
        'duplicate_groups': 0,
        'redundant_points_marked': 0,
        'station_positions': {},
    }

    if 'survey_station_name' not in result.columns:
        return result, stats

    # Собираем координаты стояний из строк-стояний
    station_positions: dict[str, np.ndarray] = {}
    if 'is_station' in result.columns:
        for idx in result[result['is_station'].astype(bool)].index:
            row = result.loc[idx]
            st_name = str(row.get('survey_station_name') or row.get('name') or '').strip()
            if not st_name:
                continue
            try:
                pos = np.array([float(row['x']), float(row['y'])], dtype=float)
                if np.all(np.isfinite(pos)):
                    station_positions[st_name] = pos
            except (ValueError, TypeError, KeyError):
                pass
    stats['station_positions'] = {k: v.tolist() for k, v in station_positions.items()}

    # Отбираем только рабочие измерительные точки
    working_mask = pd.Series(True, index=result.index)
    for flag_col in ('is_station', 'is_auxiliary', 'is_control'):
        if flag_col in result.columns:
            working_mask &= ~result[flag_col].astype(bool)

    working = result[working_mask]
    if len(working) < 2:
        return result, stats

    working_indices = working.index.tolist()
    n = len(working_indices)
    coords_xy = working[['x', 'y']].to_numpy(dtype=float)
    coords_z = working['z'].to_numpy(dtype=float)
    station_names = working['survey_station_name'].fillna('').tolist()

    # Union-Find для кластеризации дублей
    parent = list(range(n))

    def _find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def _union(i: int, j: int) -> None:
        pi, pj = _find(i), _find(j)
        if pi != pj:
            parent[pj] = pi

    for i in range(n):
        for j in range(i + 1, n):
            if station_names[i] == station_names[j]:
                continue  # одно стояние — не дубль
            dxy = float(np.linalg.norm(coords_xy[i] - coords_xy[j]))
            dz = abs(float(coords_z[i]) - float(coords_z[j]))
            if dxy <= xy_tol and dz <= z_tol:
                _union(i, j)

    # Собираем кластеры
    clusters: dict[int, list[int]] = defaultdict(list)
    for i in range(n):
        clusters[_find(i)].append(i)

    duplicate_clusters = {r: m for r, m in clusters.items() if len(m) > 1}
    if not duplicate_clusters:
        return result, stats

    stats['multi_station_dedup_applied'] = True
    stats['duplicate_groups'] = len(duplicate_clusters)

    marked_control = 0
    for members in duplicate_clusters.values():
        # Для каждого члена группы вычисляем расстояние до своего стояния
        dist_to_station: list[float] = []
        for i in members:
            st_name = station_names[i]
            st_pos = station_positions.get(st_name)
            if st_pos is not None:
                dist = float(np.linalg.norm(coords_xy[i] - st_pos))
            else:
                dist = float('inf')
            dist_to_station.append(dist)

        # Лучший — ближайший к своей стоянке; при равенстве берём первый
        best_local = int(np.argmin(dist_to_station))
        for k, i in enumerate(members):
            if k != best_local:
                original_idx = working_indices[i]
                result.at[original_idx, 'is_control'] = True
                marked_control += 1

    stats['redundant_points_marked'] = marked_control

    if marked_control > 0:
        logger.info(
            f"Автодедупликация многостояночных данных: "
            f"{len(duplicate_clusters)} групп дублей, "
            f"помечено {marked_control} избыточных измерений как контрольные"
        )
    return result, stats


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
        self.parser_strategy = "trimble_jobxml_pointrecord"
        self.warnings: list[str] = []
        self.raw_records = 0
        self.annotation_details: dict[str, Any] = {}
        self.dedup_stats: dict[str, Any] = {}

    def load(self) -> pd.DataFrame:
        """Загружает данные из JobXML файла"""
        try:
            tree = ET.parse(self.file_path)
            root = tree.getroot()
            self.raw_records = len(root.findall('.//PointRecord')) or len(root.findall('.//Point'))

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
                self.parser_strategy = "trimble_jobxml_point_grid"
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
                self.parser_strategy = "trimble_jobxml_point_wgs84"
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
            raise ValueError(f"Ошибка парсинга JobXML: {e!s}")
        except Exception as e:
            raise ValueError(f"Ошибка чтения JobXML: {e!s}")

    def _to_dataframe(self) -> pd.DataFrame:
        """Конвертирует точки в DataFrame. При наличии нескольких стояний
        автоматически помечает избыточные дублирующие измерения."""
        df = pd.DataFrame(self.points)
        result = df[['x', 'y', 'z']].copy()
        result['name'] = df['point_id']
        annotated, annotation_details = _annotate_trimble_point_records(result)
        self.annotation_details = annotation_details

        if annotation_details.get('multi_station_detected'):
            annotated, dedup_stats = _deduplicate_multi_station_points(annotated)
            self.dedup_stats = dedup_stats
            n_marked = int(dedup_stats.get('redundant_points_marked', 0))
            n_groups = int(dedup_stats.get('duplicate_groups', 0))
            if n_marked > 0:
                self.warnings.append(
                    f"Обнаружено {n_groups} групп задублированных измерений "
                    f"({n_marked} точек помечены как контрольные дубли). "
                    f"Для каждой группы автоматически выбрано лучшее измерение "
                    f"по дистанции до стоянки. Ручная перестановка по поясам доступна в мастере импорта."
                )

        return annotated


class TrimbleCSVLoader:
    """
    Загрузчик для CSV файлов, экспортированных из Trimble

    Trimble может экспортировать данные в CSV через:
    - Trimble Business Center → Export → CSV
    - Trimble Access → Export → Text File
    """

    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        self.parser_strategy = "trimble_csv_headers"
        self.warnings: list[str] = []
        self.raw_records = 0

    def load(self) -> pd.DataFrame:
        """Загружает CSV файл от Trimble"""
        try:
            # Пробуем различные варианты структуры CSV от Trimble

            # Вариант 1: Стандартный CSV с заголовками
            try:
                df = pd.read_csv(self.file_path)
                self.raw_records = len(df)
                return self._parse_trimble_csv(df)
            except (pd.errors.ParserError, KeyError, ValueError, IndexError):
                pass

            # Вариант 2: CSV без заголовков
            try:
                df = pd.read_csv(self.file_path, header=None)
                self.raw_records = len(df)
                self.parser_strategy = "trimble_csv_no_header"
                return self._parse_trimble_csv_no_header(df)
            except (pd.errors.ParserError, KeyError, ValueError, IndexError):
                pass

            # Вариант 3: Текстовый файл с пробелами
            try:
                df = pd.read_csv(self.file_path, delim_whitespace=True)
                self.raw_records = len(df)
                self.parser_strategy = "trimble_text_whitespace"
                return self._parse_trimble_csv(df)
            except (pd.errors.ParserError, KeyError, ValueError, IndexError):
                pass

            raise ValueError("Не удалось распознать формат Trimble CSV")

        except Exception as e:
            raise ValueError(f"Ошибка чтения Trimble CSV: {e!s}")

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
        self.parser_strategy = "trimble_text_regex"
        self.warnings: list[str] = []
        self.raw_records = 0

    def load(self) -> pd.DataFrame:
        """Загружает текстовый файл с координатами"""
        try:
            with open(self.file_path, encoding='utf-8') as f:
                lines = f.readlines()
            self.raw_records = len(lines)

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
            raise ValueError(f"Ошибка чтения текстового файла: {e!s}")


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
        self.parser_strategy = "job_binary_unresolved"
        self.warnings: list[str] = []
        self.raw_records = 0
        self.method_stats: dict[str, Any] = {}
        self.annotation_details: dict[str, Any] = {}

    def load(self) -> pd.DataFrame:
        """Пытается загрузить бинарный JOB файл"""
        try:
            with open(self.file_path, 'rb') as f:
                data = f.read()
            self.raw_records = len(data)

            # Проверяем заголовок
            header = data[:40].decode('ascii', errors='ignore')
            if 'Trimble' not in header:
                raise ValueError("Файл не является Trimble JOB файлом")

            logger.info(f"Загрузка бинарного JOB файла: {self.file_path.name}")
            name_candidates = self._extract_ascii_identifiers(data)
            structured_points = self._extract_structured_points(data)
            step8_points = self._scan_triplets(data, step=8, max_abs=1000.0, label='triplet_step8')
            step4_points = self._scan_triplets(data, step=4, max_abs=10000.0, label='triplet_step4')
            pattern_points = self._scan_pattern_records(data)

            if structured_points:
                unique_points = self._deduplicate_structured_points(structured_points)
            else:
                all_points = step8_points + step4_points + pattern_points
                unique_points = self._deduplicate_points(all_points)
            self.points = unique_points

            if not self.points:
                raise ValueError("В JOB файле не найдено координат точек")

            if not structured_points:
                self._attach_point_names(name_candidates)
            self.parser_strategy = self._select_parser_strategy(
                structured_count=len(structured_points),
                name_candidates=name_candidates,
                step8_count=len(step8_points),
                step4_count=len(step4_points),
                pattern_count=len(pattern_points),
            )

            if not structured_points and len(name_candidates) < len(self.points):
                self.warnings.append(
                    "Имена точек извлечены частично, для части записей использованы сгенерированные идентификаторы."
                )
            if structured_points:
                self.warnings.append(
                    "Координаты JOB восстановлены из структурированных записей и полярных наблюдений; для полной идентичности рекомендуется сверка с экспортом JobXML."
                )
            else:
                self.warnings.append(
                    "Бинарный JOB обработан многоступенчатым эвристическим парсером; результат рекомендуется сверить с экспортом JobXML."
                )

            logger.info(
                f"Загружено {len(self.points)} точек из JOB файла "
                f"(стратегия={self.parser_strategy}, методы={self.method_stats})"
            )
            for warning in self.warnings:
                logger.warning(warning)

            return self._to_dataframe()

        except Exception as e:
            logger.error(f"Ошибка загрузки JOB файла: {e}")
            raise ValueError(
                f"Не удалось загрузить бинарный JOB файл: {e!s}\n\n"
                "РЕКОМЕНДАЦИЯ:\n"
                "1. Откройте JOB файл в Trimble Business Center\n"
                "2. Экспортируйте в JobXML: File → Export → JobXML\n"
                "3. Загрузите JobXML файл (.jxl) в программу"
            )

    def _extract_ascii_identifiers(self, data: bytes) -> list[str]:
        matches = re.findall(rb'[A-Za-z][A-Za-z0-9_\-]{1,15}', data)
        blacklist = {'Trimble', 'Version', 'Project', 'Record', 'Point'}
        identifiers: list[str] = []
        seen = set()
        for raw in matches:
            try:
                text = raw.decode('ascii', errors='ignore')
            except Exception:
                continue
            if not text or text in blacklist or text in seen:
                continue
            if text.startswith('PT') or any(ch.isdigit() for ch in text):
                identifiers.append(text)
                seen.add(text)
        self.method_stats['ascii_identifier_candidates'] = len(identifiers)
        return identifiers

    def _extract_structured_points(self, data: bytes) -> list[dict[str, Any]]:
        records = self._iterate_structured_records(data)
        self.method_stats['structured_records'] = len(records)
        if not records:
            self.method_stats['structured_direct_points'] = 0
            self.method_stats['structured_observation_points'] = 0
            self.method_stats['structured_points'] = 0
            return []

        direct_points, station_contexts = self._extract_direct_coordinate_points(records)
        observation_points = self._extract_observation_points(records, station_contexts)
        structured_points = direct_points + observation_points

        self.method_stats['structured_direct_points'] = len(direct_points)
        self.method_stats['structured_observation_points'] = len(observation_points)
        self.method_stats['structured_points'] = len(structured_points)
        return structured_points

    def _iterate_structured_records(self, data: bytes) -> list[dict[str, Any]]:
        start = self._find_first_record_offset(data)
        if start is None:
            return []

        records: list[dict[str, Any]] = []
        pos = start
        while pos + 3 < len(data):
            if pos < 4:
                break
            length = struct.unpack('<I', data[pos - 4:pos])[0]
            if length <= 0 or pos + length > len(data):
                break

            payload = data[pos:pos + length]
            if len(payload) < 3 or payload[1] not in {0x30, 0x31, 0x33} or payload[2] != 0x2A:
                break

            records.append({
                'offset': pos,
                'length': length,
                'type_code': payload[1],
                'payload': payload,
            })
            pos = pos + length + 4

        return records

    def _find_first_record_offset(self, data: bytes) -> int | None:
        for pos in range(4, len(data) - 3):
            if data[pos + 1] not in {0x30, 0x31, 0x33} or data[pos + 2] != 0x2A:
                continue

            length = struct.unpack('<I', data[pos - 4:pos])[0]
            if 16 <= length <= len(data) - pos:
                return pos

        return None

    def _extract_direct_coordinate_points(
        self,
        records: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], dict[str, dict[str, float]]]:
        points: list[dict[str, Any]] = []
        station_contexts: dict[str, dict[str, float]] = {}

        for index, record in enumerate(records[:-1]):
            payload = record['payload']
            if record['type_code'] != 0x30 or b'KI' not in payload or b'F1&' in payload or b'BackSight' in payload:
                continue

            point_name = self._extract_name_before_marker(payload, b'KI')
            if not point_name:
                continue

            next_record = records[index + 1]
            next_payload = next_record['payload']
            if next_record['type_code'] != 0x33 or len(next_payload) < 48:
                continue

            x = struct.unpack('<d', next_payload[24:32])[0]
            y = struct.unpack('<d', next_payload[32:40])[0]
            z = struct.unpack('<d', next_payload[40:48])[0]
            if not self._is_reasonable_structured_coordinate(x, y, z):
                continue

            points.append({
                'point_id': point_name,
                'x': x,
                'y': y,
                'z': z,
                'offset': record['offset'],
                'strategy': 'structured_direct_coordinate',
            })
            station_contexts[point_name] = {
                'x': x,
                'y': y,
                'z': z,
                'instrument_height': 0.0,
            }

        if station_contexts:
            station_names = list(station_contexts.keys())
            for record in records:
                payload = record['payload']
                if record['type_code'] != 0x30 or len(payload) < 40:
                    continue

                for station_name in station_names:
                    marker = station_name.encode('ascii') + b'\x00'
                    marker_index = payload.find(marker)
                    if marker_index == -1:
                        continue

                    value_offset = marker_index + len(marker)
                    if value_offset + 8 > len(payload):
                        continue

                    value = struct.unpack('<d', payload[value_offset:value_offset + 8])[0]
                    if 0.1 < value < 5.0:
                        station_contexts[station_name]['instrument_height'] = value
                        break

        return points, station_contexts

    def _extract_observation_points(
        self,
        records: list[dict[str, Any]],
        station_contexts: dict[str, dict[str, float]],
    ) -> list[dict[str, Any]]:
        if not station_contexts:
            return []

        station_name, station = next(iter(station_contexts.items()))
        instrument_height = float(station.get('instrument_height', 0.0))
        points: list[dict[str, Any]] = []

        for index, record in enumerate(records[:-1]):
            payload = record['payload']
            if record['type_code'] != 0x30 or len(payload) not in {54, 55} or b'F1&' not in payload:
                continue

            point_name = self._extract_name_before_marker(payload, b'F1&')
            if not point_name or point_name == station_name:
                continue

            observation_record = records[index + 1]
            observation_payload = observation_record['payload']
            if observation_record['type_code'] != 0x33 or len(observation_payload) < 48:
                continue

            azimuth = struct.unpack('<d', observation_payload[24:32])[0]
            zenith = struct.unpack('<d', observation_payload[32:40])[0]
            slope_distance = struct.unpack('<d', observation_payload[40:48])[0]
            if not self._is_reasonable_observation(azimuth, zenith, slope_distance):
                continue

            horizontal_distance = slope_distance * math.sin(zenith)
            x = station['x'] + horizontal_distance * math.sin(azimuth)
            y = station['y'] + horizontal_distance * math.cos(azimuth)
            z = station['z'] + instrument_height + slope_distance * math.cos(zenith)
            if not self._is_reasonable_structured_coordinate(x, y, z):
                continue

            points.append({
                'point_id': point_name,
                'x': x,
                'y': y,
                'z': z,
                'offset': record['offset'],
                'strategy': 'structured_polar_observation',
            })

        return points

    def _extract_name_before_marker(self, record: bytes, marker: bytes) -> str:
        marker_index = record.find(marker)
        if marker_index == -1:
            return ''

        end = marker_index
        while end > 0 and record[end - 1] == 0:
            end -= 1

        start = end
        while start > 0 and 32 <= record[start - 1] < 127:
            start -= 1

        return record[start:end].decode('ascii', errors='ignore').strip()

    def _is_reasonable_structured_coordinate(self, x: float, y: float, z: float) -> bool:
        if not np.isfinite([x, y, z]).all():
            return False
        return abs(x) < 1_000_000 and abs(y) < 1_000_000 and abs(z) < 100_000

    def _is_reasonable_observation(self, azimuth: float, zenith: float, slope_distance: float) -> bool:
        if not np.isfinite([azimuth, zenith, slope_distance]).all():
            return False
        if not 0.0 <= azimuth <= (math.tau + 0.1):
            return False
        if not 0.0 <= zenith <= (math.pi + 0.1):
            return False
        return 0.01 <= slope_distance <= 1_000_000.0

    def _is_reasonable_triplet(self, x: float, y: float, z: float, max_abs: float) -> bool:
        if not np.isfinite([x, y, z]).all():
            return False
        if abs(x) >= max_abs or abs(y) >= max_abs or abs(z) >= max_abs:
            return False
        if abs(x) <= 0.01 and abs(y) <= 0.01:
            return False
        if abs(x - y) < 1e-6 and abs(y - z) < 1e-6:
            return False
        return abs(x) > 1.0 or abs(y) > 1.0 or abs(z) > 0.05

    def _scan_triplets(self, data: bytes, step: int, max_abs: float, label: str) -> list[dict[str, Any]]:
        points: list[dict[str, Any]] = []
        for offset in range(0, len(data) - 24, step):
            try:
                x = struct.unpack('<d', data[offset:offset + 8])[0]
                y = struct.unpack('<d', data[offset + 8:offset + 16])[0]
                z = struct.unpack('<d', data[offset + 16:offset + 24])[0]
            except Exception:
                continue
            if self._is_reasonable_triplet(x, y, z, max_abs=max_abs):
                points.append({
                    'point_id': f'PT_{len(points) + 1}',
                    'x': x,
                    'y': y,
                    'z': z,
                    'offset': offset,
                    'strategy': label,
                })
        self.method_stats[label] = len(points)
        return points

    def _scan_pattern_records(self, data: bytes) -> list[dict[str, Any]]:
        pattern = b'\x00\x00\x00\x03\x30\x2a'
        pos = 0
        points: list[dict[str, Any]] = []
        while True:
            pos = data.find(pattern, pos)
            if pos == -1:
                break
            search_start = pos + len(pattern)
            search_end = min(pos + 200, len(data))
            found = False
            for offset in range(search_start, search_end - 24, 4):
                try:
                    x = struct.unpack('<d', data[offset:offset + 8])[0]
                    y = struct.unpack('<d', data[offset + 8:offset + 16])[0]
                    z = struct.unpack('<d', data[offset + 16:offset + 24])[0]
                except Exception:
                    continue
                if self._is_reasonable_triplet(x, y, z, max_abs=10000.0):
                    points.append({
                        'point_id': f'PT_{len(points) + 1}',
                        'x': x,
                        'y': y,
                        'z': z,
                        'offset': offset,
                        'strategy': 'pattern_scan',
                    })
                    found = True
                    break
            pos += 1 if not found else len(pattern)
        self.method_stats['pattern_scan'] = len(points)
        return points

    def _deduplicate_points(self, points: list[dict[str, Any]]) -> list[dict[str, Any]]:
        unique_points: list[dict[str, Any]] = []
        for point in points:
            is_duplicate = False
            for existing in unique_points:
                if (
                    abs(point['x'] - existing['x']) < 0.001
                    and abs(point['y'] - existing['y']) < 0.001
                    and abs(point['z'] - existing['z']) < 0.001
                ):
                    is_duplicate = True
                    break
            if not is_duplicate:
                unique_points.append(point)
        self.method_stats['deduplicated_points'] = len(unique_points)
        return unique_points

    def _deduplicate_structured_points(self, points: list[dict[str, Any]]) -> list[dict[str, Any]]:
        unique_points: list[dict[str, Any]] = []
        seen_names: set[str] = set()
        for point in points:
            point_name = str(point.get('point_id', '')).strip()
            if point_name and point_name not in seen_names:
                unique_points.append(point)
                seen_names.add(point_name)
                continue

            is_duplicate = False
            for existing in unique_points:
                if (
                    abs(point['x'] - existing['x']) < 0.001
                    and abs(point['y'] - existing['y']) < 0.001
                    and abs(point['z'] - existing['z']) < 0.001
                ):
                    is_duplicate = True
                    break
            if not is_duplicate:
                unique_points.append(point)

        self.method_stats['deduplicated_points'] = len(unique_points)
        return unique_points

    def _attach_point_names(self, name_candidates: list[str]) -> None:
        for idx, point in enumerate(self.points):
            if idx < len(name_candidates):
                point['point_id'] = name_candidates[idx]
            else:
                point['point_id'] = point.get('point_id', f'PT_{idx + 1}')

    def _select_parser_strategy(
        self,
        structured_count: int,
        name_candidates: list[str],
        step8_count: int,
        step4_count: int,
        pattern_count: int,
    ) -> str:
        if structured_count:
            return "job_binary_structured_records"
        if step8_count >= max(step4_count, pattern_count) and len(name_candidates) >= max(1, step8_count // 2):
            return "job_binary_structured_triplets"
        if step8_count >= max(step4_count, pattern_count):
            return "job_binary_triplets_step8"
        if pattern_count >= step4_count:
            return "job_binary_pattern_scan"
        return "job_binary_triplets_step4"

    def _to_dataframe(self) -> pd.DataFrame:
        """Конвертирует точки в DataFrame"""
        df = pd.DataFrame(self.points)
        result = df[['x', 'y', 'z']].copy()
        result['name'] = df['point_id']
        annotated, annotation_details = _annotate_trimble_point_records(result)
        self.annotation_details = annotation_details
        return annotated


def _compare_point_sets(reference: pd.DataFrame, candidate: pd.DataFrame) -> dict[str, Any]:
    if reference.empty or candidate.empty:
        return {}
    ref_cols = {'x', 'y', 'z'}
    cand_cols = {'x', 'y', 'z'}
    if not ref_cols.issubset(reference.columns) or not cand_cols.issubset(candidate.columns):
        return {}

    candidate_xyz = candidate[['x', 'y', 'z']].to_numpy(dtype=float)
    distances: list[float] = []
    for _, ref_row in reference[['x', 'y', 'z']].iterrows():
        ref_point = ref_row.to_numpy(dtype=float)
        diff = candidate_xyz - ref_point
        norms = np.linalg.norm(diff, axis=1)
        if len(norms) > 0:
            distances.append(float(norms.min()))

    return {
        'reference_points': len(reference),
        'candidate_points': len(candidate),
        'mean_nearest_distance': round(float(np.mean(distances)), 6) if distances else None,
        'max_nearest_distance': round(float(np.max(distances)), 6) if distances else None,
        'point_count_delta': int(len(candidate) - len(reference)),
    }


def _find_paired_trimble_exports(file_path: str) -> list[Path]:
    path = Path(file_path)
    stem = path.stem.lower()
    candidates: list[Path] = []
    for sibling in path.parent.iterdir():
        if sibling == path or sibling.suffix.lower() not in {'.jxl', '.jobxml', '.xml'}:
            continue
        if sibling.stem.lower() == stem:
            candidates.append(sibling)
    return sorted(candidates)


def _build_trimble_loaded_data(
    file_path: str,
    data: pd.DataFrame,
    parser_strategy: str,
    warnings: list[str] | None = None,
    raw_records: int = 0,
    confidence: float = 1.0,
    details: dict[str, Any] | None = None,
) -> LoadedSurveyData:
    diagnostics = ImportDiagnostics(
        source_path=str(file_path),
        source_format=f"trimble_{Path(file_path).suffix.lower().lstrip('.')}",
        parser_strategy=parser_strategy,
        raw_records=int(raw_records or len(data)),
        accepted_points=len(data),
        discarded_points=max(int(raw_records or len(data)) - len(data), 0),
        confidence=float(confidence),
        warnings=list(warnings or []),
        details=dict(details or {}),
    )
    return LoadedSurveyData(
        data=data,
        epsg_code=None,
        source_format=diagnostics.source_format,
        parser_strategy=parser_strategy,
        warnings=list(diagnostics.warnings),
        confidence=float(confidence),
        diagnostics=diagnostics,
    )


def load_trimble_data_detailed(file_path: str) -> LoadedSurveyData:
    """
    Расширенная загрузка данных Trimble с диагностикой.
    """
    path = Path(file_path)
    ext = path.suffix.lower()

    if ext in ['.jxl', '.jobxml', '.xml']:
        loader = TrimbleJobXMLLoader(file_path)
        data = loader.load()
        details: dict[str, Any] = dict(loader.annotation_details)
        if loader.dedup_stats:
            details['dedup_stats'] = loader.dedup_stats
        return _build_trimble_loaded_data(
            file_path=file_path,
            data=data,
            parser_strategy=loader.parser_strategy,
            warnings=loader.warnings,
            raw_records=loader.raw_records or len(data),
            confidence=0.96,
            details=details,
        )

    if ext == '.csv':
        loader = TrimbleCSVLoader(file_path)
        data = loader.load()
        return _build_trimble_loaded_data(
            file_path=file_path,
            data=data,
            parser_strategy=loader.parser_strategy,
            warnings=loader.warnings,
            raw_records=loader.raw_records or len(data),
            confidence=0.9,
        )

    if ext == '.txt':
        loader = TrimbleTextLoader(file_path)
        data = loader.load()
        return _build_trimble_loaded_data(
            file_path=file_path,
            data=data,
            parser_strategy=loader.parser_strategy,
            warnings=loader.warnings,
            raw_records=loader.raw_records or len(data),
            confidence=0.88,
        )

    if ext == '.job':
        loader = TrimbleJobBinaryLoader(file_path)
        data: pd.DataFrame | None = None
        binary_error: Exception | None = None
        try:
            data = loader.load()
        except Exception as exc:
            binary_error = exc

        comparison_details: dict[str, Any] = {
            'method_stats': dict(loader.method_stats),
            'paired_exports': [],
        }
        comparison_details.update(getattr(loader, 'annotation_details', {}) or {})
        binary_warnings = list(loader.warnings)
        paired_exports = _find_paired_trimble_exports(file_path)
        if paired_exports:
            paired_loaded: tuple[Path, pd.DataFrame, TrimbleJobXMLLoader] | None = None
            warnings: list[str] = []
            for paired in paired_exports:
                try:
                    paired_loader = TrimbleJobXMLLoader(str(paired))
                    paired_data = paired_loader.load()
                    comparison = (
                        _compare_point_sets(paired_data, data)
                        if data is not None
                        else {
                            'reference_points': len(paired_data),
                            'candidate_points': 0,
                            'mean_nearest_distance': None,
                            'max_nearest_distance': None,
                            'point_count_delta': -len(paired_data),
                        }
                    )
                    comparison['paired_file'] = str(paired)
                    comparison_details['paired_exports'].append(comparison)
                    if paired_loaded is None:
                        paired_loaded = (paired, paired_data, paired_loader)
                except Exception as exc:
                    warnings.append(f"Не удалось сравнить JOB с парным экспортом {paired.name}: {exc}")
            if paired_loaded is not None:
                paired_file, paired_data, paired_loader = paired_loaded
                comparison_details['paired_export_used'] = str(paired_file)
                comparison_details['binary_parser_strategy'] = loader.parser_strategy
                comparison_details.update(getattr(paired_loader, 'annotation_details', {}) or {})
                if binary_error is not None:
                    warnings.append(
                        f"Встроенный парсер JOB не справился, поэтому использован парный экспорт {paired_file.name}."
                    )
                else:
                    warnings.append(
                        f"Для точного импорта JOB использован парный экспорт {paired_file.name}."
                    )
                return _build_trimble_loaded_data(
                    file_path=file_path,
                    data=paired_data,
                    parser_strategy='job_paired_jobxml_exact',
                    warnings=warnings,
                    raw_records=loader.raw_records or paired_loader.raw_records or len(paired_data),
                    confidence=0.99,
                    details=comparison_details,
                )
        else:
            warnings = list(binary_warnings)
            warnings.append("Парный JobXML/JobXML export для сверки JOB файла рядом не найден.")

        if data is None:
            raise binary_error if binary_error is not None else ValueError("Не удалось загрузить бинарный JOB файл")

        warnings = list(binary_warnings) + [w for w in locals().get('warnings', []) if w not in binary_warnings]

        confidence = 0.8 if loader.parser_strategy == 'job_binary_structured_records' else 0.55
        if comparison_details['paired_exports']:
            mean_distances = [
                item.get('mean_nearest_distance')
                for item in comparison_details['paired_exports']
                if item.get('mean_nearest_distance') is not None
            ]
            if mean_distances:
                confidence = 0.82 if min(mean_distances) <= 0.05 else 0.7

        return _build_trimble_loaded_data(
            file_path=file_path,
            data=data,
            parser_strategy=loader.parser_strategy,
            warnings=warnings,
            raw_records=loader.raw_records or len(data),
            confidence=confidence,
            details=comparison_details,
        )

    raise ValueError(f"Неизвестный формат Trimble файла: {ext}")


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

    return load_trimble_data_detailed(file_path).data

