---
name: Архитектурные паттерны и anti-patterns
description: Ключевые паттерны и нарушения в кодовой базе GeoVertical Analyzer
type: project
---

## Установленные паттерны

- Асинхронные операции через QThread (DataLoadThread, CalculationThread) с QProgressDialog — корректно реализованы
- Сигналы/слоты PyQt6 используются правильно; blockSignals() при programmatic updates
- Undo/Redo через core/undo_manager.py с MainWindowStateCommand, UndoManager (max 50 снимков)
- Пользовательские исключения из core/exceptions.py используются везде
- Rich tooltips реализованы в gui/rich_tooltip.py, применяются через set_rich_tooltip()
- Autosave через QTimer каждые 3 минуты с recover-диалогом при запуске
- Dark theme через QApplication.setStyleSheet() с persist в QSettings

## Критические нарушения (обнаружены при аудите 2026-03-28)

- full_report_tab.py: двойное определение _build_metadata_group() и _build_title_object_group() — строки 172-383 содержат обе версии, первая с нормальными строками, вторая с unicode-escapes. Первая версия перезаписывается второй.
- full_report_tab.py: unicode-escapes в строках (~346-413) — все строки записаны как \uXXXX вместо читаемого кириллического текста. Это признак проблемы с кодировкой при сохранении файла.
- main_window.py: строка 765 содержит мусор-байты ('Р'РѕСЃСЃС‚Р°РЅРѕРІР»РµРЅРѕ...') — Mojibake из-за двойного декодирования
- calculation_tab.py (117 строк): упрощённая заглушка для расчёта ветровых нагрузок, не интегрирована с основным workflow

## Архитектурные риски

- main_window.py (~4200 строк): "God object" — содержит бизнес-логику (blueprint creation, section operations, zero-station cleanup) которая должна быть в core/
- gui/data_import_wizard.py: метод _group_points_by_belts() — чистая бизнес-логика сортировки точек по поясам, находится в GUI-слое
- second_station_import_wizard.py: вычисление угла между линиями (~1440-1451 в main_window.py) выполняется inline в обработчике сигнала

**Why:** нарушение принципа разделения core/gui, затрудняет тестирование
**How to apply:** при ревью кода в main_window.py и импорт-мастерах — проверять наличие бизнес-логики в GUI

## Файлы повышенного риска

- gui/main_window.py — 4198 строк, "God object", часто нарушает separation of concerns
- gui/full_report_tab.py — 2806 строк, проблемы с кодировкой, дублирование методов
- gui/data_import_wizard.py — 2627 строк, сложный многошаговый wizard с бизнес-логикой
