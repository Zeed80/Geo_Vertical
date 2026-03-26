"""
3D редактор точек на основе PyQtGraph
Позволяет визуализировать, редактировать и управлять точками в 3D пространстве
"""

import json
import math
import numpy as np
import pandas as pd
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                             QLabel, QDialog, QFormLayout, QDialogButtonBox,
                             QLineEdit, QSpinBox, QComboBox, QMessageBox, QMenu,
                             QCheckBox, QSizePolicy, QToolButton, QGridLayout,
                             QDoubleSpinBox, QTabWidget, QSplitter)
from PyQt6.QtCore import Qt, pyqtSignal, QPointF, QSize
from PyQt6.QtGui import QColor, QAction
import pyqtgraph as pg
import pyqtgraph.opengl as gl
from typing import Optional, List, Dict, Tuple, Any
from contextlib import contextmanager
import logging
import re

from gui.ui_helpers import apply_compact_button_style
from core.section_operations import get_section_lines, find_section_levels
from core.tower_generator import TowerBlueprint, TowerBlueprintV2
from gui.tower_builder_panel import TowerBuilderPanel
from gui.index_manager import IndexManager
from gui.tower_3d_renderer import Tower3DRenderer
from gui.editor_components import (
    ContrastGLTextItem,
    ButtonGroupWidget,
    ToolPanelWidget,
    PointEditDialog,
    TiltPlaneDialog,
)
logger = logging.getLogger(__name__)


