"""
Entry point. Run with:  python -m show_monitor.main
"""
from __future__ import annotations

import logging
import os
import sys

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

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
