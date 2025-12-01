"""
Дерево структуры башни с иерархией:
Башня → Части → Секции → Элементы (Пояса, Раскосы, Распорки)
"""

from __future__ import annotations

from typing import Optional, Dict, Any, List
from PyQt6.QtCore import Qt, pyqtSignal, QModelIndex
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QTreeWidget,
    QTreeWidgetItem,
    QMenu,
    QHeaderView,
    QLabel,
    QLineEdit,
    QHBoxLayout,
    QPushButton,
)

from core.tower_generator import TowerBlueprintV2, TowerSegmentSpec, TowerSectionSpec
from core.structure.model import MemberType


class TowerStructureTreeWidget(QWidget):
    """
    Виджет дерева структуры башни.
    Отображает иерархию: Башня → Части → Секции → Элементы
    """
    
    # Сигналы
    elementSelected = pyqtSignal(str, object)  # type, element_data
    elementDoubleClicked = pyqtSignal(str, object)
    
    # Типы элементов для сигналов
    TYPE_TOWER = "tower"
    TYPE_SEGMENT = "segment"
    TYPE_SECTION = "section"
    TYPE_ELEMENT = "element"
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._blueprint: Optional[TowerBlueprintV2] = None
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """Настройка интерфейса дерева."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        
        # Заголовок
        header = QHBoxLayout()
        title = QLabel("Структура башни")
        title.setStyleSheet("font-weight: 600; font-size: 10pt;")
        header.addWidget(title)
        header.addStretch()
        
        # Поиск (заглушка для будущего расширения)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Поиск...")
        self.search_edit.setMaximumWidth(150)
        header.addWidget(self.search_edit)
        
        layout.addLayout(header)
        
        # Дерево
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Элемент", "Тип", "Профиль"])
        self.tree.setRootIsDecorated(True)
        self.tree.setAlternatingRowColors(True)
        self.tree.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        
        # Обработчики событий
        self.tree.itemSelectionChanged.connect(self._on_selection_changed)
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.tree.customContextMenuRequested.connect(self._on_context_menu)
        
        # Настройка колонок
        header_view = self.tree.header()
        header_view.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header_view.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        
        layout.addWidget(self.tree)
        
        # Информационная панель
        info_layout = QHBoxLayout()
        self.info_label = QLabel("Выберите элемент")
        self.info_label.setStyleSheet("color: #666; font-size: 9pt;")
        info_layout.addWidget(self.info_label)
        info_layout.addStretch()
        layout.addLayout(info_layout)
    
    def set_blueprint(self, blueprint: Optional[TowerBlueprintV2]) -> None:
        """Установить чертеж башни для отображения."""
        self._blueprint = blueprint
        self._refresh_tree()
    
    def _refresh_tree(self) -> None:
        """Обновить дерево структуры."""
        self.tree.clear()
        
        if not self._blueprint:
            self.info_label.setText("Нет чертежа")
            return
        
        # Корневой элемент - Башня
        root_item = QTreeWidgetItem(self.tree)
        root_item.setText(0, "Башня")
        root_item.setText(1, "Конструкция")
        root_item.setData(0, Qt.ItemDataRole.UserRole, {"type": self.TYPE_TOWER, "data": self._blueprint})
        root_item.setExpanded(True)
        
        # Добавить части (сегменты)
        for seg_idx, segment in enumerate(self._blueprint.segments):
            seg_item = self._create_segment_item(segment, seg_idx)
            root_item.addChild(seg_item)
        
        # Обновить информацию
        total_height = sum(seg.height for seg in self._blueprint.segments)
        self.info_label.setText(f"Частей: {len(self._blueprint.segments)}, Высота: {total_height:.2f} м")
    
    def _create_segment_item(self, segment: TowerSegmentSpec, index: int) -> QTreeWidgetItem:
        """Создать элемент дерева для части башни."""
        item = QTreeWidgetItem()
        item.setText(0, segment.name)
        item.setText(1, "Часть")
        
        # Информация о профилях
        profile_info = self._get_profile_info(segment.profile_spec)
        if profile_info:
            item.setText(2, profile_info)
        
        item.setData(0, Qt.ItemDataRole.UserRole, {
            "type": self.TYPE_SEGMENT,
            "data": segment,
            "index": index
        })
        item.setExpanded(True)
        
        # Добавить секции
        if segment.sections:
            for sec_idx, section in enumerate(segment.sections):
                sec_item = self._create_section_item(section, sec_idx, segment)
                item.addChild(sec_item)
        else:
            # Если секций нет, создать элементы напрямую
            self._add_element_items(item, segment)
        
        return item
    
    def _create_section_item(self, section: TowerSectionSpec, index: int, segment: TowerSegmentSpec) -> QTreeWidgetItem:
        """Создать элемент дерева для секции."""
        item = QTreeWidgetItem()
        item.setText(0, section.name)
        item.setText(1, "Секция")
        
        # Информация о профилях
        profile_info = self._get_profile_info(section.profile_spec)
        if profile_info:
            item.setText(2, profile_info)
        elif segment.profile_spec:
            profile_info = self._get_profile_info(segment.profile_spec)
            if profile_info:
                item.setText(2, f"({profile_info})")
        
        item.setData(0, Qt.ItemDataRole.UserRole, {
            "type": self.TYPE_SECTION,
            "data": section,
            "segment": segment,
            "index": index
        })
        item.setExpanded(False)
        
        # Добавить элементы (пояса, раскосы, распорки)
        self._add_element_items(item, segment, section)
        
        return item
    
    def _add_element_items(self, parent_item: QTreeWidgetItem, segment: TowerSegmentSpec, section: Optional[TowerSectionSpec] = None) -> None:
        """Добавить элементы (пояса, раскосы, распорки) в дерево."""
        # Определить профили
        profile_spec = section.profile_spec if section and section.profile_spec else segment.profile_spec
        
        leg_profile = self._get_profile_display_name(profile_spec.get("leg_profile"))
        brace_profile = self._get_profile_display_name(profile_spec.get("brace_profile"))
        strut_profile = self._get_profile_display_name(profile_spec.get("strut_profile", brace_profile))
        
        # Пояса
        leg_item = QTreeWidgetItem()
        leg_item.setText(0, "Пояса")
        leg_item.setText(1, "Элементы")
        leg_item.setText(2, leg_profile or "Не задано")
        leg_item.setData(0, Qt.ItemDataRole.UserRole, {
            "type": self.TYPE_ELEMENT,
            "element_type": MemberType.LEG,
            "profile": profile_spec.get("leg_profile"),
            "segment": segment,
            "section": section
        })
        parent_item.addChild(leg_item)
        
        # Раскосы
        brace_item = QTreeWidgetItem()
        brace_item.setText(0, "Раскосы")
        brace_item.setText(1, "Элементы")
        brace_item.setText(2, brace_profile or "Не задано")
        brace_item.setData(0, Qt.ItemDataRole.UserRole, {
            "type": self.TYPE_ELEMENT,
            "element_type": MemberType.BRACE,
            "profile": profile_spec.get("brace_profile"),
            "segment": segment,
            "section": section
        })
        parent_item.addChild(brace_item)
        
        # Распорки
        strut_item = QTreeWidgetItem()
        strut_item.setText(0, "Распорки")
        strut_item.setText(1, "Элементы")
        strut_item.setText(2, strut_profile or "Не задано")
        strut_item.setData(0, Qt.ItemDataRole.UserRole, {
            "type": self.TYPE_ELEMENT,
            "element_type": MemberType.STRUT,
            "profile": profile_spec.get("strut_profile", profile_spec.get("brace_profile")),
            "segment": segment,
            "section": section
        })
        parent_item.addChild(strut_item)
    
    def _get_profile_info(self, profile_spec: Dict[str, Any]) -> Optional[str]:
        """Получить строковое представление профилей из спецификации."""
        if not profile_spec:
            return None
        
        parts = []
        if profile_spec.get("leg_profile") and profile_spec["leg_profile"] != "Не задано":
            parts.append(f"Пояса: {self._get_profile_display_name(profile_spec['leg_profile'])}")
        if profile_spec.get("brace_profile") and profile_spec["brace_profile"] != "Не задано":
            parts.append(f"Раскосы: {self._get_profile_display_name(profile_spec['brace_profile'])}")
        
        return ", ".join(parts) if parts else None
    
    def _get_profile_display_name(self, profile_name: Optional[str]) -> Optional[str]:
        """Получить отображаемое имя профиля."""
        if not profile_name or profile_name == "Не задано":
            return None
        # Если это уже полное имя (тип + обозначение + стандарт), вернуть как есть
        return profile_name
    
    def _on_selection_changed(self) -> None:
        """Обработка изменения выбора в дереве."""
        current_item = self.tree.currentItem()
        if not current_item:
            return
        
        data = current_item.data(0, Qt.ItemDataRole.UserRole)
        if data:
            self.elementSelected.emit(data["type"], data)
    
    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        """Обработка двойного клика по элементу."""
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data:
            self.elementDoubleClicked.emit(data["type"], data)
    
    def _on_context_menu(self, position) -> None:
        """Обработка контекстного меню."""
        item = self.tree.itemAt(position)
        if not item:
            return
        
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        
        menu = QMenu(self)
        
        # Опции в зависимости от типа элемента
        if data["type"] == self.TYPE_SEGMENT:
            menu.addAction("Добавить секцию", lambda: self._add_section(data))
            menu.addAction("Удалить часть", lambda: self._remove_segment(data))
            menu.addAction("Копировать часть", lambda: self._copy_segment(data))
        elif data["type"] == self.TYPE_SECTION:
            menu.addAction("Удалить секцию", lambda: self._remove_section(data))
            menu.addAction("Копировать секцию", lambda: self._copy_section(data))
        elif data["type"] == self.TYPE_ELEMENT:
            menu.addAction("Назначить профиль", lambda: self._assign_profile(data))
            menu.addAction("Скопировать профиль", lambda: self._copy_profile(data))
        
        menu.exec(self.tree.mapToGlobal(position))
    
    def _add_section(self, data: Dict[str, Any]) -> None:
        """Добавить секцию (заглушка)."""
        # Будет реализовано позже
        pass
    
    def _remove_segment(self, data: Dict[str, Any]) -> None:
        """Удалить часть (заглушка)."""
        # Будет реализовано позже
        pass
    
    def _copy_segment(self, data: Dict[str, Any]) -> None:
        """Копировать часть (заглушка)."""
        # Будет реализовано позже
        pass
    
    def _remove_section(self, data: Dict[str, Any]) -> None:
        """Удалить секцию (заглушка)."""
        # Будет реализовано позже
        pass
    
    def _copy_section(self, data: Dict[str, Any]) -> None:
        """Копировать секцию (заглушка)."""
        # Будет реализовано позже
        pass
    
    def _assign_profile(self, data: Dict[str, Any]) -> None:
        """Назначить профиль элементу (заглушка)."""
        # Будет реализовано позже
        pass
    
    def _copy_profile(self, data: Dict[str, Any]) -> None:
        """Скопировать профиль (заглушка)."""
        # Будет реализовано позже
        pass
