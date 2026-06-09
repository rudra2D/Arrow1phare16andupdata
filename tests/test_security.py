from modules.security import SecurityManager, is_panic_command


def test_panic_command_is_detected():
    assert is_panic_command("/panic") is True
    assert is_panic_command("please panic now") is True


def test_security_manager_triggers_secure_panic_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("ARROW_DATA_DIR", str(tmp_path))

    manager = SecurityManager(pin="4242", idle_timeout_seconds=1)
    result = manager.trigger_panic("test panic")

    assert result["panic_active"] is True
    assert manager.is_locked() is True
    assert "secure" in result["message"].lower()


def test_security_manager_unlocks_with_pin_and_records_session_snapshot(tmp_path, monkeypatch):
    monkeypatch.setenv("ARROW_DATA_DIR", str(tmp_path))

    manager = SecurityManager(pin="4242", idle_timeout_seconds=1)
    manager.trigger_panic("session snapshot")

    assert manager.unlock("4242") is True
    assert manager.is_locked() is False
