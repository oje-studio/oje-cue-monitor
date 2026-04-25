from __future__ import annotations

from PyQt6.QtWidgets import (
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QStyledItemDelegate,
    QComboBox, QStyleOptionViewItem, QLabel, QLineEdit, QPlainTextEdit,
    QFrame,
)
from PyQt6.QtCore import Qt, pyqtSignal, QModelIndex, QRect
from PyQt6.QtGui import QColor, QFont, QBrush, QPainter, QPixmap, QIcon

from cue_engine import Cue
from ui.fonts import mono_font
from typing import List, Optional, Tuple, Dict

C_CURRENT    = QColor(55, 130, 55)
C_PAST_BG    = QColor(50, 50, 50)
C_FUTURE_BG  = QColor(38, 38, 38)
C_DIVIDER_BG = QColor(20, 20, 38)
C_TEXT_DIM   = QColor(105, 105, 105)
C_TEXT_NORM  = QColor(220, 220, 220)
C_TEXT_DIVIDER = QColor(150, 150, 200)
C_TC_ERROR   = QColor(110, 35, 35)
C_DUPLICATE  = QColor(140, 100, 20)
C_DUP_HIGHLIGHT = QColor(160, 120, 30)

# 20 color choices
COLOR_PALETTE: List[Tuple[str, QColor]] = [
    ("",           QColor(0, 0, 0, 0)),
    ("red",        QColor(175, 48, 48)),
    ("dark red",   QColor(120, 25, 25)),
    ("orange",     QColor(195, 105, 38)),
    ("amber",      QColor(210, 160, 30)),
    ("yellow",     QColor(175, 155, 38)),
    ("lime",       QColor(95, 180, 45)),
    ("green",      QColor(48, 155, 75)),
    ("dark green", QColor(30, 100, 50)),
    ("teal",       QColor(38, 140, 130)),
    ("cyan",       QColor(48, 165, 175)),
    ("sky",        QColor(70, 145, 210)),
    ("blue",       QColor(48, 95, 175)),
    ("dark blue",  QColor(35, 55, 130)),
    ("indigo",     QColor(75, 55, 160)),
    ("purple",     QColor(125, 55, 175)),
    ("magenta",    QColor(165, 50, 140)),
    ("pink",       QColor(195, 95, 155)),
    ("rose",       QColor(190, 70, 90)),
    ("white",      QColor(200, 200, 200)),
    ("grey",       QColor(110, 110, 110)),
]

NAMED_COLORS = {name: color for name, color in COLOR_PALETTE if name}

COL_COLOR = 4

# column index -> Cue field (None = read-only)
COL_FIELD = {
    0: None, 1: "timecode", 2: "name", 3: "description", 4: "color",
}
COLUMNS = ("#", "Timecode", "Name", "Description", "Color")


def _named_bg(name: str) -> Optional[QColor]:
    return NAMED_COLORS.get(name.lower().strip())


def _color_icon(color: QColor, size: int = 16) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QBrush(color))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(1, 1, size - 2, size - 2, 3, 3)
    p.end()
    return QIcon(pm)


# ── Color delegate ────────────────────────────────────────────────────────────

