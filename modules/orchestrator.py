"""Phase 14: Universal Orchestrator & Future-Proof Engine."""

from __future__ import annotations

import importlib
import inspect
import pkgutil
import threading
from typing import Callable, Dict, Iterable

import modules


class UniversalOrchestrator:
    """Auto-discovers plugin hooks and broadcasts phase events across Arrow."""

    def __init__(self, auto_scan: bool = True, package_name: str = "modules") -> None:
        self.package_name = package_name
        self._plugins: dict[str, dict] = {}
        self._event_history: list[dict] = []
        self._lock = threading.RLock()
        self._booted = False
        if auto_scan:
            self.discover_plugins()

    def register_plugin(self, name: str, callback: Callable, events: Iterable[str] | None = None, priority: int = 0) -> dict:
        plugin = {
            "name": name,
            "callback": callback,
            "events": tuple(events) if events else ("*",),
            "priority": priority,
        }
        with self._lock:
            self._plugins[name] = plugin
        return plugin

    def discover_plugins(self) -> list[dict]:
        discovered: list[dict] = []
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
                        registered = self.register_plugin(
                            metadata.get("name", module_name),
                            handler,
                            events=metadata.get("events", ("*",)),
                            priority=int(metadata.get("priority", 0)),
                        )
                        discovered.append(registered)
                    continue

                for _, candidate in inspect.getmembers(module, inspect.isfunction):
                    plugin_spec = getattr(candidate, "ORCHESTRATOR_PLUGIN", None)
                    if isinstance(plugin_spec, dict):
                        registered = self.register_plugin(
                            plugin_spec.get("name", candidate.__name__),
                            candidate,
                            events=plugin_spec.get("events", ("*",)),
                            priority=int(plugin_spec.get("priority", 0)),
                        )
                        discovered.append(registered)

        return discovered

    def _candidate_modules(self) -> list[str]:
        package = importlib.import_module(self.package_name)
        candidates = [f"{self.package_name}.{name}" for _, name, _ in pkgutil.iter_modules(package.__path__)]
        candidates = [name for name in candidates if not name.endswith(".orchestrator")]
        return candidates

    def broadcast(self, event_type: str, payload: dict | None = None) -> list[dict]:
        record = {"event_type": event_type, "payload": dict(payload or {}), "plugins": []}
        with self._lock:
            ordered = sorted(self._plugins.values(), key=lambda item: item.get("priority", 0), reverse=True)

        results: list[dict] = []
        for plugin in ordered:
            events = plugin.get("events", ("*",))
            if "*" not in events and event_type not in events:
                continue
            try:
                result = plugin["callback"](event_type, dict(payload or {}))
            except Exception as exc:
                result = {"error": str(exc)}
            results.append({"name": plugin["name"], "result": result})
            record["plugins"].append(plugin["name"])

        with self._lock:
            self._event_history.append(record)
        return results

    def route_command(self, user_text: str, fallback: Callable[[str], object]) -> object:
        self.broadcast("command.received", {"text": user_text})
        result = fallback(user_text)
        self.broadcast("command.completed", {"text": user_text, "result": result})
        return result

    def start(self) -> dict:
        if not self._booted:
            self.discover_plugins()
            self._booted = True
        result = self.broadcast("orchestrator.boot", {"status": "ready"})
        return {"ready": True, "plugins": len(self._plugins), "events": result}

    def history(self) -> list[dict]:
        return list(self._event_history)


_DEFAULT_ORCHESTRATOR: UniversalOrchestrator | None = None


def get_orchestrator() -> UniversalOrchestrator:
    global _DEFAULT_ORCHESTRATOR
    if _DEFAULT_ORCHESTRATOR is None:
        _DEFAULT_ORCHESTRATOR = UniversalOrchestrator(auto_scan=True)
    return _DEFAULT_ORCHESTRATOR
