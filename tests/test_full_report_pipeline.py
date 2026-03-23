"""
Тесты для полного генератора отчёта.
"""

from datetime import date

import pandas as pd
from PyQt6.QtWidgets import QApplication

from core.full_report_models import FullReportDraftState, OfficialReportContext, SurveyStationEntry
from core.report_schema import (
    ConclusionEntry,
    ContractorInfo,
    CustomerInfo,
    DocumentReviewEntry,
    EquipmentEntry,
    FullReportData,
    InspectedObject,
    ReferenceProfile,
    ReportMetadata,
    Specialist,
    StructuralElement,
    TechnicalStateEntry,
    TitleObjectInfo,
    VerticalDeviationRecord,
)
from core.services.report_templates import (
    ReportDataAssembler,
    ReportTemplateManager,
    build_report_data_from_template,
)
from gui.full_report_tab import FullReportTab
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


def test_render_model_includes_geodesic_summary_table():
    report = _sample_report_data()
    report.geodesic_results = {
        "total_levels": 2,
        "max_deviation_mm": 8.5,
        "mean_deviation_mm": 4.25,
        "levels": [
            {"index": 1, "height_m": 5.0, "deviation_mm": 2.5, "points": 24},
            {"index": 2, "height_m": 10.0, "deviation_mm": 8.5, "points": 32},
        ],
    }
    report.calculation_results = {"max_straightness_mm": 6.2}
    draft = FullReportDraftState(
        form_data=report,
        official_context=OfficialReportContext(performer="\u0418\u0441\u043f\u043e\u043b\u043d\u0438\u0442\u0435\u043b\u044c"),
    )

    model = FullReportBuilder().assemble_render_model(draft, {}, None)
    measurements_section = next(section for section in model.sections if section.key == "measurements")
    table_titles = [table.title for table in measurements_section.tables]

    assert "\u0421\u0432\u043e\u0434\u043a\u0430 \u043f\u043e\u043b\u0443\u0447\u0435\u043d\u043d\u044b\u0445 \u0438 \u0440\u0430\u0441\u0441\u0447\u0438\u0442\u0430\u043d\u043d\u044b\u0445 \u0434\u0430\u043d\u043d\u044b\u0445" in table_titles
    assert "\u0414\u0435\u0442\u0430\u043b\u0438\u0437\u0430\u0446\u0438\u044f \u0433\u0435\u043e\u0434\u0435\u0437\u0438\u0447\u0435\u0441\u043a\u0438\u0445 \u0443\u0440\u043e\u0432\u043d\u0435\u0439" in table_titles


def test_full_report_tab_reuses_shared_report_info_for_title_object():
    app = QApplication.instance() or QApplication([])
    _ = app
    tab = FullReportTab()
    tab.apply_shared_report_info(
        {
            "project_name": "\u041c\u0430\u0447\u0442\u0430 \u041f\u0420\u0421-12",
            "location": "\u0412\u043e\u0440\u043e\u043d\u0435\u0436\u0441\u043a\u0430\u044f \u043e\u0431\u043b\u0430\u0441\u0442\u044c",
            "organization": "\u041e\u041e\u041e \u00ab\u0413\u0430\u0437\u043f\u0440\u043e\u043c \u0442\u0440\u0430\u043d\u0441\u0433\u0430\u0437 \u041c\u043e\u0441\u043a\u0432\u0430\u00bb",
            "executor": "\u0418\u0432\u0430\u043d\u043e\u0432 \u0418.\u0418.",
            "position": "\u0413\u043b\u0430\u0432\u043d\u044b\u0439 \u0438\u043d\u0436\u0435\u043d\u0435\u0440",
            "survey_date": "21.03.2026",
            "notes": "\u041f\u043e\u0432\u0442\u043e\u0440\u043d\u0430\u044f \u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0430.",
        }
    )
    tab.metadata_fields["inventory_number"].setText("0044165")

    form_data = tab.collect_form_data(validate_required=False)

    assert form_data.metadata.project_name == "\u041c\u0430\u0447\u0442\u0430 \u041f\u0420\u0421-12"
    assert form_data.metadata.location == "\u0412\u043e\u0440\u043e\u043d\u0435\u0436\u0441\u043a\u0430\u044f \u043e\u0431\u043b\u0430\u0441\u0442\u044c"
    assert form_data.title_object is not None
    assert form_data.title_object.name == form_data.metadata.project_name
    assert form_data.title_object.inventory_number == "0044165"
    assert form_data.title_object.operator == "\u041e\u041e\u041e \u00ab\u0413\u0430\u0437\u043f\u0440\u043e\u043c \u0442\u0440\u0430\u043d\u0441\u0433\u0430\u0437 \u041c\u043e\u0441\u043a\u0432\u0430\u00bb"
    assert form_data.title_object.location == form_data.metadata.location
    assert form_data.object_list
    assert form_data.object_list[0].inventory_number == "0044165"


