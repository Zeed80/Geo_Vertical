"""
Система Undo/Redo для отмены и повтора операций
Реализует паттерн Command
"""

import copy
import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


class Command(ABC):
    """Базовый класс команды"""

    @abstractmethod
    def execute(self) -> bool:
        """Выполняет команду"""
        pass

    @abstractmethod
    def undo(self) -> bool:
        """Отменяет команду"""
        pass

    @abstractmethod
    def get_description(self) -> str:
        """Возвращает описание команды"""
        pass


class UndoManager:
    """
    Менеджер для управления историей команд Undo/Redo

    Хранит стек команд для отмены и повтора операций
    """

    def __init__(self, max_history_size: int = 50):
        """
        Инициализация менеджера

        Args:
            max_history_size: Максимальный размер истории команд
        """
        self.max_history_size = max_history_size
        self.undo_stack: list[Command] = []
        self.redo_stack: list[Command] = []
        self._executing = False  # Флаг для предотвращения рекурсии

    def execute_command(self, command: Command) -> bool:
        """
        Выполняет команду и добавляет её в историю

        Args:
            command: Команда для выполнения

        Returns:
            True если команда выполнена успешно
        """
        if self._executing:
            return False

        try:
            self._executing = True

            if command.execute():
                # Добавляем в стек отмены
                self.undo_stack.append(command)

                # Ограничиваем размер стека
                if len(self.undo_stack) > self.max_history_size:
                    self.undo_stack.pop(0)

                # Очищаем стек повтора при новой команде
                self.redo_stack.clear()

                logger.info(f"Команда выполнена: {command.get_description()}, стек undo: {len(self.undo_stack)}")
                return True
            else:
                logger.warning(f"Команда не выполнена: {command.get_description()}")
                return False

        finally:
            self._executing = False

    def undo(self) -> bool:
        """
        Отменяет последнюю команду

        Returns:
            True если команда отменена успешно
        """
        if not self.can_undo():
            return False

        if self._executing:
            return False

        try:
            self._executing = True

            command = self.undo_stack.pop()
            logger.info(f"Отменяем команду: {command.get_description()}, тип: {type(command).__name__}")
            if command.undo():
                self.redo_stack.append(command)
                logger.info(f"Команда отменена успешно: {command.get_description()}, redo_stack_len={len(self.redo_stack)}")
                return True
            else:
                # Возвращаем команду обратно в стек при ошибке
                self.undo_stack.append(command)
                logger.error(f"Не удалось отменить команду: {command.get_description()}")
                return False

        finally:
            self._executing = False

    def redo(self) -> bool:
        """
        Повторяет последнюю отмененную команду

        Returns:
            True если команда повторена успешно
        """
        if not self.can_redo():
            return False

        if self._executing:
            return False

        try:
            self._executing = True

            command = self.redo_stack.pop()
            logger.info(f"Повторяем команду: {command.get_description()}, тип: {type(command).__name__}")
            if command.execute():
                self.undo_stack.append(command)
                logger.info(f"Команда повторена успешно: {command.get_description()}, undo_stack_len={len(self.undo_stack)}")
                return True
            else:
                # Возвращаем команду обратно в стек при ошибке
                self.redo_stack.append(command)
                logger.error(f"Не удалось повторить команду: {command.get_description()}")
                return False

        finally:
            self._executing = False

    def can_undo(self) -> bool:
        """Проверяет, можно ли отменить команду"""
        return len(self.undo_stack) > 0 and not self._executing

    def can_redo(self) -> bool:
        """Проверяет, можно ли повторить команду"""
        return len(self.redo_stack) > 0 and not self._executing

    def clear(self):
        """Очищает всю историю"""
        self.undo_stack.clear()
        self.redo_stack.clear()
        logger.debug("История команд очищена")

    def get_undo_description(self) -> str | None:
        """Возвращает описание последней команды для отмены"""
        if self.can_undo():
            return self.undo_stack[-1].get_description()
        return None

    def get_redo_description(self) -> str | None:
        """Возвращает описание последней команды для повтора"""
        if self.can_redo():
            return self.redo_stack[-1].get_description()
        return None

    def serialize(self) -> dict[str, Any]:
        """
        Сериализует историю undo/redo в словарь для сохранения

        Returns:
            Словарь с сериализованными стеками команд
        """
        import base64
        import pickle

        def serialize_command_stack(stack: list[Command]) -> list[dict[str, Any]]:
            """Сериализует стек команд"""
            serialized = []
            for cmd in stack:
                cmd_dict = {
                    'type': cmd.__class__.__name__,
                    'description': cmd.get_description(),
                }

                # Для разных типов команд сохраняем разные данные
                if isinstance(cmd, TowerBlueprintApplyCommand):
                    # Сохраняем все данные команды
                    cmd_dict['old_raw_data'] = cmd.old_raw_data
                    cmd_dict['old_processed_data'] = cmd.old_processed_data
                    cmd_dict['old_original_data_before_sections'] = cmd.old_original_data_before_sections
                    cmd_dict['old_tower_blueprint'] = cmd.old_tower_blueprint.to_dict() if cmd.old_tower_blueprint else None
                    cmd_dict['old_epsg_code'] = cmd.old_epsg_code
                    cmd_dict['old_height_tolerance'] = cmd.old_height_tolerance
                    cmd_dict['old_center_method'] = cmd.old_center_method
                    cmd_dict['old_expected_belt_count'] = cmd.old_expected_belt_count
                    cmd_dict['old_tower_faces_count'] = cmd.old_tower_faces_count
                    cmd_dict['old_section_data'] = cmd.old_section_data
                    cmd_dict['old_xy_plane_state'] = cmd.old_xy_plane_state
                    cmd_dict['new_blueprint'] = cmd.new_blueprint.to_dict() if cmd.new_blueprint else None
                elif isinstance(cmd, DataChangeCommand):
                    # Для DataChangeCommand сохраняем данные
                    cmd_dict['old_data'] = cmd.old_data
                    cmd_dict['new_data'] = cmd.new_data
                elif isinstance(cmd, EditorStateCommand):
                    cmd_dict['old_state'] = cmd.old_state
                    cmd_dict['new_state'] = cmd.new_state
                    cmd_dict['skip_initial_execute'] = cmd._skip_initial_execute
                elif isinstance(cmd, MainWindowStateCommand):
                    cmd_dict['old_state'] = cmd.old_state
                    cmd_dict['new_state'] = cmd.new_state
                    cmd_dict['skip_initial_execute'] = cmd._skip_initial_execute
                elif isinstance(cmd, RowAddCommand):
                    # Для RowAddCommand сохраняем данные строки
                    cmd_dict['row_data'] = cmd.row_data
                    cmd_dict['row_index'] = cmd.row_index
                elif isinstance(cmd, RowDeleteCommand):
                    # Для RowDeleteCommand сохраняем удаленные строки
                    cmd_dict['deleted_rows'] = cmd.deleted_rows
                    cmd_dict['row_indices'] = cmd.row_indices
                elif isinstance(cmd, CellEditCommand):
                    # Для CellEditCommand сохраняем значения
                    cmd_dict['row_index'] = cmd.row_index
                    cmd_dict['column_name'] = cmd.column_name
                    cmd_dict['old_value'] = cmd.old_value
                    cmd_dict['new_value'] = cmd.new_value

                # Сериализуем DataFrame через pickle и base64
                serialized_cmd = {}
                for key, value in cmd_dict.items():
                    if value is None:
                        serialized_cmd[key] = None
                    elif isinstance(value, pd.DataFrame):
                        # Сериализуем DataFrame
                        pickled = pickle.dumps(value)
                        serialized_cmd[key] = {
                            '_type': 'DataFrame',
                            '_data': base64.b64encode(pickled).decode('utf-8')
                        }
                    elif isinstance(value, pd.Series):
                        # Сериализуем Series
                        pickled = pickle.dumps(value)
                        serialized_cmd[key] = {
                            '_type': 'Series',
                            '_data': base64.b64encode(pickled).decode('utf-8')
                        }
                    else:
                        # Для других типов (списки, словари и т.д.) pickle будет использован в ProjectManager
                        serialized_cmd[key] = value

                serialized.append(serialized_cmd)

            return serialized

        return {
            'undo_stack': serialize_command_stack(self.undo_stack),
            'redo_stack': serialize_command_stack(self.redo_stack),
            'max_history_size': self.max_history_size,
        }

    def deserialize(self, data: dict[str, Any], main_window=None) -> bool:
        """
        Восстанавливает историю undo/redo из словаря

        Args:
            data: Словарь с сериализованными стеками команд
            main_window: Ссылка на главное окно (нужна для восстановления команд)

        Returns:
            True если история восстановлена успешно
        """
        import base64
        import pickle

        try:
            self.undo_stack.clear()
            self.redo_stack.clear()

            if 'max_history_size' in data:
                self.max_history_size = data['max_history_size']

            def deserialize_value(value: Any) -> Any:
                """Десериализует значение"""
                if isinstance(value, dict) and '_type' in value and '_data' in value:
                    if value['_type'] == 'DataFrame' or value['_type'] == 'Series':
                        pickled = base64.b64decode(value['_data'].encode('utf-8'))
                        return pickle.loads(pickled)
                return value

            def deserialize_command(cmd_dict: dict[str, Any], main_window_ref) -> Command | None:
                """Десериализует команду"""
                cmd_type = cmd_dict.get('type')
                if not cmd_type:
                    return None

                if cmd_type == 'TowerBlueprintApplyCommand':
                    if main_window_ref is None:
                        logger.warning("Не удалось восстановить TowerBlueprintApplyCommand: нет ссылки на main_window")
                        return None

                    # Восстанавливаем blueprint
                    from core.tower_generator import TowerBlueprint
                    new_blueprint_dict = cmd_dict.get('new_blueprint')
                    if new_blueprint_dict:
                        new_blueprint = TowerBlueprint.from_dict(new_blueprint_dict)
                    else:
                        logger.warning("Не удалось восстановить blueprint из команды")
                        return None

                    # Создаем команду без сохранения состояния (при восстановлении из файла)
                    # Временно сохраняем текущее состояние, чтобы команда могла быть создана
                    cmd = TowerBlueprintApplyCommand.__new__(TowerBlueprintApplyCommand)
                    cmd.main_window = main_window_ref
                    cmd.new_blueprint = new_blueprint
                    cmd.description = cmd_dict.get('description', 'Применение blueprint башни')

                    # Восстанавливаем сохраненные данные напрямую
                    cmd.old_raw_data = deserialize_value(cmd_dict.get('old_raw_data'))
                    # processed_data может быть сложной структурой, но pickle в ProjectManager должен его правильно восстановить
                    cmd.old_processed_data = cmd_dict.get('old_processed_data')
                    cmd.old_original_data_before_sections = deserialize_value(cmd_dict.get('old_original_data_before_sections'))
                    # section_data может быть списком словарей, но pickle в ProjectManager должен его правильно восстановить

                    old_blueprint_dict = cmd_dict.get('old_tower_blueprint')
                    if old_blueprint_dict:
                        cmd.old_tower_blueprint = TowerBlueprint.from_dict(old_blueprint_dict)
                    else:
                        cmd.old_tower_blueprint = None

                    cmd.old_epsg_code = cmd_dict.get('old_epsg_code')
                    cmd.old_height_tolerance = cmd_dict.get('old_height_tolerance')
                    cmd.old_center_method = cmd_dict.get('old_center_method')
                    cmd.old_expected_belt_count = cmd_dict.get('old_expected_belt_count')
                    cmd.old_tower_faces_count = cmd_dict.get('old_tower_faces_count')
                    cmd.old_section_data = cmd_dict.get('old_section_data')
                    cmd.old_xy_plane_state = cmd_dict.get('old_xy_plane_state')

                    return cmd

                elif cmd_type == 'DataChangeCommand':
                    # Для DataChangeCommand нужны функции getter/setter, которые мы не можем восстановить
                    # Поэтому пропускаем такие команды при загрузке
                    logger.warning("DataChangeCommand не может быть восстановлена при загрузке проекта")
                    return None

                elif cmd_type == 'EditorStateCommand':
                    if main_window_ref is None:
                        logger.warning("Не удалось восстановить EditorStateCommand: нет ссылки на main_window")
                        return None

                    cmd = EditorStateCommand.__new__(EditorStateCommand)
                    cmd.main_window = main_window_ref
                    cmd.old_state = cmd_dict.get('old_state') or {}
                    cmd.new_state = cmd_dict.get('new_state') or {}
                    if hasattr(main_window_ref, '_normalize_editor_undo_state'):
                        cmd.old_state = main_window_ref._normalize_editor_undo_state(cmd.old_state)
                        cmd.new_state = main_window_ref._normalize_editor_undo_state(cmd.new_state)
                    cmd.description = cmd_dict.get('description', 'Изменение в 3D-редакторе')
                    cmd._skip_initial_execute = bool(cmd_dict.get('skip_initial_execute', False))
                    return cmd

                elif cmd_type == 'MainWindowStateCommand':
                    if main_window_ref is None:
                        logger.warning("Не удалось восстановить MainWindowStateCommand: нет ссылки на main_window")
                        return None

                    cmd = MainWindowStateCommand.__new__(MainWindowStateCommand)
                    cmd.main_window = main_window_ref
                    cmd.old_state = cmd_dict.get('old_state') or {}
                    cmd.new_state = cmd_dict.get('new_state') or {}
                    if hasattr(main_window_ref, '_compose_main_window_undo_state'):
                        cmd.old_state = main_window_ref._compose_main_window_undo_state(cmd.old_state)
                        cmd.new_state = main_window_ref._compose_main_window_undo_state(cmd.new_state)
                    cmd.description = cmd_dict.get('description', 'Изменение состояния проекта')
                    cmd._skip_initial_execute = bool(cmd_dict.get('skip_initial_execute', False))
                    return cmd

                elif cmd_type == 'RowAddCommand':
                    # Аналогично для RowAddCommand
                    logger.warning("RowAddCommand не может быть восстановлена при загрузке проекта")
                    return None

                elif cmd_type == 'RowDeleteCommand':
                    # Аналогично для RowDeleteCommand
                    logger.warning("RowDeleteCommand не может быть восстановлена при загрузке проекта")
                    return None

                elif cmd_type == 'CellEditCommand':
                    # Аналогично для CellEditCommand
                    logger.warning("CellEditCommand не может быть восстановлена при загрузке проекта")
                    return None

                return None

            # Восстанавливаем стеки
            undo_stack_data = data.get('undo_stack', [])
            for cmd_dict in undo_stack_data:
                cmd = deserialize_command(cmd_dict, main_window)
                if cmd is not None:
                    self.undo_stack.append(cmd)

            redo_stack_data = data.get('redo_stack', [])
            for cmd_dict in redo_stack_data:
                cmd = deserialize_command(cmd_dict, main_window)
                if cmd is not None:
                    self.redo_stack.append(cmd)

            logger.info(f"Восстановлена история undo/redo: {len(self.undo_stack)} команд в undo, {len(self.redo_stack)} команд в redo")
            return True

        except Exception as e:
            logger.error(f"Ошибка восстановления истории undo/redo: {e}", exc_info=True)
            self.undo_stack.clear()
            self.redo_stack.clear()
            return False


