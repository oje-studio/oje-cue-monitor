from __future__ import annotations
from typing import Dict, Optional

import html
import logging
import os
import platform
import queue
from datetime import datetime

from PyQt6.QtCore import Qt, QTimer, QSettings
from PyQt6.QtGui import (
    QColor, QFont, QPalette, QKeySequence, QShortcut, QAction,
    QPainter, QPixmap,
)
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
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
from ui import theme
from web_remote import WebRemoteServer

logger = logging.getLogger(__name__)

APP_NAME  = "ØJE CUE MONITOR"
VERSION   = "v1.0β"
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
            f"CueCard {{ background: {theme.BG_SURFACE}; "
            f"border: 1px solid {theme.BORDER}; "
            f"border-radius: {theme.RADIUS_LG}px; }}"
        )
        self._countdown_enabled = True
        self._operator_names: list = []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(6)

        tl = QLabel(title.upper())
        tl.setStyleSheet(
            f"color: {theme.TEXT_DIM}; font-size: 11px; "
            "font-weight: 600; letter-spacing: 1.5px;"
        )
        lay.addWidget(tl)

        self.name_lbl = QLabel("—")
        fn = QFont(); fn.setPointSize(20); fn.setBold(True)
        self.name_lbl.setFont(fn)
        self.name_lbl.setWordWrap(True)
        self.name_lbl.setStyleSheet(f"color: {theme.TEXT_BRIGHT};")
        lay.addWidget(self.name_lbl)

        self.desc_lbl = QLabel("")
        self.desc_lbl.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 13px;")
        self.desc_lbl.setWordWrap(True)
        lay.addWidget(self.desc_lbl)

        # Operator notes are NOT rendered in the main window cue cards —
        # they got squashed and read poorly. The full operator notes
        # surface in Performance Mode and the Web Remote (which have
        # space) and are edited via the OperatorEditPanel in Edit Cues.
        self.ops_lbl = None

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
            self.cd_lbl.setText("")
            return
        self.name_lbl.setText(cue.name or "—")
        self.desc_lbl.setText(cue.description)
        if countdown is not None and self._countdown_enabled:
            m, s  = divmod(int(countdown), 60)
            # Sub-10-second countdown flips to the danger hue so the
            # operator's eye snaps to the upcoming GO without needing
            # a separate flashing indicator.
            color = (theme.SEMANTIC_DANGER if countdown < 10
                     else theme.TEXT_BRIGHT)
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
        header.setStyleSheet(f"background: {theme.BG_HEADER};")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(14, 0, 14, 0)
        hl.setSpacing(10)

        hl.addWidget(BrandMark(parent=header), alignment=Qt.AlignmentFlag.AlignVCenter)

        hl.addWidget(_dot_sep())

        self._signal_dot = QLabel("●")
        self._signal_dot.setStyleSheet(f"color: {theme.SEMANTIC_DANGER}; font-size: 16px;")
        hl.addWidget(self._signal_dot)

        self._tc_label = QLabel("--:--:--:--")
        self._tc_label.setFont(mono_font(22, bold=True))
        self._tc_label.setStyleSheet(f"color: {theme.TEXT_BRIGHT}; letter-spacing: 2px;")
        hl.addWidget(self._tc_label)

        hl.addWidget(_dot_sep())

        self._fps_label = QLabel("FPS —")
        self._fps_label.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 12px;")
        hl.addWidget(self._fps_label)

        hl.addWidget(_dot_sep())

        self._vu = VUMeter()
        hl.addWidget(self._vu)

        self._signal_warn = QLabel("")
        self._signal_warn.setStyleSheet(f"color: {theme.SEMANTIC_WARNING}; font-size: 11px;")
        hl.addWidget(self._signal_warn)

        hl.addStretch()

        self._live_label = QLabel("● LIVE")
        self._live_label.setStyleSheet(
            f"color: {theme.SEMANTIC_SUCCESS}; font-size: 12px; font-weight: bold;"
        )
        self._live_label.setVisible(False)
        hl.addWidget(self._live_label)

        # Show-specific logo (pulled from .ojeshow settings.logo_path).
        # Distinct from the BrandMark on the left — that's the studio
        # mark, this is whatever logo the operator wants for the
        # current production.  Hidden until set_show_settings wires
        # in a real pixmap.
        self._header_logo = QLabel()
        self._header_logo.setVisible(False)
        hl.addWidget(self._header_logo)

        # Wall clock at the far right of the header — sized to match the
        # timecode (mono 24, bold) so the eye reads them as a pair:
        # "show timecode" on one side, "real-world time" on the other.
        # Small clock-face icon prefix makes it unmistakable that this
        # is wall time, not another timecode.
        from ui.icons import make_icon
        hl.addWidget(_dot_sep())
        self._clock_icon_lbl = QLabel()
        self._clock_icon_lbl.setPixmap(
            make_icon("clock", theme.TEXT_DIM).pixmap(20, 20)
        )
        hl.addWidget(self._clock_icon_lbl)
        self._clock_label = QLabel("")
        self._clock_label.setFont(mono_font(24, bold=True))
        self._clock_label.setStyleSheet(f"color: {theme.TEXT_BRIGHT};")
        hl.addWidget(self._clock_label)
        # Header now ends here — Performance and Start moved to the
        # footer alongside Edit Cues / Remote so the operator sees one
        # clean monitoring strip on top and one action strip at the
        # bottom (instead of mixing both in the header).

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
        from ui.icons import make_icon, icon_size

        footer = QWidget()
        footer.setFixedHeight(56)
        footer.setStyleSheet(f"background: {theme.BG_HEADER};")
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(12, 0, 12, 0)
        fl.setSpacing(8)

        # ── Left edge: Help + Edit Cues ──────────────────────────────
        # Tiny "?" pill on the very left, dim — quick path to the help
        # dialog without occupying the menu bar.
        self._btn_help = QPushButton("?")
        self._btn_help.setFixedSize(28, 28)
        self._btn_help.setToolTip("Help & Keyboard Shortcuts  [F1]")
        self._btn_help.setStyleSheet(_help_btn_style())
        self._btn_help.clicked.connect(self._show_help)
        fl.addWidget(self._btn_help)

        # Show prep lives on the left — the operator does this before
        # the show starts and may dip back in mid-show to tweak notes.
        self._btn_edit = QPushButton(" Edit Cues")
        self._btn_edit.setIcon(make_icon("edit", theme.TEXT_PRIMARY))
        self._btn_edit.setIconSize(icon_size(16))
        self._btn_edit.setFixedHeight(34)
        self._btn_edit.setCheckable(True)
        self._btn_edit.setStyleSheet(_secondary_btn_style())
        self._btn_edit.clicked.connect(self._toggle_edit_mode)
        fl.addWidget(self._btn_edit)

        fl.addStretch()
        # Studio copyright in the middle, tiny + dim — recognised but
        # not competing for attention.
        cr_lbl = QLabel(f"{COPYRIGHT}  ·  {WEBSITE}")
        cr_lbl.setStyleSheet(f"color: {theme.TEXT_DISABLED}; font-size: 10px;")
        fl.addWidget(cr_lbl)
        fl.addStretch()

        # ── Right cluster: Remote → Performance → START ──────────────
        # Reads left-to-right as the show-startup order:
        #   Remote   — let the team's phones connect
        #   Performance — bring the operator screen up
        #   START    — arm LTC and run the show
        self._btn_remote = QPushButton(" Remote")
        self._btn_remote.setIcon(make_icon("remote", theme.TEXT_PRIMARY))
        self._btn_remote.setIconSize(icon_size(16))
        self._btn_remote.setFixedHeight(34)
        self._btn_remote.setToolTip("Start/stop web remote for other devices")
        self._btn_remote.setCheckable(True)
        self._btn_remote.setStyleSheet(_secondary_btn_style())
        self._btn_remote.clicked.connect(self._toggle_remote)
        fl.addWidget(self._btn_remote)

        self._btn_perf = QPushButton(" Performance")
        self._btn_perf.setIcon(make_icon("fullscreen", theme.TEXT_PRIMARY))
        self._btn_perf.setIconSize(icon_size(16))
        self._btn_perf.setFixedHeight(34)
        self._btn_perf.setStyleSheet(_secondary_btn_style())
        self._btn_perf.clicked.connect(self._enter_perf_mode)
        fl.addWidget(self._btn_perf)

        # START is THE primary action — visually distinct (taller, wider,
        # full green) so the eye lands on it first.  Switches to red
        # in stop_btn_style while LTC is decoding.
        self._btn_start = QPushButton(" START")
        self._btn_start.setIcon(make_icon("record", "#ffffff"))
        self._btn_start.setIconSize(icon_size(18))
        self._btn_start.setFixedHeight(40)
        self._btn_start.setMinimumWidth(110)
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
        last_name = os.path.basename(last_show) if last_show else ""
        if not _RecoveryDialog.ask(self, last_name):
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

        # ── Settings ─────────────────────────
        # Qt's TextHeuristicRole auto-detects the words "Settings",
        # "Preferences", "Options", "Configure" in QAction text and
        # silently moves the action to the macOS application menu.
        # That's where last time the Settings submenu showed up empty —
        # the action got teleported. Force NoRole so the action stays
        # exactly where we put it.
        a_settings = QAction("Settings…", self)
        a_settings.setMenuRole(QAction.MenuRole.NoRole)
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

    def _current_show_title(self) -> str:
        if self._show_settings.show_title.strip():
            return self._show_settings.show_title.strip()
        if self._show and self._show.file_path:
            stem = os.path.splitext(os.path.basename(self._show.file_path))[0]
            return stem.replace("_", " ")
        return "Untitled Show"

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
            self._web_remote.set_operator_colors(settings.operator_colors)
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
        self._web_remote.set_operator_colors(self._show_settings.operator_colors)
        self._web_remote.set_remote_password(self._show_settings.remote_password)
        self._web_remote.start()
        self._btn_remote.setText(" Remote ON")
        from ui.icons import make_icon
        self._btn_remote.setIcon(make_icon("remote", "#ffffff"))
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
        self._btn_remote.setText(" Remote")
        from ui.icons import make_icon
        self._btn_remote.setIcon(make_icon("remote", "#dadada"))
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
            self._btn_edit.setText(" Done")
            from ui.icons import make_icon
            self._btn_edit.setIcon(make_icon("check", "#dadada"))
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
            self._btn_edit.setText(" Edit Cues")
            from ui.icons import make_icon
            self._btn_edit.setIcon(make_icon("edit", "#dadada"))
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
        elif field == "color":
            # Re-style immediately so the new colour shows as a row
            # tint on the next paint instead of waiting for the
            # _update_cues tick.
            self._table.update_highlight(self._engine.cues, None,
                                         self._current_frames)
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
        self._btn_start.setText(" STOP")
        from ui.icons import make_icon
        self._btn_start.setIcon(make_icon("stop", "#ffffff"))
        self._btn_start.setStyleSheet(_stop_btn_style())
        self._live_label.setVisible(True)

    def _stop_decoder(self):
        if self._decoder:
            self._decoder.stop()
            self._decoder = None
        self._running = False
        self._poll_timer.stop()
        self._blink_timer.stop()
        self._btn_start.setText(" START")
        from ui.icons import make_icon
        self._btn_start.setIcon(make_icon("record", "#ffffff"))
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
        # Steady state: green when LTC is locked, red otherwise.
        # Routed through the design system so the indicator matches
        # the active-cue green and the connection-lost banner red on
        # the web remote — same colour, same meaning, anywhere it
        # appears.
        color = theme.SEMANTIC_SUCCESS if self._signal_ok else theme.SEMANTIC_DANGER
        self._signal_dot.setStyleSheet(f"color: {color}; font-size: 16px;")

    def _do_blink(self):
        # While waiting for LTC the dot pulses between full danger
        # red and a faded version of the same hue (25 % alpha) so the
        # reader's eye registers "trying to lock" without competing
        # with the timecode for attention.  Using the same base
        # colour for both blink halves keeps the pulse readable on
        # any monitor calibration.
        self._blink_state = not self._blink_state
        color = (theme.SEMANTIC_DANGER if self._blink_state
                 else theme.with_alpha(theme.SEMANTIC_DANGER, 0.25))
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
        # Inline <style> keeps the markup readable — kbd, headings, and
        # body text reuse design-system tokens instead of repeating
        # hex literals on every <td>.
        kbd = (
            f"color:{theme.SEMANTIC_INFO}; font-weight:bold; "
            f"font-family:'Menlo','Consolas',monospace;"
        )
        h_color = theme.TEXT_PRIMARY
        body_color = theme.TEXT_PRIMARY
        muted_color = theme.TEXT_MUTED
        warn_color = theme.SEMANTIC_WARNING
        help_text = (
            f"<h3 style='color:{h_color};'>Keyboard Shortcuts</h3>"
            f"<table cellpadding='4' style='color:{body_color}; font-size:13px;'>"
            f"<tr><td style='{kbd}'>{_mod}+N</td>"
            "    <td>New show</td></tr>"
            f"<tr><td style='{kbd}'>{_mod}+O</td>"
            "    <td>Open show file / import CSV</td></tr>"
            f"<tr><td style='{kbd}'>{_mod}+S</td>"
            "    <td>Save show</td></tr>"
            f"<tr><td style='{kbd}'>P</td>"
            "    <td>Toggle Performance Mode</td></tr>"
            f"<tr><td style='{kbd}'>Escape</td>"
            "    <td>Exit Performance Mode</td></tr>"
            f"<tr><td style='{kbd}'>Space</td>"
            "    <td>Manual cue mark (logged)</td></tr>"
            f"<tr><td style='{kbd}'>F1</td>"
            "    <td>This help window</td></tr>"
            "</table>"
            "<br>"
            f"<h3 style='color:{h_color};'>Edit Mode</h3>"
            f"<table cellpadding='4' style='color:{body_color}; font-size:13px;'>"
            f"<tr><td style='{kbd}'>+ Cue</td>"
            "    <td>Add cue after selection</td></tr>"
            f"<tr><td style='{kbd}'>+ Section</td>"
            "    <td>Add section divider</td></tr>"
            f"<tr><td style='{kbd}'>Delete</td>"
            "    <td>Delete selected rows (multi-select)</td></tr>"
            f"<tr><td style='{kbd}'>Up / Down</td>"
            "    <td>Move selected cue</td></tr>"
            "</table>"
            "<br>"
            f"<h3 style='color:{h_color};'>Show File (.ojeshow)</h3>"
            f"<p style='color:{muted_color}; font-size:12px;'>"
            "A single JSON file containing all settings (audio device, operators, "
            "font sizes, logo) and the complete cue list. Replaces the legacy CSV format. "
            "Auto-saved when exiting Edit Mode.</p>"
            "<br>"
            f"<h3 style='color:{h_color};'>LTC Timecode</h3>"
            f"<p style='color:{muted_color}; font-size:12px;'>"
            "Connect an LTC/SMPTE timecode source to any audio input. "
            "Select the device and channel in Settings. Press START to begin reading. "
            "The VU meter shows input level — aim for -20 to -6 dBFS.</p>"
            "<br>"
            f"<h3 style='color:{h_color};'>Duplicate Timecodes</h3>"
            f"<p style='color:{muted_color}; font-size:12px;'>"
            "Cues with identical timecodes are marked with a "
            f"<span style='color:{warn_color};'>&#9888;</span> warning. "
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

class _RecoveryDialog(QDialog):
    """
    Restore-from-autosave prompt shown at startup when the previous
    session ended without an explicit save.  Replaces the
    platform-default QMessageBox so the dialog matches the dark
    surface the operator sees everywhere else in the app.
    """

    def __init__(self, last_show_name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Restore Unsaved Changes")
        self.setMinimumWidth(440)
        self.setStyleSheet(
            f"QDialog {{ background: {theme.BG_APP}; }}"
            f"QLabel {{ color: {theme.TEXT_PRIMARY}; }}"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 18)
        root.setSpacing(14)

        # Tag — small caps, lifted from theme.SEMANTIC_WARNING so the
        # operator's eye registers "this is a recovery flow" before
        # they read the body.  Two-line headline + dim explanation
        # mirror the empty-state placeholder pattern (b7 / e3).
        tag = QLabel("AUTOSAVE FOUND")
        tag.setStyleSheet(
            f"color: {theme.SEMANTIC_WARNING}; font-size: 11px; "
            "font-weight: 700; letter-spacing: 2px;"
        )
        root.addWidget(tag)

        head = QLabel("The previous session ended before saving.")
        f_head = QFont(); f_head.setPointSize(15); f_head.setBold(True)
        head.setFont(f_head)
        head.setStyleSheet(f"color: {theme.TEXT_BRIGHT};")
        head.setWordWrap(True)
        root.addWidget(head)

        # Show the original file name when we have one — operator sees
        # exactly which show is being recovered.  Otherwise the second
        # paragraph is enough context.
        if last_show_name:
            sub = QLabel(
                f"Restore the autosaved cue list for "
                f"<b>{html.escape(last_show_name)}</b>?"
            )
        else:
            sub = QLabel("Restore the autosaved cue list?")
        sub.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 12px;")
        sub.setTextFormat(Qt.TextFormat.RichText)
        sub.setWordWrap(True)
        root.addWidget(sub)

        hint = QLabel(
            "Discarding clears the autosave and starts with a blank show."
        )
        hint.setStyleSheet(f"color: {theme.TEXT_DIM}; font-size: 11px;")
        hint.setWordWrap(True)
        root.addWidget(hint)

        # Action row — Discard left/secondary, Restore right/primary
        # green so the safe-default sits where the eye lands.
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        btn_discard = QPushButton("Discard")
        btn_discard.setStyleSheet(_secondary_btn_style())
        btn_discard.setFixedHeight(32)
        btn_discard.clicked.connect(self.reject)
        btn_row.addWidget(btn_discard)

        btn_restore = QPushButton("Restore")
        btn_restore.setStyleSheet(_start_btn_style())
        btn_restore.setFixedHeight(32)
        btn_restore.setMinimumWidth(110)
        btn_restore.setDefault(True)
        btn_restore.clicked.connect(self.accept)
        btn_row.addWidget(btn_restore)

        root.addSpacing(4)
        root.addLayout(btn_row)

    @classmethod
    def ask(cls, parent, last_show_name: str = "") -> bool:
        dlg = cls(last_show_name, parent)
        return dlg.exec() == QDialog.DialogCode.Accepted


# ── helpers ───────────────────────────────────────────────────────────────────

def _hline() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    f.setStyleSheet(f"color: {DARK_BORDER.name()};")
    return f


def _dot_sep() -> QLabel:
    """
    Middot separator between header items — same shape as the
    Performance Mode and Web Remote status bars (A3).  A typographic
    rest between groups, not a vertical bar that visually competes
    with the timecode digits.
    """
    s = QLabel("·")
    s.setStyleSheet(f"color: {theme.TEXT_DIM}; font-size: 22px;")
    return s


def _logo_pixmap(color_hex: str, size: int) -> QPixmap:
    """
    Load assets/logo_src.png, recolour every non-transparent pixel to
    `color_hex`, and scale to `size × size`.  CompositionMode_SourceIn
    keeps the glyph silhouette and replaces its colour — the studio
    Ø is orange in the source file but lives on a dark header here,
    so it has to retint at runtime.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    src_path = os.path.join(os.path.dirname(here), "assets", "logo_src.png")
    src = QPixmap(src_path)
    if src.isNull():
        return QPixmap()
    # Render at 2× then downscale so HiDPI displays still get crisp
    # edges; PyQt picks up the high-res variant via QPixmap automatic
    # devicePixelRatio handling.
    scaled = src.scaled(
        size * 2, size * 2,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    out = QPixmap(scaled.size())
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.drawPixmap(0, 0, scaled)
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    p.fillRect(out.rect(), QColor(color_hex))
    p.end()
    return out


class BrandMark(QWidget):
    """
    Studio Ø glyph (recoloured from assets/logo_src.png) followed by
    the product name and version.  One reusable widget so the same
    brand block can land in the header, the About dialog, the PDF
    cover, etc. without each surface re-implementing the typography.

    Tokens:
      mark        theme.BRAND_MARK_COLOR / BRAND_MARK_SIZE
      product     theme.TEXT_BRIGHT (semibold, tracked)
      version     theme.TEXT_MUTED  (regular)
    """

    def __init__(self, product: str = "CUE MONITOR", version: str = VERSION,
                 parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        mark = QLabel()
        mark.setFixedSize(theme.BRAND_MARK_SIZE, theme.BRAND_MARK_SIZE)
        mark.setPixmap(_logo_pixmap(theme.BRAND_MARK_COLOR, theme.BRAND_MARK_SIZE))
        mark.setScaledContents(True)
        lay.addWidget(mark, alignment=Qt.AlignmentFlag.AlignVCenter)

        name = QLabel(product)
        name.setFont(sans_font(13, bold=False))
        name.setStyleSheet(
            f"color: {theme.TEXT_BRIGHT}; font-weight: 600; letter-spacing: 1.5px;"
        )
        lay.addWidget(name, alignment=Qt.AlignmentFlag.AlignVCenter)

        ver = QLabel(version)
        ver.setFont(sans_font(11, bold=False))
        ver.setStyleSheet(f"color: {theme.TEXT_MUTED};")
        lay.addWidget(ver, alignment=Qt.AlignmentFlag.AlignVCenter)


def _vline() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.VLine)
    f.setStyleSheet(f"color: {DARK_BORDER.name()};")
    return f


def _start_btn_style() -> str:
    """Primary action — show is armed, ready to GO."""
    return (
        f"QPushButton {{ background: {theme.ACTION_PRIMARY}; "
        f"color: white; font-weight: 700; letter-spacing: 1px; "
        f"border: none; border-radius: {theme.RADIUS_MD}px; "
        f"padding: 0 14px; }}"
        f"QPushButton:hover {{ background: {theme.ACTION_PRIMARY_HOVER}; }}"
    )


def _stop_btn_style() -> str:
    """START in its 'running' state — pressing again stops the show."""
    return (
        f"QPushButton {{ background: {theme.SEMANTIC_DANGER}; "
        f"color: white; font-weight: 700; letter-spacing: 1px; "
        f"border: none; border-radius: {theme.RADIUS_MD}px; "
        f"padding: 0 14px; }}"
        f"QPushButton:hover {{ background: #ED5A5F; }}"
    )


def _secondary_btn_style() -> str:
    """
    Edit Cues / Remote / Performance — quieter than START so the
    eye lands on the primary action first.  Uses BG_RAISED so the
    button still reads as a control on the very dark footer, and
    flips to an info-blue accent when checkable buttons are toggled
    on (Remote streaming / Edit Mode active).
    """
    return (
        f"QPushButton {{ background: {theme.BG_RAISED}; "
        f"color: {theme.TEXT_PRIMARY}; font-weight: 600; "
        f"border: 1px solid {theme.BORDER}; "
        f"border-radius: {theme.RADIUS_MD}px; "
        f"padding: 0 12px; }}"
        f"QPushButton:hover {{ background: #2e2e2e; "
        f"border-color: {theme.BORDER_STRONG}; }}"
        f"QPushButton:checked {{ background: rgba(122, 183, 255, 0.14); "
        f"color: {theme.SEMANTIC_INFO}; "
        f"border-color: {theme.SEMANTIC_INFO}; }}"
        f"QPushButton:checked:hover {{ background: rgba(122, 183, 255, 0.22); }}"
    )


def _help_btn_style() -> str:
    """Tiny pill on the very left of the footer — quiet by default."""
    return (
        f"QPushButton {{ background: transparent; color: {theme.TEXT_DIM}; "
        f"border: 1px solid {theme.BORDER}; "
        f"border-radius: 14px; font-weight: bold; font-size: 13px; }}"
        f"QPushButton:hover {{ color: {theme.TEXT_PRIMARY}; "
        f"border-color: {theme.BORDER_STRONG}; }}"
    )


