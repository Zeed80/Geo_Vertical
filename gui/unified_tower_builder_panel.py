"""
Единая панель конструктора башни с тремя областями:
- Дерево структуры (слева)
- 3D визуализация (центр)
- Панель свойств (справа)
"""

from __future__ import annotations

from typing import Optional, Dict, Any, List
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QPushButton,
    QLabel,
)

from core.tower_generator import TowerBlueprintV2
from core.db.profile_manager import ProfileManager
from gui.enhanced_tower_preview import EnhancedTowerPreview3D
from gui.tower_structure_tree import TowerStructureTreeWidget
from gui.tower_properties_panel import TowerPropertiesPanel


class UnifiedTowerBuilderPanel(QWidget):
    """
    Единая панель конструктора башни с тремя областями.
    Объединяет дерево структуры, 3D визуализацию и панель свойств.
    """
    
    blueprintRequested = pyqtSignal(TowerBlueprintV2)
    statusMessage = pyqtSignal(str)
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.profile_manager = ProfileManager()
        self._current_blueprint: Optional[TowerBlueprintV2] = None
        
        self._setup_ui()
        self._connect_signals()
    
    def _setup_ui(self) -> None:
        """Настройка интерфейса с тремя областями."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(4)
        
        # Панель инструментов
        toolbar = QHBoxLayout()
        toolbar.setSpacing(4)
        
        self.generate_btn = QPushButton("Построить башню")
        self.generate_btn.clicked.connect(self._emit_blueprint)
        toolbar.addWidget(self.generate_btn)
        
        toolbar.addStretch()
        
        self.status_label = QLabel("Готов к работе")
        self.status_label.setStyleSheet("color: #666; font-size: 9pt;")
        toolbar.addWidget(self.status_label)
        
        main_layout.addLayout(toolbar)
        
        # Основной splitter с тремя областями
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_splitter.setChildrenCollapsible(False)
        main_splitter.setHandleWidth(6)
        
        # Левая область: Дерево структуры
        self.structure_tree = TowerStructureTreeWidget()
        self.structure_tree.setMinimumWidth(250)
        self.structure_tree.setMaximumWidth(400)
        main_splitter.addWidget(self.structure_tree)
        
        # Центральная область: 3D визуализация
        self.preview_3d = EnhancedTowerPreview3D()
        main_splitter.addWidget(self.preview_3d)
        
        # Правая область: Панель свойств
        self.properties_panel = TowerPropertiesPanel(self.profile_manager)
        self.properties_panel.setMinimumWidth(300)
        self.properties_panel.setMaximumWidth(450)
        main_splitter.addWidget(self.properties_panel)
        
        # Пропорции: дерево 20%, 3D 50%, свойства 30%
        main_splitter.setStretchFactor(0, 2)
        main_splitter.setStretchFactor(1, 5)
        main_splitter.setStretchFactor(2, 3)
        
        main_layout.addWidget(main_splitter, stretch=1)
        
        self._main_splitter = main_splitter
    
    def _connect_signals(self) -> None:
        """Подключить сигналы между компонентами."""
        # Дерево → Панель свойств
        self.structure_tree.elementSelected.connect(self._on_element_selected)
        self.structure_tree.elementDoubleClicked.connect(self._on_element_double_clicked)
        
        # Панель свойств → обновление чертежа
        self.properties_panel.propertyChanged.connect(self._on_property_changed)
        self.properties_panel.profileAssigned.connect(self._on_profile_assigned)
    
    def set_blueprint(self, blueprint: Optional[TowerBlueprintV2]) -> None:
        """Установить чертеж башни для редактирования."""
        self._current_blueprint = blueprint
        if blueprint:
            # Обновить все компоненты
            self.structure_tree.set_blueprint(blueprint)
            self.preview_3d.set_blueprint(blueprint)
            self.properties_panel.set_blueprint(blueprint)
            self.statusMessage.emit("Чертёж загружен")
        else:
            self.structure_tree.set_blueprint(None)
            self.preview_3d.reset()
            self.properties_panel.set_element(None, {})
            self.properties_panel.set_blueprint(None)
            self.statusMessage.emit("Чертёж очищен")
    
    def get_blueprint(self) -> Optional[TowerBlueprintV2]:
        """Получить текущий чертеж башни."""
        return self._current_blueprint
    
    def _on_element_selected(self, element_type: str, element_data: Dict[str, Any]) -> None:
        """Обработка выбора элемента в дереве."""
        self.properties_panel.set_element(element_type, element_data)
    
    def _on_element_double_clicked(self, element_type: str, element_data: Dict[str, Any]) -> None:
        """Обработка двойного клика по элементу."""
        # Переключиться на вкладку свойств соответствующего типа
        if element_type == "element":
            self.properties_panel.tabs.setCurrentIndex(1)  # Вкладка "Профили"
        elif element_type in ("segment", "section"):
            self.properties_panel.tabs.setCurrentIndex(2)  # Вкладка "Решетка"
    
    def _on_property_changed(self, property_name: str, value: Any) -> None:
        """Обработка изменения свойства."""
        # Обновить чертеж и предпросмотр
        if self._current_blueprint:
            # TODO: Реализовать обновление чертежа
            self.preview_3d.set_blueprint(self._current_blueprint)
    
    def _on_profile_assigned(self, element_type: str, profile_name: str) -> None:
        """Обработка назначения профиля."""
        # Обновить дерево и предпросмотр
        if self._current_blueprint:
            self.structure_tree.set_blueprint(self._current_blueprint)
            self.preview_3d.set_blueprint(self._current_blueprint)
    
    def _emit_blueprint(self) -> None:
        """Эмитировать сигнал с текущим чертежом."""
        if self._current_blueprint:
            self.blueprintRequested.emit(self._current_blueprint)
            self.statusMessage.emit("Чертёж башни обновлён")
        else:
            self.statusMessage.emit("Нет чертежа для построения")
