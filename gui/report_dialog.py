"""
Диалог для ввода информации перед генерацией отчета
"""

from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
                             QLabel, QLineEdit, QPushButton, QTextEdit,
                             QDialogButtonBox, QGroupBox, QDateEdit, QComboBox)
from PyQt6.QtCore import QDate

from gui.ui_helpers import apply_compact_button_style

class ReportInfoDialog(QDialog):
    """Диалог для ввода информации об отчете"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Информация для отчета')
        self.setModal(True)
        self.resize(600, 500)
        self.init_ui()
        
    def init_ui(self):
        """Инициализация интерфейса"""
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        # Группа: Информация об объекте
        object_group = QGroupBox('Информация об объекте')
        object_layout = QFormLayout()
        object_group.setLayout(object_layout)
        
        self.project_name_edit = QLineEdit()
        self.project_name_edit.setPlaceholderText('Например: Мачта связи №5, высота 50 м')
        self.project_name_edit.setText('Антенно-мачтовое сооружение')
        object_layout.addRow('Наименование объекта:', self.project_name_edit)
        
        self.location_edit = QLineEdit()
        self.location_edit.setPlaceholderText('Адрес или координаты')
        object_layout.addRow('Местоположение:', self.location_edit)
        
        self.object_type_combo = QComboBox()
        self.object_type_combo.addItems([
            'Мачта связи',
            'Радиомачта',
            'Телевизионная мачта',
            'Антенная опора',
            'Прочее'
        ])
        object_layout.addRow('Тип сооружения:', self.object_type_combo)
        
        layout.addWidget(object_group)
        
        # Группа: Организация
        org_group = QGroupBox('Организация')
        org_layout = QFormLayout()
        org_group.setLayout(org_layout)
        
        self.organization_edit = QLineEdit()
        self.organization_edit.setPlaceholderText('Название организации')
        org_layout.addRow('Организация:', self.organization_edit)
        
        self.executor_edit = QLineEdit()
        self.executor_edit.setPlaceholderText('ФИО исполнителя')
        org_layout.addRow('Исполнитель:', self.executor_edit)
        
        self.position_edit = QLineEdit()
        self.position_edit.setPlaceholderText('Должность')
        org_layout.addRow('Должность:', self.position_edit)
        
        layout.addWidget(org_group)
        
        # Группа: Дата обследования
        date_group = QGroupBox('Дата обследования')
        date_layout = QFormLayout()
        date_group.setLayout(date_layout)
        
        self.survey_date = QDateEdit()
        self.survey_date.setDate(QDate.currentDate())
        self.survey_date.setCalendarPopup(True)
        self.survey_date.setDisplayFormat('dd.MM.yyyy')
        date_layout.addRow('Дата:', self.survey_date)
        
        layout.addWidget(date_group)
        
        # Группа: Примечания
        notes_group = QGroupBox('Примечания')
        notes_layout = QVBoxLayout()
        notes_group.setLayout(notes_layout)
        
        self.notes_edit = QTextEdit()
        self.notes_edit.setPlaceholderText(
            'Дополнительная информация, особые условия измерений, '
            'погодные условия и т.д.'
        )
        self.notes_edit.setMaximumHeight(100)
        notes_layout.addWidget(self.notes_edit)
        
        layout.addWidget(notes_group)
        
        # Кнопки
        layout.addStretch()
        
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
        
        # Кнопка "Очистить"
        clear_btn = QPushButton('Очистить\nвсе')
        clear_btn.clicked.connect(self.clear_all)
        apply_compact_button_style(clear_btn, width=90, min_height=46)
        button_box.addButton(clear_btn, QDialogButtonBox.ResetRole)
        
        layout.addWidget(button_box)
        
    def get_report_info(self) -> dict:
        """Возвращает введенную информацию"""
        return {
            'project_name': self.project_name_edit.text() or 'Объект контроля',
            'location': self.location_edit.text(),
            'object_type': self.object_type_combo.currentText(),
            'organization': self.organization_edit.text(),
            'executor': self.executor_edit.text(),
            'position': self.position_edit.text(),
            'survey_date': self.survey_date.date().toString('dd.MM.yyyy'),
            'notes': self.notes_edit.toPlainText()
        }
    
    def clear_all(self):
        """Очищает все поля"""
        self.project_name_edit.setText('Антенно-мачтовое сооружение')
        self.location_edit.clear()
        self.object_type_combo.setCurrentIndex(0)
        self.organization_edit.clear()
        self.executor_edit.clear()
        self.position_edit.clear()
        self.survey_date.setDate(QDate.currentDate())
        self.notes_edit.clear()

