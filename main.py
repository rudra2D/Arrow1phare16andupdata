"""Main loop for the Arrow voice assistant."""

import os
import time
import signal
import threading
import subprocess

from config import VOICE_LANGUAGE, VOICE_RECORD_SECONDS
from btu import parse_gemini_task, query_gemini, query_gemini_with_image
from modules.browser_control import extract_youtube_query, play_youtube
from modules.camera import capture_live_desk_snapshot
from modules.code_generator import run_generated
from modules.app_orchestrator import (
    find_windows,
    focus_window,
    click,
    move_and_click,
    type_text,
    hotkey,
    trigger_kill_switch,
    clear_kill_switch,
)
from modules.failsafe import FailSafe
from modules.memory import (
    get_profile_data,
    learn_about_me,
    log_project_idea,
    parse_project_logging_request,
    recall_memory,
    remember_memory,
    remember_visual_objects,
    summarize_user_profile,
    vacuum_memory_database,
)
from modules.scheduler import Scheduler, schedule_reminder
from modules.telegram_bot import SmartRemoteEngine
from modules.pc_control import (
    get_system_status,
    open_app,
    press_shortcut,
    take_screenshot,
)
from modules.command_maker import handle_unrecognized_intent
from modules.orchestrator import get_orchestrator
from modules.security import get_security_manager, is_panic_command
from modules.web_scraper import (
    extract_weather_location,
    extract_wikipedia_query,
    get_top_news_headlines,
    get_weather,
    get_wikipedia_summary,
)
from voice_in import listen
from voice_out import speak


# Background PID registry (module-level so available on import)
# Tracks PIDs for background processes started by generated code.
_active_background_pids = set()
_bg_pids_lock = threading.Lock()


def _extract_security_pin(text: str) -> str | None:
    match = __import__("re").search(r"(?:unlock|resume)(?:\s+with\s+pin)?\s+(\d{3,8})", text, flags=__import__("re").IGNORECASE)
    if match:
        return match.group(1)
    return None


def handle_memory_command(user_text: str) -> str | None:
    lower_text = user_text.strip().lower()

    if is_panic_command(user_text):
        security_manager = get_security_manager()
        security_manager.trigger_panic("voice panic command")
        return "Arrow entered secure stealth mode. Background activity is paused and the session is locked."

    # Quick help request from the user
    if any(phrase in lower_text for phrase in ["what can you do", "what can you", "help", "what commands", "what do you do"]):
        help_lines = [
            "I can do voice commands and remote actions:",
            "- Play YouTube: 'play lofi on YouTube'",
            "- Open apps: 'open Chrome'",
            "- Take screenshot: 'take screenshot'",
            "- Reminders: 'remind me in 10 minutes to make tea'",
            "- Save project ideas: 'Arrow, log this idea for the new project Smart Desk Hub'",
            "- Scan your desk: 'scan my desk' or 'what do you see on my desk'",
            "- Ask about you: 'who am I' or 'what do you know about me'",
            "- Remote control via Telegram: use /screenshot, /status, /play, /open, /desk, /remember, /profile",
        ]
        return "\n".join(help_lines)

    if any(keyword in lower_text for keyword in ["log this idea", "new project", "project vault", "blueprint vault"]):
        parsed = parse_project_logging_request(user_text)
        try:
            entry = log_project_idea(
                project_name=parsed["project_name"],
                core_logic=parsed["core_logic"],
                notes=parsed["notes"],
                project_id=parsed["project_id"],
            )
            return (
                f"Project blueprint saved to the Multi-Project Blueprint Vault as {entry['project_id']}. "
                f"I stored the core logic and your brainstorming notes in your local profile-safe database."
            )
        except Exception as exc:
            print(f"[main] Project vault save error: {exc}")
            return "I could not save that project idea to the vault yet."

    if any(keyword in lower_text for keyword in ["remember", "save", "store", "note"]):
        memory_entry = remember_memory(user_text)
        if memory_entry:
            key, value = memory_entry
            return f"Okay, I will remember {key} as {value}."

    profile_entry = learn_about_me(user_text)
    if profile_entry:
        key, value = profile_entry
        return f"Got it. I will remember that your {key} is {value}."

    if any(keyword in lower_text for keyword in ["who am i", "what do you know about me", "tell me about me", "what about me"]):
        return summarize_user_profile()

    if "i don't know about me" in lower_text or "you don't know about me" in lower_text:
        return "I don't have enough information about you yet. Tell me something such as 'remember that my favorite color is blue'."

    if any(keyword in lower_text for keyword in ["what is my", "what's my", "do you remember", "tell me my", "recall my"]):
        recalled = recall_memory(user_text)
        if recalled:
            key, value = recalled
            return f"Your {key} is {value}."

    return None


