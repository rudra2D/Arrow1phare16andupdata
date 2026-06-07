"""Send text to Gemini and return the AI response."""

import base64
import json
import os
import requests

from config import GEMINI_API_KEY, GEMINI_MODEL
from modules.memory import get_personalized_context


GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta2/models/{model}:generateText"


def query_gemini(prompt_text: str) -> str:
    """Send prompt text to Gemini and return the generated response."""
    if not GEMINI_API_KEY or GEMINI_API_KEY == "YOUR_GEMINI_API_KEY_HERE":
        raise ValueError("Gemini API key is not configured in config.py")

    url = GEMINI_URL.format(model=GEMINI_MODEL)
    personal_context = get_personalized_context()
    if personal_context:
        prompt_text = f"{personal_context}\n\n{prompt_text}"

    headers = {
        "Content-Type": "application/json",
    }
    payload = {
        "prompt": {
            "text": prompt_text,
        },
        "temperature": 0.7,
        "maxOutputTokens": 512,
    }

    response = requests.post(url, params={"key": GEMINI_API_KEY}, headers=headers, data=json.dumps(payload), timeout=30)
    response.raise_for_status()

    data = response.json()
    candidates = data.get("candidates") or []
    if not candidates:
        raise RuntimeError(f"Gemini did not return a candidate response: {data}")

    output_text = candidates[0].get("output", "")
    return output_text.strip()


def _encode_image(image_path: str) -> str | None:
    if not os.path.exists(image_path):
        return None
    try:
        with open(image_path, "rb") as handle:
            return base64.b64encode(handle.read()).decode("utf-8")
    except Exception:
        return None


def query_gemini_with_image(prompt_text: str, image_path: str) -> str:
    """Send text and image data to Gemini and return the generated response."""
    if not GEMINI_API_KEY or GEMINI_API_KEY == "YOUR_GEMINI_API_KEY_HERE":
        raise ValueError("Gemini API key is not configured in config.py")

    image_b64 = _encode_image(image_path)
    if image_b64 is None:
        return query_gemini(prompt_text)

    url = GEMINI_URL.format(model=GEMINI_MODEL)
    personal_context = get_personalized_context()
    if personal_context:
        prompt_text = f"{personal_context}\n\n{prompt_text}"

    headers = {
        "Content-Type": "application/json",
    }
    payload = {
        "prompt": {
            "text": prompt_text,
            "image": {
                "imageBytes": image_b64,
            },
        },
        "temperature": 0.7,
        "maxOutputTokens": 512,
    }

    response = requests.post(url, params={"key": GEMINI_API_KEY}, headers=headers, data=json.dumps(payload), timeout=60)
    response.raise_for_status()

    data = response.json()
    candidates = data.get("candidates") or []
    if not candidates:
        raise RuntimeError(f"Gemini did not return a candidate response: {data}")

    output_text = candidates[0].get("output", "")
    return output_text.strip()


def parse_gemini_task(output_text: str) -> dict | None:
    """Parse a Gemini response for a task definition in JSON format."""
    if not output_text:
        return None

    trimmed = output_text.strip()
    start = trimmed.find("{")
    end = trimmed.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None

    json_text = trimmed[start:end + 1]
    try:
        data = json.loads(json_text)
    except json.JSONDecodeError:
        return None

    if isinstance(data, dict) and data.get("task_type"):
        return data
    return None


if __name__ == "__main__":
    test_prompt = "Hello Gemini, please respond with a short greeting."
    result = query_gemini(test_prompt)
    print(result)
