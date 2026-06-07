"""Generate and run Python code produced by Gemini in a controlled sandbox.

This module writes code into `arrow_data/generated/` and executes it either
foreground (capture stdout/stderr) or background (log to files). It strictly
ensures files are written only under the generated directory to avoid path
traversal vulnerabilities.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Dict, Optional

GENERATED_DIR = Path("arrow_data/generated")
LOG_DIR = GENERATED_DIR / "logs"
GENERATED_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)


def _safe_filename(name: Optional[str]) -> str:
    """Create a safe filename under the generated directory.

    Removes path separators and keeps only alphanumerics, hyphen and underscore.
    Falls back to a timestamped name.
    """
    import time

    if not name:
        return f"generated_{int(time.time())}.py"
    base = Path(name).name
    base = re.sub(r"[^0-9A-Za-z._-]", "_", base)
    if not base.lower().endswith(".py"):
        base = base + ".py"
    return base


def write_code(code: str, filename_hint: Optional[str] = None) -> Path:
    """Write `code` into a new file under `arrow_data/generated/` and return path.

    This function prevents path traversal and always writes inside the sandbox.
    """
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    filename = _safe_filename(filename_hint)
    full = GENERATED_DIR / filename
    # Ensure we stay in the directory
    full = full.resolve()
    if GENERATED_DIR.resolve() not in full.parents and full != GENERATED_DIR.resolve():
        raise PermissionError("Invalid generated filename")

    with open(full, "w", encoding="utf-8") as f:
        f.write(code)

    # Make executable by owner if possible
    try:
        os.chmod(full, 0o700)
    except Exception:
        pass

    return full


def run_generated(
    code: str,
    filename_hint: Optional[str] = None,
    timeout: Optional[float] = 30.0,
    background: bool = False,
) -> Dict[str, Optional[str]]:
    """Write and execute generated Python code.

    If `background` is True the process is started detached and stdout/stderr are
    written to log files under `arrow_data/generated/logs/` and a dictionary
    with `pid` and `log_paths` is returned. If False the function waits up to
    `timeout` seconds for the process to finish and returns captured output.
    """
    path = write_code(code, filename_hint)
    python_exe = os.environ.get("PYTHON_EXECUTABLE", "python3")

    if background:
        stdout_log = LOG_DIR / (path.stem + ".out.log")
        stderr_log = LOG_DIR / (path.stem + ".err.log")
        # Start process detached with redirected logs
        with open(stdout_log, "ab") as out_f, open(stderr_log, "ab") as err_f:
            proc = subprocess.Popen(
                [python_exe, str(path)],
                stdout=out_f,
                stderr=err_f,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )

        return {
            "status": "started",
            "pid": str(proc.pid),
            "stdout_log": str(stdout_log),
            "stderr_log": str(stderr_log),
            "file": str(path),
        }

    # Foreground execution with capture
    try:
        proc = subprocess.Popen(
            [python_exe, str(path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            text=True,
        )
        out, err = proc.communicate(timeout=timeout)
        return {
            "status": "finished",
            "returncode": str(proc.returncode),
            "stdout": out,
            "stderr": err,
            "file": str(path),
        }
    except subprocess.TimeoutExpired:
        proc.kill()
        out, err = proc.communicate()
        return {
            "status": "timeout",
            "returncode": str(proc.returncode),
            "stdout": out,
            "stderr": err,
            "file": str(path),
        }
    except Exception as exc:
        return {"status": "error", "error": str(exc), "file": str(path)}


__all__ = ["write_code", "run_generated", "GENERATED_DIR", "LOG_DIR"]
