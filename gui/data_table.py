"""
Редактируемая таблица данных с тремя таблицами: точки стояния, точки башни, секции
"""

import json

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTableWidget,
                             QTableWidgetItem, QPushButton, QHeaderView, QMessageBox,
                             QTabWidget, QLabel, QGroupBox, QAbstractItemView, QCheckBox,
                             QComboBox, QDialog, QFormLayout, QDoubleSpinBox, QDialogButtonBox,
                             QFrame)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
import pandas as pd
import numpy as np
import math
import logging

from typing import Any, Dict, List, Optional, Tuple, Iterable

from gui.ui_helpers import apply_compact_button_style
from core.calculations import (
    approximate_tower_axis,
    calculate_local_coordinate_system,
    calculate_vertical_deviation_with_local_cs,
)
from core.normatives import NormativeChecker, get_vertical_tolerance
from core.point_utils import (
    build_flag_mask,
    build_is_station_mask,
    build_working_tower_mask,
    normalize_tower_point_flags,
)
from core.services.verticality_sections import build_verticality_check_from_sections
from core.services.angular_verticality import AngularVerticalityBuilder

logger = logging.getLogger(__name__)

class AddStationDialog(QDialog):
    """Диалог добавления новой точки стояния инструмента."""

    def __init__(self, parent=None, *, existing_distance: float = 10.0):
        super().__init__(parent)
        self.setWindowTitle('Добавить точку стояния')
        self.setModal(True)
        self._build_ui(existing_distance)

    def _build_ui(self, existing_distance: float):
        layout = QFormLayout(self)

        # Позиция относительно исходной станции: слева (по оси Y) или справа.
        self.position_combo = QComboBox(self)
        self.position_combo.addItem('Слева от текущей станции', 'left')
        self.position_combo.addItem('Справа от текущей станции', 'right')
        layout.addRow('Расположение:', self.position_combo)

        # Угол в градусах; по умолчанию 90°.
        self.angle_spin = QDoubleSpinBox(self)
        self.angle_spin.setRange(-360.0, 360.0)
        self.angle_spin.setDecimals(3)
        self.angle_spin.setSingleStep(1.0)
        self.angle_spin.setValue(90.0)
        layout.addRow('Угол (°):', self.angle_spin)

        # Расстояние от мачты; по умолчанию расстояние текущей станции.
        self.distance_spin = QDoubleSpinBox(self)
        self.distance_spin.setRange(0.1, 10_000.0)
        self.distance_spin.setDecimals(3)
        self.distance_spin.setSingleStep(0.1)
        self.distance_spin.setValue(max(existing_distance, 0.1))
        layout.addRow('Расстояние, м:', self.distance_spin)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, parent=self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def get_values(self) -> dict:
        return {
            'position': self.position_combo.currentData(),
            'angle_deg': float(self.angle_spin.value()),
            'distance': float(self.distance_spin.value()),
        }

