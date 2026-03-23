"""
Модуль нормативных допусков для геодезического контроля.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass(frozen=True)
class NormativeDocument:
    code: str
    title: str
    scope: str = ""
    applies_to: tuple[str, ...] = ()


NORMATIVE_REFERENCES: List[NormativeDocument] = [
    NormativeDocument(
        "СП 70.13330.2012",
        "Несущие и ограждающие конструкции. Актуализированная редакция СНиП 3.03.01-87",
        "Допуски при монтаже и эксплуатации металлических конструкций",
        ("tower", "mast", "odn"),
    ),
    NormativeDocument(
        "ГОСТ 31937-2011",
        "Здания и сооружения. Правила обследования и мониторинга технического состояния",
        "Общий порядок обследования зданий и сооружений",
        ("tower", "mast", "odn"),
    ),
    NormativeDocument(
        "ГОСТ Р 71949-2025",
        "Опоры антенных сооружений связи. Обследование технического состояния. Общие требования",
        "Специализированный стандарт для антенных опор",
        ("tower", "mast"),
    ),
    NormativeDocument(
        "СП 13-102-2003",
        "Правила обследования несущих строительных конструкций зданий и сооружений",
        "Методика обследования несущих конструкций",
        ("tower", "mast", "odn"),
    ),
    NormativeDocument(
        "СП 20.13330.2016",
        "Нагрузки и воздействия. Актуализированная редакция СНиП 2.01.07-85*",
        "Определение ветровых, снеговых, гололёдных нагрузок",
        ("tower", "mast", "odn"),
    ),
    NormativeDocument(
        "СП 16.13330.2017",
        "Стальные конструкции. Актуализированная редакция СНиП II-23-81*",
        "Расчёт и проектирование стальных конструкций",
        ("tower", "mast", "odn"),
    ),
    NormativeDocument(
        "ГОСТ 9.032-74",
        "Покрытия лакокрасочные. Группы, технические требования и обозначения",
        "Контроль лакокрасочных покрытий",
        ("tower", "mast", "odn"),
    ),
    NormativeDocument(
        "ГОСТ 9.302-88",
        "Покрытия металлические и неметаллические неорганические. Методы контроля",
        "Контроль защитных покрытий",
        ("tower", "mast", "odn"),
    ),
    NormativeDocument(
        "ГОСТ 14782-86",
        "Контроль неразрушающий. Соединения сварные. Методы ультразвуковые",
        "УЗК сварных соединений",
        ("tower", "mast"),
    ),
    NormativeDocument(
        "ГОСТ 22536.0-87",
        "Сталь углеродистая и чугун нелегированный. Общие требования к методам анализа",
        "Определение химического состава стали",
        ("tower", "mast"),
    ),
    NormativeDocument(
        "ГОСТ 18442-80",
        "Контроль неразрушающий. Капиллярные методы. Общие требования",
        "Капиллярный контроль дефектов",
        ("tower", "mast"),
    ),
    NormativeDocument(
        "СП 22.13330.2016",
        "Основания зданий и сооружений. Актуализированная редакция СНиП 2.02.01-83*",
        "Проектирование оснований и фундаментов",
        ("tower", "mast", "odn"),
    ),
    NormativeDocument(
        "ГОСТ 26433.2-94",
        "Правила выполнения измерений параметров зданий и сооружений",
        "Геодезический контроль параметров конструкций",
        ("tower", "mast", "odn"),
    ),
    NormativeDocument(
        "СП 126.13330.2017",
        "Геодезические работы в строительстве. Актуализированная редакция СНиП 3.01.03-84",
        "Геодезическое обеспечение строительства",
        ("tower", "mast", "odn"),
    ),
    NormativeDocument(
        "ГОСТ 27751-2014",
        "Надёжность строительных конструкций и оснований. Основные положения",
        "Оценка надёжности и остаточного ресурса",
        ("tower", "mast", "odn"),
    ),
    NormativeDocument(
        "ГОСТ 2.105-2019",
        "ЕСКД. Общие требования к текстовым документам",
        "Оформление технической документации и отчётов",
        ("tower", "mast", "odn"),
    ),
    NormativeDocument(
        "ГОСТ 5264-80",
        "Ручная дуговая сварка. Соединения сварные. Основные типы, конструктивные элементы и размеры",
        "Контроль сварных соединений",
        ("tower", "mast"),
    ),
    NormativeDocument(
        "СП 63.13330.2018",
        "Бетонные и железобетонные конструкции. Основные положения",
        "Обследование бетонных конструкций фундаментов",
        ("tower", "mast", "odn"),
    ),
    NormativeDocument(
        "ГОСТ Р 53778-2010",
        "Здания и сооружения. Правила обследования и мониторинга технического состояния",
        "Категорирование технического состояния",
        ("tower", "mast", "odn"),
    ),
    NormativeDocument(
        "РД 34.21.122-87",
        "Инструкция по устройству молниезащиты зданий и сооружений",
        "Проверка молниезащиты и заземления",
        ("tower", "mast"),
    ),
]


def get_normatives_for_structure(structure_type: str) -> List[NormativeDocument]:
    """Возвращает нормативные документы, применимые к данному типу опоры."""
    key = str(structure_type or "tower").lower()
    return [doc for doc in NORMATIVE_REFERENCES if not doc.applies_to or key in doc.applies_to]


def format_normative_list(docs: List[NormativeDocument]) -> List[str]:
    """Формирует текстовый перечень нормативных документов."""
    return [f"{doc.code} {doc.title}" for doc in docs]

# Базовые коэффициенты для вертикальности по типам опор.
# По умолчанию оставляем башню для обратной совместимости.
VERTICAL_TOLERANCE_COEFFICIENT = 0.001
VERTICAL_TOLERANCE_COEFFICIENTS = {
    "tower": 0.001,
    "mast": 0.0007,
    "odn": 0.005,
}

# Допуск прямолинейности: L / 750
STRAIGHTNESS_TOLERANCE_DIVISOR = 750


def get_vertical_tolerance(height: float, structure_type: str = "tower") -> float:
    coefficient = VERTICAL_TOLERANCE_COEFFICIENTS.get(
        str(structure_type or "tower").lower(),
        VERTICAL_TOLERANCE_COEFFICIENT,
    )
    return coefficient * abs(height)


def get_straightness_tolerance(section_length: float) -> float:
    return section_length / STRAIGHTNESS_TOLERANCE_DIVISOR


def check_vertical_compliance(deviation: float, height: float, structure_type: str = "tower") -> bool:
    tolerance = get_vertical_tolerance(height, structure_type)
    return abs(deviation) <= tolerance


def check_straightness_compliance(deflection: float, section_length: float) -> bool:
    tolerance = get_straightness_tolerance(section_length)
    return abs(deflection) <= tolerance


class NormativeChecker:
    def __init__(self, structure_type: str = "tower"):
        self.structure_type = structure_type
        self.vertical_coefficient = VERTICAL_TOLERANCE_COEFFICIENTS.get(
            str(structure_type or "tower").lower(),
            VERTICAL_TOLERANCE_COEFFICIENT,
        )
        self.straightness_divisor = STRAIGHTNESS_TOLERANCE_DIVISOR

    def check_vertical_deviations(self, deviations: list, heights: list) -> dict:
        results = {
            "compliant": [],
            "non_compliant": [],
            "total": len(deviations),
            "passed": 0,
            "failed": 0,
        }

        for i, (dev, h) in enumerate(zip(deviations, heights)):
            tolerance = get_vertical_tolerance(h, self.structure_type)
            is_compliant = abs(dev) <= tolerance
            result_item = {
                "index": i,
                "height": h,
                "deviation": dev,
                "tolerance": tolerance,
                "compliant": is_compliant,
                "excess": abs(dev) - tolerance if not is_compliant else 0,
            }
            if is_compliant:
                results["compliant"].append(result_item)
                results["passed"] += 1
            else:
                results["non_compliant"].append(result_item)
                results["failed"] += 1
        return results

    def check_straightness_deviations(self, deflections: list, section_length: float) -> dict:
        tolerance = get_straightness_tolerance(section_length)
        results = {
            "compliant": [],
            "non_compliant": [],
            "total": len(deflections),
            "passed": 0,
            "failed": 0,
            "tolerance": tolerance,
        }

        for i, deflection in enumerate(deflections):
            is_compliant = abs(deflection) <= tolerance
            result_item = {
                "index": i,
                "deflection": deflection,
                "tolerance": tolerance,
                "compliant": is_compliant,
                "excess": abs(deflection) - tolerance if not is_compliant else 0,
            }
            if is_compliant:
                results["compliant"].append(result_item)
                results["passed"] += 1
            else:
                results["non_compliant"].append(result_item)
                results["failed"] += 1
        return results
