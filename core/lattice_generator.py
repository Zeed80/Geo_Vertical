from enum import Enum

import numpy as np

from core.structure.model import MemberType, TowerModel


class LatticePattern(Enum):
    CROSS = "cross"       # Крестовая (X)
    Z_BRACE = "z_brace"   # Раскосная (Z)
    K_BRACE = "k_brace"   # Полураскосная (K)
    PORTAL = "portal"     # Портальная (V)
    NONE = "none"         # Только пояса

class LatticeGenerator:
    def __init__(self, model: TowerModel):
        self.model = model

    def _get_node_pos(self, node_id: int) -> np.ndarray:
        node = self.model.get_node(node_id)
        return np.array([node.x, node.y, node.z]) if node else np.zeros(3)

    def _create_intermediate_nodes(
        self,
        n1_id: int,
        n2_id: int,
        count: int
    ) -> list[int]:
        """Create 'count' nodes distributed linearly between n1 and n2."""
        if count <= 0:
            return []

        p1 = self._get_node_pos(n1_id)
        p2 = self._get_node_pos(n2_id)
        new_ids = []

        for i in range(1, count + 1):
            t = i / (count + 1)
            p = p1 + (p2 - p1) * t
            new_ids.append(self.model.add_node(p[0], p[1], p[2]))

        return new_ids

    def generate_section_lattice(
        self,
        bottom_indices: list[int], # Node IDs for bottom belt
        top_indices: list[int],    # Node IDs for top belt
        pattern: LatticePattern,
        subdivide: int = 1,
        leg_profile: dict | None = None,
        brace_profile: dict | None = None
    ):
        """
        Generates lattice members for a tower section.
        Assumes indices are ordered around the perimeter (e.g., [A, B, C, D]).
        """
        num_legs = len(bottom_indices)
        if len(top_indices) != num_legs:
            raise ValueError("Bottom and top node counts must match")

        # 1. Create Legs (if not already connected, but usually we add them here or assume exist)
        # We will add leg members explicitly here
        for i in range(num_legs):
            self.model.add_member(bottom_indices[i], top_indices[i], MemberType.LEG, profile=leg_profile)

        # 2. Process each face
        for i in range(num_legs):
            # Define the 4 corners of the face
            # Leg 1: b1 -> t1
            # Leg 2: b2 -> t2
            b1_id = bottom_indices[i]
            t1_id = top_indices[i]

            next_i = (i + 1) % num_legs
            b2_id = bottom_indices[next_i]
            t2_id = top_indices[next_i]

            # Also add horizontal struts (belts) at top and bottom if they don't exist?
            # Usually struts are added at section boundaries.
            # Let's add Struts (Belts) at bottom and top for now.
            # Note: This might duplicate if we process sections sequentially.
            # Ideally struts are property of the "belt" level.
            # We'll assume "Belt" generation is separate or handled here.
            # Let's add them for now, duplication check can be done later or by ID check.
            # Struts usually use same profile as braces or specific strut profile.
            # Using brace_profile for simplicity if not specified.
            self.model.add_member(b1_id, b2_id, MemberType.STRUT, profile=brace_profile)
            self.model.add_member(t1_id, t2_id, MemberType.STRUT, profile=brace_profile)

            if pattern == LatticePattern.NONE:
                continue

            # Subdivide the face vertically
            # We need intermediate nodes on Leg 1 and Leg 2
            leg1_intermediates = self._create_intermediate_nodes(b1_id, t1_id, subdivide - 1)
            leg2_intermediates = self._create_intermediate_nodes(b2_id, t2_id, subdivide - 1)

            # Combine into layers: [bottom], [inter1], [inter2], ..., [top]
            col1 = [b1_id] + leg1_intermediates + [t1_id]
            col2 = [b2_id] + leg2_intermediates + [t2_id]

            # Process each sub-panel
            for j in range(len(col1) - 1):
                # Corners of sub-panel
                lb = col1[j]     # Left Bottom
                lt = col1[j+1]   # Left Top
                rb = col2[j]     # Right Bottom
                rt = col2[j+1]   # Right Top

                # Add horizontal strut between sub-panels if needed (not for top/bottom as added above)
                # Actually for subdivide > 1 we need internal horizontal struts
                if j > 0:
                    self.model.add_member(lb, rb, MemberType.STRUT, profile=brace_profile)

                self._apply_pattern_to_panel(lb, lt, rb, rt, pattern, brace_profile)

    def _get_or_create_midpoint(self, n1_id: int, n2_id: int) -> int:
        # Check if member exists and has a midpoint? No, just create geometric midpoint.
        # In a real efficient system we'd check if a node already exists at that coord.
        # For now, just create new node.
        p1 = self._get_node_pos(n1_id)
        p2 = self._get_node_pos(n2_id)
        mid = (p1 + p2) / 2
        return self.model.add_node(mid[0], mid[1], mid[2])

    def _apply_pattern_to_panel(
        self,
        lb: int, lt: int,
        rb: int, rt: int,
        pattern: LatticePattern,
        profile: dict | None = None
    ):
        if pattern == LatticePattern.CROSS:
            # X-brace
            self.model.add_member(lb, rt, MemberType.BRACE, profile=profile)
            self.model.add_member(rb, lt, MemberType.BRACE, profile=profile)

        elif pattern == LatticePattern.Z_BRACE:
            # Z-brace (single diagonal)
            self.model.add_member(lb, rt, MemberType.BRACE, profile=profile)

        elif pattern == LatticePattern.PORTAL:
            # V-brace (Portal) - Inverted V (Chevron)
            # From Bottom Corners to Top Mid
            mid_top = self._get_or_create_midpoint(lt, rt)
            self.model.add_member(lb, mid_top, MemberType.BRACE, profile=profile)
            self.model.add_member(rb, mid_top, MemberType.BRACE, profile=profile)

        elif pattern == LatticePattern.K_BRACE:
            # K-brace (Vertical K)
            # Midpoint of columns (legs)
            mid_l = self._get_or_create_midpoint(lb, lt)
            self.model.add_member(mid_l, rb, MemberType.BRACE, profile=profile)
            self.model.add_member(mid_l, rt, MemberType.BRACE, profile=profile)
            # Mirror
            mid_r = self._get_or_create_midpoint(rb, rt)
            self.model.add_member(mid_r, lb, MemberType.BRACE, profile=profile)
            self.model.add_member(mid_r, lt, MemberType.BRACE, profile=profile)
