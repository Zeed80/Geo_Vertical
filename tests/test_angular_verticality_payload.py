import math
import os
from pathlib import Path
from types import MethodType

import pandas as pd
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox, QTableWidgetItem

from core.calculations import process_tower_data
from core.data_loader import load_survey_data
from core.section_operations import find_section_levels, get_section_lines
from core.services.calculation_service import CalculationService
from gui.data_import_wizard import DataImportWizard
from gui.data_table import AddStationDialog, DataTableWidget
from gui.report_widget import ReportWidget
from gui.straightness_widget import StraightnessWidget
from gui.verticality_widget import VerticalityWidget
from utils.report_generator_enhanced import EnhancedReportGenerator

_APP = QApplication.instance() or QApplication([])
EXAMPLES_DIR = Path(__file__).resolve().parents[1] / "examples"


class _EditorStub:
    def __init__(self, section_data):
        self.section_data = section_data
        self.active_station_index = None

    def set_active_station_index(self, station_id):
        self.active_station_index = station_id


def _ensure_app():
    return _APP


def _concat_without_all_na_warning(base_frame: pd.DataFrame, extra_frame: pd.DataFrame) -> pd.DataFrame:
    bool_like_columns = {"is_station", "is_auxiliary", "is_control", "is_part_boundary"}
    all_columns = list(dict.fromkeys([*base_frame.columns.tolist(), *extra_frame.columns.tolist()]))

    def _point_index_series(length: int, offset: int) -> pd.Series:
        return pd.Series(range(offset + 1, offset + length + 1), dtype="Int64")

    def _default_value(column_name: str):
        if column_name in bool_like_columns:
            return False
        if column_name in base_frame.columns and pd.api.types.is_numeric_dtype(base_frame[column_name]):
            return 0
        return ""

    def _prepare(frame: pd.DataFrame, point_index_offset: int) -> pd.DataFrame:
        prepared = frame.copy()
        for column_name in all_columns:
            if column_name == "point_index":
                fallback = _point_index_series(len(prepared), point_index_offset)
                if column_name not in prepared.columns:
                    prepared[column_name] = fallback
                else:
                    numeric_point_index = pd.to_numeric(prepared[column_name], errors="coerce")
                    prepared[column_name] = numeric_point_index.where(numeric_point_index.notna(), fallback).astype("Int64")
            elif column_name not in prepared.columns:
                prepared[column_name] = _default_value(column_name)
            elif prepared[column_name].isna().all():
                prepared[column_name] = _default_value(column_name)
        return prepared.loc[:, all_columns]

    return pd.concat(
        [
            _prepare(base_frame, 0),
            _prepare(extra_frame, len(base_frame)),
        ],
        ignore_index=True,
    )


def _section_points(center_x: float, center_y: float, z: float, radius: float = 1.0):
    return [
        (center_x + radius, center_y, z),
        (center_x, center_y + radius, z),
        (center_x - radius, center_y, z),
        (center_x, center_y - radius, z),
    ], [1, 2, 3, 4]


def _build_fixture_with_geometry(
    primary_station=(-10.0, 0.0),
    secondary_station=(6.0, -8.0),
    shift=(0.012, -0.004),
    upper_height=10.0,
):
    _ensure_app()

    base_points, base_belts = _section_points(0.0, 0.0, 0.0)
    upper_points, upper_belts = _section_points(shift[0], shift[1], upper_height)

    section_data = [
        {
            "name": "0",
            "height": 0.0,
            "points": base_points,
            "belt_nums": base_belts,
            "section_num": 0,
            "tower_part": 1,
        },
        {
            "name": "1",
            "height": upper_height,
            "points": upper_points,
            "belt_nums": upper_belts,
            "section_num": 1,
            "tower_part": 1,
        },
    ]
    editor = _EditorStub(section_data)
    widget = DataTableWidget(editor)

    records = [
        {
            "name": "ST1",
            "x": primary_station[0],
            "y": primary_station[1],
            "z": 1.5,
            "is_station": True,
            "station_role": "primary",
            "belt": None,
            "point_index": 1,
        },
        {
            "name": "ST2",
            "x": secondary_station[0],
            "y": secondary_station[1],
            "z": 1.5,
            "is_station": True,
            "station_role": "secondary",
            "belt": None,
            "point_index": 2,
        },
    ]

    point_index = 3
    for belts, points, section_prefix in (
        (base_belts, base_points, "B0"),
        (upper_belts, upper_points, "B1"),
    ):
        for belt, point in zip(belts, points):
            records.append(
                {
                    "name": f"{section_prefix}-{belt}",
                    "x": point[0],
                    "y": point[1],
                    "z": point[2],
                    "belt": belt,
                    "is_station": False,
                    "point_index": point_index,
                    "tower_part": 1,
                }
            )
            point_index += 1

    raw_data = pd.DataFrame(records)
    widget.set_data(raw_data)

    processed_results = {
        "valid": True,
        "centers": pd.DataFrame(
            [
                {
                    "x": 0.0,
                    "y": 0.0,
                    "z": 0.0,
                    "deviation": 0.0,
                    "deviation_x": 0.0,
                    "deviation_y": 0.0,
                },
                {
                    "x": shift[0],
                    "y": shift[1],
                    "z": upper_height,
                    "deviation": math.hypot(shift[0], shift[1]),
                    "deviation_x": shift[0],
                    "deviation_y": shift[1],
                },
            ]
        ),
    }
    widget.set_processed_results(processed_results)
    return widget, raw_data, processed_results, editor


