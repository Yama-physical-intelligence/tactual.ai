"""Record hand sessions (landmarks only, never video) and replay them through the gesture engine.

Record:  ./run.sh --record session.jsonl
Replay:  .venv/bin/python -m fingering.record session.jsonl      # prints what the engine does

Recordings make bugs reproducible ("it clicked when I scratched my nose") and are the raw
material for regression tests and future learned gestures.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Iterator

import numpy as np

from .hand import Hand


class Recorder:
    def __init__(self, path: Path):
        self._f = open(path, "w")

    def write(self, t: float, hands: list[Hand]) -> None:
        rec = {"t": round(t, 4), "hands": [
            {"h": h.handedness, "a": round(h.aspect, 4), "lm": np.round(h.landmarks, 5).tolist()} for h in hands
        ]}
        self._f.write(json.dumps(rec, separators=(",", ":")) + "\n")

    def close(self) -> None:
        self._f.close()


def read(path: Path) -> Iterator[tuple[float, list[Hand]]]:
    with open(path) as f:
        for line in f:
            rec = json.loads(line)
            yield rec["t"], [Hand(np.array(h["lm"]), h["h"], h["a"]) for h in rec["hands"]]


def replay(path: Path, config: Path | None = None) -> list[tuple[float, object]]:
    """Run a recording through a fresh engine using the saved profile/calibration; return actions."""
    from .actions import MoveCursor, Notice
    from .config import load_settings
    from .gestures import GestureEngine
    from .mapping import ScreenMapper
    from .profile import apply_profile, load_profile

    s = load_settings(config)
    profile = load_profile(s.profile_path)
    if profile:
        apply_profile(s, profile)
    engine = GestureEngine(s, ScreenMapper.load(s.calibration_path, 1512, 982))
    out = []
    for t, hands in read(path):
        out += [(t, a) for a in engine.update(hands, t) if not isinstance(a, (MoveCursor, Notice))]
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Replay a recorded hand session through the gesture engine.")
    p.add_argument("recording", type=Path)
    p.add_argument("--config", type=Path, help="settings JSON overrides")
    args = p.parse_args(argv)
    actions = replay(args.recording, args.config)
    t0 = actions[0][0] if actions else 0.0
    for t, a in actions:
        print(f"{t - t0:8.2f}s  {a}")
    print(f"{len(actions)} actions", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
