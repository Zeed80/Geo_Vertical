"""Model-based completion of missing vertical face tracks for regular towers/masts."""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from core.point_utils import build_working_tower_mask

logger = logging.getLogger(__name__)

SUPPORTED_PART_SHAPES = {"prism", "truncated_pyramid"}
DEFAULT_HEIGHT_TOLERANCE = 0.35
DEFAULT_FACE_SEARCH_MAX = 8


def _normalize_angle(angle_rad: float) -> float:
    return float((angle_rad + 2.0 * math.pi) % (2.0 * math.pi))


def _angular_distance(a_rad: float, b_rad: float) -> float:
    diff = abs(_normalize_angle(a_rad) - _normalize_angle(b_rad))
    return float(min(diff, 2.0 * math.pi - diff))


def _circular_mean(angles_rad: list[float] | np.ndarray) -> float:
    if len(angles_rad) == 0:
        return 0.0
    angles = np.asarray(angles_rad, dtype=float)
    return _normalize_angle(float(math.atan2(np.sin(angles).sum(), np.cos(angles).sum())))


def _fit_circumscribed_circle(xy: np.ndarray) -> tuple[np.ndarray, float]:
    """Fit a circumscribed circle to 2D points with stable fallbacks."""
    n_points = len(xy)
    if n_points == 0:
        return np.zeros(2, dtype=float), 0.0
    if n_points == 1:
        return xy[0].astype(float).copy(), 0.0
    if n_points == 2:
        center = xy.mean(axis=0).astype(float)
        radius = float(np.linalg.norm(xy[0] - center))
        return center, radius

    matrix_a = np.column_stack([2.0 * xy[:, 0], 2.0 * xy[:, 1], np.ones(n_points)])
    vector_b = xy[:, 0] ** 2 + xy[:, 1] ** 2

    try:
        solution, _, rank, singular_values = np.linalg.lstsq(matrix_a, vector_b, rcond=None)
        condition = (
            float(singular_values[0] / max(singular_values[-1], 1e-12))
            if len(singular_values) >= 2
            else 1.0
        )
        if rank < 2 or condition > 1e10:
            raise ValueError("Degenerate circle fit")
        cx, cy, c_term = solution
        radius_sq = float(c_term + cx * cx + cy * cy)
        radius = float(math.sqrt(max(radius_sq, 0.0)))
        return np.array([cx, cy], dtype=float), radius
    except (np.linalg.LinAlgError, ValueError):
        center = xy.mean(axis=0).astype(float)
        radius = float(np.mean(np.linalg.norm(xy - center, axis=1)))
        return center, radius


def _fit_linear_model(z_values: np.ndarray, target_values: np.ndarray) -> tuple[float, float]:
    if len(z_values) == 0:
        return 0.0, 0.0
    if len(z_values) == 1:
        return 0.0, float(target_values[0])
    slope, intercept = np.polyfit(z_values.astype(float), target_values.astype(float), deg=1)
    return float(slope), float(intercept)


def _cluster_height_levels_from_z(z_values: np.ndarray, tolerance: float = DEFAULT_HEIGHT_TOLERANCE) -> np.ndarray:
    if len(z_values) == 0:
        return np.array([], dtype=int)
    order = np.argsort(z_values)
    sorted_z = z_values[order]
    labels = np.ones(len(sorted_z), dtype=int)
    for idx in range(1, len(sorted_z)):
        if float(sorted_z[idx] - sorted_z[idx - 1]) > float(tolerance):
            labels[idx] = labels[idx - 1] + 1
        else:
            labels[idx] = labels[idx - 1]
    result = np.zeros(len(z_values), dtype=int)
    result[order] = labels
    return result


def _model_sse(z_values: np.ndarray, radius_values: np.ndarray, shape: str) -> tuple[float, tuple[float, float]]:
    if len(z_values) == 0:
        return 0.0, (0.0, 0.0)
    if shape == "prism":
        intercept = float(np.mean(radius_values))
        predictions = np.full(len(radius_values), intercept, dtype=float)
        sse = float(np.sum((radius_values - predictions) ** 2))
        return sse, (0.0, intercept)
    slope, intercept = _fit_linear_model(z_values, radius_values)
    predictions = slope * z_values + intercept
    sse = float(np.sum((radius_values - predictions) ** 2))
    return sse, (slope, intercept)


def _bic_score(sample_count: int, sse: float, parameter_count: int) -> float:
    if sample_count <= 0:
        return float("inf")
    normalized = max(float(sse) / max(sample_count, 1), 1e-12)
    return float(sample_count * math.log(normalized) + parameter_count * math.log(max(sample_count, 2)))


def _track_column(data: pd.DataFrame) -> str | None:
    for column_name in ("part_face_track", "face_track", "part_belt", "belt"):
        if column_name not in data.columns:
            continue
        values = pd.to_numeric(data[column_name], errors="coerce")
        if (values > 0).any():
            return column_name
    return None


