import math
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pandas as pd
import pytest
from PyQt6.QtWidgets import QApplication

from core.data_loader import load_survey_data
from core.face_track_completion import (
    CompletionPartSpec,
    FaceTrackCompleter,
    infer_completion_part_specs,
    suggest_face_count,
)
from core.point_utils import build_working_tower_mask
from core.section_operations import (
    add_missing_points_for_sections,
    find_section_levels,
    get_section_lines,
)
from core.sorting_pipeline import sort_imported_tower_points
from gui.belt_completion_dialog import BeltCompletionDialog
from gui.data_import_wizard import DataImportWizard


EXAMPLES_DIR = os.path.join(os.path.dirname(__file__), "..", "examples")
_APP = QApplication.instance() or QApplication([])


def _make_regular_track_data(
    *,
    z_levels: list[float],
    faces: int = 4,
    rotation_deg: float = 20.0,
    center_fn=None,
    radius_fn=None,
    tower_part_fn=None,
    z_offsets=None,
) -> pd.DataFrame:
    center_fn = center_fn or (lambda z: (0.0, 0.0))
    radius_fn = radius_fn or (lambda z: 3.0)
    z_offsets = z_offsets or {}
    rows = []
    point_index = 1
    step = 2.0 * math.pi / faces
    rotation = math.radians(rotation_deg)

    for height_level, z_base in enumerate(z_levels, start=1):
        part_number = int(tower_part_fn(z_base)) if tower_part_fn is not None else 1
        for track in range(1, faces + 1):
            point_z = float(z_base + z_offsets.get(track, 0.0))
            center_x, center_y = center_fn(point_z)
            radius = radius_fn(point_z)
            angle = rotation + step * (track - 1)
            x_value = center_x + radius * math.cos(angle)
            y_value = center_y + radius * math.sin(angle)
            rows.append(
                {
                    "name": f"P{point_index}",
                    "x": x_value,
                    "y": y_value,
                    "z": point_z,
                    "face_track": track,
                    "part_face_track": track,
                    "belt": track,
                    "part_belt": track,
                    "height_level": height_level,
                    "tower_part": part_number,
                    "tower_part_memberships": f"[{part_number}]",
                    "is_part_boundary": False,
                    "faces": faces,
                    "point_index": point_index,
                    "is_station": False,
                    "is_auxiliary": False,
                    "is_control": False,
                }
            )
            point_index += 1
    return pd.DataFrame(rows)


def test_suggest_face_count_prefers_square_for_three_of_four_levels():
    full = _make_regular_track_data(z_levels=[0.0, 10.0, 20.0, 30.0], faces=4)
    partial = full[full["face_track"] != 4].copy().reset_index(drop=True)

    assert suggest_face_count(partial, default_faces=4) == 4


def test_face_track_completer_builds_missing_fourth_track_and_uses_diagonal_z():
    z_offsets = {1: 0.00, 2: 0.12, 3: 0.04, 4: -0.05}
    full = _make_regular_track_data(z_levels=[0.0, 10.0, 20.0, 30.0], faces=4, z_offsets=z_offsets)
    partial = full[full["face_track"] != 4].copy().reset_index(drop=True)

    completer = FaceTrackCompleter(
        partial,
        [CompletionPartSpec(part_number=1, z_min=-1.0, z_max=40.0, shape="prism", faces=4)],
    )
    merged, generated = completer.preview(z_method="diagonal")

    assert len(generated) == 4
    assert set(generated["face_track"].astype(int)) == {4}
    assert len(merged) == len(partial) + 4

    expected_z = (
        full[full["face_track"] == 2]
        .sort_values("height_level")["z"]
        .to_numpy(dtype=float)
    )
    actual_z = (
        generated.sort_values("height_level")["z"]
        .to_numpy(dtype=float)
    )
    assert np.allclose(actual_z, expected_z, atol=1e-9)


def test_face_track_completer_matches_composite_pyramid_prism_geometry():
    z_levels = [0.0, 10.0, 20.0, 30.0, 40.0, 50.0]
    boundary = 25.0

    def radius_fn(z_value: float) -> float:
        if z_value < boundary:
            return 4.0 - 0.04 * z_value
        return 3.0

    def part_fn(z_value: float) -> int:
        return 1 if z_value < boundary else 2

    full = _make_regular_track_data(
        z_levels=z_levels,
        faces=4,
        center_fn=lambda z: (0.02 * z, -0.01 * z),
        radius_fn=radius_fn,
        tower_part_fn=part_fn,
    )
    partial = full[full["face_track"] != 4].copy().reset_index(drop=True)
    specs = [
        CompletionPartSpec(part_number=1, z_min=-1.0, z_max=boundary, shape="truncated_pyramid", faces=4),
        CompletionPartSpec(part_number=2, z_min=boundary, z_max=60.0, shape="prism", faces=4),
    ]

    completer = FaceTrackCompleter(partial, specs)
    _, generated = completer.preview(z_method="mean")

    assert len(generated) == len(z_levels)
    generated = generated.sort_values("height_level").reset_index(drop=True)
    expected = full[full["face_track"] == 4].sort_values("height_level").reset_index(drop=True)

    assert np.allclose(generated["x"].to_numpy(dtype=float), expected["x"].to_numpy(dtype=float), atol=0.05)
    assert np.allclose(generated["y"].to_numpy(dtype=float), expected["y"].to_numpy(dtype=float), atol=0.05)
    assert list(generated["tower_part"].astype(int)) == list(expected["tower_part"].astype(int))


