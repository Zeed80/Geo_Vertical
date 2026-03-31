import json
import os

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal
from PyQt6.QtWidgets import QApplication, QMessageBox

from core.face_track_completion import CompletionPartSpec, FaceTrackCompleter
from core.calculations import process_tower_data
from core.data_loader import load_survey_data
from core.import_models import ImportDiagnostics, LoadedSurveyData
from core.point_utils import build_working_tower_mask
from core.section_operations import get_section_lines
from core.sorting_pipeline import sort_imported_tower_points
from core.services.project_manager import ProjectManager
from gui import main_window as main_window_module
from gui.data_import_wizard import DataImportWizard

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


def _finalize_imported_example(relative_path: str) -> pd.DataFrame:
    loaded = load_survey_data(os.path.join(os.path.dirname(__file__), "..", "examples", relative_path))
    wizard = DataImportWizard(loaded.data, import_payload=loaded.to_context_dict())
    wizard.cached_selected_points = loaded.data.copy()
    wizard.show_step_2()
    wizard.finalize_data()
    result = wizard.get_result().copy()
    wizard.reject()
    _APP.processEvents()
    return result


def _append_synthetic_second_station(data: pd.DataFrame) -> pd.DataFrame:
    stations = data.loc[data["is_station"]].copy()
    tower_points = data.loc[build_working_tower_mask(data)].copy()
    station_row = stations.iloc[0]
    center_x = float(tower_points["x"].mean())
    center_y = float(tower_points["y"].mean())
    base_dx = float(station_row["x"]) - center_x
    base_dy = float(station_row["y"]) - center_y
    base_distance = max((base_dx ** 2 + base_dy ** 2) ** 0.5, 1e-9)
    orth_x = base_dy / base_distance
    orth_y = -base_dx / base_distance
    point_index = int(pd.to_numeric(data["point_index"], errors="coerce").max()) + 1 if "point_index" in data.columns else len(data) + 1

    second_station = pd.DataFrame(
        [
            {
                "name": "ST2",
                "x": center_x + orth_x * base_distance,
                "y": center_y + orth_y * base_distance,
                "z": float(station_row["z"]),
                "is_station": True,
                "station_role": "secondary",
                "station_origin": "synthetic",
                "belt": None,
                "point_index": point_index,
            }
        ]
    )
    return pd.concat([data, second_station], ignore_index=True)


def _build_partial_square_tracks() -> pd.DataFrame:
    rows = []
    point_index = 1
    levels = [(1, 0.0), (2, 10.0)]
    corners = {
        1: (0.0, 0.0),
        2: (2.0, 0.0),
        3: (2.0, 2.0),
    }
    for height_level, z_value in levels:
        for track_num, (x_value, y_value) in corners.items():
            rows.append(
                {
                    "name": f"P{point_index}",
                    "x": x_value,
                    "y": y_value,
                    "z": z_value,
                    "belt": track_num,
                    "face_track": track_num,
                    "part_belt": track_num,
                    "part_face_track": track_num,
                    "faces": 4,
                    "height_level": height_level,
                    "point_index": point_index,
                    "is_station": False,
                    "is_auxiliary": False,
                    "is_control": False,
                    "tower_part": 1,
                    "tower_part_memberships": json.dumps([1], ensure_ascii=False),
                    "is_part_boundary": False,
                }
            )
            point_index += 1
    return pd.DataFrame(rows)


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


def test_build_missing_belt_rebuilds_sections_even_when_none_existed(main_window, monkeypatch):
    partial = _build_partial_square_tracks()
    _load_into_main_window(main_window, partial)
    main_window.tower_faces_count = 4
    main_window.expected_belt_count = 4

    completer = FaceTrackCompleter(
        partial,
        [CompletionPartSpec(part_number=1, z_min=-1.0, z_max=20.0, shape="prism", faces=4)],
    )

    class _AcceptedDialog:
        def __init__(self, *_args, **_kwargs):
            self.completer = completer
            self.z_method = "diagonal"

        def exec(self):
            return main_window_module.QDialog.DialogCode.Accepted

    monkeypatch.setattr("gui.belt_completion_dialog.BeltCompletionDialog", _AcceptedDialog)

    main_window.on_build_missing_belt()

    assert len(main_window.editor_3d.section_data) == 2
    assert [round(section["height"], 3) for section in main_window.editor_3d.section_data] == [0.0, 10.0]


