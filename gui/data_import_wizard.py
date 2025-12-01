"""
Мастер импорта данных с фильтрацией точек и назначением поясов
"""

from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QListWidget, QListWidgetItem, QSpinBox,
                             QGroupBox, QMessageBox, QInputDialog, QSplitter,
                             QTableWidget, QTableWidgetItem, QHeaderView, QWidget,
                             QFormLayout, QComboBox, QAbstractItemView, QRadioButton,
                             QButtonGroup, QDoubleSpinBox, QScrollArea)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QDrag, QColor
import pandas as pd
import numpy as np
import logging
import json
from typing import Any, Dict, List

from gui.ui_helpers import apply_compact_button_style, is_dark_theme_enabled

logger = logging.getLogger(__name__)


class DraggableListWidget(QListWidget):
    """Список с поддержкой drag & drop"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)


class DataImportWizard(QDialog):
    """
    Мастер импорта данных с двумя этапами:
    1. Выбор точек (галочки)
    2. Распределение по поясам (drag & drop + кнопки)
    """
    
    def __init__(self, data: pd.DataFrame, saved_settings: dict = None, parent=None):
        super().__init__(parent)
        self.raw_data = data.copy()
        self.filtered_data = None
        self.current_step = 1
        self.belt_count = 4
        self.saved_settings = saved_settings  # Сохраненные настройки сортировки
        self.sorting_settings = None  # Настройки для сохранения
        self.cached_selected_points = None  # Кэш выбранных точек с первого шага
        self.station_point_idx = None  # Индекс точки стояния тахеометра
        self.dark_theme_enabled = is_dark_theme_enabled()
        self.point_part_memberships = {}  # Карта принадлежности точек частям башни
        
        # Параметры составной башни
        self.tower_type = "simple"  # "simple" или "composite"
        # Список частей: [{"part_number": 1, "shape": "prism", "faces": 4, "split_height": None}, ...]
        # split_height - высота начала этой части (для первой части = None, для остальных - высота раздвоения)
        self.tower_parts = []
        self.split_height_tolerance = 1.0  # Разброс высоты при определении частей (метры)
        
        # Пытаемся загрузить blueprint из parent (MainWindow)
        self._load_blueprint_from_parent()
        
        self.setWindowTitle('Мастер импорта данных')
        self.setMinimumSize(900, 600)
        
        self.init_ui()
        self.show_step_1()
    
    def init_ui(self):
        """Инициализация интерфейса"""
        layout = QVBoxLayout()
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)
        self.setLayout(layout)
        
        # Заголовок
        self.title_label = QLabel()
        self.title_label.setStyleSheet('font-size: 12pt; font-weight: 600; padding: 4px;')
        layout.addWidget(self.title_label)
        
        # Контейнер для шагов
        self.steps_container = QWidget()
        self.steps_layout = QVBoxLayout()
        self.steps_layout.setContentsMargins(4, 4, 4, 4)
        self.steps_layout.setSpacing(4)
        self.steps_container.setLayout(self.steps_layout)
        layout.addWidget(self.steps_container)
        
        # Кнопки навигации
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(4)
        
        self.back_btn = QPushButton('⬅ Назад')
        self.back_btn.clicked.connect(self.go_back)
        self.back_btn.setEnabled(False)
        apply_compact_button_style(self.back_btn, width=104, min_height=34)
        buttons_layout.addWidget(self.back_btn)
        
        buttons_layout.addStretch()
        
        self.cancel_btn = QPushButton('Отмена')
        self.cancel_btn.clicked.connect(self.reject)
        apply_compact_button_style(self.cancel_btn, width=96, min_height=34)
        buttons_layout.addWidget(self.cancel_btn)
        
        self.next_btn = QPushButton('Далее ➡')
        self.next_btn.clicked.connect(self.go_next)
        apply_compact_button_style(self.next_btn, width=120, min_height=34)
        buttons_layout.addWidget(self.next_btn)
        
        layout.addLayout(buttons_layout)

    def _info_box_style(self) -> str:
        """Возвращает стиль инфобокса в соответствии с темой."""
        if self.dark_theme_enabled:
            return (
                'padding: 6px; border-radius: 4px; font-size: 9pt; '
                'background-color: #2c2f34; border: 1px solid #3f3f43; '
                'color: #f0f0f0;'
            )
        return (
            'padding: 6px; border-radius: 4px; font-size: 9pt; '
            'background-color: #E3F2FD; border: 1px solid #90CAF9; '
            'color: #0d1b2a;'
        )
    
    def clear_steps_container(self):
        """Очистка контейнера шагов"""
        while self.steps_layout.count():
            item = self.steps_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
    
    def show_step_1(self):
        """Шаг 1: Выбор точек"""
        self.current_step = 1
        self.title_label.setText('Шаг 1 из 2: Выбор точек для обработки')
        self.back_btn.setEnabled(False)
        self.next_btn.setText('Далее ➡')
        
        self.clear_steps_container()
        
        # Запрос количества поясов
        belt_layout = QHBoxLayout()
        belt_layout.setSpacing(4)
        belt_label = QLabel('Количество поясов:')
        belt_label.setStyleSheet('font-size: 9pt;')
        belt_layout.addWidget(belt_label)
        
        self.belt_spin = QSpinBox()
        self.belt_spin.setMinimum(1)
        self.belt_spin.setMaximum(50)
        self.belt_spin.setStyleSheet('font-size: 9pt; padding: 2px;')
        
        # Загружаем количество поясов из сохраненных настроек
        if self.saved_settings and 'belt_count' in self.saved_settings:
            self.belt_count = self.saved_settings['belt_count']
            logger.info(f"DataImportWizard: Загружено количество поясов из настроек: {self.belt_count}")
        else:
            logger.info(f"DataImportWizard: Используется значение по умолчанию: {self.belt_count}")
        
        # Если количество поясов передано из второго импорта, делаем поле только для чтения
        if self.saved_settings and 'belt_count' in self.saved_settings and self.saved_settings.get('read_only', False):
            self.belt_spin.setEnabled(False)
            self.belt_spin.setToolTip('Количество поясов определено из первого импорта и не может быть изменено')
            logger.info(f"DataImportWizard: Поле количества поясов установлено только для чтения")
        
        self.belt_spin.setValue(self.belt_count)
        belt_layout.addWidget(self.belt_spin)
        belt_layout.addStretch()
        
        self.steps_layout.addLayout(belt_layout)
        
        # Выбор типа башни
        tower_type_group = QGroupBox('Тип башни')
        tower_type_group.setStyleSheet('QGroupBox { font-size: 9pt; margin-top: 4px; } QGroupBox::title { subcontrol-origin: margin; left: 6px; padding: 0 4px; }')
        tower_type_layout = QVBoxLayout()
        tower_type_layout.setContentsMargins(6, 8, 6, 6)
        tower_type_layout.setSpacing(3)
        
        self.tower_type_group = QButtonGroup(self)
        self.simple_tower_radio = QRadioButton('Обычная башня')
        self.simple_tower_radio.setStyleSheet('font-size: 9pt; padding: 2px;')
        self.composite_tower_radio = QRadioButton('Составная башня')
        self.composite_tower_radio.setStyleSheet('font-size: 9pt; padding: 2px;')
        self.simple_tower_radio.setChecked(True)
        self.tower_type_group.addButton(self.simple_tower_radio, 0)
        self.tower_type_group.addButton(self.composite_tower_radio, 1)
        
        tower_type_layout.addWidget(self.simple_tower_radio)
        tower_type_layout.addWidget(self.composite_tower_radio)
        
        # Загружаем тип башни из сохраненных настроек
        if self.saved_settings and 'tower_type' in self.saved_settings:
            tower_type = self.saved_settings['tower_type']
            if tower_type == 'composite':
                self.composite_tower_radio.setChecked(True)
                self.tower_type = 'composite'
            else:
                self.simple_tower_radio.setChecked(True)
                self.tower_type = 'simple'
        
        self.simple_tower_radio.toggled.connect(self._on_tower_type_changed)
        self.composite_tower_radio.toggled.connect(self._on_tower_type_changed)
        
        tower_type_group.setLayout(tower_type_layout)
        self.steps_layout.addWidget(tower_type_group)
        
        # Контейнер для настроек составной башни с прокруткой
        self.composite_settings_scroll = QScrollArea()
        self.composite_settings_scroll.setWidgetResizable(True)
        self.composite_settings_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.composite_settings_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.composite_settings_scroll.setMinimumHeight(150)
        self.composite_settings_scroll.setMaximumHeight(400)
        
        self.composite_settings_widget = QWidget()
        self.composite_settings_layout = QVBoxLayout()
        self.composite_settings_layout.setContentsMargins(2, 2, 2, 2)
        self.composite_settings_layout.setSpacing(3)
        self.composite_settings_widget.setLayout(self.composite_settings_layout)
        
        self.composite_settings_scroll.setWidget(self.composite_settings_widget)
        self.composite_settings_scroll.setVisible(self.tower_type == 'composite')
        self.steps_layout.addWidget(self.composite_settings_scroll)
        
        # Инициализация настроек составной башни
        self._init_composite_tower_settings()
        
        # Описание
        info_label = QLabel('Отметьте галочками точки, которые нужно обработать. '
                            'Снимите галочки с точек вспомогательного оборудования.')
        info_label.setWordWrap(True)
        info_label.setStyleSheet(self._info_box_style())
        self.steps_layout.addWidget(info_label)
        
        # Кнопки выбора всех/снятия всех
        selection_layout = QHBoxLayout()
        selection_layout.setSpacing(4)
        
        select_all_btn = QPushButton('✓ Все')
        select_all_btn.clicked.connect(self.select_all_points)
        apply_compact_button_style(select_all_btn, width=70, min_height=28)
        selection_layout.addWidget(select_all_btn)
        
        deselect_all_btn = QPushButton('✗ Снять')
        deselect_all_btn.clicked.connect(self.deselect_all_points)
        apply_compact_button_style(deselect_all_btn, width=70, min_height=28)
        selection_layout.addWidget(deselect_all_btn)
        
        selection_layout.addStretch()
        
        self.selected_count_label = QLabel()
        self.selected_count_label.setStyleSheet('font-size: 9pt; padding: 2px;')
        self.update_selected_count()
        selection_layout.addWidget(self.selected_count_label)
        
        self.steps_layout.addLayout(selection_layout)
        
        # Список точек с галочками
        self.points_list = QListWidget()
        self.points_list.setStyleSheet('''
            QListWidget::item {
                padding: 3px;
                font-size: 9pt;
                min-height: 20px;
            }
            QListWidget::item:selected {
                background-color: #3daee9;
            }
        ''')
        self.points_list.itemChanged.connect(self.update_selected_count)
        
        # Получаем список исключенных точек из сохраненных настроек
        excluded_points = set()
        if self.saved_settings and 'excluded_points' in self.saved_settings:
            excluded_points = set(self.saved_settings['excluded_points'])
        
        for idx, row in self.raw_data.iterrows():
            name = row.get('name', f'Точка {idx+1}')
            z = row.get('z', 0)
            item_text = f"{name} (Z = {z:.3f} м)"
            
            item = QListWidgetItem(item_text)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            
            # Устанавливаем галочку на основе сохраненных настроек
            if idx in excluded_points:
                item.setCheckState(Qt.CheckState.Unchecked)
            else:
                item.setCheckState(Qt.CheckState.Checked)
            
            item.setData(Qt.ItemDataRole.UserRole, idx)  # Сохраняем индекс
            
            self.points_list.addItem(item)
        
        # Логируем количество точек
        total_points = self.raw_data.shape[0]
        selected_points = total_points - len(excluded_points)
        logger.info(f"Шаг 1: Всего {total_points} точек, выбрано {selected_points}, исключено {len(excluded_points)}")
        if excluded_points:
            logger.info(f"Исключенные точки (индексы): {sorted(excluded_points)}")
        
        self.steps_layout.addWidget(self.points_list)
    
    def _on_tower_type_changed(self):
        """Обработчик изменения типа башни"""
        if self.simple_tower_radio.isChecked():
            self.tower_type = "simple"
        else:
            self.tower_type = "composite"
        self.composite_settings_scroll.setVisible(self.tower_type == 'composite')
        
        # Если переключились на составную башню, инициализируем настройки
        if self.tower_type == 'composite':
            self._init_composite_tower_settings()
        
        logger.info(f"Тип башни изменен на: {self.tower_type}")
    
    def _init_composite_tower_settings(self):
        """Инициализация настроек составной башни"""
        # Очищаем предыдущие настройки
        while self.composite_settings_layout.count():
            item = self.composite_settings_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        if self.tower_type != 'composite':
            return
        
        # Загружаем настройки из saved_settings
        if self.saved_settings:
            if 'tower_parts' in self.saved_settings and self.saved_settings['tower_parts']:
                self.tower_parts = self.saved_settings['tower_parts'].copy()
            if 'split_height_tolerance' in self.saved_settings:
                self.split_height_tolerance = self.saved_settings['split_height_tolerance']
            else:
                self.split_height_tolerance = 1.0  # Значение по умолчанию
        
        # Если настройки не загружены, инициализация по умолчанию
        if not self.tower_parts:
            self.tower_parts = [
                {"part_number": 1, "shape": "prism", "faces": 4, "split_height": None}
            ]
        
        self._update_composite_settings_ui()
    
    def _auto_detect_split_height(self) -> float:
        """Автоматическое определение высоты раздвоения"""
        try:
            selected_points = self.get_selected_points()
            if selected_points.empty or len(selected_points) < 6:
                return None
            
            # Исключаем точки standing
            if 'is_station' in selected_points.columns:
                selected_points = selected_points[~selected_points['is_station'].fillna(False).astype(bool)]
            
            if selected_points.empty:
                return None
            
            z_values = selected_points['z'].values
            z_min = z_values.min()
            z_max = z_values.max()
            z_range = z_max - z_min
            
            if z_range < 1.0:  # Слишком маленький диапазон
                return None
            
            # Анализируем распределение точек по высоте
            # Ищем резкое изменение количества точек на уровне
            num_bins = max(10, min(50, len(selected_points) // 5))
            hist, bin_edges = np.histogram(z_values, bins=num_bins)
            
            # Ищем локальный минимум в распределении (место раздвоения)
            # Обычно это место, где количество точек резко уменьшается
            min_idx = np.argmin(hist[1:-1]) + 1  # Пропускаем края
            if min_idx < len(bin_edges) - 1:
                split_height = (bin_edges[min_idx] + bin_edges[min_idx + 1]) / 2.0
                
                # Проверяем, что высота в разумных пределах
                if z_min < split_height < z_max:
                    logger.info(f"Автоопределена высота раздвоения: {split_height:.3f} м")
                    return float(split_height)
            
            # Альтернативный метод: медиана высот
            split_height = np.median(z_values)
            logger.info(f"Использована медиана высот для раздвоения: {split_height:.3f} м")
            return float(split_height)
            
        except Exception as e:
            logger.warning(f"Ошибка при автоопределении высоты раздвоения: {e}")
            return None
    
    def _update_composite_settings_ui(self):
        """Обновление UI настроек составной башни"""
        # Очищаем предыдущие элементы
        while self.composite_settings_layout.count():
            item = self.composite_settings_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        if self.tower_type != 'composite':
            return
        
        # Группа настроек частей
        parts_group = QGroupBox('Настройки частей башни')
        parts_group.setStyleSheet('QGroupBox { font-size: 9pt; margin-top: 4px; } QGroupBox::title { subcontrol-origin: margin; left: 6px; padding: 0 4px; }')
        parts_layout = QVBoxLayout()
        parts_layout.setContentsMargins(4, 8, 4, 4)
        parts_layout.setSpacing(3)
        
        # Отображаем все части
        for part_idx, part in enumerate(self.tower_parts):
            part_num = part_idx + 1
            part_group = QGroupBox(f'Часть {part_num}')
            part_group.setStyleSheet('QGroupBox { font-size: 9pt; margin-top: 4px; } QGroupBox::title { subcontrol-origin: margin; left: 6px; padding: 0 4px; }')
            part_layout = QFormLayout()
            part_layout.setContentsMargins(4, 8, 4, 4)
            part_layout.setSpacing(3)
            part_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
            
            # Форма
            shape_combo = QComboBox()
            shape_combo.setStyleSheet('font-size: 9pt; padding: 2px;')
            shape_combo.addItem('Призма', 'prism')
            shape_combo.addItem('Усеченная пирамида', 'truncated_pyramid')
            shape_combo.setCurrentIndex(shape_combo.findData(part.get('shape', 'prism')))
            shape_combo.currentIndexChanged.connect(
                lambda idx, pn=part_num: self._update_part_param(pn, 'shape', shape_combo.currentData())
            )
            shape_label = QLabel('Форма:')
            shape_label.setStyleSheet('font-size: 9pt;')
            part_layout.addRow(shape_label, shape_combo)
            
            # Количество поясов
            faces_spin = QSpinBox()
            faces_spin.setStyleSheet('font-size: 9pt; padding: 2px;')
            faces_spin.setRange(3, 64)
            faces_spin.setValue(part.get('faces', 4))
            faces_spin.valueChanged.connect(
                lambda val, pn=part_num: self._update_part_param(pn, 'faces', val)
            )
            faces_label = QLabel('Граней:')
            faces_label.setStyleSheet('font-size: 9pt;')
            part_layout.addRow(faces_label, faces_spin)
            
            # Высота начала части (для первой части не показываем, для остальных - высота раздвоения)
            if part_num > 1:
                split_height_spin = QDoubleSpinBox()
                split_height_spin.setStyleSheet('font-size: 9pt; padding: 2px;')
                split_height_spin.setRange(0.1, 1000.0)
                split_height_spin.setDecimals(3)
                split_height_spin.setSuffix(' м')
                split_height = part.get('split_height')
                if split_height is not None:
                    split_height_spin.setValue(split_height)
                else:
                    # Автоопределение для первой дополнительной части
                    if part_num == 2:
                        auto_height = self._auto_detect_split_height()
                        if auto_height is not None:
                            split_height_spin.setValue(auto_height)
                            self._update_part_param(part_num, 'split_height', auto_height)
                split_height_spin.valueChanged.connect(
                    lambda val, pn=part_num: self._update_part_param(pn, 'split_height', val)
                )
                height_label = QLabel('Высота:')
                height_label.setStyleSheet('font-size: 9pt;')
                part_layout.addRow(height_label, split_height_spin)
                
                # Кнопка автоопределения (только для второй части)
                if part_num == 2:
                    auto_detect_btn = QPushButton('🔄 Авто')
                    auto_detect_btn.setStyleSheet('font-size: 9pt; padding: 2px;')
                    auto_detect_btn.clicked.connect(
                        lambda checked, spin=split_height_spin: self._on_auto_detect_clicked(spin)
                    )
                    apply_compact_button_style(auto_detect_btn, width=70, min_height=24)
                    part_layout.addRow('', auto_detect_btn)
            
            # Кнопка удаления части (нельзя удалить первую часть)
            if part_num > 1:
                delete_btn = QPushButton('🗑 Удалить')
                delete_btn.setStyleSheet('font-size: 9pt; padding: 2px;')
                delete_btn.clicked.connect(lambda checked, pn=part_num: self._remove_part(pn))
                apply_compact_button_style(delete_btn, width=70, min_height=24)
                part_layout.addRow('', delete_btn)
            
            part_group.setLayout(part_layout)
            parts_layout.addWidget(part_group)
        
        # Разброс высоты (общий для всех частей)
        tolerance_group = QGroupBox('Общие настройки')
        tolerance_group.setStyleSheet('QGroupBox { font-size: 9pt; margin-top: 4px; } QGroupBox::title { subcontrol-origin: margin; left: 6px; padding: 0 4px; }')
        tolerance_layout = QFormLayout()
        tolerance_layout.setContentsMargins(4, 8, 4, 4)
        tolerance_layout.setSpacing(3)
        tolerance_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        tolerance_spin = QDoubleSpinBox()
        tolerance_spin.setStyleSheet('font-size: 9pt; padding: 2px;')
        tolerance_spin.setRange(0.1, 5.0)
        tolerance_spin.setDecimals(2)
        tolerance_spin.setSuffix(' м')
        tolerance_spin.setValue(self.split_height_tolerance)
        tolerance_spin.setSingleStep(0.1)
        tolerance_spin.setToolTip('Учитывается при определении принадлежности точки к части башни.\n'
                                 'Точка относится к части, если её высота попадает в диапазон:\n'
                                 '[высота_начала_части - разброс, высота_начала_следующей_части + разброс]')
        tolerance_spin.valueChanged.connect(lambda val: setattr(self, 'split_height_tolerance', val))
        tolerance_label = QLabel('Разброс:')
        tolerance_label.setStyleSheet('font-size: 9pt;')
        tolerance_layout.addRow(tolerance_label, tolerance_spin)
        tolerance_group.setLayout(tolerance_layout)
        parts_layout.addWidget(tolerance_group)
        
        # Кнопка добавления новой части
        add_part_btn = QPushButton('➕ Добавить часть')
        add_part_btn.setStyleSheet('font-size: 9pt; padding: 2px;')
        add_part_btn.clicked.connect(self._add_new_part)
        apply_compact_button_style(add_part_btn, width=120, min_height=28)
        parts_layout.addWidget(add_part_btn)
        
        parts_group.setLayout(parts_layout)
        self.composite_settings_layout.addWidget(parts_group)
        
        # Обновляем размеры виджета после добавления элементов
        # Используем QTimer для отложенного обновления, чтобы гарантировать правильный расчет размеров
        QTimer.singleShot(0, lambda: (
            self.composite_settings_widget.adjustSize(),
            self.composite_settings_widget.updateGeometry(),
            self.composite_settings_scroll.updateGeometry(),
            self.composite_settings_scroll.update()
        ))
    
    def _group_points_by_belts(self, points_list: pd.DataFrame, indices: list, num_belts: int, station_idx: int = None) -> list:
        """Группирует точки по поясам (граням) на основе углового распределения вокруг центра
        
        Алгоритм:
        1. Группирует точки по высоте (секции)
        2. Внутри каждой секции группирует точки по углу вокруг центра (пояса/грани)
        
        Args:
            points_list: DataFrame с точками (должен содержать колонки x, y, z)
            indices: Список индексов точек для группировки
            num_belts: Количество поясов (граней)
            station_idx: Индекс точки standing для исключения (опционально)
        
        Returns:
            Список списков индексов точек для каждого пояса
        """
        if len(indices) == 0:
            return [[] for _ in range(num_belts)]
        
        if num_belts <= 0:
            return [indices]
        
        # Получаем точки по индексам
        # Обрабатываем виртуальные индексы (дубликаты точек на границе)
        real_indices = []
        for idx in indices:
            if isinstance(idx, str) and '_part' in idx:
                # Виртуальный индекс - извлекаем оригинальный для проверки standing
                original_idx = int(idx.split('_part')[0])
                if original_idx != station_idx:
                    real_indices.append(idx)
            else:
                # Реальный индекс
                if idx != station_idx:
                    real_indices.append(idx)
        
        indices = real_indices
        
        # Получаем точки по индексам
        points_df = points_list.loc[indices].copy()
        
        # Исключаем точку standing, если она есть (по флагу is_station)
        if 'is_station' in points_df.columns:
            station_mask = points_df['is_station'].fillna(False).astype(bool)
            points_df = points_df[~station_mask]
            indices = points_df.index.tolist()
        
        if len(indices) == 0:
            return [[] for _ in range(num_belts)]
        
        # Шаг 1: Группируем точки по высоте (секции) с допуском 0.3 м
        height_tolerance = 0.3
        sections = {}
        for idx in indices:
            z = points_list.loc[idx, 'z']
            # Ищем существующую секцию или создаем новую
            found_section = None
            for section_z in sections.keys():
                if abs(z - section_z) <= height_tolerance:
                    found_section = section_z
                    break
            
            if found_section is not None:
                sections[found_section].append(idx)
            else:
                sections[z] = [idx]
        
        # Шаг 2: Внутри каждой секции группируем точки по углу вокруг центра (пояса)
        belts = [[] for _ in range(num_belts)]
        
        for section_z, section_indices in sections.items():
            if len(section_indices) == 0:
                continue
            
            # Вычисляем центр секции в плоскости XY
            section_points = points_list.loc[section_indices]
            center_x = section_points['x'].mean()
            center_y = section_points['y'].mean()
            
            # Вычисляем углы всех точек секции относительно центра
            angles_with_indices = []
            for idx in section_indices:
                x = points_list.loc[idx, 'x']
                y = points_list.loc[idx, 'y']
                # Угол в диапазоне [0, 2π]
                angle = np.arctan2(y - center_y, x - center_x)
                if angle < 0:
                    angle += 2 * np.pi
                angles_with_indices.append((angle, idx))
            
            # Сортируем по углу
            angles_with_indices.sort(key=lambda x: x[0])
            
            # Распределяем точки по поясам на основе угла
            angle_per_belt = 2 * np.pi / num_belts
            
            for angle, idx in angles_with_indices:
                # Определяем номер пояса на основе угла
                belt_idx = int(angle / angle_per_belt)
                # Ограничиваем диапазон
                belt_idx = min(belt_idx, num_belts - 1)
                belts[belt_idx].append(idx)
        
        return belts
    
    def _determine_point_part(self, z: float, split_heights: list) -> int:
        """Определяет принадлежность точки к части башни по высоте
        
        Args:
            z: Высота точки
            split_heights: Список высот начала частей (начиная со второй части)
        
        Returns:
            Номер части (начиная с 1)
        """
        parts = self._determine_point_parts(z, split_heights)
        return parts[0]  # Возвращаем первую часть для обратной совместимости
    
    def _determine_point_parts(self, z: float, split_heights: list) -> list:
        """Определяет принадлежность точки к частям башни по высоте
        Точки на границе могут принадлежать нескольким частям
        
        Args:
            z: Высота точки
            split_heights: Список высот начала частей (начиная со второй части)
        
        Returns:
            Список номеров частей (начиная с 1), к которым принадлежит точка
        """
        if not split_heights:
            return [1]
        
        sorted_heights = sorted(split_heights)
        tolerance = self.split_height_tolerance
        total_parts = len(sorted_heights) + 1
        current_part = 1
        
        for idx, split_height in enumerate(sorted_heights):
            lower_part = idx + 1
            upper_part = lower_part + 1
            
            if z < split_height - tolerance:
                # Точка явно находится ниже границы и принадлежит текущей части
                return [lower_part]
            
            if abs(z - split_height) <= tolerance:
                # Точка в зоне перекрытия — относится к обеим смежным частям
                parts = [lower_part]
                if upper_part <= total_parts:
                    parts.append(upper_part)
                return sorted(parts)
            
            if z < split_height + tolerance:
                # Точка сразу после границы, но не попала в зону перекрытия
                return [upper_part]
            
            current_part = upper_part
        
        # Если точка выше всех границ — относится к последней части
        return [current_part]
    
    def _update_part_param(self, part_number: int, param: str, value):
        """Обновление параметра части башни"""
        part_idx = part_number - 1
        if 0 <= part_idx < len(self.tower_parts):
            self.tower_parts[part_idx][param] = value
            logger.debug(f"Обновлен параметр {param} части {part_number}: {value}")
    
    def _add_new_part(self):
        """Добавление новой части башни"""
        part_num = len(self.tower_parts) + 1
        
        # Автоопределение высоты начала для новой части
        split_height = None
        if part_num == 2:
            # Для второй части пытаемся автоопределить
            split_height = self._auto_detect_split_height()
        else:
            # Для последующих частей используем высоту начала предыдущей части + небольшой отступ
            if len(self.tower_parts) > 0:
                prev_part = self.tower_parts[-1]
                prev_split = prev_part.get('split_height')
                if prev_split is not None:
                    # Используем предыдущую высоту + 5 метров как начальное значение
                    split_height = prev_split + 5.0
        
        # Добавляем новую часть
        new_part = {
            "part_number": part_num,
            "shape": "prism",
            "faces": 3,
            "split_height": split_height
        }
        self.tower_parts.append(new_part)
        
        self._update_composite_settings_ui()
        
        # Принудительно обновляем размеры после добавления части
        self.composite_settings_widget.adjustSize()
        self.composite_settings_widget.updateGeometry()
        self.composite_settings_scroll.updateGeometry()
        self.composite_settings_scroll.update()
        
        logger.info(f"Добавлена часть {part_num} башни, высота начала: {split_height}")
    
    def _remove_part(self, part_num: int):
        """Удаление части башни"""
        if part_num <= 1:
            QMessageBox.warning(self, 'Ошибка', 'Нельзя удалить первую часть башни')
            return
        
        reply = QMessageBox.question(
            self,
            'Подтверждение',
            f'Удалить часть {part_num}?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            part_idx = part_num - 1
            if 0 <= part_idx < len(self.tower_parts):
                self.tower_parts.pop(part_idx)
                # Перенумеровываем части
                for idx, part in enumerate(self.tower_parts):
                    part['part_number'] = idx + 1
                self._update_composite_settings_ui()
                
                # Обновляем размеры после удаления части
                QTimer.singleShot(0, lambda: (
                    self.composite_settings_widget.adjustSize(),
                    self.composite_settings_widget.updateGeometry(),
                    self.composite_settings_scroll.updateGeometry(),
                    self.composite_settings_scroll.update()
                ))
                
                logger.info(f"Удалена часть {part_num}")
    
    def _on_auto_detect_clicked(self, spin_box: QDoubleSpinBox):
        """Обработчик кнопки автоопределения высоты"""
        auto_height = self._auto_detect_split_height()
        if auto_height is not None:
            spin_box.setValue(auto_height)
            # Обновляем высоту начала части в tower_parts
            if len(self.tower_parts) >= 2:
                self.tower_parts[1]['split_height'] = auto_height
            QMessageBox.information(self, 'Автоопределение', 
                                  f'Высота начала части определена автоматически: {auto_height:.3f} м')
        else:
            QMessageBox.warning(self, 'Ошибка', 
                              'Не удалось автоматически определить высоту начала части. Укажите вручную.')
    
    def _load_blueprint_from_parent(self):
        """Загружает blueprint из parent (MainWindow), если он есть"""
        try:
            if self.parent() is None:
                return
            
            # Пытаемся получить project_manager из parent
            if hasattr(self.parent(), 'project_manager'):
                project_manager = self.parent().project_manager
                if hasattr(project_manager, 'tower_builder_state') and project_manager.tower_builder_state:
                    blueprint_dict = project_manager.tower_builder_state
                    
                    # Проверяем, является ли blueprint составной башней
                    if isinstance(blueprint_dict, dict) and 'segments' in blueprint_dict:
                        segments = blueprint_dict.get('segments', [])
                        if len(segments) > 1:
                            # Это составная башня
                            self.tower_type = 'composite'
                            self.tower_parts = []
                            
                            # Вычисляем высоты начала для каждой части
                            current_height = 0.0
                            
                            # Создаем список частей
                            for idx, segment in enumerate(segments, start=1):
                                split_height = current_height if idx > 1 else None
                                
                                self.tower_parts.append({
                                    'part_number': idx,
                                    'shape': segment.get('shape', 'prism'),
                                    'faces': segment.get('faces', 4),
                                    'split_height': split_height
                                })
                                
                                # Увеличиваем текущую высоту на высоту текущего сегмента
                                current_height += segment.get('height', 0)
                            
                            split_heights_str = ', '.join([f"{p.get('split_height', 'None'):.3f}" if p.get('split_height') is not None else 'None' 
                                                          for p in self.tower_parts[1:]])
                            logger.info(f"Загружен blueprint из проекта: составная башня с {len(segments)} частями, высоты начала частей: [{split_heights_str}]")
                            
                            # Обновляем saved_settings для передачи в UI
                            if self.saved_settings is None:
                                self.saved_settings = {}
                            self.saved_settings['tower_type'] = 'composite'
                            self.saved_settings['tower_parts'] = self.tower_parts
        except Exception as e:
            logger.warning(f"Не удалось загрузить blueprint из parent: {e}")
    
    def show_step_2(self):
        """Шаг 2: Распределение по поясам"""
        self.current_step = 2
        self.title_label.setText('Шаг 2 из 2: Распределение точек по поясам')
        self.back_btn.setEnabled(True)
        self.next_btn.setText('Готово ✓')
        
        self.clear_steps_container()
        
        # Получаем количество поясов и тип башни
        self.belt_count = self.belt_spin.value()
        
        # Для составной башни определяем количество поясов для каждой части
        if self.tower_type == 'composite' and self.tower_parts:
            # Используем максимальное количество поясов среди всех частей
            max_faces = max(part.get('faces', 4) for part in self.tower_parts)
            self.belt_count = max_faces
            logger.info(f"Составная башня: максимальное количество поясов = {self.belt_count}")
        
        # Описание
        if self.tower_type == 'composite':
            info_text = ('Распределите точки по поясам. Точки автоматически разделены по частям башни '
                        'на основе высоты раздвоения. Используйте перетаскивание мышью '
                        'или кнопки для перемещения точек между поясами.')
        else:
            info_text = ('Распределите точки по поясам. Используйте перетаскивание мышью '
                        'или кнопки для перемещения точек между поясами.')
        info_label = QLabel(info_text)
        info_label.setWordWrap(True)
        info_label.setStyleSheet(self._info_box_style())
        self.steps_layout.addWidget(info_label)
        
        # Поле для выбора точки стояния тахеометра
        station_layout = QHBoxLayout()
        station_layout.setSpacing(4)
        station_label = QLabel('Точка стояния:')
        station_label.setStyleSheet('font-size: 9pt;')
        self.station_combo = QComboBox()
        self.station_combo.setEditable(False)
        self.station_combo.setStyleSheet('font-size: 9pt; padding: 2px;')
        
        # Добавляем все точки в комбо-бокс (включая точку standing, если она была выбрана)
        # Используем raw_data, чтобы иметь доступ ко всем точкам, включая standing
        selected_indices = []
        if hasattr(self, 'points_list') and self.points_list is not None:
            try:
                for i in range(self.points_list.count()):
                    item = self.points_list.item(i)
                    if item and item.checkState() == Qt.CheckState.Checked:
                        idx = item.data(Qt.ItemDataRole.UserRole)
                        if idx is not None:
                            selected_indices.append(idx)
            except (RuntimeError, AttributeError):
                pass
        
        # Добавляем точки в комбо-бокс
        for idx in selected_indices:
            if idx in self.raw_data.index:
                row = self.raw_data.loc[idx]
                name = row.get('name', f'Точка {idx+1}')
                z = row.get('z', 0)
                item_text = f"{name} (Z = {z:.3f} м)"
                self.station_combo.addItem(item_text, idx)
        
        # Пытаемся автоматически определить точку стояния из выбранных точек
        if selected_indices:
            selected_points_for_detection = self.raw_data.loc[selected_indices]
            auto_station_idx = self._find_station_point(selected_points_for_detection)
            if auto_station_idx is not None:
                station_idx = self.station_combo.findData(auto_station_idx)
                if station_idx >= 0:
                    self.station_combo.setCurrentIndex(station_idx)
                    logger.info(f"Автоматически выбрана точка стояния: {self.raw_data.loc[auto_station_idx, 'name']}")
        
        # Обработчик изменения выбора точки standing
        # При смене точки standing, старая точка должна появиться в списках для сортировки
        self._station_changing = False  # Флаг для предотвращения зацикливания
        def on_station_changed():
            # Предотвращаем зацикливание
            if self._station_changing:
                return
            self._station_changing = True
            try:
                # При изменении выбора точки standing перезапускаем автосортировку
                # чтобы старая точка появилась в списках, а новая была исключена
                if hasattr(self, 'belt_lists') and self.belt_lists:
                    # Временно отключаем сигнал, чтобы избежать рекурсии
                    self.station_combo.blockSignals(True)
                    try:
                        # Очищаем списки
                        for belt_list in self.belt_lists:
                            belt_list.clear()
                        # Запускаем автосортировку заново с новым выбором точки standing
                        logger.info("Перезапуск автосортировки из-за изменения выбора точки standing")
                        self.auto_sort_belts()
                    finally:
                        self.station_combo.blockSignals(False)
            finally:
                self._station_changing = False
        
        # Подключаем обработчик только после создания комбо-бокса
        # Используем флаг для предотвращения вызова при инициализации
        self._station_combo_initialized = False
        def on_station_changed_safe():
            if self._station_combo_initialized:
                on_station_changed()
            else:
                self._station_combo_initialized = True
        
        self.station_combo.currentIndexChanged.connect(on_station_changed_safe)
        
        station_layout.addWidget(station_label)
        station_layout.addWidget(self.station_combo)
        station_layout.addStretch()
        self.steps_layout.addLayout(station_layout)
        
        # Кнопки управления
        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(4)
        
        move_btn = QPushButton('➡ На пояс')
        move_btn.clicked.connect(self.move_to_belt)
        apply_compact_button_style(move_btn, width=80, min_height=28)
        controls_layout.addWidget(move_btn)
        
        clear_btn = QPushButton('🗑 Очистить')
        clear_btn.clicked.connect(self.clear_belt)
        apply_compact_button_style(clear_btn, width=85, min_height=28)
        controls_layout.addWidget(clear_btn)
        
        controls_layout.addStretch()
        
        auto_sort_btn = QPushButton('🔄 Авто')
        auto_sort_btn.clicked.connect(self.auto_sort_belts)
        apply_compact_button_style(auto_sort_btn, width=75, min_height=28)
        controls_layout.addWidget(auto_sort_btn)
        
        self.steps_layout.addLayout(controls_layout)
        
        # Создаем UI для поясов с группировкой по частям
        if self.tower_type == 'composite' and len(self.tower_parts) > 1:
            # Составная башня - создаем вкладки для каждой части
            from PyQt6.QtWidgets import QTabWidget
            
            tabs = QTabWidget()
            self.belt_lists = []
            
            # Вычисляем смещения для глобальных номеров поясов
            belt_offsets = [0]
            for part_idx in range(1, len(self.tower_parts)):
                prev_faces = self.tower_parts[part_idx - 1].get('faces', 4)
                belt_offsets.append(belt_offsets[-1] + prev_faces)
            
            for part_idx, part in enumerate(self.tower_parts):
                part_num = part_idx + 1
                part_faces = part.get('faces', 4)
                
                # Создаем виджет для части
                part_widget = QWidget()
                part_layout = QVBoxLayout()
                part_layout.setContentsMargins(2, 2, 2, 2)
                part_layout.setSpacing(3)
                part_widget.setLayout(part_layout)
                
                # Информация о части
                part_info = QLabel(f'Часть {part_num}: {part.get("shape", "prism")}, {part_faces} поясов')
                part_info.setStyleSheet('font-weight: 600; font-size: 9pt; padding: 3px;')
                part_layout.addWidget(part_info)
                
                # Создаем столбцы для поясов этой части
                part_splitter = QSplitter(Qt.Orientation.Horizontal)
                part_splitter.setChildrenCollapsible(False)
                
                for belt_idx in range(part_faces):
                    global_belt_num = belt_offsets[part_idx] + belt_idx + 1
                    
                    belt_widget = QWidget()
                    belt_layout = QVBoxLayout()
                    belt_layout.setContentsMargins(2, 2, 2, 2)
                    belt_layout.setSpacing(2)
                    belt_widget.setLayout(belt_layout)
                    
                    # Заголовок пояса (показываем part_belt, который начинается с 1 для каждой части)
                    part_belt_num = belt_idx + 1
                    belt_label = QLabel(f'Пояс {part_belt_num}')
                    belt_label.setStyleSheet('font-weight: 600; font-size: 9pt; padding: 3px;')
                    belt_layout.addWidget(belt_label)
                    
                    # Список точек пояса
                    belt_list = DraggableListWidget()
                    belt_list.setStyleSheet('''
                        QListWidget::item {
                            padding: 2px;
                            font-size: 9pt;
                            min-height: 18px;
                        }
                        QListWidget::item:selected {
                            background-color: #3daee9;
                        }
                    ''')
                    belt_list.setProperty('belt_number', global_belt_num)
                    belt_list.setProperty('part_number', part_num)
                    belt_layout.addWidget(belt_list)
                    
                    self.belt_lists.append(belt_list)
                    part_splitter.addWidget(belt_widget)
                
                part_layout.addWidget(part_splitter)
                tabs.addTab(part_widget, f'Часть {part_num}')
            
            self.steps_layout.addWidget(tabs)
        else:
            # Обычная башня - простой список поясов
            splitter = QSplitter(Qt.Orientation.Horizontal)
            splitter.setChildrenCollapsible(False)
            
            self.belt_lists = []
            
            for i in range(self.belt_count):
                belt_widget = QWidget()
                belt_layout = QVBoxLayout()
                belt_layout.setContentsMargins(2, 2, 2, 2)
                belt_layout.setSpacing(2)
                belt_widget.setLayout(belt_layout)
                
                # Заголовок пояса
                belt_label = QLabel(f'Пояс {i+1}')
                belt_label.setStyleSheet('font-weight: 600; font-size: 9pt; padding: 3px;')
                belt_layout.addWidget(belt_label)
                
                # Список точек пояса
                belt_list = DraggableListWidget()
                belt_list.setStyleSheet('''
                    QListWidget::item {
                        padding: 2px;
                        font-size: 9pt;
                        min-height: 18px;
                    }
                    QListWidget::item:selected {
                        background-color: #3daee9;
                    }
                ''')
                belt_list.setProperty('belt_number', i+1)
                belt_layout.addWidget(belt_list)
                
                self.belt_lists.append(belt_list)
                splitter.addWidget(belt_widget)
            
            self.steps_layout.addWidget(splitter)
        
        # Автоматическая сортировка при первом открытии
        self.auto_sort_belts()
    
    def _find_station_point(self, points: pd.DataFrame):
        """Автоматически найти точку стояния (расстояние >15м от всех остальных)
        
        Алгоритм:
        1. Для каждой точки вычисляем минимальное расстояние до ближайшей другой точки
        2. Если это расстояние > 15м, то это точка standing (она далеко от всех остальных)
        
        Returns:
            Индекс точки стояния или None
        """
        if points is None or points.empty or len(points) < 2:
            return None
        
        # Минимальное расстояние для определения точки стояния
        min_distance = 15.0
        
        # Вычисляем расстояния между всеми точками
        positions = points[['x', 'y', 'z']].values
        point_indices = points.index.tolist()
        
        # Для каждой точки находим минимальное расстояние до ближайшей другой точки
        best_candidate = None
        best_min_distance = 0.0
        
        for pos_idx, (original_idx, point) in enumerate(points.iterrows()):
            point_pos = np.array([point['x'], point['y'], point['z']])
            
            # Вычисляем расстояния до всех остальных точек
            distances = np.linalg.norm(positions - point_pos, axis=1)
            
            # Исключаем саму точку из сравнения (расстояние до себя = 0)
            # Создаем маску для всех точек кроме текущей
            mask = np.ones(len(distances), dtype=bool)
            mask[pos_idx] = False
            other_distances = distances[mask]
            
            # Находим минимальное расстояние до ближайшей точки
            if len(other_distances) > 0:
                min_dist_to_others = other_distances.min()
            else:
                min_dist_to_others = 0
            
            # Если минимальное расстояние больше порога - это кандидат на точку standing
            # Выбираем точку с максимальным минимальным расстоянием (самую далекую)
            if min_dist_to_others >= min_distance:
                if min_dist_to_others > best_min_distance:
                    best_min_distance = min_dist_to_others
                    best_candidate = original_idx
        
        if best_candidate is not None:
            point_name = points.loc[best_candidate, 'name'] if 'name' in points.columns else f'Точка {best_candidate}'
            logger.info(f"Найдена точка standing на расстоянии {best_min_distance:.3f}м от остальных: {point_name} (индекс {best_candidate})")
            return best_candidate
        
        logger.info("Точка standing не найдена автоматически (нет точек на расстоянии >15м от остальных)")
        return None
    
    def select_all_points(self):
        """Выбрать все точки"""
        for i in range(self.points_list.count()):
            item = self.points_list.item(i)
            item.setCheckState(Qt.CheckState.Checked)
    
    def deselect_all_points(self):
        """Снять выбор со всех точек"""
        for i in range(self.points_list.count()):
            item = self.points_list.item(i)
            item.setCheckState(Qt.CheckState.Unchecked)
    
    def update_selected_count(self):
        """Обновление счетчика выбранных точек"""
        if not hasattr(self, 'points_list') or self.points_list is None:
            return
        
        try:
            selected = sum(1 for i in range(self.points_list.count()) 
                          if self.points_list.item(i) and self.points_list.item(i).checkState() == Qt.CheckState.Checked)
            total = self.points_list.count()
            if hasattr(self, 'selected_count_label') and self.selected_count_label is not None:
                self.selected_count_label.setText(f'Выбрано: {selected} из {total}')
        except (RuntimeError, AttributeError) as e:
            logger.warning(f"Ошибка при обновлении счетчика выбранных точек: {e}")
    
    def get_selected_points(self) -> pd.DataFrame:
        """Получить отфильтрованные точки
        
        ВАЖНО: Возвращает DataFrame с оригинальными индексами из raw_data!
        Точка standing исключается из результата только если она выбрана в station_combo.
        Если пользователь меняет выбор точки standing, старая точка должна появиться в списках.
        """
        # Если уже есть кэшированные данные - возвращаем их
        if self.cached_selected_points is not None:
            logger.debug(f"Используем кэшированные выбранные точки: {len(self.cached_selected_points)} точек")
            # Исключаем текущую точку standing из кэша
            station_idx = None
            if hasattr(self, 'station_combo') and self.station_combo.currentIndex() >= 0:
                station_idx = self.station_combo.currentData()
            
            if station_idx is not None and station_idx in self.cached_selected_points.index:
                result = self.cached_selected_points.drop(index=station_idx)
                logger.debug(f"Исключена текущая точка standing (индекс {station_idx}) из кэша")
                return result
            return self.cached_selected_points
        
        # Иначе читаем из points_list (если он существует)
        selected_indices = []
        
        try:
            if hasattr(self, 'points_list') and self.points_list is not None:
                for i in range(self.points_list.count()):
                    item = self.points_list.item(i)
                    if item and item.checkState() == Qt.CheckState.Checked:
                        idx = item.data(Qt.ItemDataRole.UserRole)
                        if idx is not None:
                            selected_indices.append(idx)
                
                if selected_indices:
                    # НЕ сбрасываем индексы! Сохраняем оригинальные из raw_data
                    result = self.raw_data.loc[selected_indices].copy()
                    
                    # Исключаем текущую точку standing, если она выбрана
                    station_idx = None
                    if hasattr(self, 'station_combo') and self.station_combo.currentIndex() >= 0:
                        station_idx = self.station_combo.currentData()
                    
                    if station_idx is not None and station_idx in result.index:
                        result = result.drop(index=station_idx)
                        logger.debug(f"Исключена текущая точка standing (индекс {station_idx}) из выбранных точек")
                    
                    logger.debug(f"Прочитано {len(result)} выбранных точек из points_list (без текущей standing)")
                    return result
        except (RuntimeError, AttributeError) as e:
            logger.warning(f"Ошибка при чтении points_list: {e}")
        
        # Если points_list недоступен, возвращаем все точки без текущей standing (fallback)
        logger.warning("points_list недоступен, возвращаем все точки из raw_data (без текущей standing)")
        result = self.raw_data.copy()
        
        # Исключаем текущую точку standing
        station_idx = None
        if hasattr(self, 'station_combo') and self.station_combo.currentIndex() >= 0:
            station_idx = self.station_combo.currentData()
        
        if station_idx is not None and station_idx in result.index:
            result = result.drop(index=station_idx)
            logger.debug(f"Исключена текущая точка standing (индекс {station_idx}) из всех точек")
        
        return result
    
    def auto_sort_belts(self):
        """Автоматическая сортировка точек по поясам"""
        from core.belt_operations import auto_assign_belts
        
        # Очищаем все списки
        for belt_list in self.belt_lists:
            belt_list.clear()
        
        # Проверяем, есть ли сохраненные настройки сортировки
        if self.saved_settings and 'belt_assignments' in self.saved_settings:
            # Загружаем сохраненную сортировку
            logger.info("Загрузка сохраненной сортировки точек по поясам")
            
            # Получаем индекс точки standing для исключения
            station_idx = None
            if hasattr(self, 'station_combo') and self.station_combo.currentIndex() >= 0:
                station_idx = self.station_combo.currentData()
                logger.info(f"Исключаем точку standing из загруженной сортировки: индекс {station_idx}")
            
            belt_assignments = self.saved_settings['belt_assignments']
            
            # ВАЖНО: Берем только точки, которые были выбраны на шаге 1
            selected_points_df = self.get_selected_points()
            selected_names = set(selected_points_df['name'].tolist())
            
            logger.info(f"Выбрано точек на шаге 1: {len(selected_names)}")
            
            # Используем оригинальные индексы из raw_data, но только для выбранных точек
            loaded_count = 0
            skipped_count = 0
            
            for belt_num, point_names in belt_assignments.items():
                belt_idx = int(belt_num) - 1
                if belt_idx < 0 or belt_idx >= len(self.belt_lists):
                    continue
                
                for point_name in point_names:
                    # ПРОВЕРЯЕМ: была ли эта точка выбрана на шаге 1?
                    if point_name not in selected_names:
                        skipped_count += 1
                        logger.debug(f"Пропускаем точку '{point_name}' - не выбрана на шаге 1")
                        continue
                    
                    # Ищем точку по имени в ОРИГИНАЛЬНЫХ данных (raw_data)
                    point_row = self.raw_data[self.raw_data['name'] == point_name]
                    if not point_row.empty:
                        # Берем ОРИГИНАЛЬНЫЙ индекс из raw_data
                        original_idx = point_row.index[0]
                        
                        # Пропускаем точку standing
                        if original_idx == station_idx:
                            logger.debug(f"Пропускаем точку '{point_name}' - это точка standing")
                            continue
                        
                        z = point_row['z'].iloc[0]
                        
                        item_text = f"{point_name} (Z = {z:.3f} м)"
                        item = QListWidgetItem(item_text)
                        item.setData(Qt.ItemDataRole.UserRole, original_idx)  # Сохраняем оригинальный индекс!
                        self._style_belt_item(item, int(belt_num))
                        
                        self.belt_lists[belt_idx].addItem(item)
                        loaded_count += 1
            
            logger.info(f"Сохраненная сортировка загружена: {loaded_count} точек, пропущено {skipped_count}")
            if loaded_count > 0:
                return
            logger.warning("Не удалось применить сохраненную сортировку — выполняем автоматическое распределение")
            # очистим списки перед автосортировкой
            for belt_list in self.belt_lists:
                belt_list.clear()
        
        # Если нет сохраненных настроек - выполняем автоматическую сортировку
        filtered = self.get_selected_points()
        
        if filtered.empty:
            QMessageBox.warning(self, 'Предупреждение', 'Нет выбранных точек для сортировки')
            return
        
        # Получаем индекс точки standing для исключения из сортировки
        # ВАЖНО: точка standing должна быть доступна для выбора, но не попадать в списки поясов
        station_idx = None
        if hasattr(self, 'station_combo') and self.station_combo.currentIndex() >= 0:
            station_idx = self.station_combo.currentData()
            logger.info(f"Исключаем точку standing из автосортировки: индекс {station_idx}")
        
        # ВАЖНО: filtered содержит оригинальные индексы из raw_data
        # Создаем копию и добавляем рабочие колонки
        points_list = filtered.copy()
        points_list['assigned'] = False
        points_list['belt'] = 0
        points_list['tower_part'] = 1  # По умолчанию все точки в первой части
        points_list['part_belt'] = 0  # Номер пояса внутри части
        
        # Список оригинальных индексов в порядке их следования (исключаем точку standing из сортировки)
        # Но точка standing должна быть доступна в комбо-боксе для выбора
        original_indices = [idx for idx in points_list.index.tolist() if idx != station_idx]
        
        indices_preview = f"{original_indices[:10]}..." if len(original_indices) > 10 else f"{original_indices}"
        logger.info(f"Начинаем автосортировку: всего {len(original_indices)} выбранных точек, "
                   f"тип башни: {self.tower_type}, оригинальные индексы: {indices_preview}")
        
        # Если башня составная - определяем принадлежность точек к частям с учетом разброса
        # ВАЖНО: Точки на границе частей дублируются и включаются в обе части
        point_part_memberships = {}
        if self.tower_type == 'composite' and len(self.tower_parts) > 1:
            logger.info(f"Составная башня: {len(self.tower_parts)} частей, разброс = {self.split_height_tolerance:.2f} м")
            
            split_heights = []
            for part in self.tower_parts[1:]:
                split_height = part.get('split_height')
                if split_height is not None:
                    split_heights.append(split_height)
            
            for original_idx in original_indices:
                z = points_list.loc[original_idx, 'z']
                parts_for_point = self._determine_point_parts(z, split_heights)
                point_part_memberships[original_idx] = parts_for_point
                points_list.loc[original_idx, 'tower_part'] = parts_for_point[0]
            
            for part_num in range(1, len(self.tower_parts) + 1):
                count = sum(1 for memberships in point_part_memberships.values() if part_num in memberships)
                logger.info(f"Распределение по частям: часть {part_num} = {count} точек")
        else:
            for original_idx in original_indices:
                point_part_memberships[original_idx] = [1]
                points_list.loc[original_idx, 'tower_part'] = 1
        
        self.point_part_memberships = point_part_memberships
        
        # Сортируем точки по частям и высоте
        if self.tower_type == 'composite' and len(self.tower_parts) > 1:
            # Составная башня - сортировка по частям
            # Вычисляем смещения для глобальных номеров поясов
            belt_offsets = [0]  # Смещение для первой части = 0
            for part_idx in range(1, len(self.tower_parts)):
                prev_faces = self.tower_parts[part_idx - 1].get('faces', 4)
                belt_offsets.append(belt_offsets[-1] + prev_faces)
            
            for part_num in range(1, len(self.tower_parts) + 1):
                part_indices = [
                    idx for idx in original_indices
                    if part_num in point_part_memberships.get(idx, [1])
                ]
                if not part_indices:
                    continue
                part_points = points_list.loc[part_indices].copy()
                
                # Определяем количество поясов для этой части
                part_idx = part_num - 1
                if part_idx < len(self.tower_parts):
                    part_faces = self.tower_parts[part_idx].get('faces', self.belt_count)
                else:
                    part_faces = self.belt_count
                
                logger.info(f"Часть {part_num}: {len(part_points)} точек, поясов = {part_faces}")
                
                # Сортируем точки по высоте
                part_points_sorted = part_points.sort_values('z')
                part_indices = part_points_sorted.index.tolist()
                
                # Группируем точки по поясам (граням) внутри части используя угловое распределение
                if len(part_indices) > 0:
                    # Используем угловое распределение для определения поясов
                    belts = self._group_points_by_belts(points_list, part_indices, part_faces, station_idx)
                    
                    # Распределяем точки по поясам
                    # ВАЖНО: Для составных башен пояса начинаются с 1 для каждой части (part_belt)
                    for belt_idx, belt_point_indices in enumerate(belts, start=1):
                        if belt_idx > part_faces:
                            break
                        
                        # part_belt - номер пояса внутри части (начинается с 1)
                        part_belt_num = belt_idx
                        # Глобальный номер пояса для отображения в UI (используется только для индексации списков)
                        global_belt_num = belt_offsets[part_idx] + belt_idx
                        
                        for idx in belt_point_indices:
                            # Обрабатываем виртуальные индексы (дубликаты точек на границе)
                            if isinstance(idx, str) and '_part' in idx:
                                # Извлекаем оригинальный индекс из виртуального
                                original_idx = int(idx.split('_part')[0])
                                is_duplicate = True
                            else:
                                original_idx = idx
                                is_duplicate = False
                            
                            # Пропускаем точку standing
                            if original_idx == station_idx:
                                logger.debug(f"Пропускаем точку standing '{points_list.loc[idx, 'name']}' при добавлении в пояс {belt_idx}")
                                continue
                            
                            points_list.loc[idx, 'assigned'] = True
                            # Сохраняем part_belt как основной номер пояса для составных башен
                            points_list.loc[idx, 'belt'] = part_belt_num
                            points_list.loc[idx, 'part_belt'] = part_belt_num
                            
                            row = points_list.loc[idx]
                            name = row.get('name', f'Точка {original_idx+1}')
                            z = row.get('z', 0)
                            
                            # Для дубликатов добавляем пометку
                            duplicate_mark = " [Дубликат]" if is_duplicate else ""
                            item_text = f"{name} (Z = {z:.3f} м) [Ч{part_num}, П{part_belt_num}]{duplicate_mark}"
                            item = QListWidgetItem(item_text)
                            # Сохраняем оригинальный индекс (не виртуальный) для связи с raw_data
                            item.setData(Qt.ItemDataRole.UserRole, original_idx)
                            self._style_belt_item(item, global_belt_num)
                            
                            # Добавляем в соответствующий список поясов (используем global_belt_num для индексации)
                            belt_list_idx = global_belt_num - 1
                            if 0 <= belt_list_idx < len(self.belt_lists):
                                self.belt_lists[belt_list_idx].addItem(item)
                        
                        logger.info(f"Часть {part_num}, пояс {part_belt_num} (глобальный индекс {global_belt_num}): {len(belt_point_indices)} точек")
        else:
            # Обычная башня - используем угловое распределение для группировки по поясам
            # Группируем точки по поясам (граням) на основе углового распределения
            # Для обычной башни логика такая же, как для составной - пояса начинаются с 1
            belts = self._group_points_by_belts(points_list, original_indices, self.belt_count, station_idx)
            
            # Распределяем точки по поясам
            for belt_idx, belt_point_indices in enumerate(belts, start=1):
                if belt_idx > self.belt_count:
                    break
                
                # Для обычной башни part_belt = belt (пояса начинаются с 1)
                part_belt_num = belt_idx
                
                for original_idx in belt_point_indices:
                    # Пропускаем точку standing
                    if original_idx == station_idx:
                        logger.debug(f"Пропускаем точку standing '{points_list.loc[original_idx, 'name']}' при добавлении в пояс {belt_idx}")
                        continue
                    
                    points_list.loc[original_idx, 'assigned'] = True
                    points_list.loc[original_idx, 'belt'] = part_belt_num
                    points_list.loc[original_idx, 'part_belt'] = part_belt_num
                    
                    row = points_list.loc[original_idx]
                    name = row.get('name', f'Точка {original_idx+1}')
                    z = row.get('z', 0)
                    
                    item_text = f"{name} (Z = {z:.3f} м)"
                    item = QListWidgetItem(item_text)
                    item.setData(Qt.ItemDataRole.UserRole, original_idx)
                    self._style_belt_item(item, part_belt_num)
                    
                    self.belt_lists[part_belt_num - 1].addItem(item)
                
                logger.info(f"Пояс {part_belt_num}: {len(belt_point_indices)} точек")
        
        assigned_count = points_list['assigned'].sum()
        unassigned_count = len(points_list) - assigned_count
        
        # Логируем нераспределенные точки
        if unassigned_count > 0:
            unassigned_indices = points_list[~points_list['assigned']].index.tolist()
            unassigned_names = points_list.loc[unassigned_indices, 'name'].tolist()
            logger.warning(f"Остались нераспределенные точки ({unassigned_count}): {unassigned_names}")
            logger.warning(f"Индексы нераспределенных точек: {unassigned_indices}")
        
        logger.info(f"Автосортировка завершена: {assigned_count} точек распределены по поясам")
    
    def get_belt_color(self, belt_num: int) -> QColor:
        """Получить цвет пояса"""
        if self.dark_theme_enabled:
            colors = [
                QColor(136, 76, 91),
                QColor(74, 123, 97),
                QColor(70, 94, 150),
                QColor(148, 122, 62),
                QColor(125, 84, 148),
                QColor(70, 130, 150),
            ]
        else:
            colors = [
                QColor(255, 200, 200),  # Светло-красный
                QColor(200, 255, 200),  # Светло-зеленый
                QColor(200, 200, 255),  # Светло-синий
                QColor(255, 255, 200),  # Светло-желтый
                QColor(255, 200, 255),  # Светло-пурпурный
                QColor(200, 255, 255),  # Светло-циан
            ]
        return colors[(belt_num - 1) % len(colors)]

    def _style_belt_item(self, item: QListWidgetItem, belt_num: int):
        """Применяет цвета к элементу списка пояса с учетом темы."""
        background = self.get_belt_color(belt_num)
        item.setBackground(background)
        luminance = 0.299 * background.red() + 0.587 * background.green() + 0.114 * background.blue()
        if luminance > 150:
            text_color = QColor(33, 33, 33)
        else:
            text_color = QColor(240, 240, 240)
        item.setForeground(text_color)
    
    def move_to_belt(self):
        """Переместить выбранные точки на другой пояс"""
        # Находим активный список
        current_list = None
        for belt_list in self.belt_lists:
            if belt_list.hasFocus() or len(belt_list.selectedItems()) > 0:
                current_list = belt_list
                break
        
        if current_list is None or len(current_list.selectedItems()) == 0:
            QMessageBox.warning(self, 'Предупреждение', 
                              'Выберите точки для перемещения')
            return
        
        # Запрашиваем номер пояса
        belt_num, ok = QInputDialog.getInt(
            self, 
            'Переместить на пояс',
            'Введите номер пояса:',
            1, 1, self.belt_count, 1
        )
        
        if ok:
            selected_items = current_list.selectedItems()
            target_list = self.belt_lists[belt_num - 1]
            
            for item in selected_items:
                # Клонируем item
                new_item = QListWidgetItem(item.text())
                new_item.setData(Qt.ItemDataRole.UserRole, item.data(Qt.ItemDataRole.UserRole))
                self._style_belt_item(new_item, belt_num)
                
                # Добавляем в целевой список
                target_list.addItem(new_item)
                
                # Удаляем из текущего
                row = current_list.row(item)
                current_list.takeItem(row)
            
            logger.info(f"Перемещено {len(selected_items)} точек на пояс {belt_num}")
    
    def clear_belt(self):
        """Очистить пояс"""
        belt_num, ok = QInputDialog.getInt(
            self,
            'Очистить пояс',
            'Введите номер пояса для очистки:',
            1, 1, self.belt_count, 1
        )
        
        if ok:
            reply = QMessageBox.question(
                self,
                'Подтверждение',
                f'Очистить пояс {belt_num}?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.belt_lists[belt_num - 1].clear()
                logger.info(f"Очищен пояс {belt_num}")
    
    def go_back(self):
        """Вернуться на предыдущий шаг"""
        if self.current_step == 2:
            self.show_step_1()
    
    def go_next(self):
        """Перейти к следующему шагу"""
        if self.current_step == 1:
            # Читаем выбранные точки напрямую из points_list
            selected_indices = []
            selected_count = 0
            
            try:
                if hasattr(self, 'points_list') and self.points_list is not None:
                    for i in range(self.points_list.count()):
                        item = self.points_list.item(i)
                        if item and item.checkState() == Qt.CheckState.Checked:
                            idx = item.data(Qt.ItemDataRole.UserRole)
                            if idx is not None:
                                selected_indices.append(idx)
                                selected_count += 1
            except (RuntimeError, AttributeError) as e:
                logger.error(f"Ошибка при чтении points_list: {e}")
                QMessageBox.warning(self, 'Ошибка', 'Не удалось прочитать выбранные точки')
                return
            
            logger.info(f"Переход на шаг 2: выбрано {selected_count} из {self.points_list.count() if hasattr(self, 'points_list') else 0} точек")
            logger.info(f"Индексы выбранных точек: {selected_indices[:10]}..." if len(selected_indices) > 10 else f"{selected_indices}")
            
            if selected_count < 3:
                QMessageBox.warning(self, 'Предупреждение', 
                                  'Выберите минимум 3 точки для продолжения')
                return
            
            # Кэшируем выбранные точки ПЕРЕД переходом на следующий шаг
            # Исключаем точку standing из кэша
            station_idx = None
            if hasattr(self, 'station_combo') and self.station_combo.currentIndex() >= 0:
                station_idx = self.station_combo.currentData()
            
            if selected_indices:
                # Исключаем точку standing из выбранных индексов
                if station_idx is not None and station_idx in selected_indices:
                    selected_indices = [idx for idx in selected_indices if idx != station_idx]
                    logger.info(f"Исключена точка standing (индекс {station_idx}) из кэша")
                
                self.cached_selected_points = self.raw_data.loc[selected_indices].copy()
                logger.info(f"Кэшировано {len(self.cached_selected_points)} выбранных точек перед переходом на шаг 2 (без standing)")
            else:
                logger.warning("Не удалось кэшировать выбранные точки - список индексов пуст")
                QMessageBox.warning(self, 'Ошибка', 'Не удалось получить выбранные точки')
                return
            
            self.show_step_2()
        
        elif self.current_step == 2:
            # Сохраняем настройки сортировки ПЕРЕД закрытием диалога
            self.sorting_settings = self.get_sorting_settings()
            
            # Финализируем данные
            self.finalize_data()
            self.accept()
    
    def finalize_data(self):
        """Формирование финальных данных с назначенными поясами"""
        result_data = []
        
        # Получаем индекс точки standing
        if hasattr(self, 'station_combo') and self.station_combo.currentIndex() >= 0:
            self.station_point_idx = self.station_combo.currentData()
            logger.info(f"Сохранена точка standing: индекс {self.station_point_idx}")
        else:
            self.station_point_idx = None
            logger.warning("Точка standing не выбрана")
        
        # Проверяем, что belt_lists существует
        if not hasattr(self, 'belt_lists') or self.belt_lists is None:
            logger.error("belt_lists не инициализирован. Возможно, show_step_2 не был вызван.")
            # Создаем пустой filtered_data
            self.filtered_data = pd.DataFrame()
            return
        
        membership_map = getattr(self, 'point_part_memberships', {}) or {}
        result_points: Dict[int, Dict[str, Any]] = {}
        
        def ensure_entry(idx: int) -> Dict[str, Any]:
            if idx not in result_points:
                base_data = self.raw_data.loc[idx].to_dict()
                base_data['is_station'] = False
                result_points[idx] = {
                    'base': base_data,
                    'parts': set(),
                    'part_belts': {}
                }
            return result_points[idx]
        
        belt_offsets = [0]
        if self.tower_type == 'composite' and len(self.tower_parts) > 1:
            for part_idx in range(1, len(self.tower_parts)):
                prev_faces = self.tower_parts[part_idx - 1].get('faces', 4)
                belt_offsets.append(belt_offsets[-1] + prev_faces)
        
        for belt_idx, belt_list in enumerate(self.belt_lists):
            global_belt_num = belt_idx + 1
            
            part_num = 1
            part_belt_num = global_belt_num
            if self.tower_type == 'composite' and len(self.tower_parts) > 1:
                for part_idx, part in enumerate(self.tower_parts):
                    part_faces = part.get('faces', 4)
                    part_offset = belt_offsets[part_idx]
                    if part_offset < global_belt_num <= part_offset + part_faces:
                        part_num = part_idx + 1
                        part_belt_num = global_belt_num - part_offset
                        break
            
            point_count = 0
            for i in range(belt_list.count()):
                item = belt_list.item(i)
                original_idx = item.data(Qt.ItemDataRole.UserRole)
                
                if original_idx == self.station_point_idx:
                    continue
                
                entry = ensure_entry(original_idx)
                entry['parts'].add(part_num)
                entry['part_belts'][part_num] = part_belt_num
                point_count += 1
            
            logger.info(f"Пояс {global_belt_num}: {point_count} точек")
        
        # Гарантируем, что все выбранные точки присутствуют
        if self.cached_selected_points is not None:
            candidate_indices = self.cached_selected_points.index.tolist()
        else:
            candidate_indices = self.raw_data.index.tolist()
        
        for idx in candidate_indices:
            if idx == self.station_point_idx:
                continue
            ensure_entry(idx)
        
        # КРИТИЧЕСКИ ВАЖНО: сохраняем исходный порядок точек из raw_data или cached_selected_points
        # Определяем исходный порядок точек
        if self.cached_selected_points is not None:
            # Используем порядок из cached_selected_points (это порядок выбранных точек на шаге 1)
            source_order = self.cached_selected_points.index.tolist()
            logger.debug(f"finalize_data: Используем порядок из cached_selected_points: {len(source_order)} точек")
        else:
            # Fallback: используем порядок из raw_data
            source_order = self.raw_data.index.tolist()
            logger.debug(f"finalize_data: Используем порядок из raw_data: {len(source_order)} точек")
        
        # Исключаем точку standing из исходного порядка
        if self.station_point_idx is not None and self.station_point_idx in source_order:
            source_order = [idx for idx in source_order if idx != self.station_point_idx]
        
        result_data = []
        # Итерируемся в исходном порядке, а не в порядке словаря result_points
        for original_idx in source_order:
            if original_idx not in result_points:
                # Точка не была назначена ни на один пояс - пропускаем или добавляем с belt=None
                logger.debug(f"finalize_data: Точка {original_idx} не найдена в result_points, пропускаем")
                continue
            
            entry = result_points[original_idx]
            base = entry['base'].copy()
            memberships = sorted(entry['parts']) if entry['parts'] else membership_map.get(original_idx, [])
            if not memberships:
                memberships = membership_map.get(original_idx, [base.get('tower_part', 1) or 1])
            if not memberships:
                memberships = [1]
            
            primary_part = memberships[0]
            part_belt_value = entry['part_belts'].get(primary_part)
            
            base['tower_part'] = primary_part
            base['part_belt'] = part_belt_value
            base['belt'] = part_belt_value if part_belt_value is not None else base.get('belt')
            base['tower_part_memberships'] = json.dumps(memberships, ensure_ascii=False)
            base['part_belt_assignments'] = json.dumps(entry['part_belts'], ensure_ascii=False)
            
            result_data.append(base)
        
        # Добавляем точку standing в конец (если есть)
        if self.station_point_idx is not None:
            station_data = self.raw_data.loc[self.station_point_idx].to_dict()
            station_data['belt'] = None
            station_data['is_station'] = True
            station_data['tower_part'] = None
            station_data['part_belt'] = None
            station_data['tower_part_memberships'] = json.dumps([], ensure_ascii=False)
            station_data['part_belt_assignments'] = json.dumps({}, ensure_ascii=False)
            result_data.append(station_data)
        
        if not result_data:
            logger.warning("Не удалось сформировать результат - список пуст")
            self.filtered_data = pd.DataFrame()
            return
        
        # КРИТИЧЕСКИ ВАЖНО: создаем DataFrame с сохранением порядка точек
        # НЕ используем reset_index(drop=True) сразу, чтобы сохранить соответствие с исходными индексами
        # Но создаем новый DataFrame с последовательными индексами для совместимости
        self.filtered_data = pd.DataFrame(result_data)
        
        # Логируем порядок для отладки
        if len(self.filtered_data) > 0:
            logger.info(
                f"finalize_data: Создан DataFrame с {len(self.filtered_data)} точками. "
                f"Первые 5 индексов: {list(self.filtered_data.index[:5])}, "
                f"последние 5 индексов: {list(self.filtered_data.index[-5:])}"
            )
            
            # Проверяем соответствие порядка с исходными данными
            if self.cached_selected_points is not None and len(self.cached_selected_points) > 0:
                first_5_original = list(self.cached_selected_points.index[:5])
                first_5_result = list(self.filtered_data.index[:5])
                if first_5_original != first_5_result:
                    logger.warning(
                        f"finalize_data: Порядок может не совпадать! "
                        f"Первые 5 исходных: {first_5_original}, "
                        f"первые 5 результата: {first_5_result}"
                    )
        
        # Теперь сбрасываем индексы для создания последовательной нумерации
        # Это нужно для совместимости с остальным кодом
        self.filtered_data = self.filtered_data.reset_index(drop=True)
        
        belt_distribution = self.filtered_data['belt'].value_counts(dropna=True).sort_index()
        logger.info(f"Финализировано {len(self.filtered_data)} точек. Распределение по поясам: {belt_distribution.to_dict()}")
        
        if self.tower_type == 'composite' and 'tower_part' in self.filtered_data.columns:
            part_distribution = self.filtered_data['tower_part'].value_counts(dropna=True).sort_index()
            logger.info(f"Распределение по частям (первичное назначение): {part_distribution.to_dict()}")
    
    def get_sorting_settings(self) -> dict:
        """Получить настройки сортировки для сохранения"""
        settings = {
            'belt_count': self.belt_count,
            'excluded_points': [],
            'belt_assignments': {},
            'tower_type': self.tower_type,
            'tower_parts': self.tower_parts.copy() if self.tower_parts else [],
            'split_height_tolerance': self.split_height_tolerance
        }
        
        try:
            # Сохраняем список исключенных точек (если points_list еще существует)
            if hasattr(self, 'points_list') and self.points_list is not None:
                try:
                    for i in range(self.points_list.count()):
                        item = self.points_list.item(i)
                        if item and item.checkState() == Qt.CheckState.Unchecked:
                            idx = item.data(Qt.ItemDataRole.UserRole)
                            settings['excluded_points'].append(int(idx))
                except RuntimeError:
                    logger.warning("points_list был удален, пропускаем сохранение исключенных точек")
            
            # Сохраняем распределение по поясам
            if hasattr(self, 'belt_lists'):
                for belt_idx, belt_list in enumerate(self.belt_lists):
                    belt_num = belt_idx + 1
                    point_names = []
                    
                    try:
                        for i in range(belt_list.count()):
                            item = belt_list.item(i)
                            if item:
                                original_idx = item.data(Qt.ItemDataRole.UserRole)
                                point_name = self.raw_data.loc[original_idx, 'name']
                                point_names.append(point_name)
                    except RuntimeError:
                        logger.warning(f"belt_list для пояса {belt_num} был удален")
                        continue
                    
                    if point_names:
                        settings['belt_assignments'][belt_num] = point_names
        
        except Exception as e:
            logger.error(f"Ошибка при сохранении настроек: {e}")
        
        split_heights_str = ', '.join([str(p.get('split_height', 'None')) for p in settings['tower_parts'][1:]])
        logger.info(f"Сохранены настройки: тип башни={settings['tower_type']}, частей={len(settings['tower_parts'])}, высоты начала частей=[{split_heights_str}]")
        return settings
    
    def get_cached_sorting_settings(self) -> dict:
        """Получить кэшированные настройки сортировки"""
        return self.sorting_settings if self.sorting_settings else {}
    
    def get_result(self) -> pd.DataFrame:
        """Получить результат работы мастера"""
        return self.filtered_data if self.filtered_data is not None else pd.DataFrame()

