"""Camera-space -> screen-space mapping via a 4-corner perspective calibration."""

import json
import logging
from pathlib import Path

import cv2
import numpy as np

log = logging.getLogger(__name__)

# Comfortable default region (normalized, mirrored frame): TL, TR, BR, BL.
DEFAULT_CORNERS = ((0.25, 0.20), (0.75, 0.20), (0.75, 0.65), (0.25, 0.65))


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
    """Screen calibration: move your hand around the area you want to use for a few seconds.
    That area (robust 5-95th percentile of the aim point) is mapped to the whole screen."""

    DURATION_S = 5.0
    MIN_W, MIN_H = 0.20, 0.15  # never map a tiny area: keeps the cursor from being twitchy

    def __init__(self):
        self.samples: list[tuple[float, float]] = []
        self._t0: float | None = None
        self.progress = 0.0

    @property
    def done(self) -> bool:
        return self.progress >= 1.0 and len(self.samples) >= 30

    @property
    def prompt(self) -> str:
        return "Screen setup: sweep your hand over the area you want to use (reach every edge)"

    def feed(self, anchor: tuple[float, float] | None, t: float) -> None:
        if anchor is None:
            return
        if self._t0 is None:
            self._t0 = t
        self.samples.append(anchor)
        self.progress = min((t - self._t0) / self.DURATION_S, 1.0)

    def corners(self):
        pts = np.array(self.samples)
        (x0, y0), (x1, y1) = np.percentile(pts, 5, axis=0), np.percentile(pts, 95, axis=0)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        hw, hh = max((x1 - x0) / 2, self.MIN_W / 2), max((y1 - y0) / 2, self.MIN_H / 2)
        x0, x1 = max(cx - hw, 0.0), min(cx + hw, 1.0)
        y0, y1 = max(cy - hh, 0.0), min(cy + hh, 1.0)
        return ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
