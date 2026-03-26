from __future__ import annotations

import os

import pandas as pd
import pytest
from PyQt6.QtWidgets import QApplication
from matplotlib.figure import Figure

from core.normatives import get_straightness_tolerance, get_vertical_tolerance
from gui.straightness_widget import StraightnessWidget
from gui.verticality_widget import VerticalityWidget


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

VERTICALITY_PROFILE_LABEL_X = "\u041e\u0442\u043a\u043b\u043e\u043d\u0435\u043d\u0438\u0435 \u043f\u043e X"
VERTICALITY_XLABEL = "\u041e\u0442\u043a\u043b\u043e\u043d\u0435\u043d\u0438\u0435 X, \u043c\u043c"
HEIGHT_YLABEL = "\u0412\u044b\u0441\u043e\u0442\u0430, \u043c"
VERTICALITY_TITLE_X = "\u0412\u0435\u0440\u0442\u0438\u043a\u0430\u043b\u044c\u043d\u043e\u0441\u0442\u044c \u043f\u043e \u043e\u0441\u0438 X"
STRAIGHTNESS_PROFILE_LABEL = "\u0424\u0430\u043a\u0442\u0438\u0447\u0435\u0441\u043a\u0438\u0439 \u043f\u0440\u043e\u0433\u0438\u0431"
STRAIGHTNESS_XLABEL = "\u0421\u0442\u0440\u0435\u043b\u0430 \u043f\u0440\u043e\u0433\u0438\u0431\u0430, \u043c\u043c"
STRAIGHTNESS_TITLE = "\u041f\u043e\u044f\u0441 1"


def _ensure_app():
    return QApplication.instance() or QApplication([])


def test_verticality_plot_draws_zero_line_tolerance_envelope_and_scaled_profile():
    _ensure_app()
    widget = VerticalityWidget()
    section_data = [
        {"section_num": 0, "height": 0.0, "deviation_x": 0.0, "deviation_y": 0.0},
        {"section_num": 1, "height": 10.0, "deviation_x": 12.0, "deviation_y": -4.0},
    ]

    ax = widget.figure.add_subplot(1, 1, 1)
    widget._plot_verticality_profile(ax, section_data, component="x", divisor=2.0)

    lines = ax.get_lines()
    profile_line = next(line for line in lines if line.get_label() == VERTICALITY_PROFILE_LABEL_X)
    zero_lines = [
        line for line in lines
        if list(line.get_xdata()) == [0, 0] and line.get_linestyle() == "-"
    ]
    tolerance_lines = [line for line in lines if line.get_linestyle() == "--"]
    expected_tolerance = get_vertical_tolerance(10.0) * 1000.0

    assert ax.get_xlabel() == VERTICALITY_XLABEL
    assert ax.get_ylabel() == HEIGHT_YLABEL
    assert ax.get_title() == VERTICALITY_TITLE_X
    assert list(profile_line.get_xdata()) == pytest.approx([0.0, 6.0], abs=1e-9)
    assert list(profile_line.get_ydata()) == pytest.approx([0.0, 10.0], abs=1e-9)
    assert zero_lines
    assert len(tolerance_lines) == 2
    assert sorted(float(line.get_xdata()[1]) for line in tolerance_lines) == pytest.approx(
        [-expected_tolerance, expected_tolerance],
        abs=1e-9,
    )


def test_straightness_plot_draws_zero_line_tolerance_lines_and_profile_points():
    _ensure_app()
    widget = StraightnessWidget()
    belt_points = pd.DataFrame(
        [
            {"x": 0.0, "y": 0.0, "z": 0.0, "belt": 1},
            {"x": 0.02, "y": 0.0, "z": 5.0, "belt": 1},
            {"x": 0.0, "y": 0.0, "z": 10.0, "belt": 1},
        ]
    )
    figure = Figure()
    ax = figure.add_subplot(1, 1, 1)

    rendered = widget._render_straightness_plot(ax, belt_num=1, belt_points=belt_points)

    lines = ax.get_lines()
    profile_line = next(
        line
        for line in lines
        if line.get_linestyle() == "-" and list(line.get_ydata()) == [0.0, 5.0, 10.0]
    )
    zero_lines = [
        line for line in lines
        if list(line.get_xdata()) == [0, 0] and line.get_linestyle() == "-"
    ]
    tolerance_lines = [line for line in lines if line.get_linestyle() == "--"]
    expected_tolerance = get_straightness_tolerance(10.0) * 1000.0

    assert rendered is True
    assert ax.get_xlabel() == STRAIGHTNESS_XLABEL
    assert ax.get_ylabel() == HEIGHT_YLABEL
    assert ax.get_title() == STRAIGHTNESS_TITLE
    assert list(profile_line.get_xdata()) == pytest.approx([0.0, 20.0, 0.0], abs=1e-9)
    assert list(profile_line.get_ydata()) == pytest.approx([0.0, 5.0, 10.0], abs=1e-9)
    assert zero_lines
    assert len(tolerance_lines) == 2
    assert sorted(float(line.get_xdata()[0]) for line in tolerance_lines) == pytest.approx(
        [-expected_tolerance, expected_tolerance],
        abs=1e-9,
    )
