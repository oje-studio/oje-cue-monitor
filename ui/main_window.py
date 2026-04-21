from __future__ import annotations
from typing import Optional

import logging
import os
import queue
from datetime import datetime

from PyQt6.QtCore import Qt, QTimer, QSettings
from PyQt6.QtGui import (
    QColor, QFont, QPalette, QKeySequence, QShortcut,
    QPainter, QBrush, QPixmap,
)
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QFileDialog, QMessageBox,
    QFrame, QStackedWidget, QDialog,
)

from cue_engine import CueEngine, CueParseError
from ltc_decoder import LTCDecoder, LTCLibError
from show_file import ShowFile, ShowSettings
from ui.cue_table import CueTable, CueEditToolbar, OperatorEditPanel
from ui.performance_view import PerformanceView
from ui.settings_dialog import SettingsDialog
from ui.remote_panel import RemotePanel
from web_remote import WebRemoteServer

logger = logging.getLogger(__name__)

APP_NAME  = "ØJE CUE MONITOR"
VERSION   = "v0.96β"
COPYRIGHT = "© 2026 ØJE Studio"

# ── palette ───────────────────────────────────────────────────────────────────
DARK_BG      = QColor(28, 28, 28)
DARK_PANEL   = QColor(42, 42, 42)
DARK_BORDER  = QColor(58, 58, 58)
TEXT_BRIGHT  = QColor(218, 218, 218)
TEXT_DIM     = QColor(135, 135, 135)
ACCENT_GREEN  = QColor(75, 195, 115)
ACCENT_RED    = QColor(215, 75, 75)
ACCENT_YELLOW = QColor(225, 195, 55)
ACCENT_ORANGE = QColor(225, 135, 48)
NEAR_BLACK    = QColor(18, 18, 18)


def make_dark_palette() -> QPalette:
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window,          DARK_BG)
    p.setColor(QPalette.ColorRole.WindowText,      TEXT_BRIGHT)
    p.setColor(QPalette.ColorRole.Base,            QColor(35, 35, 35))
    p.setColor(QPalette.ColorRole.AlternateBase,   DARK_PANEL)
    p.setColor(QPalette.ColorRole.ToolTipBase,     DARK_PANEL)
    p.setColor(QPalette.ColorRole.ToolTipText,     TEXT_BRIGHT)
    p.setColor(QPalette.ColorRole.Text,            TEXT_BRIGHT)
    p.setColor(QPalette.ColorRole.Button,          DARK_PANEL)
    p.setColor(QPalette.ColorRole.ButtonText,      TEXT_BRIGHT)
    p.setColor(QPalette.ColorRole.BrightText,      QColor(255, 90, 90))
    p.setColor(QPalette.ColorRole.Highlight,       QColor(55, 115, 195))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    p.setColor(QPalette.ColorRole.Mid,             DARK_BORDER)
    p.setColor(QPalette.ColorRole.Dark,            QColor(18, 18, 18))
    return p


# ── VU meter ─────────────────────────────────────────────────────────────────

class VUMeter(QWidget):
    BARS = 5

    def __init__(self, parent=None):
        super().__init__(parent)
        self._db = -120.0
        self.setFixedSize(62, 20)

    def set_db(self, db: float):
        self._db = db
        self.update()

    def paintEvent(self, _):
        painter = QPainter(self)
        W, H  = self.width(), self.height()
        bw    = (W - (self.BARS - 1) * 2) // self.BARS
        norm  = max(0.0, min(1.0, (self._db + 60.0) / 60.0))
        lit   = int(norm * self.BARS)
        for i in range(self.BARS):
            x = i * (bw + 2)
            if i >= self.BARS - 1:
                c = ACCENT_RED if i < lit else QColor(60, 20, 20)
            elif i >= self.BARS - 2:
                c = ACCENT_ORANGE if i < lit else QColor(55, 40, 15)
            else:
                c = ACCENT_GREEN if i < lit else QColor(25, 55, 35)
            painter.fillRect(x, 2, bw, H - 4, c)
        painter.end()


# ── Cue card ─────────────────────────────────────────────────────────────────

