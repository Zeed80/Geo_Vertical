import json
from contextlib import contextmanager
from types import MethodType

import numpy as np
import pandas as pd
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication

from core.section_operations import get_section_lines
from gui.data_table import DataTableWidget
from gui.point_editor_3d import PointEditor3DWidget

_APP = QApplication.instance() or QApplication([])


def test_normalize_text_color_converts_normalized_rgba_to_opaque_qcolor():
    color = PointEditor3DWidget._normalize_text_color((0.0, 0.0, 0.0, 1.0))

    assert isinstance(color, QColor)
    assert color.getRgb() == (0, 0, 0, 255)


def test_normalize_text_color_preserves_8bit_rgba_values():
    color = PointEditor3DWidget._normalize_text_color((10, 20, 30, 40))

    assert isinstance(color, QColor)
    assert color.getRgb() == (10, 20, 30, 40)


def test_build_point_label_uses_only_name_without_number():
    row = pd.Series({'name': 'P12', 'point_index': 42})

    label = PointEditor3DWidget._build_point_label(row, dataframe_idx=7)

    assert label == 'P12'


def test_build_point_label_falls_back_when_name_missing():
    row = pd.Series({'name': None, 'point_index': 42})

    label = PointEditor3DWidget._build_point_label(row, dataframe_idx=7)

    assert label == 'Point 7'


def test_compute_point_label_position_moves_label_outward_and_up():
    position = PointEditor3DWidget._compute_point_label_position(
        point_xyz=np.array([2.0, 0.0, 5.0]),
        center_xy=np.array([0.0, 0.0]),
        lateral_offset=0.4,
        vertical_offset=0.3,
    )

    assert position == (2.4, 0.0, 5.3)


def test_compute_belt_label_position_uses_bottom_point_and_moves_down():
    position = PointEditor3DWidget._compute_belt_label_position(
        line_points=np.array([[2.0, 0.0, 1.0], [2.0, 0.0, 6.0]]),
        center_xy=np.array([0.0, 0.0]),
        lateral_offset=0.4,
        vertical_drop=0.5,
    )

    assert position == (2.4, 0.0, 0.5)


def test_suggest_new_section_height_supports_top_and_bottom_modes():
    heights = [2.5, 10.0, 17.5, 25.0]

    assert PointEditor3DWidget._suggest_new_section_height(heights, 'top') > max(heights)
    assert PointEditor3DWidget._suggest_new_section_height(heights, 'bottom') < min(heights)


class _SignalStub:
    def __init__(self):
        self.calls = 0

    def emit(self, *args, **kwargs):
        self.calls += 1


class _LabelStub:
    def __init__(self):
        self.text = ''

    def setText(self, text):
        self.text = text


class _IndexManagerStub:
    def __init__(self):
        self.last_data = None

    def set_data(self, data):
        self.last_data = data.copy(deep=True)


class _EditorAddSectionStub:
    def __init__(self, data: pd.DataFrame, section_data: list[dict]):
        self.data = data.copy(deep=True)
        self.section_data = [dict(section) for section in section_data]
        self.point_index_counter = 0
        self.index_manager = _IndexManagerStub()
        self.info_label = _LabelStub()
        self.data_changed = _SignalStub()
        self.show_central_axis = False
        self._ensure_point_indices = MethodType(PointEditor3DWidget._ensure_point_indices, self)
        self._get_next_point_index = MethodType(PointEditor3DWidget._get_next_point_index, self)
        self._build_is_station_mask = PointEditor3DWidget._build_is_station_mask
        self._validate_new_section_height = PointEditor3DWidget._validate_new_section_height
        self._current_section_heights = MethodType(PointEditor3DWidget._current_section_heights, self)
        self._resolve_section_track_column = PointEditor3DWidget._resolve_section_track_column
        self._canonicalize_section_mutation_data = MethodType(PointEditor3DWidget._canonicalize_section_mutation_data, self)
        self._resolve_section_levels = MethodType(PointEditor3DWidget._resolve_section_levels, self)
        self._rebuild_section_data = MethodType(PointEditor3DWidget._rebuild_section_data, self)
        self._refresh_after_section_mutation = MethodType(PointEditor3DWidget._refresh_after_section_mutation, self)

    @contextmanager
    def undo_transaction(self, _description):
        class _Tx:
            committed = False

            def commit(self_inner):
                self_inner.committed = True

        yield _Tx()

    def update_3d_view(self):
        return None

    def set_section_lines(self, section_data):
        self.section_data = [dict(section) for section in section_data]

    def update_section_lines(self):
        return None

    def update_all_indices(self):
        return None

    def update_central_axis(self):
        return None


