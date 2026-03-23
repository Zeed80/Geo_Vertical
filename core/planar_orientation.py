"""Shared helpers for clockwise tower ordering in plan view."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd

_EPS = 1e-9
BELT_NUMBERING_VERSION = "cw_station_right_v2"


def normalize_positive_angle_rad(angle_rad: float) -> float:
    """Normalize an angle to the [0, 2*pi) interval."""
    return float(angle_rad % (2.0 * math.pi))


def normalize_signed_angle_rad(angle_rad: float) -> float:
    """Normalize an angle to the (-pi, pi] interval."""
    angle = normalize_positive_angle_rad(angle_rad)
    if angle > math.pi:
        angle -= 2.0 * math.pi
    return float(angle)


def normalize_signed_angle_deg(angle_deg: float) -> float:
    """Normalize an angle to the (-180, 180] interval."""
    angle = float(angle_deg % 360.0)
    if angle > 180.0:
        angle -= 360.0
    return angle


def _to_xy_vector(values: Sequence[float] | np.ndarray) -> np.ndarray:
    vector = np.asarray(values, dtype=float)
    if vector.shape[0] < 2:
        raise ValueError("Expected a 2D vector or point.")
    return np.array([float(vector[0]), float(vector[1])], dtype=float)


def _normalize_xy(vector_xy: Sequence[float] | np.ndarray) -> np.ndarray | None:
    vector = _to_xy_vector(vector_xy)
    norm = float(np.linalg.norm(vector))
    if norm <= _EPS:
        return None
    return vector / norm


def math_signed_angle_rad(
    source_xy: Sequence[float] | np.ndarray,
    target_xy: Sequence[float] | np.ndarray,
) -> float:
    """Return the signed mathematical angle from source to target (CCW positive)."""
    source = _normalize_xy(source_xy)
    target = _normalize_xy(target_xy)
    if source is None or target is None:
        return 0.0
    dot = float(np.clip(np.dot(source, target), -1.0, 1.0))
    det = float(source[0] * target[1] - source[1] * target[0])
    return float(math.atan2(det, dot))


def domain_signed_angle_rad(
    source_xy: Sequence[float] | np.ndarray,
    target_xy: Sequence[float] | np.ndarray,
) -> float:
    """Return the signed domain angle from source to target (CW positive)."""
    return float(-math_signed_angle_rad(source_xy, target_xy))


def domain_signed_angle_deg(
    source_xy: Sequence[float] | np.ndarray,
    target_xy: Sequence[float] | np.ndarray,
) -> float:
    """Return the signed domain angle from source to target in degrees (CW positive)."""
    return float(math.degrees(domain_signed_angle_rad(source_xy, target_xy)))


def domain_rotation_deg_to_math_rad(angle_deg: float) -> float:
    """Convert a CW-positive domain rotation in degrees to a math rotation in radians."""
    return float(math.radians(-float(angle_deg)))


def observer_right_axis(
    tower_center_xy: Sequence[float] | np.ndarray,
    station_xy: Sequence[float] | np.ndarray | None,
) -> np.ndarray:
    """Return the observer's right axis looking from station to the tower center."""
    if station_xy is None:
        return np.array([1.0, 0.0], dtype=float)

    center = _to_xy_vector(tower_center_xy)
    station = _to_xy_vector(station_xy)
    forward = center - station
    norm = float(np.linalg.norm(forward))
    if norm <= _EPS:
        return np.array([1.0, 0.0], dtype=float)
    return np.array([forward[1], -forward[0]], dtype=float) / norm


def extract_reference_station_xy(
    points: pd.DataFrame | None,
    *,
    station_idx: Any | None = None,
) -> np.ndarray | None:
    """Extract the first station XY from a DataFrame when available."""
    if points is None or points.empty:
        return None

    if station_idx is not None and station_idx in points.index:
        row = points.loc[station_idx]
        if pd.notna(row.get("x")) and pd.notna(row.get("y")):
            return row[["x", "y"]].to_numpy(dtype=float)

    if "is_station" in points.columns:
        station_mask = points["is_station"].fillna(False).astype(bool)
        if station_mask.any():
            row = points.loc[station_mask].iloc[0]
            return row[["x", "y"]].to_numpy(dtype=float)

    if "name" in points.columns:
        names = points["name"].astype(str).str.lower()
        station_rows = points[names.str.startswith("st")]
        if not station_rows.empty:
            row = station_rows.iloc[0]
            return row[["x", "y"]].to_numpy(dtype=float)

    return None


