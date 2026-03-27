from types import MethodType, SimpleNamespace

import matplotlib
import pandas as pd

from gui.report_widget import ReportWidget

matplotlib.use("Agg")
import matplotlib.pyplot as plt


class _DummyVerticalityWidget:
    def __init__(self):
        self.figure, ax = plt.subplots()
        ax.plot([0, 1], [0, 1])

    @staticmethod
    def get_table_data():
        return [
            {
                "section_num": 1,
                "height": 10.0,
                "deviation_x": 1.0,
                "deviation_y": 2.0,
                "total_deviation": 2.2,
                "tolerance": 10.0,
            }
        ]


class _DummyStraightnessWidget:
    @staticmethod
    def get_all_belts_data():
        return {
            1: {
                "min_height": 0.0,
                "max_height": 10.0,
                "belts": {
                    1: [
                        {"height": 0.0, "deflection": 0.0, "tolerance": 10.0},
                        {"height": 10.0, "deflection": 1.5, "tolerance": 10.0},
                    ]
                },
            }
        }

    @staticmethod
    def get_part_figures_for_pdf(part_num, group_size=2):
        figure, ax = plt.subplots()
        ax.plot([0, 1], [part_num, part_num + 1])
        return [((1,), figure)]


def test_generate_preview_html_embeds_png_images():
    fake_widget = SimpleNamespace(temp_dir=None, temp_files=[])
    fake_widget._empty_verticality_check = ReportWidget._empty_verticality_check
    fake_widget._compute_verticality_check = MethodType(ReportWidget._compute_verticality_check, fake_widget)
    fake_widget._render_verticality_stats_html = MethodType(ReportWidget._render_verticality_stats_html, fake_widget)
    fake_widget._figure_to_base64_png = MethodType(ReportWidget._figure_to_base64_png, fake_widget)
    fake_widget._collect_angular_measurements = lambda: {"x": [], "y": []}
    fake_widget._render_angular_table_html = MethodType(ReportWidget._render_angular_table_html, fake_widget)

    raw_data = pd.DataFrame([{"X": 0, "Y": 0, "Z": 0}, {"X": 1, "Y": 1, "Z": 10}])
    processed_data = {"centers": pd.DataFrame([{"z": 10.0}, {"z": 20.0}])}

    verticality_widget = _DummyVerticalityWidget()
    straightness_widget = _DummyStraightnessWidget()

    try:
        html = ReportWidget.generate_preview_html(
            fake_widget,
            raw_data,
            processed_data,
            verticality_widget=verticality_widget,
            straightness_widget=straightness_widget,
            project_name="Test Tower",
            organization="Test Org",
            report_info={"project_name": "Test Tower", "organization": "Test Org"},
        )
    finally:
        plt.close("all")
        ReportWidget.cleanup_temp_files(fake_widget)

    assert html.count("data:image/png;base64,") >= 2
    assert "<svg" not in html.lower()
    assert "chart-container" in html
    assert "GeoVertical Analyzer v1.0" in html
    assert "status-ok" in html or "status-error" in html


