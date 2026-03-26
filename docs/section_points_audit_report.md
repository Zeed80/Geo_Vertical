# Аудит логики секций и точек

## Summary

Аудит выполнен по трём слоям:

- статический разбор критических точек входа в `core.section_operations`, `gui.main_window`, `gui.point_editor_3d`, `core.undo_manager`, `core.services.project_manager`;
- прогон существующих unit-тестов по секциям и поясам;
- воспроизведение ключевых интеграционных сценариев на реальном `MainWindow`.

Базовый результат:

- существующие unit-тесты happy-path для `section_operations`, `point_editor_3d` и `belt_operations` зелёные;
- критические ошибки сосредоточены не в изолированных алгоритмах, а в синхронизации состояния между `raw_data`, `editor_3d.data`, `data_table.original_data`, `section_data`, `original_data_before_sections` и двумя системами undo/redo;
- `section_data` сейчас работает как изменяемый кэш/слепок, а не как гарантированно пересчитываемое представление;
- найдено несколько подтверждённых дефектов с воспроизведением.

## Проверенные артефакты

- `core/section_operations.py`
- `gui/main_window.py`
- `gui/point_editor_3d.py`
- `core/undo_manager.py`
- `core/services/project_manager.py`
- `gui/data_table.py`
- `tests/test_section_operations.py`
- `tests/test_point_editor_3d.py`
- `tests/test_belt_operations.py`
- `tests/test_section_audit_regressions.py`

## Track 1. Активный код и затенённые реализации

### Дубли и затенение

| Объект | Старое определение | Активное определение | Итог |
| --- | --- | --- | --- |
| `find_section_levels` | `core/section_operations.py:20` | `core/section_operations.py:582` | Активна только нижняя версия |
| `add_missing_points_for_sections` | `core/section_operations.py:71` | `core/section_operations.py:622` | Активна только нижняя версия |
| `get_section_lines` | `core/section_operations.py:205` | `core/section_operations.py:725` | Активна только нижняя версия |
| `PointEditor3DWidget.update_section_lines` | `gui/point_editor_3d.py:1799` | `gui/point_editor_3d.py:4946` | Активна только нижняя версия |
| `PointEditor3DWidget.set_data` | `gui/point_editor_3d.py:1249` | `gui/point_editor_3d.py:5064` | Активна только нижняя версия |

### Мёртвый код

В `gui/point_editor_3d.py:3343` метод `add_section()` немедленно делает `return self._add_section_impl(...)`, после чего внутри файла остаётся большой блок старой реализации, который никогда не исполняется.

### Вывод

- фактическое поведение нельзя понимать по первым определениям;
- поддержка и аудит усложнены, потому что в файле одновременно лежат старая и новая логика;
- любое локальное исправление в верхней версии функций/методов не изменит реальное поведение приложения.

## Track 2. Инварианты секций

Ниже инварианты, которые должны выполняться после любой операции, меняющей точки или секции.

| Инвариант | Описание | Статус по аудиту |
| --- | --- | --- |
| `I1` | `section_data` соответствует текущему набору точек | Нарушается |
| `I2` | после отмены операции состояние секций возвращается вместе с данными | Нарушается |
| `I3` | удаление всех секций не должно затирать последующие правки исходных точек | Нарушается |
| `I4` | редактирование через таблицу и через 3D должно синхронно обновлять `raw_data` и `section_data` | Нарушается |
| `I5` | сохранённый проект не должен фиксировать устаревший `section_data` | Нарушается при сохранении stale state |
| `I6` | `point_index` должен оставаться стабильным в операциях добавления/пересборки секций | В основном соблюдается |
| `I7` | одна секция на высоту в рамках tolerance | Соблюдается в active `get_section_lines()` |
| `I8` | не более одной точки секции на пояс/часть | Соблюдается в active `get_section_lines()` |

## Interfaces And State Map

### Карта мутаций секций

