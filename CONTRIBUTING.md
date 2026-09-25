# Contributing to Tactual

Thanks for helping build touchless control that feels natural. This guide gets you from clone to a tested change.

## Setup

```sh
git clone https://github.com/Yama-physical-intelligence/tactual.ai.git
cd tactual.ai
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest -q
./run.sh --dry-run
```

Grant Camera and Accessibility access to your terminal (see the README). Use `--dry-run` while developing: gestures
are logged but the mouse and keyboard aren't touched.

## Project layout

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). In short:

- `fingering/gestures.py`: the gesture engine (pure logic; most changes land here)
- `fingering/hand.py`: landmark geometry
- `fingering/config.py`: every tunable, with comments
- `fingering/controller.py`, `fingering/ax.py`: the macOS output layer
- `fingering/tracker.py`: MediaPipe tracking
- `tests/`: engine tests with synthetic hands, plus I/O tests

## Tests

```sh
.venv/bin/python -m pytest -q
```

Tests build synthetic hands with `make_hand()` (in `tests/test_gestures.py`) and drive the engine frame by frame at
30 fps. No camera is needed. Every gesture change should come with tests for:

- the gesture firing when performed, and
- **nothing** firing for nearby, non-intended motions (the harder and more important half).

## Recording a bug report

Many bugs only show up with real hands. Record the problem, which saves landmarks only and never video:

```sh
./run.sh --dry-run --record bug.jsonl      # reproduce the problem, then press q
.venv/bin/python -m fingering.record bug.jsonl
```

The replay prints every action the engine produced, with timestamps. Attach `bug.jsonl` and your
`gesture_profile.json` to the issue, and describe what you did and what you expected.

## Guidelines

- **Keep the engine pure.** No camera, OS or time calls inside `gestures.py`; time comes in as `t`.
- **Normalize by hand size.** Thresholds on distances should be in hand units (`hand.scale`), not pixels or frame
  fractions, so they work at any distance from the camera.
- **Use hysteresis for every threshold** that toggles a state, and debounce poses.
- **Put new tunables in `Settings`**, with a comment explaining the unit and the effect.
- **Fail safe.** Anything interrupted (a lost hand, a pause) must release held buttons and swallow half-finished
  pinches.
- **Protect latency.** The per-frame path must stay well under a millisecond outside the model. Slow work (like the
  Accessibility lookup) runs once per gesture, not once per frame.
- Match the surrounding code style: type hints, small functions, and comments that explain *why*.

## Commit messages

Use a short imperative subject line, then a body explaining what changed and why, with numbers where relevant
(latency, thresholds).
