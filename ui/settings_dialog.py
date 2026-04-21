from __future__ import annotations
from typing import List, Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QSpinBox, QLineEdit, QFileDialog, QGroupBox,
    QFormLayout, QScrollArea, QWidget, QFrame, QCheckBox,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QPixmap

from show_file import ShowSettings


class SettingsDialog(QDialog):
    def __init__(self, settings: ShowSettings, audio_devices: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Show Settings")
        self.setMinimumWidth(520)
        self.setMinimumHeight(600)
        self._settings = settings
        self._result_settings: Optional[ShowSettings] = None

        root = QVBoxLayout(self)
        root.setSpacing(16)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setSpacing(16)
        lay.setContentsMargins(8, 8, 8, 8)

        # ── Audio ─────────────────────────────────────────────────────────────
        grp_audio = QGroupBox("Audio Input (LTC)")
        al = QFormLayout(grp_audio)

        self._audio_devices = audio_devices

        self._combo_device = QComboBox()
        self._combo_device.addItem("(System Default)", "")
        for dev in audio_devices:
            label = f"{dev['name']}  [{dev['channels']}ch]"
            self._combo_device.addItem(label, dev["name"])
        # Select current
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

        # ── Logo ────────────────���──────────────────────��──────────────────────
        grp_logo = QGroupBox("Studio Logo")
        ll = QHBoxLayout(grp_logo)

        self._logo_path_lbl = QLabel(settings.logo_path or "(none)")
        self._logo_path_lbl.setStyleSheet("color: #aaa; font-size: 11px;")
        ll.addWidget(self._logo_path_lbl, stretch=1)

        btn_logo = QPushButton("Choose...")
        btn_logo.clicked.connect(self._pick_logo)
        ll.addWidget(btn_logo)

        btn_clear_logo = QPushButton("Clear")
        btn_clear_logo.clicked.connect(self._clear_logo)
        ll.addWidget(btn_clear_logo)

        lay.addWidget(grp_logo)

        # ── Operators ���────────────────────────────────────────────────────────
        grp_ops = QGroupBox("Operators")
        self._ops_lay = QVBoxLayout(grp_ops)

        self._op_edits: List[QLineEdit] = []
        for name in settings.operator_names:
            self._add_operator_row(name)

        btn_row = QHBoxLayout()
        btn_add_op = QPushButton("+ Add Operator")
        btn_add_op.clicked.connect(lambda: self._add_operator_row(""))
        btn_row.addWidget(btn_add_op)
        btn_row.addStretch()
        self._ops_lay.addLayout(btn_row)

        lay.addWidget(grp_ops)

        # ── Performance Mode ──────────────────────────────────────────────────
        grp_perf = QGroupBox("Performance Mode — Font Sizes")
        pl = QFormLayout(grp_perf)

        self._spin_cue_name = QSpinBox()
        self._spin_cue_name.setRange(20, 120)
        self._spin_cue_name.setValue(settings.perf_cue_name_size)
        pl.addRow("Current Cue Name:", self._spin_cue_name)

        self._spin_cue_desc = QSpinBox()
        self._spin_cue_desc.setRange(10, 60)
        self._spin_cue_desc.setValue(settings.perf_cue_desc_size)
        pl.addRow("Current Cue Description:", self._spin_cue_desc)

        self._spin_op_size = QSpinBox()
        self._spin_op_size.setRange(10, 50)
        self._spin_op_size.setValue(settings.perf_operator_size)
        pl.addRow("Operator Comments:", self._spin_op_size)

        self._spin_op_name_size = QSpinBox()
        self._spin_op_name_size.setRange(8, 30)
        self._spin_op_name_size.setValue(settings.perf_operator_name_size)
        pl.addRow("Operator Name Label:", self._spin_op_name_size)

        self._spin_next_name = QSpinBox()
        self._spin_next_name.setRange(14, 60)
        self._spin_next_name.setValue(settings.perf_next_name_size)
        pl.addRow("Next Cue Name:", self._spin_next_name)

        self._spin_next_desc = QSpinBox()
        self._spin_next_desc.setRange(10, 40)
        self._spin_next_desc.setValue(settings.perf_next_desc_size)
        pl.addRow("Next Cue Description:", self._spin_next_desc)

        self._spin_countdown = QSpinBox()
        self._spin_countdown.setRange(16, 72)
        self._spin_countdown.setValue(settings.perf_countdown_size)
        pl.addRow("Countdown Timer:", self._spin_countdown)

        self._chk_countdown = QCheckBox("Show countdown timer")
        self._chk_countdown.setChecked(settings.countdown_enabled)
        pl.addRow("", self._chk_countdown)

        lay.addWidget(grp_perf)

        lay.addStretch()
        scroll.setWidget(content)
        root.addWidget(scroll)

        # ── Buttons ───────────────────────────────────────────────────────────
        btn_lay = QHBoxLayout()
        btn_lay.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_lay.addWidget(btn_cancel)

        btn_ok = QPushButton("Apply")
        btn_ok.setDefault(True)
        btn_ok.clicked.connect(self._apply)
        btn_lay.addWidget(btn_ok)

        root.addLayout(btn_lay)

    def _rebuild_channel_combo(self, _unused=None, preferred: Optional[int] = None):
        """Populate the channel combo based on the currently selected device."""
        # Preserve existing selection across device changes when possible.
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
        # Clamp preferred to available range
        target = min(max(int(preferred), 0), max_channels - 1)
        self._combo_channel.setCurrentIndex(target)
        self._combo_channel.blockSignals(False)

    def _max_channels_for(self, device_name: str) -> int:
        """Input-channel count for a device, with a safe default for the system default."""
        if device_name:
            for dev in self._audio_devices:
                if dev["name"] == device_name:
                    return max(1, int(dev["channels"]))
        # System default — assume stereo; if the real device has more the user
        # can pick it explicitly.
        if self._audio_devices:
            return max(1, int(self._audio_devices[0]["channels"]))
        return 2

    def _add_operator_row(self, name: str):
        row = QHBoxLayout()
        edit = QLineEdit(name)
        edit.setPlaceholderText(f"Operator {len(self._op_edits) + 1}")
        row.addWidget(edit, stretch=1)

        btn_del = QPushButton("x")
        btn_del.setFixedWidth(28)
        btn_del.clicked.connect(lambda: self._remove_operator(edit, row))
        row.addWidget(btn_del)

        # Insert before the "+ Add" button row
        idx = self._ops_lay.count() - 1
        self._ops_lay.insertLayout(idx, row)
        self._op_edits.append(edit)

    def _remove_operator(self, edit: QLineEdit, layout: QHBoxLayout):
        if len(self._op_edits) <= 1:
            return
        self._op_edits.remove(edit)
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._ops_lay.removeItem(layout)

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

        op_names = [e.text().strip() or e.placeholderText()
                    for e in self._op_edits if e.text().strip() or True]
        # Filter out empty
        op_names = [n for n in op_names if n]
        if not op_names:
            op_names = ["Operator 1"]

        self._result_settings = ShowSettings(
            audio_device_name=self._combo_device.currentData() or "",
            audio_channel=int(self._combo_channel.currentData() or 0),
            logo_path=logo,
            operator_names=op_names,
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
