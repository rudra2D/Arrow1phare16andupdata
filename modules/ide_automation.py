"""Phase 10: IDE Workspace & Coding Automation Core.

This module provides IDE workspace launch control, programmatic code injection,
workspace suite execution, syntax exception tracing, and Phase 14 orchestrator
connectivity for development events.
"""

from __future__ import annotations

import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from queue import Queue, Empty
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

ORCHESTRATOR_PLUGIN = {
    "name": "ide_automation",
    "handler": "orchestrator_event_hook",
    "events": ("ide.compile.request", "ide.debug.trigger"),
    "priority": 12,
}

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COMMAND_TIMEOUT_SECONDS = 30
LINE_BUFFER_WAIT_SECONDS = 0.1

IDE_COMMAND_MAP = {
    "vscode": ["code"],
    "androidstudio": ["studio.sh", "android-studio", "studio"],
    "pycharm": ["pycharm", "pycharm.sh"],
    "intellij": ["idea", "idea.sh"],
    "webstorm": ["webstorm", "webstorm.sh"],
    "goland": ["goland", "goland.sh"],
}


def _resolve_workspace_path(workspace_path: Union[str, Path]) -> Path:
    path = Path(workspace_path)
    if not path.is_absolute():
        path = WORKSPACE_ROOT / path
    try:
        resolved = path.resolve(strict=False)
    except Exception:
        resolved = path
    if not str(resolved).startswith(str(WORKSPACE_ROOT)):
        raise ValueError("Workspace path must remain inside the Arrow repository root")
    return resolved


def _find_executable(candidate: str) -> Optional[str]:
    if shutil.which(candidate):
        return candidate
    if platform.system() == "Windows":
        return shutil.which(candidate + ".exe")
    return None


def _build_ide_command(workspace_path: Path, ide_name: str) -> List[str]:
    normalized = ide_name.strip().lower()
    candidates = IDE_COMMAND_MAP.get(normalized, [normalized])
    for candidate in candidates:
        executable = _find_executable(candidate)
        if executable:
            return [executable, str(workspace_path)]
    raise FileNotFoundError(f"IDE executable not found for {ide_name}")


