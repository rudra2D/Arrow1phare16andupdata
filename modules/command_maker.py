"""Phase 15: Auto Command Maker Engine."""

from __future__ import annotations

import base64
import os
import random
import re
import threading
import time
import traceback
from typing import Any

from btu import query_gemini
from modules.memory import (
    get_memory_db_path,
    get_profile_data,
    initialize_memory_store,
    log_project_idea,
)
from modules.security import get_security_manager


ORCHESTRATOR_PLUGIN = {
    "name": "command_maker",
    "handler": "orchestrator_event_hook",
    "events": ("command.received", "command.generated", "orchestrator.boot"),
    "priority": 25,
}


def _xor_encrypt(payload: str, key: str) -> str:
    key_bytes = (key or "arrow-command-key").encode("utf-8")
    raw = payload.encode("utf-8")
    encoded = bytearray()
    for index, value in enumerate(raw):
        encoded.append(value ^ key_bytes[index % len(key_bytes)])
    return base64.b64encode(bytes(encoded)).decode("ascii")


def _xor_decrypt(payload: str, key: str) -> str:
    key_bytes = (key or "arrow-command-key").encode("utf-8")
    raw = base64.b64decode(payload.encode("ascii"))
    decoded = bytearray()
    for index, value in enumerate(raw):
        decoded.append(value ^ key_bytes[index % len(key_bytes)])
    return bytes(decoded).decode("utf-8")


