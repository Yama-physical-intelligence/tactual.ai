# Tactual: the sense of digital touch

Control your computer with your bare hand, using only a webcam. Tactual tracks your hand, draws a subtle
"ghost" of it on screen, and turns pinches and gestures into real clicks, scrolls, drags, zooms and desktop
switches. **Everything runs on-device**: no cloud, no video stored, no network after the first model download.

> **Status:** early prototype (v0.2), macOS only. The goal is *Minority Report* / *Iron Man* style control of
> every device; this repo is the first working slice.

- **[Gesture guide](docs/GESTURES.md)**: every gesture, with tips for getting it reliable
- **[Architecture](docs/ARCHITECTURE.md)**: how the pipeline and gesture engine work, and how to extend them
- **[Contributing](CONTRIBUTING.md)**: dev setup, tests, recording bug reports
- **[Research notes](docs/approach.html)**: prior art, benchmarks and design rationale (open in a browser)
- **[Changelog](CHANGELOG.md)**

---

## Highlights

- **Hand imprint on screen**: a faint, click-through outline of your hand (both hands while zooming), drawn
  over every window and full-screen app. An aim ring marks exactly where a click will land.
- **Pinch is the action**: the cursor sits where your thumb and index finger meet. You tap to click, pinch and
  move to scroll, pinch and twist to dial-scroll, and tap-then-pinch to drag.
- **Precise clicks**: the cursor freezes while you pinch, and *click rewind* places the click where you were
  aiming just before your fingers started closing.
- **Scroll anywhere**: if you pinch over something that can't scroll (a title bar or toolbar), the scroll is
  sent to the window's main scrollable area, found through the macOS Accessibility API. Fast scrolls keep gliding with momentum.
- **Two-hand zoom, at no cost**: Tactual tracks one hand (about 12 ms per frame) and switches to two-hand tracking only
  when a second hand appears.
- **Fits your hand**: a guided setup learns your pinch and fist, and a 5-second sweep maps your
  comfortable area to the whole screen.
- **Built for development**: a pure, unit-tested gesture engine, landmark-only session recording and replay,
  and JSON settings overrides.

## Gestures

| Gesture | Action |
|---|---|
| ☝️ Point / hover | Move the cursor (it follows the thumb–index pinch point) |
| 🤏 Tap thumb + index | Left click |
| 🤏🤏 Tap twice quickly | Double-click |
| 🤏↕️ Pinch and move | Scroll: content follows your hand; flick and release for momentum |
| 🤏🔄 Pinch and twist | Dial scroll: clockwise scrolls down, anticlockwise scrolls up |
| 🤏 → 🤏↔️ Tap, then pinch again and move | Drag and drop (like a trackpad tap-drag) |
| 🤌 Pinch thumb + middle | Right click |
| 🤏 + 🤏 Both hands pinch, spread / close | Zoom in / out (⌘+ / ⌘−) |
| 🖐 Open palm, swipe left / right | Switch desktop (Space) |
| 🖐 Open palm, swipe up / down | Mission Control / App windows |
| ✊ Hold a fist for 1 s | Pause / resume control |

A pinch held still does nothing, so resting in a pinch is safe. See the **[gesture guide](docs/GESTURES.md)**
for details and tips.

---

## Quick start

Requirements: macOS on Apple Silicon (developed on macOS 26.6, M1 Pro; Intel is untested), Python 3.11, and a webcam.

```sh
git clone https://github.com/Yama-physical-intelligence/tactual.ai.git
cd tactual.ai
./run.sh --dry-run    # safe first run: recognizes gestures, doesn't touch the mouse
./run.sh              # live
```

`run.sh` creates a virtualenv and installs dependencies on first run. The hand model
(`hand_landmarker.task`, about 8 MB) downloads automatically into `models/`.

### macOS permissions

Grant both permissions to the app you run it from (Terminal, iTerm, Ghostty, VS Code…) in
**System Settings → Privacy & Security**:

1. **Camera**: to see your hand.
2. **Accessibility**: to move the cursor, click, and find scrollable areas.

Fully quit and reopen that terminal after granting them.