def test_administraciya_build_missing_belt_keeps_sections_and_axis_centered(main_window, monkeypatch):
    administraciya_path = os.path.join(os.path.dirname(__file__), "..", "examples", "Administraciya-1.job")
    loaded = load_survey_data(administraciya_path)
    data = sort_imported_tower_points(loaded.data, expected_faces=3, multi_station=True).data.copy()
    _load_into_main_window(main_window, data)
    main_window.tower_faces_count = 4
    main_window.expected_belt_count = 4

    original_exec = main_window_module.QDialog.exec

    def _accept_completion_dialog(self):
        if self.__class__.__name__ == "BeltCompletionDialog":
            self._on_accept()
            return main_window_module.QDialog.DialogCode.Accepted
        return original_exec(self)

    monkeypatch.setattr(main_window_module.QDialog, "exec", _accept_completion_dialog)

    main_window.on_build_missing_belt()
    main_window.create_sections()

    assert len(main_window.editor_3d.section_data) == 2
    generated_track = (
        main_window.raw_data[
            (main_window.raw_data["generated_by"] == "face_track_completion")
            & (main_window.raw_data["face_track"] == 4)
        ][["x", "y", "z"]]
        .sort_values("z")
        .reset_index(drop=True)
    )
    section_heights = [round(float(section["height"]), 3) for section in main_window.editor_3d.section_data]
    assert section_heights == [2.187, 11.779]

    for section, (_, generated_row) in zip(main_window.editor_3d.section_data, generated_track.iterrows()):
        center_xy = section.get("center_xy")
        assert center_xy is not None
        distance = ((float(center_xy[0]) - float(generated_row["x"])) ** 2 + (float(center_xy[1]) - float(generated_row["y"])) ** 2) ** 0.5
        assert distance > 0.3


def test_administraciya_build_missing_belt_keeps_payload_sections_without_processed_results(main_window, monkeypatch):
    administraciya_path = os.path.join(os.path.dirname(__file__), "..", "examples", "Administraciya-1.job")
    loaded = load_survey_data(administraciya_path)
    data = sort_imported_tower_points(loaded.data, expected_faces=3, multi_station=True).data.copy()
    _load_into_main_window(main_window, data)
    main_window.tower_faces_count = 4
    main_window.expected_belt_count = 4

    original_exec = main_window_module.QDialog.exec

    def _accept_completion_dialog(self):
        if self.__class__.__name__ == "BeltCompletionDialog":
            self._on_accept()
            return main_window_module.QDialog.DialogCode.Accepted
        return original_exec(self)

    monkeypatch.setattr(main_window_module.QDialog, "exec", _accept_completion_dialog)

    main_window.on_build_missing_belt()

    payload = main_window.data_table.get_angular_measurements()

    assert main_window.processed_data is None
    assert payload["x"]
    assert payload["basis"]["has_required_stations"] is False
    assert [round(float(section["height"]), 3) for section in payload["sections"]] == [2.187, 11.779]
    assert {section["source"] for section in payload["sections"]} == {"sections"}


