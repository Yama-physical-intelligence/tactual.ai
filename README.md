# Tactual: the sense of digital touch

Control your computer with your bare hand, using only a webcam. Tactual tracks your hand, draws a subtle
"ghost" of it on screen, and turns pinches and gestures into real clicks, scrolls, drags and desktop switches.
**Everything runs on-device**: no cloud, no video stored, no network after the first model download.

> **Status:** early prototype (v0.1), macOS only. The goal is *Minority Report* / *Iron Man* style control of
> every device; this repo is the first working slice. See the research and design notes in
> [`docs/approach.html`](docs/approach.html).

---

## What it does today

- **Hand imprint on screen**: a faint, click-through outline of your hand, drawn over every window and
  full-screen app, with an aim ring exactly where your thumb and index finger meet.
- **Pinch-to-act**: the cursor sits at your pinch point, and the cursor freezes while you pinch so clicks land where you aim.
- **Per-user gesture setup**: a guided 20-second setup measures *your* hand (open, point, pinch, fist) and
  sets detection thresholds from it.
- **Screen calibration**: map a comfortable hand area to the whole screen, so small, relaxed movements are enough.
- **Low latency**: hand tracking takes about 12 ms per frame on an M1 Pro, and OS events are sent through
  native Quartz calls in under 1 ms.

### Gestures

| Gesture | Action |
|---|---|
| ☝️ Point / hover | Move the cursor (it follows the thumb–index pinch point) |
| 🤏 Tap thumb + index | Left click |
| 🤏🤏 Tap twice quickly | Double-click |
| 🤏↕️ Pinch and move | Scroll: the page follows your hand, vertically and horizontally |
| 🤏 → 🤏↔️ Tap, then pinch again and move | Drag and drop (like a trackpad tap-drag) |
| 🤌 Pinch thumb + middle | Right click |
| 🖐 Open palm, swipe left / right | Switch desktop (Space) |
| 🖐 Open palm, swipe up / down | Mission Control / App windows |
| ✊ Hold a fist for 1 s | Pause / resume control |
| 🤏 + 🤏 Both hands pinch, spread / close | Zoom in / out (requires `--two-hands`) |

A pinch held still does nothing, so you can rest in a pinch safely.

---

## Quick start

Requirements: macOS on Apple Silicon (Intel should work but is untested), Python 3.11, and a webcam.

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
2. **Accessibility**: to move the cursor and click.

Fully quit and reopen that terminal after granting them.

### First run: setup

On first launch (or with `--setup`), Tactual walks you through:

1. **Gesture setup**: open hand → point → pinch thumb+index → pinch thumb+middle → fist. Each step waits
   until it sees the pose, then samples it for about 1 second. The results are saved to `gesture_profile.json`.
2. **Screen corners**: aim at each screen corner (top-left, top-right, bottom-right, bottom-left) and pinch.
   The results are saved to `calibration.json`.

Instructions appear in a pill at the bottom of the screen and in the preview window.

### Keys and options

With the preview window focused: `q` quit · `p` pause · `g` redo gesture setup · `c` redo screen corners ·
`esc` cancel setup.

```
./run.sh [--dry-run] [--setup] [--calibrate] [--hand Left] [--anchor pinch|knuckle|tip]
         [--two-hands] [--no-overlay] [--no-preview] [--camera N]
```

---

## How it works

```
camera ─▶ tracker ─▶ features ─▶ gesture engine ─▶ mapping + 1€ filter ─▶ actuator
 17–33ms    ~12ms     <0.1ms         <0.2ms               <0.1ms            <1ms
```

1. **Tracker** (`tracker.py`): MediaPipe Hand Landmarker in VIDEO mode. It runs the palm detector once, then
   only the cheap landmark model while tracking. It returns 21 landmarks and handedness per hand.
2. **Features** (`hand.py`): scale-invariant geometry: finger extension ratios, pinch distances normalized by
   hand size, the pinch point, and palm centre.
3. **Gesture engine** (`gestures.py`): a pure, deterministic state machine with hysteresis on every threshold
   and pose debouncing. It emits plain-data **Actions** (`MoveCursor`, `Click`, `Scroll`, `Shortcut`, …).
   It has no camera or OS dependencies, so it is fully unit-tested.
4. **Mapping** (`mapping.py`, `filters.py`): a perspective homography from the calibrated hand area to the
   screen, plus a [1€ filter](https://gery.casiez.net/1euro/) that stays steady when you're still and
   responsive when you move.
5. **Actuator** (`controller.py`): native `CGEventPost` for moves, clicks with real click-state (so double-click
   works), drags, pixel-precise two-axis scrolling, and Mission Control shortcuts.
6. **Overlay** (`overlay.py`): a transparent, click-through AppKit window that draws the hand imprint and setup
   prompts.

End-to-end latency from hand movement to cursor movement is roughly 45–70 ms, and most of it is the camera's frame
time. Tactual's own processing is about 13 ms.

### Project layout

```
fingering/
  app.py         main loop, CLI
  tracker.py     MediaPipe hand tracking
  hand.py        landmark geometry
  gestures.py    GestureEngine: landmarks -> Actions
  actions.py     Action data types
  profile.py     per-user gesture setup and profile
  mapping.py     screen calibration (homography)
  filters.py     1€ filter
  controller.py  macOS actuator (Quartz)
  overlay.py     on-screen hand imprint
  hud.py         preview-window overlay
  config.py      all tunable settings
tests/           engine tests with synthetic hands (no camera needed)
docs/            research and design notes
```

### Development

```sh
.venv/bin/python -m pytest -q
```

Every threshold lives in `fingering/config.py`. The engine consumes landmarks and emits Actions, so new gestures
are new rules in `gestures.py`; the OS layer doesn't change.

**Dependency note:** MediaPipe 1.0.x crashes on macOS (`graph_service.h: Service is unavailable`), so this
project pins `mediapipe==0.10.21`.

---

## Roadmap

- **Pinch-first control**: pinch at the pointed spot, detect whether the element under it is scrollable, and
  rotate thumb + index like a dial to scroll. Swipes become a pinch-and-fling instead of an open-palm wave.
- **Target practice calibration**: on-screen targets for each action, learning your aim offset, tap timing and
  drift from labelled attempts.
- **Adaptive learning**: implicit re-calibration from misses (a quick re-click next to the target, reversed scrolls, ⌘Z).
- **Accessibility-aware snapping**: snap clicks to real buttons and links using the macOS Accessibility tree.
- **Native Swift menu-bar app**: zero-copy camera to the Neural Engine, Apple Vision backend, signed builds.
- **Windows and Linux actuators**, plus user-defined gestures learned on-device.

## Known limitations

- macOS only, main display only.
- Needs decent lighting: in dim light the camera drops to about 15 fps, which adds lag.
- Precision is below a trackpad for tiny targets (Accessibility-aware snapping is planned).
- Holding your arm up is tiring. Calibrate a small, low hand area and rest your elbow on the desk.
