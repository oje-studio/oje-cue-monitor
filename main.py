import sys
import logging
import os
import platform
from datetime import datetime


def _default_log_dir() -> str:
    """Platform-appropriate log directory."""
    system = platform.system()
    if system == "Darwin":
        return os.path.expanduser("~/Library/Logs/OJECueMonitor")
    if system == "Windows":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(base, "OJECueMonitor", "Logs")
    # Linux / other
    base = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
    return os.path.join(base, "OJECueMonitor", "logs")


_log_dir = _default_log_dir()
try:
    os.makedirs(_log_dir, exist_ok=True)
    _log_path = os.path.join(_log_dir, datetime.now().strftime("session_%Y-%m-%d.log"))
    _file_handler = logging.FileHandler(_log_path, encoding="utf-8")
    _file_handler.setLevel(logging.DEBUG)
    _file_handler.setFormatter(logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(name)s: %(message)s"
    ))
    _handlers = [_file_handler]
except OSError:
    _handlers = []

# In a PyInstaller --windowed / --noconsole build, sys.stdout and sys.stderr
# are None. Attaching a StreamHandler to them causes AttributeError on the
# first log call. Only add the console handler when a real stream exists.
if sys.stderr is not None:
    _console_handler = logging.StreamHandler()
    _console_handler.setLevel(logging.INFO)
    _console_handler.setFormatter(logging.Formatter(
        "%(asctime)s  %(levelname)s  %(name)s: %(message)s"
    ))
    _handlers.append(_console_handler)

logging.basicConfig(level=logging.DEBUG, handlers=_handlers)

APP_NAME  = "ØJE CUE MONITOR"
VERSION   = "0.97beta"
COPYRIGHT = "© 2026 ØJE Studio"


def main():
    from PyQt6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    app.setApplicationName("OJE Cue Monitor")
    app.setApplicationVersion(VERSION)
    app.setOrganizationName("OJE Studio")

    app.setStyle("Fusion")

    from ui.main_window import make_dark_palette
    app.setPalette(make_dark_palette())

    app.setStyleSheet("""
        QToolTip {
            color: #dcdcdc;
            background-color: #2a2a2a;
            border: 1px solid #555;
            padding: 3px;
        }
        QComboBox {
            background: #2a2a2a;
            color: #dcdcdc;
            border: 1px solid #505050;
            border-radius: 3px;
            padding: 2px 8px;
        }
        QComboBox QAbstractItemView {
            background: #2a2a2a;
            color: #dcdcdc;
            selection-background-color: #3a72c0;
        }
        QPushButton {
            background: #383838;
            color: #dcdcdc;
            border: 1px solid #505050;
            border-radius: 4px;
            padding: 2px 10px;
        }
        QPushButton:hover  { background: #464646; }
        QPushButton:pressed { background: #2e2e2e; }
        QTableWidget {
            background: #242424;
            gridline-color: #383838;
            color: #dcdcdc;
            border: none;
        }
        QHeaderView::section {
            background: #1c1c1c;
            color: #909090;
            border: none;
            border-right: 1px solid #383838;
            border-bottom: 1px solid #383838;
            padding: 4px 8px;
            font-size: 11px;
            font-weight: bold;
            letter-spacing: 1px;
        }
        QScrollBar:vertical {
            background: #1c1c1c;
            width: 10px;
            border: none;
        }
        QScrollBar::handle:vertical {
            background: #505050;
            border-radius: 4px;
            min-height: 20px;
        }
        QScrollBar::handle:vertical:hover { background: #686868; }
        QScrollBar::add-line:vertical,
        QScrollBar::sub-line:vertical { height: 0px; }
        QDialog {
            background: #262626;
        }
        QMessageBox {
            background: #262626;
        }
    """)

    from ui.main_window import MainWindow
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
