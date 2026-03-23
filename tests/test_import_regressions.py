import json
from pathlib import Path

import pandas as pd
import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QMessageBox, QInputDialog, QWidget

from core.data_loader import load_survey_data
from core.import_grouping import estimate_composite_split_height, group_points_by_global_angle
from core.import_models import LoadedSurveyData
from core.multi_station_import import auto_merge_multi_station_tower
from core.point_utils import build_working_tower_mask
from core.second_station_matching import build_method1_preview, find_best_method2_preview
from core.section_operations import (
    add_missing_points_for_sections,
    find_section_levels,
    get_section_lines,
)
from core.services.calculation_service import CalculationService
from core.services.project_manager import ProjectManager
from core.services.report_templates import ReportDataAssembler, ReportTemplateManager, build_report_data_from_template
from core.tower_generator import create_blueprint_from_imported_data
from gui.data_import_wizard import DataImportWizard
from gui.straightness_widget import StraightnessWidget
from gui.second_station_import_wizard import SecondStationImportWizard
from tests.test_full_report_pipeline import _sample_report_data

EXAMPLES_DIR = Path(__file__).resolve().parents[1] / "examples"


def _prepare_razvilnoe_station_pair() -> tuple[pd.DataFrame, pd.DataFrame]:
    first = load_survey_data(str(EXAMPLES_DIR / "Priv-PRS_Razvilnoe-1.job")).data.copy()
    second = load_survey_data(str(EXAMPLES_DIR / "Priv-PRS_Razvilnoe-2.job")).data.copy()

    for data in (first, second):
        data["is_station"] = data["name"].astype(str).str.lower().str.startswith("st")
        tower_indices = data.index[~data["is_station"]].tolist()
        grouped = group_points_by_global_angle(data, tower_indices, 4)
        for belt_num, group in enumerate(grouped, start=1):
            data.loc[group, "belt"] = belt_num
        data.loc[~data["is_station"], "faces"] = 4

    return first, second


def _prepare_simple_single_station_data() -> pd.DataFrame:
    data = pd.DataFrame(
        [
            {"name": "E0", "x": 2.0, "y": 0.0, "z": 0.0},
            {"name": "N0", "x": 0.0, "y": 2.0, "z": 0.0},
            {"name": "W0", "x": -2.0, "y": 0.0, "z": 0.0},
            {"name": "S0", "x": 0.0, "y": -2.0, "z": 0.0},
            {"name": "E5", "x": 2.0, "y": 0.0, "z": 5.0},
            {"name": "N5", "x": 0.0, "y": 2.0, "z": 5.0},
            {"name": "W5", "x": -2.0, "y": 0.0, "z": 5.0},
            {"name": "S5", "x": 0.0, "y": -2.0, "z": 5.0},
            {"name": "E10", "x": 2.0, "y": 0.0, "z": 10.0},
            {"name": "N10", "x": 0.0, "y": 2.0, "z": 10.0},
            {"name": "W10", "x": -2.0, "y": 0.0, "z": 10.0},
            {"name": "S10", "x": 0.0, "y": -2.0, "z": 10.0},
            {"name": "st1", "x": -15.0, "y": 0.0, "z": 1.7},
        ]
    )
    data["is_station"] = data["name"].eq("st1")
    return data


def _finalize_import_for_calculations(relative_path: str) -> pd.DataFrame:
    app = QApplication.instance() or QApplication([])
    loaded = load_survey_data(str(EXAMPLES_DIR / relative_path))
    wizard = DataImportWizard(loaded.data, import_payload=loaded.to_context_dict())
    wizard.cached_selected_points = loaded.data.copy()
    wizard.show_step_2()
    wizard.finalize_data()
    result = wizard.get_result().copy()
    wizard.reject()
    app.processEvents()
    return result


def test_loaded_survey_data_context_roundtrip():
    loaded = load_survey_data(str(EXAMPLES_DIR / "test_tower_data.csv"))
    restored = LoadedSurveyData.from_context_dict(loaded.data, loaded.to_context_dict())

    assert restored.source_format == loaded.source_format
    assert restored.parser_strategy == loaded.parser_strategy
    assert restored.diagnostics.accepted_points == len(loaded.data)


def test_trimble_job_reports_paired_export_diagnostics():
    loaded_job = load_survey_data(str(EXAMPLES_DIR / "PRS-6.job"))
    loaded_jxl = load_survey_data(str(EXAMPLES_DIR / "PRS-6.jxl"))

    paired_exports = loaded_job.diagnostics.details.get('paired_exports', [])
    assert loaded_job.source_format == 'trimble_job'
    assert loaded_job.parser_strategy == 'job_paired_jobxml_exact'
    assert loaded_job.confidence > loaded_jxl.confidence
    assert paired_exports
    assert paired_exports[0]['paired_file'].endswith('PRS-6.jxl')
    assert paired_exports[0]['max_nearest_distance'] is not None
    assert paired_exports[0]['max_nearest_distance'] < 0.01
    assert loaded_job.diagnostics.details['paired_export_used'].endswith('PRS-6.jxl')
    assert loaded_job.diagnostics.warnings


