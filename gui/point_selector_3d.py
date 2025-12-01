"""
3D визуализатор и редактор точек для выбора точек башни
Использует plotly для интерактивной 3D визуализации
"""

import numpy as np
import pandas as pd
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
                             QLabel, QGroupBox, QTextEdit, QSplitter, QCheckBox,
                             QSpinBox, QDoubleSpinBox, QFormLayout, QWidget)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWebEngineWidgets import QWebEngineView
import plotly.graph_objects as go
import plotly.express as px
from typing import Optional, List, Dict
import logging

from core.point_filter import PointFilter, InteractivePointSelector
from gui.ui_helpers import apply_compact_button_style

logger = logging.getLogger(__name__)


class PointSelector3DDialog(QDialog):
    """
    Диалог для 3D визуализации и интерактивного выбора точек
    """
    
    points_filtered = pyqtSignal(pd.DataFrame, dict)  # Сигнал с отфильтрованными точками
    
    def __init__(self, data: pd.DataFrame, parent=None):
        super().__init__(parent)
        
        self.original_data = data.copy()
        self.filtered_data = None
        self.analysis_info = None
        
        # Фильтр и селектор
        self.point_filter = PointFilter()
        self.selector = InteractivePointSelector(data)
        
        # Режим работы
        self.auto_filter_applied = False
        
        self.init_ui()
        
        # Сразу показываем все точки
        self.show_all_points()
    
    def init_ui(self):
        """Инициализация интерфейса"""
        self.setWindowTitle('3D Фильтр точек башни')
        self.setGeometry(100, 100, 1400, 900)
        
        # Главный layout
        main_layout = QVBoxLayout()
        
        # Верхняя панель - кнопки управления
        control_panel = self.create_control_panel()
        main_layout.addWidget(control_panel)
        
        # Центральная часть - splitter с 3D видом и информацией
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # 3D вид (plotly через QWebEngineView)
        self.web_view = QWebEngineView()
        splitter.addWidget(self.web_view)
        
        # Правая панель - информация и настройки
        right_panel = self.create_right_panel()
        splitter.addWidget(right_panel)
        
        splitter.setStretchFactor(0, 3)  # 3D вид занимает больше места
        splitter.setStretchFactor(1, 1)
        
        main_layout.addWidget(splitter)
        
        # Нижние кнопки
        button_layout = QHBoxLayout()
        
        self.apply_btn = QPushButton('✓ Применить фильтр')
        self.apply_btn.clicked.connect(self.apply_filter)
        apply_compact_button_style(self.apply_btn, width=96, min_height=34)

        cancel_btn = QPushButton('Отмена')
        cancel_btn.clicked.connect(self.reject)
        apply_compact_button_style(cancel_btn, width=88, min_height=34)
        
        button_layout.addStretch()
        button_layout.addWidget(self.apply_btn)
        button_layout.addWidget(cancel_btn)
        
        main_layout.addLayout(button_layout)
        
        self.setLayout(main_layout)
    
    def create_control_panel(self) -> QWidget:
        """Создание панели управления"""
        panel = QGroupBox("Управление")
        layout = QHBoxLayout()
        
        # Кнопка автофильтрации
        self.auto_filter_btn = QPushButton('🔍\nАвто\nфильтрация')
        self.auto_filter_btn.clicked.connect(self.run_auto_filter)
        self.auto_filter_btn.setToolTip('Автоматически определить точки башни по геометрии')
        apply_compact_button_style(self.auto_filter_btn, width=90, min_height=48)
        layout.addWidget(self.auto_filter_btn)
        
        # Кнопка сброса
        reset_btn = QPushButton('↺\nСбросить')
        reset_btn.clicked.connect(self.reset_filter)
        reset_btn.setToolTip('Сбросить все фильтры и показать все точки')
        apply_compact_button_style(reset_btn, width=80, min_height=46)
        layout.addWidget(reset_btn)
        
        # Кнопка инверсии
        invert_btn = QPushButton('⇄\nИнвертировать')
        invert_btn.clicked.connect(self.invert_selection)
        invert_btn.setToolTip('Инвертировать выбор (выбранные ↔ отклоненные)')
        apply_compact_button_style(invert_btn, width=90, min_height=46)
        layout.addWidget(invert_btn)
        
        layout.addStretch()
        
        # Статистика
        self.stats_label = QLabel()
        self.update_stats_label()
        layout.addWidget(self.stats_label)
        
        panel.setLayout(layout)
        return panel
    
    def create_right_panel(self) -> QWidget:
        """Создание правой панели с информацией и настройками"""
        panel = QWidget()
        layout = QVBoxLayout()
        
        # Настройки фильтра
        settings_group = QGroupBox("Настройки фильтра")
        settings_layout = QFormLayout()
        
        self.height_tolerance_spin = QDoubleSpinBox()
        self.height_tolerance_spin.setRange(0.01, 5.0)
        self.height_tolerance_spin.setValue(0.1)
        self.height_tolerance_spin.setSingleStep(0.05)
        self.height_tolerance_spin.setDecimals(2)
        self.height_tolerance_spin.setSuffix(' м')
        self.height_tolerance_spin.setToolTip('Допуск группировки точек по высоте')
        settings_layout.addRow('Допуск по высоте:', self.height_tolerance_spin)
        
        self.min_points_spin = QSpinBox()
        self.min_points_spin.setRange(1, 12)
        self.min_points_spin.setValue(1)
        self.min_points_spin.setToolTip('Минимум точек на поясе (1 для центров поясов)')
        settings_layout.addRow('Мин. точек на пояс:', self.min_points_spin)
        
        self.max_points_spin = QSpinBox()
        self.max_points_spin.setRange(1, 20)
        self.max_points_spin.setValue(20)
        self.max_points_spin.setToolTip('Максимум точек на поясе')
        settings_layout.addRow('Макс. точек на пояс:', self.max_points_spin)
        
        self.circularity_spin = QDoubleSpinBox()
        self.circularity_spin.setRange(0.0, 1.0)
        self.circularity_spin.setValue(0.0)
        self.circularity_spin.setSingleStep(0.05)
        self.circularity_spin.setDecimals(2)
        self.circularity_spin.setToolTip('Порог "круглости" пояса (0.0 = отключить, 1.0 = идеальная окружность)')
        settings_layout.addRow('Порог круглости:', self.circularity_spin)
        
        settings_group.setLayout(settings_layout)
        layout.addWidget(settings_group)
        
        # Информация об анализе
        info_group = QGroupBox("Результаты анализа")
        info_layout = QVBoxLayout()
        
        self.info_text = QTextEdit()
        self.info_text.setReadOnly(True)
        self.info_text.setMaximumHeight(300)
        info_layout.addWidget(self.info_text)
        
        info_group.setLayout(info_layout)
        layout.addWidget(info_group)
        
        # Легенда цветов
        legend_group = QGroupBox("Легенда")
        legend_layout = QVBoxLayout()
        
        legend_layout.addWidget(QLabel('🟢 Зеленый - Точки башни (выбрано)'))
        legend_layout.addWidget(QLabel('🔴 Красный - Отклонено (реперы, оборудование)'))
        legend_layout.addWidget(QLabel('🟡 Желтый - Сомнительные точки'))
        
        legend_group.setLayout(legend_layout)
        layout.addWidget(legend_group)
        
        layout.addStretch()
        
        panel.setLayout(layout)
        return panel
    
    def show_all_points(self):
        """Показать все точки без фильтрации"""
        data = self.original_data
        
        # Все точки - синий цвет (не классифицированы)
        colors = ['blue'] * len(data)
        labels = ['Не классифицировано'] * len(data)
        
        self.update_3d_view(data, colors, labels)
        
        self.info_text.setText(f"Загружено {len(data)} точек\n\n"
                              "Нажмите 'Автоматическая фильтрация' для анализа")
    
    def run_auto_filter(self):
        """Запуск автоматической фильтрации"""
        # Обновляем параметры фильтра из настроек
        self.point_filter.height_tolerance = self.height_tolerance_spin.value()
        self.point_filter.min_points = self.min_points_spin.value()
        self.point_filter.max_points = self.max_points_spin.value()
        self.point_filter.circularity_threshold = self.circularity_spin.value()
        
        # Запускаем анализ
        try:
            filtered_data, analysis_info = self.point_filter.analyze_and_filter(self.original_data)
            
            self.filtered_data = filtered_data
            self.analysis_info = analysis_info
            self.auto_filter_applied = True
            
            # Обновляем селектор
            classification = self.point_filter.get_classification(self.original_data)
            self.selector.selection = (classification == 'tower')
            
            # Визуализация результатов
            self.visualize_filter_results()
            
            # Обновляем информацию
            summary = self.point_filter.get_summary()
            self.info_text.setText(summary)
            
            self.update_stats_label()
            
            logger.info(f"Автофильтрация: {len(filtered_data)}/{len(self.original_data)} точек")
            
        except Exception as e:
            logger.error(f"Ошибка автофильтрации: {str(e)}")
            self.info_text.setText(f"ОШИБКА:\n{str(e)}")
    
    def visualize_filter_results(self):
        """Визуализация результатов фильтрации"""
        data = self.original_data
        classification = self.point_filter.get_classification(data)
        
        # Цвета по классификации
        color_map = {
            'tower': 'green',
            'rejected': 'red',
            'unknown': 'gray'
        }
        
        colors = [color_map[c] for c in classification]
        labels = classification.tolist()
        
        self.update_3d_view(data, colors, labels)
    
    def update_3d_view(self, data: pd.DataFrame, colors: List[str], labels: List[str]):
        """Обновление 3D визуализации"""
        # Создаем 3D scatter plot с plotly
        fig = go.Figure()
        
        # Группируем по цветам для легенды
        unique_colors = list(set(colors))
        color_names = {
            'green': 'Башня (выбрано)',
            'red': 'Отклонено',
            'blue': 'Не классифицировано',
            'gray': 'Неизвестно',
            'yellow': 'Сомнительно'
        }
        
        for color in unique_colors:
            mask = [c == color for c in colors]
            mask_array = np.array(mask)
            
            fig.add_trace(go.Scatter3d(
                x=data['x'][mask_array],
                y=data['y'][mask_array],
                z=data['z'][mask_array],
                mode='markers',
                name=color_names.get(color, color),
                marker=dict(
                    size=6,
                    color=color,
                    line=dict(color='black', width=0.5)
                ),
                text=[f"#{i}: ({data['x'].iloc[i]:.2f}, {data['y'].iloc[i]:.2f}, {data['z'].iloc[i]:.2f})" 
                      for i in range(len(data)) if mask[i]],
                hovertemplate='%{text}<extra></extra>'
            ))
        
        # Если есть ось башни, рисуем ее
        if self.analysis_info and self.analysis_info.get('tower_axis'):
            axis = self.analysis_info['tower_axis']
            z_range = [data['z'].min(), data['z'].max()]
            
            # Вертикальная линия оси
            fig.add_trace(go.Scatter3d(
                x=[axis['center_x'], axis['center_x']],
                y=[axis['center_y'], axis['center_y']],
                z=z_range,
                mode='lines',
                name='Ось башни',
                line=dict(color='black', width=4, dash='dash')
            ))
        
        # Настройки layout
        fig.update_layout(
            title='3D Модель точек съемки',
            scene=dict(
                xaxis_title='X (Easting), м',
                yaxis_title='Y (Northing), м',
                zaxis_title='Z (Высота), м',
                aspectmode='data'
            ),
            height=800,
            showlegend=True,
            legend=dict(x=0.7, y=0.95)
        )
        
        # Конвертируем в HTML и загружаем в веб-вид
        # Используем inline для надежности (не требует интернета)
        html = fig.to_html(include_plotlyjs='inline')
        self.web_view.setHtml(html)
    
    def reset_filter(self):
        """Сброс всех фильтров"""
        self.selector = InteractivePointSelector(self.original_data)
        self.filtered_data = None
        self.analysis_info = None
        self.auto_filter_applied = False
        
        self.show_all_points()
        self.update_stats_label()
        
        logger.info("Фильтр сброшен")
    
    def invert_selection(self):
        """Инвертирование выбора"""
        self.selector.selection = ~self.selector.selection
        
        # Обновляем визуализацию
        if self.auto_filter_applied:
            # Инвертируем классификацию
            classification = self.point_filter.get_classification(self.original_data)
            inverted_class = classification.apply(lambda x: 'rejected' if x == 'tower' else 'tower' if x == 'rejected' else x)
            
            color_map = {'tower': 'green', 'rejected': 'red', 'unknown': 'gray'}
            colors = [color_map[c] for c in inverted_class]
            labels = inverted_class.tolist()
            
            self.update_3d_view(self.original_data, colors, labels)
        
        self.update_stats_label()
        logger.info("Выбор инвертирован")
    
    def update_stats_label(self):
        """Обновление статистики"""
        selected = self.selector.selection.sum()
        total = len(self.original_data)
        rejected = total - selected
        
        self.stats_label.setText(
            f"<b>Статистика:</b> Выбрано: {selected} | Отклонено: {rejected} | Всего: {total}"
        )
    
    def apply_filter(self):
        """Применение фильтра и закрытие диалога"""
        filtered_data = self.selector.get_selected_data()
        
        if len(filtered_data) < 3:
            self.info_text.setText("ОШИБКА: Недостаточно точек для анализа (минимум 3)")
            return
        
        # Формируем информацию для передачи
        filter_info = {
            'total_points': len(self.original_data),
            'selected_points': len(filtered_data),
            'auto_filter_applied': self.auto_filter_applied,
            'analysis_info': self.analysis_info
        }
        
        # Отправляем сигнал с отфильтрованными данными
        self.points_filtered.emit(filtered_data, filter_info)
        
        self.accept()
    
    def get_filtered_data(self) -> Optional[pd.DataFrame]:
        """Получить отфильтрованные данные (после закрытия диалога)"""
        return self.selector.get_selected_data()


