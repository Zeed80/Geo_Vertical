"""Тесты для core.belt_operations — плоскости поясов, проекции, геометрия."""

import numpy as np
import pandas as pd
import pytest

from core.belt_operations import (
    align_points_to_belt,
    calculate_belt_line,
    create_belt_plane,
    detect_instrument_station,
    distance_point_to_line,
    fit_circle_3d,
    generate_belt_circle_points,
    project_point_to_plane,
    project_points_to_plane,
    validate_belt_geometry,
)


def _make_df(coords):
    return pd.DataFrame(coords, columns=['x', 'y', 'z'])


# ============================================================
# create_belt_plane
# ============================================================

class TestCreateBeltPlane:
    def test_xy_plane(self):
        df = _make_df([(0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0)])
        plane = create_belt_plane(df)
        normal = np.array(plane['normal'])
        assert abs(abs(normal[2]) - 1.0) < 1e-6
        assert abs(normal[0]) < 1e-6
        assert abs(normal[1]) < 1e-6
        assert plane['rmse'] < 1e-6

    def test_xz_plane(self):
        df = _make_df([(0, 0, 0), (1, 0, 0), (0, 0, 1), (1, 0, 1)])
        plane = create_belt_plane(df)
        normal = np.array(plane['normal'])
        assert abs(abs(normal[1]) - 1.0) < 1e-6

    def test_too_few_points_raises(self):
        df = _make_df([(0, 0, 0), (1, 0, 0)])
        with pytest.raises(ValueError):
            create_belt_plane(df)

    def test_center_is_mean(self):
        pts = [(0, 0, 0), (2, 0, 0), (1, 1, 0)]
        df = _make_df(pts)
        plane = create_belt_plane(df)
        assert abs(plane['center'][0] - 1.0) < 1e-6
        assert abs(plane['center'][2] - 0.0) < 1e-6


# ============================================================
# project_point_to_plane / project_points_to_plane
# ============================================================

class TestProjection:
    def _xy_plane(self):
        return {'a': 0, 'b': 0, 'c': 1, 'd': 0}

    def test_project_onto_xy_plane(self):
        plane = self._xy_plane()
        proj = project_point_to_plane(np.array([3, 4, 5]), plane)
        np.testing.assert_allclose(proj, [3, 4, 0], atol=1e-6)

    def test_point_on_plane_unchanged(self):
        plane = self._xy_plane()
        proj = project_point_to_plane(np.array([1, 2, 0]), plane)
        np.testing.assert_allclose(proj, [1, 2, 0], atol=1e-6)

    def test_batch_projection(self):
        plane = self._xy_plane()
        pts = np.array([[1, 2, 3], [4, 5, 6]])
        result = project_points_to_plane(pts, plane)
        assert result.shape == (2, 3)
        np.testing.assert_allclose(result[:, 2], 0, atol=1e-6)


# ============================================================
# fit_circle_3d
# ============================================================

class TestFitCircle3d:
    def test_perfect_circle(self):
        r = 5.0
        theta = np.linspace(0, 2 * np.pi, 20, endpoint=False)
        pts = [(r * np.cos(t), r * np.sin(t), 0.0) for t in theta]
        df = _make_df(pts)
        result = fit_circle_3d(df)
        assert abs(result['radius'] - r) < 0.5
        assert result['rmse'] < 0.5

    def test_too_few_points_raises(self):
        df = _make_df([(0, 0, 0), (1, 0, 0)])
        with pytest.raises(ValueError):
            fit_circle_3d(df)


# ============================================================
# align_points_to_belt
# ============================================================

