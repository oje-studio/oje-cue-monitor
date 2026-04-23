"""
Scene-based data model.

A Show contains ordered Scenes. Each Scene has a start wall-clock time
(HH:MM:SS) and a list of SceneCues. SceneCue offsets are measured from
the start of the scene (offset=0 == scene start), so scenes are
portable — changing a scene's start time just shifts all its cues.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from uuid import uuid4


# Time source for a scene — determines which clock drives cue firing.
# Currently the engine only resolves `world_clock` (real wall clock);
# `ltc` and `manual` are stored but will gain runtime support in later
# commits. They're defined here so the data model is forward-compatible
# and the UI can expose the choice today.
TIME_SOURCE_WORLD = "world_clock"
TIME_SOURCE_LTC   = "ltc"
TIME_SOURCE_MANUAL = "manual"

TIME_SOURCES = (TIME_SOURCE_WORLD, TIME_SOURCE_LTC, TIME_SOURCE_MANUAL)

TIME_SOURCE_LABELS = {
    TIME_SOURCE_WORLD:  "World Clock",
    TIME_SOURCE_LTC:    "LTC",
    TIME_SOURCE_MANUAL: "Manual",
}


@dataclass
class SceneCue:
    offset: float = 0.0          # seconds from scene start
    name: str = ""
    description: str = ""
    color: str = ""
    operator_comments: Dict[str, str] = field(default_factory=dict)
    id: str = field(default_factory=lambda: uuid4().hex[:12])


@dataclass
class Scene:
    name: str = ""
    start_time: str = "00:00:00"  # HH:MM:SS wall-clock time
    time_source: str = TIME_SOURCE_WORLD
    cues: List[SceneCue] = field(default_factory=list)
    id: str = field(default_factory=lambda: uuid4().hex[:12])

    def start_seconds(self) -> Optional[int]:
        try:
            h, m, s = self.start_time.split(":")
            return int(h) * 3600 + int(m) * 60 + int(s)
        except (ValueError, AttributeError):
            return None


@dataclass
class ShowSettings:
    operator_names: List[str] = field(default_factory=lambda: ["Operator 1"])

    # LTC input — show-wide, not per-scene. Empty device name means "off".
    audio_device_name: str = ""
    audio_channel: int = 0

    # Drift threshold (seconds) for local clock vs NTP — warning above this.
    drift_warning_seconds: float = 5.0

    # Performance-screen clock appearance
    perf_clock_size: int = 96
    perf_clock_color: str = "#ffffff"
    perf_cue_name_size: int = 56
    perf_cue_desc_size: int = 26
    perf_operator_size: int = 20
    perf_operator_name_size: int = 12
    perf_next_name_size: int = 30
    perf_next_desc_size: int = 16

    # Logo
    logo_path: str = ""


@dataclass
class Show:
    settings: ShowSettings = field(default_factory=ShowSettings)
    scenes: List[Scene] = field(default_factory=list)


# ── offset helpers ────────────────────────────────────────────────────────────

def format_offset(seconds: float) -> str:
    """Human-readable HH:MM:SS.ff form of a scene-relative offset."""
    total = max(0.0, float(seconds))
    h = int(total // 3600)
    m = int((total % 3600) // 60)
    s = total - h * 3600 - m * 60
    return f"{h:02d}:{m:02d}:{s:05.2f}"


def parse_offset(text: str) -> Optional[float]:
    """
    Accepts HH:MM:SS.ff / MM:SS.ff / SS.ff / plain seconds.
    Returns None on parse failure.
    """
    if text is None:
        return None
    t = str(text).strip()
    if not t:
        return None
    try:
        if ":" not in t:
            return float(t)
        parts = t.split(":")
        parts = [float(p) if p else 0.0 for p in parts]
        if len(parts) == 2:
            m, s = parts
            return m * 60 + s
        if len(parts) == 3:
            h, m, s = parts
            return h * 3600 + m * 60 + s
    except ValueError:
        return None
    return None
