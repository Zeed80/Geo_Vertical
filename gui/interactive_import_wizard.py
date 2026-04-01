"""Interactive import wizard with explicit review/confirmation steps."""

from __future__ import annotations

import copy
from typing import Any, Dict

import pandas as pd
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFrame,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QAbstractItemView,
)

from core.interactive_import import (
    InteractiveImportThresholds,
    apply_interactive_corrections,
    apply_section_review_selection,
    build_interactive_correction_review,
    build_section_review,
)
from core.point_utils import build_working_tower_mask
from gui.data_import_wizard import DataImportWizard
from gui.ui_helpers import apply_compact_button_style


class InteractiveImportWizard(DataImportWizard):
    """Extended import wizard that adds correction and section review steps."""

    def __init__(
        self,
        data: pd.DataFrame,
        saved_settings: dict | None = None,
        parent=None,
        import_payload: Dict[str, Any] | None = None,
    ):
        self.total_steps = 4
        self.interactive_thresholds = InteractiveImportThresholds()
        self.interactive_base_data = pd.DataFrame()
        self.corrected_preview_data = pd.DataFrame()
        self.confirmed_section_data: list[dict[str, Any]] = []
        self.correction_review: dict[str, Any] = {}
        self.section_review: dict[str, Any] = {}
        self.applied_corrections: list[dict[str, Any]] = []
        self.rejected_corrections: list[dict[str, Any]] = []
        self.accepted_generated_sections: list[dict[str, Any]] = []
        self.selected_correction_rows: set[int] = set()
        self.selected_generated_sections: set[int] = set()
        self.interactive_sorting_snapshot: dict[str, Any] = {}
        self.import_mode = "interactive"
        super().__init__(
            data,
            saved_settings=saved_settings,
            parent=parent,
            import_payload=import_payload,
        )
        self.setWindowTitle("Интерактивный импорт данных")

        self.title_label.setWordWrap(True)
        self._install_steps_scroll_area()
        self.setMinimumSize(1100, 760)
        self.resize(1220, 860)

    def show_step_1(self):
        super().show_step_1()
        self.next_btn.setEnabled(True)
        self.title_label.setText("Шаг 1 из 4: Анализ файла и подтверждение конструкции")
        self.next_btn.setText("Далее →")
        self._inject_interactive_step_banner(
            "Режим интерактивного импорта: структура, грани, исправления точек и секции "
            "подтверждаются пользователем до загрузки данных в проект."
        )
        self._finalize_step_view()

    def show_step_2(self):
        super().show_step_2()
        self.next_btn.setEnabled(True)
        self.title_label.setText("Шаг 2 из 4: Подтверждение стоянки и распределения по граням")
        self.next_btn.setText("Далее →")
        self._inject_interactive_step_banner(
            "Проверьте стоянку и раскладку по поясам. На следующем шаге мастер покажет "
            "кандидатов на исправление геометрии точек, но не применит их без отметки."
        )
        self._finalize_step_view()

    def show_step_3(self):
        self.current_step = 3
        self.title_label.setText("Шаг 3 из 4: Подтверждение исправлений точек")
        self.back_btn.setEnabled(True)
        self.next_btn.setEnabled(True)
        self.next_btn.setText("Далее →")
        self.clear_steps_container()

        layout = self.steps_layout
        info = QLabel(
            "Ни одна коррекция не применяется автоматически. Отметьте только те предложения, "
            "которые хотите принять, затем переходите к подтверждению секций."
        )
        info.setWordWrap(True)
        info.setStyleSheet(self._info_box_style())
        layout.addWidget(info)

        threshold_group = QGroupBox("Пороги предложений")
        threshold_group.setStyleSheet(
            "QGroupBox { font-size: 9pt; margin-top: 4px; } "
            "QGroupBox::title { subcontrol-origin: margin; left: 6px; padding: 0 4px; }"
        )
        threshold_layout = QFormLayout()
        threshold_layout.setContentsMargins(6, 8, 6, 6)
        threshold_layout.setSpacing(4)
        threshold_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)
        threshold_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        threshold_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        threshold_layout.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        threshold_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.z_snap_spin = QDoubleSpinBox()
        self.z_snap_spin.setRange(0.01, 1.0)
        self.z_snap_spin.setDecimals(3)
        self.z_snap_spin.setSuffix(" м")
        self.z_snap_spin.setValue(self.interactive_thresholds.z_snap_tolerance_m)
        self.z_snap_spin.setMaximumWidth(180)
        threshold_layout.addRow("Привязка по высоте:", self.z_snap_spin)

        self.max_projection_spin = QDoubleSpinBox()
        self.max_projection_spin.setRange(0.01, 2.0)
        self.max_projection_spin.setDecimals(3)
        self.max_projection_spin.setSuffix(" м")
        self.max_projection_spin.setValue(self.interactive_thresholds.max_projection_distance_m)
        self.max_projection_spin.setMaximumWidth(180)
        threshold_layout.addRow("Макс. сдвиг проекции:", self.max_projection_spin)

        self.station_angle_spin = QDoubleSpinBox()
        self.station_angle_spin.setRange(0.1, 15.0)
        self.station_angle_spin.setDecimals(2)
        self.station_angle_spin.setSuffix("°")
        self.station_angle_spin.setValue(self.interactive_thresholds.max_station_angle_deg)
        self.station_angle_spin.setMaximumWidth(180)
        threshold_layout.addRow("Макс. угол луча:", self.station_angle_spin)

        self.adjacent_ratio_spin = QDoubleSpinBox()
        self.adjacent_ratio_spin.setRange(1.1, 10.0)
        self.adjacent_ratio_spin.setDecimals(2)
        self.adjacent_ratio_spin.setValue(self.interactive_thresholds.min_adjacent_improvement_ratio)
        self.adjacent_ratio_spin.setMaximumWidth(180)
        threshold_layout.addRow("Мин. выигрыш соседней грани:", self.adjacent_ratio_spin)

        threshold_group.setLayout(threshold_layout)
        threshold_group.setMinimumHeight(threshold_group.sizeHint().height())
        layout.addWidget(threshold_group)

        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(4)

        recalc_btn = QPushButton("Пересчитать")
        recalc_btn.clicked.connect(self._recalculate_correction_candidates)
        apply_compact_button_style(recalc_btn, width=110, min_height=30)
        buttons_layout.addWidget(recalc_btn)

        select_safe_btn = QPushButton("Выбрать безопасные")
        select_safe_btn.clicked.connect(self._select_safe_corrections)
        apply_compact_button_style(select_safe_btn, width=150, min_height=30)
        buttons_layout.addWidget(select_safe_btn)

        clear_btn = QPushButton("Снять выбор")
        clear_btn.clicked.connect(self._clear_correction_selection)
        apply_compact_button_style(clear_btn, width=110, min_height=30)
        buttons_layout.addWidget(clear_btn)

        buttons_layout.addStretch()
        layout.addLayout(buttons_layout)

        self.correction_summary_label = QLabel()
        self.correction_summary_label.setWordWrap(True)
        self.correction_summary_label.setStyleSheet(self._info_box_style())
        self.correction_summary_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.correction_summary_label)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter, 1)

        self.correction_table = QTableWidget(0, 9)
        self.correction_table.setHorizontalHeaderLabels(
            [
                "Принять",
                "Точка",
                "Текущий пояс",
                "Предложение",
                "Тип",
                "Смещение, мм",
                "ΔZ, мм",
                "Надежность",
                "Причина",
            ]
        )
        self.correction_table.verticalHeader().setVisible(False)
        self.correction_table.setAlternatingRowColors(True)
        header = self.correction_table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)
        self.correction_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.correction_table.setMinimumHeight(360)
        self.correction_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.correction_table.itemSelectionChanged.connect(self._update_correction_preview)
        splitter.addWidget(self.correction_table)

        import pyqtgraph as pg
        self.correction_preview_plot = pg.PlotWidget(title="Превью коррекции (XY)")
        self.correction_preview_plot.setBackground('w' if not getattr(self, "dark_theme_enabled", False) else '#1e1e1e')
        self.correction_preview_plot.showGrid(x=True, y=True, alpha=0.3)
        self.correction_preview_plot.setAspectLocked(True)
        splitter.addWidget(self.correction_preview_plot)
        splitter.setSizes([600, 400])

        self._populate_correction_table()
        self._finalize_step_view()

    def show_step_4(self):
        self.current_step = 4
        self.title_label.setText("Шаг 4 из 4: Подтверждение секций")
        self.back_btn.setEnabled(True)
        self.next_btn.setEnabled(True)
        self.next_btn.setText("Готово ✓")
        self.clear_steps_container()

        layout = self.steps_layout
        info = QLabel(
            "Проверьте уровни секций и укажите, где разрешено добавить недостающие точки секций. "
            "Секции без генерации считаются подтвержденными и будут перенесены в проект."
        )
        info.setWordWrap(True)
        info.setStyleSheet(self._info_box_style())
        layout.addWidget(info)

        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(4)

        select_all_btn = QPushButton("Включить все генерации")
        select_all_btn.clicked.connect(self._select_all_generated_sections)
        apply_compact_button_style(select_all_btn, width=170, min_height=30)
        buttons_layout.addWidget(select_all_btn)

        clear_btn = QPushButton("Отключить генерации")
        clear_btn.clicked.connect(self._clear_generated_sections)
        apply_compact_button_style(clear_btn, width=170, min_height=30)
        buttons_layout.addWidget(clear_btn)

        buttons_layout.addStretch()
        layout.addLayout(buttons_layout)

        self.section_summary_label = QLabel()
        self.section_summary_label.setWordWrap(True)
        self.section_summary_label.setStyleSheet(self._info_box_style())
        self.section_summary_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.section_summary_label)

        self.missing_belts_warning_label = QLabel()
        self.missing_belts_warning_label.setWordWrap(True)
        self.missing_belts_warning_label.setStyleSheet("color: #d32f2f; font-weight: bold; padding: 4px;")
        self.missing_belts_warning_label.setVisible(False)
        layout.addWidget(self.missing_belts_warning_label)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter, 1)

        self.section_table = QTableWidget(0, 6)
        self.section_table.setHorizontalHeaderLabels(
            ["Принять генерацию", "Секция", "Высота, м", "Точек", "Поясов", "Сгенерировано"]
        )
        self.section_table.verticalHeader().setVisible(False)
        self.section_table.setAlternatingRowColors(True)
        header = self.section_table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.section_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.section_table.setMinimumHeight(320)
        self.section_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.section_table.itemSelectionChanged.connect(self._update_section_preview)
        splitter.addWidget(self.section_table)

        import pyqtgraph as pg
        self.section_preview_plot = pg.PlotWidget(title="Превью секции (XZ)")
        self.section_preview_plot.setBackground('w' if not getattr(self, "dark_theme_enabled", False) else '#1e1e1e')
        self.section_preview_plot.showGrid(x=True, y=True, alpha=0.3)
        splitter.addWidget(self.section_preview_plot)
        splitter.setSizes([600, 400])

        self._populate_section_table()
        self._finalize_step_view()

    def _fast_copy_settings(self, settings: dict) -> dict:
        if not settings:
            return {}
        result = {"belt_count": settings.get("belt_count", 4)}
        if "assignments" in settings:
            result["assignments"] = {k: list(v) for k, v in settings["assignments"].items()}
        for k, v in settings.items():
            if k not in result:
                result[k] = v
        return result

    def go_next(self):
        if self.current_step == 1:
            super().go_next()
            return

        if self.current_step == 2:
            self.sorting_settings = self.get_sorting_settings()
            self.interactive_sorting_snapshot = self._fast_copy_settings(self.sorting_settings)
            validation_summary = self._validate_final_assignment_state()
            audit = self._build_import_audit(validation_summary)
            if audit["warnings"]:
                reply = QMessageBox.question(
                    self,
                    "Проверка распределения",
                    "Перед переходом к исправлениям обнаружены предупреждения:\n\n"
                    + "\n".join(f"• {warning}" for warning in audit["warnings"])
                    + "\n\nПерейти к проверке исправлений?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if reply != QMessageBox.StandardButton.Yes:
                    return
            DataImportWizard.finalize_data(self)
            self.interactive_base_data = self.get_result().copy()
            self.corrected_preview_data = self.interactive_base_data.copy()
            self.interactive_thresholds = InteractiveImportThresholds.from_data(self.interactive_base_data)
            self.show_step_3()
            self._recalculate_correction_candidates()
            return

        if self.current_step == 3:
            self._apply_selected_corrections()
            self._build_section_preview()
            self.show_step_4()
            return

        if self.current_step == 4:
            self._finalize_interactive_result()
            self.accept()

    def go_back(self):
        if self.current_step == 4:
            self.show_step_3()
            return
        if self.current_step == 3:
            if self.interactive_sorting_snapshot:
                self.saved_settings = self._fast_copy_settings(self.interactive_sorting_snapshot)
            self.show_step_2()
            return
        super().go_back()

    def _inject_interactive_step_banner(self, text: str) -> None:
        banner = QLabel(text)
        banner.setWordWrap(True)
        banner.setStyleSheet(self._info_box_style())
        self.steps_layout.insertWidget(0, banner)

    def _install_steps_scroll_area(self) -> None:
        if getattr(self, "steps_scroll", None) is not None:
            return
        main_layout = self.layout()
        if main_layout is None:
            return
        steps_index = main_layout.indexOf(self.steps_container)
        if steps_index < 0:
            return

        main_layout.removeWidget(self.steps_container)
        self.steps_scroll = QScrollArea(self)
        self.steps_scroll.setWidgetResizable(True)
        self.steps_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.steps_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.steps_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.steps_scroll.setWidget(self.steps_container)
        self.steps_scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.steps_scroll.setMinimumHeight(480)
        main_layout.insertWidget(1, self.steps_scroll, 1)

    def _finalize_step_view(self) -> None:
        self.steps_container.adjustSize()
        if getattr(self, "steps_scroll", None) is not None:
            self.steps_scroll.ensureVisible(0, 0, 0, 0)
            self.steps_scroll.verticalScrollBar().setValue(0)

    def _refresh_thresholds_from_widgets(self) -> None:
        if not all(
            hasattr(self, attr_name)
            for attr_name in (
                "z_snap_spin",
                "max_projection_spin",
                "station_angle_spin",
                "adjacent_ratio_spin",
            )
        ):
            return
        self.interactive_thresholds = InteractiveImportThresholds(
            z_snap_tolerance_m=float(self.z_snap_spin.value()),
            max_projection_distance_m=float(self.max_projection_spin.value()),
            max_station_angle_deg=float(self.station_angle_spin.value()),
            min_adjacent_improvement_ratio=float(self.adjacent_ratio_spin.value()),
            min_track_residual_m=float(self.interactive_thresholds.min_track_residual_m),
        )

    def _recalculate_correction_candidates(self) -> None:
        self._refresh_thresholds_from_widgets()
        self.correction_review = build_interactive_correction_review(
            self.interactive_base_data,
            thresholds=self.interactive_thresholds,
        )
        self.selected_correction_rows &= {
            int(candidate["row_index"])
            for candidate in self.correction_review.get("candidates", [])
        }
        if hasattr(self, "correction_table") and self.correction_table is not None:
            self._populate_correction_table()

    def _populate_correction_table(self) -> None:
        candidates = list(self.correction_review.get("candidates", []))
        summary = dict(self.correction_review.get("point_status_counts", {}))
        self.correction_table.setRowCount(len(candidates))

        for row_number, candidate in enumerate(candidates):
            check_item = QTableWidgetItem()
            check_item.setFlags(check_item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            row_idx = int(candidate["row_index"])
            check_item.setCheckState(
                Qt.CheckState.Checked if row_idx in self.selected_correction_rows else Qt.CheckState.Unchecked
            )
            check_item.setData(Qt.ItemDataRole.UserRole, row_idx)
            self.correction_table.setItem(row_number, 0, check_item)

            current_belt = int(candidate["current_belt"])
            proposed_belt = int(candidate["proposed_belt"])
            distance_mm = float(candidate["distance_moved_m"]) * 1000.0
            delta_z_mm = (float(candidate["proposed_z"]) - float(candidate["current_z"])) * 1000.0

            cells = [
                str(candidate["point_name"]),
                str(current_belt),
                f"{proposed_belt} ({candidate['proposed_x']:.3f}, {candidate['proposed_y']:.3f}, {candidate['proposed_z']:.3f})",
                str(candidate["correction_kind"]),
                f"{distance_mm:.1f}",
                f"{delta_z_mm:+.1f}",
                str(candidate["safety"]),
                str(candidate["reason"]),
            ]
            for column, value in enumerate(cells, start=1):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.correction_table.setItem(row_number, column, item)

        self.correction_summary_label.setText(
            "Рабочих точек принято без замечаний: {accepted}\n"
            "Кандидатов на исправление: {candidate_count}\n"
            "Точек, оставленных на ручной разбор: {manual_review}".format(
                accepted=int(summary.get("accepted", 0)),
                candidate_count=len(candidates),
                manual_review=int(summary.get("manual_review", 0)),
            )
        )

    def _update_correction_preview(self) -> None:
        if not hasattr(self, "correction_preview_plot"):
            return
        self.correction_preview_plot.clear()
        
        selected_items = self.correction_table.selectedItems()
        if not selected_items:
            return
            
        row_num = selected_items[0].row()
        item = self.correction_table.item(row_num, 0)
        if not item:
            return
            
        row_idx_data = item.data(Qt.ItemDataRole.UserRole)
        if row_idx_data is None:
            return
            
        row_idx = int(row_idx_data)
        
        candidates = list(self.correction_review.get("candidates", []))
        candidate = next((c for c in candidates if int(c["row_index"]) == row_idx), None)
        if not candidate:
            return
            
        curr_x, curr_y = candidate["current_x"], candidate["current_y"]
        prop_x, prop_y = candidate["proposed_x"], candidate["proposed_y"]
        
        import pyqtgraph as pg
        
        working_mask = build_working_tower_mask(self.interactive_base_data)
        working = self.interactive_base_data[working_mask]
        
        if "belt" in working.columns:
            try:
                belt_pts = working[pd.to_numeric(working["belt"], errors="coerce") == candidate["proposed_belt"]]
                if not belt_pts.empty:
                    bx = belt_pts["x"].to_numpy()
                    by = belt_pts["y"].to_numpy()
                    self.correction_preview_plot.plot(bx, by, pen=None, symbol='s', symbolBrush=(150, 150, 150, 150), symbolSize=8)
            except Exception:
                pass
                
        self.correction_preview_plot.plot([curr_x], [curr_y], pen=None, symbol='o', symbolBrush='r', symbolSize=12, name="Оригинал")
        self.correction_preview_plot.plot([prop_x], [prop_y], pen=None, symbol='o', symbolBrush='g', symbolSize=12, name="Предложение")
        self.correction_preview_plot.plot([curr_x, prop_x], [curr_y, prop_y], pen=pg.mkPen('y', width=2, style=Qt.PenStyle.DashLine))

    def _select_safe_corrections(self) -> None:
        self.selected_correction_rows = set()
        for candidate in self.correction_review.get("candidates", []):
            safety = str(candidate.get("safety", "")).lower()
            if safety == "safe":
                self.selected_correction_rows.add(int(candidate["row_index"]))
            elif safety.endswith("%"):
                try:
                    if int(safety[:-1]) >= 50:
                        self.selected_correction_rows.add(int(candidate["row_index"]))
                except ValueError:
                    pass
        self._populate_correction_table()

    def _clear_correction_selection(self) -> None:
        self.selected_correction_rows = set()
        self._populate_correction_table()

    def _collect_selected_correction_rows(self) -> set[int]:
        selected: set[int] = set()
        for row_number in range(self.correction_table.rowCount()):
            item = self.correction_table.item(row_number, 0)
            if item is None:
                continue
            if item.checkState() == Qt.CheckState.Checked:
                row_idx = item.data(Qt.ItemDataRole.UserRole)
                if row_idx is not None:
                    selected.add(int(row_idx))
        self.selected_correction_rows = selected
        return selected

    def _apply_selected_corrections(self) -> None:
        selected_rows = self._collect_selected_correction_rows()
        corrected, applied, rejected = apply_interactive_corrections(
            self.interactive_base_data,
            list(self.correction_review.get("candidates", [])),
            selected_rows,
        )
        self.corrected_preview_data = corrected
        self.applied_corrections = applied
        self.rejected_corrections = rejected

    def _build_section_preview(self) -> None:
        self.section_review = build_section_review(self.corrected_preview_data)
        
        # Check for missing belts warning
        belt_count = self.belt_count
        rows = self.section_review.get("rows", [])
        self.missing_belts_warning = False
        for row in rows:
            if int(row.get("belt_count", 0)) < belt_count:
                self.missing_belts_warning = True
                break
                
        generated_defaults = {
            int(row["section_num"])
            for row in rows
            if bool(row.get("apply_generated_default"))
        }
        if self.selected_generated_sections:
            self.selected_generated_sections &= {
                int(row["section_num"]) for row in self.section_review.get("rows", [])
            }
        else:
            self.selected_generated_sections = generated_defaults

    def _populate_section_table(self) -> None:
        rows = list(self.section_review.get("rows", []))
        self.section_table.setRowCount(len(rows))

        total_generated = 0
        for row_number, row in enumerate(rows):
            section_num = int(row["section_num"])
            generated_count = int(row.get("generated_count", 0) or 0)
            total_generated += generated_count

            check_item = QTableWidgetItem()
            check_item.setFlags(check_item.flags() | Qt.ItemFlag.ItemIsEnabled)
            if generated_count > 0:
                check_item.setFlags(check_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                check_item.setCheckState(
                    Qt.CheckState.Checked
                    if section_num in self.selected_generated_sections
                    else Qt.CheckState.Unchecked
                )
            else:
                check_item.setCheckState(Qt.CheckState.Checked)
            check_item.setData(Qt.ItemDataRole.UserRole, section_num)
            self.section_table.setItem(row_number, 0, check_item)

            values = [
                f"Секция {section_num}",
                f"{float(row['height']):.3f}",
                str(int(row["point_count"])),
                str(int(row["belt_count"])),
                str(generated_count),
            ]
            for column, value in enumerate(values, start=1):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.section_table.setItem(row_number, column, item)

        self.section_summary_label.setText(
            "Найдено секций: {count}\n"
            "Секций с генерацией точек: {generated_sections}\n"
            "Суммарно сгенерированных точек: {generated_points}".format(
                count=len(rows),
                generated_sections=sum(1 for row in rows if int(row.get("generated_count", 0) or 0) > 0),
                generated_points=total_generated,
            )
        )
        
        if getattr(self, "missing_belts_warning", False):
            self.missing_belts_warning_label.setText(
                "⚠️ Внимание: На некоторых секциях не хватает точек (поясов меньше, чем требуется). "
                "Генерация точек по неполным данным может быть неточной. "
                "Рекомендуется загрузить съемку со второй стоянки, воспользоваться функцией 'Достроить пояс' "
                "или пропустить этот шаг."
            )
            self.missing_belts_warning_label.setVisible(True)
        else:
            self.missing_belts_warning_label.setVisible(False)

    def _update_section_preview(self) -> None:
        if not hasattr(self, "section_preview_plot"):
            return
        self.section_preview_plot.clear()
        
        selected_items = self.section_table.selectedItems()
        if not selected_items:
            return
            
        row_num = selected_items[0].row()
        item = self.section_table.item(row_num, 0)
        if not item:
            return
            
        section_num_data = item.data(Qt.ItemDataRole.UserRole)
        if section_num_data is None:
            return
            
        section_num = int(section_num_data)
        
        rows = list(self.section_review.get("rows", []))
        section = next((r for r in rows if int(r["section_num"]) == section_num), None)
        if not section:
            return
            
        target_z = float(section["height"])
        tolerance = float(self.section_review.get("height_tolerance", 1.10))
        
        data = self.section_review.get("data_with_sections")
        if data is None or data.empty:
            return
            
        mask = data["z"].sub(target_z).abs().le(tolerance)
        section_data = data[mask]
        
        if section_data.empty:
            return
            
        import pyqtgraph as pg
        
        gen_mask = pd.Series(False, index=section_data.index)
        if "is_section_generated" in section_data.columns:
            gen_mask = section_data["is_section_generated"].fillna(False).astype(bool)
            
        real_pts = section_data[~gen_mask]
        gen_pts = section_data[gen_mask]
        
        if not real_pts.empty:
            self.section_preview_plot.plot(
                real_pts["x"].to_numpy(), real_pts["z"].to_numpy(),
                pen=None, symbol='o', symbolBrush='b', symbolSize=10, name="Оригинал"
            )
            
        if not gen_pts.empty:
            self.section_preview_plot.plot(
                gen_pts["x"].to_numpy(), gen_pts["z"].to_numpy(),
                pen=None, symbol='star', symbolBrush='g', symbolSize=14, name="Сгенерировано"
            )

    def _collect_selected_generated_sections(self) -> set[int]:
        selected: set[int] = set()
        for row_number in range(self.section_table.rowCount()):
            item = self.section_table.item(row_number, 0)
            if item is None:
                continue
            section_num = item.data(Qt.ItemDataRole.UserRole)
            if section_num is None:
                continue
            if item.checkState() == Qt.CheckState.Checked:
                selected.add(int(section_num))
        self.selected_generated_sections = selected
        return selected

    def _select_all_generated_sections(self) -> None:
        self.selected_generated_sections = {
            int(row["section_num"])
            for row in self.section_review.get("rows", [])
            if int(row.get("generated_count", 0) or 0) > 0
        }
        self._populate_section_table()

    def _clear_generated_sections(self) -> None:
        self.selected_generated_sections = {
            int(row["section_num"])
            for row in self.section_review.get("rows", [])
            if int(row.get("generated_count", 0) or 0) == 0
        }
        self._populate_section_table()

    def _skip_sections(self) -> None:
        self.selected_generated_sections = set()
        self._finalize_interactive_result()
        self.accept()

    def _finalize_interactive_result(self) -> None:
        selected_sections = self._collect_selected_generated_sections()
        final_data, section_lines, accepted_sections = apply_section_review_selection(
            self.section_review,
            selected_sections,
        )
        self.filtered_data = final_data.reset_index(drop=True)
        self.confirmed_section_data = section_lines
        self.accepted_generated_sections = accepted_sections
        self.sorting_settings = self._fast_copy_settings(self.interactive_sorting_snapshot)
        validation_summary = self._validation_summary_from_data(self.filtered_data)
        self._build_import_audit(validation_summary)

    def _validation_summary_from_data(self, data: pd.DataFrame) -> Dict[str, Any]:
        if data is None or data.empty:
            return {
                "valid": False,
                "warnings": ["После интерактивного импорта не осталось подтвержденных точек."],
                "assigned_count": 0,
                "unassigned_count": 0,
                "selected_count": 0,
                "belt_counts": {},
            }

        belt_counts: Dict[int, int] = {}
        if "belt" in data.columns:
            numeric_belts = pd.to_numeric(data["belt"], errors="coerce").dropna().astype(int)
            if not numeric_belts.empty:
                belt_counts = {
                    int(belt_num): int(count)
                    for belt_num, count in numeric_belts.value_counts().sort_index().to_dict().items()
                }

        working_mask = build_working_tower_mask(data)
        assigned_count = int(pd.to_numeric(data.loc[working_mask, "belt"], errors="coerce").notna().sum()) if "belt" in data.columns else 0
        warnings: list[str] = []
        if assigned_count == 0:
            warnings.append("Ни одна рабочая точка не подтверждена после интерактивного импорта.")
        if "import_review_status" in data.columns:
            manual_review = int(data["import_review_status"].astype(str).eq("manual_review").sum())
            if manual_review > 0:
                warnings.append(f"Остались точки без исправления, оставленные на ручной разбор: {manual_review}")

        return {
            "valid": len(warnings) == 0,
            "warnings": warnings,
            "assigned_count": assigned_count,
            "unassigned_count": 0,
            "selected_count": int(working_mask.sum()),
            "belt_counts": belt_counts,
        }

    def _build_import_audit(self, validation_summary: Dict[str, Any] | None = None) -> Dict[str, Any]:
        audit = super()._build_import_audit(validation_summary)
        audit["import_mode"] = "interactive"
        audit["interactive"] = {
            "thresholds": self.interactive_thresholds.to_dict(),
            "candidate_count": len(self.correction_review.get("candidates", [])),
            "selected_corrections": sorted(int(value) for value in self.selected_correction_rows),
            "applied_corrections": copy.deepcopy(self.applied_corrections),
            "rejected_corrections": copy.deepcopy(self.rejected_corrections),
            "point_status_counts": dict(self.correction_review.get("point_status_counts", {})),
            "section_levels": [float(value) for value in self.section_review.get("section_levels", [])],
            "accepted_generated_sections": copy.deepcopy(self.accepted_generated_sections),
            "section_count": len(self.confirmed_section_data),
        }
        self.import_audit = audit
        return audit

    def get_confirmed_section_data(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self.confirmed_section_data)
