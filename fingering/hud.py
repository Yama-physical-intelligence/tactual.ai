"""Preview overlay: hand skeleton, active region, mode, latency."""

import cv2
import numpy as np

from .gestures import GestureEngine
from .hand import CONNECTIONS, Hand

FONT = cv2.FONT_HERSHEY_SIMPLEX
GREEN, ORANGE, RED, CYAN, WHITE, GREY = (90, 220, 90), (40, 140, 255), (70, 70, 230), (230, 200, 60), (255, 255, 255), (150, 150, 150)
HELP = "q quit | p pause | g gesture setup | c screen setup | esc cancel"


def _text(img, s, org, scale=0.55, color=WHITE, thick=1):
    cv2.putText(img, s, org, FONT, scale, (0, 0, 0), thick + 3, cv2.LINE_AA)
    cv2.putText(img, s, org, FONT, scale, color, thick, cv2.LINE_AA)


def draw(frame: np.ndarray, engine: GestureEngine, hands: list[Hand], fps: float, infer_ms: float) -> None:
    h, w = frame.shape[:2]
    px = lambda p: (int(p[0] * w), int(p[1] * h))  # noqa: E731

    # Active region (calibrated area that maps to the whole screen)
    if not engine.calibrator:
        cv2.polylines(frame, [np.int32([px(c) for c in engine.mapper.corners])], True, CYAN, 1, cv2.LINE_AA)

    for hand in hands:
        pts = [px(p) for p in hand.landmarks]
        for a, b in CONNECTIONS:
            cv2.line(frame, pts[a], pts[b], GREY, 2, cv2.LINE_AA)
        for p in pts:
            cv2.circle(frame, p, 3, WHITE, -1, cv2.LINE_AA)
    if engine.anchor:
        color = ORANGE if engine.mode.startswith(("pinch", "drag")) else GREEN
        cv2.circle(frame, px(engine.anchor), 9, color, 2, cv2.LINE_AA)

    state_color = RED if not engine.enabled else GREEN
    _text(frame, "ACTIVE" if engine.enabled else "PAUSED", (12, 28), 0.8, state_color, 2)
    _text(frame, f"mode: {engine.mode}", (12, 54))
    _text(frame, f"{fps:4.0f} fps   model {infer_ms:4.1f} ms", (12, 76), 0.5, GREY)
    if engine.last_event:
        _text(frame, engine.last_event, (12, 100), 0.6, ORANGE)

    if engine.fist_progress > 0 and engine.anchor:
        c = px(engine.anchor)
        cv2.ellipse(frame, c, (30, 30), -90, 0, 360 * engine.fist_progress, RED, 4, cv2.LINE_AA)

    gc = engine.gesture_calibrator
    if gc:
        _text(frame, gc.prompt, (12, h // 2), 0.6, ORANGE, 2)
        cv2.rectangle(frame, (12, h // 2 + 14), (12 + int((w - 24) * gc.progress), h // 2 + 20), ORANGE, -1)
    if engine.calibrator:
        cal = engine.calibrator
        if len(cal.samples) >= 5:
            box = np.int32([px(c) for c in cal.corners()])
            cv2.polylines(frame, [box], True, ORANGE, 2, cv2.LINE_AA)
        _text(frame, "Sweep your hand over the area to use", (12, h // 2), 0.6, ORANGE, 2)
        cv2.rectangle(frame, (12, h // 2 + 14), (12 + int((w - 24) * cal.progress), h // 2 + 20), ORANGE, -1)

    _text(frame, HELP, (12, h - 12), 0.45, GREY)
