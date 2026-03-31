"""Тесты для core.section_operations — работа с секциями башни."""

import pandas as pd
import pytest

from core.section_operations import (
    _resolve_requested_section_entries,
    add_missing_points_for_sections,
    find_section_levels,
    get_section_lines,
)


def _make_tower_df(rows):
    """Создаёт DataFrame из списка dict."""
    return pd.DataFrame(rows)


# ============================================================
# find_section_levels
# ============================================================

class TestFindSectionLevels:
    def test_empty_dataframe(self):
        df = pd.DataFrame(columns=['z', 'belt'])
        assert find_section_levels(df) == []

    def test_missing_columns(self):
        df = pd.DataFrame({'x': [1, 2]})
        assert find_section_levels(df) == []

    def test_simple_three_levels(self):
        rows = []
        for belt in [1, 2, 3, 4]:
            for z in [0.0, 10.0, 20.0]:
                rows.append({'x': belt, 'y': 0, 'z': z, 'belt': belt})
        df = _make_tower_df(rows)
        levels = find_section_levels(df, height_tolerance=0.3)
        assert len(levels) == 3
        assert abs(levels[0] - 0.0) < 0.5
        assert abs(levels[1] - 10.0) < 0.5
        assert abs(levels[2] - 20.0) < 0.5

    def test_close_heights_grouped(self):
        rows = [
            {'z': 10.0, 'belt': 1},
            {'z': 10.1, 'belt': 2},
            {'z': 10.2, 'belt': 3},
            {'z': 20.0, 'belt': 1},
        ]
        df = _make_tower_df(rows)
        levels = find_section_levels(df, height_tolerance=0.3)
        assert len(levels) == 2

    def test_excludes_station_points(self):
        rows = [
            {'z': 0.0, 'belt': 1, 'is_station': False},
            {'z': 0.0, 'belt': 2, 'is_station': False},
            {'z': 10.0, 'belt': 1, 'is_station': False},
            {'z': 10.0, 'belt': 2, 'is_station': False},
            {'z': -5.0, 'belt': 0, 'is_station': True},
        ]
        df = _make_tower_df(rows)
        levels = find_section_levels(df, height_tolerance=0.3)
        heights = [round(l, 1) for l in levels]
        assert -5.0 not in heights

    def test_excludes_auxiliary_and_control_points(self):
        rows = [
            {'z': 0.0, 'belt': 1},
            {'z': 10.0, 'belt': 1},
            {'z': 25.0, 'belt': 99, 'is_auxiliary': True},
            {'z': 30.0, 'belt': 98, 'is_control': True},
        ]
        df = _make_tower_df(rows)
        levels = find_section_levels(df, height_tolerance=0.3)
        heights = [round(l, 1) for l in levels]
        assert 25.0 not in heights
        assert 30.0 not in heights

    def test_partial_height_levels_are_reclustered_instead_of_dropping_zero_rows(self):
        rows = []
        corners = {
            1: (1.0, 0.0),
            2: (0.0, 1.0),
            3: (-1.0, 0.0),
            4: (0.0, -1.0),
        }
        for z_value in (0.0, 10.0):
            for belt, (x_value, y_value) in corners.items():
                rows.append(
                    {
                        'x': x_value,
                        'y': y_value,
                        'z': z_value,
                        'belt': belt,
                        'face_track': belt,
                        'height_level': 0 if belt < 4 else (1 if z_value == 0.0 else 2),
                    }
                )

        df = _make_tower_df(rows)

        levels = find_section_levels(df, height_tolerance=0.3)
        sections = get_section_lines(df, levels, height_tolerance=0.3)

        assert levels == pytest.approx([0.0, 10.0], abs=1e-9)
        assert len(sections) == 2
        assert all(section['belt_nums'] == [1, 2, 3, 4] for section in sections)
        assert all(len(section['points']) == 4 for section in sections)


# ============================================================
# add_missing_points_for_sections
# ============================================================

