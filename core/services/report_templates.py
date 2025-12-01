"""
Управление шаблонами отчётов и автоматическое наполнение данных.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

import pandas as pd

from core.report_schema import (
    AnnexEntry,
    ConclusionEntry,
    EquipmentEntry,
    FullReportData,
    InspectedObject,
    MeasurementSummary,
    ReferenceProfile,
    ResidualResourceResult,
    TechnicalStateEntry,
    TitleObjectInfo,
    VerticalDeviationRecord,
    StraightnessRecord,
    DocumentReviewEntry,
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
        if not self.directory_file.exists():
            self.directory_file.write_text("[]", encoding="utf-8")

    def list_templates(self) -> List[str]:
        return sorted(p.stem for p in self.storage_dir.glob("*.json"))

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

    def load_template(self, name: str) -> FullReportData:
        path = self.template_path(name)
        if not path.exists():
            raise FileNotFoundError(f"Шаблон '{name}' не найден: {path}")
        with path.open("r", encoding="utf-8") as fp:
            payload = json.load(fp)
        return FullReportData.from_dict(payload)

    def delete_template(self, name: str) -> None:
        path = self.template_path(name)
        if path.exists():
            path.unlink()

    def load_reference_profiles(self) -> List[ReferenceProfile]:
        try:
            with self.directory_file.open("r", encoding="utf-8") as fp:
                payload = json.load(fp)
        except (OSError, json.JSONDecodeError):
            return []
        return [self._deserialize_reference_profile(item) for item in payload]

    def save_reference_profiles(self, profiles: List[ReferenceProfile]) -> None:
        data = [asdict(profile) for profile in profiles]
        with self.directory_file.open("w", encoding="utf-8") as fp:
            json.dump(data, fp, ensure_ascii=False, indent=2, default=str)

    def merge_reference_profiles(self, profiles: List[ReferenceProfile]) -> None:
        existing = {profile.name.lower(): profile for profile in self.load_reference_profiles()}
        for profile in profiles or []:
            existing[profile.name.lower()] = profile
        self.save_reference_profiles(list(existing.values()))

    @staticmethod
    def _deserialize_reference_profile(item: Dict[str, Any]) -> ReferenceProfile:
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
    processed_data: Dict[str, Any],
    raw_data: Optional[pd.DataFrame] = None,
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
        processed_data: Dict[str, Any],
        raw_data: Optional[pd.DataFrame] = None,
        reference_profiles: Optional[List[ReferenceProfile]] = None,
    ):
        self.processed = processed_data or {}
        self.raw = raw_data
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
        report.geodesic_results = self._build_verticality_section()
        report.calculation_results = self._build_calculation_section()
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
        self._apply_reference_profiles(report)
        return report

    def _build_verticality_section(self) -> Dict[str, Any]:
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

    def _build_calculation_section(self) -> Dict[str, Any]:
        straightness = self.processed.get("straightness")
        if isinstance(straightness, pd.DataFrame) and not straightness.empty:
            max_dev = float(abs(straightness["deviation_mm"]).max())
            return {"max_straightness_mm": max_dev, "segments": straightness.to_dict(orient="records")}
        return {}

    def _build_measurement_summaries(self) -> List[MeasurementSummary]:
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

    def _build_residual_resource(self) -> Optional[ResidualResourceResult]:
        resource = self.processed.get("residual_resource")
        if not resource:
            return None
        return ResidualResourceResult(
            satisfies_requirements=bool(resource.get("ok", True)),
            residual_years=float(resource.get("years", 0)),
            notes=resource.get("notes", ""),
        )

    def _build_title_object(self, report: FullReportData) -> TitleObjectInfo:
        metadata = report.metadata
        city = metadata.approval_city or (report.customer.actual_address.split(",")[0] if report.customer.actual_address else "")
        return TitleObjectInfo(
            name=metadata.project_name or metadata.customer_name,
            inventory_number=metadata.inventory_number or "—",
            operator=metadata.operator_name or report.customer.full_name,
            location=metadata.location or report.customer.actual_address,
            city=city,
            year=metadata.approval_date.year if metadata.approval_date else datetime.today().year,
        )

    def _build_verticality_records(self) -> List[VerticalDeviationRecord]:
        centers = self.processed.get("centers")
        if isinstance(centers, pd.DataFrame) and not centers.empty:
            records: List[VerticalDeviationRecord] = []
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

    def _build_straightness_records(self) -> List[StraightnessRecord]:
        centers = self.processed.get("centers")
        if isinstance(centers, pd.DataFrame) and not centers.empty:
            records: List[StraightnessRecord] = []
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

    def _build_default_annexes(self) -> List[AnnexEntry]:
        return [
            AnnexEntry(code=code, title=title, description=None, pages=[])
            for code, title in self._default_annex_map
        ]

    def _build_object_list(self, report: FullReportData) -> List[InspectedObject]:
        metadata = report.metadata
        entry = InspectedObject(
            name=metadata.project_name,
            inventory_number=metadata.inventory_number or None,
            commissioning_year=None,
            location=metadata.location or report.customer.actual_address,
            notes=f"Эксплуатирующая организация: {metadata.operator_name or report.customer.full_name}",
        )
        return [entry]

    def _build_documents_review(self, report: FullReportData) -> List[DocumentReviewEntry]:
        reviews: List[DocumentReviewEntry] = []
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

    def _build_technical_state(self, report: FullReportData) -> List[TechnicalStateEntry]:
        entries: List[TechnicalStateEntry] = []
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

    def _build_conclusions(self, report: FullReportData) -> List[ConclusionEntry]:
        conclusions: List[ConclusionEntry] = []
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

    @staticmethod
    def _to_mm(value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value) * 1000.0
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
    "ReportTemplateManager",
    "ReportDataAssembler",
    "build_report_data_from_template",
]


