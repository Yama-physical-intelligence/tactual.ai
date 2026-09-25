import numpy as np
import pytest

from fingering.actions import Click, MouseButton, MoveCursor, Scroll, Shortcut
from fingering.config import Settings
from fingering.gestures import GestureEngine
from fingering.hand import INDEX_TIP, MIDDLE_TIP, THUMB_TIP, Hand, Pose
from fingering.mapping import ScreenMapper

DT = 1 / 30


def make_hand(cx=0.5, cy=0.5, fingers=(False, True, False, False, False), pinch=None, handedness="Right"):
    """Synthetic upright hand. fingers = extended (thumb, index, middle, ring, pinky); pinch = 'index'|'middle'."""
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


def test_calibration_maps_corners(engine):
    c = Clock()
    engine.start_calibration()
    corners = [(0.3, 0.3), (0.7, 0.3), (0.7, 0.6), (0.3, 0.6)]
    for x, y in corners:
        # pinched synthetic hand: pinch point = index tip + 0.0025 = (cx - 0.0275, cy - 0.1175)
        run(engine, c, 5, cx=x + 0.0275, cy=y + 0.1175)
        run(engine, c, 2, cx=x + 0.0275, cy=y + 0.1175, pinch="index")
    assert engine.calibrator is None
    assert engine.mapper.map(0.3, 0.3) == pytest.approx((0, 0), abs=2)
    assert engine.mapper.map(0.7, 0.6) == pytest.approx((999, 799), abs=2)
    assert (engine.s.calibration_path).exists()


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
