"""MediaPipe Hand Landmarker wrapper.

VIDEO mode runs the (expensive) palm detector only until it has found `num_hands` hands, then just
the cheap landmark model. Tracking 2 hands while only 1 is visible therefore re-runs the detector
every frame (~30 ms instead of ~12 ms). So in "auto" mode we track one hand, and a background probe
checks a few times per second whether a second hand has appeared; only then do we switch to a
two-hand tracker (for zoom), and back once the second hand leaves.

A two-hand tracker that has been following a single hand does not reliably pick up a second hand
that appears later, so each switch uses a freshly created tracker (prepared in the background).
"""

import logging
import time
import urllib.request
from concurrent.futures import Future, ThreadPoolExecutor
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
PROBE_INTERVAL_S = 0.3
TWO_HAND_LINGER_S = 1.0


def ensure_model(path: Path) -> Path:
    if not path.exists():
        log.info("Downloading hand model to %s", path)
        path.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(MODEL_URL, path)
    return path


def _landmarker(model_path: Path, num_hands: int, mode) -> vision.HandLandmarker:
    return vision.HandLandmarker.create_from_options(vision.HandLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(model_path)),
        running_mode=mode,
        num_hands=num_hands,
        min_hand_detection_confidence=0.6,
        min_hand_presence_confidence=0.6,
        min_tracking_confidence=0.5,
    ))


class HandTracker:
    def __init__(self, model_path: Path, hands_mode: str = "auto"):
        """hands_mode: "one" (fastest, no zoom) or "auto" (1 hand, switching to 2 on demand)."""
        if hands_mode not in ("one", "auto"):
            raise ValueError(f"hands_mode must be 'one' or 'auto', not {hands_mode!r}")
        self._model_path = model_path = ensure_model(model_path)
        self.mode = hands_mode
        self._one = _landmarker(model_path, 1, vision.RunningMode.VIDEO)
        self._two: vision.HandLandmarker | None = None
        self._probe = self._pool = None
        if hands_mode == "auto":
            self._probe = _landmarker(model_path, 2, vision.RunningMode.IMAGE)
            self._pool = ThreadPoolExecutor(1, thread_name_prefix="hand-probe")
            self._next_two: Future = self._pool.submit(self._new_two)
        self._probe_future: Future | None = None
        self._probe_t = 0.0
        self.two_active = False
        self._two_seen_t = 0.0
        self._last_ts = -1

    def process(self, frame_bgr: np.ndarray, t: float) -> list[Hand]:
        """frame_bgr must already be mirrored (selfie view) so handedness and motion feel natural."""
        h, w = frame_bgr.shape[:2]
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB))
        ts = max(int(t * 1000), self._last_ts + 1)  # timestamps must strictly increase
        self._last_ts = ts
        if self.mode == "auto":
            self._update_auto(image, t)
        landmarker = self._two if self.two_active else self._one
        result = landmarker.detect_for_video(image, ts)
        hands = [
            Hand(np.array([(p.x, p.y) for p in lms], dtype=np.float64), hd[0].category_name, w / h)
            for lms, hd in zip(result.hand_landmarks, result.handedness)
        ]
        if self.two_active and len(hands) >= 2:
            self._two_seen_t = t
        return hands

    def _new_two(self) -> vision.HandLandmarker:
        return _landmarker(self._model_path, 2, vision.RunningMode.VIDEO)

    def _update_auto(self, image: mp.Image, t: float) -> None:
        if self.two_active:
            if t - self._two_seen_t > TWO_HAND_LINGER_S:
                self.two_active = False
                old, self._two = self._two, None
                self._pool.submit(old.close)
                self._next_two = self._pool.submit(self._new_two)  # fresh one for next time
                log.debug("two-hand tracking off")
            return
        f = self._probe_future
        if f is not None and f.done():
            self._probe_future = None
            if f.exception() is None and len(f.result().hand_landmarks) >= 2:
                self._two = self._next_two.result()
                self.two_active, self._two_seen_t = True, t
                log.debug("two-hand tracking on")
                return
        if self._probe_future is None and t - self._probe_t >= PROBE_INTERVAL_S:
            self._probe_t = t
            self._probe_future = self._pool.submit(self._probe.detect, image)

    def close(self) -> None:
        if self._pool:
            self._pool.shutdown(wait=True)
        if self._probe:
            nxt = self._next_two.result()
            if nxt is not self._two:
                nxt.close()
        for lm in (self._one, self._two, self._probe):
            if lm:
                lm.close()
