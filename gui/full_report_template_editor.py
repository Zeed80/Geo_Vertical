"""
Диалог управления шаблонами полного отчёта ДО ТСС.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QPlainTextEdit,
    QMessageBox,
    QInputDialog,
)

from core.report_schema import (
    Appendix,
    ConclusionEntry,
    ContractorInfo,
    CustomerInfo,
    DocumentReference,
    DocumentReviewEntry,
    EquipmentEntry,
    FullReportData,
    InspectedObject,
    Recommendation,
    ReportMetadata,
    Specialist,
    TechnicalStateEntry,
    VisualInspectionEntry,
)
from core.services.report_templates import ReportTemplateManager


def build_demo_report_data() -> FullReportData:
    today = date.today()
    metadata = ReportMetadata(
        report_number="ГМПД-ГТМ-ТСС-0000",
        project_name="Пример объекта",
        inventory_number="0000000",
        location="Регион, город, адрес объекта",
        customer_name="ООО «Газпром трансгаз»",
        operator_name="ООО «ГМП-Диагностика»",
        start_date=today,
        end_date=today,
        approval_person="И.О. Фамилия",
        approval_position="Директор",
        approval_city="Москва",
        approval_date=today,
    )
    customer = CustomerInfo(
        full_name="ООО «Газпром трансгаз»",
        director="Иванов И.И.",
        legal_address="117420, Москва, ул. Наметкина, 16",
        actual_address="117420, Москва, ул. Наметкина, 16",
        phone="+7 (495) 000-00-00",
        email="info@example.com",
    )
    contractor = ContractorInfo(
        full_name="ООО «ГМП-Диагностика»",
        director="Петров П.П.",
        legal_address="г. Москва, Щербинка, Симферопольское ш., д.14а",
        postal_address="г. Москва, Щербинка, Симферопольское ш., д.14а",
        phone="+7 (495) 111-11-11",
        email="office@example.com",
        accreditation_certificate="№ АЦЛНК-38-00000",
        sro_certificate="№ 9718087276-20230101-0000",
    )

    specialist = Specialist(
        full_name="Кожевников В.А.",
        certifications={"ВИК": "АЦСНК-38-II-03705"},
        expires_at={"ВИК": today},
    )
    equipment = EquipmentEntry(
        name="Тахеометр Trimble M3DR5",
        serial_number="D000000",
        certificate="С-АКЗ/11-03-2025/415978163",
        valid_until=today,
    )
    appendix = Appendix(title="Приложение А", description="Перечень нормативов", files=[])
    visual = VisualInspectionEntry(element="Пояса", defects="Без дефектов")
    recommendation = Recommendation(text="Провести очередное обследование согласно графику.")

    return FullReportData(
        metadata=metadata,
        customer=customer,
        contractor=contractor,
        specialists=[specialist],
        equipment=[equipment],
        documents=[
            DocumentReference(title="Технический паспорт", identifier="б/н"),
        ],
        object_list=[
            InspectedObject(
                name="Башня ПРС-12",
                inventory_number="0044165",
                commissioning_year=1957,
                location="Воронежская обл., Острогожский р-н, с. Владимировка",
                notes="Эксплуатирующая организация: ООО «Газпром трансгаз Москва»",
            )
        ],
        loads=None,
        soils=[],
        climate=None,
        structure=None,
        objects=[],
        documents_review=[
            DocumentReviewEntry(
                title="Технический паспорт",
                identifier="б/н",
                summary="Документ содержит данные о конструктивных элементах объекта.",
                conclusion="Использован при подготовке отчёта.",
            )
        ],
        normative_list=[
            "ГОСТ 31937-2011",
            "СП 13-102-2003",
        ],
        technical_state=[
            TechnicalStateEntry(
                structure="Металлоконструкции",
                classification="Работоспособное",
                comments="Дефектов, влияющих на несущую способность, не выявлено.",
            )
        ],
        visual_inspection=[visual],
        conclusions=[
            ConclusionEntry(label="Общее состояние", text="Конструкции соответствуют требованиям ГОСТ 31937-2011."),
        ],
        measurements=[],
        residual_resource=None,
        materials_research=[],
        geodesic_results={},
        calculation_results={},
        recommendations=[recommendation],
        appendices=[appendix],
    )


class FullReportTemplateEditor(QDialog):
    """Диалог для создания и редактирования шаблонов."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Шаблоны полного отчета")
        self.resize(920, 720)

        self.manager = ReportTemplateManager()

        main_layout = QVBoxLayout()
        self.setLayout(main_layout)

        header_layout = QHBoxLayout()
        self.template_combo = QComboBox()
        header_layout.addWidget(QLabel("Текущий шаблон:"))
        header_layout.addWidget(self.template_combo, stretch=1)

        self.load_btn = QPushButton("Загрузить")
        self.load_btn.clicked.connect(self.load_template)
        header_layout.addWidget(self.load_btn)

        self.delete_btn = QPushButton("Удалить")
        self.delete_btn.clicked.connect(self.delete_template)
        header_layout.addWidget(self.delete_btn)

        main_layout.addLayout(header_layout)

        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText("JSON-шаблон полного отчёта")
        main_layout.addWidget(self.editor, stretch=1)

        buttons_layout = QHBoxLayout()

        self.skeleton_btn = QPushButton("Создать черновик")
        self.skeleton_btn.clicked.connect(self.generate_skeleton)
        buttons_layout.addWidget(self.skeleton_btn)

        self.save_btn = QPushButton("Сохранить как…")
        self.save_btn.clicked.connect(self.save_template)
        buttons_layout.addWidget(self.save_btn)

        self.close_btn = QPushButton("Закрыть")
        self.close_btn.clicked.connect(self.accept)
        buttons_layout.addWidget(self.close_btn)

        main_layout.addLayout(buttons_layout)

        self._reload_list()

    def _reload_list(self):
        templates = self.manager.list_templates()
        self.template_combo.clear()
        self.template_combo.addItems(templates)
        if templates:
            self.template_combo.setCurrentIndex(0)

    def load_template(self):
        name = self.template_combo.currentText()
        if not name:
            QMessageBox.information(self, "Шаблон", "Нет доступных шаблонов.")
            return
        try:
            data = self.manager.load_template(name)
            payload = asdict(data)
            self.editor.setPlainText(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        except Exception as error:
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить шаблон:\n{error}")

    def delete_template(self):
        name = self.template_combo.currentText()
        if not name:
            return
        answer = QMessageBox.question(
            self,
            "Удаление шаблона",
            f"Удалить шаблон «{name}»?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.manager.delete_template(name)
        self._reload_list()

    def generate_skeleton(self):
        payload = asdict(build_demo_report_data())
        self.editor.setPlainText(json.dumps(payload, ensure_ascii=False, indent=2, default=str))

    def save_template(self):
        raw = self.editor.toPlainText().strip()
        if not raw:
            QMessageBox.warning(self, "Пустой шаблон", "Введите JSON с данными отчёта.")
            return
        try:
            payload = json.loads(raw)
            report_data = FullReportData.from_dict(payload)
        except Exception as error:
            QMessageBox.critical(self, "Ошибка", f"JSON не прошёл проверку:\n{error}")
            return

        name, ok = QInputDialog.getText(self, "Имя шаблона", "Введите название шаблона:", text=self.template_combo.currentText())
        if not ok or not name.strip():
            return

        try:
            self.manager.save_template(report_data, name.strip())
        except Exception as error:
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить шаблон:\n{error}")
            return

        self._reload_list()
        QMessageBox.information(self, "Готово", f"Шаблон «{name}» сохранён.")


