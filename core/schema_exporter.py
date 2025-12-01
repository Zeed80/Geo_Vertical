"""
Модуль экспорта схемы башни GeoVertical в различные форматы (DXF, PDF).

Содержит:
    - Объекты данных схемы (точки, пояса, секции, ось).
    - Универсальную подготовку данных из pandas DataFrame.
    - Экспорт в DXF через ezdxf.
    - Экспорт в PDF через reportlab.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple
import math
import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Структуры данных
# -----------------------------------------------------------------------------


@dataclass
class SchemaPoint:
    """Описание точки схемы."""

    name: str
    x: float
    y: float
    z: float
    index: Optional[int] = None
    belt: Optional[int] = None
    is_station: bool = False
    attributes: Dict[str, Any] = field(default_factory=dict)

    @property
    def coords(self) -> Tuple[float, float, float]:
        return float(self.x), float(self.y), float(self.z)


@dataclass
class SectionLine:
    """Горизонтальная секция башни."""

    height: float
    points: List[Tuple[float, float, float]]
    belt_numbers: List[int] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return len(self.points) >= 2

    def centroid(self) -> Tuple[float, float, float]:
        if not self.points:
            return 0.0, 0.0, float(self.height)
        xs, ys, zs = zip(*self.points)
        return float(np.mean(xs)), float(np.mean(ys)), float(np.mean(zs))


@dataclass
class BeltPolyline:
    """Полилиния пояса."""

    belt_number: int
    points: List[Tuple[float, float, float]]
    closed: bool = True

    @property
    def is_valid(self) -> bool:
        return len(self.points) >= 2

    def centroid(self) -> Tuple[float, float, float]:
        if not self.points:
            return 0.0, 0.0, 0.0
        xs, ys, zs = zip(*self.points)
        return float(np.mean(xs)), float(np.mean(ys)), float(np.mean(zs))


@dataclass
class AxisData:
    """Описание центральной оси башни."""

    start: Tuple[float, float, float]
    end: Tuple[float, float, float]
    description: Optional[str] = None

    def length(self) -> float:
        x1, y1, z1 = self.start
        x2, y2, z2 = self.end
        return float(math.dist((x1, y1, z1), (x2, y2, z2)))

    def midpoint(self) -> Tuple[float, float, float]:
        x1, y1, z1 = self.start
        x2, y2, z2 = self.end
        return (float((x1 + x2) / 2.0), float((y1 + y2) / 2.0), float((z1 + z2) / 2.0))


@dataclass
class SchemaData:
    """Комплексное описание всей схемы для экспорта."""

    points: List[SchemaPoint]
    belts: List[BeltPolyline] = field(default_factory=list)
    sections: List[SectionLine] = field(default_factory=list)
    axis: Optional[AxisData] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def all_coordinates(self) -> Iterable[Tuple[float, float, float]]:
        for point in self.points:
            yield point.coords
        for belt in self.belts:
            for coords in belt.points:
                yield coords
        for section in self.sections:
            for coords in section.points:
                yield coords
        if self.axis:
            yield self.axis.start
            yield self.axis.end

    def bounds(self) -> Tuple[float, float, float, float, float, float]:
        coords = list(self.all_coordinates())
        if not coords:
            raise ValueError("Невозможно вычислить границы: отсутствуют геометрические данные.")
        xs, ys, zs = zip(*coords)
        return (
            float(min(xs)),
            float(max(xs)),
            float(min(ys)),
            float(max(ys)),
            float(min(zs)),
            float(max(zs)),
        )


@dataclass
class LayerConfig:
    """Названия слоёв DXF."""

    points: str = "GEO_POINTS"
    station_points: str = "GEO_STATION"
    point_labels: str = "GEO_POINT_LABELS"
    belts: str = "GEO_BELTS"
    belt_labels: str = "GEO_BELT_LABELS"
    sections: str = "GEO_SECTIONS"
    section_labels: str = "GEO_SECTION_LABELS"
    axis: str = "GEO_AXIS"
    metadata: str = "GEO_METADATA"


@dataclass
class DxfExportOptions:
    """Настройки экспорта в DXF."""

    include_points: bool = True
    include_point_labels: bool = True
    include_belts: bool = True
    include_belt_labels: bool = True
    include_sections: bool = True
    include_section_labels: bool = True
    include_axis: bool = True
    include_metadata: bool = True
    text_height: float = 0.35  # в метрах
    belt_label_height: float = 0.45
    section_label_height: float = 0.45
    metadata_text_height: float = 0.5
    metadata_column_width: float = 120.0
    layer_config: LayerConfig = field(default_factory=LayerConfig)


# -----------------------------------------------------------------------------
# Подготовка данных
# -----------------------------------------------------------------------------


def _sort_points_radially(points: pd.DataFrame) -> List[Tuple[float, float, float]]:
    """Сортирует точки по углу вокруг центра для корректной полилинии."""
    if points.empty:
        return []

    center_x = float(points["x"].mean())
    center_y = float(points["y"].mean())
    deltas_x = points["x"].to_numpy(dtype=float) - center_x
    deltas_y = points["y"].to_numpy(dtype=float) - center_y
    angles = np.arctan2(deltas_y, deltas_x)
    order = np.argsort(angles)
    sorted_points = points.iloc[order][["x", "y", "z"]].to_numpy(dtype=float)
    return [tuple(pt) for pt in sorted_points]


def _extract_station_point(points: pd.DataFrame) -> Optional[SchemaPoint]:
    if "is_station" not in points.columns:
        return None
    station_mask = points["is_station"].fillna(False).astype(bool)
    if not station_mask.any():
        return None
    station_row = points[station_mask].iloc[0]
    return SchemaPoint(
        name=str(station_row.get("name", "Station")),
        x=float(station_row["x"]),
        y=float(station_row["y"]),
        z=float(station_row["z"]),
        index=int(station_row.get("point_index")) if "point_index" in station_row else None,
        belt=int(station_row["belt"]) if pd.notna(station_row.get("belt")) else None,
        is_station=True,
    )


def build_schema_data(
    points: pd.DataFrame,
    section_data: Optional[List[Dict[str, Any]]] = None,
    processed_data: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> SchemaData:
    """
    Собирает SchemaData из pandas DataFrame и служебных структур приложения.
    """
    if points is None or points.empty:
        raise ValueError("Отсутствуют точки для экспорта схемы.")

    required_columns = {"x", "y", "z", "name"}
    missing = required_columns.difference(points.columns)
    if missing:
        raise ValueError(f"Для экспорта схемы отсутствуют обязательные колонки: {', '.join(sorted(missing))}")

    prepared_points = []
    for idx, row in points.iterrows():
        point_index = None
        if "point_index" in points.columns and pd.notna(row.get("point_index")):
            try:
                point_index = int(row["point_index"])
            except (TypeError, ValueError):
                point_index = None

        belt_value = row.get("belt")
        belt = None
        if pd.notna(belt_value):
            try:
                belt = int(belt_value)
            except (TypeError, ValueError):
                belt = None

        prepared_points.append(
            SchemaPoint(
                name=str(row.get("name", f"P{idx}")),
                x=float(row["x"]),
                y=float(row["y"]),
                z=float(row["z"]),
                index=point_index,
                belt=belt,
                is_station=bool(row.get("is_station", False)),
            )
        )

    belts: List[BeltPolyline] = []
    if "belt" in points.columns:
        unique_belts = sorted(
            {int(b) for b in points["belt"].dropna().unique() if pd.notna(b)},
            key=lambda v: v,
        )
        for belt_num in unique_belts:
            belt_points = points[
                (points["belt"].astype(float) == float(belt_num))
                & (~points.get("is_station", pd.Series(False, index=points.index)).fillna(False))
            ]
            if len(belt_points) < 2:
                continue
            ordered = _sort_points_radially(belt_points)
            belts.append(BeltPolyline(belt_number=belt_num, points=ordered, closed=True))

    sections: List[SectionLine] = []
    if section_data:
        for section_info in section_data:
            raw_points = section_info.get("points", [])
            prepared_section_points = [
                (float(p[0]), float(p[1]), float(p[2])) for p in raw_points if len(p) >= 3
            ]
            belt_nums = section_info.get("belt_nums") or section_info.get("belt_numbers") or []
            sections.append(
                SectionLine(
                    height=float(section_info.get("height", prepared_section_points[0][2] if prepared_section_points else 0.0)),
                    points=prepared_section_points,
                    belt_numbers=[int(b) for b in belt_nums if b is not None],
                )
            )

    axis_data: Optional[AxisData] = None
    if processed_data:
        axis_info = processed_data.get("axis") or {}
        if axis_info.get("valid"):
            z_min = float(points["z"].min())
            z_max = float(points["z"].max())
            z0 = float(axis_info.get("z0", z_min))
            dx = float(axis_info.get("dx", 0.0))
            dy = float(axis_info.get("dy", 0.0))
            x0 = float(axis_info.get("x0", 0.0))
            y0 = float(axis_info.get("y0", 0.0))

            def point_at_z(target_z: float) -> Tuple[float, float, float]:
                delta = target_z - z0
                return (
                    x0 + dx * delta,
                    y0 + dy * delta,
                    target_z,
                )

            description = None
            if "r_x" in axis_info or "r_y" in axis_info:
                pieces = []
                rx = axis_info.get("r_x")
                ry = axis_info.get("r_y")
                if rx is not None:
                    pieces.append(f"r_x={rx:.3f}")
                if ry is not None:
                    pieces.append(f"r_y={ry:.3f}")
                if pieces:
                    description = "Ось башни (" + ", ".join(pieces) + ")"

            axis_data = AxisData(
                start=point_at_z(z_min),
                end=point_at_z(z_max),
                description=description,
            )
        elif sections:
            # Fallback на основе секций
            lowest_section = min(sections, key=lambda s: s.height)
            highest_section = max(sections, key=lambda s: s.height)
            axis_data = AxisData(
                start=lowest_section.centroid(),
                end=highest_section.centroid(),
                description="Ось башни (по центрам секций)",
            )

    schema_metadata: Dict[str, Any] = {}
    if metadata:
        schema_metadata.update(metadata)

    schema_metadata.update(
        {
            "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "point_count": len(prepared_points),
            "belt_count": len(belts),
            "section_count": len(sections),
        }
    )

    z_values = points["z"].to_numpy(dtype=float)
    schema_metadata["height_min"] = float(np.min(z_values))
    schema_metadata["height_max"] = float(np.max(z_values))
    schema_metadata["height_span"] = float(np.max(z_values) - np.min(z_values))

    station_point = _extract_station_point(points)
    if station_point and all(not p.is_station for p in prepared_points):
        prepared_points.append(station_point)

    schema = SchemaData(
        points=prepared_points,
        belts=belts,
        sections=sections,
        axis=axis_data,
        metadata=schema_metadata,
    )

    logger.info(
        "Подготовлены данные схемы: %d точек, %d поясов, %d секций.",
        len(prepared_points),
        len(belts),
        len(sections),
    )

    return schema


# -----------------------------------------------------------------------------
# Экспорт в DXF
# -----------------------------------------------------------------------------


def _ensure_layers(doc, options: DxfExportOptions) -> None:
    layers = doc.layers
    layer_defs = {
        options.layer_config.points: {"color": 2},  # Жёлтый
        options.layer_config.station_points: {"color": 1},  # Красный
        options.layer_config.point_labels: {"color": 3},  # Зелёный
        options.layer_config.belts: {"color": 4},  # Циан
        options.layer_config.belt_labels: {"color": 5},
        options.layer_config.sections: {"color": 6},  # Магента
        options.layer_config.section_labels: {"color": 140},
        options.layer_config.axis: {"color": 7, "linetype": "CENTER"},
        options.layer_config.metadata: {"color": 8},
    }

    for layer_name, attrs in layer_defs.items():
        if layer_name in layers:
            continue
        layers.new(layer_name, dxfattribs=attrs)


def _set_text_position(text, position: Tuple[float, float, float], align: Optional[str] = None) -> None:
    """Универсально устанавливает позицию текста, учитывая разные версии ezdxf."""
    x, y = position[0], position[1]
    z = position[2] if len(position) > 2 else 0.0

    if hasattr(text, "set_pos"):
        if align:
            text.set_pos((x, y, z), align=align)
        else:
            text.set_pos((x, y, z))
        return

    text.dxf.insert = (x, y, z)
    if not align:
        return

    align_upper = align.upper()
    halign = None
    valign = None

    if "RIGHT" in align_upper:
        halign = 2
    elif "CENTER" in align_upper:
        halign = 1

    if "TOP" in align_upper:
        valign = 3
    elif "BOTTOM" in align_upper:
        valign = 1
    elif "MIDDLE" in align_upper:
        valign = 2

    if halign is not None:
        text.dxf.halign = halign
        text.dxf.align_point = (x, y, z)
    if valign is not None:
        text.dxf.valign = valign


def export_schema_to_dxf(schema: SchemaData, file_path: str, options: Optional[DxfExportOptions] = None) -> None:
    """Экспортирует SchemaData в DXF файл."""
    if not file_path:
        raise ValueError("Не указан путь для сохранения DXF файла.")

    options = options or DxfExportOptions()

    try:
        import ezdxf
        from ezdxf import units as ez_units
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Для экспорта в DXF требуется установленный пакет ezdxf.") from exc

    doc = ezdxf.new("R2018", setup=True)
    doc.units = ez_units.M
    _ensure_layers(doc, options)
    msp = doc.modelspace()

    min_x, max_x, min_y, max_y, min_z, max_z = schema.bounds()
    span_x = max(max_x - min_x, 1.0)
    span_y = max(max_y - min_y, 1.0)
    margin = max(span_x, span_y) * 0.05

    if options.include_points:
        for point in schema.points:
            layer_name = options.layer_config.station_points if point.is_station else options.layer_config.points
            msp.add_point(point.coords, dxfattribs={"layer": layer_name})

            if options.include_point_labels:
                label_parts = [point.name]
                if point.belt is not None:
                    label_parts.append(f"B{point.belt}")
                if point.index is not None:
                    label_parts.append(f"#{point.index}")
                text_value = " | ".join(label_parts)
                text = msp.add_text(
                    text_value,
                    dxfattribs={
                        "layer": options.layer_config.point_labels,
                        "height": options.text_height,
                    },
                )
                _set_text_position(text, point.coords, align="LEFT")

    if options.include_belts:
        for belt in schema.belts:
            if not belt.is_valid:
                continue
            points = belt.points
            if belt.closed and (len(points) < 3 or points[0] != points[-1]):
                points = points + [points[0]]
            msp.add_polyline3d(points, dxfattribs={"layer": options.layer_config.belts})

            if options.include_belt_labels:
                cx, cy, cz = belt.centroid()
                text = msp.add_text(
                    f"Пояс {belt.belt_number}",
                    dxfattribs={
                        "layer": options.layer_config.belt_labels,
                        "height": options.belt_label_height,
                    },
                )
                _set_text_position(text, (cx, cy, cz), align="MIDDLE_CENTER")

    if options.include_sections:
        for section in schema.sections:
            if not section.is_valid:
                continue
            msp.add_polyline3d(section.points, dxfattribs={"layer": options.layer_config.sections})
            if options.include_section_labels:
                cx, cy, cz = section.centroid()
                label = f"Секция Z={section.height:.2f} м"
                if section.belt_numbers:
                    belts_str = ", ".join(str(b) for b in section.belt_numbers)
                    label += f" (пояса: {belts_str})"
                text = msp.add_text(
                    label,
                    dxfattribs={
                        "layer": options.layer_config.section_labels,
                        "height": options.section_label_height,
                    },
                )
                _set_text_position(text, (cx, cy, cz), align="MIDDLE_CENTER")

    if options.include_axis and schema.axis:
        axis = schema.axis
        msp.add_line(axis.start, axis.end, dxfattribs={"layer": options.layer_config.axis})
        if axis.description:
            mx, my, mz = axis.midpoint()
            text = msp.add_text(
                axis.description,
                dxfattribs={
                    "layer": options.layer_config.axis,
                    "height": options.section_label_height,
                },
            )
            _set_text_position(text, (mx, my, mz), align="MIDDLE_CENTER")

    if options.include_metadata and schema.metadata:
        metadata_lines = []
        for key, value in schema.metadata.items():
            readable_key = str(key).replace("_", " ").capitalize()
            metadata_lines.append(f"{readable_key}: {value}")

        metadata_text = "\n".join(metadata_lines)
        anchor_x = max_x + margin
        anchor_y = max_y + margin
        anchor_z = min_z

        mtext = msp.add_mtext(
            metadata_text,
            dxfattribs={
                "layer": options.layer_config.metadata,
                "char_height": options.metadata_text_height,
                "width": options.metadata_column_width,
            },
        )
        mtext.set_location((anchor_x, anchor_y, anchor_z))

    doc.saveas(file_path)
    logger.info("Схема экспортирована в DXF: %s", file_path)


# -----------------------------------------------------------------------------
# Экспорт в PDF
# -----------------------------------------------------------------------------


def export_schema_to_pdf(schema: SchemaData, file_path: str) -> None:
    """Экспортирует SchemaData в PDF файл через reportlab."""
    if not file_path:
        raise ValueError("Не указан путь для сохранения PDF файла.")

    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            SimpleDocTemplate,
            Paragraph,
            Spacer,
            Table,
            TableStyle,
            PageBreak,
        )
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Для экспорта в PDF требуется установленный пакет reportlab.") from exc

    doc = SimpleDocTemplate(
        file_path,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        title="GeoVertical Schema Export",
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="SectionHeader", parent=styles["Heading2"], spaceBefore=12, spaceAfter=6))

    elements = []
    elements.append(Paragraph("Схема башни GeoVertical", styles["Title"]))
    elements.append(Spacer(1, 12))

    # Основные метаданные
    if schema.metadata:
        metadata_rows = []
        for key, value in sorted(schema.metadata.items()):
            readable_key = str(key).replace("_", " ").capitalize()
            metadata_rows.append(
                [
                    Paragraph(f"<b>{readable_key}</b>", styles["BodyText"]),
                    Paragraph(str(value), styles["BodyText"]),
                ]
            )
        metadata_table = Table(metadata_rows, colWidths=[60 * mm, None])
        metadata_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f0f0f0")),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.grey),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
                ]
            )
        )
        elements.append(Paragraph("Метаданные", styles["SectionHeader"]))
        elements.append(metadata_table)
        elements.append(Spacer(1, 12))

    # Таблица точек
    if schema.points:
        elements.append(Paragraph("Точки схемы", styles["SectionHeader"]))
        point_rows = [
            ["Название", "X (м)", "Y (м)", "Z (м)", "Пояс", "Тип"]
        ]
        for point in sorted(schema.points, key=lambda p: (p.is_station, p.name)):
            point_rows.append(
                [
                    point.name,
                    f"{point.x:.3f}",
                    f"{point.y:.3f}",
                    f"{point.z:.3f}",
                    str(point.belt) if point.belt is not None else "—",
                    "Станция" if point.is_station else "Рабочая точка",
                ]
            )

        point_table = Table(point_rows, repeatRows=1, colWidths=[40 * mm, 25 * mm, 25 * mm, 25 * mm, 20 * mm, 35 * mm])
        point_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#d0e4ff")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
                    ("ALIGN", (1, 1), (-2, -1), "RIGHT"),
                    ("ALIGN", (0, 0), (0, -1), "LEFT"),
                    ("ALIGN", (-1, 1), (-1, -1), "LEFT"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.grey),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
                ]
            )
        )
        elements.append(point_table)
        elements.append(Spacer(1, 12))

    # Пояса
    if schema.belts:
        elements.append(Paragraph("Пояса", styles["SectionHeader"]))
        belt_rows = [["Пояс", "Количество точек", "Средняя высота, м"]]
        for belt in schema.belts:
            _, _, z_vals = zip(*belt.points)
            belt_rows.append(
                [
                    str(belt.belt_number),
                    str(len(belt.points)),
                    f"{float(np.mean(z_vals)):.3f}",
                ]
            )
        belt_table = Table(belt_rows, repeatRows=1, colWidths=[30 * mm, 35 * mm, 45 * mm])
        belt_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#ffe0b2")),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.grey),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
                ]
            )
        )
        elements.append(belt_table)
        elements.append(Spacer(1, 12))

    # Секции
    if schema.sections:
        elements.append(Paragraph("Секции", styles["SectionHeader"]))
        section_rows = [["Высота, м", "Количество точек", "Пояса"]]
        for section in schema.sections:
            section_rows.append(
                [
                    f"{section.height:.3f}",
                    str(len(section.points)),
                    ", ".join(str(b) for b in section.belt_numbers) if section.belt_numbers else "—",
                ]
            )
        section_table = Table(section_rows, repeatRows=1, colWidths=[40 * mm, 40 * mm, 70 * mm])
        section_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#c8e6c9")),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.grey),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
                ]
            )
        )
        elements.append(section_table)
        elements.append(Spacer(1, 12))

    # Информация об оси
    if schema.axis:
        elements.append(Paragraph("Центральная ось", styles["SectionHeader"]))
        info = [
            Paragraph(f"<b>Начало:</b> ({schema.axis.start[0]:.3f}, {schema.axis.start[1]:.3f}, {schema.axis.start[2]:.3f}) м", styles["BodyText"]),
            Paragraph(f"<b>Конец:</b> ({schema.axis.end[0]:.3f}, {schema.axis.end[1]:.3f}, {schema.axis.end[2]:.3f}) м", styles["BodyText"]),
            Paragraph(f"<b>Длина:</b> {schema.axis.length():.3f} м", styles["BodyText"]),
        ]
        if schema.axis.description:
            info.append(Paragraph(f"<b>Описание:</b> {schema.axis.description}", styles["BodyText"]))
        for paragraph in info:
            elements.append(paragraph)
        elements.append(Spacer(1, 12))

    # Завершение
    elements.append(PageBreak())
    elements.append(Paragraph("Экспорт создан автоматически системой GeoVertical.", styles["Normal"]))

    doc.build(elements)
    logger.info("Схема экспортирована в PDF: %s", file_path)


