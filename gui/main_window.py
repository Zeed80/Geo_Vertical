"""
Главное окно приложения GeoVertical Analyzer
"""

from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QTabWidget, QMenuBar, QMenu, QToolBar,
                             QFileDialog, QMessageBox, QStatusBar, QLabel,
                             QPushButton, QComboBox, QGroupBox, QFormLayout,
                             QDoubleSpinBox, QDialog, QSplitter, QSpinBox, QCheckBox,
                             QSizePolicy, QApplication)
from contextlib import contextmanager

from PyQt6.QtCore import Qt, pyqtSignal, QSettings, QRect, QTimer
from PyQt6.QtGui import QIcon, QAction, QPalette, QColor, QGuiApplication
import pandas as pd
import numpy as np
from typing import Optional, Dict, Any
import logging
import json
import os
import pickle
import re
from pathlib import Path

from gui.data_table import DataTableWidget
from gui.point_editor_3d import PointEditor3DWidget
from gui.data_import_wizard import DataImportWizard
from gui.second_station_import_wizard import SecondStationImportWizard
from gui.full_report_tab import FullReportTab
from core.data_loader import load_data_from_file, validate_data
from core.normatives import NormativeChecker
from core.belt_operations import estimate_belt_count_from_heights, auto_assign_belts
from core.section_operations import find_section_levels, add_missing_points_for_sections, get_section_lines
from utils.coordinate_systems import CoordinateSystemManager, get_common_epsg_list
from core.services import ProjectManager, CalculationService
from core.tower_generator import TowerBlueprint, generate_tower_data
from core.schema_exporter import (
    build_schema_data,
    export_schema_to_dxf,
    export_schema_to_pdf,
    DxfExportOptions,
)
from core.exceptions import (
    GeoVerticalError,
    DataLoadError,
    FileFormatError,
    DataValidationError,
    CalculationError,
    InsufficientDataError,
    InvalidCoordinatesError,
    GroupingError,
    CoordinateTransformError,
    ReportGenerationError,
    PDFGenerationError,
    ExcelGenerationError,
    FilteringError,
    AutoFilterError,
    ProjectSaveError,
    ProjectLoadError,
    SettingsLoadError,
    SettingsSaveError,
    ExportError,
    SchemaExportError,
)

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Главное окно приложения"""
    
    def __init__(self):
        super().__init__()
        
        # Данные
        self.raw_data = None
        self.processed_data = None
        self.epsg_code = None
        self.current_file_path = None  # Путь к текущему открытому файлу
        self.original_data_before_sections = None  # Данные до создания секций
        self._tower_blueprint: Optional[TowerBlueprint] = None  # Последний blueprint мастера
        
        # Сервисы
        self.project_manager = ProjectManager()
        self.calculation_service = CalculationService()
        self.normative_checker = NormativeChecker()
        
        # Менеджер Undo/Redo
        from core.undo_manager import UndoManager
        self.undo_manager = UndoManager(max_history_size=50)
        
        # Настройки расчетов
        self.height_tolerance = 0.1  # метры
        self.center_method = 'mean'
        self.expected_belt_count = None  # None = автоопределение
        self.tower_faces_count = None  # Количество граней башни
        
        # Сохраненные пути
        self._paths_settings = QSettings('GeoVertical', 'GeoVerticalAnalyzerPaths')
        self.last_open_dir = self._paths_settings.value('last_open_dir', os.getcwd())
        
        # Виджеты (будут созданы в init_ui)
        self.editor_3d = None
        self.data_table = None
        self.belt_count_spin = None
        self.auto_belt_checkbox = None
        self.dark_theme_action = None
        self.dark_theme_enabled = False
        self.export_schema_action = None
        self.full_report_tab = None
        
        # Автосохранение
        self.autosave_timer = QTimer(self)
        self.autosave_enabled = True
        self.autosave_interval_minutes = 3  # По умолчанию 3 минуты (улучшенная защита)
        self.has_unsaved_changes = False  # Флаг несохраненных изменений
        self.autosave_path = None  # Путь для автосохранения
        self._suspend_data_sync = False  # Флаг предотвращения рекурсии при синхронизации данных
        
        self.init_ui()
        self.load_theme_settings()
        self.load_window_geometry()  # Загружаем сохраненные настройки окна
        
        # Обновляем состояние кнопок undo/redo после инициализации
        self._update_undo_redo_actions()
        
        # Настраиваем автосохранение после инициализации UI
        self._setup_autosave()
        # Пытаемся восстановить после сбоя (только если нет загруженного проекта)
        if self.raw_data is None:
            self._try_recover_autosave()
        
    @contextmanager
    def _suspend_data_change_handlers(self):
        """Временная блокировка реакций на сигналы data_changed."""
        previous_state = self._suspend_data_sync
        self._suspend_data_sync = True
        try:
            yield
        finally:
            self._suspend_data_sync = previous_state

    def init_ui(self):
        """Инициализация интерфейса"""
        self.setWindowTitle('GeoVertical Analyzer - Анализ вертикальности мачт')
        
        # НЕ максимизируем окно здесь - это делает load_window_geometry()
        # Или максимизирует при первом запуске
        
        # Создаем меню
        self.create_menu()
        
        # Создаем панель инструментов
        self.create_toolbar()
        
        # Создаем центральный виджет
        self.create_central_widget()
        
        # Создаем статус-бар
        self.create_statusbar()
        
    def _create_toolbar_button(self, text, callback, tooltip: Optional[str] = None,
                                enabled: bool = True, variant: Optional[str] = None,
                                width: int = 78, height: int = 36,
                                rich_tooltip_title: Optional[str] = None,
                                rich_tooltip_desc: Optional[str] = None,
                                rich_tooltip_shortcut: Optional[str] = None) -> QPushButton:
        """Создает компактную кнопку с однострочной подписью для тулбара."""
        button = QPushButton(text)
        button.setObjectName('toolbarButton')
        button.setCheckable(False)
        button.clicked.connect(callback)
        button.setEnabled(enabled)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        # Компактные размеры для однострочных кнопок
        button.setFixedWidth(max(width, 90))
        button.setFixedHeight(max(height, 36))

        # Всегда устанавливаем tooltip - если не указан, используем текст кнопки
        if tooltip:
            button.setToolTip(tooltip)
        else:
            # Создаем tooltip из текста кнопки, убирая эмодзи и переносы строк
            tooltip_text = text.replace('\n', ' ').strip()
            # Убираем эмодзи для более читаемого tooltip
            tooltip_text = re.sub(r'[^\w\s\-\(\)]', '', tooltip_text).strip()
            if tooltip_text:
                button.setToolTip(tooltip_text)
        
        # Устанавливаем rich tooltip если указан
        if rich_tooltip_title:
            from gui.rich_tooltip import set_rich_tooltip
            set_rich_tooltip(button, rich_tooltip_title, 
                           rich_tooltip_desc or "", 
                           rich_tooltip_shortcut or "")

        if variant:
            button.setProperty('variant', variant)

        return button

    def create_menu(self):
        """Создание меню"""
        menubar = self.menuBar()
        
        # Меню "Файл"
        file_menu = menubar.addMenu('Файл')
        
        # Новый проект
        new_project_action = QAction('Новый проект', self)
        new_project_action.setShortcut('Ctrl+N')
        new_project_action.triggered.connect(self.new_project)
        file_menu.addAction(new_project_action)

        create_tower_action = QAction('Создать башню...', self)
        create_tower_action.setShortcut('Ctrl+Shift+N')
        create_tower_action.triggered.connect(self.create_tower_from_scratch)
        file_menu.addAction(create_tower_action)
        
        file_menu.addSeparator()
        
        open_action = QAction('Импорт GEO файла...', self)
        open_action.setShortcut('Ctrl+O')
        open_action.triggered.connect(self.open_file)
        file_menu.addAction(open_action)
        
        second_station_action = QAction('Импорт с другой точки стояния...', self)
        second_station_action.triggered.connect(self.import_second_station)
        file_menu.addAction(second_station_action)
        
        file_menu.addSeparator()
        
        # Действия для проекта
        save_project_action = QAction('Сохранить проект...', self)
        save_project_action.setShortcut('Ctrl+Shift+S')
        save_project_action.triggered.connect(self.save_project)
        file_menu.addAction(save_project_action)
        
        load_project_action = QAction('Открыть проект...', self)
        load_project_action.setShortcut('Ctrl+Shift+O')
        load_project_action.triggered.connect(self.load_project)
        file_menu.addAction(load_project_action)
        
        file_menu.addSeparator()
        
        save_report_action = QAction('Сохранить отчет...', self)
        save_report_action.setShortcut('Ctrl+S')
        save_report_action.triggered.connect(self.save_report)
        file_menu.addAction(save_report_action)

        file_menu.addSeparator()
        
        exit_action = QAction('Выход', self)
        exit_action.setShortcut('Ctrl+Q')
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Меню "Правка"
        edit_menu = menubar.addMenu('Правка')
        
        # Undo/Redo
        self.undo_action = QAction('Отменить', self)
        self.undo_action.setShortcut('Ctrl+Z')
        self.undo_action.setEnabled(False)
        self.undo_action.triggered.connect(self.undo)
        edit_menu.addAction(self.undo_action)
        
        self.redo_action = QAction('Повторить', self)
        self.redo_action.setShortcut('Ctrl+Y')
        self.redo_action.setEnabled(False)
        self.redo_action.triggered.connect(self.redo)
        edit_menu.addAction(self.redo_action)
        
        edit_menu.addSeparator()
        
        add_point_action = QAction('Добавить точку', self)
        add_point_action.triggered.connect(self.add_point)
        edit_menu.addAction(add_point_action)
        
        delete_selected_action = QAction('Удалить выбранные', self)
        delete_selected_action.setShortcut('Del')
        delete_selected_action.triggered.connect(self.delete_selected_points)
        edit_menu.addAction(delete_selected_action)
        
        edit_menu.addSeparator()
        
        clear_action = QAction('Очистить все данные', self)
        clear_action.triggered.connect(self.clear_data)
        edit_menu.addAction(clear_action)
        
        # Меню "Расчет"
        calc_menu = menubar.addMenu('Расчет')
        
        calculate_action = QAction('Выполнить расчет', self)
        calculate_action.setShortcut('F5')
        calculate_action.triggered.connect(self.calculate)
        calc_menu.addAction(calculate_action)
        
        calc_menu.addSeparator()
        
        batch_action = QAction('Пакетная обработка...', self)
        batch_action.setToolTip('Обработка нескольких файлов одновременно')
        batch_action.triggered.connect(self.show_batch_processing)
        calc_menu.addAction(batch_action)
        
        calc_menu.addSeparator()
        
        settings_action = QAction('Параметры расчета...', self)
        settings_action.triggered.connect(self.show_settings)
        calc_menu.addAction(settings_action)

        # Меню "Экспорт"
        export_menu = menubar.addMenu('Экспорт')
        self.export_schema_action = QAction('Сохранить схему...', self)
        self.export_schema_action.setShortcut('Ctrl+E')
        self.export_schema_action.setEnabled(False)
        self.export_schema_action.triggered.connect(self.export_schema_dialog)
        export_menu.addAction(self.export_schema_action)

        # Меню "Вид"
        view_menu = menubar.addMenu('Вид')
        self.dark_theme_action = QAction('Темная тема', self, checkable=True)
        self.dark_theme_action.toggled.connect(self.on_dark_theme_toggled)
        view_menu.addAction(self.dark_theme_action)
        
        # Меню "Справка"
        help_menu = menubar.addMenu('Справка')
        
        user_guide_action = QAction('Руководство пользователя', self)
        user_guide_action.setShortcut('F1')
        user_guide_action.triggered.connect(self.show_user_guide)
        help_menu.addAction(user_guide_action)
        
        help_menu.addSeparator()
        
        about_norms_action = QAction('О нормативах', self)
        about_norms_action.triggered.connect(self.show_about_normatives)
        help_menu.addAction(about_norms_action)
        
        about_action = QAction('О программе', self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
        
    def create_toolbar(self):
        """Создание панели инструментов"""
        toolbar = QToolBar()
        toolbar.setObjectName('MainToolBar')
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        self.toolbar = toolbar
        
        # Применяем начальные стили
        self.update_toolbar_styles()
        
        # ========== ГРУППА: Проект ==========
        open_project_btn = self._create_toolbar_button(
            '📁 Открыть проект',
            self.load_project,
            tooltip='Открыть сохраненный проект (Ctrl+Shift+O)',
            width=120,
            rich_tooltip_title='Открыть проект',
            rich_tooltip_desc='Загрузите ранее сохраненный проект со всеми данными, настройками и результатами расчетов.',
            rich_tooltip_shortcut='Ctrl+Shift+O'
        )
        toolbar.addWidget(open_project_btn)
        
        self.save_project_btn = self._create_toolbar_button(
            '💾 Сохранить проект',
            self.save_project,
            tooltip='Быстрое сохранение проекта (Ctrl+Shift+S)',
            enabled=False,
            width=130,
            rich_tooltip_title='Сохранить проект',
            rich_tooltip_desc='Быстрое сохранение проекта в текущий файл. Сохраняются все данные, настройки и результаты расчетов.',
            rich_tooltip_shortcut='Ctrl+Shift+S'
        )
        toolbar.addWidget(self.save_project_btn)
        
        save_project_as_btn = self._create_toolbar_button(
            '💾 Сохранить как',
            self.save_project_as,
            tooltip='Сохранить проект с новым именем',
            width=120,
            rich_tooltip_title='Сохранить проект как',
            rich_tooltip_desc='Сохранить проект в новый файл с указанием имени. Позволяет создать копию проекта.'
        )
        toolbar.addWidget(save_project_as_btn)
        
        toolbar.addSeparator()
        
        # ========== ГРУППА: Импорт данных ==========
        open_btn = self._create_toolbar_button(
            '📂 Импорт GEO', 
            self.open_file, 
            tooltip='Импорт GEO файла (Ctrl+O)',
            width=110,
            rich_tooltip_title='Импорт геодезических данных',
            rich_tooltip_desc='Загрузите файл с координатами точек башни. Поддерживаются форматы: CSV, DXF, GeoJSON, Shapefile, Trimble JobXML.',
            rich_tooltip_shortcut='Ctrl+O'
        )
        toolbar.addWidget(open_btn)
        
        import_second_btn = self._create_toolbar_button(
            '📥 Импорт второй станции',
            self.import_second_station,
            tooltip='Импорт данных с другой точки стояния',
            width=150,
            rich_tooltip_title='Импорт второй станции',
            rich_tooltip_desc='Загрузите данные измерений с дополнительной точки стояния для объединения с основными данными.'
        )
        toolbar.addWidget(import_second_btn)
        
        toolbar.addSeparator()
        
        # ========== ГРУППА: Редактирование ==========
        self.undo_btn = self._create_toolbar_button(
            '↩️ Отменить',
            self.undo,
            tooltip='Отменить последнее действие (Ctrl+Z)',
            enabled=False,
            width=100,
            rich_tooltip_title='Отменить действие',
            rich_tooltip_desc='Отменяет последнее выполненное действие. Поддерживается история изменений.',
            rich_tooltip_shortcut='Ctrl+Z'
        )
        toolbar.addWidget(self.undo_btn)
        
        self.redo_btn = self._create_toolbar_button(
            '↪️ Повторить',
            self.redo,
            tooltip='Повторить отмененное действие (Ctrl+Y)',
            enabled=False,
            width=100,
            rich_tooltip_title='Повторить действие',
            rich_tooltip_desc='Повторяет последнее отмененное действие.',
            rich_tooltip_shortcut='Ctrl+Y'
        )
        toolbar.addWidget(self.redo_btn)
        
        toolbar.addSeparator()
        
        # ========== ГРУППА: Данные ==========
        toolbar.addWidget(QLabel('  Поясов: '))
        self.belt_count_spin = QSpinBox()
        self.belt_count_spin.setMinimum(1)
        self.belt_count_spin.setMaximum(50)
        self.belt_count_spin.setValue(10)
        self.belt_count_spin.setToolTip('Ожидаемое количество поясов башни')
        self.belt_count_spin.valueChanged.connect(self.on_belt_count_changed)
        self.belt_count_spin.setFixedWidth(60)
        toolbar.addWidget(self.belt_count_spin)
        
        self.auto_belt_checkbox = QCheckBox('Авто')
        self.auto_belt_checkbox.setChecked(True)
        self.auto_belt_checkbox.setToolTip('Автоматическое определение количества поясов')
        self.auto_belt_checkbox.toggled.connect(self.on_auto_belt_toggled)
        self.belt_count_spin.setEnabled(False)  # По умолчанию авто
        toolbar.addWidget(self.auto_belt_checkbox)
        
        toolbar.addWidget(QLabel('  Угол (XY): '))
        from PyQt6.QtWidgets import QDoubleSpinBox
        self.line_angle_spin = QDoubleSpinBox()
        self.line_angle_spin.setRange(-360.0, 360.0)
        self.line_angle_spin.setDecimals(1)
        self.line_angle_spin.setSingleStep(1.0)
        self.line_angle_spin.setToolTip('Угол между линиями двух импортов в плоскости XY')
        self.line_angle_spin.setFixedWidth(70)
        toolbar.addWidget(self.line_angle_spin)

        build_belt_btn = self._create_toolbar_button(
            '⬛ Достроить пояс',
            self.on_build_missing_belt,
            tooltip='Достроить недостающий пояс на основе соседних поясов',
            width=120,
            rich_tooltip_title='Достроить пояс',
            rich_tooltip_desc='Автоматически создает недостающий пояс башни на основе геометрии соседних поясов. Используется для восстановления пропущенных данных.'
        )
        toolbar.addWidget(build_belt_btn)
        
        toolbar.addSeparator()
        
        # ========== ГРУППА: Расчет ==========
        toolbar.addWidget(QLabel('  СК: '))
        self.epsg_combo = QComboBox()
        self.epsg_combo.addItem('Авто', None)
        for code, desc in get_common_epsg_list():
            self.epsg_combo.addItem(f"EPSG:{code} - {desc}", code)
        self.epsg_combo.currentIndexChanged.connect(self.on_epsg_changed)
        self.epsg_combo.setFixedWidth(180)
        toolbar.addWidget(self.epsg_combo)
        
        calc_btn = self._create_toolbar_button(
            '⚙️ Рассчитать',
            self.calculate,
            tooltip='Выполнить расчет вертикальности и прямолинейности (F5)',
            variant='primary',
            width=110,
            rich_tooltip_title='Выполнить расчет',
            rich_tooltip_desc='Запускает полный цикл расчетов: группировка точек по поясам, расчет центров, построение оси башни, вычисление отклонений и проверка нормативов.',
            rich_tooltip_shortcut='F5'
        )
        toolbar.addWidget(calc_btn)
        
        toolbar.addSeparator()
        
        # ========== ГРУППА: Экспорт ==========
        save_btn = self._create_toolbar_button(
            '💾 Сохранить отчет', 
            self.save_report, 
            tooltip='Сохранить отчет в PDF, Word или Excel (Ctrl+S)',
            width=130,
            rich_tooltip_title='Сохранить отчет',
            rich_tooltip_desc='Генерирует профессиональный отчет с результатами анализа. Доступны форматы: PDF (с графиками), Word (DOCX), Excel (таблицы).',
            rich_tooltip_shortcut='Ctrl+S'
        )
        toolbar.addWidget(save_btn)
        
        toolbar.addSeparator()
        
        # ========== ГРУППА: Очистка ==========
        clear_btn = self._create_toolbar_button(
            '🗑️ Очистить данные', 
            self.clear_data, 
            tooltip='Очистить все данные и начать заново',
            width=130,
            rich_tooltip_title='Очистить данные',
            rich_tooltip_desc='Удаляет все загруженные данные, результаты расчетов и сбрасывает проект к начальному состоянию. Действие необратимо.'
        )
        toolbar.addWidget(clear_btn)
        
    def create_central_widget(self):
        """Создание центрального виджета с тремя основными вкладками"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        central_widget.setLayout(main_layout)
        
        # Основной TabWidget с тремя вкладками
        self.main_tabs = QTabWidget()
        main_layout.addWidget(self.main_tabs)
        
        # ===== ВКЛАДКА 1: Главная (3D редактор + таблица) =====
        main_tab = QWidget()
        main_tab_layout = QVBoxLayout()
        main_tab_layout.setContentsMargins(5, 5, 5, 5)
        main_tab.setLayout(main_tab_layout)
        
        # Splitter: 3D редактор и таблица данных
        top_splitter = QSplitter(Qt.Orientation.Horizontal)
        top_splitter.setHandleWidth(6)
        top_splitter.setStyleSheet("""
            QSplitter::handle {
                background: #cccccc;
            }
            QSplitter::handle:hover {
                background: #999999;
            }
        """)
        
        # 3D редактор точек
        self.editor_3d = PointEditor3DWidget()
        self.editor_3d.toolbar_position_changed.connect(self.on_editor_toolbar_position_changed)
        self.editor_3d.data_changed.connect(self.on_3d_data_changed)
        self.editor_3d.point_selected.connect(self.on_3d_point_selected)
        self.editor_3d.belt_assigned.connect(self.on_belt_assigned)
        self.editor_3d.tower_blueprint_requested.connect(self.apply_tower_blueprint)
        self.editor_3d.setMinimumWidth(600)
        self.restore_editor_toolbar_position()
        top_splitter.addWidget(self.editor_3d)
        
        # Таблица данных (с передачей ссылки на 3D редактор для секций)
        self.data_table = DataTableWidget(editor_3d=self.editor_3d)
        self.data_table.data_changed.connect(self.on_table_data_changed)
        self.data_table.row_selected.connect(self.on_table_point_selected)
        self.data_table.active_station_changed.connect(self.on_active_station_changed)
        self.data_table.setMinimumWidth(400)
        top_splitter.addWidget(self.data_table)
        
        # Пропорции: 3D занимает 65%, таблица 35%
        top_splitter.setStretchFactor(0, 65)
        top_splitter.setStretchFactor(1, 35)
        
        main_tab_layout.addWidget(top_splitter)
        
        self.main_tabs.addTab(main_tab, '🏠 Главная')
        
        # ===== ВКЛАДКА 2: Вертикальность башни =====
        from gui.verticality_widget import VerticalityWidget
        self.verticality_widget = VerticalityWidget()
        # Передаем ссылку на 3D редактор для доступа к section_data
        self.verticality_widget.editor_3d = self.editor_3d
        # Передаем ссылку на таблицу данных для получения угловых измерений
        self.verticality_widget.data_table_widget = self.data_table
        self.main_tabs.addTab(self.verticality_widget, '📐 Вертикальность башни')
        
        # ===== ВКЛАДКА 3: Прямолинейность ствола башни =====
        from gui.straightness_widget import StraightnessWidget
        self.straightness_widget = StraightnessWidget()
        # Передаем ссылку на 3D редактор
        self.straightness_widget.editor_3d = self.editor_3d
        self.main_tabs.addTab(self.straightness_widget, '📏 Прямолинейность поясов башни')
        
        # ===== ВКЛАДКА 4: Отчет =====
        from gui.report_widget import ReportWidget
        self.report_widget = ReportWidget()
        self.main_tabs.addTab(self.report_widget, '📄 Отчет')

        self.full_report_tab = FullReportTab()
        self.main_tabs.addTab(self.full_report_tab, '🧾 Полный отчет')
        
    def create_statusbar(self):
        """Создание статус-бара"""
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        self.statusBar.showMessage('Готов к работе')
        
    def open_file(self):
        """Импорт GEO файла"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            'Импорт GEO файла',
            self.last_open_dir or '',
            'Все поддерживаемые (*.csv *.txt *.shp *.geojson *.json *.dxf *.job *.jxl *.jobxml *.xml *.raw);;'
            'CSV файлы (*.csv *.txt);;'
            'Shapefile (*.shp);;'
            'GeoJSON (*.geojson *.json);;'
            'DXF файлы (*.dxf);;'
            'Trimble файлы (*.job *.jxl *.jobxml *.xml);;'
            'FieldGenius RAW (*.raw)'
        )
        
        if file_path:
            # Сохраняем папку, из которой был загружен файл
            self.last_open_dir = os.path.dirname(file_path)
            self._paths_settings.setValue('last_open_dir', self.last_open_dir)
            self.load_file(file_path)
    
    def import_second_station(self):
        """Импорт данных с другой точки стояния"""
        if self.raw_data is None or self.raw_data.empty:
            QMessageBox.warning(
                self,
                'Нет данных',
                'Сначала загрузите основной файл с точками.'
            )
            return
        
        # ВАЖНО: Используем количество поясов, указанное пользователем при первом импорте
        # Это значение хранится в self.expected_belt_count
        belt_count_from_first = self.expected_belt_count
        
        if belt_count_from_first is None:
            # Fallback: если значение не установлено, используем значение из spinbox
            belt_count_from_first = self.belt_count_spin.value() if self.belt_count_spin else 4
            logger.warning(f"Количество поясов не было установлено, используем значение из spinbox: {belt_count_from_first}")
        else:
            logger.info(f"Используем количество поясов из первого импорта: {belt_count_from_first}")
        
        # Открываем мастер импорта с передачей количества поясов из первого импорта
        wizard = SecondStationImportWizard(self.raw_data, self, belt_count_from_first_import=belt_count_from_first)
        
        if wizard.exec() == QDialog.DialogCode.Accepted:
            merged_data = wizard.get_result_data()
            visualization_data = wizard.get_visualization_data()
            
            if merged_data is not None and not merged_data.empty:
                # Удаляем ошибочную станцию с координатами (0,0)
                try:
                    if 'is_station' in merged_data.columns:
                        md = merged_data.copy()
                        x0 = md['x'].round(6)
                        y0 = md['y'].round(6)
                        station_mask = md['is_station'].fillna(False).astype(bool)
                        zero_station_mask = station_mask & (x0 == 0.0) & (y0 == 0.0)
                        if zero_station_mask.any():
                            zero_idx = md[zero_station_mask].index.tolist()
                            # Сохраняем первую (ожидаемо из первого импорта), удаляем только последующие
                            if len(zero_idx) > 1:
                                to_drop = zero_idx[1:]
                                md = md.drop(index=to_drop).reset_index(drop=True)
                                removed = len(to_drop)
                            else:
                                removed = 0
                            import logging
                            logging.getLogger(__name__).info(f"Удалена(ы) лишняя(ие) точка(и) стояния в (0,0): {removed}")
                            merged_data = md
                except (DataLoadError, ValueError, KeyError) as e:
                    logger.warning(f"Ошибка при обработке точек стояния: {e}")
                    # Продолжаем работу с исходными данными
                
                # Обновляем данные
                self.raw_data = merged_data
                
                # Обновляем виджеты
                self.editor_3d.set_data(self.raw_data)
                # Обновляем таблицы данных (станции и пояса)
                if hasattr(self, 'data_table') and self.data_table is not None:
                    self.data_table.set_data(self.raw_data)
                
                # Передаем данные для визуализации линий соединения, если они есть
                if visualization_data:
                    self.editor_3d.set_belt_connection_lines(visualization_data)
                    try:
                        import numpy as np
                        l1 = visualization_data.get('line1')
                        l2 = visualization_data.get('line2')
                        if l1 and l2:
                            a1 = np.array(l1['start']); b1 = np.array(l1['end'])
                            a2 = np.array(l2['start']); b2 = np.array(l2['end'])
                            v1 = b1 - a1; v2 = b2 - a2
                            v1_xy = np.array([v1[0], v1[1]]); v2_xy = np.array([v2[0], v2[1]])
                            if np.linalg.norm(v1_xy) > 1e-9 and np.linalg.norm(v2_xy) > 1e-9:
                                v1n = v1_xy/np.linalg.norm(v1_xy); v2n = v2_xy/np.linalg.norm(v2_xy)
                                dot = float(np.clip(np.dot(v1n, v2n), -1.0, 1.0))
                                det = float(v1n[0]*v2n[1] - v1n[1]*v2n[0])
                                ang = np.degrees(np.arctan2(det, dot))
                                if hasattr(self, 'line_angle_spin'):
                                    self.line_angle_spin.setValue(round(ang, 1))
                    except (CalculationError, ValueError, KeyError, AttributeError) as e:
                        logger.debug(f"Не удалось вычислить угол между линиями: {e}")
                        # Это не критичная ошибка, продолжаем работу
                
                # Обновляем расчеты
                self.update_analysis_widgets()
                
                self.statusBar.showMessage(
                    f'Импортировано с другой точки стояния: {len(merged_data)} точек', 3000
                )
                logger.info(f"Импорт с другой точки стояния: {len(merged_data)} точек")
            else:
                QMessageBox.warning(
                    self,
                    'Ошибка',
                    'Не удалось объединить данные.'
                )
            
    def get_settings_file_path(self, data_file_path: str) -> str:
        """Получить путь к файлу настроек для данного файла данных"""
        base_name = os.path.splitext(data_file_path)[0]
        return f"{base_name}.sorting.json"
    
    def load_sorting_settings(self, data_file_path: str) -> Optional[dict]:
        """Загрузить настройки сортировки из файла"""
        settings_file = self.get_settings_file_path(data_file_path)
        
        if os.path.exists(settings_file):
            try:
                with open(settings_file, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                logger.info(f"Загружены настройки сортировки из {settings_file}")
                return settings
            except (SettingsLoadError, json.JSONDecodeError, IOError, OSError) as e:
                logger.error(f"Ошибка загрузки настроек: {e}")
                return None
        
        return None
    
    def save_sorting_settings(self, data_file_path: str, settings: dict):
        """Сохранить настройки сортировки в файл"""
        settings_file = self.get_settings_file_path(data_file_path)
        
        try:
            with open(settings_file, 'w', encoding='utf-8') as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)
            logger.info(f"Сохранены настройки сортировки в {settings_file}")
        except (SettingsSaveError, IOError, OSError, TypeError) as e:
            logger.error(f"Ошибка сохранения настроек: {e}")
            raise SettingsSaveError(f"Не удалось сохранить настройки: {e}") from e
    
    def save_current_sorting(self):
        """Сохранить текущую сортировку точек по поясам"""
        if not self.current_file_path:
            QMessageBox.warning(self, 'Предупреждение', 
                              'Нет загруженного файла для сохранения сортировки')
            return
        
        if self.raw_data is None or self.raw_data.empty:
            QMessageBox.warning(self, 'Предупреждение', 
                              'Нет данных для сохранения сортировки')
            return
        
        if 'belt' not in self.raw_data.columns:
            QMessageBox.warning(self, 'Предупреждение', 
                              'Данные не содержат информации о поясах')
            return
        
        try:
            # Собираем текущее состояние сортировки
            settings = {
                'belt_count': int(self.raw_data['belt'].max()),
                'excluded_points': [],  # Пока не сохраняем исключенные
                'belt_assignments': {}
            }
            
            # Группируем точки по поясам
            for belt_num in sorted(self.raw_data['belt'].unique()):
                if pd.isna(belt_num):
                    continue
                
                belt_num = int(belt_num)
                belt_points = self.raw_data[self.raw_data['belt'] == belt_num]
                point_names = belt_points['name'].tolist()
                
                settings['belt_assignments'][belt_num] = point_names
            
            # Сохраняем настройки
            self.save_sorting_settings(self.current_file_path, settings)
            
            # Показываем подтверждение
            total_points = len(self.raw_data)
            belt_count = len(settings['belt_assignments'])
            
            QMessageBox.information(
                self,
                'Сохранение завершено',
                f'Сортировка сохранена успешно!\n\n'
                f'Точек: {total_points}\n'
                f'Поясов: {belt_count}\n\n'
                f'При следующей загрузке этого файла\n'
                f'сортировка будет восстановлена автоматически.'
            )
            
            self.statusBar.showMessage(f'Сортировка сохранена: {total_points} точек, {belt_count} поясов')
            
        except (SettingsSaveError, ValueError, KeyError, AttributeError) as e:
            logger.error(f"Ошибка при сохранении сортировки: {e}", exc_info=True)
            QMessageBox.critical(self, 'Ошибка', 
                               f'Ошибка при сохранении сортировки:\n{str(e)}')
    
    def create_sections(self):
        """Создать секции башни с автоматическим добавлением недостающих точек"""
        if self.raw_data is None or self.raw_data.empty:
            QMessageBox.warning(self, 'Предупреждение', 
                              'Нет данных для создания секций')
            return
        
        if 'belt' not in self.raw_data.columns:
            QMessageBox.warning(self, 'Предупреждение', 
                              'Данные не содержат информации о поясах.\n'
                              'Сначала выполните сортировку по поясам.')
            return
        
        try:
            self.statusBar.showMessage('Создание секций...')
            
            # Сохраняем оригинальные данные перед созданием секций
            self.original_data_before_sections = self.raw_data.copy()
            
            # 1. Находим уровни секций
            section_levels = find_section_levels(self.raw_data, height_tolerance=0.3)
            
            if not section_levels:
                QMessageBox.warning(self, 'Предупреждение', 
                                  'Не удалось определить уровни секций')
                return
            
            # 2. Добавляем недостающие точки
            initial_count = len(self.raw_data)
            data_with_sections = add_missing_points_for_sections(
                self.raw_data, section_levels, height_tolerance=0.3
            )
            added_count = len(data_with_sections) - initial_count
            
            # 3. Обновляем данные через команду
            from core.undo_manager import DataChangeCommand
            
            old_data = self.raw_data.copy(deep=True) if self.raw_data is not None else pd.DataFrame()
            new_data = data_with_sections.copy(deep=True)
            
            def data_getter():
                return self.raw_data if self.raw_data is not None else pd.DataFrame()
            
            def data_setter(data):
                self.raw_data = data
                if hasattr(self, 'data_table'):
                    self.data_table.set_data(data)
                if hasattr(self, 'editor_3d'):
                    self.editor_3d.set_data(data)
            
            create_sections_command = DataChangeCommand(
                data_getter,
                data_setter,
                old_data,
                new_data,
                f"Создание секций ({len(section_levels)} секций, добавлено {added_count} точек)"
            )
            
            # Выполняем команду через undo_manager
            self.undo_manager.execute_command(create_sections_command)
            self._update_undo_redo_actions()
            self.has_unsaved_changes = True  # Отмечаем изменения
            
            # Метод удаления секций доступен через 3D редактор
            
            # 4. Получаем линии секций для визуализации
            section_lines = get_section_lines(data_with_sections, section_levels, height_tolerance=0.3)
            
            # 5. Передаем линии секций в 3D редактор для отрисовки
            if hasattr(self.editor_3d, 'set_section_lines'):
                self.editor_3d.set_section_lines(section_lines)
            
            # Активируем кнопки в 3D редакторе
            if hasattr(self.editor_3d, 'create_sections_action'):
                self.editor_3d.create_sections_action.setEnabled(True)
            if hasattr(self.editor_3d, 'remove_sections_action'):
                self.editor_3d.remove_sections_action.setEnabled(True)
            if hasattr(self.editor_3d, 'build_central_axis_action'):
                self.editor_3d.build_central_axis_action.setEnabled(True)
            
            # Обновляем информационное поле в 3D редакторе
            if hasattr(self.editor_3d, 'info_label'):
                info_text = f'✓ Создано {len(section_levels)} секций, добавлено {added_count} точек'
                self.editor_3d.info_label.setText(info_text)
            
            self.statusBar.showMessage(
                f'Создано {len(section_levels)} секций, добавлено {added_count} точек'
            )
            
            logger.info(f"Создано {len(section_levels)} секций, добавлено {added_count} точек")
            
        except (CalculationError, GroupingError, ValueError, KeyError) as e:
            logger.error(f"Ошибка при создании секций: {e}", exc_info=True)
            QMessageBox.critical(self, 'Ошибка', 
                               f'Ошибка при создании секций:\n{str(e)}')
            self.statusBar.showMessage('Ошибка создания секций')
    
    def remove_sections(self):
        """Удалить все добавленные точки секций, вернуть оригинальные данные"""
        if self.original_data_before_sections is None:
            QMessageBox.warning(self, 'Предупреждение', 
                              'Нет сохраненных оригинальных данных')
            return
        
        try:
            # Восстанавливаем оригинальные данные через команду
            from core.undo_manager import DataChangeCommand
            
            old_data = self.raw_data.copy(deep=True) if self.raw_data is not None else pd.DataFrame()
            new_data = self.original_data_before_sections.copy(deep=True)
            
            def data_getter():
                return self.raw_data if self.raw_data is not None else pd.DataFrame()
            
            def data_setter(data):
                self.raw_data = data
                if hasattr(self, 'data_table'):
                    self.data_table.set_data(data)
                if hasattr(self, 'editor_3d'):
                    self.editor_3d.set_data(data)
            
            remove_sections_command = DataChangeCommand(
                data_getter,
                data_setter,
                old_data,
                new_data,
                "Удаление секций"
            )
            
            # Выполняем команду через undo_manager
            self.undo_manager.execute_command(remove_sections_command)
            self._update_undo_redo_actions()
            self.has_unsaved_changes = True  # Отмечаем изменения
            
            # Очищаем линии секций
            if hasattr(self.editor_3d, 'set_section_lines'):
                self.editor_3d.set_section_lines([])
            
            # Деактивируем кнопки в 3D редакторе
            if hasattr(self.editor_3d, 'remove_sections_action'):
                self.editor_3d.remove_sections_action.setEnabled(False)
            if hasattr(self.editor_3d, 'build_central_axis_action'):
                self.editor_3d.build_central_axis_action.setEnabled(False)
            
            # Очищаем сохраненные данные
            self.original_data_before_sections = None
            
            self.statusBar.showMessage('Секции удалены, данные восстановлены')
            logger.info("Секции удалены, восстановлены оригинальные данные")
            
        except (CalculationError, AttributeError, KeyError) as e:
            logger.error(f"Ошибка при удалении секций: {e}", exc_info=True)
            QMessageBox.critical(self, 'Ошибка', 
                               f'Ошибка при удалении секций:\n{str(e)}')
    
    def load_file(self, file_path: str, use_async: bool = True):
        """
        Загрузка данных из файла через мастер импорта
        
        Args:
            file_path: Путь к файлу
            use_async: Использовать асинхронную загрузку (по умолчанию True)
        """
        if use_async:
            self._load_file_async(file_path)
        else:
            self._load_file_sync(file_path)
    
    def _load_file_async(self, file_path: str):
        """Асинхронная загрузка файла через QThread"""
        from core.data_loader_async import DataLoadThread
        from PyQt6.QtWidgets import QProgressDialog
        
        self.statusBar.showMessage(f'Загрузка {file_path}...')
        self.current_file_path = file_path
        
        # Создаем поток загрузки
        self.load_thread = DataLoadThread(file_path, self)
        
        # Создаем диалог прогресса
        progress_dialog = QProgressDialog(f"Загрузка файла:\n{file_path}", "Отменить", 0, 100, self)
        progress_dialog.setWindowTitle("Загрузка данных")
        progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        progress_dialog.setAutoClose(True)
        progress_dialog.setAutoReset(True)
        
        # Подключаем сигналы
        self.load_thread.progress.connect(progress_dialog.setValue)
        self.load_thread.progress.connect(lambda p, m: progress_dialog.setLabelText(m))
        self.load_thread.data_loaded.connect(lambda data, epsg: self._on_data_loaded_async(data, epsg, progress_dialog))
        self.load_thread.error.connect(lambda msg: self._on_load_error_async(msg, progress_dialog))
        self.load_thread.finished.connect(progress_dialog.reset)
        
        # Кнопка отмены
        progress_dialog.canceled.connect(self.load_thread.cancel)
        
        # Запускаем поток
        self.load_thread.start()
        progress_dialog.exec()
    
    def _on_data_loaded_async(self, data: pd.DataFrame, epsg_code: Optional[int], progress_dialog):
        """Обработка успешной загрузки данных"""
        progress_dialog.setValue(100)
        progress_dialog.close()
        self._process_loaded_data(data, epsg_code)
    
    def _on_load_error_async(self, error_message: str, progress_dialog):
        """Обработка ошибки загрузки"""
        progress_dialog.close()
        QMessageBox.critical(self, 'Ошибка загрузки', f'Ошибка загрузки файла:\n{error_message}')
        self.statusBar.showMessage('Ошибка загрузки')
        self.current_file_path = None
    
    def _load_file_sync(self, file_path: str):
        """Синхронная загрузка файла (старый метод)"""
        try:
            self.statusBar.showMessage(f'Загрузка {file_path}...')
            self.current_file_path = file_path
            
            # Загружаем данные
            data, epsg = load_data_from_file(file_path)
            
            self._process_loaded_data(data, epsg)
            
        except (DataLoadError, FileFormatError, DataValidationError, IOError, OSError) as e:
            logger.error(f"Ошибка загрузки файла: {e}", exc_info=True)
            QMessageBox.critical(self, 'Ошибка', f'Ошибка загрузки файла:\n{str(e)}')
            self.statusBar.showMessage('Ошибка загрузки')
            self.current_file_path = None
    
    def _process_loaded_data(self, data: pd.DataFrame, epsg_code: Optional[int]):
        """Обработка загруженных данных (общий метод для синхронной и асинхронной загрузки)"""
        try:
            # Валидация
            is_valid, message = validate_data(data)
            if not is_valid:
                QMessageBox.warning(self, 'Ошибка валидации', message)
                return
            
            # Загружаем сохраненные настройки сортировки (если есть)
            saved_settings = self.load_sorting_settings(self.current_file_path)
            
            if saved_settings:
                logger.info("Найдены сохраненные настройки сортировки")
            
            # Открываем мастер импорта с сохраненными настройками
            wizard = DataImportWizard(data, saved_settings, self)
            
            if wizard.exec() == QDialog.DialogCode.Accepted:
                # Получаем обработанные данные с назначенными поясами
                processed_data = wizard.get_result()
                
                if processed_data.empty:
                    QMessageBox.warning(self, 'Предупреждение', 
                                      'Нет данных после обработки')
                    return
                
                # Сохраняем EPSG код и путь (данные будут установлены командой)
                self.epsg_code = epsg_code
                # Синхронизируем с project_manager
                self.project_manager.current_file_path = self.current_file_path
                
                # Устанавливаем EPSG в комбобокс
                if epsg_code:
                    for i in range(self.epsg_combo.count()):
                        if self.epsg_combo.itemData(i) == epsg_code:
                            self.epsg_combo.setCurrentIndex(i)
                            break
                
                # Получаем количество поясов из настроек мастера импорта
                sorting_settings = wizard.get_cached_sorting_settings()
                if sorting_settings and 'belt_count' in sorting_settings:
                    belt_count = sorting_settings['belt_count']
                    logger.info(f"Количество поясов взято из настроек мастера импорта: {belt_count}")
                else:
                    # Fallback: определяем как максимальный номер пояса
                    belt_counts = processed_data['belt'].dropna()
                    if len(belt_counts) > 0:
                        belt_count = int(belt_counts.max())
                    else:
                        belt_count = 4  # Значение по умолчанию
                    logger.info(f"Количество поясов определено как максимальный номер пояса: {belt_count}")
                    
                self.belt_count_spin.setValue(belt_count)
                self.expected_belt_count = belt_count
                
                # Определяем количество граней башни
                self._determine_tower_faces(processed_data)
                
                # Создаем blueprint из импортированных данных, если башня составная
                # Создаем blueprint из импортированных данных для конструктора
                from core.tower_generator import create_blueprint_from_imported_data
                
                tower_parts_info = None
                if sorting_settings and sorting_settings.get('tower_type') == 'composite':
                    tower_parts_info = {
                        'split_height': sorting_settings.get('split_height'),
                        'parts': sorting_settings.get('tower_parts', [])
                    }
                
                # Определяем параметры прибора из данных (если есть точка стояния)
                instrument_distance = 60.0
                instrument_angle_deg = 0.0
                instrument_height = 1.7
                
                if 'is_station' in processed_data.columns:
                    station_data = processed_data[processed_data['is_station'] == True]
                    if not station_data.empty:
                        station = station_data.iloc[0]
                        # Вычисляем расстояние и угол от центра башни
                        tower_data = processed_data[processed_data['is_station'] != True]
                        if not tower_data.empty:
                            tower_center = tower_data[['x', 'y']].mean()
                            station_xy = np.array([station['x'], station['y']])
                            center_xy = np.array([tower_center['x'], tower_center['y']])
                            diff = station_xy - center_xy
                            instrument_distance = float(np.linalg.norm(diff))
                            instrument_angle_deg = float(np.degrees(np.arctan2(diff[1], diff[0])))
                            instrument_height = float(station.get('z', 1.7))
                
                # Если нет информации о частях, но есть tower_part в данных, создаем из данных
                if tower_parts_info is None and 'tower_part' in processed_data.columns:
                    unique_parts = sorted(processed_data['tower_part'].dropna().unique())
                    if len(unique_parts) > 1:
                        parts = []
                        for part_num in unique_parts:
                            part_data = processed_data[processed_data['tower_part'] == part_num]
                            if not part_data.empty:
                                # Определяем параметры части
                                faces = int(part_data['belt'].nunique()) if 'belt' in part_data.columns else 4
                                shape = 'prism'  # По умолчанию
                                if 'faces' in part_data.columns:
                                    unique_faces = part_data['faces'].dropna().unique()
                                    if len(unique_faces) > 0:
                                        faces = int(unique_faces[0])
                                
                                parts.append({
                                    'part_number': int(part_num),
                                    'shape': shape,
                                    'faces': faces,
                                })
                        
                        if parts:
                            # Определяем высоту раздвоения
                            part_1_data = processed_data[processed_data['tower_part'] == 1]
                            split_height = float(part_1_data['z'].max()) if not part_1_data.empty else None
                            
                            tower_parts_info = {
                                'split_height': split_height,
                                'parts': parts
                            }
                
                blueprint = create_blueprint_from_imported_data(
                    processed_data,
                    tower_parts_info=tower_parts_info,
                    instrument_distance=instrument_distance,
                    instrument_angle_deg=instrument_angle_deg,
                    instrument_height=instrument_height,
                    base_rotation_deg=0.0
                )
                
                self._tower_blueprint = blueprint
                self.project_manager.tower_builder_state = blueprint.to_dict()
                if hasattr(self.editor_3d, 'set_tower_builder_blueprint'):
                    self.editor_3d.set_tower_builder_blueprint(blueprint)
                logger.info(f"Создан blueprint из импортированных данных: {len(blueprint.segments)} частей")
                
                # Логируем распределение по поясам перед загрузкой
                belt_distribution = processed_data['belt'].value_counts().sort_index()
                logger.info(f"Загружаем данные в главное окно. Распределение по поясам: {belt_distribution.to_dict()}")
                logger.info(f"Первые 5 строк данных:\n{processed_data[['name', 'belt']].head(10)}")
                
                # Создаем команду для импорта данных (ПЕРЕД установкой данных)
                from core.undo_manager import DataChangeCommand
                
                old_data = self.raw_data.copy(deep=True) if self.raw_data is not None else pd.DataFrame()
                new_data = processed_data.copy(deep=True)
                
                def data_getter():
                    return self.raw_data if self.raw_data is not None else pd.DataFrame()
                
                def data_setter(data):
                    self.raw_data = data
                    if hasattr(self, 'data_table'):
                        self.data_table.set_data(data)
                    if hasattr(self, 'editor_3d'):
                        self.editor_3d.set_data(data)
                
                import_command = DataChangeCommand(
                    data_getter,
                    data_setter,
                    old_data,
                    new_data,
                    f"Импорт данных из {os.path.basename(self.current_file_path) if self.current_file_path else 'файла'}"
                )
                
                # Выполняем команду через undo_manager (она установит данные)
                self.undo_manager.execute_command(import_command)
                
                # Обновляем состояние кнопок undo/redo после импорта
                self._update_undo_redo_actions()
                
                # Активируем кнопки
                self.save_project_btn.setEnabled(True)
                # Кнопки работы с секциями находятся в 3D редакторе
                
                # НЕ сохраняем настройки автоматически - пользователь сделает это сам через кнопку
                
                # Обновляем виджеты анализа
                self.update_analysis_widgets()
                
                self.statusBar.showMessage(f'Загружено {len(processed_data)} точек, {belt_count} поясов')
                logger.info(f"Загружено {len(processed_data)} точек с {belt_count} поясами")
            else:
                self.statusBar.showMessage('Загрузка отменена')
                self.current_file_path = None
            
        except (DataLoadError, FileFormatError, DataValidationError, IOError, OSError) as e:
            logger.error(f"Ошибка загрузки файла: {e}", exc_info=True)
            QMessageBox.critical(self, 'Ошибка', f'Ошибка загрузки файла:\n{str(e)}')
            self.statusBar.showMessage('Ошибка загрузки')
            
    def calculate(self, use_async: bool = True):
        """
        Выполнение расчетов (асинхронно или синхронно)
        
        Args:
            use_async: Использовать асинхронную загрузку (по умолчанию True)
        """
        if self.raw_data is None or self.raw_data.empty:
            QMessageBox.warning(self, 'Предупреждение', 'Нет данных для расчета')
            return
        
        if use_async:
            self._calculate_async()
        else:
            self._calculate_sync()
    
    def _calculate_async(self):
        """Асинхронное выполнение расчетов через QThread"""
        from core.calculation_thread import CalculationThread
        from PyQt6.QtWidgets import QProgressDialog
        
        # Получаем текущие данные из таблицы
        current_data = self.data_table.get_data()
        
        # Проверяем, что есть данные
        if current_data.empty:
            QMessageBox.warning(self, 'Ошибка', 'Таблица данных пуста. Загрузите данные или проверьте таблицу.')
            return
        
        self.statusBar.showMessage('Подготовка расчетов...')
        
        # Сохраняем активную станцию для восстановления после расчетов
        self._saved_active_station = getattr(self.data_table, 'active_station_id', None)
        
        # Создаем поток расчетов
        self.calculation_thread = CalculationThread(
            raw_data=self.raw_data,
            table_data=current_data,
            epsg_code=self.epsg_code,
            height_tolerance=self.height_tolerance,
            center_method=self.center_method,
            use_assigned_belts=True,
            parent=self
        )
        
        # Создаем диалог прогресса
        progress_dialog = QProgressDialog("Выполнение расчетов...", "Отменить", 0, 100, self)
        progress_dialog.setWindowTitle("Расчеты")
        progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        progress_dialog.setAutoClose(True)
        progress_dialog.setAutoReset(True)
        progress_dialog.setMinimumDuration(500)  # Показывать через 500мс
        
        # Подключаем сигналы
        self.calculation_thread.progress.connect(progress_dialog.setValue)
        self.calculation_thread.progress.connect(lambda p, m: progress_dialog.setLabelText(m))
        self.calculation_thread.calculation_finished.connect(
            lambda results: self._on_calculation_finished_async(results, progress_dialog)
        )
        self.calculation_thread.error.connect(
            lambda msg: self._on_calculation_error_async(msg, progress_dialog)
        )
        self.calculation_thread.finished.connect(progress_dialog.reset)
        
        # Кнопка отмены
        progress_dialog.canceled.connect(self.calculation_thread.cancel)
        
        # Запускаем поток
        self.calculation_thread.start()
    
    def _on_calculation_finished_async(self, results: Dict[str, Any], progress_dialog):
        """Обработка завершения асинхронных расчетов"""
        progress_dialog.close()
        
        try:
            self.processed_data = results
            self.data_table.set_processed_results(results)
            if hasattr(self.editor_3d, 'set_processed_results'):
                self.editor_3d.set_processed_results(results)
            
            # Обновляем графики анализа
            centers = results['centers']
            self.verticality_widget.set_data(self.raw_data, results)
            self.straightness_widget.set_data(self.raw_data, results)
            
            # Получаем результаты проверки нормативов
            vertical_check = results.get('vertical_check', {'passed': 0, 'failed': 0})
            straightness_check = results.get('straightness_check', {'passed': 0, 'failed': 0})
            
            # Обновляем виджет отчета
            self.report_widget.epsg_code = self.epsg_code
            if self.current_file_path:
                import os
                project_name = os.path.splitext(os.path.basename(self.current_file_path))[0]
                self.report_widget.project_name = project_name
            else:
                self.report_widget.project_name = "Отчет по геодезическому контролю"
            self.report_widget.editor_3d = self.editor_3d
            self.report_widget.set_data(
                self.raw_data,
                results,
                verticality_widget=self.verticality_widget,
                straightness_widget=self.straightness_widget,
                data_table_widget=self.data_table
            )
            self._update_full_report_context()
            
            # Отображаем результаты в статус-баре и информационных окнах
            results_text = (
                f'✓ Расчет завершен: Поясов - {len(centers)}; '
                f'Вертикальность: ✓{vertical_check["passed"]} ✗{vertical_check["failed"]}; '
                f'Прямолинейность: ✓{straightness_check["passed"]} ✗{straightness_check["failed"]}'
            )
            self.statusBar.showMessage(results_text, 10000)
            
            # Обновляем информационные окна виджетов
            self.verticality_widget.info_label.setText(results_text)
            self.straightness_widget.info_label.setText(results_text)
            
            logger.info(f"Расчет завершен: {results_text}")
            
            # Восстанавливаем активную станцию
            if hasattr(self, '_saved_active_station') and self._saved_active_station is not None:
                try:
                    self.data_table.set_active_station(self._saved_active_station)
                except (AttributeError, ValueError, KeyError) as e:
                    logger.debug(f"Не удалось установить активную станцию: {e}")
            
        except Exception as e:
            logger.error(f"Ошибка при обработке результатов расчетов: {e}", exc_info=True)
            QMessageBox.critical(self, 'Ошибка', f'Ошибка при обработке результатов:\n{str(e)}')
    
    def _on_calculation_error_async(self, error_message: str, progress_dialog):
        """Обработка ошибки асинхронных расчетов"""
        progress_dialog.close()
        logger.error(f"Ошибка расчета: {error_message}", exc_info=True)
        QMessageBox.critical(self, 'Ошибка расчета', f'Произошла ошибка:\n{error_message}')
        self.statusBar.showMessage('Ошибка расчета')
    
    def _calculate_sync(self):
        """Синхронное выполнение расчетов (для обратной совместимости)"""
        try:
            self.statusBar.showMessage('Выполнение расчетов...')
            
            # Получаем текущие данные из таблицы
            current_data = self.data_table.get_data()
            
            # Проверяем, что есть данные
            if current_data.empty:
                QMessageBox.warning(self, 'Ошибка', 'Таблица данных пуста. Загрузите данные или проверьте таблицу.')
                return
            
            current_active_station = getattr(self.data_table, 'active_station_id', None)
            
            # Используем сервис расчетов
            results = self.calculation_service.calculate(
                raw_data=self.raw_data,
                table_data=current_data,
                epsg_code=self.epsg_code,
                height_tolerance=self.height_tolerance,
                center_method=self.center_method,
                use_assigned_belts=True
            )
            
            self.processed_data = results
            self.data_table.set_processed_results(results)
            if hasattr(self.editor_3d, 'set_processed_results'):
                self.editor_3d.set_processed_results(results)
            
            # Обновляем графики анализа
            centers = results['centers']
            self.verticality_widget.set_data(self.raw_data, results)
            self.straightness_widget.set_data(self.raw_data, results)
            
            # Получаем результаты проверки нормативов из сервиса
            vertical_check = results.get('vertical_check', {'passed': 0, 'failed': 0})
            straightness_check = results.get('straightness_check', {'passed': 0, 'failed': 0})
            
            # Сохраняем результаты проверки в processed_data для отчета
            results['vertical_check'] = vertical_check
            results['straightness_check'] = straightness_check
            
            # Обновляем виджет отчета
            self.report_widget.epsg_code = self.epsg_code
            if self.current_file_path:
                import os
                project_name = os.path.splitext(os.path.basename(self.current_file_path))[0]
                self.report_widget.project_name = project_name
            else:
                self.report_widget.project_name = "Отчет по геодезическому контролю"
            self.report_widget.editor_3d = self.editor_3d  # Передаем ссылку на 3D редактор
            self.report_widget.set_data(
                self.raw_data,
                results,
                verticality_widget=self.verticality_widget,
                straightness_widget=self.straightness_widget,
                data_table_widget=self.data_table
            )
            
            # Отображаем результаты в статус-баре и информационных окнах
            results_text = (
                f'✓ Расчет завершен: Поясов - {len(centers)}; '
                f'Вертикальность: ✓{vertical_check["passed"]} ✗{vertical_check["failed"]}; '
                f'Прямолинейность: ✓{straightness_check["passed"]} ✗{straightness_check["failed"]}'
            )
            self.statusBar.showMessage(results_text, 10000)  # Показываем 10 секунд
            
            # Обновляем информационные окна виджетов
            self.verticality_widget.info_label.setText(results_text)
            self.straightness_widget.info_label.setText(results_text)
            
            logger.info(f"Расчет завершен: {results_text}")
            
            if current_active_station is not None:
                try:
                    self.data_table.set_active_station(current_active_station)
                except (AttributeError, ValueError, KeyError) as e:
                    logger.debug(f"Не удалось установить активную станцию: {e}")
            
        except (CalculationError, InsufficientDataError, InvalidCoordinatesError, GroupingError, CoordinateTransformError) as e:
            logger.error(f"Ошибка расчета: {str(e)}", exc_info=True)
            QMessageBox.critical(self, 'Ошибка расчета', f'Произошла ошибка:\n{str(e)}')
            self.statusBar.showMessage('Ошибка расчета')
            
    def save_report(self):
        """Сохранение отчета"""
        if self.processed_data is None:
            QMessageBox.warning(self, 'Предупреждение', 'Нет данных для сохранения. Выполните расчет.')
            return
        
        file_path, filter_type = QFileDialog.getSaveFileName(
            self,
            'Сохранить отчет',
            'Отчет по геодезическому контролю',
            'PDF файлы (*.pdf);;Word файлы (*.docx);;Excel файлы (*.xlsx)'
        )
        
        if file_path:
            try:
                if 'PDF' in filter_type or 'Word' in filter_type:
                    # Показываем диалог для ввода информации об объекте
                    from gui.report_dialog import ReportInfoDialog
                    
                    dialog = ReportInfoDialog(self)
                    if dialog.exec() == QDialog.DialogCode.Accepted:
                        report_info = dialog.get_report_info()
                        
                        if 'PDF' in filter_type:
                            # Используем расширенный генератор для PDF
                            from utils.report_generator_enhanced import EnhancedReportGenerator
                            
                            # Получаем данные угловых измерений из таблицы данных
                            angular_measurements = None
                            if hasattr(self.data_table, 'get_angular_measurements'):
                                try:
                                    angular_measurements = self.data_table.get_angular_measurements()
                                except Exception as e:
                                    logger.warning(f"Не удалось получить данные угловых измерений: {e}")
                            
                            generator = EnhancedReportGenerator()
                            generator.generate_professional_pdf(
                                self.raw_data,
                                self.processed_data,
                                file_path,
                                project_name=report_info['project_name'],
                                organization=report_info['organization'],
                                vertical_plot_widget=self.verticality_widget,
                                straightness_plot_widget=self.straightness_widget,
                                angular_measurements=angular_measurements
                            )
                            
                            QMessageBox.information(
                                self, 
                                'Успех', 
                                f'Профессиональный PDF отчет сохранен:\n{file_path}\n\n'
                                f'Объект: {report_info["project_name"]}'
                            )
                        else:  # DOCX
                            # Используем расширенный генератор для DOCX
                            from utils.report_generator_enhanced import EnhancedReportGenerator
                            
                            # Получаем данные угловых измерений из таблицы данных
                            angular_measurements = None
                            if hasattr(self.data_table, 'get_angular_measurements'):
                                try:
                                    angular_measurements = self.data_table.get_angular_measurements()
                                except Exception as e:
                                    logger.warning(f"Не удалось получить данные угловых измерений: {e}")
                            
                            generator = EnhancedReportGenerator()
                            generator.generate_professional_docx(
                                self.raw_data,
                                self.processed_data,
                                file_path,
                                project_name=report_info['project_name'],
                                organization=report_info['organization'],
                                verticality_widget=self.verticality_widget,
                                straightness_widget=self.straightness_widget,
                                angular_measurements=angular_measurements
                            )
                            
                            QMessageBox.information(
                                self, 
                                'Успех', 
                                f'Word отчет (DOCX) сохранен:\n{file_path}\n\n'
                                f'Объект: {report_info["project_name"]}'
                            )
                    else:
                        return  # Пользователь отменил
                else:
                    # Excel отчет
                    from utils.report_generator import ReportGenerator
                    
                    generator = ReportGenerator()
                    generator.generate_excel_report(
                        self.raw_data,
                        self.processed_data,
                        file_path
                    )
                    
                    QMessageBox.information(self, 'Успех', f'Excel отчет сохранен:\n{file_path}')
                
            except (ReportGenerationError, PDFGenerationError, ExcelGenerationError, IOError, OSError) as e:
                QMessageBox.critical(self, 'Ошибка', f'Ошибка сохранения отчета:\n{str(e)}')
    
    def save_project(self):
        """Быстрое сохранение проекта (если путь уже известен)"""
        if self.raw_data is None or self.raw_data.empty:
            self.statusBar.showMessage('⚠ Нет данных для сохранения')
            return
        
        # Если проект уже сохранен - сохраняем по тому же пути
        if self.project_manager.current_project_path:
            self._save_project_to_file(self.project_manager.current_project_path)
        else:
            # Иначе запрашиваем путь
            self.save_project_as()
    
    def save_project_as(self):
        """Сохранение проекта с запросом имени файла"""
        if self.raw_data is None or self.raw_data.empty:
            self.statusBar.showMessage('⚠ Нет данных для сохранения')
            return
        
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            'Сохранить проект',
            self.last_open_dir or '',
            'Проект GeoVertical (*.gvproj)'
        )
        
        if file_path:
            # Сохраняем папку, в которую был сохранен проект
            self.last_open_dir = os.path.dirname(file_path)
            self._paths_settings.setValue('last_open_dir', self.last_open_dir)
            self._save_project_to_file(file_path)
    
    def _save_project_to_file(self, file_path: str):
        """Внутренний метод сохранения проекта в файл"""
        try:
            # Получаем section_data из 3D редактора
            section_data = None
            if hasattr(self.editor_3d, 'section_data'):
                section_data = self.editor_3d.section_data
            
            xy_plane_state = None
            if hasattr(self.editor_3d, 'get_xy_plane_state'):
                xy_plane_state = self.editor_3d.get_xy_plane_state()
            
            tower_builder_state = (
                self._tower_blueprint.to_dict() if self._tower_blueprint else None
            )

            # Используем ProjectManager для сохранения
            full_report_state = (
                self.full_report_tab.serialize_state() if self.full_report_tab is not None else None
            )
            
            # Сериализуем историю undo/redo
            undo_history = self.undo_manager.serialize()

            self.project_manager.save_project(
                file_path=file_path,
                raw_data=self.raw_data,
                processed_data=self.processed_data,
                epsg_code=self.epsg_code,
                current_file_path=self.current_file_path,
                original_data_before_sections=self.original_data_before_sections,
                height_tolerance=self.height_tolerance,
                center_method=self.center_method,
                expected_belt_count=self.expected_belt_count,
                tower_faces_count=self.tower_faces_count,
                xy_plane_state=xy_plane_state,
                section_data=section_data,
                tower_builder_state=tower_builder_state,
                full_report_state=full_report_state,
                undo_history=undo_history,
            )
            
            # Активируем кнопку быстрого сохранения
            self.save_project_btn.setEnabled(True)
            
            # Обновляем заголовок окна
            import os
            project_name = os.path.basename(file_path)
            self.setWindowTitle(f'GeoVertical Analyzer - {project_name}')
            
            self.statusBar.showMessage(f'✓ Проект сохранен: {file_path}', 3000)
            self.has_unsaved_changes = False  # Сбрасываем флаг после сохранения
            
        except ProjectSaveError as e:
            logger.error(f"Ошибка сохранения проекта: {e}", exc_info=True)
            self.statusBar.showMessage(f'❌ Ошибка сохранения проекта: {str(e)}')
            QMessageBox.critical(self, 'Ошибка', f'Ошибка сохранения проекта:\n{str(e)}')
    
    def new_project(self, preserve_builder: bool = False, show_message: bool = True):
        """Создание нового проекта - очистка всех данных и состояния"""
        # Проверяем наличие несохраненных изменений или загруженного проекта с данными
        has_data = self.raw_data is not None and not self.raw_data.empty
        has_project = self.project_manager.current_project_path is not None
        
        if (self.has_unsaved_changes or (has_data and has_project)):
            reply = QMessageBox.question(
                self,
                'Несохраненные изменения',
                'У вас есть несохраненные изменения.\n\n'
                'Сохранить проект перед созданием нового?',
                QMessageBox.StandardButton.Save |
                QMessageBox.StandardButton.Discard |
                QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Save
            )
            
            if reply == QMessageBox.StandardButton.Cancel:
                return False
            elif reply == QMessageBox.StandardButton.Save:
                # Пытаемся сохранить
                if self.project_manager.current_project_path:
                    try:
                        self._save_project_to_file(self.project_manager.current_project_path)
                        self.has_unsaved_changes = False
                    except Exception as e:
                        logger.error(f"Ошибка сохранения при создании нового проекта: {e}", exc_info=True)
                        QMessageBox.warning(
                            self,
                            'Ошибка сохранения',
                            f'Не удалось сохранить проект:\n{str(e)}\n\n'
                            'Создать новый проект без сохранения?'
                        )
                        # Если пользователь отменил, прерываем выполнение
                        return False
                else:
                    # Проект не сохранен - предлагаем сохранить как
                    self.save_project_as()
                    # Если пользователь отменил сохранение, прерываем выполнение
                    if self.has_unsaved_changes:
                        return False
        
        # Очистка данных
        self.raw_data = None
        self.processed_data = None
        self.epsg_code = None
        self.current_file_path = None
        self.original_data_before_sections = None
        if not preserve_builder:
            self._tower_blueprint = None
        
        # Сброс настроек расчетов к значениям по умолчанию
        self.height_tolerance = 0.1
        self.center_method = 'mean'
        self.expected_belt_count = None
        self.tower_faces_count = None

        if self.full_report_tab is not None:
            self.full_report_tab.clear_form()
            self.full_report_tab.set_source_data(None, None)
        
        # Очистка ProjectManager
        self.project_manager.current_project_path = None
        self.project_manager.current_file_path = None
        if not preserve_builder:
            self.project_manager.tower_builder_state = None
        
        # Очистка виджетов
        if self.data_table is not None:
            self.data_table.clear()
            self.data_table.set_processed_results(None)
        
        if self.editor_3d is not None:
            # Полная очистка 3D редактора - удаляем все визуальные элементы из сцены
            if hasattr(self.editor_3d, 'glview') and self.editor_3d.glview is not None:
                # Удаляем точки (scatter plot)
                if hasattr(self.editor_3d, 'point_scatter') and self.editor_3d.point_scatter is not None:
                    try:
                        self.editor_3d.glview.removeItem(self.editor_3d.point_scatter)
                    except Exception:
                        pass
                    self.editor_3d.point_scatter = None
                
                # Удаляем метки точек
                if hasattr(self.editor_3d, 'point_labels'):
                    for label in self.editor_3d.point_labels:
                        try:
                            self.editor_3d.glview.removeItem(label)
                        except Exception:
                            pass
                    self.editor_3d.point_labels.clear()
                
                # Удаляем линии поясов
                if hasattr(self.editor_3d, 'belt_lines'):
                    for line in self.editor_3d.belt_lines:
                        try:
                            self.editor_3d.glview.removeItem(line)
                        except Exception:
                            pass
                    self.editor_3d.belt_lines.clear()
                
                # Удаляем полилинии поясов
                if hasattr(self.editor_3d, 'belt_polylines'):
                    for belt_num, polyline in list(self.editor_3d.belt_polylines.items()):
                        try:
                            self.editor_3d.glview.removeItem(polyline)
                        except Exception:
                            pass
                    self.editor_3d.belt_polylines.clear()
                
                # Удаляем линии соединения поясов
                if hasattr(self.editor_3d, 'belt_connection_lines'):
                    for line in self.editor_3d.belt_connection_lines:
                        try:
                            self.editor_3d.glview.removeItem(line)
                        except Exception:
                            pass
                    self.editor_3d.belt_connection_lines.clear()
                
                # Удаляем линии секций
                if hasattr(self.editor_3d, 'section_lines'):
                    for line in self.editor_3d.section_lines:
                        try:
                            self.editor_3d.glview.removeItem(line)
                        except Exception:
                            pass
                    self.editor_3d.section_lines.clear()
                
                # Удаляем центральную ось
                if hasattr(self.editor_3d, 'central_axis_line') and self.editor_3d.central_axis_line is not None:
                    try:
                        self.editor_3d.glview.removeItem(self.editor_3d.central_axis_line)
                    except Exception:
                        pass
                    self.editor_3d.central_axis_line = None
                
                # Удаляем оси координат
                if hasattr(self.editor_3d, 'axis_items'):
                    for item in self.editor_3d.axis_items:
                        try:
                            self.editor_3d.glview.removeItem(item)
                        except Exception:
                            pass
                    self.editor_3d.axis_items.clear()
                
                # Удаляем плоскость XY
                if hasattr(self.editor_3d, 'xy_plane_item') and self.editor_3d.xy_plane_item is not None:
                    try:
                        self.editor_3d.glview.removeItem(self.editor_3d.xy_plane_item)
                    except Exception:
                        pass
                    self.editor_3d.xy_plane_item = None
            
            # Сбрасываем все переменные состояния к начальным значениям
            if hasattr(self.editor_3d, 'data'):
                self.editor_3d.data = None
            if hasattr(self.editor_3d, 'point_index_counter'):
                self.editor_3d.point_index_counter = 0
            if hasattr(self.editor_3d, 'selected_indices'):
                self.editor_3d.selected_indices = []
            if hasattr(self.editor_3d, 'section_data'):
                self.editor_3d.section_data = []
            if hasattr(self.editor_3d, 'show_central_axis'):
                self.editor_3d.show_central_axis = False
            if hasattr(self.editor_3d, 'xy_plane_initialized'):
                self.editor_3d.xy_plane_initialized = False
            if hasattr(self.editor_3d, 'xy_plane_center'):
                self.editor_3d.xy_plane_center = np.array([0.0, 0.0, 0.0], dtype=float)
            if hasattr(self.editor_3d, 'xy_plane_size'):
                self.editor_3d.xy_plane_size = 10.0
            if hasattr(self.editor_3d, 'is_selecting'):
                self.editor_3d.is_selecting = False
            if hasattr(self.editor_3d, 'drag_start_pos'):
                self.editor_3d.drag_start_pos = None
            if hasattr(self.editor_3d, 'belt_selection_mode'):
                self.editor_3d.belt_selection_mode = False
            if hasattr(self.editor_3d, 'pending_point_idx'):
                self.editor_3d.pending_point_idx = None
            if hasattr(self.editor_3d, 'belt_mass_move_mode'):
                self.editor_3d.belt_mass_move_mode = False
            if hasattr(self.editor_3d, 'pending_belt_num'):
                self.editor_3d.pending_belt_num = None
            if hasattr(self.editor_3d, 'section_selection_mode'):
                self.editor_3d.section_selection_mode = False
            if hasattr(self.editor_3d, 'section_alignment_mode'):
                self.editor_3d.section_alignment_mode = False
            if hasattr(self.editor_3d, 'section_deletion_mode'):
                self.editor_3d.section_deletion_mode = False
            if hasattr(self.editor_3d, 'processed_results'):
                self.editor_3d.processed_results = None
            if hasattr(self.editor_3d, 'active_station_index'):
                self.editor_3d.active_station_index = None
            if hasattr(self.editor_3d, 'station_indices'):
                self.editor_3d.station_indices = []
            if hasattr(self.editor_3d, '_index_to_position'):
                self.editor_3d._index_to_position = {}
            if hasattr(self.editor_3d, '_last_visualization_data'):
                self.editor_3d._last_visualization_data = None
            
            # Очищаем данные через метод (это также обновит индексы)
            self.editor_3d.set_data(pd.DataFrame())
            if hasattr(self.editor_3d, 'set_processed_results'):
                self.editor_3d.set_processed_results(None)
            
            # Очищаем линии соединения поясов через метод (если есть)
            if hasattr(self.editor_3d, 'set_belt_connection_lines'):
                self.editor_3d.set_belt_connection_lines({})
            
            # Сбрасываем камеру
            if hasattr(self.editor_3d, 'reset_camera'):
                self.editor_3d.reset_camera()
            
            # Обновляем виджет
            if hasattr(self.editor_3d, 'update'):
                self.editor_3d.update()
        
        # Сброс значений виджетов к значениям по умолчанию
        if self.belt_count_spin is not None:
            self.belt_count_spin.setValue(10)
        
        if self.auto_belt_checkbox is not None:
            self.auto_belt_checkbox.setChecked(True)
        
        if hasattr(self, 'epsg_combo') and self.epsg_combo is not None:
            self.epsg_combo.setCurrentIndex(0)  # Устанавливаем "Авто"
        
        # Очистка Undo/Redo
        self.undo_manager.clear()
        self._update_undo_redo_actions()
        
        # Сброс флагов
        self.has_unsaved_changes = False
        self.autosave_path = None
        
        # Обновление UI
        self.setWindowTitle('GeoVertical Analyzer - Анализ вертикальности мачт')
        self.update_export_actions_state()
        if hasattr(self, 'save_project_btn') and self.save_project_btn is not None:
            self.save_project_btn.setEnabled(False)
        if show_message:
            self.statusBar.showMessage('Новый проект создан', 3000)
        if hasattr(self.editor_3d, 'set_tower_builder_blueprint'):
            if preserve_builder:
                self.editor_3d.set_tower_builder_blueprint(self._tower_blueprint)
            else:
                self.editor_3d.set_tower_builder_blueprint(None)
        if hasattr(self.editor_3d, 'hide_tower_builder_tab') and not preserve_builder:
            self.editor_3d.hide_tower_builder_tab()
        
        logger.info("Создан новый проект - все данные очищены")
        return True

    def create_tower_from_scratch(self):
        """Активирует встроенный конструктор башни."""
        if not self.new_project(preserve_builder=True, show_message=False):
            return
        if hasattr(self.editor_3d, 'show_tower_builder_tab'):
            self.editor_3d.show_tower_builder_tab()
        self.statusBar.showMessage('Конструктор башни готов к работе', 3000)

    def apply_tower_blueprint(self, blueprint: TowerBlueprint):
        """Применяет blueprint, созданный в конструкторе."""
        if not isinstance(blueprint, TowerBlueprint):
            return

        # Создаем команду для применения blueprint
        from core.undo_manager import TowerBlueprintApplyCommand
        
        command = TowerBlueprintApplyCommand(
            self,
            blueprint,
            "Применение blueprint башни"
        )
        
        # Выполняем команду через undo_manager
        if self.undo_manager.execute_command(command):
            # Получаем metadata для сообщения из уже примененных данных
            if self.raw_data is not None and not self.raw_data.empty:
                belt_count = self.raw_data['belt'].nunique() if 'belt' in self.raw_data.columns else 0
                max_height = self.raw_data['z'].max() if 'z' in self.raw_data.columns else 0.0
                self.statusBar.showMessage(
                    f"Построена новая башня: поясов {belt_count}, высота {max_height:.2f} м",
                    4000,
                )
            else:
                self.statusBar.showMessage('Башня применена', 4000)
            logger.info("Сгенерированы данные башни из конструктора")
            
            # Обновляем состояние кнопок undo/redo
            logger.info(f"После выполнения команды: can_undo={self.undo_manager.can_undo()}, can_redo={self.undo_manager.can_redo()}, undo_stack_len={len(self.undo_manager.undo_stack)}")
            self._update_undo_redo_actions()
        else:
            self.statusBar.showMessage('Ошибка применения blueprint', 3000)
            logger.error("Не удалось применить blueprint")

    def load_project(self):
        """Загрузка проекта"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            'Открыть проект',
            self.last_open_dir or '',
            'Проект GeoVertical (*.gvproj)'
        )
        
        if file_path:
            try:
                self.last_open_dir = os.path.dirname(file_path)
                self._paths_settings.setValue('last_open_dir', self.last_open_dir)
                # Используем ProjectManager для загрузки
                project_data = self.project_manager.load_project(file_path)
                blueprint_state = project_data.get('tower_builder_state')
                if blueprint_state:
                    try:
                        self._tower_blueprint = TowerBlueprint.from_dict(blueprint_state)
                    except Exception:
                        self._tower_blueprint = None
                else:
                    self._tower_blueprint = None
                self.project_manager.tower_builder_state = blueprint_state
                
                # Восстанавливаем данные
                self.raw_data = project_data.get('raw_data')
                self.processed_data = project_data.get('processed_data')
                full_report_state = project_data.get('full_report_state', {})
                self.epsg_code = project_data.get('epsg_code')
                self.current_file_path = project_data.get('current_file_path')
                self.original_data_before_sections = project_data.get('original_data_before_sections')
                # Синхронизируем с project_manager
                self.project_manager.current_file_path = self.current_file_path
                self.height_tolerance = project_data.get('height_tolerance', 0.1)
                self.center_method = project_data.get('center_method', 'mean')
                self.expected_belt_count = project_data.get('expected_belt_count')
                self.tower_faces_count = project_data.get('tower_faces_count')
                
                # Обновляем интерфейс
                if self.raw_data is not None and not self.raw_data.empty:
                    # Сначала устанавливаем количество поясов до установки данных в виджеты
                    if 'belt' in self.raw_data.columns:
                        belt_count = self.raw_data['belt'].nunique()
                        self.belt_count_spin.blockSignals(True)  # Блокируем сигналы
                        self.belt_count_spin.setValue(belt_count)
                        self.belt_count_spin.blockSignals(False)  # Разблокируем
                        self.expected_belt_count = belt_count
                        logger.info(f"Восстановлено количество поясов: {belt_count}")
                    
                    self.data_table.set_data(self.raw_data)
                    self.editor_3d.set_data(self.raw_data)
                    if 'xy_plane_state' in project_data and hasattr(self.editor_3d, 'set_xy_plane_state'):
                        self.editor_3d.set_xy_plane_state(project_data.get('xy_plane_state'))
                    
                    # Восстанавливаем историю Undo/Redo
                    undo_history = project_data.get('undo_history')
                    if undo_history:
                        # Восстанавливаем историю только если есть данные
                        if self.raw_data is not None and not self.raw_data.empty:
                            logger.info(f"Восстановление истории undo/redo из проекта: undo_stack={len(undo_history.get('undo_stack', []))}, redo_stack={len(undo_history.get('redo_stack', []))}")
                            if self.undo_manager.deserialize(undo_history, self):
                                logger.info(f"История успешно восстановлена: can_undo={self.undo_manager.can_undo()}, can_redo={self.undo_manager.can_redo()}")
                            else:
                                logger.warning("Не удалось восстановить историю undo/redo")
                                self.undo_manager.clear()
                        else:
                            # Если данных нет, очищаем историю
                            logger.info("Данных нет, очищаем историю undo/redo")
                            self.undo_manager.clear()
                    else:
                        # Если истории нет в проекте, очищаем
                        logger.info("Истории undo/redo нет в проекте, очищаем")
                        self.undo_manager.clear()
                    self._update_undo_redo_actions()
                    
                    # Восстанавливаем section_data
                    if 'section_data' in project_data:
                        # Сохраняем section_data в 3D редакторе
                        self.editor_3d.section_data = project_data['section_data']
                        
                        # Активируем кнопки работы с секциями
                        has_sections = bool(len(project_data['section_data']) > 0)
                        if hasattr(self.editor_3d, 'remove_sections_action'):
                            self.editor_3d.remove_sections_action.setEnabled(has_sections)
                        if hasattr(self.editor_3d, 'build_central_axis_action'):
                            self.editor_3d.build_central_axis_action.setEnabled(has_sections)
                        if hasattr(self.editor_3d, 'tilt_plane_btn'):
                            self.editor_3d.tilt_plane_btn.setEnabled(has_sections)
                        if hasattr(self.editor_3d, 'tilt_single_section_btn'):
                            self.editor_3d.tilt_single_section_btn.setEnabled(has_sections)
                        
                        # Отрисовываем линии секций
                        if hasattr(self.editor_3d, 'update_section_lines'):
                            self.editor_3d.update_section_lines()
                        
                        logger.info(f"Восстановлено {len(project_data['section_data'])} секций")
                    
                    # Активируем кнопки
                    self.save_project_btn.setEnabled(True)
                    # Кнопки работы с секциями находятся в 3D редакторе
                    
                    logger.info(f"Загружено {len(self.raw_data)} точек из проекта")
                    
                    # Если нет blueprint, но есть данные, создаем blueprint из данных
                    if self._tower_blueprint is None and self.raw_data is not None and not self.raw_data.empty:
                        try:
                            from core.tower_generator import create_blueprint_from_imported_data
                            
                            # Определяем параметры прибора из данных (если есть точка стояния)
                            instrument_distance = 60.0
                            instrument_angle_deg = 0.0
                            instrument_height = 1.7
                            
                            if 'is_station' in self.raw_data.columns:
                                station_data = self.raw_data[self.raw_data['is_station'] == True]
                                if not station_data.empty:
                                    station = station_data.iloc[0]
                                    # Вычисляем расстояние и угол от центра башни
                                    tower_data = self.raw_data[self.raw_data['is_station'] != True]
                                    if not tower_data.empty:
                                        tower_center = tower_data[['x', 'y']].mean()
                                        station_xy = np.array([station['x'], station['y']])
                                        center_xy = np.array([tower_center['x'], tower_center['y']])
                                        diff = station_xy - center_xy
                                        instrument_distance = float(np.linalg.norm(diff))
                                        instrument_angle_deg = float(np.degrees(np.arctan2(diff[1], diff[0])))
                                        instrument_height = float(station.get('z', 1.7))
                            
                            # Определяем информацию о частях башни из данных
                            tower_parts_info = None
                            if 'tower_part' in self.raw_data.columns:
                                unique_parts = sorted(self.raw_data['tower_part'].dropna().unique())
                                if len(unique_parts) > 1:
                                    parts = []
                                    for part_num in unique_parts:
                                        part_data = self.raw_data[self.raw_data['tower_part'] == part_num]
                                        if not part_data.empty:
                                            # Определяем параметры части
                                            faces = int(part_data['belt'].nunique()) if 'belt' in part_data.columns else 4
                                            shape = 'prism'  # По умолчанию
                                            if 'faces' in part_data.columns:
                                                unique_faces = part_data['faces'].dropna().unique()
                                                if len(unique_faces) > 0:
                                                    faces = int(unique_faces[0])
                                            
                                            # Определяем размеры
                                            part_xy = part_data[['x', 'y']].values
                                            center = part_xy.mean(axis=0)
                                            radii = np.linalg.norm(part_xy - center, axis=1)
                                            avg_radius = radii.mean()
                                            base_size = avg_radius * 2.0
                                            
                                            parts.append({
                                                'part_number': int(part_num),
                                                'shape': shape,
                                                'faces': faces,
                                            })
                                    
                                    if parts:
                                        # Определяем высоту раздвоения
                                        part_1_data = self.raw_data[self.raw_data['tower_part'] == 1]
                                        split_height = float(part_1_data['z'].max()) if not part_1_data.empty else None
                                        
                                        tower_parts_info = {
                                            'split_height': split_height,
                                            'parts': parts
                                        }
                            
                            blueprint = create_blueprint_from_imported_data(
                                self.raw_data,
                                tower_parts_info=tower_parts_info,
                                instrument_distance=instrument_distance,
                                instrument_angle_deg=instrument_angle_deg,
                                instrument_height=instrument_height,
                                base_rotation_deg=0.0
                            )
                            
                            self._tower_blueprint = blueprint
                            self.project_manager.tower_builder_state = blueprint.to_dict()
                            logger.info(f"Создан blueprint из данных проекта: {len(blueprint.segments)} частей")
                        except Exception as e:
                            logger.warning(f"Не удалось создать blueprint из данных проекта: {e}")
                            self._tower_blueprint = None
                    
                    # Загружаем blueprint в конструктор
                    if hasattr(self.editor_3d, 'set_tower_builder_blueprint'):
                        self.editor_3d.set_tower_builder_blueprint(self._tower_blueprint)
                    if hasattr(self.editor_3d, 'hide_tower_builder_tab'):
                        self.editor_3d.hide_tower_builder_tab()
                
                # Восстанавливаем результаты расчетов, если они есть
                if self.processed_data is not None:
                    try:
                        self.verticality_widget.set_data(self.raw_data, self.processed_data)
                        self.straightness_widget.set_data(self.raw_data, self.processed_data)
                        if hasattr(self.editor_3d, 'set_processed_results'):
                            self.editor_3d.set_processed_results(self.processed_data)
                        if hasattr(self.data_table, 'set_processed_results'):
                            self.data_table.set_processed_results(self.processed_data)
                    except (CalculationError, AttributeError, KeyError, ValueError) as calc_exc:
                        logger.warning(f"Не удалось восстановить данные анализа: {calc_exc}")
                        self.processed_data = None
                        self.verticality_widget.set_data(self.raw_data, None)
                        self.straightness_widget.set_data(self.raw_data, None)
                        if hasattr(self.editor_3d, 'set_processed_results'):
                            self.editor_3d.set_processed_results(None)
                        if hasattr(self.data_table, 'set_processed_results'):
                            self.data_table.set_processed_results(None)
                else:
                    self.verticality_widget.set_data(self.raw_data, None)
                    self.straightness_widget.set_data(self.raw_data, None)
                    if hasattr(self.editor_3d, 'set_processed_results'):
                        self.editor_3d.set_processed_results(None)
                    if hasattr(self.data_table, 'set_processed_results'):
                        self.data_table.set_processed_results(None)

                # Обновляем доступность функций
                self.update_export_actions_state()
                if hasattr(self.editor_3d, 'update_central_axis') and getattr(self.editor_3d, 'show_central_axis', False):
                    self.editor_3d.update_central_axis()

                # Обновляем заголовок окна
                project_name = os.path.basename(file_path)
                self.setWindowTitle(f'GeoVertical Analyzer - {project_name}')
                
                self.statusBar.showMessage(f'✓ Проект загружен: {file_path}', 3000)
                logger.info(f"Проект загружен: {file_path}")

                if self.full_report_tab is not None:
                    if full_report_state:
                        self.full_report_tab.load_state(full_report_state)
                    else:
                        self.full_report_tab.clear_form()
                    self.full_report_tab.set_source_data(self.raw_data, self.processed_data)
                
            except (ProjectLoadError, IOError, OSError, pickle.UnpicklingError, AttributeError, KeyError, ValueError) as e:
                logger.error(f"Ошибка загрузки проекта: {e}", exc_info=True)
                self.statusBar.showMessage(f'❌ Ошибка загрузки проекта: {str(e)}')
                QMessageBox.critical(self, 'Ошибка', f'Ошибка загрузки проекта:\n{str(e)}')
                
    def add_point(self):
        """Добавление новой точки"""
        # Открываем диалог добавления в 3D редакторе
        self.editor_3d.add_point_dialog()
        
    def delete_selected_points(self):
        """Удаление выбранных точек"""
        # Удаляем через 3D редактор (он синхронизирует с таблицей)
        self.editor_3d.delete_selected_points()
        
    def open_point_filter(self):
        """Открытие 3D фильтра точек"""
        if self.raw_data is None or self.raw_data.empty:
            QMessageBox.warning(self, 'Предупреждение', 'Нет данных для фильтрации')
            return
        
        try:
            # Открываем диалог 3D фильтра
            dialog = PointSelector3DDialog(self.raw_data, self)
            
            # Подключаем сигнал
            dialog.points_filtered.connect(self.on_points_filtered)
            
            # Показываем диалог
            result = dialog.exec()
            
            if result == QDialog.DialogCode.Accepted:
                # Данные уже обработаны через сигнал
                pass
            
        except (FilteringError, AttributeError, ValueError, KeyError) as e:
            logger.error(f"Ошибка фильтрации точек: {e}", exc_info=True)
            QMessageBox.critical(self, 'Ошибка', f'Ошибка фильтрации точек:\n{str(e)}')
    
    def on_points_filtered(self, filtered_data: pd.DataFrame, filter_info: dict):
        """Обработка отфильтрованных точек"""
        try:
            # Обновляем данные
            self.raw_data = filtered_data
            
            # Обновляем таблицу
            self.data_table.set_data(filtered_data)
            
            # Статус
            self.statusBar.showMessage(
                f'Фильтрация применена: {filter_info["selected_points"]}/{filter_info["total_points"]} точек'
            )
            
            # Сообщение пользователю
            msg = f"Фильтрация выполнена!\n\n"
            msg += f"Исходное количество точек: {filter_info['total_points']}\n"
            msg += f"Отобрано для анализа: {filter_info['selected_points']}\n"
            msg += f"Исключено: {filter_info['total_points'] - filter_info['selected_points']}\n\n"
            
            if filter_info.get('auto_filter_applied'):
                analysis = filter_info.get('analysis_info', {})
                msg += f"Найдено поясов башни: {analysis.get('valid_belts', 0)}\n"
            
            msg += "\nМожете продолжить расчет вертикальности."
            
            QMessageBox.information(self, 'Фильтрация завершена', msg)
            
        except (FilteringError, DataLoadError, ValueError, KeyError, AttributeError) as e:
            logger.error(f"Ошибка обработки отфильтрованных данных: {e}", exc_info=True)
            QMessageBox.critical(self, 'Ошибка', f'Ошибка обработки данных:\n{str(e)}')
    
    def clear_data(self):
        """Очистка всех данных"""
        reply = QMessageBox.question(
            self,
            'Подтверждение очистки',
            'Очистить все данные и начать заново?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.raw_data = None
            self.processed_data = None
            self.data_table.clear()
            self.data_table.set_processed_results(None)
            self.editor_3d.set_data(pd.DataFrame())
            # Очистка виджетов анализа уже происходит через set_data
            # Кнопки фильтрации больше нет
            self.statusBar.showMessage('Данные очищены')
            self.update_export_actions_state()
            self.undo_manager.clear()  # Очищаем историю при очистке данных
            self._update_undo_redo_actions()
    
    def undo(self, checked=False):
        """Отменяет последнюю операцию"""
        logger.info(f"Вызов undo: can_undo={self.undo_manager.can_undo()}, undo_stack_len={len(self.undo_manager.undo_stack)}")
        if not self.undo_manager.can_undo():
            logger.warning("Нельзя выполнить undo: стек пуст или выполняется другая команда")
            self.statusBar.showMessage('Нет действий для отмены', 2000)
            return
        if self.undo_manager.undo():
            undo_desc = self.undo_manager.get_redo_description()  # После undo следующая команда для redo
            if undo_desc:
                self.statusBar.showMessage(f'Отменено: {undo_desc}', 2000)
            else:
                self.statusBar.showMessage('Операция отменена', 2000)
            logger.info(f"Undo выполнен успешно: can_undo={self.undo_manager.can_undo()}, can_redo={self.undo_manager.can_redo()}")
            self._update_undo_redo_actions()
            # Обновляем данные в виджетах
            if self.raw_data is not None:
                self.data_table.set_data(self.raw_data)
                if hasattr(self.editor_3d, 'set_data'):
                    self.editor_3d.set_data(self.raw_data)
                
                # Обновляем section_data если есть
                if hasattr(self.editor_3d, 'section_data') and self.editor_3d.section_data:
                    if hasattr(self.editor_3d, 'set_section_lines'):
                        self.editor_3d.set_section_lines(self.editor_3d.section_data)
                
                # Обновляем виджеты анализа
                self.update_export_actions_state()
                if hasattr(self, 'verticality_widget'):
                    self.verticality_widget.set_data(self.raw_data, self.processed_data)
                if hasattr(self, 'straightness_widget'):
                    self.straightness_widget.set_data(self.raw_data, self.processed_data)
            else:
                # Если данных нет, очищаем виджеты
                self.data_table.set_data(pd.DataFrame())
                if hasattr(self.editor_3d, 'set_data'):
                    self.editor_3d.set_data(pd.DataFrame())
                if hasattr(self.editor_3d, 'set_section_lines'):
                    self.editor_3d.set_section_lines([])
                if hasattr(self, 'verticality_widget'):
                    self.verticality_widget.set_data(None, None)
                if hasattr(self, 'straightness_widget'):
                    self.straightness_widget.set_data(None, None)
            
            self.has_unsaved_changes = True
        else:
            self.statusBar.showMessage('Не удалось отменить операцию', 2000)
    
    def redo(self, checked=False):
        """Повторяет последнюю отмененную операцию"""
        logger.info(f"Вызов redo: can_redo={self.undo_manager.can_redo()}, redo_stack_len={len(self.undo_manager.redo_stack)}")
        if not self.undo_manager.can_redo():
            logger.warning("Нельзя выполнить redo: стек пуст или выполняется другая команда")
            self.statusBar.showMessage('Нет действий для повтора', 2000)
            return
        if self.undo_manager.redo():
            redo_desc = self.undo_manager.get_undo_description()  # После redo команда снова в undo
            if redo_desc:
                self.statusBar.showMessage(f'Повторено: {redo_desc}', 2000)
            else:
                self.statusBar.showMessage('Операция повторена', 2000)
            logger.info(f"Redo выполнен успешно: can_undo={self.undo_manager.can_undo()}, can_redo={self.undo_manager.can_redo()}")
            self._update_undo_redo_actions()
            # Обновляем данные в виджетах
            if self.raw_data is not None:
                self.data_table.set_data(self.raw_data)
                if hasattr(self.editor_3d, 'set_data'):
                    self.editor_3d.set_data(self.raw_data)
                
                # Обновляем section_data если есть
                if hasattr(self.editor_3d, 'section_data') and self.editor_3d.section_data:
                    if hasattr(self.editor_3d, 'set_section_lines'):
                        self.editor_3d.set_section_lines(self.editor_3d.section_data)
                
                # Обновляем виджеты анализа
                self.update_export_actions_state()
                if hasattr(self, 'verticality_widget'):
                    self.verticality_widget.set_data(self.raw_data, self.processed_data)
                if hasattr(self, 'straightness_widget'):
                    self.straightness_widget.set_data(self.raw_data, self.processed_data)
            else:
                # Если данных нет, очищаем виджеты
                self.data_table.set_data(pd.DataFrame())
                if hasattr(self.editor_3d, 'set_data'):
                    self.editor_3d.set_data(pd.DataFrame())
                if hasattr(self.editor_3d, 'set_section_lines'):
                    self.editor_3d.set_section_lines([])
                if hasattr(self, 'verticality_widget'):
                    self.verticality_widget.set_data(None, None)
                if hasattr(self, 'straightness_widget'):
                    self.straightness_widget.set_data(None, None)
            
            self.has_unsaved_changes = True
        else:
            self.statusBar.showMessage('Не удалось повторить операцию', 2000)
    
    def _update_undo_redo_actions(self):
        """Обновляет состояние кнопок Undo/Redo"""
        can_undo = self.undo_manager.can_undo()
        can_redo = self.undo_manager.can_redo()
        
        logger.debug(f"_update_undo_redo_actions: can_undo={can_undo}, can_redo={can_redo}, undo_stack_len={len(self.undo_manager.undo_stack)}, redo_stack_len={len(self.undo_manager.redo_stack)}")
        
        # Обновляем действия в меню
        if hasattr(self, 'undo_action'):
            self.undo_action.setEnabled(can_undo)
        if hasattr(self, 'redo_action'):
            self.redo_action.setEnabled(can_redo)
        
        # Обновляем кнопки на панели инструментов
        if hasattr(self, 'undo_btn'):
            self.undo_btn.setEnabled(can_undo)
        if hasattr(self, 'redo_btn'):
            self.redo_btn.setEnabled(can_redo)
        
        # Обновляем текст с описанием команды
        if hasattr(self, 'undo_action'):
            undo_desc = self.undo_manager.get_undo_description()
            if undo_desc:
                self.undo_action.setText(f'Отменить: {undo_desc}')
            else:
                self.undo_action.setText('Отменить')
        
        if hasattr(self, 'redo_action'):
            redo_desc = self.undo_manager.get_redo_description()
            if redo_desc:
                self.redo_action.setText(f'Повторить: {redo_desc}')
            else:
                self.redo_action.setText('Повторить')
    
    def on_epsg_changed(self, index):
        """Обработчик изменения системы координат"""
        epsg = self.epsg_combo.itemData(index)
        if epsg:
            self.epsg_code = epsg
            self.statusBar.showMessage(f'Система координат: EPSG:{epsg}')
            
    def show_batch_processing(self):
        """Показать диалог пакетной обработки"""
        from gui.batch_dialog import BatchProcessingDialog
        
        dialog = BatchProcessingDialog(self)
        dialog.exec()
    
    def show_settings(self):
        """Показать окно настроек"""
        from gui.settings_dialog import SettingsDialog
        
        dialog = SettingsDialog(self)
        dialog.set_height_tolerance(self.height_tolerance)
        dialog.set_center_method(self.center_method)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.height_tolerance = dialog.get_height_tolerance()
            self.center_method = dialog.get_center_method()
            self.statusBar.showMessage('Параметры обновлены')
            
    def on_belt_count_changed(self, value: int):
        """Обработчик изменения количества поясов"""
        if not self.auto_belt_checkbox.isChecked():
            self.expected_belt_count = value
            logger.info(f"Установлено количество поясов: {value}")
    
    def on_auto_belt_toggled(self, checked: bool):
        """Обработчик переключения автоопределения поясов"""
        self.belt_count_spin.setEnabled(not checked)
        if checked:
            self.expected_belt_count = None
            logger.info("Включено автоопределение количества поясов")
        else:
            self.expected_belt_count = self.belt_count_spin.value()
            logger.info(f"Ручное определение поясов: {self.expected_belt_count}")
    
    def _determine_tower_faces(self, data: pd.DataFrame):
        """Определяет количество граней башни на основе данных"""
        if 'belt' not in data.columns:
            logger.warning("Колонка 'belt' не найдена, используем значение по умолчанию")
            self.tower_faces_count = 4
            return
        
        # Находим количество точек на каждом поясе
        belt_counts = {}
        for belt_num in data['belt'].dropna().unique():
            belt_points = data[data['belt'] == belt_num]
            # Исключаем точки стояния
            if 'is_station' in belt_points.columns:
                belt_points = belt_points[~belt_points['is_station'].fillna(False)]
            belt_counts[belt_num] = len(belt_points)
        
        if belt_counts:
            # Берем наиболее частое количество точек на поясе
            from collections import Counter
            count_freq = Counter(belt_counts.values())
            most_common_count = count_freq.most_common(1)[0][0]
            self.tower_faces_count = most_common_count
            logger.info(f"Количество граней определено: {most_common_count} "
                       f"(найдено на поясах: {dict(count_freq)})")
        else:
            self.tower_faces_count = 4
            logger.warning("Не удалось определить количество граней, используем значение по умолчанию: 4")
    
    def auto_filter_points(self):
        """Автоматическая фильтрация и назначение поясов"""
        if self.raw_data is None or self.raw_data.empty:
            QMessageBox.warning(self, 'Предупреждение', 'Нет данных для фильтрации')
            return
        
        try:
            # Определяем количество поясов
            if self.expected_belt_count is None:
                belt_count = estimate_belt_count_from_heights(self.raw_data, self.height_tolerance)
                self.belt_count_spin.setValue(belt_count)
                logger.info(f"Автоопределено поясов: {belt_count}")
            else:
                belt_count = self.expected_belt_count
            
            # Автоматическое назначение поясов
            filtered_data = auto_assign_belts(self.raw_data, belt_count, self.height_tolerance)
            
            # Обновляем данные
            self.raw_data = filtered_data
            self.editor_3d.set_data(filtered_data)
            self.data_table.set_data(filtered_data)
            self.has_unsaved_changes = True  # Отмечаем изменения
            
            self.statusBar.showMessage(f'Автофильтрация выполнена: {belt_count} поясов')
            QMessageBox.information(
                self, 
                'Автофильтрация', 
                f'Успешно назначено {belt_count} поясов для {len(filtered_data)} точек'
            )
            
        except (FilteringError, AutoFilterError, CalculationError, GroupingError) as e:
            logger.error(f"Ошибка автофильтрации: {e}", exc_info=True)
            QMessageBox.critical(self, 'Ошибка', f'Ошибка автофильтрации:\n{str(e)}')
    
    def on_3d_data_changed(self):
        """Обработчик изменения данных в 3D редакторе"""
        # Защита от зацикливания: если уже обновляем виджеты, пропускаем
        if (hasattr(self, '_updating_analysis_widgets') and self._updating_analysis_widgets) or self._suspend_data_sync:
            logger.debug("Пропуск on_3d_data_changed - уже выполняется обновление виджетов")
            return
        
        # Синхронизируем с таблицей
        data = self.editor_3d.get_data()
        if data is not None and not data.empty:
            # КРИТИЧЕСКИ ВАЖНО: проверяем наличие point_index перед передачей в таблицу
            if 'point_index' not in data.columns:
                logger.warning(
                    f"on_3d_data_changed: Колонка 'point_index' отсутствует в данных из editor_3d! "
                    f"Колонки: {list(data.columns)}. "
                    f"Это приведет к проблемам с выбором строк в таблице."
                )
            else:
                logger.debug(
                    f"on_3d_data_changed: Колонка 'point_index' присутствует. "
                    f"Первые 5 значений: {list(data['point_index'].head())}"
                )
            
            # Обновляем таблицу без генерации обратных сигналов
            with self._suspend_data_change_handlers():
                self.data_table.set_data(data)
            self.raw_data = data
        self.processed_data = None
        self.update_analysis_widgets()
        self.statusBar.showMessage('Данные изменены в 3D. Требуется пересчет.')
    
    def on_table_data_changed(self):
        """Обработчик изменения данных в таблице"""
        # Защита от зацикливания: если уже обновляем виджеты, пропускаем
        if (hasattr(self, '_updating_analysis_widgets') and self._updating_analysis_widgets) or self._suspend_data_sync:
            logger.debug("Пропуск on_table_data_changed - уже выполняется обновление виджетов")
            return
        
        # Берем актуальные данные напрямую из DataTable (с сохранением служебных колонок)
        if getattr(self.data_table, 'original_data', None) is not None:
            data = self.data_table.original_data.copy(deep=True)
        else:
            data = self.data_table.get_data()
        if data is None:
            data = pd.DataFrame()

        self.raw_data = data
        
        # Обновляем editor_3d без генерации обратных сигналов
        with self._suspend_data_change_handlers():
            self.editor_3d.set_data(data)

        # Сбрасываем результаты расчетов
        self.processed_data = None
        self.data_table.set_processed_results(None)

        # Обновляем связанные виджеты
        self.update_analysis_widgets()
        self.statusBar.showMessage('Данные изменены в таблице. Требуется пересчет.')
    
    def update_analysis_widgets(self):
        """Обновить виджеты анализа (вертикальность, прямолинейность)"""
        # Защита от зацикливания: проверяем, не выполняется ли уже обновление
        if not hasattr(self, '_updating_analysis_widgets'):
            self._updating_analysis_widgets = False
        
        if self._updating_analysis_widgets:
            logger.debug("Пропуск обновления виджетов анализа - уже выполняется")
            return
        
        self._updating_analysis_widgets = True
        try:
            if self.raw_data is not None and not self.raw_data.empty:
                # Обновляем виджет вертикальности
                self.verticality_widget.set_data(self.raw_data, self.processed_data)
                
                # Обновляем виджет прямолинейности
                self.straightness_widget.set_data(self.raw_data, self.processed_data)
                
                logger.info("Виджеты анализа обновлены")
            self.update_export_actions_state()
            self._update_full_report_context()
        finally:
            self._updating_analysis_widgets = False

    def _update_full_report_context(self):
        if self.full_report_tab is not None:
            self.full_report_tab.set_source_data(self.raw_data, self.processed_data)

    def update_export_actions_state(self):
        """Включает или отключает элементы управления экспортом схемы в зависимости от наличия данных."""
        has_data = (
            self.editor_3d is not None
            and getattr(self.editor_3d, "data", None) is not None
            and not getattr(self.editor_3d, "data").empty
        )
        if self.export_schema_action is not None:
            self.export_schema_action.setEnabled(has_data)

    def _build_schema_export_metadata(self) -> Dict[str, Any]:
        """Формирует метаданные для сохранения в DXF."""
        metadata: Dict[str, Any] = {
            "source_file": self.current_file_path or "",
            "project_file": self.project_manager.current_project_path or "",
            "epsg_code": self.epsg_code if self.epsg_code is not None else "",
            "height_tolerance_m": self.height_tolerance,
            "center_method": self.center_method,
        }
        if self.expected_belt_count is not None:
            metadata["expected_belt_count"] = self.expected_belt_count
        if self.tower_faces_count is not None:
            metadata["tower_faces_count"] = self.tower_faces_count
        return metadata

    def export_schema_dialog(self):
        """Открывает диалог выбора файла и выполняет экспорт схемы в выбранный формат."""
        if self.editor_3d is None or getattr(self.editor_3d, "data", None) is None or self.editor_3d.data.empty:
            QMessageBox.warning(self, 'Экспорт схемы', 'Нет данных для экспорта. Загрузите или подготовьте схему.')
            return

        default_dir = self.project_manager.current_project_path or (self.current_file_path and os.path.dirname(self.current_file_path))
        if not default_dir:
            default_dir = os.getcwd()

        default_name = "geo_vertical_schema.dxf"
        if self.current_file_path:
            base_name = os.path.splitext(os.path.basename(self.current_file_path))[0]
            default_name = f"{base_name}_schema.dxf"

        filters = 'DXF файлы (*.dxf);;PDF файлы (*.pdf);;GeoJSON файлы (*.geojson);;KML файлы (*.kml)'
        file_path, selected_filter = QFileDialog.getSaveFileName(
            self,
            'Экспорт схемы',
            os.path.join(default_dir, default_name),
            filters
        )

        if not file_path:
            return

        save_path = Path(file_path)
        suffix = save_path.suffix.lower()
        if not suffix:
            # Определяем расширение по выбранному фильтру
            if 'pdf' in (selected_filter or '').lower():
                suffix = '.pdf'
            elif 'geojson' in (selected_filter or '').lower():
                suffix = '.geojson'
            elif 'kml' in (selected_filter or '').lower():
                suffix = '.kml'
            else:
                suffix = '.dxf'
            save_path = save_path.with_suffix(suffix)

        try:
            section_data = getattr(self.editor_3d, 'section_data', []) or []
            schema = build_schema_data(
                self.editor_3d.get_data(),
                section_data=section_data,
                processed_data=self.processed_data,
                metadata=self._build_schema_export_metadata()
            )

            if suffix == '.dxf':
                export_schema_to_dxf(schema, str(save_path), DxfExportOptions())
                QMessageBox.information(self, 'Экспорт схемы', f'Схема успешно экспортирована в DXF:\n{save_path}')
            elif suffix == '.pdf':
                export_schema_to_pdf(schema, str(save_path))
                QMessageBox.information(self, 'Экспорт схемы', f'Схема успешно экспортирована в PDF:\n{save_path}')
            elif suffix == '.geojson':
                from core.exporters.geojson_exporter import export_data_to_geojson
                export_data_to_geojson(
                    self.editor_3d.get_data(),
                    str(save_path),
                    epsg_code=self.epsg_code,
                    include_metadata=True
                )
                QMessageBox.information(self, 'Экспорт данных', f'Данные успешно экспортированы в GeoJSON:\n{save_path}')
            elif suffix == '.kml':
                from core.exporters.kml_exporter import export_data_to_kml
                project_name = os.path.splitext(os.path.basename(self.current_file_path or "project"))[0] if self.current_file_path else "GeoVertical Points"
                export_data_to_kml(
                    self.editor_3d.get_data(),
                    str(save_path),
                    name=project_name,
                    description=f"Экспорт из GeoVertical Analyzer\nEPSG: {self.epsg_code or 'не указан'}",
                    epsg_code=self.epsg_code
                )
                QMessageBox.information(self, 'Экспорт данных', f'Данные успешно экспортированы в KML:\n{save_path}\n\nМожно открыть в Google Earth')
            else:
                raise ValueError(f"Неподдерживаемое расширение файла: {suffix}")

        except (SchemaExportError, ExportError, IOError, OSError, ValueError, AttributeError) as exc:
            logger.error("Ошибка экспорта схемы: %s", exc, exc_info=True)
            QMessageBox.critical(self, 'Ошибка экспорта', f'Не удалось экспортировать схему:\n{exc}')
    
    def _normalize_index_to_point_index(self, idx: Any) -> Optional[int]:
        """
        Нормализовать любой тип индекса в point_index используя raw_data.
        
        Args:
            idx: Индекс любого типа (point_index, DataFrame index, position)
            
        Returns:
            point_index или None, если не удалось нормализовать
        """
        if self.raw_data is None or self.raw_data.empty:
            return None
        
        # Если передан point_index напрямую
        if 'point_index' in self.raw_data.columns:
            try:
                idx_int = int(idx)
                mask = self.raw_data['point_index'] == idx_int
                if mask.any():
                    return idx_int
            except (ValueError, TypeError):
                pass
        
        # Если передан индекс DataFrame, ищем point_index в записи
        try:
            if idx in self.raw_data.index:
                record = self.raw_data.loc[idx]
                if 'point_index' in self.raw_data.columns:
                    point_index_value = record.get('point_index')
                    if pd.notna(point_index_value):
                        try:
                            return int(point_index_value)
                        except (ValueError, TypeError):
                            pass
        except (KeyError, TypeError):
            pass
        
        # Если передан как позиция (0-based)
        # КРИТИЧЕСКИ ВАЖНО: НЕ используем idx как позицию, если он может быть point_index!
        # point_index обычно >= 1, но может совпадать с позицией
        # Поэтому проверяем позицию ТОЛЬКО если idx не является point_index
        try:
            if isinstance(idx, int) and 0 <= idx < len(self.raw_data):
                # Проверяем, не является ли idx point_index
                is_point_index = False
                if 'point_index' in self.raw_data.columns:
                    is_point_index = (self.raw_data['point_index'] == idx).any()
                
                # Если idx не является point_index, используем его как позицию
                if not is_point_index:
                    record = self.raw_data.iloc[idx]
                    if 'point_index' in self.raw_data.columns:
                        point_index_value = record.get('point_index')
                        if pd.notna(point_index_value):
                            try:
                                return int(point_index_value)
                            except (ValueError, TypeError):
                                pass
        except (IndexError, KeyError):
            pass
        
        return None
    
    def on_3d_point_selected(self, index: int):
        """Обработчик выбора точки в 3D редакторе"""
        # КРИТИЧЕСКИ ВАЖНО: index уже является point_index (эмитируется из mouse_press_event)
        # НЕ нужно нормализовать его снова, так как это может привести к ошибкам
        # Просто передаем его напрямую в select_row
        logger.debug(f"on_3d_point_selected: получен index={index}, передаем в select_row")
        
        # Подсвечиваем соответствующую строку в таблице
        # select_row сам нормализует индекс, если нужно
        self.data_table.select_row(index)
    
    def on_table_point_selected(self, index: int):
        """Обработчик выбора точки в таблице (index может быть point_index или индекс DataFrame)"""
        # Нормализуем индекс в point_index для надежности
        normalized_index = self._normalize_index_to_point_index(index)
        search_index = normalized_index if normalized_index is not None else index
        
        # Подсвечиваем соответствующую точку в 3D
        self.editor_3d.select_points([search_index])
        
        # Ищем запись по point_index или индексу DataFrame для установки активной станции
        if self.raw_data is not None:
            try:
                # Сначала пробуем найти по point_index
                record = None
                found_index = None
                if normalized_index is not None:
                    try:
                        mask = self.raw_data['point_index'] == normalized_index
                        matching = self.raw_data[mask]
                        if not matching.empty:
                            found_index = matching.index[0]
                            record = matching.iloc[0]
                    except (ValueError, TypeError):
                        pass
                
                # Fallback: поиск по индексу DataFrame
                if record is None and index in self.raw_data.index:
                    found_index = index
                    record = self.raw_data.loc[index]
                
                if record is not None and found_index is not None:
                    if bool(record.get('is_station', False)):
                        self.data_table.set_active_station(found_index)
            except (KeyError, AttributeError, IndexError) as e:
                logger.debug(f"Не удалось установить активную станцию: {e}")
    
    def on_belt_assigned(self, indices: list, belt_num: int):
        """Обработчик назначения пояса"""
        logger.info(f"Пояс {belt_num} назначен точкам: {indices}")
        # Данные уже синхронизированы через сигналы data_changed
    
    def show_about_normatives(self):
        """Показать информацию о нормативах"""
        text = """
<h2>Нормативная база</h2>

<h3>СП 70.13330.2012</h3>
<p><b>Отклонение от вертикали:</b> d<sub>i</sub> ≤ 0.001 × h<sub>i</sub></p>
<p>где h<sub>i</sub> - высота точки от основания (метры)</p>

<h3>Инструкция Минсвязи СССР (1980)</h3>
<p><b>Стрела прогиба (прямолинейность):</b> δ<sub>i</sub> ≤ L / 750</p>
<p>где L - длина секции между опорными точками (метры)</p>

<hr>
<p>Все измерения должны проводиться в метрической системе координат.</p>
"""
        
        QMessageBox.information(self, 'Нормативы', text)
        
    def show_about(self):
        """Показать информацию о программе"""
        from core import __version__
        text = f"""
<h2>GeoVertical Analyzer</h2>
<p>Версия {__version__}</p>

<p>Программа для геодезического контроля антенно-мачтовых сооружений</p>

<h3>Возможности:</h3>
<ul>
  <li>Загрузка данных из различных форматов (CSV, Shapefile, GeoJSON, DXF, Trimble)</li>
  <li>3D редактор точек с интерактивной визуализацией</li>
  <li>Автоматическая фильтрация точек башни</li>
  <li>Автоматическая группировка точек по поясам</li>
  <li>Расчет отклонений от вертикали (СП 70.13330.2012)</li>
  <li>Расчет стрелы прогиба (Инструкция Минсвязи СССР 1980)</li>
  <li>Генерация отчетов в Excel, PDF и Word</li>
</ul>

<h3>Документация:</h3>
<ul>
  <li>Руководство пользователя: docs/USER_GUIDE.md</li>
  <li>Поддержка Trimble: docs/TRIMBLE_SUPPORT.md</li>
  <li>История изменений: CHANGELOG.md</li>
</ul>

<p><b>Разработано в соответствии с техническим заданием</b></p>
"""
        
        QMessageBox.about(self, 'О программе', text)
    
    def show_user_guide(self):
        """Показать руководство пользователя"""
        from gui.help_dialog import HelpDialog
        dialog = HelpDialog(self)
        dialog.exec()

    def load_theme_settings(self):
        """Загружает и применяет сохранённую тему оформления."""
        settings = QSettings('GeoAnalysis', 'GeoVertical Analyzer')
        dark = settings.value('appearance/darkTheme', False, type=bool)
        if self.dark_theme_action:
            self.dark_theme_action.blockSignals(True)
        self.apply_theme(bool(dark), persist=False)
        if self.dark_theme_action:
            self.dark_theme_action.setChecked(bool(dark))
            self.dark_theme_action.blockSignals(False)

    def on_dark_theme_toggled(self, checked: bool):
        """Переключение тёмной темы из меню."""
        self.apply_theme(checked)

    def apply_theme(self, dark: bool, persist: bool = True):
        """Применяет выбранную цветовую схему ко всему приложению."""

        app = QApplication.instance()
        if not app:
            return

        if dark:
            palette = QPalette()
            palette.setColor(QPalette.ColorRole.Window, QColor(45, 45, 48))
            palette.setColor(QPalette.ColorRole.WindowText, QColor(220, 220, 220))
            palette.setColor(QPalette.ColorRole.Base, QColor(30, 30, 30))
            palette.setColor(QPalette.ColorRole.AlternateBase, QColor(45, 45, 48))
            palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(255, 255, 255))
            palette.setColor(QPalette.ColorRole.ToolTipText, QColor(45, 45, 48))
            palette.setColor(QPalette.ColorRole.Text, QColor(220, 220, 220))
            palette.setColor(QPalette.ColorRole.Button, QColor(45, 45, 48))
            palette.setColor(QPalette.ColorRole.ButtonText, QColor(220, 220, 220))
            palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 0, 0))
            palette.setColor(QPalette.ColorRole.Highlight, QColor(76, 163, 224))
            palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
            palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(127, 127, 127))
            palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(127, 127, 127))

            app.setPalette(palette)
            app.setStyleSheet("""
                QToolTip {
                    color: #ffffff;
                    background-color: #2f2f2f;
                    border: 1px solid #3c3c3c;
                }
                QLineEdit, QTextEdit, QPlainTextEdit,
                QSpinBox, QDoubleSpinBox, QComboBox {
                    color: #f3f3f3;
                    background-color: #2a2a2d;
                    selection-background-color: #4ca3e0;
                    selection-color: #ffffff;
                    border: 1px solid #3f3f43;
                }
                QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled,
                QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {
                    color: #8c8c8c;
                    background-color: #343437;
                    border: 1px solid #3f3f43;
                }
                QAbstractItemView, QTableView, QTableWidget,
                QListView, QListWidget, QTreeView, QTreeWidget {
                    color: #f0f0f0;
                    background-color: #232327;
                    alternate-background-color: #2c2c30;
                    gridline-color: #44444a;
                    selection-background-color: #4ca3e0;
                    selection-color: #ffffff;
                }
                QHeaderView::section {
                    background-color: #2f2f33;
                    color: #f0f0f0;
                    border: 1px solid #3f3f43;
                    padding: 4px 6px;
                }
                QGroupBox {
                    color: #f0f0f0;
                    border: 1px solid #3a3a3f;
                    border-radius: 4px;
                    margin-top: 6px;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    subcontrol-position: top left;
                    padding: 0 6px;
                }
                QTabWidget::pane {
                    border: 1px solid #3f3f43;
                    background: #232327;
                }
                QTabBar::tab {
                    background: #2c2c30;
                    color: #f0f0f0;
                    padding: 6px 12px;
                    border: 1px solid #3f3f43;
                }
                QTabBar::tab:selected {
                    background: #3a3a40;
                }
            """)
        else:
            app.setPalette(app.style().standardPalette())
            app.setStyleSheet("")

        if persist:
            settings = QSettings('GeoAnalysis', 'GeoVertical Analyzer')
            settings.setValue('appearance/darkTheme', dark)

        self.dark_theme_enabled = dark
        
        # Обновляем стили toolbar
        self.update_toolbar_styles()
        
        # Обновляем стили кнопок в таблицах данных
        self.update_table_button_styles()
        
        # Обновляем стили всех rich tooltips
        from gui.rich_tooltip import _tooltip_manager
        _tooltip_manager.update_all_styles()
    
    def update_table_button_styles(self):
        """Обновляет стили кнопок в таблицах данных при смене темы"""
        if not hasattr(self, 'data_table') or not self.data_table:
            return
        
        from gui.ui_helpers import apply_compact_button_style
        
        # Обновляем кнопки в таблице точек стояния
        if hasattr(self.data_table, 'add_station_btn'):
            apply_compact_button_style(self.data_table.add_station_btn, 
                                      width=200, min_height=36)
        if hasattr(self.data_table, 'set_active_station_btn'):
            apply_compact_button_style(self.data_table.set_active_station_btn, 
                                      width=160, min_height=36)
        
        # Обновляем кнопки в таблице точек башни
        if hasattr(self.data_table, 'tower_add_btn'):
            apply_compact_button_style(self.data_table.tower_add_btn, 
                                      width=150, min_height=36)
        if hasattr(self.data_table, 'tower_delete_btn'):
            apply_compact_button_style(self.data_table.tower_delete_btn, 
                                      width=160, min_height=36)
    
    def update_toolbar_styles(self):
        """Обновляет стили toolbar в зависимости от текущей темы"""
        if not hasattr(self, 'toolbar') or not self.toolbar:
            return
        
        is_dark = self.dark_theme_enabled
        
        if is_dark:
            # Темная тема - темные кнопки с хорошим контрастом
            style = """
                QToolBar#MainToolBar {
                    spacing: 4px;
                    padding: 4px 6px;
                    background-color: #2d2d30;
                    border-bottom: 1px solid #3f3f43;
                }
                QPushButton#toolbarButton {
                    padding: 6px 12px;
                    font-size: 11px;
                    font-weight: 500;
                    text-align: center;
                    border: 1px solid #4a4a4e;
                    border-radius: 4px;
                    background-color: #3a3a3e;
                    color: #e0e0e0;
                }
                QPushButton#toolbarButton:hover {
                    background-color: #4a4a4e;
                    border-color: #5a5a5e;
                    color: #ffffff;
                }
                QPushButton#toolbarButton:pressed {
                    background-color: #2a2a2e;
                    border-color: #3a3a3e;
                }
                QPushButton#toolbarButton:disabled {
                    color: #6a6a6a;
                    background-color: #2f2f33;
                    border-color: #3a3a3e;
                }
                QPushButton#toolbarButton[variant="primary"] {
                    background-color: #4CAF50;
                    color: white;
                    border-color: #45a049;
                    font-weight: 600;
                }
                QPushButton#toolbarButton[variant="primary"]:hover {
                    background-color: #5cbf60;
                    border-color: #4CAF50;
                }
                QPushButton#toolbarButton[variant="primary"]:pressed {
                    background-color: #3d9f41;
                    border-color: #3d8b40;
                }
                QLabel {
                    color: #e0e0e0;
                }
                QSpinBox, QDoubleSpinBox, QComboBox {
                    color: #e0e0e0;
                    background-color: #2a2a2d;
                    border: 1px solid #3f3f43;
                }
                QCheckBox {
                    color: #e0e0e0;
                }
            """
        else:
            # Светлая тема - светлые кнопки с хорошим контрастом
            style = """
                QToolBar#MainToolBar {
                    spacing: 4px;
                    padding: 4px 6px;
                    background-color: #f5f5f5;
                    border-bottom: 1px solid #d0d0d0;
                }
                QPushButton#toolbarButton {
                    padding: 6px 12px;
                    font-size: 11px;
                    font-weight: 500;
                    text-align: center;
                    border: 1px solid #b0b0b0;
                    border-radius: 4px;
                    background-color: #ffffff;
                    color: #212121;
                }
                QPushButton#toolbarButton:hover {
                    background-color: #e8e8e8;
                    border-color: #909090;
                }
                QPushButton#toolbarButton:pressed {
                    background-color: #d0d0d0;
                    border-color: #707070;
                }
                QPushButton#toolbarButton:disabled {
                    color: #9e9e9e;
                    background-color: #f5f5f5;
                    border-color: #d0d0d0;
                }
                QPushButton#toolbarButton[variant="primary"] {
                    background-color: #4CAF50;
                    color: white;
                    border-color: #45a049;
                    font-weight: 600;
                }
                QPushButton#toolbarButton[variant="primary"]:hover {
                    background-color: #45a049;
                    border-color: #3d8b40;
                }
                QPushButton#toolbarButton[variant="primary"]:pressed {
                    background-color: #3d8b40;
                    border-color: #357a38;
                }
                QLabel {
                    color: #212121;
                }
                QSpinBox, QDoubleSpinBox, QComboBox {
                    color: #212121;
                    background-color: #ffffff;
                    border: 1px solid #b0b0b0;
                }
                QCheckBox {
                    color: #212121;
                }
            """
        
        self.toolbar.setStyleSheet(style)
    
    def load_window_geometry(self):
        """Загрузка сохраненной геометрии окна"""
        settings = QSettings('GeoVertical', 'GeoVerticalAnalyzer')
        
        # Загружаем геометрию окна
        geometry = settings.value('window/geometry')
        if geometry:
            self.restoreGeometry(geometry)
            self._ensure_window_geometry_within_screen()
            logger.info("Загружены настройки окна")
        else:
            # Первый запуск - максимизируем окно
            self.showMaximized()
            logger.info("Первый запуск - окно максимизировано")
        
        # Загружаем состояние окна (максимизировано/нормальное)
        state = settings.value('window/state')
        if state:
            self.restoreState(state)

    def restore_editor_toolbar_position(self):
        """Восстанавливает позицию панели инструментов 3D-редактора."""
        if not self.editor_3d:
            return
        settings = QSettings('GeoVertical', 'GeoVerticalAnalyzer')
        position = settings.value('editorToolbar/position', 'left')
        if isinstance(position, str):
            normalized = position.lower()
            if normalized in {'left', 'top', 'right'}:
                self.editor_3d.set_toolbar_position(normalized)

    def on_editor_toolbar_position_changed(self, position: str):
        """Сохраняет позицию панели инструментов 3D-редактора."""
        if not isinstance(position, str):
            return
        normalized = position.lower()
        if normalized not in {'left', 'top', 'right'}:
            return
        settings = QSettings('GeoVertical', 'GeoVerticalAnalyzer')
        settings.setValue('editorToolbar/position', normalized)
    
    def save_window_geometry(self):
        """Сохранение геометрии окна"""
        settings = QSettings('GeoVertical', 'GeoVerticalAnalyzer')
        
        # Сохраняем геометрию окна
        settings.setValue('window/geometry', self.saveGeometry())
        
        # Сохраняем состояние окна
        settings.setValue('window/state', self.saveState())
        
        logger.info("Сохранены настройки окна")
    
    def _ensure_window_geometry_within_screen(self):
        """Корректирует размеры и позицию окна, чтобы они помещались на экране."""
        screen = QGuiApplication.primaryScreen()
        if not screen:
            return
        available = screen.availableGeometry()
        frame = self.frameGeometry()
        
        available_width = max(1, available.width())
        available_height = max(1, available.height())
        min_width = min(max(self.minimumWidth(), 1020), available_width)
        min_height = min(max(self.minimumHeight(), 700), available_height)
        
        width = min(max(frame.width(), min_width), available_width)
        height = min(max(frame.height(), min_height), available_height)
        
        max_left = available.left() + available_width - width
        max_top = available.top() + available_height - height
        if max_left < available.left():
            left = available.left()
        else:
            left = min(max(frame.left(), available.left()), max_left)
        if max_top < available.top():
            top = available.top()
        else:
            top = min(max(frame.top(), available.top()), max_top)
        
        self.setGeometry(left, top, width, height)
    
    def _setup_autosave(self):
        """Настройка автосохранения"""
        settings = QSettings('GeoVertical', 'GeoVerticalAnalyzer')
        self.autosave_enabled = settings.value('autosave/enabled', True, type=bool)
        self.autosave_interval_minutes = settings.value('autosave/interval_minutes', 3, type=int)  # Улучшенная защита: 3 минуты
        
        if self.autosave_enabled:
            # Устанавливаем таймер
            interval_ms = self.autosave_interval_minutes * 60 * 1000
            self.autosave_timer.timeout.connect(self._autosave_project)
            self.autosave_timer.start(interval_ms)
            logger.info(f"Автосохранение включено: интервал {self.autosave_interval_minutes} минут")
    
    def _autosave_project(self):
        """Автоматическое сохранение проекта"""
        if self.raw_data is None or self.raw_data.empty:
            return
        
        # Если проект уже сохранен, сохраняем по тому же пути
        if self.project_manager.current_project_path:
            try:
                self._save_project_to_file(self.project_manager.current_project_path)
                logger.debug("Автосохранение выполнено успешно")
            except Exception as e:
                logger.warning(f"Ошибка автосохранения: {e}")
        else:
            # Если проект не сохранен, используем временный файл автосохранения
            try:
                # Получаем section_data из 3D редактора
                section_data = None
                if hasattr(self.editor_3d, 'section_data'):
                    section_data = self.editor_3d.section_data
                
                xy_plane_state = None
                if hasattr(self.editor_3d, 'get_xy_plane_state'):
                    xy_plane_state = self.editor_3d.get_xy_plane_state()
                
                # Используем ProjectManager для автосохранения
                tower_builder_state = (
                    self._tower_blueprint.to_dict() if self._tower_blueprint else None
                )

                full_report_state = (
                    self.full_report_tab.serialize_state() if self.full_report_tab is not None else None
                )

                autosave_file = self.project_manager.save_autosave(
                    raw_data=self.raw_data,
                    processed_data=self.processed_data,
                    epsg_code=self.epsg_code,
                    current_file_path=self.current_file_path,
                    original_data_before_sections=self.original_data_before_sections,
                    height_tolerance=self.height_tolerance,
                    center_method=self.center_method,
                    expected_belt_count=self.expected_belt_count,
                    tower_faces_count=self.tower_faces_count,
                    xy_plane_state=xy_plane_state,
                    section_data=section_data,
                    tower_builder_state=tower_builder_state,
                    full_report_state=full_report_state,
                )
                
                if autosave_file:
                    self.autosave_path = autosave_file
                    
            except Exception as e:
                logger.warning(f"Ошибка автосохранения во временный файл: {e}")
    
    def _try_recover_autosave(self):
        """Пытается восстановить проект из автосохранения после сбоя"""
        try:
            # Проверяем настройку - показывать ли диалог восстановления
            settings = QSettings('GeoVertical', 'GeoVerticalAnalyzer')
            show_recovery_dialog = settings.value('autosave/show_recovery_dialog', False, type=bool)
            
            # Если диалог отключен, просто выходим
            if not show_recovery_dialog:
                logger.debug("Диалог восстановления проекта отключен в настройках")
                return
            
            latest_autosave = self.project_manager.get_latest_autosave()
            
            if not latest_autosave:
                return
            
            # Получаем время модификации файла
            import time
            file_mtime = os.path.getmtime(latest_autosave)
            file_time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(file_mtime))
            
            # Предлагаем восстановить
            reply = QMessageBox.question(
                self,
                'Восстановление проекта',
                f'Обнаружено автосохранение от {file_time_str}.\n\n'
                f'Восстановить проект?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                # Загружаем автосохранение
                self._load_project_from_file(latest_autosave)
                logger.info(f"Проект восстановлен из автосохранения: {latest_autosave}")
        except Exception as e:
            logger.warning(f"Ошибка при попытке восстановления автосохранения: {e}")
    
    def _load_project_from_file(self, file_path: str):
        """Внутренний метод загрузки проекта из файла (используется для автосохранения)"""
        try:
            # Используем ProjectManager для загрузки
            project_data = self.project_manager.load_project(file_path)
            
            # Восстанавливаем данные
            self.raw_data = project_data.get('raw_data')
            self.processed_data = project_data.get('processed_data')
            full_report_state = project_data.get('full_report_state', {})
            self.epsg_code = project_data.get('epsg_code')
            self.current_file_path = project_data.get('current_file_path')
            self.original_data_before_sections = project_data.get('original_data_before_sections')
            # Синхронизируем с project_manager
            self.project_manager.current_file_path = self.current_file_path
            self.height_tolerance = project_data.get('height_tolerance', 0.1)
            self.center_method = project_data.get('center_method', 'mean')
            self.expected_belt_count = project_data.get('expected_belt_count')
            self.tower_faces_count = project_data.get('tower_faces_count')
            
            # Обновляем интерфейс
            if self.raw_data is not None and not self.raw_data.empty:
                if 'belt' in self.raw_data.columns:
                    belt_count = self.raw_data['belt'].nunique()
                    self.belt_count_spin.blockSignals(True)
                    self.belt_count_spin.setValue(belt_count)
                    self.belt_count_spin.blockSignals(False)
                    self.expected_belt_count = belt_count
                
                self.data_table.set_data(self.raw_data)
                self.editor_3d.set_data(self.raw_data)
                
                if 'xy_plane_state' in project_data and hasattr(self.editor_3d, 'set_xy_plane_state'):
                    self.editor_3d.set_xy_plane_state(project_data.get('xy_plane_state'))
                
                if 'section_data' in project_data:
                    self.editor_3d.section_data = project_data['section_data']
                    has_sections = bool(len(project_data['section_data']) > 0)
                    if hasattr(self.editor_3d, 'remove_sections_action'):
                        self.editor_3d.remove_sections_action.setEnabled(has_sections)
                    if hasattr(self.editor_3d, 'build_central_axis_action'):
                        self.editor_3d.build_central_axis_action.setEnabled(has_sections)
                    if hasattr(self.editor_3d, 'update_section_lines'):
                        self.editor_3d.update_section_lines()
                
                self.save_project_btn.setEnabled(True)
                
                if self.processed_data is not None:
                    try:
                        self.verticality_widget.set_data(self.raw_data, self.processed_data)
                        self.straightness_widget.set_data(self.raw_data, self.processed_data)
                        if hasattr(self.editor_3d, 'set_processed_results'):
                            self.editor_3d.set_processed_results(self.processed_data)
                        if hasattr(self.data_table, 'set_processed_results'):
                            self.data_table.set_processed_results(self.processed_data)
                    except Exception:
                        pass
                
                self.update_export_actions_state()
                self.statusBar.showMessage('Проект восстановлен из автосохранения', 5000)

            if self.full_report_tab is not None:
                if full_report_state:
                    self.full_report_tab.load_state(full_report_state)
                else:
                    self.full_report_tab.clear_form()
                self.full_report_tab.set_source_data(self.raw_data, self.processed_data)
        except Exception as e:
            logger.error(f"Ошибка загрузки проекта из файла: {e}", exc_info=True)
            QMessageBox.warning(self, 'Ошибка', f'Не удалось восстановить проект:\n{str(e)}')
    
    def closeEvent(self, event):
        """Обработка закрытия окна с проверкой несохраненных изменений"""
        # Проверяем наличие несохраненных изменений
        if self.has_unsaved_changes and self.raw_data is not None and not self.raw_data.empty:
            reply = QMessageBox.question(
                self,
                'Несохраненные изменения',
                'У вас есть несохраненные изменения.\n\n'
                'Сохранить проект перед закрытием?',
                QMessageBox.StandardButton.Save |
                QMessageBox.StandardButton.Discard |
                QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Save
            )
            
            if reply == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
            elif reply == QMessageBox.StandardButton.Save:
                # Пытаемся сохранить
                if self.project_manager.current_project_path:
                    try:
                        self._save_project_to_file(self.project_manager.current_project_path)
                        self.has_unsaved_changes = False
                    except Exception as e:
                        logger.error(f"Ошибка сохранения при закрытии: {e}", exc_info=True)
                        QMessageBox.warning(
                            self,
                            'Ошибка сохранения',
                            f'Не удалось сохранить проект:\n{str(e)}\n\n'
                            'Закрыть без сохранения?'
                        )
                        # Пользователь может выбрать отмену в следующем диалоге
                        event.ignore()
                        return
                else:
                    # Проект не сохранен - предлагаем сохранить как
                    self.save_project_as()
                    # Если пользователь отменил сохранение, отменяем закрытие
                    if self.has_unsaved_changes:
                        event.ignore()
                        return
        
        # Останавливаем автосохранение
        if self.autosave_timer.isActive():
            self.autosave_timer.stop()
        
        # Сохраняем настройки перед закрытием
        self.save_window_geometry()
        event.accept()

    def on_build_missing_belt(self):
        """Достроить недостающий пояс на текущих данных.
        
        Использует ту же логику, что и галочка в окне импорта с другой точки стояния:
        1. Сначала пробует зеркальный метод (если есть данные визуализации)
        2. Если зеркальный метод не сработал, использует метод параллельных линий
        """
        if self.raw_data is None or self.raw_data.empty:
            return
        try:
            import logging
            import numpy as np
            import pandas as pd
            from core.belt_completion import complete_missing_belt_parallel_lines, complete_missing_belt_mirror
            
            faces = int(self.expected_belt_count or 4)
            rd = self.raw_data.copy()
            
            # Ищем отсутствующий пояс
            target_belt = None
            if 'belt' in rd.columns:
                present = set(int(b) for b in rd['belt'].dropna().unique())
                for b in range(1, faces+1):
                    if b not in present:
                        target_belt = b
                        break
            if target_belt is None:
                target_belt = 3 if faces >= 3 else 2
            
            logging.getLogger(__name__).info(f"[build_belt] Ручная достройка: faces={faces}, target_belt={target_belt}")
            
            # Пробуем получить данные визуализации из editor_3d для зеркального метода
            visualization_data = None
            if hasattr(self, 'editor_3d') and hasattr(self.editor_3d, 'belt_connection_lines'):
                # Пытаемся получить сохраненные данные визуализации
                # (они могут быть сохранены после импорта с другой точки стояния)
                try:
                    # Проверяем, есть ли линии соединения в editor_3d
                    if hasattr(self.editor_3d, '_last_visualization_data'):
                        visualization_data = self.editor_3d._last_visualization_data
                except AttributeError:
                    pass
            
            merged = rd
            gen = pd.DataFrame()
            
            # Сначала пробуем зеркальный метод (если есть данные визуализации)
            if visualization_data:
                line1 = visualization_data.get('line1')
                line2 = visualization_data.get('line2')
                if line1 and line2:
                    pa = np.array(line1['end']) if 'end' in line1 else None
                    pb = np.array(line2['end']) if 'end' in line2 else None
                    if pa is not None and pb is not None:
                        logging.getLogger(__name__).info(f"[mirror] Запуск зеркального метода: A={pa}, B={pb}")
                        try:
                            merged, gen = complete_missing_belt_mirror(
                                rd, 
                                faces=faces, 
                                target_belt=target_belt, 
                                point_a=pa, 
                                point_b=pb, 
                                source_belt=1, 
                                tolerance=0.15
                            )
                        except Exception as e:
                            logging.getLogger(__name__).warning(f"[mirror] Ошибка зеркального метода: {e}")
                            gen = pd.DataFrame()  # Сбрасываем, чтобы попробовать параллельные линии
            
            # Если зеркальный метод не сработал — используем параллельные линии
            if gen is None or gen.empty:
                logging.getLogger(__name__).info(f"[parallel_lines] Запуск метода параллельных линий")
                merged, gen = complete_missing_belt_parallel_lines(
                    rd, 
                    faces=faces, 
                    target_belt=target_belt, 
                    tolerance=0.15
                )
            
            if gen is not None and not gen.empty:
                self.raw_data = merged
                self.editor_3d.set_data(self.raw_data)
                
                # Визуализация поли-линии для пояса
                try:
                    bdf = self.raw_data[self.raw_data['belt'] == target_belt]
                    if bdf is not None and not bdf.empty:
                        cx, cy = bdf['x'].mean(), bdf['y'].mean()
                        angles = np.arctan2(bdf['y'] - cy, bdf['x'] - cx)
                        order = np.argsort(angles.values)
                        ordered = bdf.iloc[order][['x','y','z']].values
                        self.editor_3d.set_belt_polyline(int(target_belt), ordered)
                except (AttributeError, KeyError, ValueError, IndexError) as e:
                    logger.debug(f"Не удалось создать полилинию для пояса {target_belt}: {e}")
                
                if hasattr(self, 'data_table') and self.data_table is not None:
                    self.data_table.set_data(self.raw_data)
                
                self.update_analysis_widgets()
                logging.getLogger(__name__).info(f"Достроен пояс {target_belt}: добавлено {len(gen)} точек")
                self.statusBar.showMessage(f"Достроен пояс {target_belt}: добавлено {len(gen)} точек", 3000)
            else:
                logging.getLogger(__name__).warning("[build_belt] Не удалось достроить пояс — нет новых точек")
                self.statusBar.showMessage("Не удалось достроить пояс — нет новых точек", 3000)
        except (CalculationError, GroupingError, ValueError, KeyError, AttributeError) as e:
            import logging
            logging.getLogger(__name__).error(f"Ошибка достройки пояса: {e}", exc_info=True)
            self.statusBar.showMessage(f"Ошибка достройки пояса: {e}", 5000)

    def on_active_station_changed(self, station_id):
        if self.raw_data is None or self.raw_data.empty:
            return
        self.calculate()

