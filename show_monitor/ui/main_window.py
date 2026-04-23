"""
SHOW MONITOR main window.

Layout:
  Top bar      — app title, big wall clock, NTP drift indicator
  Left panel   — scenes list (add/remove/reorder)
  Right panel  — active scene's cue table (add/remove/reorder, edit offsets)
  Bottom panel — current and next cue cards with countdown
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QFont, QKeySequence
from PyQt6.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QFileDialog, QFrame, QHBoxLayout,
    QHeaderView, QInputDialog, QLabel, QLineEdit, QMainWindow, QMenuBar, QMessageBox,
    QPushButton, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from .. import APP_NAME, FILE_EXT, VERSION
from ..engine import Playhead, resolve
from ..scene_model import (
    Scene, SceneCue, Show, ShowSettings, TIME_SOURCES, TIME_SOURCE_LABELS,
    format_offset, parse_offset,
)
from ..show_file import load_show, save_show
from ..world_clock import DriftMonitor, now_hms, now_seconds_of_day
from .performance_view import PerformanceView
from .settings_dialog import SettingsDialog

logger = logging.getLogger(__name__)

# Colour palette mirrors the classic CUE MONITOR so the two apps feel
# like siblings rather than independent tools.
DARK_BG      = "#1c1c1c"
DARK_PANEL   = "#2a2a2a"
DARK_BORDER  = "#3a3a3a"
TEXT_BRIGHT  = "#dadada"
TEXT_DIM     = "#878787"
ACCENT_BLUE   = "#3773c3"
ACCENT_YELLOW = "#e1c337"
ACCENT_RED    = "#d74b4b"
ACCENT_GREEN  = "#4bc373"
ACCENT_ORANGE = "#e18730"
NEAR_BLACK   = "#121212"


def _mono(size: int) -> QFont:
    f = QFont("Menlo")
    f.setStyleHint(QFont.StyleHint.Monospace)
    f.setPointSize(size)
    return f


# ── Top bar with clock + drift indicator ──────────────────────────────────────

class TopBar(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            f"TopBar {{ background: {DARK_PANEL}; border-bottom: 1px solid {DARK_BORDER}; }}"
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 8, 16, 8)

        title = QLabel(f"{APP_NAME}  {VERSION}")
        title.setStyleSheet(f"color: {TEXT_DIM}; font-size: 12px; letter-spacing: 2px;")
        lay.addWidget(title)

        lay.addStretch()

        self.clock = QLabel("--:--:--")
        self.clock.setFont(_mono(36))
        self.clock.setStyleSheet(f"color: {TEXT_BRIGHT};")
        lay.addWidget(self.clock)

        lay.addStretch()

        self.drift = QLabel("NTP checking…")
        self.drift.setStyleSheet(f"color: {TEXT_DIM}; font-size: 11px;")
        lay.addWidget(self.drift)

    def set_time(self, hms: str):
        self.clock.setText(hms)

    def set_drift(self, drift: Optional[float], threshold: float):
        if drift is None:
            self.drift.setText("NTP: no internet")
            self.drift.setStyleSheet(f"color: {TEXT_DIM}; font-size: 11px;")
            return
        ok = abs(drift) < threshold
        color = ACCENT_GREEN if ok else ACCENT_RED
        sign = "+" if drift >= 0 else "−"
        self.drift.setText(f"NTP drift: {sign}{abs(drift):.2f}s")
        self.drift.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: bold;")


# ── Scenes list ───────────────────────────────────────────────────────────────

SCENE_COL_NAME, SCENE_COL_START, SCENE_COL_SOURCE = 0, 1, 2
SCENE_HEADERS = ["Scene Name", "Start Time", "Source"]


class ScenesPanel(QFrame):
    """
    Scene editor. Inline editing for name + start time; time source via
    a combobox. Selection drives which scene's cues are shown on the
    right; the "active" scene (current playhead) is highlighted green.
    """
    scene_selected = pyqtSignal(int)
    scene_add = pyqtSignal()
    scene_remove = pyqtSignal(int)
    scene_field_changed = pyqtSignal(int, str, str)  # row, field, value

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            f"ScenesPanel {{ background: {DARK_PANEL}; border-right: 1px solid {DARK_BORDER}; }}"
        )

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        hdr = QLabel("SCENES")
        hdr.setStyleSheet(f"color: {ACCENT_BLUE}; font-size: 11px; font-weight: bold; letter-spacing: 2px;")
        lay.addWidget(hdr)

        self._table = QTableWidget(0, len(SCENE_HEADERS))
        self._table.setHorizontalHeaderLabels(SCENE_HEADERS)
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setStyleSheet(
            f"QTableWidget {{ background: {DARK_BG}; color: {TEXT_BRIGHT};"
            f" gridline-color: {DARK_BORDER}; border: 1px solid {DARK_BORDER}; }}"
            f"QHeaderView::section {{ background: {DARK_PANEL}; color: {TEXT_DIM};"
            f" border: none; padding: 4px 8px; font-weight: bold; font-size: 10px; letter-spacing: 1px; }}"
            f"QTableWidget::item:selected {{ background: {ACCENT_BLUE}; color: white; }}"
        )
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(SCENE_COL_NAME, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(SCENE_COL_START, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(SCENE_COL_SOURCE, QHeaderView.ResizeMode.ResizeToContents)

        self._table.itemChanged.connect(self._on_item_changed)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        lay.addWidget(self._table, 1)

        btn_row = QHBoxLayout()
        add = QPushButton("+ Scene")
        add.clicked.connect(self.scene_add.emit)
        rm = QPushButton("− Scene")
        rm.clicked.connect(self._on_remove)
        btn_row.addWidget(add)
        btn_row.addWidget(rm)
        lay.addLayout(btn_row)

    # ── public API ────
    def set_scenes(self, scenes):
        """Full rebuild — call only when the scenes list itself changes."""
        prev = self._table.currentRow()
        self._table.blockSignals(True)
        self._table.setRowCount(len(scenes))
        for i, sc in enumerate(scenes):
            name_item = QTableWidgetItem(sc.name or "")
            start_item = QTableWidgetItem(sc.start_time or "00:00:00")
            start_item.setFont(_mono(11))
            src_item = QTableWidgetItem("")
            src_item.setFlags(src_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

            self._table.setItem(i, SCENE_COL_NAME, name_item)
            self._table.setItem(i, SCENE_COL_START, start_item)
            self._table.setItem(i, SCENE_COL_SOURCE, src_item)

            combo = QComboBox()
            for src in TIME_SOURCES:
                combo.addItem(TIME_SOURCE_LABELS[src], src)
            idx = next((k for k, s in enumerate(TIME_SOURCES) if s == sc.time_source), 0)
            combo.setCurrentIndex(idx)
            combo.currentIndexChanged.connect(
                lambda _idx, row=i, c=combo: self.scene_field_changed.emit(
                    row, "time_source", c.currentData()
                )
            )
            self._table.setCellWidget(i, SCENE_COL_SOURCE, combo)

        if 0 <= prev < len(scenes):
            self._table.selectRow(prev)
        elif scenes:
            self._table.selectRow(0)
        self._table.blockSignals(False)

    def mark_active(self, active_index: Optional[int]):
        """Light touch — just restyles existing rows. Safe to call on every tick."""
        for row in range(self._table.rowCount()):
            is_active = (row == active_index)
            for col in (SCENE_COL_NAME, SCENE_COL_START):
                it = self._table.item(row, col)
                if not it:
                    continue
                it.setForeground(QColor(ACCENT_GREEN) if is_active else QColor(TEXT_BRIGHT))
                f = it.font(); f.setBold(is_active); it.setFont(f)

    def current_row(self) -> int:
        return self._table.currentRow()

    def select_row(self, row: int):
        if 0 <= row < self._table.rowCount():
            self._table.selectRow(row)

    # ── signals ────
    def _on_item_changed(self, item: QTableWidgetItem):
        row, col = item.row(), item.column()
        text = item.text().strip()
        if col == SCENE_COL_NAME:
            self.scene_field_changed.emit(row, "name", text)
        elif col == SCENE_COL_START:
            # Light validation: accept HH:MM:SS, otherwise revert
            ok = False
            if text.count(":") == 2:
                try:
                    h, m, s = (int(x) for x in text.split(":"))
                    ok = 0 <= h <= 23 and 0 <= m <= 59 and 0 <= s <= 59
                except ValueError:
                    ok = False
            if not ok:
                self._table.blockSignals(True)
                item.setText("00:00:00")
                self._table.blockSignals(False)
                text = "00:00:00"
            self.scene_field_changed.emit(row, "start_time", text)

    def _on_selection_changed(self):
        self.scene_selected.emit(self._table.currentRow())

    def _on_remove(self):
        r = self._table.currentRow()
        if r >= 0:
            self.scene_remove.emit(r)


# ── Cue table ─────────────────────────────────────────────────────────────────

COL_OFFSET, COL_NAME, COL_DESC, COL_OPS = 0, 1, 2, 3
COL_HEADERS = ["Offset", "Name", "Description", "Operator notes"]


class CueTable(QTableWidget):
    cue_changed = pyqtSignal(int, str, str)  # row, field, value

    def __init__(self, parent=None):
        super().__init__(0, len(COL_HEADERS), parent)
        self.setHorizontalHeaderLabels(COL_HEADERS)
        self.setStyleSheet(
            f"QTableWidget {{ background: {DARK_BG}; color: {TEXT_BRIGHT};"
            f" gridline-color: {DARK_BORDER}; border: 1px solid {DARK_BORDER}; }}"
            f"QHeaderView::section {{ background: {DARK_PANEL}; color: {TEXT_DIM};"
            f" border: none; padding: 4px 8px; font-weight: bold; font-size: 10px; letter-spacing: 1px; }}"
            f"QTableWidget::item:selected {{ background: {ACCENT_BLUE}; color: white; }}"
        )
        self.verticalHeader().setVisible(False)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.horizontalHeader().setSectionResizeMode(COL_OFFSET, QHeaderView.ResizeMode.ResizeToContents)
        self.horizontalHeader().setSectionResizeMode(COL_NAME, QHeaderView.ResizeMode.Interactive)
        self.horizontalHeader().setSectionResizeMode(COL_DESC, QHeaderView.ResizeMode.Stretch)
        self.horizontalHeader().setSectionResizeMode(COL_OPS, QHeaderView.ResizeMode.Interactive)
        self.setColumnWidth(COL_NAME, 200)
        self.setColumnWidth(COL_OPS, 240)

        self._cues: list = []
        self._current_cue_row: Optional[int] = None
        self.itemChanged.connect(self._on_item_changed)

    def load_cues(self, cues, operator_names):
        self._cues = cues
        self.blockSignals(True)
        self.setRowCount(len(cues))
        for row, cue in enumerate(cues):
            self._set_item(row, COL_OFFSET, format_offset(cue.offset), mono=True)
            self._set_item(row, COL_NAME, cue.name)
            self._set_item(row, COL_DESC, cue.description)
            op_text = ", ".join(
                f"{n}: {cue.operator_comments[n]}"
                for n in operator_names if cue.operator_comments.get(n)
            )
            self._set_item(row, COL_OPS, op_text)
        self.blockSignals(False)
        self._apply_highlight()

    def mark_current(self, row: Optional[int]):
        self._current_cue_row = row
        self._apply_highlight()

    def _apply_highlight(self):
        for r in range(self.rowCount()):
            for c in range(self.columnCount()):
                it = self.item(r, c)
                if not it:
                    continue
                if r == self._current_cue_row:
                    it.setBackground(QColor(50, 80, 50))
                else:
                    it.setBackground(QColor(DARK_BG))

    def _set_item(self, row, col, text, mono=False):
        it = QTableWidgetItem(text or "")
        if mono:
            it.setFont(_mono(11))
        if col == COL_OPS:
            it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.setItem(row, col, it)

    def _on_item_changed(self, item: QTableWidgetItem):
        row, col = item.row(), item.column()
        text = item.text()
        if col == COL_OFFSET:
            val = parse_offset(text)
            if val is None:
                # Revert to stored value
                self.blockSignals(True)
                item.setText(format_offset(self._cues[row].offset))
                self.blockSignals(False)
                return
            self.cue_changed.emit(row, "offset", str(val))
        elif col == COL_NAME:
            self.cue_changed.emit(row, "name", text)
        elif col == COL_DESC:
            self.cue_changed.emit(row, "description", text)


# ── Current / Next card ───────────────────────────────────────────────────────

class CueCard(QFrame):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            f"CueCard {{ background: {DARK_PANEL}; border: 1px solid {DARK_BORDER}; border-radius: 6px; }}"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(4)

        tl = QLabel(title.upper())
        tl.setStyleSheet(f"color: {TEXT_DIM}; font-size: 11px; font-weight: bold; letter-spacing: 2px;")
        lay.addWidget(tl)

        self.name_lbl = QLabel("—")
        nf = QFont(); nf.setPointSize(20); nf.setBold(True)
        self.name_lbl.setFont(nf)
        self.name_lbl.setStyleSheet(f"color: {TEXT_BRIGHT};")
        self.name_lbl.setWordWrap(True)
        lay.addWidget(self.name_lbl)

        self.desc_lbl = QLabel("")
        self.desc_lbl.setStyleSheet(f"color: {TEXT_DIM}; font-size: 13px;")
        self.desc_lbl.setWordWrap(True)
        lay.addWidget(self.desc_lbl)

        self.ops_lbl = QLabel("")
        self.ops_lbl.setStyleSheet(f"color: {ACCENT_YELLOW}; font-size: 12px;")
        self.ops_lbl.setWordWrap(True)
        lay.addWidget(self.ops_lbl)

        self.cd_lbl = QLabel("")
        self.cd_lbl.setFont(_mono(16))
        self.cd_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        lay.addWidget(self.cd_lbl)

        lay.addStretch()

    def show_cue(self, cue: Optional[SceneCue], operator_names, countdown: Optional[float] = None):
        if cue is None:
            self.name_lbl.setText("—")
            self.desc_lbl.setText("")
            self.ops_lbl.setText("")
            self.cd_lbl.setText("")
            return
        self.name_lbl.setText(cue.name or "—")
        self.desc_lbl.setText(cue.description)
        ops = cue.operator_comments or {}
        lines = [f"{n}: {ops[n]}" for n in operator_names if ops.get(n)]
        self.ops_lbl.setText("\n".join(lines))
        if countdown is not None:
            m, s = divmod(int(countdown), 60)
            color = ACCENT_RED if countdown < 10 else TEXT_BRIGHT
            self.cd_lbl.setText(f"in {m:02d}:{s:02d}")
            self.cd_lbl.setStyleSheet(f"color: {color}; font-size: 16px;")
        else:
            self.cd_lbl.setText("")


# ── Main window ───────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME}  {VERSION}")
        self.resize(1280, 800)
        self.setStyleSheet(f"QMainWindow {{ background: {DARK_BG}; }}")

        self._show = Show()
        self._file_path: Optional[str] = None
        self._dirty = False
        self._active_scene_row = 0

        self._drift = DriftMonitor()
        self._drift.start()

        self._perf_view: Optional[PerformanceView] = None

        # ── Layout ────
        central = QWidget()
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._topbar = TopBar()
        outer.addWidget(self._topbar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(splitter, 1)

        self._scenes_panel = ScenesPanel()
        self._scenes_panel.scene_selected.connect(self._on_scene_selected)
        self._scenes_panel.scene_add.connect(self._on_scene_add)
        self._scenes_panel.scene_remove.connect(self._on_scene_remove)
        self._scenes_panel.scene_field_changed.connect(self._on_scene_field_changed)
        splitter.addWidget(self._scenes_panel)

        right = QWidget()
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(8, 8, 8, 8)
        right_lay.setSpacing(6)

        cue_hdr_row = QHBoxLayout()
        cue_hdr = QLabel("CUES")
        cue_hdr.setStyleSheet(f"color: {ACCENT_BLUE}; font-size: 11px; font-weight: bold; letter-spacing: 2px;")
        cue_hdr_row.addWidget(cue_hdr)
        cue_hdr_row.addStretch()
        self._btn_add_cue = QPushButton("+ Cue")
        self._btn_add_cue.clicked.connect(self._on_cue_add)
        self._btn_del_cue = QPushButton("− Cue")
        self._btn_del_cue.clicked.connect(self._on_cue_delete)
        cue_hdr_row.addWidget(self._btn_add_cue)
        cue_hdr_row.addWidget(self._btn_del_cue)
        right_lay.addLayout(cue_hdr_row)

        self._table = CueTable()
        self._table.cue_changed.connect(self._on_cue_changed)
        right_lay.addWidget(self._table, 1)

        cards_row = QHBoxLayout()
        self._current_card = CueCard("Current Cue")
        self._next_card = CueCard("Next Cue")
        cards_row.addWidget(self._current_card, 1)
        cards_row.addWidget(self._next_card, 1)
        right_lay.addLayout(cards_row)

        splitter.addWidget(right)
        splitter.setSizes([260, 1020])

        self.setCentralWidget(central)

        self._build_menu()

        # ── Tick ────
        self._tick_timer = QTimer(self)
        self._tick_timer.timeout.connect(self._on_tick)
        self._tick_timer.start(200)

    # ── menu ────
    def _build_menu(self):
        mb = self.menuBar()
        f = mb.addMenu("&File")
        a_new = QAction("New Show", self)
        a_new.setShortcut(QKeySequence.StandardKey.New)
        a_new.triggered.connect(self._on_new)
        f.addAction(a_new)
        a_open = QAction("Open…", self)
        a_open.setShortcut(QKeySequence.StandardKey.Open)
        a_open.triggered.connect(self._on_open)
        f.addAction(a_open)
        a_save = QAction("Save", self)
        a_save.setShortcut(QKeySequence.StandardKey.Save)
        a_save.triggered.connect(self._on_save)
        f.addAction(a_save)
        a_save_as = QAction("Save As…", self)
        a_save_as.setShortcut(QKeySequence.StandardKey.SaveAs)
        a_save_as.triggered.connect(self._on_save_as)
        f.addAction(a_save_as)

        v = mb.addMenu("&View")
        a_perf = QAction("Performance Mode", self)
        a_perf.setShortcut("P")
        a_perf.triggered.connect(self._toggle_performance)
        v.addAction(a_perf)

        s = mb.addMenu("&Settings")
        a_settings = QAction("Show Settings…", self)
        a_settings.setShortcut("Ctrl+,")
        a_settings.triggered.connect(self._open_settings)
        s.addAction(a_settings)

    # ── tick ────
    def _on_tick(self):
        hms = now_hms()
        self._topbar.set_time(hms)

        drift_state = self._drift.state()
        self._topbar.set_drift(drift_state["drift"], self._show.settings.drift_warning_seconds)

        ph = resolve(self._show, now_seconds_of_day())
        self._update_cards(ph)
        # Light-weight: just re-styles existing rows, doesn't touch editable
        # cells or rebuild the table (won't interrupt inline edits).
        self._scenes_panel.mark_active(ph.current_scene_index)

        cur_row = None
        if ph.current_cue and ph.current_cue.scene_index == self._active_scene_row:
            cur_row = ph.current_cue.cue_index
        self._table.mark_current(cur_row)

    def _update_cards(self, ph: Playhead):
        ops = self._show.settings.operator_names
        cur_scene = ph.current_cue.resolve(self._show)[0] if ph.current_cue else None
        cur_cue = ph.current_cue.resolve(self._show)[1] if ph.current_cue else None
        nxt_cue = ph.next_cue.resolve(self._show)[1] if ph.next_cue else None
        self._current_card.show_cue(cur_cue, ops)
        self._next_card.show_cue(nxt_cue, ops, ph.countdown())

        if self._perf_view is not None:
            self._perf_view.set_time(now_hms())
            drift_state = self._drift.state()
            self._perf_view.set_drift(drift_state["drift"], self._show.settings.drift_warning_seconds)
            self._perf_view.show_current(cur_scene.name if cur_scene else "", cur_cue)
            self._perf_view.show_next(nxt_cue, ph.countdown())

    def _open_settings(self):
        dlg = SettingsDialog(self._show.settings, self)
        if dlg.exec():
            new = dlg.get_settings()
            if new is not None:
                self._show.settings = new
                self._apply_settings()
                self._mark_dirty()

    def _apply_settings(self):
        """Push settings changes into all widgets that care about them."""
        s = self._show.settings
        # Re-render cue cards so operator list changes show up immediately.
        # Scene panel and cue table rebuilds happen via _reload_scenes.
        if self._perf_view is not None:
            self._perf_view.apply_settings(s)
            self._perf_view.set_operators(s.operator_names)
        self._reload_scenes()

    def _toggle_performance(self):
        if self._perf_view is not None:
            self._perf_view.close()
            self._perf_view = None
            return
        self._perf_view = PerformanceView()
        self._perf_view.apply_settings(self._show.settings)
        self._perf_view.set_operators(self._show.settings.operator_names)
        self._perf_view.setWindowTitle(f"{APP_NAME} — Performance")
        self._perf_view.destroyed.connect(self._on_perf_closed)
        self._perf_view.showFullScreen()

    def _on_perf_closed(self):
        self._perf_view = None

    # ── scene handlers ────
    def _on_scene_selected(self, row: int):
        if row < 0 or row >= len(self._show.scenes):
            return
        self._active_scene_row = row
        self._table.load_cues(self._show.scenes[row].cues, self._show.settings.operator_names)

    def _on_scene_add(self):
        # Direct append with sensible defaults — the user edits fields inline
        # in the table rather than going through a modal dialog.
        default_name = f"Scene {len(self._show.scenes) + 1}"
        self._show.scenes.append(Scene(name=default_name, start_time=now_hms()))
        self._active_scene_row = len(self._show.scenes) - 1
        self._reload_scenes()
        self._mark_dirty()

    def _on_scene_remove(self, row: int):
        if not (0 <= row < len(self._show.scenes)):
            return
        name = self._show.scenes[row].name or f"scene {row + 1}"
        if QMessageBox.question(self, "Delete scene", f"Delete «{name}»?") != QMessageBox.StandardButton.Yes:
            return
        del self._show.scenes[row]
        self._active_scene_row = max(0, min(self._active_scene_row, len(self._show.scenes) - 1))
        self._reload_scenes()
        self._mark_dirty()

    def _on_scene_field_changed(self, row: int, field: str, value: str):
        if not (0 <= row < len(self._show.scenes)):
            return
        sc = self._show.scenes[row]
        if field == "name":
            sc.name = value
        elif field == "start_time":
            sc.start_time = value
        elif field == "time_source":
            sc.time_source = value
        self._mark_dirty()

    def _reload_scenes(self):
        self._scenes_panel.set_scenes(self._show.scenes)
        if self._show.scenes:
            self._scenes_panel.select_row(self._active_scene_row)
            self._table.load_cues(
                self._show.scenes[self._active_scene_row].cues,
                self._show.settings.operator_names,
            )
        else:
            self._table.load_cues([], self._show.settings.operator_names)

    # ── cue handlers ────
    def _on_cue_add(self):
        if not self._show.scenes:
            QMessageBox.information(self, "No scene", "Add a scene first.")
            return
        sc = self._show.scenes[self._active_scene_row]
        sc.cues.append(SceneCue(offset=0.0, name="New cue"))
        self._table.load_cues(sc.cues, self._show.settings.operator_names)
        self._mark_dirty()

    def _on_cue_delete(self):
        row = self._table.currentRow()
        if not self._show.scenes or row < 0:
            return
        sc = self._show.scenes[self._active_scene_row]
        if row >= len(sc.cues):
            return
        del sc.cues[row]
        self._table.load_cues(sc.cues, self._show.settings.operator_names)
        self._mark_dirty()

    def _on_cue_changed(self, row: int, field: str, value: str):
        if not self._show.scenes:
            return
        sc = self._show.scenes[self._active_scene_row]
        if not (0 <= row < len(sc.cues)):
            return
        cue = sc.cues[row]
        if field == "offset":
            try:
                cue.offset = float(value)
            except ValueError:
                return
        elif field == "name":
            cue.name = value
        elif field == "description":
            cue.description = value
        self._mark_dirty()

    # ── file handlers ────
    def _on_new(self):
        if not self._confirm_discard():
            return
        self._show = Show()
        self._file_path = None
        self._active_scene_row = 0
        self._reload_scenes()
        self._dirty = False
        self._update_title()

    def _on_open(self):
        if not self._confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Open show", "", f"SHOW MONITOR (*{FILE_EXT})"
        )
        if not path:
            return
        try:
            self._show = load_show(path)
        except (ValueError, OSError) as e:
            QMessageBox.critical(self, "Open failed", str(e))
            return
        self._file_path = path
        self._active_scene_row = 0
        self._reload_scenes()
        self._dirty = False
        self._update_title()

    def _on_save(self):
        if not self._file_path:
            self._on_save_as()
            return
        try:
            save_show(self._show, self._file_path)
            self._dirty = False
            self._update_title()
        except OSError as e:
            QMessageBox.critical(self, "Save failed", str(e))

    def _on_save_as(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save show", "", f"SHOW MONITOR (*{FILE_EXT})"
        )
        if not path:
            return
        if not path.endswith(FILE_EXT):
            path += FILE_EXT
        self._file_path = path
        self._on_save()

    def _confirm_discard(self) -> bool:
        if not self._dirty:
            return True
        reply = QMessageBox.question(
            self, "Unsaved changes",
            "Discard unsaved changes?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        return reply == QMessageBox.StandardButton.Yes

    def _mark_dirty(self):
        self._dirty = True
        self._update_title()

    def _update_title(self):
        base = f"{APP_NAME}  {VERSION}"
        name = os.path.basename(self._file_path) if self._file_path else "Untitled"
        self.setWindowTitle(f"{base}  —  {name}{'*' if self._dirty else ''}")

    def closeEvent(self, event):
        self._drift.stop()
        super().closeEvent(event)
