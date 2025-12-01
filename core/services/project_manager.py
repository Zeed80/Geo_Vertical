"""
Менеджер проектов - управление сохранением и загрузкой проектов
"""

import pickle
import os
import glob
import time
import logging
from typing import Optional, Dict, Any
from pathlib import Path
import pandas as pd

from core.exceptions import ProjectSaveError, ProjectLoadError

logger = logging.getLogger(__name__)


class ProjectManager:
    """
    Менеджер проектов для управления сохранением и загрузкой проектов GeoVertical
    
    Отвечает за:
    - Сохранение проектов в файлы .gvproj
    - Загрузку проектов из файлов
    - Автосохранение
    - Восстановление после сбоя
    """
    
    PROJECT_VERSION = '1.2'
    AUTOSAVE_DIR = os.path.join(os.path.expanduser('~'), '.geovertical', 'autosave')
    AUTOSAVE_KEEP_COUNT = 5  # Количество автосохранений для хранения
    AUTOSAVE_MAX_AGE_HOURS = 24  # Максимальный возраст автосохранения для восстановления
    
    def __init__(self):
        """Инициализация менеджера проектов"""
        self.current_project_path: Optional[str] = None
        self.current_file_path: Optional[str] = None
        self.tower_builder_state: Optional[Dict[str, Any]] = None
        
        # Создаем директорию для автосохранения
        os.makedirs(self.AUTOSAVE_DIR, exist_ok=True)
    
    def save_project(
        self,
        file_path: str,
        raw_data: pd.DataFrame,
        processed_data: Optional[Dict[str, Any]],
        epsg_code: Optional[int],
        current_file_path: Optional[str],
        original_data_before_sections: Optional[pd.DataFrame],
        height_tolerance: float,
        center_method: str,
        expected_belt_count: Optional[int],
        tower_faces_count: Optional[int],
        xy_plane_state: Optional[Any] = None,
        section_data: Optional[Any] = None,
        tower_builder_state: Optional[Dict[str, Any]] = None,
        full_report_state: Optional[Dict[str, Any]] = None,
        undo_history: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Сохраняет проект в файл
        
        Args:
            file_path: Путь для сохранения проекта
            raw_data: Исходные данные
            processed_data: Результаты расчетов
            epsg_code: EPSG код системы координат
            current_file_path: Путь к исходному файлу данных
            original_data_before_sections: Данные до создания секций
            height_tolerance: Допуск по высоте
            center_method: Метод расчета центра
            expected_belt_count: Ожидаемое количество поясов
            tower_faces_count: Количество граней башни
            xy_plane_state: Состояние XY плоскости в 3D редакторе
            section_data: Данные секций
            
        Raises:
            ProjectSaveError: При ошибке сохранения
        """
        try:
            project_data = {
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
            }
            
            with open(file_path, 'wb') as f:
                pickle.dump(project_data, f)
            
            self.current_project_path = file_path
            self.tower_builder_state = tower_builder_state
            logger.info(f"Проект сохранен: {file_path}")
            
        except (IOError, OSError, pickle.PickleError, AttributeError) as e:
            raise ProjectSaveError(f"Ошибка сохранения проекта: {str(e)}") from e
    
    def load_project(self, file_path: str) -> Dict[str, Any]:
        """
        Загружает проект из файла
        
        Args:
            file_path: Путь к файлу проекта
            
        Returns:
            Словарь с данными проекта
            
        Raises:
            ProjectLoadError: При ошибке загрузки
        """
        try:
            with open(file_path, 'rb') as f:
                project_data = pickle.load(f)
            
            # Проверяем версию
            version = project_data.get('version', '1.0')
            if version != self.PROJECT_VERSION:
                logger.warning(f"Загружен проект версии {version}, текущая версия {self.PROJECT_VERSION}")
            
            self.current_project_path = file_path
            self.tower_builder_state = project_data.get('tower_builder_state')
            logger.info(f"Проект загружен: {file_path}")
            
            return project_data
            
        except (IOError, OSError, pickle.UnpicklingError, AttributeError, KeyError, ValueError) as e:
            raise ProjectLoadError(f"Ошибка загрузки проекта: {str(e)}") from e
    
    def save_autosave(
        self,
        raw_data: pd.DataFrame,
        processed_data: Optional[Dict[str, Any]],
        epsg_code: Optional[int],
        current_file_path: Optional[str],
        original_data_before_sections: Optional[pd.DataFrame],
        height_tolerance: float,
        center_method: str,
        expected_belt_count: Optional[int],
        tower_faces_count: Optional[int],
        xy_plane_state: Optional[Any] = None,
        section_data: Optional[Any] = None,
        tower_builder_state: Optional[Dict[str, Any]] = None,
        full_report_state: Optional[Dict[str, Any]] = None,
        undo_history: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """
        Сохраняет автосохранение во временный файл
        
        Returns:
            Путь к файлу автосохранения или None при ошибке
        """
        try:
            from datetime import datetime
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
            )
            
            # Очищаем старые автосохранения
            self._cleanup_old_autosaves()
            
            logger.debug(f"Автосохранение выполнено: {autosave_file}")
            return autosave_file
            
        except Exception as e:
            logger.warning(f"Ошибка автосохранения: {e}")
            return None
    
    def get_latest_autosave(self) -> Optional[str]:
        """
        Получает путь к последнему файлу автосохранения
        
        Returns:
            Путь к файлу или None, если автосохранений нет
        """
        try:
            if not os.path.exists(self.AUTOSAVE_DIR):
                return None
            
            pattern = os.path.join(self.AUTOSAVE_DIR, 'autosave_*.gvproj')
            autosave_files = glob.glob(pattern)
            
            if not autosave_files:
                return None
            
            # Сортируем по времени модификации (новый первым)
            autosave_files.sort(key=os.path.getmtime, reverse=True)
            latest_autosave = autosave_files[0]
            
            # Проверяем возраст файла
            file_age_hours = (time.time() - os.path.getmtime(latest_autosave)) / 3600
            if file_age_hours > self.AUTOSAVE_MAX_AGE_HOURS:
                logger.info("Автосохранение слишком старое, пропускаем")
                return None
            
            return latest_autosave
            
        except Exception as e:
            logger.warning(f"Ошибка при поиске автосохранения: {e}")
            return None
    
    def _cleanup_old_autosaves(self):
        """Удаляет старые файлы автосохранения, оставляя только последние"""
        try:
            pattern = os.path.join(self.AUTOSAVE_DIR, 'autosave_*.gvproj')
            autosave_files = glob.glob(pattern)
            
            if len(autosave_files) <= self.AUTOSAVE_KEEP_COUNT:
                return
            
            # Сортируем по времени модификации (новые первыми)
            autosave_files.sort(key=os.path.getmtime, reverse=True)
            
            # Удаляем старые файлы
            for old_file in autosave_files[self.AUTOSAVE_KEEP_COUNT:]:
                try:
                    os.remove(old_file)
                    logger.debug(f"Удален старый файл автосохранения: {old_file}")
                except Exception as e:
                    logger.warning(f"Не удалось удалить старый файл автосохранения {old_file}: {e}")
                    
        except Exception as e:
            logger.warning(f"Ошибка при очистке старых автосохранений: {e}")
    
    def get_project_name(self) -> str:
        """Получает имя текущего проекта"""
        if self.current_project_path:
            return os.path.basename(self.current_project_path)
        return "Новый проект"

