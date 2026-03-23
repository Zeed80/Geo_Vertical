from pathlib import Path

import pytest

from core.calculations import (
    approximate_tower_axis,
    calculate_belt_center,
    calculate_vertical_deviation,
    group_points_by_height,
    process_tower_data,
)
from core.data_loader import load_data_from_file, validate_data
from core.normatives import NormativeChecker

EXAMPLES_DIR = Path(__file__).resolve().parents[1] / "examples"


@pytest.fixture
def sample_data():
    data, epsg = load_data_from_file(str(EXAMPLES_DIR / "test_tower_data.csv"))
    assert epsg is None
    return data


@pytest.fixture
def sample_belts(sample_data):
    belts = group_points_by_height(sample_data, tolerance=0.1)
    assert len(belts) == 4
    return belts


@pytest.fixture
def sample_centers(sample_belts):
    centers = []
    for _, points in sorted(sample_belts.items()):
        x_c, y_c, z_c = calculate_belt_center(points, method='mean')
        centers.append({'x': x_c, 'y': y_c, 'z': z_c})
    return centers


def test_data_loading_and_validation(sample_data):
    is_valid, message = validate_data(sample_data)
    assert is_valid, message
    assert {'x', 'y', 'z', 'name'}.issubset(sample_data.columns)
    assert len(sample_data) == 16


def test_grouping_returns_expected_belts(sample_belts):
    assert list(sample_belts.keys()) == sorted(sample_belts.keys())
    assert all(len(points) == 4 for points in sample_belts.values())


def test_axis_and_vertical_deviation(sample_centers):
    import pandas as pd

    centers_df = pd.DataFrame(sample_centers)
    axis = approximate_tower_axis(centers_df)
    assert axis['valid'] is True

    centers_with_dev = calculate_vertical_deviation(centers_df, axis)
    assert 'deviation' in centers_with_dev.columns
    assert float(centers_with_dev['deviation'].max()) > 0.0


def test_normatives_work_on_processed_centers(sample_data):
    checker = NormativeChecker()
    results = process_tower_data(sample_data, height_tolerance=0.1, center_method='mean')
    assert results['valid'] is True

    vertical_check = checker.check_vertical_deviations(
        results['centers']['deviation'].tolist(),
        results['centers']['z'].tolist(),
    )
    assert vertical_check['total'] == len(results['centers'])


def test_full_processing_pipeline(sample_data):
    results = process_tower_data(sample_data, height_tolerance=0.1, center_method='mean')
    assert results['valid'] is True
    assert len(results['centers']) == 4
    assert results['axis']['valid'] is True


def test_perfect_tower_has_submillimeter_deviation():
    data, _ = load_data_from_file(str(EXAMPLES_DIR / "test_tower_perfect.csv"))
    results = process_tower_data(data, height_tolerance=0.1)
    max_deviation_mm = float(results['centers']['deviation'].max()) * 1000.0
    assert max_deviation_mm < 1.0
