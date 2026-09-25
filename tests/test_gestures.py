import math

import numpy as np
import pytest

from fingering.actions import Click, MouseButton, MoveCursor, Scroll, Shortcut
from fingering.config import Settings
from fingering.gestures import GestureEngine
from fingering.hand import INDEX_TIP, MIDDLE_TIP, THUMB_TIP, Hand, Pose
from fingering.mapping import ScreenMapper

DT = 1 / 30


def make_hand(cx=0.5, cy=0.5, fingers=(False, True, False, False, False), pinch=None, handedness="Right",
              gap=None, angle=0.0):
    """Synthetic upright hand. fingers = extended (thumb, index, middle, ring, pinky); pinch = 'index'|'middle'.
    gap: thumb tip this far right of the index tip (a half-closed pinch). angle: roll in degrees."""
    lm = np.zeros((21, 2))
    lm[0] = (cx, cy + 0.15)  # wrist
    for f, dx in enumerate((-0.03, 0.0, 0.03, 0.06)):
        base = 5 + 4 * f
        ext = fingers[f + 1]
        lm[base] = (cx + dx, cy)
        lm[base + 1] = (cx + dx, cy - 0.05 if ext else cy - 0.03)
        lm[base + 2] = (cx + dx, cy - 0.09 if ext else cy - 0.01)
        lm[base + 3] = (cx + dx, cy - 0.12 if ext else cy + 0.02)
    lm[1] = (cx - 0.04, cy + 0.11)
    lm[2] = (cx - 0.06, cy + 0.08)
    lm[3] = (cx - 0.09, cy + 0.05)
    lm[4] = (cx - 0.13, cy + 0.02) if fingers[0] else (cx - 0.01, cy + 0.05)
    if pinch:
        lm[THUMB_TIP] = lm[INDEX_TIP if pinch == "index" else MIDDLE_TIP] + 0.005
    if gap is not None:
        lm[THUMB_TIP] = lm[INDEX_TIP] + (gap, 0.0)
    if angle:
        r = np.radians(angle)
        rot = np.array([[np.cos(r), -np.sin(r)], [np.sin(r), np.cos(r)]])
        pivot = lm[INDEX_TIP].copy()  # twisting a pinch turns the hand around the pinch point
        lm = (lm - pivot) @ rot.T + pivot
    return Hand(lm, handedness, aspect=1.0)


POINT = (False, True, False, False, False)
PALM = (True, True, True, True, True)
FIST = (False, False, False, False, False)
TWO = (False, True, True, False, False)


@pytest.fixture
def engine(tmp_path):
    s = Settings(calibration_path=tmp_path / "cal.json", profile_path=tmp_path / "profile.json")
    return GestureEngine(s, ScreenMapper(1000, 800))


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        self.t += DT
        return self.t


def run(engine, clock, frames, **hand_kw):
    out = []
    for _ in range(frames):
        out += engine.update([make_hand(**hand_kw)], clock())
    return [a for a in out if not a.__class__.__name__ == "Notice"]


def test_thumb_resting_on_curled_finger_is_not_a_pinch(engine):
    c = Clock()
    out = run(engine, c, 10) + run(engine, c, 10, fingers=FIST)
    assert not any(isinstance(a, (Click, MouseButton)) for a in out)


def test_finger_detection():
    assert make_hand(fingers=PALM).fingers == PALM
    assert make_hand(fingers=FIST).fingers == FIST
    assert make_hand(fingers=TWO).fingers == TWO
    assert make_hand(pinch="index").pinch_ratio(INDEX_TIP) < 0.1


def test_point_moves_cursor(engine):
    c = Clock()
    run(engine, c, 5, cx=0.4)
    moves = [a for a in run(engine, c, 10, cx=0.6) if isinstance(a, MoveCursor)]
    assert moves and moves[-1].x > 500
    assert engine.pose is Pose.POINTER


def test_quick_pinch_clicks_and_holds_cursor(engine):
    c = Clock()
    run(engine, c, 5)
    during = run(engine, c, 3, pinch="index")
    assert not any(isinstance(a, (MoveCursor, Click)) for a in during)  # steady click
    after = run(engine, c, 1)
    assert Click("left", 1) in after


def test_double_click(engine):
    c = Clock()
    run(engine, c, 5)
    run(engine, c, 3, pinch="index"); run(engine, c, 2)
    run(engine, c, 3, pinch="index")
    assert Click("left", 2) in run(engine, c, 1)


