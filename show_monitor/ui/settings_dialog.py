"""
SHOW MONITOR settings dialog.

Based on the pattern of ui/settings_dialog.py in the classic CUE MONITOR
— same visual language, adapted to the SHOW MONITOR's settings:
operators, drift threshold, performance clock appearance, and the
performance-mode font sizes.
"""
from __future__ import annotations

from typing import List, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QDialog, QDoubleSpinBox, QFileDialog,
    QFormLayout, QFrame, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

from ..scene_model import ShowSettings


class SettingsDialog(QDialog):
    def __init__(self, settings: ShowSettings, audio_devices: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Show Settings")
        self.setMinimumWidth(520)
        self.setMinimumHeight(640)
        self._settings = settings
        self._audio_devices = audio_devices
        self._result: Optional[ShowSettings] = None

        root = QVBoxLayout(self)
        root.setSpacing(16)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setSpacing(16)
        lay.setContentsMargins(8, 8, 8, 8)

        # ── Logo ────
        grp_logo = QGroupBox("Studio Logo")
        ll = QHBoxLayout(grp_logo)
        self._logo_path = settings.logo_path or ""
        self._logo_lbl = QLabel(self._logo_path or "(none)")
        self._logo_lbl.setStyleSheet("color: #aaa; font-size: 11px;")
        ll.addWidget(self._logo_lbl, stretch=1)
        btn_pick = QPushButton("Choose…")
        btn_pick.clicked.connect(self._pick_logo)
        ll.addWidget(btn_pick)
        btn_clear = QPushButton("Clear")
        btn_clear.clicked.connect(self._clear_logo)
        ll.addWidget(btn_clear)
        lay.addWidget(grp_logo)

        # ── Audio (LTC) ────
        grp_audio = QGroupBox("Audio Input (LTC)")
        al = QFormLayout(grp_audio)

        self._combo_device = QComboBox()
        self._combo_device.addItem("(Off — no LTC)", "")
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

        # ── Operators ────
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

        # ── Clock / NTP ────
        grp_clock = QGroupBox("World Clock")
        cl = QFormLayout(grp_clock)

        self._spin_drift = QDoubleSpinBox()
        self._spin_drift.setRange(0.1, 60.0)
        self._spin_drift.setDecimals(1)
        self._spin_drift.setSuffix(" s")
        self._spin_drift.setValue(settings.drift_warning_seconds)
        cl.addRow("NTP drift warning threshold:", self._spin_drift)

        lay.addWidget(grp_clock)

        # ── Performance Clock ────
        grp_pclock = QGroupBox("Performance Clock")
        pcl = QFormLayout(grp_pclock)

        self._spin_clock = QSpinBox()
        self._spin_clock.setRange(32, 300)
        self._spin_clock.setValue(settings.perf_clock_size)
        pcl.addRow("Clock size:", self._spin_clock)

        color_row = QHBoxLayout()
        self._clock_color = settings.perf_clock_color or "#ffffff"
        self._clock_color_swatch = QLabel()
        self._clock_color_swatch.setFixedSize(24, 24)
        self._refresh_swatch()
        color_row.addWidget(self._clock_color_swatch)
        btn_color = QPushButton("Choose colour…")
        btn_color.clicked.connect(self._pick_color)
        color_row.addWidget(btn_color)
        color_row.addStretch()
        pcl.addRow("Clock colour:", self._wrap_layout(color_row))

        lay.addWidget(grp_pclock)

        # ── Performance fonts ────
        grp_perf = QGroupBox("Performance Mode — Font Sizes")
        pl = QFormLayout(grp_perf)

        self._spin_cue_name = self._mk_spin(20, 120, settings.perf_cue_name_size)
        pl.addRow("Current Cue Name:", self._spin_cue_name)

        self._spin_cue_desc = self._mk_spin(10, 60, settings.perf_cue_desc_size)
        pl.addRow("Current Cue Description:", self._spin_cue_desc)

        self._spin_op_size = self._mk_spin(10, 50, settings.perf_operator_size)
        pl.addRow("Operator Comments:", self._spin_op_size)

        self._spin_op_name_size = self._mk_spin(8, 30, settings.perf_operator_name_size)
        pl.addRow("Operator Name Label:", self._spin_op_name_size)

        self._spin_next_name = self._mk_spin(14, 60, settings.perf_next_name_size)
        pl.addRow("Next Cue Name:", self._spin_next_name)

        self._spin_next_desc = self._mk_spin(10, 40, settings.perf_next_desc_size)
        pl.addRow("Next Cue Description:", self._spin_next_desc)

        lay.addWidget(grp_perf)

        lay.addStretch()
        scroll.setWidget(content)
        root.addWidget(scroll)

        # ── Buttons ────
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

    # ── helpers ────
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

    def _mk_spin(self, lo: int, hi: int, val: int) -> QSpinBox:
        s = QSpinBox()
        s.setRange(lo, hi)
        s.setValue(val)
        return s

    def _wrap_layout(self, hl: QHBoxLayout) -> QWidget:
        w = QWidget()
        w.setLayout(hl)
        return w

    def _add_operator_row(self, name: str):
        row = QHBoxLayout()
        edit = QLineEdit(name)
        edit.setPlaceholderText(f"Operator {len(self._op_edits) + 1}")
        row.addWidget(edit, stretch=1)

        btn_del = QPushButton("x")
        btn_del.setFixedWidth(28)
        btn_del.clicked.connect(lambda: self._remove_operator(edit, row))
        row.addWidget(btn_del)

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

    def _refresh_swatch(self):
        self._clock_color_swatch.setStyleSheet(
            f"background: {self._clock_color}; border: 1px solid #555;"
        )

    def _pick_color(self):
        col = QColorDialog.getColor(QColor(self._clock_color), self, "Clock colour")
        if col.isValid():
            self._clock_color = col.name()
            self._refresh_swatch()

    def _pick_logo(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Logo", "", "Images (*.png *.jpg *.jpeg *.svg);;All Files (*)",
        )
        if path:
            self._logo_path = path
            self._logo_lbl.setText(path)

    def _clear_logo(self):
        self._logo_path = ""
        self._logo_lbl.setText("(none)")

    def _apply(self):
        op_names = [e.text().strip() for e in self._op_edits if e.text().strip()]
        if not op_names:
            op_names = ["Operator 1"]

        self._result = ShowSettings(
            operator_names=op_names,
            audio_device_name=self._combo_device.currentData() or "",
            audio_channel=int(self._combo_channel.currentData() or 0),
            drift_warning_seconds=float(self._spin_drift.value()),
            perf_clock_size=self._spin_clock.value(),
            perf_clock_color=self._clock_color,
            perf_cue_name_size=self._spin_cue_name.value(),
            perf_cue_desc_size=self._spin_cue_desc.value(),
            perf_operator_size=self._spin_op_size.value(),
            perf_operator_name_size=self._spin_op_name_size.value(),
            perf_next_name_size=self._spin_next_name.value(),
            perf_next_desc_size=self._spin_next_desc.value(),
            logo_path=self._logo_path,
        )
        self.accept()

    def get_settings(self) -> Optional[ShowSettings]:
        return self._result
