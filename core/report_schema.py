"""
Модель данных полного отчета по форме ДО ТСС.

Содержит детализированные dataclass-структуры, описывающие все разделы отчета,
включая титульные блоки, сведения об организациях, специалистов, приборы,
нормативы, результаты обследований и приложения.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any


@dataclass
class ReportMetadata:
    report_number: str
    project_name: str
    inventory_number: str
    location: str
    customer_name: str
    operator_name: str
    start_date: date
    end_date: date
    approval_person: str
    approval_position: str
    approval_city: str
    approval_date: date


@dataclass
class CustomerInfo:
    full_name: str
    director: str
    legal_address: str
    actual_address: str
    phone: str
    email: str


@dataclass
class ContractorInfo:
    full_name: str
    director: str
    legal_address: str
    postal_address: str
    phone: str
    email: str
    accreditation_certificate: str
    sro_certificate: str


@dataclass
class Specialist:
    full_name: str
    certifications: dict[str, str]
    expires_at: dict[str, date]


@dataclass
class EquipmentEntry:
    name: str
    serial_number: str
    certificate: str
    valid_until: date


@dataclass
class DocumentReference:
    title: str
    identifier: str
    comments: str | None = None


@dataclass
class TitleObjectInfo:
    name: str
    inventory_number: str
    operator: str
    location: str
    city: str
    year: int


@dataclass
class InspectedObject:
    name: str
    inventory_number: str | None = None
    commissioning_year: int | None = None
    location: str | None = None
    notes: str | None = None


@dataclass
class DocumentReviewEntry:
    title: str
    identifier: str | None = None
    summary: str | None = None
    conclusion: str | None = None


@dataclass
class TechnicalStateEntry:
    structure: str
    classification: str
    comments: str | None = None


@dataclass
class ConclusionEntry:
    label: str
    text: str


@dataclass
class ReferenceProfile:
    name: str
    role: str | None = None
    instruments: list[EquipmentEntry] = field(default_factory=list)
    certificates: list[str] = field(default_factory=list)
    contacts: dict[str, str] = field(default_factory=dict)


@dataclass
class LoadCondition:
    snow_load_kpa: float
    wind_pressure_kpa: float
    icing_mm: float
    seismicity: int
    reliability_factor: float


@dataclass
class SoilCondition:
    soil_type: str
    freezing_depth_m: float


@dataclass
class ClimateParameters:
    cold_period: dict[str, Any]
    warm_period: dict[str, Any]


@dataclass
class StructuralDescription:
    purpose: str
    planning_decisions: str
    structural_scheme: str
    geology: str | None
    foundations: str
    metal_structure: str
    lattice_notes: str | None = None


@dataclass
class StructuralElement:
    section: str
    element: str
    material: str
    parameters: str
    notes: str | None = None


@dataclass
class AngleMeasurementRecord:
    index: int
    section: str
    height_m: float
    belt: str
    kl_arcsec: float | None = None
    kr_arcsec: float | None = None
    diff_arcsec: float | None = None
    beta_measured: float | None = None
    center_value: float | None = None
    delta_beta: float | None = None
    delta_mm: float | None = None


@dataclass
class VerticalDeviationRecord:
    section_number: int
    height_m: float
    deviation_previous_mm: float | None
    deviation_current_mm: float | None


@dataclass
class StraightnessRecord:
    belt_number: int
    height_m: float
    deviation_mm: float
    tolerance_mm: float


@dataclass
class ThicknessMeasurementRecord:
    group_name: str
    location: str
    normative_thickness_mm: float
    readings_mm: list[float]
    min_value_mm: float
    deviation_percent: float


@dataclass
class CoatingMeasurementRecord:
    group_name: str
    location: str
    project_range_min_mkm: float
    project_range_max_mkm: float
    readings_mkm: list[float]
    min_value_mkm: float


@dataclass
class UltrasonicInspectionRecord:
    location: str
    base_thickness_mm: float
    sample_thickness_mm: float
    equivalent_area_mm2: float | None
    depth_mm: float | None
    length_mm: float | None
    defect_type: str | None
    conclusion: str


@dataclass
class ConcreteStrengthRecord:
    zone: str
    mean_strength_mpa: float
    adjusted_strength_mpa: float


@dataclass
class ProtectiveLayerRecord:
    location: str
    allowed_mm: float
    measured_mm: float
    deviation_percent: float


@dataclass
class VibrationRecord:
    location: str
    displacement_microns: list[float]
    frequency_hz: float


@dataclass
class SettlementRecord:
    mark: str
    year: int
    settlement_mm: float


@dataclass
class ResourceCalculationData:
    service_life_years: float
    wear_constant: float
    total_service_life_years: float
    residual_resource_years: float
    epsilon: float
    lambda_value: float


@dataclass
class AnnexEntry:
    code: str
    title: str
    description: str | None = None
    pages: list[int] = field(default_factory=list)


@dataclass
class VisualInspectionEntry:
    element: str
    defects: str


@dataclass
class MeasurementSummary:
    method: str
    standard: str
    result: str


@dataclass
class ResidualResourceResult:
    satisfies_requirements: bool
    residual_years: float
    notes: str


@dataclass
class Recommendation:
    text: str


@dataclass
class Appendix:
    title: str
    description: str | None = None
    files: list[str] = field(default_factory=list)


@dataclass
class FullReportData:
    metadata: ReportMetadata
    customer: CustomerInfo
    contractor: ContractorInfo
    specialists: list[Specialist] = field(default_factory=list)
    equipment: list[EquipmentEntry] = field(default_factory=list)
    documents: list[DocumentReference] = field(default_factory=list)
    object_list: list[InspectedObject] = field(default_factory=list)
    loads: LoadCondition | None = None
    soils: list[SoilCondition] = field(default_factory=list)
    climate: ClimateParameters | None = None
    structure: StructuralDescription | None = None
    objects: list[DocumentReference] = field(default_factory=list)
    documents_review: list[DocumentReviewEntry] = field(default_factory=list)
    normative_list: list[str] = field(default_factory=list)
    technical_state: list[TechnicalStateEntry] = field(default_factory=list)
    visual_inspection: list[VisualInspectionEntry] = field(default_factory=list)
    conclusions: list[ConclusionEntry] = field(default_factory=list)
    measurements: list[MeasurementSummary] = field(default_factory=list)
    residual_resource: ResidualResourceResult | None = None
    materials_research: list[MeasurementSummary] = field(default_factory=list)
    geodesic_results: dict[str, Any] = field(default_factory=dict)
    calculation_results: dict[str, Any] = field(default_factory=dict)
    recommendations: list[Recommendation] = field(default_factory=list)
    appendices: list[Appendix] = field(default_factory=list)
    structural_elements: list[StructuralElement] = field(default_factory=list)
    title_object: TitleObjectInfo | None = None
    reference_profiles: list[ReferenceProfile] = field(default_factory=list)
    angle_measurements: list[AngleMeasurementRecord] = field(default_factory=list)
    vertical_deviation_table: list[VerticalDeviationRecord] = field(default_factory=list)
    straightness_records: list[StraightnessRecord] = field(default_factory=list)
    thickness_measurements: list[ThicknessMeasurementRecord] = field(default_factory=list)
    coating_measurements: list[CoatingMeasurementRecord] = field(default_factory=list)
    ultrasonic_records: list[UltrasonicInspectionRecord] = field(default_factory=list)
    concrete_strength_records: list[ConcreteStrengthRecord] = field(default_factory=list)
    protective_layer_records: list[ProtectiveLayerRecord] = field(default_factory=list)
    vibration_records: list[VibrationRecord] = field(default_factory=list)
    settlement_records: list[SettlementRecord] = field(default_factory=list)
    resource_calculation: ResourceCalculationData | None = None
    annexes: list[AnnexEntry] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Сериализация в словарь для сохранения в JSON."""
        return asdict(self)

    @staticmethod
    def from_dict(payload: dict[str, Any]) -> FullReportData:
        """Десериализация из словаря."""

        def parse_date(value: Any) -> date:
            if isinstance(value, date):
                return value
            if isinstance(value, (datetime, )):
                return value.date()
            if value in (None, "", "null"):
                return date.today()
            if isinstance(value, str):
                for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
                    try:
                        return datetime.strptime(value, fmt).date()
                    except ValueError:
                        continue
                return datetime.fromisoformat(value).date()
            raise ValueError(f"Невозможно преобразовать значение в дату: {value}")

        def parse_metadata(data: dict[str, Any]) -> ReportMetadata:
            return ReportMetadata(
                report_number=data["report_number"],
                project_name=data["project_name"],
                inventory_number=data["inventory_number"],
                location=data["location"],
                customer_name=data["customer_name"],
                operator_name=data["operator_name"],
                start_date=parse_date(data["start_date"]),
                end_date=parse_date(data["end_date"]),
                approval_person=data["approval_person"],
                approval_position=data["approval_position"],
                approval_city=data["approval_city"],
                approval_date=parse_date(data["approval_date"]),
            )

        def parse_specialists(data: list[dict[str, Any]]) -> list[Specialist]:
            specialists = []
            for item in data or []:
                expires = {k: parse_date(v) for k, v in (item.get("expires_at") or {}).items()}
                specialists.append(
                    Specialist(
                        full_name=item["full_name"],
                        certifications=item.get("certifications", {}),
                        expires_at=expires,
                    )
                )
            return specialists

        def parse_equipment(data: list[dict[str, Any]]) -> list[EquipmentEntry]:
            items = []
            for item in data or []:
                items.append(
                    EquipmentEntry(
                        name=item["name"],
                        serial_number=item["serial_number"],
                        certificate=item["certificate"],
                        valid_until=parse_date(item["valid_until"]),
                    )
                )
            return items

        def parse_documents(data: list[dict[str, Any]]) -> list[DocumentReference]:
            return [
                DocumentReference(title=item["title"], identifier=item["identifier"], comments=item.get("comments"))
                for item in data or []
            ]

        def parse_visual(data: list[dict[str, Any]]) -> list[VisualInspectionEntry]:
            return [
                VisualInspectionEntry(element=item["element"], defects=item["defects"])
                for item in data or []
            ]

        def parse_measurements(data: list[dict[str, Any]]) -> list[MeasurementSummary]:
            return [
                MeasurementSummary(method=item["method"], standard=item["standard"], result=item["result"])
                for item in data or []
            ]

        def parse_recommendations(data: list[dict[str, Any]]) -> list[Recommendation]:
            return [Recommendation(text=item["text"]) for item in data or []]

        def parse_appendices(data: list[dict[str, Any]]) -> list[Appendix]:
            return [
                Appendix(title=item["title"], description=item.get("description"), files=item.get("files", []))
                for item in data or []
            ]

        def parse_objects(data: list[dict[str, Any]]) -> list[InspectedObject]:
            objects: list[InspectedObject] = []
            for item in data or []:
                year = item.get("commissioning_year")
                try:
                    parsed_year = int(year) if year not in (None, "", "null") else None
                except (TypeError, ValueError):
                    parsed_year = None
                objects.append(
                    InspectedObject(
                        name=item.get("name", ""),
                        inventory_number=item.get("inventory_number"),
                        commissioning_year=parsed_year,
                        location=item.get("location"),
                        notes=item.get("notes"),
                    )
                )
            return objects

        def parse_document_reviews(data: list[dict[str, Any]]) -> list[DocumentReviewEntry]:
            return [
                DocumentReviewEntry(
                    title=item.get("title", ""),
                    identifier=item.get("identifier"),
                    summary=item.get("summary"),
                    conclusion=item.get("conclusion"),
                )
                for item in data or []
            ]

        def parse_technical_state(data: list[dict[str, Any]]) -> list[TechnicalStateEntry]:
            return [
                TechnicalStateEntry(
                    structure=item.get("structure", ""),
                    classification=item.get("classification", ""),
                    comments=item.get("comments"),
                )
                for item in data or []
            ]

        def parse_conclusions(data: list[dict[str, Any]]) -> list[ConclusionEntry]:
            return [
                ConclusionEntry(label=item.get("label", ""), text=item.get("text", ""))
                for item in data or []
            ]

        def parse_structural_elements(data: list[dict[str, Any]]) -> list[StructuralElement]:
            return [
                StructuralElement(
                    section=item.get("section", ""),
                    element=item.get("element", ""),
                    material=item.get("material", ""),
                    parameters=item.get("parameters", ""),
                    notes=item.get("notes"),
                )
                for item in data or []
            ]

        def parse_title_object(data: dict[str, Any] | None) -> TitleObjectInfo | None:
            if not data:
                return None
            return TitleObjectInfo(**data)

        def parse_reference_profiles(data: list[dict[str, Any]]) -> list[ReferenceProfile]:
            profiles: list[ReferenceProfile] = []
            for item in data or []:
                instruments_payload = item.get("instruments", []) or []
                instruments = [
                    EquipmentEntry(
                        name=inst.get("name", ""),
                        serial_number=inst.get("serial_number", ""),
                        certificate=inst.get("certificate", ""),
                        valid_until=parse_date(inst.get("valid_until")),
                    )
                    for inst in instruments_payload
                ]
                profile = ReferenceProfile(
                    name=item.get("name", ""),
                    role=item.get("role"),
                    instruments=instruments,
                    certificates=item.get("certificates", []),
                    contacts=item.get("contacts", {}),
                )
                profiles.append(profile)
            return profiles

        def parse_angle_measurements(data: list[dict[str, Any]]) -> list[AngleMeasurementRecord]:
            return [AngleMeasurementRecord(**item) for item in data or []]

        def parse_vertical_deviation(data: list[dict[str, Any]]) -> list[VerticalDeviationRecord]:
            return [VerticalDeviationRecord(**item) for item in data or []]

        def parse_straightness(data: list[dict[str, Any]]) -> list[StraightnessRecord]:
            return [StraightnessRecord(**item) for item in data or []]

        def parse_thickness(data: list[dict[str, Any]]) -> list[ThicknessMeasurementRecord]:
            return [ThicknessMeasurementRecord(**item) for item in data or []]

        def parse_coating(data: list[dict[str, Any]]) -> list[CoatingMeasurementRecord]:
            return [CoatingMeasurementRecord(**item) for item in data or []]

        def parse_ultrasonic(data: list[dict[str, Any]]) -> list[UltrasonicInspectionRecord]:
            return [UltrasonicInspectionRecord(**item) for item in data or []]

        def parse_concrete_strength(data: list[dict[str, Any]]) -> list[ConcreteStrengthRecord]:
            return [ConcreteStrengthRecord(**item) for item in data or []]

        def parse_protective_layer(data: list[dict[str, Any]]) -> list[ProtectiveLayerRecord]:
            return [ProtectiveLayerRecord(**item) for item in data or []]

        def parse_vibration(data: list[dict[str, Any]]) -> list[VibrationRecord]:
            return [VibrationRecord(**item) for item in data or []]

        def parse_settlement(data: list[dict[str, Any]]) -> list[SettlementRecord]:
            return [SettlementRecord(**item) for item in data or []]

        def parse_resource_calc(data: dict[str, Any] | None) -> ResourceCalculationData | None:
            if not data:
                return None
            return ResourceCalculationData(**data)

        def parse_annexes(data: list[dict[str, Any]]) -> list[AnnexEntry]:
            return [AnnexEntry(**item) for item in data or []]

        metadata = parse_metadata(payload["metadata"])
        customer = CustomerInfo(**payload["customer"])
        contractor = ContractorInfo(**payload["contractor"])

        residual = payload.get("residual_resource")
        residual_obj = (
            ResidualResourceResult(
                satisfies_requirements=residual["satisfies_requirements"],
                residual_years=residual["residual_years"],
                notes=residual.get("notes", ""),
            )
            if residual
            else None
        )

        structure_payload = payload.get("structure")
        structure_obj = StructuralDescription(**structure_payload) if structure_payload else None

        climate_payload = payload.get("climate")
        climate_obj = ClimateParameters(**climate_payload) if climate_payload else None

        loads_payload = payload.get("loads")
        load_obj = LoadCondition(**loads_payload) if loads_payload else None

        soils = [SoilCondition(**item) for item in payload.get("soils", [])]
        objects = parse_documents(payload.get("objects", []))

        return FullReportData(
            metadata=metadata,
            customer=customer,
            contractor=contractor,
            specialists=parse_specialists(payload.get("specialists", [])),
            equipment=parse_equipment(payload.get("equipment", [])),
            documents=parse_documents(payload.get("documents", [])),
            object_list=parse_objects(payload.get("object_list", payload.get("objects_list", []))),
            loads=load_obj,
            soils=soils,
            climate=climate_obj,
            structure=structure_obj,
            objects=objects,
            documents_review=parse_document_reviews(payload.get("documents_review", [])),
            normative_list=payload.get("normative_list", []),
            technical_state=parse_technical_state(payload.get("technical_state", [])),
            visual_inspection=parse_visual(payload.get("visual_inspection", [])),
            conclusions=parse_conclusions(payload.get("conclusions", [])),
            measurements=parse_measurements(payload.get("measurements", [])),
            residual_resource=residual_obj,
            materials_research=parse_measurements(payload.get("materials_research", [])),
            geodesic_results=payload.get("geodesic_results", {}),
            calculation_results=payload.get("calculation_results", {}),
            recommendations=parse_recommendations(payload.get("recommendations", [])),
            appendices=parse_appendices(payload.get("appendices", [])),
            structural_elements=parse_structural_elements(payload.get("structural_elements", [])),
            title_object=parse_title_object(payload.get("title_object")),
            reference_profiles=parse_reference_profiles(payload.get("reference_profiles", [])),
            angle_measurements=parse_angle_measurements(payload.get("angle_measurements", [])),
            vertical_deviation_table=parse_vertical_deviation(payload.get("vertical_deviation_table", [])),
            straightness_records=parse_straightness(payload.get("straightness_records", [])),
            thickness_measurements=parse_thickness(payload.get("thickness_measurements", [])),
            coating_measurements=parse_coating(payload.get("coating_measurements", [])),
            ultrasonic_records=parse_ultrasonic(payload.get("ultrasonic_records", [])),
            concrete_strength_records=parse_concrete_strength(payload.get("concrete_strength_records", [])),
            protective_layer_records=parse_protective_layer(payload.get("protective_layer_records", [])),
            vibration_records=parse_vibration(payload.get("vibration_records", [])),
            settlement_records=parse_settlement(payload.get("settlement_records", [])),
            resource_calculation=parse_resource_calc(payload.get("resource_calculation")),
            annexes=parse_annexes(payload.get("annexes", [])),
        )


__all__ = [
    "AngleMeasurementRecord",
    "AnnexEntry",
    "Appendix",
    "ClimateParameters",
    "CoatingMeasurementRecord",
    "ConclusionEntry",
    "ConcreteStrengthRecord",
    "ContractorInfo",
    "CustomerInfo",
    "DocumentReference",
    "DocumentReviewEntry",
    "EquipmentEntry",
    "FullReportData",
    "InspectedObject",
    "LoadCondition",
    "MeasurementSummary",
    "ProtectiveLayerRecord",
    "Recommendation",
    "ReferenceProfile",
    "ReportMetadata",
    "ResidualResourceResult",
    "ResourceCalculationData",
    "SettlementRecord",
    "SoilCondition",
    "Specialist",
    "StraightnessRecord",
    "StructuralDescription",
    "StructuralElement",
    "TechnicalStateEntry",
    "ThicknessMeasurementRecord",
    "TitleObjectInfo",
    "UltrasonicInspectionRecord",
    "VerticalDeviationRecord",
    "VibrationRecord",
    "VisualInspectionEntry",
]

