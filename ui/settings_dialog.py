from __future__ import annotations
from typing import List, Optional, Dict

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QSpinBox, QLineEdit, QFileDialog, QGroupBox,
    QFormLayout, QScrollArea, QWidget, QFrame, QCheckBox,
    QColorDialog,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QPixmap, QColor

from show_file import ShowSettings
from ui import theme
from ui.icons import make_icon, icon_size


# ── Style helpers (duplicated rather than imported from main_window
#    to keep the dialog's surface area independent — these are the
#    same vocabulary that c4 introduced in the footer). ─────────────
def _dialog_qss() -> str:
    """Dark-themed defaults for every input/group widget in the dialog."""
    return (
        f"QDialog {{ background: {theme.BG_APP}; }}"
        f"QScrollArea, QScrollArea > QWidget > QWidget "
        f"{{ background: transparent; border: none; }}"

        # QGroupBox: tighter, token-driven panel with the title floating
        # at the top-left in dim caps.
        f"QGroupBox {{ background: {theme.BG_SURFACE}; "
        f"border: 1px solid {theme.BORDER_SUBTLE}; "
        f"border-radius: {theme.RADIUS_LG}px; "
        f"margin-top: 18px; padding: 18px 14px 12px 14px; "
        f"color: {theme.TEXT_PRIMARY}; }}"
        f"QGroupBox::title {{ subcontrol-origin: margin; "
        f"subcontrol-position: top left; left: 12px; padding: 0 4px; "
        f"color: {theme.TEXT_MUTED}; "
        f"font-size: 11px; font-weight: 600; letter-spacing: 1.5px; }}"

        f"QLabel {{ color: {theme.TEXT_PRIMARY}; }}"

        # Inputs: shared bg / border / focus ring across line edits,
        # spin boxes, combos, password fields.
        f"QLineEdit, QSpinBox, QComboBox {{ "
        f"background: {theme.BG_INPUT}; "
        f"color: {theme.TEXT_PRIMARY}; "
        f"border: 1px solid {theme.BORDER}; "
        f"border-radius: {theme.RADIUS_SM}px; "
        f"padding: 5px 8px; "
        f"selection-background-color: {theme.BG_RAISED}; }}"
        f"QLineEdit:focus, QSpinBox:focus, QComboBox:focus "
        f"{{ border-color: {theme.SEMANTIC_INFO}; }}"
        f"QComboBox::drop-down {{ width: 18px; border: none; }}"

        f"QCheckBox {{ color: {theme.TEXT_PRIMARY}; }}"
        f"QCheckBox::indicator {{ width: 16px; height: 16px; "
        f"border: 1px solid {theme.BORDER}; border-radius: {theme.RADIUS_SM}px; "
        f"background: {theme.BG_INPUT}; }}"
        f"QCheckBox::indicator:checked {{ "
        f"background: {theme.SEMANTIC_INFO}; "
        f"border-color: {theme.SEMANTIC_INFO}; }}"
    )


def _primary_btn_qss() -> str:
    return (
        f"QPushButton {{ background: {theme.ACTION_PRIMARY}; "
        f"color: white; font-weight: 700; letter-spacing: 1px; "
        f"border: none; border-radius: {theme.RADIUS_MD}px; "
        f"padding: 8px 18px; }}"
        f"QPushButton:hover {{ background: {theme.ACTION_PRIMARY_HOVER}; }}"
    )


def _secondary_btn_qss() -> str:
    return (
        f"QPushButton {{ background: {theme.BG_RAISED}; "
        f"color: {theme.TEXT_PRIMARY}; font-weight: 600; "
        f"border: 1px solid {theme.BORDER}; "
        f"border-radius: {theme.RADIUS_MD}px; "
        f"padding: 6px 14px; }}"
        f"QPushButton:hover {{ background: #2e2e2e; "
        f"border-color: {theme.BORDER_STRONG}; }}"
    )


def _ghost_icon_btn_qss() -> str:
    return (
        f"QPushButton {{ background: transparent; "
        f"border: 1px solid {theme.BORDER_SUBTLE}; "
        f"border-radius: {theme.RADIUS_SM}px; "
        f"padding: 0; }}"
        f"QPushButton:hover {{ background: {theme.BG_RAISED}; "
        f"border-color: {theme.BORDER_STRONG}; }}"
    )


