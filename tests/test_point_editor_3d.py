import numpy as np
import pandas as pd
from PyQt6.QtGui import QColor

from gui.point_editor_3d import PointEditor3DWidget


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
