"""
Справочник ветровых, снеговых и сейсмических районов по СП 20.13330.2016.

Предоставляет нормативные значения нагрузок для автозаполнения
раздела «Нагрузки и воздействия» в полном отчёте.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class WindRegion:
    """Ветровой район по СП 20.13330.2016, таблица 11.1."""
    code: str
    pressure_kpa: float
    description: str = ""


@dataclass(frozen=True)
class SnowRegion:
    """Снеговой район по СП 20.13330.2016, таблица 10.1."""
    code: str
    load_kpa: float
    description: str = ""


@dataclass(frozen=True)
class IcingRegion:
    """Район по толщине стенки гололёда по СП 20.13330.2016, таблица 12.1."""
    code: str
    thickness_mm: float
    description: str = ""


WIND_REGIONS: list[WindRegion] = [
    WindRegion("Ia", 0.17, "Ia район — 0.17 кПа"),
    WindRegion("I", 0.23, "I район — 0.23 кПа"),
    WindRegion("II", 0.30, "II район — 0.30 кПа"),
    WindRegion("III", 0.38, "III район — 0.38 кПа"),
    WindRegion("IV", 0.48, "IV район — 0.48 кПа"),
    WindRegion("V", 0.60, "V район — 0.60 кПа"),
    WindRegion("VI", 0.73, "VI район — 0.73 кПа"),
    WindRegion("VII", 0.85, "VII район — 0.85 кПа"),
]

SNOW_REGIONS: list[SnowRegion] = [
    SnowRegion("I", 0.50, "I район — 0.50 кПа"),
    SnowRegion("II", 1.00, "II район — 1.00 кПа"),
    SnowRegion("III", 1.50, "III район — 1.50 кПа"),
    SnowRegion("IV", 2.00, "IV район — 2.00 кПа"),
    SnowRegion("V", 2.50, "V район — 2.50 кПа"),
    SnowRegion("VI", 3.00, "VI район — 3.00 кПа"),
    SnowRegion("VII", 3.50, "VII район — 3.50 кПа"),
    SnowRegion("VIII", 4.00, "VIII район — 4.00 кПа"),
]

ICING_REGIONS: list[IcingRegion] = [
    IcingRegion("I", 5.0, "I район — 5 мм"),
    IcingRegion("II", 10.0, "II район — 10 мм"),
    IcingRegion("III", 15.0, "III район — 15 мм"),
    IcingRegion("IV", 20.0, "IV район — 20 мм"),
    IcingRegion("V", 25.0, "V район — 25 мм"),
]

SEISMICITY_LEVELS: list[tuple[int, str]] = [
    (5, "5 баллов — несейсмичная территория"),
    (6, "6 баллов — слабая сейсмичность"),
    (7, "7 баллов — умеренная сейсмичность"),
    (8, "8 баллов — высокая сейсмичность"),
    (9, "9 баллов — очень высокая сейсмичность"),
]


LOCALITY_CLIMATE_DB: dict[str, dict[str, str]] = {
    "москва": {"wind": "I", "snow": "III", "icing": "II", "seismicity": "5"},
    "санкт-петербург": {"wind": "II", "snow": "III", "icing": "II", "seismicity": "5"},
    "новосибирск": {"wind": "III", "snow": "IV", "icing": "III", "seismicity": "6"},
    "екатеринбург": {"wind": "II", "snow": "III", "icing": "III", "seismicity": "6"},
    "казань": {"wind": "II", "snow": "IV", "icing": "III", "seismicity": "6"},
    "нижний новгород": {"wind": "I", "snow": "IV", "icing": "II", "seismicity": "5"},
    "челябинск": {"wind": "II", "snow": "III", "icing": "III", "seismicity": "6"},
    "самара": {"wind": "II", "snow": "IV", "icing": "II", "seismicity": "6"},
    "ростов-на-дону": {"wind": "III", "snow": "II", "icing": "II", "seismicity": "6"},
    "уфа": {"wind": "II", "snow": "V", "icing": "III", "seismicity": "6"},
    "красноярск": {"wind": "III", "snow": "III", "icing": "III", "seismicity": "6"},
    "пермь": {"wind": "II", "snow": "V", "icing": "III", "seismicity": "6"},
    "воронеж": {"wind": "II", "snow": "III", "icing": "II", "seismicity": "5"},
    "волгоград": {"wind": "III", "snow": "II", "icing": "II", "seismicity": "6"},
    "краснодар": {"wind": "III", "snow": "II", "icing": "II", "seismicity": "7"},
    "саратов": {"wind": "III", "snow": "III", "icing": "II", "seismicity": "6"},
    "тюмень": {"wind": "II", "snow": "III", "icing": "III", "seismicity": "5"},
    "тольятти": {"wind": "II", "snow": "IV", "icing": "II", "seismicity": "6"},
    "ижевск": {"wind": "II", "snow": "V", "icing": "III", "seismicity": "6"},
    "барнаул": {"wind": "III", "snow": "IV", "icing": "III", "seismicity": "7"},
    "иркутск": {"wind": "III", "snow": "II", "icing": "III", "seismicity": "8"},
    "хабаровск": {"wind": "III", "snow": "II", "icing": "IV", "seismicity": "6"},
    "владивосток": {"wind": "IV", "snow": "III", "icing": "IV", "seismicity": "7"},
    "ярославль": {"wind": "I", "snow": "IV", "icing": "II", "seismicity": "5"},
    "махачкала": {"wind": "V", "snow": "II", "icing": "I", "seismicity": "8"},
    "томск": {"wind": "III", "snow": "IV", "icing": "III", "seismicity": "6"},
    "оренбург": {"wind": "III", "snow": "IV", "icing": "III", "seismicity": "6"},
    "кемерово": {"wind": "III", "snow": "IV", "icing": "III", "seismicity": "6"},
    "рязань": {"wind": "I", "snow": "III", "icing": "II", "seismicity": "5"},
    "астрахань": {"wind": "III", "snow": "I", "icing": "I", "seismicity": "6"},
    "набережные челны": {"wind": "II", "snow": "IV", "icing": "III", "seismicity": "6"},
    "пенза": {"wind": "II", "snow": "III", "icing": "II", "seismicity": "5"},
    "липецк": {"wind": "II", "snow": "III", "icing": "II", "seismicity": "5"},
    "тула": {"wind": "I", "snow": "III", "icing": "II", "seismicity": "5"},
    "киров": {"wind": "I", "snow": "V", "icing": "III", "seismicity": "5"},
    "чебоксары": {"wind": "I", "snow": "IV", "icing": "II", "seismicity": "5"},
    "калининград": {"wind": "II", "snow": "II", "icing": "I", "seismicity": "5"},
    "курск": {"wind": "II", "snow": "III", "icing": "II", "seismicity": "5"},
    "улан-удэ": {"wind": "III", "snow": "I", "icing": "III", "seismicity": "8"},
    "сочи": {"wind": "III", "snow": "II", "icing": "I", "seismicity": "8"},
    "мурманск": {"wind": "IV", "snow": "V", "icing": "IV", "seismicity": "5"},
    "архангельск": {"wind": "II", "snow": "IV", "icing": "III", "seismicity": "5"},
    "якутск": {"wind": "II", "snow": "II", "icing": "II", "seismicity": "7"},
    "грозный": {"wind": "IV", "snow": "II", "icing": "I", "seismicity": "8"},
    "петропавловск-камчатский": {"wind": "VII", "snow": "VII", "icing": "V", "seismicity": "9"},
    "южно-сахалинск": {"wind": "V", "snow": "VI", "icing": "IV", "seismicity": "8"},
    "норильск": {"wind": "V", "snow": "V", "icing": "IV", "seismicity": "5"},
}


def get_wind_regions() -> list[WindRegion]:
    return list(WIND_REGIONS)


def get_snow_regions() -> list[SnowRegion]:
    return list(SNOW_REGIONS)


def get_icing_regions() -> list[IcingRegion]:
    return list(ICING_REGIONS)


def find_wind_region(code: str) -> WindRegion | None:
    for r in WIND_REGIONS:
        if r.code.upper() == code.strip().upper():
            return r
    return None


def find_snow_region(code: str) -> SnowRegion | None:
    for r in SNOW_REGIONS:
        if r.code.upper() == code.strip().upper():
            return r
    return None


def find_icing_region(code: str) -> IcingRegion | None:
    for r in ICING_REGIONS:
        if r.code.upper() == code.strip().upper():
            return r
    return None


def lookup_locality(locality: str) -> dict[str, str] | None:
    key = locality.strip().lower()
    return LOCALITY_CLIMATE_DB.get(key)


def get_locality_names() -> list[str]:
    return sorted(LOCALITY_CLIMATE_DB.keys(), key=str.lower)


def autofill_loads_from_locality(locality: str) -> dict[str, float] | None:
    """Возвращает нагрузки по населённому пункту или None."""
    info = lookup_locality(locality)
    if info is None:
        return None
    result: dict[str, float] = {}
    wind = find_wind_region(info.get("wind", ""))
    if wind:
        result["wind_pressure_kpa"] = wind.pressure_kpa
    snow = find_snow_region(info.get("snow", ""))
    if snow:
        result["snow_load_kpa"] = snow.load_kpa
    icing = find_icing_region(info.get("icing", ""))
    if icing:
        result["icing_mm"] = icing.thickness_mm
    seis = info.get("seismicity")
    if seis:
        try:
            result["seismicity"] = float(seis)
        except ValueError:
            pass
    return result