class Point3DViewer(QWidget):
    """
    Виджет для простого просмотра 3D модели башни
    (Для вставки в главное окно или отчеты)
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        layout = QVBoxLayout()
        
        self.web_view = QWebEngineView()
        layout.addWidget(self.web_view)
        
        self.setLayout(layout)
    
    def show_tower_3d(self, data: pd.DataFrame, belt_labels: Optional[pd.Series] = None):
        """
        Показать 3D модель башни
        
        Args:
            data: DataFrame с координатами (x, y, z)
            belt_labels: Метки поясов для цветовой кодировки
        """
        fig = go.Figure()
        
        if belt_labels is not None and 'belt_id' in data.columns:
            # Цветовая кодировка по поясам
            unique_belts = sorted(data['belt_id'].unique())
            colors = px.colors.qualitative.Set3[:len(unique_belts)]
            
            for i, belt_id in enumerate(unique_belts):
                belt_data = data[data['belt_id'] == belt_id]
                
                fig.add_trace(go.Scatter3d(
                    x=belt_data['x'],
                    y=belt_data['y'],
                    z=belt_data['z'],
                    mode='markers',
                    name=f'Пояс {belt_id} (h={belt_data["z"].mean():.1f}м)',
                    marker=dict(size=8, color=colors[i % len(colors)])
                ))
        else:
            # Простое отображение всех точек
            fig.add_trace(go.Scatter3d(
                x=data['x'],
                y=data['y'],
                z=data['z'],
                mode='markers',
                marker=dict(size=6, color='blue')
            ))
        
        fig.update_layout(
            title='3D Модель башни',
            scene=dict(
                xaxis_title='X, м',
                yaxis_title='Y, м',
                zaxis_title='Z, м',
                aspectmode='data'
            ),
            height=600
        )
        
        html = fig.to_html(include_plotlyjs='cdn')
        self.web_view.setHtml(html)

