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
from ui import theme
from typing import List, Optional, Tuple, Dict

C_FUTURE_BG  = QColor(38, 38, 38)
# Past rows: a hair-thin 3 % white lift over the future-row bg.
# Pre-computed from _color_blend(C_FUTURE_BG, white, 0.03) so it can
# live at module level without a forward reference.  The visual
# delta from C_FUTURE_BG is intentionally tiny — past cues are
# differentiated mainly by dim text and unbold weight, not by a
# loud background change like the previous #323232.
C_PAST_BG    = QColor(44, 44, 44)
# Section dividers were previously a warm amber (BG #231E14, text
# #C8B97A) — visually distinct but clashed with cue tags that landed
# in the same warm-tone family.  Move to neutral grey from the
# design system so dividers read as "structural metadata" rather
# than "another colour signal".
C_SECTION_BG    = QColor(theme.SECTION_BG)
C_SECTION_TEXT  = QColor(theme.SECTION_TEXT)
C_SECTION_COUNT = QColor(theme.SECTION_COUNT_TEXT)
C_TEXT_NORM  = QColor(220, 220, 220)

# 20 color choices
# A short, well-spaced palette is easier to scan than 20 near-duplicates.
# Eight buckets cover the operator's actual semantic vocabulary
# (alarm / warning / attention / go / info / secondary / special / neutral)
# without three near-identical reds or three near-identical blues.
# Names are kept stable so existing .ojeshow files that referenced any of
# the deleted hues still resolve to the closest remaining bucket below.
COLOR_PALETTE: List[Tuple[str, QColor]] = [
    ("",       QColor(0, 0, 0, 0)),       # no colour
    ("red",    QColor(175, 48, 48)),
    ("orange", QColor(195, 105, 38)),
    ("amber",  QColor(210, 160, 30)),
    ("green",  QColor(48, 155, 75)),
    ("teal",   QColor(38, 140, 130)),
    ("blue",   QColor(48, 95, 175)),
    ("purple", QColor(125, 55, 175)),
    ("grey",   QColor(110, 110, 110)),
]

# Backwards-compat aliases — old shows referenced these names; map them
# onto the closest surviving bucket so loading doesn't drop the colour.
_COLOR_ALIASES = {
    "dark red":   "red",
    "yellow":     "amber",
    "lime":       "green",
    "dark green": "green",
    "cyan":       "teal",
    "sky":        "blue",
    "dark blue":  "blue",
    "indigo":     "purple",
    "magenta":    "purple",
    "pink":       "purple",
    "rose":       "red",
    "white":      "grey",
}

NAMED_COLORS = {name: color for name, color in COLOR_PALETTE if name}

COL_COLOR = 4

# column index -> Cue field (None = read-only)
COL_FIELD = {
    0: None, 1: "timecode", 2: "name", 3: "description", 4: "color",
}
COLUMNS = ("#", "Timecode", "Name", "Description", "Color")


