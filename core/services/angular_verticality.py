from __future__ import annotations

import copy
import json
import math
from collections.abc import Iterable
from typing import Any, Optional

import numpy as np
import pandas as pd

from core.calculations import calculate_local_coordinate_system
from core.normatives import get_vertical_tolerance
from core.section_operations import _resolve_section_center_xy
from core.services.verticality_sections import build_verticality_check_from_sections


class AngularVerticalityBuilder:
    def __init__(
        self,
        *,
        processed_results: dict[str, Any] | None = None,
        section_snapshots: list[dict[str, Any]] | None = None,
        primary_station_coords: tuple[float, float, float] | None = None,
        secondary_station_coords: tuple[float, float, float] | None = None,
        basis_metadata: dict[str, Any] | None = None,
    ) -> None:
        self.processed_results = processed_results or {}
        self.section_snapshots = copy.deepcopy(section_snapshots or [])
        self.primary_station_coords = primary_station_coords
        self.secondary_station_coords = secondary_station_coords
        self.basis_metadata = copy.deepcopy(basis_metadata or {})

    @staticmethod
    def _safe_int(value: Any, default: int | None = None) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _make_section_key(section_num: int | None, height: float | None) -> str:
        try:
            if section_num is not None and not pd.isna(section_num):
                return f"section:{int(section_num)}"
        except (TypeError, ValueError):
            pass
        if height is None:
            return "section:unknown"
        return f"height:{float(height):.6f}"

    def _default_payload(self) -> dict[str, Any]:
        return {
            "x": [],
            "y": [],
            "rows_by_axis": {"x": [], "y": []},
            "sections": [],
            "basis": copy.deepcopy(self.basis_metadata),
            "complete": False,
            "vertical_check": build_verticality_check_from_sections([]),
        }

    def _get_station_for_axis(self, axis: str) -> tuple[float, float, float] | None:
        return self.secondary_station_coords if (axis or "x").lower() == "y" else self.primary_station_coords

    def build_payload(self, tower_data: pd.DataFrame | None) -> dict[str, Any]:
        payload = self._default_payload()
        tower_df = tower_data.copy() if isinstance(tower_data, pd.DataFrame) else pd.DataFrame()
        section_entries = self._prepare_angular_sections(tower_df)
        rows_by_axis: dict[str, list[dict[str, Any]]] = {"x": [], "y": []}
        axis_sections: dict[str, dict[str, dict[str, Any]]] = {"x": {}, "y": {}}

        basis = copy.deepcopy(self.basis_metadata)
        payload["basis"] = basis
        has_required_stations = bool(basis.get("has_required_stations"))
        has_authoritative_stations = bool(basis.get("has_authoritative_stations", has_required_stations))
        processed_fallback_sections = self._build_sections_from_processed_results(section_entries)
        snapshot_fallback_sections = self._build_sections_from_section_entries(section_entries)
        fallback_sections = processed_fallback_sections or snapshot_fallback_sections

        for axis in ("x", "y"):
            station_coords = self._get_station_for_axis(axis)
            if station_coords is None:
                continue

            raw_rows: list[dict[str, Any]] = []
            for section in section_entries:
                points_df = section.get("points_df")
                if points_df is None or points_df.empty or len(points_df) < 2:
                    continue
                raw_rows.extend(
                    self._build_axis_rows_from_points(
                        points_df,
                        station_coords,
                        section_label=str(section.get("section_label", "")),
                        section_num=section.get("section_num"),
                        part_num=section.get("part_num"),
                        part_memberships=section.get("part_memberships"),
                        section_height=section.get("height"),
                        belt_sequence=section.get("belt_sequence"),
                        preferred_center_xy=section.get("preferred_center_xy"),
                    )
                )

            finalized_rows, finalized_sections = self._finalize_axis_rows(axis, station_coords, raw_rows)
            rows_by_axis[axis] = finalized_rows
            axis_sections[axis] = finalized_sections

        if has_required_stations:
            station_sections = self._build_sections_from_axis_payload(
                axis_sections,
                authoritative=has_authoritative_stations,
            )
            if has_authoritative_stations:
                merged_sections = self._merge_station_sections_with_fallback(station_sections, fallback_sections)
            else:
                merged_sections = processed_fallback_sections or station_sections or snapshot_fallback_sections
        else:
            merged_sections = fallback_sections

        payload["rows_by_axis"] = rows_by_axis
        payload["x"] = rows_by_axis["x"]
        payload["y"] = rows_by_axis["y"]
        payload["sections"] = merged_sections
        self._synchronize_axis_rows_with_sections(payload)
        payload["complete"] = has_authoritative_stations and bool(merged_sections) and all(
            bool(item.get("basis_complete")) for item in merged_sections
        )
        payload["vertical_check"] = build_verticality_check_from_sections(merged_sections)
        return payload

    @staticmethod
    def _ensure_section_numbers(sections: list[dict[str, Any]]) -> None:
        if not sections:
            return

        height_tolerance = 0.01
        section_num = 0
        seen_heights: list[float] = []

        for section in sections:
            section_height = float(section.get("height", 0.0) or 0.0)
            existing_section_num = AngularVerticalityBuilder._safe_int(section.get("section_num"))
            if existing_section_num is not None:
                seen_heights.append(section_height)
                section["section_num"] = existing_section_num
                section_num = max(section_num, existing_section_num + 1)
                continue

            matched_height = None
            for seen_height in seen_heights:
                if abs(section_height - seen_height) <= height_tolerance:
                    matched_height = seen_height
                    break

            if matched_height is None:
                section["section_num"] = section_num
                seen_heights.append(section_height)
                section_num += 1
            else:
                section["section_num"] = max(section_num - 1, 0)

    @staticmethod
    def _decode_part_memberships(value: Any) -> list[int]:
        if value is None:
            return []
        if isinstance(value, float) and math.isnan(value):
            return []
        if isinstance(value, str):
            try:
                decoded = json.loads(value)
            except Exception:
                return []
        elif isinstance(value, (list, tuple, set)):
            decoded = list(value)
        else:
            return []

        result: list[int] = []
        for item in decoded:
            safe_value = AngularVerticalityBuilder._safe_int(item)
            if safe_value is not None and safe_value not in result:
                result.append(safe_value)
        return result

    def _extract_part_memberships(self, source: Any) -> list[int]:
        memberships = set()

        if isinstance(source, pd.DataFrame):
            if "tower_part_memberships" in source.columns:
                for value in source["tower_part_memberships"].dropna():
                    memberships.update(self._decode_part_memberships(value))
            if not memberships and "tower_part" in source.columns:
                for value in source["tower_part"].dropna().tolist():
                    safe_value = self._safe_int(value)
                    if safe_value is not None:
                        memberships.add(safe_value)
            if not memberships and "segment" in source.columns:
                for value in source["segment"].dropna().tolist():
                    safe_value = self._safe_int(value)
                    if safe_value is not None:
                        memberships.add(safe_value)
            return sorted(memberships)

        if isinstance(source, dict):
            memberships.update(self._decode_part_memberships(source.get("tower_part_memberships")))
            if not memberships:
                safe_value = self._safe_int(source.get("tower_part"))
                if safe_value is not None:
                    memberships.add(safe_value)
            if not memberships:
                safe_value = self._safe_int(source.get("segment"))
                if safe_value is not None:
                    memberships.add(safe_value)

        return sorted(memberships)

    @staticmethod
    def _section_height_tolerance(entries: list[dict[str, Any]]) -> float:
        heights = sorted(
            {
                round(float(entry.get("height", 0.0) or 0.0), 6)
                for entry in entries
                if entry.get("height") is not None
            }
        )
        if len(heights) > 1:
            min_step = min(abs(heights[idx] - heights[idx - 1]) for idx in range(1, len(heights)))
            return max(0.05, min(1.5, float(min_step) * 0.6))
        return 0.3

    def _match_section_entry_by_height(
        self,
        height: float,
        section_entries: list[dict[str, Any]],
        tolerance: float | None = None,
    ) -> dict[str, Any] | None:
        if not section_entries:
            return None
        tolerance = self._section_height_tolerance(section_entries) if tolerance is None else tolerance

        matched_entry = None
        matched_diff = float("inf")
        for entry in section_entries:
            entry_height = entry.get("height")
            if entry_height is None:
                continue
            diff = abs(float(entry_height) - float(height))
            if diff <= tolerance and diff < matched_diff:
                matched_entry = entry
                matched_diff = diff
        return matched_entry

    @staticmethod
    def _infer_mm_scale(series: pd.Series) -> float:
        numeric = pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)
        valid = numeric[np.isfinite(numeric)]
        if valid.size == 0:
            return 1.0
        return 1000.0 if float(np.nanmax(np.abs(valid))) < 2.0 else 1.0

    @staticmethod
    def _section_snapshot_mean_z(section: dict[str, Any]) -> float | None:
        points = section.get("points", []) if isinstance(section, dict) else []
        if not isinstance(points, (list, tuple)) or not points:
            return None

        z_values: list[float] = []
        for point in points:
            if not isinstance(point, (list, tuple)) or len(point) < 3:
                continue
            try:
                z_value = float(point[2])
            except (TypeError, ValueError):
                continue
            if np.isfinite(z_value):
                z_values.append(z_value)

        if not z_values:
            return None
        return float(np.mean(z_values))

    @classmethod
    def _section_height_candidates(cls, section: dict[str, Any]) -> list[float]:
        candidates: list[float] = []
        raw_values = [
            section.get("center_z"),
            section.get("height"),
            cls._section_snapshot_mean_z(section),
        ]
        for raw_value in raw_values:
            try:
                candidate = float(raw_value)
            except (TypeError, ValueError):
                continue
            if not np.isfinite(candidate):
                continue
            if any(abs(existing - candidate) <= 1e-6 for existing in candidates):
                continue
            candidates.append(candidate)
        return candidates

    @classmethod
    def _section_sort_height(cls, section: dict[str, Any]) -> float:
        candidates = cls._section_height_candidates(section)
        return candidates[0] if candidates else 0.0

    def _match_section_points_from_tower_data(
        self,
        section: dict[str, Any],
        tower_df: pd.DataFrame,
        tolerance: float = 0.3,
    ) -> pd.DataFrame:
        if tower_df is None or tower_df.empty or "z" not in tower_df.columns:
            return pd.DataFrame(columns=["x", "y", "z", "belt"])

        section_heights = self._section_height_candidates(section)
        if not section_heights:
            return pd.DataFrame(columns=["x", "y", "z", "belt"])

        numeric_z = pd.to_numeric(tower_df["z"], errors="coerce")
        section_memberships = self._extract_part_memberships(section)
        part_mask = pd.Series(True, index=tower_df.index)
        if section_memberships:
            part_mask = pd.Series(False, index=tower_df.index)
            if "tower_part_memberships" in tower_df.columns:
                for membership in section_memberships:
                    encoded = tower_df["tower_part_memberships"].map(
                        lambda value: membership in self._decode_part_memberships(value)
                    )
                    part_mask |= encoded.fillna(False)
            if "tower_part" in tower_df.columns:
                numeric_parts = pd.to_numeric(tower_df["tower_part"], errors="coerce")
                part_mask |= numeric_parts.isin(section_memberships)

        belt_sequence = section.get("belt_nums", []) if isinstance(section.get("belt_nums"), (list, tuple)) else []
        belt_mask = pd.Series(True, index=tower_df.index)
        if belt_sequence and "belt" in tower_df.columns:
            belt_values = [self._safe_int(value) for value in belt_sequence]
            belt_values = [value for value in belt_values if value is not None]
            if belt_values:
                numeric_belts = pd.to_numeric(tower_df["belt"], errors="coerce")
                belt_mask = numeric_belts.isin(belt_values)

        points_df = pd.DataFrame(columns=["x", "y", "z", "belt"])
        for section_height in section_heights:
            mask = numeric_z.notna() & (numeric_z.sub(section_height).abs() <= float(tolerance))
            if section_memberships and part_mask.any():
                mask &= part_mask
            if belt_sequence and "belt" in tower_df.columns and (mask & belt_mask).any():
                mask &= belt_mask
            candidate_df = tower_df[mask].copy()
            if candidate_df.empty:
                continue
            points_df = candidate_df
            break

        if points_df.empty:
            return pd.DataFrame(columns=["x", "y", "z", "belt"])

        if "belt" not in points_df.columns:
            points_df["belt"] = [None] * len(points_df)
            return points_df

        if belt_sequence:
            belt_order = {
                belt_num: order
                for order, belt_num in enumerate(
                    value for value in (self._safe_int(item) for item in belt_sequence) if value is not None
                )
            }
            numeric_belts = pd.to_numeric(points_df["belt"], errors="coerce")
            points_df = (
                points_df.assign(
                    _belt_order=numeric_belts.map(
                        lambda value: belt_order.get(self._safe_int(value), len(belt_order))
                    )
                )
                .sort_values(by=["_belt_order", "z"], ascending=[True, True])
                .drop(columns=["_belt_order"])
            )

        return points_df

    @staticmethod
    def _build_section_points_df_from_snapshot(section: dict[str, Any]) -> pd.DataFrame:
        points = section.get("points", []) or []
        points_df = pd.DataFrame(points, columns=["x", "y", "z"]) if points else pd.DataFrame(columns=["x", "y", "z"])
        belt_sequence = section.get("belt_nums", []) if isinstance(section.get("belt_nums"), (list, tuple)) else None
        if not points_df.empty:
            if belt_sequence and len(belt_sequence) == len(points_df):
                points_df["belt"] = list(belt_sequence)
            else:
                points_df["belt"] = [None] * len(points_df)
        return points_df

    @staticmethod
    def _resolve_points_center_xy(
        points_df: pd.DataFrame | None,
        fallback_center_xy: tuple[float, float] | None = None,
    ) -> tuple[float, float] | None:
        if points_df is None or points_df.empty or "x" not in points_df.columns or "y" not in points_df.columns:
            return fallback_center_xy

        selected_rows = [row for _, row in points_df.iterrows()]
        points = [
            (float(row["x"]), float(row["y"]), float(row["z"]))
            for _, row in points_df.iterrows()
            if pd.notna(row.get("x")) and pd.notna(row.get("y")) and pd.notna(row.get("z"))
        ]
        if not points:
            return fallback_center_xy

        try:
            center_xy = _resolve_section_center_xy(selected_rows, points)
            return (float(center_xy[0]), float(center_xy[1]))
        except Exception:
            mean_xy = points_df[["x", "y"]].mean().to_numpy(dtype=float)
            return (float(mean_xy[0]), float(mean_xy[1]))

    def _prepare_angular_sections(self, tower_data: pd.DataFrame | None) -> list[dict[str, Any]]:
        section_entries: list[dict[str, Any]] = []
        tower_df = tower_data.copy() if isinstance(tower_data, pd.DataFrame) else pd.DataFrame()

        if self.section_snapshots:
            sections = sorted(self.section_snapshots, key=self._section_sort_height)
            self._ensure_section_numbers(sections)
            matched_current_sections = 0

            for index, section in enumerate(sections):
                points_df = self._match_section_points_from_tower_data(section, tower_df, tolerance=0.3)
                if not points_df.empty:
                    matched_current_sections += 1
                elif tower_df.empty:
                    points_df = self._build_section_points_df_from_snapshot(section)
                else:
                    continue

                belt_sequence = section.get("belt_nums", []) if isinstance(section.get("belt_nums"), (list, tuple)) else None
                section_num = self._safe_int(section.get("section_num"), index)
                part_memberships = self._extract_part_memberships(section)
                snapshot_center_xy = None
                raw_center_xy = section.get("center_xy")
                if isinstance(raw_center_xy, (list, tuple)) and len(raw_center_xy) >= 2:
                    try:
                        snapshot_center_xy = (float(raw_center_xy[0]), float(raw_center_xy[1]))
                    except (TypeError, ValueError):
                        snapshot_center_xy = None
                preferred_center_xy = self._resolve_points_center_xy(points_df, snapshot_center_xy)
                if not points_df.empty and "z" in points_df.columns:
                    section_height = float(points_df["z"].mean())
                else:
                    section_height = self._section_sort_height(section)
                section_entries.append(
                    {
                        "section_key": self._make_section_key(section_num, section_height),
                        "section_num": section_num,
                        "section_label": section.get("name") or section.get("label") or str(section_num),
                        "height": section_height,
                        "points_df": points_df,
                        "belt_sequence": belt_sequence,
                        "part_memberships": part_memberships,
                        "part_num": part_memberships[0] if part_memberships else None,
                        "preferred_center_xy": preferred_center_xy,
                        "points_count": int(len(points_df)) if points_df is not None else 0,
                    }
                )
            if section_entries and matched_current_sections:
                return section_entries

        if tower_df.empty or "z" not in tower_df.columns:
            return []

        numeric_z = pd.to_numeric(tower_df["z"], errors="coerce")
        heights = sorted(numeric_z.dropna().unique())
        for index, height in enumerate(heights):
            points_df = tower_df[np.isclose(numeric_z, height)].copy()
            if points_df.empty:
                continue
            if "belt" not in points_df.columns:
                points_df["belt"] = [None] * len(points_df)
            part_memberships = self._extract_part_memberships(points_df)
            preferred_center_xy = self._resolve_points_center_xy(points_df)
            section_entries.append(
                {
                    "section_key": self._make_section_key(index, height),
                    "section_num": index,
                    "section_label": str(index),
                    "height": float(height),
                    "points_df": points_df,
                    "belt_sequence": None,
                    "part_memberships": part_memberships,
                    "part_num": part_memberships[0] if part_memberships else None,
                    "preferred_center_xy": preferred_center_xy,
                    "points_count": int(len(points_df)),
                }
            )
        return section_entries

    def _build_sections_from_section_entries(self, section_entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not section_entries:
            return []

        center_rows: list[dict[str, Any]] = []
        for entry in section_entries:
            center_xy = entry.get("preferred_center_xy")
            if center_xy is None:
                center_xy = self._resolve_points_center_xy(entry.get("points_df"))
            if center_xy is None:
                continue

            height = entry.get("height")
            if height is None:
                points_df = entry.get("points_df")
                if isinstance(points_df, pd.DataFrame) and not points_df.empty and "z" in points_df.columns:
                    height = float(points_df["z"].mean())
                else:
                    height = 0.0

            center_rows.append(
                {
                    "section_key": entry.get("section_key"),
                    "section_num": entry.get("section_num"),
                    "section_label": entry.get("section_label"),
                    "height": float(height),
                    "center_xy": (float(center_xy[0]), float(center_xy[1])),
                    "part_num": entry.get("part_num"),
                    "part_memberships": list(entry.get("part_memberships", []) or []),
                    "points_count": entry.get("points_count"),
                }
            )

        return self._build_axis_based_sections_from_centers(
            center_rows,
            source="sections",
            reference_mode="best_fit",
        )

    def _build_axis_based_sections_from_centers(
        self,
        center_rows: list[dict[str, Any]],
        *,
        source: str,
        reference_mode: str = "best_fit",
    ) -> list[dict[str, Any]]:
        if not center_rows:
            return []

        centers_df = pd.DataFrame(
            [
                {
                    "section_key": row.get("section_key"),
                    "section_num": row.get("section_num"),
                    "section_label": row.get("section_label"),
                    "x": float(row["center_xy"][0]),
                    "y": float(row["center_xy"][1]),
                    "z": float(row.get("height", 0.0) or 0.0),
                    "tower_part": row.get("part_num"),
                    "tower_part_memberships": json.dumps(row.get("part_memberships", []) or [], ensure_ascii=False),
                }
                for row in center_rows
                if row.get("center_xy") is not None
            ]
        )
        if centers_df.empty:
            return []

        centers_df = centers_df.sort_values("z").reset_index(drop=True)
        primary_station = self._get_station_for_axis("x")
        standing_point = {"x": 0.0, "y": 0.0, "z": 0.0}
        if primary_station is not None:
            standing_point = {
                "x": float(primary_station[0]),
                "y": float(primary_station[1]),
                "z": float(primary_station[2]),
            }

        local_cs = calculate_local_coordinate_system(centers_df, standing_point, None)
        x_axis = np.array(local_cs.get("x_axis", (1.0, 0.0, 0.0)), dtype=float)
        y_axis = np.array(local_cs.get("y_axis", (0.0, 1.0, 0.0)), dtype=float)

        baseline_by_part: dict[int, dict[str, Any]] = {}
        for row in sorted(
            center_rows,
            key=lambda item: (
                float(item.get("height", 0.0) or 0.0),
                self._safe_int(item.get("section_num"), 10**9),
            ),
        ):
            center_xy = row.get("center_xy")
            if center_xy is None:
                continue
            part_key = int(row["part_num"]) if row.get("part_num") is not None else 0
            baseline_by_part.setdefault(part_key, row)

        basis_complete = reference_mode == "baseline_by_part"
        allow_station_component_override = source == "stations" and basis_complete
        result: list[dict[str, Any]] = []

        for row in sorted(
            center_rows,
            key=lambda item: (
                float(item.get("height", 0.0) or 0.0),
                self._safe_int(item.get("section_num"), 10**9),
            ),
        ):
            center_xy = row.get("center_xy")
            if center_xy is None:
                continue

            height = float(row.get("height", 0.0) or 0.0)
            part_key = int(row["part_num"]) if row.get("part_num") is not None else 0
            baseline_row = baseline_by_part.get(part_key)
            baseline_center_xy = baseline_row.get("center_xy") if baseline_row is not None else None
            if baseline_center_xy is None:
                baseline_center_xy = center_xy

            axis_point_xy = (
                float(baseline_center_xy[0]),
                float(baseline_center_xy[1]),
            )
            current_center_xy = np.array([float(center_xy[0]), float(center_xy[1]), 0.0], dtype=float)
            baseline_center_xyz = np.array(
                [float(baseline_center_xy[0]), float(baseline_center_xy[1]), 0.0],
                dtype=float,
            )

            shift_vector = current_center_xy - baseline_center_xyz
            resolved_shift_xy_mm = row.get("resolved_shift_xy_mm")
            if isinstance(resolved_shift_xy_mm, (list, tuple)) and len(resolved_shift_xy_mm) >= 2:
                try:
                    shift_vector = np.array(
                        [
                            float(resolved_shift_xy_mm[0]) / 1000.0,
                            float(resolved_shift_xy_mm[1]) / 1000.0,
                            0.0,
                        ],
                        dtype=float,
                    )
                except (TypeError, ValueError):
                    pass

            local_deviation_x_mm = float(np.dot(shift_vector, x_axis) * 1000.0)
            local_deviation_y_mm = float(np.dot(shift_vector, y_axis) * 1000.0)
            total_deviation_mm = float(np.linalg.norm(shift_vector[:2]) * 1000.0)

            deviation_x_mm = local_deviation_x_mm
            deviation_y_mm = local_deviation_y_mm
            if allow_station_component_override:
                station_deviation_x = row.get("station_deviation_x")
                station_deviation_y = row.get("station_deviation_y")
                if station_deviation_x is not None:
                    deviation_x_mm = float(station_deviation_x)
                if station_deviation_y is not None:
                    deviation_y_mm = float(station_deviation_y)

            merged_row = dict(row)
            merged_row.update(
                {
                    "axis_point_xy": axis_point_xy,
                    "local_deviation_x": local_deviation_x_mm,
                    "local_deviation_y": local_deviation_y_mm,
                    "deviation_x": deviation_x_mm,
                    "deviation_y": deviation_y_mm,
                    "total_deviation": total_deviation_mm,
                    "deviation": total_deviation_mm,
                    "tolerance": float(get_vertical_tolerance(height) * 1000.0),
                    "source": source,
                    "basis_complete": basis_complete,
                }
            )
            result.append(merged_row)

        return result

    def _build_sections_from_processed_results(self, section_entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        results = self.processed_results
        if not results:
            return []

        centers = results.get("centers")
        if centers is None:
            return []

        if isinstance(centers, pd.DataFrame):
            centers_df = centers.copy()
        else:
            try:
                centers_df = pd.DataFrame(centers)
            except Exception:
                return []

        if centers_df.empty:
            return []

        height_col = next((candidate for candidate in ("z", "height", "belt_height") if candidate in centers_df.columns), None)
        if height_col is None or "x" not in centers_df.columns or "y" not in centers_df.columns:
            return []

        tolerance = self._section_height_tolerance(section_entries)
        existing_nums = [self._safe_int(entry.get("section_num")) for entry in section_entries]
        existing_nums = [num for num in existing_nums if num is not None]
        next_section_num = (max(existing_nums) + 1) if existing_nums else 0
        center_rows: list[dict[str, Any]] = []

        for _, row in centers_df.sort_values(height_col).iterrows():
            try:
                height = float(row[height_col])
                center_xy = (float(row.get("x", 0.0) or 0.0), float(row.get("y", 0.0) or 0.0))
            except (TypeError, ValueError):
                continue

            matched_entry = self._match_section_entry_by_height(height, section_entries, tolerance=tolerance)
            if matched_entry is not None:
                section_num = matched_entry.get("section_num")
                section_label = matched_entry.get("section_label")
                part_num = matched_entry.get("part_num")
                part_memberships = matched_entry.get("part_memberships", [])
            else:
                section_num = next_section_num
                section_label = str(section_num)
                part_memberships = self._extract_part_memberships(row)
                part_num = part_memberships[0] if part_memberships else self._safe_int(row.get("tower_part"))
                next_section_num += 1

            center_rows.append(
                {
                    "section_key": self._make_section_key(section_num, height),
                    "section_num": section_num,
                    "section_label": section_label,
                    "height": height,
                    "center_xy": center_xy,
                    "part_num": part_num,
                    "part_memberships": list(part_memberships),
                }
            )

        return self._build_axis_based_sections_from_centers(
            center_rows,
            source="processed",
            reference_mode="best_fit",
        )

    @staticmethod
    def _bearing_seconds_between_points(from_xy: np.ndarray, to_xy: np.ndarray) -> float | None:
        vector = np.asarray(to_xy, dtype=float) - np.asarray(from_xy, dtype=float)
        norm = float(np.linalg.norm(vector))
        if norm < 1e-9:
            return None
        angle_deg = math.degrees(math.atan2(vector[1], vector[0])) % 360.0
        return angle_deg * 3600.0

    @staticmethod
    def _station_axis_projection_mm(
        station_xy: np.ndarray,
        reference_xy: np.ndarray,
        actual_xy: np.ndarray,
    ) -> float | None:
        reference_vec = np.asarray(reference_xy, dtype=float) - np.asarray(station_xy, dtype=float)
        ref_norm = float(np.linalg.norm(reference_vec))
        if ref_norm < 1e-9:
            return None
        view_unit = reference_vec / ref_norm
        normal_unit = np.array([-view_unit[1], view_unit[0]], dtype=float)
        residual_xy = np.asarray(actual_xy, dtype=float) - np.asarray(reference_xy, dtype=float)
        return float(np.dot(residual_xy, normal_unit) * 1000.0)

    def _synchronize_axis_rows_with_sections(self, payload: dict[str, Any]) -> None:
        sections = payload.get("sections")
        if not isinstance(sections, list) or not sections:
            return

        section_map = {
            section.get("section_key"): section
            for section in sections
            if isinstance(section, dict) and section.get("section_key")
        }
        if not section_map:
            return

        has_both_axes = all(self._get_station_for_axis(axis) is not None for axis in ("x", "y"))
        section_axis_values: dict[str, dict[str, float]] = {}

        for axis in ("x", "y"):
            station_coords = self._get_station_for_axis(axis)
            if station_coords is None:
                continue

            station_xy = np.array([float(station_coords[0]), float(station_coords[1])], dtype=float)
            rows = payload.get("rows_by_axis", {}).get(axis, [])
            for row in rows:
                section = section_map.get(row.get("section_key"))
                if section is None:
                    continue

                center_xy = section.get("center_xy")
                axis_point_xy = section.get("axis_point_xy")
                if center_xy is None or axis_point_xy is None:
                    continue

                actual_xy = np.asarray(center_xy, dtype=float)
                reference_xy = np.asarray(axis_point_xy, dtype=float)
                measured_sec = self._bearing_seconds_between_points(station_xy, actual_xy)
                reference_sec = self._bearing_seconds_between_points(station_xy, reference_xy)
                delta_mm = self._station_axis_projection_mm(station_xy, reference_xy, actual_xy)
                if measured_sec is None or reference_sec is None or delta_mm is None:
                    continue

                delta_sec = self._normalized_angle_diff(measured_sec, reference_sec)
                row["reference_center_sec"] = float(reference_sec)
                row["center_str"] = self._format_angle_seconds(reference_sec)
                row["delta_sec"] = float(delta_sec)
                row["delta_str"] = '0.00"' if abs(delta_sec) < 1e-9 else f"{float(delta_sec):+.2f}\""
                row["delta_mm"] = float(delta_mm)
                row["delta_mm_str"] = f"{float(delta_mm):+.1f}"

                axis_values = section_axis_values.setdefault(str(section.get("section_key")), {})
                axis_values[axis] = float(delta_mm)

        if has_both_axes:
            for section in sections:
                axis_values = section_axis_values.get(str(section.get("section_key")))
                if not axis_values:
                    continue
                if "x" in axis_values:
                    section["deviation_x"] = float(axis_values["x"])
                if "y" in axis_values:
                    section["deviation_y"] = float(axis_values["y"])

    def _finalize_axis_rows(
        self,
        axis: str,
        station_coords: tuple[float, float, float],
        raw_rows: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
        if not raw_rows:
            return [], {}

        station_xy = np.array([float(station_coords[0]), float(station_coords[1])], dtype=float)
        section_map: dict[str, dict[str, Any]] = {}

        for row in raw_rows:
            section_key = row.get("section_key")
            if section_key is None:
                continue
            if section_key not in section_map:
                section_map[section_key] = {
                    "section_key": section_key,
                    "section_num": row.get("section_num"),
                    "section_label": row.get("section_label"),
                    "height": float(row.get("height", 0.0) or 0.0),
                    "center_sec": row.get("center_sec"),
                    "center_xy": row.get("center_xy"),
                    "center_range_m": row.get("center_range_m"),
                    "part_num": row.get("part_num"),
                    "part_memberships": list(row.get("part_memberships", []) or []),
                    "center_ranges": [],
                }
            center_range_m = row.get("center_range_m")
            if center_range_m is not None:
                section_map[section_key]["center_ranges"].append(float(center_range_m))

        for section in section_map.values():
            center_ranges = [value for value in section.pop("center_ranges", []) if value is not None]
            if center_ranges:
                section["center_range_m"] = float(np.mean(center_ranges))

        baseline_by_part: dict[int, dict[str, Any]] = {}
        for section in section_map.values():
            part_key = int(section["part_num"]) if section.get("part_num") is not None else 0
            current = baseline_by_part.get(part_key)
            if current is None or section["height"] < current["height"]:
                baseline_by_part[part_key] = section

        finalized_rows: list[dict[str, Any]] = []
        axis_sections: dict[str, dict[str, Any]] = {}

        for row in sorted(
            raw_rows,
            key=lambda item: (
                float(item.get("height", 0.0) or 0.0),
                self._safe_int(item.get("section_num"), 10**9),
                str(item.get("belt", "")),
            ),
        ):
            section_key = row.get("section_key")
            section = section_map.get(section_key)
            if section is None:
                continue

            part_key = int(section["part_num"]) if section.get("part_num") is not None else 0
            baseline = baseline_by_part.get(part_key)
            center_sec = section.get("center_sec")
            baseline_center_sec = baseline.get("center_sec") if baseline is not None else None
            center_xy = np.asarray(section.get("center_xy", (0.0, 0.0)), dtype=float)
            baseline_xy = np.asarray(baseline.get("center_xy", (0.0, 0.0)), dtype=float) if baseline is not None else None
            center_range_m = section.get("center_range_m")

            delta_sec = None
            delta_mm = None
            normal_xy = None

            if baseline is not None and center_sec is not None and baseline_center_sec is not None:
                delta_sec = self._normalized_angle_diff(float(center_sec), float(baseline_center_sec))
                baseline_view = baseline_xy - station_xy
                baseline_norm = float(np.linalg.norm(baseline_view))
                if baseline_norm >= 1e-9:
                    view_unit = baseline_view / baseline_norm
                    normal_xy = np.array([-view_unit[1], view_unit[0]], dtype=float)
                    if section_key == baseline["section_key"]:
                        delta_sec = 0.0
                        delta_mm = 0.0
                    elif center_range_m is not None:
                        delta_rad = math.radians(float(delta_sec) / 3600.0)
                        delta_mm = float(math.sin(delta_rad) * float(center_range_m) * 1000.0)
                elif section_key == baseline["section_key"]:
                    delta_sec = 0.0
                    delta_mm = 0.0

            row_copy = dict(row)
            row_copy["axis"] = axis
            row_copy["center_sec"] = center_sec
            row_copy["center_range_m"] = center_range_m
            row_copy["center_str"] = self._format_angle_seconds(center_sec)
            if delta_sec is None:
                row_copy["delta_sec"] = None
                row_copy["delta_str"] = "—"
            else:
                row_copy["delta_sec"] = float(delta_sec)
                row_copy["delta_str"] = '0.00"' if abs(delta_sec) < 1e-9 else f"{float(delta_sec):+.2f}\""
            if delta_mm is None:
                row_copy["delta_mm"] = None
                row_copy["delta_mm_str"] = "—"
            else:
                row_copy["delta_mm"] = float(delta_mm)
                row_copy["delta_mm_str"] = f"{float(delta_mm):+.1f}"
            finalized_rows.append(row_copy)

            axis_sections[section_key] = {
                "section_key": section_key,
                "section_num": section.get("section_num"),
                "section_label": section.get("section_label"),
                "height": section.get("height"),
                "deviation_mm": float(delta_mm) if delta_mm is not None else None,
                "center_xy": tuple(center_xy.tolist()),
                "center_sec": center_sec,
                "center_range_m": float(center_range_m) if center_range_m is not None else None,
                "part_num": section.get("part_num"),
                "part_memberships": list(section.get("part_memberships", []) or []),
                "normal_xy": tuple(normal_xy.tolist()) if normal_xy is not None else None,
                "station_coords": [float(station_coords[0]), float(station_coords[1]), float(station_coords[2])],
                "axis": axis,
                "basis_complete": normal_xy is not None and delta_mm is not None,
            }

        return finalized_rows, axis_sections

    @staticmethod
    def _direction_from_angle_seconds(angle_sec: float | None) -> np.ndarray | None:
        if angle_sec is None:
            return None
        angle_rad = math.radians(float(angle_sec) / 3600.0)
        return np.array([math.cos(angle_rad), math.sin(angle_rad)], dtype=float)

    @staticmethod
    def _solve_station_shift(
        section_x: dict[str, Any] | None,
        section_y: dict[str, Any] | None,
    ) -> np.ndarray | None:
        if section_x is None or section_y is None:
            return None
        if section_x.get("deviation_mm") is None or section_y.get("deviation_mm") is None:
            return None
        if section_x.get("normal_xy") is None or section_y.get("normal_xy") is None:
            return None

        matrix = np.array([section_x["normal_xy"], section_y["normal_xy"]], dtype=float)
        rhs = np.array(
            [
                float(section_x["deviation_mm"]) / 1000.0,
                float(section_y["deviation_mm"]) / 1000.0,
            ],
            dtype=float,
        )
        if abs(float(np.linalg.det(matrix))) < 1e-8:
            return None
        try:
            return np.linalg.solve(matrix, rhs)
        except np.linalg.LinAlgError:
            return None

    def _intersect_station_rays(
        self,
        section_x: dict[str, Any] | None,
        section_y: dict[str, Any] | None,
    ) -> np.ndarray | None:
        if section_x is None or section_y is None:
            return None
        if section_x.get("center_sec") is None or section_y.get("center_sec") is None:
            return None
        if section_x.get("station_coords") is None or section_y.get("station_coords") is None:
            return None

        station_x = np.array(section_x["station_coords"][:2], dtype=float)
        station_y = np.array(section_y["station_coords"][:2], dtype=float)
        direction_x = self._direction_from_angle_seconds(section_x.get("center_sec"))
        direction_y = self._direction_from_angle_seconds(section_y.get("center_sec"))
        if direction_x is None or direction_y is None:
            return None

        matrix = np.column_stack((direction_x, -direction_y))
        if abs(float(np.linalg.det(matrix))) < 1e-8:
            return None
        rhs = station_y - station_x
        try:
            parameters = np.linalg.solve(matrix, rhs)
        except np.linalg.LinAlgError:
            return None

        return station_x + float(parameters[0]) * direction_x

    def _build_sections_from_axis_payload(
        self,
        axis_sections: dict[str, dict[str, dict[str, Any]]],
        *,
        authoritative: bool = True,
    ) -> list[dict[str, Any]]:
        sections_x = axis_sections.get("x", {})
        sections_y = axis_sections.get("y", {})
        all_keys = set(sections_x.keys()) | set(sections_y.keys())
        result: list[dict[str, Any]] = []
        baseline_by_part_x: dict[int, dict[str, Any]] = {}
        baseline_by_part_y: dict[int, dict[str, Any]] = {}

        for section in sections_x.values():
            part_key = int(section["part_num"]) if section.get("part_num") is not None else 0
            current = baseline_by_part_x.get(part_key)
            if current is None or float(section.get("height", 0.0) or 0.0) < float(current.get("height", 0.0) or 0.0):
                baseline_by_part_x[part_key] = section

        for section in sections_y.values():
            part_key = int(section["part_num"]) if section.get("part_num") is not None else 0
            current = baseline_by_part_y.get(part_key)
            if current is None or float(section.get("height", 0.0) or 0.0) < float(current.get("height", 0.0) or 0.0):
                baseline_by_part_y[part_key] = section

        for section_key in sorted(
            all_keys,
            key=lambda key: (
                float((sections_x.get(key) or sections_y.get(key) or {}).get("height", 0.0) or 0.0),
                self._safe_int((sections_x.get(key) or sections_y.get(key) or {}).get("section_num"), 10**9),
            ),
        ):
            section_x = sections_x.get(section_key)
            section_y = sections_y.get(section_key)
            meta = section_x or section_y
            if meta is None:
                continue

            part_key = int(meta["part_num"]) if meta.get("part_num") is not None else 0
            baseline_section_x = baseline_by_part_x.get(part_key)
            baseline_section_y = baseline_by_part_y.get(part_key)

            current_center_xy = self._intersect_station_rays(section_x, section_y)
            baseline_center_xy = self._intersect_station_rays(baseline_section_x, baseline_section_y)
            if current_center_xy is not None and baseline_center_xy is not None:
                shift_xy = current_center_xy - baseline_center_xy
            else:
                shift_xy = self._solve_station_shift(section_x, section_y)
            if current_center_xy is None and shift_xy is not None and baseline_center_xy is not None:
                current_center_xy = baseline_center_xy + shift_xy
            if current_center_xy is None and meta.get("center_xy") is not None:
                current_center_xy = np.asarray(meta.get("center_xy"), dtype=float)

            height = float(meta.get("height", 0.0) or 0.0)
            result.append(
                {
                    "section_key": section_key,
                    "section_num": meta.get("section_num"),
                    "section_label": meta.get("section_label"),
                    "height": height,
                    "part_num": meta.get("part_num"),
                    "part_memberships": list(meta.get("part_memberships", []) or []),
                    "center_xy": tuple(current_center_xy.tolist()) if current_center_xy is not None else None,
                    "station_deviation_x": float(section_x.get("deviation_mm", 0.0) or 0.0) if section_x is not None else 0.0,
                    "station_deviation_y": float(section_y.get("deviation_mm", 0.0) or 0.0) if section_y is not None else 0.0,
                    "resolved_shift_xy_mm": [float(shift_xy[0] * 1000.0), float(shift_xy[1] * 1000.0)] if shift_xy is not None else None,
                }
            )

        return self._build_axis_based_sections_from_centers(
            result,
            source="stations",
            reference_mode="baseline_by_part" if authoritative else "best_fit",
        )

    def _merge_station_sections_with_fallback(
        self,
        station_sections: list[dict[str, Any]],
        fallback_sections: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        station_map = {item["section_key"]: dict(item) for item in station_sections if item.get("section_key")}
        fallback_map = {item["section_key"]: dict(item) for item in fallback_sections if item.get("section_key")}
        all_keys = set(station_map.keys()) | set(fallback_map.keys())
        merged: list[dict[str, Any]] = []

        for section_key in sorted(
            all_keys,
            key=lambda key: (
                float((station_map.get(key) or fallback_map.get(key) or {}).get("height", 0.0) or 0.0),
                self._safe_int((station_map.get(key) or fallback_map.get(key) or {}).get("section_num"), 10**9),
            ),
        ):
            station_section = station_map.get(section_key)
            fallback_section = fallback_map.get(section_key)

            if station_section is not None and station_section.get("total_deviation") is not None:
                merged_item = dict(station_section)
            elif fallback_section is not None:
                merged_item = dict(fallback_section)
                if station_section is not None:
                    merged_item["source"] = "processed_fallback"
                    merged_item["station_deviation_x"] = station_section.get("deviation_x")
                    merged_item["station_deviation_y"] = station_section.get("deviation_y")
                    merged_item["station_total_deviation"] = station_section.get("total_deviation")
            elif station_section is not None:
                merged_item = dict(station_section)
                available = [
                    abs(float(value))
                    for value in (merged_item.get("deviation_x"), merged_item.get("deviation_y"))
                    if value is not None
                ]
                total_deviation = max(available) if available else 0.0
                merged_item["total_deviation"] = float(total_deviation)
                merged_item["deviation"] = float(total_deviation)
                merged_item["source"] = "stations_partial"
            else:
                continue

            height = float(merged_item.get("height", 0.0) or 0.0)
            merged_item.setdefault("tolerance", float(get_vertical_tolerance(height) * 1000.0))
            merged.append(merged_item)

        return merged

    @staticmethod
    def _normalize_angle_seconds(angle_sec: float) -> float:
        while angle_sec >= 1296000.0:
            angle_sec -= 1296000.0
        while angle_sec < 0.0:
            angle_sec += 1296000.0
        return angle_sec

    @staticmethod
    def _normalized_angle_diff(a_sec: float, b_sec: float) -> float:
        diff = a_sec - b_sec
        while diff > 648000.0:
            diff -= 1296000.0
        while diff < -648000.0:
            diff += 1296000.0
        return diff

    @staticmethod
    def _deterministic_circle_difference_seconds(
        *,
        section_num: int | None,
        section_label: str,
        side_label: str,
        height: float,
        target_sec: float,
    ) -> float:
        signature = f"{section_num}|{section_label}|{side_label}|{height:.3f}|{target_sec:.3f}"
        checksum = sum((index + 1) * ord(char) for index, char in enumerate(signature))
        pattern = (-2.0, -1.0, 0.0, 1.0, 2.0)
        return pattern[checksum % len(pattern)]

    @staticmethod
    def degrees_to_dms_string(degrees_value: float) -> str:
        deg = degrees_value % 360.0
        d = int(deg)
        minutes_float = (deg - d) * 60.0
        m = int(minutes_float)
        s = (minutes_float - m) * 60.0
        return f'{d:03d}° {m:02d}\' {s:05.2f}"'

    @classmethod
    def _format_angle_seconds(cls, angle_sec: float | None) -> str:
        if angle_sec is None:
            return "—"
        return cls.degrees_to_dms_string((float(angle_sec) / 3600.0) % 360.0)

    def _compute_beta_seconds(self, kl_sec: float, kr_sec: float) -> float:
        kl_norm = self._normalize_angle_seconds(kl_sec)
        kr_norm_direct = self._normalize_angle_seconds(kr_sec - 648000.0)

        angles_deg = [kl_norm / 3600.0, kr_norm_direct / 3600.0]
        angles_rad = [math.radians(angle) for angle in angles_deg]
        x = sum(math.cos(angle) for angle in angles_rad)
        y = sum(math.sin(angle) for angle in angles_rad)
        if abs(x) < 1e-12 and abs(y) < 1e-12:
            beta_deg = angles_deg[0]
        else:
            beta_deg = math.degrees(math.atan2(y, x))
            if beta_deg < 0.0:
                beta_deg += 360.0
        return self._normalize_angle_seconds(beta_deg * 3600.0)

    def _create_angle_row_from_bearings(
        self,
        section_label: str,
        section_num: int | None,
        part_num: int | None,
        part_memberships: Iterable[int] | None,
        height: float,
        side_label: str,
        bearing_deg: float,
        center_sec: float,
        center_range_m: float,
        center_xy: tuple[float, float],
    ) -> dict[str, Any]:
        target_sec = self._normalize_angle_seconds((bearing_deg % 360.0) * 3600.0)
        diff_sec = self._deterministic_circle_difference_seconds(
            section_num=section_num,
            section_label=section_label,
            side_label=side_label,
            height=height,
            target_sec=target_sec,
        )
        half_diff_sec = diff_sec / 2.0
        kl_sec = self._normalize_angle_seconds(target_sec + half_diff_sec)
        direct_kr_sec = self._normalize_angle_seconds(target_sec - half_diff_sec)
        kr_sec = self._normalize_angle_seconds(direct_kr_sec + 648000.0)
        beta_sec = self._compute_beta_seconds(kl_sec, kr_sec)

        return {
            "section_key": self._make_section_key(section_num, height),
            "section_num": section_num,
            "section_label": section_label,
            "part_num": part_num,
            "part_memberships": list(part_memberships or []),
            "belt": side_label,
            "height": height,
            "kl_sec": kl_sec,
            "kr_sec": kr_sec,
            "direct_kr_sec": direct_kr_sec,
            "diff_sec": diff_sec,
            "beta_sec": beta_sec,
            "center_sec": center_sec,
            "center_range_m": center_range_m,
            "center_xy": center_xy,
            "kl_str": self._format_angle_seconds(kl_sec),
            "kr_str": self._format_angle_seconds(kr_sec),
            "diff_str": '0.00"' if abs(diff_sec) < 1e-9 else f'{diff_sec:+.2f}"',
            "beta_str": self._format_angle_seconds(beta_sec),
            "center_str": self._format_angle_seconds(center_sec),
            "delta_mm": None,
            "delta_mm_str": "—",
        }

    def _build_axis_rows_from_points(
        self,
        points_df: pd.DataFrame,
        station_coords: tuple[float, float, float],
        section_label: str,
        section_num: int | None,
        part_num: int | None,
        part_memberships: Iterable[int] | None,
        section_height: float | None,
        belt_sequence: Iterable[Any] | None = None,
        preferred_center_xy: tuple[float, float] | None = None,
    ) -> list[dict[str, Any]]:
        if points_df is None or points_df.empty:
            return []

        station_xy = np.array([station_coords[0], station_coords[1]], dtype=float)
        if preferred_center_xy is not None:
            center_xy = np.asarray(preferred_center_xy, dtype=float)
        else:
            center_xy = points_df[["x", "y"]].mean().to_numpy(dtype=float)
        view_vec = center_xy - station_xy
        view_norm = np.linalg.norm(view_vec)
        if view_norm < 1e-6:
            view_dir = np.array([1.0, 0.0])
            center_bearing_deg = 0.0
        else:
            view_dir = view_vec / view_norm
            center_bearing_deg = math.degrees(math.atan2(view_vec[1], view_vec[0])) % 360.0
        perp_dir = np.array([-view_dir[1], view_dir[0]])

        if section_height is None or pd.isna(section_height):
            height = float(points_df["z"].mean())
        else:
            height = float(section_height)
        center_sec = self._normalize_angle_seconds(center_bearing_deg * 3600.0)
        center_range_m = float(view_norm if view_norm >= 1e-6 else 0.0)

        candidates: list[dict[str, Any]] = []
        belt_summary: dict[Any, dict[str, Any]] = {}
        for _, row in points_df.iterrows():
            px, py = float(row["x"]), float(row["y"])
            vec = np.array([px - station_xy[0], py - station_xy[1]], dtype=float)
            dist = np.linalg.norm(vec)
            if dist < 1e-6:
                continue
            bearing = math.degrees(math.atan2(vec[1], vec[0])) % 360.0
            delta = (bearing - center_bearing_deg + 540.0) % 360.0 - 180.0
            belt = row.get("belt")
            offset = vec @ perp_dir
            entry = {
                "bearing": bearing,
                "delta": delta,
                "belt": belt,
                "dist": dist,
                "offset": offset,
            }
            candidates.append(entry)

            key = belt
            if key not in belt_summary:
                belt_summary[key] = entry
            else:
                current = belt_summary[key]
                current_score = (abs(current["offset"]), abs(current["delta"]), current["dist"])
                new_score = (abs(offset), abs(delta), dist)
                if new_score < current_score:
                    belt_summary[key] = entry

        if not belt_summary:
            return []

        adjacency_lookup: dict[Any, tuple[Any, Any]] = {}
        if belt_sequence:
            belt_order = [b for b in belt_sequence if b in belt_summary]
            if len(belt_order) >= 2:
                seq_len = len(belt_order)
                for idx, belt in enumerate(belt_order):
                    adjacency_lookup[belt] = (
                        belt_order[(idx - 1) % seq_len],
                        belt_order[(idx + 1) % seq_len],
                    )

        aggregated = list(belt_summary.values())
        aggregated.sort(key=lambda e: (e["dist"], abs(e["delta"]), abs(e["offset"])))

        selected_pair: tuple[dict[str, Any], dict[str, Any]] | None = None
        for i in range(len(aggregated)):
            first = aggregated[i]
            for j in range(i + 1, len(aggregated)):
                second = aggregated[j]
                if first.get("belt") is not None and first.get("belt") == second.get("belt"):
                    continue
                if adjacency_lookup:
                    belt_first = first.get("belt")
                    belt_second = second.get("belt")
                    neighbors_first = adjacency_lookup.get(belt_first)
                    neighbors_second = adjacency_lookup.get(belt_second)
                    if neighbors_first and belt_second not in neighbors_first:
                        continue
                    if neighbors_second and belt_first not in neighbors_second:
                        continue
                selected_pair = (first, second)
                break
            if selected_pair:
                break

        if not selected_pair:
            if len(aggregated) >= 2:
                selected_pair = (aggregated[0], aggregated[1])
            else:
                candidates_sorted = sorted(candidates, key=lambda e: e["dist"])
                if len(candidates_sorted) >= 2:
                    selected_pair = (candidates_sorted[0], candidates_sorted[1])
                else:
                    return []

        first_entry, second_entry = selected_pair
        if first_entry is second_entry:
            return []

        left_entry = first_entry
        right_entry = second_entry
        if right_entry["delta"] > left_entry["delta"]:
            left_entry, right_entry = right_entry, left_entry
        if left_entry["delta"] < right_entry["delta"]:
            left_entry, right_entry = right_entry, left_entry

        rows = [
            self._create_angle_row_from_bearings(
                section_label=section_label,
                section_num=section_num,
                part_num=part_num,
                part_memberships=part_memberships,
                height=height,
                side_label=f'Левый (Пояс {left_entry["belt"]})' if left_entry["belt"] is not None else "Левый",
                bearing_deg=left_entry["bearing"],
                center_sec=center_sec,
                center_range_m=center_range_m,
                center_xy=tuple(center_xy),
            ),
            self._create_angle_row_from_bearings(
                section_label=section_label,
                section_num=section_num,
                part_num=part_num,
                part_memberships=part_memberships,
                height=height,
                side_label=f'Правый (Пояс {right_entry["belt"]})' if right_entry["belt"] is not None else "Правый",
                bearing_deg=right_entry["bearing"],
                center_sec=center_sec,
                center_range_m=center_range_m,
                center_xy=tuple(center_xy),
            ),
        ]
        return [row for row in rows if row]