def test_administraciya_full_import_build_missing_belt_restores_sections_and_station_axes(main_window, monkeypatch):
    data = _finalize_imported_example("Administraciya-1.job")
    _load_into_main_window(main_window, data)
    main_window.tower_faces_count = 4
    main_window.expected_belt_count = 4

    original_exec = main_window_module.QDialog.exec

    def _accept_completion_dialog(self):
        if self.__class__.__name__ == "BeltCompletionDialog":
            self._on_accept()
            return main_window_module.QDialog.DialogCode.Accepted
        return original_exec(self)

    monkeypatch.setattr(main_window_module.QDialog, "exec", _accept_completion_dialog)

    main_window.on_build_missing_belt()

    working = main_window.raw_data.loc[build_working_tower_mask(main_window.raw_data)].copy()
    height_levels = pd.to_numeric(working["height_level"], errors="coerce").fillna(0).astype(int)
    assert (height_levels > 0).all()

    main_window.create_sections()

    assert len(main_window.editor_3d.section_data) == 2
    assert all(len(section["points"]) >= 4 for section in main_window.editor_3d.section_data)

    main_window.raw_data = _append_synthetic_second_station(main_window.raw_data)
    main_window.editor_3d.set_data(main_window.raw_data)
    main_window.data_table.set_data(main_window.raw_data)

    payload = main_window.data_table.get_angular_measurements()

    assert payload["basis"]["has_required_stations"] is True
    assert payload["basis"]["has_authoritative_stations"] is False
    assert payload["x"]
    assert payload["y"]


def test_administraciya_add_middle_section_after_build_missing_belt_keeps_payload_and_centers(main_window, monkeypatch):
    data = _finalize_imported_example("Administraciya-1.job")
    _load_into_main_window(main_window, data)
    main_window.tower_faces_count = 4
    main_window.expected_belt_count = 4

    original_exec = main_window_module.QDialog.exec

    def _accept_completion_dialog(self):
        if self.__class__.__name__ == "BeltCompletionDialog":
            self._on_accept()
            return main_window_module.QDialog.DialogCode.Accepted
        return original_exec(self)

    monkeypatch.setattr(main_window_module.QDialog, "exec", _accept_completion_dialog)

    main_window.on_build_missing_belt()
    main_window.create_sections()

    base_heights = [float(section["height"]) for section in main_window.editor_3d.section_data]
    middle_height = float(sum(base_heights) / len(base_heights))

    main_window.editor_3d.add_section(middle_height, tower_part=1, placement="absolute")
    main_window.raw_data = main_window.editor_3d.get_data()
    main_window.data_table.set_data(main_window.raw_data)

    inserted_rows = main_window.raw_data.loc[main_window.raw_data["z"].sub(middle_height).abs() <= 1e-6].copy()
    raw_results = process_tower_data(
        main_window.raw_data,
        main_window.height_tolerance,
        main_window.center_method,
        section_grouping_mode="height_levels",
        use_cache=False,
    )
    current_data = main_window.data_table.get_data()
    payload = main_window.data_table.get_angular_measurements()
    results = main_window.calculation_service.calculate(
        main_window.raw_data,
        current_data,
        main_window.epsg_code,
        main_window.height_tolerance,
        main_window.center_method,
    )

    assert len(main_window.editor_3d.section_data) == 3
    assert len(inserted_rows) == 4
    assert set(inserted_rows["generated_by"]) == {"section_generation"}
    assert set(inserted_rows["is_generated"].astype(bool)) == {True}
    assert [round(float(section["height"]), 3) for section in main_window.editor_3d.section_data] == pytest.approx(
        [round(base_heights[0], 3), round(middle_height, 3), round(base_heights[1], 3)],
        abs=1e-3,
    )
    assert [round(float(section["height"]), 3) for section in payload["sections"]] == pytest.approx(
        [round(base_heights[0], 3), round(middle_height, 3), round(base_heights[1], 3)],
        abs=1e-3,
    )
    assert len(results["centers"]) == 3
    assert results["centers"]["points_count"].tolist() == [4, 4, 4]
    assert_frame_equal(
        raw_results["centers"][
            ["x", "y", "z", "deviation_x", "deviation_y", "deviation", "points_count"]
        ].reset_index(drop=True),
        results["centers"][
            ["x", "y", "z", "deviation_x", "deviation_y", "deviation", "points_count"]
        ].reset_index(drop=True),
        check_exact=False,
        atol=5e-4,
        rtol=0.0,
    )


