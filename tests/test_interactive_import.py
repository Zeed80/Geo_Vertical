import copy
import json
import os

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal
from PyQt6.QtWidgets import QApplication, QLabel, QMessageBox

from core.import_models import ImportDiagnostics, LoadedSurveyData
from core.interactive_import import (
    apply_interactive_corrections,
    apply_section_review_selection,
    build_interactive_correction_review,
    build_section_review,
)
from gui import main_window as main_window_module
from gui.interactive_import_wizard import InteractiveImportWizard

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_APP = QApplication.instance() or QApplication([])


def _tower_row(
    name: str,
    x: float,
    y: float,
    z: float,
    belt: int,
    *,
    height_level: int | None = None,
    point_index: int | None = None,
) -> dict:
    row = {
        "name": name,
        "x": float(x),
        "y": float(y),
        "z": float(z),
        "belt": int(belt),
        "face_track": int(belt),
        "part_belt": int(belt),
        "part_face_track": int(belt),
        "tower_part": 1,
        "segment": 1,
        "tower_part_memberships": json.dumps([1], ensure_ascii=False),
        "is_part_boundary": False,
        "is_station": False,
        "is_auxiliary": False,
        "is_control": False,
        "point_index": int(point_index or 0),
    }
    if height_level is not None:
        row["height_level"] = int(height_level)
    return row


def _build_projection_candidate_data() -> pd.DataFrame:
    rows = [
        {
            "name": "ST1",
            "x": 0.0,
            "y": -50.0,
            "z": 1.7,
            "belt": None,
            "face_track": None,
            "part_belt": None,
            "part_face_track": None,
            "tower_part": 1,
            "segment": 1,
            "tower_part_memberships": json.dumps([1], ensure_ascii=False),
            "is_part_boundary": False,
            "is_station": True,
            "station_role": "primary",
            "is_auxiliary": False,
            "is_control": False,
            "point_index": 0,
        },
        _tower_row("P1", 1.0, 0.0, 0.0, 1, height_level=1, point_index=1),
        _tower_row("P2", 2.0, 0.0, 10.0, 1, height_level=2, point_index=2),
        _tower_row("P3", 3.0, 0.0, 20.0, 1, height_level=3, point_index=3),
        _tower_row("P4", 4.0, 0.12, 30.0, 1, height_level=4, point_index=4),
        _tower_row("P5", 5.0, 0.0, 40.0, 1, height_level=5, point_index=5),
    ]
    return pd.DataFrame(rows)


def _build_square_section_data() -> pd.DataFrame:
    rows = []
    point_index = 1
    corners = {
        1: (0.0, 0.0),
        2: (2.0, 0.0),
        3: (2.0, 2.0),
        4: (0.0, 2.0),
    }
    for height_level, z_value in ((1, 0.0), (2, 5.0), (3, 10.0)):
        belts = (1, 2, 3) if z_value == 5.0 else (1, 2, 3, 4)
        for belt in belts:
            x_value, y_value = corners[belt]
            rows.append(
                _tower_row(
                    f"P{point_index}",
                    x_value,
                    y_value,
                    z_value,
                    belt,
                    height_level=height_level,
                    point_index=point_index,
                )
            )
            point_index += 1
    return pd.DataFrame(rows)


@pytest.fixture
def suppress_message_boxes(monkeypatch):
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)


@pytest.fixture
def main_window(monkeypatch, suppress_message_boxes):
    monkeypatch.setattr(main_window_module.MainWindow, "_try_recover_autosave", lambda self: None)
    window = main_window_module.MainWindow()
    window.autosave_timer.stop()
    yield window
    window.autosave_timer.stop()
    window.close()
    window.deleteLater()
    _APP.processEvents()


def test_build_interactive_correction_review_projects_point_to_confirmed_track():
    data = _build_projection_candidate_data()

    review = build_interactive_correction_review(data)

    candidates = {int(candidate["row_index"]): candidate for candidate in review["candidates"]}
    candidate = candidates[4]

    assert candidate["point_name"] == "P4"
    assert candidate["correction_kind"] == "project_to_face_track"
    assert candidate["current_belt"] == 1
    assert candidate["proposed_belt"] == 1
    assert candidate["distance_moved_m"] == pytest.approx(0.120, abs=0.01)
    assert candidate["proposed_y"] == pytest.approx(0.0, abs=0.02)
    assert review["point_status_counts"]["correction_candidate"] == 1

    corrected, applied, rejected = apply_interactive_corrections(data, review["candidates"], {4})

    assert len(applied) == 1
    assert not rejected
    assert bool(corrected.at[4, "import_corrected"]) is True
    assert corrected.at[4, "import_review_status"] == "corrected"
    assert corrected.at[4, "source_y"] == pytest.approx(0.12, abs=1e-9)
    assert corrected.at[4, "y"] == pytest.approx(0.0, abs=0.02)
    assert corrected.at[4, "import_correction_kind"] == "project_to_face_track"
    assert corrected.at[4, "import_correction_distance_mm"] == pytest.approx(120.0, abs=1.0)


