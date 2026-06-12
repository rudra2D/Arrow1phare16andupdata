"""Phase 8: Vision Core for local Wi-Fi feed ingestion and tracking.

This module provides a production-ready vision pipeline using Ultralytics YOLO
for object detection and Supervision for annotation and trajectory telemetry.
It integrates with the Phase 14 Orchestrator as an auto-discovered plugin.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import cv2
import numpy as np
import supervision as sv
from ultralytics import YOLO

from modules.orchestrator import get_orchestrator

ORCHESTRATOR_PLUGIN = {
    "name": "vision_core",
    "handler": "orchestrator_event_hook",
    "events": ("*",),
    "priority": 20,
}

VISION_SNAPSHOT_DIR = Path("storage/vision_snapshots")
VISION_SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)


class VisionCoreEngine:
    def __init__(
        self,
        model_name: str = "yolov8n.pt",
        confidence: float = 0.35,
        initial_fps: float = 10.0,
        latency_threshold: float = 0.08,
        device: str = "cpu",
    ) -> None:
        self.model_name = model_name
        self.confidence = confidence
        self.device = device
        self.model: Optional[YOLO] = None
        self.ready = False
        self.loading_error: Optional[str] = None
        self.model_lock = threading.Lock()
        self.load_thread: Optional[threading.Thread] = None
        self.capture_thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        self.frame_interval = 1.0 / initial_fps
        self.min_interval = 1.0 / 10.0
        self.max_interval = 1.0 / 1.0
        self.latency_threshold = latency_threshold
        self.processing_latency = 0.0
        self.box_annotator = sv.BoxAnnotator(thickness=2)
        self.trajectories: Dict[int, List[tuple[int, int]]] = {}
        self.previous_side_map: Dict[int, int] = {}
        self.line_start: Optional[np.ndarray] = None
        self.line_end: Optional[np.ndarray] = None
        self.orchestrator = get_orchestrator()

    def initialize_vision_engine(self) -> None:
        if self.load_thread and self.load_thread.is_alive():
            return
        self.load_thread = threading.Thread(
            target=self._load_model,
            daemon=True,
            name="vision-core-model-loader",
        )
        self.load_thread.start()

    def _load_model(self) -> None:
        try:
            self.model = YOLO(self.model_name)
            self.ready = True
            self.loading_error = None
        except Exception as exc:
            self.ready = False
            self.loading_error = str(exc)

    def wait_until_ready(self, timeout: float = 15.0) -> bool:
        start = time.time()
        while time.time() - start < timeout:
            if self.ready:
                return True
            if self.loading_error:
                return False
            time.sleep(0.2)
        return self.ready

    def start_stream(self, feed_url: str) -> dict[str, Any]:
        if not self.ready or self.model is None:
            return {
                "status": "error",
                "error": "vision engine is not initialized or model is not ready",
            }

        if self.capture_thread and self.capture_thread.is_alive():
            return {"status": "already_running", "feed_url": feed_url}

        self.stop_event.clear()
        self.capture_thread = threading.Thread(
            target=self._stream_loop,
            args=(feed_url,),
            daemon=True,
            name="vision-core-stream",
        )
        self.capture_thread.start()
        return {"status": "started", "feed_url": feed_url}

    def stop_stream(self) -> dict[str, Any]:
        self.stop_event.set()
        if self.capture_thread:
            self.capture_thread.join(timeout=2)
        return {"status": "stopped"}

    def _stream_loop(self, feed_url: str) -> None:
        capture = cv2.VideoCapture(feed_url)
        if not capture.isOpened():
            self._broadcast_event(
                "vision.stream.error",
                {"feed_url": feed_url, "error": "unable to open video stream"},
            )
            return

        while not self.stop_event.is_set():
            start_time = time.perf_counter()
            success, frame = capture.read()
            if not success or frame is None:
                time.sleep(0.1)
                continue

            self._initialize_line_zone(frame)
            if not self.ready or self.model is None:
                time.sleep(0.1)
                continue

            detection_payload = self._process_frame(frame, feed_url)
            if detection_payload:
                self._broadcast_event("vision.alert.triggered", detection_payload)

            self.processing_latency = time.perf_counter() - start_time
            self._adjust_frame_interval(self.processing_latency)
            time.sleep(self.frame_interval)

        capture.release()

    def _process_frame(self, frame: cv2.Mat, feed_url: str) -> Optional[Dict[str, Any]]:
        results = self.model.track(
            frame,
            conf=self.confidence,
            persist=True,
            device=self.device,
        )
        if not results:
            return None

        result = results[0]
        detections = self._build_detections(result)
        annotated_frame = self.box_annotator.annotate(frame.copy(), detections)
        self._check_trajectory_alerts(detections, frame, feed_url)
        return {
            "feed_url": feed_url,
            "frame_width": int(frame.shape[1]),
            "frame_height": int(frame.shape[0]),
            "detections": len(detections.xyxy),
            "objects": detections.class_id.tolist() if hasattr(detections, "class_id") else [],
            "latency": round(self.processing_latency, 4),
        }

    def _build_detections(self, result: Any) -> sv.Detections:
        if hasattr(sv.Detections, "from_ultralytics"):
            return sv.Detections.from_ultralytics(result)

        if hasattr(sv.Detections, "from_yolov8"):
            return sv.Detections.from_yolov8(result)

        raise RuntimeError("Supervision Detections factory for Ultralytics models is unavailable in this version")

    def _initialize_line_zone(self, frame: cv2.Mat) -> None:
        if self.line_start is not None and self.line_end is not None:
            return
        height, width = frame.shape[:2]
        self.line_start = np.array((int(width * 0.1), int(height * 0.35)))
        self.line_end = np.array((int(width * 0.9), int(height * 0.35)))

    def _adjust_frame_interval(self, latency: float) -> None:
        if latency > self.latency_threshold and self.frame_interval < self.max_interval:
            self.frame_interval = min(self.max_interval, self.frame_interval * 1.2)
        elif latency < self.latency_threshold * 0.75 and self.frame_interval > self.min_interval:
            self.frame_interval = max(self.min_interval, self.frame_interval * 0.9)

    def _check_trajectory_alerts(self, detections: sv.Detections, frame: cv2.Mat, feed_url: str) -> None:
        if len(detections.xyxy) == 0:
            return

        alert_objects: List[Dict[str, Any]] = []
        for index, box in enumerate(detections.xyxy):
            centroid = self._centroid_from_box(box)
            object_id = self._object_id_from_detections(detections, index)
            self._update_trajectory(object_id, centroid)
            if self._check_line_crossing(object_id, centroid):
                alert_objects.append(
                    {
                        "object_id": object_id,
                        "centroid": tuple(centroid),
                        "label": self._label_from_detections(detections, index),
                    }
                )

        if alert_objects:
            snapshot_path = self._capture_snapshot(frame)
            self._broadcast_event(
                "vision.snapshot.saved",
                {
                    "feed_url": feed_url,
                    "snapshot_path": str(snapshot_path),
                    "object_count": len(alert_objects),
                    "objects": alert_objects,
                },
            )

    def _object_id_from_detections(self, detections: sv.Detections, index: int) -> int:
        if hasattr(detections, "id") and len(detections.id) > index:
            return int(detections.id[index])
        return index

    @staticmethod
    def _centroid_from_box(box: np.ndarray) -> np.ndarray:
        x1, y1, x2, y2 = box.astype(int)
        return np.array([int((x1 + x2) / 2), int((y1 + y2) / 2)])

    @staticmethod
    def _label_from_detections(detections: sv.Detections, index: int) -> str:
        if hasattr(detections, "labels") and len(detections.labels) > index:
            return str(detections.labels[index])
        if hasattr(detections, "class_id") and len(detections.class_id) > index:
            return str(int(detections.class_id[index]))
        return "unknown"

    def _update_trajectory(self, object_id: int, centroid: np.ndarray) -> None:
        trajectory = self.trajectories.setdefault(object_id, [])
        trajectory.append((int(centroid[0]), int(centroid[1])))
        if len(trajectory) > 32:
            trajectory.pop(0)

    def _check_line_crossing(self, object_id: int, centroid: np.ndarray) -> bool:
        if self.line_start is None or self.line_end is None:
            return False

        current_side = self._point_side(centroid)
        previous_side = self.previous_side_map.get(object_id, current_side)
        self.previous_side_map[object_id] = current_side
        return current_side != previous_side

    def _point_side(self, point: np.ndarray) -> int:
        if self.line_start is None or self.line_end is None:
            return 0
        x1, y1 = self.line_start
        x2, y2 = self.line_end
        px, py = point
        return int(np.sign((x2 - x1) * (py - y1) - (y2 - y1) * (px - x1)))

    def _capture_snapshot(self, frame: cv2.Mat) -> Path:
        timestamp = int(time.time() * 1000)
        snapshot_path = VISION_SNAPSHOT_DIR / f"vision_snapshot_{timestamp}.jpg"
        cv2.imwrite(str(snapshot_path), frame)
        return snapshot_path

    def _broadcast_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        self.orchestrator.broadcast(event_type, payload)

    def get_trajectory_summary(self) -> Dict[str, Any]:
        return {
            "trajectory_count": len(self.trajectories),
            "sample_paths": {str(object_id): self.trajectories[object_id][-5:] for object_id in list(self.trajectories)[:5]},
            "processing_latency": round(self.processing_latency, 4),
            "frame_interval": round(self.frame_interval, 4),
        }


ENGINE = VisionCoreEngine()


def initialize_vision_engine(model_name: str = "yolov8n.pt", confidence: float = 0.35) -> VisionCoreEngine:
    ENGINE.model_name = model_name
    ENGINE.confidence = confidence
    ENGINE.initialize_vision_engine()
    return ENGINE


def process_camera_feed(feed_url: str) -> dict[str, Any]:
    if not ENGINE.ready:
        ENGINE.initialize_vision_engine()
        if not ENGINE.wait_until_ready(timeout=15.0):
            return {"status": "error", "error": "Vision engine failed to initialize"}
    return ENGINE.start_stream(feed_url)


def track_object_trajectories() -> Dict[str, Any]:
    return ENGINE.get_trajectory_summary()


def orchestrator_event_hook(event_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    if event_type == "camera.stream.start":
        feed_url = str(payload.get("feed_url", ""))
        if not feed_url:
            return {"status": "error", "error": "feed_url is required"}
        return process_camera_feed(feed_url)

    if event_type == "camera.stream.stop":
        return ENGINE.stop_stream()

    if event_type == "vision.snapshot.request":
        return {"status": "ignored", "info": "snapshot request event received"}

    return {"status": "ignored", "event_type": event_type}
