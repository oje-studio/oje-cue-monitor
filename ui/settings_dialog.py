from __future__ import annotations
from typing import List, Optional, Dict

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QSpinBox, QLineEdit, QFileDialog, QGroupBox,
    QFormLayout, QScrollArea, QWidget, QFrame, QCheckBox,
    QColorDialog, QTabWidget, QSizePolicy, QGraphicsDropShadowEffect,
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QFont, QPixmap, QColor

from show_file import ShowSettings
from ui import theme
from ui.fonts import mono_font, sans_font
from ui.icons import make_icon, icon_size


# ── Tab bar + widget styling ────────────────────────────────────
def _tab_qss() -> str:
    return (
        f"QTabWidget::pane {{ "
        f"border: 1px solid {theme.BORDER_SUBTLE}; "
        f"border-top: none; "
        f"background: {theme.BG_APP}; }}"

        f"QTabBar::tab {{ "
        f"background: {theme.BG_SURFACE}; "
        f"color: {theme.TEXT_MUTED}; "
        f"border: 1px solid {theme.BORDER_SUBTLE}; "
        f"border-bottom: none; "
        f"padding: 10px 20px; "
        f"font-size: 11px; font-weight: 600; "
        f"letter-spacing: 1.5px; "
        f"margin-right: 2px; "
        f"border-top-left-radius: {theme.RADIUS_MD}px; "
        f"border-top-right-radius: {theme.RADIUS_MD}px; }}"

        f"QTabBar::tab:selected {{ "
        f"background: {theme.BG_APP}; "
        f"color: {theme.TEXT_BRIGHT}; "
        f"border-bottom: 2px solid {theme.SEMANTIC_INFO}; }}"

        f"QTabBar::tab:hover:!selected {{ "
        f"background: {theme.BG_RAISED}; "
        f"color: {theme.TEXT_PRIMARY}; }}"
    )


def _dialog_qss() -> str:
    return (
        f"QDialog {{ background: {theme.BG_APP}; }}"
        f"QScrollArea, QScrollArea > QWidget > QWidget "
        f"{{ background: transparent; border: none; }}"
        f"QLabel {{ color: {theme.TEXT_PRIMARY}; }}"

        f"QLineEdit, QSpinBox, QComboBox {{ "
        f"background: {theme.BG_INPUT}; "
        f"color: {theme.TEXT_PRIMARY}; "
        f"border: 1px solid {theme.BORDER}; "
        f"border-radius: {theme.RADIUS_SM}px; "
        f"padding: 6px 10px; min-height: 20px; "
        f"selection-background-color: {theme.BG_RAISED}; }}"
        f"QLineEdit:focus, QSpinBox:focus, QComboBox:focus "
        f"{{ border-color: {theme.SEMANTIC_INFO}; }}"
        f"QComboBox::drop-down {{ width: 20px; border: none; }}"

        f"QCheckBox {{ color: {theme.TEXT_PRIMARY}; spacing: 8px; }}"
        f"QCheckBox::indicator {{ width: 18px; height: 18px; "
        f"border: 1px solid {theme.BORDER}; border-radius: {theme.RADIUS_SM}px; "
        f"background: {theme.BG_INPUT}; }}"
        f"QCheckBox::indicator:checked {{ "
        f"background: {theme.SEMANTIC_INFO}; "
        f"border-color: {theme.SEMANTIC_INFO}; }}"

        + _tab_qss()
    )


def _primary_btn_qss() -> str:
    return (
        f"QPushButton {{ background: {theme.ACTION_PRIMARY}; "
        f"color: white; font-weight: 700; letter-spacing: 1px; "
        f"border: none; border-radius: {theme.RADIUS_MD}px; "
        f"padding: 10px 24px; font-size: 13px; }}"
        f"QPushButton:hover {{ background: {theme.ACTION_PRIMARY_HOVER}; }}"
        f"QPushButton:pressed {{ background: #28A85E; }}"
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
        f"QPushButton:pressed {{ background: #1a1a1a; }}"
    )


def _ghost_icon_btn_qss() -> str:
    return (
        f"QPushButton {{ background: transparent; "
        f"border: 1px solid {theme.BORDER_SUBTLE}; "
        f"border-radius: {theme.RADIUS_SM}px; "
        f"padding: 0; }}"
        f"QPushButton:hover {{ background: {theme.BG_RAISED}; "
        f"border-color: {theme.BORDER_STRONG}; }}"
        f"QPushButton:pressed {{ background: {theme.BG_SURFACE}; }}"
    )