def test_pinch_and_move_scrolls(engine):
    c = Clock()
    run(engine, c, 5)
    out = []
    for i in range(10):
        out += engine.update([make_hand(pinch="index", cy=0.5 + 0.01 * i)], c())
    released = run(engine, c, 1, cy=0.6)
    scrolls = [a for a in out if isinstance(a, Scroll)]
    assert scrolls and all(sc.dy > 0 for sc in scrolls)  # natural: hand down -> content down
    assert not any(isinstance(a, (Click, MouseButton, MoveCursor)) for a in out)  # cursor holds while scrolling
    assert not any(isinstance(a, (Click, MouseButton)) for a in released)


def test_long_still_pinch_does_nothing(engine):
    c = Clock()
    run(engine, c, 5)
    out = run(engine, c, 20, pinch="index") + run(engine, c, 2)
    assert not any(isinstance(a, (Click, MouseButton, Scroll)) for a in out)


def tap_then_drag(engine, c):
    run(engine, c, 5)
    run(engine, c, 3, pinch="index"); run(engine, c, 2)  # tap
    out = run(engine, c, 2, pinch="index")
    for i in range(6):
        out += engine.update([make_hand(pinch="index", cx=0.5 + 0.02 * i)], c())
    return out


def test_tap_then_pinch_move_drags(engine):
    c = Clock()
    out = tap_then_drag(engine, c)
    assert MouseButton("left", True) in out
    assert any(isinstance(a, MoveCursor) for a in out)
    released = run(engine, c, 1, cx=0.6)
    assert MouseButton("left", False) in released
    assert not any(isinstance(a, Click) for a in released)


def test_right_click(engine):
    c = Clock()
    run(engine, c, 5)
    assert Click("right") in run(engine, c, 2, fingers=TWO, pinch="middle")
    assert not any(isinstance(a, Click) for a in run(engine, c, 2))


def test_palm_swipe_switches_space(engine):
    c = Clock()
    run(engine, c, 5, fingers=PALM, cx=0.7)
    out = []
    for i in range(8):
        out += engine.update([make_hand(fingers=PALM, cx=0.7 - 0.04 * i)], c())
    assert Shortcut("space_right") in out  # natural: hand moves left -> go right
    assert not any(isinstance(a, MoveCursor) for a in out)


def test_fist_toggles_pause(engine):
    c = Clock()
    run(engine, c, 40, fingers=FIST)
    assert not engine.enabled
    assert run(engine, c, 10, cx=0.8) == []  # paused: nothing happens
    run(engine, c, 40, fingers=FIST)
    assert engine.enabled


def test_two_hand_zoom_no_click(engine):
    c = Clock()
    run(engine, c, 5)
    out = []
    for gap in (0.1, 0.1, 0.15, 0.2, 0.25):
        hands = [make_hand(cx=0.5 - gap, pinch="index"), make_hand(cx=0.5 + gap, pinch="index", handedness="Left")]
        out += engine.update(hands, c())
    assert Shortcut("zoom_in") in out
    out += run(engine, c, 3)  # release the pinch with one hand
    assert not any(isinstance(a, Click) for a in out)


def test_hand_lost_releases_drag(engine):
    c = Clock()
    tap_then_drag(engine, c)
    assert engine.mode == "drag"
    out = []
    for _ in range(15):
        out += engine.update([], c())
    assert MouseButton("left", False) in out


def test_screen_setup_maps_swept_area(engine):
    c = Clock()
    engine.start_calibration()
    # sweep the (unpinched) aim point around a 0.3..0.7 x 0.3..0.6 rectangle; aim = (cx - 0.005, cy - 0.035)
    path = [(0.3 + 0.4 * k / 20, 0.3) for k in range(21)] + [(0.7, 0.3 + 0.3 * k / 20) for k in range(21)]
    path += [(0.7 - 0.4 * k / 20, 0.6) for k in range(21)] + [(0.3, 0.6 - 0.3 * k / 20) for k in range(21)]
    for k in range(200):
        x, y = path[k % len(path)]
        engine.update([make_hand(cx=x + 0.005, cy=y + 0.035)], c())
    assert engine.calibrator is None
    assert engine.s.calibration_path.exists()
    (x0, y0), _, (x1, y1), _ = engine.mapper.corners
    assert x0 == pytest.approx(0.3, abs=0.03) and x1 == pytest.approx(0.7, abs=0.03)
    assert y0 == pytest.approx(0.3, abs=0.03) and y1 == pytest.approx(0.6, abs=0.03)


