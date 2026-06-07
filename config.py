"""Configuration for Arrow voice assistant."""

# Put your Gemini API key here.
# You can get a free key from https://aistudio.google.com or Google Cloud.
GEMINI_API_KEY = "YOUR_GEMINI_API_KEY_HERE"

# Gemini model to use. Change this if you want a different Gemini model.
GEMINI_MODEL = "gemini-1.5-pro"

# Voice input / output settings.
VOICE_RECORD_SECONDS = 7
VOICE_LANGUAGE = "en-US"

# Telegram remote control settings.
TELEGRAM_BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
# Replace with your own Telegram user ID so only you can control Arrow remotely.
TELEGRAM_USER_ID = 0

# Wi-Fi camera RTSP feed for Arrow's live snapshot.
CAMERA_RTSP_URL = "rtsp://YOUR_CAMERA_RTSP_URL"
