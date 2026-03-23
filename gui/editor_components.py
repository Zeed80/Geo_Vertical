"""
Вспомогательные компоненты для 3D-редактора точек.

Классы, извлечённые из point_editor_3d.py для уменьшения размера файла.
"""

from __future__ import annotations

import math
import numpy as np
from typing import Optional, List, Dict, Any

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QDialog, QFormLayout, QDialogButtonBox,
    QLineEdit, QComboBox, QMessageBox,
    QCheckBox, QSizePolicy, QDoubleSpinBox, QGridLayout,
)
from PyQt6.QtCore import Qt, QPointF, QSize
from PyQt6.QtGui import QColor

import pyqtgraph as pg
import pyqtgraph.opengl as gl

from gui.ui_helpers import apply_compact_button_style


class ContrastGLTextItem(gl.GLTextItem):
    """GLTextItem с тенью для читаемых подписей поверх 3D-сцены."""

    def __init__(
        self,
        parentItem=None,
        shadow_color: Optional[QColor] = None,
        shadow_offset: Optional[QPointF] = None,
        screen_offset: Optional[QPointF] = None,
        **kwds,
    ):
        self.shadow_color = shadow_color if shadow_color is not None else QColor(0, 0, 0, 200)
        self.shadow_offset = shadow_offset if shadow_offset is not None else QPointF(1.5, 1.5)
        self.screen_offset = screen_offset if screen_offset is not None else QPointF(0.0, 0.0)
        super().__init__(parentItem=parentItem, **kwds)

    def paint(self):
        if len(self.text) < 1:
            return
        self.setupGLState()

        project = self.compute_projection()
        vec3 = pg.QtGui.QVector3D(*self.pos)
        text_pos = self.align_text(project.map(vec3).toPointF())
        text_pos += self.screen_offset

        painter = pg.QtGui.QPainter(self.view())
        painter.setFont(self.font)
        painter.setRenderHints(
            pg.QtGui.QPainter.RenderHint.Antialiasing | pg.QtGui.QPainter.RenderHint.TextAntialiasing
        )

        shadow_pos = QPointF(text_pos)
        shadow_pos += self.shadow_offset
        painter.setPen(self.shadow_color)
        painter.drawText(shadow_pos, self.text)

        painter.setPen(self.color)
        painter.drawText(text_pos, self.text)
        painter.end()


