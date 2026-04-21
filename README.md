# ØJE CUE MONITOR

Live show operator tool — LTC/SMPTE timecode reader + cue list manager with performance mode.

[oje.studio](https://oje.studio) · [hello@oje.studio](mailto:hello@oje.studio)

![Version](https://img.shields.io/badge/version-0.97beta-blue)
![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Windows-lightgrey)
![Python](https://img.shields.io/badge/python-3.9+-green)

## Features

- **LTC Timecode Decoding** — reads SMPTE/LTC timecode from any audio input via libltc
- **Non-Linear Cue Triggering** — cues trigger by timecode hit in user-defined order, not sorted
- **Cue List** — timed cues with names, descriptions, colors, section dividers
- **Per-Operator Comments** — configurable operator list, each cue has individual notes per operator
- **Performance Mode** — full-screen operator view with large fonts, countdown timer, operator columns
- **Web Remote** — serve Performance View to any device on the local network via WebSocket
- **Show File Format (.ojeshow)** — single JSON file with all settings + cue list
- **Duplicate Timecode Detection** — visual warnings for conflicting cues
- **Signal Monitoring** — VU meter, weak/clipping warnings, signal loss detection
- **Dark UI** — designed for backstage/booth environments

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

**ØJE Studio** — [oje.studio](https://oje.studio) · [hello@oje.studio](mailto:hello@oje.studio)