class ColorDelegate(QStyledItemDelegate):
    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        color_name = index.data(Qt.ItemDataRole.DisplayRole) or ""
        color = _named_bg(color_name)
        painter.save()
        if color:
            rect = QRect(option.rect.x() + 4, option.rect.y() + 4,
                         option.rect.width() - 8, option.rect.height() - 8)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(rect, 4, 4)
            painter.setPen(QColor(255, 255, 255, 200))
            f = QFont(); f.setPointSize(10)
            painter.setFont(f)
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, color_name)
        else:
            painter.setPen(QColor(80, 80, 80))
            painter.drawText(option.rect, Qt.AlignmentFlag.AlignCenter, "—")
        painter.restore()

    def createEditor(self, parent, option, index):
        combo = QComboBox(parent)
        combo.setStyleSheet(
            "QComboBox { background: #2a2a2a; color: #dcdcdc; border: 1px solid #555; }"
            "QComboBox QAbstractItemView { background: #2a2a2a; color: #dcdcdc; }"
        )
        for name, color in COLOR_PALETTE:
            if name:
                combo.addItem(_color_icon(color, 14), f"  {name}", name)
            else:
                combo.addItem("  (none)", "")
        combo.currentIndexChanged.connect(lambda: self.commitData.emit(combo))
        combo.currentIndexChanged.connect(
            lambda: self.closeEditor.emit(combo, QStyledItemDelegate.EndEditHint.NoHint))
        return combo

    def setEditorData(self, editor: QComboBox, index):
        val = (index.data(Qt.ItemDataRole.DisplayRole) or "").strip().lower()
        for i in range(editor.count()):
            if editor.itemData(i) == val:
                editor.setCurrentIndex(i)
                return
        editor.setCurrentIndex(0)

    def setModelData(self, editor: QComboBox, model, index):
        model.setData(index, editor.currentData() or "", Qt.ItemDataRole.EditRole)


# ── Timecode editor popup ─────────────────────────────────────────────────────

