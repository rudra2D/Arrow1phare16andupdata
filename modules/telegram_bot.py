"""Telegram bot remote control for Arrow."""

import os
import platform
import subprocess
import threading
import time
from typing import Any

import requests

from config import ADMIN_CHAT_ID, TELEGRAM_BOT_TOKEN, TELEGRAM_USER_ID
from btu import query_gemini_with_image
from modules.memory import (
    get_dynamic_command_count,
    get_memory_db_path,
    initialize_memory_store,
    remember_memory,
    remember_visual_objects,
    summarize_user_profile,
)
from modules.orchestrator import get_orchestrator
from modules.security import get_security_manager
from voice_out import speak

API_BASE = "https://api.telegram.org"

ORCHESTRATOR_PLUGIN = {
    "name": "telegram",
    "handler": "orchestrator_event_hook",
    "events": ("*",),
    "priority": 10,
}


def orchestrator_event_hook(event_type: str, payload: dict) -> dict:
    """Notify the Telegram remote interface when the orchestrator emits an event."""
    try:
        engine = SmartRemoteEngine()
        if engine.admin_chat_id and engine.token and engine.token != "YOUR_TELEGRAM_BOT_TOKEN":
            engine._send_message(engine.admin_chat_id, f"Arrow orchestrator event: {event_type}")
            return {"status": "notified", "event_type": event_type}
    except Exception as exc:
        return {"status": "skipped", "error": str(exc)}
    return {"status": "not-configured", "event_type": event_type}


def build_dashboard_report() -> str:
    """Compile a Phase 7 dashboard summary for the admin chat."""
    orchestrator = get_orchestrator()
    phase_status = "ready" if orchestrator.start().get("ready") else "paused"
    plugin_names = sorted(getattr(orchestrator, "_plugins", {}).keys()) or ["none"]
    dynamic_commands = get_dynamic_command_count()
    db_path = get_memory_db_path()
    encryption_health = "ok" if db_path.exists() else "missing"

    lines = [
        "Arrow Smart Dashboard",
        "- Active phases: " + ", ".join(plugin_names),
        "- Phase 14 orchestration: " + phase_status,
        "- Encryption health: " + encryption_health,
        "- Phase 15 dynamic commands: " + str(dynamic_commands),
        "- Memory database: " + str(db_path),
    ]
    return "\n".join(lines)


def send_dashboard_report(chat_id: int | None = None) -> dict:
    """Send the dashboard summary to the configured admin chat and/or the requesting chat."""
    report = build_dashboard_report()
    engine = SmartRemoteEngine()

    if not engine.token or engine.token == "YOUR_TELEGRAM_BOT_TOKEN":
        return {"status": "not-configured", "report": report, "sent_to": []}

    targets = []
    if chat_id is not None:
        targets.append(int(chat_id))
    if engine.admin_chat_id:
        targets.append(int(engine.admin_chat_id))

    unique_targets = list(dict.fromkeys(targets))
    for target in unique_targets:
        engine._send_message(target, report)

    return {"status": "sent", "report": report, "sent_to": unique_targets}


