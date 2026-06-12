import asyncio
from unittest.mock import MagicMock, patch

from modules.orchestrator import CentralOrchestrator, get_orchestrator


def test_orchestrator_discovers_builtin_plugins():
    orchestrator = CentralOrchestrator(auto_scan=True, auto_start_background=False)
    plugins = orchestrator.discover_plugins()

    names = {plugin["name"] for plugin in plugins}
    assert "vision_core" in names
    assert any(name in names for name in ("memory", "security", "telegram"))


def test_orchestrator_broadcasts_events_to_registered_handlers():
    orchestrator = CentralOrchestrator(auto_scan=False, auto_start_background=False)

    seen = []

    def test_handler(event_type, payload):
        seen.append((event_type, payload))

    orchestrator.register_plugin("test_hook", test_handler, events={"phase14.test"})
    orchestrator.broadcast("phase14.test", {"value": 1})

    assert seen == [("phase14.test", {"value": 1})]


def test_background_task_queue_priority():
    orchestrator = CentralOrchestrator(auto_scan=False, auto_start_background=True)
    try:
        result_high = orchestrator.enqueue_background_task("phase14.background", {"value": 1}, priority=10)
        result_low = orchestrator.enqueue_background_task("phase14.background", {"value": 2}, priority=1)

        assert result_high["status"] == "queued"
        assert result_low["status"] == "queued"

        # Use the orchestrator inspection helper to avoid race conditions
        snapshot = orchestrator.get_queued_tasks_snapshot()
        assert any(t.get("payload", {}).get("value") == 1 for t in snapshot)
    finally:
        orchestrator.stop_background_worker()


def test_vision_optimization_event_listener_queues_work():
    orchestrator = CentralOrchestrator(auto_scan=False, auto_start_background=True)
    try:
        with patch.object(orchestrator, "enqueue_background_task", return_value={"status": "queued"}) as mock_enqueue:
            result = orchestrator.broadcast("vision.optimization.requested", {"dataset_id": "Roboflow/universal-objects", "validation_metrics": {"mean_average_precision": 0.72}})

        assert any(entry["name"] == "_vision_optimization_event_handler" or entry["name"] == "listener" for entry in result)
        mock_enqueue.assert_called_once()
    finally:
        orchestrator.stop_background_worker()


def test_get_orchestrator_returns_singleton():
    first = get_orchestrator()
    second = get_orchestrator()

    assert first is second
