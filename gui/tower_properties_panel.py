"""
Панель свойств выбранного элемента башни.
Адаптивно отображает свойства в зависимости от типа выбранного элемента.
"""

from __future__ import annotations

from typing import Optional, Dict, Any
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QComboBox,
    QDoubleSpinBox,
    QSpinBox,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QMessageBox,
    QFileDialog,
)

from core.tower_generator import TowerSegmentSpec, TowerSectionSpec, TowerBlueprintV2
from core.structure.model import MemberType
from core.db.profile_manager import ProfileManager
from core.structure.builder import TowerModelBuilder
from core.physics.wind_load import WindLoadCalculator, WIND_ZONES, TERRAIN_COEFFS
import numpy as np

# Импорт для таблицы МКЭ (ленивый импорт в методе для избежания циклических зависимостей)


class TowerPropertiesPanel(QWidget):
    """
    Панель свойств для редактирования параметров выбранного элемента.
    Адаптивно меняет содержимое в зависимости от типа элемента.
    """
    
    # Сигналы
    propertyChanged = pyqtSignal(str, object)  # property_name, value
    profileAssigned = pyqtSignal(str, str)  # element_type, profile_name
    
    def __init__(self, profile_manager: ProfileManager, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.profile_manager = profile_manager
        self._current_element_type: Optional[str] = None
        self._current_element_data: Optional[Dict[str, Any]] = None
        self._current_blueprint: Optional[TowerBlueprintV2] = None
        self._last_calculation_result = None
        self._updating = False
        
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """Настройка интерфейса панели свойств."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        
        # Заголовок
        self.title_label = QLabel("Выберите элемент")
        self.title_label.setStyleSheet("font-weight: 600; font-size: 11pt; padding: 4px;")
        layout.addWidget(self.title_label)
        
        # Вкладки для разных типов свойств
        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.TabPosition.North)
        
        # Вкладка: Основные свойства
        self.general_tab = QWidget()
        self._setup_general_tab()
        self.tabs.addTab(self.general_tab, "Основные")
        
        # Вкладка: Профили
        self.profiles_tab = QWidget()
        self._setup_profiles_tab()
        self.tabs.addTab(self.profiles_tab, "Профили")
        
        # Вкладка: Решетка
        self.lattice_tab = QWidget()
        self._setup_lattice_tab()
        self.tabs.addTab(self.lattice_tab, "Решетка")
        
        # Вкладка: Расчет
        self.calculation_tab = QWidget()
        self._setup_calculation_tab()
        self.tabs.addTab(self.calculation_tab, "Расчет")
        
        # Вкладка: Таблица расчета МКЭ
        from gui.calculation_table_widget import CalculationTableWidget
        self.mke_table = CalculationTableWidget(self.profile_manager)
        self.tabs.addTab(self.mke_table, "Таблица МКЭ")
        
        layout.addWidget(self.tabs)
        
        # Кнопки действий
        buttons_layout = QHBoxLayout()
        self.apply_btn = QPushButton("Применить")
        self.apply_btn.clicked.connect(self._on_apply)
        self.apply_btn.setEnabled(False)
        buttons_layout.addWidget(self.apply_btn)
        
        buttons_layout.addStretch()
        
        layout.addLayout(buttons_layout)
    
    def _setup_general_tab(self) -> None:
        """Настройка вкладки основных свойств."""
        layout = QVBoxLayout(self.general_tab)
        layout.setContentsMargins(8, 8, 8, 8)
        
        self.general_form = QFormLayout()
        layout.addLayout(self.general_form)
        layout.addStretch()
    
    def _setup_profiles_tab(self) -> None:
        """Настройка вкладки профилей."""
        layout = QVBoxLayout(self.profiles_tab)
        layout.setContentsMargins(8, 8, 8, 8)
        
        profiles_group = QGroupBox("Назначение профилей")
        profiles_form = QFormLayout()
        
        # Профиль поясов
        self.leg_profile_combo = QComboBox()
        self._populate_profiles_combo(self.leg_profile_combo)
        profiles_form.addRow("Пояса:", self.leg_profile_combo)
        
        # Профиль раскосов
        self.brace_profile_combo = QComboBox()
        self._populate_profiles_combo(self.brace_profile_combo)
        profiles_form.addRow("Раскосы:", self.brace_profile_combo)
        
        # Профиль распорок
        self.strut_profile_combo = QComboBox()
        self._populate_profiles_combo(self.strut_profile_combo)
        profiles_form.addRow("Распорки:", self.strut_profile_combo)
        
        profiles_group.setLayout(profiles_form)
        layout.addWidget(profiles_group)
        
        # Кнопка группового назначения
        group_btn = QPushButton("Назначить на все элементы")
        group_btn.clicked.connect(self._on_group_assign)
        layout.addWidget(group_btn)
        
        layout.addStretch()
    
    def _setup_lattice_tab(self) -> None:
        """Настройка вкладки решетки."""
        layout = QVBoxLayout(self.lattice_tab)
        layout.setContentsMargins(8, 8, 8, 8)
        
        lattice_group = QGroupBox("Тип решетки")
        lattice_form = QFormLayout()
        
        self.lattice_type_combo = QComboBox()
        self.lattice_type_combo.addItems([
            "cross", "z_brace", "k_brace", "portal", "none"
        ])
        lattice_form.addRow("Схема:", self.lattice_type_combo)
        
        lattice_group.setLayout(lattice_form)
        layout.addWidget(lattice_group)
        
        layout.addStretch()
    
    def _setup_calculation_tab(self) -> None:
        """Настройка вкладки расчета."""
        layout = QVBoxLayout(self.calculation_tab)
        layout.setContentsMargins(8, 8, 8, 8)
        
        # Параметры расчета
        params_group = QGroupBox("Параметры расчета ветровой нагрузки")
        params_form = QFormLayout()
        
        self.wind_zone_combo = QComboBox()
        for zone_num, pressure in WIND_ZONES.items():
            self.wind_zone_combo.addItem(f"Ветровой район {zone_num} ({pressure} кПа)", zone_num)
        self.wind_zone_combo.setCurrentIndex(1)  # Район 2 по умолчанию
        params_form.addRow("Ветровой район:", self.wind_zone_combo)
        
        self.terrain_combo = QComboBox()
        terrain_descriptions = {
            'A': 'Открытое побережье',
            'B': 'Город/Лес',
            'C': 'Плотная застройка'
        }
        for terrain_type, desc in terrain_descriptions.items():
            self.terrain_combo.addItem(f"Тип местности {terrain_type} ({desc})", terrain_type)
        self.terrain_combo.setCurrentIndex(0)  # Тип A по умолчанию
        params_form.addRow("Тип местности:", self.terrain_combo)
        
        params_group.setLayout(params_form)
        layout.addWidget(params_group)
        
        # Кнопка расчета
        calc_btn = QPushButton("Выполнить расчет")
        calc_btn.clicked.connect(self._on_calculate)
        layout.addWidget(calc_btn)
        
        # Результаты
        results_group = QGroupBox("Результаты")
        results_layout = QVBoxLayout()
        
        self.results_text = QTextEdit()
        self.results_text.setReadOnly(True)
        self.results_text.setMaximumHeight(200)
        self.results_text.setPlaceholderText("Результаты расчета будут отображены здесь...")
        results_layout.addWidget(self.results_text)
        
        # Кнопка экспорта
        export_btn = QPushButton("Экспорт отчета (PDF)")
        export_btn.clicked.connect(self._on_export_report)
        results_layout.addWidget(export_btn)
        
        results_group.setLayout(results_layout)
        layout.addWidget(results_group)
        
        layout.addStretch()
    
    def _populate_profiles_combo(self, combo: QComboBox) -> None:
        """Заполнить комбобокс профилями."""
        combo.clear()
        combo.addItem("Не задано", None)
        
        # Получить все профили
        pipes = self.profile_manager.get_profiles_by_type("pipe")
        angles = self.profile_manager.get_profiles_by_type("angle")
        
        for p in pipes:
            display_name = f"{p['type']} {p['designation']} ({p['standard']})"
            combo.addItem(display_name, p)
        
        for a in angles:
            display_name = f"{a['type']} {a['designation']} ({a['standard']})"
            combo.addItem(display_name, a)
    
    def set_element(self, element_type: str, element_data: Dict[str, Any]) -> None:
        """Установить выбранный элемент для редактирования."""
        self._current_element_type = element_type
        self._current_element_data = element_data
        self._updating = True
        
        try:
            self._update_ui()
        finally:
            self._updating = False
        
        self.apply_btn.setEnabled(True)
    
    def _update_ui(self) -> None:
        """Обновить интерфейс в соответствии с выбранным элементом."""
        if not self._current_element_data:
            self.title_label.setText("Выберите элемент")
            return
        
        data = self._current_element_data
        
        # Обновить заголовок
        if self._current_element_type == "tower":
            self.title_label.setText("Башня")
        elif self._current_element_type == "segment":
            self.title_label.setText(f"Часть: {data.get('data', {}).name if hasattr(data.get('data'), 'name') else 'Неизвестно'}")
        elif self._current_element_type == "section":
            self.title_label.setText(f"Секция: {data.get('data', {}).name if hasattr(data.get('data'), 'name') else 'Неизвестно'}")
        elif self._current_element_type == "element":
            element_type = data.get("element_type")
            type_names = {
                MemberType.LEG: "Пояса",
                MemberType.BRACE: "Раскосы",
                MemberType.STRUT: "Распорки"
            }
            self.title_label.setText(type_names.get(element_type, "Элемент"))
        
        # Очистить форму основных свойств
        while self.general_form.rowCount() > 0:
            self.general_form.removeRow(0)
        
        # Заполнить форму в зависимости от типа
        if self._current_element_type == "segment":
            self._fill_segment_properties(data.get("data"))
        elif self._current_element_type == "section":
            self._fill_section_properties(data.get("data"))
        elif self._current_element_type == "element":
            self._fill_element_properties(data)
        
        # Обновить профили
        self._update_profiles()
        
        # Обновить решетку
        self._update_lattice()
    
    def _fill_segment_properties(self, segment: Optional[TowerSegmentSpec]) -> None:
        """Заполнить свойства части башни."""
        if not segment:
            return
        
        name_edit = QLineEdit(segment.name)
        name_edit.textChanged.connect(lambda v: self._on_property_changed("name", v))
        self.general_form.addRow("Название:", name_edit)
        
        shape_combo = QComboBox()
        shape_combo.addItems(["Призма", "Усечённая пирамида"])
        shape_combo.setCurrentText("Призма" if segment.shape == "prism" else "Усечённая пирамида")
        shape_combo.currentTextChanged.connect(lambda v: self._on_property_changed("shape", "prism" if v == "Призма" else "truncated_pyramid"))
        self.general_form.addRow("Форма:", shape_combo)
        
        height_spin = QDoubleSpinBox()
        height_spin.setRange(0.5, 500.0)
        height_spin.setDecimals(2)
        height_spin.setValue(segment.height)
        height_spin.setSuffix(" м")
        height_spin.valueChanged.connect(lambda v: self._on_property_changed("height", v))
        self.general_form.addRow("Высота:", height_spin)
        
        faces_spin = QSpinBox()
        faces_spin.setRange(3, 64)
        faces_spin.setValue(segment.faces)
        faces_spin.valueChanged.connect(lambda v: self._on_property_changed("faces", v))
        self.general_form.addRow("Граней:", faces_spin)
        
        base_spin = QDoubleSpinBox()
        base_spin.setRange(0.5, 200.0)
        base_spin.setDecimals(3)
        base_spin.setValue(segment.base_size)
        base_spin.setSuffix(" м")
        base_spin.valueChanged.connect(lambda v: self._on_property_changed("base_size", v))
        self.general_form.addRow("Нижний размер:", base_spin)
        
        if segment.shape == "truncated_pyramid":
            top_spin = QDoubleSpinBox()
            top_spin.setRange(0.1, 200.0)
            top_spin.setDecimals(3)
            top_spin.setValue(segment.top_size or segment.base_size)
            top_spin.setSuffix(" м")
            top_spin.valueChanged.connect(lambda v: self._on_property_changed("top_size", v))
            self.general_form.addRow("Верхний размер:", top_spin)
    
    def _fill_section_properties(self, section: Optional[TowerSectionSpec]) -> None:
        """Заполнить свойства секции."""
        if not section:
            return
        
        name_edit = QLineEdit(section.name)
        name_edit.textChanged.connect(lambda v: self._on_property_changed("name", v))
        self.general_form.addRow("Название:", name_edit)
        
        height_spin = QDoubleSpinBox()
        height_spin.setRange(0.01, 500.0)
        height_spin.setDecimals(3)
        height_spin.setValue(section.height)
        height_spin.setSuffix(" м")
        height_spin.valueChanged.connect(lambda v: self._on_property_changed("height", v))
        self.general_form.addRow("Высота:", height_spin)
        
        offset_x_spin = QDoubleSpinBox()
        offset_x_spin.setRange(-10.0, 10.0)
        offset_x_spin.setDecimals(3)
        offset_x_spin.setValue(section.offset_x)
        offset_x_spin.setSuffix(" м")
        offset_x_spin.valueChanged.connect(lambda v: self._on_property_changed("offset_x", v))
        self.general_form.addRow("Смещение X:", offset_x_spin)
        
        offset_y_spin = QDoubleSpinBox()
        offset_y_spin.setRange(-10.0, 10.0)
        offset_y_spin.setDecimals(3)
        offset_y_spin.setValue(section.offset_y)
        offset_y_spin.setSuffix(" м")
        offset_y_spin.valueChanged.connect(lambda v: self._on_property_changed("offset_y", v))
        self.general_form.addRow("Смещение Y:", offset_y_spin)
    
    def _fill_element_properties(self, data: Dict[str, Any]) -> None:
        """Заполнить свойства элемента."""
        element_type = data.get("element_type")
        type_label = QLabel({
            MemberType.LEG: "Пояса",
            MemberType.BRACE: "Раскосы",
            MemberType.STRUT: "Распорки"
        }.get(element_type, "Элемент"))
        self.general_form.addRow("Тип элемента:", type_label)
        
        profile_name = data.get("profile", "Не задано")
        profile_label = QLabel(profile_name)
        self.general_form.addRow("Текущий профиль:", profile_label)
    
    def _update_profiles(self) -> None:
        """Обновить комбобоксы профилей."""
        if not self._current_element_data:
            return
        
        data = self._current_element_data
        profile_spec = {}
        
        if self._current_element_type == "segment":
            segment = data.get("data")
            if segment:
                profile_spec = segment.profile_spec
        elif self._current_element_type == "section":
            section = data.get("data")
            segment = data.get("segment")
            if section and section.profile_spec:
                profile_spec = section.profile_spec
            elif segment:
                profile_spec = segment.profile_spec
        elif self._current_element_type == "element":
            profile_spec = {"leg_profile": data.get("profile"), "brace_profile": data.get("profile")}
        
        # Установить значения
        leg_profile = profile_spec.get("leg_profile", "Не задано")
        brace_profile = profile_spec.get("brace_profile", "Не задано")
        strut_profile = profile_spec.get("strut_profile", brace_profile)
        
        self._set_combo_value(self.leg_profile_combo, leg_profile)
        self._set_combo_value(self.brace_profile_combo, brace_profile)
        self._set_combo_value(self.strut_profile_combo, strut_profile)
    
    def _set_combo_value(self, combo: QComboBox, value: str) -> None:
        """Установить значение в комбобоксе."""
        if not value or value == "Не задано":
            combo.setCurrentIndex(0)
            return
        
        index = combo.findText(value, Qt.MatchFlag.MatchContains)
        if index >= 0:
            combo.setCurrentIndex(index)
        else:
            combo.setCurrentIndex(0)
    
    def _update_lattice(self) -> None:
        """Обновить тип решетки."""
        if not self._current_element_data:
            return
        
        data = self._current_element_data
        lattice_type = "cross"
        
        if self._current_element_type == "segment":
            segment = data.get("data")
            if segment:
                lattice_type = segment.lattice_type
        elif self._current_element_type == "section":
            section = data.get("data")
            if section:
                lattice_type = section.lattice_type
        
        index = self.lattice_type_combo.findText(lattice_type)
        if index >= 0:
            self.lattice_type_combo.setCurrentIndex(index)
    
    def _on_property_changed(self, property_name: str, value: Any) -> None:
        """Обработка изменения свойства."""
        if self._updating:
            return
        self.propertyChanged.emit(property_name, value)
    
    def _on_group_assign(self) -> None:
        """Групповое назначение профилей."""
        # Будет реализовано позже
        QMessageBox.information(self, "Информация", "Групповое назначение будет реализовано в мастере операций")
    
    def _on_apply(self) -> None:
        """Применить изменения."""
        # Будет реализовано позже
        self.apply_btn.setEnabled(False)
        QMessageBox.information(self, "Информация", "Изменения применены")
    
    def set_blueprint(self, blueprint: Optional[TowerBlueprintV2]) -> None:
        """Установить чертеж башни для расчета."""
        self._current_blueprint = blueprint
        if hasattr(self, 'mke_table'):
            self.mke_table.set_blueprint(blueprint)
    
    def _on_calculate(self) -> None:
        """Выполнить расчет ветровой нагрузки."""
        if not self._current_blueprint:
            QMessageBox.warning(self, "Ошибка", "Нет чертежа башни для расчета.")
            return
        
        try:
            self.results_text.append("Построение модели...")
            
            # Построить модель
            builder = TowerModelBuilder(self._current_blueprint, self.profile_manager)
            model = builder.build()
            
            self.results_text.append(f"Модель построена: {len(model.nodes)} узлов, {len(model.members)} элементов.")
            
            # Получить параметры расчета
            wind_zone = self.wind_zone_combo.currentData()
            terrain_type = self.terrain_combo.currentData()
            
            if not wind_zone or not terrain_type:
                QMessageBox.warning(self, "Ошибка", "Выберите параметры расчета.")
                return
            
            self.results_text.append("Выполнение расчета ветровой нагрузки...")
            
            # Выполнить расчет
            calculator = WindLoadCalculator(model)
            result = calculator.calculate(wind_zone, terrain_type)
            
            self._last_calculation_result = result
            
            # Отобразить результаты
            f1 = result.natural_frequencies[0] if result.natural_frequencies else 0.0
            f2 = result.natural_frequencies[1] if len(result.natural_frequencies) > 1 else 0.0
            max_load = np.max(np.abs(result.total_load)) if result.total_load is not None else 0.0
            total_force = np.sum(result.total_load) if result.total_load is not None else 0.0
            
            results_html = f"""
            <b>Результаты расчета ветровой нагрузки:</b><br>
            <br>
            <b>Параметры:</b><br>
            Ветровой район: {wind_zone} ({WIND_ZONES[wind_zone]} кПа)<br>
            Тип местности: {terrain_type}<br>
            <br>
            <b>Собственные частоты:</b><br>
            1-я частота: {f1:.3f} Гц<br>
            2-я частота: {f2:.3f} Гц<br>
            <br>
            <b>Нагрузки:</b><br>
            Максимальная узловая нагрузка: {max_load:.1f} Н<br>
            Суммарная ветровая нагрузка: {total_force/1000:.2f} кН<br>
            """
            
            self.results_text.setHtml(results_html)
            
            # Эмитировать сигнал для визуализации в 3D
            self._visualize_wind_loads(model, result)
            
            QMessageBox.information(self, "Расчет выполнен", "Расчет ветровой нагрузки успешно завершен.")
            
        except Exception as e:
            error_msg = f"Ошибка при расчете: {str(e)}"
            self.results_text.append(error_msg)
            QMessageBox.critical(self, "Ошибка расчета", error_msg)
    
    def _visualize_wind_loads(self, model, result) -> None:
        """Визуализировать ветровые нагрузки (будет подключено к 3D виджету)."""
        # TODO: Эмитировать сигнал для визуализации в EnhancedTowerPreview3D
        # Пока просто сохраняем результат
        pass
    
    def get_calculation_result(self):
        """Получить результат последнего расчета."""
        return self._last_calculation_result
    
    def _on_export_report(self) -> None:
        """Экспортировать отчет расчета."""
        if not self._last_calculation_result:
            QMessageBox.warning(self, "Ошибка", "Сначала выполните расчет.")
            return
        
        try:
            from core.exporters.calculation_report import generate_pdf_report
            
            path, _ = QFileDialog.getSaveFileName(
                self,
                "Сохранить отчет",
                "wind_load_report.pdf",
                "PDF Files (*.pdf)"
            )
            
            if path:
                generate_pdf_report(path, self._last_calculation_result, self._current_blueprint)
                QMessageBox.information(self, "Успех", f"Отчет сохранен: {path}")
        except ImportError:
            QMessageBox.warning(self, "Ошибка", "Модуль экспорта отчетов не найден.")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось создать отчет: {str(e)}")
