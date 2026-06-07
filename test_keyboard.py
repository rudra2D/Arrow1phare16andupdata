"""Standalone test runner for the Virtual Keyboard (Phase 12).

Usage: python3 test_keyboard.py

This script stops any running Hand Mode to avoid input conflicts, then
starts the Virtual Keyboard overlay. Press Ctrl-C to stop and exit cleanly.
"""

import time

from modules.virtual_keyboard import (
    initialize,
    start_virtual_keyboard,
    stop_virtual_keyboard,
    cleanup_virtual_keyboard,
    is_virtual_keyboard_active,
)

# Ensure hand_mode won't interfere
try:
    from modules.hand_mode import stop_hand_mode, cleanup_hand_mode
except Exception:
    stop_hand_mode = None
    cleanup_hand_mode = None


def main():
    print("[test_keyboard] Stopping hand_mode (if active) to avoid conflicts...")
    try:
        if stop_hand_mode:
            stop_hand_mode()
        if cleanup_hand_mode:
            cleanup_hand_mode()
    except Exception as exc:
        print(f"[test_keyboard] Warning stopping hand_mode: {exc}")

    print("[test_keyboard] Initializing virtual keyboard...")
    initialize()
    start_virtual_keyboard()

    print("[test_keyboard] Virtual keyboard running. Press Ctrl-C to exit.")
    try:
        while True:
            if not is_virtual_keyboard_active():
                # If thread stopped unexpectedly, exit
                print("[test_keyboard] Virtual keyboard stopped.")
                break
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("[test_keyboard] Keyboard interrupt received. Stopping...")
    finally:
        try:
            stop_virtual_keyboard()
            cleanup_virtual_keyboard()
        except Exception:
            pass
        print("[test_keyboard] Exiting.")


if __name__ == "__main__":
    main()
