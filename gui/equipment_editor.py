from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QPushButton, 
    QFormLayout, QLineEdit, QDoubleSpinBox, QGroupBox, QMessageBox
)
from typing import Dict, List

class EquipmentEditorWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.equipment_list: List[Dict] = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        
        # Left: List
        left_layout = QVBoxLayout()
        self.list_widget = QListWidget()
        self.list_widget.currentRowChanged.connect(self._on_selection_changed)
        left_layout.addWidget(self.list_widget)
        
        btn_layout = QHBoxLayout()
        add_btn = QPushButton("Добавить")
        add_btn.clicked.connect(self._add_item)
        del_btn = QPushButton("Удалить")
        del_btn.clicked.connect(self._del_item)
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(del_btn)
        left_layout.addLayout(btn_layout)
        
        layout.addLayout(left_layout, stretch=1)
        
        # Right: Details
        right_group = QGroupBox("Параметры оборудования")
        form = QFormLayout()
        
        self.name_edit = QLineEdit()
        self.name_edit.editingFinished.connect(self._save_current)
        form.addRow("Название:", self.name_edit)
        
        self.type_edit = QLineEdit() # Could be combo
        self.type_edit.setText("Antenna")
        self.type_edit.editingFinished.connect(self._save_current)
        form.addRow("Тип:", self.type_edit)
        
        self.height_spin = QDoubleSpinBox()
        self.height_spin.setRange(0, 500)
        self.height_spin.setSuffix(" м")
        self.height_spin.valueChanged.connect(self._save_current)
        form.addRow("Высота (Z):", self.height_spin)
        
        self.mass_spin = QDoubleSpinBox()
        self.mass_spin.setRange(0, 10000)
        self.mass_spin.setSuffix(" кг")
        self.mass_spin.valueChanged.connect(self._save_current)
        form.addRow("Масса:", self.mass_spin)
        
        self.area_spin = QDoubleSpinBox()
        self.area_spin.setRange(0, 100)
        self.area_spin.setDecimals(3)
        self.area_spin.setSuffix(" м²")
        self.area_spin.valueChanged.connect(self._save_current)
        form.addRow("Площадь (Ax/Ay):", self.area_spin)
        
        right_group.setLayout(form)
        layout.addWidget(right_group, stretch=1)

    def set_data(self, equipment_list: List[Dict]):
        self.equipment_list = equipment_list
        self._refresh_list()

    def _refresh_list(self):
        self.list_widget.clear()
        for item in self.equipment_list:
            self.list_widget.addItem(f"{item.get('name', 'Equipment')} ({item.get('height', 0)}m)")

    def _add_item(self):
        new_item = {
            "name": "Новое оборудование",
            "type": "Antenna",
            "height": 10.0,
            "mass": 10.0,
            "area_x": 0.5,
            "area_y": 0.5
        }
        self.equipment_list.append(new_item)
        self._refresh_list()
        self.list_widget.setCurrentRow(len(self.equipment_list) - 1)

    def _del_item(self):
        row = self.list_widget.currentRow()
        if row >= 0:
            self.equipment_list.pop(row)
            self._refresh_list()

    def _on_selection_changed(self, row):
        if row < 0 or row >= len(self.equipment_list):
            return
        item = self.equipment_list[row]
        self.name_edit.setText(item.get("name", ""))
        self.type_edit.setText(item.get("type", ""))
        self.height_spin.setValue(float(item.get("height", 0)))
        self.mass_spin.setValue(float(item.get("mass", 0)))
        self.area_spin.setValue(float(item.get("area_x", 0))) # Simplifying to square

    def _save_current(self):
        row = self.list_widget.currentRow()
        if row < 0 or row >= len(self.equipment_list):
            return
        item = self.equipment_list[row]
        item["name"] = self.name_edit.text()
        item["type"] = self.type_edit.text()
        item["height"] = self.height_spin.value()
        item["mass"] = self.mass_spin.value()
        item["area_x"] = self.area_spin.value()
        item["area_y"] = self.area_spin.value()
        
        # Update list item text
        self.list_widget.item(row).setText(f"{item['name']} ({item['height']}m)")
