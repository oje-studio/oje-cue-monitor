# ØJE CUE MONITOR

macOS live show operator tool — LTC/SMPTE timecode reader + cue list manager with performance mode.

![Version](https://img.shields.io/badge/version-0.97beta-blue)
![Platform](https://img.shields.io/badge/platform-macOS-lightgrey)
![Python](https://img.shields.io/badge/python-3.9+-green)

## Features

- **LTC Timecode Decoding** — reads SMPTE/LTC timecode from any audio input via libltc
- **Cue List** — timed cues with names, descriptions, colors, section dividers
- **Per-Operator Comments** — configurable operator list, each cue has individual notes per operator
- **Performance Mode** — full-screen operator view with large fonts, countdown timer, operator columns
- **Show File Format (.ojeshow)** — single JSON file with all settings + cue list
- **Duplicate Timecode Detection** �� visual warnings for conflicting cues
- **Signal Monitoring** — VU meter, weak/clipping warnings, signal loss detection
- **Dark UI** — designed for backstage/booth environments

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Cmd+N` | New show |
| `Cmd+O` | Open show file / import CSV |
| `Cmd+S` | Save show |
| `P` | Toggle Performance Mode |
| `Escape` | Exit Performance Mode |
| `Space` | Manual cue mark |
| `F1` | Help |

## Installation

```bash
# Clone
git clone https://github.com/oje-studio/oje-cue-monitor.git
cd oje-cue-monitor

# Install dependencies (macOS)
bash setup.sh

# Run
python3 main.py
```

### Manual Setup

```bash
brew install portaudio libltc
pip3 install PyQt6 pyaudio numpy
```

## Build .app Bundle

```bash
bash build.sh
```

Produces `dist/ØJE CUE MONITOR.app` — drag to Applications.

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

- macOS (Apple Silicon or Intel)
- Python 3.9+
- libltc (`brew install libltc`)
- portaudio (`brew install portaudio`)

## License

© 2026 ØJE Studio. All rights reserved.
