"""
Тесты новой модели генерации башни.
"""

import pytest

from core.tower_generator import (
    LegacyTowerBlueprint,
    SectionSpec,
    TowerBlueprintV2,
    TowerSegmentSpec,
    generate_tower_data,
)


def test_prism_with_multiple_parts_and_levels():
    blueprint = TowerBlueprintV2(
        segments=[
            TowerSegmentSpec(
                name="Основание",
                shape="prism",
                faces=4,
                height=6.0,
                levels=2,
                base_size=4.0,
            ),
            TowerSegmentSpec(
                name="Верхняя часть",
                shape="prism",
                faces=6,
                height=4.0,
                levels=1,
                base_size=3.0,
            ),
        ],
        instrument_distance=30.0,
        instrument_angle_deg=30.0,
        instrument_height=1.6,
    )
    data, section_data, metadata = generate_tower_data(blueprint, seed=5)

    tower_points = data[~data["is_station"]]
    assert set(tower_points["segment"].unique()) == {1, 2}
    assert metadata["total_height"] == pytest.approx(10.0)
    # Проверяем, что уровней больше, чем частей благодаря параметру levels
    assert len(section_data) == 4


def test_truncated_pyramid_radius_decreases():
    blueprint = TowerBlueprintV2(
        segments=[
            TowerSegmentSpec(
                name="Пирамида",
                shape="truncated_pyramid",
                faces=5,
                height=12.0,
                levels=3,
                base_size=5.0,
                top_size=2.5,
            )
        ],
        instrument_distance=20.0,
        instrument_angle_deg=0.0,
        instrument_height=1.8,
    )
    data, _, _ = generate_tower_data(blueprint, seed=10)
    points = data[~data["is_station"]]

    bottom = points[points["segment_level"] == 0]
    top_level = points["segment_level"].max()
    top = points[points["segment_level"] == top_level]
    bottom_radius = (bottom[["x", "y"]].pow(2).sum(axis=1).mean()) ** 0.5
    top_radius = (top[["x", "y"]].pow(2).sum(axis=1).mean()) ** 0.5
    assert top_radius < bottom_radius


def test_levels_parameter_controls_discrete_heights():
    blueprint = TowerBlueprintV2(
        segments=[
            TowerSegmentSpec(
                name="Высокая призма",
                shape="prism",
                faces=4,
                height=9.0,
                levels=3,
                base_size=4.0,
            )
        ]
    )
    data, section_data, _ = generate_tower_data(blueprint, seed=0)
    heights = sorted({round(entry["height"], 5) for entry in section_data})
    expected = [0.0, 3.0, 6.0, 9.0]
    assert heights == expected


def test_generated_belts_follow_clockwise_order_from_station():
    blueprint = TowerBlueprintV2(
        segments=[
            TowerSegmentSpec(
                name="Square",
                shape="prism",
                faces=4,
                height=4.0,
                levels=1,
                base_size=4.0,
            )
        ],
        instrument_distance=20.0,
        instrument_angle_deg=0.0,
        instrument_height=1.7,
    )
    data, section_data, _ = generate_tower_data(blueprint, seed=0)

    bottom_level = data[(~data["is_station"]) & (data["z"] == 0.0)].sort_values("belt")
    assert bottom_level["belt"].tolist() == [1, 2, 3, 4]
    assert bottom_level["y"].tolist()[0] == pytest.approx(bottom_level["y"].min())

    first_section = section_data[0]
    assert first_section["belt_nums"] == [1, 2, 3, 4]
    assert first_section["points"][0][1] == pytest.approx(min(point[1] for point in first_section["points"]))


def test_legacy_blueprint_is_converted():
    legacy = LegacyTowerBlueprint(
        tower_type="prism",
        faces=3,
        base_size=6.0,
        top_size=6.0,
        total_height=6.0,
        sections=[
            SectionSpec(name="Legacy", height=6.0, shape="prism", lower_size=6.0, upper_size=6.0)
        ],
    )
    data, _, meta = generate_tower_data(legacy, seed=1)
    assert meta["total_height"] == pytest.approx(6.0)
    belts = data[~data["is_station"]]["faces"].unique()
    assert len(belts) == 1 and belts[0] == 3
