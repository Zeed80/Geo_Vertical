"""
Экспортер данных башни в формат SCAD для расчета МКЭ.
"""

from __future__ import annotations

from typing import Optional, Dict, List, Any
from pathlib import Path

from core.tower_generator import TowerBlueprintV2
from core.structure.builder import TowerModelBuilder
from core.structure.model import TowerModel, MemberType
from core.db.profile_manager import ProfileManager


class SCADExporter:
    """
    Экспортер данных башни в текстовый формат для импорта в SCAD.
    """
    
    def __init__(self, profile_manager: Optional[ProfileManager] = None):
        self.profile_manager = profile_manager or ProfileManager()
    
    def export(self, blueprint: TowerBlueprintV2, output_path: str) -> None:
        """
        Экспортировать данные башни в файл SCAD.
        
        Args:
            blueprint: Чертеж башни
            output_path: Путь к выходному файлу
        """
        # Построить модель
        builder = TowerModelBuilder(blueprint, self.profile_manager)
        model = builder.build()
        
        # Сгенерировать текст
        content = self._generate_scad_content(model, blueprint)
        
        # Записать в файл
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)
    
    def _generate_scad_content(self, model: TowerModel, blueprint: TowerBlueprintV2) -> str:
        """Сгенерировать содержимое файла SCAD."""
        lines = []
        
        # Заголовок
        lines.append("; Данные для расчета МКЭ в SCAD")
        lines.append(f"; Башня: {len(blueprint.segments)} частей, высота {blueprint.total_height():.2f} м")
        lines.append("")
        
        # Узлы
        lines.append("; ===== УЗЛЫ =====")
        lines.append("NODES")
        nodes = sorted(model.nodes.items(), key=lambda x: x[0])
        for node_id, node in nodes:
            fixed = "1" if node.is_fixed else "0"
            lines.append(f"{node_id:6d} {node.x:12.6f} {node.y:12.6f} {node.z:12.6f} {fixed}")
        lines.append("")
        
        # Элементы
        lines.append("; ===== ЭЛЕМЕНТЫ =====")
        lines.append("ELEMENTS")
        
        type_names = {
            MemberType.LEG: "Пояс",
            MemberType.BRACE: "Раскос",
            MemberType.STRUT: "Распорка",
        }
        
        for member in model.members:
            elem_type = type_names.get(member.member_type, "Элемент")
            
            # Данные профиля
            if member.profile_data:
                profile_name = member.profile_data.get('designation', 'Не задано')
                standard = member.profile_data.get('standard', 'Не задано')
                A = member.profile_data.get('A', 0.0)
                Ix = member.profile_data.get('Ix', 0.0)
                Iy = member.profile_data.get('Iy', 0.0)
            else:
                profile_name = "Не задано"
                standard = "Не задано"
                A = Ix = Iy = 0.0
            
            lines.append(
                f"{member.id:6d} {member.start_node_id:6d} {member.end_node_id:6d} "
                f"{elem_type:10s} {profile_name:20s} {standard:20s} "
                f"{A:10.2f} {Ix:12.2f} {Iy:12.2f}"
            )
        lines.append("")
        
        # Материалы
        lines.append("; ===== МАТЕРИАЛЫ =====")
        lines.append("MATERIALS")
        lines.append("1 Сталь 206000.0 7850.0 0.3")
        lines.append("")
        
        # Нагрузки (заглушка)
        lines.append("; ===== НАГРУЗКИ =====")
        lines.append("LOADS")
        lines.append("; Нагрузки будут добавлены после расчета ветровой нагрузки")
        lines.append("")
        
        # Оборудование
        if model.equipment:
            lines.append("; ===== ОБОРУДОВАНИЕ =====")
            lines.append("EQUIPMENT")
            for eq in model.equipment:
                lines.append(
                    f"{eq.name:20s} {eq.height:8.2f} {eq.mass:8.1f} "
                    f"{eq.area_x:8.3f} {eq.area_y:8.3f}"
                )
            lines.append("")
        
        return "\n".join(lines)
