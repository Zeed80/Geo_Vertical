from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from core.normatives import NormativeChecker, get_vertical_tolerance


def _coerce_optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_xy_pair(value: Any) -> tuple[float, float] | None:
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return None
    try:
        return (float(value[0]), float(value[1]))
    except (TypeError, ValueError):
        return None


def _canonical_section_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        sections = payload.get("sections")
        if isinstance(sections, list):
            return [item for item in sections if isinstance(item, dict)]
    return []


def normalize_verticality_sections(payload: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []

    for item in _canonical_section_list(payload):
        height = item.get("height")
        total_deviation = item.get("total_deviation", item.get("deviation"))
        if height is None or total_deviation is None:
            continue

        try:
            normalized_height = float(height)
            normalized_total = float(total_deviation)
            normalized_deviation_x = float(item.get("deviation_x", 0.0) or 0.0)
            normalized_deviation_y = float(item.get("deviation_y", 0.0) or 0.0)
        except (TypeError, ValueError):
            continue

        normalized: dict[str, Any] = dict(item)
        normalized["section_num"] = _coerce_optional_int(item.get("section_num"))
        normalized["part_num"] = _coerce_optional_int(item.get("part_num")) or item.get("part_num")
        normalized["height"] = normalized_height
        normalized["deviation_x"] = normalized_deviation_x
        normalized["deviation_y"] = normalized_deviation_y
        normalized["total_deviation"] = normalized_total
        normalized["deviation"] = normalized_total
        normalized["tolerance"] = float(item.get("tolerance") or get_vertical_tolerance(normalized_height) * 1000.0)
        normalized["points_count"] = item.get("points_count", item.get("point_count"))
        normalized["source"] = item.get("source")
        normalized["basis_complete"] = item.get("basis_complete")

        center_xy = _coerce_xy_pair(item.get("center_xy"))
        if center_xy is not None:
            normalized["center_xy"] = center_xy

        axis_point_xy = _coerce_xy_pair(item.get("axis_point_xy"))
        if axis_point_xy is not None:
            normalized["axis_point_xy"] = axis_point_xy

        result.append(normalized)

    result.sort(
        key=lambda section: (
            float(section.get("height", 0.0) or 0.0),
            section.get("section_num") if section.get("section_num") is not None else 10**9,
        )
    )
    return result


def aggregate_angular_measurements_by_sections(
    angular_measurements: Any,
    height_tolerance: float = 0.3,
) -> list[dict[str, Any]]:
    normalized_sections = normalize_verticality_sections(angular_measurements)
    if normalized_sections:
        return normalized_sections

    if not isinstance(angular_measurements, dict):
        return []

    basis = angular_measurements.get("basis", {})
    has_authoritative_stations = basis.get("has_authoritative_stations", basis.get("has_required_stations"))
    if basis.get("requires_two_stations") and not has_authoritative_stations:
        return []

    rows_x = angular_measurements.get("x", [])
    rows_y = angular_measurements.get("y", [])
    if not rows_x and not rows_y:
        return []

    def group_by_height(rows: list[dict[str, Any]], tolerance: float) -> dict[float, float]:
        if not rows:
            return {}

        groups: dict[float, list[float]] = {}
        for row in rows:
            height = row.get("height")
            delta_mm = row.get("delta_mm")
            if height is None or delta_mm is None:
                continue

            matched_height = None
            for key_height in groups:
                if abs(float(height) - float(key_height)) <= tolerance:
                    matched_height = key_height
                    break

            if matched_height is None:
                groups[float(height)] = [float(delta_mm)]
            else:
                groups[matched_height].append(float(delta_mm))

        return {
            height: float(np.mean(valid_deviations))
            for height, valid_deviations in groups.items()
            if valid_deviations
        }

    deviations_x_by_height = group_by_height(rows_x, height_tolerance)
    deviations_y_by_height = group_by_height(rows_y, height_tolerance)
    all_heights = sorted(set(deviations_x_by_height.keys()) | set(deviations_y_by_height.keys()))

    result: list[dict[str, Any]] = []
    for section_num, height in enumerate(all_heights):
        deviation_x = float(deviations_x_by_height.get(height, 0.0))
        deviation_y = float(deviations_y_by_height.get(height, 0.0))
        total_deviation = float(np.hypot(deviation_x, deviation_y))
        result.append(
            {
                "section_num": section_num,
                "height": float(height),
                "deviation_x": deviation_x,
                "deviation_y": deviation_y,
                "total_deviation": total_deviation,
                "deviation": total_deviation,
                "tolerance": float(get_vertical_tolerance(float(height)) * 1000.0),
            }
        )

    return result


def get_preferred_verticality_sections(*payload_candidates: Any) -> list[dict[str, Any]]:
    for payload in payload_candidates:
        sections = aggregate_angular_measurements_by_sections(payload)
        if sections:
            return sections
    return []


def empty_verticality_check(structure_type: str = "tower") -> dict[str, Any]:
    return NormativeChecker(structure_type).check_vertical_deviations([], [])


def build_verticality_check_from_sections(
    sections: Any,
    structure_type: str = "tower",
) -> dict[str, Any]:
    normalized_sections = normalize_verticality_sections(sections)
    if not normalized_sections:
        return empty_verticality_check(structure_type)

    checker = NormativeChecker(structure_type)
    deviations_m = [float(item["total_deviation"]) / 1000.0 for item in normalized_sections]
    heights_m = [float(item["height"]) for item in normalized_sections]
    result = checker.check_vertical_deviations(deviations_m, heights_m)

    for collection_name in ("compliant", "non_compliant"):
        for item in result.get(collection_name, []):
            source_section = normalized_sections[item.get("index", 0)]
            item["section_num"] = source_section.get("section_num")
            item["part_num"] = source_section.get("part_num")
            item["source"] = source_section.get("source")

    return result


def build_verticality_check_from_sources(
    *payload_candidates: Any,
    centers: Any = None,
    structure_type: str = "tower",
) -> dict[str, Any]:
    sections = get_preferred_verticality_sections(*payload_candidates)
    if sections:
        return build_verticality_check_from_sections(sections, structure_type=structure_type)

    if isinstance(centers, pd.DataFrame) and not centers.empty:
        height_col = next((candidate for candidate in ("z", "height", "belt_height") if candidate in centers.columns), None)
        if height_col is not None and "deviation" in centers.columns:
            checker = NormativeChecker(structure_type)
            return checker.check_vertical_deviations(
                pd.to_numeric(centers["deviation"], errors="coerce").fillna(0.0).tolist(),
                pd.to_numeric(centers[height_col], errors="coerce").fillna(0.0).tolist(),
            )

    return empty_verticality_check(structure_type)
