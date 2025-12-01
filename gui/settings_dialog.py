"""
Диалог настроек расчета
"""

from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
                             QLabel, QDoubleSpinBox, QComboBox, QPushButton,
                             QGroupBox, QSpinBox, QCheckBox, QDialogButtonBox,
                             QTabWidget, QWidget, QFileDialog, QMessageBox,
                             QFontComboBox, QSlider)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from gui.ui_helpers import apply_compact_button_style
from utils.settings_manager import SettingsManager
from core.exceptions import SettingsLoadError, SettingsSaveError
import logging

logger = logging.getLogger(__name__)

class SettingsDialog(QDialog):
    """Диалог настроек параметров расчета"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Настройки')
        self.setModal(True)
        self.resize(600, 600)
        self.settings_manager = SettingsManager()
        self.init_ui()
        self.load_settings()
        
    def init_ui(self):
        """Инициализация интерфейса"""
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        # Создаем вкладки
        tabs = QTabWidget()
        layout.addWidget(tabs)
        
        # Вкладка 1: Расчеты
        calc_tab = QWidget()
        calc_layout = QVBoxLayout()
        calc_tab.setLayout(calc_layout)
        
        # Группа: Параметры группировки
        grouping_group = QGroupBox('Параметры группировки точек')
        grouping_layout = QFormLayout()
        grouping_group.setLayout(grouping_layout)
        
        self.height_tolerance_spin = QDoubleSpinBox()
        self.height_tolerance_spin.setRange(0.01, 1.0)
        self.height_tolerance_spin.setSingleStep(0.01)
        self.height_tolerance_spin.setValue(0.1)
        self.height_tolerance_spin.setDecimals(2)
        self.height_tolerance_spin.setSuffix(' м')
        self.height_tolerance_spin.setToolTip('Допуск по высоте для объединения точек в один пояс')
        grouping_layout.addRow('Допуск по высоте:', self.height_tolerance_spin)
        
        calc_layout.addWidget(grouping_group)
        
        # Группа: Методы расчета
        methods_group = QGroupBox('Методы расчета')
        methods_layout = QFormLayout()
        methods_group.setLayout(methods_layout)
        
        self.center_method_combo = QComboBox()
        self.center_method_combo.addItem('Среднее арифметическое', 'mean')
        self.center_method_combo.addItem('Метод наименьших квадратов', 'lsq')
        self.center_method_combo.setToolTip('Метод определения центра пояса')
        methods_layout.addRow('Метод центрирования:', self.center_method_combo)
        
        calc_layout.addWidget(methods_group)
        
        # Группа: Допуски (только для информации)
        tolerances_group = QGroupBox('Нормативные допуски (только просмотр)')
        tolerances_layout = QFormLayout()
        tolerances_group.setLayout(tolerances_layout)
        
        vertical_label = QLabel('0.001 × h (СП 70.13330.2012)')
        vertical_label.setStyleSheet('color: #0066cc; font-weight: bold;')
        tolerances_layout.addRow('Вертикальность:', vertical_label)
        
        straight_label = QLabel('L / 750 (Инструкция 1980)')
        straight_label.setStyleSheet('color: #0066cc; font-weight: bold;')
        tolerances_layout.addRow('Прямолинейность:', straight_label)
        
        calc_layout.addWidget(tolerances_group)
        calc_layout.addStretch()
        
        tabs.addTab(calc_tab, 'Расчеты')
        
        # Вкладка 2: Интерфейс
        ui_tab = QWidget()
        ui_layout = QVBoxLayout()
        ui_tab.setLayout(ui_layout)
        
        # Группа: Настройки графиков
        plot_group = QGroupBox('Настройки графиков')
        plot_layout = QFormLayout()
        plot_group.setLayout(plot_layout)
        
        self.point_size_spin = QSpinBox()
        self.point_size_spin.setRange(20, 200)
        self.point_size_spin.setValue(100)
        self.point_size_spin.setToolTip('Размер точек на графиках')
        plot_layout.addRow('Размер точек:', self.point_size_spin)
        
        self.show_grid_check = QCheckBox()
        self.show_grid_check.setChecked(True)
        self.show_grid_check.setToolTip('Отображать сетку на графиках')
        plot_layout.addRow('Показывать сетку:', self.show_grid_check)
        
        self.show_legend_check = QCheckBox()
        self.show_legend_check.setChecked(True)
        self.show_legend_check.setToolTip('Отображать легенду на графиках')
        plot_layout.addRow('Показывать легенду:', self.show_legend_check)
        
        ui_layout.addWidget(plot_group)
        
        # Группа: Шрифты
        font_group = QGroupBox('Настройки шрифтов')
        font_layout = QFormLayout()
        font_group.setLayout(font_layout)
        
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(8, 20)
        self.font_size_spin.setValue(10)
        self.font_size_spin.setSuffix(' pt')
        self.font_size_spin.setToolTip('Размер шрифта интерфейса')
        font_layout.addRow('Размер шрифта:', self.font_size_spin)
        
        ui_layout.addWidget(font_group)
        ui_layout.addStretch()
        
        tabs.addTab(ui_tab, 'Интерфейс')
        
        # Вкладка 3: Экспорт
        export_tab = QWidget()
        export_layout = QVBoxLayout()
        export_tab.setLayout(export_layout)
        
        # Группа: Настройки экспорта
        export_settings_group = QGroupBox('Настройки экспорта по умолчанию')
        export_settings_layout = QFormLayout()
        export_settings_group.setLayout(export_settings_layout)
        
        self.default_export_format_combo = QComboBox()
        self.default_export_format_combo.addItem('PDF', 'pdf')
        self.default_export_format_combo.addItem('Excel', 'xlsx')
        self.default_export_format_combo.addItem('Word (DOCX)', 'docx')
        self.default_export_format_combo.addItem('CSV', 'csv')
        self.default_export_format_combo.addItem('GeoJSON', 'geojson')
        self.default_export_format_combo.addItem('KML', 'kml')
        export_settings_layout.addRow('Формат по умолчанию:', self.default_export_format_combo)
        
        export_layout.addWidget(export_settings_group)
        export_layout.addStretch()
        
        tabs.addTab(export_tab, 'Экспорт')
        
        # Вкладка 4: Управление настройками
        manage_tab = QWidget()
        manage_layout = QVBoxLayout()
        manage_tab.setLayout(manage_layout)
        
        manage_group = QGroupBox('Импорт/Экспорт настроек')
        manage_group_layout = QVBoxLayout()
        manage_group.setLayout(manage_group_layout)
        
        import_btn = QPushButton('📥 Импортировать настройки')
        import_btn.clicked.connect(self.import_settings)
        manage_group_layout.addWidget(import_btn)
        
        export_btn = QPushButton('📤 Экспортировать настройки')
        export_btn.clicked.connect(self.export_settings)
        manage_group_layout.addWidget(export_btn)
        
        manage_layout.addWidget(manage_group)
        manage_layout.addStretch()
        
        tabs.addTab(manage_tab, 'Управление')
        
        # Кнопки
        layout.addStretch()
        
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.RestoreDefaults
        )
        button_box.accepted.connect(self.on_accept)
        button_box.rejected.connect(self.reject)
        restore_button = button_box.button(QDialogButtonBox.StandardButton.RestoreDefaults)
        if restore_button:
            restore_button.setText('Сбросить\nнастройки')
            apply_compact_button_style(restore_button, width=110, min_height=48)
            restore_button.clicked.connect(self.restore_defaults)

        ok_button = button_box.button(QDialogButtonBox.StandardButton.Ok)
        cancel_button = button_box.button(QDialogButtonBox.StandardButton.Cancel)
        if ok_button:
            ok_button.setText('Сохранить')
            apply_compact_button_style(ok_button, width=104, min_height=34)
        if cancel_button:
            cancel_button.setText('Отмена')
            apply_compact_button_style(cancel_button, width=96, min_height=34)
        
        layout.addWidget(button_box)
    
    def load_settings(self):
        """Загружает сохраненные настройки"""
        try:
            # Загружаем настройки расчетов
            height_tolerance = self.settings_manager.load_setting('calculation/height_tolerance', 0.1)
            self.height_tolerance_spin.setValue(float(height_tolerance))
            
            center_method = self.settings_manager.load_setting('calculation/center_method', 'mean')
            self.set_center_method(center_method)
            
            # Загружаем настройки интерфейса
            font_size = self.settings_manager.load_setting('ui/font_size', 10)
            self.font_size_spin.setValue(int(font_size))
            
            point_size = self.settings_manager.load_setting('plot/point_size', 100)
            self.point_size_spin.setValue(int(point_size))
            
            show_grid = self.settings_manager.load_setting('plot/show_grid', True)
            self.show_grid_check.setChecked(bool(show_grid))
            
            show_legend = self.settings_manager.load_setting('plot/show_legend', True)
            self.show_legend_check.setChecked(bool(show_legend))
            
            # Загружаем настройки экспорта
            default_format = self.settings_manager.load_setting('export/default_format', 'pdf')
            for i in range(self.default_export_format_combo.count()):
                if self.default_export_format_combo.itemData(i) == default_format:
                    self.default_export_format_combo.setCurrentIndex(i)
                    break
        except Exception as e:
            logger.warning(f"Ошибка загрузки настроек: {e}")
    
    def on_accept(self):
        """Сохранение настроек при принятии диалога"""
        try:
            # Сохраняем настройки расчетов
            self.settings_manager.save_setting('calculation/height_tolerance', self.height_tolerance_spin.value())
            self.settings_manager.save_setting('calculation/center_method', self.get_center_method())
            
            # Сохраняем настройки интерфейса
            self.settings_manager.save_setting('ui/font_size', self.font_size_spin.value())
            self.settings_manager.save_setting('plot/point_size', self.point_size_spin.value())
            self.settings_manager.save_setting('plot/show_grid', self.show_grid_check.isChecked())
            self.settings_manager.save_setting('plot/show_legend', self.show_legend_check.isChecked())
            
            # Сохраняем настройки экспорта
            self.settings_manager.save_setting('export/default_format', self.default_export_format_combo.currentData())
            
            self.accept()
        except Exception as e:
            logger.error(f"Ошибка сохранения настроек: {e}", exc_info=True)
            QMessageBox.warning(self, 'Ошибка', f'Не удалось сохранить настройки:\n{str(e)}')
    
    def import_settings(self):
        """Импорт настроек из файла"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            'Импортировать настройки',
            '',
            'JSON файлы (*.json);;Все файлы (*.*)'
        )
        
        if file_path:
            try:
                self.settings_manager.import_settings(file_path, merge=True)
                self.load_settings()  # Перезагружаем настройки
                QMessageBox.information(self, 'Успех', 'Настройки успешно импортированы')
            except SettingsLoadError as e:
                QMessageBox.critical(self, 'Ошибка', f'Ошибка импорта настроек:\n{str(e)}')
    
    def export_settings(self):
        """Экспорт настроек в файл"""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            'Экспортировать настройки',
            'geovertical_settings.json',
            'JSON файлы (*.json);;Все файлы (*.*)'
        )
        
        if file_path:
            try:
                self.settings_manager.export_settings(file_path)
                QMessageBox.information(self, 'Успех', f'Настройки успешно экспортированы:\n{file_path}')
            except SettingsSaveError as e:
                QMessageBox.critical(self, 'Ошибка', f'Ошибка экспорта настроек:\n{str(e)}')
        
    def get_height_tolerance(self) -> float:
        """Возвращает допуск группировки по высоте"""
        return self.height_tolerance_spin.value()
    
    def set_height_tolerance(self, value: float):
        """Устанавливает допуск группировки по высоте"""
        self.height_tolerance_spin.setValue(value)
        
    def get_center_method(self) -> str:
        """Возвращает метод расчета центра"""
        return self.center_method_combo.currentData()
    
    def set_center_method(self, method: str):
        """Устанавливает метод расчета центра"""
        for i in range(self.center_method_combo.count()):
            if self.center_method_combo.itemData(i) == method:
                self.center_method_combo.setCurrentIndex(i)
                break
    
    def get_units(self) -> str:
        """Возвращает единицы измерения"""
        return self.units_combo.currentData()
    
    def get_plot_settings(self) -> dict:
        """Возвращает настройки графиков"""
        return {
            'point_size': self.point_size_spin.value(),
            'show_grid': self.show_grid_check.isChecked(),
            'show_legend': self.show_legend_check.isChecked()
        }
    
    def restore_defaults(self):
        """Восстанавливает настройки по умолчанию"""
        self.height_tolerance_spin.setValue(0.1)
        self.center_method_combo.setCurrentIndex(0)
        self.units_combo.setCurrentIndex(0)
        self.point_size_spin.setValue(100)
        self.show_grid_check.setChecked(True)
        self.show_legend_check.setChecked(True)

