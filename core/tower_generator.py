"""
Генератор синтетической башни для режима «Создать башню».

Описывает структуру башни через чертёж (blueprint) и создаёт DataFrame
с точками поясов, секциями и точкой стояния прибора.
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from typing import Any, Union

import numpy as np
import pandas as pd

from core.planar_orientation import clockwise_order_indices

logger = logging.getLogger(__name__)

SUPPORTED_SHAPES = {"prism", "truncated_pyramid"}


def _deg2rad(value: float) -> float:
    return value * math.pi / 180.0


from core.point_utils import (
    build_is_station_mask as _build_is_station_mask,
)
from core.point_utils import (
    decode_part_memberships as _decode_part_memberships,
)
from core.point_utils import (
    filter_points_by_part as _filter_points_by_part,
)


def _size_to_radius(size_m: float) -> float:
    """
    Преобразует «размер пояса» (диаметр между противоположными гранями/ребрами)
    в радиус окружности описанной вокруг правильного многоугольника.

    Мы трактуем ввод как диаметр по вершинам (между противоположными точками),
    что соответствует удвоенному радиусу.
    """
    if size_m <= 0:
        raise ValueError("Размер секции должен быть положительным")
    return size_m / 2.0


def _build_polygon_points(
    center: tuple[float, float],
    radius: float,
    faces: int,
    z_value: float,
    rotation_deg: float,
    deviation_m: float,
    rng: np.random.Generator,
    reference_station_xy: tuple[float, float] | None = None,
) -> list[tuple[float, float, float]]:
    """Формирует точки правильного многоугольника с небольшой девиацией."""
    if faces < 3:
        raise ValueError("Количество граней должно быть >= 3")

    rotation = _deg2rad(rotation_deg)
    raw_points: list[tuple[float, float, float]] = []
    for face_idx in range(faces):
        angle = rotation + 2.0 * math.pi * face_idx / faces
        x = center[0] + radius * math.cos(angle)
        y = center[1] + radius * math.sin(angle)
        if deviation_m > 0:
            # Применяем случайную девиацию в плоскости XY с возможностью отрицательных значений
            # Используем uniform распределение для равномерного распределения в диапазоне [-deviation_m, +deviation_m]
            x += rng.uniform(-deviation_m, deviation_m)
            y += rng.uniform(-deviation_m, deviation_m)
        raw_points.append((x, y, z_value))

    order = clockwise_order_indices(
        np.array([[point[0], point[1]] for point in raw_points], dtype=float),
        center_xy=np.array(center, dtype=float),
        station_xy=np.array(reference_station_xy, dtype=float)
        if reference_station_xy is not None
        else None,
    )

    points: list[tuple[float, float, float]] = []
    for point_idx in order:
        x, y, z_coord = raw_points[int(point_idx)]
        points.append((x, y, z_coord))
    return points


@dataclass
class SectionSpec:
    """Описание одной секции башни (высотного блока)."""

    name: str
    height: float
    tilt_mm: float = 0.0
    tilt_direction_deg: float = 0.0
    lower_tilt_mm: float | None = None
    lower_tilt_direction_deg: float = 0.0
    upper_tilt_mm: float | None = None
    upper_tilt_direction_deg: float = 0.0
    shape: str = "prism"
    faces: int | None = None
    rotation_deg: float | None = None
    lower_size: float | None = None
    upper_size: float | None = None
    deviation_mm: float | None = None
    segment_id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict[str, Any]) -> SectionSpec:
        return SectionSpec(
            name=data.get("name", "Секция"),
            height=float(data.get("height", 0.0)),
            tilt_mm=float(data.get("tilt_mm", 0.0)),
            tilt_direction_deg=float(data.get("tilt_direction_deg", 0.0)),
            lower_tilt_mm=(
                float(data["lower_tilt_mm"]) if data.get("lower_tilt_mm") is not None else None
            ),
            lower_tilt_direction_deg=float(data.get("lower_tilt_direction_deg", 0.0)),
            upper_tilt_mm=(
                float(data["upper_tilt_mm"]) if data.get("upper_tilt_mm") is not None else None
            ),
            upper_tilt_direction_deg=float(data.get("upper_tilt_direction_deg", 0.0)),
            shape=data.get("shape", "prism"),
            faces=int(data["faces"]) if data.get("faces") is not None else None,
            rotation_deg=(
                float(data["rotation_deg"]) if data.get("rotation_deg") is not None else None
            ),
            lower_size=(float(data["lower_size"]) if data.get("lower_size") else None),
            upper_size=(float(data["upper_size"]) if data.get("upper_size") else None),
            deviation_mm=(float(data["deviation_mm"]) if data.get("deviation_mm") else None),
            segment_id=int(data["segment_id"]) if data.get("segment_id") is not None else None,
        )

    def validate(self) -> None:
        # Нижние секции могут иметь высоту 0
        if self.height < 0 or (self.height == 0 and self.name.lower() not in ("нижняя", "нижняя секция")):
            raise ValueError(f"Высота секции '{self.name}' должна быть > 0")
        if self.shape not in SUPPORTED_SHAPES:
            raise ValueError(f"Форма секции '{self.name}' не поддерживается: {self.shape}")
        if self.faces is not None and int(self.faces) < 3:
            raise ValueError(f"Секция '{self.name}' должна иметь минимум 3 грани")
        if self.rotation_deg is not None and not math.isfinite(self.rotation_deg):
            raise ValueError(f"Некорректный угол поворота в секции '{self.name}'")


@dataclass
class LegacyTowerBlueprint:
    """Полное описание параметров синтетической башни."""

    tower_type: str = "prism"
    faces: int = 8
    base_size: float = 4.0
    top_size: float = 3.0
    total_height: float = 30.0
    sections: list[SectionSpec] = field(default_factory=list)
    instrument_distance: float = 60.0
    instrument_angle_deg: float = 0.0
    instrument_height: float = 1.7
    base_rotation_deg: float = 0.0
    default_deviation_mm: float = 5.0
    orientation: str = "bottom_up"
    metadata: dict[str, Any] = field(default_factory=dict)
    global_tilt_mm: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "tower_type": self.tower_type,
            "faces": self.faces,
            "base_size": self.base_size,
            "top_size": self.top_size,
            "total_height": self.total_height,
            "sections": [section.to_dict() for section in self.sections],
            "instrument_distance": self.instrument_distance,
            "instrument_angle_deg": self.instrument_angle_deg,
            "instrument_height": self.instrument_height,
            "base_rotation_deg": self.base_rotation_deg,
            "default_deviation_mm": self.default_deviation_mm,
            "orientation": self.orientation,
            "metadata": self.metadata,
            "global_tilt_mm": self.global_tilt_mm,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> LegacyTowerBlueprint:
        sections_data = data.get("sections", []) or []
        sections = [SectionSpec.from_dict(section) for section in sections_data]
        return LegacyTowerBlueprint(
            tower_type=data.get("tower_type", "prism"),
            faces=int(data.get("faces", 8)),
            base_size=float(data.get("base_size", 4.0)),
            top_size=float(data.get("top_size", 3.0)),
            total_height=float(data.get("total_height", 30.0)),
            sections=sections,
            instrument_distance=float(data.get("instrument_distance", 60.0)),
            instrument_angle_deg=float(data.get("instrument_angle_deg", 0.0)),
            instrument_height=float(data.get("instrument_height", 1.7)),
            base_rotation_deg=float(data.get("base_rotation_deg", 0.0)),
            default_deviation_mm=float(data.get("default_deviation_mm", 5.0)),
            orientation=data.get("orientation", "bottom_up"),
            metadata=data.get("metadata", {}),
            global_tilt_mm=float(data.get("global_tilt_mm", data.get("metadata", {}).get("global_tilt_mm", 0.0)) or 0.0),
        )

    def ensure_sections(self) -> list[SectionSpec]:
        """
        Гарантирует наличие хотя бы одной секции.
        Если пользователь не задал секции, создаём одну секцию на всю высоту.
        """
        if self.sections:
            return list(self.sections)
        default_section = SectionSpec(
            name="Секция 1",
            height=self.total_height,
            shape=self.tower_type,
            lower_size=self.base_size,
            upper_size=self.top_size if self.tower_type == "truncated_pyramid" else self.base_size,
            deviation_mm=self.default_deviation_mm,
            faces=self.faces,
            rotation_deg=self.base_rotation_deg,
            segment_id=1,
        )
        return [default_section]

    def get_sections_bottom_up(self) -> list[SectionSpec]:
        sections = self.ensure_sections()
        if self.orientation == "top_down":
            return list(reversed(sections))
        return sections

    def get_sections_top_down(self) -> list[SectionSpec]:
        sections = self.ensure_sections()
        if self.orientation == "top_down":
            return sections
        return list(reversed(sections))

    def validate(self) -> None:
        if self.orientation not in {"bottom_up", "top_down"}:
            self.orientation = "bottom_up"
        if self.base_size <= 0:
            raise ValueError("Размер нижней секции должен быть > 0")
        self.metadata = dict(self.metadata or {})
        sections = self.get_sections_bottom_up()
        if not sections:
            raise ValueError("Не заданы секции башни")

        base_faces = max(3, int(self.faces))
        base_rotation = float(self.base_rotation_deg)
        prev_upper_size: float | None = None
        current_segment = 1
        for idx, section in enumerate(sections):
            if not section.shape:
                section.shape = self.tower_type
            if section.faces is None:
                section.faces = base_faces if idx == 0 else sections[idx - 1].faces
            section.faces = max(3, int(section.faces))
            if section.rotation_deg is None:
                section.rotation_deg = base_rotation if idx == 0 else sections[idx - 1].rotation_deg
            if section.segment_id is None:
                if idx == 0:
                    current_segment = 1
                else:
                    prev_section = sections[idx - 1]
                    if section.faces != prev_section.faces or section.shape != prev_section.shape:
                        current_segment = (prev_section.segment_id or current_segment) + 1
                    else:
                        current_segment = prev_section.segment_id or current_segment
                section.segment_id = current_segment
            else:
                current_segment = int(section.segment_id)
                if current_segment <= 0:
                    raise ValueError("segment_id должен быть положительным целым числом")
            section.validate()

            lower_default = section.lower_size
            if lower_default is None:
                lower_default = prev_upper_size if prev_upper_size is not None else self.base_size
            if lower_default is None or lower_default <= 0:
                raise ValueError(f"Некорректный нижний размер в секции '{section.name}'")

            if section.shape == "prism":
                section.lower_size = float(lower_default)
                upper = section.upper_size if section.upper_size is not None else section.lower_size
                section.upper_size = float(max(upper, 1e-6))
            elif section.shape == "truncated_pyramid":
                lower = float(lower_default)
                upper = section.upper_size
                if upper is None:
                    fallback_upper = (
                        self.top_size if idx == len(sections) - 1 and self.top_size > 0 else lower - 0.01
                    )
                    upper = max(fallback_upper, 0.01)
                upper = float(upper)
                if upper >= lower:
                    raise ValueError(f"В секции '{section.name}' нижний размер должен быть больше верхнего")
                section.lower_size = lower
                section.upper_size = upper
            else:
                raise ValueError(f"Форма секции '{section.name}' не поддерживается")

            prev_upper_size = section.upper_size

        self.total_height = sum(section.height for section in sections)
        if self.total_height <= 0:
            raise ValueError("Суммарная высота секций должна быть > 0")
        if prev_upper_size is not None:
            self.top_size = float(prev_upper_size)
        else:
            self.top_size = self.base_size
        self.global_tilt_mm = max(0.0, float(self.global_tilt_mm or 0.0))
        self.sections = sections
        if sections:
            self.faces = sections[0].faces or self.faces

        segments_meta: list[dict[str, Any]] = []
        for section in sections:
            found = next((seg for seg in segments_meta if seg["id"] == section.segment_id), None)
            if not found:
                found = {
                    "id": section.segment_id,
                    "faces": section.faces,
                    "shape": section.shape,
                    "sections": [],
                }
                segments_meta.append(found)
            found["sections"].append(section.name)
        self.metadata["segments"] = segments_meta


@dataclass
class TowerSectionSpec:
    """Описывает отдельную секцию внутри части башни."""

    name: str
    height: float
    offset_x: float = 0.0
    offset_y: float = 0.0
    lattice_type: str = "cross"
    profile_spec: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        # Нижние секции могут иметь высоту 0
        if self.height < 0 or (self.height == 0 and self.name.lower() not in ("нижняя", "нижняя секция")):
            raise ValueError(f"Высота секции '{self.name}' должна быть > 0")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "height": self.height,
            "offset_x": self.offset_x,
            "offset_y": self.offset_y,
            "lattice_type": self.lattice_type,
            "profile_spec": self.profile_spec,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> TowerSectionSpec:
        return TowerSectionSpec(
            name=data.get("name", "Секция"),
            height=float(data.get("height", 0.0)),
            offset_x=float(data.get("offset_x", 0.0)),
            offset_y=float(data.get("offset_y", 0.0)),
            lattice_type=data.get("lattice_type", "cross"),
            profile_spec=data.get("profile_spec", {}),
        )


@dataclass
class TowerSegmentSpec:
    """Описание составной части башни в новой модели."""

    name: str
    shape: str = "prism"
    faces: int = 4
    height: float = 10.0
    levels: int = 1
    base_size: float = 4.0
    top_size: float | None = None
    deviation_mm: float = 0.0
    sections: list[TowerSectionSpec] = field(default_factory=list)
    lattice_type: str = "cross"
    profile_spec: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if self.shape not in SUPPORTED_SHAPES:
            raise ValueError(f"Форма части '{self.name}' не поддерживается: {self.shape}")
        if self.faces < 3:
            raise ValueError(f"Часть '{self.name}' должна иметь минимум 3 грани")
        if self.height <= 0:
            raise ValueError(f"Высота части '{self.name}' должна быть > 0")
        if self.levels <= 0:
            raise ValueError(f"Количество поясов в части '{self.name}' должно быть > 0")
        if self.base_size <= 0:
            raise ValueError(f"Размер основания части '{self.name}' должен быть > 0")
        if self.shape == "truncated_pyramid":
            if self.top_size is None or self.top_size <= 0:
                raise ValueError(f"У части '{self.name}' нужно указать верхний размер > 0")
            if self.top_size >= self.base_size:
                raise ValueError(
                    f"В части '{self.name}' верхний размер должен быть меньше нижнего"
                )
        else:
            # Призма всегда использует одинаковый размер по высоте
            self.top_size = self.base_size
        if self.sections:
            for section in self.sections:
                section.validate()
            total_height = sum(section.height for section in self.sections)
            if total_height <= 0:
                raise ValueError(f"В части '{self.name}' сумма высот секций должна быть > 0")
            if abs(total_height - self.height) > 1e-3:
                raise ValueError(
                    f"Сумма высот секций части '{self.name}' ({total_height:.3f}) не совпадает с высотой части {self.height:.3f}"
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "shape": self.shape,
            "faces": self.faces,
            "height": self.height,
            "levels": self.levels,
            "base_size": self.base_size,
            "top_size": self.top_size,
            "deviation_mm": self.deviation_mm,
            "sections": [section.to_dict() for section in self.sections],
            "lattice_type": self.lattice_type,
            "profile_spec": self.profile_spec,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> TowerSegmentSpec:
        return TowerSegmentSpec(
            name=data.get("name", "Часть"),
            shape=data.get("shape", "prism"),
            faces=int(data.get("faces", 4)),
            height=float(data.get("height", 10.0)),
            levels=int(data.get("levels", 1)),
            base_size=float(data.get("base_size", 4.0)),
            top_size=float(data["top_size"]) if data.get("top_size") is not None else None,
            deviation_mm=float(data.get("deviation_mm", 0.0)),
            sections=[TowerSectionSpec.from_dict(item) for item in data.get("sections", [])],
            lattice_type=data.get("lattice_type", "cross"),
            profile_spec=data.get("profile_spec", {}),
        )


@dataclass
class TowerBlueprintV2:
    """Новая модель башни, описывающая составные части."""

    segments: list[TowerSegmentSpec] = field(default_factory=list)
    instrument_distance: float = 60.0
    instrument_angle_deg: float = 0.0
    instrument_height: float = 1.7
    base_rotation_deg: float = 0.0
    default_deviation_mm: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def total_height(self) -> float:
        return sum(segment.height for segment in self.segments)

    def validate(self) -> None:
        if not self.segments:
            raise ValueError("Не заданы части башни")
        for segment in self.segments:
            segment.validate()
        if self.instrument_distance <= 0:
            raise ValueError("Расстояние до прибора должно быть > 0")
        self.metadata = dict(self.metadata or {})
        self.metadata["parts"] = [
            {
                "name": segment.name,
                "shape": segment.shape,
                "faces": segment.faces,
                "height": segment.height,
                "levels": segment.levels,
                "base_size": segment.base_size,
                "top_size": segment.top_size if segment.top_size is not None else segment.base_size,
                "sections": [section.to_dict() for section in segment.sections],
            }
            for segment in self.segments
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "segments": [segment.to_dict() for segment in self.segments],
            "instrument_distance": self.instrument_distance,
            "instrument_angle_deg": self.instrument_angle_deg,
            "instrument_height": self.instrument_height,
            "base_rotation_deg": self.base_rotation_deg,
            "default_deviation_mm": self.default_deviation_mm,
            "metadata": self.metadata,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> TowerBlueprintV2:
        if "segments" in data:
            segments_data = data.get("segments") or []
            segments = [TowerSegmentSpec.from_dict(item) for item in segments_data]
        else:
            # Легаси-структура: преобразуем секции в части
            legacy_sections = data.get("sections") or []
            segments = []
            if legacy_sections:
                faces = int(data.get("faces", 4))
                for idx, section in enumerate(legacy_sections, start=1):
                    lower = float(section.get("lower_size") or data.get("base_size", 4.0))
                    upper = float(section.get("upper_size") or lower)
                    segments.append(
                        TowerSegmentSpec(
                            name=section.get("name", f"Часть {idx}"),
                            shape=section.get("shape", data.get("tower_type", "prism")),
                            faces=int(section.get("faces", faces)),
                            height=float(section.get("height", data.get("total_height", 10.0))),
                            levels=1,
                            base_size=lower,
                            top_size=upper,
                            deviation_mm=float(
                                section.get("deviation_mm", data.get("default_deviation_mm", 0.0))
                            ),
                        )
                    )
            else:
                # Минимальная часть по данным верхнего уровня
                segments.append(
                    TowerSegmentSpec(
                        name=data.get("name", "Часть 1"),
                        shape=data.get("tower_type", "prism"),
                        faces=int(data.get("faces", 4)),
                        height=float(data.get("total_height", 10.0)),
                        levels=int(data.get("levels", 1)),
                        base_size=float(data.get("base_size", 4.0)),
                        top_size=float(data.get("top_size", data.get("base_size", 4.0))),
                        deviation_mm=float(data.get("default_deviation_mm", 0.0)),
                    )
                )

        return TowerBlueprintV2(
            segments=segments,
            instrument_distance=float(data.get("instrument_distance", 60.0)),
            instrument_angle_deg=float(data.get("instrument_angle_deg", 0.0)),
            instrument_height=float(data.get("instrument_height", 1.7)),
            base_rotation_deg=float(data.get("base_rotation_deg", 0.0)),
            default_deviation_mm=float(data.get("default_deviation_mm", 0.0)),
            metadata=data.get("metadata", {}),
        )

    @staticmethod
    def from_legacy_blueprint(legacy: LegacyTowerBlueprint) -> TowerBlueprintV2:
        segments = []
        for idx, section in enumerate(legacy.get_sections_bottom_up(), start=1):
            segments.append(
                TowerSegmentSpec(
                    name=section.name,
                    shape=section.shape,
                    faces=int(section.faces or legacy.faces),
                    height=section.height,
                    levels=1,
                    base_size=float(section.lower_size or legacy.base_size),
                    top_size=float(section.upper_size or section.lower_size or legacy.top_size),
                    deviation_mm=float(section.deviation_mm or legacy.default_deviation_mm),
                )
            )
        blueprint = TowerBlueprintV2(
            segments=segments,
            instrument_distance=legacy.instrument_distance,
            instrument_angle_deg=legacy.instrument_angle_deg,
            instrument_height=legacy.instrument_height,
            base_rotation_deg=legacy.base_rotation_deg,
            default_deviation_mm=legacy.default_deviation_mm,
            metadata=dict(legacy.metadata),
        )
        blueprint.validate()
        return blueprint


def _section_deviation(section: SectionSpec, default_mm: float) -> float:
    value_mm = section.deviation_mm if section.deviation_mm is not None else default_mm
    return max(value_mm, 0.0) / 1000.0


def _resolve_section_radii(
    section: SectionSpec,
    current_radius: float,
) -> tuple[float, float]:
    """Возвращает радиусы нижнего и верхнего пояса секции."""
    lower_radius = _size_to_radius(section.lower_size) if section.lower_size else current_radius
    upper_radius = _size_to_radius(section.upper_size) if section.upper_size else lower_radius
    return lower_radius, upper_radius


def _build_level_points(
    *,
    z_value: float,
    center: tuple[float, float],
    radius: float,
    faces: int,
    rotation_deg: float,
    deviation_m: float,
    rng: np.random.Generator,
    reference_station_xy: tuple[float, float] | None = None,
) -> list[tuple[float, float, float]]:
    """Возвращает набор точек уровня (горизонтального сечения)."""
    return _build_polygon_points(
        center=center,
        radius=radius,
        faces=faces,
        z_value=z_value,
        rotation_deg=rotation_deg,
        deviation_m=deviation_m,
        rng=rng,
        reference_station_xy=reference_station_xy,
    )


def _vector_from_polar(length: float, angle_rad: float) -> np.ndarray:
    return np.array(
        [
            length * math.cos(angle_rad),
            length * math.sin(angle_rad),
        ],
        dtype=float,
    )


def _vector_angle_deg(vector: np.ndarray) -> float:
    return (math.degrees(math.atan2(vector[1], vector[0])) + 360.0) % 360.0


def _vector_from_tilt(mm_value: float | None, direction_deg: float) -> np.ndarray:
    if mm_value is None:
        return np.zeros(2, dtype=float)
    length = max(mm_value, 0.0) / 1000.0
    return _vector_from_polar(length, _deg2rad(direction_deg))


def _absolute_center_from_values(
    mm_value: float | None,
    direction_deg: float,
    fallback: np.ndarray,
) -> np.ndarray:
    if mm_value is None:
        return np.array(fallback, dtype=float)
    return _vector_from_tilt(mm_value, direction_deg)


def _apply_global_tilt_to_sections(
    sections: list[SectionSpec],
    rng: np.random.Generator,
    *,
    tilt_mm: float,
    direction_deg: float | None = None,
) -> None:
    """Распределяет глобальный крен между секциями без индивидуальных смещений."""
    if tilt_mm <= 0 or not sections:
        return
    eligible_indices = [
        idx
        for idx, section in enumerate(sections)
        if section.lower_tilt_mm is None and section.upper_tilt_mm is None
    ]
    if not eligible_indices:
        return

    direction = (
        float(direction_deg)
        if direction_deg is not None
        else float(rng.uniform(0.0, 360.0))
    )
    target_vector = _vector_from_tilt(tilt_mm, direction)
    if np.linalg.norm(target_vector) <= 1e-9:
        return

    weights = rng.random(len(eligible_indices))
    if not np.any(weights):
        weights = np.ones(len(eligible_indices), dtype=float)
    cumulative = np.cumsum(weights / weights.sum())

    for idx, fraction in zip(eligible_indices, cumulative):
        section_vector = target_vector * float(fraction)
        magnitude_mm = float(np.linalg.norm(section_vector) * 1000.0)
        if magnitude_mm <= 1e-9:
            sections[idx].upper_tilt_mm = 0.0
            sections[idx].upper_tilt_direction_deg = 0.0
            continue
        sections[idx].upper_tilt_mm = magnitude_mm
        sections[idx].upper_tilt_direction_deg = _vector_angle_deg(section_vector)


def _segment_radius(segment: TowerSegmentSpec, level_fraction: float) -> float:
    """Возвращает радиус по уровню внутри части."""
    base_radius = _size_to_radius(segment.base_size)
    top_value = segment.top_size if segment.top_size is not None else segment.base_size
    top_radius = _size_to_radius(top_value)
    if segment.shape == "prism":
        return base_radius
    level_fraction = float(min(max(level_fraction, 0.0), 1.0))
    return base_radius - (base_radius - top_radius) * level_fraction


def _segment_level_descriptors(
    segment: TowerSegmentSpec,
    start_center: np.ndarray,
) -> tuple[list[dict[str, Any]], np.ndarray]:
    """Формирует список уровней внутри части с учётом секций и смещений."""
    descriptors: list[dict[str, Any]] = []
    center = np.array(start_center, dtype=float)
    descriptors.append(
        {
            "height": 0.0,
            "center": center.copy(),
            "section_index": 0,
            "section_name": None,
        }
    )
    if segment.sections:
        cumulative = 0.0
        for idx, section in enumerate(segment.sections, start=1):
            cumulative += section.height
            center = center + np.array([section.offset_x, section.offset_y], dtype=float)
            descriptors.append(
                {
                    "height": cumulative,
                    "center": center.copy(),
                    "section_index": idx,
                    "section_name": section.name,
                }
            )
    else:
        level_step = segment.height / float(max(segment.levels, 1))
        for local_level in range(1, segment.levels + 1):
            cumulative = level_step * local_level
            descriptors.append(
                {
                    "height": cumulative,
                    "center": center.copy(),
                    "section_index": local_level,
                    "section_name": None,
                }
            )
    return descriptors, center


def build_tower_geometry_v2(
    blueprint: TowerBlueprintV2,
    *,
    seed: int | None = None,
) -> dict[str, Any]:
    """
    Создаёт геометрию башни по новой модели, основанной на частях.
    """
    blueprint.validate()
    rng = np.random.default_rng(seed)

    instrument_distance = (
        float(blueprint.instrument_distance) if hasattr(blueprint, 'instrument_distance') else 60.0
    )
    instrument_angle_deg = (
        float(blueprint.instrument_angle_deg) if hasattr(blueprint, 'instrument_angle_deg') else 0.0
    )
    instrument_height = (
        float(blueprint.instrument_height) if hasattr(blueprint, 'instrument_height') else 1.7
    )
    tower_offset_x = instrument_distance * math.cos(_deg2rad(instrument_angle_deg))
    tower_offset_y = instrument_distance * math.sin(_deg2rad(instrument_angle_deg))
    local_reference_station_xy = (-tower_offset_x, -tower_offset_y)

    current_height = 0.0
    level_index = 1
    levels: list[dict[str, Any]] = []
    current_center = np.array([0.0, 0.0], dtype=float)

    for part_index, segment in enumerate(blueprint.segments, start=1):
        segment.validate()
        # Используем default_deviation_mm из blueprint для случайного смещения точек в плоскости XY
        deviation_m = blueprint.default_deviation_mm / 1000.0

        descriptors, final_center = _segment_level_descriptors(segment, current_center)
        for descriptor in descriptors:
            z_value = current_height + descriptor["height"]
            fraction = descriptor["height"] / segment.height if segment.height else 0.0
            radius = _segment_radius(segment, fraction)
            center_tuple = tuple(descriptor["center"])
            level_points = _build_level_points(
                z_value=z_value,
                center=center_tuple,
                radius=radius,
                faces=segment.faces,
                rotation_deg=blueprint.base_rotation_deg,
                deviation_m=deviation_m,
                rng=rng,
                reference_station_xy=local_reference_station_xy,
            )
            if level_points is None or len(level_points) == 0:
                logger.warning(f"Не удалось создать точки для уровня {level_index}, сегмент {part_index}, высота {z_value:.2f}м")
                continue
            levels.append(
                {
                    "index": level_index,
                    "height": z_value,
                    "points": level_points,
                    "segment": part_index,
                    "segment_name": segment.name,
                    "segment_level": descriptor["section_index"],
                    "faces": segment.faces,
                    "center": center_tuple,
                    "section_name": descriptor["section_name"],
                }
            )
            level_index += 1
        current_height += segment.height
        current_center = final_center.copy()

    rows: list[dict[str, Any]] = []
    for level in levels:
        segment_id = level["segment"]
        level_points = level.get("points")
        if level_points is None:
            logger.warning(f"Пропущен уровень {level.get('index', 'unknown')}: points is None")
            continue
        for belt_idx, point in enumerate(level_points, start=1):
            rows.append(
                {
                    "name": f"P{segment_id:02d}B{belt_idx:02d}L{level['index']:02d}",
                    "x": float(point[0]),
                    "y": float(point[1]),
                    "z": float(point[2]),
                    "belt": belt_idx,
                    "segment": segment_id,
                    "segment_level": level["segment_level"],
                    "segment_name": level["segment_name"],
                    "level": level["index"],
                    "faces": level["faces"],
                    "generated": True,
                    "is_station": False,
                    "center_x": float(level["center"][0]),
                    "center_y": float(level["center"][1]),
                }
            )

    # Точка стояния - начало координат (0,0,0)
    # Башня строится на расстоянии от точки стояния
    instrument_distance = float(blueprint.instrument_distance) if hasattr(blueprint, 'instrument_distance') else 60.0
    instrument_angle_deg = float(blueprint.instrument_angle_deg) if hasattr(blueprint, 'instrument_angle_deg') else 0.0
    instrument_height = float(blueprint.instrument_height) if hasattr(blueprint, 'instrument_height') else 1.7

    standing_point = {
        "x": 0.0,
        "y": 0.0,
        "z": instrument_height,
    }

    # Вычисляем смещение башни от точки стояния
    # Башня должна быть смещена на instrument_distance в направлении instrument_angle_deg
    tower_offset_x = instrument_distance * math.cos(_deg2rad(instrument_angle_deg))
    tower_offset_y = instrument_distance * math.sin(_deg2rad(instrument_angle_deg))

    logger.info(f"Точка стояния: X=0.000 м, Y=0.000 м, Z={standing_point['z']:.3f} м (начало координат XYZ)")
    logger.info(f"Смещение башни от точки стояния: X={tower_offset_x:.3f} м, Y={tower_offset_y:.3f} м (расстояние={instrument_distance:.1f} м, угол={instrument_angle_deg:.1f}°)")

    # Смещаем все точки башни от точки стояния
    for row in rows:
        row["x"] = float(row["x"]) + tower_offset_x
        row["y"] = float(row["y"]) + tower_offset_y

    rows.append(
        {
            "name": "STATION_1",
            "x": standing_point["x"],
            "y": standing_point["y"],
            "z": standing_point["z"],
            "belt": np.nan,
            "segment": np.nan,
            "segment_level": np.nan,
            "segment_name": None,
            "level": np.nan,
            "faces": np.nan,
            "generated": True,
            "is_station": True,
        }
    )

    data = pd.DataFrame(rows)

    # Обновляем section_data с учетом смещения башни от точки стояния
    # Дедуплицируем уровни по высоте, чтобы избежать задваивания секций на границах частей
    height_tolerance = 0.01  # Допуск для определения одинаковой высоты (1 см)

    # Группируем levels по высоте
    levels_by_height: dict[float, list[dict[str, Any]]] = {}
    for level in levels:
        level_height = level["height"]
        # Ищем существующую группу для этой высоты
        matched_height = None
        for existing_height in levels_by_height:
            if abs(level_height - existing_height) <= height_tolerance:
                matched_height = existing_height
                break

        if matched_height is not None:
            # Добавляем к существующей группе
            levels_by_height[matched_height].append(level)
        else:
            # Создаем новую группу
            levels_by_height[level_height] = [level]

    section_data = []
    for height, grouped_levels in sorted(levels_by_height.items()):
        if len(grouped_levels) == 1:
            # Одна секция на этой высоте - обычный случай
            level = grouped_levels[0]
            # Смещаем точки секции на смещение башни
            shifted_points = [
                (float(p[0]) + tower_offset_x, float(p[1]) + tower_offset_y, float(p[2]))
                for p in level["points"]
            ]
            # Смещаем центр секции
            shifted_center = (
                float(level["center"][0]) + tower_offset_x,
                float(level["center"][1]) + tower_offset_y
            )

            section_info = {
                "height": height,
                "points": shifted_points,
                "belt_nums": list(range(1, level["faces"] + 1)),
                "segment": level["segment"],
                "segment_name": level["segment_name"],
                "segment_level": level["segment_level"],
                "faces": level["faces"],
                "center": shifted_center,
                "section_name": level.get("section_name"),
                "tower_part": level["segment"],  # segment соответствует части
            }
            section_data.append(section_info)
        else:
            # Несколько уровней на одной высоте (граничная секция между частями)
            # Объединяем их в одну секцию с информацией о принадлежности к нескольким частям
            logger.info(f"Объединение {len(grouped_levels)} уровней на высоте {height:.3f}м (граничная секция между частями)")

            # Собираем все точки из всех уровней (они должны быть одинаковыми или очень близкими)
            all_points = []
            all_belt_nums = set()
            all_segments = set()
            segment_names = []
            section_names = []

            for level in grouped_levels:
                shifted_points = [
                    (float(p[0]) + tower_offset_x, float(p[1]) + tower_offset_y, float(p[2]))
                    for p in level["points"]
                ]
                # Добавляем уникальные точки (если их еще нет)
                for point in shifted_points:
                    if point not in all_points:
                        all_points.append(point)

                all_belt_nums.update(range(1, level["faces"] + 1))
                all_segments.add(level["segment"])
                if level.get("segment_name"):
                    segment_names.append(level["segment_name"])
                if level.get("section_name"):
                    section_names.append(level["section_name"])

            # Усредняем центры всех уровней
            centers_x = [level["center"][0] + tower_offset_x for level in grouped_levels]
            centers_y = [level["center"][1] + tower_offset_y for level in grouped_levels]
            averaged_center = (
                float(np.mean(centers_x)),
                float(np.mean(centers_y))
            )

            # Определяем основную часть (нижняя часть, если граница)
            primary_segment = min(all_segments)

            section_info = {
                "height": height,
                "points": all_points,
                "belt_nums": sorted(all_belt_nums),
                "segment": primary_segment,  # Основная часть
                "segment_name": segment_names[0] if segment_names else None,
                "segment_level": grouped_levels[0]["segment_level"],
                "faces": max(level["faces"] for level in grouped_levels),
                "center": averaged_center,
                "section_name": section_names[0] if section_names else None,
                "tower_part": primary_segment,  # Основная часть
                "tower_part_memberships": sorted(all_segments),  # Принадлежность ко всем частям
                "is_part_boundary": True,  # Граничная секция
            }
            section_data.append(section_info)

            logger.debug(f"  Объединенная секция: части {sorted(all_segments)}, поясов {len(sorted(all_belt_nums))}, точек {len(all_points)}")

    metadata = {
        "standing_point": standing_point,
        "total_height": blueprint.total_height(),
        "levels": len(levels),
        "parts": blueprint.metadata.get("parts", []),
        "belts": max((segment.faces for segment in blueprint.segments), default=0),
    }

    logger.info(
        "Сгенерирована башня (новая модель): частей=%s, высота=%.2f м, точек=%s",
        len(blueprint.segments),
        metadata["total_height"],
        len(data),
    )

    return {
        "data": data,
        "section_data": section_data,
        "standing_point": standing_point,
        "blueprint": blueprint,
        "metadata": metadata,
    }


def build_tower_geometry(
    blueprint: LegacyTowerBlueprint,
    *,
    seed: int | None = None,
) -> dict[str, Any]:
    """
    Создаёт геометрию башни по заданному blueprint.

    Returns:
        {
            "data": pd.DataFrame,
            "section_data": List[Dict],
            "standing_point": Dict[str, float],
            "blueprint": TowerBlueprint
        }
    """
    blueprint.validate()
    rng = np.random.default_rng(seed)

    instrument_distance = (
        float(blueprint.instrument_distance) if hasattr(blueprint, 'instrument_distance') else 60.0
    )
    instrument_angle_deg = (
        float(blueprint.instrument_angle_deg) if hasattr(blueprint, 'instrument_angle_deg') else 0.0
    )
    tower_offset_x = instrument_distance * math.cos(_deg2rad(instrument_angle_deg))
    tower_offset_y = instrument_distance * math.sin(_deg2rad(instrument_angle_deg))
    local_reference_station_xy = (-tower_offset_x, -tower_offset_y)

    sections = blueprint.get_sections_bottom_up()
    global_tilt_mm = float(
        getattr(blueprint, "global_tilt_mm", 0.0)
        or blueprint.metadata.get("global_tilt_mm", 0.0)
        or 0.0
    )
    _apply_global_tilt_to_sections(
        sections,
        rng,
        tilt_mm=global_tilt_mm,
        direction_deg=blueprint.metadata.get("global_tilt_direction_deg"),
    )
    levels: list[dict[str, Any]] = []

    current_center = np.array([0.0, 0.0], dtype=float)
    current_height = 0.0
    current_radius = _size_to_radius(blueprint.base_size)
    level_index = 1
    for idx, section in enumerate(sections):
        section.validate()
        deviation_m = _section_deviation(section, blueprint.default_deviation_mm)
        section_faces = max(3, int(section.faces or blueprint.faces))
        section_rotation = float(
            section.rotation_deg if section.rotation_deg is not None else blueprint.base_rotation_deg
        )
        lower_radius, upper_radius = _resolve_section_radii(section, current_radius)

        lower_center = _absolute_center_from_values(
            section.lower_tilt_mm,
            section.lower_tilt_direction_deg,
            current_center,
        )

        need_lower_level = (
            not levels
            or not math.isclose(levels[-1]["height"], current_height, abs_tol=1e-6)
            or levels[-1].get("segment") != section.segment_id
            or levels[-1].get("faces") != section_faces
        )
        if need_lower_level:
            level_points = _build_level_points(
                z_value=current_height,
                center=tuple(lower_center),
                radius=lower_radius,
                faces=section_faces,
                rotation_deg=section_rotation,
                deviation_m=deviation_m,
                rng=rng,
                reference_station_xy=local_reference_station_xy,
            )
            levels.append(
                {
                    "index": level_index,
                    "height": current_height,
                    "points": level_points,
                    "section": section.name,
                    "segment": int(section.segment_id or 1),
                    "faces": section_faces,
                }
            )
            level_index += 1

        incremental_center = lower_center + _vector_from_tilt(
            section.tilt_mm,
            section.tilt_direction_deg,
        )
        upper_center = _absolute_center_from_values(
            section.upper_tilt_mm,
            section.upper_tilt_direction_deg,
            incremental_center,
        )
        current_height += section.height
        current_height = round(current_height, 6)

        level_points = _build_level_points(
            z_value=current_height,
            center=tuple(upper_center),
            radius=upper_radius,
            faces=section_faces,
            rotation_deg=section_rotation,
            deviation_m=deviation_m,
            rng=rng,
            reference_station_xy=local_reference_station_xy,
        )
        levels.append(
            {
                "index": level_index,
                "height": current_height,
                "points": level_points,
                "section": section.name,
                "segment": int(section.segment_id or 1),
                "faces": section_faces,
            }
        )
        level_index += 1

        current_center = upper_center
        current_radius = upper_radius

    rows: list[dict[str, Any]] = []
    belt_tracks: dict[tuple[int, int], list[tuple[float, float, float]]] = defaultdict(list)
    point_index_counter = 1

    for level in levels:
        belt_nums: list[int] = []
        segment_id = int(level.get("segment", 1))
        for vertex_idx, point in enumerate(level["points"], start=1):
            belt_nums.append(vertex_idx)
            belt_tracks[(segment_id, vertex_idx)].append(point)
            rows.append(
                {
                    "name": f"B{vertex_idx:02d}L{level['index']:02d}",
                    "x": float(point[0]),
                    "y": float(point[1]),
                    "z": float(point[2]),
                    "belt": vertex_idx,
                    "level": level["index"],
                    "section_name": level["section"],
                    "segment": segment_id,
                    "faces": level.get("faces"),
                    "point_index": point_index_counter,
                    "is_station": False,
                    "tower_part": segment_id,  # Добавляем сразу для совместимости
                    "tower_part_memberships": None,  # Будет заполнено позже при необходимости
                    "is_part_boundary": False,
                }
            )
            point_index_counter += 1
        level["belt_nums"] = belt_nums

    # Точка стояния - начало координат (0,0,0)
    # Башня строится на расстоянии от точки стояния
    instrument_distance = float(blueprint.instrument_distance) if hasattr(blueprint, 'instrument_distance') else 60.0
    instrument_angle_deg = float(blueprint.instrument_angle_deg) if hasattr(blueprint, 'instrument_angle_deg') else 0.0

    standing_point = {
        "x": 0.0,
        "y": 0.0,
        "z": blueprint.instrument_height,
    }

    # Вычисляем смещение башни от точки стояния
    tower_offset_x = instrument_distance * math.cos(_deg2rad(instrument_angle_deg))
    tower_offset_y = instrument_distance * math.sin(_deg2rad(instrument_angle_deg))

    logger.info(f"Точка стояния: X=0.000 м, Y=0.000 м, Z={standing_point['z']:.3f} м (начало координат XYZ)")
    logger.info(f"Смещение башни от точки стояния: X={tower_offset_x:.3f} м, Y={tower_offset_y:.3f} м (расстояние={instrument_distance:.1f} м, угол={instrument_angle_deg:.1f}°)")

    # Смещаем все точки башни от точки стояния
    for row in rows:
        row["x"] = float(row["x"]) + tower_offset_x
        row["y"] = float(row["y"]) + tower_offset_y

    rows.append(
        {
            "name": "STATION_1",
            "x": standing_point["x"],
            "y": standing_point["y"],
            "z": standing_point["z"],
            "belt": np.nan,
            "level": np.nan,
            "segment": np.nan,
            "faces": np.nan,
            "section_name": None,
            "point_index": point_index_counter,
            "is_station": True,
            "tower_part": np.nan,  # Станция не относится к части башни
            "tower_part_memberships": None,
            "is_part_boundary": False,
        }
    )

    data = pd.DataFrame(rows)

    # Обновляем section_data с учетом смещения башни от точки стояния
    # Дедуплицируем уровни по высоте, чтобы избежать задваивания секций на границах частей
    height_tolerance = 0.01  # Допуск для определения одинаковой высоты (1 см)

    # Группируем levels по высоте
    levels_by_height: dict[float, list[dict[str, Any]]] = {}
    for level in levels:
        level_height = level["height"]
        # Ищем существующую группу для этой высоты
        matched_height = None
        for existing_height in levels_by_height:
            if abs(level_height - existing_height) <= height_tolerance:
                matched_height = existing_height
                break

        if matched_height is not None:
            # Добавляем к существующей группе
            levels_by_height[matched_height].append(level)
        else:
            # Создаем новую группу
            levels_by_height[level_height] = [level]

    section_data = []
    for height, grouped_levels in sorted(levels_by_height.items()):
        if len(grouped_levels) == 1:
            # Одна секция на этой высоте - обычный случай
            level = grouped_levels[0]
            # Смещаем точки секции на смещение башни
            shifted_points = [
                (float(p[0]) + tower_offset_x, float(p[1]) + tower_offset_y, float(p[2]))
                for p in level["points"]
            ]

            section_info = {
                "height": height,
                "points": shifted_points,
                "belt_nums": level.get("belt_nums", list(range(1, (level.get("faces") or blueprint.faces) + 1))),
                "segment": level.get("segment"),
                "faces": level.get("faces"),
                "section_name": level.get("section"),
            }

            # Добавляем информацию о части
            segment_id = level.get("segment")
            if segment_id is not None:
                section_info["tower_part"] = int(segment_id)

            section_data.append(section_info)
        else:
            # Несколько уровней на одной высоте (граничная секция между частями)
            logger.info(f"Объединение {len(grouped_levels)} уровней на высоте {height:.3f}м (граничная секция между частями)")

            # Собираем все точки из всех уровней
            all_points = []
            all_belt_nums = set()
            all_segments = set()
            section_names = []

            for level in grouped_levels:
                shifted_points = [
                    (float(p[0]) + tower_offset_x, float(p[1]) + tower_offset_y, float(p[2]))
                    for p in level["points"]
                ]
                # Добавляем уникальные точки (если их еще нет)
                for point in shifted_points:
                    if point not in all_points:
                        all_points.append(point)

                belt_nums = level.get("belt_nums", list(range(1, (level.get("faces") or blueprint.faces) + 1)))
                all_belt_nums.update(belt_nums)
                segment_id = level.get("segment")
                if segment_id is not None:
                    all_segments.add(int(segment_id))
                section_name = level.get("section")
                if section_name:
                    section_names.append(section_name)

            # Определяем основную часть (нижняя часть, если граница)
            primary_segment = min(all_segments) if all_segments else 1

            section_info = {
                "height": height,
                "points": all_points,
                "belt_nums": sorted(all_belt_nums),
                "segment": primary_segment,
                "faces": max((level.get("faces") or blueprint.faces) for level in grouped_levels),
                "section_name": section_names[0] if section_names else None,
                "tower_part": primary_segment,
                "tower_part_memberships": sorted(all_segments) if all_segments else [1],
                "is_part_boundary": True,
            }
            section_data.append(section_info)

            logger.debug(f"  Объединенная секция: части {sorted(all_segments)}, поясов {len(sorted(all_belt_nums))}, точек {len(all_points)}")

    max_faces = max((int(level.get("faces") or blueprint.faces) for level in levels), default=blueprint.faces)
    metadata = {
        "standing_point": standing_point,
        "total_height": current_height,
        "belts": max_faces,
        "levels": len(levels),
        "segments": blueprint.metadata.get("segments", []),
    }

    logger.info(
        "Сгенерирована башня: поясов=%s, высота=%.2f м, точек=%s",
        metadata["belts"],
        metadata["total_height"],
        len(data),
    )

    return {
        "data": data,
        "section_data": section_data,
        "standing_point": standing_point,
        "blueprint": blueprint,
        "metadata": metadata,
    }


def generate_tower_data(
    blueprint: Union[LegacyTowerBlueprint, TowerBlueprintV2, dict[str, Any]],
    *,
    seed: int | None = None,
) -> tuple[pd.DataFrame, list[dict[str, Any]], dict[str, Any]]:
    """
    Высокоуровневая функция для генерации данных.

    Returns:
        DataFrame с точками, section_data для визуализации, metadata.
    """
    geometry = build_tower_geometry_v2(_ensure_blueprint_v2(blueprint), seed=seed)
    return geometry["data"], geometry["section_data"], geometry["metadata"]


def blueprint_from_sections(
    *,
    tower_type: str,
    faces: int,
    base_size: float,
    top_size: float,
    total_height: float,
    sections: Sequence[dict[str, Any]],
    instrument_distance: float,
    instrument_angle_deg: float,
    instrument_height: float,
    base_rotation_deg: float,
    default_deviation_mm: float,
    orientation: str = "bottom_up",
) -> LegacyTowerBlueprint:
    """
    Утилита для сборки blueprint из словарей (удобно для мастера).
    """
    section_specs = [SectionSpec.from_dict(section) for section in sections]
    return LegacyTowerBlueprint(
        tower_type=tower_type,
        faces=faces,
        base_size=base_size,
        top_size=top_size,
        total_height=total_height,
        sections=section_specs,
        instrument_distance=instrument_distance,
        instrument_angle_deg=instrument_angle_deg,
        instrument_height=instrument_height,
        base_rotation_deg=base_rotation_deg,
        default_deviation_mm=default_deviation_mm,
        orientation=orientation,
    )


def append_sections(
    blueprint: LegacyTowerBlueprint,
    new_sections: Sequence[dict[str, Any] | SectionSpec],
    *,
    inherit_center: bool = True,
) -> LegacyTowerBlueprint:
    """
    Возвращает новый blueprint с добавленными секциями поверх существующих.

    Args:
        blueprint: исходный TowerBlueprint
        new_sections: iterable словарей или SectionSpec
        inherit_center: если True, нижний крен новой секции наследует верх предыдущей
    """
    source_sections = [SectionSpec.from_dict(section.to_dict()) for section in blueprint.get_sections_bottom_up()]
    if not new_sections:
        return blueprint

    if not source_sections:
        base_section = SectionSpec.from_dict(
            SectionSpec(
                name="Секция 1",
                height=blueprint.total_height,
                shape=blueprint.tower_type,
                faces=blueprint.faces,
                rotation_deg=blueprint.base_rotation_deg,
                lower_size=blueprint.base_size,
                upper_size=blueprint.top_size,
                deviation_mm=blueprint.default_deviation_mm,
            ).to_dict()
        )
        source_sections.append(base_section)

    last_section = source_sections[-1]
    appended: list[SectionSpec] = []
    next_segment = (last_section.segment_id or len(source_sections)) + 1
    inherit_tilt_mm = last_section.upper_tilt_mm if last_section.upper_tilt_mm is not None else last_section.tilt_mm
    inherit_tilt_dir = (
        last_section.upper_tilt_direction_deg
        if last_section.upper_tilt_mm is not None
        else last_section.tilt_direction_deg
    )

    for raw in new_sections:
        spec = raw if isinstance(raw, SectionSpec) else SectionSpec.from_dict(raw)
        if inherit_center and inherit_tilt_mm is not None and spec.lower_tilt_mm is None:
            spec.lower_tilt_mm = inherit_tilt_mm
            spec.lower_tilt_direction_deg = inherit_tilt_dir
        if spec.segment_id is None:
            spec.segment_id = next_segment
        appended.append(spec)

    combined_sections = source_sections + appended
    updated_blueprint = LegacyTowerBlueprint(
        tower_type=blueprint.tower_type,
        faces=blueprint.faces,
        base_size=blueprint.base_size,
        top_size=blueprint.top_size,
        total_height=sum(section.height for section in combined_sections),
        sections=[SectionSpec.from_dict(section.to_dict()) for section in combined_sections],
        instrument_distance=blueprint.instrument_distance,
        instrument_angle_deg=blueprint.instrument_angle_deg,
        instrument_height=blueprint.instrument_height,
        base_rotation_deg=blueprint.base_rotation_deg,
        default_deviation_mm=blueprint.default_deviation_mm,
        orientation="bottom_up",
        metadata=dict(blueprint.metadata),
        global_tilt_mm=blueprint.global_tilt_mm,
    )
    updated_blueprint.validate()
    return updated_blueprint


def _ensure_blueprint_v2(
    blueprint: Union[TowerBlueprintV2, LegacyTowerBlueprint, dict[str, Any]],
) -> TowerBlueprintV2:
    if isinstance(blueprint, TowerBlueprintV2):
        return blueprint
    if isinstance(blueprint, LegacyTowerBlueprint):
        return TowerBlueprintV2.from_legacy_blueprint(blueprint)
    if isinstance(blueprint, dict):
        return TowerBlueprintV2.from_dict(blueprint)
    raise TypeError("Unsupported blueprint type for tower generation")


# Обратная совместимость: большинство модулей используют имя TowerBlueprint.
TowerBlueprint = TowerBlueprintV2


def _coerce_face_count(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, float) and np.isnan(value):
        return None
    try:
        face_count = int(value)
    except (TypeError, ValueError):
        return None
    if face_count < 3:
        return None
    return face_count


def _resolve_faces_from_imported_data(
    data: pd.DataFrame,
    default_faces: int | None = None,
    belt_column: str = "belt",
) -> int:
    if 'faces' in data.columns:
        face_values = pd.to_numeric(data['faces'], errors='coerce').dropna()
        face_values = face_values[face_values >= 3]
        if not face_values.empty:
            return int(face_values.mode().iloc[0])

    explicit_faces = _coerce_face_count(default_faces)
    if explicit_faces is not None:
        return explicit_faces

    for col in ('face_track', 'part_face_track', belt_column):
        if col in data.columns:
            values = pd.to_numeric(data[col], errors='coerce').dropna()
            values = values[values > 0]
            if not values.empty:
                unique_vals = sorted({int(v) for v in values})
                if unique_vals:
                    return max(3, max(len(unique_vals), max(unique_vals)))

    return 4


def _count_levels_from_data(part_data: pd.DataFrame) -> int:
    """Определяет количество уровней из колонки height_level или по данным."""
    if 'height_level' in part_data.columns:
        hl = pd.to_numeric(part_data['height_level'], errors='coerce').dropna()
        if not hl.empty:
            return max(1, int(hl.nunique()))
    return 1


def create_blueprint_from_imported_data(
    data: pd.DataFrame,
    tower_parts_info: dict[str, Any] | None = None,
    instrument_distance: float = 60.0,
    instrument_angle_deg: float = 0.0,
    instrument_height: float = 1.7,
    base_rotation_deg: float = 0.0,
    default_faces: int | None = None,
) -> TowerBlueprintV2:
    """
    Создает TowerBlueprintV2 из импортированных данных

    Преобразует информацию о частях башни из импортированных данных
    в формат TowerBlueprintV2 для использования в конструкторе башен.

    Args:
        data: DataFrame с точками башни (может содержать колонки 'tower_part', 'part_belt')
        tower_parts_info: Информация о частях башни (опционально):
            {
                'split_height': float,
                'parts': [
                    {'part_number': 1, 'shape': 'prism', 'faces': 4, ...},
                    {'part_number': 2, 'shape': 'truncated_pyramid', 'faces': 3, ...}
                ]
            }
        instrument_distance: Расстояние до прибора
        instrument_angle_deg: Угол прибора
        instrument_height: Высота прибора
        base_rotation_deg: Поворот граней

    Returns:
        TowerBlueprintV2 с сегментами, соответствующими частям башни
    """
    segments = []

    # Исключаем точки standing
    tower_data = data.copy()
    if 'is_station' in tower_data.columns:
        tower_data = tower_data[~_build_is_station_mask(tower_data['is_station'])]

    if tower_data.empty:
        # Минимальная башня по умолчанию
        segments.append(
            TowerSegmentSpec(
                name="Часть 1",
                shape="prism",
                faces=4,
                height=10.0,
                levels=1,
                base_size=4.0,
                top_size=4.0,
            )
        )
    elif tower_parts_info and tower_parts_info.get('parts'):
        # Составная башня из tower_parts_info
        split_height = tower_parts_info.get('split_height')
        parts = tower_parts_info['parts']

        for part_info in parts:
            part_num = part_info.get('part_number', 1)
            shape = part_info.get('shape', 'prism')

            # Определяем высоту части и данные части
            part_data = pd.DataFrame()  # Инициализируем пустым DataFrame

            if part_num == 1:
                if split_height is not None:
                    part_data = tower_data[tower_data['z'] < split_height]
                    if not part_data.empty:
                        height = part_data['z'].max() - part_data['z'].min()
                    else:
                        height = 10.0
                else:
                    part_data = tower_data.copy()
                    height = part_data['z'].max() - part_data['z'].min() if not part_data.empty else 10.0
            else:
                if split_height is not None:
                    part_data = tower_data[tower_data['z'] >= split_height]
                    if not part_data.empty:
                        height = part_data['z'].max() - part_data['z'].min()
                    else:
                        height = 10.0
                else:
                    height = 10.0

            faces = _resolve_faces_from_imported_data(
                part_data,
                default_faces=part_info.get('faces', default_faces),
                belt_column='part_belt' if 'part_belt' in part_data.columns else 'belt',
            )

            # Определяем размеры (приблизительно)
            if part_data.empty:
                base_size = 4.0
                top_size = 3.0 if shape == 'truncated_pyramid' else 4.0
            else:
                # Используем средний радиус по точкам
                part_data_xy = part_data[['x', 'y']].values
                center = part_data_xy.mean(axis=0)
                radii = np.linalg.norm(part_data_xy - center, axis=1)
                avg_radius = radii.mean()
                base_size = avg_radius * 2.0  # Диаметр
                top_size = base_size * 0.75 if shape == 'truncated_pyramid' else base_size

            segments.append(
                TowerSegmentSpec(
                    name=f"Часть {part_num}",
                    shape=shape,
                    faces=faces,
                    height=max(height, 1.0),
                    levels=_count_levels_from_data(part_data),
                    base_size=max(base_size, 0.5),
                    top_size=max(top_size, 0.1) if shape == 'truncated_pyramid' else max(base_size, 0.5),
                )
            )
    elif (
        ('tower_part_memberships' in tower_data.columns and tower_data['tower_part_memberships'].notna().any())
        or ('tower_part' in tower_data.columns and tower_data['tower_part'].notna().any())
    ):
        # Составная башня из данных (учитываем расширенные принадлежности точек)
        unique_parts = set()
        if 'tower_part_memberships' in tower_data.columns:
            for value in tower_data['tower_part_memberships'].dropna():
                unique_parts.update(_decode_part_memberships(value))
        if not unique_parts and 'tower_part' in tower_data.columns:
            unique_parts.update(tower_data['tower_part'].dropna().unique())
        unique_parts = sorted(int(part) for part in unique_parts if part is not None)

        for part_num in unique_parts:
            part_data = _filter_points_by_part(tower_data, part_num)
            if part_data.empty:
                continue

            # Определяем форму и количество граней из данных
            shape = 'prism'  # По умолчанию
            faces = _resolve_faces_from_imported_data(
                part_data,
                default_faces=default_faces,
                belt_column='part_belt' if 'part_belt' in part_data.columns else 'belt',
            )

            height = part_data['z'].max() - part_data['z'].min()

            # Определяем размеры
            part_data_xy = part_data[['x', 'y']].values
            center = part_data_xy.mean(axis=0)
            radii = np.linalg.norm(part_data_xy - center, axis=1)
            avg_radius = radii.mean()
            base_size = avg_radius * 2.0

            segments.append(
                TowerSegmentSpec(
                    name=f"Часть {int(part_num)}",
                    shape=shape,
                    faces=faces,
                    height=max(height, 1.0),
                    levels=_count_levels_from_data(part_data),
                    base_size=max(base_size, 0.5),
                    top_size=max(base_size, 0.5),
                )
            )
    else:
        # Обычная башня
        height = tower_data['z'].max() - tower_data['z'].min()
        faces = _resolve_faces_from_imported_data(tower_data, default_faces=default_faces)

        # Определяем размеры
        tower_data_xy = tower_data[['x', 'y']].values
        center = tower_data_xy.mean(axis=0)
        radii = np.linalg.norm(tower_data_xy - center, axis=1)
        avg_radius = radii.mean()
        base_size = avg_radius * 2.0

        segments.append(
            TowerSegmentSpec(
                name="Часть 1",
                shape="prism",
                faces=faces,
                height=max(height, 1.0),
                levels=_count_levels_from_data(tower_data),
                base_size=max(base_size, 0.5),
                top_size=max(base_size, 0.5),
            )
        )

    if not segments:
        # Fallback: минимальная башня
        segments.append(
            TowerSegmentSpec(
                name="Часть 1",
                shape="prism",
                faces=4,
                height=10.0,
                levels=1,
                base_size=4.0,
                top_size=4.0,
            )
        )

    blueprint = TowerBlueprintV2(
        segments=segments,
        instrument_distance=instrument_distance,
        instrument_angle_deg=instrument_angle_deg,
        instrument_height=instrument_height,
        base_rotation_deg=base_rotation_deg,
        default_deviation_mm=0.0,
    )

    blueprint.validate()
    logger.info(f"Создан blueprint из импортированных данных: {len(segments)} частей")

    return blueprint