class DataChangeCommand(Command):
    """Команда для изменения данных в таблице"""

    def __init__(
        self,
        data_getter: Callable[[], pd.DataFrame],
        data_setter: Callable[[pd.DataFrame], None],
        old_data: pd.DataFrame,
        new_data: pd.DataFrame,
        description: str = "Изменение данных",
        post_execute: Callable[[], None] | None = None,
        post_undo: Callable[[], None] | None = None
    ):
        """
        Инициализация команды изменения данных

        Args:
            data_getter: Функция для получения текущих данных
            data_setter: Функция для установки данных
            old_data: Данные до изменения
            new_data: Данные после изменения
            description: Описание команды
        """
        self.data_getter = data_getter
        self.data_setter = data_setter
        self.old_data = old_data.copy()
        self.new_data = new_data.copy()
        self.description = description
        self.post_execute = post_execute
        self.post_undo = post_undo

    def execute(self) -> bool:
        """Применяет изменение данных"""
        try:
            self.data_setter(self.new_data)
            if self.post_execute is not None:
                self.post_execute()
            return True
        except Exception as e:
            logger.error(f"Ошибка выполнения команды изменения данных: {e}", exc_info=True)
            return False

    def undo(self) -> bool:
        """Отменяет изменение данных"""
        try:
            self.data_setter(self.old_data)
            if self.post_undo is not None:
                self.post_undo()
            return True
        except Exception as e:
            logger.error(f"Ошибка отмены команды изменения данных: {e}", exc_info=True)
            return False

    def get_description(self) -> str:
        """Возвращает описание команды"""
        return self.description