### First run: setup (about 30 seconds)

On first launch (or with `--setup`):

1. **Gesture setup**: open hand → point → pinch thumb+index → pinch thumb+middle → fist. Each step waits
   until it sees the pose, then samples it for about 1 second. The results are saved to `gesture_profile.json`.
2. **Screen setup**: for 5 seconds, sweep your hand over the area you want to use and reach every edge. That
   area maps to the whole screen. The result is saved to `calibration.json`.

Instructions appear in a pill at the bottom of the screen. Redo either step at any time with `g` or `c`.

### Keys

With the preview window focused: `q` quit · `p` pause · `g` redo gesture setup · `c` redo screen setup ·
`esc` cancel setup. Without the preview (`--no-preview`), use a fist to pause and Ctrl+C in the terminal to quit.

### Options

| Flag | Effect |
|---|---|
| `--dry-run` | Recognize gestures and log them, but don't touch the mouse or keyboard |
| `--setup` / `--calibrate` | Run gesture + screen setup / screen setup only |
| `--hand Left` | Use the left hand as the primary hand |
| `--anchor pinch\|knuckle\|tip` | What the cursor follows (default: the pinch point) |
| `--hands auto\|one` | `auto` enables two-hand zoom on demand; `one` is the fastest mode, without zoom |
| `--no-smart-scroll` | Always scroll exactly under the pinch point |
| `--no-overlay` / `--no-preview` | Hide the on-screen hand imprint / the camera preview |
| `--config FILE.json` | Override any setting, e.g. `{"natural_scroll": false, "dial_gain": 20}` |
| `--record FILE.jsonl` | Record hand landmarks (never video) for replay and bug reports |
| `--camera N` | Use another camera |

All settings, with comments, live in [`fingering/config.py`](fingering/config.py).

---

## How it works

```
camera ─▶ tracker ─▶ features ─▶ gesture engine ─▶ mapping + 1€ filter ─▶ actuator ─▶ macOS
 17–33ms    ~12ms     <0.1ms         <0.2ms               <0.1ms            <1ms
                                                                    └▶ overlay (hand imprint)
```

- **Tracker**: MediaPipe Hand Landmarker in tracking mode, with automatic one- or two-hand switching.
- **Gesture engine**: a pure, deterministic state machine. It takes landmarks in and emits plain-data actions
  (`MoveCursor`, `Click`, `Scroll`, `Shortcut`…). It has no camera or OS code, so it's fully unit-tested.
- **Actuator**: native Quartz events, including real double-click state, drag events, two-axis pixel scrolling,
  Accessibility-based scroll targeting and Mission Control shortcuts.

End-to-end latency from hand movement to cursor movement is about 45–70 ms, and most of that is the
camera's frame time. Details are in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Development

```sh
.venv/bin/python -m pytest -q                            # run the tests (no camera needed)
./run.sh --record session.jsonl                          # record a session
.venv/bin/python -m fingering.record session.jsonl       # replay it: prints what the engine did
```

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Roadmap

- **Target-practice calibration**: on-screen targets that learn your aim offset, tap timing and drift from
  real attempts.
- **Adaptive learning**: gentle re-calibration from misses (a quick re-click next to the target, reversed
  scrolls, ⌘Z).
- **Snap to targets**: pull clicks onto nearby buttons and links using the Accessibility tree.
- **Trackpad-style relative mode**, for precise work with small hand movements.
- **Native Swift menu-bar app**: zero-copy camera to Neural Engine path, Apple Vision backend, signed builds.
- **Windows and Linux support**, plus user-defined gestures learned on-device.
- **AI layer**: voice plus pointing ("move *this* there"), per-app gesture bindings, and an MCP server exposing
  gestures and actions to agents.

## Known limitations

- macOS only, main display only.
- In dim light the camera drops to about 15 fps, which adds lag. Face a light source.
- Precision is below a trackpad for tiny targets.
- Holding your arm up is tiring. Rest your elbow on the desk and use a small sweep area.
- Zoom uses ⌘+ / ⌘−, which most apps support, but not every app.