def _ensure_height_levels(data: pd.DataFrame, tolerance: float = DEFAULT_HEIGHT_TOLERANCE) -> pd.DataFrame:
    return normalize_working_height_levels(data, tolerance=tolerance)


def normalize_working_height_levels(
    data: pd.DataFrame,
    tolerance: float = DEFAULT_HEIGHT_TOLERANCE,
    *,
    force: bool = False,
) -> pd.DataFrame:
    prepared = data.copy()
    if prepared.empty:
        if "height_level" not in prepared.columns:
            prepared["height_level"] = pd.Series(dtype=int)
        return prepared

    if "height_level" not in prepared.columns:
        prepared["height_level"] = 0

    numeric = pd.to_numeric(prepared["height_level"], errors="coerce").fillna(0)
    prepared["height_level"] = numeric.astype(int)

    if "z" not in prepared.columns:
        return prepared

    working_mask = build_working_tower_mask(prepared)
    numeric_z = pd.to_numeric(prepared["z"], errors="coerce")
    working_index = prepared.index[working_mask & numeric_z.notna()]
    if len(working_index) == 0:
        return prepared

    current_levels = prepared.loc[working_index, "height_level"]
    if not force and (current_levels > 0).all():
        return prepared

    prepared.loc[working_index, "height_level"] = _cluster_height_levels_from_z(
        numeric_z.loc[working_index].to_numpy(dtype=float),
        tolerance=tolerance,
    )
    return prepared


def _assign_parts_by_ranges(
    data: pd.DataFrame,
    part_specs: list["CompletionPartSpec"],
) -> np.ndarray:
    assignments = np.zeros(len(data), dtype=int)
    if not part_specs:
        return assignments

    sorted_specs = sorted(part_specs, key=lambda item: (item.z_min, item.part_number))
    last_index = len(sorted_specs) - 1
    z_values = pd.to_numeric(data["z"], errors="coerce").to_numpy(dtype=float)
    for row_idx, z_value in enumerate(z_values):
        if not np.isfinite(z_value):
            continue
        for spec_idx, spec in enumerate(sorted_specs):
            upper_inclusive = spec_idx == last_index
            in_range = spec.z_min <= z_value <= spec.z_max if upper_inclusive else spec.z_min <= z_value < spec.z_max
            if in_range:
                assignments[row_idx] = int(spec.part_number)
                break
    return assignments


def _next_point_index(data: pd.DataFrame) -> int:
    if "point_index" not in data.columns:
        return 1
    values = pd.to_numeric(data["point_index"], errors="coerce").dropna()
    if values.empty:
        return 1
    return int(values.max()) + 1


def _suggested_name(global_track: int, height_level: int, point_index: int) -> str:
    return f"GEN_FT{global_track}_L{height_level}_{point_index}"


def _safe_part_memberships(part_number: int) -> str:
    return json.dumps([int(part_number)], ensure_ascii=False)


def _expand_range_if_flat(z_min: float, z_max: float, epsilon: float = 0.1) -> tuple[float, float]:
    if z_max <= z_min:
        return float(z_min), float(z_min + epsilon)
    return float(z_min), float(z_max)


def _consolidate_levels(data: pd.DataFrame, *, track_col: str) -> list[dict[str, Any]]:
    consolidated: list[dict[str, Any]] = []
    grouped = (
        data.groupby(["height_level", track_col], dropna=True)
        .agg({"x": "mean", "y": "mean", "z": "mean"})
        .reset_index()
    )
    grouped["height_level"] = pd.to_numeric(grouped["height_level"], errors="coerce").fillna(0).astype(int)
    grouped[track_col] = pd.to_numeric(grouped[track_col], errors="coerce").fillna(0).astype(int)
    grouped = grouped[(grouped["height_level"] > 0) & (grouped[track_col] > 0)].copy()

    for height_level, level_group in grouped.groupby("height_level", sort=True):
        points = []
        for _, row in level_group.sort_values(track_col).iterrows():
            points.append(
                {
                    "track": int(row[track_col]),
                    "x": float(row["x"]),
                    "y": float(row["y"]),
                    "z": float(row["z"]),
                }
            )
        if not points:
            continue
        consolidated.append(
            {
                "height_level": int(height_level),
                "z": float(np.mean([point["z"] for point in points])),
                "points": points,
            }
        )
    return consolidated