def test_second_station_import_rebuilds_sections_via_main_window_state_command(main_window, monkeypatch):
    _load_into_main_window(main_window, _build_square_tower())
    main_window.expected_belt_count = 4
    main_window.create_sections()

    merged_data = _build_square_tower(levels=(0.0, 12.0))
    visualization_data = {
        "line1": {"start": [0.0, 0.0, 0.0], "end": [1.0, 0.0, 0.0]},
        "line2": {"start": [0.0, 0.0, 0.0], "end": [0.0, 1.0, 0.0]},
        "angle_deg": 90.0,
    }

    class _AcceptedSecondStationWizard:
        def __init__(self, *_args, **_kwargs):
            pass

        def exec(self):
            return main_window_module.QDialog.DialogCode.Accepted

        def get_result_data(self):
            return merged_data.copy(deep=True)

        def get_visualization_data(self):
            return dict(visualization_data)

        def get_second_station_import_context(self):
            return {"source": "fake_second_station"}

        def get_second_station_import_diagnostics(self):
            return {"accepted_points": len(merged_data)}

        def get_transformation_audit(self):
            return {
                "method": 2,
                "transformation_quality": {
                    "visualization_data": dict(visualization_data),
                },
            }

    monkeypatch.setattr(main_window_module, "SecondStationImportWizard", _AcceptedSecondStationWizard)

    main_window.import_second_station()

    assert [round(float(section["height"]), 3) for section in main_window.editor_3d.section_data] == [0.0, 12.0]
    assert main_window.processed_data is None
    assert main_window.import_context["second_station_import"]["source"] == "fake_second_station"
    assert main_window.line_angle_spin.value() == pytest.approx(90.0, abs=1e-6)

    main_window.undo()
    assert [round(float(section["height"]), 3) for section in main_window.editor_3d.section_data] == [0.0, 10.0]

    main_window.redo()
    assert [round(float(section["height"]), 3) for section in main_window.editor_3d.section_data] == [0.0, 12.0]


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


def test_load_project_restores_create_sections_undo_history(main_window, tmp_path):
    base_data = _build_square_tower()
    _load_into_main_window(main_window, base_data)

    main_window.create_sections()

    project_path = tmp_path / "create_sections_history.gvproj"
    main_window._save_project_to_file(str(project_path))
    main_window._load_project_from_file(str(project_path))

    assert main_window.undo_manager.can_undo()

    main_window.undo()

    assert not main_window.editor_3d.section_data
    assert_frame_equal(
        main_window.raw_data.reset_index(drop=True),
        base_data.reset_index(drop=True),
        check_dtype=False,
    )


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


def test_load_project_restores_remove_sections_undo_history(main_window, tmp_path):
    _load_into_main_window(main_window, _build_square_tower())

    main_window.create_sections()
    main_window.remove_sections()

    project_path = tmp_path / "remove_sections_history.gvproj"
    main_window._save_project_to_file(str(project_path))
    main_window._load_project_from_file(str(project_path))

    assert main_window.undo_manager.can_undo()
    assert not main_window.editor_3d.section_data

    main_window.undo()

    assert [round(section["height"], 3) for section in main_window.editor_3d.section_data] == [0.0, 10.0]


