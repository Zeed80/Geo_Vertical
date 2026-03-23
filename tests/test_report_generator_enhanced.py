from utils.report_generator_enhanced import EnhancedReportGenerator


def test_verticality_conclusion_lines_for_exceedance():
    line1, line2 = EnhancedReportGenerator._build_verticality_conclusion_lines({"failed": 1})

    assert "превышают допусков" in line1
    assert "требуют дополнительной оценки" in line2


def test_verticality_conclusion_lines_for_compliance():
    line1, line2 = EnhancedReportGenerator._build_verticality_conclusion_lines({"failed": 0})

    assert "не превышают допусков" in line1
    assert "не препятствуют нормальной эксплуатации" in line2