def _build_fixture():
    return _build_fixture_with_geometry()


def _build_single_station_fixture():
    _, raw_data, processed_results, editor = _build_fixture()
    widget = DataTableWidget(editor)
    single_station_data = raw_data[raw_data["station_role"].fillna("") != "secondary"].copy()
    single_station_data.reset_index(drop=True, inplace=True)
    widget.set_data(single_station_data)
    widget.set_processed_results(processed_results)
    return widget, single_station_data, processed_results, editor


def _build_single_station_generated_center_fixture():
    section_data = [
        {
            "name": "0",
            "height": 0.0,
            "points": [(-1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (1.0, 0.0, 0.0), (0.0, -1.0, 0.0)],
            "belt_nums": [1, 2, 3, 4],
            "section_num": 0,
            "tower_part": 1,
            "center_xy": (0.0, 0.0),
            "center_z": 0.0,
        },
        {
            "name": "1",
            "height": 10.0,
            "points": [(-1.0, 0.0, 10.0), (5.0, 1.0, 10.0), (1.0, 0.0, 10.0), (5.0, -1.0, 10.0)],
            "belt_nums": [1, 2, 3, 4],
            "section_num": 1,
            "tower_part": 1,
            "center_xy": (0.0, 0.0),
            "center_z": 10.0,
        },
    ]
    editor = _EditorStub(section_data)
    widget = DataTableWidget(editor)

    raw_data = pd.DataFrame(
        [
            {
                "name": "ST1",
                "x": -10.0,
                "y": 0.0,
                "z": 1.5,
                "is_station": True,
                "station_role": "primary",
                "belt": None,
                "point_index": 1,
            },
            {
                "name": "B0-1",
                "x": -1.0,
                "y": 0.0,
                "z": 0.0,
                "belt": 1,
                "face_track": 1,
                "faces": 4,
                "is_station": False,
                "point_index": 2,
                "tower_part": 1,
            },
            {
                "name": "B0-2",
                "x": 0.0,
                "y": 1.0,
                "z": 0.0,
                "belt": 2,
                "face_track": 2,
                "faces": 4,
                "is_station": False,
                "point_index": 3,
                "tower_part": 1,
            },
            {
                "name": "B0-3",
                "x": 1.0,
                "y": 0.0,
                "z": 0.0,
                "belt": 3,
                "face_track": 3,
                "faces": 4,
                "is_station": False,
                "point_index": 4,
                "tower_part": 1,
            },
            {
                "name": "B0-4",
                "x": 0.0,
                "y": -1.0,
                "z": 0.0,
                "belt": 4,
                "face_track": 4,
                "faces": 4,
                "is_station": False,
                "point_index": 5,
                "tower_part": 1,
            },
            {
                "name": "B1-1",
                "x": -1.0,
                "y": 0.0,
                "z": 10.0,
                "belt": 1,
                "face_track": 1,
                "faces": 4,
                "is_station": False,
                "point_index": 6,
                "tower_part": 1,
            },
            {
                "name": "B1-2",
                "x": 5.0,
                "y": 1.0,
                "z": 10.0,
                "belt": 2,
                "face_track": 2,
                "faces": 4,
                "is_station": False,
                "point_index": 7,
                "tower_part": 1,
                "is_generated": True,
                "generated_by": "section_generation",
            },
            {
                "name": "B1-3",
                "x": 1.0,
                "y": 0.0,
                "z": 10.0,
                "belt": 3,
                "face_track": 3,
                "faces": 4,
                "is_station": False,
                "point_index": 8,
                "tower_part": 1,
            },
            {
                "name": "B1-4",
                "x": 5.0,
                "y": -1.0,
                "z": 10.0,
                "belt": 4,
                "face_track": 4,
                "faces": 4,
                "is_station": False,
                "point_index": 9,
                "tower_part": 1,
                "is_generated": True,
                "generated_by": "face_track_completion",
            },
        ]
    )
    widget.set_data(raw_data)
    widget.set_processed_results(None)
    return widget, raw_data, editor


def _build_real_example_fixture(*, add_second_station: bool = False, attach_processed_to_table: bool = True):
    loaded = load_survey_data(str(EXAMPLES_DIR / "острогожск_РРС-11.jxl"))
    wizard = DataImportWizard(loaded.data, import_payload=loaded.to_context_dict())
    wizard.cached_selected_points = loaded.data.copy()
    wizard.show_step_2()
    if hasattr(wizard, "station_combo") and wizard.station_combo is not None:
        station_index = wizard.station_combo.findText("St1")
        if station_index >= 0:
            wizard.station_combo.setCurrentIndex(station_index)
    wizard.auto_sort_belts()
    wizard.finalize_data()
    raw_data = wizard.get_result().copy()
    wizard.reject()
    _ensure_app().processEvents()

    if add_second_station:
        stations = raw_data.loc[raw_data["is_station"]].copy()
        tower_points = raw_data.loc[~raw_data["is_station"]].copy()
        station_row = stations.iloc[0]
        center_x = float(tower_points["x"].mean())
        center_y = float(tower_points["y"].mean())
        base_dx = float(station_row["x"]) - center_x
        base_dy = float(station_row["y"]) - center_y
        base_distance = math.hypot(base_dx, base_dy)
        base_norm = max(base_distance, 1e-9)
        orth_x = base_dy / base_norm
        orth_y = -base_dx / base_norm
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
                    "point_index": (
                        int(raw_data["point_index"].max()) + 1
                        if "point_index" in raw_data.columns
                        else len(raw_data) + 1
                    ),
                }
            ]
        )
        raw_data = _concat_without_all_na_warning(raw_data, second_station)

    levels = find_section_levels(raw_data, height_tolerance=0.3)
    editor = _EditorStub(get_section_lines(raw_data, levels, height_tolerance=0.3))
    widget = DataTableWidget(editor)
    widget.set_data(raw_data)
    processed_results = process_tower_data(
        raw_data,
        use_assigned_belts=False,
        section_grouping_mode="height_levels",
        use_cache=False,
    )
    if attach_processed_to_table:
        widget.set_processed_results(processed_results)
    return widget, raw_data, processed_results, editor


