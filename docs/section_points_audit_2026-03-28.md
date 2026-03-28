# Аудит модуля секций и точек на секциях

Дата: 2026-03-28

## Scope

Проверены ключевые точки построения, ручного редактирования, хранения и потребления секций:

- `core/section_operations.py`
- `gui/point_editor_3d.py`
- `gui/main_window.py`
- `core/undo_manager.py`
- `core/services/project_manager.py`
- `core/tower_generator.py`
- `gui/data_table.py`
- `gui/verticality_widget.py`
- `core/services/angular_verticality.py`
- `core/services/verticality_sections.py`
- `gui/tower_builder_panel.py`
- `gui/tower_builder_master.py`
- `gui/tower_properties_panel.py`
- `core/schema_exporter.py`

Прогонялись тесты:

```text
pytest tests/test_section_operations.py tests/test_section_audit_regressions.py tests/test_point_editor_3d.py tests/test_import_regressions.py tests/test_angular_verticality_payload.py tests/test_undo_manager.py -q
```

Результат: все тесты зеленые. Это не подтверждает надежность модуля, а показывает, что текущее покрытие пропускает ряд опасных сценариев.

## Executive Verdict

Модуль секций нельзя считать надежным без рефакторинга.

Основные причины:

- доменная логика секций продублирована и частично затенена в одних и тех же файлах;
- критические операции редактирования работают не через единый сервис, а через разрозненные mutating-paths;
- в системе одновременно живут две истории undo/redo;
- разные части приложения используют разные допуски по высоте и по-разному нумеруют секции;
- downstream-потребители секций не имеют единого контракта и частично реконструируют метаданные сами.

## Confirmed Findings

### P0. Дубли и затенение критических функций в ядре секций

Файл: `core/section_operations.py`

- `find_section_levels` определен дважды: строки `20` и `582`
- `add_missing_points_for_sections` определен дважды: строки `71` и `622`
- `get_section_lines` определен дважды: строки `205` и `726`

Риск:

- фактическое поведение определяется только нижними версиями;
- чтение файла вводит в заблуждение;
- любое исправление в верхней реализации не повлияет на runtime;
- высока вероятность, что часть багфиксов уже делалась “не в том месте”.

Что делать:

- удалить затененные реализации;
- оставить по одной публичной функции;
- вынести старую логику в git history, а не в рабочий код;
- после очистки заново проверить контракт каждой функции.

### P0. Дубли, мертвый код и скрытая переопределяемость в 3D-редакторе

Файл: `gui/point_editor_3d.py`

- `set_data` определен дважды: строки `1249` и `5065`
- `update_section_lines` определен дважды: строки `1799` и `4947`
- `set_structural_lines` определен дважды: строки `1855` и `5003`
- `add_section` сразу делает `return self._add_section_impl(...)` на строке `3350`, после чего в методе остается большой недостижимый блок старой реализации

Риск:

- поведение редактора невозможно безопасно сопровождать;
- часть кода выглядит “живой”, но никогда не исполняется;
- при следующем изменении почти гарантирован ошибочный patch не в активную ветку логики.

Что делать:

- удалить недостижимый код после `return`;
- убрать дубли методов;
- зафиксировать `_add_section_impl` как единственный путь ручного добавления секции;
- разделить доменную логику и визуализацию.

### P0. Критические операции редактирования секций идут в обход канонического rebuild

Файл: `gui/point_editor_3d.py`

Подтверждено:

- `project_point_to_section_level` меняет `self.data`, но не пересобирает `section_data` через `get_section_lines` (`2683+`)
- `align_section` меняет точки секции, но не делает rebuild (`2887+`)
- `delete_section` удаляет строки и вручную выкидывает одну запись из `section_data`, а не пересобирает все секции (`3073+`)

Отдельно опасно:

- `delete_section` вообще не использует `undo_transaction`;
- `project_point_to_section_level` и `delete_section` различают “исходные” и “сгенерированные” точки по имени, а не по флагу `is_section_generated`;
- regex в `project_point_to_section_level` ищет только `^S\d+_B\d+$`, то есть не покрывает составные точки вида `S..._P..._B...`.

Риск:

- после ручного редактирования секции и данные секций могут расходиться;
- в составных башнях операции могут неверно определить сгенерированные точки;
- пользователь может необратимо удалить исходные точки секции без локального undo.

Что делать:

- перевести все секционные мутации на единый сервис `SectionMutationService`;
- после любой мутации либо делать полный rebuild `section_data`, либо хранить секции как вычисляемое представление;
- отказаться от name-based эвристик там, где можно опираться на `is_section_generated`;
- добавить regression-тесты на составные секции с `_P`.

