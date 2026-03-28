"""
Виджеты для отображения графиков
"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QSizePolicy
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
import pandas as pd
import numpy as np
from core.normatives import get_vertical_tolerance, get_straightness_tolerance


class BasePlotWidget(QWidget):
    """Базовый виджет для графиков"""
    
    def __init__(self):
        super().__init__()
        self.init_ui()
        
    def init_ui(self):
        """Инициализация интерфейса"""
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        # Создаем фигуру matplotlib
        self.figure = Figure(figsize=(10, 8))
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        # Панель инструментов
        self.toolbar = NavigationToolbar(self.canvas, self)
        
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas)
        
    def clear(self):
        """Очищает график"""
        self.figure.clear()
        self.canvas.draw()


class VerticalityPlotWidget(BasePlotWidget):
    """Виджет для графика вертикальности"""
    
    def plot(self, centers: pd.DataFrame, axis: dict):
        """
        Строит график отклонения от вертикали
        
        Args:
            centers: DataFrame с центрами поясов и отклонениями
            axis: Параметры аппроксимированной оси
        """
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        
        if centers.empty:
            ax.text(0.5, 0.5, 'Нет данных для отображения',
                   ha='center', va='center', transform=ax.transAxes, fontsize=14)
            self.canvas.draw()
            return
        
        # Преобразуем в мм для удобства отображения
        heights = centers['z'].values
        deviations_mm = centers['deviation'].values * 1000  # в мм
        
        # Вычисляем допуски
        tolerances_mm = np.array([get_vertical_tolerance(h) * 1000 for h in heights])
        
        # Определяем цвета точек (зеленый - норма, красный - превышение)
        passed_flags = [abs(d) <= t for d, t in zip(deviations_mm, tolerances_mm)]
        colors = ['#2ECC71' if p else '#E74C3C' for p in passed_flags]
        
        # Заполненная область допуска (как в примере)
        ax.fill_betweenx(heights, -tolerances_mm, tolerances_mm, 
                         alpha=0.2, color='#3498DB', label='Область допуска')
        
        # Линии допуска (пунктирные)
        ax.plot(tolerances_mm, heights, 'b--', linewidth=1.5, alpha=0.7)
        ax.plot(-tolerances_mm, heights, 'b--', linewidth=1.5, alpha=0.7)
        
        # График отклонений с линией
        ax.plot(deviations_mm, heights, 'o-', color='#34495E', linewidth=2, 
               markersize=8, markerfacecolor='white', markeredgewidth=2,
               label='Фактические отклонения', zorder=10)
        
        # Цветные маркеры для точек в норме/не в норме
        for d, h, c in zip(deviations_mm, heights, colors):
            ax.plot(d, h, 'o', color=c, markersize=10, zorder=11)
        
        # Нулевая линия (идеальная вертикаль)
        ax.axvline(x=0, color='#7F8C8D', linestyle='-', linewidth=2, alpha=0.5, label='Идеальная вертикаль')
        
        # Оформление
        ax.set_xlabel('Отклонение от вертикали, мм', fontsize=13, fontweight='bold', labelpad=10)
        ax.set_ylabel('Высота, м', fontsize=13, fontweight='bold', labelpad=10)
        ax.set_title('График отклонения от вертикали\nСП 70.13330.2012 (d ≤ 0.001·h)', 
                    fontsize=15, fontweight='bold', pad=20)
        ax.grid(True, alpha=0.3, linestyle='--', linewidth=0.7)
        ax.legend(loc='best', fontsize=10, framealpha=0.9, shadow=True)
        
        # Улучшенные границы графика
        x_margin = max(abs(deviations_mm).max(), tolerances_mm.max()) * 0.2
        ax.set_xlim(-tolerances_mm.max() - x_margin, tolerances_mm.max() + x_margin)
        
        # Статистика
        passed = sum(passed_flags)
        failed = len(passed_flags) - passed
        stats_text = f'✓ В норме: {passed}\n✗ Превышение: {failed}'
        ax.text(0.98, 0.02, stats_text, transform=ax.transAxes,
               verticalalignment='bottom', horizontalalignment='right',
               bbox=dict(boxstyle='round', facecolor='lightblue', alpha=0.7))
        
        self.figure.tight_layout()
        self.canvas.draw()


class StraightnessPlotWidget(BasePlotWidget):
    """Виджет для графика прямолинейности"""
    
    def plot(self, centers: pd.DataFrame):
        """
        Строит график стрелы прогиба (прямолинейность)
        
        Args:
            centers: DataFrame с центрами поясов и отклонениями прямолинейности
        """
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        
        if centers.empty or 'straightness_deviation' not in centers:
            ax.text(0.5, 0.5, 'Нет данных для отображения',
                   ha='center', va='center', transform=ax.transAxes, fontsize=14)
            self.canvas.draw()
            return
        
        # Преобразуем в мм
        heights = centers['z'].values
        deviations_mm = centers['straightness_deviation'].values * 1000  # в мм
        
        # Допуск прямолинейности
        if 'section_length' in centers and centers['section_length'].iloc[0] > 0:
            section_length = centers['section_length'].iloc[0]
            tolerance = get_straightness_tolerance(section_length) * 1000  # в мм
        else:
            tolerance = 0
        
        # Определяем цвета
        passed_flags = [abs(d) <= tolerance for d in deviations_mm]
        colors = ['#2ECC71' if p else '#E74C3C' for p in passed_flags]
        
        # Заполненная область допуска
        if tolerance > 0:
            ax.fill_betweenx(heights, -tolerance, tolerance, 
                             alpha=0.2, color='#9B59B6', label='Область допуска')
            # Линии допуска (пунктирные)
            ax.axvline(x=tolerance, color='#8E44AD', linestyle='--', linewidth=1.5, alpha=0.7)
            ax.axvline(x=-tolerance, color='#8E44AD', linestyle='--', linewidth=1.5, alpha=0.7)
        
        # График отклонений с линией
        ax.plot(deviations_mm, heights, 'o-', color='#34495E', linewidth=2,
               markersize=8, markerfacecolor='white', markeredgewidth=2,
               label='Фактическая стрела прогиба', zorder=10)
        
        # Цветные маркеры для точек
        for d, h, c in zip(deviations_mm, heights, colors):
            ax.plot(d, h, 'o', color=c, markersize=10, zorder=11)
        
        # Нулевая линия (базовая прямая)
        ax.axvline(x=0, color='#7F8C8D', linestyle='-', linewidth=2, alpha=0.5,
                  label='Базовая линия прямолинейности')
        
        # Оформление
        ax.set_xlabel('Стрела прогиба, мм', fontsize=13, fontweight='bold', labelpad=10)
        ax.set_ylabel('Высота, м', fontsize=13, fontweight='bold', labelpad=10)
        ax.set_title('График отклонения от прямолинейности\nИнструкция Минсвязи СССР 1980 (δ ≤ L/750)',
                    fontsize=15, fontweight='bold', pad=20)
        ax.grid(True, alpha=0.3, linestyle='--', linewidth=0.7)
        ax.legend(loc='best', fontsize=10, framealpha=0.9, shadow=True)
        
        # Улучшенные границы графика
        if tolerance > 0:
            x_margin = tolerance * 0.2
            ax.set_xlim(-tolerance - x_margin, tolerance + x_margin)
        
        # Статистика
        passed = sum(passed_flags)
        failed = len(passed_flags) - passed
        stats_text = f'✓ В норме: {passed}\n✗ Превышение: {failed}'
        if tolerance > 0:
            stats_text += f'\n\nДопуск: {tolerance:.2f} мм'
        ax.text(0.98, 0.02, stats_text, transform=ax.transAxes,
               verticalalignment='bottom', horizontalalignment='right',
               bbox=dict(boxstyle='round', facecolor='lightgreen', alpha=0.7))
        
        self.figure.tight_layout()
        self.canvas.draw()


class CombinedPlotWidget(BasePlotWidget):
    """Виджет с комбинированным отображением"""
    
    def plot(self, centers: pd.DataFrame, axis: dict):
        """
        Строит оба графика на одной фигуре
        
        Args:
            centers: DataFrame с данными
            axis: Параметры оси
        """
        self.figure.clear()
        
        # Два графика рядом
        ax1 = self.figure.add_subplot(121)
        ax2 = self.figure.add_subplot(122)
        
        # График вертикальности в ax1
        if not centers.empty:
            heights = centers['z'].values
            deviations_mm = centers['deviation'].values * 1000
            tolerances_mm = np.array([get_vertical_tolerance(h) * 1000 for h in heights])
            
            colors = ['green' if abs(d) <= t else 'red'
                     for d, t in zip(deviations_mm, tolerances_mm)]
            
            ax1.scatter(deviations_mm, heights, c=colors, s=80, alpha=0.6)
            ax1.plot(tolerances_mm, heights, 'b--', linewidth=1.5)
            ax1.plot(-tolerances_mm, heights, 'b--', linewidth=1.5)
            ax1.axvline(x=0, color='gray', linestyle='-', linewidth=0.5)
            ax1.set_xlabel('Отклонение (мм)')
            ax1.set_ylabel('Высота (м)')
            ax1.set_title('Вертикальность')
            ax1.grid(True, alpha=0.3)
        
        # График прямолинейности в ax2
        if not centers.empty and 'straightness_deviation' in centers:
            deviations_mm = centers['straightness_deviation'].values * 1000
            
            if 'section_length' in centers:
                section_length = centers['section_length'].iloc[0]
                tolerance = get_straightness_tolerance(section_length) * 1000
                colors = ['green' if abs(d) <= tolerance else 'red' for d in deviations_mm]
                
                ax2.scatter(deviations_mm, heights, c=colors, s=80, alpha=0.6)
                ax2.axvline(x=tolerance, color='blue', linestyle='--', linewidth=1.5)
                ax2.axvline(x=-tolerance, color='blue', linestyle='--', linewidth=1.5)
            else:
                ax2.scatter(deviations_mm, heights, c='blue', s=80, alpha=0.6)
            
            ax2.axvline(x=0, color='gray', linestyle='-', linewidth=0.5)
            ax2.set_xlabel('Стрела прогиба (мм)')
            ax2.set_ylabel('Высота (м)')
            ax2.set_title('Прямолинейность')
            ax2.grid(True, alpha=0.3)
        
        self.figure.tight_layout()
        self.canvas.draw()