# ── Operator row ─────────────────────────────────────────────────
class _OperatorRow(QWidget):
    """
    One operator entry: colour swatch (clickable to override) +
    name field + delete (x) button.  Stores the resolved colour
    locally so the picker can round-trip explicit overrides
    without losing the swatch when the operator's name changes.
    """

    def __init__(self, name: str, color: str, on_delete, parent=None):
        super().__init__(parent)
        self._color = color
        self._on_delete = on_delete

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        # The line edit has to exist before _refresh_swatch can ask
        # for the resolved colour — _displayed_color() reads name()
        # to fall back through theme.operator_color().
        self.edit = QLineEdit(name)
        self.edit.setPlaceholderText("Role (e.g. Lighting / Audio / Stage Manager)")
        self.edit.textChanged.connect(self._on_name_changed)

        self.swatch = QPushButton()
        self.swatch.setFixedSize(22, 22)
        self.swatch.setCursor(Qt.CursorShape.PointingHandCursor)
        self.swatch.setToolTip("Click to override colour. Right-click to reset.")
        self.swatch.clicked.connect(self._pick_color)
        self.swatch.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.swatch.customContextMenuRequested.connect(lambda _p: self.reset_color())
        self._refresh_swatch()

        lay.addWidget(self.swatch)
        lay.addWidget(self.edit, stretch=1)

        btn_del = QPushButton()
        btn_del.setIcon(make_icon("x", theme.TEXT_DIM))
        btn_del.setIconSize(icon_size(14))
        btn_del.setFixedSize(26, 26)
        btn_del.setStyleSheet(_ghost_icon_btn_qss())
        btn_del.setToolTip("Remove this operator")
        btn_del.clicked.connect(lambda: self._on_delete(self))
        lay.addWidget(btn_del)

    def name(self) -> str:
        return self.edit.text().strip()

    def color(self) -> str:
        """Resolved colour for save — returns "" when the user wants
        to fall back to the theme alias / cycle, "#rrggbb" otherwise."""
        return self._color or ""

    def _on_name_changed(self, _t: str):
        # If we're falling back to the theme resolver, the swatch
        # tracks the new name — but only if the operator hasn't
        # picked an explicit override.
        self._refresh_swatch()

    def _pick_color(self):
        # Pre-fill the picker with the currently displayed colour so
        # the operator can nudge it slightly rather than hunt for the
        # current value.
        current = self._displayed_color()
        col = QColorDialog.getColor(QColor(current), self, "Operator colour")
        if col.isValid():
            self._color = col.name()
            self._refresh_swatch()

    def reset_color(self):
        """Clear an explicit override so the row falls back to the
        theme resolver (alias map for known roles, cycle palette
        for unknown ones)."""
        self._color = ""
        self._refresh_swatch()

    def _displayed_color(self) -> str:
        return self._color or theme.operator_color(self.name())

    def _refresh_swatch(self):
        c = self._displayed_color()
        # Round swatch with subtle border so a dark-grey override
        # is still visible on the dark surface.
        self.swatch.setStyleSheet(
            f"QPushButton {{ background: {c}; "
            f"border: 1px solid {theme.BORDER}; "
            f"border-radius: 11px; }}"
            f"QPushButton:hover {{ border-color: {theme.BORDER_STRONG}; }}"
        )


