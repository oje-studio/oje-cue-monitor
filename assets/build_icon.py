"""
Icon generator for ØJE CUE MONITOR.

Produces:
  assets/icon_1024.png   — source master (flat, for review)
  assets/icon.ico        — Windows multi-size (16/32/48/64/128/256)
  assets/icon.icns       — macOS multi-size  (16/32/128/256/512/1024)

Run from the project root:
    python3 assets/build_icon.py
"""
from __future__ import annotations

import math
import os
import struct
import sys
from io import BytesIO

from PIL import Image, ImageDraw, ImageFilter

# ── Design constants ─────────────────────────────────────────────────────────
BASE         = 1024
BG_COLOR     = (28, 28, 28, 255)     # matches DARK_BG in main_window.py
LOGO_COLOR   = (255, 74, 30, 255)    # ØJE red
CORNER_RADIUS_RATIO = 0.22            # macOS squircle-ish
RING_OUTER_RATIO    = 0.78            # outer diameter as fraction of canvas
STROKE_RATIO        = 0.115           # ring + slash stroke thickness
SLASH_OVERHANG      = 0.055           # how far the slash extends beyond the ring

OUT_DIR = os.path.dirname(os.path.abspath(__file__))


def draw_master(size: int = BASE) -> Image.Image:
    """Render the flat icon at the given size."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))

    # Rounded-square dark background
    bg = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    bd = ImageDraw.Draw(bg)
    radius = int(size * CORNER_RADIUS_RATIO)
    bd.rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=BG_COLOR)
    img.alpha_composite(bg)

    # Ring (O)
    ring = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    rd = ImageDraw.Draw(ring)
    outer = size * RING_OUTER_RATIO
    stroke = size * STROKE_RATIO
    cx = cy = size / 2
    r_out = outer / 2
    r_in = r_out - stroke
    # Outer disc
    rd.ellipse(
        (cx - r_out, cy - r_out, cx + r_out, cy + r_out),
        fill=LOGO_COLOR,
    )
    # Inner punch
    rd.ellipse(
        (cx - r_in, cy - r_in, cx + r_in, cy + r_in),
        fill=(0, 0, 0, 0),
    )
    img.alpha_composite(ring)

    # Slash — diagonal from lower-left to upper-right with overhang
    slash = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    sd = ImageDraw.Draw(slash)
    angle = math.radians(45)
    overhang = size * SLASH_OVERHANG
    half_len = r_out + overhang
    dx = math.cos(angle) * half_len
    dy = math.sin(angle) * half_len
    # Slash endpoints: bottom-left → top-right
    p1 = (cx - dx, cy + dy)
    p2 = (cx + dx, cy - dy)
    sd.line([p1, p2], fill=LOGO_COLOR, width=int(stroke), joint="curve")
    # Round the ends so they match the ring's visual weight
    end_r = stroke / 2
    for (x, y) in (p1, p2):
        sd.ellipse((x - end_r, y - end_r, x + end_r, y + end_r), fill=LOGO_COLOR)
    img.alpha_composite(slash)

    return img


def save_ico(master: Image.Image, path: str) -> None:
    """Windows .ico — bundle the standard range of sizes into one file."""
    sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
    # Feed Pillow a 256x256 master and let it emit all requested sizes.
    src = master.resize((256, 256), Image.LANCZOS)
    src.save(path, format="ICO", sizes=sizes)


# ── ICNS writer (minimal, stdlib-only) ───────────────────────────────────────
#
# The .icns format is a simple container: 8-byte header ('icns' + total size),
# followed by a sequence of chunks { 4-byte type, 4-byte size (incl. header),
# payload }. We embed PNG chunks directly (Apple accepts PNG payloads for
# modern type codes).
#
# Type codes used here (all PNG-compatible):
#   ic04 =   16x16    ic07 =  128x128     ic09 =  512x512
#   ic05 =   32x32    ic13 =  256x256     ic10 = 1024x1024 (aka "ic10" 2x of 512)
#   ic11 =   16x16@2x (32)   ic12 =  32x32@2x (64)
#   ic14 = 512x512@2x (1024)
#
# We'll emit the common retina-safe set.

ICNS_ENTRIES = [
    ("ic04",   16),
    ("ic05",   32),
    ("ic07",  128),
    ("ic13",  256),
    ("ic09",  512),
    ("ic10", 1024),
]


def save_icns(master: Image.Image, path: str) -> None:
    chunks = []
    for code, px in ICNS_ENTRIES:
        im = master.resize((px, px), Image.LANCZOS)
        buf = BytesIO()
        im.save(buf, format="PNG")
        data = buf.getvalue()
        chunks.append((code, data))

    body = b""
    for code, data in chunks:
        body += code.encode("ascii")
        body += struct.pack(">I", 8 + len(data))
        body += data

    total_size = 8 + len(body)
    with open(path, "wb") as f:
        f.write(b"icns")
        f.write(struct.pack(">I", total_size))
        f.write(body)


def compose_from_source(src_path: str, size: int = BASE) -> Image.Image:
    """Composite a user-provided logo PNG onto the dark rounded background."""
    logo = Image.open(src_path).convert("RGBA")
    # Trim to content bbox so padding is consistent
    bbox = logo.getbbox()
    if bbox:
        logo = logo.crop(bbox)
    # Scale so the longer side is ~72% of the canvas
    target = int(size * 0.72)
    scale = target / max(logo.size)
    new_size = (int(logo.size[0] * scale), int(logo.size[1] * scale))
    logo = logo.resize(new_size, Image.LANCZOS)

    # Dark rounded background
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    bd = ImageDraw.Draw(img)
    radius = int(size * CORNER_RADIUS_RATIO)
    bd.rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=BG_COLOR)

    # Centered paste
    ox = (size - logo.size[0]) // 2
    oy = (size - logo.size[1]) // 2
    img.alpha_composite(logo, dest=(ox, oy))
    return img


def main() -> None:
    src = os.path.join(OUT_DIR, "logo_src.png")
    if os.path.exists(src):
        print(f"Using source PNG: {src}")
        master = compose_from_source(src, BASE)
    else:
        print("No logo_src.png — synthesizing icon from primitives.")
        master = draw_master(BASE)

    master.save(os.path.join(OUT_DIR, "icon_1024.png"), format="PNG")
    save_ico(master, os.path.join(OUT_DIR, "icon.ico"))
    save_icns(master, os.path.join(OUT_DIR, "icon.icns"))

    print("Generated:")
    for name in ("icon_1024.png", "icon.ico", "icon.icns"):
        p = os.path.join(OUT_DIR, name)
        print(f"  {p}  ({os.path.getsize(p):,} bytes)")


if __name__ == "__main__":
    main()