def test_angular_measurements_are_deterministic():
    widget, _, _, _ = _build_fixture()

    first = widget.get_angular_measurements()
    widget._invalidate_angular_verticality_cache()
    second = widget.get_angular_measurements()

    def _strip(rows):
        return [
            (
                row["section_num"],
                row["belt"],
                row["kl_sec"],
                row["kr_sec"],
                row["beta_sec"],
                row["delta_mm"],
            )
            for row in rows
        ]

    assert _strip(first["x"]) == _strip(second["x"])
    assert _strip(first["y"]) == _strip(second["y"])


def test_circle_readings_have_small_stable_deviation_and_absolute_angle_format():
    widget, _, _, _ = _build_fixture()
    payload = widget.get_angular_measurements()

    all_rows = payload["x"] + payload["y"]

    assert any(abs(row["diff_sec"]) > 0.0 for row in all_rows)
    assert all(abs(row["diff_sec"]) <= 2.0 for row in all_rows)
    assert all(not row["beta_str"].startswith("+") for row in all_rows)
    assert all(not row["center_str"].startswith("+") for row in all_rows)


def test_section_rows_share_center_and_delta_but_keep_distinct_side_angles():
    widget, _, _, _ = _build_fixture()
    payload = widget.get_angular_measurements()

    upper_rows = [row for row in payload["x"] if row.get("section_num") == 1]
    assert len(upper_rows) == 2
    assert len({row["center_str"] for row in upper_rows}) == 1
    assert len({row["delta_str"] for row in upper_rows}) == 1
    assert len({row["delta_mm_str"] for row in upper_rows}) == 1
    assert upper_rows[0]["beta_str"] != upper_rows[1]["beta_str"]
    assert upper_rows[0]["kl_str"] != upper_rows[1]["kl_str"]


def test_delta_b_is_derived_from_delta_beta_and_station_distance():
    widget, _, _, _ = _build_fixture()
    payload = widget.get_angular_measurements()

    upper_rows = [row for row in payload["x"] if row.get("section_num") == 1]

    expected_delta_mm = math.sin(math.radians(upper_rows[0]["delta_sec"] / 3600.0)) * upper_rows[0]["center_range_m"] * 1000.0

    assert upper_rows[0]["delta_mm"] == pytest.approx(expected_delta_mm, abs=1e-6)
    assert upper_rows[1]["delta_mm"] == pytest.approx(expected_delta_mm, abs=1e-6)


def test_station_ray_intersection_keeps_large_shift_geometry_exact():
    widget, _, _, _ = _build_fixture_with_geometry(
        primary_station=(-25.96552379995421, -6.380168654215614),
        secondary_station=(15.277404106968884, 3.608194565299815),
        shift=(0.04960381602092927, -0.02162902521950685),
    )
    payload = widget.get_angular_measurements()

    upper_section = next(section for section in payload["sections"] if section["section_num"] == 1)

    assert upper_section["resolved_shift_xy_mm"] == pytest.approx(
        [49.60381602092927, -21.62902521950685],
        abs=0.05,
    )
    assert upper_section["center_xy"] == pytest.approx((0.04960381602092927, -0.02162902521950685), abs=1e-9)
    assert upper_section["total_deviation"] == pytest.approx(
        math.hypot(49.60381602092927, -21.62902521950685),
        abs=0.05,
    )


