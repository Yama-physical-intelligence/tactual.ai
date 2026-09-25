"""Gesture engine: turns per-frame hand landmarks into Actions.

Pure logic with no camera or OS dependencies, so it can be unit-tested and replayed.

Gestures (primary hand). The cursor sits where thumb and index tips meet.
  point / hover                    -> move cursor
  tap thumb+index                  -> left click; tap twice -> double-click
  pinch thumb+index and move       -> scroll (content follows the hand, both axes)
  tap, then pinch again and move   -> drag, release to drop (like a trackpad tap-drag)
  pinch thumb+middle               -> right click
  open palm swipe L/R/U/D          -> switch Space / Mission Control / App windows
  fist held                        -> pause / resume
Two hands (--two-hands), both pinching, spread/close -> zoom in / out
"""

import math
from collections import deque

from .actions import Action, Click, MouseButton, MoveCursor, Notice, Scroll, Shortcut
from .config import Settings
from .filters import OneEuroFilter
from .hand import INDEX_MCP, INDEX_TIP, MIDDLE_TIP, THUMB_TIP, WRIST, Hand, Pose
from .mapping import Calibrator, ScreenMapper
from .profile import GestureCalibrator, apply_profile, compute_profile, save_profile


class GestureEngine:
    def __init__(self, settings: Settings, mapper: ScreenMapper):
        self.s = settings
        self.mapper = mapper
        self.enabled = True
        self._fx = OneEuroFilter(settings.filter_min_cutoff, settings.filter_beta)
        self._fy = OneEuroFilter(settings.filter_min_cutoff, settings.filter_beta)
        self.cursor: tuple[float, float] | None = None
        self.anchor: tuple[float, float] | None = None  # normalized camera coords, for the HUD
        self.hand: Hand | None = None  # primary hand of the last frame
        self.last_event = ""
        self.fist_progress = 0.0
        self.calibrator: Calibrator | None = None
        self.gesture_calibrator: GestureCalibrator | None = None
        self.then_calibrate_screen = False  # first-run wizard: gestures, then screen corners
        self._last_tap_t = -math.inf
        self._reset_tracking()

    def _reset_tracking(self) -> None:
        self.pose = Pose.NONE
        self._pose_candidate = Pose.NONE
        self._pose_count = 0
        self._pinch: str | None = None  # None | "left" | "right"
        self._pinch_t0 = 0.0
        self._pinch_mode: str | None = None  # "pending" (maybe a tap) | "hold" | "scroll" | "drag"
        self._pinch_origin: tuple[float, float] | None = None
        self._pinch_is_second = False  # pinch started right after a tap: double-click or drag
        self._pos: tuple[float, float] | None = None  # filtered screen position of the anchor
        self._raw_pos: tuple[float, float] | None = None  # unfiltered (no lag), for movement tests
        self._scroll_acc = (0.0, 0.0)
        self._dragging = False
        self._need_release = False  # swallow a pinch that was interrupted (zoom/pause/lost hand)
        self._scroll_ref: tuple[float, float] | None = None
        self._swipe_hist: deque = deque()
        self._swipe_block_until = 0.0
        self.zooming = False
        self._zoom_base = 0.0
        self._zoom_count = 0
        self._fist_t0: float | None = None
        self._fist_armed = True
        self.fist_progress = 0.0
        self._last_seen: float | None = None
        self._fx.reset()
        self._fy.reset()

    # ------------------------------------------------------------------ public

    @property
    def mode(self) -> str:
        if self.gesture_calibrator:
            return "gesture setup"
        if self.calibrator:
            return "calibrating"
        if not self.enabled:
            return "paused"
        if self.zooming:
            return "zoom"
        if self._dragging:
            return "drag"
        if self._pinch_mode == "scroll":
            return "scroll"
        if self._pinch:
            return f"pinch-{self._pinch}"
        return self.pose.value

    @property
    def setup_progress(self) -> float:
        cal = self.gesture_calibrator or self.calibrator
        return cal.progress if cal else 0.0

    @property
    def prompt(self) -> str | None:
        """Instruction to show the user during setup, else None."""
        if self.gesture_calibrator:
            return self.gesture_calibrator.prompt
        if self.calibrator:
            return self.calibrator.prompt
        return None

    def update(self, hands: list[Hand], t: float) -> list[Action]:
        if self.gesture_calibrator:
            return self._calibrate_gestures(hands, t)
        if not hands:
            if self._last_seen is not None and t - self._last_seen > self.s.hand_lost_s:
                out = self._release()
                self._reset_tracking()
                self._need_release = True  # a hand re-entering mid-pinch must not click
                self.anchor = self.hand = None
                return out
            return []
        self._last_seen = t
        hand = self.hand = self._primary(hands)
        self.anchor = self._anchor_point(hand)

        if self.calibrator:
            return self._calibrate(hand, t)

        out: list[Action] = []
        if self.enabled:
            zoom = self._zoom(hands)
            if zoom is not None:
                return zoom

        edge = self._update_pinch(hand)
        pose = self._update_pose(hand)
        out += self._update_fist(pose, t)
        if not self.enabled or pose is Pose.FIST:
            return out
        if pose is Pose.POINTER:
            self._track(hand, t)
        out += self._pinch_actions(edge, t)
        if pose is Pose.POINTER:
            out += self._move(t)
        out += self._swipe(hand, pose, t)
        return out

    def set_enabled(self, enabled: bool) -> list[Action]:
        out = [] if enabled else self._release()
        self.enabled = enabled
        out.append(self._event("control ON" if enabled else "control PAUSED"))
        return out

    def start_calibration(self) -> list[Action]:
        out = self._release()
        self.calibrator = Calibrator()
        out.append(self._event("calibration started"))
        return out

    def cancel_calibration(self) -> list[Action]:
        self.calibrator = self.gesture_calibrator = None
        self.then_calibrate_screen = False
        return [self._event("calibration cancelled")]

    def start_gesture_calibration(self, then_screen: bool = False) -> list[Action]:
        out = self._release()
        self.calibrator = None
        self.gesture_calibrator = GestureCalibrator()
        self.then_calibrate_screen = then_screen
        out.append(self._event("gesture setup started"))
        return out

    def reset(self) -> list[Action]:
        """Release anything held (call on shutdown)."""
        return self._release()

    # ----------------------------------------------------------------- helpers

    def _event(self, text: str) -> Notice:
        self.last_event = text
        return Notice(text)

    def _primary(self, hands: list[Hand]) -> Hand:
        for h in hands:
            if h.handedness == self.s.primary_hand:
                return h
        return hands[0]

    def _release(self) -> list[Action]:
        out: list[Action] = []
        if self._dragging:
            out.append(MouseButton("left", False))
            self._dragging = False
        if self._pinch:
            self._pinch, self._pinch_mode = None, None
            self._need_release = True
        return out

    def _anchor_point(self, hand: Hand) -> tuple[float, float]:
        if self.s.cursor_anchor == "pinch":
            return hand.pinch_point
        return hand.point(INDEX_MCP if self.s.cursor_anchor == "knuckle" else INDEX_TIP)

    # ------------------------------------------------------------------- pinch

    def _update_pinch(self, hand: Hand):
        ri, rm = hand.pinch_ratio(INDEX_TIP), hand.pinch_ratio(MIDDLE_TIP)
        # A real pinch holds the fingertip away from the palm; a thumb resting on a curled finger doesn't.
        reach = lambda tip: hand.dist(WRIST, tip) / hand.scale > self.s.pinch_min_reach  # noqa: E731
        if self._need_release:
            if ri > self.s.pinch_exit and (rm > self.s.pinch_exit_middle or not reach(MIDDLE_TIP)):
                self._need_release = False
            return None
        if self._pinch is None:
            if self.pose is Pose.FIST:
                return None
            if ri < self.s.pinch_enter and ri <= rm and reach(INDEX_TIP):
                self._pinch = "left"
            elif rm < self.s.pinch_enter_middle and reach(MIDDLE_TIP):
                self._pinch = "right"
            return ("start", self._pinch) if self._pinch else None
        r, exit_thr = (ri, self.s.pinch_exit) if self._pinch == "left" else (rm, self.s.pinch_exit_middle)
        if r > exit_thr:
            kind, self._pinch = self._pinch, None
            return ("end", kind)
        return None

    def _pinch_actions(self, edge, t: float) -> list[Action]:
        if edge is None:
            return self._pinch_held(t) if self._pinch == "left" else []
        phase, kind = edge
        if kind == "right":
            if phase == "start":
                self._pinch_t0 = t
                return [Click("right"), self._event("right click")]
            return []
        if phase == "start":
            self._pinch_t0, self._pinch_mode, self._pinch_origin = t, "pending", self._raw_pos
            self._pinch_is_second = t - self._last_tap_t < self.s.double_click_s
            return []
        mode, self._pinch_mode = self._pinch_mode, None
        if mode == "drag":
            self._dragging = False
            return [MouseButton("left", False), self._event("drop")]
        if mode != "pending":  # scroll finished, or a long still hold: no click
            return []
        if self._pinch_is_second:
            self._last_tap_t = -math.inf
            return [Click("left", 2), self._event("double click")]
        self._last_tap_t = t
        return [Click("left", 1), self._event("click")]

    def _pinch_held(self, t: float) -> list[Action]:
        raw, origin = self._raw_pos, self._pinch_origin
        if raw is None or origin is None:
            return []
        if self._pinch_mode == "scroll":
            return self._scroll_step(self._pos)
        if self._pinch_mode not in ("pending", "hold"):
            return []
        if math.hypot(raw[0] - origin[0], raw[1] - origin[1]) < self.s.pinch_move_px:
            if self._pinch_mode == "pending" and t - self._pinch_t0 > self.s.tap_max_s:
                self._pinch_mode = "hold"  # too long for a tap; still becomes scroll/drag if moved
            return []
        if self._pinch_is_second:
            self._pinch_mode, self._dragging = "drag", True
            return [MouseButton("left", True), self._event("drag")]
        self._pinch_mode, self._scroll_ref, self._scroll_acc = "scroll", self._pos, (0.0, 0.0)
        return [self._event("scroll")]

    def _scroll_step(self, pos: tuple[float, float]) -> list[Action]:
        k = self.s.scroll_gain * (1 if self.s.natural_scroll else -1)
        ax = self._scroll_acc[0] + (pos[0] - self._scroll_ref[0]) * k
        ay = self._scroll_acc[1] + (pos[1] - self._scroll_ref[1]) * k
        self._scroll_ref = pos
        dx, dy = int(ax), int(ay)
        self._scroll_acc = (ax - dx, ay - dy)
        return [Scroll(dy, dx)] if dx or dy else []

    # -------------------------------------------------------------------- pose

    def _raw_pose(self, hand: Hand) -> Pose:
        if self._pinch:
            return Pose.POINTER
        index, middle, ring, pinky = hand.extended(self.s.extend_thresholds)
        if not (index or middle or ring or pinky):
            return Pose.FIST
        if index and middle and ring and pinky:
            return Pose.PALM
        return Pose.POINTER if index else Pose.NONE

    def _update_pose(self, hand: Hand) -> Pose:
        raw = self._raw_pose(hand)
        if raw is self.pose:
            self._pose_count = 0
            return self.pose
        if raw is self._pose_candidate:
            self._pose_count += 1
        else:
            self._pose_candidate, self._pose_count = raw, 1
        if self._pose_count >= self.s.pose_stable_frames or self._pinch:
            self.pose, self._pose_count = raw, 0
            self._swipe_hist.clear()
        return self.pose

    # ------------------------------------------------------------------ motion

    def _track(self, hand: Hand, t: float) -> None:
        sx, sy = self._raw_pos = self.mapper.map(*self._anchor_point(hand))
        self._pos = (self._fx(sx, t), self._fy(sy, t))

    def _move(self, t: float) -> list[Action]:
        # Steady click: hold the cursor still while left-pinched (unless dragging), and only
        # briefly for a right-click so a lingering middle pinch can never freeze the cursor.
        frozen = (self._pinch == "left" and not self._dragging) or (
            self._pinch == "right" and t - self._pinch_t0 < 0.4)
        if self._pos is None or frozen:
            return []
        fx, fy = self._pos
        if self.cursor and math.hypot(fx - self.cursor[0], fy - self.cursor[1]) < self.s.move_deadzone_px:
            return []
        self.cursor = (fx, fy)
        return [MoveCursor(fx, fy)]

    def _swipe(self, hand: Hand, pose: Pose, t: float) -> list[Action]:
        if pose is not Pose.PALM:
            self._swipe_hist.clear()
            return []
        self._swipe_hist.append((t, *hand.palm_center))
        while t - self._swipe_hist[0][0] > self.s.swipe_window_s:
            self._swipe_hist.popleft()
        if t < self._swipe_block_until or len(self._swipe_hist) < 3:
            return []
        _, x0, y0 = self._swipe_hist[0]
        _, x1, y1 = self._swipe_hist[-1]
        dx, dy = x1 - x0, y1 - y0
        name = None
        if abs(dx) >= self.s.swipe_min_dist and abs(dx) > 1.5 * abs(dy):
            name = "space_right" if (dx < 0) == self.s.natural_swipe else "space_left"
        elif abs(dy) >= self.s.swipe_min_dist and abs(dy) > 1.5 * abs(dx):
            name = "mission_control" if dy < 0 else "app_windows"
        if not name:
            return []
        self._swipe_block_until = t + self.s.swipe_cooldown_s
        self._swipe_hist.clear()
        return [Shortcut(name), self._event(name.replace("_", " "))]

    # -------------------------------------------------------------------- zoom

    def _zoom(self, hands: list[Hand]) -> list[Action] | None:
        """Both hands pinching: spread = zoom in, close = zoom out. None = not zooming."""
        thr = self.s.pinch_exit if self.zooming else self.s.pinch_enter
        if len(hands) < 2 or not all(h.pinch_ratio(INDEX_TIP) < thr for h in hands[:2]):
            self.zooming, self._zoom_count = False, 0
            return None
        if not self.zooming:  # both hands must pinch for a few frames: avoids accidental zoom
            self._zoom_count += 1
            if self._zoom_count < self.s.zoom_stable_frames:
                return None

        def pinch_point(h: Hand):
            (ax, ay), (bx, by) = h.point(THUMB_TIP), h.point(INDEX_TIP)
            return ((ax + bx) / 2) * h.aspect, (ay + by) / 2

        (x0, y0), (x1, y1) = pinch_point(hands[0]), pinch_point(hands[1])
        d = math.hypot(x1 - x0, y1 - y0)
        if not self.zooming:
            self.zooming, self._zoom_base = True, max(d, 1e-6)
            return self._release() + [self._event("zoom")]
        ratio = d / self._zoom_base
        if ratio >= self.s.zoom_step:
            self._zoom_base = d
            return [Shortcut("zoom_in"), self._event("zoom in")]
        if ratio <= 1 / self.s.zoom_step:
            self._zoom_base = max(d, 1e-6)
            return [Shortcut("zoom_out"), self._event("zoom out")]
        return []

    # --------------------------------------------------------------- fist/pause

    def _update_fist(self, pose: Pose, t: float) -> list[Action]:
        if pose is not Pose.FIST:
            self._fist_t0, self._fist_armed, self.fist_progress = None, True, 0.0
            return []
        if self._fist_t0 is None:
            self._fist_t0 = t
        self.fist_progress = min((t - self._fist_t0) / self.s.fist_toggle_s, 1.0)
        if self.fist_progress >= 1.0 and self._fist_armed:
            self._fist_armed = False
            return self.set_enabled(not self.enabled)
        return []

    # ------------------------------------------------------------- calibration

    def _calibrate(self, hand: Hand, t: float) -> list[Action]:
        self.calibrator.feed(self.anchor, t)
        if not self.calibrator.done:
            return []
        corners, self.calibrator = self.calibrator.corners(), None
        try:
            self.mapper.set_corners(corners)
        except ValueError:
            return [self._event("screen setup failed - press c to retry")]
        self.mapper.save(self.s.calibration_path)
        self._fx.reset()
        self._fy.reset()
        self._need_release = True
        return [self._event("screen setup saved")]

    def _calibrate_gestures(self, hands: list[Hand], t: float) -> list[Action]:
        cal = self.gesture_calibrator
        hand = self.hand = self._primary(hands) if hands else None
        self.anchor = self._anchor_point(hand) if hand else None
        step = cal.step
        cal.feed(hand, t)
        if not cal.done:
            return [self._event(f"step {step + 1} captured")] if cal.step != step else []
        self.gesture_calibrator = None
        try:
            profile = compute_profile(cal.samples)
        except ValueError as e:
            self.then_calibrate_screen = False
            return [self._event(f"gesture setup failed: {e} (press g)")]
        apply_profile(self.s, profile)
        save_profile(self.s.profile_path, profile)
        self._need_release = True
        out = [self._event("gesture setup saved")]
        if self.then_calibrate_screen:
            self.then_calibrate_screen = False
            out += self.start_calibration()
        return out
