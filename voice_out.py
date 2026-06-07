"""Convert text to speech and play it through speakers."""

import os
import tempfile

try:
    import pyttsx3
except ImportError:
    pyttsx3 = None

try:
    from gtts import gTTS
except ImportError:
    gTTS = None

try:
    from playsound import playsound
except ImportError:
    playsound = None


def speak(text: str, language: str = "en") -> None:
    """Speak the provided text through system speakers."""
    if not text:
        return

    text = text.strip()

    if pyttsx3 is not None:
        try:
            engine = pyttsx3.init()
            engine.say(text)
            engine.runAndWait()
            return
        except Exception as exc:
            print(f"[voice_out] pyttsx3 failed: {exc}")

    if gTTS is not None and playsound is not None:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as temp_file:
            tts = gTTS(text=text, lang=language)
            tts.save(temp_file.name)
            try:
                playsound(temp_file.name)
            except Exception as exc:
                print(f"[voice_out] playsound playback failed: {exc}")
            finally:
                try:
                    os.unlink(temp_file.name)
                except OSError:
                    pass
        return

    raise RuntimeError(
        "No text-to-speech backend available. Install pyttsx3 or gtts+playsound."
    )


if __name__ == "__main__":
    speak("Hello from Arrow. Voice output is ready.")
