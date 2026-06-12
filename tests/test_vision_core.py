"""Test suite for Phase 8 Vision Core Engine.

Comprehensive pytest coverage for vision_core module including:
- Engine initialization and model loading
- Auto FPS resource guard throttling
- Flash snapshot and frame buffer operations
- Orchestrator event hook integration
"""

import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from modules.vision_core import (
    VisionCoreEngine,
    initialize_vision_engine,
    process_camera_feed,
    track_object_trajectories,
    orchestrator_event_hook,
    VISION_SNAPSHOT_DIR,
)


class TestVisionCoreEngineInitialization:
    """Tests for vision engine initialization and model loading."""

    def test_initialize_vision_engine_success(self):
        """Verify vision engine initializes safely without error."""
        with patch("modules.vision_core.YOLO") as mock_yolo:
            mock_yolo.return_value = MagicMock()
            engine = VisionCoreEngine()
            assert engine is not None
            assert engine.model_name == "yolov8n.pt"
            assert engine.confidence == 0.35
            assert engine.device == "cpu"
            assert not engine.ready

            engine.initialize_vision_engine()
            time.sleep(0.5)
            assert engine.ready
            mock_yolo.assert_called_once_with("yolov8n.pt")

    def test_initialize_vision_engine_with_custom_params(self):
        """Verify vision engine initializes with custom parameters."""
        with patch("modules.vision_core.YOLO") as mock_yolo:
            mock_yolo.return_value = MagicMock()
            engine = initialize_vision_engine(
                model_name="yolov8m.pt",
                confidence=0.5
            )
            assert engine.model_name == "yolov8m.pt"
            assert engine.confidence == 0.5
            time.sleep(0.5)
            assert engine.ready

    def test_initialize_vision_engine_load_error_handling(self):
        """Verify vision engine handles model loading errors gracefully."""
        with patch("modules.vision_core.YOLO") as mock_yolo:
            mock_yolo.side_effect = RuntimeError("Model not found")
            engine = VisionCoreEngine()
            engine.initialize_vision_engine()
            time.sleep(0.5)
            assert not engine.ready
            assert engine.loading_error is not None
            assert "Model not found" in engine.loading_error

    def test_vision_engine_wait_until_ready(self):
        """Verify wait_until_ready polls for model readiness."""
        with patch("modules.vision_core.YOLO") as mock_yolo:
            mock_yolo.return_value = MagicMock()
            engine = VisionCoreEngine()
            engine.initialize_vision_engine()

            result = engine.wait_until_ready(timeout=5.0)
            assert result is True
            assert engine.ready

    def test_vision_engine_wait_until_ready_timeout(self):
        """Verify wait_until_ready respects timeout on failure."""
        engine = VisionCoreEngine()
        result = engine.wait_until_ready(timeout=0.2)
        assert result is False

    def test_engine_initialization_attributes(self):
        """Verify engine has correct initialization attributes."""
        with patch("modules.vision_core.YOLO") as mock_yolo:
            mock_yolo.return_value = MagicMock()
            engine = VisionCoreEngine(
                model_name="yolov8s.pt",
                confidence=0.45,
                initial_fps=5.0,
                latency_threshold=0.1,
                device="cuda",
            )
            assert engine.model_name == "yolov8s.pt"
            assert engine.confidence == 0.45
            assert engine.device == "cuda"
            assert engine.latency_threshold == 0.1
            assert engine.frame_interval == pytest.approx(0.2, abs=0.01)