def test_trimble_job_uses_paired_export_for_exact_match():
    loaded_job = load_survey_data(str(EXAMPLES_DIR / "Priv-URS_Privoln-1.job"))
    loaded_jxl = load_survey_data(str(EXAMPLES_DIR / "Priv-URS_Privoln-1.jxl"))

    paired_exports = loaded_job.diagnostics.details.get('paired_exports', [])

    assert loaded_job.parser_strategy == 'job_paired_jobxml_exact'
    assert loaded_job.diagnostics.details['paired_export_used'].endswith('Priv-URS_Privoln-1.jxl')
    assert paired_exports
    assert paired_exports[0]['point_count_delta'] == 0
    assert paired_exports[0]['max_nearest_distance'] is not None
    assert paired_exports[0]['max_nearest_distance'] < 0.01
    pd.testing.assert_frame_equal(
        loaded_job.data.reset_index(drop=True),
        loaded_jxl.data.reset_index(drop=True),
    )


@pytest.mark.parametrize(
    ("filename", "expected_strategy"),
    [
        ("Priv/Priv-PRS_Semichniy.jxl", "trimble_jxl"),
        ("Priv/Priv-PRS_Semichniy.job", "trimble_job"),
    ],
)
def test_trimble_semichniy_detects_multi_station_blocks(filename, expected_strategy):
    loaded = load_survey_data(str(EXAMPLES_DIR / filename))

    assert loaded.source_format == expected_strategy
    assert loaded.diagnostics.details.get('multi_station_detected') is True
    assert [block['station_name'] for block in loaded.diagnostics.details.get('station_blocks', [])] == ['st1', 'st2']
    assert 'rp1' in loaded.diagnostics.details.get('auxiliary_points', [])

    station_rows = loaded.data[loaded.data['is_station']]
    assert station_rows['name'].tolist() == ['st1', 'st2']
    assert int(station_rows.iloc[0]['survey_station_order']) == 1
    assert int(station_rows.iloc[1]['survey_station_order']) == 2
    assert bool(loaded.data.loc[loaded.data['name'] == 'rp1', 'is_auxiliary'].iloc[0]) is True


def test_semichniy_multi_station_merge_forms_four_belts_and_marks_duplicates():
    loaded = load_survey_data(str(EXAMPLES_DIR / "Priv/Priv-PRS_Semichniy.jxl"))
    base_station_idx = int(loaded.data.index[loaded.data['name'] == 'st1'][0])

    merged, audit = auto_merge_multi_station_tower(
        loaded.data,
        4,
        base_station_idx=base_station_idx,
    )

    working_mask = build_working_tower_mask(merged)
    active_points = merged[working_mask & merged['belt'].notna()].copy()

    assert sorted(active_points['belt'].dropna().astype(int).unique().tolist()) == [1, 2, 3, 4]
    assert audit['new_belts'] == [4]
    assert len(audit['control_duplicates']) >= 4
    assert len(audit['review_duplicates']) >= 1

    station_rows = merged[merged['is_station']].copy()
    assert station_rows['belt'].isna().all()
    assert station_rows['station_role'].tolist() == ['primary', 'secondary']

    auxiliary_row = merged[merged['name'] == 'rp1'].iloc[0]
    assert bool(auxiliary_row['is_auxiliary']) is True
    assert pd.isna(auxiliary_row['belt'])

    control_names = set(merged.loc[merged['is_control'], 'name'].astype(str).tolist())
    assert {'19', '20', '21', '22', '23', '25', '26', '27', '28'}.issubset(control_names)


def test_data_import_wizard_preserves_multi_station_service_points(monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *args, **kwargs: QMessageBox.StandardButton.Ok))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *args, **kwargs: QMessageBox.StandardButton.Ok))

    loaded = load_survey_data(str(EXAMPLES_DIR / "Priv/Priv-PRS_Semichniy.jxl"))
    wizard = DataImportWizard(loaded.data, import_payload=loaded.to_context_dict())
    wizard.cached_selected_points = loaded.data.copy()
    wizard.show_step_2()
    wizard.finalize_data()

    result = wizard.get_result()
    active_names = set(result.loc[result['belt'].notna(), 'name'].astype(str).tolist())

    assert {'st1', 'st2', 'rp1'}.isdisjoint(active_names)
    assert result.loc[result['is_station'], 'belt'].isna().all()
    assert result.loc[result['is_auxiliary'], 'belt'].isna().all()
    assert result.loc[result['is_control'], 'belt'].isna().all()
    assert sorted(result.loc[result['belt'].notna(), 'belt'].dropna().astype(int).unique().tolist()) == [1, 2, 3, 4]
    assert int(result['is_control'].sum()) >= 4

    wizard.reject()
    app.processEvents()