| Точка входа | Вход | Что меняет | Источник истины после операции | Пересборка `section_data` |
| --- | --- | --- | --- | --- |
| `find_section_levels` | `data`, `height_tolerance` | ничего | `data` | не применимо |
| `add_missing_points_for_sections` | `data`, `section_levels` | новый DataFrame | возвращаемый DataFrame | не применимо |
| `get_section_lines` | `data`, `section_levels` | ничего | `data` | строит новое `section_data` |
| `MainWindow.create_sections` | `raw_data` | `raw_data`, `editor_3d.data`, `original_data_before_sections`, `editor_3d.section_data`, undo stack | `raw_data` + отдельный `section_data` | да, через `get_section_lines()` |
| `MainWindow.remove_sections` | `original_data_before_sections` | `raw_data`, `editor_3d.data`, `editor_3d.section_data`, undo stack | snapshot `original_data_before_sections` | нет, просто очищает |
| `MainWindow.on_3d_data_changed` | `editor_3d.data` | `raw_data`, `data_table.original_data`, analysis widgets | `editor_3d.data`/`raw_data` | нет |
| `MainWindow.on_table_data_changed` | `data_table.original_data` | `raw_data`, `editor_3d.data`, analysis widgets | `data_table.original_data`/`raw_data` | нет |
| `PointEditor3DWidget._add_section_impl` | `section_height`, `tower_part`, `placement` | `editor_3d.data`, `editor_3d.section_data`, local undo stack | `editor_3d.data` | да, через `get_section_lines()` |
| `PointEditor3DWidget.delete_section` | `section_height` | `editor_3d.data`, `editor_3d.section_data` | `editor_3d.data` | частично, только удаляет выбранную секцию из списка |
| `PointEditor3DWidget.edit_selected_point` | редактируемая точка | `editor_3d.data`, local undo stack | `editor_3d.data` | нет |
| `PointEditor3DWidget.delete_selected_points` | выбранные точки | `editor_3d.data`, local undo stack | `editor_3d.data` | нет |
| `PointEditor3DWidget.project_point_to_section_level` | точка + высота секции | `editor_3d.data`, local undo stack | `editor_3d.data` | нет |
| `PointEditor3DWidget.align_section` | высота секции | `editor_3d.data`, local undo stack | `editor_3d.data` | нет |
| `PointEditor3DWidget.align_all_sections_to_belt` | пояс | `editor_3d.data`, `editor_3d.section_data`, local undo stack | `editor_3d.data` | да, через `get_section_lines()` |
| `PointEditor3DWidget.shift_tower_height` | `offset` | `editor_3d.data`, `editor_3d.section_data` | `editor_3d.data` | нет полного rebuild, только in-place shift секций |
| `PointEditor3DWidget.apply_section_tilt` | секция + target offset | `editor_3d.data`, `editor_3d.section_data` | `editor_3d.data` | да, через `find_section_levels()` + `get_section_lines()` |
| `PointEditor3DWidget.apply_single_section_tilt` | секция + target offset | `editor_3d.data`, `editor_3d.section_data` | `editor_3d.data` | да, через `find_section_levels()` + `get_section_lines()` |
| `PointEditor3DWidget.capture_state/restore_state` | локальный snapshot | `editor_3d.data`, `editor_3d.section_data`, local undo stack | snapshot в редакторе | восстанавливает snapshot напрямую |
| `DataChangeCommand` | `old_data`, `new_data`, setter | только данные, которые знает setter | внешний setter | не умеет работать с `section_data` сам по себе |
| `ProjectManager.save_project/load_project` | `raw_data`, `section_data`, snapshot | сериализует/восстанавливает проект | файл проекта | не пересчитывает, сохраняет как есть |

## Track 3. Создание и пересоздание секций

### Что работает

- `MainWindow.create_sections()` корректно вызывает active trio `find_section_levels() -> add_missing_points_for_sections() -> get_section_lines()`;
- `PointEditor3DWidget._add_section_impl()` после ручного добавления секции делает rebuild `section_data`;
- `get_section_lines()` в active версии удаляет дубликаты по `(tower_part, belt)` и строит секции в трековом режиме.

### Основная проблема

`create_sections()` создаёт `section_data` отдельно от `DataChangeCommand`. Undo/redo верхнего уровня знает только о замене `raw_data`, но не о состоянии `section_data`. Из-за этого после undo/redo секции могут визуально и логически остаться от предыдущего состояния.

