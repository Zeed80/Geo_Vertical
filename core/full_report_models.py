from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any

from core.report_schema import (
    Appendix,
    ContractorInfo,
    CustomerInfo,
    EquipmentEntry,
    FullReportData,
    Recommendation,
    Specialist,
)


def _parse_date(value: Any, default: date | None = None) -> date:
    if isinstance(value, date):
        return value
    if isinstance(value, datetime):
        return value.date()
    if value in (None, "", "null"):
        return default or date.today()
    if isinstance(value, str):
        for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue
        return datetime.fromisoformat(value).date()
    return default or date.today()


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    if value in (None, "", "null"):
        return None
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def create_empty_full_report_data() -> FullReportData:
    today = date.today()
    return FullReportData.from_dict(
        {
            "metadata": {
                "report_number": "",
                "project_name": "",
                "inventory_number": "",
                "location": "",
                "customer_name": "",
                "operator_name": "",
                "start_date": today.isoformat(),
                "end_date": today.isoformat(),
                "approval_person": "",
                "approval_position": "",
                "approval_city": "",
                "approval_date": today.isoformat(),
            },
            "customer": {
                "full_name": "",
                "director": "",
                "legal_address": "",
                "actual_address": "",
                "phone": "",
                "email": "",
            },
            "contractor": {
                "full_name": "",
                "director": "",
                "legal_address": "",
                "postal_address": "",
                "phone": "",
                "email": "",
                "accreditation_certificate": "",
                "sro_certificate": "",
            },
        }
    )


@dataclass
class SurveyStationEntry:
    name: str = ""
    distance_m: float | None = None
    note: str = ""

    @staticmethod
    def from_dict(payload: dict[str, Any]) -> SurveyStationEntry:
        value = payload.get("distance_m")
        try:
            distance = float(value) if value not in (None, "") else None
        except (TypeError, ValueError):
            distance = None
        return SurveyStationEntry(
            name=str(payload.get("name", "")),
            distance_m=distance,
            note=str(payload.get("note", "")),
        )


@dataclass
class OfficialReportContext:
    structure_type: str = "tower"
    base_station: str = ""
    project_code: str = ""
    locality: str = ""
    survey_date: date = field(default_factory=date.today)
    performer: str = ""
    reviewer: str = ""
    instrument: str = ""
    weather: str = ""
    wind: str = ""
    measurement_reason: str = ""
    commissioning_year: int | None = None
    decision_comment: str = ""
    stations: list[SurveyStationEntry] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "structure_type": self.structure_type,
            "base_station": self.base_station,
            "project_code": self.project_code,
            "locality": self.locality,
            "survey_date": self.survey_date.isoformat(),
            "performer": self.performer,
            "reviewer": self.reviewer,
            "instrument": self.instrument,
            "weather": self.weather,
            "wind": self.wind,
            "measurement_reason": self.measurement_reason,
            "commissioning_year": self.commissioning_year,
            "decision_comment": self.decision_comment,
            "stations": [asdict(item) for item in self.stations],
        }

    @staticmethod
    def from_dict(payload: dict[str, Any] | None) -> OfficialReportContext:
        payload = payload or {}
        value = payload.get("commissioning_year")
        try:
            commissioning_year = int(value) if value not in (None, "") else None
        except (TypeError, ValueError):
            commissioning_year = None
        return OfficialReportContext(
            structure_type=str(payload.get("structure_type", "tower") or "tower"),
            base_station=str(payload.get("base_station", "")),
            project_code=str(payload.get("project_code", "")),
            locality=str(payload.get("locality", "")),
            survey_date=_parse_date(payload.get("survey_date")),
            performer=str(payload.get("performer", "")),
            reviewer=str(payload.get("reviewer", "")),
            instrument=str(payload.get("instrument", "")),
            weather=str(payload.get("weather", "")),
            wind=str(payload.get("wind", "")),
            measurement_reason=str(payload.get("measurement_reason", "")),
            commissioning_year=commissioning_year,
            decision_comment=str(payload.get("decision_comment", "")),
            stations=[
                SurveyStationEntry.from_dict(item)
                for item in (payload.get("stations") or [])
                if isinstance(item, dict)
            ],
        )


@dataclass
class ValidationIssue:
    section: str
    severity: str
    message: str
    field_path: str = ""
    code: str = ""

    @staticmethod
    def from_dict(payload: dict[str, Any]) -> ValidationIssue:
        return ValidationIssue(
            section=str(payload.get("section", "general")),
            severity=str(payload.get("severity", "warning")),
            message=str(payload.get("message", "")),
            field_path=str(payload.get("field_path", "")),
            code=str(payload.get("code", "")),
        )


