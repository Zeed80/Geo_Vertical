"""Helpers for the interactive import workflow."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd

from core.point_utils import build_working_tower_mask
from core.section_operations import (
    add_missing_points_for_sections,
    find_section_levels,
    get_section_lines,
)
from core.section_state import SECTION_BUILD_HEIGHT_TOLERANCE

_MIN_MOVE_METERS = 0.005


@dataclass
class InteractiveImportThresholds:
    """Conservative thresholds used by interactive correction proposals."""

    z_snap_tolerance_m: float = 0.15
    max_projection_distance_m: float = 0.30
    max_station_angle_deg: float = 1.5
    min_adjacent_improvement_ratio: float = 2.0
    min_track_residual_m: float = 0.03

    def to_dict(self) -> dict[str, float]:
        return {key: float(value) for key, value in asdict(self).items()}


def _numeric_series(data: pd.DataFrame, column: str) -> pd.Series:
    if column not in data.columns:
        return pd.Series(dtype=float, index=data.index)
    return pd.to_numeric(data[column], errors="coerce")


def _first_numeric(row: pd.Series, *columns: str) -> int | None:
    for column in columns:
        if column not in row.index:
            continue
        value = pd.to_numeric(pd.Series([row.get(column)]), errors="coerce").iloc[0]
        if pd.notna(value):
            return int(value)
    return None


def _wrap_angle_rad(value: float) -> float:
    return float(np.arctan2(np.sin(value), np.cos(value)))


def _angle_delta_deg(a_rad: float, b_rad: float) -> float:
    return float(abs(np.degrees(_wrap_angle_rad(a_rad - b_rad))))


def _line_intersection_xy(
    point_a: np.ndarray,
    direction_a: np.ndarray,
    point_b: np.ndarray,
    direction_b: np.ndarray,
) -> np.ndarray | None:
    matrix = np.column_stack([direction_a, -direction_b])
    det = float(np.linalg.det(matrix))
    if abs(det) < 1e-9:
        return None
    try:
        params = np.linalg.solve(matrix, point_b - point_a)
    except np.linalg.LinAlgError:
        return None
    ray_scale = float(params[0])
    if ray_scale <= 0.0:
        return None
    return point_a + ray_scale * direction_a


def _project_xy_to_line(point_xy: np.ndarray, anchor_xy: np.ndarray, direction_xy: np.ndarray) -> np.ndarray:
    offset = point_xy - anchor_xy
    scale = float(np.dot(offset, direction_xy))
    return anchor_xy + scale * direction_xy


def _distance_to_xy_line(point_xy: np.ndarray, anchor_xy: np.ndarray, direction_xy: np.ndarray) -> float:
    projected = _project_xy_to_line(point_xy, anchor_xy, direction_xy)
    return float(np.linalg.norm(point_xy - projected))


def _track_key(row: pd.Series) -> tuple[int, int] | None:
    belt_value = _first_numeric(row, "part_belt", "part_face_track", "face_track", "belt")
    if belt_value is None or belt_value <= 0:
        return None
    part_value = _first_numeric(row, "tower_part")
    return (part_value or 1, belt_value)


def _resolve_station_xy(data: pd.DataFrame) -> np.ndarray | None:
    if data.empty or "is_station" not in data.columns:
        return None
    station_mask = data["is_station"].fillna(False).astype(bool)
    stations = data.loc[station_mask].copy()
    if stations.empty:
        return None
    if "station_role" in stations.columns:
        primary = stations[stations["station_role"].astype(str).str.lower() == "primary"]
        if not primary.empty:
            stations = primary
    try:
        row = stations.iloc[0]
        return np.array([float(row["x"]), float(row["y"])], dtype=float)
    except (TypeError, ValueError, KeyError):
        return None


def _build_track_models(data: pd.DataFrame, station_xy: np.ndarray | None) -> dict[tuple[int, int], dict[str, Any]]:
    working = data.loc[build_working_tower_mask(data)].copy()
    models: dict[tuple[int, int], dict[str, Any]] = {}
    if working.empty:
        return models

    grouped: dict[tuple[int, int], list[int]] = {}
    for row_idx, row in working.iterrows():
        key = _track_key(row)
        if key is None:
            continue
        grouped.setdefault(key, []).append(int(row_idx))

    for key, indices in grouped.items():
        subset = working.loc[indices].copy()
        if len(subset) < 2:
            continue
        xy = subset[["x", "y"]].to_numpy(dtype=float)
        center = np.mean(xy, axis=0, dtype=float)
        centered = xy - center
        _, _, vh = np.linalg.svd(centered, full_matrices=False)
        direction = np.asarray(vh[0], dtype=float)
        norm = float(np.linalg.norm(direction))
        if norm <= 1e-9:
            continue
        direction = direction / norm
        z_values = pd.to_numeric(subset["z"], errors="coerce").dropna().to_numpy(dtype=float)
        level_values = pd.to_numeric(subset.get("height_level"), errors="coerce").dropna().to_numpy(dtype=int)
        model: dict[str, Any] = {
            "indices": [int(value) for value in subset.index.tolist()],
            "anchor_xy": center,
            "direction_xy": direction,
            "z_levels": sorted({float(value) for value in z_values.tolist()}),
            "height_levels": sorted({int(value) for value in level_values.tolist() if int(value) > 0}),
            "point_count": int(len(subset)),
        }
        if station_xy is not None:
            station_vectors = xy - station_xy
            station_angles = np.arctan2(station_vectors[:, 1], station_vectors[:, 0])
            complex_mean = np.mean(np.exp(1j * station_angles))
            if abs(complex_mean) > 1e-9:
                model["station_angle_rad"] = float(np.angle(complex_mean))
        models[key] = model

    return models


def _nearest_track_level(row: pd.Series, model: dict[str, Any]) -> float | None:
    if not model.get("z_levels"):
        return None
    return min(model["z_levels"], key=lambda value: abs(value - float(row["z"])))


def _build_candidate(
    *,
    row_idx: int,
    row: pd.Series,
    current_key: tuple[int, int],
    proposed_key: tuple[int, int],
    correction_kind: str,
    proposed_xy: np.ndarray,
    proposed_z: float,
    moved_distance_m: float,
    current_residual_m: float,
    proposed_residual_m: float,
    reason: str,
    safety: str,
) -> dict[str, Any]:
    return {
        "row_index": int(row_idx),
        "point_name": str(row.get("name", row_idx)),
        "tower_part": int(proposed_key[0]),
        "current_belt": int(current_key[1]),
        "proposed_belt": int(proposed_key[1]),
        "correction_kind": correction_kind,
        "current_x": float(row["x"]),
        "current_y": float(row["y"]),
        "current_z": float(row["z"]),
        "proposed_x": float(proposed_xy[0]),
        "proposed_y": float(proposed_xy[1]),
        "proposed_z": float(proposed_z),
        "distance_moved_m": float(moved_distance_m),
        "current_residual_m": float(current_residual_m),
        "proposed_residual_m": float(proposed_residual_m),
        "reason": reason,
        "safety": safety,
    }


def build_interactive_correction_review(
    data: pd.DataFrame,
    thresholds: InteractiveImportThresholds | None = None,
) -> dict[str, Any]:
    thresholds = thresholds or InteractiveImportThresholds()
    working = data.loc[build_working_tower_mask(data)].copy()
    station_xy = _resolve_station_xy(data)
    track_models = _build_track_models(data, station_xy)
    candidates: list[dict[str, Any]] = []
    point_status_counts = {
        "accepted": 0,
        "correction_candidate": 0,
        "manual_review": 0,
    }

    for row_idx, row in working.iterrows():
        key = _track_key(row)
        if key is None:
            point_status_counts["manual_review"] += 1
            continue

        model = track_models.get(key)
        if model is None:
            point_status_counts["manual_review"] += 1
            continue

        point_xy = np.array([float(row["x"]), float(row["y"])], dtype=float)
        current_residual = _distance_to_xy_line(point_xy, model["anchor_xy"], model["direction_xy"])
        row_angle = None
        if station_xy is not None:
            station_vector = point_xy - station_xy
            if float(np.linalg.norm(station_vector)) > 1e-9:
                row_angle = float(np.arctan2(station_vector[1], station_vector[0]))

        z_target = _nearest_track_level(row, model)
        z_delta = abs(float(row["z"]) - float(z_target)) if z_target is not None else None
        z_snap_candidate = None
        if (
            z_target is not None
            and z_delta is not None
            and _MIN_MOVE_METERS < z_delta <= thresholds.z_snap_tolerance_m
            and current_residual <= thresholds.max_projection_distance_m
        ):
            z_snap_candidate = _build_candidate(
                row_idx=int(row_idx),
                row=row,
                current_key=key,
                proposed_key=key,
                correction_kind="snap_z_to_level",
                proposed_xy=point_xy,
                proposed_z=float(z_target),
                moved_distance_m=float(z_delta),
                current_residual_m=current_residual,
                proposed_residual_m=current_residual,
                reason=f"Height differs from stable level by {z_delta * 1000.0:.0f} mm.",
                safety="safe",
            )

        projection_candidate = None
        if (
            station_xy is not None
            and current_residual > thresholds.min_track_residual_m
            and row_angle is not None
        ):
            model_angle = model.get("station_angle_rad")
            angle_delta = _angle_delta_deg(row_angle, model_angle) if model_angle is not None else 0.0
            if angle_delta <= thresholds.max_station_angle_deg:
                station_ray = point_xy - station_xy
                station_ray_norm = float(np.linalg.norm(station_ray))
                if station_ray_norm > 1e-9:
                    projected_xy = _line_intersection_xy(
                        station_xy,
                        station_ray / station_ray_norm,
                        model["anchor_xy"],
                        model["direction_xy"],
                    )
                    if projected_xy is not None:
                        move = float(np.linalg.norm(projected_xy - point_xy))
                        if _MIN_MOVE_METERS < move <= thresholds.max_projection_distance_m:
                            projection_candidate = _build_candidate(
                                row_idx=int(row_idx),
                                row=row,
                                current_key=key,
                                proposed_key=key,
                                correction_kind="project_to_face_track",
                                proposed_xy=projected_xy,
                                proposed_z=float(row["z"]),
                                moved_distance_m=move,
                                current_residual_m=current_residual,
                                proposed_residual_m=0.0,
                                reason=f"Station ray matches the confirmed track; move {move * 1000.0:.0f} mm.",
                                safety="safe",
                            )

        adjacent_candidate = None
        if current_residual > thresholds.min_track_residual_m and row_angle is not None:
            for delta in (-1, 1):
                adjacent_key = (key[0], key[1] + delta)
                adjacent_model = track_models.get(adjacent_key)
                if adjacent_model is None:
                    continue
                adjacent_angle = adjacent_model.get("station_angle_rad")
                angle_delta = _angle_delta_deg(row_angle, adjacent_angle) if adjacent_angle is not None else 0.0
                if angle_delta > thresholds.max_station_angle_deg:
                    continue
                adjacent_residual = _distance_to_xy_line(
                    point_xy,
                    adjacent_model["anchor_xy"],
                    adjacent_model["direction_xy"],
                )
                if adjacent_residual <= 1e-9:
                    improvement_ratio = float("inf")
                else:
                    improvement_ratio = current_residual / adjacent_residual
                if improvement_ratio < thresholds.min_adjacent_improvement_ratio:
                    continue

                if station_xy is not None:
                    station_ray = point_xy - station_xy
                    station_ray_norm = float(np.linalg.norm(station_ray))
                    if station_ray_norm <= 1e-9:
                        continue
                    projected_xy = _line_intersection_xy(
                        station_xy,
                        station_ray / station_ray_norm,
                        adjacent_model["anchor_xy"],
                        adjacent_model["direction_xy"],
                    )
                else:
                    projected_xy = _project_xy_to_line(
                        point_xy,
                        adjacent_model["anchor_xy"],
                        adjacent_model["direction_xy"],
                    )
                if projected_xy is None:
                    continue
                move = float(np.linalg.norm(projected_xy - point_xy))
                if not (_MIN_MOVE_METERS < move <= thresholds.max_projection_distance_m):
                    continue

                candidate = _build_candidate(
                    row_idx=int(row_idx),
                    row=row,
                    current_key=key,
                    proposed_key=adjacent_key,
                    correction_kind="adjacent_face_rebind_then_project",
                    proposed_xy=projected_xy,
                    proposed_z=float(row["z"]),
                    moved_distance_m=move,
                    current_residual_m=current_residual,
                    proposed_residual_m=adjacent_residual,
                    reason=(
                        "Adjacent track reduces residual from "
                        f"{current_residual * 1000.0:.0f} mm to {adjacent_residual * 1000.0:.0f} mm."
                    ),
                    safety="review",
                )
                if (
                    adjacent_candidate is None
                    or candidate["proposed_residual_m"] < adjacent_candidate["proposed_residual_m"]
                ):
                    adjacent_candidate = candidate

        chosen = projection_candidate or adjacent_candidate or z_snap_candidate
        if chosen is None:
            if current_residual > thresholds.min_track_residual_m:
                point_status_counts["manual_review"] += 1
            else:
                point_status_counts["accepted"] += 1
            continue

        candidates.append(chosen)
        point_status_counts["correction_candidate"] += 1

    return {
        "thresholds": thresholds.to_dict(),
        "station_xy": station_xy.tolist() if station_xy is not None else None,
        "track_model_count": int(len(track_models)),
        "candidates": candidates,
        "point_status_counts": point_status_counts,
    }


def apply_interactive_corrections(
    data: pd.DataFrame,
    candidates: list[dict[str, Any]],
    accepted_row_indices: set[int],
) -> tuple[pd.DataFrame, list[dict[str, Any]], list[dict[str, Any]]]:
    result = data.copy()
    for source_col, value_col in (("source_x", "x"), ("source_y", "y"), ("source_z", "z")):
        if source_col not in result.columns:
            result[source_col] = pd.to_numeric(result.get(value_col), errors="coerce")

    if "source_belt" not in result.columns:
        result["source_belt"] = _numeric_series(result, "belt")
    if "confirmed_belt" not in result.columns:
        result["confirmed_belt"] = _numeric_series(result, "belt")
    if "import_corrected" not in result.columns:
        result["import_corrected"] = False
    else:
        result["import_corrected"] = result["import_corrected"].fillna(False).astype(bool)
    if "import_correction_kind" not in result.columns:
        result["import_correction_kind"] = None
    if "import_correction_distance_mm" not in result.columns:
        result["import_correction_distance_mm"] = 0.0
    if "import_review_status" not in result.columns:
        result["import_review_status"] = None

    service_mask = pd.Series(False, index=result.index)
    for column in ("is_station", "is_auxiliary", "is_control"):
        if column in result.columns:
            service_mask |= result[column].fillna(False).astype(bool)
    working_mask = build_working_tower_mask(result)
    result.loc[working_mask, "import_review_status"] = "accepted"
    result.loc[service_mask, "import_review_status"] = "service"

    applied: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    candidate_map = {int(candidate["row_index"]): dict(candidate) for candidate in candidates}

    for row_idx, candidate in candidate_map.items():
        if row_idx not in result.index:
            continue
        if row_idx not in accepted_row_indices:
            result.at[row_idx, "import_review_status"] = "manual_review"
            rejected.append(candidate)
            continue

        result.at[row_idx, "x"] = float(candidate["proposed_x"])
        result.at[row_idx, "y"] = float(candidate["proposed_y"])
        result.at[row_idx, "z"] = float(candidate["proposed_z"])
        result.at[row_idx, "import_corrected"] = True
        result.at[row_idx, "import_correction_kind"] = str(candidate["correction_kind"])
        result.at[row_idx, "import_correction_distance_mm"] = float(candidate["distance_moved_m"]) * 1000.0
        result.at[row_idx, "import_review_status"] = "corrected"
        result.at[row_idx, "confirmed_belt"] = int(candidate["proposed_belt"])

        if "belt" in result.columns:
            result.at[row_idx, "belt"] = int(candidate["proposed_belt"])
        if "part_belt" in result.columns:
            result.at[row_idx, "part_belt"] = int(candidate["proposed_belt"])
        if "face_track" in result.columns:
            result.at[row_idx, "face_track"] = int(candidate["proposed_belt"])
        if "part_face_track" in result.columns:
            result.at[row_idx, "part_face_track"] = int(candidate["proposed_belt"])

        applied.append(candidate)

    section_generated_mask = result.get("is_section_generated")
    if section_generated_mask is not None:
        generated_mask = pd.Series(section_generated_mask, index=result.index).fillna(False).astype(bool)
        result.loc[generated_mask, "import_review_status"] = "generated_section"

    return result, applied, rejected


def build_section_review(
    data: pd.DataFrame,
    *,
    height_tolerance: float = SECTION_BUILD_HEIGHT_TOLERANCE,
) -> dict[str, Any]:
    if data.empty:
        return {
            "height_tolerance": float(height_tolerance),
            "section_levels": [],
            "data_with_sections": data.copy(),
            "section_lines": [],
            "rows": [],
        }

    section_levels = find_section_levels(data, height_tolerance=height_tolerance)
    data_with_sections = add_missing_points_for_sections(
        data,
        section_levels,
        height_tolerance=height_tolerance,
    )
    section_lines = get_section_lines(
        data_with_sections,
        section_levels,
        height_tolerance=height_tolerance,
    )

    rows: list[dict[str, Any]] = []
    generated_source = data_with_sections.get("is_section_generated")
    if generated_source is None:
        generated_mask = pd.Series(False, index=data_with_sections.index, dtype=bool)
    else:
        generated_mask = pd.Series(generated_source, index=data_with_sections.index).astype("boolean").fillna(False).astype(bool)
    for section_num, section in enumerate(section_lines, start=1):
        height = float(section.get("height", 0.0) or 0.0)
        generated_count = int(
            (
                generated_mask
                & data_with_sections["z"].sub(height).abs().le(height_tolerance)
            ).sum()
        )
        rows.append(
            {
                "section_num": int(section_num),
                "height": height,
                "point_count": int(len(section.get("points", []))),
                "belt_count": int(len(section.get("belt_nums", []))),
                "generated_count": generated_count,
                "apply_generated_default": generated_count == 0,
            }
        )

    return {
        "height_tolerance": float(height_tolerance),
        "section_levels": [float(value) for value in section_levels],
        "data_with_sections": data_with_sections,
        "section_lines": section_lines,
        "rows": rows,
    }


def apply_section_review_selection(
    review: dict[str, Any],
    accepted_section_numbers: set[int],
) -> tuple[pd.DataFrame, list[dict[str, Any]], list[dict[str, Any]]]:
    data_with_sections = review.get("data_with_sections")
    if not isinstance(data_with_sections, pd.DataFrame):
        return pd.DataFrame(), [], []

    result = data_with_sections.copy()
    rows = list(review.get("rows", []))
    height_tolerance = float(review.get("height_tolerance", SECTION_BUILD_HEIGHT_TOLERANCE))
    blocked_heights = {
        float(row["height"])
        for row in rows
        if int(row.get("generated_count", 0) or 0) > 0
        and int(row.get("section_num", 0) or 0) not in accepted_section_numbers
    }

    if blocked_heights and "is_section_generated" in result.columns:
        generated_mask = result["is_section_generated"].astype("boolean").fillna(False).astype(bool)
        reject_mask = pd.Series(False, index=result.index)
        for height in blocked_heights:
            reject_mask |= result["z"].sub(height).abs().le(height_tolerance)
        result = result.loc[~(generated_mask & reject_mask)].copy().reset_index(drop=True)

    section_levels = [float(value) for value in review.get("section_levels", [])]
    section_lines = get_section_lines(
        result,
        section_levels,
        height_tolerance=height_tolerance,
    )
    accepted_sections = [
        dict(row)
        for row in rows
        if int(row.get("generated_count", 0) or 0) == 0
        or int(row.get("section_num", 0) or 0) in accepted_section_numbers
    ]
    return result, section_lines, accepted_sections