def test_authoritative_two_station_sections_use_lowest_section_as_zero_baseline():
    widget, _, _, _ = _build_fixture()
    payload = widget.get_angular_measurements()

    base_section = next(section for section in payload["sections"] if section["section_num"] == 0)

    assert base_section["deviation_x"] == pytest.approx(0.0, abs=1e-9)
    assert base_section["deviation_y"] == pytest.approx(0.0, abs=1e-9)
    assert base_section["total_deviation"] == pytest.approx(0.0, abs=1e-9)

    base_rows_x = [row for row in payload["x"] if row.get("section_num") == 0]
    base_rows_y = [row for row in payload["y"] if row.get("section_num") == 0]
    assert base_rows_x
    assert base_rows_y
    assert all(float(row["delta_mm"]) == pytest.approx(0.0, abs=1e-9) for row in base_rows_x)
    assert all(float(row["delta_mm"]) == pytest.approx(0.0, abs=1e-9) for row in base_rows_y)


def test_non_orthogonal_station_geometry_reconstructs_total_deviation():
    widget, _, _, _ = _build_fixture()
    payload = widget.get_angular_measurements()

    upper_section = next(section for section in payload["sections"] if section["section_num"] == 1)
    aggregated = EnhancedReportGenerator._aggregate_angular_measurements_by_sections(payload)
    aggregated_upper = next(section for section in aggregated if section["section_num"] == 1)

    assert upper_section["station_deviation_x"] == pytest.approx(-4.0, abs=0.05)
    assert upper_section["station_deviation_y"] == pytest.approx(-7.2, abs=0.05)
    assert upper_section["resolved_shift_xy_mm"] == pytest.approx([12.0, -4.0], abs=0.05)
    assert upper_section["total_deviation"] == pytest.approx(math.hypot(12.0, -4.0), abs=0.05)
    assert aggregated_upper["total_deviation"] == pytest.approx(upper_section["total_deviation"], abs=1e-6)


def test_verticality_normatives_do_not_reuse_straightness_summary():
    service = CalculationService()
    result = service._check_verticality_normatives(
        {
            "valid": True,
            "straightness_summary": {"passed": 99, "failed": 0, "violations": []},
            "centers": pd.DataFrame([{"z": 10.0, "deviation": 0.02}]),
        }
    )

    assert result["passed"] == 0
    assert result["failed"] == 1
    assert result["violations"]


def test_verticality_normatives_preserve_section_metadata_from_canonical_sections():
    service = CalculationService()
    result = service._check_verticality_normatives(
        {
            "valid": True,
            "angular_verticality": {
                "sections": [
                    {
                        "section_num": 7,
                        "part_num": 3,
                        "height": 10.0,
                        "deviation_x": 12.0,
                        "deviation_y": 16.0,
                        "total_deviation": 20.0,
                    }
                ]
            },
            "centers": pd.DataFrame([{"z": 10.0, "deviation": 0.0}]),
        }
    )

    assert result["passed"] == 0
    assert result["failed"] == 1
    assert result["violations"] == [
        {
            "belt_height": 10.0,
            "deviation": 0.02,
            "normative": 0.01,
            "section_num": 7,
            "part_num": 3,
        }
    ]


def test_verticality_widget_get_table_data_reads_actual_columns():
    _ensure_app()
    widget = VerticalityWidget()
    widget.deviation_table.setRowCount(1)
    values = ["2", "7.5", "1", "+4.00", "+5.00", "6.40", "7.50"]
    for column, value in enumerate(values):
        widget.deviation_table.setItem(0, column, QTableWidgetItem(value))

    data = widget.get_table_data()

    assert data == [
        {
            "section_num": 2,
            "height": 7.5,
            "deviation_x": 4.0,
            "deviation_y": 5.0,
            "total_deviation": 6.4,
            "deviation": 6.4,
            "tolerance": 7.5,
        }
    ]


def test_verticality_widget_get_table_data_prefers_raw_section_payload_over_scaled_table_text():
    _ensure_app()
    widget = VerticalityWidget()
    section_data = [
        {
            "section_num": 1,
            "height": 7.5,
            "deviation_x": 8.0,
            "deviation_y": -6.0,
            "total_deviation": 10.0,
        }
    ]

    widget._current_section_data = widget._make_table_payload(section_data)
    widget._fill_deviation_table(section_data, divisor=2.0)

    assert widget.deviation_table.item(0, 3).text() == "+4.00"
    assert widget.deviation_table.item(0, 4).text() == "-3.00"
    assert widget.deviation_table.item(0, 5).text() == "+5.00"

    data = widget.get_table_data()
    data[0]["deviation_x"] = 999.0

    assert widget.get_table_data() == [
        {
            "section_num": 1,
            "height": 7.5,
            "deviation_x": 8.0,
            "deviation_y": -6.0,
            "total_deviation": 10.0,
            "deviation": 10.0,
            "tolerance": 7.5,
        }
    ]


