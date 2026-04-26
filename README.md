# ØJE CUE MONITOR

Live show operator tool — LTC/SMPTE timecode reader + cue list manager with performance mode.

[oje.studio](https://oje.studio) · [hello@oje.studio](mailto:hello@oje.studio)

## Download

Pre-built binaries for macOS and Windows: **[GitHub Releases](https://github.com/oje-studio/oje-cue-monitor/releases)**.
No Python install required — just download, unzip (macOS) or run (Windows).

![Version](https://img.shields.io/badge/version-1.0beta-blue)
![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Windows-lightgrey)
![Python](https://img.shields.io/badge/python-3.9+-green)

## Features

- **LTC Timecode Decoding** — reads SMPTE/LTC timecode from any audio input via libltc
- **Non-Linear Cue Triggering** — cues trigger by timecode hit in user-defined order, not sorted
- **Cue List** — timed cues with names, descriptions, colours, section dividers with cue counts
- **Per-Operator Comments** — configurable operator list with role-semantic colours (Lighting blue, Audio amber, Stage Manager purple, customisable per role) so each operator picks out their column at a glance
- **Performance Mode** — full-screen operator view with large fonts, countdown timer, role-coloured operator columns, and a one-tap full-cue-list overlay
- **Web Remote** — serve Performance View to any device on the local network via WebSocket; password-protected access; operator-specific filtering so each phone shows only the cues its operator owns
- **Duplicate Timecode Detection** — amber row tint, left stripe, and "DUP" pill in the cue list; identical detection in the cue table and any future cue-list export
- **Signal Monitoring** — five-bar VU meter, semantic LIVE / WEAK / CLIPPING / NO SIGNAL states, signal-loss blink
- **Show File Format (.ojeshow)** — single JSON file with all settings + cue list, autosave on dirty, crash-recovery prompt on next launch
- **Unified Dark Design System** — single token vocabulary across the desktop UI, the cue table, Performance Mode, and the web remote so colours mean the same thing everywhere they appear (green = active / locked, amber = warning / duplicate, red = stop / no signal)

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Cmd+N` / `Ctrl+N` | New show |
| `Cmd+O` / `Ctrl+O` | Open show file / import CSV |
| `Cmd+S` / `Ctrl+S` | Save show |
| `P` | Toggle Performance Mode |
| `Escape` | Exit Performance Mode |
| `Space` | Manual cue mark |
| `F1` | Help |

## macOS

### Install & Run

```bash
git clone https://github.com/oje-studio/oje-cue-monitor.git
cd oje-cue-monitor
bash setup.sh
python3 main.py
```

### Build .app

```bash
bash build.sh
```

Produces `dist/ØJE CUE MONITOR.app` — drag to Applications.

## Windows

### Install & Run

```
git clone https://github.com/oje-studio/oje-cue-monitor.git
cd oje-cue-monitor
setup_win.bat
python main.py
```

### Build .exe

```
build_win.bat
```

Produces `dist/OJE CUE MONITOR.exe` — single file, no install needed. `libltc.dll` is bundled inside.

## Show File Format

`.ojeshow` — JSON containing settings (audio device, operators, font sizes, logo) and the complete cue list.

```json
{
  "version": 1,
  "settings": { "operator_names": ["Lighting", "Audio", "SM"], ... },
  "cues": [
    { "timecode": "00:01:00:00", "name": "Intro", "operator_comments": {"Lighting": "Go"} }
  ]
}
```

An example show file is included: `example_show.ojeshow`

## Requirements

### macOS
- macOS (Apple Silicon or Intel)
- Python 3.9+
- libltc (`brew install libltc`)
- portaudio (`brew install portaudio`)

### Windows
- Windows 10/11 x64
- Python 3.9+
- libltc.dll (included in `libs/win64/`)

## License

© 2026 ØJE Studio. All rights reserved.

---

## About ØJE Studio

ØJE is an independent multimedia studio based in Vienna, operating internationally.

We are structured as a cultural-tech practice uniting artistic authorship, technical leadership and production accountability within a single studio. Our team combines expertise in scenographic thinking, real-time systems and spatial media with the technical depth to realise projects end-to-end — from strategic concept development and documentation to technical passports, on-site coordination, testing and operational execution.

ØJE positions itself between contemporary art, festival culture and spatial production, engaging with complex contexts where artistic intent and technical precision carry equal weight.

[oje.studio](https://oje.studio) · [hello@oje.studio](mailto:hello@oje.studio)