def test_cancelled_import_keeps_existing_project_state(main_window, monkeypatch):
    base_data = _build_square_tower()
    _load_into_main_window(main_window, base_data)
    main_window.current_file_path = "existing.csv"
    main_window.import_context = {"source": "existing"}
    main_window.import_diagnostics = {"status": "existing"}
    main_window.transformation_audit = {"quality": "existing"}

    previous_state = main_window._capture_main_window_undo_state()

    class _RejectedWizard:
        def __init__(self, *args, **kwargs):
            pass

        def exec(self):
            return main_window_module.QDialog.DialogCode.Rejected

    monkeypatch.setattr(main_window_module, "DataImportWizard", _RejectedWizard)

    loaded = LoadedSurveyData(
        data=_build_square_tower(levels=(0.0, 5.0)),
        epsg_code=4326,
        diagnostics=ImportDiagnostics(source_path="new.csv"),
    )

    main_window._process_loaded_data(
        loaded,
        import_file_path="new.csv",
        old_state=previous_state,
    )

    assert main_window.current_file_path == "existing.csv"
    assert main_window.import_context == {"source": "existing"}
    assert main_window.import_diagnostics == {"status": "existing"}
    assert main_window.transformation_audit == {"quality": "existing"}
    assert_frame_equal(
        main_window.raw_data.reset_index(drop=True),
        base_data.reset_index(drop=True),
        check_dtype=False,
    )


def test_import_undo_history_survives_save_load(main_window, monkeypatch, tmp_path):
    base_data = _build_square_tower(levels=(0.0, 5.0))
    _load_into_main_window(main_window, base_data)
    main_window.current_file_path = "existing.csv"

    class _AcceptedWizard:
        def __init__(self, data, *args, **kwargs):
            self._result = data.copy(deep=True)

        def exec(self):
            return main_window_module.QDialog.DialogCode.Accepted

        def get_result(self):
            return self._result.copy(deep=True)

        def get_cached_sorting_settings(self):
            return {"belt_count": 4}

        def get_import_audit(self):
            return {
                "belt_summary": {"assigned_points": len(self._result)},
                "tower_part_summary": {},
                "standing_candidates": [],
            }

    monkeypatch.setattr(main_window_module, "DataImportWizard", _AcceptedWizard)

    imported_data = _build_square_tower(levels=(0.0, 10.0, 20.0))
    loaded = LoadedSurveyData(
        data=imported_data,
        epsg_code=4326,
        diagnostics=ImportDiagnostics(source_path="import.csv"),
    )

    main_window._process_loaded_data(
        loaded,
        import_file_path="import.csv",
        old_state=main_window._capture_main_window_undo_state(),
    )

    assert_frame_equal(
        main_window.raw_data.reset_index(drop=True),
        imported_data.reset_index(drop=True),
        check_dtype=False,
    )
    assert main_window.current_file_path == "import.csv"

    project_path = tmp_path / "import_undo_history.gvproj"
    main_window._save_project_to_file(str(project_path))
    main_window._load_project_from_file(str(project_path))

    assert_frame_equal(
        main_window.raw_data.reset_index(drop=True),
        imported_data.reset_index(drop=True),
        check_dtype=False,
    )
    assert main_window.current_file_path == "import.csv"
    assert main_window.undo_manager.can_undo()

    main_window.undo()

    assert_frame_equal(
        main_window.raw_data.reset_index(drop=True),
        base_data.reset_index(drop=True),
        check_dtype=False,
    )
    assert main_window.current_file_path == "existing.csv"


def test_editor_undo_buttons_delegate_to_global_undo_manager(main_window):
    _load_into_main_window(main_window, _build_square_tower())

    main_window.create_sections()
    main_window.editor_3d.delete_section(10.0)

    assert [round(section["height"], 3) for section in main_window.editor_3d.section_data] == [0.0]
    assert main_window.undo_manager.can_undo()

    main_window.editor_3d.undo_action()

    assert [round(section["height"], 3) for section in main_window.editor_3d.section_data] == [0.0, 10.0]

    main_window.editor_3d.redo_action()

    assert [round(section["height"], 3) for section in main_window.editor_3d.section_data] == [0.0]


def test_on_table_data_changed_should_rebuild_section_data(main_window):
    _load_into_main_window(main_window, _build_square_tower())
    main_window.create_sections()

    updated = main_window.data_table.original_data.copy(deep=True)
    updated.loc[updated["z"] == 10.0, "z"] = 20.0
    main_window.data_table.original_data = updated

    main_window.on_table_data_changed()

    assert [round(section["height"], 3) for section in main_window.editor_3d.section_data] == [0.0, 20.0]
    assert_frame_equal(
        main_window.original_data_before_sections.reset_index(drop=True),
        updated.reset_index(drop=True),
        check_dtype=False,
    )


