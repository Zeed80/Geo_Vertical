"""
Тесты для полного генератора отчёта.
"""

import os
from datetime import date
from pathlib import Path

import pandas as pd

from core.report_schema import (
    FullReportData,
    ReportMetadata,
    CustomerInfo,
    ContractorInfo,
    Specialist,
    EquipmentEntry,
    StructuralElement,
    ReferenceProfile,
    InspectedObject,
    DocumentReviewEntry,
    TechnicalStateEntry,
    ConclusionEntry,
)
from core.services.report_templates import (
    ReportTemplateManager,
    build_report_data_from_template,
)
from utils.full_report_builder import FullReportBuilder


def _sample_report_data(with_extended: bool = False) -> FullReportData:
    today = date.today()
    metadata = ReportMetadata(
        report_number="TEST-001",
        project_name="Тестовая башня",
        inventory_number="7777777",
        location="Воронежская обл., р-н",
        customer_name="ООО «Газпром трансгаз Москва»",
        operator_name="ООО «ГМП-Диагностика»",
        start_date=today,
        end_date=today,
        approval_person="Иванов И.И.",
        approval_position="Директор",
        approval_city="Москва",
        approval_date=today,
    )
    customer = CustomerInfo(
        full_name="ООО «Газпром трансгаз Москва»",
        director="Иванов И.И.",
        legal_address="Москва, ул. Наметкина, 16",
        actual_address="Москва, ул. Наметкина, 16",
        phone="+7 (495) 000-00-00",
        email="info@example.com",
    )
    contractor = ContractorInfo(
        full_name="ООО «ГМП-Диагностика»",
        director="Петров П.П.",
        legal_address="Москва, Щербинка",
        postal_address="Москва, Щербинка",
        phone="+7 (495) 111-11-11",
        email="office@example.com",
        accreditation_certificate="АЦЛНК-38-00000",
        sro_certificate="9718087276-20230912-1011",
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
    profile = ReferenceProfile(
        name="Кожевников В.А.",
        role="Начальник ДЭО",
        instruments=[equipment],
        certificates=["ВИК: АЦСНК-38-II-03705"],
        contacts={"email": "kojevnikov@example.com"},
    )

    report = FullReportData(
        metadata=metadata,
        customer=customer,
        contractor=contractor,
        specialists=[specialist],
        equipment=[equipment],
        documents=[],
        loads=None,
        soils=[],
        climate=None,
        structure=None,
        objects=[],
        normative_list=["ГОСТ 31937-2011"],
        visual_inspection=[],
        measurements=[],
        residual_resource=None,
        materials_research=[],
        geodesic_results={},
        calculation_results={},
        recommendations=[],
        appendices=[],
        structural_elements=[
            StructuralElement(
                section="+28.2",
                element="Пояс",
                material="Труба 159х6",
                parameters="Сталь Ст20",
                notes="Фланцевые соединения",
            )
        ],
        reference_profiles=[profile],
    )
    if with_extended:
        report.object_list = [
            InspectedObject(
                name="Башня ПРС-12",
                inventory_number="0044165",
                commissioning_year=1957,
                location="Воронежская обл.",
                notes="Эксплуатирующая организация: ООО «Газпром трансгаз Москва»",
            )
        ]
        report.documents_review = [
            DocumentReviewEntry(
                title="Технический паспорт",
                identifier="б/н",
                summary="Содержит сведения о конструкциях.",
                conclusion="Соответствует заданию.",
            )
        ]
        report.technical_state = [
            TechnicalStateEntry(
                structure="Несущие конструкции",
                classification="Работоспособное",
                comments="Отклонения в пределах допуска.",
            )
        ]
        report.conclusions = [ConclusionEntry(label="Состояние", text="Конструкция пригодна к эксплуатации.")]
    return report


def test_template_roundtrip(tmp_path):
    manager = ReportTemplateManager(storage_dir=tmp_path)
    data = _sample_report_data(with_extended=True)
    manager.save_template(data, "test")
    loaded = manager.load_template("test")
    assert loaded.metadata.project_name == data.metadata.project_name
    assert loaded.customer.full_name == data.customer.full_name
    assert loaded.structural_elements[0].element == "Пояс"
    assert loaded.reference_profiles[0].name == "Кожевников В.А."
    assert loaded.object_list[0].name == "Башня ПРС-12"
    assert loaded.documents_review[0].title == "Технический паспорт"
    assert loaded.technical_state[0].classification == "Работоспособное"
    assert loaded.conclusions[0].label == "Состояние"


def test_assembler_enriches_data(tmp_path):
    manager = ReportTemplateManager(storage_dir=tmp_path)
    sample = _sample_report_data()
    manager.save_template(sample, "base")
    manager.merge_reference_profiles(sample.reference_profiles)

    centers = pd.DataFrame(
        [
            {"z": 5.0, "deviation": 0.0001, "points_count": 32},
            {"z": 10.0, "deviation": 0.0003, "points_count": 44},
        ]
    )
    processed = {
        "centers": centers,
        "thickness_summary": "Максимальное снижение толщины 5%",
        "residual_resource": {"ok": True, "years": 120, "notes": "Без ограничений"},
    }

    report = build_report_data_from_template(manager, "base", processed, centers)
    assert report.geodesic_results["total_levels"] == 2
    assert report.measurements[0].method.startswith("Толщинометрия")
    assert report.residual_resource.residual_years == 120
    assert any(eq.name == "Тахеометр Trimble M3DR5" for eq in report.equipment)
    assert report.title_object is not None
    assert len(report.vertical_deviation_table) == 2
    assert len(report.straightness_records) == 2
    assert len(report.annexes) >= 10
    assert report.object_list
    assert report.documents_review
    assert report.technical_state
    assert report.conclusions


def test_full_report_builder_creates_doc(tmp_path):
    builder = FullReportBuilder()
    output = tmp_path / "report.docx"
    builder.build_docx(_sample_report_data(), output)
    assert output.exists()
    assert output.stat().st_size > 0