def test_add_section_rebuilds_section_data_and_preserves_point_schema():
    rows = []
    point_index = 1
    for z in (0.0, 10.0):
        for belt, (x, y) in enumerate(((0.0, 0.0), (2.0, 0.0), (2.0, 2.0), (0.0, 2.0)), start=1):
            rows.append(
                {
                    'name': f'P{point_index}',
                    'x': x + z * 0.01,
                    'y': y + z * 0.02,
                    'z': z,
                    'belt': belt,
                    'point_index': point_index,
                    'is_station': False,
                    'is_auxiliary': False,
                    'is_control': False,
                    'tower_part': 1,
                    'segment': 1,
                    'tower_part_memberships': json.dumps([1], ensure_ascii=False),
                    'is_part_boundary': False,
                }
            )
            point_index += 1

    data = pd.DataFrame(rows)
    section_data = get_section_lines(data, [0.0, 10.0], height_tolerance=0.3)
    editor = _EditorAddSectionStub(data, section_data)

    PointEditor3DWidget._add_section_impl(editor, 20.0, tower_part=1, placement='top')

    new_rows = editor.data[np.isclose(editor.data['z'], 20.0)]
    assert len(new_rows) == 4
    assert set(new_rows['belt'].astype(int)) == {1, 2, 3, 4}
    assert set(new_rows['tower_part'].astype(int)) == {1}
    assert set(new_rows['tower_part_memberships']) == {json.dumps([1], ensure_ascii=False)}
    assert not new_rows['is_station'].any()
    assert not new_rows['is_auxiliary'].any()
    assert not new_rows['is_control'].any()
    assert any(abs(section['height'] - 20.0) < 1e-6 and len(section['points']) == 4 for section in editor.section_data)
    assert editor.data_changed.calls == 1


def test_add_section_reindexes_height_levels_and_marks_generated_metadata():
    rows = []
    point_index = 1
    for height_level, z_value in enumerate((0.0, 10.0), start=1):
        for track_num, (x_value, y_value) in enumerate(((0.0, 0.0), (2.0, 0.0), (2.0, 2.0), (0.0, 2.0)), start=1):
            rows.append(
                {
                    'name': f'P{point_index}',
                    'x': x_value + z_value * 0.01,
                    'y': y_value + z_value * 0.02,
                    'z': z_value,
                    'belt': track_num,
                    'face_track': track_num,
                    'part_belt': track_num,
                    'part_face_track': track_num,
                    'faces': 4,
                    'height_level': height_level,
                    'point_index': point_index,
                    'is_station': False,
                    'is_auxiliary': False,
                    'is_control': False,
                    'is_generated': False,
                    'generated_by': '',
                    'tower_part': 1,
                    'segment': 1,
                    'tower_part_memberships': json.dumps([1], ensure_ascii=False),
                    'is_part_boundary': False,
                }
            )
            point_index += 1

    data = pd.DataFrame(rows)
    section_data = get_section_lines(data, [0.0, 10.0], height_tolerance=0.3)
    editor = _EditorAddSectionStub(data, section_data)

    PointEditor3DWidget._add_section_impl(editor, 5.0, tower_part=1, placement='absolute')

    new_rows = editor.data[np.isclose(editor.data['z'], 5.0)].copy()
    assert len(new_rows) == 4
    assert set(new_rows['generated_by']) == {'section_generation'}
    assert set(new_rows['is_generated'].astype(bool)) == {True}
    assert set(new_rows['is_section_generated'].astype(bool)) == {True}

    level_by_height = (
        editor.data.groupby(editor.data['z'].round(6))['height_level']
        .agg(lambda values: sorted(set(int(value) for value in values)))
        .to_dict()
    )
    assert level_by_height == {0.0: [1], 5.0: [2], 10.0: [3]}


class _EditorDeleteSectionStub:
    def __init__(self, data: pd.DataFrame, section_data: list[dict]):
        self.data = data.copy(deep=True)
        self.section_data = [dict(section) for section in section_data]
        self.index_manager = _IndexManagerStub()
        self.info_label = _LabelStub()
        self.data_changed = _SignalStub()
        self.show_central_axis = False
        self.section_deletion_mode = True
        self._current_section_heights = MethodType(PointEditor3DWidget._current_section_heights, self)
        self._canonicalize_section_mutation_data = MethodType(PointEditor3DWidget._canonicalize_section_mutation_data, self)
        self._resolve_section_levels = MethodType(PointEditor3DWidget._resolve_section_levels, self)
        self._rebuild_section_data = MethodType(PointEditor3DWidget._rebuild_section_data, self)
        self._refresh_after_section_mutation = MethodType(PointEditor3DWidget._refresh_after_section_mutation, self)

    @contextmanager
    def undo_transaction(self, _description):
        class _Tx:
            committed = False

            def commit(self_inner):
                self_inner.committed = True

        yield _Tx()

    def set_section_lines(self, section_data):
        self.section_data = [dict(section) for section in section_data]

    def update_3d_view(self):
        return None

    def update_all_indices(self):
        return None

    def update_section_lines(self):
        return None

    def update_central_axis(self):
        return None