def _score_face_count_from_geometry(
    consolidated_levels: list[dict[str, Any]],
    faces: int,
) -> float:
    if faces < 3:
        return float("inf")

    step = 2.0 * math.pi / faces
    total_error = 0.0
    total_points = 0
    usable_levels = 0

    for level_info in consolidated_levels:
        points = level_info["points"]
        if len(points) < 3:
            continue
        max_track = max(point["track"] for point in points)
        if max_track > faces:
            return float("inf")
        xy = np.array([[point["x"], point["y"]] for point in points], dtype=float)
        center_xy, _ = _fit_circumscribed_circle(xy)
        phase_candidates = []
        for point in points:
            angle = math.atan2(point["y"] - center_xy[1], point["x"] - center_xy[0])
            phase_candidates.append(angle - step * (point["track"] - 1))
        phase = _circular_mean(phase_candidates)
        level_error = 0.0
        for point in points:
            angle = math.atan2(point["y"] - center_xy[1], point["x"] - center_xy[0])
            target = phase + step * (point["track"] - 1)
            level_error += _angular_distance(angle, target) ** 2
        total_error += level_error
        total_points += len(points)
        usable_levels += 1

    if usable_levels == 0 or total_points == 0:
        return float("inf")

    return float(total_error / total_points + 0.004 * faces)


def suggest_face_count(
    data: pd.DataFrame,
    *,
    default_faces: int | None = None,
    max_faces: int = DEFAULT_FACE_SEARCH_MAX,
) -> int:
    working = data.copy()
    track_col = _track_column(working)
    if track_col is None or working.empty:
        return max(3, int(default_faces or 4))

    working = _ensure_height_levels(working)
    working[track_col] = pd.to_numeric(working[track_col], errors="coerce")
    working = working[working[track_col] > 0].copy()
    if working.empty:
        return max(3, int(default_faces or 4))

    consolidated_levels = _consolidate_levels(working, track_col=track_col)
    observed_max = int(pd.to_numeric(working[track_col], errors="coerce").max())
    candidate_max = max(observed_max, int(default_faces or 0), 4)
    candidate_max = min(max_faces, candidate_max + 2)

    best_faces = max(3, observed_max, int(default_faces or 0))
    best_score = float("inf")
    for candidate_faces in range(max(3, observed_max), max(candidate_max, 3) + 1):
        score = _score_face_count_from_geometry(consolidated_levels, candidate_faces)
        if score < best_score:
            best_score = score
            best_faces = candidate_faces

    return int(best_faces)


@dataclass(slots=True)
class CompletionPartSpec:
    part_number: int
    z_min: float
    z_max: float
    shape: str = "prism"
    faces: int = 4
    label: str | None = None
    source: str = "inferred"

    def validate(self) -> None:
        if self.shape not in SUPPORTED_PART_SHAPES:
            raise ValueError(f"Unsupported part shape: {self.shape}")
        if int(self.faces) < 3:
            raise ValueError("Part must have at least 3 faces")
        if not np.isfinite(self.z_min) or not np.isfinite(self.z_max) or self.z_max <= self.z_min:
            raise ValueError("Invalid part height range")


@dataclass(slots=True)
class FittedPartModel:
    spec: CompletionPartSpec
    center_x_slope: float
    center_x_intercept: float
    center_y_slope: float
    center_y_intercept: float
    radius_slope: float
    radius_intercept: float
    rotation_rad: float
    track_direction: int
    global_track_offset: int
    observed_tracks: tuple[int, ...]
    target_tracks: tuple[int, ...]
    levels: tuple[dict[str, Any], ...]

    def center_at(self, z_value: float) -> np.ndarray:
        return np.array(
            [
                self.center_x_slope * z_value + self.center_x_intercept,
                self.center_y_slope * z_value + self.center_y_intercept,
            ],
            dtype=float,
        )

    def radius_at(self, z_value: float) -> float:
        radius = self.radius_slope * z_value + self.radius_intercept
        return float(max(radius, 1e-6))

    def angle_for_track(self, local_track: int) -> float:
        step = 2.0 * math.pi / self.spec.faces
        return _normalize_angle(self.rotation_rad + self.track_direction * step * (local_track - 1))

    def global_track_for(self, local_track: int) -> int:
        return int(self.global_track_offset + local_track)


def _build_radius_profile(data: pd.DataFrame) -> pd.DataFrame:
    track_col = _track_column(data)
    if track_col is None:
        return pd.DataFrame(columns=["height_level", "z", "radius"])

    prepared = _ensure_height_levels(data)
    consolidated_levels = _consolidate_levels(prepared, track_col=track_col)
    rows = []
    for level_info in consolidated_levels:
        if len(level_info["points"]) < 2:
            continue
        xy = np.array([[point["x"], point["y"]] for point in level_info["points"]], dtype=float)
        center_xy, _ = _fit_circumscribed_circle(xy)
        radii = np.linalg.norm(xy - center_xy, axis=1)
        rows.append(
            {
                "height_level": int(level_info["height_level"]),
                "z": float(level_info["z"]),
                "radius": float(np.mean(radii)),
            }
        )
    return pd.DataFrame(rows).sort_values("z").reset_index(drop=True)


