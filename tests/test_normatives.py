"""
Unit-тесты для модуля normatives.py
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from core.normatives import (
    get_vertical_tolerance,
    get_straightness_tolerance,
    check_vertical_compliance,
    check_straightness_compliance,
    NormativeChecker
)


class TestGetVerticalTolerance:
    """Тесты функции get_vertical_tolerance"""
    
    def test_basic(self):
        """Базовый тест"""
        tolerance = get_vertical_tolerance(10.0)
        assert tolerance == 0.01  # 0.001 * 10
    
    def test_zero_height(self):
        """Тест с нулевой высотой"""
        tolerance = get_vertical_tolerance(0.0)
        assert tolerance == 0.0
    
    def test_high_tower(self):
        """Тест высокой башни"""
        tolerance = get_vertical_tolerance(100.0)
        assert tolerance == 0.1  # 0.001 * 100


class TestGetStraightnessTolerance:
    """Тесты функции get_straightness_tolerance"""
    
    def test_basic(self):
        """Базовый тест"""
        tolerance = get_straightness_tolerance(7.5)
        assert abs(tolerance - 0.01) < 1e-6  # 7.5 / 750
    
    def test_zero_length(self):
        """Тест с нулевой длиной"""
        tolerance = get_straightness_tolerance(0.0)
        assert tolerance == 0.0


class TestCheckVerticalCompliance:
    """Тесты функции check_vertical_compliance"""
    
    def test_compliant(self):
        """Тест соответствия нормативу"""
        deviation = 0.005  # 5 мм
        height = 10.0
        tolerance = get_vertical_tolerance(height)  # 0.01 м = 10 мм
        result = check_vertical_compliance(deviation, height)
        assert result['compliant']
        assert result['deviation'] == deviation
        assert result['tolerance'] == tolerance
    
    def test_non_compliant(self):
        """Тест превышения норматива"""
        deviation = 0.015  # 15 мм
        height = 10.0
        tolerance = get_vertical_tolerance(height)  # 0.01 м = 10 мм
        result = check_vertical_compliance(deviation, height)
        assert not result['compliant']
        assert result['excess'] > 0


class TestCheckStraightnessCompliance:
    """Тесты функции check_straightness_compliance"""
    
    def test_compliant(self):
        """Тест соответствия нормативу"""
        deflection = 0.005  # 5 мм
        section_length = 7.5
        tolerance = get_straightness_tolerance(section_length)  # 0.01 м = 10 мм
        result = check_straightness_compliance(deflection, section_length)
        assert result['compliant']
    
    def test_non_compliant(self):
        """Тест превышения норматива"""
        deflection = 0.015  # 15 мм
        section_length = 7.5
        tolerance = get_straightness_tolerance(section_length)  # 0.01 м = 10 мм
        result = check_straightness_compliance(deflection, section_length)
        assert not result['compliant']


class TestNormativeChecker:
    """Тесты класса NormativeChecker"""
    
    def test_check_vertical_deviations(self):
        """Тест проверки отклонений вертикальности"""
        checker = NormativeChecker()
        deviations = [0.005, 0.008, 0.012]  # 5, 8, 12 мм
        heights = [5.0, 10.0, 15.0]
        result = checker.check_vertical_deviations(deviations, heights)
        assert 'total' in result
        assert 'passed' in result
        assert 'failed' in result
        assert result['total'] == 3
    
    def test_check_straightness_deviations(self):
        """Тест проверки отклонений прямолинейности"""
        checker = NormativeChecker()
        deflections = [0.005, 0.008, 0.012]  # 5, 8, 12 мм
        section_length = 7.5
        result = checker.check_straightness_deviations(deflections, section_length)
        assert 'total' in result
        assert 'passed' in result
        assert 'failed' in result
    
    def test_empty_lists(self):
        """Тест с пустыми списками"""
        checker = NormativeChecker()
        result = checker.check_vertical_deviations([], [])
        assert result['total'] == 0
        assert result['passed'] == 0
        assert result['failed'] == 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

