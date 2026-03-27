"""Тесты для core.straightness_calculations — стрелы прогиба, наклон поясов, авто-детекция."""

import numpy as np
import pandas as pd
import pytest

from core.straightness_calculations import (
    auto_detect_split_height,
    build_straightness_profiles,
    calculate_belt_angle,
    calculate_belt_deflections,
    find_station_point,
)
from core.services.straightness_profiles import get_preferred_straightness_part_map


def _make_belt_df(coords):
    """Вспомогательная функция для создания DataFrame из списка (x, y, z)."""
    return pd.DataFrame(coords, columns=['x', 'y', 'z'])


# ============================================================
# calculate_belt_deflections
# ============================================================

class TestCalculateBeltDeflections:
    def test_single_point_returns_zero(self):
        df = _make_belt_df([(0, 0, 10)])
        result = calculate_belt_deflections(df)
        assert result == [0.0]

    def test_two_points_both_zero(self):
        df = _make_belt_df([(0, 0, 0), (0, 0, 10)])
        result = calculate_belt_deflections(df)
        assert result == [0.0, 0.0]

    def test_straight_line_all_zero(self):
        df = _make_belt_df([
            (0.0, 0.0, 0.0),
            (0.0, 0.0, 5.0),
            (0.0, 0.0, 10.0),
        ])
        result = calculate_belt_deflections(df)
        assert len(result) == 3
        assert result[0] == 0.0
        assert result[-1] == 0.0
        assert abs(result[1]) < 1e-6

    def test_offset_middle_point_positive_deflection(self):
        df = _make_belt_df([
            (0.0, 0.0, 0.0),
            (0.01, 0.0, 5.0),
            (0.0, 0.0, 10.0),
        ])
        result = calculate_belt_deflections(df)
        assert result[0] == 0.0
        assert result[-1] == 0.0
        assert result[1] > 0.0

    def test_offset_middle_point_negative_deflection(self):
        df = _make_belt_df([
            (0.0, 0.0, 0.0),
            (-0.01, 0.0, 5.0),
            (0.0, 0.0, 10.0),
        ])
        result = calculate_belt_deflections(df)
        assert result[1] < 0.0

    def test_with_part_heights(self):
        df = _make_belt_df([
            (0.0, 0.0, 0.0),
            (0.005, 0.0, 5.0),
            (0.0, 0.0, 10.0),
        ])
        result = calculate_belt_deflections(df, part_min_height=0.0, part_max_height=10.0)
        assert len(result) == 3
        assert result[0] == 0.0
        assert result[-1] == 0.0
        assert result[1] > 0.0

    def test_same_height_returns_zeros(self):
        df = _make_belt_df([
            (0.0, 0.0, 5.0),
            (1.0, 0.0, 5.0),
            (2.0, 0.0, 5.0),
        ])
        result = calculate_belt_deflections(df)
        assert all(v == 0.0 for v in result)

    def test_unsorted_input_handled(self):
        df = _make_belt_df([
            (0.0, 0.0, 10.0),
            (0.0, 0.0, 0.0),
            (0.01, 0.0, 5.0),
        ])
        result = calculate_belt_deflections(df)
        assert len(result) == 3
        assert result[0] == 0.0
        assert result[-1] == 0.0

    def test_part_heights_no_matching_points_fallback(self):
        df = _make_belt_df([
            (0.0, 0.0, 2.0),
            (0.01, 0.0, 5.0),
            (0.0, 0.0, 8.0),
        ])
        result = calculate_belt_deflections(df, part_min_height=0.0, part_max_height=10.0)
        assert len(result) == 3
        assert result[0] == 0.0
        assert result[-1] == 0.0

    def test_shared_boundary_triplets_use_local_sections(self):
        df = _make_belt_df([
            (0.0, 0.0, 0.0),
            (0.01, 0.0, 5.0),
            (0.0, 0.0, 10.0),
            (0.02, 0.0, 15.0),
            (0.0, 0.0, 20.0),
        ])

        result = calculate_belt_deflections(df)

        assert len(result) == 5
        assert result[0] == 0.0
        assert result[2] == 0.0
        assert result[4] == 0.0
        assert result[1] > 0.0
        assert result[3] > 0.0


# ============================================================
# calculate_belt_angle
# ============================================================

