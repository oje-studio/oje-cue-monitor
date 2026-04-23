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
    QAbstractItemView, QApplication, QFileDialog, QFrame, QHBoxLayout, QHeaderView,
    QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow,
    QMenuBar, QMessageBox, QPushButton, QSplitter, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from .. import APP_NAME, FILE_EXT, VERSION
from ..engine import Playhead, resolve
from ..scene_model import Scene, SceneCue, Show, ShowSettings, format_offset, parse_offset
from ..show_file import load_show, save_show
from ..world_clock import DriftMonitor, now_hms, now_seconds_of_day

logger = logging.getLogger(__name__)

DARK_BG = "#101010"
DARK_PANEL = "#1a1a1a"
DARK_BORDER = "#2a2a2a"
TEXT_BRIGHT = "#f0f0f0"
TEXT_DIM = "#888888"
ACCENT_BLUE = "#4a90d9"
ACCENT_YELLOW = "#e6c840"
ACCENT_RED = "#e05050"
ACCENT_GREEN = "#60c070"


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

class ScenesPanel(QFrame):
    scene_selected = pyqtSignal(int)
    scene_add = pyqtSignal()
    scene_remove = pyqtSignal(int)
    scene_renamed = pyqtSignal(int, str, str)  # index, new_name, new_start

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

        self._list = QListWidget()
        self._list.setStyleSheet(
            f"QListWidget {{ background: {DARK_BG}; color: {TEXT_BRIGHT}; border: 1px solid {DARK_BORDER}; }}"
            f"QListWidget::item:selected {{ background: {ACCENT_BLUE}; color: white; }}"
        )
        self._list.currentRowChanged.connect(self.scene_selected.emit)
        self._list.itemDoubleClicked.connect(self._on_double_click)
        lay.addWidget(self._list, 1)

        btn_row = QHBoxLayout()
        add = QPushButton("+ Scene")
        add.clicked.connect(self.scene_add.emit)
        rm = QPushButton("−")
        rm.clicked.connect(self._on_remove)
        rm.setFixedWidth(30)
        btn_row.addWidget(add)
        btn_row.addWidget(rm)
        lay.addLayout(btn_row)

    def set_scenes(self, scenes, active_index: Optional[int] = None):
        prev = self._list.currentRow()
        self._list.blockSignals(True)
        self._list.clear()
        for i, sc in enumerate(scenes):
            label = f"{sc.start_time}   {sc.name or '(unnamed)'}"
            it = QListWidgetItem(label)
            if active_index == i:
                it.setForeground(QColor(ACCENT_GREEN))
                f = it.font(); f.setBold(True); it.setFont(f)
            self._list.addItem(it)
        if prev >= 0 and prev < len(scenes):
            self._list.setCurrentRow(prev)
        elif scenes:
            self._list.setCurrentRow(0)
        self._list.blockSignals(False)

    def current_row(self) -> int:
        return self._list.currentRow()

    def _on_remove(self):
        r = self._list.currentRow()
        if r >= 0:
            self.scene_remove.emit(r)

    def _on_double_click(self, item: QListWidgetItem):
        row = self._list.row(item)
        # Two-field editor: scene name and start time
        current_text = item.text()
        # Extract from "HH:MM:SS   Name"
        current_start, _, current_name = current_text.partition("   ")
        name, ok = QInputDialog.getText(self, "Scene name", "Name:", text=current_name)
        if not ok:
            return
        start, ok2 = QInputDialog.getText(
            self, "Scene start time",
            "Start time (HH:MM:SS):", text=current_start,
        )
        if not ok2:
            return
        self.scene_renamed.emit(row, name.strip(), start.strip())


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
        self._scenes_panel.scene_renamed.connect(self._on_scene_renamed)
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

    # ── tick ────
    def _on_tick(self):
        hms = now_hms()
        self._topbar.set_time(hms)

        drift_state = self._drift.state()
        self._topbar.set_drift(drift_state["drift"], self._show.settings.drift_warning_seconds)

        ph = resolve(self._show, now_seconds_of_day())
        self._update_cards(ph)
        self._scenes_panel.set_scenes(self._show.scenes, ph.current_scene_index)

        cur_row = None
        if ph.current_cue and ph.current_cue.scene_index == self._active_scene_row:
            cur_row = ph.current_cue.cue_index
        self._table.mark_current(cur_row)

    def _update_cards(self, ph: Playhead):
        ops = self._show.settings.operator_names
        cur_cue = ph.current_cue.resolve(self._show)[1] if ph.current_cue else None
        nxt_cue = ph.next_cue.resolve(self._show)[1] if ph.next_cue else None
        self._current_card.show_cue(cur_cue, ops)
        self._next_card.show_cue(nxt_cue, ops, ph.countdown())

    # ── scene handlers ────
    def _on_scene_selected(self, row: int):
        if row < 0 or row >= len(self._show.scenes):
            return
        self._active_scene_row = row
        self._table.load_cues(self._show.scenes[row].cues, self._show.settings.operator_names)

    def _on_scene_add(self):
        name, ok = QInputDialog.getText(self, "New scene", "Scene name:")
        if not ok:
            return
        start, ok2 = QInputDialog.getText(self, "Start time", "HH:MM:SS:", text=now_hms())
        if not ok2:
            return
        self._show.scenes.append(Scene(name=name.strip() or "Scene", start_time=start.strip() or "00:00:00"))
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

    def _on_scene_renamed(self, row: int, name: str, start: str):
        if not (0 <= row < len(self._show.scenes)):
            return
        sc = self._show.scenes[row]
        sc.name = name
        if start:
            sc.start_time = start
        self._reload_scenes()
        self._mark_dirty()

    def _reload_scenes(self):
        self._scenes_panel.set_scenes(self._show.scenes)
        if self._show.scenes:
            self._scenes_panel._list.setCurrentRow(self._active_scene_row)
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
