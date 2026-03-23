import numpy as np
import pandas as pd

from core.planar_orientation import (
    clockwise_order_indices,
    domain_signed_angle_deg,
    extract_reference_station_xy,
    observer_right_axis,
    sort_points_clockwise,
)


def test_domain_signed_angle_uses_clockwise_positive():
    v1 = np.array([1.0, 0.0], dtype=float)
    assert domain_signed_angle_deg(v1, np.array([0.0, -1.0], dtype=float)) == 90.0
    assert domain_signed_angle_deg(v1, np.array([0.0, 1.0], dtype=float)) == -90.0


def test_observer_right_axis_points_to_visual_right_side():
    center = np.array([0.0, 0.0], dtype=float)
    station = np.array([0.0, -10.0], dtype=float)
    right_axis = observer_right_axis(center, station)
    assert np.allclose(right_axis, np.array([1.0, 0.0], dtype=float))


def test_clockwise_order_anchors_to_observer_right():
    points = np.array(
        [
            [1.0, 0.0],   # east
            [0.0, 1.0],   # north
            [-1.0, 0.0],  # west
            [0.0, -1.0],  # south
        ],
        dtype=float,
    )
    station = np.array([-10.0, 0.0], dtype=float)
    order = clockwise_order_indices(points, center_xy=np.array([0.0, 0.0]), station_xy=station)
    assert order.tolist() == [3, 2, 1, 0]


def test_clockwise_order_falls_back_to_positive_x_without_station():
    points = np.array(
        [
            [0.0, 1.0],   # north
            [-1.0, 0.0],  # west
            [0.0, -1.0],  # south
            [1.0, 0.0],   # east
        ],
        dtype=float,
    )
    order = clockwise_order_indices(points, center_xy=np.array([0.0, 0.0]))
    assert order.tolist() == [3, 2, 1, 0]


def test_sort_points_clockwise_uses_observer_right_anchor():
    df = pd.DataFrame(
        [
            {"name": "north", "x": 0.0, "y": 1.0, "z": 0.0},
            {"name": "west", "x": -1.0, "y": 0.0, "z": 0.0},
            {"name": "south", "x": 0.0, "y": -1.0, "z": 0.0},
            {"name": "east", "x": 1.0, "y": 0.0, "z": 0.0},
        ]
    )
    sorted_df = sort_points_clockwise(df, station_xy=np.array([-10.0, 0.0]))
    assert sorted_df["name"].tolist() == ["south", "west", "north", "east"]


def test_extract_reference_station_xy_prefers_station_row():
    data = pd.DataFrame(
        [
            {"name": "st1", "x": 10.0, "y": 20.0, "is_station": True},
            {"name": "p1", "x": 1.0, "y": 2.0, "is_station": False},
        ]
    )
    station_xy = extract_reference_station_xy(data)
    assert np.allclose(station_xy, np.array([10.0, 20.0], dtype=float))
