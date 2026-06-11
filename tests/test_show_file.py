"""ShowFile (.ojeshow) round-trip + CSV import tests."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from show_file import ShowCue, ShowFile, ShowSettings


def test_save_load_round_trip(tmp_path):
    show = ShowFile(
        settings=ShowSettings(
            show_title="Round Trip",
            operator_names=["Light", "Audio"],
            operator_colors={"Light": "#85b7eb"},
            remote_password="secret",
            countdown_enabled=False,
        ),
        cues=[
            ShowCue(timecode="", name="ACT 1", is_divider=True),
            ShowCue(timecode="00:00:10:00", name="Opening", description="Blackout out",
                    color="#2EBD6B", group="Act 1",
                    operator_comments={"Light": "GO 1", "Audio": "Fade in"}),
        ],
    )
    p = tmp_path / "show.ojeshow"
    show.save(str(p))

    loaded = ShowFile.load(str(p))
    assert loaded.settings.show_title == "Round Trip"
    assert loaded.settings.operator_names == ["Light", "Audio"]
    assert loaded.settings.operator_colors == {"Light": "#85b7eb"}
    assert loaded.settings.countdown_enabled is False
    assert len(loaded.cues) == 2
    assert loaded.cues[0].is_divider is True
    assert loaded.cues[1].operator_comments == {"Light": "GO 1", "Audio": "Fade in"}
    assert loaded.file_path == str(p)


def test_load_defaults_for_missing_keys(tmp_path):
    # Older / hand-edited files may omit settings keys — load() must default.
    p = tmp_path / "minimal.ojeshow"
    p.write_text('{"version": 1, "cues": [{"timecode": "00:00:01:00", "name": "A"}]}',
                 encoding="utf-8")
    loaded = ShowFile.load(str(p))
    assert loaded.settings.operator_names == ["Operator 1"]
    assert loaded.settings.perf_cue_name_size == 56
    assert loaded.cues[0].name == "A"
    assert loaded.cues[0].is_divider is False


def test_save_requires_path():
    show = ShowFile()
    try:
        show.save()
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_csv_import_operator_syntax(tmp_path):
    csv_path = tmp_path / "cues.csv"
    csv_path.write_text(
        "timecode,name,description,color,group,operators\n"
        "00:00:05:00,Intro,House down,#fff,Act 1,Light: GO 1 | Audio: Track 1\n"
        ",ACT BREAK,,,,\n"
        "00:01:00:00,Verse,,,,Solo note\n",
        encoding="utf-8",
    )
    show = ShowFile.from_csv(str(csv_path))
    assert len(show.cues) == 3
    assert show.cues[0].operator_comments == {"Light": "GO 1", "Audio": "Track 1"}
    assert show.cues[1].is_divider is True
    # bare entry (no colon) lands on the default operator
    assert show.cues[2].operator_comments == {"Operator 1": "Solo note"}
    # operators collected into settings
    assert set(show.settings.operator_names) == {"Light", "Audio", "Operator 1"}


def test_example_show_loads():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    example = os.path.join(root, "example_show.ojeshow")
    if not os.path.exists(example):
        return  # fixture optional
    loaded = ShowFile.load(example)
    assert isinstance(loaded.cues, list) and loaded.cues
