"""Centered figure frame; drag edges/corners to resize. Default fit is 4:3."""

from __future__ import annotations

from PyQt6.QtCore import QPoint, QRect, Qt
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QSizePolicy, QWidget

_EDGE = 10


class AspectFrame(QWidget):
    def __init__(self, child: QWidget, *, ratio: float = 4 / 3, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._child = child
        self._ratio = float(ratio)
        self._manual: tuple[int, int] | None = None
        self._drag_mode: str | None = None
        self._drag_origin = None
        self._drag_geom = None
        child.setParent(self)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(200, 150)
        self.setMouseTracking(True)

    def reset_fit(self) -> None:
        self._manual = None
        self._layout_child()

    def resizeEvent(self, event) -> None:  # noqa: N802
        self._layout_child()
        super().resizeEvent(event)

    def _fit_size(self) -> tuple[int, int]:
        pw, ph = max(1, self.width()), max(1, self.height())
        if pw / ph > self._ratio:
            fh = ph - 4
            fw = int(round(fh * self._ratio))
        else:
            fw = pw - 4
            fh = int(round(fw / self._ratio))
        return max(160, fw), max(120, fh)

    def _layout_child(self) -> None:
        pw, ph = self.width(), self.height()
        if self._manual is not None:
            fw, fh = self._manual
            fw = min(max(160, fw), pw - 4)
            fh = min(max(120, fh), ph - 4)
        else:
            fw, fh = self._fit_size()
        x = max(2, (pw - fw) // 2)
        y = max(2, (ph - fh) // 2)
        self._child.setGeometry(x, y, fw, fh)
        self._child.show()
        self._child.update()
        self.update()

    def _hit(self, pos) -> str | None:
        r = self._child.geometry().adjusted(-2, -2, 2, 2)
        if not r.adjusted(-_EDGE, -_EDGE, _EDGE, _EDGE).contains(pos):
            return None
        left = abs(pos.x() - r.left()) <= _EDGE
        right = abs(pos.x() - r.right()) <= _EDGE
        top = abs(pos.y() - r.top()) <= _EDGE
        bottom = abs(pos.y() - r.bottom()) <= _EDGE
        if top and left:
            return "tl"
        if top and right:
            return "tr"
        if bottom and left:
            return "bl"
        if bottom and right:
            return "br"
        if left:
            return "l"
        if right:
            return "r"
        if top:
            return "t"
        if bottom:
            return "b"
        return None

    def _cursor_for(self, mode: str | None):
        return {
            "l": Qt.CursorShape.SizeHorCursor,
            "r": Qt.CursorShape.SizeHorCursor,
            "t": Qt.CursorShape.SizeVerCursor,
            "b": Qt.CursorShape.SizeVerCursor,
            "tl": Qt.CursorShape.SizeFDiagCursor,
            "br": Qt.CursorShape.SizeFDiagCursor,
            "tr": Qt.CursorShape.SizeBDiagCursor,
            "bl": Qt.CursorShape.SizeBDiagCursor,
        }.get(mode, Qt.CursorShape.ArrowCursor)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        mode = self._hit(event.pos())
        if event.button() == Qt.MouseButton.LeftButton and mode:
            r = self._child.geometry()
            self._drag_mode = mode
            self._drag_origin = event.pos()
            self._drag_geom = QRect(r)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_mode is None:
            self.setCursor(self._cursor_for(self._hit(event.pos())))
            return
        r = QRect(self._drag_geom)
        dx = event.pos().x() - self._drag_origin.x()
        dy = event.pos().y() - self._drag_origin.y()
        mode = self._drag_mode
        if "l" in mode:
            r.setLeft(r.left() + dx)
        if "r" in mode:
            r.setRight(r.right() + dx)
        if "t" in mode:
            r.setTop(r.top() + dy)
        if "b" in mode:
            r.setBottom(r.bottom() + dy)
        fw = max(160, min(self.width() - 4, r.width()))
        fh = max(120, min(self.height() - 4, r.height()))
        self._manual = (fw, fh)
        self._layout_child()
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._drag_mode = None
        self._drag_origin = None
        self._drag_geom = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        self.reset_fit()
        event.accept()

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        r = self._child.geometry().adjusted(-1, -1, 1, 1)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#6a6a6e"), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(r)
        br = QRect(r.right() - 10, r.bottom() - 10, 12, 12)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#007acc"))
        painter.drawRect(br)
