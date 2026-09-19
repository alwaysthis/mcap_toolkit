"""Bottom transport: seek bar; time left, play controls centered, time mode right."""

from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QIcon, QPainter, QPen, QPixmap, QPolygonF
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from mcap_toolkit.plot.time_axis import TimeMode, format_playhead, playhead_ns_from_ratio, ratio_from_playhead
from mcap_toolkit.ui.seek_bar import SeekBar

_ICON_FG = "#c8c8c8"


def _media_icon(kind: str, size: int = 128) -> QIcon:
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    c = QColor(_ICON_FG)
    cx = size * 0.5
    cy = size * 0.5
    if kind in ("play", "pause"):
        p.setPen(QPen(c, max(2.4, size * 0.048), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.setBrush(Qt.BrushStyle.NoBrush)
        r = size * 0.40
        p.drawEllipse(QRectF(cx - r, cy - r, 2 * r, 2 * r))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(c))
        if kind == "play":
            s = size * 0.17
            tri = QPolygonF(
                [
                    QPointF(cx - s * 0.45, cy - s),
                    QPointF(cx - s * 0.45, cy + s),
                    QPointF(cx + s, cy),
                ]
            )
            p.drawPolygon(tri)
        else:
            bw = size * 0.075
            bh = size * 0.30
            gap = size * 0.07
            p.drawRoundedRect(QRectF(cx - gap - bw, cy - bh / 2, bw, bh), 2, 2)
            p.drawRoundedRect(QRectF(cx + gap, cy - bh / 2, bw, bh), 2, 2)
    else:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(c))
        bar_w = size * 0.085
        bar_h = size * 0.46
        bar_y = cy - bar_h / 2
        s = size * 0.20
        if kind == "prev":
            p.drawRoundedRect(QRectF(size * 0.20, bar_y, bar_w, bar_h), 1.5, 1.5)
            ox = size * 0.36
            tri = QPolygonF(
                [
                    QPointF(ox + s * 1.55, cy - s),
                    QPointF(ox + s * 1.55, cy + s),
                    QPointF(ox, cy),
                ]
            )
            p.drawPolygon(tri)
        else:
            p.drawRoundedRect(QRectF(size * 0.72, bar_y, bar_w, bar_h), 1.5, 1.5)
            ox = size * 0.30
            tri = QPolygonF(
                [
                    QPointF(ox, cy - s),
                    QPointF(ox, cy + s),
                    QPointF(ox + s * 1.55, cy),
                ]
            )
            p.drawPolygon(tri)
    p.end()
    return QIcon(pix)


