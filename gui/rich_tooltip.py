"""
Модуль для создания анимированных rich tooltips с визуальными подсказками
"""

from PyQt6.QtWidgets import (QWidget, QLabel, QVBoxLayout, QHBoxLayout, 
                             QGraphicsOpacityEffect, QFrame)
from PyQt6.QtCore import (Qt, QPropertyAnimation, QTimer, QPoint, QRect, 
                          QEasingCurve, pyqtProperty, QObject)
from PyQt6.QtGui import QPainter, QColor, QFont, QPen, QBrush, QPalette
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


class RichTooltip(QWidget):
    """Богатый tooltip с анимацией и HTML контентом"""
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Tool |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        
        self._opacity = 1.0
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        
        self.init_ui()
        self.hide()
        
    def init_ui(self):
        """Инициализация интерфейса"""
        layout = QVBoxLayout()
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)
        self.setLayout(layout)
        
        # Контейнер для контента
        self.content_frame = QFrame()
        self.content_frame.setObjectName('tooltipFrame')
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(4)
        self.content_frame.setLayout(content_layout)
        
        # Заголовок
        self.title_label = QLabel()
        self.title_label.setObjectName('tooltipTitle')
        self.title_label.setWordWrap(True)
        content_layout.addWidget(self.title_label)
        
        # Описание
        self.description_label = QLabel()
        self.description_label.setObjectName('tooltipDescription')
        self.description_label.setWordWrap(True)
        content_layout.addWidget(self.description_label)
        
        # Горячие клавиши
        self.shortcut_label = QLabel()
        self.shortcut_label.setObjectName('tooltipShortcut')
        content_layout.addWidget(self.shortcut_label)
        
        layout.addWidget(self.content_frame)
        
        # Применяем стили
        self.update_style()
    
    def update_style(self):
        """Обновление стилей в зависимости от темы"""
        from gui.ui_helpers import is_dark_theme_enabled
        is_dark = is_dark_theme_enabled()
        
        if is_dark:
            bg_color = QColor(45, 45, 45)
            text_color = QColor(255, 255, 255)
            border_color = QColor(100, 100, 100)
        else:
            bg_color = QColor(255, 255, 255)
            text_color = QColor(0, 0, 0)
            border_color = QColor(200, 200, 200)
        
        style = f"""
        QFrame#tooltipFrame {{
            background-color: {bg_color.name()};
            border: 1px solid {border_color.name()};
            border-radius: 8px;
            padding: 8px;
        }}
        QLabel#tooltipTitle {{
            color: {text_color.name()};
            font-weight: bold;
            font-size: 13px;
            padding-bottom: 4px;
        }}
        QLabel#tooltipDescription {{
            color: {text_color.name()};
            font-size: 11px;
            line-height: 1.4;
        }}
        QLabel#tooltipShortcut {{
            color: {text_color.name()};
            font-size: 10px;
            font-style: italic;
            padding-top: 4px;
        }}
        """
        self.setStyleSheet(style)
    
    def set_content(self, title: str, description: str = "", shortcut: str = ""):
        """Установка контента tooltip"""
        self.title_label.setText(title)
        self.description_label.setText(description)
        
        if shortcut:
            self.shortcut_label.setText(f"Горячая клавиша: {shortcut}")
            self.shortcut_label.show()
        else:
            self.shortcut_label.hide()
        
        # Обновляем размер
        self.adjustSize()
    
    def show_tooltip(self, target_widget: QWidget, position: Optional[QPoint] = None):
        """Показать tooltip относительно виджета"""
        # Получаем глобальную позицию виджета
        global_pos = target_widget.mapToGlobal(QPoint(0, 0))
        
        if position is None:
            # Позиционируем снизу от кнопки
            position = QPoint(
                global_pos.x() + target_widget.width() // 2 - self.width() // 2,
                global_pos.y() + target_widget.height() + 8
            )
        
        # Проверяем границы экрана
        screen_geometry = self.screen().availableGeometry()
        if position.x() + self.width() > screen_geometry.right():
            position.setX(screen_geometry.right() - self.width() - 10)
        if position.x() < screen_geometry.left():
            position.setX(screen_geometry.left() + 10)
        if position.y() + self.height() > screen_geometry.bottom():
            # Показываем сверху
            position.setY(global_pos.y() - self.height() - 8)
        if position.y() < screen_geometry.top():
            position.setY(screen_geometry.top() + 10)
        
        self.move(position)
        self.fade_in()
        self.show()
    
    def fade_in(self):
        """Анимация появления"""
        self.opacity_effect.setOpacity(0.0)
        self.animation = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.animation.setDuration(200)
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(1.0)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.animation.start()
    
    def fade_out(self, callback=None):
        """Анимация исчезновения"""
        self.animation = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.animation.setDuration(150)
        self.animation.setStartValue(1.0)
        self.animation.setEndValue(0.0)
        self.animation.setEasingCurve(QEasingCurve.Type.InCubic)
        if callback:
            self.animation.finished.connect(callback)
        self.animation.start()
    
    def hide_tooltip(self):
        """Скрыть tooltip с анимацией"""
        self.fade_out(lambda: self.hide())


