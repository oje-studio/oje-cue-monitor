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

from typing import Dict, List, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget,
)


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
