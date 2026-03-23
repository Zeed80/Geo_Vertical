"""
Unit-тесты для модуля undo_manager.py
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pandas as pd
import pytest

from core.undo_manager import CellEditCommand, DataChangeCommand, RowAddCommand, RowDeleteCommand, UndoManager


class TestUndoManager:
    """Тесты класса UndoManager"""

    def test_initial_state(self):
        """Тест начального состояния"""
        manager = UndoManager()
        assert not manager.can_undo()
        assert not manager.can_redo()

    def test_execute_command(self):
        """Тест выполнения команды"""
        manager = UndoManager()
        data = pd.DataFrame({'x': [1, 2], 'y': [3, 4]})
        new_data = pd.DataFrame({'x': [1, 2, 3], 'y': [3, 4, 5]})

        current_data = [data]

        def get_data():
            return current_data[0]

        def set_data(df):
            current_data[0] = df

        command = DataChangeCommand(get_data, set_data, data, new_data, "Тест")
        result = manager.execute_command(command)

        assert result
        assert manager.can_undo()
        assert not manager.can_redo()

    def test_undo(self):
        """Тест отмены команды"""
        manager = UndoManager()
        data = pd.DataFrame({'x': [1, 2], 'y': [3, 4]})
        new_data = pd.DataFrame({'x': [1, 2, 3], 'y': [3, 4, 5]})

        current_data = [data]

        def get_data():
            return current_data[0]

        def set_data(df):
            current_data[0] = df

        command = DataChangeCommand(get_data, set_data, data, new_data, "Тест")
        manager.execute_command(command)

        assert manager.undo()
        assert len(current_data[0]) == len(data)
        assert manager.can_redo()

    def test_redo(self):
        """Тест повтора команды"""
        manager = UndoManager()
        data = pd.DataFrame({'x': [1, 2], 'y': [3, 4]})
        new_data = pd.DataFrame({'x': [1, 2, 3], 'y': [3, 4, 5]})

        current_data = [data]

        def get_data():
            return current_data[0]

        def set_data(df):
            current_data[0] = df

        command = DataChangeCommand(get_data, set_data, data, new_data, "Тест")
        manager.execute_command(command)
        manager.undo()

        assert manager.redo()
        assert len(current_data[0]) == len(new_data)

    def test_max_history_size(self):
        """Тест ограничения размера истории"""
        manager = UndoManager(max_history_size=3)
        data = pd.DataFrame({'x': [1]})

        current_data = [data]

        def get_data():
            return current_data[0]

        def set_data(df):
            current_data[0] = df

        # Выполняем больше команд, чем max_history_size
        for i in range(5):
            new_data = pd.DataFrame({'x': [i]})
            command = DataChangeCommand(get_data, set_data, current_data[0], new_data, f"Команда {i}")
            manager.execute_command(command)

        # Должно быть только max_history_size команд в стеке
        assert len(manager.undo_stack) == 3

    def test_clear(self):
        """Тест очистки истории"""
        manager = UndoManager()
        data = pd.DataFrame({'x': [1, 2]})
        new_data = pd.DataFrame({'x': [1, 2, 3]})

        current_data = [data]

        def get_data():
            return current_data[0]

        def set_data(df):
            current_data[0] = df

        command = DataChangeCommand(get_data, set_data, data, new_data, "Тест")
        manager.execute_command(command)

        manager.clear()
        assert not manager.can_undo()
        assert not manager.can_redo()


class TestDataChangeCommand:
    """Тесты класса DataChangeCommand"""

    def test_execute(self):
        """Тест выполнения команды"""
        data = pd.DataFrame({'x': [1, 2], 'y': [3, 4]})
        new_data = pd.DataFrame({'x': [1, 2, 3], 'y': [3, 4, 5]})

        current_data = [data]

        def get_data():
            return current_data[0]

        def set_data(df):
            current_data[0] = df

        command = DataChangeCommand(get_data, set_data, data, new_data, "Изменение данных")
        assert command.execute()
        assert len(current_data[0]) == len(new_data)

    def test_undo(self):
        """Тест отмены команды"""
        data = pd.DataFrame({'x': [1, 2], 'y': [3, 4]})
        new_data = pd.DataFrame({'x': [1, 2, 3], 'y': [3, 4, 5]})

        current_data = [new_data]

        def get_data():
            return current_data[0]

        def set_data(df):
            current_data[0] = df

        command = DataChangeCommand(get_data, set_data, data, new_data, "Изменение данных")
        command.execute()
        assert command.undo()
        assert len(current_data[0]) == len(data)


class TestRowAddCommand:
    """Тесты класса RowAddCommand"""

    def test_execute(self):
        """Тест добавления строки"""
        data = pd.DataFrame({'x': [1, 2], 'y': [3, 4]})
        new_row = pd.Series({'x': 3, 'y': 5})

        current_data = [data]

        def get_data():
            return current_data[0]

        def set_data(df):
            current_data[0] = df

        command = RowAddCommand(get_data, set_data, new_row, "Добавление строки")
        assert command.execute()
        assert len(current_data[0]) == len(data) + 1

    def test_undo(self):
        """Тест отмены добавления строки"""
        data = pd.DataFrame({'x': [1, 2], 'y': [3, 4]})
        new_row = pd.Series({'x': 3, 'y': 5})

        current_data = [data]

        def get_data():
            return current_data[0]

        def set_data(df):
            current_data[0] = df

        command = RowAddCommand(get_data, set_data, new_row, "Добавление строки")
        command.execute()
        assert command.undo()
        assert len(current_data[0]) == len(data)


class TestRowDeleteCommand:
    """Тесты класса RowDeleteCommand"""

    def test_execute(self):
        """Тест удаления строк"""
        data = pd.DataFrame({'x': [1, 2, 3], 'y': [4, 5, 6]})

        current_data = [data]

        def get_data():
            return current_data[0]

        def set_data(df):
            current_data[0] = df

        command = RowDeleteCommand(get_data, set_data, [1], "Удаление строки")
        assert command.execute()
        assert len(current_data[0]) == len(data) - 1

    def test_undo(self):
        """Тест отмены удаления строк"""
        data = pd.DataFrame({'x': [1, 2, 3], 'y': [4, 5, 6]})

        current_data = [data]

        def get_data():
            return current_data[0]

        def set_data(df):
            current_data[0] = df

        command = RowDeleteCommand(get_data, set_data, [1], "Удаление строки")
        command.execute()
        assert command.undo()
        assert len(current_data[0]) == len(data)


class TestCellEditCommand:
    """Тесты класса CellEditCommand"""

    def test_execute(self):
        """Тест редактирования ячейки"""
        data = pd.DataFrame({'x': [1, 2], 'y': [3, 4]})

        current_data = [data]

        def get_data():
            return current_data[0]

        def set_data(df):
            current_data[0] = df

        command = CellEditCommand(get_data, set_data, 0, 'x', 1, 10, "Редактирование ячейки")
        assert command.execute()
        assert current_data[0].at[0, 'x'] == 10

    def test_undo(self):
        """Тест отмены редактирования ячейки"""
        data = pd.DataFrame({'x': [1, 2], 'y': [3, 4]})

        current_data = [data]

        def get_data():
            return current_data[0]

        def set_data(df):
            current_data[0] = df

        command = CellEditCommand(get_data, set_data, 0, 'x', 1, 10, "Редактирование ячейки")
        command.execute()
        assert command.undo()
        assert current_data[0].at[0, 'x'] == 1


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

