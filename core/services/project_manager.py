"""
Менеджер проектов - управление сохранением и загрузкой проектов.

Формат v2.0: JSON-сериализация с поддержкой DataFrame, numpy-типов
и обратной совместимостью с pickle-файлами.
"""

import glob
import json
import logging
import math
import os
import time
from datetime import date, datetime
from typing import Any

import numpy as np
import pandas as pd

from core.exceptions import ProjectLoadError, ProjectSaveError

logger = logging.getLogger(__name__)

_DATAFRAME_MARKER = "__dataframe__"
_FORMAT_KEY = "__format__"
_FORMAT_JSON = "geovertical_json"


def _serialize_value(value: Any) -> Any:
    """Рекурсивно преобразует объект в JSON-сериализуемую структуру."""
    if value is None:
        return None
    if isinstance(value, pd.DataFrame):
        return {
            _DATAFRAME_MARKER: True,
            "columns": value.columns.tolist(),
            "data": value.reset_index(drop=True).to_dict(orient="list"),
            "dtypes": {col: str(dtype) for col, dtype in value.dtypes.items()},
        }
    if isinstance(value, pd.Series):
        return _serialize_value(value.to_frame())
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        v = float(value)
        if math.isnan(v):
            return None
        if math.isinf(v):
            return None
        return v
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {_serialize_key(k): _serialize_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize_value(item) for item in value]
    if isinstance(value, set):
        return [_serialize_value(item) for item in sorted(value)]
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
    return value


def _serialize_key(key: Any) -> str:
    """Ключи JSON должны быть строками."""
    if isinstance(key, (int, float, np.integer, np.floating)):
        return str(key)
    return str(key)


def _deserialize_value(value: Any) -> Any:
    """Рекурсивно восстанавливает объект из JSON-структуры."""
    if value is None:
        return None
    if isinstance(value, dict):
        if value.get(_DATAFRAME_MARKER):
            data = value.get("data", {})
            columns = value.get("columns", [])
            dtypes = value.get("dtypes", {})
            df = pd.DataFrame(data, columns=columns)
            for col, dtype_str in dtypes.items():
                if col in df.columns:
                    try:
                        if "float" in dtype_str or "int" in dtype_str:
                            df[col] = pd.to_numeric(df[col], errors="coerce")
                        elif dtype_str == "bool":
                            df[col] = df[col].astype(bool)
                    except (ValueError, TypeError):
                        pass
            return df
        return {k: _deserialize_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_deserialize_value(item) for item in value]
    return value


