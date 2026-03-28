"""
Единая панель конструктора башни с двумя областями:
- Дерево структуры (слева)
- Панель свойств (справа)
3D визуализация отображается в основном окне PointEditor3DWidget
"""

from __future__ import annotations

from typing import Optional, Dict, Any, List
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QPushButton,
    QLabel,
    QMessageBox,
    QTextEdit,
    QGroupBox,
)

from core.tower_generator import TowerBlueprintV2
from core.db.profile_manager import ProfileManager
from gui.tower_structure_tree import TowerStructureTreeWidget
from gui.tower_properties_panel import TowerPropertiesPanel


class UnifiedTowerBuilderPanel(QWidget):
    """
    Единая панель конструктора башни с двумя областями.
    Объединяет дерево структуры и панель свойств.
    3D визуализация отображается в основном окне через сигнал towerVisualizationRequested.
    """
    
    blueprintRequested = pyqtSignal(TowerBlueprintV2)
    referenceModelUpdated = pyqtSignal(TowerBlueprintV2)
    statusMessage = pyqtSignal(str)
    towerVisualizationRequested = pyqtSignal(TowerBlueprintV2)  # Сигнал для запроса визуализации в основном окне
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.profile_manager = ProfileManager()
        self._current_blueprint: Optional[TowerBlueprintV2] = None
        
        # Таймер для отложенного обновления предпросмотра
        self._preview_update_timer = QTimer()
        self._preview_update_timer.setSingleShot(True)
        self._preview_update_timer.timeout.connect(self._update_preview_now)
        
        self._setup_ui()
        self._connect_signals()
    
    def _setup_ui(self) -> None:
        """Настройка интерфейса с тремя областями."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(6)
        
        # Панель инструментов
        self.toolbar = QHBoxLayout()
        self.toolbar.setSpacing(4)
        
        self.generate_btn = QPushButton("Обновить модель")
        self.generate_btn.setToolTip("Обновить вайрфрейм-оверлей в 3D окне без замены данных съёмки")
        self.generate_btn.clicked.connect(self._emit_reference_update)
        self.toolbar.addWidget(self.generate_btn)

        self.generate_data_btn = QPushButton("Создать башню из чертежа...")
        self.generate_data_btn.setToolTip("Сгенерировать синтетические точки (ЗАМЕНЯЕТ данные съёмки)")
        self.generate_data_btn.setStyleSheet("QPushButton { color: #c47a00; font-weight: bold; }")
        self.generate_data_btn.clicked.connect(self._emit_blueprint)
        self.toolbar.addWidget(self.generate_data_btn)
        
        # Кнопка мастера групповых операций
        self.master_btn = QPushButton("Мастер операций")
        self.master_btn.setToolTip("Групповые операции над элементами башни")
        self.master_btn.clicked.connect(self._open_master)
        self.toolbar.addWidget(self.master_btn)
        
        self.toolbar.addStretch()
        
        self.status_label = QLabel("Готов к работе")
        self.status_label.setStyleSheet("color: #666; font-size: 9pt;")
        self.toolbar.addWidget(self.status_label)
        
        main_layout.addLayout(self.toolbar)
        
        # Основной splitter с двумя областями
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_splitter.setChildrenCollapsible(False)
        main_splitter.setHandleWidth(6)
        
        # Левая область: Дерево структуры
        self.structure_tree = TowerStructureTreeWidget()
        self.structure_tree.setMinimumWidth(280)
        self.structure_tree.setMaximumWidth(420)
        main_splitter.addWidget(self.structure_tree)
        
        # Правая область: Панель свойств
        self.properties_panel = TowerPropertiesPanel(self.profile_manager)
        self.properties_panel.setMinimumWidth(350)
        self.properties_panel.setMaximumWidth(500)
        main_splitter.addWidget(self.properties_panel)
        
        # Пропорции: дерево 40%, свойства 60%
        main_splitter.setStretchFactor(0, 2)
        main_splitter.setStretchFactor(1, 3)
        
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
            self.properties_panel.set_blueprint(blueprint)
            # Запросить визуализацию в основном окне
            self.towerVisualizationRequested.emit(blueprint)
            self.statusMessage.emit("Чертёж загружен")
        else:
            self.structure_tree.set_blueprint(None)
            self.properties_panel.set_element(None, {})
            self.properties_panel.set_blueprint(None)
            # Очистить визуализацию в основном окне
            self.towerVisualizationRequested.emit(None)
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
        # Если обновлен весь чертеж
        if property_name == "blueprint_updated":
            self._current_blueprint = value
            self._schedule_preview_update()
            return
        
        # Обновить чертеж и предпросмотр в реальном времени
        if self._current_blueprint:
            self._schedule_preview_update()
    
    def _schedule_preview_update(self) -> None:
        """Запланировать обновление предпросмотра."""
        # Остановить предыдущий таймер и запустить новый
        self._preview_update_timer.stop()
        self._preview_update_timer.start(200)  # 200 мс задержка для плавности
    
    def _update_preview_now(self) -> None:
        """Обновить предпросмотр немедленно."""
        if self._current_blueprint:
            # Обновить все компоненты
            self.structure_tree.set_blueprint(self._current_blueprint)
            self.properties_panel.set_blueprint(self._current_blueprint)
            # Обновить визуализацию в основном окне
            self.towerVisualizationRequested.emit(self._current_blueprint)
    
    def _on_profile_assigned(self, element_type: str, profile_name: str) -> None:
        """Обработка назначения профиля."""
        # Обновить дерево и предпросмотр через отложенное обновление
        if self._current_blueprint:
            self._schedule_preview_update()
    
    def _open_master(self) -> None:
        """Открыть мастер групповых операций."""
        if not self._current_blueprint:
            QMessageBox.warning(self, "Ошибка", "Нет чертежа башни для операций.")
            return
        
        from gui.tower_builder_master import TowerBuilderMaster
        from PyQt6.QtWidgets import QMessageBox
        
        master = TowerBuilderMaster(self._current_blueprint, self.profile_manager, self)
        master.operationCompleted.connect(self._on_master_operation)
        
        if master.exec() == master.DialogCode.Accepted:
            pass
    
    def _on_master_operation(self, operation_data: Dict[str, Any]) -> None:
        """Обработка операции из мастера."""
        from gui.tower_builder_master import TowerBuilderMaster
        
        new_blueprint = TowerBuilderMaster.apply_operation(self._current_blueprint, operation_data)
        self.set_blueprint(new_blueprint)
        self.statusMessage.emit("Групповая операция применена")
    
    def _emit_reference_update(self) -> None:
        """Обновить референсную модель (вайрфрейм оверлей) без замены данных съёмки."""
        if self._current_blueprint:
            self.referenceModelUpdated.emit(self._current_blueprint)
            self.statusMessage.emit("Референсная модель обновлена")
        else:
            self.statusMessage.emit("Нет чертежа для обновления")

    def _emit_blueprint(self) -> None:
        """Сгенерировать синтетические данные из чертежа (ЗАМЕНЯЕТ данные съёмки)."""
        if not self._current_blueprint:
            self.statusMessage.emit("Нет чертежа для построения")
            return
        reply = QMessageBox.warning(
            self,
            "Замена данных",
            "Это действие ЗАМЕНИТ все импортированные данные синтетическими точками.\n"
            "Реальные измерения будут утеряны (отмена через Ctrl+Z).\n\nПродолжить?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.blueprintRequested.emit(self._current_blueprint)
        self.statusMessage.emit("Башня сгенерирована из чертежа")
    
    def get_structure_tree(self) -> TowerStructureTreeWidget:
        """Получить дерево структуры башни."""
        return self.structure_tree
    
    def get_properties_panel(self) -> TowerPropertiesPanel:
        """Получить панель свойств."""
        return self.properties_panel
    
    def get_toolbar(self) -> QHBoxLayout:
        """Получить тулбар с кнопками управления."""
        return self.toolbar