def handle_camera_command(user_text: str) -> str | None:
    lower_text = user_text.strip().lower()
    if not any(keyword in lower_text for keyword in ["camera", "live desk", "live camera", "rtsp", "desk camera", "look at my desk", "describe my desk", "analyze my desk", "what do you see", "what is on my desk"]):
        return None

    camera_result = capture_live_desk_snapshot()
    if not camera_result:
        return "I could not capture the live camera snapshot. Please check your RTSP URL and camera connection."

    try:
        vision_text = query_gemini_with_image(
            "Analyze the attached desk snapshot. Describe visible items, gadgets, screen details, and any potential hardware or wiring issues. Remember physical objects to help me identify your desk tools later.",
            camera_result["path"],
        )
        remember_visual_objects(vision_text)
        return f"Saved live desk snapshot to {camera_result['path']}. {camera_result['summary']} Gemini says: {vision_text}"
    except Exception as exc:
        print(f"[main] Vision Gemini error: {exc}")
        return f"Saved live desk snapshot to {camera_result['path']}. {camera_result['summary']}"


def handle_local_command(user_text: str) -> str | None:
    lower_text = user_text.strip().lower()

    camera_response = handle_camera_command(user_text)
    if camera_response is not None:
        return camera_response

    if "screenshot" in lower_text:
        path = take_screenshot()
        return f"Screenshot taken and saved to {path}."

    if "open notepad" in lower_text or lower_text == "notepad":
        if open_app("notepad"):
            return "Opening Notepad for you."
        return "I could not open Notepad on this machine."

    if any(keyword in lower_text for keyword in ["remind me", "timer", "set timer", "reminder", "schedule"]):
        schedule_result = schedule_reminder(user_text)
        if schedule_result:
            return schedule_result

    if "open chrome" in lower_text or "open browser" in lower_text or "chrome" == lower_text:
        if open_app("chrome"):
            return "Opening Chrome for you."
        return "I could not open Chrome on this machine."

    if any(keyword in lower_text for keyword in ["press", "shortcut", "hotkey", "key combination"]):
        if press_shortcut(user_text):
            return "Shortcut pressed."
        return "I could not recognize that shortcut command."

    if any(keyword in lower_text for keyword in ["cpu", "ram", "memory", "battery"]):
        return get_system_status()

    # Simple app orchestrator voice commands
    if lower_text.startswith("focus "):
        target = user_text.strip()[6:]
        wins = find_windows(target)
        if wins:
            if focus_window(wins[0]):
                return f"Brought {wins[0].title} to the foreground."
        return "I could not find that window."

    if lower_text.startswith("click at "):
        try:
            parts = lower_text.replace("click at ", "").split()
            x = int(parts[0].strip().strip(','))
            y = int(parts[1].strip())
            if move_and_click(x, y):
                return f"Clicked at {x}, {y}."
        except Exception:
            return "Could not parse coordinates. Use: click at 100 200"

    if lower_text.startswith("type "):
        txt = user_text.strip()[5:]
        if type_text(txt):
            return f"Typed: {txt}"
        return "Typing failed."

    if lower_text.startswith("hotkey "):
        keys = user_text.strip()[7:].split()
        if hotkey(*keys):
            return f"Pressed hotkey: {' + '.join(keys)}"
        return "Hotkey failed."

    if "weather" in lower_text:
        location = extract_weather_location(user_text)
        return get_weather(location)

    if "news" in lower_text or "headline" in lower_text:
        return get_top_news_headlines()

    if "youtube" in lower_text and any(term in lower_text for term in ["play", "search", "watch"]):
        query = extract_youtube_query(user_text)
        if play_youtube(query):
            return f"Playing {query} on YouTube."
        return "I could not play that YouTube video right now."

    if "wikipedia" in lower_text or any(lower_text.startswith(term) for term in ["who is", "what is", "define", "tell me about", "search wikipedia for"]):
        query = extract_wikipedia_query(user_text)
        return get_wikipedia_summary(query)

    return None


