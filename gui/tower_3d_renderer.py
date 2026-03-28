"""
Утилита для отрисовки башни в 3D окне glview
"""

from __future__ import annotations

from typing import Optional, Dict, List, Tuple
import numpy as np
from PyQt6.QtCore import Qt
import pyqtgraph.opengl as gl

from core.tower_generator import TowerBlueprintV2
from core.structure.builder import TowerModelBuilder
from core.structure.model import MemberType, TowerModel


class Tower3DRenderer:
    """
    Класс для управления визуализацией башни в glview.
    Отрисовывает элементы башни (пояса, раскосы, распорки, диафрагмы) в 3D пространстве.
    """
    
    # Цвета для типов элементов
    ELEMENT_COLORS = {
        MemberType.LEG: (0.2, 0.2, 0.2, 1.0),      # Темно-серый для поясов
        MemberType.BRACE: (0.0, 0.4, 0.8, 0.8),     # Синий для раскосов
        MemberType.STRUT: (0.0, 0.6, 0.2, 0.8),    # Зеленый для распорок
        MemberType.DIAPHRAGM: (0.8, 0.4, 0.0, 0.8), # Оранжевый для диафрагм
        MemberType.CROSSBAR: (0.6, 0.6, 0.0, 0.8), # Желтый для перекладин
    }
    
    # Базовые толщины линий (без учета профилей)
    BASE_LINE_WIDTHS = {
        MemberType.LEG: 3.0,
        MemberType.BRACE: 2.0,
        MemberType.STRUT: 1.5,
        MemberType.DIAPHRAGM: 2.5,
        MemberType.CROSSBAR: 2.0,
    }
    
    def __init__(self, glview: gl.GLViewWidget):
        """
        Инициализация рендерера.

        Args:
            glview: Виджет OpenGL для отрисовки
        """
        self.glview = glview
        self._blueprint: Optional[TowerBlueprintV2] = None
        self._model: Optional[TowerModel] = None
        self._visible = True

        # Смещение в мировых координатах: прибавляется ко всем узлам при рендеринге,
        # чтобы предпросмотр башни совпадал с облаком измеренных точек.
        self._world_offset: np.ndarray = np.zeros(3, dtype=float)

        # Элементы визуализации
        self._member_items: Dict[int, gl.GLLinePlotItem] = {}
        self._node_items: Dict[int, gl.GLScatterPlotItem] = {}

        # Настройки отображения
        self._show_profiles = True  # Учитывать профили при отрисовке
        self._show_nodes = False    # Показывать узлы
    
    def set_world_offset(self, offset: np.ndarray) -> None:
        """Установить XYZ-смещение для позиционирования предпросмотра в мировых координатах.

        Вызывать до render_blueprint(), либо повторный вызов render_blueprint() применит
        актуальное смещение.

        Args:
            offset: массив [x, y, z] — смещение, прибавляемое ко всем узлам модели.
        """
        self._world_offset = np.asarray(offset, dtype=float)
        if self._model is not None:
            self._update_visualization()

    def render_blueprint(self, blueprint: Optional[TowerBlueprintV2]) -> None:
        """
        Отрисовать чертеж башни.

        Args:
            blueprint: Чертеж башни для отрисовки
        """
        self._blueprint = blueprint
        if blueprint:
            builder = TowerModelBuilder(blueprint)
            self._model = builder.build()
            self._update_visualization()
        else:
            self._model = None
            self.clear()
    
    def update_blueprint(self, blueprint: Optional[TowerBlueprintV2]) -> None:
        """
        Обновить визуализацию при изменении чертежа.
        
        Args:
            blueprint: Обновленный чертеж башни
        """
        self.render_blueprint(blueprint)
    
    def clear(self) -> None:
        """Очистить визуализацию."""
        # Удалить все элементы визуализации
        for item in list(self._member_items.values()):
            if item in self.glview.items:
                self.glview.removeItem(item)
        self._member_items.clear()
        
        for item in list(self._node_items.values()):
            if item in self.glview.items:
                self.glview.removeItem(item)
        self._node_items.clear()
    
    def set_visible(self, visible: bool) -> None:
        """
        Установить видимость визуализации.
        
        Args:
            visible: True для показа, False для скрытия
        """
        if self._visible == visible:
            return
        
        self._visible = visible
        
        # Показать/скрыть все элементы
        for item in self._member_items.values():
            item.setVisible(visible)
        
        for item in self._node_items.values():
            item.setVisible(visible)
    
    def is_visible(self) -> bool:
        """Проверить видимость визуализации."""
        return self._visible
    
    def set_show_profiles(self, show: bool) -> None:
        """
        Установить отображение профилей (толщина линий).
        
        Args:
            show: True для учета профилей, False для базовой толщины
        """
        if self._show_profiles == show:
            return
        
        self._show_profiles = show
        if self._model:
            self._update_visualization()
    
    def set_show_nodes(self, show: bool) -> None:
        """
        Установить отображение узлов.
        
        Args:
            show: True для показа узлов, False для скрытия
        """
        if self._show_nodes == show:
            return
        
        self._show_nodes = show
        if self._model:
            self._update_visualization()
    
    def _update_visualization(self) -> None:
        """Обновить визуализацию модели."""
        if not self._model:
            return
        
        self.clear()
        
        if not self._visible:
            return
        
        # Группировать элементы по типам для эффективной отрисовки
        elements_by_type: Dict[MemberType, List[Tuple[int, int, int]]] = {
            MemberType.LEG: [],
            MemberType.BRACE: [],
            MemberType.STRUT: [],
            MemberType.DIAPHRAGM: [],
            MemberType.CROSSBAR: [],
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
                c1 = np.asarray(n1.coords, dtype=float) + self._world_offset
                c2 = np.asarray(n2.coords, dtype=float) + self._world_offset
                segments.append([c1, c2])
                member_ids.append(member_id)
            
            # Вычислить толщину линий
            line_width = self._calculate_line_width(member_type, elements)
            
            # Цвет
            color = self.ELEMENT_COLORS.get(member_type, (0.5, 0.5, 0.5, 1.0))
            
            # Создать элемент визуализации
            pos = np.array(segments, dtype=float).reshape(-1, 3)
            item = gl.GLLinePlotItem(
                pos=pos,
                color=color,
                width=line_width,
                mode="lines"
            )
            item.setVisible(self._visible)
            self.glview.addItem(item)
            
            # Сохранить связь между визуальным элементом и ID элементов
            for member_id in member_ids:
                self._member_items[member_id] = item
        
        # Отрисовка узлов (если включено)
        if self._show_nodes:
            node_positions = []
            node_ids = []

            for node_id, node in self._model.nodes.items():
                node_positions.append(np.asarray(node.coords, dtype=float) + self._world_offset)
                node_ids.append(node_id)

            if node_positions:
                pos = np.array(node_positions, dtype=float)
                node_item = gl.GLScatterPlotItem(
                    pos=pos,
                    color=(1.0, 0.0, 0.0, 0.8),  # Красный для узлов
                    size=5.0
                )
                node_item.setVisible(self._visible)
                self.glview.addItem(node_item)
                
                for node_id in node_ids:
                    self._node_items[node_id] = node_item
    
    def _calculate_line_width(self, member_type: MemberType, elements: List[Tuple[int, int, int]]) -> float:
        """
        Вычислить толщину линии на основе профилей элементов.
        
        Args:
            member_type: Тип элемента
            elements: Список элементов (member_id, start_id, end_id)
        
        Returns:
            Толщина линии в пикселях
        """
        if not self._show_profiles:
            return self.BASE_LINE_WIDTHS.get(member_type, 1.0)
        
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
            line_width = self.BASE_LINE_WIDTHS.get(member_type, 1.0)
        
        return line_width
    
    def get_model(self) -> Optional[TowerModel]:
        """Получить текущую модель башни."""
        return self._model
    
    def get_blueprint(self) -> Optional[TowerBlueprintV2]:
        """Получить текущий чертеж башни."""
        return self._blueprint