class PointEditor3DWidget(QWidget):
    """
    3D редактор точек с использованием PyQtGraph GLViewWidget
    
    Сигналы:
        point_selected(index): Точка выбрана
        point_modified(index, data): Точка изменена
        point_added(data): Точка добавлена
        point_deleted(index): Точка удалена
        belt_assigned(indices, belt_num): Пояс назначен точкам
        data_changed(): Данные изменены
    """
    
    point_selected = pyqtSignal(int)
    point_modified = pyqtSignal(int, dict)
    point_added = pyqtSignal(dict)
    point_deleted = pyqtSignal(int)
    belt_assigned = pyqtSignal(list, object)
    data_changed = pyqtSignal()
    toolbar_position_changed = pyqtSignal(str)
    tower_blueprint_requested = pyqtSignal(object)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.data = None  # DataFrame с данными (x, y, z, name, belt)
        self.point_index_counter = 0  # Максимальный присвоенный индекс точки
        self.index_manager = IndexManager()  # Менеджер индексов для безопасного доступа к точкам
        self.selected_indices = []
        self.belt_colors = {}  # Цвета для поясов
        self.show_belt_lines = True
        
        # 3D объекты
        self.point_scatter = None
        self.point_labels = []
        self.belt_lines = []
        self.axis_items = []
        self.section_lines = []  # Линии секций
        self.section_data = []   # Данные о секциях
        self.central_axis_line = None  # Линия центральной оси
        self.belt_polylines = {}  # Визуализация полилиний поясов по номеру
        self.show_central_axis = False  # Флаг отображения центральной оси
        self.belt_connection_lines = []  # Линии соединения поясов
        self._last_visualization_data = None  # Последние данные визуализации для использования в зеркальном методе
        self.toolbar_buttons: List[QWidget] = []
        self.toolbar_position_actions: Dict[str, QAction] = {}
        self.toolbar_position: str = 'left'
        self.xy_plane_center = np.array([0.0, 0.0, 0.0], dtype=float)
        self.xy_plane_size = 10.0
        self.xy_plane_item: Optional[gl.GLMeshItem] = None
        self.xy_plane_move_mode = False
        self.xy_plane_initialized = False
        
        # Переменные для выбора точек
        self.is_selecting = False
        self.drag_start_pos = None
        
        # Режим выбора линии пояса
        self.belt_selection_mode = False
        self.pending_point_idx = None
        
        # Режим массового переноса точек пояса на линию
        self.belt_mass_move_mode = False
        self.pending_belt_num = None
        
        # Режим выбора уровня секции
        self.section_selection_mode = False
        
        # Режим выравнивания секции
        self.section_alignment_mode = False
        
        # Режим удаления секции
        self.section_deletion_mode = False
        
        # Undo/redo
        self.undo_stack: List[Tuple[str, dict]] = []
        self.redo_stack: List[Tuple[str, dict]] = []
        
        self.processed_results: Optional[Dict[str, Any]] = None
        self._tower_blueprint: Optional[TowerBlueprint] = None
        self._blueprint_applied: bool = False  # Флаг применения blueprint к точкам
        
        self.active_station_index: Optional[int] = None
        self.station_indices: List[int] = []
        self._index_to_position: Dict[Any, int] = {}
        
        # Рендерер для визуализации башни из конструктора
        # Будет инициализирован после создания glview в init_ui()
        self._tower_renderer: Optional[Tower3DRenderer] = None
        
        # Компоненты для режима unified (будут созданы при необходимости)
        self._unified_structure_tree: Optional[QWidget] = None
        self._unified_properties_panel: Optional[QWidget] = None
        self._unified_toolbar_widget: Optional[QWidget] = None
        self._unified_mode_active: bool = False
        self._original_splitter_structure: Optional[tuple] = None  # Для восстановления
        
        self.init_ui()
        self.setup_colors()

    def _decode_part_memberships(self, value) -> List[int]:
        """Декодирует JSON/список принадлежности частей."""
        if value is None:
            return []
        if isinstance(value, str):
            try:
                decoded = json.loads(value)
            except Exception:
                return []
        elif isinstance(value, (list, tuple, set)):
            decoded = list(value)
        else:
            return []
        memberships = []
        for item in decoded:
            try:
                memberships.append(int(item))
            except (TypeError, ValueError):
                continue
        return memberships
    
    def init_ui(self):
        """Инициализация интерфейса"""
        root_layout = QVBoxLayout()
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(2)
        self.setLayout(root_layout)
        self.root_layout = root_layout
        
        # Панель инструментов (возможность менять позицию)
        self.toolbar = self.create_toolbar()
        self.toolbar.set_position(self.toolbar_position)
        
        # 3D вид
        self.glview = gl.GLViewWidget()
        self.glview.setCameraPosition(distance=100)
        self.glview.setBackgroundColor((0.95, 0.95, 0.95, 1.0))  # Светло-серый фон
        
        # Настройка управления камерой
        # По умолчанию PyQtGraph использует:
        # - ЛКМ для вращения
        # - СКМ или Ctrl+ЛКМ для перемещения
        # - Колесико для зума
        # Мы изменяем на:
        # - ПКМ для перемещения
        # - ЛКМ для выбора точек (наш custom обработчик)
        # - СКМ или Shift+ЛКМ для вращения
        
        # Подключаем обработчики мыши и клавиатуры
        self.glview.mousePressEvent = self.mouse_press_event
        self.glview.mouseMoveEvent = self.mouse_move_event
        self.glview.mouseReleaseEvent = self.mouse_release_event
        self.glview.mouseDoubleClickEvent = self.mouse_double_click_event
        self.glview.keyPressEvent = self.key_press_event
        
        # Переменные для отслеживания перетаскивания камеры
        self.camera_drag_start_pos = None
        self.camera_drag_button = None

        # Основная рабочая область
        self.main_area_layout = QHBoxLayout()
        self.main_area_layout.setContentsMargins(0, 0, 0, 0)
        self.main_area_layout.setSpacing(4)

        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.setChildrenCollapsible(False)
        self.main_splitter.setHandleWidth(6)
        self.main_splitter.addWidget(self.glview)

        self.side_tabs = QTabWidget()
        self.side_tabs.setTabPosition(QTabWidget.TabPosition.South)
        self.side_tabs.setMinimumWidth(360)
        self.tower_builder_panel = TowerBuilderPanel(self)
        self.tower_builder_panel.blueprintRequested.connect(self._on_tower_blueprint_requested)
        self.tower_builder_panel.statusMessage.connect(self._set_status_message)
        # Подключить сигнал визуализации для отображения башни в основном окне
        self.tower_builder_panel.towerVisualizationRequested.connect(self._on_tower_visualization_requested)
        self.side_tabs.addTab(self.tower_builder_panel, "Конструктор")
        self.main_splitter.addWidget(self.side_tabs)
        self.main_splitter.setStretchFactor(0, 4)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setCollapsible(1, True)

        self.main_area_layout.addWidget(self.main_splitter)
        root_layout.addLayout(self.main_area_layout, stretch=1)
        self.tower_builder_visible = False
        self._builder_last_size = 360
        self._update_builder_panel_visibility()
        
        # НЕ добавляем сетку - она непонятная
        # НЕ добавляем grid = gl.GLGridItem()
        
        # Добавляем только оси координат (красиво и понятно)
        self.add_coordinate_axes()
        
        # Компактная информационная панель
        info_layout = QHBoxLayout()
        info_layout.setContentsMargins(5, 0, 5, 0)
        info_layout.setSpacing(5)
        self.info_label = QLabel('Точек: 0 | Выбрано: 0')
        self.info_label.setStyleSheet('font-size: 9pt; padding: 2px;')
        self.info_label.setMaximumHeight(20)  # Ограничиваем высоту
        info_layout.addWidget(self.info_label)
        info_layout.addStretch()
        root_layout.addLayout(info_layout)
    
        # Применяем позицию панели
        self.apply_toolbar_position(initial=True)

        self.update_undo_redo_buttons()
        
        # Инициализировать рендерер после создания glview
        if self.glview:
            self._tower_renderer = Tower3DRenderer(self.glview)
    
    def _create_toolbar_button(self, text: str, *, callback=None, tooltip: Optional[str] = None,
                                checkable: bool = False, checked: bool = False,
                                width: int = 78, height: int = 54, enabled: bool = True,
                                rich_tooltip_title: Optional[str] = None,
                                rich_tooltip_desc: Optional[str] = None,
                                rich_tooltip_shortcut: Optional[str] = None) -> QPushButton:
        """Создает компактную многострочную кнопку для тулбара редактора."""
        button = QPushButton(text)
        button.setObjectName('editorToolbarButton')
        button.setCheckable(checkable)
        if checkable:
            button.setChecked(checked)
        button.setEnabled(enabled)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        # Увеличиваем размеры кнопок для лучшей читаемости текста
        button.setFixedWidth(max(width, 85))
        button.setFixedHeight(max(height, 56))
        # Всегда устанавливаем tooltip - если не указан, используем текст кнопки
        if tooltip:
            button.setToolTip(tooltip)
        else:
            # Создаем tooltip из текста кнопки, убирая эмодзи и переносы строк
            tooltip_text = text.replace('\n', ' ').strip()
            # Убираем эмодзи для более читаемого tooltip
            tooltip_text = re.sub(r'[^\w\s\-\(\)]', '', tooltip_text).strip()
            if tooltip_text:
                button.setToolTip(tooltip_text)
        
        # Устанавливаем rich tooltip если указан
        if rich_tooltip_title:
            from gui.rich_tooltip import set_rich_tooltip
            set_rich_tooltip(button, rich_tooltip_title, 
                           rich_tooltip_desc or "", 
                           rich_tooltip_shortcut or "")
        base_style = (
            "QPushButton#editorToolbarButton {\n"
            "    padding: 6px 8px;\n"
            "    font-size: 10px;\n"
            "    font-weight: 500;\n"
            "    text-align: center;\n"
            "}\n"
        )
        if checkable:
            base_style += (
                "QPushButton#editorToolbarButton:checked {\n"
                "    background-color: rgba(76, 175, 80, 46);\n"
                "}\n"
            )
        button.setStyleSheet(base_style)

        if callback:
            if checkable:
                button.toggled.connect(callback)
            else:
                button.clicked.connect(callback)
        
        self._register_toolbar_button(button, base_width=width, base_height=height)
        return button

    def _register_toolbar_button(self, button: QWidget, *, base_width: int, base_height: int):
        """Регистрирует кнопку тулбара для последующей адаптации размеров."""
        button.setProperty('base_width', base_width)
        button.setProperty('base_height', base_height)
        button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.toolbar_buttons.append(button)

    def _update_toolbar_button_sizes(self):
        """Адаптирует размеры кнопок тулбара под выбранную ориентацию."""
        if not hasattr(self, 'toolbar') or self.toolbar is None:
            return
        
        orientation = self.toolbar.orientation()
        for button in self.toolbar_buttons:
            if button is None:
                continue
            base_width = button.property('base_width') or 80
            base_height = button.property('base_height') or 52
            
            if orientation == Qt.Orientation.Vertical:
                width = int(base_width)
                height = int(base_height)
                button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            else:
                width = int(max(base_width + 8, 82))
                height = int(max(base_height - 16, 40))
                button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            
            button.setFixedWidth(width)
            button.setFixedHeight(height)

    def _update_toolbar_position_menu(self):
        """Обновляет состояние меню выбора позиции панели."""
        for pos, action in self.toolbar_position_actions.items():
            if action is not None:
                action.blockSignals(True)
                action.setChecked(pos == self.toolbar_position)
                action.blockSignals(False)

    def set_toolbar_position(self, position: str):
        """Изменяет расположение панели инструментов."""
        if position not in {'left', 'top', 'right'}:
            return
        if position == self.toolbar_position and hasattr(self, 'toolbar') and self.toolbar is not None:
            return
        
        self.toolbar_position = position
        self.apply_toolbar_position()
        self.toolbar_position_changed.emit(self.toolbar_position)

    def apply_toolbar_position(self, initial: bool = False):
        """Применяет текущее расположение панели инструментов."""
        if not hasattr(self, 'toolbar') or self.toolbar is None:
            return
        
        # Удаляем панель из предыдущего контейнера
        if hasattr(self, 'main_area_layout'):
            self.main_area_layout.removeWidget(self.toolbar)
        if hasattr(self, 'root_layout'):
            self.root_layout.removeWidget(self.toolbar)
        
        self.toolbar.setParent(None)
        self.toolbar.hide()
        
        self.toolbar.set_position(self.toolbar_position)
        
        if self.toolbar_position == 'left':
            self.main_area_layout.insertWidget(0, self.toolbar, 0)
        elif self.toolbar_position == 'right':
            self.main_area_layout.addWidget(self.toolbar, 0)
        elif self.toolbar_position == 'top':
            self.root_layout.insertWidget(0, self.toolbar)
        else:
            self.main_area_layout.insertWidget(0, self.toolbar, 0)
        
        self.toolbar.show()
        self.toolbar.reflow()
        self._update_toolbar_button_sizes()
        self._update_toolbar_position_menu()
        
        if not initial:
            self.update()

    def create_toolbar(self) -> ToolPanelWidget:
        """Создание панели инструментов"""
        toolbar = ToolPanelWidget(self)

        # Меню настройки расположения панели
        settings_button = QToolButton()
        settings_button.setText('⚙️\nПанель')
        settings_button.setToolTip('Изменить расположение панели инструментов')
        settings_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        settings_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        settings_button.setStyleSheet(
            "padding: 6px 8px; font-size: 11px; font-weight: 500; text-align: center;"
        )
        self._register_toolbar_button(settings_button, base_width=66, base_height=48)

        settings_menu = QMenu(settings_button)
        positions = [('left', 'Слева'), ('top', 'Сверху'), ('right', 'Справа')]
        self.toolbar_position_actions = {}
        for pos, label in positions:
            action = settings_menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(pos == self.toolbar_position)
            action.triggered.connect(lambda checked, p=pos: self.set_toolbar_position(p))
            self.toolbar_position_actions[pos] = action
        settings_button.setMenu(settings_menu)
        toolbar.add_button(settings_button)

        # ========== ГРУППА: Редактирование точек ==========
        toolbar.add_button(self._create_toolbar_button(
            '➕\nДобавить\nточку',
            callback=self.add_point_dialog,
            tooltip='Добавить новую точку в башню',
            rich_tooltip_title='Добавить точку',
            rich_tooltip_desc='Открывает диалог для добавления новой точки в башню. Можно указать координаты X, Y, Z и назначить пояс.'
        ))

        toolbar.add_button(self._create_toolbar_button(
            '✏️\nРедактировать',
            callback=self.edit_selected_point,
            tooltip='Редактировать выбранную точку',
            rich_tooltip_title='Редактировать точку',
            rich_tooltip_desc='Редактирует координаты выбранной точки. Выберите точку в 3D редакторе или таблице, затем нажмите эту кнопку.'
        ))

        toolbar.add_button(self._create_toolbar_button(
            '❌\nУдалить',
            callback=self.delete_selected_points,
            tooltip='Удалить выбранные точки (Del)',
            rich_tooltip_title='Удалить точки',
            rich_tooltip_desc='Удаляет выбранные точки из башни. Можно выбрать несколько точек для удаления.',
            rich_tooltip_shortcut='Del'
        ))

        # ========== ГРУППА: Работа с поясами ==========
        toolbar.add_button(self._create_toolbar_button(
            '🏷️\nТочки\nна пояс',
            callback=self.move_all_belt_points_to_line_dialog,
            tooltip='Выбрать линию пояса и перенести на неё все точки этого пояса',
            rich_tooltip_title='Перенести точки на пояс',
            rich_tooltip_desc='Выберите линию пояса, и все точки этого пояса будут автоматически перенесены на эту линию. Используется для выравнивания точек пояса.'
        ))

        toolbar.add_button(self._create_toolbar_button(
            '📍\nНа линию\nпояса',
            callback=self.project_to_belt_line_dialog,
            tooltip='Спроецировать выбранные точки на линию пояса',
            rich_tooltip_title='Спроецировать на линию пояса',
            rich_tooltip_desc='Проецирует выбранные точки на линию пояса. Точки перемещаются перпендикулярно к линии пояса.'
        ))

        # ========== ГРУППА: Работа с секциями ==========
        self.create_sections_btn = self._create_toolbar_button(
            '📏\nСоздать\nсекции',
            callback=self.create_sections_wrapper,
            tooltip='Автоматическая разбивка башни на секции с добавлением недостающих точек',
            enabled=False,
            rich_tooltip_title='Создать секции',
            rich_tooltip_desc='Автоматически разбивает башню на секции и добавляет недостающие точки для полного описания геометрии. Секции определяются по уровням поясов.'
        )
        toolbar.add_button(self.create_sections_btn)

        self.remove_sections_btn = self._create_toolbar_button(
            '🗑️\nУдалить\nсекции',
            callback=self.remove_sections_wrapper,
            tooltip='Удалить все добавленные точки секций, вернуть оригинальные данные',
            enabled=False,
            rich_tooltip_title='Удалить секции',
            rich_tooltip_desc='Удаляет все точки, добавленные при создании секций, возвращая башню к исходному состоянию. Оригинальные точки сохраняются.'
        )
        toolbar.add_button(self.remove_sections_btn)

        toolbar.add_button(self._create_toolbar_button(
            '📐\nНа уровень\nсекции',
            callback=self.project_to_section_level_dialog,
            tooltip='Спроецировать выбранные точки на уровень секции',
            rich_tooltip_title='Спроецировать на уровень секции',
            rich_tooltip_desc='Проецирует выбранные точки на горизонтальный уровень секции. Используется для выравнивания точек по высоте.'
        ))

        toolbar.add_button(self._create_toolbar_button(
            '🔧\nВыровнять\nсекцию',
            callback=self.align_section_dialog,
            tooltip='Автоматически переносит все точки секции на одну линию',
            rich_tooltip_title='Выровнять секцию',
            rich_tooltip_desc='Автоматически переносит все точки выбранной секции на одну прямую линию. Используется для исправления геометрии секции.'
        ))

        toolbar.add_button(self._create_toolbar_button(
            '⚖️\nВыровнять\nсекции',
            callback=self.align_all_sections_dialog,
            tooltip='Выровнять все секции по выбранному поясу с умным переносом точек',
            rich_tooltip_title='Выровнять все секции',
            rich_tooltip_desc='Выравнивает все секции башни по выбранному поясу с умным переносом точек. Обеспечивает единообразие геометрии.'
        ))

        toolbar.add_button(self._create_toolbar_button(
            '🗑️\nУдалить\nсекцию',
            callback=self.delete_section_dialog,
            tooltip='Удалить выбранную секцию и все её добавленные точки',
            rich_tooltip_title='Удалить секцию',
            rich_tooltip_desc='Удаляет выбранную секцию и все точки, добавленные при её создании. Оригинальные точки сохраняются.'
        ))

        toolbar.add_button(self._create_toolbar_button(
            '➕\nДобавить\nсекцию',
            callback=self.add_section_dialog,
            tooltip='Добавить новую секцию над или под существующей',
            rich_tooltip_title='Добавить секцию',
            rich_tooltip_desc='Добавляет новую секцию над или под существующей. Позволяет расширить модель башни.'
        ))

        toolbar.add_button(self._create_toolbar_button(
            '⬆️\nСместить\nбашню',
            callback=self.shift_tower_height_dialog,
            tooltip='Сместить всю башню по высоте, изменив высоту нижней секции',
            rich_tooltip_title='Сместить башню по высоте',
            rich_tooltip_desc='Смещает всю башню по вертикали, изменяя высоту нижней секции. Все точки смещаются на одинаковое значение.'
        ))

        self.build_central_axis_btn = self._create_toolbar_button(
            '📌\nЦентральная\nось',
            callback=self.build_central_axis,
            tooltip='Построить вертикальную линию через центры секций',
            enabled=False,
            rich_tooltip_title='Построить центральную ось',
            rich_tooltip_desc='Строит вертикальную линию, проходящую через центры всех секций башни. Используется для визуализации и анализа.'
        )
        toolbar.add_button(self.build_central_axis_btn)

        self.tilt_plane_btn = self._create_toolbar_button(
            '⚙️\nКрен\nсекции',
            callback=self.open_section_tilt_dialog,
            tooltip='Повернуть плоскость так, чтобы выбранная секция имела заданный крен',
            enabled=False,
            rich_tooltip_title='Крен секции',
            rich_tooltip_desc='Поворачивает плоскость так, чтобы выбранная секция имела заданный крен. Влияет на все секции выше выбранной.'
        )
        toolbar.add_button(self.tilt_plane_btn)

        self.tilt_single_section_btn = self._create_toolbar_button(
            '⚙️\nКрен\n(лок.)',
            callback=self.open_single_section_tilt_dialog,
            tooltip='Перераспределить только выбранную секцию под заданный крен',
            enabled=False,
            rich_tooltip_title='Крен секции (локальный)',
            rich_tooltip_desc='Перераспределяет только выбранную секцию под заданный крен, не влияя на другие секции.'
        )
        toolbar.add_button(self.tilt_single_section_btn)

        # ========== ГРУППА: Отмена/Повтор ==========
        self.undo_button = self._create_toolbar_button(
            '↩️\nОтменить',
            callback=self.undo_action,
            tooltip='Отменить последнее действие (Ctrl+Z)',
            enabled=False,
            rich_tooltip_title='Отменить действие',
            rich_tooltip_desc='Отменяет последнее выполненное действие. Поддерживается история изменений.',
            rich_tooltip_shortcut='Ctrl+Z'
        )
        toolbar.add_button(self.undo_button)

        self.redo_button = self._create_toolbar_button(
            '↪️\nПовторить',
            callback=self.redo_action,
            tooltip='Повторить отмененное действие (Ctrl+Y)',
            enabled=False,
            rich_tooltip_title='Повторить действие',
            rich_tooltip_desc='Повторяет последнее отмененное действие.',
            rich_tooltip_shortcut='Ctrl+Y'
        )
        toolbar.add_button(self.redo_button)

        # ========== ГРУППА: Вид и настройки ==========
        self.move_xy_plane_btn = self._create_toolbar_button(
            '🟦\nПеренести\nXY',
            callback=self.start_xy_plane_move_mode,
            tooltip='Перенести плоскость XY через выбранную точку'
        )
        toolbar.add_button(self.move_xy_plane_btn)

        self.toggle_belt_lines_btn = self._create_toolbar_button(
            '👁️\nЛинии\nпоясов',
            callback=self.toggle_belt_lines,
            tooltip='Показать/скрыть линии поясов',
            checkable=True,
            checked=True
        )
        toolbar.add_button(self.toggle_belt_lines_btn)

        self.toggle_tower_visualization_btn = self._create_toolbar_button(
            '🏗️\nБашня\n3D',
            callback=self.toggle_tower_visualization,
            tooltip='Показать/скрыть визуализацию башни из конструктора',
            checkable=True,
            checked=True,
            enabled=False  # Включится, когда будет загружен чертеж
        )
        toolbar.add_button(self.toggle_tower_visualization_btn)

        self.tower_builder_toggle_btn = self._create_toolbar_button(
            '🏗️\nКонструктор',
            callback=self.toggle_tower_builder_panel,
            tooltip='Показать или скрыть конструктор башни',
            checkable=True,
            checked=False
        )
        toolbar.add_button(self.tower_builder_toggle_btn)

        toolbar.add_button(self._create_toolbar_button(
            '🔄\nСброс\nвида',
            callback=self.reset_camera,
            tooltip='Сбросить вид камеры к исходному положению'
        ))

        return toolbar
    
    def setup_colors(self):
        """Настройка цветов для поясов"""
        # Предопределенные цвета для поясов (RGB)
        colors = [
            (1.0, 0.0, 0.0, 1.0),  # Красный
            (0.0, 1.0, 0.0, 1.0),  # Зеленый
            (0.0, 0.0, 1.0, 1.0),  # Синий
            (1.0, 1.0, 0.0, 1.0),  # Желтый
            (1.0, 0.0, 1.0, 1.0),  # Пурпурный
            (0.0, 1.0, 1.0, 1.0),  # Циан
            (1.0, 0.5, 0.0, 1.0),  # Оранжевый
            (0.5, 0.0, 1.0, 1.0),  # Фиолетовый
            (0.0, 0.5, 0.5, 1.0),  # Бирюзовый
            (0.5, 0.5, 0.0, 1.0),  # Оливковый
        ]
        
        for i in range(20):  # Поддержка до 20 поясов
            self.belt_colors[i] = colors[i % len(colors)]
        
        # Цвет по умолчанию для точек без пояса
        self.belt_colors[None] = (0.5, 0.5, 0.5, 1.0)  # Серый
    
    @staticmethod
    def _normalize_vector(vec: Optional[np.ndarray]) -> Optional[np.ndarray]:
        if vec is None:
            return None
        norm = float(np.linalg.norm(vec))
        if norm < 1e-9:
            return None
        return vec / norm

    @staticmethod
    def _normalize_text_color(color: Any) -> QColor:
        """Приводит normalized RGBA (0..1) к QColor с непрозрачной альфой 0..255."""
        if isinstance(color, QColor):
            return color

        if isinstance(color, (tuple, list, np.ndarray)):
            components = list(color)
            if len(components) in (3, 4):
                numeric: List[float] = []
                has_float_component = False
                for component in components:
                    if isinstance(component, np.generic):
                        component = component.item()
                    has_float_component = has_float_component or isinstance(component, float)
                    if not isinstance(component, (int, float)):
                        break
                    numeric.append(float(component))
                else:
                    if has_float_component and all(0.0 <= value <= 1.0 for value in numeric):
                        if len(numeric) == 3:
                            return QColor.fromRgbF(numeric[0], numeric[1], numeric[2], 1.0)
                        return QColor.fromRgbF(numeric[0], numeric[1], numeric[2], numeric[3])

        return pg.mkColor(color)

    @staticmethod
    def _build_point_label(row: pd.Series, dataframe_idx: Any) -> str:
        """Р’РѕР·РІСЂР°С‰Р°РµС‚ РїРѕРґРїРёСЃСЊ С‚РѕС‡РєРё РґР»СЏ 3D-РІРёРґР° Р±РµР· С‚РµС…РЅРёС‡РµСЃРєРѕРіРѕ РЅРѕРјРµСЂР°."""
        raw_name = str(row.get('name', '')).strip()
        if raw_name and raw_name.lower() != 'nan':
            return raw_name
        return f'Point {dataframe_idx}'

    @staticmethod
    def _compute_outward_xy_direction(anchor_xy: np.ndarray, center_xy: np.ndarray) -> np.ndarray:
        """Возвращает нормализованное направление от центра наружу в плоскости XY."""
        anchor = np.asarray(anchor_xy, dtype=float)
        center = np.asarray(center_xy, dtype=float)
        direction = anchor - center
        norm = float(np.linalg.norm(direction))
        if norm < 1e-9:
            return np.array([1.0, 0.0], dtype=float)
        return direction / norm

    @classmethod
    def _compute_point_label_position(
        cls,
        point_xyz: np.ndarray,
        center_xy: np.ndarray,
        lateral_offset: float,
        vertical_offset: float,
    ) -> Tuple[float, float, float]:
        """Сдвигает подпись точки вверх и немного наружу от линии пояса."""
        point = np.asarray(point_xyz, dtype=float)
        outward = cls._compute_outward_xy_direction(point[:2], center_xy)
        return (
            float(point[0] + outward[0] * lateral_offset),
            float(point[1] + outward[1] * lateral_offset),
            float(point[2] + vertical_offset),
        )

    @classmethod
    def _compute_belt_label_position(
        cls,
        line_points: np.ndarray,
        center_xy: np.ndarray,
        lateral_offset: float,
        vertical_drop: float,
    ) -> Tuple[float, float, float]:
        """Размещает подпись пояса у нижней точки и сдвигает ее вниз и наружу."""
        points = np.asarray(line_points, dtype=float)
        anchor = points[0]
        outward = cls._compute_outward_xy_direction(anchor[:2], center_xy)
        return (
            float(anchor[0] + outward[0] * lateral_offset),
            float(anchor[1] + outward[1] * lateral_offset),
            float(anchor[2] - vertical_drop),
        )

    @staticmethod
    def _compute_character_width_pixels(font) -> float:
        """Возвращает ширину одного символа для текущего шрифта в пикселях."""
        metrics = pg.QtGui.QFontMetrics(font)
        return float(max(metrics.horizontalAdvance('0'), metrics.averageCharWidth(), 1))

    def _project_world_to_screen(self, point_xyz: np.ndarray) -> Optional[QPointF]:
        """Проецирует мировую точку в экранные координаты текущего GLViewWidget."""
        if self.glview is None or self.glview.width() <= 0 or self.glview.height() <= 0:
            return None
        try:
            viewport = (0, 0, self.glview.width(), self.glview.height())
            region = viewport
            projection = self.glview.projectionMatrix(region, viewport)
            transform = projection * self.glview.viewMatrix()
            vec = pg.QtGui.QVector3D(*np.asarray(point_xyz, dtype=float))
            projected = transform.map(vec)
            x_ndc = projected.x()
            y_ndc = projected.y()
            x_screen = (x_ndc + 1.0) * 0.5 * self.glview.width()
            y_screen = (1.0 - y_ndc) * 0.5 * self.glview.height()
            return QPointF(float(x_screen), float(y_screen))
        except Exception:
            return None

    def _compute_point_label_screen_offset(
        self,
        point_xyz: np.ndarray,
        center_xy: np.ndarray,
        pixel_offset: float,
    ) -> QPointF:
        """Вычисляет экранный сдвиг подписи точки наружу от центра башни."""
        point = np.asarray(point_xyz, dtype=float)
        outward = self._compute_outward_xy_direction(point[:2], center_xy)
        screen_base = self._project_world_to_screen(point)
        screen_probe = self._project_world_to_screen(
            np.array([point[0] + outward[0], point[1] + outward[1], point[2]], dtype=float)
        )
        if screen_base is None or screen_probe is None:
            return QPointF(float(pixel_offset), 0.0)

        delta_x = float(screen_probe.x() - screen_base.x())
        delta_y = float(screen_probe.y() - screen_base.y())
        norm = math.hypot(delta_x, delta_y)
        if norm < 1e-9:
            return QPointF(float(pixel_offset), 0.0)
        scale = float(pixel_offset) / norm
        return QPointF(delta_x * scale, delta_y * scale)
    
    @staticmethod
    def _build_is_station_mask(series: pd.Series) -> pd.Series:
        series = series.copy()
        if series.dtype == 'object':
            string_mask = series.map(lambda value: isinstance(value, str))
            if string_mask.any():
                lowered = series[string_mask].str.strip().str.lower()
                mapping = {'true': True, 'false': False, '1': True, '0': False, 'yes': True, 'no': False}
                mapped = lowered.map(mapping)
                valid_idx = mapped.dropna().index
                if len(valid_idx) > 0:
                    series.loc[valid_idx] = mapped.loc[valid_idx]
            series = series.infer_objects(copy=False)
        null_mask = series.isna()
        if null_mask.any():
            series.loc[null_mask] = False
        return series.astype(bool)
    
    def add_coordinate_axes(self):
        """Добавление осей координат (только для ориентации)"""
        # Автоматическая длина осей будет установлена при загрузке данных
        # Пока не добавляем оси - они добавятся в update_coordinate_axes()
        pass
    
    def update_coordinate_axes(self):
        """Обновление осей координат с учетом размеров данных."""
        if self.glview is None:
            return

        for item in self.axis_items:
            try:
                self.glview.removeItem(item)
            except Exception:
                pass
        self.axis_items.clear()

        if self.data is None or self.data.empty:
            self.clear_xy_plane_visual()
            return

        positions = self.data[['x', 'y', 'z']].values
        if positions.size == 0:
            return

        extent = positions.max(axis=0) - positions.min(axis=0)
        max_extent = float(np.max(extent)) if np.any(extent > 0) else 1.0
        axis_length = max(max_extent * 0.15, 0.5)

        station_origin = None
        if 'is_station' in self.data.columns:
            station_mask = self._build_is_station_mask(self.data['is_station'])
            stations = self.data[station_mask]
            if not stations.empty:
                p0 = stations.iloc[0]
                station_origin = np.array([
                    float(p0['x']),
                    float(p0['y']),
                    float(p0['z'])
                ], dtype=float)

        center_point = None
        if hasattr(self, 'section_data') and self.section_data:
            try:
                lowest = sorted(self.section_data, key=lambda s: s.get('height', 0.0))[0]
                pts = np.array(lowest.get('points', []), dtype=float)
                if pts.size:
                    center_point = np.array([
                        float(np.mean(pts[:, 0])),
                        float(np.mean(pts[:, 1])),
                        float(np.mean(pts[:, 2]))
                    ], dtype=float)
            except Exception:
                center_point = None

        if center_point is None:
            try:
                non_station = self.data.copy()
                if 'is_station' in non_station.columns:
                    mask = self._build_is_station_mask(non_station['is_station'])
                    non_station = non_station[~mask]
                if not non_station.empty:
                    zmin = float(non_station['z'].min())
                    slab = non_station[np.abs(non_station['z'] - zmin) <= 0.15]
                    if slab.empty:
                        slab = non_station[non_station['z'] == zmin]
                    if not slab.empty:
                        center_point = np.array([
                            float(slab['x'].mean()),
                            float(slab['y'].mean()),
                            float(slab['z'].mean())
                        ], dtype=float)
            except Exception:
                center_point = None

        if center_point is None and self.processed_results:
            centers_df = self.processed_results.get('centers')
            try:
                if isinstance(centers_df, pd.DataFrame) and not centers_df.empty:
                    df = centers_df.copy()
                    if 'z' in df.columns:
                        df = df.sort_values('z')
                        first = df.iloc[0]
                        center_point = np.array([
                            float(first.get('x', 0.0)),
                            float(first.get('y', 0.0)),
                            float(first.get('z', 0.0)),
                        ], dtype=float)
            except Exception:
                center_point = None

        z_unit = np.array([0.0, 0.0, 1.0], dtype=float)

        y_dir: Optional[np.ndarray] = None
        if station_origin is not None and center_point is not None:
            dir_xy = center_point[:2] - station_origin[:2]
            if np.linalg.norm(dir_xy) > 1e-9:
                y_dir = np.array([dir_xy[0], dir_xy[1], 0.0], dtype=float)
                y_dir = self._normalize_vector(y_dir)

        if y_dir is None and self.processed_results:
            local_cs = self.processed_results.get('local_cs')
            if local_cs and local_cs.get('valid', False):
                try:
                    candidate = np.array(local_cs.get('y_axis', (0.0, 1.0, 0.0)), dtype=float)
                    if candidate.shape[0] >= 3:
                        candidate[2] = 0.0
                    y_dir = self._normalize_vector(candidate)
                except Exception:
                    y_dir = None

        if y_dir is None:
            y_dir = np.array([0.0, 1.0, 0.0], dtype=float)

        x_dir = np.cross(y_dir, z_unit)
        x_dir = self._normalize_vector(x_dir)
        if x_dir is None:
            x_dir = np.array([1.0, 0.0, 0.0], dtype=float)

        y_dir = np.cross(z_unit, x_dir)
        y_dir = self._normalize_vector(y_dir)
        if y_dir is None:
            y_dir = np.array([0.0, 1.0, 0.0], dtype=float)

        local_x = x_dir
        local_y = y_dir
        local_z = z_unit

        axes_vectors = {
            'X': local_x,
            'Y': local_y,
            'Z': local_z,
        }

        if station_origin is None:
            min_pos = positions.min(axis=0)
            station_origin = min_pos.astype(float)

        if station_origin is not None:
            self._add_axis_gizmo(station_origin, axes_vectors, axis_length * 0.45, origin_label='S')

        tower_origin = None
        if self.processed_results:
            axis_params = self.processed_results.get('axis')
            if axis_params and axis_params.get('valid', False):
                tower_origin = np.array([
                    float(axis_params.get('x0', station_origin[0] if station_origin is not None else 0.0)),
                    float(axis_params.get('y0', station_origin[1] if station_origin is not None else 0.0)),
                    float(axis_params.get('z0', station_origin[2] if station_origin is not None else 0.0)),
                ], dtype=float)
        if tower_origin is None and center_point is not None:
            tower_origin = center_point

        if tower_origin is not None:
            self._add_axis_gizmo(tower_origin, axes_vectors, axis_length * 0.35, origin_label='O')

    def _add_axis_gizmo(
        self,
        origin: np.ndarray,
        axes_vectors: Dict[str, np.ndarray],
        length: float,
        origin_label: Optional[str] = None,
    ) -> None:
        origin = np.array(origin, dtype=float)
        colors = {
            'X': (1.0, 0.2, 0.2, 1.0),
            'Y': (0.2, 0.8, 0.3, 1.0),
            'Z': (0.2, 0.4, 1.0, 1.0),
        }

        marker = gl.GLScatterPlotItem(
            pos=np.array([origin]),
            color=(1.0, 1.0, 1.0, 0.9),
            size=10,
            pxMode=True,
        )
        self.glview.addItem(marker)
        self.axis_items.append(marker)

        if origin_label:
            font = pg.QtGui.QFont('Arial', 10, pg.QtGui.QFont.Weight.Bold)
            label_item = self._create_text_item(
                position=(origin[0], origin[1], origin[2] + length * 0.15),
                text=origin_label,
                color=(1.0, 1.0, 1.0, 1.0),
                font=font,
            )
            if label_item is not None:
                self.glview.addItem(label_item)
                self.axis_items.append(label_item)

        for axis_name in ('X', 'Y', 'Z'):
            direction = axes_vectors.get(axis_name)
            if direction is None:
                continue
            direction = np.array(direction, dtype=float)
            norm = np.linalg.norm(direction)
            if norm < 1e-9:
                continue
            direction = direction / norm
            items = self._create_arrow_items(origin, direction, length, colors[axis_name])
            for item in items:
                self.glview.addItem(item)
                self.axis_items.append(item)

            label_font = pg.QtGui.QFont('Arial', 10, pg.QtGui.QFont.Weight.Bold)
            label_pos = origin + direction * (length * 0.75)
            text_item = self._create_text_item(
                position=(label_pos[0], label_pos[1], label_pos[2]),
                text=axis_name,
                color=colors[axis_name],
                font=label_font,
            )
            if text_item is not None:
                self.glview.addItem(text_item)
                self.axis_items.append(text_item)

    def _create_arrow_items(
        self,
        origin: np.ndarray,
        direction: np.ndarray,
        length: float,
        color: Tuple[float, float, float, float],
    ) -> List[gl.GLGraphicsItem]:
        direction = np.array(direction, dtype=float)
        norm = np.linalg.norm(direction)
        if norm < 1e-9 or length <= 0.0:
            return []
        direction = direction / norm

        shaft_ratio = 0.75
        head_ratio = 1.0 - shaft_ratio
        shaft_end = origin + direction * (length * shaft_ratio)
        arrow_tip = origin + direction * length

        shaft = gl.GLLinePlotItem(pos=np.array([origin, shaft_end]), color=color, width=2.0, antialias=True)

        base_vec = np.cross(direction, np.array([0.0, 0.0, 1.0], dtype=float))
        if np.linalg.norm(base_vec) < 1e-6:
            base_vec = np.cross(direction, np.array([0.0, 1.0, 0.0], dtype=float))
        base_vec = base_vec / np.linalg.norm(base_vec)
        base_vec2 = np.cross(direction, base_vec)
        base_vec2 = base_vec2 / np.linalg.norm(base_vec2)

        head_length = length * head_ratio
        head_radius = head_length * 0.6
        head_base = arrow_tip - direction * head_length

        head_points = [
            np.array([arrow_tip, head_base + base_vec * head_radius]),
            np.array([arrow_tip, head_base - base_vec * head_radius]),
            np.array([arrow_tip, head_base + base_vec2 * head_radius]),
            np.array([arrow_tip, head_base - base_vec2 * head_radius]),
        ]
        head_lines = [gl.GLLinePlotItem(pos=pts, color=color, width=1.5, antialias=True) for pts in head_points]
        return [shaft] + head_lines

    def clear_xy_plane_visual(self):
        """Удаляет визуализацию плоскости XY из сцены."""
        if self.xy_plane_item is not None:
            try:
                self.glview.removeItem(self.xy_plane_item)
            except Exception:
                pass
            self.xy_plane_item = None

    def initialize_xy_plane_from_positions(self, positions: Optional[np.ndarray]) -> None:
        """Инициализирует положение плоскости XY на основе текущих данных."""
        if positions is None or positions.size == 0:
            self.xy_plane_center = np.array([0.0, 0.0, 0.0], dtype=float)
            self.xy_plane_size = 10.0
            self.xy_plane_initialized = False
            self.clear_xy_plane_visual()
            return

        extent_x = float(np.max(positions[:, 0]) - np.min(positions[:, 0]))
        extent_y = float(np.max(positions[:, 1]) - np.min(positions[:, 1]))
        size_candidate = max(extent_x, extent_y, 1.0) * 1.2
        if not np.isfinite(size_candidate):
            size_candidate = 10.0

        self.xy_plane_size = max(size_candidate, 5.0)
        center_x = float(np.mean(positions[:, 0]))
        center_y = float(np.mean(positions[:, 1]))
        base_z = float(np.min(positions[:, 2]))
        self.xy_plane_center = np.array([center_x, center_y, base_z], dtype=float)
        self.xy_plane_initialized = True

    def update_xy_plane_geometry(self, positions: Optional[np.ndarray] = None) -> None:
        """Перестраивает полупрозрачную плоскость XY."""
        if self.glview is None:
            return

        if positions is None:
            if self.data is None or self.data.empty:
                self.clear_xy_plane_visual()
                return
            positions = self.data[['x', 'y', 'z']].values

        if positions is None or positions.size == 0:
            self.clear_xy_plane_visual()
            return

        extent_x = float(np.max(positions[:, 0]) - np.min(positions[:, 0]))
        extent_y = float(np.max(positions[:, 1]) - np.min(positions[:, 1]))
        size_candidate = max(extent_x, extent_y, 1.0) * 1.2
        if not np.isfinite(size_candidate):
            size_candidate = 10.0
        self.xy_plane_size = max(size_candidate, 5.0)

        if not self.xy_plane_initialized:
            self.initialize_xy_plane_from_positions(positions)

        cx, cy, cz = self.xy_plane_center
        half = self.xy_plane_size / 2.0
        vertices = np.array([
            [cx - half, cy - half, cz],
            [cx + half, cy - half, cz],
            [cx + half, cy + half, cz],
            [cx - half, cy + half, cz]
        ], dtype=float)
        faces = np.array([[0, 1, 2], [0, 2, 3]], dtype=int)
        face_colors = np.array([
            [0.0, 0.45, 0.9, 0.18],
            [0.0, 0.45, 0.9, 0.18]
        ], dtype=float)
        edge_color = (0.0, 0.35, 0.7, 0.4)

        self.clear_xy_plane_visual()
        plane_item = gl.GLMeshItem(
            vertexes=vertices,
            faces=faces,
            faceColors=face_colors,
            smooth=False,
            drawEdges=True,
            edgeColor=edge_color,
            glOptions='translucent'
        )
        self.glview.addItem(plane_item)
        self.xy_plane_item = plane_item

    def set_xy_plane_center(self, center: np.ndarray, update_geometry: bool = True) -> None:
        """Устанавливает новое положение плоскости XY."""
        center = np.array(center, dtype=float)
        if center.shape != (3,):
            raise ValueError('Ожидается центр плоскости в формате (x, y, z)')
        self.xy_plane_center = center
        self.xy_plane_initialized = True
        if update_geometry:
            self.update_xy_plane_geometry()

    def get_xy_plane_state(self) -> dict:
        """Возвращает состояние плоскости XY для сохранения проекта."""
        return {
            'center': self.xy_plane_center.tolist(),
            'size': float(self.xy_plane_size),
            'initialized': bool(self.xy_plane_initialized)
        }

    def set_xy_plane_state(self, state: Optional[dict], update_geometry: bool = True) -> None:
        """Восстанавливает состояние плоскости XY из сохранённого словаря."""
        if not state:
            self.xy_plane_initialized = False
            if update_geometry:
                self.update_xy_plane_geometry()
            return

        center = state.get('center')
        size = state.get('size')
        initialized = state.get('initialized', True)

        if center is not None:
            try:
                self.xy_plane_center = np.array(center, dtype=float)
            except Exception:
                logger.warning('Некорректный центр плоскости XY в сохранённом состоянии, используется значение по умолчанию')
                self.xy_plane_center = np.array([0.0, 0.0, 0.0], dtype=float)

        if size is not None:
            try:
                self.xy_plane_size = max(float(size), 5.0)
            except (TypeError, ValueError):
                logger.warning('Некорректный размер плоскости XY в сохранённом состоянии, используется значение по умолчанию')
                self.xy_plane_size = 10.0

        self.xy_plane_initialized = bool(initialized)
        if update_geometry:
            self.update_xy_plane_geometry()

    def _get_xy_plane_height(self) -> float:
        """Возвращает высоту плоскости XY."""
        return float(self.xy_plane_center[2])

    def start_xy_plane_move_mode(self):
        """Активирует режим, в котором пользователь выбирает точку для переноса плоскости XY."""
        if self.data is None or self.data.empty:
            self.info_label.setText('⚠ Нет данных для переноса плоскости')
            return

        self.xy_plane_move_mode = True
        self.info_label.setText('🔵 Выберите точку, через которую должна проходить плоскость XY (ESC - отмена)')

    def apply_xy_plane_translation(self, point_idx: int):
        """Переносит плоскость XY через выбранную точку."""
        if self.data is None or self.data.empty:
            self.xy_plane_move_mode = False
            self.info_label.setText('⚠ Нет данных для переноса плоскости')
            return

        if point_idx < 0 or point_idx >= len(self.data):
            self.xy_plane_move_mode = False
            self.info_label.setText('⚠ Выбранная точка недоступна')
            return

        description = 'Перенос плоскости XY'
        try:
            with self.undo_transaction(description) as tx:
                point = self.data.iloc[int(point_idx)]
                center = np.array([float(point['x']), float(point['y']), float(point['z'])], dtype=float)
                self.set_xy_plane_center(center)
                tx.commit()

            point_name = point['name'] if 'name' in self.data.columns else f'Точка {point_idx}'
            self.info_label.setText(
                f'✓ Плоскость XY перенесена на точку {point_name} (Z={self.xy_plane_center[2]:.3f} м)'
            )
            logger.info(
                f"Плоскость XY перенесена на точку {point_name}: "
                f"центр=({self.xy_plane_center[0]:.3f}, {self.xy_plane_center[1]:.3f}, {self.xy_plane_center[2]:.3f})"
            )
        except Exception as e:
            logger.error(f"Ошибка переноса плоскости XY: {e}", exc_info=True)
            self.info_label.setText(f'❌ Ошибка переноса плоскости XY: {str(e)}')
        finally:
            self.xy_plane_move_mode = False

    def set_data(self, data: pd.DataFrame, preserve_history: bool = False):
        """
        Установить данные для отображения
        
        Args:
            data: DataFrame с колонками x, y, z, name, и опционально belt, is_station
        """
        # Clear structural lines when setting new data
        if hasattr(self, 'structural_items'):
            for item in self.structural_items:
                self.glview.removeItem(item)
            self.structural_items.clear()
        
        # Если загружаются новые данные без blueprint, сбросить флаг применения
        # (blueprint может быть применен только к конкретным данным)
        self._blueprint_applied = False
        # Очистить предпросмотр при загрузке новых данных
        self._clear_tower_preview()

        # Защита от зацикливания: проверяем, не выполняется ли уже обновление
        if not hasattr(self, '_updating_3d_view'):
            self._updating_3d_view = False
        
        if self._updating_3d_view:
            logger.debug("Пропуск set_data - уже выполняется обновление 3D вида")
            return
        
        # ВАЖНО: сохраняем порядок данных как есть, не сортируем
        # Копируем данные с сохранением индексов и порядка строк
        self.data = data.copy()
        
        # Логируем информацию о данных для отладки
        if not self.data.empty:
            logger.debug(
                f"set_data: Загружено {len(self.data)} точек. "
                f"Первые 5 индексов: {list(self.data.index[:5])}, "
                f"последние 5 индексов: {list(self.data.index[-5:])}"
            )
        
        self._ensure_point_indices()

        if self.data is None or self.data.empty:
            self.xy_plane_initialized = False
            self.clear_xy_plane_visual()
        elif not preserve_history:
            self.xy_plane_initialized = False
        
        # Гарантируем наличие ключевых колонок
        if 'belt' not in self.data.columns:
            self.data['belt'] = None
        if 'is_station' not in self.data.columns:
            self.data['is_station'] = False
        else:
            self.data['is_station'] = self._build_is_station_mask(self.data['is_station'])
        if 'tower_part' not in self.data.columns:
            self.data['tower_part'] = 1
        if 'tower_part_memberships' not in self.data.columns:
            self.data['tower_part_memberships'] = None
        if 'is_part_boundary' not in self.data.columns:
            self.data['is_part_boundary'] = False
        else:
            boundary_series = self.data['is_part_boundary']
            if boundary_series.dtype != bool:
                boundary_series = boundary_series.fillna(False)
                try:
                    boundary_series = boundary_series.astype(bool)
                except Exception:
                    boundary_series = boundary_series.map(lambda v: bool(v))
            self.data['is_part_boundary'] = boundary_series
        
        # Активируем кнопку создания секций, если есть данные с поясами
        if hasattr(self, 'create_sections_btn'):
            has_belts = self.data is not None and not self.data.empty and 'belt' in self.data.columns
            has_valid_belts = bool(has_belts and self.data['belt'].notna().any())
            self.create_sections_btn.setEnabled(has_valid_belts)
        
        # Обновляем внутренние индексы и 3D представление без генерации лишних сигналов
        self._ensure_point_indices()
        # Обновляем IndexManager с новыми данными
        self.index_manager.set_data(self.data)
        self._refresh_index_mapping()
        self.selected_indices = []
        self.pending_point_idx = None
        
        # Обновляем 3D вид только если не выполняется текущий апдейт
        if not getattr(self, '_updating_3d_view', False):
            self.update_3d_view()
        self.update_info_label()
        
        # Центрируем камеру только при загрузке данных
        self.reset_camera()

        if preserve_history:
            self.update_undo_redo_buttons()
        else:
            self.clear_history()
    
    def _ensure_point_indices(self, dataframe: Optional[pd.DataFrame] = None):
        """
        Гарантирует наличие уникального столбца point_index для стабильной нумерации точек.
        Обновляет счетчик максимального индекса.
        
        Оптимизированная версия:
        - Избегает ненужных пересозданий индексов
        - Более эффективная проверка уникальности
        - Валидация существующих индексов
        
        Args:
            dataframe: Опциональный DataFrame для обработки. Если None, используется self.data.
        """
        df = dataframe if dataframe is not None else self.data
        if df is None or df.empty:
            self.point_index_counter = 0
            return
        
        if 'point_index' not in df.columns:
            # Создаем новые индексы с 1
            df['point_index'] = np.arange(1, len(df) + 1, dtype=int)
            self.point_index_counter = len(df)
        else:
            # Оптимизированная проверка и исправление существующих индексов
            point_idx_series = pd.to_numeric(df['point_index'], errors='coerce')
            
            # Быстрая проверка: все ли индексы валидны и уникальны?
            valid_mask = point_idx_series.notna()
            if valid_mask.all():
                # Все значения валидны, проверяем уникальность
                unique_values = point_idx_series.unique()
                if len(unique_values) == len(point_idx_series):
                    # Все индексы уникальны - обновляем только счетчик
                    self.point_index_counter = int(point_idx_series.max())
                    if dataframe is None:
                        self.data = df
                    return
            
            # Нужно исправить индексы: есть пропуски или дубликаты
            used_indices: set = set()
            next_candidate = int(point_idx_series[point_idx_series.notna()].max()) if point_idx_series.notna().any() else 0
            
            # Используем векторные операции где возможно
            point_idx_array = point_idx_series.values
            
            for i in range(len(point_idx_array)):
                value = point_idx_array[i]
                
                # Проверяем валидность и уникальность
                if pd.isna(value) or (isinstance(value, (int, float)) and int(value) in used_indices):
                    next_candidate += 1
                    point_idx_array[i] = next_candidate
                    used_indices.add(next_candidate)
                else:
                    int_value = int(value)
                    used_indices.add(int_value)
                    if int_value > next_candidate:
                        next_candidate = int_value
            
            # Обновляем Series
            df['point_index'] = pd.Series(point_idx_array, dtype=int, index=df.index)
            self.point_index_counter = next_candidate
        
        if dataframe is None:
            self.data = df
    
    def _get_next_point_index(self) -> int:
        """Возвращает следующий уникальный индекс точки."""
        self.point_index_counter += 1
        return self.point_index_counter
    
    def get_data(self) -> pd.DataFrame:
        """Получить текущие данные"""
        return self.data.copy() if self.data is not None else pd.DataFrame()
    
    def update_3d_view(self):
        """Обновление 3D визуализации"""
        # Защита от зацикливания: проверяем, не выполняется ли уже обновление
        if not hasattr(self, '_updating_3d_view'):
            self._updating_3d_view = False
        
        if self._updating_3d_view:
            logger.debug("Пропуск update_3d_view - уже выполняется")
            return
        
        self._updating_3d_view = True
        try:
            if self.data is None or self.data.empty:
                self.clear_xy_plane_visual()
                return
            
            self._refresh_index_mapping()
            
            # Удаляем старые объекты
            if self.point_scatter is not None:
                self.glview.removeItem(self.point_scatter)
            
            for label in self.point_labels:
                self.glview.removeItem(label)
            self.point_labels.clear()
            
            for line in self.belt_lines:
                self.glview.removeItem(line)
            self.belt_lines.clear()
            
            # Подготовка данных для scatter plot
            # КРИТИЧЕСКИ ВАЖНО: positions создается в позиционном порядке (iloc)
            # positions[i] соответствует self.data.iloc[i]
            # Используем явную итерацию для гарантии соответствия порядка
            positions_list = []
            for pos_idx in range(len(self.data)):
                row = self.data.iloc[pos_idx]
                pos_3d = np.array([
                    float(row['x']),
                    float(row['y']),
                    float(row['z'])
                ], dtype=float)
                positions_list.append(pos_3d)
            
            positions = np.array(positions_list)
            
            # ВАЛИДАЦИЯ: проверяем соответствие размеров
            if len(positions) != len(self.data):
                logger.error(
                    f"update_3d_view: Несоответствие размеров! "
                    f"positions.shape={positions.shape}, len(data)={len(self.data)}"
                )
                self._updating_3d_view = False
                return
            
            # ДОПОЛНИТЕЛЬНАЯ ВАЛИДАЦИЯ: проверяем, что positions соответствует данным
            # Сравниваем первые и последние несколько точек
            if len(positions) > 0:
                validation_count = min(3, len(positions))
                for i in range(validation_count):
                    row = self.data.iloc[i]
                    expected = np.array([float(row['x']), float(row['y']), float(row['z'])])
                    actual = positions[i]
                    if not np.allclose(actual, expected, atol=1e-6):
                        logger.error(
                            f"update_3d_view: Несоответствие координат для позиции {i}! "
                            f"expected={expected}, actual={actual}"
                        )
                        self._updating_3d_view = False
                        return
            
            self.update_xy_plane_geometry(positions)
            
            # Цвета точек по поясам с различием основных и добавленных
            # ВАЖНО: используем позиционную итерацию (iloc) для гарантии соответствия с positions
            colors = []
            for pos_idx in range(len(self.data)):
                row = self.data.iloc[pos_idx]
                belt = row['belt']
                base_color = self.belt_colors.get(belt, self.belt_colors[None])
                
                # Проверяем, является ли точка автоматически добавленной
                point_name = row['name'] if 'name' in self.data.columns else ''
                is_auto_added = isinstance(point_name, str) and point_name.startswith('S') and '_B' in point_name
                
                if is_auto_added:
                    # Добавленные точки - более светлые (добавляем прозрачность и осветляем)
                    color = (
                        base_color[0] * 0.6 + 0.4,  # Осветляем R
                        base_color[1] * 0.6 + 0.4,  # Осветляем G
                        base_color[2] * 0.6 + 0.4,  # Осветляем B
                        0.6  # Полупрозрачные
                    )
                else:
                    # Основные точки - насыщенные
                    color = base_color
                
                colors.append(color)
            
            colors = np.array(colors)
            
            # ВАЛИДАЦИЯ: проверяем соответствие размеров массивов
            if len(colors) != len(positions):
                logger.error(
                    f"update_3d_view: Несоответствие размеров colors и positions! "
                    f"len(colors)={len(colors)}, len(positions)={len(positions)}"
                )
                self._updating_3d_view = False
                return
            
            # Размеры точек (компактные)
            sizes = np.full(len(self.data), 6.0)  # Уменьшенный размер
            # ВАЖНО: selected_indices содержит позиции (iloc индексы), а не индексы DataFrame
            # КРИТИЧЕСКИ ВАЖНО: проверяем валидность selected_indices перед использованием
            valid_selected_indices = [pos_idx for pos_idx in self.selected_indices if 0 <= pos_idx < len(sizes)]
            if len(valid_selected_indices) != len(self.selected_indices):
                logger.warning(
                    f"update_3d_view: Некоторые selected_indices невалидны! "
                    f"Было: {self.selected_indices}, стало: {valid_selected_indices}, "
                    f"len(data)={len(self.data)}"
                )
                self.selected_indices = valid_selected_indices
            
            for pos_idx in self.selected_indices:
                if 0 <= pos_idx < len(sizes):  # Проверяем, что позиция действительна
                    sizes[pos_idx] = 12.0  # Выбранные точки крупнее
                    # Логируем для отладки
                    if pos_idx < len(self.data):
                        point_name = self.data.iloc[pos_idx].get('name', 'N/A') if 'name' in self.data.columns else 'N/A'
                        point_coords = self.data.iloc[pos_idx][['x', 'y', 'z']].values
                        logger.info(
                            f"update_3d_view: Выделена точка pos={pos_idx}, name={point_name}, "
                            f"coords=({point_coords[0]:.3f}, {point_coords[1]:.3f}, {point_coords[2]:.3f})"
                        )
            
            # ВАЛИДАЦИЯ: проверяем соответствие размеров sizes
            if len(sizes) != len(positions):
                logger.error(
                    f"update_3d_view: Несоответствие размеров sizes и positions! "
                    f"len(sizes)={len(sizes)}, len(positions)={len(positions)}"
                )
                self._updating_3d_view = False
                return
            
            # Создаем scatter plot
            # КРИТИЧЕСКИ ВАЖНО: positions создается в том же порядке, что и self.data.iloc
            # positions[i] = self.data.iloc[i][['x', 'y', 'z']]
            # Это гарантирует, что point_scatter.pos[i] соответствует self.data.iloc[i] и self.data.index[i]
            positions_copy = positions.copy()  # Копируем для безопасности
            self.point_scatter = gl.GLScatterPlotItem(
                pos=positions_copy,
                color=colors,
                size=sizes,
                pxMode=True  # Размер в пикселях, не зависит от масштаба
            )
            self.glview.addItem(self.point_scatter)
            
            # КРИТИЧЕСКАЯ ВАЛИДАЦИЯ: проверяем, что point_scatter.pos соответствует positions после создания
            if hasattr(self.point_scatter, 'pos') and self.point_scatter.pos is not None:
                if len(self.point_scatter.pos) != len(positions_copy):
                    logger.error(
                        f"update_3d_view: КРИТИЧЕСКАЯ ОШИБКА! Размеры не совпадают после создания scatter! "
                        f"point_scatter.pos={len(self.point_scatter.pos)}, positions={len(positions_copy)}"
                    )
                else:
                    # Проверяем первые и последние несколько точек
                    check_count = min(3, len(positions_copy))
                    mismatches = []
                    for i in range(check_count):
                        if not np.allclose(self.point_scatter.pos[i], positions_copy[i], atol=1e-6):
                            mismatches.append((i, positions_copy[i], self.point_scatter.pos[i]))
                    
                    # Проверяем последние точки
                    if len(positions_copy) > check_count:
                        for i in range(max(0, len(positions_copy) - check_count), len(positions_copy)):
                            if not np.allclose(self.point_scatter.pos[i], positions_copy[i], atol=1e-6):
                                mismatches.append((i, positions_copy[i], self.point_scatter.pos[i]))
                    
                    if mismatches:
                        logger.error(
                            f"update_3d_view: КРИТИЧЕСКАЯ ОШИБКА! Несоответствие координат после создания scatter! "
                            f"Несоответствия: {mismatches[:5]}"
                        )
                    else:
                        logger.debug(
                            f"update_3d_view: Валидация scatter пройдена. "
                            f"point_scatter.pos соответствует positions ({len(positions_copy)} точек)"
                        )
            
            # ВАЛИДАЦИЯ: проверяем соответствие positions и данных перед созданием scatter
            if len(positions) > 0 and len(self.data) > 0:
                # Проверяем первые и последние несколько точек для гарантии правильного порядка
                check_count = min(5, len(positions), len(self.data))
                mismatches = []
                for i in range(check_count):
                    row = self.data.iloc[i]
                    expected = np.array([float(row['x']), float(row['y']), float(row['z'])])
                    actual = positions[i]
                    if not np.allclose(actual, expected, atol=1e-6):
                        mismatches.append((i, expected, actual))
                
                # Проверяем последние точки
                if len(positions) > check_count:
                    for i in range(max(0, len(positions) - check_count), len(positions)):
                        row = self.data.iloc[i]
                        expected = np.array([float(row['x']), float(row['y']), float(row['z'])])
                        actual = positions[i]
                        if not np.allclose(actual, expected, atol=1e-6):
                            mismatches.append((i, expected, actual))
                
                if mismatches:
                    logger.error(
                        f"update_3d_view: Обнаружены несоответствия координат перед созданием scatter! "
                        f"Несоответствия: {mismatches[:10]}"  # Показываем первые 10
                    )
                else:
                    logger.debug(
                        f"update_3d_view: Валидация пройдена. Создан point_scatter с {len(positions)} точками. "
                        f"Проверено {check_count * 2} точек (первые и последние)"
                    )
            
            # Добавляем линии поясов
            if self.show_belt_lines:
                self.update_belt_lines()
            
            # Обновляем оси координат
            self.update_coordinate_axes()
            
            # Добавляем текстовые метки (названия точек) В КОНЦЕ, чтобы они были поверх всего
            # Вычисляем смещение для текста
            z_range = positions.max(axis=0)[2] - positions.min(axis=0)[2]
            offset_z = max(z_range * 0.02, 0.3)  # Минимум 0.3 метра
            point_label_font = pg.QtGui.QFont('Arial', 12, pg.QtGui.QFont.Weight.Bold)
            point_label_offset_px = self._compute_character_width_pixels(point_label_font)

            label_source = self.data
            if 'is_station' in self.data.columns:
                station_mask = self._build_is_station_mask(self.data['is_station'])
                non_station = self.data[~station_mask]
                if not non_station.empty:
                    label_source = non_station
            center_xy = np.array(
                [
                    float(label_source['x'].mean()),
                    float(label_source['y'].mean()),
                ],
                dtype=float,
            )
            
            labels_added = 0
            # ВАЖНО: используем позиционную итерацию для соответствия с positions
            for pos_idx in range(len(self.data)):
                row = self.data.iloc[pos_idx]
                dataframe_idx = self.data.index[pos_idx]  # Индекс DataFrame для логирования
                
                point_name = self._build_point_label(row, dataframe_idx)
                point_xyz = np.array([float(row['x']), float(row['y']), float(row['z'])], dtype=float)
                screen_offset = self._compute_point_label_screen_offset(
                    point_xyz=point_xyz,
                    center_xy=center_xy,
                    pixel_offset=point_label_offset_px,
                )

                text_pos = self._compute_point_label_position(
                    point_xyz=point_xyz,
                    center_xy=center_xy,
                    lateral_offset=0.0,
                    vertical_offset=offset_z,
                )
                text_item = self._create_text_item(
                    position=text_pos,
                    text=point_name,
                    color=(1.0, 1.0, 1.0, 1.0),
                    font=point_label_font,
                    screen_offset=screen_offset,
                )
                if text_item is not None:
                    self.glview.addItem(text_item)
                    self.point_labels.append(text_item)
                    labels_added += 1

            logger.info(f"Добавлено {labels_added} текстовых меток из {len(self.data)} точек")
        finally:
            self._updating_3d_view = False
    
    def update_belt_lines(self):
        """Отрисовка линий поясов - последовательные соединения снизу вверх."""
        if self.data is None or self.data.empty:
            return

        belts = self.data[self.data['belt'].notna()].groupby('belt')
        xy_extent = self.data[['x', 'y']].max().values - self.data[['x', 'y']].min().values
        lateral_offset = max(float(np.max(xy_extent)) * 0.03, 0.25)
        z_range = float(self.data['z'].max() - self.data['z'].min()) if 'z' in self.data.columns else 0.0
        vertical_drop = max(z_range * 0.02, 0.5)
        label_source = self.data
        if 'is_station' in self.data.columns:
            station_mask = self._build_is_station_mask(self.data['is_station'])
            non_station = self.data[~station_mask]
            if not non_station.empty:
                label_source = non_station
        center_xy = np.array(
            [
                float(label_source['x'].mean()),
                float(label_source['y'].mean()),
            ],
            dtype=float,
        )

        for belt_num, belt_data in belts:
            if len(belt_data) < 2:
                continue

            color = self.belt_colors.get(belt_num, (0.5, 0.5, 0.5, 1.0))

            sorted_data = belt_data.sort_values(['z', 'name']) if 'name' in belt_data.columns else belt_data.sort_values('z')
            line_points = sorted_data[['x', 'y', 'z']].values

            belt_line = gl.GLLinePlotItem(
                pos=line_points,
                color=color,
                width=2.5,
                antialias=True,
            )
            self.glview.addItem(belt_line)
            self.belt_lines.append(belt_line)

            belt_label = self._create_text_item(
                position=self._compute_belt_label_position(
                    line_points=line_points,
                    center_xy=center_xy,
                    lateral_offset=lateral_offset,
                    vertical_drop=vertical_drop,
                ),
                text=f'Пояс {int(belt_num)}',
                color=(*color[:3], 0.9),
                font=pg.QtGui.QFont('Arial', 10, pg.QtGui.QFont.Weight.Bold),
            )
            if belt_label is not None:
                self.glview.addItem(belt_label)
                self.belt_lines.append(belt_label)
    
    def set_section_lines(self, section_data: List[Dict]):
        """
        Установить данные о секциях для визуализации
        
        Args:
            section_data: Список словарей с информацией о секциях
                [{'height': float, 'points': [(x,y,z),...], 'belt_nums': [...]}, ...]
        """
        self.section_data = section_data
        self.update_section_lines()
        
        # Обновляем состояние кнопок
        has_sections = bool(len(section_data) > 0)
        if hasattr(self, 'build_central_axis_btn'):
            self.build_central_axis_btn.setEnabled(has_sections)
        if hasattr(self, 'remove_sections_btn'):
            self.remove_sections_btn.setEnabled(has_sections)
        if hasattr(self, 'tilt_plane_btn'):
            self.tilt_plane_btn.setEnabled(has_sections)
        if hasattr(self, 'tilt_single_section_btn'):
            self.tilt_single_section_btn.setEnabled(has_sections)
        
        # Если секций нет, скрываем центральную ось
        if not has_sections and self.show_central_axis:
            self.show_central_axis = False
            if self.central_axis_line is not None:
                self.glview.removeItem(self.central_axis_line)
                self.central_axis_line = None
        
        # Обновляем центральную ось, если она была построена и секции есть
        if self.show_central_axis and has_sections:
            self.update_central_axis()
        
        # Обновляем таблицу секций в главном окне
        self.update_data_table_sections()
    
    def update_section_lines(self):
        """Обновить визуализацию линий секций"""
        # Удаляем старые линии секций
        for line in self.section_lines:
            self.glview.removeItem(line)
        self.section_lines.clear()
        
        if not self.section_data:
            return
        
        # Рисуем горизонтальные линии между точками на одном уровне
        for section in self.section_data:
            points = section['points']
            
            if len(points) < 2:
                continue
            
            # Преобразуем в numpy array
            # Замыкаем контур
            pts = points + [points[0]]
            section_points = np.array(pts)
            
            # Рисуем линию, соединяющую все точки секции
            section_line = gl.GLLinePlotItem(
                pos=section_points,
                color=(0.2, 0.8, 0.2, 0.7),  # Зеленый полупрозрачный
                width=2,
                antialias=True
            )
            self.glview.addItem(section_line)
            self.section_lines.append(section_line)
            
            # Добавляем подпись секции
            # Позиция: в начале линии секции, чуть сбоку
            label_pos = section_points[0].copy()
            label_pos[0] += (section_points[-1][0] - section_points[0][0]) * 0.1  # Смещение
            
            section_label = self._create_text_item(
                position=tuple(label_pos),
                text=f'Секция Z={section["height"]:.2f}м',
                color=(0.1, 0.6, 0.1, 0.9),
                font=pg.QtGui.QFont('Arial', 11, pg.QtGui.QFont.Weight.Bold),
            )
            if section_label is not None:
                self.glview.addItem(section_label)
                self.section_lines.append(section_label)
            
            logger.info(f"Отрисована линия секции на высоте {section['height']:.2f}м, точек: {len(points)}")
        
        # Обновляем центральную ось, если она отображается
        if self.show_central_axis:
            self.update_central_axis()
        
        # Обновляем таблицу секций в главном окне
        self.update_data_table_sections()

    def set_structural_lines(self, members_data: List[Dict[str, Any]]):
        """
        Displays structural members (lattice).
        members_data: list of dicts with 'points' (start, end), 'type' (leg, brace...), 'color'.
        """
        # Clear old items (we reuse section_items or create new list?)
        # Let's create a new list for structural members to avoid conflict with sections
        if not hasattr(self, 'structural_items'):
            self.structural_items = []
            
        for item in self.structural_items:
            self.glview.removeItem(item)
        self.structural_items.clear()
        
        if not members_data:
            return
            
        # Batch lines by color/type for performance? 
        # GLLinePlotItem supports mode='lines' for disjoint segments.
        # Group by color
        from collections import defaultdict
        grouped = defaultdict(list)
        
        for m in members_data:
            pts = m['points'] # [p1, p2]
            color = tuple(m['color'])
            grouped[color].append(pts)
            
        for color, segments in grouped.items():
            # Flatten points: [p1a, p1b, p2a, p2b, ...]
            all_points = np.array(segments).reshape(-1, 3)
            
            item = gl.GLLinePlotItem(
                pos=all_points,
                color=color,
                width=1.5,
                mode='lines',
                antialias=True
            )
            self.glview.addItem(item)
            self.structural_items.append(item)

    
    def create_sections_wrapper(self):
        """Обертка для вызова метода создания секций из главного окна"""
        # Получаем ссылку на главное окно через parent
        main_window = self.parent()
        while main_window and not hasattr(main_window, 'create_sections'):
            main_window = main_window.parent()
        
        if main_window and hasattr(main_window, 'create_sections'):
            main_window.create_sections()
        else:
            QMessageBox.warning(self, 'Предупреждение', 
                              'Не удалось найти главное окно приложения')
    
    def remove_sections_wrapper(self):
        """Обертка для вызова метода удаления секций из главного окна"""
        # Получаем ссылку на главное окно через parent
        main_window = self.parent()
        while main_window and not hasattr(main_window, 'remove_sections'):
            main_window = main_window.parent()
        
        if main_window and hasattr(main_window, 'remove_sections'):
            main_window.remove_sections()
        else:
            QMessageBox.warning(self, 'Предупреждение', 
                              'Не удалось найти главное окно приложения')
    
    def build_central_axis(self):
        """Построить вертикальную линию через центры секций"""
        if not self.section_data:
            QMessageBox.warning(self, 'Предупреждение', 
                              'Нет секций для построения центральной оси.\n'
                              'Сначала создайте секции.')
            return
        
        self.show_central_axis = True
        self.update_central_axis()
        # Кнопка уже должна быть активна (активируется при наличии секций)
        
        logger.info("Построена центральная ось через центры секций")
    
    def update_central_axis(self):
        """Обновить визуализацию центральной оси"""
        # Удаляем старую линию оси
        if self.central_axis_line is not None:
            self.glview.removeItem(self.central_axis_line)
            self.central_axis_line = None
        
        if not self.section_data or not self.show_central_axis:
            return
        
        # Вычисляем центры всех секций
        section_centers = []
        for section in self.section_data:
            points = section['points']
            if len(points) == 0:
                continue
            
            # Вычисляем центр секции как среднее по X и Y координатам
            center_x = np.mean([p[0] for p in points])
            center_y = np.mean([p[1] for p in points])
            # Высота - среднее по Z координатам всех точек секции
            center_z = np.mean([p[2] for p in points])
            
            section_centers.append((center_x, center_y, center_z))
        
        if len(section_centers) < 2:
            logger.warning("Недостаточно секций для построения центральной оси (нужно минимум 2)")
            return
        
        # Сортируем центры по высоте (Z)
        section_centers.sort(key=lambda p: p[2])
        
        # Если есть только 2 точки, строим прямую линию
        # Если больше - используем средний центр по X и Y для всех секций
        if len(section_centers) >= 2:
            # Вычисляем средний центр по X и Y (используем все точки)
            avg_center_x = np.mean([c[0] for c in section_centers])
            avg_center_y = np.mean([c[1] for c in section_centers])
            
            # Находим минимальную и максимальную высоты
            min_z = min([c[2] for c in section_centers])
            max_z = max([c[2] for c in section_centers])
            
            # Строим вертикальную линию от min_z до max_z через средний центр
            axis_points = np.array([
                [avg_center_x, avg_center_y, min_z],
                [avg_center_x, avg_center_y, max_z]
            ])
            
            # Создаем линию центральной оси
            self.central_axis_line = gl.GLLinePlotItem(
                pos=axis_points,
                color=(1.0, 0.0, 0.0, 0.9),  # Красный цвет, непрозрачный
                width=3,
                antialias=True
            )
            self.glview.addItem(self.central_axis_line)
            
            logger.info(f"Обновлена центральная ось: от ({avg_center_x:.3f}, {avg_center_y:.3f}, {min_z:.3f}) "
                       f"до ({avg_center_x:.3f}, {avg_center_y:.3f}, {max_z:.3f})")
    
    def update_data_table_sections(self):
        """Обновляет таблицу секций в главном окне"""
        main_window = self.parent()
        while main_window and not hasattr(main_window, 'data_table'):
            main_window = main_window.parent()
        
        if main_window and hasattr(main_window, 'data_table'):
            if hasattr(main_window.data_table, 'update_sections_table'):
                main_window.data_table.update_sections_table()
    
    def add_point_dialog(self):
        """Диалог добавления новой точки"""
        # Получаем список доступных поясов
        available_belts = self.get_available_belts()
        available_parts = self.get_available_parts()
        
        # Данные по умолчанию
        default_data = {
            'name': f'Точка {len(self.data)+1 if self.data is not None else 1}',
            'x': 0.0,
            'y': 0.0,
            'z': 0.0,
            'belt': None,
            'tower_part': available_parts[0] if available_parts else 1,
            'is_part_boundary': False
        }
        
        dialog = PointEditDialog(default_data, available_belts, available_parts, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_data = dialog.get_point_data()
            if new_data:
                self.add_point(new_data)
    
    def add_point(self, point_data: dict):
        """Добавить новую точку"""
        description = f"Добавить точку {point_data.get('name', '')}"
        try:
            with self.undo_transaction(description) as tx:
                self._ensure_point_indices()
                
                raw_index = point_data.get('point_index')
                try:
                    point_index = int(raw_index)
                except (TypeError, ValueError):
                    point_index = None
                
                if self.data is not None:
                    existing_indices = set(self.data['point_index'].astype(int))
                else:
                    existing_indices = set()
                
                if point_index is None or point_index in existing_indices:
                    point_index = self._get_next_point_index()
                else:
                    self.point_index_counter = max(self.point_index_counter, point_index)
                point_data['point_index'] = point_index
                try:
                    part_value = int(point_data.get('tower_part', 1) or 1)
                except (TypeError, ValueError):
                    part_value = 1
                if part_value <= 0:
                    part_value = 1
                point_data['tower_part'] = part_value
                boundary_flag = bool(point_data.get('is_part_boundary', False))
                point_data['is_part_boundary'] = boundary_flag
                memberships = {part_value}
                if boundary_flag:
                    memberships.add(part_value + 1)
                point_data['tower_part_memberships'] = json.dumps(sorted(memberships), ensure_ascii=False)
                
                if self.data is None:
                    self.data = pd.DataFrame([point_data])
                else:
                    self.data = pd.concat([self.data, pd.DataFrame([point_data])], ignore_index=True)
                self._ensure_point_indices()
                
                # Обновляем IndexManager после добавления точки
                self.index_manager.set_data(self.data)

                self.update_3d_view()
                self.update_info_label()
                self.point_added.emit(point_data)
                self.data_changed.emit()
                tx.commit()
        except Exception as e:
            logger.error(f"Ошибка при добавлении точки: {e}", exc_info=True)
            self.info_label.setText(f'❌ Ошибка: {str(e)}')
    
    def edit_selected_point(self):
        """Редактировать выбранную точку"""
        if not self.selected_indices or self.data is None:
            QMessageBox.warning(self, 'Предупреждение', 'Выберите точку для редактирования')
            return
        
        # Проверяем, что индекс действителен после возможного удаления точек
        if self.selected_indices[0] >= len(self.data):
            QMessageBox.warning(self, 'Предупреждение', 'Выбранная точка была удалена')
            self.selected_indices = []
            self.update_3d_view()
            self.update_info_label()
            return
        
        idx = self.selected_indices[0]
        point_data = self.data.iloc[idx].to_dict()
        
        available_belts = self.get_available_belts()
        available_parts = self.get_available_parts()
        
        dialog = PointEditDialog(point_data, available_belts, available_parts, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_data = dialog.get_point_data()
            if new_data:
                description = f"Изменить точку {point_data.get('name', idx)}"
                try:
                    with self.undo_transaction(description) as tx:
                        for key, value in new_data.items():
                            if key in ('tower_part', 'is_part_boundary'):
                                continue
                            self.data.at[idx, key] = value

                        part_value = new_data.get('tower_part', self.data.at[idx, 'tower_part'])
                        boundary_flag = new_data.get('is_part_boundary', 
                                                     self.data.at[idx, 'is_part_boundary'] 
                                                     if 'is_part_boundary' in self.data.columns 
                                                     else False)
                        self._apply_part_assignment(idx, part_value, boundary_flag)

                        self.update_3d_view()
                        self.point_modified.emit(idx, new_data)
                        self.data_changed.emit()
                        self.update_all_indices()
                        tx.commit()
                except Exception as e:
                    logger.error(f"Ошибка при редактировании точки: {e}", exc_info=True)
                    self.info_label.setText(f'❌ Ошибка: {str(e)}')
    
    def delete_selected_points(self):
        """
        Удалить выбранные точки.
        
        Использует point_index для сигналов вместо индексов DataFrame.
        Валидирует индексы перед удалением.
        """
        if not self._validate_selection():
            if not self.selected_indices:
                QMessageBox.warning(self, 'Предупреждение', 'Выберите точки для удаления')
            else:
                QMessageBox.warning(self, 'Предупреждение', 'Выбранные точки больше не существуют')
                self.selected_indices = []
                self.update_3d_view()
                self.update_info_label()
            return
        
        if self.data is None or self.data.empty:
            QMessageBox.warning(self, 'Предупреждение', 'Нет данных для удаления')
            return
        
        # Получаем point_index для всех удаляемых точек
        point_indices_to_delete = []
        dataframe_indices_to_delete = []
        
        for pos in self.selected_indices:
            point_index = self.index_manager.find_point_index_by_position(pos)
            dataframe_idx = self.index_manager.get_dataframe_index_by_position(pos)
            
            if dataframe_idx is not None:
                dataframe_indices_to_delete.append(dataframe_idx)
                if point_index is not None:
                    point_indices_to_delete.append(point_index)
                else:
                    # Fallback на индекс DataFrame, если point_index недоступен
                    point_indices_to_delete.append(dataframe_idx)
        
        if not dataframe_indices_to_delete:
            QMessageBox.warning(self, 'Предупреждение', 'Не удалось определить индексы точек для удаления')
            return
        
        reply = QMessageBox.question(
            self,
            'Подтверждение удаления',
            f'Удалить {len(self.selected_indices)} точек?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            description = f"Удалить {len(self.selected_indices)} точек"
            try:
                with self.undo_transaction(description) as tx:
                    # Удаляем точки по индексам DataFrame
                    self.data = self.data.drop(dataframe_indices_to_delete).reset_index(drop=True)
                    
                    # Обновляем IndexManager сразу после удаления
                    self.index_manager.set_data(self.data)

                    # Эмитируем сигналы с point_index
                    for point_idx in point_indices_to_delete:
                        self.point_deleted.emit(point_idx)

                    self.selected_indices = []
                    self.update_3d_view()
                    self.update_info_label()
                    self.data_changed.emit()
                    self.update_all_indices()
                    tx.commit()
            except (KeyError, IndexError) as e:
                error_msg = f"Ошибка доступа при удалении точек: {e}"
                logger.error(error_msg, exc_info=True)
                QMessageBox.critical(self, 'Ошибка', error_msg)
                self.info_label.setText(f'❌ {error_msg}')
            except Exception as e:
                error_msg = f"Ошибка при удалении точек: {e}"
                logger.error(error_msg, exc_info=True)
                QMessageBox.critical(self, 'Ошибка', error_msg)
                self.info_label.setText(f'❌ {error_msg}')
    
    def move_all_belt_points_to_line_dialog(self):
        """Начинает режим массового переноса всех точек пояса на выбранную линию
        
        Логика:
        1. Выбираем линию пояса (между двумя точками)
        2. Все точки этого пояса переносятся на эту линию (3D линию в пространстве)
        """
        logger.info("move_all_belt_points_to_line_dialog вызвана")
        if self.data is None or self.data.empty:
            self.info_label.setText('⚠ Нет данных')
            logger.warning("move_all_belt_points_to_line_dialog: нет данных")
            return
        
        available_belts = self.get_available_belts()
        
        if not available_belts:
            self.info_label.setText('⚠ Нет определенных поясов')
            logger.warning("move_all_belt_points_to_line_dialog: нет поясов")
            return
        
        # Включаем режим массового переноса
        self.belt_mass_move_mode = True
        
        # Показываем инструкцию
        self.info_label.setText('🔵 Выберите линию пояса (между двумя точками) для переноса всех точек пояса (ESC - отмена)')
        
        logger.info(f"Активирован режим массового переноса точек пояса на линию. belt_mass_move_mode={self.belt_mass_move_mode}")
    
    def move_all_belt_points_to_line(self, belt_num: int, point1_idx: int, point2_idx: int):
        """Переносит все точки пояса через точку стояния на выбранную 3D линию
        
        Новая логика:
        1. Находим точку стояния тахеометра
        2. Для каждой точки пояса строим линию от точки standing до переносимой точки
        3. Продлеваем эту линию до пересечения с указанным поясом
        4. Переносим точку на это пересечение
        5. Переносим только точки, удаленные от линии пояса больше чем на 0.2м
        
        Args:
            belt_num: номер пояса
            point1_idx: индекс первой точки линии
            point2_idx: индекс второй точки линии
        """
        description = f"Перенос пояса {belt_num} на выбранную линию"
        try:
            with self.undo_transaction(description) as tx:
                # Проверяем, что индексы действительны после возможного удаления точек
                if point1_idx >= len(self.data) or point2_idx >= len(self.data):
                    self.info_label.setText('⚠ Одна из точек линии была удалена')
                    return
                
                # Находим точку standing
                station_mask = self.data.get('is_station', pd.Series([False] * len(self.data))) == True
                station_points = self.data[station_mask]
                
                if len(station_points) == 0:
                    self.info_label.setText('⚠ Не найдена точка standing тахеометра')
                    return
                
                station_point = station_points.iloc[0]
                station_pos = np.array([station_point['x'], station_point['y'], station_point['z']])
                
                # Получаем точки, определяющие линию пояса
                p1 = self.data.loc[point1_idx]
                p2 = self.data.loc[point2_idx]
                
                # Вектор линии пояса в 3D
                belt_line_point = np.array([p1['x'], p1['y'], p1['z']])
                belt_line_dir = np.array([p2['x'] - p1['x'], p2['y'] - p1['y'], p2['z'] - p1['z']])
                belt_line_len = np.linalg.norm(belt_line_dir)
                
                if belt_line_len < 1e-6:
                    self.info_label.setText('⚠ Выбранные точки слишком близко')
                    return
                
                belt_line_dir = belt_line_dir / belt_line_len  # Нормализуем
                
                # Получаем все точки этого пояса
                belt_mask = self.data['belt'] == belt_num
                belt_points = self.data[belt_mask]
                
                if len(belt_points) < 2:
                    self.info_label.setText(f'⚠ На поясе {belt_num} слишком мало точек')
                    return
                
                moved_count = 0
                total_distance = 0.0
                threshold = 0.2  # Порог расстояния для переноса
                
                # Для каждой точки пояса
                for idx in belt_points.index:
                    # Пропускаем точки, которые уже на линии (p1 и p2) и точку standing
                    if idx in [point1_idx, point2_idx] or self.data.loc[idx].get('is_station', False):
                        continue
                    
                    point = self.data.loc[idx]
                    point_pos = np.array([point['x'], point['y'], point['z']])
                    
                    # Проверяем расстояние от точки до линии пояса
                    to_point = point_pos - belt_line_point
                    t = np.dot(to_point, belt_line_dir)
                    closest_on_belt = belt_line_point + t * belt_line_dir
                    dist_to_belt = np.linalg.norm(point_pos - closest_on_belt)
                    
                    # Переносим только если расстояние больше порога
                    if dist_to_belt > threshold:
                        # Вектор от точки standing до переносимой точки
                        vec_station_to_point = point_pos - station_pos
                        vec_station_to_point_len = np.linalg.norm(vec_station_to_point)
                        
                        if vec_station_to_point_len < 1e-6:
                            continue
                        
                        vec_station_to_point_norm = vec_station_to_point / vec_station_to_point_len
                        
                        # Построим плоскость, перпендикулярную вектору station->point и проходящую через линию пояса
                        # Направляющий вектор плоскости - направление линии пояса
                        # Нормаль плоскости - перпендикулярно и вектору пояса, и vector station->point
                        plane_normal = np.cross(belt_line_dir, vec_station_to_point_norm)
                        plane_normal_len = np.linalg.norm(plane_normal)
                        
                        if plane_normal_len < 1e-6:
                            # Векторы коллинеарны, используем простую проекцию
                            projected = closest_on_belt
                        else:
                            plane_normal = plane_normal / plane_normal_len
                            
                            # Плоскость проходит через точку на линии пояса (belt_line_point)
                            # Уравнение плоскости: (p - belt_line_point) · plane_normal = 0
                            # Линия: station_pos + t * vec_station_to_point_norm
                            # Подставляем в уравнение: (station_pos + t*vec_norm - belt_line_point) · plane_normal = 0
                            # Раскрываем: (station_pos - belt_line_point) · plane_normal + t * (vec_norm · plane_normal) = 0
                            # t = -((station_pos - belt_line_point) · plane_normal) / (vec_norm · plane_normal)
                            
                            to_belt_line = station_pos - belt_line_point
                            dot_plane = np.dot(to_belt_line, plane_normal)
                            dot_dir = np.dot(vec_station_to_point_norm, plane_normal)
                            
                            if abs(dot_dir) < 1e-6:
                                # Линия параллельна плоскости, используем простую проекцию
                                projected = closest_on_belt
                            else:
                                t_intersection = -dot_plane / dot_dir
                                intersection_point = station_pos + t_intersection * vec_station_to_point_norm
                                
                                # Получили высоту из пересечения с плоскостью
                                # Теперь проектируем эту точку на линию пояса (находим X и Y на линии пояса)
                                # Ближайшая точка на линии пояса с этой высотой
                                # Решаем: find t such that (belt_line_point + t * belt_line_dir).z = intersection_point.z
                                if abs(belt_line_dir[2]) > 1e-6:
                                    t_on_belt = (intersection_point[2] - belt_line_point[2]) / belt_line_dir[2]
                                    projected = belt_line_point + t_on_belt * belt_line_dir
                                else:
                                    # Линия пояса горизонтальна, используем простое проектирование
                                    projected = closest_on_belt
                        
                        # Расстояние перемещения
                        distance = np.linalg.norm(projected - point_pos)
                        
                        # Обновляем координаты
                        self.data.at[idx, 'x'] = projected[0]
                        self.data.at[idx, 'y'] = projected[1]
                        self.data.at[idx, 'z'] = projected[2]
                        
                        moved_count += 1
                        total_distance += distance
                
                # Обновляем визуализацию
                self.update_3d_view()
                
                # Сигнализируем об изменении
                self.data_changed.emit()
                self.update_all_indices()
                
                # Показываем статистику
                avg_distance = total_distance / moved_count if moved_count > 0 else 0
                p1_name = p1['name'] if 'name' in self.data.columns else f'Точка {point1_idx}'
                p2_name = p2['name'] if 'name' in self.data.columns else f'Точка {point2_idx}'
                
                self.info_label.setText(
                    f'✓ Пояс {belt_num} выровнен по линии {p1_name}-{p2_name}: '
                    f'{moved_count} точек, средняя Δ={avg_distance:.3f}м'
                )
                
                if moved_count == 0:
                    self.info_label.setText('⚠ Нет точек для переноса')
                    return
                
                logger.info(f"Перенесено {moved_count} точек пояса {belt_num} на линию между точками {point1_idx} и {point2_idx}")
                tx.commit()
        except Exception as e:
            logger.error(f"Ошибка при массовом переносе точек пояса: {e}", exc_info=True)
            self.info_label.setText(f'❌ Ошибка: {str(e)}')
        finally:
            # Выключаем режим
            self.belt_mass_move_mode = False
            self.pending_belt_num = None
    
    def get_available_belts(self) -> List[int]:
        """Получить список доступных поясов (без точек standing)"""
        if self.data is None or 'belt' not in self.data.columns:
            return []
        
        # Исключаем точки standing
        data_without_station = self.data.copy()
        if 'is_station' in self.data.columns:
            mask = self._build_is_station_mask(data_without_station['is_station'])
            data_without_station['is_station'] = mask
            data_without_station = data_without_station[~mask]
        
        belts = data_without_station['belt'].dropna().unique()
        return sorted([int(b) for b in belts if b is not None])

    def get_available_parts(self) -> List[int]:
        """Возвращает список частей башни, доступных для назначения точкам."""
        if self.data is None or 'tower_part' not in self.data.columns:
            return [1]
        try:
            part_series = pd.to_numeric(self.data['tower_part'], errors='coerce')
        except Exception:
            return [1]
        parts = sorted({int(value) for value in part_series.dropna().unique().tolist() if int(value) > 0})
        return parts or [1]
    
    def project_to_belt_line_dialog(self):
        """Начинает интерактивный режим выбора линии пояса"""
        logger.info("project_to_belt_line_dialog вызвана")
        if not self.selected_indices or self.data is None:
            self.info_label.setText('⚠ Выберите точку для переноса на линию пояса')
            logger.warning("project_to_belt_line_dialog: нет выбранных точек или данных")
            return
        
        if len(self.selected_indices) > 1:
            self.info_label.setText('⚠ Выберите только одну точку для переноса')
            logger.warning(f"project_to_belt_line_dialog: выбрано {len(self.selected_indices)} точек, требуется 1")
            return
        
        available_belts = self.get_available_belts()
        
        if not available_belts:
            self.info_label.setText('⚠ Нет определенных поясов. Сначала назначьте пояса точкам.')
            logger.warning("project_to_belt_line_dialog: нет поясов")
            return
        
        # Включаем режим выбора линии пояса
        self.belt_selection_mode = True
        
        # Проверяем, что индекс действителен после возможного удаления точек
        if self.selected_indices[0] >= len(self.data):
            self.info_label.setText('⚠ Выбранная точка была удалена')
            self.selected_indices = []
            self.update_3d_view()
            self.update_info_label()
            logger.warning(f"project_to_belt_line_dialog: индекс {self.selected_indices[0]} вне диапазона")
            return
        
        self.pending_point_idx = self.selected_indices[0]
        
        # Показываем инструкцию в информационной строке
        point_name = self.data.at[self.pending_point_idx, 'name'] if 'name' in self.data.columns else f'Точка {self.pending_point_idx}'
        self.info_label.setText(f'🔵 Выберите линию между точками пояса для переноса "{point_name}" (ESC - отмена)')
        
        logger.info(f"Активирован режим выбора линии пояса для точки {self.pending_point_idx}. belt_selection_mode={self.belt_selection_mode}")
    
    def project_point_to_selected_belt_line(self, belt_num: int, point1_idx: int, point2_idx: int):
        """Проецирует точку через точку standing на линию между двумя точками пояса
        
        Новая логика:
        1. Находим точку стояния тахеометра
        2. Строим линию от точки standing до переносимой точки
        3. Продлеваем эту линию до пересечения с указанной линией пояса
        4. Переносим точку на это пересечение
        5. Проверяем расстояние от точки до линии пояса (порог 0.2м)
        """
        if self.pending_point_idx is None:
            return
        
        # Проверяем, что индекс действителен после возможного удаления точек
        if self.pending_point_idx >= len(self.data):
            self.info_label.setText('⚠ Точка была удалена')
            self.pending_point_idx = None
            self.belt_selection_mode = False
            return
        
        try:
            idx = self.pending_point_idx
            
            # Находим точку standing
            station_mask = self.data.get('is_station', pd.Series([False] * len(self.data))) == True
            station_points = self.data[station_mask]
            
            if len(station_points) == 0:
                self.info_label.setText('⚠ Не найдена точка standing тахеометра')
                return
            
            station_point = station_points.iloc[0]
            station_pos = np.array([station_point['x'], station_point['y'], station_point['z']])
            
            # Координаты двух точек линии в 3D
            p1 = self.data.iloc[point1_idx]
            p2 = self.data.iloc[point2_idx]
            
            # Точка для переноса
            point = self.data.iloc[idx]
            
            # Точки в 3D пространстве
            line_start = np.array([p1['x'], p1['y'], p1['z']])
            line_end = np.array([p2['x'], p2['y'], p2['z']])
            point_pos = np.array([point['x'], point['y'], point['z']])
            
            # Проверяем расстояние от точки до линии пояса
            belt_line_vec = line_end - line_start
            belt_line_len = np.linalg.norm(belt_line_vec)
            
            if belt_line_len < 1e-6:
                self.info_label.setText('⚠ Выбранные точки слишком близко друг к другу')
                return
            
            belt_line_dir = belt_line_vec / belt_line_len
            to_point = point_pos - line_start
            t = np.dot(to_point, belt_line_dir)
            closest_on_belt = line_start + t * belt_line_dir
            dist_to_belt = np.linalg.norm(point_pos - closest_on_belt)
            
            # Переносим только если расстояние больше порога
            threshold = 0.2
            if dist_to_belt <= threshold:
                self.info_label.setText(f'⚠ Точка уже на линии пояса (расстояние {dist_to_belt:.3f}м ≤ {threshold}м)')
                return
            
            # Вектор от точки standing до переносимой точки
            vec_station_to_point = point_pos - station_pos
            vec_station_to_point_len = np.linalg.norm(vec_station_to_point)
            
            if vec_station_to_point_len < 1e-6:
                self.info_label.setText('⚠ Точка совпадает с точкой standing')
                return
            
            vec_station_to_point_norm = vec_station_to_point / vec_station_to_point_len
            
            # Построим плоскость, перпендикулярную вектору station->point и проходящую через линию пояса
            # Направляющий вектор плоскости - направление линии пояса
            # Нормаль плоскости - перпендикулярно и вектору пояса, и vector station->point
            plane_normal = np.cross(belt_line_dir, vec_station_to_point_norm)
            plane_normal_len = np.linalg.norm(plane_normal)
            
            if plane_normal_len < 1e-6:
                # Векторы коллинеарны, используем простую проекцию
                projected = closest_on_belt
            else:
                plane_normal = plane_normal / plane_normal_len
                
                # Плоскость проходит через точку на линии пояса (line_start)
                # Уравнение плоскости: (p - line_start) · plane_normal = 0
                # Линия: station_pos + t * vec_station_to_point_norm
                # Подставляем в уравнение: (station_pos + t*vec_norm - line_start) · plane_normal = 0
                # Раскрываем: (station_pos - line_start) · plane_normal + t * (vec_norm · plane_normal) = 0
                # t = -((station_pos - line_start) · plane_normal) / (vec_norm · plane_normal)
                
                to_belt_line = station_pos - line_start
                dot_plane = np.dot(to_belt_line, plane_normal)
                dot_dir = np.dot(vec_station_to_point_norm, plane_normal)
                
                if abs(dot_dir) < 1e-6:
                    # Линия параллельна плоскости, используем простую проекцию
                    projected = closest_on_belt
                else:
                    t_intersection = -dot_plane / dot_dir
                    intersection_point = station_pos + t_intersection * vec_station_to_point_norm
                    
                    # Получили высоту из пересечения с плоскостью
                    # Теперь проектируем эту точку на линию пояса (находим X и Y на линии пояса)
                    # Ближайшая точка на линии пояса с этой высотой
                    # Решаем: find t such that (line_start + t * belt_line_dir).z = intersection_point.z
                    if abs(belt_line_dir[2]) > 1e-6:
                        t_on_belt = (intersection_point[2] - line_start[2]) / belt_line_dir[2]
                        projected = line_start + t_on_belt * belt_line_dir
                    else:
                        # Линия пояса горизонтальна, используем простое проектирование
                        projected = closest_on_belt
            
            # Итоговые координаты: точка лежит на линии пояса с высотой из пересечения
            new_x = projected[0]
            new_y = projected[1]
            new_z = projected[2]
            
            # Расстояние перемещения в 3D
            distance = np.linalg.norm(projected - point_pos)
            
            # Обновляем координаты точки
            self.data.at[idx, 'x'] = new_x
            self.data.at[idx, 'y'] = new_y
            self.data.at[idx, 'z'] = new_z
            
            # Обновляем визуализацию
            self.update_3d_view()
            
            # Сигнализируем об изменении
            self.point_modified.emit(idx, {'x': new_x, 'y': new_y, 'z': new_z})
            self.data_changed.emit()
            self.update_all_indices()
            
            # Показываем информацию в строке состояния
            point_name = self.data.at[idx, 'name'] if 'name' in self.data.columns else f'Точка {idx}'
            p1_name = p1['name'] if 'name' in self.data.columns else f'Точка {point1_idx}'
            p2_name = p2['name'] if 'name' in self.data.columns else f'Точка {point2_idx}'
            
            self.info_label.setText(
                f'✓ "{point_name}" → линия {p1_name}-{p2_name} (пояс {belt_num}), '
                f'Δ={distance:.3f}м, новые координаты: Z={new_z:.3f}м'
            )
            
            logger.info(f"Точка {idx} ({point_name}) перенесена на 3D линию {p1_name}-{p2_name} пояса {belt_num}, "
                      f"перемещение: {distance:.3f}м, новые координаты: ({new_x:.3f}, {new_y:.3f}, {new_z:.3f})")
            
        except Exception as e:
            logger.error(f"Ошибка при переносе точки: {e}", exc_info=True)
            self.info_label.setText(f'❌ Ошибка при переносе точки: {str(e)}')
        finally:
            # Выключаем режим выбора
            self.belt_selection_mode = False
            self.pending_point_idx = None
    
    def cancel_belt_selection(self):
        """Отменяет режим выбора линии пояса"""
        if self.belt_selection_mode:
            self.belt_selection_mode = False
            self.pending_point_idx = None
            logger.info("Режим выбора линии пояса отменен")
    
    def project_to_section_level_dialog(self):
        """Начинает интерактивный режим выбора уровня секции"""
        if not self.selected_indices or self.data is None:
            self.info_label.setText('⚠ Выберите точку для переноса на уровень секции')
            return
        
        if len(self.selected_indices) > 1:
            self.info_label.setText('⚠ Выберите только одну точку для переноса')
            return
        
        if not self.section_data:
            self.info_label.setText('⚠ Нет секций. Сначала создайте секции.')
            return
        
        # Проверяем, что индекс действителен после возможного удаления точек
        if self.selected_indices[0] >= len(self.data):
            self.info_label.setText('⚠ Выбранная точка была удалена')
            self.selected_indices = []
            self.update_3d_view()
            self.update_info_label()
            return
        
        # Проверяем, что точка принадлежит поясу
        idx = self.selected_indices[0]
        if 'belt' not in self.data.columns or pd.isna(self.data.at[idx, 'belt']):
            self.info_label.setText('⚠ Точка должна принадлежать поясу')
            return
        
        # Включаем режим выбора уровня секции
        self.section_selection_mode = True
        self.pending_point_idx = self.selected_indices[0]
        
        # Показываем инструкцию в информационной строке
        point_name = self.data.at[self.pending_point_idx, 'name'] if 'name' in self.data.columns else f'Точка {self.pending_point_idx}'
        self.info_label.setText(f'🔵 Выберите уровень секции (зеленую линию) для переноса "{point_name}" (ESC - отмена)')
        
        logger.info(f"Активирован режим выбора уровня секции для точки {self.pending_point_idx}")
    
    def project_point_to_section_level(self, section_height: float):
        """Переносит точку на уровень секции вдоль вектора пояса
        
        Логика:
        1. Определяем пояс точки
        2. Находим две соседние точки на поясе (выше и ниже целевой высоты)
        3. Интерполируем/экстраполируем положение точки на новой высоте вдоль вектора пояса
        """
        if self.pending_point_idx is None:
            return
        
        # Проверяем, что индекс действителен после возможного удаления точек
        if self.pending_point_idx >= len(self.data):
            self.info_label.setText('⚠ Точка была удалена')
            self.pending_point_idx = None
            self.section_selection_mode = False
            return
        
        # Определяем допуск по высоте для секций
        height_tolerance = 0.3
        
        try:
            idx = self.pending_point_idx
            point = self.data.iloc[idx]
            belt_num = int(point['belt'])
            
            logger.debug(f"Перенос точки {idx} на секцию Z={section_height:.3f}м, пояс {belt_num}")
            logger.debug(f"Исходная позиция точки: ({point['x']:.3f}, {point['y']:.3f}, {point['z']:.3f})")
            
            # Получаем все точки пояса
            belt_mask = self.data['belt'] == belt_num
            belt_points = self.data[belt_mask].copy()
            
            logger.debug(f"Точек на поясе {belt_num}: {len(belt_points)}")
            
            if len(belt_points) < 2:
                self.info_label.setText(f'⚠ На поясе {belt_num} недостаточно точек')
                return
            
            # Сортируем точки пояса по высоте
            belt_points_sorted = belt_points.sort_values('z')
            
            # Находим точки выше и ниже целевой высоты
            points_below = belt_points_sorted[belt_points_sorted['z'] < section_height]
            points_above = belt_points_sorted[belt_points_sorted['z'] > section_height]
            
            if points_below.empty or points_above.empty:
                # Экстраполяция
                if points_below.empty:
                    # Берем две самые нижние точки
                    if len(belt_points_sorted) < 2:
                        self.info_label.setText('⚠ Недостаточно точек для экстраполяции')
                        return
                    p1 = belt_points_sorted.iloc[0]
                    p2 = belt_points_sorted.iloc[1]
                else:
                    # Берем две самые верхние точки
                    if len(belt_points_sorted) < 2:
                        self.info_label.setText('⚠ Недостаточно точек для экстраполяции')
                        return
                    p1 = belt_points_sorted.iloc[-2]
                    p2 = belt_points_sorted.iloc[-1]
            else:
                # Интерполяция между ближайшими точками
                p1 = points_below.iloc[-1]  # Ближайшая снизу
                p2 = points_above.iloc[0]   # Ближайшая сверху
            
            # Линейная интерполяция/экстраполяция вдоль вектора пояса
            if abs(p2['z'] - p1['z']) < 1e-6:
                # Точки на одной высоте - берем среднее
                new_x = (p1['x'] + p2['x']) / 2
                new_y = (p1['y'] + p2['y']) / 2
            else:
                t = (section_height - p1['z']) / (p2['z'] - p1['z'])
                new_x = p1['x'] + t * (p2['x'] - p1['x'])
                new_y = p1['y'] + t * (p2['y'] - p1['y'])
            
            new_z = section_height
            
            # Расстояние перемещения
            old_pos = np.array([point['x'], point['y'], point['z']])
            new_pos = np.array([new_x, new_y, new_z])
            distance = np.linalg.norm(new_pos - old_pos)
            
            # Проверяем, является ли точка основной
            point_name = self.data.at[idx, 'name'] if 'name' in self.data.columns else f'Точка {idx}'
            is_original_point = not point_name.startswith('S') or '_B' not in point_name
            
            # Если переносим основную точку, проверяем наличие автоматически добавленной точки на целевой секции
            if is_original_point:
                logger.debug(f"Точка '{point_name}' является основной, проверяем конфликты на целевой секции")
                
                # Находим точки на целевой секции
                target_section_mask = np.abs(self.data['z'] - section_height) < height_tolerance
                target_section_points = self.data[target_section_mask]
                
                logger.debug(f"Точек на целевой секции: {len(target_section_points)}")
                
                # Ищем автоматически добавленную точку на этом поясе и секции
                auto_point_mask = (
                    target_section_points['belt'] == belt_num
                ) & target_section_points['name'].str.match(r'^S\d+_B\d+$', na=False)
                
                auto_points_to_remove = target_section_points[auto_point_mask]
                
                if len(auto_points_to_remove) > 0:
                    logger.info(f"Найдена автоматически добавленная точка на целевой секции: {auto_points_to_remove['name'].values}")
                    
                    # Удаляем автоматически добавленную точку
                    indices_to_delete = auto_points_to_remove.index.tolist()
                    self.data = self.data.drop(indices_to_delete).reset_index(drop=True)
                    
                    # Корректируем idx после удаления, если нужно
                    deleted_before_idx = sum(1 for i in indices_to_delete if i < idx)
                    idx = idx - deleted_before_idx
                    
                    logger.info(f"Удалена точка {auto_points_to_remove['name'].values}, индекс скорректирован: {idx}")
            
            # Обновляем координаты точки
            self.data.at[idx, 'x'] = new_x
            self.data.at[idx, 'y'] = new_y
            self.data.at[idx, 'z'] = new_z
            
            # Обновляем визуализацию
            self.update_3d_view()
            
            # Сигнализируем об изменении
            self.point_modified.emit(idx, {'x': new_x, 'y': new_y, 'z': new_z})
            self.data_changed.emit()
            self.update_all_indices()
            
            # Показываем информацию
            point_name = self.data.at[idx, 'name'] if 'name' in self.data.columns else f'Точка {idx}'
            
            # Проверяем, является ли перенесенная точка основной (не добавленной автоматически)
            is_original_point = not point_name.startswith('S') or '_B' not in point_name
            
            if is_original_point and abs(point['z'] - new_z) > height_tolerance:
                # Точка переместилась с одной секции на другую
                old_section_height = point['z']
                
                # Проверяем, остались ли на старой секции основные точки
                old_section_mask = np.abs(self.data['z'] - old_section_height) < height_tolerance
                old_section_points = self.data[old_section_mask]
                
                # Фильтруем только основные точки (не добавленные автоматически)
                original_points_mask = ~old_section_points['name'].str.match(r'^S\d+_B\d+$', na=False)
                original_points_on_old_section = old_section_points[original_points_mask]
                
                if len(original_points_on_old_section) == 0:
                    # Нет основных точек на старой секции - удаляем её
                    logger.info(f"На секции Z={old_section_height:.3f}м не осталось основных точек, удаляем секцию")
                    
                    # Удаляем все автоматически добавленные точки на этой секции
                    auto_added_mask = old_section_points['name'].str.match(r'^S\d+_B\d+$', na=False)
                    points_to_delete = old_section_points[auto_added_mask]
                    
                    if len(points_to_delete) > 0:
                        indices_to_delete = points_to_delete.index.tolist()
                        self.data = self.data.drop(indices_to_delete).reset_index(drop=True)
                        
                        # Удаляем секцию из section_data
                        self.section_data = [s for s in self.section_data 
                                           if abs(s['height'] - old_section_height) > height_tolerance]
                        
                        # Обновляем визуализацию
                        self.update_3d_view()
                        self.update_section_lines()
                        
                        # Обновляем центральную ось, если она отображается
                        if self.show_central_axis:
                            self.update_central_axis()
                        
                        logger.info(f"Удалена пустая секция Z={old_section_height:.3f}м, удалено {len(points_to_delete)} точек")
            
            self.info_label.setText(
                f'✓ "{point_name}" перенесена на уровень секции Z={new_z:.3f}м (пояс {belt_num}), '
                f'Δ={distance:.3f}м'
            )
            
            logger.info(f"Точка {idx} ({point_name}) перенесена на уровень секции {new_z:.3f}м, "
                      f"пояс {belt_num}, перемещение: {distance:.3f}м")
            
        except Exception as e:
            logger.error(f"Ошибка при переносе точки на уровень секции: {e}", exc_info=True)
            self.info_label.setText(f'❌ Ошибка: {str(e)}')
        finally:
            # Выключаем режим выбора
            self.section_selection_mode = False
            self.pending_point_idx = None
    
    def align_section_dialog(self):
        """Начинает интерактивный режим выравнивания секции"""
        # Включаем режим выравнивания секции
        self.section_alignment_mode = True
        
        # Показываем инструкцию в информационной строке
        if self.section_data:
            self.info_label.setText('🔵 Выберите уровень секции (зеленую линию) или точку для выравнивания всех точек (ESC - отмена)')
        else:
            self.info_label.setText('🔵 Выберите точку (не точку стояния) для переноса всех точек на эту высоту (ESC - отмена)')
        
        logger.info("Активирован режим выравнивания секции")
    
    def align_section(self, section_height: float):
        """Автоматически переносит все точки секции на одну высоту
        
        Логика:
        1. Находим все точки на данной высоте секции (в пределах tolerance)
        2. Для каждого пояса вычисляем среднюю линию между точками этого пояса на уровне секции
        3. Переносим все точки пояса на эту высоту вдоль векторов пояса
        """
        # Находим все точки, принадлежащие этой секции
        height_tolerance = 0.3

        data_without_station = self.data.copy()
        if 'is_station' in self.data.columns:
            mask = self._build_is_station_mask(data_without_station['is_station'])
            data_without_station['is_station'] = mask
            data_without_station = data_without_station[~mask]

        section_mask = np.abs(data_without_station['z'] - section_height) < height_tolerance
        section_points = data_without_station[section_mask]

        if len(section_points) == 0:
            self.info_label.setText('⚠ Нет точек на выбранной высоте')
            self.section_alignment_mode = False
            self.pending_point_idx = None
            return

        belts = section_points['belt'].dropna().unique()
        # Если поясов нет, переносим все точки на выбранную высоту по вертикали
        if len(belts) == 0:
            # Переносим все точки (кроме точки стояния) на выбранную высоту по вертикали
            description = f'Перенести все точки на высоту Z={section_height:.2f}м'
            try:
                with self.undo_transaction(description) as tx:
                    moved_count = 0
                    total_distance = 0.0
                    
                    # Получаем все точки для переноса (кроме точки стояния)
                    for idx in data_without_station.index:
                        point = self.data.loc[idx]
                        old_z = point['z']
                        
                        if abs(old_z - section_height) < 1e-6:
                            continue  # Точка уже на нужной высоте
                        
                        # Переносим только по Z (вертикально)
                        distance = abs(old_z - section_height)
                        
                        self.data.at[idx, 'z'] = section_height
                        
                        moved_count += 1
                        total_distance += distance
                    
                    if moved_count == 0:
                        self.info_label.setText('⚠ Не удалось перенести точки — все уже на выбранной высоте.')
                        return
                    
                    # Обновляем IndexManager после изменения данных
                    self.index_manager.set_data(self.data)
                    
                    self.update_3d_view()
                    if self.show_central_axis:
                        self.update_central_axis()
                    
                    self.data_changed.emit()
                    self.update_all_indices()
                    
                    avg_distance = total_distance / moved_count if moved_count > 0 else 0
                    self.info_label.setText(
                        f'✓ Точки перенесены! Перемещено точек: {moved_count}, '
                        f'средняя Δ={avg_distance:.3f}м на Z={section_height:.3f}м'
                    )
                    
                    logger.info(
                        f"Перенесены точки на высоту {section_height:.3f}м: "
                        f"{moved_count} точек, средняя Δ={avg_distance:.3f}м"
                    )
                    
                    tx.commit()
            except Exception as e:
                logger.error(f"Ошибка при переносе точек на высоту: {e}", exc_info=True)
                self.info_label.setText(f'❌ Ошибка: {str(e)}')
            finally:
                self.section_alignment_mode = False
                self.pending_point_idx = None
            return

        description = f'Выровнять секцию Z={section_height:.2f}м'
        try:
            with self.undo_transaction(description) as tx:
                moved_count = 0
                total_distance = 0.0

                for belt_num in belts:
                    belt_num = int(belt_num)
                    belt_mask = data_without_station['belt'] == belt_num
                    belt_points = data_without_station[belt_mask].copy()

                    if len(belt_points) < 2:
                        continue

                    belt_points_sorted = belt_points.sort_values('z')

                    for idx in section_points[section_points['belt'] == belt_num].index:
                        point = self.data.loc[idx]

                        points_below = belt_points_sorted[belt_points_sorted['z'] < section_height]
                        points_above = belt_points_sorted[belt_points_sorted['z'] > section_height]

                        if points_below.empty or points_above.empty:
                            if len(belt_points_sorted) < 2:
                                continue
                            if points_below.empty:
                                p1 = belt_points_sorted.iloc[0]
                                p2 = belt_points_sorted.iloc[1]
                            else:
                                p1 = belt_points_sorted.iloc[-2]
                                p2 = belt_points_sorted.iloc[-1]
                        else:
                            p1 = points_below.iloc[-1]
                            p2 = points_above.iloc[0]

                        if abs(p2['z'] - p1['z']) < 1e-6:
                            new_x = (p1['x'] + p2['x']) / 2
                            new_y = (p1['y'] + p2['y']) / 2
                        else:
                            t = (section_height - p1['z']) / (p2['z'] - p1['z'])
                            new_x = p1['x'] + t * (p2['x'] - p1['x'])
                            new_y = p1['y'] + t * (p2['y'] - p1['y'])

                        new_z = section_height

                        old_pos = np.array([point['x'], point['y'], point['z']])
                        new_pos = np.array([new_x, new_y, new_z])
                        distance = np.linalg.norm(new_pos - old_pos)

                        self.data.at[idx, 'x'] = new_x
                        self.data.at[idx, 'y'] = new_y
                        self.data.at[idx, 'z'] = new_z

                        moved_count += 1
                        total_distance += distance

                if moved_count == 0:
                    self.info_label.setText('⚠ Не удалось выровнять секцию — точки не найдены.')
                    return

                self.update_3d_view()
                if self.show_central_axis:
                    self.update_central_axis()

                self.data_changed.emit()
                self.update_all_indices()

                avg_distance = total_distance / moved_count if moved_count > 0 else 0
                self.info_label.setText(
                    f'✓ Секция выровнена! Перенесено точек: {moved_count}, '
                    f'средняя Δ={avg_distance:.3f}м на Z={section_height:.3f}м'
                )

                logger.info(
                    f"Выровнена секция на высоте {section_height:.3f}м: "
                    f"{moved_count} точек, средняя Δ={avg_distance:.3f}м"
                )

                tx.commit()
        except Exception as e:
            logger.error(f"Ошибка при выравнивании секции: {e}", exc_info=True)
            self.info_label.setText(f'❌ Ошибка: {str(e)}')
        finally:
            self.section_alignment_mode = False
            self.pending_point_idx = None
    
    def delete_section_dialog(self):
        """Начинает интерактивный режим удаления конкретной секции"""
        if not self.section_data:
            self.info_label.setText('⚠ Нет секций. Сначала создайте секции.')
            return
        
        # Включаем режим удаления секции
        self.section_deletion_mode = True
        
        # Показываем инструкцию в информационной строке
        self.info_label.setText('🔵 Выберите уровень секции (зеленую линию) для удаления (ESC - отмена)')
        
        logger.info("Активирован режим удаления секции")
    
    def delete_section(self, section_height: float):
        """Удаляет конкретную секцию и ВСЕ точки на ней (включая основные)
        
        Логика:
        1. Находим все точки на этой высоте секции
        2. Удаляем ВСЕ точки на этой секции (и основные, и добавленные)
        3. Удаляем линию секции из визуализации
        4. Обновляем данные
        """
        try:
            # Находим все точки на этой высоте секции
            height_tolerance = 0.3
            section_mask = np.abs(self.data['z'] - section_height) < height_tolerance
            section_points = self.data[section_mask]
            
            if len(section_points) == 0:
                self.info_label.setText('⚠ Нет точек на выбранной секции')
                return
            
            logger.info(f"Найдено {len(section_points)} точек на секции {section_height:.3f}м")
            
            # Удаляем ВСЕ точки на этой секции
            indices_to_delete = section_points.index.tolist()
            
            # Подсчитываем основные и добавленные точки
            auto_added_mask = section_points['name'].str.match(r'^S\d+_B\d+$', na=False)
            auto_points_count = auto_added_mask.sum()
            original_points_count = len(section_points) - auto_points_count
            
            # Удаляем точки из DataFrame
            self.data = self.data.drop(indices_to_delete).reset_index(drop=True)
            
            # Обновляем IndexManager после удаления точек
            self.index_manager.set_data(self.data)
            
            # Удаляем эту секцию из section_data
            self.section_data = [s for s in self.section_data if abs(s['height'] - section_height) > height_tolerance]
            
            # Обновляем визуализацию
            self.update_3d_view()
            self.update_section_lines()
            
            # Обновляем состояние кнопок
            has_sections = bool(len(self.section_data) > 0)
            if hasattr(self, 'build_central_axis_btn'):
                self.build_central_axis_btn.setEnabled(has_sections)
            
            # Обновляем центральную ось, если она отображается
            if self.show_central_axis:
                self.update_central_axis()
            
            # Сигнализируем об изменении
            self.data_changed.emit()
            
            # Показываем информацию
            self.info_label.setText(
                f'✓ Секция удалена! Z={section_height:.3f}м, удалено: {len(section_points)} точек ({original_points_count} основных, {auto_points_count} добавленных)'
            )
            
            logger.info(f"Удалена секция на высоте {section_height:.3f}м: {len(section_points)} точек")
            
        except Exception as e:
            logger.error(f"Ошибка при удалении секции: {e}", exc_info=True)
            self.info_label.setText(f'❌ Ошибка: {str(e)}')
        finally:
            # Выключаем режим удаления
            self.section_deletion_mode = False
    
    def add_section_dialog(self):
        """Диалог добавления новой промежуточной секции с выбором части башни и абсолютной высоты"""
        if not self.section_data:
            self.info_label.setText('⚠ Нет секций. Сначала создайте секции.')
            return
        
        if self.data is None or self.data.empty:
            self.info_label.setText('⚠ Нет данных для добавления секции.')
            return
        
        # Находим минимальную и максимальную высоты секций
        section_heights = [s['height'] for s in self.section_data]
        min_section_height = min(section_heights)
        max_section_height = max(section_heights)
        
        logger.info(f"Минимальная высота секции: {min_section_height:.3f}м, максимальная: {max_section_height:.3f}м")
        
        # Получаем список доступных частей башни
        available_parts = self.get_available_parts()
        
        # Создаем диалоговое окно
        # (QDialog, QVBoxLayout, QLabel, QDoubleSpinBox, QPushButton, QHBoxLayout, QFormLayout, QComboBox уже импортированы)
        
        dialog = QDialog(self)
        dialog.setWindowTitle('Добавить промежуточную секцию')
        dialog.setModal(True)
        dialog.setMinimumWidth(400)
        
        layout = QVBoxLayout()
        layout.setSpacing(12)
        
        # Информация о текущих секциях
        info_text = f'Текущие секции:\nНижняя: {min_section_height:.2f}м\nВерхняя: {max_section_height:.2f}м'
        info_label = QLabel(info_text)
        info_label.setStyleSheet('color: #666; padding: 5px;')
        layout.addWidget(info_label)
        
        # Форма для ввода параметров
        form_layout = QFormLayout()
        form_layout.setSpacing(10)

        placement_combo = QComboBox()
        placement_combo.addItem('Сверху', 'top')
        placement_combo.addItem('Снизу', 'bottom')
        placement_combo.addItem('По абсолютной высоте', 'absolute')
        form_layout.addRow('Добавлять:', placement_combo)
        
        # Выбор части башни
        part_combo = QComboBox()
        for part_num in available_parts:
            part_combo.addItem(f'Часть {part_num}', part_num)
        if available_parts:
            part_combo.setCurrentIndex(0)
        form_layout.addRow('Часть башни:', part_combo)
        
        # Поле ввода абсолютной высоты
        height_spin = QDoubleSpinBox()
        height_spin.setMinimum(0.0)
        height_spin.setMaximum(1000.0)
        height_spin.setDecimals(3)
        height_spin.setSingleStep(0.1)
        height_spin.setSuffix(' м')
        form_layout.addRow('Абсолютная высота:', height_spin)
        
        # Метка для валидации
        validation_label = QLabel('')
        validation_label.setStyleSheet('color: #d32f2f; font-size: 9pt; padding: 2px;')
        validation_label.setWordWrap(True)
        form_layout.addRow('', validation_label)
        
        layout.addLayout(form_layout)
        
        layout.addStretch()
        
        # Кнопки (создаем до функции валидации, чтобы она могла к ним обращаться)
        button_layout = QHBoxLayout()
        ok_button = QPushButton('OK')
        cancel_button = QPushButton('Отмена')
        apply_compact_button_style(ok_button, width=120, min_height=34)
        apply_compact_button_style(cancel_button, width=120, min_height=34)
        button_layout.addStretch()
        button_layout.addWidget(ok_button)
        button_layout.addWidget(cancel_button)
        layout.addLayout(button_layout)
        
        dialog.setLayout(layout)

        def refresh_height_suggestion():
            suggested_height = self._suggest_new_section_height(
                section_heights,
                placement_combo.currentData(),
            )
            height_spin.blockSignals(True)
            height_spin.setValue(suggested_height)
            height_spin.blockSignals(False)
        
        # Функция валидации высоты (определяем после создания ok_button)
        def validate_height():
            is_valid, message = self._validate_new_section_height(
                self.section_data,
                float(height_spin.value()),
                placement=placement_combo.currentData(),
            )
            validation_label.setText(message)
            if is_valid:
                validation_label.setStyleSheet('color: #2e7d32; font-size: 9pt; padding: 2px;')
            else:
                validation_label.setStyleSheet('color: #d32f2f; font-size: 9pt; padding: 2px;')
            ok_button.setEnabled(is_valid)
            return is_valid
        
        # Подключаем валидацию
        refresh_height_suggestion()
        placement_combo.currentIndexChanged.connect(refresh_height_suggestion)
        placement_combo.currentIndexChanged.connect(lambda _: validate_height())
        height_spin.valueChanged.connect(validate_height)
        validate_height()  # Первоначальная валидация
        
        # Обработчики кнопок
        def on_ok():
            if validate_height():
                dialog.accept()
        
        ok_button.clicked.connect(on_ok)
        cancel_button.clicked.connect(dialog.reject)
        
        # Показываем диалог
        if dialog.exec() == QDialog.DialogCode.Accepted:
            section_height = height_spin.value()
            selected_part = part_combo.currentData()
            placement = placement_combo.currentData()
            
            logger.info(
                "Добавление новой секции на высоте %.3fм, часть: %s, placement=%s",
                section_height,
                selected_part,
                placement,
            )
            
            # Добавляем новую секцию
            self.add_section(section_height, tower_part=selected_part, placement=placement)
    
    @staticmethod
    def _estimate_section_step(section_heights: List[float]) -> float:
        valid_heights = sorted(float(height) for height in section_heights if height is not None)
        if len(valid_heights) < 2:
            return 2.0

        deltas = [
            next_height - current_height
            for current_height, next_height in zip(valid_heights, valid_heights[1:])
            if next_height - current_height > 1e-6
        ]
        if not deltas:
            return 2.0
        return max(float(np.median(deltas)), 0.1)

    @classmethod
    def _suggest_new_section_height(cls, section_heights: List[float], placement: Optional[str]) -> float:
        valid_heights = sorted(float(height) for height in section_heights if height is not None)
        if not valid_heights:
            return 0.0

        placement_mode = (placement or 'absolute').lower()
        step = cls._estimate_section_step(valid_heights)
        if placement_mode == 'top':
            return valid_heights[-1] + step
        if placement_mode == 'bottom':
            return max(0.0, valid_heights[0] - step)
        return (valid_heights[0] + valid_heights[-1]) / 2.0

    @staticmethod
    def _validate_new_section_height(
        section_data: List[Dict],
        height: float,
        *,
        placement: Optional[str] = 'absolute',
        height_tolerance: float = 0.3,
    ) -> Tuple[bool, str]:
        if height < 0 or height > 1000:
            return False, '⚠ Высота должна быть в диапазоне 0-1000 м'

        heights = [
            float(section.get('height'))
            for section in section_data or []
            if section.get('height') is not None
        ]
        for existing_height in heights:
            if abs(existing_height - height) < height_tolerance:
                return False, f'⚠ Секция на высоте {existing_height:.2f} м уже существует'

        if heights:
            placement_mode = (placement or 'absolute').lower()
            min_height = min(heights)
            max_height = max(heights)
            if placement_mode == 'top' and height <= max_height + height_tolerance:
                return False, f'⚠ Для режима "сверху" высота должна быть выше {max_height:.2f} м'
            if placement_mode == 'bottom' and height >= min_height - height_tolerance:
                return False, f'⚠ Для режима "снизу" высота должна быть ниже {min_height:.2f} м'

        return True, '✓ Высота валидна'

    def add_section(self, section_height: float, tower_part: Optional[int] = None, placement: Optional[str] = 'absolute'):
        """Добавляет новую секцию на заданной высоте с точками на всех поясах
        
        Args:
            section_height: Высота новой секции (метры)
            tower_part: Номер части башни (опционально, если не указан - определяется автоматически)
        """
        return self._add_section_impl(section_height, tower_part=tower_part, placement=placement)

        try:
            height_tolerance = 0.3
            
            # Проверяем, нет ли уже секции на этой высоте
            for section in self.section_data:
                if abs(section['height'] - section_height) < height_tolerance:
                    self.info_label.setText(f'⚠ Секция на высоте {section_height:.2f}м уже существует')
                    return
            
            # Получаем список поясов (исключаем точки standing)
            data_without_station = self.data.copy()
            if 'is_station' in self.data.columns:
                mask = self._build_is_station_mask(data_without_station['is_station'])
                data_without_station['is_station'] = mask
                data_without_station = data_without_station[~mask]
            
            available_belts = sorted(data_without_station['belt'].dropna().unique())
            
            if len(available_belts) == 0:
                self.info_label.setText('⚠ Нет поясов для добавления секции')
                return
            
            self._ensure_point_indices()
            added_count = 0
            new_points = []
            
            # Предварительно определяем часть, если она не указана
            section_part = tower_part
            section_segment = tower_part
            
            if section_part is None:
                # Автоматическое определение части из существующих точек
                # Берем точки близкие к целевой высоте
                height_mask = self.data['z'].between(section_height - height_tolerance, section_height + height_tolerance)
                section_points = self.data[height_mask]
                
                if not section_points.empty:
                    # Определяем часть из tower_part или segment
                    if 'tower_part' in section_points.columns and section_points['tower_part'].notna().any():
                        # Берем наиболее часто встречающуюся часть
                        part_counts = section_points['tower_part'].value_counts()
                        if not part_counts.empty:
                            section_part = int(part_counts.index[0])
                            section_segment = section_part  # segment соответствует части
                    elif 'segment' in section_points.columns and section_points['segment'].notna().any():
                        segment_counts = section_points['segment'].value_counts()
                        if not segment_counts.empty:
                            section_segment = int(segment_counts.index[0])
                            section_part = section_segment
                else:
                    # Если нет точек на этой высоте, ищем ближайшие точки
                    if not self.data.empty:
                        # Берем точки выше и ниже
                        points_below = self.data[self.data['z'] < section_height]
                        points_above = self.data[self.data['z'] > section_height]
                        
                        # Используем точки снизу, если есть, иначе сверху
                        reference_points = points_below if not points_below.empty else points_above
                        if not reference_points.empty:
                            if 'tower_part' in reference_points.columns and reference_points['tower_part'].notna().any():
                                part_counts = reference_points['tower_part'].value_counts()
                                if not part_counts.empty:
                                    section_part = int(part_counts.index[0])
                                    section_segment = section_part
                            elif 'segment' in reference_points.columns and reference_points['segment'].notna().any():
                                segment_counts = reference_points['segment'].value_counts()
                                if not segment_counts.empty:
                                    section_segment = int(segment_counts.index[0])
                                    section_part = section_segment
            
            # Убеждаемся, что колонки существуют
            if 'tower_part' not in self.data.columns:
                self.data['tower_part'] = None
            if 'segment' not in self.data.columns:
                self.data['segment'] = None
            
            # Добавляем точку на каждом поясе
            for belt_num in available_belts:
                belt_num = int(belt_num)
                
                # Получаем точки этого пояса (без точек standing)
                belt_points = data_without_station[data_without_station['belt'] == belt_num]
                
                if len(belt_points) < 2:
                    logger.warning(f"На поясе {belt_num} недостаточно точек для интерполяции")
                    continue
                
                # Сортируем точки пояса по высоте
                belt_points_sorted = belt_points.sort_values('z')
                
                # Находим точки выше и ниже уровня новой секции
                points_below = belt_points_sorted[belt_points_sorted['z'] < section_height]
                points_above = belt_points_sorted[belt_points_sorted['z'] > section_height]
                
                # Выбираем точки для интерполяции/экстраполяции
                if points_below.empty:
                    # Берем две самые нижние точки (экстраполяция вниз)
                    p1 = belt_points_sorted.iloc[0]
                    p2 = belt_points_sorted.iloc[1]
                elif points_above.empty:
                    # Берем две самые верхние точки (экстраполяция вверх)
                    p1 = belt_points_sorted.iloc[-2]
                    p2 = belt_points_sorted.iloc[-1]
                else:
                    # Интерполяция между ближайшими точками
                    p1 = points_below.iloc[-1]  # Ближайшая снизу
                    p2 = points_above.iloc[0]   # Ближайшая сверху
                
                # Линейная интерполяция/экстраполяция
                if abs(p2['z'] - p1['z']) < 1e-6:
                    # Точки на одной высоте
                    new_x = (p1['x'] + p2['x']) / 2
                    new_y = (p1['y'] + p2['y']) / 2
                else:
                    t = (section_height - p1['z']) / (p2['z'] - p1['z'])
                    new_x = p1['x'] + t * (p2['x'] - p1['x'])
                    new_y = p1['y'] + t * (p2['y'] - p1['y'])
                
                # Генерируем имя для новой точки
                new_name = f"S{int(section_height)}_B{belt_num}"
                
                # Создаем новую точку с информацией о части
                new_point = {
                    'name': new_name,
                    'x': new_x,
                    'y': new_y,
                    'z': section_height,
                    'belt': belt_num,
                    'point_index': self._get_next_point_index()
                }
                
                # Устанавливаем tower_part и segment, если они определены
                if section_part is not None:
                    new_point['tower_part'] = section_part
                if section_segment is not None:
                    new_point['segment'] = section_segment
                
                new_points.append((new_x, new_y, section_height))
                
                # Добавляем к DataFrame
                new_point_df = pd.DataFrame([new_point])
                self.data = pd.concat([self.data, new_point_df], ignore_index=True)
                self._ensure_point_indices()
                
                added_count += 1
                
                logger.info(f"Добавлена точка '{new_name}' на ({new_x:.3f}, {new_y:.3f}, {section_height:.3f}), часть: {section_part}")
            
            # Добавляем новую секцию в section_data
            new_section = {
                'height': section_height,
                'points': new_points,
                'belt_nums': [int(b) for b in available_belts]
            }
            
            # Добавляем информацию о части, если она определена
            if section_part is not None:
                new_section['tower_part'] = section_part
            if section_segment is not None:
                new_section['segment'] = section_segment
            
            self.section_data.append(new_section)
            
            # Сортируем section_data по высоте
            self.section_data = sorted(self.section_data, key=lambda s: s['height'])
            
            # Обновляем IndexManager после добавления точек
            self.index_manager.set_data(self.data)
            
            # Обновляем визуализацию
            self.update_3d_view()
            self.update_section_lines()
            
            # Обновляем состояние кнопок
            has_sections = bool(len(self.section_data) > 0)
            if hasattr(self, 'build_central_axis_btn'):
                self.build_central_axis_btn.setEnabled(has_sections)
            
            # Обновляем центральную ось, если она отображается
            if self.show_central_axis:
                self.update_central_axis()
            
            # Сигнализируем об изменении
            self.data_changed.emit()
            self.update_all_indices()
            
            # Показываем информацию
            self.info_label.setText(
                f'✓ Секция добавлена! Z={section_height:.3f}м, добавлено точек: {added_count}'
            )
            
            logger.info(f"Добавлена секция на высоте {section_height:.3f}м: {added_count} точек")
            
        except Exception as e:
            logger.error(f"Ошибка при добавлении секции: {e}", exc_info=True)
            self.info_label.setText(f'❌ Ошибка: {str(e)}')

    def _add_section_impl(
        self,
        section_height: float,
        *,
        tower_part: Optional[int] = None,
        placement: Optional[str] = 'absolute',
    ):
        """Canonical section insertion path used by the dialog and tests."""
        try:
            height_tolerance = 0.3
            is_valid, validation_message = self._validate_new_section_height(
                self.section_data,
                float(section_height),
                placement=placement,
                height_tolerance=height_tolerance,
            )
            if not is_valid:
                self.info_label.setText(validation_message)
                return

            placement_mode = (placement or 'absolute').lower()
            description = f'Добавить секцию Z={section_height:.3f} м'
            with self.undo_transaction(description) as tx:
                data_without_station = self.data.copy()
                if 'is_station' in self.data.columns:
                    station_mask = self._build_is_station_mask(data_without_station['is_station'])
                    data_without_station['is_station'] = station_mask
                    data_without_station = data_without_station[~station_mask]

                available_belts = sorted(data_without_station['belt'].dropna().unique())
                if not available_belts:
                    self.info_label.setText('⚠ Нет поясов для добавления секции')
                    return

                self._ensure_point_indices()
                added_count = 0
                section_part = tower_part
                section_segment = tower_part

                if section_part is None:
                    height_mask = self.data['z'].between(section_height - height_tolerance, section_height + height_tolerance)
                    section_points = self.data[height_mask]
                    if not section_points.empty:
                        if 'tower_part' in section_points.columns and section_points['tower_part'].notna().any():
                            part_counts = section_points['tower_part'].value_counts()
                            if not part_counts.empty:
                                section_part = int(part_counts.index[0])
                                section_segment = section_part
                        elif 'segment' in section_points.columns and section_points['segment'].notna().any():
                            segment_counts = section_points['segment'].value_counts()
                            if not segment_counts.empty:
                                section_segment = int(segment_counts.index[0])
                                section_part = section_segment
                    else:
                        points_below = self.data[self.data['z'] < section_height]
                        points_above = self.data[self.data['z'] > section_height]
                        if placement_mode == 'top':
                            reference_points = points_below if not points_below.empty else points_above
                        elif placement_mode == 'bottom':
                            reference_points = points_above if not points_above.empty else points_below
                        else:
                            reference_points = points_below if not points_below.empty else points_above

                        if not reference_points.empty:
                            if 'tower_part' in reference_points.columns and reference_points['tower_part'].notna().any():
                                part_counts = reference_points['tower_part'].value_counts()
                                if not part_counts.empty:
                                    section_part = int(part_counts.index[0])
                                    section_segment = section_part
                            elif 'segment' in reference_points.columns and reference_points['segment'].notna().any():
                                segment_counts = reference_points['segment'].value_counts()
                                if not segment_counts.empty:
                                    section_segment = int(segment_counts.index[0])
                                    section_part = section_segment

                if 'tower_part' not in self.data.columns:
                    self.data['tower_part'] = None
                if 'segment' not in self.data.columns:
                    self.data['segment'] = None
                if 'tower_part_memberships' not in self.data.columns:
                    self.data['tower_part_memberships'] = None
                if 'is_part_boundary' not in self.data.columns:
                    self.data['is_part_boundary'] = False

                for belt_value in available_belts:
                    belt_num = int(belt_value)
                    belt_points = data_without_station[data_without_station['belt'] == belt_num]
                    if len(belt_points) < 2:
                        logger.warning("На поясе %s недостаточно точек для интерполяции", belt_num)
                        continue

                    belt_points_sorted = belt_points.sort_values('z')
                    points_below = belt_points_sorted[belt_points_sorted['z'] < section_height]
                    points_above = belt_points_sorted[belt_points_sorted['z'] > section_height]

                    if points_below.empty:
                        p1 = belt_points_sorted.iloc[0]
                        p2 = belt_points_sorted.iloc[1]
                    elif points_above.empty:
                        p1 = belt_points_sorted.iloc[-2]
                        p2 = belt_points_sorted.iloc[-1]
                    else:
                        p1 = points_below.iloc[-1]
                        p2 = points_above.iloc[0]

                    if abs(float(p2['z']) - float(p1['z'])) < 1e-6:
                        new_x = (float(p1['x']) + float(p2['x'])) / 2.0
                        new_y = (float(p1['y']) + float(p2['y'])) / 2.0
                    else:
                        ratio = (float(section_height) - float(p1['z'])) / (float(p2['z']) - float(p1['z']))
                        new_x = float(p1['x']) + ratio * (float(p2['x']) - float(p1['x']))
                        new_y = float(p1['y']) + ratio * (float(p2['y']) - float(p1['y']))

                    new_point = dict(p1.to_dict())
                    new_point['name'] = f"S{int(round(section_height))}_B{belt_num}"
                    new_point['x'] = float(new_x)
                    new_point['y'] = float(new_y)
                    new_point['z'] = float(section_height)
                    new_point['belt'] = belt_num
                    new_point['point_index'] = self._get_next_point_index()
                    new_point['is_section_generated'] = True

                    if 'is_station' in self.data.columns:
                        new_point['is_station'] = False
                    if 'is_auxiliary' in self.data.columns:
                        new_point['is_auxiliary'] = False
                    if 'is_control' in self.data.columns:
                        new_point['is_control'] = False
                    if 'station_role' in self.data.columns:
                        new_point['station_role'] = None
                    if section_part is not None:
                        new_point['tower_part'] = section_part
                    if section_segment is not None:
                        new_point['segment'] = section_segment
                    if 'is_part_boundary' in self.data.columns:
                        new_point['is_part_boundary'] = False
                    if 'tower_part_memberships' in self.data.columns:
                        new_point['tower_part_memberships'] = (
                            json.dumps([int(section_part)], ensure_ascii=False)
                            if section_part is not None else None
                        )
                    if 'part_belt' in self.data.columns:
                        new_point['part_belt'] = belt_num
                    if 'part_belt_assignments' in self.data.columns:
                        new_point['part_belt_assignments'] = (
                            json.dumps({str(int(section_part)): belt_num}, ensure_ascii=False)
                            if section_part is not None else None
                        )

                    self.data = pd.concat([self.data, pd.DataFrame([new_point])], ignore_index=True)
                    added_count += 1

                if added_count == 0:
                    self.info_label.setText('⚠ Не удалось добавить точки секции')
                    return

                self._ensure_point_indices()
                requested_heights = sorted(
                    [
                        float(section.get('height'))
                        for section in self.section_data
                        if section.get('height') is not None
                    ] + [float(section_height)]
                )
                self.section_data = get_section_lines(self.data, requested_heights, height_tolerance=height_tolerance)

                self.index_manager.set_data(self.data)
                self.update_3d_view()
                self.update_section_lines()

                has_sections = bool(self.section_data)
                if hasattr(self, 'build_central_axis_btn'):
                    self.build_central_axis_btn.setEnabled(has_sections)
                if self.show_central_axis:
                    self.update_central_axis()

                self.data_changed.emit()
                self.update_all_indices()
                tx.commit()

                self.info_label.setText(
                    f'✓ Секция добавлена! Z={section_height:.3f} м, добавлено точек: {added_count}'
                )
                logger.info("Добавлена секция на высоте %.3f м: %s точек", section_height, added_count)

        except Exception as e:
            logger.error(f"Ошибка при добавлении секции: {e}", exc_info=True)
            self.info_label.setText(f'❌ Ошибка: {str(e)}')
    
    def shift_tower_height_dialog(self):
        """Диалог изменения высоты нижней секции (смещение всей башни)"""
        if self.data is None or self.data.empty:
            self.info_label.setText('⚠ Нет данных для смещения.')
            return
        
        # Находим текущую минимальную высоту
        current_min_height = self.data['z'].min()
        
        logger.info(f"Текущая минимальная высота башни: {current_min_height:.3f}м")
        
        # Если есть секции, находим минимальную высоту секции
        if self.section_data:
            section_heights = [s['height'] for s in self.section_data]
            min_section_height = min(section_heights)
            logger.info(f"Текущая высота нижней секции: {min_section_height:.3f}м")
        else:
            min_section_height = current_min_height
        
        # Создаем диалоговое окно
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QDoubleSpinBox, QPushButton, QHBoxLayout
        
        dialog = QDialog(self)
        dialog.setWindowTitle('Изменить высоту нижней секции')
        dialog.setModal(True)
        
        layout = QVBoxLayout()
        
        # Информация
        info_text = f'Текущая минимальная высота: {current_min_height:.3f}м'
        if self.section_data:
            info_text += f'\nТекущая высота нижней секции: {min_section_height:.3f}м'
        info_label = QLabel(info_text)
        layout.addWidget(info_label)
        
        # Поле ввода новой высоты
        layout.addWidget(QLabel('Новая высота нижней секции (метры):'))
        height_spin = QDoubleSpinBox()
        height_spin.setMinimum(-1000.0)
        height_spin.setMaximum(1000.0)
        height_spin.setValue(min_section_height if self.section_data else current_min_height)
        height_spin.setDecimals(3)
        height_spin.setSingleStep(0.1)
        layout.addWidget(height_spin)
        
        # Информация о смещении
        offset_label = QLabel('Смещение: 0.000м')
        layout.addWidget(offset_label)
        
        # Обновление информации о смещении при изменении значения
        def update_offset_info():
            new_height = height_spin.value()
            reference_height = min_section_height if self.section_data else current_min_height
            offset = new_height - reference_height
            offset_label.setText(f'Смещение: {offset:+.3f}м')
        
        height_spin.valueChanged.connect(update_offset_info)
        
        # Кнопки
        button_layout = QHBoxLayout()
        ok_button = QPushButton('OK')
        cancel_button = QPushButton('Отмена')
        apply_compact_button_style(ok_button, width=120, min_height=34)
        apply_compact_button_style(cancel_button, width=120, min_height=34)
        button_layout.addWidget(ok_button)
        button_layout.addWidget(cancel_button)
        layout.addLayout(button_layout)
        
        dialog.setLayout(layout)
        
        # Обработчики кнопок
        ok_button.clicked.connect(dialog.accept)
        cancel_button.clicked.connect(dialog.reject)
        
        # Показываем диалог
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_height = height_spin.value()
            reference_height = min_section_height if self.section_data else current_min_height
            offset = new_height - reference_height
            
            if abs(offset) < 0.001:
                self.info_label.setText('⚠ Смещение слишком мало, изменения не применены')
                return
            
            logger.info(f"Смещение башни на {offset:+.3f}м")
            
            # Применяем смещение
            self.shift_tower_height(offset)
    
    def shift_tower_height(self, offset: float):
        """Смещает всю башню по высоте на заданную величину
        
        Args:
            offset: Величина смещения по Z (метры), может быть положительной или отрицательной
        """
        try:
            if abs(offset) < 0.001:
                self.info_label.setText('⚠ Смещение слишком мало')
                return
            
            # Подсчитываем количество точек
            total_points = len(self.data)
            
            # Смещаем все точки по Z
            self.data['z'] = self.data['z'] + offset
            
            logger.info(f"Смещено {total_points} точек на {offset:+.3f}м по оси Z")
            
            # Смещаем все секции
            if self.section_data:
                sections_count = len(self.section_data)
                
                for section in self.section_data:
                    # Обновляем высоту секции
                    section['height'] += offset
                    
                    # Обновляем координаты Z для всех точек в секции
                    updated_points = []
                    for x, y, z in section['points']:
                        updated_points.append((x, y, z + offset))
                    section['points'] = updated_points
                
                logger.info(f"Смещено {sections_count} секций на {offset:+.3f}м")
            
            # Обновляем визуализацию
            self.update_3d_view()
            self.update_section_lines()
            
            # Обновляем центральную ось, если она отображается
            if self.show_central_axis:
                self.update_central_axis()
            
            # Сигнализируем об изменении данных
            self.data_changed.emit()
            self.update_all_indices()
            
            # Находим новую минимальную высоту
            new_min_height = self.data['z'].min()
            
            # Показываем информацию
            direction = "вверх" if offset > 0 else "вниз"
            self.info_label.setText(
                f'✓ Башня смещена {direction} на {abs(offset):.3f}м. Новая минимальная высота: {new_min_height:.3f}м'
            )
            
            logger.info(f"Башня смещена {direction} на {abs(offset):.3f}м. Новая минимальная высота: {new_min_height:.3f}м")
            
        except Exception as e:
            logger.error(f"Ошибка при смещении башни: {e}", exc_info=True)
            self.info_label.setText(f'❌ Ошибка: {str(e)}')
    
    def find_belt_line_at_position(self, mouse_pos) -> Optional[Tuple[int, int, int]]:
        """Определяет, на какую линию между точками пояса кликнули
        
        Returns:
            Tuple[belt_num, point1_idx, point2_idx] или None
        """
        if self.data is None or self.data.empty:
            return None
        
        try:
            # Получаем размер виджета и viewport
            w = self.glview.width()
            h = self.glview.height()
            viewport = (0, 0, w, h)
            region = (0, 0, w, h)
            
            # Получаем матрицы трансформации с правильными аргументами
            view_matrix = self.glview.viewMatrix()
            proj_matrix = self.glview.projectionMatrix(region, viewport)
            mvp = proj_matrix * view_matrix
            
            # Проверяем линии всех поясов
            available_belts = self.get_available_belts()
            
            best_match = None
            best_dist = float('inf')
            
            for belt_num in available_belts:
                belt_mask = self.data['belt'] == belt_num
                belt_indices = self.data.index[belt_mask].tolist()
                
                if len(belt_indices) < 2:
                    continue
                
                # Сортируем точки пояса по углу для правильного соединения
                belt_points_data = self.data.loc[belt_indices]
                from core.planar_orientation import extract_reference_station_xy, sort_points_clockwise

                sorted_indices = sort_points_clockwise(
                    belt_points_data,
                    station_xy=extract_reference_station_xy(self.data),
                    preserve_index=True,
                ).index.tolist()
                
                # Проверяем все линии между соседними точками (включая замыкающую)
                for i in range(len(sorted_indices)):
                    idx1 = sorted_indices[i]
                    idx2 = sorted_indices[(i + 1) % len(sorted_indices)]
                    
                    p1 = self.data.loc[idx1]
                    p2 = self.data.loc[idx2]
                    
                    # Проецируем точки на экран
                    vec1 = pg.Vector(p1['x'], p1['y'], p1['z'])
                    vec2 = pg.Vector(p2['x'], p2['y'], p2['z'])
                    
                    transformed1 = mvp.map(vec1)
                    transformed2 = mvp.map(vec2)
                    
                    # Проверяем, что оба конца видимы
                    if transformed1.z() >= 1.0 or transformed2.z() >= 1.0:
                        continue
                    
                    screen1_x = (transformed1.x() + 1.0) * w / 2.0
                    screen1_y = (1.0 - transformed1.y()) * h / 2.0
                    screen2_x = (transformed2.x() + 1.0) * w / 2.0
                    screen2_y = (1.0 - transformed2.y()) * h / 2.0
                    
                    # Вычисляем расстояние от клика до линии
                    # Используем формулу расстояния от точки до отрезка
                    line_vec = np.array([screen2_x - screen1_x, screen2_y - screen1_y])
                    line_len = np.linalg.norm(line_vec)
                    
                    if line_len < 1e-6:
                        continue
                    
                    line_dir = line_vec / line_len
                    
                    # Вектор от начала линии до клика
                    to_click = np.array([mouse_pos.x() - screen1_x, mouse_pos.y() - screen1_y])
                    
                    # Проекция на линию
                    t = np.dot(to_click, line_dir)
                    t = max(0, min(line_len, t))  # Ограничиваем отрезком
                    
                    # Ближайшая точка на отрезке
                    closest = np.array([screen1_x, screen1_y]) + t * line_dir
                    
                    # Расстояние от клика до линии
                    dist = np.linalg.norm(np.array([mouse_pos.x(), mouse_pos.y()]) - closest)
                    
                    # Если это лучшее совпадение
                    if dist < best_dist and dist < 20:  # Порог 20 пикселей
                        best_dist = dist
                        best_match = (belt_num, idx1, idx2)
            
            return best_match
        
        except Exception as e:
            logger.error(f"Ошибка при определении линии пояса: {e}", exc_info=True)
            return None
    
    def find_section_line_at_position(self, mouse_pos) -> Optional[float]:
        """Определяет, на какую линию секции кликнули или на какую точку (для определения высоты)
        
        Returns:
            float: Высота секции или точки, если найдена, иначе None
        """
        # Сначала проверяем секции, если они есть
        if self.section_data:
            try:
                # Получаем размер виджета и viewport
                w = self.glview.width()
                h = self.glview.height()
                viewport = (0, 0, w, h)
                region = (0, 0, w, h)
                
                # Получаем матрицы трансформации с правильными аргументами
                view_matrix = self.glview.viewMatrix()
                proj_matrix = self.glview.projectionMatrix(region, viewport)
                mvp = proj_matrix * view_matrix
                
                best_dist = float('inf')
                best_section_height = None
                
                # Проверяем каждую линию секции
                for section_info in self.section_data:
                    section_height = section_info['height']
                    points = section_info['points']
                    
                    if len(points) < 2:
                        continue
                    
                    # Проверяем каждый отрезок линии секции
                    for i in range(len(points) - 1):
                        p1 = points[i]
                        p2 = points[i + 1]
                        
                        # Проецируем точки на экран
                        vec1 = pg.Vector(p1[0], p1[1], p1[2])
                        vec2 = pg.Vector(p2[0], p2[1], p2[2])
                        
                        transformed1 = mvp.map(vec1)
                        transformed2 = mvp.map(vec2)
                        
                        # Проверяем, что оба конца видимы
                        if transformed1.z() >= 1.0 or transformed2.z() >= 1.0:
                            continue
                        
                        screen1_x = (transformed1.x() + 1.0) * w / 2.0
                        screen1_y = (1.0 - transformed1.y()) * h / 2.0
                        screen2_x = (transformed2.x() + 1.0) * w / 2.0
                        screen2_y = (1.0 - transformed2.y()) * h / 2.0
                        
                        # Вычисляем расстояние от клика до линии
                        line_vec = np.array([screen2_x - screen1_x, screen2_y - screen1_y])
                        line_len = np.linalg.norm(line_vec)
                        
                        if line_len < 1e-6:
                            continue
                        
                        line_dir = line_vec / line_len
                        
                        # Вектор от начала линии до клика
                        to_click = np.array([mouse_pos.x() - screen1_x, mouse_pos.y() - screen1_y])
                        
                        # Проекция на линию
                        t = np.dot(to_click, line_dir)
                        t = max(0, min(line_len, t))
                        
                        # Ближайшая точка на отрезке
                        closest = np.array([screen1_x, screen1_y]) + t * line_dir
                        
                        # Расстояние от клика до линии
                        dist = np.linalg.norm(np.array([mouse_pos.x(), mouse_pos.y()]) - closest)
                        
                        # Если это лучшее совпадение
                        if dist < best_dist and dist < 20:  # Порог 20 пикселей
                            best_dist = dist
                            best_section_height = section_height
                
                return best_section_height
            except Exception as e:
                logger.error(f"Ошибка при определении линии секции: {e}", exc_info=True)
                return None
        
        # Если секций нет, ищем ближайшую точку (кроме точки стояния)
        try:
            clicked_idx = self.find_nearest_point(mouse_pos)
            if clicked_idx is not None and clicked_idx in self.data.index:
                point = self.data.loc[clicked_idx]
                # Проверяем, что это не точка стояния
                if 'is_station' in self.data.columns:
                    is_station = self.data.at[clicked_idx, 'is_station']
                    if pd.notna(is_station) and bool(is_station):
                        logger.debug(f"Клик на точку стояния {clicked_idx}, пропускаем")
                        return None
                # Возвращаем высоту точки
                return float(point['z'])
        
        except Exception as e:
            logger.error(f"Ошибка при определении линии секции: {e}", exc_info=True)
            return None
    
    def key_press_event(self, event):
        """Обработка нажатий клавиш"""
        if event.key() == Qt.Key.Key_Escape:
            if self.belt_mass_move_mode:
                self.belt_mass_move_mode = False
                self.pending_belt_num = None
                self.info_label.setText('Режим массового переноса точек пояса отменен')
                return
            elif self.belt_selection_mode:
                self.cancel_belt_selection()
                self.info_label.setText('Режим выбора линии пояса отменен')
                return
            elif self.section_selection_mode:
                self.section_selection_mode = False
                self.pending_point_idx = None
                self.info_label.setText('Режим выбора уровня секции отменен')
                return
            elif self.section_alignment_mode:
                self.section_alignment_mode = False
                self.info_label.setText('Режим выравнивания секции отменен')
                return
            elif self.section_deletion_mode:
                self.section_deletion_mode = False
                self.info_label.setText('Режим удаления секции отменен')
                return
            elif self.xy_plane_move_mode:
                self.xy_plane_move_mode = False
                self.info_label.setText('Перенос плоскости XY отменен')
                return
        
        # Стандартная обработка
        gl.GLViewWidget.keyPressEvent(self.glview, event)
    
    def toggle_belt_lines(self, checked: bool):
        """Переключить отображение линий поясов"""
        self.show_belt_lines = checked
        self.update_3d_view()
    
    def reset_camera(self):
        """Сброс положения камеры"""
        if self.data is not None and not self.data.empty:
            positions = self.data[['x', 'y', 'z']].values
            center = positions.mean(axis=0)
            
            # Вычисляем расстояние камеры
            extent = positions.max(axis=0) - positions.min(axis=0)
            distance = np.linalg.norm(extent) * 2
            
            self.glview.setCameraPosition(
                distance=distance,
                elevation=30,
                azimuth=45
            )
            self.glview.opts['center'] = pg.Vector(center[0], center[1], center[2])
    
    def update_info_label(self):
        """Обновление информационной панели"""
        total = len(self.data) if self.data is not None else 0
        selected = len(self.selected_indices)
        
        self.info_label.setText(f'Точек: {total} | Выбрано: {selected}')
    
    def select_points(self, indices: List[int]):
        """
        Выбрать точки по индексам (point_index или индексы DataFrame)
        
        Args:
            indices: Список индексов (point_index, если есть в данных, иначе индексы DataFrame)
        """
        try:
            if self.data is None or self.data.empty:
                logger.warning("select_points: data пуст или None")
                return

            station_to_activate: Optional[int] = None
            positions: List[int] = []

            # КРИТИЧЕСКИ ВАЖНО: нормализуем индексы в позиции (iloc индексы)
            # для правильного соответствия с selected_indices и визуализацией
            for idx in indices:
                pos = None
                
                # Метод 1: если это point_index, ищем напрямую в данных (ПРИОРИТЕТ!)
                # КРИТИЧЕСКИ ВАЖНО: point_index начинается с 1, а позиции с 0
                # Поэтому нужно искать по колонке point_index, а не использовать idx как позицию
                # Проверяем point_index ПЕРВЫМ, так как это самый надежный способ
                if 'point_index' in self.data.columns:
                    try:
                        # Проверяем, является ли idx point_index (обычно point_index >= 1)
                        # Но также проверяем, что такой point_index существует в данных
                        mask = self.data['point_index'] == idx
                        if mask.any():
                            # Находим первую позицию с таким point_index
                            # Используем позиционный поиск через iloc
                            matching_positions = [i for i, m in enumerate(mask) if m]
                            if matching_positions:
                                pos = matching_positions[0]  # Берем первую найденную позицию
                                logger.debug(
                                    f"select_points: Найдена позиция pos={pos} для point_index={idx}, "
                                    f"name={self.data.iloc[pos].get('name', 'N/A') if 'name' in self.data.columns else 'N/A'}"
                                )
                        else:
                            # Если не нашли по point_index, пробуем как индекс DataFrame
                            if idx in self.data.index:
                                pos = list(self.data.index).index(idx)
                                logger.debug(f"select_points: Найдена позиция pos={pos} для DataFrame index={idx}")
                    except Exception as e:
                        logger.debug(f"select_points: ошибка при поиске по point_index для idx={idx}: {e}")
                
                # Метод 2: пробуем через index_manager (если point_index не сработал)
                if pos is None:
                    try:
                        pos = self.index_manager.normalize_to_position(idx, index_type='auto')
                        if pos is not None:
                            # Валидация: проверяем, что позиция корректна
                            if pos < 0 or pos >= len(self.data):
                                logger.warning(f"select_points: index_manager вернул невалидную позицию {pos} для idx={idx}")
                                pos = None
                            else:
                                logger.debug(f"select_points: index_manager вернул позицию pos={pos} для idx={idx}")
                    except Exception as e:
                        logger.debug(f"select_points: index_manager не смог нормализовать idx={idx}: {e}")
                
                # Метод 3: если это индекс DataFrame
                if pos is None:
                    try:
                        if idx in self.data.index:
                            pos = list(self.data.index).index(idx)
                            logger.debug(f"select_points: Найдена позиция pos={pos} для DataFrame index={idx}")
                    except (ValueError, TypeError) as e:
                        logger.debug(f"select_points: idx={idx} не найден в индексах DataFrame: {e}")
                
                # Метод 4: если это уже позиция (0-based)
                # КРИТИЧЕСКИ ВАЖНО: НЕ используем idx как позицию, если это может быть point_index!
                # point_index обычно >= 1, а позиции 0-based, но лучше проверить явно
                if pos is None:
                    try:
                        if isinstance(idx, int) and 0 <= idx < len(self.data):
                            # Дополнительная проверка: если есть point_index, убеждаемся, что idx не является point_index
                            # Если idx совпадает с point_index какой-то точки, это не позиция!
                            is_point_index = False
                            if 'point_index' in self.data.columns:
                                is_point_index = (self.data['point_index'] == idx).any()
                            
                            if not is_point_index:
                                # Проверяем, что это действительно позиция
                                if idx < len(self.data.index):
                                    pos = idx
                                    logger.debug(f"select_points: Использован idx={idx} как позиция")
                            else:
                                logger.debug(f"select_points: idx={idx} является point_index, не используем как позицию")
                    except Exception as e:
                        logger.debug(f"select_points: ошибка при проверке позиции для idx={idx}: {e}")
                
                if pos is not None:
                    positions.append(pos)
                    # Получаем индекс DataFrame для проверки станции
                    try:
                        dataframe_idx = self.data.index[pos]
                        if station_to_activate is None and dataframe_idx in self.station_indices:
                            station_to_activate = dataframe_idx
                    except (IndexError, KeyError):
                        pass
                else:
                    logger.warning(
                        f"select_points: Не удалось нормализовать индекс {idx} (тип: {type(idx)}) в позицию. "
                        f"Доступные point_index: {list(self.data['point_index'].unique()[:5]) if 'point_index' in self.data.columns else 'N/A'}, "
                        f"доступные индексы DataFrame: {list(self.data.index[:5])}"
                    )

            n = len(self.data)
            self.selected_indices = [pos for pos in positions if 0 <= pos < n]
            
            # Логируем для отладки
            if self.selected_indices:
                selected_names = []
                selected_coords = []
                for p in self.selected_indices:
                    if p < len(self.data):
                        row = self.data.iloc[p]
                        name = row.get('name', 'N/A') if 'name' in self.data.columns else 'N/A'
                        coords = (float(row['x']), float(row['y']), float(row['z']))
                        selected_names.append(name)
                        selected_coords.append(coords)
                
                logger.info(
                    f"select_points: Выбрано {len(self.selected_indices)} точек. "
                    f"Позиции: {self.selected_indices}, имена: {selected_names}, "
                    f"координаты: {selected_coords}"
                )
            
            self.update_3d_view()
            self.update_info_label()

            if station_to_activate is not None:
                self.set_active_station_index(station_to_activate)
        except Exception as e:
            logger.error(f"Ошибка в select_points: {e}", exc_info=True)
    
    def clear_selection(self):
        """Очистить выбор"""
        self.selected_indices = []
        self.update_3d_view()
        self.update_info_label()
    
    def mouse_move_event(self, event):
        """Обработка перемещения мыши с зажатой кнопкой"""
        # Если зажата правая кнопка - перемещаем камеру
        if event.buttons() & Qt.MouseButton.RightButton:
            if self.camera_drag_start_pos is not None:
                delta = event.pos() - self.camera_drag_start_pos
                # Перемещение камеры
                self.glview.pan(delta.x(), delta.y(), 0, relative='view')
                self.camera_drag_start_pos = event.pos()
            return
        
        # Если зажата средняя кнопка или Shift+ЛКМ - вращаем камеру
        if (event.buttons() & Qt.MouseButton.MiddleButton) or \
           (event.buttons() & Qt.MouseButton.LeftButton and event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            if self.camera_drag_start_pos is not None:
                delta = event.pos() - self.camera_drag_start_pos
                # Вращение камеры
                self.glview.orbit(delta.x() * 0.5, delta.y() * 0.5)
                self.camera_drag_start_pos = event.pos()
            return
        
        # Стандартная обработка для других случаев
        # Вызываем стандартный обработчик напрямую
        gl.GLViewWidget.mouseMoveEvent(self.glview, event)
    
    def mouse_press_event(self, event):
        """Обработка нажатия мыши"""
        # Правая кнопка - начинаем перемещение камеры
        if event.button() == Qt.MouseButton.RightButton:
            self.camera_drag_start_pos = event.pos()
            self.camera_drag_button = Qt.MouseButton.RightButton
            return
        
        # Средняя кнопка или Shift+ЛКМ - начинаем вращение камеры
        if event.button() == Qt.MouseButton.MiddleButton or \
           (event.button() == Qt.MouseButton.LeftButton and event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            self.camera_drag_start_pos = event.pos()
            self.camera_drag_button = event.button()
            return
        
        if event.button() == Qt.MouseButton.LeftButton:
            # Если активен режим массового переноса точек пояса
            if self.belt_mass_move_mode:
                logger.info(f"Обработка клика в режиме belt_mass_move_mode={self.belt_mass_move_mode}")
                result = self.find_belt_line_at_position(event.pos())
                if result is not None:
                    belt_num, point1_idx, point2_idx = result
                    p1_name = self.data.at[point1_idx, 'name'] if 'name' in self.data.columns else f'Точка {point1_idx}'
                    p2_name = self.data.at[point2_idx, 'name'] if 'name' in self.data.columns else f'Точка {point2_idx}'
                    logger.info(f"Выбрана линия {p1_name}-{p2_name} пояса {belt_num} для массового переноса")
                    self.move_all_belt_points_to_line(belt_num, point1_idx, point2_idx)
                else:
                    logger.warning("Не найдена линия пояса при клике")
                    self.info_label.setText('⚠ Кликните на линию между точками пояса')
                return
            
            # Если активен режим выбора линии пояса
            if self.belt_selection_mode:
                logger.info(f"Обработка клика в режиме belt_selection_mode={self.belt_selection_mode}")
                result = self.find_belt_line_at_position(event.pos())
                if result is not None:
                    belt_num, point1_idx, point2_idx = result
                    
                    # Проверяем, что индексы действительны после возможного удаления точек
                    if point1_idx >= len(self.data) or point2_idx >= len(self.data):
                        self.info_label.setText('⚠ Одна из точек линии была удалена')
                        self.belt_selection_mode = False
                        self.pending_point_idx = None
                        logger.warning(f"Индексы вне диапазона: point1_idx={point1_idx}, point2_idx={point2_idx}, len(data)={len(self.data)}")
                        return
                    
                    p1_name = self.data.at[point1_idx, 'name'] if 'name' in self.data.columns else f'Точка {point1_idx}'
                    p2_name = self.data.at[point2_idx, 'name'] if 'name' in self.data.columns else f'Точка {point2_idx}'
                    logger.info(f"Выбрана линия {p1_name}-{p2_name} пояса {belt_num}")
                    self.project_point_to_selected_belt_line(belt_num, point1_idx, point2_idx)
                else:
                    logger.warning("Не найдена линия пояса при клике")
                    self.info_label.setText('⚠ Кликните на линию между точками пояса')
                return
            
            # Если активен режим выбора уровня секции
            if self.section_selection_mode:
                section_height = self.find_section_line_at_position(event.pos())
                if section_height is not None:
                    logger.info(f"Выбран уровень секции Z={section_height:.3f}м")
                    self.project_point_to_section_level(section_height)
                else:
                    self.info_label.setText('⚠ Кликните на зеленую линию секции')
                return
            
            # Если активен режим выравнивания секции
            if self.section_alignment_mode:
                section_height = self.find_section_line_at_position(event.pos())
                if section_height is not None:
                    logger.info(f"Выбран уровень для выравнивания Z={section_height:.3f}м")
                    self.align_section(section_height)
                else:
                    if self.section_data:
                        self.info_label.setText('⚠ Кликните на зеленую линию секции или на точку')
                    else:
                        self.info_label.setText('⚠ Кликните на точку (не точку стояния) для переноса всех точек на эту высоту')
                return
            
            # Если активен режим удаления секции
            if self.section_deletion_mode:
                section_height = self.find_section_line_at_position(event.pos())
                if section_height is not None:
                    logger.info(f"Выбран уровень секции для удаления Z={section_height:.3f}м")
                    self.delete_section(section_height)
                else:
                    self.info_label.setText('⚠ Кликните на зеленую линию секции')
                return
            
            if self.xy_plane_move_mode:
                clicked_idx = self.find_nearest_point(event.pos())
                if clicked_idx is not None:
                    self.apply_xy_plane_translation(clicked_idx)
                else:
                    self.info_label.setText('⚠ Выберите точку, через которую пройдет плоскость XY')
                return
            
            # Находим ближайшую точку к клику
            # Используем ту же простую логику, что и в mouse_double_click_event (которая работает правильно)
            if self.data is not None and not self.data.empty:
                logger.debug(f"mouse_press_event: Начинаем поиск ближайшей точки. event.pos()={event.pos()}")
                clicked_idx = self.find_nearest_point(event.pos())
                logger.debug(f"mouse_press_event: find_nearest_point вернул clicked_idx={clicked_idx}")
                
                if clicked_idx is not None:
                    # КРИТИЧЕСКИ ВАЖНО: find_nearest_point возвращает индекс DataFrame
                    # Нужно найти позицию (iloc) этого индекса
                    # Используем ту же логику, что в mouse_double_click_event
                    pos = None
                    try:
                        # Метод 1: прямой поиск позиции по индексу DataFrame
                        pos = list(self.data.index).index(clicked_idx)
                        logger.debug(f"mouse_press_event: Найдена позиция pos={pos} для clicked_idx={clicked_idx}")
                        
                        # Валидация
                        if pos < 0 or pos >= len(self.data):
                            raise ValueError(f"Позиция {pos} вне диапазона [0, {len(self.data)})")
                        
                        # Дополнительная валидация: проверяем соответствие
                        validation_idx = self.data.index[pos]
                        if validation_idx != clicked_idx:
                            logger.warning(
                                f"mouse_press_event: Несоответствие! clicked_idx={clicked_idx}, pos={pos}, "
                                f"validation_idx={validation_idx}. Используем validation_idx."
                            )
                            clicked_idx = validation_idx
                    except (ValueError, AttributeError, IndexError) as e:
                        logger.debug(f"mouse_press_event: Прямой поиск не удался: {e}, пробуем index_manager")
                        # Fallback через index_manager
                        try:
                            pos = self.index_manager.normalize_to_position(clicked_idx, 'dataframe_index')
                            logger.debug(f"mouse_press_event: index_manager вернул pos={pos}")
                        except Exception as e2:
                            logger.debug(f"mouse_press_event: index_manager не смог конвертировать: {e2}")
                            pos = None
                    
                    if pos is None:
                        logger.error(
                            f"mouse_press_event: Не удалось определить позицию для clicked_idx={clicked_idx}. "
                            f"Доступные индексы (первые 10): {list(self.data.index[:10])}, "
                            f"всего точек: {len(self.data)}"
                        )
                        return
                    
                    # КРИТИЧЕСКАЯ ВАЛИДАЦИЯ: проверяем, что pos действительно соответствует clicked_idx
                    final_validation_idx = self.data.index[pos]
                    if final_validation_idx != clicked_idx:
                        logger.error(
                            f"mouse_press_event: КРИТИЧЕСКАЯ ОШИБКА! После всех конвертаций несоответствие! "
                            f"pos={pos}, clicked_idx={clicked_idx}, final_validation_idx={final_validation_idx}"
                        )
                        # Исправляем
                        clicked_idx = final_validation_idx
                    
                    # Получаем информацию о точке
                    point_row = self.data.iloc[pos]
                    point_name = point_row.get('name', 'N/A') if 'name' in self.data.columns else 'N/A'
                    
                    # Получаем point_index напрямую из данных по позиции
                    point_index = None
                    if 'point_index' in self.data.columns:
                        point_index_value = point_row.get('point_index')
                        if pd.notna(point_index_value):
                            try:
                                point_index = int(point_index_value)
                            except (ValueError, TypeError):
                                pass
                    
                    logger.info(
                        f"mouse_press_event: Клик обработан. pos={pos}, idx={clicked_idx}, "
                        f"point_index={point_index}, name={point_name}"
                    )
                    
                    # Обработка множественного выбора
                    if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                        if pos in self.selected_indices:
                            self.selected_indices.remove(pos)
                        else:
                            self.selected_indices.append(pos)
                    else:
                        self.selected_indices = [pos]
                    
                    self.update_3d_view()
                    self.update_info_label()
                    
                    if clicked_idx in self.station_indices:
                        self.set_active_station_index(clicked_idx)
                    
                    # Эмитируем point_selected с point_index
                    # КРИТИЧЕСКИ ВАЖНО: проверяем, что point_index действительно соответствует выбранной точке
                    try:
                        # ВАЛИДАЦИЯ: проверяем point_index перед эмиссией
                        if point_index is not None:
                            # Проверяем, что point_index действительно соответствует точке в pos
                            validation_point_index = None
                            if 'point_index' in self.data.columns:
                                validation_point_index_value = self.data.iloc[pos].get('point_index')
                                if pd.notna(validation_point_index_value):
                                    try:
                                        validation_point_index = int(validation_point_index_value)
                                    except (ValueError, TypeError):
                                        pass
                            
                            if validation_point_index != point_index:
                                logger.warning(
                                    f"mouse_press_event: Несоответствие point_index! "
                                    f"point_index={point_index}, validation_point_index={validation_point_index}, "
                                    f"pos={pos}, name={point_name}. Используем validation_point_index."
                                )
                                point_index = validation_point_index
                            
                            if point_index is not None:
                                self.point_selected.emit(point_index)
                                logger.info(
                                    f"mouse_press_event: Эмит point_selected с point_index={point_index} "
                                    f"для точки pos={pos}, idx={clicked_idx}, name={point_name}"
                                )
                            else:
                                # Fallback: используем index_manager
                                point_index_from_manager = self.index_manager.find_point_index_by_dataframe_index(clicked_idx)
                                if point_index_from_manager is not None:
                                    self.point_selected.emit(point_index_from_manager)
                                    logger.info(
                                        f"mouse_press_event: Эмит point_selected (через manager) point_index={point_index_from_manager} "
                                        f"для точки pos={pos}, idx={clicked_idx}, name={point_name}"
                                    )
                                else:
                                    # Последний fallback: используем индекс DataFrame
                                    logger.warning(
                                        f"mouse_press_event: point_index недоступен, используем clicked_idx={clicked_idx} "
                                        f"для точки pos={pos}, name={point_name}"
                                    )
                                    self.point_selected.emit(clicked_idx)
                        else:
                            # Fallback: используем index_manager
                            point_index_from_manager = self.index_manager.find_point_index_by_dataframe_index(clicked_idx)
                            if point_index_from_manager is not None:
                                self.point_selected.emit(point_index_from_manager)
                                logger.info(
                                    f"mouse_press_event: Эмит point_selected (через manager) point_index={point_index_from_manager} "
                                    f"для точки pos={pos}, idx={clicked_idx}, name={point_name}"
                                )
                            else:
                                # Последний fallback: используем индекс DataFrame
                                logger.warning(
                                    f"mouse_press_event: point_index недоступен, используем clicked_idx={clicked_idx} "
                                    f"для точки pos={pos}, name={point_name}"
                                )
                                self.point_selected.emit(clicked_idx)
                    except (KeyError, IndexError) as e:
                        logger.error(
                            f"mouse_press_event: Ошибка при получении point_index для pos={pos}, "
                            f"clicked_idx={clicked_idx}: {e}", exc_info=True
                        )
                        self.point_selected.emit(clicked_idx)
                    
                    # Важно: не вызываем стандартный обработчик, если выбрали точку
                    event.accept()
                    return
        
        # Если не выбрали точку - стандартное поведение камеры
        # Вызываем стандартный обработчик только если не обработали событие
        # Используем прямой вызов через класс, чтобы избежать рекурсии
        gl.GLViewWidget.mousePressEvent(self.glview, event)
    
    def mouse_release_event(self, event):
        """Обработка отпускания мыши"""
        # Сбрасываем состояние перетаскивания камеры
        if event.button() == self.camera_drag_button:
            self.camera_drag_start_pos = None
            self.camera_drag_button = None
        
        gl.GLViewWidget.mouseReleaseEvent(self.glview, event)
    
    def mouse_double_click_event(self, event):
        """Обработка двойного клика - редактирование точки"""
        if event.button() == Qt.MouseButton.LeftButton:
            # Игнорируем двойной клик в режиме выбора пояса
            if self.belt_selection_mode:
                return
            
            if self.data is not None and not self.data.empty:
                clicked_idx = self.find_nearest_point(event.pos())
                if clicked_idx is not None:
                    # Конвертируем индекс DataFrame в позицию (аналогично mouse_press_event)
                    pos = None
                    try:
                        pos = list(self.data.index).index(clicked_idx)
                        # Валидация
                        if pos < 0 or pos >= len(self.data):
                            raise ValueError(f"Позиция {pos} вне диапазона")
                        validation_idx = self.data.index[pos]
                        if validation_idx != clicked_idx:
                            clicked_idx = validation_idx
                    except (ValueError, AttributeError, IndexError):
                        # Fallback через index_manager
                        try:
                            pos = self.index_manager.normalize_to_position(clicked_idx, 'dataframe_index')
                        except Exception:
                            pos = None
                    
                    if pos is None:
                        logger.warning(f"mouse_double_click_event: Не удалось определить позицию для clicked_idx={clicked_idx}")
                        return
                    
                    self.selected_indices = [pos]
                    self.update_3d_view()
                    self.update_info_label()
                    self.set_active_station_index(clicked_idx if clicked_idx in self.station_indices else None)
                    self.edit_selected_point()
                    return
        
        gl.GLViewWidget.mouseDoubleClickEvent(self.glview, event)
    
    def find_nearest_point(self, mouse_pos) -> Optional[int]:
        """
        Найти ближайшую точку к позиции мыши.
        
        Returns:
            Индекс DataFrame ближайшей точки или None, если не найдена.
            ВАЖНО: Возвращает индекс DataFrame, который соответствует позиции в массиве positions.
            Гарантируется, что возвращаемый индекс соответствует найденной позиции pos_idx.
        """
        if self.data is None or self.data.empty or self.point_scatter is None:
            return None
        
        try:
            # Получаем размер виджета и viewport
            w = self.glview.width()
            h = self.glview.height()
            if w <= 0 or h <= 0:
                return None
            
            viewport = (0, 0, w, h)
            region = (0, 0, w, h)
            
            # Получаем матрицы трансформации
            view_matrix = self.glview.viewMatrix()
            proj_matrix = self.glview.projectionMatrix(region, viewport)
            mvp = proj_matrix * view_matrix
            
            # Проецируем все точки на экран
            # КРИТИЧЕСКИ ВАЖНО: собираем все кандидаты и выбираем лучший по реальному расстоянию
            candidates = []  # Список кандидатов: (pos_idx, idx, dist, effective_dist, screen_x, screen_y)
            threshold = 15  # Пиксели (порог для клика)
            
            # Получаем координаты мыши относительно GLViewWidget
            # ВАЖНО: mouse_pos может быть QPoint, нужно убедиться, что координаты правильные
            mouse_x = float(mouse_pos.x())
            mouse_y = float(mouse_pos.y())
            
            # КРИТИЧЕСКИ ВАЖНО: проверяем, что координаты мыши в пределах виджета
            if mouse_x < 0 or mouse_x >= w or mouse_y < 0 or mouse_y >= h:
                logger.warning(
                    f"find_nearest_point: Координаты мыши вне виджета! "
                    f"mouse=({mouse_x}, {mouse_y}), widget_size=({w}, {h})"
                )
                # Не возвращаем None, так как это может быть нормально (клик на границе)
            
            logger.debug(
                f"find_nearest_point: Поиск ближайшей точки. "
                f"Мышь=({mouse_x:.1f}, {mouse_y:.1f}), виджет=({w}, {h}), threshold={threshold}px"
            )
            
            # КРИТИЧЕСКИ ВАЖНО: НЕ используем point_scatter.pos для поиска, так как он может быть не синхронизирован
            # Используем координаты напрямую из self.data - это гарантирует актуальность и правильный порядок
            # Порядок: self.data.iloc[i] соответствует positions[i] в update_3d_view
            
            # Итерируемся по позициям напрямую из self.data
            # Это гарантирует, что мы используем актуальные координаты в правильном порядке
            for pos_idx in range(len(self.data)):
                # Получаем координаты напрямую из self.data - это гарантирует актуальность
                row = self.data.iloc[pos_idx]
                pos_3d = np.array([
                    float(row['x']),
                    float(row['y']),
                    float(row['z'])
                ], dtype=float)
                
                # Получаем индекс DataFrame для этой позиции
                idx = self.data.index[pos_idx]
                
                # Преобразуем точку в экранные координаты
                vec = pg.Vector(float(pos_3d[0]), float(pos_3d[1]), float(pos_3d[2]))
                
                # Применяем view и projection матрицы
                transformed = mvp.map(vec)
                
                # Нормализованные координаты устройства (NDC) находятся в диапазоне [-1, 1]
                ndc_x = transformed.x()
                ndc_y = transformed.y()
                ndc_z = transformed.z()
                
                # Проверяем, что точка видна (в пределах видимой области и перед камерой)
                # В NDC координатах видимая область: x,y в [-1,1], z в [-1,1]
                # z < 1.0 означает, что точка перед камерой (в видимой области)
                if -1.0 <= ndc_x <= 1.0 and -1.0 <= ndc_y <= 1.0 and -1.0 <= ndc_z < 1.0:
                    # Преобразуем NDC координаты в экранные координаты
                    # PyQtGraph использует систему координат с началом в левом верхнем углу
                    screen_x = (ndc_x + 1.0) * w / 2.0
                    screen_y = (1.0 - ndc_y) * h / 2.0  # Инвертируем Y, так как экранная Y идет сверху вниз
                    
                    # Вычисляем расстояние от клика до спроецированной точки
                    dx = screen_x - mouse_x
                    dy = screen_y - mouse_y
                    dist = np.sqrt(dx * dx + dy * dy)
                    
                    # Учитываем размер точки при вычислении расстояния
                    # Используем базовый размер, так как размеры точек могут различаться
                    point_size = 6.0  # Базовый размер точки
                    # Если точка выбрана, она может быть крупнее
                    if pos_idx in self.selected_indices:
                        point_size = 12.0
                    
                    # Эффективное расстояние: если клик внутри радиуса точки, считаем расстояние = 0
                    # Иначе используем расстояние минус радиус (но не меньше 0)
                    point_radius = point_size / 2.0
                    if dist <= point_radius:
                        # Клик внутри точки - приоритет выше
                        effective_dist = 0.0
                    else:
                        # Клик вне точки - используем расстояние минус радиус
                        effective_dist = dist - point_radius
                    
                    # Если точка достаточно близко, добавляем в кандидаты
                    # ВАЖНО: используем реальное расстояние (dist) для сравнения, а не эффективное
                    if effective_dist < threshold:
                        candidates.append((pos_idx, idx, dist, effective_dist, screen_x, screen_y, point_radius))
            
            # Выбираем лучшего кандидата: сначала по эффективному расстоянию, затем по реальному расстоянию
            # Это гарантирует, что точки, в которые кликнули напрямую (effective_dist=0), имеют приоритет
            # А среди них выбираем ближайшую по реальному расстоянию
            if candidates:
                # Сортируем: сначала по effective_dist (меньше лучше), затем по dist (меньше лучше)
                candidates.sort(key=lambda c: (c[3], c[2]))  # (effective_dist, dist)
                nearest_pos_idx, nearest_idx, min_dist, min_effective_dist, screen_x, screen_y, point_radius = candidates[0]
                
                # КРИТИЧЕСКАЯ ВАЛИДАЦИЯ: проверяем, что nearest_idx действительно соответствует nearest_pos_idx
                validation_idx = self.data.index[nearest_pos_idx]
                if validation_idx != nearest_idx:
                    logger.warning(
                        f"find_nearest_point: Несоответствие индексов! "
                        f"nearest_pos_idx={nearest_pos_idx}, nearest_idx={nearest_idx}, "
                        f"validation_idx={validation_idx}. Используем validation_idx."
                    )
                    nearest_idx = validation_idx
                
                # Логируем информацию о найденной точке и всех близких кандидатах
                point_name = self.data.iloc[nearest_pos_idx].get('name', 'N/A') if 'name' in self.data.columns else 'N/A'
                point_coords = self.data.iloc[nearest_pos_idx][['x', 'y', 'z']].values
                logger.info(
                    f"find_nearest_point: Найдено {len(candidates)} кандидатов. Выбрана точка pos={nearest_pos_idx}, "
                    f"idx={nearest_idx}, name={point_name}, coords=({point_coords[0]:.3f}, {point_coords[1]:.3f}, {point_coords[2]:.3f}), "
                    f"dist={min_dist:.2f}px, effective={min_effective_dist:.2f}px, "
                    f"screen=({screen_x:.1f}, {screen_y:.1f}), mouse=({mouse_x:.1f}, {mouse_y:.1f})"
                )
                
                # Логируем все близкие кандидаты для диагностики
                if len(candidates) > 1:
                    logger.debug(f"find_nearest_point: Все кандидаты (первые 5):")
                    for i, (c_pos_idx, c_idx, c_dist, c_eff_dist, c_sx, c_sy, c_radius) in enumerate(candidates[:5]):
                        c_name = self.data.iloc[c_pos_idx].get('name', 'N/A') if 'name' in self.data.columns else 'N/A'
                        c_coords = self.data.iloc[c_pos_idx][['x', 'y', 'z']].values
                        logger.debug(
                            f"  [{i}] pos={c_pos_idx}, idx={c_idx}, name={c_name}, "
                            f"coords=({c_coords[0]:.3f}, {c_coords[1]:.3f}, {c_coords[2]:.3f}), "
                            f"dist={c_dist:.2f}px, effective={c_eff_dist:.2f}px"
                        )
            else:
                nearest_pos_idx = None
                nearest_idx = None
                min_dist = float('inf')
            
            if nearest_idx is not None and nearest_pos_idx is not None:
                # ВАЛИДАЦИЯ: проверяем соответствие позиции и индекса DataFrame
                try:
                    # Проверяем, что индекс DataFrame действительно соответствует сохраненной позиции
                    validation_idx = self.data.index[nearest_pos_idx]
                    if validation_idx != nearest_idx:
                        logger.warning(
                            f"find_nearest_point: Несоответствие индексов! "
                            f"Позиция={nearest_pos_idx}, ожидаемый индекс={validation_idx}, "
                            f"полученный индекс={nearest_idx}. Используем валидированный индекс."
                        )
                        nearest_idx = validation_idx
                    
                    # Получаем информацию о найденной точке для логирования
                    point_name = self.data.iloc[nearest_pos_idx].get('name', 'N/A') if 'name' in self.data.columns else 'N/A'
                    point_index_val = self.data.iloc[nearest_pos_idx].get('point_index', 'N/A') if 'point_index' in self.data.columns else 'N/A'
                    
                    # Координаты из data (то, что использовалось для поиска)
                    data_coords = np.array([
                        float(self.data.iloc[nearest_pos_idx]['x']),
                        float(self.data.iloc[nearest_pos_idx]['y']),
                        float(self.data.iloc[nearest_pos_idx]['z'])
                    ])
                    
                    logger.info(
                        f"find_nearest_point: Найдена точка pos={nearest_pos_idx}, idx={nearest_idx}, "
                        f"point_index={point_index_val}, name={point_name}, "
                        f"coords=({data_coords[0]:.3f}, {data_coords[1]:.3f}, {data_coords[2]:.3f}), "
                        f"расстояние={min_dist:.2f}px, мышь=({mouse_x}, {mouse_y})"
                    )
                except (IndexError, KeyError) as e:
                    logger.error(
                        f"find_nearest_point: Ошибка валидации для pos={nearest_pos_idx}, idx={nearest_idx}: {e}",
                        exc_info=True
                    )
                    # В случае ошибки валидации все равно возвращаем индекс, но с предупреждением
                except Exception as e:
                    logger.debug(f"find_nearest_point: Найдена точка idx={nearest_idx}, расстояние={min_dist:.2f}px, ошибка логирования: {e}")
            
            return nearest_idx
        
        except Exception as e:
            logger.error(f"Ошибка при поиске ближайшей точки: {e}", exc_info=True)
            return None
    
    def set_belt_connection_lines(self, visualization_data: Dict):
        """
        Установить данные для визуализации линий соединения поясов
        
        Args:
            visualization_data: Словарь с данными для визуализации
                {
                    'line1': {'start': [x,y,z], 'end': [x,y,z], 'label': str},
                    'line2': {'start': [x,y,z], 'end': [x,y,z], 'label': str},
                    'matched_points': {'p1': [x,y,z], 'p2': [x,y,z]},
                    'angle_deg': float
                }
        """
        # Удаляем старые линии соединения, если они есть
        if hasattr(self, 'belt_connection_lines'):
            for line in self.belt_connection_lines:
                self.glview.removeItem(line)
        
        self.belt_connection_lines = []
        
        # Сохраняем данные визуализации для последующего использования (например, для зеркального метода)
        self._last_visualization_data = visualization_data
        
        if not visualization_data:
            return
        
        # Получаем данные линий
        line1 = visualization_data.get('line1')
        line2 = visualization_data.get('line2')
        
        if not line1 or not line2:
            return
        
        # Создаем линии соединения
        # Линия 1 (зеленая)
        start1 = np.array(line1['start'])
        end1 = np.array(line1['end'])
        pts1 = np.array([start1, end1])
        line1_mesh = gl.GLLinePlotItem(pos=pts1, color=(0, 1, 0, 1), width=3)
        self.glview.addItem(line1_mesh)
        self.belt_connection_lines.append(line1_mesh)
        
        # Линия 2 (пурпурная)
        start2 = np.array(line2['start'])
        end2 = np.array(line2['end'])
        pts2 = np.array([start2, end2])
        line2_mesh = gl.GLLinePlotItem(pos=pts2, color=(1, 0, 1, 1), width=3)
        self.glview.addItem(line2_mesh)
        self.belt_connection_lines.append(line2_mesh)
        
        # Добавляем проекции на плоскость XY (пунктирные линии)
        # Проекция линии 1
        plane_z = self._get_xy_plane_height()

        start1_xy = np.array([start1[0], start1[1], plane_z])
        end1_xy = np.array([end1[0], end1[1], plane_z])
        pts1_xy = np.array([start1_xy, end1_xy])
        line1_xy_mesh = gl.GLLinePlotItem(pos=pts1_xy, color=(0, 1, 0, 0.5), width=1)
        self.glview.addItem(line1_xy_mesh)
        self.belt_connection_lines.append(line1_xy_mesh)
        
        # Проекция линии 2
        start2_xy = np.array([start2[0], start2[1], plane_z])
        end2_xy = np.array([end2[0], end2[1], plane_z])
        pts2_xy = np.array([start2_xy, end2_xy])
        line2_xy_mesh = gl.GLLinePlotItem(pos=pts2_xy, color=(1, 0, 1, 0.5), width=1)
        self.glview.addItem(line2_xy_mesh)
        self.belt_connection_lines.append(line2_xy_mesh)
        
        logger.info(f"Добавлены линии соединения поясов (угол поворота: {visualization_data.get('angle_deg', 0):.2f}°)")
        logger.info(f"Линия 1: от {line1['start']} до {line1['end']}")
        logger.info(f"Линия 2: от {line2['start']} до {line2['end']}")
        
        # Дополнительное логирование для отладки
        logger.info(f"set_belt_connection_lines вызван с данными:")
        logger.info(f"  line1: {line1}")
        logger.info(f"  line2: {line2}")
        logger.info(f"  visualization_data: {visualization_data}")

    def set_belt_polyline(self, belt_num: int, points3d: np.ndarray, color=(1.0, 0.6, 0.0, 0.9), width: int = 2):
        """Отобразить полилинию пояса (замкнутую) для наглядности граней.
        points3d: массив shape (N, 3) в порядке обхода. Если не замкнута, замкнём автоматически.
        """
        try:
            # Удаляем предыдущую линию этого пояса
            if belt_num in self.belt_polylines:
                try:
                    self.glview.removeItem(self.belt_polylines[belt_num])
                except Exception:
                    pass
                self.belt_polylines.pop(belt_num, None)

            if points3d is None or len(points3d) < 2:
                return

            pts = np.array(points3d, dtype=float)
            # замыкаем
            if not np.allclose(pts[0], pts[-1]):
                pts = np.vstack([pts, pts[0]])

            line_item = gl.GLLinePlotItem(pos=pts, color=color, width=width, antialias=True)
            self.glview.addItem(line_item)
            self.belt_polylines[belt_num] = line_item
            logger.info(f"Отрисована полилиния пояса {belt_num}: {len(pts)-1} рёбер")
        except Exception as e:
            logger.error(f"Ошибка отрисовки полилинии пояса {belt_num}: {e}", exc_info=True)
    
    def update_section_lines(self):
        """Обновить визуализацию линий секций"""
        # Удаляем старые линии секций
        for line in self.section_lines:
            self.glview.removeItem(line)
        self.section_lines.clear()
        
        if not self.section_data:
            return
        
        # Рисуем горизонтальные линии между точками на одном уровне
        for section in self.section_data:
            points = section['points']
            
            if len(points) < 2:
                continue
            
            # Преобразуем в numpy array
            # Замыкаем контур
            pts = points + [points[0]]
            section_points = np.array(pts)
            
            # Рисуем линию, соединяющую все точки секции
            section_line = gl.GLLinePlotItem(
                pos=section_points,
                color=(0.2, 0.8, 0.2, 0.7),  # Зеленый полупрозрачный
                width=2,
                antialias=True
            )
            self.glview.addItem(section_line)
            self.section_lines.append(section_line)
            
            # Добавляем подпись секции
            # Позиция: в начале линии секции, чуть сбоку
            label_pos = section_points[0].copy()
            label_pos[0] += (section_points[-1][0] - section_points[0][0]) * 0.1  # Смещение
            
            section_label = self._create_text_item(
                position=tuple(label_pos),
                text=f'Секция Z={section["height"]:.2f}м',
                color=(0.1, 0.6, 0.1, 0.9),
                font=pg.QtGui.QFont('Arial', 11, pg.QtGui.QFont.Weight.Bold),
            )
            if section_label is not None:
                self.glview.addItem(section_label)
                self.section_lines.append(section_label)
            
            logger.info(f"Отрисована линия секции на высоте {section['height']:.2f}м, точек: {len(points)}")
        
        # Обновляем центральную ось, если она отображается
        if self.show_central_axis:
            self.update_central_axis()
        
        # Обновляем таблицу секций в главном окне
        self.update_data_table_sections()

    def set_structural_lines(self, members_data: List[Dict[str, Any]]):
        """
        Displays structural members (lattice).
        members_data: list of dicts with 'points' (start, end), 'type' (leg, brace...), 'color'.
        """
        # Clear old items (we reuse section_items or create new list?)
        # Let's create a new list for structural members to avoid conflict with sections
        if not hasattr(self, 'structural_items'):
            self.structural_items = []
            
        for item in self.structural_items:
            self.glview.removeItem(item)
        self.structural_items.clear()
        
        if not members_data:
            return
            
        # Batch lines by color/type for performance? 
        # GLLinePlotItem supports mode='lines' for disjoint segments.
        # Group by color
        from collections import defaultdict
        grouped = defaultdict(list)
        
        for m in members_data:
            pts = m['points'] # [p1, p2]
            color = tuple(m['color'])
            grouped[color].append(pts)
            
        for color, segments in grouped.items():
            # Flatten points: [p1a, p1b, p2a, p2b, ...]
            all_points = np.array(segments).reshape(-1, 3)
            
            item = gl.GLLinePlotItem(
                pos=all_points,
                color=color,
                width=1.5,
                mode='lines',
                antialias=True
            )
            self.glview.addItem(item)
            self.structural_items.append(item)

    
    def update_all_indices(self):
        """
        Обновляет все индексы после изменений в данных
        Вызывается при загрузке проекта и любом редактировании
        """
        self._ensure_point_indices()
        # Обновляем IndexManager с актуальными данными
        self.index_manager.set_data(self.data)
        # Обновляем маппинг индексов для выделения точек
        self._refresh_index_mapping()
        # Очищаем выбранные индексы, которые могут быть недействительными
        self.selected_indices = []
        self.pending_point_idx = None
        
        # Обновляем 3D вид только если не выполняется уже обновление
        if not getattr(self, '_updating_3d_view', False):
            self.update_3d_view()
        self.update_info_label()
    
    def set_data(self, data: pd.DataFrame, preserve_history: bool = False):
        """
        Установить данные для отображения
        
        Args:
            data: DataFrame с колонками x, y, z, name, и опционально belt, is_station
        """
        self.data = data.copy()

        if self.data is None or self.data.empty:
            self.xy_plane_initialized = False
            self.clear_xy_plane_visual()
        elif not preserve_history:
            self.xy_plane_initialized = False
        
        # Добавляем колонку belt если её нет
        if 'belt' not in self.data.columns:
            self.data['belt'] = None
        
        # Добавляем колонку is_station если её нет
        if 'is_station' not in self.data.columns:
            self.data['is_station'] = False
        
        # Активируем кнопку создания секций, если есть данные с поясами
        if hasattr(self, 'create_sections_btn'):
            has_belts = self.data is not None and not self.data.empty and 'belt' in self.data.columns
            has_valid_belts = bool(has_belts and self.data['belt'].notna().any())
            self.create_sections_btn.setEnabled(has_valid_belts)
        
        # Обновляем внутренние индексы без лишних сигналов
        self._ensure_point_indices()
        # Обновляем IndexManager с новыми данными
        self.index_manager.set_data(self.data)
        self._refresh_index_mapping()
        self.selected_indices = []
        self.pending_point_idx = None
        
        # Обновляем 3D вид только если не выполняется текущий апдейт
        if not getattr(self, '_updating_3d_view', False):
            self.update_3d_view()
        self.update_info_label()
        
        # Центрируем камеру только при загрузке данных
        self.reset_camera()

        if preserve_history:
            self.update_undo_redo_buttons()
        else:
            self.clear_history()
    
    def capture_state(self) -> dict:
        """Сериализует текущее состояние точек и секций для undo/redo."""
        data_snapshot = self.data.copy(deep=True) if self.data is not None else None

        section_snapshot = []
        for section in getattr(self, 'section_data', []) or []:
            section_dict = {
                'height': section.get('height'),
                'points': [tuple(p) for p in section.get('points', [])],
                'belt_nums': list(section.get('belt_nums', [])),
                # Сохраняем всю информацию о частях башни
                'tower_part': section.get('tower_part'),
                'tower_part_memberships': section.get('tower_part_memberships'),
                'is_part_boundary': section.get('is_part_boundary', False),
                'segment': section.get('segment'),
                'segment_name': section.get('segment_name'),
                'section_num': section.get('section_num'),
                'section_name': section.get('section_name'),
            }
            # Сохраняем center, если есть
            if 'center' in section:
                center = section.get('center')
                if center is not None:
                    section_dict['center'] = tuple(center) if isinstance(center, (list, tuple)) else center
            
            section_snapshot.append(section_dict)

        return {
            'data': data_snapshot,
            'section_data': section_snapshot,
            'show_central_axis': self.show_central_axis,
            'point_index_counter': self.point_index_counter,
            'xy_plane_state': self.get_xy_plane_state()
        }

    def restore_state(self, state: dict):
        """Восстанавливает состояние точек и секций."""
        snapshot = state or {}
        data_snapshot = snapshot.get('data')
        if data_snapshot is not None:
            self.data = data_snapshot.copy(deep=True)
            self.point_index_counter = snapshot.get('point_index_counter', 0)
            self._ensure_point_indices()

        snapshot_sections = snapshot.get('section_data', [])
        self.section_data = []
        for section in snapshot_sections:
            section_dict = {
                'height': section.get('height'),
                'points': [tuple(p) for p in section.get('points', [])],
                'belt_nums': list(section.get('belt_nums', [])),
                # Восстанавливаем всю информацию о частях башни
                'tower_part': section.get('tower_part'),
                'tower_part_memberships': section.get('tower_part_memberships'),
                'is_part_boundary': section.get('is_part_boundary', False),
                'segment': section.get('segment'),
                'segment_name': section.get('segment_name'),
                'section_num': section.get('section_num'),
                'section_name': section.get('section_name'),
            }
            # Восстанавливаем center, если есть
            if 'center' in section:
                section_dict['center'] = section.get('center')
            
            self.section_data.append(section_dict)

        self.show_central_axis = snapshot.get('show_central_axis', False)
        self.set_xy_plane_state(snapshot.get('xy_plane_state'), update_geometry=False)

        # Перерисовываем 3D и таблицы
        self.update_all_indices()
        self.update_section_lines()
        if self.show_central_axis:
            self.update_central_axis()

        self.data_changed.emit()

    def push_undo_state(self, description: str):
        """Сохраняет текущее состояние в стек отмен."""
        if self.data is None:
            return

        state = self.capture_state()
        self.undo_stack.append((description, state))
        if len(self.undo_stack) > 50:
            self.undo_stack.pop(0)
 
        self.redo_stack.clear()
        self.update_undo_redo_buttons()
        return state

    @contextmanager
    def undo_transaction(self, description: str):
        """Контекст для операций с поддержкой undo/redo."""
        state = self.push_undo_state(description)
        committed = False

        class _UndoRecord:
            def commit(self_inner):
                nonlocal committed
                committed = True

        record = _UndoRecord()

        try:
            yield record
            if not committed and self.undo_stack and self.undo_stack[-1][0] == description:
                self.undo_stack.pop()
        except Exception:
            if self.undo_stack and self.undo_stack[-1][0] == description:
                self.undo_stack.pop()
            if state is not None:
                self.restore_state(state)
            raise
        finally:
            self.update_undo_redo_buttons()

    def clear_history(self):
        """Очищает историю undo/redo."""
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.update_undo_redo_buttons()

    def undo_action(self):
        """Отменяет последнюю операцию."""
        if not self.undo_stack:
            return

        description, prev_state = self.undo_stack.pop()
        self.redo_stack.append((description, self.capture_state()))
        self.restore_state(prev_state)
        self.info_label.setText(f'↩️ Отменено действие: {description}')
        self.update_undo_redo_buttons()

    def redo_action(self):
        """Повторяет последнюю отменённую операцию."""
        if not self.redo_stack:
            return

        description, next_state = self.redo_stack.pop()
        self.undo_stack.append((description, self.capture_state()))
        self.restore_state(next_state)
        self.info_label.setText(f'↪️ Повторено действие: {description}')
        self.update_undo_redo_buttons()

    def update_undo_redo_buttons(self):
        """Обновляет доступность кнопок Undo/Redo."""
        if hasattr(self, 'undo_button'):
            self.undo_button.setEnabled(bool(self.undo_stack))
        if hasattr(self, 'redo_button'):
            self.redo_button.setEnabled(bool(self.redo_stack))

    def toggle_tower_builder_panel(self, checked: bool):
        self.tower_builder_visible = bool(checked)
        self._update_builder_panel_visibility()

    def _update_builder_panel_visibility(self):
        if not hasattr(self, 'side_tabs'):
            return
        visible = bool(getattr(self, 'tower_builder_visible', False))
        if hasattr(self, 'tower_builder_toggle_btn'):
            self.tower_builder_toggle_btn.blockSignals(True)
            self.tower_builder_toggle_btn.setChecked(visible)
            self.tower_builder_toggle_btn.blockSignals(False)
        
        # Проверить режим конструктора
        is_unified_mode = False
        if hasattr(self, 'tower_builder_panel') and hasattr(self.tower_builder_panel, '_mode'):
            is_unified_mode = self.tower_builder_panel._mode == 'unified'
        
        if visible:
            if is_unified_mode:
                # Режим unified - интегрировать компоненты в основное окно
                self._setup_unified_mode()
            else:
                # Режим tabs - показать side_tabs
                if self._unified_mode_active:
                    self._teardown_unified_mode()
                self.side_tabs.show()
                if hasattr(self, 'main_splitter') and self.main_splitter is not None:
                    self.main_splitter.setCollapsible(1, False)
                    sizes = self.main_splitter.sizes()
                    total = sum(sizes) or 1
                    builder_size = max(getattr(self, '_builder_last_size', 360), 320)
                    main_size = max(total - builder_size, builder_size * 2)
                    self.main_splitter.setSizes([int(main_size), int(builder_size)])
                index = self.side_tabs.indexOf(self.tower_builder_panel)
                if index >= 0:
                    self.side_tabs.setCurrentIndex(index)
        else:
            # Скрыть конструктор
            if self._unified_mode_active:
                self._teardown_unified_mode()
            if hasattr(self, 'main_splitter') and self.main_splitter is not None:
                sizes = self.main_splitter.sizes()
                if len(sizes) >= 2:
                    self._builder_last_size = max(sizes[1], 320)
                    self.main_splitter.setSizes([sizes[0] + sizes[1], 0])
                self.main_splitter.setCollapsible(1, True)
            self.side_tabs.hide()

    def _on_tower_blueprint_requested(self, blueprint: TowerBlueprint):
        self._tower_blueprint = blueprint
        self.tower_blueprint_requested.emit(blueprint)
        
        # При применении blueprint очищаем предпросмотр
        # Визуализация будет через set_structural_lines() после применения
        self._clear_tower_preview()
        self._blueprint_applied = True
        
        # Обновить визуализацию башни в 3D окне (но она не будет отображаться, т.к. blueprint применен)
        self.render_tower_from_blueprint(blueprint)
    
    def _on_tower_visualization_requested(self, blueprint: Optional[TowerBlueprintV2]) -> None:
        """
        Обработка запроса визуализации башни из конструктора.
        
        Args:
            blueprint: Чертеж башни для визуализации (TowerBlueprintV2 или None)
        """
        # Обновить визуализацию башни в 3D окне
        # Метод render_tower_from_blueprint принимает TowerBlueprint или TowerBlueprintV2
        self.render_tower_from_blueprint(blueprint)  # type: ignore

    def _set_status_message(self, message: str):
        if hasattr(self, 'info_label') and message:
            self.info_label.setText(message)

    def show_tower_builder_tab(self):
        self.tower_builder_visible = True
        self._update_builder_panel_visibility()

    def hide_tower_builder_tab(self):
        self.tower_builder_visible = False
        self._update_builder_panel_visibility()

    def set_tower_builder_blueprint(self, blueprint: Optional[TowerBlueprint]):
        self._tower_blueprint = blueprint
        if hasattr(self, 'tower_builder_panel'):
            self.tower_builder_panel.set_blueprint(blueprint)
        
        # Обновить визуализацию башни в 3D окне
        self.render_tower_from_blueprint(blueprint)
    
    def render_tower_from_blueprint(self, blueprint: Optional[TowerBlueprint]) -> None:
        """
        Отрисовать башню из чертежа в 3D окне.
        
        Логика работы:
        - Если blueprint применен к точкам - НЕ использовать Tower3DRenderer (предпросмотр),
          визуализация уже есть через set_structural_lines()
        - Если blueprint не применен - использовать Tower3DRenderer для предпросмотра
        
        Args:
            blueprint: Чертеж башни для отрисовки (может быть TowerBlueprint или TowerBlueprintV2)
        """
        # Если blueprint применен, не используем предпросмотр
        # Визуализация уже есть через set_structural_lines()
        if self._is_blueprint_applied():
            # Очистить предпросмотр, если он был
            if self._tower_renderer:
                self._tower_renderer.clear()
            return
        
        # Режим предпросмотра (blueprint не применен)
        if not self._tower_renderer:
            return
        
        # Преобразовать TowerBlueprint в TowerBlueprintV2, если необходимо
        if blueprint is None:
            self._tower_renderer.render_blueprint(None)
            # Отключить кнопку, если нет чертежа
            if hasattr(self, 'toggle_tower_visualization_btn'):
                self.toggle_tower_visualization_btn.setEnabled(False)
                self.toggle_tower_visualization_btn.setChecked(False)
            return
        
        # Если это уже TowerBlueprintV2, используем напрямую
        if isinstance(blueprint, TowerBlueprintV2):
            self._tower_renderer.render_blueprint(blueprint)
            # Включить кнопку, если есть чертеж
            if hasattr(self, 'toggle_tower_visualization_btn'):
                self.toggle_tower_visualization_btn.setEnabled(True)
                # Восстановить сохраненное состояние видимости
                if self.is_tower_visualization_visible():
                    self.toggle_tower_visualization_btn.setChecked(True)
        else:
            # Для старого формата TowerBlueprint не отрисовываем
            # (можно добавить конвертацию при необходимости)
            self._tower_renderer.render_blueprint(None)
            if hasattr(self, 'toggle_tower_visualization_btn'):
                self.toggle_tower_visualization_btn.setEnabled(False)
                self.toggle_tower_visualization_btn.setChecked(False)
    
    def set_tower_visualization_visible(self, visible: bool) -> None:
        """
        Установить видимость визуализации башни.
        
        В зависимости от состояния blueprint управляет разными источниками визуализации:
        - Если blueprint применен - управляет structural_items (примененная визуализация)
        - Если blueprint не применен - управляет Tower3DRenderer (предпросмотр)
        
        Args:
            visible: True для показа, False для скрытия
        """
        if self._is_blueprint_applied():
            # Управление видимостью примененной визуализации
            if hasattr(self, 'structural_items'):
                for item in self.structural_items:
                    item.setVisible(visible)
        else:
            # Управление видимостью предпросмотра
            if self._tower_renderer:
                self._tower_renderer.set_visible(visible)
    
    def is_tower_visualization_visible(self) -> bool:
        """
        Проверить видимость визуализации башни.
        
        Returns:
            True если визуализация видима, False если скрыта
        """
        if self._is_blueprint_applied():
            # Проверка видимости примененной визуализации
            if hasattr(self, 'structural_items') and self.structural_items:
                # Проверяем видимость первого элемента (все должны иметь одинаковую видимость)
                return self.structural_items[0].isVisible() if self.structural_items else False
            return False
        else:
            # Проверка видимости предпросмотра
            if self._tower_renderer:
                return self._tower_renderer.is_visible()
            return False
    
    def toggle_tower_visualization(self, checked: bool) -> None:
        """
        Переключить видимость визуализации башни.
        
        Args:
            checked: True для показа, False для скрытия
        """
        self.set_tower_visualization_visible(checked)
    
    def _is_blueprint_applied(self) -> bool:
        """
        Проверить, применен ли blueprint к точкам.
        
        Returns:
            True если blueprint применен, False если нет
        """
        return self._blueprint_applied
    
    def _clear_tower_preview(self) -> None:
        """Очистить визуализацию предпросмотра башни из конструктора."""
        if self._tower_renderer:
            self._tower_renderer.clear()
    
    def _setup_unified_mode(self) -> None:
        """
        Настроить layout для режима unified.
        Создает трехпанельный splitter: дерево слева, glview в центре, панель свойств справа.
        """
        if self._unified_mode_active:
            return  # Уже настроено
        
        # Сохранить исходную структуру для восстановления
        if self.main_splitter:
            sizes = self.main_splitter.sizes()
            self._original_splitter_structure = (sizes, self.main_splitter.orientation())
        
        # Получить компоненты из UnifiedTowerBuilderPanel
        if not hasattr(self, 'tower_builder_panel') or not hasattr(self.tower_builder_panel, '_unified_panel'):
            return
        
        unified_panel = self.tower_builder_panel._unified_panel
        if not unified_panel:
            return
        
        # Получить компоненты
        structure_tree = unified_panel.get_structure_tree()
        properties_panel = unified_panel.get_properties_panel()
        toolbar_layout = unified_panel.get_toolbar()
        
        # Извлечь компоненты из их текущих родителей
        # Дерево и панель свойств находятся внутри splitter в unified_panel
        if structure_tree.parent() and hasattr(structure_tree.parent(), 'layout'):
            parent_layout = structure_tree.parent().layout()
            if parent_layout:
                parent_layout.removeWidget(structure_tree)
        
        if properties_panel.parent() and hasattr(properties_panel.parent(), 'layout'):
            parent_layout = properties_panel.parent().layout()
            if parent_layout:
                parent_layout.removeWidget(properties_panel)
        
        # Создать виджет для тулбара
        toolbar_widget = QWidget()
        # Копировать элементы из toolbar_layout
        toolbar_widget_layout = QHBoxLayout(toolbar_widget)
        toolbar_widget_layout.setContentsMargins(4, 4, 4, 4)
        toolbar_widget_layout.setSpacing(4)
        
        # Перенести виджеты из toolbar_layout
        items_to_move = []
        for i in range(toolbar_layout.count()):
            item = toolbar_layout.itemAt(i)
            if item:
                items_to_move.append(item)
        
        for item in items_to_move:
            if item.widget():
                toolbar_layout.removeWidget(item.widget())
                toolbar_widget_layout.addWidget(item.widget())
            elif item.spacerItem():
                toolbar_layout.removeItem(item)
                toolbar_widget_layout.addItem(item.spacerItem())
        
        toolbar_widget.setMaximumHeight(50)
        
        # Создать правую панель с тулбаром и панелью свойств
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(6, 6, 6, 6)
        right_layout.setSpacing(4)
        right_layout.addWidget(toolbar_widget)
        right_layout.addWidget(properties_panel, stretch=1)
        
        # Удалить side_tabs из splitter
        if self.side_tabs in [self.main_splitter.widget(i) for i in range(self.main_splitter.count())]:
            self.main_splitter.removeWidget(self.side_tabs)
        self.side_tabs.hide()
        
        # Скрыть unified_panel (компоненты извлечены)
        unified_panel.hide()
        
        # Добавить новые виджеты в splitter
        # Найти позицию glview
        glview_index = -1
        for i in range(self.main_splitter.count()):
            if self.main_splitter.widget(i) == self.glview:
                glview_index = i
                break
        
        if glview_index >= 0:
            # Вставить дерево перед glview
            self.main_splitter.insertWidget(glview_index, structure_tree)
            # Вставить правую панель после glview
            self.main_splitter.insertWidget(glview_index + 2, right_panel)
        else:
            # Если glview не найден, добавить в конец
            self.main_splitter.addWidget(structure_tree)
            self.main_splitter.addWidget(right_panel)
        
        # Установить пропорции: дерево 20%, glview 60%, панель 20%
        # Найти индексы после вставки
        structure_index = -1
        glview_index = -1
        panel_index = -1
        for i in range(self.main_splitter.count()):
            widget = self.main_splitter.widget(i)
            if widget == structure_tree:
                structure_index = i
            elif widget == self.glview:
                glview_index = i
            elif widget == right_panel:
                panel_index = i
        
        if structure_index >= 0:
            self.main_splitter.setStretchFactor(structure_index, 2)  # Дерево
        if glview_index >= 0:
            self.main_splitter.setStretchFactor(glview_index, 6)  # glview
        if panel_index >= 0:
            self.main_splitter.setStretchFactor(panel_index, 2)  # Панель
        
        # Сохранить ссылки
        self._unified_structure_tree = structure_tree
        self._unified_properties_panel = properties_panel
        self._unified_toolbar_widget = toolbar_widget
        self._unified_mode_active = True
        
        # Показать компоненты
        structure_tree.show()
        right_panel.show()
    
    def _teardown_unified_mode(self) -> None:
        """
        Восстановить исходный layout после режима unified.
        """
        if not self._unified_mode_active:
            return
        
        # Удалить компоненты unified режима из splitter
        widgets_to_remove = []
        for i in range(self.main_splitter.count()):
            widget = self.main_splitter.widget(i)
            if widget == self._unified_structure_tree:
                widgets_to_remove.append((i, widget))
            elif self._unified_toolbar_widget and widget and hasattr(widget, 'layout'):
                # Проверить, содержит ли виджет тулбар
                layout = widget.layout()
                if layout and self._unified_toolbar_widget in [layout.itemAt(j).widget() for j in range(layout.count()) if layout.itemAt(j) and layout.itemAt(j).widget()]:
                    widgets_to_remove.append((i, widget))
        
        # Удалить в обратном порядке, чтобы индексы не сбились
        for i, widget in sorted(widgets_to_remove, reverse=True):
            self.main_splitter.removeWidget(widget)
            widget.hide()
        
        # Вернуть компоненты обратно в unified_panel
        if hasattr(self, 'tower_builder_panel') and hasattr(self.tower_builder_panel, '_unified_panel'):
            unified_panel = self.tower_builder_panel._unified_panel
            if unified_panel and self._unified_structure_tree:
                # Вернуть дерево и панель свойств в unified_panel
                # (они будут восстановлены при следующем показе unified_panel)
                pass
        
        # Восстановить side_tabs
        if self.side_tabs not in [self.main_splitter.widget(i) for i in range(self.main_splitter.count())]:
            self.main_splitter.addWidget(self.side_tabs)
            self.side_tabs.show()
        
        # Восстановить исходные пропорции
        if self._original_splitter_structure:
            sizes, orientation = self._original_splitter_structure
            if len(sizes) >= 2:
                self.main_splitter.setSizes(sizes)
        
        # Сбросить флаги
        self._unified_structure_tree = None
        self._unified_properties_panel = None
        self._unified_toolbar_widget = None
        self._unified_mode_active = False

    def align_all_sections_dialog(self):
        """Диалог выбора пояса для выравнивания всех секций."""
        if self.section_data is None or len(self.section_data) == 0:
            self.info_label.setText('⚠ Нет секций. Сначала создайте секции.')
            return

        if self.data is None or self.data.empty or 'belt' not in self.data.columns:
            self.info_label.setText('⚠ Нет данных с поясами для выравнивания.')
            return

        belts_series = self.data['belt'].dropna()
        if belts_series.empty:
            self.info_label.setText('⚠ Нет назначенных поясов.')
            return

        available_belts = sorted({int(b) for b in belts_series})

        from PyQt6.QtWidgets import QInputDialog

        belt_items = [f'Пояс {belt}' for belt in available_belts]
        belt_text, ok = QInputDialog.getItem(
            self,
            'Выровнять секции',
            'Выберите опорный пояс:',
            belt_items,
            0,
            False
        )

        if not ok or not belt_text:
            return

        selected_index = belt_items.index(belt_text)
        target_belt = available_belts[selected_index]

        self.align_all_sections_to_belt(target_belt)

    def align_all_sections_to_belt(self, belt_num: int):
        """Выровнять все секции по выбранному поясу."""
        if self.section_data is None or len(self.section_data) == 0:
            self.info_label.setText('⚠ Нет секций для выравнивания.')
            return

        if self.data is None or self.data.empty:
            self.info_label.setText('⚠ Нет данных для выравнивания.')
            return

        sections_with_belt = [
            section for section in self.section_data
            if belt_num in [int(b) for b in section.get('belt_nums', []) if b is not None]
        ]

        if not sections_with_belt:
            self.info_label.setText(f'⚠ Ни одна секция не содержит пояс {belt_num}.')
            return

        description = f'Выровнять секции по поясу {belt_num}'
        try:
            with self.undo_transaction(description) as tx:
                moved_total = 0
                total_distance = 0.0
                new_section_levels = []

                for section in self.section_data:
                    belt_nums = section.get('belt_nums', []) or []
                    points = section.get('points', []) or []

                    if not belt_nums or not points:
                        new_section_levels.append(section.get('height'))
                        continue

                    belt_nums_int = [int(b) for b in belt_nums if b is not None]
                    if belt_num not in belt_nums_int:
                        new_section_levels.append(section.get('height'))
                        continue

                    reference_index = belt_nums_int.index(belt_num)
                    reference_point = points[reference_index]
                    target_z = float(reference_point[2])

                    moved, distance = self._align_section_points_to_height(section, target_z)
                    moved_total += moved
                    total_distance += distance
                    new_section_levels.append(target_z)

                if moved_total == 0:
                    self.info_label.setText('⚠ Не удалось выровнять секции — точки не найдены.')
                    return

                try:
                    updated_levels = sorted(set(new_section_levels))
                    new_section_data = get_section_lines(self.data, updated_levels, height_tolerance=0.3)
                    self.section_data = new_section_data
                except Exception as exc:
                    logger.warning(f"Не удалось пересобрать линии секций после выравнивания: {exc}")

                self.update_all_indices()
                self.update_section_lines()
                if self.show_central_axis:
                    self.update_central_axis()

                self.data_changed.emit()

                average_distance = total_distance / moved_total if moved_total else 0.0
                self.info_label.setText(
                    f'✓ Секции выровнены по поясу {belt_num}. Перемещено точек: {moved_total}, '
                    f'средняя Δ={average_distance:.3f} м'
                )
                logger.info(
                    f"Выровнены все секции по поясу {belt_num}: перемещено {moved_total} точек, "
                    f"среднее перемещение {average_distance:.3f} м"
                )

                tx.commit()
        except Exception as e:
            logger.error(f"Ошибка при выравнивании секций: {e}", exc_info=True)
            self.info_label.setText(f'❌ Ошибка: {str(e)}')

    def _align_section_points_to_height(self, section: Dict, target_z: float) -> Tuple[int, float]:
        """Переносит все точки секции на заданный уровень с умным выравниванием."""
        moved_count = 0
        total_distance = 0.0

        belt_nums = section.get('belt_nums', []) or []
        points = section.get('points', []) or []

        for belt_value, point_coords in zip(belt_nums, points):
            if belt_value is None:
                continue

            belt_num = int(belt_value)
            point_index = self._find_point_index_for_section_point(belt_num, point_coords)
            if point_index is None:
                logger.debug(f"Не найден индекс точки пояса {belt_num} для координат {point_coords}")
                continue

            distance = self._move_point_along_belt(point_index, target_z, belt_num)
            if distance > 0:
                moved_count += 1
                total_distance += distance

        return moved_count, total_distance

    def _find_point_index_for_section_point(self, belt_num: int, coords: Tuple[float, float, float], tolerance: float = 0.35) -> Optional[int]:
        """Находит индекс точки в DataFrame, соответствующей точке секции."""
        if self.data is None or self.data.empty or 'belt' not in self.data.columns:
            return None

        belt_series = self.data['belt']
        belt_mask = belt_series.notna() & np.isclose(belt_series.astype(float), float(belt_num))
        candidates = self.data[belt_mask]

        if 'is_station' in candidates.columns:
            mask = self._build_is_station_mask(candidates['is_station'])
            candidates = candidates[~mask]

        if candidates.empty:
            return None

        diffs = np.sqrt(
            (candidates['x'] - coords[0]) ** 2 +
            (candidates['y'] - coords[1]) ** 2 +
            (candidates['z'] - coords[2]) ** 2
        )

        idx = diffs.idxmin()
        if diffs.loc[idx] <= tolerance:
            return idx
        return None

    def _move_point_along_belt(self, point_index: int, target_z: float, belt_num: int) -> float:
        """Смещает точку вдоль линии пояса на указанный уровень."""
        if self.data is None or point_index not in self.data.index:
            return 0.0

        point = self.data.loc[point_index]
        if abs(point['z'] - target_z) < 1e-6:
            # Обновляем на всякий случай точку точным значением высоты
            self.data.at[point_index, 'z'] = target_z
            return 0.0

        belt_numeric = pd.to_numeric(self.data['belt'], errors='coerce')
        belt_points = self.data[belt_numeric.notna() & np.isclose(belt_numeric, float(belt_num))].copy()
        if 'is_station' in belt_points.columns:
            mask = self._build_is_station_mask(belt_points['is_station'])
            belt_points = belt_points[~mask]

        if len(belt_points) < 2:
            self.data.at[point_index, 'z'] = target_z
            return abs(point['z'] - target_z)

        belt_points_sorted = belt_points.sort_values('z')

        points_below = belt_points_sorted[belt_points_sorted['z'] < target_z]
        points_above = belt_points_sorted[belt_points_sorted['z'] > target_z]

        if points_below.empty or points_above.empty:
            if len(belt_points_sorted) < 2:
                return 0.0
            if points_below.empty:
                p1 = belt_points_sorted.iloc[0]
                p2 = belt_points_sorted.iloc[1]
            else:
                p1 = belt_points_sorted.iloc[-2]
                p2 = belt_points_sorted.iloc[-1]
        else:
            p1 = points_below.iloc[-1]
            p2 = points_above.iloc[0]

        if abs(p2['z'] - p1['z']) < 1e-6:
            new_x = (p1['x'] + p2['x']) / 2
            new_y = (p1['y'] + p2['y']) / 2
        else:
            t = (target_z - p1['z']) / (p2['z'] - p1['z'])
            new_x = p1['x'] + t * (p2['x'] - p1['x'])
            new_y = p1['y'] + t * (p2['y'] - p1['y'])

        old_pos = np.array([point['x'], point['y'], point['z']])
        new_pos = np.array([new_x, new_y, target_z])
        distance = np.linalg.norm(new_pos - old_pos)

        self.data.at[point_index, 'x'] = new_x
        self.data.at[point_index, 'y'] = new_y
        self.data.at[point_index, 'z'] = target_z

        return distance

    def _sync_tilt_with_blueprint(self, section_entry: Dict[str, Any], target_offset_mm: float, current_offset_mm: float):
        """Синхронизирует крен секции с отклонениями в blueprint конструктора и обновляет UI."""
        if not self._tower_blueprint:
            return
        
        try:
            from core.tower_generator import TowerBlueprintV2
            
            if not isinstance(self._tower_blueprint, TowerBlueprintV2):
                return
            
            segment = section_entry.get('segment')
            section_name = section_entry.get('section_name')
            section_ref = section_entry.get('section_ref', {})
            
            if not segment or not section_name:
                return
            
            # Находим соответствующую секцию в blueprint
            segment_idx = int(segment) - 1
            if 0 <= segment_idx < len(self._tower_blueprint.segments):
                blueprint_segment = self._tower_blueprint.segments[segment_idx]
                
                # Ищем секцию по имени
                for blueprint_section in blueprint_segment.sections:
                    if blueprint_section.name == section_name:
                        # Вычисляем изменение крена
                        delta_offset_mm = target_offset_mm - current_offset_mm
                        
                        # Вычисляем направление крена из offset_vector
                        offset_vector = section_entry.get('offset_vector', np.array([0.0, 0.0]))
                        if np.linalg.norm(offset_vector) > 1e-9:
                            direction = offset_vector / np.linalg.norm(offset_vector)
                            # Обновляем offset_x и offset_y в метрах
                            blueprint_section.offset_x += float(direction[0] * delta_offset_mm / 1000.0)
                            blueprint_section.offset_y += float(direction[1] * delta_offset_mm / 1000.0)
                            
                            logger.info(
                                f"Синхронизирован крен секции '{section_name}' в части '{blueprint_segment.name}': "
                                f"offset_x={blueprint_section.offset_x * 1000.0:.2f}мм, offset_y={blueprint_section.offset_y * 1000.0:.2f}мм"
                            )
                            
                            # Обновляем UI конструктора
                            if hasattr(self, 'tower_builder_panel'):
                                self.tower_builder_panel.set_blueprint(self._tower_blueprint)
                        break
        except Exception as exc:
            logger.warning(f"Не удалось синхронизировать крен с blueprint: {exc}")

    def _collect_section_point_indices(self, section: Dict, tolerance: float = 0.3) -> List[int]:
        """
        Возвращает индексы точек, принадлежащих указанной секции.
        
        Использует высоту секции и номера поясов (belt_nums) для точного определения точек.
        Это более надежный метод, чем поиск по координатам.
        
        Args:
            section: Словарь с информацией о секции из section_data
            tolerance: Допуск по высоте для поиска точек (метры)
        
        Returns:
            Список индексов точек, принадлежащих секции
        """
        if self.data is None or self.data.empty:
            return []
        
        indices = []
        section_height = section.get('height')
        belt_nums = section.get('belt_nums', []) or []
        
        if section_height is None:
            logger.warning("Не указана высота секции для поиска точек")
            return []
        
        if not belt_nums:
            logger.warning(f"Не указаны номера поясов для секции на высоте {section_height:.3f}м")
            return []
        
        # Исключаем точки standing
        data_without_station = self.data.copy()
        if 'is_station' in self.data.columns:
            data_without_station['is_station'] = self._build_is_station_mask(data_without_station['is_station'])
            data_without_station = data_without_station[~data_without_station['is_station']]
        
        # Находим точки на высоте секции
        height_mask = np.abs(data_without_station['z'].values - section_height) <= tolerance
        level_points = data_without_station[height_mask]
        
        if level_points.empty:
            logger.debug(f"Не найдено точек на высоте {section_height:.3f}м (допуск {tolerance}м)")
            return []
        
        # Фильтруем по номерам поясов
        belt_nums_set = set(int(b) for b in belt_nums if b is not None)
        
        for idx, row in level_points.iterrows():
            belt_val = row.get('belt')
            if pd.notna(belt_val):
                try:
                    belt_num = int(float(belt_val))
                    if belt_num in belt_nums_set:
                        indices.append(idx)
                except (TypeError, ValueError):
                    continue
        
        logger.debug(f"Найдено {len(indices)} точек для секции на высоте {section_height:.3f}м, пояса: {sorted(belt_nums_set)}")
        return indices

    def _find_section_indices_for_point(self, point_index: int) -> List[int]:
        """Находит все точки секции, которой принадлежит указанная точка."""
        if self.section_data is None or not self.section_data:
            return []
        for section in self.section_data:
            indices = self._collect_section_point_indices(section)
            if point_index in indices:
                return indices
        return []

    def _apply_part_assignment(
        self,
        primary_index: int,
        part_value: Optional[int],
        boundary_flag: Optional[bool] = None
    ) -> None:
        """Назначает часть башни точке и всем точкам её секции, учитывая разделение частей."""
        if self.data is None or primary_index not in self.data.index:
            return

        if 'tower_part' not in self.data.columns:
            self.data['tower_part'] = 1
        if 'tower_part_memberships' not in self.data.columns:
            self.data['tower_part_memberships'] = None
        if 'is_part_boundary' not in self.data.columns:
            self.data['is_part_boundary'] = False

        try:
            part_int = int(part_value) if part_value is not None else int(self.data.at[primary_index, 'tower_part'])
        except (TypeError, ValueError):
            part_int = 1
        if part_int <= 0:
            part_int = 1

        affected_indices = self._find_section_indices_for_point(primary_index)
        if not affected_indices:
            affected_indices = [primary_index]

        boundary_indices = set(affected_indices) if boundary_flag else set()
        boundary_z = None
        if boundary_indices:
            try:
                boundary_z = float(self.data.loc[list(boundary_indices), 'z'].astype(float).mean())
            except Exception:
                boundary_z = None

        for idx in affected_indices:
            if idx not in self.data.index:
                continue
            self.data.at[idx, 'tower_part'] = part_int
            is_boundary = idx in boundary_indices
            self.data.at[idx, 'is_part_boundary'] = bool(boundary_flag and is_boundary)
            memberships = {part_int}
            if self.data.at[idx, 'is_part_boundary']:
                memberships.add(part_int + 1)
            self.data.at[idx, 'tower_part_memberships'] = json.dumps(sorted(memberships), ensure_ascii=False)

        if boundary_flag and boundary_z is not None:
            self._rebalance_parts_for_boundary(part_int, boundary_z, boundary_indices)

    def _row_membership_contains(self, row: pd.Series, part_num: int) -> bool:
        memberships = []
        value = row.get('tower_part_memberships')
        if value not in (None, '', [], '{}', '[]'):
            memberships = self._decode_part_memberships(value)
        if memberships:
            return part_num in memberships
        raw_value = row.get('tower_part', 1)
        try:
            base = int(raw_value)
        except (TypeError, ValueError):
            base = 1
        if base <= 0:
            base = 1
        if bool(row.get('is_part_boundary', False)):
            return part_num in (base, base + 1)
        return base == part_num

    def _rebalance_parts_for_boundary(
        self,
        lower_part: int,
        boundary_z: float,
        boundary_indices: set[int]
    ) -> None:
        """Перераспределяет точки между частями относительно новой границы."""
        if self.data is None or boundary_z is None:
            return
        upper_part = lower_part + 1
        tolerance = 1e-4

        for idx, row in self.data.iterrows():
            if bool(row.get('is_station', False)):
                continue
            belongs_lower = self._row_membership_contains(row, lower_part)
            belongs_upper = self._row_membership_contains(row, upper_part)
            if not (belongs_lower or belongs_upper):
                continue

            try:
                z_val = float(row.get('z', 0.0))
            except (TypeError, ValueError):
                z_val = 0.0

            if idx in boundary_indices or abs(z_val - boundary_z) <= tolerance:
                target_part = lower_part
                is_boundary = True
            elif z_val < boundary_z:
                target_part = lower_part
                is_boundary = False
            else:
                target_part = upper_part
                is_boundary = False

            self.data.at[idx, 'tower_part'] = target_part
            self.data.at[idx, 'is_part_boundary'] = is_boundary

            memberships = {target_part}
            if is_boundary:
                memberships.add(upper_part)
            self.data.at[idx, 'tower_part_memberships'] = json.dumps(sorted(memberships), ensure_ascii=False)

    def _compute_section_centers(self) -> List[Dict[str, Any]]:
        """Возвращает список центров секций с векторами отклонений."""
        if not self.section_data:
            return []

        sections = [s for s in self.section_data if s.get('points')]
        if not sections:
            return []

        sorted_sections = sorted(sections, key=lambda s: float(s.get('height', 0.0)))
        
        # Пронумеровываем секции, если они еще не пронумерованы
        # Используем ту же логику, что и в verticality_widget
        height_tolerance = 0.01
        section_num = 0
        seen_heights = []
        
        for section in sorted_sections:
            if 'section_num' not in section or section.get('section_num') is None:
                section_height = section.get('height', 0)
                # Проверяем, не создали ли мы уже секцию на близкой высоте
                is_duplicate = False
                for seen_height in seen_heights:
                    if abs(section_height - seen_height) <= height_tolerance:
                        is_duplicate = True
                        section['section_num'] = section_num - 1
                        break
                
                if not is_duplicate:
                    section['section_num'] = section_num
                    seen_heights.append(section_height)
                    section_num += 1
        
        centers: List[Dict[str, Any]] = []

        for section in sorted_sections:
            points = np.array(section.get('points', []), dtype=float)
            if points.size == 0:
                continue
            center = np.mean(points, axis=0)
            height = float(section.get('height', center[2] if center.size >= 3 else 0.0))
            section_num_val = section.get('section_num', None)  # Получаем номер секции (сквозная нумерация)
            section_name = section.get('section_name', 'Неизвестно')
            
            # Определяем принадлежность к частям башни
            # Используем tower_part_memberships если есть (для граничных секций)
            # Иначе используем tower_part или segment
            part_memberships = []
            if 'tower_part_memberships' in section and section.get('tower_part_memberships') is not None:
                import json
                memberships_val = section.get('tower_part_memberships')
                try:
                    if isinstance(memberships_val, str):
                        # Может быть JSON строка
                        part_memberships = json.loads(memberships_val)
                    elif isinstance(memberships_val, (list, tuple)):
                        # Уже список
                        part_memberships = list(memberships_val)
                    else:
                        part_memberships = []
                    # Преобразуем в список целых чисел
                    part_memberships = [int(p) for p in part_memberships if p is not None and not (isinstance(p, float) and np.isnan(p))]
                except (TypeError, ValueError, json.JSONDecodeError):
                    part_memberships = []
            
            # Если нет memberships, используем tower_part или segment
            if not part_memberships:
                tower_part = section.get('tower_part')
                if tower_part is not None:
                    try:
                        part_memberships = [int(tower_part)]
                    except (TypeError, ValueError):
                        pass
            
            # Если все еще нет, используем segment
            if not part_memberships:
                segment = section.get('segment')
                if segment is not None:
                    try:
                        part_memberships = [int(segment)]
                    except (TypeError, ValueError):
                        pass
            
            # Формируем строку для отображения части
            if len(part_memberships) > 1:
                # Граничная секция - несколько частей через дробь
                part_memberships_sorted = sorted(part_memberships)
                segment_name = '/'.join([str(p) for p in part_memberships_sorted])
            elif len(part_memberships) == 1:
                # Одна часть
                segment_name = f'Часть {part_memberships[0]}'
            else:
                # Неизвестно
                segment = section.get('segment')
                segment_name = f'Часть {segment}' if segment is not None else 'Неизвестно'
            
            centers.append({
                'height': height,
                'center': center,
                'belt_nums': [int(b) for b in section.get('belt_nums', []) if b is not None],
                'section_ref': section,
                'segment': part_memberships[0] if part_memberships else section.get('segment'),
                'segment_name': segment_name,
                'section_name': section_name,
                'section_num': section_num_val,  # Добавляем номер секции
                'tower_part': part_memberships[0] if part_memberships else section.get('tower_part'),
                'tower_part_memberships': part_memberships if len(part_memberships) > 1 else None,
            })

        if not centers:
            return []

        base_center = centers[0]['center']
        base_height = centers[0]['height']
        for entry in centers:
            vec = entry['center'][:2] - base_center[:2]
            entry['offset_vector'] = vec
            entry['offset_len_m'] = float(np.linalg.norm(vec))
            entry['offset_len_mm'] = entry['offset_len_m'] * 1000.0
            entry['height_delta'] = float(entry['height'] - base_height)

        return centers

    def open_section_tilt_dialog(self):
        """Открывает диалог настройки крена секции."""
        if not self.section_data:
            self.info_label.setText('⚠ Нет секций. Сначала создайте секции.')
            return

        centers = self._compute_section_centers()
        if len(centers) < 2:
            self.info_label.setText('⚠ Недостаточно секций для настройки крена.')
            return

        dialog = TiltPlaneDialog(centers, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        selected_info = dialog.get_selected_info()
        if not selected_info:
            return
        target_offset_mm = dialog.get_target_offset_mm()
        self.apply_section_tilt(selected_info['height'], target_offset_mm)

    def open_single_section_tilt_dialog(self):
        """Открывает диалог локального крена только выбранной секции."""
        if not self.section_data:
            self.info_label.setText('⚠ Нет секций. Сначала создайте секции.')
            return

        centers = self._compute_section_centers()
        if len(centers) < 1:
            self.info_label.setText('⚠ Недостаточно секций для настройки крена.')
            return

        dialog = TiltPlaneDialog(
            centers,
            self,
            title='Локальный крен секции',
            note_text='Сдвиг произойдет только для выбранной секции. Направление остаётся прежним.'
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        selected_info = dialog.get_selected_info()
        if not selected_info:
            return
        target_offset_mm = dialog.get_target_offset_mm()
        self.apply_single_section_tilt(selected_info['height'], target_offset_mm)

    def apply_section_tilt(self, section_height: float, target_offset_mm: float):
        """Поворачивает плоскость так, чтобы на секции был заданный крен."""
        if self.data is None or self.data.empty:
            self.info_label.setText('⚠ Нет данных для изменения крена.')
            return
        centers = self._compute_section_centers()
        if not centers:
            self.info_label.setText('⚠ Нет данных о секциях для изменения крена.')
            return

        base_entry = centers[0]
        target_entry = next((c for c in centers if abs(c['height'] - section_height) < 1e-4), None)
        if target_entry is None:
            self.info_label.setText('⚠ Не удалось найти выбранную секцию.')
            return

        height_delta = float(target_entry.get('height_delta', 0.0))
        if abs(height_delta) < 1e-6:
            self.info_label.setText('⚠ Нельзя задать крен для базовой секции.')
            return

        direction_vec = np.array(target_entry.get('offset_vector'), dtype=float)
        direction_norm = float(np.linalg.norm(direction_vec))
        target_offset_m = max(float(target_offset_mm), 0.0) / 1000.0
        current_offset_m = float(target_entry.get('offset_len_m', 0.0))

        if direction_norm < 1e-9:
            if target_offset_m < 1e-6:
                self.info_label.setText('ℹ️ Секция уже имеет нулевой крен.')
            else:
                self.info_label.setText('⚠ Невозможно определить направление крена для этой секции.')
            return

        if abs(target_offset_m - current_offset_m) < 1e-6:
            self.info_label.setText('ℹ️ Крен секции уже соответствует указанному значению.')
            return

        direction_unit = direction_vec / direction_norm
        slope_old = current_offset_m / height_delta
        slope_new = target_offset_m / height_delta

        base_center = np.array(base_entry['center'], dtype=float)
        base_xy = base_center[:2]
        base_height = float(base_entry['height'])

        description = f'Настроить крен секции Z={section_height:.2f}м'
        try:
            with self.undo_transaction(description) as tx:
                # Собираем индексы всех точек секций башни для обработки
                # Используем section_data для определения точек секций
                all_section_point_indices = set()
                
                if self.section_data:
                    for section in self.section_data:
                        section_indices = self._collect_section_point_indices(section, tolerance=0.3)
                        all_section_point_indices.update(section_indices)
                
                if not all_section_point_indices:
                    self.info_label.setText('⚠ Не найдены точки секций для изменения крена.')
                    return
                
                # Исключаем точки standing
                data_without_station = self.data.copy()
                if 'is_station' in self.data.columns:
                    station_mask = self._build_is_station_mask(self.data['is_station'])
                    station_indices = set(self.data[station_mask].index)
                    all_section_point_indices = all_section_point_indices - station_indices
                
                if not all_section_point_indices:
                    self.info_label.setText('⚠ Не найдены точки секций (после исключения точек standing).')
                    return
                
                logger.info(f"Изменение абсолютного крена: обрабатывается {len(all_section_point_indices)} точек секций")
                
                moved_points = 0
                for idx in all_section_point_indices:
                    if idx not in self.data.index:
                        continue
                    row = self.data.loc[idx]
                    z_val = float(row['z'])
                    height_offset = z_val - base_height
                    old_axis_xy = base_xy + direction_unit * slope_old * height_offset
                    new_axis_xy = base_xy + direction_unit * slope_new * height_offset
                    delta = new_axis_xy - old_axis_xy
                    if np.linalg.norm(delta) < 1e-9:
                        continue
                    self.data.at[idx, 'x'] = float(row['x']) + float(delta[0])
                    self.data.at[idx, 'y'] = float(row['y']) + float(delta[1])
                    moved_points += 1

                if moved_points == 0:
                    self.info_label.setText('⚠ Точки не изменились — операция отменена.')
                    return

                # Пересчитываем section_levels из актуальных данных после изменения координат
                section_levels = find_section_levels(self.data, height_tolerance=0.3)
                
                if section_levels:
                    # Обновляем section_data с актуальными координатами точек
                    # get_section_lines теперь всегда правильно сохраняет информацию о частях из данных точек
                    self.section_data = get_section_lines(self.data, section_levels, height_tolerance=0.3)
                else:
                    self.section_data = []

                self.update_all_indices()
                self.update_3d_view()
                self.update_section_lines()
                if self.show_central_axis:
                    self.update_central_axis()

                self.data_changed.emit()
                tx.commit()

                # Синхронизируем крен с отклонениями секций в конструкторе
                self._sync_tilt_with_blueprint(target_entry, target_offset_mm, current_offset_m * 1000.0)
                
                # Получаем номер секции из target_entry
                section_num = target_entry.get('section_num', None)
                section_num_text = f"№{section_num}" if section_num is not None else ""
                section_num_display = f"{section_num_text} " if section_num_text else ""
                
                self.info_label.setText(
                    f'✓ Крен секции {section_num_display}Z={section_height:.2f}м установлен на {target_offset_mm:.2f} мм'
                )
                logger.info(
                    "Крен секции %sZ=%.3fм изменён: было %.3f мм, стало %.3f мм",
                    section_num_display,
                    section_height,
                    current_offset_m * 1000.0,
                    target_offset_m * 1000.0,
                )
        except Exception as exc:
            logger.error(f'Ошибка настройки крена секции: {exc}', exc_info=True)
            self.info_label.setText(f'❌ Ошибка: {exc}')

    def apply_single_section_tilt(self, section_height: float, target_offset_mm: float):
        """Смещает только выбранную секцию до заданного крена."""
        if self.data is None or self.data.empty:
            self.info_label.setText('⚠ Нет данных для изменения крена.')
            return

        centers = self._compute_section_centers()
        if not centers:
            self.info_label.setText('⚠ Нет данных о секциях для изменения крена.')
            return

        base_entry = centers[0]
        target_entry = next((c for c in centers if abs(c['height'] - section_height) < 1e-4), None)
        if target_entry is None:
            self.info_label.setText('⚠ Не удалось найти выбранную секцию.')
            return

        direction_vec = np.array(target_entry.get('offset_vector'), dtype=float)
        direction_norm = float(np.linalg.norm(direction_vec))
        target_offset_m = max(float(target_offset_mm), 0.0) / 1000.0
        current_offset_m = float(target_entry.get('offset_len_m', 0.0))

        if direction_norm < 1e-9:
            if target_offset_m < 1e-6:
                self.info_label.setText('ℹ️ Секция уже имеет нулевой крен.')
            else:
                self.info_label.setText('⚠ Невозможно определить направление крена для этой секции.')
            return

        if abs(target_offset_m - current_offset_m) < 1e-6:
            self.info_label.setText('ℹ️ Крен секции уже соответствует указанному значению.')
            return

        direction_unit = direction_vec / direction_norm
        delta_vec = direction_unit * (target_offset_m - current_offset_m)

        section_ref = target_entry.get('section_ref', {})
        if not section_ref:
            # Если section_ref отсутствует, создаем его из target_entry
            section_ref = {
                'height': section_height,
                'belt_nums': target_entry.get('belt_nums', []),
            }
        
        point_indices = self._collect_section_point_indices(section_ref, tolerance=0.3)
        if not point_indices:
            self.info_label.setText('⚠ Не удалось найти точки выбранной секции.')
            logger.warning(f"Не найдены точки для секции на высоте {section_height:.3f}м, пояса: {section_ref.get('belt_nums', [])}")
            return
        
        logger.info(f"Локальный крен: найдено {len(point_indices)} точек для секции на высоте {section_height:.3f}м")

        description = f'Локальный крен секции Z={section_height:.2f}м'
        try:
            with self.undo_transaction(description) as tx:
                for idx in point_indices:
                    self.data.at[idx, 'x'] = float(self.data.at[idx, 'x']) + float(delta_vec[0])
                    self.data.at[idx, 'y'] = float(self.data.at[idx, 'y']) + float(delta_vec[1])

                # Пересчитываем section_levels из актуальных данных после изменения координат
                section_levels = find_section_levels(self.data, height_tolerance=0.3)
                
                if section_levels:
                    # Обновляем section_data с актуальными координатами точек
                    # get_section_lines теперь всегда правильно сохраняет информацию о частях из данных точек
                    self.section_data = get_section_lines(self.data, section_levels, height_tolerance=0.3)
                else:
                    self.section_data = []

                self.update_all_indices()
                self.update_3d_view()
                self.update_section_lines()
                if self.show_central_axis:
                    self.update_central_axis()

                self.data_changed.emit()
                tx.commit()
                
                # Синхронизируем крен с отклонениями секций в конструкторе
                self._sync_tilt_with_blueprint(target_entry, target_offset_mm, current_offset_m * 1000.0)
                
                # Получаем номер секции из target_entry
                section_num = target_entry.get('section_num', None)
                section_num_text = f"№{section_num}" if section_num is not None else ""
                section_num_display = f"{section_num_text} " if section_num_text else ""
                
                self.info_label.setText(
                    f'✓ Секция {section_num_display}Z={section_height:.2f}м локально смещена до крена {target_offset_mm:.2f} мм'
                )
                
                logger.info(
                    "Локальный крен секции %sZ=%.3fм изменён: было %.3f мм, стало %.3f мм",
                    section_num_display,
                    section_height,
                    current_offset_m * 1000.0,
                    target_offset_m * 1000.0,
                )
        except Exception as exc:
            logger.error(f'Ошибка локального крена секции: {exc}', exc_info=True)
            self.info_label.setText(f'❌ Ошибка: {exc}')

    def set_processed_results(self, results: Optional[Dict[str, Any]]):
        """Сохраняет результаты расчёта для визуализации локальных осей."""
        self.processed_results = results
        self.update_coordinate_axes()

    def _update_station_indices(self):
        self._refresh_index_mapping()

        if self.data is None or 'is_station' not in self.data.columns:
            self.station_indices = []
            self.active_station_index = None
            return

        mask = self._build_is_station_mask(self.data['is_station'])
        indices = [idx for idx, flag in mask.items() if bool(flag)]
        self.station_indices = indices

        if not indices:
            self.active_station_index = None
            return

        if self.active_station_index not in indices:
            self.active_station_index = indices[0]

    def set_active_station_index(self, index: Optional[int]):
        if index is None or self.data is None or index not in self.data.index:
            return
        if index not in self.station_indices:
            return
        if self.active_station_index == index:
            return
        self.active_station_index = index
        self.update_coordinate_axes()

    def _refresh_index_mapping(self):
        if self.data is None:
            self._index_to_position = {}
        else:
            try:
                self._index_to_position = {
                    idx: pos for pos, idx in enumerate(self.data.index)
                }
            except Exception:
                self._index_to_position = {}

    def _get_position_from_index(self, index: Any) -> Optional[int]:
        """
        Получить позицию по индексу (point_index или индекс DataFrame).
        
        Использует index_manager для надежной конвертации point_index в позицию.
        
        Args:
            index: Индекс любого типа (point_index, DataFrame index, position)
            
        Returns:
            Позиция (0-based) или None, если не найдена
        """
        if self.data is None:
            return None
        
        # Используем index_manager для нормализации индекса в позицию
        position = self.index_manager.normalize_to_position(index, index_type='auto')
        if position is not None:
            return position
        
        # Fallback: используем старый маппинг для индексов DataFrame
        return self._index_to_position.get(index)

    def _get_index_from_position(self, position: int) -> Optional[Any]:
        if self.data is None:
            return None
        try:
            return self.data.index[position]
        except Exception:
            return None
    
    def _safe_get_point(self, idx: Any, index_type: str = 'position') -> Optional[pd.Series]:
        """
        Безопасное получение точки по любому типу индекса.
        
        Args:
            idx: Индекс точки (позиция, индекс DataFrame или point_index)
            index_type: Тип индекса ('position', 'dataframe_index', 'point_index', 'auto')
            
        Returns:
            Series с данными точки или None, если индекс невалиден
        """
        if self.data is None or self.data.empty:
            return None
        
        try:
            if index_type == 'position':
                return self.index_manager.get_point_by_position(idx)
            elif index_type == 'dataframe_index':
                return self.index_manager.get_point_by_dataframe_index(idx)
            elif index_type == 'point_index':
                return self.index_manager.get_point_by_point_index(idx)
            elif index_type == 'auto':
                # Пробуем автоматически определить тип
                point = self.index_manager.get_point_by_position(idx)
                if point is not None:
                    return point
                point = self.index_manager.get_point_by_point_index(idx)
                if point is not None:
                    return point
                return self.index_manager.get_point_by_dataframe_index(idx)
        except Exception as e:
            logger.debug(f"Ошибка при безопасном получении точки (idx={idx}, type={index_type}): {e}")
            return None
        
        return None
    
    def _validate_selection(self) -> bool:
        """
        Проверить валидность текущего выбора точек.
        
        Returns:
            True, если выбор валиден, False иначе
        """
        if not self.selected_indices:
            return False
        
        if self.data is None or self.data.empty:
            return False
        
        # Проверяем каждую выбранную позицию
        for pos in self.selected_indices:
            if not isinstance(pos, int):
                return False
            if pos < 0 or pos >= len(self.data):
                return False
            if not self.index_manager.validate_index(pos, 'position'):
                return False
        
        return True
    
    def _get_point_index_from_selection(self) -> Optional[int]:
        """
        Получить point_index первой выбранной точки.
        
        Returns:
            point_index или None, если выбор невалиден
        """
        if not self._validate_selection():
            return None
        
        if not self.selected_indices:
            return None
        
        pos = self.selected_indices[0]
        return self.index_manager.find_point_index_by_position(pos)

    def _create_text_item(self, position, text, color=(1.0, 1.0, 1.0, 1.0), font=None, screen_offset=None):
        """Унифицированное создание GLTextItem с учетом совместимости PyQtGraph."""
        try:
            item = ContrastGLTextItem(screen_offset=screen_offset)
            item.setGLOptions('translucent')
            item.setDepthValue(1e6)
            kwargs = {
                'pos': np.array(position, dtype=float),
                'text': str(text),
                'color': self._normalize_text_color(color),
            }
            if font is not None:
                kwargs['font'] = font
            item.setData(**kwargs)
            return item
        except Exception as exc:  # noqa: BLE001
            logger.error("Не удалось создать текстовую метку '%s': %s", text, exc, exc_info=True)
            return None
