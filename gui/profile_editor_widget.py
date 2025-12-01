"""
Виджет для редактирования и визуализации профилей проката.
Отображает схему профиля, оси инерции и характеристики.
"""

from __future__ import annotations

from typing import Optional, Dict, Any
from PyQt6.QtCore import Qt, pyqtSignal, QRectF, QPointF
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QComboBox,
    QDoubleSpinBox,
    QPushButton,
    QScrollArea,
    QSplitter,
)
from PyQt6.QtGui import QPainter, QPen, QBrush, QColor, QFont

from core.db.profile_manager import ProfileManager


# Словарь русских названий типов профилей
PROFILE_TYPE_NAMES = {
    "pipe": "Труба",
    "angle": "Уголок",
    "channel": "Швеллер",
    "i_beam": "Двутавр",
    "rectangular": "Прямоугольная труба",
}


class ProfileSchemeWidget(QWidget):
    """
    Виджет для отображения схемы профиля с осями инерции.
    """
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._profile_data: Optional[Dict[str, Any]] = None
        self.setMinimumSize(300, 300)
        self.setStyleSheet("background-color: white; border: 1px solid #ccc;")
    
    def set_profile(self, profile_data: Optional[Dict[str, Any]]) -> None:
        """Установить профиль для отображения."""
        self._profile_data = profile_data
        self.update()
    
    def paintEvent(self, event) -> None:
        """Отрисовка схемы профиля."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Фон
        painter.fillRect(self.rect(), QColor(255, 255, 255))
        
        if not self._profile_data:
            # Отобразить заглушку
            painter.setPen(QPen(QColor(200, 200, 200), 1))
            painter.setFont(QFont("Arial", 12))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Выберите профиль")
            return
        
        profile_type = self._profile_data.get("type", "")
        width = self.width()
        height = self.height()
        margin = 40
        draw_area = QRectF(margin, margin, width - 2 * margin, height - 2 * margin)
        
        # Центр для отрисовки
        center_x = draw_area.center().x()
        center_y = draw_area.center().y()
        
        painter.setPen(QPen(QColor(0, 0, 0), 2))
        
        if profile_type == "pipe":
            self._draw_pipe(painter, draw_area, center_x, center_y)
        elif profile_type == "angle":
            self._draw_angle(painter, draw_area, center_x, center_y)
        elif profile_type == "channel":
            self._draw_channel(painter, draw_area, center_x, center_y)
        else:
            # Общий вид для других типов
            painter.drawRect(draw_area)
        
        # Оси инерции
        self._draw_inertia_axes(painter, draw_area, center_x, center_y)
        
        # Размеры
        self._draw_dimensions(painter, draw_area, center_x, center_y)
    
    def _draw_pipe(self, painter: QPainter, area: QRectF, cx: float, cy: float) -> None:
        """Отрисовать трубу."""
        d = self._profile_data.get("d", 100)  # мм
        t = self._profile_data.get("t", 5)  # мм
        
        # Масштаб
        scale = min(area.width() / (d * 1.5), area.height() / (d * 1.5))
        radius_outer = (d / 2) * scale
        radius_inner = max(0, ((d - 2 * t) / 2) * scale)
        
        # Внешний круг
        painter.setPen(QPen(QColor(0, 0, 0), 2))
        painter.setBrush(QBrush(QColor(240, 240, 240)))
        painter.drawEllipse(QPointF(cx, cy), radius_outer, radius_outer)
        
        # Внутренний круг (если есть толщина)
        if radius_inner > 2:
            painter.setPen(QPen(QColor(255, 255, 255), 1))
            painter.setBrush(QBrush(QColor(255, 255, 255)))
            painter.drawEllipse(QPointF(cx, cy), radius_inner, radius_inner)
        
        # Размерные линии
        painter.setPen(QPen(QColor(100, 100, 100), 1))
        # Горизонтальная размерная линия
        line_len = radius_outer * 1.3
        painter.drawLine(cx - line_len, cy - radius_outer - 15, cx + line_len, cy - radius_outer - 15)
        painter.drawLine(cx - line_len, cy - radius_outer - 15, cx - line_len, cy - radius_outer - 10)
        painter.drawLine(cx + line_len, cy - radius_outer - 15, cx + line_len, cy - radius_outer - 10)
        
        # Центральные линии (штриховые)
        painter.setPen(QPen(QColor(200, 200, 200), 1, Qt.PenStyle.DashLine))
        painter.drawLine(cx - radius_outer * 1.4, cy, cx + radius_outer * 1.4, cy)
        painter.drawLine(cx, cy - radius_outer * 1.4, cx, cy + radius_outer * 1.4)
    
    def _draw_angle(self, painter: QPainter, area: QRectF, cx: float, cy: float) -> None:
        """Отрисовать уголок."""
        b = self._profile_data.get("b", 50)  # мм
        t = self._profile_data.get("t", 5)  # мм
        
        # Масштаб
        scale = min(area.width() / (b * 2.5), area.height() / (b * 2.5))
        size = b * scale
        thickness = t * scale
        
        # Уголок (L-образный) - упрощенная схема
        # Вертикальная полка
        v_rect = QRectF(cx - size/2, cy - size/2, thickness, size)
        # Горизонтальная полка
        h_rect = QRectF(cx - size/2, cy - size/2, size, thickness)
        
        painter.setPen(QPen(QColor(0, 0, 0), 2))
        painter.setBrush(QBrush(QColor(240, 240, 240)))
        painter.drawRect(v_rect)
        painter.drawRect(h_rect)
        
        # Размерные линии
        painter.setPen(QPen(QColor(100, 100, 100), 1))
        # Размер b (ширина полки)
        dim_y = cy - size/2 - 20
        painter.drawLine(cx - size/2 - 10, dim_y, cx + size/2 + 10, dim_y)
        painter.drawLine(cx - size/2 - 10, dim_y, cx - size/2 - 10, dim_y - 5)
        painter.drawLine(cx + size/2 + 10, dim_y, cx + size/2 + 10, dim_y - 5)
        
        # Центральные линии (штриховые)
        painter.setPen(QPen(QColor(200, 200, 200), 1, Qt.PenStyle.DashLine))
        painter.drawLine(cx - size, cy, cx + size, cy)
        painter.drawLine(cx, cy - size, cx, cy + size)
    
    def _draw_channel(self, painter: QPainter, area: QRectF, cx: float, cy: float) -> None:
        """Отрисовать швеллер."""
        h = self._profile_data.get("d", 100)  # высота
        b = self._profile_data.get("b", 50)  # ширина полки
        t = self._profile_data.get("t", 5)  # толщина
        
        # Масштаб
        scale = min(area.width() / (h * 1.6), area.height() / (b * 2.8))
        height = h * scale
        width = b * scale
        thickness = t * scale
        
        # Швеллер (П-образный)
        painter.setPen(QPen(QColor(0, 0, 0), 2))
        painter.setBrush(QBrush(QColor(240, 240, 240)))
        
        # Левая полка (верхняя)
        painter.drawRect(cx - height/2, cy - width/2, thickness, width)
        # Стенка (вертикальная)
        painter.drawRect(cx - height/2, cy - width/2, height, thickness)
        # Правая полка (нижняя)
        painter.drawRect(cx + height/2 - thickness, cy - width/2, thickness, width)
        
        # Размерные линии
        painter.setPen(QPen(QColor(100, 100, 100), 1))
        # Размер h (высота)
        dim_x = cx - height/2 - 20
        painter.drawLine(dim_x, cy - width/2 - 10, dim_x, cy + width/2 + 10)
        painter.drawLine(dim_x, cy - width/2 - 10, dim_x - 5, cy - width/2 - 10)
        painter.drawLine(dim_x, cy + width/2 + 10, dim_x - 5, cy + width/2 + 10)
        
        # Центральные линии (штриховые)
        painter.setPen(QPen(QColor(200, 200, 200), 1, Qt.PenStyle.DashLine))
        painter.drawLine(cx - height, cy, cx + height, cy)
        painter.drawLine(cx, cy - width, cx, cy + width)
    
    def _draw_inertia_axes(self, painter: QPainter, area: QRectF, cx: float, cy: float) -> None:
        """Отрисовать оси инерции с подписями."""
        if not self._profile_data:
            return
        
        # Ось X (красная) - горизонтальная
        painter.setPen(QPen(QColor(255, 0, 0), 2))
        painter.drawLine(area.left() + 10, cy, area.right() - 10, cy)
        # Стрелка
        arrow_size = 8
        painter.drawLine(area.right() - 10, cy, area.right() - 10 - arrow_size, cy - arrow_size/2)
        painter.drawLine(area.right() - 10, cy, area.right() - 10 - arrow_size, cy + arrow_size/2)
        painter.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        painter.setPen(QPen(QColor(200, 0, 0), 1))
        painter.drawText(area.right() - 35, cy - 8, "X")
        
        # Ось Y (зеленая) - вертикальная
        painter.setPen(QPen(QColor(0, 150, 0), 2))
        painter.drawLine(cx, area.top() + 10, cx, area.bottom() - 10)
        # Стрелка
        painter.drawLine(cx, area.top() + 10, cx - arrow_size/2, area.top() + 10 + arrow_size)
        painter.drawLine(cx, area.top() + 10, cx + arrow_size/2, area.top() + 10 + arrow_size)
        painter.setPen(QPen(QColor(0, 120, 0), 1))
        painter.drawText(cx + 8, area.top() + 25, "Y")
        
        # Центр тяжести (точка)
        painter.setPen(QPen(QColor(0, 0, 255), 2))
        painter.setBrush(QBrush(QColor(0, 0, 255)))
        painter.drawEllipse(QPointF(cx, cy), 3, 3)
        
        # Подпись центра тяжести
        painter.setFont(QFont("Arial", 8, QFont.Weight.Bold))
        painter.setPen(QPen(QColor(0, 0, 200), 1))
        painter.drawText(cx + 6, cy - 4, "ЦТ")
        
        # Подписи осей
        painter.setFont(QFont("Arial", 9, QFont.Weight.Bold))
        # Подпись оси X
        painter.setPen(QPen(QColor(200, 0, 0), 1))
        painter.drawText(area.right() - 25, cy - 8, "X")
        # Подпись оси Y
        painter.setPen(QPen(QColor(0, 120, 0), 1))
        painter.drawText(cx + 8, area.top() + 22, "Y")
    
    def _draw_dimensions(self, painter: QPainter, area: QRectF, cx: float, cy: float) -> None:
        """Отрисовать размеры профиля."""
        if not self._profile_data:
            return
        
        painter.setPen(QPen(QColor(0, 0, 200), 1))
        painter.setFont(QFont("Arial", 9))
        
        profile_type = self._profile_data.get("type", "")
        
        if profile_type == "pipe":
            d = self._profile_data.get("d", 0)
            t = self._profile_data.get("t", 0)
            painter.drawText(area.left() + 5, area.top() + 15, f"Ø{d}×{t} мм")
        elif profile_type == "angle":
            b = self._profile_data.get("b", 0)
            t = self._profile_data.get("t", 0)
            painter.drawText(area.left() + 5, area.top() + 15, f"{b}×{b}×{t} мм")
        elif profile_type == "channel":
            h = self._profile_data.get("d", 0)
            b = self._profile_data.get("b", 0)
            t = self._profile_data.get("t", 0)
            painter.drawText(area.left() + 5, area.top() + 15, f"{h}×{b}×{t} мм")


class ProfileEditorWidget(QWidget):
    """
    Виджет для редактирования профиля с визуализацией.
    """
    
    profileChanged = pyqtSignal(dict)  # Измененный профиль
    
    def __init__(self, profile_manager: ProfileManager, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.profile_manager = profile_manager
        self._current_profile: Optional[Dict[str, Any]] = None
        self._updating = False
        
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """Настройка интерфейса."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        
        # Splitter для разделения схемы и свойств
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Левая часть: Схема профиля
        scheme_group = QGroupBox("Схема профиля с осями инерции")
        scheme_layout = QVBoxLayout()
        scheme_layout.setContentsMargins(4, 4, 4, 4)
        self.scheme_widget = ProfileSchemeWidget()
        self.scheme_widget.setMinimumSize(320, 320)
        scheme_layout.addWidget(self.scheme_widget)
        scheme_group.setLayout(scheme_layout)
        scheme_group.setMinimumWidth(360)
        scheme_group.setMaximumWidth(500)
        splitter.addWidget(scheme_group)
        
        # Правая часть: Характеристики
        props_group = QGroupBox("Характеристики профиля")
        props_layout = QVBoxLayout()
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(320)
        scroll.setMaximumWidth(400)
        
        props_widget = QWidget()
        props_form = QFormLayout(props_widget)
        props_form.setSpacing(8)
        props_form.setContentsMargins(8, 8, 8, 8)
        
        # Название профиля
        self.name_label = QLabel("—")
        self.name_label.setStyleSheet("font-weight: 600; font-size: 11pt;")
        props_form.addRow("Название:", self.name_label)
        
        # Тип профиля (русское название)
        self.type_label = QLabel("—")
        props_form.addRow("Тип:", self.type_label)
        
        # Стандарт
        self.standard_label = QLabel("—")
        props_form.addRow("Стандарт:", self.standard_label)
        
        # Геометрические характеристики
        geom_group = QGroupBox("Геометрические характеристики")
        geom_form = QFormLayout()
        
        self.d_spin = QDoubleSpinBox()
        self.d_spin.setRange(0, 10000)
        self.d_spin.setSuffix(" мм")
        self.d_spin.setDecimals(1)
        self.d_spin.valueChanged.connect(self._on_value_changed)
        geom_form.addRow("Диаметр/Высота (d):", self.d_spin)
        
        self.t_spin = QDoubleSpinBox()
        self.t_spin.setRange(0, 1000)
        self.t_spin.setSuffix(" мм")
        self.t_spin.setDecimals(1)
        self.t_spin.valueChanged.connect(self._on_value_changed)
        geom_form.addRow("Толщина (t):", self.t_spin)
        
        self.b_spin = QDoubleSpinBox()
        self.b_spin.setRange(0, 10000)
        self.b_spin.setSuffix(" мм")
        self.b_spin.setDecimals(1)
        self.b_spin.valueChanged.connect(self._on_value_changed)
        geom_form.addRow("Ширина (b):", self.b_spin)
        
        geom_group.setLayout(geom_form)
        props_form.addRow(geom_group)
        
        # Механические характеристики
        mech_group = QGroupBox("Механические характеристики")
        mech_form = QFormLayout()
        
        self.A_spin = QDoubleSpinBox()
        self.A_spin.setRange(0, 10000)
        self.A_spin.setSuffix(" см²")
        self.A_spin.setDecimals(2)
        self.A_spin.valueChanged.connect(self._on_value_changed)
        mech_form.addRow("Площадь (A):", self.A_spin)
        
        self.Ix_spin = QDoubleSpinBox()
        self.Ix_spin.setRange(0, 1000000)
        self.Ix_spin.setSuffix(" см⁴")
        self.Ix_spin.setDecimals(2)
        self.Ix_spin.valueChanged.connect(self._on_value_changed)
        mech_form.addRow("Момент инерции Ix:", self.Ix_spin)
        
        self.Iy_spin = QDoubleSpinBox()
        self.Iy_spin.setRange(0, 1000000)
        self.Iy_spin.setSuffix(" см⁴")
        self.Iy_spin.setDecimals(2)
        self.Iy_spin.valueChanged.connect(self._on_value_changed)
        mech_form.addRow("Момент инерции Iy:", self.Iy_spin)
        
        self.ix_spin = QDoubleSpinBox()
        self.ix_spin.setRange(0, 1000)
        self.ix_spin.setSuffix(" см")
        self.ix_spin.setDecimals(2)
        self.ix_spin.valueChanged.connect(self._on_value_changed)
        mech_form.addRow("Радиус инерции ix:", self.ix_spin)
        
        self.iy_spin = QDoubleSpinBox()
        self.iy_spin.setRange(0, 1000)
        self.iy_spin.setSuffix(" см")
        self.iy_spin.setDecimals(2)
        self.iy_spin.valueChanged.connect(self._on_value_changed)
        mech_form.addRow("Радиус инерции iy:", self.iy_spin)
        
        self.mass_spin = QDoubleSpinBox()
        self.mass_spin.setRange(0, 1000)
        self.mass_spin.setSuffix(" кг/м")
        self.mass_spin.setDecimals(3)
        self.mass_spin.valueChanged.connect(self._on_value_changed)
        mech_form.addRow("Масса 1 м:", self.mass_spin)
        
        mech_group.setLayout(mech_form)
        props_form.addRow(mech_group)
        
        scroll.setWidget(props_widget)
        props_layout.addWidget(scroll)
        props_group.setLayout(props_layout)
        splitter.addWidget(props_group)
        
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        
        layout.addWidget(splitter, stretch=1)
        
        # Кнопки
        buttons_layout = QHBoxLayout()
        self.save_btn = QPushButton("Сохранить изменения")
        self.save_btn.clicked.connect(self._on_save)
        self.save_btn.setEnabled(False)
        buttons_layout.addWidget(self.save_btn)
        buttons_layout.addStretch()
        layout.addLayout(buttons_layout)
    
    def set_profile(self, profile_data: Optional[Dict[str, Any]]) -> None:
        """Установить профиль для редактирования."""
        self._current_profile = profile_data
        self._updating = True
        
        try:
            if profile_data:
                # Обновить схему
                self.scheme_widget.set_profile(profile_data)
                
                # Обновить названия
                profile_type = profile_data.get("type", "")
                type_name = PROFILE_TYPE_NAMES.get(profile_type, profile_type)
                designation = profile_data.get("designation", "—")
                
                self.name_label.setText(f"{type_name} {designation}")
                self.type_label.setText(type_name)
                self.standard_label.setText(profile_data.get("standard", "—"))
                
                # Обновить значения
                self.d_spin.setValue(profile_data.get("d", 0))
                self.t_spin.setValue(profile_data.get("t", 0))
                self.b_spin.setValue(profile_data.get("b", 0))
                self.A_spin.setValue(profile_data.get("A", 0))
                self.Ix_spin.setValue(profile_data.get("Ix", 0))
                self.Iy_spin.setValue(profile_data.get("Iy", 0))
                self.ix_spin.setValue(profile_data.get("i_x", 0))
                self.iy_spin.setValue(profile_data.get("i_y", 0))
                self.mass_spin.setValue(profile_data.get("mass_per_m", 0))
                
                # Показать/скрыть поля в зависимости от типа
                self._update_visibility(profile_type)
            else:
                self.scheme_widget.set_profile(None)
                self.name_label.setText("—")
                self.type_label.setText("—")
                self.standard_label.setText("—")
        finally:
            self._updating = False
            self.save_btn.setEnabled(False)
    
    def _update_visibility(self, profile_type: str) -> None:
        """Обновить видимость полей в зависимости от типа профиля."""
        # Для трубы: d, t
        # Для уголка: b, t
        # Для швеллера: d (h), b, t
        
        self.d_spin.setVisible(profile_type in ("pipe", "channel"))
        self.t_spin.setVisible(True)
        self.b_spin.setVisible(profile_type in ("angle", "channel"))
    
    def _on_value_changed(self) -> None:
        """Обработка изменения значения."""
        if self._updating:
            return
        
        self.save_btn.setEnabled(True)
        
        # Обновить схему при изменении геометрии
        if self._current_profile:
            updated_profile = self._current_profile.copy()
            updated_profile["d"] = self.d_spin.value()
            updated_profile["t"] = self.t_spin.value()
            updated_profile["b"] = self.b_spin.value()
            self.scheme_widget.set_profile(updated_profile)
    
    def _on_save(self) -> None:
        """Сохранить изменения профиля."""
        if not self._current_profile:
            return
        
        # Обновить данные профиля
        updated_profile = self._current_profile.copy()
        updated_profile["d"] = self.d_spin.value()
        updated_profile["t"] = self.t_spin.value()
        updated_profile["b"] = self.b_spin.value()
        updated_profile["A"] = self.A_spin.value()
        updated_profile["Ix"] = self.Ix_spin.value()
        updated_profile["Iy"] = self.Iy_spin.value()
        updated_profile["i_x"] = self.ix_spin.value()
        updated_profile["i_y"] = self.iy_spin.value()
        updated_profile["mass_per_m"] = self.mass_spin.value()
        
        # Сохранить в БД
        if self.profile_manager.add_profile(updated_profile):
            self._current_profile = updated_profile
            self.save_btn.setEnabled(False)
            self.profileChanged.emit(updated_profile)
        else:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Ошибка", "Не удалось сохранить профиль.")
