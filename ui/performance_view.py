from __future__ import annotations
from typing import Optional, List, Dict
from datetime import datetime

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QPixmap

from show_file import ShowSettings

APP_NAME  = "ØJE CUE MONITOR"
COPYRIGHT = "© 2026 ØJE Studio"


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

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Real time bar ────────────────────────────────────────────────────
        time_bar = QWidget()
        time_bar.setFixedHeight(36)
        time_bar.setStyleSheet("background: #0a0a0a;")
        tb_lay = QHBoxLayout(time_bar)
        tb_lay.setContentsMargins(20, 0, 20, 0)

        self._clock_lbl = QLabel("")
        f_clock = QFont("Menlo"); f_clock.setPointSize(14); f_clock.setBold(True)
        self._clock_lbl.setFont(f_clock)
        self._clock_lbl.setStyleSheet("color: #555555;")
        self._clock_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tb_lay.addStretch()
        tb_lay.addWidget(self._clock_lbl)
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
        self._f_curr_name = QFont("Helvetica Neue")
        self._f_curr_name.setPointSize(56)
        self._f_curr_name.setBold(True)
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
        self._f_countdown = QFont("Menlo")
        self._f_countdown.setPointSize(36)
        self._f_countdown.setBold(True)
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
        f_tc = QFont("Menlo"); f_tc.setPointSize(13)
        self._tc_overlay.setFont(f_tc)
        self._tc_overlay.setStyleSheet("color: #2a2a2a; background: transparent;")
        self._tc_overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self._esc_hint = QLabel("Esc  —  exit performance mode", self)
        self._esc_hint.setStyleSheet("color: #1e1e1e; font-size: 11px; background: transparent;")
        self._esc_hint.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self._copyright_lbl = QLabel(f"{APP_NAME}  {COPYRIGHT}", self)
        self._copyright_lbl.setStyleSheet("color: #1e1e1e; font-size: 11px; background: transparent;")
        self._copyright_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

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
                       tc_str: str, current_group: str = "", next_group: str = ""):
        self._tc_overlay.setText(tc_str)
        self._curr_group.setText(f"[{current_group}]" if current_group else "")
        self._next_group.setText(f"[{next_group}]" if next_group else "")

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
                    lbl.setText(f"{name}: {comment}")
                    lbl.setVisible(True)
                else:
                    lbl.setVisible(False)
            else:
                lbl.setVisible(False)

    def _clear_next_ops(self):
        for lbl in self._next_op_labels:
            lbl.setVisible(False)

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
