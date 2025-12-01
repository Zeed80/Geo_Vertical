import numpy as np
import pandas as pd
from core.survey_registration import shift_points_along_z, translate_points_xy, rotate_points_around_z, compute_xy_signed_angle


def test_shift_points_along_z():
    df = pd.DataFrame({'x':[0,1],'y':[0,1],'z':[10,20]})
    out = shift_points_along_z(df, 5)
    assert np.allclose(out['z'].values, [15,25])


def test_translate_points_xy():
    df = pd.DataFrame({'x':[0,1],'y':[0,1],'z':[10,20]})
    out = translate_points_xy(df, 2, -3)
    assert np.allclose(out['x'].values, [2,3])
    assert np.allclose(out['y'].values, [-3,-2])
    assert np.allclose(out['z'].values, [10,20])


def test_rotate_points_around_z_center_invariant():
    center = np.array([5.0, 5.0, 0.0])
    df = pd.DataFrame({'x':[6.0],'y':[5.0],'z':[0.0]})
    out = rotate_points_around_z(df, np.pi/2, center)
    # (6,5) вокруг (5,5) на 90° -> (5,6)
    assert np.allclose(out['x'].values, [5.0])
    assert np.allclose(out['y'].values, [6.0])


def test_compute_xy_signed_angle():
    v1 = np.array([1.0, 0.0])
    v2 = np.array([0.0, 1.0])
    angle_cw = compute_xy_signed_angle(v1, v2, 1)
    angle_ccw = compute_xy_signed_angle(v1, v2, -1)
    assert np.isclose(angle_cw, np.pi/2)
    assert np.isclose(angle_ccw, -np.pi/2)
