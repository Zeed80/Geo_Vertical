"""Interactive dialog for model-based completion of missing vertical face tracks."""

from __future__ import annotations

from typing import Any

import pandas as pd
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from core.face_track_completion import (
    CompletionPartSpec,
    FaceTrackCompleter,
    build_completion_part_specs,
)


class BeltCompletionDialog(QDialog):
    def __init__(
        self,
        data: pd.DataFrame,
        *,
        blueprint: Any | None = None,
        suggested_faces: int | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._data = data.copy()
        self._blueprint = blueprint
        self._suggested_faces = suggested_faces
        self._completer: FaceTrackCompleter | None = None

        self.setWindowTitle("Достройка пояса")
        self.setMinimumSize(760, 560)

        self._setup_ui()
        self._load_initial_parts()
        self._refresh_analysis()

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(10)

        parts_group = QGroupBox("Геометрия частей")
        parts_layout = QVBoxLayout(parts_group)

        self._parts_table = QTableWidget(0, 6)
        self._parts_table.setHorizontalHeaderLabels(["Часть", "Z min", "Z max", "Тип", "Граней", "Источник"])
        self._parts_table.verticalHeader().setVisible(False)
        self._parts_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._parts_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._parts_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self._parts_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._parts_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        parts_layout.addWidget(self._parts_table)

        parts_buttons = QHBoxLayout()
        self._auto_btn = QPushButton("Автоанализ")
        self._auto_btn.clicked.connect(self._load_initial_parts)
        parts_buttons.addWidget(self._auto_btn)
        self._add_btn = QPushButton("Добавить часть")
        self._add_btn.clicked.connect(self._add_part_row)
        parts_buttons.addWidget(self._add_btn)
        self._remove_btn = QPushButton("Удалить часть")
        self._remove_btn.clicked.connect(self._remove_selected_part)
        parts_buttons.addWidget(self._remove_btn)
        parts_buttons.addStretch()
        parts_layout.addLayout(parts_buttons)
        root.addWidget(parts_group)

        preview_group = QGroupBox("Предпросмотр достройки")
        preview_layout = QVBoxLayout(preview_group)

        options_form = QFormLayout()
        self._z_method_combo = QComboBox()
        self._z_method_combo.addItem("По противоположному поясу", "diagonal")
        self._z_method_combo.addItem("Среднее по уровню", "mean")
        self._z_method_combo.currentIndexChanged.connect(self._refresh_analysis)
        options_form.addRow("Z новой точки:", self._z_method_combo)
        preview_layout.addLayout(options_form)

        self._summary_label = QLabel()
        self._summary_label.setWordWrap(True)
        preview_layout.addWidget(self._summary_label)

        self._analysis_table = QTableWidget(0, 7)
        self._analysis_table.setHorizontalHeaderLabels(
            ["Часть", "Тип", "Граней", "Уровней", "Есть треки", "Достроить", "Точек"]
        )
        self._analysis_table.verticalHeader().setVisible(False)
        self._analysis_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._analysis_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._analysis_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self._analysis_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self._analysis_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        preview_layout.addWidget(self._analysis_table)

        root.addWidget(preview_group)

        button_row = QHBoxLayout()
        self._recalc_btn = QPushButton("Обновить")
        self._recalc_btn.clicked.connect(self._refresh_analysis)
        button_row.addWidget(self._recalc_btn)
        button_row.addStretch()
        self._button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._button_box.button(QDialogButtonBox.StandardButton.Ok).setText("Достроить")
        self._button_box.accepted.connect(self._on_accept)
        self._button_box.rejected.connect(self.reject)
        button_row.addWidget(self._button_box)
        root.addLayout(button_row)

    def _load_initial_parts(self) -> None:
        default_faces = int(self._suggested_faces or 0) or None
        specs = build_completion_part_specs(
            self._data,
            blueprint=self._blueprint,
            default_faces=default_faces,
        )
        self._parts_table.setRowCount(0)
        for spec in specs:
            self._append_part_spec(spec)
        self._refresh_analysis()

    def _append_part_spec(self, spec: CompletionPartSpec) -> None:
        row = self._parts_table.rowCount()
        self._parts_table.insertRow(row)

        label_item = QTableWidgetItem(str(spec.part_number))
        label_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self._parts_table.setItem(row, 0, label_item)

        z_min_spin = QDoubleSpinBox()
        z_min_spin.setRange(-1000.0, 10000.0)
        z_min_spin.setDecimals(3)
        z_min_spin.setValue(float(spec.z_min))
        z_min_spin.valueChanged.connect(self._refresh_analysis)
        self._parts_table.setCellWidget(row, 1, z_min_spin)

        z_max_spin = QDoubleSpinBox()
        z_max_spin.setRange(-1000.0, 10000.0)
        z_max_spin.setDecimals(3)
        z_max_spin.setValue(float(spec.z_max))
        z_max_spin.valueChanged.connect(self._refresh_analysis)
        self._parts_table.setCellWidget(row, 2, z_max_spin)

        shape_combo = QComboBox()
        shape_combo.addItem("Призма", "prism")
        shape_combo.addItem("Усеченная пирамида", "truncated_pyramid")
        shape_combo.setCurrentIndex(0 if spec.shape == "prism" else 1)
        shape_combo.currentIndexChanged.connect(self._refresh_analysis)
        self._parts_table.setCellWidget(row, 3, shape_combo)

        faces_spin = QSpinBox()
        faces_spin.setRange(3, 16)
        faces_spin.setValue(int(spec.faces))
        faces_spin.valueChanged.connect(self._refresh_analysis)
        self._parts_table.setCellWidget(row, 4, faces_spin)

        source_item = QTableWidgetItem(str(spec.source))
        source_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self._parts_table.setItem(row, 5, source_item)

    def _add_part_row(self) -> None:
        last_z = 0.0
        if self._parts_table.rowCount():
            last_widget = self._parts_table.cellWidget(self._parts_table.rowCount() - 1, 2)
            if isinstance(last_widget, QDoubleSpinBox):
                last_z = float(last_widget.value())
        faces = int(self._suggested_faces or 4)
        self._append_part_spec(
            CompletionPartSpec(
                part_number=self._parts_table.rowCount() + 1,
                z_min=last_z,
                z_max=last_z + 10.0,
                shape="prism",
                faces=faces,
                source="manual",
            )
        )
        self._refresh_analysis()

    def _remove_selected_part(self) -> None:
        selected_rows = sorted({index.row() for index in self._parts_table.selectionModel().selectedRows()}, reverse=True)
        for row in selected_rows:
            self._parts_table.removeRow(row)
        self._renumber_rows()
        self._refresh_analysis()

    def _renumber_rows(self) -> None:
        for row in range(self._parts_table.rowCount()):
            item = self._parts_table.item(row, 0)
            if item is None:
                item = QTableWidgetItem()
                self._parts_table.setItem(row, 0, item)
            item.setText(str(row + 1))

    def _collect_specs(self) -> list[CompletionPartSpec]:
        specs: list[CompletionPartSpec] = []
        for row in range(self._parts_table.rowCount()):
            z_min_widget = self._parts_table.cellWidget(row, 1)
            z_max_widget = self._parts_table.cellWidget(row, 2)
            shape_widget = self._parts_table.cellWidget(row, 3)
            faces_widget = self._parts_table.cellWidget(row, 4)
            specs.append(
                CompletionPartSpec(
                    part_number=row + 1,
                    z_min=float(z_min_widget.value()),
                    z_max=float(z_max_widget.value()),
                    shape=str(shape_widget.currentData()),
                    faces=int(faces_widget.value()),
                    label=f"Part {row + 1}",
                    source=str(self._parts_table.item(row, 5).text() if self._parts_table.item(row, 5) else "manual"),
                )
            )
        return specs

    def _refresh_analysis(self) -> None:
        try:
            specs = self._collect_specs()
            completer = FaceTrackCompleter(self._data, specs)
            analysis = completer.analyze()
        except Exception as exc:
            self._summary_label.setText(f"Ошибка конфигурации: {exc}")
            self._analysis_table.setRowCount(0)
            self._button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
            return

        total_points = sum(item["points_to_add"] for item in analysis)
        if not analysis or total_points <= 0:
            self._summary_label.setText("Новые точки не требуются: в выбранной конфигурации отсутствует глобально пропущенный пояс.")
            self._button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        else:
            self._summary_label.setText(f"Будет добавлено {total_points} точек по {len(analysis)} частям.")
            self._button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(True)

        self._analysis_table.setRowCount(len(analysis))
        for row, item in enumerate(analysis):
            values = [
                str(item["part_number"]),
                str(item["shape"]),
                str(item["faces"]),
                str(item["level_count"]),
                ", ".join(str(track) for track in item["observed_tracks"]) or "—",
                ", ".join(str(track) for track in item["missing_tracks"]) or "—",
                str(item["points_to_add"]),
            ]
            for col, value in enumerate(values):
                table_item = QTableWidgetItem(value)
                if col in (0, 2, 3, 6):
                    table_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._analysis_table.setItem(row, col, table_item)

    def _on_accept(self) -> None:
        specs = self._collect_specs()
        self._completer = FaceTrackCompleter(self._data, specs)
        self.accept()

    @property
    def completer(self) -> FaceTrackCompleter | None:
        return self._completer

    @property
    def z_method(self) -> str:
        return str(self._z_method_combo.currentData() or "diagonal")
