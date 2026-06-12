"""Holographic Virtual Keyboard (Air-Typing Engine) for Arrow.

Features:
- Auto-installs dependencies: opencv-python, mediapipe, pyautogui
- Displays a transparent QWERTY overlay on the lower half of the camera feed
- Tracks index finger (landmark 8) with EMA smoothing and hover-to-select timer
- Shows circular loading ring while hovering; presses key after 0.5s dwell
- Flashes key and emits short beep on activation
- Runs as a thread-safe background daemon

Usage:
- import modules.virtual_keyboard as vk
- vk.initialize(); vk.start_virtual_keyboard()
- vk.stop_virtual_keyboard(); vk.cleanup_virtual_keyboard()
"""
from __future__ import annotations

import subprocess
import sys
import time
import threading
import math
import shutil
import os
from typing import Optional, Tuple, Dict

# Detect headless display environments before importing GUI dependencies.
HEADLESS = os.environ.get("DISPLAY") is None and sys.platform != "win32"

# Auto-install missing dependencies
_REQUIRED = {
    "cv2": "opencv-python",
    "mediapipe": "mediapipe",
    "pyautogui": "pyautogui",
}
_INSTALL_FAILED = False
for mod, pkg in _REQUIRED.items():
    if mod == "pyautogui" and HEADLESS:
        continue
    try:
        __import__(mod)
    except ImportError:
        print(f"[virtual_keyboard] Attempting to install {pkg}...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])
        except subprocess.CalledProcessError:
            print(f"[virtual_keyboard] Could not install {pkg} automatically. Continuing with degraded mode.")
            _INSTALL_FAILED = True

try:
    import cv2
    import mediapipe as mp
    if HEADLESS:
        pyautogui = None
        _DEPS_OK = False
    else:
        import pyautogui
        _DEPS_OK = True
except Exception:
    cv2 = None
    mp = None
    pyautogui = None
    _DEPS_OK = False

# Import camera URL from config
from config import CAMERA_RTSP_URL

if pyautogui is not None:
    try:
        pyautogui.FAILSAFE = False
    except Exception:
        pass

# Parameters
FRAME_SKIP = 2
HOVER_SECONDS = 0.5
EMA_ALPHA = 0.45
LOAD_RING_RADIUS = 30
LOAD_RING_THICKNESS = 4
KEY_FLASH_TIME = 0.12
VIRTUAL_BOX_RATIO = 0.7
FONT = cv2.FONT_HERSHEY_SIMPLEX if cv2 is not None else 0

# Sound/beep utility (cross-platform fallback)
def _beep() -> None:
    try:
        if os.name == "nt":
            import winsound

            winsound.Beep(1000, 60)
        else:
            # Try to use 'paplay' or 'play' if available
            if shutil.which("paplay"):
                # generate short sine with sox? paplay requires file; fallback to bell
                print('\a', end='')
            elif shutil.which("play"):
                # 'play' from sox can synthesize a short tone
                subprocess.run(["play", "-nq", "synth", "0.06", "sin", "1000"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                # Terminal bell as last resort
                print('\a', end='')
    except Exception:
        pass


class VirtualKeyboard:
    def __init__(self):
        self.stop_event = threading.Event()
        self.thread: Optional[threading.Thread] = None
        self.cap: Optional[cv2.VideoCapture] = None
        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(static_image_mode=False, max_num_hands=1, min_detection_confidence=0.6, min_tracking_confidence=0.5)
        self.lock = threading.Lock()
        self.last_pos: Optional[Tuple[float, float]] = None
        self.frame_count = 0
        self.hover_key: Optional[str] = None
        self.hover_start: Optional[float] = None
        self.flash_until: Dict[str, float] = {}
        self.key_boxes: Dict[str, Tuple[int, int, int, int]] = {}

    def initialize_camera(self) -> bool:
        if not _DEPS_OK or cv2 is None:
            self._log("Missing dependencies (opencv/mediapipe/pyautogui). Virtual keyboard disabled.")
            return False
        try:
            self.cap = cv2.VideoCapture(CAMERA_RTSP_URL)
            return self.cap is not None and self.cap.isOpened()
        except Exception:
            self.cap = None
            return False

    def close_camera(self) -> None:
        if self.cap is not None:
            try:
                self.cap.release()
            except Exception:
                pass
        self.cap = None

    def _log(self, msg: str) -> None:
        print(f"[virtual_keyboard] {msg}")

    def _compute_key_layout(self, frame_w: int, frame_h: int) -> None:
        # Lower half keyboard area
        top = int(frame_h * 0.55)
        bottom = frame_h - 10
        left = 10
        right = frame_w - 10
        box_w = right - left
        box_h = bottom - top

        # Rows for QWERTY layout
        rows = [
            list("qwertyuiop"),
            list("asdfghjkl"),
            list("zxcvbnm"),
        ]

        # Compute widths per key for first three rows
        y = top
        row_h = int(box_h * 0.22)
        self.key_boxes = {}
        for r_index, row in enumerate(rows):
            cols = len(row)
            # apply small offset for staggered rows
            stagger = int((box_w / 20) * r_index)
            key_w = int((box_w - 40) / cols)
            x = left + 20 + stagger
            for k in row:
                x1 = x
                y1 = y
                x2 = x + key_w - 6
                y2 = y + row_h - 6
                self.key_boxes[k] = (x1, y1, x2, y2)
                x = x + key_w
            y += row_h + 6

        # Space bar
        sb_top = y
        sb_h = int(row_h * 1.1)
        sb_left = left + int(box_w * 0.1)
        sb_right = right - int(box_w * 0.1)
        self.key_boxes["space"] = (sb_left, sb_top, sb_right, sb_top + sb_h)

    def _point_in_box(self, px: int, py: int, box: Tuple[int, int, int, int]) -> bool:
        x1, y1, x2, y2 = box
        return x1 <= px <= x2 and y1 <= py <= y2

    def _draw_overlay(self, frame, frame_w: int, frame_h: int, index_px: Optional[Tuple[int, int]] = None, load_progress: float = 0.0):
        # translucent overlay
        overlay = frame.copy()
        for key, box in self.key_boxes.items():
            x1, y1, x2, y2 = box
            # flash handling
            now = time.monotonic()
            if key in self.flash_until and now < self.flash_until[key]:
                color = (0, 200, 0)
            else:
                color = (255, 255, 255)
            cv2.rectangle(overlay, (x1, y1), (x2, y2), color, -1)
            # key label
            label = "Space" if key == "space" else key.upper()
            font_scale = 0.6 if key != "space" else 1.0
            text_size = cv2.getTextSize(label, FONT, font_scale, 2)[0]
            tx = x1 + (x2 - x1 - text_size[0]) // 2
            ty = y1 + (y2 - y1 + text_size[1]) // 2
            cv2.putText(overlay, label, (tx, ty), FONT, font_scale, (0, 0, 0), 2, cv2.LINE_AA)
        # blend overlay
        cv2.addWeighted(overlay, 0.45, frame, 0.55, 0, frame)

        # draw loading ring around index
        if index_px is not None:
            ix, iy = index_px
            # full circle background
            cv2.circle(frame, (ix, iy), LOAD_RING_RADIUS, (200, 200, 200), LOAD_RING_THICKNESS)
            # progress arc
            if load_progress > 0.0:
                start_angle = -90
                end_angle = int(-90 + 360 * min(max(load_progress, 0.0), 1.0))
                cv2.ellipse(frame, (ix, iy), (LOAD_RING_RADIUS, LOAD_RING_RADIUS), 0, start_angle, end_angle, (0, 200, 0), LOAD_RING_THICKNESS)
        return frame

    def _handle_activation(self, key: str) -> None:
        # trigger key press and visual/audio feedback
        try:
            if key == "space":
                pyautogui.press("space")
            else:
                pyautogui.press(key)
            _beep()
            self.flash_until[key] = time.monotonic() + KEY_FLASH_TIME
            self._log(f"Key activated: {key}")
        except Exception as exc:
            self._log(f"Failed to press key {key}: {exc}")

    def _process_frame(self, frame) -> None:
        frame_h, frame_w = frame.shape[:2]
        if not self.key_boxes:
            self._compute_key_layout(frame_w, frame_h)

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.hands.process(rgb)
        index_px = None
        progress = 0.0

        if results.multi_hand_landmarks:
            lm = results.multi_hand_landmarks[0].landmark
            idx = lm[8]
            ix = int(idx.x * frame_w)
            iy = int(idx.y * frame_h)
            # EMA smoothing on normalized coords
            normalized = (idx.x, idx.y)
            if self.last_pos is None:
                self.last_pos = normalized
            else:
                self.last_pos = (EMA_ALPHA * normalized[0] + (1 - EMA_ALPHA) * self.last_pos[0], EMA_ALPHA * normalized[1] + (1 - EMA_ALPHA) * self.last_pos[1])
            ix_s = int(self.last_pos[0] * frame_w)
            iy_s = int(self.last_pos[1] * frame_h)
            index_px = (ix_s, iy_s)

            # Check which key we hover
            hovered = None
            for key, box in self.key_boxes.items():
                if self._point_in_box(ix_s, iy_s, box):
                    hovered = key
                    break

            now = time.monotonic()
            if hovered is not None:
                if self.hover_key != hovered:
                    self.hover_key = hovered
                    self.hover_start = now
                else:
                    elapsed = now - (self.hover_start or now)
                    progress = min(1.0, elapsed / HOVER_SECONDS)
                    if elapsed >= HOVER_SECONDS:
                        # Activate
                        self._handle_activation(hovered)
                        # reset hover
                        self.hover_key = None
                        self.hover_start = None
            else:
                self.hover_key = None
                self.hover_start = None
        else:
            self.last_pos = None
            self.hover_key = None
            self.hover_start = None

        # Draw overlay and ring
        out = self._draw_overlay(frame, frame_w, frame_h, index_px=index_px, load_progress=progress)
        cv2.imshow("VirtualKeyboard", out)
        cv2.waitKey(1)

    def _run(self) -> None:
        self._log("Virtual Keyboard thread started.")
        if not self.initialize_camera():
            self._log("Could not open camera stream.")
            return
        frame_idx = 0
        try:
            while not self.stop_event.is_set():
                ret, frame = self.cap.read()
                if not ret or frame is None:
                    time.sleep(0.05)
                    continue
                frame_idx += 1
                if frame_idx % FRAME_SKIP != 0:
                    continue
                self._process_frame(frame)
        finally:
            self.close_camera()
            cv2.destroyWindow("VirtualKeyboard")
            self._log("Virtual Keyboard thread stopped.")

    def start(self) -> None:
        with self.lock:
            if self.thread and self.thread.is_alive():
                return
            self.stop_event.clear()
            self.thread = threading.Thread(target=self._run, daemon=True, name="VirtualKeyboard")
            self.thread.start()
        self._log("Virtual Keyboard started.")

    def stop(self) -> None:
        with self.lock:
            self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=2)
        self._log("Virtual Keyboard stopped.")

    def cleanup(self) -> None:
        try:
            self.stop()
        except Exception:
            pass
        try:
            self.hands.close()
        except Exception:
            pass


# Module-level instance and API
_vk: Optional[VirtualKeyboard] = None


def initialize() -> None:
    global _vk
    if _vk is None:
        _vk = VirtualKeyboard()
    _vk._log("Initialized.")


def start_virtual_keyboard() -> None:
    global _vk
    if _vk is None:
        initialize()
    _vk.start()


def stop_virtual_keyboard() -> None:
    global _vk
    if _vk is not None:
        _vk.stop()


def is_virtual_keyboard_active() -> bool:
    return _vk is not None and _vk.thread is not None and _vk.thread.is_alive()


def cleanup_virtual_keyboard() -> None:
    global _vk
    if _vk is not None:
        _vk.cleanup()
        _vk = None


def orchestrator_event_hook(event_type: str, payload: Dict[str, object]) -> Dict[str, object]:
    if event_type == "keyboard.virtual.start":
        start_virtual_keyboard()
        return {"status": "started", "event_type": event_type}
    if event_type == "keyboard.virtual.stop":
        stop_virtual_keyboard()
        return {"status": "stopped", "event_type": event_type}
    return {"status": "ignored", "event_type": event_type}


ORCHESTRATOR_PLUGIN = {
    "name": "virtual_keyboard",
    "handler": "orchestrator_event_hook",
    "events": ("keyboard.virtual.start", "keyboard.virtual.stop"),
    "priority": 11,
}


__all__ = [
    "initialize",
    "start_virtual_keyboard",
    "stop_virtual_keyboard",
    "is_virtual_keyboard_active",
    "cleanup_virtual_keyboard",
    "orchestrator_event_hook",
    "ORCHESTRATOR_PLUGIN",
]