### P0. В проекте нет единого источника правды для undo/redo

Файлы:

- `core/undo_manager.py`
- `gui/point_editor_3d.py`
- `gui/main_window.py`

Факты:

- `MainWindow` использует глобальный `UndoManager`
- `PointEditor3DWidget` хранит собственные `undo_stack/redo_stack`, `capture_state`, `restore_state`, `undo_transaction`, `undo_action`, `redo_action`
- `ProjectManager` сохраняет `undo_history`, но `UndoManager.deserialize()` явно не восстанавливает `DataChangeCommand`, `RowAddCommand`, `RowDeleteCommand`, `CellEditCommand` (`core/undo_manager.py:344-363`)

Риск:

- после загрузки проекта часть истории теряется по определению;
- пользователь видит, что история “сохраняется”, но критичные команды секций фактически не подлежат восстановлению;
- глобальные и локальные действия могут откатываться по разным моделям состояния.

Что делать:

- оставить один механизм history для данных секций и точек;
- если history сохраняется в проект, она должна либо восстанавливаться целиком, либо явно не сохраняться;
- не смешивать UI-local snapshots и глобальные команды уровня документа.

### P0. Несогласованные height tolerance по всему стеку

Файлы и значения:

- `gui/main_window.py`: `self.height_tolerance = 0.1`, но секции создаются и rebuild-ятся с `0.3`
- `core/section_operations.py`: `0.3`
- `gui/data_table.py`: нумерация секций при `0.01`
- `gui/verticality_widget.py`: нумерация при `0.01`, matching местами через адаптивный tolerance
- `core/services/angular_verticality.py`: нумерация при `0.01`
- `core/tower_generator.py`: дедупликация section heights при `0.01`

Риск:

- одна и та же геометрия может давать разные секции и разные `section_num` в разных частях приложения;
- граничные секции башни и близкие уровни могут по-разному схлопываться в ядре, UI и аналитике;
- пользователь может увидеть несовпадение между 3D, таблицей секций и аналитическими отчетами.

Что делать:

- ввести единый `SectionPolicy`/`SectionConfig` с одним источником параметров;
- разделить tolerance для geometry-matching, height-clustering, UI-numbering и analytics-matching, но сделать это явно;
- запретить hardcode значений `0.3` и `0.01` вне конфигурации.

### P1. Rebuild активных секций в MainWindow завязан на хрупкую эвристику

Файл: `gui/main_window.py`

Проблемы:

- `_rebuild_active_sections_from_raw_data()` пересобирает секции только если `editor_3d.section_data` уже не пустой (`166-183`)
- используется жесткий `height_tolerance=0.3`, а не `self.height_tolerance`

Риск:

- если секции очищены ошибочно или не были восстановлены после промежуточного состояния, rebuild уже не произойдет;
- поведение экрана зависит от случайного текущего состояния списка секций, а не от raw data.

Что делать:

- rebuild должен зависеть от явного режима “секции активны”, а не от текущей непустоты списка;
- tolerance нужно брать из единой конфигурации;
- section overlay следует хранить отдельно от raw data и rebuild-ить детерминированно.

### P1. Builder-цепочка содержит явные незавершенные места и риски потери правок

Файлы:

- `gui/tower_builder_panel.py`
- `gui/tower_builder_master.py`
- `gui/tower_properties_panel.py`

Подтверждено:

- в `gui/tower_builder_panel.py:808-853` прямо описана нерешенная проблема обратной синхронизации изменений из `LatticeEditor` в `_part_lattice_specs`
- в `gui/tower_builder_panel.py:417-426` перенос lattice spec при reorder помечен как “too complex for now”
- в `gui/tower_builder_master.py:432-435` применение шаблонов профилей не реализовано, только info dialog
- в `gui/tower_properties_panel.py:831` оставлен TODO по визуализации

Риск:

- пользователь может изменить параметры решетки, а генерация башни соберет blueprint не из актуального состояния;
- reorder частей может повредить соответствие segment <-> lattice config;
- ручные правки builder-параметров и section metadata могут разойтись.

Что делать:

- завершить data flow builder -> blueprint -> geometry -> section_data;
- убрать временные side-storage-структуры, которые живут отдельно от основного blueprint;
- добавить roundtrip-тесты на reorder, редактирование lattice и генерацию.

### P1. Persistence сохраняет все как есть, но не валидирует согласованность состояния

Файл: `core/services/project_manager.py`

Проблемы:

- сериализация DataFrame восстанавливает типы очень грубо: числа через `to_numeric`, `bool` через `astype(bool)`
- миграция сравнивает версии как строки: `if version < '2.0'`
- слой сохранения не проверяет согласованность `raw_data` и `section_data`

