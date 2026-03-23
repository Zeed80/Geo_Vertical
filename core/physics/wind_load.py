from dataclasses import dataclass

import numpy as np
from scipy.sparse import coo_matrix, linalg

from core.structure.model import TowerModel

# SP 20.13330.2016 Data
WIND_ZONES = {
    1: 0.23, 2: 0.30, 3: 0.38, 4: 0.48, 5: 0.60, 6: 0.73, 7: 0.85
} # kPa

TERRAIN_COEFFS = {
    'A': {'k10': 1.0, 'alpha': 0.12}, # Open coast
    'B': {'k10': 0.65, 'alpha': 0.16}, # Town/Forest
    'C': {'k10': 0.4, 'alpha': 0.22}   # Urban
}

@dataclass
class WindLoadResult:
    static_load: np.ndarray # Force vector (Fx, Fy, Fz) per node
    dynamic_load: np.ndarray
    natural_frequencies: list[float] # Hz
    mode_shapes: list[np.ndarray]
    total_load: np.ndarray

class WindLoadCalculator:
    def __init__(self, model: TowerModel):
        self.model = model
        self.node_map = {node_id: i for i, node_id in enumerate(sorted(model.nodes.keys()))}
        self.reverse_node_map = {i: node_id for node_id, i in self.node_map.items()}
        self.num_nodes = len(model.nodes)
        self.dof_per_node = 3 # Simplified to 3 DOF (Translation) for lumped mass, or 6 for Beam
        # Let's use 3 DOF truss elements for simplicity in this iteration
        # (Assuming pinned joints, which is standard for truss analysis)
        self.num_dof = self.num_nodes * 3

    def calculate(self, wind_zone: int, terrain_type: str = 'A') -> WindLoadResult:
        w0 = WIND_ZONES.get(wind_zone, 0.23) * 1000 # Pa

        # 1. Static Wind Load
        f_static = self._calc_static_wind_load(w0, terrain_type)

        # 2. Dynamic Analysis
        freqs, modes = self._solve_eigenvalues(num_modes=3)

        # 3. Dynamic Component (Pulsation)
        # Simplified pulsation coeff
        f_dynamic = np.zeros_like(f_static)
        # TODO: Implement full SP 20 pulsation logic using mode shapes
        # For now, add 50% dynamic factor as placeholder
        f_dynamic = f_static * 0.5

        total = f_static + f_dynamic

        return WindLoadResult(
            static_load=f_static,
            dynamic_load=f_dynamic,
            natural_frequencies=freqs,
            mode_shapes=modes,
            total_load=total
        )

    def _calc_static_wind_load(self, w0: float, terrain: str) -> np.ndarray:
        forces = np.zeros(self.num_dof)
        k_params = TERRAIN_COEFFS.get(terrain, TERRAIN_COEFFS['A'])

        # Process Members
        for member in self.model.members:
            n1 = self.model.nodes[member.start_node_id]
            n2 = self.model.nodes[member.end_node_id]

            # Mid-height for K(z)
            z_mid = (n1.z + n2.z) / 2.0
            k_z = k_params['k10'] * (max(z_mid, 10.0) / 10.0)**(2 * k_params['alpha'])

            # Area and Cx
            # Placeholder: Assume pipe D=0.1m
            d = 0.1
            if member.profile_data:
                d = member.profile_data.get('d', 100) / 1000.0

            length = np.linalg.norm(n2.coords - n1.coords)
            area = d * length
            cx = 1.2 # Aerodynamic coeff for tubular

            q_wind = w0 * k_z * cx * area

            # Distribute to nodes (Fx direction)
            # Assuming wind X
            idx1 = self.node_map[n1.id] * 3
            idx2 = self.node_map[n2.id] * 3

            forces[idx1] += q_wind / 2.0
            forces[idx2] += q_wind / 2.0

        # Process Equipment
        for eq in self.model.equipment:
            # Find nearest node? Or add to model as node?
            # Simplified: Find nearest node and apply load
            pass # TODO

        return forces

    def _solve_eigenvalues(self, num_modes: int = 3) -> tuple[list[float], list[np.ndarray]]:
        """Solve K u = w^2 M u"""
        K = self._assemble_stiffness()
        M = self._assemble_mass()

        # Apply Boundary Conditions (Fixed nodes)
        fixed_dofs = []
        for node_id, node in self.model.nodes.items():
            if node.is_fixed:
                idx = self.node_map[node_id] * 3
                fixed_dofs.extend([idx, idx+1, idx+2])

        # Reduce matrices
        free_dofs = sorted(list(set(range(self.num_dof)) - set(fixed_dofs)))
        if not free_dofs:
            return [], []

        K_red = K[np.ix_(free_dofs, free_dofs)]
        M_red = M[np.ix_(free_dofs, free_dofs)]

        # Solve
        try:
            vals, vecs = linalg.eigsh(K_red, M=M_red, k=num_modes, which='SM')
            freqs = np.sqrt(np.abs(vals)) / (2 * np.pi)

            # Reconstruct full mode shapes
            full_modes = []
            for i in range(num_modes):
                mode = np.zeros(self.num_dof)
                mode[free_dofs] = vecs[:, i]
                full_modes.append(mode)

            return list(freqs), full_modes
        except Exception as e:
            print(f"Eigenvalue solver failed: {e}")
            return [], []

    def _assemble_stiffness(self) -> coo_matrix:
        # Truss Element Stiffness
        rows, cols, data = [], [], []

        for member in self.model.members:
            n1 = self.model.nodes[member.start_node_id]
            n2 = self.model.nodes[member.end_node_id]

            vec = n2.coords - n1.coords
            L = np.linalg.norm(vec)
            if L < 1e-6: continue

            # E, A
            E = 2.06e11 # Steel Pa
            A = 0.001 # m2 default
            if member.profile_data:
                A = member.profile_data.get('A', 10.0) / 10000.0 # cm2 to m2

            k = (E * A) / L

            # Direction cosines
            cx, cy, cz = vec / L

            # Local to Global transformation for Truss
            # T = [cx cy cz 0 0 0; 0 0 0 cx cy cz] ...
            # Simplified Truss Matrix (3 DOF per node)
            # k_local = [[1, -1], [-1, 1]] * k
            # T matrix vector
            t = np.array([cx, cy, cz])
            k_global_block = np.outer(t, t) * k

            # Indices
            idx1 = self.node_map[n1.id] * 3
            idx2 = self.node_map[n2.id] * 3

            # Add 4 blocks
            # 1-1
            for r in range(3):
                for c in range(3):
                    rows.append(idx1 + r)
                    cols.append(idx1 + c)
                    data.append(k_global_block[r, c])

                    rows.append(idx2 + r)
                    cols.append(idx2 + c)
                    data.append(k_global_block[r, c])

                    rows.append(idx1 + r)
                    cols.append(idx2 + c)
                    data.append(-k_global_block[r, c])

                    rows.append(idx2 + r)
                    cols.append(idx1 + c)
                    data.append(-k_global_block[r, c])

        return coo_matrix((data, (rows, cols)), shape=(self.num_dof, self.num_dof)).tocsr()

    def _assemble_mass(self) -> coo_matrix:
        # Lumped mass matrix
        masses = np.zeros(self.num_dof)

        for member in self.model.members:
            n1 = self.model.nodes[member.start_node_id]
            n2 = self.model.nodes[member.end_node_id]
            L = np.linalg.norm(n2.coords - n1.coords)

            rho = 7850 # Steel kg/m3
            A = 0.001
            if member.profile_data:
                A = member.profile_data.get('A', 10.0) / 10000.0

            m_member = rho * A * L

            # Distribute to nodes
            idx1 = self.node_map[n1.id] * 3
            idx2 = self.node_map[n2.id] * 3

            for i in range(3):
                masses[idx1 + i] += m_member / 2.0
                masses[idx2 + i] += m_member / 2.0

        # Equipment mass
        for eq in self.model.equipment:
            pass # TODO: Add to nearest node

        # Create diagonal matrix
        rows = np.arange(self.num_dof)
        return coo_matrix((masses, (rows, rows)), shape=(self.num_dof, self.num_dof)).tocsr()