class ProjectManager:
    """
    Менеджер проектов для управления сохранением и загрузкой проектов GeoVertical.

    Формат v2.0: JSON с версионированием.
    Обратная совместимость: чтение pickle-файлов (v1.x).
    """

    PROJECT_VERSION = '2.0'
    AUTOSAVE_DIR = os.path.join(os.path.expanduser('~'), '.geovertical', 'autosave')
    AUTOSAVE_KEEP_COUNT = 5
    AUTOSAVE_MAX_AGE_HOURS = 24

    def __init__(self):
        self.current_project_path: str | None = None
        self.current_file_path: str | None = None
        self.tower_builder_state: dict[str, Any] | None = None
        self.import_context: dict[str, Any] | None = None
        self.import_diagnostics: dict[str, Any] | None = None
        self.transformation_audit: dict[str, Any] | None = None
        os.makedirs(self.AUTOSAVE_DIR, exist_ok=True)

    def save_project(
        self,
        file_path: str,
        raw_data: pd.DataFrame,
        processed_data: dict[str, Any] | None,
        epsg_code: int | None,
        current_file_path: str | None,
        original_data_before_sections: pd.DataFrame | None,
        height_tolerance: float,
        center_method: str,
        expected_belt_count: int | None,
        tower_faces_count: int | None,
        xy_plane_state: Any | None = None,
        section_data: Any | None = None,
        tower_builder_state: dict[str, Any] | None = None,
        full_report_state: dict[str, Any] | None = None,
        undo_history: dict[str, Any] | None = None,
        import_context: dict[str, Any] | None = None,
        import_diagnostics: dict[str, Any] | None = None,
        transformation_audit: dict[str, Any] | None = None,
    ) -> None:
        """Сохраняет проект в файл (формат JSON v2.0)."""
        try:
            project_data = {
                _FORMAT_KEY: _FORMAT_JSON,
                'version': self.PROJECT_VERSION,
                'raw_data': raw_data,
                'processed_data': processed_data,
                'epsg_code': epsg_code,
                'current_file_path': current_file_path,
                'original_data_before_sections': original_data_before_sections,
                'height_tolerance': height_tolerance,
                'center_method': center_method,
                'expected_belt_count': expected_belt_count,
                'tower_faces_count': tower_faces_count,
                'xy_plane_state': xy_plane_state,
                'section_data': section_data,
                'tower_builder_state': tower_builder_state,
                'full_report_state': full_report_state,
                'undo_history': undo_history,
                'import_context': import_context,
                'import_diagnostics': import_diagnostics,
                'transformation_audit': transformation_audit,
            }

            serialized = _serialize_value(project_data)

            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(serialized, f, ensure_ascii=False, indent=None, default=str)

            self.current_project_path = file_path
            self.tower_builder_state = tower_builder_state
            self.import_context = import_context
            self.import_diagnostics = import_diagnostics
            self.transformation_audit = transformation_audit
            logger.info(f"Проект сохранен: {file_path}")

        except (OSError, TypeError, ValueError) as e:
            raise ProjectSaveError(f"Ошибка сохранения проекта: {e!s}") from e

    def load_project(self, file_path: str) -> dict[str, Any]:
        """Загружает проект из файла (JSON v2.0 или pickle v1.x)."""
        try:
            project_data = self._try_load_json(file_path)
            if project_data is None:
                project_data = self._try_load_pickle(file_path)

            if project_data is None:
                raise ProjectLoadError("Не удалось загрузить проект: неизвестный формат файла")

            version = project_data.get('version', '1.0')
            project_data = self._migrate(project_data, version)

            self.current_project_path = file_path
            self.tower_builder_state = project_data.get('tower_builder_state')
            self.import_context = project_data.get('import_context')
            self.import_diagnostics = project_data.get('import_diagnostics')
            self.transformation_audit = project_data.get('transformation_audit')
            logger.info(f"Проект загружен: {file_path} (версия {version})")

            return project_data

        except ProjectLoadError:
            raise
        except Exception as e:
            raise ProjectLoadError(f"Ошибка загрузки проекта: {e!s}") from e

    @staticmethod
    def _try_load_json(file_path: str) -> dict[str, Any] | None:
        """Пробует загрузить файл как JSON."""
        try:
            with open(file_path, encoding='utf-8') as f:
                first_char = f.read(1)
                if first_char != '{':
                    return None
                f.seek(0)
                raw = json.load(f)
            if not isinstance(raw, dict) or raw.get(_FORMAT_KEY) != _FORMAT_JSON:
                return None
            return _deserialize_value(raw)
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            return None

    @staticmethod
    def _try_load_pickle(file_path: str) -> dict[str, Any] | None:
        """Пробует загрузить файл как pickle (обратная совместимость)."""
        try:
            import pickle
            with open(file_path, 'rb') as f:
                data = pickle.load(f)
            if isinstance(data, dict):
                logger.info("Загружен проект в устаревшем pickle-формате, при сохранении будет конвертирован в JSON")
                return data
            return None
        except Exception:
            return None

    @staticmethod
    def _migrate(data: dict[str, Any], version: str) -> dict[str, Any]:
        """Миграция данных проекта между версиями."""
        if version < '1.3':
            if 'import_context' not in data:
                data['import_context'] = None
            if 'import_diagnostics' not in data:
                data['import_diagnostics'] = None
            if 'transformation_audit' not in data:
                data['transformation_audit'] = None
        if version < '2.0':
            if 'undo_history' not in data:
                data['undo_history'] = None
            if 'full_report_state' not in data:
                data['full_report_state'] = None
        data['version'] = ProjectManager.PROJECT_VERSION
        return data

    def save_autosave(
        self,
        raw_data: pd.DataFrame,
        processed_data: dict[str, Any] | None,
        epsg_code: int | None,
        current_file_path: str | None,
        original_data_before_sections: pd.DataFrame | None,
        height_tolerance: float,
        center_method: str,
        expected_belt_count: int | None,
        tower_faces_count: int | None,
        xy_plane_state: Any | None = None,
        section_data: Any | None = None,
        tower_builder_state: dict[str, Any] | None = None,
        full_report_state: dict[str, Any] | None = None,
        undo_history: dict[str, Any] | None = None,
        import_context: dict[str, Any] | None = None,
        import_diagnostics: dict[str, Any] | None = None,
        transformation_audit: dict[str, Any] | None = None,
    ) -> str | None:
        """Сохраняет автосохранение во временный файл."""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            autosave_file = os.path.join(self.AUTOSAVE_DIR, f'autosave_{timestamp}.gvproj')

            self.save_project(
                autosave_file,
                raw_data,
                processed_data,
                epsg_code,
                current_file_path,
                original_data_before_sections,
                height_tolerance,
                center_method,
                expected_belt_count,
                tower_faces_count,
                xy_plane_state,
                section_data,
                tower_builder_state,
                full_report_state,
                undo_history,
                import_context,
                import_diagnostics,
                transformation_audit,
            )

            self._cleanup_old_autosaves()
            logger.debug(f"Автосохранение выполнено: {autosave_file}")
            return autosave_file

        except Exception as e:
            logger.warning(f"Ошибка автосохранения: {e}")
            return None

    def get_latest_autosave(self) -> str | None:
        """Получает путь к последнему файлу автосохранения."""
        try:
            if not os.path.exists(self.AUTOSAVE_DIR):
                return None

            pattern = os.path.join(self.AUTOSAVE_DIR, 'autosave_*.gvproj')
            autosave_files = glob.glob(pattern)

            if not autosave_files:
                return None

            autosave_files.sort(key=os.path.getmtime, reverse=True)
            latest_autosave = autosave_files[0]

            file_age_hours = (time.time() - os.path.getmtime(latest_autosave)) / 3600
            if file_age_hours > self.AUTOSAVE_MAX_AGE_HOURS:
                logger.info("Автосохранение слишком старое, пропускаем")
                return None

            return latest_autosave

        except Exception as e:
            logger.warning(f"Ошибка при поиске автосохранения: {e}")
            return None

    def _cleanup_old_autosaves(self):
        """Удаляет старые файлы автосохранения, оставляя только последние."""
        try:
            pattern = os.path.join(self.AUTOSAVE_DIR, 'autosave_*.gvproj')
            autosave_files = glob.glob(pattern)

            if len(autosave_files) <= self.AUTOSAVE_KEEP_COUNT:
                return

            autosave_files.sort(key=os.path.getmtime, reverse=True)

            for old_file in autosave_files[self.AUTOSAVE_KEEP_COUNT:]:
                try:
                    os.remove(old_file)
                    logger.debug(f"Удален старый файл автосохранения: {old_file}")
                except Exception as e:
                    logger.warning(f"Не удалось удалить старый файл автосохранения {old_file}: {e}")

        except Exception as e:
            logger.warning(f"Ошибка при очистке старых автосохранений: {e}")

    def get_project_name(self) -> str:
        """Получает имя текущего проекта."""
        if self.current_project_path:
            return os.path.basename(self.current_project_path)
        return "Новый проект"
