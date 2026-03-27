# Аудит расчета вертикальности и прямолинейности

Дата фиксации: 2026-03-25

## Цель

Зафиксировать единый аудиторский контур для всей цепочки расчета вертикальности и прямолинейности:

`импорт -> регистрация съемки -> группировка точек -> секции/пояса -> математика -> нормативы -> таблицы -> графики -> PDF/DOCX/Full Report`.

Этот проход аудита включает:

- baseline тестов и известных предупреждений окружения;
- карту источников истины и точек расхождения;
- перечень дефектов и архитектурных рисков;
- быстрые исправления, выполненные в этом проходе;
- каталог эталонных сценариев и пробелов покрытия.

## Baseline на момент аудита

Успешно пройдены:

- `pytest tests\test_calculations.py tests\test_straightness_calculations.py tests\test_angular_verticality_payload.py -q`
- `pytest tests\test_import_regressions.py -q`

Дополнительно добавлены и пройдены регрессии:

- `pytest tests\test_report_template_verticality_traceability.py -q`
- `pytest tests\test_audit_phase2_regressions.py -q`

Зафиксированные риски baseline:

- `pandas FutureWarning` в ветках с `fillna(False).astype(bool)` и `pd.concat(...)` с пустыми или all-NA блоками.
- `pytest-cov` в текущем окружении не воспроизводится: при запуске с coverage падает импорт `SciPy` с ошибкой `generic_type: type "ObjSense" is already registered!`.

## Что исправлено в этом проходе

Исправлен разрыв источника истины для полного отчета.

До изменения `ReportDataAssembler` в `core/services/report_templates.py` строил:

- `geodesic_results`
- `vertical_deviation_table`

только по `processed["centers"]`, даже если UI и angular journal уже использовали canonical section payload из `angular_verticality`.

После изменения сборщик отчета:

- сначала использует canonical sections из `angular_measurements["sections"]`;
- затем fallback на `processed["angular_verticality"]["sections"]`;
- только при отсутствии этих данных возвращается к `centers`.

Это убирает ключевое расхождение между UI, angular journal и full report template.

## Что исправлено во второй фазе

1. Удалены затененные дубли определений в `core/calculations.py`:
   - `group_points_by_height`
   - `_get_cache_key`
   - `calculate_straightness_deviation`

2. Убрана продуктовая ветка `FutureWarning` в `gui/data_table.py` для `is_part_boundary`.

3. Добавлены synthetic-regressions на critical invariants:
   - идеальная башня без крена и прогиба;
   - локальный прогиб поясов без смещения оси;
   - исключение station/control/auxiliary-точек из рабочего контура;
   - составная башня с общей граничной секцией;
   - контроль отсутствия дублированных определений в расчетном модуле.

## Карта трассировки данных

### 1. Импорт и регистрация

Основные входы:

- `core/data_loader.py`
- `core/trimble_loader.py`
- `core/import_grouping.py`
- `core/multi_station_import.py`
- `core/survey_registration.py`
- `core/second_station_matching.py`

Что проверять:

- формат исходника `CSV/JXL/JOB`;
- pairing основного и дополнительного экспорта;
- сохранение `point_index`, `belt`, `tower_part`, `is_station`, `is_control`, `is_auxiliary`, `is_part_boundary`;
- воспроизводимость transformation audit после второй станции.

### 2. Формирование секций и поясов

Основные узлы:

- `core/section_operations.py`
- `core/calculations.py::group_points_by_height`
- `gui/data_table.py` section matching и canonical `sections`

Что проверять:

- непрерывность секций и частей;
- split-height и общие граничные секции;
- исключение служебных точек из рабочего контура;
- устойчивость к неотсортированным и неполным данным.

### 3. Ядро вертикальности

Основные узлы:

- `core/calculations.py::process_tower_data`
- `core/calculations.py::approximate_tower_axis`
- `core/calculations.py::calculate_vertical_deviation_with_local_cs`
- `gui/data_table.py::_build_angular_verticality_payload`
- `gui/data_table.py::_build_sections_from_axis_payload`
- `gui/data_table.py::_merge_station_sections_with_fallback`