def test_assembler_syncs_duplicate_fields_and_station_points():
    report = _sample_report_data()
    report.metadata.customer_name = ""
    report.metadata.operator_name = ""
    report.title_object = None
    report.object_list = []

    raw_data = pd.DataFrame(
        [
            {"name": "P1", "x": 0.0, "y": 0.0, "z": 5.0, "is_station": False},
            {"name": "P2", "x": 2.0, "y": 0.0, "z": 5.0, "is_station": False},
            {"name": "SP1", "x": 10.0, "y": 0.0, "z": 1.5, "is_station": True},
            {"name": "SP2", "x": -12.0, "y": 0.0, "z": 1.8, "is_station": True},
        ]
    )
    assembler = ReportDataAssembler({}, raw_data, report.reference_profiles)
    enriched = assembler.fill_measurement_sections(report)
    official = assembler.build_official_context(enriched)

    assert enriched.metadata.customer_name == enriched.customer.full_name
    assert enriched.metadata.operator_name == enriched.contractor.full_name
    assert enriched.title_object is not None
    assert enriched.title_object.inventory_number == enriched.metadata.inventory_number
    assert enriched.title_object.location == enriched.metadata.location
    assert enriched.title_object.operator == enriched.customer.full_name
    assert [item.name for item in official.stations] == ["SP1", "SP2"]
    assert official.base_station == "SP1"
    assert official.stations[0].distance_m == 9.0
    assert official.stations[1].distance_m == 13.0


def test_builder_warns_about_duplicate_field_and_station_mismatches():
    report = _sample_report_data()
    report.title_object = TitleObjectInfo(
        name=report.metadata.project_name,
        inventory_number="DIFF-001",
        operator="Другая организация",
        location="Другой адрес",
        city="Москва",
        year=report.metadata.approval_date.year,
    )

    raw_data = pd.DataFrame(
        [
            {"name": "Tower-1", "x": 0.0, "y": 0.0, "z": 5.0, "is_station": False},
            {"name": "Tower-2", "x": 2.0, "y": 0.0, "z": 5.0, "is_station": False},
            {"name": "SP1", "x": 8.0, "y": 0.0, "z": 1.5, "is_station": True},
        ]
    )
    draft = FullReportDraftState(
        form_data=report,
        official_context=OfficialReportContext(
            performer="Исполнитель",
            stations=[SurveyStationEntry(name="MANUAL-STATION", distance_m=99.0, note="ручной ввод")],
            base_station="MANUAL",
        ),
    )
    model = FullReportBuilder().assemble_render_model(draft, {}, raw_data)

    assert any("Инвентарный номер в карточке объекта отличается" in message for message in model.warnings)
    assert any("Местоположение в карточке объекта отличается" in message for message in model.warnings)
    assert any("БС/базовая станция не совпадает" in message for message in model.warnings)
    assert any("Список стоянок в полном отчёте отличается" in message for message in model.warnings)


def test_full_report_draft_migrates_legacy_state():
    source = _sample_report_data(with_extended=True)
    legacy = source.to_dict()
    draft = FullReportDraftState.from_dict(legacy)
    assert draft.form_data.metadata.project_name == source.metadata.project_name
    assert draft.selected_template == ""


def test_new_template_save_excludes_runtime_sections(tmp_path):
    manager = ReportTemplateManager(storage_dir=tmp_path)
    report = _sample_report_data(with_extended=True)
    report.measurements = []
    template = manager.create_template_from_report(
        "official",
        report,
        official_context_defaults=OfficialReportContext(structure_type="mast", performer="Иванов"),
    )
    manager.save_full_template(template)
    loaded = manager.load_full_template("official")
    assert loaded.form_data.metadata.report_number == ""
    assert loaded.official_context_defaults.structure_type == "mast"
    assert loaded.form_data.conclusions == []


def test_render_model_drives_preview_and_docx(tmp_path):
    report = _sample_report_data(with_extended=True)
    report.vertical_deviation_table = [
        VerticalDeviationRecord(section_number=1, height_m=10.0, deviation_previous_mm=None, deviation_current_mm=9.0),
    ]
    draft = FullReportDraftState(
        form_data=report,
        official_context=OfficialReportContext(
            structure_type="mast",
            performer="Исполнитель",
            instrument="Trimble",
            decision_comment="Требуется согласование с проектировщиком.",
        ),
    )
    builder = FullReportBuilder()
    model = builder.assemble_render_model(draft, {}, None)
    html = builder.render_preview(model)
    output = tmp_path / "full_render.docx"
    builder.render_docx(model, output)
    assert "Протокол вертикальности" in html
    assert "Выявлены превышения по вертикальности" in html
    assert output.exists()