def test_table_mutation_undo_history_survives_save_load(main_window, tmp_path):
    base_data = _build_square_tower()
    _load_into_main_window(main_window, base_data)
    main_window.create_sections()

    old_data = main_window.data_table.original_data.copy(deep=True)
    new_data = old_data.copy(deep=True)
    new_data.loc[new_data["z"] == 10.0, "z"] = 20.0
    main_window.data_table.original_data = new_data.copy(deep=True)

    main_window.data_table.data_mutated.emit(old_data, new_data, "Редактирование точки башни")
    main_window.data_table.data_changed.emit()

    assert [round(section["height"], 3) for section in main_window.editor_3d.section_data] == [0.0, 20.0]
    assert_frame_equal(
        main_window.original_data_before_sections.reset_index(drop=True),
        new_data.reset_index(drop=True),
        check_dtype=False,
    )
    expected_current_snapshot = main_window.original_data_before_sections.copy(deep=True)
    assert len(main_window.undo_manager.undo_stack) == 2

    project_path = tmp_path / "table_mutation_undo_history.gvproj"
    main_window._save_project_to_file(str(project_path))

    loaded = ProjectManager().load_project(str(project_path))
    assert_frame_equal(
        loaded["original_data_before_sections"].reset_index(drop=True),
        expected_current_snapshot.reset_index(drop=True),
        check_dtype=False,
    )

    main_window._load_project_from_file(str(project_path))
    assert [round(section["height"], 3) for section in main_window.editor_3d.section_data] == [0.0, 20.0]

    main_window.undo()

    assert [round(section["height"], 3) for section in main_window.editor_3d.section_data] == [0.0, 10.0]
    assert_frame_equal(
        main_window.original_data_before_sections.reset_index(drop=True),
        old_data.reset_index(drop=True),
        check_dtype=False,
    )

    main_window.undo()

    assert not main_window.editor_3d.section_data


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


def test_save_project_normalizes_stale_section_data_before_persistence(main_window, tmp_path):
    raw_data = _build_square_tower(levels=(0.0, 10.0))
    _load_into_main_window(main_window, raw_data)
    main_window.editor_3d.section_data = [
        {"height": 0.0, "points": [(99.0, 99.0, 0.0)], "belt_nums": [1]},
        {"height": 10.0, "points": [(99.0, 99.0, 10.0)], "belt_nums": [1]},
    ]

    project_path = tmp_path / "normalized_save.gvproj"
    main_window._save_project_to_file(str(project_path))

    loaded = ProjectManager().load_project(str(project_path))
    expected = get_section_lines(raw_data, [0.0, 10.0], height_tolerance=0.3)

    assert _normalize_section_data(loaded["section_data"]) == _normalize_section_data(expected)


def test_load_project_rebuilds_stale_section_data_from_raw_data(main_window, tmp_path):
    raw_data = _build_square_tower(levels=(0.0, 10.0))
    stale_section_data = [
        {"height": 0.0, "points": [(77.0, 77.0, 0.0)], "belt_nums": [1]},
        {"height": 10.0, "points": [(88.0, 88.0, 10.0)], "belt_nums": [1]},
    ]

    project_path = tmp_path / "normalized_load.gvproj"
    manager = ProjectManager()
    manager.save_project(
        str(project_path),
        raw_data=raw_data,
        processed_data=None,
        epsg_code=None,
        current_file_path="sample.csv",
        original_data_before_sections=None,
        height_tolerance=0.3,
        center_method="mean",
        expected_belt_count=4,
        tower_faces_count=4,
        section_data=stale_section_data,
    )

    main_window._load_project_from_file(str(project_path))
    expected = get_section_lines(raw_data, [0.0, 10.0], height_tolerance=0.3)

    assert _normalize_section_data(main_window.editor_3d.section_data) == _normalize_section_data(expected)
    assert main_window.data_table.sections_table.rowCount() == len(expected)


