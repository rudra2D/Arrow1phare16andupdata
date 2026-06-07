"""Voice input via microphone and speech-to-text."""

import speech_recognition as sr


def listen(timeout: int = None, phrase_time_limit: int = None, language: str = "en-US") -> str:
    """Listen on the default microphone and return recognized text."""
    recognizer = sr.Recognizer()
    with sr.Microphone() as source:
        print("[voice_in] Listening... speak now.")
        recognizer.adjust_for_ambient_noise(source, duration=1)
        audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)

    try:
        print("[voice_in] Recognizing speech...")
        return recognizer.recognize_google(audio, language=language)
    except sr.WaitTimeoutError:
        print("[voice_in] Listening timed out.")
        return ""
    except sr.UnknownValueError:
        print("[voice_in] Could not understand audio.")
        return ""
    except sr.RequestError as exc:
        print(f"[voice_in] Speech recognition service error: {exc}")
        return ""


if __name__ == "__main__":
    text = listen(timeout=10, phrase_time_limit=10)
    print(f"Recognized: {text}")