Подтверждённый сценарий:

- импорт/загрузка данных;
- `create_sections()`;
- `undo()`;
- `raw_data` вернулось, а `editor_3d.section_data` осталось заполненным.

Причина:

- `DataChangeCommand` оперирует только DataFrame;
- `MainWindow.undo()` повторно вызывает `set_section_lines(self.editor_3d.section_data)`, даже если `section_data` уже stale.

## Track 4. Ручные операции с секциями

### Операции с rebuild

Эти пути явно пересобирают секции:

- `_add_section_impl()` — `gui/point_editor_3d.py:3712`
- `align_all_sections_to_belt()` — `gui/point_editor_3d.py:5738`
- `apply_section_tilt()` — `gui/point_editor_3d.py:6373`
- `apply_single_section_tilt()` — `gui/point_editor_3d.py:6473`

### Операции без rebuild

Эти пути меняют данные, но не пересчитывают `section_data`:

- `align_section()` — только `data_changed.emit()` и `update_all_indices()`, без `get_section_lines()`
- `project_point_to_section_level()` — меняет координаты точки, но не rebuild секции
- `delete_section()` — вручную удаляет только одну запись из `section_data`, а не строит заново всю структуру

### Вывод

Ручные секционные операции разделены на две группы:

- часть опирается на полную пересборку и относительно безопасна;
- часть изменяет только точки и надеется на внешнюю синхронизацию, которая сейчас не пересобирает секции.

## Track 5. Операции с точками, влияющие на секции

### Подтверждённо проблемные точки

- `edit_selected_point()` — `gui/point_editor_3d.py:2114`
- `delete_selected_points()` — `gui/point_editor_3d.py:2189`
- `MainWindow.on_3d_data_changed()` — `gui/main_window.py:2691`
- `MainWindow.on_table_data_changed()` — `gui/main_window.py:2722`

Во всех этих цепочках данные точек меняются, но rebuild `section_data` не выполняется.

### Последствия

- секции визуально остаются на старых высотах;
- таблица секций продолжает показывать устаревшие центры и состав;
- аналитические виджеты получают новые точки, но продолжают опираться на старый `section_data`;
- сохранение проекта может зафиксировать логически несовместимые `raw_data` и `section_data`.

## Track 6. Undo/Redo

### Найденная архитектура

Есть два разных механизма:

- верхний `UndoManager` в `MainWindow`, работающий через `DataChangeCommand` и другие команды;
- локальный стек `undo_stack/redo_stack` внутри `PointEditor3DWidget`, который сериализует и `data`, и `section_data`.

### Почему это опасно

- верхний undo знает только о `raw_data`, но не о `section_data`;
- локальный undo знает о `section_data`, но не синхронизирован с `MainWindow.undo_manager`;
- пользователь может смешивать верхнеуровневые команды и локальные 3D-операции в одной сессии.

### Подтверждённый дефект

`undo(create_sections)` оставляет stale `section_data`.

### Дополнительный риск

Любая команда секций, выполненная через `MainWindow`, а затем продолженная локальными правками в 3D, создаёт разные источники истины для history stack.

## Track 7. Сохранение, загрузка, автосохранение

### Что работает

- `ProjectManager.save_project()` и `ProjectManager.load_project()` сохраняют и восстанавливают `raw_data`, `section_data`, `original_data_before_sections`;
- то же верно для `save_autosave()`.

### Что не работает концептуально

Слой persistence не валидирует, согласован ли `section_data` с `raw_data`. Он сохраняет текущее значение как есть.

Следствие:

- если `section_data` устарел до сохранения, stale state будет восстановлен после `load_project()` и `autosave recovery`;
- это не баг сериализации, а следствие сохранения кэша секций без обязательной пересборки перед save.

## Track 8. Таблица и аналитические виджеты

### Таблица секций

`DataTableWidget.update_sections_table()` берёт `section_data` напрямую из `editor_3d.section_data`. Значит таблица секций полностью зависит от того, насколько этот список актуален.

### Аналитические виджеты

