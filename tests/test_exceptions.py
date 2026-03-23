"""Тесты для core.exceptions — кастомные исключения."""


from core.exceptions import (
    AutoFilterError,
    CalculationError,
    CoordinateSystemError,
    CoordinateTransformError,
    DataLoadError,
    DataValidationError,
    EPSGNotFoundError,
    ExcelGenerationError,
    ExportError,
    FieldGeniusError,
    FieldGeniusParsingError,
    FileFormatError,
    FilteringError,
    GeoVerticalError,
    GroupingError,
    InsufficientDataError,
    InvalidCoordinatesError,
    NormativeError,
    NormativeViolationError,
    PDFGenerationError,
    ProjectError,
    ProjectLoadError,
    ProjectSaveError,
    ReportGenerationError,
    SchemaExportError,
    SettingsError,
    SettingsLoadError,
    SettingsSaveError,
    TrimbleBinaryNotSupportedError,
    TrimbleError,
    TrimbleParsingError,
)


class TestExceptionHierarchy:
    def test_base_is_exception(self):
        assert issubclass(GeoVerticalError, Exception)

    def test_data_load_hierarchy(self):
        assert issubclass(DataLoadError, GeoVerticalError)
        assert issubclass(FileFormatError, DataLoadError)
        assert issubclass(DataValidationError, DataLoadError)

    def test_trimble_hierarchy(self):
        assert issubclass(TrimbleError, DataLoadError)
        assert issubclass(TrimbleBinaryNotSupportedError, TrimbleError)
        assert issubclass(TrimbleParsingError, TrimbleError)

    def test_fieldgenius_hierarchy(self):
        assert issubclass(FieldGeniusError, DataLoadError)
        assert issubclass(FieldGeniusParsingError, FieldGeniusError)

    def test_calculation_hierarchy(self):
        assert issubclass(CalculationError, GeoVerticalError)
        assert issubclass(InsufficientDataError, CalculationError)
        assert issubclass(InvalidCoordinatesError, CalculationError)
        assert issubclass(GroupingError, CalculationError)

    def test_normative_hierarchy(self):
        assert issubclass(NormativeError, GeoVerticalError)
        assert issubclass(NormativeViolationError, NormativeError)

    def test_report_hierarchy(self):
        assert issubclass(ReportGenerationError, GeoVerticalError)
        assert issubclass(PDFGenerationError, ReportGenerationError)
        assert issubclass(ExcelGenerationError, ReportGenerationError)

    def test_filter_hierarchy(self):
        assert issubclass(FilteringError, GeoVerticalError)
        assert issubclass(AutoFilterError, FilteringError)

    def test_coordinate_hierarchy(self):
        assert issubclass(CoordinateSystemError, GeoVerticalError)
        assert issubclass(EPSGNotFoundError, CoordinateSystemError)
        assert issubclass(CoordinateTransformError, CoordinateSystemError)

    def test_project_hierarchy(self):
        assert issubclass(ProjectError, GeoVerticalError)
        assert issubclass(ProjectSaveError, ProjectError)
        assert issubclass(ProjectLoadError, ProjectError)

    def test_settings_hierarchy(self):
        assert issubclass(SettingsError, GeoVerticalError)
        assert issubclass(SettingsLoadError, SettingsError)
        assert issubclass(SettingsSaveError, SettingsError)

    def test_export_hierarchy(self):
        assert issubclass(ExportError, GeoVerticalError)
        assert issubclass(SchemaExportError, ExportError)


class TestInsufficientDataError:
    def test_default_message(self):
        err = InsufficientDataError(required=10, actual=3)
        assert err.required == 10
        assert err.actual == 3
        assert '10' in str(err)
        assert '3' in str(err)

    def test_custom_message(self):
        err = InsufficientDataError(required=5, actual=1, message='my msg')
        assert str(err) == 'my msg'


class TestNormativeViolationError:
    def test_default_message(self):
        err = NormativeViolationError(normative='test_norm', actual=0.015, required=0.010)
        assert err.normative == 'test_norm'
        assert err.actual == 0.015
        assert err.required == 0.010
        assert 'test_norm' in str(err)

    def test_custom_message(self):
        err = NormativeViolationError(normative='n', actual=1.0, required=0.5, message='oops')
        assert str(err) == 'oops'


class TestTrimbleBinaryNotSupportedError:
    def test_without_path(self):
        err = TrimbleBinaryNotSupportedError()
        assert 'JOB' in str(err)

    def test_with_path(self):
        err = TrimbleBinaryNotSupportedError(file_path='test.job')
        assert 'test.job' in str(err)
        assert 'JOB' in str(err)