def _infer_shape_from_profile(z_values: np.ndarray, radius_values: np.ndarray) -> tuple[str, tuple[float, float]]:
    prism_sse, prism_params = _model_sse(z_values, radius_values, "prism")
    prism_bic = _bic_score(len(z_values), prism_sse, 1)

    if len(z_values) < 3:
        return "prism", prism_params

    pyramid_sse, pyramid_params = _model_sse(z_values, radius_values, "truncated_pyramid")
    pyramid_bic = _bic_score(len(z_values), pyramid_sse, 2)
    if pyramid_bic + 2.0 < prism_bic and abs(pyramid_params[0]) > 1e-4:
        return "truncated_pyramid", pyramid_params
    return "prism", prism_params


def _fit_rotation_and_direction(
    level_records: list[dict[str, Any]],
    *,
    faces: int,
    center_x_slope: float,
    center_x_intercept: float,
    center_y_slope: float,
    center_y_intercept: float,
) -> tuple[float, int]:
    step = 2.0 * math.pi / faces
    best_rotation = 0.0
    best_direction = 1
    best_error = float("inf")

    for direction in (1, -1):
        phase_candidates: list[float] = []
        samples: list[tuple[float, float]] = []
        for level_info in level_records:
            z_value = float(level_info["z"])
            center_x = center_x_slope * z_value + center_x_intercept
            center_y = center_y_slope * z_value + center_y_intercept
            for point in sorted(level_info["points"], key=lambda item: int(item["track"])):
                angle = math.atan2(point["y"] - center_y, point["x"] - center_x)
                phase_candidates.append(angle - direction * step * (point["track"] - 1))
                samples.append((angle, float(point["track"])))

        if not phase_candidates:
            continue

        rotation = _circular_mean(phase_candidates)
        error = 0.0
        for angle, track in samples:
            target = rotation + direction * step * (track - 1)
            error += _angular_distance(angle, target) ** 2

        if error < best_error:
            best_error = error
            best_rotation = rotation
            best_direction = direction

    return float(best_rotation), int(best_direction)


def infer_completion_part_specs(
    data: pd.DataFrame,
    *,
    default_faces: int | None = None,
) -> list[CompletionPartSpec]:
    working_mask = build_working_tower_mask(data)
    working = data.loc[working_mask].copy() if len(data) else data.copy()
    working = working.dropna(subset=["x", "y", "z"])
    if working.empty:
        return [CompletionPartSpec(part_number=1, z_min=0.0, z_max=1.0, faces=max(3, int(default_faces or 4)))]

    working = _ensure_height_levels(working)

    if "tower_part" in working.columns:
        part_values = pd.to_numeric(working["tower_part"], errors="coerce")
        unique_parts = sorted({int(value) for value in part_values.dropna().tolist() if int(value) > 0})
        if len(unique_parts) > 1:
            part_specs = []
            for part_number in unique_parts:
                part_data = working[part_values.fillna(0).astype(int) == part_number].copy()
                if part_data.empty:
                    continue
                faces = max(int(default_faces or 0), suggest_face_count(part_data, default_faces=default_faces))
                profile = _build_radius_profile(part_data)
                shape = "prism"
                if len(profile) >= 3:
                    shape, _ = _infer_shape_from_profile(profile["z"].to_numpy(), profile["radius"].to_numpy())
                z_min, z_max = _expand_range_if_flat(float(part_data["z"].min()), float(part_data["z"].max()))
                part_specs.append(
                    CompletionPartSpec(
                        part_number=part_number,
                        z_min=z_min,
                        z_max=z_max,
                        shape=shape,
                        faces=faces,
                        label=f"Part {part_number}",
                        source="data",
                    )
                )
            if part_specs:
                return sorted(part_specs, key=lambda item: (item.z_min, item.part_number))

    profile = _build_radius_profile(working)
    faces = max(int(default_faces or 0), suggest_face_count(working, default_faces=default_faces))
    if len(profile) < 4:
        shape, _ = _infer_shape_from_profile(profile["z"].to_numpy(), profile["radius"].to_numpy())
        z_min, z_max = _expand_range_if_flat(float(working["z"].min()), float(working["z"].max()))
        return [
            CompletionPartSpec(
                part_number=1,
                z_min=z_min,
                z_max=z_max,
                shape=shape,
                faces=faces,
                label="Part 1",
                source="inferred",
            )
        ]

    one_shape, _ = _infer_shape_from_profile(profile["z"].to_numpy(), profile["radius"].to_numpy())
    one_sse, _ = _model_sse(
        profile["z"].to_numpy(dtype=float),
        profile["radius"].to_numpy(dtype=float),
        one_shape,
    )
    one_bic = _bic_score(len(profile), one_sse, 2 if one_shape == "truncated_pyramid" else 1)

    best_split: dict[str, Any] | None = None
    for split_idx in range(2, len(profile) - 1):
        left = profile.iloc[:split_idx].copy()
        right = profile.iloc[split_idx:].copy()
        if len(left) < 2 or len(right) < 2:
            continue
        left_shape, _ = _infer_shape_from_profile(left["z"].to_numpy(), left["radius"].to_numpy())
        right_shape, _ = _infer_shape_from_profile(right["z"].to_numpy(), right["radius"].to_numpy())
        left_sse, _ = _model_sse(left["z"].to_numpy(dtype=float), left["radius"].to_numpy(dtype=float), left_shape)
        right_sse, _ = _model_sse(right["z"].to_numpy(dtype=float), right["radius"].to_numpy(dtype=float), right_shape)
        left_bic = _bic_score(len(left), left_sse, 2 if left_shape == "truncated_pyramid" else 1)
        right_bic = _bic_score(len(right), right_sse, 2 if right_shape == "truncated_pyramid" else 1)
        total_bic = left_bic + right_bic
        if best_split is None or total_bic < best_split["bic"]:
            boundary = float((left["z"].iloc[-1] + right["z"].iloc[0]) / 2.0)
            best_split = {
                "bic": total_bic,
                "boundary": boundary,
                "left_shape": left_shape,
                "right_shape": right_shape,
            }

    if best_split is not None and best_split["bic"] + 6.0 < one_bic:
        z_min = float(working["z"].min())
        z_max = float(working["z"].max())
        boundary = float(best_split["boundary"])
        part1_min, part1_max = _expand_range_if_flat(z_min, boundary)
        part2_min, part2_max = _expand_range_if_flat(boundary, z_max)
        return [
            CompletionPartSpec(
                part_number=1,
                z_min=part1_min,
                z_max=part1_max,
                shape=str(best_split["left_shape"]),
                faces=faces,
                label="Part 1",
                source="inferred",
            ),
            CompletionPartSpec(
                part_number=2,
                z_min=part2_min,
                z_max=part2_max,
                shape=str(best_split["right_shape"]),
                faces=faces,
                label="Part 2",
                source="inferred",
            ),
        ]

    z_min, z_max = _expand_range_if_flat(float(working["z"].min()), float(working["z"].max()))
    return [
        CompletionPartSpec(
            part_number=1,
            z_min=z_min,
            z_max=z_max,
            shape=one_shape,
            faces=faces,
            label="Part 1",
            source="inferred",
        )
    ]