class EditorStateCommand(Command):
    """Команда для полного undo/redo состояния 3D-редактора."""

    def __init__(
        self,
        main_window,
        old_state: dict[str, Any],
        new_state: dict[str, Any],
        description: str = "Изменение в 3D-редакторе",
        skip_initial_execute: bool = False,
    ):
        self.main_window = main_window
        self.old_state = copy.deepcopy(old_state) if old_state is not None else {}
        self.new_state = copy.deepcopy(new_state) if new_state is not None else {}
        self.description = description
        self._skip_initial_execute = bool(skip_initial_execute)

    def execute(self) -> bool:
        """Применяет новое состояние или пропускает первичное выполнение."""
        try:
            if self._skip_initial_execute:
                self._skip_initial_execute = False
                return True
            self.main_window._apply_editor_undo_state(copy.deepcopy(self.new_state))
            return True
        except Exception as e:
            logger.error(f"Ошибка при применении EditorStateCommand: {e}", exc_info=True)
            return False

    def undo(self) -> bool:
        """Восстанавливает предыдущее состояние редактора."""
        try:
            self.main_window._apply_editor_undo_state(copy.deepcopy(self.old_state))
            return True
        except Exception as e:
            logger.error(f"Ошибка при undo EditorStateCommand: {e}", exc_info=True)
            return False

    def get_description(self) -> str:
        """Возвращает описание команды."""
        return self.description


