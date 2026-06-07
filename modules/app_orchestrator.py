"""App orchestrator for GUI automation and window management.

Provides safe, cancellable GUI automation primitives using `pyautogui` and
`pygetwindow` (if available). Includes a kill-switch event that other parts
of the system can trigger to stop long-running automated sequences.
"""

from __future__ import annotations

import threading
import time
from typing import Callable, List, Optional, Tuple

try:
    import pyautogui
except Exception:
    pyautogui = None
try:
    import pygetwindow as gw
except Exception:
    gw = None

# Global kill event
_kill_event = threading.Event()


def trigger_kill_switch() -> None:
    """Trigger the global kill switch to stop running GUI sequences."""
    _kill_event.set()


def clear_kill_switch() -> None:
    """Clear the global kill switch so sequences can run again."""
    _kill_event.clear()


def is_killed() -> bool:
    return _kill_event.is_set()


def find_windows(title_substring: str) -> List:
    """Return list of windows matching `title_substring` (case-insensitive).

    If `pygetwindow` is not available returns an empty list.
    """
    if gw is None:
        return []
    return [w for w in gw.getAllWindows() if title_substring.lower() in (w.title or "").lower()]


def focus_window(window) -> bool:
    """Bring `window` (pygetwindow Window) to foreground.

    Returns True on success. If `pygetwindow` is not available attempts a
    best-effort by using `pyautogui` to click the center of the window.
    """
    if window is None:
        return False
    try:
        if gw is not None:
            window.activate()
            time.sleep(0.25)
            window.maximize()
            return True
    except Exception:
        pass

    # Best-effort fallback: click approximate center
    try:
        bbox = (window.left, window.top, window.width, window.height)
        cx = bbox[0] + bbox[2] // 2
        cy = bbox[1] + bbox[3] // 2
        pyautogui.click(cx, cy)
        return True
    except Exception:
        return False


def click(x: int, y: int, button: str = "left") -> bool:
    if is_killed():
        return False
    try:
        if pyautogui is None:
            return False
        pyautogui.click(x, y, button=button)
        return True
    except Exception:
        return False


def move_and_click(x: int, y: int, duration: float = 0.1) -> bool:
    if is_killed():
        return False
    try:
        if pyautogui is None:
            return False
        pyautogui.moveTo(x, y, duration=duration)
        pyautogui.click()
        return True
    except Exception:
        return False


def type_text(text: str, interval: float = 0.03) -> bool:
    if is_killed():
        return False
    try:
        if pyautogui is None:
            return False
        pyautogui.write(text, interval=interval)
        return True
    except Exception:
        return False


def hotkey(*keys: str) -> bool:
    if is_killed():
        return False
    try:
        if pyautogui is None:
            return False
        pyautogui.hotkey(*keys)
        return True
    except Exception:
        return False


def run_sequence(steps: List[Tuple[str, Tuple]], check_interval: float = 0.1) -> bool:
    """Run a sequence of steps.

    Each step is a tuple (action, args_tuple). Supported actions: 'click',
    'move_click', 'type', 'hotkey', 'sleep', 'focus_window_by_title'. The
    function checks the kill switch between steps and aborts if set.
    """
    for action, args in steps:
        if is_killed():
            return False
        if action == "click":
            click(*args)
        elif action == "move_click":
            move_and_click(*args)
        elif action == "type":
            type_text(*args)
        elif action == "hotkey":
            hotkey(*args)
        elif action == "sleep":
            time.sleep(args[0])
        elif action == "focus_window_by_title":
            title = args[0]
            wins = find_windows(title)
            if wins:
                focus_window(wins[0])
        time.sleep(check_interval)
    return True


__all__ = [
    "find_windows",
    "focus_window",
    "click",
    "move_and_click",
    "type_text",
    "hotkey",
    "run_sequence",
    "trigger_kill_switch",
    "clear_kill_switch",
    "is_killed",
]
