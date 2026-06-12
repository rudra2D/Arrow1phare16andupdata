"""Failsafe monitor for Arrow."""

import os
import threading
import time

try:
    import pyautogui
except Exception:  # pragma: no cover
    pyautogui = None


class FailSafe:
    def __init__(self, stop_callback, corner_x: int = 0, corner_y: int = 0, interval: float = 0.25):
        self.stop_callback = stop_callback
        self.corner_x = corner_x
        self.corner_y = corner_y
        self.interval = interval
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        if not self.thread.is_alive():
            self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self.thread.join(timeout=1)

    def _run(self) -> None:
        while not self.stop_event.is_set():
            if pyautogui is None:
                time.sleep(self.interval)
                continue
            try:
                x, y = pyautogui.position()
                if x == self.corner_x and y == self.corner_y:
                    print("[failsafe] Mouse at corner detected. Stopping Arrow.")
                    self.stop_callback()
                    return
            except Exception:
                pass
            time.sleep(self.interval)