def build_completion_part_specs(
    data: pd.DataFrame,
    *,
    blueprint: Any | None = None,
    default_faces: int | None = None,
) -> list[CompletionPartSpec]:
    inferred_specs = infer_completion_part_specs(data, default_faces=default_faces)

    segments = getattr(blueprint, "segments", None) if blueprint is not None else None
    if not segments:
        return inferred_specs

    tower_data = data.loc[build_working_tower_mask(data)].copy()
    tower_data = tower_data.dropna(subset=["z"])
    if tower_data.empty:
        return inferred_specs

    z_base = float(tower_data["z"].min())
    blueprint_specs: list[CompletionPartSpec] = []
    cursor = z_base
    for part_index, segment in enumerate(segments, start=1):
        height = float(getattr(segment, "height", 0.0) or 0.0)
        if height <= 0:
            continue
        next_cursor = cursor + height
        blueprint_specs.append(
            CompletionPartSpec(
                part_number=part_index,
                z_min=cursor,
                z_max=next_cursor,
                shape=str(getattr(segment, "shape", "prism") or "prism"),
                faces=int(getattr(segment, "faces", default_faces or 4) or (default_faces or 4)),
                label=str(getattr(segment, "name", f"Part {part_index}") or f"Part {part_index}"),
                source="blueprint",
            )
        )
        cursor = next_cursor

    if len(blueprint_specs) == 1 and len(inferred_specs) > 1:
        return inferred_specs

    if len(blueprint_specs) > 1 or any(spec.shape != "prism" for spec in blueprint_specs):
        return blueprint_specs

    return inferred_specs or blueprint_specs


