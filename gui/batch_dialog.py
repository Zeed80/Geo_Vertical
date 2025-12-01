"""
Диалог пакетной обработки файлов
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QListWidget,
    QLabel, QProgressBar, QTextEdit, QFileDialog, QMessageBox,
    QGroupBox, QFormLayout, QDoubleSpinBox, QComboBox, QDialogButtonBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from typing import List, Dict, Any, Optional
import logging

from core.batch_processor import BatchProcessor
from core.exceptions import ExportError

logger = logging.getLogger(__name__)


class BatchProcessThread(QThread):
    """Поток для пакетной обработки файлов"""
    
    progress = pyqtSignal(int, int, str)  # current, total, message
    finished = pyqtSignal(list)  # results
    error = pyqtSignal(str)  # error_message
    
    def __init__(
        self,
        file_paths: List[str],
        height_tolerance: float,
        center_method: str,
        parent=None
    ):
        super().__init__(parent)
        self.file_paths = file_paths
        self.height_tolerance = height_tolerance
        self.center_method = center_method
        self.processor = BatchProcessor()
    
    def run(self):
        """Выполнение пакетной обработки"""
        try:
            results = self.processor.process_files(
                self.file_paths,
                height_tolerance=self.height_tolerance,
                center_method=self.center_method,
                progress_callback=lambda c, t, m: self.progress.emit(c, t, m)
            )
            self.finished.emit(results)
        except Exception as e:
            self.error.emit(f"Ошибка пакетной обработки: {str(e)}")


class BatchProcessingDialog(QDialog):
    """Диалог для пакетной обработки файлов"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Пакетная обработка файлов')
        self.setModal(True)
        self.resize(700, 600)
        
        self.file_paths: List[str] = []
        self.results: List[Dict[str, Any]] = []
        self.process_thread: Optional[BatchProcessThread] = None
        
        self.init_ui()
    
    def init_ui(self):
        """Инициализация интерфейса"""
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        # Группа выбора файлов
        files_group = QGroupBox('Файлы для обработки')
        files_layout = QVBoxLayout()
        files_group.setLayout(files_layout)
        
        buttons_layout = QHBoxLayout()
        add_files_btn = QPushButton('➕ Добавить файлы')
        add_files_btn.clicked.connect(self.add_files)
        buttons_layout.addWidget(add_files_btn)
        
        remove_file_btn = QPushButton('➖ Удалить выбранный')
        remove_file_btn.clicked.connect(self.remove_selected_file)
        buttons_layout.addWidget(remove_file_btn)
        
        clear_files_btn = QPushButton('🗑️ Очистить список')
        clear_files_btn.clicked.connect(self.clear_files)
        buttons_layout.addWidget(clear_files_btn)
        buttons_layout.addStretch()
        
        files_layout.addLayout(buttons_layout)
        
        self.files_list = QListWidget()
        self.files_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        files_layout.addWidget(self.files_list)
        
        layout.addWidget(files_group)
        
        # Группа параметров
        params_group = QGroupBox('Параметры обработки')
        params_layout = QFormLayout()
        params_group.setLayout(params_layout)
        
        self.height_tolerance_spin = QDoubleSpinBox()
        self.height_tolerance_spin.setRange(0.01, 1.0)
        self.height_tolerance_spin.setSingleStep(0.01)
        self.height_tolerance_spin.setValue(0.1)
        self.height_tolerance_spin.setDecimals(2)
        self.height_tolerance_spin.setSuffix(' м')
        params_layout.addRow('Допуск по высоте:', self.height_tolerance_spin)
        
        self.center_method_combo = QComboBox()
        self.center_method_combo.addItem('Среднее арифметическое', 'mean')
        self.center_method_combo.addItem('Метод наименьших квадратов', 'lsq')
        params_layout.addRow('Метод центрирования:', self.center_method_combo)
        
        layout.addWidget(params_group)
        
        # Прогресс-бар
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        self.status_label = QLabel('Готов к обработке')
        layout.addWidget(self.status_label)
        
        # Лог обработки
        log_group = QGroupBox('Лог обработки')
        log_layout = QVBoxLayout()
        log_group.setLayout(log_layout)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(150)
        log_layout.addWidget(self.log_text)
        
        layout.addWidget(log_group)
        
        # Кнопки
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | 
            QDialogButtonBox.StandardButton.Cancel |
            QDialogButtonBox.StandardButton.Save
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText('Начать обработку')
        buttons.button(QDialogButtonBox.StandardButton.Save).setText('Сохранить отчет')
        buttons.button(QDialogButtonBox.StandardButton.Save).setEnabled(False)
        buttons.accepted.connect(self.start_processing)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.Save).clicked.connect(self.save_summary_report)
        
        layout.addWidget(buttons)
    
    def add_files(self):
        """Добавление файлов в список"""
        files, _ = QFileDialog.getOpenFileNames(
            self,
            'Выберите файлы для обработки',
            '',
            'Все поддерживаемые форматы (*.csv *.txt *.jxl *.jobxml *.dxf *.shp *.geojson);;'
            'CSV файлы (*.csv);;Trimble (*.jxl *.jobxml);;DXF (*.dxf);;Shapefile (*.shp);;GeoJSON (*.geojson)'
        )
        
        for file_path in files:
            if file_path not in self.file_paths:
                self.file_paths.append(file_path)
                from pathlib import Path
                self.files_list.addItem(Path(file_path).name)
        
        self.update_status()
    
    def remove_selected_file(self):
        """Удаление выбранного файла из списка"""
        current_row = self.files_list.currentRow()
        if current_row >= 0:
            self.files_list.takeItem(current_row)
            del self.file_paths[current_row]
            self.update_status()
    
    def clear_files(self):
        """Очистка списка файлов"""
        self.file_paths.clear()
        self.files_list.clear()
        self.update_status()
    
    def update_status(self):
        """Обновление статуса"""
        count = len(self.file_paths)
        self.status_label.setText(f'Выбрано файлов: {count}')
    
    def start_processing(self):
        """Запуск пакетной обработки"""
        if not self.file_paths:
            QMessageBox.warning(self, 'Предупреждение', 'Выберите файлы для обработки')
            return
        
        # Блокируем кнопки
        self.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(len(self.file_paths))
        self.progress_bar.setValue(0)
        self.log_text.clear()
        
        # Создаем и запускаем поток обработки
        self.process_thread = BatchProcessThread(
            self.file_paths,
            self.height_tolerance_spin.value(),
            self.center_method_combo.currentData(),
            self
        )
        self.process_thread.progress.connect(self.on_progress)
        self.process_thread.finished.connect(self.on_processing_finished)
        self.process_thread.error.connect(self.on_processing_error)
        self.process_thread.start()
    
    def on_progress(self, current: int, total: int, message: str):
        """Обработка прогресса"""
        self.progress_bar.setValue(current)
        self.status_label.setText(message)
        self.log_text.append(f"[{current}/{total}] {message}")
    
    def on_processing_finished(self, results: List[Dict[str, Any]]):
        """Обработка завершения"""
        self.results = results
        self.progress_bar.setValue(self.progress_bar.maximum())
        
        # Генерируем сводку
        from core.batch_processor import BatchProcessor
        processor = BatchProcessor()
        processor.results = results
        summary = processor.generate_summary_report()
        
        # Показываем результаты
        success_count = summary['successful']
        failed_count = summary['failed']
        
        self.log_text.append("\n" + "="*50)
        self.log_text.append("ОБРАБОТКА ЗАВЕРШЕНА")
        self.log_text.append("="*50)
        self.log_text.append(f"Всего файлов: {summary['total_files']}")
        self.log_text.append(f"Успешно обработано: {success_count}")
        self.log_text.append(f"Ошибок: {failed_count}")
        self.log_text.append(f"Всего точек: {summary['total_points']}")
        self.log_text.append(f"Всего поясов: {summary['total_belts']}")
        
        if failed_count > 0:
            self.log_text.append("\nОшибки:")
            for error_info in summary['errors']:
                self.log_text.append(f"  {error_info['file']}: {error_info['error']}")
        
        self.status_label.setText(
            f'Обработка завершена: ✓{success_count} ✗{failed_count}'
        )
        
        # Разблокируем кнопки
        self.setEnabled(True)
        buttons = self.findChild(QDialogButtonBox)
        if buttons:
            buttons.button(QDialogButtonBox.StandardButton.Save).setEnabled(True)
        
        QMessageBox.information(
            self,
            'Обработка завершена',
            f'Обработано файлов: {success_count}/{summary["total_files"]}\n\n'
            f'Успешно: {success_count}\n'
            f'Ошибок: {failed_count}'
        )
    
    def on_processing_error(self, error_message: str):
        """Обработка ошибки"""
        self.log_text.append(f"ОШИБКА: {error_message}")
        self.status_label.setText(f'Ошибка: {error_message}')
        self.setEnabled(True)
        QMessageBox.critical(self, 'Ошибка обработки', error_message)
    
    def save_summary_report(self):
        """Сохранение сводного отчета"""
        if not self.results:
            QMessageBox.warning(self, 'Предупреждение', 'Нет результатов для сохранения')
            return
        
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            'Сохранить сводный отчет',
            'Сводный отчет пакетной обработки',
            'Excel файлы (*.xlsx);;CSV файлы (*.csv)'
        )
        
        if not file_path:
            return
        
        try:
            from core.batch_processor import BatchProcessor
            processor = BatchProcessor()
            processor.results = self.results
            summary = processor.generate_summary_report()
            
            # Создаем DataFrame с результатами
            import pandas as pd
            report_data = []
            for result in self.results:
                report_data.append({
                    'Файл': result['file_name'],
                    'Успешно': 'Да' if result.get('success') else 'Нет',
                    'Точек': result.get('points_count', 0),
                    'Поясов': result.get('belts_count', 0),
                    'Вертикальность (✓)': result.get('vertical_passed', 0),
                    'Вертикальность (✗)': result.get('vertical_failed', 0),
                    'Прямолинейность (✓)': result.get('straightness_passed', 0),
                    'Прямолинейность (✗)': result.get('straightness_failed', 0),
                    'Ошибка': result.get('error', '')
                })
            
            df = pd.DataFrame(report_data)
            
            if file_path.endswith('.xlsx'):
                with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
                    # Лист с результатами
                    df.to_excel(writer, sheet_name='Результаты', index=False)
                    
                    # Лист со сводкой
                    summary_data = pd.DataFrame([{
                        'Всего файлов': summary['total_files'],
                        'Успешно': summary['successful'],
                        'Ошибок': summary['failed'],
                        'Всего точек': summary['total_points'],
                        'Всего поясов': summary['total_belts'],
                        'Вертикальность (✓)': summary['total_vertical_passed'],
                        'Вертикальность (✗)': summary['total_vertical_failed'],
                        'Прямолинейность (✓)': summary['total_straightness_passed'],
                        'Прямолинейность (✗)': summary['total_straightness_failed']
                    }])
                    summary_data.to_excel(writer, sheet_name='Сводка', index=False)
            else:
                # CSV
                df.to_csv(file_path, index=False, encoding='utf-8-sig')
            
            QMessageBox.information(self, 'Успех', f'Сводный отчет сохранен:\n{file_path}')
            
        except Exception as e:
            logger.error(f"Ошибка сохранения сводного отчета: {e}", exc_info=True)
            QMessageBox.critical(self, 'Ошибка', f'Ошибка сохранения отчета:\n{str(e)}')

