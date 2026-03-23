import pytest

from core.normatives import (
    NormativeChecker,
    check_straightness_compliance,
    check_vertical_compliance,
    get_straightness_tolerance,
    get_vertical_tolerance,
)


class TestGetVerticalTolerance:
    def test_basic(self):
        assert get_vertical_tolerance(10.0) == 0.01

    def test_mast_uses_stricter_tolerance(self):
        assert get_vertical_tolerance(10.0, "mast") == pytest.approx(0.007)

    def test_odn_uses_looser_tolerance(self):
        assert get_vertical_tolerance(10.0, "odn") == pytest.approx(0.05)

    def test_zero_height(self):
        assert get_vertical_tolerance(0.0) == 0.0

    def test_high_tower(self):
        assert get_vertical_tolerance(100.0) == 0.1


class TestGetStraightnessTolerance:
    def test_basic(self):
        assert abs(get_straightness_tolerance(7.5) - 0.01) < 1e-6

    def test_zero_length(self):
        assert get_straightness_tolerance(0.0) == 0.0


class TestComplianceChecks:
    def test_vertical_compliant(self):
        assert check_vertical_compliance(0.005, 10.0) is True

    def test_vertical_non_compliant_for_mast(self):
        assert check_vertical_compliance(0.008, 10.0, "mast") is False

    def test_vertical_non_compliant(self):
        assert check_vertical_compliance(0.015, 10.0) is False

    def test_straightness_compliant(self):
        assert check_straightness_compliance(0.005, 7.5) is True

    def test_straightness_non_compliant(self):
        assert check_straightness_compliance(0.015, 7.5) is False


class TestNormativeChecker:
    def test_check_vertical_deviations(self):
        checker = NormativeChecker()
        deviations = [0.005, 0.008, 0.012]
        heights = [5.0, 10.0, 15.0]
        result = checker.check_vertical_deviations(deviations, heights)
        assert result['total'] == 3
        assert result['passed'] + result['failed'] == 3

    def test_check_straightness_deviations(self):
        checker = NormativeChecker()
        result = checker.check_straightness_deviations([0.005, 0.008, 0.012], 7.5)
        assert result['total'] == 3
        assert result['tolerance'] == pytest.approx(0.01)

    def test_empty_lists(self):
        checker = NormativeChecker()
        result = checker.check_vertical_deviations([], [])
        assert result['total'] == 0
        assert result['passed'] == 0
        assert result['failed'] == 0
