"""
Модуль нормативных допусков для геодезического контроля мачт

Основан на:
- СП 70.13330.2012 "Несущие и ограждающие конструкции"
- Инструкция Минсвязи СССР от 23.04.1980
"""

# Константы нормативов
VERTICAL_TOLERANCE_COEFFICIENT = 0.001  # СП 70.13330.2012, таблица 4.15
STRAIGHTNESS_TOLERANCE_DIVISOR = 750    # Инструкция Минсвязи СССР 1980


def get_vertical_tolerance(height: float) -> float:
    """
    Вычисляет допустимое отклонение от вертикали
    
    Формула: d_допуск = 0.001 × h
    где h - высота точки от основания
    
    Args:
        height: Высота точки в метрах
        
    Returns:
        Допустимое отклонение в метрах
    """
    return VERTICAL_TOLERANCE_COEFFICIENT * abs(height)


def get_straightness_tolerance(section_length: float) -> float:
    """
    Вычисляет допустимую стрелу прогиба для проверки прямолинейности
    
    Формула: δ_допуск = L / 750
    где L - длина секции (расстояние между опорными точками)
    
    Args:
        section_length: Длина секции в метрах
        
    Returns:
        Допустимая стрела прогиба в метрах
    """
    return section_length / STRAIGHTNESS_TOLERANCE_DIVISOR


def check_vertical_compliance(deviation: float, height: float) -> bool:
    """
    Проверяет соответствие отклонения от вертикали нормативу
    
    Args:
        deviation: Фактическое отклонение в метрах
        height: Высота точки в метрах
        
    Returns:
        True если отклонение в пределах нормы, False иначе
    """
    tolerance = get_vertical_tolerance(height)
    return abs(deviation) <= tolerance


def check_straightness_compliance(deflection: float, section_length: float) -> bool:
    """
    Проверяет соответствие стрелы прогиба нормативу
    
    Args:
        deflection: Фактическая стрела прогиба в метрах
        section_length: Длина секции в метрах
        
    Returns:
        True если прогиб в пределах нормы, False иначе
    """
    tolerance = get_straightness_tolerance(section_length)
    return abs(deflection) <= tolerance


class NormativeChecker:
    """
    Класс для проверки соответствия измерений нормативам
    """
    
    def __init__(self):
        self.vertical_coefficient = VERTICAL_TOLERANCE_COEFFICIENT
        self.straightness_divisor = STRAIGHTNESS_TOLERANCE_DIVISOR
        
    def check_vertical_deviations(self, deviations: list, heights: list) -> dict:
        """
        Проверяет все отклонения от вертикали
        
        Args:
            deviations: Список отклонений в метрах
            heights: Список высот в метрах
            
        Returns:
            Словарь с результатами проверки
        """
        results = {
            'compliant': [],
            'non_compliant': [],
            'total': len(deviations),
            'passed': 0,
            'failed': 0
        }
        
        for i, (dev, h) in enumerate(zip(deviations, heights)):
            tolerance = get_vertical_tolerance(h)
            is_compliant = abs(dev) <= tolerance
            
            result_item = {
                'index': i,
                'height': h,
                'deviation': dev,
                'tolerance': tolerance,
                'compliant': is_compliant,
                'excess': abs(dev) - tolerance if not is_compliant else 0
            }
            
            if is_compliant:
                results['compliant'].append(result_item)
                results['passed'] += 1
            else:
                results['non_compliant'].append(result_item)
                results['failed'] += 1
                
        return results
    
    def check_straightness_deviations(self, deflections: list, section_length: float) -> dict:
        """
        Проверяет стрелы прогиба
        
        Args:
            deflections: Список стрел прогиба в метрах
            section_length: Длина секции в метрах
            
        Returns:
            Словарь с результатами проверки
        """
        tolerance = get_straightness_tolerance(section_length)
        
        results = {
            'compliant': [],
            'non_compliant': [],
            'total': len(deflections),
            'passed': 0,
            'failed': 0,
            'tolerance': tolerance
        }
        
        for i, deflection in enumerate(deflections):
            is_compliant = abs(deflection) <= tolerance
            
            result_item = {
                'index': i,
                'deflection': deflection,
                'tolerance': tolerance,
                'compliant': is_compliant,
                'excess': abs(deflection) - tolerance if not is_compliant else 0
            }
            
            if is_compliant:
                results['compliant'].append(result_item)
                results['passed'] += 1
            else:
                results['non_compliant'].append(result_item)
                results['failed'] += 1
                
        return results

