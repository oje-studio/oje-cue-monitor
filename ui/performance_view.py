from __future__ import annotations
from typing import Optional, List, Dict
from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QListWidget, QListWidgetItem,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QBrush, QColor, QFont, QIcon, QPainter, QPen, QPixmap

from show_file import ShowSettings
from ui.fonts import mono_font, sans_font

APP_NAME  = "ØJE CUE MONITOR"
COPYRIGHT = "© 2026 ØJE Studio"


class _PerfVUMeter(QWidget):
    """5-bar LED-style level meter for the Performance status bar.
    Matches the meter in the main edit window so the operator sees the
    same shape on both screens.
    """
    BARS = 5
    _GREEN  = QColor(75, 195, 115)
    _AMBER  = QColor(225, 135, 48)
    _RED    = QColor(215, 75, 75)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._db = -120.0
        self.setFixedSize(72, 22)

    def set_db(self, db: float):
        self._db = db
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        W, H = self.width(), self.height()
        bw = (W - (self.BARS - 1) * 2) // self.BARS
        # Map -60..0 dBFS onto 0..BARS so the rightmost bar lights only
        # near clipping. Anything quieter than -60 dB is dark.
        norm = max(0.0, min(1.0, (self._db + 60.0) / 60.0))
        lit = int(norm * self.BARS)
        for i in range(self.BARS):
            x = i * (bw + 2)
            if i >= self.BARS - 1:
                c = self._RED if i < lit else QColor(60, 20, 20)
            elif i >= self.BARS - 2:
                c = self._AMBER if i < lit else QColor(55, 40, 15)
            else:
                c = self._GREEN if i < lit else QColor(25, 55, 35)
            p.fillRect(x, 2, bw, H - 4, c)
        p.end()