class SmartRemoteEngine:
    def __init__(self) -> None:
        self.token = TELEGRAM_BOT_TOKEN
        self.admin_chat_id = ADMIN_CHAT_ID or TELEGRAM_USER_ID
        self.offset = None
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.started = False

    def _build_url(self, method: str) -> str:
        return f"{API_BASE}/bot{self.token}/{method}"

    def _authorized(self, user_id: int | None, chat_id: int | None) -> bool:
        if not self.admin_chat_id:
            return False
        if chat_id is not None and chat_id == self.admin_chat_id:
            return True
        if user_id is not None and user_id == self.admin_chat_id:
            return True
        return False

    def _get_updates(self) -> list[dict[str, Any]]:
        if not self.token or self.token == "YOUR_TELEGRAM_BOT_TOKEN":
            return []

        params = {"timeout": 30, "allowed_updates": ["message"]}
        if self.offset is not None:
            params["offset"] = self.offset

        response = requests.get(self._build_url("getUpdates"), params=params, timeout=40)
        response.raise_for_status()
        data = response.json()
        if not data.get("ok"):
            return []

        return data.get("result", [])

    def _send_message(self, chat_id: int, text: str) -> None:
        if not self.token or self.token == "YOUR_TELEGRAM_BOT_TOKEN":
            return
        payload = {"chat_id": chat_id, "text": text}
        requests.post(self._build_url("sendMessage"), data=payload, timeout=15)

    def _send_photo(self, chat_id: int, photo_path: str, caption: str | None = None) -> None:
        if not self.token or self.token == "YOUR_TELEGRAM_BOT_TOKEN":
            return
        with open(photo_path, "rb") as photo_file:
            files = {"photo": photo_file}
            data = {"chat_id": chat_id}
            if caption:
                data["caption"] = caption
            requests.post(self._build_url("sendPhoto"), files=files, data=data, timeout=30)

    def _process_message(self, message: dict[str, Any]) -> None:
        from_user = message.get("from") or {}
        user_id = from_user.get("id")
        chat = message.get("chat") or {}
        chat_id = chat.get("id")
        text = (message.get("text") or "").strip()

        if user_id is None or chat_id is None or not text:
            return

        if not self._authorized(user_id, chat_id):
            return

        security_manager = get_security_manager()
        security_manager.mark_activity("telegram")

        lower_text = text.lower().strip()

        if lower_text == "/panic":
            result = security_manager.trigger_panic("telegram panic command")
            self._send_message(chat_id, result["message"])
            return

        if lower_text.startswith("/unlock "):
            pin = text[len("/unlock "):].strip()
            if security_manager.unlock(pin):
                self._send_message(chat_id, "Security lock released. Arrow is ready to resume.")
            else:
                self._send_message(chat_id, "Incorrect PIN. Arrow remains locked.")
            return

        if security_manager.is_locked():
            security_manager.record_intrusion_attempt(text)
            self._send_message(chat_id, "Arrow is locked for security. Send /unlock <PIN> to resume.")
            return

        if lower_text == "/dashboard":
            report = build_dashboard_report()
            self._send_message(chat_id, report)
            send_dashboard_report(chat_id=chat_id)
            return

        if lower_text == "/screenshot":
            from modules.pc_control import take_screenshot

            screenshot_path = take_screenshot()
            self._send_photo(chat_id, screenshot_path, caption="Arrow screenshot")
        elif lower_text == "/status":
            self._send_message(chat_id, self.get_status())
        elif lower_text == "/shutdown_pc":
            result = self._run_windows_system_command("shutdown", ["/s", "/t", "10"])
            if result:
                self._send_message(chat_id, "Windows shutdown scheduled in 10 seconds.")
            else:
                self._send_message(chat_id, "Shutdown command is only available on Windows or the command failed.")
        elif lower_text == "/restart_pc":
            result = self._run_windows_system_command("shutdown", ["/r", "/t", "10"])
            if result:
                self._send_message(chat_id, "Windows restart scheduled in 10 seconds.")
            else:
                self._send_message(chat_id, "Restart command is only available on Windows or the command failed.")
        elif lower_text.startswith("/say "):
            message = text[5:].strip()
            if message:
                speak(message)
                self._send_message(chat_id, f"Spoken: {message}")
            else:
                self._send_message(chat_id, "Please provide text after /say.")
        elif lower_text.startswith("/open "):
            from modules.pc_control import open_app

            target = text[6:].strip()
            if target and open_app(target):
                self._send_message(chat_id, f"Opening {target}.")
            else:
                self._send_message(chat_id, f"I could not open {target}.")
        elif lower_text.startswith("/play "):
            from modules.browser_control import play_youtube

            query = text[6:].strip()
            if query and play_youtube(query):
                self._send_message(chat_id, f"Playing {query} on YouTube.")
            else:
                self._send_message(chat_id, "I could not play that YouTube query.")
        elif lower_text.startswith("/press "):
            from modules.pc_control import press_shortcut

            shortcut = text[7:].strip()
            if shortcut and press_shortcut(shortcut):
                self._send_message(chat_id, f"Pressed shortcut: {shortcut}")
            else:
                self._send_message(chat_id, "I could not recognize that shortcut command.")
        elif lower_text in {"/desk", "/scan", "/camera", "/desk scan", "/scan desk"}:
            from modules.camera import capture_live_desk_snapshot

            camera_result = capture_live_desk_snapshot()
            if not camera_result:
                self._send_message(chat_id, "I could not capture the live camera snapshot. Check the RTSP URL and camera connection.")
            else:
                try:
                    vision_text = query_gemini_with_image(
                        "Analyze the attached desk snapshot. Describe visible items, gadgets, screen details, and any potential hardware or wiring issues.",
                        camera_result["path"],
                    )
                    remember_visual_objects(vision_text)
                    self._send_message(chat_id, f"Saved desk snapshot to {camera_result['path']}. {camera_result['summary']} Gemini says: {vision_text}")
                except Exception as exc:
                    print(f"[telegram_bot] Vision error: {exc}")
                    self._send_message(chat_id, f"Saved desk snapshot to {camera_result['path']}. {camera_result['summary']}")
        elif lower_text == "/profile":
            profile_summary = summarize_user_profile()
            self._send_message(chat_id, profile_summary)
        elif lower_text == "/help":
            help_msg = (
                "Arrow Smart Remote Engine commands:\n"
                "/screenshot - take screen capture\n"
                "/status - system status (CPU/RAM/battery)\n"
                "/shutdown_pc - schedule safe Windows shutdown\n"
                "/restart_pc - schedule safe Windows restart\n"
                "/play <query> - play YouTube query\n"
                "/open <app> - open application (chrome, notepad)\n"
                "/press <shortcut> - press keyboard shortcut\n"
                "/desk - scan desk via camera and analyze\n"
                "/remember <text> - save a memory\n"
                "/profile - show stored profile and desk items\n"
                "/dashboard - show the Phase 7 dashboard and orchestration summary\n"
                "/panic - activate secure stealth mode\n"
                "/unlock <PIN> - release the security lock"
            )
            self._send_message(chat_id, help_msg)
        elif lower_text.startswith("/remember "):
            memory_text = text[10:].strip()
            if memory_text:
                if not memory_text.lower().startswith(("remember", "save", "store", "note")):
                    memory_text = f"remember {memory_text}"
                entry = remember_memory(memory_text)
                if entry:
                    key, value = entry
                    self._send_message(chat_id, f"Remembered {key} = {value}.")
                else:
                    self._send_message(chat_id, "I could not understand that memory to remember.")
            else:
                self._send_message(chat_id, "Please provide something to remember after /remember.")

    def _run_windows_system_command(self, command_name: str, args: list[str]) -> bool:
        if platform.system() != "Windows":
            return False
        try:
            subprocess.run([command_name, *args], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except Exception:
            return False

    def get_status(self) -> str:
        arrow_status = "running" if self.started else "not running"
        try:
            from modules.pc_control import get_system_status

            system_status = get_system_status()
        except Exception as exc:
            system_status = f"system status unavailable: {exc}"
        return f"Arrow is {arrow_status}. {system_status}"

    def send_startup_message(self) -> None:
        if not self.admin_chat_id:
            return
        self._send_message(self.admin_chat_id, "Arrow Smart Remote Engine has started successfully.")

    def _run(self) -> None:
        while not self.stop_event.is_set():
            try:
                updates = self._get_updates()
                for update in updates:
                    self.offset = update["update_id"] + 1
                    message = update.get("message")
                    if message:
                        self._process_message(message)
            except Exception:
                time.sleep(5)

    def start(self) -> None:
        if self.thread.is_alive() or not self.token or self.token == "YOUR_TELEGRAM_BOT_TOKEN" or not self.admin_chat_id:
            return
        self.thread.start()
        self.started = True

    def stop(self) -> None:
        self.stop_event.set()
        self.thread.join(timeout=1)


TelegramRemoteBot = SmartRemoteEngine
