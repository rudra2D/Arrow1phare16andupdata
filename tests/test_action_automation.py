"""Tests for Phase 9 action automation and hardware relay integration."""

from unittest.mock import MagicMock, patch

import pytest

from modules import action_automation as aa


class TestExecuteMouseAction:
    def test_execute_mouse_action_success(self):
        mock_pyautogui = MagicMock()
        with patch.object(aa, "_is_display_available", return_value=True), \
             patch.object(aa, "pyautogui", mock_pyautogui):
            result = aa.execute_mouse_action((123, 456), action_type="click")

        assert result["status"] == "executed"
        assert result["action_type"] == "click"
        assert result["coordinates"] == (123, 456)
        mock_pyautogui.moveTo.assert_called_once_with(123, 456, duration=0.15)
        mock_pyautogui.click.assert_called_once()

    def test_execute_mouse_action_headless_fallback(self):
        mock_pyautogui = MagicMock()
        mock_pyautogui.moveTo.side_effect = RuntimeError("DisplayError")

        with patch.object(aa, "_is_display_available", return_value=True), \
             patch.object(aa, "pyautogui", mock_pyautogui):
            result = aa.execute_mouse_action((10, 20), action_type="click")

        assert result["status"] == "error"
        assert "DisplayError" in result["error"]
        assert result["action_type"] == "click"


class TestExecuteKeyboardShortcut:
    def test_execute_keyboard_shortcut(self):
        mock_pyautogui = MagicMock()
        with patch.object(aa, "_is_display_available", return_value=True), \
             patch.object(aa, "pyautogui", mock_pyautogui):
            result = aa.execute_keyboard_shortcut(["ctrl", "alt", "s"])

        assert result["status"] == "executed"
        assert result["keys"] == ["ctrl", "alt", "s"]
        mock_pyautogui.hotkey.assert_called_once_with("ctrl", "alt", "s")

    def test_execute_keyboard_shortcut_single_key(self):
        mock_pyautogui = MagicMock()
        with patch.object(aa, "_is_display_available", return_value=True), \
             patch.object(aa, "pyautogui", mock_pyautogui):
            result = aa.execute_keyboard_shortcut("enter")

        assert result["status"] == "executed"
        assert result["keys"] == ["enter"]
        mock_pyautogui.press.assert_called_once_with("enter")


class TestDispatchHardwareSignal:
    def test_dispatch_hardware_signal_real_vs_mock(self):
        fake_serial = MagicMock()
        fake_serial.SerialException = Exception

        fake_ser = MagicMock()
        fake_ser.readline.return_value = b"OK\n"
        fake_serial.Serial.return_value.__enter__.return_value = fake_ser

        with patch.object(aa, "serial", fake_serial), \
             patch.object(aa, "_resolve_serial_port", return_value="COM3"):
            result = aa.dispatch_hardware_signal(1, True)

        assert result["status"] == "sent"
        assert result["relay_id"] == 1
        assert result["state"] is True
        assert result["port"] == "COM3"
        assert result["command"] == "RELAY:1:1"
        fake_serial.Serial.assert_called_once_with(
            "COM3",
            baudrate=aa.HARDWARE_BAUDRATE,
            timeout=aa.HARDWARE_TIMEOUT,
        )
        fake_ser.write.assert_called_once_with(b"RELAY:1:1\n")

    def test_dispatch_hardware_signal_port_unavailable_switches_to_mock(self):
        fake_serial = MagicMock()
        fake_serial.SerialException = Exception

        with patch.object(aa, "serial", fake_serial), \
             patch.object(aa, "_resolve_serial_port", return_value=None):
            result = aa.dispatch_hardware_signal(2, False)

        assert result["status"] == "mock"
        assert result["relay_id"] == 2
        assert result["state"] is False
        assert result["reason"] == "no serial port available"

    def test_dispatch_hardware_signal_invalid_relay_id(self):
        result = aa.dispatch_hardware_signal("invalid", True)

        assert result["status"] == "error"
        assert "relay_id must be an integer" in result["error"]


class TestActionOrchestratorEventHookRouting:
    def test_action_orchestrator_event_hook_vision_alert_triggered(self):
        mock_mouse = MagicMock(return_value={"status": "executed"})
        mock_relay = MagicMock(return_value={"status": "mock"})

        with patch.object(aa, "execute_mouse_action", mock_mouse), \
             patch.object(aa, "dispatch_hardware_signal", mock_relay):
            payload = {"frame_width": 640, "frame_height": 480, "detections": 2}
            result = aa.orchestrator_event_hook("vision.alert.triggered", payload)

        assert result["status"] == "handled"
        assert result["event_type"] == "vision.alert.triggered"
        mock_mouse.assert_called_once_with((320, 240), action_type="click")
        mock_relay.assert_called_once_with(relay_id=1, state=True)
        assert result["action_result"]["status"] == "executed"

    def test_action_orchestrator_event_hook_vision_snapshot_saved(self):
        mock_shortcut = MagicMock(return_value={"status": "executed"})
        mock_relay = MagicMock(return_value={"status": "mock"})

        with patch.object(aa, "execute_keyboard_shortcut", mock_shortcut), \
             patch.object(aa, "dispatch_hardware_signal", mock_relay):
            result = aa.orchestrator_event_hook("vision.snapshot.saved", {})

        assert result["status"] == "handled"
        assert result["event_type"] == "vision.snapshot.saved"
        mock_shortcut.assert_called_once_with(["ctrl", "alt", "s"])
        mock_relay.assert_called_once_with(relay_id=2, state=False)
        assert result["shortcut_result"]["status"] == "executed"

    def test_action_orchestrator_event_hook_ignores_unknown_event(self):
        result = aa.orchestrator_event_hook("unrelated.event", {})

        assert result["status"] == "ignored"
        assert result["event_type"] == "unrelated.event"
