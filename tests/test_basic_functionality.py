"""
Базовые тесты функциональности
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pandas as pd
import numpy as np
from core.data_loader import load_data_from_file, validate_data, CSVLoader
from core.calculations import (
    group_points_by_height, 
    calculate_belt_center,
    approximate_tower_axis,
    calculate_vertical_deviation,
    process_tower_data
)
from core.normatives import (
    get_vertical_tolerance,
    get_straightness_tolerance,
    check_vertical_compliance,
    NormativeChecker
)


def test_data_loading():
    """Тест загрузки данных"""
    print("Тест 1: Загрузка данных из CSV...")
    
    # Загружаем тестовый файл
    data, epsg = load_data_from_file('examples/test_tower_data.csv')
    
    assert not data.empty, "Данные не должны быть пустыми"
    assert 'x' in data.columns, "Должна быть колонка x"
    assert 'y' in data.columns, "Должна быть колонка y"
    assert 'z' in data.columns, "Должна быть колонка z"
    
    print(f"✓ Загружено {len(data)} точек")
    
    # Валидация
    is_valid, message = validate_data(data)
    assert is_valid, f"Данные должны быть валидны: {message}"
    print(f"✓ Валидация пройдена: {message}")
    
    return data


def test_grouping(data):
    """Тест группировки точек по поясам"""
    print("\nТест 2: Группировка точек по поясам...")
    
    belts = group_points_by_height(data, tolerance=0.1)
    
    assert len(belts) > 0, "Должен быть хотя бы один пояс"
    print(f"✓ Обнаружено {len(belts)} поясов")
    
    for height, points in belts.items():
        print(f"  Пояс на высоте {height:.2f}м: {len(points)} точек")
    
    return belts


def test_centers(belts):
    """Тест расчета центров поясов"""
    print("\nТест 3: Расчет центров поясов...")
    
    centers = []
    for height, points in sorted(belts.items()):
        x_c, y_c, z_c = calculate_belt_center(points, method='mean')
        centers.append({'x': x_c, 'y': y_c, 'z': z_c})
        print(f"  Центр на высоте {z_c:.2f}м: ({x_c:.3f}, {y_c:.3f})")
    
    centers_df = pd.DataFrame(centers)
    assert len(centers_df) == len(belts), "Количество центров должно совпадать с поясами"
    print(f"✓ Рассчитано {len(centers_df)} центров")
    
    return centers_df


def test_axis(centers):
    """Тест аппроксимации оси"""
    print("\nТест 4: Аппроксимация оси мачты...")
    
    axis = approximate_tower_axis(centers)
    
    assert axis['valid'], "Ось должна быть валидной"
    print(f"✓ Ось аппроксимирована")
    print(f"  Начало: ({axis['x0']:.3f}, {axis['y0']:.3f}, {axis['z0']:.1f})")
    print(f"  Наклон: dx={axis['dx']:.6f}, dy={axis['dy']:.6f}")
    print(f"  Корреляция: r_x={axis['r_x']:.4f}, r_y={axis['r_y']:.4f}")
    
    return axis


def test_deviations(centers, axis):
    """Тест расчета отклонений"""
    print("\nТест 5: Расчет отклонений от вертикали...")
    
    centers_with_dev = calculate_vertical_deviation(centers, axis)
    
    assert 'deviation' in centers_with_dev.columns, "Должна быть колонка deviation"
    
    print(f"✓ Рассчитаны отклонения для {len(centers_with_dev)} поясов")
    for idx, row in centers_with_dev.iterrows():
        dev_mm = row['deviation'] * 1000
        print(f"  Высота {row['z']:.1f}м: отклонение {dev_mm:.2f} мм")
    
    return centers_with_dev


def test_normatives(centers_with_dev):
    """Тест проверки нормативов"""
    print("\nТест 6: Проверка соответствия нормативам...")
    
    checker = NormativeChecker()
    
    # Проверка вертикальности
    vertical_check = checker.check_vertical_deviations(
        centers_with_dev['deviation'].tolist(),
        centers_with_dev['z'].tolist()
    )
    
    print(f"✓ Проверка вертикальности:")
    print(f"  Всего: {vertical_check['total']}")
    print(f"  В норме: {vertical_check['passed']}")
    print(f"  Превышение: {vertical_check['failed']}")
    
    if vertical_check['non_compliant']:
        print("  Превышения допуска:")
        for item in vertical_check['non_compliant']:
            excess_mm = item['excess'] * 1000
            print(f"    Высота {item['height']:.1f}м: +{excess_mm:.2f} мм")
    
    return vertical_check


def test_full_processing():
    """Тест полного цикла обработки"""
    print("\nТест 7: Полный цикл обработки...")
    
    data, _ = load_data_from_file('examples/test_tower_data.csv')
    
    results = process_tower_data(data, height_tolerance=0.1, center_method='mean')
    
    assert results['valid'], "Результаты должны быть валидными"
    assert len(results['centers']) > 0, "Должны быть центры поясов"
    
    print(f"✓ Полная обработка выполнена успешно")
    print(f"  Обнаружено поясов: {len(results['centers'])}")
    print(f"  Ось валидна: {results['axis']['valid']}")
    
    return results


def test_perfect_tower():
    """Тест на идеальной вертикальной мачте"""
    print("\nТест 8: Идеальная вертикальная мачта...")
    
    data, _ = load_data_from_file('examples/test_tower_perfect.csv')
    results = process_tower_data(data, height_tolerance=0.1)
    
    centers = results['centers']
    max_deviation = centers['deviation'].max() * 1000  # в мм
    
    print(f"✓ Максимальное отклонение: {max_deviation:.3f} мм")
    assert max_deviation < 1.0, "Для идеальной мачты отклонение должно быть < 1 мм"
    print("✓ Идеальная мачта прошла проверку")
    
    return results


def run_all_tests():
    """Запуск всех тестов"""
    print("="*60)
    print("ЗАПУСК ТЕСТОВ GeoVertical Analyzer")
    print("="*60)
    
    try:
        # Тест 1: Загрузка
        data = test_data_loading()
        
        # Тест 2: Группировка
        belts = test_grouping(data)
        
        # Тест 3: Центры
        centers = test_centers(belts)
        
        # Тест 4: Ось
        axis = test_axis(centers)
        
        # Тест 5: Отклонения
        centers_with_dev = test_deviations(centers, axis)
        
        # Тест 6: Нормативы
        vertical_check = test_normatives(centers_with_dev)
        
        # Тест 7: Полный цикл
        results_full = test_full_processing()
        
        # Тест 8: Идеальная мачта
        results_perfect = test_perfect_tower()
        
        print("\n" + "="*60)
        print("ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО! ✓")
        print("="*60)
        return True
        
    except Exception as e:
        print(f"\n❌ ОШИБКА В ТЕСТАХ: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)