def test_verticality_widget_prefers_processed_canonical_sections_without_rebuilding_centers():
    _ensure_app()
    widget = VerticalityWidget()
    widget.processed_data = {
        "angular_verticality": {
            "sections": [
                {
                    "section_num": 9,
                    "part_num": 2,
                    "height": 6.0,
                    "deviation_x": 14.0,
                    "deviation_y": -2.0,
                    "total_deviation": 14.1421356237,
                    "source": "processed_fallback",
                }
            ]
        },
        "centers": pd.DataFrame([{"z": 6.0, "x": 0.0, "y": 0.0, "deviation": 0.001}]),
    }

    assert widget._calculate_section_deviations() == [
        {
            "section_num": 9,
            "part_num": 2,
            "height": 6.0,
            "deviation_x": 14.0,
            "deviation_y": -2.0,
            "total_deviation": 14.1421356237,
            "deviation": 14.1421356237,
            "tolerance": 6.0,
            "points_count": None,
            "source": "processed_fallback",
            "basis_complete": None,
        }
    ]


def test_angular_verticality_requires_two_stations_before_section_aggregation():
    widget, raw_data, processed_results, editor = _build_single_station_fixture()
    payload = widget.get_angular_measurements()

    assert payload["x"]
    assert payload["sections"]
    assert payload["complete"] is False
    assert payload["basis"]["has_required_stations"] is False
    upper_payload_section = next(section for section in payload["sections"] if section["section_num"] == 1)
    assert upper_payload_section["source"] == "processed"
    assert EnhancedReportGenerator._aggregate_angular_measurements_by_sections(payload)[1]["total_deviation"] == pytest.approx(
        12.6491106407,
        abs=0.05,
    )

    prompted = {"calls": []}

    def _fake_ensure_complete(interactive=True):
        prompted["calls"].append(interactive)
        return False

    widget.ensure_complete_angular_station_basis = _fake_ensure_complete

    verticality_widget = VerticalityWidget()
    verticality_widget.data = raw_data
    verticality_widget.processed_data = processed_results
    verticality_widget.editor_3d = editor
    verticality_widget.data_table_widget = widget

    vertical_sections = verticality_widget._calculate_section_deviations()
    upper_section = next(section for section in vertical_sections if section["section_num"] == 1)

    assert prompted["calls"] == [False]
    assert upper_section["total_deviation"] == pytest.approx(12.6491106407, abs=0.05)


def test_single_station_payload_falls_back_to_current_sections_without_processed_results():
    widget, _, _, _ = _build_single_station_fixture()
    widget.set_processed_results(None)

    payload = widget.get_angular_measurements()

    assert payload["x"]
    assert payload["basis"]["has_required_stations"] is False
    assert payload["complete"] is False
    assert [section["section_num"] for section in payload["sections"]] == [0, 1]
    assert {section["source"] for section in payload["sections"]} == {"sections"}


def test_single_station_payload_uses_robust_section_center_from_current_points():
    widget, _, _ = _build_single_station_generated_center_fixture()

    payload = widget.get_angular_measurements()

    upper_section = next(section for section in payload["sections"] if section["section_num"] == 1)
    upper_rows = [row for row in payload["x"] if row.get("section_num") == 1]

    assert upper_section["center_xy"] == pytest.approx((0.0, 0.0), abs=1e-9)
    assert upper_rows
    assert all(float(row["reference_center_sec"]) == pytest.approx(0.0, abs=1e-9) for row in upper_rows)


def test_verticality_widget_falls_back_to_processed_centers_when_table_payload_is_incomplete():
    data_table_widget, raw_data, processed_results, editor = _build_real_example_fixture(
        attach_processed_to_table=False,
    )

    verticality_widget = VerticalityWidget()
    verticality_widget.data = raw_data
    verticality_widget.processed_data = processed_results
    verticality_widget.editor_3d = editor
    verticality_widget.data_table_widget = data_table_widget

    vertical_sections = verticality_widget._calculate_section_deviations()
    actual_totals = [section["total_deviation"] for section in vertical_sections]
    expected_totals = [float(value) * 1000.0 for value in processed_results["centers"]["deviation"].tolist()]

    assert actual_totals == pytest.approx(expected_totals, abs=0.05)
    assert actual_totals[0] == pytest.approx(0.0, abs=0.05)
    assert max(actual_totals) > 90.0


def test_verticality_widget_fallback_prefers_section_center_fields_over_point_mean():
    _, raw_data, editor = _build_single_station_generated_center_fixture()

    verticality_widget = VerticalityWidget()
    verticality_widget.data = raw_data
    verticality_widget.processed_data = None
    verticality_widget.editor_3d = editor
    verticality_widget.data_table_widget = None

    vertical_sections = verticality_widget._calculate_section_deviations()
    upper_section = next(section for section in vertical_sections if section["section_num"] == 1)

    assert upper_section["center_x"] == pytest.approx(0.0, abs=1e-9)
    assert upper_section["center_y"] == pytest.approx(0.0, abs=1e-9)


