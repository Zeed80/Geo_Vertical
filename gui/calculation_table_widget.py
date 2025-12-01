"""
Виджет таблицы расчета для МКЭ (SCAD-совместимый формат).
Отображает полные данные для расчета методом конечных элементов.
"""

from __future__ import annotations

from typing import Optional, Dict, List, Any
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QPushButton,
    QHeaderView,
    QFileDialog,
    QMessageBox,
    QLabel,
)

from core.tower_generator import TowerBlueprintV2
from core.structure.builder import TowerModelBuilder
from core.structure.model import TowerModel, MemberType
from core.db.profile_manager import ProfileManager
import pandas as pd


class CalculationTableWidget(QWidget):
    """
    Виджет для отображения таблицы расчета МКЭ.
    Показывает данные по узлам, элементам, нагрузкам и оборудованию.
    """
    
    def __init__(self, profile_manager: ProfileManager, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.profile_manager = profile_manager
        self._blueprint: Optional[TowerBlueprintV2] = None
        self._model: Optional[TowerModel] = None
        
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """Настройка интерфейса."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        
        # Заголовок
        header = QHBoxLayout()
        title = QLabel("Таблица расчета для МКЭ")
        title.setStyleSheet("font-weight: 600; font-size: 11pt;")
        header.addWidget(title)
        header.addStretch()
        
        # Кнопки экспорта
        export_csv_btn = QPushButton("Экспорт CSV")
        export_csv_btn.clicked.connect(self._export_csv)
        header.addWidget(export_csv_btn)
        
        export_excel_btn = QPushButton("Экспорт Excel")
        export_excel_btn.clicked.connect(self._export_excel)
        header.addWidget(export_excel_btn)
        
        export_scad_btn = QPushButton("Экспорт SCAD")
        export_scad_btn.clicked.connect(self._export_scad)
        header.addWidget(export_scad_btn)
        
        layout.addLayout(header)
        
        # Вкладки для разных разделов
        self.tabs = QTabWidget()
        
        # Вкладка: Узлы
        self.nodes_table = QTableWidget()
        self._setup_table(self.nodes_table, [
            "Номер узла", "X (м)", "Y (м)", "Z (м)",
            "Закрепление X", "Закрепление Y", "Закрепление Z"
        ])
        self.tabs.addTab(self.nodes_table, "Узлы")
        
        # Вкладка: Элементы
        self.members_table = QTableWidget()
        self._setup_table(self.members_table, [
            "Номер элемента", "Начальный узел", "Конечный узел",
            "Тип элемента", "Название профиля", "Стандарт",
            "Площадь (см²)", "Ix (см⁴)", "Iy (см⁴)",
            "ix (см)", "iy (см)", "Материал", "E (МПа)"
        ])
        self.tabs.addTab(self.members_table, "Элементы")
        
        # Вкладка: Нагрузки
        self.loads_table = QTableWidget()
        self._setup_table(self.loads_table, [
            "Номер узла", "Тип нагрузки",
            "Fx (кН)", "Fy (кН)", "Fz (кН)",
            "Mx (кН·м)", "My (кН·м)", "Mz (кН·м)"
        ])
        self.tabs.addTab(self.loads_table, "Нагрузки")
        
        # Вкладка: Оборудование
        self.equipment_table = QTableWidget()
        self._setup_table(self.equipment_table, [
            "Название", "Высота (м)", "Масса (кг)",
            "Площадь X (м²)", "Площадь Y (м²)", "Привязанный узел"
        ])
        self.tabs.addTab(self.equipment_table, "Оборудование")
        
        layout.addWidget(self.tabs)
    
    def _setup_table(self, table: QTableWidget, headers: List[str]) -> None:
        """Настройка таблицы."""
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    
    def set_blueprint(self, blueprint: Optional[TowerBlueprintV2]) -> None:
        """Установить чертеж башни для расчета."""
        self._blueprint = blueprint
        if blueprint:
            builder = TowerModelBuilder(blueprint, self.profile_manager)
            self._model = builder.build()
            self._update_tables()
        else:
            self._model = None
            self._clear_tables()
    
    def _update_tables(self) -> None:
        """Обновить все таблицы."""
        if not self._model:
            return
        
        self._update_nodes_table()
        self._update_members_table()
        self._update_loads_table()
        self._update_equipment_table()
    
    def _update_nodes_table(self) -> None:
        """Обновить таблицу узлов."""
        if not self._model:
            return
        
        nodes = sorted(self._model.nodes.items(), key=lambda x: x[0])
        self.nodes_table.setRowCount(len(nodes))
        
        for row, (node_id, node) in enumerate(nodes):
            self.nodes_table.setItem(row, 0, QTableWidgetItem(str(node_id)))
            self.nodes_table.setItem(row, 1, QTableWidgetItem(f"{node.x:.3f}"))
            self.nodes_table.setItem(row, 2, QTableWidgetItem(f"{node.y:.3f}"))
            self.nodes_table.setItem(row, 3, QTableWidgetItem(f"{node.z:.3f}"))
            self.nodes_table.setItem(row, 4, QTableWidgetItem("Да" if node.is_fixed else "Нет"))
            self.nodes_table.setItem(row, 5, QTableWidgetItem("Да" if node.is_fixed else "Нет"))
            self.nodes_table.setItem(row, 6, QTableWidgetItem("Да" if node.is_fixed else "Нет"))
    
    def _update_members_table(self) -> None:
        """Обновить таблицу элементов."""
        if not self._model:
            return
        
        self.members_table.setRowCount(len(self._model.members))
        
        type_names = {
            MemberType.LEG: "Пояс",
            MemberType.BRACE: "Раскос",
            MemberType.STRUT: "Распорка",
            MemberType.DIAPHRAGM: "Диафрагма",
        }
        
        for row, member in enumerate(self._model.members):
            self.members_table.setItem(row, 0, QTableWidgetItem(str(member.id)))
            self.members_table.setItem(row, 1, QTableWidgetItem(str(member.start_node_id)))
            self.members_table.setItem(row, 2, QTableWidgetItem(str(member.end_node_id)))
            self.members_table.setItem(row, 3, QTableWidgetItem(type_names.get(member.member_type, "Неизвестно")))
            
            # Данные профиля
            if member.profile_data:
                profile_name = member.profile_data.get('designation', 'Не задано')
                standard = member.profile_data.get('standard', 'Не задано')
                A = member.profile_data.get('A', 0.0)
                Ix = member.profile_data.get('Ix', 0.0)
                Iy = member.profile_data.get('Iy', 0.0)
                ix = member.profile_data.get('i_x', 0.0)
                iy = member.profile_data.get('i_y', 0.0)
            else:
                profile_name = "Не задано"
                standard = "Не задано"
                A = Ix = Iy = ix = iy = 0.0
            
            self.members_table.setItem(row, 4, QTableWidgetItem(profile_name))
            self.members_table.setItem(row, 5, QTableWidgetItem(standard))
            self.members_table.setItem(row, 6, QTableWidgetItem(f"{A:.2f}" if A > 0 else "—"))
            self.members_table.setItem(row, 7, QTableWidgetItem(f"{Ix:.2f}" if Ix > 0 else "—"))
            self.members_table.setItem(row, 8, QTableWidgetItem(f"{Iy:.2f}" if Iy > 0 else "—"))
            self.members_table.setItem(row, 9, QTableWidgetItem(f"{ix:.2f}" if ix > 0 else "—"))
            self.members_table.setItem(row, 10, QTableWidgetItem(f"{iy:.2f}" if iy > 0 else "—"))
            self.members_table.setItem(row, 11, QTableWidgetItem("Сталь"))
            self.members_table.setItem(row, 12, QTableWidgetItem("206000"))
    
    def _update_loads_table(self) -> None:
        """Обновить таблицу нагрузок."""
        # Пока пустая, будет заполняться после расчета ветровой нагрузки
        self.loads_table.setRowCount(0)
    
    def _update_equipment_table(self) -> None:
        """Обновить таблицу оборудования."""
        if not self._model:
            return
        
        self.equipment_table.setRowCount(len(self._model.equipment))
        
        for row, eq in enumerate(self._model.equipment):
            self.equipment_table.setItem(row, 0, QTableWidgetItem(eq.name))
            self.equipment_table.setItem(row, 1, QTableWidgetItem(f"{eq.height:.2f}"))
            self.equipment_table.setItem(row, 2, QTableWidgetItem(f"{eq.mass:.1f}"))
            self.equipment_table.setItem(row, 3, QTableWidgetItem(f"{eq.area_x:.3f}"))
            self.equipment_table.setItem(row, 4, QTableWidgetItem(f"{eq.area_y:.3f}"))
            self.equipment_table.setItem(row, 5, QTableWidgetItem("—"))  # TODO: привязка к узлу
    
    def _clear_tables(self) -> None:
        """Очистить все таблицы."""
        self.nodes_table.setRowCount(0)
        self.members_table.setRowCount(0)
        self.loads_table.setRowCount(0)
        self.equipment_table.setRowCount(0)
    
    def _export_csv(self) -> None:
        """Экспортировать данные в CSV."""
        if not self._model:
            QMessageBox.warning(self, "Ошибка", "Нет данных для экспорта.")
            return
        
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить CSV",
            "mke_data.csv",
            "CSV Files (*.csv)"
        )
        
        if path:
            try:
                # Экспортировать каждую таблицу в отдельный файл
                base_path = path.replace('.csv', '')
                self._export_table_to_csv(self.nodes_table, f"{base_path}_nodes.csv")
                self._export_table_to_csv(self.members_table, f"{base_path}_members.csv")
                self._export_table_to_csv(self.loads_table, f"{base_path}_loads.csv")
                self._export_table_to_csv(self.equipment_table, f"{base_path}_equipment.csv")
                
                QMessageBox.information(self, "Успех", f"Данные экспортированы: {base_path}_*.csv")
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Не удалось экспортировать: {str(e)}")
    
    def _export_excel(self) -> None:
        """Экспортировать данные в Excel."""
        if not self._model:
            QMessageBox.warning(self, "Ошибка", "Нет данных для экспорта.")
            return
        
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить Excel",
            "mke_data.xlsx",
            "Excel Files (*.xlsx)"
        )
        
        if path:
            try:
                with pd.ExcelWriter(path, engine='openpyxl') as writer:
                    self._table_to_dataframe(self.nodes_table).to_excel(writer, sheet_name='Узлы', index=False)
                    self._table_to_dataframe(self.members_table).to_excel(writer, sheet_name='Элементы', index=False)
                    self._table_to_dataframe(self.loads_table).to_excel(writer, sheet_name='Нагрузки', index=False)
                    self._table_to_dataframe(self.equipment_table).to_excel(writer, sheet_name='Оборудование', index=False)
                
                QMessageBox.information(self, "Успех", f"Данные экспортированы: {path}")
            except ImportError:
                QMessageBox.warning(self, "Ошибка", "Для экспорта в Excel требуется библиотека openpyxl.")
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Не удалось экспортировать: {str(e)}")
    
    def _export_table_to_csv(self, table: QTableWidget, path: str) -> None:
        """Экспортировать таблицу в CSV."""
        df = self._table_to_dataframe(table)
        df.to_csv(path, index=False, encoding='utf-8-sig')
    
    def _export_scad(self) -> None:
        """Экспортировать данные в формат SCAD."""
        if not self._blueprint:
            QMessageBox.warning(self, "Ошибка", "Нет данных для экспорта.")
            return
        
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить SCAD",
            "tower_data.scad",
            "SCAD Files (*.scad);;Text Files (*.txt)"
        )
        
        if path:
            try:
                from core.exporters.scad_exporter import SCADExporter
                exporter = SCADExporter(self.profile_manager)
                exporter.export(self._blueprint, path)
                QMessageBox.information(self, "Успех", f"Данные экспортированы: {path}")
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Не удалось экспортировать: {str(e)}")
    
    def _table_to_dataframe(self, table: QTableWidget) -> pd.DataFrame:
        """Преобразовать таблицу в DataFrame."""
        headers = [table.horizontalHeaderItem(i).text() for i in range(table.columnCount())]
        data = []
        
        for row in range(table.rowCount()):
            row_data = []
            for col in range(table.columnCount()):
                item = table.item(row, col)
                row_data.append(item.text() if item else "")
            data.append(row_data)
        
        return pd.DataFrame(data, columns=headers)
