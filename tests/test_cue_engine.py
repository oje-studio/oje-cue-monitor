"""CueEngine unit tests — pure logic, no Qt/audio imports.

Covers timecode math, duplicate detection, non-linear current-cue
resolution, list-order next-cue semantics, and fps changes. These are
the behaviours the operator relies on mid-show, so they gate the
binary build in CI.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cue_engine import Cue, CueEngine, CueParseError, find_duplicate_rows
from show_file import ShowCue, ShowFile


# ── helpers ────────────────────────────────────────────────────────────────

def engine_with(tcs, fps=25.0):
    """Build an engine whose cues have the given timecodes (in list order)."""
    eng = CueEngine(fps=fps)
    eng.load_show_cues([
        ShowCue(timecode=tc, name=f"Cue {i+1}", is_divider=(tc == ""))
        for i, tc in enumerate(tcs)
    ])
    return eng


# ── timecode math ──────────────────────────────────────────────────────────

def test_tc_to_frames_25fps():
    eng = CueEngine(fps=25.0)
    assert eng.tc_to_frames(0, 0, 0, 0) == 0
    assert eng.tc_to_frames(0, 0, 1, 0) == 25
    assert eng.tc_to_frames(1, 0, 0, 0) == 90000
    assert eng.tc_to_frames(1, 2, 3, 4) == (3600 + 120 + 3) * 25 + 4


def test_tc_to_frames_30fps():
    eng = CueEngine(fps=30.0)
    assert eng.tc_to_frames(0, 1, 0, 0) == 1800
    assert eng.tc_to_frames(23, 59, 59, 29) == (23 * 3600 + 59 * 60 + 59) * 30 + 29


def test_frames_round_trip():
    eng = CueEngine(fps=25.0)
    for h, m, s, f in [(0, 0, 0, 0), (0, 59, 59, 24), (1, 0, 0, 0), (23, 59, 59, 24)]:
        frames = eng.tc_to_frames(h, m, s, f)
        assert eng.frames_to_tc_str(frames) == f"{h:02d}:{m:02d}:{s:02d}:{f:02d}"


def test_parse_timecode_valid():
    eng = CueEngine()
    assert eng.parse_timecode("01:02:03:04") == (1, 2, 3, 4)
    assert eng.parse_timecode("  01:02:03:04  ") == (1, 2, 3, 4)


@pytest.mark.parametrize("bad", ["01:02:03", "1:2", "", "aa:bb:cc:dd", "01-02-03-04"])
def test_parse_timecode_invalid(bad):
    eng = CueEngine()
    with pytest.raises(CueParseError):
        eng.parse_timecode(bad)


# ── duplicate detection ────────────────────────────────────────────────────

def test_duplicates_flag_all_sharers():
    eng = engine_with(["00:00:10:00", "00:00:20:00", "00:00:10:00"])
    assert find_duplicate_rows(eng.cues) == {0, 2}


def test_duplicates_ignore_dividers_and_empty():
    cues = [
        Cue(1, "", "DIV", "", "", -1, is_divider=True),
        Cue(2, "", "DIV2", "", "", -1, is_divider=True),
        Cue(3, "00:00:05:00", "A", "", "", 125),
    ]
    assert find_duplicate_rows(cues) == set()


def test_duplicates_whitespace_insensitive():
    eng = engine_with(["00:00:10:00", " 00:00:10:00 "])
    assert find_duplicate_rows(eng.cues) == {0, 1}


# ── current cue: non-linear triggering ─────────────────────────────────────

def test_current_cue_none_before_first():
    eng = engine_with(["00:01:00:00"])
    assert eng.get_current_cue(0) is None


def test_current_cue_latest_passed_wins():
    eng = engine_with(["00:00:10:00", "00:01:00:00", "00:00:30:00"])
    # at 45s the most recently passed TC is 00:00:30 (row 3) even though
    # a later row (00:01:00) exists — non-linear, by timecode not order
    cur = eng.get_current_cue(45 * 25)
    assert cur is not None and cur.timecode == "00:00:30:00"


def test_current_cue_duplicate_tc_later_row_wins():
    eng = engine_with(["00:00:10:00", "00:00:10:00"])
    cur = eng.get_current_cue(11 * 25)
    assert cur is eng.cues[1]


def test_current_cue_skips_dividers():
    eng = engine_with(["", "00:00:10:00"])
    cur = eng.get_current_cue(11 * 25)
    assert cur is not None and cur.name == "Cue 2"


# ── next cue: list order, not time order ───────────────────────────────────

def test_next_cue_walks_list_order():
    # 04:00 first row, 03:00 last row — after 03:00 plays, the show is over:
    # "next" must be None, not 04:00 again (docstring contract).
    eng = engine_with(["00:04:00:00", "00:01:00:00", "00:03:00:00"])
    eng.get_current_cue(eng.tc_to_frames(0, 3, 0, 1))  # inside last cue
    assert eng.get_next_cue(eng.tc_to_frames(0, 3, 0, 1)) is None


def test_next_cue_before_show_is_first_row():
    eng = engine_with(["00:04:00:00", "00:01:00:00"])
    eng.reset_active()
    eng.get_current_cue(0)  # nothing passed yet
    nxt = eng.get_next_cue(0)
    assert nxt is not None and nxt.timecode == "00:04:00:00"


def test_countdown_positive_and_none():
    eng = engine_with(["00:00:10:00", "00:00:20:00"])
    eng.get_current_cue(12 * 25)            # current = cue 1
    cd = eng.get_countdown(12 * 25)         # next = cue 2 at 20s
    assert cd == pytest.approx(8.0)
    # next cue earlier than now (list order) → negative remaining → None
    eng2 = engine_with(["00:00:30:00", "00:00:10:00"])
    eng2.get_current_cue(35 * 25)           # current = row 1 (30s)
    assert eng2.get_countdown(35 * 25) is None


# ── hour boundary fixture ──────────────────────────────────────────────────

FIXTURE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "hour_boundary_test.ojeshow")


def test_hour_boundary_fixture_crossing():
    show = ShowFile.load(FIXTURE)
    eng = CueEngine(fps=25.0)
    eng.load_show_cues(show.cues)
    # just before hour 1: current is the last hour-0 cue
    before = eng.get_current_cue(eng.tc_to_frames(0, 59, 59, 24))
    assert before is not None and before.timecode.startswith("00:")
    # exactly at hour 1: the 01:00:00:00 cue triggers
    at = eng.get_current_cue(eng.tc_to_frames(1, 0, 0, 0))
    assert at is not None and at.timecode == "01:00:00:00"


# ── mutations & fps ────────────────────────────────────────────────────────

def test_update_timecode_toggles_divider():
    eng = engine_with(["00:00:10:00"])
    eng.update_cue_field(0, "timecode", "")
    assert eng.cues[0].is_divider and eng.cues[0].frames == -1
    eng.update_cue_field(0, "timecode", "00:00:20:00")
    assert not eng.cues[0].is_divider and eng.cues[0].frames == 20 * 25


def test_set_fps_recomputes_frames():
    eng = engine_with(["00:01:00:00"], fps=25.0)
    assert eng.cues[0].frames == 1500
    eng.set_fps(30.0)
    assert eng.cues[0].frames == 1800


def test_add_remove_reindex():
    eng = engine_with(["00:00:01:00", "00:00:02:00"])
    eng.add_cue(0)
    assert [c.index for c in eng.cues] == [1, 2, 3]
    eng.remove_cue(1)
    assert [c.index for c in eng.cues] == [1, 2]
