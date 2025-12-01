"""
Улучшенная 3D визуализация башни с:
- Визуализацией профилей (толщина линий)
- Цветовой кодировкой по типам элементов
- Интерактивным выбором элементов
- Визуализацией ветровых нагрузок
"""

from __future__ import annotations

from typing import Optional, Dict, List, Tuple, Any
import numpy as np
from PyQt6.QtCore import Qt, pyqtSignal, QPoint
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PyQt6.QtGui import QColor

import pyqtgraph.opengl as gl

from core.tower_generator import TowerBlueprintV2
from core.structure.builder import TowerModelBuilder
from core.structure.model import MemberType, TowerModel


class EnhancedTowerPreview3D(QWidget):
    """
    Улучшенная 3D визуализация башни с интерактивным выбором элементов
    и визуализацией профилей.
    """
    
    # Сигналы
    elementSelected = pyqtSignal(int, MemberType)  # member_id, member_type
    nodeSelected = pyqtSignal(int)  # node_id
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._blueprint: Optional[TowerBlueprintV2] = None
        self._model: Optional[TowerModel] = None
        self._selected_member_id: Optional[int] = None
        self._selected_node_id: Optional[int] = None
        
        # Цвета для типов элементов
        self._element_colors = {
            MemberType.LEG: (0.2, 0.2, 0.2, 1.0),      # Темно-серый для поясов
            MemberType.BRACE: (0.0, 0.4, 0.8, 0.8),     # Синий для раскосов
            MemberType.STRUT: (0.0, 0.6, 0.2, 0.8),    # Зеленый для распорок
            MemberType.DIAPHRAGM: (0.8, 0.4, 0.0, 0.8), # Оранжевый для диафрагм
        }
        
        # Цвет для выбранного элемента
        self._selected_color = (1.0, 0.0, 0.0, 1.0)  # Красный
        
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """Настройка интерфейса."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        
        # Панель инструментов
        toolbar = QHBoxLayout()
        toolbar.setSpacing(4)
        
        self.reset_view_btn = QPushButton("Сброс вида")
        self.reset_view_btn.clicked.connect(self._reset_view)
        toolbar.addWidget(self.reset_view_btn)
        
        self.show_profiles_btn = QPushButton("Показать профили")
        self.show_profiles_btn.setCheckable(True)
        self.show_profiles_btn.setChecked(True)
        self.show_profiles_btn.toggled.connect(self._toggle_profiles)
        toolbar.addWidget(self.show_profiles_btn)
        
        toolbar.addStretch()
        
        self.info_label = QLabel("Готов к работе")
        self.info_label.setStyleSheet("color: #666; font-size: 9pt;")
        toolbar.addWidget(self.info_label)
        
        layout.addLayout(toolbar)
        
        # 3D виджет
        self.gl_view = gl.GLViewWidget()
        self.gl_view.setCameraPosition(distance=80)
        self.gl_view.setBackgroundColor((0.96, 0.96, 0.96, 1.0))
        
        # Обработка кликов будет реализована позже через переопределение событий GLViewWidget
        
        layout.addWidget(self.gl_view, stretch=1)
        
        # Элементы визуализации
        self._axes_items: List[gl.GLLinePlotItem] = []
        self._member_items: Dict[int, gl.GLLinePlotItem] = {}
        self._node_items: Dict[int, gl.GLScatterPlotItem] = {}
        self._load_items: List[gl.GLLinePlotItem] = []
        
        self._setup_axes()
    
    def _setup_axes(self) -> None:
        """Настройка осей координат."""
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
            item = gl.GLLinePlotItem(pos=pos, color=color, width=3)
            self.gl_view.addItem(item)
            self._axes_items.append(item)
    
    def set_blueprint(self, blueprint: Optional[TowerBlueprintV2]) -> None:
        """Установить чертеж башни для визуализации."""
        self._blueprint = blueprint
        if blueprint:
            builder = TowerModelBuilder(blueprint)
            self._model = builder.build()
            self._update_visualization()
        else:
            self._model = None
            self._clear_visualization()
    
    def _update_visualization(self) -> None:
        """Обновить визуализацию модели."""
        if not self._model:
            return
        
        self._clear_visualization()
        
        # Группировать элементы по типам для эффективной отрисовки
        elements_by_type: Dict[MemberType, List[Tuple[int, int, int]]] = {
            MemberType.LEG: [],
            MemberType.BRACE: [],
            MemberType.STRUT: [],
        }
        
        for member in self._model.members:
            n1 = self._model.nodes.get(member.start_node_id)
            n2 = self._model.nodes.get(member.end_node_id)
            if not n1 or not n2:
                continue
            
            if member.member_type in elements_by_type:
                elements_by_type[member.member_type].append((
                    member.id,
                    member.start_node_id,
                    member.end_node_id
                ))
        
        # Отрисовка элементов по типам
        for member_type, elements in elements_by_type.items():
            if not elements:
                continue
            
            # Подготовить данные для отрисовки
            segments = []
            member_ids = []
            
            for member_id, start_id, end_id in elements:
                n1 = self._model.nodes[start_id]
                n2 = self._model.nodes[end_id]
                segments.append([n1.coords, n2.coords])
                member_ids.append(member_id)
            
            # Вычислить толщину линий на основе профилей
            line_width = self._calculate_line_width(member_type, elements)
            
            # Цвет
            color = self._element_colors.get(member_type, (0.5, 0.5, 0.5, 1.0))
            
            # Создать элемент визуализации
            pos = np.array(segments, dtype=float).reshape(-1, 3)
            item = gl.GLLinePlotItem(
                pos=pos,
                color=color,
                width=line_width,
                mode="lines"
            )
            self.gl_view.addItem(item)
            
            # Сохранить связь между визуальным элементом и ID элементов
            for member_id in member_ids:
                self._member_items[member_id] = item
        
        # Обновить информацию
        self.info_label.setText(
            f"Узлов: {len(self._model.nodes)}, Элементов: {len(self._model.members)}"
        )
    
    def _calculate_line_width(self, member_type: MemberType, elements: List[Tuple[int, int, int]]) -> float:
        """Вычислить толщину линии на основе профилей элементов."""
        if not self.show_profiles_btn.isChecked():
            # Базовая толщина без учета профилей
            base_widths = {
                MemberType.LEG: 3.0,
                MemberType.BRACE: 2.0,
                MemberType.STRUT: 1.5,
            }
            return base_widths.get(member_type, 1.0)
        
        # Вычислить средний диаметр профилей
        total_d = 0.0
        count = 0
        
        for member_id, _, _ in elements:
            member = next((m for m in self._model.members if m.id == member_id), None)
            if member and member.profile_data:
                d = member.profile_data.get('d', 100)  # мм
                total_d += d
                count += 1
        
        if count > 0:
            avg_d = total_d / count
            # Преобразовать мм в пиксели (масштабирование)
            line_width = max(1.0, min(10.0, avg_d / 20.0))
        else:
            # Базовая толщина
            base_widths = {
                MemberType.LEG: 3.0,
                MemberType.BRACE: 2.0,
                MemberType.STRUT: 1.5,
            }
            line_width = base_widths.get(member_type, 1.0)
        
        return line_width
    
    def _clear_visualization(self) -> None:
        """Очистить визуализацию."""
        # Удалить элементы (кроме осей)
        for item in list(self._member_items.values()):
            if item in self.gl_view.items:
                self.gl_view.removeItem(item)
        self._member_items.clear()
        
        for item in list(self._node_items.values()):
            if item in self.gl_view.items:
                self.gl_view.removeItem(item)
        self._node_items.clear()
        
        for item in self._load_items:
            if item in self.gl_view.items:
                self.gl_view.removeItem(item)
        self._load_items.clear()
    
    def _reset_view(self) -> None:
        """Сбросить вид камеры."""
        self.gl_view.setCameraPosition(distance=80, elevation=30, azimuth=45)
    
    def _toggle_profiles(self, checked: bool) -> None:
        """Переключить отображение профилей."""
        if self._model:
            self._update_visualization()
    
    
    def select_member(self, member_id: int) -> None:
        """Выделить элемент по ID."""
        if self._selected_member_id == member_id:
            return
        
        # Снять выделение с предыдущего элемента
        if self._selected_member_id and self._selected_member_id in self._member_items:
            # TODO: Восстановить исходный цвет
            pass
        
        self._selected_member_id = member_id
        
        # Выделить новый элемент
        if member_id in self._member_items:
            # TODO: Изменить цвет на выделенный
            self.elementSelected.emit(member_id, MemberType.LEG)  # TODO: определить тип
    
    def show_wind_loads(self, loads: Dict[int, np.ndarray]) -> None:
        """Показать ветровые нагрузки в виде векторов."""
        # Очистить предыдущие нагрузки
        for item in self._load_items:
            if item in self.gl_view.items:
                self.gl_view.removeItem(item)
        self._load_items.clear()
        
        if not self._model:
            return
        
        # Отобразить векторы сил
        for node_id, force_vector in loads.items():
            node = self._model.nodes.get(node_id)
            if not node:
                continue
            
            # Нормализовать вектор для визуализации
            magnitude = np.linalg.norm(force_vector)
            if magnitude < 1e-6:
                continue
            
            scale = min(5.0, magnitude / 1000.0)  # Масштаб для визуализации
            direction = force_vector / magnitude
            
            end_point = node.coords + direction * scale
            
            pos = np.array([node.coords, end_point], dtype=float)
            item = gl.GLLinePlotItem(
                pos=pos,
                color=(1.0, 0.0, 0.0, 0.8),  # Красный для нагрузок
                width=2.0,
                mode="lines"
            )
            self.gl_view.addItem(item)
            self._load_items.append(item)
    
    def reset(self) -> None:
        """Сбросить визуализацию."""
        self._clear_visualization()
        self._model = None
        self._blueprint = None
        self._selected_member_id = None
        self._selected_node_id = None
        self.info_label.setText("Готов к работе")