# ── Helpers ─────────────────────────────────────────────────────

def _section_label(text: str) -> QLabel:
    lbl = QLabel(text.upper())
    lbl.setStyleSheet(
        f"color: {theme.TEXT_MUTED}; font-size: 11px; "
        f"font-weight: 600; letter-spacing: 1.5px; "
        f"padding: 0; margin: 0;"
    )
    return lbl


def _field_label(text: str) -> QLabel:
    lbl = QLabel(text.upper())
    lbl.setStyleSheet(
        f"color: {theme.TEXT_DIM}; font-size: 10px; "
        f"font-weight: 600; letter-spacing: 1px; "
        f"margin-bottom: 2px;"
    )
    return lbl


def _hint_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(f"color: {theme.TEXT_DIM}; font-size: 11px;")
    lbl.setWordWrap(True)
    return lbl


def _section_card() -> QFrame:
    card = QFrame()
    card.setStyleSheet(
        f"QFrame {{ background: {theme.BG_SURFACE}; "
        f"border: 1px solid {theme.BORDER_SUBTLE}; "
        f"border-radius: {theme.RADIUS_LG}px; }}"
    )
    return card


def _divider() -> QFrame:
    d = QFrame()
    d.setFrameShape(QFrame.Shape.HLine)
    d.setFixedHeight(1)
    d.setStyleSheet(f"background: {theme.BORDER_SUBTLE}; border: none;")
    return d


# ── Operator row ─────────────────────────────────────────────────
class _OperatorRow(QWidget):
    def __init__(self, name: str, color: str, on_delete, parent=None):
        super().__init__(parent)
        self._color = color
        self._on_delete = on_delete
        self.setStyleSheet(
            f"_OperatorRow {{ border-radius: {theme.RADIUS_SM}px; }}"
            f"_OperatorRow:hover {{ background: {theme.BG_RAISED}; }}"
        )

        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(10)

        self.edit = QLineEdit(name)
        self.edit.setPlaceholderText("Role name (e.g. Lighting, Audio, Stage Manager)")
        self.edit.textChanged.connect(self._on_name_changed)

        self.swatch = QPushButton()
        self.swatch.setFixedSize(24, 24)
        self.swatch.setCursor(Qt.CursorShape.PointingHandCursor)
        self.swatch.setToolTip("Click to override colour. Right-click to reset.")
        self.swatch.clicked.connect(self._pick_color)
        self.swatch.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.swatch.customContextMenuRequested.connect(lambda _p: self.reset_color())
        self._refresh_swatch()

        lay.addWidget(self.swatch)
        lay.addWidget(self.edit, stretch=1)

        btn_del = QPushButton()
        btn_del.setIcon(make_icon("x", theme.SEMANTIC_DANGER))
        btn_del.setIconSize(icon_size(14))
        btn_del.setFixedSize(28, 28)
        btn_del.setStyleSheet(_ghost_icon_btn_qss())
        btn_del.setToolTip("Remove this operator")
        btn_del.clicked.connect(lambda: self._on_delete(self))
        lay.addWidget(btn_del)

    def name(self) -> str:
        return self.edit.text().strip()

    def color(self) -> str:
        return self._color or ""

    def _on_name_changed(self, _t: str):
        self._refresh_swatch()

    def _pick_color(self):
        current = self._displayed_color()
        col = QColorDialog.getColor(QColor(current), self, "Operator colour")
        if col.isValid():
            self._color = col.name()
            self._refresh_swatch()

    def reset_color(self):
        self._color = ""
        self._refresh_swatch()

    def _displayed_color(self) -> str:
        return self._color or theme.operator_color(self.name())

    def _refresh_swatch(self):
        c = self._displayed_color()
        self.swatch.setStyleSheet(
            f"QPushButton {{ background: {c}; "
            f"border: 1px solid {theme.BORDER}; "
            f"border-radius: 12px; }}"
            f"QPushButton:hover {{ border-color: {theme.BORDER_STRONG}; "
            f"border-width: 2px; }}"
        )


# ── Font size preview ────────────────────────────────────────────