class CueCard(QFrame):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.Box)
        self.setStyleSheet(
            f"CueCard {{ background: {DARK_PANEL.name()}; "
            f"border: 1px solid {DARK_BORDER.name()}; border-radius: 6px; }}"
        )
        self._countdown_enabled = True
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(4)

        tl = QLabel(title.upper())
        tl.setStyleSheet(
            f"color: {TEXT_DIM.name()}; font-size: 11px; font-weight: bold; letter-spacing: 1px;"
        )
        lay.addWidget(tl)

        self.name_lbl = QLabel("—")
        fn = QFont(); fn.setPointSize(20); fn.setBold(True)
        self.name_lbl.setFont(fn)
        self.name_lbl.setWordWrap(True)
        self.name_lbl.setStyleSheet(f"color: {TEXT_BRIGHT.name()};")
        lay.addWidget(self.name_lbl)

        self.desc_lbl = QLabel("")
        self.desc_lbl.setStyleSheet(f"color: {TEXT_DIM.name()}; font-size: 13px;")
        self.desc_lbl.setWordWrap(True)
        lay.addWidget(self.desc_lbl)

        self.ops_lbl = QLabel("")
        self.ops_lbl.setStyleSheet(
            f"color: {ACCENT_YELLOW.name()}; font-size: 12px;"
        )
        self.ops_lbl.setWordWrap(True)
        lay.addWidget(self.ops_lbl)

        self.cd_lbl = QLabel("")
        fcd = QFont("Menlo"); fcd.setPointSize(16)
        self.cd_lbl.setFont(fcd)
        self.cd_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        lay.addWidget(self.cd_lbl)

        lay.addStretch()

    def set_countdown_enabled(self, enabled: bool):
        self._countdown_enabled = enabled

    def set_cue(self, cue, countdown: float = None):
        if cue is None:
            self.name_lbl.setText("—")
            self.desc_lbl.setText("")
            self.ops_lbl.setText("")
            self.cd_lbl.setText("")
            return
        self.name_lbl.setText(cue.name or "—")
        self.desc_lbl.setText(cue.description)
        # Show operator comments vertically (one per line)
        ops_text = ""
        if cue.operator_comments:
            lines = [f"{k}: {v}" for k, v in cue.operator_comments.items() if v]
            ops_text = "\n".join(lines)
        self.ops_lbl.setText(ops_text)
        if countdown is not None and self._countdown_enabled:
            m, s  = divmod(int(countdown), 60)
            color = ACCENT_RED.name() if countdown < 10 else TEXT_BRIGHT.name()
            self.cd_lbl.setText(f"in {m:02d}:{s:02d}")
            self.cd_lbl.setStyleSheet(f"color: {color}; font-size: 16px;")
        else:
            self.cd_lbl.setText("")


