import json
import os

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal
from PyQt6.QtWidgets import QApplication, QMessageBox

from core.section_operations import get_section_lines
from core.services.project_manager import ProjectManager
from gui import main_window as main_window_module

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_APP = QApplication.instance() or QApplication([])


def _build_square_tower(
    *,
    levels=(0.0, 10.0),
    include_parts: bool = True,
) -> pd.DataFrame:
    rows = []
    point_index = 1
    corners = ((0.0, 0.0), (2.0, 0.0), (2.0, 2.0), (0.0, 2.0))
    for level in levels:
        for belt, (x, y) in enumerate(corners, start=1):
            row = {
                "name": f"P{point_index}",
                "x": x,
                "y": y,
                "z": float(level),
                "belt": belt,
                "point_index": point_index,
                "is_station": False,
            }
            if include_parts:
                row.update(
                    {
                        "tower_part": 1,
                        "segment": 1,
                        "tower_part_memberships": json.dumps([1], ensure_ascii=False),
                        "is_part_boundary": False,
                    }
                )
            rows.append(row)
            point_index += 1
    return pd.DataFrame(rows)


def _normalize_section_data(section_data):
    normalized = []
    for section in section_data or []:
        normalized.append(
            {
                "height": round(float(section.get("height", 0.0)), 6),
                "belt_nums": [int(b) for b in section.get("belt_nums", [])],
                "points": [
                    tuple(round(float(coord), 6) for coord in point)
                    for point in section.get("points", [])
                ],
                "tower_part": section.get("tower_part"),
                "segment": section.get("segment"),
                "section_num": section.get("section_num"),
                "section_name": section.get("section_name"),
            }
        )
    return sorted(normalized, key=lambda item: item["height"])


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


def _load_into_main_window(window, data: pd.DataFrame) -> None:
    window.raw_data = data.copy(deep=True)
    window.editor_3d.set_data(window.raw_data)
    window.data_table.set_data(window.raw_data)


def test_main_window_create_and_remove_sections_roundtrip(main_window):
    base_data = _build_square_tower()
    _load_into_main_window(main_window, base_data)

    main_window.create_sections()
    assert [round(section["height"], 3) for section in main_window.editor_3d.section_data] == [0.0, 10.0]

    main_window.remove_sections()

    assert not main_window.editor_3d.section_data
    assert_frame_equal(
        main_window.raw_data.reset_index(drop=True),
        base_data.reset_index(drop=True),
        check_dtype=False,
    )


def test_undo_create_sections_should_clear_section_data(main_window):
    _load_into_main_window(main_window, _build_square_tower())

    main_window.create_sections()
    assert main_window.editor_3d.section_data

    main_window.undo()

    assert not main_window.editor_3d.section_data


def test_redo_create_sections_should_restore_section_data(main_window):
    _load_into_main_window(main_window, _build_square_tower())

    main_window.create_sections()
    main_window.undo()

    main_window.redo()

    assert [round(section["height"], 3) for section in main_window.editor_3d.section_data] == [0.0, 10.0]


def test_remove_sections_should_preserve_post_creation_point_edits(main_window):
    _load_into_main_window(main_window, _build_square_tower())

    main_window.create_sections()
    main_window.editor_3d.data.at[0, "x"] = 99.0
    main_window.on_3d_data_changed()

    main_window.remove_sections()

    assert main_window.raw_data.at[0, "x"] == 99.0
    assert not main_window.editor_3d.section_data


def test_remove_sections_undo_redo_should_restore_section_state(main_window):
    _load_into_main_window(main_window, _build_square_tower())

    main_window.create_sections()
    main_window.editor_3d.data.at[0, "x"] = 99.0
    main_window.on_3d_data_changed()

    main_window.remove_sections()
    main_window.undo()

    assert main_window.raw_data.at[0, "x"] == 99.0
    assert [round(section["height"], 3) for section in main_window.editor_3d.section_data] == [0.0, 10.0]

    main_window.redo()

    assert main_window.raw_data.at[0, "x"] == 99.0
    assert not main_window.editor_3d.section_data


def test_on_table_data_changed_should_rebuild_section_data(main_window):
    _load_into_main_window(main_window, _build_square_tower())
    main_window.create_sections()

    updated = main_window.data_table.original_data.copy(deep=True)
    updated.loc[updated["z"] == 10.0, "z"] = 20.0
    main_window.data_table.original_data = updated

    main_window.on_table_data_changed()

    assert [round(section["height"], 3) for section in main_window.editor_3d.section_data] == [0.0, 20.0]


def test_on_3d_data_changed_should_rebuild_section_data(main_window):
    _load_into_main_window(main_window, _build_square_tower())
    main_window.create_sections()

    top_indices = main_window.editor_3d.data.index[main_window.editor_3d.data["z"] == 10.0]
    main_window.editor_3d.data.loc[top_indices, "z"] = 20.0

    main_window.on_3d_data_changed()

    assert [round(section["height"], 3) for section in main_window.editor_3d.section_data] == [0.0, 20.0]


def test_project_manager_roundtrip_preserves_section_data_and_snapshot(tmp_path):
    raw_data = _build_square_tower(levels=(0.0, 10.0, 20.0))
    original_before_sections = raw_data.iloc[:8].copy(deep=True)
    section_data = get_section_lines(raw_data, [0.0, 10.0, 20.0], height_tolerance=0.3)

    project_path = tmp_path / "section_audit_roundtrip.gvproj"
    manager = ProjectManager()
    manager.save_project(
        str(project_path),
        raw_data=raw_data,
        processed_data={"valid": True},
        epsg_code=4326,
        current_file_path="sample.csv",
        original_data_before_sections=original_before_sections,
        height_tolerance=0.3,
        center_method="mean",
        expected_belt_count=4,
        tower_faces_count=4,
        section_data=section_data,
    )

    loaded = manager.load_project(str(project_path))

    assert_frame_equal(
        loaded["raw_data"].reset_index(drop=True),
        raw_data.reset_index(drop=True),
        check_dtype=False,
    )
    assert_frame_equal(
        loaded["original_data_before_sections"].reset_index(drop=True),
        original_before_sections.reset_index(drop=True),
        check_dtype=False,
    )
    assert _normalize_section_data(loaded["section_data"]) == _normalize_section_data(section_data)


def test_project_manager_autosave_preserves_section_data(tmp_path):
    raw_data = _build_square_tower(levels=(0.0, 10.0, 20.0))
    section_data = get_section_lines(raw_data, [0.0, 10.0, 20.0], height_tolerance=0.3)

    manager = ProjectManager()
    manager.AUTOSAVE_DIR = str(tmp_path)
    autosave_path = manager.save_autosave(
        raw_data=raw_data,
        processed_data={"valid": True},
        epsg_code=4326,
        current_file_path="sample.csv",
        original_data_before_sections=raw_data.copy(deep=True),
        height_tolerance=0.3,
        center_method="mean",
        expected_belt_count=4,
        tower_faces_count=4,
        section_data=section_data,
    )

    assert autosave_path is not None

    loaded = manager.load_project(autosave_path)

    assert_frame_equal(
        loaded["raw_data"].reset_index(drop=True),
        raw_data.reset_index(drop=True),
        check_dtype=False,
    )
    assert _normalize_section_data(loaded["section_data"]) == _normalize_section_data(section_data)
