from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Settings:
    # Camera / tracker
    camera_index: int = 0
    frame_width: int = 640
    frame_height: int = 480
    camera_fps: int = 60
    max_hands: int = 1  # 2 enables two-hand zoom but re-runs the palm detector while one hand is visible
    primary_hand: str = "Right"
    model_path: Path = field(default_factory=lambda: PROJECT_ROOT / "models" / "hand_landmarker.task")
    calibration_path: Path = field(default_factory=lambda: PROJECT_ROOT / "calibration.json")
    profile_path: Path = field(default_factory=lambda: PROJECT_ROOT / "gesture_profile.json")

    # Cursor follows: "pinch" (where thumb and index tips meet), "knuckle" (index MCP) or "tip" (index tip).
    cursor_anchor: str = "pinch"
    filter_min_cutoff: float = 1.2
    filter_beta: float = 0.008
    move_deadzone_px: float = 1.5

    # Pinch thresholds, as a ratio of hand size (wrist -> middle knuckle). Enter < exit = hysteresis.
    pinch_enter: float = 0.30
    pinch_exit: float = 0.45
    pinch_enter_middle: float = 0.30
    pinch_exit_middle: float = 0.45
    pinch_min_reach: float = 1.2  # fingertip-to-wrist distance, in hand sizes
    # A finger counts as extended when wrist->tip / wrist->pip exceeds this (index, middle, ring, pinky).
    extend_thresholds: tuple = (1.15, 1.15, 1.15, 1.15)
    tap_max_s: float = 0.35  # pinch shorter than this (without moving) is a tap = click
    pinch_move_px: float = 20.0  # pinch-and-move beyond this = scroll (or drag after a tap)
    # Click rewind: a click lands where the aim point was just before the fingers started closing
    # (closing a pinch drags the aim point a little). Looks back at most this far.
    click_rewind_s: float = 0.25
    double_click_s: float = 0.45
    pose_stable_frames: int = 3

    # Pinch-and-move scroll: content follows the hand like grabbing a page.
    scroll_gain: float = 1.0  # scroll pixels per pixel of (mapped) hand movement
    natural_scroll: bool = True
    # Dial scroll: while pinched, twist the hand like a knob (clockwise = down).
    dial_start_deg: float = 14.0
    dial_gain: float = 14.0  # scroll pixels per degree
    # Momentum after releasing a fast scroll, like a trackpad fling.
    momentum_min_speed: float = 600.0  # px/s needed to fling
    momentum_decay_s: float = 0.35

    # Swipe (open palm)
    swipe_window_s: float = 0.35
    swipe_min_dist: float = 0.12  # fraction of frame
    swipe_axis_ratio: float = 1.3  # main-axis travel must dominate the other axis by this much
    swipe_cooldown_s: float = 0.9
    natural_swipe: bool = True

    # Two-hand zoom
    zoom_step: float = 1.15
    zoom_stable_frames: int = 4

    # Pause toggle (fist hold) and hand-lost handling
    fist_toggle_s: float = 1.0
    hand_lost_s: float = 0.25