def test_real_example_with_fictive_station_keeps_baseline_verticality_from_processed_centers():
    widget, raw_data, processed_results, editor = _build_real_example_fixture(
        add_second_station=True,
        attach_processed_to_table=True,
    )
    payload = widget.get_angular_measurements()

    assert payload["basis"]["has_required_stations"] is True
    assert payload["basis"]["has_authoritative_stations"] is False
    assert payload["basis"]["secondary_station_is_synthetic"] is True
    assert payload["complete"] is False

    payload_totals = [section["total_deviation"] for section in payload["sections"]]
    expected_totals = [float(value) * 1000.0 for value in processed_results["centers"]["deviation"].tolist()]
    assert payload_totals == pytest.approx(expected_totals, abs=0.05)
    assert payload_totals[0] == pytest.approx(0.0, abs=0.05)
    assert max(payload_totals) > 90.0
    assert {section["source"] for section in payload["sections"]} == {"processed"}

    verticality_widget = VerticalityWidget()
    verticality_widget.data = raw_data
    verticality_widget.processed_data = processed_results
    verticality_widget.editor_3d = editor
    verticality_widget.data_table_widget = widget
    vertical_sections = verticality_widget._calculate_section_deviations()

    assert [section["total_deviation"] for section in vertical_sections] == pytest.approx(expected_totals, abs=0.05)


def test_real_example_with_synthetic_station_still_has_rows_but_uses_station_sections_only_without_processed_results():
    widget, _, _, _ = _build_real_example_fixture(
        add_second_station=True,
        attach_processed_to_table=False,
    )
    payload = widget.get_angular_measurements()

    assert payload["x"]
    assert payload["y"]
    assert payload["basis"]["has_required_stations"] is True
    assert payload["basis"]["has_authoritative_stations"] is False
    assert payload["complete"] is False
    assert {section["source"] for section in payload["sections"]} == {"stations"}


def test_real_example_station_rows_follow_baseline_shifts_in_station_axes():
    widget, raw_data, _, editor = _build_real_example_fixture(
        add_second_station=True,
        attach_processed_to_table=False,
    )
    payload = widget.get_angular_measurements()

    rows_x = [row for idx, row in enumerate(payload["x"]) if idx % 2 == 0]
    rows_y = [row for idx, row in enumerate(payload["y"]) if idx % 2 == 0]

    assert max(abs(float(row["delta_mm"])) for row in rows_x) < 10.0
    assert max(abs(float(row["delta_mm"])) for row in rows_y) > 90.0

    verticality_widget = VerticalityWidget()
    verticality_widget.data = raw_data
    verticality_widget.processed_data = None
    verticality_widget.editor_3d = editor
    verticality_widget.data_table_widget = widget
    vertical_sections = verticality_widget._calculate_section_deviations()
    by_section = {section["section_num"]: section for section in vertical_sections}

    for row in rows_x:
        assert by_section[row["section_num"]]["deviation_x"] == pytest.approx(float(row["delta_mm"]), abs=0.05)
    for row in rows_y:
        assert by_section[row["section_num"]]["deviation_y"] == pytest.approx(float(row["delta_mm"]), abs=0.05)


def test_real_example_straightness_widget_uses_readable_labels_and_clustered_heights():
    _, raw_data, processed_results, _ = _build_real_example_fixture(
        add_second_station=False,
        attach_processed_to_table=True,
    )

    straightness_widget = StraightnessWidget()
    straightness_widget.set_data(raw_data, processed_results)

    headers = [
        straightness_widget.deviation_table.horizontalHeaderItem(column).text()
        for column in range(straightness_widget.deviation_table.columnCount())
    ]
    heights = [
        straightness_widget.deviation_table.item(row, 0).text()
        for row in range(straightness_widget.deviation_table.rowCount())
    ]

    assert straightness_widget.info_label.text() == "Графики построены для 4 поясов"
    assert straightness_widget.graph_tabs.tabText(0) == "Все пояса"
    assert headers == [
        "Высота, м",
        "Пояс 1",
        "Пояс 2",
        "Пояс 3",
        "Пояс 4",
        "Допустимое, мм",
    ]
    assert heights == ["2.5", "10.0", "17.5", "25.0", "30.3"]
    assert straightness_widget.deviation_table.item(0, 5).text().startswith("±")


