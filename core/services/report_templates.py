"""
Управление шаблонами отчётов и автоматическое наполнение данных.
"""

from __future__ import annotations

import json
import math
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from core.full_report_models import (
    FullReportDraftState,
    FullReportTemplate,
    OfficialReportContext,
    ReferenceLibrary,
    SurveyStationEntry,
    deepcopy_report_data,
)
from core.report_schema import (
    AngleMeasurementRecord,
    AnnexEntry,
    Appendix,
    ConclusionEntry,
    DocumentReviewEntry,
    EquipmentEntry,
    FullReportData,
    InspectedObject,
    MeasurementSummary,
    ReferenceProfile,
    ResidualResourceResult,
    StraightnessRecord,
    StructuralElement,
    TechnicalStateEntry,
    TitleObjectInfo,
    VerticalDeviationRecord,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
USER_DATA_DIR = PROJECT_ROOT / "user_data" / "report_templates"
USER_DATA_DIR.mkdir(parents=True, exist_ok=True)


def _safe_parse_date(value: Any) -> datetime.date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue
    return datetime.today().date()


class ReportTemplateManager:
    """Менеджер пользовательских шаблонов отчётов."""

    def __init__(self, storage_dir: Path | None = None):
        self.storage_dir = storage_dir or USER_DATA_DIR
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.directory_file = self.storage_dir / "_reference_directory.json"
        self.library_file = self.storage_dir / "_reference_library.json"
        if not self.directory_file.exists():
            self.directory_file.write_text("[]", encoding="utf-8")
        if not self.library_file.exists():
            self.library_file.write_text("{}", encoding="utf-8")

    def list_templates(self) -> list[str]:
        return sorted(
            p.stem for p in self.storage_dir.glob("*.json")
            if not p.name.startswith("_")
        )

    def template_path(self, name: str) -> Path:
        safe_name = name.strip().replace(" ", "_")
        return self.storage_dir / f"{safe_name}.json"

    def save_template(self, data: FullReportData, name: str) -> Path:
        path = self.template_path(name)
        with path.open("w", encoding="utf-8") as fp:
            json.dump(asdict(data), fp, ensure_ascii=False, indent=2, default=str)
        if data.reference_profiles:
            self.merge_reference_profiles(data.reference_profiles)
        return path

    def create_template_from_report(
        self,
        name: str,
        data: FullReportData,
        official_context_defaults: OfficialReportContext | None = None,
        include_measurements: bool = False,
        include_attachments: bool = False,
    ) -> FullReportTemplate:
        template_data = deepcopy_report_data(data)
        if not include_measurements:
            template_data.measurements = []
            template_data.geodesic_results = {}
            template_data.calculation_results = {}
            template_data.residual_resource = None
            template_data.angle_measurements = []
            template_data.vertical_deviation_table = []
            template_data.straightness_records = []
            template_data.thickness_measurements = []
            template_data.coating_measurements = []
            template_data.ultrasonic_records = []
            template_data.concrete_strength_records = []
            template_data.protective_layer_records = []
            template_data.vibration_records = []
            template_data.settlement_records = []
            template_data.technical_state = []
            template_data.conclusions = []
            template_data.recommendations = []
        template_data.metadata.report_number = ""
        template_data.metadata.start_date = datetime.today().date()
        template_data.metadata.end_date = datetime.today().date()
        template_data.metadata.approval_date = datetime.today().date()
        if not include_attachments:
            for appendix in template_data.appendices:
                appendix.files = []
        return FullReportTemplate(
            name=name,
            form_data=template_data,
            official_context_defaults=official_context_defaults or OfficialReportContext(),
        )

    def save_full_template(self, template: FullReportTemplate) -> Path:
        path = self.template_path(template.name)
        with path.open("w", encoding="utf-8") as fp:
            json.dump(template.to_dict(), fp, ensure_ascii=False, indent=2, default=str)
        if template.form_data.reference_profiles:
            self.merge_reference_profiles(template.form_data.reference_profiles)
        return path

    def delete_template(self, name: str) -> None:
        path = self.template_path(name)
        if path.exists():
            path.unlink()

    def load_full_template(self, name: str) -> FullReportTemplate:
        path = self.template_path(name)
        if not path.exists():
            raise FileNotFoundError(f"Шаблон '{name}' не найден: {path}")
        with path.open("r", encoding="utf-8") as fp:
            payload = json.load(fp)
        return FullReportTemplate.from_dict(payload, fallback_name=name)

    def load_template(self, name: str) -> FullReportData:
        return self.load_full_template(name).form_data

    def load_reference_profiles(self) -> list[ReferenceProfile]:
        try:
            with self.directory_file.open("r", encoding="utf-8") as fp:
                payload = json.load(fp)
        except (OSError, json.JSONDecodeError):
            return []
        return [self._deserialize_reference_profile(item) for item in payload]

    def save_reference_profiles(self, profiles: list[ReferenceProfile]) -> None:
        data = [asdict(profile) for profile in profiles]
        with self.directory_file.open("w", encoding="utf-8") as fp:
            json.dump(data, fp, ensure_ascii=False, indent=2, default=str)

    def merge_reference_profiles(self, profiles: list[ReferenceProfile]) -> None:
        existing = {profile.name.lower(): profile for profile in self.load_reference_profiles()}
        for profile in profiles or []:
            existing[profile.name.lower()] = profile
        self.save_reference_profiles(list(existing.values()))

    def load_reference_library(self) -> ReferenceLibrary:
        try:
            with self.library_file.open("r", encoding="utf-8") as fp:
                payload = json.load(fp)
        except (OSError, json.JSONDecodeError):
            return ReferenceLibrary()
        return ReferenceLibrary.from_dict(payload)

    def save_reference_library(self, library: ReferenceLibrary) -> None:
        with self.library_file.open("w", encoding="utf-8") as fp:
            json.dump(library.to_dict(), fp, ensure_ascii=False, indent=2, default=str)

    def merge_into_reference_library(self, draft: FullReportDraftState) -> None:
        library = self.load_reference_library()
        if draft.form_data.customer.full_name:
            known = {item.full_name for item in library.customers}
            if draft.form_data.customer.full_name not in known:
                library.customers.append(deepcopy(draft.form_data.customer))
        if draft.form_data.contractor.full_name:
            known = {item.full_name for item in library.contractors}
            if draft.form_data.contractor.full_name not in known:
                library.contractors.append(deepcopy(draft.form_data.contractor))

        specialist_keys = {item.full_name for item in library.specialists}
        for specialist in draft.form_data.specialists:
            if specialist.full_name and specialist.full_name not in specialist_keys:
                library.specialists.append(deepcopy(specialist))
                specialist_keys.add(specialist.full_name)

        equipment_keys = {(item.name, item.serial_number) for item in library.equipment}
        for item in draft.form_data.equipment:
            key = (item.name, item.serial_number)
            if item.name and key not in equipment_keys:
                library.equipment.append(deepcopy(item))
                equipment_keys.add(key)

        for conclusion in draft.form_data.conclusions:
            if conclusion.text and conclusion.text not in library.conclusion_texts:
                library.conclusion_texts.append(conclusion.text)

        appendix_titles = {item.title for item in library.appendices}
        for appendix in draft.form_data.appendices:
            if appendix.title and appendix.title not in appendix_titles:
                library.appendices.append(
                    Appendix(title=appendix.title, description=appendix.description, files=[])
                )
                appendix_titles.add(appendix.title)

        recommendation_texts = {item.text for item in library.recommendations}
        for item in draft.form_data.recommendations:
            if item.text and item.text not in recommendation_texts:
                library.recommendations.append(deepcopy(item))
                recommendation_texts.add(item.text)

        self.save_reference_library(library)

    def build_draft_from_template(
        self,
        template_name: str,
        processed_data: dict[str, Any],
        raw_data: pd.DataFrame | None = None,
        import_context: dict[str, Any] | None = None,
        import_diagnostics: dict[str, Any] | None = None,
    ) -> FullReportDraftState:
        template = self.load_full_template(template_name)
        directory_profiles = self.load_reference_profiles()
        if directory_profiles:
            existing = {profile.name.lower(): profile for profile in template.form_data.reference_profiles}
            for profile in directory_profiles:
                if profile.name.lower() not in existing:
                    template.form_data.reference_profiles.append(profile)
        assembler = ReportDataAssembler(
            processed_data,
            raw_data,
            template.form_data.reference_profiles,
            import_context=import_context,
            import_diagnostics=import_diagnostics,
        )
        form_data = assembler.fill_measurement_sections(deepcopy_report_data(template.form_data))
        official_context = assembler.build_official_context(form_data, template.official_context_defaults)
        return FullReportDraftState(
            form_data=form_data,
            selected_template=template_name,
            official_context=official_context,
        )

    @staticmethod
    def _deserialize_reference_profile(item: dict[str, Any]) -> ReferenceProfile:
        instruments = []
        for inst in item.get("instruments", []) or []:
            instruments.append(
                EquipmentEntry(
                    name=inst.get("name", ""),
                    serial_number=inst.get("serial_number", ""),
                    certificate=inst.get("certificate", ""),
                    valid_until=_safe_parse_date(inst.get("valid_until")),
                )
            )
        return ReferenceProfile(
            name=item.get("name", ""),
            role=item.get("role"),
            instruments=instruments,
            certificates=item.get("certificates", []),
            contacts=item.get("contacts", {}),
        )


def build_report_data_from_template(
    template_manager: ReportTemplateManager,
    template_name: str,
    processed_data: dict[str, Any],
    raw_data: pd.DataFrame | None = None,
) -> FullReportData:
    """Загружает шаблон и автоматически подставляет актуальные данные измерений."""
    template = template_manager.load_template(template_name)
    directory_profiles = template_manager.load_reference_profiles()
    if directory_profiles:
        existing = {profile.name.lower(): profile for profile in template.reference_profiles}
        for profile in directory_profiles:
            if profile.name.lower() not in existing:
                template.reference_profiles.append(profile)
    assembler = ReportDataAssembler(processed_data, raw_data, template.reference_profiles)
    return assembler.fill_measurement_sections(template)


class ReportDataAssembler:
    """Заполняет динамические поля отчёта на основе расчётов."""

    def __init__(
        self,
        processed_data: dict[str, Any],
        raw_data: pd.DataFrame | None = None,
        reference_profiles: list[ReferenceProfile] | None = None,
        import_context: dict[str, Any] | None = None,
        import_diagnostics: dict[str, Any] | None = None,
        tower_blueprint=None,
        angular_measurements: dict[str, Any] | None = None,
    ):
        self.processed = processed_data or {}
        self.raw = raw_data
        self.import_context = import_context or {}
        self.import_diagnostics = import_diagnostics or {}
        self.tower_blueprint = tower_blueprint
        self.angular_measurements = angular_measurements or {}
        self.reference_profiles = {
            profile.name.lower(): profile for profile in (reference_profiles or [])
        }
        self._default_annex_map = [
            ("Приложение А", "Перечень нормативно-технической документации"),
            ("Приложение Б", "Термины и определения"),
            ("Приложение Г", "Копии документов"),
            ("Приложение Д", "Фотографические материалы"),
            ("Приложение Е", "Ведомость дефектов и повреждений"),
            ("Приложение Ж", "Расчёт остаточного ресурса сооружения"),
            ("Приложение И", "Графические материалы"),
            ("Приложение К", "Протоколы испытаний материалов"),
            ("Приложение Л", "Протокол геодезических измерений"),
            ("Приложение М", "Поверочный расчёт строительных конструкций"),
        ]

    def fill_measurement_sections(self, report: FullReportData) -> FullReportData:
        report = self.synchronize_identity_fields(report)
        report.geodesic_results = self._build_verticality_section() or dict(report.geodesic_results or {})
        report.calculation_results = self._build_calculation_section() or dict(report.calculation_results or {})
        import_quality = self._build_import_quality_section()
        if import_quality:
            report.geodesic_results["import_quality"] = import_quality
        if not report.measurements:
            report.measurements = self._build_measurement_summaries()
        if not report.residual_resource:
            report.residual_resource = self._build_residual_resource()
        if not report.title_object:
            report.title_object = self._build_title_object(report)
        if not report.vertical_deviation_table:
            report.vertical_deviation_table = self._build_verticality_records()
        if not report.straightness_records:
            report.straightness_records = self._build_straightness_records()
        if not report.annexes:
            report.annexes = self._build_default_annexes()
        if not report.object_list:
            report.object_list = self._build_object_list(report)
        if not report.documents_review:
            report.documents_review = self._build_documents_review(report)
        if not report.technical_state:
            report.technical_state = self._build_technical_state(report)
        if not report.conclusions:
            report.conclusions = self._build_conclusions(report)
        if not report.angle_measurements and self.angular_measurements:
            report.angle_measurements = self._build_angle_measurements_from_data()
        if not report.normative_list:
            report.normative_list = self._build_normative_list()
        if self.tower_blueprint is not None:
            self._apply_blueprint_data(report)
        self._apply_reference_profiles(report)
        return report

    def synchronize_identity_fields(self, report: FullReportData) -> FullReportData:
        metadata = report.metadata
        first_object = report.object_list[0] if report.object_list else None

        if not metadata.customer_name and report.customer.full_name:
            metadata.customer_name = report.customer.full_name
        if not metadata.operator_name and report.contractor.full_name:
            metadata.operator_name = report.contractor.full_name
        if not metadata.project_name and first_object and first_object.name:
            metadata.project_name = first_object.name
        if not metadata.inventory_number and first_object and first_object.inventory_number:
            metadata.inventory_number = first_object.inventory_number
        if not metadata.location:
            metadata.location = self._first_text(
                first_object.location if first_object else None,
                report.customer.actual_address,
                report.contractor.postal_address,
                report.contractor.legal_address,
            )

        title = report.title_object or TitleObjectInfo(
            name="",
            inventory_number="",
            operator="",
            location="",
            city="",
            year=metadata.approval_date.year if metadata.approval_date else datetime.today().year,
        )
        title.name = self._first_text(title.name, metadata.project_name, first_object.name if first_object else None)
        title.inventory_number = self._first_text(
            title.inventory_number,
            metadata.inventory_number,
            first_object.inventory_number if first_object else None,
        )
        title.operator = self._first_text(
            title.operator,
            metadata.customer_name,
            report.customer.full_name,
            metadata.operator_name,
        )
        title.location = self._first_text(
            title.location,
            metadata.location,
            first_object.location if first_object else None,
            report.customer.actual_address,
        )
        title.city = self._first_text(
            title.city,
            metadata.approval_city,
            self._extract_city(title.location),
            self._extract_city(report.customer.actual_address),
        )
        if not title.year:
            title.year = metadata.approval_date.year if metadata.approval_date else datetime.today().year
        report.title_object = title

        if report.object_list:
            normalized_objects: list[InspectedObject] = []
            for index, item in enumerate(report.object_list):
                if index == 0:
                    normalized_objects.append(
                        InspectedObject(
                            name=self._first_text(item.name, metadata.project_name, title.name),
                            inventory_number=self._first_text(
                                item.inventory_number,
                                metadata.inventory_number,
                                title.inventory_number,
                            )
                            or None,
                            commissioning_year=item.commissioning_year or title.year or None,
                            location=self._first_text(item.location, metadata.location, title.location) or None,
                            notes=item.notes
                            or (
                                f"Эксплуатирующая организация: {title.operator}"
                                if title.operator
                                else None
                            ),
                        )
                    )
                    continue
                normalized_objects.append(item)
            report.object_list = normalized_objects

        return report

    def _build_import_quality_section(self) -> dict[str, Any]:
        diagnostics = self.import_diagnostics or self.processed.get("import_diagnostics") or {}
        import_context = self.import_context or self.processed.get("import_context") or {}
        if not diagnostics and not import_context:
            return {}
        return {
            "source_format": import_context.get("source_format") or diagnostics.get("source_format"),
            "parser_strategy": import_context.get("parser_strategy") or diagnostics.get("parser_strategy"),
            "confidence": import_context.get("confidence", diagnostics.get("confidence")),
            "warnings": import_context.get("warnings") or diagnostics.get("warnings", []),
            "raw_records": diagnostics.get("raw_records"),
            "accepted_points": diagnostics.get("accepted_points"),
            "discarded_points": diagnostics.get("discarded_points"),
            "fallback_chain": diagnostics.get("fallback_chain", []),
            "paired_exports": diagnostics.get("details", {}).get("paired_exports", []),
            "transformation_audit": self.processed.get("transformation_audit") or {},
        }

    def _build_verticality_section(self) -> dict[str, Any]:
        centers = self.processed.get("centers")
        if not isinstance(centers, pd.DataFrame) or centers.empty:
            return {}

        summary = {
            "total_levels": len(centers),
            "max_deviation_mm": float((centers["deviation"].abs().max() * 1000).round(2)),
            "mean_deviation_mm": float((centers["deviation"].abs().mean() * 1000).round(2)),
            "levels": [],
        }

        for idx, row in centers.iterrows():
            summary["levels"].append(
                {
                    "index": idx + 1,
                    "height_m": float(row.get("z", 0.0)),
                    "deviation_mm": float(row.get("deviation", 0.0) * 1000),
                    "points": int(row.get("points_count", 0)) if not pd.isna(row.get("points_count", 0)) else 0,
                }
            )
        return summary

    def _build_calculation_section(self) -> dict[str, Any]:
        summary = self.processed.get("straightness_summary")
        if isinstance(summary, dict):
            max_deflection_mm = float(summary.get("max_deflection_mm", 0.0))
            if max_deflection_mm > 0:
                return {"max_straightness_mm": max_deflection_mm}

        centers = self.processed.get("centers")
        if isinstance(centers, pd.DataFrame) and not centers.empty and "straightness_deviation" in centers.columns:
            deviation_mm = (centers["straightness_deviation"].abs() * 1000).dropna()
            if not deviation_mm.empty and deviation_mm.max() > 0:
                return {"max_straightness_mm": float(deviation_mm.max())}
        return {}

    def _build_measurement_summaries(self) -> list[MeasurementSummary]:
        measurements = []
        if "thickness_summary" in self.processed:
            measurements.append(
                MeasurementSummary(
                    method="Толщинометрия металлоконструкций",
                    standard="ГОСТ Р 55614-2013",
                    result=self.processed["thickness_summary"],
                )
            )
        if "coating_summary" in self.processed:
            measurements.append(
                MeasurementSummary(
                    method="Контроль лакокрасочного покрытия",
                    standard="ГОСТ 31993-2013",
                    result=self.processed["coating_summary"],
                )
            )
        return measurements

    def _build_residual_resource(self) -> ResidualResourceResult | None:
        resource = self.processed.get("residual_resource")
        if not resource:
            return None
        return ResidualResourceResult(
            satisfies_requirements=bool(resource.get("ok", True)),
            residual_years=float(resource.get("years", 0)),
            notes=resource.get("notes", ""),
        )

    def build_official_context(
        self,
        report: FullReportData,
        defaults: OfficialReportContext | None = None,
    ) -> OfficialReportContext:
        defaults = defaults or OfficialReportContext()
        report = self.synchronize_identity_fields(report)
        object_name = report.title_object.name if report.title_object else report.metadata.project_name
        locality = self._first_text(
            defaults.locality,
            report.metadata.location,
            report.title_object.location if report.title_object else None,
        )
        performer = defaults.performer or report.metadata.operator_name or report.contractor.full_name
        instrument = defaults.instrument
        if not instrument and report.equipment:
            instrument = report.equipment[0].name

        structure_type = defaults.structure_type or "tower"
        import_tower_type = str(self.import_context.get("tower_type", "")).lower()
        if import_tower_type in {"mast", "tower", "odn"}:
            structure_type = import_tower_type

        commissioning_year = defaults.commissioning_year
        current_year = datetime.today().year
        if (commissioning_year is None or commissioning_year == current_year) and report.title_object:
            commissioning_year = report.title_object.year

        derived_stations = self.collect_station_entries()
        stations = defaults.stations or derived_stations
        base_station = self._first_text(
            defaults.base_station,
            stations[0].name if stations else None,
            object_name,
        )

        survey_date = defaults.survey_date
        if survey_date == datetime.today().date() and report.metadata.end_date:
            survey_date = report.metadata.end_date

        return OfficialReportContext(
            structure_type=structure_type,
            base_station=base_station,
            project_code=self._first_text(defaults.project_code, report.metadata.inventory_number),
            locality=locality,
            survey_date=survey_date,
            performer=performer,
            reviewer=defaults.reviewer,
            instrument=instrument,
            weather=defaults.weather,
            wind=defaults.wind,
            measurement_reason=defaults.measurement_reason,
            commissioning_year=commissioning_year,
            decision_comment=defaults.decision_comment,
            stations=stations,
        )

    def _build_verticality_records(self) -> list[VerticalDeviationRecord]:
        centers = self.processed.get("centers")
        if isinstance(centers, pd.DataFrame) and not centers.empty:
            records: list[VerticalDeviationRecord] = []
            for idx, (_, row) in enumerate(centers.reset_index(drop=True).iterrows(), start=1):
                deviation_mm = self._to_mm(row.get("deviation"))
                records.append(
                    VerticalDeviationRecord(
                        section_number=idx,
                        height_m=float(row.get("z", 0.0)),
                        deviation_previous_mm=None,
                        deviation_current_mm=deviation_mm,
                    )
                )
            return records
        return []

    def _build_straightness_records(self) -> list[StraightnessRecord]:
        profiles = self.processed.get("straightness_profiles")
        if isinstance(profiles, list) and profiles:
            records: list[StraightnessRecord] = []
            for profile in profiles:
                belt_number = int(profile.get("belt", 0))
                tolerance_mm = float(profile.get("tolerance_mm", 0.0))
                for point in profile.get("points", []):
                    records.append(
                        StraightnessRecord(
                            belt_number=belt_number,
                            height_m=float(point.get("z", 0.0)),
                            deviation_mm=float(point.get("deflection_mm", 0.0)),
                            tolerance_mm=tolerance_mm,
                        )
                    )
            records.sort(key=lambda item: (item.belt_number, item.height_m))
            return records

        centers = self.processed.get("centers")
        if isinstance(centers, pd.DataFrame) and not centers.empty:
            records: list[StraightnessRecord] = []
            for idx, (_, row) in enumerate(centers.reset_index(drop=True).iterrows(), start=1):
                deviation = self._to_mm(row.get("straightness_deviation"))
                tolerance = self._to_mm(row.get("section_length")) / 750 if row.get("section_length") else 0.0
                records.append(
                    StraightnessRecord(
                        belt_number=idx,
                        height_m=float(row.get("z", 0.0)),
                        deviation_mm=deviation or 0.0,
                        tolerance_mm=tolerance or 0.0,
                    )
                )
            return records
        return []

    def _build_angle_measurements_from_data(self) -> list[AngleMeasurementRecord]:
        records = []
        idx = 1
        for axis_key in ("x", "y"):
            rows = self.angular_measurements.get(axis_key, [])
            for row in rows:
                records.append(AngleMeasurementRecord(
                    index=idx,
                    section=str(row.get("section", "")),
                    height_m=float(row.get("height", 0.0)),
                    belt=str(row.get("belt", "")),
                    kl_arcsec=row.get("kl_sec"),
                    kr_arcsec=row.get("kr_sec"),
                    diff_arcsec=row.get("diff_sec"),
                    beta_measured=row.get("center_sec"),
                    center_value=row.get("center_sec"),
                    delta_beta=row.get("delta_sec"),
                    delta_mm=row.get("delta_mm"),
                ))
                idx += 1
        return records

    def _apply_blueprint_data(self, report: FullReportData) -> None:
        bp = self.tower_blueprint
        if bp is None:
            return

        segments = getattr(bp, "segments", None)
        if not segments:
            sections_legacy = getattr(bp, "sections", None)
            if sections_legacy:
                self._apply_legacy_blueprint(report, bp)
            return

        total_height = bp.total_height() if callable(getattr(bp, "total_height", None)) else sum(s.height for s in segments)
        faces = segments[0].faces if segments else 4
        base_size = segments[0].base_size if segments else 0
        top_size = getattr(segments[-1], "top_size", None) or segments[-1].base_size if segments else 0
        shape_map = {"prism": "призма", "truncated_pyramid": "усечённая пирамида", "cylinder": "цилиндр"}
        shape_name = shape_map.get(segments[0].shape, segments[0].shape) if segments else "призма"

        if not report.structural_elements:
            elements = []
            cumulative_height = 0.0
            for seg in segments:
                for sec in (seg.sections or []):
                    cumulative_height += sec.height
                    profile_info = sec.profile_spec or seg.profile_spec or {}
                    profile_str = ", ".join(f"{k}: {v}" for k, v in profile_info.items()) if profile_info else ""
                    lattice = sec.lattice_type or seg.lattice_type or "cross"
                    elements.append(StructuralElement(
                        section=f"{seg.name} / отм. {cumulative_height:.1f} м",
                        element=sec.name,
                        material=profile_info.get("material", "Ст3"),
                        parameters=profile_str,
                        notes=f"решётка: {lattice}",
                    ))
                if not seg.sections:
                    cumulative_height += seg.height
                    profile_info = seg.profile_spec or {}
                    profile_str = ", ".join(f"{k}: {v}" for k, v in profile_info.items()) if profile_info else ""
                    elements.append(StructuralElement(
                        section=f"{seg.name} / H={seg.height:.1f} м",
                        element=f"{seg.name} ({shape_map.get(seg.shape, seg.shape)})",
                        material=profile_info.get("material", "Ст3"),
                        parameters=profile_str,
                        notes=f"{seg.faces}-гранная, решётка: {seg.lattice_type}",
                    ))
            report.structural_elements = elements

        if report.structure and not report.structure.structural_scheme:
            scheme_parts = [
                f"{faces}-гранная {shape_name}",
                f"высота {total_height:.1f} м",
                f"{len(segments)} частей",
                f"основание {base_size:.1f} м",
            ]
            if top_size and top_size != base_size:
                scheme_parts.append(f"верх {top_size:.1f} м")
            report.structure.structural_scheme = ", ".join(scheme_parts)

        if report.structure and not report.structure.metal_structure:
            metal_parts = []
            for seg in segments:
                profile = seg.profile_spec or {}
                profile_str = ", ".join(f"{k}={v}" for k, v in profile.items()) if profile else "не указан"
                metal_parts.append(f"{seg.name}: {seg.faces}-гранная {shape_map.get(seg.shape, seg.shape)}, "
                                   f"H={seg.height:.1f} м, профиль: {profile_str}")
            report.structure.metal_structure = "; ".join(metal_parts)

    def _apply_legacy_blueprint(self, report: FullReportData, bp) -> None:
        sections = getattr(bp, "sections", [])
        total_height = getattr(bp, "total_height", 0)
        if callable(total_height):
            total_height = total_height()
        faces = getattr(bp, "faces", 4)
        base_size = getattr(bp, "base_size", 0)
        top_size = getattr(bp, "top_size", base_size)
        tower_type = getattr(bp, "tower_type", "prism")
        shape_map = {"prism": "призма", "truncated_pyramid": "усечённая пирамида", "cylinder": "цилиндр"}
        shape_name = shape_map.get(tower_type, tower_type)

        if not report.structural_elements and sections:
            elements = []
            cumulative_height = 0.0
            for sec in sections:
                cumulative_height += sec.height
                elements.append(StructuralElement(
                    section=f"Секция {sec.name} / отм. {cumulative_height:.1f} м",
                    element=sec.name,
                    material="Ст3",
                    parameters="",
                    notes=f"решётка: {getattr(sec, 'lattice_type', 'cross')}",
                ))
            report.structural_elements = elements

        if report.structure and not report.structure.structural_scheme:
            report.structure.structural_scheme = (
                f"{faces}-гранная {shape_name}, высота {total_height:.1f} м, "
                f"{len(sections)} секций, основание {base_size:.1f} м, верх {top_size:.1f} м"
            )

    def _build_normative_list(self) -> list[str]:
        from core.normatives import get_normatives_for_structure, format_normative_list
        structure_type = str(self.import_context.get("tower_type", "tower")).lower()
        if structure_type not in ("tower", "mast", "odn"):
            structure_type = "tower"
        docs = get_normatives_for_structure(structure_type)
        return format_normative_list(docs)

    def _build_default_annexes(self) -> list[AnnexEntry]:
        return [
            AnnexEntry(code=code, title=title, description=None, pages=[])
            for code, title in self._default_annex_map
        ]

    def _build_documents_review(self, report: FullReportData) -> list[DocumentReviewEntry]:
        reviews: list[DocumentReviewEntry] = []
        for document in report.documents:
            summary_parts = []
            if document.comments:
                summary_parts.append(document.comments)
            if report.metadata.project_name:
                summary_parts.append(f"Используется при подготовке отчёта {report.metadata.project_name}.")
            summary = " ".join(summary_parts).strip()
            reviews.append(
                DocumentReviewEntry(
                    title=document.title,
                    identifier=document.identifier,
                    summary=summary or "Документ учтён при анализе нормативной и технической документации.",
                    conclusion="Соответствует требованиям технического задания.",
                )
            )
        if not reviews:
            reviews.append(
                DocumentReviewEntry(
                    title="Техническое задание на обследование",
                    identifier=report.metadata.report_number,
                    summary=f"Сформировано на основании данных проекта {report.metadata.project_name}.",
                    conclusion="Материалы заказчика приняты без замечаний.",
                )
            )
        return reviews

    def _build_technical_state(self, report: FullReportData) -> list[TechnicalStateEntry]:
        entries: list[TechnicalStateEntry] = []
        deviation = report.geodesic_results.get("max_deviation_mm")
        if deviation is not None:
            classification = "Работоспособное" if deviation <= 50 else "Требует внимания"
            entries.append(
                TechnicalStateEntry(
                    structure="Геодезические параметры",
                    classification=classification,
                    comments=f"Максимальное отклонение ствола {deviation:.1f} мм.",
                )
            )
        if report.residual_resource:
            classification = (
                "Работоспособное" if report.residual_resource.satisfies_requirements else "Ограниченно-работоспособное"
            )
            entries.append(
                TechnicalStateEntry(
                    structure="Несущая способность",
                    classification=classification,
                    comments=f"Расчётный остаточный ресурс {report.residual_resource.residual_years:.0f} лет.",
                )
            )
        if not entries:
            entries.append(
                TechnicalStateEntry(
                    structure="Техническое состояние конструкции",
                    classification="Работоспособное",
                    comments="Данные обследования соответствуют требованиям ГОСТ 31937-2011.",
                )
            )
        return entries

    def _build_conclusions(self, report: FullReportData) -> list[ConclusionEntry]:
        conclusions: list[ConclusionEntry] = []
        if report.technical_state:
            classification = report.technical_state[0].classification
            conclusions.append(
                ConclusionEntry(
                    label="Техническое состояние",
                    text=f"Общее техническое состояние конструкций оценивается как {classification.lower()}.",
                )
            )
        if report.residual_resource:
            status = "обеспечивает безопасную эксплуатацию" if report.residual_resource.satisfies_requirements else "требует дополнительных расчётов"
            conclusions.append(
                ConclusionEntry(
                    label="Остаточный ресурс",
                    text=(
                        f"Расчёт остаточного ресурса показывает, что сооружение {status}. "
                        f"Прогнозируемый ресурс — {report.residual_resource.residual_years:.0f} лет."
                    ),
                )
            )
        if report.geodesic_results.get("max_deviation_mm") is not None:
            deviation = report.geodesic_results["max_deviation_mm"]
            conclusions.append(
                ConclusionEntry(
                    label="Геодезические измерения",
                    text=f"Максимальное отклонение ствола составило {deviation:.1f} мм, что сопоставимо с допуском СП 70.13330.2012.",
                )
            )
        if not conclusions:
            conclusions.append(
                ConclusionEntry(
                    label="Общие выводы",
                    text="По результатам обследования конструкция может эксплуатироваться в штатном режиме.",
                )
            )
        return conclusions

    def collect_station_entries(self) -> list[SurveyStationEntry]:
        return self._build_station_entries_from_context()

    def _build_station_entries_from_context(self) -> list[SurveyStationEntry]:
        point_entries = self._build_station_entries_from_points()
        if point_entries:
            return point_entries

        stations: list[SurveyStationEntry] = []
        transformation = self.processed.get("transformation_audit") or {}
        source_file = self.import_context.get("source_file")
        if source_file:
            stations.append(
                SurveyStationEntry(
                    name="Основная съемка",
                    distance_m=transformation.get("base_distance_m"),
                    note=str(source_file),
                )
            )
        second_source = transformation.get("second_station_source")
        if second_source:
            stations.append(
                SurveyStationEntry(
                    name="Вторая станция",
                    distance_m=transformation.get("second_station_distance_m"),
                    note=str(second_source),
                )
            )
        return stations

    def _build_station_entries_from_points(self) -> list[SurveyStationEntry]:
        if not isinstance(self.raw, pd.DataFrame) or self.raw.empty or "is_station" not in self.raw.columns:
            return []

        station_mask = self.raw["is_station"].fillna(False).astype(bool)
        station_points = self.raw[station_mask].copy()
        if station_points.empty:
            return []

        reference_xy = self._resolve_station_reference_xy(station_mask)
        transformation = self.processed.get("transformation_audit") or {}
        audit_distances = [
            transformation.get("base_distance_m"),
            transformation.get("second_station_distance_m"),
        ]

        stations: list[SurveyStationEntry] = []
        for order, (_, row) in enumerate(station_points.reset_index(drop=True).iterrows(), start=1):
            distance_m = self._safe_float(row.get("distance_to_tower"))
            if distance_m is None and reference_xy is not None:
                x = self._safe_float(row.get("x"))
                y = self._safe_float(row.get("y"))
                if x is not None and y is not None:
                    distance_m = math.hypot(x - reference_xy[0], y - reference_xy[1])
            if distance_m is None and order - 1 < len(audit_distances):
                distance_m = self._safe_float(audit_distances[order - 1])

            name = self._first_text(
                row.get("name"),
                row.get("station"),
                f"Стоянка {order}",
            )
            note_parts: list[str] = []
            source = self._first_text(row.get("source_file"), row.get("source"))
            if source:
                note_parts.append(source)
            z_value = self._safe_float(row.get("z"))
            if z_value is not None:
                note_parts.append(f"Z={z_value:.3f} м")
            stations.append(
                SurveyStationEntry(
                    name=name,
                    distance_m=distance_m,
                    note="; ".join(note_parts),
                )
            )
        return stations

    def _resolve_station_reference_xy(self, station_mask: pd.Series) -> tuple[float, float] | None:
        if not isinstance(self.raw, pd.DataFrame) or self.raw.empty:
            return None

        tower_points = self.raw.loc[~station_mask].copy()
        if {"x", "y"}.issubset(tower_points.columns):
            tower_points = tower_points.dropna(subset=["x", "y"])
            if not tower_points.empty:
                return (float(tower_points["x"].mean()), float(tower_points["y"].mean()))

        centers = self.processed.get("centers")
        if isinstance(centers, pd.DataFrame) and {"x", "y"}.issubset(centers.columns):
            centers = centers.dropna(subset=["x", "y"])
            if not centers.empty:
                return (float(centers["x"].mean()), float(centers["y"].mean()))
        return None

    def _build_title_object(self, report: FullReportData) -> TitleObjectInfo:
        metadata = report.metadata
        city = metadata.approval_city or (report.customer.actual_address.split(",")[0] if report.customer.actual_address else "")
        return TitleObjectInfo(
            name=metadata.project_name or metadata.customer_name,
            inventory_number=metadata.inventory_number or "—",
            operator=metadata.customer_name or report.customer.full_name or metadata.operator_name,
            location=metadata.location or report.customer.actual_address,
            city=city,
            year=metadata.approval_date.year if metadata.approval_date else datetime.today().year,
        )

    def _build_object_list(self, report: FullReportData) -> list[InspectedObject]:
        metadata = report.metadata
        title = report.title_object or self._build_title_object(report)
        entry = InspectedObject(
            name=metadata.project_name or title.name,
            inventory_number=metadata.inventory_number or None,
            commissioning_year=None,
            location=metadata.location or title.location or report.customer.actual_address,
            notes=f"Эксплуатирующая организация: {title.operator or report.customer.full_name}",
        )
        return [entry]

    @staticmethod
    def _to_mm(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value) * 1000.0
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _first_text(*values: Any) -> str:
        for value in values:
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return text
        return ""

    @staticmethod
    def _extract_city(value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        return text.split(",")[0].strip()

    @staticmethod
    def _safe_float(value: Any) -> float | None:
        try:
            if value in (None, ""):
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    def _apply_reference_profiles(self, report: FullReportData) -> None:
        if not self.reference_profiles:
            return
        existing = {profile.name.lower(): profile for profile in report.reference_profiles}
        for key, profile in self.reference_profiles.items():
            if key not in existing:
                report.reference_profiles.append(profile)
            else:
                target = existing[key]
                if not target.role and profile.role:
                    target.role = profile.role
                if not target.certificates and profile.certificates:
                    target.certificates = profile.certificates
                if not target.contacts and profile.contacts:
                    target.contacts = profile.contacts
                if profile.instruments:
                    target_instruments = {(inst.name, inst.serial_number) for inst in target.instruments}
                    for instrument in profile.instruments:
                        if (instrument.name, instrument.serial_number) not in target_instruments:
                            target.instruments.append(instrument)

        existing_equipment = {(eq.name, eq.serial_number) for eq in report.equipment}
        for profile in report.reference_profiles:
            for instrument in profile.instruments:
                key = (instrument.name, instrument.serial_number)
                if key not in existing_equipment:
                    report.equipment.append(instrument)
                    existing_equipment.add(key)

        for specialist in report.specialists:
            profile = self.reference_profiles.get(specialist.full_name.lower())
            if not profile:
                continue
            if (not specialist.certifications) and profile.certificates:
                parsed = {}
                for idx, cert in enumerate(profile.certificates, start=1):
                    if ":" in cert:
                        area, value = cert.split(":", 1)
                        parsed[area.strip()] = value.strip()
                    else:
                        parsed[f"ref_{idx}"] = cert.strip()
                specialist.certifications = parsed


__all__ = [
    "ReportDataAssembler",
    "ReportTemplateManager",
    "build_report_data_from_template",
]


