"""Phase 7: Telegram Storage & Maintenance Runtime.

This module registers as a Phase 14 Orchestrator listener and manages
private upload channels, SQLite vacuum maintenance, and admin telemetry.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

import requests

from config import (
    ADMIN_CHAT_ID,
    PRIVATE_BACKUP_UPLOAD_URL,
    PRIVATE_SERVER_UPLOAD_URL,
    PRIVATE_STORAGE_AUTH_TOKEN,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_USER_ID,
)
from modules.memory import get_memory_db_path, initialize_memory_store, vacuum_memory_database
from modules.orchestrator import get_orchestrator

API_BASE = "https://api.telegram.org"
DEFAULT_VACUUM_INTERVAL_SECONDS = 3600

ORCHESTRATOR_PLUGIN = {
    "name": "telegram_storage",
    "handler": "orchestrator_event_hook",
    "events": ("*",),
    "priority": 15,
}


class TelegramStorageEngine:
    def __init__(self) -> None:
        self.token = TELEGRAM_BOT_TOKEN
        self.admin_chat_id = ADMIN_CHAT_ID or TELEGRAM_USER_ID
        self.server_url = PRIVATE_SERVER_UPLOAD_URL
        self.backup_url = PRIVATE_BACKUP_UPLOAD_URL
        self.auth_token = PRIVATE_STORAGE_AUTH_TOKEN
        self.thread = threading.Thread(
            target=self._maintenance_loop,
            daemon=True,
            name="telegram-storage-maintenance",
        )
        self.started = False
        self._last_vacuum = None

    def is_configured(self) -> bool:
        return bool(self.token and self.admin_chat_id)

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        return headers

    def _telegram_url(self, method: str) -> str:
        return f"{API_BASE}/bot{self.token}/{method}"

    def send_telegram_message(self, chat_id: int, text: str) -> dict[str, Any]:
        if not self.is_configured():
            return {"status": "skipped", "reason": "telegram-not-configured"}

        payload = {"chat_id": chat_id, "text": text}
        response = requests.post(self._telegram_url("sendMessage"), data=payload, timeout=15)
        try:
            response.raise_for_status()
            return {"status": "ok", "chat_id": chat_id}
        except Exception as exc:
            return {"status": "error", "error": str(exc), "chat_id": chat_id}

    def _upload_file(
        self,
        url: str,
        file_path: Path,
        category: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not url:
            return {"status": "skipped", "reason": "upload-url-not-configured", "category": category}
        if not file_path.exists() or not file_path.is_file():
            return {"status": "skipped", "reason": "file-missing", "file_path": str(file_path)}

        data = {
            "category": category,
            "file_name": file_path.name,
            "metadata": json.dumps(metadata or {}),
        }

        with file_path.open("rb") as handle:
            files = {"file": (file_path.name, handle, "application/octet-stream")}
            response = requests.post(url, headers=self._headers(), files=files, data=data, timeout=120)

        try:
            response.raise_for_status()
            result = response.json() if response.headers.get("content-type", "").startswith("application/json") else {"status_text": response.text}
            return {"status": "uploaded", "category": category, "file_path": str(file_path), "destination": url, "response": result}
        except Exception as exc:
            return {"status": "error", "category": category, "file_path": str(file_path), "destination": url, "error": str(exc)}

    def send_private_server_data(self, file_path: Path, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._upload_file(file_path=file_path, url=self.server_url, category="private server data", metadata=metadata)

    def send_private_backup_data(self, file_path: Path, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._upload_file(file_path=file_path, url=self.backup_url, category="private backup server data", metadata=metadata)

    def build_dashboard_report(self) -> str:
        orchestrator = get_orchestrator()
        plugin_names = sorted(getattr(orchestrator, "_plugins", {}).keys())
        db_path = get_memory_db_path()
        db_exists = db_path.exists()

        report_lines = [
            "Arrow Phase 7 Storage Dashboard",
            f"- Phase 14 orchestrator status: {'ready' if orchestrator._booted else 'not ready'}",
            f"- Loaded plugins: {', '.join(plugin_names) if plugin_names else 'none'}",
            f"- Telegram configured: {'yes' if self.is_configured() else 'no'}",
            f"- Admin chat locked: {'yes' if self.admin_chat_id else 'no'}",
            f"- Private server channel configured: {'yes' if bool(self.server_url) else 'no'}",
            f"- Private backup channel configured: {'yes' if bool(self.backup_url) else 'no'}",
            f"- Memory DB path: {db_path}",
            f"- Memory DB exists: {'yes' if db_exists else 'no'}",
            f"- Last SQLite VACUUM: {self._last_vacuum or 'pending'}",
        ]
        return "\n".join(report_lines)

    def send_dashboard_report(self, chat_id: int | None = None) -> dict[str, Any]:
        sent_to: list[int] = []
        if chat_id is not None:
            result = self.send_telegram_message(chat_id, self.build_dashboard_report())
            if result.get("status") == "ok":
                sent_to.append(chat_id)

        if self.admin_chat_id and self.admin_chat_id != chat_id:
            result = self.send_telegram_message(self.admin_chat_id, self.build_dashboard_report())
            if result.get("status") == "ok":
                sent_to.append(self.admin_chat_id)

        return {"status": "sent" if sent_to else "skipped", "sent_to": sent_to}

    def send_startup_message(self) -> None:
        if self.admin_chat_id:
            self.send_telegram_message(self.admin_chat_id, "Arrow Phase 7 Storage Engine has started and is monitoring the event bus.")

    def _maintenance_loop(self) -> None:
        while True:
            try:
                vacuum_memory_database(keep_days=30)
                self._last_vacuum = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
            except Exception:
                pass
            time.sleep(DEFAULT_VACUUM_INTERVAL_SECONDS)

    def start(self) -> None:
        if not self.thread.is_alive():
            self.thread.start()
            self.started = True

    def dispatch_file(
        self,
        file_path: Path | str,
        category: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        path = Path(file_path)
        if category == "private backup server data":
            return self.send_private_backup_data(path, metadata)
        return self.send_private_server_data(path, metadata)


ENGINE = TelegramStorageEngine()


def orchestrator_event_hook(event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    if event_type == "orchestrator.boot":
        ENGINE.start()
        ENGINE.send_startup_message()
        return {"status": "phase7-ready", "started": ENGINE.started}

    if event_type == "command.completed" and payload.get("route_file"):
        category = payload.get("route_file_category", "private backup server data")
        file_path = payload.get("route_file")
        metadata = payload.get("route_file_metadata", {})
        return ENGINE.dispatch_file(file_path, category, metadata)

    if event_type == "orchestrator.boot" or event_type == "orchestrator.shutdown":
        return {"status": "event-received", "event": event_type}

    return {"status": "ignored", "event": event_type}
