---
name: UX-конвенции приложения
description: Установленные паттерны UX/UI в GeoVertical Analyzer
type: project
---

## Навигация и структура

- 5 вкладок верхнего уровня: Главная / Вертикальность башни / Прямолинейность поясов / Отчет / Полный отчет
- Главная вкладка: QSplitter 65%/35% между 3D-редактором (PointEditor3DWidget) и DataTableWidget
- DataTableWidget имеет 3 внутренние вкладки: Точки стояния / Точки башни / Секции
- Toolbar главного окна: группы через сепараторы (Проект | Импорт | Редактирование | Данные | Расчет | Экспорт | Очистка)

## Feedback и статус

- statusBar.showMessage() для коротких операций (timeout 3000-10000 мс)
- QProgressDialog для длительных операций (DataLoadThread, CalculationThread)
- QMessageBox.warning() для предупреждений, QMessageBox.critical() для ошибок
- info_label в 3D-редакторе для контекстной информации по операциям

## Кнопки тулбара

- Главный тулбар: _create_toolbar_button() — фиксированная ширина 90-130px, высота 36px, Rich Tooltips
- Редактор 3D: _create_toolbar_button() — фиксированная 85-130px, высота 56px, многострочные подписи
- ui_helpers.apply_compact_button_style() — стиль для кнопок в таблицах данных

## Темы

- Светлая/тёмная тема через QApplication.setStyleSheet()
- is_dark_theme_enabled() из gui/ui_helpers.py — проверка в диалогах
- Тема сохраняется в QSettings('GeoAnalysis', 'GeoVertical Analyzer')

## Сохранение/загрузка

- Формат проекта: .gvproj (JSON), управляется core/services/ProjectManager
- Quick Save (Ctrl+Shift+S) — сохранение по текущему пути
- Save As — новый файл
- Autosave: каждые 3 минуты, recover-диалог при запуске
- Title window: 'GeoVertical Analyzer - {project_name}' когда проект открыт

## Undo/Redo

- Ctrl+Z / Ctrl+Y (не стандартный Ctrl+Shift+Z для redo)
- Undo/Redo кнопки в тулбаре с состоянием enabled/disabled
- 50 снимков истории максимум

## Обработка ошибок в формах

- QMessageBox.warning() для предупреждений (нет данных, нет поясов)
- QMessageBox.critical() для ошибок с текстом исключения
- Inline-валидация в DataTableWidget через цвет строк
