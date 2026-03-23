"""
Unit-тесты для модуля calculations.py
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import numpy as np
import pandas as pd
import pytest

from core.calculations import (
    approximate_tower_axis,
    calculate_belt_center,
    calculate_straightness_deviation,
    calculate_vertical_deviation,
    distance_to_line_3d,
    group_points_by_height,
    invalidate_cache,
    process_tower_data,
)


class TestGroupPointsByHeight:
    """Тесты функции group_points_by_height"""

    def test_empty_dataframe(self):
        """Тест с пустым DataFrame"""
        df = pd.DataFrame()
        result = group_points_by_height(df, tolerance=0.1)
        assert result == {}

    def test_single_point(self):
        """Тест с одной точкой"""
        df = pd.DataFrame({'x': [0], 'y': [0], 'z': [5.0]})
        result = group_points_by_height(df, tolerance=0.1)
        assert len(result) == 1

    def test_multiple_belts(self):
        """Тест группировки нескольких поясов"""
        data = []
        for z in [0.0, 5.0, 10.0, 15.0]:
            for i in range(4):
                angle = i * np.pi / 2
                data.append({
                    'x': np.cos(angle),
                    'y': np.sin(angle),
                    'z': z
                })
        df = pd.DataFrame(data)
        result = group_points_by_height(df, tolerance=0.1)
        assert len(result) == 4

    def test_tolerance(self):
        """Тест влияния допуска"""
        df = pd.DataFrame({
            'x': [0, 1, 2, 3],
            'y': [0, 0, 0, 0],
            'z': [5.0, 5.05, 5.15, 5.25]
        })
        # С малым допуском - 4 группы
        result_small = group_points_by_height(df, tolerance=0.05)
        # С большим допуском - меньше групп
        result_large = group_points_by_height(df, tolerance=0.2)
        assert len(result_small) >= len(result_large)

    def test_with_assigned_belts(self):
        """Тест с назначенными поясами"""
        df = pd.DataFrame({
            'x': [0, 1, 2, 3],
            'y': [0, 0, 0, 0],
            'z': [5.0, 5.0, 10.0, 10.0],
            'belt': [1, 1, 2, 2]
        })
        result = group_points_by_height(df, tolerance=0.1, section_grouping_mode='assigned_sections')
        assert len(result) == 2


    def test_height_levels_handles_non_contiguous_index(self):
        df = pd.DataFrame(
            {
                'x': [0.0, 1.0, 0.0, 1.0],
                'y': [0.0, 0.0, 1.0, 1.0],
                'z': [5.0, 5.02, 10.0, 10.01],
                'belt': [1, 3, 1, 3],
            },
            index=[10, 12, 20, 25],
        )

        result = group_points_by_height(df, tolerance=0.1, section_grouping_mode='height_levels')

        assert len(result) == 2
        assert sorted(len(group) for group in result.values()) == [2, 2]


class TestCalculateBeltCenter:
    """Тесты функции calculate_belt_center"""

    def test_mean_method(self):
        """Тест метода среднего"""
        df = pd.DataFrame({
            'x': [0, 1, 0, -1],
            'y': [1, 0, -1, 0],
            'z': [5.0, 5.0, 5.0, 5.0]
        })
        center = calculate_belt_center(df, method='mean')
        assert abs(center[0] - 0.0) < 1e-6
        assert abs(center[1] - 0.0) < 1e-6
        assert abs(center[2] - 5.0) < 1e-6

    def test_lsq_method(self):
        """Тест метода наименьших квадратов"""
        df = pd.DataFrame({
            'x': [0, 1, 0, -1],
            'y': [1, 0, -1, 0],
            'z': [5.0, 5.0, 5.0, 5.0]
        })
        center = calculate_belt_center(df, method='lsq')
        assert len(center) == 3
        assert abs(center[2] - 5.0) < 1e-6

    def test_single_point(self):
        """Тест с одной точкой"""
        df = pd.DataFrame({'x': [1.0], 'y': [2.0], 'z': [5.0]})
        center = calculate_belt_center(df, method='mean')
        assert center[0] == 1.0
        assert center[1] == 2.0
        assert center[2] == 5.0


class TestApproximateTowerAxis:
    """Тесты функции approximate_tower_axis"""

    def test_perfect_vertical(self):
        """Тест идеально вертикальной башни"""
        centers = pd.DataFrame({
            'x': [0, 0, 0, 0],
            'y': [0, 0, 0, 0],
            'z': [0, 5, 10, 15]
        })
        axis = approximate_tower_axis(centers)
        assert axis['valid']
        assert abs(axis['dx']) < 1e-6
        assert abs(axis['dy']) < 1e-6

    def test_tilted_tower(self):
        """Тест наклоненной башни"""
        centers = pd.DataFrame({
            'x': [0, 0.01, 0.02, 0.03],
            'y': [0, 0.01, 0.02, 0.03],
            'z': [0, 5, 10, 15]
        })
        axis = approximate_tower_axis(centers)
        assert axis['valid']
        assert abs(axis['dx']) > 0
        assert abs(axis['dy']) > 0

    def test_empty_centers(self):
        """Тест с пустыми центрами"""
        centers = pd.DataFrame()
        axis = approximate_tower_axis(centers)
        assert not axis['valid']

    def test_single_center(self):
        """Тест с одним центром"""
        centers = pd.DataFrame({'x': [0], 'y': [0], 'z': [5.0]})
        axis = approximate_tower_axis(centers)
        # С одним центром ось не может быть построена
        assert not axis['valid']


class TestCalculateVerticalDeviation:
    """Тесты функции calculate_vertical_deviation"""

    def test_perfect_vertical(self):
        """Тест идеально вертикальной башни"""
        centers = pd.DataFrame({
            'x': [0, 0, 0],
            'y': [0, 0, 0],
            'z': [0, 5, 10]
        })
        axis = {
            'valid': True,
            'x0': 0.0,
            'y0': 0.0,
            'z0': 0.0,
            'dx': 0.0,
            'dy': 0.0
        }
        result = calculate_vertical_deviation(centers, axis)
        assert 'deviation' in result.columns
        assert all(result['deviation'] < 1e-6)

    def test_with_deviation(self):
        """Тест с отклонениями"""
        centers = pd.DataFrame({
            'x': [0, 0.01, 0.02],
            'y': [0, 0.01, 0.02],
            'z': [0, 5, 10]
        })
        axis = {
            'valid': True,
            'x0': 0.0,
            'y0': 0.0,
            'z0': 0.0,
            'dx': 0.0,
            'dy': 0.0
        }
        result = calculate_vertical_deviation(centers, axis)
        assert result['deviation'].iloc[0] == 0.0
        assert all(result['deviation'].iloc[1:] > 0)


class TestCalculateStraightnessDeviation:
    """Тесты функции calculate_straightness_deviation"""

    def test_perfect_straight(self):
        """Тест идеально прямой башни"""
        centers = pd.DataFrame({
            'x': [0, 0, 0],
            'y': [0, 0, 0],
            'z': [0, 5, 10]
        })
        result = calculate_straightness_deviation(centers)
        assert 'straightness_deviation' in result.columns
        assert all(result['straightness_deviation'] < 1e-6)

    def test_less_than_three_points(self):
        """Тест с менее чем тремя точками"""
        centers = pd.DataFrame({
            'x': [0, 0],
            'y': [0, 0],
            'z': [0, 5]
        })
        result = calculate_straightness_deviation(centers)
        assert all(result['straightness_deviation'] == 0.0)


    def test_preserves_source_index_after_sorting(self):
        centers = pd.DataFrame(
            {
                'x': [0.0, 0.02, 0.0],
                'y': [0.0, 0.0, 0.0],
                'z': [10.0, 5.0, 0.0],
            },
            index=[30, 10, 20],
        )

        result = calculate_straightness_deviation(centers)

        assert result.loc[10, 'straightness_deviation'] > 0.0
        assert result.loc[20, 'straightness_deviation'] == 0.0
        assert result.loc[30, 'straightness_deviation'] == 0.0


class TestProcessTowerData:
    """Тесты функции process_tower_data"""

    def test_basic_processing(self):
        """Базовый тест обработки"""
        data = []
        for z in [0.0, 5.0, 10.0]:
            for i in range(4):
                angle = i * np.pi / 2
                data.append({
                    'x': np.cos(angle),
                    'y': np.sin(angle),
                    'z': z,
                    'name': f'Point_{z}_{i}'
                })
        df = pd.DataFrame(data)
        results = process_tower_data(df, height_tolerance=0.1, center_method='mean')
        assert results['valid']
        assert len(results['centers']) > 0
        assert results['axis']['valid']

    def test_empty_data(self):
        """Тест с пустыми данными"""
        df = pd.DataFrame()
        results = process_tower_data(df, height_tolerance=0.1)
        assert not results['valid']

    def test_cache(self):
        """Тест кэширования"""
        data = []
        for z in [0.0, 5.0]:
            for i in range(4):
                angle = i * np.pi / 2
                data.append({
                    'x': np.cos(angle),
                    'y': np.sin(angle),
                    'z': z,
                    'name': f'Point_{z}_{i}'
                })
        df = pd.DataFrame(data)

        # Первый вызов
        results1 = process_tower_data(df, height_tolerance=0.1, use_cache=True)
        # Второй вызов (должен использовать кэш)
        results2 = process_tower_data(df, height_tolerance=0.1, use_cache=True)

        assert results1['valid'] == results2['valid']
        assert len(results1['centers']) == len(results2['centers'])

    def test_cache_respects_belt_and_flag_changes(self):
        data = []
        for z in [0.0, 5.0, 10.0]:
            for belt_num, (x, y) in enumerate([(1.0, 0.0), (0.0, 1.0), (-1.0, 0.0), (0.0, -1.0)], start=1):
                data.append({
                    'x': x,
                    'y': y,
                    'z': z,
                    'belt': belt_num,
                    'name': f'P_{belt_num}_{z}'
                })

        original = pd.DataFrame(data)
        collapsed = original.copy()
        collapsed.loc[collapsed['belt'].notna(), 'belt'] = 1

        invalidate_cache()
        collapsed_results = process_tower_data(
            collapsed,
            height_tolerance=0.1,
            center_method='mean',
            section_grouping_mode='height_levels',
            use_cache=True,
        )
        restored_results = process_tower_data(
            original,
            height_tolerance=0.1,
            center_method='mean',
            section_grouping_mode='height_levels',
            use_cache=True,
        )

        assert collapsed_results['valid']
        assert restored_results['valid']
        assert len(collapsed_results['straightness_profiles']) == 1
        assert len(restored_results['straightness_profiles']) == 4
        invalidate_cache()


    def test_height_levels_accept_sparse_face_belts(self):
        df = pd.DataFrame(
            [
                {'x': 1.0, 'y': 0.0, 'z': 0.0, 'belt': 1},
                {'x': -1.0, 'y': 0.0, 'z': 0.0, 'belt': 3},
                {'x': 1.0, 'y': 0.0, 'z': 5.0, 'belt': 1},
                {'x': -1.0, 'y': 0.0, 'z': 5.0, 'belt': 3},
            ]
        )

        results = process_tower_data(
            df,
            height_tolerance=0.1,
            center_method='mean',
            section_grouping_mode='height_levels',
            use_cache=False,
        )

        assert results['valid']
        assert len(results['centers']) == 2
        assert results['straightness_profiles']


class TestDistanceToLine3D:
    """Тесты функции distance_to_line_3d"""

    def test_point_on_line(self):
        """Тест точки на прямой"""
        point = (0, 0, 0)
        line_point = (0, 0, 0)
        line_direction = (1, 0, 0)
        distance = distance_to_line_3d(point, line_point, line_direction)
        assert abs(distance) < 1e-6

    def test_point_off_line(self):
        """Тест точки вне прямой"""
        point = (0, 1, 0)
        line_point = (0, 0, 0)
        line_direction = (1, 0, 0)
        distance = distance_to_line_3d(point, line_point, line_direction)
        assert abs(distance - 1.0) < 1e-6


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

