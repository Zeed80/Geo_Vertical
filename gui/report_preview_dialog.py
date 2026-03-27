"""
Интерактивное окно предпросмотра отчета с таблицами и графиками
"""
import logging
from pathlib import Path
import tempfile
import base64
from io import BytesIO
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
                             QLabel, QTextBrowser, QScrollArea, QWidget)
from PyQt6.QtGui import QFont

from gui.ui_helpers import apply_compact_button_style
logger = logging.getLogger(__name__)


class ReportPreviewDialog(QDialog):
    """Диалог предпросмотра отчета с интерактивным HTML-представлением"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Предпросмотр отчета')
        self.setMinimumSize(900, 700)
        self.resize(1100, 800)
        
        # Временные файлы для графиков
        self.temp_files = []
        self.temp_dir = None
        
        self.init_ui()
    
    def init_ui(self):
        """Инициализация интерфейса"""
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        self.setLayout(layout)
        
        # Заголовок
        title_label = QLabel('📄 Предпросмотр отчета')
        title_label.setFont(QFont('Arial', 14, QFont.Weight.Bold))
        layout.addWidget(title_label)
        
        # Область просмотра
        self.preview_browser = QTextBrowser()
        self.preview_browser.setFont(QFont('Arial', 10))
        layout.addWidget(self.preview_browser)
        
        # Кнопки
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()
        
        self.close_btn = QPushButton('Закрыть')
        self.close_btn.clicked.connect(self.accept)
        apply_compact_button_style(self.close_btn, width=120, min_height=34)
        buttons_layout.addWidget(self.close_btn)
        
        layout.addLayout(buttons_layout)
    
    def generate_preview_html(self, 
                             raw_data, 
                             processed_data,
                             verticality_widget=None,
                             straightness_widget=None,
                             project_name="Объект контроля",
                             organization="",
                             report_info=None):
        """Генерация HTML-представления отчета
        
        Args:
            raw_data: Исходные данные
            processed_data: Обработанные данные
            verticality_widget: Виджет вертикальности
            straightness_widget: Виджет прямолинейности
            project_name: Название проекта
            organization: Организация
        """
        try:
            # Создаем временную директорию для графиков
            self.temp_dir = Path(tempfile.mkdtemp(prefix='geov_report_'))
            
            html_parts = []
            
            # Стили
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
            
            # Таблица вертикальности
            html_parts.append('<h2>2. ТАБЛИЦА ОТКЛОНЕНИЙ СТВОЛА ОТ ВЕРТИКАЛИ</h2>')
            
            from core.services.verticality_sections import get_preferred_verticality_sections

            verticality_widget_data = []
            if verticality_widget and hasattr(verticality_widget, 'get_table_data'):
                try:
                    verticality_widget_data = verticality_widget.get_table_data()
                except Exception as e:
                    logger.warning(f"Ошибка получения данных вертикальности: {e}")
            verticality_data = get_preferred_verticality_sections(
                processed_data.get('angular_verticality') if isinstance(processed_data, dict) else None,
                verticality_widget_data,
            )
            
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
                    
                    tolerance_mm = get_vertical_tolerance(height) * 1000
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
            
            # График вертикальности
            if verticality_widget and hasattr(verticality_widget, 'figure'):
                html_parts.append('<h3>График вертикальности</h3>')
                chart_path = self.temp_dir / 'verticality_chart.png'
                verticality_widget.figure.savefig(str(chart_path), dpi=150, bbox_inches='tight')
                self.temp_files.append(str(chart_path))
                
                # Конвертируем изображение в base64 для встраивания в HTML
                with open(chart_path, 'rb') as f:
                    img_data = base64.b64encode(f.read()).decode('utf-8')
                
                html_parts.append('<div class="chart-container">')
                html_parts.append(f'<img src="data:image/png;base64,{img_data}" alt="График вертикальности">')
                html_parts.append('<p><em>Рис. 1. Отклонения центров поясов от вертикальной оси мачты</em></p>')
                html_parts.append('</div>')
            
            # Таблица прогибов
            html_parts.append('<h2>3. ТАБЛИЦА СТРЕЛ ПРОГИБА ПОЯСОВ СТВОЛА (ПРЯМОЛИНЕЙНОСТЬ)</h2>')
            
            from core.services.straightness_profiles import get_preferred_straightness_part_map

            straightness_widget_data = {}
            if straightness_widget and hasattr(straightness_widget, 'get_all_belts_data'):
                try:
                    straightness_widget_data = straightness_widget.get_all_belts_data()
                except Exception as e:
                    logger.warning(f"Ошибка получения данных прямолинейности: {e}")

            straightness_data = get_preferred_straightness_part_map(
                processed_data.get('straightness_profiles') if isinstance(processed_data, dict) else None,
                straightness_widget_data,
                points=raw_data,
                tower_parts_info=processed_data.get('tower_parts_info') if isinstance(processed_data, dict) else None,
            )

            if straightness_data:
                for part_num in sorted(straightness_data.keys()):
                    part_info = straightness_data[part_num]
                    belts_data = part_info.get('belts', {})
                    if not belts_data:
                        continue

                    min_height = float(part_info.get('min_height', 0.0) or 0.0)
                    max_height = float(part_info.get('max_height', 0.0) or 0.0)
                    if len(straightness_data) > 1:
                        min_str = f"{min_height:.1f}".replace('.', ',')
                        max_str = f"{max_height:.3f}".replace('.', ',')
                        html_parts.append(f'<h3>Часть {part_num} ({min_str} - {max_str})</h3>')

                    all_heights = set()
                    max_tolerance = 0.0
                    for belt_data in belts_data.values():
                        for item in belt_data:
                            all_heights.add(round(float(item['height']), 1))
                            max_tolerance = max(max_tolerance, float(item.get('tolerance', 0.0) or 0.0))

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

                    belt_height_deflection = {}
                    for belt_num, belt_data in belts_data.items():
                        for item in belt_data:
                            height_rounded = round(float(item['height']), 1)
                            belt_height_deflection[(belt_num, height_rounded)] = float(item.get('deflection', 0.0) or 0.0)

                    for height in sorted_heights:
                        html_parts.append('<tr>')
                        html_parts.append(f'<td>{height:.1f}</td>')

                        for belt_num in sorted_belts:
                            key = (belt_num, height)
                            if key in belt_height_deflection:
                                deflection = belt_height_deflection[key]
                                status_class = 'status-error' if abs(deflection) > max_tolerance else 'status-ok'
                                html_parts.append(f'<td class="{status_class}">{deflection:+.1f}</td>')
                            else:
                                html_parts.append('<td>-</td>')

                        html_parts.append(f'<td>±{max_tolerance:.1f}</td>')
                        html_parts.append('</tr>')

                    html_parts.append('</tbody>')
                    html_parts.append('</table>')
            else:
                html_parts.append('<p><em>Нет данных для отображения</em></p>')
            
            # Графики прямолинейности
            if straightness_widget:
                html_parts.append('<h3>Графики прямолинейности</h3>')
                
                # Пытаемся получить объединенный график
                if hasattr(straightness_widget, 'get_combined_figure_for_pdf'):
                    combined_figure = straightness_widget.get_combined_figure_for_pdf()
                    if combined_figure:
                        chart_path = self.temp_dir / 'straightness_combined.png'
                        combined_figure.savefig(str(chart_path), dpi=150, bbox_inches='tight')
                        self.temp_files.append(str(chart_path))
                        
                        with open(chart_path, 'rb') as f:
                            img_data = base64.b64encode(f.read()).decode('utf-8')
                        
                        html_parts.append('<div class="chart-container">')
                        html_parts.append(f'<img src="data:image/png;base64,{img_data}" alt="Графики прямолинейности">')
                        html_parts.append('<p><em>Рис. 2. Отклонения от прямолинейности (стрела прогиба)</em></p>')
                        html_parts.append('</div>')
                
                # Если нет объединенного, пробуем отдельные графики
                elif hasattr(straightness_widget, 'get_all_figures_for_pdf'):
                    figures_list = straightness_widget.get_all_figures_for_pdf()
                    for fig_num, (belt_num, figure) in enumerate(figures_list, start=2):
                        chart_path = self.temp_dir / f'straightness_belt_{belt_num}.png'
                        figure.savefig(str(chart_path), dpi=150, bbox_inches='tight')
                        self.temp_files.append(str(chart_path))
                        
                        with open(chart_path, 'rb') as f:
                            img_data = base64.b64encode(f.read()).decode('utf-8')
                        
                        html_parts.append('<div class="chart-container">')
                        html_parts.append(f'<img src="data:image/png;base64,{img_data}" alt="График пояса {belt_num}">')
                        html_parts.append(f'<p><em>Рис. {fig_num}. Отклонения от прямолинейности пояса {belt_num}</em></p>')
                        html_parts.append('</div>')
            
            html_parts.append('<div class="footer">')
            html_parts.append('<p>Отчет сгенерирован программой GeoVertical Analyzer v1.0</p>')
            html_parts.append('</div>')
            
            html_parts.append('</div>')  # закрываем container
            
            html_content = '\n'.join(html_parts)
            self.preview_browser.setHtml(html_content)
            
            logger.info("HTML предпросмотр сгенерирован успешно")
            
        except Exception as e:
            logger.error(f"Ошибка генерации HTML предпросмотра: {e}", exc_info=True)
            self.preview_browser.setHtml(f'<p style="color: red;">Ошибка генерации предпросмотра: {str(e)}</p>')
    
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
    
    def closeEvent(self, event):
        """Обработчик закрытия окна"""
        self.cleanup_temp_files()
        super().closeEvent(event)
