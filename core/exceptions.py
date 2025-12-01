"""
Кастомные исключения для GeoVertical Analyzer

Иерархия исключений:
    GeoVerticalError
    ├── DataLoadError
    │   ├── FileFormatError
    │   ├── DataValidationError
    │   ├── TrimbleError
    │   │   ├── TrimbleBinaryNotSupportedError
    │   │   └── TrimbleParsingError
    │   └── FieldGeniusError
    │       └── FieldGeniusParsingError
    ├── CalculationError
    │   ├── InsufficientDataError
    │   ├── InvalidCoordinatesError
    │   └── GroupingError
    ├── NormativeError
    │   └── NormativeViolationError
    ├── ReportGenerationError
    │   ├── PDFGenerationError
    │   └── ExcelGenerationError
    ├── FilteringError
    │   └── AutoFilterError
    ├── CoordinateSystemError
    │   ├── EPSGNotFoundError
    │   └── CoordinateTransformError
    ├── ProjectError
    │   ├── ProjectSaveError
    │   └── ProjectLoadError
    ├── SettingsError
    │   ├── SettingsLoadError
    │   └── SettingsSaveError
    └── ExportError
        └── SchemaExportError
"""


class GeoVerticalError(Exception):
    """Базовое исключение для всех ошибок GeoVertical Analyzer"""
    pass


# ========== Ошибки загрузки данных ==========

class DataLoadError(GeoVerticalError):
    """Ошибка при загрузке данных из файла"""
    pass


class FileFormatError(DataLoadError):
    """Неподдерживаемый или некорректный формат файла"""
    pass


class DataValidationError(DataLoadError):
    """Ошибка валидации загруженных данных"""
    pass


# ========== Ошибки расчетов ==========

class CalculationError(GeoVerticalError):
    """Ошибка при выполнении расчетов"""
    pass


class InsufficientDataError(CalculationError):
    """Недостаточно данных для выполнения расчета"""
    def __init__(self, required: int, actual: int, message: str = None):
        self.required = required
        self.actual = actual
        if message is None:
            message = f"Недостаточно данных для расчета: требуется {required}, получено {actual}"
        super().__init__(message)


class InvalidCoordinatesError(CalculationError):
    """Некорректные координаты точек"""
    pass


class GroupingError(CalculationError):
    """Ошибка при группировке точек по поясам"""
    pass


# ========== Ошибки нормативов ==========

class NormativeError(GeoVerticalError):
    """Ошибка при проверке нормативов"""
    pass


class NormativeViolationError(NormativeError):
    """Нарушение нормативных требований"""
    def __init__(self, normative: str, actual: float, required: float, message: str = None):
        self.normative = normative
        self.actual = actual
        self.required = required
        if message is None:
            message = f"Нарушение норматива {normative}: {actual:.4f} > {required:.4f}"
        super().__init__(message)


# ========== Ошибки генерации отчетов ==========

class ReportGenerationError(GeoVerticalError):
    """Ошибка при генерации отчета"""
    pass


class PDFGenerationError(ReportGenerationError):
    """Ошибка при генерации PDF отчета"""
    pass


class ExcelGenerationError(ReportGenerationError):
    """Ошибка при генерации Excel отчета"""
    pass


# ========== Ошибки фильтрации точек ==========

class FilteringError(GeoVerticalError):
    """Ошибка при фильтрации точек"""
    pass


class AutoFilterError(FilteringError):
    """Ошибка автоматической фильтрации"""
    pass


# ========== Ошибки работы с координатными системами ==========

class CoordinateSystemError(GeoVerticalError):
    """Ошибка при работе с координатными системами"""
    pass


class EPSGNotFoundError(CoordinateSystemError):
    """EPSG код не найден или не поддерживается"""
    pass


class CoordinateTransformError(CoordinateSystemError):
    """Ошибка при трансформации координат"""
    pass


# ========== Ошибки работы с Trimble ==========

class TrimbleError(DataLoadError):
    """Ошибка при работе с форматами Trimble"""
    pass


class TrimbleBinaryNotSupportedError(TrimbleError):
    """Бинарные JOB файлы не поддерживаются"""
    def __init__(self, file_path: str = None):
        message = (
            "Прямая загрузка бинарных JOB файлов не поддерживается.\n\n"
            "Формат JOB является проприетарным и недокументированным.\n\n"
            "РЕШЕНИЕ:\n"
            "1. Откройте JOB файл в Trimble Business Center\n"
            "2. Экспортируйте данные в один из форматов:\n"
            "   - JobXML (File → Export → JobXML)\n"
            "   - CSV (File → Export → CSV/Text)\n"
            "   - Shapefile (File → Export → Shapefile)\n"
            "3. Загрузите полученный файл в программу\n\n"
            "Поддерживаемые форматы: .jxl (JobXML), .csv, .txt, .shp"
        )
        if file_path:
            message = f"Файл: {file_path}\n\n" + message
        super().__init__(message)


class TrimbleParsingError(TrimbleError):
    """Ошибка при парсинге Trimble файла"""
    pass


# ========== Ошибки работы с FieldGenius ==========

class FieldGeniusError(DataLoadError):
    """Ошибка при работе с форматами FieldGenius"""
    pass


class FieldGeniusParsingError(FieldGeniusError):
    """Ошибка при парсинге FieldGenius RAW файла"""
    pass


# ========== Ошибки работы с проектами ==========

class ProjectError(GeoVerticalError):
    """Ошибка при работе с проектом"""
    pass


class ProjectSaveError(ProjectError):
    """Ошибка при сохранении проекта"""
    pass


class ProjectLoadError(ProjectError):
    """Ошибка при загрузке проекта"""
    pass


# ========== Ошибки работы с настройками ==========

class SettingsError(GeoVerticalError):
    """Ошибка при работе с настройками"""
    pass


class SettingsLoadError(SettingsError):
    """Ошибка при загрузке настроек"""
    pass


class SettingsSaveError(SettingsError):
    """Ошибка при сохранении настроек"""
    pass


# ========== Ошибки экспорта ==========

class ExportError(GeoVerticalError):
    """Ошибка при экспорте данных"""
    pass


class SchemaExportError(ExportError):
    """Ошибка при экспорте схемы"""
    pass