Риск:

- при сложных колонках секций возможны тихие изменения типа;
- stale `section_data` будет сохранен и потом восстановлен как будто это валидное состояние;
- строковое сравнение версий рискованно для будущих версий вроде `10.0`.

Что делать:

- хранить schema-version и сравнивать версии семантически;
- перед save либо пересобирать `section_data`, либо сохранять checksum/metadata для проверки консистентности;
- явно тестировать поля `is_section_generated`, `tower_part_memberships`, `part_belt_assignments`, nullable bool/numeric.

### P1. Downstream-потребители секций частично дублируют доменную логику

Файлы:

- `gui/data_table.py`
- `gui/verticality_widget.py`
- `core/services/angular_verticality.py`

Подтверждено:

- в каждом из этих модулей есть собственная логика нумерации секций;
- tolerance для одинаковой высоты там `0.01`, а не доменный tolerance ядра;
- часть метаданных секции восстанавливается из `tower_part_memberships`, `tower_part`, `segment` по месту.

Риск:

- разная нумерация и разное понимание “одинаковой секции”;
- рост числа расхождений при составных башнях и ручном редактировании;
- усложнение отчетности и экспортов.

Что делать:

- вынести `section_num`, `section_key`, `part_memberships`, `section_label` в единый нормализатор;
- downstream должен потреблять уже нормализованный `section_data`, а не домысливать его заново.

## Test Coverage Audit

Что покрыто:

- базовые unit-тесты `section_operations`
- основные сценарии create/remove/undo/redo в `MainWindow`
- happy-path ручного добавления секции в `PointEditor3DWidget`
- часть composite-import сценариев
- angular verticality payload happy-path

Что не покрыто, но критично:

- `project_point_to_section_level`
- `align_section`
- `delete_section`
- `align_all_sections_to_belt` на составной башне
- `apply_section_tilt` и `apply_single_section_tilt` на boundary sections
- конфликт локального undo редактора и глобального undo окна
- восстановление истории после save/load
- roundtrip builder -> blueprint -> generated data -> section_data
- tolerance-consistency между generator/core/gui/analytics
- name-based эвристики для `S..._P..._B...`

## Исчерпывающее TO DO

### P0. Стабилизация архитектуры секций

1. Удалить дубли и мертвый код в `core/section_operations.py` и `gui/point_editor_3d.py`.
2. Зафиксировать один канонический contract для секции:
   - `height`
   - `points`
   - `belt_nums`
   - `section_num`
   - `section_name`
   - `tower_part`
   - `tower_part_memberships`
   - `is_part_boundary`
   - `segment`
3. Вынести все операции мутации секций в единый service-layer.
4. Убрать name-based классификацию generated/original points, где есть `is_section_generated`.
5. Объединить undo/redo.

### P1. Стабилизация состояния и данных

1. Ввести единый `SectionConfig` с tolerance-политикой.
2. Перевести rebuild секций на детерминированную схему.
3. Перед сохранением проекта валидировать или пересобирать `section_data`.
4. Нормализовать numbering и matching секций для UI и аналитики.
5. Завершить builder-sync по lattice/profile/segment reorder.

### P1. Тесты на реальные риски

1. Добавить regression-тесты на `project_point_to_section_level`.
2. Добавить regression-тесты на `align_section`.
3. Добавить regression-тесты на `delete_section` с проверкой undo.
4. Добавить тесты на composite names `S10_P2_B3`.
5. Добавить тесты на tolerance mismatch и numbering consistency.
6. Добавить save/load тесты на restoration of section-related metadata и history semantics.

### P2. Улучшения после стабилизации

1. Сделать `section_data` вычисляемым представлением, а не mutable cache.
2. Разделить geometry section lines и analytics section entities.
3. Убрать доменную логику из `DataTableWidget` и `VerticalityWidget`.
4. Добавить диагностический режим: compare `raw_data -> rebuilt section_data` against current cached sections.

## Recommended Execution Order

1. Очистить дубли и зафиксировать активные реализации.
2. Ввести единый доменный сервис секций.
3. Перевести все мутации редактора на этот сервис.
4. Упростить undo/redo до одного механизма.
5. Убрать tolerance-drift по стеку.
6. Дожать builder roundtrip.
7. Расширить regression suite.

## Bottom Line

Текущая проблема не в одной поломанной функции. Проблема системная: секции одновременно являются и расчетной сущностью, и UI-кэшем, и частично редактируемой структурой, и источником данных для аналитики. Пока это не сведено к одной доменной модели, баги будут возвращаться даже после локальных правок.