class ButtonGroupWidget(QWidget):
    """Виджет-группа для кнопок с рамкой и заголовком снизу."""

    def __init__(self, title: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName('buttonGroup')

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(4, 4, 4, 2)
        main_layout.setSpacing(2)
        self.setLayout(main_layout)

        self.buttons_container = QWidget()
        self.buttons_layout = QHBoxLayout()
        self.buttons_layout.setContentsMargins(3, 3, 3, 0)
        self.buttons_layout.setSpacing(2)
        self.buttons_layout.setSizeConstraint(QVBoxLayout.SizeConstraint.SetFixedSize)
        self.buttons_container.setLayout(self.buttons_layout)
        main_layout.addWidget(self.buttons_container)

        self.title_label = QLabel(title)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setStyleSheet("""
            QLabel {
                font-size: 9px;
                color: #666;
                padding: 2px;
                background-color: transparent;
            }
        """)
        main_layout.addWidget(self.title_label)

        self.setStyleSheet("""
            QWidget#buttonGroup {
                border: 1px solid #b0b0b0;
                border-radius: 4px;
                background-color: #f0f0f0;
                margin: 2px;
            }
        """)

    def add_button(self, button: QWidget):
        if button is None:
            return
        self.buttons_layout.addWidget(button)

    def buttons(self):
        buttons = []
        for i in range(self.buttons_layout.count()):
            item = self.buttons_layout.itemAt(i)
            if item and item.widget():
                buttons.append(item.widget())
        return buttons

    def sizeHint(self):
        total_width = 0
        max_height = 0
        for i in range(self.buttons_layout.count()):
            item = self.buttons_layout.itemAt(i)
            if item and item.widget():
                widget = item.widget()
                hint = widget.sizeHint()
                total_width += hint.width()
                max_height = max(max_height, hint.height())

        margins = self.buttons_layout.contentsMargins()
        spacing = self.buttons_layout.spacing()
        button_count = self.buttons_layout.count()

        width = total_width + margins.left() + margins.right() + spacing * max(0, button_count - 1)
        height = max_height + margins.top() + margins.bottom() + 20

        return QSize(width, height)


class ToolPanelWidget(QWidget):
    """Компактная панель инструментов с адаптивной раскладкой."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._position: str = 'left'
        self._orientation: Qt.Orientation = Qt.Orientation.Vertical
        self._items: List[QWidget] = []

        self._grid = QGridLayout()
        self._grid.setContentsMargins(4, 4, 4, 4)
        self._grid.setHorizontalSpacing(4)
        self._grid.setVerticalSpacing(4)
        self.setLayout(self._grid)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

    def add_button(self, button: QWidget):
        if button is None:
            return
        button.setParent(self)
        self._items.append(button)
        button.show()
        self.reflow()

    def add_group(self, group: ButtonGroupWidget):
        if group is None:
            return
        group.setParent(self)
        self._items.append(group)
        group.show()
        self.reflow()

    def items(self) -> List[QWidget]:
        return list(self._items)

    def orientation(self) -> Qt.Orientation:
        return self._orientation

    def set_position(self, position: str):
        valid_positions = {'left', 'right', 'top'}
        if position not in valid_positions:
            position = 'left'
        self._position = position
        self._orientation = Qt.Orientation.Horizontal if position == 'top' else Qt.Orientation.Vertical
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)

        if position == 'top':
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        else:
            self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

        self.reflow()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.reflow()

    def _clear_layout(self):
        for i in reversed(range(self._grid.count())):
            item = self._grid.takeAt(i)
            widget = item.widget()
            if widget:
                widget.hide()

    def reflow(self):
        if not self._items:
            return

        self._clear_layout()

        spacing = self._grid.horizontalSpacing() or 4
        margins = self._grid.contentsMargins()

        button_widths = []
        button_heights = []
        for widget in self._items:
            if isinstance(widget, ButtonGroupWidget):
                hint = widget.sizeHint()
                button_widths.append(int(hint.width()))
                button_heights.append(int(hint.height()))
            else:
                base_width = widget.property('base_width')
                base_height = widget.property('base_height')
                if base_width is None:
                    base_width = widget.sizeHint().width()
                if base_height is None:
                    base_height = widget.sizeHint().height()
                button_widths.append(int(base_width))
                button_heights.append(int(base_height))

        max_width = max(button_widths) if button_widths else 80
        max_height = max(button_heights) if button_heights else 52
        count = len(self._items)

        if self._position == 'top':
            available_width = max(1, self.width() - margins.left() - margins.right())
            if available_width <= 0:
                available_width = max_width + spacing
            columns = max(1, min(count, (available_width + spacing) // (max_width + spacing)))
            if columns <= 0:
                columns = 1
            rows = math.ceil(count / columns)

            col = row = 0
            for widget in self._items:
                self._grid.addWidget(widget, row, col)
                widget.show()
                col += 1
                if col >= columns:
                    col = 0
                    row += 1

            for c in range(columns):
                self._grid.setColumnStretch(c, 1)
            for r in range(rows):
                self._grid.setRowStretch(r, 0)

            required_height = rows * (max_height + spacing) + margins.top() + margins.bottom()
            self.setFixedHeight(required_height)

        else:
            available_height = max(1, self.height() - margins.top() - margins.bottom())
            if available_height < max_height + spacing:
                rows_per_column = count
            else:
                rows_per_column = max(1, min(count, (available_height + spacing) // (max_height + spacing)))
            if rows_per_column <= 0:
                rows_per_column = 1
            columns = math.ceil(count / rows_per_column)

            row = col = 0
            max_columns_used = 0
            for widget in self._items:
                self._grid.addWidget(widget, row, col)
                widget.show()
                row += 1
                max_columns_used = max(max_columns_used, col + 1)
                if row >= rows_per_column:
                    row = 0
                    col += 1

            for c in range(max_columns_used):
                self._grid.setColumnStretch(c, 0)
            for r in range(rows_per_column):
                self._grid.setRowStretch(r, 0)

            required_width = max_columns_used * (max_width + spacing) + margins.left() + margins.right()
            self.setFixedWidth(required_width)

        self.updateGeometry()


class PointEditDialog(QDialog):
    """Диалог для редактирования координат и параметров точки."""

    def __init__(
        self,
        point_data: dict,
        available_belts: List[int],
        available_parts: List[int],
        parent=None,
    ):
        super().__init__(parent)
        self.point_data = point_data.copy()
        self.available_belts = available_belts or []
        self.available_parts = available_parts or [1]
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle('Редактирование точки')
        self.setModal(True)

        layout = QFormLayout()

        self.name_edit = QLineEdit(str(self.point_data.get('name', '')))
        layout.addRow('Название:', self.name_edit)

        self.x_edit = QLineEdit(str(self.point_data.get('x', 0.0)))
        self.y_edit = QLineEdit(str(self.point_data.get('y', 0.0)))
        self.z_edit = QLineEdit(str(self.point_data.get('z', 0.0)))

        self.x_edit.textChanged.connect(lambda: self._validate_coordinate(self.x_edit, 'X'))
        self.y_edit.textChanged.connect(lambda: self._validate_coordinate(self.y_edit, 'Y'))
        self.z_edit.textChanged.connect(lambda: self._validate_coordinate(self.z_edit, 'Z'))

        layout.addRow('X (м):', self.x_edit)
        layout.addRow('Y (м):', self.y_edit)
        layout.addRow('Z (м):', self.z_edit)

        self.validation_label = QLabel('')
        self.validation_label.setWordWrap(True)
        self.validation_label.setStyleSheet('color: red; font-size: 10pt;')
        layout.addRow('', self.validation_label)

        self.belt_combo = QComboBox()
        self.belt_combo.addItem('Не назначен', None)
        for belt_num in self.available_belts:
            self.belt_combo.addItem(f'Пояс {belt_num}', belt_num)

        current_belt = self.point_data.get('belt', None)
        if current_belt is not None:
            index = self.belt_combo.findData(current_belt)
            if index >= 0:
                self.belt_combo.setCurrentIndex(index)

        layout.addRow('Пояс:', self.belt_combo)

        self.part_combo = QComboBox()
        added_parts = sorted({int(p) for p in self.available_parts if p is not None})
        if not added_parts:
            added_parts = [1]
        for part_num in added_parts:
            self.part_combo.addItem(f'Часть {part_num}', part_num)
        current_part = self.point_data.get('tower_part')
        if current_part is not None:
            part_index = self.part_combo.findData(int(current_part))
            if part_index >= 0:
                self.part_combo.setCurrentIndex(part_index)
        layout.addRow('Часть башни:', self.part_combo)

        self.boundary_check = QCheckBox('Разделение частей (граница)')
        boundary_value = bool(self.point_data.get('is_part_boundary', False))
        self.boundary_check.setChecked(boundary_value)
        layout.addRow('', self.boundary_check)

        button_layout = QHBoxLayout()

        ok_btn = QPushButton('OK')
        ok_btn.clicked.connect(self.accept)
        apply_compact_button_style(ok_btn, width=96, min_height=32)
        button_layout.addWidget(ok_btn)

        cancel_btn = QPushButton('Отмена')
        cancel_btn.clicked.connect(self.reject)
        apply_compact_button_style(cancel_btn, width=96, min_height=32)
        button_layout.addWidget(cancel_btn)

        layout.addRow('', button_layout)

        self.setLayout(layout)

    def _validate_coordinate(self, edit: QLineEdit, coord_name: str) -> bool:
        text = edit.text().strip()

        if not text:
            edit.setStyleSheet('')
            return False

        try:
            value = float(text)

            if not np.isfinite(value):
                edit.setStyleSheet('background-color: #ffcccc;')
                self.validation_label.setText(f'{coord_name}: значение должно быть конечным числом')
                return False

            if coord_name == 'Z' and value < 0:
                edit.setStyleSheet('background-color: #ffcccc;')
                self.validation_label.setText(f'{coord_name}: высота не может быть отрицательной')
                return False

            if coord_name == 'Z' and value > 10000:
                edit.setStyleSheet('background-color: #fff4cc;')
                self.validation_label.setText(f'{coord_name}: значение очень большое ({value} м). Проверьте единицы измерения.')
                return True

            if coord_name in ('X', 'Y') and abs(value) > 1e6:
                edit.setStyleSheet('background-color: #fff4cc;')
                self.validation_label.setText(f'{coord_name}: значение очень большое ({value} м). Проверьте единицы измерения.')
                return True

            edit.setStyleSheet('')
            self.validation_label.setText('')
            return True

        except ValueError:
            edit.setStyleSheet('background-color: #ffcccc;')
            self.validation_label.setText(f'{coord_name}: введите корректное число')
            return False

    def get_point_data(self) -> Optional[dict]:
        x_valid = self._validate_coordinate(self.x_edit, 'X')
        y_valid = self._validate_coordinate(self.y_edit, 'Y')
        z_valid = self._validate_coordinate(self.z_edit, 'Z')

        if not (x_valid and y_valid and z_valid):
            error_msg = "Исправьте ошибки валидации перед сохранением"
            if self.validation_label.text():
                error_msg = self.validation_label.text()
            QMessageBox.warning(self, 'Ошибка валидации', error_msg)
            return None

        try:
            x_value = float(self.x_edit.text().strip())
            y_value = float(self.y_edit.text().strip())
            z_value = float(self.z_edit.text().strip())

            if not (np.isfinite(x_value) and np.isfinite(y_value) and np.isfinite(z_value)):
                QMessageBox.warning(self, 'Ошибка валидации', 'Все координаты должны быть конечными числами')
                return None

            if z_value < 0:
                QMessageBox.warning(self, 'Ошибка валидации', 'Высота (Z) не может быть отрицательной')
                return None

            return {
                'name': self.name_edit.text().strip(),
                'x': x_value,
                'y': y_value,
                'z': z_value,
                'belt': self.belt_combo.currentData(),
                'tower_part': self.part_combo.currentData(),
                'is_part_boundary': self.boundary_check.isChecked(),
            }
        except ValueError as e:
            QMessageBox.warning(self, 'Ошибка валидации', f'Некорректное значение координаты: {e}')
            return None


class TiltPlaneDialog(QDialog):
    """Диалог для задания крена на выбранной секции."""

    def __init__(
        self,
        section_infos: List[Dict[str, Any]],
        parent=None,
        *,
        title: str = 'Настройка крена секции',
        note_text: str = 'Укажите модуль отклонения в миллиметрах. Направление останется прежним.',
    ):
        super().__init__(parent)
        self.section_infos = section_infos
        self.setWindowTitle(title)
        self.setModal(True)

        layout = QVBoxLayout()
        form = QFormLayout()

        self.section_combo = QComboBox()
        for info in self.section_infos:
            height = info.get('height', 0.0)
            offset_mm = info.get('offset_len_mm', 0.0)
            segment_name = info.get('segment_name', '')
            section_name = info.get('section_name', '')
            section_num = info.get('section_num', None)

            section_num_text = f"№{section_num}" if section_num is not None else "№?"
            if segment_name and section_name:
                text = f"{section_num_text} | Z={height:.2f}м | {segment_name} | {section_name} | крен={offset_mm:.2f}мм"
            elif segment_name:
                text = f"{section_num_text} | Z={height:.2f}м | {segment_name} | крен={offset_mm:.2f}мм"
            else:
                text = f"{section_num_text} | Z={height:.2f}м | крен={offset_mm:.2f}мм"

            self.section_combo.addItem(text, info)
        self.section_combo.currentIndexChanged.connect(self._on_section_changed)
        form.addRow('Секция:', self.section_combo)

        self.current_label = QLabel('—')
        form.addRow('Текущий крен:', self.current_label)

        self.target_spin = QDoubleSpinBox()
        self.target_spin.setDecimals(2)
        self.target_spin.setRange(0.0, 10000.0)
        self.target_spin.setSuffix(' мм')
        form.addRow('Желаемый крен:', self.target_spin)

        layout.addLayout(form)

        note = QLabel(note_text)
        note.setWordWrap(True)
        layout.addWidget(note)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.setLayout(layout)
        self._on_section_changed(self.section_combo.currentIndex())

    def _on_section_changed(self, index: int):
        info = self.section_combo.itemData(index)
        if not info:
            self.current_label.setText('—')
            return
        self.current_label.setText(f"{info['offset_len_mm']:.2f} мм")
        self.target_spin.setValue(max(info['offset_len_mm'], 0.0))

    def get_selected_info(self) -> Optional[Dict[str, Any]]:
        return self.section_combo.currentData()

    def get_target_offset_mm(self) -> float:
        return float(self.target_spin.value())
