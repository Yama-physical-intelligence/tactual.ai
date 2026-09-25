"""Camera-space -> screen-space mapping via a 4-corner perspective calibration."""

import json
import logging
from pathlib import Path

import cv2
import numpy as np

log = logging.getLogger(__name__)

# Comfortable default region (normalized, mirrored frame): TL, TR, BR, BL.
DEFAULT_CORNERS = ((0.25, 0.20), (0.75, 0.20), (0.75, 0.65), (0.25, 0.65))
CORNER_NAMES = ("TOP-LEFT", "TOP-RIGHT", "BOTTOM-RIGHT", "BOTTOM-LEFT")


class ScreenMapper:
    def __init__(self, screen_w: int, screen_h: int, corners=DEFAULT_CORNERS):
        self.screen_w, self.screen_h = screen_w, screen_h
        self.set_corners(corners)

    def set_corners(self, corners) -> None:
        src = np.float32(corners)
        if src.shape != (4, 2) or abs(cv2.contourArea(src)) < 0.01 or not cv2.isContourConvex(src):
            raise ValueError("calibration corners must form a convex region covering >1% of the frame")
        w, h = self.screen_w - 1, self.screen_h - 1
        dst = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
        self._h = cv2.getPerspectiveTransform(src, dst)
        self.corners = tuple((float(x), float(y)) for x, y in corners)

    def map(self, x: float, y: float, clamp: bool = True) -> tuple[float, float]:
        v = self._h @ np.array([x, y, 1.0])
        sx, sy = v[0] / v[2], v[1] / v[2]
        if not clamp:
            return float(sx), float(sy)
        return min(max(sx, 0.0), self.screen_w - 1), min(max(sy, 0.0), self.screen_h - 1)

    def save(self, path: Path) -> None:
        path.write_text(json.dumps({"corners": self.corners}, indent=2))

    @classmethod
    def load(cls, path: Path, screen_w: int, screen_h: int) -> "ScreenMapper":
        if path.exists():
            try:
                return cls(screen_w, screen_h, json.loads(path.read_text())["corners"])
            except (ValueError, KeyError, TypeError) as e:
                log.warning("Ignoring invalid calibration %s: %s", path, e)
        return cls(screen_w, screen_h)


class Calibrator:
    """Collects the 4 corners: aim at each screen corner and pinch; the pinch point is captured."""

    def __init__(self):
        self.points: list[tuple[float, float]] = []

    @property
    def done(self) -> bool:
        return len(self.points) == 4

    @property
    def prompt(self) -> str:
        return f"Point at {CORNER_NAMES[len(self.points)]} corner and pinch ({len(self.points) + 1}/4)"

    def capture(self, anchor: tuple[float, float]) -> None:
        self.points.append(anchor)
