"""
Мастер групповых операций для конструктора башни.
Позволяет выбирать элементы по критериям и выполнять групповые операции.
"""

from __future__ import annotations

from typing import Optional, Dict, List, Any, Set
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QGroupBox,
    QLabel,
    QComboBox,
    QCheckBox,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QDialog,
    QDialogButtonBox,
    QMessageBox,
    QSpinBox,
    QDoubleSpinBox,
)

from core.tower_generator import TowerBlueprintV2, TowerSegmentSpec, TowerSectionSpec
from core.structure.model import MemberType
from core.db.profile_manager import ProfileManager

# Словарь русских названий типов профилей
PROFILE_TYPE_NAMES = {
    "pipe": "Труба",
    "angle": "Уголок",
    "channel": "Швеллер",
    "i_beam": "Двутавр",
}


class TowerBuilderMaster(QDialog):
    """
    Мастер для групповых операций над элементами башни.
    """
    
    # Сигнал с результатом операции
    operationCompleted = pyqtSignal(dict)  # operation_data
    
    def __init__(self, blueprint: TowerBlueprintV2, profile_manager: ProfileManager, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.blueprint = blueprint
        self.profile_manager = profile_manager
        self._selected_elements: Set[tuple] = set()  # (segment_idx, section_idx, element_type)
        
        self.setWindowTitle("Мастер групповых операций")
        self.setMinimumSize(700, 600)
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """Настройка интерфейса мастера."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        
        # Шаг 1: Выбор элементов
        selection_group = QGroupBox("Шаг 1: Выбор элементов")
        selection_layout = QVBoxLayout()
        
        # Критерии выбора
        criteria_group = QGroupBox("Критерии выбора")
        criteria_form = QFormLayout()
        
        # Выбор по частям
        self.select_by_segments_check = QCheckBox("Выбрать по частям")
        self.select_by_segments_check.setChecked(True)
        self.segments_list = QListWidget()
        self.segments_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        self.segments_list.setMaximumHeight(100)
        criteria_form.addRow(self.select_by_segments_check, self.segments_list)
        
        # Выбор по типам элементов
        self.select_by_type_check = QCheckBox("Выбрать по типам элементов")
        self.select_by_type_check.setChecked(True)
        types_layout = QHBoxLayout()
        self.leg_check = QCheckBox("Пояса")
        self.leg_check.setChecked(True)
        self.brace_check = QCheckBox("Раскосы")
        self.brace_check.setChecked(True)
        self.strut_check = QCheckBox("Распорки")
        self.strut_check.setChecked(True)
        types_layout.addWidget(self.leg_check)
        types_layout.addWidget(self.brace_check)
        types_layout.addWidget(self.strut_check)
        types_layout.addStretch()
        criteria_form.addRow(self.select_by_type_check, types_layout)
        
        # Выбор по высоте
        self.select_by_height_check = QCheckBox("Выбрать по высоте")
        height_layout = QHBoxLayout()
        self.height_from_spin = QDoubleSpinBox()
        self.height_from_spin.setRange(0, 1000)
        self.height_from_spin.setDecimals(2)
        self.height_from_spin.setSuffix(" м")
        self.height_to_spin = QDoubleSpinBox()
        self.height_to_spin.setRange(0, 1000)
        self.height_to_spin.setDecimals(2)
        self.height_to_spin.setValue(1000)
        self.height_to_spin.setSuffix(" м")
        height_layout.addWidget(QLabel("От:"))
        height_layout.addWidget(self.height_from_spin)
        height_layout.addWidget(QLabel("До:"))
        height_layout.addWidget(self.height_to_spin)
        height_layout.addStretch()
        criteria_form.addRow(self.select_by_height_check, height_layout)
        
        criteria_group.setLayout(criteria_form)
        selection_layout.addWidget(criteria_group)
        
        # Кнопка применения критериев
        apply_criteria_btn = QPushButton("Применить критерии")
        apply_criteria_btn.clicked.connect(self._apply_selection_criteria)
        selection_layout.addWidget(apply_criteria_btn)
        
        # Список выбранных элементов
        selected_label = QLabel("Выбранные элементы:")
        selected_label.setStyleSheet("font-weight: 600;")
        selection_layout.addWidget(selected_label)
        
        self.selected_list = QListWidget()
        self.selected_list.setMaximumHeight(150)
        selection_layout.addWidget(self.selected_list)
        
        selection_group.setLayout(selection_layout)
        layout.addWidget(selection_group)
        
        # Шаг 2: Операция
        operation_group = QGroupBox("Шаг 2: Операция")
        operation_layout = QVBoxLayout()
        
        self.operation_combo = QComboBox()
        self.operation_combo.addItems([
            "Назначить профиль",
            "Изменить тип решетки",
            "Копировать настройки",
            "Применить шаблон профилей"
        ])
        self.operation_combo.currentIndexChanged.connect(self._on_operation_changed)
        operation_layout.addWidget(QLabel("Тип операции:"))
        operation_layout.addWidget(self.operation_combo)
        
        # Панель параметров операции
        self.operation_params_widget = QWidget()
        self.operation_params_layout = QVBoxLayout(self.operation_params_widget)
        operation_layout.addWidget(self.operation_params_widget)
        
        operation_group.setLayout(operation_layout)
        layout.addWidget(operation_group)
        
        # Кнопки
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_apply)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
        # Инициализация
        self._populate_segments()
        self._on_operation_changed()
        # Не применять критерии автоматически - пользователь сам выберет
    
    def _populate_segments(self) -> None:
        """Заполнить список частей башни."""
        self.segments_list.clear()
        for idx, segment in enumerate(self.blueprint.segments):
            item = QListWidgetItem(segment.name)
            item.setData(Qt.ItemDataRole.UserRole, idx)
            item.setSelected(True)
            self.segments_list.addItem(item)
    
    def _apply_selection_criteria(self) -> None:
        """Применить критерии выбора элементов."""
        self._selected_elements.clear()
        self.selected_list.clear()
        
        # Получить выбранные части
        selected_segment_indices = set()
        if self.select_by_segments_check.isChecked():
            for item in self.segments_list.selectedItems():
                segment_idx = item.data(Qt.ItemDataRole.UserRole)
                selected_segment_indices.add(segment_idx)
        else:
            selected_segment_indices = set(range(len(self.blueprint.segments)))
        
        # Получить выбранные типы элементов
        selected_types = set()
        if self.select_by_type_check.isChecked():
            if self.leg_check.isChecked():
                selected_types.add(MemberType.LEG)
            if self.brace_check.isChecked():
                selected_types.add(MemberType.BRACE)
            if self.strut_check.isChecked():
                selected_types.add(MemberType.STRUT)
        else:
            selected_types = {MemberType.LEG, MemberType.BRACE, MemberType.STRUT}
        
        # Получить диапазон высот
        height_from = self.height_from_spin.value() if self.select_by_height_check.isChecked() else 0
        height_to = self.height_to_spin.value() if self.select_by_height_check.isChecked() else 10000
        
        # Вычислить накопленные высоты для каждой части
        accumulated_heights = []
        current_height = 0.0
        for segment in self.blueprint.segments:
            accumulated_heights.append(current_height)
            current_height += segment.height
        
        # Выбрать элементы по критериям
        for seg_idx in selected_segment_indices:
            if seg_idx >= len(self.blueprint.segments):
                continue
            
            segment = self.blueprint.segments[seg_idx]
            seg_base_height = accumulated_heights[seg_idx]
            seg_top_height = seg_base_height + segment.height
            
            # Проверить высоту
            if self.select_by_height_check.isChecked():
                if seg_top_height < height_from or seg_base_height > height_to:
                    continue
            
            # Обработать секции или всю часть
            if segment.sections:
                current_section_height = seg_base_height
                for sec_idx, section in enumerate(segment.sections):
                    sec_base_height = current_section_height
                    sec_top_height = sec_base_height + section.height
                    current_section_height = sec_top_height
                    
                    if self.select_by_height_check.isChecked():
                        if sec_top_height < height_from or sec_base_height > height_to:
                            continue
                    
                    for elem_type in selected_types:
                        key = (seg_idx, sec_idx, elem_type)
                        self._selected_elements.add(key)
            else:
                # Вся часть
                for elem_type in selected_types:
                    key = (seg_idx, -1, elem_type)  # -1 означает всю часть
                    self._selected_elements.add(key)
        
        # Обновить список
        self._update_selected_list()
    
    def _update_selected_list(self) -> None:
        """Обновить список выбранных элементов."""
        self.selected_list.clear()
        
        type_names = {
            MemberType.LEG: "Пояса",
            MemberType.BRACE: "Раскосы",
            MemberType.STRUT: "Распорки",
        }
        
        # Группировать по частям
        by_segment: Dict[int, List[tuple]] = {}
        for key in sorted(self._selected_elements):
            seg_idx, sec_idx, elem_type = key
            if seg_idx not in by_segment:
                by_segment[seg_idx] = []
            by_segment[seg_idx].append(key)
        
        for seg_idx in sorted(by_segment.keys()):
            segment = self.blueprint.segments[seg_idx]
            for key in by_segment[seg_idx]:
                sec_idx, elem_type = key[1], key[2]
                type_name = type_names.get(elem_type, "Неизвестно")
                
                if sec_idx >= 0 and segment.sections and sec_idx < len(segment.sections):
                    section = segment.sections[sec_idx]
                    text = f"{segment.name} → {section.name} → {type_name}"
                else:
                    text = f"{segment.name} → {type_name}"
                
                item = QListWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, key)
                self.selected_list.addItem(item)
        
        # Обновить счетчик
        count = len(self._selected_elements)
        self.selected_list.setToolTip(f"Выбрано элементов: {count}")
    
    def _on_operation_changed(self) -> None:
        """Обработка изменения типа операции."""
        # Очистить панель параметров
        while self.operation_params_layout.count():
            child = self.operation_params_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        
        operation = self.operation_combo.currentText()
        
        if operation == "Назначить профиль":
            self._setup_assign_profile_params()
        elif operation == "Изменить тип решетки":
            self._setup_change_lattice_params()
        elif operation == "Копировать настройки":
            self._setup_copy_settings_params()
        elif operation == "Применить шаблон профилей":
            self._setup_apply_template_params()
    
    def _setup_assign_profile_params(self) -> None:
        """Настройка параметров назначения профиля."""
        form = QFormLayout()
        
        # Тип элемента
        self.profile_element_type_combo = QComboBox()
        self.profile_element_type_combo.addItems(["Пояса", "Раскосы", "Раскосы и распорки"])
        form.addRow("Для элементов:", self.profile_element_type_combo)
        
        # Профиль
        self.profile_combo = QComboBox()
        self._populate_profiles_combo(self.profile_combo)
        form.addRow("Профиль:", self.profile_combo)
        
        self.operation_params_layout.addLayout(form)
    
    def _setup_change_lattice_params(self) -> None:
        """Настройка параметров изменения типа решетки."""
        form = QFormLayout()
        
        self.lattice_type_combo = QComboBox()
        self.lattice_type_combo.addItems([
            "cross", "z_brace", "k_brace", "portal", "none"
        ])
        form.addRow("Тип решетки:", self.lattice_type_combo)
        
        self.operation_params_layout.addLayout(form)
    
    def _setup_copy_settings_params(self) -> None:
        """Настройка параметров копирования настроек."""
        form = QFormLayout()
        
        # Источник
        self.source_segment_combo = QComboBox()
        for idx, segment in enumerate(self.blueprint.segments):
            self.source_segment_combo.addItem(segment.name, idx)
        form.addRow("Копировать из части:", self.source_segment_combo)
        
        self.operation_params_layout.addLayout(form)
    
    def _setup_apply_template_params(self) -> None:
        """Настройка параметров применения шаблона."""
        form = QFormLayout()
        
        info_label = QLabel("Шаблоны профилей будут загружены из сохраненных конфигураций")
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #666; padding: 4px;")
        form.addRow(info_label)
        
        self.operation_params_layout.addLayout(form)
    
    def _populate_profiles_combo(self, combo: QComboBox) -> None:
        """Заполнить комбобокс профилями."""
        combo.clear()
        combo.addItem("Не задано", None)
        
        type_names = {
            "pipe": "Труба",
            "angle": "Уголок",
            "channel": "Швеллер",
        }
        
        pipes = self.profile_manager.get_profiles_by_type("pipe")
        angles = self.profile_manager.get_profiles_by_type("angle")
        channels = self.profile_manager.get_profiles_by_type("channel")
        
        for p in pipes:
            type_name = type_names.get(p['type'], p['type'])
            display_name = f"{type_name} {p['designation']} ({p['standard']})"
            combo.addItem(display_name, p)
        
        for a in angles:
            type_name = type_names.get(a['type'], a['type'])
            display_name = f"{type_name} {a['designation']} ({a['standard']})"
            combo.addItem(display_name, a)
        
        for c in channels:
            type_name = type_names.get(c['type'], c['type'])
            display_name = f"{type_name} {c['designation']} ({c['standard']})"
            combo.addItem(display_name, c)
    
    def _on_apply(self) -> None:
        """Применить операцию."""
        if not self._selected_elements:
            QMessageBox.warning(self, "Ошибка", "Не выбраны элементы для операции.")
            return
        
        operation = self.operation_combo.currentText()
        result = {
            "operation": operation,
            "selected_elements": list(self._selected_elements),
            "params": {}
        }
        
        if operation == "Назначить профиль":
            profile_data = self.profile_combo.currentData()
            if not profile_data:
                QMessageBox.warning(self, "Ошибка", "Выберите профиль.")
                return
            
            element_type_text = self.profile_element_type_combo.currentText()
            result["params"] = {
                "profile": profile_data,
                "element_type": element_type_text
            }
        
        elif operation == "Изменить тип решетки":
            lattice_type = self.lattice_type_combo.currentText()
            result["params"] = {
                "lattice_type": lattice_type
            }
        
        elif operation == "Копировать настройки":
            source_idx = self.source_segment_combo.currentData()
            result["params"] = {
                "source_segment": source_idx
            }
        
        elif operation == "Применить шаблон профилей":
            # TODO: Реализовать загрузку шаблонов
            QMessageBox.information(self, "Информация", "Применение шаблонов будет реализовано позже.")
            return
        
        self.operationCompleted.emit(result)
        self.accept()
    
    @staticmethod
    def apply_operation(blueprint: TowerBlueprintV2, operation_data: Dict[str, Any]) -> TowerBlueprintV2:
        """
        Применить операцию к чертежу башни.
        Возвращает новый чертеж с примененными изменениями.
        """
        from copy import deepcopy
        new_blueprint = deepcopy(blueprint)
        
        operation = operation_data["operation"]
        selected_elements = operation_data["selected_elements"]
        params = operation_data["params"]
        
        if operation == "Назначить профиль":
            profile_data = params["profile"]
            element_type_text = params["element_type"]
            
            # Формировать строку профиля
            type_name = PROFILE_TYPE_NAMES.get(profile_data.get("type", ""), profile_data.get("type", ""))
            designation = profile_data.get("designation", "")
            standard = profile_data.get("standard", "")
            profile_string = f"{type_name} {designation} ({standard})"
            
            # Определить, какие типы элементов обновлять
            target_types = []
            if "Пояса" in element_type_text:
                target_types.append("leg_profile")
            if "Раскосы" in element_type_text:
                target_types.append("brace_profile")
            if "распорки" in element_type_text.lower():
                target_types.append("strut_profile")
            
            # Применить к выбранным элементам
            for seg_idx, sec_idx, elem_type in selected_elements:
                if seg_idx >= len(new_blueprint.segments):
                    continue
                
                segment = new_blueprint.segments[seg_idx]
                
                if sec_idx >= 0 and segment.sections:
                    # Применить к секции
                    section = segment.sections[sec_idx]
                    if not section.profile_spec:
                        section.profile_spec = {}
                    
                    for target_type in target_types:
                        section.profile_spec[target_type] = profile_string
                else:
                    # Применить к части
                    if not segment.profile_spec:
                        segment.profile_spec = {}
                    
                    for target_type in target_types:
                        segment.profile_spec[target_type] = profile_string
        
        elif operation == "Изменить тип решетки":
            lattice_type = params["lattice_type"]
            
            for seg_idx, sec_idx, elem_type in selected_elements:
                if seg_idx >= len(new_blueprint.segments):
                    continue
                
                segment = new_blueprint.segments[seg_idx]
                
                if sec_idx >= 0 and segment.sections and sec_idx < len(segment.sections):
                    section = segment.sections[sec_idx]
                    section.lattice_type = lattice_type
                else:
                    segment.lattice_type = lattice_type
        
        elif operation == "Копировать настройки":
            source_idx = params["source_segment"]
            if source_idx is None or source_idx >= len(new_blueprint.segments):
                return new_blueprint
            
            source_segment = new_blueprint.segments[source_idx]
            
            for seg_idx, sec_idx, elem_type in selected_elements:
                if seg_idx == source_idx:
                    continue
                if seg_idx >= len(new_blueprint.segments):
                    continue
                
                target_segment = new_blueprint.segments[seg_idx]
                
                # Копировать профили и тип решетки
                if source_segment.profile_spec:
                    target_segment.profile_spec = source_segment.profile_spec.copy()
                else:
                    target_segment.profile_spec = {}
                target_segment.lattice_type = source_segment.lattice_type
        
        return new_blueprint
