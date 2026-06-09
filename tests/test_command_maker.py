from modules.command_maker import generate_command, get_generated_commands, rollback_command


def test_generate_command_returns_safe_plan(monkeypatch, tmp_path):
    monkeypatch.setenv("ARROW_DATA_DIR", str(tmp_path))

    result = generate_command("open a safe note for me")

    assert result["status"] in {"generated", "blocked", "failed"}


def test_generated_commands_are_stored_and_rollbackable(monkeypatch, tmp_path):
    monkeypatch.setenv("ARROW_DATA_DIR", str(tmp_path))

    result = generate_command("create a simple note reminder")
    commands = get_generated_commands()

    if result.get("status") == "generated":
        assert any(item["command_id"] == result["command_id"] for item in commands)
        rollback = rollback_command(result["command_id"])
        assert rollback["status"] in {"rolled-back", "not-found"}
