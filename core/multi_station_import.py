"""Helpers for multi-station Trimble mast imports."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable
from typing import Any

import numpy as np
import pandas as pd

from core.import_grouping import group_points_by_global_angle
from core.point_utils import (
    build_non_working_tower_mask,
    build_working_tower_mask,
    normalize_tower_point_flags,
)

STRICT_DUPLICATE_XY_TOLERANCE = 0.05
REVIEW_DUPLICATE_XY_TOLERANCE = 0.10
DUPLICATE_LEVEL_TOLERANCE = 0.15


def _circular_delta_deg(from_angle: float, to_angle: float) -> float:
    delta = (to_angle - from_angle + 180.0) % 360.0 - 180.0
    return float(delta)


def _estimate_tower_center_xy(data: pd.DataFrame) -> np.ndarray:
    working_mask = build_working_tower_mask(data)
    working = data.loc[working_mask, ['x', 'y']]
    if working.empty:
        working = data[['x', 'y']]
    return working.mean().to_numpy(dtype=float)


def _angle_from_center(point_xy: np.ndarray, center_xy: np.ndarray) -> float:
    return float(math.degrees(math.atan2(point_xy[1] - center_xy[1], point_xy[0] - center_xy[0])))


def _ordered_indices(data: pd.DataFrame) -> list[Any]:
    if 'source_order' in data.columns:
        ordered = data.sort_values('source_order')
        return ordered.index.tolist()
    return data.index.tolist()


def split_survey_station_blocks(data: pd.DataFrame) -> list[dict[str, Any]]:
    """Split rows into station observation blocks preserving survey order."""
    normalized = normalize_tower_point_flags(data)
    station_mask = normalized['is_station']

    if 'survey_station_order' in normalized.columns and normalized['survey_station_order'].notna().any():
        station_orders = (
            pd.to_numeric(normalized['survey_station_order'], errors='coerce')
            .dropna()
            .astype(int)
            .unique()
            .tolist()
        )
        station_orders = sorted(station_orders)
        blocks: list[dict[str, Any]] = []
        for station_order in station_orders:
            order_mask = pd.to_numeric(normalized['survey_station_order'], errors='coerce').eq(station_order)
            block_rows = normalized[order_mask].copy()
            if block_rows.empty:
                continue
            station_rows = block_rows[station_mask.reindex(block_rows.index, fill_value=False)]
            station_idx = station_rows.index[0] if not station_rows.empty else None
            station_name = None
            if station_idx is not None:
                station_name = str(block_rows.loc[station_idx, 'name'])
            elif 'survey_station_name' in block_rows.columns and block_rows['survey_station_name'].notna().any():
                station_name = str(block_rows['survey_station_name'].dropna().iloc[0])
            blocks.append(
                {
                    'station_idx': station_idx,
                    'station_name': station_name,
                    'station_order': int(station_order),
                    'indices': block_rows.index.tolist(),
                }
            )
        return blocks

    blocks = []
    current_block: dict[str, Any] | None = None
    for idx in _ordered_indices(normalized):
        if bool(normalized.at[idx, 'is_station']):
            current_block = {
                'station_idx': idx,
                'station_name': str(normalized.at[idx, 'name']),
                'station_order': len(blocks) + 1,
                'indices': [idx],
            }
            blocks.append(current_block)
            continue
        if current_block is not None:
            current_block['indices'].append(idx)

    return blocks


def _build_block_groups(
    data: pd.DataFrame,
    block: dict[str, Any],
    expected_faces: int,
) -> list[dict[str, Any]]:
    working_mask = build_working_tower_mask(data)
    block_indices = [idx for idx in block['indices'] if idx in data.index]
    working_indices = [idx for idx in block_indices if bool(working_mask.get(idx, False))]
    if not working_indices:
        return []

    station_idx = block.get('station_idx')
    station_xy = None
    if station_idx is not None and station_idx in data.index:
        station_xy = data.loc[station_idx, ['x', 'y']].to_numpy(dtype=float)

    local_groups = group_points_by_global_angle(
        data,
        working_indices,
        expected_faces,
        station_idx=station_idx,
        reference_station_xy=station_xy,
    )

    group_meta: list[dict[str, Any]] = []
    for local_slot, indices in enumerate(local_groups, start=1):
        if not indices:
            continue
        centroid_xy = data.loc[indices, ['x', 'y']].mean().to_numpy(dtype=float)
        group_meta.append(
            {
                'local_slot': int(local_slot),
                'indices': list(indices),
                'centroid_xy': centroid_xy,
                'point_count': len(indices),
            }
        )
    return group_meta


def _build_station_rotation_shift(
    base_station_xy: np.ndarray | None,
    current_station_xy: np.ndarray | None,
    center_xy: np.ndarray,
    expected_faces: int,
) -> int:
    if expected_faces <= 0 or base_station_xy is None or current_station_xy is None:
        return 0
    step = 360.0 / float(expected_faces)
    base_angle = _angle_from_center(base_station_xy, center_xy)
    current_angle = _angle_from_center(current_station_xy, center_xy)
    shift_deg = (base_angle - current_angle) % 360.0
    return int(round(shift_deg / step)) % expected_faces


def _find_duplicate_match(
    data: pd.DataFrame,
    point_idx: Any,
    candidate_indices: Iterable[Any],
) -> dict[str, Any] | None:
    point_row = data.loc[point_idx]
    point_xy = point_row[['x', 'y']].to_numpy(dtype=float)
    point_z = float(point_row['z'])

    best_match: dict[str, Any] | None = None
    for candidate_idx in candidate_indices:
        candidate_row = data.loc[candidate_idx]
        z_delta = abs(point_z - float(candidate_row['z']))
        if z_delta > DUPLICATE_LEVEL_TOLERANCE:
            continue
        candidate_xy = candidate_row[['x', 'y']].to_numpy(dtype=float)
        xy_distance = float(np.linalg.norm(point_xy - candidate_xy))
        if xy_distance > REVIEW_DUPLICATE_XY_TOLERANCE:
            continue

        match_type = 'duplicate'
        if xy_distance > STRICT_DUPLICATE_XY_TOLERANCE:
            match_type = 'review'

        match = {
            'candidate_idx': candidate_idx,
            'xy_distance': xy_distance,
            'z_delta': z_delta,
            'match_type': match_type,
        }
        if best_match is None:
            best_match = match
            continue
        if match['match_type'] == 'duplicate' and best_match['match_type'] != 'duplicate':
            best_match = match
            continue
        if xy_distance < best_match['xy_distance']:
            best_match = match

    return best_match


def auto_merge_multi_station_tower(
    data: pd.DataFrame,
    expected_faces: int,
    *,
    base_station_idx: Any | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Auto-merge multiple station blocks into global mast belts."""
    if expected_faces <= 0:
        raise ValueError("expected_faces must be positive")

    merged = normalize_tower_point_flags(data).copy()
    if 'belt' not in merged.columns:
        merged['belt'] = pd.NA
    if 'part_belt' not in merged.columns:
        merged['part_belt'] = pd.NA
    if 'faces' not in merged.columns:
        merged['faces'] = pd.NA
    if 'station_role' not in merged.columns:
        merged['station_role'] = None

    merged['belt'] = pd.NA
    merged['part_belt'] = pd.NA
    merged['faces'] = pd.NA
    merged['is_control'] = False
    merged['station_role'] = None

    blocks = split_survey_station_blocks(merged)
    if not blocks:
        return merged, {
            'mode': 'single_station_fallback',
            'multi_station_detected': False,
            'station_blocks': [],
        }

    base_block = None
    if base_station_idx is not None:
        for block in blocks:
            if block.get('station_idx') == base_station_idx:
                base_block = block
                break
    if base_block is None:
        base_block = blocks[0]

    ordered_blocks = [base_block] + [block for block in blocks if block is not base_block]
    center_xy = _estimate_tower_center_xy(merged)
    base_station_xy = None
    if base_block.get('station_idx') is not None:
        base_station_xy = merged.loc[base_block['station_idx'], ['x', 'y']].to_numpy(dtype=float)

    active_by_belt: dict[int, list[Any]] = defaultdict(list)
    block_summaries: list[dict[str, Any]] = []
    control_duplicates: list[dict[str, Any]] = []
    review_duplicates: list[dict[str, Any]] = []
    new_belts: set[int] = set()

    for block in ordered_blocks:
        station_idx = block.get('station_idx')
        station_name = str(block.get('station_name') or '')
        current_station_xy = None
        if station_idx is not None and station_idx in merged.index:
            current_station_xy = merged.loc[station_idx, ['x', 'y']].to_numpy(dtype=float)
            merged.at[station_idx, 'station_role'] = 'primary' if block is base_block else 'secondary'

        shift = _build_station_rotation_shift(
            base_station_xy,
            current_station_xy,
            center_xy,
            expected_faces,
        )
        groups = _build_block_groups(merged, block, expected_faces)
        block_summary = {
            'station_idx': station_idx,
            'station_name': station_name,
            'station_order': int(block.get('station_order') or 0),
            'rotation_shift': int(shift),
            'tracks': [],
        }

        duplicate_distances: list[float] = []
        block_new_belts: set[int] = set()
        for group in groups:
            local_slot = int(group['local_slot'])
            global_belt = ((local_slot - 1 + shift) % expected_faces) + 1
            belt_was_empty = len(active_by_belt.get(global_belt, [])) == 0
            group_assigned = 0
            group_controls = 0
            group_reviews = 0

            for point_idx in group['indices']:
                match = _find_duplicate_match(merged, point_idx, active_by_belt.get(global_belt, []))
                if match is not None:
                    merged.at[point_idx, 'is_control'] = True
                    merged.at[point_idx, 'belt'] = pd.NA
                    merged.at[point_idx, 'part_belt'] = pd.NA
                    merged.at[point_idx, 'faces'] = pd.NA
                    duplicate_record = {
                        'station_name': station_name,
                        'station_order': int(block.get('station_order') or 0),
                        'point_idx': point_idx,
                        'point_name': str(merged.at[point_idx, 'name']),
                        'matched_idx': match['candidate_idx'],
                        'matched_name': str(merged.at[match['candidate_idx'], 'name']),
                        'global_belt': int(global_belt),
                        'xy_distance': round(float(match['xy_distance']), 6),
                        'z_delta': round(float(match['z_delta']), 6),
                    }
                    duplicate_distances.append(float(match['xy_distance']))
                    if match['match_type'] == 'review':
                        duplicate_record['review_required'] = True
                        review_duplicates.append(duplicate_record)
                        group_reviews += 1
                    else:
                        control_duplicates.append(duplicate_record)
                        group_controls += 1
                    continue

                merged.at[point_idx, 'belt'] = int(global_belt)
                merged.at[point_idx, 'part_belt'] = int(global_belt)
                merged.at[point_idx, 'faces'] = int(expected_faces)
                active_by_belt[int(global_belt)].append(point_idx)
                group_assigned += 1
            if belt_was_empty and group_assigned > 0 and block is not base_block:
                new_belts.add(int(global_belt))
                block_new_belts.add(int(global_belt))

            block_summary['tracks'].append(
                {
                    'local_belt': int(local_slot),
                    'global_belt': int(global_belt),
                    'point_count': int(group['point_count']),
                    'assigned_points': int(group_assigned),
                    'control_points': int(group_controls),
                    'review_points': int(group_reviews),
                }
            )

        if duplicate_distances:
            squared = np.square(np.asarray(duplicate_distances, dtype=float))
            block_summary['registration_rmse'] = round(float(np.sqrt(np.mean(squared))), 6)
        else:
            block_summary['registration_rmse'] = None
        block_summary['new_global_belts'] = sorted(block_new_belts)
        block_summaries.append(block_summary)

    working_mask = build_working_tower_mask(merged)
    active_mask = working_mask & merged['belt'].notna()
    active_belts = sorted(int(value) for value in merged.loc[active_mask, 'belt'].dropna().astype(int).unique())
    new_belts.discard(0)

    audit = {
        'mode': 'multi_station',
        'multi_station_detected': len(blocks) > 1,
        'base_station_idx': base_block.get('station_idx'),
        'base_station_name': base_block.get('station_name'),
        'expected_faces': int(expected_faces),
        'station_blocks': block_summaries,
        'control_duplicates': control_duplicates,
        'review_duplicates': review_duplicates,
        'new_belts': sorted(int(value) for value in new_belts if value in active_belts),
        'active_belts': active_belts,
        'working_point_count': int(active_mask.sum()),
        'control_point_count': int(merged['is_control'].sum()),
    }
    return merged, audit
