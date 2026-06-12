
# Arrow

Last updated: 2026-06-11

Arrow is a modular automation and perception platform for voice, gesture, vision, IDE control, remote access, and orchestration.

## Project Overview

Arrow is structured as a phase-driven system built around a central orchestrator. It combines cloud-trained models, local desktop automation, hardware relay support, and headless-safe failover for GitHub Codespaces and server environments.

Key active components:
- Phase 1: command and voice routing (`main.py`)
- Phase 2: JSON memory vault (`modules/memory.py`)
- Phase 3: browser automation blueprint (`modules/browser_control.py`)
- Phase 4: Telegram remote command interface (`modules/telegram_bot.py`)
- Phase 5: task scheduler (`modules/scheduler.py`)
- Phase 6: security and failsafe layers (`modules/security.py`, `modules/failsafe.py`)
- Phase 7: secure environment config and token loading (`config.py`)
- Phase 8: vision core with YOLO and supervision (`modules/vision_core.py`)
- Phase 9: OS automation + hardware relay integration (`modules/action_automation.py`)
- Phase 10: IDE workspace automation (`modules/ide_automation.py`)
- Phase 11: hand mode gesture tracking (`modules/hand_mode.py`)
- Phase 12: headless-safe virtual keyboard (`modules/virtual_keyboard.py`)
- Phase 14: orchestrator and event plugin discovery (`modules/orchestrator.py`)

## Directory Structure

Root files:
- `README.md`
- `requirements.txt`
- `config.py`
- `main.py`
- `run_arrow.sh`
- `install_service.sh`
- `arrow.service`
- `test_keyboard.py`

Data directories:
- `arrow_data/`
- `storage/`

Core modules:
- `modules/action_automation.py`
- `modules/app_orchestrator.py`
- `modules/browser_control.py`
- `modules/camera.py`
- `modules/code_generator.py`
- `modules/command_maker.py`
- `modules/failsafe.py`
- `modules/hand_mode.py`
- `modules/ide_automation.py`
- `modules/memory.py`
- `modules/orchestrator.py`
- `modules/pc_control.py`
- `modules/scheduler.py`
- `modules/security.py`
- `modules/telegram_bot.py`
- `modules/telegram_storage.py`
- `modules/virtual_keyboard.py`
- `modules/vision_core.py`
- `modules/web_scraper.py`

Tests:
- `tests/`
- `test_keyboard.py`

## Getting Started

1. Create and activate a Python virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Set required environment variables in your shell:

```bash
export GEMINI_API_KEY="your_gemini_api_key"
export TELEGRAM_BOT_TOKEN="your_telegram_token"
export TELEGRAM_USER_ID="your_numeric_id"
export ADMIN_CHAT_ID="your_admin_id"
export CAMERA_RTSP_URL="rtsp://your_camera_feed"
```

4. Run Arrow:

```bash
python main.py
```

## Headless and Codespaces Safe Mode

Arrow includes headless-safe guards around GUI automation and visual input modules:
- `modules/virtual_keyboard.py`
- `modules/hand_mode.py`
- `modules/action_automation.py`
- `modules/pc_control.py`
- `modules/app_orchestrator.py`

In headless environments, these modules degrade safely instead of raising import-time exceptions.

## Testing

Run the unified system test suite:

```bash
PYTHONPATH=. pytest -v --tb=short
```

Run a targeted phase test:

```bash
python -m pytest tests/test_ide_automation.py
```

## Deployment Matrix

| Component | Module(s) | Status |
|---|---|---|
| IDE Automation | `modules/ide_automation.py` | Validated |
| Hand Mode | `modules/hand_mode.py` | Headless-safe |
| Virtual Keyboard | `modules/virtual_keyboard.py` | Headless-safe |
| Vision Core | `modules/vision_core.py` | Validated |
| Action Automation | `modules/action_automation.py` | Validated |
| Orchestrator | `modules/orchestrator.py` | Built |

## Notes

- `README.md` and backup files are synchronized to reflect the current project state.
- Latest documented status: `72 passed` in `15.72s` on the current environment.

## Backup Copies

This project maintains synchronized root-level backup markdown files:
- `arrow_project_backup.md`
- `arrow-project-backup.md`
- `Arrow_Project_Backup.md`
- `Aero project backup.md`
