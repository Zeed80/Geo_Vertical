from __future__ import annotations

import ast
import warnings
from collections import Counter
from pathlib import Path

import pandas as pd
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from core.calculations import process_tower_data
from core.point_utils import decode_part_memberships
from gui.data_table import DataTableWidget

FACE_COORDS = {
    1: (1.0, 0.0),
    2: (0.0, 1.0),
    3: (-1.0, 0.0),
    4: (0.0, -1.0),
}


def _build_square_tower(
    heights: list[float],
    *,
    center_offsets: dict[float, tuple[float, float]] | None = None,
    point_offsets: dict[tuple[int, float], tuple[float, float]] | None = None,
    row_overrides: dict[float, dict] | None = None,
    extra_rows: list[dict] | None = None,
) -> pd.DataFrame:
    center_offsets = center_offsets or {}
    point_offsets = point_offsets or {}
    row_overrides = row_overrides or {}
    rows: list[dict] = []

    for height in heights:
        center_x, center_y = center_offsets.get(float(height), (0.0, 0.0))
        per_height = row_overrides.get(float(height), {})
        for belt, (base_x, base_y) in FACE_COORDS.items():
            offset_x, offset_y = point_offsets.get((belt, float(height)), (0.0, 0.0))
            row = {
                "name": f"B{belt}_{height}",
                "x": center_x + base_x + offset_x,
                "y": center_y + base_y + offset_y,
                "z": float(height),
                "belt": belt,
            }
            row.update(per_height)
            rows.append(row)

    if extra_rows:
        rows.extend(extra_rows)

    return pd.DataFrame(rows)


def test_calculations_module_keeps_single_canonical_definitions():
    module_path = Path(__file__).resolve().parents[1] / "core" / "calculations.py"
    tree = ast.parse(module_path.read_text(encoding="utf-8-sig"))
    function_counts = Counter(
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
    )

    assert function_counts["group_points_by_height"] == 1
    assert function_counts["_get_cache_key"] == 1
    assert function_counts["calculate_straightness_deviation"] == 1


def test_synthetic_perfect_tower_has_zero_verticality_and_straightness():
    data = _build_square_tower([0.0, 5.0, 10.0])

    results = process_tower_data(data, height_tolerance=0.1, use_cache=False)

    assert results["valid"]
    assert len(results["centers"]) == 3
    assert float(results["centers"]["deviation"].abs().max()) < 1e-12
    assert float(results["centers"]["straightness_deviation"].abs().max()) < 1e-12
    assert results["straightness_summary"]["max_deflection_mm"] == 0.0
    assert all(profile["max_deflection_mm"] == 0.0 for profile in results["straightness_profiles"])


def test_local_belt_bow_does_not_shift_axis_but_is_visible_in_straightness():
    data = _build_square_tower(
        [0.0, 5.0, 10.0],
        point_offsets={
            (1, 5.0): (0.02, 0.0),
            (3, 5.0): (-0.02, 0.0),
        },
    )

    results = process_tower_data(data, height_tolerance=0.1, use_cache=False)
    profile_max_by_belt = {
        int(profile["belt"]): float(profile["max_deflection_mm"])
        for profile in results["straightness_profiles"]
    }

    assert results["valid"]
    assert float(results["centers"]["deviation"].abs().max()) < 1e-12
    assert profile_max_by_belt[1] > 0.0
    assert profile_max_by_belt[3] > 0.0
    assert profile_max_by_belt[2] == 0.0
    assert profile_max_by_belt[4] == 0.0
    assert results["straightness_summary"]["max_deflection_mm"] > 0.0


def test_service_points_do_not_pollute_synthetic_results():
    clean = _build_square_tower([0.0, 5.0, 10.0])
    service_rows = [
        {
            "name": "ST1",
            "x": 25.0,
            "y": 0.0,
            "z": 0.0,
            "belt": None,
            "is_station": True,
            "is_auxiliary": False,
            "is_control": False,
        },
        {
            "name": "AUX1",
            "x": 30.0,
            "y": 30.0,
            "z": 3.0,
            "belt": None,
            "is_station": False,
            "is_auxiliary": True,
            "is_control": False,
        },
        {
            "name": "CTRL1",
            "x": -25.0,
            "y": 10.0,
            "z": 8.0,
            "belt": None,
            "is_station": False,
            "is_auxiliary": False,
            "is_control": True,
        },
    ]
    augmented = _build_square_tower([0.0, 5.0, 10.0], extra_rows=service_rows)

    clean_results = process_tower_data(clean, height_tolerance=0.1, use_cache=False)
    augmented_results = process_tower_data(augmented, height_tolerance=0.1, use_cache=False)

    clean_centers = clean_results["centers"][["z", "deviation", "straightness_deviation"]].reset_index(drop=True)
    augmented_centers = augmented_results["centers"][["z", "deviation", "straightness_deviation"]].reset_index(drop=True)

    assert clean_centers.equals(augmented_centers)
    assert clean_results["straightness_summary"] == augmented_results["straightness_summary"]


def test_composite_boundary_section_keeps_shared_memberships_and_profiles_per_part():
    data = _build_square_tower(
        [0.0, 10.0, 20.0],
        row_overrides={
            0.0: {
                "tower_part": 1,
                "tower_part_memberships": "[1]",
                "is_part_boundary": False,
            },
            10.0: {
                "tower_part": 1,
                "tower_part_memberships": "[1, 2]",
                "is_part_boundary": True,
            },
            20.0: {
                "tower_part": 2,
                "tower_part_memberships": "[2]",
                "is_part_boundary": False,
            },
        },
    )

    results = process_tower_data(data, height_tolerance=0.1, use_cache=False)
    boundary_center = results["centers"].loc[results["centers"]["z"] == 10.0].iloc[0]
    part_numbers = {
        int(profile["part_number"])
        for profile in results["straightness_profiles"]
    }

    assert results["valid"]
    assert len(results["centers"]) == 3
    assert decode_part_memberships(boundary_center["tower_part_memberships"]) == [1, 2]
    assert results["tower_parts_info"]["split_height"] == 10.0
    assert part_numbers == {1, 2}


def test_data_table_normalizes_boundary_flags_without_futurewarning():
    app = QApplication.instance() or QApplication([])
    _ = app
    widget = DataTableWidget()
    data = pd.DataFrame(
        [
            {"name": "P1", "x": 1.0, "y": 0.0, "z": 0.0, "is_part_boundary": None},
            {"name": "P2", "x": -1.0, "y": 0.0, "z": 5.0, "is_part_boundary": "1"},
            {"name": "P3", "x": 0.0, "y": 1.0, "z": 10.0, "is_part_boundary": "false"},
        ]
    )

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", FutureWarning)
        widget.set_data(data)

    future_messages = [str(item.message) for item in caught if issubclass(item.category, FutureWarning)]

    assert not any("Downcasting object dtype arrays on .fillna" in message for message in future_messages)
    assert widget.original_data["is_part_boundary"].tolist() == [False, True, False]


def test_data_table_falls_back_when_station_point_index_is_empty_string():
    app = QApplication.instance() or QApplication([])
    _ = app
    widget = DataTableWidget()
    data = pd.DataFrame(
        [
            {"name": "ST1", "x": 10.0, "y": 0.0, "z": 1.5, "is_station": True, "point_index": ""},
            {"name": "P1", "x": 1.0, "y": 0.0, "z": 0.0, "belt": 1, "is_station": False},
        ]
    )

    widget.set_data(data)

    station_item = widget.station_table.item(0, 0)
    assert station_item.text() == "1"
    assert station_item.data(Qt.ItemDataRole.UserRole) == 1
