"""
Обновлённая панель конструктора башни. Пользователь задаёт части башни,
их форму, количество поясов и размеры. Результат — TowerBlueprintV2.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QGroupBox,
    QFormLayout,
    QComboBox,
    QSpinBox,
    QDoubleSpinBox,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QPushButton,
    QHBoxLayout,
    QMessageBox,
    QHeaderView,
    QTabWidget,
    QInputDialog,
    QFileDialog,
)

from core.tower_generator import TowerSegmentSpec, TowerBlueprintV2, TowerSectionSpec
from core.db.profile_manager import ProfileManager
from gui.tower_builder_wizard import TowerBuilderWizard
from gui.lattice_editor import LatticeEditorWidget
from gui.equipment_editor import EquipmentEditorWidget
from gui.calculation_tab import CalculationTab
from gui.unified_tower_builder_panel import UnifiedTowerBuilderPanel


class TowerBuilderPanel(QWidget):
    """UI для создания башни из нескольких частей."""

    COL_NAME = 0
    COL_SHAPE = 1
    COL_HEIGHT = 2
    COL_FACES_LEVELS = 3  # Граней/Поясов (одно и то же)
    COL_BASE = 4
    COL_TOP = 5

    SECTION_COL_NAME = 0
    SECTION_COL_HEIGHT = 1
    SECTION_COL_DEVIATION_X = 2  # Девиация X в мм
    SECTION_COL_DEVIATION_Y = 3  # Девиация Y в мм

    blueprintRequested = pyqtSignal(TowerBlueprintV2)
    statusMessage = pyqtSignal(str)
    towerVisualizationRequested = pyqtSignal(TowerBlueprintV2)  # Сигнал для запроса визуализации в основном окне

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.profile_manager = ProfileManager()
        self._templates = self._build_templates()
        self._part_sections: List[List[Dict[str, float]]] = []
        self._section_tables: Dict[int, QTableWidget] = {}
        self._updating_sections = False
        
        # Temporary storage for lattice specs per part index
        # key: part_index, value: dict (lattice_type, profile_spec)
        self._part_lattice_specs: Dict[int, Dict] = {}
        
        # Режим работы: 'tabs' (вкладки) или 'unified' (единая панель)
        self._mode = 'tabs'
        self._unified_panel: Optional[UnifiedTowerBuilderPanel] = None
        
        self._setup_ui()
        self._reset_parts()
        self._refresh_template_combo()

    # ------------------------------------------------------------------ UI
    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Панель переключения режимов
        mode_layout = QHBoxLayout()
        mode_layout.setContentsMargins(4, 4, 4, 4)
        
        mode_label = QLabel("Режим конструктора:")
        mode_layout.addWidget(mode_label)
        
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Вкладки (классический)", "tabs")
        self.mode_combo.addItem("Единая панель (новый)", "unified")
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        mode_layout.addWidget(self.mode_combo)
        
        mode_layout.addStretch()
        main_layout.addLayout(mode_layout)
        
        # Контейнер для панелей
        self.panel_container = QWidget()
        panel_container_layout = QVBoxLayout(self.panel_container)
        panel_container_layout.setContentsMargins(0, 0, 0, 0)
        
        # Старый режим: вкладки
        self.tabs = QTabWidget()
        
        # Tab 1: Geometry
        self.geometry_tab = QWidget()
        self._setup_geometry_ui(self.geometry_tab)
        self.tabs.addTab(self.geometry_tab, "Геометрия")
        
        # Tab 2: Lattice
        self.lattice_editor = LatticeEditorWidget(self.profile_manager)
        self.tabs.addTab(self.lattice_editor, "Решетка")
        
        # Tab 3: Equipment
        self.equipment_editor = EquipmentEditorWidget()
        self.tabs.addTab(self.equipment_editor, "Оборудование")
        
        # Tab 4: Calculation
        self.calculation_tab = CalculationTab()
        self.tabs.addTab(self.calculation_tab, "Расчет нагрузки")
        
        panel_container_layout.addWidget(self.tabs)
        self.panel_container.setLayout(panel_container_layout)
        
        main_layout.addWidget(self.panel_container, stretch=1)
        
        # Кнопка построения (для режима вкладок)
        self.generate_btn = QPushButton("Построить башню")
        self.generate_btn.clicked.connect(self._emit_blueprint)
        main_layout.addWidget(self.generate_btn)
        
        # Инициализировать режим
        self._on_mode_changed()

    def _setup_geometry_ui(self, parent_widget: QWidget) -> None:
        layout = QVBoxLayout(parent_widget)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        instrument_group = QGroupBox("Положение прибора")
        instrument_form = QFormLayout()

        self.distance_spin = QDoubleSpinBox()
        self.distance_spin.setRange(1.0, 1000.0)
        self.distance_spin.setValue(60.0)
        self.distance_spin.setSuffix(" м")
        instrument_form.addRow("Расстояние:", self.distance_spin)

        self.angle_spin = QDoubleSpinBox()
        self.angle_spin.setRange(-360.0, 360.0)
        self.angle_spin.setDecimals(1)
        self.angle_spin.setSuffix(" °")
        instrument_form.addRow("Угол:", self.angle_spin)

        self.instrument_height_spin = QDoubleSpinBox()
        self.instrument_height_spin.setRange(-5.0, 100.0)
        self.instrument_height_spin.setDecimals(2)
        self.instrument_height_spin.setValue(1.7)
        self.instrument_height_spin.setSuffix(" м")
        instrument_form.addRow("Высота прибора:", self.instrument_height_spin)

        self.rotation_spin = QDoubleSpinBox()
        self.rotation_spin.setRange(0.0, 360.0)
        self.rotation_spin.setDecimals(1)
        self.rotation_spin.setSuffix(" °")
        instrument_form.addRow("Поворот граней:", self.rotation_spin)

        self.deviation_spin = QDoubleSpinBox()
        self.deviation_spin.setRange(0.0, 1000.0)
        self.deviation_spin.setDecimals(1)
        self.deviation_spin.setValue(5.0)
        self.deviation_spin.setSuffix(" мм")
        instrument_form.addRow("Девиация точек (случайная):", self.deviation_spin)

        instrument_group.setLayout(instrument_form)
        layout.addWidget(instrument_group)

        header_row = QHBoxLayout()
        title = QLabel("Части башни (снизу вверх)")
        title.setStyleSheet("font-weight: 600;")
        header_row.addWidget(title)
        header_row.addStretch()
        self.summary_label = QLabel("")
        header_row.addWidget(self.summary_label)
        layout.addLayout(header_row)

        self.parts_table = QTableWidget(0, 6)
        self.parts_table.setHorizontalHeaderLabels(
            [
                "Название",
                "Форма",
                "Высота (м)",
                "Граней/Поясов",
                "Нижний размер (м)",
                "Верхний размер (м)",
            ]
        )
        header = self.parts_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.parts_table.verticalHeader().setVisible(False)
        self.parts_table.currentCellChanged.connect(self._on_part_selection_changed)
        layout.addWidget(self.parts_table, stretch=1)

        controls = QHBoxLayout()
        add_btn = QPushButton("Добавить часть")
        add_btn.clicked.connect(self._handle_add_part)
        remove_btn = QPushButton("Удалить")
        remove_btn.clicked.connect(self._remove_part_row)
        up_btn = QPushButton("Выше")
        up_btn.clicked.connect(lambda: self._move_part(-1))
        down_btn = QPushButton("Ниже")
        down_btn.clicked.connect(lambda: self._move_part(1))
        controls.addWidget(add_btn)
        controls.addWidget(remove_btn)
        controls.addWidget(up_btn)
        controls.addWidget(down_btn)
        controls.addStretch()
        
        # Выбор шаблона
        self.template_combo = QComboBox()
        self.template_combo.setMinimumWidth(150)
        self.template_combo.setMaximumWidth(250)
        controls.addWidget(self.template_combo)
        template_btn = QPushButton("Применить шаблон")
        template_btn.clicked.connect(self._apply_selected_template)
        controls.addWidget(template_btn)
        save_template_btn = QPushButton("Сохранить шаблон")
        save_template_btn.clicked.connect(self._save_as_template)
        wizard_btn = QPushButton("Мастер…")
        wizard_btn.clicked.connect(self._open_wizard)
        controls.addWidget(save_template_btn)
        controls.addWidget(wizard_btn)
        layout.addLayout(controls)

        sections_header = QHBoxLayout()
        sections_label = QLabel("Секции каждой части")
        sections_label.setStyleSheet("font-weight: 600;")
        sections_header.addWidget(sections_label)
        self.sections_hint = QLabel("Задайте высоту и смещение секций для выделенной части")
        self.sections_hint.setStyleSheet("color: #666;")
        sections_header.addStretch()
        sections_header.addWidget(self.sections_hint)
        layout.addLayout(sections_header)

        self.sections_tabs = QTabWidget()
        self.sections_tabs.setTabPosition(QTabWidget.TabPosition.North)
        self.sections_tabs.setDocumentMode(True)
        self.sections_tabs.currentChanged.connect(self._on_section_tab_changed)
        layout.addWidget(self.sections_tabs, stretch=1)

    # ------------------------------------------------------------------ parts helpers
    def _reset_parts(self) -> None:
        self.parts_table.setRowCount(0)
        self._part_sections = []
        self._part_lattice_specs = {}
        self.sections_tabs.clear()
        self._add_part_row(
            {
                "name": "Часть 1",
                "shape": "prism",
                "faces": 4,
                "height": 5.0,
                "levels": 4,
                "base_size": 4.0,
                "top_size": 4.0,
            }
        )
        self._update_summary()
        self._refresh_section_tabs()

    def _handle_add_part(self) -> None:
        index = self.parts_table.rowCount() + 1
        prev_top = self._double_value(self.parts_table.rowCount() - 1, self.COL_TOP) if self.parts_table.rowCount() > 0 else 4.0
        self._add_part_row(
            {
                "name": f"Часть {index}",
                "shape": "prism",
                "faces": 4,
                "height": 5.0,
                "levels": 4,
                "base_size": prev_top,
                "top_size": prev_top,
            }
        )

    def _add_part_row(self, data: Dict[str, float], sections: Optional[List[Dict[str, float]]] = None) -> None:
        row = self.parts_table.rowCount()
        self.parts_table.insertRow(row)
        sections_data = sections if sections is not None else self._default_sections_for_part(data, row)
        if row >= len(self._part_sections):
            self._part_sections.append(sections_data)
        else:
            self._part_sections.insert(row, sections_data)
            
        # Init lattice spec for this part
        if row not in self._part_lattice_specs:
            self._part_lattice_specs[row] = {
                "lattice_type": data.get("lattice_type", "cross"),
                "profile_spec": data.get("profile_spec", {})
            }

        name_item = QTableWidgetItem(str(data.get("name", f"Часть {row + 1}")))
        self.parts_table.setItem(row, self.COL_NAME, name_item)

        shape_widget = self._create_shape_widget(data.get("shape", "prism"))
        self.parts_table.setCellWidget(row, self.COL_SHAPE, shape_widget)

        height_widget = self._create_double_spin(
            value=float(data.get("height", 5.0)),
            minimum=0.5,
            maximum=500.0,
            decimals=2,
        )
        self.parts_table.setCellWidget(row, self.COL_HEIGHT, height_widget)

        # Граней/Поясов - одно и то же значение
        faces_levels_value = int(data.get("levels", data.get("faces", 4)))
        faces_levels_widget = self._create_int_spin(
            value=faces_levels_value,
            minimum=3,
            maximum=64,
        )
        self.parts_table.setCellWidget(row, self.COL_FACES_LEVELS, faces_levels_widget)

        base_widget = self._create_double_spin(
            value=float(data.get("base_size", 4.0)),
            minimum=0.5,
            maximum=200.0,
        )
        self.parts_table.setCellWidget(row, self.COL_BASE, base_widget)

        top_widget = self._create_double_spin(
            value=float(data.get("top_size", 4.0)),
            minimum=0.1,
            maximum=200.0,
        )
        self.parts_table.setCellWidget(row, self.COL_TOP, top_widget)

        self._update_summary()
        self._refresh_section_tabs()

    def _create_shape_widget(self, value: str) -> QComboBox:
        combo = QComboBox()
        combo.addItem("Призма", "prism")
        combo.addItem("Усечённая пирамида", "truncated_pyramid")
        index = combo.findData(value)
        combo.setCurrentIndex(index if index >= 0 else 0)
        combo.currentIndexChanged.connect(self._on_parts_changed)
        return combo

    def _create_int_spin(self, *, value: int, minimum: int, maximum: int) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(minimum, maximum)
        spin.setValue(value)
        spin.valueChanged.connect(lambda *_: self._on_parts_changed())
        return spin

    def _create_double_spin(
        self,
        *,
        value: float,
        minimum: float,
        maximum: float,
        decimals: int = 3,
        suffix: str = "",
    ) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(decimals)
        spin.setValue(value)
        spin.setSuffix(suffix)
        spin.valueChanged.connect(lambda *_: self._on_parts_changed())
        return spin

    def _remove_part_row(self) -> None:
        row = self.parts_table.currentRow()
        if row < 0:
            row = self.parts_table.rowCount() - 1
        if row < 0:
            return
        self.parts_table.removeRow(row)
        if row < len(self._part_sections):
            self._part_sections.pop(row)
        if row in self._part_lattice_specs:
            del self._part_lattice_specs[row]
            
        if not self._part_sections and self.parts_table.rowCount() > 0:
            while len(self._part_sections) < self.parts_table.rowCount():
                part_index = len(self._part_sections)
                part_height = self._part_height(part_index) if part_index < self.parts_table.rowCount() else 1.0
                self._part_sections.append(self._default_sections_for_part({"height": part_height}, part_index))
        if self.parts_table.rowCount() == 0:
            self._reset_parts()
        else:
            self._update_summary()
            self._refresh_section_tabs()  # Это обновит z_base для всех секций

    def _move_part(self, direction: int) -> None:
        row = self.parts_table.currentRow()
        target = row + direction
        if row < 0 or target < 0 or target >= self.parts_table.rowCount():
            return
        data = self._serialize_row(row)
        self.parts_table.removeRow(row)
        self.parts_table.insertRow(target)
        self._apply_row_data(target, data)
        if row < len(self._part_sections):
            sections_data = self._part_sections.pop(row)
            self._part_sections.insert(target, sections_data)
        
        # Move lattice spec
        spec = self._part_lattice_specs.pop(row, {})
        # Handle reordering of other specs?
        # Ideally re-index everything.
        # Simply re-generating dict is easiest if we serialized fully.
        # But we are storing in a side-dict.
        # Let's just rebuild self._part_lattice_specs properly.
        # Too complex for now, let's assume it's fine or just clear and reload from 'data' if we stored it there.
        # We did NOT store lattice in _serialize_row yet.
        self._part_lattice_specs[target] = spec
        
        self.parts_table.setCurrentCell(target, 0)
        self._update_summary()
        self._refresh_section_tabs()

    def _serialize_row(self, row: int) -> Dict[str, float]:
        faces_levels = self._int_value(row, self.COL_FACES_LEVELS)
        
        # Get lattice spec
        lattice_spec = self._part_lattice_specs.get(row, {})
        
        return {
            "name": self._text(row, self.COL_NAME) or f"Часть {row + 1}",
            "shape": self._shape_value(row),
            "faces": faces_levels,
            "height": self._double_value(row, self.COL_HEIGHT),
            "levels": faces_levels,
            "base_size": self._double_value(row, self.COL_BASE),
            "top_size": self._double_value(row, self.COL_TOP),
            "sections": self._serialize_sections(row),
            "lattice_type": lattice_spec.get("lattice_type", "cross"),
            "profile_spec": lattice_spec.get("profile_spec", {}),
        }

    def _apply_row_data(self, row: int, data: Dict[str, float]) -> None:
        self.parts_table.setItem(row, self.COL_NAME, QTableWidgetItem(str(data.get("name", f"Часть {row+1}"))))
        self.parts_table.setCellWidget(row, self.COL_SHAPE, self._create_shape_widget(data.get("shape", "prism")))
        self.parts_table.setCellWidget(
            row,
            self.COL_HEIGHT,
            self._create_double_spin(value=float(data.get("height", 5.0)), minimum=0.5, maximum=500.0),
        )
        # Граней/Поясов - одно и то же значение
        faces_levels_value = int(data.get("levels", data.get("faces", 4)))
        self.parts_table.setCellWidget(
            row,
            self.COL_FACES_LEVELS,
            self._create_int_spin(value=faces_levels_value, minimum=3, maximum=64),
        )
        self.parts_table.setCellWidget(
            row,
            self.COL_BASE,
            self._create_double_spin(value=float(data.get("base_size", 4.0)), minimum=0.5, maximum=200.0),
        )
        self.parts_table.setCellWidget(
            row,
            self.COL_TOP,
            self._create_double_spin(value=float(data.get("top_size", 4.0)), minimum=0.1, maximum=200.0),
        )
        
        # Restore lattice spec
        self._part_lattice_specs[row] = {
            "lattice_type": data.get("lattice_type", "cross"),
            "profile_spec": data.get("profile_spec", {})
        }

    # ------------------------------------------------------------------ data helpers
    def _shape_value(self, row: int) -> str:
        widget = self.parts_table.cellWidget(row, self.COL_SHAPE)
        if isinstance(widget, QComboBox):
            return widget.currentData()
        return "prism"

    def _double_value(self, row: int, column: int) -> float:
        widget = self.parts_table.cellWidget(row, column)
        if isinstance(widget, QDoubleSpinBox):
            return float(widget.value())
        item = self.parts_table.item(row, column)
        if item:
            try:
                return float(item.text().replace(",", "."))
            except ValueError:
                return 0.0
        return 0.0

    def _int_value(self, row: int, column: int) -> int:
        widget = self.parts_table.cellWidget(row, column)
        if isinstance(widget, QSpinBox):
            return int(widget.value())
        item = self.parts_table.item(row, column)
        if item:
            try:
                return int(item.text())
            except ValueError:
                return 0
        return 0

    def _text(self, row: int, column: int) -> str:
        item = self.parts_table.item(row, column)
        return item.text().strip() if item else ""

    def _default_sections_for_part(self, data: Dict[str, float], part_index: int = 0) -> List[Dict[str, float]]:
        part_height = float(data.get("height", 5.0))
        accumulated_height = self._get_accumulated_height(part_index)
        lower_height = 0.0
        upper_height = part_height
        
        return [
            {
                "name": "Нижняя",
                "height": lower_height,
                "deviation_x_mm": 0.0,
                "deviation_y_mm": 0.0,
                "z_base": accumulated_height,
            },
            {
                "name": "Верхняя",
                "height": upper_height,
                "deviation_x_mm": 0.0,
                "deviation_y_mm": 0.0,
                "z_base": accumulated_height + lower_height,
            }
        ]
    
    def _get_accumulated_height(self, part_index: int) -> float:
        total = 0.0
        for row in range(part_index):
            total += self._part_height(row)
        return total

    def _part_height(self, row: int) -> float:
        return float(self._double_value(row, self.COL_HEIGHT))

    def _refresh_section_tabs(self) -> None:
        self._updating_sections = True
        while len(self._part_sections) < self.parts_table.rowCount():
            part_index = len(self._part_sections)
            part_height = self._part_height(part_index) if part_index < self.parts_table.rowCount() else 1.0
            self._part_sections.append(self._default_sections_for_part({"height": part_height}, part_index))
        self._update_all_sections_z_base()
        self.sections_tabs.clear()
        self._section_tables.clear()
        for row in range(self.parts_table.rowCount()):
            widget = self._build_section_tab(row)
            title = self._text(row, self.COL_NAME) or f"Часть {row + 1}"
            self.sections_tabs.addTab(widget, title)
        self._updating_sections = False
        current = max(0, self.parts_table.currentRow())
        if 0 <= current < self.sections_tabs.count():
            self.sections_tabs.setCurrentIndex(current)
    
    def _update_all_sections_z_base(self) -> None:
        for part_index in range(len(self._part_sections)):
            accumulated_height = self._get_accumulated_height(part_index)
            sections = self._part_sections[part_index]
            if not sections:
                continue
            current_z = accumulated_height
            for section in sections:
                section["z_base"] = current_z
                current_z += section.get("height", 0.0)

    def _build_section_tab(self, part_index: int) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        info = QLabel("Высота секции — вклад в суммарную высоту части. ΔX/ΔY — смещение центра.")
        info.setWordWrap(True)
        info.setStyleSheet("color: #666; font-size: 9pt;")
        layout.addWidget(info)

        table = QTableWidget(0, 4)
        table.setHorizontalHeaderLabels(["Секция", "Высота (м)", "Девиация X (мм)", "Девиация Y (мм)"])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.verticalHeader().setVisible(False)
        table.setProperty("part_index", part_index)
        table.itemChanged.connect(self._on_section_item_changed)
        self._section_tables[part_index] = table
        layout.addWidget(table, stretch=1)
        self._apply_sections_to_table(part_index)

        buttons = QHBoxLayout()
        add_btn = QPushButton("Добавить секцию")
        add_btn.clicked.connect(lambda *_: self._add_section(part_index))
        remove_btn = QPushButton("Удалить")
        remove_btn.clicked.connect(lambda *_: self._remove_section(part_index))
        random_offset_btn = QPushButton("Применить случайное смещение")
        random_offset_btn.clicked.connect(lambda *_: self._apply_random_offset(part_index))
        buttons.addWidget(add_btn)
        buttons.addWidget(remove_btn)
        buttons.addWidget(random_offset_btn)
        buttons.addStretch()
        layout.addLayout(buttons)
        return widget

    def _recalculate_upper_section_height(self, part_index: int) -> None:
        if part_index >= len(self._part_sections):
            return
        sections = self._part_sections[part_index]
        if len(sections) < 2:
            return
        
        part_height = self._part_height(part_index)
        other_sections_height = sum(s.get("height", 0.0) for s in sections[:-1])
        upper_section = sections[-1]
        upper_section["height"] = max(0.01, part_height - other_sections_height)
        
        accumulated_height = self._get_accumulated_height(part_index)
        z_base = accumulated_height
        for s in sections:
            s["z_base"] = z_base
            z_base += s.get("height", 0.0)
    
    def _apply_sections_to_table(self, part_index: int) -> None:
        table = self._section_tables.get(part_index)
        if table is None:
            return
        self._updating_sections = True
        sections = self._part_sections[part_index] if part_index < len(self._part_sections) else []
        table.setRowCount(len(sections))
        for row, entry in enumerate(sections):
            table.setItem(row, self.SECTION_COL_NAME, QTableWidgetItem(str(entry.get("name", f"Секция {row + 1}"))))
            height_item = QTableWidgetItem(f"{float(entry.get('height', 0.0)):.3f}")
            if row == len(sections) - 1:
                height_item.setFlags(height_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                height_item.setToolTip("Высота верхней секции рассчитывается автоматически")
            table.setItem(row, self.SECTION_COL_HEIGHT, height_item)
            deviation_x = entry.get("deviation_x_mm", entry.get("offset_x", 0.0) * 1000.0 if entry.get("offset_x") else 0.0)
            deviation_y = entry.get("deviation_y_mm", entry.get("offset_y", 0.0) * 1000.0 if entry.get("offset_y") else 0.0)
            table.setItem(row, self.SECTION_COL_DEVIATION_X, QTableWidgetItem(f"{float(deviation_x):.1f}"))
            table.setItem(row, self.SECTION_COL_DEVIATION_Y, QTableWidgetItem(f"{float(deviation_y):.1f}"))
            for col in range(table.columnCount()):
                item = table.item(row, col)
                if item:
                    item.setData(Qt.ItemDataRole.UserRole, part_index)
        self._updating_sections = False

    def _add_section(self, part_index: int) -> None:
        if part_index >= len(self._part_sections):
            return
        sections = self._part_sections[part_index]
        if len(sections) < 2:
            part_height = self._part_height(part_index)
            accumulated_height = self._get_accumulated_height(part_index)
            sections.clear()
            sections.extend(self._default_sections_for_part({"height": part_height}, part_index))
            self._apply_sections_to_table(part_index)
            self._update_summary()
            return
        
        total_height = self._part_height(part_index)
        other_sections_height = sum(s.get("height", 0.0) for s in sections[:-1])
        remaining = total_height - other_sections_height
        new_height = max(0.1, remaining * 0.5)
        accumulated_height = self._get_accumulated_height(part_index)
        z_base = accumulated_height
        for s in sections[:-1]:
            z_base += s.get("height", 0.0)
        
        sections.insert(-1, {
            "name": f"Секция {len(sections)}",
            "height": new_height,
            "deviation_x_mm": 0.0,
            "deviation_y_mm": 0.0,
            "z_base": z_base,
        })
        
        self._recalculate_upper_section_height(part_index)
        self._apply_sections_to_table(part_index)
        self._update_summary()

    def _remove_section(self, part_index: int) -> None:
        table = self._section_tables.get(part_index)
        if table is None or part_index >= len(self._part_sections):
            return
        sections = self._part_sections[part_index]
        if len(sections) <= 2:
            QMessageBox.information(
                self,
                "Невозможно удалить",
                "Нельзя удалить нижнюю и верхнюю секции. Они обязательны для каждой части."
            )
            return
        
        row = table.currentRow()
        if row < 0:
            row = table.rowCount() - 1
        if row < 0:
            return
        
        if row == 0 or row == len(sections) - 1:
            QMessageBox.information(
                self,
                "Невозможно удалить",
                "Нельзя удалить нижнюю и верхнюю секции. Они обязательны для каждой части."
            )
            return
        
        sections.pop(row)
        self._recalculate_upper_section_height(part_index)
        self._apply_sections_to_table(part_index)
        self._update_summary()

    def _apply_random_offset(self, part_index: int) -> None:
        import random
        import math
        
        if part_index >= len(self._part_sections):
            return
        
        sections = self._part_sections[part_index]
        if len(sections) < 2:
            return
        
        deviation_mm = float(self.deviation_spin.value())
        if deviation_mm <= 0:
            QMessageBox.warning(
                self,
                "Ошибка",
                "Установите значение девиации больше 0 для применения случайного смещения."
            )
            return
        
        angle_rad = random.uniform(0, 2 * math.pi)
        offset_magnitude_mm = random.uniform(-deviation_mm, deviation_mm)
        upper_section = sections[-1]
        upper_offset_x_mm = offset_magnitude_mm * math.cos(angle_rad)
        upper_offset_y_mm = offset_magnitude_mm * math.sin(angle_rad)
        part_height = self._part_height(part_index)
        if part_height <= 0:
            return
        
        for section in sections:
            section_height = section.get("height", 0.0)
            height_fraction = section_height / part_height if part_height > 0 else 0.0
            section_offset_x_mm = upper_offset_x_mm * height_fraction
            section_offset_y_mm = upper_offset_y_mm * height_fraction
            section["deviation_x_mm"] = section_offset_x_mm
            section["deviation_y_mm"] = section_offset_y_mm
        
        self._apply_sections_to_table(part_index)
        self.statusMessage.emit(f"Применено случайное смещение: верхняя секция смещена на {offset_magnitude_mm:.1f} мм")

    def _on_section_item_changed(self, item: QTableWidgetItem) -> None:
        if self._updating_sections or item is None:
            return
        table = item.tableWidget()
        part_index = table.property("part_index")
        if part_index is None or part_index >= len(self._part_sections):
            return
        row = item.row()
        sections = self._part_sections[part_index]
        if row >= len(sections):
            return
        text = item.text().strip()
        entry = sections[row]
        if item.column() == self.SECTION_COL_NAME:
            entry["name"] = text or f"Секция {row + 1}"
        else:
            try:
                value = float(text.replace(",", ".")) if text else 0.0
            except ValueError:
                value = 0.0
            if item.column() == self.SECTION_COL_HEIGHT:
                if row == len(sections) - 1:
                    self._apply_sections_to_table(part_index)
                    QMessageBox.information(
                        self,
                        "Нельзя изменить",
                        "Высота верхней секции рассчитывается автоматически и не может быть изменена вручную."
                    )
                    return
                
                new_height = value if row == 0 else max(0.01, value)
                entry["height"] = new_height
                self._recalculate_upper_section_height(part_index)
                self._apply_sections_to_table(part_index)
            elif item.column() == self.SECTION_COL_DEVIATION_X:
                entry["deviation_x_mm"] = value
            elif item.column() == self.SECTION_COL_DEVIATION_Y:
                entry["deviation_y_mm"] = value
        self._update_summary()

    def _on_part_selection_changed(self, current_row: int, *_args) -> None:
        if current_row < 0:
            return
        if not self._updating_sections and current_row < self.sections_tabs.count():
            self.sections_tabs.setCurrentIndex(current_row)
            
        # Update Lattice Editor with temporary Spec object for this part
        # Create a temp spec using current data
        part_data = self._serialize_row(current_row)
        temp_spec = TowerSegmentSpec.from_dict(part_data)
        
        # We pass this object to lattice editor
        # Note: modifications in editor should update our _part_lattice_specs
        # But we need a way to sync back.
        # LatticeEditor modifies the object passed to it.
        # So if we pass an object from our internal state, it works?
        # _serialize_row creates a NEW dict.
        # So we need to maintain a persistent object or update back.
        
        # Let's make LatticeEditor take a callback or we handle logic here.
        # Or we just let LatticeEditor modify the spec, and we save it back when tab changes or generate called.
        # Actually LatticeEditor modifies 'self.current_segment' which is the object we passed.
        # So we need to pass an object that lives longer.
        
        # Creating a full SegmentSpec just for editing seems heavy if we regenerate it often.
        # Better: update `_part_lattice_specs` when LatticeEditor changes something.
        # Since LatticeEditor just modifies attributes of the passed object, we can't easily know.
        # Let's just create a "proxy" object or make LatticeEditor emit signals.
        # Actually, LatticeEditor modifies `.lattice_type` and `.profile_spec`.
        # We can pass a simple wrapper or just the spec dict?
        # The editor expects TowerSegmentSpec.
        
        self.lattice_editor.set_segment(temp_spec)
        
        # We need to capture changes from temp_spec back to our storage
        # Hack: Use a QTimer or signal?
        # Or make LatticeEditor emit 'changed' signal.
        # For now, let's assume the user clicks 'Generate' which calls _serialize_row again.
        # But _serialize_row reads from `_part_lattice_specs`. 
        # We need to write `temp_spec` back to `_part_lattice_specs` when it changes.
        # The editor doesn't emit signal.
        
        # Solution: Subclass LatticeEditor or modify it to emit signal.
        # Or just monkey-patch the temp_spec to update our dict.
        
        # Let's rely on "Generate" to gather data, but we need to save edits.
        # I will make _part_lattice_specs store the actual SegmentSpec objects?
        # No, mixing data models is messy.
        
        # I'll update LatticeEditor to have a save mechanism or signal.
        # But I can't edit it now easily without another tool call.
        # I will store the `temp_spec` as `self._current_editing_spec` and check it before switching parts.
        
        if hasattr(self, "_current_editing_spec") and self._current_editing_part_idx is not None:
            # Save previous
            self._part_lattice_specs[self._current_editing_part_idx] = {
                "lattice_type": self._current_editing_spec.lattice_type,
                "profile_spec": self._current_editing_spec.profile_spec
            }
            
        self._current_editing_spec = temp_spec
        self._current_editing_part_idx = current_row

    def _on_section_tab_changed(self, index: int) -> None:
        if self._updating_sections or index < 0:
            return
        if index < self.parts_table.rowCount():
            self.parts_table.setCurrentCell(index, 0)

    def _on_parts_changed(self, *_args):
        for part_index in range(len(self._part_sections)):
            sections = self._part_sections[part_index]
            part_height = self._part_height(part_index)
            
            if len(sections) < 2:
                sections.clear()
                sections.extend(self._default_sections_for_part({"height": part_height}, part_index))
            else:
                self._recalculate_upper_section_height(part_index)
        
        self._update_summary()
        current_part = self.parts_table.currentRow()
        if current_part >= 0 and current_part < len(self._part_sections):
            self._apply_sections_to_table(current_part)

    def _collect_segments(self) -> List[Dict[str, float]]:
        # Ensure we save the currently editing spec if any
        if hasattr(self, "_current_editing_spec") and self._current_editing_part_idx is not None:
            self._part_lattice_specs[self._current_editing_part_idx] = {
                "lattice_type": self._current_editing_spec.lattice_type,
                "profile_spec": self._current_editing_spec.profile_spec
            }
            
        segments: List[Dict[str, float]] = []
        for row in range(self.parts_table.rowCount()):
            segments.append(self._serialize_row(row))
        return segments

    def _serialize_sections(self, row: int) -> List[Dict[str, float]]:
        if row >= len(self._part_sections):
            return []
        sections: List[Dict[str, float]] = []
        for index, entry in enumerate(self._part_sections[row]):
            deviation_x_mm = entry.get("deviation_x_mm", entry.get("offset_x", 0.0) * 1000.0 if entry.get("offset_x") else 0.0)
            deviation_y_mm = entry.get("deviation_y_mm", entry.get("offset_y", 0.0) * 1000.0 if entry.get("offset_y") else 0.0)
            sections.append(
                {
                    "name": entry.get("name", f"Секция {index + 1}"),
                    "height": float(entry.get("height", 0.0)),
                    "offset_x": float(deviation_x_mm / 1000.0),
                    "offset_y": float(deviation_y_mm / 1000.0),
                }
            )
        return sections

    def _sections_from_spec(self, segment: TowerSegmentSpec, part_index: int = 0) -> List[Dict[str, float]]:
        sections = []
        if getattr(segment, "sections", None) and len(segment.sections) >= 2:
            accumulated_height = self._get_accumulated_height(part_index)
            z_base = accumulated_height
            for section in segment.sections:
                sections.append({
                    "name": section.name,
                    "height": float(section.height),
                    "deviation_x_mm": float(section.offset_x * 1000.0),
                    "deviation_y_mm": float(section.offset_y * 1000.0),
                    "z_base": z_base,
                })
                z_base += float(section.height)
        else:
            sections = self._default_sections_for_part({"height": segment.height}, part_index)
        return sections

    # ------------------------------------------------------------------ blueprint API
    def build_blueprint(self) -> TowerBlueprintV2:
        segments = []
        for data in self._collect_segments():
            height = float(data["height"])
            levels = max(1, int(data["levels"]))
            base_size = float(data["base_size"])
            top_size = float(data["top_size"])
            section_specs = [
                TowerSectionSpec(
                    name=section["name"],
                    height=float(section["height"]),
                    offset_x=float(section["offset_x"]),
                    offset_y=float(section["offset_y"]),
                )
                for section in data.get("sections", [])
            ]
            segments.append(
                TowerSegmentSpec(
                    name=data["name"],
                    shape=data["shape"],
                    faces=max(3, int(data["faces"])),
                    height=height,
                    levels=levels,
                    base_size=base_size,
                    top_size=top_size,
                    deviation_mm=0.0,
                    sections=section_specs,
                    lattice_type=data.get("lattice_type", "cross"),
                    profile_spec=data.get("profile_spec", {})
                )
            )
        if not segments:
            raise ValueError("Добавьте хотя бы одну часть башни.")

        blueprint = TowerBlueprintV2(
            segments=segments,
            instrument_distance=float(self.distance_spin.value()),
            instrument_angle_deg=float(self.angle_spin.value()),
            instrument_height=float(self.instrument_height_spin.value()),
            base_rotation_deg=float(self.rotation_spin.value()),
            default_deviation_mm=float(self.deviation_spin.value()),
        )
        
        # Add equipment to metadata
        if hasattr(self, "equipment_editor"):
            blueprint.metadata["equipment"] = self.equipment_editor.equipment_list
            
        blueprint.validate()
        return blueprint

    def set_blueprint(self, blueprint: Optional[TowerBlueprintV2]) -> None:
        """Установить чертеж башни."""
        if self._mode == 'unified' and self._unified_panel:
            self._unified_panel.set_blueprint(blueprint)
            return
        
        if not blueprint:
            self._reset_parts()
            return
        self.distance_spin.setValue(float(blueprint.instrument_distance))
        self.angle_spin.setValue(float(blueprint.instrument_angle_deg))
        self.instrument_height_spin.setValue(float(blueprint.instrument_height))
        self.rotation_spin.setValue(float(blueprint.base_rotation_deg))
        self.deviation_spin.setValue(float(blueprint.default_deviation_mm))

        self.parts_table.setRowCount(0)
        self._part_sections = []
        self._part_lattice_specs = {}
        
        for part_index, segment in enumerate(blueprint.segments):
            # Save lattice spec
            self._part_lattice_specs[part_index] = {
                "lattice_type": segment.lattice_type,
                "profile_spec": segment.profile_spec
            }
            
            self._add_part_row(
                {
                    "name": segment.name,
                    "shape": segment.shape,
                    "faces": segment.faces,
                    "height": segment.height,
                    "levels": segment.levels,
                    "base_size": segment.base_size,
                    "top_size": segment.top_size if segment.top_size is not None else segment.base_size,
                },
                sections=self._sections_from_spec(segment, part_index),
            )
            
        # Restore equipment
        if "equipment" in blueprint.metadata and hasattr(self, "equipment_editor"):
            self.equipment_editor.set_data(blueprint.metadata["equipment"])
            
        self._update_summary()
        self._refresh_section_tabs()
        
        for part_index in range(len(self._part_sections)):
            if part_index in self._section_tables:
                self._apply_sections_to_table(part_index)

    def _emit_blueprint(self) -> None:
        try:
            blueprint = self.build_blueprint()
        except ValueError as error:
            QMessageBox.warning(self, "Ошибка параметров", str(error))
            return
        
        # Update calculation tab
        if hasattr(self, "calculation_tab"):
            self.calculation_tab.set_blueprint(blueprint)
            
        self.blueprintRequested.emit(blueprint)
        self.statusMessage.emit("Чертёж башни обновлён.")

    # ------------------------------------------------------------------ templates / wizard
    def _get_templates_dir(self) -> Path:
        app_dir = Path(__file__).parent.parent
        templates_dir = app_dir / "templates" / "towers"
        templates_dir.mkdir(parents=True, exist_ok=True)
        return templates_dir
    
    def _build_templates(self) -> Dict[str, Dict[str, object]]:
        templates = {
            "prism_50": {
                "title": "Призма 50 м",
                "segments": [
                    {"name": "Основание", "shape": "prism", "faces": 8, "height": 20.0, "levels": 2, "base_size": 5.0},
                    {"name": "Верхняя часть", "shape": "prism", "faces": 8, "height": 30.0, "levels": 3, "base_size": 4.0},
                ],
                "distance": 75.0,
            },
            "pyramid_80": {
                "title": "Пирамида 80 м",
                "segments": [
                    {
                        "name": "Нижняя часть",
                        "shape": "truncated_pyramid",
                        "faces": 6,
                        "height": 40.0,
                        "levels": 4,
                        "base_size": 9.0,
                        "top_size": 5.0,
                    },
                    {
                        "name": "Верх",
                        "shape": "truncated_pyramid",
                        "faces": 6,
                        "height": 40.0,
                        "levels": 4,
                        "base_size": 5.0,
                        "top_size": 3.0,
                    },
                ],
                "distance": 120.0,
            },
        }
        user_templates = self._load_user_templates()
        templates.update(user_templates)
        return templates
    
    def _load_user_templates(self) -> Dict[str, Dict[str, object]]:
        templates = {}
        templates_dir = self._get_templates_dir()
        if not templates_dir.exists():
            return templates
        
        for template_file in templates_dir.glob("*.json"):
            try:
                with open(template_file, "r", encoding="utf-8") as f:
                    template_data = json.load(f)
                    template_key = f"user_{template_file.stem}"
                    templates[template_key] = template_data
            except Exception as e:
                print(f"Ошибка загрузки шаблона {template_file}: {e}")
        
        return templates
    
    def _save_as_template(self) -> None:
        try:
            blueprint = self.build_blueprint()
        except ValueError as error:
            QMessageBox.warning(self, "Ошибка параметров", f"Нельзя сохранить шаблон: {error}")
            return
        
        name, ok = QInputDialog.getText(
            self,
            "Сохранить шаблон",
            "Введите название шаблона:",
            text="Мой шаблон"
        )
        
        if not ok or not name.strip():
            return
        
        template_data = {
            "title": name.strip(),
            "segments": [],
            "distance": float(self.distance_spin.value()),
            "angle": float(self.angle_spin.value()),
            "instrument_height": float(self.instrument_height_spin.value()),
            "rotation": float(self.rotation_spin.value()),
        }
        
        for row in range(self.parts_table.rowCount()):
            segment_data = self._serialize_row(row)
            sections_data = []
            if row < len(self._part_sections):
                for section_entry in self._part_sections[row]:
                    sections_data.append({
                        "name": section_entry.get("name", "Секция"),
                        "height": float(section_entry.get("height", 0.0)),
                        "deviation_x_mm": float(section_entry.get("deviation_x_mm", 0.0)),
                        "deviation_y_mm": float(section_entry.get("deviation_y_mm", 0.0)),
                    })
            
            template_data["segments"].append({
                "name": segment_data["name"],
                "shape": segment_data["shape"],
                "faces": segment_data["faces"],
                "height": segment_data["height"],
                "levels": segment_data["levels"],
                "base_size": segment_data["base_size"],
                "top_size": segment_data["top_size"],
                "sections": sections_data,
                "lattice_type": segment_data.get("lattice_type", "cross"),
                "profile_spec": segment_data.get("profile_spec", {})
            })
        
        templates_dir = self._get_templates_dir()
        safe_name = "".join(c if c.isalnum() or c in (" ", "-", "_") else "_" for c in name.strip())
        safe_name = safe_name.replace(" ", "_")
        template_file = templates_dir / f"{safe_name}.json"
        
        try:
            with open(template_file, "w", encoding="utf-8") as f:
                json.dump(template_data, f, ensure_ascii=False, indent=2)
            
            self._templates = self._build_templates()
            self._refresh_template_combo()
            
            QMessageBox.information(
                self,
                "Шаблон сохранён",
                f"Шаблон «{name}» успешно сохранён.\n\nФайл: {template_file}"
            )
            self.statusMessage.emit(f"Шаблон «{name}» сохранён.")
        except Exception as e:
            QMessageBox.critical(
                self,
                "Ошибка сохранения",
                f"Не удалось сохранить шаблон:\n{str(e)}"
            )
    
    def _refresh_template_combo(self) -> None:
        if not hasattr(self, "template_combo"):
            return
        self.template_combo.clear()
        self.template_combo.addItem("Пользовательский", "custom")
        for key, template in self._templates.items():
            title = template.get("title", key)
            if key.startswith("user_"):
                title = f"📁 {title}"
            self.template_combo.addItem(title, key)

    def _apply_selected_template(self) -> None:
        key = self.template_combo.currentData()
        if not key or key == "custom":
            return
        template = self._templates.get(key)
        if not template:
            return
        
        self.parts_table.setRowCount(0)
        self._part_sections = []
        self._part_lattice_specs = {}
        
        for part_index, segment in enumerate(template.get("segments", [])):
            sections = None
            if "sections" in segment and segment["sections"]:
                sections = []
                for section in segment["sections"]:
                    sections.append({
                        "name": section.get("name", "Секция"),
                        "height": float(section.get("height", 0.0)),
                        "deviation_x_mm": float(section.get("deviation_x_mm", section.get("offset_x", 0.0) * 1000.0 if section.get("offset_x") else 0.0)),
                        "deviation_y_mm": float(section.get("deviation_y_mm", section.get("offset_y", 0.0) * 1000.0 if section.get("offset_y") else 0.0)),
                    })
            self._add_part_row(segment, sections=sections)
        
        if template.get("distance") is not None:
            self.distance_spin.setValue(float(template["distance"]))
        if template.get("angle") is not None:
            self.angle_spin.setValue(float(template["angle"]))
        if template.get("instrument_height") is not None:
            self.instrument_height_spin.setValue(float(template["instrument_height"]))
        if template.get("rotation") is not None:
            self.rotation_spin.setValue(float(template["rotation"]))
        
        self._refresh_section_tabs()
        self.statusMessage.emit(f"Шаблон «{template.get('title', key)}» применён.")

    def _open_wizard(self) -> None:
        try:
            current = self.build_blueprint()
        except ValueError as error:
            QMessageBox.warning(self, "Ошибка параметров", str(error))
            return
        wizard = TowerBuilderWizard(blueprint=current, parent=self.window())
        if wizard.exec() != wizard.DialogCode.Accepted:
            return
        blueprint = wizard.current_blueprint()
        if blueprint:
            self.set_blueprint(blueprint)
            self.statusMessage.emit("Конфигурация из мастера применена.")

    # ------------------------------------------------------------------ summary
    def _on_mode_changed(self) -> None:
        """Обработка изменения режима конструктора."""
        new_mode = self.mode_combo.currentData()
        if new_mode == self._mode:
            return
        
        # Сохранить текущий чертеж
        current_blueprint = None
        try:
            current_blueprint = self.build_blueprint()
        except:
            pass
        
        # Удалить старую панель
        layout = self.panel_container.layout()
        if self._mode == 'unified' and self._unified_panel:
            layout.removeWidget(self._unified_panel)
            self._unified_panel.setParent(None)
            self._unified_panel = None
        elif self._mode == 'tabs':
            layout.removeWidget(self.tabs)
            self.generate_btn.setVisible(True)
        
        # Добавить новую панель
        self._mode = new_mode
        if new_mode == 'unified':
            self._unified_panel = UnifiedTowerBuilderPanel()
            self._unified_panel.blueprintRequested.connect(self.blueprintRequested.emit)
            self._unified_panel.statusMessage.connect(self.statusMessage.emit)
            # Подключить сигнал визуализации для отображения в основном окне
            self._unified_panel.towerVisualizationRequested.connect(self.towerVisualizationRequested.emit)
            layout.addWidget(self._unified_panel)
            self.generate_btn.setVisible(False)
            
            if current_blueprint:
                self._unified_panel.set_blueprint(current_blueprint)
            
            # Уведомить родительский виджет о переключении режима для обновления layout
            if hasattr(self.parent(), '_update_builder_panel_visibility'):
                self.parent()._update_builder_panel_visibility()
        else:
            layout.addWidget(self.tabs)
            self.generate_btn.setVisible(True)
            
            if current_blueprint:
                self.set_blueprint(current_blueprint)
            
            # Уведомить родительский виджет о переключении режима для обновления layout
            if hasattr(self.parent(), '_update_builder_panel_visibility'):
                self.parent()._update_builder_panel_visibility()
    
    def _update_summary(self) -> None:
        segments = self._collect_segments()
        total_height = sum(data["height"] for data in segments)
        mismatches = []
        for idx, data in enumerate(segments, start=1):
            sections = data.get("sections") or []
            if sections:
                diff = abs(sum(section["height"] for section in sections) - data["height"])
                if diff > 1e-3:
                    mismatches.append(str(idx))
        text = f"Суммарная высота: {total_height:.2f} м"
        if mismatches:
            text += f" | ⚠ несоответствие высот в частях: {', '.join(mismatches)}"
        self.summary_label.setText(text)
