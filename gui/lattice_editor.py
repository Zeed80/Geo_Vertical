from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QLabel, 
    QGroupBox, QFormLayout, QDoubleSpinBox
)
from core.db.profile_manager import ProfileManager
from core.tower_generator import TowerSegmentSpec

class LatticeEditorWidget(QWidget):
    def __init__(self, profile_manager: ProfileManager, parent=None):
        super().__init__(parent)
        self.profile_manager = profile_manager
        self.current_segment: TowerSegmentSpec = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Pattern Selection
        pattern_group = QGroupBox("Тип решетки")
        pattern_layout = QFormLayout()
        self.pattern_combo = QComboBox()
        for label, key in [
            ("Крест",       "cross"),
            ("Z-раскос",    "z_brace"),
            ("K-раскос",    "k_brace"),
            ("Портальная",  "portal"),
            ("Без решетки", "none"),
        ]:
            self.pattern_combo.addItem(label, key)
        self.pattern_combo.currentIndexChanged.connect(self._on_pattern_changed)
        pattern_layout.addRow("Схема:", self.pattern_combo)
        pattern_group.setLayout(pattern_layout)
        layout.addWidget(pattern_group)
        
        # Profile Selection
        profiles_group = QGroupBox("Профили элементов")
        profiles_layout = QFormLayout()
        
        self.leg_profile_combo = QComboBox()
        self.brace_profile_combo = QComboBox()
        
        self._populate_profiles()
        
        self.leg_profile_combo.currentTextChanged.connect(self._on_profile_changed)
        self.brace_profile_combo.currentTextChanged.connect(self._on_profile_changed)
        
        profiles_layout.addRow("Пояса:", self.leg_profile_combo)
        profiles_layout.addRow("Раскосы:", self.brace_profile_combo)
        profiles_group.setLayout(profiles_layout)
        layout.addWidget(profiles_group)
        
        layout.addStretch()

    def _populate_profiles(self):
        # Fetch pipes and angles from DB
        pipes = self.profile_manager.get_profiles_by_type("pipe")
        angles = self.profile_manager.get_profiles_by_type("angle")
        channels = self.profile_manager.get_profiles_by_type("channel")
        
        # Словарь русских названий
        type_names = {
            "pipe": "Труба",
            "angle": "Уголок",
            "channel": "Швеллер",
            "i_beam": "Двутавр",
        }
        
        items = ["Не задано"]
        for p in pipes:
            type_name = type_names.get(p['type'], p['type'])
            items.append(f"{type_name} {p['designation']} ({p['standard']})")
        for a in angles:
            type_name = type_names.get(a['type'], a['type'])
            items.append(f"{type_name} {a['designation']} ({a['standard']})")
        for c in channels:
            type_name = type_names.get(c['type'], c['type'])
            items.append(f"{type_name} {c['designation']} ({c['standard']})")
            
        self.leg_profile_combo.addItems(items)
        self.brace_profile_combo.addItems(items)

    def set_segment(self, segment: TowerSegmentSpec):
        self.current_segment = segment
        if not segment:
            self.setEnabled(False)
            return
        self.setEnabled(True)
        
        # Load values
        idx = self.pattern_combo.findData(segment.lattice_type)
        if idx >= 0:
            self.pattern_combo.setCurrentIndex(idx)
            
        # Load profiles (simplified)
        spec = segment.profile_spec
        leg_p = spec.get("leg_profile", "Не задано")
        brace_p = spec.get("brace_profile", "Не задано")
        
        self.leg_profile_combo.setCurrentText(leg_p)
        self.brace_profile_combo.setCurrentText(brace_p)

    def _on_pattern_changed(self, _index):
        if self.current_segment:
            self.current_segment.lattice_type = self.pattern_combo.currentData()

    def _on_profile_changed(self, _):
        if self.current_segment:
            self.current_segment.profile_spec["leg_profile"] = self.leg_profile_combo.currentText()
            self.current_segment.profile_spec["brace_profile"] = self.brace_profile_combo.currentText()
