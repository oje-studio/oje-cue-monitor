"""
Shared UI primitives for SHOW MONITOR.

Portraits of the equivalent widgets in ui/cue_table.py (classic CUE
MONITOR), adapted to the scene/offset model. Centralised here so the
look is consistent between the scenes panel and the cue table.

TimecodePopup:
  Single-field popup with a QLineEdit mask. Used for scene start_time
  (HH:MM:SS) and cue offsets (HH:MM:SS.FF).
  NOTE: we read displayText() instead of text() to dodge a Qt quirk
  where a `0` blank char makes text() drop typed zeros. Same bug we
  fixed in the classic app (see git log).

OperatorEditPanel:
  A row of labeled QLineEdits, one per operator, that edit the
  selected cue's operator_comments dict inline.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from PyQt6.QtCore import QModelIndex, QRect, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QFont, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QStyledItemDelegate,
    QStyleOptionViewItem, QVBoxLayout, QWidget,
)


# ── Colour palette — identical set/names as CUE MONITOR ──────────────────────

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


def named_bg(name: str) -> Optional[QColor]:
    return NAMED_COLORS.get((name or "").lower().strip())


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


class VUMeter(QWidget):
    """5-bar LED-style VU meter. Input is dBFS (-120 .. 0)."""

    BARS = 5
    ACCENT_GREEN  = QColor(75, 195, 115)
    ACCENT_ORANGE = QColor(225, 135, 48)
    ACCENT_RED    = QColor(215, 75, 75)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._db = -120.0
        self.setFixedSize(62, 20)

    def set_db(self, db: float):
        self._db = db
        self.update()

    def paintEvent(self, _):
        painter = QPainter(self)
        W, H = self.width(), self.height()
        bw = (W - (self.BARS - 1) * 2) // self.BARS
        norm = max(0.0, min(1.0, (self._db + 60.0) / 60.0))
        lit = int(norm * self.BARS)
        for i in range(self.BARS):
            x = i * (bw + 2)
            if i >= self.BARS - 1:
                c = self.ACCENT_RED if i < lit else QColor(60, 20, 20)
            elif i >= self.BARS - 2:
                c = self.ACCENT_ORANGE if i < lit else QColor(55, 40, 15)
            else:
                c = self.ACCENT_GREEN if i < lit else QColor(25, 55, 35)
            painter.fillRect(x, 2, bw, H - 4, c)
        painter.end()


class ColorDelegate(QStyledItemDelegate):
    """Renders a color swatch + label and opens a combobox editor on activation."""

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        name = index.data(Qt.ItemDataRole.DisplayRole) or ""
        color = named_bg(name)
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
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, name)
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


def mono_font(size: int = 13) -> QFont:
    f = QFont("Menlo")
    f.setStyleHint(QFont.StyleHint.Monospace)
    f.setPointSize(size)
    return f


# ── Timecode popup editor ─────────────────────────────────────────────────────

class TimecodePopup(QFrame):
    """
    Generic fixed-mask time editor. Two presets covered by `mask`:
      - "hms"   → HH:MM:SS        (scene start times)
      - "hmsff" → HH:MM:SS.FF     (cue offsets, 2-digit fractional seconds)
    """
    accepted = pyqtSignal(str)

    MASKS = {
        "hms":   ("00:00:00;0",    "HH : MM : SS",         "00:00:00",     220),
        "hmsff": ("00:00:00\\.00;0", "HH : MM : SS . FF",   "00:00:00.00",  240),
    }

    def __init__(self, current: str, mask_key: str = "hms", parent=None):
        super().__init__(parent, Qt.WindowType.Popup)
        self.setStyleSheet(
            "TimecodePopup { background: #1c1c1c; border: 2px solid #4a90d9;"
            " border-radius: 6px; }"
        )
        mask, label_text, placeholder, width = self.MASKS[mask_key]
        self.setFixedSize(width, 70)

        self._applied = False
        self._cancelled = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(6)

        lbl = QLabel(label_text)
        lbl.setStyleSheet("color: #666; font-size: 10px; letter-spacing: 1px;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(lbl)

        self._edit = QLineEdit()
        self._edit.setInputMask(mask)
        self._edit.setFont(mono_font(16))
        self._edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._edit.setStyleSheet(
            "QLineEdit { background: #0a0a0a; color: #ffffff;"
            " border: 1px solid #555; border-radius: 4px; padding: 4px; }"
        )
        self._edit.setText(current if current else placeholder)
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
        # displayText() preserves typed zeros under the '0' blank char —
        # see the same-named fix in ui/cue_table.py for context.
        self.accepted.emit(self._edit.displayText())


# ── Operator edit panel ───────────────────────────────────────────────────────

class OperatorEditPanel(QFrame):
    """
    Edits the selected cue's operator_comments dict. One row per
    operator; edits fire operator_changed(row, op_name, comment) for
    the owner to persist back into the cue.
    """
    operator_changed = pyqtSignal(int, str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            "OperatorEditPanel { background: #1a1a1a; border-top: 1px solid #3a3a3a; }"
        )
        self._current_row = -1
        self._operator_names: List[str] = []
        self._fields: Dict[str, QLineEdit] = {}
        self._field_widgets: list = []

        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(12, 6, 12, 6)
        self._root.setSpacing(3)

        title = QLabel("OPERATOR COMMENTS")
        title.setStyleSheet(
            "color: #7a7acd; font-size: 10px; font-weight: bold; letter-spacing: 2px;"
        )
        self._root.addWidget(title)

        self._fields_container = QWidget()
        self._fields_lay = QVBoxLayout(self._fields_container)
        self._fields_lay.setContentsMargins(0, 0, 0, 0)
        self._fields_lay.setSpacing(2)
        self._root.addWidget(self._fields_container)

    def set_operators(self, operator_names: List[str]):
        self._operator_names = list(operator_names)
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

            edit = QLineEdit()
            edit.setPlaceholderText("…")
            edit.setStyleSheet(
                "QLineEdit { background: #222; color: #ddd; border: 1px solid #3a3a3a;"
                " border-radius: 3px; padding: 2px 6px; font-size: 12px; }"
                "QLineEdit:focus { border-color: #5577bb; }"
            )
            edit.editingFinished.connect(lambda n=name, e=edit: self._fire(n, e))
            row_lay.addWidget(edit)

            self._fields[name] = edit
            self._fields_lay.addWidget(row_w)
            self._field_widgets.append(row_w)

        h = 28 + len(operator_names) * 28 if operator_names else 0
        self.setFixedHeight(h)

    def show_for_cue(self, row: int, comments: Dict[str, str]):
        self._current_row = row
        for name, edit in self._fields.items():
            edit.blockSignals(True)
            edit.setText(comments.get(name, ""))
            edit.blockSignals(False)
        self.setVisible(bool(self._operator_names))

    def hide_panel(self):
        self._current_row = -1
        self.setVisible(False)

    def _fire(self, op_name: str, edit: QLineEdit):
        if self._current_row >= 0:
            self.operator_changed.emit(self._current_row, op_name, edit.text().strip())
