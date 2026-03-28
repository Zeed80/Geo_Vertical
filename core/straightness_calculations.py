"""
Расчеты стрел прогиба и наклона поясов башни.

Вынесены из gui/straightness_widget.py для разделения бизнес-логики и UI.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from core.normatives import get_straightness_tolerance
from core.point_utils import (
    build_working_tower_mask as _build_working_tower_mask,
)
from core.point_utils import (
    decode_part_memberships as _decode_part_memberships,
)
from core.point_utils import (
    filter_points_by_part as _filter_points_by_part,
)


def calculate_belt_deflections(
    belt_points: pd.DataFrame,
    part_min_height: float | None = None,
    part_max_height: float | None = None,
) -> list[float]:
    """Рассчитывает локальные стрелы прогиба по трехточечным секциям.

    Для каждой секции используются три соседние точки по высоте: нижняя,
    средняя и верхняя. Крайние точки секции считаются опорными и получают 0,
    а для средней точки считается перпендикуляр до хорды между крайними.

    Соседние секции делят общую граничную точку, поэтому окна идут с шагом 2:
    `(0, 1, 2)`, `(2, 3, 4)`, `(4, 5, 6)` и т.д.

    Аргументы `part_min_height` / `part_max_height` оставлены для совместимости
    со старыми вызовами виджета, но сам расчет выполняется по уже переданному
    набору точек пояса.
    """
    del part_min_height, part_max_height

    belt_sorted = belt_points.sort_values("z").copy()
    if len(belt_sorted) < 2:
        return [0.0] * len(belt_sorted)

    deflections = [0.0] * len(belt_sorted)
    points_array = belt_sorted[["x", "y", "z"]].to_numpy(dtype=float)

    section_start = 0
    while section_start + 2 < len(points_array):
        first_point = points_array[section_start]
        middle_point = points_array[section_start + 1]
        last_point = points_array[section_start + 2]

        line_direction = last_point - first_point
        line_length = float(np.linalg.norm(line_direction))
        if np.isfinite(line_length) and line_length >= 1e-9:
            line_dir_norm = line_direction / line_length
            vector_to_middle = middle_point - first_point
            projection = np.dot(vector_to_middle, line_dir_norm) * line_dir_norm
            perpendicular = vector_to_middle - projection
            deflection_m = float(np.linalg.norm(perpendicular))
            sign = 1.0 if perpendicular[0] >= 0.0 else -1.0
            deflections[section_start + 1] = sign * deflection_m * 1000.0

        section_start += 2

    return deflections


def calculate_belt_angle(belt_points: pd.DataFrame) -> float:
    """Рассчитывает угол наклона пояса относительно вертикали (в радианах)."""
    belt_sorted = belt_points.sort_values("z")

    if len(belt_sorted) < 2:
        return 0.0

    first = belt_sorted.iloc[0]
    last = belt_sorted.iloc[-1]

    belt_vec = np.array([
        last["x"] - first["x"],
        last["y"] - first["y"],
        last["z"] - first["z"],
    ])

    vertical = np.array([0.0, 0.0, 1.0])
    cos_angle = np.dot(belt_vec, vertical) / (np.linalg.norm(belt_vec) * np.linalg.norm(vertical))
    cos_angle = np.clip(cos_angle, -1.0, 1.0)
    angle = np.arccos(cos_angle)
    return np.pi / 2 - angle if angle < np.pi / 2 else angle - np.pi / 2


def build_straightness_profiles(
    points: pd.DataFrame,
    tower_parts_info: dict | None = None,
) -> list[dict]:
    """Build canonical straightness profiles for tower face tracks."""
    if points is None or points.empty or "belt" not in points.columns:
        return []

    working = points.loc[_build_working_tower_mask(points)].copy()
    if working.empty:
        return []

    part_numbers: list[int] = []
    if tower_parts_info and tower_parts_info.get("parts"):
        part_numbers = [
            int(part.get("part_number"))
            for part in tower_parts_info["parts"]
            if part.get("part_number") is not None
        ]

    if not part_numbers and (
        ("tower_part_memberships" in working.columns and working["tower_part_memberships"].notna().any())
        or ("tower_part" in working.columns and working["tower_part"].notna().any())
    ):
        unique_parts = set()
        if "tower_part_memberships" in working.columns:
            for value in working["tower_part_memberships"].dropna():
                unique_parts.update(_decode_part_memberships(value))
        if not unique_parts and "tower_part" in working.columns:
            part_values = pd.to_numeric(working["tower_part"], errors="coerce").dropna()
            unique_parts.update(int(value) for value in part_values if int(value) > 0)
        part_numbers = sorted(int(part) for part in unique_parts if part is not None)

    part_frames: list[tuple[int, pd.DataFrame]] = []
    if part_numbers:
        for part_num in sorted(set(part_numbers)):
            part_points = _filter_points_by_part(working, part_num)
            if not part_points.empty:
                part_frames.append((int(part_num), part_points.copy()))
    else:
        part_frames.append((1, working.copy()))

    profiles: list[dict] = []
    for part_num, part_points in part_frames:
        numeric_belts = pd.to_numeric(part_points["belt"], errors="coerce")
        part_points = part_points.loc[numeric_belts.notna()].copy()
        if part_points.empty:
            continue

        part_points["belt"] = numeric_belts.loc[part_points.index].astype(int)
        part_min_height = float(part_points["z"].min())
        part_max_height = float(part_points["z"].max())
        part_height = max(0.0, part_max_height - part_min_height)
        tolerance_mm = float(get_straightness_tolerance(part_height) * 1000.0) if part_height > 0 else 0.0

        for belt_num, belt_points in part_points.groupby("belt"):
            belt_sorted = belt_points.sort_values("z").copy()
            if len(belt_sorted) < 2:
                continue

            deflections = calculate_belt_deflections(belt_sorted)
            profile_points = []
            for idx, (_, point) in enumerate(belt_sorted.iterrows()):
                profile_points.append(
                    {
                        "source_index": point.name,
                        "z": float(point["z"]),
                        "deflection_mm": float(deflections[idx] if idx < len(deflections) else 0.0),
                    }
                )

            profiles.append(
                {
                    "part_number": int(part_num),
                    "belt": int(belt_num),
                    "section_length_m": float(part_height),
                    "tolerance_mm": tolerance_mm,
                    "max_deflection_mm": float(
                        max((abs(item["deflection_mm"]) for item in profile_points), default=0.0)
                    ),
                    "part_min_height": float(part_min_height),
                    "part_max_height": float(part_max_height),
                    "points": profile_points,
                }
            )

    profiles.sort(key=lambda item: (int(item.get("part_number", 1)), int(item.get("belt", 0))))
    return profiles


def auto_detect_split_height(points: pd.DataFrame) -> float | None:
    """Автоматически определяет высоту раздвоения составной башни."""
    if points is None or points.empty or len(points) < 6:
        return None

    working = points.copy()
    if "is_station" in working.columns:
        working = working[~working["is_station"].fillna(False).astype(bool)]

    if working.empty:
        return None

    z_values = working["z"].values
    z_min, z_max = z_values.min(), z_values.max()
    z_range = z_max - z_min

    if z_range < 1.0:
        return None

    num_bins = max(10, min(50, len(working) // 5))
    hist, bin_edges = np.histogram(z_values, bins=num_bins)

    min_idx = np.argmin(hist[1:-1]) + 1
    if min_idx < len(bin_edges) - 1:
        split_height = (bin_edges[min_idx] + bin_edges[min_idx + 1]) / 2.0
        if z_min < split_height < z_max:
            return float(split_height)

    return float(np.median(z_values))


def find_station_point(points: pd.DataFrame, min_distance: float = 15.0) -> int | None:
    """Автоматически находит точку стояния прибора."""
    if points is None or points.empty or len(points) < 2:
        return None

    positions = points[["x", "y", "z"]].values
    best_candidate = None
    best_min_dist = 0.0

    for pos_idx, (original_idx, _) in enumerate(points.iterrows()):
        distances = np.linalg.norm(positions - positions[pos_idx], axis=1)
        mask = np.ones(len(distances), dtype=bool)
        mask[pos_idx] = False
        other_distances = distances[mask]

        if len(other_distances) == 0:
            continue

        min_dist_to_others = other_distances.min()
        if min_dist_to_others >= min_distance and min_dist_to_others > best_min_dist:
            best_min_dist = min_dist_to_others
            best_candidate = original_idx

    return best_candidate