def test_delete_section_removes_only_generated_points():
    rows = []
    point_index = 1
    for z in (0.0, 10.0):
        for belt, (x, y) in enumerate(((0.0, 0.0), (2.0, 0.0), (2.0, 2.0), (0.0, 2.0)), start=1):
            rows.append(
                {
                    'name': f'P{point_index}',
                    'x': x,
                    'y': y,
                    'z': z,
                    'belt': belt,
                    'point_index': point_index,
                    'is_station': False,
                    'is_section_generated': False,
                }
            )
            point_index += 1

    for belt, (x, y) in enumerate(((0.0, 0.0), (2.0, 0.0), (2.0, 2.0), (0.0, 2.0)), start=1):
        rows.append(
            {
                'name': f'S5_B{belt}',
                'x': x + 0.5,
                'y': y + 0.5,
                'z': 5.0,
                'belt': belt,
                'point_index': point_index,
                'is_station': False,
                'is_section_generated': True,
            }
        )
        point_index += 1

    data = pd.DataFrame(rows)
    section_data = get_section_lines(data, [0.0, 5.0, 10.0], height_tolerance=0.3)
    editor = _EditorDeleteSectionStub(data, section_data)

    PointEditor3DWidget.delete_section(editor, 5.0)

    assert editor.section_deletion_mode is False
    assert editor.data_changed.calls == 1
    assert len(editor.data) == 8
    assert not editor.data['is_section_generated'].fillna(False).any()
    assert [round(section['height'], 3) for section in editor.section_data] == [0.0, 10.0]


class _EditorProjectSectionStub:
    def __init__(self, data: pd.DataFrame, section_data: list[dict]):
        self.data = data.copy(deep=True)
        self.section_data = [dict(section) for section in section_data]
        self.index_manager = _IndexManagerStub()
        self.info_label = _LabelStub()
        self.data_changed = _SignalStub()
        self.point_modified = _SignalStub()
        self.show_central_axis = False
        self.pending_point_idx = 0
        self.section_selection_mode = True
        self._build_is_station_mask = PointEditor3DWidget._build_is_station_mask
        self._legacy_project_point_to_section_level = MethodType(
            PointEditor3DWidget._legacy_project_point_to_section_level,
            self,
        )
        self._current_section_heights = MethodType(PointEditor3DWidget._current_section_heights, self)
        self._resolve_section_levels = MethodType(PointEditor3DWidget._resolve_section_levels, self)
        self._rebuild_section_data = MethodType(PointEditor3DWidget._rebuild_section_data, self)

    @contextmanager
    def undo_transaction(self, _description):
        class _Tx:
            committed = False

            def commit(self_inner):
                self_inner.committed = True

        yield _Tx()

    def set_section_lines(self, section_data):
        self.section_data = [dict(section) for section in section_data]

    def update_3d_view(self):
        return None

    def update_all_indices(self):
        return None

    def update_section_lines(self):
        return None

    def update_central_axis(self):
        return None


def test_project_point_to_section_level_does_not_restore_removed_empty_section():
    rows = [
        {
            'name': 'P1',
            'x': 0.0,
            'y': 0.0,
            'z': 5.0,
            'belt': 1,
            'point_index': 1,
            'is_station': False,
            'is_section_generated': False,
        },
        {
            'name': 'P2',
            'x': 0.0,
            'y': 0.0,
            'z': 10.0,
            'belt': 1,
            'point_index': 2,
            'is_station': False,
            'is_section_generated': False,
        },
    ]
    for point_index, belt in enumerate((2, 3, 4), start=3):
        rows.append(
            {
                'name': f'P{point_index}',
                'x': float(belt),
                'y': 0.0,
                'z': 10.0,
                'belt': belt,
                'point_index': point_index,
                'is_station': False,
                'is_section_generated': False,
            }
        )
    for point_index, belt in enumerate((2, 3, 4), start=6):
        rows.append(
            {
                'name': f'S5_B{belt}',
                'x': float(belt) + 0.5,
                'y': 0.5,
                'z': 5.0,
                'belt': belt,
                'point_index': point_index,
                'is_station': False,
                'is_section_generated': True,
            }
        )

    data = pd.DataFrame(rows)
    section_data = get_section_lines(data, [5.0, 10.0], height_tolerance=0.3)
    editor = _EditorProjectSectionStub(data, section_data)

    PointEditor3DWidget.project_point_to_section_level(editor, 10.0)

    assert editor.section_selection_mode is False
    assert editor.pending_point_idx is None
    assert editor.point_modified.calls == 1
    assert editor.data_changed.calls >= 1
    assert (editor.data['z'] == 5.0).sum() == 0
    assert [round(section['height'], 3) for section in editor.section_data] == [10.0]


