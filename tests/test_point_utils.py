"""Тесты для core.point_utils — утилиты работы с точками башни."""


import numpy as np
import pandas as pd

from core.point_utils import (
    build_is_station_mask,
    decode_part_memberships,
    filter_points_by_part,
    row_belongs_to_part,
)

# ============================================================
# build_is_station_mask
# ============================================================

class TestBuildIsStationMask:
    def test_string_true_false(self):
        s = pd.Series(['true', 'false', 'True', 'FALSE'])
        result = build_is_station_mask(s)
        assert list(result) == [True, False, True, False]

    def test_string_yes_no(self):
        s = pd.Series(['yes', 'no', 'YES', 'No'])
        result = build_is_station_mask(s)
        assert list(result) == [True, False, True, False]

    def test_string_one_zero(self):
        s = pd.Series(['1', '0', '1'])
        result = build_is_station_mask(s)
        assert list(result) == [True, False, True]

    def test_numeric_series(self):
        s = pd.Series([1, 0, 1, 0])
        result = build_is_station_mask(s)
        assert list(result) == [True, False, True, False]

    def test_nan_treated_as_false(self):
        s = pd.Series([True, np.nan, False, np.nan])
        result = build_is_station_mask(s)
        assert list(result) == [True, False, False, False]

    def test_bool_series_passthrough(self):
        s = pd.Series([True, False, True])
        result = build_is_station_mask(s)
        assert list(result) == [True, False, True]

    def test_mixed_strings_and_nan(self):
        s = pd.Series(['true', np.nan, 'no', None])
        result = build_is_station_mask(s)
        assert list(result) == [True, False, False, False]

    def test_whitespace_trimmed(self):
        s = pd.Series([' true ', ' false '])
        result = build_is_station_mask(s)
        assert list(result) == [True, False]


# ============================================================
# decode_part_memberships
# ============================================================

class TestDecodePartMemberships:
    def test_none_returns_empty(self):
        assert decode_part_memberships(None) == []

    def test_nan_returns_empty(self):
        assert decode_part_memberships(float('nan')) == []

    def test_json_string_list(self):
        assert decode_part_memberships('[1, 2, 3]') == [1, 2, 3]

    def test_plain_list(self):
        assert decode_part_memberships([1, 2]) == [1, 2]

    def test_tuple_input(self):
        assert decode_part_memberships((3, 4)) == [3, 4]

    def test_set_input(self):
        result = decode_part_memberships({5})
        assert result == [5]

    def test_invalid_json_string(self):
        assert decode_part_memberships('not_json') == []

    def test_non_int_items_skipped(self):
        assert decode_part_memberships(['abc', 1, 'xyz', 2]) == [1, 2]

    def test_numeric_string_items(self):
        assert decode_part_memberships('[\"1\", \"2\"]') == [1, 2]

    def test_unsupported_type_returns_empty(self):
        assert decode_part_memberships(42) == []


# ============================================================
# row_belongs_to_part
# ============================================================

class TestRowBelongsToPart:
    def test_via_tower_part_memberships_json(self):
        row = pd.Series({
            'tower_part_memberships': '[1, 2]',
            'tower_part': 1,
            'is_part_boundary': False,
        })
        assert row_belongs_to_part(row, 1) is True
        assert row_belongs_to_part(row, 2) is True
        assert row_belongs_to_part(row, 3) is False

    def test_via_tower_part_simple(self):
        row = pd.Series({
            'tower_part': 2,
            'is_part_boundary': False,
        })
        assert row_belongs_to_part(row, 2) is True
        assert row_belongs_to_part(row, 1) is False

    def test_boundary_belongs_to_both(self):
        row = pd.Series({
            'tower_part': 1,
            'is_part_boundary': True,
        })
        assert row_belongs_to_part(row, 1) is True
        assert row_belongs_to_part(row, 2) is True
        assert row_belongs_to_part(row, 3) is False

    def test_none_tower_part_defaults_to_1(self):
        row = pd.Series({
            'tower_part': None,
            'is_part_boundary': False,
        })
        assert row_belongs_to_part(row, 1) is True
        assert row_belongs_to_part(row, 2) is False

    def test_nan_tower_part_defaults_to_1(self):
        row = pd.Series({
            'tower_part': float('nan'),
            'is_part_boundary': False,
        })
        assert row_belongs_to_part(row, 1) is True

    def test_zero_tower_part_defaults_to_1(self):
        row = pd.Series({
            'tower_part': 0,
            'is_part_boundary': False,
        })
        assert row_belongs_to_part(row, 1) is True

    def test_invalid_tower_part_string(self):
        row = pd.Series({
            'tower_part': 'abc',
            'is_part_boundary': False,
        })
        assert row_belongs_to_part(row, 1) is False


# ============================================================
# filter_points_by_part
# ============================================================

class TestFilterPointsByPart:
    def test_filter_by_tower_part(self):
        df = pd.DataFrame({
            'x': [1, 2, 3],
            'y': [1, 2, 3],
            'z': [10, 20, 30],
            'tower_part': [1, 1, 2],
        })
        result = filter_points_by_part(df, 1)
        assert len(result) == 2
        assert list(result['z']) == [10, 20]

    def test_filter_with_memberships(self):
        df = pd.DataFrame({
            'x': [1, 2, 3],
            'y': [1, 2, 3],
            'z': [10, 20, 30],
            'tower_part': [1, 1, 2],
            'tower_part_memberships': ['[1]', '[1,2]', '[2]'],
            'is_part_boundary': [False, True, False],
        })
        result = filter_points_by_part(df, 2)
        assert len(result) == 2
        assert list(result['z']) == [20, 30]

    def test_filter_empty_part(self):
        df = pd.DataFrame({
            'x': [1, 2],
            'y': [1, 2],
            'z': [10, 20],
            'tower_part': [1, 1],
        })
        result = filter_points_by_part(df, 3)
        assert len(result) == 0