def test_generate_preview_html_prefers_processed_angular_sections_over_widget_table_fallback():
    fake_widget = SimpleNamespace(temp_dir=None, temp_files=[])
    fake_widget._empty_verticality_check = ReportWidget._empty_verticality_check
    fake_widget._compute_verticality_check = MethodType(ReportWidget._compute_verticality_check, fake_widget)
    fake_widget._render_verticality_stats_html = MethodType(ReportWidget._render_verticality_stats_html, fake_widget)
    fake_widget._figure_to_base64_png = MethodType(ReportWidget._figure_to_base64_png, fake_widget)
    fake_widget._collect_angular_measurements = lambda: {"x": [], "y": [], "sections": []}
    fake_widget._render_angular_table_html = MethodType(ReportWidget._render_angular_table_html, fake_widget)

    raw_data = pd.DataFrame([{"X": 0, "Y": 0, "Z": 0}, {"X": 1, "Y": 1, "Z": 10}])
    processed_data = {
        "centers": pd.DataFrame([{"z": 10.0, "deviation": 0.001}]),
        "angular_verticality": {
            "sections": [
                {
                    "section_num": 7,
                    "height": 12.0,
                    "deviation_x": 20.0,
                    "deviation_y": 15.0,
                    "total_deviation": 25.0,
                    "source": "processed_fallback",
                }
            ]
        },
    }

    class _FallbackVerticalityWidget(_DummyVerticalityWidget):
        @staticmethod
        def get_table_data():
            return [
                {
                    "section_num": 1,
                    "height": 10.0,
                    "deviation_x": 1.0,
                    "deviation_y": 2.0,
                    "total_deviation": 2.2,
                    "tolerance": 10.0,
                }
            ]

    try:
        html = ReportWidget.generate_preview_html(
            fake_widget,
            raw_data,
            processed_data,
            verticality_widget=_FallbackVerticalityWidget(),
            straightness_widget=_DummyStraightnessWidget(),
            project_name="Test Tower",
            organization="Test Org",
            report_info={"project_name": "Test Tower", "organization": "Test Org"},
        )
    finally:
        plt.close("all")
        ReportWidget.cleanup_temp_files(fake_widget)

    assert "25.0" in html
    assert ">7<" in html
    assert "2.2" not in html


def test_generate_preview_html_prefers_processed_straightness_profiles_over_widget_fallback():
    fake_widget = SimpleNamespace(temp_dir=None, temp_files=[])
    fake_widget._empty_verticality_check = ReportWidget._empty_verticality_check
    fake_widget._compute_verticality_check = MethodType(ReportWidget._compute_verticality_check, fake_widget)
    fake_widget._render_verticality_stats_html = MethodType(ReportWidget._render_verticality_stats_html, fake_widget)
    fake_widget._figure_to_base64_png = MethodType(ReportWidget._figure_to_base64_png, fake_widget)
    fake_widget._collect_angular_measurements = lambda: {"x": [], "y": [], "sections": []}
    fake_widget._render_angular_table_html = MethodType(ReportWidget._render_angular_table_html, fake_widget)

    raw_data = pd.DataFrame(
        [
            {"x": 0.0, "y": 0.0, "z": 0.0, "belt": 1},
            {"x": 0.02, "y": 0.0, "z": 5.0, "belt": 1},
            {"x": 0.0, "y": 0.0, "z": 10.0, "belt": 1},
        ]
    )
    processed_data = {
        "centers": pd.DataFrame([{"z": 10.0, "deviation": 0.001}]),
        "straightness_profiles": [
            {
                "part_number": 1,
                "belt": 1,
                "part_min_height": 0.0,
                "part_max_height": 10.0,
                "tolerance_mm": 13.3,
                "points": [
                    {"z": 0.0, "deflection_mm": 0.0, "source_index": 0},
                    {"z": 5.0, "deflection_mm": 25.0, "source_index": 1},
                    {"z": 10.0, "deflection_mm": 0.0, "source_index": 2},
                ],
            }
        ],
    }

    class _FallbackStraightnessWidget(_DummyStraightnessWidget):
        @staticmethod
        def get_all_belts_data():
            return {
                1: {
                    "min_height": 0.0,
                    "max_height": 10.0,
                    "belts": {
                        1: [
                            {"height": 0.0, "deflection": 0.0, "tolerance": 10.0},
                            {"height": 10.0, "deflection": 1.5, "tolerance": 10.0},
                        ]
                    },
                }
            }

    try:
        html = ReportWidget.generate_preview_html(
            fake_widget,
            raw_data,
            processed_data,
            verticality_widget=_DummyVerticalityWidget(),
            straightness_widget=_FallbackStraightnessWidget(),
            project_name="Test Tower",
            organization="Test Org",
            report_info={"project_name": "Test Tower", "organization": "Test Org"},
        )
    finally:
        plt.close("all")
        ReportWidget.cleanup_temp_files(fake_widget)

    assert "+25.0" in html
    assert "+1.5" not in html
