"""Telegram bot remote control for Arrow."""

import threading
import time
from typing import Any

import requests

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_USER_ID
from btu import query_gemini_with_image
from modules.browser_control import play_youtube
from modules.camera import capture_live_desk_snapshot
from modules.memory import remember_memory, remember_visual_objects, summarize_user_profile
from modules.pc_control import get_system_status, open_app, press_shortcut, take_screenshot
from voice_out import speak

API_BASE = "https://api.telegram.org"


class TelegramRemoteBot:
    def __init__(self) -> None:
        self.token = TELEGRAM_BOT_TOKEN
        self.allowed_user_id = TELEGRAM_USER_ID
        self.offset = None
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _build_url(self, method: str) -> str:
        return f"{API_BASE}/bot{self.token}/{method}"

    def _authorized(self, user_id: int) -> bool:
        return self.allowed_user_id and user_id == self.allowed_user_id

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

        if not self._authorized(user_id):
            return

        lower_text = text.lower().strip()
        if lower_text == "/screenshot":
            screenshot_path = take_screenshot()
            self._send_photo(chat_id, screenshot_path, caption="Arrow screenshot")
        elif lower_text == "/status":
            status = get_system_status()
            self._send_message(chat_id, status)
        elif lower_text.startswith("/say "):
            message = text[5:].strip()
            if message:
                speak(message)
                self._send_message(chat_id, f"Spoken: {message}")
            else:
                self._send_message(chat_id, "Please provide text after /say.")
        elif lower_text.startswith("/open "):
            target = text[6:].strip()
            if target and open_app(target):
                self._send_message(chat_id, f"Opening {target}.")
            else:
                self._send_message(chat_id, f"I could not open {target}.")
        elif lower_text.startswith("/play "):
            query = text[6:].strip()
            if query and play_youtube(query):
                self._send_message(chat_id, f"Playing {query} on YouTube.")
            else:
                self._send_message(chat_id, "I could not play that YouTube query.")
        elif lower_text.startswith("/press "):
            shortcut = text[7:].strip()
            if shortcut and press_shortcut(shortcut):
                self._send_message(chat_id, f"Pressed shortcut: {shortcut}")
            else:
                self._send_message(chat_id, "I could not recognize that shortcut command.")
        elif lower_text in {"/desk", "/scan", "/camera", "/desk scan", "/scan desk"}:
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
                "Arrow remote commands:\n"
                "/screenshot - take screen capture\n"
                "/status - system status (CPU/RAM/battery)\n"
                "/play <query> - play YouTube query\n"
                "/open <app> - open application (chrome, notepad)\n"
                "/press <shortcut> - press keyboard shortcut\n"
                "/desk - scan desk via camera and analyze\n"
                "/remember <text> - save a memory\n"
                "/profile - show stored profile and desk items"
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
        if self.thread.is_alive() or not self.token or self.token == "YOUR_TELEGRAM_BOT_TOKEN":
            return
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self.thread.join(timeout=1)