class TimecodePopup(QFrame):
    """Floating popup with masked input for timecode editing."""
    accepted = pyqtSignal(str)

    def __init__(self, current_tc: str, parent=None):
        super().__init__(parent, Qt.WindowType.Popup)
        self.setStyleSheet(
            "TimecodePopup { background: #1c1c1c; border: 2px solid #4a90d9; border-radius: 6px; }"
        )
        self.setFixedSize(220, 70)
        self._applied = False
        self._cancelled = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(6)

        lbl = QLabel("HH : MM : SS : FF")
        lbl.setStyleSheet("color: #666; font-size: 10px; letter-spacing: 1px;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(lbl)

        self._edit = QLineEdit()
        self._edit.setInputMask("00:00:00:00;0")
        self._edit.setFont(mono_font(16))
        self._edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._edit.setStyleSheet(
            "QLineEdit { background: #0a0a0a; color: #ffffff; "
            "border: 1px solid #555; border-radius: 4px; padding: 4px; }"
        )
        self._edit.setText(current_tc if current_tc else "00:00:00:00")
        self._edit.selectAll()
        self._edit.returnPressed.connect(self._on_return)
        lay.addWidget(self._edit)

    def showEvent(self, event):
        super().showEvent(event)
        self._edit.setFocus()
        self._edit.selectAll()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self._cancelled = True
            self.close()
        else:
            super().keyPressEvent(event)

    def hideEvent(self, event):
        if not self._cancelled:
            self._try_apply()
        super().hideEvent(event)

    def _on_return(self):
        self._try_apply()
        self.close()

    def _try_apply(self):
        if self._applied:
            return
        self._applied = True
        # Use displayText() not text(): with blank char '0', text() strips
        # typed zeros (can't distinguish them from unfilled positions), so
        # e.g. "10:00:00:00" comes back as "1:::". displayText() preserves
        # the visible value with blanks filled in.
        val = self._edit.displayText()
        parts = val.split(":")
        if len(parts) != 4:
            return
        parts = [p if p else "0" for p in parts]
        if all(p.isdigit() for p in parts):
            h = min(int(parts[0]), 23)
            m = min(int(parts[1]), 59)
            s = min(int(parts[2]), 59)
            f = min(int(parts[3]), 29)
            self.accepted.emit(f"{h:02d}:{m:02d}:{s:02d}:{f:02d}")


# ── Timecode paint delegate (visual only, no editing) ─────────────────────────

class TimecodeDelegate(QStyledItemDelegate):
    def __init__(self, table: "CueTable", parent=None):
        super().__init__(parent)
        self._table = table

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        row = index.row()
        is_dup = row in self._table._duplicate_rows

        super().paint(painter, option, index)

        if is_dup:
            painter.save()
            painter.setPen(QColor(225, 180, 40))
            f = QFont(); f.setPointSize(13)
            painter.setFont(f)
            x = option.rect.right() - 18
            y = option.rect.center().y() + 5
            painter.drawText(x, y, "⚠")
            painter.restore()

    def createEditor(self, parent, option, index):
        return None


# ── CueTable ─────────────────────────────────────────────────────────────────

class CueTable(QTableWidget):
    cue_data_changed      = pyqtSignal(int, str, str)
    row_add_requested     = pyqtSignal(int)
    row_delete_requested  = pyqtSignal(int)
    rows_delete_requested = pyqtSignal(list)
    row_move_requested    = pyqtSignal(int, int)
    divider_add_requested = pyqtSignal(int)
    cue_selected          = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(0, len(COLUMNS), parent)
        self._edit_mode    = False
        self._block_signal = False
        self._collapsed_groups: set = set()
        self._cues: List[Cue] = []
        self._duplicate_rows: set = set()
        self._highlighted_siblings: List[int] = []

        self.setHorizontalHeaderLabels(COLUMNS)
        hh = self.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        hh.resizeSection(1, 120)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        hh.resizeSection(4, 90)
        self.verticalHeader().setVisible(False)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setAlternatingRowColors(False)
        self.setShowGrid(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)

        f = QFont(); f.setPointSize(12)
        self.setFont(f)

        self.setItemDelegateForColumn(1, TimecodeDelegate(self, self))
        self.setItemDelegateForColumn(COL_COLOR, ColorDelegate(self))
        self.itemChanged.connect(self._on_item_changed)
        self.currentCellChanged.connect(self._on_cell_changed)

    # ── load ──────────────────────────────────────────────────────────────────

    def load_cues(self, cues: List[Cue]):
        self._cues = cues
        self._collapsed_groups = {
            row for row in self._collapsed_groups
            if 0 <= row < len(cues) and cues[row].is_divider
        }
        self._compute_duplicates(cues)
        self._highlighted_siblings = []
        self._block_signal = True
        self.setRowCount(len(cues))
        for row, cue in enumerate(cues):
            self._write_row(row, cue)
        self._block_signal = False
        self._apply_styles(cues, None, 0)
        self._apply_collapse()
        if self._edit_mode:
            self._update_duplicate_highlight(self.currentRow())

    def _compute_duplicates(self, cues: List[Cue]):
        from collections import Counter
        tc_counts = Counter(
            c.timecode.strip() for c in cues
            if not c.is_divider and c.timecode.strip()
        )
        self._duplicate_rows = set()
        for row, cue in enumerate(cues):
            if not cue.is_divider and cue.timecode.strip():
                if tc_counts[cue.timecode.strip()] > 1:
                    self._duplicate_rows.add(row)

    def _write_row(self, row: int, cue: Cue):
        tc_display = cue.timecode if not cue.is_divider else ""
        name_display = cue.name
        if cue.is_divider:
            name_display = f"  {cue.name}"

        is_dup = row in self._duplicate_rows

        values = [str(cue.index), tc_display, name_display,
                  cue.description, cue.color]
        for col, text in enumerate(values):
            item = self.item(row, col)
            if item is None:
                item = QTableWidgetItem(text)
                self.setItem(row, col, item)
            else:
                item.setText(text)
            if col == 0:
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            else:
                item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            if col in (0, 1):
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if col == 1 and is_dup:
                item.setToolTip("Duplicate timecode — only the last cue will be active")
            elif col == 1:
                item.setToolTip("")

        self.setRowHeight(row, 30 if cue.is_divider else 26)

    def refresh_index_column(self, cues: List[Cue]):
        self._cues = cues
        self._block_signal = True
        for row, cue in enumerate(cues):
            item = self.item(row, 0)
            if item:
                item.setText(str(cue.index))
        self._block_signal = False

    # ── collapse/expand groups ────────────────────────────────────────────────

    def toggle_group(self, divider_row: int):
        if divider_row in self._collapsed_groups:
            self._collapsed_groups.discard(divider_row)
        else:
            self._collapsed_groups.add(divider_row)
        self._apply_collapse()
        self._apply_styles(self._cues, None, 0)

    def _apply_collapse(self):
        if self._edit_mode:
            for row in range(self.rowCount()):
                self.setRowHidden(row, False)
            return

        hiding = False
        for row in range(self.rowCount()):
            if row < len(self._cues) and self._cues[row].is_divider:
                hiding = (row in self._collapsed_groups)
                self.setRowHidden(row, False)
            else:
                self.setRowHidden(row, hiding)

    def mouseDoubleClickEvent(self, event):
        idx = self.indexAt(event.pos())
        if idx.isValid() and idx.row() < len(self._cues):
            cue = self._cues[idx.row()]
            if cue.is_divider and not self._edit_mode:
                self.toggle_group(idx.row())
                return
            if idx.column() == 1 and self._edit_mode and not cue.is_divider:
                self._open_timecode_editor(idx.row())
                return
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event):
        idx = self.indexAt(event.pos())
        if (
            event.button() == Qt.MouseButton.LeftButton
            and idx.isValid()
            and idx.row() < len(self._cues)
        ):
            cue = self._cues[idx.row()]
            # Divider rows show a fold arrow in the first column; make that
            # arrow behave like a real disclosure control on single click.
            if cue.is_divider and not self._edit_mode and idx.column() == 0:
                self.toggle_group(idx.row())
                self.setCurrentCell(idx.row(), idx.column())
                return
        super().mousePressEvent(event)

    def _open_timecode_editor(self, row: int):
        cue = self._cues[row]
        item = self.item(row, 1)
        if not item:
            return
        rect = self.visualItemRect(item)
        global_pos = self.viewport().mapToGlobal(rect.bottomLeft())

        popup = TimecodePopup(cue.timecode, self)
        popup.accepted.connect(lambda tc: self._apply_timecode(row, tc))
        popup.move(global_pos)
        popup.show()

    def _apply_timecode(self, row: int, tc: str):
        self.cue_data_changed.emit(row, "timecode", tc)

    # ── highlight ─────────────────────────────────────────────────────────────

    def update_highlight(self, cues: List[Cue], current_cue: Optional[Cue], current_frames: int):
        self._cues = cues
        self._apply_styles(cues, current_cue, current_frames)
        if current_cue is not None:
            row = current_cue.index - 1
            if 0 <= row < self.rowCount():
                self.scrollTo(self.model().index(row, 0))

    def _apply_styles(self, cues: List[Cue], current_cue: Optional[Cue], current_frames: int):
        self.blockSignals(True)
        try:
            self._apply_styles_inner(cues, current_cue, current_frames)
        finally:
            self.blockSignals(False)

    def _apply_styles_inner(self, cues: List[Cue], current_cue: Optional[Cue], current_frames: int):
        for row, cue in enumerate(cues):
            if cue.is_divider:
                collapsed = row in self._collapsed_groups
                arrow = "▶" if collapsed else "▼"
                item0 = self.item(row, 0)
                if item0:
                    item0.setText(arrow)
                for col in range(self.columnCount()):
                    item = self.item(row, col)
                    if not item:
                        continue
                    item.setBackground(QBrush(C_DIVIDER_BG))
                    item.setForeground(QBrush(C_TEXT_DIVIDER))
                    _bold(item, True)
                continue

            is_current = current_cue is not None and cue.index == current_cue.index
            is_past    = current_cue is not None and row < (current_cue.index - 1) and not is_current
            is_dup     = row in self._duplicate_rows
            is_dup_hl  = row in self._highlighted_siblings
            custom_bg  = _named_bg(cue.color) if cue.color else None

            for col in range(self.columnCount()):
                if col == COL_COLOR:
                    continue
                item = self.item(row, col)
                if not item:
                    continue
                if is_current:
                    item.setBackground(QBrush(custom_bg if custom_bg else C_CURRENT))
                    item.setForeground(QBrush(C_TEXT_NORM))
                    _bold(item, True)
                elif is_dup_hl:
                    item.setBackground(QBrush(C_DUP_HIGHLIGHT))
                    item.setForeground(QBrush(C_TEXT_NORM))
                    _bold(item, False)
                elif is_dup and col == 1:
                    item.setBackground(QBrush(C_DUPLICATE))
                    item.setForeground(QBrush(C_TEXT_NORM))
                    _bold(item, False)
                elif is_past:
                    item.setBackground(QBrush(C_PAST_BG))
                    item.setForeground(QBrush(C_TEXT_DIM))
                    _bold(item, False)
                else:
                    item.setBackground(QBrush(custom_bg.darker(200) if custom_bg else C_FUTURE_BG))
                    item.setForeground(QBrush(C_TEXT_NORM))
                    _bold(item, False)

    # ── editing ───────────────────────────────────────────────────────────────

    def set_edit_mode(self, enabled: bool):
        self._edit_mode = enabled
        if enabled:
            self.setEditTriggers(
                QAbstractItemView.EditTrigger.DoubleClicked
                | QAbstractItemView.EditTrigger.SelectedClicked
            )
        else:
            self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._apply_collapse()

    def _on_item_changed(self, item: QTableWidgetItem):
        if self._block_signal or not self._edit_mode:
            return
        row = item.row()
        col = item.column()
        field = COL_FIELD.get(col)
        if field is None or field == "timecode":
            return
        value = item.text().strip()
        self.cue_data_changed.emit(row, field, value)

    def _on_cell_changed(self, row, col, prev_row, prev_col):
        if self._edit_mode and 0 <= row < len(self._cues):
            self.cue_selected.emit(row)
        self._update_duplicate_highlight(row)

    def _update_duplicate_highlight(self, row: int):
        old_siblings = self._highlighted_siblings
        self._highlighted_siblings = []

        if self._edit_mode and 0 <= row < len(self._cues) and row in self._duplicate_rows:
            tc = self._cues[row].timecode.strip()
            for r, cue in enumerate(self._cues):
                if r != row and not cue.is_divider and cue.timecode.strip() == tc:
                    self._highlighted_siblings.append(r)

        changed_rows = set(old_siblings) | set(self._highlighted_siblings)
        if changed_rows:
            self._apply_styles(self._cues, None, 0)

    # ── actions ───────────────────────────────────────────────────────────────

    def add_row_after_selected(self):
        self.row_add_requested.emit(self.currentRow())

    def add_divider_after_selected(self):
        self.divider_add_requested.emit(self.currentRow())

    def delete_selected_rows(self):
        rows = sorted(set(idx.row() for idx in self.selectedIndexes()))
        if rows:
            self.rows_delete_requested.emit(rows)

    def move_selected_up(self):
        row = self.currentRow()
        if row > 0:
            self.row_move_requested.emit(row, row - 1)

    def move_selected_down(self):
        row = self.currentRow()
        if 0 <= row < self.rowCount() - 1:
            self.row_move_requested.emit(row, row + 1)