def test_verticality_plot_uses_raw_section_deviations():
    widget, raw_data, _, editor = _build_real_example_fixture(
        add_second_station=True,
        attach_processed_to_table=False,
    )

    verticality_widget = VerticalityWidget()
    verticality_widget.data = raw_data
    verticality_widget.processed_data = None
    verticality_widget.editor_3d = editor
    verticality_widget.data_table_widget = widget
    section_data = verticality_widget._calculate_section_deviations()
    expected_sections = sorted(section_data, key=lambda item: float(item.get("height", 0.0) or 0.0))
    expected_heights = [float(item["height"]) for item in expected_sections]
    expected_dev_x = [float(item["deviation_x"]) for item in expected_sections]
    expected_dev_y = [float(item["deviation_y"]) for item in expected_sections]

    verticality_widget.figure.clear()
    ax_x = verticality_widget.figure.add_subplot(1, 2, 1)
    verticality_widget._plot_verticality_profile(ax_x, section_data, component='x')
    profile_x = next(line for line in ax_x.get_lines() if line.get_label() == 'Отклонение по X')
    assert list(profile_x.get_xdata()) == pytest.approx(expected_dev_x, abs=1e-9)
    assert list(profile_x.get_ydata()) == pytest.approx(expected_heights, abs=1e-9)

    ax_y = verticality_widget.figure.add_subplot(1, 2, 2)
    verticality_widget._plot_verticality_profile(ax_y, section_data, component='y')
    profile_y = next(line for line in ax_y.get_lines() if line.get_label() == 'Отклонение по Y')
    assert list(profile_y.get_xdata()) == pytest.approx(expected_dev_y, abs=1e-9)
    assert list(profile_y.get_ydata()) == pytest.approx(expected_heights, abs=1e-9)


def test_journal_verticality_and_report_use_same_section_payload():
    widget, raw_data, processed_results, editor = _build_fixture()
    payload = widget.get_angular_measurements()

    verticality_widget = VerticalityWidget()
    verticality_widget.data = raw_data
    verticality_widget.processed_data = processed_results
    verticality_widget.editor_3d = editor
    verticality_widget.data_table_widget = widget
    vertical_sections = verticality_widget._calculate_section_deviations()
    vertical_upper = next(section for section in vertical_sections if section["section_num"] == 1)

    report_stub = type("ReportStub", (), {})()
    report_stub.data_table_widget = widget
    report_stub._collect_angular_measurements = MethodType(ReportWidget._collect_angular_measurements, report_stub)
    report_sections = EnhancedReportGenerator._aggregate_angular_measurements_by_sections(
        report_stub._collect_angular_measurements()
    )
    report_upper = next(section for section in report_sections if section["section_num"] == 1)

    assert vertical_upper["total_deviation"] == pytest.approx(payload["sections"][1]["total_deviation"], abs=1e-6)
    assert report_upper["total_deviation"] == pytest.approx(vertical_upper["total_deviation"], abs=1e-6)


def test_angular_sections_use_current_tower_points_instead_of_stale_section_snapshot():
    loaded = load_survey_data(str(EXAMPLES_DIR / "острогожск_РРС-11.jxl"))
    raw_data = loaded.data.copy()
    tower_points = raw_data.loc[~raw_data["is_station"]].sort_values("z").reset_index(drop=True)

    clean_sections = []
    stale_sections = []
    for section_num in range(5):
        section_points = tower_points.iloc[section_num * 4:(section_num + 1) * 4].copy()
        clean_points = [
            (float(row.x), float(row.y), float(row.z))
            for row in section_points.itertuples()
        ]
        stale_points = [
            (
                float(row.x) + (1.0 if section_num > 0 else 0.0),
                float(row.y) - (0.5 if section_num > 0 else 0.0),
                float(row.z),
            )
            for row in section_points.itertuples()
        ]
        section_height = float(section_points["z"].mean())
        clean_sections.append({
            "name": str(section_num),
            "height": section_height,
            "points": clean_points,
            "belt_nums": [1, 2, 3, 4],
            "section_num": section_num,
        })
        stale_sections.append({
            "name": str(section_num),
            "height": section_height,
            "points": stale_points,
            "belt_nums": [1, 2, 3, 4],
            "section_num": section_num,
        })

    clean_editor = _EditorStub(clean_sections)
    clean_widget = DataTableWidget(clean_editor)
    clean_widget.set_data(raw_data)
    clean_payload = clean_widget.get_angular_measurements()

    stale_editor = _EditorStub(stale_sections)
    stale_widget = DataTableWidget(stale_editor)
    stale_widget.set_data(raw_data)
    stale_payload = stale_widget.get_angular_measurements()

    clean_upper_rows = [row for row in clean_payload["x"] if row.get("section_num") == 1]
    stale_upper_rows = [row for row in stale_payload["x"] if row.get("section_num") == 1]

    assert clean_upper_rows
    assert stale_upper_rows
    assert stale_upper_rows[0]["center_str"] == clean_upper_rows[0]["center_str"]
    assert stale_upper_rows[0]["delta_mm"] == pytest.approx(clean_upper_rows[0]["delta_mm"], abs=1e-6)
    assert stale_upper_rows[1]["delta_mm"] == pytest.approx(clean_upper_rows[1]["delta_mm"], abs=1e-6)


