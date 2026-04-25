"""
Remote Access panel — shows URLs and QR codes for web remote connections.
"""
from __future__ import annotations
from typing import Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QWidget,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QPixmap, QImage

from web_remote import get_local_ip, generate_qr_data_uri

import base64


class RemotePanel(QDialog):
    """Dialog showing remote access URLs and QR codes."""

    def __init__(self, port: int, password: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Remote Access")
        self.setMinimumWidth(620)
        self.setMinimumHeight(500)

        ip = get_local_ip()
        base_url = f"http://{ip}:{port}"

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        # Title
        title = QLabel("Remote Access — Performance View")
        ft = QFont(); ft.setPointSize(16); ft.setBold(True)
        title.setFont(ft)
        title.setStyleSheet("color: #dcdcdc;")
        root.addWidget(title)

        hint = QLabel(
            "Devices on the same WiFi network can open one shared link.\n"
            "On the page they choose operator name and enter the password shown below."
        )
        hint.setStyleSheet("color: #888; font-size: 12px;")
        hint.setWordWrap(True)
        root.addWidget(hint)

        root.addWidget(_hline())

        # Scroll area for links
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        clay = QVBoxLayout(content)
        clay.setSpacing(16)
        clay.setContentsMargins(0, 0, 0, 0)

        # Single shared URL
        clay.addWidget(self._make_entry(
            "Shared Remote Link",
            base_url,
        ))

        if password:
            pwd_frame = QFrame()
            pwd_frame.setStyleSheet(
                "QFrame { background: #111; border: 1px solid #333; border-radius: 8px; }"
            )
            pwd_lay = QVBoxLayout(pwd_frame)
            pwd_lay.setContentsMargins(14, 12, 14, 12)
            pwd_lay.setSpacing(4)

            pwd_tag = QLabel("ACCESS PASSWORD")
            pwd_tag.setStyleSheet("color: #888; font-size: 11px; font-weight: bold; letter-spacing: 2px;")
            pwd_lay.addWidget(pwd_tag)

            pwd = QLabel(password)
            pwd.setStyleSheet("color: #f0f0f0; font-size: 24px; font-weight: bold;")
            pwd.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            pwd_lay.addWidget(pwd)
            clay.addWidget(pwd_frame)
        else:
            pwd_frame = QFrame()
            pwd_frame.setStyleSheet(
                "QFrame { background: #111; border: 1px solid #333; border-radius: 8px; }"
            )
            pwd_lay = QVBoxLayout(pwd_frame)
            pwd_lay.setContentsMargins(14, 12, 14, 12)
            pwd_lay.setSpacing(4)

            pwd_tag = QLabel("ACCESS PASSWORD")
            pwd_tag.setStyleSheet("color: #888; font-size: 11px; font-weight: bold; letter-spacing: 2px;")
            pwd_lay.addWidget(pwd_tag)

            pwd = QLabel("Not set")
            pwd.setStyleSheet("color: #c8c8c8; font-size: 18px; font-weight: bold;")
            pwd_lay.addWidget(pwd)

            pwd_hint = QLabel("Open Settings to add a password for phones and tablets.")
            pwd_hint.setStyleSheet("color: #777; font-size: 11px;")
            pwd_hint.setWordWrap(True)
            pwd_lay.addWidget(pwd_hint)
            clay.addWidget(pwd_frame)

        clay.addStretch()
        scroll.setWidget(content)
        root.addWidget(scroll, stretch=1)

        # Close
        btn_close = QPushButton("Close")
        btn_close.setFixedWidth(80)
        btn_close.clicked.connect(self.accept)
        root.addWidget(btn_close, alignment=Qt.AlignmentFlag.AlignRight)

    def _make_entry(self, label: str, url: str) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet(
            "QFrame { background: #1a1a1a; border: 1px solid #333; border-radius: 6px; }"
        )
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(12)

        # QR code
        qr_data = generate_qr_data_uri(url)
        qr_lbl = QLabel()
        if qr_data:
            b64 = qr_data.split(",", 1)[1]
            img_data = base64.b64decode(b64)
            img = QImage()
            img.loadFromData(img_data)
            pix = QPixmap.fromImage(img).scaled(
                180, 180, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            qr_lbl.setPixmap(pix)
        else:
            qr_lbl.setText("(no qrcode)")
            qr_lbl.setStyleSheet("color: #555; font-size: 10px;")
        qr_lbl.setFixedSize(180, 180)
        lay.addWidget(qr_lbl)

        # Text info
        info_lay = QVBoxLayout()
        info_lay.setSpacing(4)

        name_lbl = QLabel(label)
        name_lbl.setStyleSheet("color: #dcdcdc; font-weight: bold; font-size: 13px;")
        info_lay.addWidget(name_lbl)

        url_lbl = QLabel(url)
        url_lbl.setStyleSheet("color: #4a90d9; font-size: 12px; font-family: Menlo;")
        url_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        info_lay.addWidget(url_lbl)

        info_lay.addStretch()
        lay.addLayout(info_lay, stretch=1)

        return frame


def _hline() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    f.setStyleSheet("color: #333;")
    return f