class TooltipManager(QObject):
    """Менеджер для управления rich tooltips"""
    
    _instance = None
    _tooltips: Dict[QWidget, RichTooltip] = {}
    _show_timers: Dict[QWidget, QTimer] = {}
    _hide_timers: Dict[QWidget, QTimer] = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            super().__init__()
            self._tooltips = {}
            self._show_timers = {}
            self._hide_timers = {}
            self._initialized = True
    
    def register_tooltip(self, widget: QWidget, title: str, 
                        description: str = "", shortcut: str = ""):
        """Регистрация tooltip для виджета"""
        if widget in self._tooltips:
            # Обновляем существующий
            tooltip = self._tooltips[widget]
            tooltip.set_content(title, description, shortcut)
        else:
            # Создаем новый
            tooltip = RichTooltip()
            tooltip.set_content(title, description, shortcut)
            self._tooltips[widget] = tooltip
            
            # Устанавливаем обработчики событий
            widget.installEventFilter(self)
    
    def eventFilter(self, obj: QWidget, event) -> bool:
        """Фильтр событий для показа/скрытия tooltips"""
        if obj not in self._tooltips:
            return False
        
        tooltip = self._tooltips[obj]
        
        if event.type() == event.Type.Enter:
            # Запускаем таймер показа
            timer = QTimer()
            timer.setSingleShot(True)
            timer.timeout.connect(lambda: self._show_tooltip(obj))
            timer.start(500)  # Задержка 500мс перед показом
            self._show_timers[obj] = timer
            
        elif event.type() == event.Type.Leave:
            # Отменяем таймер показа
            if obj in self._show_timers:
                self._show_timers[obj].stop()
                del self._show_timers[obj]
            
            # Скрываем tooltip
            self._hide_tooltip(obj)
            
        elif event.type() == event.Type.Move or event.type() == event.Type.Resize:
            # Обновляем позицию tooltip если он виден
            if tooltip.isVisible():
                self._update_tooltip_position(obj)
        
        return False
    
    def _show_tooltip(self, widget: QWidget):
        """Показать tooltip для виджета"""
        if widget not in self._tooltips:
            return
        
        tooltip = self._tooltips[widget]
        tooltip.show_tooltip(widget)
    
    def _hide_tooltip(self, widget: QWidget):
        """Скрыть tooltip для виджета"""
        if widget not in self._tooltips:
            return
        
        tooltip = self._tooltips[widget]
        if tooltip.isVisible():
            tooltip.hide_tooltip()
    
    def _update_tooltip_position(self, widget: QWidget):
        """Обновить позицию tooltip"""
        if widget not in self._tooltips:
            return
        
        tooltip = self._tooltips[widget]
        if tooltip.isVisible():
            tooltip.show_tooltip(widget)
    
    def unregister_tooltip(self, widget: QWidget):
        """Удалить tooltip для виджета"""
        if widget in self._tooltips:
            tooltip = self._tooltips[widget]
            tooltip.hide()
            tooltip.deleteLater()
            del self._tooltips[widget]
        
        if widget in self._show_timers:
            self._show_timers[widget].stop()
            del self._show_timers[widget]
        
        if widget in self._hide_timers:
            self._hide_timers[widget].stop()
            del self._hide_timers[widget]
        
        widget.removeEventFilter(self)
    
    def update_all_styles(self):
        """Обновить стили всех tooltips (при смене темы)"""
        for tooltip in self._tooltips.values():
            tooltip.update_style()


# Глобальный экземпляр менеджера
_tooltip_manager = TooltipManager()


def set_rich_tooltip(widget: QWidget, title: str, description: str = "", shortcut: str = ""):
    """Удобная функция для установки rich tooltip на виджет"""
    _tooltip_manager.register_tooltip(widget, title, description, shortcut)