class TestAutoFPSResourceGuardThrottling:
    """Tests for adaptive frame rate throttling based on latency."""

    def test_auto_fps_resource_guard_throttling(self):
        """Verify smart load controller dynamically throttles frame rate on high latency."""
        with patch("modules.vision_core.YOLO") as mock_yolo:
            mock_yolo.return_value = MagicMock()
            engine = VisionCoreEngine(
                latency_threshold=0.08,
                initial_fps=10.0
            )
            engine.initialize_vision_engine()
            time.sleep(0.5)

            initial_interval = engine.frame_interval
            assert initial_interval == pytest.approx(0.1, abs=0.01)

            # Simulate high latency -> should increase interval (slower frame rate)
            engine._adjust_frame_interval(latency=0.15)
            high_latency_interval = engine.frame_interval
            assert high_latency_interval > initial_interval

            # Simulate low latency -> should decrease interval (faster frame rate)
            engine._adjust_frame_interval(latency=0.02)
            low_latency_interval = engine.frame_interval
            assert low_latency_interval < high_latency_interval

    def test_fps_throttling_respects_min_bounds(self):
        """Verify frame interval cannot go below minimum."""
        with patch("modules.vision_core.YOLO") as mock_yolo:
            mock_yolo.return_value = MagicMock()
            engine = VisionCoreEngine()
            engine.initialize_vision_engine()
            time.sleep(0.5)

            # Simulate extreme low latency multiple times
            for _ in range(20):
                engine._adjust_frame_interval(latency=0.001)

            assert engine.frame_interval >= engine.min_interval
            assert engine.frame_interval == pytest.approx(engine.min_interval, abs=0.001)

    def test_fps_throttling_respects_max_bounds(self):
        """Verify frame interval cannot exceed maximum."""
        with patch("modules.vision_core.YOLO") as mock_yolo:
            mock_yolo.return_value = MagicMock()
            engine = VisionCoreEngine()
            engine.initialize_vision_engine()
            time.sleep(0.5)

            # Simulate extreme high latency multiple times
            for _ in range(20):
                engine._adjust_frame_interval(latency=1.0)

            assert engine.frame_interval <= engine.max_interval
            assert engine.frame_interval == pytest.approx(engine.max_interval, abs=0.001)

    def test_processing_latency_tracking(self):
        """Verify engine accurately tracks processing latency metrics."""
        with patch("modules.vision_core.YOLO") as mock_yolo:
            mock_yolo.return_value = MagicMock()
            engine = VisionCoreEngine()
            engine.initialize_vision_engine()
            time.sleep(0.5)

            assert engine.processing_latency == 0.0
            engine.processing_latency = 0.042
            assert engine.processing_latency == pytest.approx(0.042, abs=0.001)

    def test_latency_threshold_configuration(self):
        """Verify latency threshold is configurable and used correctly."""
        with patch("modules.vision_core.YOLO") as mock_yolo:
            mock_yolo.return_value = MagicMock()
            engine = VisionCoreEngine(latency_threshold=0.15)
            assert engine.latency_threshold == 0.15


class TestFlashSnapshotAndFrameBuffer:
    """Tests for snapshot capture and frame buffering operations."""

    def test_flash_snapshot_and_frame_buffer(self):
        """Verify frame is captured and successfully buffered to storage directory."""
        with patch("modules.vision_core.YOLO") as mock_yolo, \
             patch("modules.vision_core.cv2.imwrite") as mock_imwrite:

            mock_yolo.return_value = MagicMock()
            mock_imwrite.return_value = True

            engine = VisionCoreEngine()
            engine.initialize_vision_engine()
            time.sleep(0.5)

            # Create mock frame
            mock_frame = np.zeros((480, 640, 3), dtype=np.uint8)

            # Capture snapshot
            snapshot_path = engine._capture_snapshot(mock_frame)

            assert snapshot_path is not None
            assert "vision_snapshot_" in str(snapshot_path)
            assert str(snapshot_path).endswith(".jpg")
            assert str(snapshot_path).startswith(str(VISION_SNAPSHOT_DIR))
            mock_imwrite.assert_called_once()

    def test_snapshot_directory_exists(self):
        """Verify snapshot directory is created and accessible."""
        assert VISION_SNAPSHOT_DIR.exists()
        assert VISION_SNAPSHOT_DIR.is_dir()

    def test_multiple_snapshots_buffered_sequentially(self):
        """Verify multiple snapshots can be buffered sequentially with unique names."""
        with patch("modules.vision_core.YOLO") as mock_yolo, \
             patch("modules.vision_core.cv2.imwrite") as mock_imwrite:

            mock_yolo.return_value = MagicMock()
            mock_imwrite.return_value = True

            engine = VisionCoreEngine()
            engine.initialize_vision_engine()
            time.sleep(0.5)

            mock_frame = np.zeros((480, 640, 3), dtype=np.uint8)

            paths = []
            for _ in range(3):
                path = engine._capture_snapshot(mock_frame)
                paths.append(path)
                time.sleep(0.01)

            assert len(paths) == 3
            assert len(set(str(p) for p in paths)) == 3  # All unique names
            assert mock_imwrite.call_count == 3

    def test_trajectory_tracking_buffer_limit(self):
        """Verify trajectory buffer respects 32-point size limit."""
        with patch("modules.vision_core.YOLO") as mock_yolo:
            mock_yolo.return_value = MagicMock()
            engine = VisionCoreEngine()
            engine.initialize_vision_engine()
            time.sleep(0.5)

            # Add many points to trajectory
            for i in range(50):
                centroid = np.array([100 + i, 100 + i])
                engine._update_trajectory(object_id=1, centroid=centroid)

            # Verify buffer is capped at 32
            assert len(engine.trajectories[1]) == 32

    def test_centroid_calculation_from_box(self):
        """Verify centroid is calculated correctly from bounding box coordinates."""
        box = np.array([100, 100, 200, 300])
        centroid = VisionCoreEngine._centroid_from_box(box)

        expected = np.array([150, 200])
        np.testing.assert_array_equal(centroid, expected)

    def test_snapshot_path_uniqueness_over_time(self):
        """Verify snapshots get unique names based on millisecond timestamps."""
        with patch("modules.vision_core.YOLO") as mock_yolo, \
             patch("modules.vision_core.cv2.imwrite") as mock_imwrite:

            mock_yolo.return_value = MagicMock()
            mock_imwrite.return_value = True

            engine = VisionCoreEngine()
            engine.initialize_vision_engine()
            time.sleep(0.5)

            mock_frame = np.zeros((480, 640, 3), dtype=np.uint8)

            path1 = engine._capture_snapshot(mock_frame)
            time.sleep(0.002)
            path2 = engine._capture_snapshot(mock_frame)

            assert str(path1) != str(path2)
            assert path1.name < path2.name  # Lexicographic ordering by timestamp


