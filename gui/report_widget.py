"""
Виджет для предпросмотра и редактирования отчета с интерактивным HTML-представлением
"""
import logging
import re
from pathlib import Path
import tempfile
import base64
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTextBrowser,
                             QPushButton, QLabel, QFileDialog, QMessageBox, QFrame,
                             QSplitter, QGroupBox, QFormLayout, QLineEdit, QTextEdit,
                             QComboBox, QDateEdit, QScrollArea, QDialog)
from PyQt6.QtCore import Qt, QDate, pyqtSignal, QStandardPaths, QUrl, QSettings
from PyQt6.QtGui import QFont, QDesktopServices

from gui.ui_helpers import apply_compact_button_style
from utils.report_generator_enhanced import EnhancedReportGenerator
from utils.report_generator import ReportGenerator
from utils.full_report_builder import FullReportBuilder
from core.services.report_templates import ReportTemplateManager
from gui.full_report_template_editor import FullReportTemplateEditor
from gui.excel_export_dialog import ExcelExportDialog
logger = logging.getLogger(__name__)

class NotesTextEdit(QTextEdit):
    """QTextEdit с сигналом editingFinished, срабатывающим при потере фокуса"""
    editingFinished = pyqtSignal()
    
    def focusOutEvent(self, event):
        """Вызывается при потере фокуса"""
        super().focusOutEvent(event)
        self.editingFinished.emit()