# ── Main Window ───────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):

    PAGE_NORMAL = 0
    PAGE_PERF   = 1

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME}  {VERSION}")
        self.setMinimumSize(900, 640)

        self._qsettings       = QSettings("OJEStudio", "OJECueMonitor")
        self._engine          = CueEngine(fps=25.0)
        self._show: Optional[ShowFile] = None
        self._show_settings   = ShowSettings()
        self._decoder: Optional[LTCDecoder] = None
        self._running         = False
        self._current_frames  = 0
        self._last_tc         = (0, 0, 0, 0)
        self._last_fps        = 25.0
        self._signal_ok       = False
        self._blink_state     = False
        self._edit_mode       = False
        self._logo_pixmap: Optional[QPixmap] = None
        self._log_file        = None
        self._audio_devices: list = []
        self._web_remote: Optional[WebRemoteServer] = None

        self._init_log()
        self._scan_audio_devices()
        self._build_ui()
        self._setup_shortcuts()
        self._restore_state()

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(40)
        self._poll_timer.timeout.connect(self._poll_decoder)

        self._blink_timer = QTimer(self)
        self._blink_timer.setInterval(500)
        self._blink_timer.timeout.connect(self._do_blink)

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        self._stack = QStackedWidget()
        self.setCentralWidget(self._stack)

        normal = QWidget()
        self._stack.addWidget(normal)
        self._build_normal_page(normal)

        self._perf_view = PerformanceView()
        self._stack.addWidget(self._perf_view)

        self._stack.setCurrentIndex(self.PAGE_NORMAL)

    def _build_normal_page(self, parent: QWidget):
        root = QVBoxLayout(parent)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header ────────────────────────────────────────────────────────────
        header = QWidget()
        header.setFixedHeight(52)
        header.setStyleSheet(f"background: {NEAR_BLACK.name()};")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(14, 0, 14, 0)
        hl.setSpacing(10)

        app_lbl = QLabel(APP_NAME)
        fapp = QFont("Helvetica Neue"); fapp.setPointSize(15); fapp.setBold(True)
        app_lbl.setFont(fapp)
        app_lbl.setStyleSheet(f"color: {TEXT_BRIGHT.name()}; letter-spacing: 1px;")
        hl.addWidget(app_lbl)

        ver_lbl = QLabel(VERSION)
        ver_lbl.setStyleSheet(f"color: {TEXT_DIM.name()}; font-size: 11px;")
        hl.addWidget(ver_lbl)

        hl.addWidget(_vline())

        self._signal_dot = QLabel("●")
        self._signal_dot.setStyleSheet(f"color: {ACCENT_RED.name()}; font-size: 16px;")
        hl.addWidget(self._signal_dot)

        tc_font = QFont("Menlo"); tc_font.setPointSize(22); tc_font.setBold(True)
        self._tc_label = QLabel("--:--:--:--")
        self._tc_label.setFont(tc_font)
        self._tc_label.setStyleSheet(f"color: {TEXT_BRIGHT.name()}; letter-spacing: 2px;")
        hl.addWidget(self._tc_label)

        self._fps_label = QLabel("FPS: —")
        self._fps_label.setStyleSheet(f"color: {TEXT_DIM.name()}; font-size: 12px;")
        hl.addWidget(self._fps_label)

        self._vu = VUMeter()
        hl.addWidget(self._vu)

        self._signal_warn = QLabel("")
        self._signal_warn.setStyleSheet(f"color: {ACCENT_ORANGE.name()}; font-size: 11px;")
        hl.addWidget(self._signal_warn)

        hl.addStretch()

        # Real time clock
        self._clock_label = QLabel("")
        self._clock_label.setStyleSheet(f"color: {TEXT_DIM.name()}; font-size: 12px;")
        hl.addWidget(self._clock_label)

        hl.addWidget(_vline())

        self._live_label = QLabel("● LIVE")
        self._live_label.setStyleSheet(
            f"color: {ACCENT_GREEN.name()}; font-size: 12px; font-weight: bold;"
        )
        self._live_label.setVisible(False)
        hl.addWidget(self._live_label)

        # Logo in header
        self._header_logo = QLabel()
        self._header_logo.setVisible(False)
        hl.addWidget(self._header_logo)

        root.addWidget(header)
        root.addWidget(_hline())

        # ── Cue cards ─────────────────────────────────────────────────────────
        cards_w = QWidget()
        cards_w.setStyleSheet(f"background: {DARK_BG.name()};")
        cl = QHBoxLayout(cards_w)
        cl.setContentsMargins(16, 12, 16, 12)
        cl.setSpacing(16)
        self._current_card = CueCard("Current Cue")
        self._next_card    = CueCard("Next Cue")
        cl.addWidget(self._current_card)
        cl.addWidget(self._next_card)
        root.addWidget(cards_w)
        root.addWidget(_hline())

        # ── Cue table + edit toolbar ──────────────────────────────────────────
        self._table = CueTable()
        self._table.cue_data_changed.connect(self._on_cue_edit)
        self._table.row_add_requested.connect(self._on_row_add)
        self._table.row_delete_requested.connect(self._on_row_delete)
        self._table.rows_delete_requested.connect(self._on_rows_delete)
        self._table.row_move_requested.connect(self._on_row_move)
        self._table.divider_add_requested.connect(self._on_divider_add)
        self._table.cue_selected.connect(self._on_cue_selected)

        self._edit_toolbar = CueEditToolbar(self._table)
        self._edit_toolbar.setVisible(False)

        # Operator edit panel (below table, visible in edit mode)
        self._op_panel = OperatorEditPanel()
        self._op_panel.operator_changed.connect(self._on_operator_changed)
        self._op_panel.setVisible(False)

        root.addWidget(self._edit_toolbar)
        root.addWidget(self._table, stretch=1)
        root.addWidget(self._op_panel)
        root.addWidget(_hline())

        # ── Footer ────────────────────────────────────────────────────────────
        footer = QWidget()
        footer.setFixedHeight(48)
        footer.setStyleSheet(f"background: {NEAR_BLACK.name()};")
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(12, 0, 12, 0)
        fl.setSpacing(8)

        self._btn_new = QPushButton("New")
        self._btn_new.setFixedHeight(30)
        self._btn_new.setToolTip("Create a new empty show")
        self._btn_new.clicked.connect(self._new_show)
        fl.addWidget(self._btn_new)

        self._btn_open = QPushButton("Open")
        self._btn_open.setFixedHeight(30)
        self._btn_open.setToolTip("Open show file (.ojeshow) or import CSV")
        self._btn_open.clicked.connect(self._open_show)
        fl.addWidget(self._btn_open)

        self._btn_save = QPushButton("Save")
        self._btn_save.setFixedHeight(30)
        self._btn_save.setToolTip("Save show file (.ojeshow)  [Cmd+S]")
        self._btn_save.clicked.connect(self._save_show)
        fl.addWidget(self._btn_save)

        self._btn_save_as = QPushButton("Save As...")
        self._btn_save_as.setFixedHeight(30)
        self._btn_save_as.setToolTip("Save to a new file")
        self._btn_save_as.clicked.connect(self._save_show_as)
        fl.addWidget(self._btn_save_as)

        fl.addWidget(_vline())

        self._btn_edit = QPushButton("Edit Cues")
        self._btn_edit.setFixedHeight(30)
        self._btn_edit.setCheckable(True)
        self._btn_edit.clicked.connect(self._toggle_edit_mode)
        fl.addWidget(self._btn_edit)

        self._btn_settings = QPushButton("Settings")
        self._btn_settings.setFixedHeight(30)
        self._btn_settings.clicked.connect(self._open_settings)
        fl.addWidget(self._btn_settings)

        self._btn_remote = QPushButton("Remote")
        self._btn_remote.setFixedHeight(30)
        self._btn_remote.setToolTip("Start/stop web remote for other devices")
        self._btn_remote.setCheckable(True)
        self._btn_remote.clicked.connect(self._toggle_remote)
        fl.addWidget(self._btn_remote)

        fl.addStretch()

        self._btn_help = QPushButton("?")
        self._btn_help.setFixedSize(28, 28)
        self._btn_help.setToolTip("Help & Keyboard Shortcuts  [F1]")
        self._btn_help.clicked.connect(self._show_help)
        fl.addWidget(self._btn_help)

        cr_lbl = QLabel(f"{COPYRIGHT}  {VERSION}")
        cr_lbl.setStyleSheet(f"color: {QColor(55,55,55).name()}; font-size: 10px;")
        fl.addWidget(cr_lbl)

        fl.addWidget(_vline())

        self._btn_perf = QPushButton("Performance Mode")
        self._btn_perf.setFixedHeight(30)
        self._btn_perf.setFixedWidth(160)
        self._btn_perf.setStyleSheet(_perf_btn_style())
        self._btn_perf.clicked.connect(self._enter_perf_mode)
        fl.addWidget(self._btn_perf)

        self._btn_start = QPushButton("START")
        self._btn_start.setFixedHeight(30)
        self._btn_start.setFixedWidth(72)
        self._btn_start.setStyleSheet(_start_btn_style())
        self._btn_start.clicked.connect(self._toggle_start)
        fl.addWidget(self._btn_start)

        root.addWidget(footer)

        # Clock update timer
        self._clock_timer = QTimer(self)
        self._clock_timer.setInterval(1000)
        self._clock_timer.timeout.connect(self._update_clock)
        self._clock_timer.start()
        self._update_clock()

    # ── shortcuts ─────────────────────────────────────────────────────────────

    def _setup_shortcuts(self):
        QShortcut(QKeySequence("Space"),  self).activated.connect(self._mark_cue)
        QShortcut(QKeySequence("P"),      self).activated.connect(self._toggle_perf_mode)
        QShortcut(QKeySequence("Escape"), self).activated.connect(self._exit_perf_mode)
        QShortcut(QKeySequence("F1"),     self).activated.connect(self._show_help)
        QShortcut(QKeySequence.StandardKey.Save, self).activated.connect(self._save_show)
        QShortcut(QKeySequence.StandardKey.New,  self).activated.connect(self._new_show)
        QShortcut(QKeySequence.StandardKey.Open, self).activated.connect(self._open_show)

    # ── state ─────────────────────────────────────────────────────────────────

    def _restore_state(self):
        geom = self._qsettings.value("geometry")
        if geom:
            self.restoreGeometry(geom)
        last_show = self._qsettings.value("last_show", "")
        if last_show and os.path.exists(last_show):
            self._load_show_file(last_show)
        else:
            # Try legacy CSV
            last_csv = self._qsettings.value("last_csv", "")
            if last_csv and os.path.exists(last_csv):
                self._import_csv(last_csv)

    def _scan_audio_devices(self):
        self._audio_devices = []
        try:
            import pyaudio
            pa = pyaudio.PyAudio()
            for i in range(pa.get_device_count()):
                info = pa.get_device_info_by_index(i)
                if info.get("maxInputChannels", 0) > 0:
                    self._audio_devices.append({
                        "index": i,
                        "name": info["name"],
                        "channels": int(info["maxInputChannels"]),
                    })
            pa.terminate()
        except Exception as e:
            logger.error("Failed to scan audio devices: %s", e)

    def _update_clock(self):
        self._clock_label.setText(datetime.now().strftime("%H:%M:%S"))

    # ── Show file operations ──────────────────────────────────────────────────

    def _new_show(self):
        if self._engine.cues:
            reply = QMessageBox.question(
                self, "New Show",
                "Save current show before creating a new one?",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No
                | QMessageBox.StandardButton.Cancel,
            )
            if reply == QMessageBox.StandardButton.Cancel:
                return
            if reply == QMessageBox.StandardButton.Yes:
                self._save_show()

        self._show = ShowFile()
        self._show_settings = ShowSettings()
        self._engine.cues.clear()
        self._table.load_cues(self._engine.cues)
        self._apply_settings(self._show_settings)
        self.setWindowTitle(f"{APP_NAME}  {VERSION}  —  New Show")
        logger.info("New show created")

    def _open_show(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Show File", "",
            "Show Files (*.ojeshow);;CSV Files (*.csv);;All Files (*)"
        )
        if not path:
            return
        if path.lower().endswith(".csv"):
            self._import_csv(path)
        else:
            self._load_show_file(path)

    def _load_show_file(self, path: str):
        try:
            self._show = ShowFile.load(path)
            self._show_settings = self._show.settings
            self._engine.load_show_cues(self._show.cues)
            self._table.load_cues(self._engine.cues)
            self._apply_settings(self._show_settings)
            self.setWindowTitle(f"{APP_NAME}  {VERSION}  —  {os.path.basename(path)}")
            self._qsettings.setValue("last_show", path)
        except (OSError, ValueError) as e:
            QMessageBox.critical(self, "Load Error", str(e))

    def _import_csv(self, path: str):
        try:
            self._show = ShowFile.from_csv(path)
            self._show_settings = self._show.settings
            self._engine.load_show_cues(self._show.cues)
            self._table.load_cues(self._engine.cues)
            self._apply_settings(self._show_settings)
            self.setWindowTitle(f"{APP_NAME}  {VERSION}  —  {os.path.basename(path)} (imported)")
        except (OSError, CueParseError) as e:
            QMessageBox.critical(self, "Import Error", str(e))

    def _save_show(self):
        logger.info("Save requested")
        if self._show is None:
            self._show = ShowFile()
        # Sync engine cues back
        self._show.cues = self._engine.to_show_cues()
        self._show.settings = self._show_settings

        path = self._show.file_path
        if not path or not path.endswith(".ojeshow"):
            path, _ = QFileDialog.getSaveFileName(
                self, "Save Show File", "",
                "Show Files (*.ojeshow);;All Files (*)"
            )
        if not path:
            logger.info("Save cancelled by user")
            return
        if not path.endswith(".ojeshow"):
            path += ".ojeshow"
        try:
            self._show.save(path)
            self._qsettings.setValue("last_show", path)
            self.setWindowTitle(f"{APP_NAME}  {VERSION}  —  {os.path.basename(path)}")
            self._flash_save_ok()
            logger.info("Saved to %s", path)
        except OSError as e:
            logger.error("Save failed: %s", e)
            QMessageBox.critical(self, "Save Error", str(e))

    def _flash_save_ok(self):
        self._btn_save.setText("Saved!")
        self._btn_save.setStyleSheet(
            f"QPushButton {{ background: {QColor(48,125,75).name()}; "
            f"color: white; border-radius: 4px; }}"
        )
        QTimer.singleShot(1500, self._reset_save_btn)

    def _reset_save_btn(self):
        self._btn_save.setText("Save")
        self._btn_save.setStyleSheet("")

    def _save_show_as(self):
        if self._show is None:
            self._show = ShowFile()
        self._show.cues = self._engine.to_show_cues()
        self._show.settings = self._show_settings
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Show File As", "",
            "Show Files (*.ojeshow);;All Files (*)"
        )
        if not path:
            return
        if not path.endswith(".ojeshow"):
            path += ".ojeshow"
        try:
            self._show.save(path)
            self._qsettings.setValue("last_show", path)
            self.setWindowTitle(f"{APP_NAME}  {VERSION}  —  {os.path.basename(path)}")
            logger.info("Saved as %s", path)
        except OSError as e:
            QMessageBox.critical(self, "Save Error", str(e))

    # ── Settings ──────────────────────────────────────────────────────────────

    def _open_settings(self):
        dlg = SettingsDialog(self._show_settings, self._audio_devices, self)
        if dlg.exec():
            new_settings = dlg.get_settings()
            if new_settings:
                self._show_settings = new_settings
                self._apply_settings(new_settings)

    def _apply_settings(self, settings: ShowSettings):
        # Logo
        if settings.logo_path and os.path.exists(settings.logo_path):
            self._apply_logo(settings.logo_path)
        elif not settings.logo_path:
            self._header_logo.setVisible(False)
            self._perf_view.set_logo(None)

        # Countdown toggle
        self._current_card.set_countdown_enabled(settings.countdown_enabled)
        self._next_card.set_countdown_enabled(settings.countdown_enabled)

        # Performance view
        self._perf_view.apply_settings(settings)

        # Operator edit panel
        self._op_panel.set_operators(settings.operator_names)

    # ── Web Remote ─────────────────────────────────────────────────────────────

    def _toggle_remote(self, checked: bool):
        if checked:
            self._start_remote()
        else:
            self._stop_remote()

    def _start_remote(self):
        if self._web_remote and self._web_remote._running:
            self._show_remote_panel()
            return
        self._web_remote = WebRemoteServer(port=8080)
        self._web_remote.set_operators(self._show_settings.operator_names)
        self._web_remote.start()
        self._btn_remote.setText("Remote ON")
        self._btn_remote.setStyleSheet(
            f"QPushButton {{ background: {QColor(48,100,160).name()}; "
            f"color: white; border-radius: 4px; }}"
        )
        logger.info("Web remote started: %s", self._web_remote.base_url)
        self._show_remote_panel()

    def _stop_remote(self):
        if self._web_remote:
            self._web_remote.stop()
            self._web_remote = None
        self._btn_remote.setText("Remote")
        self._btn_remote.setStyleSheet("")
        logger.info("Web remote stopped")

    def _show_remote_panel(self):
        port = self._web_remote.port if self._web_remote else 8080
        dlg = RemotePanel(port, self._show_settings.operator_names, self)
        dlg.exec()

    # ── Logo ─────────────────────────────────────────────────────────────────

    def _apply_logo(self, path: str):
        pix = QPixmap(path)
        if pix.isNull():
            return
        self._logo_pixmap = pix
        header_pix = pix.scaledToHeight(36, Qt.TransformationMode.SmoothTransformation)
        self._header_logo.setPixmap(header_pix)
        self._header_logo.setVisible(True)
        self._perf_view.set_logo(pix)

    # ── edit mode ─────────────────────────────────────────────────────────────

    def _toggle_edit_mode(self, checked: bool):
        self._edit_mode = checked
        self._table.set_edit_mode(checked)
        self._edit_toolbar.setVisible(checked)
        if checked:
            self._btn_edit.setText("Done")
            self._btn_edit.setStyleSheet(
                f"QPushButton {{ background: {QColor(52,120,52).name()}; "
                f"color: white; border-radius: 4px; }}"
            )
            # Show operator panel if operators are defined
            if self._show_settings.operator_names:
                self._op_panel.setVisible(True)
        else:
            self._btn_edit.setText("Edit Cues")
            self._btn_edit.setStyleSheet("")
            self._op_panel.hide_panel()
            self._save_show()

    def _on_cue_selected(self, row: int):
        if 0 <= row < len(self._engine.cues):
            cue = self._engine.cues[row]
            if not cue.is_divider:
                self._op_panel.show_for_cue(row, cue)

    def _on_operator_changed(self, row: int, op_name: str, comment: str):
        self._engine.update_operator_comment(row, op_name, comment)
        # Refresh table row to show updated summary
        self._table.load_cues(self._engine.cues)
        self._table.set_edit_mode(True)

    def _on_cue_edit(self, row: int, field: str, value: str):
        self._engine.update_cue_field(row, field, value)
        if field == "timecode":
            self._table.load_cues(self._engine.cues)
            self._table.set_edit_mode(True)
        else:
            self._table.refresh_index_column(self._engine.cues)

    def _on_row_add(self, after_row: int):
        self._engine.add_cue(after_index_0=after_row)
        self._table.load_cues(self._engine.cues)
        self._table.set_edit_mode(True)
        new_row = min(after_row + 1, len(self._engine.cues) - 1)
        self._table.setCurrentCell(new_row, 3)

    def _on_row_delete(self, row: int):
        if row < 0 or row >= len(self._engine.cues):
            return
        name = self._engine.cues[row].name or f"row {row + 1}"
        reply = QMessageBox.question(
            self, "Delete Cue",
            f"Delete  «{name}»?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._engine.remove_cue(row)
            self._table.load_cues(self._engine.cues)
            self._table.set_edit_mode(True)

    def _on_rows_delete(self, rows: list):
        if not rows:
            return
        reply = QMessageBox.question(
            self, "Delete Cues",
            f"Delete {len(rows)} selected cue(s)?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._engine.remove_cues(rows)
            self._table.load_cues(self._engine.cues)
            self._table.set_edit_mode(True)

    def _on_divider_add(self, after_row: int):
        self._engine.add_cue(after_index_0=after_row, is_divider=True)
        self._table.load_cues(self._engine.cues)
        self._table.set_edit_mode(True)
        new_row = min(after_row + 1, len(self._engine.cues) - 1)
        self._table.setCurrentCell(new_row, 3)

    def _on_row_move(self, from_row: int, to_row: int):
        self._engine.move_cue(from_row, to_row)
        self._table.load_cues(self._engine.cues)
        self._table.set_edit_mode(True)
        self._table.setCurrentCell(to_row, self._table.currentColumn())

    # ── decoder ───────────────────────────────────────────────────────────────

    def _toggle_start(self):
        if self._running:
            self._stop_decoder()
        else:
            self._start_decoder()

    def _start_decoder(self):
        # Find device index by name from settings
        device_index = None
        dev_name = self._show_settings.audio_device_name
        if dev_name:
            for dev in self._audio_devices:
                if dev["name"] == dev_name:
                    device_index = dev["index"]
                    break
        channel_index = self._show_settings.audio_channel

        logger.info("Starting decoder  device=%s  channel=%d", device_index, channel_index)
        self._decoder = LTCDecoder(device_index=device_index, channel_index=channel_index)
        self._decoder.start()
        self._running = True
        self._poll_timer.start()
        self._btn_start.setText("STOP")
        self._btn_start.setStyleSheet(_stop_btn_style())
        self._live_label.setVisible(True)

    def _stop_decoder(self):
        if self._decoder:
            self._decoder.stop()
            self._decoder = None
        self._running = False
        self._poll_timer.stop()
        self._blink_timer.stop()
        self._btn_start.setText("START")
        self._btn_start.setStyleSheet(_start_btn_style())
        self._live_label.setVisible(False)
        self._signal_ok = False
        self._refresh_signal_dot()

    # ── decoder polling ───────────────────────────────────────────────────────

    def _poll_decoder(self):
        if not self._decoder:
            return
        try:
            while True:
                self._handle_msg(self._decoder.out_queue.get_nowait())
        except queue.Empty:
            pass

    def _handle_msg(self, msg):
        kind = msg[0]

        if kind == "timecode":
            _, h, m, s, f, fps = msg
            self._last_tc        = (h, m, s, f)
            self._last_fps       = fps
            self._engine.fps     = fps
            self._current_frames = self._engine.tc_to_frames(h, m, s, f)
            tc_str = f"{h:02d}:{m:02d}:{s:02d}:{f:02d}"
            self._tc_label.setText(tc_str)
            self._fps_label.setText(f"FPS: {fps:.2f}")
            self._signal_ok = True
            self._blink_timer.stop()
            self._refresh_signal_dot()
            self._update_cues(tc_str)
            self._log(f"TC {tc_str}  fps={fps:.2f}")

        elif kind == "signal_lost":
            self._signal_ok = False
            h, m, s, f = self._last_tc
            self._tc_label.setText(f"{h:02d}:{m:02d}:{s:02d}:{f:02d}  [NO SIGNAL]")
            self._blink_timer.start()
            self._log("SIGNAL LOST")

        elif kind == "level":
            db = msg[1]
            self._vu.set_db(db)
            if db < -40:
                self._signal_warn.setText("Weak signal")
            elif db > -3:
                self._signal_warn.setText("Clipping!")
            else:
                self._signal_warn.setText("")

        elif kind == "error":
            self._stop_decoder()
            self._show_error(msg[1])

    def _update_cues(self, tc_str: str = "--:--:--:--"):
        current   = self._engine.get_current_cue(self._current_frames)
        nxt       = self._engine.get_next_cue(self._current_frames)
        countdown = self._engine.get_countdown(self._current_frames)

        self._current_card.set_cue(current)
        self._next_card.set_cue(nxt, countdown)

        if not self._edit_mode:
            self._table.update_highlight(self._engine.cues, current, self._current_frames)

        cur_group = self._engine.get_group_for_cue(current) if current else ""
        nxt_group = self._engine.get_group_for_cue(nxt) if nxt else ""
        self._perf_view.update_display(current, nxt, countdown, tc_str, cur_group, nxt_group)

        if self._web_remote and self._web_remote._running:
            self._web_remote.broadcast_state(
                current, nxt, countdown, tc_str, cur_group, nxt_group
            )

    def _refresh_signal_dot(self):
        color = ACCENT_GREEN.name() if self._signal_ok else ACCENT_RED.name()
        self._signal_dot.setStyleSheet(f"color: {color}; font-size: 16px;")

    def _do_blink(self):
        self._blink_state = not self._blink_state
        color = ACCENT_RED.name() if self._blink_state else QColor(75, 18, 18).name()
        self._signal_dot.setStyleSheet(f"color: {color}; font-size: 16px;")

    # ── performance mode ──────────────────────────────────────────────────────

    def _enter_perf_mode(self):
        self._stack.setCurrentIndex(self.PAGE_PERF)
        self.showFullScreen()
        h, m, s, f = self._last_tc
        tc_str    = f"{h:02d}:{m:02d}:{s:02d}:{f:02d}"
        current   = self._engine.get_current_cue(self._current_frames)
        nxt       = self._engine.get_next_cue(self._current_frames)
        countdown = self._engine.get_countdown(self._current_frames)
        cur_group = self._engine.get_group_for_cue(current) if current else ""
        nxt_group = self._engine.get_group_for_cue(nxt) if nxt else ""
        self._perf_view.update_display(current, nxt, countdown, tc_str, cur_group, nxt_group)

    def _exit_perf_mode(self):
        if self._stack.currentIndex() == self.PAGE_PERF:
            self._stack.setCurrentIndex(self.PAGE_NORMAL)
            self.showNormal()

    def _toggle_perf_mode(self):
        if self._stack.currentIndex() == self.PAGE_PERF:
            self._exit_perf_mode()
        else:
            self._enter_perf_mode()

    # ── misc ──────────────────────────────────────────────────────────────────

    def _mark_cue(self):
        self._log(f"MANUAL MARK  frames={self._current_frames}")

    def _show_error(self, msg: str):
        dlg = QDialog(self)
        dlg.setWindowTitle("Error")
        dlg.setMinimumWidth(440)
        lay = QVBoxLayout(dlg)
        lbl = QLabel(msg)
        lbl.setWordWrap(True)
        lay.addWidget(lbl)
        if "brew install" in msg:
            copy_btn = QPushButton("Copy install command")
            copy_btn.clicked.connect(
                lambda: QApplication.clipboard().setText("brew install libltc")
            )
            lay.addWidget(copy_btn)
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(dlg.accept)
        lay.addWidget(ok_btn)
        dlg.exec()

    def _init_log(self):
        log_dir = os.path.expanduser("~/Library/Logs/OJECueMonitor")
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, datetime.now().strftime("session_%Y-%m-%d.log"))
        try:
            self._log_file = open(log_path, "a", encoding="utf-8")
            self._log(f"--- {APP_NAME} {VERSION} started ---")
        except OSError:
            self._log_file = None

    def _log(self, msg: str):
        if self._log_file:
            ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            self._log_file.write(f"[{ts}]  {msg}\n")
            self._log_file.flush()

    def _show_help(self):
        dlg = QDialog(self)
        dlg.setWindowTitle(f"About {APP_NAME}")
        dlg.setMinimumWidth(520)
        dlg.setMinimumHeight(560)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(12)

        title = QLabel(f"{APP_NAME}  {VERSION}")
        ft = QFont("Helvetica Neue"); ft.setPointSize(18); ft.setBold(True)
        title.setFont(ft)
        title.setStyleSheet(f"color: {TEXT_BRIGHT.name()};")
        lay.addWidget(title)

        sub = QLabel(f"{COPYRIGHT}\nLTC Timecode Cue List Manager for Live Shows")
        sub.setStyleSheet(f"color: {TEXT_DIM.name()}; font-size: 12px;")
        lay.addWidget(sub)

        lay.addWidget(_hline())

        help_text = (
            "<h3 style='color:#dcdcdc;'>Keyboard Shortcuts</h3>"
            "<table cellpadding='4' style='color:#ccc; font-size:13px;'>"
            "<tr><td style='color:#7a7acd; font-weight:bold;'>Cmd+N</td>"
            "    <td>New show</td></tr>"
            "<tr><td style='color:#7a7acd; font-weight:bold;'>Cmd+O</td>"
            "    <td>Open show file / import CSV</td></tr>"
            "<tr><td style='color:#7a7acd; font-weight:bold;'>Cmd+S</td>"
            "    <td>Save show</td></tr>"
            "<tr><td style='color:#7a7acd; font-weight:bold;'>P</td>"
            "    <td>Toggle Performance Mode</td></tr>"
            "<tr><td style='color:#7a7acd; font-weight:bold;'>Escape</td>"
            "    <td>Exit Performance Mode</td></tr>"
            "<tr><td style='color:#7a7acd; font-weight:bold;'>Space</td>"
            "    <td>Manual cue mark (logged)</td></tr>"
            "<tr><td style='color:#7a7acd; font-weight:bold;'>F1</td>"
            "    <td>This help window</td></tr>"
            "</table>"
            "<br>"
            "<h3 style='color:#dcdcdc;'>Edit Mode</h3>"
            "<table cellpadding='4' style='color:#ccc; font-size:13px;'>"
            "<tr><td style='color:#7a7acd; font-weight:bold;'>+ Cue</td>"
            "    <td>Add cue after selection</td></tr>"
            "<tr><td style='color:#7a7acd; font-weight:bold;'>+ Section</td>"
            "    <td>Add section divider</td></tr>"
            "<tr><td style='color:#7a7acd; font-weight:bold;'>Delete</td>"
            "    <td>Delete selected rows (multi-select)</td></tr>"
            "<tr><td style='color:#7a7acd; font-weight:bold;'>Up / Down</td>"
            "    <td>Move selected cue</td></tr>"
            "</table>"
            "<br>"
            "<h3 style='color:#dcdcdc;'>Show File (.ojeshow)</h3>"
            "<p style='color:#aaa; font-size:12px;'>"
            "A single JSON file containing all settings (audio device, operators, "
            "font sizes, logo) and the complete cue list. Replaces the legacy CSV format. "
            "Auto-saved when exiting Edit Mode.</p>"
            "<br>"
            "<h3 style='color:#dcdcdc;'>LTC Timecode</h3>"
            "<p style='color:#aaa; font-size:12px;'>"
            "Connect an LTC/SMPTE timecode source to any audio input. "
            "Select the device and channel in Settings. Press START to begin reading. "
            "The VU meter shows input level — aim for -20 to -6 dBFS.</p>"
            "<br>"
            "<h3 style='color:#dcdcdc;'>Duplicate Timecodes</h3>"
            "<p style='color:#aaa; font-size:12px;'>"
            "Cues with identical timecodes are marked with a "
            "<span style='color:#e6c840;'>&#9888;</span> warning. "
            "Only the last cue in list order will be active during playback. "
            "Click a duplicate to highlight all siblings.</p>"
        )

        lbl = QLabel(help_text)
        lbl.setWordWrap(True)
        lbl.setTextFormat(Qt.TextFormat.RichText)
        lbl.setStyleSheet("background: transparent;")

        scroll = QFrame()
        sl = QVBoxLayout(scroll)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.addWidget(lbl)

        lay.addWidget(scroll, stretch=1)

        ok = QPushButton("Close")
        ok.setFixedWidth(80)
        ok.clicked.connect(dlg.accept)
        lay.addWidget(ok, alignment=Qt.AlignmentFlag.AlignRight)

        dlg.exec()

    def closeEvent(self, event):
        self._stop_decoder()
        if self._web_remote:
            self._web_remote.stop()
        self._qsettings.setValue("geometry", self.saveGeometry())
        if self._log_file:
            self._log("--- session ended ---")
            self._log_file.close()
        event.accept()


# ── helpers ───────────────────────────────────────────────────────────────────

def _hline() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    f.setStyleSheet(f"color: {DARK_BORDER.name()};")
    return f


def _vline() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.VLine)
    f.setStyleSheet(f"color: {DARK_BORDER.name()};")
    return f


def _start_btn_style() -> str:
    return (
        f"QPushButton {{ background: {QColor(48,125,75).name()}; "
        f"color: white; font-weight: bold; border-radius: 4px; }}"
        f"QPushButton:hover {{ background: {QColor(58,152,92).name()}; }}"
    )


def _stop_btn_style() -> str:
    return (
        f"QPushButton {{ background: {QColor(155,48,48).name()}; "
        f"color: white; font-weight: bold; border-radius: 4px; }}"
        f"QPushButton:hover {{ background: {ACCENT_RED.name()}; }}"
    )


def _perf_btn_style() -> str:
    return (
        f"QPushButton {{ background: {QColor(48,75,135).name()}; "
        f"color: white; font-weight: bold; border-radius: 4px; }}"
        f"QPushButton:hover {{ background: {QColor(58,92,165).name()}; }}"
    )