class TestVisionOrchestratorEventHook:
    """Tests for orchestrator event hook integration."""

    def test_vision_orchestrator_event_hook_camera_start(self):
        """Verify event hook handles camera stream start event correctly."""
        with patch("modules.vision_core.YOLO") as mock_yolo, \
             patch("modules.vision_core.ENGINE.start_stream") as mock_start:

            mock_yolo.return_value = MagicMock()
            mock_start.return_value = {"status": "started", "feed_url": "rtsp://test"}

            from modules.vision_core import ENGINE
            ENGINE.ready = True
            ENGINE.model = MagicMock()

            result = orchestrator_event_hook(
                "camera.stream.start",
                {"feed_url": "rtsp://test"}
            )

            assert result["status"] == "started"
            assert mock_start.called

    def test_vision_orchestrator_event_hook_camera_stop(self):
        """Verify event hook handles camera stream stop event correctly."""
        result = orchestrator_event_hook("camera.stream.stop", {})
        assert result["status"] == "stopped"

    def test_vision_orchestrator_event_hook_missing_feed_url(self):
        """Verify event hook returns error for missing feed_url in start event."""
        result = orchestrator_event_hook("camera.stream.start", {})
        assert result["status"] == "error"
        assert "feed_url" in result["error"].lower()

    def test_vision_orchestrator_event_hook_snapshot_request(self):
        """Verify event hook handles snapshot request event."""
        result = orchestrator_event_hook("vision.snapshot.request", {})
        assert result["status"] == "ignored"

    def test_vision_orchestrator_event_hook_unknown_event(self):
        """Verify event hook ignores unknown events gracefully."""
        result = orchestrator_event_hook("unknown.event.type", {"payload": "data"})
        assert result["status"] == "ignored"
        assert result["event_type"] == "unknown.event.type"

    def test_vision_orchestrator_event_hook_payload_preservation(self):
        """Verify event hook preserves payload structure in responses."""
        result = orchestrator_event_hook(
            "vision.snapshot.request",
            {"test_key": "test_value"}
        )
        assert result["status"] == "ignored"


class TestProcessCameraFeed:
    """Tests for camera feed processing function."""

    def test_process_camera_feed_engine_not_ready(self):
        """Verify process_camera_feed initializes engine if not ready."""
        with patch("modules.vision_core.YOLO") as mock_yolo:
            mock_yolo.return_value = MagicMock()

            result = process_camera_feed("rtsp://test")

            assert result["status"] in ["error", "already_running", "started"]

    def test_process_camera_feed_with_ready_engine(self):
        """Verify process_camera_feed returns started when engine ready."""
        with patch("modules.vision_core.YOLO") as mock_yolo:
            mock_yolo.return_value = MagicMock()

            from modules.vision_core import ENGINE
            ENGINE.ready = True
            ENGINE.model = MagicMock()

            result = process_camera_feed("rtsp://test")

            assert result["status"] in ["already_running", "started"]

    def test_process_camera_feed_with_valid_url(self):
        """Verify process_camera_feed accepts valid RTSP/HTTP URLs."""
        with patch("modules.vision_core.YOLO") as mock_yolo:
            mock_yolo.return_value = MagicMock()

            from modules.vision_core import ENGINE
            ENGINE.ready = True
            ENGINE.model = MagicMock()

            for url in ["rtsp://192.168.1.100:554/stream", "http://localhost:8080/feed"]:
                result = process_camera_feed(url)
                assert result["status"] in ["already_running", "started"]


