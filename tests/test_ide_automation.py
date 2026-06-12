"""Tests for Phase 10 IDE automation and workspace orchestration."""

import io
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from modules import ide_automation as ia


def test_open_ide_workspace_invalid_directory():
    result = ia.open_ide_workspace("nonexistent_workspace", ide_name="vscode")

    assert result["status"] == "error"
    assert "workspace path is not a valid directory" in result["error"]


def test_open_ide_workspace_missing_binary(tmp_path, monkeypatch):
    monkeypatch.setattr(ia, "WORKSPACE_ROOT", tmp_path)
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()

    with patch.object(ia, "_find_executable", return_value=None):
        result = ia.open_ide_workspace(workspace_dir, ide_name="vscode")

    assert result["status"] == "missing_binary"
    assert "IDE executable not found" in result["error"]


def test_open_ide_workspace_launch_success(tmp_path, monkeypatch):
    monkeypatch.setattr(ia, "WORKSPACE_ROOT", tmp_path)
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()

    fake_process = MagicMock()
    fake_process.pid = 1234
    fake_process.returncode = 0
    fake_process.communicate.return_value = ("", "")
    fake_popen = MagicMock(return_value=fake_process)

    with patch.object(ia, "_build_ide_command", return_value=["code", str(workspace_dir)]), \
            patch("modules.ide_automation.subprocess.Popen", fake_popen):
        result = ia.open_ide_workspace(workspace_dir, ide_name="vscode")

    assert result["status"] == "launched"
    assert result["pid"] == 1234
    assert result["workspace_path"] == str(workspace_dir)
    fake_popen.assert_called_once()


def test_programmatic_code_injection_create_and_append(tmp_path, monkeypatch):
    monkeypatch.setattr(ia, "WORKSPACE_ROOT", tmp_path)
    target_file = tmp_path / "code.py"

    first = ia.programmatic_code_injection("code.py", "print('hello')")
    assert first["status"] == "created"
    assert target_file.exists()
    assert target_file.read_text().strip() == "print('hello')"

    second = ia.programmatic_code_injection("code.py", "print('goodbye')")
    assert second["status"] == "updated"
    assert "print('goodbye')" in target_file.read_text()


def test_execute_workspace_suite_success():
    command = [sys.executable, "-c", "print('ok')"]
    result = ia.execute_workspace_suite(command)

    assert result["status"] == "success"
    assert "ok" in result["stdout"]
    assert result["returncode"] == 0


def test_execute_workspace_suite_timeout(monkeypatch):
    command = [sys.executable, "-c", "import time; time.sleep(5)"]
    monkeypatch.setattr(ia, "DEFAULT_COMMAND_TIMEOUT_SECONDS", 1)

    result = ia.execute_workspace_suite(command)

    assert result["status"] == "timeout"
    assert result["timeout_seconds"] == 1


def test_trace_syntax_exceptions_parses_python_error():
    stderr = (
        "Traceback (most recent call last):\n"
        "  File \"/tmp/test.py\", line 2, in <module>\n"
        "    print(unknown_variable)\n"
        "NameError: name 'unknown_variable' is not defined\n"
    )

    errors = ia.trace_syntax_exceptions(stderr)

    assert len(errors) == 1
    assert errors[0]["file"] == "/tmp/test.py"
    assert errors[0]["line"] == 2
    assert errors[0]["error_type"] == "NameError"
    assert "unknown_variable" in errors[0]["message"]


def test_orchestrator_event_hook_compile_requests_execution():
    fake_result = {"status": "success", "stdout": "ok", "stderr": ""}
    with patch.object(ia, "execute_workspace_suite", return_value=fake_result) as mock_suite:
        payload = {"command": "pytest -q"}
        result = ia.orchestrator_event_hook("ide.compile.request", payload)

    assert result["status"] == "compiled"
    assert result["event_type"] == "ide.compile.request"
    assert result["result"] == fake_result
    mock_suite.assert_called_once_with("pytest -q")


def test_orchestrator_event_hook_debug_triggers_ide():
    debug_response = {"status": "launched", "workspace_path": "/tmp"}
    with patch.object(ia, "open_ide_workspace", return_value=debug_response) as mock_open:
        payload = {"workspace_path": "/tmp", "ide_name": "vscode"}
        result = ia.orchestrator_event_hook("ide.debug.trigger", payload)

    assert result["status"] == "debugging"
    assert result["event_type"] == "ide.debug.trigger"
    assert result["result"] == debug_response
    mock_open.assert_called_once_with("/tmp", "vscode")
