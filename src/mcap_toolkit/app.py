"""QApplication entry. Keep wiring thin; UI lives in ui/."""

from __future__ import annotations

import sys
import traceback

from PyQt6.QtCore import QLocale
from PyQt6.QtWidgets import QApplication, QMessageBox

from mcap_toolkit.layout.theme import apply_vscode_theme
from mcap_toolkit.ui.main_window import MainWindow


def _excepthook(exc_type, exc, tb) -> None:
    text = "".join(traceback.format_exception(exc_type, exc, tb))
    sys.stderr.write(text)
    try:
        QMessageBox.critical(None, "Error", text[-2500:] or str(exc))
    except Exception:
        pass


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    sys.excepthook = _excepthook
    QLocale.setDefault(QLocale(QLocale.Language.English))
    app = QApplication(argv)
    app.setOrganizationName("CLC")
    app.setApplicationName("mcap_toolkit")
    app.setApplicationDisplayName("MCAP Toolkit")
    apply_vscode_theme(app)
    win = MainWindow()
    win.show()
    for arg in argv[1:]:
        if arg.lower().endswith(".mcap"):
            win.open_path(arg)
            break
    return app.exec()
