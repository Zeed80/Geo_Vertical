"""
Мастер пошаговой генерации синтетической башни.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWizard,
    QWizardPage,
    QSpinBox,
)

from core.tower_generator import TowerSegmentSpec, TowerBlueprintV2
from gui.tower_preview_widget import TowerPreviewWidget


class SectionsPage(QWizardPage):
    """Страница редактирования секций для мастера."""

    def __init__(self, wizard: TowerBuilderWizard, blueprint: TowerBlueprintV2):
        super().__init__(wizard)
        self.setTitle("Настройка секций")
        self._wizard = wizard
        self._blueprint = blueprint

        self.sections_table = QTableWidget(0, 8)
        self.sections_table.setHorizontalHeaderLabels(
            [
                "Название",
                "Высота (м)",
                "Поясов",
                "Форма",
                "Граней",
                "Нижний размер (м)",
                "Верхний размер (м)",
                "Девиация (мм)",
            ]
        )
        self.sections_table.setEditTriggers(
            QAbstractItemView.EditTrigger.AllEditTriggers
        )
        self.sections_table.horizontalHeader().setStretchLastSection(True)

        self.preview = TowerPreviewWidget()

        self.total_height_label = QLabel()

        buttons_layout = QHBoxLayout()
        add_button = QPushButton("Добавить секцию")
        remove_button = QPushButton("Удалить секцию")
        add_button.clicked.connect(self._add_section_row)
        remove_button.clicked.connect(self._remove_section_row)
        buttons_layout.addWidget(add_button)
        buttons_layout.addWidget(remove_button)
        buttons_layout.addStretch()
        buttons_layout.addWidget(self.total_height_label)

        table_layout = QVBoxLayout()
        table_layout.addWidget(self.sections_table)
        table_layout.addLayout(buttons_layout)

        grid = QGridLayout()
        grid.addLayout(table_layout, 0, 0)
        grid.addWidget(self.preview, 0, 1)
        grid.setColumnStretch(0, 3)
        grid.setColumnStretch(1, 2)
        self.setLayout(grid)

        self.sections_table.itemChanged.connect(self._on_table_changed)

        if blueprint.segments:
            for segment in blueprint.segments:
                self._add_section_row(
                    {
                        "name": segment.name,
                        "height": segment.height,
                        "levels": segment.levels,
                        "shape": segment.shape,
                        "faces": segment.faces,
                        "lower_size": segment.base_size,
                        "upper_size": segment.top_size if segment.top_size is not None else segment.base_size,
                        "deviation_mm": segment.deviation_mm,
                    }
                )
        else:
            self._add_section_row(
                {
                    "name": "Часть 1",
                    "height": 5.0,
                    "levels": 1,
                    "shape": "prism",
                    "faces": 4,
                    "lower_size": 4.0,
                    "upper_size": 4.0,
                    "deviation_mm": blueprint.default_deviation_mm,
                }
            )
        self._recalculate_total_height()

    def _add_section_row(self, section: Optional[Dict[str, float]] = None):
        row = self.sections_table.rowCount()
        self.sections_table.insertRow(row)

        defaults = {
            "name": f"Часть {row + 1}",
            "height": 5.0,
            "levels": 1,
            "shape": "prism",
            "faces": 4,
            "lower_size": 4.0,
            "upper_size": 4.0,
            "deviation_mm": 0.0,
        }
        if section:
            defaults.update(section)

        self.sections_table.setItem(row, 0, QTableWidgetItem(str(defaults["name"])))
        self.sections_table.setItem(row, 1, QTableWidgetItem(f"{float(defaults['height']):.3f}"))
        self.sections_table.setItem(row, 2, QTableWidgetItem(str(int(defaults["levels"]))))

        shape_combo = QComboBox()
        shape_combo.addItem("Призма", "prism")
        shape_combo.addItem("Усеченная пирамида", "truncated_pyramid")
        shape_combo.setCurrentIndex(shape_combo.findData(defaults["shape"]))
        shape_combo.currentIndexChanged.connect(self._on_table_changed)
        self.sections_table.setCellWidget(row, 3, shape_combo)

        faces_spin = QSpinBox()
        faces_spin.setRange(3, 64)
        faces_spin.setValue(int(defaults.get("faces", 4)))
        faces_spin.valueChanged.connect(self._on_table_changed)
        self.sections_table.setCellWidget(row, 4, faces_spin)

        base_item = QTableWidgetItem(f"{float(defaults['lower_size']):.3f}")
        top_item = QTableWidgetItem(f"{float(defaults['upper_size']):.3f}")
        dev_item = QTableWidgetItem(f"{float(defaults['deviation_mm']):.3f}")
        self.sections_table.setItem(row, 5, base_item)
        self.sections_table.setItem(row, 6, top_item)
        self.sections_table.setItem(row, 7, dev_item)

        self._recalculate_total_height()

    def _remove_section_row(self):
        row = self.sections_table.currentRow()
        if row < 0:
            return
        self.sections_table.removeRow(row)
        self._recalculate_total_height()
        self._wizard.notify_configuration_changed()

    def _on_table_changed(self, *_args):
        self.completeChanged.emit()
        self._recalculate_total_height()
        self._wizard.notify_configuration_changed()

    def _recalculate_total_height(self):
        total = 0.0
        for row in range(self.sections_table.rowCount()):
            item = self.sections_table.item(row, 1)
            if item is None:
                continue
            try:
                total += float(item.text())
            except (TypeError, ValueError):
                continue
        self.total_height_label.setText(f"Суммарная высота секций: {total:.2f} м")

    def get_sections(self) -> List[Dict[str, float]]:
        sections: List[Dict[str, float]] = []
        if self.sections_table.rowCount() == 0:
            raise ValueError("Добавьте хотя бы одну секцию")
        for row in range(self.sections_table.rowCount()):
            shape_widget = self.sections_table.cellWidget(row, 3)
            shape = (
                shape_widget.currentData()
                if isinstance(shape_widget, QComboBox)
                else "prism"
            )
            faces_widget = self.sections_table.cellWidget(row, 4)
            faces_value = faces_widget.value() if isinstance(faces_widget, QSpinBox) else 4
            lower = self._safe_optional_float(row, 5) or 1.0
            upper = self._safe_optional_float(row, 6) or lower
            deviation = self._safe_optional_float(row, 7) or 0.0
            section = {
                "name": self._safe_text(row, 0) or f"Часть {row + 1}",
                "height": self._safe_float(row, 1, default=1.0),
                "levels": max(1, int(self._safe_float(row, 2, default=1.0))),
                "shape": shape,
                "faces": faces_value,
                "lower_size": lower,
                "upper_size": upper,
                "deviation_mm": deviation,
            }
            if section["height"] <= 0:
                raise ValueError(f"Высота секции '{section['name']}' должна быть > 0")
            sections.append(section)
        return sections

    def _safe_text(self, row: int, column: int) -> str:
        item = self.sections_table.item(row, column)
        return item.text().strip() if item else ""

    def _safe_float(self, row: int, column: int, default: float) -> float:
        item = self.sections_table.item(row, column)
        if not item or not item.text().strip():
            return default
        return float(item.text())

    def _safe_optional_float(self, row: int, column: int) -> Optional[float]:
        item = self.sections_table.item(row, column)
        if not item:
            return None
        text = item.text().strip()
        if not text:
            return None
        return float(text)

    def update_preview(self, blueprint: TowerBlueprintV2):
        self.preview.update_preview(blueprint)


class SummaryPage(QWizardPage):
    """Финальное подтверждение."""

    def __init__(self, wizard: TowerBuilderWizard):
        super().__init__(wizard)
        self.setTitle("Подтверждение конфигурации")
        self.summary_label = QLabel()
        self.summary_label.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.summary_label.setWordWrap(True)

        layout = QVBoxLayout()
        layout.addWidget(self.summary_label)
        layout.addStretch()
        self.setLayout(layout)

    def update_summary(self, blueprint: Optional[TowerBlueprintV2]):
        if not blueprint:
            self.summary_label.setText("Параметры недоступны.")
            return
        parts = "\n".join(
            f"- {segment.name}: {segment.height:.2f} м, форма {segment.shape}, поясов {segment.levels}, граней {segment.faces}"
            for segment in blueprint.segments
        )
        self.summary_label.setText(
            "Башня будет создана со следующими параметрами:\n"
            f"• Высота: {blueprint.total_height():.2f} м\n"
            f"• Прибор: расстояние {blueprint.instrument_distance:.1f} м, угол {blueprint.instrument_angle_deg:.1f}°, высота {blueprint.instrument_height:.2f} м\n\n"
            f"Части:\n{parts}"
        )


class TowerBuilderWizard(QWizard):
    """Простой мастер конфигурации башни."""

    def __init__(
        self,
        *,
        blueprint: Optional[TowerBlueprintV2] = None,
        parent: Optional[QWizard] = None,
    ):
        super().__init__(parent)
        default_blueprint = TowerBlueprintV2(
            segments=[
                TowerSegmentSpec(
                    name="Часть 1",
                    shape="prism",
                    faces=4,
                    height=5.0,
                    levels=1,
                    base_size=4.0,
                    top_size=4.0,
                )
            ]
        )
        self._source_blueprint = blueprint or default_blueprint
        self._current_blueprint: Optional[TowerBlueprintV2] = None

        self.sections_page = SectionsPage(self, self._source_blueprint)
        self.summary_page = SummaryPage(self)
        self.addPage(self.sections_page)
        self.addPage(self.summary_page)

        self.setWindowTitle("Мастер конструирования башни")
        self.setOption(QWizard.WizardOption.NoBackButtonOnStartPage, True)

        self.notify_configuration_changed()

    def _build_blueprint(self) -> TowerBlueprintV2:
        sections_data = self.sections_page.get_sections()
        segment_specs = [
            TowerSegmentSpec(
                name=data["name"],
                shape=data["shape"],
                faces=int(data["faces"]),
                height=float(data["height"]),
                levels=max(1, int(data["levels"])),
                base_size=float(data["lower_size"]),
                top_size=float(data["upper_size"]),
                deviation_mm=float(data["deviation_mm"]),
            )
            for data in sections_data
        ]
        blueprint = TowerBlueprintV2(
            segments=segment_specs,
            instrument_distance=self._source_blueprint.instrument_distance,
            instrument_angle_deg=self._source_blueprint.instrument_angle_deg,
            instrument_height=self._source_blueprint.instrument_height,
            base_rotation_deg=self._source_blueprint.base_rotation_deg,
            default_deviation_mm=self._source_blueprint.default_deviation_mm,
        )
        blueprint.validate()
        return blueprint

    def notify_configuration_changed(self):
        try:
            blueprint = self._build_blueprint()
        except Exception:
            self._current_blueprint = None
            self.sections_page.preview.reset()
            self.summary_page.update_summary(None)
            return

        self._current_blueprint = blueprint
        self.sections_page.update_preview(blueprint)
        self.summary_page.update_summary(blueprint)

    def current_blueprint(self) -> Optional[TowerBlueprintV2]:
        return self._current_blueprint

    def accept(self):
        if not self._current_blueprint:
            QMessageBox.warning(
                self,
                "Ошибка конфигурации",
                "Невозможно завершить мастер: исправьте параметры секций.",
            )
            return
        super().accept()
