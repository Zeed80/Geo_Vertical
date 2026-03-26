# Матрица формул и нормативов для вертикальности и прямолинейности

Дата фиксации: 2026-03-25

## Единицы и правила пересчета

| Объект | Внутреннее представление | Отображение |
| --- | --- | --- |
| Координаты `x/y/z` | метры | метры |
| Вертикальность по `centers` | метры | чаще мм |
| Canonical section deviations | мм | мм |
| Углы визирования | градусы/секунды дуги | секунды дуги и форматированная строка |
| Прямолинейность по профилям | мм | мм |

Критические точки пересчета:

- `m -> mm`: умножение на `1000`
- `arcsec -> deg`: деление на `3600`
- `deg -> rad`: `math.radians(...)` или эквивалент через `sin(delta_sec / 3600°)`

## Формульная матрица

| Метрика | Формула/логика | Единицы | Норматив/допуск | Основной код | Основные потребители |
| --- | --- | --- | --- | --- | --- |
| Центр пояса/секции | среднее по рабочим точкам группы высот | м | нет | `core/calculations.py::group_points_by_height`, расчет центров в `process_tower_data` | verticality, straightness, UI |
| Аппроксимация оси башни | линейная ось по центрам `x(z), y(z)` | м | нет | `core/calculations.py::approximate_tower_axis` | verticality |
| Локальные отклонения по осям | проекция смещения центра на локальные оси X/Y | м в ядре, мм в payload/report | далее проверяются суммарно | `calculate_vertical_deviation_with_local_cs`, `gui/data_table.py::_build_axis_based_sections_from_centers` | verticality widget, reports |
| Суммарное отклонение от вертикали | `sqrt(dx^2 + dy^2)` | м в ядре, мм в canonical sections | `k * H` | `core/calculations.py`, `gui/data_table.py` | service layer, UI, report |
| Угловое расхождение `delta_sec` | нормализованная разность фактического и опорного направления | сек. дуги | нет | `gui/data_table.py::_normalized_angle_diff` | angular journal |
| Линейное отклонение из угла | `delta_mm = sin(delta_sec / 3600 deg) * D * 1000` | мм | далее участвует в verticality | `gui/data_table.py::_synchronize_axis_rows_with_sections` и строковая логика angular payload | angular journal, report |
| Базовая секция для authoritative stations | нижняя секция части задает baseline | мм | норматив применяется выше базовой | `gui/data_table.py::_build_sections_from_axis_payload`, `_merge_station_sections_with_fallback` | verticality sections |
| Vertical tolerance для башни | `0.001 * H` | м в нормативном ядре, мм в UI/report | СП 70.13330.2012 | `core/normatives.py::get_vertical_tolerance` | service, UI, report |
| Vertical tolerance для мачты | `0.0007 * H` | м | прикладная логика проекта | `core/normatives.py::get_vertical_tolerance` | service, UI |
| Vertical tolerance для ODN | `0.005 * H` | м | прикладная логика проекта | `core/normatives.py::get_vertical_tolerance` | service, UI |
| Норматив verticality check | сравнение отклонения каждой секции с допуском по высоте | м/мм | passed/failed | `core/services/calculation_service.py::_check_verticality_normatives`, `gui/data_table.py::_build_verticality_check_from_sections` | report/widget conclusions |
| Локальная прямолинейность пояса | трехточечная схема на соседних точках/участках пояса | мм | `L/750` | `core/straightness_calculations.py::calculate_belt_deflections` | straightness widget/report |
| Допуск прямолинейности | `section_length_mm / 750` | мм | `L/750` | `core/straightness_calculations.py::get_straightness_tolerance` | straightness summary/report |
| Summary по прямолинейности | максимум по `straightness_profiles` | мм | через violations | `build_straightness_profiles`, `straightness_summary` | service/report |
| Summary по verticality для full report | максимум/среднее по canonical sections, fallback на centers | мм | справочный итог | `core/services/report_templates.py` | full report |

## Где возможны риски единиц

1. `centers["deviation"]` живет в метрах, но report/UI часто работают в мм.
2. Canonical `angular_verticality["sections"]` уже хранит отклонения в мм.
3. При построении графиков важно не делить и не умножать значения повторно.
4. Для угловых журналов критична дисциплина переходов `sec -> deg -> sin(...)`.

## Обязательные инварианты аудита

1. Для одного и того же section payload итоговое `total_deviation` должно совпадать в:
   - `verticality_widget`
   - `report_widget`
   - `report_templates`
   - `report_generator_enhanced`
2. Для `straightness_profiles` и таблиц отчета максимальная стрела прогиба должна совпадать с `straightness_summary["max_deflection_mm"]`.
3. Нормативный вывод должен зависеть от неокругленного значения, а не от текстового форматирования.