def test_data_import_wizard_can_exclude_point_from_belts(monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *args, **kwargs: QMessageBox.StandardButton.Ok))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *args, **kwargs: QMessageBox.StandardButton.Ok))

    data = _prepare_simple_single_station_data()
    wizard = DataImportWizard(data)
    wizard.cached_selected_points = data[~data["is_station"]].copy()
    wizard.show_step_2()
    station_combo_idx = wizard.station_combo.findData(int(data.index[data["is_station"]][0]))
    assert station_combo_idx >= 0
    wizard.station_combo.setCurrentIndex(station_combo_idx)
    wizard.auto_sort_belts()

    source_list = next(belt_list for belt_list in wizard.belt_lists if belt_list.count() > 0)
    item = source_list.item(0)
    point_idx = int(item.data(Qt.ItemDataRole.UserRole))
    point_name = str(data.loc[point_idx, "name"])
    item.setSelected(True)
    source_list.setCurrentItem(item)
    source_list.setFocus()

    wizard.move_to_unassigned()

    assert any(
        int(wizard.unassigned_list.item(i).data(Qt.ItemDataRole.UserRole)) == point_idx
        for i in range(wizard.unassigned_list.count())
    )
    assert all(
        all(
            int(belt_list.item(i).data(Qt.ItemDataRole.UserRole)) != point_idx
            for i in range(belt_list.count())
        )
        for belt_list in wizard.belt_lists
    )

    wizard.finalize_data()
    result = wizard.get_result()
    assert point_name not in set(result["name"].astype(str).tolist())

    wizard.reject()
    app.processEvents()


def test_data_import_wizard_can_restore_point_from_unassigned_list(monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *args, **kwargs: QMessageBox.StandardButton.Ok))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *args, **kwargs: QMessageBox.StandardButton.Ok))
    monkeypatch.setattr(QInputDialog, "getInt", staticmethod(lambda *args, **kwargs: (2, True)))

    data = _prepare_simple_single_station_data()
    wizard = DataImportWizard(data)
    wizard.cached_selected_points = data[~data["is_station"]].copy()
    wizard.show_step_2()
    station_combo_idx = wizard.station_combo.findData(int(data.index[data["is_station"]][0]))
    assert station_combo_idx >= 0
    wizard.station_combo.setCurrentIndex(station_combo_idx)
    wizard.auto_sort_belts()

    source_list = next(belt_list for belt_list in wizard.belt_lists if belt_list.count() > 0)
    item = source_list.item(0)
    point_idx = int(item.data(Qt.ItemDataRole.UserRole))
    point_name = str(data.loc[point_idx, "name"])
    item.setSelected(True)
    source_list.setCurrentItem(item)
    source_list.setFocus()
    wizard.move_to_unassigned()

    restored_item = next(
        wizard.unassigned_list.item(i)
        for i in range(wizard.unassigned_list.count())
        if int(wizard.unassigned_list.item(i).data(Qt.ItemDataRole.UserRole)) == point_idx
    )
    restored_item.setSelected(True)
    wizard.unassigned_list.setCurrentItem(restored_item)
    wizard.unassigned_list.setFocus()

    wizard.move_to_belt()
    wizard.finalize_data()
    result = wizard.get_result()
    point_row = result[result["name"].astype(str) == point_name].iloc[0]

    assert int(point_row["belt"]) == 2
    assert all(
        int(wizard.unassigned_list.item(i).data(Qt.ItemDataRole.UserRole)) != point_idx
        for i in range(wizard.unassigned_list.count())
    )

    wizard.reject()
    app.processEvents()


def test_data_import_wizard_excluded_multi_station_point_is_removed_from_result(monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *args, **kwargs: QMessageBox.StandardButton.Ok))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *args, **kwargs: QMessageBox.StandardButton.Ok))

    loaded = load_survey_data(str(EXAMPLES_DIR / "Priv/Priv-PRS_Semichniy.jxl"))
    wizard = DataImportWizard(loaded.data, import_payload=loaded.to_context_dict())
    wizard.cached_selected_points = loaded.data.copy()
    wizard.show_step_2()

    source_list = next(belt_list for belt_list in wizard.belt_lists if belt_list.count() > 0)
    item = source_list.item(0)
    point_idx = int(item.data(Qt.ItemDataRole.UserRole))
    point_name = str(loaded.data.loc[point_idx, "name"])
    item.setSelected(True)
    source_list.setCurrentItem(item)
    source_list.setFocus()

    wizard.move_to_unassigned()
    wizard.finalize_data()
    result = wizard.get_result()

    assert point_name not in set(result["name"].astype(str).tolist())

    wizard.reject()
    app.processEvents()