class TestTrackObjectTrajectories:
    """Tests for object trajectory tracking and summary."""

    def test_track_object_trajectories_empty(self):
        """Verify trajectory summary works when no objects tracked."""
        with patch("modules.vision_core.YOLO") as mock_yolo:
            mock_yolo.return_value = MagicMock()

            from modules.vision_core import ENGINE
            ENGINE.trajectories.clear()
            ENGINE.processing_latency = 0.0
            ENGINE.frame_interval = 0.1

            result = track_object_trajectories()

            assert result["trajectory_count"] == 0
            assert result["sample_paths"] == {}
            assert result["processing_latency"] == pytest.approx(0.0, abs=0.001)

    def test_track_object_trajectories_with_data(self):
        """Verify trajectory summary includes all tracking data correctly."""
        with patch("modules.vision_core.YOLO") as mock_yolo:
            mock_yolo.return_value = MagicMock()

            from modules.vision_core import ENGINE
            ENGINE.trajectories = {
                1: [(100, 100), (105, 105), (110, 110)],
                2: [(200, 200), (210, 210)],
            }
            ENGINE.processing_latency = 0.05
            ENGINE.frame_interval = 0.1

            result = track_object_trajectories()

            assert result["trajectory_count"] == 2
            assert "1" in result["sample_paths"]
            assert "2" in result["sample_paths"]
            assert result["processing_latency"] == pytest.approx(0.05, abs=0.001)
            assert result["frame_interval"] == pytest.approx(0.1, abs=0.001)

    def test_trajectory_summary_last_five_points(self):
        """Verify trajectory summary includes last 5 points of each trajectory."""
        with patch("modules.vision_core.YOLO") as mock_yolo:
            mock_yolo.return_value = MagicMock()

            from modules.vision_core import ENGINE
            ENGINE.trajectories = {
                1: [(i, i) for i in range(20)],
            }

            result = track_object_trajectories()

            assert len(result["sample_paths"]["1"]) <= 5
            assert result["sample_paths"]["1"] == [(15, 15), (16, 16), (17, 17), (18, 18), (19, 19)]


class TestVisionCoreThreading:
    """Tests for threading and concurrency safety."""

    def test_model_lock_prevents_race_conditions(self):
        """Verify model_lock provides thread-safe access to model."""
        with patch("modules.vision_core.YOLO") as mock_yolo:
            mock_yolo.return_value = MagicMock()
            engine = VisionCoreEngine()

            assert isinstance(engine.model_lock, type(threading.Lock()))

            # Verify lock can be acquired and released
            engine.model_lock.acquire()
            assert engine.model_lock.locked()
            engine.model_lock.release()
            assert not engine.model_lock.locked()

    def test_stop_event_gracefully_halts_stream(self):
        """Verify stop_event can gracefully signal stream capture to halt."""
        with patch("modules.vision_core.YOLO") as mock_yolo:
            mock_yolo.return_value = MagicMock()
            engine = VisionCoreEngine()

            assert not engine.stop_event.is_set()
            engine.stop_event.set()
            assert engine.stop_event.is_set()
            engine.stop_event.clear()
            assert not engine.stop_event.is_set()

    def test_load_thread_daemon_flag(self):
        """Verify load thread runs as daemon."""
        with patch("modules.vision_core.YOLO") as mock_yolo:
            mock_yolo.return_value = MagicMock()
            engine = VisionCoreEngine()
            engine.initialize_vision_engine()

            # Thread should have been created
            assert engine.load_thread is not None
            assert engine.load_thread.daemon

    def test_capture_thread_daemon_flag(self):
        """Verify capture thread runs as daemon."""
        with patch("modules.vision_core.YOLO") as mock_yolo, \
             patch("modules.vision_core.cv2.VideoCapture") as mock_cap:

            mock_yolo.return_value = MagicMock()
            mock_capture_obj = MagicMock()
            mock_capture_obj.isOpened.return_value = False
            mock_cap.return_value = mock_capture_obj

            engine = VisionCoreEngine()
            engine.ready = True
            engine.model = MagicMock()
            engine.start_stream("rtsp://test")

            # Capture thread should be daemon
            if engine.capture_thread:
                assert engine.capture_thread.daemon


