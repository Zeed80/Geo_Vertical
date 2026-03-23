"""
Типы данных для расширенного контракта импорта.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd


def _safe_list(value: list[Any] | None) -> list[Any]:
    return list(value) if value else []


def _safe_dict(value: dict[str, Any] | None) -> dict[str, Any]:
    return dict(value) if value else {}


@dataclass
class ImportDiagnostics:
    """Единый контейнер диагностической информации импорта."""

    source_path: str = ""
    source_format: str = ""
    parser_strategy: str = ""
    raw_records: int = 0
    accepted_points: int = 0
    discarded_points: int = 0
    confidence: float = 1.0
    warnings: list[str] = field(default_factory=list)
    fallback_chain: list[str] = field(default_factory=list)
    discarded_reasons: dict[str, int] = field(default_factory=dict)
    standing_point_candidates: list[dict[str, Any]] = field(default_factory=list)
    duplicate_stats: dict[str, Any] = field(default_factory=dict)
    belt_summary: dict[str, Any] = field(default_factory=dict)
    tower_part_summary: dict[str, Any] = field(default_factory=dict)
    transformation_quality: dict[str, Any] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)

    def add_warning(self, message: str) -> None:
        if message and message not in self.warnings:
            self.warnings.append(message)

    def add_fallback(self, name: str) -> None:
        if name and name not in self.fallback_chain:
            self.fallback_chain.append(name)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_path": self.source_path,
            "source_format": self.source_format,
            "parser_strategy": self.parser_strategy,
            "raw_records": int(self.raw_records),
            "accepted_points": int(self.accepted_points),
            "discarded_points": int(self.discarded_points),
            "confidence": float(self.confidence),
            "warnings": _safe_list(self.warnings),
            "fallback_chain": _safe_list(self.fallback_chain),
            "discarded_reasons": _safe_dict(self.discarded_reasons),
            "standing_point_candidates": _safe_list(self.standing_point_candidates),
            "duplicate_stats": _safe_dict(self.duplicate_stats),
            "belt_summary": _safe_dict(self.belt_summary),
            "tower_part_summary": _safe_dict(self.tower_part_summary),
            "transformation_quality": _safe_dict(self.transformation_quality),
            "details": _safe_dict(self.details),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> ImportDiagnostics:
        if not payload:
            return cls()
        return cls(
            source_path=str(payload.get("source_path", "")),
            source_format=str(payload.get("source_format", "")),
            parser_strategy=str(payload.get("parser_strategy", "")),
            raw_records=int(payload.get("raw_records", 0) or 0),
            accepted_points=int(payload.get("accepted_points", 0) or 0),
            discarded_points=int(payload.get("discarded_points", 0) or 0),
            confidence=float(payload.get("confidence", 1.0) or 0.0),
            warnings=_safe_list(payload.get("warnings")),
            fallback_chain=_safe_list(payload.get("fallback_chain")),
            discarded_reasons=_safe_dict(payload.get("discarded_reasons")),
            standing_point_candidates=_safe_list(payload.get("standing_point_candidates")),
            duplicate_stats=_safe_dict(payload.get("duplicate_stats")),
            belt_summary=_safe_dict(payload.get("belt_summary")),
            tower_part_summary=_safe_dict(payload.get("tower_part_summary")),
            transformation_quality=_safe_dict(payload.get("transformation_quality")),
            details=_safe_dict(payload.get("details")),
        )


@dataclass
class LoadedSurveyData:
    """Расширенный результат импорта геодезического файла."""

    data: pd.DataFrame
    epsg_code: int | None = None
    source_format: str = ""
    parser_strategy: str = ""
    warnings: list[str] = field(default_factory=list)
    confidence: float = 1.0
    diagnostics: ImportDiagnostics = field(default_factory=ImportDiagnostics)

    def to_legacy_tuple(self):
        return self.data, self.epsg_code

    def to_context_dict(self) -> dict[str, Any]:
        return {
            "source_format": self.source_format,
            "parser_strategy": self.parser_strategy,
            "warnings": _safe_list(self.warnings or self.diagnostics.warnings),
            "confidence": float(self.confidence),
            "epsg_code": self.epsg_code,
            "diagnostics": self.diagnostics.to_dict(),
        }

    @classmethod
    def from_context_dict(
        cls,
        data: pd.DataFrame,
        payload: dict[str, Any] | None,
    ) -> LoadedSurveyData:
        payload = payload or {}
        diagnostics_payload = payload.get("diagnostics")
        diagnostics = ImportDiagnostics.from_dict(diagnostics_payload)
        return cls(
            data=data,
            epsg_code=payload.get("epsg_code"),
            source_format=str(payload.get("source_format", diagnostics.source_format or "")),
            parser_strategy=str(payload.get("parser_strategy", diagnostics.parser_strategy or "")),
            warnings=_safe_list(payload.get("warnings", diagnostics.warnings)),
            confidence=float(payload.get("confidence", diagnostics.confidence or 0.0)),
            diagnostics=diagnostics,
        )
