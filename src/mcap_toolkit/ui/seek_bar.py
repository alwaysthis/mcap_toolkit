"""Painted seek bar. QSlider + app QSS is unreliable on Windows (value/handle drift)."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal, QRectF
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QSizePolicy, QWidget


class SeekBar(QWidget):
    ratio_changed = pyqtSignal(float)
    pressed = pyqtSignal()
    released = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("seekSlider")
        self._ratio = 0.0
        self._dragging = False
        self.setMinimumHeight(28)
        self.setMaximumHeight(32)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)

    def ratio(self) -> float:
        return self._ratio

    def set_ratio(self, ratio: float, *, force: bool = False) -> None:
        if self._dragging and not force:
            return
        r = max(0.0, min(1.0, float(ratio)))
        if abs(r - self._ratio) < 1e-7:
            return
        self._ratio = r
        self.update()

    def is_dragging(self) -> bool:
        return self._dragging

    def finish_drag(self) -> None:
        if not self._dragging:
            return
        self._dragging = False
        self.released.emit()

    def cancel_drag(self) -> None:
        self._dragging = False

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self._dragging = True
        self.pressed.emit()
        self._seek_x(self._x(event), force=True)
        event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if not self._dragging:
            return
        if not event.buttons() & Qt.MouseButton.LeftButton:
            self.finish_drag()
            return
        self._seek_x(self._x(event))
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._dragging:
            self._seek_x(self._x(event), force=True)
            self._dragging = False
            self.released.emit()
        event.accept()

    def _x(self, event) -> float:
        if hasattr(event, "position"):
            return float(event.position().x())
        return float(event.pos().x())

    def _seek_x(self, x: float, *, force: bool = False) -> None:
        pad = 8.0
        w = max(1.0, float(self.width()) - 2.0 * pad)
        r = max(0.0, min(1.0, (float(x) - pad) / w))
        if not force and abs(r - self._ratio) < 1e-6:
            return
        self._ratio = r
        self.update()
        self.ratio_changed.emit(r)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = float(self.width())
        h = float(self.height())
        painter.fillRect(self.rect(), QColor("#3c3c41"))
        gy = h * 0.5
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#9a9aa3"))
        painter.drawRoundedRect(QRectF(8, gy - 4, max(0.0, w - 16), 8), 4, 4)
        filled = max(0.0, min(w - 16, self._ratio * (w - 16)))
        painter.setBrush(QColor("#3ea6ff"))
        painter.drawRoundedRect(QRectF(8, gy - 4, filled, 8), 4, 4)
        cx = 8 + filled
        painter.setBrush(QColor("#ffffff"))
        painter.setPen(QPen(QColor("#2b89d6"), 1.5))
        painter.drawEllipse(QRectF(cx - 8, gy - 8, 16, 16))