def test_composite_split_height_detection_handles_privoln_mast():
    loaded = load_survey_data(str(EXAMPLES_DIR / "Priv-URS_Privoln-1.jxl"))

    split_height = estimate_composite_split_height(loaded.data, num_belts=4)

    assert split_height is not None
    assert 48.0 <= split_height <= 48.8


def test_global_angle_grouping_keeps_four_face_tracks_on_privoln_mast():
    loaded = load_survey_data(str(EXAMPLES_DIR / "Priv-URS_Privoln-1.jxl"))
    tower_points = loaded.data[loaded.data["name"] != "st1"].copy()

    grouped = group_points_by_global_angle(
        tower_points,
        tower_points.index.tolist(),
        4,
    )

    counts = sorted(len(group) for group in grouped)
    assert counts == [10, 12, 12, 12]


def test_global_angle_grouping_preserves_three_observed_tracks_on_partial_four_face_job():
    loaded = load_survey_data(str(EXAMPLES_DIR / "Priv-PRS_Razvilnoe-1.job"))
    data = loaded.data.copy()
    data["is_station"] = data["name"].astype(str).str.lower().eq("st1")
    tower_points = data[~data["is_station"]].copy()

    grouped = group_points_by_global_angle(
        data,
        tower_points.index.tolist(),
        4,
    )

    non_empty_counts = sorted(len(group) for group in grouped if group)
    assert non_empty_counts == [4, 4, 6]
    assert sum(1 for group in grouped if group) == 3

    point_to_group = {}
    for group_idx, group in enumerate(grouped, start=1):
        for idx in group:
            point_to_group[idx] = group_idx

    idx_4 = tower_points.index[tower_points["name"] == "4"][0]
    idx_5 = tower_points.index[tower_points["name"] == "5"][0]
    idx_8 = tower_points.index[tower_points["name"] == "8"][0]
    idx_9 = tower_points.index[tower_points["name"] == "9"][0]
    idx_12 = tower_points.index[tower_points["name"] == "12"][0]
    idx_13 = tower_points.index[tower_points["name"] == "13"][0]

    assert point_to_group[idx_4] == point_to_group[idx_5]
    assert point_to_group[idx_8] == point_to_group[idx_9]
    assert point_to_group[idx_12] == point_to_group[idx_13]

    for belt_num, group in enumerate(grouped, start=1):
        data.loc[group, "belt"] = belt_num

    assigned_belts = sorted(int(value) for value in data.loc[~data["is_station"], "belt"].dropna().unique())
    assert assigned_belts == [1, 2, 3]


def test_global_angle_grouping_starts_from_station_right_track_on_ostrogozsk_job():
    loaded = load_survey_data(str(EXAMPLES_DIR / "ostrogozsk_prs15.jxl"))
    data = loaded.data.copy()
    tower_points = data[~data["name"].astype(str).str.lower().str.startswith("st")].copy()

    grouped = group_points_by_global_angle(
        data,
        tower_points.index.tolist(),
        4,
    )

    point_to_group = {}
    for group_idx, group in enumerate(grouped, start=1):
        for idx in group:
            point_to_group[idx] = group_idx

    assert all(point_to_group[tower_points.index[tower_points["name"] == name][0]] == 1 for name in ["1", "2", "3", "4", "5"])
    assert all(point_to_group[tower_points.index[tower_points["name"] == name][0]] == 2 for name in ["6", "7", "8", "9", "10"])
    assert all(point_to_group[tower_points.index[tower_points["name"] == name][0]] == 3 for name in ["11", "12", "13", "14", "15"])
    assert all(point_to_group[tower_points.index[tower_points["name"] == name][0]] == 4 for name in ["16", "17", "18", "19", "20"])


def test_method2_preview_finds_stable_pair_for_partial_second_station_job():
    first, second = _prepare_razvilnoe_station_pair()

    preview = find_best_method2_preview(
        first,
        second,
        tower_faces=4,
        target_angle_deg=90.0,
        prefer_clockwise=True,
    )

    assert preview is not None
    assert preview["mapping_source"] == "pair_inference"
    assert preview["expected_visible_mapping_sequence"] == [2, 1, 4]
    assert preview["visible_mapping_sequence"] == [3, 2, 1]
    assert preview["second_visible_order_left_to_right"] == [3, 2, 1]
    assert preview["station_angle_delta_deg"] == pytest.approx(90.0, abs=7.0)
    assert float(preview["angle_deg"]) == pytest.approx(85.39, abs=8.0)


def test_method1_preview_maps_second_station_clockwise_and_right_side():
    first, second = _prepare_razvilnoe_station_pair()

    preview = build_method1_preview(
        first,
        second,
        tower_faces=4,
        target_angle_deg=90.0,
        prefer_clockwise=True,
    )

    assert preview is not None
    assert preview["visible_mapping_sequence"] == [4, 3, 2]
    assert preview["belt_mapping"] == {1: 2, 2: 3, 3: 4}
    assert preview["matched_pair_count"] >= 6
    assert preview["station_side"] == "right"
    assert preview["station_angle_delta_deg"] == pytest.approx(90.0, abs=10.0)


