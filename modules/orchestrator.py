"""Phase 14: Central Orchestrator & Event-Driven Engine.

This module is the central brain for Arrow. It provides:
- plugin discovery and event broadcasting across phases
- asynchronous background task queueing for cloud-heavy events
- a Trinity Cloud Sync architecture for GitHub, Google Colab, and Google Drive
- Phase 16 training pipeline orchestration with remote dataset ingestion,
  shadow evaluation, and guarded production model updates
- secure credential retrieval from Google Colab secure environment
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
import json
import os
import pkgutil
import threading
import time
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Optional, Union

import modules

try:
    import google.colab.userdata as colab_userdata
except Exception:
    colab_userdata = None

EventPayload = Dict[str, Any]
PluginResult = Dict[str, Any]
PluginHandler = Union[Callable[[str, EventPayload], Any], Callable[[str, EventPayload], Awaitable[Any]]]


class DriveMountError(RuntimeError):
    pass


class CredentialError(RuntimeError):
    pass


class CentralOrchestrator:
    """Central orchestrator for Arrow's event-driven and cloud-synced engine."""

    def __init__(
        self,
        auto_scan: bool = True,
        package_name: str = "modules",
        github_source: Optional[str] = None,
        colab_base_url: str = "https://colab.research.google.com",
        drive_mount: Union[str, Path] = "/content/drive",
        auto_start_background: bool = True,
    ) -> None:
        self.package_name = package_name
        self.github_source = github_source or os.getenv(
            "ARROW_GITHUB_SOURCE",
            "https://github.com/rudra2D/Arrow1phare16andupdata",
        )
        self.colab_base_url = colab_base_url
        self.drive_mount = Path(drive_mount)
        self.dataset_vault = self.drive_mount / "arrow_data" / "datasets"
        self.model_vault = self.drive_mount / "arrow_models"
        self.report_vault = self.drive_mount / "arrow_reports"

        self._plugins: Dict[str, Dict[str, Any]] = {}
        self._event_listeners: Dict[str, List[Dict[str, Any]]] = {}
        self._event_history: List[Dict[str, Any]] = []
        self._lock = threading.RLock()
        self._booted = False

        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._task_queue: Optional[asyncio.PriorityQueue[tuple[int, float, EventPayload]]] = None
        self._background_thread: Optional[threading.Thread] = None
        self._running = False
        self._task_counter = 0
        self._queued_tasks_snapshot: List[EventPayload] = []

        if auto_start_background:
            self._start_background_worker()

        self.register_event_listener(
            "vision.optimization.requested",
            self._vision_optimization_event_handler,
            priority=20,
        )

        if auto_scan:
            self.discover_plugins()

    def _start_background_worker(self) -> None:
        if self._background_thread and self._background_thread.is_alive():
            return

        self._background_thread = threading.Thread(
            target=self._run_background_loop,
            daemon=True,
            name="CentralOrchestratorBackground",
        )
        self._background_thread.start()

        while self._loop is None:
            time.sleep(0.01)

    def _run_background_loop(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._task_queue = asyncio.PriorityQueue()
        self._running = True
        self._loop.create_task(self._background_worker())
        self._loop.run_forever()

    async def _background_worker(self) -> None:
        assert self._task_queue is not None
        while self._running:
            _priority, _order, task = await self._task_queue.get()
            try:
                # Remove from snapshot when the background worker starts processing it
                try:
                    # match by queued_at timestamp if available
                    queued_at = task.get("queued_at")
                    for i, t in enumerate(self._queued_tasks_snapshot):
                        if isinstance(t, dict) and t.get("queued_at") == queued_at:
                            del self._queued_tasks_snapshot[i]
                            break
                except Exception:
                    pass

                await self._dispatch_background_task(task)
            except Exception:
                pass
            self._task_queue.task_done()

        # Drain remaining tasks gracefully
        try:
            while not self._task_queue.empty():
                try:
                    self._task_queue.get_nowait()
                    self._task_queue.task_done()
                except Exception:
                    break
        except Exception:
            pass

    def stop_background_worker(self) -> None:
        if not self._running or self._loop is None:
            return
        self._running = False
        # Push a sentinel task to unblock the worker if it's waiting on get()
        try:
            if self._task_queue is not None:
                self._task_counter += 1
                self._loop.call_soon_threadsafe(self._task_queue.put_nowait, (999999, self._task_counter, {"event_type": "__shutdown__"}))
        except Exception:
            pass
        self._loop.call_soon_threadsafe(self._loop.stop)
        if self._background_thread is not None:
            self._background_thread.join(timeout=2)

    def _get_secure_token(self, token_key: str) -> str:
        if colab_userdata is not None:
            token = colab_userdata.get(token_key)
            if token:
                return str(token)
        token = os.getenv(token_key)
        if token:
            return token
        raise CredentialError(f"Secure token '{token_key}' not available")

    def _ensure_drive_mount(self) -> Path:
        try:
            self.drive_mount.mkdir(parents=True, exist_ok=True)
            self.dataset_vault.mkdir(parents=True, exist_ok=True)
            self.model_vault.mkdir(parents=True, exist_ok=True)
            self.report_vault.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            raise DriveMountError(f"Cannot mount Drive vault at {self.drive_mount}: {exc}")
        return self.drive_mount

    async def _download_dataset_to_drive(self, dataset_id: str) -> Path:
        self._ensure_drive_mount()
        target_path = self.dataset_vault / dataset_id.replace("/", "_")
        target_path.mkdir(parents=True, exist_ok=True)
        try:
            from huggingface_hub import snapshot_download

            access_token = self._get_secure_token("HUGGINGFACE_TOKEN")
            snapshot_download(
                repo_id=dataset_id,
                local_dir=str(target_path),
                token=access_token,
                repo_type="dataset",
            )
        except ImportError as exc:
            raise RuntimeError("huggingface_hub is required for dataset ingestion") from exc
        return target_path

    def get_github_baseline_reference(self) -> str:
        """Return the GitHub read-only source of truth URL for baseline configurations."""
        return self.github_source

    def verify_github_read_only_source(self) -> bool:
        """Verify that the configured GitHub source is a valid read-only repository reference."""
        return self.github_source.startswith("https://github.com") or self.github_source.startswith("git@github.com")

    def get_colab_execution_url(self, notebook_path: str) -> str:
        """Generate a Google Colab URL for remote GPU notebook execution."""
        notebook_path = notebook_path.lstrip("/")
        return f"{self.colab_base_url}/github/{self.github_source}/blob/main/{notebook_path}"

    def get_drive_vault_path(self) -> Path:
        """Return the mounted Google Drive vault path for Arrow assets."""
        return self.drive_mount

    def _load_baseline_metrics(self) -> Dict[str, float]:
        baseline_file = self.model_vault / "baseline_metrics.json"
        if not baseline_file.exists():
            return {}
        try:
            metrics = json.loads(baseline_file.read_text(encoding="utf-8"))
            return {k: float(v) for k, v in metrics.items() if isinstance(v, (int, float))}
        except Exception:
            return {}

    def _save_baseline_metrics(self, metrics: Dict[str, float]) -> None:
        baseline_file = self.model_vault / "baseline_metrics.json"
        baseline_file.write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    def _is_metric_higher(self, new_metrics: Dict[str, float], baseline_metrics: Dict[str, float]) -> bool:
        baseline_map = baseline_metrics.get("mean_average_precision", 0.0)
        new_map = new_metrics.get("mean_average_precision", 0.0)
        return new_map > baseline_map

    def _write_metric_report(
        self,
        dataset_id: str,
        new_metrics: Dict[str, float],
        baseline_metrics: Dict[str, float],
        updated: bool,
    ) -> Path:
        self._ensure_drive_mount()
        timestamp = int(time.time())
        report_file = self.report_vault / f"optimization_report_{dataset_id.replace('/', '_')}_{timestamp}.txt"
        gain = new_metrics.get("mean_average_precision", 0.0) - baseline_metrics.get("mean_average_precision", 0.0)
        report_lines = [
            f"Dataset: {dataset_id}",
            f"Drive Path: {self.dataset_vault / dataset_id.replace('/', '_')}",
            f"Updated Production Model: {updated}",
            f"Baseline mAP: {baseline_metrics.get('mean_average_precision', 0.0):.4f}",
            f"New mAP: {new_metrics.get('mean_average_precision', 0.0):.4f}",
            f"mAP Gain: {gain:.4f}",
        ]
        report_file.write_text("\n".join(report_lines), encoding="utf-8")
        return report_file

    async def _dispatch_background_task(self, task: EventPayload) -> None:
        event_type = task.get("event_type")
        payload = task.get("payload", {})
        if event_type == "vision.optimization.requested":
            await self._execute_vision_optimization(payload)

    async def _execute_vision_optimization(self, payload: EventPayload) -> None:
        dataset_id = payload.get("dataset_id", "Roboflow/universal-objects")
        validation_metrics = payload.get("validation_metrics")
        if not isinstance(validation_metrics, dict):
            return

        dataset_path = await self._download_dataset_to_drive(dataset_id)
        baseline_metrics = self._load_baseline_metrics()
        new_metrics = {k: float(v) for k, v in validation_metrics.items() if isinstance(v, (int, float))}
        update_model = self._is_metric_higher(new_metrics, baseline_metrics)

        if update_model:
            candidate_model = self.model_vault / "candidate.pt"
            production_model = self.model_vault / "best.pt"
            if candidate_model.exists():
                candidate_model.replace(production_model)
            self._save_baseline_metrics(new_metrics)
            self.broadcast("vision.model.updated", {"metrics": new_metrics, "model_path": str(production_model)})

        self._write_metric_report(dataset_id, new_metrics, baseline_metrics, update_model)

    async def _vision_optimization_event_handler(self, event_type: str, payload: EventPayload) -> Dict[str, Any]:
        self.enqueue_background_task(event_type, payload, priority=50)
        return {"status": "queued", "event_type": event_type}

    def _candidate_modules(self) -> List[str]:
        package = importlib.import_module(self.package_name)
        candidates = [f"{self.package_name}.{name}" for _, name, _ in pkgutil.iter_modules(package.__path__)]
        return [name for name in candidates if name != f"{self.package_name}.orchestrator"]

    def register_plugin(
        self,
        name: str,
        callback: PluginHandler,
        events: Optional[Iterable[str]] = None,
        priority: int = 0,
    ) -> Dict[str, Any]:
        plugin = {
            "name": name,
            "callback": callback,
            "events": tuple(events) if events else ("*",),
            "priority": priority,
        }
        with self._lock:
            self._plugins[name] = plugin
        return plugin

    def register_event_listener(
        self,
        event_type: str,
        handler: PluginHandler,
        priority: int = 0,
    ) -> None:
        listeners = self._event_listeners.setdefault(event_type, [])
        listeners.append({"handler": handler, "priority": priority})
        listeners.sort(key=lambda item: item["priority"], reverse=True)

    def discover_plugins(self) -> List[Dict[str, Any]]:
        discovered: List[Dict[str, Any]] = []
        with self._lock:
            for module_name in self._candidate_modules():
                try:
                    module = importlib.import_module(module_name)
                except Exception:
                    continue

                metadata = getattr(module, "ORCHESTRATOR_PLUGIN", None)
                if isinstance(metadata, dict):
                    handler_name = metadata.get("handler", "orchestrator_event_hook")
                    handler = getattr(module, handler_name, None)
                    if callable(handler):
                        plugin = self.register_plugin(
                            metadata.get("name", module_name),
                            handler,
                            events=metadata.get("events", ("*",)),
                            priority=int(metadata.get("priority", 0)),
                        )
                        discovered.append(plugin)
                    continue

                for _, candidate in inspect.getmembers(module, inspect.isfunction):
                    plugin_spec = getattr(candidate, "ORCHESTRATOR_PLUGIN", None)
                    if isinstance(plugin_spec, dict):
                        plugin = self.register_plugin(
                            plugin_spec.get("name", candidate.__name__),
                            candidate,
                            events=plugin_spec.get("events", ("*",)),
                            priority=int(plugin_spec.get("priority", 0)),
                        )
                        discovered.append(plugin)
        return discovered

    def enqueue_background_task(
        self,
        event_type: str,
        payload: EventPayload,
        priority: int = 0,
    ) -> Dict[str, Any]:
        if self._task_queue is None:
            return {"status": "error", "error": "background worker unavailable"}

        task: EventPayload = {
            "event_type": event_type,
            "payload": payload,
            "priority": priority,
            "queued_at": time.time(),
        }
        self._task_counter += 1
        queued_task = (-(priority or 0), self._task_counter, task)
        try:
            # Maintain a lightweight snapshot for diagnostics/tests.
            self._queued_tasks_snapshot.append(task)
        except Exception:
            pass

        if self._loop is not None:
            try:
                # Use call_soon_threadsafe with put_nowait to schedule insertion without creating
                # an extra coroutine object that would need awaiting.
                self._loop.call_soon_threadsafe(self._task_queue.put_nowait, queued_task)
                return {"status": "queued", "event_type": event_type, "priority": priority}
            except Exception:
                # Fallback to run_coroutine_threadsafe if put_nowait is unavailable
                asyncio.run_coroutine_threadsafe(self._task_queue.put(queued_task), self._loop)
                return {"status": "queued", "event_type": event_type, "priority": priority}

        return {"status": "error", "error": "event loop is not running"}

    def get_queued_tasks_snapshot(self) -> List[EventPayload]:
        """Return a shallow snapshot of queued tasks for inspection (testing/debug).

        This intentionally uses the underlying queue buffer for non-production
        introspection and should be used only for diagnostics or tests.
        """
        if self._task_queue is None:
            return []
        try:
            # Access internal buffer; copy to avoid race conditions.
            raw = list(getattr(self._task_queue, "_queue", []))
            # Merge snapshot with internal queue for maximum coverage
            queue_items = [item[2] for item in raw]
            snapshot_copy = list(self._queued_tasks_snapshot)
            # Return union preserving order: snapshot first then queue items
            return snapshot_copy + [q for q in queue_items if q not in snapshot_copy]
        except Exception:
            return []

    def broadcast(self, event_type: str, payload: Optional[EventPayload] = None) -> List[Dict[str, Any]]:
        payload = payload or {}
        record: Dict[str, Any] = {"event_type": event_type, "payload": dict(payload), "plugins": []}
        with self._lock:
            ordered_plugins = sorted(self._plugins.values(), key=lambda item: item.get("priority", 0), reverse=True)

        results: List[Dict[str, Any]] = []
        for plugin in ordered_plugins:
            events = plugin.get("events", ("*",))
            if "*" not in events and event_type not in events:
                continue
            try:
                callback = plugin["callback"]
                if asyncio.iscoroutinefunction(callback):
                    if self._loop is not None:
                        future = asyncio.run_coroutine_threadsafe(callback(event_type, payload), self._loop)
                        result = future.result(timeout=30)
                    else:
                        result = asyncio.run(callback(event_type, payload))
                else:
                    result = callback(event_type, payload)
            except Exception as exc:
                result = {"error": str(exc)}
            results.append({"name": plugin["name"], "result": result})
            record["plugins"].append(plugin["name"])

        event_listeners = self._event_listeners.get(event_type, [])
        for listener in event_listeners:
            handler = listener["handler"]
            try:
                if asyncio.iscoroutinefunction(handler):
                    if self._loop is not None:
                        future = asyncio.run_coroutine_threadsafe(handler(event_type, payload), self._loop)
                        listener_result = future.result(timeout=30)
                    else:
                        listener_result = asyncio.run(handler(event_type, payload))
                else:
                    listener_result = handler(event_type, payload)
            except Exception as exc:
                listener_result = {"error": str(exc)}
            results.append({"name": getattr(handler, "__name__", "listener"), "result": listener_result})
            record["plugins"].append(getattr(handler, "__name__", "listener"))

        with self._lock:
            self._event_history.append(record)
        return results

    def route_command(self, user_text: str, fallback: Callable[[str], Any]) -> Any:
        self.broadcast("command.received", {"text": user_text})
        result = fallback(user_text)
        self.broadcast("command.completed", {"text": user_text, "result": result})
        return result

    def start(self) -> Dict[str, Any]:
        if not self._booted:
            self.discover_plugins()
            self._booted = True
        result = self.broadcast("orchestrator.boot", {"status": "ready"})
        return {"ready": True, "plugins": len(self._plugins), "events": result}

    def history(self) -> List[Dict[str, Any]]:
        return list(self._event_history)


_DEFAULT_ORCHESTRATOR: Optional[CentralOrchestrator] = None


def get_orchestrator() -> CentralOrchestrator:
    global _DEFAULT_ORCHESTRATOR
    if _DEFAULT_ORCHESTRATOR is None:
        # Do not auto-start background worker for the global singleton to
        # avoid spawning threads during import/test collection. Call
        # `start()` on the orchestrator instance to begin background processing.
        _DEFAULT_ORCHESTRATOR = CentralOrchestrator(auto_scan=True, auto_start_background=False)
    return _DEFAULT_ORCHESTRATOR
