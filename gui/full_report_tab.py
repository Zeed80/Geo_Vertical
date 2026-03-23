"""
Вкладка ввода данных полного отчёта ДО ТСС.
"""

from __future__ import annotations

import re
import shutil
from datetime import date, datetime
from html import escape
from pathlib import Path
from typing import Dict, Any, List

from PyQt6.QtCore import Qt, QTimer, QStringListModel
from PyQt6.QtWidgets import (
    QApplication,
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
    QCompleter,
    QFileDialog,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QListWidget,
    QListWidgetItem,
    QSplitter,
    QInputDialog,
)

from gui.full_report_template_editor import FullReportTemplateEditor
from core.full_report_models import (
    AttachmentManifestEntry,
    FullReportDraftState,
    OfficialReportContext,
    ReleaseManifest,
    SurveyStationEntry,
)
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
from utils.settings_manager import SettingsManager


class FullReportTab(QWidget):
    """Интерактивная вкладка для подготовки полного отчёта."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.template_manager = ReportTemplateManager()
        self.builder = FullReportBuilder(self.template_manager)
        self.settings_manager = SettingsManager()
        self.raw_data = None
        self.processed_data = None
        self.import_context: Dict[str, Any] = {}
        self.import_diagnostics: Dict[str, Any] = {}
        self.project_path: str | None = None
        self.tower_blueprint = None
        self.angular_measurements: Dict[str, Any] = {}
        self._loading_state = False
        self._current_section_key = "title"
        self._last_loaded_state: Dict[str, Any] = {}
        self.field_provenance: Dict[str, str] = {}
        self.dirty_sections: List[str] = []
        self.shared_report_info: Dict[str, Any] = {}
        self.preview_timer = QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.setInterval(450)
        self.preview_timer.timeout.connect(self._refresh_preview)

        self.template_combo: QComboBox | None = None
        self.preview_mode_combo: QComboBox | None = None
        self.preview_browser: QTextBrowser | None = None
        self.section_list: QListWidget | None = None
        self.section_status_label: QLabel | None = None
        self.metadata_fields: Dict[str, QLineEdit | QDateEdit] = {}
        self.title_fields: Dict[str, QLineEdit | QSpinBox] = {}
        self.customer_fields: Dict[str, QLineEdit] = {}
        self.contractor_fields: Dict[str, QLineEdit] = {}
        self.official_fields: Dict[str, QLineEdit | QDateEdit | QComboBox | QSpinBox | QPlainTextEdit] = {}
        self.load_fields: Dict[str, QDoubleSpinBox | QSpinBox] = {}
        self.climate_cold_edit: QPlainTextEdit | None = None
        self.climate_warm_edit: QPlainTextEdit | None = None
        self.structure_fields: Dict[str, QPlainTextEdit] = {}
        self.resource_fields: Dict[str, QDoubleSpinBox] = {}
        self.station_table = None
        self.form_scroll_area: QScrollArea | None = None
        self.section_anchors: Dict[str, QWidget] = {}

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
        self.normatives_table = None

        self._build_ui()
        for field_name in ("name", "inventory_number", "operator", "location"):
            widget = self.title_fields.get(field_name)
            if isinstance(widget, QLineEdit):
                widget.setReadOnly(True)
                widget.setToolTip("РџРѕР»Рµ РїРѕРґС‚СЏРіРёРІР°РµС‚СЃСЏ РёР· РѕСЃРЅРѕРІРЅС‹С… СЂРµРєРІРёР·РёС‚РѕРІ.")
        self._refresh_templates()

    def _build_metadata_group(self):
        group = QGroupBox("Титульные данные")
        form = QFormLayout(group)
        note = QLabel("РќР°РёРјРµРЅРѕРІР°РЅРёРµ, РёРЅРІРµРЅС‚Р°СЂРЅС‹Р№ РЅРѕРјРµСЂ, РѕСЂРіР°РЅРёР·Р°С†РёСЏ Рё Р°РґСЂРµСЃ Р±РµСЂСѓС‚СЃСЏ РёР· РѕСЃРЅРѕРІРЅС‹С… СЂРµРєРІРёР·РёС‚РѕРІ, С‡С‚РѕР±С‹ РЅРµ РІРІРѕРґРёС‚СЊ РёС… РїРѕРІС‚РѕСЂРЅРѕ.")
        note.setWordWrap(True)
        form.addRow(note)
        note = QLabel("Р—Р°РїРѕР»РЅСЏР№С‚Рµ РѕСЃРЅРѕРІРЅС‹Рµ СЂРµРєРІРёР·РёС‚С‹ РѕРґРёРЅ СЂР°Р·. РќРёР¶Рµ РѕРЅРё Р±СѓРґСѓС‚ РёСЃРїРѕР»СЊР·РѕРІР°РЅС‹ РІРѕ РІСЃРµС… СЂР°Р·РґРµР»Р°С….")
        note.setWordWrap(True)
        form.addRow(note)

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

        def add_line(key: str, label: str, widget_cls=QLineEdit, read_only: bool = False):
            widget = widget_cls()
            if isinstance(widget, QSpinBox):
                widget.setRange(1900, 2100)
                widget.setValue(date.today().year)
            elif isinstance(widget, QLineEdit) and read_only:
                widget.setReadOnly(True)
                widget.setToolTip("РџРѕР»Рµ РїРѕРґС‚СЏРіРёРІР°РµС‚СЃСЏ РёР· РѕР±С‰РёС… СЂРµРєРІРёР·РёС‚РѕРІ.")
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

    def _build_metadata_group(self):
        group = QGroupBox("\u0422\u0438\u0442\u0443\u043b\u044c\u043d\u044b\u0435 \u0434\u0430\u043d\u043d\u044b\u0435")
        form = QFormLayout(group)
        note = QLabel(
            "\u0417\u0430\u043f\u043e\u043b\u043d\u0438\u0442\u0435 \u043e\u0441\u043d\u043e\u0432\u043d\u044b\u0435 \u0440\u0435\u043a\u0432\u0438\u0437\u0438\u0442\u044b \u043e\u0434\u0438\u043d \u0440\u0430\u0437. "
            "\u041d\u0430\u0438\u043c\u0435\u043d\u043e\u0432\u0430\u043d\u0438\u0435, \u0438\u043d\u0432\u0435\u043d\u0442\u0430\u0440\u043d\u044b\u0439 \u043d\u043e\u043c\u0435\u0440 \u0438 \u043c\u0435\u0441\u0442\u043e\u043f\u043e\u043b\u043e\u0436\u0435\u043d\u0438\u0435 "
            "\u0434\u0430\u043b\u044c\u0448\u0435 \u0431\u0443\u0434\u0443\u0442 \u0438\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043d\u044b \u0430\u0432\u0442\u043e\u043c\u0430\u0442\u0438\u0447\u0435\u0441\u043a\u0438."
        )
        note.setWordWrap(True)
        form.addRow(note)

        def add_line(key, label, default=""):
            edit = QLineEdit(default)
            self.metadata_fields[key] = edit
            form.addRow(label, edit)

        add_line("report_number", "\u041d\u043e\u043c\u0435\u0440 \u043e\u0442\u0447\u0451\u0442\u0430:")
        add_line("project_name", "\u041d\u0430\u0438\u043c\u0435\u043d\u043e\u0432\u0430\u043d\u0438\u0435 \u043e\u0431\u044a\u0435\u043a\u0442\u0430:")
        add_line("inventory_number", "\u0418\u043d\u0432\u0435\u043d\u0442\u0430\u0440\u043d\u044b\u0439 \u2116:")
        add_line("location", "\u041c\u0435\u0441\u0442\u043e\u043f\u043e\u043b\u043e\u0436\u0435\u043d\u0438\u0435:")
        add_line("customer_name", "\u0417\u0430\u043a\u0430\u0437\u0447\u0438\u043a (\u0434\u043b\u044f \u0442\u0438\u0442\u0443\u043b\u0430):")
        add_line("operator_name", "\u0418\u0441\u043f\u043e\u043b\u043d\u0438\u0442\u0435\u043b\u044c (\u0434\u043b\u044f \u0442\u0438\u0442\u0443\u043b\u0430):")

        def add_date(key, label):
            edit = QDateEdit()
            edit.setCalendarPopup(True)
            edit.setDisplayFormat("dd.MM.yyyy")
            edit.setDate(date.today())
            self.metadata_fields[key] = edit
            form.addRow(label, edit)

        add_date("start_date", "\u0414\u0430\u0442\u0430 \u043d\u0430\u0447\u0430\u043b\u0430 \u0440\u0430\u0431\u043e\u0442:")
        add_date("end_date", "\u0414\u0430\u0442\u0430 \u043e\u043a\u043e\u043d\u0447\u0430\u043d\u0438\u044f:")
        add_line("approval_person", "\u0423\u0442\u0432\u0435\u0440\u0436\u0434\u0430\u044e\u0449\u0438\u0439:")
        add_line("approval_position", "\u0414\u043e\u043b\u0436\u043d\u043e\u0441\u0442\u044c:")
        add_line("approval_city", "\u0413\u043e\u0440\u043e\u0434:")
        add_date("approval_date", "\u0414\u0430\u0442\u0430 \u0443\u0442\u0432\u0435\u0440\u0436\u0434\u0435\u043d\u0438\u044f:")

        return group

    def _build_title_object_group(self):
        group = QGroupBox("\u041a\u0430\u0440\u0442\u043e\u0447\u043a\u0430 \u043e\u0431\u044a\u0435\u043a\u0442\u0430 (\u0430\u0432\u0442\u043e\u0437\u0430\u043f\u043e\u043b\u043d\u0435\u043d\u0438\u0435)")
        form = QFormLayout(group)
        note = QLabel(
            "\u041f\u043e\u043b\u044f \u043d\u0430\u0438\u043c\u0435\u043d\u043e\u0432\u0430\u043d\u0438\u044f, \u0438\u043d\u0432\u0435\u043d\u0442\u0430\u0440\u043d\u043e\u0433\u043e \u043d\u043e\u043c\u0435\u0440\u0430, \u043e\u0440\u0433\u0430\u043d\u0438\u0437\u0430\u0446\u0438\u0438 "
            "\u0438 \u043c\u0435\u0441\u0442\u043e\u043f\u043e\u043b\u043e\u0436\u0435\u043d\u0438\u044f \u0441\u0438\u043d\u0445\u0440\u043e\u043d\u0438\u0437\u0438\u0440\u0443\u044e\u0442\u0441\u044f \u0441 \u0442\u0438\u0442\u0443\u043b\u044c\u043d\u044b\u043c\u0438 \u0434\u0430\u043d\u043d\u044b\u043c\u0438. "
            "\u0412\u0440\u0443\u0447\u043d\u0443\u044e \u043e\u0431\u044b\u0447\u043d\u043e \u043d\u0443\u0436\u043d\u043e \u0443\u0442\u043e\u0447\u043d\u0438\u0442\u044c \u0442\u043e\u043b\u044c\u043a\u043e \u0433\u043e\u0440\u043e\u0434 \u0438 \u0433\u043e\u0434."
        )
        note.setWordWrap(True)
        form.addRow(note)

        def add_line(key: str, label: str, widget_cls=QLineEdit, read_only: bool = False):
            widget = widget_cls()
            if isinstance(widget, QSpinBox):
                widget.setRange(1900, 2100)
                widget.setValue(date.today().year)
            elif isinstance(widget, QLineEdit) and read_only:
                widget.setReadOnly(True)
                widget.setToolTip("\u041f\u043e\u043b\u0435 \u043f\u043e\u0434\u0442\u044f\u0433\u0438\u0432\u0430\u0435\u0442\u0441\u044f \u0438\u0437 \u043e\u0431\u0449\u0438\u0445 \u0440\u0435\u043a\u0432\u0438\u0437\u0438\u0442\u043e\u0432.")
            self.title_fields[key] = widget
            form.addRow(label, widget)

        add_line("name", "\u041d\u0430\u0438\u043c\u0435\u043d\u043e\u0432\u0430\u043d\u0438\u0435 \u043e\u0431\u044a\u0435\u043a\u0442\u0430:", read_only=True)
        add_line("inventory_number", "\u0418\u043d\u0432\u0435\u043d\u0442\u0430\u0440\u043d\u044b\u0439 \u2116:", read_only=True)
        add_line("operator", "\u042d\u043a\u0441\u043f\u043b\u0443\u0430\u0442\u0438\u0440\u0443\u044e\u0449\u0430\u044f \u043e\u0440\u0433\u0430\u043d\u0438\u0437\u0430\u0446\u0438\u044f:", read_only=True)
        add_line("location", "\u041c\u0435\u0441\u0442\u043e\u043d\u0430\u0445\u043e\u0436\u0434\u0435\u043d\u0438\u0435:", read_only=True)
        add_line("city", "\u0413\u043e\u0440\u043e\u0434 \u043f\u0435\u0447\u0430\u0442\u0438:")
        add_line("year", "\u0413\u043e\u0434 \u0432\u044b\u043f\u0443\u0441\u043a\u0430 \u043e\u0442\u0447\u0451\u0442\u0430:", QSpinBox)
        return group

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

    def _open_template_editor(self):
        editor = FullReportTemplateEditor(self)
        if editor.exec():
            self._refresh_templates()

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
            if preserve_manual and rows and table.rowCount() > 0:
                return
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
            self.normatives_table,
            [self._split_normative_entry(entry) for entry in data.normative_list],
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
        self._sync_identity_projection()

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
    def _split_normative_entry(entry: str) -> List[str]:
        parts = entry.strip().split(" ", 1)
        code = parts[0] if parts else ""
        title = parts[1] if len(parts) > 1 else ""
        return [code, title]

    def _table_to_normative_list(self, table) -> List[str]:
        if not table:
            return []
        result = []
        for row in self._iter_rows(table):
            code = row[0]
            title = row[1] if len(row) > 1 else ""
            if code:
                entry = f"{code} {title}".strip() if title else code
                result.append(entry)
        return result

    @staticmethod
    def _iter_rows(table: QTableWidget):
        for row in range(table.rowCount()):
            yield [
                table.item(row, col).text().strip() if table.item(row, col) else ""
                for col in range(table.columnCount())
            ]

    @staticmethod
    def _sanitize_filename(value: str) -> str:
        safe_chars = "".join(ch for ch in value if ch.isalnum() or ch in ("-", "_"))
        return safe_chars.strip("_-")

    # -------------------------------------------------- Draft/UI overrides
    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.addLayout(self._build_template_toolbar())

        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter, stretch=1)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QLabel("Разделы"))
        self.section_list = QListWidget()
        self.section_list.currentItemChanged.connect(self._on_section_selected)
        left_layout.addWidget(self.section_list, stretch=1)
        self.section_status_label = QLabel("Статусы разделов появятся после заполнения формы.")
        self.section_status_label.setWordWrap(True)
        left_layout.addWidget(self.section_status_label)
        splitter.addWidget(left_panel)

        self.form_scroll_area = QScrollArea()
        self.form_scroll_area.setWidgetResizable(True)
        container = QWidget()
        scroll_layout = QVBoxLayout(container)
        scroll_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        metadata_group = self._build_metadata_group()
        title_object_group = self._build_title_object_group()
        official_group = self._build_official_context_group()
        customer_group = self._build_customer_group()
        contractor_group = self._build_contractor_group()
        loads_group = self._build_loads_group()
        climate_group = self._build_climate_group()
        structure_group = self._build_structure_group()

        for widget in [
            metadata_group,
            title_object_group,
            official_group,
            customer_group,
            contractor_group,
            loads_group,
            climate_group,
            structure_group,
        ]:
            scroll_layout.addWidget(widget)

        self.specialists_table = self._create_table_group("Специалисты", ["ФИО", "Аттестации (ключ:№)", "Срок действия (ключ:ДД.ММ.ГГГГ)"])
        self.equipment_table = self._create_table_group("Приборы и оборудование", ["Наименование", "Зав.№", "Свидетельство", "Действительно до"])
        self.documents_table = self._create_table_group("Документы", ["Название", "Идентификатор", "Комментарий"])
        self.object_table = self._create_table_group("Перечень объектов обследования", ["Наименование", "Инвентарный №", "Год ввода", "Местонахождение", "Примечание"])
        self.object_table.group.setTitle("\u041f\u0435\u0440\u0435\u0447\u0435\u043d\u044c \u043e\u0431\u044a\u0435\u043a\u0442\u043e\u0432 \u043e\u0431\u0441\u043b\u0435\u0434\u043e\u0432\u0430\u043d\u0438\u044f (\u043f\u0435\u0440\u0432\u0430\u044f \u0441\u0442\u0440\u043e\u043a\u0430 \u0437\u0430\u043f\u043e\u043b\u043d\u044f\u0435\u0442\u0441\u044f \u0430\u0432\u0442\u043e\u043c\u0430\u0442\u0438\u0447\u0435\u0441\u043a\u0438)")
        self.object_table.group.setToolTip(
            "\u041f\u0435\u0440\u0432\u044b\u0439 \u043e\u0431\u044a\u0435\u043a\u0442 \u0441\u0438\u043d\u0445\u0440\u043e\u043d\u0438\u0437\u0438\u0440\u0443\u0435\u0442\u0441\u044f \u0438\u0437 \u0442\u0438\u0442\u0443\u043b\u044c\u043d\u044b\u0445 \u0440\u0435\u043a\u0432\u0438\u0437\u0438\u0442\u043e\u0432. "
            "\u0414\u043e\u0431\u0430\u0432\u043b\u044f\u0439\u0442\u0435 \u043d\u0438\u0436\u0435 \u0434\u043e\u043f\u043e\u043b\u043d\u0438\u0442\u0435\u043b\u044c\u043d\u044b\u0435 \u043e\u0431\u044a\u0435\u043a\u0442\u044b, \u0435\u0441\u043b\u0438 \u043e\u043d\u0438 \u0435\u0441\u0442\u044c."
        )
        self.soils_table = self._create_table_group("Инженерно-геологические условия", ["Тип грунта", "Глубина промерзания, м"])
        self.structural_elements_table = self._create_table_group("Элементы решетки и поясов", ["Секция/отметка", "Элемент", "Материал", "Параметры", "Примечание"])
        self.visual_table = self._create_table_group("Визуальное обследование", ["Конструкция", "Дефекты"])
        self.measurements_table = self._create_table_group("Инструментальные измерения", ["Метод", "Стандарт", "Результат"])
        self.documents_review_table = self._create_table_group("Результаты анализа документации", ["Документ", "Идентификатор", "Краткий вывод", "Заключение"])
        self.normatives_table = self._create_normatives_group()
        self.technical_state_table = self._create_table_group("Оценка технического состояния", ["Конструкция", "Классификация", "Комментарии"])
        self.conclusions_table = self._create_table_group("Выводы", ["Заголовок", "Текст вывода"])
        self.angle_table = self._create_table_group("Журнал угловых измерений", ["№", "Секция", "Высота (м)", "Пояс", "KL", "KR", "KL-KR", "βизм", "Центр (мм)", "Δβ", "Δ (мм)"])
        self.vertical_table = self._create_table_group("Отклонения ствола от вертикали", ["№ секции", "Отметка (м)", "Смещение 1 (мм)", "Смещение 2 (мм)"])
        self.straightness_table = self._create_table_group("Стрелы прогиба поясов", ["Пояс №", "Высота (м)", "Отклонение (мм)", "Допуск (мм)"])
        self.thickness_table = self._create_table_group("Протокол толщинометрии", ["Группа", "Место", "Норматив (мм)", "Показания (/)", "Минимум (мм)", "Отклонение (%)"])
        self.coating_table = self._create_table_group("Протокол ЛКП", ["Группа", "Место", "Мин диапазон (мкм)", "Макс диапазон (мкм)", "Показания (/)", "Минимум (мкм)"])
        self.ultrasonic_table = self._create_table_group("Протокол УЗК", ["Место", "Толщина осн. (мм)", "Толщина измеренная (мм)", "Экв. площадь (мм2)", "Глубина (мм)", "Длина (мм)", "Тип дефекта", "Заключение"])
        self.concrete_table = self._create_table_group("Прочность бетона", ["Зона", "Rср (МПа)", "R* (МПа)"])
        self.protective_table = self._create_table_group("Защитный слой бетона", ["Место", "Допустимо (мм)", "Измерено (мм)", "Отклонение (%)"])
        self.vibration_table = self._create_table_group("Протокол вибраций", ["Место", "Перемещения (x/y/z мкм)", "Частота (Гц)"])
        self.settlement_table = self._create_table_group("Осадки фундаментов", ["Марка", "Год", "Осадка (мм)"])
        self.recommendations_table = self._create_table_group("Рекомендации", ["Текст рекомендации"])
        self.appendices_table = self._create_table_group("Приложения", ["Название", "Описание", "Файлы (через ;)"])
        self.annexes_table = self._create_table_group("Перечень приложений A-M", ["Код", "Название", "Описание", "Страницы (через ;)"])

        scroll_layout.addWidget(self.normatives_table.group)

        for table in [
            self.specialists_table,
            self.equipment_table,
            self.documents_table,
            self.object_table,
            self.soils_table,
            self.structural_elements_table,
            self.visual_table,
            self.measurements_table,
            self.documents_review_table,
            self.technical_state_table,
            self.conclusions_table,
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
            self.recommendations_table,
            self.appendices_table,
            self.annexes_table,
        ]:
            scroll_layout.addWidget(table.group)

        resource_group = self._build_resource_group()
        scroll_layout.addWidget(resource_group)
        scroll_layout.addStretch()

        self.form_scroll_area.setWidget(container)
        splitter.addWidget(self.form_scroll_area)

        preview_panel = QWidget()
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_header = QHBoxLayout()
        preview_header.addWidget(QLabel("Предпросмотр"))
        self.preview_mode_combo = QComboBox()
        self.preview_mode_combo.addItem("Весь документ", "document")
        self.preview_mode_combo.addItem("Текущий раздел", "section")
        self.preview_mode_combo.addItem("Ошибки и предупреждения", "errors")
        self.preview_mode_combo.currentIndexChanged.connect(lambda *_: self._refresh_preview())
        preview_header.addWidget(self.preview_mode_combo)
        preview_layout.addLayout(preview_header)
        self.preview_browser = QTextBrowser()
        preview_layout.addWidget(self.preview_browser, stretch=1)
        splitter.addWidget(preview_panel)
        splitter.setSizes([190, 760, 560])

        self.section_anchors = {
            "title": metadata_group,
            "participants": official_group,
            "normatives": structure_group,
            "measurements": self.angle_table.group,
            "results": self.technical_state_table.group,
            "appendices": self.appendices_table.group,
        }
        self._populate_section_list()
        self._connect_form_change_tracking()
        self._setup_completers()

        actions_row = QHBoxLayout()
        import_project_btn = QPushButton("Импорт из проекта")
        import_project_btn.setToolTip("Импортировать организации/специалистов/оборудование из другого проекта (.gvproj)")
        import_project_btn.clicked.connect(self._import_from_project)
        actions_row.addWidget(import_project_btn)

        actions_row.addStretch()
        clear_btn = QPushButton("Очистить")
        clear_btn.clicked.connect(self.clear_form)
        actions_row.addWidget(clear_btn)
        generate_btn = QPushButton("Сформировать DOCX / PDF")
        generate_btn.clicked.connect(self._generate_report)
        actions_row.addWidget(generate_btn)
        main_layout.addLayout(actions_row)

    def _create_table_group(self, title: str, headers: List[str]):
        group = QGroupBox(title)
        layout = QVBoxLayout(group)
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.horizontalHeader().setStretchLastSection(True)
        for index, header in enumerate(headers):
            item = table.horizontalHeaderItem(index)
            if item is not None:
                item.setToolTip(header)
        layout.addWidget(table)

        btn_layout = QHBoxLayout()
        add_btn = QPushButton("Добавить")
        duplicate_btn = QPushButton("Дублировать")
        paste_btn = QPushButton("Вставить")
        remove_btn = QPushButton("Удалить")
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(duplicate_btn)
        btn_layout.addWidget(paste_btn)
        btn_layout.addWidget(remove_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        def add_row():
            table.insertRow(table.rowCount())

        def duplicate_selected():
            selected_rows = sorted({idx.row() for idx in table.selectedIndexes()})
            for row in selected_rows:
                row_idx = table.rowCount()
                table.insertRow(row_idx)
                for col in range(table.columnCount()):
                    source = table.item(row, col)
                    table.setItem(row_idx, col, QTableWidgetItem(source.text() if source else ""))

        def paste_from_clipboard():
            text = QApplication.clipboard().text()
            if not text.strip():
                return
            for raw_row in [line for line in text.splitlines() if line.strip()]:
                cells = raw_row.split("\t")
                row_idx = table.rowCount()
                table.insertRow(row_idx)
                for col, cell in enumerate(cells[:table.columnCount()]):
                    table.setItem(row_idx, col, QTableWidgetItem(cell.strip()))

        def remove_selected():
            selected = sorted({idx.row() for idx in table.selectedIndexes()}, reverse=True)
            for row in selected:
                table.removeRow(row)

        add_btn.clicked.connect(add_row)
        duplicate_btn.clicked.connect(duplicate_selected)
        paste_btn.clicked.connect(paste_from_clipboard)
        remove_btn.clicked.connect(remove_selected)
        table.cellChanged.connect(lambda *_: self._on_form_changed())

        table.group = group  # type: ignore[attr-defined]
        table.headers = headers  # type: ignore[attr-defined]
        return table

    def _create_normatives_group(self):
        from core.normatives import NORMATIVE_REFERENCES, get_normatives_for_structure
        group = QGroupBox("Нормативные документы")
        layout = QVBoxLayout(group)

        table = QTableWidget(0, 2)
        table.setHorizontalHeaderLabels(["Обозначение", "Наименование"])
        table.horizontalHeader().setStretchLastSection(True)
        table.setColumnWidth(0, 200)
        layout.addWidget(table)

        btn_layout = QHBoxLayout()
        add_btn = QPushButton("Добавить")
        remove_btn = QPushButton("Удалить")
        autofill_btn = QPushButton("Заполнить по типу опоры")
        autofill_btn.setToolTip("Автозаполнение нормативов из справочника на основе типа опоры")
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(remove_btn)
        btn_layout.addWidget(autofill_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        def add_row():
            table.insertRow(table.rowCount())

        def remove_selected():
            selected = sorted({idx.row() for idx in table.selectedIndexes()}, reverse=True)
            for row in selected:
                table.removeRow(row)

        def autofill_normatives():
            structure_widget = self.official_fields.get("structure_type")
            structure_type = "tower"
            if isinstance(structure_widget, QComboBox):
                structure_type = structure_widget.currentData() or "tower"
            docs = get_normatives_for_structure(structure_type)
            existing_codes = set()
            for r in range(table.rowCount()):
                item = table.item(r, 0)
                if item and item.text().strip():
                    existing_codes.add(item.text().strip())
            for doc in docs:
                if doc.code not in existing_codes:
                    row_idx = table.rowCount()
                    table.insertRow(row_idx)
                    table.setItem(row_idx, 0, QTableWidgetItem(doc.code))
                    table.setItem(row_idx, 1, QTableWidgetItem(doc.title))

        add_btn.clicked.connect(add_row)
        remove_btn.clicked.connect(remove_selected)
        autofill_btn.clicked.connect(autofill_normatives)
        table.cellChanged.connect(lambda *_: self._on_form_changed())

        table.group = group  # type: ignore[attr-defined]
        table.headers = ["Обозначение", "Наименование"]  # type: ignore[attr-defined]
        return table

    def _setup_completers(self):
        library = self.template_manager.load_reference_library()
        customer_names = [c.full_name for c in library.customers if c.full_name]
        contractor_names = [c.full_name for c in library.contractors if c.full_name]
        specialist_names = [s.full_name for s in library.specialists if s.full_name]

        org_data = self.settings_manager.load_default_organization()
        if org_data.get("full_name"):
            for lst in (customer_names, contractor_names):
                if org_data["full_name"] not in lst:
                    lst.insert(0, org_data["full_name"])

        for field_key, suggestions in [
            ("full_name", customer_names),
        ]:
            widget = self.customer_fields.get(field_key)
            if isinstance(widget, QLineEdit) and suggestions:
                completer = QCompleter(suggestions, widget)
                completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
                completer.setFilterMode(Qt.MatchFlag.MatchContains)
                widget.setCompleter(completer)

        for field_key, suggestions in [
            ("full_name", contractor_names),
        ]:
            widget = self.contractor_fields.get(field_key)
            if isinstance(widget, QLineEdit) and suggestions:
                completer = QCompleter(suggestions, widget)
                completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
                completer.setFilterMode(Qt.MatchFlag.MatchContains)
                widget.setCompleter(completer)

    def _fill_default_organization(self):
        org = self.settings_manager.load_default_organization()
        if not any(org.values()):
            QMessageBox.information(self, "Организация", "Организация по умолчанию не сохранена.\n"
                                    "Заполните данные исполнителя и нажмите «Запомнить орг.»")
            return
        contractor_mapping = {
            "full_name": "full_name",
            "director": "director",
            "legal_address": "legal_address",
            "postal_address": "postal_address",
            "phone": "phone",
            "email": "email",
            "accreditation_certificate": "accreditation_certificate",
            "sro_certificate": "sro_certificate",
        }
        for org_key, field_key in contractor_mapping.items():
            widget = self.contractor_fields.get(field_key)
            if isinstance(widget, QLineEdit) and org.get(org_key):
                if not widget.text().strip():
                    widget.setText(org[org_key])

        if org.get("approval_person"):
            widget = self.metadata_fields.get("approval_person")
            if isinstance(widget, QLineEdit) and not widget.text().strip():
                widget.setText(org["approval_person"])
        if org.get("approval_position"):
            widget = self.metadata_fields.get("approval_position")
            if isinstance(widget, QLineEdit) and not widget.text().strip():
                widget.setText(org["approval_position"])
        if org.get("city"):
            widget = self.metadata_fields.get("approval_city")
            if isinstance(widget, QLineEdit) and not widget.text().strip():
                widget.setText(org["city"])

    def _save_default_organization(self):
        org = {}
        for key in ("full_name", "director", "legal_address", "postal_address",
                     "phone", "email", "accreditation_certificate", "sro_certificate"):
            widget = self.contractor_fields.get(key)
            if isinstance(widget, QLineEdit):
                org[key] = widget.text().strip()

        widget = self.metadata_fields.get("approval_person")
        org["approval_person"] = widget.text().strip() if isinstance(widget, QLineEdit) else ""
        widget = self.metadata_fields.get("approval_position")
        org["approval_position"] = widget.text().strip() if isinstance(widget, QLineEdit) else ""
        widget = self.metadata_fields.get("approval_city")
        org["city"] = widget.text().strip() if isinstance(widget, QLineEdit) else ""

        self.settings_manager.save_default_organization(org)
        QMessageBox.information(self, "Сохранено", "Данные организации сохранены как значения по умолчанию.")

    def _validate_certificates(self):
        today = date.today()
        warnings = []
        if self.equipment_table:
            for row in range(self.equipment_table.rowCount()):
                date_item = self.equipment_table.item(row, 3)
                name_item = self.equipment_table.item(row, 0)
                if date_item and date_item.text().strip():
                    try:
                        parts = date_item.text().strip().split(".")
                        valid_date = date(int(parts[2]), int(parts[1]), int(parts[0]))
                        if valid_date < today:
                            name = name_item.text() if name_item else f"строка {row + 1}"
                            warnings.append(f"Прибор «{name}»: свидетельство истекло {date_item.text()}")
                    except (ValueError, IndexError):
                        pass
        if self.specialists_table:
            for row in range(self.specialists_table.rowCount()):
                expires_item = self.specialists_table.item(row, 2)
                name_item = self.specialists_table.item(row, 0)
                if expires_item and expires_item.text().strip():
                    for part in expires_item.text().split("\n"):
                        part = part.strip()
                        if ":" not in part:
                            continue
                        _, date_str = part.split(":", 1)
                        date_str = date_str.strip()
                        try:
                            dp = date_str.split(".")
                            cert_date = date(int(dp[2]), int(dp[1]), int(dp[0]))
                            if cert_date < today:
                                name = name_item.text() if name_item else f"строка {row + 1}"
                                warnings.append(f"Специалист «{name}»: аттестация истекла {date_str}")
                        except (ValueError, IndexError):
                            pass
        return warnings

    def _build_official_context_group(self):
        group = QGroupBox("Официальный контекст и реквизиты НТД")
        form = QFormLayout(group)

        structure_combo = QComboBox()
        structure_combo.addItem("Башня", "tower")
        structure_combo.addItem("Мачта", "mast")
        structure_combo.addItem("ОДН", "odn")
        self.official_fields["structure_type"] = structure_combo
        form.addRow("Тип опоры:", structure_combo)

        tower_catalog_combo = QComboBox()
        tower_catalog_combo.addItem("— выберите типовую башню —", "")
        from core.db.tower_catalog import get_tower_catalog
        for entry in get_tower_catalog():
            tower_catalog_combo.addItem(f"{entry.code} — {entry.name} ({entry.height_m:.0f} м)", entry.code)
        tower_catalog_combo.currentIndexChanged.connect(self._on_tower_catalog_selected)
        self.tower_catalog_combo = tower_catalog_combo
        form.addRow("Типовая башня:", tower_catalog_combo)

        def add_line(key: str, label: str):
            edit = QLineEdit()
            self.official_fields[key] = edit
            form.addRow(label, edit)

        add_line("base_station", "БС / базовая станция:")
        add_line("project_code", "Проект / шифр:")

        locality_row = QHBoxLayout()
        locality_edit = QLineEdit()
        self.official_fields["locality"] = locality_edit
        locality_row.addWidget(locality_edit, stretch=1)

        from core.db.climate_catalog import get_locality_names
        locality_completer = QCompleter(get_locality_names(), locality_edit)
        locality_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        locality_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        locality_edit.setCompleter(locality_completer)

        climate_fill_btn = QPushButton("Нагрузки")
        climate_fill_btn.setToolTip("Автозаполнить ветровые/снеговые/гололёдные нагрузки по населённому пункту")
        climate_fill_btn.clicked.connect(self._fill_loads_from_locality)
        locality_row.addWidget(climate_fill_btn)
        form.addRow("Населенный пункт:", locality_row)

        survey_date = QDateEdit()
        survey_date.setCalendarPopup(True)
        survey_date.setDisplayFormat("dd.MM.yyyy")
        survey_date.setDate(date.today())
        self.official_fields["survey_date"] = survey_date
        form.addRow("Дата обследования:", survey_date)

        add_line("performer", "Исполнитель:")
        add_line("reviewer", "Проверяющий:")
        add_line("instrument", "Прибор:")
        add_line("weather", "Погодные условия:")
        add_line("wind", "Ветер:")
        add_line("measurement_reason", "Причина измерений:")

        commissioning_year = QSpinBox()
        commissioning_year.setRange(1900, 2100)
        commissioning_year.setValue(date.today().year)
        self.official_fields["commissioning_year"] = commissioning_year
        form.addRow("Год ввода в эксплуатацию:", commissioning_year)

        decision_comment = QPlainTextEdit()
        decision_comment.setPlaceholderText("Комментарий/решение при превышениях по вертикальности")
        decision_comment.setFixedHeight(70)
        self.official_fields["decision_comment"] = decision_comment
        form.addRow("Решение/комментарий:", decision_comment)

        self.station_table = self._create_table_group("Стоянки и расстояния", ["Стоянка", "Расстояние, м", "Примечание"])
        form.addRow(self.station_table.group)
        return group

    def _fill_loads_from_locality(self):
        locality_widget = self.official_fields.get("locality")
        if not isinstance(locality_widget, QLineEdit):
            return
        locality = locality_widget.text().strip()
        if not locality:
            QMessageBox.information(self, "Нагрузки", "Укажите населённый пункт.")
            return
        from core.db.climate_catalog import autofill_loads_from_locality
        loads = autofill_loads_from_locality(locality)
        if loads is None:
            QMessageBox.information(self, "Нагрузки", f"Населённый пункт «{locality}» не найден в справочнике.\n"
                                    "Укажите нагрузки вручную или выберите пункт из подсказок.")
            return
        mapping = {
            "snow_load_kpa": "snow_load_kpa",
            "wind_pressure_kpa": "wind_pressure_kpa",
            "icing_mm": "icing_mm",
            "seismicity": "seismicity",
        }
        filled = []
        for load_key, field_key in mapping.items():
            value = loads.get(load_key)
            if value is not None:
                widget = self.load_fields.get(field_key)
                if widget is not None:
                    widget.setValue(value)
                    filled.append(f"{field_key}: {value}")
        if filled:
            QMessageBox.information(self, "Нагрузки заполнены",
                                    f"По населённому пункту «{locality}» заполнены:\n" + "\n".join(filled))

    def _on_tower_catalog_selected(self, index: int):
        if index <= 0 or not hasattr(self, "tower_catalog_combo"):
            return
        code = self.tower_catalog_combo.currentData()
        if not code:
            return
        from core.db.tower_catalog import find_tower_by_code
        entry = find_tower_by_code(code)
        if entry is None:
            return

        structure_widget = self.official_fields.get("structure_type")
        if isinstance(structure_widget, QComboBox):
            idx = structure_widget.findData(entry.structure_type)
            if idx >= 0:
                structure_widget.setCurrentIndex(idx)

        shape = "призма" if entry.base_size_m == entry.top_size_m else "усечённая пирамида"
        scheme = (f"{entry.faces}-гранная {shape}, высота {entry.height_m:.0f} м, "
                  f"{entry.sections} секций, основание {entry.base_size_m:.1f} м, верх {entry.top_size_m:.1f} м")

        edit = self.structure_fields.get("structural_scheme")
        if edit and isinstance(edit, QPlainTextEdit) and not edit.toPlainText().strip():
            edit.setPlainText(scheme)

        edit = self.structure_fields.get("purpose")
        if edit and isinstance(edit, QPlainTextEdit) and not edit.toPlainText().strip():
            edit.setPlainText(entry.description)

        if entry.profiles:
            metal_text = "; ".join(f"{k}: {v}" for k, v in entry.profiles.items())
            edit = self.structure_fields.get("metal_structure")
            if edit and isinstance(edit, QPlainTextEdit) and not edit.toPlainText().strip():
                edit.setPlainText(metal_text)

        if entry.normative_codes and self.normatives_table:
            existing_codes = set()
            for r in range(self.normatives_table.rowCount()):
                item = self.normatives_table.item(r, 0)
                if item and item.text().strip():
                    existing_codes.add(item.text().strip())
            from core.normatives import NORMATIVE_REFERENCES
            code_to_title = {doc.code: doc.title for doc in NORMATIVE_REFERENCES}
            for norm_code in entry.normative_codes:
                if norm_code not in existing_codes:
                    row_idx = self.normatives_table.rowCount()
                    self.normatives_table.insertRow(row_idx)
                    self.normatives_table.setItem(row_idx, 0, QTableWidgetItem(norm_code))
                    self.normatives_table.setItem(row_idx, 1, QTableWidgetItem(code_to_title.get(norm_code, "")))

    def _populate_section_list(self):
        if self.section_list is None:
            return
        self.section_list.clear()
        labels = [
            ("title", "Реквизиты и титул"),
            ("participants", "Объект и участники"),
            ("normatives", "Нормативная часть"),
            ("measurements", "Измерения и протоколы"),
            ("results", "Расчеты и выводы"),
            ("appendices", "Приложения и выпуск"),
        ]
        for key, title in labels:
            item = QListWidgetItem(title)
            item.setData(Qt.ItemDataRole.UserRole, key)
            self.section_list.addItem(item)
        if self.section_list.count():
            self.section_list.setCurrentRow(0)

    def _on_section_selected(self, current: QListWidgetItem | None, previous: QListWidgetItem | None = None):
        if current is None:
            return
        key = current.data(Qt.ItemDataRole.UserRole)
        self._current_section_key = key or "title"
        anchor = self.section_anchors.get(self._current_section_key)
        if anchor is not None and self.form_scroll_area is not None:
            self.form_scroll_area.ensureWidgetVisible(anchor, 0, 24)
        self._refresh_preview()

    def _connect_form_change_tracking(self):
        for widget in self.findChildren((QLineEdit, QPlainTextEdit, QDateEdit, QSpinBox, QDoubleSpinBox, QComboBox)):
            if widget is self.template_combo or widget is self.preview_mode_combo:
                continue
            if isinstance(widget, QLineEdit):
                widget.textChanged.connect(self._on_form_changed)
            elif isinstance(widget, QPlainTextEdit):
                widget.textChanged.connect(self._on_form_changed)
            elif isinstance(widget, QDateEdit):
                widget.dateChanged.connect(self._on_form_changed)
            elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                widget.valueChanged.connect(self._on_form_changed)
            elif isinstance(widget, QComboBox):
                widget.currentIndexChanged.connect(self._on_form_changed)

    def _on_form_changed(self, *args):
        if self._loading_state:
            return
        provenance_key = f"{self._current_section_key}:state"
        self.field_provenance[provenance_key] = "manual"
        if self._current_section_key not in self.dirty_sections:
            self.dirty_sections.append(self._current_section_key)
        self._sync_identity_projection()
        self.preview_timer.start()

    def _refresh_preview(self):
        if self.preview_browser is None:
            return
        try:
            draft = self.collect_draft_state(validate_required=False)
            model = self.builder.assemble_render_model(
                draft,
                self.processed_data or {},
                self.raw_data,
                self.import_context,
                self.import_diagnostics,
            )
            preview_mode = "document"
            if self.preview_mode_combo is not None:
                preview_mode = str(self.preview_mode_combo.currentData() or "document")
            html = self.builder.render_preview(model, preview_mode, self._current_section_key)
            self.preview_browser.setHtml(html)
            self._update_section_statuses(model)
        except Exception as exc:
            self.preview_browser.setHtml(f"<html><body><p>Предпросмотр недоступен: {escape(str(exc))}</p></body></html>")

    def _update_section_statuses(self, model):
        if self.section_list is None:
            return
        status_map = {section.key: section.status for section in model.sections}
        status_text = []
        for row in range(self.section_list.count()):
            item = self.section_list.item(row)
            key = item.data(Qt.ItemDataRole.UserRole)
            base = item.text().split(" [")[0]
            label = self.builder._status_label(status_map.get(key, "not_started"))
            item.setText(f"{base} [{label}]")
            status_text.append(f"{base}: {label}")
        if self.section_status_label is not None:
            self.section_status_label.setText("\n".join(status_text[:6]))

    def set_source_data(self, raw_data, processed_data, import_context: Dict[str, Any] | None = None,
                        import_diagnostics: Dict[str, Any] | None = None, project_path: str | None = None,
                        tower_blueprint=None, angular_measurements: Dict[str, Any] | None = None):
        self.raw_data = raw_data
        self.processed_data = processed_data
        self.import_context = import_context or {}
        self.import_diagnostics = import_diagnostics or {}
        self.project_path = project_path
        self.tower_blueprint = tower_blueprint
        self.angular_measurements = angular_measurements or {}
        if self.shared_report_info:
            self.apply_shared_report_info(self.shared_report_info, force=False)
        self._refresh_preview()

    def apply_shared_report_info(self, report_info: Dict[str, Any], force: bool = False):
        if not report_info:
            return

        self.shared_report_info = dict(report_info)
        self._loading_state = True
        try:
            project_name = str(report_info.get("project_name", "") or "").strip()
            location = str(report_info.get("location", "") or "").strip()
            organization = str(report_info.get("organization", "") or "").strip()
            executor = str(report_info.get("executor", "") or "").strip()
            position = str(report_info.get("position", "") or "").strip()
            notes = str(report_info.get("notes", "") or "").strip()
            survey_date = self._parse_report_info_date(report_info.get("survey_date"))

            self._set_line_edit_value(self.metadata_fields.get("project_name"), project_name, force=force)
            self._set_line_edit_value(self.metadata_fields.get("location"), location, force=force)
            self._set_line_edit_value(self.metadata_fields.get("customer_name"), organization, force=force)
            self._set_line_edit_value(self.metadata_fields.get("operator_name"), organization, force=force)
            self._set_line_edit_value(self.customer_fields.get("full_name"), organization, force=force)
            self._set_line_edit_value(self.contractor_fields.get("full_name"), organization, force=force)
            self._set_line_edit_value(self.metadata_fields.get("approval_position"), position, force=force)
            self._set_line_edit_value(self.official_fields.get("performer"), executor, force=force)
            self._set_line_edit_value(self.official_fields.get("measurement_reason"), notes, force=force)

            self._set_line_edit_value(self.title_fields.get("name"), project_name, force=force)
            self._set_line_edit_value(self.title_fields.get("operator"), organization, force=force)
            self._set_line_edit_value(self.title_fields.get("location"), location, force=force)

            self._set_date_edit_value(self.official_fields.get("survey_date"), survey_date, force=force)
            self._set_date_edit_value(self.metadata_fields.get("start_date"), survey_date, force=force)
            self._set_date_edit_value(self.metadata_fields.get("end_date"), survey_date, force=force)
        finally:
            self._loading_state = False

        self._sync_identity_projection()
        self.field_provenance["title:state"] = "report"
        self.field_provenance["participants:state"] = "report"
        self._refresh_preview()

    def load_state(self, state: Dict[str, Any]):
        if not state:
            return
        try:
            draft = FullReportDraftState.from_dict(state)
            self._loading_state = True
            self.clear_form()
            self.populate_form(draft.form_data)
            self._populate_official_context(draft.official_context)
            if self.preview_mode_combo is not None:
                idx = max(self.preview_mode_combo.findData(draft.preview_settings.mode), 0)
                self.preview_mode_combo.setCurrentIndex(idx)
            self.field_provenance = dict(draft.field_provenance)
            self.dirty_sections = list(draft.dirty_sections)
            self._last_loaded_state = draft.to_dict()
        except Exception as exc:
            QMessageBox.warning(self, "Ошибка восстановления", f"Не удалось восстановить вкладку полного отчета:\n{exc}")
        finally:
            self._loading_state = False
            self._refresh_preview()

    def collect_draft_state(self, validate_required: bool = False, sync_assets: bool = True) -> FullReportDraftState:
        form_data = self.collect_form_data(validate_required=validate_required)
        official_context = self._collect_official_context()
        attachments_manifest = self._build_attachment_manifest(form_data, sync_assets=sync_assets)
        draft = FullReportDraftState(
            form_data=form_data,
            selected_template=self.template_combo.currentText() if self.template_combo and self.template_combo.isEnabled() else "",
            official_context=official_context,
            field_provenance=dict(self.field_provenance),
            attachments_manifest=attachments_manifest,
            dirty_sections=list(self.dirty_sections),
        )
        if self.preview_mode_combo is not None:
            draft.preview_settings.mode = str(self.preview_mode_combo.currentData() or "document")
        return draft

    def _collect_official_context(self) -> OfficialReportContext:
        structure_widget = self.official_fields["structure_type"]
        structure_type = structure_widget.currentData() if isinstance(structure_widget, QComboBox) else "tower"
        commissioning_widget = self.official_fields["commissioning_year"]
        decision_widget = self.official_fields["decision_comment"]
        return OfficialReportContext(
            structure_type=str(structure_type or "tower"),
            base_station=self._text_value(self.official_fields["base_station"]),
            project_code=self._text_value(self.official_fields["project_code"]),
            locality=self._text_value(self.official_fields["locality"]),
            survey_date=self._date_value(self.official_fields["survey_date"]),
            performer=self._text_value(self.official_fields["performer"]),
            reviewer=self._text_value(self.official_fields["reviewer"]),
            instrument=self._text_value(self.official_fields["instrument"]),
            weather=self._text_value(self.official_fields["weather"]),
            wind=self._text_value(self.official_fields["wind"]),
            measurement_reason=self._text_value(self.official_fields["measurement_reason"]),
            commissioning_year=int(commissioning_widget.value()) if isinstance(commissioning_widget, QSpinBox) else None,
            decision_comment=decision_widget.toPlainText().strip() if isinstance(decision_widget, QPlainTextEdit) else "",
            stations=self._table_to_stations(self.station_table),
        )

    def _populate_official_context(self, context: OfficialReportContext):
        structure_widget = self.official_fields.get("structure_type")
        if isinstance(structure_widget, QComboBox):
            idx = max(structure_widget.findData(context.structure_type), 0)
            structure_widget.setCurrentIndex(idx)
        for key in ["base_station", "project_code", "locality", "performer", "reviewer", "instrument", "weather", "wind", "measurement_reason"]:
            widget = self.official_fields.get(key)
            if isinstance(widget, QLineEdit):
                widget.setText(getattr(context, key))
        survey_widget = self.official_fields.get("survey_date")
        if isinstance(survey_widget, QDateEdit):
            survey_widget.setDate(context.survey_date)
        commissioning_widget = self.official_fields.get("commissioning_year")
        if isinstance(commissioning_widget, QSpinBox) and context.commissioning_year is not None:
            commissioning_widget.setValue(context.commissioning_year)
        decision_widget = self.official_fields.get("decision_comment")
        if isinstance(decision_widget, QPlainTextEdit):
            decision_widget.setPlainText(context.decision_comment)
        if self.station_table is not None:
            self.station_table.setRowCount(0)
            for station in context.stations:
                row = self.station_table.rowCount()
                self.station_table.insertRow(row)
                self.station_table.setItem(row, 0, QTableWidgetItem(station.name))
                self.station_table.setItem(row, 1, QTableWidgetItem("" if station.distance_m is None else str(station.distance_m)))
                self.station_table.setItem(row, 2, QTableWidgetItem(station.note))

    def _table_to_stations(self, table) -> List[SurveyStationEntry]:
        if not table:
            return []
        stations = []
        for row in self._iter_rows(table):
            distance = self._safe_float(row[1])
            stations.append(SurveyStationEntry(name=row[0], distance_m=distance, note=row[2]))
        return stations

    def _import_from_project(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Импорт данных из проекта", "",
            "Проекты GeoVertical (*.gvproj);;Все файлы (*)",
        )
        if not file_path:
            return
        try:
            import json
            with open(file_path, encoding="utf-8") as f:
                project_data = json.load(f)
            full_report_state = project_data.get("full_report_state", {})
            if not full_report_state:
                QMessageBox.information(self, "Импорт", "В выбранном проекте нет данных полного отчёта.")
                return

            from core.full_report_models import FullReportDraftState
            draft = FullReportDraftState.from_dict(full_report_state)
            source_data = draft.form_data

            import_options = [
                "Заказчик и исполнитель",
                "Специалисты",
                "Оборудование",
                "Всё вышеперечисленное",
            ]
            choice, ok = QInputDialog.getItem(self, "Что импортировать?",
                                              f"Импорт из: {Path(file_path).stem}", import_options, 3, False)
            if not ok:
                return

            self._loading_state = True
            if choice in (import_options[0], import_options[3]):
                for key, edit in self.customer_fields.items():
                    val = getattr(source_data.customer, key, "")
                    if isinstance(edit, QLineEdit) and val and not edit.text().strip():
                        edit.setText(val)
                for key, edit in self.contractor_fields.items():
                    val = getattr(source_data.contractor, key, "")
                    if isinstance(edit, QLineEdit) and val and not edit.text().strip():
                        edit.setText(val)

            if choice in (import_options[1], import_options[3]):
                if source_data.specialists:
                    self._append_specialists_from_library(source_data.specialists)

            if choice in (import_options[2], import_options[3]):
                if source_data.equipment:
                    self._append_equipment_from_library(source_data.equipment)

            self._loading_state = False
            self._refresh_preview()
            QMessageBox.information(self, "Импорт", f"Данные импортированы из проекта «{Path(file_path).stem}».")
        except json.JSONDecodeError:
            try:
                import pickle
                with open(file_path, "rb") as f:
                    project_data = pickle.load(f)
                full_report_state = project_data.get("full_report_state", {})
                if full_report_state:
                    from core.full_report_models import FullReportDraftState
                    draft = FullReportDraftState.from_dict(full_report_state)
                    source_data = draft.form_data
                    self._loading_state = True
                    for key, edit in self.customer_fields.items():
                        val = getattr(source_data.customer, key, "")
                        if isinstance(edit, QLineEdit) and val and not edit.text().strip():
                            edit.setText(val)
                    for key, edit in self.contractor_fields.items():
                        val = getattr(source_data.contractor, key, "")
                        if isinstance(edit, QLineEdit) and val and not edit.text().strip():
                            edit.setText(val)
                    if source_data.specialists:
                        self._append_specialists_from_library(source_data.specialists)
                    if source_data.equipment:
                        self._append_equipment_from_library(source_data.equipment)
                    self._loading_state = False
                    self._refresh_preview()
                    QMessageBox.information(self, "Импорт", f"Данные импортированы из проекта «{Path(file_path).stem}».")
                else:
                    QMessageBox.information(self, "Импорт", "В выбранном проекте нет данных полного отчёта.")
            except Exception as exc:
                QMessageBox.critical(self, "Ошибка", f"Не удалось импортировать данные:\n{exc}")
        except Exception as exc:
            self._loading_state = False
            QMessageBox.critical(self, "Ошибка", f"Не удалось импортировать данные:\n{exc}")

    def _save_draft(self):
        draft = self.collect_draft_state(validate_required=False)
        self._last_loaded_state = draft.to_dict()
        self.template_manager.merge_into_reference_library(draft)
        window = self.window()
        if hasattr(window, "save_project"):
            try:
                window.save_project()
                QMessageBox.information(self, "Черновик", "Черновик полного отчета сохранен в проекте.")
                return
            except Exception:
                pass
        QMessageBox.information(self, "Черновик", "Состояние полного отчета зафиксировано и будет сохранено при следующем сохранении проекта.")

    def _restore_draft(self):
        if not self._last_loaded_state:
            QMessageBox.information(self, "Восстановление", "Нет сохраненного состояния для восстановления.")
            return
        self.load_state(self._last_loaded_state)

    def _add_from_library(self):
        library = self.template_manager.load_reference_library()
        current = self._current_section_key
        if current == "participants":
            options = []
            if library.customers:
                options.append("Заказчик")
            if library.contractors:
                options.append("Исполнитель")
            if library.specialists:
                options.append("Специалисты")
            if library.equipment:
                options.append("Оборудование")
            if not options:
                QMessageBox.information(self, "Справочник", "В справочнике пока нет записей для этого раздела.")
                return
            choice, ok = QInputDialog.getItem(self, "Справочник", "Что добавить?", options, 0, False)
            if not ok:
                return
            self._loading_state = True
            if choice == "Заказчик" and library.customers:
                customer = library.customers[0]
                for key, edit in self.customer_fields.items():
                    edit.setText(getattr(customer, key, ""))
            elif choice == "Исполнитель" and library.contractors:
                contractor = library.contractors[0]
                for key, edit in self.contractor_fields.items():
                    edit.setText(getattr(contractor, key, ""))
            elif choice == "Специалисты" and library.specialists:
                self._append_specialists_from_library(library.specialists)
            elif choice == "Оборудование" and library.equipment:
                self._append_equipment_from_library(library.equipment)
            self._loading_state = False
        elif current == "appendices" and library.appendices:
            self._loading_state = True
            for appendix in library.appendices:
                row = self.appendices_table.rowCount()
                self.appendices_table.insertRow(row)
                self.appendices_table.setItem(row, 0, QTableWidgetItem(appendix.title))
                self.appendices_table.setItem(row, 1, QTableWidgetItem(appendix.description or ""))
                self.appendices_table.setItem(row, 2, QTableWidgetItem("; ".join(appendix.files)))
            self._loading_state = False
        elif current == "results" and library.recommendations:
            self._loading_state = True
            for item in library.recommendations:
                row = self.recommendations_table.rowCount()
                self.recommendations_table.insertRow(row)
                self.recommendations_table.setItem(row, 0, QTableWidgetItem(item.text))
            self._loading_state = False
        else:
            QMessageBox.information(self, "Справочник", "Для текущего раздела нет подходящих записей в справочнике.")
            return
        self.field_provenance[f"{current}:state"] = "library"
        self._refresh_preview()

    def _append_specialists_from_library(self, specialists: List[Specialist]):
        for specialist in specialists:
            row = self.specialists_table.rowCount()
            self.specialists_table.insertRow(row)
            self.specialists_table.setItem(row, 0, QTableWidgetItem(specialist.full_name))
            self.specialists_table.setItem(row, 1, QTableWidgetItem("\n".join(f"{k}:{v}" for k, v in specialist.certifications.items())))
            self.specialists_table.setItem(row, 2, QTableWidgetItem("\n".join(f"{k}:{v:%d.%m.%Y}" for k, v in specialist.expires_at.items())))

    def _append_equipment_from_library(self, equipment: List[EquipmentEntry]):
        for item in equipment:
            row = self.equipment_table.rowCount()
            self.equipment_table.insertRow(row)
            self.equipment_table.setItem(row, 0, QTableWidgetItem(item.name))
            self.equipment_table.setItem(row, 1, QTableWidgetItem(item.serial_number))
            self.equipment_table.setItem(row, 2, QTableWidgetItem(item.certificate))
            self.equipment_table.setItem(row, 3, QTableWidgetItem(item.valid_until.strftime("%d.%m.%Y")))

    def _build_attachment_manifest(self, form_data: FullReportData, sync_assets: bool = True) -> List[AttachmentManifestEntry]:
        manifest: List[AttachmentManifestEntry] = []
        asset_dir = self._resolve_assets_dir()
        for appendix in form_data.appendices:
            normalized_files = []
            for raw_path in appendix.files:
                source = Path(raw_path)
                relative_path = raw_path
                if sync_assets and source.is_absolute() and source.exists():
                    asset_dir.mkdir(parents=True, exist_ok=True)
                    target = asset_dir / source.name
                    if source != target:
                        try:
                            shutil.copy2(source, target)
                        except OSError:
                            target = source
                    relative_path = self._normalize_stored_path(target)
                normalized_files.append(relative_path)
                manifest.append(
                    AttachmentManifestEntry(
                        title=appendix.title or source.name,
                        relative_path=relative_path,
                        source_path=str(source),
                        description=appendix.description or "",
                        include_in_release=True,
                    )
                )
            appendix.files = normalized_files
        return manifest

    def _resolve_assets_dir(self) -> Path:
        if self.project_path:
            project_path = Path(self.project_path)
            return project_path.parent / f"{project_path.stem}_assets" / "full_report"
        return Path(self.template_manager.storage_dir).parent / "draft_full_report_assets"

    def _normalize_stored_path(self, path: Path) -> str:
        if self.project_path:
            project_dir = Path(self.project_path).parent
            try:
                return str(path.relative_to(project_dir))
            except ValueError:
                return str(path)
        return str(path)

    def collect_form_data(self, validate_required: bool = True) -> FullReportData:
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

        if validate_required:
            if not metadata.project_name:
                raise ValueError("Укажите наименование объекта в титульном блоке.")
            if not metadata.report_number:
                raise ValueError("Укажите номер полного отчета.")

        customer = CustomerInfo(**{k: self.customer_fields[k].text() for k in self.customer_fields})
        contractor = ContractorInfo(**{k: self.contractor_fields[k].text() for k in self.contractor_fields})

        title_name = self._first_text(metadata.project_name, self.title_fields["name"].text().strip())
        title_inventory = self._first_text(metadata.inventory_number, self.title_fields["inventory_number"].text().strip())
        title_operator = self._first_text(
            self.title_fields["operator"].text().strip(),
            metadata.customer_name,
            customer.full_name,
            metadata.operator_name,
            contractor.full_name,
        )
        title_location = self._first_text(
            metadata.location,
            self.title_fields["location"].text().strip(),
            customer.actual_address,
            contractor.postal_address,
            contractor.legal_address,
        )
        title_city = self._first_text(self.title_fields["city"].text().strip(), metadata.approval_city)
        title_year = int(self.title_fields["year"].value())
        title_object = None
        if any([title_name, title_inventory, title_operator, title_location, title_city]):
            title_object = TitleObjectInfo(
                name=title_name,
                inventory_number=title_inventory,
                operator=title_operator,
                location=title_location,
                city=title_city,
                year=title_year,
            )
        object_list = self._table_to_objects(self.object_table)
        if not object_list and any([title_name, title_inventory, title_location, title_operator]):
            commissioning_widget = self.official_fields.get("commissioning_year")
            commissioning_year = int(commissioning_widget.value()) if isinstance(commissioning_widget, QSpinBox) else None
            primary_note = (
                f"\u042d\u043a\u0441\u043f\u043b\u0443\u0430\u0442\u0438\u0440\u0443\u044e\u0449\u0430\u044f \u043e\u0440\u0433\u0430\u043d\u0438\u0437\u0430\u0446\u0438\u044f: {title_operator}"
                if title_operator
                else None
            )
            object_list = [
                InspectedObject(
                    name=title_name,
                    inventory_number=title_inventory or None,
                    commissioning_year=commissioning_year,
                    location=title_location or None,
                    notes=primary_note,
                )
            ]

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
            object_list=object_list,
            loads=loads,
            soils=self._table_to_soils(self.soils_table),
            climate=climate,
            structure=structure,
            objects=[],
            documents_review=self._table_to_document_reviews(self.documents_review_table),
            normative_list=self._table_to_normative_list(self.normatives_table),
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

    def _load_template(self):
        if not self.template_combo or not self.template_combo.isEnabled():
            QMessageBox.information(self, "Шаблоны", "Нет доступных шаблонов.")
            return
        name = self.template_combo.currentText()
        if not name:
            return

        load_options = ["Весь шаблон", "Только организации/специалисты", "Только нагрузки и климат", "Только описание конструкций"]
        choice, ok = QInputDialog.getItem(self, "Загрузка шаблона", f"Что загрузить из «{name}»?", load_options, 0, False)
        if not ok:
            return

        try:
            template = self.template_manager.load_full_template(name)
            self._loading_state = True
            data = template.form_data

            if choice == load_options[0]:
                self.populate_form(data)
                self._populate_official_context(template.official_context_defaults)
                self.field_provenance = {f"{key}:state": "template" for key in self.section_anchors.keys()}
            elif choice == load_options[1]:
                for key, edit in self.customer_fields.items():
                    val = getattr(data.customer, key, "")
                    if isinstance(edit, QLineEdit) and val:
                        edit.setText(val)
                for key, edit in self.contractor_fields.items():
                    val = getattr(data.contractor, key, "")
                    if isinstance(edit, QLineEdit) and val:
                        edit.setText(val)
                if data.specialists and self.specialists_table:
                    self.populate_form(data, preserve_manual=False)
            elif choice == load_options[2]:
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
            elif choice == load_options[3]:
                if data.structure:
                    for key, edit in self.structure_fields.items():
                        val = getattr(data.structure, key, "") or ""
                        if val:
                            edit.setPlainText(val)

            self._loading_state = False
            self._refresh_preview()
        except Exception as exc:
            self._loading_state = False
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить шаблон:\n{exc}")

    def _save_template(self):
        try:
            draft = self.collect_draft_state(validate_required=False)
        except ValueError as exc:
            QMessageBox.warning(self, "Недостаточно данных", str(exc))
            return
        name, ok = QInputDialog.getText(self, "Имя шаблона", "Введите название шаблона:")
        if not ok or not name.strip():
            return
        try:
            template = self.template_manager.create_template_from_report(
                name.strip(),
                draft.form_data,
                official_context_defaults=draft.official_context,
                include_measurements=False,
                include_attachments=False,
            )
            self.template_manager.save_full_template(template)
            self.template_manager.merge_into_reference_library(draft)
            self._refresh_templates()
            QMessageBox.information(self, "Готово", f"Шаблон «{name}» сохранен.")
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить шаблон:\n{exc}")

    def _generate_report(self):
        cert_warnings = self._validate_certificates()
        if cert_warnings:
            text = "Обнаружены истёкшие сертификаты/аттестации:\n\n" + "\n".join(cert_warnings) + "\n\nПродолжить формирование отчёта?"
            reply = QMessageBox.question(self, "Предупреждение", text, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply != QMessageBox.StandardButton.Yes:
                return

        try:
            draft = self.collect_draft_state(validate_required=False)
            model = self.builder.assemble_render_model(
                draft,
                self.processed_data or {},
                self.raw_data,
                self.import_context,
                self.import_diagnostics,
            )
        except Exception as exc:
            QMessageBox.warning(self, "Недостаточно данных", str(exc))
            return

        if model.errors:
            QMessageBox.warning(self, "Экспорт заблокирован", "\n".join(model.errors))
            return

        documents_dir = Path(self.template_manager.storage_dir).parent
        report_number = self._sanitize_filename(draft.form_data.metadata.report_number) or "full_report"
        default_path = documents_dir / f"{report_number}.docx"
        file_path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Сохранить полный отчет",
            str(default_path),
            "Word файлы (*.docx);;PDF файлы (*.pdf)",
        )
        if not file_path:
            return

        want_pdf = file_path.lower().endswith(".pdf") or "pdf" in selected_filter.lower()
        docx_path = file_path if not want_pdf else file_path.rsplit(".", 1)[0] + ".docx"

        try:
            draft.release_manifest = ReleaseManifest(
                output_path=file_path,
                exported_at=datetime.now(),
                draft_hash=draft.draft_hash(),
                template_name=draft.selected_template,
                included_files=[item.relative_path for item in draft.attachments_manifest if item.include_in_release],
            )
            model = self.builder.assemble_render_model(
                draft,
                self.processed_data or {},
                self.raw_data,
                self.import_context,
                self.import_diagnostics,
            )
            self.builder.render_docx(model, docx_path)

            if want_pdf:
                try:
                    from docx2pdf import convert
                    convert(docx_path, file_path)
                except ImportError:
                    QMessageBox.warning(self, "PDF", "Для экспорта в PDF установите модуль docx2pdf:\n"
                                        "pip install docx2pdf")
                except Exception as pdf_exc:
                    QMessageBox.warning(self, "PDF", f"DOCX сохранён, но конвертация в PDF не удалась:\n{pdf_exc}")

            self._last_loaded_state = draft.to_dict()
            self._refresh_preview()
            QMessageBox.information(self, "Готово", f"Полный отчет сохранен:\n{file_path}")
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка", f"Не удалось сформировать отчет:\n{exc}")

    def clear_form(self):
        self._loading_state = True
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
        for widget in self.official_fields.values():
            if isinstance(widget, QLineEdit):
                widget.clear()
            elif isinstance(widget, QDateEdit):
                widget.setDate(date.today())
            elif isinstance(widget, QComboBox):
                widget.setCurrentIndex(0)
            elif isinstance(widget, QSpinBox):
                widget.setValue(date.today().year)
            elif isinstance(widget, QPlainTextEdit):
                widget.clear()
        for spin in self.load_fields.values():
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
            self.normatives_table,
            self.station_table,
        ]:
            if table:
                table.setRowCount(0)
        self.field_provenance = {}
        self.dirty_sections = []
        self._loading_state = False
        self._refresh_preview()

    def _build_template_toolbar(self):
        layout = QHBoxLayout()
        layout.addWidget(QLabel("Шаблон:"))
        self.template_combo = QComboBox()
        layout.addWidget(self.template_combo, stretch=1)

        refresh_btn = QPushButton("Обновить")
        refresh_btn.clicked.connect(self._refresh_templates)
        layout.addWidget(refresh_btn)

        load_btn = QPushButton("Загрузить")
        load_btn.clicked.connect(self._load_template)
        layout.addWidget(load_btn)

        save_tpl_btn = QPushButton("Сохранить как шаблон")
        save_tpl_btn.clicked.connect(self._save_template)
        layout.addWidget(save_tpl_btn)

        save_draft_btn = QPushButton("Сохранить черновик")
        save_draft_btn.clicked.connect(self._save_draft)
        layout.addWidget(save_draft_btn)

        restore_btn = QPushButton("Восстановить")
        restore_btn.clicked.connect(self._restore_draft)
        layout.addWidget(restore_btn)

        sync_btn = QPushButton("Синхронизировать реквизиты")
        sync_btn.setToolTip("Подтянуть дублирующиеся реквизиты и стоянки из уже введённых данных проекта")
        sync_btn.clicked.connect(lambda: self._sync_identity_fields(force=False, replace_stations=True))
        layout.addWidget(sync_btn)

        autofill_btn = QPushButton("Автозаполнить раздел")
        autofill_btn.clicked.connect(self._auto_fill_current_section)
        layout.addWidget(autofill_btn)

        library_btn = QPushButton("Добавить из справочника")
        library_btn.clicked.connect(self._add_from_library)
        layout.addWidget(library_btn)

        org_fill_btn = QPushButton("Орг. по умолчанию")
        org_fill_btn.setToolTip("Заполнить данные исполнителя из настроек (организация по умолчанию)")
        org_fill_btn.clicked.connect(self._fill_default_organization)
        layout.addWidget(org_fill_btn)

        org_save_btn = QPushButton("Запомнить орг.")
        org_save_btn.setToolTip("Сохранить текущие данные исполнителя как организацию по умолчанию")
        org_save_btn.clicked.connect(self._save_default_organization)
        layout.addWidget(org_save_btn)

        advanced_btn = QPushButton("Расш.")
        advanced_btn.setToolTip("Расширенный редактор шаблонов")
        advanced_btn.clicked.connect(self._open_template_editor)
        layout.addWidget(advanced_btn)
        return layout

    def _auto_fill_current_section(self):
        section_requires_results = self._current_section_key not in {"title", "participants"}
        if section_requires_results and not self.processed_data:
            QMessageBox.warning(self, "Нет данных", "Сначала выполните расчёт и загрузите проектные данные.")
            return

        try:
            draft = self.collect_draft_state(validate_required=False, sync_assets=False)
        except Exception as exc:
            QMessageBox.warning(self, "Недостаточно данных", str(exc))
            return

        assembler = self._make_report_assembler(draft.form_data.reference_profiles)
        enriched = assembler.fill_measurement_sections(draft.form_data)
        official = assembler.build_official_context(enriched, draft.official_context)

        self._loading_state = True
        if section_requires_results:
            self.populate_form(enriched, preserve_manual=True)
        self._apply_identity_to_form(enriched, official, force=False, replace_stations=True)
        self._loading_state = False

        target_key = self._current_section_key if self._current_section_key in {"title", "participants"} else "measurements"
        self.field_provenance[f"{target_key}:state"] = "auto"
        self._refresh_preview()

    def serialize_state(self) -> Dict[str, Any]:
        try:
            draft = self.collect_draft_state(validate_required=False, sync_assets=False)
            assembler = self._make_report_assembler(draft.form_data.reference_profiles)
            draft.form_data = assembler.fill_measurement_sections(draft.form_data)
            draft.official_context = assembler.build_official_context(draft.form_data, draft.official_context)
            draft.attachments_manifest = self._build_attachment_manifest(draft.form_data, sync_assets=True)
            draft.last_saved_at = datetime.now()
            self._last_loaded_state = draft.to_dict()
            return draft.to_dict()
        except Exception:
            return {}

    def _make_report_assembler(self, reference_profiles=None) -> ReportDataAssembler:
        return ReportDataAssembler(
            self.processed_data or {},
            self.raw_data,
            reference_profiles or [],
            import_context=self.import_context,
            import_diagnostics=self.import_diagnostics,
            tower_blueprint=self.tower_blueprint,
            angular_measurements=self.angular_measurements,
        )

    def _sync_identity_fields(self, force: bool = False, replace_stations: bool = True):
        try:
            draft = self.collect_draft_state(validate_required=False, sync_assets=False)
        except Exception as exc:
            QMessageBox.warning(self, "Недостаточно данных", str(exc))
            return

        assembler = self._make_report_assembler(draft.form_data.reference_profiles)
        normalized = assembler.fill_measurement_sections(draft.form_data)
        official = assembler.build_official_context(normalized, draft.official_context)

        self._loading_state = True
        self._apply_identity_to_form(normalized, official, force=force, replace_stations=replace_stations)
        self._loading_state = False
        self.field_provenance[f"{self._current_section_key}:state"] = "auto"
        self._refresh_preview()

    def _apply_identity_to_form(
        self,
        data: FullReportData,
        official: OfficialReportContext,
        force: bool = False,
        replace_stations: bool = True,
    ):
        customer_name = self._first_text(data.customer.full_name, data.metadata.customer_name)
        contractor_name = self._first_text(data.contractor.full_name, data.metadata.operator_name)
        title = data.title_object

        self._set_line_edit_value(self.metadata_fields.get("project_name"), data.metadata.project_name, force=force)
        self._set_line_edit_value(self.metadata_fields.get("inventory_number"), data.metadata.inventory_number, force=force)
        self._set_line_edit_value(self.metadata_fields.get("location"), data.metadata.location, force=force)
        self._set_line_edit_value(self.metadata_fields.get("customer_name"), customer_name, force=force)
        self._set_line_edit_value(self.metadata_fields.get("operator_name"), contractor_name, force=force)
        self._set_line_edit_value(self.customer_fields.get("full_name"), customer_name, force=force)
        self._set_line_edit_value(self.contractor_fields.get("full_name"), contractor_name, force=force)

        if title is not None:
            self._set_line_edit_value(self.title_fields.get("name"), title.name, force=force)
            self._set_line_edit_value(self.title_fields.get("inventory_number"), title.inventory_number, force=force)
            self._set_line_edit_value(self.title_fields.get("operator"), title.operator, force=force)
            self._set_line_edit_value(self.title_fields.get("location"), title.location, force=force)
            self._set_line_edit_value(self.title_fields.get("city"), title.city, force=force)
            year_widget = self.title_fields.get("year")
            if isinstance(year_widget, QSpinBox) and (force or year_widget.value() <= 1900):
                year_widget.setValue(title.year)

        self._set_line_edit_value(self.official_fields.get("base_station"), official.base_station, force=force)
        self._set_line_edit_value(self.official_fields.get("project_code"), official.project_code, force=force)
        self._set_line_edit_value(self.official_fields.get("locality"), official.locality, force=force)
        self._set_line_edit_value(self.official_fields.get("performer"), official.performer, force=force)
        self._set_line_edit_value(self.official_fields.get("instrument"), official.instrument, force=force)

        survey_widget = self.official_fields.get("survey_date")
        if isinstance(survey_widget, QDateEdit):
            current_date = survey_widget.date().toPyDate()
            if force or current_date == date.today():
                survey_widget.setDate(official.survey_date)

        structure_widget = self.official_fields.get("structure_type")
        if isinstance(structure_widget, QComboBox):
            idx = max(structure_widget.findData(official.structure_type), 0)
            if force or structure_widget.currentData() in (None, "", "tower"):
                structure_widget.setCurrentIndex(idx)

        commissioning_widget = self.official_fields.get("commissioning_year")
        if isinstance(commissioning_widget, QSpinBox) and official.commissioning_year:
            if force or commissioning_widget.value() <= 1900:
                commissioning_widget.setValue(official.commissioning_year)

        if replace_stations and self.station_table is not None:
            self.station_table.setRowCount(0)
            for station in official.stations:
                row = self.station_table.rowCount()
                self.station_table.insertRow(row)
                self.station_table.setItem(row, 0, QTableWidgetItem(station.name))
                self.station_table.setItem(row, 1, QTableWidgetItem("" if station.distance_m is None else self._format_station_distance(station.distance_m)))
                self.station_table.setItem(row, 2, QTableWidgetItem(station.note))
        self._sync_identity_projection()

    def _sync_identity_projection(self):
        if self.object_table is None:
            return

        project_name = self._text_value(self.metadata_fields.get("project_name"))
        inventory_number = self._text_value(self.metadata_fields.get("inventory_number"))
        location = self._text_value(self.metadata_fields.get("location"))
        customer_name = self._first_text(
            self._text_value(self.metadata_fields.get("customer_name")),
            self._text_value(self.customer_fields.get("full_name")),
        )
        contractor_name = self._first_text(
            self._text_value(self.metadata_fields.get("operator_name")),
            self._text_value(self.contractor_fields.get("full_name")),
        )
        title_operator = self._first_text(customer_name, contractor_name)
        title_location = self._first_text(
            location,
            self._text_value(self.customer_fields.get("actual_address")),
            self._text_value(self.contractor_fields.get("postal_address")),
            self._text_value(self.contractor_fields.get("legal_address")),
        )
        title_city = self._first_text(
            self._text_value(self.title_fields.get("city")),
            self._text_value(self.metadata_fields.get("approval_city")),
        )

        previous_loading_state = self._loading_state
        self._loading_state = True
        try:
            self._set_line_edit_value(self.title_fields.get("name"), project_name, force=True)
            self._set_line_edit_value(self.title_fields.get("inventory_number"), inventory_number, force=True)
            self._set_line_edit_value(self.title_fields.get("operator"), title_operator, force=True)
            self._set_line_edit_value(self.title_fields.get("location"), title_location, force=True)
            if title_city:
                self._set_line_edit_value(self.title_fields.get("city"), title_city, force=False)
            self._sync_primary_object_row(project_name, inventory_number, title_location, title_operator)
        finally:
            self._loading_state = previous_loading_state

    def _sync_primary_object_row(
        self,
        project_name: str,
        inventory_number: str,
        location: str,
        operator_name: str,
    ):
        if self.object_table is None:
            return
        if not any([project_name, inventory_number, location, operator_name]) and self.object_table.rowCount() == 0:
            return

        if self.object_table.rowCount() == 0:
            self.object_table.insertRow(0)

        existing_year = self._safe_int(self._table_item_text(self.object_table, 0, 2)) if self.object_table.rowCount() else None
        existing_note = self._table_item_text(self.object_table, 0, 4).strip() if self.object_table.rowCount() else ""
        commissioning_widget = self.official_fields.get("commissioning_year")
        default_year = int(commissioning_widget.value()) if isinstance(commissioning_widget, QSpinBox) else None
        note_value = existing_note or (
            f"\u042d\u043a\u0441\u043f\u043b\u0443\u0430\u0442\u0438\u0440\u0443\u044e\u0449\u0430\u044f \u043e\u0440\u0433\u0430\u043d\u0438\u0437\u0430\u0446\u0438\u044f: {operator_name}"
            if operator_name
            else ""
        )

        values = [
            project_name,
            inventory_number,
            "" if existing_year is None and default_year is None else str(existing_year or default_year or ""),
            location,
            note_value,
        ]
        for column, value in enumerate(values):
            item = self.object_table.item(0, column)
            if item is None:
                self.object_table.setItem(0, column, QTableWidgetItem(value))
            elif item.text() != value:
                item.setText(value)

    def _set_line_edit_value(self, widget, value: str, force: bool = False):
        if not isinstance(widget, QLineEdit):
            return
        if force or not widget.text().strip():
            widget.setText(value or "")

    def _set_date_edit_value(self, widget, value: date | None, force: bool = False):
        if not isinstance(widget, QDateEdit) or value is None:
            return
        current_date = widget.date().toPyDate()
        if force or current_date == date.today():
            widget.setDate(value)

    @staticmethod
    def _parse_report_info_date(value: Any) -> date | None:
        if isinstance(value, date):
            return value
        text = str(value or "").strip()
        if not text:
            return None
        for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        return None

    @staticmethod
    def _table_item_text(table: QTableWidget | None, row: int, column: int) -> str:
        if table is None:
            return ""
        item = table.item(row, column)
        return item.text() if item is not None else ""

    def _format_station_distance(self, value: float) -> str:
        text = f"{value:.3f}"
        return text.rstrip("0").rstrip(".")

    @staticmethod
    def _first_text(*values):
        for value in values:
            text = str(value or "").strip()
            if text:
                return text
        return ""

