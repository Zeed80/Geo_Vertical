"""Helpers for automatic Method 2 matching and preview for second-station import."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment

from core.planar_orientation import (
    domain_rotation_deg_to_math_rad,
    domain_signed_angle_deg,
    extract_reference_station_xy,
    normalize_signed_angle_deg,
    observer_left_to_right_order_indices,
)
from core.survey_registration import (
    apply_helmert_transform,
    compute_helmert_parameters,
    rotate_points_around_z,
    shift_points_along_z,
    translate_points_xy,
)


def _regular_points(data: pd.DataFrame) -> pd.DataFrame:
    if data is None or data.empty:
        return pd.DataFrame(columns=list(data.columns) if data is not None else [])

    working = data.copy()
    if "is_station" in working.columns:
        station_mask = working["is_station"].fillna(False).astype(bool)
        working = working[~station_mask]
    return working


def _station_points(data: pd.DataFrame) -> pd.DataFrame:
    if data is None or data.empty:
        return pd.DataFrame(columns=list(data.columns) if data is not None else [])

    if "is_station" in data.columns:
        station_mask = data["is_station"].fillna(False).astype(bool)
        stations = data[station_mask].copy()
        if not stations.empty:
            return stations

    if "name" in data.columns:
        names = data["name"].astype(str).str.lower()
        return data[names.str.startswith("st")].copy()

    return pd.DataFrame(columns=list(data.columns))


def _first_station_point(data: pd.DataFrame) -> pd.Series | None:
    stations = _station_points(data)
    if stations.empty:
        return None
    return stations.iloc[0]


def _sorted_visible_belts(data: pd.DataFrame) -> list[int]:
    regular = _regular_points(data)
    if "belt" not in regular.columns:
        return []

    belts: list[int] = []
    for value in regular["belt"].dropna():
        try:
            belts.append(int(value))
        except (TypeError, ValueError):
            continue
    return sorted(set(belts))


def _left_to_right_visible_belts(data: pd.DataFrame) -> list[int]:
    regular = _regular_points(data)
    if regular.empty or "belt" not in regular.columns:
        return _sorted_visible_belts(data)

    station_xy = extract_reference_station_xy(data)
    if station_xy is None:
        return _sorted_visible_belts(data)

    tower_center = regular[["x", "y"]].mean().to_numpy(dtype=float)
    belt_numbers: list[int] = []
    centroids: list[np.ndarray] = []
    for belt in _sorted_visible_belts(data):
        belt_points = regular[regular["belt"] == belt]
        if belt_points.empty:
            continue
        centroid = belt_points[["x", "y"]].mean().to_numpy(dtype=float)
        belt_numbers.append(int(belt))
        centroids.append(np.asarray(centroid, dtype=float))

    if not centroids:
        return []

    order = observer_left_to_right_order_indices(
        np.array(centroids, dtype=float),
        tower_center_xy=tower_center,
        station_xy=station_xy,
    )
    return [belt_numbers[int(idx)] for idx in order]


def _normalize_angle_deg(angle_deg: float) -> float:
    return normalize_signed_angle_deg(angle_deg)


def _iter_neighbor_candidates(
    data: pd.DataFrame,
    base_point: pd.Series,
    *,
    height_tolerance: float,
) -> list[dict[str, Any]]:
    """Return visible neighboring belts that have a point near the base height."""
    regular = _regular_points(data)
    if regular.empty or "belt" not in regular.columns:
        return []

    try:
        base_belt = int(base_point["belt"])
    except (TypeError, ValueError, KeyError):
        return []

    visible_belts = _sorted_visible_belts(data)
    if base_belt not in visible_belts:
        return []

    base_height = float(base_point["z"])
    base_xy = np.array([float(base_point["x"]), float(base_point["y"])], dtype=float)
    neighbors: list[dict[str, Any]] = []

    for candidate_belt in visible_belts:
        if candidate_belt == base_belt:
            continue
        belt_points = regular[
            (regular["belt"] == candidate_belt)
            & (np.abs(regular["z"] - base_height) <= height_tolerance)
        ].copy()
        if belt_points.empty:
            continue

        distances = np.sqrt(
            (belt_points["x"] - base_xy[0]) ** 2
            + (belt_points["y"] - base_xy[1]) ** 2
        )
        nearest_idx = distances.idxmin()
        neighbor_point = belt_points.loc[nearest_idx]
        belt_delta = candidate_belt - base_belt
        neighbors.append(
            {
                "belt": int(candidate_belt),
                "point": neighbor_point,
                "index": nearest_idx,
                "belt_delta": int(belt_delta),
            }
        )

    neighbors.sort(key=lambda item: (abs(item["belt_delta"]), item["belt"]))
    return neighbors


def _compute_signed_angle_delta(
    existing_base: pd.Series,
    existing_neighbor: pd.Series,
    second_base: pd.Series,
    second_neighbor: pd.Series,
    *,
    target_angle_deg: float,
    prefer_clockwise: bool | None = None,
) -> dict[str, Any] | None:
    v1 = np.array(
        [
            float(existing_neighbor["x"]) - float(existing_base["x"]),
            float(existing_neighbor["y"]) - float(existing_base["y"]),
        ],
        dtype=float,
    )
    v2 = np.array(
        [
            float(second_neighbor["x"]) - float(second_base["x"]),
            float(second_neighbor["y"]) - float(second_base["y"]),
        ],
        dtype=float,
    )

    norm1 = float(np.linalg.norm(v1))
    norm2 = float(np.linalg.norm(v2))
    if norm1 <= 1e-9 or norm2 <= 1e-9:
        return None

    u1 = v1 / norm1
    u2 = v2 / norm2
    dot = float(np.clip(np.dot(u1, u2), -1.0, 1.0))
    det = float(u1[0] * u2[1] - u1[1] * u2[0])
    measured_deg = float(domain_signed_angle_deg(u1, u2))

    if prefer_clockwise is True:
        directions = (1,)
    elif prefer_clockwise is False:
        directions = (-1,)
    else:
        directions = (1, -1)

    best_candidate: dict[str, Any] | None = None
    for direction in directions:
        target_signed_deg = abs(float(target_angle_deg)) if direction > 0 else -abs(float(target_angle_deg))
        delta_deg = _normalize_angle_deg(target_signed_deg - measured_deg)
        rotation_error_deg = abs(abs(delta_deg) - abs(float(target_angle_deg)))
        candidate = {
            "angle_rad": float(domain_rotation_deg_to_math_rad(delta_deg)),
            "angle_deg": float(delta_deg),
            "direction": int(direction),
            "measured_deg": measured_deg,
            "target_signed_deg": float(target_signed_deg),
            "rotation_error_deg": float(rotation_error_deg),
        }
        if best_candidate is None or (
            candidate["rotation_error_deg"],
            abs(candidate["angle_deg"]),
        ) < (
            best_candidate["rotation_error_deg"],
            abs(best_candidate["angle_deg"]),
        ):
            best_candidate = candidate

    return best_candidate


def _apply_method2_transform(
    second_station_data: pd.DataFrame,
    second_base: pd.Series,
    existing_base: pd.Series,
    angle_rad: float,
) -> pd.DataFrame:
    """Apply the Method 2 shift/translate/rotate chain without mutating inputs."""
    delta_z = float(existing_base["z"] - second_base["z"])
    shifted = shift_points_along_z(second_station_data, delta_z)

    if second_base.name not in shifted.index:
        raise KeyError(f"Base point index {second_base.name!r} is missing after Z shift")

    base_xy_after_shift = shifted.loc[second_base.name, ["x", "y"]].to_numpy(dtype=float)
    target_xy = np.array([float(existing_base["x"]), float(existing_base["y"])], dtype=float)
    translate_xy = target_xy - base_xy_after_shift
    translated = translate_points_xy(shifted, float(translate_xy[0]), float(translate_xy[1]))

    rotation_center = np.array(
        [
            float(existing_base["x"]),
            float(existing_base["y"]),
            float(existing_base["z"]),
        ],
        dtype=float,
    )
    return rotate_points_around_z(translated, angle_rad, rotation_center)


def _signed_cyclic_delta(source: int, target: int, faces: int) -> int:
    forward = (target - source) % faces
    backward = forward - faces
    return int(forward if abs(forward) <= abs(backward) else backward)


def _build_expected_visible_mapping(
    existing_data: pd.DataFrame,
    second_station_data: pd.DataFrame,
    *,
    faces: int,
    target_angle_deg: float,
    prefer_clockwise: bool | None,
) -> dict[str, Any] | None:
    if faces <= 0 or prefer_clockwise is None:
        return None

    second_visible = _left_to_right_visible_belts(second_station_data)
    existing_visible = _left_to_right_visible_belts(existing_data)
    if not second_visible:
        return None

    face_angle = 360.0 / float(faces)
    shift_steps = int(round(abs(float(target_angle_deg)) / face_angle))
    if shift_steps <= 0:
        shift_steps = 1
    if prefer_clockwise is False:
        shift_steps = -shift_steps

    global_anchor = int(((-shift_steps) % faces) + 1)
    expected_visible = [
        int(((global_anchor + int(local_belt) - 2) % faces) + 1)
        for local_belt in second_visible
    ]

    belt_mapping = {
        int(local_belt): int(global_belt)
        for local_belt, global_belt in zip(second_visible, expected_visible)
    }
    if not belt_mapping:
        return None

    return {
        "existing_visible_order": existing_visible,
        "second_visible_order_left_to_right": second_visible,
        "expected_visible_mapping_sequence": expected_visible,
        "belt_mapping": belt_mapping,
    }


def _infer_second_belt_mapping(
    second_station_data: pd.DataFrame,
    *,
    faces: int,
    second_base_belt: int,
    existing_base_belt: int,
    second_neighbor_belt: int,
    existing_neighbor_belt: int,
) -> dict[int, int] | None:
    if faces <= 0:
        return None

    second_visible = _sorted_visible_belts(second_station_data)
    if second_base_belt not in second_visible or second_neighbor_belt not in second_visible:
        return None

    delta_second = second_neighbor_belt - second_base_belt
    if delta_second == 0:
        return None

    delta_existing = _signed_cyclic_delta(existing_base_belt, existing_neighbor_belt, faces)
    if delta_existing == 0:
        return None

    orientation = 1 if (delta_second > 0) == (delta_existing > 0) else -1
    mapping: dict[int, int] = {}
    for local_belt in second_visible:
        global_belt_zero_based = (
            (existing_base_belt - 1)
            + orientation * (local_belt - second_base_belt)
        ) % faces
        mapping[int(local_belt)] = int(global_belt_zero_based + 1)

    if mapping.get(second_base_belt) != existing_base_belt:
        return None
    if mapping.get(second_neighbor_belt) != existing_neighbor_belt:
        return None

    return mapping


def _apply_belt_mapping(data: pd.DataFrame, mapping: dict[int, int]) -> pd.DataFrame:
    if not mapping:
        return data.copy()

    remapped = data.copy()
    if "belt" not in remapped.columns:
        return remapped

    def remap_value(value: Any) -> Any:
        if pd.isna(value):
            return value
        try:
            return mapping.get(int(value), int(value))
        except (TypeError, ValueError):
            return value

    remapped["belt"] = remapped["belt"].map(remap_value)
    return remapped


def _score_overlap(
    existing_data: pd.DataFrame,
    transformed_second: pd.DataFrame,
    *,
    shared_belts: set[int],
    height_tolerance: float,
    merge_tolerance: float,
) -> dict[str, Any]:
    existing_regular = _regular_points(existing_data)
    second_regular = _regular_points(transformed_second)

    if shared_belts:
        existing_regular = existing_regular[existing_regular["belt"].isin(shared_belts)].copy()
        second_regular = second_regular[second_regular["belt"].isin(shared_belts)].copy()

    close_distances: list[float] = []
    nearest_distances: list[float] = []

    for _, point in second_regular.iterrows():
        if "belt" not in point or pd.isna(point["belt"]):
            continue
        target_belt = int(point["belt"])
        candidates = existing_regular[
            (existing_regular["belt"] == target_belt)
            & (np.abs(existing_regular["z"] - float(point["z"])) <= height_tolerance)
        ].copy()
        if candidates.empty:
            continue

        distances = np.sqrt(
            (candidates["x"] - float(point["x"])) ** 2
            + (candidates["y"] - float(point["y"])) ** 2
            + (candidates["z"] - float(point["z"])) ** 2
        )
        nearest_distance = float(distances.min())
        nearest_distances.append(nearest_distance)
        if nearest_distance <= merge_tolerance:
            close_distances.append(nearest_distance)

    close_count = len(close_distances)
    close_mean = float(np.mean(close_distances)) if close_distances else math.inf
    trimmed_count = min(max(3, close_count), len(nearest_distances))
    trimmed_mean = (
        float(np.mean(sorted(nearest_distances)[:trimmed_count]))
        if nearest_distances and trimmed_count > 0
        else math.inf
    )

    return {
        "shared_close_count": int(close_count),
        "shared_close_mean": close_mean,
        "shared_trimmed_mean": trimmed_mean,
    }


def _match_points_by_belt_and_height(
    existing_data: pd.DataFrame,
    second_station_data: pd.DataFrame,
    *,
    shared_belts: set[int],
    height_tolerance: float,
) -> list[dict[str, Any]]:
    existing_regular = _regular_points(existing_data)
    second_regular = _regular_points(second_station_data)
    matched_pairs: list[dict[str, Any]] = []

    for belt in sorted(shared_belts):
        existing_belt = existing_regular[existing_regular["belt"] == belt].copy()
        second_belt = second_regular[second_regular["belt"] == belt].copy()
        if existing_belt.empty or second_belt.empty:
            continue

        existing_rows = list(existing_belt.iterrows())
        second_rows = list(second_belt.iterrows())
        cost_matrix = np.full((len(second_rows), len(existing_rows)), 1e6, dtype=float)
        for row_idx, (_, second_point) in enumerate(second_rows):
            for col_idx, (_, existing_point) in enumerate(existing_rows):
                dz = abs(float(second_point["z"]) - float(existing_point["z"]))
                if dz <= height_tolerance:
                    cost_matrix[row_idx, col_idx] = dz

        if cost_matrix.size == 0:
            continue

        row_ind, col_ind = linear_sum_assignment(cost_matrix)
        for row_idx, col_idx in zip(row_ind, col_ind, strict=False):
            dz = float(cost_matrix[int(row_idx), int(col_idx)])
            if dz > height_tolerance:
                continue

            second_index, second_point = second_rows[int(row_idx)]
            existing_index, existing_point = existing_rows[int(col_idx)]
            matched_pairs.append(
                {
                    "belt": int(belt),
                    "height_delta": dz,
                    "second_index": second_index,
                    "existing_index": existing_index,
                    "second_name": str(second_point.get("name", second_index)),
                    "existing_name": str(existing_point.get("name", existing_index)),
                }
            )

    matched_pairs.sort(
        key=lambda item: (
            item["belt"],
            item["height_delta"],
            str(item["existing_name"]),
            str(item["second_name"]),
        )
    )
    return matched_pairs


def _station_angle_delta_deg(
    existing_data: pd.DataFrame,
    transformed_second: pd.DataFrame,
) -> float | None:
    station_existing = _first_station_point(existing_data)
    station_second = _first_station_point(transformed_second)
    existing_regular = _regular_points(existing_data)
    if station_existing is None or station_second is None or existing_regular.empty:
        return None

    tower_center = existing_regular[["x", "y"]].mean().to_numpy(dtype=float)
    v1 = station_existing[["x", "y"]].to_numpy(dtype=float) - tower_center
    v2 = station_second[["x", "y"]].to_numpy(dtype=float) - tower_center
    if float(np.linalg.norm(v1)) <= 1e-9 or float(np.linalg.norm(v2)) <= 1e-9:
        return None

    return float(domain_signed_angle_deg(v1, v2))


def build_method2_preview(
    existing_data: pd.DataFrame,
    second_station_data: pd.DataFrame,
    *,
    existing_index: Any,
    second_index: Any,
    tower_faces: int = 4,
    target_angle_deg: float = 90.0,
    height_tolerance: float = 1.2,
    merge_tolerance: float = 0.35,
    prefer_clockwise: bool | None = None,
) -> dict[str, Any] | None:
    """Build a preview of Method 2 import for a specific pair of points."""
    if existing_index not in existing_data.index or second_index not in second_station_data.index:
        return None

    existing_base = existing_data.loc[existing_index]
    second_base = second_station_data.loc[second_index]

    if pd.isna(existing_base.get("belt")) or pd.isna(second_base.get("belt")):
        return None

    expected_mapping_info = _build_expected_visible_mapping(
        existing_data,
        second_station_data,
        faces=int(tower_faces or 4),
        target_angle_deg=target_angle_deg,
        prefer_clockwise=prefer_clockwise,
    )

    existing_neighbors = _iter_neighbor_candidates(
        existing_data,
        existing_base,
        height_tolerance=height_tolerance,
    )
    second_neighbors = _iter_neighbor_candidates(
        second_station_data,
        second_base,
        height_tolerance=height_tolerance,
    )
    if not existing_neighbors or not second_neighbors:
        return None

    best_preview: dict[str, Any] | None = None
    for existing_neighbor in existing_neighbors:
        for second_neighbor in second_neighbors:
            angle_info = _compute_signed_angle_delta(
                existing_base,
                existing_neighbor["point"],
                second_base,
                second_neighbor["point"],
                target_angle_deg=target_angle_deg,
                prefer_clockwise=prefer_clockwise,
            )
            if angle_info is None:
                continue

            belt_mapping = _infer_second_belt_mapping(
                second_station_data,
                faces=int(tower_faces or 4),
                second_base_belt=int(second_base["belt"]),
                existing_base_belt=int(existing_base["belt"]),
                second_neighbor_belt=int(second_neighbor["belt"]),
                existing_neighbor_belt=int(existing_neighbor["belt"]),
            )
            mapping_source = "pair_inference"

            if not belt_mapping and expected_mapping_info is not None:
                fallback_mapping = dict(expected_mapping_info["belt_mapping"])
                if fallback_mapping.get(int(second_base["belt"])) == int(existing_base["belt"]):
                    belt_mapping = fallback_mapping
                    mapping_source = "expected_visible_order_fallback"

            if not belt_mapping:
                continue

            second_visible_order_left_to_right = _left_to_right_visible_belts(second_station_data)
            visible_mapping_sequence = [
                belt_mapping.get(local_belt, local_belt)
                for local_belt in second_visible_order_left_to_right
            ]
            existing_visible_order = _left_to_right_visible_belts(existing_data)

            transformed_second = _apply_method2_transform(
                second_station_data,
                second_base,
                existing_base,
                angle_info["angle_rad"],
            )
            transformed_second = _apply_belt_mapping(transformed_second, belt_mapping)

            shared_belts = set(_sorted_visible_belts(existing_data)) & set(belt_mapping.values())
            overlap = _score_overlap(
                existing_data,
                transformed_second,
                shared_belts=shared_belts,
                height_tolerance=height_tolerance,
                merge_tolerance=merge_tolerance,
            )

            transformed_neighbor_point = transformed_second.loc[second_neighbor["index"]]
            station_angle_delta = _station_angle_delta_deg(existing_data, transformed_second)
            station_angle_error = (
                abs(_normalize_angle_deg(station_angle_delta - angle_info["target_signed_deg"]))
                if station_angle_delta is not None
                else math.inf
            )
            rotation_error = float(angle_info.get("rotation_error_deg", math.inf))

            preview = {
                "existing_index": existing_index,
                "second_index": second_index,
                "existing_name": str(existing_base.get("name", existing_index)),
                "second_name": str(second_base.get("name", second_index)),
                "existing_belt": int(existing_base["belt"]),
                "second_belt": int(second_base["belt"]),
                "existing_neighbor_belt": int(existing_neighbor["belt"]),
                "second_neighbor_belt": int(second_neighbor["belt"]),
                "belt_mapping": belt_mapping,
                "mapping_source": mapping_source,
                "existing_visible_order": existing_visible_order,
                "second_visible_order": _sorted_visible_belts(second_station_data),
                "second_visible_order_left_to_right": second_visible_order_left_to_right,
                "visible_mapping_sequence": visible_mapping_sequence,
                "expected_visible_mapping_sequence": (
                    list(expected_mapping_info["expected_visible_mapping_sequence"])
                    if expected_mapping_info is not None
                    else []
                ),
                "expected_belt_mapping": (
                    dict(expected_mapping_info["belt_mapping"])
                    if expected_mapping_info is not None
                    else {}
                ),
                "angle_deg": float(angle_info["angle_deg"]),
                "direction": int(angle_info["direction"]),
                "measured_angle_deg": float(angle_info["measured_deg"]),
                "target_angle_deg": float(target_angle_deg),
                "target_signed_deg": float(angle_info["target_signed_deg"]),
                "rotation_error_deg": rotation_error,
                "station_angle_delta_deg": station_angle_delta,
                "station_angle_error_deg": station_angle_error,
                "height_delta": float(abs(float(existing_base["z"]) - float(second_base["z"]))),
                "transformed_second": transformed_second,
                "visualization_data": {
                    "line1": {
                        "start": np.array(
                            [float(existing_base["x"]), float(existing_base["y"]), float(existing_base["z"])],
                            dtype=float,
                        ),
                        "end": np.array(
                            [
                                float(existing_neighbor["point"]["x"]),
                                float(existing_neighbor["point"]["y"]),
                                float(existing_neighbor["point"]["z"]),
                            ],
                            dtype=float,
                        ),
                        "label": (
                            f"First survey: belt {int(existing_base['belt'])}"
                            f" -> belt {int(existing_neighbor['belt'])}"
                        ),
                    },
                    "line2": {
                        "start": np.array(
                            [float(existing_base["x"]), float(existing_base["y"]), float(existing_base["z"])],
                            dtype=float,
                        ),
                        "end": np.array(
                            [
                                float(transformed_neighbor_point["x"]),
                                float(transformed_neighbor_point["y"]),
                                float(transformed_neighbor_point["z"]),
                            ],
                            dtype=float,
                        ),
                        "label": (
                            f"Second survey: local belt {int(second_base['belt'])}"
                            f" -> {int(second_neighbor['belt'])}, mapped"
                            f" {belt_mapping[int(second_base['belt'])]} ->"
                            f" {belt_mapping[int(second_neighbor['belt'])]}"
                        ),
                    },
                    "angle_deg": float(angle_info["angle_deg"]),
                },
            }
            preview.update(overlap)
            preview["sort_key"] = (
                preview["station_angle_error_deg"],
                preview["rotation_error_deg"],
                -preview["shared_close_count"],
                preview["shared_trimmed_mean"],
                preview["height_delta"],
                preview["existing_belt"],
                preview["second_belt"],
            )

            if best_preview is None or preview["sort_key"] < best_preview["sort_key"]:
                best_preview = preview

    return best_preview


def build_method1_preview(
    existing_data: pd.DataFrame,
    second_station_data: pd.DataFrame,
    *,
    tower_faces: int = 4,
    target_angle_deg: float = 90.0,
    height_tolerance: float = 1.2,
    merge_tolerance: float = 0.35,
    prefer_clockwise: bool | None = None,
) -> dict[str, Any] | None:
    """Build an automatic Method 1 preview by testing plausible global belt mappings."""
    faces = max(1, int(tower_faces or 4))
    second_visible = _left_to_right_visible_belts(second_station_data)
    existing_visible = _left_to_right_visible_belts(existing_data)
    if not second_visible or not existing_visible:
        return None

    expected_mapping_info = _build_expected_visible_mapping(
        existing_data,
        second_station_data,
        faces=faces,
        target_angle_deg=target_angle_deg,
        prefer_clockwise=prefer_clockwise,
    )
    expected_sequence = (
        list(expected_mapping_info["expected_visible_mapping_sequence"])
        if expected_mapping_info is not None
        else []
    )

    target_abs_deg = abs(float(target_angle_deg))
    candidate_sequences: list[list[int]] = []
    seen_sequences: set[tuple[int, ...]] = set()

    def add_candidate(sequence: list[int]) -> None:
        key = tuple(int(value) for value in sequence)
        if not sequence or len(sequence) != len(second_visible) or key in seen_sequences:
            return
        seen_sequences.add(key)
        candidate_sequences.append([int(value) for value in sequence])

    add_candidate(expected_sequence)
    for start_face in range(1, faces + 1):
        add_candidate(
            [((start_face - offset - 1) % faces) + 1 for offset in range(len(second_visible))]
        )

    best_preview: dict[str, Any] | None = None
    for visible_mapping_sequence in candidate_sequences:
        belt_mapping = {
            int(local_belt): int(global_belt)
            for local_belt, global_belt in zip(second_visible, visible_mapping_sequence, strict=False)
        }
        if not belt_mapping:
            continue

        remapped_second = _apply_belt_mapping(second_station_data, belt_mapping)
        shared_belts = set(_sorted_visible_belts(existing_data)) & set(belt_mapping.values())
        matched_pairs = _match_points_by_belt_and_height(
            existing_data,
            remapped_second,
            shared_belts=shared_belts,
            height_tolerance=height_tolerance,
        )
        if len(matched_pairs) < 3:
            continue

        points_source = np.array(
            [
                remapped_second.loc[pair["second_index"], ["x", "y", "z"]].to_numpy(dtype=float)
                for pair in matched_pairs
            ],
            dtype=float,
        )
        points_target = np.array(
            [
                existing_data.loc[pair["existing_index"], ["x", "y", "z"]].to_numpy(dtype=float)
                for pair in matched_pairs
            ],
            dtype=float,
        )
        transform_result = compute_helmert_parameters(points_source, points_target)
        if not bool(transform_result.get("success", True)):
            continue

        transformed_second = apply_helmert_transform(remapped_second, transform_result)
        overlap = _score_overlap(
            existing_data,
            transformed_second,
            shared_belts=shared_belts,
            height_tolerance=height_tolerance,
            merge_tolerance=merge_tolerance,
        )
        station_angle_delta = _station_angle_delta_deg(existing_data, transformed_second)
        station_side = None
        if station_angle_delta is not None:
            station_side = "right" if station_angle_delta > 0 else "left"

        if station_angle_delta is None:
            station_angle_error = math.inf
            direction_penalty = math.inf
        elif prefer_clockwise is True:
            target_signed_deg = target_abs_deg
            station_angle_error = abs(_normalize_angle_deg(station_angle_delta - target_signed_deg))
            direction_penalty = 0.0 if station_angle_delta > 0 else 180.0
        elif prefer_clockwise is False:
            target_signed_deg = -target_abs_deg
            station_angle_error = abs(_normalize_angle_deg(station_angle_delta - target_signed_deg))
            direction_penalty = 0.0 if station_angle_delta < 0 else 180.0
        else:
            station_angle_error = abs(abs(station_angle_delta) - target_abs_deg)
            direction_penalty = 0.0

        rmse = float(transform_result.get("rmse", math.inf))
        trimmed_mean = float(overlap.get("shared_trimmed_mean", math.inf))
        preview = {
            "method": 1,
            "mapping_source": "visible_sequence_search",
            "belt_mapping": belt_mapping,
            "existing_visible_order": list(existing_visible),
            "second_visible_order_left_to_right": list(second_visible),
            "visible_mapping_sequence": list(visible_mapping_sequence),
            "expected_visible_mapping_sequence": list(expected_sequence),
            "matched_pairs": matched_pairs,
            "matched_pair_count": len(matched_pairs),
            "transform_result": transform_result,
            "transformed_second": transformed_second,
            "station_angle_delta_deg": station_angle_delta,
            "station_angle_error_deg": float(station_angle_error),
            "station_side": station_side,
            "target_angle_deg": float(target_angle_deg),
            "prefer_clockwise": prefer_clockwise,
            "rmse": rmse,
            **overlap,
        }
        preview["sort_key"] = (
            float(direction_penalty),
            float(station_angle_error),
            -int(preview["matched_pair_count"]),
            rmse,
            trimmed_mean,
            tuple(visible_mapping_sequence),
        )

        if best_preview is None or preview["sort_key"] < best_preview["sort_key"]:
            best_preview = preview

    return best_preview


def find_best_method2_preview(
    existing_data: pd.DataFrame,
    second_station_data: pd.DataFrame,
    *,
    tower_faces: int = 4,
    target_angle_deg: float = 90.0,
    height_tolerance: float = 1.2,
    merge_tolerance: float = 0.35,
    prefer_clockwise: bool | None = None,
) -> dict[str, Any] | None:
    """Search for the best automatic Method 2 base pair between two surveys."""
    existing_regular = _regular_points(existing_data)
    second_regular = _regular_points(second_station_data)
    if existing_regular.empty or second_regular.empty:
        return None

    best_preview: dict[str, Any] | None = None
    for existing_index, existing_point in existing_regular.iterrows():
        if pd.isna(existing_point.get("belt")):
            continue
        for second_index, second_point in second_regular.iterrows():
            if pd.isna(second_point.get("belt")):
                continue
            if abs(float(existing_point["z"]) - float(second_point["z"])) > height_tolerance:
                continue

            preview = build_method2_preview(
                existing_data,
                second_station_data,
                existing_index=existing_index,
                second_index=second_index,
                tower_faces=tower_faces,
                target_angle_deg=target_angle_deg,
                height_tolerance=height_tolerance,
                merge_tolerance=merge_tolerance,
                prefer_clockwise=prefer_clockwise,
            )
            if preview is None:
                continue

            if best_preview is None or preview["sort_key"] < best_preview["sort_key"]:
                best_preview = preview

    return best_preview
