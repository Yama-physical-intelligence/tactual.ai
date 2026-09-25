# Changelog

## 0.2.0: 2026-09-26

### Added
- **Click rewind**: clicks land where you aimed just before your fingers started closing.
- **Dial scroll**: pinch and twist like a knob (clockwise = down).
- **Scroll momentum**: releasing a fast scroll keeps it gliding.
- **Smart scroll targeting**: scrolls started over non-scrollable UI go to the window's main scroll area
  (Accessibility API).
- **Two-hand zoom on by default**: `auto` hands mode tracks one hand and switches to two only when a second hand
  appears, so one-hand use stays at about 12 ms per frame. Both hand imprints are drawn.
- **Session recording and replay**: `--record FILE.jsonl` (landmarks only) and `python -m fingering.record FILE`.
- **Settings file**: `--config FILE.json` overrides any setting.
- Docs: gesture guide, architecture, contributing.

### Changed
- Screen setup is now a 5-second sweep of the usable area instead of pinching four corners.
- The gesture setup waits for each pose before sampling, and places thresholds near the measured pinch, with caps.
- Scrolling engages sooner (20 px instead of 30 px). Palm swipes are easier (12% travel in 0.35 s). Zoom steps are finer (15%).
- `--two-hands` is replaced by `--hands auto|one`.

### Fixed
- The cursor could freeze in place when setup produced loose pinch thresholds (a relaxed hand read as pinched).
- A lingering thumb+middle pinch could freeze the cursor.
- Corner calibration could count one flickering pinch as two corners.

## 0.1.0: 2026-09-26

First prototype: MediaPipe hand tracking, pinch-point cursor, tap / double-tap / pinch-scroll / tap-drag /
right-click, palm swipes for Spaces and Mission Control, fist to pause, per-user gesture setup, on-screen hand
imprint, native Quartz output.
