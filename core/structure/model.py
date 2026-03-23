from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import numpy as np


class MemberType(Enum):
    LEG = "leg"           # Пояс
    BRACE = "brace"       # Раскос
    STRUT = "strut"       # Распорка
    DIAPHRAGM = "diaphragm" # Диафрагма
    CROSSBAR = "crossbar" # Перекладина

@dataclass
class StructuralNode:
    id: int
    x: float
    y: float
    z: float
    is_fixed: bool = False # Закреплен ли узел (опора)

    @property
    def coords(self) -> np.ndarray:
        return np.array([self.x, self.y, self.z])

@dataclass
class StructuralMember:
    id: int
    start_node_id: int
    end_node_id: int
    member_type: MemberType
    profile_data: dict[str, Any] | None = None # Данные профиля из БД

    # Computed properties can be added here (length, vector, etc.)

@dataclass
class TowerEquipment:
    id: int
    name: str
    equipment_type: str # Antenna, Dish, etc.
    height: float       # Высота установки (z)
    mass: float         # kg
    area_x: float       # Площадь наветренная X (м2)
    area_y: float       # Площадь наветренная Y (м2)
    cx: float = 1.2     # Аэродинамический коэффициент
    azimuth: float = 0.0 # Азимут установки
    offset_x: float = 0.0
    offset_y: float = 0.0

@dataclass
class TowerModel:
    nodes: dict[int, StructuralNode] = field(default_factory=dict)
    members: list[StructuralMember] = field(default_factory=list)
    equipment: list[TowerEquipment] = field(default_factory=list)

    def add_node(self, x: float, y: float, z: float, is_fixed: bool = False) -> int:
        node_id = len(self.nodes) + 1
        self.nodes[node_id] = StructuralNode(node_id, x, y, z, is_fixed)
        return node_id

    def add_member(self, start_id: int, end_id: int, m_type: MemberType, profile: dict | None = None) -> int:
        member_id = len(self.members) + 1
        self.members.append(StructuralMember(member_id, start_id, end_id, m_type, profile))
        return member_id

    def get_node(self, node_id: int) -> StructuralNode | None:
        return self.nodes.get(node_id)
