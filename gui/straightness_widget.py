"""
Р’РёРґР¶РµС‚ РґР»СЏ РѕС‚РѕР±СЂР°Р¶РµРЅРёСЏ РїСЂСЏРјРѕР»РёРЅРµР№РЅРѕСЃС‚Рё СЃС‚РІРѕР»Р° Р±Р°С€РЅРё
Р Р°СЃС‡РµС‚ СЃС‚СЂРµР»С‹ РїСЂРѕРіРёР±Р° РїРѕСЏСЃР° СЃС‚РІРѕР»Р°
"""

import json
import numpy as np
import pandas as pd
from typing import Optional
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTabWidget,
                             QTableWidget, QTableWidgetItem, QHeaderView, QSplitter, QScrollArea)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
import matplotlib.pyplot as plt
from matplotlib import ticker
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import logging

from core.normatives import get_straightness_tolerance
from core.point_utils import build_working_tower_mask
from core.straightness_calculations import calculate_belt_deflections as calculate_canonical_belt_deflections
from core.services.straightness_profiles import (
    get_preferred_straightness_part_map,
    get_preferred_straightness_profiles,
)

logger = logging.getLogger(__name__)


class StraightnessWidget(QWidget):
    """Р’РёРґР¶РµС‚ РґР»СЏ РѕС‚РѕР±СЂР°Р¶РµРЅРёСЏ РіСЂР°С„РёРєР° РїСЂСЏРјРѕР»РёРЅРµР№РЅРѕСЃС‚Рё СЃС‚РІРѕР»Р° Р±Р°С€РЅРё"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.data = None
        self.processed_data = None
        self.editor_3d = None  # РЎСЃС‹Р»РєР° РЅР° 3D СЂРµРґР°РєС‚РѕСЂ
        self.init_ui()
    
    def _decode_part_memberships(self, value) -> list[int]:
        if value is None:
            return []
        if isinstance(value, float) and np.isnan(value):
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
        memberships = []
        for item in decoded:
            try:
                memberships.append(int(item))
            except (TypeError, ValueError):
                continue
        return memberships
    
    def _build_is_station_mask(self, series: pd.Series) -> pd.Series:
        series = series.copy()
        if series.dtype == 'object':
            string_mask = series.map(lambda value: isinstance(value, str))
            if string_mask.any():
                lowered = series[string_mask].str.strip().str.lower()
                mapping = {'true': True, 'false': False, '1': True, '0': False, 'yes': True, 'no': False}
                mapped = lowered.map(mapping)
                valid_idx = mapped.dropna().index
                if len(valid_idx) > 0:
                    series.loc[valid_idx] = mapped.loc[valid_idx]
            series = series.infer_objects(copy=False)
        null_mask = series.isna()
        if null_mask.any():
            series.loc[null_mask] = False
        return series.astype(bool)

    def _row_has_part(self, row: pd.Series, part_num: int) -> bool:
        memberships = []
        if 'tower_part_memberships' in row and pd.notna(row.get('tower_part_memberships')):
            memberships = self._decode_part_memberships(row.get('tower_part_memberships'))
        if memberships:
            return part_num in memberships
        raw_value = row.get('tower_part', 1)
        if raw_value is None or (isinstance(raw_value, float) and np.isnan(raw_value)):
            raw_value = 1
        try:
            base_part = int(raw_value)
        except (TypeError, ValueError):
            return False
        if base_part <= 0:
            base_part = 1
        if bool(row.get('is_part_boundary', False)):
            return part_num in (base_part, base_part + 1)
        return base_part == part_num
    
    def _collect_unique_parts(self, data: pd.DataFrame) -> list[int]:
        parts = set()
        if 'tower_part_memberships' in data.columns:
            for value in data['tower_part_memberships'].dropna():
                parts.update(self._decode_part_memberships(value))
        if not parts and 'tower_part' in data.columns:
            parts.update(data['tower_part'].dropna().unique())
        if 'is_part_boundary' in data.columns and data['is_part_boundary'].any():
            boundary_rows = data[data['is_part_boundary']]
            for _, row in boundary_rows.iterrows():
                raw_value = row.get('tower_part', 1)
                try:
                    base_part = int(raw_value)
                except (TypeError, ValueError):
                    base_part = 1
                if base_part <= 0:
                    base_part = 1
                parts.update({base_part, base_part + 1})
        return sorted(int(part) for part in parts if part is not None)

    def _get_working_data(self) -> pd.DataFrame:
        if self.data is None or self.data.empty:
            return pd.DataFrame()
        try:
            return self.data[build_working_tower_mask(self.data)].copy()
        except Exception:
            return self.data.copy()

    def _get_profile_lookup(self) -> dict[tuple[int, int], dict]:
        lookup: dict[tuple[int, int], dict] = {}
        for profile in get_preferred_straightness_profiles(
            self.processed_data.get('straightness_profiles') if isinstance(self.processed_data, dict) else None
        ):
            try:
                part_number = int(profile.get('part_number', 1))
                belt_number = int(profile.get('belt', 0))
            except (TypeError, ValueError):
                continue
            lookup[(part_number, belt_number)] = profile
        return lookup

    def _get_profile_deflections(
        self,
        belt_points: pd.DataFrame,
        belt_num: int,
        part_num: Optional[int],
    ) -> Optional[list[float]]:
        if belt_points is None or belt_points.empty:
            return []
        lookup = self._get_profile_lookup()
        profile = lookup.get((int(part_num or 1), int(belt_num)))
        if not profile:
            return None

        point_map = {}
        for point in profile.get('points', []):
            try:
                point_map[int(point.get('source_index'))] = float(point.get('deflection_mm', 0.0))
            except (TypeError, ValueError):
                continue

        belt_sorted = belt_points.sort_values('z')
        if belt_sorted.empty:
            return []
        if not point_map:
            return [0.0] * len(belt_sorted)

        return [float(point_map.get(int(idx), 0.0)) for idx in belt_sorted.index]
        
    def _cluster_display_heights(self, heights: list[float], tolerance: float = 0.25) -> tuple[list[float], dict[float, float]]:
        if not heights:
            return [], {}

        processed_levels: list[float] = []
        if isinstance(self.processed_data, dict):
            centers = self.processed_data.get('centers')
            if centers is not None:
                try:
                    centers_df = centers.copy() if isinstance(centers, pd.DataFrame) else pd.DataFrame(centers)
                except Exception:
                    centers_df = pd.DataFrame()
                if not centers_df.empty:
                    height_col = next((candidate for candidate in ('z', 'height', 'belt_height') if candidate in centers_df.columns), None)
                    if height_col is not None:
                        processed_levels = sorted({
                            round(float(value), 1)
                            for value in centers_df[height_col].dropna().tolist()
                        })

        mapping: dict[float, float] = {}
        if processed_levels:
            for raw_height in heights:
                raw_value = float(raw_height)
                nearest_level = min(processed_levels, key=lambda value: abs(value - raw_value))
                mapping[round(raw_value, 6)] = float(nearest_level if abs(nearest_level - raw_value) <= tolerance else round(raw_value, 1))
            all_levels = sorted({*processed_levels, *mapping.values()})
            return [float(level) for level in all_levels], mapping

        sorted_heights = sorted(float(height) for height in heights)
        clusters: list[list[float]] = []
        for height in sorted_heights:
            if not clusters:
                clusters.append([height])
                continue
            current_cluster = clusters[-1]
            current_mean = sum(current_cluster) / len(current_cluster)
            if abs(height - current_mean) <= tolerance:
                current_cluster.append(height)
            else:
                clusters.append([height])

        display_levels: list[float] = []
        for cluster in clusters:
            display_level = float(round(sum(cluster) / len(cluster), 1))
            display_levels.append(display_level)
            for raw_height in cluster:
                mapping[round(float(raw_height), 6)] = display_level

        return display_levels, mapping

    @staticmethod
    def _display_height(height: float, mapping: dict[float, float]) -> float:
        return float(mapping.get(round(float(height), 6), round(float(height), 1)))

    def init_ui(self):
        """РРЅРёС†РёР°Р»РёР·Р°С†РёСЏ РёРЅС‚РµСЂС„РµР№СЃР°"""
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)
        self.setLayout(main_layout)
        
        # Splitter РґР»СЏ РіСЂР°С„РёРєР° Рё С‚Р°Р±Р»РёС†С‹
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Р›РµРІР°СЏ С‡Р°СЃС‚СЊ - РіСЂР°С„РёРєРё
        graph_widget = QWidget()
        graph_layout = QVBoxLayout()
        graph_layout.setContentsMargins(0, 0, 0, 0)
        graph_widget.setLayout(graph_layout)
        
        self.graph_tabs = QTabWidget()
        self.graph_tabs.setTabsClosable(False)
        self.graph_tabs.currentChanged.connect(self._on_graph_tab_changed)
        graph_layout.addWidget(self.graph_tabs)
        self.graph_tab_layouts = {}
        self._graph_entries_by_part = {}
        self._rendered_graph_parts = set()
        splitter.addWidget(graph_widget)
        
        # РџСЂР°РІР°СЏ С‡Р°СЃС‚СЊ - С‚Р°Р±Р»РёС†Р°
        table_widget = QWidget()
        table_layout = QVBoxLayout()
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_widget.setLayout(table_layout)
        
        # Р—Р°РіРѕР»РѕРІРѕРє С‚Р°Р±Р»РёС†С‹
        table_title = QLabel('Отклонения прогиба по поясам')
        table_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        table_title.setStyleSheet('font-weight: bold; padding: 5px;')
        table_layout.addWidget(table_title)
        
        # РўР°Р±Р»РёС†Р° - СЃС‚РѕР»Р±С†С‹ РґР»СЏ РєР°Р¶РґРѕРіРѕ РїРѕСЏСЃР°
        self.deviation_table = QTableWidget()
        # РЎС‚РѕР»Р±С†С‹ Р±СѓРґСѓС‚ РґРѕР±Р°РІР»РµРЅС‹ РґРёРЅР°РјРёС‡РµСЃРєРё РїСЂРё Р·Р°РїРѕР»РЅРµРЅРёРё РґР°РЅРЅС‹С…
        self.deviation_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.deviation_table.setAlternatingRowColors(True)
        table_layout.addWidget(self.deviation_table)

        # Р’РєР»Р°РґРєРё РґР»СЏ С‚Р°Р±Р»РёС† С‡Р°СЃС‚РµР№ СЃРѕСЃС‚Р°РІРЅРѕР№ Р±Р°С€РЅРё
        self.parts_table_tabs = QTabWidget()
        self.parts_table_tabs.hide()
        table_layout.addWidget(self.parts_table_tabs)
        self.part_tables = {}
        splitter.addWidget(table_widget)
        
        # РџСЂРѕРїРѕСЂС†РёРё splitter - РіСЂР°С„РёРєРё Р·Р°РЅРёРјР°СЋС‚ Р±РѕР»СЊС€Рµ РјРµСЃС‚Р°
        splitter.setStretchFactor(0, 70)
        splitter.setStretchFactor(1, 30)
        
        main_layout.addWidget(splitter, stretch=1)
        
        # РРЅС„РѕСЂРјР°С†РёРѕРЅРЅР°СЏ РјРµС‚РєР°
        self.info_label = QLabel('Загрузите данные для отображения графиков прямолинейности')
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.info_label.setStyleSheet('padding: 5px; color: #333; background-color: #f0f0f0; border-radius: 3px;')
        self.info_label.setWordWrap(True)
        self.info_label.setMaximumHeight(50)
        main_layout.addWidget(self.info_label)
        
    def set_data(self, data: pd.DataFrame, processed_data: dict = None):
        """РЈСЃС‚Р°РЅРѕРІРёС‚СЊ РґР°РЅРЅС‹Рµ РґР»СЏ РїРѕСЃС‚СЂРѕРµРЅРёСЏ РіСЂР°С„РёРєР°
        
        Args:
            data: DataFrame СЃ С‚РѕС‡РєР°РјРё
            processed_data: РћР±СЂР°Р±РѕС‚Р°РЅРЅС‹Рµ РґР°РЅРЅС‹Рµ СЃ СЂР°СЃС‡РµС‚Р°РјРё (РѕРїС†РёРѕРЅР°Р»СЊРЅРѕ)
        """
        # Р—Р°С‰РёС‚Р° РѕС‚ Р·Р°С†РёРєР»РёРІР°РЅРёСЏ: РїСЂРѕРІРµСЂСЏРµРј, РЅРµ РІС‹РїРѕР»РЅСЏРµС‚СЃСЏ Р»Рё СѓР¶Рµ РѕР±РЅРѕРІР»РµРЅРёРµ
        if not hasattr(self, '_updating_plots'):
            self._updating_plots = False
        
        if self._updating_plots:
            logger.debug("РџСЂРѕРїСѓСЃРє set_data - СѓР¶Рµ РІС‹РїРѕР»РЅСЏРµС‚СЃСЏ РѕР±РЅРѕРІР»РµРЅРёРµ")
            return
        
        # РџСЂРѕРІРµСЂСЏРµРј, РёР·РјРµРЅРёР»РёСЃСЊ Р»Рё РґР°РЅРЅС‹Рµ (С‡С‚РѕР±С‹ РёР·Р±РµР¶Р°С‚СЊ Р»РёС€РЅРёС… РѕР±РЅРѕРІР»РµРЅРёР№)
        data_changed = self.data is None or not self.data.equals(data) if data is not None else True
        
        # Р‘РµР·РѕРїР°СЃРЅРѕРµ СЃСЂР°РІРЅРµРЅРёРµ processed_data (РјРѕР¶РµС‚ Р±С‹С‚СЊ dict, DataFrame РёР»Рё None)
        processed_changed = True
        if self.processed_data is None:
            processed_changed = processed_data is not None
        elif processed_data is None:
            processed_changed = True
        elif isinstance(self.processed_data, pd.DataFrame) and isinstance(processed_data, pd.DataFrame):
            processed_changed = not self.processed_data.equals(processed_data)
        elif isinstance(self.processed_data, dict) and isinstance(processed_data, dict):
            # РџСЂРѕСЃС‚РѕРµ СЃСЂР°РІРЅРµРЅРёРµ СЃР»РѕРІР°СЂРµР№ (РґР»СЏ РіР»СѓР±РѕРєРѕРіРѕ СЃСЂР°РІРЅРµРЅРёСЏ РЅСѓР¶РЅР° Р±РѕР»РµРµ СЃР»РѕР¶РЅР°СЏ Р»РѕРіРёРєР°)
            processed_changed = self.processed_data is not processed_data
        else:
            processed_changed = self.processed_data is not processed_data
        
        if not data_changed and not processed_changed:
            logger.debug("Р”Р°РЅРЅС‹Рµ РЅРµ РёР·РјРµРЅРёР»РёСЃСЊ, РїСЂРѕРїСѓСЃРє РѕР±РЅРѕРІР»РµРЅРёСЏ")
            return
        
        self.data = data
        self.processed_data = processed_data
        self.update_plots()
        
    def update_plots(self):
        """РћР±РЅРѕРІРёС‚СЊ РІСЃРµ РіСЂР°С„РёРєРё РїСЂСЏРјРѕР»РёРЅРµР№РЅРѕСЃС‚Рё РїРѕ РїРѕСЏСЃР°Рј РЅР° РѕРґРЅРѕР№ РІРєР»Р°РґРєРµ"""
        # Р—Р°С‰РёС‚Р° РѕС‚ Р·Р°С†РёРєР»РёРІР°РЅРёСЏ
        if not hasattr(self, '_updating_plots'):
            self._updating_plots = False
        
        if self._updating_plots:
            logger.debug("РџСЂРѕРїСѓСЃРє update_plots - СѓР¶Рµ РІС‹РїРѕР»РЅСЏРµС‚СЃСЏ")
            return
        
        self._updating_plots = True
        try:
            if self.data is None or self.data.empty:
                self.info_label.setText('Нет данных для отображения')
                self._clear_graphs()
                self.deviation_table.setRowCount(0)
                return
            # РџСЂРѕРІРµСЂСЏРµРј РЅР°Р»РёС‡РёРµ РїРѕСЏСЃРѕРІ
            if 'belt' not in self.data.columns:
                self.info_label.setText('Исходные данные должны содержать информацию о поясах')
                self._clear_graphs()
                self.deviation_table.setRowCount(0)
                return
            
            # РћС‡РёС‰Р°РµРј СЃСѓС‰РµСЃС‚РІСѓСЋС‰РёРµ РіСЂР°С„РёРєРё Рё С‚Р°Р±Р»РёС†Сѓ
            self._clear_graphs()
            self.deviation_table.setRowCount(0)
            
            # РСЃРєР»СЋС‡Р°РµРј С‚РѕС‡РєРё standing
            data_without_station = self._get_working_data()
            
            # РџСЂРѕРІРµСЂСЏРµРј, СЏРІР»СЏРµС‚СЃСЏ Р»Рё Р±Р°С€РЅСЏ СЃРѕСЃС‚Р°РІРЅРѕР№
            has_memberships = 'tower_part_memberships' in data_without_station.columns and data_without_station['tower_part_memberships'].notna().any()
            has_numeric_parts = 'tower_part' in data_without_station.columns and data_without_station['tower_part'].notna().any()
            is_composite = has_memberships or has_numeric_parts
            
            if is_composite:
                unique_parts = self._collect_unique_parts(data_without_station)
                if not unique_parts and has_numeric_parts:
                    unique_parts = sorted(data_without_station['tower_part'].dropna().unique())
                if not unique_parts:
                    unique_parts = [1]
                logger.info(f"РћР±РЅР°СЂСѓР¶РµРЅР° СЃРѕСЃС‚Р°РІРЅР°СЏ Р±Р°С€РЅСЏ СЃ С‡Р°СЃС‚СЏРјРё: {unique_parts}")
            else:
                unique_parts = [1]
            
            # РџРѕР»СѓС‡Р°РµРј СЃРїРёСЃРѕРє РїРѕСЏСЃРѕРІ
            belts = sorted(data_without_station['belt'].dropna().unique())
            
            if len(belts) == 0:
                self.info_label.setText('Нет поясов в данных')
                return
            
            logger.info(f"РџРѕСЃС‚СЂРѕРµРЅРёРµ РіСЂР°С„РёРєРѕРІ РїСЂСЏРјРѕР»РёРЅРµР№РЅРѕСЃС‚Рё РґР»СЏ {len(belts)} РїРѕСЏСЃРѕРІ")
            
            # РЎРѕР±РёСЂР°РµРј РґР°РЅРЅС‹Рµ РґР»СЏ С‚Р°Р±Р»РёС† (РїРѕ С‡Р°СЃС‚СЏРј) Рё РїРѕРґРіРѕС‚Р°РІР»РёРІР°РµРј РіСЂР°С„РёРєРё
            belt_data_by_part: dict[int, dict[int, dict]] = {}
            graph_entries_by_part: dict[int, list] = {}
            
            # Р“СЂСѓРїРїРёСЂСѓРµРј РїРѕСЏСЃР° РїРѕ С‡Р°СЃС‚СЏРј РґР»СЏ СЃРѕСЃС‚Р°РІРЅРѕР№ Р±Р°С€РЅРё
            if is_composite:
                # Р”РѕР±Р°РІР»СЏРµРј Р·Р°РіРѕР»РѕРІРєРё РґР»СЏ С‡Р°СЃС‚РµР№
                for part_num in unique_parts:
                    # РџРѕР»СѓС‡Р°РµРј РїРѕСЏСЃР° СЌС‚РѕР№ С‡Р°СЃС‚Рё
                    part_mask = data_without_station.apply(lambda row: self._row_has_part(row, part_num), axis=1)
                    part_data = data_without_station[part_mask].copy()
                    part_belts = sorted(part_data['belt'].dropna().unique())
                    
                    logger.info(f"Р§Р°СЃС‚СЊ {int(part_num)}: {len(part_belts)} РїРѕСЏСЃРѕРІ")
                    
                    # РќР°С…РѕРґРёРј РјРёРЅРёРјР°Р»СЊРЅСѓСЋ Рё РјР°РєСЃРёРјР°Р»СЊРЅСѓСЋ РІС‹СЃРѕС‚Сѓ РґР»СЏ СЌС‚РѕР№ С‡Р°СЃС‚Рё
                    part_min_height = part_data['z'].min()
                    part_max_height = part_data['z'].max()
                    part_height = part_max_height - part_min_height
                    
                    for belt_num in part_belts:
                        belt_points = part_data[part_data['belt'] == belt_num]
                        
                        if len(belt_points) < 2:
                            logger.warning(f"РќР° РїРѕСЏСЃРµ {belt_num} С‡Р°СЃС‚Рё {int(part_num)} РЅРµРґРѕСЃС‚Р°С‚РѕС‡РЅРѕ С‚РѕС‡РµРє РґР»СЏ СЂР°СЃС‡РµС‚Р°")
                            continue
                        
                        # РЎРѕР±РёСЂР°РµРј РґР°РЅРЅС‹Рµ РґР»СЏ С‚Р°Р±Р»РёС†С‹
                        belt_sorted = belt_points.sort_values('z')
                        deflections = self._calculate_belt_deflections(belt_sorted, part_num=int(part_num),
                                                                      part_min_height=part_min_height,
                                                                      part_max_height=part_max_height)
                        belt_length = part_height  # РСЃРїРѕР»СЊР·СѓРµРј РІС‹СЃРѕС‚Сѓ С‡Р°СЃС‚Рё, Р° РЅРµ РїРѕСЏСЃР°
                        from core.normatives import get_straightness_tolerance
                        max_allowed_deflection_m = get_straightness_tolerance(belt_length)
                        max_allowed_deflection_mm = max_allowed_deflection_m * 1000  # РІ РјРј
                        
                        # РЎРѕС…СЂР°РЅСЏРµРј РґР°РЅРЅС‹Рµ РїРѕ СЌС‚РѕРјСѓ РїРѕСЏСЃСѓ
                        part_id = int(part_num)
                        part_tables = belt_data_by_part.setdefault(part_id, {})
                        graph_entries_by_part.setdefault(part_id, [])
                        part_tables[int(belt_num)] = {
                            'points': [],
                            'tolerance': max_allowed_deflection_mm,
                            'part_min_height': part_min_height,
                            'part_max_height': part_max_height,
                            'part_height': part_height
                        }
                        
                        for i, (idx, point) in enumerate(belt_sorted.iterrows()):
                            deflection = deflections[i] if i < len(deflections) else 0.0
                            # РСЃРїРѕР»СЊР·СѓРµРј Р°Р±СЃРѕР»СЋС‚РЅСѓСЋ РІС‹СЃРѕС‚Сѓ (РєР°Рє РІ РіСЂР°С„РёРєРµ)
                            absolute_height = point['z']
                            part_tables[int(belt_num)]['points'].append({
                                'height': absolute_height,  # РђР±СЃРѕР»СЋС‚РЅР°СЏ РІС‹СЃРѕС‚Р°
                                'deflection': deflection
                            })
                        logger.debug(f"Р§Р°СЃС‚СЊ {part_num}, РџРѕСЏСЃ {belt_num}: РІС‹СЃРѕС‚Р° С‡Р°СЃС‚Рё={part_height:.2f}Рј, "
                                   f"С‚РѕС‡РµРє={len(belt_sorted)}, РїРµСЂРІР°СЏ РІС‹СЃРѕС‚Р°={belt_sorted.iloc[0]['z']:.2f}Рј, "
                                   f"РїРѕСЃР»РµРґРЅСЏСЏ={belt_sorted.iloc[-1]['z']:.2f}Рј")
                        # РЎРѕС…СЂР°РЅСЏРµРј РґР°РЅРЅС‹Рµ РґР»СЏ РіСЂР°С„РёРєР° СЃ РёРЅС„РѕСЂРјР°С†РёРµР№ Рѕ РіСЂР°РЅРёС†Р°С… С‡Р°СЃС‚Рё
                        graph_entries_by_part[part_id].append(
                            (int(belt_num), belt_points.copy(), part_id, part_min_height, part_max_height)
                        )
            else:
                # РћР±С‹С‡РЅР°СЏ Р±Р°С€РЅСЏ - РѕР±СЂР°Р±Р°С‚С‹РІР°РµРј РІСЃРµ РїРѕСЏСЃР°
                # РќР°С…РѕРґРёРј РјРёРЅРёРјР°Р»СЊРЅСѓСЋ Рё РјР°РєСЃРёРјР°Р»СЊРЅСѓСЋ РІС‹СЃРѕС‚Сѓ РґР»СЏ РІСЃРµР№ Р±Р°С€РЅРё
                tower_min_height = data_without_station['z'].min()
                tower_max_height = data_without_station['z'].max()
                tower_height = tower_max_height - tower_min_height
                
                for belt_num in belts:
                    belt_points = data_without_station[data_without_station['belt'] == belt_num]
                    
                    if len(belt_points) < 2:
                        logger.warning(f"РќР° РїРѕСЏСЃРµ {belt_num} РЅРµРґРѕСЃС‚Р°С‚РѕС‡РЅРѕ С‚РѕС‡РµРє РґР»СЏ СЂР°СЃС‡РµС‚Р°")
                        continue
                    
                    # РЎРѕР±РёСЂР°РµРј РґР°РЅРЅС‹Рµ РґР»СЏ С‚Р°Р±Р»РёС†С‹
                    belt_sorted = belt_points.sort_values('z')
                    deflections = self._calculate_belt_deflections(belt_sorted)
                    belt_length = tower_height  # РСЃРїРѕР»СЊР·СѓРµРј РІС‹СЃРѕС‚Сѓ РІСЃРµР№ Р±Р°С€РЅРё
                    from core.normatives import get_straightness_tolerance
                    max_allowed_deflection_m = get_straightness_tolerance(belt_length)
                    max_allowed_deflection_mm = max_allowed_deflection_m * 1000  # РІ РјРј
                    
                    # РЎРѕС…СЂР°РЅСЏРµРј РґР°РЅРЅС‹Рµ РїРѕ СЌС‚РѕРјСѓ РїРѕСЏСЃСѓ
                    part_id = 1
                    part_tables = belt_data_by_part.setdefault(part_id, {})
                    graph_entries_by_part.setdefault(part_id, [])
                    part_tables[int(belt_num)] = {
                        'points': [],
                        'tolerance': max_allowed_deflection_mm,
                        'part_min_height': tower_min_height,
                        'part_max_height': tower_max_height,
                        'part_height': tower_height
                    }
                    
                    for i, (idx, point) in enumerate(belt_sorted.iterrows()):
                        deflection = deflections[i] if i < len(deflections) else 0.0
                        # РСЃРїРѕР»СЊР·СѓРµРј Р°Р±СЃРѕР»СЋС‚РЅСѓСЋ РІС‹СЃРѕС‚Сѓ (РєР°Рє РІ РіСЂР°С„РёРєРµ)
                        absolute_height = point['z']
                        part_tables[int(belt_num)]['points'].append({
                            'height': absolute_height,  # РђР±СЃРѕР»СЋС‚РЅР°СЏ РІС‹СЃРѕС‚Р°
                            'deflection': deflection
                        })
                    # РЎРѕС…СЂР°РЅСЏРµРј РґР°РЅРЅС‹Рµ РґР»СЏ РіСЂР°С„РёРєР° СЃ РёРЅС„РѕСЂРјР°С†РёРµР№ Рѕ РіСЂР°РЅРёС†Р°С… Р±Р°С€РЅРё
                    graph_entries_by_part[part_id].append(
                        (int(belt_num), belt_points.copy(), part_id, tower_min_height, tower_max_height)
                    )
            
            # Р—Р°РїРѕР»РЅСЏРµРј С‚Р°Р±Р»РёС†С‹ (РїРѕ РѕРґРЅРѕР№ РґР»СЏ РєР°Р¶РґРѕР№ С‡Р°СЃС‚Рё)
            is_multi_part = is_composite and len(belt_data_by_part) > 1
            self._fill_pivot_table(belt_data_by_part, is_multi_part)
            self._graph_entries_by_part = graph_entries_by_part
            self._rendered_graph_parts = set()
            
            graph_part_keys = sorted(belt_data_by_part.keys())
            if graph_part_keys:
                self._setup_graph_tabs(graph_part_keys, is_multi_part)
            else:
                self._show_graph_placeholder('Нет данных для построения графиков прямолинейности')
            
            parts_count = len(belt_data_by_part) if is_composite else 1
            parts_text = f" ({parts_count} частей)" if is_composite and parts_count > 1 else ""
            self.info_label.setText(f'Графики построены для {len(belts)} поясов{parts_text}')
            logger.info(f"Р“СЂР°С„РёРєРё РїСЂСЏРјРѕР»РёРЅРµР№РЅРѕСЃС‚Рё РїРѕСЃС‚СЂРѕРµРЅС‹ РґР»СЏ {len(belts)} РїРѕСЏСЃРѕРІ{parts_text}")
            
        except Exception as e:
            logger.error(f"РћС€РёР±РєР° РїСЂРё РїРѕСЃС‚СЂРѕРµРЅРёРё РіСЂР°С„РёРєРѕРІ РїСЂСЏРјРѕР»РёРЅРµР№РЅРѕСЃС‚Рё: {e}", exc_info=True)
            self.info_label.setText(f'Ошибка: {str(e)}')
        finally:
            self._updating_plots = False
    
    def _clear_graphs(self):
        """РћС‡РёСЃС‚РёС‚СЊ РІСЃРµ РіСЂР°С„РёРєРё"""
        self.graph_tabs.clear()
        self.graph_tab_layouts = {}
        self._graph_entries_by_part = {}
        self._rendered_graph_parts = set()

    def _show_graph_placeholder(self, message: str):
        self.graph_tabs.clear()
        placeholder = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label = QLabel(message)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet('color: #666; font-size: 10pt;')
        layout.addWidget(label)
        placeholder.setLayout(layout)
        self.graph_tabs.addTab(placeholder, 'Графики')

    def _create_graph_tab_widget(self):
        tab_widget = QWidget()
        tab_layout = QVBoxLayout()
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.setSpacing(0)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content_widget = QWidget()
        belt_layout = QHBoxLayout()
        belt_layout.setContentsMargins(5, 5, 5, 5)
        belt_layout.setSpacing(10)
        content_widget.setLayout(belt_layout)
        scroll_area.setWidget(content_widget)

        tab_layout.addWidget(scroll_area)
        tab_widget.setLayout(tab_layout)
        return tab_widget, belt_layout

    def _setup_graph_tabs(self, part_keys: list[int], is_multi_part: bool):
        self.graph_tabs.blockSignals(True)
        self.graph_tabs.clear()
        self.graph_tab_layouts = {}
        self._rendered_graph_parts = set()

        tab_bar = self.graph_tabs.tabBar()
        for part_num in part_keys:
            title = f'Часть {part_num}' if is_multi_part else 'Все пояса'
            tab_widget, belt_layout = self._create_graph_tab_widget()
            index = self.graph_tabs.addTab(tab_widget, title)
            if tab_bar is not None:
                tab_bar.setTabData(index, part_num)
            self.graph_tab_layouts[part_num] = belt_layout

        self.graph_tabs.blockSignals(False)

        if part_keys:
            self.graph_tabs.setCurrentIndex(0)
            self._render_graphs_for_part(part_keys[0])

    def _render_graphs_for_part(self, part_num: Optional[int]):
        if part_num is None or part_num in self._rendered_graph_parts:
            return
        layout = self.graph_tab_layouts.get(part_num)
        if layout is None:
            return
        entries = self._graph_entries_by_part.get(part_num, [])

        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not entries:
            placeholder = QLabel('Недостаточно данных для построения графиков этой части')
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            placeholder.setStyleSheet('color: #666; font-size: 10pt;')
            layout.addWidget(placeholder)
            self._rendered_graph_parts.add(part_num)
            return

        for entry in entries:
            if len(entry) >= 5:
                belt_num, belt_points, part_label, part_min_height, part_max_height = entry
            else:
                # РћР±СЂР°С‚РЅР°СЏ СЃРѕРІРјРµСЃС‚РёРјРѕСЃС‚СЊ СЃРѕ СЃС‚Р°СЂС‹Рј С„РѕСЂРјР°С‚РѕРј
                belt_num, belt_points, part_label = entry[:3]
                part_min_height = None
                part_max_height = None
            self._create_belt_graph(
                belt_num,
                belt_points,
                part_num=part_label,
                part_min_height=part_min_height,
                part_max_height=part_max_height,
                target_layout=layout
            )
        self._rendered_graph_parts.add(part_num)

    def _on_graph_tab_changed(self, index: int):
        tab_bar = self.graph_tabs.tabBar()
        if tab_bar is None:
            return
        part_num = tab_bar.tabData(index)
        if part_num is None:
            return
        self._render_graphs_for_part(part_num)
    
    def _create_belt_graph(
        self,
        belt_num: int,
        belt_points: pd.DataFrame,
        part_num: Optional[int] = None,
        part_min_height: Optional[float] = None,
        part_max_height: Optional[float] = None,
        target_layout: Optional[QHBoxLayout] = None
    ):
        """Создает компактный график для одного пояса башни."""
        if target_layout is None:
            return

        graph_item_widget = QWidget()
        graph_item_layout = QVBoxLayout()
        graph_item_layout.setContentsMargins(5, 5, 5, 5)
        graph_item_layout.setSpacing(3)
        graph_item_widget.setLayout(graph_item_layout)

        if part_num is not None:
            graph_title = QLabel(f'Пояс {int(belt_num)} [Часть {int(part_num)}]')
        else:
            graph_title = QLabel(f'Пояс {int(belt_num)}')
        graph_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        graph_title.setStyleSheet('font-weight: bold; padding: 2px; font-size: 9pt;')
        graph_title.setMaximumHeight(25)
        graph_item_layout.addWidget(graph_title)

        figure = Figure(figsize=(4, 8), dpi=100)
        canvas = FigureCanvas(figure)
        graph_item_layout.addWidget(canvas, stretch=1)

        self._plot_belt_straightness(
            figure,
            belt_num,
            belt_points,
            part_num=part_num,
            part_min_height=part_min_height,
            part_max_height=part_max_height,
        )

        target_layout.addWidget(graph_item_widget, stretch=1)

    def _populate_part_table(self, table: QTableWidget, belt_data_dict: dict, part_num: Optional[int] = None):
        """Заполняет сводную таблицу по поясам: строки = высоты секций, столбцы = пояса."""
        try:
            part_suffix = f" (часть {part_num})" if part_num is not None else ""
            logger.info(f"Заполнение сводной таблицы для {len(belt_data_dict)} поясов{part_suffix}")
            table.setRowCount(0)
            table.setColumnCount(0)

            if not belt_data_dict:
                logger.warning("Нет данных для таблицы")
                return

            raw_heights = [
                float(point['height'])
                for belt_data in belt_data_dict.values()
                for point in belt_data['points']
            ]
            sorted_heights, display_height_map = self._cluster_display_heights(raw_heights)
            sorted_belts = sorted(belt_data_dict.keys())

            max_tolerance = max(belt_data['tolerance'] for belt_data in belt_data_dict.values())
            max_tolerance_rounded = round(max_tolerance, 1)

            table.setColumnCount(len(sorted_belts) + 2)
            headers = ['Высота, м'] + [f'Пояс {belt}' for belt in sorted_belts] + ['Допустимое, мм']
            table.setHorizontalHeaderLabels(headers)
            table.setRowCount(len(sorted_heights))

            belt_height_deflection = {}
            for belt_num, belt_data in belt_data_dict.items():
                for point in belt_data['points']:
                    display_height = self._display_height(point['height'], display_height_map)
                    belt_height_deflection[(belt_num, display_height)] = {
                        'deflection': round(point['deflection'], 1),
                        'tolerance': float(belt_data['tolerance']),
                    }

            tolerance_col_idx = len(sorted_belts) + 1
            for row_idx, height in enumerate(sorted_heights):
                height_item = QTableWidgetItem(f"{height:.1f}")
                height_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                table.setItem(row_idx, 0, height_item)

                for col_idx, belt_num in enumerate(sorted_belts, start=1):
                    payload = belt_height_deflection.get((belt_num, height))
                    if payload is None:
                        empty_item = QTableWidgetItem('-')
                        empty_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                        table.setItem(row_idx, col_idx, empty_item)
                        continue

                    deflection = float(payload['deflection'])
                    tolerance = float(payload['tolerance'])
                    deflection_item = QTableWidgetItem(f"{deflection:+.1f}")
                    deflection_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    if abs(deflection) > max_tolerance_rounded:
                        deflection_item.setForeground(QColor(220, 50, 50))
                    else:
                        deflection_item.setForeground(QColor(50, 150, 50))
                    deflection_item.setToolTip(
                        f"Допустимое для пояса {belt_num}: ±{tolerance:.1f} мм\n"
                        f"Максимальное допустимое: ±{max_tolerance_rounded:.1f} мм\n"
                        "Инструкция Минсвязи СССР, 1980: δ_допуск = L / 750"
                    )
                    table.setItem(row_idx, col_idx, deflection_item)

                tolerance_item = QTableWidgetItem(f"±{max_tolerance_rounded:.1f}")
                tolerance_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                tolerance_item.setToolTip(
                    "Максимальное допустимое значение среди всех поясов\n"
                    "Инструкция Минсвязи СССР, 1980: δ_допуск = L / 750"
                )
                table.setItem(row_idx, tolerance_col_idx, tolerance_item)

            logger.info(
                f"Сводная таблица заполнена: {len(sorted_heights)} высотных уровней, "
                f"{len(sorted_belts)} поясов{part_suffix}"
            )
        except Exception as e:
            logger.error(f"Ошибка при заполнении сводной таблицы: {e}", exc_info=True)

    def _fill_pivot_table(self, belt_data_by_part: dict[int, dict], is_multi_part: bool):
        """РЎРѕР·РґР°РµС‚ РѕРґРЅСѓ РёР»Рё РЅРµСЃРєРѕР»СЊРєРѕ С‚Р°Р±Р»РёС† РїСЂРѕРіРёР±РѕРІ РІ Р·Р°РІРёСЃРёРјРѕСЃС‚Рё РѕС‚ С‡РёСЃР»Р° С‡Р°СЃС‚РµР№."""
        if not belt_data_by_part:
            self.deviation_table.setRowCount(0)
            self.deviation_table.setColumnCount(0)
            self.parts_table_tabs.hide()
            self.deviation_table.show()
            return
        
        if is_multi_part:
            self.deviation_table.hide()
            self.parts_table_tabs.show()
            while self.parts_table_tabs.count():
                widget = self.parts_table_tabs.widget(0)
                self.parts_table_tabs.removeTab(0)
                if widget is not None:
                    widget.deleteLater()
            self.part_tables = {}
            for part_num in sorted(belt_data_by_part.keys()):
                part_table = QTableWidget()
                part_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
                part_table.setAlternatingRowColors(True)
                self._populate_part_table(part_table, belt_data_by_part[part_num], part_num)
                self.parts_table_tabs.addTab(part_table, f'Часть {part_num}')
                self.part_tables[part_num] = part_table
        else:
            self.parts_table_tabs.hide()
            self.deviation_table.show()
            part_num = next(iter(belt_data_by_part.keys()))
            self._populate_part_table(self.deviation_table, belt_data_by_part[part_num], part_num if len(belt_data_by_part) > 1 else None)
    
    def _plot_belt_straightness(self, figure, belt_num: int, belt_points: pd.DataFrame, 
                                part_num: Optional[int] = None,
                                part_min_height: Optional[float] = None,
                                part_max_height: Optional[float] = None):
        """РџРѕСЃС‚СЂРѕРёС‚СЊ РіСЂР°С„РёРє СЃС‚СЂРµР» РїСЂРѕРіРёР±Р° РґР»СЏ РїРѕСЏСЃР°
        
        Args:
            figure: Figure matplotlib
            belt_num: РќРѕРјРµСЂ РїРѕСЏСЃР°
            belt_points: РўРѕС‡РєРё РїРѕСЏСЃР°
            part_num: РќРѕРјРµСЂ С‡Р°СЃС‚Рё Р±Р°С€РЅРё (РѕРїС†РёРѕРЅР°Р»СЊРЅРѕ, РґР»СЏ РЅРѕСЂРјР°Р»РёР·Р°С†РёРё РІС‹СЃРѕС‚)
            part_min_height: РњРёРЅРёРјР°Р»СЊРЅР°СЏ РІС‹СЃРѕС‚Р° С‡Р°СЃС‚Рё (РґР»СЏ РЅРѕСЂРјР°Р»РёР·Р°С†РёРё)
            part_max_height: РњР°РєСЃРёРјР°Р»СЊРЅР°СЏ РІС‹СЃРѕС‚Р° С‡Р°СЃС‚Рё (РґР»СЏ РЅРѕСЂРјР°Р»РёР·Р°С†РёРё)
        """
        try:
            figure.clear()
            ax = figure.add_subplot(1, 1, 1)
            rendered = self._render_straightness_plot(ax, belt_num, belt_points, part_num=part_num,
                                                     part_min_height=part_min_height, part_max_height=part_max_height)
            if rendered:
                figure.tight_layout(rect=[0.12, 0.12, 0.97, 0.95], pad=2.0, h_pad=2.5, w_pad=3.0)
        except Exception as e:
            logger.error(f"РћС€РёР±РєР° РїСЂРё РїРѕСЃС‚СЂРѕРµРЅРёРё РіСЂР°С„РёРєР° РґР»СЏ РїРѕСЏСЃР° {belt_num}: {e}", exc_info=True)
    
    def _render_straightness_plot(self, ax, belt_num: int, belt_points: pd.DataFrame, 
                                  part_num: Optional[int] = None,
                                  part_min_height: Optional[float] = None,
                                  part_max_height: Optional[float] = None) -> bool:
        """РќР°СЂРёСЃРѕРІР°С‚СЊ РіСЂР°С„РёРє РїСЂСЏРјРѕР»РёРЅРµР№РЅРѕСЃС‚Рё РІ РїРµСЂРµРґР°РЅРЅС‹С… РѕСЃСЏС….
        
        Args:
            ax: РћСЃРё matplotlib РґР»СЏ РѕС‚СЂРёСЃРѕРІРєРё
            belt_num: РќРѕРјРµСЂ РїРѕСЏСЃР°
            belt_points: РўРѕС‡РєРё РїРѕСЏСЃР°
            part_num: РќРѕРјРµСЂ С‡Р°СЃС‚Рё Р±Р°С€РЅРё (РѕРїС†РёРѕРЅР°Р»СЊРЅРѕ, РґР»СЏ СЂР°СЃС‡РµС‚Р° РґРѕРїСѓСЃРєР°)
            part_min_height: РњРёРЅРёРјР°Р»СЊРЅР°СЏ РІС‹СЃРѕС‚Р° С‡Р°СЃС‚Рё (РґР»СЏ СЂР°СЃС‡РµС‚Р° РґРѕРїСѓСЃРєР°, РµСЃР»Рё None - РІС‹С‡РёСЃР»СЏРµС‚СЃСЏ РёР· РїРѕСЏСЃР°)
            part_max_height: РњР°РєСЃРёРјР°Р»СЊРЅР°СЏ РІС‹СЃРѕС‚Р° С‡Р°СЃС‚Рё (РґР»СЏ СЂР°СЃС‡РµС‚Р° РґРѕРїСѓСЃРєР°, РµСЃР»Рё None - РІС‹С‡РёСЃР»СЏРµС‚СЃСЏ РёР· РїРѕСЏСЃР°)
        """
        belt_sorted = belt_points.sort_values('z')
        absolute_heights = belt_sorted['z'].values

        if len(absolute_heights) < 2:
            logger.warning("РќРµРґРѕСЃС‚Р°С‚РѕС‡РЅРѕ С‚РѕС‡РµРє РЅР° РїРѕСЏСЃРµ %s РґР»СЏ РїРѕСЃС‚СЂРѕРµРЅРёСЏ РіСЂР°С„РёРєР°", belt_num)
            ax.axis('off')
            ax.text(0.5, 0.5, "\u041d\u0435\u0434\u043e\u0441\u0442\u0430\u0442\u043e\u0447\u043d\u043e \u0434\u0430\u043d\u043d\u044b\u0445", transform=ax.transAxes,
                    ha='center', va='center', fontsize=9, color='gray')
            return False

        # РћРїСЂРµРґРµР»СЏРµРј РіСЂР°РЅРёС†С‹ С‡Р°СЃС‚Рё РґР»СЏ СЂР°СЃС‡РµС‚Р° РґРѕРїСѓСЃРєР°
        # РСЃРїРѕР»СЊР·СѓРµРј РіСЂР°РЅРёС†С‹ С‡Р°СЃС‚Рё, РµСЃР»Рё РѕРЅРё РїРµСЂРµРґР°РЅС‹, РёРЅР°С‡Рµ - РіСЂР°РЅРёС†С‹ РїРѕСЏСЃР°
        if part_min_height is not None and part_max_height is not None:
            min_height = part_min_height
            max_height = part_max_height
            logger.debug(f"Р“СЂР°С„РёРє РїРѕСЏСЃР° {belt_num}, С‡Р°СЃС‚СЊ {part_num}: РёСЃРїРѕР»СЊР·СѓРµРј РіСЂР°РЅРёС†С‹ С‡Р°СЃС‚Рё "
                        f"({min_height:.2f}Рј - {max_height:.2f}Рј)")
        else:
            min_height = absolute_heights.min()
            max_height = absolute_heights.max()
            logger.debug(f"Р“СЂР°С„РёРє РїРѕСЏСЃР° {belt_num}: РёСЃРїРѕР»СЊР·СѓРµРј РіСЂР°РЅРёС†С‹ РїРѕСЏСЃР° "
                        f"({min_height:.2f}Рј - {max_height:.2f}Рј)")
        part_height = max_height - min_height
        logger.debug(f"Р“СЂР°С„РёРє РїРѕСЏСЃР° {belt_num}: РІС‹СЃРѕС‚Р° С‡Р°СЃС‚Рё={part_height:.2f}Рј, "
                    f"Р°Р±СЃРѕР»СЋС‚РЅС‹Рµ РІС‹СЃРѕС‚С‹ РѕС‚ {absolute_heights.min():.2f}Рј РґРѕ {absolute_heights.max():.2f}Рј")

        deflections = self._calculate_belt_deflections(belt_sorted, part_num=part_num,
                                                       part_min_height=part_min_height,
                                                       part_max_height=part_max_height)
        belt_length = part_height  # РСЃРїРѕР»СЊР·СѓРµРј РІС‹СЃРѕС‚Сѓ С‡Р°СЃС‚Рё/Р±Р°С€РЅРё РґР»СЏ СЂР°СЃС‡РµС‚Р° РґРѕРїСѓСЃРєР°
        from core.normatives import get_straightness_tolerance
        max_allowed_deflection_m = get_straightness_tolerance(belt_length)
        max_allowed_deflection_mm = max_allowed_deflection_m * 1000

        ax.set_xlabel("\u0421\u0442\u0440\u0435\u043b\u0430 \u043f\u0440\u043e\u0433\u0438\u0431\u0430, \u043c\u043c", fontsize=10)
        ax.set_ylabel("\u0412\u044b\u0441\u043e\u0442\u0430, \u043c", fontsize=10)
        ax.set_title(f"\u041f\u043e\u044f\u0441 {int(belt_num)}", fontsize=10, fontweight='bold')
        ax.tick_params(axis='both', labelsize=9)
        ax.xaxis.set_major_locator(ticker.MaxNLocator(6))
        ax.yaxis.set_major_locator(ticker.MaxNLocator(integer=True, nbins=8))

        max_deflection_abs = max(abs(d) for d in deflections) if deflections else 10
        x_min = -max(max_deflection_abs * 1.2, max_allowed_deflection_mm * 1.5)
        x_max = max(max_deflection_abs * 1.2, max_allowed_deflection_mm * 1.5)
        ax.set_xlim(x_min, x_max)

        # РСЃРїРѕР»СЊР·СѓРµРј Р°Р±СЃРѕР»СЋС‚РЅС‹Рµ РІС‹СЃРѕС‚С‹ РґР»СЏ РіСЂР°С„РёРєР° (РєР°Рє РІ С‚Р°Р±Р»РёС†Рµ РїСЂСЏРјРѕР»РёРЅРµР№РЅРѕСЃС‚Рё)
        height_range = absolute_heights.max() - absolute_heights.min()
        y_min = absolute_heights.min() - height_range * 0.05
        y_max = absolute_heights.max() + height_range * 0.05
        ax.set_ylim(y_min, y_max)

        ax.axvline(x=0, color='black', linewidth=1.0, linestyle='-', zorder=1)
        ax.axvline(x=-max_allowed_deflection_mm, color='gray', linewidth=1.5, linestyle='--',
                   zorder=2, alpha=0.7, label=f"\u0414\u043e\u043f\u0443\u0441\u043a \u00b1{max_allowed_deflection_mm:.1f} \u043c\u043c")
        ax.axvline(x=max_allowed_deflection_mm, color='gray', linewidth=1.5, linestyle='--',
                   zorder=2, alpha=0.7)

        ax.grid(True, axis='x', linestyle=':', linewidth=0.5, alpha=0.5, color='gray', zorder=0)
        ax.grid(True, axis='y', linestyle=':', linewidth=0.5, alpha=0.3, color='gray', zorder=0)

        # РСЃРїРѕР»СЊР·СѓРµРј Р°Р±СЃРѕР»СЋС‚РЅС‹Рµ РІС‹СЃРѕС‚С‹ РґР»СЏ РіСЂР°С„РёРєР° (РєР°Рє РІ С‚Р°Р±Р»РёС†Рµ РїСЂСЏРјРѕР»РёРЅРµР№РЅРѕСЃС‚Рё)
        ax.plot(deflections, absolute_heights,
                color='red', linewidth=1.5, linestyle='-',
                marker='o', markersize=4, markerfacecolor='red',
                markeredgecolor='white', markeredgewidth=0.5,
                label="\u0424\u0430\u043a\u0442\u0438\u0447\u0435\u0441\u043a\u0438\u0439 \u043f\u0440\u043e\u0433\u0438\u0431", zorder=5)

        ax.legend(loc='best', fontsize=8, framealpha=0.9, frameon=True)
        ax.spines['top'].set_linewidth(0.5)
        ax.spines['right'].set_linewidth(0.5)
        ax.spines['bottom'].set_linewidth(1.0)
        ax.spines['left'].set_linewidth(1.0)

        return True
    
    def _calculate_belt_deflections(self, belt_points: pd.DataFrame, part_num: Optional[int] = None,
                                   part_min_height: Optional[float] = None,
                                   part_max_height: Optional[float] = None):
        """Р Р°СЃСЃС‡РёС‚Р°С‚СЊ СЃС‚СЂРµР»С‹ РїСЂРѕРіРёР±Р° РґР»СЏ РїРѕСЏСЃР°
        
        РЎРѕРіР»Р°СЃРЅРѕ РЅРѕСЂРјР°С‚РёРІР°Рј (РРЅСЃС‚СЂСѓРєС†РёСЏ РњРёРЅСЃРІСЏР·Рё РЎРЎРЎР , 1980):
        - Р‘Р°Р·РѕРІР°СЏ Р»РёРЅРёСЏ СЃС‚СЂРѕРёС‚СЃСЏ С‡РµСЂРµР· РЅРёР¶РЅСЋСЋ Рё РІРµСЂС…РЅСЋСЋ С‚РѕС‡РєРё РїРѕСЏСЃР° **РІ РїСЂРµРґРµР»Р°С… С‡Р°СЃС‚Рё**
        - РЎС‚СЂРµР»Р° РїСЂРѕРіРёР±Р° - СЂР°СЃСЃС‚РѕСЏРЅРёРµ РѕС‚ РєР°Р¶РґРѕР№ С‚РѕС‡РєРё РїРѕСЏСЃР° РґРѕ СЌС‚РѕР№ РїСЂСЏРјРѕР№
        - Р”РѕРїСѓСЃС‚РёРјР°СЏ СЃС‚СЂРµР»Р° РїСЂРѕРіРёР±Р°: Оґ_РґРѕРїСѓСЃРє = L / 750, РіРґРµ L - РґР»РёРЅР° РїРѕСЏСЃР° (РІС‹СЃРѕС‚Р° С‡Р°СЃС‚Рё)
        - РџРµСЂРІР°СЏ (РЅРёР¶РЅСЏСЏ) Рё РїРѕСЃР»РµРґРЅСЏСЏ (РІРµСЂС…РЅСЏСЏ) С‚РѕС‡РєР° РїРѕСЏСЃР° РІ С‡Р°СЃС‚Рё РІСЃРµРіРґР° РёРјРµСЋС‚ РѕС‚РєР»РѕРЅРµРЅРёРµ 0,
          С‚Р°Рє РєР°Рє РѕРЅРё СЏРІР»СЏСЋС‚СЃСЏ РѕРїРѕСЂРЅС‹РјРё С‚РѕС‡РєР°РјРё РґР»СЏ РїРѕСЃС‚СЂРѕРµРЅРёСЏ Р±Р°Р·РѕРІРѕР№ Р»РёРЅРёРё
        
        Р”Р»СЏ СЃРѕСЃС‚Р°РІРЅРѕР№ Р±Р°С€РЅРё СЂР°СЃС‡РµС‚ РІС‹РїРѕР»РЅСЏРµС‚СЃСЏ С‚РѕР»СЊРєРѕ РґР»СЏ С‚РѕС‡РµРє СЌС‚РѕР№ С‡Р°СЃС‚Рё.
        РћРїРѕСЂРЅС‹Рµ С‚РѕС‡РєРё РѕРїСЂРµРґРµР»СЏСЋС‚СЃСЏ РєР°Рє С‚РѕС‡РєРё РЅР° РјРёРЅРёРјР°Р»СЊРЅРѕР№ Рё РјР°РєСЃРёРјР°Р»СЊРЅРѕР№ РІС‹СЃРѕС‚Рµ С‡Р°СЃС‚Рё.
        
        Args:
            belt_points: РўРѕС‡РєРё РїРѕСЏСЃР° (СѓР¶Рµ РѕС‚С„РёР»СЊС‚СЂРѕРІР°РЅРЅС‹Рµ РїРѕ С‡Р°СЃС‚Рё, РµСЃР»Рё СЌС‚Рѕ СЃРѕСЃС‚Р°РІРЅР°СЏ Р±Р°С€РЅСЏ)
            part_num: РќРѕРјРµСЂ С‡Р°СЃС‚Рё Р±Р°С€РЅРё (РѕРїС†РёРѕРЅР°Р»СЊРЅРѕ, РґР»СЏ СЃРѕСЃС‚Р°РІРЅРѕР№ Р±Р°С€РЅРё)
            part_min_height: РњРёРЅРёРјР°Р»СЊРЅР°СЏ РІС‹СЃРѕС‚Р° С‡Р°СЃС‚Рё (РґР»СЏ РѕРїСЂРµРґРµР»РµРЅРёСЏ РѕРїРѕСЂРЅРѕР№ С‚РѕС‡РєРё)
            part_max_height: РњР°РєСЃРёРјР°Р»СЊРЅР°СЏ РІС‹СЃРѕС‚Р° С‡Р°СЃС‚Рё (РґР»СЏ РѕРїСЂРµРґРµР»РµРЅРёСЏ РѕРїРѕСЂРЅРѕР№ С‚РѕС‡РєРё)
            
        Returns:
            List[float]: РЎРїРёСЃРѕРє СЃС‚СЂРµР» РїСЂРѕРіРёР±Р° (РІ РјРј) РґР»СЏ РєР°Р¶РґРѕР№ С‚РѕС‡РєРё
        """
        # РЎРѕСЂС‚РёСЂСѓРµРј РїРѕ РІС‹СЃРѕС‚Рµ
        belt_sorted = belt_points.sort_values('z').copy()
        
        if len(belt_sorted) < 2:
            return [0.0] * len(belt_sorted)
        belt_numbers = pd.to_numeric(belt_sorted.get('belt'), errors='coerce').dropna()
        if not belt_numbers.empty:
            profile_deflections = self._get_profile_deflections(
                belt_sorted,
                int(belt_numbers.iloc[0]),
                part_num,
            )
            if profile_deflections is not None:
                return profile_deflections
        return [float(value) for value in calculate_canonical_belt_deflections(belt_sorted)]

    
    def _calculate_belt_angle(self, belt_points: pd.DataFrame):
        """Р Р°СЃСЃС‡РёС‚Р°С‚СЊ СѓРіРѕР» РЅР°РєР»РѕРЅР° РїРѕСЏСЃР° РѕС‚РЅРѕСЃРёС‚РµР»СЊРЅРѕ РІРµСЂС‚РёРєР°Р»Рё
        
        Args:
            belt_points: РўРѕС‡РєРё РїРѕСЏСЃР°
            
        Returns:
            float: РЈРіРѕР» РІ СЂР°РґРёР°РЅР°С…
        """
        # РќР°С…РѕРґРёРј РїРµСЂРІСѓСЋ Рё РїРѕСЃР»РµРґРЅСЋСЋ С‚РѕС‡РєРё РїРѕ РІС‹СЃРѕС‚Рµ
        belt_sorted = belt_points.sort_values('z')
        
        if len(belt_sorted) < 2:
            return 0.0
        
        first_point = belt_sorted.iloc[0]
        last_point = belt_sorted.iloc[-1]
        
        # Р’РµРєС‚РѕСЂ РїРѕСЏСЃР°
        belt_vec = np.array([
            last_point['x'] - first_point['x'],
            last_point['y'] - first_point['y'],
            last_point['z'] - first_point['z']
        ])
        
        # Р’РµСЂС‚РёРєР°Р»СЊРЅС‹Р№ РІРµРєС‚РѕСЂ [0, 0, 1]
        vertical_vec = np.array([0.0, 0.0, 1.0])
        
        # РЈРіРѕР» РјРµР¶РґСѓ РІРµРєС‚РѕСЂР°РјРё
        cos_angle = np.dot(belt_vec, vertical_vec) / (np.linalg.norm(belt_vec) * np.linalg.norm(vertical_vec))
        cos_angle = np.clip(cos_angle, -1.0, 1.0)
        angle = np.arccos(cos_angle)
        
        # РЈРіРѕР» РѕС‚РєР»РѕРЅРµРЅРёСЏ РѕС‚ РІРµСЂС‚РёРєР°Р»Рё
        deviation_angle = np.pi / 2 - angle if angle < np.pi / 2 else angle - np.pi / 2
        
        return deviation_angle
    
    def _fill_belt_table(self, table, belt_num: int, belt_points: pd.DataFrame):
        """Р—Р°РїРѕР»РЅРёС‚СЊ С‚Р°Р±Р»РёС†Сѓ СЃС‚СЂРµР» РїСЂРѕРіРёР±Р° РґР»СЏ РїРѕСЏСЃР°
        
        Args:
            table: QTableWidget
            belt_num: РќРѕРјРµСЂ РїРѕСЏСЃР°
            belt_points: РўРѕС‡РєРё РїРѕСЏСЃР°
        """
        try:
            logger.info(f"Р—Р°РїРѕР»РЅРµРЅРёРµ С‚Р°Р±Р»РёС†С‹ РґР»СЏ РїРѕСЏСЃР° {belt_num}: {len(belt_points)} С‚РѕС‡РµРє")
            table.setRowCount(0)  # РћС‡РёС‰Р°РµРј С‚Р°Р±Р»РёС†Сѓ
            
            # РЎРѕСЂС‚РёСЂСѓРµРј РїРѕ РІС‹СЃРѕС‚Рµ
            belt_sorted = belt_points.sort_values('z')
            deflections = self._calculate_belt_deflections(belt_sorted)
            
            if not deflections:
                logger.warning("РќРµС‚ РґР°РЅРЅС‹С… Рѕ РїСЂРѕРіРёР±Р°С… РґР»СЏ С‚Р°Р±Р»РёС†С‹")
                return
            
            # Р Р°СЃСЃС‡РёС‚С‹РІР°РµРј РґР»РёРЅСѓ РїРѕСЏСЃР° РґР»СЏ РЅРѕСЂРјР°С‚РёРІР° (РІС‹СЃРѕС‚Р° РїРѕСЏСЃР°)
            belt_length = belt_sorted['z'].max() - belt_sorted['z'].min()
            from core.normatives import get_straightness_tolerance
            max_allowed_deflection_m = get_straightness_tolerance(belt_length)
            max_allowed_deflection_mm = max_allowed_deflection_m * 1000  # РІ РјРј
            
            for i, (idx, point) in enumerate(belt_sorted.iterrows()):
                row = table.rowCount()
                table.insertRow(row)
                
                # Р’С‹СЃРѕС‚Р°
                height_item = QTableWidgetItem(f"{point['z']:.2f}")
                height_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                table.setItem(row, 0, height_item)
                
                # РЎС‚СЂРµР»Р° РїСЂРѕРіРёР±Р°
                deflection = deflections[i] if i < len(deflections) else 0.0
                deflection_item = QTableWidgetItem(f"{deflection:+.2f}")
                deflection_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                
                # Р¦РІРµС‚РѕРІР°СЏ РёРЅРґРёРєР°С†РёСЏ
                if abs(deflection) > max_allowed_deflection_mm:
                    # РџСЂРµРІС‹С€РµРЅРёРµ РЅРѕСЂРјР°С‚РёРІР°
                    deflection_item.setForeground(QColor(220, 50, 50))  # РљСЂР°СЃРЅС‹Р№
                else:
                    # Р’ РЅРѕСЂРјРµ
                    deflection_item.setForeground(QColor(50, 150, 50))  # Р—РµР»РµРЅС‹Р№
                
                table.setItem(row, 1, deflection_item)
                
                # Р”РѕРїСѓСЃС‚РёРјРѕРµ РѕС‚РєР»РѕРЅРµРЅРёРµ (РЅРѕСЂРјР°С‚РёРІ L/750)
                tolerance_item = QTableWidgetItem(f"{max_allowed_deflection_mm:.2f}")
                tolerance_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                tolerance_item.setToolTip(f"РРЅСЃС‚СЂСѓРєС†РёСЏ РњРёРЅСЃРІСЏР·Рё РЎРЎРЎР , 1980: Оґ_РґРѕРїСѓСЃРє = L / 750 = {max_allowed_deflection_mm:.2f} РјРј\nРіРґРµ L = {belt_length:.3f} Рј - РґР»РёРЅР° РїРѕСЏСЃР° (РІС‹СЃРѕС‚Р°)")
                table.setItem(row, 2, tolerance_item)
                
                logger.debug(f"РЎС‚СЂРѕРєР° {row}: H={point['z']:.2f}Рј, Def={deflection:+.2f}РјРј, "
                            f"Р”РѕРїСѓСЃРє={max_allowed_deflection_mm:.2f}РјРј")
            
            logger.info(f"РўР°Р±Р»РёС†Р° Р·Р°РїРѕР»РЅРµРЅР° {table.rowCount()} СЃС‚СЂРѕРєР°РјРё РґР»СЏ РїРѕСЏСЃР° {belt_num}")
            
        except Exception as e:
            logger.error(f"РћС€РёР±РєР° РїСЂРё Р·Р°РїРѕР»РЅРµРЅРёРё С‚Р°Р±Р»РёС†С‹ РґР»СЏ РїРѕСЏСЃР° {belt_num}: {e}", exc_info=True)
    
    def get_all_belts_data(self):
        """РџРѕР»СѓС‡РёС‚СЊ РґР°РЅРЅС‹Рµ СЃС‚СЂРµР» РїСЂРѕРіРёР±Р° РґР»СЏ РІСЃРµС… РїРѕСЏСЃРѕРІ, СЃРіСЂСѓРїРїРёСЂРѕРІР°РЅРЅС‹Рµ РїРѕ С‡Р°СЃС‚СЏРј Р±Р°С€РЅРё
        
        Returns:
            Dict[int, Dict]: РЎР»РѕРІР°СЂСЊ СЃ РєР»СЋС‡Р°РјРё - РЅРѕРјРµСЂР°РјРё С‡Р°СЃС‚РµР№, Р·РЅР°С‡РµРЅРёСЏРјРё - СЃР»РѕРІР°СЂСЏРјРё:
            {
                part_num: {
                    'min_height': float,  # РњРёРЅРёРјР°Р»СЊРЅР°СЏ РІС‹СЃРѕС‚Р° С‡Р°СЃС‚Рё
                    'max_height': float,  # РњР°РєСЃРёРјР°Р»СЊРЅР°СЏ РІС‹СЃРѕС‚Р° С‡Р°СЃС‚Рё
                    'belts': Dict[int, List[Dict]]  # Р”Р°РЅРЅС‹Рµ РїРѕ РїРѕСЏСЃР°Рј (РЅРѕРјРµСЂ РїРѕСЏСЃР° -> СЃРїРёСЃРѕРє РґР°РЅРЅС‹С…)
                }
            }
        """
        if self.data is None or self.data.empty or 'belt' not in self.data.columns:
            return {}

        tower_parts_info = self.processed_data.get('tower_parts_info') if isinstance(self.processed_data, dict) else None
        return get_preferred_straightness_part_map(
            self.processed_data.get('straightness_profiles') if isinstance(self.processed_data, dict) else None,
            points=self._get_working_data(),
            tower_parts_info=tower_parts_info,
        )

        all_data_by_parts = {}
        
        if self.data is None or self.data.empty or 'belt' not in self.data.columns:
            return all_data_by_parts
        
        # РСЃРєР»СЋС‡Р°РµРј С‚РѕС‡РєРё standing
        data_without_station = self._get_working_data()
        
        # РџСЂРѕРІРµСЂСЏРµРј, СЏРІР»СЏРµС‚СЃСЏ Р»Рё Р±Р°С€РЅСЏ СЃРѕСЃС‚Р°РІРЅРѕР№
        profiles = self.processed_data.get('straightness_profiles') if isinstance(self.processed_data, dict) else None
        if isinstance(profiles, list) and profiles:
            for profile in profiles:
                try:
                    part_id = int(profile.get('part_number', 1))
                    belt_id = int(profile.get('belt', 0))
                except (TypeError, ValueError):
                    continue
                part_entry = all_data_by_parts.setdefault(part_id, {
                    'min_height': float(profile.get('part_min_height', 0.0)),
                    'max_height': float(profile.get('part_max_height', 0.0)),
                    'belts': {},
                })
                part_entry['belts'][belt_id] = [
                    {
                        'height': float(point.get('z', 0.0)),
                        'deflection': float(point.get('deflection_mm', 0.0)),
                        'tolerance': float(profile.get('tolerance_mm', 0.0)),
                    }
                    for point in profile.get('points', [])
                ]
            if all_data_by_parts:
                return all_data_by_parts

        has_memberships = 'tower_part_memberships' in data_without_station.columns and data_without_station['tower_part_memberships'].notna().any()
        has_numeric_parts = 'tower_part' in data_without_station.columns and data_without_station['tower_part'].notna().any()
        is_composite = has_memberships or has_numeric_parts
        
        if is_composite:
            unique_parts = self._collect_unique_parts(data_without_station)
            if not unique_parts and has_numeric_parts:
                unique_parts = sorted(data_without_station['tower_part'].dropna().unique())
            if not unique_parts:
                unique_parts = [1]
        else:
            unique_parts = [1]
        
        from core.normatives import get_straightness_tolerance
        
        # Р“СЂСѓРїРїРёСЂСѓРµРј РїРѕСЏСЃР° РїРѕ С‡Р°СЃС‚СЏРј РґР»СЏ СЃРѕСЃС‚Р°РІРЅРѕР№ Р±Р°С€РЅРё
        if is_composite:
            for part_num in unique_parts:
                # РџРѕР»СѓС‡Р°РµРј РїРѕСЏСЃР° СЌС‚РѕР№ С‡Р°СЃС‚Рё
                part_mask = data_without_station.apply(lambda row: self._row_has_part(row, part_num), axis=1)
                part_data = data_without_station[part_mask].copy()
                part_belts = sorted(part_data['belt'].dropna().unique())
                
                # РќР°С…РѕРґРёРј РјРёРЅРёРјР°Р»СЊРЅСѓСЋ Рё РјР°РєСЃРёРјР°Р»СЊРЅСѓСЋ РІС‹СЃРѕС‚Сѓ РґР»СЏ СЌС‚РѕР№ С‡Р°СЃС‚Рё
                part_min_height = float(part_data['z'].min())
                part_max_height = float(part_data['z'].max())
                part_height = part_max_height - part_min_height
                
                # Р Р°СЃСЃС‡РёС‚С‹РІР°РµРј РґРѕРїСѓСЃС‚РёРјРѕРµ Р·РЅР°С‡РµРЅРёРµ РґР»СЏ С‡Р°СЃС‚Рё
                max_allowed_deflection_m = get_straightness_tolerance(part_height)
                max_allowed_deflection_mm = max_allowed_deflection_m * 1000
                
                belts_data = {}
                for belt_num in part_belts:
                    belt_points = part_data[part_data['belt'] == belt_num]
                    
                    if len(belt_points) < 2:
                        continue
                    
                    belt_sorted = belt_points.sort_values('z')
                    deflections = self._calculate_belt_deflections(belt_sorted, part_num=int(part_num),
                                                                  part_min_height=part_min_height,
                                                                  part_max_height=part_max_height)
                    
                    belt_data = []
                    for i, (idx, point) in enumerate(belt_sorted.iterrows()):
                        belt_data.append({
                            'height': float(point['z']),  # РђР±СЃРѕР»СЋС‚РЅР°СЏ РІС‹СЃРѕС‚Р°
                            'deflection': float(deflections[i] if i < len(deflections) else 0),
                            'tolerance': max_allowed_deflection_mm
                        })
                    
                    belts_data[int(belt_num)] = belt_data
                
                if belts_data:  # Р”РѕР±Р°РІР»СЏРµРј С‚РѕР»СЊРєРѕ РµСЃР»Рё РµСЃС‚СЊ РґР°РЅРЅС‹Рµ
                    part_id = int(part_num)
                    all_data_by_parts[part_id] = {
                        'min_height': part_min_height,
                        'max_height': part_max_height,
                        'belts': belts_data
                    }
        else:
            # РћР±С‹С‡РЅР°СЏ Р±Р°С€РЅСЏ - РѕР±СЂР°Р±Р°С‚С‹РІР°РµРј РІСЃРµ РїРѕСЏСЃР° РєР°Рє РѕРґРЅСѓ С‡Р°СЃС‚СЊ
            belts = sorted(data_without_station['belt'].dropna().unique())
            tower_min_height = float(data_without_station['z'].min())
            tower_max_height = float(data_without_station['z'].max())
            tower_height = tower_max_height - tower_min_height
            
            max_allowed_deflection_m = get_straightness_tolerance(tower_height)
            max_allowed_deflection_mm = max_allowed_deflection_m * 1000
            
            belts_data = {}
            for belt_num in belts:
                belt_points = data_without_station[data_without_station['belt'] == belt_num]
                
                if len(belt_points) < 2:
                    continue
                
                belt_sorted = belt_points.sort_values('z')
                deflections = self._calculate_belt_deflections(belt_sorted)
                
                belt_data = []
                for i, (idx, point) in enumerate(belt_sorted.iterrows()):
                    belt_data.append({
                        'height': float(point['z']),
                        'deflection': float(deflections[i] if i < len(deflections) else 0),
                        'tolerance': max_allowed_deflection_mm
                    })
                
                belts_data[int(belt_num)] = belt_data
            
            if belts_data:
                all_data_by_parts[1] = {
                    'min_height': tower_min_height,
                    'max_height': tower_max_height,
                    'belts': belts_data
                }
        
        return all_data_by_parts
    
    def get_all_figures_for_pdf(self):
        """РџРѕР»СѓС‡РёС‚СЊ РІСЃРµ figure РѕР±СЉРµРєС‚С‹ РґР»СЏ СЃРѕС…СЂР°РЅРµРЅРёСЏ РІ PDF
        
        Returns:
            List[Tuple[int, Figure]]: РЎРїРёСЃРѕРє РєРѕСЂС‚РµР¶РµР№ (РЅРѕРјРµСЂ_РїРѕСЏСЃР°, figure)
        """
        figures = []
        
        working_data = self._get_working_data()
        if working_data.empty or 'belt' not in working_data.columns:
            return figures

        belts = sorted(working_data['belt'].dropna().unique())
        
        for belt_num in belts:
            belt_points = working_data[working_data['belt'] == belt_num]
            
            if len(belt_points) < 2:
                continue
            
            # РЎРѕР·РґР°РµРј figure РґР»СЏ СЌС‚РѕРіРѕ РїРѕСЏСЃР°
            figure = Figure(figsize=(8, 6), dpi=100)
            self._plot_belt_straightness(figure, belt_num, belt_points, part_num=None)
            figures.append((int(belt_num), figure))
        
        return figures
    
    def get_combined_figure_for_pdf(self):
        """РЎРѕР·РґР°С‚СЊ РѕР±СЉРµРґРёРЅРµРЅРЅС‹Р№ РіСЂР°С„РёРє РІСЃРµС… РїРѕСЏСЃРѕРІ РґР»СЏ PDF
        
        Returns:
            Figure: Matplotlib figure СЃ СЃСѓР±РїР»РѕС‚Р°РјРё РґР»СЏ РІСЃРµС… РїРѕСЏСЃРѕРІ
        """
        working_data = self._get_working_data()
        if working_data.empty or 'belt' not in working_data.columns:
            return None

        belts = sorted(working_data['belt'].dropna().unique())
        
        if len(belts) == 0:
            return None
        
        # РћРїСЂРµРґРµР»СЏРµРј СЂР°Р·РјРµСЂ СЃРµС‚РєРё
        num_belts = len(belts)
        
        # РЎРѕР·РґР°РµРј СЃРµС‚РєСѓ РіСЂР°С„РёРєРѕРІ: 2 РєРѕР»РѕРЅРєРё, СЃС‚РѕР»СЊРєРѕ СЃС‚СЂРѕРє, СЃРєРѕР»СЊРєРѕ РЅСѓР¶РЅРѕ
        cols = 2
        rows = (num_belts + cols - 1) // cols  # РћРєСЂСѓРіР»СЏРµРј РІРІРµСЂС…
        
        # РЎРѕР·РґР°РµРј figure СЃ СЃСѓР±РїР»РѕС‚Р°РјРё
        figure = Figure(figsize=(12, max(6, 4.5 * rows)), dpi=120)
        subplot_pos = 1

        for belt_num in belts:
            belt_points = working_data[working_data['belt'] == belt_num]
            if len(belt_points) < 2:
                continue

            ax = figure.add_subplot(rows, cols, subplot_pos)
            rendered = self._render_straightness_plot(ax, belt_num, belt_points, part_num=None)
            if not rendered:
                figure.delaxes(ax)
                continue

            subplot_pos += 1

        if subplot_pos == 1:
            return None

        figure.tight_layout(pad=2.0, h_pad=2.5, w_pad=2.0)
        return figure

    def get_grouped_figures_for_pdf(self, group_size: int = 2):
        """РџРѕР»СѓС‡РёС‚СЊ С„РёРіСѓСЂС‹ СЃ РіСЂР°С„РёРєР°РјРё, СЃРіСЂСѓРїРїРёСЂРѕРІР°РЅРЅС‹РјРё РїРѕ РЅРµСЃРєРѕР»СЊРєРѕ РїРѕСЏСЃРѕРІ."""
        working_data = self._get_working_data()
        if working_data.empty or 'belt' not in working_data.columns:
            return []

        belts = sorted(working_data['belt'].dropna().unique())
        if not belts:
            return []

        group_size = max(1, group_size)
        grouped_figures = []

        for start in range(0, len(belts), group_size):
            belt_group = belts[start:start + group_size]
            cols = len(belt_group)
            figure = Figure(figsize=(12 if cols > 1 else 8, 5.5), dpi=120)
            subplot_pos = 1
            plotted_belts: list[int] = []

            for belt_num in belt_group:
                belt_points = working_data[working_data['belt'] == belt_num]
                if len(belt_points) < 2:
                    continue

                ax = figure.add_subplot(1, cols, subplot_pos)
                rendered = self._render_straightness_plot(ax, belt_num, belt_points, part_num=None)
                if not rendered:
                    figure.delaxes(ax)
                    continue

                plotted_belts.append(int(belt_num))
                subplot_pos += 1

            if not plotted_belts:
                plt.close(figure)
                continue

            figure.tight_layout(pad=2.0, w_pad=2.0)
            grouped_figures.append((tuple(plotted_belts), figure))

        return grouped_figures
    
    def get_part_figures_for_pdf(self, part_num: int, group_size: int = 2):
        """РџРѕР»СѓС‡РёС‚СЊ С„РёРіСѓСЂС‹ СЃ РіСЂР°С„РёРєР°РјРё РґР»СЏ РєРѕРЅРєСЂРµС‚РЅРѕР№ С‡Р°СЃС‚Рё Р±Р°С€РЅРё.
        
        Args:
            part_num: РќРѕРјРµСЂ С‡Р°СЃС‚Рё Р±Р°С€РЅРё
            group_size: РљРѕР»РёС‡РµСЃС‚РІРѕ РїРѕСЏСЃРѕРІ РЅР° РѕРґРЅРѕРј РіСЂР°С„РёРєРµ
            
        Returns:
            List[Tuple[Tuple[int, ...], Figure]]: РЎРїРёСЃРѕРє РєРѕСЂС‚РµР¶РµР№ (РіСЂСѓРїРїР°_РїРѕСЏСЃРѕРІ, figure)
        """
        if not hasattr(self, '_graph_entries_by_part') or not self._graph_entries_by_part:
            return []
        
        entries = self._graph_entries_by_part.get(part_num, [])
        if not entries:
            return []
        
        # РџРѕР»СѓС‡Р°РµРј СЃРїРёСЃРѕРє РїРѕСЏСЃРѕРІ РґР»СЏ СЌС‚РѕР№ С‡Р°СЃС‚Рё
        part_belts = sorted([entry[0] for entry in entries])
        if not part_belts:
            return []
        
        group_size = max(1, group_size)
        grouped_figures = []
        
        for start in range(0, len(part_belts), group_size):
            belt_group = part_belts[start:start + group_size]
            cols = len(belt_group)
            figure = Figure(figsize=(12 if cols > 1 else 8, 5.5), dpi=120)
            subplot_pos = 1
            plotted_belts: list[int] = []
            
            # РЎРѕР·РґР°РµРј СЃР»РѕРІР°СЂСЊ РґР»СЏ Р±С‹СЃС‚СЂРѕРіРѕ РїРѕРёСЃРєР° Р·Р°РїРёСЃРµР№ РїРѕ РЅРѕРјРµСЂСѓ РїРѕСЏСЃР°
            belt_to_entry = {entry[0]: entry for entry in entries}
            
            for belt_num in belt_group:
                entry = belt_to_entry.get(belt_num)
                if not entry:
                    continue
                
                _, belt_points, part_id, part_min_height, part_max_height = entry
                
                if len(belt_points) < 2:
                    continue
                
                ax = figure.add_subplot(1, cols, subplot_pos)
                rendered = self._render_straightness_plot(
                    ax, belt_num, belt_points, 
                    part_num=part_id,
                    part_min_height=part_min_height,
                    part_max_height=part_max_height
                )
                if not rendered:
                    figure.delaxes(ax)
                    continue
                
                plotted_belts.append(int(belt_num))
                subplot_pos += 1
            
            if not plotted_belts:
                plt.close(figure)
                continue
            
            figure.tight_layout(pad=2.0, w_pad=2.0)
            grouped_figures.append((tuple(plotted_belts), figure))
        
        return grouped_figures

    