def test_second_station_wizard_auto_match_populates_preview_for_razvilnoe_pair(monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *args, **kwargs: QMessageBox.StandardButton.Ok))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *args, **kwargs: QMessageBox.StandardButton.Ok))

    first, second = _prepare_razvilnoe_station_pair()
    wizard = SecondStationImportWizard(first, belt_count_from_first_import=4)
    wizard.second_station_data = second
    wizard._populate_new_table(second)
    wizard.method2_radio.setChecked(True)

    wizard.auto_match_points()

    assert wizard.method2_preview is not None
    assert wizard.method2_preview["expected_visible_mapping_sequence"] == [2, 1, 4]
    assert wizard.method2_preview["visible_mapping_sequence"] == [3, 2, 1]
    assert wizard.get_visualization_data() is not None

    selected_rows = []
    for row in range(wizard.new_table.rowCount()):
        combo = wizard.new_table.cellWidget(row, 4)
        if combo is not None and combo.currentData() not in (-1, None):
            selected_rows.append(row)
    assert selected_rows == [wizard._find_table_row_by_second_index(wizard.method2_preview["second_index"])]

    summary = wizard._compose_quality_summary()
    assert "Preview" in summary
    assert "2-1-4" in summary

    wizard.reject()
    app.processEvents()


def test_second_station_wizard_method1_auto_match_uses_clockwise_mapping(monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *args, **kwargs: QMessageBox.StandardButton.Ok))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *args, **kwargs: QMessageBox.StandardButton.Ok))

    first, second = _prepare_razvilnoe_station_pair()
    wizard = SecondStationImportWizard(first, belt_count_from_first_import=4)
    wizard.second_station_data = second
    wizard._populate_new_table(second)
    wizard.method1_radio.setChecked(True)

    wizard.auto_match_points()

    assert wizard.method1_preview is not None
    assert wizard.second_station_belt_mapping == {1: 2, 2: 3, 3: 4}
    assert wizard.method1_preview["visible_mapping_sequence"] == [4, 3, 2]
    assert wizard.method1_preview["station_side"] == "right"

    selected_rows = []
    for row in range(wizard.new_table.rowCount()):
        combo = wizard.new_table.cellWidget(row, 4)
        if combo is not None and combo.currentData() not in (-1, None):
            selected_rows.append(row)

    assert len(selected_rows) >= 6

    summary = wizard._compose_quality_summary()
    assert "Method 1 preview" in summary
    assert "4-3-2" in summary
    assert "right" in summary

    wizard.reject()
    app.processEvents()


def test_second_station_wizard_method1_merge_uses_remapped_belts(monkeypatch):
    class _DummyEditor:
        def __init__(self):
            self.data = None
            self.lines = None

        def set_data(self, data):
            self.data = data.copy()

        def set_belt_connection_lines(self, lines):
            self.lines = dict(lines or {})

        def get_data(self):
            return self.data.copy() if self.data is not None else pd.DataFrame()

    class _DummyParent(QWidget):
        def __init__(self):
            super().__init__()
            self.editor_3d = _DummyEditor()

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *args, **kwargs: QMessageBox.StandardButton.Ok))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *args, **kwargs: QMessageBox.StandardButton.Yes))
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *args, **kwargs: QMessageBox.StandardButton.Ok))

    first, second = _prepare_razvilnoe_station_pair()
    parent = _DummyParent()
    parent.editor_3d.set_data(first)
    wizard = SecondStationImportWizard(first, parent=parent, belt_count_from_first_import=4)
    wizard.second_station_data = second
    wizard._populate_new_table(second)
    wizard.method1_radio.setChecked(True)

    wizard.auto_match_points()
    wizard._merge_method1()

    assert wizard.result_data is not None
    assert wizard.transform_quality["method"] == 1
    assert wizard.second_station_belt_mapping == {1: 2, 2: 3, 3: 4}

    second_names = set(second["name"].astype(str))
    merged_second = wizard.result_data[wizard.result_data["name"].astype(str).isin(second_names)]
    merged_belts = sorted(int(value) for value in merged_second["belt"].dropna().unique())
    assert 4 in merged_belts

    wizard.reject()
    app.processEvents()


