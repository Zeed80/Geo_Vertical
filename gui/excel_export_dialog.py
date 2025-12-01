"""
Диалог параметров экспорта в Excel
"""

from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout,
                             QLabel, QCheckBox, QDialogButtonBox,
                             QGroupBox, QSpinBox)
from PyQt6.QtCore import Qt

from gui.ui_helpers import apply_compact_button_style


class ExcelExportDialog(QDialog):
    """Диалог для настройки параметров экспорта в Excel"""
    
    def __init__(self, parent=None, has_angular_data: bool = False):
        super().__init__(parent)
        self.setWindowTitle('Параметры экспорта в Excel')
        self.setModal(True)
        self.resize(400, 300)
        self.has_angular_data = has_angular_data
        self.init_ui()
        
    def init_ui(self):
        """Инициализация интерфейса"""
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        # Группа: Листы для экспорта
        sheets_group = QGroupBox('Включаемые листы')
        sheets_layout = QVBoxLayout()
        sheets_group.setLayout(sheets_layout)
        
        self.include_results_check = QCheckBox('Результаты расчетов')
        self.include_results_check.setChecked(True)
        self.include_results_check.setEnabled(False)  # Всегда включен
        sheets_layout.addWidget(self.include_results_check)
        
        self.include_normatives_check = QCheckBox('Нормативы и выводы')
        self.include_normatives_check.setChecked(True)
        self.include_normatives_check.setEnabled(False)  # Всегда включен
        sheets_layout.addWidget(self.include_normatives_check)
        
        self.include_angular_check = QCheckBox('Журнал угловых измерений')
        self.include_angular_check.setChecked(self.has_angular_data)
        self.include_angular_check.setEnabled(self.has_angular_data)
        if not self.has_angular_data:
            self.include_angular_check.setToolTip('Нет данных угловых измерений')
        sheets_layout.addWidget(self.include_angular_check)
        
        layout.addWidget(sheets_group)
        
        # Группа: Параметры таблицы журнала угловых измерений
        if self.has_angular_data:
            angular_group = QGroupBox('Параметры журнала угловых измерений')
            angular_layout = QFormLayout()
            angular_group.setLayout(angular_layout)
            
            # Информация о количестве столбцов (фиксировано)
            columns_label = QLabel('11 столбцов (фиксированная структура)')
            columns_label.setStyleSheet('color: #666; font-style: italic;')
            angular_layout.addRow('Количество столбцов:', columns_label)
            
            layout.addWidget(angular_group)
        
        # Информационное сообщение
        info_label = QLabel(
            'Все таблицы будут экспортированы с границами ячеек.\n'
            'Ширина столбцов оптимизирована автоматически.'
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet('color: #555; padding: 10px; background-color: #f0f0f0; border-radius: 5px;')
        layout.addWidget(info_label)
        
        layout.addStretch()
        
        # Кнопки
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        ok_button = button_box.button(QDialogButtonBox.StandardButton.Ok)
        cancel_button = button_box.button(QDialogButtonBox.StandardButton.Cancel)
        if ok_button:
            apply_compact_button_style(ok_button, width=96, min_height=34)
        if cancel_button:
            apply_compact_button_style(cancel_button, width=96, min_height=34)
        
        layout.addWidget(button_box)
        
    def get_options(self) -> dict:
        """Возвращает выбранные опции экспорта"""
        return {
            'include_results': self.include_results_check.isChecked(),
            'include_normatives': self.include_normatives_check.isChecked(),
            'include_angular': self.include_angular_check.isChecked() if self.has_angular_data else False,
        }
