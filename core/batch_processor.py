"""
Модуль пакетной обработки нескольких файлов
"""

import logging
from pathlib import Path
from typing import Any

import pandas as pd

from core.data_loader import load_data_from_file, validate_data
from core.exceptions import CalculationError, DataLoadError, DataValidationError
from core.services.calculation_service import CalculationService

logger = logging.getLogger(__name__)


class BatchProcessor:
    """
    Класс для пакетной обработки нескольких файлов
    """

    def __init__(self):
        """Инициализация процессора"""
        self.calculation_service = CalculationService()
        self.results: list[dict[str, Any]] = []

    def process_files(
        self,
        file_paths: list[str],
        height_tolerance: float = 0.1,
        center_method: str = 'mean',
        progress_callback: callable | None = None
    ) -> list[dict[str, Any]]:
        """
        Обрабатывает список файлов

        Args:
            file_paths: Список путей к файлам
            height_tolerance: Допуск группировки по высоте
            center_method: Метод расчета центра
            progress_callback: Функция обратного вызова для прогресса (current, total, message)

        Returns:
            Список результатов обработки для каждого файла
        """
        self.results = []
        total_files = len(file_paths)

        for i, file_path in enumerate(file_paths, 1):
            try:
                if progress_callback:
                    progress_callback(i, total_files, f"Обработка {Path(file_path).name}...")

                # Загружаем данные
                data, epsg_code = load_data_from_file(file_path)

                # Валидация
                is_valid, message = validate_data(data, check_outliers=False)  # Отключаем проверку выбросов для пакетной обработки
                if not is_valid:
                    self.results.append({
                        'file_path': file_path,
                        'file_name': Path(file_path).name,
                        'success': False,
                        'error': f"Валидация не пройдена: {message}",
                        'points_count': 0
                    })
                    continue

                # Выполняем расчеты
                results = self.calculation_service.calculate(
                    raw_data=data,
                    table_data=data,
                    epsg_code=epsg_code,
                    height_tolerance=height_tolerance,
                    center_method=center_method,
                    section_grouping_mode='height_levels'
                )

                # Извлекаем статистику
                centers = results.get('centers', pd.DataFrame())
                vertical_check = results.get('vertical_check', {'passed': 0, 'failed': 0})
                straightness_check = results.get('straightness_check', {'passed': 0, 'failed': 0})

                # Сохраняем результат
                self.results.append({
                    'file_path': file_path,
                    'file_name': Path(file_path).name,
                    'success': True,
                    'points_count': len(data),
                    'belts_count': len(centers),
                    'vertical_passed': vertical_check.get('passed', 0),
                    'vertical_failed': vertical_check.get('failed', 0),
                    'straightness_passed': straightness_check.get('passed', 0),
                    'straightness_failed': straightness_check.get('failed', 0),
                    'epsg_code': epsg_code,
                    'results': results  # Полные результаты для сводного отчета
                })

                logger.info(
                    f"Файл обработан: {Path(file_path).name} - "
                    f"{len(centers)} поясов, "
                    f"Вертикальность: ✓{vertical_check.get('passed', 0)} ✗{vertical_check.get('failed', 0)}"
                )

            except (DataLoadError, DataValidationError) as e:
                self.results.append({
                    'file_path': file_path,
                    'file_name': Path(file_path).name,
                    'success': False,
                    'error': f"Ошибка загрузки: {e!s}",
                    'points_count': 0
                })
                logger.error(f"Ошибка обработки файла {file_path}: {e}", exc_info=True)

            except CalculationError as e:
                self.results.append({
                    'file_path': file_path,
                    'file_name': Path(file_path).name,
                    'success': False,
                    'error': f"Ошибка расчета: {e!s}",
                    'points_count': len(data) if 'data' in locals() else 0
                })
                logger.error(f"Ошибка расчета для файла {file_path}: {e}", exc_info=True)

            except Exception as e:
                self.results.append({
                    'file_path': file_path,
                    'file_name': Path(file_path).name,
                    'success': False,
                    'error': f"Неожиданная ошибка: {e!s}",
                    'points_count': 0
                })
                logger.error(f"Неожиданная ошибка при обработке файла {file_path}: {e}", exc_info=True)

        return self.results

    def generate_summary_report(self) -> dict[str, Any]:
        """
        Генерирует сводный отчет по всем обработанным файлам

        Returns:
            Словарь со сводной статистикой
        """
        if not self.results:
            return {
                'total_files': 0,
                'successful': 0,
                'failed': 0,
                'total_points': 0,
                'total_belts': 0
            }

        successful = [r for r in self.results if r.get('success', False)]
        failed = [r for r in self.results if not r.get('success', False)]

        summary = {
            'total_files': len(self.results),
            'successful': len(successful),
            'failed': len(failed),
            'total_points': sum(r.get('points_count', 0) for r in successful),
            'total_belts': sum(r.get('belts_count', 0) for r in successful),
            'total_vertical_passed': sum(r.get('vertical_passed', 0) for r in successful),
            'total_vertical_failed': sum(r.get('vertical_failed', 0) for r in successful),
            'total_straightness_passed': sum(r.get('straightness_passed', 0) for r in successful),
            'total_straightness_failed': sum(r.get('straightness_failed', 0) for r in successful),
            'failed_files': [r['file_name'] for r in failed],
            'errors': [{'file': r['file_name'], 'error': r.get('error', 'Неизвестная ошибка')} for r in failed]
        }

        return summary

