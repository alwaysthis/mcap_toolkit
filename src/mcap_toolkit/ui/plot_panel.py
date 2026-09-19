"""One MATLAB-style pyqtgraph figure per tab."""

from __future__ import annotations

from PyQt6.QtCore import QLineF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

import numpy as np
import pyqtgraph as pg
import pyqtgraph.exporters  # noqa: F401

from mcap_toolkit.plot.downsample import downsample_xy, stairs_xy
from mcap_toolkit.plot.matlab import AXES_FG, FIGURE_BG, GRID, PLAYHEAD
from mcap_toolkit.plot.models import PlotSpec, Series
from mcap_toolkit.plot.time_axis import (
    TimeMode,
    clock_tick_positions,
    format_clock_hms,
    is_clock_mode,
    nice_clock_step,
    rel_seconds_to_ns,
    x_values,
    xlabel_for_mode,
)
from mcap_toolkit.ui.aspect_frame import AspectFrame

pg.setConfigOptions(antialias=True)

_AXIS_FONT = QFont("Arial", 9)
_LINE_WIDTH = 2.0
_AXIS_WIDTH = 1.0
_TICK_WIDTH = 1.0
_GRID_WIDTH = 0.5
_TICK_LEN = 6
_LEGEND_WIDTH = 148
_LEGEND_RAIL = 22


def _tool_icon(kind: str) -> QIcon:
    pix = QPixmap(18, 18)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor("#d4d4d4"), 1.7)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    if kind == "box":
        p.drawRect(3, 4, 12, 10)
        p.drawLine(3, 14, 7, 9)
    elif kind == "pan":
        p.drawLine(9, 2, 9, 16)
        p.drawLine(2, 9, 16, 9)
        p.drawLine(9, 2, 6, 5)
        p.drawLine(9, 2, 12, 5)
        p.drawLine(9, 16, 6, 13)
        p.drawLine(9, 16, 12, 13)
        p.drawLine(2, 9, 5, 6)
        p.drawLine(2, 9, 5, 12)
        p.drawLine(16, 9, 13, 6)
        p.drawLine(16, 9, 13, 12)
    elif kind == "reset":
        p.drawArc(3, 3, 12, 12, 40 * 16, 280 * 16)
        p.drawLine(14, 3, 14, 7)
        p.drawLine(14, 3, 10, 3)
    p.end()
    return QIcon(pix)


def _major_ticks(axis: pg.AxisItem, vmin: float, vmax: float, px: float) -> list[float]:
    try:
        levels = axis.tickValues(vmin, vmax, max(float(px), 1.0))
    except Exception:
        return []
    if not levels:
        return []
    values = levels[0][1]
    return [float(v) for v in values]


def _tick_label(value: float, spacing: float) -> str:
    v = float(value)
    step = abs(float(spacing)) if spacing else 0.0
    if step >= 1.0:
        return f"{v:.0f}"
    if step >= 0.1:
        return f"{v:.1f}"
    if step >= 0.01:
        return f"{v:.2f}"
    return f"{v:.3g}"


class SparseGridItem(pg.GraphicsObject):
    """Grid in the ViewBox so the playhead cannot erase axis-painted lines."""

    def __init__(self, plot: pg.PlotWidget) -> None:
        super().__init__()
        self._plot = plot
        self.setZValue(-1000)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

    def boundingRect(self) -> QRectF:  # noqa: N802
        vb = self.getViewBox()
        if vb is None:
            return QRectF()
        return QRectF(vb.viewRect())

    def viewRangeChanged(self) -> None:  # noqa: N802
        self.prepareGeometryChange()
        self.update()

    def paint(self, painter, _option, _widget=None) -> None:
        vb = self.getViewBox()
        if vb is None:
            return
        (x0, x1), (y0, y1) = vb.viewRange()
        painter.setPen(pg.mkPen(GRID, width=_GRID_WIDTH))
        left = self._plot.getAxis("left")
        bottom = self._plot.getAxis("bottom")
        for y in _major_ticks(left, y0, y1, vb.height()):
            painter.drawLine(QLineF(x0, y, x1, y))
        for x in _major_ticks(bottom, x0, x1, vb.width()):
            painter.drawLine(QLineF(x, y0, x, y1))