def handle_gemini_task(task_data: dict, user_text: str) -> str | None:
    task_type = str(task_data.get("task_type", "")).upper()
    if task_type == "WEB_AUTO":
        query = str(task_data.get("query", "")).strip()
        if not query:
            query = extract_youtube_query(user_text)
        if not query:
            return None
        if play_youtube(query):
            return f"Playing {query} on YouTube."
        return "I could not execute the browser automation task right now."

    if task_type in {"CODE", "CODE_EXEC", "GENERATE_CODE"}:
        code_text = str(task_data.get("code", "")).strip()
        if not code_text:
            # Some Gemini outputs may embed code under 'query' or 'payload'
            code_text = str(task_data.get("query", "")).strip()
        if not code_text:
            return "Gemini provided an empty code payload."

        background = bool(task_data.get("background", False))
        result = run_generated(code_text, filename_hint=task_data.get("filename"), background=background)
        # Track background PIDs so an emergency kill can terminate them.
        if result.get("status") == "started" and result.get("pid"):
            try:
                pid_val = int(result.get("pid"))
                with _bg_pids_lock:
                    _active_background_pids.add(pid_val)
            except Exception:
                pass
        if result.get("status") == "started":
            return f"Started generated program (pid {result.get('pid')}). Logs: {result.get('stdout_log')}, {result.get('stderr_log')}"
        if result.get("status") in {"finished", "timeout", "error"}:
            out = result.get("stdout") or ""
            err = result.get("stderr") or result.get("error") or ""
            return f"Execution finished. stdout:\n{out}\nstderr:\n{err}"
        return "Could not run generated code."

    return None


