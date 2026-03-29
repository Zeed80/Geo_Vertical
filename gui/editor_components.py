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
    QStackedWidget, QToolButton,
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
    """Виджет-группа для кнопок с рамкой и заголовком снизу. Поддерживает светлую и тёмную тему."""

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
        # Без явного color — наследует цвет текста из палитры (работает в обеих темах)
        self.title_label.setStyleSheet(
            'font-size: 9px; padding: 2px; background-color: transparent;'
        )
        main_layout.addWidget(self.title_label)

        # palette(mid) адаптируется к текущей теме (светлая/тёмная) без хардкода
        self.setStyleSheet("""
            QWidget#buttonGroup {
                border: 1px solid palette(mid);
                border-radius: 4px;
                background-color: transparent;
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
                # Для кнопок с фиксированным размером используем fixedWidth/Height
                min_w, max_w = widget.minimumWidth(), widget.maximumWidth()
                min_h, max_h = widget.minimumHeight(), widget.maximumHeight()
                w = min_w if (min_w == max_w and min_w > 0) else widget.sizeHint().width()
                h = min_h if (min_h == max_h and min_h > 0) else widget.sizeHint().height()
                total_width += w
                max_height = max(max_height, h)

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


class TabToolbarWidget(QWidget):
    """Компактная вкладочная панель инструментов 3D-редактора.
    Вкладки (Точки / Пояса / Секции / …) переключают набор кнопок в одной строке.
    Полная высота ~78px. Вкладки оформлены с рамкой и акцентной полосой."""

    # Цвета для светлой темы (defaults)
    _ACCENT_LIGHT  = '#0078d4'
    _ACCENT_DARK   = '#4da3e0'

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName('tabToolbar')

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 2, 4, 0)
        root.setSpacing(0)

        # --- Строка вкладок (высота 30px) ---
        tab_bar_widget = QWidget()
        tab_bar_widget.setObjectName('tabBarWidget')
        self._tab_bar_row = QHBoxLayout(tab_bar_widget)
        # отступ снизу 0 — вкладки "прилипают" к панели кнопок
        self._tab_bar_row.setContentsMargins(0, 2, 0, 0)
        self._tab_bar_row.setSpacing(2)
        tab_bar_widget.setFixedHeight(30)
        root.addWidget(tab_bar_widget)
        self._tab_bar_widget = tab_bar_widget

        # --- Область кнопок (стек страниц) ---
        self._stack = QStackedWidget()
        self._stack.setObjectName('tabStack')
        self._stack.setFixedHeight(52)
        root.addWidget(self._stack)

        self._tab_btns: List[QPushButton] = []
        self._current: int = 0
        self._is_dark: bool = False

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        # Применяем начальный стиль (светлая тема)
        self.apply_style(False)

    def add_tab(self, title: str, widgets: list) -> int:
        """Добавить вкладку с указанными виджетами-кнопками."""
        idx = len(self._tab_btns)

        tab_btn = QPushButton(title)
        tab_btn.setCheckable(True)
        tab_btn.setChecked(idx == 0)
        tab_btn.setFixedHeight(28)
        tab_btn.setObjectName('toolbarTabBtn')
        tab_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        tab_btn.clicked.connect(lambda _c, i=idx: self._activate(i))
        self._tab_bar_row.addWidget(tab_btn)
        self._tab_btns.append(tab_btn)

        panel = QWidget()
        panel.setObjectName('tabPanel')
        row = QHBoxLayout(panel)
        row.setContentsMargins(6, 3, 6, 3)
        row.setSpacing(4)
        for w in widgets:
            if w is not None:
                row.addWidget(w)
        row.addStretch()
        self._stack.addWidget(panel)

        # Переприменяем стиль чтобы новая кнопка получила правильный вид
        self.apply_style(self._is_dark)
        return idx

    def add_settings_button(self, button: QWidget):
        """Кнопка ⚙️ справа от вкладок (настройки панели)."""
        self._tab_bar_row.addStretch()
        self._tab_bar_row.addWidget(button)

    def _activate(self, idx: int):
        self._current = idx
        self._stack.setCurrentIndex(idx)
        for i, btn in enumerate(self._tab_btns):
            btn.setChecked(i == idx)
        # Обновить стили чтобы активная вкладка получила правильную границу
        self.apply_style(self._is_dark)

    # --- Совместимость с ToolPanelWidget ---
    def set_position(self, pos: str):
        pass

    def reflow(self):
        pass

    def orientation(self) -> Qt.Orientation:
        return Qt.Orientation.Horizontal

    def items(self) -> List[QWidget]:
        result = []
        for i in range(self._stack.count()):
            panel = self._stack.widget(i)
            if panel and panel.layout():
                lay = panel.layout()
                for j in range(lay.count()):
                    item = lay.itemAt(j)
                    if item and item.widget():
                        result.append(item.widget())
        return result

    def apply_style(self, is_dark: bool):
        """Применить тему. Вкладки оформлены как настоящие tabs:
        рамка на 3 сторонах, активная — акцентный цвет, неактивная — серая."""
        self._is_dark = is_dark

        if is_dark:
            accent        = self._ACCENT_DARK
            panel_bg      = '#1e1e21'
            bar_bg        = '#2d2d30'
            inactive_bg   = '#3a3a3e'
            inactive_text = '#a0a0a0'
            inactive_border = '#555558'
            hover_bg      = '#464649'
            active_text   = '#ffffff'
            stack_border  = '#555558'
        else:
            accent        = self._ACCENT_LIGHT
            panel_bg      = '#ffffff'
            bar_bg        = '#f0f0f0'
            inactive_bg   = '#e4e4e4'
            inactive_text = '#606060'
            inactive_border = '#c0c0c0'
            hover_bg      = '#d8d8d8'
            active_text   = '#ffffff'
            stack_border  = '#c8c8c8'

        # Цвет фона вкладки совпадает с panel_bg (эффект "открытой" вкладки)
        # Нижняя граница активной вкладки = panel_bg (визуально стирает рамку снизу)
        self._tab_bar_widget.setStyleSheet(
            f'QWidget#tabBarWidget {{ background: {bar_bg}; }}'
        )
        self._stack.setStyleSheet(
            f'QStackedWidget#tabStack {{ '
            f'border: 1px solid {stack_border}; '
            f'border-top: 2px solid {accent}; '
            f'background: {panel_bg}; }}'
        )

        active_style = f"""
            QPushButton#toolbarTabBtn:checked {{
                font-size: 9px; font-weight: 700;
                border: 1px solid {accent};
                border-bottom: 1px solid {panel_bg};
                border-radius: 4px 4px 0px 0px;
                padding: 2px 12px 3px 12px;
                background: {panel_bg};
                color: {accent};
                margin-bottom: -1px;
            }}
        """
        inactive_style = f"""
            QPushButton#toolbarTabBtn {{
                font-size: 9px; font-weight: 500;
                border: 1px solid {inactive_border};
                border-bottom: 1px solid {inactive_border};
                border-radius: 4px 4px 0px 0px;
                padding: 2px 12px 3px 12px;
                background: {inactive_bg};
                color: {inactive_text};
            }}
            QPushButton#toolbarTabBtn:hover:!checked {{
                background: {hover_bg};
                color: {inactive_text};
                border-color: {accent};
            }}
        """
        combined = inactive_style + active_style
        for btn in self._tab_btns:
            btn.setStyleSheet(combined)


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