class TransportBar(QWidget):
    play_toggled = pyqtSignal()
    step_prev = pyqtSignal()
    step_next = pyqtSignal()
    speed_changed = pyqtSignal(float)
    seek_ratio = pyqtSignal(float)
    time_mode_changed = pyqtSignal(str)
    scrubbing_changed = pyqtSignal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("transportBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._t0 = 0
        self._t1 = 0
        self._playhead_ns = 0
        self._playing = False
        self._icon_play = _media_icon("play")
        self._icon_pause = _media_icon("pause")
        self.setMinimumHeight(108)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.slider = SeekBar()

        self.btn_prev = self._icon_button("prev", "Previous frame", 40)
        self.btn_play = self._icon_button("play", "Play", 56)
        self.btn_play.setObjectName("playBtn")
        self.btn_play.setIcon(self._icon_play)
        self.btn_play.setIconSize(QSize(48, 48))
        self.btn_next = self._icon_button("next", "Next frame", 40)

        self.speed = QComboBox()
        for label, val in (
            ("0.25x", 0.25),
            ("0.5x", 0.5),
            ("1x", 1.0),
            ("2x", 2.0),
            ("4x", 4.0),
            ("8x", 8.0),
        ):
            self.speed.addItem(label, val)
        self.speed.setCurrentIndex(2)
        self.speed.setFixedWidth(72)

        self.time_mode = QComboBox()
        self.time_mode.addItem("Relative time", TimeMode.RELATIVE.value)
        self.time_mode.addItem("Absolute time", TimeMode.ABSOLUTE.value)
        self.time_mode.setFixedWidth(100)

        self.time_label = QLabel("—")
        self.time_label.setObjectName("transportTime")
        self.time_label.setMinimumWidth(148)
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        left = QWidget()
        left_row = QHBoxLayout(left)
        left_row.setContentsMargins(0, 0, 0, 0)
        left_row.setSpacing(0)
        left_row.addWidget(self.time_label, 0, Qt.AlignmentFlag.AlignVCenter)
        left_row.addStretch(1)

        mid = QWidget()
        mid_row = QHBoxLayout(mid)
        mid_row.setContentsMargins(0, 0, 0, 0)
        mid_row.setSpacing(6)
        mid_row.addStretch(1)
        mid_row.addWidget(self.btn_prev, 0, Qt.AlignmentFlag.AlignVCenter)
        mid_row.addWidget(self.btn_play, 0, Qt.AlignmentFlag.AlignVCenter)
        mid_row.addWidget(self.btn_next, 0, Qt.AlignmentFlag.AlignVCenter)
        mid_row.addStretch(1)

        right = QWidget()
        right_row = QHBoxLayout(right)
        right_row.setContentsMargins(0, 0, 0, 0)
        right_row.setSpacing(6)
        right_row.addStretch(1)
        right_row.addWidget(QLabel("Speed"), 0, Qt.AlignmentFlag.AlignVCenter)
        right_row.addWidget(self.speed, 0, Qt.AlignmentFlag.AlignVCenter)
        right_row.addSpacing(10)
        right_row.addWidget(QLabel("Time"), 0, Qt.AlignmentFlag.AlignVCenter)
        right_row.addWidget(self.time_mode, 0, Qt.AlignmentFlag.AlignVCenter)

        left.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        mid.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        right.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        controls = QHBoxLayout()
        controls.setContentsMargins(12, 2, 12, 10)
        controls.setSpacing(0)
        controls.addWidget(left, 1)
        controls.addWidget(mid, 1)
        controls.addWidget(right, 1)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 10, 16, 4)
        root.setSpacing(6)
        root.addWidget(self.slider)
        root.addLayout(controls)

        self.btn_play.clicked.connect(self._on_play_clicked)
        self.btn_prev.clicked.connect(self._on_prev_clicked)
        self.btn_next.clicked.connect(self._on_next_clicked)
        self.speed.currentIndexChanged.connect(self._emit_speed)
        self.time_mode.currentIndexChanged.connect(self._emit_mode)
        self.slider.pressed.connect(self._on_pressed)
        self.slider.released.connect(self._on_released)
        self.slider.ratio_changed.connect(self._on_ratio)

    def _icon_button(self, kind: str, tip: str, size: int) -> QPushButton:
        btn = QPushButton()
        btn.setObjectName("transportBtn")
        btn.setToolTip(tip)
        btn.setFixedSize(size, size)
        btn.setIcon(_media_icon(kind))
        btn.setIconSize(QSize(size - 8, size - 8))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.setFlat(True)
        btn.setAutoDefault(False)
        btn.setDefault(False)
        return btn

    def is_dragging(self) -> bool:
        return self.slider.is_dragging()

    def set_playing(self, playing: bool) -> None:
        self._playing = bool(playing)
        if self._playing:
            self.btn_play.setIcon(self._icon_pause)
            self.btn_play.setToolTip("Pause")
        else:
            self.btn_play.setIcon(self._icon_play)
            self.btn_play.setToolTip("Play")

    def set_range(self, t0_ns: int, t1_ns: int) -> None:
        self._t0 = int(t0_ns)
        self._t1 = int(t1_ns)

    def playhead_ns(self) -> int:
        if self._t1 > self._t0:
            return playhead_ns_from_ratio(self._t0, self._t1, self.slider.ratio())
        return int(self._playhead_ns)

    def slider_ratio(self) -> float:
        return self.slider.ratio()

    def set_playhead(self, t_ns: int) -> None:
        self._playhead_ns = int(t_ns)
        self._set_time_text(self._playhead_ns)
        if self.is_dragging():
            return
        self.slider.set_ratio(ratio_from_playhead(self._t0, self._t1, self._playhead_ns), force=True)

    def set_time_label(self, t_ns: int) -> None:
        self._set_time_text(int(t_ns))

    def current_time_mode(self) -> str:
        data = self.time_mode.currentData()
        if data in (TimeMode.RELATIVE.value, TimeMode.ABSOLUTE.value):
            return str(data)
        return TimeMode.RELATIVE.value

    def _set_time_text(self, t_ns: int) -> None:
        self.time_label.setText(format_playhead(int(t_ns), self._t0, self.current_time_mode()))

    def _emit_speed(self, _i: int) -> None:
        val = self.speed.currentData()
        self.speed_changed.emit(float(val if val is not None else 1.0))

    def _emit_mode(self, _i: int) -> None:
        self.time_mode_changed.emit(self.current_time_mode())

    def _on_play_clicked(self) -> None:
        self.slider.cancel_drag()
        self.play_toggled.emit()

    def _on_prev_clicked(self) -> None:
        self.slider.finish_drag()
        self.step_prev.emit()

    def _on_next_clicked(self) -> None:
        self.slider.finish_drag()
        self.step_next.emit()

    def _on_pressed(self) -> None:
        self.scrubbing_changed.emit(True)

    def _on_released(self) -> None:
        self._playhead_ns = playhead_ns_from_ratio(self._t0, self._t1, self.slider.ratio())
        self._set_time_text(self._playhead_ns)
        self.seek_ratio.emit(self.slider.ratio())
        self.scrubbing_changed.emit(False)

    def _on_ratio(self, ratio: float) -> None:
        self._playhead_ns = playhead_ns_from_ratio(self._t0, self._t1, float(ratio))
        self._set_time_text(self._playhead_ns)
        self.seek_ratio.emit(float(ratio))