def _named_bg(name: str) -> Optional[QColor]:
    key = (name or "").lower().strip()
    if key in NAMED_COLORS:
        return NAMED_COLORS[key]
    # Resolve legacy names from the longer palette to a current colour.
    return NAMED_COLORS.get(_COLOR_ALIASES.get(key, ""))


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
    """
    Cue-colour cell paint.  Renders a tight horizontal pill instead
    of an almost-cell-sized rectangle so the column reads as a
    decorative tag, not a saturated stripe — consistent with the
    new 7 % row tint, which is now the primary "what colour is
    this cue?" signal.  Empty cues show a faint em-dash.
    """

    PILL_HEIGHT = 12

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        color = _named_bg(index.data(Qt.ItemDataRole.DisplayRole) or "")
        painter.save()
        if color:
            cell = option.rect
            pill_w = max(cell.width() - 16, 0)
            pill_h = self.PILL_HEIGHT
            x = cell.x() + 8
            y = cell.center().y() - pill_h // 2
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(x, y, pill_w, pill_h, pill_h / 2, pill_h / 2)
        else:
            painter.setPen(QColor(theme.TEXT_DISABLED))
            f = QFont(); f.setPointSize(11)
            painter.setFont(f)
            painter.drawText(option.rect, Qt.AlignmentFlag.AlignCenter, "—")
        painter.restore()

    def createEditor(self, parent, option, index):
        combo = QComboBox(parent)
        combo.setStyleSheet(
            f"QComboBox {{ background: {theme.BG_INPUT}; "
            f"color: {theme.TEXT_PRIMARY}; "
            f"border: 1px solid {theme.BORDER}; "
            f"border-radius: {theme.RADIUS_SM}px; }}"
            f"QComboBox QAbstractItemView {{ background: {theme.BG_INPUT}; "
            f"color: {theme.TEXT_PRIMARY}; "
            f"selection-background-color: {theme.BG_RAISED}; }}"
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
    """
    Read-only paint for the timecode column.  The duplicate-row
    indication used to live here as a small ⚠ glyph; it now lives
    in DupBadgeDelegate on the NAME column (a clearer "DUP" pill,
    co-located with the row's amber stripe and tint), so this
    delegate is back to a plain paint.
    """

    def __init__(self, table: "CueTable", parent=None):
        super().__init__(parent)
        self._table = table

    def createEditor(self, parent, option, index):
        return None


# ── Active-row stripe delegate ───────────────────────────────────────────────

class ActiveRowDelegate(QStyledItemDelegate):
    """
    Lays a 3-px coloured stripe down the left edge of certain rows.
    Installed only on column 0 (#) — a stripe at the left of the
    leftmost cell reads as "the row's left border" because col 0
    butts up against the table's left edge.

    Priority: active (green) > duplicate (amber).  An active cue
    that also happens to be a duplicate is still "live", so the
    green wins.

    The row tint, text colour, and bold come from
    _apply_styles_inner; this delegate only adds the visible stripe,
    so a stale state still looks sensible if the painter runs first.
    """

    STRIPE_WIDTH = 3

    def __init__(self, table: "CueTable", parent=None):
        super().__init__(parent)
        self._table = table

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        super().paint(painter, option, index)
        row = index.row()
        stripe = None
        if row == self._table._active_row:
            stripe = QColor(theme.SEMANTIC_SUCCESS)
        elif row in self._table._duplicate_rows:
            stripe = QColor(theme.SEMANTIC_WARNING)
        if stripe is not None:
            painter.save()
            painter.setBrush(QBrush(stripe))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(
                option.rect.x(), option.rect.y(),
                self.STRIPE_WIDTH, option.rect.height(),
            )
            painter.restore()


class DupBadgeDelegate(QStyledItemDelegate):
    """
    Paints a small amber "DUP" pill at the right edge of the NAME
    column for duplicate-timecode rows.  Coexists with the cell's
    own text + editor — the pill is purely visual feedback,
    drawn on top after the default item paint.
    """

    def __init__(self, table: "CueTable", parent=None):
        super().__init__(parent)
        self._table = table

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        super().paint(painter, option, index)
        if index.row() not in self._table._duplicate_rows:
            return
        # Don't paint the badge on dividers (which never carry a
        # timecode and so can't be duplicates anyway, but be safe).
        cue = self._table._cues[index.row()] if index.row() < len(self._table._cues) else None
        if cue is None or cue.is_divider:
            return

        painter.save()
        f = QFont(); f.setPointSize(9); f.setBold(True)
        painter.setFont(f)
        text = "DUP"
        fm = painter.fontMetrics()
        text_w = fm.horizontalAdvance(text)
        pad_x = 6
        pad_y = 2
        pill_w = text_w + pad_x * 2
        pill_h = fm.height() + pad_y * 2
        x = option.rect.right() - pill_w - 6
        y = option.rect.center().y() - pill_h // 2
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QBrush(QColor(theme.SEMANTIC_WARNING)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(x, y, pill_w, pill_h, pill_h / 2, pill_h / 2)
        painter.setPen(QColor("#1a1300"))      # dark ink for AAA contrast on amber
        painter.drawText(
            QRect(x, y, pill_w, pill_h),
            Qt.AlignmentFlag.AlignCenter,
            text,
        )
        painter.restore()


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
        self._section_counts: Dict[int, int] = {}
        self._active_row: int = -1

        self.setHorizontalHeaderLabels(COLUMNS)
        hh = self.horizontalHeader()
        # Column sizing rationale:
        #   #          fits to content (1-3 digits)
        #   Timecode   fixed 120 px — always HH:MM:SS:FF, no wrap
        #   Name       interactive ~220 px — readable but doesn't hog
        #   Description STRETCH — takes whatever's left; this is the
        #              column that gets squeezed when the operator panel
        #              opens on the right, so Description gets priority
        #   Color      fixed 64 px — narrow pill swatch (the row tint
        #              already carries the colour signal; this column
        #              just gives the operator a quick "what tag?"
        #              indicator and the picker affordance)
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        hh.resizeSection(1, 120)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        hh.resizeSection(2, 220)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        hh.resizeSection(4, 64)
        self.verticalHeader().setVisible(False)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setAlternatingRowColors(False)
        self.setShowGrid(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)

        f = QFont(); f.setPointSize(12)
        self.setFont(f)
        # Focus ring on the active cell — sub-treme blue outline so the
        # operator can see where their next keystroke goes (Qt's default
        # is no border at all on QTableWidget cells).
        self.setStyleSheet(self.styleSheet() + """
            QTableWidget::item:focus {
                border: 1px solid #5a8ec0;
                outline: none;
            }
            QTableWidget::item:selected {
                background: #2c4a70;
            }
        """)

        self.setItemDelegateForColumn(0, ActiveRowDelegate(self, self))
        self.setItemDelegateForColumn(1, TimecodeDelegate(self, self))
        self.setItemDelegateForColumn(2, DupBadgeDelegate(self, self))
        self.setItemDelegateForColumn(COL_COLOR, ColorDelegate(self))
        # Hidden by default — set_edit_mode(True) reveals it when
        # the operator enters edit mode.
        self.setColumnHidden(COL_COLOR, True)
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
        self._compute_section_counts(cues)
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

    def _compute_section_counts(self, cues: List[Cue]):
        """
        For each divider row, count how many real cues fall under it
        (everything from the row after the divider up to the next
        divider, or end of list).  Used by _write_row to append
        " · N" to the divider's display name so the operator sees
        the section weight at a glance.
        """
        counts: Dict[int, int] = {}
        current_divider = None
        running = 0
        for row, cue in enumerate(cues):
            if cue.is_divider:
                if current_divider is not None:
                    counts[current_divider] = running
                current_divider = row
                running = 0
            else:
                running += 1
        if current_divider is not None:
            counts[current_divider] = running
        self._section_counts = counts

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
            count = self._section_counts.get(row, 0)
            count_part = f"  ·  {count} cue{'' if count == 1 else 's'}" if count else ""
            name_display = f"  {cue.name}{count_part}"

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

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.rowCount() != 0:
            return
        # Empty-state placeholder.  An untouched QTableWidget with no
        # rows is a blank charcoal slab — readable, but it gives the
        # operator no clue what they're meant to do.  A short, dim
        # two-line message at the centre points to the two normal
        # ways to populate the list.
        painter = QPainter(self.viewport())
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            rect = self.viewport().rect()
            center_y = rect.center().y()

            head_font = QFont(); head_font.setPointSize(15); head_font.setBold(True)
            sub_font  = QFont(); sub_font.setPointSize(11)

            painter.setPen(QColor(theme.TEXT_MUTED))
            painter.setFont(head_font)
            head_h = painter.fontMetrics().height()
            painter.drawText(
                QRect(rect.x(), center_y - head_h, rect.width(), head_h),
                Qt.AlignmentFlag.AlignCenter,
                "No cues yet",
            )

            painter.setPen(QColor(theme.TEXT_DIM))
            painter.setFont(sub_font)
            sub_h = painter.fontMetrics().height()
            painter.drawText(
                QRect(rect.x(), center_y + 4, rect.width(), sub_h),
                Qt.AlignmentFlag.AlignCenter,
                "Add one with + in Edit Cues, or open a .ojeshow / .csv from File.",
            )
        finally:
            painter.end()

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
        prev_active = self._active_row
        if current_cue is not None and 1 <= current_cue.index <= len(cues):
            self._active_row = current_cue.index - 1
        else:
            self._active_row = -1
        # Repaint col 0 of the previous active row so its green stripe
        # disappears when the current cue advances.  setBackground on
        # the new active row covers the new stripe automatically; only
        # the *outgoing* row needs an explicit nudge.
        if prev_active != self._active_row and prev_active >= 0:
            idx = self.model().index(prev_active, 0)
            self.update(idx)
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
                    item.setBackground(QBrush(C_SECTION_BG))
                    # Section name is brighter than the trailing
                    # "· N cues" text — Qt items are single-foreground,
                    # so we settle on the brighter section colour for
                    # the whole cell and rely on the count's quieter
                    # phrasing to step back visually.
                    item.setForeground(QBrush(C_SECTION_TEXT))
                    _bold(item, True)
                continue

            is_current = current_cue is not None and cue.index == current_cue.index
            # "Past" by timecode, not by list row. Non-linear cue ordering
            # means a cue further down the list can be in the past
            # (smaller timecode) and one near the top can be in the future.
            is_past = (
                cue.has_timecode
                and not is_current
                and cue.frames <= current_frames
            )
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
                    # Active cue is always green tint regardless of any
                    # cue-colour tag — the green carries the "this is
                    # live" semantic, and the cue colour reverts to a
                    # decorative tag (still visible in the COL_COLOR
                    # swatch and its 7 % row tint when not active).
                    # The stripe at the row's left edge is painted by
                    # ActiveRowDelegate on col 0.
                    item.setBackground(
                        QBrush(_color_blend(C_FUTURE_BG,
                                            QColor(theme.SEMANTIC_SUCCESS),
                                            0.14))
                    )
                    item.setForeground(QBrush(QColor(theme.TEXT_BRIGHT)))
                    _bold(item, True)
                elif is_dup_hl or is_dup:
                    # Duplicate-timecode rows: a 14 % amber blend over
                    # the row, matching the active-row blend strength
                    # but in the warning hue.  Sibling-highlighted
                    # rows (the operator clicked one duplicate to see
                    # its peers) get a slightly stronger 18 % blend
                    # plus brighter text so the selection emphasis
                    # still stands out without introducing yet
                    # another colour.  The full row tints — col 1 is
                    # no longer special-cased.  The "DUP" pill is
                    # painted by DupBadgeDelegate on col 2 and the
                    # left stripe by ActiveRowDelegate on col 0.
                    alpha = 0.18 if is_dup_hl else 0.14
                    item.setBackground(
                        QBrush(_color_blend(C_FUTURE_BG,
                                            QColor(theme.SEMANTIC_WARNING),
                                            alpha))
                    )
                    item.setForeground(
                        QBrush(QColor(theme.TEXT_BRIGHT if is_dup_hl else theme.TEXT_PRIMARY))
                    )
                    _bold(item, False)
                elif is_past:
                    item.setBackground(QBrush(C_PAST_BG))
                    item.setForeground(QBrush(QColor(theme.TEXT_MUTED)))
                    _bold(item, False)
                else:
                    # Cue-colour rows now read as "tagged with this hue"
                    # rather than "filled with this hue" — a 7 % blend
                    # over the standard future-row background lifts the
                    # tone enough to spot at a glance without making the
                    # name text fight the colour for legibility.  Old
                    # behaviour (full dark shade) flooded the row and
                    # made every coloured cue look more important than
                    # the white-text default cue.
                    if custom_bg:
                        item.setBackground(QBrush(_color_blend(C_FUTURE_BG, custom_bg, 0.07)))
                    else:
                        item.setBackground(QBrush(C_FUTURE_BG))
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
        # Color column is only useful in edit mode (the picker). In view
        # mode the whole row already tints to the cue colour, so the
        # column itself is just visual noise — hide it.
        self.setColumnHidden(COL_COLOR, not enabled)
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
            "OperatorEditPanel { background: #1a1a1a; border-left: 1px solid #333; }"
        )
        self._current_row = -1
        self._operator_names: List[str] = []
        self._fields: Dict[str, _OperatorCommentEdit] = {}
        self._field_widgets: list = []

        self._root_lay = QVBoxLayout(self)
        self._root_lay.setContentsMargins(12, 8, 12, 8)
        self._root_lay.setSpacing(6)

        self._title = QLabel("OPERATOR COMMENTS")
        self._title.setStyleSheet(
            "color: #7a7acd; font-size: 10px; font-weight: bold; letter-spacing: 2px;"
        )
        self._root_lay.addWidget(self._title)

        # Scroll area lets the panel handle many operators or tall comments
        # without needing a fixed pixel height (which used to fight with the
        # splitter that owns this widget).
        from PyQt6.QtWidgets import QScrollArea
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; }")

        self._fields_container = QWidget()
        self._fields_container.setStyleSheet("background: transparent;")
        self._fields_lay = QVBoxLayout(self._fields_container)
        self._fields_lay.setContentsMargins(0, 0, 0, 0)
        self._fields_lay.setSpacing(8)
        scroll.setWidget(self._fields_container)
        self._root_lay.addWidget(scroll, 1)
        self.setMinimumWidth(280)

    def set_operators(self, operator_names: List[str]):
        self._operator_names = operator_names
        # Clear existing widgets AND any leftover stretch so the previous
        # bottom-spacer doesn't accumulate across rebuilds.
        while self._fields_lay.count():
            item = self._fields_lay.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        self._field_widgets.clear()
        self._fields.clear()

        for name in operator_names:
            row_w = QWidget()
            row_lay = QVBoxLayout(row_w)
            row_lay.setContentsMargins(0, 0, 0, 0)
            row_lay.setSpacing(2)

            lbl = QLabel(name.upper())
            lbl.setStyleSheet(
                "color: #8888cc; font-size: 10px; font-weight: bold; letter-spacing: 1.5px;"
            )
            row_lay.addWidget(lbl)

            edit = _OperatorCommentEdit()
            edit.setPlaceholderText("Multi-line comment…")
            edit.setMinimumHeight(58)
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

        # Bottom stretch keeps operator rows pinned at the top instead of
        # the QPlainTextEdits ballooning to fill an oversized panel.
        self._fields_lay.addStretch(1)
        # Don't lock our height — the splitter owns it.
        self.setMinimumHeight(0)

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


