"""VS Code–inspired chrome, slightly lifted off pure black, with separators."""

from __future__ import annotations

VSCODE_QSS = """
QMainWindow, QDialog {
    background-color: #333337;
    color: #d4d4d4;
    font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif;
    font-size: 13px;
}
QWidget {
    color: #d4d4d4;
    font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif;
}
QMenuBar {
    background-color: #3e3e42;
    color: #d4d4d4;
    border: none;
    border-bottom: 1px solid #6a6a6e;
    padding: 2px 0;
}
QMenuBar::item {
    background: transparent;
    padding: 4px 10px;
}
QMenuBar::item:selected {
    background-color: #505054;
}
QMenu {
    background-color: #3c3c41;
    color: #d4d4d4;
    border: 1px solid #6a6a6e;
    padding: 4px;
}
QMenu::item {
    padding: 4px 24px 4px 12px;
}
QMenu::item:selected {
    background-color: #094771;
    color: #ffffff;
}
QStatusBar {
    background-color: #3c3c41;
    color: #d4d4d4;
    border-top: 1px solid #6a6a6e;
}
QStatusBar::item {
    border: none;
}
QSplitter::handle {
    background-color: #6a6a6e;
}
QSplitter::handle:horizontal {
    width: 4px;
}
QSplitter::handle:vertical {
    height: 4px;
}
QTabBar {
    background-color: transparent;
    qproperty-drawBase: 0;
}
QTabBar::tab {
    background-color: transparent;
    color: #d4d4d4;
    padding: 7px 12px 6px 10px;
    border: none;
    margin: 6px 4px 0 0;
    min-height: 22px;
    min-width: 72px;
}
#tabStrip {
    background-color: #3c3c41;
}
#editorPane {
    background-color: #2d2d30;
    border: none;
}
#workspace_blank {
    background-color: #2d2d30;
}
#workspaceIdle, #workspaceLoading {
    color: #b0b0b0;
    font-size: 14px;
}
QProgressBar {
    background-color: #252528;
    border: 1px solid #5a5a60;
    border-radius: 5px;
    height: 10px;
    text-align: center;
    color: #d4d4d4;
}
QProgressBar::chunk {
    background-color: #3ea6ff;
    border-radius: 4px;
}
#workspace {
    background-color: #2d2d30;
    border-bottom: 1px solid #6a6a6e;
}
#transportBar {
    background-color: #3c3c41;
    border-top: 1px solid #6a6a6e;
}
#legendRail {
    background-color: #333338;
    border-left: 1px solid #6a6a6e;
}
QComboBox {
    background-color: #3c3c41;
    color: #d4d4d4;
    border: 1px solid #5a5a60;
    padding: 3px 8px;
    min-height: 22px;
}
QComboBox:hover {
    border: 1px solid #007acc;
}
QComboBox::drop-down {
    border: none;
    width: 18px;
}
QComboBox QAbstractItemView {
    background-color: #3c3c41;
    color: #d4d4d4;
    selection-background-color: #094771;
    border: 1px solid #6a6a6e;
}
QCheckBox {
    color: #d4d4d4;
    spacing: 6px;
}
QLabel {
    color: #d4d4d4;
    background: transparent;
}
QToolButton {
    background: transparent;
    border: 1px solid transparent;
    color: #d4d4d4;
    padding: 4px;
    min-width: 28px;
    min-height: 28px;
}
QToolButton:hover {
    background-color: #4a4a50;
    border: 1px solid #6a6a6e;
}
QToolButton:checked {
    background-color: #094771;
    border: 1px solid #007acc;
}
QToolButton:pressed {
    background-color: #094771;
}
QToolButton#tabCloseBtn {
    background: transparent;
    border: none;
    padding: 0;
    margin: 0 10px 0 4px;
    min-width: 16px;
    max-width: 16px;
    min-height: 16px;
    max-height: 16px;
}
QToolButton#tabCloseBtn:hover {
    background-color: #5a5a60;
    border: none;
    border-radius: 8px;
}
QToolButton#tabCloseBtn:pressed {
    background-color: #6a6a6e;
    border: none;
}
QPushButton {
    background-color: #0e639c;
    color: #ffffff;
    border: none;
    padding: 4px 12px;
    min-height: 24px;
}
QPushButton:hover {
    background-color: #1177bb;
}
QPushButton#transportBtn, QPushButton#playBtn {
    background-color: transparent;
    color: #c8c8c8;
    border: none;
    padding: 0;
    min-width: 36px;
    min-height: 36px;
}
QPushButton#transportBtn:hover, QPushButton#playBtn:hover {
    background-color: #4a4a50;
    border: none;
    border-radius: 22px;
}
QPushButton#transportBtn:pressed, QPushButton#playBtn:pressed {
    background-color: #094771;
    border: none;
    border-radius: 22px;
}
QPushButton#playBtn {
    min-width: 56px;
    min-height: 56px;
    border-radius: 28px;
}
QListWidget {
    background-color: #2d2d30;
    color: #d4d4d4;
    border: none;
    outline: none;
}
QListWidget::item:selected {
    background-color: #094771;
    color: #ffffff;
}
QScrollBar:vertical {
    background: #2d2d30;
    width: 10px;
    margin: 0;
    border: none;
}
QScrollBar::handle:vertical {
    background: #5a5a60;
    min-height: 24px;
    border-radius: 4px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QProgressDialog, QMessageBox {
    background-color: #3c3c41;
}
QLineEdit {
    background-color: #3c3c41;
    color: #d4d4d4;
    border: 1px solid #5a5a60;
    padding: 3px 6px;
}
QSlider#seekSlider {
    background: transparent;
    min-height: 28px;
}
QSlider#seekSlider::groove:horizontal {
    height: 6px;
    background: #3c3c3c;
    border-radius: 3px;
    margin: 0 8px;
}
QSlider#seekSlider::sub-page:horizontal {
    background: #007acc;
    border-radius: 3px;
    margin: 0 8px;
}
QSlider#seekSlider::add-page:horizontal {
    background: #3c3c3c;
    border-radius: 3px;
    margin: 0 8px;
}
QSlider#seekSlider::handle:horizontal {
    width: 16px;
    height: 16px;
    margin: -6px 0;
    background: #ffffff;
    border: 1px solid #007acc;
    border-radius: 8px;
}
QSlider#seekSlider::handle:horizontal:hover {
    background: #e8e8e8;
}
"""


def apply_vscode_theme(app) -> None:
    app.setStyle("Fusion")
    app.setStyleSheet(VSCODE_QSS)
