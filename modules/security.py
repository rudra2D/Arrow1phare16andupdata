"""Phase 13 security core for Arrow."""

import os
import threading
import time

from modules.memory import get_memory_db_path, initialize_memory_store, log_project_idea


DEFAULT_SECURITY_PIN = os.getenv("ARROW_SECURITY_PIN", "4242")


def is_panic_command(text: str) -> bool:
    lowered = text.lower().strip()
    return lowered in {"/panic", "panic", "panic now", "panic mode"} or "panic" in lowered


def _clear_terminal() -> None:
    try:
        print("\033[2J\033[H", end="", flush=True)
    except Exception:
        pass


ORCHESTRATOR_PLUGIN = {
    "name": "security",
    "handler": "orchestrator_event_hook",
    "events": ("*",),
    "priority": 30,
}


def orchestrator_event_hook(event_type: str, payload: dict) -> dict:
    """React to orchestrator events with the existing security core."""
    manager = get_security_manager()
    manager.mark_activity(event_type)
    return {"status": "observed", "event_type": event_type, "locked": manager.is_locked()}


class SecurityManager:
    """Provides a lightweight security layer for Arrow sessions."""

    def __init__(self, pin: str | None = None, idle_timeout_seconds: int = 300) -> None:
        self.pin = (pin or os.getenv("ARROW_SECURITY_PIN") or DEFAULT_SECURITY_PIN).strip()
        self.idle_timeout_seconds = idle_timeout_seconds
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread = None
        self._last_activity = time.time()
        self._locked = False
        self._panic_active = False
        self._stealth_active = False
        self._session_label = "Arrow Security Session"

    def mark_activity(self, reason: str = "activity") -> None:
        with self._lock:
            self._last_activity = time.time()
            if self._panic_active:
                self._stealth_active = True

    def is_locked(self) -> bool:
        with self._lock:
            return self._locked

    def is_panic_active(self) -> bool:
        with self._lock:
            return self._panic_active

    def _snapshot(self, reason: str) -> dict:
        return {
            "reason": reason,
            "locked": self._locked,
            "panic_active": self._panic_active,
            "stealth_active": self._stealth_active,
            "db_path": str(get_memory_db_path()),
            "last_activity": self._last_activity,
        }

    def _secure_session_snapshot(self, reason: str) -> None:
        try:
            initialize_memory_store()
            snapshot = self._snapshot(reason)
            note_text = (
                f"Security event: {reason}. "
                f"locked={snapshot['locked']}, panic_active={snapshot['panic_active']}, "
                f"stealth_active={snapshot['stealth_active']}"
            )
            log_project_idea(
                project_name="Arrow Secure Session",
                core_logic="Archive the current session state for anti-tamper protection and user-account isolation.",
                notes=note_text,
                project_id="arrow-secure-session",
            )
        except Exception:
            pass

    def trigger_panic(self, reason: str = "manual panic") -> dict:
        with self._lock:
            self._panic_active = True
            self._stealth_active = True
            self._locked = True
            self._last_activity = time.time()
        _clear_terminal()
        self._secure_session_snapshot(reason)
        return {
            "panic_active": True,
            "message": "Arrow entered secure stealth mode. Background activity is paused and the session is locked.",
            "reason": reason,
            "db_path": str(get_memory_db_path()),
        }

    def unlock(self, candidate_pin: str) -> bool:
        if candidate_pin.strip() == self.pin:
            with self._lock:
                self._locked = False
                self._stealth_active = False
                self._last_activity = time.time()
            return True
        return False

    def lock(self, reason: str = "idle timeout") -> dict:
        with self._lock:
            self._locked = True
            self._stealth_active = True
            self._last_activity = time.time()
        self._secure_session_snapshot(reason)
        return {"locked": True, "message": f"Arrow locked for security: {reason}. Enter your PIN to resume.", "reason": reason}

    def record_intrusion_attempt(self, text: str) -> dict:
        self._secure_session_snapshot(f"unauthenticated attempt: {text[:120]}")
        return self.lock(reason="unauthenticated interaction")

    def _monitor(self) -> None:
        while not self._stop_event.is_set():
            time.sleep(1)
            if self._locked or self._panic_active:
                continue
            if time.time() - self._last_activity >= self.idle_timeout_seconds:
                self.lock(reason="idle timeout")

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._monitor, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1)


def get_security_manager(pin: str | None = None, idle_timeout_seconds: int = 300) -> SecurityManager:
    global _DEFAULT_SECURITY_MANAGER
    if _DEFAULT_SECURITY_MANAGER is None:
        _DEFAULT_SECURITY_MANAGER = SecurityManager(pin=pin, idle_timeout_seconds=idle_timeout_seconds)
    return _DEFAULT_SECURITY_MANAGER


_DEFAULT_SECURITY_MANAGER: SecurityManager | None = None
