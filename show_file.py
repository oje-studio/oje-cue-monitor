"""
Show file format (.ojeshow) — JSON-based.
Contains all settings + cue list in one file.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field as dc_field
from typing import List, Optional, Dict


@dataclass
class ShowSettings:
    # Show metadata
    show_title: str = ""

    # Audio
    audio_device_name: str = ""
    audio_channel: int = 0

    # Logo
    logo_path: str = ""

    # Operators (global list)
    operator_names: List[str] = dc_field(default_factory=lambda: ["Operator 1"])

    # Per-operator colour overrides ({name: "#rrggbb"}). Empty by
    # default — render call sites resolve unknown roles via
    # ui.theme.operator_color() (alias map + stable fallback cycle),
    # so older .ojeshow files keep rendering with sensible colours.
    operator_colors: Dict[str, str] = dc_field(default_factory=dict)

    # Web remote
    remote_password: str = ""

    # Performance mode fonts
    perf_cue_name_size: int = 56
    perf_cue_desc_size: int = 26
    perf_operator_size: int = 20
    perf_operator_name_size: int = 12
    perf_next_name_size: int = 30
    perf_next_desc_size: int = 16
    perf_countdown_size: int = 36

    # Countdown toggle
    countdown_enabled: bool = True


@dataclass
class ShowCue:
    timecode: str = ""
    name: str = ""
    description: str = ""
    color: str = ""
    group: str = ""
    operator_comments: Dict[str, str] = dc_field(default_factory=dict)
    is_divider: bool = False


@dataclass
class ShowFile:
    settings: ShowSettings = dc_field(default_factory=ShowSettings)
    cues: List[ShowCue] = dc_field(default_factory=list)
    file_path: str = ""

    def save(self, path: Optional[str] = None):
        path = path or self.file_path
        if not path:
            raise ValueError("No file path specified")
        data = {
            "version": 1,
            "settings": {
                "show_title": self.settings.show_title,
                "audio_device_name": self.settings.audio_device_name,
                "audio_channel": self.settings.audio_channel,
                "logo_path": self.settings.logo_path,
                "operator_names": self.settings.operator_names,
                "operator_colors": self.settings.operator_colors,
                "remote_password": self.settings.remote_password,
                "perf_cue_name_size": self.settings.perf_cue_name_size,
                "perf_cue_desc_size": self.settings.perf_cue_desc_size,
                "perf_operator_size": self.settings.perf_operator_size,
                "perf_operator_name_size": self.settings.perf_operator_name_size,
                "perf_next_name_size": self.settings.perf_next_name_size,
                "perf_next_desc_size": self.settings.perf_next_desc_size,
                "perf_countdown_size": self.settings.perf_countdown_size,
                "countdown_enabled": self.settings.countdown_enabled,
            },
            "cues": [
                {
                    "timecode": c.timecode,
                    "name": c.name,
                    "description": c.description,
                    "color": c.color,
                    "group": c.group,
                    "operator_comments": c.operator_comments,
                    "is_divider": c.is_divider,
                }
                for c in self.cues
            ],
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        self.file_path = path

    @classmethod
    def load(cls, path: str) -> "ShowFile":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        s = data.get("settings", {})
        settings = ShowSettings(
            show_title=s.get("show_title", ""),
            audio_device_name=s.get("audio_device_name", ""),
            audio_channel=s.get("audio_channel", 0),
            logo_path=s.get("logo_path", ""),
            operator_names=s.get("operator_names", ["Operator 1"]),
            operator_colors=dict(s.get("operator_colors", {})),
            remote_password=s.get("remote_password", ""),
            perf_cue_name_size=s.get("perf_cue_name_size", 56),
            perf_cue_desc_size=s.get("perf_cue_desc_size", 26),
            perf_operator_size=s.get("perf_operator_size", 20),
            perf_operator_name_size=s.get("perf_operator_name_size", 12),
            perf_next_name_size=s.get("perf_next_name_size", 30),
            perf_next_desc_size=s.get("perf_next_desc_size", 16),
            perf_countdown_size=s.get("perf_countdown_size", 36),
            countdown_enabled=s.get("countdown_enabled", True),
        )

        cues = []
        for cd in data.get("cues", []):
            cues.append(ShowCue(
                timecode=cd.get("timecode", ""),
                name=cd.get("name", ""),
                description=cd.get("description", ""),
                color=cd.get("color", ""),
                group=cd.get("group", ""),
                operator_comments=cd.get("operator_comments", {}),
                is_divider=cd.get("is_divider", False),
            ))

        show = cls(settings=settings, cues=cues, file_path=path)
        return show

    @classmethod
    def from_csv(cls, csv_path: str) -> "ShowFile":
        """Import from legacy CSV format."""
        import csv
        show = cls()
        with open(csv_path, newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            if not reader.fieldnames:
                return show

            # Collect operator names from data
            all_op_names = set()

            raw_cues = []
            for row in reader:
                tc = row.get("timecode", "").strip()
                ops_raw = row.get("operators", "").strip()
                op_comments: Dict[str, str] = {}
                if ops_raw:
                    for entry in ops_raw.split("|"):
                        entry = entry.strip()
                        if ":" in entry:
                            name, comment = entry.split(":", 1)
                            name = name.strip()
                            op_comments[name] = comment.strip()
                            all_op_names.add(name)
                        elif entry:
                            op_comments["Operator 1"] = entry
                            all_op_names.add("Operator 1")
                elif row.get("operator_note", "").strip():
                    op_comments["Operator 1"] = row["operator_note"].strip()
                    all_op_names.add("Operator 1")

                raw_cues.append(ShowCue(
                    timecode=tc,
                    name=row.get("name", "").strip(),
                    description=row.get("description", "").strip(),
                    color=row.get("color", "").strip(),
                    group=row.get("group", "").strip(),
                    operator_comments=op_comments,
                    is_divider=(tc == ""),
                ))

            show.cues = raw_cues
            if all_op_names:
                show.settings.operator_names = sorted(all_op_names)

        return show
