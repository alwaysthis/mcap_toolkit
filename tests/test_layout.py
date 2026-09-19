"""Two-pane tab workspace: blank until factory layout after a file is conceptually open."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QLabel

from mcap_toolkit.layout.docks import DOCK_IMAGE, DOCK_ORDER, DOCK_ROI, dock_titles
from mcap_toolkit.layout.workspace import Workspace


def test_workspace_starts_blank() -> None:
    app = QApplication.instance() or QApplication([])
    titles = dock_titles()
    panels = {key: QLabel(titles[key]) for key in DOCK_ORDER}
    ws = Workspace()
    ws.set_panels(panels)
    ws.show()
    app.processEvents()
    assert ws.is_blank()
    assert ws.left.count() == 0
    assert ws.right.count() == 0
    ws.close()
    app.processEvents()


def test_factory_tabs_are_not_tiled() -> None:
    app = QApplication.instance() or QApplication([])
    titles = dock_titles()
    panels = {key: QLabel(titles[key]) for key in DOCK_ORDER}
    ws = Workspace()
    ws.set_panels(panels)
    ws.show()
    ws.apply_factory()
    app.processEvents()
    assert not ws.is_blank()
    assert ws.left.keys() == [DOCK_IMAGE]
    assert DOCK_ROI in ws.right.keys()
    assert ws.right.count() == 3
    assert ws.left.count() == 1
    ws.close()
    app.processEvents()


def test_loading_overlay_stays_blank() -> None:
    app = QApplication.instance() or QApplication([])
    titles = dock_titles()
    panels = {key: QLabel(titles[key]) for key in DOCK_ORDER}
    ws = Workspace()
    ws.set_panels(panels)
    ws.show()
    ws.show_loading("Opening demo.mcap…")
    app.processEvents()
    assert ws.is_blank()
    assert ws.is_loading()
    ws.show_idle()
    app.processEvents()
    assert ws.is_blank()
    assert not ws.is_loading()
    ws.close()
    app.processEvents()
