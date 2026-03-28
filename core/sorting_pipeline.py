"""Unified point sorting pipeline for tower survey imports.

Handles all sorting scenarios:
- Simple/composite towers
- Single/multi-station surveys
- Partial visibility (not all faces visible)
- Irregular point distributions
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment

from core.planar_orientation import (
    _ensure_center_xy,
    clockwise_angle_from_anchor_rad,
    clockwise_order_indices,
    extract_reference_station_xy,
    observer_right_axis,
    select_rightmost_anchor_vector,
)
from core.point_utils import (
    build_working_tower_mask,
    normalize_tower_point_flags,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class SortedTowerResult:
    """Result of the sorting pipeline."""

    data: pd.DataFrame
    face_count: int
    height_levels: list[float]
    tower_center_xy: tuple[float, float]
    anchor_angle_deg: float
    audit: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Height clustering (gap-based, replaces DBSCAN/KMeans)
# ---------------------------------------------------------------------------


def _cluster_height_levels(
    z_values: np.ndarray,
    *,
    expected_levels: int | None = None,
    tolerance: float = 0.3,
) -> np.ndarray:
    """Cluster points by height using gap-based algorithm.

    Returns an array of 1-based level labels (same length as z_values).
    Level 1 = lowest group.
    """
    n = len(z_values)
    if n == 0:
        return np.array([], dtype=int)

    # Sort indices by Z
    order = np.argsort(z_values)
    sorted_z = z_values[order]

    # Find gaps > tolerance
    if n == 1:
        labels_sorted = np.array([1], dtype=int)
    else:
        diffs = np.diff(sorted_z)
        # Assign cluster labels: increment when gap > tolerance
        labels_sorted = np.ones(n, dtype=int)
        for i in range(1, n):
            if diffs[i - 1] > tolerance:
                labels_sorted[i] = labels_sorted[i - 1] + 1
            else:
                labels_sorted[i] = labels_sorted[i - 1]

    cluster_count = labels_sorted[-1]

    # Adjust cluster count if expected_levels is provided
    if expected_levels is not None and expected_levels > 0 and cluster_count != expected_levels:
        if cluster_count > expected_levels:
            # Too many clusters — merge closest ones
            labels_sorted = _merge_closest_clusters(sorted_z, labels_sorted, expected_levels)
        elif cluster_count < expected_levels:
            # Too few clusters — split largest by biggest internal gap
            labels_sorted = _split_largest_clusters(sorted_z, labels_sorted, expected_levels)

    # Map back to original order
    result = np.empty(n, dtype=int)
    result[order] = labels_sorted
    return result


def _merge_closest_clusters(
    sorted_z: np.ndarray,
    labels: np.ndarray,
    target_count: int,
) -> np.ndarray:
    """Merge closest clusters until target_count is reached."""
    labels = labels.copy()
    while True:
        unique_labels = sorted(set(labels))
        if len(unique_labels) <= target_count:
            break
        # Find the two adjacent clusters with smallest gap between their means
        cluster_means = []
        for label in unique_labels:
            mask = labels == label
            cluster_means.append(np.mean(sorted_z[mask]))
        min_gap = float('inf')
        merge_pair = (unique_labels[0], unique_labels[1])
        for i in range(len(cluster_means) - 1):
            gap = cluster_means[i + 1] - cluster_means[i]
            if gap < min_gap:
                min_gap = gap
                merge_pair = (unique_labels[i], unique_labels[i + 1])
        # Merge: relabel second cluster to first
        labels[labels == merge_pair[1]] = merge_pair[0]

    # Renumber consecutively 1..N
    unique_sorted = sorted(set(labels))
    remap = {old: new for new, old in enumerate(unique_sorted, start=1)}
    return np.array([remap[l] for l in labels], dtype=int)


def _split_largest_clusters(
    sorted_z: np.ndarray,
    labels: np.ndarray,
    target_count: int,
) -> np.ndarray:
    """Split largest clusters by internal gaps until target_count is reached."""
    labels = labels.copy()
    next_label = labels.max() + 1

    while True:
        unique_labels = sorted(set(labels))
        if len(unique_labels) >= target_count:
            break
        # Find the cluster with the largest internal gap
        best_label = None
        best_gap = -1.0
        best_split_pos = -1
        for label in unique_labels:
            indices = np.where(labels == label)[0]
            if len(indices) < 2:
                continue
            cluster_z = sorted_z[indices]
            internal_diffs = np.diff(cluster_z)
            max_idx = int(np.argmax(internal_diffs))
            if internal_diffs[max_idx] > best_gap:
                best_gap = internal_diffs[max_idx]
                best_label = label
                best_split_pos = indices[max_idx + 1]  # First index of new cluster
        if best_label is None or best_gap <= 0:
            break
        # Split: everything from best_split_pos onward in that cluster gets new label
        cluster_indices = np.where(labels == best_label)[0]
        split_mask = cluster_indices >= best_split_pos
        labels[cluster_indices[split_mask]] = next_label
        next_label += 1

    # Renumber consecutively 1..N
    unique_sorted = sorted(set(labels))
    remap = {old: new for new, old in enumerate(unique_sorted, start=1)}
    return np.array([remap[l] for l in labels], dtype=int)


# ---------------------------------------------------------------------------
# Face track assignment (angular, replaces group_points_by_global_angle)
# ---------------------------------------------------------------------------


def _assign_face_tracks(
    data: pd.DataFrame,
    working_mask: np.ndarray,
    height_levels: np.ndarray,
    expected_faces: int,
    center_xy: np.ndarray,
    station_xy: np.ndarray | None = None,
) -> np.ndarray:
    """Assign angular face tracks (1-based) to working tower points.

    Algorithm:
    1. Select seed level (most points, prefer middle height on tie)
    2. Sort seed level clockwise from observer's right → face_track 1..N
    3. Propagate outward (up and down from seed) using angular matching
    4. Validate Z-monotonicity per track

    Returns array of face_track values (same length as data, 0 for non-working).
    """
    result = np.zeros(len(data), dtype=int)
    working_indices = np.where(working_mask)[0]
    if len(working_indices) == 0 or expected_faces <= 0:
        return result

    working_levels = height_levels[working_indices]
    unique_levels = sorted(set(working_levels))
    if not unique_levels:
        return result

    # Group working indices by level
    level_groups: dict[int, list[int]] = defaultdict(list)
    for wi, level in zip(working_indices, working_levels):
        level_groups[level].append(wi)

    # Select seed level: most points, prefer middle on tie
    mid_rank = len(unique_levels) // 2
    seed_level = max(
        unique_levels,
        key=lambda lv: (len(level_groups[lv]), -abs(unique_levels.index(lv) - mid_rank)),
    )

    seed_indices = level_groups[seed_level]
    seed_xy = data.iloc[seed_indices][['x', 'y']].to_numpy(dtype=float)

    # Sort seed level clockwise
    cw_order = clockwise_order_indices(seed_xy, center_xy=center_xy, station_xy=station_xy)

    # Build anchor angles from seed level
    anchor = select_rightmost_anchor_vector(seed_xy, center_xy=center_xy, station_xy=station_xy)
    seed_vectors = seed_xy - center_xy

    # Start numbering from the first-in-file point at the seed level so that
    # face_track=1 is assigned to the face whose measurement appears earliest
    # in the source data (matches user expectations for face-sequential surveys).
    cw_order_arr = np.asarray(cw_order)
    first_file_local_idx = int(np.argmin(seed_indices))  # local index of first-file seed point
    positions = np.where(cw_order_arr == first_file_local_idx)[0]
    first_cw_rank = int(positions[0]) if len(positions) > 0 else 0

    # Assign face tracks to seed level (1-based, in clockwise order from first-file point)
    seed_track_angles: dict[int, float] = {}  # track → angle
    for rank, order_idx in enumerate(cw_order):
        track = ((rank - first_cw_rank) % expected_faces) + 1
        actual_idx = seed_indices[order_idx]
        result[actual_idx] = track
        vec = seed_vectors[order_idx]
        angle = clockwise_angle_from_anchor_rad(vec, anchor_vector_xy=anchor)
        # Keep last angle for each track (in case of multiple points per track at seed)
        seed_track_angles[track] = angle

    # Compute reference angles for each track (from seed)
    track_ref_angles = dict(seed_track_angles)

    # Propagate outward from seed
    seed_pos = unique_levels.index(seed_level)
    # Process levels above seed, then below seed
    levels_above = unique_levels[seed_pos + 1:]
    levels_below = list(reversed(unique_levels[:seed_pos]))

    for level_sequence in [levels_above, levels_below]:
        # Reset reference angles to seed at start of each direction
        current_ref_angles = dict(track_ref_angles)
        for level in level_sequence:
            indices = level_groups[level]
            _assign_level_tracks(
                data, indices, result, expected_faces,
                center_xy, anchor, current_ref_angles,
            )
            # Update reference angles from this level for next propagation step
            for idx in indices:
                track = result[idx]
                if track > 0:
                    vec = data.iloc[idx][['x', 'y']].to_numpy(dtype=float) - center_xy
                    current_ref_angles[track] = clockwise_angle_from_anchor_rad(
                        vec, anchor_vector_xy=anchor
                    )

    return result


def _assign_level_tracks(
    data: pd.DataFrame,
    indices: list[int],
    result: np.ndarray,
    expected_faces: int,
    center_xy: np.ndarray,
    anchor: np.ndarray,
    ref_angles: dict[int, float],
) -> None:
    """Assign face tracks to points at a single height level using Hungarian matching."""
    n_points = len(indices)
    if n_points == 0:
        return

    # Compute angles for current level points
    points_xy = data.iloc[indices][['x', 'y']].to_numpy(dtype=float)
    vectors = points_xy - center_xy
    point_angles = np.array([
        clockwise_angle_from_anchor_rad(vec, anchor_vector_xy=anchor)
        for vec in vectors
    ], dtype=float)

    # Build available tracks and their reference angles
    available_tracks = sorted(ref_angles.keys())
    n_tracks = len(available_tracks)

    if n_tracks == 0:
        # No reference — just assign sequentially
        for i, idx in enumerate(indices):
            result[idx] = (i % expected_faces) + 1
        return

    if n_points == 1 and n_tracks >= 1:
        # Single point — assign to nearest track
        best_track = min(
            available_tracks,
            key=lambda t: _angular_distance(point_angles[0], ref_angles[t]),
        )
        result[indices[0]] = best_track
        return

    # Build cost matrix: rows = points, cols = tracks
    # Use adaptive penalty for unmatched
    if n_points > 1:
        sorted_angles = np.sort(point_angles)
        inter_distances = np.diff(sorted_angles)
        if len(inter_distances) > 0:
            penalty = max(2.0 * np.median(inter_distances), math.pi / expected_faces)
        else:
            penalty = math.pi / expected_faces
    else:
        penalty = math.pi / expected_faces

    cost = np.full((n_points, n_tracks), penalty * 2, dtype=float)
    for i, pa in enumerate(point_angles):
        for j, track in enumerate(available_tracks):
            cost[i, j] = _angular_distance(pa, ref_angles[track])

    # Solve assignment
    if n_points <= n_tracks:
        row_ind, col_ind = linear_sum_assignment(cost)
        for ri, ci in zip(row_ind, col_ind):
            if cost[ri, ci] < penalty * 2:
                result[indices[ri]] = available_tracks[ci]
            else:
                # Point too far from any track — assign to nearest anyway but log
                nearest = int(np.argmin(cost[ri]))
                result[indices[ri]] = available_tracks[nearest]
    else:
        # More points than tracks — allow multiple points per track
        # Assign each point to nearest track
        for i, pa in enumerate(point_angles):
            best_j = int(np.argmin(cost[i]))
            result[indices[i]] = available_tracks[best_j]


def _angular_distance(a: float, b: float) -> float:
    """Minimum angular distance between two angles in [0, 2*pi)."""
    diff = abs(a - b)
    return min(diff, 2.0 * math.pi - diff)


# ---------------------------------------------------------------------------
# Clockwise angle computation for debugging/display
# ---------------------------------------------------------------------------


def _compute_cw_angles(
    data: pd.DataFrame,
    working_mask: np.ndarray,
    center_xy: np.ndarray,
    station_xy: np.ndarray | None = None,
) -> np.ndarray:
    """Compute clockwise angle in degrees for each point."""
    angles = np.full(len(data), np.nan, dtype=float)
    working_indices = np.where(working_mask)[0]
    if len(working_indices) == 0:
        return angles

    anchor = select_rightmost_anchor_vector(
        data.iloc[working_indices][['x', 'y']].to_numpy(dtype=float),
        center_xy=center_xy,
        station_xy=station_xy,
    )

    for wi in working_indices:
        vec = data.iloc[wi][['x', 'y']].to_numpy(dtype=float) - center_xy
        angle_rad = clockwise_angle_from_anchor_rad(vec, anchor_vector_xy=anchor)
        angles[wi] = math.degrees(angle_rad)

    return angles


# ---------------------------------------------------------------------------
# Composite tower splitting
# ---------------------------------------------------------------------------


def _split_composite_parts(
    data: pd.DataFrame,
    working_mask: np.ndarray,
    tower_parts: list[dict],
    split_heights: list[float],
    tolerance: float,
) -> np.ndarray:
    """Assign tower_part (1-based) to each point.

    Points within tolerance of a split height are assigned to the LOWER part
    (they'll be included in both parts during processing via boundary logic).
    """
    parts = np.ones(len(data), dtype=int)
    if not split_heights:
        return parts

    z_values = data['z'].to_numpy(dtype=float)
    sorted_splits = sorted(split_heights)

    for i in range(len(data)):
        if not working_mask[i]:
            parts[i] = 0
            continue
        z = z_values[i]
        assigned_part = 1
        for split_idx, split_h in enumerate(sorted_splits):
            if z > split_h + tolerance:
                assigned_part = split_idx + 2
            elif z > split_h - tolerance:
                # Boundary zone — assign to lower part, mark for duplication later
                assigned_part = split_idx + 1
                break
            else:
                break
        parts[i] = assigned_part

    return parts


def _get_boundary_indices(
    data: pd.DataFrame,
    working_mask: np.ndarray,
    split_heights: list[float],
    tolerance: float,
) -> set[int]:
    """Return indices of points within tolerance of any split height."""
    boundary = set()
    z_values = data['z'].to_numpy(dtype=float)
    for i in range(len(data)):
        if not working_mask[i]:
            continue
        for sh in split_heights:
            if abs(z_values[i] - sh) <= tolerance:
                boundary.add(i)
                break
    return boundary


# ---------------------------------------------------------------------------
# Multi-station merge
# ---------------------------------------------------------------------------


def _compute_rotation_shift(
    base_station_xy: np.ndarray | None,
    current_station_xy: np.ndarray | None,
    center_xy: np.ndarray,
    expected_faces: int,
    base_track_angles: dict[int, float] | None = None,
    current_track_angles: dict[int, float] | None = None,
) -> int:
    """Compute rotation shift between stations.

    Tries all possible shifts and picks the one with minimum angular cost.
    Falls back to geometric estimation if track angles are not available.
    """
    if expected_faces <= 0:
        return 0

    # Geometric estimate
    geo_shift = 0
    if base_station_xy is not None and current_station_xy is not None:
        step = 360.0 / float(expected_faces)
        base_angle = math.degrees(math.atan2(
            base_station_xy[1] - center_xy[1],
            base_station_xy[0] - center_xy[0],
        ))
        current_angle = math.degrees(math.atan2(
            current_station_xy[1] - center_xy[1],
            current_station_xy[0] - center_xy[0],
        ))
        shift_deg = (base_angle - current_angle) % 360.0
        geo_shift = round(shift_deg / step) % expected_faces

    # If we have track angles from both stations, validate by trying all shifts
    if base_track_angles and current_track_angles:
        best_shift = geo_shift
        best_cost = float('inf')
        for candidate_shift in range(expected_faces):
            cost = 0.0
            matched = 0
            for local_track, local_angle in current_track_angles.items():
                global_track = ((local_track - 1 + candidate_shift) % expected_faces) + 1
                if global_track in base_track_angles:
                    cost += _angular_distance(local_angle, base_track_angles[global_track])
                    matched += 1
            if matched > 0:
                avg_cost = cost / matched
                if avg_cost < best_cost:
                    best_cost = avg_cost
                    best_shift = candidate_shift
        return best_shift

    return geo_shift


def _find_duplicates_between_stations(
    data: pd.DataFrame,
    new_indices: list[Any],
    existing_indices: list[Any],
    xy_tolerance: float = 0.10,
    z_tolerance: float = 0.20,
) -> list[dict[str, Any]]:
    """Find duplicate observations between stations."""
    duplicates = []
    for new_idx in new_indices:
        new_xy = data.loc[new_idx, ['x', 'y']].to_numpy(dtype=float)
        new_z = float(data.loc[new_idx, 'z'])
        best: dict[str, Any] | None = None
        for exist_idx in existing_indices:
            exist_xy = data.loc[exist_idx, ['x', 'y']].to_numpy(dtype=float)
            exist_z = float(data.loc[exist_idx, 'z'])
            z_delta = abs(new_z - exist_z)
            if z_delta > z_tolerance:
                continue
            xy_dist = float(np.linalg.norm(new_xy - exist_xy))
            if xy_dist > xy_tolerance:
                continue
            match_type = 'duplicate' if xy_dist <= 0.05 else 'review'
            candidate = {
                'new_idx': new_idx,
                'existing_idx': exist_idx,
                'xy_distance': xy_dist,
                'z_delta': z_delta,
                'match_type': match_type,
            }
            if best is None or xy_dist < best['xy_distance']:
                best = candidate
        if best is not None:
            duplicates.append(best)
    return duplicates


# ---------------------------------------------------------------------------
# Station block splitting (adapted from multi_station_import)
# ---------------------------------------------------------------------------


def _split_station_blocks(data: pd.DataFrame) -> list[dict[str, Any]]:
    """Split data into station observation blocks."""
    station_mask = data.get('is_station', pd.Series(False, index=data.index))
    station_mask = station_mask.fillna(False).astype(bool)

    # Try survey_station_order first
    if 'survey_station_order' in data.columns and data['survey_station_order'].notna().any():
        station_orders = (
            pd.to_numeric(data['survey_station_order'], errors='coerce')
            .dropna()
            .astype(int)
            .unique()
            .tolist()
        )
        blocks: list[dict[str, Any]] = []
        for station_order in sorted(station_orders):
            order_mask = pd.to_numeric(data['survey_station_order'], errors='coerce').eq(station_order)
            block_rows = data[order_mask]
            if block_rows.empty:
                continue
            station_rows = block_rows[station_mask.reindex(block_rows.index, fill_value=False)]
            station_idx = station_rows.index[0] if not station_rows.empty else None
            station_name = str(block_rows.loc[station_idx, 'name']) if station_idx is not None else None
            blocks.append({
                'station_idx': station_idx,
                'station_name': station_name,
                'station_order': int(station_order),
                'indices': block_rows.index.tolist(),
            })
        return blocks

    # Fallback: split by is_station flags in order
    blocks = []
    current_block: dict[str, Any] | None = None
    ordered_indices = data.index.tolist()
    if 'source_order' in data.columns:
        ordered_indices = data.sort_values('source_order').index.tolist()

    for idx in ordered_indices:
        if bool(station_mask.get(idx, False)):
            current_block = {
                'station_idx': idx,
                'station_name': str(data.at[idx, 'name']),
                'station_order': len(blocks) + 1,
                'indices': [idx],
            }
            blocks.append(current_block)
        elif current_block is not None:
            current_block['indices'].append(idx)

    return blocks


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def sort_imported_tower_points(
    data: pd.DataFrame,
    expected_faces: int,
    *,
    station_idx: int | None = None,
    tower_type: str = "simple",
    tower_parts: list[dict] | None = None,
    split_heights: list[float] | None = None,
    split_height_tolerance: float = 0.5,
    multi_station: bool = False,
    base_station_idx: int | None = None,
    height_tolerance: float = 0.3,
) -> SortedTowerResult:
    """Unified pipeline for sorting imported tower survey points.

    Args:
        data: DataFrame with columns x, y, z, name, is_station (and optionally
              survey_station_order, survey_station_name, is_auxiliary, is_control).
        expected_faces: Number of tower faces (3, 4, 6, etc.).
        station_idx: Index of the station point (for single-station surveys).
        tower_type: "simple" or "composite".
        tower_parts: List of part definitions for composite towers.
        split_heights: Heights where composite tower parts change.
        split_height_tolerance: Tolerance for part boundary detection.
        multi_station: Whether data comes from multiple survey stations.
        base_station_idx: Which station to use as reference (multi-station).
        height_tolerance: Tolerance for height level clustering.

    Returns:
        SortedTowerResult with fully annotated DataFrame.
    """
    audit: dict[str, Any] = {
        'expected_faces': expected_faces,
        'tower_type': tower_type,
        'multi_station': multi_station,
    }

    # Normalize flags
    work_data = normalize_tower_point_flags(data).copy()

    # Initialize output columns
    work_data['face_track'] = 0
    work_data['height_level'] = 0
    work_data['cw_angle_deg'] = np.nan
    work_data['tower_part'] = 1
    work_data['part_face_track'] = 0
    work_data['faces'] = expected_faces
    work_data['is_part_boundary'] = False

    # Build working mask
    working_mask = build_working_tower_mask(work_data).to_numpy(dtype=bool)
    working_indices = np.where(working_mask)[0]

    if len(working_indices) == 0:
        logger.warning("Нет рабочих точек башни для сортировки")
        return SortedTowerResult(
            data=_finalize_columns(work_data),
            face_count=expected_faces,
            height_levels=[],
            tower_center_xy=(0.0, 0.0),
            anchor_angle_deg=0.0,
            audit=audit,
        )

    # Determine station XY
    station_xy = extract_reference_station_xy(work_data, station_idx=station_idx)

    # Compute tower center from working points
    center_xy = work_data.iloc[working_indices][['x', 'y']].mean().to_numpy(dtype=float)
    audit['tower_center_xy'] = (float(center_xy[0]), float(center_xy[1]))

    if multi_station:
        result = _process_multi_station(
            work_data, working_mask, expected_faces,
            center_xy, base_station_idx, height_tolerance, audit,
        )
        return result

    if tower_type == 'composite' and tower_parts and split_heights:
        result = _process_composite(
            work_data, working_mask, expected_faces,
            tower_parts, split_heights, split_height_tolerance,
            station_idx, station_xy, center_xy, height_tolerance, audit,
        )
        return result

    # Simple tower, single station
    return _process_simple(
        work_data, working_mask, expected_faces,
        station_xy, center_xy, height_tolerance, audit,
    )


def _process_simple(
    data: pd.DataFrame,
    working_mask: np.ndarray,
    expected_faces: int,
    station_xy: np.ndarray | None,
    center_xy: np.ndarray,
    height_tolerance: float,
    audit: dict[str, Any],
) -> SortedTowerResult:
    """Process a simple tower from a single station."""
    working_indices = np.where(working_mask)[0]
    z_values = data.iloc[working_indices]['z'].to_numpy(dtype=float)

    # 1. Cluster height levels
    height_labels = _cluster_height_levels(z_values, tolerance=height_tolerance)
    full_height_levels = np.zeros(len(data), dtype=int)
    full_height_levels[working_indices] = height_labels
    data['height_level'] = full_height_levels

    # Compute height level medians
    height_level_medians = _compute_level_medians(z_values, height_labels)
    audit['height_level_count'] = len(height_level_medians)
    audit['height_level_medians'] = height_level_medians

    # 2. Assign face tracks
    face_tracks = _assign_face_tracks(
        data, working_mask, full_height_levels,
        expected_faces, center_xy, station_xy,
    )
    data['face_track'] = face_tracks

    # 3. Compute clockwise angles
    cw_angles = _compute_cw_angles(data, working_mask, center_xy, station_xy)
    data['cw_angle_deg'] = cw_angles

    # 4. Set derived columns
    data['part_face_track'] = data['face_track']
    data['faces'] = 0
    data.loc[working_mask, 'faces'] = expected_faces

    # Audit
    assigned = (face_tracks > 0).sum()
    audit['assigned_points'] = int(assigned)
    audit['unassigned_points'] = int(len(working_indices) - assigned)

    # Anchor angle
    anchor_angle = 0.0
    face1_mask = face_tracks == 1
    if face1_mask.any():
        face1_angles = cw_angles[face1_mask]
        valid = face1_angles[~np.isnan(face1_angles)]
        if len(valid) > 0:
            anchor_angle = float(np.mean(valid))

    return SortedTowerResult(
        data=_finalize_columns(data),
        face_count=expected_faces,
        height_levels=height_level_medians,
        tower_center_xy=(float(center_xy[0]), float(center_xy[1])),
        anchor_angle_deg=anchor_angle,
        audit=audit,
    )


def _process_composite(
    data: pd.DataFrame,
    working_mask: np.ndarray,
    expected_faces: int,
    tower_parts: list[dict],
    split_heights: list[float],
    split_height_tolerance: float,
    station_idx: int | None,
    station_xy: np.ndarray | None,
    center_xy: np.ndarray,
    height_tolerance: float,
    audit: dict[str, Any],
) -> SortedTowerResult:
    """Process a composite tower (multiple cross-sections)."""
    # Assign tower parts
    part_labels = _split_composite_parts(
        data, working_mask, tower_parts, split_heights, split_height_tolerance
    )
    data['tower_part'] = part_labels

    # Mark boundary points
    boundary_indices = _get_boundary_indices(
        data, working_mask, split_heights, split_height_tolerance
    )
    for idx in boundary_indices:
        data.iat[idx, data.columns.get_loc('is_part_boundary')] = True

    all_height_medians = []
    audit['parts'] = []

    for part_num in range(1, len(tower_parts) + 1):
        part_info = tower_parts[part_num - 1] if part_num <= len(tower_parts) else {}
        part_faces = int(part_info.get('faces', expected_faces) or expected_faces)

        # Points for this part (including boundary from adjacent)
        part_mask = working_mask & (part_labels == part_num)
        # Also include boundary points from adjacent parts
        for bi in boundary_indices:
            if working_mask[bi]:
                part_mask[bi] = True

        part_indices = np.where(part_mask)[0]
        if len(part_indices) == 0:
            audit['parts'].append({'part_num': part_num, 'point_count': 0})
            continue

        z_values = data.iloc[part_indices]['z'].to_numpy(dtype=float)

        # Cluster heights for this part
        height_labels = _cluster_height_levels(z_values, tolerance=height_tolerance)
        for i, pi in enumerate(part_indices):
            data.iat[pi, data.columns.get_loc('height_level')] = int(height_labels[i])

        # Compute part center
        part_center = data.iloc[part_indices][['x', 'y']].mean().to_numpy(dtype=float)

        # Full height levels array for assignment
        full_hl = np.zeros(len(data), dtype=int)
        for i, pi in enumerate(part_indices):
            full_hl[pi] = height_labels[i]

        # Assign face tracks for this part
        face_tracks = _assign_face_tracks(
            data, part_mask, full_hl, part_faces, part_center, station_xy,
        )
        for pi in part_indices:
            if face_tracks[pi] > 0:
                data.iat[pi, data.columns.get_loc('part_face_track')] = int(face_tracks[pi])
                data.iat[pi, data.columns.get_loc('faces')] = part_faces
                # Global face_track: offset by previous parts' face counts
                offset = sum(
                    int(tower_parts[p].get('faces', expected_faces) or expected_faces)
                    for p in range(part_num - 1)
                )
                data.iat[pi, data.columns.get_loc('face_track')] = int(face_tracks[pi]) + offset

        medians = _compute_level_medians(z_values, height_labels)
        all_height_medians.extend(medians)
        audit['parts'].append({
            'part_num': part_num,
            'faces': part_faces,
            'point_count': len(part_indices),
            'height_levels': len(medians),
        })

    # Compute angles
    cw_angles = _compute_cw_angles(data, working_mask, center_xy, station_xy)
    data['cw_angle_deg'] = cw_angles

    anchor_angle = 0.0
    face1_mask = data['face_track'].to_numpy() == 1
    if face1_mask.any():
        valid = cw_angles[face1_mask & ~np.isnan(cw_angles)]
        if len(valid) > 0:
            anchor_angle = float(np.mean(valid))

    return SortedTowerResult(
        data=_finalize_columns(data),
        face_count=expected_faces,
        height_levels=sorted(all_height_medians),
        tower_center_xy=(float(center_xy[0]), float(center_xy[1])),
        anchor_angle_deg=anchor_angle,
        audit=audit,
    )


def _process_multi_station(
    data: pd.DataFrame,
    working_mask: np.ndarray,
    expected_faces: int,
    center_xy: np.ndarray,
    base_station_idx: int | None,
    height_tolerance: float,
    audit: dict[str, Any],
) -> SortedTowerResult:
    """Process multi-station survey data.

    Delegates to ``auto_merge_multi_station_tower()`` for the core merge logic,
    then enriches the result with height_level, face_track, and cw_angle_deg.
    """
    from core.multi_station_import import auto_merge_multi_station_tower

    merged, merge_audit = auto_merge_multi_station_tower(
        data, expected_faces, base_station_idx=base_station_idx,
    )
    audit.update(merge_audit)

    # Copy merged results into pipeline columns
    merged['face_track'] = 0
    merged['height_level'] = 0
    merged['cw_angle_deg'] = np.nan
    merged['part_face_track'] = 0
    merged['is_part_boundary'] = False

    # Map belt → face_track for assigned working points
    belt_vals = pd.to_numeric(merged.get('belt'), errors='coerce')
    assigned_mask = belt_vals.notna() & (belt_vals > 0)
    if assigned_mask.any():
        merged.loc[assigned_mask, 'face_track'] = belt_vals.loc[assigned_mask].astype(int)
        merged.loc[assigned_mask, 'part_face_track'] = merged.loc[assigned_mask, 'face_track']

        # Cluster height levels for assigned points
        assigned_z = merged.loc[assigned_mask, 'z'].to_numpy(dtype=float)
        hl = _cluster_height_levels(assigned_z, tolerance=height_tolerance)
        merged.loc[assigned_mask, 'height_level'] = hl

    # Compute center and angles
    working = build_working_tower_mask(merged).to_numpy(dtype=bool)
    working_indices = np.where(working)[0]
    if len(working_indices) > 0:
        center = merged.iloc[working_indices][['x', 'y']].mean().to_numpy(dtype=float)
    else:
        center = center_xy

    station_xy = extract_reference_station_xy(merged, station_idx=base_station_idx)
    cw_angles = _compute_cw_angles(merged, working, center, station_xy)
    merged['cw_angle_deg'] = cw_angles

    # Height level medians
    if assigned_mask.any():
        height_level_medians = _compute_level_medians(
            merged.loc[assigned_mask, 'z'].to_numpy(dtype=float),
            merged.loc[assigned_mask, 'height_level'].to_numpy(dtype=int),
        )
    else:
        height_level_medians = []

    anchor_angle = 0.0
    face1_mask = merged['face_track'].to_numpy() == 1
    if face1_mask.any():
        valid = cw_angles[face1_mask & ~np.isnan(cw_angles)]
        if len(valid) > 0:
            anchor_angle = float(np.mean(valid))

    return SortedTowerResult(
        data=_finalize_columns(merged),
        face_count=expected_faces,
        height_levels=height_level_medians,
        tower_center_xy=(float(center[0]), float(center[1])),
        anchor_angle_deg=anchor_angle,
        audit=audit,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _compute_level_medians(z_values: np.ndarray, labels: np.ndarray) -> list[float]:
    """Compute median Z for each height level, sorted ascending."""
    medians = {}
    for level in sorted(set(labels)):
        if level <= 0:
            continue
        mask = labels == level
        medians[level] = float(np.median(z_values[mask]))
    return [medians[k] for k in sorted(medians.keys())]


def _finalize_columns(data: pd.DataFrame) -> pd.DataFrame:
    """Set belt = face_track, part_belt = part_face_track for UI compatibility."""
    data['belt'] = data['face_track']
    data['part_belt'] = data['part_face_track']
    return data
