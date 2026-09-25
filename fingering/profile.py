"""Per-user gesture calibration: record the user's own poses, derive thresholds from them.

Each step waits until the pose is actually seen (gated against the open-hand reference), then a
short settle, then ~1 s of samples. Thresholds are placed between the user's measured "open" and
"closed" values, so detection fits their hand and camera.
"""

import json
import logging
from dataclasses import fields
from pathlib import Path
from statistics import median

from .config import Settings
from .hand import INDEX_TIP, MIDDLE_TIP, WRIST, Hand

log = logging.getLogger(__name__)

STEPS = (
    ("palm", "OPEN your hand, fingers apart"),
    ("point", "Point with your index finger (relaxed)"),
    ("pinch_index", "Pinch THUMB + INDEX and hold"),
    ("pinch_middle", "Pinch THUMB + MIDDLE and hold"),
    ("fist", "Make a FIST and hold"),
)
SETTLE_S = 0.5
CAPTURE_S = 1.2
PROFILE_KEYS = ("pinch_enter", "pinch_exit", "pinch_enter_middle", "pinch_exit_middle",
                "pinch_min_reach", "extend_thresholds")


def features(hand: Hand) -> dict:
    return {
        "ri": hand.pinch_ratio(INDEX_TIP),
        "rm": hand.pinch_ratio(MIDDLE_TIP),
        "reach_i": hand.dist(WRIST, INDEX_TIP) / hand.scale,
        "reach_m": hand.dist(WRIST, MIDDLE_TIP) / hand.scale,
        "ext": hand.extension_ratios,
    }


class GestureCalibrator:
    def __init__(self):
        self.step = 0
        self.samples: dict[str, list[dict]] = {key: [] for key, _ in STEPS}
        self._t0: float | None = None
        self.progress = 0.0

    @property
    def done(self) -> bool:
        return self.step >= len(STEPS)

    @property
    def prompt(self) -> str:
        return f"Gesture setup {self.step + 1}/{len(STEPS)}: {STEPS[self.step][1]}"

    def _pose_seen(self, key: str, f: dict) -> bool:
        """Only start timing a step once the user is actually making that pose."""
        palm = self.samples["palm"]
        if key in ("palm", "point") or not palm:
            return True
        if key == "pinch_index":
            return f["ri"] < 0.5 * median(s["ri"] for s in palm)
        if key == "pinch_middle":
            return f["rm"] < 0.5 * median(s["rm"] for s in palm)
        # fist: average finger straightness at most halfway between "bent" (1.0) and the open palm
        open_ext = median(sum(s["ext"]) / 4 for s in palm)
        return sum(f["ext"]) / 4 < 1 + 0.5 * (open_ext - 1)

    def feed(self, hand: Hand | None, t: float) -> None:
        if self.done:
            return
        key = STEPS[self.step][0]
        if hand is None or not self._pose_seen(key, features(hand)):  # wait (restart) until the pose is held
            self._t0, self.progress = None, 0.0
            self.samples[key].clear()
            return
        if self._t0 is None:
            self._t0 = t
        elapsed = t - self._t0
        self.progress = min(elapsed / (SETTLE_S + CAPTURE_S), 1.0)
        if elapsed >= SETTLE_S:
            self.samples[STEPS[self.step][0]].append(features(hand))
        if elapsed >= SETTLE_S + CAPTURE_S:
            self.step += 1
            self._t0, self.progress = None, 0.0


def compute_profile(samples: dict[str, list[dict]]) -> dict:
    def med(step, key):
        return median(s[key] for s in samples[step])

    open_i = med("palm", "ri")  # "point" may have the thumb tucked near the index
    pinched_i = med("pinch_index", "ri")
    open_m = med("palm", "rm")  # not "point": a tucked thumb sits near the curled middle finger
    pinched_m = med("pinch_middle", "rm")
    for name, opened, pinched in (("index", open_i, pinched_i), ("middle", open_m, pinched_m)):
        if opened - pinched < 0.15:
            raise ValueError(f"{name} pinch wasn't distinct from the open hand, try again")

    # Fingertip reach threshold: halfway between a curled fist and a real pinch, so a thumb
    # resting on a curled finger never clicks. Fall back to 85% of pinch reach if they overlap.
    pinch_reach = min(med("pinch_index", "reach_i"), med("pinch_middle", "reach_m"))
    fist_reach = max(med("fist", "reach_i"), med("fist", "reach_m"))
    min_reach = (pinch_reach + fist_reach) / 2 if fist_reach < pinch_reach else 0.85 * pinch_reach
    ext = []
    for f in range(4):
        closed = median(s["ext"][f] for s in samples["fist"])
        opened = median(s["ext"][f] for s in samples["palm"])
        if opened - closed < 0.1:
            raise ValueError("fist and open hand looked too similar, try again")
        ext.append(round((closed + opened) / 2, 3))

    return {
        "pinch_enter": round(pinched_i + 0.35 * (open_i - pinched_i), 3),
        "pinch_exit": round(pinched_i + 0.6 * (open_i - pinched_i), 3),
        "pinch_enter_middle": round(pinched_m + 0.35 * (open_m - pinched_m), 3),
        "pinch_exit_middle": round(pinched_m + 0.6 * (open_m - pinched_m), 3),
        "pinch_min_reach": round(min_reach, 3),
        "extend_thresholds": ext,
    }


def apply_profile(settings: Settings, profile: dict) -> None:
    names = {f.name for f in fields(settings)}
    for key in PROFILE_KEYS:
        if key in profile and key in names:
            value = profile[key]
            setattr(settings, key, tuple(value) if isinstance(value, list) else float(value))


def save_profile(path: Path, profile: dict) -> None:
    path.write_text(json.dumps(profile, indent=2))


def load_profile(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return None
    except (ValueError, OSError) as e:
        log.warning("Ignoring invalid gesture profile %s: %s", path, e)
        return None