class _FontPreview(QFrame):
    """Live preview of Performance Mode font sizes."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            f"_FontPreview {{ background: #090909; "
            f"border: 1px solid {theme.BORDER_SUBTLE}; "
            f"border-radius: {theme.RADIUS_LG}px; }}"
        )
        self.setMinimumHeight(200)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 16)
        root.setSpacing(4)

        tag = QLabel("CURRENT CUE")
        tag.setStyleSheet(
            f"color: {theme.TEXT_DIM}; font-size: 10px; "
            f"font-weight: 600; letter-spacing: 3px;"
        )
        root.addWidget(tag)

        self._name_lbl = QLabel("Opening Number")
        self._name_lbl.setStyleSheet(f"color: {theme.TEXT_BRIGHT};")
        self._name_lbl.setWordWrap(True)
        root.addWidget(self._name_lbl)

        self._desc_lbl = QLabel("Full cast on stage, house lights down")
        self._desc_lbl.setStyleSheet(f"color: {theme.TEXT_MUTED};")
        self._desc_lbl.setWordWrap(True)
        root.addWidget(self._desc_lbl)

        # Operator preview
        op_row = QHBoxLayout()
        op_row.setSpacing(16)
        op_row.setContentsMargins(0, 8, 0, 0)

        self._op_name_lbl = QLabel("LIGHTING")
        self._op_name_lbl.setStyleSheet(
            f"color: {theme.OPERATOR_LIGHTING}; font-weight: 600; "
            f"letter-spacing: 1.5px;"
        )
        op_row.addWidget(self._op_name_lbl)

        self._op_comment_lbl = QLabel("Cue 12 GO — follow spot on lead")
        self._op_comment_lbl.setStyleSheet(f"color: {theme.TEXT_BRIGHT};")
        op_row.addWidget(self._op_comment_lbl, stretch=1)
        root.addLayout(op_row)

        root.addWidget(_divider())

        # Next cue section
        nr = QHBoxLayout()
        nr.setContentsMargins(0, 4, 0, 0)

        next_left = QVBoxLayout()
        next_left.setSpacing(2)

        next_tag = QLabel("UP NEXT")
        next_tag.setStyleSheet(
            f"color: {theme.TEXT_DIM}; font-size: 10px; "
            f"font-weight: 600; letter-spacing: 3px;"
        )
        next_left.addWidget(next_tag)

        self._next_name_lbl = QLabel("Scene Change")
        self._next_name_lbl.setStyleSheet(f"color: {theme.TEXT_PRIMARY};")
        next_left.addWidget(self._next_name_lbl)

        self._next_desc_lbl = QLabel("Transition to Act 2")
        self._next_desc_lbl.setStyleSheet(f"color: {theme.TEXT_MUTED};")
        next_left.addWidget(self._next_desc_lbl)

        nr.addLayout(next_left, stretch=1)

        self._cd_lbl = QLabel("01:24")
        self._cd_lbl.setStyleSheet(f"color: {theme.TEXT_BRIGHT};")
        self._cd_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        nr.addWidget(self._cd_lbl)

        root.addLayout(nr)
        root.addStretch()

    def update_sizes(self, cue_name: int, cue_desc: int, op_size: int,
                     op_name_size: int, next_name: int, next_desc: int,
                     countdown: int):
        # Scale down proportionally for the preview panel
        scale = 0.45

        f = sans_font(max(8, int(cue_name * scale)), bold=True)
        self._name_lbl.setFont(f)

        f = sans_font(max(8, int(cue_desc * scale)))
        self._desc_lbl.setFont(f)

        f = sans_font(max(7, int(op_size * scale)))
        self._op_comment_lbl.setFont(f)

        f = sans_font(max(7, int(op_name_size * scale)), bold=True)
        self._op_name_lbl.setFont(f)

        f = sans_font(max(7, int(next_name * scale)), bold=True)
        self._next_name_lbl.setFont(f)

        f = sans_font(max(7, int(next_desc * scale)))
        self._next_desc_lbl.setFont(f)

        f = mono_font(max(8, int(countdown * scale)), bold=True)
        self._cd_lbl.setFont(f)


# ── SettingsDialog ───────────────────────────────────────────────
class SettingsDialog(QDialog):
    def __init__(self, settings: ShowSettings, audio_devices: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Show Settings")
        self.setMinimumWidth(620)
        self.setMinimumHeight(680)
        self._settings = settings
        self._result_settings: Optional[ShowSettings] = None
        self._audio_devices = audio_devices

        self.setStyleSheet(_dialog_qss())

        root = QVBoxLayout(self)
        root.setSpacing(0)
        root.setContentsMargins(0, 0, 0, 0)

        # ── Header ───────────────────────────────────────────────
        header = QWidget()
        header.setStyleSheet(f"background: {theme.BG_HEADER};")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(24, 16, 24, 16)
        hl.setSpacing(12)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(make_icon("edit", theme.TEXT_MUTED).pixmap(24, 24))
        hl.addWidget(icon_lbl)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title = QLabel("Show Settings")
        title.setFont(sans_font(16, bold=True))
        title.setStyleSheet(f"color: {theme.TEXT_BRIGHT};")
        title_col.addWidget(title)

        subtitle = QLabel(settings.show_title or "Untitled Show")
        subtitle.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 12px;")
        self._header_subtitle = subtitle
        title_col.addWidget(subtitle)

        hl.addLayout(title_col)
        hl.addStretch()
        root.addWidget(header)

        # ── Tabs ─────────────────────────────────────────────────
        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_show_tab(settings), "SHOW")
        self._tabs.addTab(self._build_operators_tab(settings), "OPERATORS")
        self._tabs.addTab(self._build_remote_tab(settings), "REMOTE")
        self._tabs.addTab(self._build_perf_tab(settings), "PERFORMANCE")
        root.addWidget(self._tabs, stretch=1)

        # ── Action bar ───────────────────────────────────────────
        root.addWidget(_divider())
        action_bar = QWidget()
        action_bar.setStyleSheet(f"background: {theme.BG_HEADER};")
        al = QHBoxLayout(action_bar)
        al.setContentsMargins(24, 14, 24, 14)
        al.setSpacing(12)
        al.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setStyleSheet(_secondary_btn_qss())
        btn_cancel.setFixedHeight(36)
        btn_cancel.clicked.connect(self.reject)
        al.addWidget(btn_cancel)

        btn_ok = QPushButton("  Apply Settings")
        btn_ok.setIcon(make_icon("check", "#ffffff"))
        btn_ok.setIconSize(icon_size(16))
        btn_ok.setStyleSheet(_primary_btn_qss())
        btn_ok.setFixedHeight(36)
        btn_ok.setDefault(True)
        btn_ok.clicked.connect(self._apply)
        al.addWidget(btn_ok)
        root.addWidget(action_bar)

    # ── Tab: Show ─────────────────────────────────────────────────

    def _build_show_tab(self, settings: ShowSettings) -> QWidget:
        page = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setSpacing(20)
        lay.setContentsMargins(24, 24, 24, 24)

        # ── Title ─────────────────────────────────────
        lay.addWidget(_section_label("Show Information"))
        card = _section_card()
        cl = QVBoxLayout(card)
        cl.setContentsMargins(16, 16, 16, 16)
        cl.setSpacing(12)

        cl.addWidget(_field_label("Title"))
        self._show_title_edit = QLineEdit(settings.show_title)
        self._show_title_edit.setPlaceholderText("Show title for exports and printouts")
        self._show_title_edit.textChanged.connect(
            lambda t: self._header_subtitle.setText(t or "Untitled Show")
        )
        cl.addWidget(self._show_title_edit)

        lay.addWidget(card)

        # ── Audio ─────────────────────────────────────
        lay.addWidget(_section_label("Audio Input (LTC)"))
        card2 = _section_card()
        cl2 = QVBoxLayout(card2)
        cl2.setContentsMargins(16, 16, 16, 16)
        cl2.setSpacing(12)

        cl2.addWidget(_field_label("Device"))
        self._combo_device = QComboBox()
        self._combo_device.addItem("(System Default)", "")
        for dev in self._audio_devices:
            label = f"{dev['name']}  [{dev['channels']}ch]"
            self._combo_device.addItem(label, dev["name"])
        for i in range(self._combo_device.count()):
            if self._combo_device.itemData(i) == settings.audio_device_name:
                self._combo_device.setCurrentIndex(i)
                break
        cl2.addWidget(self._combo_device)

        cl2.addWidget(_field_label("Channel"))
        self._combo_channel = QComboBox()
        cl2.addWidget(self._combo_channel)
        self._combo_device.currentIndexChanged.connect(self._rebuild_channel_combo)
        self._rebuild_channel_combo(preferred=settings.audio_channel)

        lay.addWidget(card2)

        # ── Logo ──────────────────────────────────────
        lay.addWidget(_section_label("Studio Logo"))
        card3 = _section_card()
        cl3 = QVBoxLayout(card3)
        cl3.setContentsMargins(16, 16, 16, 16)
        cl3.setSpacing(12)

        # Preview
        self._logo_preview = QLabel()
        self._logo_preview.setFixedHeight(60)
        self._logo_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._logo_preview.setStyleSheet(
            f"background: {theme.BG_INPUT}; "
            f"border: 1px dashed {theme.BORDER}; "
            f"border-radius: {theme.RADIUS_SM}px;"
        )
        self._update_logo_preview(settings.logo_path)
        cl3.addWidget(self._logo_preview)

        self._logo_path_lbl = QLabel(settings.logo_path or "(none)")
        self._logo_path_lbl.setStyleSheet(
            f"color: {theme.TEXT_DIM}; font-size: 10px;"
        )
        self._logo_path_lbl.setWordWrap(True)
        cl3.addWidget(self._logo_path_lbl)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_logo = QPushButton("  Choose…")
        btn_logo.setIcon(make_icon("plus", theme.TEXT_PRIMARY))
        btn_logo.setIconSize(icon_size(14))
        btn_logo.setStyleSheet(_secondary_btn_qss())
        btn_logo.clicked.connect(self._pick_logo)
        btn_row.addWidget(btn_logo)

        btn_clear = QPushButton("Clear")
        btn_clear.setStyleSheet(_secondary_btn_qss())
        btn_clear.clicked.connect(self._clear_logo)
        btn_row.addWidget(btn_clear)
        btn_row.addStretch()
        cl3.addLayout(btn_row)

        lay.addWidget(card3)

        lay.addStretch()
        scroll.setWidget(content)

        page_lay = QVBoxLayout(page)
        page_lay.setContentsMargins(0, 0, 0, 0)
        page_lay.addWidget(scroll)
        return page

    # ── Tab: Operators ────────────────────────────────────────────

    def _build_operators_tab(self, settings: ShowSettings) -> QWidget:
        page = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setSpacing(16)
        lay.setContentsMargins(24, 24, 24, 24)

        lay.addWidget(_section_label("Operator Roles"))
        lay.addWidget(_hint_label(
            "Operators appear as columns in Performance Mode and as comment "
            "sections in the Web Remote. Click a colour swatch to override, "
            "right-click to reset to automatic."
        ))

        card = _section_card()
        self._ops_lay = QVBoxLayout(card)
        self._ops_lay.setContentsMargins(12, 12, 12, 12)
        self._ops_lay.setSpacing(4)

        self._op_rows: List[_OperatorRow] = []
        for name in settings.operator_names:
            self._add_operator_row(name, settings.operator_colors.get(name, ""))

        # Add button
        btn_add = QPushButton("  Add Operator")
        btn_add.setIcon(make_icon("plus", theme.SEMANTIC_INFO))
        btn_add.setIconSize(icon_size(14))
        btn_add.setFixedHeight(36)
        btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add.setStyleSheet(
            f"QPushButton {{ background: transparent; "
            f"color: {theme.SEMANTIC_INFO}; font-weight: 600; "
            f"border: 1px dashed {theme.BORDER}; "
            f"border-radius: {theme.RADIUS_MD}px; "
            f"padding: 0 14px; }}"
            f"QPushButton:hover {{ background: {theme.with_alpha(theme.SEMANTIC_INFO, 0.08)}; "
            f"border-color: {theme.SEMANTIC_INFO}; }}"
            f"QPushButton:pressed {{ background: {theme.with_alpha(theme.SEMANTIC_INFO, 0.04)}; }}"
        )
        btn_add.clicked.connect(lambda: self._add_operator_row("", ""))
        self._ops_lay.addWidget(btn_add)

        lay.addWidget(card)
        lay.addStretch()

        scroll.setWidget(content)
        page_lay = QVBoxLayout(page)
        page_lay.setContentsMargins(0, 0, 0, 0)
        page_lay.addWidget(scroll)
        return page

    # ── Tab: Remote ───────────────────────────────────────────────

    def _build_remote_tab(self, settings: ShowSettings) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setSpacing(20)
        lay.setContentsMargins(24, 24, 24, 24)

        lay.addWidget(_section_label("Web Remote Access"))
        lay.addWidget(_hint_label(
            "Set a password to require authentication when operators "
            "connect to the Web Remote from their phones or tablets. "
            "Leave empty for open access on the local network."
        ))

        card = _section_card()
        cl = QVBoxLayout(card)
        cl.setContentsMargins(16, 16, 16, 16)
        cl.setSpacing(12)

        cl.addWidget(_field_label("Password"))

        pw_row = QHBoxLayout()
        pw_row.setSpacing(8)
        self._remote_password = QLineEdit(settings.remote_password)
        self._remote_password.setEchoMode(QLineEdit.EchoMode.Password)
        self._remote_password.setPlaceholderText("Enter password for remote access")
        pw_row.addWidget(self._remote_password, stretch=1)

        self._pw_visible = False
        self._btn_eye = QPushButton()
        self._btn_eye.setFixedSize(36, 36)
        self._btn_eye.setToolTip("Show / hide password")
        self._btn_eye.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_eye.setStyleSheet(_ghost_icon_btn_qss())
        self._update_eye_icon()
        self._btn_eye.clicked.connect(self._toggle_password_visibility)
        pw_row.addWidget(self._btn_eye)

        cl.addLayout(pw_row)
        cl.addWidget(_hint_label(
            "The password is shown in the Remote panel on this Mac so "
            "operators can read it off the screen."
        ))

        lay.addWidget(card)
        lay.addStretch()
        return page

    # ── Tab: Performance ──────────────────────────────────────────

    def _build_perf_tab(self, settings: ShowSettings) -> QWidget:
        page = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setSpacing(20)
        lay.setContentsMargins(24, 24, 24, 24)

        # ── Live preview ──────────────────────────────
        lay.addWidget(_section_label("Live Preview"))
        self._font_preview = _FontPreview()
        shadow = QGraphicsDropShadowEffect(self._font_preview)
        shadow.setBlurRadius(20)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 100))
        self._font_preview.setGraphicsEffect(shadow)
        lay.addWidget(self._font_preview)

        # ── Current Cue sizes ─────────────────────────
        lay.addWidget(_section_label("Current Cue"))
        card1 = _section_card()
        cl1 = QVBoxLayout(card1)
        cl1.setContentsMargins(16, 16, 16, 16)
        cl1.setSpacing(14)

        self._spin_cue_name = self._make_spin_row(
            cl1, "Cue Name", 20, 120, settings.perf_cue_name_size
        )
        self._spin_cue_desc = self._make_spin_row(
            cl1, "Description", 10, 60, settings.perf_cue_desc_size
        )
        self._spin_op_size = self._make_spin_row(
            cl1, "Operator Comments", 10, 50, settings.perf_operator_size
        )
        self._spin_op_name_size = self._make_spin_row(
            cl1, "Operator Name Label", 8, 30, settings.perf_operator_name_size
        )
        lay.addWidget(card1)

        # ── Next Cue sizes ────────────────────────────
        lay.addWidget(_section_label("Next Cue"))
        card2 = _section_card()
        cl2 = QVBoxLayout(card2)
        cl2.setContentsMargins(16, 16, 16, 16)
        cl2.setSpacing(14)

        self._spin_next_name = self._make_spin_row(
            cl2, "Cue Name", 14, 60, settings.perf_next_name_size
        )
        self._spin_next_desc = self._make_spin_row(
            cl2, "Description", 10, 40, settings.perf_next_desc_size
        )
        self._spin_countdown = self._make_spin_row(
            cl2, "Countdown Timer", 16, 72, settings.perf_countdown_size
        )

        self._chk_countdown = QCheckBox("Show countdown timer")
        self._chk_countdown.setChecked(settings.countdown_enabled)
        cl2.addWidget(self._chk_countdown)

        lay.addWidget(card2)

        lay.addStretch()
        scroll.setWidget(content)

        page_lay = QVBoxLayout(page)
        page_lay.setContentsMargins(0, 0, 0, 0)
        page_lay.addWidget(scroll)

        self._refresh_preview()
        return page

    # ── Helpers ──────────────────────────────────────────────────

    def _make_spin_row(self, parent_layout: QVBoxLayout, label: str,
                       lo: int, hi: int, value: int) -> QSpinBox:
        row = QHBoxLayout()
        row.setSpacing(12)

        lbl = QLabel(label)
        lbl.setStyleSheet(f"color: {theme.TEXT_PRIMARY}; font-size: 12px;")
        lbl.setMinimumWidth(160)
        row.addWidget(lbl)

        spin = QSpinBox()
        spin.setRange(lo, hi)
        spin.setValue(value)
        spin.setSuffix(" pt")
        spin.setFixedWidth(90)
        spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        spin.valueChanged.connect(self._refresh_preview)
        row.addWidget(spin)

        # Size indicator bar
        bar_bg = QFrame()
        bar_bg.setFixedHeight(4)
        bar_bg.setStyleSheet(
            f"background: {theme.BG_INPUT}; border-radius: 2px;"
        )
        bar_bg.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        bar_fill = QFrame(bar_bg)
        bar_fill.setFixedHeight(4)
        bar_fill.setStyleSheet(
            f"background: {theme.SEMANTIC_INFO}; border-radius: 2px;"
        )
        spin._bar_bg = bar_bg
        spin._bar_fill = bar_fill
        spin._lo = lo
        spin._hi = hi
        self._update_bar(spin)
        spin.valueChanged.connect(lambda _v, s=spin: self._update_bar(s))
        row.addWidget(bar_bg, stretch=1)

        parent_layout.addLayout(row)
        return spin

    def _update_bar(self, spin: QSpinBox):
        lo = spin._lo
        hi = spin._hi
        frac = (spin.value() - lo) / max(hi - lo, 1)
        total_w = spin._bar_bg.width() or 200
        fill_w = max(4, int(frac * total_w))
        spin._bar_fill.setFixedWidth(fill_w)

    def _refresh_preview(self, _v=None):
        if not hasattr(self, '_font_preview'):
            return
        self._font_preview.update_sizes(
            cue_name=self._spin_cue_name.value(),
            cue_desc=self._spin_cue_desc.value(),
            op_size=self._spin_op_size.value(),
            op_name_size=self._spin_op_name_size.value(),
            next_name=self._spin_next_name.value(),
            next_desc=self._spin_next_desc.value(),
            countdown=self._spin_countdown.value(),
        )

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
            self._update_logo_preview(path)

    def _clear_logo(self):
        self._logo_path_lbl.setText("(none)")
        self._update_logo_preview("")

    def _update_logo_preview(self, path: str):
        if path and path != "(none)":
            pm = QPixmap(path)
            if not pm.isNull():
                self._logo_preview.setPixmap(
                    pm.scaledToHeight(56, Qt.TransformationMode.SmoothTransformation)
                )
                self._logo_preview.setStyleSheet(
                    f"background: {theme.BG_INPUT}; "
                    f"border: 1px solid {theme.BORDER_SUBTLE}; "
                    f"border-radius: {theme.RADIUS_SM}px;"
                )
                return
        self._logo_preview.clear()
        self._logo_preview.setText("No logo selected")
        self._logo_preview.setStyleSheet(
            f"background: {theme.BG_INPUT}; "
            f"color: {theme.TEXT_DIM}; font-size: 11px; "
            f"border: 1px dashed {theme.BORDER}; "
            f"border-radius: {theme.RADIUS_SM}px;"
        )

    def _toggle_password_visibility(self):
        self._pw_visible = not self._pw_visible
        self._remote_password.setEchoMode(
            QLineEdit.EchoMode.Normal if self._pw_visible
            else QLineEdit.EchoMode.Password
        )
        self._update_eye_icon()

    def _update_eye_icon(self):
        # Use a simple text toggle since we don't have an eye icon in the set
        self._btn_eye.setText("◉" if self._pw_visible else "○")
        self._btn_eye.setStyleSheet(
            _ghost_icon_btn_qss() +
            f"QPushButton {{ font-size: 16px; color: "
            f"{theme.SEMANTIC_INFO if self._pw_visible else theme.TEXT_DIM}; }}"
        )

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
