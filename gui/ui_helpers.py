"""Вспомогательные функции для унификации вида элементов GUI."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QPushButton, QSizePolicy
from PyQt6.QtGui import QPalette
import re


def apply_compact_button_style(button: QPushButton, *, width: int = 88, min_height: int = 34) -> None:
    """Применяет компактный стиль к кнопке c горизонтальной ориентацией с поддержкой тем."""

    button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    # Увеличиваем размеры кнопок для лучшей читаемости текста
    button.setFixedWidth(max(width, 90))
    button.setFixedHeight(max(min_height, 36))
    
    # Применяем стиль в зависимости от темы
    is_dark = is_dark_theme_enabled()
    
    if is_dark:
        # Темная тема - хороший контраст
        button.setStyleSheet("""
            padding: 4px 10px;
            font-size: 10px;
            font-weight: 500;
            text-align: center;
            border: 1px solid #4a4a4e;
            border-radius: 4px;
            background-color: #3a3a3e;
            color: #e0e0e0;
        """)
    else:
        # Светлая тема - хороший контраст
        button.setStyleSheet("""
            padding: 4px 10px;
            font-size: 10px;
            font-weight: 500;
            text-align: center;
            border: 1px solid #b0b0b0;
            border-radius: 4px;
            background-color: #ffffff;
            color: #212121;
        """)
    
    # Если у кнопки нет tooltip, создаем его из текста
    if not button.toolTip():
        button_text = button.text().replace('\n', ' ').strip()
        if button_text:
            tooltip_text = re.sub(r'[^\w\s\-\(\)]', '', button_text).strip()
            if tooltip_text:
                button.setToolTip(tooltip_text)
    # Принудительно обновляем стиль после изменения параметров
    button.style().unpolish(button)
    button.style().polish(button)
    button.update()


def is_dark_theme_enabled() -> bool:
    """Возвращает True, если активирована темная тема приложения."""
    app = QApplication.instance()
    if not app:
        return False
    window_color = app.palette().color(QPalette.ColorRole.Window)
    return window_color.lightness() < 128

