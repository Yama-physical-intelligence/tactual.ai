"""Main loop: camera -> tracker -> gesture engine -> OS events, with a preview window."""

import argparse
import logging
import sys
import time

import cv2

from .config import Settings
from .controller import MacController, accessibility_trusted
from .gestures import GestureEngine
from .hud import draw
from .mapping import ScreenMapper
from .profile import apply_profile, load_profile
from .tracker import HandTracker

log = logging.getLogger("fingering")
WINDOW = "Fingering"


def parse_args(argv):
    p = argparse.ArgumentParser(description="Control your Mac with hand gestures.")
    p.add_argument("--camera", type=int, default=0, help="camera index (default 0)")
    p.add_argument("--dry-run", action="store_true", help="recognize gestures but don't move the mouse")
    p.add_argument("--calibrate", action="store_true", help="start with screen setup (sweep your hand over the area to use)")
    p.add_argument("--setup", action="store_true", help="run gesture + screen calibration (auto on first run)")
    p.add_argument("--hand", choices=["Right", "Left"], default="Right", help="primary control hand")
    p.add_argument("--no-overlay", action="store_true", help="hide the on-screen hand imprint")
    p.add_argument("--no-preview", action="store_true", help="hide the camera preview window")
    p.add_argument("--anchor", choices=["pinch", "knuckle", "tip"], default="pinch",
                   help="cursor follows the thumb-index pinch point (default), index knuckle, or index tip")
    p.add_argument("--two-hands", action="store_true", help="track 2 hands (enables zoom, costs speed)")
    return p.parse_args(argv)


def open_camera(s: Settings) -> cv2.VideoCapture:
    cap = cv2.VideoCapture(s.camera_index)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, s.frame_width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, s.frame_height)
    cap.set(cv2.CAP_PROP_FPS, s.camera_fps)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return cap


def overlay_points(engine: GestureEngine, scale: float = 0.7):
    """Primary hand in screen pixels, shrunk around the anchor and pinned to the cursor,
    so the ghost's thumb-index contact point is exactly where a click lands."""
    hand = engine.hand
    if hand is None or engine.anchor is None:
        return None
    ax, ay = engine.mapper.map(*engine.anchor, clamp=False)
    cx, cy = engine.cursor if engine.cursor and not engine.prompt else (ax, ay)
    pts = [engine.mapper.map(x, y, clamp=False) for x, y in hand.landmarks]
    return [(cx + (x - ax) * scale, cy + (y - ay) * scale) for x, y in pts]


def overlay_state(engine: GestureEngine) -> str:
    if not engine.enabled:
        return "paused"
    return "pinch" if engine.mode.startswith(("pinch", "drag", "zoom", "scroll")) else "active"


def main(argv=None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    s = Settings(camera_index=args.camera, primary_hand=args.hand, cursor_anchor=args.anchor,
                 max_hands=2 if args.two_hands else 1)

    if not args.dry_run and not accessibility_trusted(prompt=True):
        log.warning("Accessibility permission missing: the cursor won't move. Enable your terminal in "
                    "System Settings > Privacy & Security > Accessibility, then restart.")

    profile = load_profile(s.profile_path)
    if profile:
        apply_profile(s, profile)
        log.info("Loaded gesture profile %s", s.profile_path.name)
    controller = MacController(dry_run=args.dry_run)
    mapper = ScreenMapper.load(s.calibration_path, *controller.screen_size)
    engine = GestureEngine(s, mapper)
    tracker = HandTracker(s.model_path, s.max_hands)
    cap = open_camera(s)
    if not cap.isOpened():
        log.error("Cannot open camera %d. Allow camera access for your terminal in "
                  "System Settings > Privacy & Security > Camera.", s.camera_index)
        return 1

    overlay = None
    if not args.no_overlay:
        from .overlay import HandOverlay
        overlay = HandOverlay()
    if not args.no_preview:
        cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(WINDOW, 400, 300)
    if args.setup or profile is None:
        engine.start_gesture_calibration(then_screen=True)
    elif args.calibrate:
        engine.start_calibration()
    log.info("Screen %dx%d | %s", *controller.screen_size, "DRY RUN" if args.dry_run else "LIVE")

    fps, last = 0.0, time.perf_counter()
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                log.error("Camera read failed")
                break
            frame = cv2.flip(frame, 1)
            t = time.perf_counter()
            hands = tracker.process(frame, t)
            infer_ms = (time.perf_counter() - t) * 1000
            for action in engine.update(hands, t):
                controller.execute(action)

            now = time.perf_counter()
            fps = 0.9 * fps + 0.1 / max(now - last, 1e-6)
            last = now
            if overlay:
                overlay.update(overlay_points(engine), overlay_state(engine), engine.prompt,
                               engine.setup_progress, engine.anchor and engine.cursor)
            if args.no_preview:
                continue
            draw(frame, engine, hands, fps, infer_ms)
            cv2.imshow(WINDOW, frame)

            key = cv2.waitKey(1) & 0xFF
            actions = []
            if key == ord("q"):
                break
            if key == ord("p"):
                actions = engine.set_enabled(not engine.enabled)
            elif key == ord("c"):
                actions = engine.start_calibration()
            elif key == ord("g"):
                actions = engine.start_gesture_calibration()
            elif key == 27 and engine.prompt:
                actions = engine.cancel_calibration()
            for action in actions:
                controller.execute(action)
    except KeyboardInterrupt:
        pass
    finally:
        for action in engine.reset():
            controller.execute(action)
        cap.release()
        tracker.close()
        if overlay:
            overlay.close()
        cv2.destroyAllWindows()
    return 0