class TestAddMissingPointsForSections:
    def test_empty_returns_empty(self):
        df = pd.DataFrame(columns=['x', 'y', 'z', 'belt'])
        result = add_missing_points_for_sections(df, [10.0])
        assert len(result) == 0

    def test_no_levels_returns_copy(self):
        df = _make_tower_df([
            {'x': 0, 'y': 0, 'z': 10, 'belt': 1},
        ])
        result = add_missing_points_for_sections(df, [])
        assert len(result) == 1

    def test_adds_missing_point(self):
        rows = [
            {'x': 1.0, 'y': 0.0, 'z': 0.0, 'belt': 1, 'name': 'P1'},
            {'x': 1.0, 'y': 0.0, 'z': 10.0, 'belt': 1, 'name': 'P2'},
            {'x': 0.0, 'y': 1.0, 'z': 0.0, 'belt': 2, 'name': 'P3'},
            {'x': 0.0, 'y': 1.0, 'z': 10.0, 'belt': 2, 'name': 'P4'},
        ]
        df = _make_tower_df(rows)
        result = add_missing_points_for_sections(df, [5.0])
        assert len(result) > 4

    def test_existing_point_not_duplicated(self):
        rows = [
            {'x': 0, 'y': 0, 'z': 0, 'belt': 1, 'name': 'P1'},
            {'x': 0, 'y': 0, 'z': 5.0, 'belt': 1, 'name': 'P2'},
            {'x': 0, 'y': 0, 'z': 10, 'belt': 1, 'name': 'P3'},
        ]
        df = _make_tower_df(rows)
        result = add_missing_points_for_sections(df, [5.0], height_tolerance=0.3)
        assert len(result) == 3

    def test_explicit_requested_heights_do_not_collapse_when_height_levels_are_corrupted(self):
        rows = []
        corners = {
            1: (1.0, 0.0),
            2: (0.0, 1.0),
            3: (-1.0, 0.0),
            4: (0.0, -1.0),
        }
        for z_value, level in ((2.0, 1), (7.0, 1), (12.0, 2)):
            for belt, (x_value, y_value) in corners.items():
                rows.append(
                    {
                        'x': x_value,
                        'y': y_value,
                        'z': z_value,
                        'belt': belt,
                        'face_track': belt,
                        'height_level': level,
                    }
                )

        entries = _resolve_requested_section_entries(
            _make_tower_df(rows),
            [2.0, 7.0, 12.0],
            base_tolerance=0.3,
        )

        assert [round(float(entry['height']), 3) for entry in entries] == [2.0, 7.0, 12.0]


# ============================================================
# get_section_lines
# ============================================================

class TestGetSectionLines:
    def test_empty_data(self):
        df = pd.DataFrame(columns=['x', 'y', 'z', 'belt'])
        assert get_section_lines(df, [10.0]) == []

    def test_empty_levels(self):
        df = _make_tower_df([
            {'x': 0, 'y': 0, 'z': 10, 'belt': 1},
        ])
        assert get_section_lines(df, []) == []

    def test_single_level_returns_section(self):
        rows = [
            {'x': 1, 'y': 0, 'z': 10.0, 'belt': 1},
            {'x': 0, 'y': 1, 'z': 10.0, 'belt': 2},
            {'x': -1, 'y': 0, 'z': 10.0, 'belt': 3},
        ]
        df = _make_tower_df(rows)
        sections = get_section_lines(df, [10.0])
        assert len(sections) == 1
        assert len(sections[0]['points']) == 3
        assert sections[0]['height'] == 10.0

    def test_duplicate_levels_deduplicated(self):
        rows = [
            {'x': 1, 'y': 0, 'z': 10.0, 'belt': 1},
            {'x': 0, 'y': 1, 'z': 10.0, 'belt': 2},
        ]
        df = _make_tower_df(rows)
        sections = get_section_lines(df, [10.0, 10.1, 10.05], height_tolerance=0.3)
        assert len(sections) == 1

    def test_tower_part_info_preserved(self):
        rows = [
            {'x': 1, 'y': 0, 'z': 10.0, 'belt': 1, 'tower_part': 1},
            {'x': 0, 'y': 1, 'z': 10.0, 'belt': 2, 'tower_part': 1},
        ]
        df = _make_tower_df(rows)
        sections = get_section_lines(df, [10.0])
        assert len(sections) == 1
        assert sections[0].get('tower_part') == 1

    def test_ignores_non_working_points(self):
        rows = [
            {'x': 1, 'y': 0, 'z': 10.0, 'belt': 1},
            {'x': 0, 'y': 1, 'z': 10.0, 'belt': 2},
            {'x': 50, 'y': 50, 'z': 10.0, 'belt': 98, 'is_auxiliary': True},
            {'x': 60, 'y': 60, 'z': 10.0, 'belt': 99, 'is_control': True},
        ]
        df = _make_tower_df(rows)
        sections = get_section_lines(df, [10.0])
        assert len(sections) == 1
        assert sections[0]['belt_nums'] == [1, 2]
        assert len(sections[0]['points']) == 2

    def test_center_xy_prefers_measured_opposite_diagonal_over_generated_points(self):
        rows = [
            {'x': -2.0, 'y': 0.0, 'z': 10.0, 'belt': 1, 'face_track': 1, 'faces': 4, 'is_generated': False},
            {'x': 5.0, 'y': 1.0, 'z': 10.0, 'belt': 2, 'face_track': 2, 'faces': 4, 'is_generated': True, 'generated_by': 'section_generation'},
            {'x': 2.0, 'y': 0.0, 'z': 10.0, 'belt': 3, 'face_track': 3, 'faces': 4, 'is_generated': False},
            {'x': 5.0, 'y': -1.0, 'z': 10.0, 'belt': 4, 'face_track': 4, 'faces': 4, 'is_generated': True, 'generated_by': 'face_track_completion'},
        ]
        df = _make_tower_df(rows)

        sections = get_section_lines(df, [10.0])

        assert len(sections) == 1
        assert sections[0]['center_xy'] == (0.0, 0.0)