def test_section_review_keeps_generated_points_only_for_confirmed_sections():
    data = _build_square_section_data()

    review = build_section_review(data)

    assert [round(float(value), 3) for value in review["section_levels"]] == [0.0, 5.0, 10.0]
    assert len(review["rows"]) == 3
    assert review["rows"][0]["generated_count"] == 0
    assert review["rows"][1]["generated_count"] == 1
    assert review["rows"][2]["generated_count"] == 0

    rejected_data, rejected_sections, accepted_rejected = apply_section_review_selection(review, set())
    accepted_data, accepted_sections, accepted_confirmed = apply_section_review_selection(review, {2})

    rejected_generated = rejected_data["is_section_generated"].astype("boolean").fillna(False).astype(bool).sum()
    accepted_generated = accepted_data["is_section_generated"].astype("boolean").fillna(False).astype(bool).sum()

    assert rejected_generated == 0
    assert accepted_generated == 1
    assert len(rejected_sections) == 3
    assert len(accepted_sections) == 3
    assert len(accepted_rejected) == 2
    assert len(accepted_confirmed) == 3


def test_interactive_wizard_step2_keeps_next_enabled_and_uses_scroll_area():
    wizard = InteractiveImportWizard(_build_square_section_data())
    wizard.cached_selected_points = wizard.raw_data.copy(deep=True)

    wizard.show_step_2()

    assert wizard.current_step == 2
    assert wizard.next_btn.isEnabled() is True
    assert wizard.title_label.wordWrap() is True
    assert getattr(wizard, "steps_scroll", None) is not None

    wizard.reject()
    _APP.processEvents()


def test_interactive_wizard_go_next_from_step2_builds_step3_widgets(suppress_message_boxes):
    wizard = InteractiveImportWizard(_build_projection_candidate_data())
    wizard.cached_selected_points = wizard.raw_data.copy(deep=True)

    wizard.show_step_2()
    wizard.go_next()
    _APP.processEvents()

    assert wizard.current_step == 3
    assert hasattr(wizard, "z_snap_spin")
    assert hasattr(wizard, "correction_table")
    assert wizard.z_snap_spin.maximumWidth() == 180
    assert wizard.correction_table.minimumHeight() >= 360
    visible_labels = [label.text() for label in wizard.steps_container.findChildren(QLabel) if label.isVisible()]
    assert not any("Количество поясов" in text for text in visible_labels)
    assert not any("Точка стояния" in text for text in visible_labels)

    wizard.reject()
    _APP.processEvents()


def test_main_window_interactive_import_persists_mode_and_confirmed_sections(main_window, monkeypatch):
    base_data = _build_square_section_data()
    review = build_section_review(base_data)
    final_data, section_lines, _accepted_sections = apply_section_review_selection(review, {2})

    class _AcceptedInteractiveWizard:
        def __init__(self, *_args, **_kwargs):
            self._result = final_data.copy(deep=True)

        def exec(self):
            return main_window_module.QDialog.DialogCode.Accepted

        def get_result(self):
            return self._result.copy(deep=True)

        def get_cached_sorting_settings(self):
            return {"belt_count": 4}

        def get_import_audit(self):
            return {
                "import_mode": "interactive",
                "belt_summary": {"assigned_points": int(len(self._result))},
                "tower_part_summary": {"parts": 1},
                "standing_candidates": [],
            }

        def get_confirmed_section_data(self):
            return copy.deepcopy(section_lines)

    monkeypatch.setattr(main_window_module, "InteractiveImportWizard", _AcceptedInteractiveWizard)

    loaded = LoadedSurveyData(
        data=base_data,
        epsg_code=4326,
        diagnostics=ImportDiagnostics(source_path="interactive.csv"),
    )

    main_window._process_loaded_data(
        loaded,
        import_file_path="interactive.csv",
        old_state=main_window._capture_main_window_undo_state(),
        import_mode="interactive",
    )

    generated_mask = main_window.raw_data["is_section_generated"].astype("boolean").fillna(False).astype(bool)
    assert generated_mask.sum() == 1
    assert main_window.import_context["import_mode"] == "interactive"
    assert main_window.import_diagnostics["details"]["import_mode"] == "interactive"
    assert len(main_window.editor_3d.section_data) == len(section_lines)
    assert main_window.current_file_path == "interactive.csv"

    expected_original = final_data.loc[~generated_mask].reset_index(drop=True)
    assert_frame_equal(
        main_window.original_data_before_sections.reset_index(drop=True),
        expected_original,
        check_dtype=False,
    )
