"""
Scene runner.

Each scene declares a `time_source` (world_clock, ltc, manual). At tick
time the UI builds a TimeContext holding the current value of every
source (seconds-of-day, or None if unavailable — e.g. LTC with no
signal). `resolve()` routes each scene to its declared source, skips
scenes whose source has no current value, and picks the most-recently
started active scene as the playhead.

Within that scene the current cue is the last one whose fire time
(scene.start + cue.offset) has passed; the next cue is the earliest one
that hasn't. "Next" is scoped to the same scene — chasing cues across
scenes on different time sources doesn't yield a meaningful countdown
(two clocks, two time axes), so we don't.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .scene_model import (
    Scene, SceneCue, Show, TIME_SOURCE_LTC, TIME_SOURCE_MANUAL, TIME_SOURCE_WORLD,
)


@dataclass
class TimeContext:
    """
    Snapshot of every time source at a single tick.
    A source set to None is treated as unavailable.
    """
    world: Optional[float] = None   # seconds of day (wall clock)
    ltc: Optional[float] = None     # seconds of day (LTC TC)
    manual: Optional[float] = None  # seconds since manual play start

    def for_source(self, src: str) -> Optional[float]:
        if src == TIME_SOURCE_WORLD:
            return self.world
        if src == TIME_SOURCE_LTC:
            return self.ltc
        if src == TIME_SOURCE_MANUAL:
            return self.manual
        return None


@dataclass
class CueRef:
    scene_index: int
    cue_index: int
    fire_seconds: float   # absolute seconds in the scene's source time

    def resolve(self, show: Show) -> Tuple[Scene, SceneCue]:
        sc = show.scenes[self.scene_index]
        return sc, sc.cues[self.cue_index]


@dataclass
class Playhead:
    ctx: TimeContext
    current_scene_index: Optional[int] = None
    current_cue: Optional[CueRef] = None
    next_cue: Optional[CueRef] = None
    # Time value used for the countdown (in the current scene's source).
    _current_source_time: Optional[float] = None

    def countdown(self) -> Optional[float]:
        if self.next_cue is None or self._current_source_time is None:
            return None
        return max(0.0, self.next_cue.fire_seconds - self._current_source_time)


def resolve(show: Show, ctx: TimeContext) -> Playhead:
    """
    Route each scene to its own time source, pick the most-recently
    started scene as the playhead, then resolve current/next inside it.
    """
    # Among scenes whose source time is available and whose start has passed,
    # pick the one that started most recently (smallest elapsed). When the
    # user sets Scene B to start at 19:05, they expect it to take over from
    # Scene A at 19:05 — not "whichever has been running longest".
    best_scene_idx: Optional[int] = None
    best_elapsed: Optional[float] = None
    best_source_time: Optional[float] = None

    for i, sc in enumerate(show.scenes):
        src_time = ctx.for_source(sc.time_source)
        if src_time is None:
            continue
        sc_start = sc.start_seconds()
        if sc_start is None or sc_start > src_time:
            continue
        elapsed = src_time - sc_start
        if best_elapsed is None or elapsed < best_elapsed:
            best_elapsed = elapsed
            best_scene_idx = i
            best_source_time = src_time

    playhead = Playhead(ctx=ctx)
    if best_scene_idx is None:
        return playhead
    playhead.current_scene_index = best_scene_idx
    playhead._current_source_time = best_source_time

    sc = show.scenes[best_scene_idx]
    sc_start = sc.start_seconds() or 0
    cur_ref: Optional[CueRef] = None
    nxt_ref: Optional[CueRef] = None
    # Cues in declared order; fire time = start + offset
    ordered = sorted(enumerate(sc.cues), key=lambda t: float(t[1].offset))
    for cue_idx, cue in ordered:
        fire = sc_start + float(cue.offset)
        if fire <= best_source_time:
            cur_ref = CueRef(best_scene_idx, cue_idx, fire)
        else:
            nxt_ref = CueRef(best_scene_idx, cue_idx, fire)
            break

    playhead.current_cue = cur_ref
    playhead.next_cue = nxt_ref
    return playhead
