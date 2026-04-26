"""
Inline-SVG icon library for the cue monitor.

Each icon is a tiny SVG string with stroke="currentColor" so we can
recolour it on the fly via str.replace before handing it to Qt's SVG
renderer. Output is a QIcon you can drop into setIcon() on any
QPushButton / QAction.

Why inline strings instead of files in assets/:
  * Self-contained — no asset path bookkeeping in PyInstaller specs.
  * Trivially recolourable (button hover state, dark/light themes,
    record-red on START, etc.).
  * Tiny — the whole library is < 2 KB of source.

Drawing conventions: 24×24 viewBox, 2 px stroke, round caps/joins,
single-colour. Keep paths minimal — these read at 16-20 px button
sizes, no fine detail survives.
"""
from __future__ import annotations

from typing import Dict

from PyQt6.QtCore import QByteArray, QSize, Qt
from PyQt6.QtGui import QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer


# Each entry: viewBox 24×24, currentColor swappable.
_SVG: Dict[str, str] = {
    # ── Transport / monitor ──────────────────────────────────────────────
    "record": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
        '<circle cx="12" cy="12" r="6" fill="currentColor"/>'
        '</svg>'
    ),
    "stop": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
        '<rect x="7" y="7" width="10" height="10" rx="1" fill="currentColor"/>'
        '</svg>'
    ),
    "fullscreen": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="2" stroke-linecap="round" '
        'stroke-linejoin="round">'
        '<path d="M4 9V4h5"/><path d="M20 9V4h-5"/>'
        '<path d="M4 15v5h5"/><path d="M20 15v5h-5"/>'
        '</svg>'
    ),
    "remote": (
        # Wi-Fi-style three arcs + dot — reads as "broadcast / remote".
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="2" stroke-linecap="round">'
        '<path d="M3.5 10c5-5 12-5 17 0"/>'
        '<path d="M7 13.5c3-3 7-3 10 0"/>'
        '<path d="M10.5 17c1-1 2-1 3 0"/>'
        '<circle cx="12" cy="19.5" r="1" fill="currentColor" stroke="none"/>'
        '</svg>'
    ),

    # ── Edit toolbar ─────────────────────────────────────────────────────
    "edit": (
        # Pencil — diagonal body + a small chisel tip.
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="2" stroke-linecap="round" '
        'stroke-linejoin="round">'
        '<path d="M4 20h4L19 9l-4-4L4 16v4z"/>'
        '<path d="M14 6l4 4"/>'
        '</svg>'
    ),
    "check": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="2.4" stroke-linecap="round" '
        'stroke-linejoin="round">'
        '<polyline points="5,12 10,17 19,7"/>'
        '</svg>'
    ),
    "plus": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="2.2" stroke-linecap="round">'
        '<line x1="12" y1="5" x2="12" y2="19"/>'
        '<line x1="5" y1="12" x2="19" y2="12"/>'
        '</svg>'
    ),
    "section": (
        # Three horizontal lines, the middle one shorter — paragraph
        # marker that's clearly distinct from "+".
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="2" stroke-linecap="round">'
        '<line x1="4" y1="7" x2="20" y2="7"/>'
        '<line x1="4" y1="12" x2="14" y2="12"/>'
        '<line x1="4" y1="17" x2="20" y2="17"/>'
        '</svg>'
    ),
    "x": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="2.2" stroke-linecap="round">'
        '<line x1="6" y1="6" x2="18" y2="18"/>'
        '<line x1="18" y1="6" x2="6" y2="18"/>'
        '</svg>'
    ),
    "up": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="2.2" stroke-linecap="round" '
        'stroke-linejoin="round">'
        '<polyline points="6,15 12,9 18,15"/>'
        '</svg>'
    ),
    "down": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="2.2" stroke-linecap="round" '
        'stroke-linejoin="round">'
        '<polyline points="6,9 12,15 18,15"/>'  # placeholder — replaced below
        '</svg>'
    ),
    "clock": (
        # Circle face + hour/minute hands. Stays legible at 16-20 px.
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="2" stroke-linecap="round" '
        'stroke-linejoin="round">'
        '<circle cx="12" cy="12" r="9"/>'
        '<polyline points="12,7 12,12 16,14"/>'
        '</svg>'
    ),
}

# Fix the down arrow polyline (typo above keeps the file readable but the
# real shape needs the apex pointing down).
_SVG["down"] = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
    'stroke="currentColor" stroke-width="2.2" stroke-linecap="round" '
    'stroke-linejoin="round">'
    '<polyline points="6,9 12,15 18,9"/>'
    '</svg>'
)


def make_icon(name: str, color: str = "#dadada", size: int = 24) -> QIcon:
    """
    Render the named SVG into a QIcon at the given pixel size, recoloured
    to `color`. Returns an empty QIcon if the name isn't registered (so
    callers don't need to None-check).
    """
    svg = _SVG.get(name)
    if not svg:
        return QIcon()
    coloured = svg.replace("currentColor", color)
    renderer = QSvgRenderer(QByteArray(coloured.encode("utf-8")))
    # Render at 2× to look crisp on retina, then scale down — Qt picks
    # the high-res variant on HiDPI displays automatically.
    px = QPixmap(size * 2, size * 2)
    px.fill(Qt.GlobalColor.transparent)
    painter = QPainter(px)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter)
    painter.end()
    return QIcon(px)


def icon_size(px: int = 18) -> QSize:
    return QSize(px, px)