`verticality_widget` и `straightness_widget` получают новые `raw_data`, но цепочка их обновления не исправляет stale `section_data`. Поэтому таблица и анализ могут расходиться.

## Confirmed Defects

### Critical

1. `undo(create_sections)` не очищает `section_data`

- Сценарий: `create_sections()` -> `undo()`
- Факт: `raw_data` откатывается, секции остаются
- Подтверждение: воспроизведено интеграционно, зафиксировано в `tests/test_section_audit_regressions.py`
- Корень: `DataChangeCommand` не знает о `section_data`, а `MainWindow.undo()` повторно активирует stale список
- Статус: исправлено, закреплено regression-тестом

2. `remove_sections()` затирает все правки точек, сделанные после создания секций

- Сценарий: `create_sections()` -> изменение точки -> `remove_sections()`
- Факт: приложение возвращает snapshot `original_data_before_sections`, теряя последующие правки
- Подтверждение: воспроизведено интеграционно
- Корень: `remove_sections()` использует полный snapshot rollback вместо удаления только секционных артефактов
- Статус: исправлено, закреплено regression-тестом

### High

3. Изменения через таблицу не перестраивают `section_data`

- Сценарий: `create_sections()` -> изменить высоты в таблице -> `on_table_data_changed()`
- Факт: `raw_data` уже новый, `section_data` остаётся старым
- Подтверждение: воспроизведено интеграционно
- Корень: в `on_table_data_changed()` нет invalidation/rebuild секций
- Статус: исправлено, закреплено regression-тестом

4. Изменения через 3D не перестраивают `section_data`

- Сценарий: `create_sections()` -> изменить точки в `editor_3d.data` -> `on_3d_data_changed()`
- Факт: `raw_data` и таблица синхронизируются, `section_data` остаётся старым
- Подтверждение: воспроизведено интеграционно
- Корень: в `on_3d_data_changed()` нет invalidation/rebuild секций
- Статус: исправлено, закреплено regression-тестом

5. Локальные операции над точками и отдельной секцией не вызывают rebuild

- Затронутые пути: `edit_selected_point()`, `delete_selected_points()`, `project_point_to_section_level()`, `align_section()`
- Факт: метод меняет точки, но оставляет секции в старом виде
- Подтверждение: статический аудит кода; опора на проблемный sync path

### Medium

6. Дубли и shadowed-реализации затрудняют поддержку и повышают риск ложных исправлений

- Подтверждение: `core/section_operations.py`, `gui/point_editor_3d.py`

7. Stale `section_data` сохраняется в проект и автосохранение без валидации

- Подтверждение: путь `save_project()/save_autosave()` сериализует список как есть

## Scenario Matrix

| Сценарий | Статус | Комментарий |
| --- | --- | --- |
| Импорт -> создание секций -> повторное создание секций без очистки | Частично покрыт статикой | Явного подтверждённого сбоя не зафиксировано, но сценарий нужен в manual QA |
| Создание секций -> удаление одной секции -> undo -> redo | Риск | Локальный undo хранит `section_data`, но интеграционного теста пока нет |
| Создание секций -> удаление всех секций -> undo -> redo | Подтверждённый дефект | Undo оставляет stale `section_data` |
| Создание секций -> добавление новой секции сверху/снизу/по абсолютной высоте | Базово покрыт | `_add_section_impl()` пересобирает секции, unit-тест уже есть |
| Создание секций -> редактирование точки на секции без смены высоты | Подтверждённый дефект по цепочке | Нет rebuild секций после редактирования точки |
| Создание секций -> редактирование точки с изменением высоты/пояса/части | Подтверждённый дефект | Секции устаревают сильнее всего |
| Создание секций -> удаление одной точки секции | High risk | `delete_selected_points()` не rebuild секции |
| Создание секций -> удаление не-секционной точки | Вероятно нормально | Но отдельного теста нет |
| Создание секций -> выравнивание одной секции | High risk | `align_section()` не rebuild секции |
| Создание секций -> выравнивание всех секций по выбранному поясу | Статически выглядит корректно | Есть явный rebuild через `get_section_lines()` |
| Создание секций -> смещение всей башни по высоте | Вероятно нормально | Секции сдвигаются in-place вместе с данными |
| Создание секций -> глобальный крен по секциям | Статически выглядит корректно | Есть полный rebuild |
| Создание секций -> локальный крен одной секции | Статически выглядит корректно | Есть полный rebuild |
| Любой сценарий -> save/load | Работает как сохранение текущего слепка | Если слепок stale, после загрузки он останется stale |
| Любой сценарий -> autosave/recovery | Работает как сохранение текущего слепка | Та же проблема stale state |
| Редактирование через таблицу | Подтверждённый дефект | `section_data` не инвалидируется |
| Редактирование через 3D | Подтверждённый дефект | `section_data` не инвалидируется |
| Несколько `tower_part`, граничные секции, неполные пояса | Частично покрыт статикой | active `get_section_lines()` учитывает memberships, но интеграционных сценариев пока нет |