def test_section_operations_follow_tracks_for_privoln_composite_import():
    loaded = load_survey_data(str(EXAMPLES_DIR / "Priv-URS_Privoln-1.jxl"))
    data = loaded.data.copy()
    data["is_station"] = data["name"].eq("st1")

    tower_mask = ~data["is_station"]
    grouped = group_points_by_global_angle(
        data,
        data.index[tower_mask].tolist(),
        4,
    )
    for belt_num, group in enumerate(grouped, start=1):
        data.loc[group, "belt"] = belt_num
        data.loc[group, "part_belt"] = belt_num
    data.loc[data["is_station"], "belt"] = pd.NA

    split_height = 48.36
    tolerance = 1.0
    memberships = []
    primary_parts = []
    for _, row in data.iterrows():
        if bool(row["is_station"]):
            memberships.append(json.dumps([], ensure_ascii=False))
            primary_parts.append(pd.NA)
            continue

        z_value = float(row["z"])
        if z_value < split_height - tolerance:
            parts = [1]
        elif abs(z_value - split_height) <= tolerance:
            parts = [1, 2]
        else:
            parts = [2]

        memberships.append(json.dumps(parts, ensure_ascii=False))
        primary_parts.append(parts[0])

    data["tower_part_memberships"] = memberships
    data["tower_part"] = primary_parts
    data["faces"] = data["belt"].where(~data["is_station"]).map(lambda value: 4 if pd.notna(value) else pd.NA)

    levels = find_section_levels(data, height_tolerance=0.3)
    assert len(levels) == 12
    assert levels[0] == pytest.approx(6.2367, abs=0.2)
    assert levels[8] == pytest.approx(48.403, abs=0.3)
    assert levels[-1] == pytest.approx(62.093, abs=0.3)

    completed = add_missing_points_for_sections(data, levels, height_tolerance=0.3)
    assert len(completed) == len(data) + 3

    section_lines = get_section_lines(completed, levels, height_tolerance=0.3)
    assert len(section_lines) == 12
    assert len(section_lines[0]["points"]) == 4
    assert len(section_lines[-1]["points"]) == 4


def test_project_manager_persists_import_metadata(tmp_path):
    manager = ProjectManager()
    raw_data = pd.DataFrame(
        [
            {'name': 'P1', 'x': 1.0, 'y': 0.0, 'z': 0.0},
            {'name': 'P2', 'x': 0.0, 'y': 1.0, 'z': 0.0},
            {'name': 'P3', 'x': -1.0, 'y': 0.0, 'z': 5.0},
        ]
    )
    processed_data = {'valid': True, 'centers': pd.DataFrame([{'x': 0.0, 'y': 0.0, 'z': 0.0, 'deviation': 0.0}])}
    import_context = {'source_format': 'csv', 'parser_strategy': 'csv_sep_comma', 'confidence': 0.95}
    import_diagnostics = {
        'source_format': 'csv',
        'parser_strategy': 'csv_sep_comma',
        'raw_records': 3,
        'accepted_points': 3,
        'discarded_points': 0,
        'warnings': [],
    }
    transformation_audit = {'method': 2, 'matching': {'matched_count': 1, 'unmatched_count': 0}}
    target = tmp_path / 'sample.gvproj'

    manager.save_project(
        file_path=str(target),
        raw_data=raw_data,
        processed_data=processed_data,
        epsg_code=None,
        current_file_path='examples/test_tower_data.csv',
        original_data_before_sections=None,
        height_tolerance=0.1,
        center_method='mean',
        expected_belt_count=4,
        tower_faces_count=4,
        import_context=import_context,
        import_diagnostics=import_diagnostics,
        transformation_audit=transformation_audit,
    )
    restored = manager.load_project(str(target))

    assert restored['import_context'] == import_context
    assert restored['import_diagnostics']['accepted_points'] == 3
    assert restored['transformation_audit']['method'] == 2


def test_calculation_service_rejects_non_contiguous_belts_in_assigned_sections_mode():
    service = CalculationService()
    data = pd.DataFrame(
        [
            {'name': 'P1', 'x': 1.0, 'y': 0.0, 'z': 0.0, 'belt': 1},
            {'name': 'P2', 'x': -1.0, 'y': 0.0, 'z': 0.0, 'belt': 1},
            {'name': 'P3', 'x': 1.0, 'y': 0.0, 'z': 5.0, 'belt': 3},
            {'name': 'P4', 'x': -1.0, 'y': 0.0, 'z': 5.0, 'belt': 3},
        ]
    )

    with pytest.raises(Exception, match='отсутствуют \\[2\\]'):
        service.calculate(
            raw_data=data,
            table_data=data,
            epsg_code=None,
            height_tolerance=0.1,
            center_method='mean',
            section_grouping_mode='assigned_sections',
        )