class _DataTableEditorStub:
    def __init__(self, section_data):
        self.section_data = section_data
        self.active_station_index = None

    def set_active_station_index(self, value):
        self.active_station_index = value


class _GLViewAxisStub:
    def __init__(self):
        self.added_items = []
        self.removed_items = []

    def addItem(self, item):
        self.added_items.append(item)

    def removeItem(self, item):
        self.removed_items.append(item)


class _AxisLineStub:
    def __init__(self, pos, color, width, antialias):
        self.pos = np.asarray(pos, dtype=float)
        self.color = color
        self.width = width
        self.antialias = antialias


class _EditorCentralAxisStub:
    def __init__(self, section_data):
        self.section_data = [dict(section) for section in section_data]
        self.show_central_axis = True
        self.central_axis_line = None
        self.glview = _GLViewAxisStub()


def test_update_central_axis_uses_section_centers_for_axis_fit(monkeypatch):
    monkeypatch.setattr('gui.point_editor_3d.gl.GLLinePlotItem', _AxisLineStub)

    section_data = [
        {
            'points': [(10.0, 0.0, 0.0), (10.0, 1.0, 0.0), (10.0, -1.0, 0.0)],
            'center_xy': (0.0, 0.0),
            'center_z': 0.0,
        },
        {
            'points': [(20.0, 0.0, 10.0), (20.0, 1.0, 10.0), (20.0, -1.0, 10.0)],
            'center_xy': (1.0, -0.5),
            'center_z': 10.0,
        },
        {
            'points': [(30.0, 0.0, 20.0), (30.0, 1.0, 20.0), (30.0, -1.0, 20.0)],
            'center_xy': (2.0, -1.0),
            'center_z': 20.0,
        },
    ]
    editor = _EditorCentralAxisStub(section_data)

    PointEditor3DWidget.update_central_axis(editor)

    assert editor.central_axis_line is not None
    assert len(editor.glview.added_items) == 1
    assert np.allclose(editor.central_axis_line.pos[0], [0.0, 0.0, 0.0], atol=1e-6)
    assert np.allclose(editor.central_axis_line.pos[1], [2.0, -1.0, 20.0], atol=1e-6)


def test_data_table_set_data_without_stations_still_populates_tower_and_sections():
    data = pd.DataFrame(
        [
            {'name': 'P1', 'x': 0.0, 'y': 0.0, 'z': 0.0, 'belt': 1, 'point_index': 1, 'is_station': False},
            {'name': 'P2', 'x': 1.0, 'y': 0.0, 'z': 0.0, 'belt': 2, 'point_index': 2, 'is_station': False},
            {'name': 'P3', 'x': 1.0, 'y': 1.0, 'z': 10.0, 'belt': 1, 'point_index': 3, 'is_station': False},
            {'name': 'P4', 'x': 0.0, 'y': 1.0, 'z': 10.0, 'belt': 2, 'point_index': 4, 'is_station': False},
        ]
    )
    section_data = get_section_lines(data, [0.0, 10.0], height_tolerance=0.3)
    table = DataTableWidget(editor_3d=_DataTableEditorStub(section_data))

    table.set_data(data)

    assert table.sections_table.rowCount() == len(section_data)
    assert len(table._current_tower_data) == len(data)
    assert table.tower_parts_tabs.count() == 1
    part_table = table.tower_parts_tabs.widget(0)
    assert part_table.rowCount() == len(data)


def test_data_table_set_data_does_not_fail_when_itemchanged_is_already_disconnected():
    data = pd.DataFrame(
        [
            {'name': 'P1', 'x': 0.0, 'y': 0.0, 'z': 0.0, 'belt': 1, 'point_index': 1, 'is_station': False},
            {'name': 'P2', 'x': 1.0, 'y': 0.0, 'z': 10.0, 'belt': 2, 'point_index': 2, 'is_station': False},
        ]
    )
    table = DataTableWidget(editor_3d=_DataTableEditorStub([]))

    table.on_tower_mode_toggled(True)
    table.set_data(data)

    assert len(table._current_tower_data) == len(data)


def test_data_table_sections_table_uses_section_center_fields():
    section_data = [
        {
            'height': 10.0,
            'points': [(10.0, 10.0, 10.0), (12.0, 10.0, 10.0), (12.0, 12.0, 10.0), (10.0, 12.0, 10.0)],
            'belt_nums': [1, 2, 3, 4],
            'center_xy': (1.25, -2.5),
            'center_z': 10.5,
        }
    ]
    table = DataTableWidget(editor_3d=_DataTableEditorStub(section_data))

    table.update_sections_table()

    assert table.sections_table.item(0, 4).text() == '1.250000'
    assert table.sections_table.item(0, 5).text() == '-2.500000'
    assert table.sections_table.item(0, 6).text() == '10.500'