## Матрица тестового покрытия

### Что уже было покрыто до аудита

| Тестовый файл | Что покрывает | Ограничение |
| --- | --- | --- |
| `tests/test_section_operations.py` | алгоритмы `find_section_levels`, `add_missing_points_for_sections`, `get_section_lines` | нет `MainWindow`, нет sync между слоями |
| `tests/test_point_editor_3d.py` | `_add_section_impl`, вспомогательные методы редактора | нет интеграции с `MainWindow` и persistence |
| `tests/test_belt_operations.py` | поясные операции | не касается жизненного цикла `section_data` |

### Что добавлено в этом аудите

| Тестовый файл | Тип | Статус |
| --- | --- | --- |
| `tests/test_section_audit_regressions.py::test_main_window_create_and_remove_sections_roundtrip` | baseline integration | должен проходить |
| `tests/test_section_audit_regressions.py::test_undo_create_sections_should_clear_section_data` | regression | проходит после исправления |
| `tests/test_section_audit_regressions.py::test_remove_sections_should_preserve_post_creation_point_edits` | regression | проходит после исправления |
| `tests/test_section_audit_regressions.py::test_on_table_data_changed_should_rebuild_section_data` | regression | проходит после исправления |
| `tests/test_section_audit_regressions.py::test_on_3d_data_changed_should_rebuild_section_data` | regression | проходит после исправления |
| `tests/test_section_audit_regressions.py::test_project_manager_roundtrip_preserves_section_data_and_snapshot` | persistence | должен проходить |
| `tests/test_section_audit_regressions.py::test_project_manager_autosave_preserves_section_data` | persistence | должен проходить |

## Архитектурные причины проблем

1. `section_data` хранится как mutable cache, а не как строго производное представление.
2. Источник истины раздвоен между `raw_data`, `editor_3d.data`, `data_table.original_data`.
3. Undo/redo раздвоен между `MainWindow` и `PointEditor3DWidget`.
4. `remove_sections()` решает задачу через полный snapshot rollback, а не через целевое удаление секционных изменений.
5. Сохранение проекта сериализует stale cache без валидации.
6. В кодовой базе одновременно присутствуют старые и активные реализации одних и тех же операций.

## Обязательные регрессионные тесты на следующий этап исправления

- Интеграционный тест на `create_sections()` -> `undo()` -> `redo()` с проверкой и `raw_data`, и `section_data`.
- Интеграционный тест на `remove_sections()` после ручного редактирования существующей точки.
- Тесты на `edit_selected_point()`, `delete_selected_points()`, `project_point_to_section_level()`, `align_section()` с обязательной проверкой rebuild/invalidation секций.
- Тесты на save/load после stale-prone операций.
- Тесты на multi-part tower и boundary sections.
- Тесты на повторный запуск `create_sections()` поверх уже созданных секций.

## Итог

Главная проблема текущей реализации не в одном ошибочном алгоритме построения секций, а в архитектуре жизненного цикла `section_data`.

Пока `section_data` не станет единообразно:

- либо полностью производным от `data`,
- либо обновляемым через единый mutation layer,

ошибки будут повторяться в undo/redo, таблице, 3D-редакторе и persistence даже при локальных исправлениях отдельных методов.
