import numpy as np
import pandas as pd

from core.survey_registration import rotate_points_around_z, shift_points_along_z, translate_points_xy


def test_method2_sequence_aligns_and_removes_belt():
    # Первая съемка: два пояса, по одной точке в каждом
    existing = pd.DataFrame([
        {'x':0.0,'y':0.0,'z':10.0,'belt':1}, # базовая
        {'x':1.0,'y':0.0,'z':10.0,'belt':2},
    ])
    # Вторая съемка: та же геометрия, но сдвинута и повернута
    second = pd.DataFrame([
        {'x':2.0,'y':1.0,'z':8.0,'belt':1},  # базовая смещена по XY и Z
        {'x':3.0,'y':1.0,'z':8.0,'belt':2},
    ])
    new_base = second.iloc[0]
    existing_base = existing.iloc[0]

    # Δz
    delta_z = float(existing_base['z'] - new_base['z'])
    shifted = shift_points_along_z(second, delta_z)
    # Перенос к базе
    txy = np.array([existing_base['x'] - new_base['x'], existing_base['y'] - new_base['y']])
    translated = translate_points_xy(shifted, float(txy[0]), float(txy[1]))
    # Поворот вокруг Z через базу (0°)
    rotated = rotate_points_around_z(translated, 0.0, np.array([existing_base['x'], existing_base['y'], existing_base['z']]))

    # Базовая должна совпасть
    base_after = rotated.iloc[0]
    assert np.allclose([base_after['x'], base_after['y'], base_after['z']], [existing_base['x'], existing_base['y'], existing_base['z']])

    # Удаляем пояс базовой точки из второй съемки
    belt_to_remove = int(new_base['belt'])
    remaining = rotated[rotated['belt'] != belt_to_remove]
    assert len(remaining) == 1
    assert remaining.iloc[0]['belt'] == 2