Что проверять:

- переход от центров поясов к оси и локальной СК;
- знаки `deviation_x/deviation_y`;
- суммарное отклонение `total_deviation`;
- режимы `stations`, `processed`, `processed_fallback`, `stations_partial`;
- актуальность payload после редактирования таблицы и 3D.

### 4. Ядро прямолинейности

Основные узлы:

- `core/straightness_calculations.py`
- `core/services/calculation_service.py`
- `gui/straightness_widget.py`

Что проверять:

- трехточечную локальную схему по поясам;
- знак стрелы прогиба;
- part-wise tolerance;
- исключение station/control/auxiliary-точек;
- согласование `straightness_profiles` и `straightness_summary`.

### 5. Нормативный слой

Основные узлы:

- `core/normatives.py`
- `core/services/calculation_service.py::_check_verticality_normatives`
- `core/services/calculation_service.py::_check_straightness_normatives`
- `gui/data_table.py::_build_verticality_check_from_sections`

Что проверять:

- `0.001H` для башен;
- коэффициенты для `tower/mast/odn`;
- `L/750` для прямолинейности;
- отсутствие смешения verticality и straightness в сводках.

### 6. Представление и отчеты

Основные узлы:

- `gui/verticality_widget.py`
- `gui/straightness_widget.py`
- `gui/plots_widget.py`
- `gui/report_widget.py`
- `utils/report_generator_enhanced.py`
- `core/services/report_templates.py`

Что проверять:

- одинаковые числа в таблицах, графиках и отчетах;
- допустимы только различия округления;
- canonical angular sections должны быть единым источником, если они доступны;
- графики не должны повторно масштабировать м/мм и углы/секунды.

## Найденные дефекты и риски

### Высокий приоритет

1. Full report template раньше строился по `centers`, а не по canonical angular sections.
   Статус: исправлено в этом проходе.
   Риск: различие между UI, journal и итоговым отчетом по тем же данным.

2. В `core/calculations.py` присутствуют дублированные определения функций.
   Примеры: `calculate_straightness_deviation`, `_get_cache_key`.
   Статус: закрыт во второй фазе.
   Риск: снят, модуль больше не содержит затененных duplicates по этим entrypoints.

### Средний приоритет

1. В `gui/straightness_widget.py::_calculate_belt_deflections` есть недостижимая legacy-ветка после раннего `return`.
   Статус: открыт.
   Риск: сопровождение и ложное ощущение активного fallback-кода.

2. В проекте сосуществуют два отчетных стека:
   - `core/services/report_templates.py`
   - `utils/report_generator_enhanced.py`
   Статус: открыт.
   Риск: одна логика уже перешла на canonical sections, вторая могла отставать.

3. Coverage-прогон нестабилен из-за конфликта `pytest-cov` и импорта `SciPy`.
   Статус: открыт.
   Риск: нельзя надежно измерять покрытие и видеть дыры в аудите.

4. `pandas FutureWarning` указывает на возможное изменение поведения в будущих версиях.
   Статус: частично закрыт.
   Риск: предупреждение по `is_part_boundary` в продуктовой ветке устранено; остаются test-only предупреждения вокруг `pd.concat(...)` с пустыми/all-NA блоками.

### Низкий приоритет

1. В нескольких местах расчеты и представление все еще завязаны на private methods вместо единого публичного контракта данных.
   Статус: открыт.
   Риск: локальные исправления сложнее масштабировать на все представления.

## Матрица статуса по этапам аудита

