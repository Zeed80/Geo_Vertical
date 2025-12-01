import numpy as np
from typing import List, Optional, Tuple
from core.tower_generator import TowerBlueprintV2, TowerSegmentSpec, TowerSectionSpec
from core.structure.model import TowerModel, MemberType
from core.lattice_generator import LatticeGenerator, LatticePattern

from core.db.profile_manager import ProfileManager

class TowerModelBuilder:
    def __init__(self, blueprint: TowerBlueprintV2, profile_manager: Optional[ProfileManager] = None):
        self.blueprint = blueprint
        self.profile_manager = profile_manager or ProfileManager()

    def _resolve_profile(self, designation: str) -> Optional[dict]:
        if not designation or designation == "Не задано":
            return None
        # designation format "type name (standard)" or just name?
        # LatticeEditor uses: f"{p['type']} {p['designation']} ({p['standard']})"
        # We need to parse this back or store simpler ID.
        # Let's try to parse: "pipe 57x3 (GOST 8732-78)"
        try:
            parts = designation.split("(")
            if len(parts) < 2: return None
            standard = parts[1].rstrip(")")
            
            type_and_name = parts[0].strip().split(" ")
            p_type = type_and_name[0]
            p_name = " ".join(type_and_name[1:])
            
            return self.profile_manager.get_profile_by_designation(standard, p_name)
        except Exception:
            return None

    def build(self) -> TowerModel:
        if not self.blueprint:
            return TowerModel()
            
        model = TowerModel()
        gen = LatticeGenerator(model)
        
        current_z = 0.0
        prev_nodes = []
        
        # Add fixed base nodes
        # ... (rest is same, but calling generate_section_lattice with profiles)
        
        # Assuming 4 faces for now (should come from blueprint)
        # Use first segment faces
        first_seg = self.blueprint.segments[0]
        faces = first_seg.faces
        base_size = first_seg.base_size
        r = base_size / 2.0 # Radius for prism/pyramid
        
        # Rotation
        rot_rad = np.radians(self.blueprint.base_rotation_deg)
        
        for i in range(faces):
            angle = 2 * np.pi * i / faces + rot_rad
            x = r * np.cos(angle)
            y = r * np.sin(angle)
            # Fixed nodes at Z=0
            nid = model.add_node(x, y, 0.0, is_fixed=True)
            prev_nodes.append(nid)
            
        # Iterate segments
        for segment in self.blueprint.segments:
            sections = segment.sections
            # If no sections defined (legacy or simple), create one covering the whole segment
            if not sections:
                l_type = getattr(segment, 'lattice_type', 'cross')
                prof_spec = getattr(segment, 'profile_spec', {})
                sections = [type('obj', (object,), {'height': segment.height, 'lattice_type': l_type, 'offset_x': 0, 'offset_y': 0, 'profile_spec': prof_spec})()]
            
            # We need to interpolate radius from segment base to top
            seg_start_z = current_z
            seg_height = segment.height
            seg_base_size = segment.base_size
            seg_top_size = segment.top_size if segment.top_size is not None else segment.base_size
            
            if segment.shape == 'prism':
                seg_top_size = seg_base_size
                
            for section in sections:
                h = section.height
                if h <= 0: continue
                current_z += h
                
                # Calculate radius at current_z
                rel_h = current_z - seg_start_z
                t = rel_h / seg_height if seg_height > 0 else 1.0
                current_size = seg_base_size + (seg_top_size - seg_base_size) * t
                r_curr = current_size / 2.0
                
                # Create nodes
                curr_nodes = []
                for i in range(faces):
                    angle = 2 * np.pi * i / faces + rot_rad
                    x = r_curr * np.cos(angle) 
                    y = r_curr * np.sin(angle) 
                    nid = model.add_node(x, y, current_z)
                    curr_nodes.append(nid)
                
                # Generate lattice
                pattern_str = getattr(section, 'lattice_type', getattr(segment, 'lattice_type', 'cross'))
                try:
                    pattern = LatticePattern(pattern_str)
                except ValueError:
                    pattern = LatticePattern.CROSS
                
                # Resolve profiles
                prof_spec = getattr(section, 'profile_spec', getattr(segment, 'profile_spec', {}))
                leg_p = self._resolve_profile(prof_spec.get("leg_profile"))
                brace_p = self._resolve_profile(prof_spec.get("brace_profile"))
                
                gen.generate_section_lattice(
                    prev_nodes, 
                    curr_nodes, 
                    pattern, 
                    leg_profile=leg_p, 
                    brace_profile=brace_p
                )
                
                prev_nodes = curr_nodes
                
        return model
