"""Configuration for Arrow voice assistant."""

import os

# Put your Gemini API key here.
# You can get a free key from https://aistudio.google.com or Google Cloud.
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY_HERE")

# Gemini model to use. Change this if you want a different Gemini model.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-pro")

# Voice input / output settings.
VOICE_RECORD_SECONDS = int(os.getenv("VOICE_RECORD_SECONDS", "7"))
VOICE_LANGUAGE = os.getenv("VOICE_LANGUAGE", "en-US")

# Telegram remote control settings.
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()

def _int_env(key: str, default: int = 0) -> int:
    value = os.getenv(key)
    if value is None or value.strip() == "":
        return default
    try:
        return int(value.strip())
    except ValueError:
        return default

# Replace with your own Telegram user ID so only you can control Arrow remotely.
TELEGRAM_USER_ID = _int_env("TELEGRAM_USER_ID", 0)
# Strict admin chat ID for the Smart Remote Engine. Only this chat may execute commands.
ADMIN_CHAT_ID = _int_env("ADMIN_CHAT_ID", TELEGRAM_USER_ID)

# Private storage endpoints for Phase 7 file routing.
PRIVATE_SERVER_UPLOAD_URL = os.getenv("PRIVATE_SERVER_UPLOAD_URL", "").strip()
PRIVATE_BACKUP_UPLOAD_URL = os.getenv("PRIVATE_BACKUP_UPLOAD_URL", "").strip()
PRIVATE_STORAGE_AUTH_TOKEN = os.getenv("PRIVATE_STORAGE_AUTH_TOKEN", "").strip()

# Wi-Fi camera RTSP feed for Arrow's live snapshot.
CAMERA_RTSP_URL = os.getenv("CAMERA_RTSP_URL", "rtsp://YOUR_CAMERA_RTSP_URL")
