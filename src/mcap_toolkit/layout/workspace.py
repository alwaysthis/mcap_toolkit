"""Two editor groups with closable tabs. One figure per tab."""

from __future__ import annotations

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QCursor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QStyle,
    QStyleOptionTab,
    QTabBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from mcap_toolkit.layout.docks import (
    DOCK_IMAGE,
    DOCK_ROI,
    DOCK_SHUTTER,
    DOCK_TEMPERATURE,
    dock_titles,
)

LEFT_DEFAULT = (DOCK_IMAGE,)
RIGHT_DEFAULT = (DOCK_ROI, DOCK_TEMPERATURE, DOCK_SHUTTER)


def _tab_icon(kind: str) -> QIcon:
    pix = QPixmap(32, 32)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor("#8a8a90"), 2.2)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    if kind == "image":
        p.drawRoundedRect(6, 8, 20, 16, 3, 3)
        p.drawEllipse(10, 11, 5, 5)
        p.drawLine(8, 21, 14, 16)
        p.drawLine(14, 16, 18, 19)
        p.drawLine(18, 19, 24, 13)
    else:
        p.drawLine(7, 24, 7, 10)
        p.drawLine(7, 24, 25, 24)
        p.drawLine(7, 18, 13, 12)
        p.drawLine(13, 12, 18, 16)
        p.drawLine(18, 16, 25, 8)
    p.end()
    return QIcon(pix)


def _close_icon() -> QIcon:
    pix = QPixmap(32, 32)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor("#d8d8dc"), 3.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.drawLine(9, 9, 23, 23)
    p.drawLine(23, 9, 9, 23)
    p.end()
    return QIcon(pix)


_TAB_ICONS = {
    DOCK_IMAGE: "image",
    DOCK_ROI: "plot",
    DOCK_TEMPERATURE: "plot",
    DOCK_SHUTTER: "plot",
}


class EditorTabBar(QTabBar):
    """Top-rounded tabs that share the pane color; close button inset from the edge."""

    _RADIUS = 8.0
    PANE = QColor("#2d2d30")
    INACTIVE = QColor("#333337")
    HOVER = QColor("#303034")
    INK = QColor("#d4d4d4")
    INK_DIM = QColor("#b0b0b4")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMouseTracking(True)

    def tabSizeHint(self, index: int) -> QSize:  # noqa: N802
        size = super().tabSizeHint(index)
        return QSize(max(size.width() + 22, 108), max(size.height(), 30))

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        super().mouseMoveEvent(event)
        self.update()

    def leaveEvent(self, event) -> None:  # type: ignore[override]
        super().leaveEvent(event)
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setClipRect(event.rect())
        hover = self.tabAt(self.mapFromGlobal(QCursor.pos())) if self.underMouse() else -1
        for index in range(self.count()):
            self._paint_tab(painter, index, hover == index)

    def _paint_tab(self, painter: QPainter, index: int, hovered: bool) -> None:
        rect = self.tabRect(index)
        rect.setTop(max(rect.top(), 4))
        rect.setBottom(self.height())
        selected = index == self.currentIndex()
        if selected:
            fill, ink = self.PANE, self.INK
        elif hovered:
            fill, ink = self.HOVER, self.INK
        else:
            fill, ink = self.INACTIVE, self.INK_DIM

        x = float(rect.x())
        y = float(rect.y())
        w = float(rect.width())
        h = float(rect.height())
        r = self._RADIUS
        path = QPainterPath()
        path.moveTo(x, y + h)
        path.lineTo(x, y + r)
        path.quadTo(x, y, x + r, y)
        path.lineTo(x + w - r, y)
        path.quadTo(x + w, y, x + w, y + r)
        path.lineTo(x + w, y + h)
        path.closeSubpath()
        painter.fillPath(path, fill)

        option = QStyleOptionTab()
        self.initStyleOption(option, index)
        option.palette.setColor(option.palette.ColorRole.WindowText, ink)
        option.palette.setColor(option.palette.ColorRole.ButtonText, ink)
        option.rect = rect.adjusted(8, 0, -28, 0)
        self.style().drawControl(
            QStyle.ControlElement.CE_TabBarTabLabel, option, painter, self
        )


