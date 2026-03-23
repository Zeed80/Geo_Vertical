"""
Модуль загрузки геоданных из различных форматов
"""

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from core.exceptions import (
    DataLoadError,
    DataValidationError,
    FieldGeniusError,
    FieldGeniusParsingError,
    FileFormatError,
    TrimbleError,
    TrimbleParsingError,
)
from core.import_models import ImportDiagnostics, LoadedSurveyData

logger = logging.getLogger(__name__)

try:
    from core.trimble_loader import load_trimble_data, load_trimble_data_detailed
    TRIMBLE_AVAILABLE = True
except ImportError:
    TRIMBLE_AVAILABLE = False

try:
    from core.fieldgenius_loader import (
        FieldGeniusDBFLoader,
        FieldGeniusINILoader,
        FieldGeniusProjectLoader,
        FieldGeniusRAWLoader,
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
        self.parser_strategy = ""
        self.warnings: list[str] = []
        self.fallback_chain: list[str] = []
        self.raw_records = 0
        self.discarded_reasons: dict[str, int] = {}

    def load(self) -> pd.DataFrame:
        """Загружает данные из файла"""
        raise NotImplementedError

    def detect_format(self) -> str:
        """Определяет формат файла"""
        return self.file_path.suffix.lower()

    def _record_warning(self, message: str) -> None:
        if message and message not in self.warnings:
            self.warnings.append(message)

    def _record_fallback(self, name: str) -> None:
        if name and name not in self.fallback_chain:
            self.fallback_chain.append(name)


class CSVLoader(DataLoader):
    """Загрузчик CSV файлов"""

    def load(self) -> pd.DataFrame:
        """
        Загружает данные из CSV

        Ожидаемые колонки: x, y, z (или X, Y, Z, или Height)
        """
        try:
            df = None
            selected_sep = None
            # Пробуем разные разделители
            for sep in [',', ';', '\t']:
                try:
                    candidate = pd.read_csv(self.file_path, sep=sep)
                except (OSError, pd.errors.EmptyDataError, pd.errors.ParserError) as e:
                    logger.debug(f"Не удалось прочитать CSV с разделителем '{sep}': {e}")
                    self._record_fallback(f"csv_sep_{sep}")
                    continue

                if candidate.empty and len(candidate.columns) == 0:
                    continue

                if len(candidate.columns) >= 3:
                    df = candidate
                    selected_sep = sep
                    break

            if df is None:
                raise FileFormatError("Не удалось прочитать CSV: неизвестный формат или неверный разделитель")
            self.raw_records = len(df)
            self.parser_strategy = f"csv_sep_{selected_sep or 'unknown'}"

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
            before_dropna = len(result)
            result = result.dropna()
            dropped_count = before_dropna - len(result)
            if dropped_count > 0:
                self.discarded_reasons['invalid_numeric_rows'] = dropped_count
                self._record_warning(
                    f"При импорте CSV отброшено {dropped_count} строк с некорректными координатами."
                )

            # Пробуем извлечь EPSG из метаданных (если есть)
            self._try_extract_epsg(df)

            self.data = result
            return result

        except (FileFormatError, DataValidationError):
            raise
        except (OSError, pd.errors.EmptyDataError, pd.errors.ParserError, ValueError) as e:
            raise DataLoadError(f"Ошибка загрузки CSV: {e!s}") from e

    def _find_column(self, df: pd.DataFrame, names: list) -> str | None:
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
            self.raw_records = len(gdf)
            self.parser_strategy = "geojson_geopandas"

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
            discarded = max(self.raw_records - len(result), 0)
            if discarded:
                self.discarded_reasons['non_point_features'] = discarded
                self._record_warning(
                    f"При импорте GeoJSON пропущено {discarded} объектов без корректной точечной геометрии."
                )
            self.data = result
            return result

        except ImportError as e:
            raise DataLoadError("Для работы с GeoJSON требуется установить geopandas") from e
        except (OSError, ValueError, KeyError, AttributeError) as e:
            raise DataLoadError(f"Ошибка загрузки GeoJSON: {e!s}") from e


class ShapefileLoader(DataLoader):
    """Загрузчик Shapefile"""

    def load(self) -> pd.DataFrame:
        """Загружает данные из Shapefile"""
        try:
            import geopandas as gpd

            # Загружаем Shapefile
            gdf = gpd.read_file(self.file_path)
            self.raw_records = len(gdf)
            self.parser_strategy = "shapefile_geopandas"

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
            discarded = max(self.raw_records - len(result), 0)
            if discarded:
                self.discarded_reasons['non_point_features'] = discarded
                self._record_warning(
                    f"При импорте Shapefile пропущено {discarded} объектов без корректной точечной геометрии."
                )
            self.data = result
            return result

        except ImportError as e:
            raise DataLoadError("Для работы с Shapefile требуется установить geopandas") from e
        except (OSError, ValueError, KeyError, AttributeError) as e:
            raise DataLoadError(f"Ошибка загрузки Shapefile: {e!s}") from e


class DXFLoader(DataLoader):
    """Загрузчик DXF файлов"""

    def load(self) -> pd.DataFrame:
        """Загружает данные из DXF"""
        try:
            import ezdxf

            # Загружаем DXF
            doc = ezdxf.readfile(self.file_path)
            msp = doc.modelspace()
            self.parser_strategy = "dxf_point_and_insert_scan"

            # Извлекаем точки
            points = []
            entity_count = 0
            for entity in msp:
                entity_count += 1
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
                    self._record_fallback("dxf_insert_entities")
            self.raw_records = entity_count

            if not points:
                raise DataValidationError("В DXF не найдено точек")

            result = pd.DataFrame(points)
            self.data = result
            return result

        except ImportError as e:
            raise DataLoadError("Для работы с DXF требуется установить ezdxf") from e
        except (OSError, ValueError, AttributeError) as e:
            raise DataLoadError(f"Ошибка загрузки DXF: {e!s}") from e
        except Exception as e:
            # Обработка специфичных ошибок ezdxf
            import ezdxf
            if isinstance(e, (ezdxf.DXFStructureError, ezdxf.DXFValueError)):
                error_msg = f"Ошибка структуры DXF файла: {e!s}"
                logger.error(error_msg, exc_info=True)
                raise DataLoadError(error_msg) from e
            error_msg = f"Неожиданная ошибка загрузки DXF: {type(e).__name__}: {e!s}"
            logger.error(error_msg, exc_info=True)
            raise DataLoadError(error_msg) from e


from core.point_utils import build_is_station_mask as _build_station_mask


def _build_standing_candidates(data: pd.DataFrame, top_n: int = 3) -> list[dict[str, Any]]:
    if data is None or data.empty or not {'x', 'y', 'z'}.issubset(data.columns):
        return []

    candidates: list[dict[str, Any]] = []
    if 'is_station' in data.columns:
        station_mask = _build_station_mask(data['is_station'])
        station_rows = data[station_mask]
        for idx, row in station_rows.head(top_n).iterrows():
            candidates.append({
                'index': int(idx) if isinstance(idx, (int, np.integer)) else str(idx),
                'name': str(row.get('name', f'Точка {idx}')),
                'reason': 'explicit_station_flag',
                'score': 1.0,
                'x': float(row.get('x', 0.0)),
                'y': float(row.get('y', 0.0)),
                'z': float(row.get('z', 0.0)),
            })
        if candidates:
            return candidates

    work = data[['x', 'y', 'z']].dropna().copy()
    if len(work) < 2:
        return []

    centroid_xy = work[['x', 'y']].median().to_numpy(dtype=float)
    coords_xy = work[['x', 'y']].to_numpy(dtype=float)
    if len(coords_xy) == 1:
        return []

    nearest_distances: list[tuple[Any, float, float]] = []
    for idx, row in data.iterrows():
        point_xy = np.array([row.get('x', np.nan), row.get('y', np.nan)], dtype=float)
        if not np.isfinite(point_xy).all():
            continue
        diffs = coords_xy - point_xy
        distances = np.linalg.norm(diffs, axis=1)
        non_zero = distances[distances > 1e-9]
        nearest = float(non_zero.min()) if len(non_zero) > 0 else 0.0
        centroid_distance = float(np.linalg.norm(point_xy - centroid_xy))
        nearest_distances.append((idx, nearest, centroid_distance))

    nearest_distances.sort(key=lambda item: (item[1], item[2]), reverse=True)
    for idx, nearest, centroid_distance in nearest_distances[:top_n]:
        row = data.loc[idx]
        score = nearest + centroid_distance * 0.25
        candidates.append({
            'index': int(idx) if isinstance(idx, (int, np.integer)) else str(idx),
            'name': str(row.get('name', f'Точка {idx}')),
            'reason': 'isolation_heuristic',
            'score': round(float(score), 6),
            'nearest_neighbor_distance': round(nearest, 6),
            'distance_from_centroid': round(centroid_distance, 6),
            'x': float(row.get('x', 0.0)),
            'y': float(row.get('y', 0.0)),
            'z': float(row.get('z', 0.0)),
        })

    return candidates


def _build_duplicate_stats(data: pd.DataFrame) -> dict[str, Any]:
    if data is None or data.empty or not {'x', 'y', 'z'}.issubset(data.columns):
        return {'duplicate_points': 0, 'duplicate_groups': 0}
    rounded = data[['x', 'y', 'z']].round(6)
    duplicates_mask = rounded.duplicated(keep=False)
    duplicate_groups = rounded[duplicates_mask].value_counts().to_dict()
    return {
        'duplicate_points': int(duplicates_mask.sum()),
        'duplicate_groups': len(duplicate_groups),
    }


def _build_belt_summary(data: pd.DataFrame) -> dict[str, Any]:
    if data is None or data.empty or 'belt' not in data.columns:
        return {'has_belts': False, 'count': 0}
    belts = data['belt'].dropna()
    if belts.empty:
        return {'has_belts': False, 'count': 0}
    summary: dict[str, Any] = {
        'has_belts': True,
        'count': int(belts.nunique()),
        'distribution': {str(k): int(v) for k, v in belts.value_counts().sort_index().to_dict().items()},
    }
    numeric_belts = pd.to_numeric(belts, errors='coerce').dropna().astype(int)
    if not numeric_belts.empty:
        sorted_unique = sorted(numeric_belts.unique().tolist())
        expected = list(range(sorted_unique[0], sorted_unique[-1] + 1))
        summary['continuous_numbering'] = sorted_unique == expected
        summary['missing_numbers'] = [num for num in expected if num not in sorted_unique]
    return summary


def _build_tower_part_summary(data: pd.DataFrame) -> dict[str, Any]:
    if data is None or data.empty:
        return {'has_parts': False, 'count': 0}
    memberships_multi = 0
    if 'tower_part_memberships' in data.columns:
        for value in data['tower_part_memberships'].dropna():
            try:
                decoded = json.loads(value) if isinstance(value, str) else value
            except Exception:
                decoded = []
            if isinstance(decoded, list) and len(decoded) > 1:
                memberships_multi += 1
    if 'tower_part' not in data.columns:
        return {'has_parts': memberships_multi > 0, 'count': 0, 'multi_membership_points': memberships_multi}
    parts = data['tower_part'].dropna()
    if parts.empty and memberships_multi == 0:
        return {'has_parts': False, 'count': 0}
    distribution = {str(k): int(v) for k, v in parts.value_counts().sort_index().to_dict().items()} if not parts.empty else {}
    return {
        'has_parts': True,
        'count': int(parts.nunique()) if not parts.empty else 0,
        'distribution': distribution,
        'multi_membership_points': int(memberships_multi),
    }


def _estimate_import_confidence(
    data: pd.DataFrame,
    raw_records: int,
    warning_count: int,
    duplicate_stats: dict[str, Any],
    explicit_confidence: float | None = None,
) -> float:
    if explicit_confidence is not None:
        return float(max(0.0, min(1.0, explicit_confidence)))
    confidence = 1.0
    if raw_records > 0 and len(data) < raw_records:
        confidence -= min(0.25, (raw_records - len(data)) / max(raw_records, 1))
    confidence -= min(0.35, warning_count * 0.08)
    duplicate_points = int(duplicate_stats.get('duplicate_points', 0) or 0)
    if len(data) > 0 and duplicate_points > 0:
        confidence -= min(0.15, duplicate_points / max(len(data), 1) * 0.2)
    return float(max(0.1, min(1.0, confidence)))


def _create_loaded_survey_data(
    data: pd.DataFrame,
    file_path: str,
    source_format: str,
    parser_strategy: str,
    epsg_code: int | None = None,
    warnings: list[str] | None = None,
    raw_records: int = 0,
    discarded_reasons: dict[str, int] | None = None,
    fallback_chain: list[str] | None = None,
    details: dict[str, Any] | None = None,
    confidence: float | None = None,
    transformation_quality: dict[str, Any] | None = None,
) -> LoadedSurveyData:
    warnings = list(warnings or [])
    duplicate_stats = _build_duplicate_stats(data)
    diagnostics = ImportDiagnostics(
        source_path=str(file_path),
        source_format=source_format,
        parser_strategy=parser_strategy,
        raw_records=int(raw_records or len(data)),
        accepted_points=len(data),
        discarded_points=max(int(raw_records or len(data)) - len(data), 0),
        warnings=warnings,
        fallback_chain=list(fallback_chain or []),
        discarded_reasons=dict(discarded_reasons or {}),
        standing_point_candidates=_build_standing_candidates(data),
        duplicate_stats=duplicate_stats,
        belt_summary=_build_belt_summary(data),
        tower_part_summary=_build_tower_part_summary(data),
        transformation_quality=dict(transformation_quality or {}),
        details=dict(details or {}),
    )
    diagnostics.confidence = _estimate_import_confidence(
        data,
        diagnostics.raw_records,
        len(diagnostics.warnings),
        duplicate_stats,
        explicit_confidence=confidence,
    )
    return LoadedSurveyData(
        data=data,
        epsg_code=epsg_code,
        source_format=source_format,
        parser_strategy=parser_strategy,
        warnings=warnings,
        confidence=diagnostics.confidence,
        diagnostics=diagnostics,
    )


def load_survey_data(file_path: str) -> LoadedSurveyData:
    """
    Автоматически определяет формат и загружает данные с расширенной диагностикой.
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
            loaded = load_trimble_data_detailed(file_path)
            if not loaded.diagnostics.source_path:
                loaded.diagnostics.source_path = str(file_path)
            if not loaded.source_format:
                loaded.source_format = f"trimble_{extension.lstrip('.')}"
            if not loaded.parser_strategy:
                loaded.parser_strategy = loaded.diagnostics.parser_strategy
            if not loaded.warnings:
                loaded.warnings = list(loaded.diagnostics.warnings)
            return loaded
        except NotImplementedError:
            # Для .job файлов выводим сообщение с инструкцией
            raise
        except (TrimbleError, TrimbleParsingError, OSError) as e:
            # Если не удалось загрузить как Trimble, пробуем другие загрузчики
            if extension == '.txt':
                pass  # Попробуем стандартный CSVLoader
            else:
                raise TrimbleError(f"Ошибка загрузки Trimble файла: {e!s}") from e

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
                    return _create_loaded_survey_data(
                        data=data,
                        file_path=file_path,
                        source_format='fieldgenius_project',
                        parser_strategy='fieldgenius_project_loader',
                        epsg_code=loader.epsg_code,
                        raw_records=len(data),
                    )
            except (FieldGeniusError, FieldGeniusParsingError, OSError) as e:
                logger.debug(f"Не удалось загрузить как проект FieldGenius: {e}")
                # Продолжаем с другими загрузчиками

        # Обработка .ini файлов (проекты FieldGenius)
        if extension == '.ini':
            try:
                loader = FieldGeniusProjectLoader(file_path)
                data = loader.load()
                return _create_loaded_survey_data(
                    data=data,
                    file_path=file_path,
                    source_format='fieldgenius_ini',
                    parser_strategy='fieldgenius_ini_loader',
                    epsg_code=loader.epsg_code,
                    raw_records=len(data),
                )
            except (FieldGeniusError, FieldGeniusParsingError, OSError) as e:
                raise FieldGeniusError(f"Ошибка загрузки проекта FieldGenius из INI: {e!s}") from e

        # Обработка .dbf файлов (базы данных FieldGenius)
        if extension == '.dbf':
            try:
                loader = FieldGeniusDBFLoader(file_path)
                data = loader.load()
                return _create_loaded_survey_data(
                    data=data,
                    file_path=file_path,
                    source_format='fieldgenius_dbf',
                    parser_strategy='fieldgenius_dbf_loader',
                    epsg_code=loader.epsg_code,
                    raw_records=len(data),
                )
            except (FieldGeniusError, FieldGeniusParsingError, OSError) as e:
                raise FieldGeniusError(f"Ошибка загрузки FieldGenius DBF файла: {e!s}") from e

        # Обработка .raw файлов (RAW данные FieldGenius)
        if extension == '.raw':
            try:
                loader = FieldGeniusRAWLoader(file_path)
                # Проверяем, что это действительно FieldGenius файл
                if loader._is_fieldgenius_file():
                    data = loader.load()
                    return _create_loaded_survey_data(
                        data=data,
                        file_path=file_path,
                        source_format='fieldgenius_raw',
                        parser_strategy='fieldgenius_raw_loader',
                        epsg_code=loader.epsg_code,
                        raw_records=len(data),
                    )
                else:
                    # Если не FieldGenius, пробуем другие загрузчики или выдаем ошибку
                    raise FileFormatError("Файл .raw не является FieldGenius форматом")
            except (FieldGeniusError, FieldGeniusParsingError, OSError) as e:
                raise FieldGeniusError(f"Ошибка загрузки FieldGenius RAW файла: {e!s}") from e

    loader_class = loader_map.get(extension)
    if not loader_class:
        raise FileFormatError(f"Неподдерживаемый формат файла: {extension}")

    loader = loader_class(file_path)
    data = loader.load()
    return _create_loaded_survey_data(
        data=data,
        file_path=file_path,
        source_format=extension.lstrip('.'),
        parser_strategy=loader.parser_strategy or f"{extension.lstrip('.')}_loader",
        epsg_code=loader.epsg_code,
        warnings=loader.warnings,
        raw_records=loader.raw_records or len(data),
        discarded_reasons=loader.discarded_reasons,
        fallback_chain=loader.fallback_chain,
    )


def load_data_from_file(file_path: str) -> tuple[pd.DataFrame, int | None]:
    """
    Совместимый слой поверх расширенного контракта импорта.
    """
    loaded = load_survey_data(file_path)
    return loaded.data, loaded.epsg_code


def validate_data(data: pd.DataFrame, check_outliers: bool = True) -> tuple[bool, str]:
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
