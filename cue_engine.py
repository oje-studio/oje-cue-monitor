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

    # Seconds after a cue's TC during which we still show it as "current"
    # when there is no following cue in the list. With a successor cue
    # present, "current" naturally hands off to it; without one, this
    # caps how long the last fired cue keeps the screen.
    _LAST_CUE_HOLD_SECONDS = 30

    def get_current_cue(self, tc_frames: int) -> Optional[Cue]:
        """
        Non-linear cue triggering — cues are matched purely by timecode,
        not by list order. The "current" cue is the one whose timecode is
        most recently passed (largest frames value <= tc_frames). When two
        cues share the same timecode, the later one in list order wins
        (matches the duplicate-TC warning shown in the editor).

        Edge case: if the playhead has run past every cue's timecode and
        there's no next cue queued in list order, we still hold the last
        fired cue on screen for _LAST_CUE_HOLD_SECONDS so the operator
        can confirm it landed. After that the engine reports None and
        the UI shows "No cue at this timecode" — useful for shows where
        LTC keeps running long after the last cue fires.
        """
        self._prev_frames = tc_frames
        best_idx = -1
        best_frames = -1
        for i, cue in enumerate(self.cues):
            if cue.is_divider or not cue.has_timecode:
                continue
            if cue.frames <= tc_frames and cue.frames >= best_frames:
                best_idx = i
                best_frames = cue.frames
        self._active_index = best_idx
        if not (0 <= best_idx < len(self.cues)):
            return None

        # Hold-then-release: only enforce the timeout when there's no
        # next cue in list order. With a queued next cue the show's
        # running normally and the current should persist.
        if self._has_next_cue_after(best_idx):
            return self.cues[best_idx]
        elapsed_frames = tc_frames - best_frames
        hold_frames = self._LAST_CUE_HOLD_SECONDS * (self.fps or 25.0)
        if elapsed_frames > hold_frames:
            return None
        return self.cues[best_idx]

    def _has_next_cue_after(self, index: int) -> bool:
        for j in range(index + 1, len(self.cues)):
            c = self.cues[j]
            if not c.is_divider and c.has_timecode:
                return True
        return False

    def get_next_cue(self, tc_frames: int) -> Optional[Cue]:
        """
        Next cue in *list order* — i.e. the show's running order, which is
        what the operator actually maintains. Random access by timecode is
        only for resolving the *current* cue; once that's pinned down,
        "next" walks the list from there.

        Why list order, not time order:
        if cues are 04:00 (row 1), then 03:00 (row 17, last), the operator
        considers 03:00 the end of the show. After it plays, "next" should
        be empty — not 04:00 again from the top.
        """
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
        remaining_frames = nxt.frames - tc_frames
        if remaining_frames < 0:
            return None
        return remaining_frames / self.fps