def clockwise_angle_from_anchor_rad(
    vector_xy: Sequence[float] | np.ndarray,
    *,
    anchor_vector_xy: Sequence[float] | np.ndarray,
) -> float:
    """Return the clockwise angle from anchor_vector to vector in [0, 2*pi)."""
    return normalize_positive_angle_rad(
        domain_signed_angle_rad(anchor_vector_xy, vector_xy)
    )


def _ensure_center_xy(
    points_xy: np.ndarray,
    center_xy: Sequence[float] | np.ndarray | None = None,
) -> np.ndarray:
    if center_xy is not None:
        return _to_xy_vector(center_xy)
    if points_xy.size == 0:
        return np.zeros(2, dtype=float)
    return np.mean(points_xy, axis=0, dtype=float)


def select_rightmost_anchor_vector(
    points_xy: Sequence[Sequence[float]] | np.ndarray,
    *,
    center_xy: Sequence[float] | np.ndarray | None = None,
    station_xy: Sequence[float] | np.ndarray | None = None,
) -> np.ndarray:
    """
    Choose the anchor vector for belt 1.

    The anchor is the point with the maximum projection on the observer's right
    axis when looking from the station to the tower center. Without a station we
    fall back to the global +X axis.
    """
    points = np.asarray(points_xy, dtype=float)
    if points.size == 0:
        return np.array([1.0, 0.0], dtype=float)

    center = _ensure_center_xy(points, center_xy)
    vectors = points - center
    anchor_axis = observer_right_axis(center, station_xy)
    distances = np.linalg.norm(vectors, axis=1)
    projections = vectors @ anchor_axis
    angular_deviation = np.array(
        [
            min(
                clockwise_angle_from_anchor_rad(vector, anchor_vector_xy=anchor_axis),
                clockwise_angle_from_anchor_rad(anchor_axis, anchor_vector_xy=vector)
                if np.linalg.norm(vector) > _EPS
                else 0.0,
            )
            for vector in vectors
        ],
        dtype=float,
    )

    order = np.lexsort((-distances, angular_deviation, -projections))
    best_idx = int(order[0])
    if distances[best_idx] <= _EPS:
        return anchor_axis
    return np.asarray(vectors[best_idx], dtype=float)


def clockwise_order_indices(
    points_xy: Sequence[Sequence[float]] | np.ndarray,
    *,
    center_xy: Sequence[float] | np.ndarray | None = None,
    station_xy: Sequence[float] | np.ndarray | None = None,
    anchor_vector_xy: Sequence[float] | np.ndarray | None = None,
) -> np.ndarray:
    """Return point indices ordered clockwise from the selected anchor."""
    points = np.asarray(points_xy, dtype=float)
    if len(points) == 0:
        return np.array([], dtype=int)

    center = _ensure_center_xy(points, center_xy)
    vectors = points - center
    anchor = (
        _to_xy_vector(anchor_vector_xy)
        if anchor_vector_xy is not None
        else select_rightmost_anchor_vector(points, center_xy=center, station_xy=station_xy)
    )

    angles = np.array(
        [clockwise_angle_from_anchor_rad(vector, anchor_vector_xy=anchor) for vector in vectors],
        dtype=float,
    )
    distances = np.linalg.norm(vectors, axis=1)
    return np.lexsort((distances, angles))


def sort_points_clockwise(
    points: pd.DataFrame,
    *,
    station_xy: Sequence[float] | np.ndarray | None = None,
    center_xy: Sequence[float] | np.ndarray | None = None,
    anchor_vector_xy: Sequence[float] | np.ndarray | None = None,
    preserve_index: bool = False,
) -> pd.DataFrame:
    """Sort DataFrame points clockwise using the shared domain ordering."""
    if points.empty:
        return points.copy()

    order = clockwise_order_indices(
        points[["x", "y"]].to_numpy(dtype=float),
        center_xy=center_xy,
        station_xy=station_xy,
        anchor_vector_xy=anchor_vector_xy,
    )
    sorted_points = points.iloc[order]
    return sorted_points if preserve_index else sorted_points.reset_index(drop=True)


def observer_left_to_right_order_indices(
    points_xy: Sequence[Sequence[float]] | np.ndarray,
    *,
    tower_center_xy: Sequence[float] | np.ndarray,
    station_xy: Sequence[float] | np.ndarray | None,
) -> np.ndarray:
    """Return indices ordered from the observer's left to right."""
    points = np.asarray(points_xy, dtype=float)
    if len(points) == 0:
        return np.array([], dtype=int)
    if station_xy is None:
        return np.arange(len(points), dtype=int)

    station = _to_xy_vector(station_xy)
    center = _to_xy_vector(tower_center_xy)
    right_axis = observer_right_axis(center, station)
    left_axis = -right_axis
    lateral_scores = (points - station) @ left_axis
    return np.argsort(-lateral_scores)