@dataclass
class PreviewSettings:
    mode: str = "document"

    @staticmethod
    def from_dict(payload: dict[str, Any] | None) -> PreviewSettings:
        payload = payload or {}
        return PreviewSettings(mode=str(payload.get("mode", "document")))


@dataclass
class AttachmentManifestEntry:
    title: str
    relative_path: str
    source_path: str = ""
    description: str = ""
    include_in_release: bool = True

    @staticmethod
    def from_dict(payload: dict[str, Any]) -> AttachmentManifestEntry:
        return AttachmentManifestEntry(
            title=str(payload.get("title", "")),
            relative_path=str(payload.get("relative_path", "")),
            source_path=str(payload.get("source_path", "")),
            description=str(payload.get("description", "")),
            include_in_release=bool(payload.get("include_in_release", True)),
        )


@dataclass
class ReleaseManifest:
    output_path: str = ""
    exported_at: datetime | None = None
    draft_hash: str = ""
    template_name: str = ""
    included_files: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "output_path": self.output_path,
            "exported_at": self.exported_at.isoformat() if self.exported_at else None,
            "draft_hash": self.draft_hash,
            "template_name": self.template_name,
            "included_files": list(self.included_files),
        }

    @staticmethod
    def from_dict(payload: dict[str, Any] | None) -> ReleaseManifest | None:
        if not payload:
            return None
        return ReleaseManifest(
            output_path=str(payload.get("output_path", "")),
            exported_at=_parse_datetime(payload.get("exported_at")),
            draft_hash=str(payload.get("draft_hash", "")),
            template_name=str(payload.get("template_name", "")),
            included_files=[str(item) for item in (payload.get("included_files") or [])],
        )


@dataclass
class FullReportTemplate:
    name: str
    version: int = 2
    form_data: FullReportData = field(default_factory=create_empty_full_report_data)
    official_context_defaults: OfficialReportContext = field(default_factory=OfficialReportContext)
    section_layout: list[str] = field(default_factory=list)
    narrative_blocks: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "template_version": self.version,
            "name": self.name,
            "form_data": self.form_data.to_dict(),
            "official_context_defaults": self.official_context_defaults.to_dict(),
            "section_layout": list(self.section_layout),
            "narrative_blocks": dict(self.narrative_blocks),
        }

    @staticmethod
    def from_dict(payload: dict[str, Any], fallback_name: str = "") -> FullReportTemplate:
        if "form_data" not in payload:
            return FullReportTemplate(
                name=fallback_name or str(payload.get("name", "")),
                form_data=FullReportData.from_dict(payload),
            )
        return FullReportTemplate(
            name=str(payload.get("name", fallback_name)),
            version=int(payload.get("template_version", 2)),
            form_data=FullReportData.from_dict(payload.get("form_data") or {}),
            official_context_defaults=OfficialReportContext.from_dict(payload.get("official_context_defaults")),
            section_layout=[str(item) for item in (payload.get("section_layout") or [])],
            narrative_blocks={str(k): str(v) for k, v in (payload.get("narrative_blocks") or {}).items()},
        )


@dataclass
class ReferenceLibrary:
    customers: list[CustomerInfo] = field(default_factory=list)
    contractors: list[ContractorInfo] = field(default_factory=list)
    specialists: list[Specialist] = field(default_factory=list)
    equipment: list[EquipmentEntry] = field(default_factory=list)
    conclusion_texts: list[str] = field(default_factory=list)
    appendices: list[Appendix] = field(default_factory=list)
    recommendations: list[Recommendation] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(payload: dict[str, Any] | None) -> ReferenceLibrary:
        payload = payload or {}

        def _parse_specialist(item: dict[str, Any]) -> Specialist:
            expires = {}
            for k, v in (item.get("expires_at") or {}).items():
                expires[k] = _parse_date(v)
            return Specialist(
                full_name=item.get("full_name", ""),
                certifications=item.get("certifications", {}),
                expires_at=expires,
            )

        def _parse_equipment_entry(item: dict[str, Any]) -> EquipmentEntry:
            return EquipmentEntry(
                name=item.get("name", ""),
                serial_number=item.get("serial_number", ""),
                certificate=item.get("certificate", ""),
                valid_until=_parse_date(item.get("valid_until")),
            )

        return ReferenceLibrary(
            customers=[
                CustomerInfo(**item)
                for item in (payload.get("customers") or [])
                if isinstance(item, dict)
            ],
            contractors=[
                ContractorInfo(**item)
                for item in (payload.get("contractors") or [])
                if isinstance(item, dict)
            ],
            specialists=[
                _parse_specialist(item)
                for item in (payload.get("specialists") or [])
                if isinstance(item, dict)
            ],
            equipment=[
                _parse_equipment_entry(item)
                for item in (payload.get("equipment") or [])
                if isinstance(item, dict)
            ],
            conclusion_texts=[str(item) for item in (payload.get("conclusion_texts") or [])],
            appendices=[
                Appendix(
                    title=str(item.get("title", "")),
                    description=item.get("description"),
                    files=[str(path) for path in (item.get("files") or [])],
                )
                for item in (payload.get("appendices") or [])
                if isinstance(item, dict)
            ],
            recommendations=[
                Recommendation(text=str(item.get("text", "")))
                for item in (payload.get("recommendations") or [])
                if isinstance(item, dict)
            ],
        )


