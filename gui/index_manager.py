"""
Модуль для централизованного управления индексами точек.

Предоставляет единый API для работы с различными типами индексов:
- Позиция (position) - числовой индекс от 0 до len(data)-1 (iloc)
- Индекс DataFrame (dataframe_index) - индекс строки в DataFrame (at/loc)
- Point Index (point_index) - уникальный идентификатор точки в столбце point_index

Решает проблемы:
- Смешанного использования типов индексов
- Отсутствия валидации индексов
- Дублирования логики поиска точек
- Неэффективных множественных обращений к DataFrame
"""

from typing import Optional, Any, Dict, List
import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)


class IndexManager:
    """
    Централизованный менеджер индексов для работы с точками.
    
    Управляет конвертацией между различными типами индексов и предоставляет
    безопасный доступ к данным точек с валидацией и кэшированием.
    """
    
    def __init__(self, data: Optional[pd.DataFrame] = None):
        """
        Инициализация менеджера индексов.
        
        Args:
            data: DataFrame с данными точек. Должен содержать столбец 'point_index'.
        """
        self.data: Optional[pd.DataFrame] = None
        self._position_to_point_index: Dict[int, int] = {}
        self._point_index_to_position: Dict[int, int] = {}
        self._point_index_to_dataframe_index: Dict[int, Any] = {}
        self._dataframe_index_to_point_index: Dict[Any, int] = {}
        self._cache_valid = False
        
        if data is not None:
            self.set_data(data)
    
    def set_data(self, data: pd.DataFrame) -> None:
        """
        Установить новые данные и обновить маппинги.
        
        Args:
            data: DataFrame с данными точек
        """
        self.data = data.copy() if data is not None else None
        self._cache_valid = False
        self._rebuild_cache()
    
    def _rebuild_cache(self) -> None:
        """Перестроить кэш маппингов между типами индексов."""
        if self.data is None or self.data.empty:
            self._position_to_point_index.clear()
            self._point_index_to_position.clear()
            self._point_index_to_dataframe_index.clear()
            self._dataframe_index_to_point_index.clear()
            self._cache_valid = True
            return
        
        self._position_to_point_index.clear()
        self._point_index_to_position.clear()
        self._point_index_to_dataframe_index.clear()
        self._dataframe_index_to_point_index.clear()
        
        if 'point_index' not in self.data.columns:
            logger.warning("DataFrame не содержит столбец 'point_index'. Кэш будет пустым.")
            self._cache_valid = True
            return
        
        # Строим маппинги
        for position, (dataframe_idx, row) in enumerate(self.data.iterrows()):
            try:
                point_idx_value = row.get('point_index')
                if pd.notna(point_idx_value):
                    point_idx = int(point_idx_value)
                    
                    # Позиция <-> point_index
                    self._position_to_point_index[position] = point_idx
                    self._point_index_to_position[point_idx] = position
                    
                    # point_index <-> dataframe_index
                    self._point_index_to_dataframe_index[point_idx] = dataframe_idx
                    self._dataframe_index_to_point_index[dataframe_idx] = point_idx
            except (ValueError, TypeError) as e:
                logger.debug(f"Не удалось обработать точку на позиции {position}: {e}")
                continue
        
        self._cache_valid = True
        logger.debug(f"Кэш перестроен: {len(self._point_index_to_position)} точек")
    
    def invalidate_cache(self) -> None:
        """Инвалидировать кэш (будет перестроен при следующем обращении)."""
        self._cache_valid = False
    
    def get_point_by_position(self, pos: int) -> Optional[pd.Series]:
        """
        Получить точку по позиции (0-based индекс).
        
        Args:
            pos: Позиция точки (от 0 до len(data)-1)
            
        Returns:
            Series с данными точки или None, если позиция невалидна
        """
        if not self.validate_index(pos, 'position'):
            return None
        
        try:
            return self.data.iloc[pos]
        except (IndexError, KeyError) as e:
            logger.debug(f"Ошибка доступа к позиции {pos}: {e}")
            return None
    
    def get_point_by_dataframe_index(self, idx: Any) -> Optional[pd.Series]:
        """
        Получить точку по индексу DataFrame.
        
        Args:
            idx: Индекс строки в DataFrame
            
        Returns:
            Series с данными точки или None, если индекс невалиден
        """
        if not self.validate_index(idx, 'dataframe_index'):
            return None
        
        try:
            return self.data.loc[idx]
        except (KeyError, IndexError) as e:
            logger.debug(f"Ошибка доступа к индексу DataFrame {idx}: {e}")
            return None
    
    def get_point_by_point_index(self, point_idx: int) -> Optional[pd.Series]:
        """
        Получить точку по point_index.
        
        Args:
            point_idx: Уникальный идентификатор точки из столбца point_index
            
        Returns:
            Series с данными точки или None, если point_index не найден
        """
        if not self.validate_index(point_idx, 'point_index'):
            return None
        
        position = self.find_position_by_point_index(point_idx)
        if position is None:
            return None
        
        return self.get_point_by_position(position)
    
    def find_position_by_point_index(self, point_idx: int) -> Optional[int]:
        """
        Найти позицию точки по point_index.
        
        Args:
            point_idx: Уникальный идентификатор точки
            
        Returns:
            Позиция точки или None, если не найдена
        """
        if not self._cache_valid:
            self._rebuild_cache()
        
        return self._point_index_to_position.get(point_idx)
    
    def find_dataframe_index_by_point_index(self, point_idx: int) -> Optional[Any]:
        """
        Найти индекс DataFrame по point_index.
        
        Args:
            point_idx: Уникальный идентификатор точки
            
        Returns:
            Индекс DataFrame или None, если не найден
        """
        if not self._cache_valid:
            self._rebuild_cache()
        
        return self._point_index_to_dataframe_index.get(point_idx)
    
    def find_point_index_by_position(self, pos: int) -> Optional[int]:
        """
        Найти point_index по позиции.
        
        Args:
            pos: Позиция точки (0-based)
            
        Returns:
            point_index или None, если не найден
        """
        if not self._cache_valid:
            self._rebuild_cache()
        
        return self._position_to_point_index.get(pos)
    
    def find_point_index_by_dataframe_index(self, idx: Any) -> Optional[int]:
        """
        Найти point_index по индексу DataFrame.
        
        Args:
            idx: Индекс DataFrame
            
        Returns:
            point_index или None, если не найден
        """
        if not self._cache_valid:
            self._rebuild_cache()
        
        return self._dataframe_index_to_point_index.get(idx)
    
    def validate_index(self, idx: Any, index_type: str = 'auto') -> bool:
        """
        Проверить валидность индекса.
        
        Args:
            idx: Индекс для проверки
            index_type: Тип индекса ('position', 'dataframe_index', 'point_index', 'auto')
                       В режиме 'auto' определяется тип автоматически
            
        Returns:
            True, если индекс валиден, False иначе
        """
        if self.data is None or self.data.empty:
            return False
        
        if index_type == 'auto':
            # Автоматическое определение типа
            if isinstance(idx, int):
                # Проверяем как position
                if 0 <= idx < len(self.data):
                    return True
                # Проверяем как point_index
                if not self._cache_valid:
                    self._rebuild_cache()
                if idx in self._point_index_to_position:
                    return True
                # Проверяем как dataframe_index
                try:
                    if idx in self.data.index:
                        return True
                except (TypeError, ValueError):
                    pass
            else:
                # Проверяем как dataframe_index
                try:
                    if idx in self.data.index:
                        return True
                except (TypeError, ValueError):
                    pass
        
        elif index_type == 'position':
            if isinstance(idx, int) and 0 <= idx < len(self.data):
                return True
        
        elif index_type == 'dataframe_index':
            try:
                return idx in self.data.index
            except (TypeError, ValueError):
                return False
        
        elif index_type == 'point_index':
            if isinstance(idx, int):
                if not self._cache_valid:
                    self._rebuild_cache()
                return idx in self._point_index_to_position
        
        return False
    
    def get_point_index(self, idx: Any, index_type: str = 'auto') -> Optional[int]:
        """
        Получить point_index из любого типа индекса.
        
        Args:
            idx: Индекс (любого типа)
            index_type: Тип индекса ('position', 'dataframe_index', 'point_index', 'auto')
            
        Returns:
            point_index или None, если не найден
        """
        if index_type == 'auto':
            # Пробуем определить тип автоматически
            if isinstance(idx, int):
                # Сначала проверяем как point_index
                if self.validate_index(idx, 'point_index'):
                    return idx
                # Потом как position
                if self.validate_index(idx, 'position'):
                    return self.find_point_index_by_position(idx)
                # Потом как dataframe_index
                if self.validate_index(idx, 'dataframe_index'):
                    return self.find_point_index_by_dataframe_index(idx)
            else:
                # Проверяем как dataframe_index
                if self.validate_index(idx, 'dataframe_index'):
                    return self.find_point_index_by_dataframe_index(idx)
        
        elif index_type == 'position':
            return self.find_point_index_by_position(idx)
        
        elif index_type == 'dataframe_index':
            return self.find_point_index_by_dataframe_index(idx)
        
        elif index_type == 'point_index':
            if self.validate_index(idx, 'point_index'):
                return idx
        
        return None
    
    def get_all_point_indices(self) -> List[int]:
        """
        Получить список всех point_index в данных.
        
        Returns:
            Список point_index
        """
        if not self._cache_valid:
            self._rebuild_cache()
        
        return sorted(self._point_index_to_position.keys())
    
    def get_dataframe_index_by_position(self, pos: int) -> Optional[Any]:
        """
        Получить индекс DataFrame по позиции.
        
        Args:
            pos: Позиция точки
            
        Returns:
            Индекс DataFrame или None
        """
        if not self.validate_index(pos, 'position'):
            return None
        
        try:
            return self.data.index[pos]
        except (IndexError, KeyError):
            return None
    
    def normalize_to_point_index(self, idx: Any, index_type: str = 'auto') -> Optional[int]:
        """
        Нормализовать любой тип индекса в point_index.
        
        Это универсальный метод для конвертации любого типа индекса в point_index.
        Используется для унификации работы с индексами между компонентами.
        
        Args:
            idx: Индекс любого типа (position, dataframe_index, point_index)
            index_type: Тип индекса ('position', 'dataframe_index', 'point_index', 'auto')
                       В режиме 'auto' определяется тип автоматически
            
        Returns:
            point_index или None, если не удалось нормализовать
        """
        if self.data is None or self.data.empty:
            return None
        
        # Если уже point_index, возвращаем как есть
        if index_type == 'point_index' or (index_type == 'auto' and self.validate_index(idx, 'point_index')):
            return int(idx) if isinstance(idx, (int, float)) else None
        
        # Используем существующий метод get_point_index
        return self.get_point_index(idx, index_type)
    
    def normalize_to_position(self, idx: Any, index_type: str = 'auto') -> Optional[int]:
        """
        Нормализовать любой тип индекса в позицию (0-based).
        
        Это универсальный метод для конвертации любого типа индекса в позицию.
        Используется для работы с selected_indices в 3D редакторе.
        
        Args:
            idx: Индекс любого типа (position, dataframe_index, point_index)
            index_type: Тип индекса ('position', 'dataframe_index', 'point_index', 'auto')
                       В режиме 'auto' определяется тип автоматически
            
        Returns:
            Позиция (0-based) или None, если не удалось нормализовать
        """
        if self.data is None or self.data.empty:
            return None
        
        if not self._cache_valid:
            self._rebuild_cache()
        
        # Если уже позиция, возвращаем как есть
        if index_type == 'position' or (index_type == 'auto' and self.validate_index(idx, 'position')):
            return int(idx) if isinstance(idx, (int, float)) and 0 <= int(idx) < len(self.data) else None
        
        # Конвертируем через point_index для надежности
        point_idx = self.normalize_to_point_index(idx, index_type)
        if point_idx is not None:
            position = self.find_position_by_point_index(point_idx)
            if position is not None:
                return position
        
        # Fallback: если передан dataframe_index, конвертируем напрямую
        if index_type == 'dataframe_index' or (index_type == 'auto' and self.validate_index(idx, 'dataframe_index')):
            try:
                position = list(self.data.index).index(idx)
                return position
            except (ValueError, TypeError):
                pass
        
        return None