def test_calculation_service_accepts_sparse_face_belts_in_height_level_mode():
    service = CalculationService()
    data = pd.DataFrame(
        [
            {'name': 'P1', 'x': 1.0, 'y': 0.0, 'z': 0.0, 'belt': 1},
            {'name': 'P2', 'x': -1.0, 'y': 0.0, 'z': 0.0, 'belt': 3},
            {'name': 'P3', 'x': 1.0, 'y': 0.0, 'z': 5.0, 'belt': 1},
            {'name': 'P4', 'x': -1.0, 'y': 0.0, 'z': 5.0, 'belt': 3},
        ]
    )

    results = service.calculate(
        raw_data=data,
        table_data=data,
        epsg_code=None,
        height_tolerance=0.1,
        center_method='mean',
        section_grouping_mode='height_levels',
    )

    assert results['valid']
    assert len(results['centers']) == 2


def test_privoln_straightness_profiles_match_widget_and_report():
    app = QApplication.instance() or QApplication([])
    data = _finalize_import_for_calculations('Priv-URS_Privoln-1.jxl')
    service = CalculationService()
    results = service.calculate(
        raw_data=data,
        table_data=data,
        epsg_code=None,
        height_tolerance=0.3,
        center_method='mean',
        section_grouping_mode='height_levels',
    )

    widget = StraightnessWidget()
    widget.set_data(data, results)
    widget_data = widget.get_all_belts_data()
    widget_max = max(
        abs(point['deflection'])
        for part in widget_data.values()
        for belt_points in part['belts'].values()
        for point in belt_points
    )

    report_records = ReportDataAssembler(results, data, [])._build_straightness_records()
    report_max = max(abs(record.deviation_mm) for record in report_records)

    assert len(results['centers']) == len(find_section_levels(data, 0.3))
    assert float(results['centers']['deviation'].max()) < 0.25
    assert results['tower_parts_info']['split_height'] is None
    assert round(results['straightness_summary']['max_deflection_mm'], 1) == 147.3
    assert round(widget_max, 1) == 147.3
    assert round(report_max, 1) == 147.3
    assert [(p['part_number'], p['belt'], round(p['max_deflection_mm'], 1)) for p in results['straightness_profiles']] == [
        (1, 1, 23.4),
        (1, 2, 37.5),
        (1, 3, 147.3),
        (1, 4, 9.9),
    ]
    app.processEvents()


def test_semichniy_straightness_profiles_ignore_service_points_and_match_widget():
    app = QApplication.instance() or QApplication([])
    data = _finalize_import_for_calculations('Priv/Priv-PRS_Semichniy.jxl')
    service = CalculationService()
    results = service.calculate(
        raw_data=data,
        table_data=data,
        epsg_code=None,
        height_tolerance=0.3,
        center_method='mean',
        section_grouping_mode='height_levels',
    )

    widget = StraightnessWidget()
    widget.set_data(data, results)
    widget_data = widget.get_all_belts_data()
    widget_max = max(
        abs(point['deflection'])
        for part in widget_data.values()
        for belt_points in part['belts'].values()
        for point in belt_points
    )

    profile_source_indices = {
        int(point['source_index'])
        for profile in results['straightness_profiles']
        for point in profile['points']
    }
    excluded_indices = set(data.index[~build_working_tower_mask(data)])

    assert len(results['centers']) == len(find_section_levels(data, 0.3))
    assert float(results['centers']['deviation'].max()) < 0.25
    assert profile_source_indices.isdisjoint(excluded_indices)
    assert results['tower_parts_info']['split_height'] is None
    assert round(results['straightness_summary']['max_deflection_mm'], 1) == 44.6
    assert round(widget_max, 1) == 44.6
    app.processEvents()


def test_full_report_assembler_includes_import_quality(tmp_path):
    manager = ReportTemplateManager(storage_dir=tmp_path)
    sample = _sample_report_data()
    manager.save_template(sample, 'base')

    centers = pd.DataFrame([{'z': 5.0, 'deviation': 0.0002, 'points_count': 4}])
    processed = {
        'centers': centers,
        'import_context': {
            'source_format': 'trimble_job',
            'parser_strategy': 'job_paired_jobxml_exact',
            'confidence': 0.99,
        },
        'import_diagnostics': {
            'source_format': 'trimble_job',
            'parser_strategy': 'job_paired_jobxml_exact',
            'raw_records': 80556,
            'accepted_points': 46,
            'discarded_points': 80510,
            'warnings': ['Для точного импорта JOB использован парный экспорт PRS-6.jxl.'],
            'details': {
                'paired_export_used': 'examples/PRS-6.jxl',
                'paired_exports': [{'paired_file': 'examples/PRS-6.jxl', 'point_count_delta': 3}],
            },
        },
        'transformation_audit': {'method': 2},
    }

    report = build_report_data_from_template(manager, 'base', processed, centers)
    import_quality = report.geodesic_results['import_quality']

    assert import_quality['source_format'] == 'trimble_job'
    assert import_quality['parser_strategy'] == 'job_paired_jobxml_exact'
    assert import_quality['paired_exports'][0]['point_count_delta'] == 3


