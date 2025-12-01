"""
Виджет предпросмотра башни для мастера создания.
"""

from __future__ import annotations

from typing import List, Optional

from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget
from PyQt6.QtCore import Qt

import pyqtgraph.opengl as gl
import numpy as np

from core.tower_generator import TowerBlueprint, generate_tower_data
from core.structure.builder import TowerModelBuilder
from core.structure.model import MemberType


class TowerPreviewWidget(QWidget):
    """
    Компактный 3D предпросмотр башни.
    Показывает линии секций, соединительные вертикали и точку стояния.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._gl_view = gl.GLViewWidget()
        self._gl_view.setCameraPosition(distance=80)
        self._gl_view.setBackgroundColor((0.96, 0.96, 0.96, 1.0))

        self._axes_items: List[gl.GLLinePlotItem] = []
        self._section_items: List[gl.GLLinePlotItem] = []
        self._member_items: List[gl.GLLinePlotItem] = []
        self._standing_item: Optional[gl.GLScatterPlotItem] = None

        self._summary_label = QLabel("Предпросмотр недоступен")
        self._summary_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._summary_label.setStyleSheet("padding: 4px; color: #444;")

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self._gl_view, 1)
        layout.addWidget(self._summary_label)
        self.setLayout(layout)

        self._setup_axes()

    def _setup_axes(self):
        axis_length = 10.0
        colors = {
            "x": (1.0, 0.0, 0.0, 1.0),
            "y": (0.0, 0.6, 0.0, 1.0),
            "z": (0.0, 0.0, 1.0, 1.0),
        }
        axes = (
            ([0, 0, 0], [axis_length, 0, 0], colors["x"]),
            ([0, 0, 0], [0, axis_length, 0], colors["y"]),
            ([0, 0, 0], [0, 0, axis_length], colors["z"]),
        )
        for start, end, color in axes:
            pos = np.array([start, end], dtype=float)
            item = gl.GLLinePlotItem(pos=pos, color=color, width=2)
            self._gl_view.addItem(item)
            self._axes_items.append(item)

    def reset(self):
        for item in self._section_items:
            self._gl_view.removeItem(item)
        self._section_items.clear()
        
        for item in self._member_items:
            self._gl_view.removeItem(item)
        self._member_items.clear()
        
        if self._standing_item is not None:
            self._gl_view.removeItem(self._standing_item)
            self._standing_item = None
        self._summary_label.setText("Предпросмотр недоступен")

    def update_preview(self, blueprint: TowerBlueprint):
        """
        Перестраивает предпросмотр по заданному blueprint.
        """
        try:
            # Generate structural model for lattice visualization
            builder = TowerModelBuilder(blueprint)
            model = builder.build()
            
            # Keep basic metadata for text
            # Still useful to get 'belts' count etc, or calculate from model
            # Using existing generator for quick metadata
            _, _, metadata = generate_tower_data(blueprint, seed=777)
            
        except Exception as error:
            self.reset()
            self._summary_label.setText(f"Ошибка генерации: {error}")
            return

        self.reset()

        # Render Members
        
        # Prepare batches for performance (lines of same color)
        # Legs
        leg_segments = []
        brace_segments = []
        strut_segments = []
        
        for member in model.members:
            n1 = model.nodes.get(member.start_node_id)
            n2 = model.nodes.get(member.end_node_id)
            if not n1 or not n2: continue
            
            points = [n1.coords, n2.coords]
            
            if member.member_type == MemberType.LEG:
                leg_segments.append(points)
            elif member.member_type == MemberType.BRACE:
                brace_segments.append(points)
            elif member.member_type == MemberType.STRUT:
                strut_segments.append(points)
            else:
                strut_segments.append(points)

        # Draw Legs (Black/Dark Grey, Thick)
        if leg_segments:
            pos = np.array(leg_segments, dtype=float).reshape(-1, 3)
            # Connect segments? No, GLLinePlotItem mode='lines' takes pairs
            item = gl.GLLinePlotItem(
                pos=pos,
                color=(0.2, 0.2, 0.2, 1.0),
                width=2.0,
                mode="lines"
            )
            self._gl_view.addItem(item)
            self._member_items.append(item)
            
        # Draw Braces (Blue, Thin)
        if brace_segments:
            pos = np.array(brace_segments, dtype=float).reshape(-1, 3)
            item = gl.GLLinePlotItem(
                pos=pos,
                color=(0.0, 0.4, 0.8, 0.8),
                width=1.0,
                mode="lines"
            )
            self._gl_view.addItem(item)
            self._member_items.append(item)
            
        # Draw Struts (Green, Thin)
        if strut_segments:
            pos = np.array(strut_segments, dtype=float).reshape(-1, 3)
            item = gl.GLLinePlotItem(
                pos=pos,
                color=(0.0, 0.6, 0.2, 0.8),
                width=1.0,
                mode="lines"
            )
            self._gl_view.addItem(item)
            self._member_items.append(item)

        self._summary_label.setText(
            f"Высота: {metadata['total_height']:.1f} м | Узлов: {len(model.nodes)} | Элементов: {len(model.members)}"
        )


