"""
Generate a transparent-background version of the Ø mark — used as the
default `assets/logo_src.png` that feeds into both the app icon and the
in-app Studio Logo slot. Run once; no need to ship this script in the
built app.

Matches the geometry used by assets/build_icon.py so the mark alignment
stays consistent across the synthesised icon and any PNG exports.
"""
from __future__ import annotations

import math
import os

from PIL import Image, ImageDraw

# Geometry mirrors build_icon.py's draw_master() — just on a transparent
# canvas instead of a dark rounded square.
BASE       = 1024
LOGO_COLOR = (255, 74, 30, 255)
RING_OUTER_RATIO = 0.78
STROKE_RATIO     = 0.115
SLASH_OVERHANG   = 0.055


def draw_logo(size: int = BASE) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))

    # Ring
    ring = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    rd = ImageDraw.Draw(ring)
    outer = size * RING_OUTER_RATIO
    stroke = size * STROKE_RATIO
    cx = cy = size / 2
    r_out = outer / 2
    r_in = r_out - stroke
    rd.ellipse((cx - r_out, cy - r_out, cx + r_out, cy + r_out), fill=LOGO_COLOR)
    rd.ellipse((cx - r_in, cy - r_in, cx + r_in, cy + r_in), fill=(0, 0, 0, 0))
    img.alpha_composite(ring)

    # Slash
    slash = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    sd = ImageDraw.Draw(slash)
    angle = math.radians(45)
    overhang = size * SLASH_OVERHANG
    half_len = r_out + overhang
    dx = math.cos(angle) * half_len
    dy = math.sin(angle) * half_len
    p1 = (cx - dx, cy + dy)
    p2 = (cx + dx, cy - dy)
    sd.line([p1, p2], fill=LOGO_COLOR, width=int(stroke), joint="curve")
    end_r = stroke / 2
    for (x, y) in (p1, p2):
        sd.ellipse((x - end_r, y - end_r, x + end_r, y + end_r), fill=LOGO_COLOR)
    img.alpha_composite(slash)

    return img


if __name__ == "__main__":
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo_src.png")
    draw_logo(BASE).save(out, format="PNG")
    print(f"Wrote {out} ({os.path.getsize(out):,} bytes)")
