import pandas as pd

from core.services.report_templates import ReportDataAssembler


def _centers_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"z": 5.0, "deviation": 0.001, "points_count": 8},
            {"z": 10.0, "deviation": 0.002, "points_count": 8},
        ]
    )


def test_report_assembler_prefers_explicit_angular_sections_for_verticality_outputs():
    centers = _centers_frame()
    explicit_angular = {
        "sections": [
            {
                "section_num": 11,
                "part_num": 2,
                "height": 6.0,
                "deviation_x": 12.0,
                "deviation_y": 5.0,
                "total_deviation": 13.0,
                "source": "stations",
            },
            {
                "section_num": 12,
                "part_num": 2,
                "height": 12.0,
                "deviation_x": 20.0,
                "deviation_y": 15.0,
                "total_deviation": 25.0,
                "source": "stations",
            },
        ]
    }
    processed_angular = {
        "sections": [
            {
                "section_num": 1,
                "height": 5.0,
                "total_deviation": 3.0,
                "source": "processed",
            }
        ]
    }

    assembler = ReportDataAssembler(
        {"centers": centers, "angular_verticality": processed_angular},
        angular_measurements=explicit_angular,
    )

    summary = assembler._build_verticality_section()
    records = assembler._build_verticality_records()

    assert summary["total_levels"] == 2
    assert summary["max_deviation_mm"] == 25.0
    assert summary["mean_deviation_mm"] == 19.0
    assert summary["levels"][0]["section_number"] == 11
    assert summary["levels"][0]["part_num"] == 2
    assert summary["levels"][0]["source"] == "stations"
    assert [record.section_number for record in records] == [11, 12]
    assert [record.deviation_current_mm for record in records] == [13.0, 25.0]


def test_report_assembler_uses_processed_angular_sections_when_explicit_payload_missing():
    centers = _centers_frame()
    processed_angular = {
        "sections": [
            {
                "section_num": 3,
                "part_num": 1,
                "height": 4.0,
                "deviation_x": 8.0,
                "deviation_y": 6.0,
                "total_deviation": 10.0,
                "source": "processed_fallback",
            },
            {
                "section_num": 4,
                "part_num": 1,
                "height": 9.0,
                "deviation_x": 0.0,
                "deviation_y": 24.0,
                "total_deviation": 24.0,
                "source": "processed_fallback",
            },
        ]
    }

    assembler = ReportDataAssembler({"centers": centers, "angular_verticality": processed_angular})

    summary = assembler._build_verticality_section()
    records = assembler._build_verticality_records()

    assert summary["total_levels"] == 2
    assert summary["max_deviation_mm"] == 24.0
    assert summary["levels"][0]["section_number"] == 3
    assert summary["levels"][1]["section_number"] == 4
    assert [record.section_number for record in records] == [3, 4]
    assert [record.height_m for record in records] == [4.0, 9.0]


def test_report_assembler_falls_back_to_centers_without_angular_sections():
    centers = _centers_frame()
    assembler = ReportDataAssembler({"centers": centers})

    summary = assembler._build_verticality_section()
    records = assembler._build_verticality_records()

    assert summary["total_levels"] == 2
    assert summary["max_deviation_mm"] == 2.0
    assert summary["mean_deviation_mm"] == 1.5
    assert [record.section_number for record in records] == [1, 2]
    assert [record.deviation_current_mm for record in records] == [1.0, 2.0]
