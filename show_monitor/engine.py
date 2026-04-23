"""
Scene runner.

Given a wall-clock time (seconds since local midnight) and a Show,
resolves the current scene, current cue within it, the next cue, and
the countdown to that next cue.

Scenes without a valid start_time are ignored. Cues are assumed to fire
at (scene.start_seconds + cue.offset). The "current cue" is the most
recent cue whose fire time is <= now; the "next cue" is the earliest
cue whose fire time is > now (may be in the next scene).

Scenes are resolved by their start_time, not by their order in the
`scenes` list — the user can keep the list in any order they want for
editing convenience.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from .scene_model import Scene, SceneCue, Show


@dataclass
class CueRef:
    """Location of a cue in the show (scene index + cue index + absolute fire time)."""
    scene_index: int
    cue_index: int
    fire_seconds: float     # absolute seconds-of-day

    def resolve(self, show: Show) -> Tuple[Scene, SceneCue]:
        sc = show.scenes[self.scene_index]
        return sc, sc.cues[self.cue_index]


@dataclass
class Playhead:
    """Snapshot of where the show is right now."""
    now_seconds: float
    current_scene_index: Optional[int]
    current_cue: Optional[CueRef]
    next_cue: Optional[CueRef]

    def countdown(self) -> Optional[float]:
        if self.next_cue is None:
            return None
        return max(0.0, self.next_cue.fire_seconds - self.now_seconds)


def _all_cue_refs(show: Show) -> List[CueRef]:
    """All cues across all scenes, sorted by absolute fire time."""
    refs: List[CueRef] = []
    for si, sc in enumerate(show.scenes):
        start = sc.start_seconds()
        if start is None:
            continue
        for ci, cue in enumerate(sc.cues):
            refs.append(CueRef(
                scene_index=si,
                cue_index=ci,
                fire_seconds=start + float(cue.offset),
            ))
    refs.sort(key=lambda r: r.fire_seconds)
    return refs


def _active_scene_index(show: Show, now: float) -> Optional[int]:
    """Index of the latest scene whose start_time <= now."""
    best: Optional[Tuple[float, int]] = None
    for i, sc in enumerate(show.scenes):
        start = sc.start_seconds()
        if start is None or start > now:
            continue
        if best is None or start > best[0]:
            best = (start, i)
    return best[1] if best else None


def resolve(show: Show, now_seconds: float) -> Playhead:
    refs = _all_cue_refs(show)
    current: Optional[CueRef] = None
    nxt: Optional[CueRef] = None
    for r in refs:
        if r.fire_seconds <= now_seconds:
            current = r
        else:
            nxt = r
            break
    return Playhead(
        now_seconds=now_seconds,
        current_scene_index=_active_scene_index(show, now_seconds),
        current_cue=current,
        next_cue=nxt,
    )
