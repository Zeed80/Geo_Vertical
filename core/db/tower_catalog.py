"""
Справочник типовых башен и мачт связи.

Содержит характеристики наиболее распространённых типов антенных
сооружений для автозаполнения паспорта объекта, описания конструкций,
нагрузок и нормативной базы в полном отчёте.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Dict, Any


@dataclass(frozen=True)
class TowerCatalogEntry:
    code: str
    name: str
    structure_type: str  # "tower", "mast", "odn"
    height_m: float
    faces: int
    sections: int
    base_size_m: float
    top_size_m: float
    year_project: int | None = None
    description: str = ""
    normative_codes: tuple[str, ...] = ()
    default_loads: Dict[str, float] = field(default_factory=dict)
    profiles: Dict[str, str] = field(default_factory=dict)


TOWER_CATALOG: List[TowerCatalogEntry] = [
    TowerCatalogEntry(
        code="ПСМО-40",
        name="Призматическая стальная мачта обзорная 40 м",
        structure_type="tower",
        height_m=40.0,
        faces=4,
        sections=4,
        base_size_m=3.2,
        top_size_m=3.2,
        year_project=1975,
        description="4-гранная призматическая башня высотой 40 м с оттяжками",
        normative_codes=("СП 70.13330.2012", "ГОСТ 31937-2011", "ГОСТ Р 71949-2025"),
        profiles={"пояса": "Уголок 100x100x8", "решётка": "Уголок 63x63x5"},
    ),
    TowerCatalogEntry(
        code="П-64",
        name="Пирамидальная башня 64 м",
        structure_type="tower",
        height_m=64.0,
        faces=4,
        sections=6,
        base_size_m=6.4,
        top_size_m=2.0,
        year_project=1968,
        description="4-гранная пирамидальная башня 64 м для радиорелейных линий",
        normative_codes=("СП 70.13330.2012", "ГОСТ 31937-2011", "ГОСТ Р 71949-2025"),
        profiles={"пояса": "Уголок 125x125x10", "решётка": "Уголок 75x75x6"},
    ),
    TowerCatalogEntry(
        code="П-72",
        name="Пирамидальная башня 72 м",
        structure_type="tower",
        height_m=72.0,
        faces=4,
        sections=7,
        base_size_m=7.2,
        top_size_m=2.0,
        year_project=1968,
        description="4-гранная пирамидальная башня 72 м для радиорелейных линий",
        normative_codes=("СП 70.13330.2012", "ГОСТ 31937-2011", "ГОСТ Р 71949-2025"),
        profiles={"пояса": "Уголок 140x140x12", "решётка": "Уголок 75x75x6"},
    ),
    TowerCatalogEntry(
        code="У30-2/48",
        name="Универсальная башня 48 м (модификация 2)",
        structure_type="tower",
        height_m=48.0,
        faces=4,
        sections=5,
        base_size_m=4.8,
        top_size_m=2.0,
        year_project=1985,
        description="4-гранная пирамидальная башня 48 м для связи",
        normative_codes=("СП 70.13330.2012", "ГОСТ 31937-2011", "ГОСТ Р 71949-2025"),
        profiles={"пояса": "Уголок 110x110x8", "решётка": "Уголок 63x63x5"},
    ),
    TowerCatalogEntry(
        code="РМ4001-59",
        name="Радиомачта 59 м (проект 4001)",
        structure_type="mast",
        height_m=59.0,
        faces=3,
        sections=5,
        base_size_m=2.4,
        top_size_m=0.6,
        year_project=1970,
        description="3-гранная мачта с оттяжками 59 м",
        normative_codes=("СП 70.13330.2012", "ГОСТ 31937-2011", "ГОСТ Р 71949-2025"),
        profiles={"пояса": "Труба 89x4", "решётка": "Труба 48x3"},
    ),
    TowerCatalogEntry(
        code="СОМ-30",
        name="Стальная обзорная мачта 30 м",
        structure_type="tower",
        height_m=30.0,
        faces=4,
        sections=3,
        base_size_m=2.5,
        top_size_m=2.5,
        year_project=1980,
        description="4-гранная призматическая башня 30 м",
        normative_codes=("СП 70.13330.2012", "ГОСТ 31937-2011"),
        profiles={"пояса": "Уголок 90x90x7", "решётка": "Уголок 50x50x5"},
    ),
    TowerCatalogEntry(
        code="АМС-70",
        name="Антенно-мачтовое сооружение 70 м",
        structure_type="tower",
        height_m=70.0,
        faces=3,
        sections=7,
        base_size_m=5.0,
        top_size_m=1.5,
        year_project=2005,
        description="3-гранная пирамидальная башня 70 м для сотовой связи",
        normative_codes=("СП 70.13330.2012", "ГОСТ 31937-2011", "ГОСТ Р 71949-2025"),
        profiles={"пояса": "Уголок 125x125x10", "решётка": "Уголок 63x63x5"},
    ),
    TowerCatalogEntry(
        code="АМС-110",
        name="Антенно-мачтовое сооружение 110 м",
        structure_type="tower",
        height_m=110.0,
        faces=4,
        sections=11,
        base_size_m=9.0,
        top_size_m=2.5,
        year_project=2008,
        description="4-гранная пирамидальная башня 110 м с секционным монтажом",
        normative_codes=("СП 70.13330.2012", "ГОСТ 31937-2011", "ГОСТ Р 71949-2025"),
        profiles={"пояса": "Уголок 160x160x14", "решётка": "Уголок 90x90x7"},
    ),
    TowerCatalogEntry(
        code="Р-2",
        name="Ретранслятор Р-2 (30 м)",
        structure_type="tower",
        height_m=30.0,
        faces=3,
        sections=3,
        base_size_m=2.0,
        top_size_m=0.8,
        year_project=1990,
        description="3-гранная пирамидальная башня 30 м для ретрансляции",
        normative_codes=("СП 70.13330.2012", "ГОСТ 31937-2011"),
        profiles={"пояса": "Труба 76x4", "решётка": "Труба 42x3"},
    ),
    TowerCatalogEntry(
        code="ОДН-6",
        name="Опора двойного назначения 6 м",
        structure_type="odn",
        height_m=6.0,
        faces=1,
        sections=1,
        base_size_m=0.3,
        top_size_m=0.15,
        description="Стальная трубчатая опора двойного назначения (освещение + связь)",
        normative_codes=("СП 70.13330.2012", "ГОСТ 31937-2011"),
        profiles={"ствол": "Труба 219x6"},
    ),
    TowerCatalogEntry(
        code="АМС-40",
        name="Антенно-мачтовое сооружение 40 м",
        structure_type="tower",
        height_m=40.0,
        faces=3,
        sections=4,
        base_size_m=3.5,
        top_size_m=1.2,
        year_project=2000,
        description="3-гранная пирамидальная башня 40 м для сотовой связи",
        normative_codes=("СП 70.13330.2012", "ГОСТ 31937-2011", "ГОСТ Р 71949-2025"),
        profiles={"пояса": "Уголок 100x100x8", "решётка": "Уголок 50x50x5"},
    ),
    TowerCatalogEntry(
        code="АМС-50",
        name="Антенно-мачтовое сооружение 50 м",
        structure_type="tower",
        height_m=50.0,
        faces=3,
        sections=5,
        base_size_m=4.0,
        top_size_m=1.5,
        year_project=2002,
        description="3-гранная пирамидальная башня 50 м для сотовой связи",
        normative_codes=("СП 70.13330.2012", "ГОСТ 31937-2011", "ГОСТ Р 71949-2025"),
        profiles={"пояса": "Уголок 110x110x8", "решётка": "Уголок 63x63x5"},
    ),
]


def get_tower_catalog() -> List[TowerCatalogEntry]:
    return list(TOWER_CATALOG)


def find_tower_by_code(code: str) -> TowerCatalogEntry | None:
    code_lower = code.strip().lower()
    for entry in TOWER_CATALOG:
        if entry.code.lower() == code_lower:
            return entry
    return None


def find_towers_by_type(structure_type: str) -> List[TowerCatalogEntry]:
    key = structure_type.lower()
    return [t for t in TOWER_CATALOG if t.structure_type == key]
