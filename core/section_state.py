from __future__ import annotations

import re

import pandas as pd

from core.point_utils import build_flag_mask

SECTION_BUILD_HEIGHT_TOLERANCE = 0.3
SECTION_NUMBERING_HEIGHT_TOLERANCE = 0.01

_LEGACY_SECTION_POINT_RE = re.compile(r"^S\d+(?:_P\d+)?_B\d+$")


def is_generated_section_name(name: object) -> bool:
    if name is None:
        return False
    return bool(_LEGACY_SECTION_POINT_RE.match(str(name).strip()))


def build_section_generated_mask(data: pd.DataFrame) -> pd.Series:
    explicit_mask = build_flag_mask(data, 'is_section_generated')
    if 'name' not in data.columns:
        return explicit_mask
    legacy_mask = data['name'].fillna('').astype(str).str.match(_LEGACY_SECTION_POINT_RE, na=False)
    return (explicit_mask | legacy_mask).reindex(data.index, fill_value=False)


def deduplicate_section_heights(
    heights: list[float],
    *,
    tolerance: float = SECTION_BUILD_HEIGHT_TOLERANCE,
) -> list[float]:
    result: list[float] = []
    for raw_height in sorted(float(height) for height in heights):
        if not result or abs(raw_height - result[-1]) > tolerance:
            result.append(raw_height)
    return result
