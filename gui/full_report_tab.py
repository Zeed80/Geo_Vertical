"""
Вкладка ввода данных полного отчёта ДО ТСС.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Dict, Any, List

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QDateEdit,
    QGroupBox,
    QFormLayout,
    QDoubleSpinBox,
    QSpinBox,
    QPlainTextEdit,
    QScrollArea,
    QPushButton,
    QComboBox,
    QFileDialog,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
)

from gui.full_report_template_editor import FullReportTemplateEditor
from core.report_schema import (
    ReportMetadata,
    CustomerInfo,
    ContractorInfo,
    Specialist,
    EquipmentEntry,
    DocumentReference,
    LoadCondition,
    SoilCondition,
    ClimateParameters,
    StructuralDescription,
    VisualInspectionEntry,
    MeasurementSummary,
    ResidualResourceResult,
    Recommendation,
    Appendix,
    StructuralElement,
    TitleObjectInfo,
    FullReportData,
    AngleMeasurementRecord,
    VerticalDeviationRecord,
    StraightnessRecord,
    ThicknessMeasurementRecord,
    CoatingMeasurementRecord,
    UltrasonicInspectionRecord,
    ConcreteStrengthRecord,
    ProtectiveLayerRecord,
    VibrationRecord,
    SettlementRecord,
    ResourceCalculationData,
    AnnexEntry,
    InspectedObject,
    DocumentReviewEntry,
    TechnicalStateEntry,
    ConclusionEntry,
)
from core.services.report_templates import ReportTemplateManager
from core.services.report_templates import ReportDataAssembler
from utils.full_report_builder import FullReportBuilder


class FullReportTab(QWidget):
    """Интерактивная вкладка для подготовки полного отчёта."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.template_manager = ReportTemplateManager()
        self.builder = FullReportBuilder(self.template_manager)
        self.raw_data = None
        self.processed_data = None

        self.template_combo: QComboBox | None = None
        self.metadata_fields: Dict[str, QLineEdit | QDateEdit] = {}
        self.title_fields: Dict[str, QLineEdit | QSpinBox] = {}
        self.customer_fields: Dict[str, QLineEdit] = {}
        self.contractor_fields: Dict[str, QLineEdit] = {}
        self.load_fields: Dict[str, QDoubleSpinBox | QSpinBox] = {}
        self.climate_cold_edit: QPlainTextEdit | None = None
        self.climate_warm_edit: QPlainTextEdit | None = None
        self.structure_fields: Dict[str, QPlainTextEdit] = {}
        self.resource_fields: Dict[str, QDoubleSpinBox] = {}

        self.specialists_table = None
        self.equipment_table = None
        self.documents_table = None
        self.object_table = None
        self.soils_table = None
        self.visual_table = None
        self.measurements_table = None
        self.documents_review_table = None
        self.technical_state_table = None
        self.conclusions_table = None
        self.recommendations_table = None
        self.appendices_table = None
        self.structural_elements_table = None
        self.angle_table = None
        self.vertical_table = None
        self.straightness_table = None
        self.thickness_table = None
        self.coating_table = None
        self.ultrasonic_table = None
        self.concrete_table = None
        self.protective_table = None
        self.vibration_table = None
        self.settlement_table = None
        self.annexes_table = None

        self._build_ui()
        self._refresh_templates()

    # ------------------------------------------------------------------ UI ---
    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(6, 6, 6, 6)

        main_layout.addLayout(self._build_template_toolbar())

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        container = QWidget()
        scroll_layout = QVBoxLayout(container)
        scroll_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        scroll_layout.addWidget(self._build_metadata_group())
        scroll_layout.addWidget(self._build_title_object_group())
        scroll_layout.addWidget(self._build_customer_group())
        scroll_layout.addWidget(self._build_contractor_group())
        scroll_layout.addWidget(self._build_loads_group())
        scroll_layout.addWidget(self._build_climate_group())
        scroll_layout.addWidget(self._build_structure_group())

        self.specialists_table = self._create_table_group(
            "Специалисты", ["ФИО", "Аттестации (формат: ключ:№)", "Срок действия (формат: ключ:ДД.ММ.ГГГГ)"]
        )
        scroll_layout.addWidget(self.specialists_table.group)

        self.equipment_table = self._create_table_group(
            "Приборы и оборудование", ["Наименование", "Зав.№", "Свидетельство", "Действительно до (ДД.ММ.ГГГГ)"]
        )
        scroll_layout.addWidget(self.equipment_table.group)

        self.documents_table = self._create_table_group(
            "Документы", ["Название", "Идентификатор", "Комментарий"]
        )
        scroll_layout.addWidget(self.documents_table.group)

        self.object_table = self._create_table_group(
            "Перечень объектов обследования",
            ["Наименование", "Инвентарный №", "Год ввода", "Местонахождение", "Примечание"],
        )
        scroll_layout.addWidget(self.object_table.group)

        self.soils_table = self._create_table_group(
            "Инженерно-геологические условия", ["Тип грунта", "Глубина промерзания, м"]
        )
        scroll_layout.addWidget(self.soils_table.group)

        self.structural_elements_table = self._create_table_group(
            "Элементы решетки и поясов", ["Секция/отметка", "Элемент", "Материал", "Параметры", "Примечание"]
        )
        scroll_layout.addWidget(self.structural_elements_table.group)

        self.visual_table = self._create_table_group(
            "Визуальное обследование", ["Конструкция", "Дефекты"]
        )
        scroll_layout.addWidget(self.visual_table.group)

        self.measurements_table = self._create_table_group(
            "Инструментальные измерения", ["Метод", "Стандарт", "Результат"]
        )
        scroll_layout.addWidget(self.measurements_table.group)

        self.documents_review_table = self._create_table_group(
            "Результаты анализа документации", ["Документ", "Идентификатор", "Краткий вывод", "Заключение"]
        )
        scroll_layout.addWidget(self.documents_review_table.group)

        self.technical_state_table = self._create_table_group(
            "Оценка технического состояния", ["Конструкция", "Классификация", "Комментарии"]
        )
        scroll_layout.addWidget(self.technical_state_table.group)

        self.conclusions_table = self._create_table_group(
            "Выводы", ["Заголовок", "Текст вывода"]
        )
        scroll_layout.addWidget(self.conclusions_table.group)

        self.angle_table = self._create_table_group(
            "Журнал угловых измерений",
            ["№", "Секция", "Высота (м)", "Пояс", "KL", "KR", "KL-KR", "βизм", "Центр (мм)", "Δβ", "Δ (мм)"],
        )
        scroll_layout.addWidget(self.angle_table.group)

        self.vertical_table = self._create_table_group(
            "Отклонения ствола от вертикали", ["№ секции", "Отметка (м)", "Смещение 1 (мм)", "Смещение 2 (мм)"]
        )
        scroll_layout.addWidget(self.vertical_table.group)

        self.straightness_table = self._create_table_group(
            "Стрелы прогиба поясов", ["Пояс №", "Высота (м)", "Отклонение (мм)", "Допуск (мм)"]
        )
        scroll_layout.addWidget(self.straightness_table.group)

        self.thickness_table = self._create_table_group(
            "Протокол толщинометрии",
            ["Группа", "Место", "Норматив (мм)", "Показания (через /)", "Минимум (мм)", "Отклонение (%)"],
        )
        scroll_layout.addWidget(self.thickness_table.group)

        self.coating_table = self._create_table_group(
            "Протокол ЛКП",
            ["Группа", "Место", "Мин диапазон (мкм)", "Макс диапазон (мкм)", "Показания (через /)", "Минимум (мкм)"],
        )
        scroll_layout.addWidget(self.coating_table.group)

        self.ultrasonic_table = self._create_table_group(
            "Протокол УЗК",
            [
                "Место",
                "Толщина осн. (мм)",
                "Толщина измеренная (мм)",
                "Экв. площадь (мм²)",
                "Глубина (мм)",
                "Длина (мм)",
                "Тип дефекта",
                "Заключение",
            ],
        )
        scroll_layout.addWidget(self.ultrasonic_table.group)

        self.concrete_table = self._create_table_group(
            "Прочность бетона", ["Зона", "Rср (МПа)", "R* (МПа)"]
        )
        scroll_layout.addWidget(self.concrete_table.group)

        self.protective_table = self._create_table_group(
            "Защитный слой бетона", ["Место", "Допустимо (мм)", "Измерено (мм)", "Отклонение (%)"]
        )
        scroll_layout.addWidget(self.protective_table.group)

        self.vibration_table = self._create_table_group(
            "Протокол вибраций", ["Место", "Перемещения (x/y/z мкм)", "Частота (Гц)"]
        )
        scroll_layout.addWidget(self.vibration_table.group)

        self.settlement_table = self._create_table_group(
            "Осадки фундаментов", ["Марка", "Год", "Осадка (мм)"]
        )
        scroll_layout.addWidget(self.settlement_table.group)

        self.recommendations_table = self._create_table_group(
            "Рекомендации", ["Текст рекомендации"]
        )
        scroll_layout.addWidget(self.recommendations_table.group)

        self.appendices_table = self._create_table_group(
            "Приложения", ["Название", "Описание", "Файлы (через ; )"]
        )
        scroll_layout.addWidget(self.appendices_table.group)

        self.annexes_table = self._create_table_group(
            "Перечень приложений A–M", ["Код", "Название", "Описание", "Страницы (через ;)"]
        )
        scroll_layout.addWidget(self.annexes_table.group)

        scroll_layout.addWidget(self._build_resource_group())

        scroll_layout.addStretch()

        scroll_area.setWidget(container)
        main_layout.addWidget(scroll_area, stretch=1)

        main_layout.addLayout(self._build_actions_row())

    def _build_template_toolbar(self):
        layout = QHBoxLayout()
        layout.addWidget(QLabel("Шаблон:"))
        self.template_combo = QComboBox()
        layout.addWidget(self.template_combo, stretch=1)

        refresh_btn = QPushButton("🔄")
        refresh_btn.setToolTip("Обновить список шаблонов")
        refresh_btn.clicked.connect(self._refresh_templates)
        layout.addWidget(refresh_btn)

        load_btn = QPushButton("Загрузить")
        load_btn.clicked.connect(self._load_template)
        layout.addWidget(load_btn)

        save_btn = QPushButton("Сохранить как...")
        save_btn.clicked.connect(self._save_template)
        layout.addWidget(save_btn)

        auto_btn = QPushButton("Автозаполнение")
        auto_btn.setToolTip("Подставить результаты измерений и остаточный ресурс")
        auto_btn.clicked.connect(self._auto_fill_measurements)
        layout.addWidget(auto_btn)

        editor_btn = QPushButton("✏️")
        editor_btn.setToolTip("Редактировать шаблоны полного отчёта")
        editor_btn.clicked.connect(self._open_template_editor)
        layout.addWidget(editor_btn)

        return layout

    def _build_metadata_group(self):
        group = QGroupBox("Титульные данные")
        form = QFormLayout(group)

        def add_line(key, label, default=""):
            edit = QLineEdit(default)
            self.metadata_fields[key] = edit
            form.addRow(label, edit)

        add_line("report_number", "Номер отчёта:")
        add_line("project_name", "Наименование объекта:")
        add_line("inventory_number", "Инвентарный №:")
        add_line("location", "Местоположение:")
        add_line("customer_name", "Заказчик (для титула):")
        add_line("operator_name", "Исполнитель (для титула):")

        def add_date(key, label):
            edit = QDateEdit()
            edit.setCalendarPopup(True)
            edit.setDisplayFormat("dd.MM.yyyy")
            edit.setDate(date.today())
            self.metadata_fields[key] = edit
            form.addRow(label, edit)

        add_date("start_date", "Дата начала работ:")
        add_date("end_date", "Дата окончания:")
        add_line("approval_person", "Утверждающий:")
        add_line("approval_position", "Должность:")
        add_line("approval_city", "Город:")
        add_date("approval_date", "Дата утверждения:")

        return group

    def _build_title_object_group(self):
        group = QGroupBox("Паспорт объекта обследования")
        form = QFormLayout(group)

        def add_line(key: str, label: str, widget_cls=QLineEdit):
            widget = widget_cls()
            if isinstance(widget, QSpinBox):
                widget.setRange(1900, 2100)
                widget.setValue(date.today().year)
            self.title_fields[key] = widget
            form.addRow(label, widget)

        add_line("name", "Наименование объекта:")
        add_line("inventory_number", "Инвентарный №:")
        add_line("operator", "Эксплуатирующая организация:")
        add_line("location", "Местонахождение:")
        add_line("city", "Город печати:")
        add_line("year", "Год выпуска отчёта:", QSpinBox)
        return group

    def _build_resource_group(self):
        group = QGroupBox("Расчёт остаточного ресурса")
        form = QFormLayout(group)
        for key, label in [
            ("service_life_years", "Фактический срок эксплуатации, лет:"),
            ("wear_constant", "Постоянная износа λ:"),
            ("total_service_life_years", "Полный срок службы, лет:"),
            ("residual_resource_years", "Остаточный ресурс, лет:"),
            ("epsilon", "ε (повреждённость):"),
            ("lambda_value", "λ (расчётная):"),
        ]:
            spin = QDoubleSpinBox()
            spin.setDecimals(3)
            spin.setRange(0.0, 1000.0)
            if "λ" in label or "epsilon" in key:
                spin.setRange(0.0, 1.0)
            self.resource_fields[key] = spin
            form.addRow(label, spin)
        return group

    def _build_customer_group(self):
        group = QGroupBox("Сведения о заказчике")
        form = QFormLayout(group)
        for key, label in [
            ("full_name", "Полное наименование:"),
            ("director", "Руководитель:"),
            ("legal_address", "Юридический адрес:"),
            ("actual_address", "Местонахождение:"),
            ("phone", "Телефон:"),
            ("email", "E-mail:"),
        ]:
            edit = QLineEdit()
            self.customer_fields[key] = edit
            form.addRow(label, edit)
        return group

    def _build_contractor_group(self):
        group = QGroupBox("Сведения об исполнителе")
        form = QFormLayout(group)
        for key, label in [
            ("full_name", "Полное наименование:"),
            ("director", "Руководитель:"),
            ("legal_address", "Юридический адрес:"),
            ("postal_address", "Почтовый адрес:"),
            ("phone", "Телефон:"),
            ("email", "E-mail:"),
            ("accreditation_certificate", "Аттестация:"),
            ("sro_certificate", "СРО:"),
        ]:
            edit = QLineEdit()
            self.contractor_fields[key] = edit
            form.addRow(label, edit)
        return group

    def _build_loads_group(self):
        group = QGroupBox("Нагрузки и воздействия")
        form = QFormLayout(group)

        def add_spin(key, label, decimals=2, minimum=0.0, maximum=1000.0, suffix=""):
            if decimals == 0:
                widget = QSpinBox()
                widget.setRange(int(minimum), int(maximum))
            else:
                widget = QDoubleSpinBox()
                widget.setDecimals(decimals)
                widget.setRange(minimum, maximum)
            if suffix:
                widget.setSuffix(f" {suffix}")
            self.load_fields[key] = widget
            form.addRow(label, widget)

        add_spin("snow_load_kpa", "Снеговая нагрузка (кПа):", 2)
        add_spin("wind_pressure_kpa", "Ветровое давление (кПа):", 2)
        add_spin("icing_mm", "Толщина гололёда (мм):", 1)
        add_spin("seismicity", "Сейсмичность (баллы):", 0, 0, 12)
        add_spin("reliability_factor", "Коэффициент надёжности:", 2, 0.1, 5.0)

        return group

    def _build_climate_group(self):
        group = QGroupBox("Климатические параметры")
        layout = QVBoxLayout(group)
        self.climate_cold_edit = QPlainTextEdit()
        self.climate_cold_edit.setPlaceholderText("Параметры холодного периода (текст или список)")
        self.climate_warm_edit = QPlainTextEdit()
        self.climate_warm_edit.setPlaceholderText("Параметры тёплого периода (текст или список)")
        layout.addWidget(QLabel("Холодный период:"))
        layout.addWidget(self.climate_cold_edit)
        layout.addWidget(QLabel("Тёплый период:"))
        layout.addWidget(self.climate_warm_edit)
        return group

    def _build_structure_group(self):
        group = QGroupBox("Описание конструкций")
        layout = QVBoxLayout(group)
        for key, label in [
            ("purpose", "Назначение сооружения:"),
            ("planning_decisions", "Объёмно-планировочные решения:"),
            ("structural_scheme", "Конструктивная схема:"),
            ("foundations", "Фундаменты:"),
            ("metal_structure", "Металлоконструкции:"),
            ("geology", "Инженерно-геологические условия:"),
            ("lattice_notes", "Особенности решётки/узлов:"),
        ]:
            edit = QPlainTextEdit()
            edit.setPlaceholderText(label)
            self.structure_fields[key] = edit
            layout.addWidget(QLabel(label))
            layout.addWidget(edit)
        return group

    def _create_table_group(self, title: str, headers: List[str]):
        group = QGroupBox(title)
        layout = QVBoxLayout(group)
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(table)

        btn_layout = QHBoxLayout()
        add_btn = QPushButton("Добавить")
        remove_btn = QPushButton("Удалить выбранное")
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(remove_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        def add_row():
            table.insertRow(table.rowCount())

        def remove_selected():
            selected = sorted({idx.row() for idx in table.selectedIndexes()}, reverse=True)
            for row in selected:
                table.removeRow(row)

        add_btn.clicked.connect(add_row)
        remove_btn.clicked.connect(remove_selected)

        table.group = group  # type: ignore[attr-defined]
        table.headers = headers  # type: ignore[attr-defined]
        return table

    def _build_actions_row(self):
        layout = QHBoxLayout()
        layout.addStretch()

        clear_btn = QPushButton("Очистить")
        clear_btn.clicked.connect(self.clear_form)
        layout.addWidget(clear_btn)

        generate_btn = QPushButton("Сформировать полный отчёт")
        generate_btn.clicked.connect(self._generate_report)
        layout.addWidget(generate_btn)

        return layout

    # -------------------------------------------------------- Template logic
    def _refresh_templates(self):
        if not self.template_combo:
            return
        self.template_combo.blockSignals(True)
        self.template_combo.clear()
        templates = self.template_manager.list_templates()
        if templates:
            self.template_combo.addItems(templates)
            self.template_combo.setEnabled(True)
        else:
            self.template_combo.addItem("Нет шаблонов")
            self.template_combo.setEnabled(False)
        self.template_combo.blockSignals(False)

    def _load_template(self):
        if not self.template_combo:
            return
        if not self.template_combo.isEnabled():
            QMessageBox.information(self, "Шаблоны", "Создайте или импортируйте шаблон через редактор (кнопка ✏️).")
            return
        name = self.template_combo.currentText()
        if not name:
            QMessageBox.information(self, "Шаблон", "Нет выбранного шаблона.")
            return
        try:
            data = self.template_manager.load_template(name)
            self.populate_form(data)
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить шаблон:\n{exc}")

    def _save_template(self):
        try:
            data = self.collect_form_data()
        except ValueError as exc:
            QMessageBox.warning(self, "Недостаточно данных", str(exc))
            return

        from PyQt6.QtWidgets import QInputDialog

        name, ok = QInputDialog.getText(self, "Имя шаблона", "Введите название шаблона:")
        if not ok or not name.strip():
            return
        try:
            self.template_manager.save_template(data, name.strip())
            self._refresh_templates()
            QMessageBox.information(self, "Готово", f"Шаблон «{name}» сохранён.")
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить шаблон:\n{exc}")

    def _open_template_editor(self):
        editor = FullReportTemplateEditor(self)
        if editor.exec():
            self._refresh_templates()

    def _auto_fill_measurements(self):
        if not self.processed_data:
            QMessageBox.warning(self, "Нет данных", "Сначала выполните расчёт вертикальности/прямолинейности.")
            return
        try:
            data = self.collect_form_data()
        except ValueError as exc:
            QMessageBox.warning(self, "Недостаточно данных", str(exc))
            return
        assembler = ReportDataAssembler(self.processed_data, self.raw_data)
        enriched = assembler.fill_measurement_sections(data)
        self.populate_form(enriched, preserve_manual=True)
        QMessageBox.information(self, "Готово", "Технические разделы дополнены расчётными данными.")

    # ----------------------------------------------------------- Form utils
    def clear_form(self):
        for widget in self.metadata_fields.values():
            if isinstance(widget, QLineEdit):
                widget.clear()
            elif isinstance(widget, QDateEdit):
                widget.setDate(date.today())
        for field in (self.customer_fields | self.contractor_fields).values():
            field.clear()
        for widget in self.title_fields.values():
            if isinstance(widget, QLineEdit):
                widget.clear()
            elif isinstance(widget, QSpinBox):
                widget.setValue(date.today().year)
        for spin in self.load_fields.values():
            if isinstance(spin, QDoubleSpinBox | QSpinBox):
                spin.setValue(0)
        for spin in self.resource_fields.values():
            spin.setValue(0)
        if self.climate_cold_edit:
            self.climate_cold_edit.clear()
        if self.climate_warm_edit:
            self.climate_warm_edit.clear()
        for edit in self.structure_fields.values():
            edit.clear()
        for table in [
            self.specialists_table,
            self.equipment_table,
            self.documents_table,
            self.object_table,
            self.soils_table,
            self.visual_table,
            self.measurements_table,
            self.documents_review_table,
            self.technical_state_table,
            self.conclusions_table,
            self.recommendations_table,
            self.appendices_table,
            self.structural_elements_table,
            self.angle_table,
            self.vertical_table,
            self.straightness_table,
            self.thickness_table,
            self.coating_table,
            self.ultrasonic_table,
            self.concrete_table,
            self.protective_table,
            self.vibration_table,
            self.settlement_table,
            self.annexes_table,
        ]:
            if table:
                table.setRowCount(0)

    def set_source_data(self, raw_data, processed_data):
        self.raw_data = raw_data
        self.processed_data = processed_data

    # ---------------------------------------------------------- Serialization
    def serialize_state(self) -> Dict[str, Any]:
        try:
            return self.collect_form_data().to_dict()
        except ValueError:
            return {}

    def load_state(self, state: Dict[str, Any]):
        if not state:
            return
        try:
            data = FullReportData.from_dict(state)
            self.populate_form(data)
        except Exception as exc:
            QMessageBox.warning(self, "Ошибка восстановления", f"Не удалось восстановить вкладку полного отчёта:\n{exc}")

    # ---------------------------------------------------------- Data mapping
    def collect_form_data(self) -> FullReportData:
        metadata = ReportMetadata(
            report_number=self._text_value(self.metadata_fields["report_number"]),
            project_name=self._text_value(self.metadata_fields["project_name"]),
            inventory_number=self._text_value(self.metadata_fields["inventory_number"]),
            location=self._text_value(self.metadata_fields["location"]),
            customer_name=self._text_value(self.metadata_fields["customer_name"]),
            operator_name=self._text_value(self.metadata_fields["operator_name"]),
            start_date=self._date_value(self.metadata_fields["start_date"]),
            end_date=self._date_value(self.metadata_fields["end_date"]),
            approval_person=self._text_value(self.metadata_fields["approval_person"]),
            approval_position=self._text_value(self.metadata_fields["approval_position"]),
            approval_city=self._text_value(self.metadata_fields["approval_city"]),
            approval_date=self._date_value(self.metadata_fields["approval_date"]),
        )

        if not metadata.project_name:
            raise ValueError("Укажите наименование объекта в титульном блоке.")
        if not metadata.report_number:
            raise ValueError("Укажите номер отчёта.")

        customer = CustomerInfo(**{k: self.customer_fields[k].text() for k in self.customer_fields})
        contractor = ContractorInfo(**{k: self.contractor_fields[k].text() for k in self.contractor_fields})

        title_object = None
        if self.title_fields["name"].text().strip():
            title_object = TitleObjectInfo(
                name=self.title_fields["name"].text().strip(),
                inventory_number=self.title_fields["inventory_number"].text().strip(),
                operator=self.title_fields["operator"].text().strip(),
                location=self.title_fields["location"].text().strip(),
                city=self.title_fields["city"].text().strip(),
                year=int(self.title_fields["year"].value()),
            )

        loads = LoadCondition(
            snow_load_kpa=float(self.load_fields["snow_load_kpa"].value()),
            wind_pressure_kpa=float(self.load_fields["wind_pressure_kpa"].value()),
            icing_mm=float(self.load_fields["icing_mm"].value()),
            seismicity=int(self.load_fields["seismicity"].value()),
            reliability_factor=float(self.load_fields["reliability_factor"].value()),
        )

        climate = ClimateParameters(
            cold_period={"text": self.climate_cold_edit.toPlainText() if self.climate_cold_edit else ""},
            warm_period={"text": self.climate_warm_edit.toPlainText() if self.climate_warm_edit else ""},
        )

        structure = StructuralDescription(
            purpose=self.structure_fields["purpose"].toPlainText(),
            planning_decisions=self.structure_fields["planning_decisions"].toPlainText(),
            structural_scheme=self.structure_fields["structural_scheme"].toPlainText(),
            geology=self.structure_fields["geology"].toPlainText(),
            foundations=self.structure_fields["foundations"].toPlainText(),
            metal_structure=self.structure_fields["metal_structure"].toPlainText(),
            lattice_notes=self.structure_fields["lattice_notes"].toPlainText(),
        )

        resource_calc = None
        if any(spin.value() for spin in self.resource_fields.values()):
            resource_calc = ResourceCalculationData(
                service_life_years=float(self.resource_fields["service_life_years"].value()),
                wear_constant=float(self.resource_fields["wear_constant"].value()),
                total_service_life_years=float(self.resource_fields["total_service_life_years"].value()),
                residual_resource_years=float(self.resource_fields["residual_resource_years"].value()),
                epsilon=float(self.resource_fields["epsilon"].value()),
                lambda_value=float(self.resource_fields["lambda_value"].value()),
            )

        return FullReportData(
            metadata=metadata,
            customer=customer,
            contractor=contractor,
            specialists=self._table_to_specialists(self.specialists_table),
            equipment=self._table_to_equipment(self.equipment_table),
            documents=self._table_to_documents(self.documents_table),
            object_list=self._table_to_objects(self.object_table),
            loads=loads,
            soils=self._table_to_soils(self.soils_table),
            climate=climate,
            structure=structure,
            objects=[],
            documents_review=self._table_to_document_reviews(self.documents_review_table),
            normative_list=[],
            technical_state=self._table_to_technical_state(self.technical_state_table),
            visual_inspection=self._table_to_visual(self.visual_table),
            conclusions=self._table_to_conclusions(self.conclusions_table),
            measurements=self._table_to_measurements(self.measurements_table),
            residual_resource=None,
            materials_research=[],
            geodesic_results={},
            calculation_results={},
            recommendations=self._table_to_recommendations(self.recommendations_table),
            appendices=self._table_to_appendices(self.appendices_table),
            structural_elements=self._table_to_structural_elements(self.structural_elements_table),
            title_object=title_object,
            angle_measurements=self._table_to_angle_measurements(self.angle_table),
            vertical_deviation_table=self._table_to_vertical_deviation(self.vertical_table),
            straightness_records=self._table_to_straightness(self.straightness_table),
            thickness_measurements=self._table_to_thickness(self.thickness_table),
            coating_measurements=self._table_to_coating(self.coating_table),
            ultrasonic_records=self._table_to_ultrasonic(self.ultrasonic_table),
            concrete_strength_records=self._table_to_concrete(self.concrete_table),
            protective_layer_records=self._table_to_protective(self.protective_table),
            vibration_records=self._table_to_vibration(self.vibration_table),
            settlement_records=self._table_to_settlement(self.settlement_table),
            resource_calculation=resource_calc,
            annexes=self._table_to_annexes(self.annexes_table),
        )

    def populate_form(self, data: FullReportData, preserve_manual: bool = False):
        # Metadata
        for key, widget in self.metadata_fields.items():
            value = getattr(data.metadata, key)
            if isinstance(widget, QLineEdit):
                widget.setText(value)
            elif isinstance(widget, QDateEdit):
                widget.setDate(value)

        for field_map, obj in [
            (self.customer_fields, data.customer),
            (self.contractor_fields, data.contractor),
        ]:
            for key, edit in field_map.items():
                edit.setText(getattr(obj, key, ""))

        if data.title_object:
            self.title_fields["name"].setText(data.title_object.name)
            self.title_fields["inventory_number"].setText(data.title_object.inventory_number)
            self.title_fields["operator"].setText(data.title_object.operator)
            self.title_fields["location"].setText(data.title_object.location)
            self.title_fields["city"].setText(data.title_object.city)
            self.title_fields["year"].setValue(data.title_object.year)

        if data.loads:
            self.load_fields["snow_load_kpa"].setValue(data.loads.snow_load_kpa)
            self.load_fields["wind_pressure_kpa"].setValue(data.loads.wind_pressure_kpa)
            self.load_fields["icing_mm"].setValue(data.loads.icing_mm)
            self.load_fields["seismicity"].setValue(data.loads.seismicity)
            self.load_fields["reliability_factor"].setValue(data.loads.reliability_factor)

        if data.climate:
            if self.climate_cold_edit:
                self.climate_cold_edit.setPlainText(str(data.climate.cold_period.get("text", "")))
            if self.climate_warm_edit:
                self.climate_warm_edit.setPlainText(str(data.climate.warm_period.get("text", "")))

        if data.structure:
            for key, edit in self.structure_fields.items():
                edit.setPlainText(getattr(data.structure, key, "") or "")

        if data.resource_calculation:
            self.resource_fields["service_life_years"].setValue(data.resource_calculation.service_life_years)
            self.resource_fields["wear_constant"].setValue(data.resource_calculation.wear_constant)
            self.resource_fields["total_service_life_years"].setValue(data.resource_calculation.total_service_life_years)
            self.resource_fields["residual_resource_years"].setValue(
                data.resource_calculation.residual_resource_years
            )
            self.resource_fields["epsilon"].setValue(data.resource_calculation.epsilon)
            self.resource_fields["lambda_value"].setValue(data.resource_calculation.lambda_value)

        def populate_table(table, rows):
            if not table:
                return
            if not preserve_manual:
                table.setRowCount(0)
            else:
                table.setRowCount(0)
            for row_data in rows:
                row_idx = table.rowCount()
                table.insertRow(row_idx)
                for col, value in enumerate(row_data):
                    table.setItem(row_idx, col, QTableWidgetItem(value))

        def fmt(value, decimals=2):
            if value is None or value == "":
                return ""
            if isinstance(value, float):
                formatted = f"{value:.{decimals}f}"
                return formatted.rstrip("0").rstrip(".")
            return str(value)

        populate_table(
            self.specialists_table,
            [
                [
                    spec.full_name,
                    "\n".join(f"{k}:{v}" for k, v in spec.certifications.items()),
                    "\n".join(f"{k}:{v:%d.%m.%Y}" for k, v in spec.expires_at.items()),
                ]
                for spec in data.specialists
            ],
        )
        populate_table(
            self.equipment_table,
            [
                [eq.name, eq.serial_number, eq.certificate, eq.valid_until.strftime("%d.%m.%Y")]
                for eq in data.equipment
            ],
        )
        populate_table(
            self.documents_table,
            [[doc.title, doc.identifier, doc.comments or ""] for doc in data.documents],
        )
        populate_table(
            self.object_table,
            [
                [
                    obj.name,
                    obj.inventory_number or "",
                    fmt(obj.commissioning_year, 0),
                    obj.location or "",
                    obj.notes or "",
                ]
                for obj in data.object_list
            ],
        )
        populate_table(
            self.soils_table,
            [[soil.soil_type, str(soil.freezing_depth_m)] for soil in data.soils],
        )
        populate_table(
            self.structural_elements_table,
            [
                [el.section, el.element, el.material, el.parameters, el.notes or ""]
                for el in getattr(data, "structural_elements", [])
            ],
        )
        populate_table(
            self.visual_table,
            [[entry.element, entry.defects] for entry in data.visual_inspection],
        )
        populate_table(
            self.measurements_table,
            [[m.method, m.standard, m.result] for m in data.measurements],
        )
        populate_table(
            self.documents_review_table,
            [
                [item.title, item.identifier or "", item.summary or "", item.conclusion or ""]
                for item in data.documents_review
            ],
        )
        populate_table(
            self.technical_state_table,
            [
                [entry.structure, entry.classification, entry.comments or ""]
                for entry in data.technical_state
            ],
        )
        populate_table(
            self.conclusions_table,
            [[entry.label, entry.text] for entry in data.conclusions],
        )
        populate_table(
            self.recommendations_table,
            [[rec.text] for rec in data.recommendations],
        )
        populate_table(
            self.appendices_table,
            [[app.title, app.description or "", ";".join(app.files)] for app in data.appendices],
        )
        populate_table(
            self.angle_table,
            [
                [
                    fmt(record.index, 0),
                    record.section,
                    fmt(record.height_m),
                    record.belt,
                    fmt(record.kl_arcsec),
                    fmt(record.kr_arcsec),
                    fmt(record.diff_arcsec),
                    fmt(record.beta_measured),
                    fmt(record.center_value),
                    fmt(record.delta_beta),
                    fmt(record.delta_mm),
                ]
                for record in data.angle_measurements
            ],
        )
        populate_table(
            self.vertical_table,
            [
                [
                    fmt(record.section_number, 0),
                    fmt(record.height_m),
                    fmt(record.deviation_previous_mm),
                    fmt(record.deviation_current_mm),
                ]
                for record in data.vertical_deviation_table
            ],
        )
        populate_table(
            self.straightness_table,
            [
                [
                    fmt(record.belt_number, 0),
                    fmt(record.height_m),
                    fmt(record.deviation_mm),
                    fmt(record.tolerance_mm),
                ]
                for record in data.straightness_records
            ],
        )
        populate_table(
            self.thickness_table,
            [
                [
                    record.group_name,
                    record.location,
                    fmt(record.normative_thickness_mm),
                    " / ".join(fmt(value) for value in record.readings_mm),
                    fmt(record.min_value_mm),
                    fmt(record.deviation_percent),
                ]
                for record in data.thickness_measurements
            ],
        )
        populate_table(
            self.coating_table,
            [
                [
                    record.group_name,
                    record.location,
                    fmt(record.project_range_min_mkm),
                    fmt(record.project_range_max_mkm),
                    " / ".join(fmt(value) for value in record.readings_mkm),
                    fmt(record.min_value_mkm),
                ]
                for record in data.coating_measurements
            ],
        )
        populate_table(
            self.ultrasonic_table,
            [
                [
                    record.location,
                    fmt(record.base_thickness_mm),
                    fmt(record.sample_thickness_mm),
                    fmt(record.equivalent_area_mm2),
                    fmt(record.depth_mm),
                    fmt(record.length_mm),
                    record.defect_type or "",
                    record.conclusion,
                ]
                for record in data.ultrasonic_records
            ],
        )
        populate_table(
            self.concrete_table,
            [
                [record.zone, fmt(record.mean_strength_mpa), fmt(record.adjusted_strength_mpa)]
                for record in data.concrete_strength_records
            ],
        )
        populate_table(
            self.protective_table,
            [
                [record.location, fmt(record.allowed_mm), fmt(record.measured_mm), fmt(record.deviation_percent)]
                for record in data.protective_layer_records
            ],
        )
        populate_table(
            self.vibration_table,
            [
                [record.location, " / ".join(fmt(val) for val in record.displacement_microns), fmt(record.frequency_hz)]
                for record in data.vibration_records
            ],
        )
        populate_table(
            self.settlement_table,
            [[record.mark, fmt(record.year, 0), fmt(record.settlement_mm)] for record in data.settlement_records],
        )
        populate_table(
            self.annexes_table,
            [
                [annex.code, annex.title, annex.description or "", ";".join(map(str, annex.pages))]
                for annex in data.annexes
            ],
        )

    # ------------------------------------------------------------ Converters
    @staticmethod
    def _text_value(widget):
        return widget.text().strip() if isinstance(widget, QLineEdit) else ""

    @staticmethod
    def _date_value(widget):
        if isinstance(widget, QDateEdit):
            return widget.date().toPyDate()
        return date.today()

    @staticmethod
    def _parse_mapping(value: str) -> Dict[str, str]:
        mapping = {}
        for part in re.split(r"[;\n]+", value.strip()):
            if not part:
                continue
            if ":" in part:
                key, val = part.split(":", 1)
                mapping[key.strip()] = val.strip()
        return mapping

    @staticmethod
    def _parse_date_mapping(value: str) -> Dict[str, date]:
        mapping: Dict[str, date] = {}
        for part in re.split(r"[;\n]+", value.strip()):
            if not part:
                continue
            if ":" not in part:
                continue
            key, val = part.split(":", 1)
            key = key.strip()
            val = val.strip()
            try:
                day, month, year = map(int, val.replace(".", " ").split())
                mapping[key] = date(year, month, day)
            except Exception:
                continue
        return mapping

    @staticmethod
    def _safe_float(value: str) -> float | None:
        value = value.strip().replace(",", ".")
        if not value:
            return None
        try:
            return float(value)
        except ValueError:
            return None

    @staticmethod
    def _safe_int(value: str) -> int | None:
        value = value.strip()
        if not value:
            return None
        try:
            return int(float(value))
        except ValueError:
            return None

    @staticmethod
    def _split_numeric_series(value: str) -> List[float]:
        result = []
        for part in re.split(r"[\/,;]+", value.replace("|", "/")):
            part = part.strip()
            if not part:
                continue
            try:
                result.append(float(part.replace(",", ".")))
            except ValueError:
                continue
        return result

    def _table_to_specialists(self, table):
        result = []
        if not table:
            return result
        for row in self._iter_rows(table):
            certifications = self._parse_mapping(row[1])
            expires = self._parse_date_mapping(row[2])
            result.append(Specialist(full_name=row[0], certifications=certifications, expires_at=expires))
        return result

    def _table_to_equipment(self, table):
        result = []
        if not table:
            return result
        for row in self._iter_rows(table):
            try:
                day, month, year = map(int, row[3].replace(".", " ").split())
                dt = date(year, month, day)
            except Exception:
                dt = date.today()
            result.append(
                EquipmentEntry(
                    name=row[0],
                    serial_number=row[1],
                    certificate=row[2],
                    valid_until=dt,
                )
            )
        return result

    def _table_to_documents(self, table):
        if not table:
            return []
        return [DocumentReference(title=row[0], identifier=row[1], comments=row[2]) for row in self._iter_rows(table)]

    def _table_to_objects(self, table):
        if not table:
            return []
        items = []
        for row in self._iter_rows(table):
            year = self._safe_int(row[2]) if row[2] else None
            items.append(
                InspectedObject(
                    name=row[0],
                    inventory_number=row[1] or None,
                    commissioning_year=year,
                    location=row[3] or None,
                    notes=row[4] or None,
                )
            )
        return items

    def _table_to_soils(self, table):
        if not table:
            return []
        items = []
        for row in self._iter_rows(table):
            try:
                depth = float(row[1])
            except ValueError:
                depth = 0.0
            items.append(SoilCondition(soil_type=row[0], freezing_depth_m=depth))
        return items

    def _table_to_structural_elements(self, table):
        if not table:
            return []
        return [
            StructuralElement(section=row[0], element=row[1], material=row[2], parameters=row[3], notes=row[4])
            for row in self._iter_rows(table)
        ]

    def _table_to_visual(self, table):
        if not table:
            return []
        return [VisualInspectionEntry(element=row[0], defects=row[1]) for row in self._iter_rows(table)]

    def _table_to_measurements(self, table):
        if not table:
            return []
        return [MeasurementSummary(method=row[0], standard=row[1], result=row[2]) for row in self._iter_rows(table)]

    def _table_to_document_reviews(self, table):
        if not table:
            return []
        return [
            DocumentReviewEntry(title=row[0], identifier=row[1], summary=row[2], conclusion=row[3])
            for row in self._iter_rows(table)
        ]

    def _table_to_technical_state(self, table):
        if not table:
            return []
        return [
            TechnicalStateEntry(structure=row[0], classification=row[1], comments=row[2])
            for row in self._iter_rows(table)
        ]

    def _table_to_conclusions(self, table):
        if not table:
            return []
        return [ConclusionEntry(label=row[0], text=row[1]) for row in self._iter_rows(table)]

    def _table_to_recommendations(self, table):
        if not table:
            return []
        return [Recommendation(text=row[0]) for row in self._iter_rows(table)]

    def _table_to_appendices(self, table):
        if not table:
            return []
        appendices = []
        for row in self._iter_rows(table):
            files = [item.strip() for item in row[2].split(";") if item.strip()]
            appendices.append(Appendix(title=row[0], description=row[1], files=files))
        return appendices

    def _table_to_angle_measurements(self, table):
        if not table:
            return []
        records = []
        for row in self._iter_rows(table):
            records.append(
                AngleMeasurementRecord(
                    index=self._safe_int(row[0]) or len(records) + 1,
                    section=row[1],
                    height_m=self._safe_float(row[2]) or 0.0,
                    belt=row[3],
                    kl_arcsec=self._safe_float(row[4]),
                    kr_arcsec=self._safe_float(row[5]),
                    diff_arcsec=self._safe_float(row[6]),
                    beta_measured=self._safe_float(row[7]),
                    center_value=self._safe_float(row[8]),
                    delta_beta=self._safe_float(row[9]),
                    delta_mm=self._safe_float(row[10]),
                )
            )
        return records

    def _table_to_vertical_deviation(self, table):
        if not table:
            return []
        records = []
        for row in self._iter_rows(table):
            records.append(
                VerticalDeviationRecord(
                    section_number=self._safe_int(row[0]) or len(records) + 1,
                    height_m=self._safe_float(row[1]) or 0.0,
                    deviation_previous_mm=self._safe_float(row[2]),
                    deviation_current_mm=self._safe_float(row[3]),
                )
            )
        return records

    def _table_to_straightness(self, table):
        if not table:
            return []
        records = []
        for row in self._iter_rows(table):
            records.append(
                StraightnessRecord(
                    belt_number=self._safe_int(row[0]) or len(records) + 1,
                    height_m=self._safe_float(row[1]) or 0.0,
                    deviation_mm=self._safe_float(row[2]) or 0.0,
                    tolerance_mm=self._safe_float(row[3]) or 0.0,
                )
            )
        return records

    def _table_to_thickness(self, table):
        if not table:
            return []
        records = []
        for row in self._iter_rows(table):
            readings = self._split_numeric_series(row[3])
            records.append(
                ThicknessMeasurementRecord(
                    group_name=row[0],
                    location=row[1],
                    normative_thickness_mm=self._safe_float(row[2]) or 0.0,
                    readings_mm=readings,
                    min_value_mm=self._safe_float(row[4]) or (min(readings) if readings else 0.0),
                    deviation_percent=self._safe_float(row[5]) or 0.0,
                )
            )
        return records

    def _table_to_coating(self, table):
        if not table:
            return []
        records = []
        for row in self._iter_rows(table):
            readings = self._split_numeric_series(row[4])
            records.append(
                CoatingMeasurementRecord(
                    group_name=row[0],
                    location=row[1],
                    project_range_min_mkm=self._safe_float(row[2]) or 0.0,
                    project_range_max_mkm=self._safe_float(row[3]) or 0.0,
                    readings_mkm=readings,
                    min_value_mkm=self._safe_float(row[5]) or (min(readings) if readings else 0.0),
                )
            )
        return records

    def _table_to_ultrasonic(self, table):
        if not table:
            return []
        return [
            UltrasonicInspectionRecord(
                location=row[0],
                base_thickness_mm=self._safe_float(row[1]) or 0.0,
                sample_thickness_mm=self._safe_float(row[2]) or 0.0,
                equivalent_area_mm2=self._safe_float(row[3]),
                depth_mm=self._safe_float(row[4]),
                length_mm=self._safe_float(row[5]),
                defect_type=row[6],
                conclusion=row[7],
            )
            for row in self._iter_rows(table)
        ]

    def _table_to_concrete(self, table):
        if not table:
            return []
        return [
            ConcreteStrengthRecord(
                zone=row[0],
                mean_strength_mpa=self._safe_float(row[1]) or 0.0,
                adjusted_strength_mpa=self._safe_float(row[2]) or 0.0,
            )
            for row in self._iter_rows(table)
        ]

    def _table_to_protective(self, table):
        if not table:
            return []
        return [
            ProtectiveLayerRecord(
                location=row[0],
                allowed_mm=self._safe_float(row[1]) or 0.0,
                measured_mm=self._safe_float(row[2]) or 0.0,
                deviation_percent=self._safe_float(row[3]) or 0.0,
            )
            for row in self._iter_rows(table)
        ]

    def _table_to_vibration(self, table):
        if not table:
            return []
        records = []
        for row in self._iter_rows(table):
            records.append(
                VibrationRecord(
                    location=row[0],
                    displacement_microns=self._split_numeric_series(row[1]),
                    frequency_hz=self._safe_float(row[2]) or 0.0,
                )
            )
        return records

    def _table_to_settlement(self, table):
        if not table:
            return []
        return [
            SettlementRecord(
                mark=row[0],
                year=self._safe_int(row[1]) or date.today().year,
                settlement_mm=self._safe_float(row[2]) or 0.0,
            )
            for row in self._iter_rows(table)
        ]

    def _table_to_annexes(self, table):
        if not table:
            return []
        annexes = []
        for row in self._iter_rows(table):
            pages = []
            for part in row[3].split(";"):
                part = part.strip()
                if not part:
                    continue
                value = self._safe_int(part)
                if value is not None:
                    pages.append(value)
            annexes.append(AnnexEntry(code=row[0], title=row[1], description=row[2], pages=pages))
        return annexes

    @staticmethod
    def _iter_rows(table: QTableWidget):
        for row in range(table.rowCount()):
            yield [
                table.item(row, col).text().strip() if table.item(row, col) else ""
                for col in range(table.columnCount())
            ]

    # ---------------------------------------------------------- Generation
    def _generate_report(self):
        try:
            base_data = self.collect_form_data()
        except ValueError as exc:
            QMessageBox.warning(self, "Недостаточно данных", str(exc))
            return

        assembler = ReportDataAssembler(self.processed_data or {}, self.raw_data)
        enriched = assembler.fill_measurement_sections(base_data)

        documents_dir = Path(self.template_manager.storage_dir).parent
        report_number = self._sanitize_filename(base_data.metadata.report_number) or "full_report"
        default_path = documents_dir / f"{report_number}.docx"

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить полный отчёт", str(default_path), "Word файлы (*.docx)"
        )
        if not file_path:
            return
        try:
            self.builder.build_docx(enriched, file_path)
            QMessageBox.information(self, "Готово", f"Полный отчёт сохранён:\n{file_path}")
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка", f"Не удалось сформировать отчёт:\n{exc}")

    @staticmethod
    def _sanitize_filename(value: str) -> str:
        safe_chars = "".join(ch for ch in value if ch.isalnum() or ch in ("-", "_"))
        return safe_chars.strip("_-")