def main() -> None:
    # main runtime — background PID registry is module-level

    def _kill_background_processes() -> None:
        with _bg_pids_lock:
            pids = list(_active_background_pids)
        for pid in pids:
            try:
                if os.name == "nt":
                    # On Windows, prefer taskkill to reliably terminate GUI/console processes
                    try:
                        subprocess.run(["taskkill", "/F", "/PID", str(pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
                        print(f"[main] taskkill attempted for pid {pid}")
                    except Exception:
                        # As a fallback, try CTRL_C_EVENT for console processes
                        try:
                            os.kill(pid, signal.CTRL_C_EVENT)
                        except Exception:
                            pass
                else:
                    # POSIX: try graceful terminate then force kill
                    try:
                        os.kill(pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                    time.sleep(0.05)
                    try:
                        os.kill(pid, 0)
                        os.kill(pid, signal.SIGKILL)
                    except Exception:
                        pass
                print(f"[main] Killed/background-terminated process {pid}")
            except PermissionError:
                print(f"[main] Permission error killing pid {pid}")
            except Exception as exc:
                print(f"[main] Error killing pid {pid}: {exc}")
        with _bg_pids_lock:
            _active_background_pids.clear()

    def scheduler_notify(message: str) -> None:
        print(f"[scheduler] {message}")
        speak(message)

    scheduler = Scheduler(scheduler_notify)
    scheduler.start()

    orchestrator = get_orchestrator()
    orchestrator.start()

    security_manager = get_security_manager()
    security_manager.start()

    def _db_maintenance_loop() -> None:
        while True:
            try:
                vacuum_memory_database(keep_days=30)
            except Exception as exc:
                print(f"[main] Database maintenance error: {exc}")
            time.sleep(1800)

    maintenance_thread = threading.Thread(target=_db_maintenance_loop, daemon=True, name="arrow-db-maintenance")
    maintenance_thread.start()

    remote_control = SmartRemoteEngine()
    remote_control.start()
    remote_control.send_startup_message()

    def stop_arrow() -> None:
        scheduler.stop()
        remote_control.stop()
        security_manager.stop()
        speak("Arrow has been stopped.")
        os._exit(0)

    failsafe = FailSafe(stop_arrow)
    failsafe.start()

    user_profile = get_profile_data()
    if user_profile.get("name"):
        greeting_name = user_profile["name"]
        print(f"Arrow voice assistant starting for {greeting_name}. Say 'exit' or 'quit' to stop.")
        speak(f"Hello {greeting_name}, I am ready whenever you are.")
    else:
        print("Arrow voice assistant starting. Say 'exit' or 'quit' to stop.")
        speak("Hello, I am ready whenever you are.")

    try:
        security_manager.mark_activity("startup")
        desk_snapshot = capture_live_desk_snapshot()
        if desk_snapshot:
            try:
                analysis = query_gemini_with_image(
                    "Analyze this desk snapshot. Describe visible items, gadgets, screen details, and any potential hardware or wiring issues. Remember physical objects to help me identify your desk tools later.",
                    desk_snapshot["path"],
                )
                remember_visual_objects(analysis)
                speak(f"I also scanned your desk. {analysis}")
            except Exception as exc:
                print(f"[main] Desk awareness error: {exc}")
                speak("I captured a desk snapshot but could not analyze it right now.")
        while True:
            try:
                user_text = listen(timeout=10, phrase_time_limit=VOICE_RECORD_SECONDS, language=VOICE_LANGUAGE)
            except Exception as exc:
                print(f"[main] Voice input error: {exc}")
                user_text = ""

            if not user_text:
                print("[main] No input detected. Try again.")
                time.sleep(1)
                continue

            print(f"You said: {user_text}")
            orchestrator.broadcast("voice.command.received", {"text": user_text, "source": "voice"})
            security_manager.mark_activity("voice")

            if security_manager.is_locked():
                if is_panic_command(user_text):
                    security_manager.trigger_panic("voice panic while locked")
                    speak("Arrow is in secure stealth mode.")
                    continue
                pin = _extract_security_pin(user_text)
                if pin and security_manager.unlock(pin):
                    speak("Security lock released. Welcome back.")
                    continue
                security_manager.record_intrusion_attempt(user_text)
                speak("Arrow is locked for security. Enter your PIN to resume.")
                continue

            if is_panic_command(user_text):
                _kill_background_processes()
                result = security_manager.trigger_panic("voice panic command")
                print(f"[main] {result['message']}")
                speak(result["message"])
                continue

            # Highest-priority emergency listener: exact phrases that trigger
            # an immediate kill-switch and termination of background tasks.
            em_low = user_text.strip().lower()
            if em_low in {"arrow stop", "arrow stop execution"}:
                # Trigger app orchestrator kill-switch to stop run_sequence loops
                try:
                    trigger_kill_switch()
                except Exception:
                    pass
                # Kill any background processes started by generated code
                try:
                    _kill_background_processes()
                except Exception as exc:
                    print(f"[main] Error while killing background processes: {exc}")

                # Terminal warning and audible confirmation
                warning = '!!! EMERGENCY KILL-SWITCH ACTIVATED !!!'
                print(warning)
                try:
                    speak('Emergency kill switch activated. Stopping all automation now.')
                except Exception:
                    pass
                # Continue listening but ensure sequences remain stopped until cleared
                continue

            if user_text.strip().lower() in {"exit", "quit", "stop", "bye"}:
                print("Arrow is shutting down.")
                speak("Goodbye. See you soon.")
                break

            memory_response = orchestrator.route_command(user_text, handle_memory_command)
            if memory_response is not None:
                print(f"Arrow: {memory_response}")
                speak(memory_response)
                continue

            local_response = orchestrator.route_command(user_text, handle_local_command)
            if local_response is not None:
                print(f"Arrow: {local_response}")
                speak(local_response)
                continue

            command_response = handle_unrecognized_intent(user_text)
            if command_response.get("status") == "generated":
                print(f"Arrow: {command_response['message']}")
                speak(command_response['message'])
                continue

            try:
                response_text = query_gemini(user_text)
                print(f"Gemini: {response_text}")
                task_data = parse_gemini_task(response_text)
                if task_data:
                    task_response = handle_gemini_task(task_data, user_text)
                    if task_response:
                        print(f"Arrow: {task_response}")
                        speak(task_response)
                        continue

                speak(response_text)
            except Exception as exc:
                print(f"[main] Gemini error: {exc}")
                speak("Sorry, I could not reach Gemini. Please try again.")
    finally:
        scheduler.stop()
        remote_control.stop()
        security_manager.stop()


if __name__ == "__main__":
    main()