| Этап | Статус | Комментарий |
| --- | --- | --- |
| Нормативно-методическая матрица | Выполнено | См. `docs/verticality_straightness_formula_matrix.md` |
| Аудит импорта и предобработки | Частично | Зафиксированы ключевые узлы и риски pairing/flags/split-height |
| Аудит единиц и CRS | Частично | Выделены точки m/mm и deg/sec/rad, нужен отдельный прогон по EPSG-кейсам |
| Ядро вертикальности | Частично | Основная трассировка собрана, найден и устранен report mismatch |
| Угловая вертикальность | Частично | Canonical payload и merge paths описаны, нужны отдельные manual datasets |
| Ядро прямолинейности | Частично | Реальные регрессии есть, архитектурные замечания зафиксированы |
| Согласованность математика/UI/отчет | Частично | Закрыт один критичный разрыв, остаются mixed-report paths |
| Аудит графиков | В очереди | Нужен скриншотный/figure-level прогон по сценариям |
| Заключения и сводки | Частично | Проверено разделение verticality vs straightness в service layer |
| Численная устойчивость | Частично | Граничные случаи перечислены, покрытие пока неполное |
| Тестовое покрытие | Частично | Добавлены регрессии на report traceability и synthetic audit scenarios |
| Производственный след | Частично | import diagnostics and transformation audit уже подключены, нужна унификация логов |

## Быстрые исправления следующего прохода

1. Вынести единый публичный helper для verticality sections, чтобы UI/report/service не собирали схему независимо.
2. Закрыть оставшиеся `pandas FutureWarning` в test/import ветках с `pd.concat`.
3. Очистить dead code в `gui/straightness_widget.py`.
4. Добавить figure-level проверки на подписи осей, нулевую линию и значения plotted points.
5. Добавить synthetic authoritative-cases для двух реальных станций и edge-tolerance verdicts.

## Архитектурные риски

1. Canonical payload вертикальности пока формируется в GUI-слое (`gui/data_table.py`), а не в чистом сервисе.
2. Full report и enhanced report имеют пересекающиеся, но не полностью одинаковые маршруты получения данных.
3. Часть вычислительных контрактов существует фактически, но не оформлена как типизированная схема результата.

## Критерии завершения полного аудита

Аудит можно считать завершенным только если:

- для каждой итоговой метрики указан ровно один источник истины;
- для каждой метрики есть формула, единицы и норматив;
- для каждого результата в UI и отчете есть ручная проверка или автотест;
- графики, таблицы и отчеты расходятся только по явно описанному округлению;
- coverage-прогон воспроизводим и показывает реальное покрытие critical path.

## Phase 3 Update

Completed in this pass:

- Closed the remaining test-side `pd.concat(...)` warning path in `tests/test_angular_verticality_payload.py` with a schema-aware helper that preserves stable `point_index`.
- Added figure-level regressions in `tests/test_plot_audit_regressions.py` for verticality and straightness plots: zero line, tolerance envelope/limits, axis labels, titles, and plotted coordinates.
- Hardened `gui/data_table.py` so station-table rendering falls back to positional `point_index` when the source value is empty or non-numeric.
- Fixed user-facing straightness plot strings in `gui/straightness_widget.py` for the covered rendering path: axis labels, title, tolerance legend, empty-state text, and profile label.

Residual risk from this phase:

- `gui/straightness_widget.py` still contains mojibake in comments, docstrings, and non-covered legacy text branches; the audited `_render_straightness_plot(...)` path is now normalized and regression-tested.

## Phase 4 Update

Completed in this pass:

- Hardened `gui/verticality_widget.py` so report/preview consumers read canonical section payload from `_current_section_data` instead of re-parsing scaled table text.
- Isolated `core/calculations.py::process_tower_data(...)` cache entries and cache hits with deep copies so UI-side mutations can no longer contaminate future calculation results.
- Fixed verticality plot bounds so the tolerance envelope always fits inside the axis limits, even when actual deviations are much smaller than the allowed top deviation.
- Replaced the widget-level `tight_layout(...)` call with stable manual subplot spacing to avoid the known Matplotlib warning on the narrow on-screen figure.

Confirmed defects now covered by regressions:

