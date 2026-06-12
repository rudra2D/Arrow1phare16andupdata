"""PC control utilities for Arrow."""

import os
import platform
import re
import subprocess
import sys
import webbrowser
from datetime import datetime
from pathlib import Path

import psutil

HEADLESS = os.environ.get("DISPLAY") is None and sys.platform != "win32"
try:
    import pyautogui
except Exception:
    pyautogui = None


SCREENSHOT_DIR = Path("arrow_data/screenshots")
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

APP_COMMANDS = {
    "notepad": {
        "Windows": ["notepad"],
        "Linux": ["gedit"],
        "Darwin": ["open", "-a", "TextEdit"],
    },
    "chrome": {
        "Windows": ["cmd", "/c", "start", "chrome"],
        "Linux": ["google-chrome"],
        "Darwin": ["open", "-a", "Google Chrome"],
    },
    "calculator": {
        "Windows": ["calc"],
        "Linux": [["gnome-calculator"], ["kcalc"], ["galculator"]],
        "Darwin": ["open", "-a", "Calculator"],
    },
}

KEY_MAP = {
    "ctrl": "ctrl",
    "control": "ctrl",
    "alt": "alt",
    "shift": "shift",
    "cmd": "command",
    "command": "command",
    "win": "win",
    "super": "win",
    "option": "alt",
    "escape": "esc",
    "esc": "esc",
    "enter": "enter",
    "return": "enter",
    "tab": "tab",
    "space": "space",
    "delete": "delete",
    "backspace": "backspace",
    "up": "up",
    "down": "down",
    "left": "left",
    "right": "right",
    "f1": "f1",
    "f2": "f2",
    "f3": "f3",
    "f4": "f4",
    "f5": "f5",
    "f6": "f6",
    "f7": "f7",
    "f8": "f8",
    "f9": "f9",
    "f10": "f10",
    "f11": "f11",
    "f12": "f12",
}


def take_screenshot() -> str:
    """Take a screenshot and save it to the screenshots folder."""
    filename = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    path = SCREENSHOT_DIR / filename
    if pyautogui is None or HEADLESS:
        raise RuntimeError("Screenshot unavailable in headless mode or when pyautogui is not installed")
    image = pyautogui.screenshot()
    image.save(path)
    return str(path)


def _run_command(command: list[str] | list[list[str]]) -> bool:
    if isinstance(command[0], list):
        for subcommand in command:
            if _run_command(subcommand):
                return True
        return False

    try:
        subprocess.Popen(command)
        return True
    except FileNotFoundError:
        return False
    except Exception:
        return False


def open_app(app_name: str) -> bool:
    """Open a common application by name."""
    system_name = platform.system()
    normalized = app_name.strip().lower()
    if "notepad" in normalized:
        command = APP_COMMANDS["notepad"].get(system_name)
    elif "calculator" in normalized:
        command = APP_COMMANDS["calculator"].get(system_name)
    elif "chrome" in normalized or "browser" in normalized:
        command = APP_COMMANDS["chrome"].get(system_name)
    else:
        command = None

    if command and _run_command(command):
        return True

    if "chrome" in normalized or "browser" in normalized:
        webbrowser.open("https://www.google.com")
        return True

    return False


def _parse_keys(text: str) -> list[str]:
    text = text.lower()
    text = re.sub(r"press|shortcut|key|keys|keystrokes|hit|type|type in", "", text)
    parts = re.split(r"[\s,]+", text.strip())
    keys = []

    for part in parts:
        if not part:
            continue
        mapped = KEY_MAP.get(part)
        if mapped:
            keys.append(mapped)
        elif len(part) == 1 and part.isalnum():
            keys.append(part)
        elif part.startswith("f") and part[1:].isdigit():
            keys.append(part)

    return keys


def press_shortcut(command_text: str) -> bool:
    """Press a keyboard shortcut sequence."""
    keys = _parse_keys(command_text)
    if not keys:
        return False

    try:
        pyautogui.hotkey(*keys)
        return True
    except Exception:
        return False


def get_system_status() -> str:
    """Return a text summary of CPU, RAM, and battery status."""
    cpu = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory()
    lines = [f"CPU usage is {cpu} percent.", f"Memory usage is {memory.percent} percent."]
    battery = None
    try:
        battery = psutil.sensors_battery()
    except Exception:
        battery = None

    if battery is not None:
        charging = "charging" if battery.power_plugged else "not charging"
        lines.append(f"Battery is at {battery.percent} percent and is {charging}.")
    else:
        lines.append("Battery information is not available.")

    return " ".join(lines)