def test_screen_setup_enforces_minimum_area(engine):
    c = Clock()
    engine.start_calibration()
    for _ in range(200):  # hand barely moves
        engine.update([make_hand()], c())
    (x0, y0), _, (x1, y1), _ = engine.mapper.corners
    assert x1 - x0 >= 0.2 - 1e-9 and y1 - y0 >= 0.15 - 1e-9


def test_lingering_right_pinch_does_not_freeze_cursor(engine):
    c = Clock()
    run(engine, c, 5)
    out = []
    for i in range(30):
        out += engine.update([make_hand(fingers=TWO, pinch="middle", cx=0.4 + 0.01 * i)], c())
    assert Click("right") in out
    assert any(isinstance(a, MoveCursor) for a in out)


def test_profile_thresholds_are_clamped():
    from fingering.profile import compute_profile
    def sample(ri, rm, ext, reach=1.6):
        return {"ri": ri, "rm": rm, "reach_i": reach, "reach_m": reach, "ext": (ext,) * 4}
    samples = {  # loose measurements like a real failed run: sloppy middle pinch, big open hand
        "palm": [sample(1.15, 1.56, 1.13)] * 5, "point": [sample(1.0, 0.5, 1.05)] * 5,
        "pinch_index": [sample(0.17, 1.0, 1.05)] * 5, "pinch_middle": [sample(1.0, 0.48, 1.05)] * 5,
        "fist": [sample(0.3, 0.3, 0.9, reach=0.9)] * 5,
    }
    prof = compute_profile(samples)
    assert prof["pinch_enter"] <= 0.40 and prof["pinch_exit"] <= 0.55
    assert prof["pinch_enter_middle"] <= 0.50 and prof["pinch_exit_middle"] <= 0.65
    assert prof["pinch_enter"] < prof["pinch_exit"]


def test_gesture_calibration_builds_profile(engine):
    c = Clock()
    engine.start_gesture_calibration(then_screen=True)
    poses = [dict(fingers=PALM), dict(), dict(pinch="index"), dict(fingers=TWO, pinch="middle"), dict(fingers=FIST)]
    for kw in poses:
        run(engine, c, 70, **kw)  # settle + capture at 30 fps
    assert engine.gesture_calibrator is None
    assert engine.calibrator is not None  # wizard continues to screen corners
    s = engine.s
    assert 0 < s.pinch_enter < s.pinch_exit
    assert 0 < s.pinch_enter_middle < s.pinch_exit_middle
    assert len(s.extend_thresholds) == 4
    assert s.profile_path.exists()
    engine.cancel_calibration()
    # calibrated engine still recognizes gestures
    run(engine, c, 10)
    run(engine, c, 3, pinch="index")
    assert Click("left", 1) in run(engine, c, 2)


def test_gesture_calibration_waits_for_real_pinch(engine):
    c = Clock()
    engine.start_gesture_calibration()
    run(engine, c, 70, fingers=PALM)
    run(engine, c, 70)
    run(engine, c, 200)  # never actually pinches: setup keeps waiting instead of saving junk
    assert engine.gesture_calibrator is not None and engine.gesture_calibrator.step == 2


def test_click_rewinds_to_aim_before_fingers_closed(engine):
    c = Clock()
    run(engine, c, 20, cx=0.5)  # settle aim
    aim = engine.cursor
    run(engine, c, 2, cx=0.5, gap=0.057)  # fingers half-closed: pinch point drifts
    out = run(engine, c, 2, cx=0.5, pinch="index")
    out += run(engine, c, 1, cx=0.5)
    assert Click("left", 1) in out
    moves = [a for a in out if isinstance(a, MoveCursor)]
    assert moves and math.dist((moves[0].x, moves[0].y), aim) < 3


def test_twist_while_pinched_dial_scrolls(engine):
    c = Clock()
    run(engine, c, 5)
    out = []
    for deg in range(0, 60, 4):
        out += engine.update([make_hand(pinch="index", angle=deg)], c())
    scrolls = [a for a in out if isinstance(a, Scroll)]
    assert engine.mode == "dial"
    assert scrolls and sum(sc.dy for sc in scrolls) < 0  # clockwise -> scroll down
    assert not any(isinstance(a, Click) for a in out + run(engine, c, 2))


def test_fast_scroll_release_has_momentum(engine):
    c = Clock()
    run(engine, c, 5)
    for i in range(8):
        engine.update([make_hand(pinch="index", cy=0.4 + 0.03 * i)], c())
    run(engine, c, 1, cy=0.64)  # release
    after = run(engine, c, 10, cy=0.64)
    assert any(isinstance(a, Scroll) and a.dy > 0 for a in after)