class MainWindowStateCommand(Command):
    """Команда для serializable состояния главного окна и секционной подсистемы."""

    def __init__(
        self,
        main_window,
        old_state: dict[str, Any],
        new_state: dict[str, Any],
        description: str = "Изменение состояния проекта",
        skip_initial_execute: bool = False,
    ):
        self.main_window = main_window
        self.old_state = copy.deepcopy(old_state) if old_state is not None else {}
        self.new_state = copy.deepcopy(new_state) if new_state is not None else {}
        self.description = description
        self._skip_initial_execute = bool(skip_initial_execute)

    def execute(self) -> bool:
        """Применяет новое состояние проекта."""
        try:
            if self._skip_initial_execute:
                self._skip_initial_execute = False
                return True
            self.main_window._apply_main_window_undo_state(copy.deepcopy(self.new_state))
            return True
        except Exception as e:
            logger.error(f"Ошибка при применении MainWindowStateCommand: {e}", exc_info=True)
            return False

    def undo(self) -> bool:
        """Восстанавливает предыдущее состояние проекта."""
        try:
            self.main_window._apply_main_window_undo_state(copy.deepcopy(self.old_state))
            return True
        except Exception as e:
            logger.error(f"Ошибка при undo MainWindowStateCommand: {e}", exc_info=True)
            return False

    def get_description(self) -> str:
        """Возвращает описание команды."""
        return self.description


class RowAddCommand(Command):
    """Команда для добавления строки"""

    def __init__(
        self,
        data_getter: Callable[[], pd.DataFrame],
        data_setter: Callable[[pd.DataFrame], None],
        row_data: pd.Series,
        description: str = "Добавление строки"
    ):
        """
        Инициализация команды добавления строки

        Args:
            data_getter: Функция для получения текущих данных
            data_setter: Функция для установки данных
            row_data: Данные новой строки
            description: Описание команды
        """
        self.data_getter = data_getter
        self.data_setter = data_setter
        self.row_data = row_data.copy()
        self.row_index = None
        self.description = description

    def execute(self) -> bool:
        """Добавляет строку"""
        try:
            data = self.data_getter()
            new_data = pd.concat([data, self.row_data.to_frame().T], ignore_index=True)
            self.row_index = len(data)  # Индекс добавленной строки
            self.data_setter(new_data)
            return True
        except Exception as e:
            logger.error(f"Ошибка выполнения команды добавления строки: {e}", exc_info=True)
            return False

    def undo(self) -> bool:
        """Удаляет добавленную строку"""
        try:
            if self.row_index is None:
                return False

            data = self.data_getter()
            if self.row_index >= len(data):
                return False

            new_data = data.drop(index=self.row_index).reset_index(drop=True)
            self.data_setter(new_data)
            return True
        except Exception as e:
            logger.error(f"Ошибка отмены команды добавления строки: {e}", exc_info=True)
            return False

    def get_description(self) -> str:
        """Возвращает описание команды"""
        return self.description


