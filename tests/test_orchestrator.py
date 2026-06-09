from modules.orchestrator import UniversalOrchestrator, get_orchestrator


def test_orchestrator_discovers_builtin_plugins():
    orchestrator = UniversalOrchestrator(auto_scan=True)
    plugins = orchestrator.discover_plugins()

    names = {plugin["name"] for plugin in plugins}
    assert "memory" in names or "security" in names or "telegram" in names


def test_orchestrator_broadcasts_events_to_registered_handlers():
    orchestrator = UniversalOrchestrator(auto_scan=False)

    seen = []

    def test_handler(event_type, payload):
        seen.append((event_type, payload))

    orchestrator.register_plugin("test_hook", test_handler, events={"phase14.test"})
    orchestrator.broadcast("phase14.test", {"value": 1})

    assert seen == [("phase14.test", {"value": 1})]


def test_get_orchestrator_returns_singleton():
    first = get_orchestrator()
    second = get_orchestrator()

    assert first is second
