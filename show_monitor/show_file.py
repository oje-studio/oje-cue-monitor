"""
.ojeshow2 file format — JSON document containing scenes and settings.

Intentionally distinct extension from the classic CUE MONITOR .ojeshow so
that opening one in the wrong app fails cleanly instead of silently
producing bad data.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict
from typing import Optional

from . import FILE_VERSION
from .scene_model import Scene, SceneCue, Show, ShowSettings, TIME_SOURCES, TIME_SOURCE_WORLD


def save_show(show: Show, path: str) -> None:
    data = {
        "app": "oje-show-monitor",
        "version": FILE_VERSION,
        "settings": asdict(show.settings),
        "scenes": [
            {
                "id": sc.id,
                "name": sc.name,
                "start_time": sc.start_time,
                "time_source": sc.time_source,
                "cues": [
                    {
                        "id": c.id,
                        "offset": c.offset,
                        "name": c.name,
                        "description": c.description,
                        "color": c.color,
                        "operator_comments": dict(c.operator_comments),
                    }
                    for c in sc.cues
                ],
            }
            for sc in show.scenes
        ],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_show(path: str) -> Show:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    app = data.get("app")
    if app and app != "oje-show-monitor":
        raise ValueError(f"Not a SHOW MONITOR file (app={app!r})")

    s = data.get("settings", {})
    settings = ShowSettings(
        operator_names=list(s.get("operator_names", ["Operator 1"])),
        audio_device_name=str(s.get("audio_device_name", "")),
        audio_channel=int(s.get("audio_channel", 0)),
        drift_warning_seconds=float(s.get("drift_warning_seconds", 5.0)),
        perf_clock_size=int(s.get("perf_clock_size", 96)),
        perf_clock_color=str(s.get("perf_clock_color", "#ffffff")),
        perf_cue_name_size=int(s.get("perf_cue_name_size", 56)),
        perf_cue_desc_size=int(s.get("perf_cue_desc_size", 26)),
        perf_operator_size=int(s.get("perf_operator_size", 20)),
        perf_operator_name_size=int(s.get("perf_operator_name_size", 12)),
        perf_next_name_size=int(s.get("perf_next_name_size", 30)),
        perf_next_desc_size=int(s.get("perf_next_desc_size", 16)),
        logo_path=str(s.get("logo_path", "")),
    )

    scenes = []
    for sd in data.get("scenes", []):
        cues = []
        for cd in sd.get("cues", []):
            cues.append(SceneCue(
                offset=float(cd.get("offset", 0.0)),
                name=str(cd.get("name", "")),
                description=str(cd.get("description", "")),
                color=str(cd.get("color", "")),
                operator_comments=dict(cd.get("operator_comments", {})),
                id=str(cd.get("id") or SceneCue().id),
            ))
        src = str(sd.get("time_source", TIME_SOURCE_WORLD))
        if src not in TIME_SOURCES:
            src = TIME_SOURCE_WORLD
        scenes.append(Scene(
            name=str(sd.get("name", "")),
            start_time=str(sd.get("start_time", "00:00:00")),
            time_source=src,
            cues=cues,
            id=str(sd.get("id") or Scene().id),
        ))

    return Show(settings=settings, scenes=scenes)
