"""
Entry point. Run with:  python -m show_monitor.main
"""
from __future__ import annotations

import logging
import os
import sys

from PyQt6.QtGui import QColor, QIcon, QPalette
from PyQt6.QtWidgets import QApplication


def _apply_dark_palette(app: QApplication):
    """Match the CUE MONITOR's dark palette so both apps feel identical."""
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window,          QColor(28, 28, 28))
    p.setColor(QPalette.ColorRole.WindowText,      QColor(218, 218, 218))
    p.setColor(QPalette.ColorRole.Base,            QColor(35, 35, 35))
    p.setColor(QPalette.ColorRole.AlternateBase,   QColor(42, 42, 42))
    p.setColor(QPalette.ColorRole.ToolTipBase,     QColor(42, 42, 42))
    p.setColor(QPalette.ColorRole.ToolTipText,     QColor(218, 218, 218))
    p.setColor(QPalette.ColorRole.Text,            QColor(218, 218, 218))
    p.setColor(QPalette.ColorRole.Button,          QColor(42, 42, 42))
    p.setColor(QPalette.ColorRole.ButtonText,      QColor(218, 218, 218))
    p.setColor(QPalette.ColorRole.BrightText,      QColor(255, 90, 90))
    p.setColor(QPalette.ColorRole.Highlight,       QColor(55, 115, 195))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    p.setColor(QPalette.ColorRole.Mid,             QColor(58, 58, 58))
    p.setColor(QPalette.ColorRole.Dark,            QColor(18, 18, 18))
    app.setPalette(p)

from . import APP_NAME, VERSION


def _log_path() -> str:
    if sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Logs/OJEShowMonitor")
    elif sys.platform.startswith("win"):
        base = os.path.join(
            os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
            "OJEShowMonitor", "Logs",
        )
    else:
        base = os.path.expanduser("~/.local/share/OJEShowMonitor/logs")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "show_monitor.log")


def _setup_logging():
    fmt = "%(asctime)s  %(levelname)-5s  %(name)s: %(message)s"
    logging.basicConfig(
        level=logging.INFO, format=fmt,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(_log_path(), encoding="utf-8"),
        ],
    )


def main() -> int:
    _setup_logging()
    log = logging.getLogger(__name__)
    log.info("%s %s starting", APP_NAME, VERSION)

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(VERSION)
    _apply_dark_palette(app)

    # App icon (shared with the classic CUE MONITOR for now)
    # Try platform-specific icon, fall back to PNG.
    here = os.path.dirname(os.path.abspath(__file__))
    for name in ("icon.icns", "icon.ico", "icon_1024.png"):
        candidate = os.path.join(here, "..", "assets", name)
        if os.path.exists(candidate):
            app.setWindowIcon(QIcon(candidate))
            break

    from .ui.main_window import MainWindow
    w = MainWindow()
    w.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
