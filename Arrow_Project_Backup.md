# Arrow Project Backup

## 1. Project Architecture & State

### Root and Entry Points
- `main.py`
  - Central voice / command routing engine.
  - Contains emergency listener for "Arrow stop" / "Arrow stop execution".
  - Manages background PIDs and kill-switch invocation.
  - Currently integration-ready but import is blocked in the present environment by missing `selenium` via `modules.browser_control`.

- `test_keyboard.py`
  - Standalone runner for the holographic virtual keyboard.
  - Imports `modules.virtual_keyboard` and can be used to validate virtual keyboard behavior when dependencies are available.

### Core Modules Created So Far
- `modules/camera.py`
  - Desk and face monitor using MediaPipe face detection.
  - Implements absence timer and automated lock behavior.
  - Operational status: implemented, but currently non-functional without `opencv-python` because `cv2` is imported at module load.

- `modules/hand_mode.py`
  - MediaPipe-based hand tracking with point smoothing.
  - Auto-activation via open palm, auto-exit via fist gesture.
  - Pinch click recognition using thumb and index distances.
  - Background daemon thread design.
  - Operational status: module imports successfully in degraded mode, but runtime hand tracking requires `opencv-python`, `mediapipe`, and `pyautogui`.

- `modules/virtual_keyboard.py`
  - Transparent QWERTY keyboard overlay on camera stream.
  - Hover-to-select logic using index fingertip dwell.
  - Loading ring animation and audible activation feedback.
  - Background daemon thread design.
  - Operational status: module imports successfully in degraded mode, but the overlay and input features require `opencv-python`, `mediapipe`, and `pyautogui`.

- `modules/app_orchestrator.py`
  - OS window and GUI orchestration.
  - Provides window finding, focus, mouse/keyboard actions, hotkey sequences.
  - Includes emergency kill-switch state and stop logic.
  - Operational status: available and import-safe; degrades gracefully when `pyautogui` is missing.

- `modules/code_generator.py`
  - Securely writes Gemini-generated Python into `arrow_data/generated/`.
  - Executes generated code with an option for foreground capture or background logging.
  - Operational status: implemented and import-safe.

- `modules/telegram_bot.py`
  - Telegram command interface module.
  - Depends on `modules.browser_control` for browser actions.
  - Operational status: present but currently blocked by missing `selenium` / browser automation dependencies.

- `modules/browser_control.py`
  - Selenium-based browser automation helper.
  - Provides YouTube and web search automation support.
  - Operational status: present but import-blocked by missing `selenium`.

### Additional Supporting Modules Present
- `modules/failsafe.py`
- `modules/memory.py`
- `modules/pc_control.py`
- `modules/scheduler.py`
- `modules/web_scraper.py`
- `modules/__init__.py`

These supporting modules are present in the workspace and represent the broader architecture, but the latest active feature work of Phases 11 and 12 is centered in `camera.py`, `hand_mode.py`, `virtual_keyboard.py`, `app_orchestrator.py`, `code_generator.py`, `telegram_bot.py`, and `main.py`.

---

## 2. Phase 11 & Phase 12 Details

### Phase 11: Hand Mode
- Logic:
  - Use MediaPipe hand landmarks to track a hand and derive a control cursor from the palm center.
  - Use exponential moving average (EMA) smoothing for stable cursor movement.
  - Recognize pinch clicks by measuring the distance between the thumb tip and index fingertip.
  - Activate hand mode automatically on an open palm gesture held for a sustained period.
  - Exit hand mode automatically on a closed fist gesture held for a sustained period.
- Finalized parameters:
  - EMA smoothing alpha = `0.4`.
  - Pinch click detection based on thumb-index distance threshold.
  - Gesture-hold duration thresholds for activation/exit to reduce accidental mode switching.
- Background behavior:
  - Runs as a daemon thread that continually processes camera frames and hand landmarks.
  - Provides cursor control and click simulation when active.
- Fail-safe mode:
  - The module attempts auto-install of dependencies but gracefully degrades when installation is not permitted.
  - If dependencies are unavailable, the module still imports safely and reports degraded functionality.

### Phase 12: Virtual Keyboard
- Logic:
  - Overlay a QWERTY keyboard on the camera stream using OpenCV drawing.
  - Track the index fingertip and determine hover location over keys.
  - Perform key selection when the fingertip remains over a key for a dwell period.
  - Provide a loading ring animation during key activation to visualize dwell progress.
  - Emit a beep/sound feedback on key activation.
- Finalized parameters:
  - Hover-to-select dwell time = `0.5s`.
  - Transparent keyboard overlay positioned in the lower half of the view.
  - Visual feedback through key highlight and loading ring.
  - Audible beep on activation.
- Background behavior:
  - Runs as a daemon thread in the background so the overlay can be toggled or stopped cleanly.
- Fail-safe mode:
  - The module attempts auto-install of `opencv-python`, `mediapipe`, and `pyautogui` when missing.
  - If auto-installation fails due to environment restrictions, the module continues in degraded mode and avoids crashing on import.

---

## 3. Roadmap for Future Phases

### Phase 13: Anti-Spoofing Blink Face Core
- Blueprint:
  - Add face anti-spoofing to the camera/face detection module.
  - Implement blink detection and liveliness checks using the eye aspect ratio or facial landmark motion.
  - Combine blink sequences with face detection to confirm the user is a live human.
  - Provide a spoof-detection event output that can gate sensitive actions or authentication flows.
- Expected deliverables:
  - `modules/anti_spoof.py` or extended `modules/camera.py`.
  - Blink/liveness thresholding logic.
  - Integration hooks for lock/unlock and secure command execution.

### Phase 14: Pure Automation Engine
- Blueprint:
  - Build a system-wide automation engine for scheduled tasks and scripted workflows.
  - Provide a declarative action sequence format and runtime executor.
  - Support task orchestration across browser, local apps, keyboard/mouse control, and generated code.
  - Add retry logic, failure detection, and task state reporting.
- Expected deliverables:
  - `modules/automation_engine.py` or `modules/orchestrator.py` enhancements.
  - A scheduler interface for timed/triggered automation.
  - APIs to bind voice commands or Telegram commands to automation flows.

### Phase 15: Central Orchestrator Core
- Blueprint:
  - Create a centralized orchestrator that unifies perception, hands-free control, keyboard, automation, and safety.
  - Maintain global state and resource coordination across modules.
  - Provide a single control plane for feature toggles, emergency stop, and mode transitions.
  - Expose a clean integration layer for new modules and future expansion.
- Expected deliverables:
  - `modules/central_orchestrator.py` or a major `main.py` refactor.
  - Centralized kill-switch management and background process supervisor.
  - A decision engine that routes sensor input, gesture activation, and automation tasks.

---

## 4. Environment Configurations

### Virtual Environment
- A Python virtual environment has been created at `.venv/` in the workspace root.
- Standard venv structure includes:
  - `.venv/bin/`
  - `.venv/lib/`
  - `.venv/include/`
  - `.venv/pyvenv.cfg`

### Required Pip Dependencies
- `opencv-python`
- `mediapipe`
- `pyautogui`
- `selenium`
- `webdriver-manager`

### Activation and installation commands
```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
pip install opencv-python mediapipe pyautogui selenium webdriver-manager
```

### Notes
- The current workspace contains the `.venv/` directory, but actual runtime success depends on installing the required packages inside that environment.
- If `.venv/` is moved, the environment should be re-created on the new host with the same dependency list.

---

## Backup Summary

This document captures the current Arrow architecture, latest Phase 11/12 implementation details, and the next-phase roadmap so a new AI instance can continue the project without losing context.
