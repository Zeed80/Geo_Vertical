from __future__ import annotations

from typing import Any

import pandas as pd

from core.normatives import get_straightness_tolerance
from core.straightness_calculations import build_straightness_profiles


def _coerce_optional_int(value: Any, default: int | None = None) -> int | None:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _canonical_profile_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        profiles = payload.get("straightness_profiles")
        if isinstance(profiles, list):
            return [item for item in profiles if isinstance(item, dict)]
    return []


def normalize_straightness_profiles(payload: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []

    for profile in _canonical_profile_list(payload):
        belt_number = _coerce_optional_int(profile.get("belt"))
        if belt_number is None:
            continue

        part_number = _coerce_optional_int(profile.get("part_number"), 1) or 1
        part_min_height = float(profile.get("part_min_height", 0.0) or 0.0)
        part_max_height = float(profile.get("part_max_height", part_min_height) or part_min_height)
        section_length_m = float(
            profile.get("section_length_m", max(0.0, part_max_height - part_min_height)) or 0.0
        )
        tolerance_mm = float(
            profile.get("tolerance_mm") or get_straightness_tolerance(section_length_m) * 1000.0
        )

        normalized_points: list[dict[str, Any]] = []
        for point in profile.get("points", []):
            if not isinstance(point, dict):
                continue
            try:
                height = float(point.get("z", 0.0))
                deflection_mm = float(point.get("deflection_mm", 0.0) or 0.0)
            except (TypeError, ValueError):
                continue

            point_section_length_m = float(
                point.get("section_length_m", section_length_m) or section_length_m
            )
            point_tolerance_mm = float(
                point.get("tolerance_mm")
                or (
                    get_straightness_tolerance(point_section_length_m) * 1000.0
                    if point_section_length_m > 0.0
                    else tolerance_mm
                )
            )

            normalized_points.append(
                {
                    "source_index": _coerce_optional_int(point.get("source_index")),
                    "z": height,
                    "deflection_mm": deflection_mm,
                    "section_length_m": point_section_length_m,
                    "tolerance_mm": point_tolerance_mm,
                }
            )

        normalized_points.sort(key=lambda item: float(item.get("z", 0.0) or 0.0))
        if normalized_points:
            section_length_m = max(
                float(item.get("section_length_m", section_length_m) or section_length_m)
                for item in normalized_points
            )
            tolerance_mm = max(
                float(item.get("tolerance_mm", tolerance_mm) or tolerance_mm)
                for item in normalized_points
            )
        max_deflection_mm = max(
            (abs(float(item.get("deflection_mm", 0.0) or 0.0)) for item in normalized_points),
            default=0.0,
        )

        result.append(
            {
                "part_number": part_number,
                "belt": belt_number,
                "section_length_m": section_length_m,
                "tolerance_mm": tolerance_mm,
                "max_deflection_mm": float(profile.get("max_deflection_mm", max_deflection_mm) or max_deflection_mm),
                "part_min_height": part_min_height,
                "part_max_height": part_max_height,
                "points": normalized_points,
            }
        )

    result.sort(key=lambda item: (int(item.get("part_number", 1)), int(item.get("belt", 0))))
    return result


def build_straightness_part_map(payload: Any) -> dict[int, dict[str, Any]]:
    if isinstance(payload, dict) and "straightness_profiles" not in payload:
        direct_map = _normalize_direct_part_map(payload)
        if direct_map:
            return direct_map

    result: dict[int, dict[str, Any]] = {}
    for profile in normalize_straightness_profiles(payload):
        part_number = int(profile.get("part_number", 1))
        belt_number = int(profile.get("belt", 0))
        part_entry = result.setdefault(
            part_number,
            {
                "min_height": float(profile.get("part_min_height", 0.0) or 0.0),
                "max_height": float(profile.get("part_max_height", 0.0) or 0.0),
                "belts": {},
            },
        )
        part_entry["min_height"] = min(part_entry["min_height"], float(profile.get("part_min_height", 0.0) or 0.0))
        part_entry["max_height"] = max(part_entry["max_height"], float(profile.get("part_max_height", 0.0) or 0.0))
        part_entry["belts"][belt_number] = [
            {
                "height": float(point.get("z", 0.0) or 0.0),
                "deflection": float(point.get("deflection_mm", 0.0) or 0.0),
                "tolerance": float(
                    point.get("tolerance_mm", profile.get("tolerance_mm", 0.0)) or 0.0
                ),
                "section_length_m": float(
                    point.get("section_length_m", profile.get("section_length_m", 0.0)) or 0.0
                ),
                "source_index": _coerce_optional_int(point.get("source_index")),
            }
            for point in profile.get("points", [])
        ]

    return {
        int(part_number): {
            "min_height": float(part_info.get("min_height", 0.0) or 0.0),
            "max_height": float(part_info.get("max_height", 0.0) or 0.0),
            "belts": {
                int(belt_number): sorted(
                    [
                        {
                            "height": float(point.get("height", 0.0) or 0.0),
                            "deflection": float(point.get("deflection", 0.0) or 0.0),
                            "tolerance": float(point.get("tolerance", 0.0) or 0.0),
                            "section_length_m": float(point.get("section_length_m", 0.0) or 0.0),
                            "source_index": _coerce_optional_int(point.get("source_index")),
                        }
                        for point in belt_points
                        if isinstance(point, dict)
                    ],
                    key=lambda item: float(item.get("height", 0.0) or 0.0),
                )
                for belt_number, belt_points in sorted((part_info.get("belts") or {}).items())
            },
        }
        for part_number, part_info in sorted(result.items())
    }


def _normalize_direct_part_map(payload: dict[Any, Any]) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    for raw_part_number, part_info in payload.items():
        if not isinstance(part_info, dict) or "belts" not in part_info:
            continue

        part_number = _coerce_optional_int(raw_part_number, _coerce_optional_int(part_info.get("part_number"), 1)) or 1
        part_entry = result.setdefault(
            part_number,
            {
                "min_height": float(part_info.get("min_height", 0.0) or 0.0),
                "max_height": float(part_info.get("max_height", 0.0) or 0.0),
                "belts": {},
            },
        )
        part_entry["min_height"] = min(part_entry["min_height"], float(part_info.get("min_height", 0.0) or 0.0))
        part_entry["max_height"] = max(part_entry["max_height"], float(part_info.get("max_height", 0.0) or 0.0))

        for raw_belt_number, belt_points in (part_info.get("belts") or {}).items():
            belt_number = _coerce_optional_int(raw_belt_number)
            if belt_number is None:
                continue

            normalized_points: list[dict[str, Any]] = []
            for point in belt_points or []:
                if not isinstance(point, dict):
                    continue
                try:
                    normalized_points.append(
                        {
                            "height": float(point.get("height", 0.0) or 0.0),
                            "deflection": float(point.get("deflection", 0.0) or 0.0),
                            "tolerance": float(point.get("tolerance", 0.0) or 0.0),
                            "section_length_m": float(point.get("section_length_m", 0.0) or 0.0),
                            "source_index": _coerce_optional_int(point.get("source_index")),
                        }
                    )
                except (TypeError, ValueError):
                    continue

            normalized_points.sort(key=lambda item: float(item.get("height", 0.0) or 0.0))
            part_entry["belts"][belt_number] = normalized_points

    return {int(part_number): result[part_number] for part_number in sorted(result)}


def get_preferred_straightness_profiles(
    *payload_candidates: Any,
    points: pd.DataFrame | None = None,
    tower_parts_info: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    for payload in payload_candidates:
        profiles = normalize_straightness_profiles(payload)
        if profiles:
            return profiles

    if isinstance(points, pd.DataFrame) and not points.empty:
        return normalize_straightness_profiles(build_straightness_profiles(points, tower_parts_info))

    return []


def get_preferred_straightness_part_map(
    *payload_candidates: Any,
    points: pd.DataFrame | None = None,
    tower_parts_info: dict[str, Any] | None = None,
) -> dict[int, dict[str, Any]]:
    for payload in payload_candidates:
        part_map = build_straightness_part_map(payload)
        if part_map:
            return part_map

    if isinstance(points, pd.DataFrame) and not points.empty:
        return build_straightness_part_map(
            build_straightness_profiles(points, tower_parts_info)
        )

    return {}