@dataclass
class FullReportDraftState:
    form_data: FullReportData = field(default_factory=create_empty_full_report_data)
    selected_template: str = ""
    official_context: OfficialReportContext = field(default_factory=OfficialReportContext)
    validation_state: list[ValidationIssue] = field(default_factory=list)
    field_provenance: dict[str, str] = field(default_factory=dict)
    attachments_manifest: list[AttachmentManifestEntry] = field(default_factory=list)
    last_autofill_at: datetime | None = None
    last_saved_at: datetime | None = None
    dirty_sections: list[str] = field(default_factory=list)
    preview_settings: PreviewSettings = field(default_factory=PreviewSettings)
    release_manifest: ReleaseManifest | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "draft_version": 2,
            "form_data": self.form_data.to_dict(),
            "selected_template": self.selected_template,
            "official_context": self.official_context.to_dict(),
            "validation_state": [asdict(item) for item in self.validation_state],
            "field_provenance": dict(self.field_provenance),
            "attachments_manifest": [asdict(item) for item in self.attachments_manifest],
            "last_autofill_at": self.last_autofill_at.isoformat() if self.last_autofill_at else None,
            "last_saved_at": self.last_saved_at.isoformat() if self.last_saved_at else None,
            "dirty_sections": list(self.dirty_sections),
            "preview_settings": asdict(self.preview_settings),
            "release_manifest": self.release_manifest.to_dict() if self.release_manifest else None,
        }

    @staticmethod
    def from_dict(payload: dict[str, Any] | None) -> FullReportDraftState:
        payload = payload or {}
        if "form_data" not in payload:
            return FullReportDraftState(form_data=FullReportData.from_dict(payload))
        return FullReportDraftState(
            form_data=FullReportData.from_dict(payload.get("form_data") or {}),
            selected_template=str(payload.get("selected_template", "")),
            official_context=OfficialReportContext.from_dict(payload.get("official_context")),
            validation_state=[
                ValidationIssue.from_dict(item)
                for item in (payload.get("validation_state") or [])
                if isinstance(item, dict)
            ],
            field_provenance={
                str(key): str(value)
                for key, value in (payload.get("field_provenance") or {}).items()
            },
            attachments_manifest=[
                AttachmentManifestEntry.from_dict(item)
                for item in (payload.get("attachments_manifest") or [])
                if isinstance(item, dict)
            ],
            last_autofill_at=_parse_datetime(payload.get("last_autofill_at")),
            last_saved_at=_parse_datetime(payload.get("last_saved_at")),
            dirty_sections=[str(item) for item in (payload.get("dirty_sections") or [])],
            preview_settings=PreviewSettings.from_dict(payload.get("preview_settings")),
            release_manifest=ReleaseManifest.from_dict(payload.get("release_manifest")),
        )

    def copy(self) -> FullReportDraftState:
        return FullReportDraftState.from_dict(self.to_dict())

    def draft_hash(self) -> str:
        payload = self.to_dict()
        payload["last_saved_at"] = None
        payload["last_autofill_at"] = None
        payload["validation_state"] = []
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass
class RenderTable:
    title: str
    headers: list[str]
    rows: list[list[str]]


@dataclass
class RenderSection:
    key: str
    title: str
    status: str = "not_started"
    paragraphs: list[str] = field(default_factory=list)
    tables: list[RenderTable] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    required_fields: list[str] = field(default_factory=list)
    provenance_summary: list[str] = field(default_factory=list)


@dataclass
class FullReportRenderModel:
    document_title: str
    subtitle: str
    report_number: str
    sections: list[RenderSection] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    generated_at: datetime = field(default_factory=datetime.now)


def deepcopy_report_data(data: FullReportData) -> FullReportData:
    return FullReportData.from_dict(deepcopy(data.to_dict()))


__all__ = [
    "AttachmentManifestEntry",
    "FullReportDraftState",
    "FullReportRenderModel",
    "FullReportTemplate",
    "OfficialReportContext",
    "PreviewSettings",
    "ReferenceLibrary",
    "ReleaseManifest",
    "RenderSection",
    "RenderTable",
    "SurveyStationEntry",
    "ValidationIssue",
    "create_empty_full_report_data",
    "deepcopy_report_data",
]