def test_izob_infers_two_parts_and_generates_track_four():
    path = os.path.join(EXAMPLES_DIR, "Izob", "izob-ks-stavr-novoaleks-st2.jxl")
    loaded = load_survey_data(path)
    sorted_result = sort_imported_tower_points(loaded.data, expected_faces=3, multi_station=True)
    data = sorted_result.data

    specs = infer_completion_part_specs(data, default_faces=4)
    assert [(spec.shape, spec.faces) for spec in specs] == [
        ("truncated_pyramid", 4),
        ("prism", 4),
    ]

    completer = FaceTrackCompleter(data, specs)
    analysis = completer.analyze()
    assert [item["points_to_add"] for item in analysis] == [4, 6]
    assert [item["missing_tracks"] for item in analysis] == [[4], [4]]

    _, generated = completer.preview(z_method="diagonal")
    assert len(generated) == 10
    assert set(generated["face_track"].astype(int)) == {4}
    assert set(generated["part_face_track"].astype(int)) == {4}
    assert set(generated["tower_part"].astype(int)) == {1, 2}
    assert generated[["x", "y", "z"]].notna().all().all()


def test_izob_completion_keeps_section_generation_consistent():
    path = os.path.join(EXAMPLES_DIR, "Izob", "izob-ks-stavr-novoaleks-st2.jxl")
    loaded = load_survey_data(path)
    data = sort_imported_tower_points(loaded.data, expected_faces=3, multi_station=True).data

    specs = infer_completion_part_specs(data, default_faces=4)
    completer = FaceTrackCompleter(data, specs)
    merged, _ = completer.preview(z_method="diagonal")

    levels = find_section_levels(merged, height_tolerance=0.3)
    completed = add_missing_points_for_sections(merged, levels, height_tolerance=0.3)
    section_lines = get_section_lines(completed, levels, height_tolerance=0.3)

    assert len(levels) == 10
    assert len(section_lines) == len(levels)
    assert all(len(section["points"]) == 4 for section in section_lines)
    assert all(section.get("center_xy") is not None for section in section_lines)


def test_completion_dialog_builds_preview_for_single_level_case():
    full = _make_regular_track_data(z_levels=[0.0], faces=4)
    partial = full[full["face_track"] != 4].copy().reset_index(drop=True)

    dialog = BeltCompletionDialog(partial, suggested_faces=4)

    assert dialog._parts_table.rowCount() == 1
    assert dialog._analysis_table.rowCount() == 1
    assert "Будет добавлено 1" in dialog._summary_label.text()


def test_administraciya_completion_closes_largest_angular_gap():
    path = os.path.join(EXAMPLES_DIR, "Administraciya-1.job")
    loaded = load_survey_data(path)
    sorted_result = sort_imported_tower_points(loaded.data, expected_faces=3, multi_station=True)
    data = sorted_result.data

    specs = infer_completion_part_specs(data, default_faces=4)
    completer = FaceTrackCompleter(data, specs)
    _, generated = completer.preview(z_method="diagonal")

    assert len(generated) == 2
    assert set(generated["face_track"].astype(int)) == {4}

    level1_existing = data[(data["height_level"] == 1) & (data["face_track"] > 0)].copy()
    xy = level1_existing[["x", "y"]].to_numpy(dtype=float)
    from core.face_track_completion import _fit_circumscribed_circle

    center, _ = _fit_circumscribed_circle(xy)
    existing_angles = np.degrees(
        np.arctan2(level1_existing["y"].to_numpy(dtype=float) - center[1], level1_existing["x"].to_numpy(dtype=float) - center[0])
    ) % 360.0
    generated_level1 = generated[generated["height_level"] == 1].iloc[0]
    generated_angle = float(np.degrees(np.arctan2(generated_level1["y"] - center[1], generated_level1["x"] - center[0])) % 360.0)

    ordered = np.sort(existing_angles)
    gaps = np.diff(np.r_[ordered, ordered[0] + 360.0])
    largest_gap_index = int(np.argmax(gaps))
    gap_start = ordered[largest_gap_index]
    expected_mid = (gap_start + gaps[largest_gap_index] / 2.0) % 360.0

    delta = abs((generated_angle - expected_mid + 180.0) % 360.0 - 180.0)
    assert delta < 10.0


def test_preview_normalizes_existing_height_levels_after_full_import():
    loaded = load_survey_data(os.path.join(EXAMPLES_DIR, "Administraciya-1.job"))
    wizard = DataImportWizard(loaded.data, import_payload=loaded.to_context_dict())
    wizard.cached_selected_points = loaded.data.copy()
    wizard.show_step_2()
    wizard.finalize_data()
    imported = wizard.get_result().copy()
    wizard.reject()
    _APP.processEvents()

    working_before = imported.loc[build_working_tower_mask(imported)].copy()
    before_levels = pd.to_numeric(working_before["height_level"], errors="coerce").fillna(0).astype(int)
    assert (before_levels <= 0).all()

    specs = infer_completion_part_specs(imported, default_faces=4)
    completer = FaceTrackCompleter(imported, specs)
    merged, generated = completer.preview(z_method="diagonal")

    assert len(generated) == 2

    working_after = merged.loc[build_working_tower_mask(merged)].copy()
    after_levels = pd.to_numeric(working_after["height_level"], errors="coerce").fillna(0).astype(int)
    assert (after_levels > 0).all()