def test_angular_sections_match_current_points_when_snapshot_height_is_stale():
    widget, _, editor = _build_single_station_generated_center_fixture()
    editor.section_data[1]["height"] = 20.0
    widget.set_processed_results(None)

    payload = widget.get_angular_measurements()

    upper_rows = [row for row in payload["x"] if row.get("section_num") == 1]
    upper_section = next(section for section in payload["sections"] if section["section_num"] == 1)

    assert payload["basis"]["has_required_stations"] is False
    assert upper_rows
    assert upper_section["height"] == pytest.approx(10.0, abs=1e-9)
    assert upper_section["center_xy"] == pytest.approx((0.0, 0.0), abs=1e-9)


def test_duplicate_station_geometry_is_not_treated_as_complete_angular_basis():
    widget, raw_data, _, editor = _build_single_station_fixture()

    station_row = raw_data.loc[raw_data["is_station"]].iloc[0]
    duplicate_station = pd.DataFrame(
        [
            {
                "name": "ST2_DUP",
                "x": float(station_row["x"]),
                "y": float(station_row["y"]),
                "z": float(station_row["z"]),
                "is_station": True,
                "station_role": "secondary",
                "belt": None,
                "point_index": int(raw_data["point_index"].max()) + 1,
            }
        ]
    )

    duplicated = _concat_without_all_na_warning(raw_data, duplicate_station)
    widget = DataTableWidget(editor)
    widget.set_data(duplicated)
    payload = widget.get_angular_measurements()

    assert widget.has_complete_angular_station_basis() is False
    assert payload["basis"]["has_required_stations"] is False
    assert payload["sections"]
    assert {section["source"] for section in payload["sections"]} == {"sections"}
    assert payload["complete"] is False


def test_add_station_dialog_rejects_duplicate_of_primary_station(monkeypatch):
    widget, raw_data, _, _ = _build_single_station_fixture()

    tower_points = raw_data.loc[~raw_data["is_station"]]
    station_row = raw_data.loc[raw_data["is_station"]].iloc[0]
    existing_distance = math.hypot(
        float(station_row["x"]) - float(tower_points["x"].mean()),
        float(station_row["y"]) - float(tower_points["y"].mean()),
    )

    monkeypatch.setattr(AddStationDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(
        AddStationDialog,
        "get_values",
        lambda self: {"position": "left", "angle_deg": 0.0, "distance": existing_distance},
    )
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)

    assert widget.show_add_station_dialog() is False
    assert int(widget.original_data["is_station"].sum()) == 1
    assert widget.has_complete_angular_station_basis() is False


def test_add_station_dialog_marks_new_station_as_synthetic(monkeypatch):
    widget, raw_data, _, _ = _build_single_station_fixture()

    tower_points = raw_data.loc[~raw_data["is_station"]]
    station_row = raw_data.loc[raw_data["is_station"]].iloc[0]
    existing_distance = math.hypot(
        float(station_row["x"]) - float(tower_points["x"].mean()),
        float(station_row["y"]) - float(tower_points["y"].mean()),
    )

    monkeypatch.setattr(AddStationDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(
        AddStationDialog,
        "get_values",
        lambda self: {"position": "left", "angle_deg": 90.0, "distance": existing_distance},
    )
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)

    assert widget.show_add_station_dialog() is True
    stations = widget.original_data.loc[widget.original_data["is_station"]].copy()
    synthetic_secondary = stations.loc[stations["station_role"] == "secondary"].iloc[0]
    assert synthetic_secondary["station_origin"] == "synthetic"


def test_processed_center_calculation_is_unchanged_by_added_second_station():
    _, raw_data, _, _ = _build_single_station_fixture()

    base_results = process_tower_data(raw_data, use_assigned_belts=True, use_cache=False)

    tower_points = raw_data.loc[~raw_data["is_station"]]
    station_row = raw_data.loc[raw_data["is_station"]].iloc[0]
    center_x = float(tower_points["x"].mean())
    center_y = float(tower_points["y"].mean())
    base_dx = float(station_row["x"]) - center_x
    base_dy = float(station_row["y"]) - center_y
    base_distance = math.hypot(base_dx, base_dy)
    base_norm = max(base_distance, 1e-9)
    orth_x = base_dy / base_norm
    orth_y = -base_dx / base_norm

    second_station = pd.DataFrame(
        [
            {
                "name": "ST2",
                "x": center_x + orth_x * base_distance,
                "y": center_y + orth_y * base_distance,
                "z": float(station_row["z"]),
                "is_station": True,
                "station_role": "secondary",
                "belt": None,
                "point_index": int(raw_data["point_index"].max()) + 1,
            }
        ]
    )
    augmented = _concat_without_all_na_warning(raw_data, second_station)
    augmented_results = process_tower_data(augmented, use_assigned_belts=True, use_cache=False)

    pd.testing.assert_frame_equal(
        base_results["centers"][["z", "deviation_x", "deviation_y", "deviation"]].reset_index(drop=True),
        augmented_results["centers"][["z", "deviation_x", "deviation_y", "deviation"]].reset_index(drop=True),
        check_exact=False,
        atol=1e-12,
        rtol=0.0,
    )