class SparseAxisItem(pg.AxisItem):
    """Majors only — box/ticks width 1, numeric labels on."""

    def __init__(self, orientation: str = "left") -> None:
        super().__init__(orientation=orientation)
        self.setPen(pg.mkPen(AXES_FG, width=_AXIS_WIDTH))
        self.setTickPen(pg.mkPen(AXES_FG, width=_TICK_WIDTH))
        self.setTextPen(AXES_FG)
        self.setTickFont(_AXIS_FONT)
        self.enableAutoSIPrefix(False)
        self.setStyle(tickLength=_TICK_LEN, showValues=True, autoExpandTextSpace=True)
        self.setGrid(False)

    def tickValues(self, minVal, maxVal, size):  # noqa: N802
        levels = super().tickValues(minVal, maxVal, size)
        if not levels:
            return []
        spacing, values = levels[0]
        if len(values) > 5:
            stride = max(1, int(round(len(values) / 4.0)))
            values = list(values)[::stride]
        return [(spacing, values)]

    def tickStrings(self, values, scale, spacing):  # noqa: N802
        del scale
        return [_tick_label(v, spacing) for v in values]


class ClockAxisItem(pg.AxisItem):
    """Tick marks and labels aligned to local clock HH:MM:SS."""

    def __init__(self, orientation: str = "bottom", t0_ns: int = 0) -> None:
        super().__init__(orientation=orientation)
        self.t0_ns = int(t0_ns)
        self.enableAutoSIPrefix(False)
        self.scale = 1.0
        self.setPen(pg.mkPen(AXES_FG, width=_AXIS_WIDTH))
        self.setTickPen(pg.mkPen(AXES_FG, width=_TICK_WIDTH))
        self.setTextPen(AXES_FG)
        self.setTickFont(_AXIS_FONT)
        self.setStyle(tickLength=_TICK_LEN, showValues=True, autoExpandTextSpace=True)
        self.setGrid(False)

    def tickValues(self, minVal, maxVal, size):  # noqa: N802
        span = abs(float(maxVal) - float(minVal))
        px = max(float(size), 1.0)
        step = nice_clock_step(span, target_ticks=max(3, int(px / 160)))
        majors = clock_tick_positions(self.t0_ns, float(minVal), float(maxVal), step)
        if not majors:
            return []
        return [(step, majors)]

    def tickStrings(self, values, scale, spacing):  # noqa: N802
        del scale, spacing
        return [format_clock_hms(rel_seconds_to_ns(self.t0_ns, float(v))) for v in values]


def _swatch_icon(color: str) -> QIcon:
    pix = QPixmap(12, 12)
    pix.fill(QColor(color))
    return QIcon(pix)


def _style_axis(axis: pg.AxisItem, *, show_values: bool = False) -> None:
    axis.setPen(pg.mkPen(AXES_FG, width=_AXIS_WIDTH))
    try:
        axis.setTickPen(pg.mkPen(AXES_FG, width=_TICK_WIDTH))
    except Exception:
        pass
    axis.setTextPen(AXES_FG)
    axis.setTickFont(_AXIS_FONT)
    axis.setStyle(
        tickLength=_TICK_LEN,
        showValues=show_values,
        autoExpandTextSpace=show_values,
    )
    try:
        axis.setGrid(False)
    except Exception:
        pass