def open_ide_workspace(workspace_path: Union[str, Path], ide_name: str = "vscode") -> Dict[str, Any]:
    try:
        target = _resolve_workspace_path(workspace_path)
    except ValueError as exc:
        return {"status": "error", "error": str(exc), "workspace_path": str(workspace_path)}

    if not target.exists() or not target.is_dir():
        return {
            "status": "error",
            "error": "workspace path is not a valid directory",
            "workspace_path": str(target),
        }

    try:
        command = _build_ide_command(target, ide_name)
    except FileNotFoundError as exc:
        return {"status": "missing_binary", "error": str(exc), "ide_name": ide_name}

    try:
        process = subprocess.Popen(
            command,
            cwd=str(target),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            _, stderr = process.communicate(timeout=5)
            if process.returncode not in (0, None):
                return {
                    "status": "error",
                    "error": stderr.strip() or "IDE process exited with non-zero code",
                    "returncode": process.returncode,
                    "command": command,
                }
        except subprocess.TimeoutExpired:
            return {
                "status": "launched",
                "command": command,
                "pid": process.pid,
                "workspace_path": str(target),
            }

        return {"status": "launched", "command": command, "pid": process.pid, "workspace_path": str(target)}
    except FileNotFoundError as exc:
        return {"status": "missing_binary", "error": str(exc), "ide_name": ide_name}
    except Exception as exc:
        return {"status": "error", "error": str(exc), "command": locals().get("command")}


def programmatic_code_injection(file_path: Union[str, Path], code_content: str) -> Dict[str, Any]:
    try:
        target = _resolve_workspace_path(file_path)
    except ValueError as exc:
        return {"status": "error", "error": str(exc), "file_path": str(file_path)}

    if target.exists() and target.is_dir():
        return {"status": "error", "error": "target path is an existing directory", "file_path": str(target)}

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            existing = target.read_text(encoding="utf-8")
            if code_content.strip() in existing:
                return {"status": "unchanged", "file_path": str(target)}
            updated = existing.rstrip() + "\n\n" + code_content.lstrip()
            target.write_text(updated, encoding="utf-8")
            return {"status": "updated", "file_path": str(target), "action": "appended"}
        target.write_text(code_content.strip() + "\n", encoding="utf-8")
        return {"status": "created", "file_path": str(target), "action": "written"}
    except Exception as exc:
        return {"status": "error", "error": str(exc), "file_path": str(target)}


def _drain_stream(stream: Any, queue: Queue) -> None:
    try:
        for line in iter(stream.readline, ""):
            queue.put(line)
    finally:
        stream.close()


def execute_workspace_suite(run_command: Union[str, Iterable[str]]) -> Dict[str, Any]:
    if isinstance(run_command, str):
        try:
            command = shlex.split(run_command)
        except Exception:
            command = [run_command]
    else:
        command = [str(part) for part in run_command]

    if not command:
        return {"status": "error", "error": "empty run command"}

    executable = _find_executable(command[0])
    if executable is None:
        return {"status": "missing_binary", "error": f"binary not found: {command[0]}", "command": command}
    command[0] = executable

    stdout_queue: Queue[str] = Queue()
    stderr_queue: Queue[str] = Queue()
    stdout_lines: List[str] = []
    stderr_lines: List[str] = []

    try:
        process = subprocess.Popen(
            command,
            cwd=str(WORKSPACE_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except FileNotFoundError as exc:
        return {"status": "missing_binary", "error": str(exc), "command": command}
    except Exception as exc:
        return {"status": "error", "error": str(exc), "command": command}

    stdout_thread = threading.Thread(target=_drain_stream, args=(process.stdout, stdout_queue), daemon=True)
    stderr_thread = threading.Thread(target=_drain_stream, args=(process.stderr, stderr_queue), daemon=True)
    stdout_thread.start()
    stderr_thread.start()

    deadline = time.time() + DEFAULT_COMMAND_TIMEOUT_SECONDS
    try:
        while process.poll() is None:
            try:
                stdout_lines.append(stdout_queue.get(timeout=LINE_BUFFER_WAIT_SECONDS))
            except Empty:
                pass
            try:
                stderr_lines.append(stderr_queue.get(timeout=LINE_BUFFER_WAIT_SECONDS))
            except Empty:
                pass
            if time.time() > deadline:
                process.kill()
                return {
                    "status": "timeout",
                    "command": command,
                    "stdout": "".join(stdout_lines).strip(),
                    "stderr": "".join(stderr_lines).strip(),
                    "timeout_seconds": DEFAULT_COMMAND_TIMEOUT_SECONDS,
                }

        while True:
            try:
                stdout_lines.append(stdout_queue.get_nowait())
            except Empty:
                break
        while True:
            try:
                stderr_lines.append(stderr_queue.get_nowait())
            except Empty:
                break

        return {
            "status": "success" if process.returncode == 0 else "failed",
            "command": command,
            "returncode": process.returncode,
            "stdout": "".join(stdout_lines).strip(),
            "stderr": "".join(stderr_lines).strip(),
        }
    except Exception as exc:
        process.kill()
        return {"status": "error", "error": str(exc), "command": command}


def trace_syntax_exceptions(stderr_output: str) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    if not stderr_output:
        return results

    python_traceback = re.compile(r"^  File \"(?P<file>.+?)\", line (?P<line>\d+), in .+?\n(?P<code>.+?)\n(?P<error>.+Error: .+)$", re.MULTILINE)
    generic_error = re.compile(r"^(?P<file>.+?):(?P<line>\d+):(?:(?P<column>\d+):)?\s*(?P<error_type>[^:]+):\s*(?P<message>.+)$", re.MULTILINE)

    for match in python_traceback.finditer(stderr_output):
        error_text = match.group("error").strip()
        error_type, _, message = error_text.partition(":")
        results.append({
            "file": match.group("file"),
            "line": int(match.group("line")),
            "error_type": error_type.strip(),
            "message": message.strip(),
        })

    for match in generic_error.finditer(stderr_output):
        if any(r["file"] == match.group("file") and r["line"] == int(match.group("line")) for r in results):
            continue
        results.append({
            "file": match.group("file"),
            "line": int(match.group("line")),
            "error_type": match.group("error_type").strip(),
            "message": match.group("message").strip(),
        })

    return results


def orchestrator_event_hook(event_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        if event_type == "ide.compile.request":
            command = payload.get("command", "pytest -q")
            result = execute_workspace_suite(command)
            if result.get("stderr"):
                result["errors"] = trace_syntax_exceptions(result.get("stderr", ""))
            return {"status": "compiled", "event_type": event_type, "result": result}

        if event_type == "ide.debug.trigger":
            workspace_path = payload.get("workspace_path", ".")
            ide_name = payload.get("ide_name", "vscode")
            debug_result = open_ide_workspace(workspace_path, ide_name)
            return {"status": "debugging", "event_type": event_type, "result": debug_result}

        return {"status": "ignored", "event_type": event_type}
    except Exception as exc:
        return {"status": "error", "error": str(exc), "event_type": event_type}
