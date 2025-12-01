from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QFormLayout, 
    QComboBox, QPushButton, QLabel, QTextEdit, QMessageBox,
    QFileDialog
)
from PyQt6.QtCore import pyqtSignal
import numpy as np

from core.tower_generator import TowerBlueprintV2
from core.structure.model import TowerModel, MemberType
from core.physics.wind_load import WindLoadCalculator, WIND_ZONES, TERRAIN_COEFFS
from core.structure.builder import TowerModelBuilder

class CalculationTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.blueprint: TowerBlueprintV2 = None
        self.calculator: WindLoadCalculator = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Inputs
        input_group = QGroupBox("Параметры расчета (SP 20.13330.2016)")
        form = QFormLayout()
        
        self.zone_combo = QComboBox()
        for z in WIND_ZONES.keys():
            self.zone_combo.addItem(f"Ветровой район {z} ({WIND_ZONES[z]} кПа)", z)
        form.addRow("Ветровой район:", self.zone_combo)
        
        self.terrain_combo = QComboBox()
        for t in TERRAIN_COEFFS.keys():
            desc = "Открытое побережье" if t == 'A' else "Город/Лес" if t == 'B' else "Плотная застройка"
            self.terrain_combo.addItem(f"Тип местности {t} ({desc})", t)
        form.addRow("Тип местности:", self.terrain_combo)
        
        input_group.setLayout(form)
        layout.addWidget(input_group)
        
        # Buttons
        btn_layout = QHBoxLayout()
        calc_btn = QPushButton("Выполнить расчет")
        calc_btn.clicked.connect(self._run_calculation)
        btn_layout.addWidget(calc_btn)
        
        export_btn = QPushButton("Экспорт отчета (PDF)")
        export_btn.clicked.connect(self._export_report)
        btn_layout.addWidget(export_btn)
        layout.addLayout(btn_layout)
        
        # Results
        result_group = QGroupBox("Результаты")
        res_layout = QVBoxLayout()
        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        res_layout.addWidget(self.result_text)
        result_group.setLayout(res_layout)
        layout.addWidget(result_group, stretch=1)

    def set_blueprint(self, blueprint: TowerBlueprintV2):
        self.blueprint = blueprint
        self.result_text.clear()
        self.result_text.append("Чертеж загружен. Нажмите 'Выполнить расчет'.")

    def _run_calculation(self):
        if not self.blueprint:
            QMessageBox.warning(self, "Ошибка", "Нет чертежа башни.")
            return
            
        self.result_text.append("Построение модели...")
        builder = TowerModelBuilder(self.blueprint)
        model = builder.build()
        self.result_text.append(f"Модель построена: {len(model.nodes)} узлов, {len(model.members)} элементов.")
        
        zone = self.zone_combo.currentData()
        terrain = self.terrain_combo.currentData()
        
        self.result_text.append("Выполнение расчета...")
        calc = WindLoadCalculator(model)
        res = calc.calculate(zone, terrain)
        
        # Display
        f1 = res.natural_frequencies[0] if res.natural_frequencies else 0.0
        max_load = np.max(np.abs(res.total_load))
        total_force = np.sum(res.total_load)
        
        msg = f"""
<b>Результаты расчета:</b><br>
Ветровой район: {zone}<br>
Тип местности: {terrain}<br>
<br>
<b>Собственные частоты:</b><br>
1-я частота: {f1:.3f} Гц<br>
2-я частота: {res.natural_frequencies[1] if len(res.natural_frequencies)>1 else 0:.3f} Гц<br>
<br>
<b>Нагрузки:</b><br>
Максимальная узловая нагрузка: {max_load:.1f} Н<br>
Суммарная ветровая нагрузка: {total_force/1000:.2f} кН<br>
"""
        self.result_text.append(msg)
        self.last_result = res # Save for export

    def _export_report(self):
        if not hasattr(self, 'last_result'):
            QMessageBox.warning(self, "Ошибка", "Сначала выполните расчет.")
            return
            
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить отчет", "report.pdf", "PDF Files (*.pdf)")
        if path:
            from core.exporters.calculation_report import generate_pdf_report
            try:
                generate_pdf_report(path, self.last_result, self.blueprint)
                QMessageBox.information(self, "Успех", f"Отчет сохранен: {path}")
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Не удалось создать отчет: {e}")