def _color_blend(base: QColor, accent: QColor, alpha: float) -> QColor:
    """
    Return `base` overlaid with `accent` at `alpha` (0..1).  Qt's
    QColor has no built-in blend op, so we mix the two RGB triples
    manually.  Used for the subtle cue-colour row tint — at 0.07
    the row reads as "vaguely tinted toward this colour" rather
    than "this colour, dimmed".
    """
    inv = 1.0 - alpha
    r = int(round(base.red()   * inv + accent.red()   * alpha))
    g = int(round(base.green() * inv + accent.green() * alpha))
    b = int(round(base.blue()  * inv + accent.blue()  * alpha))
    return QColor(r, g, b)


class _OperatorCommentEdit(QPlainTextEdit):
    editingFinished = pyqtSignal()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.editingFinished.emit()


class CueEditToolbar(QWidget):
    def __init__(self, table: CueTable, parent=None):
        super().__init__(parent)
        from ui.icons import make_icon, icon_size

        self.setFixedHeight(38)
        self.setStyleSheet(
            "QWidget { background: #1a1a1a; border-bottom: 1px solid #3c3c3c; }"
            "QPushButton {"
            "  background: #232323; border: 1px solid #3a3a3a;"
            "  border-radius: 4px; padding: 0;"
            "}"
            "QPushButton:hover { background: #2c2c2c; border-color: #4a4a4a; }"
            "QPushButton:pressed { background: #1a1a1a; }"
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 4, 10, 4)
        lay.setSpacing(4)

        def btn(icon_name: str, slot, tip: str) -> QPushButton:
            b = QPushButton()
            b.setIcon(make_icon(icon_name, "#d8d8d8"))
            b.setIconSize(icon_size(16))
            b.setFixedSize(30, 28)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            lay.addWidget(b)
            return b

        # Create / delete trio.
        btn("plus",    table.add_row_after_selected,     "Add cue after selection")
        btn("section", table.add_divider_after_selected, "Add section divider")
        btn("x",       table.delete_selected_rows,       "Delete selected rows")

        # Move-row pair, separated visually so it reads as a unit.
        lay.addSpacing(8)
        btn("up",   table.move_selected_up,   "Move row up")
        btn("down", table.move_selected_down, "Move row down")
        lay.addStretch()
