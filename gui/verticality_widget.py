"""
Виджет для отображения вертикальности башни
Показывает график отклонений от вертикали по секциям
"""

import copy
import numpy as np
import pandas as pd
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QPushButton, QHBoxLayout, QLabel,
                             QTableWidget, QTableWidgetItem, QHeaderView, QSplitter)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.ticker import MaxNLocator
import logging
import json
from typing import List, Dict, Set, Optional
from core.services.verticality_sections import get_preferred_verticality_sections

logger = logging.getLogger(__name__)


class VerticalityWidget(QWidget):
    """Виджет для отображения графика вертикальности башни"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.data = None
        self.processed_data = None
        self.editor_3d = None  # Ссылка на 3D редактор для доступа к section_data
        self.data_table_widget = None  # Ссылка на таблицу данных для получения угловых измерений
        self._current_section_data: List[Dict] = []
        self.init_ui()
        
    def init_ui(self):
        """Инициализация интерфейса"""
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)
        self.setLayout(main_layout)
        
        # Splitter для графика и таблицы
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Левая часть - график
        graph_widget = QWidget()
        graph_layout = QVBoxLayout()
        graph_layout.setContentsMargins(0, 0, 0, 0)
        graph_widget.setLayout(graph_layout)
        
        # Создаем Figure для matplotlib (уменьшенная ширина, растянутая высота)
        self.figure = Figure(figsize=(3.5, 10), dpi=100)
        self.canvas = FigureCanvas(self.figure)
        graph_layout.addWidget(self.canvas)
        splitter.addWidget(graph_widget)
        
        # Правая часть - таблица
        table_widget = QWidget()
        table_layout = QVBoxLayout()
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_widget.setLayout(table_layout)
        
        # Заголовок таблицы
        table_title = QLabel('Отклонения по секциям')
        table_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        table_title.setStyleSheet('font-weight: bold; padding: 5px;')
        table_layout.addWidget(table_title)

        # Блок подгонки (делитель отклонений)
        controls_row = QHBoxLayout()
        controls_row.setContentsMargins(6, 0, 6, 4)
        controls_row.setSpacing(8)
        controls_row.addWidget(QLabel('k1'))
        from PyQt6.QtWidgets import QDoubleSpinBox
        self.adjust_spin = QDoubleSpinBox()
        self.adjust_spin.setRange(0.001, 1000.0)
        self.adjust_spin.setDecimals(3)
        self.adjust_spin.setSingleStep(0.001)
        self.adjust_spin.setValue(1.000)
        self.adjust_spin.setToolTip('Все отклонения будут делиться на это значение')
        self.adjust_spin.valueChanged.connect(self.update_plot)
        controls_row.addWidget(self.adjust_spin)
        controls_row.addStretch()
        table_layout.addLayout(controls_row)
        
        # Таблица
        self.deviation_table = QTableWidget()
        self.deviation_table.setColumnCount(7)
        self.deviation_table.setHorizontalHeaderLabels(['Секция', 'Высота, м', 'Часть', 'Отклонение X, мм', 'Отклонение Y, мм', 'Суммарное, мм', 'Допустимое, мм'])
        self.deviation_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.deviation_table.setAlternatingRowColors(True)
        table_layout.addWidget(self.deviation_table)
        splitter.addWidget(table_widget)
        
        # Пропорции splitter (графики занимают большую часть)
        splitter.setStretchFactor(0, 30)
        splitter.setStretchFactor(1, 70)
        
        main_layout.addWidget(splitter, stretch=1)  # Графики растягиваются
        
        # Информационная метка с результатами (компактная)
        self.info_label = QLabel('Загрузите данные для отображения графика')
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.info_label.setStyleSheet('padding: 5px; color: #333; background-color: #f0f0f0; border-radius: 3px;')
        self.info_label.setWordWrap(True)
        self.info_label.setMaximumHeight(50)  # Ограничиваем высоту
        main_layout.addWidget(self.info_label)
        
    def set_data(self, data: pd.DataFrame, processed_data: dict = None):
        """Установить данные для построения графика
        
        Args:
            data: DataFrame с точками (должен содержать x, y, z, belt)
            processed_data: Обработанные данные с расчетами (опционально)
        """
        self.data = data
        self.processed_data = processed_data
        self.update_plot()
        
    def update_plot(self):
        """Обновить график вертикальности"""
        if self.data is None or self.data.empty:
            self._current_section_data = []
            self.info_label.setText('⚠ Нет данных для отображения')
            return
        
        try:
            # Очищаем figure
            self.figure.clear()
            
            # Проверяем наличие секций
            if 'belt' not in self.data.columns:
                self._current_section_data = []
                self.info_label.setText('⚠ Данные должны содержать информацию о поясах')
                return
            
            # Рассчитываем отклонения по секциям
            section_data = self._calculate_section_deviations()
            
            if section_data is None or len(section_data) == 0:
                self._current_section_data = []
                self.info_label.setText('⚠ Недостаточно данных для построения графика')
                return
            
            # Делитель подгонки
            divisor = float(self.adjust_spin.value()) if hasattr(self, 'adjust_spin') and self.adjust_spin is not None else 1.0
            if divisor <= 0:
                divisor = 1.0

            self._current_section_data = self._make_table_payload(section_data)

            # Создаем два графика: один для X, один для Y
            ax_x = self.figure.add_subplot(1, 2, 1)
            self._plot_verticality_profile(ax_x, section_data, component='x', divisor=divisor)
            
            ax_y = self.figure.add_subplot(1, 2, 2)
            self._plot_verticality_profile(ax_y, section_data, component='y', divisor=divisor)
            
            # Обновляем canvas с улучшенными отступами для предотвращения наложения
            self.figure.subplots_adjust(left=0.18, right=0.96, bottom=0.08, top=0.95, wspace=0.42)
            self.canvas.draw()
            
            # Заполняем таблицу
            self._fill_deviation_table(section_data, divisor=divisor)
            
            logger.info(f"График вертикальности построен для {len(section_data)} секций")
            
        except Exception as e:
            self._current_section_data = []
            logger.error(f"Ошибка при построении графика вертикальности: {e}", exc_info=True)
            self.info_label.setText(f'❌ Ошибка: {str(e)}')
    
    def _decode_part_memberships(self, value) -> List[int]:
        """Декодирует JSON строку с принадлежностями к частям"""
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
        memberships: List[int] = []
        for item in decoded:
            try:
                memberships.append(int(item))
            except (TypeError, ValueError):
                continue
        return memberships
    
    def _section_belongs_to_part(self, section: Dict, part_num: int) -> bool:
        """Определяет, принадлежит ли секция к части башни"""
        # Проверяем segment в section_data (соответствует номеру части)
        if 'segment' in section:
            segment = section.get('segment')
            if segment is not None:
                try:
                    return int(segment) == part_num
                except (TypeError, ValueError):
                    pass
        
        # Если в section_data нет информации, используем данные точек
        if self.data is not None and not self.data.empty:
            section_height = section.get('height')
            if section_height is not None:
                # Находим точки на этой высоте и проверяем их принадлежность
                height_tolerance = 0.1
                height_mask = np.abs(self.data['z'] - section_height) <= height_tolerance
                matching_points = self.data[height_mask]
                
                if not matching_points.empty:
                    # Проверяем tower_part_memberships или tower_part
                    for _, point_row in matching_points.iterrows():
                        if 'tower_part_memberships' in point_row and pd.notna(point_row.get('tower_part_memberships')):
                            memberships = self._decode_part_memberships(point_row.get('tower_part_memberships'))
                            if part_num in memberships:
                                return True
                        if 'tower_part' in point_row and pd.notna(point_row.get('tower_part')):
                            try:
                                if int(point_row.get('tower_part')) == part_num:
                                    return True
                            except (TypeError, ValueError):
                                pass
        
        return False
    
    def _number_sections_sequentially(self, section_data_list: List[Dict]) -> None:
        """
        Пронумеровывает все секции сквозной нумерацией с 0 (по одной на абсолютную высоту).
        Дедуплицирует по высоте с допуском 1 см.
        
        Модифицирует section_data_list, добавляя поле 'section_num' к каждой секции.
        """
        # Сортируем секции по высоте
        sorted_sections = sorted(section_data_list, key=lambda s: s.get('height', 0))
        
        # Пронумеровываем все секции сквозной нумерацией с 0 (по одной на абсолютную высоту)
        height_tolerance = 0.01  # Допуск для определения одинаковой высоты (1 см)
        section_num = 0
        seen_heights = []
        
        for section in sorted_sections:
            section_height = section.get('height', 0)
            # Проверяем, не создали ли мы уже секцию на близкой высоте
            is_duplicate = False
            for seen_height in seen_heights:
                if abs(section_height - seen_height) <= height_tolerance:
                    is_duplicate = True
                    # Используем тот же номер, что и для предыдущей секции на этой высоте
                    section['section_num'] = section_num - 1
                    logger.debug(f"Секция на высоте {section_height:.3f}м использует номер {section_num - 1} (дубликат высоты)")
                    break
            
            if not is_duplicate:
                section['section_num'] = section_num
                seen_heights.append(section_height)
                section_num += 1
        
        logger.info(f"Пронумеровано {section_num} уникальных секций (сквозная нумерация с 0 до {section_num - 1})")
    
    def _collect_unique_parts_from_sections(self, section_data_list: List[Dict]) -> List[int]:
        """Собирает уникальные номера частей из секций"""
        parts = set()
        
        # Сначала пытаемся использовать segment из section_data
        for section in section_data_list:
            if 'segment' in section:
                segment = section.get('segment')
                if segment is not None:
                    try:
                        parts.add(int(segment))
                    except (TypeError, ValueError):
                        pass
        
        # Если не нашли через segment, используем данные точек
        if not parts and self.data is not None and not self.data.empty:
            if 'tower_part_memberships' in self.data.columns and self.data['tower_part_memberships'].notna().any():
                for value in self.data['tower_part_memberships'].dropna():
                    parts.update(self._decode_part_memberships(value))
            if 'tower_part' in self.data.columns and self.data['tower_part'].notna().any():
                parts.update(self.data['tower_part'].dropna().astype(int).unique())
        
        return sorted(parts) if parts else [1]
    
    @staticmethod
    def _infer_mm_scale(series: pd.Series) -> float:
        numeric = pd.to_numeric(series, errors='coerce').to_numpy(dtype=float)
        valid = numeric[np.isfinite(numeric)]
        if valid.size == 0:
            return 1.0
        return 1000.0 if float(np.nanmax(np.abs(valid))) < 2.0 else 1.0

    @staticmethod
    def _section_height_tolerance(section_data_list: List[Dict]) -> float:
        heights = sorted(
            {
                round(float(section.get('height', 0.0) or 0.0), 6)
                for section in section_data_list
                if section.get('height') is not None
            }
        )
        if len(heights) > 1:
            min_step = min(abs(heights[idx] - heights[idx - 1]) for idx in range(1, len(heights)))
            return max(0.05, min(1.5, float(min_step) * 0.6))
        return 0.3

    @staticmethod
    def _make_table_payload(section_data: List[Dict]) -> List[Dict]:
        from core.normatives import get_vertical_tolerance

        payload: List[Dict] = []
        for index, section in enumerate(sorted(section_data, key=lambda item: item.get('height', 0.0))):
            try:
                height = float(section.get('height', 0.0) or 0.0)
                deviation_x = float(section.get('deviation_x', 0.0) or 0.0)
                deviation_y = float(section.get('deviation_y', 0.0) or 0.0)
                total_deviation = float(
                    section.get(
                        'total_deviation',
                        np.hypot(deviation_x, deviation_y),
                    ) or 0.0
                )
            except (TypeError, ValueError):
                continue

            payload.append(
                {
                    'section_num': int(section.get('section_num', index)),
                    'height': height,
                    'deviation_x': deviation_x,
                    'deviation_y': deviation_y,
                    'total_deviation': total_deviation,
                    'deviation': total_deviation,
                    'tolerance': float(get_vertical_tolerance(height) * 1000.0),
                }
            )

        return payload

    def _build_sections_from_processed_centers(self) -> List[Dict]:
        if not isinstance(self.processed_data, dict):
            return []

        canonical_sections = get_preferred_verticality_sections(self.processed_data.get('angular_verticality'))
        if canonical_sections:
            return canonical_sections

        centers = self.processed_data.get('centers')
        if not isinstance(centers, pd.DataFrame) or centers.empty:
            return []

        if not (self.editor_3d and hasattr(self.editor_3d, 'section_data') and self.editor_3d.section_data):
            return []

        section_data_list = sorted(self.editor_3d.section_data, key=lambda s: s.get('height', 0.0))
        self._number_sections_sequentially(section_data_list)
        height_col = next((candidate for candidate in ('z', 'height', 'belt_height') if candidate in centers.columns), None)
        if height_col is None:
            return []

        scale_total = self._infer_mm_scale(centers['deviation']) if 'deviation' in centers.columns else 1.0
        scale_x = self._infer_mm_scale(centers['deviation_x']) if 'deviation_x' in centers.columns else scale_total
        scale_y = self._infer_mm_scale(centers['deviation_y']) if 'deviation_y' in centers.columns else scale_total
        height_tolerance = self._section_height_tolerance(section_data_list)
        result: List[Dict] = []

        for _, row in centers.sort_values(height_col).iterrows():
            try:
                height = float(row[height_col])
            except (TypeError, ValueError):
                continue

            matched_section = None
            matched_diff = float('inf')
            for section in section_data_list:
                section_height = section.get('height')
                if section_height is None:
                    continue
                diff = abs(float(section_height) - height)
                if diff <= height_tolerance and diff < matched_diff:
                    matched_section = section
                    matched_diff = diff

            deviation_x_mm = float(row.get('deviation_x', 0.0) or 0.0) * scale_x
            deviation_y_mm = float(row.get('deviation_y', 0.0) or 0.0) * scale_y
            total_deviation_mm = (
                float(row.get('deviation', 0.0) or 0.0) * scale_total
                if 'deviation' in row.index
                else float(np.hypot(deviation_x_mm, deviation_y_mm))
            )

            part_num = None
            section_num = len(result)
            if matched_section is not None:
                section_num = matched_section.get('section_num', section_num)
                tower_part = matched_section.get('tower_part')
                if tower_part is not None:
                    part_num = tower_part
                elif matched_section.get('tower_part_memberships'):
                    memberships = self._decode_part_memberships(matched_section.get('tower_part_memberships'))
                    if memberships:
                        part_num = memberships[0]

            result.append({
                'section_num': section_num,
                'height': height,
                'deviation_x': deviation_x_mm,
                'deviation_y': deviation_y_mm,
                'total_deviation': total_deviation_mm,
                'part_num': part_num,
            })

        return result

    def _calculate_section_deviations(self):
        """Рассчитать отклонения от вертикали для каждой секции
        
        Приоритетно использует данные из таблицы угловых измерений.
        Если данные угловых измерений недоступны, использует расчет на основе центров секций.
        
        Согласно нормативам (СП 70.13330.2012), отклонение вертикальности башни
        рассчитывается по секциям, а не по поясам. Секция - конструктивный элемент,
        который может включать несколько поясов.
        
        Логика:
        1. Приоритет: данные из таблицы угловых измерений (агрегированные по секциям)
        2. Fallback: расчет на основе центров секций из section_data
        
        Returns:
            List[Dict]: Список словарей с данными секций
        """
        if self.data_table_widget and hasattr(self.data_table_widget, 'get_angular_measurements'):
            try:
                if hasattr(self.data_table_widget, 'ensure_complete_angular_station_basis'):
                    self.data_table_widget.ensure_complete_angular_station_basis(interactive=False)
                angular_measurements = self.data_table_widget.get_angular_measurements()
                sections = get_preferred_verticality_sections(angular_measurements)
                if sections:
                    logger.info(f"Используем canonical payload угловых измерений: {len(sections)} секций")
                    return sections
            except Exception as e:
                logger.warning(f"Не удалось получить данные из таблицы угловых измерений: {e}")

        processed_sections = self._build_sections_from_processed_centers()
        if processed_sections:
            logger.info(f"Используем рассчитанные центры секций (fallback): {len(processed_sections)} секций")
            return processed_sections

        # Fallback: расчет на основе центров секций
        logger.info("Используем расчет на основе центров секций (fallback)")
        
        # Приоритетно используем секции из 3D редактора
        if self.editor_3d and hasattr(self.editor_3d, 'section_data') and self.editor_3d.section_data:
            section_data_list = self.editor_3d.section_data
            logger.info(f"Используем данные секций из 3D редактора: {len(section_data_list)} секций")
        else:
            logger.warning("Секции не созданы. Расчет вертикальности требует создания секций через 'Создать секции'")
            return None
        
        if len(section_data_list) == 0:
            logger.warning("Нет секций для расчета вертикальности")
            return None
        
        # Пронумеровываем все секции сквозной нумерацией с 0 (по одной на абсолютную высоту)
        self._number_sections_sequentially(section_data_list)
        
        # Сортируем секции по высоте (после нумерации)
        section_data_list = sorted(section_data_list, key=lambda s: s['height'])
        
        # Получаем локальную систему координат из processed_data для раскладывания отклонений
        x_axis = np.array([1.0, 0.0, 0.0])
        y_axis = np.array([0.0, 1.0, 0.0])
        if self.processed_data and 'local_cs' in self.processed_data:
            local_cs = self.processed_data.get('local_cs', {})
            if local_cs.get('valid', False):
                x_axis = np.array(local_cs.get('x_axis', [1.0, 0.0, 0.0]))
                y_axis = np.array(local_cs.get('y_axis', [0.0, 1.0, 0.0]))
        
        # Определяем части башни
        unique_parts = self._collect_unique_parts_from_sections(section_data_list)
        is_composite = len(unique_parts) > 1
        
        if is_composite:
            logger.info(f"Обнаружена составная башня с частями: {unique_parts}")
        else:
            logger.info("Обычная башня (одна часть)")
        
        # Результирующие данные для всех секций
        result_data = []
        
        # Обрабатываем каждую часть отдельно
        for part_num in unique_parts:
            # Фильтруем секции, принадлежащие этой части
            part_sections = [s for s in section_data_list if self._section_belongs_to_part(s, part_num)]
            
            if len(part_sections) == 0:
                logger.warning(f"Часть {part_num}: нет секций для расчета")
                continue
            
            # Сортируем секции части по высоте
            part_sections = sorted(part_sections, key=lambda s: s['height'])
            
            # Рассчитываем центры секций для этой части
            part_section_centers = []
            for section in part_sections:
                points = section.get('points', [])
                if len(points) == 0:
                    logger.warning(f"Секция части {part_num} на высоте {section['height']:.2f}м не содержит точек")
                    continue
                
                # Центр секции - среднее по X, Y координатам всех точек секции
                center_x = np.mean([p[0] for p in points])
                center_y = np.mean([p[1] for p in points])
                height = section['height']
                
                part_section_centers.append({
                    'height': height,
                    'center_x': center_x,
                    'center_y': center_y,
                    'points_count': len(points),
                    'section': section
                })
            
            if len(part_section_centers) == 0:
                logger.warning(f"Часть {part_num}: нет секций с точками для расчета")
                continue
            
            # Базовая секция для этой части - нижняя секция (минимальная высота)
            base_section = min(part_section_centers, key=lambda s: s['height'])
            base_x = base_section['center_x']
            base_y = base_section['center_y']
            base_height = base_section['height']
            
            logger.info(f"Часть {part_num}: базовая секция H={base_height:.3f}м, "
                       f"центр=({base_x:.3f}, {base_y:.3f}), всего секций в части: {len(part_section_centers)}")
            
            # Рассчитываем отклонения для каждой секции этой части относительно базовой секции части
            for section_info in part_section_centers:
                center_x = section_info['center_x']
                center_y = section_info['center_y']
                height = section_info['height']
                
                # Проверяем, является ли это базовой секцией
                if abs(height - base_height) < 0.01:
                    deviation_x_mm = 0.0
                    deviation_y_mm = 0.0
                    total_deviation_mm = 0.0
                else:
                    dx = center_x - base_x
                    dy = center_y - base_y
                    deviation_vector = np.array([dx, dy, 0.0])
                    deviation_x = np.dot(deviation_vector, x_axis)
                    deviation_y = np.dot(deviation_vector, y_axis)
                    deviation_x_mm = deviation_x * 1000
                    deviation_y_mm = deviation_y * 1000
                    total_deviation_mm = np.sqrt(dx**2 + dy**2) * 1000
                
                logger.debug(f"Часть {part_num}, секция H={height:.1f}м: центр=({center_x:.3f}, {center_y:.3f}), "
                            f"dx={deviation_x_mm:.2f}мм, dy={deviation_y_mm:.2f}мм, total={total_deviation_mm:.2f}мм")
                
                # Используем сквозную нумерацию из section_data
                section_num_for_result = section_info['section'].get('section_num', 0)
                
                result_data.append({
                    'section_num': section_num_for_result,
                    'height': height,
                    'center_x': center_x,
                    'center_y': center_y,
                    'deviation_x': deviation_x_mm,
                    'deviation_y': deviation_y_mm,
                    'total_deviation': total_deviation_mm,
                    'part_num': part_num
                })
        
        # Сортируем результат по высоте для корректного отображения
        result_data = sorted(result_data, key=lambda s: s['height'])
        
        # Дедуплицируем по высоте - на одной абсолютной высоте должна быть только одна секция
        # Если секция граничная и встречается в нескольких частях, берем первую (нижняя часть)
        deduplicated_result = []
        seen_heights = set()
        height_tolerance = 0.01
        
        for section_result in result_data:
            section_height = section_result['height']
            is_duplicate = False
            for seen_height in seen_heights:
                if abs(section_height - seen_height) <= height_tolerance:
                    is_duplicate = True
                    logger.debug(f"Пропущен дубликат секции на высоте {section_height:.3f}м (уже есть секция на высоте {seen_height:.3f}м)")
                    break
            
            if not is_duplicate:
                deduplicated_result.append(section_result)
                seen_heights.add(section_height)
        
        logger.info(f"Рассчитано {len(deduplicated_result)} уникальных секций с отклонениями (после дедупликации из {len(result_data)})")
        return deduplicated_result
    
    def _fill_deviation_table(self, section_data, divisor: float = 1.0):
        """Заполнить таблицу отклонений по секциям"""
        logger.info(f"Заполнение таблицы: {len(section_data)} секций")
        self.deviation_table.setRowCount(0)  # Очищаем таблицу
        
        if not section_data:
            logger.warning("section_data пустой, таблица не будет заполнена")
            return
        
        # Импортируем функцию расчета допуска
        from core.normatives import get_vertical_tolerance
        
        # Сортируем секции по высоте для корректного отображения
        section_data_sorted = sorted(section_data, key=lambda s: s.get('height', 0))
        
        for i, section in enumerate(section_data_sorted):
            row = self.deviation_table.rowCount()
            self.deviation_table.insertRow(row)
            
            # Номер секции (сквозная нумерация с 0)
            section_num = section.get('section_num', i)
            section_item = QTableWidgetItem(str(section_num))
            section_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.deviation_table.setItem(row, 0, section_item)
            
            # Высота
            height_item = QTableWidgetItem(f"{section['height']:.1f}")
            height_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.deviation_table.setItem(row, 1, height_item)
            
            # Номер части
            part_num = section.get('part_num', '')
            part_item = QTableWidgetItem(str(part_num) if part_num else '-')
            part_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.deviation_table.setItem(row, 2, part_item)
            
            # Отклонение X (с проверкой соответствия для компоненты)
            dev_x = section.get('deviation_x', 0.0)
            if divisor and divisor > 0:
                dev_x = dev_x / divisor
            dev_x_item = QTableWidgetItem(f"{dev_x:+.2f}")
            dev_x_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            tolerance_mm = get_vertical_tolerance(section['height']) * 1000
            if abs(dev_x) > tolerance_mm:
                dev_x_item.setForeground(QColor(220, 50, 50))  # Красный
            else:
                dev_x_item.setForeground(QColor(50, 150, 50))  # Зеленый
            self.deviation_table.setItem(row, 3, dev_x_item)
            
            # Отклонение Y (с проверкой соответствия для компоненты)
            dev_y = section.get('deviation_y', 0.0)
            if divisor and divisor > 0:
                dev_y = dev_y / divisor
            dev_y_item = QTableWidgetItem(f"{dev_y:+.2f}")
            dev_y_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if abs(dev_y) > tolerance_mm:
                dev_y_item.setForeground(QColor(220, 50, 50))  # Красный
            else:
                dev_y_item.setForeground(QColor(50, 150, 50))  # Зеленый
            self.deviation_table.setItem(row, 4, dev_y_item)
            
            # Суммарное отклонение
            total_dev = section.get('total_deviation', 0.0)
            if divisor and divisor > 0:
                total_dev = total_dev / divisor
            total_item = QTableWidgetItem(f"{total_dev:+.2f}")
            total_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            tolerance_mm = get_vertical_tolerance(section['height']) * 1000
            if abs(total_dev) > tolerance_mm:
                total_item.setForeground(QColor(220, 50, 50))  # Красный
            else:
                total_item.setForeground(QColor(50, 150, 50))  # Зеленый
            self.deviation_table.setItem(row, 5, total_item)
            
            # Допустимое отклонение (норматив СП 70.13330.2012)
            tolerance_text = f"{tolerance_mm:.2f}"
            tolerance_item = QTableWidgetItem(tolerance_text)
            tolerance_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            tolerance_item.setToolTip(f"СП 70.13330.2012: d_допуск = 0.001 × h = {tolerance_mm:.2f} мм\nгде h = {section['height']:.3f} м - высота секции")
            self.deviation_table.setItem(row, 6, tolerance_item)
            
            logger.debug(f"Строка {row}: Секция={section_num}, H={section['height']:.1f}м, "
                        f"X={dev_x:+.2f}мм, Y={dev_y:+.2f}мм, Total={total_dev:+.2f}мм, "
                        f"Допуск={tolerance_mm:.2f}мм")
        
        logger.info(f"Таблица заполнена {self.deviation_table.rowCount()} строками (базовая секция исключена)")
    
    def get_table_data(self):
        """Получить данные из таблицы отклонений
        
        Returns:
            List[Dict]: Список словарей с ключами 'section_num', 'height', 
                       'deviation_x', 'deviation_y', 'total_deviation', 'tolerance'
        """
        if self._current_section_data:
            return copy.deepcopy(self._current_section_data)

        data = []
        for i in range(self.deviation_table.rowCount()):
            section_item = self.deviation_table.item(i, 0)  # № секции
            height_item = self.deviation_table.item(i, 1)   # Высота
            dev_x_item = self.deviation_table.item(i, 3)    # Отклонение X
            dev_y_item = self.deviation_table.item(i, 4)    # Отклонение Y
            total_item = self.deviation_table.item(i, 5)    # Суммарное отклонение
            tolerance_item = self.deviation_table.item(i, 6) # Допустимое

            if height_item and total_item:
                try:
                    section_num = int(section_item.text()) if section_item else i + 1
                    height = float(height_item.text())
                    dev_x = float(dev_x_item.text()) if dev_x_item else 0.0
                    dev_y = float(dev_y_item.text()) if dev_y_item else 0.0
                    total_dev = float(total_item.text()) if total_item else 0.0
                    tolerance = float(tolerance_item.text()) if tolerance_item else 0.0
                    
                    data.append({
                        'section_num': section_num,
                        'height': height,
                        'deviation_x': dev_x,
                        'deviation_y': dev_y,
                        'total_deviation': total_dev,
                        'deviation': total_dev,  # Для обратной совместимости
                        'tolerance': tolerance
                    })
                except (ValueError, AttributeError):
                    continue
        
        # Если таблица пуста, но есть section_data, используем его
        if not data and hasattr(self, 'section_data') and self.section_data:
            logger.info("Используем section_data для получения данных таблицы")
            return self.section_data
        
        return data
    
    def _plot_verticality_profile(self, ax, section_data, component='x', divisor: float = 1.0):
        """Построить профиль вертикальности для компоненты X или Y
        
        Args:
            ax: Matplotlib axis
            section_data: Данные секций с deviation_x и deviation_y
            component: 'x' или 'y' - какой компонент отображать
        """
        # Импортируем функцию расчета допуска
        from core.normatives import get_vertical_tolerance

        section_data_sorted = sorted(section_data, key=lambda item: float(item.get('height', 0.0) or 0.0))
        heights = [d['height'] for d in section_data_sorted]
        raw_dev_x = [float(d.get('deviation_x', 0.0) or 0.0) for d in section_data_sorted]
        raw_dev_y = [float(d.get('deviation_y', 0.0) or 0.0) for d in section_data_sorted]
        base_height = min(heights) if heights else 0.0
        highest_height = max(heights) if heights else 0.0
        top_allowed = get_vertical_tolerance(highest_height) * 1000 if heights else 0.0
        if component == 'x':
            deviations = raw_dev_x
            component_label = 'X'
            color = '#E74C3C'
            paired_deviations = raw_dev_y
        else:
            deviations = raw_dev_y
            component_label = 'Y'
            color = '#3498DB'
            paired_deviations = raw_dev_x

        # Применяем делитель подгонки
        if divisor and divisor > 0:
            deviations = [float(v) / divisor for v in deviations]
            paired_deviations = [float(v) / divisor for v in paired_deviations]
        
        ax.set_xlabel(f'Отклонение {component_label}, мм', fontsize=10)
        ax.set_ylabel('Высота, м', fontsize=10)
        ax.set_title(f'Вертикальность по оси {component_label}', fontsize=11, fontweight='bold')
        
        combined = deviations + paired_deviations
        max_deviation_abs = max(abs(d) for d in combined) if combined else 50
        allowed_extent = max(max_deviation_abs, abs(top_allowed))
        x_limit = allowed_extent * 1.1 if allowed_extent > 0 else 10
        ax.set_xlim(-x_limit, x_limit)
        
        # Пределы по вертикали (точные значения минимума и максимума высот)
        y_min_raw = min(heights)
        y_max_raw = max(heights)
        y_min = y_min_raw - (y_max_raw - y_min_raw) * 0.05  # Запас 5%
        y_max = y_max_raw + (y_max_raw - y_min_raw) * 0.05
        ax.set_ylim(y_min, y_max)
        
        # Округленные высоты секций для меток оси Y
        section_heights_rounded = sorted(set([int(h) for h in heights]))
        
        # Центральная вертикальная линия (ноль)
        ax.axvline(x=0, color='black', linewidth=1.0, linestyle='-', zorder=1)
        
        # Вертикальная сетка (тонкая)
        ax.grid(True, axis='x', linestyle=':', linewidth=0.5, alpha=0.5, color='gray', zorder=0)
        
        # Горизонтальная сетка по высотам секций
        ax.grid(True, axis='y', linestyle=':', linewidth=0.5, alpha=0.3, color='gray', zorder=0)
        ax.yaxis.set_major_locator(MaxNLocator(nbins=8))
        ax.xaxis.set_major_locator(MaxNLocator(nbins=6))
        
        # Рисуем предельные линии для каждой высоты секции
        if top_allowed > 0:
            y_top = highest_height + (highest_height - base_height) * 0.05
            ax.plot(
                [0.0, top_allowed],
                [base_height, y_top],
                color='#7f8c8d',
                linewidth=1.2,
                linestyle='--',
                alpha=0.8,
                zorder=2,
            )
            ax.plot(
                [0.0, -top_allowed],
                [base_height, y_top],
                color='#7f8c8d',
                linewidth=1.2,
                linestyle='--',
                alpha=0.8,
                zorder=2,
            )
        
        # Фактическая ломаная линия отклонений - с учетом знака
        ax.plot(deviations, heights, 
               color=color, linewidth=2.0, linestyle='-', 
               marker='o', markersize=5, markerfacecolor=color,
               markeredgecolor='white', markeredgewidth=0.5,
               label=f'Отклонение по {component_label}', zorder=5)
        
        # Легенда с улучшенным размещением
        ax.legend(loc='best', fontsize=9, framealpha=0.9, frameon=True)
        
        # Стиль осей (инженерный)
        ax.spines['top'].set_linewidth(0.5)
        ax.spines['right'].set_linewidth(0.5)
        ax.spines['bottom'].set_linewidth(1.0)
        ax.spines['left'].set_linewidth(1.0)
        
        # Делаем шрифты тоньше
        for label in ax.get_xticklabels() + ax.get_yticklabels():
            label.set_fontsize(9)