class EditorGroup(QWidget):
    tab_closed = pyqtSignal(str)
    tab_shown = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._bar = EditorTabBar()
        self._bar.setObjectName("editorTabBar")
        self._bar.setDocumentMode(True)
        self._bar.setTabsClosable(False)
        self._bar.setMovable(True)
        self._bar.setExpanding(False)
        self._bar.setDrawBase(False)
        self._bar.setElideMode(Qt.TextElideMode.ElideRight)
        self._bar.setIconSize(QSize(16, 16))
        self._bar.currentChanged.connect(self._on_current)
        self._bar.tabMoved.connect(self._on_tab_moved)

        strip = QWidget()
        strip.setObjectName("tabStrip")
        row = QHBoxLayout(strip)
        row.setContentsMargins(8, 0, 8, 0)
        row.setSpacing(0)
        row.addWidget(self._bar, 0)
        row.addStretch(1)

        self._stack = QStackedWidget()
        self._stack.setObjectName("editorPane")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(strip, 0)
        layout.addWidget(self._stack, 1)

    def tabBar(self) -> QTabBar:  # noqa: N802
        return self._bar

    def count(self) -> int:
        return self._bar.count()

    def currentIndex(self) -> int:  # noqa: N802
        return self._bar.currentIndex()

    def setCurrentIndex(self, index: int) -> None:  # noqa: N802
        self._bar.setCurrentIndex(index)

    def widget(self, index: int) -> QWidget | None:
        return self._stack.widget(index)

    def keys(self) -> list[str]:
        out: list[str] = []
        for i in range(self._bar.count()):
            key = self._bar.tabData(i)
            if key is not None:
                out.append(str(key))
        return out

    def index_of_key(self, key: str) -> int:
        for i in range(self._bar.count()):
            if str(self._bar.tabData(i)) == key:
                return i
        return -1

    def add_panel(self, key: str, title: str, widget: QWidget) -> None:
        existing = self.index_of_key(key)
        if existing >= 0:
            self._bar.setCurrentIndex(existing)
            return
        icon = _tab_icon(_TAB_ICONS.get(key, "plot"))
        idx = self._bar.addTab(icon, title)
        self._bar.setTabData(idx, key)
        self._attach_close(idx)
        self._stack.insertWidget(idx, widget)
        self._bar.setCurrentIndex(idx)
        self._stack.setCurrentIndex(idx)

    def take_key(self, key: str) -> QWidget | None:
        idx = self.index_of_key(key)
        if idx < 0:
            return None
        widget = self._stack.widget(idx)
        self._bar.removeTab(idx)
        if widget is not None:
            self._stack.removeWidget(widget)
        return widget

    def _attach_close(self, index: int) -> None:
        btn = QToolButton(self._bar)
        btn.setObjectName("tabCloseBtn")
        btn.setIcon(_close_icon())
        btn.setIconSize(QSize(10, 10))
        btn.setFixedSize(16, 16)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.setAutoRaise(True)
        btn.setToolTip("Close")
        btn.clicked.connect(self._on_close_btn)
        self._bar.setTabButton(index, QTabBar.ButtonPosition.RightSide, btn)

    def _on_close_btn(self) -> None:
        btn = self.sender()
        for i in range(self._bar.count()):
            if self._bar.tabButton(i, QTabBar.ButtonPosition.RightSide) is btn:
                self._on_close(i)
                return

    def _on_tab_moved(self, src: int, dst: int) -> None:
        widget = self._stack.widget(src)
        if widget is None:
            return
        self._stack.removeWidget(widget)
        self._stack.insertWidget(dst, widget)
        self._stack.setCurrentIndex(self._bar.currentIndex())

    def _on_close(self, index: int) -> None:
        key = self._bar.tabData(index)
        widget = self._stack.widget(index)
        self._bar.removeTab(index)
        if widget is not None:
            self._stack.removeWidget(widget)
            widget.setParent(self.parent())
            widget.hide()
        if key is not None:
            self.tab_closed.emit(str(key))

    def _on_current(self, index: int) -> None:
        if index < 0:
            return
        if 0 <= index < self._stack.count():
            self._stack.setCurrentIndex(index)
        key = self._bar.tabData(index)
        if key is not None:
            self.tab_shown.emit(str(key))