1. UI/report mismatch risk: `VerticalityWidget.get_table_data()` could previously return rounded/scaled display values instead of the raw section payload.
2. Cache contamination risk: `DataTableWidget.set_processed_results(...)` could augment the returned calculations dict and leak that mutation back into the `process_tower_data(...)` cache.
3. Plot clipping risk: verticality tolerance guide lines could be drawn outside the visible x-range.
4. Layout warning risk: repeated plot refreshes could emit `Tight layout not applied` warnings during the audited rendering path.

Targeted regression coverage added:

- `tests/test_calculations.py`
- `tests/test_angular_verticality_payload.py`
- `tests/test_plot_audit_regressions.py`

Residual risk after this phase:

- Canonical angular verticality sections are still assembled in the GUI layer (`gui/data_table.py`), so the final source-of-truth is protected but not yet fully centralized in a service/core contract.
- `gui/report_widget.py`, `gui/report_preview_dialog.py`, and `utils/report_generator_enhanced.py` still depend on widget-provided accessors; they are now numerically safer, but the architectural duplication remains.

## Phase 5 Update

Completed in this pass:

- Added `core/services/verticality_sections.py` as the shared contract layer for verticality section normalization, fallback selection, angular aggregation, and normative checks.
- Switched `CalculationService`, `ReportDataAssembler`, `ReportWidget`, `VerticalityWidget`, and `EnhancedReportGenerator` to the shared helper instead of maintaining separate section-selection logic.
- Removed one more GUI-side recomputation path in `VerticalityWidget`: when canonical sections already exist in `angular_verticality`, the widget now consumes them directly instead of rebuilding equivalent rows again.

Confirmed contract after this phase:

1. `angular_verticality["sections"]` is the preferred source-of-truth whenever it exists.
2. Widget table rows are no longer allowed to outrank canonical payloads.
3. Verticality normative verdicts in service/report layers now inherit `section_num` and `part_num` from the same normalized section contract.

Residual risk after this phase:

- The producer of canonical sections is still `gui/data_table.py`; consumers are now unified, but producer logic is not yet moved out of the GUI layer.
- `utils/report_generator_enhanced.py` and `gui/report_preview_dialog.py` still contain presentation-specific fallback scaffolding, even though their numeric source now resolves through the shared helper or raw widget payload.

## Phase 6 Update

Completed in this pass:

- Added `core/services/angular_verticality.py` and moved the canonical `angular_verticality` producer out of local GUI recomputation into a dedicated service builder consumed by `DataTableWidget`.
- Added `core/services/straightness_profiles.py` as the shared selector/normalizer for `straightness_profiles` and part-grouped straightness payloads.
- Switched `StraightnessWidget.get_all_belts_data()`, `ReportWidget.generate_preview_html(...)`, `ReportPreviewDialog.generate_preview_html(...)`, and `EnhancedReportGenerator` straightness selection to the shared helper with priority `processed_data["straightness_profiles"] -> widget payload -> canonical raw-data rebuild`.
- Switched `EnhancedReportGenerator` verticality selection to the shared `get_preferred_verticality_sections(...)` path so processed canonical sections outrank widget-only fallback payloads in PDF/DOCX generation too.
- Added regressions covering the new straightness service helper and the processed-profile priority in report preview HTML.

Confirmed contract after this phase:

1. Canonical `angular_verticality` payload is now produced in `core/services/angular_verticality.py` and only orchestrated from `gui/data_table.py`.
2. Straightness preview/report tables now resolve from the same numeric source-of-truth as `straightness_profiles`.
3. Full suite verification passed after the refactor, so the new source-selection helpers are not only locally correct but also compatible with the surrounding import/report flows.

Residual risk after this phase:

- `gui/straightness_widget.py` still contains legacy fallback code paths and mojibake text outside the audited/covered execution path; numerically they are now bypassed by the canonical helper, but cleanup is still desirable.
- `utils/report_generator_enhanced.py` still has duplicated presentation structure between PDF and DOCX branches; source selection is unified, layout generation is not.
- The geodesic result contract is still structural rather than fully typed; a typed schema/dataclass layer would make future regressions cheaper to catch.
