"""
Виджет для отображения прямолинейности ствола башни
Расчет стрелы прогиба пояса ствола
"""

import json
import numpy as np
import pandas as pd
from typing import Optional
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTabWidget,
                             QTableWidget, QTableWidgetItem, QHeaderView, QSplitter, QScrollArea)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
import matplotlib.pyplot as plt
from matplotlib import ticker
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import logging

from core.normatives import get_straightness_tolerance
from core.point_utils import build_working_tower_mask
from core.straightness_calculations import calculate_belt_deflections as calculate_canonical_belt_deflections

logger = logging.getLogger(__name__)


class StraightnessWidget(QWidget):
    """Виджет для отображения графика прямолинейности ствола башни"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.data = None
        self.processed_data = None
        self.editor_3d = None  # Ссылка на 3D редактор
        self.init_ui()
    
    def _decode_part_memberships(self, value) -> list[int]:
        if value is None:
            return []
        if isinstance(value, float) and np.isnan(value):
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
    
    def _build_is_station_mask(self, series: pd.Series) -> pd.Series:
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

    def _row_has_part(self, row: pd.Series, part_num: int) -> bool:
        memberships = []
        if 'tower_part_memberships' in row and pd.notna(row.get('tower_part_memberships')):
            memberships = self._decode_part_memberships(row.get('tower_part_memberships'))
        if memberships:
            return part_num in memberships
        raw_value = row.get('tower_part', 1)
        if raw_value is None or (isinstance(raw_value, float) and np.isnan(raw_value)):
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
    
    def _collect_unique_parts(self, data: pd.DataFrame) -> list[int]:
        parts = set()
        if 'tower_part_memberships' in data.columns:
            for value in data['tower_part_memberships'].dropna():
                parts.update(self._decode_part_memberships(value))
        if not parts and 'tower_part' in data.columns:
            parts.update(data['tower_part'].dropna().unique())
        if 'is_part_boundary' in data.columns and data['is_part_boundary'].any():
            boundary_rows = data[data['is_part_boundary']]
            for _, row in boundary_rows.iterrows():
                raw_value = row.get('tower_part', 1)
                try:
                    base_part = int(raw_value)
                except (TypeError, ValueError):
                    base_part = 1
                if base_part <= 0:
                    base_part = 1
                parts.update({base_part, base_part + 1})
        return sorted(int(part) for part in parts if part is not None)

    def _get_working_data(self) -> pd.DataFrame:
        if self.data is None or self.data.empty:
            return pd.DataFrame()
        try:
            return self.data[build_working_tower_mask(self.data)].copy()
        except Exception:
            return self.data.copy()

    def _get_profile_lookup(self) -> dict[tuple[int, int], dict]:
        lookup: dict[tuple[int, int], dict] = {}
        if not isinstance(self.processed_data, dict):
            return lookup
        for profile in self.processed_data.get('straightness_profiles', []) or []:
            try:
                part_number = int(profile.get('part_number', 1))
                belt_number = int(profile.get('belt', 0))
            except (TypeError, ValueError):
                continue
            lookup[(part_number, belt_number)] = profile
        return lookup

    def _get_profile_deflections(
        self,
        belt_points: pd.DataFrame,
        belt_num: int,
        part_num: Optional[int],
    ) -> Optional[list[float]]:
        if belt_points is None or belt_points.empty:
            return []
        lookup = self._get_profile_lookup()
        profile = lookup.get((int(part_num or 1), int(belt_num)))
        if not profile:
            return None

        point_map = {}
        for point in profile.get('points', []):
            try:
                point_map[int(point.get('source_index'))] = float(point.get('deflection_mm', 0.0))
            except (TypeError, ValueError):
                continue

        belt_sorted = belt_points.sort_values('z')
        if belt_sorted.empty:
            return []
        if not point_map:
            return [0.0] * len(belt_sorted)

        return [float(point_map.get(int(idx), 0.0)) for idx in belt_sorted.index]
        
    def init_ui(self):
        """Инициализация интерфейса"""
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)
        self.setLayout(main_layout)
        
        # Splitter для графика и таблицы
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Левая часть - графики
        graph_widget = QWidget()
        graph_layout = QVBoxLayout()
        graph_layout.setContentsMargins(0, 0, 0, 0)
        graph_widget.setLayout(graph_layout)
        
        self.graph_tabs = QTabWidget()
        self.graph_tabs.setTabsClosable(False)
        self.graph_tabs.currentChanged.connect(self._on_graph_tab_changed)
        graph_layout.addWidget(self.graph_tabs)
        self.graph_tab_layouts = {}
        self._graph_entries_by_part = {}
        self._rendered_graph_parts = set()
        splitter.addWidget(graph_widget)
        
        # Правая часть - таблица
        table_widget = QWidget()
        table_layout = QVBoxLayout()
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_widget.setLayout(table_layout)
        
        # Заголовок таблицы
        table_title = QLabel('Стрелы прогиба по всем поясам')
        table_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        table_title.setStyleSheet('font-weight: bold; padding: 5px;')
        table_layout.addWidget(table_title)
        
        # Таблица - столбцы для каждого пояса
        self.deviation_table = QTableWidget()
        # Столбцы будут добавлены динамически при заполнении данных
        self.deviation_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.deviation_table.setAlternatingRowColors(True)
        table_layout.addWidget(self.deviation_table)

        # Вкладки для таблиц частей составной башни
        self.parts_table_tabs = QTabWidget()
        self.parts_table_tabs.hide()
        table_layout.addWidget(self.parts_table_tabs)
        self.part_tables = {}
        splitter.addWidget(table_widget)
        
        # Пропорции splitter - графики занимают больше места
        splitter.setStretchFactor(0, 70)
        splitter.setStretchFactor(1, 30)
        
        main_layout.addWidget(splitter, stretch=1)
        
        # Информационная метка
        self.info_label = QLabel('Загрузите данные для отображения графиков прямолинейности')
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.info_label.setStyleSheet('padding: 5px; color: #333; background-color: #f0f0f0; border-radius: 3px;')
        self.info_label.setWordWrap(True)
        self.info_label.setMaximumHeight(50)
        main_layout.addWidget(self.info_label)
        
    def set_data(self, data: pd.DataFrame, processed_data: dict = None):
        """Установить данные для построения графика
        
        Args:
            data: DataFrame с точками
            processed_data: Обработанные данные с расчетами (опционально)
        """
        # Защита от зацикливания: проверяем, не выполняется ли уже обновление
        if not hasattr(self, '_updating_plots'):
            self._updating_plots = False
        
        if self._updating_plots:
            logger.debug("Пропуск set_data - уже выполняется обновление")
            return
        
        # Проверяем, изменились ли данные (чтобы избежать лишних обновлений)
        data_changed = self.data is None or not self.data.equals(data) if data is not None else True
        
        # Безопасное сравнение processed_data (может быть dict, DataFrame или None)
        processed_changed = True
        if self.processed_data is None:
            processed_changed = processed_data is not None
        elif processed_data is None:
            processed_changed = True
        elif isinstance(self.processed_data, pd.DataFrame) and isinstance(processed_data, pd.DataFrame):
            processed_changed = not self.processed_data.equals(processed_data)
        elif isinstance(self.processed_data, dict) and isinstance(processed_data, dict):
            # Простое сравнение словарей (для глубокого сравнения нужна более сложная логика)
            processed_changed = self.processed_data is not processed_data
        else:
            processed_changed = self.processed_data is not processed_data
        
        if not data_changed and not processed_changed:
            logger.debug("Данные не изменились, пропуск обновления")
            return
        
        self.data = data
        self.processed_data = processed_data
        self.update_plots()
        
    def update_plots(self):
        """Обновить все графики прямолинейности по поясам на одной вкладке"""
        # Защита от зацикливания
        if not hasattr(self, '_updating_plots'):
            self._updating_plots = False
        
        if self._updating_plots:
            logger.debug("Пропуск update_plots - уже выполняется")
            return
        
        self._updating_plots = True
        try:
            if self.data is None or self.data.empty:
                self.info_label.setText('⚠ Нет данных для отображения')
                self._clear_graphs()
                self.deviation_table.setRowCount(0)
                return
            # Проверяем наличие поясов
            if 'belt' not in self.data.columns:
                self.info_label.setText('⚠ Данные должны содержать информацию о поясах')
                self._clear_graphs()
                self.deviation_table.setRowCount(0)
                return
            
            # Очищаем существующие графики и таблицу
            self._clear_graphs()
            self.deviation_table.setRowCount(0)
            
            # Исключаем точки standing
            data_without_station = self._get_working_data()
            
            # Проверяем, является ли башня составной
            has_memberships = 'tower_part_memberships' in data_without_station.columns and data_without_station['tower_part_memberships'].notna().any()
            has_numeric_parts = 'tower_part' in data_without_station.columns and data_without_station['tower_part'].notna().any()
            is_composite = has_memberships or has_numeric_parts
            
            if is_composite:
                unique_parts = self._collect_unique_parts(data_without_station)
                if not unique_parts and has_numeric_parts:
                    unique_parts = sorted(data_without_station['tower_part'].dropna().unique())
                if not unique_parts:
                    unique_parts = [1]
                logger.info(f"Обнаружена составная башня с частями: {unique_parts}")
            else:
                unique_parts = [1]
            
            # Получаем список поясов
            belts = sorted(data_without_station['belt'].dropna().unique())
            
            if len(belts) == 0:
                self.info_label.setText('⚠ Нет данных о поясах')
                return
            
            logger.info(f"Построение графиков прямолинейности для {len(belts)} поясов")
            
            # Собираем данные для таблиц (по частям) и подготавливаем графики
            belt_data_by_part: dict[int, dict[int, dict]] = {}
            graph_entries_by_part: dict[int, list] = {}
            
            # Группируем пояса по частям для составной башни
            if is_composite:
                # Добавляем заголовки для частей
                for part_num in unique_parts:
                    # Получаем пояса этой части
                    part_mask = data_without_station.apply(lambda row: self._row_has_part(row, part_num), axis=1)
                    part_data = data_without_station[part_mask].copy()
                    part_belts = sorted(part_data['belt'].dropna().unique())
                    
                    logger.info(f"Часть {int(part_num)}: {len(part_belts)} поясов")
                    
                    # Находим минимальную и максимальную высоту для этой части
                    part_min_height = part_data['z'].min()
                    part_max_height = part_data['z'].max()
                    part_height = part_max_height - part_min_height
                    
                    for belt_num in part_belts:
                        belt_points = part_data[part_data['belt'] == belt_num]
                        
                        if len(belt_points) < 2:
                            logger.warning(f"На поясе {belt_num} части {int(part_num)} недостаточно точек для расчета")
                            continue
                        
                        # Собираем данные для таблицы
                        belt_sorted = belt_points.sort_values('z')
                        deflections = self._calculate_belt_deflections(belt_sorted, part_num=int(part_num),
                                                                      part_min_height=part_min_height,
                                                                      part_max_height=part_max_height)
                        belt_length = part_height  # Используем высоту части, а не пояса
                        from core.normatives import get_straightness_tolerance
                        max_allowed_deflection_m = get_straightness_tolerance(belt_length)
                        max_allowed_deflection_mm = max_allowed_deflection_m * 1000  # в мм
                        
                        # Сохраняем данные по этому поясу
                        part_id = int(part_num)
                        part_tables = belt_data_by_part.setdefault(part_id, {})
                        graph_entries_by_part.setdefault(part_id, [])
                        part_tables[int(belt_num)] = {
                            'points': [],
                            'tolerance': max_allowed_deflection_mm,
                            'part_min_height': part_min_height,
                            'part_max_height': part_max_height,
                            'part_height': part_height
                        }
                        
                        for i, (idx, point) in enumerate(belt_sorted.iterrows()):
                            deflection = deflections[i] if i < len(deflections) else 0.0
                            # Используем абсолютную высоту (как в графике)
                            absolute_height = point['z']
                            part_tables[int(belt_num)]['points'].append({
                                'height': absolute_height,  # Абсолютная высота
                                'deflection': deflection
                            })
                        logger.debug(f"Часть {part_num}, Пояс {belt_num}: высота части={part_height:.2f}м, "
                                   f"точек={len(belt_sorted)}, первая высота={belt_sorted.iloc[0]['z']:.2f}м, "
                                   f"последняя={belt_sorted.iloc[-1]['z']:.2f}м")
                        # Сохраняем данные для графика с информацией о границах части
                        graph_entries_by_part[part_id].append(
                            (int(belt_num), belt_points.copy(), part_id, part_min_height, part_max_height)
                        )
            else:
                # Обычная башня - обрабатываем все пояса
                # Находим минимальную и максимальную высоту для всей башни
                tower_min_height = data_without_station['z'].min()
                tower_max_height = data_without_station['z'].max()
                tower_height = tower_max_height - tower_min_height
                
                for belt_num in belts:
                    belt_points = data_without_station[data_without_station['belt'] == belt_num]
                    
                    if len(belt_points) < 2:
                        logger.warning(f"На поясе {belt_num} недостаточно точек для расчета")
                        continue
                    
                    # Собираем данные для таблицы
                    belt_sorted = belt_points.sort_values('z')
                    deflections = self._calculate_belt_deflections(belt_sorted)
                    belt_length = tower_height  # Используем высоту всей башни
                    from core.normatives import get_straightness_tolerance
                    max_allowed_deflection_m = get_straightness_tolerance(belt_length)
                    max_allowed_deflection_mm = max_allowed_deflection_m * 1000  # в мм
                    
                    # Сохраняем данные по этому поясу
                    part_id = 1
                    part_tables = belt_data_by_part.setdefault(part_id, {})
                    graph_entries_by_part.setdefault(part_id, [])
                    part_tables[int(belt_num)] = {
                        'points': [],
                        'tolerance': max_allowed_deflection_mm,
                        'part_min_height': tower_min_height,
                        'part_max_height': tower_max_height,
                        'part_height': tower_height
                    }
                    
                    for i, (idx, point) in enumerate(belt_sorted.iterrows()):
                        deflection = deflections[i] if i < len(deflections) else 0.0
                        # Используем абсолютную высоту (как в графике)
                        absolute_height = point['z']
                        part_tables[int(belt_num)]['points'].append({
                            'height': absolute_height,  # Абсолютная высота
                            'deflection': deflection
                        })
                    # Сохраняем данные для графика с информацией о границах башни
                    graph_entries_by_part[part_id].append(
                        (int(belt_num), belt_points.copy(), part_id, tower_min_height, tower_max_height)
                    )
            
            # Заполняем таблицы (по одной для каждой части)
            is_multi_part = is_composite and len(belt_data_by_part) > 1
            self._fill_pivot_table(belt_data_by_part, is_multi_part)
            self._graph_entries_by_part = graph_entries_by_part
            self._rendered_graph_parts = set()
            
            graph_part_keys = sorted(belt_data_by_part.keys())
            if graph_part_keys:
                self._setup_graph_tabs(graph_part_keys, is_multi_part)
            else:
                self._show_graph_placeholder('Нет данных для графиков прямолинейности')
            
            parts_count = len(belt_data_by_part) if is_composite else 1
            parts_text = f" ({parts_count} частей)" if is_composite and parts_count > 1 else ""
            self.info_label.setText(f'✓ Графики построены для {len(belts)} поясов{parts_text}')
            logger.info(f"Графики прямолинейности построены для {len(belts)} поясов{parts_text}")
            
        except Exception as e:
            logger.error(f"Ошибка при построении графиков прямолинейности: {e}", exc_info=True)
            self.info_label.setText(f'❌ Ошибка: {str(e)}')
        finally:
            self._updating_plots = False
    
    def _clear_graphs(self):
        """Очистить все графики"""
        self.graph_tabs.clear()
        self.graph_tab_layouts = {}
        self._graph_entries_by_part = {}
        self._rendered_graph_parts = set()

    def _show_graph_placeholder(self, message: str):
        self.graph_tabs.clear()
        placeholder = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label = QLabel(message)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet('color: #666; font-size: 10pt;')
        layout.addWidget(label)
        placeholder.setLayout(layout)
        self.graph_tabs.addTab(placeholder, 'Графики')

    def _create_graph_tab_widget(self):
        tab_widget = QWidget()
        tab_layout = QVBoxLayout()
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.setSpacing(0)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content_widget = QWidget()
        belt_layout = QHBoxLayout()
        belt_layout.setContentsMargins(5, 5, 5, 5)
        belt_layout.setSpacing(10)
        content_widget.setLayout(belt_layout)
        scroll_area.setWidget(content_widget)

        tab_layout.addWidget(scroll_area)
        tab_widget.setLayout(tab_layout)
        return tab_widget, belt_layout

    def _setup_graph_tabs(self, part_keys: list[int], is_multi_part: bool):
        self.graph_tabs.blockSignals(True)
        self.graph_tabs.clear()
        self.graph_tab_layouts = {}
        self._rendered_graph_parts = set()

        tab_bar = self.graph_tabs.tabBar()
        for part_num in part_keys:
            title = f'Часть {part_num}' if is_multi_part else 'Все пояса'
            tab_widget, belt_layout = self._create_graph_tab_widget()
            index = self.graph_tabs.addTab(tab_widget, title)
            if tab_bar is not None:
                tab_bar.setTabData(index, part_num)
            self.graph_tab_layouts[part_num] = belt_layout

        self.graph_tabs.blockSignals(False)

        if part_keys:
            self.graph_tabs.setCurrentIndex(0)
            self._render_graphs_for_part(part_keys[0])

    def _render_graphs_for_part(self, part_num: Optional[int]):
        if part_num is None or part_num in self._rendered_graph_parts:
            return
        layout = self.graph_tab_layouts.get(part_num)
        if layout is None:
            return
        entries = self._graph_entries_by_part.get(part_num, [])

        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not entries:
            placeholder = QLabel('Недостаточно данных для построения графиков этой части')
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            placeholder.setStyleSheet('color: #666; font-size: 10pt;')
            layout.addWidget(placeholder)
            self._rendered_graph_parts.add(part_num)
            return

        for entry in entries:
            if len(entry) >= 5:
                belt_num, belt_points, part_label, part_min_height, part_max_height = entry
            else:
                # Обратная совместимость со старым форматом
                belt_num, belt_points, part_label = entry[:3]
                part_min_height = None
                part_max_height = None
            self._create_belt_graph(
                belt_num,
                belt_points,
                part_num=part_label,
                part_min_height=part_min_height,
                part_max_height=part_max_height,
                target_layout=layout
            )
        self._rendered_graph_parts.add(part_num)

    def _on_graph_tab_changed(self, index: int):
        tab_bar = self.graph_tabs.tabBar()
        if tab_bar is None:
            return
        part_num = tab_bar.tabData(index)
        if part_num is None:
            return
        self._render_graphs_for_part(part_num)
    
    def _create_belt_graph(
        self,
        belt_num: int,
        belt_points: pd.DataFrame,
        part_num: Optional[int] = None,
        part_min_height: Optional[float] = None,
        part_max_height: Optional[float] = None,
        target_layout: Optional[QHBoxLayout] = None
    ):
        """Создать график для одного пояса и добавить в контейнер
        
        Args:
            belt_num: Номер пояса
            belt_points: Точки пояса
            part_num: Номер части башни (опционально, для составной башни)
            target_layout: Layout вкладки, куда добавляется график
        """
        if target_layout is None:
            return
        # Создаем виджет для графика, который будет растягиваться по высоте
        graph_item_widget = QWidget()
        graph_item_layout = QVBoxLayout()
        graph_item_layout.setContentsMargins(5, 5, 5, 5)
        graph_item_layout.setSpacing(3)
        graph_item_widget.setLayout(graph_item_layout)
        
        # Заголовок графика (компактный)
        if part_num is not None:
            graph_title = QLabel(f'Пояс {int(belt_num)} [Ч{int(part_num)}]')
        else:
            graph_title = QLabel(f'Пояс {int(belt_num)}')
        graph_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        graph_title.setStyleSheet('font-weight: bold; padding: 2px; font-size: 9pt;')
        graph_title.setMaximumHeight(25)
        graph_item_layout.addWidget(graph_title)
        
        # Создаем Figure для matplotlib (высота увеличена для растяжения)
        figure = Figure(figsize=(4, 8), dpi=100)
        canvas = FigureCanvas(figure)
        graph_item_layout.addWidget(canvas, stretch=1)  # Растягиваем график
        
        # Построение графика
        self._plot_belt_straightness(figure, belt_num, belt_points, part_num=part_num, 
                                     part_min_height=part_min_height, part_max_height=part_max_height)
        
        # Добавляем в контейнер с растяжением по высоте
        target_layout.addWidget(graph_item_widget, stretch=1)
    
    def _populate_part_table(self, table: QTableWidget, belt_data_dict: dict, part_num: Optional[int] = None):
        """Заполнить таблицу с поворотом: строки = высоты, столбцы = пояса
        
        Args:
            belt_data_dict: Словарь {belt_num: {'points': [...], 'tolerance': float}}
        """
        try:
            part_suffix = f" (часть {part_num})" if part_num is not None else ""
            logger.info(f"Заполнение сводной таблицы для {len(belt_data_dict)} поясов{part_suffix}")
            table.setRowCount(0)
            table.setColumnCount(0)
            
            if not belt_data_dict:
                logger.warning("Нет данных для таблицы")
                return
            
            # Собираем все уникальные высоты и округляем до 0.1 м
            # Используем абсолютные высоты (как в графике)
            all_heights = set()
            for belt_data in belt_data_dict.values():
                for point in belt_data['points']:
                    height_rounded = round(point['height'], 1)  # Округление до 0.1 м
                    all_heights.add(height_rounded)
            
            sorted_heights = sorted(all_heights)
            sorted_belts = sorted(belt_data_dict.keys())
            
            # Находим максимальное допустимое значение среди всех поясов
            max_tolerance = max(belt_data['tolerance'] for belt_data in belt_data_dict.values())
            max_tolerance_rounded = round(max_tolerance, 1)  # Округление до 0.1 мм
            
            # Настраиваем таблицу: столбцы = пояса + допустимое значение (+ первый столбец для высоты)
            table.setColumnCount(len(sorted_belts) + 2)
            headers = ['Высота, м'] + [f'Пояс {belt}' for belt in sorted_belts] + ['Допустимое, мм']
            table.setHorizontalHeaderLabels(headers)
            table.setRowCount(len(sorted_heights))
            
            # Создаем словарь для быстрого доступа: (belt_num, height_rounded) -> deflection
            belt_height_deflection = {}
            for belt_num, belt_data in belt_data_dict.items():
                for point in belt_data['points']:
                    height_rounded = round(point['height'], 1)
                    deflection_rounded = round(point['deflection'], 1)  # Округление до 0.1 мм
                    belt_height_deflection[(belt_num, height_rounded)] = {
                        'deflection': deflection_rounded,
                        'tolerance': belt_data['tolerance']
                    }
            
            # Заполняем таблицу
            tolerance_col_idx = len(sorted_belts) + 1  # Индекс столбца с допустимым значением
            
            for row_idx, height in enumerate(sorted_heights):
                # Столбец с высотой
                height_item = QTableWidgetItem(f"{height:.1f}")
                height_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                table.setItem(row_idx, 0, height_item)
                
                # Столбцы с прогибами по поясам
                for col_idx, belt_num in enumerate(sorted_belts, start=1):
                    key = (belt_num, height)
                    if key in belt_height_deflection:
                        data = belt_height_deflection[key]
                        deflection = data['deflection']
                        tolerance = data['tolerance']
                        
                        # Создаем ячейку с прогибом
                        deflection_item = QTableWidgetItem(f"{deflection:+.1f}")
                        deflection_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                        
                        # Цветовая индикация (используем максимальное допустимое значение)
                        if abs(deflection) > max_tolerance_rounded:
                            deflection_item.setForeground(QColor(220, 50, 50))  # Красный - превышение
                        else:
                            deflection_item.setForeground(QColor(50, 150, 50))  # Зеленый - норма
                        
                        # Tooltip с допустимым значением для конкретного пояса
                        deflection_item.setToolTip(f"Допустимое для пояса {belt_num}: ±{tolerance:.1f} мм\nМаксимальное допустимое: ±{max_tolerance_rounded:.1f} мм\nИнструкция Минсвязи СССР, 1980: δ_допуск = L / 750")
                        
                        table.setItem(row_idx, col_idx, deflection_item)
                    else:
                        # Нет данных для этой высоты и пояса
                        empty_item = QTableWidgetItem('-')
                        empty_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                        table.setItem(row_idx, col_idx, empty_item)
                
                # Столбец с допустимым значением (максимальным)
                tolerance_item = QTableWidgetItem(f"±{max_tolerance_rounded:.1f}")
                tolerance_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                tolerance_item.setToolTip(f"Максимальное допустимое значение среди всех поясов\nИнструкция Минсвязи СССР, 1980: δ_допуск = L / 750")
                table.setItem(row_idx, tolerance_col_idx, tolerance_item)
            
            logger.info(f"Сводная таблица заполнена: {len(sorted_heights)} строк (высот), {len(sorted_belts)} столбцов (пояса){part_suffix}")
            
        except Exception as e:
            logger.error(f"Ошибка при заполнении сводной таблицы: {e}", exc_info=True)

    def _fill_pivot_table(self, belt_data_by_part: dict[int, dict], is_multi_part: bool):
        """Создает одну или несколько таблиц прогибов в зависимости от числа частей."""
        if not belt_data_by_part:
            self.deviation_table.setRowCount(0)
            self.deviation_table.setColumnCount(0)
            self.parts_table_tabs.hide()
            self.deviation_table.show()
            return
        
        if is_multi_part:
            self.deviation_table.hide()
            self.parts_table_tabs.show()
            while self.parts_table_tabs.count():
                widget = self.parts_table_tabs.widget(0)
                self.parts_table_tabs.removeTab(0)
                if widget is not None:
                    widget.deleteLater()
            self.part_tables = {}
            for part_num in sorted(belt_data_by_part.keys()):
                part_table = QTableWidget()
                part_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
                part_table.setAlternatingRowColors(True)
                self._populate_part_table(part_table, belt_data_by_part[part_num], part_num)
                self.parts_table_tabs.addTab(part_table, f'Часть {part_num}')
                self.part_tables[part_num] = part_table
        else:
            self.parts_table_tabs.hide()
            self.deviation_table.show()
            part_num = next(iter(belt_data_by_part.keys()))
            self._populate_part_table(self.deviation_table, belt_data_by_part[part_num], part_num if len(belt_data_by_part) > 1 else None)
    
    def _plot_belt_straightness(self, figure, belt_num: int, belt_points: pd.DataFrame, 
                                part_num: Optional[int] = None,
                                part_min_height: Optional[float] = None,
                                part_max_height: Optional[float] = None):
        """Построить график стрел прогиба для пояса
        
        Args:
            figure: Figure matplotlib
            belt_num: Номер пояса
            belt_points: Точки пояса
            part_num: Номер части башни (опционально, для нормализации высот)
            part_min_height: Минимальная высота части (для нормализации)
            part_max_height: Максимальная высота части (для нормализации)
        """
        try:
            figure.clear()
            ax = figure.add_subplot(1, 1, 1)
            rendered = self._render_straightness_plot(ax, belt_num, belt_points, part_num=part_num,
                                                     part_min_height=part_min_height, part_max_height=part_max_height)
            if rendered:
                figure.tight_layout(rect=[0.12, 0.12, 0.97, 0.95], pad=2.0, h_pad=2.5, w_pad=3.0)
        except Exception as e:
            logger.error(f"Ошибка при построении графика для пояса {belt_num}: {e}", exc_info=True)
    
    def _render_straightness_plot(self, ax, belt_num: int, belt_points: pd.DataFrame, 
                                  part_num: Optional[int] = None,
                                  part_min_height: Optional[float] = None,
                                  part_max_height: Optional[float] = None) -> bool:
        """Нарисовать график прямолинейности в переданных осях.
        
        Args:
            ax: Оси matplotlib для отрисовки
            belt_num: Номер пояса
            belt_points: Точки пояса
            part_num: Номер части башни (опционально, для расчета допуска)
            part_min_height: Минимальная высота части (для расчета допуска, если None - вычисляется из пояса)
            part_max_height: Максимальная высота части (для расчета допуска, если None - вычисляется из пояса)
        """
        belt_sorted = belt_points.sort_values('z')
        absolute_heights = belt_sorted['z'].values

        if len(absolute_heights) < 2:
            logger.warning("Недостаточно точек на поясе %s для построения графика", belt_num)
            ax.axis('off')
            ax.text(0.5, 0.5, 'Недостаточно данных', transform=ax.transAxes,
                    ha='center', va='center', fontsize=9, color='gray')
            return False

        # Определяем границы части для расчета допуска
        # Используем границы части, если они переданы, иначе - границы пояса
        if part_min_height is not None and part_max_height is not None:
            min_height = part_min_height
            max_height = part_max_height
            logger.debug(f"График пояса {belt_num}, часть {part_num}: используем границы части "
                        f"({min_height:.2f}м - {max_height:.2f}м)")
        else:
            min_height = absolute_heights.min()
            max_height = absolute_heights.max()
            logger.debug(f"График пояса {belt_num}: используем границы пояса "
                        f"({min_height:.2f}м - {max_height:.2f}м)")
        part_height = max_height - min_height
        logger.debug(f"График пояса {belt_num}: высота части={part_height:.2f}м, "
                    f"абсолютные высоты от {absolute_heights.min():.2f}м до {absolute_heights.max():.2f}м")

        deflections = self._calculate_belt_deflections(belt_sorted, part_num=part_num,
                                                       part_min_height=part_min_height,
                                                       part_max_height=part_max_height)
        belt_length = part_height  # Используем высоту части/башни для расчета допуска
        from core.normatives import get_straightness_tolerance
        max_allowed_deflection_m = get_straightness_tolerance(belt_length)
        max_allowed_deflection_mm = max_allowed_deflection_m * 1000

        ax.set_xlabel('Стрела прогиба, мм', fontsize=10)
        ax.set_ylabel('Высота, м', fontsize=10)
        ax.set_title(f'Пояс {int(belt_num)}', fontsize=10, fontweight='bold')
        ax.tick_params(axis='both', labelsize=9)
        ax.xaxis.set_major_locator(ticker.MaxNLocator(6))
        ax.yaxis.set_major_locator(ticker.MaxNLocator(integer=True, nbins=8))

        max_deflection_abs = max(abs(d) for d in deflections) if deflections else 10
        x_min = -max(max_deflection_abs * 1.2, max_allowed_deflection_mm * 1.5)
        x_max = max(max_deflection_abs * 1.2, max_allowed_deflection_mm * 1.5)
        ax.set_xlim(x_min, x_max)

        # Используем абсолютные высоты для графика (как в таблице прямолинейности)
        height_range = absolute_heights.max() - absolute_heights.min()
        y_min = absolute_heights.min() - height_range * 0.05
        y_max = absolute_heights.max() + height_range * 0.05
        ax.set_ylim(y_min, y_max)

        ax.axvline(x=0, color='black', linewidth=1.0, linestyle='-', zorder=1)
        ax.axvline(x=-max_allowed_deflection_mm, color='gray', linewidth=1.5, linestyle='--',
                   zorder=2, alpha=0.7, label=f'Допуск ±{max_allowed_deflection_mm:.1f} мм')
        ax.axvline(x=max_allowed_deflection_mm, color='gray', linewidth=1.5, linestyle='--',
                   zorder=2, alpha=0.7)

        ax.grid(True, axis='x', linestyle=':', linewidth=0.5, alpha=0.5, color='gray', zorder=0)
        ax.grid(True, axis='y', linestyle=':', linewidth=0.5, alpha=0.3, color='gray', zorder=0)

        # Используем абсолютные высоты для графика (как в таблице прямолинейности)
        ax.plot(deflections, absolute_heights,
                color='red', linewidth=1.5, linestyle='-',
                marker='o', markersize=4, markerfacecolor='red',
                markeredgecolor='white', markeredgewidth=0.5,
                label='Фактический прогиб', zorder=5)

        ax.legend(loc='best', fontsize=8, framealpha=0.9, frameon=True)
        ax.spines['top'].set_linewidth(0.5)
        ax.spines['right'].set_linewidth(0.5)
        ax.spines['bottom'].set_linewidth(1.0)
        ax.spines['left'].set_linewidth(1.0)

        return True
    
    def _calculate_belt_deflections(self, belt_points: pd.DataFrame, part_num: Optional[int] = None,
                                   part_min_height: Optional[float] = None,
                                   part_max_height: Optional[float] = None):
        """Рассчитать стрелы прогиба для пояса
        
        Согласно нормативам (Инструкция Минсвязи СССР, 1980):
        - Базовая линия строится через нижнюю и верхнюю точки пояса **в пределах части**
        - Стрела прогиба - расстояние от каждой точки пояса до этой прямой
        - Допустимая стрела прогиба: δ_допуск = L / 750, где L - длина пояса (высота части)
        - Первая (нижняя) и последняя (верхняя) точка пояса в части всегда имеют отклонение 0,
          так как они являются опорными точками для построения базовой линии
        
        Для составной башни расчет выполняется только для точек этой части.
        Опорные точки определяются как точки на минимальной и максимальной высоте части.
        
        Args:
            belt_points: Точки пояса (уже отфильтрованные по части, если это составная башня)
            part_num: Номер части башни (опционально, для составной башни)
            part_min_height: Минимальная высота части (для определения опорной точки)
            part_max_height: Максимальная высота части (для определения опорной точки)
            
        Returns:
            List[float]: Список стрел прогиба (в мм) для каждой точки
        """
        # Сортируем по высоте
        belt_sorted = belt_points.sort_values('z').copy()
        
        if len(belt_sorted) < 2:
            return [0.0] * len(belt_sorted)
        belt_numbers = pd.to_numeric(belt_sorted.get('belt'), errors='coerce').dropna()
        if not belt_numbers.empty:
            profile_deflections = self._get_profile_deflections(
                belt_sorted,
                int(belt_numbers.iloc[0]),
                part_num,
            )
            if profile_deflections is not None:
                return profile_deflections
        return [float(value) for value in calculate_canonical_belt_deflections(belt_sorted)]
        
        # Для составной башни используем границы части для определения опорных точек
        # Если границы части переданы, используем их для поиска опорных точек
        if part_min_height is not None and part_max_height is not None:
            height_tolerance = 0.1
            # Находим точки на нижней и верхней границе части
            bottom_points = belt_sorted[np.abs(belt_sorted['z'] - part_min_height) <= height_tolerance]
            top_points = belt_sorted[np.abs(belt_sorted['z'] - part_max_height) <= height_tolerance]
            
            if len(bottom_points) > 0 and len(top_points) > 0:
                # Используем средние точки на границах как опорные
                first_point = {
                    'x': bottom_points['x'].mean(),
                    'y': bottom_points['y'].mean(),
                    'z': bottom_points['z'].mean()
                }
                last_point = {
                    'x': top_points['x'].mean(),
                    'y': top_points['y'].mean(),
                    'z': top_points['z'].mean()
                }
            else:
                # Fallback: используем первую и последнюю точку по высоте
                first_point = belt_sorted.iloc[0]
                last_point = belt_sorted.iloc[-1]
        else:
            # Обычная башня - используем первую и последнюю точку по высоте
            first_point = belt_sorted.iloc[0]
            last_point = belt_sorted.iloc[-1]
        
        # Координаты опорных точек
        if isinstance(first_point, pd.Series):
            p1 = np.array([first_point['x'], first_point['y'], first_point['z']])
        else:
            p1 = np.array([first_point['x'], first_point['y'], first_point['z']])
            
        if isinstance(last_point, pd.Series):
            p2 = np.array([last_point['x'], last_point['y'], last_point['z']])
        else:
            p2 = np.array([last_point['x'], last_point['y'], last_point['z']])
        
        # Направляющий вектор прямой через опорные точки
        line_direction = p2 - p1
        line_length = np.linalg.norm(line_direction)
        
        # Если точки на одной высоте или очень близко - возвращаем нули
        if abs(p1[2] - p2[2]) < 1e-6 or line_length < 1e-6:
            return [0.0] * len(belt_sorted)
        
        # Нормализуем направляющий вектор
        line_direction = line_direction / line_length
        
        # Рассчитываем отклонения для каждой точки
        deflections = []
        
        for idx, (point_idx, point) in enumerate(belt_sorted.iterrows()):
            point_3d = np.array([point['x'], point['y'], point['z']])
            
            # Проверяем, является ли точка опорной (на нижней или верхней границе части)
            is_bottom_support = False
            is_top_support = False
            
            if part_min_height is not None and part_max_height is not None:
                height_tolerance = 0.1
                is_bottom_support = np.abs(point['z'] - part_min_height) <= height_tolerance
                is_top_support = np.abs(point['z'] - part_max_height) <= height_tolerance
            else:
                # Для обычной башни первая и последняя точка - опорные
                is_bottom_support = (idx == 0)
                is_top_support = (idx == len(belt_sorted) - 1)
            
            # Опорные точки всегда имеют отклонение 0
            if is_bottom_support or is_top_support:
                deflections.append(0.0)
                continue
            
            # Вектор от опорной точки до текущей точки
            v = point_3d - p1
            
            # Проекция v на направление прямой
            proj = np.dot(v, line_direction) * line_direction
            
            # Перпендикулярная составляющая (отклонение от прямой)
            perp = v - proj
            
            # Расстояние от точки до прямой (стрела прогиба)
            deflection_m = np.linalg.norm(perp)
            
            # Определяем знак отклонения для визуализации
            # Используем проекцию на нормаль к прямой в горизонтальной плоскости
            # Для простоты используем знак отклонения по X
            sign = 1.0 if perp[0] >= 0 else -1.0
            
            deflection_mm = sign * deflection_m * 1000  # в мм с учетом знака
            
            deflections.append(deflection_mm)
        
        logger.debug(f"Расчет стрел прогиба для пояса (часть {part_num if part_num else 'вся'}): {len(belt_sorted)} точек, "
                     f"опорные точки ({p1[0]:.3f}, {p1[1]:.3f}, {p1[2]:.3f}) и "
                     f"({p2[0]:.3f}, {p2[1]:.3f}, {p2[2]:.3f})")
        
        return deflections
    
    def _calculate_belt_angle(self, belt_points: pd.DataFrame):
        """Рассчитать угол наклона пояса относительно вертикали
        
        Args:
            belt_points: Точки пояса
            
        Returns:
            float: Угол в радианах
        """
        # Находим первую и последнюю точки по высоте
        belt_sorted = belt_points.sort_values('z')
        
        if len(belt_sorted) < 2:
            return 0.0
        
        first_point = belt_sorted.iloc[0]
        last_point = belt_sorted.iloc[-1]
        
        # Вектор пояса
        belt_vec = np.array([
            last_point['x'] - first_point['x'],
            last_point['y'] - first_point['y'],
            last_point['z'] - first_point['z']
        ])
        
        # Вертикальный вектор [0, 0, 1]
        vertical_vec = np.array([0.0, 0.0, 1.0])
        
        # Угол между векторами
        cos_angle = np.dot(belt_vec, vertical_vec) / (np.linalg.norm(belt_vec) * np.linalg.norm(vertical_vec))
        cos_angle = np.clip(cos_angle, -1.0, 1.0)
        angle = np.arccos(cos_angle)
        
        # Угол отклонения от вертикали
        deviation_angle = np.pi / 2 - angle if angle < np.pi / 2 else angle - np.pi / 2
        
        return deviation_angle
    
    def _fill_belt_table(self, table, belt_num: int, belt_points: pd.DataFrame):
        """Заполнить таблицу стрел прогиба для пояса
        
        Args:
            table: QTableWidget
            belt_num: Номер пояса
            belt_points: Точки пояса
        """
        try:
            logger.info(f"Заполнение таблицы для пояса {belt_num}: {len(belt_points)} точек")
            table.setRowCount(0)  # Очищаем таблицу
            
            # Сортируем по высоте
            belt_sorted = belt_points.sort_values('z')
            deflections = self._calculate_belt_deflections(belt_sorted)
            
            if not deflections:
                logger.warning("Нет данных о прогибах для таблицы")
                return
            
            # Рассчитываем длину пояса для норматива (высота пояса)
            belt_length = belt_sorted['z'].max() - belt_sorted['z'].min()
            from core.normatives import get_straightness_tolerance
            max_allowed_deflection_m = get_straightness_tolerance(belt_length)
            max_allowed_deflection_mm = max_allowed_deflection_m * 1000  # в мм
            
            for i, (idx, point) in enumerate(belt_sorted.iterrows()):
                row = table.rowCount()
                table.insertRow(row)
                
                # Высота
                height_item = QTableWidgetItem(f"{point['z']:.2f}")
                height_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                table.setItem(row, 0, height_item)
                
                # Стрела прогиба
                deflection = deflections[i] if i < len(deflections) else 0.0
                deflection_item = QTableWidgetItem(f"{deflection:+.2f}")
                deflection_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                
                # Цветовая индикация
                if abs(deflection) > max_allowed_deflection_mm:
                    # Превышение норматива
                    deflection_item.setForeground(QColor(220, 50, 50))  # Красный
                else:
                    # В норме
                    deflection_item.setForeground(QColor(50, 150, 50))  # Зеленый
                
                table.setItem(row, 1, deflection_item)
                
                # Допустимое отклонение (норматив L/750)
                tolerance_item = QTableWidgetItem(f"{max_allowed_deflection_mm:.2f}")
                tolerance_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                tolerance_item.setToolTip(f"Инструкция Минсвязи СССР, 1980: δ_допуск = L / 750 = {max_allowed_deflection_mm:.2f} мм\nгде L = {belt_length:.3f} м - длина пояса (высота)")
                table.setItem(row, 2, tolerance_item)
                
                logger.debug(f"Строка {row}: H={point['z']:.2f}м, Def={deflection:+.2f}мм, "
                            f"Допуск={max_allowed_deflection_mm:.2f}мм")
            
            logger.info(f"Таблица заполнена {table.rowCount()} строками для пояса {belt_num}")
            
        except Exception as e:
            logger.error(f"Ошибка при заполнении таблицы для пояса {belt_num}: {e}", exc_info=True)
    
    def get_all_belts_data(self):
        """Получить данные стрел прогиба для всех поясов, сгруппированные по частям башни
        
        Returns:
            Dict[int, Dict]: Словарь с ключами - номерами частей, значениями - словарями:
            {
                part_num: {
                    'min_height': float,  # Минимальная высота части
                    'max_height': float,  # Максимальная высота части
                    'belts': Dict[int, List[Dict]]  # Данные по поясам (номер пояса -> список данных)
                }
            }
        """
        all_data_by_parts = {}
        
        if self.data is None or self.data.empty or 'belt' not in self.data.columns:
            return all_data_by_parts
        
        # Исключаем точки standing
        data_without_station = self._get_working_data()
        
        # Проверяем, является ли башня составной
        profiles = self.processed_data.get('straightness_profiles') if isinstance(self.processed_data, dict) else None
        if isinstance(profiles, list) and profiles:
            for profile in profiles:
                try:
                    part_id = int(profile.get('part_number', 1))
                    belt_id = int(profile.get('belt', 0))
                except (TypeError, ValueError):
                    continue
                part_entry = all_data_by_parts.setdefault(part_id, {
                    'min_height': float(profile.get('part_min_height', 0.0)),
                    'max_height': float(profile.get('part_max_height', 0.0)),
                    'belts': {},
                })
                part_entry['belts'][belt_id] = [
                    {
                        'height': float(point.get('z', 0.0)),
                        'deflection': float(point.get('deflection_mm', 0.0)),
                        'tolerance': float(profile.get('tolerance_mm', 0.0)),
                    }
                    for point in profile.get('points', [])
                ]
            if all_data_by_parts:
                return all_data_by_parts

        has_memberships = 'tower_part_memberships' in data_without_station.columns and data_without_station['tower_part_memberships'].notna().any()
        has_numeric_parts = 'tower_part' in data_without_station.columns and data_without_station['tower_part'].notna().any()
        is_composite = has_memberships or has_numeric_parts
        
        if is_composite:
            unique_parts = self._collect_unique_parts(data_without_station)
            if not unique_parts and has_numeric_parts:
                unique_parts = sorted(data_without_station['tower_part'].dropna().unique())
            if not unique_parts:
                unique_parts = [1]
        else:
            unique_parts = [1]
        
        from core.normatives import get_straightness_tolerance
        
        # Группируем пояса по частям для составной башни
        if is_composite:
            for part_num in unique_parts:
                # Получаем пояса этой части
                part_mask = data_without_station.apply(lambda row: self._row_has_part(row, part_num), axis=1)
                part_data = data_without_station[part_mask].copy()
                part_belts = sorted(part_data['belt'].dropna().unique())
                
                # Находим минимальную и максимальную высоту для этой части
                part_min_height = float(part_data['z'].min())
                part_max_height = float(part_data['z'].max())
                part_height = part_max_height - part_min_height
                
                # Рассчитываем допустимое значение для части
                max_allowed_deflection_m = get_straightness_tolerance(part_height)
                max_allowed_deflection_mm = max_allowed_deflection_m * 1000
                
                belts_data = {}
                for belt_num in part_belts:
                    belt_points = part_data[part_data['belt'] == belt_num]
                    
                    if len(belt_points) < 2:
                        continue
                    
                    belt_sorted = belt_points.sort_values('z')
                    deflections = self._calculate_belt_deflections(belt_sorted, part_num=int(part_num),
                                                                  part_min_height=part_min_height,
                                                                  part_max_height=part_max_height)
                    
                    belt_data = []
                    for i, (idx, point) in enumerate(belt_sorted.iterrows()):
                        belt_data.append({
                            'height': float(point['z']),  # Абсолютная высота
                            'deflection': float(deflections[i] if i < len(deflections) else 0),
                            'tolerance': max_allowed_deflection_mm
                        })
                    
                    belts_data[int(belt_num)] = belt_data
                
                if belts_data:  # Добавляем только если есть данные
                    part_id = int(part_num)
                    all_data_by_parts[part_id] = {
                        'min_height': part_min_height,
                        'max_height': part_max_height,
                        'belts': belts_data
                    }
        else:
            # Обычная башня - обрабатываем все пояса как одну часть
            belts = sorted(data_without_station['belt'].dropna().unique())
            tower_min_height = float(data_without_station['z'].min())
            tower_max_height = float(data_without_station['z'].max())
            tower_height = tower_max_height - tower_min_height
            
            max_allowed_deflection_m = get_straightness_tolerance(tower_height)
            max_allowed_deflection_mm = max_allowed_deflection_m * 1000
            
            belts_data = {}
            for belt_num in belts:
                belt_points = data_without_station[data_without_station['belt'] == belt_num]
                
                if len(belt_points) < 2:
                    continue
                
                belt_sorted = belt_points.sort_values('z')
                deflections = self._calculate_belt_deflections(belt_sorted)
                
                belt_data = []
                for i, (idx, point) in enumerate(belt_sorted.iterrows()):
                    belt_data.append({
                        'height': float(point['z']),
                        'deflection': float(deflections[i] if i < len(deflections) else 0),
                        'tolerance': max_allowed_deflection_mm
                    })
                
                belts_data[int(belt_num)] = belt_data
            
            if belts_data:
                all_data_by_parts[1] = {
                    'min_height': tower_min_height,
                    'max_height': tower_max_height,
                    'belts': belts_data
                }
        
        return all_data_by_parts
    
    def get_all_figures_for_pdf(self):
        """Получить все figure объекты для сохранения в PDF
        
        Returns:
            List[Tuple[int, Figure]]: Список кортежей (номер_пояса, figure)
        """
        figures = []
        
        working_data = self._get_working_data()
        if working_data.empty or 'belt' not in working_data.columns:
            return figures

        belts = sorted(working_data['belt'].dropna().unique())
        
        for belt_num in belts:
            belt_points = working_data[working_data['belt'] == belt_num]
            
            if len(belt_points) < 2:
                continue
            
            # Создаем figure для этого пояса
            figure = Figure(figsize=(8, 6), dpi=100)
            self._plot_belt_straightness(figure, belt_num, belt_points, part_num=None)
            figures.append((int(belt_num), figure))
        
        return figures
    
    def get_combined_figure_for_pdf(self):
        """Создать объединенный график всех поясов для PDF
        
        Returns:
            Figure: Matplotlib figure с субплотами для всех поясов
        """
        working_data = self._get_working_data()
        if working_data.empty or 'belt' not in working_data.columns:
            return None

        belts = sorted(working_data['belt'].dropna().unique())
        
        if len(belts) == 0:
            return None
        
        # Определяем размер сетки
        num_belts = len(belts)
        
        # Создаем сетку графиков: 2 колонки, столько строк, сколько нужно
        cols = 2
        rows = (num_belts + cols - 1) // cols  # Округляем вверх
        
        # Создаем figure с субплотами
        figure = Figure(figsize=(12, max(6, 4.5 * rows)), dpi=120)
        subplot_pos = 1

        for belt_num in belts:
            belt_points = working_data[working_data['belt'] == belt_num]
            if len(belt_points) < 2:
                continue

            ax = figure.add_subplot(rows, cols, subplot_pos)
            rendered = self._render_straightness_plot(ax, belt_num, belt_points, part_num=None)
            if not rendered:
                figure.delaxes(ax)
                continue

            subplot_pos += 1

        if subplot_pos == 1:
            return None

        figure.tight_layout(pad=2.0, h_pad=2.5, w_pad=2.0)
        return figure

    def get_grouped_figures_for_pdf(self, group_size: int = 2):
        """Получить фигуры с графиками, сгруппированными по несколько поясов."""
        working_data = self._get_working_data()
        if working_data.empty or 'belt' not in working_data.columns:
            return []

        belts = sorted(working_data['belt'].dropna().unique())
        if not belts:
            return []

        group_size = max(1, group_size)
        grouped_figures = []

        for start in range(0, len(belts), group_size):
            belt_group = belts[start:start + group_size]
            cols = len(belt_group)
            figure = Figure(figsize=(12 if cols > 1 else 8, 5.5), dpi=120)
            subplot_pos = 1
            plotted_belts: list[int] = []

            for belt_num in belt_group:
                belt_points = working_data[working_data['belt'] == belt_num]
                if len(belt_points) < 2:
                    continue

                ax = figure.add_subplot(1, cols, subplot_pos)
                rendered = self._render_straightness_plot(ax, belt_num, belt_points, part_num=None)
                if not rendered:
                    figure.delaxes(ax)
                    continue

                plotted_belts.append(int(belt_num))
                subplot_pos += 1

            if not plotted_belts:
                plt.close(figure)
                continue

            figure.tight_layout(pad=2.0, w_pad=2.0)
            grouped_figures.append((tuple(plotted_belts), figure))

        return grouped_figures
    
    def get_part_figures_for_pdf(self, part_num: int, group_size: int = 2):
        """Получить фигуры с графиками для конкретной части башни.
        
        Args:
            part_num: Номер части башни
            group_size: Количество поясов на одном графике
            
        Returns:
            List[Tuple[Tuple[int, ...], Figure]]: Список кортежей (группа_поясов, figure)
        """
        if not hasattr(self, '_graph_entries_by_part') or not self._graph_entries_by_part:
            return []
        
        entries = self._graph_entries_by_part.get(part_num, [])
        if not entries:
            return []
        
        # Получаем список поясов для этой части
        part_belts = sorted([entry[0] for entry in entries])
        if not part_belts:
            return []
        
        group_size = max(1, group_size)
        grouped_figures = []
        
        for start in range(0, len(part_belts), group_size):
            belt_group = part_belts[start:start + group_size]
            cols = len(belt_group)
            figure = Figure(figsize=(12 if cols > 1 else 8, 5.5), dpi=120)
            subplot_pos = 1
            plotted_belts: list[int] = []
            
            # Создаем словарь для быстрого поиска записей по номеру пояса
            belt_to_entry = {entry[0]: entry for entry in entries}
            
            for belt_num in belt_group:
                entry = belt_to_entry.get(belt_num)
                if not entry:
                    continue
                
                _, belt_points, part_id, part_min_height, part_max_height = entry
                
                if len(belt_points) < 2:
                    continue
                
                ax = figure.add_subplot(1, cols, subplot_pos)
                rendered = self._render_straightness_plot(
                    ax, belt_num, belt_points, 
                    part_num=part_id,
                    part_min_height=part_min_height,
                    part_max_height=part_max_height
                )
                if not rendered:
                    figure.delaxes(ax)
                    continue
                
                plotted_belts.append(int(belt_num))
                subplot_pos += 1
            
            if not plotted_belts:
                plt.close(figure)
                continue
            
            figure.tight_layout(pad=2.0, w_pad=2.0)
            grouped_figures.append((tuple(plotted_belts), figure))
        
        return grouped_figures

    