class ReportWidget(QWidget):
    """Виджет для отображения и редактирования отчета с интерактивным предпросмотром"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.data = None
        self.processed_data = None
        self.editor_3d = None  # Ссылка на 3D редактор
        self.verticality_widget = None
        self.straightness_widget = None
        self.data_table_widget = None
        self.raw_data = None
        self.epsg_code = None
        self.project_name = "Отчет по геодезическому контролю"
        self.template_manager = ReportTemplateManager()
        self.full_report_builder = FullReportBuilder(self.template_manager)
        self.template_combo = None
        
        # Временные файлы для графиков
        self.temp_files = []
        self.temp_dir = None
        
        # Настройки для сохранения последней папки отчетов
        self.report_paths_settings = QSettings('GeoVertical', 'GeoVerticalAnalyzerPaths')
        
        self.init_ui()
        
    def init_ui(self):
        """Инициализация интерфейса"""
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)
        self.setLayout(main_layout)
        
        # Панель инструментов
        toolbar_layout = QHBoxLayout()
        
        self.save_pdf_btn = QPushButton('💾\nPDF')
        self.save_pdf_btn.setToolTip('Сохранить отчет в PDF')
        self.save_pdf_btn.clicked.connect(lambda: self.save_report('pdf'))
        apply_compact_button_style(self.save_pdf_btn, width=72, min_height=48)
        from gui.rich_tooltip import set_rich_tooltip
        set_rich_tooltip(self.save_pdf_btn, 'Сохранить отчет в PDF',
                        'Генерирует профессиональный PDF отчет с титульным листом, таблицами данных, графиками вертикальности и прямолинейности, а также выводами и рекомендациями.')
        toolbar_layout.addWidget(self.save_pdf_btn)
        
        self.save_docx_btn = QPushButton('💾\nWord')
        self.save_docx_btn.setToolTip('Сохранить отчет в Word (DOCX)')
        self.save_docx_btn.clicked.connect(lambda: self.save_report('docx'))
        apply_compact_button_style(self.save_docx_btn, width=72, min_height=48)
        set_rich_tooltip(self.save_docx_btn, 'Сохранить отчет в Word',
                        'Создает редактируемый отчет в формате DOCX. Можно открыть в Microsoft Word или LibreOffice для дальнейшего редактирования.')
        toolbar_layout.addWidget(self.save_docx_btn)

        self.save_full_docx_btn = QPushButton('📘\nПолный')
        self.save_full_docx_btn.setToolTip('Сформировать полный DOCX по шаблону ДО ТСС')
        self.save_full_docx_btn.clicked.connect(self.save_full_report)
        apply_compact_button_style(self.save_full_docx_btn, width=90, min_height=48)
        set_rich_tooltip(
            self.save_full_docx_btn,
            'Полный техотчет',
            'Формирует полный технический отчет по структуре ДО ТСС с использованием выбранного шаблона.'
        )
        toolbar_layout.addWidget(self.save_full_docx_btn)
        
        self.save_xlsx_btn = QPushButton('💾\nExcel')
        self.save_xlsx_btn.setToolTip('Сохранить отчет в Excel')
        self.save_xlsx_btn.clicked.connect(lambda: self.save_report('xlsx'))
        apply_compact_button_style(self.save_xlsx_btn, width=72, min_height=48)
        set_rich_tooltip(self.save_xlsx_btn, 'Сохранить отчет в Excel',
                        'Экспортирует данные в формат Excel с несколькими листами: исходные данные, результаты расчетов, проверка нормативов.')
        toolbar_layout.addWidget(self.save_xlsx_btn)
        
        toolbar_layout.addStretch()
        
        # Кнопка обновления предпросмотра
        self.refresh_btn = QPushButton('🔄\nОбновить')
        self.refresh_btn.setToolTip('Обновить предпросмотр отчета')
        self.refresh_btn.clicked.connect(self.update_preview)
        apply_compact_button_style(self.refresh_btn, width=80, min_height=48)
        set_rich_tooltip(self.refresh_btn, 'Обновить предпросмотр',
                        'Обновляет предпросмотр отчета с учетом последних изменений в данных и результатах расчетов.')
        toolbar_layout.addWidget(self.refresh_btn)
        
        main_layout.addLayout(toolbar_layout)
        
        # Splitter: предпросмотр слева, поля справа
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(6)
        splitter.setStyleSheet("""
            QSplitter::handle {
                background: #cccccc;
            }
            QSplitter::handle:hover {
                background: #999999;
            }
        """)
        
        # === ЛЕВАЯ ЧАСТЬ: Предпросмотр отчета ===
        preview_widget = QWidget()
        preview_layout = QVBoxLayout()
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_widget.setLayout(preview_layout)
        
        preview_label = QLabel('📄 Предпросмотр отчета')
        preview_label.setFont(QFont('Arial', 12, QFont.Weight.Bold))
        preview_layout.addWidget(preview_label)
        
        self.preview_browser = QTextBrowser()
        self.preview_browser.setFont(QFont('Arial', 10))
        self.preview_browser.setPlaceholderText('Здесь будет отображаться отчет после выполнения расчетов')
        preview_layout.addWidget(self.preview_browser)
        
        splitter.addWidget(preview_widget)
        
        # === ПРАВАЯ ЧАСТЬ: Поля для заполнения ===
        fields_widget = QWidget()
        fields_layout = QVBoxLayout()
        fields_layout.setContentsMargins(5, 0, 5, 0)
        fields_widget.setLayout(fields_layout)
        
        fields_label = QLabel('📝 Информация об объекте')
        fields_label.setFont(QFont('Arial', 12, QFont.Weight.Bold))
        fields_layout.addWidget(fields_label)
        
        # Scroll area для полей
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setMaximumWidth(350)
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout()
        scroll_layout.setContentsMargins(5, 5, 5, 5)
        scroll_widget.setLayout(scroll_layout)
        
        # Группа: Информация об объекте
        object_group = QGroupBox('Информация об объекте')
        object_layout = QFormLayout()
        object_group.setLayout(object_layout)
        
        self.project_name_edit = QLineEdit()
        self.project_name_edit.setPlaceholderText('Например: Мачта связи №5, высота 50 м')
        self.project_name_edit.setText('Антенно-мачтовое сооружение')
        self.project_name_edit.editingFinished.connect(self.on_field_changed)
        object_layout.addRow('Наименование объекта:', self.project_name_edit)
        
        self.location_edit = QLineEdit()
        self.location_edit.setPlaceholderText('Адрес или координаты')
        self.location_edit.editingFinished.connect(self.on_field_changed)
        object_layout.addRow('Местоположение:', self.location_edit)
        
        self.object_type_combo = QComboBox()
        self.object_type_combo.addItems([
            'Мачта связи',
            'Радиомачта',
            'Телевизионная мачта',
            'Антенная опора',
            'Прочее'
        ])
        self.object_type_combo.currentTextChanged.connect(self.on_field_changed)
        object_layout.addRow('Тип сооружения:', self.object_type_combo)
        
        scroll_layout.addWidget(object_group)
        
        # Группа: Организация
        org_group = QGroupBox('Организация')
        org_layout = QFormLayout()
        org_group.setLayout(org_layout)
        
        self.organization_edit = QLineEdit()
        self.organization_edit.setPlaceholderText('Название организации')
        self.organization_edit.editingFinished.connect(self.on_field_changed)
        org_layout.addRow('Организация:', self.organization_edit)
        
        self.executor_edit = QLineEdit()
        self.executor_edit.setPlaceholderText('ФИО исполнителя')
        self.executor_edit.editingFinished.connect(self.on_field_changed)
        org_layout.addRow('Исполнитель:', self.executor_edit)
        
        self.position_edit = QLineEdit()
        self.position_edit.setPlaceholderText('Должность')
        self.position_edit.editingFinished.connect(self.on_field_changed)
        org_layout.addRow('Должность:', self.position_edit)
        
        scroll_layout.addWidget(org_group)
        
        # Группа: Дата обследования
        date_group = QGroupBox('Дата обследования')
        date_layout = QFormLayout()
        date_group.setLayout(date_layout)
        
        self.survey_date = QDateEdit()
        self.survey_date.setDate(QDate.currentDate())
        self.survey_date.setCalendarPopup(True)
        self.survey_date.setDisplayFormat('dd.MM.yyyy')
        self.survey_date.dateChanged.connect(self.on_field_changed)
        date_layout.addRow('Дата:', self.survey_date)
        
        scroll_layout.addWidget(date_group)
        
        # Группа: Примечания
        notes_group = QGroupBox('Примечания')
        notes_layout = QVBoxLayout()
        notes_group.setLayout(notes_layout)
        
        self.notes_edit = NotesTextEdit()
        self.notes_edit.setPlaceholderText(
            'Дополнительная информация, особые условия измерений, '
            'погодные условия и т.д.'
        )
        self.notes_edit.setMaximumHeight(100)
        # Обновляем только при потере фокуса (переходе в другое поле или вкладку)
        self.notes_edit.editingFinished.connect(self.on_field_changed)
        notes_layout.addWidget(self.notes_edit)
        
        scroll_layout.addWidget(notes_group)

        template_group = QGroupBox('Шаблон полного отчета')
        template_layout = QVBoxLayout()
        template_group.setLayout(template_layout)

        self.template_combo = QComboBox()
        self.template_combo.setPlaceholderText('Нет сохраненных шаблонов')
        template_layout.addWidget(self.template_combo)

        template_btn_layout = QHBoxLayout()
        self.refresh_templates_btn = QPushButton('🔄')
        self.refresh_templates_btn.setToolTip('Обновить список шаблонов')
        self.refresh_templates_btn.clicked.connect(self._update_template_combo)
        template_btn_layout.addWidget(self.refresh_templates_btn)

        self.open_templates_btn = QPushButton('📁')
        self.open_templates_btn.setToolTip('Открыть каталог шаблонов')
        self.open_templates_btn.clicked.connect(self._open_templates_folder)
        template_btn_layout.addWidget(self.open_templates_btn)

        self.edit_templates_btn = QPushButton('✏️')
        self.edit_templates_btn.setToolTip('Открыть редактор шаблонов')
        self.edit_templates_btn.clicked.connect(self._open_template_editor)
        template_btn_layout.addWidget(self.edit_templates_btn)

        template_layout.addLayout(template_btn_layout)
        scroll_layout.addWidget(template_group)
        scroll_layout.addStretch()
        
        scroll_area.setWidget(scroll_widget)
        fields_layout.addWidget(scroll_area)
        
        splitter.addWidget(fields_widget)
        
        # Устанавливаем пропорции (75% предпросмотр, 25% поля)
        splitter.setSizes([750, 250])
        
        # Растягиваем splitter на всю доступную высоту
        main_layout.addWidget(splitter, stretch=1)
        
        # Информационный лейбл (компактный, внизу)
        self.info_label = QLabel('⚠ Отчет не сгенерирован. Выполните расчет')
        self.info_label.setStyleSheet('padding: 3px 5px; background-color: #fff3cd; border: 1px solid #ffc107; border-radius: 3px; font-size: 10px;')
        self.info_label.setMaximumHeight(25)
        main_layout.addWidget(self.info_label)
        
        # По умолчанию кнопки сохранения отключены
        self.save_pdf_btn.setEnabled(False)
        self.save_docx_btn.setEnabled(False)
        self.save_xlsx_btn.setEnabled(False)
        self.refresh_btn.setEnabled(False)
        self.save_full_docx_btn.setEnabled(False)

        self._update_template_combo()
        
    def on_field_changed(self):
        """Обработчик изменения полей - обновляет предпросмотр"""
        if self.processed_data and self.processed_data.get('valid'):
            # Небольшая задержка, чтобы не обновлять при каждом символе
            self.update_preview()
    
    def set_data(self, raw_data, processed_data, verticality_widget=None, straightness_widget=None, data_table_widget=None):
        """Установить данные для отчета
        
        Args:
            raw_data: Исходные данные
            processed_data: Обработанные данные с расчетами
            verticality_widget: Виджет вертикальности
            straightness_widget: Виджет прямолинейности
        """
        self.raw_data = raw_data
        self.processed_data = processed_data
        self.verticality_widget = verticality_widget
        self.straightness_widget = straightness_widget
        self.data_table_widget = data_table_widget
        
        if processed_data and processed_data.get('valid'):
            self.update_preview()
        else:
            self.preview_browser.setHtml('<p style="color: #666; padding: 20px;">Нет данных для отчета. Выполните расчет.</p>')
            self.save_pdf_btn.setEnabled(False)
            self.save_docx_btn.setEnabled(False)
            self.save_xlsx_btn.setEnabled(False)
            self.refresh_btn.setEnabled(False)
            self.save_full_docx_btn.setEnabled(False)
            self.info_label.setText('⚠ Отчет не сгенерирован. Выполните расчет')
            self.info_label.setStyleSheet('padding: 5px; background-color: #fff3cd; border: 1px solid #ffc107; border-radius: 3px;')
        self._sync_full_report_button_state()
    
    def update_preview(self):
        """Обновление HTML-предпросмотра отчета"""
        if not self.processed_data or not self.processed_data.get('valid'):
            return
        
        try:
            # Получаем информацию из полей
            report_info = self.get_report_info()
            
            # Генерируем HTML
            html_content = self.generate_preview_html(
                self.raw_data,
                self.processed_data,
                verticality_widget=self.verticality_widget,
                straightness_widget=self.straightness_widget,
                project_name=report_info['project_name'],
                organization=report_info.get('organization', ''),
                report_info=report_info
            )
            
            self.preview_browser.setHtml(html_content)
            
            # Активируем кнопки сохранения
            self.save_pdf_btn.setEnabled(True)
            self.save_docx_btn.setEnabled(True)
            self.save_xlsx_btn.setEnabled(True)
            self.refresh_btn.setEnabled(True)
            
            self.info_label.setText('✓ Отчет готов. Заполните информацию справа и сохраните.')
            self.info_label.setStyleSheet('padding: 5px; background-color: #d4edda; border: 1px solid #28a745; border-radius: 3px;')
            
            logger.info("Предпросмотр отчета обновлен")
            
        except Exception as e:
            logger.error(f"Ошибка обновления предпросмотра: {e}", exc_info=True)
            self.preview_browser.setHtml(f'<p style="color: red; padding: 20px;">Ошибка генерации предпросмотра: {str(e)}</p>')
            self.info_label.setText(f'❌ Ошибка: {str(e)}')
            self.info_label.setStyleSheet('padding: 5px; background-color: #f8d7da; border: 1px solid #dc3545; border-radius: 3px;')
    
    def get_report_info(self):
        """Получить информацию из полей"""
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

    def _update_template_combo(self):
        if not self.template_combo:
            return
        templates = self.template_manager.list_templates()
        self.template_combo.blockSignals(True)
        self.template_combo.clear()
        self.template_combo.addItems(templates)
        self.template_combo.blockSignals(False)
        self.template_combo.setEnabled(bool(templates))
        self._sync_full_report_button_state()

    def _sync_full_report_button_state(self):
        has_templates = bool(self.template_combo and self.template_combo.count() > 0)
        data_ready = bool(self.processed_data and self.processed_data.get('valid'))
        self.save_full_docx_btn.setEnabled(has_templates and data_ready)

    def _open_templates_folder(self):
        folder = self.template_manager.storage_dir
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _open_template_editor(self):
        editor = FullReportTemplateEditor(self)
        editor.exec()
        self._update_template_combo()

    def _collect_angular_measurements(self):
        """Собирает данные угловых измерений из таблицы."""
        default = {'x': [], 'y': []}
        widget = self.data_table_widget
        if widget and hasattr(widget, 'get_angular_measurements'):
            try:
                measurements = widget.get_angular_measurements()
                if isinstance(measurements, dict):
                    result = {
                        'x': measurements.get('x', []) or [],
                        'y': measurements.get('y', []) or [],
                    }
                    return result
            except Exception as exc:  # noqa: BLE001
                logger.warning("Не удалось получить данные угловых измерений: %s", exc)
        return default

    @staticmethod
    def _render_angular_table_html(rows):
        if not rows:
            return '<p><em>Данные отсутствуют</em></p>'

        headers = [
            '№', 'Секция', 'H, м', 'Пояс', 'KL', 'KR', 'KL–KR (″)', 'βизм', 'Bизм', 'Δβ', 'Δb, мм'
        ]

        html = ['<table>']
        html.append('<thead><tr>')
        for header in headers:
            html.append(f'<th>{header}</th>')
        html.append('</tr></thead>')

        html.append('<tbody>')
        for idx, row in enumerate(rows, start=1):
            html.append('<tr>')
            height = row.get('height')
            height_str = f"{float(height):.1f}" if height is not None else '—'
            belt_value = row.get('belt', '—')
            belt_str = str(belt_value) if belt_value is not None else '—'
            html.extend([
                f'<td>{idx}</td>',
                f'<td>{row.get("section_label", "—")}</td>',
                f'<td>{height_str}</td>',
                f'<td>{belt_str}</td>',
                f'<td>{row.get("kl_str", "—")}</td>',
                f'<td>{row.get("kr_str", "—")}</td>',
                f'<td>{row.get("diff_str", "—")}</td>',
                f'<td>{row.get("beta_str", "—")}</td>',
                f'<td>{row.get("center_str", "—")}</td>',
                f'<td>{row.get("delta_str", "—")}</td>',
                f'<td>{row.get("delta_mm_str", "—")}</td>',
            ])
            html.append('</tr>')
        html.append('</tbody>')
        html.append('</table>')
        return '\n'.join(html)

    @staticmethod
    def _sanitize_filename_component(value: str | None, fallback: str) -> str:
        """Удаляет недопустимые символы в имени файла."""
        if value:
            sanitized = re.sub(r'[\\/*?:"<>|]+', '_', value.strip())
            sanitized = re.sub(r'\s+', ' ', sanitized).strip()
        else:
            sanitized = ''
        return sanitized or fallback

    def _suggest_default_filename(self, extension: str, report_info: dict) -> str:
        """Формирует имя файла по умолчанию на основе данных отчета."""
        base_name = self._sanitize_filename_component(
            report_info.get('project_name'),
            'Отчет по геодезическому контролю'
        )
        date_suffix = QDate.currentDate().toString('yyyyMMdd')
        return f'{base_name}_{date_suffix}{extension}'

    def generate_preview_html(self, 
                             raw_data, 
                             processed_data,
                             verticality_widget=None,
                             straightness_widget=None,
                             project_name="Объект контроля",
                             organization="",
                             report_info=None):
        """Генерация HTML-представления отчета"""
        try:
            # Создаем временную директорию для графиков, если её нет
            if not self.temp_dir:
                self.temp_dir = Path(tempfile.mkdtemp(prefix='geov_report_'))
            
            html_parts = []
            
            # Стили (тот же код из report_preview_dialog.py)
            html_parts.append("""
            <style>
                body {
                    font-family: Arial, sans-serif;
                    margin: 20px;
                    background-color: #f5f5f5;
                }
                .container {
                    background-color: white;
                    padding: 30px;
                    max-width: 1000px;
                    margin: 0 auto;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                }
                h1 {
                    color: #2c3e50;
                    text-align: center;
                    border-bottom: 3px solid #3498db;
                    padding-bottom: 10px;
                }
                h2 {
                    color: #34495e;
                    margin-top: 30px;
                    border-left: 4px solid #3498db;
                    padding-left: 10px;
                }
                h3 {
                    color: #7f8c8d;
                    margin-top: 20px;
                }
                table {
                    width: 100%;
                    border-collapse: collapse;
                    margin: 15px 0;
                    font-size: 11px;
                }
                th {
                    background-color: #34495e;
                    color: white;
                    padding: 10px;
                    text-align: center;
                    font-weight: bold;
                }
                td {
                    padding: 8px;
                    text-align: center;
                    border: 1px solid #ddd;
                }
                tr:nth-child(even) {
                    background-color: #f9f9f9;
                }
                tr:hover {
                    background-color: #f0f0f0;
                }
                .status-ok {
                    color: #27ae60;
                    font-weight: bold;
                }
                .status-error {
                    color: #e74c3c;
                    font-weight: bold;
                }
                .chart-container {
                    text-align: center;
                    margin: 20px 0;
                }
                .chart-container img {
                    max-width: 100%;
                    height: auto;
                    border: 1px solid #ddd;
                    border-radius: 5px;
                    box-shadow: 0 2px 5px rgba(0,0,0,0.1);
                }
                .info-box {
                    background-color: #ecf0f1;
                    padding: 15px;
                    border-radius: 5px;
                    margin: 15px 0;
                }
                .footer {
                    margin-top: 40px;
                    padding-top: 20px;
                    border-top: 2px solid #bdc3c7;
                    text-align: center;
                    color: #7f8c8d;
                    font-size: 10px;
                }
            </style>
            """)
            
            html_parts.append('<div class="container">')
            
            # Титульный лист
            html_parts.append('<h1>ОТЧЕТ</h1>')
            html_parts.append('<h2 style="text-align: center;">по результатам геодезического контроля</h2>')
            html_parts.append('<h2 style="text-align: center;">антенно-мачтового сооружения</h2>')
            html_parts.append('<br>')
            
            # Информация об объекте
            html_parts.append('<div class="info-box">')
            if report_info and report_info.get('project_name'):
                html_parts.append(f'<p><strong>Объект:</strong> {report_info["project_name"]}</p>')
            else:
                html_parts.append(f'<p><strong>Объект:</strong> {project_name}</p>')
            
            org = organization
            if report_info and report_info.get('organization'):
                org = report_info['organization']
            if org:
                html_parts.append(f'<p><strong>Организация:</strong> {org}</p>')
            
            if report_info and report_info.get('location'):
                html_parts.append(f'<p><strong>Местоположение:</strong> {report_info["location"]}</p>')
            
            html_parts.append(f'<p><strong>Количество точек:</strong> {len(raw_data)}</p>')
            html_parts.append(f'<p><strong>Количество поясов:</strong> {len(processed_data.get("centers", []))}</p>')
            html_parts.append(f'<p><strong>Программа:</strong> GeoVertical Analyzer v1.0</p>')
            html_parts.append('</div>')
            
            html_parts.append('<hr>')
            
            # Нормативная база
            html_parts.append('<h2>1. НОРМАТИВНАЯ БАЗА</h2>')
            html_parts.append('<p>Геодезический контроль выполнен в соответствии с требованиями:</p>')
            html_parts.append('<ul>')
            html_parts.append('<li><strong>СП 70.13330.2012</strong> "Несущие и ограждающие конструкции"<br>')
            html_parts.append('Допуск вертикальности: <strong>d ≤ 0,001 × h</strong> (где h - высота точки от основания, м)</li>')
            html_parts.append('<li><strong>ГОСТ Р 71949-2025 Конструкции опорные антенных сооружений объектов связи</strong><br>')
            html_parts.append('Допуск прямолинейности: <strong>δ ≤ L / 750</strong> (где L - длина секции, м)</li>')
            html_parts.append('</ul>')
            
            # Журнал угловых измерений
            html_parts.append('<h2>2. ЖУРНАЛ УГЛОВЫХ ИЗМЕРЕНИЙ</h2>')
            angular_measurements = self._collect_angular_measurements()
            if angular_measurements['x'] or angular_measurements['y']:
                html_parts.append('<h3>2.1. Измерения по оси X</h3>')
                html_parts.append(self._render_angular_table_html(angular_measurements['x']))

                html_parts.append('<h3>2.2. Измерения по оси Y</h3>')
                html_parts.append(self._render_angular_table_html(angular_measurements['y']))
            else:
                html_parts.append('<p><em>Данные угловых измерений отсутствуют</em></p>')

            # Таблица вертикальности
            html_parts.append('<h2>3. ТАБЛИЦА ОТКЛОНЕНИЙ СТВОЛА ОТ ВЕРТИКАЛИ</h2>')
            
            # Получаем данные угловых измерений для таблицы вертикальности
            angular_measurements = self._collect_angular_measurements()
            
            # Агрегируем данные угловых измерений по секциям
            verticality_data_from_angular = None
            if angular_measurements and (angular_measurements.get('x') or angular_measurements.get('y')):
                try:
                    from utils.report_generator_enhanced import EnhancedReportGenerator
                    verticality_data_from_angular = EnhancedReportGenerator._aggregate_angular_measurements_by_sections(angular_measurements)
                except Exception as e:
                    logger.warning(f"Ошибка агрегации данных угловых измерений: {e}")
            
            verticality_data = []
            if verticality_data_from_angular:
                # Используем данные из угловых измерений
                verticality_data = verticality_data_from_angular
            elif verticality_widget and hasattr(verticality_widget, 'get_table_data'):
                try:
                    verticality_data = verticality_widget.get_table_data()
                except Exception as e:
                    logger.warning(f"Ошибка получения данных вертикальности: {e}")
            
            if verticality_data:
                html_parts.append('<table>')
                html_parts.append('<thead>')
                html_parts.append('<tr>')
                html_parts.append('<th>№ секции</th>')
                html_parts.append('<th>Высота, м</th>')
                html_parts.append('<th>Отклонение X, мм</th>')
                html_parts.append('<th>Отклонение Y, мм</th>')
                html_parts.append('<th>Суммарное отклонение, мм</th>')
                html_parts.append('<th>Допустимое, мм</th>')
                html_parts.append('<th>Статус</th>')
                html_parts.append('</tr>')
                html_parts.append('</thead>')
                html_parts.append('<tbody>')
                
                from core.normatives import get_vertical_tolerance
                
                for item in verticality_data:
                    height = item.get('height', 0)
                    dev_x = item.get('deviation_x', item.get('deviation', 0))
                    dev_y = item.get('deviation_y', 0)
                    total_dev = item.get('total_deviation', item.get('deviation', 0))
                    
                    tolerance_mm = item.get('tolerance', get_vertical_tolerance(height) * 1000)
                    status = '✓ Норма' if abs(total_dev) <= tolerance_mm else '✗ Превышение'
                    status_class = 'status-ok' if abs(total_dev) <= tolerance_mm else 'status-error'
                    
                    html_parts.append('<tr>')
                    html_parts.append(f'<td>{item.get("section_num", "-")}</td>')
                    html_parts.append(f'<td>{height:.1f}</td>')
                    html_parts.append(f'<td>{dev_x:+.1f}</td>')
                    html_parts.append(f'<td>{dev_y:+.1f}</td>')
                    # Суммарное отклонение: округляем до десятого знака и выводим по модулю
                    html_parts.append(f'<td>{abs(total_dev):.1f}</td>')
                    html_parts.append(f'<td>{tolerance_mm:.1f}</td>')
                    html_parts.append(f'<td class="{status_class}">{status}</td>')
                    html_parts.append('</tr>')
                
                html_parts.append('</tbody>')
                html_parts.append('</table>')
            else:
                html_parts.append('<p><em>Нет данных для отображения</em></p>')
            
            # График вертикальности (используем SVG для векторного формата)
            if verticality_widget and hasattr(verticality_widget, 'figure'):
                html_parts.append('<h3>График вертикальности</h3>')
                chart_path_svg = self.temp_dir / 'verticality_chart.svg'
                verticality_widget.figure.savefig(str(chart_path_svg), format='svg', bbox_inches='tight', pad_inches=0.3)
                if str(chart_path_svg) not in self.temp_files:
                    self.temp_files.append(str(chart_path_svg))
                
                # Читаем SVG как текст и встраиваем напрямую
                with open(chart_path_svg, 'r', encoding='utf-8') as f:
                    svg_content = f.read()
                
                html_parts.append('<div class="chart-container">')
                html_parts.append(svg_content)
                html_parts.append('<p><em>Рис. 1. Отклонения центров секций от вертикальной оси мачты</em></p>')
                html_parts.append('</div>')
            
            # Таблица прогибов
            html_parts.append('<h2>4. ТАБЛИЦА СТРЕЛ ПРОГИБА ПОЯСОВ СТВОЛА (ПРЯМОЛИНЕЙНОСТЬ)</h2>')
            
            straightness_data = {}
            if straightness_widget and hasattr(straightness_widget, 'get_all_belts_data'):
                try:
                    straightness_data = straightness_widget.get_all_belts_data()
                except Exception as e:
                    logger.warning(f"Ошибка получения данных прямолинейности: {e}")
            
            if straightness_data:
                # Новая структура: данные сгруппированы по частям
                sorted_parts = sorted(straightness_data.keys())
                
                # Общий счетчик рисунков для всех частей (начинается с 2, т.к. рис. 1 - вертикальность)
                global_figure_index = 2
                
                for part_num in sorted_parts:
                    part_info = straightness_data[part_num]
                    min_height = part_info.get('min_height', 0.0)
                    max_height = part_info.get('max_height', 0.0)
                    belts_data = part_info.get('belts', {})
                    
                    if not belts_data:
                        continue
                    
                    # Заголовок для части (формат высот: "0,0 - 20,800")
                    min_str = f"{min_height:.1f}".replace('.', ',')
                    max_str = f"{max_height:.3f}".replace('.', ',')
                    part_title = f"Часть {part_num} ({min_str} - {max_str})"
                    html_parts.append(f'<h3>{part_title}</h3>')
                    
                    # Получаем все уникальные высоты для этой части
                    all_heights = set()
                    max_tolerance = 0
                    for belt_data in belts_data.values():
                        for item in belt_data:
                            all_heights.add(round(item['height'], 1))
                            max_tolerance = max(max_tolerance, item.get('tolerance', 0))
                    
                    sorted_heights = sorted(all_heights)
                    sorted_belts = sorted(belts_data.keys())
                    
                    html_parts.append('<table>')
                    html_parts.append('<thead>')
                    html_parts.append('<tr>')
                    html_parts.append('<th>Высота, м</th>')
                    for belt_num in sorted_belts:
                        html_parts.append(f'<th>Пояс {belt_num}, мм</th>')
                    html_parts.append('<th>Допустимое, мм</th>')
                    html_parts.append('</tr>')
                    html_parts.append('</thead>')
                    html_parts.append('<tbody>')
                    
                    # Создаем словарь для быстрого доступа
                    belt_height_deflection = {}
                    for belt_num, belt_data in belts_data.items():
                        for item in belt_data:
                            height_rounded = round(item['height'], 1)
                            belt_height_deflection[(belt_num, height_rounded)] = item.get('deflection', 0)
                    
                    for height in sorted_heights:
                        html_parts.append('<tr>')
                        html_parts.append(f'<td>{height:.1f}</td>')
                        
                        for belt_num in sorted_belts:
                            key = (belt_num, height)
                            if key in belt_height_deflection:
                                deflection = belt_height_deflection[key]
                                # Проверяем превышение
                                status_class = 'status-error' if abs(deflection) > max_tolerance else 'status-ok'
                                html_parts.append(f'<td class="{status_class}">{deflection:+.1f}</td>')
                            else:
                                html_parts.append('<td>-</td>')
                        
                        html_parts.append(f'<td>±{max_tolerance:.1f}</td>')
                        html_parts.append('</tr>')
                    
                    html_parts.append('</tbody>')
                    html_parts.append('</table>')
                    
                    # Графики прямолинейности для этой части сразу после таблицы
                    html_parts.append('<h3>Графики прямолинейности</h3>')
                    
                    # Получаем графики для этой части
                    part_figures = []
                    if straightness_widget and hasattr(straightness_widget, 'get_part_figures_for_pdf'):
                        try:
                            part_figures = straightness_widget.get_part_figures_for_pdf(part_num, group_size=2)
                        except Exception as e:
                            logger.warning(f"Не удалось получить графики для части {part_num}: {e}")
                    
                    if not part_figures:
                        # Fallback: пробуем получить все графики и отфильтровать
                        try:
                            if hasattr(straightness_widget, 'get_grouped_figures_for_pdf'):
                                all_figures = straightness_widget.get_grouped_figures_for_pdf()
                                part_belts = set(sorted_belts)
                                for belt_group, figure in all_figures:
                                    if any(belt in part_belts for belt in belt_group):
                                        part_figures.append((belt_group, figure))
                        except Exception as e:
                            logger.warning(f"Не удалось получить графики (fallback) для части {part_num}: {e}")
                    
                    if part_figures:
                        for belt_group, figure in part_figures:
                            chart_path_svg = self.temp_dir / f'straightness_part_{part_num}_group_{global_figure_index}.svg'
                            figure.savefig(str(chart_path_svg), format='svg', bbox_inches='tight', pad_inches=0.3)
                            if str(chart_path_svg) not in self.temp_files:
                                self.temp_files.append(str(chart_path_svg))
                            
                            with open(chart_path_svg, 'r', encoding='utf-8') as f:
                                svg_content = f.read()
                            
                            html_parts.append('<div class="chart-container">')
                            html_parts.append(svg_content)
                            belts_caption = ', '.join(str(b) for b in belt_group)
                            html_parts.append(f'<p><em>Рис. {global_figure_index}. Отклонения от прямолинейности по поясам {belts_caption}</em></p>')
                            html_parts.append('</div>')
                            global_figure_index += 1
                    else:
                        html_parts.append('<p><em>Графики для этой части недоступны</em></p>')
                
            else:
                html_parts.append('<p><em>Нет данных для отображения</em></p>')
            
            html_parts.append('<div class="footer">')
            html_parts.append('<p>Отчет сгенерирован программой GeoVertical Analyzer v1.0</p>')
            html_parts.append('</div>')
            
            html_parts.append('</div>')  # закрываем container
            
            return '\n'.join(html_parts)
            
        except Exception as e:
            logger.error(f"Ошибка генерации HTML предпросмотра: {e}", exc_info=True)
            return f'<p style="color: red;">Ошибка генерации предпросмотра: {str(e)}</p>'
    
    def cleanup_temp_files(self):
        """Удаление временных файлов"""
        for temp_file in self.temp_files:
            try:
                if Path(temp_file).exists():
                    Path(temp_file).unlink()
            except Exception as e:
                logger.warning(f"Не удалось удалить временный файл {temp_file}: {e}")
        
        # Удаляем директорию
        if self.temp_dir and self.temp_dir.exists():
            try:
                import shutil
                shutil.rmtree(self.temp_dir)
            except Exception as e:
                logger.warning(f"Не удалось удалить временную директорию {self.temp_dir}: {e}")
    
    def save_report(self, format_type):
        """Сохранение отчета в выбранном формате
        
        Args:
            format_type: Тип формата ('pdf', 'docx', 'xlsx')
        """
        if not self.processed_data or not self.processed_data.get('valid'):
            QMessageBox.warning(self, 'Предупреждение', 'Нет данных для сохранения. Выполните расчет.')
            return
        
        # Определяем фильтр и расширение
        filters = {
            'pdf': 'PDF файлы (*.pdf)',
            'docx': 'Word файлы (*.docx)',
            'xlsx': 'Excel файлы (*.xlsx)'
        }
        extensions = {
            'pdf': '.pdf',
            'docx': '.docx',
            'xlsx': '.xlsx'
        }

        if format_type not in filters:
            logger.error("Попытка сохранения отчета в неподдерживаемом формате: %s", format_type)
            QMessageBox.critical(self, 'Ошибка', f'Формат "{format_type}" не поддерживается.')
            return

        report_info = self.get_report_info()
        angular_measurements = self._collect_angular_measurements()

        # Получаем последнюю папку, в которую сохранялся отчет, или используем стандартную
        last_report_dir = self.report_paths_settings.value('last_report_dir', '')
        if last_report_dir and Path(last_report_dir).exists():
            documents_dir = last_report_dir
        else:
            documents_dir = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
            if not documents_dir:
                documents_dir = str(Path.home())

        default_filename = self._suggest_default_filename(extensions[format_type], report_info)
        initial_path = str(Path(documents_dir) / default_filename)

        dialog_title = f'Сохранить отчет ({format_type.upper()})'
        file_path_str, _ = QFileDialog.getSaveFileName(
            self,
            dialog_title,
            initial_path,
            filters[format_type]
        )

        if not file_path_str:
            logger.debug("Сохранение отчета отменено пользователем.")
            return

        file_path = Path(file_path_str)
        if file_path.suffix.lower() != extensions[format_type]:
            file_path = file_path.with_suffix(extensions[format_type])

        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as mkdir_error:
            logger.error("Не удалось создать директорию для сохранения отчета: %s", mkdir_error, exc_info=True)
            QMessageBox.critical(
                self,
                'Ошибка сохранения',
                f'Не удалось подготовить путь для сохранения отчета:\n{mkdir_error}'
            )
            return

        try:
            if format_type == 'pdf':
                self._save_pdf(str(file_path), report_info, angular_measurements)
            elif format_type == 'docx':
                self._save_docx(str(file_path), report_info, angular_measurements)
            elif format_type == 'xlsx':
                self._save_xlsx(str(file_path))
            else:
                raise ValueError(f'Неизвестный формат отчета: {format_type}')
        except Exception as save_error:
            logger.error("Ошибка при сохранении отчета (%s): %s", format_type, save_error, exc_info=True)
            QMessageBox.critical(
                self,
                'Ошибка сохранения',
                f'Не удалось сохранить отчет:\n{save_error}'
            )
            return

        # Сохраняем путь к папке для следующего раза
        saved_dir = str(file_path.parent)
        self.report_paths_settings.setValue('last_report_dir', saved_dir)
        self.report_paths_settings.sync()
        
        logger.info("Отчет сохранен пользователем: %s", file_path)
        QMessageBox.information(
            self,
            'Сохранение отчета',
            f'Отчет успешно сохранен:\n{file_path}'
        )

    def save_full_report(self):
        """Сохранение полного отчета по форме ДО ТСС."""
        if not self.processed_data or not self.processed_data.get('valid'):
            QMessageBox.warning(self, 'Предупреждение', 'Нет данных для сохранения. Выполните расчет.')
            return

        if not self.template_combo or self.template_combo.count() == 0:
            QMessageBox.warning(self, 'Шаблон не выбран', 'Добавьте шаблон полного отчета в каталог шаблонов.')
            return

        template_name = self.template_combo.currentText()
        if not template_name:
            QMessageBox.warning(self, 'Шаблон не выбран', 'Выберите шаблон полного отчета.')
            return

        report_info = self.get_report_info()
        default_filename = self._sanitize_filename_component(report_info.get('project_name'), 'Полный отчет')
        default_filename = f"{default_filename}_DO_TSS.docx"

        # Получаем последнюю папку, в которую сохранялся отчет, или используем стандартную
        last_report_dir = self.report_paths_settings.value('last_report_dir', '')
        if last_report_dir and Path(last_report_dir).exists():
            documents_dir = last_report_dir
        else:
            documents_dir = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
            if not documents_dir:
                documents_dir = str(Path.home())
        initial_path = str(Path(documents_dir) / default_filename)

        file_path_str, _ = QFileDialog.getSaveFileName(
            self,
            'Сохранить полный отчет (DOCX)',
            initial_path,
            'Word файлы (*.docx)'
        )
        if not file_path_str:
            return

        file_path = Path(file_path_str)
        if file_path.suffix.lower() != '.docx':
            file_path = file_path.with_suffix('.docx')

        try:
            self.full_report_builder.build_from_template(
                template_name,
                self.processed_data,
                self.raw_data,
                str(file_path)
            )
        except Exception as error:
            logger.error("Ошибка формирования полного отчета: %s", error, exc_info=True)
            QMessageBox.critical(
                self,
                'Ошибка сохранения',
                f'Не удалось сформировать полный отчет:\n{error}'
            )
            return

        # Сохраняем путь к папке для следующего раза
        saved_dir = str(file_path.parent)
        self.report_paths_settings.setValue('last_report_dir', saved_dir)
        self.report_paths_settings.sync()
        
        QMessageBox.information(
            self,
            'Полный отчет сохранен',
            f'Отчет успешно сохранен:\n{file_path}'
        )

    def _save_pdf(self, file_path: str, report_info: dict, angular_measurements: dict):
        """Сохранение в PDF с использованием расширенного генератора."""
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
        
    def _save_docx(self, file_path: str, report_info: dict | None = None, angular_measurements: dict | None = None):
        """Сохранение в DOCX"""
        if report_info is None:
            report_info = self.get_report_info()
        if angular_measurements is None:
            angular_measurements = self._collect_angular_measurements()

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
    
    def _save_xlsx(self, file_path: str):
        """Сохранение в XLSX"""
        # Получаем данные угловых измерений
        angular_measurements = self._collect_angular_measurements()
        has_angular_data = bool(angular_measurements and (angular_measurements.get('x') or angular_measurements.get('y')))
        
        # Показываем диалог параметров экспорта
        dialog = ExcelExportDialog(self, has_angular_data=has_angular_data)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return  # Пользователь отменил экспорт
        
        export_options = dialog.get_options()
        
        # Передаем данные угловых измерений только если они включены
        final_angular_measurements = angular_measurements if export_options.get('include_angular', False) else None
        
        generator = ReportGenerator()
        generator.generate_excel_report(
            self.raw_data,
            self.processed_data,
            file_path,
            angular_measurements=final_angular_measurements
        )
    
    def closeEvent(self, event):
        """Обработчик закрытия виджета"""
        self.cleanup_temp_files()
        super().closeEvent(event)