# ── SettingsDialog ───────────────────────────────────────────────
class SettingsDialog(QDialog):
    def __init__(self, settings: ShowSettings, audio_devices: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Show Settings")
        self.setMinimumWidth(560)
        self.setMinimumHeight(640)
        self._settings = settings
        self._result_settings: Optional[ShowSettings] = None

        self.setStyleSheet(_dialog_qss())

        root = QVBoxLayout(self)
        root.setSpacing(12)
        root.setContentsMargins(18, 14, 18, 14)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setSpacing(14)
        lay.setContentsMargins(0, 0, 0, 0)

        # ── Show ──────────────────────────────────────────────────
        grp_show = QGroupBox("SHOW")
        sl = QFormLayout(grp_show)
        sl.setHorizontalSpacing(12)
        sl.setVerticalSpacing(8)
        self._show_title_edit = QLineEdit(settings.show_title)
        self._show_title_edit.setPlaceholderText("Show title for exports and printouts")
        sl.addRow("Title:", self._show_title_edit)
        lay.addWidget(grp_show)

        # ── Audio Input (LTC) ─────────────────────────────────────
        grp_audio = QGroupBox("AUDIO INPUT (LTC)")
        al = QFormLayout(grp_audio)
        al.setHorizontalSpacing(12)
        al.setVerticalSpacing(8)

        self._audio_devices = audio_devices

        self._combo_device = QComboBox()
        self._combo_device.addItem("(System Default)", "")
        for dev in audio_devices:
            label = f"{dev['name']}  [{dev['channels']}ch]"
            self._combo_device.addItem(label, dev["name"])
        for i in range(self._combo_device.count()):
            if self._combo_device.itemData(i) == settings.audio_device_name:
                self._combo_device.setCurrentIndex(i)
                break
        al.addRow("Device:", self._combo_device)

        self._combo_channel = QComboBox()
        al.addRow("Channel:", self._combo_channel)
        self._combo_device.currentIndexChanged.connect(self._rebuild_channel_combo)
        self._rebuild_channel_combo(preferred=settings.audio_channel)

        lay.addWidget(grp_audio)

        # ── Studio Logo ───────────────────────────────────────────
        grp_logo = QGroupBox("STUDIO LOGO")
        ll = QHBoxLayout(grp_logo)
        ll.setSpacing(8)

        self._logo_path_lbl = QLabel(settings.logo_path or "(none)")
        self._logo_path_lbl.setStyleSheet(
            f"color: {theme.TEXT_MUTED}; font-size: 11px;"
        )
        ll.addWidget(self._logo_path_lbl, stretch=1)

        btn_logo = QPushButton("Choose…")
        btn_logo.setStyleSheet(_secondary_btn_qss())
        btn_logo.clicked.connect(self._pick_logo)
        ll.addWidget(btn_logo)

        btn_clear_logo = QPushButton("Clear")
        btn_clear_logo.setStyleSheet(_secondary_btn_qss())
        btn_clear_logo.clicked.connect(self._clear_logo)
        ll.addWidget(btn_clear_logo)

        lay.addWidget(grp_logo)

        # ── Operators ─────────────────────────────────────────────
        grp_ops = QGroupBox("OPERATORS")
        self._ops_lay = QVBoxLayout(grp_ops)
        self._ops_lay.setSpacing(6)

        self._op_rows: List[_OperatorRow] = []
        # Pair each name with the operator_colors override (if any —
        # empty string means "fall back to theme.operator_color()").
        for name in settings.operator_names:
            self._add_operator_row(name, settings.operator_colors.get(name, ""))

        btn_row = QHBoxLayout()
        btn_add_op = QPushButton(" Add Operator")
        btn_add_op.setIcon(make_icon("plus", theme.TEXT_PRIMARY))
        btn_add_op.setIconSize(icon_size(14))
        btn_add_op.setStyleSheet(_secondary_btn_qss())
        btn_add_op.clicked.connect(lambda: self._add_operator_row("", ""))
        btn_row.addWidget(btn_add_op)
        btn_row.addStretch()
        self._ops_lay.addLayout(btn_row)

        lay.addWidget(grp_ops)

        # ── Web Remote ────────────────────────────────────────────
        grp_remote = QGroupBox("WEB REMOTE")
        rl = QFormLayout(grp_remote)
        rl.setHorizontalSpacing(12)
        rl.setVerticalSpacing(8)

        self._remote_password = QLineEdit(settings.remote_password)
        self._remote_password.setEchoMode(QLineEdit.EchoMode.Password)
        self._remote_password.setPlaceholderText("Required on phones / tablets")
        rl.addRow("Password:", self._remote_password)

        lay.addWidget(grp_remote)

        # ── Performance Mode font sizes ───────────────────────────
        grp_perf = QGroupBox("PERFORMANCE MODE — FONT SIZES")
        pl = QFormLayout(grp_perf)
        pl.setHorizontalSpacing(12)
        pl.setVerticalSpacing(8)

        self._spin_cue_name = self._make_spin(20, 120, settings.perf_cue_name_size)
        pl.addRow("Current Cue Name:", self._spin_cue_name)

        self._spin_cue_desc = self._make_spin(10, 60, settings.perf_cue_desc_size)
        pl.addRow("Current Cue Description:", self._spin_cue_desc)

        self._spin_op_size = self._make_spin(10, 50, settings.perf_operator_size)
        pl.addRow("Operator Comments:", self._spin_op_size)

        self._spin_op_name_size = self._make_spin(8, 30, settings.perf_operator_name_size)
        pl.addRow("Operator Name Label:", self._spin_op_name_size)

        self._spin_next_name = self._make_spin(14, 60, settings.perf_next_name_size)
        pl.addRow("Next Cue Name:", self._spin_next_name)

        self._spin_next_desc = self._make_spin(10, 40, settings.perf_next_desc_size)
        pl.addRow("Next Cue Description:", self._spin_next_desc)

        self._spin_countdown = self._make_spin(16, 72, settings.perf_countdown_size)
        pl.addRow("Countdown Timer:", self._spin_countdown)

        self._chk_countdown = QCheckBox("Show countdown timer")
        self._chk_countdown.setChecked(settings.countdown_enabled)
        pl.addRow("", self._chk_countdown)

        lay.addWidget(grp_perf)

        lay.addStretch()
        scroll.setWidget(content)
        root.addWidget(scroll)

        # ── Action buttons ────────────────────────────────────────
        btn_lay = QHBoxLayout()
        btn_lay.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setStyleSheet(_secondary_btn_qss())
        btn_cancel.clicked.connect(self.reject)
        btn_lay.addWidget(btn_cancel)

        btn_ok = QPushButton("Apply")
        btn_ok.setStyleSheet(_primary_btn_qss())
        btn_ok.setDefault(True)
        btn_ok.clicked.connect(self._apply)
        btn_lay.addWidget(btn_ok)

        root.addLayout(btn_lay)

    # ── helpers ──────────────────────────────────────────────────
    def _make_spin(self, lo: int, hi: int, value: int) -> QSpinBox:
        s = QSpinBox()
        s.setRange(lo, hi)
        s.setValue(value)
        return s

    def _rebuild_channel_combo(self, _unused=None, preferred: Optional[int] = None):
        if preferred is None:
            preferred = self._combo_channel.currentData()
            if preferred is None:
                preferred = 0

        device_name = self._combo_device.currentData() or ""
        max_channels = self._max_channels_for(device_name)

        self._combo_channel.blockSignals(True)
        self._combo_channel.clear()
        for ch in range(max_channels):
            self._combo_channel.addItem(f"Channel {ch + 1} of {max_channels}", ch)
        target = min(max(int(preferred), 0), max_channels - 1)
        self._combo_channel.setCurrentIndex(target)
        self._combo_channel.blockSignals(False)

    def _max_channels_for(self, device_name: str) -> int:
        if device_name:
            for dev in self._audio_devices:
                if dev["name"] == device_name:
                    return max(1, int(dev["channels"]))
        if self._audio_devices:
            return max(1, int(self._audio_devices[0]["channels"]))
        return 2

    def _add_operator_row(self, name: str, color: str):
        row = _OperatorRow(name, color, on_delete=self._remove_operator)
        # Insert before the "+ Add Operator" button row at the bottom
        idx = self._ops_lay.count() - 1
        self._ops_lay.insertWidget(idx, row)
        self._op_rows.append(row)

    def _remove_operator(self, row: _OperatorRow):
        if len(self._op_rows) <= 1:
            return
        self._op_rows.remove(row)
        self._ops_lay.removeWidget(row)
        row.setParent(None)
        row.deleteLater()

    def _pick_logo(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Logo", "",
            "Images (*.png *.jpg *.jpeg *.svg);;All Files (*)"
        )
        if path:
            self._logo_path_lbl.setText(path)

    def _clear_logo(self):
        self._logo_path_lbl.setText("(none)")

    def _apply(self):
        logo = self._logo_path_lbl.text()
        if logo == "(none)":
            logo = ""

        op_names: List[str] = []
        op_colors: Dict[str, str] = {}
        for r in self._op_rows:
            n = r.name()
            if not n:
                continue
            op_names.append(n)
            c = r.color()
            if c:
                op_colors[n] = c

        if not op_names:
            op_names = ["Operator 1"]

        self._result_settings = ShowSettings(
            show_title=self._show_title_edit.text().strip(),
            audio_device_name=self._combo_device.currentData() or "",
            audio_channel=int(self._combo_channel.currentData() or 0),
            logo_path=logo,
            operator_names=op_names,
            operator_colors=op_colors,
            remote_password=self._remote_password.text(),
            perf_cue_name_size=self._spin_cue_name.value(),
            perf_cue_desc_size=self._spin_cue_desc.value(),
            perf_operator_size=self._spin_op_size.value(),
            perf_operator_name_size=self._spin_op_name_size.value(),
            perf_next_name_size=self._spin_next_name.value(),
            perf_next_desc_size=self._spin_next_desc.value(),
            perf_countdown_size=self._spin_countdown.value(),
            countdown_enabled=self._chk_countdown.isChecked(),
        )
        self.accept()

    def get_settings(self) -> Optional[ShowSettings]:
        return self._result_settings
