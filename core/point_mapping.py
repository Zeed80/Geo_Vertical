"""
Модуль для управления соответствием индексов между таблицами UI и данными.

Решает проблему несоответствия индексов таблицы и данных при фильтрации,
сортировке или других операциях с данными.
"""

from typing import Dict, Optional, Any
import logging

logger = logging.getLogger(__name__)


class PointMapping:
    """
    Класс для отслеживания соответствия между индексами таблицы UI и данными.
    
    Обеспечивает двунаправленное соответствие:
    - table_row -> data_index: получение индекса данных по строке таблицы
    - data_index -> table_row: получение строки таблицы по индексу данных
    
    Также поддерживает уникальные идентификаторы (name, ID) для дополнительной
    валидации и поиска точек.
    
    Пример использования:
        mapping = PointMapping()
        mapping.add_mapping(table_row=0, data_index=5, point_name="Точка_1")
        data_idx = mapping.get_data_index(0)  # Вернет 5
        table_row = mapping.get_table_row(5)   # Вернет 0
    """
    
    def __init__(self):
        """Инициализация пустого mapping"""
        # Двунаправленное соответствие: table_row -> data_index
        self.table_to_data: Dict[int, Any] = {}
        # Обратное соответствие: data_index -> table_row
        self.data_to_table: Dict[Any, int] = {}
        # Дополнительная информация: data_index -> point_name
        self.data_to_name: Dict[Any, str] = {}
        # Обратное соответствие: point_name -> data_index (для поиска по имени)
        self.name_to_data: Dict[str, Any] = {}
    
    def add_mapping(self, table_row: int, data_index: Any, point_name: Optional[str] = None):
        """
        Добавить соответствие между строкой таблицы и индексом данных.
        
        Args:
            table_row: Номер строки в таблице UI (начинается с 0)
            data_index: Индекс точки в данных (может быть int, str или другой тип)
            point_name: Опциональное имя точки для дополнительной валидации
        
        Raises:
            ValueError: Если table_row уже используется или data_index уже замаплен
        """
        if table_row in self.table_to_data:
            existing_data_idx = self.table_to_data[table_row]
            if existing_data_idx != data_index:
                logger.warning(
                    f"Перезапись mapping для table_row={table_row}: "
                    f"старый data_index={existing_data_idx}, новый={data_index}"
                )
                # Удаляем старое соответствие
                if existing_data_idx in self.data_to_table:
                    del self.data_to_table[existing_data_idx]
                if existing_data_idx in self.data_to_name:
                    old_name = self.data_to_name[existing_data_idx]
                    if old_name in self.name_to_data and self.name_to_data[old_name] == existing_data_idx:
                        del self.name_to_data[old_name]
                    del self.data_to_name[existing_data_idx]
        
        if data_index in self.data_to_table:
            existing_table_row = self.data_to_table[data_index]
            if existing_table_row != table_row:
                logger.warning(
                    f"Перезапись mapping для data_index={data_index}: "
                    f"старый table_row={existing_table_row}, новый={table_row}"
                )
                # Удаляем старое соответствие
                if existing_table_row in self.table_to_data:
                    del self.table_to_data[existing_table_row]
        
        # Добавляем новое соответствие
        self.table_to_data[table_row] = data_index
        self.data_to_table[data_index] = table_row
        
        # Сохраняем имя, если указано
        if point_name is not None:
            self.data_to_name[data_index] = point_name
            self.name_to_data[point_name] = data_index
    
    def get_data_index(self, table_row: int) -> Optional[Any]:
        """
        Получить индекс данных по номеру строки таблицы.
        
        Args:
            table_row: Номер строки в таблице UI
        
        Returns:
            Индекс точки в данных или None, если соответствие не найдено
        """
        return self.table_to_data.get(table_row)
    
    def get_table_row(self, data_index: Any) -> Optional[int]:
        """
        Получить номер строки таблицы по индексу данных.
        
        Args:
            data_index: Индекс точки в данных
        
        Returns:
            Номер строки в таблице UI или None, если соответствие не найдено
        """
        return self.data_to_table.get(data_index)
    
    def get_data_index_by_name(self, point_name: str) -> Optional[Any]:
        """
        Получить индекс данных по имени точки.
        
        Args:
            point_name: Имя точки
        
        Returns:
            Индекс точки в данных или None, если точка не найдена
        """
        return self.name_to_data.get(point_name)
    
    def get_point_name(self, data_index: Any) -> Optional[str]:
        """
        Получить имя точки по индексу данных.
        
        Args:
            data_index: Индекс точки в данных
        
        Returns:
            Имя точки или None, если имя не сохранено
        """
        return self.data_to_name.get(data_index)
    
    def has_mapping(self, table_row: int) -> bool:
        """
        Проверить, есть ли соответствие для данной строки таблицы.
        
        Args:
            table_row: Номер строки в таблице UI
        
        Returns:
            True, если соответствие существует
        """
        return table_row in self.table_to_data
    
    def has_data_index(self, data_index: Any) -> bool:
        """
        Проверить, есть ли соответствие для данного индекса данных.
        
        Args:
            data_index: Индекс точки в данных
        
        Returns:
            True, если соответствие существует
        """
        return data_index in self.data_to_table
    
    def remove_mapping(self, table_row: Optional[int] = None, data_index: Optional[Any] = None):
        """
        Удалить соответствие.
        
        Можно удалить либо по table_row, либо по data_index, либо оба должны быть указаны
        для валидации.
        
        Args:
            table_row: Номер строки в таблице UI (опционально)
            data_index: Индекс точки в данных (опционально)
        
        Raises:
            ValueError: Если не указан ни table_row, ни data_index
        """
        if table_row is None and data_index is None:
            raise ValueError("Необходимо указать либо table_row, либо data_index")
        
        # Если указан только table_row, находим data_index
        if table_row is not None and data_index is None:
            data_index = self.table_to_data.get(table_row)
            if data_index is None:
                logger.warning(f"Не найдено соответствие для table_row={table_row}")
                return
        
        # Если указан только data_index, находим table_row
        if data_index is not None and table_row is None:
            table_row = self.data_to_table.get(data_index)
            if table_row is None:
                logger.warning(f"Не найдено соответствие для data_index={data_index}")
                return
        
        # Валидация: проверяем, что соответствие корректно
        if table_row is not None and data_index is not None:
            if self.table_to_data.get(table_row) != data_index:
                logger.warning(
                    f"Несоответствие при удалении: table_row={table_row} -> "
                    f"data_index={self.table_to_data.get(table_row)}, "
                    f"ожидался {data_index}"
                )
        
        # Удаляем соответствие
        if table_row is not None and table_row in self.table_to_data:
            del self.table_to_data[table_row]
        
        if data_index is not None:
            if data_index in self.data_to_table:
                del self.data_to_table[data_index]
            if data_index in self.data_to_name:
                point_name = self.data_to_name[data_index]
                if point_name in self.name_to_data and self.name_to_data[point_name] == data_index:
                    del self.name_to_data[point_name]
                del self.data_to_name[data_index]
    
    def clear(self):
        """Очистить все соответствия"""
        self.table_to_data.clear()
        self.data_to_table.clear()
        self.data_to_name.clear()
        self.name_to_data.clear()
    
    def size(self) -> int:
        """Получить количество соответствий"""
        return len(self.table_to_data)
    
    def get_all_table_rows(self) -> list:
        """Получить список всех номеров строк таблицы"""
        return list(self.table_to_data.keys())
    
    def get_all_data_indices(self) -> list:
        """Получить список всех индексов данных"""
        return list(self.data_to_table.keys())
    
    def validate(self) -> tuple[bool, list[str]]:
        """
        Валидировать целостность соответствий.
        
        Проверяет:
        - Двунаправленная согласованность (table_row -> data_index и обратно)
        - Отсутствие дубликатов
        
        Returns:
            Кортеж (is_valid, list_of_errors):
            - is_valid: True, если все соответствия валидны
            - list_of_errors: Список найденных ошибок
        """
        errors = []
        
        # Проверяем двунаправленную согласованность
        for table_row, data_index in self.table_to_data.items():
            reverse_table_row = self.data_to_table.get(data_index)
            if reverse_table_row != table_row:
                errors.append(
                    f"Несогласованность: table_row={table_row} -> data_index={data_index}, "
                    f"но data_index={data_index} -> table_row={reverse_table_row}"
                )
        
        # Проверяем обратную согласованность
        for data_index, table_row in self.data_to_table.items():
            reverse_data_index = self.table_to_data.get(table_row)
            if reverse_data_index != data_index:
                errors.append(
                    f"Несогласованность: data_index={data_index} -> table_row={table_row}, "
                    f"но table_row={table_row} -> data_index={reverse_data_index}"
                )
        
        # Проверяем дубликаты в table_to_data
        seen_table_rows = set()
        for table_row in self.table_to_data.keys():
            if table_row in seen_table_rows:
                errors.append(f"Дубликат table_row: {table_row}")
            seen_table_rows.add(table_row)
        
        # Проверяем дубликаты в data_to_table
        seen_data_indices = set()
        for data_index in self.data_to_table.keys():
            if data_index in seen_data_indices:
                errors.append(f"Дубликат data_index: {data_index}")
            seen_data_indices.add(data_index)
        
        is_valid = len(errors) == 0
        return is_valid, errors

