"""Phase 9: Action, Automation, and Hardware Execution Interfaces.

This module provides local OS automation interfaces and hardware relay dispatching
for Arrow. It is designed to work safely in headless environments, with strict
fallbacks when display servers or serial hardware are unavailable.
"""

from __future__ import annotations

import os
import sys
import time
from typing import Any, Iterable

try:
    import pyautogui
except Exception:  # pragma: no cover
    pyautogui = None

try:
    import serial
    import serial.tools.list_ports
    SerialException = serial.SerialException
except Exception:  # pragma: no cover
    serial = None
    SerialException = Exception

ORCHESTRATOR_PLUGIN = {
    "name": "action_automation",
    "handler": "orchestrator_event_hook",
    "events": ("vision.alert.triggered", "vision.snapshot.saved"),
    "priority": 15,
}

SERIAL_PORT_ENV = os.getenv("ARROW_HARDWARE_SERIAL_PORT", "").strip()
HARDWARE_BAUDRATE = int(os.getenv("ARROW_HARDWARE_BAUDRATE", "9600"))
HARDWARE_TIMEOUT = float(os.getenv("ARROW_HARDWARE_TIMEOUT", "1"))

SUPPORTED_MOUSE_ACTIONS = {"click", "double_click", "right_click", "move"}


def _is_display_available() -> bool:
    if pyautogui is None:
        return False
    if sys.platform.startswith("linux"):
        return bool(
            os.environ.get("DISPLAY")
            or os.environ.get("WAYLAND_DISPLAY")
            or os.environ.get("XDG_SESSION_TYPE")
        )
    return True


def _normalize_keys(keys_list: Any) -> list[str]:
    if isinstance(keys_list, str):
        if "+" in keys_list:
            return [part.strip() for part in keys_list.split("+") if part.strip()]
        return [keys_list.strip()]
    if isinstance(keys_list, Iterable):
        return [str(key).strip() for key in keys_list if str(key).strip()]
    return []


def execute_mouse_action(target_coordinates: Any, action_type: str = "click") -> dict[str, Any]:
    """Execute a mouse action using pyautogui or return a safe error response."""
    if action_type not in SUPPORTED_MOUSE_ACTIONS:
        return {"status": "error", "error": f"unsupported mouse action: {action_type}"}

    try:
        x, y = target_coordinates
        x = int(x)
        y = int(y)
    except Exception as exc:
        return {"status": "error", "error": f"invalid target coordinates: {exc}"}

    if not _is_display_available():
        return {
            "status": "unavailable",
            "error": "display server is not available for mouse automation",
        }

    if pyautogui is None:
        return {"status": "unavailable", "error": "pyautogui is not installed"}

    try:
        pyautogui.FAILSAFE = False
        pyautogui.moveTo(x, y, duration=0.15)

        if action_type == "click":
            pyautogui.click()
        elif action_type == "double_click":
            pyautogui.doubleClick()
        elif action_type == "right_click":
            pyautogui.rightClick()
        elif action_type == "move":
            pass

        return {"status": "executed", "action_type": action_type, "coordinates": (x, y)}
    except Exception as exc:
        return {"status": "error", "error": str(exc), "action_type": action_type}


def execute_keyboard_shortcut(keys_list: Any) -> dict[str, Any]:
    """Execute a keyboard shortcut sequence using pyautogui or return a safe fallback."""
    keys = _normalize_keys(keys_list)
    if not keys:
        return {"status": "error", "error": "no keys provided for shortcut"}

    if not _is_display_available():
        return {
            "status": "unavailable",
            "error": "display server is not available for keyboard automation",
            "keys": keys,
        }

    if pyautogui is None:
        return {"status": "unavailable", "error": "pyautogui is not installed", "keys": keys}

    try:
        if len(keys) == 1:
            pyautogui.press(keys[0])
        else:
            pyautogui.hotkey(*keys)
        return {"status": "executed", "keys": keys}
    except Exception as exc:
        return {"status": "error", "error": str(exc), "keys": keys}


def _list_serial_ports() -> list[str]:
    if serial is None:
        return []

    try:
        return [port.device for port in serial.tools.list_ports.comports()]
    except Exception:
        return []


def _resolve_serial_port() -> str | None:
    if SERIAL_PORT_ENV:
        return SERIAL_PORT_ENV
    ports = _list_serial_ports()
    return ports[0] if ports else None


def dispatch_hardware_signal(relay_id: int | str, state: bool) -> dict[str, Any]:
    """Send a relay command over serial to external hardware or return a mocked response."""
    try:
        relay_id_value = int(relay_id)
    except Exception:
        return {"status": "error", "error": "relay_id must be an integer"}

    command_string = f"RELAY:{relay_id_value}:{1 if state else 0}\n"
    port_name = _resolve_serial_port()

    if serial is None:
        return {
            "status": "mock",
            "relay_id": relay_id_value,
            "state": bool(state),
            "command": command_string.strip(),
            "reason": "pyserial is not installed",
        }

    if not port_name:
        return {
            "status": "mock",
            "relay_id": relay_id_value,
            "state": bool(state),
            "command": command_string.strip(),
            "reason": "no serial port available",
        }

    try:
        with serial.Serial(port_name, baudrate=HARDWARE_BAUDRATE, timeout=HARDWARE_TIMEOUT) as ser:
            ser.write(command_string.encode("ascii"))
            ser.flush()
            response = ser.readline().decode("ascii", errors="ignore").strip()

        return {
            "status": "sent",
            "relay_id": relay_id_value,
            "state": bool(state),
            "port": port_name,
            "command": command_string.strip(),
            "response": response,
        }
    except SerialException as exc:
        return {
            "status": "mock",
            "relay_id": relay_id_value,
            "state": bool(state),
            "command": command_string.strip(),
            "error": str(exc),
            "reason": "serial port error",
        }
    except Exception as exc:
        return {
            "status": "error",
            "relay_id": relay_id_value,
            "state": bool(state),
            "command": command_string.strip(),
            "error": str(exc),
        }


def _derive_automation_coordinates(payload: dict[str, Any]) -> tuple[int, int]:
    width = payload.get("frame_width")
    height = payload.get("frame_height")
    if isinstance(width, int) and isinstance(height, int) and width > 0 and height > 0:
        return (width // 2, height // 2)
    return (100, 100)


def orchestrator_event_hook(event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    """React to vision-core phase events and route local automation or hardware toggles."""
    try:
        if event_type == "vision.alert.triggered":
            coordinates = _derive_automation_coordinates(payload)
            action_result = execute_mouse_action(coordinates, action_type="click")
            relay_state = bool(payload.get("objects") or payload.get("detections") or payload.get("object_count"))
            relay_result = dispatch_hardware_signal(relay_id=1, state=relay_state)
            return {
                "status": "handled",
                "event_type": event_type,
                "action_result": action_result,
                "relay_result": relay_result,
            }

        if event_type == "vision.snapshot.saved":
            shortcut_result = execute_keyboard_shortcut(["ctrl", "alt", "s"])
            relay_result = dispatch_hardware_signal(relay_id=2, state=False)
            return {
                "status": "handled",
                "event_type": event_type,
                "shortcut_result": shortcut_result,
                "relay_result": relay_result,
            }

        return {"status": "ignored", "event_type": event_type}
    except Exception as exc:
        return {"status": "error", "error": str(exc), "event_type": event_type}