_CUE_COLORS = {
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


class PerformanceView(QWidget):
    """
    Full-screen show operator view.
    Top: real time clock
    Middle 65%: current cue (group, name, desc, operator columns)
    Bottom 35%: next cue + countdown + next operators
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: #000000;")
        self._logo_pixmap: Optional[QPixmap] = None
        self._operator_names: List[str] = ["Operator 1"]
        self._settings: Optional[ShowSettings] = None
        self._countdown_enabled: bool = True
        self._signal_ok: bool = False
        self._signal_db: float = -120.0
        self._signal_warning: str = ""
        self._fps: float = 25.0
        self._cues: List = []
        self._current_cue_index: int = -1

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Status bar ───────────────────────────────────────────────────────
        time_bar = QWidget()
        time_bar.setFixedHeight(54)
        time_bar.setStyleSheet("background: #0a0a0a;")
        tb_lay = QHBoxLayout(time_bar)
        tb_lay.setContentsMargins(24, 0, 24, 0)
        tb_lay.setSpacing(10)

        self._signal_dot_lbl = QLabel("●")
        self._signal_dot_lbl.setStyleSheet("color: #d75a5a; font-size: 18px;")
        tb_lay.addStretch()
        tb_lay.addWidget(self._signal_dot_lbl, alignment=Qt.AlignmentFlag.AlignVCenter)

        self._tc_header_lbl = QLabel("--:--:--:--")
        self._tc_header_lbl.setFont(mono_font(24, bold=True))
        self._tc_header_lbl.setStyleSheet("color: #f0f0f0;")
        tb_lay.addWidget(self._tc_header_lbl, alignment=Qt.AlignmentFlag.AlignVCenter)

        self._sep_1 = QLabel("|")
        self._sep_1.setStyleSheet("color: #3d3d3d; font-size: 18px;")
        tb_lay.addWidget(self._sep_1, alignment=Qt.AlignmentFlag.AlignVCenter)

        self._fps_lbl = QLabel("FPS 25.00")
        self._fps_lbl.setFont(mono_font(15, bold=True))
        self._fps_lbl.setStyleSheet("color: #858585;")
        tb_lay.addWidget(self._fps_lbl, alignment=Qt.AlignmentFlag.AlignVCenter)

        self._sep_2 = QLabel("|")
        self._sep_2.setStyleSheet("color: #3d3d3d; font-size: 18px;")
        tb_lay.addWidget(self._sep_2, alignment=Qt.AlignmentFlag.AlignVCenter)

        self._signal_state_lbl = QLabel("NO SIGNAL")
        self._signal_state_lbl.setFont(mono_font(15, bold=True))
        tb_lay.addWidget(self._signal_state_lbl, alignment=Qt.AlignmentFlag.AlignVCenter)

        self._sep_level = QLabel("|")
        self._sep_level.setStyleSheet("color: #3d3d3d; font-size: 18px;")
        tb_lay.addWidget(self._sep_level, alignment=Qt.AlignmentFlag.AlignVCenter)

        # Visual VU meter — same style as the meter in the main edit window.
        self._vu = _PerfVUMeter()
        tb_lay.addWidget(self._vu, alignment=Qt.AlignmentFlag.AlignVCenter)

        self._signal_level_lbl = QLabel("−∞ dB")
        self._signal_level_lbl.setFont(mono_font(13, bold=True))
        self._signal_level_lbl.setStyleSheet("color: #7a7a7a;")
        tb_lay.addWidget(self._signal_level_lbl, alignment=Qt.AlignmentFlag.AlignVCenter)

        self._sep_3 = QLabel("|")
        self._sep_3.setStyleSheet("color: #3d3d3d; font-size: 18px;")
        tb_lay.addWidget(self._sep_3, alignment=Qt.AlignmentFlag.AlignVCenter)

        self._clock_lbl = QLabel("")
        self._clock_lbl.setFont(mono_font(24, bold=True))
        self._clock_lbl.setStyleSheet("color: #dcdcdc;")
        tb_lay.addWidget(self._clock_lbl, alignment=Qt.AlignmentFlag.AlignVCenter)
        tb_lay.addStretch()

        root.addWidget(time_bar)

        # ── Current cue (65%) ────────────────────────────────────────────────
        self._curr_w = QWidget()
        self._curr_w.setStyleSheet("background: #090909;")
        curr_lay = QVBoxLayout(self._curr_w)
        curr_lay.setContentsMargins(64, 24, 64, 16)
        curr_lay.setSpacing(8)

        # top row: tag + group + logo
        top_row = QHBoxLayout()
        top_row.setSpacing(12)

        self._curr_tag = QLabel("CURRENT CUE")
        self._curr_tag.setStyleSheet(
            "color: #4a4a4a; font-size: 11px; font-weight: bold; letter-spacing: 3px;"
        )
        top_row.addWidget(self._curr_tag)

        self._curr_group = QLabel("")
        self._curr_group.setStyleSheet(
            "color: #7a7acd; font-size: 13px; font-weight: bold; letter-spacing: 1px;"
        )
        top_row.addWidget(self._curr_group)
        top_row.addStretch()

        self._logo_lbl = QLabel()
        self._logo_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        self._logo_lbl.setVisible(False)
        top_row.addWidget(self._logo_lbl)

        curr_lay.addLayout(top_row)

        # Cue name
        self._curr_name = QLabel("—")
        self._f_curr_name = sans_font(56, bold=True)
        self._curr_name.setFont(self._f_curr_name)
        self._curr_name.setStyleSheet("color: #ffffff;")
        self._curr_name.setWordWrap(True)
        curr_lay.addWidget(self._curr_name)

        # Cue description
        self._curr_desc = QLabel("")
        self._f_curr_desc = QFont()
        self._f_curr_desc.setPointSize(26)
        self._curr_desc.setFont(self._f_curr_desc)
        self._curr_desc.setStyleSheet("color: #999999;")
        self._curr_desc.setWordWrap(True)
        curr_lay.addWidget(self._curr_desc)

        # Operator columns container
        self._ops_container = QWidget()
        self._ops_container.setStyleSheet("background: transparent;")
        self._ops_hlay = QHBoxLayout(self._ops_container)
        self._ops_hlay.setContentsMargins(0, 12, 0, 0)
        self._ops_hlay.setSpacing(16)
        self._op_widgets: List[_OperatorCard] = []
        curr_lay.addWidget(self._ops_container)

        curr_lay.addStretch()
        root.addWidget(self._curr_w, 65)

        # ── Divider ──────────────────────────────────────────────────────────
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setFixedHeight(2)
        div.setStyleSheet("background: #222222; border: none;")
        root.addWidget(div)

        # ── Next cue (35%) ───────────────────────────────────────────────────
        next_w = QWidget()
        next_w.setStyleSheet("background: #050505;")
        next_lay = QVBoxLayout(next_w)
        next_lay.setContentsMargins(64, 16, 64, 16)
        next_lay.setSpacing(6)

        nr = QHBoxLayout()
        self._next_tag = QLabel("NEXT")
        self._next_tag.setStyleSheet(
            "color: #3a3a3a; font-size: 11px; font-weight: bold; letter-spacing: 3px;"
        )
        nr.addWidget(self._next_tag)

        self._next_group = QLabel("")
        self._next_group.setStyleSheet(
            "color: #4a4a7a; font-size: 11px; font-weight: bold; letter-spacing: 1px;"
        )
        nr.addWidget(self._next_group)
        nr.addStretch()

        self._countdown_lbl = QLabel("")
        self._f_countdown = mono_font(36, bold=True)
        self._countdown_lbl.setFont(self._f_countdown)
        self._countdown_lbl.setStyleSheet("color: #ffffff;")
        nr.addWidget(self._countdown_lbl)

        next_lay.addLayout(nr)

        self._next_name = QLabel("—")
        self._f_next_name = QFont()
        self._f_next_name.setPointSize(30)
        self._f_next_name.setBold(True)
        self._next_name.setFont(self._f_next_name)
        self._next_name.setStyleSheet("color: #cccccc;")
        self._next_name.setWordWrap(True)
        next_lay.addWidget(self._next_name)

        self._next_desc = QLabel("")
        self._f_next_desc = QFont()
        self._f_next_desc.setPointSize(16)
        self._next_desc.setFont(self._f_next_desc)
        self._next_desc.setStyleSheet("color: #555555;")
        self._next_desc.setWordWrap(True)
        next_lay.addWidget(self._next_desc)

        # Next operator comments (compact row)
        self._next_ops_row = QWidget()
        self._next_ops_hlay = QHBoxLayout(self._next_ops_row)
        self._next_ops_hlay.setContentsMargins(0, 6, 0, 0)
        self._next_ops_hlay.setSpacing(20)
        self._next_op_labels: List[QLabel] = []
        next_lay.addWidget(self._next_ops_row)

        next_lay.addStretch()
        root.addWidget(next_w, 35)

        # ── Floating overlays ─────────────────────────────────────────────────
        self._tc_overlay = QLabel("--:--:--:--", self)
        self._tc_overlay.setFont(mono_font(13))
        self._tc_overlay.setStyleSheet("color: #2a2a2a; background: transparent;")
        self._tc_overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._tc_overlay.hide()

        self._esc_hint = QLabel("Esc  —  exit performance mode", self)
        # Two states: bright on mouse activity (and right after entering
        # the view), then fades to a barely-visible dim state ~3 s later
        # so it stays out of the operator's way during the show.
        self._ESC_HINT_BRIGHT = "color: #b0b0b0; font-size: 12px; background: transparent;"
        self._ESC_HINT_DIM    = "color: #2a2a2a; font-size: 11px; background: transparent;"
        self._esc_hint.setStyleSheet(self._ESC_HINT_BRIGHT)
        self._esc_hint.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self._esc_hint_dim_timer = QTimer(self)
        self._esc_hint_dim_timer.setSingleShot(True)
        self._esc_hint_dim_timer.setInterval(3000)
        self._esc_hint_dim_timer.timeout.connect(
            lambda: self._esc_hint.setStyleSheet(self._ESC_HINT_DIM)
        )
        # Listen for mouse movement on the whole view so any operator
        # poke wakes the hint up.
        self.setMouseTracking(True)

        self._copyright_lbl = QLabel(f"{APP_NAME}  {COPYRIGHT}", self)
        self._copyright_lbl.setStyleSheet("color: #1e1e1e; font-size: 11px; background: transparent;")
        self._copyright_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self._cue_overlay = QFrame(self)
        self._cue_overlay.setStyleSheet(
            "QFrame { background: rgba(6, 6, 6, 245); border: 1px solid #1f1f1f; border-radius: 12px; }"
        )
        self._cue_overlay.hide()

        overlay_lay = QVBoxLayout(self._cue_overlay)
        overlay_lay.setContentsMargins(18, 16, 18, 16)
        overlay_lay.setSpacing(12)

        overlay_head = QHBoxLayout()
        overlay_head.setSpacing(10)

        overlay_title = QLabel("FULL CUE LIST")
        overlay_title.setStyleSheet("color: #dcdcdc; font-size: 16px; font-weight: bold; letter-spacing: 2px;")
        overlay_head.addWidget(overlay_title)
        overlay_head.addStretch()

        self._cue_overlay_close_btn = QPushButton("Close")
        self._cue_overlay_close_btn.setFixedHeight(30)
        self._cue_overlay_close_btn.setStyleSheet(
            "QPushButton { background: #181818; color: #c8c8c8; border: 1px solid #2a2a2a; border-radius: 6px; padding: 0 12px; }"
        )
        self._cue_overlay_close_btn.clicked.connect(self._hide_cue_overlay)
        overlay_head.addWidget(self._cue_overlay_close_btn)
        overlay_lay.addLayout(overlay_head)

        self._cue_list_widget = QListWidget()
        self._cue_list_widget.setStyleSheet(
            "QListWidget { background: #0d0d0d; color: #d0d0d0; border: 1px solid #1d1d1d; border-radius: 8px; "
            "outline: none; font-size: 16px; }"
            "QListWidget::item { padding: 8px 10px; border-bottom: 1px solid #181818; }"
            "QListWidget::item:selected { background: #214d86; color: #ffffff; }"
        )
        overlay_lay.addWidget(self._cue_list_widget, stretch=1)

        self._cue_list_btn = QPushButton("CUE LIST", self)
        self._cue_list_btn.setFixedHeight(38)
        self._cue_list_btn.setStyleSheet(
            "QPushButton { background: #181818; color: #dcdcdc; border: 1px solid #2a2a2a; "
            "border-radius: 8px; padding: 0 14px; font-size: 12px; font-weight: bold; letter-spacing: 2px; }"
            "QPushButton:hover { background: #222222; }"
            "QPushButton:pressed { background: #101010; }"
        )
        self._cue_list_btn.clicked.connect(self._toggle_cue_overlay)

        # Clock timer
        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._update_clock)
        self._clock_timer.start(1000)
        self._update_clock()

    # ── public API ────────────────────────────────────────────────────────────

    def apply_settings(self, settings: ShowSettings):
        self._settings = settings
        self._operator_names = settings.operator_names
        self._countdown_enabled = settings.countdown_enabled

        # Update fonts
        self._f_curr_name.setPointSize(settings.perf_cue_name_size)
        self._curr_name.setFont(self._f_curr_name)

        self._f_curr_desc.setPointSize(settings.perf_cue_desc_size)
        self._curr_desc.setFont(self._f_curr_desc)

        self._f_next_name.setPointSize(settings.perf_next_name_size)
        self._next_name.setFont(self._f_next_name)

        self._f_next_desc.setPointSize(settings.perf_next_desc_size)
        self._next_desc.setFont(self._f_next_desc)

        self._f_countdown.setPointSize(settings.perf_countdown_size)
        self._countdown_lbl.setFont(self._f_countdown)

        # Rebuild operator cards
        self._rebuild_operator_cards()

    def set_logo(self, pixmap: Optional[QPixmap]):
        self._logo_pixmap = pixmap
        if pixmap and not pixmap.isNull():
            scaled = pixmap.scaledToHeight(72, Qt.TransformationMode.SmoothTransformation)
            self._logo_lbl.setPixmap(scaled)
            self._logo_lbl.setVisible(True)
        else:
            self._logo_lbl.setVisible(False)

    def update_display(self, current_cue, next_cue, countdown: Optional[float],
                       tc_str: str, current_group: str = "", next_group: str = "",
                       fps: Optional[float] = None, cues: Optional[List] = None):
        self._tc_overlay.setText(tc_str)
        self._tc_header_lbl.setText(tc_str)
        if fps is not None:
            self._fps = fps
        self._fps_lbl.setText(f"FPS {self._fps:.2f}")
        if cues is not None:
            self.set_cues(cues)
        self._curr_group.setText(f"[{current_group}]" if current_group else "")
        self._next_group.setText(f"[{next_group}]" if next_group else "")
        self._current_cue_index = current_cue.index if current_cue else -1
        self._refresh_cue_overlay_selection()

        if current_cue:
            self._curr_name.setText(current_cue.name or "—")
            self._curr_desc.setText(current_cue.description)
            self._update_operator_cards(current_cue)
        else:
            self._curr_name.setText("—")
            self._curr_desc.setText("")
            self._clear_operator_cards()

        if next_cue:
            self._next_name.setText(next_cue.name or "—")
            self._next_desc.setText(next_cue.description)
            self._update_next_ops(next_cue)
        else:
            self._next_name.setText("—")
            self._next_desc.setText("")
            self._clear_next_ops()

        if countdown is not None and self._countdown_enabled:
            m, s = divmod(int(countdown), 60)
            color = "#dc4040" if countdown < 10 else "#ffffff"
            self._countdown_lbl.setText(f"{m:02d}:{s:02d}")
            self._countdown_lbl.setStyleSheet(f"color: {color};")
        else:
            self._countdown_lbl.setText("")

    def update_signal_state(self, signal_ok: bool, db: float, warning: str = ""):
        self._signal_ok = signal_ok
        self._signal_db = db
        self._signal_warning = warning

        if db <= -120:
            db_text = "−∞ dB"
        else:
            db_text = f"{db:.1f} dB"
        self._signal_level_lbl.setText(db_text)
        self._vu.set_db(db)

        if warning == "Clipping!":
            state_text = "CLIPPING"
            state_color = "#dc4040"
            level_color = "#dc4040"
            dot_color = "#dc4040"
        elif warning == "Weak signal":
            state_text = "WEAK"
            state_color = "#d6a638"
            level_color = "#d6a638"
            dot_color = "#d6a638"
        elif signal_ok:
            state_text = "LIVE"
            state_color = "#4bc373"
            level_color = "#dcdcdc"
            dot_color = "#4bc373"
        else:
            state_text = "NO SIGNAL"
            state_color = "#d75a5a"
            level_color = "#7a7a7a"
            dot_color = "#d75a5a"

        self._signal_state_lbl.setText(state_text)
        self._signal_state_lbl.setStyleSheet(f"color: {state_color};")
        self._signal_level_lbl.setStyleSheet(f"color: {level_color};")
        self._signal_dot_lbl.setStyleSheet(f"color: {dot_color}; font-size: 18px;")

    def set_cues(self, cues: List):
        self._cues = list(cues)
        self._cue_list_widget.clear()
        for cue in self._cues:
            if getattr(cue, "is_divider", False):
                text = f"[SECTION] {cue.name}"
            else:
                tc = cue.timecode or "--:--:--:--"
                text = f"{tc}   {cue.name or '—'}"
            item = QListWidgetItem(text)
            if getattr(cue, "is_divider", False):
                # Tan / amber to distinguish section dividers from
                # operator labels (which are purple #7a7acd elsewhere).
                item.setForeground(QColor("#dcc88a"))
                item.setBackground(QColor("#231e14"))
                f = item.font()
                f.setBold(True)
                item.setFont(f)
            elif getattr(cue, "color", ""):
                cue_color = _named_color(getattr(cue, "color", ""))
                if cue_color is not None:
                    # Background: dark version of the cue colour, still
                    # recognisable. darker(260) used to render almost black.
                    bg = cue_color.darker(170)
                    item.setBackground(bg)
                    item.setForeground(QColor("#ffffff"))
                    # Plus a saturated swatch icon on the left so the colour
                    # reads even when the operator skims the list quickly.
                    item.setIcon(_swatch_icon(cue_color))
            self._cue_list_widget.addItem(item)
        self._refresh_cue_overlay_selection()

    # ── internal ──────────────────────────────────────────────────────────────

    def _update_clock(self):
        now = datetime.now().strftime("%H:%M:%S")
        self._clock_lbl.setText(now)

    def _rebuild_operator_cards(self):
        # Clear existing
        for card in self._op_widgets:
            card.setParent(None)
            card.deleteLater()
        self._op_widgets.clear()

        op_size = self._settings.perf_operator_size if self._settings else 20
        name_size = self._settings.perf_operator_name_size if self._settings else 12

        for name in self._operator_names:
            card = _OperatorCard(name, op_size, name_size)
            self._ops_hlay.addWidget(card)
            self._op_widgets.append(card)

        # Next ops labels
        for lbl in self._next_op_labels:
            lbl.setParent(None)
            lbl.deleteLater()
        self._next_op_labels.clear()

        for name in self._operator_names:
            lbl = QLabel()
            f = QFont(); f.setPointSize(14); f.setItalic(True)
            lbl.setFont(f)
            lbl.setStyleSheet("color: #e6c840;")
            lbl.setWordWrap(True)
            self._next_ops_hlay.addWidget(lbl)
            self._next_op_labels.append(lbl)

    def _update_operator_cards(self, cue):
        comments = cue.operator_comments if hasattr(cue, "operator_comments") else {}
        for card in self._op_widgets:
            comment = comments.get(card.op_name, "")
            card.set_comment(comment)

    def _clear_operator_cards(self):
        for card in self._op_widgets:
            card.set_comment("")

    def _update_next_ops(self, cue):
        comments = cue.operator_comments if hasattr(cue, "operator_comments") else {}
        for i, lbl in enumerate(self._next_op_labels):
            if i < len(self._operator_names):
                name = self._operator_names[i]
                comment = comments.get(name, "")
                if comment:
                    lbl.setText(f"{name}:\n{comment}")
                    lbl.setVisible(True)
                else:
                    lbl.setVisible(False)
            else:
                lbl.setVisible(False)

    def _clear_next_ops(self):
        for lbl in self._next_op_labels:
            lbl.setVisible(False)

    def _toggle_cue_overlay(self):
        if self._cue_overlay.isVisible():
            self._hide_cue_overlay()
        else:
            self._show_cue_overlay()

    def _show_cue_overlay(self):
        self._refresh_cue_overlay_selection()
        self._cue_overlay.show()
        self._cue_overlay.raise_()

    def _hide_cue_overlay(self):
        self._cue_overlay.hide()

    def _refresh_cue_overlay_selection(self):
        row = self._current_cue_index - 1 if self._current_cue_index > 0 else -1
        self._cue_list_widget.blockSignals(True)
        self._cue_list_widget.clearSelection()
        if 0 <= row < self._cue_list_widget.count():
            item = self._cue_list_widget.item(row)
            item.setSelected(True)
            self._cue_list_widget.scrollToItem(item, QListWidget.ScrollHint.PositionAtCenter)
        self._cue_list_widget.blockSignals(False)

    # ── Esc hint visibility ───────────────────────────────────────────────────

    def _wake_esc_hint(self):
        """Brighten the hint and (re)start the fade-to-dim timer."""
        if hasattr(self, "_esc_hint"):
            self._esc_hint.setStyleSheet(self._ESC_HINT_BRIGHT)
            self._esc_hint_dim_timer.start()

    def showEvent(self, event):
        super().showEvent(event)
        # Welcome the operator into perf mode with the hint clearly
        # readable; it'll fade after a few seconds.
        self._wake_esc_hint()

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        self._wake_esc_hint()

    # ── layout ────────────────────────────────────────────────────────────────

    def resizeEvent(self, event):
        super().resizeEvent(event)
        W, H = self.width(), self.height()

        self._tc_overlay.adjustSize()
        self._tc_overlay.move(W - self._tc_overlay.width() - 16, H - self._tc_overlay.height() - 14)

        self._esc_hint.adjustSize()
        self._esc_hint.move(16, H - self._esc_hint.height() - 14)

        self._copyright_lbl.adjustSize()
        self._copyright_lbl.move(
            (W - self._copyright_lbl.width()) // 2,
            H - self._copyright_lbl.height() - 14,
        )

        overlay_w = min(760, max(420, W - 140))
        overlay_h = min(720, max(260, H - 140))
        self._cue_overlay.setGeometry(
            (W - overlay_w) // 2,
            (H - overlay_h) // 2,
            overlay_w,
            overlay_h,
        )

        self._cue_list_btn.adjustSize()
        self._cue_list_btn.move(
            W - self._cue_list_btn.width() - 20,
            H - self._cue_list_btn.height() - 20,
        )


# ── Operator card widget ──────────────────────────────────────────────────────

class _OperatorCard(QWidget):
    """A single operator column card with name header + comment."""

    def __init__(self, op_name: str, font_size: int = 20, name_size: int = 12, parent=None):
        super().__init__(parent)
        self.op_name = op_name
        self.setStyleSheet(
            "background: #111118; border-radius: 8px;"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(4)

        self._name_lbl = QLabel(op_name)
        f_name = QFont()
        f_name.setPointSize(name_size)
        f_name.setBold(True)
        self._name_lbl.setFont(f_name)
        self._name_lbl.setStyleSheet(
            "color: #7a7acd; letter-spacing: 1px; background: transparent;"
        )
        lay.addWidget(self._name_lbl)

        self._comment_lbl = QLabel("")
        f_comment = QFont()
        f_comment.setPointSize(font_size)
        self._comment_lbl.setFont(f_comment)
        self._comment_lbl.setStyleSheet("color: #e6c840; background: transparent;")
        self._comment_lbl.setWordWrap(True)
        lay.addWidget(self._comment_lbl)

        lay.addStretch()

    def set_comment(self, text: str):
        self._comment_lbl.setText(text)
        self.setVisible(bool(text))


def _named_color(name: str) -> Optional[QColor]:
    value = _CUE_COLORS.get(name.lower().strip())
    return QColor(value) if value else None


def _swatch_icon(color: QColor, size: int = 14) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QBrush(color))
    p.setPen(QPen(QColor(0, 0, 0, 80), 1))
    p.drawRoundedRect(1, 1, size - 2, size - 2, 3, 3)
    p.end()
    return QIcon(pm)