class RowDeleteCommand(Command):
    """Команда для удаления строки"""

    def __init__(
        self,
        data_getter: Callable[[], pd.DataFrame],
        data_setter: Callable[[pd.DataFrame], None],
        row_indices: list[int],
        description: str = "Удаление строк"
    ):
        """
        Инициализация команды удаления строк

        Args:
            data_getter: Функция для получения текущих данных
            data_setter: Функция для установки данных
            row_indices: Индексы удаляемых строк
            description: Описание команды
        """
        self.data_getter = data_getter
        self.data_setter = data_setter
        self.row_indices = sorted(row_indices, reverse=True)  # Сортируем в обратном порядке
        self.deleted_rows = None
        self.description = description

    def execute(self) -> bool:
        """Удаляет строки"""
        try:
            data = self.data_getter()

            # Сохраняем удаляемые строки
            self.deleted_rows = data.iloc[self.row_indices].copy()

            # Удаляем строки
            new_data = data.drop(index=self.row_indices).reset_index(drop=True)
            self.data_setter(new_data)
            return True
        except Exception as e:
            logger.error(f"Ошибка выполнения команды удаления строк: {e}", exc_info=True)
            return False

    def undo(self) -> bool:
        """Восстанавливает удаленные строки"""
        try:
            if self.deleted_rows is None or len(self.deleted_rows) == 0:
                return False

            data = self.data_getter()

            # Восстанавливаем строки в исходных позициях
            # Создаем новый DataFrame с восстановленными строками
            result_data = data.copy()

            # Вставляем строки обратно в правильном порядке
            for idx, original_idx in enumerate(sorted(self.row_indices)):
                row = self.deleted_rows.iloc[idx:idx+1]
                # Вставляем строку в исходную позицию
                before = result_data.iloc[:original_idx]
                after = result_data.iloc[original_idx:]
                result_data = pd.concat([before, row, after], ignore_index=True)

            self.data_setter(result_data)
            return True
        except Exception as e:
            logger.error(f"Ошибка отмены команды удаления строк: {e}", exc_info=True)
            return False

    def get_description(self) -> str:
        """Возвращает описание команды"""
        count = len(self.row_indices)
        if count == 1:
            return f"Удаление строки {self.row_indices[0]}"
        else:
            return f"Удаление {count} строк"


class CellEditCommand(Command):
    """Команда для редактирования ячейки"""

    def __init__(
        self,
        data_getter: Callable[[], pd.DataFrame],
        data_setter: Callable[[pd.DataFrame], None],
        row_index: int,
        column_name: str,
        old_value: Any,
        new_value: Any,
        description: str = "Редактирование ячейки"
    ):
        """
        Инициализация команды редактирования ячейки

        Args:
            data_getter: Функция для получения текущих данных
            data_setter: Функция для установки данных
            row_index: Индекс строки
            column_name: Название колонки
            old_value: Старое значение
            new_value: Новое значение
            description: Описание команды
        """
        self.data_getter = data_getter
        self.data_setter = data_setter
        self.row_index = row_index
        self.column_name = column_name
        self.old_value = old_value
        self.new_value = new_value
        self.description = description

    def execute(self) -> bool:
        """Применяет изменение ячейки"""
        try:
            data = self.data_getter()
            if self.row_index >= len(data) or self.column_name not in data.columns:
                return False

            data.at[self.row_index, self.column_name] = self.new_value
            self.data_setter(data)
            return True
        except Exception as e:
            logger.error(f"Ошибка выполнения команды редактирования ячейки: {e}", exc_info=True)
            return False

    def undo(self) -> bool:
        """Отменяет изменение ячейки"""
        try:
            data = self.data_getter()
            if self.row_index >= len(data) or self.column_name not in data.columns:
                return False

            data.at[self.row_index, self.column_name] = self.old_value
            self.data_setter(data)
            return True
        except Exception as e:
            logger.error(f"Ошибка отмены команды редактирования ячейки: {e}", exc_info=True)
            return False

    def get_description(self) -> str:
        """Возвращает описание команды"""
        return f"Редактирование {self.column_name} в строке {self.row_index}"


