from __future__ import annotations
from typing import Optional

import html
import logging
import os
import platform
import queue
from datetime import datetime

from PyQt6.QtCore import Qt, QTimer, QSettings
from PyQt6.QtGui import (
    QColor, QFont, QPalette, QKeySequence, QShortcut, QAction,
    QPainter, QBrush, QPixmap, QTextDocument, QPageSize,
)
from PyQt6.QtPrintSupport import QPrinter
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QFileDialog, QMessageBox,
    QFrame, QStackedWidget, QDialog, QSplitter,
)

from cue_engine import CueEngine, CueParseError
from ltc_decoder import LTCDecoder, LTCLibError
from show_file import ShowFile, ShowSettings
from ui.cue_table import CueTable, CueEditToolbar, OperatorEditPanel
from ui.fonts import mono_font, sans_font
from ui.performance_view import PerformanceView
from ui.settings_dialog import SettingsDialog
from ui.remote_panel import RemotePanel
from web_remote import WebRemoteServer

logger = logging.getLogger(__name__)

APP_NAME  = "ØJE CUE MONITOR"
VERSION   = "v0.97β"
COPYRIGHT = "© 2026 ØJE Studio"
WEBSITE   = "oje.studio"
EMAIL     = "hello@oje.studio"

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
        self._operator_names: list = []
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
        self.cd_lbl.setFont(mono_font(16))
        self.cd_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        lay.addWidget(self.cd_lbl)

        lay.addStretch()

    def set_countdown_enabled(self, enabled: bool):
        self._countdown_enabled = enabled

    def set_operators(self, operator_names: list):
        self._operator_names = list(operator_names)

    def set_cue(self, cue, countdown: float = None):
        if cue is None:
            self.name_lbl.setText("—")
            self.desc_lbl.setText("")
            self.ops_lbl.setText("")
            self.cd_lbl.setText("")
            return
        self.name_lbl.setText(cue.name or "—")
        self.desc_lbl.setText(cue.description)
        # Iterate the current operator list (not cue.operator_comments keys)
        # so renamed/removed operators don't leak stale entries into the view.
        # Multi-line comments are indented on continuation lines for legibility.
        comments = cue.operator_comments or {}
        lines = [
            f"{name}: {comments[name].replace(chr(10), chr(10) + '    ')}"
            for name in self._operator_names
            if comments.get(name)
        ]
        self.ops_lbl.setText("\n".join(lines))
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
        self._base_title = f"{APP_NAME}  {VERSION}"
        self.setWindowTitle(self._base_title)
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
        self._last_db         = -120.0
        self._signal_warning_text = ""
        self._blink_state     = False
        self._edit_mode       = False
        self._logo_pixmap: Optional[QPixmap] = None
        self._log_file        = None
        self._audio_devices: list = []
        self._web_remote: Optional[WebRemoteServer] = None
        self._dirty           = False
        self._autosave_fresh  = True   # does the autosave file reflect current state?
        self._state_dir       = self._compute_state_dir()

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

        # Autosave dirty cue data every 10 seconds to the state dir (dropped
        # from 30s so crashes during a quick edit session still produce a
        # recoverable file). The backup is cleared on explicit save / new /
        # clean shutdown, so its presence at startup means the last session
        # crashed mid-edit.
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setInterval(10_000)
        self._autosave_timer.timeout.connect(self._autosave_tick)
        self._autosave_timer.start()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        self._stack = QStackedWidget()
        self.setCentralWidget(self._stack)

        normal = QWidget()
        self._stack.addWidget(normal)
        self._build_normal_page(normal)

        self._perf_view = PerformanceView()
        self._stack.addWidget(self._perf_view)
        self._perf_view.update_signal_state(False, self._last_db, self._signal_warning_text)

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
        app_lbl.setFont(sans_font(15, bold=True))
        app_lbl.setStyleSheet(f"color: {TEXT_BRIGHT.name()}; letter-spacing: 1px;")
        hl.addWidget(app_lbl)

        ver_lbl = QLabel(VERSION)
        ver_lbl.setStyleSheet(f"color: {TEXT_DIM.name()}; font-size: 11px;")
        hl.addWidget(ver_lbl)

        hl.addWidget(_vline())

        self._signal_dot = QLabel("●")
        self._signal_dot.setStyleSheet(f"color: {ACCENT_RED.name()}; font-size: 16px;")
        hl.addWidget(self._signal_dot)

        self._tc_label = QLabel("--:--:--:--")
        self._tc_label.setFont(mono_font(22, bold=True))
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

        hl.addWidget(_vline())

        # Transport controls live in the header top-right so they sit
        # where the operator's eyes already are when reading timecode.
        self._btn_perf = QPushButton("PERFORMANCE")
        self._btn_perf.setFixedHeight(30)
        self._btn_perf.setFixedWidth(130)
        self._btn_perf.setStyleSheet(_perf_btn_style())
        self._btn_perf.clicked.connect(self._enter_perf_mode)
        hl.addWidget(self._btn_perf)

        self._btn_start = QPushButton("START")
        self._btn_start.setFixedHeight(30)
        self._btn_start.setFixedWidth(72)
        self._btn_start.setStyleSheet(_start_btn_style())
        self._btn_start.clicked.connect(self._toggle_start)
        hl.addWidget(self._btn_start)

        root.addWidget(header)
        root.addWidget(_hline())

        # ── Cue cards ─────────────────────────────────────────────────────────
        cards_w = QWidget()
        cards_w.setStyleSheet(f"background: {DARK_BG.name()};")
        self._cards_w = cards_w
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

        table_area = QSplitter(Qt.Orientation.Horizontal)
        table_area.setChildrenCollapsible(False)
        table_area.setHandleWidth(1)
        table_area.addWidget(self._table)
        table_area.addWidget(self._op_panel)
        table_area.setStretchFactor(0, 5)
        table_area.setStretchFactor(1, 2)
        table_area.setSizes([980, 320])
        self._table_splitter = table_area

        root.addWidget(self._edit_toolbar)
        root.addWidget(table_area, stretch=1)
        root.addWidget(_hline())

        # ── Footer ────────────────────────────────────────────────────────────
        footer = QWidget()
        footer.setFixedHeight(48)
        footer.setStyleSheet(f"background: {NEAR_BLACK.name()};")
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(12, 0, 12, 0)
        fl.setSpacing(8)

        # File / Settings / Help live in the native menu bar (built in
        # _build_menu_bar). The footer keeps only the two actions the
        # operator toggles during a show — everything else is one-shot
        # and belongs in the menu.
        self._btn_edit = QPushButton("Edit Cues")
        self._btn_edit.setFixedHeight(30)
        self._btn_edit.setCheckable(True)
        self._btn_edit.clicked.connect(self._toggle_edit_mode)
        fl.addWidget(self._btn_edit)

        self._btn_remote = QPushButton("Remote")
        self._btn_remote.setFixedHeight(30)
        self._btn_remote.setToolTip("Start/stop web remote for other devices")
        self._btn_remote.setCheckable(True)
        self._btn_remote.clicked.connect(self._toggle_remote)
        fl.addWidget(self._btn_remote)

        fl.addStretch()

        cr_lbl = QLabel(f"{COPYRIGHT}  ·  {WEBSITE}  ·  {EMAIL}")
        cr_lbl.setStyleSheet(f"color: {QColor(75,75,75).name()}; font-size: 10px;")
        fl.addWidget(cr_lbl)

        fl.addWidget(_vline())

        # Wall clock moved down here from the header — still visible for the
        # operator tracking intermission / break times, but out of the way.
        self._clock_label = QLabel("")
        self._clock_label.setFont(mono_font(11))
        self._clock_label.setStyleSheet(f"color: {TEXT_DIM.name()};")
        fl.addWidget(self._clock_label)

        root.addWidget(footer)

        # Clock update timer
        self._clock_timer = QTimer(self)
        self._clock_timer.setInterval(1000)
        self._clock_timer.timeout.connect(self._update_clock)
        self._clock_timer.start()
        self._update_clock()

    # ── shortcuts ─────────────────────────────────────────────────────────────

    def _setup_shortcuts(self):
        # Window-wide shortcuts that aren't menu items (Space = mark
        # cue, P = toggle Performance, Escape = exit Performance).
        # Menu actions own their own accelerators (Cmd+N/O/S etc.) —
        # see _build_menu_bar — so we don't duplicate them here.
        QShortcut(QKeySequence("Space"),  self).activated.connect(self._mark_cue)
        QShortcut(QKeySequence("P"),      self).activated.connect(self._toggle_perf_mode)
        QShortcut(QKeySequence("Escape"), self).activated.connect(self._exit_perf_mode)

        self._build_menu_bar()

    # ── state ─────────────────────────────────────────────────────────────────

    def _restore_state(self):
        geom = self._qsettings.value("geometry")
        if geom:
            self.restoreGeometry(geom)

        last_show = self._qsettings.value("last_show", "")

        # Offer to recover from autosave if the previous session did not
        # shut down cleanly.
        if self._autosave_exists() and self._offer_autosave_recovery(last_show):
            return

        if last_show and os.path.exists(last_show):
            self._load_show_file(last_show)
        else:
            # Try legacy CSV
            last_csv = self._qsettings.value("last_csv", "")
            if last_csv and os.path.exists(last_csv):
                self._import_csv(last_csv)

    def _offer_autosave_recovery(self, last_show: str) -> bool:
        """Prompt the user to restore autosaved state.

        Returns True if the autosave was loaded, False if the user declined
        (in which case the autosave file has been deleted and the caller
        should proceed with normal startup).
        """
        path = self._autosave_path()
        reply = QMessageBox.question(
            self, "Restore Unsaved Changes",
            "The previous session ended before changes were saved.\n\n"
            "Restore the autosaved cue list?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            self._clear_autosave()
            return False

        try:
            self._show = ShowFile.load(path)
            # The autosave lives in the state dir — not where the user
            # thinks their show lives. Restore the previous file_path so
            # an explicit Save writes back to the original .ojeshow.
            if last_show:
                self._show.file_path = last_show
            self._show_settings = self._show.settings
            self._engine.load_show_cues(self._show.cues)
            self._table.load_cues(self._engine.cues)
            self._apply_settings(self._show_settings)
            name = os.path.basename(last_show) if last_show else "Recovered Show"
            self._set_base_title(f"{APP_NAME}  {VERSION}  —  {name}  [recovered]")
            # Keep the autosave file around until the user performs a real
            # save — the loaded state is unsaved as far as the original .ojeshow
            # is concerned, but the autosave file on disk already reflects it.
            self._dirty = True
            self._autosave_fresh = True
            logger.info("Recovered autosave from %s", path)
            return True
        except (OSError, ValueError) as e:
            logger.error("Failed to load autosave: %s", e)
            QMessageBox.warning(self, "Recovery Failed",
                                f"Could not read the autosave file:\n{e}")
            self._clear_autosave()
            return False

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

    def _confirm_discard_or_save(self, title: str, prompt: str) -> bool:
        if not self._dirty:
            return True

        reply = QMessageBox.question(
            self, title, prompt,
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Cancel:
            return False
        if reply == QMessageBox.StandardButton.Save:
            return self._save_show()
        return True

    # ── Menu bar ──────────────────────────────────────────────────────────────

    def _build_menu_bar(self):
        """
        Native menu bar — File / Settings / Help. On macOS Qt promotes
        this to the top-of-screen system menu automatically. Action
        roles tag Settings as Preferences and About as AboutRole so
        macOS files them under the app menu in the conventional
        place.
        """
        bar = self.menuBar()

        # ── File ─────────────────────────────
        m_file = bar.addMenu("&File")

        a_new = QAction("&New Show", self)
        a_new.setShortcut(QKeySequence.StandardKey.New)
        a_new.triggered.connect(self._new_show)
        m_file.addAction(a_new)

        a_open = QAction("&Open Show…", self)
        a_open.setShortcut(QKeySequence.StandardKey.Open)
        a_open.triggered.connect(self._open_show)
        m_file.addAction(a_open)

        m_file.addSeparator()

        a_save = QAction("&Save", self)
        a_save.setShortcut(QKeySequence.StandardKey.Save)
        a_save.triggered.connect(self._save_show)
        m_file.addAction(a_save)

        a_save_as = QAction("Save &As…", self)
        a_save_as.setShortcut(QKeySequence.StandardKey.SaveAs)
        a_save_as.triggered.connect(self._save_show_as)
        m_file.addAction(a_save_as)

        m_file.addSeparator()

        a_export_pdf = QAction("Export &PDF…", self)
        a_export_pdf.setShortcut(QKeySequence("Ctrl+E"))
        a_export_pdf.triggered.connect(self._export_pdf)
        m_file.addAction(a_export_pdf)

        # ── Settings ─────────────────────────
        # NOTE: don't set PreferencesRole — macOS would move the item into
        # the app menu and leave the Settings menu empty (looks like a
        # bug). Keep it in the Settings menu where the operator can find
        # it from the menubar directly.
        a_settings = QAction("Settings…", self)
        a_settings.setShortcut(QKeySequence("Ctrl+,"))
        a_settings.triggered.connect(self._open_settings)
        m_settings = bar.addMenu("&Settings")
        m_settings.addAction(a_settings)

        # ── Help ─────────────────────────────
        m_help = bar.addMenu("&Help")
        a_help = QAction("Keyboard Shortcuts && Help", self)
        a_help.setShortcut(QKeySequence("F1"))
        a_help.triggered.connect(self._show_help)
        m_help.addAction(a_help)

    def _new_show(self):
        if not self._confirm_discard_or_save(
            "New Show",
            "Save current show before creating a new one?",
        ):
            return

        self._show = ShowFile()
        self._show_settings = ShowSettings()
        self._engine.cues.clear()
        self._table.load_cues(self._engine.cues)
        self._apply_settings(self._show_settings)
        self._mark_clean()
        self._set_base_title(f"{APP_NAME}  {VERSION}  —  New Show")
        self._clear_autosave()
        logger.info("New show created")

    def _open_show(self):
        if not self._confirm_discard_or_save(
            "Open Show",
            "Save current show before opening another file?",
        ):
            return

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
            self._mark_clean()
            self._set_base_title(f"{APP_NAME}  {VERSION}  —  {os.path.basename(path)}")
            self._qsettings.setValue("last_show", path)
            self._clear_autosave()
        except (OSError, ValueError) as e:
            QMessageBox.critical(self, "Load Error", str(e))

    def _import_csv(self, path: str):
        try:
            self._show = ShowFile.from_csv(path)
            self._show_settings = self._show.settings
            self._engine.load_show_cues(self._show.cues)
            self._table.load_cues(self._engine.cues)
            self._apply_settings(self._show_settings)
            # Treat freshly imported as dirty — they need to Save As to persist.
            self._mark_dirty()
            self._set_base_title(f"{APP_NAME}  {VERSION}  —  {os.path.basename(path)} (imported)")
            self._clear_autosave()
        except (OSError, CueParseError) as e:
            QMessageBox.critical(self, "Import Error", str(e))

    def _save_show(self) -> bool:
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
            return False
        if not path.endswith(".ojeshow"):
            path += ".ojeshow"
        try:
            self._show.save(path)
            self._qsettings.setValue("last_show", path)
            self._mark_clean()
            self._set_base_title(f"{APP_NAME}  {VERSION}  —  {os.path.basename(path)}")
            self._flash_save_ok()
            self._clear_autosave()
            logger.info("Saved to %s", path)
            return True
        except OSError as e:
            logger.error("Save failed: %s", e)
            QMessageBox.critical(self, "Save Error", str(e))
            return False

    def _flash_save_ok(self):
        # Save button moved to the File menu — surface the confirmation
        # via the window title for ~1.5 s instead of a toast. Stash and
        # restore the base title so the dirty marker still works after.
        saved_base = self._base_title
        self.setWindowTitle(f"{saved_base}    ✓ Saved")
        QTimer.singleShot(1500, self._refresh_window_title)

    def _save_show_as(self) -> bool:
        if self._show is None:
            self._show = ShowFile()
        self._show.cues = self._engine.to_show_cues()
        self._show.settings = self._show_settings
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Show File As", "",
            "Show Files (*.ojeshow);;All Files (*)"
        )
        if not path:
            return False
        if not path.endswith(".ojeshow"):
            path += ".ojeshow"
        try:
            self._show.save(path)
            self._qsettings.setValue("last_show", path)
            self._set_base_title(f"{APP_NAME}  {VERSION}  —  {os.path.basename(path)}")
            self._clear_autosave()
            logger.info("Saved as %s", path)
            return True
        except OSError as e:
            QMessageBox.critical(self, "Save Error", str(e))
            return False

    def _default_pdf_export_path(self) -> str:
        if self._show and self._show.file_path:
            base, _ = os.path.splitext(self._show.file_path)
            return base + ".pdf"
        return os.path.join(os.path.expanduser("~"), "OJE Cue Sheet.pdf")

    def _current_show_title(self) -> str:
        if self._show_settings.show_title.strip():
            return self._show_settings.show_title.strip()
        if self._show and self._show.file_path:
            stem = os.path.splitext(os.path.basename(self._show.file_path))[0]
            return stem.replace("_", " ")
        return "Untitled Show"

    def _build_pdf_html(self) -> str:
        operator_names = list(self._show_settings.operator_names or [])
        show_name = self._current_show_title()
        generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
        cue_count = sum(1 for c in self._engine.cues if not c.is_divider)

        rows = []
        for cue in self._engine.cues:
            if cue.is_divider:
                rows.append(
                    "<tr class='section'>"
                    f"<td colspan='4'>{html.escape(cue.name or 'SECTION')}</td>"
                    "</tr>"
                )
                continue

            notes_parts = []
            for op_name in operator_names:
                comment = cue.operator_comments.get(op_name, "")
                if comment:
                    notes_parts.append(
                        f"<div class='note'>"
                        f"<span class='note-name'>{html.escape(op_name)}</span> "
                        f"{html.escape(comment).replace(chr(10), '<br>')}"
                        f"</div>"
                    )
            notes_html = "".join(notes_parts) or "<span class='muted'>—</span>"

            color_name = (cue.color or "").strip()
            color_hex = _pdf_color_hex(color_name) if color_name else ""
            tint_hex = _pdf_color_tint(color_name) if color_name else ""

            tc_style = ""
            if color_hex:
                tc_style = f" style=\"border-left: 6pt solid {html.escape(color_hex)};\""

            row_class = "cue"
            row_style = ""
            if tint_hex:
                # Tint every cell of the row, not just <tr> background, so
                # QTextDocument's HTML renderer actually applies it.
                row_style = f" style=\"background:{html.escape(tint_hex)};\""

            rows.append(
                f"<tr class='{row_class}'{row_style}>"
                f"<td class='tc'{tc_style}>{html.escape(cue.timecode or '')}</td>"
                f"<td class='cue-name'>{html.escape(cue.name or '')}</td>"
                f"<td class='cue-desc'>{html.escape(cue.description or '')}</td>"
                f"<td class='cue-notes'>{notes_html}</td>"
                "</tr>"
            )

        if not rows:
            rows.append(
                "<tr><td colspan='4' class='empty'>No cues in show.</td></tr>"
            )

        # Logo: referenced as a Qt resource named "logo" — _export_pdf
        # registers the actual QImage on the QTextDocument before printing.
        logo_html = ""
        if self._show_settings.logo_path and os.path.exists(self._show_settings.logo_path):
            logo_html = "<img src='logo' class='logo' />"

        # Landscape A4 — printer.setPageOrientation handles paper size.
        # Body margin = 0; printer.setPageMargins() handles paper margins.
        return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
body {{
    font-family: Helvetica, Arial, sans-serif;
    color: #1a1a1a;
    font-size: 11pt;
    margin: 0;
    padding: 0;
}}
.header {{
    border-bottom: 2pt solid #1f2233;
    padding-bottom: 12pt;
    margin-bottom: 16pt;
}}
.header-row {{
    width: 100%;
    border-collapse: collapse;
}}
.header-row td {{
    vertical-align: middle;
    padding: 0;
    border: 0;
}}
.logo {{
    height: 56pt;
}}
.title-cell {{
    padding-left: 14pt;
}}
h1 {{
    font-size: 26pt;
    margin: 0;
    font-weight: 700;
    letter-spacing: -0.5pt;
    color: #0a0a0a;
}}
.subtitle {{
    color: #6a6a6a;
    font-size: 10pt;
    margin-top: 2pt;
    letter-spacing: 0.4pt;
}}
.meta-cell {{
    text-align: right;
    color: #555;
    font-size: 9pt;
    line-height: 1.5;
}}
table.cues {{
    width: 100%;
    border-collapse: collapse;
    table-layout: fixed;
}}
table.cues th {{
    background: #20232f;
    color: #f0f1f5;
    font-size: 9pt;
    text-transform: uppercase;
    letter-spacing: 1.2pt;
    text-align: left;
    padding: 9pt 10pt;
    border: 0;
}}
table.cues td {{
    padding: 11pt 10pt;
    text-align: left;
    vertical-align: top;
    word-wrap: break-word;
    border-bottom: 1px solid #d8dce5;
    line-height: 1.45;
}}
tr.cue {{
    page-break-inside: avoid;
}}
.tc {{
    white-space: nowrap;
    font-family: Menlo, Courier, monospace;
    font-weight: 700;
    font-size: 11pt;
    color: #0a0a0a;
}}
.cue-name {{
    font-weight: 700;
    color: #0a0a0a;
    font-size: 11.5pt;
}}
.cue-desc {{
    color: #3a3a3a;
}}
.cue-notes {{
    color: #1a1a1a;
}}
.section td {{
    background: #1f2233;
    color: #ffffff;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1.4pt;
    padding: 10pt 14pt;
    border: 0;
    font-size: 10pt;
    page-break-after: avoid;
}}
.note {{
    margin: 0 0 6pt 0;
}}
.note:last-child {{ margin-bottom: 0; }}
.note-name {{
    font-weight: 700;
    color: #4d3fa0;
    font-size: 9pt;
    text-transform: uppercase;
    letter-spacing: 0.6pt;
}}
.muted {{ color: #999; }}
.empty {{
    color: #777;
    text-align: center;
    padding: 36pt;
    font-style: italic;
}}
</style>
</head>
<body>
<div class="header">
<table class="header-row"><tr>
<td style="width:80pt;">{logo_html}</td>
<td class="title-cell">
<h1>{html.escape(show_name)}</h1>
<div class="subtitle">CUE SHEET · {cue_count} cue{'s' if cue_count != 1 else ''} · {len(operator_names)} operator{'s' if len(operator_names) != 1 else ''}</div>
</td>
<td class="meta-cell">
Generated {html.escape(generated_at)}<br>
{html.escape(APP_NAME)} {html.escape(VERSION)}
</td>
</tr></table>
</div>
<table class="cues">
<thead>
<tr>
<th style="width: 12%;">Timecode</th>
<th style="width: 20%;">Cue</th>
<th style="width: 28%;">Description</th>
<th style="width: 40%;">Operator Notes</th>
</tr>
</thead>
<tbody>
{''.join(rows)}
</tbody>
</table>
</body>
</html>"""

    def _export_pdf(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Cue Sheet PDF", self._default_pdf_export_path(),
            "PDF Files (*.pdf);;All Files (*)"
        )
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"

        from PyQt6.QtCore import QMarginsF, QUrl
        from PyQt6.QtGui import QImage, QPageLayout

        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(path)
        # Landscape A4 — gives a wide row to fit timecode, name, description
        # and operator notes side-by-side without cramping the description.
        page_layout = printer.pageLayout()
        page_layout.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
        page_layout.setOrientation(QPageLayout.Orientation.Landscape)
        page_layout.setMargins(QMarginsF(14.0, 12.0, 14.0, 12.0))
        page_layout.setUnits(QPageLayout.Unit.Millimeter)
        printer.setPageLayout(page_layout)

        doc = QTextDocument()
        # Register the studio logo (if any) as a Qt resource the HTML can
        # reference via <img src='logo'>. QImage handles the actual bytes;
        # the HTML stays generic so we don't have to base64-encode in the
        # template.
        logo_path = self._show_settings.logo_path or ""
        if logo_path and os.path.exists(logo_path):
            img = QImage(logo_path)
            if not img.isNull():
                doc.addResource(
                    QTextDocument.ResourceType.ImageResource,
                    QUrl("logo"),
                    img,
                )
        doc.setHtml(self._build_pdf_html())
        try:
            doc.print(printer)
            QMessageBox.information(
                self, "PDF Exported",
                f"Exported printable cue sheet to:\n{path}"
            )
        except Exception as e:
            QMessageBox.critical(self, "PDF Export Error", str(e))

    # ── Settings ──────────────────────────────────────────────────────────────

    def _open_settings(self):
        dlg = SettingsDialog(self._show_settings, self._audio_devices, self)
        if dlg.exec():
            new_settings = dlg.get_settings()
            if new_settings:
                self._show_settings = new_settings
                self._apply_settings(new_settings)
                self._mark_dirty()

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

        # Cue cards need the current operator list to filter out stale keys
        self._current_card.set_operators(settings.operator_names)
        self._next_card.set_operators(settings.operator_names)

        # Performance view
        self._perf_view.apply_settings(settings)

        # Operator edit panel
        self._op_panel.set_operators(settings.operator_names)
        if self._edit_mode:
            row = self._table.currentRow()
            if 0 <= row < len(self._engine.cues):
                cue = self._engine.cues[row]
                if not cue.is_divider:
                    self._op_panel.show_for_cue(row, cue)

        if self._web_remote and self._web_remote._running:
            self._web_remote.set_operators(settings.operator_names)
            self._web_remote.set_remote_password(settings.remote_password)

        # Re-render current/next cards so operator list changes take effect
        # without waiting for the next timecode poll.
        self._update_cues()

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
        self._web_remote.set_remote_password(self._show_settings.remote_password)
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
        dlg = RemotePanel(port, self._show_settings.remote_password, self)
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
            # 70 / 30 — table is the primary area, panel is the side helper.
            # setSizes wants absolute pixels (not percentages), and a tiny
            # [70, 30] gets reshuffled by minimum-size constraints into a
            # weird "panel takes everything" state. Compute from real width.
            total = self._table_splitter.width() or 1280
            self._table_splitter.setSizes(
                [int(total * 0.70), int(total * 0.30)]
            )
            row = self._table.currentRow()
            if 0 <= row < len(self._engine.cues):
                cue = self._engine.cues[row]
                if not cue.is_divider:
                    self._op_panel.show_for_cue(row, cue)
        else:
            self._btn_edit.setText("Edit Cues")
            self._btn_edit.setStyleSheet("")
            self._op_panel.hide_panel()
            self._table_splitter.setSizes([1280, 0])

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
        self._mark_dirty()

    def _on_cue_edit(self, row: int, field: str, value: str):
        self._engine.update_cue_field(row, field, value)
        if field == "timecode":
            self._table.load_cues(self._engine.cues)
            self._table.set_edit_mode(True)
        else:
            self._table.refresh_index_column(self._engine.cues)
        self._mark_dirty()

    def _on_row_add(self, after_row: int):
        self._engine.add_cue(after_index_0=after_row)
        self._table.load_cues(self._engine.cues)
        self._table.set_edit_mode(True)
        new_row = min(after_row + 1, len(self._engine.cues) - 1)
        self._table.setCurrentCell(new_row, 3)
        self._mark_dirty()

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
            self._mark_dirty()

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
            self._mark_dirty()

    def _on_divider_add(self, after_row: int):
        self._engine.add_cue(after_index_0=after_row, is_divider=True)
        self._table.load_cues(self._engine.cues)
        self._table.set_edit_mode(True)
        new_row = min(after_row + 1, len(self._engine.cues) - 1)
        self._table.setCurrentCell(new_row, 3)
        self._mark_dirty()

    def _on_row_move(self, from_row: int, to_row: int):
        self._engine.move_cue(from_row, to_row)
        self._table.load_cues(self._engine.cues)
        self._table.set_edit_mode(True)
        self._table.setCurrentCell(to_row, self._table.currentColumn())
        self._mark_dirty()

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
            if device_index is None:
                self._show_error(
                    "The selected audio device is not currently available.\n\n"
                    "Reconnect it or open Settings and choose another input device."
                )
                return
        channel_index = self._show_settings.audio_channel

        self._engine.reset_active()
        logger.info("Starting decoder  device=%s  channel=%d", device_index, channel_index)
        try:
            self._decoder = LTCDecoder(device_index=device_index, channel_index=channel_index)
            self._decoder.start()
        except Exception as e:
            logger.error("Failed to start decoder: %s", e)
            self._decoder = None
            self._show_error(f"Could not start LTC decoder:\n{e}")
            return

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
        self._last_db = -120.0
        self._signal_warning_text = ""
        self._refresh_signal_dot()
        self._perf_view.update_signal_state(self._signal_ok, self._last_db, self._signal_warning_text)

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
            self._engine.set_fps(fps)
            self._current_frames = self._engine.tc_to_frames(h, m, s, f)
            tc_str = f"{h:02d}:{m:02d}:{s:02d}:{f:02d}"
            self._tc_label.setText(tc_str)
            self._fps_label.setText(f"FPS: {fps:.2f}")
            self._signal_ok = True
            self._blink_timer.stop()
            self._refresh_signal_dot()
            self._perf_view.update_signal_state(self._signal_ok, self._last_db, self._signal_warning_text)
            self._update_cues(tc_str)
            self._log(f"TC {tc_str}  fps={fps:.2f}")

        elif kind == "signal_lost":
            self._signal_ok = False
            h, m, s, f = self._last_tc
            self._tc_label.setText(f"{h:02d}:{m:02d}:{s:02d}:{f:02d}  [NO SIGNAL]")
            self._blink_timer.start()
            self._signal_warning_text = ""
            self._perf_view.update_signal_state(self._signal_ok, self._last_db, self._signal_warning_text)
            self._log("SIGNAL LOST")

        elif kind == "level":
            db = msg[1]
            self._last_db = db
            self._vu.set_db(db)
            if db < -40:
                self._signal_warning_text = "Weak signal"
            elif db > -3:
                self._signal_warning_text = "Clipping!"
            else:
                self._signal_warning_text = ""
            self._signal_warn.setText(self._signal_warning_text)
            self._perf_view.update_signal_state(self._signal_ok, self._last_db, self._signal_warning_text)

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
        self._perf_view.update_display(
            current, nxt, countdown, tc_str, cur_group, nxt_group, self._last_fps, self._engine.cues
        )

        if self._web_remote and self._web_remote._running:
            self._web_remote.broadcast_state(
                current, nxt, countdown, tc_str, cur_group, nxt_group,
                fps=self._last_fps,
                db=self._last_db,
                signal_ok=self._signal_ok,
                running=self._running,
                signal_warning=self._signal_warning_text,
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
        self._perf_view.update_display(
            current, nxt, countdown, tc_str, cur_group, nxt_group, self._last_fps, self._engine.cues
        )

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

    @staticmethod
    def _compute_state_dir() -> str:
        """Platform-appropriate directory for logs + autosave."""
        system = platform.system()
        if system == "Darwin":
            return os.path.expanduser("~/Library/Logs/OJECueMonitor")
        if system == "Windows":
            base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
            return os.path.join(base, "OJECueMonitor", "Logs")
        base = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
        return os.path.join(base, "OJECueMonitor", "logs")

    def _autosave_path(self) -> str:
        return os.path.join(self._state_dir, "autosave.ojeshow")

    def _init_log(self):
        try:
            os.makedirs(self._state_dir, exist_ok=True)
            log_path = os.path.join(self._state_dir,
                                    datetime.now().strftime("session_%Y-%m-%d.log"))
            self._log_file = open(log_path, "a", encoding="utf-8")
            self._log(f"--- {APP_NAME} {VERSION} started ---")
        except OSError:
            self._log_file = None

    # ── Autosave ──────────────────────────────────────────────────────────────

    def _autosave_tick(self):
        self._log(f"autosave tick: dirty={self._dirty} fresh={self._autosave_fresh} cues={len(self._engine.cues)}")
        # Skip work if we have nothing to save or nothing has changed since
        # the last successful autosave write. Crucially, we do NOT flip
        # _dirty here — it tracks "unsaved since last explicit save" and is
        # only cleared by _save_show / _clear_autosave, so the close path
        # can still detect truly unsaved work.
        if not self._dirty or self._autosave_fresh:
            return
        if not self._engine.cues:
            return
        try:
            self._write_autosave()
            self._autosave_fresh = True
            self._log("autosave written")
        except OSError as e:
            logger.warning("Autosave failed: %s", e)
            self._log(f"autosave FAILED: {e}")

    def _write_autosave(self):
        path = self._autosave_path()
        # Build a ShowFile from the current engine state + settings and save
        # it atomically through a .tmp side-file so a crash mid-write cannot
        # leave a half-written autosave that would kill recovery next time.
        show = ShowFile(
            settings=self._show_settings,
            cues=self._engine.to_show_cues(),
        )
        tmp = path + ".tmp"
        os.makedirs(os.path.dirname(path), exist_ok=True)
        show.save(tmp)
        os.replace(tmp, path)

    def _clear_autosave(self):
        try:
            os.remove(self._autosave_path())
        except OSError:
            pass
        self._mark_clean()
        self._autosave_fresh = True

    def _mark_dirty(self):
        if not self._dirty:
            self._log("dirty marked (was clean)")
        self._dirty = True
        self._autosave_fresh = False
        self._refresh_window_title()

    def _mark_clean(self):
        self._dirty = False
        self._refresh_window_title()

    def _set_base_title(self, title: str):
        """Stash the canonical title; refresh applies the * marker."""
        self._base_title = title
        self._refresh_window_title()

    def _refresh_window_title(self):
        base = getattr(self, "_base_title", f"{APP_NAME}  {VERSION}")
        self.setWindowTitle(("• " + base) if self._dirty else base)

    def _autosave_exists(self) -> bool:
        try:
            return os.path.getsize(self._autosave_path()) > 0
        except OSError:
            return False

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
        title.setFont(sans_font(18, bold=True))
        title.setStyleSheet(f"color: {TEXT_BRIGHT.name()};")
        lay.addWidget(title)

        sub = QLabel(
            f"{COPYRIGHT}\n"
            f"LTC Timecode Cue List Manager for Live Shows\n"
            f"{WEBSITE}  ·  {EMAIL}"
        )
        sub.setStyleSheet(f"color: {TEXT_DIM.name()}; font-size: 12px;")
        sub.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(sub)

        lay.addWidget(_hline())

        _mod = "Ctrl" if platform.system() == "Windows" else "Cmd"
        help_text = (
            "<h3 style='color:#dcdcdc;'>Keyboard Shortcuts</h3>"
            "<table cellpadding='4' style='color:#ccc; font-size:13px;'>"
            f"<tr><td style='color:#7a7acd; font-weight:bold;'>{_mod}+N</td>"
            "    <td>New show</td></tr>"
            f"<tr><td style='color:#7a7acd; font-weight:bold;'>{_mod}+O</td>"
            "    <td>Open show file / import CSV</td></tr>"
            f"<tr><td style='color:#7a7acd; font-weight:bold;'>{_mod}+S</td>"
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
        # Offer to save unsaved changes before closing.
        if self._dirty:
            reply = QMessageBox.question(
                self, "Unsaved Changes",
                "Save changes before closing?",
                QMessageBox.StandardButton.Save
                | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel,
            )
            if reply == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
            if reply == QMessageBox.StandardButton.Save:
                if not self._save_show():   # clears autosave on success
                    event.ignore()
                    return
            elif reply == QMessageBox.StandardButton.Discard:
                self._clear_autosave()

        self._stop_decoder()
        if self._web_remote:
            self._web_remote.stop()
        self._autosave_timer.stop()
        # On a clean exit with no unsaved work, drop any stale autosave file.
        if not self._dirty:
            self._clear_autosave()
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


def _pdf_color_hex(name: str) -> str:
    mapping = {
        "red": "#af3030",
        "dark red": "#781919",
        "orange": "#c36926",
        "amber": "#d2a01e",
        "yellow": "#af9b26",
        "lime": "#5fb42d",
        "green": "#309b4b",
        "dark green": "#1e6432",
        "teal": "#268c82",
        "cyan": "#30a5af",
        "sky": "#4691d2",
        "blue": "#305faf",
        "dark blue": "#233782",
        "indigo": "#4b37a0",
        "purple": "#7d37af",
        "magenta": "#a5328c",
        "pink": "#c35f9b",
        "rose": "#be465a",
        "white": "#c8c8c8",
        "grey": "#6e6e6e",
    }
    return mapping.get(name.lower().strip(), "#9a9a9a")


def _pdf_color_tint(name: str) -> str:
    """Very light pastel of the cue colour for full-row backgrounds.
    Rendered against white paper, so we blend each colour ~92% with white
    — strong enough to scan, soft enough not to dominate."""
    hex_color = _pdf_color_hex(name)
    if not hex_color.startswith("#") or len(hex_color) != 7:
        return ""
    try:
        r = int(hex_color[1:3], 16)
        g = int(hex_color[3:5], 16)
        b = int(hex_color[5:7], 16)
    except ValueError:
        return ""
    blend = 0.08  # 8% colour, 92% white
    r = int(r * blend + 255 * (1 - blend))
    g = int(g * blend + 255 * (1 - blend))
    b = int(b * blend + 255 * (1 - blend))
    return f"#{r:02x}{g:02x}{b:02x}"
