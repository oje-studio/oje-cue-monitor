"""
Performance View — fullscreen operator display.

Top: large wall clock (size/colour configurable). Middle: current cue
name + description, then operator columns. Bottom: next cue preview.

Minimalist on purpose — this is what the booth/stage sees during a
running show, so legibility beats decoration.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QKeyEvent
from PyQt6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget,
)

from ..scene_model import SceneCue, ShowSettings


BG = "#050505"
TEXT_BRIGHT = "#ffffff"
TEXT_DIM = "#666666"
ACCENT_YELLOW = "#e6c840"
ACCENT_RED = "#e05050"


def _mono(size: int) -> QFont:
    f = QFont("Menlo")
    f.setStyleHint(QFont.StyleHint.Monospace)
    f.setPointSize(size)
    return f


class OperatorCard(QFrame):
    def __init__(self, name: str, name_size: int, value_size: int, parent=None):
        super().__init__(parent)
        self.op_name = name
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(4)

        self._lbl_name = QLabel(name.upper())
        f = QFont(); f.setPointSize(name_size); f.setBold(True)
        self._lbl_name.setFont(f)
        self._lbl_name.setStyleSheet("color: #8888cc; letter-spacing: 2px;")
        lay.addWidget(self._lbl_name)

        self._lbl_val = QLabel("")
        vf = QFont(); vf.setPointSize(value_size)
        self._lbl_val.setFont(vf)
        self._lbl_val.setStyleSheet(f"color: {ACCENT_YELLOW};")
        self._lbl_val.setWordWrap(True)
        lay.addWidget(self._lbl_val)
        lay.addStretch()

    def set_value(self, text: str):
        self._lbl_val.setText(text)


class PerformanceView(QWidget):
    """Not a QMainWindow — embedded as a stacked page or shown fullscreen."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"QWidget {{ background: {BG}; color: {TEXT_BRIGHT}; }}")
        self._settings = ShowSettings()
        self._operator_names: list = []
        self._op_cards: list = []

        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(40, 24, 40, 24)
        self._outer.setSpacing(16)

        # ── Top: large clock + drift ─────────────
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)

        self._clock = QLabel("--:--:--")
        self._clock.setAlignment(Qt.AlignmentFlag.AlignCenter)
        top_row.addStretch(1)
        top_row.addWidget(self._clock, 0)
        top_row.addStretch(1)

        self._drift = QLabel("")
        self._drift.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._drift.setStyleSheet(f"color: {TEXT_DIM}; font-size: 14px;")
        self._drift.setFixedWidth(220)
        top_row.addWidget(self._drift)

        self._outer.addLayout(top_row)

        # ── Current cue block ────────────────────
        self._scene_lbl = QLabel("")
        self._scene_lbl.setStyleSheet(f"color: {TEXT_DIM}; font-size: 14px; letter-spacing: 3px;")
        self._outer.addWidget(self._scene_lbl)

        self._cue_name = QLabel("—")
        self._cue_name.setWordWrap(True)
        self._outer.addWidget(self._cue_name)

        self._cue_desc = QLabel("")
        self._cue_desc.setWordWrap(True)
        self._cue_desc.setStyleSheet(f"color: {TEXT_DIM};")
        self._outer.addWidget(self._cue_desc)

        # ── Operator cards grid ─────────────────
        self._ops_container = QWidget()
        self._ops_lay = QGridLayout(self._ops_container)
        self._ops_lay.setContentsMargins(0, 8, 0, 8)
        self._ops_lay.setSpacing(12)
        self._outer.addWidget(self._ops_container, 1)

        # ── Next cue preview ────────────────────
        self._next_row = QHBoxLayout()
        self._next_lbl_hdr = QLabel("NEXT")
        self._next_lbl_hdr.setStyleSheet(f"color: {TEXT_DIM}; font-size: 14px; letter-spacing: 3px;")
        self._next_row.addWidget(self._next_lbl_hdr)
        self._next_row.addSpacing(16)
        self._next_name = QLabel("—")
        self._next_row.addWidget(self._next_name, 1)
        self._countdown = QLabel("")
        self._next_row.addWidget(self._countdown, 0)
        self._outer.addLayout(self._next_row)

        self.apply_settings(self._settings)

    # ── public API ────
    def apply_settings(self, settings: ShowSettings):
        self._settings = settings
        # Clock
        cf = _mono(settings.perf_clock_size)
        cf.setBold(True)
        self._clock.setFont(cf)
        self._clock.setStyleSheet(f"color: {settings.perf_clock_color};")

        # Cue name/desc fonts
        nf = QFont(); nf.setPointSize(settings.perf_cue_name_size); nf.setBold(True)
        self._cue_name.setFont(nf)
        self._cue_name.setStyleSheet(f"color: {TEXT_BRIGHT};")
        df = QFont(); df.setPointSize(settings.perf_cue_desc_size)
        self._cue_desc.setFont(df)

        # Next cue
        nnf = QFont(); nnf.setPointSize(settings.perf_next_name_size); nnf.setBold(True)
        self._next_name.setFont(nnf)
        self._next_name.setStyleSheet(f"color: {TEXT_BRIGHT};")
        cdf = _mono(settings.perf_next_name_size)
        self._countdown.setFont(cdf)
        self._countdown.setStyleSheet(f"color: {ACCENT_YELLOW};")

    def set_operators(self, names: list):
        self._operator_names = list(names)
        # Clear existing
        for card in self._op_cards:
            card.setParent(None)
            card.deleteLater()
        self._op_cards.clear()

        s = self._settings
        cols = max(1, min(4, len(names)))
        for i, name in enumerate(names):
            card = OperatorCard(
                name,
                name_size=s.perf_operator_name_size,
                value_size=s.perf_operator_size,
            )
            self._op_cards.append(card)
            self._ops_lay.addWidget(card, i // cols, i % cols)

    def set_time(self, hms: str):
        self._clock.setText(hms)

    def set_drift(self, drift: Optional[float], threshold: float):
        if drift is None:
            self._drift.setText("NTP: offline")
            self._drift.setStyleSheet(f"color: {TEXT_DIM}; font-size: 14px;")
            return
        if abs(drift) < threshold:
            self._drift.setText(f"NTP ±{abs(drift):.1f}s")
            self._drift.setStyleSheet(f"color: {TEXT_DIM}; font-size: 14px;")
        else:
            sign = "+" if drift >= 0 else "−"
            self._drift.setText(f"DRIFT {sign}{abs(drift):.1f}s")
            self._drift.setStyleSheet(f"color: {ACCENT_RED}; font-size: 16px; font-weight: bold;")

    def show_current(self, scene_name: str, cue: Optional[SceneCue]):
        self._scene_lbl.setText(scene_name.upper() if scene_name else "")
        if cue is None:
            self._cue_name.setText("—")
            self._cue_desc.setText("")
            for card in self._op_cards:
                card.set_value("")
            return
        self._cue_name.setText(cue.name or "—")
        self._cue_desc.setText(cue.description)
        comments = cue.operator_comments or {}
        for card in self._op_cards:
            card.set_value(comments.get(card.op_name, ""))

    def show_next(self, cue: Optional[SceneCue], countdown: Optional[float]):
        if cue is None:
            self._next_name.setText("—")
            self._countdown.setText("")
            return
        self._next_name.setText(cue.name or "—")
        if countdown is None:
            self._countdown.setText("")
        else:
            m, s = divmod(int(countdown), 60)
            self._countdown.setText(f"{m:02d}:{s:02d}")
            if countdown < 10:
                self._countdown.setStyleSheet(f"color: {ACCENT_RED};")
            else:
                self._countdown.setStyleSheet(f"color: {ACCENT_YELLOW};")

    def keyPressEvent(self, e: QKeyEvent):
        if e.key() == Qt.Key.Key_Escape:
            self.window().close()
        else:
            super().keyPressEvent(e)