class Workspace(QWidget):
    """Blank until a file is opened; then two tab groups (left / right)."""

    tab_closed = pyqtSignal(str)
    tab_shown = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("workspace")
        self._panels: dict[str, QWidget] = {}
        self._titles = dock_titles()
        self._loading = False

        self._blank = QFrame()
        self._blank.setObjectName("workspace_blank")
        self._blank.setFrameShape(QFrame.Shape.NoFrame)
        blank_layout = QVBoxLayout(self._blank)
        blank_layout.setContentsMargins(24, 24, 24, 24)
        blank_layout.addStretch(1)
        self._idle_hint = QLabel("Open an .mcap file, or drop one here")
        self._idle_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._idle_hint.setObjectName("workspaceIdle")
        self._load_label = QLabel("Opening file…")
        self._load_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._load_label.setObjectName("workspaceLoading")
        self._load_bar = QProgressBar()
        self._load_bar.setObjectName("workspaceProgress")
        self._load_bar.setFixedWidth(360)
        self._load_bar.setMinimumHeight(12)
        self._load_bar.setTextVisible(False)
        self._load_bar.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._load_label.hide()
        self._load_bar.hide()
        blank_layout.addWidget(self._idle_hint, 0, Qt.AlignmentFlag.AlignHCenter)
        blank_layout.addWidget(self._load_label, 0, Qt.AlignmentFlag.AlignHCenter)
        blank_layout.addSpacing(12)
        blank_layout.addWidget(self._load_bar, 0, Qt.AlignmentFlag.AlignHCenter)
        blank_layout.addStretch(1)

        self.left = EditorGroup()
        self.left.setObjectName("editorLeft")
        self.right = EditorGroup()
        self.right.setObjectName("editorRight")
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(self.left)
        self.splitter.addWidget(self.right)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 2)
        self.splitter.setChildrenCollapsible(False)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._blank)
        self._stack.addWidget(self.splitter)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._stack)

        for group in (self.left, self.right):
            group.tab_closed.connect(self.tab_closed)
            group.tab_shown.connect(self.tab_shown)

    def is_blank(self) -> bool:
        return self._stack.currentWidget() is self._blank

    def is_loading(self) -> bool:
        return self._loading

    def set_panels(self, panels: dict[str, QWidget]) -> None:
        self._panels = dict(panels)
        for widget in self._panels.values():
            widget.hide()

    def show_idle(self) -> None:
        self._loading = False
        self._load_bar.hide()
        self._load_label.hide()
        self._idle_hint.show()
        self._stack.setCurrentWidget(self._blank)

    def show_loading(self, message: str, *, maximum: int = 0) -> None:
        self.clear_file()
        self._loading = True
        self._idle_hint.hide()
        self._load_label.setText(message)
        self._load_label.show()
        if maximum > 0:
            self._load_bar.setRange(0, maximum)
            self._load_bar.setValue(0)
        else:
            self._load_bar.setRange(0, 0)
        self._load_bar.show()
        self._stack.setCurrentWidget(self._blank)

    def set_loading_progress(self, value: int, maximum: int | None = None) -> None:
        if not self._loading:
            return
        if maximum is not None and maximum > 0:
            self._load_bar.setRange(0, maximum)
        if self._load_bar.maximum() > 0:
            self._load_bar.setValue(max(0, min(int(value), self._load_bar.maximum())))

    def hide_loading(self) -> None:
        self._loading = False
        self._load_bar.hide()
        self._load_label.hide()
        self._idle_hint.show()

    def clear_file(self) -> None:
        for group in (self.left, self.right):
            for key in list(group.keys()):
                widget = group.take_key(key)
                if widget is not None:
                    widget.setParent(self)
                    widget.hide()
        self._stack.setCurrentWidget(self._blank)

    def apply_factory(self) -> None:
        self.hide_loading()
        self.clear_file()
        if not self._panels:
            self.show_idle()
            return
        for key in LEFT_DEFAULT:
            self.show_panel(key, group=self.left)
        for key in RIGHT_DEFAULT:
            self.show_panel(key, group=self.right)
        self.splitter.setSizes([780, 520])
        self._stack.setCurrentWidget(self.splitter)

    def show_panel(self, key: str, group: EditorGroup | None = None) -> None:
        widget = self._panels.get(key)
        if widget is None:
            return
        self.hide_loading()
        if self.left.index_of_key(key) >= 0:
            self.left.setCurrentIndex(self.left.index_of_key(key))
            self._stack.setCurrentWidget(self.splitter)
            return
        if self.right.index_of_key(key) >= 0:
            self.right.setCurrentIndex(self.right.index_of_key(key))
            self._stack.setCurrentWidget(self.splitter)
            return
        target = group or (self.left if key == DOCK_IMAGE else self.right)
        target.add_panel(key, self._titles.get(key, key), widget)
        widget.show()
        self._stack.setCurrentWidget(self.splitter)

    def hide_panel(self, key: str) -> None:
        for group in (self.left, self.right):
            widget = group.take_key(key)
            if widget is not None:
                widget.setParent(self)
                widget.hide()
        if self.left.count() == 0 and self.right.count() == 0:
            self.show_idle()

    def has_panel(self, key: str) -> bool:
        return self.left.index_of_key(key) >= 0 or self.right.index_of_key(key) >= 0

    def panel_visible(self, key: str) -> bool:
        if self.is_blank():
            return False
        li = self.left.index_of_key(key)
        if li >= 0:
            return self.left.tabBar().currentIndex() == li
        ri = self.right.index_of_key(key)
        if ri >= 0:
            return self.right.tabBar().currentIndex() == ri
        return False

    def current_plot_keys(self) -> list[str]:
        keys: list[str] = []
        for group in (self.left, self.right):
            i = group.currentIndex()
            if i < 0:
                continue
            key = group.tabBar().tabData(i)
            if key and str(key) != DOCK_IMAGE:
                keys.append(str(key))
        return keys
