# Architecture

Tactual is a one-way pipeline of small stages. Only the first stage touches the camera and only the last one
touches the OS, so everything in between is pure, deterministic and testable from recorded data.

```
┌────────┐   ┌─────────┐   ┌──────────┐   ┌────────────────┐   ┌─────────────┐   ┌──────────┐
│ camera │──▶│ tracker │──▶│ features │──▶│ gesture engine │──▶│ controller  │──▶│  macOS   │
└────────┘   └─────────┘   └──────────┘   └────────────────┘   └─────────────┘   └──────────┘
  app.py      tracker.py      hand.py        gestures.py         controller.py
  (OpenCV)    (MediaPipe)                    mapping.py          ax.py
                                             filters.py
                                             profile.py                      overlay.py (hand imprint)
```

| Stage | Module | Cost (M1 Pro) |
|---|---|---|
| Capture (mirrored frame, newest only) | `app.py` | 17–33 ms frame interval |
| Hand landmarks | `tracker.py` | ~12 ms (one hand), ~24 ms (two hands) |
| Geometry features | `hand.py` | < 0.1 ms |
| Gesture state machine | `gestures.py` | < 0.2 ms |
| Mapping + 1€ filter | `mapping.py`, `filters.py` | < 0.1 ms |
| OS events | `controller.py` | < 1 ms (plus ~35 ms once per scroll gesture for AX targeting) |

## Tracker (`tracker.py`)

MediaPipe Hand Landmarker in **VIDEO** mode runs the palm detector until it has found `num_hands` hands, then only
the landmark model on a crop around each tracked hand. With `num_hands=2` and one hand visible, it re-runs the
detector every frame (~38 ms). So in `auto` mode:

1. A one-hand tracker runs on every frame (~12 ms).
2. A background thread runs an IMAGE-mode two-hand detector about every 300 ms.
3. When the probe sees two hands, tracking switches to a two-hand tracker until the second hand has been gone for 1 s.
4. Each switch uses a **fresh** two-hand tracker, prepared in the background. A two-hand tracker that has been
   following a single hand doesn't reliably pick up a second hand appearing later.

MediaPipe is pinned to `0.10.21`, because `1.0.x` aborts on macOS in its Metal helper.

## Features (`hand.py`)

All distances are aspect-corrected and **normalized by hand size** (wrist → middle knuckle), so thresholds work at
any distance from the camera.

- `pinch_ratio(tip)`: thumb tip to fingertip, in hand sizes.
- `extension_ratios`: wrist→tip divided by wrist→PIP for each finger. Above ~1 means straight; below means curled.
- `pinch_point`: the midpoint of the thumb and index tips, which the cursor follows.
- `palm_center`: used for swipes.

## Gesture engine (`gestures.py`)

`GestureEngine.update(hands, t) -> list[Action]` is called once per frame. It never touches the OS; it returns
plain data (`actions.py`):

`MoveCursor(x, y)` · `Click(button, count)` · `MouseButton(button, down)` · `Scroll(dy, dx)` · `Shortcut(name)` · `Notice(text)`

### Per-frame flow

1. **Setup modes** take over first (gesture setup, then screen setup).
2. **Two-hand zoom**: if two hands are pinching for 4 or more frames, only zoom is processed.
3. **Pinch detection** with hysteresis (enter < exit) plus a *reach* guard: the fingertip must be away from
   the palm, so a thumb resting on a curled finger never counts as a pinch.
4. **Pose**, debounced over 3 frames: `pointer`, `palm`, `fist` or `none`. An active pinch forces `pointer`.
5. **Fist hold** toggles pause.
6. **Momentum** from a previous fling.
7. **Tracking**: the pinch point is mapped to the screen and 1€-filtered. A short history supports click rewind.
8. **Pinch state machine** (below).
9. **Cursor move**, unless frozen by a pinch.
10. **Palm swipe** detection.

### Pinch state machine (thumb + index)

```
                     tap (< tap_max_s, not moved)
        ┌──────────────────────────────────────────────▶ Click(count = 2 if second tap else 1)
        │
 pinch ─┴─▶ pending ──(held > tap_max_s)──▶ hold ──(release)──▶ nothing
              │  │                            │
              │  └──── twist > dial_start ────┴──▶ dial   ──(release)──▶ momentum
              │                               │
              └────── move > pinch_move ──────┴──▶ scroll ──(release)──▶ momentum
                     (or, if second tap) ─────────▶ drag   ──(release)──▶ MouseButton up
```

- Twist and move are compared relative to their thresholds; whichever is clearly larger wins.
- Movement is measured on the **raw** (unfiltered) position, because the filter keeps drifting for a moment after
  the pinch starts.
- The cursor is frozen while pinched (except while dragging). A right-pinch freezes it for only 0.4 s.
- Anything that interrupts a pinch (zoom, pause, hand lost) sets `_need_release`: the pinch is swallowed until the
  fingers open.

### Click rewind

Closing a pinch moves the pinch point, since the thumb travels toward the index finger. On pinch start, the engine
looks back up to `click_rewind_s` for the most recent frame where the fingers were still clearly open
(ratio > exit threshold) and places the cursor there. That's where the user was aiming.

## Mapping and calibration

- **Screen mapping** (`mapping.py`): a perspective homography from a region of the camera frame to the screen.
  Screen setup records the aim point for 5 s and uses the 5th–95th percentile box, with a minimum size.
- **1€ filter** (`filters.py`): its cutoff frequency rises with speed. There's no jitter at rest and little lag in motion.
- **Gesture profile** (`profile.py`): the setup samples each pose and places thresholds between the user's
  measured *pinched* and *open* values, near the pinched side and with hard caps. Raw measurements are kept in
  `gesture_profile.json` under `measured`.

## Controller (`controller.py`, `ax.py`)

- Mouse events go through `CGEventCreateMouseEvent` / `CGEventPost` at the HID tap. Click-state is set so
  double-clicks are real double-clicks, and moves become `LeftMouseDragged` while the button is down.
- Scrolling uses `CGEventCreateScrollWheelEvent` in pixel units, on two axes.
- **Smart scroll**: at the start of each scroll gesture, `ax.scroll_target` asks the Accessibility API for the
  element under the pinch point and walks up its parents. If it isn't inside an `AXScrollArea`/`AXWebArea`, it
  searches the window (bounded to 80 ms / 400 nodes) for the largest scroll area and posts the scroll there.
- Shortcuts are sent as keyboard events. Arrow keys need the Fn and NumericPad flags for the Mission Control and
  Spaces shortcuts to fire.

## Overlay (`overlay.py`)

A borderless, transparent `NSWindow` at screen-saver level that ignores mouse events and joins all Spaces. The
primary hand is drawn scaled to 0.7× around the pinch point and **pinned to the cursor**, so the ghost's fingertips
meet exactly where a click lands. Landmarks are smoothed with a light EMA.

## Adding a gesture

1. Add any new geometry to `Hand` (`hand.py`).
2. Add the detection logic to `GestureEngine` (`gestures.py`) and emit existing `Action`s. If you need a new
   action type, add it to `actions.py` and handle it in `MacController.execute`.
3. Put tunables in `Settings` (`config.py`), with a comment.
4. Write tests with the synthetic hand builder in `tests/test_gestures.py` (`make_hand(fingers=…, pinch=…,
   gap=…, angle=…)`).
5. Record a real session (`--record`) and replay it (`python -m fingering.record`) to check that the gesture fires
   when it should and stays silent when it shouldn't.