# ── Operator Edit Panel ───────────────────────────────────────────────────────

class OperatorEditPanel(QFrame):
    """Panel showing individual operator comment fields for the selected cue."""

    operator_changed = pyqtSignal(int, str, str)  # row, op_name, comment

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            "OperatorEditPanel { background: #1a1a1a; border-top: 1px solid #333; }"
        )
        self._current_row = -1
        self._operator_names: List[str] = []
        self._fields: Dict[str, _OperatorCommentEdit] = {}
        self._field_widgets: list = []

        self._root_lay = QVBoxLayout(self)
        self._root_lay.setContentsMargins(12, 6, 12, 6)
        self._root_lay.setSpacing(3)

        self._title = QLabel("OPERATOR COMMENTS")
        self._title.setStyleSheet(
            "color: #7a7acd; font-size: 10px; font-weight: bold; letter-spacing: 2px;"
        )
        self._root_lay.addWidget(self._title)

        self._fields_container = QWidget()
        self._fields_lay = QVBoxLayout(self._fields_container)
        self._fields_lay.setContentsMargins(0, 0, 0, 0)
        self._fields_lay.setSpacing(2)
        self._root_lay.addWidget(self._fields_container)

    def set_operators(self, operator_names: List[str]):
        self._operator_names = operator_names
        # Clear existing
        for w in self._field_widgets:
            w.setParent(None)
            w.deleteLater()
        self._field_widgets.clear()
        self._fields.clear()

        for name in operator_names:
            row_w = QWidget()
            row_lay = QHBoxLayout(row_w)
            row_lay.setContentsMargins(0, 0, 0, 0)
            row_lay.setSpacing(8)

            lbl = QLabel(name)
            lbl.setFixedWidth(110)
            lbl.setStyleSheet("color: #8888cc; font-size: 11px; font-weight: bold;")
            row_lay.addWidget(lbl)

            edit = _OperatorCommentEdit()
            edit.setPlaceholderText("Multi-line comment")
            edit.setFixedHeight(58)
            edit.setStyleSheet(
                "QPlainTextEdit { background: #222; color: #ddd; border: 1px solid #3a3a3a; "
                "border-radius: 3px; padding: 4px 6px; font-size: 12px; }"
                "QPlainTextEdit:focus { border-color: #5577bb; }"
            )
            edit.editingFinished.connect(lambda n=name, e=edit: self._on_edit(n, e))
            row_lay.addWidget(edit)

            self._fields[name] = edit
            self._fields_lay.addWidget(row_w)
            self._field_widgets.append(row_w)

        h = 34 + len(operator_names) * 64 if operator_names else 0
        self.setFixedHeight(h)

    def show_for_cue(self, row: int, cue: Cue):
        self._current_row = row
        for name, edit in self._fields.items():
            edit.blockSignals(True)
            edit.setPlainText(cue.operator_comments.get(name, ""))
            edit.blockSignals(False)
        self.setVisible(bool(self._operator_names))

    def hide_panel(self):
        self._current_row = -1
        self.setVisible(False)

    def _on_edit(self, op_name: str, edit: "_OperatorCommentEdit"):
        if self._current_row >= 0:
            self.operator_changed.emit(self._current_row, op_name, edit.toPlainText().strip())


# ── helpers ───────────────────────────────────────────────────────────────────

def _bold(item: QTableWidgetItem, bold: bool):
    f = item.font()
    if f.bold() != bold:
        f.setBold(bold)
        item.setFont(f)


class _OperatorCommentEdit(QPlainTextEdit):
    editingFinished = pyqtSignal()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.editingFinished.emit()


class CueEditToolbar(QWidget):
    def __init__(self, table: CueTable, parent=None):
        super().__init__(parent)
        self.setFixedHeight(38)
        self.setStyleSheet("background: #1a1a1a; border-bottom: 1px solid #3c3c3c;")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 4, 10, 4)
        lay.setSpacing(6)

        def btn(label: str, slot, tip: str = "") -> QPushButton:
            b = QPushButton(label)
            b.setFixedHeight(26)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            lay.addWidget(b)
            return b

        btn("+ Cue",     table.add_row_after_selected,     "Add cue after selection")
        btn("+ Section", table.add_divider_after_selected, "Add section divider")
        btn("Delete",    table.delete_selected_rows,       "Delete selected rows")
        btn("Up",        table.move_selected_up,           "Move row up")
        btn("Down",      table.move_selected_down,         "Move row down")
        lay.addStretch()
