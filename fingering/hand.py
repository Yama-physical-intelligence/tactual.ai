"""Hand landmark geometry. All distances are aspect-corrected and normalized by hand size."""

from dataclasses import dataclass
from enum import Enum
from functools import cached_property

import numpy as np

WRIST = 0
THUMB_CMC, THUMB_MCP, THUMB_IP, THUMB_TIP = 1, 2, 3, 4
INDEX_MCP, INDEX_PIP, INDEX_DIP, INDEX_TIP = 5, 6, 7, 8
MIDDLE_MCP, MIDDLE_PIP, MIDDLE_DIP, MIDDLE_TIP = 9, 10, 11, 12
RING_MCP, RING_PIP, RING_DIP, RING_TIP = 13, 14, 15, 16
PINKY_MCP, PINKY_PIP, PINKY_DIP, PINKY_TIP = 17, 18, 19, 20

# (pip, tip) per non-thumb finger: index, middle, ring, pinky
_FINGERS = ((INDEX_PIP, INDEX_TIP), (MIDDLE_PIP, MIDDLE_TIP), (RING_PIP, RING_TIP), (PINKY_PIP, PINKY_TIP))

CONNECTIONS = (
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (5, 9), (9, 10), (10, 11), (11, 12),
    (9, 13), (13, 14), (14, 15), (15, 16),
    (13, 17), (17, 18), (18, 19), (19, 20), (0, 17),
)


class Pose(Enum):
    NONE = "none"
    POINTER = "pointer"
    PALM = "palm"
    FIST = "fist"


@dataclass
class Hand:
    landmarks: np.ndarray  # (21, 2) normalized image coords of the mirrored frame
    handedness: str = "Right"
    aspect: float = 4 / 3  # frame width / height

    @cached_property
    def _pts(self) -> np.ndarray:
        return self.landmarks[:, :2] * np.array([self.aspect, 1.0])

    def point(self, i: int) -> tuple[float, float]:
        return float(self.landmarks[i, 0]), float(self.landmarks[i, 1])

    def dist(self, i: int, j: int) -> float:
        return float(np.linalg.norm(self._pts[i] - self._pts[j]))

    @cached_property
    def scale(self) -> float:
        return max(self.dist(WRIST, MIDDLE_MCP), 1e-6)

    def pinch_ratio(self, tip: int) -> float:
        return self.dist(THUMB_TIP, tip) / self.scale

    @cached_property
    def fingers(self) -> tuple[bool, bool, bool, bool, bool]:
        """Extended state of (thumb, index, middle, ring, pinky)."""
        thumb = self.dist(THUMB_TIP, PINKY_MCP) > self.dist(THUMB_MCP, PINKY_MCP) * 1.2
        return (thumb, *self.extended((1.15,) * 4))

    @cached_property
    def extension_ratios(self) -> tuple[float, float, float, float]:
        """wrist->tip / wrist->pip for index, middle, ring, pinky (>1 means straightened)."""
        return tuple(self.dist(WRIST, tip) / max(self.dist(WRIST, pip), 1e-6) for pip, tip in _FINGERS)

    def extended(self, thresholds) -> tuple[bool, bool, bool, bool]:
        return tuple(r > t for r, t in zip(self.extension_ratios, thresholds))

    @cached_property
    def pinch_point(self) -> tuple[float, float]:
        """Where thumb and index tips meet: the natural 'touch' point for aiming."""
        (ax, ay), (bx, by) = self.point(THUMB_TIP), self.point(INDEX_TIP)
        return (ax + bx) / 2, (ay + by) / 2

    @cached_property
    def palm_center(self) -> tuple[float, float]:
        c = self.landmarks[[WRIST, INDEX_MCP, MIDDLE_MCP, RING_MCP, PINKY_MCP], :2].mean(axis=0)
        return float(c[0]), float(c[1])