class FaceTrackCompleter:
    """Model-based completion of globally missing vertical face tracks."""

    def __init__(self, data: pd.DataFrame, part_specs: list[CompletionPartSpec]) -> None:
        self._data = data.copy(deep=True)
        self._part_specs = sorted(part_specs, key=lambda item: (item.z_min, item.part_number))
        for spec in self._part_specs:
            spec.validate()
        for previous, current in zip(self._part_specs, self._part_specs[1:]):
            if previous.z_max > current.z_min:
                raise ValueError(
                    f"Overlapping part ranges: part {previous.part_number} [{previous.z_min:.3f}, {previous.z_max:.3f}] "
                    f"and part {current.part_number} [{current.z_min:.3f}, {current.z_max:.3f}]"
                )
        self._fitted_models: list[FittedPartModel] | None = None

    @property
    def part_specs(self) -> list[CompletionPartSpec]:
        return list(self._part_specs)

    def _prepared_working_data(self) -> pd.DataFrame:
        working_mask = build_working_tower_mask(self._data)
        working = self._data.loc[working_mask].copy() if len(self._data) else self._data.copy()
        working = working.dropna(subset=["x", "y", "z"])
        working = _ensure_height_levels(working)
        assignments = _assign_parts_by_ranges(working, self._part_specs)
        working["tower_part_completion"] = assignments
        return working

    def _global_offset_for_part(self, part_data: pd.DataFrame, spec_index: int) -> int:
        if {"face_track", "part_face_track"}.issubset(part_data.columns):
            global_track = pd.to_numeric(part_data["face_track"], errors="coerce")
            local_track = pd.to_numeric(part_data["part_face_track"], errors="coerce")
            valid = (global_track > 0) & (local_track > 0)
            if valid.any():
                diff_values = (global_track[valid] - local_track[valid]).round().astype(int)
                if not diff_values.empty:
                    return int(diff_values.mode().iloc[0])

        if "tower_part" in self._data.columns:
            observed = pd.to_numeric(self._data["tower_part"], errors="coerce")
            if observed.dropna().nunique() > 1:
                offset = 0
                for idx, previous in enumerate(self._part_specs):
                    if idx >= spec_index:
                        break
                    offset += int(previous.faces)
                return offset
        return 0

    def _fit_part_model(self, part_data: pd.DataFrame, spec: CompletionPartSpec, spec_index: int) -> FittedPartModel | None:
        track_col = _track_column(part_data)
        if track_col is None or part_data.empty:
            return None

        consolidated_levels = _consolidate_levels(part_data, track_col=track_col)
        if not consolidated_levels:
            return None

        observed_tracks = sorted(
            {
                int(point["track"])
                for level_info in consolidated_levels
                for point in level_info["points"]
                if int(point["track"]) > 0
            }
        )
        target_tracks = tuple(track for track in range(1, spec.faces + 1) if track not in observed_tracks)
        if not target_tracks:
            return None

        level_centers = []
        for level_info in consolidated_levels:
            points = level_info["points"]
            xy = np.array([[point["x"], point["y"]] for point in points], dtype=float)
            if len(points) >= 3:
                center_xy, _ = _fit_circumscribed_circle(xy)
                level_centers.append((float(level_info["z"]), center_xy[0], center_xy[1]))

        if level_centers:
            centers_df = pd.DataFrame(level_centers, columns=["z", "cx", "cy"])
            slope_x, intercept_x = _fit_linear_model(centers_df["z"].to_numpy(), centers_df["cx"].to_numpy())
            slope_y, intercept_y = _fit_linear_model(centers_df["z"].to_numpy(), centers_df["cy"].to_numpy())
        else:
            slope_x = 0.0
            intercept_x = float(part_data["x"].mean())
            slope_y = 0.0
            intercept_y = float(part_data["y"].mean())

        radius_rows = []
        level_records: list[dict[str, Any]] = []
        for level_info in consolidated_levels:
            z_value = float(level_info["z"])
            center_xy = np.array(
                [
                    slope_x * z_value + intercept_x,
                    slope_y * z_value + intercept_y,
                ],
                dtype=float,
            )
            level_points = []
            radii = []
            for point in level_info["points"]:
                radius = float(math.hypot(point["x"] - center_xy[0], point["y"] - center_xy[1]))
                radii.append(radius)
                level_points.append(
                    {
                        "track": int(point["track"]),
                        "x": float(point["x"]),
                        "y": float(point["y"]),
                        "z": float(point["z"]),
                    }
                )
            radius_rows.append({"z": z_value, "radius": float(np.mean(radii)) if radii else 0.0})
            level_records.append(
                {
                    "height_level": int(level_info["height_level"]),
                    "z": z_value,
                    "points": tuple(level_points),
                }
            )

        rotation_rad, track_direction = _fit_rotation_and_direction(
            level_records,
            faces=spec.faces,
            center_x_slope=slope_x,
            center_x_intercept=intercept_x,
            center_y_slope=slope_y,
            center_y_intercept=intercept_y,
        )
        radius_df = pd.DataFrame(radius_rows)
        if spec.shape == "truncated_pyramid":
            radius_slope, radius_intercept = _fit_linear_model(
                radius_df["z"].to_numpy(dtype=float),
                radius_df["radius"].to_numpy(dtype=float),
            )
        else:
            radius_slope = 0.0
            radius_intercept = float(radius_df["radius"].median())

        return FittedPartModel(
            spec=spec,
            center_x_slope=slope_x,
            center_x_intercept=intercept_x,
            center_y_slope=slope_y,
            center_y_intercept=intercept_y,
            radius_slope=radius_slope,
            radius_intercept=radius_intercept,
            rotation_rad=rotation_rad,
            track_direction=track_direction,
            global_track_offset=self._global_offset_for_part(part_data, spec_index),
            observed_tracks=tuple(observed_tracks),
            target_tracks=target_tracks,
            levels=tuple(level_records),
        )

    def _fit_models(self) -> list[FittedPartModel]:
        if self._fitted_models is not None:
            return list(self._fitted_models)

        working = self._prepared_working_data()
        models: list[FittedPartModel] = []
        for spec_index, spec in enumerate(self._part_specs):
            part_data = working[working["tower_part_completion"] == int(spec.part_number)].copy()
            model = self._fit_part_model(part_data, spec, spec_index)
            if model is not None:
                models.append(model)
        self._fitted_models = models
        return list(models)

    def analyze(self) -> list[dict[str, Any]]:
        analyses: list[dict[str, Any]] = []
        for model in self._fit_models():
            points_to_add = 0
            for level_info in model.levels:
                existing_tracks = {int(point["track"]) for point in level_info["points"]}
                points_to_add += sum(1 for track in model.target_tracks if track not in existing_tracks)
            analyses.append(
                {
                    "part_number": model.spec.part_number,
                    "label": model.spec.label or f"Part {model.spec.part_number}",
                    "shape": model.spec.shape,
                    "faces": int(model.spec.faces),
                    "z_min": float(model.spec.z_min),
                    "z_max": float(model.spec.z_max),
                    "level_count": len(model.levels),
                    "observed_tracks": list(model.observed_tracks),
                    "missing_tracks": list(model.target_tracks),
                    "points_to_add": int(points_to_add),
                }
            )
        return analyses

    def _resolve_z_for_track(self, model: FittedPartModel, level_info: dict[str, Any], target_track: int, z_method: str) -> tuple[float, int | None]:
        level_points = {int(point["track"]): point for point in level_info["points"]}
        if z_method == "diagonal":
            if model.spec.faces % 2 == 0:
                opposite_track = ((target_track - 1 + (model.spec.faces // 2)) % model.spec.faces) + 1
                if opposite_track in level_points:
                    return float(level_points[opposite_track]["z"]), int(opposite_track)
            else:
                opposite_base = (target_track - 1 + model.spec.faces / 2.0) % model.spec.faces
                candidate_tracks = {
                    int(math.floor(opposite_base) % model.spec.faces) + 1,
                    int(math.ceil(opposite_base) % model.spec.faces) + 1,
                }
                z_values = [float(level_points[track]["z"]) for track in candidate_tracks if track in level_points]
                if z_values:
                    return float(np.mean(z_values)), None

        z_values = [float(point["z"]) for point in level_info["points"]]
        if z_values:
            return float(np.mean(z_values)), None
        return float(level_info["z"]), None

    def _build_generated_row(
        self,
        *,
        merged: pd.DataFrame,
        template_row: pd.Series,
        model: FittedPartModel,
        height_level: int,
        local_track: int,
        x_value: float,
        y_value: float,
        z_value: float,
        point_index: int,
        z_source_track: int | None,
    ) -> dict[str, Any]:
        row = template_row.to_dict()
        global_track = model.global_track_for(local_track)
        row["name"] = _suggested_name(global_track, height_level, point_index)
        row["x"] = float(x_value)
        row["y"] = float(y_value)
        row["z"] = float(z_value)
        row["is_generated"] = True
        row["generated_by"] = "face_track_completion"
        row["completion_shape"] = model.spec.shape
        row["completion_part"] = int(model.spec.part_number)
        row["completion_local_track"] = int(local_track)
        row["completion_z_source_track"] = int(z_source_track) if z_source_track is not None else pd.NA
        row["height_level"] = int(height_level)
        row["tower_part"] = int(model.spec.part_number)
        row["tower_part_memberships"] = _safe_part_memberships(model.spec.part_number)
        row["is_part_boundary"] = False
        row["faces"] = int(model.spec.faces)
        row["part_face_track"] = int(local_track)
        row["part_belt"] = int(local_track)
        row["face_track"] = int(global_track)
        row["belt"] = int(global_track)
        row["is_station"] = False
        row["is_auxiliary"] = False
        row["is_control"] = False
        if "cw_angle_deg" in merged.columns:
            row["cw_angle_deg"] = pd.NA
        if "point_index" in merged.columns:
            row["point_index"] = int(point_index)
        return row

    def preview(self, *, z_method: str = "diagonal") -> tuple[pd.DataFrame, pd.DataFrame]:
        merged = self._data.copy(deep=True)
        if merged.empty:
            return merged, pd.DataFrame()

        if "tower_part" not in merged.columns:
            merged["tower_part"] = 1
        if "tower_part_memberships" not in merged.columns:
            merged["tower_part_memberships"] = None
        if "is_part_boundary" not in merged.columns:
            merged["is_part_boundary"] = False
        if "part_face_track" not in merged.columns and "face_track" in merged.columns:
            merged["part_face_track"] = merged["face_track"]
        if "part_belt" not in merged.columns and "belt" in merged.columns:
            merged["part_belt"] = merged["belt"]
        if "is_generated" not in merged.columns:
            merged["is_generated"] = False
        if "generated_by" not in merged.columns:
            merged["generated_by"] = None
        merged = normalize_working_height_levels(merged)

        assignments = _assign_parts_by_ranges(merged, self._part_specs)
        working_mask = build_working_tower_mask(merged)
        for spec in self._part_specs:
            part_mask = working_mask & (assignments == int(spec.part_number))
            if part_mask.any():
                merged.loc[part_mask, "tower_part"] = int(spec.part_number)
                merged.loc[part_mask, "tower_part_memberships"] = _safe_part_memberships(spec.part_number)
                merged.loc[part_mask, "is_part_boundary"] = False
                merged.loc[part_mask, "faces"] = int(spec.faces)

        generated_rows: list[dict[str, Any]] = []
        next_point_index = _next_point_index(merged)
        for model in self._fit_models():
            part_rows = merged.loc[working_mask & (assignments == int(model.spec.part_number))].copy()
            if part_rows.empty:
                continue
            part_rows = _ensure_height_levels(part_rows)
            template_row = part_rows.iloc[0]
            for level_info in model.levels:
                existing_tracks = {int(point["track"]) for point in level_info["points"]}
                level_rows = part_rows[
                    pd.to_numeric(part_rows["height_level"], errors="coerce").fillna(0).astype(int)
                    == int(level_info["height_level"])
                ]
                level_template = level_rows.iloc[0] if not level_rows.empty else template_row
                for local_track in model.target_tracks:
                    if local_track in existing_tracks:
                        continue
                    z_value, z_source_track = self._resolve_z_for_track(model, level_info, local_track, z_method)
                    center_xy = model.center_at(z_value)
                    radius = model.radius_at(z_value)
                    angle = model.angle_for_track(local_track)
                    x_value = center_xy[0] + radius * math.cos(angle)
                    y_value = center_xy[1] + radius * math.sin(angle)
                    generated_rows.append(
                        self._build_generated_row(
                            merged=merged,
                            template_row=level_template,
                            model=model,
                            height_level=int(level_info["height_level"]),
                            local_track=int(local_track),
                            x_value=float(x_value),
                            y_value=float(y_value),
                            z_value=float(z_value),
                            point_index=next_point_index,
                            z_source_track=z_source_track,
                        )
                    )
                    next_point_index += 1

        generated = pd.DataFrame(generated_rows)
        if generated.empty:
            return merged, generated

        for column_name in generated.columns:
            if column_name not in merged.columns:
                merged[column_name] = pd.NA
        for column_name in merged.columns:
            if column_name not in generated.columns:
                generated[column_name] = pd.NA

        generated = generated[merged.columns.tolist()]
        merged = pd.concat([merged, generated], ignore_index=True)
        return merged, generated

    def to_blueprint(self, existing_blueprint: Any | None = None) -> Any | None:
        from core.tower_generator import TowerBlueprintV2, TowerSegmentSpec

        models = self._fit_models()
        if not models:
            return existing_blueprint

        segments = []
        for model in models:
            z_min = float(model.spec.z_min)
            z_max = float(model.spec.z_max)
            base_size = max(model.radius_at(z_min) * 2.0, 0.1)
            top_size = max(model.radius_at(z_max) * 2.0, 0.1)
            if model.spec.shape == "truncated_pyramid" and top_size >= base_size:
                top_size = max(base_size * 0.99, 0.1)
            if model.spec.shape == "prism":
                top_size = base_size
            segments.append(
                TowerSegmentSpec(
                    name=model.spec.label or f"Part {model.spec.part_number}",
                    shape=model.spec.shape,
                    faces=int(model.spec.faces),
                    height=max(z_max - z_min, 0.1),
                    levels=max(len(model.levels), 1),
                    base_size=float(base_size),
                    top_size=float(top_size),
                )
            )

        blueprint_kwargs = {
            "segments": segments,
            "instrument_distance": float(getattr(existing_blueprint, "instrument_distance", 60.0) or 60.0),
            "instrument_angle_deg": float(getattr(existing_blueprint, "instrument_angle_deg", 0.0) or 0.0),
            "instrument_height": float(getattr(existing_blueprint, "instrument_height", 1.7) or 1.7),
            "base_rotation_deg": float(getattr(existing_blueprint, "base_rotation_deg", 0.0) or 0.0),
            "default_deviation_mm": float(getattr(existing_blueprint, "default_deviation_mm", 0.0) or 0.0),
            "metadata": dict(getattr(existing_blueprint, "metadata", {}) or {}),
        }
        return TowerBlueprintV2(**blueprint_kwargs)