def test_load_project_without_sections_keeps_section_state_empty(main_window, tmp_path):
    raw_data = _build_square_tower(levels=(0.0, 10.0))

    project_path = tmp_path / "no_sections.gvproj"
    manager = ProjectManager()
    manager.save_project(
        str(project_path),
        raw_data=raw_data,
        processed_data=None,
        epsg_code=None,
        current_file_path="sample.csv",
        original_data_before_sections=None,
        height_tolerance=0.3,
        center_method="mean",
        expected_belt_count=4,
        tower_faces_count=4,
        section_data=[],
    )

    main_window._load_project_from_file(str(project_path))

    assert main_window.editor_3d.section_data == []
    assert main_window.data_table.sections_table.rowCount() == 0


def test_load_project_without_sections_reenables_create_sections_button(main_window, tmp_path):
    raw_data = _build_square_tower(levels=(0.0, 10.0))

    project_path = tmp_path / "no_sections_button_state.gvproj"
    manager = ProjectManager()
    manager.save_project(
        str(project_path),
        raw_data=raw_data,
        processed_data=None,
        epsg_code=None,
        current_file_path="sample.csv",
        original_data_before_sections=None,
        height_tolerance=0.3,
        center_method="mean",
        expected_belt_count=4,
        tower_faces_count=4,
        section_data=[],
    )

    main_window._load_project_from_file(str(project_path))

    assert main_window.editor_3d.section_data == []
    assert main_window.editor_3d.create_sections_btn.isEnabled() is True
    assert main_window.editor_3d.create_sections_action is main_window.editor_3d.create_sections_btn


def test_load_project_dialog_path_rebuilds_stale_section_data_from_raw_data(main_window, tmp_path, monkeypatch):
    raw_data = _build_square_tower(levels=(0.0, 10.0))
    stale_section_data = [
        {"height": 0.0, "points": [(11.0, 11.0, 0.0)], "belt_nums": [1]},
        {"height": 10.0, "points": [(22.0, 22.0, 10.0)], "belt_nums": [1]},
    ]

    project_path = tmp_path / "dialog_load.gvproj"
    manager = ProjectManager()
    manager.save_project(
        str(project_path),
        raw_data=raw_data,
        processed_data=None,
        epsg_code=None,
        current_file_path="sample.csv",
        original_data_before_sections=None,
        height_tolerance=0.3,
        center_method="mean",
        expected_belt_count=4,
        tower_faces_count=4,
        section_data=stale_section_data,
    )

    monkeypatch.setattr(
        main_window_module.QFileDialog,
        "getOpenFileName",
        lambda *args, **kwargs: (str(project_path), "GeoVertical (*.gvproj)"),
    )

    main_window.load_project()
    expected = get_section_lines(raw_data, [0.0, 10.0], height_tolerance=0.3)

    assert _normalize_section_data(main_window.editor_3d.section_data) == _normalize_section_data(expected)
    assert main_window.data_table.sections_table.rowCount() == len(expected)


def test_load_project_restores_editor_state_undo_history(main_window, tmp_path):
    _load_into_main_window(main_window, _build_square_tower())

    main_window.create_sections()
    main_window.editor_3d.delete_section(10.0)

    project_path = tmp_path / "editor_state_undo_history.gvproj"
    main_window._save_project_to_file(str(project_path))
    main_window._load_project_from_file(str(project_path))

    assert [round(section["height"], 3) for section in main_window.editor_3d.section_data] == [0.0]
    assert main_window.undo_manager.can_undo()

    main_window.undo()

    assert [round(section["height"], 3) for section in main_window.editor_3d.section_data] == [0.0, 10.0]
