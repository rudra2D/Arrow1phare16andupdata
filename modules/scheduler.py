"""Background scheduler for Arrow."""

import re
import threading
import time
from datetime import datetime, timedelta
from typing import Callable

from modules.memory import add_reminder, get_due_reminders, mark_reminder_triggered
from modules.pc_control import get_system_status

CHECK_INTERVAL_SECONDS = 30
MORNING_BRIEFING_HOUR = 8


def _parse_duration(text: str) -> timedelta | None:
    text = text.lower()
    match = re.search(r"(\d+)\s*(seconds|second|minutes|minute|hours|hour)", text)
    if not match:
        return None

    value = int(match.group(1))
    unit = match.group(2)
    if unit.startswith("second"):
        return timedelta(seconds=value)
    if unit.startswith("minute"):
        return timedelta(minutes=value)
    if unit.startswith("hour"):
        return timedelta(hours=value)
    return None


def _parse_absolute_time(text: str) -> datetime | None:
    text = text.lower().strip()
    match = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", text)
    if not match:
        return None

    hour = int(match.group(1))
    minute = int(match.group(2) or "0")
    suffix = match.group(3)

    if suffix:
        if suffix == "pm" and hour != 12:
            hour += 12
        if suffix == "am" and hour == 12:
            hour = 0

    now = datetime.now()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target


def extract_reminder_request(text: str) -> tuple[datetime, str] | None:
    text_lower = text.lower()

    match = re.search(r"remind me in (\d+\s*(?:seconds|second|minutes|minute|hours|hour)) (?:to )?(.+)", text_lower)
    if match:
        duration = _parse_duration(match.group(1))
        if duration is None:
            return None
        message = match.group(2).strip().rstrip("?.")
        return datetime.now() + duration, message

    match = re.search(r"remind me at (\d{1,2}(?::\d{2})?\s*(?:am|pm)?) (?:to )?(.+)", text_lower)
    if match:
        target = _parse_absolute_time(match.group(1))
        if target is None:
            return None
        message = match.group(2).strip().rstrip("?.")
        return target, message

    match = re.search(r"(?:set|start) (?:a )?timer for (\d+\s*(?:seconds|second|minutes|minute|hours|hour))(?: to (.+))?", text_lower)
    if match:
        duration = _parse_duration(match.group(1))
        if duration is None:
            return None
        message = match.group(2).strip().rstrip("?.") if match.group(2) else "Timer is done"
        return datetime.now() + duration, message

    match = re.search(r"reminder(?: for)? (.+?) at (\d{1,2}(?::\d{2})?\s*(?:am|pm)?)", text_lower)
    if match:
        message = match.group(1).strip().rstrip("?.")
        target = _parse_absolute_time(match.group(2))
        if target is None:
            return None
        return target, message

    return None


def schedule_reminder(text: str) -> str | None:
    entry = extract_reminder_request(text)
    if entry is None:
        return None

    target, message = entry
    add_reminder(target.isoformat(), message)
    return f"Reminder set for {target.strftime('%I:%M %p')} to {message}."


class Scheduler:
    def __init__(self, notify_callback: Callable[[str], None]) -> None:
        self.notify_callback = notify_callback
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.last_battery_hour = None
        self.last_briefing_date = None

    def start(self) -> None:
        if not self.thread.is_alive():
            self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self.thread.join(timeout=1)

    def _run(self) -> None:
        while not self.stop_event.is_set():
            now = datetime.now()
            self._check_hourly_battery(now)
            self._check_morning_briefing(now)
            self._check_reminders(now)
            self.stop_event.wait(CHECK_INTERVAL_SECONDS)

    def _check_hourly_battery(self, now: datetime) -> None:
        if now.minute != 0:
            return
        if now.hour == self.last_battery_hour:
            return
        self.last_battery_hour = now.hour
        status = get_system_status()
        self.notify_callback(f"Hourly system check: {status}")

    def _check_morning_briefing(self, now: datetime) -> None:
        if now.hour != MORNING_BRIEFING_HOUR or now.date() == self.last_briefing_date:
            return
        self.last_briefing_date = now.date()
        self.notify_callback("Good morning! Here is your morning briefing.")

    def _check_reminders(self, now: datetime) -> None:
        reminders = get_due_reminders(now)
        for reminder in reminders:
            self.notify_callback(f"Reminder: {reminder['message']}")
            mark_reminder_triggered(reminder['id'])