class PlotPanel(QWidget):
    export_png = pyqtSignal()
    export_csv = pyqtSignal()
    seek_requested = pyqtSignal(object)

    def __init__(self, spec: PlotSpec | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._spec = spec or PlotSpec(kind="", ylabel="")
        self._t0_ns = 0
        self._t1_ns = 0
        self._playhead_ns = 0
        self._mode = TimeMode.RELATIVE
        self._curves: dict[str, pg.PlotDataItem] = {}
        self._bufs: dict[str, tuple[np.ndarray, np.ndarray, int]] = {}
        self._y0: float | None = None
        self._y1: float | None = None
        self._streaming = False
        self._legend_open = True
        self._syncing_playhead = False
        self._needs_fit = False

        self.plot = pg.PlotWidget(background=FIGURE_BG)
        self.plot.setBackground(FIGURE_BG)
        self.plot.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        try:
            self.plot.viewport().setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
            self.plot.viewport().setAutoFillBackground(True)
        except Exception:
            pass
        self.plot.setAxisItems(
            {
                "left": SparseAxisItem("left"),
                "bottom": SparseAxisItem("bottom"),
                "right": SparseAxisItem("right"),
                "top": SparseAxisItem("top"),
            }
        )
        self.plot.showAxis("right", True)
        self.plot.showAxis("top", True)
        self.plot.showGrid(x=False, y=False)
        self.plot.setLabel("left", self._spec.ylabel, color=AXES_FG)
        self._apply_bottom_axis()
        self.plot.setMenuEnabled(False)
        self.plot.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.plot.customContextMenuRequested.connect(self._plot_menu)
        vb = self.plot.getViewBox()
        vb.setMouseMode(vb.PanMode)
        vb.setBorder(None)

        self._grid = SparseGridItem(self.plot)
        self.plot.addItem(self._grid, ignoreBounds=True)
        self._playhead_line = pg.InfiniteLine(
            angle=90,
            movable=False,
            pen=pg.mkPen(PLAYHEAD, width=1.0, style=Qt.PenStyle.DashLine),
        )
        self._playhead_line.setZValue(64)
        self.plot.addItem(self._playhead_line, ignoreBounds=True)

        self.hint = QLabel("")
        self.hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint.hide()

        self.series_list = QListWidget()
        self.series_list.setMinimumWidth(120)
        self.series_list.itemChanged.connect(self._item_changed)
        self.series_list.itemDoubleClicked.connect(self._rename_item)

        self._btn_box = QToolButton()
        self._btn_box.setIcon(_tool_icon("box"))
        self._btn_box.setToolTip("Box zoom")
        self._btn_box.setCheckable(True)
        self._btn_box.setAutoRaise(True)
        self._btn_box.toggled.connect(self._on_box)

        self._btn_pan = QToolButton()
        self._btn_pan.setIcon(_tool_icon("pan"))
        self._btn_pan.setToolTip("Pan")
        self._btn_pan.setCheckable(True)
        self._btn_pan.setChecked(True)
        self._btn_pan.setAutoRaise(True)
        self._btn_pan.toggled.connect(self._on_pan)

        self._btn_reset = QToolButton()
        self._btn_reset.setIcon(_tool_icon("reset"))
        self._btn_reset.setToolTip("Reset axes")
        self._btn_reset.setAutoRaise(True)
        self._btn_reset.clicked.connect(self.reset_view)

        tools = QHBoxLayout()
        tools.setContentsMargins(0, 0, 0, 0)
        tools.setSpacing(4)
        tools.addWidget(self._btn_box)
        tools.addWidget(self._btn_pan)
        tools.addWidget(self._btn_reset)
        tools.addStretch(1)

        self._aspect = AspectFrame(self.plot)
        plot_stack = QVBoxLayout()
        plot_stack.setContentsMargins(0, 0, 0, 0)
        plot_stack.setSpacing(0)
        plot_stack.addWidget(self._aspect, 1)
        plot_stack.addWidget(self.hint)
        plot_host = QWidget()
        plot_host.setLayout(plot_stack)

        self._legend_toggle = QToolButton()
        self._legend_toggle.setText("‹")
        self._legend_toggle.setToolTip("Hide legend")
        self._legend_toggle.setAutoRaise(True)
        self._legend_toggle.setFixedWidth(22)
        self._legend_toggle.clicked.connect(self._toggle_legend)

        self._legend_title = QLabel("Legend")
        legend_head = QHBoxLayout()
        legend_head.setContentsMargins(4, 2, 2, 2)
        legend_head.addWidget(self._legend_title, 1)
        legend_head.addWidget(self._legend_toggle)

        self._legend_rail = QWidget()
        self._legend_rail.setObjectName("legendRail")
        self._legend_rail.setMinimumWidth(_LEGEND_RAIL)
        rail = QVBoxLayout(self._legend_rail)
        rail.setContentsMargins(0, 0, 0, 0)
        rail.setSpacing(0)
        rail.addLayout(legend_head)
        rail.addWidget(self.series_list, 0)
        self._legend_rail.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Maximum)
        self._legend_rail.setFixedWidth(_LEGEND_WIDTH)
        self.series_list.setMaximumHeight(140)

        side = QVBoxLayout()
        side.setContentsMargins(0, 0, 0, 0)
        side.setSpacing(0)
        side.addWidget(self._legend_rail, 0, Qt.AlignmentFlag.AlignTop)
        side.addStretch(1)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(plot_host, 1)
        body.addLayout(side, 0)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.addLayout(tools)
        layout.addLayout(body, 1)

    def spec(self) -> PlotSpec:
        return self._spec

    def set_spec(self, spec: PlotSpec, t0_ns: int, t1_ns: int, *, fit: bool = True) -> None:
        self._spec = spec
        self._t0_ns = int(t0_ns)
        self._t1_ns = int(t1_ns)
        self._bufs = {}
        self._y0 = None
        self._y1 = None
        self._streaming = False
        for s in spec.series:
            t = np.empty(64, dtype=np.int64)
            y = np.empty(64, dtype=np.float64)
            self._bufs[s.key] = (t, y, 0)
            s.t_ns = t[:0]
            s.y = y[:0]
        self.plot.setLabel("left", spec.ylabel, color=AXES_FG)
        if fit:
            self._apply_bottom_axis()
        self._rebuild_list()
        for key in list(self._curves):
            self.plot.removeItem(self._curves.pop(key))
        if spec.series:
            self.hint.hide()
        elif spec.empty_hint:
            self.hint.setText(spec.empty_hint)
            self.hint.show()
        else:
            self.hint.hide()
        self._playhead_line.setVisible(False)
        if fit:
            self._needs_fit = True
            self.reset_view()
            if self.width() > 80 and self.height() > 80:
                self._needs_fit = False
        else:
            self._apply_xy_from_data(reset_tools=False)

    def update_spec(self, spec: PlotSpec, t0_ns: int, t1_ns: int, *, streaming: bool = True) -> None:
        """Replace series while streaming; keep the full-file X span."""
        self._spec = spec
        self._t0_ns = int(t0_ns)
        self._t1_ns = int(t1_ns)
        self.plot.setLabel("left", spec.ylabel, color=AXES_FG)
        if spec.series or not spec.empty_hint:
            self.hint.hide()
        else:
            self.hint.setText(spec.empty_hint)
            self.hint.show()
        has_series = any(s.visible and s.t_ns.size > 0 for s in spec.series)
        self._playhead_line.setVisible(has_series)
        self.plot.setAntialiasing(not streaming)
        self._patch_curves(max_points=1500 if streaming else 8000)
        self._apply_xy_from_data(reset_tools=False)

    def append_chunks(self, chunks: list[tuple], *, streaming: bool = True) -> None:
        """Append worker display points into reserved numpy buffers (no full-history copy)."""
        self._streaming = streaming
        self.plot.setAntialiasing(not streaming)
        added_legend = False
        for kind, key, label, color, step, t_raw, y_raw in chunks:
            del kind
            t_new = np.asarray(t_raw, dtype=np.int64)
            y_new = np.asarray(y_raw, dtype=np.float64)
            if t_new.size == 0:
                continue
            spec_row = None
            for s in self._spec.series:
                if s.key == key:
                    spec_row = s
                    break
            if spec_row is None:
                spec_row = Series(
                    key=str(key),
                    label=str(label),
                    t_ns=np.empty(0, dtype=np.int64),
                    y=np.empty(0, dtype=np.float64),
                    step=bool(step),
                    color=str(color),
                )
                self._spec.series.append(spec_row)
                added_legend = True
            t_buf, y_buf, n = self._bufs.get(key, (np.empty(64, dtype=np.int64), np.empty(64, dtype=np.float64), 0))
            need = n + int(t_new.size)
            if need > t_buf.size:
                cap = max(need, t_buf.size * 2)
                nt = np.empty(cap, dtype=np.int64)
                ny = np.empty(cap, dtype=np.float64)
                nt[:n] = t_buf[:n]
                ny[:n] = y_buf[:n]
                t_buf, y_buf = nt, ny
            t_buf[n:need] = t_new
            y_buf[n:need] = y_new
            n = need
            self._bufs[key] = (t_buf, y_buf, n)
            spec_row.t_ns = t_buf[:n]
            spec_row.y = y_buf[:n]
            if spec_row.visible:
                self._set_curve_data(spec_row)
            finite = y_new[np.isfinite(y_new)]
            if finite.size:
                lo, hi = float(np.min(finite)), float(np.max(finite))
                self._y0 = lo if self._y0 is None else min(self._y0, lo)
                self._y1 = hi if self._y1 is None else max(self._y1, hi)
        if added_legend:
            self._ensure_legend_keys()
        if any(s.visible and s.t_ns.size > 0 for s in self._spec.series):
            self.hint.hide()
            self._playhead_line.setVisible(True)
        self._apply_xy_from_data(reset_tools=False)

    def finish_streaming(self) -> None:
        self._streaming = False
        self.plot.setAntialiasing(True)
        self._sync_playhead_line()

    def _set_curve_data(self, s) -> None:
        x = x_values(s.t_ns, self._t0_ns, self._mode)
        y = np.asarray(s.y, dtype=np.float64)
        if s.step:
            x, y = stairs_xy(x, y)
        if x.size > 8000:
            x, y = downsample_xy(x, y, max_points=8000)
        curve = self._curves.get(s.key)
        if curve is None:
            curve = self.plot.plot(
                x,
                y,
                pen=pg.mkPen(s.color, width=_LINE_WIDTH),
                name=s.label,
                connect="finite",
            )
            self._curves[s.key] = curve
        else:
            curve.setData(x, y)

    def _redraw(self) -> None:
        self._patch_curves(max_points=8000)

    def _patch_curves(self, *, max_points: int) -> None:
        del max_points
        wanted = [s for s in self._spec.series if s.visible and s.t_ns.size > 0]
        wanted_keys = {s.key for s in wanted}
        for key in list(self._curves):
            if key not in wanted_keys:
                self.plot.removeItem(self._curves.pop(key))
        legend_changed = False
        for s in wanted:
            if s.key not in self._curves:
                legend_changed = True
            self._set_curve_data(s)
        if legend_changed or self.series_list.count() != len(self._spec.series):
            self._ensure_legend_keys()
        self._sync_playhead_line()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if self._needs_fit:
            QTimer.singleShot(0, self._fit_if_needed)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self._needs_fit and self.width() > 80 and self.height() > 80:
            QTimer.singleShot(0, self._fit_if_needed)

    def _fit_if_needed(self) -> None:
        if not self._needs_fit:
            return
        if self.width() < 80 or self.height() < 80:
            return
        self._needs_fit = False
        self.relayout()

    def set_time_mode(self, mode: TimeMode | str) -> None:
        new = TimeMode(mode) if not isinstance(mode, TimeMode) else mode
        changed = new != self._mode
        self._mode = new
        self._apply_bottom_axis()
        self._redraw()
        if changed:
            self.reset_view()
        self._sync_playhead_line()

    def relayout(self) -> None:
        """Redraw after the tab has a real size."""
        self._aspect.reset_fit()
        self._redraw()
        self.reset_view()
        self._sync_playhead_line()
        self.plot.update()
        self.update()

    def _apply_bottom_axis(self) -> None:
        if is_clock_mode(self._mode):
            axis = ClockAxisItem(orientation="bottom", t0_ns=self._t0_ns)
        else:
            axis = SparseAxisItem("bottom")
        self.plot.setAxisItems({"bottom": axis})
        self.plot.setLabel("bottom", xlabel_for_mode(self._mode), color=AXES_FG)
        self.plot.showAxis("right", True)
        self.plot.showAxis("top", True)
        _style_axis(self.plot.getAxis("left"), show_values=True)
        _style_axis(self.plot.getAxis("bottom"), show_values=True)
        _style_axis(self.plot.getAxis("right"), show_values=False)
        _style_axis(self.plot.getAxis("top"), show_values=False)
        self.plot.showGrid(x=False, y=False)
        self.plot.getAxis("left").setWidth(56)
        self.plot.getAxis("right").setWidth(10)
        self.plot.getAxis("top").setHeight(10)
        self.plot.getAxis("bottom").setHeight(40)
        if hasattr(self, "_grid"):
            self._grid.prepareGeometryChange()
            self._grid.update()

    def set_playhead(self, t_ns: int) -> None:
        self._playhead_ns = int(t_ns)
        self._sync_playhead_line()

    def x_range_ns(self) -> tuple[int, int]:
        (x0, x1), _ = self.plot.viewRange()
        return rel_seconds_to_ns(self._t0_ns, x0), rel_seconds_to_ns(self._t0_ns, x1)

    def reset_view(self) -> None:
        self._apply_xy_from_data(reset_tools=True)
        self._aspect.reset_fit()

    def _apply_xy_from_data(self, *, reset_tools: bool) -> None:
        x0 = 0.0
        x1 = max(1e-6, (int(self._t1_ns) - int(self._t0_ns)) / 1e9)
        y0: float | None = None
        y1: float | None = None
        for s in self._spec.series:
            if not s.visible or s.y.size == 0:
                continue
            yy = np.asarray(s.y, dtype=np.float64)
            finite = yy[np.isfinite(yy)]
            if finite.size == 0:
                continue
            lo, hi = float(np.min(finite)), float(np.max(finite))
            y0 = lo if y0 is None else min(y0, lo)
            y1 = hi if y1 is None else max(y1, hi)
        self.plot.enableAutoRange(x=False, y=False)
        self.plot.setXRange(x0, x1, padding=0.02)
        if y0 is None or y1 is None:
            self.plot.setYRange(0.0, 1.0, padding=0.0)
        elif y1 <= y0:
            pad = abs(y0) * 0.05 + 0.1
            self.plot.setYRange(y0 - pad, y1 + pad, padding=0.0)
        else:
            self.plot.setYRange(y0, y1, padding=0.08)
        if not reset_tools:
            return
        self._btn_box.blockSignals(True)
        self._btn_pan.blockSignals(True)
        self._btn_box.setChecked(False)
        self._btn_pan.setChecked(True)
        self._btn_box.blockSignals(False)
        self._btn_pan.blockSignals(False)
        self._apply_mouse_mode()

    def _on_box(self, on: bool) -> None:
        if on:
            self._btn_pan.blockSignals(True)
            self._btn_pan.setChecked(False)
            self._btn_pan.blockSignals(False)
        elif not self._btn_pan.isChecked():
            self._btn_pan.setChecked(True)
        self._apply_mouse_mode()

    def _on_pan(self, on: bool) -> None:
        if on:
            self._btn_box.blockSignals(True)
            self._btn_box.setChecked(False)
            self._btn_box.blockSignals(False)
        elif not self._btn_box.isChecked():
            self._btn_box.setChecked(True)
        self._apply_mouse_mode()

    def _apply_mouse_mode(self) -> None:
        vb = self.plot.getViewBox()
        vb.setMouseMode(vb.RectMode if self._btn_box.isChecked() else vb.PanMode)

    def _toggle_legend(self) -> None:
        self._legend_open = not self._legend_open
        self._legend_title.setVisible(self._legend_open)
        self.series_list.setVisible(self._legend_open)
        if self._legend_open:
            self._legend_toggle.setText("‹")
            self._legend_toggle.setToolTip("Hide legend")
            self._legend_rail.setFixedWidth(_LEGEND_WIDTH)
        else:
            self._legend_toggle.setText("›")
            self._legend_toggle.setToolTip("Show legend")
            self._legend_rail.setFixedWidth(_LEGEND_RAIL)

    def _legend_item(self, s) -> QListWidgetItem:
        item = QListWidgetItem(_swatch_icon(s.color), s.label)
        item.setData(Qt.ItemDataRole.UserRole, s.key)
        item.setFlags(
            item.flags()
            | Qt.ItemFlag.ItemIsUserCheckable
            | Qt.ItemFlag.ItemIsEditable
        )
        item.setCheckState(Qt.CheckState.Checked if s.visible else Qt.CheckState.Unchecked)
        item.setToolTip("Check to show; double-click to rename (display name only)")
        return item

    def _rebuild_list(self) -> None:
        self.series_list.blockSignals(True)
        self.series_list.clear()
        for s in self._spec.series:
            self.series_list.addItem(self._legend_item(s))
        self.series_list.blockSignals(False)
        self._fit_legend()

    def _ensure_legend_keys(self) -> None:
        have: set[str] = set()
        for i in range(self.series_list.count()):
            key = self.series_list.item(i).data(Qt.ItemDataRole.UserRole)
            if key is not None:
                have.add(str(key))
        wanted = [s.key for s in self._spec.series]
        if have - set(wanted):
            self._rebuild_list()
            return
        added = False
        self.series_list.blockSignals(True)
        for s in self._spec.series:
            if s.key in have:
                continue
            self.series_list.addItem(self._legend_item(s))
            added = True
        self.series_list.blockSignals(False)
        if added:
            self._fit_legend()

    def _fit_legend(self) -> None:
        n = max(1, self.series_list.count())
        row = self.series_list.sizeHintForRow(0)
        if row <= 0:
            row = 22
        frame = 8 + self.series_list.frameWidth() * 2
        self.series_list.setFixedHeight(min(frame + n * row, 148))

    def _item_changed(self, item: QListWidgetItem) -> None:
        key = item.data(Qt.ItemDataRole.UserRole)
        for s in self._spec.series:
            if s.key == key:
                s.visible = item.checkState() == Qt.CheckState.Checked
                s.label = item.text()
                break
        self._redraw()

    def _rename_item(self, item: QListWidgetItem) -> None:
        text, ok = QInputDialog.getText(self, "Custom label", "Series name:", text=item.text())
        if ok and text.strip():
            item.setText(text.strip())

    def _plot_menu(self, pos) -> None:
        menu = QMenu(self)
        box = menu.addAction("Box zoom")
        box.setCheckable(True)
        box.setChecked(self._btn_box.isChecked())
        pan = menu.addAction("Pan")
        pan.setCheckable(True)
        pan.setChecked(self._btn_pan.isChecked())
        reset = menu.addAction("Reset axes")
        legend = menu.addAction("Legend")
        legend.setCheckable(True)
        legend.setChecked(self._legend_open)
        menu.addSeparator()
        png = menu.addAction("Export PNG")
        csv = menu.addAction("Export CSV")
        chosen = menu.exec(self.plot.mapToGlobal(pos))
        if chosen is box:
            self._btn_box.setChecked(True)
        elif chosen is pan:
            self._btn_pan.setChecked(True)
        elif chosen is reset:
            self.reset_view()
        elif chosen is legend:
            self._toggle_legend()
        elif chosen is png:
            self.export_png.emit()
        elif chosen is csv:
            self.export_csv.emit()

    def _line_moved(self) -> None:
        if self._syncing_playhead:
            return
        try:
            x = float(self._playhead_line.value())
            self.seek_requested.emit(rel_seconds_to_ns(self._t0_ns, x))
        except (TypeError, OverflowError, ValueError):
            return

    def _sync_playhead_line(self) -> None:
        self._syncing_playhead = True
        self._playhead_line.blockSignals(True)
        try:
            x = (int(self._playhead_ns) - int(self._t0_ns)) / 1e9
            self._playhead_line.setValue(x)
            if hasattr(self, "_grid"):
                self._grid.update()
        finally:
            self._playhead_line.blockSignals(False)
            self._syncing_playhead = False

    def grab_plot_png(self, path: str) -> None:
        exporter = pg.exporters.ImageExporter(self.plot.plotItem)
        exporter.export(path)