class DataTableWidget(QWidget):
    """Виджет для отображения и редактирования данных точек в трех таблицах"""
    
    data_changed = pyqtSignal()
    data_mutated = pyqtSignal(object, object, str)
    row_selected = pyqtSignal(int)  # Глобальный индекс выбранной строки
    active_station_changed = pyqtSignal(object)
    
    def __init__(self, editor_3d=None):
        super().__init__()
        self.original_data = None  # Храним оригинальные данные с is_station
        self.editor_3d = editor_3d  # Ссылка на 3D редактор для получения section_data
        self.show_angular_mode = False
        self.primary_station_id: Optional[int] = None
        self.secondary_station_id: Optional[int] = None
        self.active_station_id: Optional[int] = None
        self._current_station_data = pd.DataFrame()
        self._current_tower_data = pd.DataFrame()
        self.processed_results: Optional[Dict[str, Any]] = None
        self._angular_verticality_payload: Optional[Dict[str, Any]] = None
        self._secondary_station_prompted = False
        self.init_ui()

    @staticmethod
    def _clone_dataframe(data: Optional[pd.DataFrame]) -> pd.DataFrame:
        return data.copy(deep=True) if isinstance(data, pd.DataFrame) else pd.DataFrame()

    @classmethod
    def _dataframes_equal(cls, left: Optional[pd.DataFrame], right: Optional[pd.DataFrame]) -> bool:
        if isinstance(left, pd.DataFrame) and isinstance(right, pd.DataFrame):
            return left.equals(right)
        if left is None and right is None:
            return True
        return cls._clone_dataframe(left).equals(cls._clone_dataframe(right))

    def _capture_original_data_snapshot(self) -> pd.DataFrame:
        return self._clone_dataframe(self.original_data)

    def _emit_data_mutation(self, old_data: Optional[pd.DataFrame], description: str) -> None:
        new_data = self._clone_dataframe(self.original_data)
        old_snapshot = self._clone_dataframe(old_data)
        if self._dataframes_equal(old_snapshot, new_data):
            return
        self.data_mutated.emit(old_snapshot, new_data, description)

    def _invalidate_angular_verticality_cache(self):
        """Сбрасывает кэш payload журнала и вертикальности."""
        self._angular_verticality_payload = None

    @staticmethod
    def _safe_int(value: Any, default: Optional[int] = None) -> Optional[int]:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _make_section_key(section_num: Optional[int], height: Optional[float]) -> str:
        try:
            if section_num is not None and not pd.isna(section_num):
                return f"section:{int(section_num)}"
        except (TypeError, ValueError):
            pass
        if height is None:
            return "section:unknown"
        return f"height:{float(height):.6f}"

    def _empty_verticality_check(self) -> Dict[str, Any]:
        return NormativeChecker().check_vertical_deviations([], [])

    @staticmethod
    def _stations_form_valid_angular_basis(
        primary_coords: Optional[Tuple[float, float, float]],
        secondary_coords: Optional[Tuple[float, float, float]],
        *,
        min_xy_distance_m: float = 0.1,
    ) -> bool:
        if primary_coords is None or secondary_coords is None:
            return False
        try:
            delta_xy = np.array(
                [
                    float(secondary_coords[0]) - float(primary_coords[0]),
                    float(secondary_coords[1]) - float(primary_coords[1]),
                ],
                dtype=float,
            )
        except (TypeError, ValueError):
            return False
        return float(np.linalg.norm(delta_xy)) >= float(min_xy_distance_m)

    def _build_angular_basis_metadata(self) -> Dict[str, Any]:
        primary_station = self._serialize_station_entry(self.primary_station_id)
        secondary_station = self._serialize_station_entry(self.secondary_station_id)
        primary_coords = self.get_station_coordinates(self.primary_station_id)
        secondary_coords = self.get_station_coordinates(self.secondary_station_id)
        secondary_is_synthetic = bool(secondary_station and secondary_station.get('station_origin') == 'synthetic')
        has_required_stations = (
            primary_station is not None
            and secondary_station is not None
            and self._stations_form_valid_angular_basis(primary_coords, secondary_coords)
        )
        has_authoritative_stations = has_required_stations and not secondary_is_synthetic
        if has_authoritative_stations:
            mode = 'stations'
        elif has_required_stations:
            mode = 'stations_synthetic_secondary'
        elif primary_station is not None:
            mode = 'stations_incomplete'
        else:
            mode = 'processed_fallback'
        return {
            'mode': mode,
            'primary_station': primary_station,
            'secondary_station': secondary_station,
            'requires_two_stations': True,
            'has_required_stations': has_required_stations,
            'has_authoritative_stations': has_authoritative_stations,
            'secondary_station_is_synthetic': secondary_is_synthetic,
        }

    def has_complete_angular_station_basis(self) -> bool:
        try:
            self._update_station_ids()
        except Exception:
            logger.exception("Не удалось обновить точки стояния перед проверкой angular-базы")
            return False
        primary_coords = self._get_station_for_axis('x')
        secondary_coords = self._get_station_for_axis('y')
        return self._stations_form_valid_angular_basis(primary_coords, secondary_coords)

    def ensure_complete_angular_station_basis(self, interactive: bool = True) -> bool:
        if self.has_complete_angular_station_basis():
            self._secondary_station_prompted = False
            return True

        if self._get_station_for_axis('x') is None:
            return False
        if not interactive or self._secondary_station_prompted:
            return False

        self._secondary_station_prompted = True
        QMessageBox.information(
            self,
            'Требуется вторая точка стояния',
            'Для расчета вертикальности по угловым измерениям добавьте вторую точку стояния прибора.',
        )
        if not self.show_add_station_dialog():
            return False

        self._secondary_station_prompted = False
        try:
            self._update_station_ids()
            self._rebuild_cached_tower_data()
        except Exception:
            logger.exception("Не удалось обновить данные после добавления второй точки стояния")
            return False
        return self.has_complete_angular_station_basis()

    def _ensure_section_numbers(self, sections: List[Dict[str, Any]]):
        """Присваивает секциям сквозную нумерацию с учетом близких высот."""
        if not sections:
            return

        height_tolerance = 0.01
        section_num = 0
        seen_heights: List[float] = []

        for section in sections:
            section_height = float(section.get('height', 0.0) or 0.0)
            existing_section_num = self._safe_int(section.get('section_num'))
            if existing_section_num is not None:
                seen_heights.append(section_height)
                section['section_num'] = existing_section_num
                section_num = max(section_num, existing_section_num + 1)
                continue

            matched_height = None
            for seen_height in seen_heights:
                if abs(section_height - seen_height) <= height_tolerance:
                    matched_height = seen_height
                    break

            if matched_height is None:
                section['section_num'] = section_num
                seen_heights.append(section_height)
                section_num += 1
            else:
                section['section_num'] = max(section_num - 1, 0)
    
    def _decode_part_memberships(self, value) -> List[int]:
        if value is None:
            return []
        if isinstance(value, float) and math.isnan(value):
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
        memberships: List[int] = []
        for item in decoded:
            try:
                memberships.append(int(item))
            except (TypeError, ValueError):
                continue
        return memberships
    
    @staticmethod
    def _build_is_station_mask(series: pd.Series) -> pd.Series:
        return build_is_station_mask(series)

    @staticmethod
    def _build_working_tower_mask(data: pd.DataFrame) -> pd.Series:
        return build_working_tower_mask(data)
    
    def _row_has_part(self, row: pd.Series, part_num: int) -> bool:
        memberships = []
        if 'tower_part_memberships' in row and pd.notna(row.get('tower_part_memberships')):
            memberships = self._decode_part_memberships(row.get('tower_part_memberships'))
        if memberships:
            return part_num in memberships
        raw_value = row.get('tower_part', 1)
        if raw_value is None or (isinstance(raw_value, float) and math.isnan(raw_value)):
            raw_value = 1
        try:
            base_part = int(raw_value)
        except (TypeError, ValueError):
            return False
        if base_part <= 0:
            base_part = 1
        if bool(row.get('is_part_boundary', False)):
            return part_num in (base_part, base_part + 1)
        return base_part == part_num
    
    def _collect_unique_parts(self, data: pd.DataFrame) -> List[int]:
        parts = set()
        if 'tower_part_memberships' in data.columns:
            for value in data['tower_part_memberships'].dropna():
                parts.update(self._decode_part_memberships(value))
        if not parts and 'tower_part' in data.columns:
            parts.update(int(p) for p in data['tower_part'].dropna().unique())
        if 'is_part_boundary' in data.columns and data['is_part_boundary'].any():
            boundary_rows = data[data['is_part_boundary']]
            for _, row in boundary_rows.iterrows():
                try:
                    base_part = int(row.get('tower_part', 1))
                except (TypeError, ValueError):
                    base_part = 1
                if base_part <= 0:
                    base_part = 1
                parts.update({base_part, base_part + 1})
        return sorted(parts)
        
    def init_ui(self):
        """Инициализация интерфейса"""
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        # Создаем TabWidget для трех таблиц
        self.tabs = QTabWidget()
        
        # ===== ВКЛАДКА 1: Точки стояния =====
        station_tab = QWidget()
        station_layout = QVBoxLayout()
        station_tab.setLayout(station_layout)
        
        station_label = QLabel('📍 Точки стояния')
        station_label.setStyleSheet('font-weight: bold; font-size: 12pt; padding: 5px;')
        station_layout.addWidget(station_label)

        # Панель кнопок над таблицей
        station_buttons_panel = QHBoxLayout()
        station_buttons_panel.setSpacing(8)
        
        self.add_station_btn = QPushButton('➕ Добавить точку стояния')
        self.add_station_btn.setToolTip('Создает новую точку стояния относительно выбранной станции.')
        self.add_station_btn.clicked.connect(self.show_add_station_dialog)
        apply_compact_button_style(self.add_station_btn, width=200, min_height=36)
        station_buttons_panel.addWidget(self.add_station_btn)
        
        self.set_active_station_btn = QPushButton('✓ Сделать активной')
        self.set_active_station_btn.setToolTip('Установить выбранную точку стояния как активную для расчетов')
        apply_compact_button_style(self.set_active_station_btn, width=160, min_height=36)
        self.set_active_station_btn.setEnabled(False)
        self.set_active_station_btn.clicked.connect(self.on_set_active_station_clicked)
        station_buttons_panel.addWidget(self.set_active_station_btn)
        
        station_buttons_panel.addStretch()
        station_layout.addLayout(station_buttons_panel)
        
        self.station_table = QTableWidget()
        self.station_table.setColumnCount(6)
        self.station_table.setHorizontalHeaderLabels(['№', 'Название', 'X (м)', 'Y (м)', 'Z (м)', 'Активная'])
        self.station_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.station_table.setAlternatingRowColors(True)
        self.station_table.itemChanged.connect(self.on_station_item_changed)
        try:
            self.station_table.itemSelectionChanged.disconnect()
        except (RuntimeError, TypeError):
            pass
        self.station_table.itemSelectionChanged.connect(self.on_station_selection_changed)
        self.setup_table_style(self.station_table)
        station_layout.addWidget(self.station_table)
        
        self.tabs.addTab(station_tab, '📍 Точки стояния')
        
        # ===== ВКЛАДКА 2: Точки башни =====
        tower_tab = QWidget()
        tower_layout = QVBoxLayout()
        tower_tab.setLayout(tower_layout)
        
        tower_label = QLabel('🗼 Точки башни')
        tower_label.setStyleSheet('font-weight: bold; font-size: 12pt; padding: 5px;')
        tower_layout.addWidget(tower_label)

        mode_layout = QHBoxLayout()
        self.tower_mode_checkbox = QCheckBox('Показать угловые измерения')
        self.tower_mode_checkbox.setToolTip(
            'Переключение между отображением линейных координат и расчетом теодолитных углов.'
        )
        self.tower_mode_checkbox.toggled.connect(self.on_tower_mode_toggled)
        mode_layout.addWidget(self.tower_mode_checkbox)
        mode_layout.addStretch()
        tower_layout.addLayout(mode_layout)
        
        # Панель кнопок над таблицей башни — сгруппированные по назначению
        tower_buttons_panel = QHBoxLayout()
        tower_buttons_panel.setSpacing(0)

        # Группа «Точки»: создание и удаление точек
        points_frame = QFrame()
        points_frame.setObjectName('towerPointsGroupFrame')
        pf_layout = QVBoxLayout(points_frame)
        pf_layout.setContentsMargins(4, 4, 4, 2)
        pf_layout.setSpacing(2)

        btns_row = QHBoxLayout()
        btns_row.setSpacing(8)

        self.tower_add_btn = QPushButton('➕ Добавить точку')
        self.tower_add_btn.setToolTip('Добавить новую точку в таблицу башни')
        self.tower_add_btn.clicked.connect(lambda: self.add_row(self.tower_table))
        apply_compact_button_style(self.tower_add_btn, width=150, min_height=36)
        btns_row.addWidget(self.tower_add_btn)

        self.tower_delete_btn = QPushButton('❌ Удалить выбранные')
        self.tower_delete_btn.setToolTip('Удалить выбранные строки из таблицы башни')
        self.tower_delete_btn.clicked.connect(lambda: self.delete_selected_rows(self.tower_table))
        apply_compact_button_style(self.tower_delete_btn, width=160, min_height=36)
        btns_row.addWidget(self.tower_delete_btn)

        pf_layout.addLayout(btns_row)

        points_label = QLabel('Точки')
        points_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        points_label.setStyleSheet('font-size: 8px; color: #808080; margin: 0; padding: 0;')
        pf_layout.addWidget(points_label)

        self._tower_points_frame = points_frame  # доступен для обновления темы

        tower_buttons_panel.addWidget(points_frame)
        tower_buttons_panel.addStretch()
        tower_layout.addLayout(tower_buttons_panel)
        
        # Для составных башен создаем вкладки для каждой части
        self.tower_parts_tabs = QTabWidget()
        self.tower_table = QTableWidget()  # Основная таблица для обычных башен
        self.tower_part_tables = {}  # Словарь таблиц для частей составной башни
        
        self.tower_table.setColumnCount(7)
        self.tower_table.setHorizontalHeaderLabels(['№', 'Название', 'X (м)', 'Y (м)', 'Z (м)', 'Пояс', 'Сгенер.'])
        self.tower_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tower_table.setAlternatingRowColors(True)
        self.tower_table.itemChanged.connect(self.on_tower_item_changed)
        try:
            self.tower_table.itemSelectionChanged.disconnect()
        except (RuntimeError, TypeError):
            pass
        self.tower_table.itemSelectionChanged.connect(self.on_tower_selection_changed)
        self.setup_table_style(self.tower_table)
        
        # По умолчанию показываем основную таблицу
        tower_layout.addWidget(self.tower_table)
        tower_layout.addWidget(self.tower_parts_tabs)
        self.tower_parts_tabs.hide()  # Скрываем вкладки частей по умолчанию

        # Таблицы угловых измерений по осям X и Y (по умолчанию скрыты)
        self.angular_tabs = QTabWidget()
        self.angular_table_x = QTableWidget()
        self.angular_table_y = QTableWidget()
        for tbl in (self.angular_table_x, self.angular_table_y):
            tbl.setAlternatingRowColors(True)
            tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            self.setup_table_style(tbl)
        self.angular_tabs.addTab(self.angular_table_x, 'Ось X')
        self.angular_tabs.addTab(self.angular_table_y, 'Ось Y')
        self.angular_tabs.hide()
        tower_layout.addWidget(self.angular_tabs)
        
        self.tabs.addTab(tower_tab, '🗼 Точки башни')
        
        # ===== ВКЛАДКА 3: Секции =====
        sections_tab = QWidget()
        sections_layout = QVBoxLayout()
        sections_tab.setLayout(sections_layout)
        
        sections_label = QLabel('📏 Секции')
        sections_label.setStyleSheet('font-weight: bold; font-size: 12pt; padding: 5px;')
        sections_layout.addWidget(sections_label)

        sections_hint = QLabel('Таблица обновляется автоматически после расчёта. Редактирование недоступно.')
        sections_hint.setStyleSheet('color: gray; font-style: italic; padding: 2px 5px;')
        sections_layout.addWidget(sections_hint)

        self.sections_table = QTableWidget()
        self.sections_table.setColumnCount(8)
        self.sections_table.setHorizontalHeaderLabels(['№', 'Абс. высота (м)', 'Часть башни', 'Секция части', 'Центр X (м)', 'Центр Y (м)', 'Центр Z (м)', 'Пояса'])
        self.sections_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.sections_table.setAlternatingRowColors(True)
        self.sections_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)  # Только для чтения
        self.setup_table_style(self.sections_table)
        sections_layout.addWidget(self.sections_table)
        
        self.tabs.addTab(sections_tab, '📏 Секции')
        
        layout.addWidget(self.tabs)
    
    def setup_table_style(self, table):
        """Настройка стиля таблицы"""
        table.setStyleSheet("""
            QTableWidget::item:selected {
                background-color: #4A90E2;
                color: white;
                font-weight: bold;
            }
            QTableWidget::item:hover {
                background-color: #E3F2FD;
            }
        """)
        
    def set_data(self, data: pd.DataFrame):
        """
        Устанавливает данные в три таблицы
        
        Args:
            data: DataFrame с колонками x, y, z, name, и опционально belt, is_station, point_index
        """
        # Не меняем порядок исходных данных — сохраняем как есть
        # ВАЖНО: нормализуем столбец is_station до булевого, чтобы корректно
        # определять принадлежность строки таблице при синхронизации выбора
        self._invalidate_angular_verticality_cache()
        self._secondary_station_prompted = False
        if data is None or data.empty:
            self.original_data = pd.DataFrame()
            self.processed_results = None
        else:
            work_data = normalize_tower_point_flags(data)
            if 'tower_part' not in work_data.columns:
                work_data['tower_part'] = 1
            if 'tower_part_memberships' not in work_data.columns:
                work_data['tower_part_memberships'] = None
            if 'is_part_boundary' not in work_data.columns:
                work_data['is_part_boundary'] = False
            else:
                work_data['is_part_boundary'] = build_flag_mask(work_data, 'is_part_boundary')
            if 'station_role' not in work_data.columns:
                work_data['station_role'] = None
            
            # КРИТИЧЕСКИ ВАЖНО: проверяем наличие point_index в данных
            # Если point_index отсутствует, но данные пришли из editor_3d, это проблема
            if 'point_index' not in work_data.columns:
                logger.warning(
                    f"set_data: Колонка 'point_index' отсутствует в данных! "
                    f"Колонки: {list(work_data.columns)}. "
                    f"Это может привести к проблемам с выбором строк в таблице. "
                    f"Создаем point_index на основе позиции (1-based)."
                )
                # Создаем point_index на основе позиции (1-based)
                # Это гарантирует, что point_index будет доступен для поиска
                work_data['point_index'] = range(1, len(work_data) + 1)
                logger.info(
                    f"set_data: Создан point_index на основе позиции. "
                    f"Первые 5 значений: {list(work_data['point_index'].head())}"
                )
            else:
                logger.debug(
                    f"set_data: Колонка 'point_index' присутствует. "
                    f"Первые 5 значений: {list(work_data['point_index'].head())}"
                )
            
            self.original_data = work_data
        
        if data is None or data.empty:
            self.station_table.setRowCount(0)
            self.tower_table.setRowCount(0)
            self.update_sections_table()
            self._current_station_data = pd.DataFrame()
            self._current_tower_data = pd.DataFrame()
            self.active_station_id = None
            if hasattr(self.editor_3d, 'set_active_station_index'):
                try:
                    self.editor_3d.set_active_station_index(None)
                except Exception as e:
                    logger.warning(f"Не удалось сбросить активную станцию в 3D-редакторе: {e}")
            if hasattr(self, 'set_active_station_btn'):
                self.set_active_station_btn.setEnabled(False)
            return
        
        # Добавляем is_station если его нет (локально для заполнения таблиц)
        if 'is_station' not in data.columns:
            data = data.copy()
            data['is_station'] = False
        
        # Отключаем сигналы временно
        for signal in (self.station_table.itemChanged, self.tower_table.itemChanged):
            try:
                signal.disconnect()
            except (RuntimeError, TypeError):
                pass
        
        # Разделяем данные на точки стояния и точки башни
        # Используем новый синтаксис для избежания FutureWarning
        station_mask = self._build_is_station_mask(self.original_data['is_station'])
        station_data = self.original_data[station_mask].copy()
        tower_data = self.original_data[self._build_working_tower_mask(self.original_data)].copy()
        
        # ДИАГНОСТИКА: логируем информацию о станциях
        logger.info(
            f"set_data: Разделение данных: всего точек={len(self.original_data)}, "
            f"станций={len(station_data)}, точек башни={len(tower_data)}"
        )
        if len(station_data) > 0:
            logger.info(
                f"set_data: Станции найдены. Первые 3: "
                f"{[(i, row.get('name', 'N/A'), row.get('point_index', 'N/A'), row.get('is_station', False)) for i, (idx, row) in enumerate(station_data.head(3).iterrows())]}"
            )
        
        # ===== Заполняем таблицу точек стояния =====
        self.station_table.setRowCount(len(station_data))
        if len(station_data) == 0:
            logger.warning(
                f"set_data: station_table пуста! Проверьте, что в данных есть точки с is_station=True. "
                f"Всего точек в original_data: {len(self.original_data)}, "
                f"is_station колонка присутствует: {'is_station' in self.original_data.columns}, "
                f"значения is_station: {self.original_data['is_station'].value_counts().to_dict() if 'is_station' in self.original_data.columns else 'N/A'}"
            )
            self._current_station_data = pd.DataFrame()
            self.active_station_id = None
            if hasattr(self.editor_3d, 'set_active_station_index'):
                try:
                    self.editor_3d.set_active_station_index(None)
                except Exception as e:
                    logger.warning(f"Не удалось сбросить активную станцию в 3D-редакторе: {e}")
            self.set_active_station_btn.setEnabled(False)
        else:
            for i, (idx, row) in enumerate(station_data.iterrows()):
                # №
                point_index_value = row.get('point_index')
                parsed_point_index = None
                point_index_text = ''
                if pd.notna(point_index_value):
                    raw_point_index = str(point_index_value).strip()
                    if raw_point_index:
                        try:
                            parsed_point_index = int(float(raw_point_index))
                        except (ValueError, TypeError):
                            point_index_text = raw_point_index
                        else:
                            point_index_text = str(parsed_point_index)
                if not point_index_text:
                    point_index_text = str(i + 1)
                item = QTableWidgetItem(point_index_text)
                # КРИТИЧЕСКИ ВАЖНО: сохраняем point_index в UserRole для стабильной идентификации
                # Если point_index отсутствует в данных, создаем его на основе позиции + 1 (1-based)
                # Это гарантирует, что UserRole всегда содержит point_index, а не позицию
                if pd.notna(point_index_value):
                    # point_index есть в данных - используем его
                    stored_point_index = parsed_point_index
                else:
                    # point_index отсутствует - создаем его на основе позиции (1-based)
                    # КРИТИЧЕСКИ ВАЖНО: используем i+1, а не i, так как point_index начинается с 1
                    stored_point_index = i + 1
                    logger.debug(
                        f"set_data (station_table): point_index отсутствует для строки {i}, "
                        f"создаем stored_point_index={stored_point_index} на основе позиции"
                    )
                if stored_point_index is None:
                    stored_point_index = i + 1
                item.setData(Qt.ItemDataRole.UserRole, stored_point_index)
                item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                self.station_table.setItem(i, 0, item)
                
                # Название
                name = row.get('name', f'Точка {i+1}')
                item = QTableWidgetItem(str(name))
                self.station_table.setItem(i, 1, item)
                
                # X, Y, Z
                for j, col in enumerate(['x', 'y', 'z'], start=2):
                    item = QTableWidgetItem(f"{row[col]:.6f}" if j < 4 else f"{row[col]:.3f}")
                    self.station_table.setItem(i, j, item)
            
                active_item = QTableWidgetItem('✓' if self.active_station_id == idx else '')
                active_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                active_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.station_table.setItem(i, 5, active_item)
            
            self._current_station_data = station_data.copy()
        # НЕ сортируем tower_data, чтобы порядок соответствовал 3D редактору
        # Сортировка может вызывать несоответствие порядка точек между таблицей и 3D видом
        self._current_tower_data = tower_data.copy()
        self._update_station_ids()

        self.populate_tower_table()
        
        # Обновляем таблицу секций
        self.update_sections_table()
        
        # Подключаем сигналы обратно
        self.station_table.itemChanged.connect(self.on_station_item_changed)
        if not self.show_angular_mode:
            self.tower_table.itemChanged.connect(self.on_tower_item_changed)
    
    def set_processed_results(self, results: Optional[Dict[str, Any]]):
        """Сохраняет результаты расчетов для синхронизации с вертикальностью."""
        self.processed_results = results
        self._invalidate_angular_verticality_cache()
        payload = self.get_angular_verticality_payload()
        if isinstance(self.processed_results, dict):
            self.processed_results['angular_verticality'] = payload
            vertical_check = payload.get('vertical_check')
            if isinstance(vertical_check, dict) and vertical_check.get('total', 0):
                self.processed_results['vertical_check'] = vertical_check
        if self.show_angular_mode:
            self.populate_tower_table()
    
    def update_sections_table(self):
        """Обновляет таблицу секций на основе section_data из editor_3d"""
        self._invalidate_angular_verticality_cache()
        if not self.editor_3d or not hasattr(self.editor_3d, 'section_data'):
            self.sections_table.setRowCount(0)
            return
        
        section_data = self.editor_3d.section_data
        if not section_data:
            self.sections_table.setRowCount(0)
            return
        
        # Логируем информацию о секциях для отладки
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Обновление таблицы секций: {len(section_data)} секций")
        for section in section_data:
            belts = section.get('belt_nums', [])
            logger.info(f"  Секция на высоте {section['height']:.2f}м: {len(section['points'])} точек, пояса: {belts}")
        
        # Сортируем секции по высоте
        sorted_sections = sorted(section_data, key=lambda s: s.get('height', 0))
        self._ensure_section_numbers(sorted_sections)
        
        self.sections_table.setRowCount(len(sorted_sections))
        
        for i, section in enumerate(sorted_sections):
            # № - используем сквозную нумерацию с 0
            section_num_display = section.get('section_num', i)
            item = QTableWidgetItem(str(section_num_display))
            item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.sections_table.setItem(i, 0, item)
            
            # Абсолютная высота (округленная до 1 знака после запятой)
            height = round(section['height'], 1)
            item = QTableWidgetItem(f"{height:.1f}")
            item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.sections_table.setItem(i, 1, item)
            
            # Часть башни - определяем из tower_part_memberships или tower_part
            part_memberships = []
            if 'tower_part_memberships' in section and section.get('tower_part_memberships') is not None:
                import json
                memberships_val = section.get('tower_part_memberships')
                try:
                    if isinstance(memberships_val, str):
                        part_memberships = json.loads(memberships_val)
                    elif isinstance(memberships_val, (list, tuple)):
                        part_memberships = list(memberships_val)
                    else:
                        part_memberships = []
                    # Преобразуем в список целых чисел, исключая NaN
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
            
            if not part_memberships:
                segment = section.get('segment')
                if segment is not None:
                    try:
                        part_memberships = [int(segment)]
                    except (TypeError, ValueError):
                        pass
            
            # Формируем строку для отображения
            if len(part_memberships) > 1:
                # Граничная секция - несколько частей через дробь
                part_memberships_sorted = sorted(part_memberships)
                segment_name = '/'.join([str(p) for p in part_memberships_sorted])
            elif len(part_memberships) == 1:
                # Одна часть
                segment_name = f'Часть {part_memberships[0]}'
            else:
                # Неизвестно
                segment_name = section.get('segment_name', 'Неизвестно')
                if isinstance(segment_name, (int, float)):
                    segment_name = f'Часть {int(segment_name)}'
            
            item = QTableWidgetItem(str(segment_name))
            item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.sections_table.setItem(i, 2, item)
            
            # Секция этой части
            section_name = section.get('section_name', 'Неизвестно')
            item = QTableWidgetItem(str(section_name))
            item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.sections_table.setItem(i, 3, item)
            
            # Вычисляем центр секции
            points = section['points']
            center_xy = section.get('center_xy')
            center_z = section.get('center_z')
            if center_xy is not None:
                center_x = float(center_xy[0])
                center_y = float(center_xy[1])
            elif len(points) > 0:
                center_x = np.mean([p[0] for p in points])
                center_y = np.mean([p[1] for p in points])
            else:
                center_x = center_y = 0.0
            if center_z is None:
                center_z = float(np.mean([p[2] for p in points])) if len(points) > 0 else 0.0
            
            # Центр X, Y, Z
            item = QTableWidgetItem(f"{center_x:.6f}")
            item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.sections_table.setItem(i, 4, item)
            
            item = QTableWidgetItem(f"{center_y:.6f}")
            item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.sections_table.setItem(i, 5, item)
            
            item = QTableWidgetItem(f"{center_z:.3f}")
            item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.sections_table.setItem(i, 6, item)
            
            # Пояса
            belt_nums = section.get('belt_nums', [])
            belt_text = ', '.join([str(b) for b in belt_nums]) if belt_nums else '—'
            item = QTableWidgetItem(belt_text)
            item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.sections_table.setItem(i, 7, item)

    def populate_tower_table(self):
        """Обновляет таблицу точек башни в зависимости от выбранного режима."""
        if self.show_angular_mode:
            self.populate_tower_table_angles()
        else:
            self.populate_tower_table_coordinates()

    def _sort_tower_dataframe(self, tower_df: pd.DataFrame) -> pd.DataFrame:
        """Сортирует точки башни по номеру пояса и высоте."""
        if tower_df is None or tower_df.empty:
            return pd.DataFrame(columns=tower_df.columns if tower_df is not None else None)
        tmp = tower_df.copy()
        try:
            sort_col = 'face_track' if 'face_track' in tmp.columns else 'belt'
            tmp['_sort_key'] = pd.to_numeric(tmp[sort_col], errors='coerce')
            tmp = tmp.sort_values(by=['_sort_key', 'z'], ascending=[True, True], na_position='last')
            tmp = tmp.drop(columns=['_sort_key'])
        except Exception:
            tmp = tower_df.copy()
        return tmp

    def _rebuild_cached_tower_data(self):
        """Переиндексирует кэш данных башни (без сортировки для соответствия 3D редактору)."""
        if self.original_data is None or self.original_data.empty:
            self._current_tower_data = pd.DataFrame()
            return
        tower_df = self.original_data[self._build_working_tower_mask(self.original_data)].copy()
        # НЕ сортируем, чтобы порядок соответствовал 3D редактору
        self._current_tower_data = tower_df.copy()

    def _update_station_ids(self):
        """Обновляет ID основных точек стояния и отмечает их роли."""
        if self.original_data is None or self.original_data.empty:
            self.primary_station_id = None
            self.secondary_station_id = None
            return

        station_df = self.original_data[self.original_data['is_station']].copy()
        if station_df.empty:
            self.primary_station_id = None
            self.secondary_station_id = None
        else:
            if 'station_role' in station_df.columns:
                prim_rows = station_df[station_df['station_role'] == 'primary']
                if not prim_rows.empty:
                    self.primary_station_id = int(prim_rows.index[0])
                else:
                    self.primary_station_id = int(station_df.index[0])

                sec_rows = station_df[station_df['station_role'] == 'secondary']
                if not sec_rows.empty:
                    self.secondary_station_id = int(sec_rows.index[0])
                else:
                    remaining = [idx for idx in station_df.index if idx != self.primary_station_id]
                    self.secondary_station_id = int(remaining[0]) if remaining else None
            else:
                self.primary_station_id = int(station_df.index[0])
                self.secondary_station_id = int(station_df.index[1]) if len(station_df) > 1 else None

        if 'station_role' not in self.original_data.columns:
            self.original_data['station_role'] = None
        else:
            self.original_data['station_role'] = self.original_data['station_role']
        self.original_data.loc[:, 'station_role'] = None
        if self.primary_station_id is not None and self.primary_station_id in self.original_data.index:
            self.original_data.at[self.primary_station_id, 'station_role'] = 'primary'
        if (self.secondary_station_id is not None and
                self.secondary_station_id in self.original_data.index):
            self.original_data.at[self.secondary_station_id, 'station_role'] = 'secondary'

        if self.active_station_id is not None and (
            self.active_station_id not in self.original_data.index
            or not bool(self.original_data.at[self.active_station_id, 'is_station'])
        ):
            self.active_station_id = None
        if self.secondary_station_id is not None or self.primary_station_id is None:
            self._secondary_station_prompted = False

    def on_tower_mode_toggled(self, checked: bool):
        """Переключает режим отображения таблицы башни."""
        self.show_angular_mode = bool(checked)
        try:
            self.tower_table.itemChanged.disconnect()
        except (RuntimeError, TypeError):
            pass
        self.populate_tower_table()
        if not self.show_angular_mode:
            self.tower_table.itemChanged.connect(self.on_tower_item_changed)

    def show_add_station_dialog(self) -> bool:
        """Создает новую точку стояния относительно основной станции."""
        if self.original_data is None or self.original_data.empty:
            QMessageBox.warning(self, 'Нет данных', 'Сначала загрузите или создайте точки стояния.')
            return False
        previous_data = self._capture_original_data_snapshot()

        base_station_id = self.primary_station_id
        if base_station_id is None and not self._current_station_data.empty:
            base_station_id = int(self._current_station_data.index[0])
        base_coords = self.get_station_coordinates(base_station_id)
        if base_coords is None:
            QMessageBox.warning(self, 'Нет базовой станции', 'Невозможно добавить дополнительную точку стояния.')
            return False

        tower_df = self._current_tower_data if self._current_tower_data is not None else pd.DataFrame()
        if tower_df.empty:
            QMessageBox.warning(self, 'Нет точек башни', 'Невозможно определить положение новой станции без точек башни.')
            return False

        center_x = float(tower_df['x'].mean())
        center_y = float(tower_df['y'].mean())
        sx, sy, sz = base_coords
        existing_distance = math.hypot(sx - center_x, sy - center_y)

        dialog = AddStationDialog(self, existing_distance=max(existing_distance, 0.1))
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False

        values = dialog.get_values()
        position = values['position'] or 'left'
        angle_rad = math.radians(values['angle_deg'])
        distance = max(values['distance'], 0.1)

        base_vector = np.array([sx - center_x, sy - center_y], dtype=float)
        norm = np.linalg.norm(base_vector)
        if norm < 1e-6:
            base_vector = np.array([1.0, 0.0])
        else:
            base_vector /= norm

        rotation_sign = -1.0 if position == 'left' else 1.0
        rot_angle = rotation_sign * angle_rad
        cos_a = math.cos(rot_angle)
        sin_a = math.sin(rot_angle)
        rotation_matrix = np.array([[cos_a, -sin_a], [sin_a, cos_a]])
        rotated_vector = rotation_matrix.dot(base_vector)
        rotated_norm = np.linalg.norm(rotated_vector)
        if rotated_norm < 1e-6:
            rotated_vector = np.array([1.0, 0.0])
        else:
            rotated_vector /= rotated_norm

        new_xy = np.array([center_x, center_y]) + rotated_vector * distance
        new_coords = (float(new_xy[0]), float(new_xy[1]), float(sz))

        if not self._stations_form_valid_angular_basis(base_coords, new_coords):
            QMessageBox.warning(
                self,
                'Некорректная геометрия станции',
                'Новая точка стояния совпадает с основной или расположена слишком близко. '
                'Укажите другой угол или расстояние.',
            )
            return False

        for station_idx in self._current_station_data.index.tolist():
            existing_coords = self.get_station_coordinates(int(station_idx))
            if existing_coords is None:
                continue
            if not self._stations_form_valid_angular_basis(existing_coords, new_coords):
                QMessageBox.warning(
                    self,
                    'Дублирующая станция',
                    'Новая точка стояния совпадает с уже существующей станцией или расположена слишком близко к ней.',
                )
                return False

        if 'station_role' not in self.original_data.columns:
            self.original_data['station_role'] = None

        new_index = int(self.original_data.index.max() + 1) if not self.original_data.empty else 0
        new_station = {
            'x': new_coords[0],
            'y': new_coords[1],
            'z': float(sz),
            'name': f"Станция {len(self._current_station_data) + 1}",
            'belt': None,
            'is_station': True,
            'point_index': self._determine_next_point_index(),
            'station_role': 'secondary',
            'station_origin': 'synthetic',
        }

        if self.original_data is None or self.original_data.empty:
            updated_data = pd.DataFrame({k: [v] for k, v in new_station.items()}, index=[new_index])
        else:
            template = self.original_data.iloc[0:0].copy()
            template = template.reindex([new_index])
            for column in template.columns:
                template.at[new_index, column] = new_station.get(column, pd.NA)
            extra_columns = [col for col in new_station.keys() if col not in template.columns]
            for column in extra_columns:
                template[column] = pd.NA
                template.at[new_index, column] = new_station[column]
            updated_data = pd.concat([self.original_data, template], copy=False)
        self.set_data(updated_data)
        self.secondary_station_id = new_index
        self._update_station_ids()
        self._emit_data_mutation(previous_data, 'Добавление точки стояния')
        self.data_changed.emit()
        QMessageBox.information(self, 'Точка добавлена', 'Новая точка стояния успешно создана.')
        return True

    def get_station_coordinates(self, station_id: Optional[int]) -> Optional[Tuple[float, float, float]]:
        if station_id is None or self.original_data is None or self.original_data.empty:
            return None
        try:
            row = self.original_data.loc[station_id]
        except KeyError:
            return None
        if not bool(row.get('is_station', False)):
            return None
        try:
            return float(row['x']), float(row['y']), float(row['z'])
        except (TypeError, ValueError, KeyError):
            return None

    def populate_tower_table_coordinates(self):
        """Заполняет таблицу линейных координат."""
        self.angular_tabs.hide()
        # ВАЖНО: _rebuild_cached_tower_data вызываем ПОСЛЕ чтения данных из original_data,
        # так как данные могут быть обновлены через on_tower_item_changed
        # Используем оригинальные данные без сортировки для соответствия порядку в 3D редактору
        # Сортировка может вызывать несоответствие порядка точек между таблицей и 3D видом
        if self.original_data is None or self.original_data.empty:
            data = pd.DataFrame()
        else:
            mask = self._build_is_station_mask(self.original_data['is_station'])
            data = self.original_data[~mask].copy()
            # НЕ сортируем данные, чтобы порядок соответствовал 3D редактору
        
        # Перестраиваем кэш ПОСЛЕ чтения данных из original_data
        self._rebuild_cached_tower_data()
        
        has_memberships = 'tower_part_memberships' in data.columns and data['tower_part_memberships'].notna().any()
        has_numeric_parts = 'tower_part' in data.columns and data['tower_part'].notna().any()
        is_composite = has_memberships or has_numeric_parts
        
        if is_composite:
            # Составная башня - создаем вкладки для каждой части
            self.tower_table.hide()
            self.tower_table.setRowCount(0)
            self.tower_parts_tabs.show()
            
            # Очищаем старые вкладки
            while self.tower_parts_tabs.count() > 0:
                self.tower_parts_tabs.removeTab(0)
            self.tower_part_tables.clear()
            
            unique_parts = self._collect_unique_parts(data)
            if not unique_parts and 'tower_part' in data.columns:
                unique_parts = sorted(data['tower_part'].dropna().unique())
            if not unique_parts:
                unique_parts = [1]
            
            for part_num in unique_parts:
                part_mask = data.apply(lambda row: self._row_has_part(row, part_num), axis=1)
                part_data = data[part_mask].copy()
                if part_data.empty:
                    continue
                
                # Создаем таблицу для части
                part_table = QTableWidget()
                part_table.setColumnCount(7)
                part_table.setHorizontalHeaderLabels(['№', 'Название', 'X (м)', 'Y (м)', 'Z (м)', 'Пояс', 'Сгенер.'])
                part_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
                part_table.setAlternatingRowColors(True)
                part_table.setEditTriggers(
                    QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.SelectedClicked
                )
                try:
                    part_table.itemSelectionChanged.disconnect()
                except (RuntimeError, TypeError):
                    pass
                part_table.itemSelectionChanged.connect(self.on_tower_selection_changed)
                self.setup_table_style(part_table)
                
                # Сортируем данные части по поясам и высоте перед заполнением таблицы
                part_data_sorted = part_data.copy()
                if 'belt' in part_data_sorted.columns:
                    part_data_sorted['belt_num'] = pd.to_numeric(part_data_sorted['belt'], errors='coerce')
                    part_data_sorted = part_data_sorted.sort_values(by=['belt_num', 'z'], ascending=[True, True], na_position='last')
                    part_data_sorted = part_data_sorted.drop(columns=['belt_num'])
                else:
                    part_data_sorted = part_data_sorted.sort_values(by='z', ascending=True)
                
                # Заполняем таблицу
                part_table.setRowCount(len(part_data_sorted))
                for i, (idx, row) in enumerate(part_data_sorted.iterrows()):
                    point_index_value = row.get('point_index')
                    point_index_text = ''
                    if pd.notna(point_index_value):
                        try:
                            point_index_text = str(int(point_index_value))
                        except (ValueError, TypeError):
                            point_index_text = str(point_index_value)
                    if not point_index_text:
                        point_index_text = str(i + 1)
                    item = QTableWidgetItem(point_index_text)
                    # КРИТИЧЕСКИ ВАЖНО: сохраняем point_index в UserRole для стабильной идентификации
                    # Если point_index отсутствует в данных, создаем его на основе позиции + 1 (1-based)
                    # Это гарантирует, что UserRole всегда содержит point_index, а не позицию
                    if pd.notna(point_index_value):
                        # point_index есть в данных - используем его
                        stored_point_index = int(point_index_value)
                    else:
                        # point_index отсутствует - создаем его на основе позиции (1-based)
                        # КРИТИЧЕСКИ ВАЖНО: используем i+1, а не i, так как point_index начинается с 1
                        stored_point_index = i + 1
                        logger.debug(
                            f"populate_tower_table (часть {part_num}): point_index отсутствует для строки {i}, "
                            f"создаем stored_point_index={stored_point_index} на основе позиции"
                        )
                    item.setData(Qt.ItemDataRole.UserRole, stored_point_index)
                    item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                    part_table.setItem(i, 0, item)

                    name = row.get('name', f'Точка {i+1}')
                    part_table.setItem(i, 1, QTableWidgetItem(str(name)))
                    part_table.setItem(i, 2, QTableWidgetItem(f"{row['x']:.6f}"))
                    part_table.setItem(i, 3, QTableWidgetItem(f"{row['y']:.6f}"))
                    part_table.setItem(i, 4, QTableWidgetItem(f"{row['z']:.3f}"))

                    # Для составных башен показываем part_belt (номер пояса внутри части)
                    belt = row.get('part_belt', row.get('belt', None))
                    if belt is not None:
                        try:
                            belt_text = str(int(float(belt)))
                        except (ValueError, TypeError):
                            belt_text = str(belt)
                    else:
                        belt_text = ''
                    part_table.setItem(i, 5, QTableWidgetItem(belt_text))

                    gen_flag = bool(row.get('is_generated', False))
                    gen_item = QTableWidgetItem('✓' if gen_flag else '')
                    gen_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                    part_table.setItem(i, 6, gen_item)
                
                part_table.itemChanged.connect(self.on_tower_item_changed)
                part_table.setProperty('tower_part', int(part_num))
                self.tower_parts_tabs.addTab(part_table, f'Часть {int(part_num)}')
                self.tower_part_tables[int(part_num)] = part_table
        else:
            # Обычная башня - используем основную таблицу
            self.tower_parts_tabs.hide()
            self.tower_table.show()
            self.tower_table.setEditTriggers(
                QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.SelectedClicked
            )
            self.tower_table.setColumnCount(7)
            self.tower_table.setHorizontalHeaderLabels(['№', 'Название', 'X (м)', 'Y (м)', 'Z (м)', 'Пояс', 'Сгенер.'])
            
            # Сортируем данные по поясам и высоте перед заполнением таблицы
            data_sorted = data.copy()
            if 'belt' in data_sorted.columns:
                data_sorted['belt_num'] = pd.to_numeric(data_sorted['belt'], errors='coerce')
                data_sorted = data_sorted.sort_values(by=['belt_num', 'z'], ascending=[True, True], na_position='last')
                data_sorted = data_sorted.drop(columns=['belt_num'])
            else:
                data_sorted = data_sorted.sort_values(by='z', ascending=True)
            
            self.tower_table.setRowCount(len(data_sorted))

            # Итерируемся по отсортированным данным
            for i, (idx, row) in enumerate(data_sorted.iterrows()):
                point_index_value = row.get('point_index')
                point_index_text = ''
                if pd.notna(point_index_value):
                    try:
                        point_index_text = str(int(point_index_value))
                    except (ValueError, TypeError):
                        point_index_text = str(point_index_value)
                if not point_index_text:
                    point_index_text = str(i + 1)
                item = QTableWidgetItem(point_index_text)
                # КРИТИЧЕСКИ ВАЖНО: сохраняем point_index в UserRole для стабильной идентификации
                # Если point_index отсутствует в данных, создаем его на основе позиции + 1 (1-based)
                # Это гарантирует, что UserRole всегда содержит point_index, а не позицию
                if pd.notna(point_index_value):
                    # point_index есть в данных - используем его
                    stored_user_role = int(point_index_value)
                else:
                    # point_index отсутствует - создаем его на основе позиции (1-based)
                    # КРИТИЧЕСКИ ВАЖНО: используем i+1, а не i, так как point_index начинается с 1
                    stored_user_role = i + 1
                    logger.debug(
                        f"populate_tower_table: point_index отсутствует для строки {i}, "
                        f"создаем stored_user_role={stored_user_role} на основе позиции"
                    )
                item.setData(Qt.ItemDataRole.UserRole, stored_user_role)
                
                # ДИАГНОСТИКА: логируем первые несколько строк для проверки соответствия
                if i < 5:
                    point_name = row.get('name', f'Точка {i+1}')
                    logger.debug(
                        f"populate_tower_table: Строка {i}: name={point_name}, "
                        f"point_index_value={point_index_value}, stored_user_role={stored_user_role}, "
                        f"dataframe_idx={idx}"
                    )
                
                item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                self.tower_table.setItem(i, 0, item)

                name = row.get('name', f'Точка {i+1}')
                self.tower_table.setItem(i, 1, QTableWidgetItem(str(name)))
                self.tower_table.setItem(i, 2, QTableWidgetItem(f"{row['x']:.6f}"))
                self.tower_table.setItem(i, 3, QTableWidgetItem(f"{row['y']:.6f}"))
                self.tower_table.setItem(i, 4, QTableWidgetItem(f"{row['z']:.3f}"))

                belt = row.get('belt', None)
                if belt is not None:
                    try:
                        belt_text = str(int(float(belt)))
                    except (ValueError, TypeError):
                        belt_text = str(belt)
                else:
                    belt_text = ''
                self.tower_table.setItem(i, 5, QTableWidgetItem(belt_text))

                gen_flag = bool(row.get('is_generated', False))
                gen_item = QTableWidgetItem('✓' if gen_flag else '')
                gen_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                self.tower_table.setItem(i, 6, gen_item)

        self.tower_add_btn.setEnabled(True)
        self.tower_delete_btn.setEnabled(True)

    def populate_tower_table_angles(self):
        """Заполняет таблицы теодолитных углов по осям X и Y."""
        self.tower_table.hide()
        self.angular_tabs.show()
        self._rebuild_cached_tower_data()
        data = self._current_tower_data if self._current_tower_data is not None else pd.DataFrame()
        if data.empty:
            for tbl in (self.angular_table_x, self.angular_table_y):
                tbl.setRowCount(0)
                tbl.setColumnCount(0)
            self.tower_add_btn.setEnabled(False)
            self.tower_delete_btn.setEnabled(False)
            return

        headers = ['№', 'Секция', 'H, м', 'Пояс', 'KL', 'KR', 'KL–KR (″)', 'βизм', 'Bизм', 'Δβ', 'Δb, мм']

        if self._get_station_for_axis('x') is None:
            QMessageBox.warning(self, 'Точка стояния отсутствует', 'Добавьте точку стояния для оси X.')
            if self.show_add_station_dialog():
                return
            for tbl in (self.angular_table_x, self.angular_table_y):
                tbl.setRowCount(0)
                tbl.setColumnCount(len(headers))
                tbl.setHorizontalHeaderLabels(headers)
            self.tower_add_btn.setEnabled(False)
            self.tower_delete_btn.setEnabled(False)
            return

        rows_x = self.compute_axis_rows(data, axis='x')
        self.angular_table_x.setColumnCount(len(headers))
        self.angular_table_x.setHorizontalHeaderLabels(headers)
        self.angular_table_x.setRowCount(len(rows_x))
        for row_idx, row in enumerate(rows_x):
            values = [
                str(row_idx + 1),
                str(row['section_label']),
                f"{row['height']:.1f}" if row['height'] is not None else '—',
                str(row['belt']),
                row['kl_str'],
                row['kr_str'],
                row['diff_str'],
                row['beta_str'],
                row.get('center_str', '—'),
                row['delta_str'],
                row.get('delta_mm_str', '—'),
            ]
            for col_idx, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                self.angular_table_x.setItem(row_idx, col_idx, item)

        if self._get_station_for_axis('y') is None:
            QMessageBox.information(self, 'Требуется вторая точка стояния', 'Для расчета по оси Y добавьте дополнительную точку стояния.')
            if self.show_add_station_dialog():
                self._rebuild_cached_tower_data()
                data = self._current_tower_data if self._current_tower_data is not None else pd.DataFrame()
                rows_y = self.compute_axis_rows(data, axis='y')
            else:
                self.angular_table_y.setColumnCount(len(headers))
                self.angular_table_y.setHorizontalHeaderLabels(headers)
                self.angular_table_y.setRowCount(0)
                self.tower_add_btn.setEnabled(False)
                self.tower_delete_btn.setEnabled(False)
                return
        else:
            rows_y = self.compute_axis_rows(data, axis='y')
        self.angular_table_y.setColumnCount(len(headers))
        self.angular_table_y.setHorizontalHeaderLabels(headers)
        self.angular_table_y.setRowCount(len(rows_y))
        for row_idx, row in enumerate(rows_y):
            values = [
                str(row_idx + 1),
                str(row['section_label']),
                f"{row['height']:.1f}" if row['height'] is not None else '—',
                str(row['belt']),
                row['kl_str'],
                row['kr_str'],
                row['diff_str'],
                row['beta_str'],
                row.get('center_str', '—'),
                row['delta_str'],
                row.get('delta_mm_str', '—'),
            ]
            for col_idx, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                self.angular_table_y.setItem(row_idx, col_idx, item)

        self.tower_add_btn.setEnabled(False)
        self.tower_delete_btn.setEnabled(False)

    def _get_station_for_axis(self, axis: str) -> Optional[Tuple[float, float, float]]:
        axis = (axis or 'x').lower()
        if axis == 'y':
            return self.get_station_coordinates(self.secondary_station_id)
        return self.get_station_coordinates(self.primary_station_id)

    def compute_axis_rows(self, tower_data: pd.DataFrame, axis: str) -> List[Dict[str, Any]]:
        """Формирует строки угловых измерений для заданной оси из общего payload."""
        payload = self.get_angular_verticality_payload(tower_data)
        rows = payload.get('rows_by_axis', {}).get((axis or 'x').lower(), [])
        return [dict(row) for row in rows]

    def _serialize_station_entry(self, station_id: Optional[int]) -> Optional[Dict[str, Any]]:
        if station_id is None:
            return None
        coords = self.get_station_coordinates(station_id)
        record = self._get_original_record(station_id)
        if coords is None and not record:
            return None
        station_payload: Dict[str, Any] = {'id': station_id}
        if record.get('name'):
            station_payload['name'] = record.get('name')
        if coords is not None:
            station_payload['coords'] = [float(coords[0]), float(coords[1]), float(coords[2])]
        station_origin = record.get('station_origin')
        if station_origin is not None and not pd.isna(station_origin):
            station_payload['station_origin'] = str(station_origin)
        return station_payload

    def _default_angular_verticality_payload(self) -> Dict[str, Any]:
        return {
            'x': [],
            'y': [],
            'rows_by_axis': {'x': [], 'y': []},
            'sections': [],
            'basis': self._build_angular_basis_metadata(),
            'complete': False,
            'vertical_check': self._empty_verticality_check(),
        }

    def get_angular_verticality_payload(self, tower_data: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
        """Возвращает единый payload журнала угловых измерений и вертикальности."""
        use_cache = tower_data is None or tower_data is self._current_tower_data
        if use_cache and self._angular_verticality_payload is not None:
            return self._angular_verticality_payload

        if tower_data is None:
            try:
                self._update_station_ids()
                self._rebuild_cached_tower_data()
            except Exception:
                logger.exception("Не удалось подготовить кэш данных для angular_verticality")
                payload = self._default_angular_verticality_payload()
                if use_cache:
                    self._angular_verticality_payload = payload
                return payload
            tower_data = self._current_tower_data if self._current_tower_data is not None else pd.DataFrame()

        try:
            payload = self._build_angular_verticality_payload(tower_data)
        except Exception:
            logger.exception("Ошибка при формировании payload angular_verticality")
            payload = self._default_angular_verticality_payload()
            payload['sections'] = self._build_sections_from_processed_results([])
            payload['vertical_check'] = self._build_verticality_check_from_sections(payload['sections'])

        if use_cache:
            self._angular_verticality_payload = payload
        return payload

    def _build_angular_verticality_payload(self, tower_data: pd.DataFrame) -> Dict[str, Any]:
        builder = AngularVerticalityBuilder(
            processed_results=self.processed_results,
            section_snapshots=(self.editor_3d.section_data if self.editor_3d and hasattr(self.editor_3d, 'section_data') else []),
            primary_station_coords=self._get_station_for_axis('x'),
            secondary_station_coords=self._get_station_for_axis('y'),
            basis_metadata=self._build_angular_basis_metadata(),
        )
        return builder.build_payload(tower_data)

    @staticmethod
    def _bearing_seconds_between_points(
        from_xy: np.ndarray,
        to_xy: np.ndarray,
    ) -> Optional[float]:
        vector = np.asarray(to_xy, dtype=float) - np.asarray(from_xy, dtype=float)
        norm = float(np.linalg.norm(vector))
        if norm < 1e-9:
            return None
        angle_deg = math.degrees(math.atan2(vector[1], vector[0])) % 360.0
        return angle_deg * 3600.0

    @staticmethod
    def _station_axis_projection_mm(
        station_xy: np.ndarray,
        reference_xy: np.ndarray,
        actual_xy: np.ndarray,
    ) -> Optional[float]:
        reference_vec = np.asarray(reference_xy, dtype=float) - np.asarray(station_xy, dtype=float)
        ref_norm = float(np.linalg.norm(reference_vec))
        if ref_norm < 1e-9:
            return None
        view_unit = reference_vec / ref_norm
        normal_unit = np.array([-view_unit[1], view_unit[0]], dtype=float)
        residual_xy = np.asarray(actual_xy, dtype=float) - np.asarray(reference_xy, dtype=float)
        return float(np.dot(residual_xy, normal_unit) * 1000.0)

    def _synchronize_axis_rows_with_sections(self, payload: Dict[str, Any]) -> None:
        sections = payload.get('sections')
        if not isinstance(sections, list) or not sections:
            return

        section_map = {
            section.get('section_key'): section
            for section in sections
            if isinstance(section, dict) and section.get('section_key')
        }
        if not section_map:
            return

        has_both_axes = all(self._get_station_for_axis(axis) is not None for axis in ('x', 'y'))
        section_axis_values: Dict[str, Dict[str, float]] = {}

        for axis in ('x', 'y'):
            station_coords = self._get_station_for_axis(axis)
            if station_coords is None:
                continue

            station_xy = np.array([float(station_coords[0]), float(station_coords[1])], dtype=float)
            rows = payload.get('rows_by_axis', {}).get(axis, [])
            for row in rows:
                section = section_map.get(row.get('section_key'))
                if section is None:
                    continue

                center_xy = section.get('center_xy')
                axis_point_xy = section.get('axis_point_xy')
                if center_xy is None or axis_point_xy is None:
                    continue

                actual_xy = np.asarray(center_xy, dtype=float)
                reference_xy = np.asarray(axis_point_xy, dtype=float)
                measured_sec = self._bearing_seconds_between_points(station_xy, actual_xy)
                reference_sec = self._bearing_seconds_between_points(station_xy, reference_xy)
                delta_mm = self._station_axis_projection_mm(station_xy, reference_xy, actual_xy)
                if measured_sec is None or reference_sec is None or delta_mm is None:
                    continue

                delta_sec = self._normalized_angle_diff(measured_sec, reference_sec)
                row['reference_center_sec'] = float(reference_sec)
                row['center_str'] = self._format_angle_seconds(reference_sec)
                row['delta_sec'] = float(delta_sec)
                row['delta_str'] = '0.00"' if abs(delta_sec) < 1e-9 else f"{float(delta_sec):+.2f}\""
                row['delta_mm'] = float(delta_mm)
                row['delta_mm_str'] = f"{float(delta_mm):+.1f}"

                axis_values = section_axis_values.setdefault(str(section.get('section_key')), {})
                axis_values[axis] = float(delta_mm)

        if has_both_axes:
            for section in sections:
                axis_values = section_axis_values.get(str(section.get('section_key')))
                if not axis_values:
                    continue
                if 'x' in axis_values:
                    section['deviation_x'] = float(axis_values['x'])
                if 'y' in axis_values:
                    section['deviation_y'] = float(axis_values['y'])

    @staticmethod
    def _section_snapshot_mean_z(section: Dict[str, Any]) -> Optional[float]:
        points = section.get('points', []) if isinstance(section, dict) else []
        if not isinstance(points, (list, tuple)) or not points:
            return None

        z_values: List[float] = []
        for point in points:
            if not isinstance(point, (list, tuple)) or len(point) < 3:
                continue
            try:
                z_value = float(point[2])
            except (TypeError, ValueError):
                continue
            if np.isfinite(z_value):
                z_values.append(z_value)

        if not z_values:
            return None
        return float(np.mean(z_values))

    @classmethod
    def _section_height_candidates(cls, section: Dict[str, Any]) -> List[float]:
        candidates: List[float] = []
        raw_values = [
            section.get('center_z'),
            section.get('height'),
            cls._section_snapshot_mean_z(section),
        ]
        for raw_value in raw_values:
            try:
                candidate = float(raw_value)
            except (TypeError, ValueError):
                continue
            if not np.isfinite(candidate):
                continue
            if any(abs(existing - candidate) <= 1e-6 for existing in candidates):
                continue
            candidates.append(candidate)
        return candidates

    @classmethod
    def _section_sort_height(cls, section: Dict[str, Any]) -> float:
        candidates = cls._section_height_candidates(section)
        return candidates[0] if candidates else 0.0

    def _match_section_points_from_tower_data(
        self,
        section: Dict[str, Any],
        tower_df: pd.DataFrame,
        tolerance: float = 0.3,
    ) -> pd.DataFrame:
        if tower_df is None or tower_df.empty or 'z' not in tower_df.columns:
            return pd.DataFrame(columns=['x', 'y', 'z', 'belt'])

        section_heights = self._section_height_candidates(section)
        if not section_heights:
            return pd.DataFrame(columns=['x', 'y', 'z', 'belt'])

        numeric_z = pd.to_numeric(tower_df['z'], errors='coerce')
        section_memberships = self._extract_part_memberships(section)
        part_mask = pd.Series(True, index=tower_df.index)
        if section_memberships:
            part_mask = pd.Series(False, index=tower_df.index)
            if 'tower_part_memberships' in tower_df.columns:
                for membership in section_memberships:
                    encoded = tower_df['tower_part_memberships'].map(
                        lambda value: membership in self._decode_part_memberships(value)
                    )
                    part_mask |= encoded.fillna(False)
            if 'tower_part' in tower_df.columns:
                numeric_parts = pd.to_numeric(tower_df['tower_part'], errors='coerce')
                part_mask |= numeric_parts.isin(section_memberships)

        belt_sequence = section.get('belt_nums', []) if isinstance(section.get('belt_nums'), (list, tuple)) else []
        belt_mask = pd.Series(True, index=tower_df.index)
        if belt_sequence and 'belt' in tower_df.columns:
            belt_values = [self._safe_int(value) for value in belt_sequence]
            belt_values = [value for value in belt_values if value is not None]
            if belt_values:
                numeric_belts = pd.to_numeric(tower_df['belt'], errors='coerce')
                belt_mask = numeric_belts.isin(belt_values)

        points_df = pd.DataFrame(columns=['x', 'y', 'z', 'belt'])
        for section_height in section_heights:
            mask = numeric_z.notna() & (numeric_z.sub(section_height).abs() <= float(tolerance))
            if section_memberships and part_mask.any():
                mask &= part_mask
            if belt_sequence and 'belt' in tower_df.columns and (mask & belt_mask).any():
                mask &= belt_mask
            candidate_df = tower_df[mask].copy()
            if candidate_df.empty:
                continue
            points_df = candidate_df
            break

        if points_df.empty:
            return pd.DataFrame(columns=['x', 'y', 'z', 'belt'])

        if 'belt' not in points_df.columns:
            points_df['belt'] = [None] * len(points_df)
            return points_df

        if belt_sequence:
            belt_order = {
                belt_num: order
                for order, belt_num in enumerate(
                    value for value in (self._safe_int(item) for item in belt_sequence) if value is not None
                )
            }
            numeric_belts = pd.to_numeric(points_df['belt'], errors='coerce')
            points_df = points_df.assign(
                _belt_order=numeric_belts.map(lambda value: belt_order.get(self._safe_int(value), len(belt_order)))
            ).sort_values(by=['_belt_order', 'z'], ascending=[True, True]).drop(columns=['_belt_order'])

        return points_df

    def _build_section_points_df_from_snapshot(self, section: Dict[str, Any]) -> pd.DataFrame:
        points = section.get('points', []) or []
        points_df = pd.DataFrame(points, columns=['x', 'y', 'z']) if points else pd.DataFrame(columns=['x', 'y', 'z'])
        belt_sequence = section.get('belt_nums', []) if isinstance(section.get('belt_nums'), (list, tuple)) else None
        if not points_df.empty:
            if belt_sequence and len(belt_sequence) == len(points_df):
                points_df['belt'] = list(belt_sequence)
            else:
                points_df['belt'] = [None] * len(points_df)
        return points_df

    def _prepare_angular_sections(self, tower_data: Optional[pd.DataFrame]) -> List[Dict[str, Any]]:
        section_entries: List[Dict[str, Any]] = []
        tower_df = tower_data.copy() if isinstance(tower_data, pd.DataFrame) else pd.DataFrame()

        if self.editor_3d and hasattr(self.editor_3d, 'section_data') and self.editor_3d.section_data:
            sections = sorted(self.editor_3d.section_data or [], key=self._section_sort_height)
            self._ensure_section_numbers(sections)
            matched_current_sections = 0

            for index, section in enumerate(sections):
                points_df = self._match_section_points_from_tower_data(section, tower_df, tolerance=0.3)
                if not points_df.empty:
                    matched_current_sections += 1
                elif tower_df.empty:
                    points_df = self._build_section_points_df_from_snapshot(section)
                else:
                    continue

                belt_sequence = section.get('belt_nums', []) if isinstance(section.get('belt_nums'), (list, tuple)) else None

                section_num = self._safe_int(section.get('section_num'), index)
                part_memberships = self._extract_part_memberships(section)
                section_height = (
                    float(points_df['z'].mean())
                    if not points_df.empty and 'z' in points_df.columns
                    else self._section_sort_height(section)
                )
                section_entries.append({
                    'section_key': self._make_section_key(section_num, section_height),
                    'section_num': section_num,
                    'section_label': section.get('name') or section.get('label') or str(section_num),
                    'height': section_height,
                    'points_df': points_df,
                    'belt_sequence': belt_sequence,
                    'part_memberships': part_memberships,
                    'part_num': part_memberships[0] if part_memberships else None,
                })
            if section_entries and matched_current_sections:
                return section_entries

        if tower_df.empty or 'z' not in tower_df.columns:
            return []

        numeric_z = pd.to_numeric(tower_df['z'], errors='coerce')
        heights = sorted(numeric_z.dropna().unique())
        for index, height in enumerate(heights):
            points_df = tower_df[np.isclose(numeric_z, height)].copy()
            if points_df.empty:
                continue
            if 'belt' not in points_df.columns:
                points_df['belt'] = [None] * len(points_df)
            section_num = index
            part_memberships = self._extract_part_memberships(points_df)
            section_entries.append({
                'section_key': self._make_section_key(section_num, height),
                'section_num': section_num,
                'section_label': str(section_num),
                'height': float(height),
                'points_df': points_df,
                'belt_sequence': None,
                'part_memberships': part_memberships,
                'part_num': part_memberships[0] if part_memberships else None,
            })
        return section_entries

    def _extract_part_memberships(self, source: Any) -> List[int]:
        memberships = set()

        if isinstance(source, pd.DataFrame):
            if 'tower_part_memberships' in source.columns:
                for value in source['tower_part_memberships'].dropna():
                    memberships.update(self._decode_part_memberships(value))
            if not memberships and 'tower_part' in source.columns:
                for value in source['tower_part'].dropna().tolist():
                    safe_value = self._safe_int(value)
                    if safe_value is not None:
                        memberships.add(safe_value)
            if not memberships and 'segment' in source.columns:
                for value in source['segment'].dropna().tolist():
                    safe_value = self._safe_int(value)
                    if safe_value is not None:
                        memberships.add(safe_value)
            return sorted(memberships)

        if isinstance(source, dict):
            memberships.update(self._decode_part_memberships(source.get('tower_part_memberships')))
            if not memberships:
                safe_value = self._safe_int(source.get('tower_part'))
                if safe_value is not None:
                    memberships.add(safe_value)
            if not memberships:
                safe_value = self._safe_int(source.get('segment'))
                if safe_value is not None:
                    memberships.add(safe_value)
        return sorted(memberships)

    @staticmethod
    def _section_height_tolerance(entries: List[Dict[str, Any]]) -> float:
        heights = sorted(
            {
                round(float(entry.get('height', 0.0) or 0.0), 6)
                for entry in entries
                if entry.get('height') is not None
            }
        )
        if len(heights) > 1:
            min_step = min(abs(heights[idx] - heights[idx - 1]) for idx in range(1, len(heights)))
            return max(0.05, min(1.5, float(min_step) * 0.6))
        return 0.3

    def _match_section_entry_by_height(
        self,
        height: float,
        section_entries: List[Dict[str, Any]],
        tolerance: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        if not section_entries:
            return None
        tolerance = self._section_height_tolerance(section_entries) if tolerance is None else tolerance

        matched_entry = None
        matched_diff = float('inf')
        for entry in section_entries:
            entry_height = entry.get('height')
            if entry_height is None:
                continue
            diff = abs(float(entry_height) - float(height))
            if diff <= tolerance and diff < matched_diff:
                matched_entry = entry
                matched_diff = diff
        return matched_entry

    @staticmethod
    def _infer_mm_scale(series: pd.Series) -> float:
        numeric = pd.to_numeric(series, errors='coerce').to_numpy(dtype=float)
        valid = numeric[np.isfinite(numeric)]
        if valid.size == 0:
            return 1.0
        return 1000.0 if float(np.nanmax(np.abs(valid))) < 2.0 else 1.0

    def _build_axis_based_sections_from_centers(
        self,
        center_rows: List[Dict[str, Any]],
        *,
        source: str,
        reference_mode: str = 'best_fit',
    ) -> List[Dict[str, Any]]:
        if not center_rows:
            return []

        centers_df = pd.DataFrame(
            [
                {
                    'section_key': row.get('section_key'),
                    'section_num': row.get('section_num'),
                    'section_label': row.get('section_label'),
                    'x': float(row['center_xy'][0]),
                    'y': float(row['center_xy'][1]),
                    'z': float(row.get('height', 0.0) or 0.0),
                    'tower_part': row.get('part_num'),
                    'tower_part_memberships': json.dumps(row.get('part_memberships', []) or [], ensure_ascii=False),
                }
                for row in center_rows
                if row.get('center_xy') is not None
            ]
        )
        if centers_df.empty:
            return []

        centers_df = centers_df.sort_values('z').reset_index(drop=True)
        primary_station = self._get_station_for_axis('x')
        standing_point = {'x': 0.0, 'y': 0.0, 'z': 0.0}
        if primary_station is not None:
            standing_point = {
                'x': float(primary_station[0]),
                'y': float(primary_station[1]),
                'z': float(primary_station[2]),
            }

        local_cs = calculate_local_coordinate_system(centers_df, standing_point, None)
        x_axis = np.array(local_cs.get('x_axis', (1.0, 0.0, 0.0)), dtype=float)
        y_axis = np.array(local_cs.get('y_axis', (0.0, 1.0, 0.0)), dtype=float)

        baseline_by_part: Dict[int, Dict[str, Any]] = {}
        for row in sorted(
            center_rows,
            key=lambda item: (
                float(item.get('height', 0.0) or 0.0),
                self._safe_int(item.get('section_num'), 10**9),
            ),
        ):
            center_xy = row.get('center_xy')
            if center_xy is None:
                continue
            part_key = int(row['part_num']) if row.get('part_num') is not None else 0
            baseline_by_part.setdefault(part_key, row)

        basis_complete = reference_mode == 'baseline_by_part'
        allow_station_component_override = source == 'stations' and basis_complete
        result: List[Dict[str, Any]] = []

        for row in sorted(
            center_rows,
            key=lambda item: (
                float(item.get('height', 0.0) or 0.0),
                self._safe_int(item.get('section_num'), 10**9),
            ),
        ):
            center_xy = row.get('center_xy')
            if center_xy is None:
                continue

            height = float(row.get('height', 0.0) or 0.0)
            part_key = int(row['part_num']) if row.get('part_num') is not None else 0
            baseline_row = baseline_by_part.get(part_key)
            baseline_center_xy = baseline_row.get('center_xy') if baseline_row is not None else None
            if baseline_center_xy is None:
                baseline_center_xy = center_xy

            axis_point_xy = (
                float(baseline_center_xy[0]),
                float(baseline_center_xy[1]),
            )
            current_center_xy = np.array(
                [float(center_xy[0]), float(center_xy[1]), 0.0],
                dtype=float,
            )
            baseline_center_xyz = np.array(
                [float(baseline_center_xy[0]), float(baseline_center_xy[1]), 0.0],
                dtype=float,
            )

            shift_vector = current_center_xy - baseline_center_xyz
            resolved_shift_xy_mm = row.get('resolved_shift_xy_mm')
            if isinstance(resolved_shift_xy_mm, (list, tuple)) and len(resolved_shift_xy_mm) >= 2:
                try:
                    shift_vector = np.array(
                        [
                            float(resolved_shift_xy_mm[0]) / 1000.0,
                            float(resolved_shift_xy_mm[1]) / 1000.0,
                            0.0,
                        ],
                        dtype=float,
                    )
                except (TypeError, ValueError):
                    pass

            local_deviation_x_mm = float(np.dot(shift_vector, x_axis) * 1000.0)
            local_deviation_y_mm = float(np.dot(shift_vector, y_axis) * 1000.0)
            total_deviation_mm = float(np.linalg.norm(shift_vector[:2]) * 1000.0)

            deviation_x_mm = local_deviation_x_mm
            deviation_y_mm = local_deviation_y_mm
            if allow_station_component_override:
                station_deviation_x = row.get('station_deviation_x')
                station_deviation_y = row.get('station_deviation_y')
                if station_deviation_x is not None:
                    deviation_x_mm = float(station_deviation_x)
                if station_deviation_y is not None:
                    deviation_y_mm = float(station_deviation_y)

            merged_row = dict(row)
            merged_row.update({
                'axis_point_xy': axis_point_xy,
                'local_deviation_x': local_deviation_x_mm,
                'local_deviation_y': local_deviation_y_mm,
                'deviation_x': deviation_x_mm,
                'deviation_y': deviation_y_mm,
                'total_deviation': total_deviation_mm,
                'deviation': total_deviation_mm,
                'tolerance': float(get_vertical_tolerance(height) * 1000.0),
                'source': source,
                'basis_complete': basis_complete,
            })
            result.append(merged_row)

        return result

    def _build_sections_from_processed_results(self, section_entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        results = self.processed_results
        if not results:
            return []

        centers = results.get('centers')
        if centers is None:
            return []

        if isinstance(centers, pd.DataFrame):
            centers_df = centers.copy()
        else:
            try:
                centers_df = pd.DataFrame(centers)
            except Exception:
                logger.exception("?? ??????? ????????????? centers ? DataFrame ??? fallback-??????????????")
                return []

        if centers_df.empty:
            return []

        height_col = next((candidate for candidate in ('z', 'height', 'belt_height') if candidate in centers_df.columns), None)
        if height_col is None or 'x' not in centers_df.columns or 'y' not in centers_df.columns:
            return []

        tolerance = self._section_height_tolerance(section_entries)
        existing_nums = [self._safe_int(entry.get('section_num')) for entry in section_entries]
        existing_nums = [num for num in existing_nums if num is not None]
        next_section_num = (max(existing_nums) + 1) if existing_nums else 0
        center_rows: List[Dict[str, Any]] = []

        for _, row in centers_df.sort_values(height_col).iterrows():
            try:
                height = float(row[height_col])
                center_xy = (float(row.get('x', 0.0) or 0.0), float(row.get('y', 0.0) or 0.0))
            except (TypeError, ValueError):
                continue

            matched_entry = self._match_section_entry_by_height(height, section_entries, tolerance=tolerance)
            if matched_entry is not None:
                section_num = matched_entry.get('section_num')
                section_label = matched_entry.get('section_label')
                part_num = matched_entry.get('part_num')
                part_memberships = matched_entry.get('part_memberships', [])
            else:
                section_num = next_section_num
                section_label = str(section_num)
                part_memberships = self._extract_part_memberships(row)
                part_num = part_memberships[0] if part_memberships else self._safe_int(row.get('tower_part'))
                next_section_num += 1

            center_rows.append({
                'section_key': self._make_section_key(section_num, height),
                'section_num': section_num,
                'section_label': section_label,
                'height': height,
                'center_xy': center_xy,
                'part_num': part_num,
                'part_memberships': list(part_memberships),
            })

        return self._build_axis_based_sections_from_centers(
            center_rows,
            source='processed',
            reference_mode='best_fit',
        )

    def _finalize_axis_rows(
        self,
        axis: str,
        station_coords: Tuple[float, float, float],
        raw_rows: List[Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, Any]]]:
        if not raw_rows:
            return [], {}

        station_xy = np.array([float(station_coords[0]), float(station_coords[1])], dtype=float)
        section_map: Dict[str, Dict[str, Any]] = {}

        for row in raw_rows:
            section_key = row.get('section_key')
            if section_key is None:
                continue
            if section_key not in section_map:
                section_map[section_key] = {
                    'section_key': section_key,
                    'section_num': row.get('section_num'),
                    'section_label': row.get('section_label'),
                    'height': float(row.get('height', 0.0) or 0.0),
                    'center_sec': row.get('center_sec'),
                    'center_xy': row.get('center_xy'),
                    'center_range_m': row.get('center_range_m'),
                    'part_num': row.get('part_num'),
                    'part_memberships': list(row.get('part_memberships', []) or []),
                    'center_ranges': [],
                }
            center_range_m = row.get('center_range_m')
            if center_range_m is not None:
                section_map[section_key]['center_ranges'].append(float(center_range_m))

        for section in section_map.values():
            center_ranges = [value for value in section.pop('center_ranges', []) if value is not None]
            if center_ranges:
                section['center_range_m'] = float(np.mean(center_ranges))

        baseline_by_part: Dict[int, Dict[str, Any]] = {}
        for section in section_map.values():
            part_key = int(section['part_num']) if section.get('part_num') is not None else 0
            current = baseline_by_part.get(part_key)
            if current is None or section['height'] < current['height']:
                baseline_by_part[part_key] = section

        finalized_rows: List[Dict[str, Any]] = []
        axis_sections: Dict[str, Dict[str, Any]] = {}

        for row in sorted(
            raw_rows,
            key=lambda item: (
                float(item.get('height', 0.0) or 0.0),
                self._safe_int(item.get('section_num'), 10**9),
                str(item.get('belt', '')),
            ),
        ):
            section_key = row.get('section_key')
            section = section_map.get(section_key)
            if section is None:
                continue

            part_key = int(section['part_num']) if section.get('part_num') is not None else 0
            baseline = baseline_by_part.get(part_key)
            center_sec = section.get('center_sec')
            baseline_center_sec = baseline.get('center_sec') if baseline is not None else None
            center_xy = np.asarray(section.get('center_xy', (0.0, 0.0)), dtype=float)
            baseline_xy = np.asarray(baseline.get('center_xy', (0.0, 0.0)), dtype=float) if baseline is not None else None
            center_range_m = section.get('center_range_m')

            delta_sec = None
            delta_mm = None
            normal_xy = None

            if baseline is not None and center_sec is not None and baseline_center_sec is not None:
                delta_sec = self._normalized_angle_diff(float(center_sec), float(baseline_center_sec))
                baseline_view = baseline_xy - station_xy
                baseline_norm = float(np.linalg.norm(baseline_view))
                if baseline_norm >= 1e-9:
                    view_unit = baseline_view / baseline_norm
                    normal_xy = np.array([-view_unit[1], view_unit[0]], dtype=float)
                    if section_key == baseline['section_key']:
                        delta_sec = 0.0
                        delta_mm = 0.0
                    else:
                        if center_range_m is not None:
                            delta_rad = math.radians(float(delta_sec) / 3600.0)
                            delta_mm = float(math.sin(delta_rad) * float(center_range_m) * 1000.0)
                elif section_key == baseline['section_key']:
                    delta_sec = 0.0
                    delta_mm = 0.0

            row_copy = dict(row)
            row_copy['axis'] = axis
            row_copy['center_sec'] = center_sec
            row_copy['center_range_m'] = center_range_m
            row_copy['center_str'] = self._format_angle_seconds(center_sec)
            if delta_sec is None:
                row_copy['delta_sec'] = None
                row_copy['delta_str'] = '—'
            else:
                row_copy['delta_sec'] = float(delta_sec)
                row_copy['delta_str'] = '0.00"' if abs(delta_sec) < 1e-9 else f"{float(delta_sec):+.2f}\""
            if delta_mm is None:
                row_copy['delta_mm'] = None
                row_copy['delta_mm_str'] = '—'
            else:
                row_copy['delta_mm'] = float(delta_mm)
                row_copy['delta_mm_str'] = f"{float(delta_mm):+.1f}"
            finalized_rows.append(row_copy)

            axis_sections[section_key] = {
                'section_key': section_key,
                'section_num': section.get('section_num'),
                'section_label': section.get('section_label'),
                'height': section.get('height'),
                'deviation_mm': float(delta_mm) if delta_mm is not None else None,
                'center_xy': tuple(center_xy.tolist()),
                'center_sec': center_sec,
                'center_range_m': float(center_range_m) if center_range_m is not None else None,
                'part_num': section.get('part_num'),
                'part_memberships': list(section.get('part_memberships', []) or []),
                'normal_xy': tuple(normal_xy.tolist()) if normal_xy is not None else None,
                'station_coords': [float(station_coords[0]), float(station_coords[1]), float(station_coords[2])],
                'axis': axis,
                'basis_complete': normal_xy is not None and delta_mm is not None,
            }

        return finalized_rows, axis_sections

    def _solve_station_shift(
        self,
        section_x: Optional[Dict[str, Any]],
        section_y: Optional[Dict[str, Any]],
    ) -> Optional[np.ndarray]:
        if section_x is None or section_y is None:
            return None
        if section_x.get('deviation_mm') is None or section_y.get('deviation_mm') is None:
            return None
        if section_x.get('normal_xy') is None or section_y.get('normal_xy') is None:
            return None

        matrix = np.array([section_x['normal_xy'], section_y['normal_xy']], dtype=float)
        rhs = np.array([
            float(section_x['deviation_mm']) / 1000.0,
            float(section_y['deviation_mm']) / 1000.0,
        ], dtype=float)
        if abs(float(np.linalg.det(matrix))) < 1e-8:
            return None
        try:
            return np.linalg.solve(matrix, rhs)
        except np.linalg.LinAlgError:
            return None

    @staticmethod
    def _direction_from_angle_seconds(angle_sec: Optional[float]) -> Optional[np.ndarray]:
        if angle_sec is None:
            return None
        angle_rad = math.radians(float(angle_sec) / 3600.0)
        return np.array([math.cos(angle_rad), math.sin(angle_rad)], dtype=float)

    def _intersect_station_rays(
        self,
        section_x: Optional[Dict[str, Any]],
        section_y: Optional[Dict[str, Any]],
    ) -> Optional[np.ndarray]:
        if section_x is None or section_y is None:
            return None
        if section_x.get('center_sec') is None or section_y.get('center_sec') is None:
            return None
        if section_x.get('station_coords') is None or section_y.get('station_coords') is None:
            return None

        station_x = np.array(section_x['station_coords'][:2], dtype=float)
        station_y = np.array(section_y['station_coords'][:2], dtype=float)
        direction_x = self._direction_from_angle_seconds(section_x.get('center_sec'))
        direction_y = self._direction_from_angle_seconds(section_y.get('center_sec'))
        if direction_x is None or direction_y is None:
            return None

        matrix = np.column_stack((direction_x, -direction_y))
        if abs(float(np.linalg.det(matrix))) < 1e-8:
            return None
        rhs = station_y - station_x
        try:
            parameters = np.linalg.solve(matrix, rhs)
        except np.linalg.LinAlgError:
            return None

        return station_x + float(parameters[0]) * direction_x

    def _build_sections_from_axis_payload(
        self,
        axis_sections: Dict[str, Dict[str, Dict[str, Any]]],
        *,
        authoritative: bool = True,
    ) -> List[Dict[str, Any]]:
        sections_x = axis_sections.get('x', {})
        sections_y = axis_sections.get('y', {})
        all_keys = set(sections_x.keys()) | set(sections_y.keys())
        result: List[Dict[str, Any]] = []
        baseline_by_part_x: Dict[int, Dict[str, Any]] = {}
        baseline_by_part_y: Dict[int, Dict[str, Any]] = {}

        for section in sections_x.values():
            part_key = int(section['part_num']) if section.get('part_num') is not None else 0
            current = baseline_by_part_x.get(part_key)
            if current is None or float(section.get('height', 0.0) or 0.0) < float(current.get('height', 0.0) or 0.0):
                baseline_by_part_x[part_key] = section

        for section in sections_y.values():
            part_key = int(section['part_num']) if section.get('part_num') is not None else 0
            current = baseline_by_part_y.get(part_key)
            if current is None or float(section.get('height', 0.0) or 0.0) < float(current.get('height', 0.0) or 0.0):
                baseline_by_part_y[part_key] = section

        for section_key in sorted(
            all_keys,
            key=lambda key: (
                float((sections_x.get(key) or sections_y.get(key) or {}).get('height', 0.0) or 0.0),
                self._safe_int((sections_x.get(key) or sections_y.get(key) or {}).get('section_num'), 10**9),
            ),
        ):
            section_x = sections_x.get(section_key)
            section_y = sections_y.get(section_key)
            meta = section_x or section_y
            if meta is None:
                continue

            part_key = int(meta['part_num']) if meta.get('part_num') is not None else 0
            baseline_section_x = baseline_by_part_x.get(part_key)
            baseline_section_y = baseline_by_part_y.get(part_key)

            shift_xy = None
            current_center_xy = self._intersect_station_rays(section_x, section_y)
            baseline_center_xy = self._intersect_station_rays(baseline_section_x, baseline_section_y)
            if current_center_xy is not None and baseline_center_xy is not None:
                shift_xy = current_center_xy - baseline_center_xy
            else:
                shift_xy = self._solve_station_shift(section_x, section_y)
            if current_center_xy is None and shift_xy is not None and baseline_center_xy is not None:
                current_center_xy = baseline_center_xy + shift_xy
            if current_center_xy is None and meta.get('center_xy') is not None:
                current_center_xy = np.asarray(meta.get('center_xy'), dtype=float)

            height = float(meta.get('height', 0.0) or 0.0)
            result.append({
                'section_key': section_key,
                'section_num': meta.get('section_num'),
                'section_label': meta.get('section_label'),
                'height': height,
                'part_num': meta.get('part_num'),
                'part_memberships': list(meta.get('part_memberships', []) or []),
                'center_xy': tuple(current_center_xy.tolist()) if current_center_xy is not None else None,
                'station_deviation_x': float(section_x.get('deviation_mm', 0.0) or 0.0) if section_x is not None else 0.0,
                'station_deviation_y': float(section_y.get('deviation_mm', 0.0) or 0.0) if section_y is not None else 0.0,
                'resolved_shift_xy_mm': [float(shift_xy[0] * 1000.0), float(shift_xy[1] * 1000.0)] if shift_xy is not None else None,
            })

        return self._build_axis_based_sections_from_centers(
            result,
            source='stations',
            reference_mode='baseline_by_part' if authoritative else 'best_fit',
        )

    def _merge_station_sections_with_fallback(
        self,
        station_sections: List[Dict[str, Any]],
        fallback_sections: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        station_map = {item['section_key']: dict(item) for item in station_sections if item.get('section_key')}
        fallback_map = {item['section_key']: dict(item) for item in fallback_sections if item.get('section_key')}
        all_keys = set(station_map.keys()) | set(fallback_map.keys())
        merged: List[Dict[str, Any]] = []

        for section_key in sorted(
            all_keys,
            key=lambda key: (
                float((station_map.get(key) or fallback_map.get(key) or {}).get('height', 0.0) or 0.0),
                self._safe_int((station_map.get(key) or fallback_map.get(key) or {}).get('section_num'), 10**9),
            ),
        ):
            station_section = station_map.get(section_key)
            fallback_section = fallback_map.get(section_key)

            if station_section is not None and station_section.get('total_deviation') is not None:
                merged_item = dict(station_section)
            elif fallback_section is not None:
                merged_item = dict(fallback_section)
                if station_section is not None:
                    merged_item['source'] = 'processed_fallback'
                    merged_item['station_deviation_x'] = station_section.get('deviation_x')
                    merged_item['station_deviation_y'] = station_section.get('deviation_y')
                    merged_item['station_total_deviation'] = station_section.get('total_deviation')
            elif station_section is not None:
                merged_item = dict(station_section)
                available = [
                    abs(float(value))
                    for value in (merged_item.get('deviation_x'), merged_item.get('deviation_y'))
                    if value is not None
                ]
                total_deviation = max(available) if available else 0.0
                merged_item['total_deviation'] = float(total_deviation)
                merged_item['deviation'] = float(total_deviation)
                merged_item['source'] = 'stations_partial'
            else:
                continue

            height = float(merged_item.get('height', 0.0) or 0.0)
            merged_item.setdefault('tolerance', float(get_vertical_tolerance(height) * 1000.0))
            merged.append(merged_item)

        return merged

    def _build_verticality_check_from_sections(self, sections: List[Dict[str, Any]]) -> Dict[str, Any]:
        return build_verticality_check_from_sections(sections)


    def _build_axis_rows_from_points(
        self,
        points_df: pd.DataFrame,
        station_coords: Tuple[float, float, float],
        section_label: str,
        section_num: Optional[int],
        part_num: Optional[int],
        part_memberships: Optional[Iterable[int]],
        section_height: Optional[float],
        belt_sequence: Optional[Iterable[Any]] = None,
    ) -> List[Dict[str, Any]]:
        if points_df is None or points_df.empty:
            return []

        station_xy = np.array([station_coords[0], station_coords[1]], dtype=float)
        center_xy = points_df[['x', 'y']].mean().to_numpy(dtype=float)
        view_vec = center_xy - station_xy
        view_norm = np.linalg.norm(view_vec)
        if view_norm < 1e-6:
            view_dir = np.array([1.0, 0.0])
            center_bearing_deg = 0.0
        else:
            view_dir = view_vec / view_norm
            center_bearing_deg = math.degrees(math.atan2(view_vec[1], view_vec[0])) % 360.0
        perp_dir = np.array([-view_dir[1], view_dir[0]])

        if section_height is None or pd.isna(section_height):
            height = float(points_df['z'].mean())
        else:
            height = float(section_height)
        center_sec = self._normalize_angle_seconds(center_bearing_deg * 3600.0)
        center_range_m = float(view_norm if view_norm >= 1e-6 else 0.0)

        candidates = []
        belt_summary: Dict[Any, Dict[str, Any]] = {}
        for _, row in points_df.iterrows():
            px, py = float(row['x']), float(row['y'])
            vec = np.array([px - station_xy[0], py - station_xy[1]], dtype=float)
            dist = np.linalg.norm(vec)
            if dist < 1e-6:
                continue
            bearing = math.degrees(math.atan2(vec[1], vec[0])) % 360.0
            delta = (bearing - center_bearing_deg + 540.0) % 360.0 - 180.0
            belt = row.get('belt')
            offset = vec @ perp_dir
            entry = {
                'bearing': bearing,
                'delta': delta,
                'belt': belt,
                'dist': dist,
                'offset': offset,
            }
            candidates.append(entry)

            key = belt
            if key not in belt_summary:
                belt_summary[key] = entry
            else:
                current = belt_summary[key]
                current_score = (abs(current['offset']), abs(current['delta']), current['dist'])
                new_score = (abs(offset), abs(delta), dist)
                if new_score < current_score:
                    belt_summary[key] = entry

        if not belt_summary:
            return []

        adjacency_lookup: Dict[Any, Tuple[Any, Any]] = {}
        if belt_sequence:
            belt_order = [b for b in belt_sequence if b in belt_summary]
            if len(belt_order) >= 2:
                seq_len = len(belt_order)
                for idx, belt in enumerate(belt_order):
                    prev_belt = belt_order[(idx - 1) % seq_len]
                    next_belt = belt_order[(idx + 1) % seq_len]
                    adjacency_lookup[belt] = (prev_belt, next_belt)

        aggregated = list(belt_summary.values())
        aggregated.sort(key=lambda e: (e['dist'], abs(e['delta']), abs(e['offset'])))

        selected_pair: Optional[Tuple[Dict[str, Any], Dict[str, Any]]] = None
        for i in range(len(aggregated)):
            first = aggregated[i]
            for j in range(i + 1, len(aggregated)):
                second = aggregated[j]
                if first.get('belt') is not None and first.get('belt') == second.get('belt'):
                    continue
                if adjacency_lookup:
                    belt_first = first.get('belt')
                    belt_second = second.get('belt')
                    neighbors_first = adjacency_lookup.get(belt_first)
                    neighbors_second = adjacency_lookup.get(belt_second)
                    if neighbors_first and belt_second not in neighbors_first:
                        continue
                    if neighbors_second and belt_first not in neighbors_second:
                        continue
                selected_pair = (first, second)
                break
            if selected_pair:
                break

        if not selected_pair:
            if len(aggregated) >= 2:
                selected_pair = (aggregated[0], aggregated[1])
            else:
                candidates_sorted = sorted(candidates, key=lambda e: e['dist'])
                if len(candidates_sorted) >= 2:
                    selected_pair = (candidates_sorted[0], candidates_sorted[1])
                else:
                    return []

        first_entry, second_entry = selected_pair

        if first_entry is second_entry:
            return []

        # Определяем ориентацию: положительный delta означает левее направления на центр
        left_entry = first_entry
        right_entry = second_entry
        if right_entry['delta'] > left_entry['delta']:
            left_entry, right_entry = right_entry, left_entry
        if left_entry['delta'] < right_entry['delta']:
            left_entry, right_entry = right_entry, left_entry

        rows = []
        rows.append(self._create_angle_row_from_bearings(
            section_label=section_label,
            section_num=section_num,
            part_num=part_num,
            part_memberships=part_memberships,
            height=height,
            side_label=f"Левый (Пояс {left_entry['belt']})" if left_entry['belt'] is not None else 'Левый',
            bearing_deg=left_entry['bearing'],
            center_sec=center_sec,
            center_range_m=center_range_m,
            center_xy=tuple(center_xy),
        ))
        rows.append(self._create_angle_row_from_bearings(
            section_label=section_label,
            section_num=section_num,
            part_num=part_num,
            part_memberships=part_memberships,
            height=height,
            side_label=f"Правый (Пояс {right_entry['belt']})" if right_entry['belt'] is not None else 'Правый',
            bearing_deg=right_entry['bearing'],
            center_sec=center_sec,
            center_range_m=center_range_m,
            center_xy=tuple(center_xy),
        ))
        return [row for row in rows if row]

    def _create_angle_row_from_bearings(
        self,
        section_label: str,
        section_num: Optional[int],
        part_num: Optional[int],
        part_memberships: Optional[Iterable[int]],
        height: float,
        side_label: str,
        bearing_deg: float,
        center_sec: float,
        center_range_m: float,
        center_xy: Tuple[float, float],
    ) -> Optional[Dict[str, Any]]:
        target_sec = self._normalize_angle_seconds((bearing_deg % 360.0) * 3600.0)
        diff_sec = self._deterministic_circle_difference_seconds(
            section_num=section_num,
            section_label=section_label,
            side_label=side_label,
            height=height,
            target_sec=target_sec,
        )
        half_diff_sec = diff_sec / 2.0
        kl_sec = self._normalize_angle_seconds(target_sec + half_diff_sec)
        direct_kr_sec = self._normalize_angle_seconds(target_sec - half_diff_sec)
        kr_sec = self._normalize_angle_seconds(direct_kr_sec + 648000.0)

        beta_sec = self._compute_beta_seconds(kl_sec, kr_sec)

        return {
            'section_key': self._make_section_key(section_num, height),
            'section_num': section_num,
            'section_label': section_label,
            'part_num': part_num,
            'part_memberships': list(part_memberships or []),
            'belt': side_label,
            'height': height,
            'kl_sec': kl_sec,
            'kr_sec': kr_sec,
            'direct_kr_sec': direct_kr_sec,
            'diff_sec': diff_sec,
            'beta_sec': beta_sec,
            'center_sec': center_sec,
            'center_range_m': center_range_m,
            'center_xy': center_xy,
            'kl_str': self._format_angle_seconds(kl_sec),
            'kr_str': self._format_angle_seconds(kr_sec),
            'diff_str': '0.00"' if abs(diff_sec) < 1e-9 else f"{diff_sec:+.2f}\"",
            'beta_str': self._format_angle_seconds(beta_sec),
            'center_str': self._format_angle_seconds(center_sec),
            'delta_mm': None,
            'delta_mm_str': '—',
        }

    @staticmethod
    def _expected_bearing_for_side(label: str) -> float:
        return 90.0 if 'Прав' in label else 270.0

    @staticmethod
    def _normalized_angle_diff(a_sec: float, b_sec: float) -> float:
        diff = a_sec - b_sec
        while diff > 648000.0:
            diff -= 1296000.0
        while diff < -648000.0:
            diff += 1296000.0
        return diff

    @staticmethod
    def _average_angles(a_sec: float, b_sec: float) -> float:
        a_rad = math.radians(a_sec / 3600.0)
        b_rad = math.radians(b_sec / 3600.0)
        x = math.cos(a_rad) + math.cos(b_rad)
        y = math.sin(a_rad) + math.sin(b_rad)
        if abs(x) < 1e-12 and abs(y) < 1e-12:
            return 0.0
        angle_deg = math.degrees(math.atan2(y, x))
        if angle_deg < 0:
            angle_deg += 360.0
        return angle_deg * 3600.0

    @classmethod
    def _format_angle_seconds(cls, angle_sec: Optional[float]) -> str:
        if angle_sec is None:
            return '—'
        return cls.degrees_to_dms_string((float(angle_sec) / 3600.0) % 360.0)

    @staticmethod
    def _deterministic_circle_difference_seconds(
        *,
        section_num: Optional[int],
        section_label: str,
        side_label: str,
        height: float,
        target_sec: float,
    ) -> float:
        signature = f"{section_num}|{section_label}|{side_label}|{height:.3f}|{target_sec:.3f}"
        checksum = sum((index + 1) * ord(char) for index, char in enumerate(signature))
        pattern = (-2.0, -1.0, 0.0, 1.0, 2.0)
        return pattern[checksum % len(pattern)]

    @staticmethod
    def offset_to_angle_seconds(offset: float, height: float) -> float:
        """Преобразует линейное смещение вдоль оси X в угловые секунды."""
        safe_height = max(abs(height), 1e-6)
        angle_rad = math.atan2(offset, safe_height)
        return math.degrees(angle_rad) * 3600.0

    @staticmethod
    def degrees_to_dms_string(degrees_value: float) -> str:
        deg = degrees_value % 360.0
        d = int(deg)
        minutes_float = (deg - d) * 60.0
        m = int(minutes_float)
        s = (minutes_float - m) * 60.0
        return f"{d:03d}° {m:02d}' {s:05.2f}\""

    @staticmethod
    def seconds_to_dms_string(seconds_value: float, include_sign: bool = True) -> str:
        """Преобразует секунды в строку формата D° M' S"."""
        if seconds_value is None:
            return '—'

        sign = ''
        if include_sign and seconds_value < 0:
            sign = '-'
        elif include_sign and seconds_value > 0:
            sign = '+'
        abs_seconds = abs(seconds_value)
        degrees = int(abs_seconds // 3600)
        minutes = int((abs_seconds % 3600) // 60)
        seconds = abs_seconds - degrees * 3600 - minutes * 60
        return f"{sign}{degrees}° {minutes:02d}' {seconds:05.2f}\""

    def _get_original_record(
        self,
        index: Optional[int],
        *,
        prefer_point_index: bool = False,
    ) -> Dict[str, Any]:
        """Возвращает копию строки исходных данных по DataFrame index или point_index."""
        if index is None or self.original_data is None or self.original_data.empty:
            return {}

        if prefer_point_index and 'point_index' in self.original_data.columns:
            try:
                numeric_point_index = pd.to_numeric(
                    self.original_data['point_index'],
                    errors='coerce',
                )
                matches = numeric_point_index.eq(int(index))
                if matches.any():
                    row = self.original_data.loc[matches].iloc[0]
                    return row.to_dict()
            except (TypeError, ValueError):
                pass

        try:
            row = self.original_data.loc[index]
        except Exception:
            return {}
        return row.to_dict()

    @staticmethod
    def _normalize_tower_part(value: Any, default: int = 1) -> int:
        """Безопасно приводит значение части башни к целому номеру."""
        if value is None:
            return default
        try:
            part_num = int(value)
            if part_num <= 0:
                return default
            return part_num
        except (TypeError, ValueError):
            return default
        
    def get_data(self) -> pd.DataFrame:
        """
        Получает данные из обеих таблиц (точки стояния + точки башни)
        
        Returns:
            DataFrame с текущими данными
        """
        if self.show_angular_mode:
            if self.original_data is None:
                return pd.DataFrame()
            return self.original_data.copy()

        def _safe_float(item: Optional[QTableWidgetItem], fallback: Any = 0.0) -> float:
            base = fallback if fallback is not None else 0.0
            if item is None:
                return float(base)
            text = item.text().strip().replace(',', '.')
            if not text:
                return float(base)
            try:
                return float(text)
            except ValueError:
                return float(base)

        def _safe_point_index(item: Optional[QTableWidgetItem], fallback: Any = None) -> Optional[int]:
            if item is None:
                try:
                    return int(fallback)
                except (TypeError, ValueError):
                    return None
            text = item.text().strip()
            if not text:
                try:
                    return int(fallback)
                except (TypeError, ValueError):
                    return None
            try:
                return int(float(text))
            except (ValueError, TypeError):
                try:
                    return int(fallback)
                except (TypeError, ValueError):
                    return None

        data_rows: List[Dict[str, Any]] = []
        
        # Читаем точки стояния
        for i in range(self.station_table.rowCount()):
            try:
                index_item = self.station_table.item(i, 0)
                global_idx = index_item.data(Qt.ItemDataRole.UserRole) if index_item else None
                base_record = self._get_original_record(global_idx, prefer_point_index=True)

                name_item = self.station_table.item(i, 1)
                name = name_item.text() if name_item else base_record.get('name', f'Точка стояния {i+1}')

                x = _safe_float(self.station_table.item(i, 2), base_record.get('x', 0.0))
                y = _safe_float(self.station_table.item(i, 3), base_record.get('y', 0.0))
                z = _safe_float(self.station_table.item(i, 4), base_record.get('z', 0.0))
                point_index = _safe_point_index(index_item, base_record.get('point_index'))

                record = base_record.copy()
                record.update({
                    'x': x,
                    'y': y,
                    'z': z,
                    'name': name,
                    'belt': None,
                    'is_station': True,
                    'point_index': point_index,
                    'tower_part': None
                })
                record.setdefault('tower_part_memberships', None)
                record['is_part_boundary'] = False
                data_rows.append(record)
            except (ValueError, AttributeError) as e:
                print(f"Пропущена строка точки стояния {i}: {e}")
                continue
        
        # Читаем точки башни
        # Определяем, является ли башня составной
        is_composite_tower = False
        if self.original_data is not None and not self.original_data.empty:
            tower_data_check = self.original_data[self._build_working_tower_mask(self.original_data)]
            has_memberships = 'tower_part_memberships' in tower_data_check.columns and tower_data_check['tower_part_memberships'].notna().any()
            has_numeric_parts = 'tower_part' in tower_data_check.columns and tower_data_check['tower_part'].notna().any()
            is_composite_tower = has_memberships or has_numeric_parts
        
        for table in self._iter_tower_tables():
            if table is None or table.rowCount() == 0:
                continue
            part_hint_raw = table.property('tower_part')
            is_part_table = part_hint_raw is not None
            try:
                part_hint = int(part_hint_raw)
            except (TypeError, ValueError):
                part_hint = 1

            for i in range(table.rowCount()):
                try:
                    index_item = table.item(i, 0)
                    global_idx = index_item.data(Qt.ItemDataRole.UserRole) if index_item else None
                    base_record = self._get_original_record(global_idx, prefer_point_index=True)

                    name_item = table.item(i, 1)
                    name = name_item.text() if name_item else base_record.get('name', f'Точка {i+1}')

                    x = _safe_float(table.item(i, 2), base_record.get('x', 0.0))
                    y = _safe_float(table.item(i, 3), base_record.get('y', 0.0))
                    z = _safe_float(table.item(i, 4), base_record.get('z', 0.0))
                    belt_item = table.item(i, 5)
                    belt_text = belt_item.text().strip() if belt_item and belt_item.text() else ''
                    
                    # Для составных башен читаем part_belt, для обычных - belt
                    if belt_text:
                        try:
                            belt_value = int(float(belt_text))
                        except (ValueError, TypeError):
                            if is_composite_tower and is_part_table:
                                belt_value = base_record.get('part_belt')
                            else:
                                belt_value = base_record.get('belt')
                    else:
                        if is_composite_tower and is_part_table:
                            belt_value = base_record.get('part_belt')
                        else:
                            belt_value = base_record.get('belt')
                    
                    point_index = _safe_point_index(index_item, base_record.get('point_index'))

                    record = base_record.copy()
                    # Для составных башен обновляем part_belt, для обычных - belt
                    if is_composite_tower and is_part_table:
                        record.update({
                            'x': x,
                            'y': y,
                            'z': z,
                            'name': name,
                            'part_belt': belt_value,
                            'belt': belt_value,  # Также обновляем belt для сортировки
                            'is_station': False,
                            'point_index': point_index,
                        })
                    else:
                        record.update({
                            'x': x,
                            'y': y,
                            'z': z,
                            'name': name,
                            'belt': belt_value,
                            'is_station': False,
                            'point_index': point_index,
                        })
                    record['tower_part'] = self._normalize_tower_part(record.get('tower_part'), part_hint)
                    if 'tower_part_memberships' in record:
                        memberships = record.get('tower_part_memberships')
                        if memberships in (None, '', []):
                            record['tower_part_memberships'] = None
                    else:
                        record['tower_part_memberships'] = None
                    record['is_part_boundary'] = bool(base_record.get('is_part_boundary', False))
                    data_rows.append(record)
                except (ValueError, AttributeError) as e:
                    print(f"Пропущена строка точки башни {i}: {e}")
                    continue
        
        if not data_rows:
            if self.original_data is not None:
                return pd.DataFrame(columns=self.original_data.columns)
            return pd.DataFrame(columns=['x', 'y', 'z', 'name', 'belt', 'is_station', 'point_index'])

        result = pd.DataFrame(data_rows)
        if self.original_data is not None:
            for column in self.original_data.columns:
                if column not in result.columns:
                    result[column] = pd.NA
            result = result[self.original_data.columns]
        return result
    
    def _determine_next_point_index(self) -> int:
        """Определяет следующий свободный индекс точки."""
        candidate_indices = []
        if self.original_data is not None and not self.original_data.empty and 'point_index' in self.original_data.columns:
            series = pd.to_numeric(self.original_data['point_index'], errors='coerce')
            candidate_indices.extend(series.dropna().astype(int).tolist())
        for table in (self.station_table, self.tower_table):
            for i in range(table.rowCount()):
                item = table.item(i, 0)
                if item:
                    try:
                        candidate_indices.append(int(item.text()))
                    except (TypeError, ValueError):
                        continue
        return (max(candidate_indices) + 1) if candidate_indices else 1
    
    def add_row(self, table):
        """Добавляет новую строку в указанную таблицу"""
        if table == self.tower_table and self.show_angular_mode:
            QMessageBox.warning(
                self,
                'Режим только для просмотра',
                'Чтобы добавлять или редактировать точки, отключите режим угловых измерений.'
            )
            return
        previous_data = self._capture_original_data_snapshot()
        row = table.rowCount()
        table.insertRow(row)
        
        # Номер
        next_index = self._determine_next_point_index()
        item = QTableWidgetItem(str(next_index))
        item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        table.setItem(row, 0, item)
        
        # Название
        item = QTableWidgetItem(f'Точка {row + 1}')
        table.setItem(row, 1, item)
        
        # Пустые ячейки для координат
        max_col = 5 if table == self.tower_table else 4
        for col in range(2, max_col):
            item = QTableWidgetItem('0.0')
            table.setItem(row, col, item)
        
        # Пояс (только для таблицы башни)
        if table == self.tower_table:
            item = QTableWidgetItem('')
            table.setItem(row, 5, item)
        
        # Обновляем таблицы и внутренние данные
        new_data = self.get_data()
        self.set_data(new_data)
        description = 'Добавление точки башни' if table == self.tower_table else 'Добавление точки стояния'
        self._emit_data_mutation(previous_data, description)
        
        self.data_changed.emit()
    
    def delete_selected_rows(self, table):
        """Удаляет выбранные строки из указанной таблицы"""
        if table == self.tower_table and self.show_angular_mode:
            QMessageBox.warning(
                self,
                'Режим только для просмотра',
                'Удаление точек недоступно в режиме угловых измерений.'
            )
            return
        previous_data = self._capture_original_data_snapshot()
        selected_rows = set()
        for item in table.selectedItems():
            selected_rows.add(item.row())
        
        if not selected_rows:
            QMessageBox.warning(self, 'Предупреждение', 'Выберите строки для удаления')
            return
        
        # Удаляем строки в обратном порядке
        for row in sorted(selected_rows, reverse=True):
            table.removeRow(row)

        # Обновляем таблицы и внутренние данные
        new_data = self.get_data()
        self.set_data(new_data)
        row_count = len(selected_rows)
        if table == self.tower_table:
            description = f'Удаление точек башни ({row_count})'
        else:
            description = f'Удаление точек стояния ({row_count})'
        self._emit_data_mutation(previous_data, description)
        
        self.data_changed.emit()
    
    def on_station_item_changed(self, item):
        """Обработчик изменения ячейки в таблице точек стояния"""
        previous_data = self._capture_original_data_snapshot()
        self._invalidate_angular_verticality_cache()
        idx_item = self.station_table.item(item.row(), 0)
        global_idx = None
        if idx_item is not None:
            global_idx = idx_item.data(Qt.ItemDataRole.UserRole)

        if item.column() in [2, 3, 4]:  # Координаты
            try:
                value = float(item.text())
                
                # Расширенная валидация координат
                column_map = {2: 'x', 3: 'y', 4: 'z'}
                col_name = column_map.get(item.column())
                error_msg = None
                
                # Проверка на разумные значения
                if col_name == 'z' and value < 0:
                    error_msg = "Высота не может быть отрицательной"
                elif col_name == 'z' and value > 10000:
                    error_msg = f"Высота слишком большая ({value} м). Проверьте единицы измерения."
                elif col_name in ['x', 'y'] and abs(value) > 1e6:
                    error_msg = f"Координата слишком большая ({value} м). Проверьте единицы измерения."
                elif not np.isfinite(value):
                    error_msg = "Значение должно быть конечным числом"
                
                if error_msg:
                    item.setBackground(QColor(255, 200, 200))
                    item.setToolTip(f"Ошибка: {error_msg}")
                else:
                    item.setBackground(QColor(255, 255, 255))
                    item.setToolTip("")
                    
                    if global_idx is not None and self.original_data is not None:
                        if col_name in self.original_data.columns:
                            self.original_data.at[global_idx, col_name] = value
                            if global_idx in self._current_station_data.index:
                                self._current_station_data.at[global_idx, col_name] = value
            except ValueError:
                item.setBackground(QColor(255, 200, 200))
                item.setToolTip("Ошибка: Введите корректное число")
            except Exception as e:
                item.setBackground(QColor(255, 200, 200))
                item.setToolTip(f"Ошибка: {str(e)}")
        elif item.column() == 1 and global_idx is not None and self.original_data is not None:
            name_value = item.text()
            self.original_data.at[global_idx, 'name'] = name_value
            if global_idx in self._current_station_data.index:
                self._current_station_data.at[global_idx, 'name'] = name_value
            self._update_station_ids()
        
        self._emit_data_mutation(previous_data, 'Редактирование точки стояния')
        self.data_changed.emit()
    
    def on_tower_item_changed(self, item):
        """Обработчик изменения ячейки в таблице точек башни"""
        previous_data = self._capture_original_data_snapshot()
        self._invalidate_angular_verticality_cache()
        table = item.tableWidget() if hasattr(item, 'tableWidget') else None
        if table is None:
            table = self.tower_table
        idx_item = table.item(item.row(), 0)
        global_idx = None
        if idx_item is not None:
            global_idx = idx_item.data(Qt.ItemDataRole.UserRole)

        if item.column() in [2, 3, 4]:  # Координаты
            try:
                value = float(item.text())
                
                # Расширенная валидация координат
                column_map = {2: 'x', 3: 'y', 4: 'z'}
                col_name = column_map.get(item.column())
                error_msg = None
                
                # Проверка на разумные значения
                if col_name == 'z' and value < 0:
                    error_msg = "Высота не может быть отрицательной"
                elif col_name == 'z' and value > 10000:
                    error_msg = f"Высота слишком большая ({value} м). Проверьте единицы измерения."
                elif col_name in ['x', 'y'] and abs(value) > 1e6:
                    error_msg = f"Координата слишком большая ({value} м). Проверьте единицы измерения."
                elif not np.isfinite(value):
                    error_msg = "Значение должно быть конечным числом"
                
                if error_msg:
                    item.setBackground(QColor(255, 200, 200))
                    item.setToolTip(f"Ошибка: {error_msg}")
                else:
                    item.setBackground(QColor(255, 255, 255))
                    item.setToolTip("")
                    
                    if global_idx is not None and self.original_data is not None:
                        if col_name in self.original_data.columns:
                            self.original_data.at[global_idx, col_name] = value
            except ValueError:
                item.setBackground(QColor(255, 200, 200))
                item.setToolTip("Ошибка: Введите корректное число")
            except Exception as e:
                item.setBackground(QColor(255, 200, 200))
                item.setToolTip(f"Ошибка: {str(e)}")
        elif item.column() == 5:  # Пояс
            text = item.text().strip()
            # Сохраняем point_index измененной точки для восстановления выделения после перезаполнения
            saved_point_index = None
            if idx_item is not None:
                saved_point_index = idx_item.data(Qt.ItemDataRole.UserRole)
            
            # Определяем, является ли это составная башня (используем тот же способ, что и при заполнении таблицы)
            is_composite = False
            if self.original_data is not None and not self.original_data.empty:
                tower_data = self.original_data[self._build_working_tower_mask(self.original_data)]
                has_memberships = 'tower_part_memberships' in tower_data.columns and tower_data['tower_part_memberships'].notna().any()
                has_numeric_parts = 'tower_part' in tower_data.columns and tower_data['tower_part'].notna().any()
                is_composite = has_memberships or has_numeric_parts
            
            belt_value_to_set = None
            # Временно отключаем сигналы itemChanged, чтобы избежать рекурсивных вызовов при обновлении
            table.itemChanged.disconnect(self.on_tower_item_changed)
            try:
                if text:
                    try:
                        belt_value_to_set = int(float(text))
                        # Обновляем данные в original_data
                        if global_idx is not None and self.original_data is not None:
                            # Находим запись по point_index, если global_idx является point_index
                            # или используем global_idx напрямую, если это индекс DataFrame
                            update_idx = None
                            if saved_point_index is not None and 'point_index' in self.original_data.columns:
                                # Пытаемся найти по point_index
                                mask = self.original_data['point_index'] == saved_point_index
                                if mask.any():
                                    update_idx = self.original_data[mask].index[0]
                                    logger.debug(f"Найден индекс DataFrame {update_idx} по point_index {saved_point_index}")
                            
                            if update_idx is None:
                                # Используем global_idx напрямую
                                if global_idx in self.original_data.index:
                                    update_idx = global_idx
                            
                            if update_idx is not None:
                                row_data = self.original_data.loc[update_idx]
                                
                                # Для составных башен обновляем part_belt, для обычных - belt
                                if is_composite:
                                    # Для составной башни обновляем part_belt
                                    if 'part_belt' in self.original_data.columns:
                                        old_part_belt = row_data.get('part_belt')
                                        self.original_data.at[update_idx, 'part_belt'] = belt_value_to_set
                                        logger.info(f"Обновлен part_belt для точки: old={old_part_belt}, new={belt_value_to_set}, DataFrame_idx={update_idx}, point_index={saved_point_index}")
                                    # Также обновляем belt, чтобы сортировка работала корректно
                                    if 'belt' in self.original_data.columns:
                                        old_belt = row_data.get('belt')
                                        self.original_data.at[update_idx, 'belt'] = belt_value_to_set
                                        logger.info(f"Обновлен belt для точки: old={old_belt}, new={belt_value_to_set}, DataFrame_idx={update_idx}, point_index={saved_point_index}")
                                else:
                                    # Для обычной башни обновляем belt
                                    if 'belt' in self.original_data.columns:
                                        old_belt = row_data.get('belt')
                                        self.original_data.at[update_idx, 'belt'] = belt_value_to_set
                                        logger.info(f"Обновлен пояс для точки: old={old_belt}, new={belt_value_to_set}, DataFrame_idx={update_idx}, point_index={saved_point_index}")
                            else:
                                logger.warning(f"Не удалось найти индекс для обновления пояса: global_idx={global_idx}, point_index={saved_point_index}")
                        
                        # Обновляем отображение в таблице с правильным форматом
                        item.setText(str(belt_value_to_set))
                        item.setBackground(QColor(255, 255, 255))
                        item.setToolTip("")
                    except ValueError:
                        item.setBackground(QColor(255, 200, 200))
                        item.setToolTip("Ошибка: Введите корректное число")
                else:
                    # Обновляем данные
                    if global_idx is not None and self.original_data is not None:
                        # Находим запись по point_index, если global_idx является point_index
                        update_idx = None
                        if saved_point_index is not None and 'point_index' in self.original_data.columns:
                            mask = self.original_data['point_index'] == saved_point_index
                            if mask.any():
                                update_idx = self.original_data[mask].index[0]
                        
                        if update_idx is None:
                            if global_idx in self.original_data.index:
                                update_idx = global_idx
                        
                        if update_idx is not None:
                            if is_composite:
                                # Для составной башни очищаем part_belt
                                if 'part_belt' in self.original_data.columns:
                                    old_part_belt = self.original_data.at[update_idx, 'part_belt']
                                    self.original_data.at[update_idx, 'part_belt'] = np.nan
                                    logger.debug(f"Очищен part_belt для точки: old={old_part_belt}, DataFrame_idx={update_idx}, point_index={saved_point_index}")
                                if 'belt' in self.original_data.columns:
                                    self.original_data.at[update_idx, 'belt'] = np.nan
                            else:
                                # Для обычной башни очищаем belt
                                if 'belt' in self.original_data.columns:
                                    old_belt = self.original_data.at[update_idx, 'belt']
                                    self.original_data.at[update_idx, 'belt'] = np.nan
                                    logger.debug(f"Очищен пояс для точки: old={old_belt}, DataFrame_idx={update_idx}, point_index={saved_point_index}")
                    
                    # Обновляем отображение в таблице
                    item.setText('')
                    item.setBackground(QColor(255, 255, 255))
                    item.setToolTip("")
            finally:
                # Включаем сигналы обратно
                table.itemChanged.connect(self.on_tower_item_changed)

            # Перезаполняем таблицу для применения сортировки по поясам
            # Отключаем сигналы на всех таблицах башни во время перезаполнения
            for tower_table in self._iter_tower_tables():
                try:
                    tower_table.itemChanged.disconnect(self.on_tower_item_changed)
                except TypeError:
                    # Сигнал уже отключен, игнорируем
                    pass
            
            try:
                # Убеждаемся, что данные в original_data актуальны перед перезаполнением
                # Проверяем, что обновление действительно применено
                if belt_value_to_set is not None and saved_point_index is not None:
                    if 'point_index' in self.original_data.columns:
                        mask = self.original_data['point_index'] == saved_point_index
                        if mask.any():
                            updated_row = self.original_data[mask].iloc[0]
                            # Проверяем соответствующее поле в зависимости от типа башни
                            if is_composite and 'part_belt' in self.original_data.columns:
                                actual_belt = updated_row.get('part_belt')
                                field_name = 'part_belt'
                            else:
                                actual_belt = updated_row.get('belt')
                                field_name = 'belt'
                            
                            if actual_belt != belt_value_to_set:
                                logger.warning(
                                    f"Обнаружено несоответствие пояса после обновления: "
                                    f"ожидалось {belt_value_to_set}, получено {actual_belt} для point_index={saved_point_index}. "
                                    f"Повторно обновляю данные (поле {field_name})."
                                )
                                self.original_data.loc[mask, field_name] = belt_value_to_set
                                # Для составных башен также обновляем belt
                                if is_composite and 'belt' in self.original_data.columns:
                                    self.original_data.loc[mask, 'belt'] = belt_value_to_set
                
                # ВАЖНО: Перед перезаполнением таблицы проверяем, что данные действительно обновлены
                # и принудительно обновляем их еще раз, чтобы гарантировать актуальность
                if belt_value_to_set is not None and saved_point_index is not None:
                    if 'point_index' in self.original_data.columns:
                        mask = self.original_data['point_index'] == saved_point_index
                        if mask.any():
                            # Принудительно обновляем данные перед перезаполнением
                            if is_composite and 'part_belt' in self.original_data.columns:
                                self.original_data.loc[mask, 'part_belt'] = belt_value_to_set
                                if 'belt' in self.original_data.columns:
                                    self.original_data.loc[mask, 'belt'] = belt_value_to_set
                                logger.info(f"ПРИНУДИТЕЛЬНО обновлен part_belt={belt_value_to_set} для point_index={saved_point_index}")
                            else:
                                if 'belt' in self.original_data.columns:
                                    self.original_data.loc[mask, 'belt'] = belt_value_to_set
                                logger.info(f"ПРИНУДИТЕЛЬНО обновлен belt={belt_value_to_set} для point_index={saved_point_index}")
                
                # Перестраиваем кэш перед перезаполнением, чтобы он содержал обновленные данные
                self._rebuild_cached_tower_data()
                # Перезаполняем таблицу, которая прочитает актуальные данные из self.original_data
                logger.info(f"Перезаполнение таблицы после изменения пояса. is_composite={is_composite}, point_index={saved_point_index}, new_belt_value={belt_value_to_set}")
                self.populate_tower_table()
                
                # После перезаполнения проверяем, что данные отображаются правильно
                if belt_value_to_set is not None and saved_point_index is not None and is_composite:
                    # Для составных башен проверяем part_belt
                    if 'point_index' in self.original_data.columns:
                        mask = self.original_data['point_index'] == saved_point_index
                        if mask.any():
                            row_after = self.original_data[mask].iloc[0]
                            actual_part_belt = row_after.get('part_belt')
                            logger.info(f"Проверка после перезаполнения: point_index={saved_point_index}, ожидаемый part_belt={belt_value_to_set}, фактический part_belt={actual_part_belt}")
            finally:
                # Включаем сигналы обратно после перезаполнения
                for tower_table in self._iter_tower_tables():
                    try:
                        tower_table.itemChanged.connect(self.on_tower_item_changed)
                    except TypeError:
                        # Сигнал уже подключен, игнорируем
                        pass
            
            # Восстанавливаем выделение измененной строки
            if saved_point_index is not None:
                # Определяем, какая таблица используется (обычная или составная)
                if self.tower_table.isVisible():
                    target_row = self._find_row_in_table(self.tower_table, saved_point_index)
                    if target_row >= 0:
                        self.tower_table.clearSelection()
                        self.tower_table.selectRow(target_row)
                        self.tower_table.scrollToItem(self.tower_table.item(target_row, 0))
                else:
                    # Для составных башен ищем в таблицах частей
                    for part_table in self.tower_part_tables.values():
                        target_row = self._find_row_in_table(part_table, saved_point_index)
                        if target_row >= 0:
                            part_table.clearSelection()
                            part_table.selectRow(target_row)
                            part_table.scrollToItem(part_table.item(target_row, 0))
                            # Переключаемся на нужную вкладку
                            tab_idx = self.tower_parts_tabs.indexOf(part_table)
                            if tab_idx >= 0:
                                self.tower_parts_tabs.setCurrentIndex(tab_idx)
                            break
            
            # После изменения пояса данные уже обновлены, но _rebuild_cached_tower_data уже вызван выше
            # Вызываем data_changed только один раз
            self._emit_data_mutation(previous_data, 'Редактирование пояса точки башни')
            self.data_changed.emit()
            return  # Выходим, чтобы не вызывать _rebuild_cached_tower_data и data_changed еще раз
        
        self._rebuild_cached_tower_data()
        
        self._emit_data_mutation(previous_data, 'Редактирование точки башни')
        self.data_changed.emit()
        
    def clear(self):
        """Очищает все таблицы"""
        self.station_table.setRowCount(0)
        self.tower_table.setRowCount(0)
        self.sections_table.setRowCount(0)
        self.active_station_id = None
        if hasattr(self, 'set_active_station_btn'):
            self.set_active_station_btn.setEnabled(False)
        
    def _iter_tower_tables(self):
        yield self.tower_table
        for table in self.tower_part_tables.values():
            yield table

    def _set_user_role_point_index(self, item: QTableWidgetItem, point_index_value: Any, dataframe_idx: Any) -> None:
        """
        Унифицированный метод для сохранения point_index в UserRole элемента таблицы.
        
        Args:
            item: Элемент таблицы
            point_index_value: Значение point_index из данных (может быть NaN)
            dataframe_idx: Индекс DataFrame для fallback
        """
        if pd.notna(point_index_value):
            try:
                item.setData(Qt.ItemDataRole.UserRole, int(point_index_value))
            except (ValueError, TypeError):
                # Fallback на индекс DataFrame, если point_index невалиден
                try:
                    item.setData(Qt.ItemDataRole.UserRole, int(dataframe_idx))
                except Exception:
                    item.setData(Qt.ItemDataRole.UserRole, dataframe_idx)
        else:
            # Если point_index отсутствует, используем индекс DataFrame
            try:
                item.setData(Qt.ItemDataRole.UserRole, int(dataframe_idx))
            except Exception:
                item.setData(Qt.ItemDataRole.UserRole, dataframe_idx)
    
    def _normalize_to_point_index(self, idx: Any) -> Optional[int]:
        """
        Нормализовать любой тип индекса в point_index.
        
        Args:
            idx: Индекс любого типа (point_index, DataFrame index, position)
            
        Returns:
            point_index или None, если не удалось нормализовать
        """
        if self.original_data is None or self.original_data.empty:
            return None
        
        # КРИТИЧЕСКИ ВАЖНО: сначала проверяем, является ли idx уже point_index
        # Это самый надежный способ, так как point_index - это основной идентификатор
        if 'point_index' in self.original_data.columns:
            try:
                idx_int = int(idx)
                mask = self.original_data['point_index'] == idx_int
                if mask.any():
                    logger.debug(f"_normalize_to_point_index: idx={idx} является point_index, возвращаем {idx_int}")
                    return idx_int
            except (ValueError, TypeError):
                pass
        
        # Если передан индекс DataFrame, ищем point_index в записи
        try:
            if idx in self.original_data.index:
                record = self.original_data.loc[idx]
                if 'point_index' in self.original_data.columns:
                    point_index_value = record.get('point_index')
                    if pd.notna(point_index_value):
                        try:
                            return int(point_index_value)
                        except (ValueError, TypeError):
                            pass
        except (KeyError, TypeError):
            pass
        
        # Если передан как позиция (0-based)
        # КРИТИЧЕСКИ ВАЖНО: НЕ используем idx как позицию, если он может быть point_index!
        # point_index обычно >= 1, но может совпадать с позицией
        # Поэтому проверяем позицию ТОЛЬКО если idx не является point_index
        try:
            if isinstance(idx, int) and 0 <= idx < len(self.original_data):
                # Проверяем, не является ли idx point_index
                is_point_index = False
                if 'point_index' in self.original_data.columns:
                    is_point_index = (self.original_data['point_index'] == idx).any()
                
                # Если idx не является point_index, используем его как позицию
                if not is_point_index:
                    record = self.original_data.iloc[idx]
                    if 'point_index' in self.original_data.columns:
                        point_index_value = record.get('point_index')
                        if pd.notna(point_index_value):
                            try:
                                return int(point_index_value)
                            except (ValueError, TypeError):
                                pass
        except (IndexError, KeyError):
            pass
        
        return None
    
    def select_row(self, row: int):
        """
        Выделяет строку в соответствующей таблице
        
        Args:
            row: point_index точки или индекс DataFrame (если point_index недоступен)
        """
        if self.original_data is None or self.original_data.empty:
            return
        
        logger.debug(f"select_row: получен row={row}, тип={type(row)}")
        
        # КРИТИЧЕСКИ ВАЖНО: row уже является point_index (передается из on_3d_point_selected)
        # Сначала проверяем, является ли row point_index напрямую
        normalized_point_index = None
        record = None
        found_index = None
        
        if 'point_index' in self.original_data.columns:
            try:
                row_int = int(row)
                logger.debug(
                    f"select_row: Проверяем, является ли row={row_int} point_index. "
                    f"Доступные point_index: {list(self.original_data['point_index'].unique()[:10])}, "
                    f"типы: {[type(v).__name__ for v in self.original_data['point_index'].unique()[:5]]}"
                )
                # Проверяем, является ли row уже point_index
                # КРИТИЧЕСКИ ВАЖНО: приводим к одному типу для сравнения
                # point_index может быть int, float, или другим типом
                mask = self.original_data['point_index'].astype(str) == str(row_int)
                if not mask.any():
                    # Пробуем числовое сравнение
                    mask = pd.to_numeric(self.original_data['point_index'], errors='coerce') == row_int
                
                if mask.any():
                    normalized_point_index = row_int
                    matching = self.original_data[mask]
                    found_index = matching.index[0]
                    record = matching.iloc[0]
                    logger.info(
                        f"select_row: row={row} является point_index, найдено: name={record.get('name', 'N/A')}, "
                        f"DataFrame index={found_index}, point_index={record.get('point_index', 'N/A')}"
                    )
                else:
                    logger.warning(
                        f"select_row: row={row_int} НЕ является point_index в original_data. "
                        f"Проверяем другие варианты... "
                        f"Доступные point_index: {sorted([int(v) for v in self.original_data['point_index'].dropna().unique()[:10]])}"
                    )
            except (ValueError, TypeError) as e:
                logger.error(f"select_row: Ошибка при проверке row={row} как point_index: {e}", exc_info=True)
        else:
            logger.warning(
                f"select_row: Колонка 'point_index' отсутствует в original_data. "
                f"Колонки: {list(self.original_data.columns) if self.original_data is not None else 'None'}"
            )
        
        # Если не нашли, пробуем нормализовать через _normalize_to_point_index
        if normalized_point_index is None:
            normalized_point_index = self._normalize_to_point_index(row)
            logger.debug(f"select_row: normalized_point_index={normalized_point_index}")
            
            if normalized_point_index is not None:
                # Ищем по point_index
                try:
                    mask = self.original_data['point_index'] == normalized_point_index
                    matching = self.original_data[mask]
                    if not matching.empty:
                        found_index = matching.index[0]
                        record = matching.iloc[0]
                        logger.debug(f"select_row: Найдено по point_index {normalized_point_index} -> DataFrame index {found_index}, name={record.get('name', 'N/A')}")
                except (ValueError, TypeError, IndexError) as e:
                    logger.debug(f"select_row: Ошибка поиска по point_index {normalized_point_index}: {e}")
        
        # Fallback: поиск по индексу DataFrame
        # КРИТИЧЕСКИ ВАЖНО: если point_index отсутствует в original_data, НЕ используем fallback!
        # В этом случае row уже является point_index, и мы будем искать в таблице по UserRole
        if record is None:
            # Если point_index отсутствует в original_data, пропускаем fallback
            # row уже является point_index, и мы будем искать в таблице напрямую
            if 'point_index' not in self.original_data.columns:
                logger.info(
                    f"select_row: point_index отсутствует в original_data, пропускаем fallback поиск. "
                    f"Будем использовать row={row} напрямую для поиска в таблице по UserRole."
                )
            else:
                # Проверяем, не является ли row point_index перед использованием как индекс DataFrame
                is_likely_point_index = False
                try:
                    row_int = int(row)
                    # Если row находится в диапазоне возможных point_index, не используем его как индекс DataFrame
                    # point_index обычно начинается с 1 и может быть до количества точек
                    if 1 <= row_int <= len(self.original_data) * 2:  # Учитываем возможный разброс
                        # Проверяем, есть ли такой point_index в данных
                        if (self.original_data['point_index'] == row_int).any():
                            is_likely_point_index = True
                            logger.warning(
                                f"select_row: row={row} похож на point_index, но не найден в данных. "
                                f"Пропускаем fallback поиск по индексу DataFrame, чтобы избежать ошибки."
                            )
                except (ValueError, TypeError):
                    pass
                
                if not is_likely_point_index:
                    try:
                        if row in self.original_data.index:
                            found_index = row
                            record = self.original_data.loc[row]
                            logger.debug(f"select_row: Найдено по DataFrame index {row} (fallback), name={record.get('name', 'N/A')}")
                    except (KeyError, TypeError) as e:
                        logger.debug(f"select_row: Ошибка поиска по DataFrame index {row}: {e}")
        
        # КРИТИЧЕСКИ ВАЖНО: если point_index отсутствует в original_data, record может быть None
        # В этом случае мы все равно можем искать в таблице по UserRole, используя row напрямую
        if record is None:
            if 'point_index' not in self.original_data.columns:
                # point_index отсутствует, но row уже является point_index
                # Продолжаем работу, используя row для поиска в таблице
                logger.info(
                    f"select_row: record не найден, но point_index отсутствует в original_data. "
                    f"Используем row={row} напрямую для поиска в таблице по UserRole."
                )
            else:
                logger.error(
                    f"select_row: Не найдена точка с индексом {row} (point_index или DataFrame index). "
                    f"Доступные point_index: {list(self.original_data['point_index'].unique()[:10])}, "
                    f"доступные индексы DataFrame: {list(self.original_data.index[:10])}"
                )
                return
        
        # Определяем, что искать: point_index или индекс DataFrame
        # В UserRole хранится point_index, поэтому используем его для поиска
        # КРИТИЧЕСКИ ВАЖНО: если normalized_point_index is None, но record найден через fallback,
        # это может означать, что мы нашли неправильную запись
        # В этом случае нужно использовать point_index из найденной записи, если он есть
        if normalized_point_index is None and record is not None:
            # Пробуем получить point_index из найденной записи
            if 'point_index' in record:
                record_point_index = record.get('point_index')
                if pd.notna(record_point_index):
                    try:
                        normalized_point_index = int(record_point_index)
                        logger.info(
                            f"select_row: Используем point_index={normalized_point_index} из найденной записи "
                            f"(name={record.get('name', 'N/A')}) вместо row={row}"
                        )
                    except (ValueError, TypeError):
                        pass
        
        # Если все еще None, проверяем, не является ли row уже point_index
        if normalized_point_index is None and 'point_index' in self.original_data.columns:
            try:
                row_int = int(row)
                # Проверяем, является ли row уже point_index
                mask = self.original_data['point_index'] == row_int
                if mask.any():
                    normalized_point_index = row_int
                    logger.info(f"select_row: row={row} является point_index, используем его напрямую")
            except (ValueError, TypeError):
                pass
        
        # КРИТИЧЕСКИ ВАЖНО: если point_index отсутствует в original_data, но row является point_index,
        # используем row напрямую для поиска в таблице по UserRole
        # В таблице point_index хранится в UserRole, поэтому можем использовать row напрямую
        if normalized_point_index is None:
            if 'point_index' not in self.original_data.columns:
                # point_index отсутствует в original_data, но row уже является point_index
                # Используем row напрямую для поиска в таблице
                try:
                    row_int = int(row)
                    # Проверяем, что row находится в разумном диапазоне для point_index
                    if 1 <= row_int <= len(self.original_data) * 2:
                        normalized_point_index = row_int
                        search_idx = row_int
                        logger.info(
                            f"select_row: point_index отсутствует в original_data, но row={row} похож на point_index. "
                            f"Используем row напрямую для поиска в таблице по UserRole."
                        )
                    else:
                        # Если row не похож на point_index, используем found_index
                        if found_index is None:
                            logger.warning(f"select_row: found_index is None для row={row} и point_index недоступен")
                            return
                        search_idx = found_index
                except (ValueError, TypeError):
                    if found_index is None:
                        logger.warning(f"select_row: found_index is None для row={row} и point_index недоступен")
                        return
                    search_idx = found_index
            else:
                # Проверяем, что у найденной записи есть point_index
                record_point_index = record.get('point_index')
                if pd.isna(record_point_index):
                    if found_index is None:
                        logger.warning(f"select_row: found_index is None для row={row} и point_index отсутствует в записи")
                        return
                    search_idx = found_index
                else:
                    try:
                        search_idx = int(record_point_index)
                    except (ValueError, TypeError):
                        search_idx = found_index if found_index is not None else row
        else:
            search_idx = normalized_point_index
        
        # Логируем информацию о поиске
        if record is not None:
            logger.info(
                f"select_row: Ищем строку с search_idx={search_idx} (normalized_point_index={normalized_point_index}, row={row}), "
                f"найдена запись: name={record.get('name', 'N/A')}, point_index={record.get('point_index', 'N/A') if 'point_index' in record else 'N/A'}"
            )
        else:
            logger.info(
                f"select_row: Ищем строку с search_idx={search_idx} (normalized_point_index={normalized_point_index}, row={row}), "
                f"record=None (будем искать напрямую в таблице по UserRole)"
            )
        
        # Определяем, является ли точка станцией
        # КРИТИЧЕСКИ ВАЖНО: если record=None, пробуем найти запись в station_table по point_index
        # Если найдена в station_table, то это станция
        is_station = False
        if record is not None:
            is_station = bool(record.get('is_station', False))
        else:
            # Если record не найден, но point_index отсутствует в original_data,
            # пробуем найти запись в station_table по point_index
            # Если найдена в station_table, то это станция
            if search_idx is not None and self.station_table.rowCount() > 0:
                # Пробуем найти в station_table
                station_row = self._find_row_in_table(self.station_table, search_idx)
                if station_row >= 0:
                    is_station = True
                    logger.info(
                        f"select_row: record=None, но найдена запись в station_table (строка {station_row}) "
                        f"для search_idx={search_idx}, определяем как станцию"
                    )
                else:
                    logger.debug(
                        f"select_row: record=None, не найдена запись в station_table для search_idx={search_idx}, "
                        f"будем искать в tower_table"
                    )
            else:
                logger.debug(
                    f"select_row: record=None, search_idx={search_idx}, station_table пуста или search_idx=None, "
                    f"будем искать в tower_table"
                )
        
        if is_station:
            table = self.station_table
            tab_idx = 0
            target_row = self._find_row_in_table(table, search_idx)
            if target_row >= 0:
                table.clearSelection()
                table.selectRow(target_row)
                table.scrollToItem(table.item(target_row, 0))
                self.tabs.setCurrentIndex(tab_idx)
                logger.debug(f"select_row: Выделена строка {target_row} в station_table для search_idx={search_idx}")
            else:
                logger.warning(f"select_row: Не найдена строка в station_table для search_idx={search_idx}. Проверяю все строки...")
                # Отладочная информация
                for r in range(min(5, table.rowCount())):  # Проверяем первые 5 строк
                    it = table.item(r, 0)
                    if it:
                        stored = it.data(Qt.ItemDataRole.UserRole)
                        logger.debug(f"  Строка {r}: UserRole={stored}, тип={type(stored)}, ищем={search_idx}, тип={type(search_idx)}")
        else:
            # Если record не найден, используем значения по умолчанию
            if record is not None:
                memberships = self._decode_part_memberships(record.get('tower_part_memberships'))
                fallback_part = self._normalize_tower_part(record.get('tower_part', 1), default=1)
            else:
                # Если record не найден, используем значения по умолчанию
                memberships = None
                fallback_part = 1
                logger.debug(f"select_row: record=None, используем значения по умолчанию для tower_part")
            
            candidate_parts = memberships or [fallback_part]
            selected = False
            for part in candidate_parts:
                part_table = self.tower_part_tables.get(part)
                if part_table is None:
                    continue
                target_row = self._find_row_in_table(part_table, search_idx)
                if target_row >= 0:
                    part_table.clearSelection()
                    part_table.selectRow(target_row)
                    part_table.scrollToItem(part_table.item(target_row, 0))
                    tab_idx = self.tower_parts_tabs.indexOf(part_table)
                    if tab_idx >= 0:
                        self.tower_parts_tabs.setCurrentIndex(tab_idx)
                    self.tabs.setCurrentIndex(1)
                    selected = True
                    logger.debug(f"select_row: Выделена строка {target_row} в part_table {part} для search_idx={search_idx}")
                    break
            if not selected:
                target_row = self._find_row_in_table(self.tower_table, search_idx)
                if target_row >= 0:
                    self.tower_table.clearSelection()
                    self.tower_table.selectRow(target_row)
                    self.tower_table.scrollToItem(self.tower_table.item(target_row, 0))
                    self.tabs.setCurrentIndex(1)
                    logger.debug(f"select_row: Выделена строка {target_row} в tower_table для search_idx={search_idx}")
                else:
                    logger.warning(f"select_row: Не найдена строка в tower_table для search_idx={search_idx}. Проверяю все строки...")
                    # Отладочная информация
                    for r in range(min(5, self.tower_table.rowCount())):  # Проверяем первые 5 строк
                        it = self.tower_table.item(r, 0)
                        if it:
                            stored = it.data(Qt.ItemDataRole.UserRole)
                            logger.debug(f"  Строка {r}: UserRole={stored}, тип={type(stored)}, ищем={search_idx}, тип={type(search_idx)}")

    def _find_row_in_table(self, table: QTableWidget, global_idx: Any) -> int:
        """
        Найти строку в таблице по point_index или индексу DataFrame.
        
        Теперь в UserRole хранится point_index (если доступен), а не индекс DataFrame.
        Это решает проблему с изменяющимися индексами после reset_index.
        
        Args:
            table: Таблица для поиска
            global_idx: point_index или индекс DataFrame для поиска
            
        Returns:
            Номер строки или -1, если не найдено
        """
        if table is None:
            return -1
        
        if global_idx is None:
            logger.debug("_find_row_in_table: global_idx is None")
            return -1
        
        # КРИТИЧЕСКИ ВАЖНО: global_idx уже является point_index (передается из select_row)
        # НЕ нужно нормализовать его снова, так как это может привести к ошибкам
        # Используем global_idx напрямую как search_idx
        logger.debug(f"_find_row_in_table: получен global_idx={global_idx}, тип={type(global_idx)}")
        
        # Если point_index отсутствует в original_data, global_idx уже является point_index
        # Используем его напрямую для поиска в таблице по UserRole
        if self.original_data is None or self.original_data.empty:
            search_idx = global_idx
        elif 'point_index' not in self.original_data.columns:
            # point_index отсутствует в original_data, но global_idx уже является point_index
            # Используем его напрямую
            try:
                search_idx = int(global_idx)
                logger.debug(f"_find_row_in_table: point_index отсутствует в original_data, используем global_idx={search_idx} напрямую")
            except (ValueError, TypeError):
                search_idx = global_idx
        else:
            # Проверяем, является ли global_idx уже point_index
            try:
                idx_int = int(global_idx)
                # Проверяем, является ли global_idx point_index
                mask = self.original_data['point_index'] == idx_int
                if mask.any():
                    # global_idx уже является point_index, используем его напрямую
                    search_idx = idx_int
                    logger.debug(f"_find_row_in_table: global_idx={global_idx} является point_index, используем напрямую")
                else:
                    # Пробуем нормализовать
                    normalized_point_index = self._normalize_to_point_index(global_idx)
                    search_idx = normalized_point_index if normalized_point_index is not None else global_idx
                    logger.debug(f"_find_row_in_table: global_idx={global_idx} не является point_index, нормализован в {search_idx}")
            except (ValueError, TypeError):
                # Если не удалось преобразовать в int, пробуем нормализовать
                normalized_point_index = self._normalize_to_point_index(global_idx)
                search_idx = normalized_point_index if normalized_point_index is not None else global_idx
        
        # Пробуем найти по point_index (теперь это основной способ)
        try:
            search_idx_int = int(search_idx)
        except (ValueError, TypeError):
            search_idx_int = None
        
        logger.info(f"_find_row_in_table: Ищем search_idx={search_idx_int} в таблице с {table.rowCount()} строками")
        
        # Собираем все совпадения для диагностики
        matches = []
        for r in range(table.rowCount()):
            it = table.item(r, 0)
            if it is None:
                continue
            stored_idx = it.data(Qt.ItemDataRole.UserRole)
            
            # Сравниваем с учетом типов - важно для корректного сопоставления
            try:
                if stored_idx is None:
                    continue
                
                # Получаем имя точки для логирования
                name_item = table.item(r, 1)  # Колонка с именем
                point_name = name_item.text() if name_item is not None else f'Строка {r}'
                
                # Логируем первые несколько строк и все потенциальные совпадения
                is_potential_match = False
                if search_idx_int is not None:
                    if isinstance(stored_idx, (int, float)):
                        stored_int = int(stored_idx)
                        is_potential_match = (stored_int == search_idx_int) or (abs(stored_int - search_idx_int) <= 1)
                    else:
                        is_potential_match = (stored_idx == search_idx)
                
                if r < 5 or is_potential_match:
                    logger.info(
                        f"_find_row_in_table: Строка {r}: name={point_name}, stored_idx={stored_idx} (тип={type(stored_idx)}), "
                        f"search_idx_int={search_idx_int} (тип={type(search_idx_int)}), "
                        f"совпадение={stored_idx == search_idx_int if search_idx_int is not None and isinstance(stored_idx, (int, float)) else False}"
                    )
                
                if is_potential_match:
                    matches.append((r, point_name, stored_idx))
                
                # Приводим к одному типу для сравнения
                # Сначала пробуем числовое сравнение (для point_index)
                if isinstance(stored_idx, (int, float)) and search_idx_int is not None:
                    stored_int = int(stored_idx)
                    if stored_int == search_idx_int:
                        logger.info(
                            f"_find_row_in_table: ✓ Найдено ТОЧНОЕ совпадение в строке {r}: "
                            f"name={point_name}, stored_idx={stored_int} == search_idx={search_idx_int}"
                        )
                        return r
                    else:
                        # Логируем близкие совпадения для диагностики
                        diff = abs(stored_int - search_idx_int)
                        if diff <= 2:
                            logger.warning(
                                f"_find_row_in_table: ⚠ Близкое значение в строке {r}: "
                                f"name={point_name}, stored_idx={stored_int}, search_idx={search_idx_int}, разница={diff}"
                            )
                
                # Если не нашли точное совпадение, но есть близкие, логируем их
                if r == table.rowCount() - 1 and matches:
                    logger.warning(
                        f"_find_row_in_table: Не найдено точного совпадения для search_idx={search_idx_int}. "
                        f"Найдено {len(matches)} близких совпадений: {matches}"
                    )
                
                # Потом пробуем прямое сравнение (для строковых индексов или точного совпадения)
                if stored_idx == search_idx:
                    logger.info(f"_find_row_in_table: Найдено совпадение в строке {r}: {stored_idx} == {search_idx}")
                    return r
                
                # Пробуем сравнение через строковое представление (на случай разных типов)
                try:
                    if str(stored_idx) == str(search_idx):
                        logger.debug(f"_find_row_in_table: Найдено совпадение в строке {r} через строковое сравнение: '{stored_idx}' == '{search_idx}'")
                        return r
                except Exception as e:
                    logger.debug(f"_find_row_in_table: ошибка строкового сравнения строки {r}: {e}")
                    
            except (TypeError, ValueError) as e:
                logger.debug(f"_find_row_in_table: Ошибка сравнения в строке {r}: {e}")
                continue
        
        # Если не нашли точное совпадение, но есть близкие совпадения, логируем их
        if matches:
            logger.error(
                f"_find_row_in_table: ❌ Не найдено ТОЧНОГО совпадения для global_idx={global_idx} "
                f"(нормализован={search_idx}, тип={type(search_idx)}). "
                f"Найдено {len(matches)} близких совпадений: {matches}"
            )
        else:
            logger.warning(
                f"_find_row_in_table: Не найдено совпадение для global_idx={global_idx} "
                f"(нормализован={search_idx}, тип={type(search_idx)}). "
                f"Проверьте, что point_index правильно хранится в UserRole таблицы."
            )
        return -1

    def on_tower_selection_changed(self):
        """
        Выбор строки в таблице башни → эмитируем point_index.
        
        Теперь в UserRole хранится point_index, поэтому используем его напрямую.
        """
        if self.original_data is None or self.original_data.empty:
            return
        sender = self.sender()
        table = sender if isinstance(sender, QTableWidget) else self.tower_table
        local_row = table.currentRow()
        if local_row < 0:
            return
        it = table.item(local_row, 0)
        if it is None:
            return
        stored_value = it.data(Qt.ItemDataRole.UserRole)
        if stored_value is None:
            return
        
        try:
            # Теперь в UserRole хранится point_index (если доступен)
            stored_int = int(stored_value)
            
            # Проверяем, является ли это point_index (ищем в original_data по point_index)
            if 'point_index' in self.original_data.columns:
                mask = self.original_data['point_index'] == stored_int
                if mask.any():
                    # Это point_index - используем его напрямую
                    self.row_selected.emit(stored_int)
                    logger.debug(f"on_tower_selection_changed: Эмит point_index={stored_int}")
                    return
            
            # Fallback: возможно, это старый индекс DataFrame
            # Пробуем найти запись по индексу DataFrame и получить point_index
            if stored_int in self.original_data.index:
                record = self.original_data.loc[stored_int]
                if 'point_index' in self.original_data.columns:
                    point_index = record.get('point_index')
                    if pd.notna(point_index):
                        try:
                            self.row_selected.emit(int(point_index))
                            logger.debug(f"on_tower_selection_changed: Эмит point_index={int(point_index)} из DataFrame index={stored_int}")
                            return
                        except (ValueError, TypeError):
                            pass
                # Если point_index недоступен, используем индекс DataFrame
                self.row_selected.emit(stored_int)
                logger.debug(f"on_tower_selection_changed: Эмит DataFrame index={stored_int} (point_index недоступен)")
            else:
                # Не нашли в индексах - возможно, это point_index, который не совпадает с индексом DataFrame
                self.row_selected.emit(stored_int)
                logger.debug(f"on_tower_selection_changed: Эмит stored_value={stored_int} (не найден в индексах)")
        except (ValueError, TypeError) as e:
            logger.debug(f"on_tower_selection_changed: Ошибка обработки stored_value={stored_value}: {e}")
            pass

    def on_station_selection_changed(self):
        """
        Выбор строки в таблице стояния → эмитируем point_index.
        
        Теперь в UserRole хранится point_index, поэтому используем его напрямую.
        """
        if self.original_data is None or self.original_data.empty:
            return
        local_row = self.station_table.currentRow()
        if local_row < 0:
            return
        it = self.station_table.item(local_row, 0)
        if it is None:
            return
        stored_value = it.data(Qt.ItemDataRole.UserRole)
        if stored_value is None:
            return
        
        try:
            # Теперь в UserRole хранится point_index (если доступен)
            stored_int = int(stored_value)
            
            # Проверяем, является ли это point_index (ищем в original_data по point_index)
            if 'point_index' in self.original_data.columns:
                mask = self.original_data['point_index'] == stored_int
                if mask.any():
                    # Это point_index - используем его напрямую
                    self.set_active_station_btn.setEnabled(True)
                    self.row_selected.emit(stored_int)
                    logger.debug(f"on_station_selection_changed: Эмит point_index={stored_int}")
                    return
            
            # Fallback: возможно, это старый индекс DataFrame
            # Пробуем найти запись по индексу DataFrame и получить point_index
            if stored_int in self.original_data.index:
                record = self.original_data.loc[stored_int]
                if 'point_index' in self.original_data.columns:
                    point_index = record.get('point_index')
                    if pd.notna(point_index):
                        try:
                            self.set_active_station_btn.setEnabled(True)
                            self.row_selected.emit(int(point_index))
                            logger.debug(f"on_station_selection_changed: Эмит point_index={int(point_index)} из DataFrame index={stored_int}")
                            return
                        except (ValueError, TypeError):
                            pass
                # Если point_index недоступен, используем индекс DataFrame
                self.set_active_station_btn.setEnabled(True)
                self.row_selected.emit(stored_int)
                logger.debug(f"on_station_selection_changed: Эмит DataFrame index={stored_int} (point_index недоступен)")
            else:
                # Не нашли в индексах - возможно, это point_index, который не совпадает с индексом DataFrame
                self.set_active_station_btn.setEnabled(True)
                self.row_selected.emit(stored_int)
                logger.debug(f"on_station_selection_changed: Эмит stored_value={stored_int} (не найден в индексах)")
        except (ValueError, TypeError) as e:
            logger.debug(f"on_station_selection_changed: Ошибка обработки stored_value={stored_value}: {e}")
            pass

    def _compute_beta_seconds(self, kl_sec: float, kr_sec: float) -> float:
        """Вычисляет средний угол βизм по кругам теодолита."""
        kl_norm = self._normalize_angle_seconds(kl_sec)
        kr_norm_direct = self._normalize_angle_seconds(kr_sec - 648000.0)

        angles_deg = [kl_norm / 3600.0, kr_norm_direct / 3600.0]
        angles_rad = [math.radians(angle) for angle in angles_deg]
        x = sum(math.cos(angle) for angle in angles_rad)
        y = sum(math.sin(angle) for angle in angles_rad)
        if abs(x) < 1e-12 and abs(y) < 1e-12:
            beta_deg = angles_deg[0]
        else:
            beta_deg = math.degrees(math.atan2(y, x))
            if beta_deg < 0.0:
                beta_deg += 360.0
        return self._normalize_angle_seconds(beta_deg * 3600.0)

    @staticmethod
    def _normalize_angle_seconds(angle_sec: float) -> float:
        """Нормализует угол в секундах в диапазон [0, 1296000)."""
        while angle_sec >= 1296000.0:
            angle_sec -= 1296000.0
        while angle_sec < 0.0:
            angle_sec += 1296000.0
        return angle_sec
        
    def _get_selected_station_id(self) -> Optional[int]:
        local_row = self.station_table.currentRow()
        if local_row < 0:
            return None
        it = self.station_table.item(local_row, 0)
        if it is None:
            return None
        idx = it.data(Qt.ItemDataRole.UserRole)
        if idx is None:
            return None
        try:
            return int(idx)
        except Exception:
            return None

    def _update_station_selection(self, state_id: Optional[int]):
        if state_id is None:
            self.station_table.clearSelection()
            self.set_active_station_btn.setEnabled(False)
            return
        for row in range(self.station_table.rowCount()):
            it = self.station_table.item(row, 0)
            if it is None:
                continue
            try:
                if int(it.data(Qt.ItemDataRole.UserRole)) == state_id:
                    self.station_table.selectRow(row)
                    self.station_table.scrollToItem(it)
                    self.set_active_station_btn.setEnabled(True)
                    return
            except Exception:
                continue
        self.station_table.clearSelection()
        self.set_active_station_btn.setEnabled(False)

    def on_set_active_station_clicked(self):
        station_id = self._get_selected_station_id()
        if station_id is None:
            return
        self.set_active_station(station_id)
        self.active_station_changed.emit(station_id)

    def set_active_station(self, station_id: Optional[int]):
        if station_id is None or self.original_data is None:
            return
        if station_id not in self.original_data.index:
            return
        if not bool(self.original_data.at[station_id, 'is_station']):
            return
        if self.active_station_id != station_id:
            self.active_station_id = station_id
        if hasattr(self.editor_3d, 'set_active_station_index'):
            try:
                self.editor_3d.set_active_station_index(station_id)
            except Exception as e:
                logger.warning(f"Не удалось установить активную станцию в 3D-редакторе: {e}")
        current_selection = station_id
        self.populate_station_table()
        self._update_station_selection(state_id=current_selection)

    def get_angular_measurements(self) -> Dict[str, Any]:
        """Возвращает данные угловых измерений и агрегированную вертикальность."""
        try:
            payload = self.get_angular_verticality_payload()
        except Exception:
            logger.exception("Не удалось получить payload угловых измерений")
            return self._default_angular_verticality_payload()
        return payload
