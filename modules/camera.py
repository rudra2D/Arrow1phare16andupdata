"""Wi-Fi camera access and desk monitoring for Arrow.

This module provides a dedicated MediaPipe-based face presence monitor that
runs on a daemon thread and triggers a system lock when no human face is seen
for a sustained interval. Snapshot capture methods remain isolated from the
monitoring loop so Gemini and voice interactions stay responsive.
"""

from __future__ import annotations

import base64
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional

import cv2

import mediapipe as mp

from config import CAMERA_RTSP_URL

CAMERA_SNAPSHOT_PATH = Path("arrow_data/screenshots/live_desk.jpg")
CAMERA_SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)

ACTIVE_MONITOR_INTERVAL = 0.2
DORMANT_MONITOR_INTERVAL = 5.0
ABSENCE_LOCK_SECONDS = 60


class CameraMonitor:
    def __init__(self, rtsp_url: str):
        self.rtsp_url = rtsp_url
        self.face_state_lock = threading.Lock()
        self.face_present = False
        self.absent_since: Optional[float] = None
        self.locked = False
        self.dormant = False
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True, name="CameraMonitor")
        self.cap: Optional[cv2.VideoCapture] = None
        self.detector = mp.solutions.face_detection.FaceDetection(
            model_selection=0,
            min_detection_confidence=0.5,
        )

    def start(self) -> None:
        if not self.thread.is_alive():
            self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self.thread.join(timeout=2)
        self._close_camera()
        self.detector.close()

    def _log(self, message: str) -> None:
        print(f"[camera] {message}")

    def _open_camera(self) -> bool:
        if self.cap is not None and self.cap.isOpened():
            return True
        try:
            self.cap = cv2.VideoCapture(self.rtsp_url)
        except Exception:
            self.cap = None
            return False

        if not self.cap.isOpened():
            if self.cap is not None:
                self.cap.release()
            self.cap = None
            return False
        return True

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

    def _detect_face(self, frame: cv2.Mat) -> bool:
        try:
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self.detector.process(rgb_frame)
            return bool(results.detections)
        except Exception:
            return False

    def _lock_system(self) -> None:
        if os.name == "nt":
            try:
                subprocess.run(
                    ["rundll32.exe", "user32.dll,LockWorkStation"],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception as exc:
                self._log(f"Failed to lock Windows workstation: {exc}")
        else:
            lock_commands = [
                ["xdg-screensaver", "lock"],
                ["gnome-screensaver-command", "-l"],
            ]
            for command in lock_commands:
                if shutil.which(command[0]):
                    try:
                        subprocess.run(
                            command,
                            check=False,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                        )
                        return
                    except Exception as exc:
                        self._log(f"Failed to execute lock command {command}: {exc}")
            self._log("No supported screen lock command found on this platform.")

    def _trigger_lock(self) -> None:
        with self.face_state_lock:
            if self.locked:
                return
            self.locked = True
            self.dormant = True
        self._log("No face sighted for 60 seconds. Locking the system and entering dormant mode.")
        self._lock_system()

    def _update_presence(self, face_present: bool) -> None:
        with self.face_state_lock:
            if face_present:
                if not self.face_present:
                    self._log("Face detected. Resetting absence timer.")
                self.face_present = True
                self.absent_since = None
                if self.locked:
                    self.locked = False
                    self._log("Visual wake event: face re-entered frame after lock.")
                if self.dormant:
                    self.dormant = False
                    self._log("Resuming active processing after wake.")
            else:
                if self.face_present or self.absent_since is None:
                    self.absent_since = time.monotonic()
                    self._log("No face detected. Starting absence timer.")
                self.face_present = False
                if not self.locked and self.absent_since is not None:
                    absence_duration = time.monotonic() - self.absent_since
                    if absence_duration >= ABSENCE_LOCK_SECONDS:
                        self._trigger_lock()

    def _run(self) -> None:
        while not self.stop_event.is_set():
            interval = DORMANT_MONITOR_INTERVAL if self.dormant else ACTIVE_MONITOR_INTERVAL
            frame = self._read_frame()
            face_present = False
            if frame is not None:
                face_present = self._detect_face(frame)
            self._update_presence(face_present)
            self.stop_event.wait(interval)
        self._close_camera()


camera_monitor = CameraMonitor(CAMERA_RTSP_URL)
camera_monitor.start()


def _ensure_output_dir() -> None:
    CAMERA_SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)


def _open_camera(rtsp_url: str) -> cv2.VideoCapture | None:
    try:
        cap = cv2.VideoCapture(rtsp_url)
    except Exception:
        return None

    if not cap.isOpened():
        cap.release()
        return None
    return cap


def _grab_frames(cap: cv2.VideoCapture, count: int = 4) -> list[cv2.Mat]:
    frames: list[cv2.Mat] = []
    for _ in range(count * 2):
        ret, frame = cap.read()
        if not ret or frame is None:
            continue
        frames.append(frame)
        if len(frames) >= count:
            break
    return frames


def save_snapshot(frame: cv2.Mat) -> str:
    _ensure_output_dir()
    cv2.imwrite(str(CAMERA_SNAPSHOT_PATH), frame)
    return str(CAMERA_SNAPSHOT_PATH)


def detect_faces(frame: cv2.Mat) -> list[tuple[int, int, int, int]]:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    if cascade.empty():
        return []
    faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60))
    return faces.tolist() if hasattr(faces, "tolist") else []


def detect_motion(frames: list[cv2.Mat]) -> bool:
    if len(frames) < 2:
        return False

    prev_gray = cv2.cvtColor(frames[0], cv2.COLOR_BGR2GRAY)
    last_gray = cv2.cvtColor(frames[-1], cv2.COLOR_BGR2GRAY)
    diff = cv2.absdiff(prev_gray, last_gray)
    _, thresh = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)
    motion_pixels = int(cv2.countNonZero(thresh))
    return motion_pixels > 5000


def capture_and_analyze(rtsp_url: str | None = None) -> dict | None:
    if not rtsp_url:
        return None

    cap = _open_camera(rtsp_url)
    if cap is None:
        return None

    frames = _grab_frames(cap, count=4)
    cap.release()
    if not frames:
        return None

    snapshot = frames[-1]
    saved_path = save_snapshot(snapshot)
    faces = detect_faces(snapshot)
    motion = detect_motion(frames)
    summary = []
    if faces:
        summary.append(f"Detected {len(faces)} face(s).")
    else:
        summary.append("No faces detected.")

    summary.append("Motion detected." if motion else "No motion detected.")

    return {
        "path": saved_path,
        "faces": len(faces),
        "motion": motion,
        "summary": " ".join(summary),
    }


def capture_live_desk_snapshot() -> dict | None:
    return capture_and_analyze(CAMERA_RTSP_URL)


def get_snapshot_base64(image_path: str) -> str | None:
    try:
        with open(image_path, "rb") as handle:
            return base64.b64encode(handle.read()).decode("utf-8")
    except Exception:
        return None
