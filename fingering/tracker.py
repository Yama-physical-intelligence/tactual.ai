"""MediaPipe Hand Landmarker wrapper (VIDEO mode: palm detection once, then cheap landmark tracking)."""

import logging
import urllib.request
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import BaseOptions, vision

from .hand import Hand

log = logging.getLogger(__name__)

MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/"
    "hand_landmarker.task"
)


def ensure_model(path: Path) -> Path:
    if not path.exists():
        log.info("Downloading hand model to %s", path)
        path.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(MODEL_URL, path)
    return path


class HandTracker:
    def __init__(self, model_path: Path, max_hands: int = 2):
        options = vision.HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(ensure_model(model_path))),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=max_hands,
            min_hand_detection_confidence=0.6,
            min_hand_presence_confidence=0.6,
            min_tracking_confidence=0.5,
        )
        self._landmarker = vision.HandLandmarker.create_from_options(options)
        self._last_ts = -1

    def process(self, frame_bgr: np.ndarray, t: float) -> list[Hand]:
        """frame_bgr must already be mirrored (selfie view) so handedness and motion feel natural."""
        h, w = frame_bgr.shape[:2]
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB))
        ts = max(int(t * 1000), self._last_ts + 1)  # timestamps must strictly increase
        self._last_ts = ts
        result = self._landmarker.detect_for_video(image, ts)
        return [
            Hand(np.array([(p.x, p.y) for p in lms], dtype=np.float64), hd[0].category_name, w / h)
            for lms, hd in zip(result.hand_landmarks, result.handedness)
        ]

    def close(self) -> None:
        self._landmarker.close()