class TestAlignPointsToBelt:
    def test_points_on_plane_zero_displacement(self):
        df = _make_df([(0, 0, 0), (1, 0, 0), (0, 1, 0)])
        plane = create_belt_plane(df)
        aligned = align_points_to_belt(df, plane)
        assert 'displacement' in aligned.columns
        assert aligned['displacement'].max() < 1e-6

    def test_off_plane_points_moved(self):
        df = _make_df([(0, 0, 0), (1, 0, 0), (0, 1, 0), (0.5, 0.5, 1.0)])
        plane = create_belt_plane(_make_df([(0, 0, 0), (1, 0, 0), (0, 1, 0)]))
        aligned = align_points_to_belt(df, plane)
        assert aligned['displacement'].iloc[3] > 0.5


# ============================================================
# distance_point_to_line
# ============================================================

class TestDistancePointToLine:
    def test_point_on_line_zero_distance(self):
        d = distance_point_to_line(
            np.array([0, 0, 5]),
            np.array([0, 0, 0]),
            np.array([0, 0, 1]),
        )
        assert abs(d) < 1e-6

    def test_perpendicular_distance(self):
        d = distance_point_to_line(
            np.array([3, 0, 0]),
            np.array([0, 0, 0]),
            np.array([0, 0, 1]),
        )
        assert abs(d - 3.0) < 1e-6


# ============================================================
# validate_belt_geometry
# ============================================================

class TestValidateBeltGeometry:
    def test_valid_geometry(self):
        r = 2.0
        theta = np.linspace(0, 2 * np.pi, 10, endpoint=False)
        pts = [(r * np.cos(t), r * np.sin(t), 0.0) for t in theta]
        df = _make_df(pts)
        is_valid, msg = validate_belt_geometry(df)
        assert is_valid

    def test_too_few_points_invalid(self):
        df = _make_df([(0, 0, 0), (1, 0, 0)])
        is_valid, msg = validate_belt_geometry(df)
        assert not is_valid
        assert 'минимум' in msg.lower()

    def test_large_height_deviation_invalid(self):
        pts = [(np.cos(i), np.sin(i), i * 10.0) for i in range(6)]
        df = _make_df(pts)
        is_valid, msg = validate_belt_geometry(df, max_height_deviation=0.01)
        assert not is_valid


# ============================================================
# calculate_belt_line
# ============================================================

class TestCalculateBeltLine:
    def test_returns_all_keys(self):
        r = 3.0
        theta = np.linspace(0, 2 * np.pi, 12, endpoint=False)
        pts = [(r * np.cos(t), r * np.sin(t), 0.0) for t in theta]
        df = _make_df(pts)
        result = calculate_belt_line(df)
        assert 'plane' in result
        assert 'circle' in result
        assert 'points_count' in result
        assert 'quality_score' in result
        assert result['points_count'] == 12

    def test_too_few_points_raises(self):
        df = _make_df([(0, 0, 0)])
        with pytest.raises(ValueError):
            calculate_belt_line(df)


# ============================================================
# generate_belt_circle_points
# ============================================================

class TestGenerateBeltCirclePoints:
    def test_generates_correct_count(self):
        r = 3.0
        theta = np.linspace(0, 2 * np.pi, 12, endpoint=False)
        pts = [(r * np.cos(t), r * np.sin(t), 0.0) for t in theta]
        df = _make_df(pts)
        belt_line = calculate_belt_line(df)
        circle_pts = generate_belt_circle_points(belt_line, num_points=30)
        assert circle_pts.shape == (30, 3)


# ============================================================
# detect_instrument_station
# ============================================================

class TestDetectInstrumentStation:
    def test_too_few_points_none(self):
        df = _make_df([(0, 0, 0), (1, 0, 1)])
        assert detect_instrument_station(df) is None

    def test_station_at_bottom(self):
        tower = [(i, 0, 10 + j) for i in range(3) for j in range(3)]
        station = [(0, 0, 0)]
        df = _make_df(station + tower)
        result = detect_instrument_station(df)
        assert result == 0

    def test_no_station_all_close(self):
        pts = [(0, 0, z) for z in np.linspace(10, 10.5, 10)]
        df = _make_df(pts)
        assert detect_instrument_station(df) is None
