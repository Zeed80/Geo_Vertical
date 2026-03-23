"""
Мастер импорта данных с другой точки стояния
"""

import json
import numpy as np
import pandas as pd
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
                             QRadioButton, QButtonGroup, QFileDialog, QMessageBox,
                             QDoubleSpinBox, QFormLayout, QGroupBox, QTableWidget,
                             QTableWidgetItem, QHeaderView, QSplitter, QCheckBox, 
                             QSpinBox, QComboBox, QSizePolicy, QScrollArea, QWidget)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from typing import Optional, List, Tuple, Dict, Any
import logging

from core.planar_orientation import domain_rotation_deg_to_math_rad, normalize_signed_angle_deg
from core.data_loader import load_survey_data
from core.survey_registration import (
    compute_helmert_parameters,
    apply_helmert_transform,
    register_belt_survey,
    evaluate_transformation_quality,
    compute_rotation_from_belt_connections,
    shift_points_along_z,
    translate_points_xy,
    rotate_points_around_z
)
from core.point_mapping import PointMapping
from core.second_station_matching import (
    build_method1_preview,
    build_method2_preview,
    find_best_method2_preview,
)
from gui.data_import_wizard import DataImportWizard
from gui.ui_helpers import apply_compact_button_style

logger = logging.getLogger(__name__)


