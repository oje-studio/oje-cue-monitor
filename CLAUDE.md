# ØJE CUE MONITOR — Working Notes for Claude Code

> Project-local context for Claude Code sessions. Read on startup, update
> when conventions or open work changes. **Do not document features that
> already exist** — those live in the code. This file is for *what's in
> flight* and *what we've agreed*.

## Repo & branch

- Origin: `oje-studio/oje-cue-monitor`
- Active branch: **`cleanup/cue-monitor-polish`**
  - Built on top of Codex's `bb21bd2` on `main` (improved editing,
    performance, remote, and PDF workflows).
- `main` has not yet been updated with the polish branch; merge is
  pending operator review.
- An older branch `claude/continue-work-AKHpD` exists on remote with an
  earlier abandoned SHOW MONITOR experiment + Codex merge. Safe to
  delete once `cleanup/cue-monitor-polish` is merged.

## Apps in this repo

There is **only one app**: `ØJE CUE MONITOR` — a live-show LTC cue
monitor with a Performance Mode and a Web Remote.

Earlier attempts to scaffold a second app (`SHOW MONITOR` with
scene-based timing) were dropped; **do not re-create that work** unless
the operator explicitly asks again.

Entry point: `python3 main.py`. Build: `bash build.sh` (macOS) or
`build_win.bat` (Windows). PyInstaller specs: `OJECueMonitor.spec`,
`OJECueMonitor_win.spec`. CI in `.github/workflows/build.yml` produces
artefacts on push to `main` and a tagged release on `v*`.

## Working agreement with the operator

- After each fix: commit with a clear message that explains the *why*,
  then `git push` to the active branch. The operator pulls on their
  Mac and tests. Don't batch fixes into a single mega-commit.
- Never push to `main` directly — keep work on the feature branch.
- Tests where they exist live in `python3 -c "..."` smoke checks run
  with `QT_QPA_PLATFORM=offscreen`. There is no formal test suite;
  visual / behavioural verification on the operator's Mac is the
  acceptance signal.
- The operator runs the app with: `pkill -f "python3 main.py"`,
  `git pull`, `python3 main.py`. If a fix isn't reaching them, the
  most likely cause is a stale Python process holding port 8080.

## Things we've debugged once — keep these in mind

These are gotchas we already fixed; flag if they regress.

1. **`QLineEdit.setInputMask("00:00:00:00;0")`** — when the blank char
   equals a valid digit, `text()` strips typed zeros. Read
   `displayText()` instead. Fixed in `ui/cue_table.py` → see
   `TimecodePopup._try_apply`.
2. **CSS specificity tie** — `.hidden` rule must come AFTER `.overlay`
   *or* be marked `!important`. We use `!important` in `web_remote.py`.
3. **iOS Safari rubber-band scroll** — body needs `position: fixed`,
   `inset: 0`, `overscroll-behavior: none`, `touch-action: pan-y` to
   stop the page sliding under the finger.
4. **`100dvh` lets content slip under iOS Safari toolbar** — use
   `100svh` instead. Trade-off: tiny dark band when toolbar collapses,
   acceptable.
5. **iOS first-load zoom** — `meta viewport` needs
   `maximum-scale=1, user-scalable=no` to render at native scale on
   first paint (no "page is slightly too big until you pinch" state).
6. **Non-linear cue triggering** — cues are matched by timecode, not
   list order. `get_current_cue` walks every cue (no early `break`).
   `get_next_cue` walks the list FROM the current row (list order is
   show order). `is_past` in `cue_table.py` is by frames, not by row.
7. **`OP_COOKIE` in password mode** vs no-password mode — only honoured
   in password mode. No-password mode renders empty operator on every
   load so the picker shows. See `_handle_index` in `web_remote.py`.

## Open questions / tasks

### "No cue at this timecode" message
Tried four interpretations (strict equality, 30-s hold past last,
end-of-show clearing, persistent + UI hint), all reverted (`fe0d5ec`).
Operator's request is genuinely ambiguous between:
- *flash on hit* (cue current only at exact TC)
- *persistent until next* (current behaviour, never clears past last)
- *some hybrid* (clear past last but not too quickly)

**Don't reopen this without a concrete table from the operator:**
"LTC = X with cues at A,B,C → should show: Y." Until then the engine
stays as-is (persistent).

### Merge to `main`
Branch is ready. Operator hasn't given the green light to merge;
they want to test more first. When they say go: open a PR, merge,
optionally tag `v0.97.1` or similar so CI ships a release.

### `oje-studio/.github` org profile repo
The repo doesn't exist on GitHub yet. Operator needs to create it
manually (Claude's GitHub MCP scope is restricted to
`oje-studio/oje-cue-monitor`). When created, prepare
`profile/README.md` content based on the studio About section in
the main README.

### Stale branch
`claude/continue-work-AKHpD` on remote — old SHOW MONITOR experiment.
Delete after `cleanup/cue-monitor-polish` merges to `main`.

## Code map

```
main.py                # PyQt entry point
cue_engine.py          # Cue list + non-linear matching
ltc_decoder.py         # LTC audio → timecode (libltc + portaudio)
show_file.py           # .ojeshow JSON load/save
web_remote.py          # aiohttp server: HTTP + WebSocket + page render
ui/main_window.py      # Edit window + Performance toggle + PDF export
ui/cue_table.py        # Cue list table widget + TimecodePopup
ui/performance_view.py # Fullscreen operator view (clock, VU, cue card)
ui/settings_dialog.py  # Show settings (audio device, operators, etc.)
ui/remote_panel.py     # Mac panel showing remote URL + QR
ui/fonts.py            # Mac mono / sans helpers
```

## Conventions

- Tone in commit messages: explain the *why* + concrete symptom that
  prompted the change. The operator reads the log.
- Comments in code are sparing — only when *why* is non-obvious.
- Don't add features beyond what's asked. If a fix doesn't need
  surrounding cleanup, don't include it.
- Russian / English mix in chat is fine; commit messages and code
  comments are English only.