class TowerBlueprintApplyCommand(Command):
    """Команда для применения blueprint башни"""

    def __init__(
        self,
        main_window,
        new_blueprint: Any,  # TowerBlueprint
        description: str = "Применение blueprint башни"
    ):
        """
        Инициализация команды применения blueprint

        Args:
            main_window: Ссылка на главное окно для доступа к данным и методам
            new_blueprint: Новый blueprint для применения
            description: Описание команды
        """
        self.main_window = main_window
        self.new_blueprint = new_blueprint
        self.description = description

        # Сохраняем состояние до применения
        try:
            self.old_raw_data = main_window.raw_data.copy(deep=True) if main_window.raw_data is not None else None
        except Exception as e:
            logger.error(f"Ошибка при сохранении old_raw_data: {e}")
            self.old_raw_data = None
        self.old_processed_data = copy.deepcopy(main_window.processed_data) if main_window.processed_data is not None else None
        self.old_original_data_before_sections = (
            main_window.original_data_before_sections.copy(deep=True)
            if main_window.original_data_before_sections is not None else None
        )
        self.old_tower_blueprint = (
            copy.deepcopy(main_window._tower_blueprint)
            if main_window._tower_blueprint is not None else None
        )
        self.old_epsg_code = main_window.epsg_code
        self.old_height_tolerance = main_window.height_tolerance
        self.old_center_method = main_window.center_method
        self.old_expected_belt_count = main_window.expected_belt_count
        self.old_tower_faces_count = main_window.tower_faces_count

        # Сохраняем section_data из 3D редактора
        if hasattr(main_window.editor_3d, 'section_data'):
            self.old_section_data = copy.deepcopy(main_window.editor_3d.section_data) if main_window.editor_3d.section_data else None
        else:
            self.old_section_data = None

        # Сохраняем xy_plane_state
        if hasattr(main_window.editor_3d, 'get_xy_plane_state'):
            self.old_xy_plane_state = main_window.editor_3d.get_xy_plane_state()
        else:
            self.old_xy_plane_state = None

    def execute(self) -> bool:
        """Применяет новый blueprint"""
        try:
            logger.info(f"Выполнение команды применения blueprint: {self.description}")
            # Вызываем оригинальный метод apply_tower_blueprint, но без очистки истории
            # Временно сохраняем флаг очистки истории
            import numpy as np
            import pandas as pd

            from core.tower_generator import generate_tower_data

            blueprint = self.new_blueprint
            logger.info("Генерация данных башни из blueprint...")
            data, section_data, metadata = generate_tower_data(blueprint)
            logger.info(f"Данные сгенерированы: {len(data)} точек, {len(section_data) if section_data else 0} секций")

            # --- Structural Model Generation & Visualization ---
            try:
                from core.structure.builder import TowerModelBuilder
                from core.structure.model import MemberType

                builder = TowerModelBuilder(blueprint)
                model = builder.build()

                # Convert model members to lines for visualization
                # Note: Model nodes are in local coords (starting at 0,0,0).
                # generate_tower_data applies offset (standing point).
                # We need to apply the same offset.
                standing = metadata.get("standing_point", {"x": 0, "y": 0, "z": 0})
                # Also generate_tower_data calculates tower_offset_x/y from instrument distance.
                # We should retrieve the applied offset or recalculate it.
                # generate_tower_data returns shifted data.
                # We can infer offset from metadata or recalculate.
                # Let's use the logic from generate_tower_data.

                # Calculate offset exactly as in generate_tower_data
                import math
                def _deg2rad(v): return v * math.pi / 180.0
                dist = float(blueprint.instrument_distance)
                angle = float(blueprint.instrument_angle_deg)
                off_x = dist * math.cos(_deg2rad(angle))
                off_y = dist * math.sin(_deg2rad(angle))

                members_data = []
                for member in model.members:
                    n1 = model.nodes.get(member.start_node_id)
                    n2 = model.nodes.get(member.end_node_id)
                    if not n1 or not n2: continue

                    p1 = np.array([n1.x + off_x, n1.y + off_y, n1.z])
                    p2 = np.array([n2.x + off_x, n2.y + off_y, n2.z])

                    color = (0.5, 0.5, 0.5, 0.5)
                    if member.member_type == MemberType.LEG:
                        color = (0.2, 0.2, 0.2, 1.0) # Dark Grey
                    elif member.member_type == MemberType.BRACE:
                        color = (0.0, 0.4, 0.8, 0.8) # Blue
                    elif member.member_type == MemberType.STRUT:
                        color = (0.0, 0.6, 0.2, 0.8) # Green

                    members_data.append({
                        "points": [p1, p2],
                        "type": member.member_type.value,
                        "color": color
                    })

                # Pass to editor_3d
                if hasattr(self.main_window.editor_3d, 'set_structural_lines'):
                    self.main_window.editor_3d.set_structural_lines(members_data)

                # Очистить предпросмотр из конструктора, т.к. blueprint применен
                if hasattr(self.main_window.editor_3d, '_clear_tower_preview'):
                    self.main_window.editor_3d._clear_tower_preview()

                # Установить флаг применения blueprint
                if hasattr(self.main_window.editor_3d, '_blueprint_applied'):
                    self.main_window.editor_3d._blueprint_applied = True

            except Exception as e:
                logger.error(f"Ошибка построения структурной модели для визуализации: {e}")

            # Убираем флаг generated, чтобы башня работала как "родная"
            if 'generated' in data.columns:
                data = data.drop(columns=['generated'])

            # Добавляем недостающие колонки для совместимости с реальными данными
            if 'point_index' not in data.columns:
                data['point_index'] = range(1, len(data) + 1)
            if 'tower_part_memberships' not in data.columns:
                data['tower_part_memberships'] = None
            if 'is_part_boundary' not in data.columns:
                data['is_part_boundary'] = False

            # Если blueprint содержит несколько segments - это составная башня
            if hasattr(blueprint, 'segments') and len(blueprint.segments) > 1:
                logger.info(f"Применение составной башни с {len(blueprint.segments)} частями")

                # Добавляем колонки tower_part и part_belt
                if 'tower_part' not in data.columns:
                    data['tower_part'] = 1
                if 'part_belt' not in data.columns:
                    data['part_belt'] = data['belt']

                # Определяем принадлежность точек к частям
                if 'segment' in data.columns:
                    for idx, row in data.iterrows():
                        if pd.notna(row.get('segment')):
                            segment_id = int(row['segment'])
                            data.loc[idx, 'tower_part'] = segment_id
                else:
                    # Определяем по высоте
                    cumulative_heights = [0.0]
                    for seg in blueprint.segments:
                        cumulative_heights.append(cumulative_heights[-1] + seg.height)

                    for idx, row in data.iterrows():
                        if pd.notna(row.get('z')):
                            z_value = float(row['z'])
                            part_num = 1
                            for part_idx in range(len(cumulative_heights) - 1):
                                if cumulative_heights[part_idx] <= z_value < cumulative_heights[part_idx + 1]:
                                    part_num = part_idx + 1
                                    break
                            if z_value >= cumulative_heights[-1]:
                                part_num = len(blueprint.segments)
                            data.loc[idx, 'tower_part'] = part_num

                # Переназначаем номера поясов для каждой части отдельно
                for part_num in range(1, len(blueprint.segments) + 1):
                    part_data = data[data['tower_part'] == part_num]
                    if not part_data.empty and 'belt' in part_data.columns:
                        part_belts = sorted(part_data['belt'].dropna().unique())
                        for belt_num in part_belts:
                            belt_mask = (data['tower_part'] == part_num) & (data['belt'] == belt_num)
                            belt_index = part_belts.index(belt_num)
                            data.loc[belt_mask, 'part_belt'] = belt_index + 1
            else:
                # Для башни из одной части также устанавливаем part_belt
                if 'part_belt' not in data.columns:
                    data['part_belt'] = data['belt']
                if 'tower_part' not in data.columns:
                    data['tower_part'] = 1

            # Устанавливаем данные
            self.main_window.raw_data = data
            self.main_window.processed_data = None
            self.main_window.original_data_before_sections = data.copy(deep=True)

            # Обновляем виджеты
            if hasattr(self.main_window.data_table, "set_data"):
                self.main_window.data_table.set_data(data)
            if hasattr(self.main_window.editor_3d, "set_data"):
                self.main_window.editor_3d.set_data(data)
            if hasattr(self.main_window.editor_3d, 'set_section_lines'):
                self.main_window.editor_3d.set_section_lines(section_data)

            # Включаем операции с секциями
            has_sections = bool(section_data and len(section_data) > 0)
            if hasattr(self.main_window.editor_3d, 'create_sections_action'):
                self.main_window.editor_3d.create_sections_action.setEnabled(True)
            if hasattr(self.main_window.editor_3d, 'remove_sections_action'):
                self.main_window.editor_3d.remove_sections_action.setEnabled(has_sections)
            if hasattr(self.main_window.editor_3d, 'build_central_axis_action'):
                self.main_window.editor_3d.build_central_axis_action.setEnabled(has_sections)
            if hasattr(self.main_window.editor_3d, 'tilt_plane_btn'):
                self.main_window.editor_3d.tilt_plane_btn.setEnabled(has_sections)
            if hasattr(self.main_window.editor_3d, 'tilt_single_section_btn'):
                self.main_window.editor_3d.tilt_single_section_btn.setEnabled(has_sections)

            # Сохраняем blueprint
            self.main_window._tower_blueprint = blueprint
            self.main_window.project_manager.tower_builder_state = blueprint.to_dict()
            if hasattr(self.main_window.editor_3d, 'set_tower_builder_blueprint'):
                self.main_window.editor_3d.set_tower_builder_blueprint(blueprint)

            # Обновляем настройки
            if hasattr(blueprint, 'segments') and len(blueprint.segments) > 1:
                self.main_window.tower_faces_count = max(seg.faces for seg in blueprint.segments)
            else:
                self.main_window.tower_faces_count = blueprint.faces if hasattr(blueprint, 'faces') else 4

            belt_count = data[data['belt'].notna()]['belt'].nunique()
            self.main_window.expected_belt_count = belt_count if belt_count > 0 else None
            if self.main_window.belt_count_spin is not None and belt_count:
                self.main_window.belt_count_spin.setValue(int(belt_count))

            # Обновляем виджеты анализа
            self.main_window.update_export_actions_state()
            if hasattr(self.main_window, 'verticality_widget'):
                self.main_window.verticality_widget.set_data(self.main_window.raw_data, None)
            if hasattr(self.main_window, 'straightness_widget'):
                self.main_window.straightness_widget.set_data(self.main_window.raw_data, None)

            self.main_window.has_unsaved_changes = True

            logger.info("Команда применения blueprint выполнена успешно")
            return True
        except Exception as e:
            logger.error(f"Ошибка выполнения команды применения blueprint: {e}", exc_info=True)
            return False

    def undo(self) -> bool:
        """Отменяет применение blueprint, восстанавливая предыдущее состояние"""
        try:
            logger.info(f"Выполнение undo для TowerBlueprintApplyCommand: old_raw_data is None={self.old_raw_data is None}")
            # Восстанавливаем данные
            if self.old_raw_data is not None:
                self.main_window.raw_data = self.old_raw_data.copy(deep=True)
            else:
                self.main_window.raw_data = None
            self.main_window.processed_data = copy.deepcopy(self.old_processed_data) if self.old_processed_data is not None else None
            self.main_window.original_data_before_sections = (
                self.old_original_data_before_sections.copy(deep=True)
                if self.old_original_data_before_sections is not None else None
            )
            self.main_window._tower_blueprint = copy.deepcopy(self.old_tower_blueprint) if self.old_tower_blueprint is not None else None
            self.main_window.epsg_code = self.old_epsg_code
            self.main_window.height_tolerance = self.old_height_tolerance
            self.main_window.center_method = self.old_center_method
            self.main_window.expected_belt_count = self.old_expected_belt_count
            self.main_window.tower_faces_count = self.old_tower_faces_count

            # Восстанавливаем section_data
            if hasattr(self.main_window.editor_3d, 'section_data'):
                self.main_window.editor_3d.section_data = (
                    copy.deepcopy(self.old_section_data)
                    if self.old_section_data is not None else None
                )

            # Восстанавливаем xy_plane_state
            if hasattr(self.main_window.editor_3d, 'set_xy_plane_state') and self.old_xy_plane_state is not None:
                self.main_window.editor_3d.set_xy_plane_state(self.old_xy_plane_state)

            # Обновляем виджеты
            if self.main_window.raw_data is not None and not self.main_window.raw_data.empty:
                if hasattr(self.main_window.data_table, "set_data"):
                    self.main_window.data_table.set_data(self.main_window.raw_data)
                if hasattr(self.main_window.editor_3d, "set_data"):
                    self.main_window.editor_3d.set_data(self.main_window.raw_data)
                if hasattr(self.main_window.editor_3d, 'set_section_lines'):
                    self.main_window.editor_3d.set_section_lines(self.old_section_data if self.old_section_data else [])

                # Обновляем настройки поясов
                if self.main_window.belt_count_spin is not None:
                    if self.main_window.expected_belt_count is not None:
                        self.main_window.belt_count_spin.setValue(int(self.main_window.expected_belt_count))

                # Обновляем blueprint в редакторе
                if hasattr(self.main_window.editor_3d, 'set_tower_builder_blueprint'):
                    self.main_window.editor_3d.set_tower_builder_blueprint(self.old_tower_blueprint)

                # Обновляем состояние кнопок секций
                has_sections = bool(self.old_section_data and len(self.old_section_data) > 0)
                if hasattr(self.main_window.editor_3d, 'create_sections_action'):
                    self.main_window.editor_3d.create_sections_action.setEnabled(
                        self.main_window.raw_data is not None and not self.main_window.raw_data.empty
                    )
                if hasattr(self.main_window.editor_3d, 'remove_sections_action'):
                    self.main_window.editor_3d.remove_sections_action.setEnabled(has_sections)
                if hasattr(self.main_window.editor_3d, 'build_central_axis_action'):
                    self.main_window.editor_3d.build_central_axis_action.setEnabled(has_sections)
                if hasattr(self.main_window.editor_3d, 'tilt_plane_btn'):
                    self.main_window.editor_3d.tilt_plane_btn.setEnabled(has_sections)
                if hasattr(self.main_window.editor_3d, 'tilt_single_section_btn'):
                    self.main_window.editor_3d.tilt_single_section_btn.setEnabled(has_sections)
            else:
                # Если данных нет, очищаем виджеты
                if hasattr(self.main_window.data_table, "set_data"):
                    self.main_window.data_table.set_data(pd.DataFrame())
                if hasattr(self.main_window.editor_3d, "set_data"):
                    self.main_window.editor_3d.set_data(pd.DataFrame())
                if hasattr(self.main_window.editor_3d, 'set_section_lines'):
                    self.main_window.editor_3d.set_section_lines([])
                if hasattr(self.main_window.editor_3d, 'set_tower_builder_blueprint'):
                    self.main_window.editor_3d.set_tower_builder_blueprint(None)

            # Обновляем виджеты анализа
            self.main_window.update_export_actions_state()
            if hasattr(self.main_window, 'verticality_widget'):
                self.main_window.verticality_widget.set_data(
                    self.main_window.raw_data,
                    self.main_window.processed_data
                )
            if hasattr(self.main_window, 'straightness_widget'):
                self.main_window.straightness_widget.set_data(
                    self.main_window.raw_data,
                    self.main_window.processed_data
                )

            self.main_window.has_unsaved_changes = True

            logger.info("Undo команды применения blueprint выполнено успешно")
            return True
        except Exception as e:
            logger.error(f"Ошибка отмены команды применения blueprint: {e}", exc_info=True)
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return False

    def get_description(self) -> str:
        """Возвращает описание команды"""
        return self.description