class SecondStationImportWizard(QDialog):
    """Мастер импорта точек с другой точки стояния"""
    
    def __init__(self, existing_data: pd.DataFrame, parent=None, belt_count_from_first_import: Optional[int] = None):
        super().__init__(parent)
        self.existing_data = existing_data
        self.result_data = None
        self.transformation_audit = None
        self.import_method = None  # 1 или 2
        self.transform_quality = None  # Информация о качестве преобразования
        self.station_point_idx = None  # Индекс точки standing для второй съемки
        self.tower_faces_from_first = None  # Количество граней из первого импорта
        
        # Система управления индексами точек для корректного соответствия между таблицей UI и данными
        self.point_mapping = PointMapping()
        self.second_station_import_context: Dict[str, Any] = {}
        self.second_station_import_diagnostics: Dict[str, Any] = {}
        self.second_station_import_audit: Dict[str, Any] = {}
        self.method1_preview: Optional[Dict[str, Any]] = None
        self.second_station_belt_mapping: Dict[int, int] = {}
        self.method2_preview: Optional[Dict[str, Any]] = None
        self._preview_restore_data: Optional[pd.DataFrame] = None
        self._preview_restore_visualization_data: Optional[Dict[str, Any]] = None
        
        # ВАЖНО: Количество поясов из первого импорта передается из MainWindow
        # Это значение, которое пользователь указал при первом импорте
        if belt_count_from_first_import is not None:
            self.belt_count_from_first = belt_count_from_first_import
            logger.info(f"Получено количество поясов из первого импорта: {self.belt_count_from_first}")
        else:
            # Fallback: пытаемся определить из данных (не идеально, но лучше чем ничего)
            self.belt_count_from_first = None
        
        self.init_ui()
        self._determine_belt_count_from_first_import()  # Определяем/проверяем количество поясов при инициализации
        self._determine_tower_faces_from_first_import()
    
    def init_ui(self):
        """Инициализация интерфейса"""
        self.setWindowTitle('Импорт с другой точки стояния')
        self.setModal(True)
        self.resize(1200, 800)
        self.setMinimumSize(1000, 700)
        
        dialog_layout = QVBoxLayout(self)
        dialog_layout.setContentsMargins(8, 8, 8, 8)
        dialog_layout.setSpacing(6)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        dialog_layout.addWidget(scroll_area)

        content_widget = QWidget()
        scroll_area.setWidget(content_widget)
        main_layout = QVBoxLayout(content_widget)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)
        
        # Заголовок (компактный)
        title = QLabel('Импорт данных с дополнительной точки стояния')
        title.setStyleSheet('font-size: 12pt; font-weight: bold; padding: 4px;')
        main_layout.addWidget(title)
        
        # Выбор метода (компактный)
        method_group = QGroupBox('Метод импорта')
        method_layout = QVBoxLayout()
        method_layout.setContentsMargins(8, 6, 8, 6)
        method_layout.setSpacing(4)
        
        self.method_group = QButtonGroup(self)
        
        self.method1_radio = QRadioButton('Метод 1: Преобразование Гельмерта (3+ точки)')
        self.method1_radio.setChecked(True)
        self.method_group.addButton(self.method1_radio, 1)
        method_layout.addWidget(self.method1_radio)
        
        method1_desc = QLabel('Сопоставьте минимум 3 точки. Будет применено преобразование Гельмерта.')
        method1_desc.setStyleSheet('color: #666; font-size: 9pt; padding-left: 24px; margin-bottom: 2px;')
        method_layout.addWidget(method1_desc)
        
        self.method2_radio = QRadioButton('Метод 2: Поворот вокруг базовой точки')
        self.method_group.addButton(self.method2_radio, 2)
        method_layout.addWidget(self.method2_radio)
        
        method2_desc = QLabel('Выберите одну совпадающую точку на поясе. Угол рассчитывается автоматически.')
        method2_desc.setStyleSheet('color: #666; font-size: 9pt; padding-left: 24px;')
        method_layout.addWidget(method2_desc)
        
        method_group.setLayout(method_layout)
        main_layout.addWidget(method_group)
        
        # Параметры (компактный)
        params_group = QGroupBox('Параметры')
        params_layout = QFormLayout()
        params_layout.setSpacing(4)
        params_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        params_layout.setContentsMargins(8, 6, 8, 6)
        
        # Информация о количестве поясов из первого импорта
        belt_count_info_layout = QHBoxLayout()
        belt_count_label = QLabel('Количество поясов (из первого импорта):')
        self.belt_count_label_value = QLabel('---')
        self.belt_count_label_value.setStyleSheet('font-weight: bold; color: #1976D2;')
        self.belt_count_label_value.setToolTip('Количество поясов из первого импорта (не изменяется)')
        belt_count_info_layout.addWidget(belt_count_label)
        belt_count_info_layout.addWidget(self.belt_count_label_value)
        belt_count_info_layout.addStretch()
        params_layout.addRow(belt_count_info_layout)
        
        # Параметр порога слияния точек
        self.merge_tolerance_spin = QDoubleSpinBox()
        self.merge_tolerance_spin.setRange(0.01, 1.0)
        self.merge_tolerance_spin.setSingleStep(0.01)
        self.merge_tolerance_spin.setValue(0.1)
        self.merge_tolerance_spin.setDecimals(3)
        self.merge_tolerance_spin.setSuffix(' м')
        self.merge_tolerance_spin.setToolTip('Расстояние для объединения одинаковых точек')
        params_layout.addRow('Порог слияния точек:', self.merge_tolerance_spin)
        
        # Параметр максимально допустимой ошибки (RMSE)
        self.max_rmse_spin = QDoubleSpinBox()
        self.max_rmse_spin.setRange(0.001, 1.0)
        self.max_rmse_spin.setSingleStep(0.01)
        self.max_rmse_spin.setValue(0.05)
        self.max_rmse_spin.setDecimals(3)
        self.max_rmse_spin.setSuffix(' м')
        self.max_rmse_spin.setToolTip(
            'Максимально допустимая среднеквадратичная ошибка (RMSE) преобразования.\n'
            'Если ошибка превышает это значение, будет показано предупреждение.'
        )
        params_layout.addRow('Макс. допустимая ошибка (RMSE):', self.max_rmse_spin)
        
        # Параметры для метода 2 (поворот)
        # Количество граней берется из первого импорта и не изменяется
        self.tower_faces_label = QLabel('Грани башни:')
        self.tower_faces_spin = QSpinBox()
        self.tower_faces_spin.setRange(3, 8)
        self.tower_faces_spin.setValue(4)
        self.tower_faces_spin.setToolTip('Количество граней башни (определяется автоматически из первого импорта, изменению не подлежит)')
        self.tower_faces_spin.setEnabled(False)  # Отключаем изменение - берется из первого импорта
        tower_faces_layout = QHBoxLayout()
        tower_faces_layout.addWidget(self.tower_faces_label)
        tower_faces_layout.addWidget(self.tower_faces_spin)
        tower_faces_layout.addWidget(QLabel('(из первого импорта)'))
        params_layout.addRow(tower_faces_layout)
        
        self.rotation_angle_spin = QDoubleSpinBox()
        self.rotation_angle_spin.setRange(-360.0, 360.0)
        self.rotation_angle_spin.setSingleStep(1.0)
        self.rotation_angle_spin.setValue(14.5)
        self.rotation_angle_spin.setDecimals(1)
        self.rotation_angle_spin.setSuffix(' °')
        self.rotation_angle_spin.setToolTip('Угол между линиями (в плане XY). Можно изменить вручную или авторасчетом.')
        params_layout.addRow('Угол между линиями:', self.rotation_angle_spin)
        
        # Выбор направления поворота (компактный)
        rotation_dir_layout = QHBoxLayout()
        rotation_dir_layout.setContentsMargins(0, 0, 0, 0)
        rotation_dir_layout.setSpacing(10)
        self.rotation_direction_cw = QRadioButton('По часовой')
        self.rotation_direction_ccw = QRadioButton('Против часовой')
        self.rotation_direction_cw.setChecked(True)
        rotation_dir_layout.addWidget(self.rotation_direction_cw)
        rotation_dir_layout.addWidget(self.rotation_direction_ccw)
        rotation_dir_layout.addStretch()
        params_layout.addRow('Направление поворота:', rotation_dir_layout)

        # Тип профиля и размер (для смещения после зеркалирования)
        self.profile_type_combo = QComboBox()
        self.profile_type_combo.addItems(['—', 'Труба', 'Уголок'])
        self.profile_type_combo.setCurrentIndex(0)
        params_layout.addRow('Профиль пояса:', self.profile_type_combo)

        self.profile_size_spin = QDoubleSpinBox()
        self.profile_size_spin.setRange(0.0, 10.0)
        self.profile_size_spin.setSingleStep(0.01)
        self.profile_size_spin.setDecimals(3)
        self.profile_size_spin.setSuffix(' м')
        self.profile_size_spin.setToolTip('Диаметр трубы или толщина уголка (в метрах)')
        self.profile_size_spin.setValue(0.0)
        params_layout.addRow('Диаметр/толщина:', self.profile_size_spin)

        # (удалено) Нормализация радиуса и тип пояса — возврат к исходному UI
        
        # Кнопка для автоматического расчета угла (компактная)
        self.auto_calculate_angle_btn = QPushButton('Авто расчет угла')
        self.auto_calculate_angle_btn.setToolTip('Рассчитать угол на основе количества граней башни (360° / количество граней)')
        self.auto_calculate_angle_btn.clicked.connect(self._auto_calculate_angle)
        apply_compact_button_style(self.auto_calculate_angle_btn, width=150, min_height=28)
        self.auto_angle_was_used = False
        params_layout.addRow('', self.auto_calculate_angle_btn)
        
        # Чекбокс: Достроить недостающий пояс после импорта
        self.autocomplete_belt_checkbox = QCheckBox('Достроить недостающий пояс после импорта')
        self.autocomplete_belt_checkbox.setChecked(False)
        params_layout.addRow('', self.autocomplete_belt_checkbox)
        
        params_group.setLayout(params_layout)
        main_layout.addWidget(params_group)
        
        # Кнопка загрузки (компактная)
        load_layout = QHBoxLayout()
        load_layout.setSpacing(8)
        
        self.load_btn = QPushButton('📂 Загрузить второй файл')
        self.load_btn.clicked.connect(self.load_second_station_file)
        apply_compact_button_style(self.load_btn, width=200, min_height=32)
        load_layout.addWidget(self.load_btn)
        load_layout.addStretch()
        
        main_layout.addLayout(load_layout)

        self.quality_summary_label = QLabel('')
        self.quality_summary_label.setWordWrap(True)
        self.quality_summary_label.setStyleSheet(
            'background: #f6f8fa; border: 1px solid #d0d7de; padding: 6px; color: #333;'
        )
        self.quality_summary_label.hide()
        main_layout.addWidget(self.quality_summary_label)
        
        # Разделитель для данных
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Существующие точки (компактный)
        existing_group = QGroupBox('Существующие точки')
        existing_layout = QVBoxLayout()
        existing_layout.setContentsMargins(6, 6, 6, 6)
        existing_layout.setSpacing(4)
        
        # Блок выбора соединяемой точки (первый импорт)
        self.connect_first_layout = QHBoxLayout()
        self.connect_first_layout.setSpacing(6)
        self.connect_first_label = QLabel('Соединяемая точка:')
        self.connect_first_combo = QComboBox()
        self.connect_first_layout.addWidget(self.connect_first_label)
        self.connect_first_layout.addWidget(self.connect_first_combo)
        existing_layout.addLayout(self.connect_first_layout)
        
        self.existing_table = QTableWidget()
        self.existing_table.setMinimumHeight(200)
        self.existing_table.setSizePolicy(self.existing_table.sizePolicy().horizontalPolicy(), QSizePolicy.Policy.Expanding)
        self.existing_table.setColumnCount(4)
        self.existing_table.setHorizontalHeaderLabels(['Название', 'X (м)', 'Y (м)', 'Z (м)'])
        self.existing_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        existing_layout.addWidget(self.existing_table)
        
        existing_group.setLayout(existing_layout)
        splitter.addWidget(existing_group)
        
        # Новые точки (компактный)
        new_group = QGroupBox('Новые точки (с другой точки стояния)')
        new_layout = QVBoxLayout()
        new_layout.setContentsMargins(6, 6, 6, 6)
        new_layout.setSpacing(4)
        
        # Блок выбора соединяемой точки (второй импорт)
        self.connect_second_layout = QHBoxLayout()
        self.connect_second_layout.setSpacing(6)
        self.connect_second_label = QLabel('Соединяемая точка:')
        self.connect_second_combo = QComboBox()
        self.connect_second_layout.addWidget(self.connect_second_label)
        self.connect_second_layout.addWidget(self.connect_second_combo)
        new_layout.addLayout(self.connect_second_layout)
        
        self.new_table = QTableWidget()
        self.new_table.setMinimumHeight(200)
        self.new_table.setSizePolicy(self.new_table.sizePolicy().horizontalPolicy(), QSizePolicy.Policy.Expanding)
        self.new_table.setColumnCount(6)
        self.new_table.setHorizontalHeaderLabels(['Название', 'X (м)', 'Y (м)', 'Z (м)', 'Соответствие', 'Остаток (м)'])
        self.new_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.new_table.setColumnWidth(4, 150)
        self.new_table.setColumnWidth(5, 100)
        new_layout.addWidget(self.new_table)
        
        # Кнопка для автоматического сопоставления (компактная)
        auto_match_btn = QPushButton('🎯 Авто сопоставление')
        auto_match_btn.clicked.connect(self.auto_match_points)
        apply_compact_button_style(auto_match_btn, width=150, min_height=28)
        new_layout.addWidget(auto_match_btn)
        
        new_group.setLayout(new_layout)
        splitter.addWidget(new_group)
        
        splitter.setStretchFactor(0, 50)
        splitter.setStretchFactor(1, 50)
        main_layout.addWidget(splitter)
        
        # Кнопки (компактные)
        button_layout = QHBoxLayout()
        button_layout.setSpacing(8)
        button_layout.addStretch()
        
        import_btn = QPushButton('✓ Импорт')
        import_btn.clicked.connect(self.do_import)
        apply_compact_button_style(import_btn, width=100, min_height=32)
        button_layout.addWidget(import_btn)
        
        cancel_btn = QPushButton('Отмена')
        cancel_btn.clicked.connect(self.reject)
        apply_compact_button_style(cancel_btn, width=100, min_height=32)
        button_layout.addWidget(cancel_btn)
        
        dialog_layout.addLayout(button_layout)

        self.method1_radio.toggled.connect(self._handle_method_selection_changed)
        self.method2_radio.toggled.connect(self._handle_method_selection_changed)
        self.rotation_direction_cw.toggled.connect(lambda _checked: self._update_method2_preview_from_selection())
        self.rotation_direction_ccw.toggled.connect(lambda _checked: self._update_method2_preview_from_selection())
        self.rotation_angle_spin.valueChanged.connect(lambda _value: self._update_method2_preview_from_selection())
        
        # Заполняем существующие точки
        self._populate_existing_table()
    
    def _determine_belt_count_from_first_import(self):
        """Определяет количество поясов из первого импорта и отображает его
        
        ВАЖНО: Количество поясов должно быть передано из MainWindow при создании.
        Если не передано, пытаемся определить из данных (максимальный номер пояса).
        """
        # Если количество поясов уже определено (передано из MainWindow), используем его
        if self.belt_count_from_first is not None:
            logger.info(f"Используется переданное количество поясов из первого импорта: {self.belt_count_from_first}")
        elif 'belt' in self.existing_data.columns:
            # Fallback: определяем из данных как максимальный номер пояса
            belts_from_first = self.existing_data['belt'].dropna()
            if len(belts_from_first) > 0:
                self.belt_count_from_first = int(belts_from_first.max())
                logger.warning(f"Количество поясов не было передано, определено из данных: {self.belt_count_from_first} "
                             f"(может быть неточно, если не все пояса заполнены)")
            else:
                self.belt_count_from_first = 4  # Значение по умолчанию
                logger.warning("Не найдено поясов в данных, используем значение по умолчанию: 4")
        else:
            self.belt_count_from_first = 4  # Значение по умолчанию
            logger.warning("Колонка 'belt' не найдена, используем значение по умолчанию: 4")
        
        # Обновляем отображение
        if hasattr(self, 'belt_count_label_value'):
            self.belt_count_label_value.setText(str(self.belt_count_from_first))
        
        logger.info(f"Финальное количество поясов из первого импорта: {self.belt_count_from_first}")
    
    def _determine_tower_faces_from_first_import(self):
        """Определяет количество граней башни из первого импорта"""
        # ВАЖНО: Количество граней башни равно количеству поясов
        # Используем значение, переданное из MainWindow
        if self.belt_count_from_first is not None:
            self.tower_faces_from_first = self.belt_count_from_first
            self.tower_faces_spin.setValue(self.belt_count_from_first)
            logger.info(f"Количество граней установлено равным количеству поясов из первого импорта: {self.belt_count_from_first}")
            # Устанавливаем дефолт угла между линиями: 360 / граней
            try:
                if self.belt_count_from_first > 0:
                    default_angle = 360.0 / float(self.belt_count_from_first)
                    self.rotation_angle_spin.setValue(default_angle)
            except Exception:
                pass
            return
        
        # Fallback: определяем из данных
        if 'belt' not in self.existing_data.columns:
            logger.warning("Колонка 'belt' не найдена в первом импорте, используем значение по умолчанию")
            self.tower_faces_from_first = 4
            self.tower_faces_spin.setValue(4)
            return

        if 'faces' in self.existing_data.columns:
            faces_from_first = self.existing_data['faces'].dropna()
            if len(faces_from_first) > 0:
                self.tower_faces_from_first = int(faces_from_first.max())
                self.tower_faces_spin.setValue(self.tower_faces_from_first)
                logger.info(f"Количество граней определено по колонке faces: {self.tower_faces_from_first}")
                try:
                    default_angle = 360.0 / float(self.tower_faces_from_first)
                    self.rotation_angle_spin.setValue(default_angle)
                except Exception:
                    pass
                return
        
        # Определяем как максимальный номер пояса
        belts_from_first = self.existing_data['belt'].dropna()
        if len(belts_from_first) > 0:
            self.tower_faces_from_first = int(belts_from_first.max())
            self.tower_faces_spin.setValue(self.tower_faces_from_first)
            logger.info(f"Количество граней определено как максимальный номер пояса: {self.tower_faces_from_first}")
            try:
                default_angle = 360.0 / float(self.tower_faces_from_first)
                self.rotation_angle_spin.setValue(default_angle)
            except Exception:
                pass
        else:
            self.tower_faces_from_first = 4
            self.tower_faces_spin.setValue(4)
            logger.warning("Не удалось определить количество граней, используем значение по умолчанию: 4")
            try:
                self.rotation_angle_spin.setValue(90.0)
            except Exception:
                pass
    
    def _populate_existing_table(self):
        """Заполнить таблицу существующих точек"""
        self.existing_table.setRowCount(len(self.existing_data))
        
        self.connect_first_combo.clear()
        for i, (idx, row) in enumerate(self.existing_data.iterrows()):
            self.existing_table.setItem(i, 0, QTableWidgetItem(str(row.get('name', f'Точка {idx}'))))
            self.existing_table.setItem(i, 1, QTableWidgetItem(f"{row['x']:.3f}"))
            self.existing_table.setItem(i, 2, QTableWidgetItem(f"{row['y']:.3f}"))
            self.existing_table.setItem(i, 3, QTableWidgetItem(f"{row['z']:.3f}"))
            # Заполняем список выбора точки для соединения (первый импорт)
            name = row.get('name', f'Точка {idx}')
            self.connect_first_combo.addItem(f"{name} (Z={row['z']:.3f})", idx)
        
        logger.info(f"Заполнено {len(self.existing_data)} существующих точек")
    
    def _populate_new_table(self, data: pd.DataFrame):
        """Заполнить таблицу новых точек"""
        # Очищаем предыдущие соответствия
        self.point_mapping.clear()
        
        self.new_table.setRowCount(len(data))
        
        self.connect_second_combo.clear()
        
        for i, (idx, row) in enumerate(data.iterrows()):
            # Сохраняем соответствие между строкой таблицы и индексом данных
            point_name = row.get('name', f'Точка {idx}')
            self.point_mapping.add_mapping(table_row=i, data_index=idx, point_name=point_name)
            
            self.new_table.setItem(i, 0, QTableWidgetItem(str(point_name)))
            self.new_table.setItem(i, 1, QTableWidgetItem(f"{row['x']:.3f}"))
            self.new_table.setItem(i, 2, QTableWidgetItem(f"{row['y']:.3f}"))
            self.new_table.setItem(i, 3, QTableWidgetItem(f"{row['z']:.3f}"))
            
            # Создаем выпадающий список для выбора соответствия
            combo = QComboBox()
            combo.addItem('-- Не выбрано --', -1)
            for j, (idx1, row1) in enumerate(self.existing_data.iterrows()):
                combo.addItem(f"{row1.get('name', f'Точка {idx1}')}" , idx1)
            self.new_table.setCellWidget(i, 4, combo)

            # Единичный выбор пары в методе 2: выбор в одной строке сбрасывает остальные
            combo.currentIndexChanged.connect(lambda _v, r=i: self._handle_match_change_single_selection(r))
            combo.currentIndexChanged.connect(lambda _v, r=i: self._update_method2_preview_from_selection(r))
            combo.currentIndexChanged.connect(lambda _v: self._refresh_quality_summary())
            
            # Колонка для остатков (пока пустая)
            self.new_table.setItem(i, 5, QTableWidgetItem(''))
            
            # Заполняем список выбора точки для соединения (второй импорт)
            self.connect_second_combo.addItem(f"{point_name} (Z={row['z']:.3f})", idx)
        
        logger.info(f"Заполнено {len(data)} новых точек, создано {self.point_mapping.size()} соответствий")
    
    def _handle_match_change_single_selection(self, changed_row: int):
        """Единичный выбор соответствия в методе 2.
        Если выбран метод 2 и в строке changed_row выбран элемент != -1,
        сбрасываем выбор во всех остальных строках на "-- Не выбрано --".
        """
        # Только для метода 2
        if not hasattr(self, 'method2_radio') or not self.method2_radio.isChecked():
            return
        combo_changed = self.new_table.cellWidget(changed_row, 4)
        if combo_changed is None:
            return
        selected_data = combo_changed.currentData()
        if selected_data is None or selected_data == -1:
            return
        for r in range(self.new_table.rowCount()):
            if r == changed_row:
                continue
            combo = self.new_table.cellWidget(r, 4)
            if combo is not None and combo.currentData() != -1:
                combo.setCurrentIndex(0)
    
    def _get_method2_target_angle_deg(self) -> float:
        tower_faces = self.tower_faces_from_first if self.tower_faces_from_first is not None else 4
        user_angle = float(self.rotation_angle_spin.value()) if hasattr(self, 'rotation_angle_spin') else 0.0
        auto_calculated_angle = 360.0 / tower_faces if tower_faces > 0 else 90.0
        use_auto_angle = getattr(self, 'auto_angle_was_used', False) or abs(user_angle - auto_calculated_angle) < 0.5
        return float(auto_calculated_angle if use_auto_angle else abs(user_angle))

    def _get_method2_prefer_clockwise(self) -> Optional[bool]:
        if not hasattr(self, 'rotation_direction_cw') or not hasattr(self, 'rotation_angle_spin'):
            return None
        rotation_direction = 1 if self.rotation_direction_cw.isChecked() else -1
        if float(self.rotation_angle_spin.value()) < 0:
            rotation_direction = -rotation_direction
        return rotation_direction > 0

    def _find_table_row_by_second_index(self, second_index: Any) -> Optional[int]:
        for row in range(self.new_table.rowCount()):
            if self.point_mapping.get_data_index(row) == second_index:
                return row
        return None

    def _build_method2_preview_for_pair(
        self,
        second_index: Any,
        existing_index: Any,
    ) -> Optional[Dict[str, Any]]:
        if not hasattr(self, 'second_station_data'):
            return None
        if second_index not in self.second_station_data.index or existing_index not in self.existing_data.index:
            return None

        tower_faces = self.tower_faces_from_first if self.tower_faces_from_first is not None else 4
        return build_method2_preview(
            self.existing_data,
            self.second_station_data,
            existing_index=existing_index,
            second_index=second_index,
            tower_faces=tower_faces,
            target_angle_deg=self._get_method2_target_angle_deg(),
            merge_tolerance=float(self.merge_tolerance_spin.value()),
            prefer_clockwise=self._get_method2_prefer_clockwise(),
        )

    def _get_or_build_method2_preview(
        self,
        second_index: Any,
        existing_index: Any,
    ) -> Optional[Dict[str, Any]]:
        if (
            self.method2_preview is not None
            and self.method2_preview.get('second_index') == second_index
            and self.method2_preview.get('existing_index') == existing_index
        ):
            return self.method2_preview
        return self._build_method2_preview_for_pair(second_index, existing_index)

    def _capture_preview_restore_state(self) -> None:
        parent = self.parent()
        editor = getattr(parent, 'editor_3d', None) if parent is not None else None
        if editor is None:
            return

        if self._preview_restore_data is None and hasattr(editor, 'get_data'):
            try:
                self._preview_restore_data = editor.get_data()
            except Exception:
                self._preview_restore_data = self.existing_data.copy()

        if self._preview_restore_visualization_data is None:
            self._preview_restore_visualization_data = getattr(editor, '_last_visualization_data', None)

    def _apply_method2_preview_visualization(self, preview: Dict[str, Any]) -> None:
        parent = self.parent()
        editor = getattr(parent, 'editor_3d', None) if parent is not None else None
        if editor is None:
            return

        self._capture_preview_restore_state()
        preview_data = pd.concat(
            [self.existing_data.copy(), preview['transformed_second'].copy()],
            ignore_index=True,
        )
        try:
            editor.set_data(preview_data)
            editor.set_belt_connection_lines(preview.get('visualization_data', {}))
        except Exception:
            logger.warning("РќРµ СѓРґР°Р»РѕСЃСЊ РѕР±РЅРѕРІРёС‚СЊ 3D preview РґР»СЏ РјРµС‚РѕРґР° 2", exc_info=True)

    def _apply_method1_preview_visualization(self, preview: Dict[str, Any]) -> None:
        parent = self.parent()
        editor = getattr(parent, 'editor_3d', None) if parent is not None else None
        if editor is None:
            return

        self._capture_preview_restore_state()
        preview_data = pd.concat(
            [self.existing_data.copy(), preview['transformed_second'].copy()],
            ignore_index=True,
        )
        try:
            editor.set_data(preview_data)
            editor.set_belt_connection_lines({})
        except Exception:
            logger.warning("Не удалось обновить 3D preview для метода 1", exc_info=True)

    def _clear_method2_preview_visualization(self) -> None:
        parent = self.parent()
        editor = getattr(parent, 'editor_3d', None) if parent is not None else None
        if editor is None:
            return

        restore_data = self._preview_restore_data if self._preview_restore_data is not None else self.existing_data
        try:
            if isinstance(restore_data, pd.DataFrame):
                editor.set_data(restore_data.copy())
            else:
                editor.set_data(self.existing_data.copy())
            editor.set_belt_connection_lines(self._preview_restore_visualization_data or {})
        except Exception:
            logger.warning("РќРµ СѓРґР°Р»РѕСЃСЊ РѕС‡РёСЃС‚РёС‚СЊ 3D preview РјРµС‚РѕРґР° 2", exc_info=True)

    def _handle_method_selection_changed(self, _checked: bool) -> None:
        if self.method2_radio.isChecked():
            self._update_method2_preview_from_selection()
        else:
            self.method2_preview = None
            if self.method1_preview is not None:
                self._apply_method1_preview_visualization(self.method1_preview)
            else:
                self._clear_method2_preview_visualization()
            self._refresh_quality_summary()

    def _update_method2_preview_from_selection(self, preferred_row: Optional[int] = None) -> None:
        if not hasattr(self, 'second_station_data') or not self.method2_radio.isChecked():
            self.method2_preview = None
            self._clear_method2_preview_visualization()
            self._refresh_quality_summary()
            return

        selected_pair: Optional[Tuple[Any, Any]] = None
        candidate_rows: List[int] = []
        if preferred_row is not None:
            candidate_rows.append(preferred_row)
        candidate_rows.extend(row for row in range(self.new_table.rowCount()) if row != preferred_row)

        for row in candidate_rows:
            combo = self.new_table.cellWidget(row, 4)
            if combo is None:
                continue
            existing_index = combo.currentData()
            if existing_index is None or existing_index == -1:
                continue
            second_index = self.point_mapping.get_data_index(row)
            if second_index is None:
                continue
            selected_pair = (second_index, existing_index)
            break

        if selected_pair is None:
            self.method2_preview = None
            self._clear_method2_preview_visualization()
            self._refresh_quality_summary()
            return

        second_index, existing_index = selected_pair
        preview = self._build_method2_preview_for_pair(second_index, existing_index)
        self.method2_preview = preview
        if preview is not None:
            self._apply_method2_preview_visualization(preview)
        else:
            self._clear_method2_preview_visualization()
        self._refresh_quality_summary()

    def _update_residuals_column(self, residuals: np.ndarray, matched_indices: List[int]):
        """Обновить колонку остаточных невязок в таблице"""
        for i, residual in zip(matched_indices, residuals):
            if i < self.new_table.rowCount():
                item = QTableWidgetItem(f"{residual:.6f}")
                # Цветовое кодирование: красный для больших ошибок, зеленый для малых
                if residual > 0.01:
                    item.setForeground(QColor(220, 53, 69))  # Красный
                elif residual > 0.001:
                    item.setForeground(QColor(255, 193, 7))  # Желтый
                else:
                    item.setForeground(QColor(40, 167, 69))  # Зеленый
                self.new_table.setItem(i, 5, item)
    
    def _safe_memberships(self, value: Any) -> List[int]:
        if value is None or (isinstance(value, float) and np.isnan(value)):
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
        result: List[int] = []
        for item in decoded:
            try:
                result.append(int(item))
            except (TypeError, ValueError):
                continue
        return result

    def _collect_matching_summary(self) -> Dict[str, Any]:
        matched_rows: List[Dict[str, Any]] = []
        unmatched_rows: List[Dict[str, Any]] = []

        for row in range(self.new_table.rowCount()):
            combo = self.new_table.cellWidget(row, 4)
            point_name_item = self.new_table.item(row, 0)
            point_name = point_name_item.text() if point_name_item else f'Row {row}'
            selected_idx = combo.currentData() if combo is not None else -1
            residual_item = self.new_table.item(row, 5)
            residual_value = None
            if residual_item and residual_item.text().strip():
                try:
                    residual_value = float(residual_item.text())
                except ValueError:
                    residual_value = None

            if selected_idx is not None and selected_idx != -1:
                matched_rows.append({
                    'row': row,
                    'point_name': point_name,
                    'existing_index': int(selected_idx),
                    'residual': residual_value,
                })
            else:
                unmatched_rows.append({
                    'row': row,
                    'point_name': point_name,
                })

        residuals = [row['residual'] for row in matched_rows if row['residual'] is not None]
        return {
            'matched_count': len(matched_rows),
            'unmatched_count': len(unmatched_rows),
            'matched_rows': matched_rows,
            'unmatched_rows': unmatched_rows,
            'max_residual': max(residuals) if residuals else None,
            'mean_residual': float(np.mean(residuals)) if residuals else None,
        }

    def _build_structure_validation(self, data: pd.DataFrame) -> Dict[str, Any]:
        warnings: List[str] = []
        belt_numbers: List[int] = []
        missing_belts: List[int] = []
        part_conflicts: List[str] = []

        if 'belt' in data.columns:
            for value in data['belt'].dropna():
                try:
                    belt_numbers.append(int(value))
                except (TypeError, ValueError):
                    warnings.append(f"Некорректное значение пояса: {value}")
            belt_numbers = sorted(set(belt_numbers))
            if belt_numbers:
                expected = list(range(belt_numbers[0], belt_numbers[-1] + 1))
                missing_belts = [belt for belt in expected if belt not in belt_numbers]
                if missing_belts:
                    warnings.append(f"Нарушена непрерывность нумерации поясов: отсутствуют {missing_belts}")

        if 'is_station' in data.columns:
            station_mask = data['is_station'].eq(True)
            station_count = int(station_mask.sum())
            zero_station_count = int(
                (station_mask & data['x'].round(6).eq(0.0) & data['y'].round(6).eq(0.0)).sum()
            )
            if station_count != 1:
                warnings.append(f"Ожидалась одна station-точка, фактически найдено {station_count}")
            if zero_station_count > 1:
                warnings.append(f"Найдено несколько station-точек с координатами (0, 0): {zero_station_count}")
        else:
            station_count = 0
            zero_station_count = 0

        if 'tower_part' in data.columns:
            part_numbers: List[int] = []
            for idx, row in data.iterrows():
                part_value = row.get('tower_part')
                if pd.isna(part_value):
                    continue
                try:
                    part_num = int(part_value)
                    part_numbers.append(part_num)
                except (TypeError, ValueError):
                    part_conflicts.append(f'Строка {idx}: некорректное значение tower_part={part_value}')
                    continue

                memberships = self._safe_memberships(row.get('tower_part_memberships'))
                if memberships and part_num not in memberships:
                    part_conflicts.append(
                        f'Строка {idx}: основная часть {part_num} отсутствует в memberships {memberships}'
                    )
                if bool(row.get('is_part_boundary', False)) and len(memberships) < 2:
                    part_conflicts.append(
                        f'Строка {idx}: граничная точка должна принадлежать минимум двум частям'
                    )
            if part_numbers:
                unique_parts = sorted(set(part_numbers))
                expected_parts = list(range(unique_parts[0], unique_parts[-1] + 1))
                missing_parts = [part for part in expected_parts if part not in unique_parts]
                if missing_parts:
                    warnings.append(f"Нарушена непрерывность частей башни: отсутствуют {missing_parts}")
        else:
            unique_parts = []

        if part_conflicts:
            warnings.extend(part_conflicts)

        return {
            'belt_numbers': belt_numbers,
            'missing_belts': missing_belts,
            'station_count': station_count,
            'zero_station_count': zero_station_count,
            'tower_parts': unique_parts,
            'warnings': warnings,
        }

    def _compose_quality_summary(self) -> str:
        lines: List[str] = []
        if self.second_station_import_context:
            lines.append(
                f"Формат второй съемки: {self.second_station_import_context.get('source_format', 'unknown')} "
                f"({self.second_station_import_context.get('parser_strategy', 'n/a')})"
            )
            confidence = self.second_station_import_context.get('confidence')
            if confidence is not None:
                lines.append(f"Уверенность импорта: {float(confidence):.2f}")

        if self.new_table.rowCount() > 0:
            matching = self._collect_matching_summary()
            lines.append(
                f"Сопоставление: matched={matching['matched_count']}, unmatched={matching['unmatched_count']}"
            )
            if matching['max_residual'] is not None:
                lines.append(
                    f"Невязки: mean={matching['mean_residual']:.6f} м, max={matching['max_residual']:.6f} м"
                )

        if self.transform_quality:
            lines.append(f"Преобразование: метод {self.transform_quality.get('method', '?')}")
            if self.transform_quality.get('rmse') is not None:
                lines.append(
                    f"RMSE={self.transform_quality['rmse']:.6f} м, "
                    f"max={self.transform_quality.get('max_error', 0.0):.6f} м"
                )
            if self.transform_quality.get('quality_warning'):
                lines.append("Есть предупреждение по качеству преобразования")

        if self.method1_radio.isChecked() and self.method1_preview:
            preview = self.method1_preview
            lines.append(f"Method 1 preview: matched={preview.get('matched_pair_count', 0)}")
            local_order = preview.get('second_visible_order_left_to_right', [])
            mapped_order = preview.get('visible_mapping_sequence', [])
            if local_order:
                lines.append(
                    f"2nd station left-to-right: {'-'.join(str(v) for v in local_order)}"
                )
            if mapped_order:
                lines.append(
                    f"Clockwise global belts: {'-'.join(str(v) for v in mapped_order)}"
                )
            station_delta = preview.get('station_angle_delta_deg')
            if station_delta is not None and np.isfinite(station_delta):
                side = preview.get('station_side') or ('right' if station_delta > 0 else 'left')
                lines.append(f"Station side: {side}, delta={station_delta:.2f} deg")
            trimmed_mean = preview.get('shared_trimmed_mean')
            if trimmed_mean is not None and np.isfinite(trimmed_mean):
                lines.append(
                    f"Preview overlap: close={preview.get('shared_close_count', 0)}, trimmed={trimmed_mean:.3f} m"
                )

        if self.method2_radio.isChecked() and self.method2_preview:
            preview = self.method2_preview
            lines.append(
                f"Preview РјРµС‚РѕРґР° 2: {preview.get('second_name', '?')} -> {preview.get('existing_name', '?')}"
            )
            local_order = preview.get('second_visible_order_left_to_right', [])
            mapped_order = preview.get('visible_mapping_sequence', [])
            expected_order = preview.get('expected_visible_mapping_sequence', [])
            if local_order:
                lines.append(
                    f"2-СЏ СЃС‚Р°РЅС†РёСЏ СЃР»РµРІР° РЅР°РїСЂР°РІРѕ: {'-'.join(str(v) for v in local_order)}"
                )
            if mapped_order:
                lines.append(
                    f"Preview РІРЅСѓС‚СЂРµРЅРЅРµРіРѕ РјР°РїРїРёРЅРіР°: {'-'.join(str(v) for v in mapped_order)}"
                )
            if expected_order and expected_order != mapped_order:
                lines.append(
                    f"РћР¶РёРґР°РµРјС‹Р№ РІРёРґ РїРѕ СЃС‚РѕСЏРЅРёСЏРј: {'-'.join(str(v) for v in expected_order)}"
                )
            station_delta = preview.get('station_angle_delta_deg')
            if station_delta is not None and np.isfinite(station_delta):
                lines.append(
                    f"Preview СЃС‚Р°РЅС†РёР№: О”={station_delta:.2f}В°, РїРѕРІРѕСЂРѕС‚={preview.get('angle_deg', 0.0):.2f}В°"
                )
            trimmed_mean = preview.get('shared_trimmed_mean')
            if trimmed_mean is not None and np.isfinite(trimmed_mean):
                lines.append(
                    f"Preview overlap: close={preview.get('shared_close_count', 0)}, trimmed={trimmed_mean:.3f} Рј"
                )

        warnings = list((self.second_station_import_diagnostics or {}).get('warnings', []))
        if warnings:
            lines.append(f"Предупреждения импорта: {len(warnings)}")

        return '\n'.join(lines).strip()

    def _refresh_quality_summary(self) -> None:
        text = self._compose_quality_summary()
        if text:
            self.quality_summary_label.setText(text)
            self.quality_summary_label.show()
        else:
            self.quality_summary_label.hide()

    def _finalize_transformation_audit(self, method: int, merged_data: pd.DataFrame) -> None:
        matching = self._collect_matching_summary()
        structure_validation = self._build_structure_validation(merged_data)
        generated_mask = (
            merged_data['is_generated'].fillna(False).astype(bool)
            if 'is_generated' in merged_data.columns else pd.Series(False, index=merged_data.index)
        )
        generated_belts = []
        if generated_mask.any() and 'belt' in merged_data.columns:
            generated_belts = sorted(
                {int(value) for value in merged_data.loc[generated_mask, 'belt'].dropna().tolist()}
            )
        audit = {
            'method': method,
            'import_context': dict(self.second_station_import_context or {}),
            'import_diagnostics': dict(self.second_station_import_diagnostics or {}),
            'import_wizard_audit': dict(self.second_station_import_audit or {}),
            'matching': matching,
            'transformation_quality': dict(self.transform_quality or {}),
            'post_merge_validation': structure_validation,
            'autocomplete_audit': {
                'enabled': bool(getattr(self, 'autocomplete_belt_checkbox', None) and self.autocomplete_belt_checkbox.isChecked()),
                'generated_points': int(generated_mask.sum()),
                'generated_belts': generated_belts,
            },
        }
        self.transformation_audit = audit

        if self.second_station_import_diagnostics:
            diag = dict(self.second_station_import_diagnostics)
            details = dict(diag.get('details') or {})
            details['second_station_audit'] = audit
            diag['details'] = details
            diag['transformation_quality'] = dict(self.transform_quality or {})
            self.second_station_import_diagnostics = diag

        self._refresh_quality_summary()

    def load_second_station_file(self):
        """Загрузка файла с другой точки standing"""
        # Получаем последнюю папку из настроек или из parent (MainWindow)
        last_dir = ''
        try:
            # Пробуем получить из parent (MainWindow)
            if self.parent() and hasattr(self.parent(), 'last_open_dir'):
                last_dir = self.parent().last_open_dir or ''
            # Если не удалось, используем QSettings напрямую
            if not last_dir:
                from PyQt6.QtCore import QSettings
                settings = QSettings('GeoVertical', 'GeoVerticalAnalyzerPaths')
                last_dir = settings.value('last_open_dir', '')
        except Exception:
            pass
        
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            'Загрузить файл с другой точки стояния',
            last_dir,
            'Все поддерживаемые (*.csv *.txt *.shp *.geojson *.json *.dxf *.job *.jxl *.jobxml *.xml *.raw);;'
            'CSV файлы (*.csv *.txt);;'
            'Shapefile (*.shp);;'
            'GeoJSON (*.geojson *.json);;'
            'DXF файлы (*.dxf);;'
            'Trimble файлы (*.job *.jxl *.jobxml *.xml);;'
            'FieldGenius RAW (*.raw)'
        )
        
        if file_path:
            # Сохраняем папку, из которой был загружен файл
            import os
            from PyQt6.QtCore import QSettings
            settings = QSettings('GeoVertical', 'GeoVerticalAnalyzerPaths')
            last_dir = os.path.dirname(file_path)
            settings.setValue('last_open_dir', last_dir)
            # Также обновляем в parent, если это MainWindow
            if self.parent() and hasattr(self.parent(), 'last_open_dir'):
                self.parent().last_open_dir = last_dir
        
        if not file_path:
            return
        
        try:
            # Загружаем данные
            loaded = load_survey_data(file_path)
            raw_data = loaded.data
            self.second_station_import_context = loaded.to_context_dict()
            self.second_station_import_diagnostics = loaded.diagnostics.to_dict()
            
            if raw_data is None or raw_data.empty:
                QMessageBox.warning(self, 'Ошибка', 'Не удалось загрузить данные из файла')
                return
            
            # Проверяем наличие необходимых колонок
            if not all(col in raw_data.columns for col in ['x', 'y', 'z']):
                QMessageBox.warning(self, 'Ошибка', 'Файл должен содержать колонки x, y, z')
                return
            
            logger.info(f"Загружено {len(raw_data)} точек из файла с другой точки стояния")
            
            # ВАЖНО: Используем количество поясов, определенное при инициализации
            # Если не определено, определяем сейчас
            if self.belt_count_from_first is None:
                self._determine_belt_count_from_first_import()
            
            belt_count_from_first = self.belt_count_from_first if self.belt_count_from_first is not None else 4
            
            logger.info(f"Используется количество поясов из первого импорта: {belt_count_from_first}")
            logger.info(f"Это значение будет установлено в DataImportWizard и не может быть изменено")
            
            # Создаем настройки для второго импорта с количеством поясов из первого
            second_import_settings = {
                'belt_count': belt_count_from_first,  # Используем количество поясов из первого импорта
                'read_only': True  # Делаем поле только для чтения, чтобы нельзя было изменить
            }
            
            # Открываем мастер импорта для выбора точек и сортировки
            # Передаем количество поясов из первого импорта
            import_wizard = DataImportWizard(
                raw_data,
                saved_settings=second_import_settings,
                import_payload=loaded.to_context_dict(),
                parent=self,
            )
            
            if import_wizard.exec() != QDialog.DialogCode.Accepted:
                logger.info("Пользователь отменил мастер импорта данных")
                return
            
            # Получаем обработанные данные из мастера
            processed_data = import_wizard.get_result()
            self.second_station_import_audit = import_wizard.get_import_audit()
            
            if processed_data is None or processed_data.empty:
                QMessageBox.warning(self, 'Ошибка', 'Не были выбраны точки для импорта')
                return
            
            # Получаем индекс точки standing из мастера и находим её в обработанных данных
            self.station_point_idx = None
            if hasattr(import_wizard, 'station_point_idx') and import_wizard.station_point_idx is not None:
                # Ищем точку standing в обработанных данных по флагу is_station
                if 'is_station' in processed_data.columns:
                    station_points = processed_data[processed_data['is_station'] == True]
                    if not station_points.empty:
                        # Берем первую найденную точку standing
                        self.station_point_idx = station_points.index[0]
                        station_name = station_points.iloc[0].get('name', 'Unknown')
                        logger.info(f"Точка standing для второй съемки найдена: {station_name} (индекс в обработанных данных: {self.station_point_idx})")
                    else:
                        logger.warning("Точка standing была выбрана в мастере, но не найдена в обработанных данных")
                else:
                    logger.debug("Колонка is_station отсутствует в обработанных данных")
            
            # Сохраняем обработанные данные
            self.method1_preview = None
            self.second_station_belt_mapping = {}
            self.method2_preview = None
            self._clear_method2_preview_visualization()
            self.second_station_data = processed_data
            
            # Заполняем таблицу
            self._populate_new_table(processed_data)
            
            self.load_btn.setText(f'✓ Загружено: {len(processed_data)} точек')
            
            logger.info(f"Обработано {len(processed_data)} точек после мастера импорта")
            self._refresh_quality_summary()
            
        except Exception as e:
            logger.error(f"Ошибка загрузки файла: {e}", exc_info=True)
            QMessageBox.critical(self, 'Ошибка', f'Не удалось загрузить файл:\n{str(e)}')
    
    def auto_match_points(self):
        """Автоматическое сопоставление точек"""
        if not hasattr(self, 'second_station_data'):
            return

        if self.method2_radio.isChecked():
            self.method1_preview = None
            self.second_station_belt_mapping = {}
            tower_faces = self.tower_faces_from_first if self.tower_faces_from_first is not None else 4
            preview = find_best_method2_preview(
                self.existing_data,
                self.second_station_data,
                tower_faces=tower_faces,
                target_angle_deg=self._get_method2_target_angle_deg(),
                merge_tolerance=float(self.merge_tolerance_spin.value()),
                prefer_clockwise=self._get_method2_prefer_clockwise(),
            )
            if preview is None:
                self.method2_preview = None
                self._clear_method2_preview_visualization()
                self._refresh_quality_summary()
                QMessageBox.warning(
                    self,
                    'РђРІС‚Рѕ СЃРѕРїРѕСЃС‚Р°РІР»РµРЅРёРµ',
                    'РќРµ СѓРґР°Р»РѕСЃСЊ РЅР°Р№С‚Рё СѓСЃС‚РѕР№С‡РёРІСѓСЋ Р±Р°Р·РѕРІСѓСЋ РїР°СЂСѓ РґР»СЏ РјРµС‚РѕРґР° 2.'
                )
                return

            target_row = self._find_table_row_by_second_index(preview['second_index'])
            if target_row is None:
                QMessageBox.warning(
                    self,
                    'РђРІС‚Рѕ СЃРѕРїРѕСЃС‚Р°РІР»РµРЅРёРµ',
                    'РќРµ СѓРґР°Р»РѕСЃСЊ РѕС‚РѕР±СЂР°Р·РёС‚СЊ РЅР°Р№РґРµРЅРЅСѓСЋ РїР°СЂСѓ РІ С‚Р°Р±Р»РёС†Рµ.'
                )
                return

            for row in range(self.new_table.rowCount()):
                combo = self.new_table.cellWidget(row, 4)
                if combo is None:
                    continue
                combo.blockSignals(True)
                combo.setCurrentIndex(0)
                combo.blockSignals(False)

            combo = self.new_table.cellWidget(target_row, 4)
            if combo is None:
                return

            for item_idx in range(combo.count()):
                if combo.itemData(item_idx) == preview['existing_index']:
                    combo.blockSignals(True)
                    combo.setCurrentIndex(item_idx)
                    combo.blockSignals(False)
                    break

            self.method2_preview = preview
            self._update_method2_preview_from_selection(target_row)

            local_order = '-'.join(str(v) for v in preview.get('second_visible_order_left_to_right', []))
            mapped_order = '-'.join(str(v) for v in preview.get('visible_mapping_sequence', []))
            QMessageBox.information(
                self,
                'РЎРѕРїРѕСЃС‚Р°РІР»РµРЅРёРµ Р·Р°РІРµСЂС€РµРЅРѕ',
                'Р”Р»СЏ РјРµС‚РѕРґР° 2 Р°РІС‚РѕРјР°С‚РёС‡РµСЃРєРё РІС‹Р±СЂР°РЅР° РѕРґРЅР° Р±Р°Р·РѕРІР°СЏ РїР°СЂР°.\n'
                f"РўРѕС‡РєРё: {preview.get('second_name', '?')} -> {preview.get('existing_name', '?')}\n"
                f"2-СЏ СЃС‚Р°РЅС†РёСЏ СЃР»РµРІР° РЅР°РїСЂР°РІРѕ: {local_order or 'n/a'}\n"
                f"Preview РјР°РїРїРёРЅРіР°: {mapped_order or 'n/a'}"
            )
            self._refresh_quality_summary()
            return

        if self.method1_radio.isChecked():
            tower_faces = self.tower_faces_from_first if self.tower_faces_from_first is not None else 4
            preview = build_method1_preview(
                self.existing_data,
                self.second_station_data,
                tower_faces=tower_faces,
                target_angle_deg=self._get_method2_target_angle_deg(),
                merge_tolerance=float(self.merge_tolerance_spin.value()),
                prefer_clockwise=self._get_method2_prefer_clockwise(),
            )
            if preview is None:
                self.method1_preview = None
                self.second_station_belt_mapping = {}
                self._clear_method2_preview_visualization()
                self._refresh_quality_summary()
                QMessageBox.warning(
                    self,
                    'Авто сопоставление',
                    'Не удалось автоматически подобрать устойчивое соответствие точек для метода 1.'
                )
                return

            self.method2_preview = None
            for row in range(self.new_table.rowCount()):
                combo = self.new_table.cellWidget(row, 4)
                if combo is None:
                    continue
                combo.blockSignals(True)
                combo.setCurrentIndex(0)
                combo.blockSignals(False)

            applied_pairs = 0
            for pair in preview.get('matched_pairs', []):
                target_row = self._find_table_row_by_second_index(pair['second_index'])
                if target_row is None:
                    continue
                combo = self.new_table.cellWidget(target_row, 4)
                if combo is None:
                    continue
                for item_idx in range(combo.count()):
                    if combo.itemData(item_idx) == pair['existing_index']:
                        combo.blockSignals(True)
                        combo.setCurrentIndex(item_idx)
                        combo.blockSignals(False)
                        applied_pairs += 1
                        break

            self.method1_preview = preview
            self.second_station_belt_mapping = dict(preview.get('belt_mapping', {}))
            self._apply_method1_preview_visualization(preview)
            self._refresh_quality_summary()

            local_order = '-'.join(str(v) for v in preview.get('second_visible_order_left_to_right', []))
            mapped_order = '-'.join(str(v) for v in preview.get('visible_mapping_sequence', []))
            station_delta = preview.get('station_angle_delta_deg')
            station_text = 'n/a'
            if station_delta is not None and np.isfinite(station_delta):
                station_text = f"{preview.get('station_side', 'unknown')} ({station_delta:.2f}°)"
            QMessageBox.information(
                self,
                'Сопоставление завершено',
                'Для метода 1 автоматически выбраны совпадающие точки.\n'
                f"Совпадений: {applied_pairs}\n"
                f"2-я станция слева направо: {local_order or 'n/a'}\n"
                f"Глобальные пояса по часовой: {mapped_order or 'n/a'}\n"
                f"Положение станции: {station_text}"
            )
            return

        tolerance = self.merge_tolerance_spin.value()
        matched_count = 0
        
        for i in range(self.new_table.rowCount()):
            # Используем point_mapping для получения корректного индекса данных
            data_index = self.point_mapping.get_data_index(i)
            if data_index is None:
                logger.warning(f"Не найдено соответствие для строки таблицы {i}, пропускаем")
                continue
            
            # Получаем точку из данных по сохраненному индексу
            if data_index not in self.second_station_data.index:
                logger.warning(f"Индекс {data_index} не найден в second_station_data, пропускаем")
                continue
            
            new_point = self.second_station_data.loc[data_index]
            combo = self.new_table.cellWidget(i, 4)
            
            if combo is None:
                continue
            
            # Находим ближайшую точку
            min_distance = float('inf')
            best_match_idx = -1
            
            for j, (idx, existing_point) in enumerate(self.existing_data.iterrows()):
                dx = new_point['x'] - existing_point['x']
                dy = new_point['y'] - existing_point['y']
                dz = new_point['z'] - existing_point['z']
                distance = np.sqrt(dx**2 + dy**2 + dz**2)
                
                if distance < min_distance:
                    min_distance = distance
                    best_match_idx = idx
            
            # Если точка близка, сопоставляем
            if min_distance <= tolerance:
                # Находим индекс в combo
                for k in range(combo.count()):
                    if combo.itemData(k) == best_match_idx:
                        combo.setCurrentIndex(k)
                        matched_count += 1
                        break
        
        QMessageBox.information(
            self,
            'Сопоставление завершено',
            f'Автоматически сопоставлено {matched_count} из {self.new_table.rowCount()} точек.'
        )
        self._refresh_quality_summary()

    def reject(self):
        self.method1_preview = None
        self.second_station_belt_mapping = {}
        self.method2_preview = None
        self._clear_method2_preview_visualization()
        super().reject()

    def closeEvent(self, event):
        self.method1_preview = None
        self.second_station_belt_mapping = {}
        self.method2_preview = None
        self._clear_method2_preview_visualization()
        super().closeEvent(event)

    def do_import(self):
        """Выполнить импорт"""
        if not hasattr(self, 'second_station_data'):
            QMessageBox.warning(self, 'Ошибка', 'Сначала загрузите файл с другой точки стояния')
            return
        
        # Определяем метод
        if self.method1_radio.isChecked():
            self.import_method = 1
        else:
            self.import_method = 2
        
        if self.import_method == 1:
            self._merge_method1()
        else:
            self._merge_method2()
    
    def _merge_method1(self):
        """Вариант 1: Объединение с использованием преобразования Гельмерта (3+ общих точек)"""
        logger.info("Объединение по методу 1 (преобразование Гельмерта)")

        second_station_data_for_merge = self.second_station_data.copy()
        if self.second_station_belt_mapping and 'belt' in second_station_data_for_merge.columns:
            second_station_data_for_merge['belt'] = second_station_data_for_merge['belt'].map(
                lambda value: (
                    self.second_station_belt_mapping.get(int(value), int(value))
                    if pd.notna(value) else value
                )
            )
        
        # Получаем все сопоставленные пары точек
        matched_pairs = []
        for i in range(self.new_table.rowCount()):
            combo = self.new_table.cellWidget(i, 4)
            if combo:
                selected_idx = combo.currentData()
                if selected_idx is not None and selected_idx != -1:
                    # Используем point_mapping для получения корректного индекса данных
                    data_index = self.point_mapping.get_data_index(i)
                    if data_index is None:
                        logger.warning(f"Не найдено соответствие для строки таблицы {i}, пропускаем точку")
                        continue
                    
                    # Получаем точку из данных по сохраненному индексу
                    if data_index not in second_station_data_for_merge.index:
                        logger.warning(f"Индекс {data_index} не найден в second_station_data, пропускаем точку")
                        continue
                    
                    new_point = second_station_data_for_merge.loc[data_index]
                    existing_point = self.existing_data.loc[selected_idx]
                    matched_pairs.append((i, data_index, new_point, existing_point))
        
        # Проверяем количество сопоставленных точек
        if len(matched_pairs) < 3:
            QMessageBox.warning(
                self,
                'Недостаточно точек',
                f'Для метода 1 необходимо сопоставить минимум 3 точки.\n'
                f'Сейчас сопоставлено: {len(matched_pairs)}'
            )
            return
        
        logger.info(f"Найдено {len(matched_pairs)} сопоставленных точек для преобразования Гельмерта")
        
        # Исключаем standing точки из вычисления параметров преобразования
        regular_second, standing_second = self._filter_standing_points(second_station_data_for_merge)
        regular_existing, _ = self._filter_standing_points(self.existing_data)
        
        # Подготавливаем массивы точек для преобразования (только обычные точки)
        points_source = []
        points_target = []
        
        # matched_pairs содержит: (table_row, data_index, new_point, existing_point)
        for table_row, data_index, new_point, existing_point in matched_pairs:
            # Пропускаем standing точки при вычислении параметров
            if 'is_station' in new_point and pd.notna(new_point.get('is_station', False)) and new_point['is_station']:
                logger.debug(f"Пропущена standing точка {new_point.get('name', 'Unknown')} при вычислении параметров Гельмерта")
                continue
            if 'is_station' in existing_point and pd.notna(existing_point.get('is_station', False)) and existing_point['is_station']:
                logger.debug(f"Пропущена standing точка {existing_point.get('name', 'Unknown')} при вычислении параметров Гельмерта")
                continue
            
            points_source.append([new_point['x'], new_point['y'], new_point['z']])
            points_target.append([existing_point['x'], existing_point['y'], existing_point['z']])
        
        # Проверяем, что осталось достаточно точек после исключения standing
        if len(points_source) < 3:
            QMessageBox.warning(
                self,
                'Недостаточно точек',
                f'После исключения standing точек осталось только {len(points_source)} точек.\n'
                f'Для метода 1 необходимо минимум 3 обычные точки (не standing).'
            )
            return
        
        points_source = np.array(points_source)
        points_target = np.array(points_target)
        
        # Вычисляем параметры преобразования Гельмерта
        try:
            transform_result = compute_helmert_parameters(points_source, points_target)
            
            if not transform_result.get('success', True):
                QMessageBox.warning(
                    self,
                    'Предупреждение',
                    f'Преобразование выполнено, но с предупреждением:\n{transform_result.get("message", "Неизвестная ошибка")}'
                )
            
            # Валидируем качество преобразования перед применением
            max_rmse = self.max_rmse_spin.value()
            max_error_threshold = max_rmse * 2.0  # Максимальная ошибка в 2 раза больше RMSE
            is_valid, warning_message, recommendations = self._validate_transformation_quality(
                transform_result, max_rmse=max_rmse, max_error=max_error_threshold
            )
            
            # Показываем предупреждение, если качество плохое
            if not is_valid:
                reply = QMessageBox.warning(
                    self,
                    'Предупреждение о качестве преобразования',
                    warning_message + "\n\nПродолжить импорт несмотря на проблемы?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.No:
                    logger.info("Пользователь отменил импорт из-за плохого качества преобразования")
                    return
            
            # Применяем преобразование ко всем точкам второй съемки
            transformed_data = apply_helmert_transform(second_station_data_for_merge, transform_result)
            
            # Показываем результаты
            rmse = transform_result['rmse']
            residuals = transform_result['residuals']
            max_error = np.max(residuals)
            
            # Вычисляем остаточные невязки для сопоставленных точек
            quality_info = evaluate_transformation_quality(points_source, points_target, transform_result)
            
            # Обновляем колонку остатков в таблице
            matched_indices = [pair[0] for pair in matched_pairs]
            self._update_residuals_column(residuals, matched_indices)
            
            # Показываем информацию о качестве преобразования
            info_msg = (
                f'Преобразование Гельмерта выполнено успешно.\n\n'
                f'Параметры:\n'
                f'  Сдвиг: Tx={transform_result["params"][0]:.4f} м, '
                f'Ty={transform_result["params"][1]:.4f} м, '
                f'Tz={transform_result["params"][2]:.4f} м\n'
                f'  Повороты: ω={np.degrees(transform_result["params"][3]):.4f}°, '
                f'φ={np.degrees(transform_result["params"][4]):.4f}°, '
                f'κ={np.degrees(transform_result["params"][5]):.4f}°\n'
                f'  Масштаб: {transform_result["params"][6]:.6f}\n\n'
                f'Качество преобразования:\n'
                f'  RMSE: {rmse:.6f} м\n'
                f'  Максимальная ошибка: {max_error:.6f} м\n'
                f'  Средняя ошибка: {quality_info["mean_error"]:.6f} м\n\n'
                f'Остаточные невязки обновлены в таблице.'
            )
            
            QMessageBox.information(
                self,
                'Результаты преобразования',
                info_msg
            )
            
            # Сохраняем информацию о преобразовании для отображения в UI
            scale = float(transform_result['params'][6])
            self.transform_quality = {
                'method': 1,
                'rmse': rmse,
                'max_error': max_error,
                'mean_error': quality_info['mean_error'],
                'residuals': residuals,
                'transform_params': transform_result['params'],
                'matched_points': len(points_source),
                'unmatched_points': max(self.new_table.rowCount() - len(matched_pairs), 0),
                'scale': scale,
                'scale_delta_ppm': float((scale - 1.0) * 1_000_000.0),
                'scale_suspected': abs(scale - 1.0) > 0.01,
                'mirror_suspected': scale < 0,
                'quality_warning': warning_message if not is_valid else '',
                'recommendations': recommendations,
            }
            
            # Объединяем данные
            tolerance = self.merge_tolerance_spin.value()
            merged_data = self._merge_points(self.existing_data, transformed_data, tolerance)
            
            if merged_data is not None:
                self.result_data = merged_data
                self._finalize_transformation_audit(method=1, merged_data=merged_data)
                
                # Обновляем данные в главном окне
                self.parent().editor_3d.set_data(merged_data)
                
                # Для метода 1 (Гельмерт) визуализация линий соединения не требуется,
                # так как преобразование применяется ко всем точкам, а не к конкретному поясу
                
                self.accept()
            else:
                QMessageBox.warning(
                    self,
                    'Ошибка',
                    'Не удалось объединить точки после преобразования.'
                )
                
        except Exception as e:
            logger.error(f"Ошибка преобразования Гельмерта: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                'Ошибка',
                f'Не удалось выполнить преобразование Гельмерта:\n{str(e)}'
            )
    
    def _auto_calculate_angle(self):
        """Автоматически рассчитывает угол поворота на основе количества граней"""
        tower_faces = self.tower_faces_spin.value()
        if tower_faces > 0:
            calculated_angle = 360.0 / tower_faces
            self.rotation_angle_spin.setValue(calculated_angle)
            self.auto_angle_was_used = True  # Устанавливаем флаг
            logger.info(f"Автоматически рассчитан угол поворота: {calculated_angle:.1f}° ({tower_faces} граней)")
    
    def _get_base_point_after_transform(self, transformed_data: pd.DataFrame, base_data_index: Any, 
                                       base_original_coords: np.ndarray) -> Optional[np.ndarray]:
        """
        Получить координаты базовой точки после преобразования.
        
        Использует сохраненный индекс базовой точки из mapping для точного определения.
        Fallback используется только если индекс действительно отсутствует.
        
        Args:
            transformed_data: Преобразованные данные (после сдвига или другого преобразования)
            base_data_index: Индекс базовой точки в исходных данных
            base_original_coords: Исходные координаты базовой точки [x, y, z] для fallback
        
        Returns:
            Координаты [x, y] базовой точки после преобразования или None, если не найдена
        """
        # Пытаемся найти точку по сохраненному индексу
        if base_data_index in transformed_data.index:
            base_row = transformed_data.loc[base_data_index]
            base_xy = np.array([base_row['x'], base_row['y']])
            logger.debug(f"Базовая точка после преобразования найдена по индексу {base_data_index}")
            return base_xy
        
        # Fallback: поиск по координатам (только если индекс действительно отсутствует)
        logger.warning(
            f"Индекс базовой точки {base_data_index} не найден в transformed_data, "
            f"используется fallback поиск по координатам"
        )
        
        # Ищем ближайшую точку по XY координатам
        if len(transformed_data) == 0:
            logger.error("transformed_data пуст, невозможно найти базовую точку")
            return None
        
        coords = transformed_data[['x', 'y']].values
        deltas = coords - base_original_coords[:2]
        dists = np.linalg.norm(deltas, axis=1)
        nearest_idx = int(np.argmin(dists)) if len(dists) > 0 else 0
        base_row = transformed_data.iloc[nearest_idx]
        base_xy = np.array([base_row['x'], base_row['y']])
        
        distance = dists[nearest_idx]
        logger.warning(
            f"Fallback: найдена ближайшая точка с индексом {transformed_data.index[nearest_idx]}, "
            f"расстояние={distance:.6f} м"
        )
        
        # Если расстояние слишком большое, это может быть ошибка
        if distance > 0.1:  # 10 см
            logger.error(
                f"Расстояние до ближайшей точки слишком большое ({distance:.6f} м), "
                f"возможно, базовая точка потеряна при преобразовании"
            )
            return None
        
        return base_xy
    
    def _calculate_rotation_angle_simple(self, base_point: np.ndarray, 
                                         first_survey_point: Optional[np.ndarray],
                                         second_survey_point: Optional[np.ndarray],
                                         target_angle_deg: float,
                                         rotation_direction_cw: bool) -> Tuple[float, Optional[str]]:
        """
        Упрощенное вычисление угла поворота на основе базовой точки и одной дополнительной точки из каждой съемки.
        
        Args:
            base_point: Базовая точка [x, y, z] (совпадающая точка из обеих съемок)
            first_survey_point: Дополнительная точка из первой съемки [x, y, z] или None
            second_survey_point: Дополнительная точка из второй съемки [x, y, z] или None
            target_angle_deg: Целевой угол поворота в градусах
            rotation_direction_cw: True если поворот по часовой стрелке, False - против
        
        Returns:
            Кортеж (angle_rad_to_apply, error_message):
            - angle_rad_to_apply: Угол поворота в радианах для применения
            - error_message: Сообщение об ошибке или None, если все в порядке
        """
        # Если дополнительные точки не выбраны, используем только целевой угол
        # ВНИМАНИЕ: Это fallback метод, используется только если новый алгоритм не сработал
        if first_survey_point is None or second_survey_point is None:
            logger.warning(
                "FALLBACK: Дополнительные точки не выбраны, используется только целевой угол. "
                "Рекомендуется использовать новый алгоритм на основе точек на разных поясах."
            )
            target_abs_deg = abs(target_angle_deg)
            target_signed_deg = target_abs_deg if rotation_direction_cw else -target_abs_deg
            angle_rad = domain_rotation_deg_to_math_rad(target_signed_deg)
            return angle_rad, "Используется fallback алгоритм (только целевой угол без учета текущего положения)"
        
        # Вычисляем векторы от базовой точки к дополнительным точкам (в плоскости XY)
        v1_xy = first_survey_point[:2] - base_point[:2]
        v2_xy = second_survey_point[:2] - base_point[:2]
        
        # Проверяем, что векторы не нулевые
        if np.linalg.norm(v1_xy) < 1e-9:
            return 0.0, "Вектор от базовой точки к точке первой съемки слишком мал"
        
        if np.linalg.norm(v2_xy) < 1e-9:
            return 0.0, "Вектор от базовой точки к точке второй съемки слишком мал"
        
        # Нормализуем векторы
        u1 = v1_xy / np.linalg.norm(v1_xy)
        u2 = v2_xy / np.linalg.norm(v2_xy)
        
        # Вычисляем текущий угол между векторами (в градусах, CCW > 0)
        dot = float(np.clip(np.dot(u1, u2), -1.0, 1.0))
        det = float(u1[0] * u2[1] - u1[1] * u2[0])
        current_signed_deg = np.degrees(np.arctan2(det, dot))
        
        logger.info(f"Текущий угол между линиями: {current_signed_deg:.2f}°")
        
        # Целевой подписанный угол: CW отрицательный, CCW положительный (вид сверху)
        target_abs_deg = abs(target_angle_deg)
        target_signed_deg = target_abs_deg if rotation_direction_cw else -target_abs_deg
        
        # Дельта поворота: target_signed - current_signed
        delta_deg = target_signed_deg - current_signed_deg
        
        # Нормализуем в диапазон (-180, 180]
        delta_deg = normalize_signed_angle_deg(delta_deg)
        angle_rad = domain_rotation_deg_to_math_rad(delta_deg)
        
        logger.info(
            f"Вычислен угол поворота: текущий={current_signed_deg:.2f}°, "
            f"целевой={target_signed_deg:.2f}°, дельта={delta_deg:.2f}°"
        )
        
        return angle_rad, None
    
    def _find_point_on_other_belt_at_same_height(self, data: pd.DataFrame, base_point: pd.Series,
                                                 base_belt: int, height_tolerance: float = 0.15) -> Optional[pd.Series]:
        """
        Находит точку на другом поясе на той же высоте, что и базовая точка.
        
        Алгоритм:
        1. Находит все пояса в данных
        2. Определяет следующий пояс после базового (или предыдущий, если базовый - последний)
        3. Фильтрует точки второго пояса по высоте (в пределах tolerance)
        4. Выбирает ближайшую точку к базовой точке по горизонтальному расстоянию
        
        Args:
            data: DataFrame с точками съемки
            base_point: Базовая точка (Series с координатами x, y, z и belt)
            base_belt: Номер базового пояса
            height_tolerance: Допустимое отклонение по высоте в метрах (по умолчанию 0.15 м)
        
        Returns:
            Найденная точка (Series) или None, если точка не найдена
        """
        if 'belt' not in data.columns:
            logger.warning("Колонка 'belt' отсутствует в данных, невозможно найти точку на другом поясе")
            return None
        
        # Получаем все уникальные пояса в данных (исключая standing точки)
        if 'is_station' in data.columns:
            regular_data = data[~data['is_station'].fillna(False).astype(bool)].copy()
        else:
            regular_data = data.copy()
        
        belts = regular_data['belt'].dropna().unique()
        if len(belts) < 2:
            logger.warning(f"Недостаточно поясов в данных: найдено {len(belts)}, требуется минимум 2")
            return None
        
        # Определяем второй пояс
        belts_sorted = sorted([int(b) for b in belts if pd.notna(b)])
        if base_belt not in belts_sorted:
            logger.warning(f"Базовый пояс {base_belt} не найден в данных")
            return None
        
        # Находим индекс базового пояса в отсортированном списке
        base_belt_idx = belts_sorted.index(base_belt)
        
        # Определяем второй пояс:
        # - Если базовый пояс не последний, берем следующий
        # - Если базовый пояс последний, берем предыдущий
        if base_belt_idx < len(belts_sorted) - 1:
            other_belt = belts_sorted[base_belt_idx + 1]
            logger.info(f"Выбран следующий пояс: {other_belt} (базовый пояс: {base_belt})")
        else:
            other_belt = belts_sorted[base_belt_idx - 1]
            logger.info(f"Выбран предыдущий пояс: {other_belt} (базовый пояс: {base_belt})")
        
        # Фильтруем точки второго пояса по высоте
        base_height = float(base_point['z'])
        other_belt_points = regular_data[
            (regular_data['belt'] == other_belt) &
            (np.abs(regular_data['z'] - base_height) <= height_tolerance)
        ].copy()
        
        if len(other_belt_points) == 0:
            logger.warning(
                f"Не найдено точек на поясе {other_belt} на высоте {base_height:.3f} м "
                f"(tolerance={height_tolerance:.3f} м)"
            )
            return None
        
        # Выбираем ближайшую точку к базовой точке по горизонтальному расстоянию (XY)
        base_xy = np.array([base_point['x'], base_point['y']])
        min_distance = float('inf')
        closest_point = None
        
        for idx, point in other_belt_points.iterrows():
            point_xy = np.array([point['x'], point['y']])
            distance = np.linalg.norm(point_xy - base_xy)
            
            if distance < min_distance:
                min_distance = distance
                closest_point = point
        
        if closest_point is not None:
            logger.info(
                f"Найдена точка на поясе {other_belt}: {closest_point.get('name', 'Unknown')}, "
                f"высота={closest_point['z']:.3f} м, расстояние={min_distance:.3f} м"
            )
        
        return closest_point
    
    def _calculate_angle_from_belt_lines(self, base_point_first: pd.Series, point_belt2_first: pd.Series,
                                         base_point_second: pd.Series, point_belt2_second: pd.Series) -> Tuple[float, float, Optional[str]]:
        """
        Вычисляет угол между проекциями линий на плоскость XY.
        
        Алгоритм:
        1. Строит векторы от базовых точек к точкам на поясе 2 (только XY компоненты)
        2. Проецирует векторы на плоскость XY (убирает Z компонент)
        3. Вычисляет угол между проекциями векторов
        4. Возвращает угол в радианах и градусах
        
        Args:
            base_point_first: Базовая точка первой съемки (Series с x, y, z)
            point_belt2_first: Точка на поясе 2 первой съемки (Series с x, y, z)
            base_point_second: Базовая точка второй съемки (Series с x, y, z)
            point_belt2_second: Точка на поясе 2 второй съемки (Series с x, y, z)
        
        Returns:
            Кортеж (angle_rad, angle_deg, error_message):
            - angle_rad: Угол в радианах
            - angle_deg: Угол в градусах
            - error_message: Сообщение об ошибке или None
        """
        # Строим векторы от базовых точек к точкам на поясе 2 (только XY компоненты)
        # Проекция на плоскость XY: убираем Z компонент
        v1_xy = np.array([
            point_belt2_first['x'] - base_point_first['x'],
            point_belt2_first['y'] - base_point_first['y']
        ])
        
        v2_xy = np.array([
            point_belt2_second['x'] - base_point_second['x'],
            point_belt2_second['y'] - base_point_second['y']
        ])
        
        # Проверяем, что векторы не нулевые
        norm_v1 = np.linalg.norm(v1_xy)
        norm_v2 = np.linalg.norm(v2_xy)
        
        if norm_v1 < 1e-9:
            return 0.0, 0.0, "Вектор от базовой точки к точке на поясе 2 первой съемки слишком мал"
        
        if norm_v2 < 1e-9:
            return 0.0, 0.0, "Вектор от базовой точки к точке на поясе 2 второй съемки слишком мал"
        
        # Нормализуем векторы
        u1 = v1_xy / norm_v1
        u2 = v2_xy / norm_v2
        
        # Вычисляем угол между проекциями векторов на плоскость XY
        # Используем atan2 для определения знака угла (CCW > 0)
        dot = float(np.clip(np.dot(u1, u2), -1.0, 1.0))
        det = float(u1[0] * u2[1] - u1[1] * u2[0])  # Определитель для направления
        
        angle_rad = np.arctan2(det, dot)
        angle_deg = np.degrees(angle_rad)
        
        logger.info(
            f"Вычислен угол между проекциями линий: {angle_deg:.2f}° "
            f"(вектор 1: длина={norm_v1:.3f} м, вектор 2: длина={norm_v2:.3f} м)"
        )
        
        return angle_rad, angle_deg, None
    
    def _filter_standing_points(self, data: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Разделяет данные на точки standing и обычные точки.
        
        Standing точки должны быть исключены из вычисления параметров преобразования,
        но включены в применение преобразования.
        
        Args:
            data: DataFrame с точками, может содержать колонку 'is_station'
        
        Returns:
            Кортеж (regular_points, standing_points):
            - regular_points: Обычные точки (без standing)
            - standing_points: Точки standing (is_station=True) или пустой DataFrame
        """
        if 'is_station' not in data.columns:
            return data.copy(), pd.DataFrame(columns=data.columns)
        
        standing_mask = data['is_station'].fillna(False).astype(bool)
        regular_points = data[~standing_mask].copy()
        standing_points = data[standing_mask].copy()
        
        logger.debug(f"Разделение точек: обычных={len(regular_points)}, standing={len(standing_points)}")
        
        return regular_points, standing_points
    
    def _merge_standing_points(self, existing_data: pd.DataFrame, 
                               transformed_data: pd.DataFrame,
                               second_station_original: pd.DataFrame) -> pd.DataFrame:
        """
        Объединяет точки standing из второй съемки с основными данными.
        
        Проверяет на дублирование перед объединением.
        
        Args:
            existing_data: Существующие данные (первая съемка)
            transformed_data: Преобразованные данные второй съемки (уже содержит standing, если они были)
            second_station_original: Исходные данные второй съемки (для получения standing)
        
        Returns:
            DataFrame с объединенными standing точками
        """
        # Получаем standing точки из исходных данных второй съемки
        standing_to_add = pd.DataFrame(columns=existing_data.columns)
        
        if self.station_point_idx is not None and self.station_point_idx in second_station_original.index:
            station_row = second_station_original.loc[self.station_point_idx].copy()
            station_row['is_station'] = True
            standing_to_add = pd.DataFrame([station_row])
        elif 'is_station' in second_station_original.columns:
            standing_mask = second_station_original['is_station'].fillna(False).astype(bool)
            if standing_mask.any():
                standing_to_add = second_station_original[standing_mask].copy()
                standing_to_add['is_station'] = True
        
        # Проверяем, что standing точки не дублируются в transformed_data
        if not standing_to_add.empty and 'is_station' in transformed_data.columns:
            transformed_standing_mask = transformed_data['is_station'].fillna(False).astype(bool)
            if transformed_standing_mask.any():
                # Standing уже есть в transformed_data, не добавляем повторно
                logger.info("Standing точки уже присутствуют в transformed_data, дублирование не требуется")
                standing_to_add = pd.DataFrame(columns=existing_data.columns)
        
        return standing_to_add
    
    def _validate_transformation_quality(self, transform_result: Dict, max_rmse: float = 0.05, 
                                        max_error: float = 0.1) -> Tuple[bool, str, List[str]]:
        """
        Валидирует качество преобразования на основе метрик.
        
        Args:
            transform_result: Результат преобразования с ключами 'rmse', 'residuals', 'max_error'
            max_rmse: Максимально допустимая RMSE в метрах (по умолчанию 0.05 м)
            max_error: Максимально допустимая ошибка в метрах (по умолчанию 0.1 м)
        
        Returns:
            Кортеж (is_valid, warning_message, recommendations):
            - is_valid: True, если качество приемлемое
            - warning_message: Сообщение с предупреждением или пустая строка
            - recommendations: Список рекомендаций по улучшению
        """
        rmse = transform_result.get('rmse', float('inf'))
        residuals = transform_result.get('residuals', np.array([]))
        max_residual = transform_result.get('max_error', np.max(residuals) if len(residuals) > 0 else float('inf'))
        
        recommendations = []
        warnings = []
        
        # Проверка RMSE
        if rmse > max_rmse:
            warnings.append(f"RMSE ({rmse:.6f} м) превышает допустимое значение ({max_rmse:.6f} м)")
            recommendations.append("Проверьте сопоставление точек - возможно, некоторые точки сопоставлены неправильно")
            recommendations.append("Убедитесь, что точки расположены на разных поясах и не являются выбросами")
        
        # Проверка максимальной ошибки
        if max_residual > max_error:
            warnings.append(f"Максимальная ошибка ({max_residual:.6f} м) превышает допустимое значение ({max_error:.6f} м)")
            recommendations.append("Проверьте точки с наибольшими остаточными невязками в таблице")
            recommendations.append("Рассмотрите возможность исключения точек с большими ошибками из сопоставления")
        
        # Проверка распределения ошибок
        if len(residuals) > 0:
            mean_error = np.mean(residuals)
            std_error = np.std(residuals)
            if std_error > mean_error * 2:
                warnings.append(f"Большой разброс ошибок (σ={std_error:.6f} м, μ={mean_error:.6f} м)")
                recommendations.append("Ошибки распределены неравномерно - проверьте качество данных")
        
        is_valid = len(warnings) == 0
        
        if warnings:
            warning_message = "Обнаружены проблемы с качеством преобразования:\n\n" + "\n".join(f"• {w}" for w in warnings)
            if recommendations:
                warning_message += "\n\nРекомендации:\n" + "\n".join(f"• {r}" for r in recommendations)
        else:
            warning_message = ""
        
        return is_valid, warning_message, recommendations
    
    def _remove_matched_belt_points(self, transformed_data: pd.DataFrame, existing_data: pd.DataFrame,
                                   target_belt: int, tolerance: float) -> pd.DataFrame:
        """
        Удаляет только совпавшие точки пояса из второй съемки, а не весь пояс.
        
        Находит точки пояса, которые совпали с точками первой съемки (в пределах tolerance),
        и удаляет только их. Остальные точки пояса сохраняются.
        
        Args:
            transformed_data: Преобразованные данные второй съемки
            existing_data: Данные первой съемки
            target_belt: Номер пояса для обработки
            tolerance: Допустимое расстояние для определения совпадения (метры)
        
        Returns:
            DataFrame с удаленными совпавшими точками пояса
        """
        if 'belt' not in transformed_data.columns or 'belt' not in existing_data.columns:
            logger.warning("Колонка 'belt' отсутствует, пропускаем удаление точек пояса")
            return transformed_data.copy()
        
        # Получаем точки целевого пояса из обеих съемок
        belt_second = transformed_data[transformed_data['belt'] == target_belt].copy()
        belt_first = existing_data[existing_data['belt'] == target_belt].copy()
        
        if belt_second.empty:
            logger.info(f"Пояс {target_belt} отсутствует во второй съемке, нечего удалять")
            return transformed_data.copy()
        
        if belt_first.empty:
            logger.info(f"Пояс {target_belt} отсутствует в первой съемке, удаляем все точки пояса из второй съемки")
            # Если пояс отсутствует в первой съемке, удаляем все точки пояса из второй
            remaining = transformed_data[transformed_data['belt'] != target_belt].copy()
            # Сохраняем standing точки
            if 'is_station' in transformed_data.columns:
                standing_mask = transformed_data['is_station'].fillna(False).astype(bool)
                standing_points = transformed_data[standing_mask].copy()
                remaining = pd.concat([remaining, standing_points], ignore_index=True)
            return remaining
        
        # Находим совпавшие точки пояса
        matched_indices = set()
        for idx2, point2 in belt_second.iterrows():
            # Ищем ближайшую точку в первой съемке на том же поясе
            min_distance = float('inf')
            for idx1, point1 in belt_first.iterrows():
                dx = point2['x'] - point1['x']
                dy = point2['y'] - point1['y']
                dz = point2['z'] - point1['z']
                distance = np.sqrt(dx**2 + dy**2 + dz**2)
                
                if distance < min_distance:
                    min_distance = distance
            
            # Если точка совпала (в пределах tolerance), отмечаем для удаления
            if min_distance <= tolerance:
                matched_indices.add(idx2)
                logger.debug(
                    f"Точка пояса {target_belt} совпала: {point2.get('name', 'Unknown')}, "
                    f"расстояние={min_distance:.6f} м"
                )
        
        # Удаляем совпавшие точки (но не standing)
        remaining = transformed_data.copy()
        if matched_indices:
            # Не удаляем standing точки
            if 'is_station' in remaining.columns:
                standing_mask = remaining['is_station'].fillna(False).astype(bool)
                matched_indices = {idx for idx in matched_indices if not standing_mask.get(idx, False)}
            
            if matched_indices:
                remaining = remaining.drop(index=list(matched_indices))
                logger.info(f"Удалено {len(matched_indices)} совпавших точек пояса {target_belt} из второй съемки")
            else:
                logger.info(f"Все совпавшие точки пояса {target_belt} являются standing, не удаляем")
        else:
            logger.info(f"Не найдено совпавших точек пояса {target_belt} в пределах tolerance={tolerance:.3f} м")
        
        return remaining
    
    def _find_base_point_pair(self, matched_pairs: List) -> Tuple[Any, Any, pd.Series, pd.Series]:
        """
        Находит базовую точку из сопоставленных пар.
        
        Args:
            matched_pairs: Список сопоставленных пар (table_row, data_index, selected_idx, new_point, existing_point)
        
        Returns:
            Кортеж (base_table_row, base_data_index, base_selected_idx, new_base, existing_base)
        
        Raises:
            ValueError: Если нет сопоставленных пар
        """
        if len(matched_pairs) < 1:
            raise ValueError("Необходима минимум одна сопоставленная пара для определения базовой точки")
        
        # Используем первую сопоставленную точку как базовую
        base_table_row, base_data_index, base_selected_idx, new_base, existing_base = matched_pairs[0]
        
        logger.info(
            f"Базовая точка: новая={new_base.get('name', 'Unknown')}, "
            f"существующая={existing_base.get('name', 'Unknown')}"
        )
        logger.info(
            f"Индексы базовой точки: base_table_row={base_table_row}, "
            f"base_data_index={base_data_index}, base_selected_idx={base_selected_idx}"
        )
        
        return base_table_row, base_data_index, base_selected_idx, new_base, existing_base
    
    def _apply_transformations(self, data: pd.DataFrame, base_point_new: pd.Series, 
                               base_point_existing: pd.Series, angle_rad: float,
                               rotation_center: np.ndarray) -> pd.DataFrame:
        """
        Применяет последовательность преобразований: Δz-сдвиг → перенос XY → поворот вокруг Z.
        
        Args:
            data: Данные для преобразования
            base_point_new: Базовая точка из новой съемки
            base_point_existing: Базовая точка из существующей съемки
            angle_rad: Угол поворота в радианах
            rotation_center: Центр поворота [x, y, z]
        
        Returns:
            Преобразованные данные
        """
        # 1) Δz-сдвиг
        delta_z = float(base_point_existing['z'] - base_point_new['z'])
        shifted = shift_points_along_z(data, delta_z)
        
        # 2) Перенос в XY, чтобы базовая точка совпала
        base_original_coords = np.array([base_point_new['x'], base_point_new['y'], base_point_new['z']])
        base_data_index = base_point_new.name if hasattr(base_point_new, 'name') else None
        
        base_xy_after_shift = self._get_base_point_after_transform(
            shifted, base_data_index, base_original_coords
        )
        
        if base_xy_after_shift is None:
            raise ValueError("Не удалось найти базовую точку после сдвига")
        
        target_xy = np.array([base_point_existing['x'], base_point_existing['y']])
        txy = target_xy - base_xy_after_shift
        translated = translate_points_xy(shifted, float(txy[0]), float(txy[1]))
        
        # Поворот будет применен отдельно в вызывающем коде после вычисления угла
        # Возвращаем только translated (после сдвига и переноса)
        return translated
    
    def _merge_method2(self):
        """Вариант 2: Регистрация по одному поясу с автоматическим расчетом угла поворота"""
        logger.info("Объединение по методу 2 (регистрация по поясу)")
        
        # Детальное логирование для отладки
        logger.info(f"=== НАЧАЛО МЕТОДА 2: РЕГИСТРАЦИЯ ПО ПОЯСУ ===")
        logger.info(f"Входные данные:")
        logger.info(f"  second_station_data: {len(self.second_station_data) if hasattr(self, 'second_station_data') else 'None'} точек")
        logger.info(f"  existing_data: {len(self.existing_data)} точек")
        logger.info(f"  tower_faces_from_first: {self.tower_faces_from_first}")
        
        # Находим базовую точку сопоставления (минимум одна точка)
        matched_pairs = []
        for i in range(self.new_table.rowCount()):
            combo = self.new_table.cellWidget(i, 4)
            if combo:
                selected_idx = combo.currentData()
                if selected_idx is not None and selected_idx != -1:
                    # Используем point_mapping для получения корректного индекса данных
                    data_index = self.point_mapping.get_data_index(i)
                    if data_index is None:
                        logger.warning(f"Не найдено соответствие для строки таблицы {i}, пропускаем точку")
                        continue
                    
                    # Получаем точку из данных по сохраненному индексу
                    if data_index not in self.second_station_data.index:
                        logger.warning(f"Индекс {data_index} не найден в second_station_data, пропускаем точку")
                        continue
                    
                    new_point = self.second_station_data.loc[data_index]
                    existing_point = self.existing_data.loc[selected_idx]
                    matched_pairs.append((i, data_index, selected_idx, new_point, existing_point))
        
        logger.info(f"Найдено сопоставленных точек: {len(matched_pairs)}")
        
        if len(matched_pairs) < 1:
            QMessageBox.warning(
                self,
                'Неверное количество точек',
                'Для метода 2 необходимо выбрать минимум одну пару сопоставленных точек на поясе.'
            )
            return
        
        # Находим базовую точку из сопоставленных пар
        base_table_row, base_idx_new, base_idx_existing, new_base, existing_base = self._find_base_point_pair(matched_pairs)
        method2_preview = self._get_or_build_method2_preview(base_idx_new, base_idx_existing)
        
        # Определяем номер пояса из базовой точки существующих данных
        target_belt = None
        if 'belt' in existing_base and pd.notna(existing_base['belt']):
            target_belt = int(existing_base['belt'])
            logger.info(f"Определен номер пояса из базовой точки: пояс {target_belt}")
        else:
            # Fallback: определяем по высоте
            height_tolerance = 0.15  # метров
            logger.warning("Поле 'belt' не найдено, определение по высоте")
        
        # Определяем пояс для обеих съемок
        if target_belt is not None:
            # Используем номер пояса
            if 'belt' in self.existing_data.columns:
                belt1_points = self.existing_data[
                    self.existing_data['belt'] == target_belt
                ].copy()
            else:
                belt1_points = pd.DataFrame()
            
            if 'belt' in self.second_station_data.columns:
                belt2_points = self.second_station_data[
                    self.second_station_data['belt'] == int(new_base['belt'])
                ].copy()
            else:
                belt2_points = pd.DataFrame()
        else:
            # Fallback: определяем по высоте
            height_tolerance = 0.15  # метров
            belt1_points = self.existing_data[
                np.abs(self.existing_data['z'] - existing_base['z']) <= height_tolerance
            ].copy()
            
            belt2_points = self.second_station_data[
                np.abs(self.second_station_data['z'] - new_base['z']) <= height_tolerance
            ].copy()
        
        if len(belt1_points) == 0 or len(belt2_points) == 0:
            QMessageBox.warning(
                self,
                'Ошибка',
                'Не удалось определить пояс. Проверьте, что точки имеют назначенные пояса или близкие высоты.'
            )
            return
        
        logger.info(f"Найдено точек в поясе: первая съемка={len(belt1_points)}, "
                   f"вторая съемка={len(belt2_points)}, пояс={target_belt}")
        
        # НОВЫЙ АЛГОРИТМ: Находим точки на другом поясе на той же высоте для вычисления угла
        height_tolerance = 0.15  # метров
        point_belt2_first = self._find_point_on_other_belt_at_same_height(
            self.existing_data, existing_base, target_belt, height_tolerance
        )
        point_belt2_second = self._find_point_on_other_belt_at_same_height(
            self.second_station_data, new_base, int(new_base['belt']), height_tolerance
        )
        
        # Инициализируем переменные для угла
        angle_deg_measured = None
        use_fallback = True
        
        # Вычисляем угол между проекциями линий на плоскость XY
        if point_belt2_first is not None and point_belt2_second is not None:
            logger.info("Используется новый алгоритм вычисления угла на основе точек на разных поясах")
            angle_rad_measured, angle_deg_measured, error_msg = self._calculate_angle_from_belt_lines(
                existing_base, point_belt2_first, new_base, point_belt2_second
            )
            
            if error_msg is not None:
                logger.warning(f"Ошибка при вычислении угла: {error_msg}, используется fallback")
                # Fallback на старый алгоритм
                use_fallback = True
                angle_deg_measured = None
            else:
                use_fallback = False
                logger.info(f"Измеренный угол между проекциями линий: {angle_deg_measured:.2f}°")
        else:
            logger.warning("Не удалось найти точки на поясе 2, используется fallback алгоритм")
            use_fallback = True
            angle_deg_measured = None
        
        # Используем количество граней из первого импорта (не изменяется)
        tower_faces = self.tower_faces_from_first if self.tower_faces_from_first is not None else 4
        logger.info(f"Используется количество граней из первого импорта: {tower_faces} (изменению не подлежит)")
        
        # Проверяем корректность количества граней
        if tower_faces <= 0:
            QMessageBox.critical(
                self,
                'Ошибка',
                f'Некорректное количество граней башни: {tower_faces}. Должно быть положительным числом.'
            )
            return
        
        # Определяем целевой угол и направление поворота
        user_angle = self.rotation_angle_spin.value()
        auto_calculated_angle = 360.0 / tower_faces if tower_faces > 0 else 90.0
        
        # Проверяем, была ли использована кнопка автоматического расчета
        use_auto_angle = getattr(self, 'auto_angle_was_used', False) or abs(user_angle - auto_calculated_angle) < 0.5
        
        if use_auto_angle:
            target_angle_deg = auto_calculated_angle
            logger.info(f"Целевой угол (автоматический): {target_angle_deg:.1f}° ({tower_faces} граней)")
        else:
            target_angle_deg = abs(user_angle)
            logger.info(f"Целевой угол (пользовательский): {target_angle_deg:.1f}°")
        
        # Определяем направление поворота
        rotation_direction = 1 if self.rotation_direction_cw.isChecked() else -1
        direction_text = "по часовой стрелке" if rotation_direction > 0 else "против часовой стрелки"
        logger.info(f"Направление поворота: {direction_text}")
        
        # Если пользователь ввел отрицательный угол, меняем направление
        if user_angle < 0:
            rotation_direction = -rotation_direction
            logger.info(f"Отрицательный угол введен, направление изменено")
        
        # Вычисляем угол поворота для применения
        if not use_fallback:
            # Используем измеренный угол и целевой угол для вычисления дельты
            # Дельта = целевой - измеренный (с учетом направления)
            target_signed_deg = target_angle_deg if rotation_direction > 0 else -target_angle_deg
            delta_deg = target_signed_deg - angle_deg_measured
            
            # Нормализуем в диапазон (-180, 180]
            delta_deg = normalize_signed_angle_deg(delta_deg)
            angle_rad_to_apply = domain_rotation_deg_to_math_rad(delta_deg)
            angle_deg_to_apply = delta_deg
            
            logger.info(
                f"Вычислен угол поворота: измеренный={angle_deg_measured:.2f}°, "
                f"целевой={target_signed_deg:.2f}°, дельта={delta_deg:.2f}°"
            )
        else:
            # Fallback: используем старый алгоритм
            logger.info("Используется fallback алгоритм вычисления угла")
            user_angle_val = float(self.rotation_angle_spin.value())
            if abs(user_angle_val) < 1e-6:
                user_angle_val = 360.0 / float(self.tower_faces_from_first or 4)
            
            base_rot = np.array([existing_base['x'], existing_base['y'], existing_base['z']])
            angle_rad_to_apply, error_msg = self._calculate_rotation_angle_simple(
                base_point=base_rot,
                first_survey_point=None,
                second_survey_point=None,
                target_angle_deg=user_angle_val,
                rotation_direction_cw=self.rotation_direction_cw.isChecked()
            )
            angle_deg_to_apply = np.degrees(angle_rad_to_apply)
            
            if error_msg is not None:
                QMessageBox.warning(
                    self,
                    'Предупреждение',
                    f'Проблема при вычислении угла поворота: {error_msg}\n'
                    f'Будет использован только целевой угол без учета текущего положения.'
                )
        
        # Находим индекс базовой точки в отфильтрованных поясах
        # Используем сохраненные индексы вместо поиска по координатам
        # Базовая точка уже известна из matched_pairs, используем её индексы
        
        # Ищем базовую точку в первой съемке по сохраненному индексу
        if base_idx_existing not in belt1_points.index:
            # Если индекс не найден в отфильтрованном поясе, ищем по координатам как fallback
            logger.warning(f"Индекс базовой точки {base_idx_existing} не найден в belt1_points, используем поиск по координатам")
            distances1 = np.sqrt(
                (belt1_points['x'] - existing_base['x'])**2 +
                (belt1_points['y'] - existing_base['y'])**2 +
                (belt1_points['z'] - existing_base['z'])**2
            )
            original_idx1_in_belt = distances1.idxmin()
        else:
            # Используем сохраненный индекс
            original_idx1_in_belt = base_idx_existing
        
        # Ищем базовую точку во второй съемке по сохраненному индексу
        if base_idx_new not in belt2_points.index:
            # Если индекс не найден в отфильтрованном поясе, ищем по координатам как fallback
            logger.warning(f"Индекс базовой точки {base_idx_new} не найден в belt2_points, используем поиск по координатам")
            distances2 = np.sqrt(
                (belt2_points['x'] - new_base['x'])**2 +
                (belt2_points['y'] - new_base['y'])**2 +
                (belt2_points['z'] - new_base['z'])**2
            )
            original_idx2_in_belt = distances2.idxmin()
        else:
            # Используем сохраненный индекс
            original_idx2_in_belt = base_idx_new
        
        # Для register_belt_survey нужны индексы в reset версиях (если они используются)
        # Но лучше избегать reset_index, поэтому создаем mapping для поясов
        belt1_mapping = {}
        belt2_mapping = {}
        for reset_idx, (orig_idx, _) in enumerate(belt1_points.iterrows()):
            belt1_mapping[orig_idx] = reset_idx
        for reset_idx, (orig_idx, _) in enumerate(belt2_points.iterrows()):
            belt2_mapping[orig_idx] = reset_idx
        
        idx1_in_belt = belt1_mapping.get(original_idx1_in_belt, 0)
        idx2_in_belt = belt2_mapping.get(original_idx2_in_belt, 0)
        
        logger.info(f"Индексы базовых точек: первая съемка (reset={idx1_in_belt}, original={original_idx1_in_belt}), "
                   f"вторая съемка (reset={idx2_in_belt}, original={original_idx2_in_belt})")
        
        # Выполняем регистрацию по поясу
        # ВАЖНО: Передаем все точки второй съемки для правильного вычисления общего центра
        # ИСКЛЮЧАЯ точки standing, которые не должны участвовать в преобразовании
        try:
            # Поворачиваем ВСЕ точки второй съемки, включая точку стояния
            second_survey_all = self.second_station_data.copy()
            standing_points_second = None
            if 'is_station' in second_survey_all.columns:
                standing_points_second = second_survey_all[second_survey_all['is_station'] == True].copy()
                logger.info(f"Точек standing во второй съемке: {len(standing_points_second)} (они тоже будут повернуты)")
            
            # Угол уже вычислен выше (angle_rad_to_apply, angle_deg_to_apply)
            base_rot = np.array([existing_base['x'], existing_base['y'], existing_base['z']])
            
            # Применяем последовательность преобразований (сдвиг и перенос)
            try:
                translated = self._apply_transformations(
                    second_survey_all, new_base, existing_base, 
                    0.0, base_rot  # Угол пока 0, применим позже
                )
            except ValueError as e:
                QMessageBox.critical(
                    self,
                    'Ошибка',
                    f'Ошибка при применении преобразований: {str(e)}'
                )
                return
            
            # Применяем поворот к translated (угол уже вычислен выше)
            from core.survey_registration import rotate_points_around_z
            rotated = rotate_points_around_z(translated, angle_rad_to_apply, base_rot)
            if method2_preview is not None:
                rotated = method2_preview['transformed_second'].copy()
                angle_deg_to_apply = float(method2_preview.get('angle_deg', angle_deg_to_apply))
                angle_rad_to_apply = float(np.radians(angle_deg_to_apply))
                angle_deg_measured = method2_preview.get('measured_angle_deg', angle_deg_measured)
                use_fallback = False
            logger.info(f"[Импорт/метод2] Применяемый дельта-поворот: {angle_deg_to_apply:.2f}°")

            # (удалено) Радиальная нормализация — возврат к исходному поведению

            # 4) Удаление совпавших точек пояса второй съемки (после трансформации они должны совпасть)
            # Определяем пояс у базовой точки второй съемки в исходных данных
            belt_to_remove = None
            if method2_preview is not None and pd.notna(new_base.get('belt', None)):
                belt_to_remove = int(
                    method2_preview.get('belt_mapping', {}).get(int(new_base['belt']), int(target_belt or new_base['belt']))
                )
            elif 'belt' in self.second_station_data.columns and pd.notna(new_base.get('belt', None)):
                belt_to_remove = int(new_base['belt'])
            elif target_belt is not None:
                belt_to_remove = int(target_belt)
            
            if belt_to_remove is not None:
                # Используем новый метод для удаления только совпавших точек
                tolerance = self.merge_tolerance_spin.value()
                remaining_second = self._remove_matched_belt_points(
                    rotated, self.existing_data, belt_to_remove, tolerance
                )
            else:
                remaining_second = rotated
                logger.warning("Не удалось определить пояс для удаления у второй съемки — пропущено")
            
            # 5) Объединяем: существующие + оставшиеся из второй съемки
            # Standing точки уже включены в remaining_second (если они не были удалены)
            # Проверяем на дублирование перед объединением
            standing_to_add = self._merge_standing_points(
                self.existing_data, remaining_second, self.second_station_data
            )
            
            # Объединяем данные
            merged_data = pd.concat([
                self.existing_data,
                remaining_second,
                standing_to_add
            ], ignore_index=True)
            
            # Нормализуем колонки belt и is_station
            if 'belt' not in merged_data.columns:
                merged_data['belt'] = np.nan
            if 'is_station' not in merged_data.columns:
                merged_data['is_station'] = False
            merged_data['is_station'] = merged_data['is_station'].fillna(False).astype(bool)
            
            # Сохраняем результат и при необходимости визуализацию
            # Вычисляем delta_z для сохранения в transform_quality
            delta_z = float(existing_base['z'] - new_base['z'])
            
            self.result_data = merged_data
            self.transform_quality = {
                'method': 2,
                'angle_deg': float(angle_deg_to_apply),
                'direction': 1 if self.rotation_direction_cw.isChecked() else -1,
                'delta_z': float(delta_z),
                'matched_points': len(matched_pairs),
                'unmatched_points': max(self.new_table.rowCount() - len(matched_pairs), 0),
                'target_angle_deg': float(target_angle_deg),
                'measured_initial_deg': float(angle_deg_measured) if angle_deg_measured is not None else None,
                'used_fallback': bool(use_fallback),
                'ambiguity_warning': (
                    'Угол определен по fallback-сценарию и требует проверки'
                    if use_fallback else ''
                ),
            }

            # Подготовка данных для визуализации линий
            # Используем найденные точки на поясе 2 для обеих съемок
            try:
                line_data = method2_preview.get('visualization_data') if method2_preview is not None else None
                
                # Используем точки на поясе 2, найденные для вычисления угла
                if line_data is None and point_belt2_first is not None and point_belt2_second is not None:
                    # Получаем координаты точек на поясе 2 после поворота
                    # Для первой съемки точка остается без изменений
                    p1_belt2 = np.array([point_belt2_first['x'], point_belt2_first['y'], point_belt2_first['z']])
                    
                    # Для второй съемки нужно найти точку после поворота
                    p2_belt2_original_idx = point_belt2_second.name if hasattr(point_belt2_second, 'name') else None
                    p2_belt2_rotated = None
                    
                    if p2_belt2_original_idx is not None and p2_belt2_original_idx in rotated.index:
                        p2_row = rotated.loc[p2_belt2_original_idx]
                        p2_belt2_rotated = np.array([p2_row['x'], p2_row['y'], p2_row['z']])
                    else:
                        # Fallback: поиск по координатам или имени
                        if 'name' in point_belt2_second and point_belt2_second['name'] is not None:
                            name_belt2 = point_belt2_second['name']
                            if 'name' in rotated.columns:
                                cand = rotated[rotated['name'] == name_belt2]
                                if not cand.empty:
                                    p2_row = cand.iloc[0]
                                    p2_belt2_rotated = np.array([p2_row['x'], p2_row['y'], p2_row['z']])
                    
                    if p2_belt2_rotated is not None:
                        # Определяем номер второго пояса для метки
                        other_belt_num = None
                        if point_belt2_first is not None and 'belt' in point_belt2_first:
                            other_belt_num = int(point_belt2_first['belt'])
                        
                        # Вычисляем финальный угол после поворота
                        v1f = p1_belt2[:2] - base_rot[:2]
                        v2f = p2_belt2_rotated[:2] - base_rot[:2]
                        measured_final_deg = None
                        if np.linalg.norm(v1f) > 1e-9 and np.linalg.norm(v2f) > 1e-9:
                            u1f = v1f / np.linalg.norm(v1f)
                            u2f = v2f / np.linalg.norm(v2f)
                            dotf = float(np.clip(np.dot(u1f, u2f), -1.0, 1.0))
                            detf = float(u1f[0] * u2f[1] - u1f[1] * u2f[0])
                            measured_final_deg = float(np.degrees(np.arctan2(detf, dotf)))
                            logger.info(
                                f"[Импорт/метод2] Измеренный угол ПОСЛЕ поворота: {measured_final_deg:.2f}° "
                                f"(целевой {target_angle_deg:.2f}°, применено {angle_deg_to_apply:.2f}°)"
                            )
                        
                        target_signed_deg = target_angle_deg if rotation_direction > 0 else -target_angle_deg
                        
                        line_data = {
                            'line1': {
                                'start': base_rot,
                                'end': p1_belt2,
                                'label': f'Линия 1 (первая съёмка, пояс {target_belt} -> пояс {other_belt_num if other_belt_num is not None else "?"})'
                            },
                            'line2': {
                                'start': base_rot,
                                'end': p2_belt2_rotated,
                                'label': f'Линия 2 (вторая съёмка, пояс {target_belt} -> пояс {other_belt_num if other_belt_num is not None else "?"})'
                            },
                            'angle_deg': float(target_signed_deg),
                            'measured_initial_deg': angle_deg_measured if not use_fallback else None,
                            'measured_final_deg': float(measured_final_deg) if measured_final_deg is not None else None
                        }
                
                if line_data is not None:
                    self.transform_quality['visualization_data'] = line_data
                    logger.info(
                        f"[Импорт/метод2] Визуализация линий подготовлена. "
                        f"initial={line_data.get('measured_initial_deg')}, "
                        f"final={line_data.get('measured_final_deg')}, "
                        f"target={line_data.get('angle_deg')}"
                    )
                else:
                    logger.warning("[Импорт/метод2] Не удалось сформировать visualization_data: отсутствуют точки на поясе 2")
            except Exception as viz_e:
                logger.warning(f"Не удалось сформировать данные визуализации линий: {viz_e}", exc_info=True)

            # Обновляем данные и линии в главном окне (перед accept)
            self.parent().editor_3d.set_data(merged_data)
            if 'visualization_data' in self.transform_quality:
                self.parent().editor_3d.set_belt_connection_lines(self.transform_quality['visualization_data'])
                
            # Достроение пояса (по желанию)
            try:
                if self.autocomplete_belt_checkbox.isChecked():
                    from core.belt_completion import complete_missing_belt_parallel_lines
                    faces = int(self.tower_faces_from_first or 4)
                    target_belt_to_fill = None
                    # ищем отсутствующий пояс
                    if 'belt' in self.result_data.columns:
                        present = set(int(b) for b in self.result_data['belt'].dropna().unique())
                        for b in range(1, faces+1):
                            if b not in present:
                                target_belt_to_fill = b
                                break
                    # если не нашли — пробуем заполнить 3 как пример
                    if target_belt_to_fill is None:
                        target_belt_to_fill = 3 if faces >= 3 else 2
                    logger.info(f"[parallel_lines] Старт автодостройки: faces={faces}, target_belt={target_belt_to_fill}")
                    # Пробуем зеркальный метод через вертикальную плоскость по двум точкам (концы line1/line2)
                    from core.belt_completion import complete_missing_belt_mirror
                    vd = self.transform_quality.get('visualization_data', {}) if hasattr(self, 'transform_quality') else {}
                    line1 = vd.get('line1'); line2 = vd.get('line2')
                    merged_after, gen = (self.result_data, pd.DataFrame())
                    if line1 and line2:
                        pa = np.array(line1['end']) if 'end' in line1 else None
                        pb = np.array(line2['end']) if 'end' in line2 else None
                        if pa is not None and pb is not None:
                            logger.info(f"[mirror] Запуск зеркального метода: A={pa}, B={pb}")
                            merged_after, gen = complete_missing_belt_mirror(self.result_data, faces=faces, target_belt=target_belt_to_fill, point_a=pa, point_b=pb, source_belt=1, tolerance=0.15)
                    # Если зеркальный не сработал — параллельные линии
                    if gen is None or gen.empty:
                        from core.belt_completion import complete_missing_belt_parallel_lines
                        merged_after, gen = complete_missing_belt_parallel_lines(self.result_data, faces=faces, target_belt=target_belt_to_fill, tolerance=0.15)
                    if gen is not None and not gen.empty:
                        # При необходимости: смещение отзеркаленных точек пояса в направлении от центра пояса 1
                        try:
                            prof = self.profile_type_combo.currentText() if hasattr(self, 'profile_type_combo') else '—'
                            size = float(self.profile_size_spin.value()) if hasattr(self, 'profile_size_spin') else 0.0
                            if prof in ('Труба', 'Уголок') and size > 0.0:
                                # Центр пояса 1 по обновленным данным
                                b1_df = merged_after[merged_after['belt'] == 1] if 'belt' in merged_after.columns else None
                                if b1_df is not None and not b1_df.empty:
                                    c1x = float(b1_df['x'].mean()); c1y = float(b1_df['y'].mean())
                                    # Попробуем найти сгенерированные точки пояса target_belt_to_fill
                                    gen_mask = (merged_after['belt'] == target_belt_to_fill)
                                    if 'is_generated' in merged_after.columns:
                                        gen_mask = gen_mask & (merged_after['is_generated'] == True)
                                    idxs = merged_after[gen_mask].index.tolist()
                                    for idx in idxs:
                                        x = float(merged_after.at[idx, 'x']); y = float(merged_after.at[idx, 'y'])
                                        vx = x - c1x; vy = y - c1y
                                        norm = (vx*vx + vy*vy) ** 0.5
                                        if norm > 1e-9:
                                            merged_after.at[idx, 'x'] = x + size * (vx / norm)
                                            merged_after.at[idx, 'y'] = y + size * (vy / norm)
                                    logger.info(f"[profile-shift] Смещение пояса {target_belt_to_fill}: тип={prof}, величина={size:.3f} м, точек={len(idxs)}")
                        except Exception as e:
                            logger.warning(f"[profile-shift] Ошибка смещения профиля: {e}")

                        self.result_data = merged_after
                        # обновляем главное окно
                        self.parent().editor_3d.set_data(self.result_data)
                        # Визуализация граней пояса: строим полилинию
                        try:
                            bdf = self.result_data[self.result_data['belt'] == target_belt_to_fill]
                            if bdf is not None and not bdf.empty:
                                from core.planar_orientation import extract_reference_station_xy, sort_points_clockwise

                                ordered = sort_points_clockwise(
                                    bdf,
                                    station_xy=extract_reference_station_xy(self.result_data),
                                )[['x', 'y', 'z']].to_numpy(dtype=float)
                                self.parent().editor_3d.set_belt_polyline(int(target_belt_to_fill), ordered)
                                logger.info(f"[parallel_lines] Визуализация поли-линии пояса {target_belt_to_fill} выполнена")
                        except Exception as viz_e:
                            logger.warning(f"[parallel_lines] Не удалось визуализировать пояс {target_belt_to_fill}: {viz_e}")
                        if hasattr(self.parent(), 'data_table') and self.parent().data_table is not None:
                            self.parent().data_table.set_data(self.result_data)
                        import logging
                        logging.getLogger(__name__).info(f"Автодостроен пояс {target_belt_to_fill} (параллельные линии): добавлено {len(gen)} точек")
                    else:
                        logger.warning("[parallel_lines] Генерация не дала новых точек — проверьте входные пояса 1/2/4")
            except Exception as e:
                logger.warning(f"Автодостройка пояса пропущена: {e}", exc_info=True)

            self._finalize_transformation_audit(method=2, merged_data=self.result_data)
            self.accept()
        except Exception as e:
            logger.error(f"Ошибка метода 2 (новая логика): {e}", exc_info=True)
            QMessageBox.critical(
                self,
                'Ошибка',
                f'Не удалось выполнить объединение (метод 2):\n{str(e)}'
            )
    
    def _merge_points_by_belts(
        self, 
        data1: pd.DataFrame, 
        data2: pd.DataFrame, 
        tolerance: float = 0.1,
        target_belt: Optional[int] = None,
        tower_faces: Optional[int] = None
    ) -> Optional[pd.DataFrame]:
        """
        Объединение точек из двух наборов данных с учетом поясов
        
        Для метода 2 (регистрация по поясу):
        - Если указан target_belt, ВСЕ точки этого пояса из data2 автоматически объединяются
          с соответствующими точками того же пояса из data1
        - Первый проект (data1) остается без изменений
        - Преобразование применено ко ВСЕМ точкам data2 (вся вторая съемка трансформирована вместе)
        
        Args:
            data1: Первый набор данных (остается без изменений)
            data2: Второй набор данных (все точки уже трансформированы)
            tolerance: Допустимое расстояние для объединения точек (метры)
            target_belt: Номер пояса для автоматического объединения всех точек (для метода 2)
        
        Returns:
            Объединенный DataFrame
        """
        # Детальное логирование для отладки
        logger.info(f"=== НАЧАЛО ОБЪЕДИНЕНИЯ ТОЧЕК ПО ПОЯСАМ ===")
        logger.info(f"Входные параметры:")
        logger.info(f"  data1: {len(data1)} точек")
        logger.info(f"  data2: {len(data2)} точек")
        logger.info(f"  tolerance: {tolerance}")
        logger.info(f"  target_belt: {target_belt}")
        
        try:
            # Создаем копию первого набора данных (он остается без изменений)
            merged = data1.copy()
            
            # Счетчики
            matched_count = 0
            added_count = 0
            
            # Множество для отслеживания использованных точек из первой съемки (для целевого пояса)
            used_indices_data1 = set()
            
            # Если указан target_belt, находим все точки этого пояса в обеих съемках
            if target_belt is not None:
                # Точки целевого пояса из первой съемки
                belt1_points = data1[data1['belt'] == target_belt].copy() if 'belt' in data1.columns else pd.DataFrame()
                
                # Точки целевого пояса из второй съемки (уже преобразованные)
                if 'belt' in data2.columns:
                    belt2_points = data2[data2['belt'] == target_belt].copy()
                else:
                    # Если пояса не назначены, определяем по высоте базовой точки
                    # Это fallback на случай, если пояса не были назначены
                    belt2_points = data2.copy()
                
                if not belt1_points.empty and not belt2_points.empty:
                    logger.info(f"Автоматическое объединение пояса {target_belt}: "
                               f"первая съемка={len(belt1_points)} точек, вторая съемка={len(belt2_points)} точек")
                    
                    # Для целевого пояса: агрессивное объединение - увеличиваем tolerance
                    belt_tolerance = tolerance * 3.0  # Увеличиваем для гарантированного объединения всех точек пояса
                    logger.info(f"Tolerance для пояса {target_belt}: {belt_tolerance:.4f} м (обычный: {tolerance:.4f} м)")
                    
                    # Для каждой точки пояса из второй съемки находим ближайшую в первой
                    # Используем жадный алгоритм для оптимального сопоставления
                    # used_indices_data1 уже объявлен выше
                    
                    # Создаем список всех возможных пар с расстояниями
                    # ВАЖНО: Сохраняем исходные индексы из data1 и data2
                    all_pairs = []
                    for idx2_data2, point2 in belt2_points.iterrows():
                        for idx1_data1, point1 in belt1_points.iterrows():
                            # Вычисляем расстояние
                            dx = point2['x'] - point1['x']
                            dy = point2['y'] - point1['y']
                            dz = point2['z'] - point1['z']
                            distance = np.sqrt(dx**2 + dy**2 + dz**2)
                            # Сохраняем исходные индексы из data1 и data2
                            all_pairs.append((distance, idx2_data2, idx1_data1, point2, point1))
                    
                    # Сортируем по расстоянию (от меньшего к большему)
                    all_pairs.sort(key=lambda x: x[0])
                    
                    # Объединяем, начиная с ближайших пар
                    for distance, idx2_data2, idx1_data1, point2, point1 in all_pairs:
                        # Пропускаем, если точка из data1 уже использована
                        if idx1_data1 in used_indices_data1:
                            continue
                        
                        # Проверяем, что расстояние не слишком большое
                        if distance > belt_tolerance:
                            logger.warning(f"Расстояние между точками пояса {target_belt} слишком большое: "
                                         f"первая={point1.get('name', 'Unknown')} (H={point1['z']:.2f}м), "
                                         f"вторая={point2.get('name', 'Unknown')} (H={point2['z']:.2f}м), "
                                         f"расстояние={distance:.4f}м (tolerance={belt_tolerance:.4f}м)")
                            # Не объединяем, если расстояние слишком большое
                            continue
                        
                        # Объединяем точку
                        matched_count += 1
                        used_indices_data1.add(idx1_data1)
                        
                        # НЕ изменяем координаты точек первой съемки!
                        # Они уже на месте. Точка из второй съемки уже преобразована
                        # и должна совпасть с точкой первой съемки.
                        # Если они близки, считаем их одной и той же точкой.
                        # Координаты остаются от первой съемки (эталонные).
                        # ВАЖНО: Используем исходный индекс из data1 для доступа к точке
                        matched_point = data1.loc[idx1_data1]
                        # Проверяем расстояние - если очень близко, координаты первой съемки не трогаем
                        if distance > 0.001:  # Если расстояние больше 1мм, возможно нужно усреднить
                            # Но для пояса обычно они должны совпадать идеально после правильного преобразования
                            logger.debug(f"Точки близки, но не идеально: расстояние={distance:.6f}м")
                        
                        logger.info(f"Объединены точки пояса {target_belt}: "
                                   f"первая={matched_point.get('name', 'Unknown')} (H={matched_point['z']:.2f}м), "
                                   f"вторая={point2.get('name', 'Unknown')} (H={point2['z']:.2f}м), "
                                   f"расстояние={distance:.4f}м")
                    
                    # Отслеживаем, какие точки из второй съемки были объединены
                    matched_indices_2_data2 = set()
                    for distance, idx2_data2, idx1_data1, point2, point1 in all_pairs:
                        if idx1_data1 in used_indices_data1:
                            matched_indices_2_data2.add(idx2_data2)
                    
                    # Добавляем оставшиеся точки как новые
                    for idx2_data2, point2 in belt2_points.iterrows():
                        # Проверяем, была ли эта точка объединена
                        if idx2_data2 not in matched_indices_2_data2:
                            added_count += 1
                            new_row = {
                                'name': point2.get('name', f'Точка {len(merged) + 1}'),
                                'x': point2['x'],
                                'y': point2['y'],
                                'z': point2['z'],
                                'belt': target_belt
                            }
                            
                            if 'is_station' in point2:
                                new_row['is_station'] = point2['is_station']
                            
                            merged = pd.concat([merged, pd.DataFrame([new_row])], ignore_index=True)
                            logger.warning(f"Добавлена точка пояса {target_belt} как новая (не найдено соответствия): "
                                         f"имя={point2.get('name', 'Unknown')}, H={point2['z']:.2f}м")
            
            # Обрабатываем остальные точки (не из целевого пояса)
            # Эти точки уже трансформированы вместе со всеми точками второй съемки
            # Они должны остаться на своих местах в трансформированной системе координат
            other_points = data2.copy()
            if target_belt is not None and 'belt' in data2.columns:
                other_points = data2[data2['belt'] != target_belt].copy()
                logger.info(f"Обработка остальных точек (не из пояса {target_belt}): {len(other_points)} точек")
                logger.info(f"Эти точки уже трансформированы вместе со всеми точками второй съемки")
            
            # Обычное объединение для остальных точек
            # Координаты этих точек уже трансформированы, они остаются на своих местах
            # в трансформированной системе координат
            
            # ВАЖНО: Создаем соответствие между индексами в other_points и строками в new_table
            # Это необходимо для корректного доступа к виджетам таблицы соответствий
            other_points_indices = list(other_points.index)
            table_row_mapping = {}  # Сопоставление индекса в other_points с номером строки в new_table
            
            # Множество для отслеживания уже объединенных точек из второй съемки (не из target_belt)
            matched_other_points_indices = set()
            
            # Находим соответствие между индексами в other_points и строками в new_table
            for table_row in range(self.new_table.rowCount()):
                combo = self.new_table.cellWidget(table_row, 4)
                if combo:
                    # Получаем индекс точки в second_station_data
                    selected_idx = combo.currentData()
                    if selected_idx is not None and selected_idx != -1:
                        # Проверяем, есть ли этот индекс в other_points
                        if selected_idx in other_points_indices:
                            table_row_mapping[selected_idx] = table_row
            
            for i, (idx, point2) in enumerate(other_points.iterrows()):
                # Пропускаем точки, которые уже были объединены
                if idx in matched_other_points_indices:
                    continue
                point2_belt = point2.get('belt') if 'belt' in point2 else None
                
                # Получаем выбранное соответствие из таблицы, если оно есть
                closest_idx = None
                # Ищем строку в таблице, соответствующую текущей точке
                if idx in table_row_mapping:
                    table_row = table_row_mapping[idx]
                    combo = self.new_table.cellWidget(table_row, 4)
                    if combo:
                        selected_idx = combo.currentData()
                        if selected_idx is not None and selected_idx != -1:
                            closest_idx = selected_idx
                
                # Если соответствие выбрано вручную, используем его
                if closest_idx is not None:
                    matched_count += 1
                    matched_other_points_indices.add(idx)  # Отмечаем точку как объединенную
                    # НЕ изменяем координаты точек первой съемки!
                    # Точка из второй съемки уже преобразована и должна совпасть с точкой первой
                    matched_point = data1.loc[closest_idx]
                    distance = np.sqrt(
                        (point2['x'] - matched_point['x'])**2 +
                        (point2['y'] - matched_point['y'])**2 +
                        (point2['z'] - matched_point['z'])**2
                    )
                    logger.debug(f"Объединены точки (ручное сопоставление): "
                               f"первая={matched_point.get('name', 'Unknown')} (H={matched_point['z']:.2f}м), "
                               f"расстояние={distance:.4f}м")
                else:
                    # Автоматический поиск ближайшей точки
                    # Сначала ищем среди точек того же пояса, если есть информация о поясах
                    search_in = data1
                    if point2_belt is not None and 'belt' in data1.columns:
                        same_belt = data1[data1['belt'] == point2_belt]
                        if not same_belt.empty:
                            search_in = same_belt
                    
                    min_distance = float('inf')
                    auto_closest_idx = None
                    
                    for idx1, point1 in search_in.iterrows():
                        # Пропускаем точки, уже использованные для целевого пояса
                        if target_belt is not None and idx1 in used_indices_data1:
                            continue
                        
                        # Вычисляем расстояние
                        dx = point2['x'] - point1['x']
                        dy = point2['y'] - point1['y']
                        dz = point2['z'] - point1['z']
                        distance = np.sqrt(dx**2 + dy**2 + dz**2)
                        
                        if distance < min_distance:
                            min_distance = distance
                            auto_closest_idx = idx1
                    
                    # Если точка близка к существующей, объединяем (усредняем)
                    if min_distance <= tolerance:
                        matched_count += 1
                        matched_other_points_indices.add(idx)  # Отмечаем точку как объединенную
                        # НЕ изменяем координаты точек первой съемки!
                        # Точка из второй съемки уже преобразована и должна совпасть с точкой первой
                        matched_point = data1.loc[auto_closest_idx]
                        logger.debug(f"Объединены точки: "
                               f"первая={matched_point.get('name', 'Unknown')} (H={matched_point['z']:.2f}м), "
                               f"расстояние={min_distance:.4f}м")
                    else:
                        # Добавляем новую точку с трансформированными координатами
                        # Точка уже трансформирована вместе со всеми точками второй съемки
                        added_count += 1
                        new_row = {
                            'name': point2.get('name', f'Точка {len(merged) + 1}'),
                            'x': point2['x'],  # Трансформированные координаты
                            'y': point2['y'],  # Трансформированные координаты
                            'z': point2['z'],  # Трансформированные координаты
                            'belt': point2.get('belt', None)
                        }
                        
                        if 'is_station' in point2:
                            new_row['is_station'] = point2['is_station']
                        
                        merged = pd.concat([merged, pd.DataFrame([new_row])], ignore_index=True)
                        logger.debug(f"Добавлена новая точка (трансформированная, из пояса {point2.get('belt', 'Unknown')}): "
                                   f"H={point2['z']:.2f}м")
            
            logger.info(f"Объединение завершено: объединено {matched_count}, добавлено {added_count}")
            logger.info(f"Объединено точек из целевого пояса {target_belt}: {len(used_indices_data1) if target_belt is not None else 0}")
            logger.info(f"Объединено точек из остальных поясов: {len(matched_other_points_indices)}")
            
            # Детальное логирование по поясам до дополнения
            if 'belt' in merged.columns:
                belts_info = merged['belt'].value_counts().sort_index()
                logger.info(f"Пояса в объединенном результате (до дополнения):")
                for belt_num, count in belts_info.items():
                    logger.info(f"  Пояс {belt_num}: {count} точек")
            else:
                logger.warning("Колонка 'belt' отсутствует в объединенных данных")
            
            # Дополняем недостающие точки по геометрии башни для каждого пояса
            if tower_faces is not None and 'belt' in merged.columns:
                from core.belt_completion import complete_belt_to_square
                logger.info("Дополнение недостающих точек по геометрии башни для всех поясов")
                
                for belt_num in merged['belt'].dropna().unique():
                    belt_points = merged[merged['belt'] == belt_num].copy()
                    if len(belt_points) < tower_faces:
                        logger.info(f"Пояс {belt_num}: найдено {len(belt_points)} точек, требуется {tower_faces}. Дополняем недостающие.")
                        
                        # Дополняем пояс до полной секции
                        completed_belt = complete_belt_to_square(
                            belt_points,
                            tower_faces=tower_faces,
                            target_height=belt_points['z'].mean() if not belt_points.empty else None
                        )
                        
                        if completed_belt is not None and not completed_belt.empty and len(completed_belt) > len(belt_points):
                            # Заменяем точки пояса в merged
                            merged = merged[merged['belt'] != belt_num]  # Удаляем старые
                            merged = pd.concat([merged, completed_belt], ignore_index=True)
                            logger.info(f"Дополнен пояс {belt_num}: было {len(belt_points)} точек, стало {len(completed_belt)} точек")
                        else:
                            logger.warning(f"Не удалось дополнить пояс {belt_num}: completed_belt пуст или недостаточно точек")
                    else:
                        logger.debug(f"Пояс {belt_num}: уже достаточно точек ({len(belt_points)})")
            
            return merged
            
        except Exception as e:
            logger.error(f"Ошибка объединения точек: {e}", exc_info=True)
            return None
    
    def _merge_points(self, data1: pd.DataFrame, data2: pd.DataFrame, tolerance: float = 0.1) -> Optional[pd.DataFrame]:
        """
        Объединение точек из двух наборов данных
        
        Args:
            data1: Первый набор данных
            data2: Второй набор данных
            tolerance: Допустимое расстояние для объединения точек (метры)
        
        Returns:
            Объединенный DataFrame
        """
        try:
            # Создаем копию первого набора данных
            merged = data1.copy()
            
            # Счетчики
            matched_count = 0
            added_count = 0
            
            # Проверяем каждую точку из второго набора
            for i, (idx, point2) in enumerate(data2.iterrows()):
                # Получаем выбранное соответствие из таблицы, если оно есть
                closest_idx = None
                combo = self.new_table.cellWidget(i, 4)
                if combo:
                    selected_idx = combo.currentData()
                    if selected_idx is not None and selected_idx != -1:
                        closest_idx = selected_idx
                
                # Если соответствие выбрано вручную, используем его
                if closest_idx is not None:
                    matched_count += 1
                    # НЕ изменяем координаты точек первой съемки!
                    # Точка из второй съемки уже преобразована и должна совпасть с точкой первой
                    matched_point = data1.loc[closest_idx]
                    distance = np.sqrt(
                        (point2['x'] - matched_point['x'])**2 +
                        (point2['y'] - matched_point['y'])**2 +
                        (point2['z'] - matched_point['z'])**2
                    )
                    logger.debug(f"Объединены точки (ручное сопоставление): "
                               f"первая={matched_point.get('name', 'Unknown')} (H={matched_point['z']:.2f}м), "
                               f"расстояние={distance:.4f}м")
                else:
                    # Автоматический поиск ближайшей точки
                    min_distance = float('inf')
                    auto_closest_idx = None
                    
                    for idx1, point1 in data1.iterrows():
                        # Вычисляем расстояние
                        dx = point2['x'] - point1['x']
                        dy = point2['y'] - point1['y']
                        dz = point2['z'] - point1['z']
                        distance = np.sqrt(dx**2 + dy**2 + dz**2)
                        
                        if distance < min_distance:
                            min_distance = distance
                            auto_closest_idx = idx1
                    
                    # Если точка близка к существующей, объединяем (усредняем)
                    if min_distance <= tolerance:
                        matched_count += 1
                        # НЕ изменяем координаты точек первой съемки!
                        # Точка из второй съемки уже преобразована и должна совпасть с точкой первой
                        matched_point = data1.loc[auto_closest_idx]
                        logger.debug(f"Объединены точки: "
                               f"первая={matched_point.get('name', 'Unknown')} (H={matched_point['z']:.2f}м), "
                               f"расстояние={min_distance:.4f}м")
                    else:
                        # Добавляем новую точку
                        added_count += 1
                        new_row = {
                            'name': point2.get('name', f'Точка {len(merged) + 1}'),
                            'x': point2['x'],
                            'y': point2['y'],
                            'z': point2['z'],
                            'belt': point2.get('belt', None)
                        }
                        
                        merged = pd.concat([merged, pd.DataFrame([new_row])], ignore_index=True)
                        
                        logger.debug(f"Добавлена новая точка: H={point2['z']:.2f}м")
            
            logger.info(f"Объединение завершено: объединено {matched_count}, добавлено {added_count}")
            
            return merged
            
        except Exception as e:
            logger.error(f"Ошибка объединения точек: {e}", exc_info=True)
            return None
    
    def get_result_data(self) -> Optional[pd.DataFrame]:
        """Получить результат импорта"""
        return self.result_data
    
    def get_transformation_audit(self) -> Optional[Dict[str, Any]]:
        """РџРѕР»СѓС‡РёС‚СЊ Р°СѓРґРёС‚ РёРјРїРѕСЂС‚Р° РІС‚РѕСЂРѕР№ СЃС‚Р°РЅС†РёРё."""
        return self.transformation_audit

    def get_second_station_import_context(self) -> Dict[str, Any]:
        """РџРѕР»СѓС‡РёС‚СЊ РєРѕРЅС‚РµРєСЃС‚ РёРјРїРѕСЂС‚Р° РІС‚РѕСЂРѕР№ СЃС‚Р°РЅС†РёРё."""
        return dict(self.second_station_import_context or {})

    def get_second_station_import_diagnostics(self) -> Dict[str, Any]:
        """РџРѕР»СѓС‡РёС‚СЊ РґРёР°РіРЅРѕСЃС‚РёРєСѓ РёРјРїРѕСЂС‚Р° РІС‚РѕСЂРѕР№ СЃС‚Р°РЅС†РёРё."""
        return dict(self.second_station_import_diagnostics or {})

    def get_visualization_data(self) -> Optional[Dict]:
        """Получить данные для визуализации линий соединения"""
        # Сначала проверяем новые данные о линиях соединения (после объединения поясов)
        if hasattr(self, 'belt_connection_visualization_data'):
            return self.belt_connection_visualization_data

        if self.method2_preview and 'visualization_data' in self.method2_preview:
            return self.method2_preview['visualization_data']
        
        # Если новых данных нет, возвращаем старые данные (после трансформации)
        if self.transform_quality and 'visualization_data' in self.transform_quality:
            return self.transform_quality['visualization_data']
        return None
    
    def _build_belt_connection_lines_after_merge(
        self,
        original_visualization_data: Dict,
        belt1_points: pd.DataFrame,
        belt2_points: pd.DataFrame,
        matched_point_pair: Tuple[int, int]
    ) -> Dict:
        """
        Строит данные для визуализации линий соединения после объединения поясов
        
        Args:
            original_visualization_data: Исходные данные визуализации из compute_rotation_from_belt_connections
            belt1_points: Точки пояса из первой съемки (после объединения)
            belt2_points: Точки пояса из второй съемки (после объединения)
            matched_point_pair: Пара индексов совпадающей точки
            
        Returns:
            Словарь с данными для визуализации линий
        """
        idx1, idx2 = matched_point_pair
        
        # Получаем совпадающие точки из объединенных данных
        point1 = belt1_points.iloc[idx1]
        point2 = belt2_points.iloc[idx2]
        
        p1 = np.array([point1['x'], point1['y'], point1['z']])
        p2 = np.array([point2['x'], point2['y'], point2['z']])
        
        logger.info(f"Построение линий соединения после объединения поясов:")
        logger.info(f"  Точка из первой съемки: ({p1[0]:.3f}, {p1[1]:.3f}, {p1[2]:.3f})")
        logger.info(f"  Точка из второй съемки: ({p2[0]:.3f}, {p2[1]:.3f}, {p2[2]:.3f})")
        
        # Находим точку на том же уровне, что и p1, в belt1
        min_height_diff = float('inf')
        closest_same_level_idx = None
        closest_same_level_point = None
        
        for i, (_, point) in enumerate(belt1_points.iterrows()):
            if i == idx1:  # Пропускаем саму точку p1
                continue
            
            point_belt1 = np.array([point['x'], point['y'], point['z']])
            height_diff = abs(point_belt1[2] - p1[2])
            
            if height_diff < min_height_diff:
                min_height_diff = height_diff
                closest_same_level_idx = i
                closest_same_level_point = point_belt1
        
        if closest_same_level_point is None:
            logger.warning("Не найдено точки на том же уровне в belt1")
            return original_visualization_data
        
        logger.info(f"  Точка на том же уровне (belt1): ({closest_same_level_point[0]:.3f}, {closest_same_level_point[1]:.3f}, {closest_same_level_point[2]:.3f})")
        
        # Находим точку на том же уровне, что и p2, в belt2
        min_height_diff = float('inf')
        closest_same_level_idx2 = None
        closest_same_level_point2 = None
        
        for i, (_, point) in enumerate(belt2_points.iterrows()):
            if i == idx2:  # Пропускаем саму точку p2
                continue
            
            point_belt2 = np.array([point['x'], point['y'], point['z']])
            height_diff = abs(point_belt2[2] - p2[2])
            
            if height_diff < min_height_diff:
                min_height_diff = height_diff
                closest_same_level_idx2 = i
                closest_same_level_point2 = point_belt2
        
        if closest_same_level_point2 is None:
            logger.warning("Не найдено точки на том же уровне в belt2")
            return original_visualization_data
        
        logger.info(f"  Точка на том же уровне (belt2): ({closest_same_level_point2[0]:.3f}, {closest_same_level_point2[1]:.3f}, {closest_same_level_point2[2]:.3f})")
        
        # Создаем данные для визуализации
        visualization_data = {
            'line1': {
                'start': p1,
                'end': closest_same_level_point,
                'label': 'Линия 1: p1 -> тот же уровень в belt1'
            },
            'line2': {
                'start': p2,
                'end': closest_same_level_point2,
                'label': 'Линия 2: p2 -> тот же уровень в belt2'
            },
            'matched_points': {
                'p1': p1,
                'p2': p2
            },
            'angle_deg': original_visualization_data.get('angle_deg', 0)
        }
        
        return visualization_data