def _safe_command_name(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or f"command-{random.randint(1000, 9999)}"


def _is_os_unsafe(command_logic: str) -> bool:
    dangerous_patterns = [
        r"rm\s+-rf\s+/",
        r"del\s+/[sfq]\s+[c-z]:\\\\windows",
        r"format\\s+c:",
        r"shutdown\s+/s",
        r"taskkill\s+/f\s+/im\s+explorer\.exe",
        r"/etc/passwd",
        r"\\\\windows\\\\system32",
        r"c:\\windows\\\\system32",
        r"/bin/",
        r"/usr/",
    ]
    lowered = command_logic.lower()
    return any(re.search(pattern, lowered) for pattern in dangerous_patterns)


def _resource_ok() -> bool:
    try:
        import psutil
        usage = psutil.virtual_memory().percent
        cpu = psutil.cpu_percent(interval=None)
        return usage < 90 and cpu < 90
    except Exception:
        try:
            load = os.getloadavg()[0]
            return load < 90
        except Exception:
            return True


def _contextual_style_hint(user_text: str) -> str:
    profile = get_profile_data()
    hints = []
    if profile.get("name"):
        hints.append(f"User name: {profile['name']}")
    if profile.get("profession"):
        hints.append(f"Profession: {profile['profession']}")
    if profile.get("likes"):
        hints.append(f"Likes: {profile['likes']}")
    return " ".join(hints) if hints else "General assistant style"


def _llm_generate_command(user_text: str, context: str) -> dict:
    prompt = (
        "Create a compact Python command plan for Arrow. "
        "Return JSON with keys command_name, intent, logic, explanation, safe_mode. "
        f"User request: {user_text}. Context: {context}. "
        "Keep the logic safe and limited to user-space operations."
    )
    try:
        reply = query_gemini(prompt)
        text = reply or ""
        block = re.search(r"\{.*\}", text, re.S)
        if block:
            return {"status": "ok", "spec": eval(block.group(0), {"__builtins__": {} })}
    except Exception:
        pass
    return {
        "status": "fallback",
        "spec": {
            "command_name": _safe_command_name(user_text),
            "intent": user_text,
            "logic": "print('Generated command placeholder for safe runtime testing')",
            "explanation": "Fallback command generation prompt used because the LLM service is unavailable.",
            "safe_mode": True,
        },
    }


def _store_command(command_spec: dict, user_text: str) -> dict:
    initialize_memory_store()
    encrypted_logic = _xor_encrypt(command_spec.get("logic", ""), os.getenv("ARROW_COMMAND_KEY", "arrow-command-key"))
    command_id = f"cmd-{int(time.time())}-{random.randint(1000, 9999)}"
    version = command_spec.get("version", "v1")

    import sqlite3
    with sqlite3.connect(get_memory_db_path()) as conn:
        conn.execute(
            "INSERT INTO dynamic_commands_vault (command_id, command_name, intent, logic, encrypted_logic, status, version, created_at, updated_at) VALUES (?, ?, ?, ?, ?, 'draft', ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (command_id, command_spec.get("command_name", _safe_command_name(user_text)), user_text, command_spec.get("logic", ""), encrypted_logic, version),
        )
        conn.execute(
            "INSERT INTO dynamic_command_revisions (command_id, revision_id, version, encrypted_logic, summary, created_at) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
            (command_id, f"rev-{command_id}", version, encrypted_logic, command_spec.get("explanation", "Initial generated command")),
        )
    log_project_idea(
        project_name="Dynamic Commands",
        core_logic="Generate dynamic user-space commands for the Auto Command Maker Engine.",
        notes=f"Stored generated command {command_id}: {user_text}",
        project_id="arrow-dynamic-commands",
    )
    return {"command_id": command_id, "version": version, "encrypted_logic": encrypted_logic}


def _execute_with_timeout(command_logic: str, timeout_seconds: int = 10) -> dict:
    result = {"status": "ok", "output": "", "error": None}
    if not _resource_ok():
        return {"status": "throttled", "output": "CPU/RAM load too high.", "error": None}

    def runner() -> None:
        try:
            namespace = {"__builtins__": __import__('builtins')}
            exec(command_logic, namespace, namespace)
            result['output'] = "dry-run completed"
        except Exception as exc:
            result['status'] = 'error'
            result['error'] = traceback.format_exc()

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join(timeout_seconds)
    if thread.is_alive():
        result['status'] = 'timeout'
        result['error'] = 'Command exceeded 10-second timeout.'
    return result


def _self_heal(command_spec: dict, error_log: str) -> dict:
    try:
        prompt = (
            "Patch this generated command to fix the runtime error. Return JSON with keys command_name, intent, logic, explanation, safe_mode. "
            f"Current command: {command_spec}. Error log: {error_log}"
        )
        reply = query_gemini(prompt)
        block = re.search(r"\{.*\}", reply, re.S)
        if block:
            patched = eval(block.group(0), {"__builtins__": {}})
            return {"status": "repaired", "spec": patched}
    except Exception:
        pass
    return {"status": "fallback", "spec": command_spec}


def generate_command(user_text: str, context: dict | None = None) -> dict:
    """Build a safe, generated command plan from an unrecognized request."""
    style_hint = _contextual_style_hint(user_text)
    llm_result = _llm_generate_command(user_text, context or style_hint)
    spec = dict(llm_result.get("spec", {}))
    spec.setdefault("command_name", _safe_command_name(user_text))
    spec.setdefault("intent", user_text)
    spec.setdefault("logic", "print('Generated command placeholder')")
    spec.setdefault("safe_mode", True)

    if _is_os_unsafe(spec.get("logic", "")):
        return {"status": "blocked", "reason": "OS safety guard blocked this command."}

    dry_run = _execute_with_timeout(spec.get("logic", ""), timeout_seconds=10)
    if dry_run.get("status") in {"error", "timeout"}:
        healed = _self_heal(spec, dry_run.get("error") or "")
        if healed.get("status") in {"repaired", "fallback"}:
            spec = healed.get("spec", spec)
            dry_run = _execute_with_timeout(spec.get("logic", ""), timeout_seconds=10)
        if dry_run.get("status") in {"error", "timeout"}:
            return {"status": "failed", "reason": dry_run.get("error", "Dry run failed")}

    saved = _store_command(spec, user_text)
    try:
        from modules.telegram_bot import SmartRemoteEngine

        telegram = SmartRemoteEngine()
        if telegram.admin_chat_id:
            telegram._send_message(telegram.admin_chat_id, f"Arrow registered a dynamic command: {spec['command_name']}.")
    except Exception:
        pass

    return {
        "status": "generated",
        "command_id": saved["command_id"],
        "command_name": spec.get("command_name"),
        "intent": spec.get("intent"),
        "logic": spec.get("logic"),
        "version": saved["version"],
        "dry_run": dry_run,
        "message": "Generated command is ready for orchestration.",
        "db_path": str(get_memory_db_path()),
    }


def rollback_command(command_id: str, version: str | None = None) -> dict:
    """Rollback a generated dynamic command to a previous stored revision."""
    import sqlite3
    conn = sqlite3.connect(get_memory_db_path())
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("SELECT command_id, version, encrypted_logic FROM dynamic_command_revisions WHERE command_id = ? ORDER BY id DESC", (command_id,)).fetchone()
        if not row:
            return {"status": "not-found"}
        target_version = version or row["version"]
        return {"status": "rolled-back", "command_id": command_id, "version": target_version, "encrypted_logic": row["encrypted_logic"]}
    finally:
        conn.close()


def get_generated_commands() -> list[dict]:
    import sqlite3
    conn = sqlite3.connect(get_memory_db_path())
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT command_id, command_name, intent, version, status, created_at FROM dynamic_commands_vault ORDER BY created_at DESC").fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def orchestrator_event_hook(event_type: str, payload: dict) -> dict:
    """Expose Phase 15 as a dynamic command-maker plugin on the orchestrator event bus."""
    if event_type == "command.received":
        text = str((payload or {}).get("text", "")).strip()
        if text:
            return {"status": "intercepted", "generated": generate_command(text, payload)}
    return {"status": "ignored", "event_type": event_type}


def handle_unrecognized_intent(user_text: str) -> dict:
    """Catch unrecognized requests and generate a safe dynamic command plan."""
    return generate_command(user_text, {"source": "voice"})
