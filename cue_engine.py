from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from typing import List, Optional, Dict

from show_file import ShowCue


@dataclass
class Cue:
    index: int
    timecode: str           # "HH:MM:SS:FF" or "" for dividers
    name: str
    description: str
    color: str
    frames: int             # absolute frame count at engine fps (-1 for dividers)
    group: str = ""
    operator_comments: Dict[str, str] = dc_field(default_factory=dict)
    is_divider: bool = False

    @property
    def has_timecode(self) -> bool:
        return self.timecode.strip() != "" and self.frames >= 0


class CueParseError(Exception):
    def __init__(self, message: str, row: int = 0):
        super().__init__(message)
        self.row = row


class CueEngine:
    def __init__(self, fps: float = 25.0):
        self.fps = fps
        self.cues: List[Cue] = []
        self._active_index: int = -1
        self._prev_frames: int = -1

    # ── timecode math ─────────────────────────────────────────────────────────

    def tc_to_frames(self, h: int, m: int, s: int, f: int, fps: float = None) -> int:
        fps = fps or self.fps
        return int((h * 3600 + m * 60 + s) * fps + f)

    def parse_timecode(self, tc_str: str, row: int = 0) -> tuple:
        parts = tc_str.strip().split(":")
        if len(parts) != 4:
            raise CueParseError(
                f"Invalid timecode '{tc_str}' — expected HH:MM:SS:FF", row
            )
        try:
            return tuple(int(p) for p in parts)
        except ValueError:
            raise CueParseError(f"Non-numeric timecode '{tc_str}'", row)

    def frames_to_tc_str(self, frames: int) -> str:
        fps = self.fps or 25.0
        total_s = int(frames / fps)
        f = int(frames % fps)
        h = total_s // 3600
        m = (total_s % 3600) // 60
        s = total_s % 60
        return f"{h:02d}:{m:02d}:{s:02d}:{f:02d}"

    # ── Load from ShowFile cues ───────────────────────────────────────────────

    def load_show_cues(self, show_cues: List[ShowCue]):
        cues: List[Cue] = []
        for i, sc in enumerate(show_cues):
            tc = sc.timecode.strip()
            is_divider = sc.is_divider or (tc == "")
            frames = -1
            if not is_divider and tc:
                try:
                    h, m, s, f = self.parse_timecode(tc)
                    frames = self.tc_to_frames(h, m, s, f)
                except CueParseError:
                    pass

            cues.append(Cue(
                index=i + 1,
                timecode=tc,
                name=sc.name,
                description=sc.description,
                color=sc.color,
                frames=frames,
                group=sc.group,
                operator_comments=dict(sc.operator_comments),
                is_divider=is_divider,
            ))

        for i, c in enumerate(cues):
            c.index = i + 1
        self.cues = cues
        self._active_index = -1
        self._prev_frames = -1

    def to_show_cues(self) -> List[ShowCue]:
        result = []
        for cue in self.cues:
            result.append(ShowCue(
                timecode=cue.timecode,
                name=cue.name,
                description=cue.description,
                color=cue.color,
                group=cue.group,
                operator_comments=dict(cue.operator_comments),
                is_divider=cue.is_divider,
            ))
        return result

    # ── mutations ─────────────────────────────────────────────────────────────

    def update_cue_field(self, index_0: int, field: str, value: str):
        if not (0 <= index_0 < len(self.cues)):
            return
        cue = self.cues[index_0]
        setattr(cue, field, value)
        if field == "timecode":
            tc_str = value.strip()
            if tc_str == "":
                cue.is_divider = True
                cue.frames = -1
            else:
                cue.is_divider = False
                try:
                    h, m, s, f = self.parse_timecode(value)
                    cue.frames = self.tc_to_frames(h, m, s, f)
                except CueParseError:
                    pass

    def update_operator_comment(self, index_0: int, op_name: str, comment: str):
        if not (0 <= index_0 < len(self.cues)):
            return
        cue = self.cues[index_0]
        if comment:
            cue.operator_comments[op_name] = comment
        else:
            cue.operator_comments.pop(op_name, None)

    def add_cue(self, after_index_0: int = -1, is_divider: bool = False) -> Cue:
        tc = "" if is_divider else "00:00:00:00"
        name = "— SECTION —" if is_divider else "New Cue"
        new = Cue(0, tc, name, "", "", -1 if is_divider else 0,
                  is_divider=is_divider)
        if after_index_0 < 0 or after_index_0 >= len(self.cues):
            self.cues.append(new)
        else:
            self.cues.insert(after_index_0 + 1, new)
        for i, c in enumerate(self.cues):
            c.index = i + 1
        return new

    def remove_cue(self, index_0: int):
        if 0 <= index_0 < len(self.cues):
            self.cues.pop(index_0)
            for i, c in enumerate(self.cues):
                c.index = i + 1

    def remove_cues(self, indices: List[int]):
        for i in sorted(indices, reverse=True):
            if 0 <= i < len(self.cues):
                self.cues.pop(i)
        for i, c in enumerate(self.cues):
            c.index = i + 1

    def move_cue(self, from_idx: int, to_idx: int):
        if (0 <= from_idx < len(self.cues)) and (0 <= to_idx < len(self.cues)):
            cue = self.cues.pop(from_idx)
            self.cues.insert(to_idx, cue)
            for i, c in enumerate(self.cues):
                c.index = i + 1

    def get_group_for_cue(self, cue: Cue) -> str:
        idx = self.cues.index(cue) if cue in self.cues else -1
        if cue.group:
            return cue.group
        for i in range(idx - 1, -1, -1):
            c = self.cues[i]
            if c.group:
                return c.group
            if c.is_divider:
                return c.name
        return ""

    def set_fps(self, fps: float):
        if fps == self.fps:
            return
        self.fps = fps
        for cue in self.cues:
            if cue.is_divider or not cue.timecode.strip():
                continue
            try:
                h, m, s, f = self.parse_timecode(cue.timecode)
                cue.frames = self.tc_to_frames(h, m, s, f)
            except CueParseError:
                pass

    def reset_active(self):
        self._active_index = -1
        self._prev_frames = -1

    # ── queries ───────────────────────────────────────────────────────────────

    def get_current_cue(self, tc_frames: int) -> Optional[Cue]:
        prev = self._prev_frames
        self._prev_frames = tc_frames
        if prev >= 0 and tc_frames != prev:
            lo, hi = min(prev, tc_frames), max(prev, tc_frames)
            for i, cue in enumerate(self.cues):
                if cue.is_divider or not cue.has_timecode:
                    continue
                if i == self._active_index:
                    continue
                if lo <= cue.frames <= hi:
                    print(f"[CUE ENGINE] TRIGGER cue {i} '{cue.name}' "
                          f"cue_frames={cue.frames} range=[{lo},{hi}] "
                          f"active was={self._active_index}")
                    self._active_index = i
                    break
        if 0 <= self._active_index < len(self.cues):
            return self.cues[self._active_index]
        return None

    def get_next_cue(self, tc_frames: int) -> Optional[Cue]:
        start = self._active_index + 1 if self._active_index >= 0 else 0
        for i in range(start, len(self.cues)):
            cue = self.cues[i]
            if cue.is_divider or not cue.has_timecode:
                continue
            return cue
        return None

    def get_countdown(self, tc_frames: int) -> Optional[float]:
        nxt = self.get_next_cue(tc_frames)
        if nxt is None:
            return None
        return abs(nxt.frames - tc_frames) / self.fps