def test_blueprint_uses_faces_column_for_partial_simple_import():
    data = pd.DataFrame(
        [
            {'name': 'P1', 'x': 2.0, 'y': 0.0, 'z': 0.0, 'belt': 1, 'faces': 4},
            {'name': 'P2', 'x': -1.0, 'y': 1.0, 'z': 0.0, 'belt': 1, 'faces': 4},
            {'name': 'P3', 'x': -1.0, 'y': -1.0, 'z': 0.0, 'belt': 1, 'faces': 4},
            {'name': 'P4', 'x': 2.2, 'y': 0.0, 'z': 5.0, 'belt': 3, 'faces': 4},
            {'name': 'P5', 'x': -1.1, 'y': 1.1, 'z': 5.0, 'belt': 3, 'faces': 4},
            {'name': 'P6', 'x': -1.1, 'y': -1.1, 'z': 5.0, 'belt': 3, 'faces': 4},
        ]
    )

    blueprint = create_blueprint_from_imported_data(data)

    assert len(blueprint.segments) == 1
    assert blueprint.segments[0].faces == 4


def test_blueprint_uses_default_faces_for_partial_simple_import():
    data = pd.DataFrame(
        [
            {'name': 'P1', 'x': 2.0, 'y': 0.0, 'z': 0.0, 'belt': 1},
            {'name': 'P2', 'x': -1.0, 'y': 1.0, 'z': 0.0, 'belt': 1},
            {'name': 'P3', 'x': -1.0, 'y': -1.0, 'z': 0.0, 'belt': 1},
            {'name': 'P4', 'x': 2.2, 'y': 0.0, 'z': 5.0, 'belt': 3},
            {'name': 'P5', 'x': -1.1, 'y': 1.1, 'z': 5.0, 'belt': 3},
            {'name': 'P6', 'x': -1.1, 'y': -1.1, 'z': 5.0, 'belt': 3},
        ]
    )

    blueprint = create_blueprint_from_imported_data(data, default_faces=4)

    assert len(blueprint.segments) == 1
    assert blueprint.segments[0].faces == 4


def test_data_import_wizard_ignores_legacy_saved_belt_assignments(monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *args, **kwargs: QMessageBox.StandardButton.Ok))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *args, **kwargs: QMessageBox.StandardButton.Ok))

    data = pd.DataFrame(
        [
            {"name": "E0", "x": 2.0, "y": 0.0, "z": 0.0},
            {"name": "N0", "x": 0.0, "y": 2.0, "z": 0.0},
            {"name": "W0", "x": -2.0, "y": 0.0, "z": 0.0},
            {"name": "S0", "x": 0.0, "y": -2.0, "z": 0.0},
            {"name": "E5", "x": 2.0, "y": 0.0, "z": 5.0},
            {"name": "N5", "x": 0.0, "y": 2.0, "z": 5.0},
            {"name": "W5", "x": -2.0, "y": 0.0, "z": 5.0},
            {"name": "S5", "x": 0.0, "y": -2.0, "z": 5.0},
            {"name": "E10", "x": 2.0, "y": 0.0, "z": 10.0},
            {"name": "N10", "x": 0.0, "y": 2.0, "z": 10.0},
            {"name": "W10", "x": -2.0, "y": 0.0, "z": 10.0},
            {"name": "S10", "x": 0.0, "y": -2.0, "z": 10.0},
            {"name": "st1", "x": -15.0, "y": 0.0, "z": 1.7},
        ]
    )
    data["is_station"] = data["name"].eq("st1")

    legacy_settings = {
        "belt_count": 4,
        "belt_assignments": {
            1: ["S0", "S5", "S10"],
            2: ["W0", "W5", "W10"],
            3: ["N0", "N5", "N10"],
            4: ["E0", "E5", "E10"],
        },
    }

    wizard = DataImportWizard(data, saved_settings=legacy_settings)
    wizard.cached_selected_points = data[~data["is_station"]].copy()
    wizard.show_step_2()
    station_combo_idx = wizard.station_combo.findData(int(data.index[data["is_station"]][0]))
    assert station_combo_idx >= 0
    wizard.station_combo.setCurrentIndex(station_combo_idx)
    wizard.auto_sort_belts()

    belt_1_names = {wizard.belt_lists[0].item(i).text().split(" ", 1)[0] for i in range(wizard.belt_lists[0].count())}
    belt_2_names = {wizard.belt_lists[1].item(i).text().split(" ", 1)[0] for i in range(wizard.belt_lists[1].count())}
    belt_4_names = {wizard.belt_lists[3].item(i).text().split(" ", 1)[0] for i in range(wizard.belt_lists[3].count())}

    assert belt_1_names
    assert all(name.startswith("S") for name in belt_1_names)
    assert "S10" in belt_1_names
    assert all(name.startswith("W") for name in belt_2_names)
    assert all(name.startswith("E") for name in belt_4_names)

    wizard.reject()
    app.processEvents()