class TestBuildStraightnessProfiles:
    def test_builds_profiles_with_source_indices(self):
        df = pd.DataFrame(
            [
                {'x': 0.0, 'y': 0.0, 'z': 0.0, 'belt': 1},
                {'x': 0.0, 'y': 0.0, 'z': 5.0, 'belt': 1},
                {'x': 0.0, 'y': 0.0, 'z': 10.0, 'belt': 1},
                {'x': 1.0, 'y': 0.0, 'z': 0.0, 'belt': 2},
                {'x': 1.0, 'y': 0.0, 'z': 5.0, 'belt': 2},
                {'x': 1.0, 'y': 0.0, 'z': 10.0, 'belt': 2},
            ],
            index=[10, 11, 12, 20, 21, 22],
        )

        profiles = build_straightness_profiles(df)

        assert len(profiles) == 2
        assert all(profile['max_deflection_mm'] == 0.0 for profile in profiles)
        assert profiles[0]['points'][0]['source_index'] in {10, 20}

    def test_profiles_use_three_point_sections(self):
        df = pd.DataFrame(
            [
                {'x': 0.0, 'y': 0.0, 'z': 0.0, 'belt': 1},
                {'x': 0.01, 'y': 0.0, 'z': 5.0, 'belt': 1},
                {'x': 0.0, 'y': 0.0, 'z': 10.0, 'belt': 1},
                {'x': 0.02, 'y': 0.0, 'z': 15.0, 'belt': 1},
                {'x': 0.0, 'y': 0.0, 'z': 20.0, 'belt': 1},
            ],
            index=[100, 101, 102, 103, 104],
        )

        profile = build_straightness_profiles(df)[0]
        point_map = {int(item['source_index']): float(item['deflection_mm']) for item in profile['points']}

        assert point_map[100] == 0.0
        assert point_map[102] == 0.0
        assert point_map[104] == 0.0
        assert point_map[101] > 0.0
        assert point_map[103] > 0.0

    def test_part_map_falls_back_to_canonical_profiles_from_raw_points(self):
        df = pd.DataFrame(
            [
                {'x': 0.0, 'y': 0.0, 'z': 0.0, 'belt': 1},
                {'x': 0.02, 'y': 0.0, 'z': 5.0, 'belt': 1},
                {'x': 0.0, 'y': 0.0, 'z': 10.0, 'belt': 1},
            ]
        )

        part_map = get_preferred_straightness_part_map(None, points=df)

        assert part_map[1]['min_height'] == pytest.approx(0.0, abs=1e-9)
        assert part_map[1]['max_height'] == pytest.approx(10.0, abs=1e-9)
        assert [point['deflection'] for point in part_map[1]['belts'][1]] == pytest.approx(
            [0.0, 20.0, 0.0],
            abs=1e-9,
        )


class TestCalculateBeltAngle:
    def test_vertical_belt_returns_pi_half(self):
        """Вертикальный пояс: функция возвращает pi/2 (дополнительный угол)."""
        df = _make_belt_df([(0, 0, 0), (0, 0, 10)])
        angle = calculate_belt_angle(df)
        assert abs(angle - np.pi / 2) < 1e-6

    def test_single_point_zero_angle(self):
        df = _make_belt_df([(0, 0, 5)])
        angle = calculate_belt_angle(df)
        assert angle == 0.0

    def test_tilted_belt_positive_angle(self):
        df = _make_belt_df([(0, 0, 0), (1, 0, 10)])
        angle = calculate_belt_angle(df)
        assert angle > 0.0

    def test_horizontal_belt_near_zero(self):
        """Горизонтальный пояс: arccos(0) = pi/2, angle >= pi/2 → returns 0."""
        df = _make_belt_df([(0, 0, 0), (10, 0, 0)])
        angle = calculate_belt_angle(df)
        assert abs(angle) < 1e-6

    def test_unsorted_input(self):
        df = _make_belt_df([(0, 0, 10), (0, 0, 0)])
        angle = calculate_belt_angle(df)
        assert abs(angle - np.pi / 2) < 1e-6


# ============================================================
# auto_detect_split_height
# ============================================================

class TestAutoDetectSplitHeight:
    def test_none_input(self):
        assert auto_detect_split_height(None) is None

    def test_empty_dataframe(self):
        df = pd.DataFrame(columns=['x', 'y', 'z'])
        assert auto_detect_split_height(df) is None

    def test_too_few_points(self):
        df = _make_belt_df([(0, 0, 1), (0, 0, 2)])
        assert auto_detect_split_height(df) is None

    def test_small_z_range(self):
        df = _make_belt_df([(0, 0, 5.0 + i * 0.1) for i in range(10)])
        result = auto_detect_split_height(df)
        assert result is None

    def test_two_cluster_returns_height_between(self):
        lower = [(np.random.uniform(-1, 1), np.random.uniform(-1, 1), z)
                 for z in np.linspace(0, 10, 20)]
        upper = [(np.random.uniform(-1, 1), np.random.uniform(-1, 1), z)
                 for z in np.linspace(30, 40, 20)]
        df = _make_belt_df(lower + upper)
        result = auto_detect_split_height(df)
        assert result is not None
        assert 0.0 < result < 40.0

    def test_excludes_station_points(self):
        points = [(0, 0, z) for z in np.linspace(0, 50, 30)]
        df = _make_belt_df(points)
        df['is_station'] = False
        df.loc[0, 'is_station'] = True
        result = auto_detect_split_height(df)
        assert result is not None


# ============================================================
# find_station_point
# ============================================================

class TestFindStationPoint:
    def test_none_input(self):
        assert find_station_point(None) is None

    def test_empty_dataframe(self):
        df = pd.DataFrame(columns=['x', 'y', 'z'])
        assert find_station_point(df) is None

    def test_single_point(self):
        df = _make_belt_df([(0, 0, 0)])
        assert find_station_point(df) is None

    def test_all_close_no_station(self):
        df = _make_belt_df([
            (0, 0, i * 0.5) for i in range(10)
        ])
        result = find_station_point(df, min_distance=20.0)
        assert result is None

    def test_remote_point_detected(self):
        tower_points = [(1, 1, z) for z in range(10)]
        station = [(100, 100, 0)]
        df = _make_belt_df(station + tower_points)
        result = find_station_point(df, min_distance=15.0)
        assert result == 0
