"""
Helpers for robust import-time grouping of tower survey points.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment
from sklearn.cluster import KMeans

from core.planar_orientation import (
    clockwise_order_indices,
    extract_reference_station_xy,
)
from core.point_utils import build_working_tower_mask

logger = logging.getLogger(__name__)

_LEVEL_HEIGHT_TOLERANCE = 1.10
_LEVEL_XY_MERGE_TOLERANCE = 0.35


def _normalize_point_indices(
    points: pd.DataFrame,
    indices: Sequence[Any] | None = None,
    *,
    station_idx: Any | None = None,
) -> list[Any]:
    """Return valid point indices, excluding the instrument station."""
    if indices is None:
        raw_indices: list[Any] = list(points.index)
    else:
        raw_indices = list(indices)

    normalized: list[Any] = []
    for idx in raw_indices:
        if isinstance(idx, str) and "_part" in idx:
            base_idx = idx.split("_part", 1)[0]
            try:
                source_idx: Any = int(base_idx)
            except ValueError:
                source_idx = base_idx
            if source_idx != station_idx:
                normalized.append(source_idx)
            continue

        if idx != station_idx:
            normalized.append(idx)

    return [idx for idx in normalized if idx in points.index]


def _cluster_indices_by_height(
    points: pd.DataFrame,
    indices: Sequence[Any],
    *,
    tolerance: float = _LEVEL_HEIGHT_TOLERANCE,
) -> list[list[Any]]:
    """Split points into coarse height levels with a forgiving tolerance."""
    ordered = sorted(indices, key=lambda idx: float(points.loc[idx, "z"]))
    levels: list[list[Any]] = []
    current_level: list[Any] = []
    last_z: float | None = None

    for idx in ordered:
        z_value = float(points.loc[idx, "z"])
        if last_z is None or (z_value - last_z) <= tolerance:
            current_level.append(idx)
        else:
            levels.append(current_level)
            current_level = [idx]
        last_z = z_value

    if current_level:
        levels.append(current_level)

    return levels


def _merge_level_duplicates(
    points: pd.DataFrame,
    level_indices: Sequence[Any],
    *,
    xy_tolerance: float = _LEVEL_XY_MERGE_TOLERANCE,
) -> list[dict[str, Any]]:
    """Collapse near-duplicate measurements on the same structural level."""
    representatives: list[dict[str, Any]] = []

    for idx in level_indices:
        xy = points.loc[idx, ["x", "y"]].to_numpy(dtype=float)
        matched_group: dict[str, Any] | None = None
        for candidate in representatives:
            candidate_xy = points.loc[candidate["rep_idx"], ["x", "y"]].to_numpy(dtype=float)
            if float(np.linalg.norm(xy - candidate_xy)) <= xy_tolerance:
                matched_group = candidate
                break

        if matched_group is None:
            representatives.append(
                {
                    "rep_idx": idx,
                    "indices": [idx],
                }
            )
        else:
            matched_group["indices"].append(idx)

    for rep in representatives:
        row = points.loc[rep["rep_idx"]]
        rep["z"] = float(row["z"])
        rep["xy"] = row[["x", "y"]].to_numpy(dtype=float)

    return representatives


def _estimate_observed_track_count(
    level_groups: Sequence[Sequence[dict[str, Any]]],
    *,
    max_tracks: int,
) -> int:
    """
    Estimate how many face tracks are really visible in this survey.

    Sparse upper singletons should not outweigh lower/full levels, so we use a
    weighted vote by the number of original points represented on each level.
    """
    weights: dict[int, int] = defaultdict(int)
    has_multi_track_level = False

    for groups in level_groups:
        track_count = min(len(groups), max_tracks)
        if track_count <= 0:
            continue
        if track_count > 1:
            has_multi_track_level = True
        point_weight = sum(len(group["indices"]) for group in groups)
        weights[track_count] += int(point_weight)

    if not weights:
        return 1

    if has_multi_track_level and 1 in weights:
        weights.pop(1, None)

    if not weights:
        return 1

    observed_tracks, _ = max(weights.items(), key=lambda item: (item[1], item[0]))
    return max(1, min(max_tracks, int(observed_tracks)))


def _predict_track_xy(track_points: Sequence[dict[str, Any]], target_z: float) -> np.ndarray:
    """Predict a track position at a given height using a simple linear trend."""
    if not track_points:
        return np.zeros(2, dtype=float)

    if len(track_points) == 1:
        return np.asarray(track_points[0]["xy"], dtype=float)

    sorted_points = sorted(track_points, key=lambda item: item["z"])
    z_values = np.array([item["z"] for item in sorted_points], dtype=float)
    xy_values = np.array([item["xy"] for item in sorted_points], dtype=float)

    if np.allclose(z_values, z_values[0]):
        return np.mean(xy_values, axis=0)

    x_coeff = np.polyfit(z_values, xy_values[:, 0], 1)
    y_coeff = np.polyfit(z_values, xy_values[:, 1], 1)
    return np.array(
        [
            float(np.polyval(x_coeff, target_z)),
            float(np.polyval(y_coeff, target_z)),
        ],
        dtype=float,
    )


def _cluster_by_angular_model(
    points: pd.DataFrame,
    working: pd.DataFrame,
    *,
    cluster_count: int,
    output_count: int,
    reference_station_xy: Sequence[float] | np.ndarray | None = None,
) -> list[list[Any]]:
    """Fallback angular clustering used when track stitching has too little context."""
    coords = working[["x", "y"]].to_numpy(dtype=float)
    center = np.array(
        [
            float(np.mean(coords[:, 0])),
            float(np.mean(coords[:, 1])),
        ],
        dtype=float,
    )
    relative = coords - center
    angles = np.arctan2(relative[:, 1], relative[:, 0])

    grouped: list[list[Any]] = [[] for _ in range(output_count)]
    if cluster_count <= 1:
        grouped[0] = sorted(working.index.tolist(), key=lambda idx: float(points.loc[idx, "z"]))
        return grouped

    features = np.column_stack([np.cos(angles), np.sin(angles)])
    labels = KMeans(
        n_clusters=cluster_count,
        random_state=42,
        n_init=10,
    ).fit_predict(features)

    cluster_centroids: list[tuple[int, np.ndarray]] = []
    for label in sorted(set(labels)):
        mask = labels == label
        cluster_centroid = np.mean(coords[mask], axis=0, dtype=float)
        cluster_centroids.append((int(label), np.asarray(cluster_centroid, dtype=float)))

    ordered_label_indices = clockwise_order_indices(
        np.array([centroid for _, centroid in cluster_centroids], dtype=float),
        center_xy=center,
        station_xy=reference_station_xy,
    )
    ordered_labels = [cluster_centroids[int(idx)][0] for idx in ordered_label_indices]
    label_to_slot = {label: slot for slot, label in enumerate(ordered_labels)}

    for idx, label in zip(working.index.tolist(), labels, strict=False):
        slot = label_to_slot[int(label)]
        grouped[slot].append(idx)

    for bucket in grouped:
        bucket.sort(key=lambda idx: float(points.loc[idx, "z"]))

    return grouped


def group_points_by_global_angle(
    points: pd.DataFrame,
    indices: Sequence[Any] | None,
    num_belts: int,
    *,
    station_idx: Any | None = None,
    reference_station_xy: Sequence[float] | np.ndarray | None = None,
) -> list[list[Any]]:
    """
    Group points into tower face tracks while tolerating partial single-station surveys.

    We first detect coarse structural levels, merge near-duplicate observations on a
    level, infer how many tracks are actually visible, and then stitch those tracks
    through height. This keeps 3-of-4 visible faces on the same three tracks instead
    of artificially spreading them across all four expected belts.
    """
    if num_belts <= 0:
        normalized = _normalize_point_indices(points, indices, station_idx=station_idx)
        return [normalized]

    normalized = _normalize_point_indices(points, indices, station_idx=station_idx)
    if not normalized:
        return [[] for _ in range(num_belts)]

    working = points.loc[normalized].copy()
    working_mask = build_working_tower_mask(working)
    working = working[working_mask]
    working = working.dropna(subset=["x", "y"])

    if working.empty:
        return [[] for _ in range(num_belts)]

    station_xy = (
        np.asarray(reference_station_xy, dtype=float)
        if reference_station_xy is not None
        else extract_reference_station_xy(points, station_idx=station_idx)
    )

    cluster_count = min(num_belts, len(working))
    grouped: list[list[Any]] = [[] for _ in range(num_belts)]
    if cluster_count <= 1:
        grouped[0] = sorted(working.index.tolist(), key=lambda idx: float(points.loc[idx, "z"]))
        return grouped

    level_indices = _cluster_indices_by_height(points, working.index.tolist())
    level_groups = [_merge_level_duplicates(points, level) for level in level_indices]
    observed_tracks = _estimate_observed_track_count(level_groups, max_tracks=cluster_count)
    anchor_level_positions = [
        idx for idx, groups in enumerate(level_groups) if len(groups) == observed_tracks
    ]

    if observed_tracks <= 1 or not anchor_level_positions:
        return _cluster_by_angular_model(
            points,
            working,
            cluster_count=observed_tracks,
            output_count=num_belts,
            reference_station_xy=station_xy,
        )

    tracks: list[list[dict[str, Any]]] = [[] for _ in range(observed_tracks)]
    seed_level_position = anchor_level_positions[0]
    seed_groups = level_groups[seed_level_position]

    seed_points_xy = np.array([np.asarray(rep["xy"], dtype=float) for rep in seed_groups], dtype=float)
    seed_center_xy = np.mean(seed_points_xy, axis=0, dtype=float)
    seed_order = clockwise_order_indices(
        seed_points_xy,
        center_xy=seed_center_xy,
        station_xy=station_xy,
    )

    for slot, rep_idx in enumerate(seed_order):
        rep = seed_groups[int(rep_idx)]
        grouped[slot].extend(rep["indices"])
        tracks[slot].append(
            {
                "z": rep["z"],
                "xy": np.asarray(rep["xy"], dtype=float),
            }
        )

    for level_position, reps in enumerate(level_groups):
        if level_position == seed_level_position or not reps:
            continue

        rep_z = float(np.mean([rep["z"] for rep in reps]))
        cost_matrix = np.full((observed_tracks, len(reps)), 1e6, dtype=float)
        for track_idx in range(observed_tracks):
            predicted_xy = _predict_track_xy(tracks[track_idx], rep_z)
            for rep_idx, rep in enumerate(reps):
                rep_xy = np.asarray(rep["xy"], dtype=float)
                cost_matrix[track_idx, rep_idx] = float(np.linalg.norm(predicted_xy - rep_xy))

        track_indices, rep_indices = linear_sum_assignment(cost_matrix)
        for track_idx, rep_idx in zip(track_indices, rep_indices, strict=False):
            rep = reps[int(rep_idx)]
            grouped[int(track_idx)].extend(rep["indices"])
            tracks[int(track_idx)].append(
                {
                    "z": rep["z"],
                    "xy": np.asarray(rep["xy"], dtype=float),
                }
            )

    for bucket in grouped:
        bucket.sort(key=lambda idx: float(points.loc[idx, "z"]))

    return grouped


def estimate_composite_split_height(
    points: pd.DataFrame,
    *,
    num_belts: int = 4,
    station_idx: Any | None = None,
) -> float | None:
    """
    Suggest a reasonable split height for a two-part composite tower.

    The primary estimator is a height-distribution valley. If that valley lands in
    an implausible low part of the mast, we fall back to a structural quartile
    derived from globally grouped face tracks.
    """
    normalized = _normalize_point_indices(points, None, station_idx=station_idx)
    if not normalized:
        return None

    working = points.loc[normalized].copy()
    working_mask = build_working_tower_mask(working)
    working = working[working_mask]
    working = working.dropna(subset=["z"])

    if len(working) < max(8, num_belts * 2):
        return None

    z_values = working["z"].to_numpy(dtype=float)
    if len(z_values) >= 2:
        sorted_heights = np.sort(z_values)
        if float(sorted_heights[1] - sorted_heights[0]) > 1.0:
            working = working[working["z"] > float(sorted_heights[0])].copy()
            z_values = working["z"].to_numpy(dtype=float)

    z_min = float(np.min(z_values))
    z_max = float(np.max(z_values))
    if not np.isfinite(z_min) or not np.isfinite(z_max) or (z_max - z_min) < 1.0:
        return None

    lower_bound = float(np.quantile(z_values, 0.55))
    upper_bound = float(np.quantile(z_values, 0.90))

    num_bins = max(10, min(50, len(working) // 5))
    hist, bin_edges = np.histogram(z_values, bins=num_bins)
    if len(hist) >= 3:
        min_idx = int(np.argmin(hist[1:-1]) + 1)
        valley_split = float((bin_edges[min_idx] + bin_edges[min_idx + 1]) / 2.0)
        if lower_bound <= valley_split <= upper_bound:
            return valley_split

    grouped = group_points_by_global_angle(
        working,
        working.index.tolist(),
        max(3, int(num_belts or 4)),
        station_idx=station_idx,
        reference_station_xy=extract_reference_station_xy(points, station_idx=station_idx),
    )
    consensus_levels: list[float] = []
    for rank in range(max((len(group) for group in grouped), default=0)):
        heights = []
        for group in grouped:
            if rank < len(group):
                heights.append(float(working.loc[group[rank], "z"]))
        if heights:
            consensus_levels.append(float(np.mean(heights)))

    if len(consensus_levels) >= 4:
        upper_level_count = max(2, round(len(consensus_levels) * 0.25))
        upper_level_count = min(upper_level_count, len(consensus_levels) - 1)
        candidate_idx = max(0, len(consensus_levels) - upper_level_count - 1)
        candidate = float(consensus_levels[candidate_idx])
        if lower_bound <= candidate <= upper_bound:
            return candidate

    return float(np.quantile(z_values, 0.75))
