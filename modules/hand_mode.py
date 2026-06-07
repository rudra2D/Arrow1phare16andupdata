"""Hand Mode for Arrow: Gesture-based cursor control and automation.

This module provides:
- Auto-dependency installation for opencv-python, mediapipe, pyautogui
- RTSP camera feed with frame-skipping for low CPU overhead
- Jitter-free palm tracking with EMA smoothing
- Virtual Monitor Box mapping (70% central region) to full OS resolution
- Distance-based pinch-click detection
- Gesture-based auto-activation (open palm 3s) and auto-exit (closed fist 3s)
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from typing import Optional

# Auto-install missing dependencies
_REQUIRED_PACKAGES = {
    "cv2": "opencv-python",
    "mediapipe": "mediapipe",
    "pyautogui": "pyautogui",
}

_INSTALL_FAILED = False
for module_name, package_name in _REQUIRED_PACKAGES.items():
    try:
        __import__(module_name)
    except ImportError:
        print(f"[hand_mode] Attempting to install {package_name}...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", package_name])
        except subprocess.CalledProcessError:
            print(f"[hand_mode] Could not install {package_name} automatically. Continuing with degraded mode.")
            _INSTALL_FAILED = True

try:
    import cv2
    import mediapipe as mp
    import pyautogui
    _DEPS_OK = True
except Exception:
    cv2 = None
    mp = None
    pyautogui = None
    _DEPS_OK = False
from config import CAMERA_RTSP_URL

# Constants
FRAME_SKIP = 2
EMA_ALPHA = 0.4
PINCH_DISTANCE_THRESHOLD = 0.05
GESTURE_HOLD_DURATION = 3.0
PALM_CENTER_LANDMARKS = [0, 5, 17]
THUMB_TIP = 4
INDEX_TIP = 8
VIRTUAL_BOX_RATIO = 0.7


def _log(message: str) -> None:
    print(f"[hand_mode] {message}")


def _get_screen_size() -> tuple[int, int]:
    try:
        w = pyautogui.size().width
        h = pyautogui.size().height
        return w, h
    except Exception:
        return 1920, 1080


def _calculate_palm_center(landmarks, frame_h: int, frame_w: int) -> tuple[float, float] | None:
    """Calculate palm center as midpoint of landmarks 0, 5, 17."""
    try:
        points = []
        for idx in PALM_CENTER_LANDMARKS:
            lm = landmarks[idx]
            points.append((lm.x, lm.y))
        center_x = sum(p[0] for p in points) / len(points)
        center_y = sum(p[1] for p in points) / len(points)
        return center_x, center_y
    except Exception:
        return None


def _apply_ema(current: tuple[float, float], previous: Optional[tuple[float, float]]) -> tuple[float, float]:
    """Apply exponential moving average for smooth cursor movement."""
    if previous is None:
        return current
    x_smooth = EMA_ALPHA * current[0] + (1 - EMA_ALPHA) * previous[0]
    y_smooth = EMA_ALPHA * current[1] + (1 - EMA_ALPHA) * previous[1]
    return x_smooth, y_smooth


def _calculate_distance(p1: tuple[float, float], p2: tuple[float, float]) -> float:
    """Euclidean distance between two 2D points."""
    return ((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2) ** 0.5


def _map_to_screen(x: float, y: float, frame_w: int, frame_h: int) -> tuple[int, int]:
    """Map normalized coordinates from 70% central virtual box to full screen."""
    # Extract 70% central region boundaries
    box_w = frame_w * VIRTUAL_BOX_RATIO
    box_h = frame_h * VIRTUAL_BOX_RATIO
    box_left = (frame_w - box_w) / 2
    box_top = (frame_h - box_h) / 2

    # Clamp to box
    x_clamped = max(box_left, min(x * frame_w, box_left + box_w))
    y_clamped = max(box_top, min(y * frame_h, box_top + box_h))

    # Normalize to box range [0, 1]
    x_norm = (x_clamped - box_left) / box_w
    y_norm = (y_clamped - box_top) / box_h

    # Map to full screen
    screen_w, screen_h = _get_screen_size()
    screen_x = int(x_norm * screen_w)
    screen_y = int(y_norm * screen_h)

    return screen_x, screen_y


def _detect_open_palm(landmarks) -> bool:
    """Detect open flat palm gesture (all fingers extended)."""
    try:
        # Check if fingertips are above their bases (extended)
        finger_tips = [8, 12, 16, 20]  # Index, Middle, Ring, Pinky tips
        finger_bases = [5, 9, 13, 17]  # Corresponding bases
        extended_count = 0
        for tip_idx, base_idx in zip(finger_tips, finger_bases):
            if landmarks[tip_idx].y < landmarks[base_idx].y:
                extended_count += 1
        return extended_count >= 3
    except Exception:
        return False


def _detect_closed_fist(landmarks) -> bool:
    """Detect closed fist gesture (all fingertips close to palm center)."""
    try:
        palm_center = _calculate_palm_center(landmarks, 0, 0)
        if not palm_center:
            return False
        finger_tips = [8, 12, 16, 20]  # Index, Middle, Ring, Pinky tips
        close_count = 0
        for tip_idx in finger_tips:
            tip = landmarks[tip_idx]
            distance = _calculate_distance(palm_center, (tip.x, tip.y))
            if distance < 0.1:
                close_count += 1
        return close_count >= 3
    except Exception:
        return False


class HandMode:
    def __init__(self):
        self.active = False
        self.stop_event = threading.Event()
        self.thread: Optional[threading.Thread] = None
        self.cap: Optional[cv2.VideoCapture] = None
        if not _DEPS_OK or mp is None:
            self.mp_hands = None
            self.hands = None
        else:
            self.mp_hands = mp.solutions.hands
            self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=1,
            min_detection_confidence=0.7,
            min_tracking_confidence=0.5,
        )
        self.last_palm_pos: Optional[tuple[float, float]] = None
        self.palm_open_since: Optional[float] = None
        self.fist_closed_since: Optional[float] = None
        self.lock = threading.Lock()

    def _log(self, message: str) -> None:
        _log(message)

    def _open_camera(self) -> bool:
        if self.cap is not None and self.cap.isOpened():
            return True
        try:
            self.cap = cv2.VideoCapture(CAMERA_RTSP_URL)
            if not self.cap.isOpened():
                self.cap = None
                return False
            return True
        except Exception:
            self.cap = None
            return False

    def _close_camera(self) -> None:
        if self.cap is not None:
            try:
                self.cap.release()
            except Exception:
                pass
        self.cap = None

    def _read_frame(self) -> Optional[cv2.Mat]:
        if not self._open_camera():
            return None
        try:
            ret, frame = self.cap.read()
            if not ret or frame is None:
                return None
            return frame
        except Exception:
            return None

    def _process_hand_frame(self, frame: cv2.Mat) -> None:
        frame_h, frame_w, _ = frame.shape
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.hands.process(rgb_frame)

        with self.lock:
            if results.multi_hand_landmarks and len(results.multi_hand_landmarks) > 0:
                landmarks = results.multi_hand_landmarks[0].landmark
                palm_center = _calculate_palm_center(landmarks, frame_h, frame_w)
                if palm_center:
                    self.last_palm_pos = _apply_ema(palm_center, self.last_palm_pos)
                    screen_x, screen_y = _map_to_screen(
                        self.last_palm_pos[0],
                        self.last_palm_pos[1],
                        frame_w,
                        frame_h,
                    )
                    pyautogui.moveTo(screen_x, screen_y, duration=0)

                    # Pinch detection
                    thumb = landmarks[THUMB_TIP]
                    index = landmarks[INDEX_TIP]
                    pinch_dist = _calculate_distance((thumb.x, thumb.y), (index.x, index.y))
                    if pinch_dist < PINCH_DISTANCE_THRESHOLD:
                        pyautogui.click()
                        self._log("Pinch detected. Click executed.")

                    # Gesture detection
                    if _detect_open_palm(landmarks):
                        if self.palm_open_since is None:
                            self.palm_open_since = time.monotonic()
                        elif time.monotonic() - self.palm_open_since >= GESTURE_HOLD_DURATION:
                            if self.active:
                                self._log("Open palm gesture detected while active. Ignoring.")
                            self.palm_open_since = None
                    else:
                        self.palm_open_since = None

                    if _detect_closed_fist(landmarks):
                        if self.fist_closed_since is None:
                            self.fist_closed_since = time.monotonic()
                        elif time.monotonic() - self.fist_closed_since >= GESTURE_HOLD_DURATION:
                            if self.active:
                                self.stop()
                            self.fist_closed_since = None
                    else:
                        self.fist_closed_since = None
            else:
                self.last_palm_pos = None
                self.palm_open_since = None
                self.fist_closed_since = None

    def _run(self) -> None:
        self._log("Starting Hand Mode background thread.")
        frame_count = 0
        while not self.stop_event.is_set():
            frame = self._read_frame()
            if frame is not None:
                frame_count += 1
                if frame_count % FRAME_SKIP == 0:
                    self._process_hand_frame(frame)
            time.sleep(0.01)
        self._close_camera()
        self._log("Hand Mode background thread stopped.")

    def start(self) -> None:
        with self.lock:
            if self.active:
                return
            self.active = True
            self.stop_event.clear()
            if self.thread is None or not self.thread.is_alive():
                self.thread = threading.Thread(target=self._run, daemon=True, name="HandMode")
                self.thread.start()
        self._log("Hand Mode activated.")

    def stop(self) -> None:
        with self.lock:
            if not self.active:
                return
            self.active = False
            self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=2)
        self._close_camera()
        self._log("Hand Mode deactivated.")

    def cleanup(self) -> None:
        self.stop()
        if self.hands is not None:
            self.hands.close()


# Module-level instance
_hand_mode: Optional[HandMode] = None


def initialize() -> None:
    """Initialize Hand Mode module."""
    global _hand_mode
    if _hand_mode is None:
        _hand_mode = HandMode()
    _log("Hand Mode initialized.")


def start_hand_mode() -> None:
    """Activate Hand Mode gesture tracking."""
    global _hand_mode
    if _hand_mode is None:
        initialize()
    if _hand_mode is not None:
        _hand_mode.start()


def stop_hand_mode() -> None:
    """Deactivate Hand Mode gesture tracking."""
    global _hand_mode
    if _hand_mode is not None:
        _hand_mode.stop()


def is_hand_mode_active() -> bool:
    """Check if Hand Mode is currently active."""
    global _hand_mode
    return _hand_mode is not None and _hand_mode.active


def cleanup_hand_mode() -> None:
    """Cleanup and shutdown Hand Mode."""
    global _hand_mode
    if _hand_mode is not None:
        _hand_mode.cleanup()
        _hand_mode = None
    _log("Hand Mode cleaned up.")


__all__ = [
    "initialize",
    "start_hand_mode",
    "stop_hand_mode",
    "is_hand_mode_active",
    "cleanup_hand_mode",
]