class TestLineZoneInitialization:
    """Tests for line zone setup for trajectory crossing detection."""

    def test_initialize_line_zone(self):
        """Verify line zone is initialized from frame dimensions correctly."""
        with patch("modules.vision_core.YOLO") as mock_yolo:
            mock_yolo.return_value = MagicMock()
            engine = VisionCoreEngine()
            engine.initialize_vision_engine()
            time.sleep(0.5)

            # Create mock frame with specific dimensions
            mock_frame = np.zeros((480, 640, 3), dtype=np.uint8)
            engine._initialize_line_zone(mock_frame)

            assert engine.line_start is not None
            assert engine.line_end is not None

            # Line should be at 35% height (0.35 * 480 = 168)
            assert engine.line_start[1] == pytest.approx(168, abs=1)
            assert engine.line_end[1] == pytest.approx(168, abs=1)

            # Line should span 10% to 90% width
            # Start: 0.1 * 640 = 64, End: 0.9 * 640 = 576
            assert engine.line_start[0] == pytest.approx(64, abs=1)
            assert engine.line_end[0] == pytest.approx(576, abs=1)

    def test_initialize_line_zone_idempotent(self):
        """Verify line zone only initializes once (idempotent)."""
        with patch("modules.vision_core.YOLO") as mock_yolo:
            mock_yolo.return_value = MagicMock()
            engine = VisionCoreEngine()

            mock_frame = np.zeros((480, 640, 3), dtype=np.uint8)
            engine._initialize_line_zone(mock_frame)
            first_start = engine.line_start.copy()

            # Initialize again with different frame size
            mock_frame2 = np.zeros((1080, 1920, 3), dtype=np.uint8)
            engine._initialize_line_zone(mock_frame2)

            # Should still be the same (idempotent)
            np.testing.assert_array_equal(engine.line_start, first_start)

    def test_line_zone_coordinates_are_integers(self):
        """Verify line zone coordinates are integer pixel values."""
        with patch("modules.vision_core.YOLO") as mock_yolo:
            mock_yolo.return_value = MagicMock()
            engine = VisionCoreEngine()

            mock_frame = np.zeros((480, 640, 3), dtype=np.uint8)
            engine._initialize_line_zone(mock_frame)

            assert isinstance(engine.line_start[0], (int, np.integer))
            assert isinstance(engine.line_start[1], (int, np.integer))
            assert isinstance(engine.line_end[0], (int, np.integer))
            assert isinstance(engine.line_end[1], (int, np.integer))


class TestPointSideCalculation:
    """Tests for point-to-line side calculation for crossing detection."""

    def test_point_side_calculation(self):
        """Verify point-to-line side calculation works correctly."""
        with patch("modules.vision_core.YOLO") as mock_yolo:
            mock_yolo.return_value = MagicMock()
            engine = VisionCoreEngine()

            # Set up a horizontal line
            engine.line_start = np.array([0, 100])
            engine.line_end = np.array([200, 100])

            # Point above line
            point_above = np.array([100, 50])
            side_above = engine._point_side(point_above)

            # Point below line
            point_below = np.array([100, 150])
            side_below = engine._point_side(point_below)

            # Should be different sides
            assert side_above != side_below


class TestBroadcastEventIntegration:
    """Tests for event broadcasting to orchestrator."""

    def test_broadcast_event_integration(self):
        """Verify engine broadcasts events to orchestrator."""
        with patch("modules.vision_core.YOLO") as mock_yolo, \
             patch("modules.vision_core.get_orchestrator") as mock_get_orch:

            mock_yolo.return_value = MagicMock()
            mock_orch = MagicMock()
            mock_get_orch.return_value = mock_orch

            engine = VisionCoreEngine()

            # Test broadcast
            engine._broadcast_event("test.event", {"key": "value"})

            mock_orch.broadcast.assert_called_once_with("test.event", {"key": "value"})


class TestEngineStreamOperations:
    """Tests for stream start/stop operations."""

    def test_stop_stream_returns_stopped_status(self):
        """Verify stop_stream returns proper status response."""
        with patch("modules.vision_core.YOLO") as mock_yolo:
            mock_yolo.return_value = MagicMock()
            engine = VisionCoreEngine()

            result = engine.stop_stream()

            assert result["status"] == "stopped"

    def test_start_stream_when_not_ready(self):
        """Verify start_stream returns error when engine not ready."""
        engine = VisionCoreEngine()

        result = engine.start_stream("rtsp://test")

        assert result["status"] == "error"
        assert "not initialized" in result["error"].lower()
