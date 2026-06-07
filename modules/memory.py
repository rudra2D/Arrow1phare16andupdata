"""Persistent memory storage for Arrow."""

import json
import re
import uuid
from pathlib import Path

MEMORY_FILE = Path("arrow_data/memory.json")
DEFAULT_MEMORY = {
    "preferences": {},
    "reminders": [],
    "profile": {},
    "desk_items": [],
}


def _ensure_memory_file() -> None:
    MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not MEMORY_FILE.exists():
        with MEMORY_FILE.open("w", encoding="utf-8") as handle:
            json.dump(DEFAULT_MEMORY, handle, indent=2)


def load_memory() -> dict:
    _ensure_memory_file()
    try:
        with MEMORY_FILE.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except json.JSONDecodeError:
        data = DEFAULT_MEMORY.copy()
    if not isinstance(data, dict):
        data = DEFAULT_MEMORY.copy()
    data.setdefault("preferences", {})
    data.setdefault("reminders", [])
    data.setdefault("profile", {})
    data.setdefault("desk_items", [])
    return data


def save_memory(data: dict) -> None:
    _ensure_memory_file()
    with MEMORY_FILE.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)


def set_preference(key: str, value: str) -> None:
    key = normalize_memory_key(key)
    value = value.strip()
    memory = load_memory()
    preferences = memory.setdefault("preferences", {})
    preferences[key] = value
    save_memory(memory)


def get_preference(key: str) -> str | None:
    key = normalize_memory_key(key)
    memory = load_memory()
    return memory.get("preferences", {}).get(key)


def get_profile_data() -> dict:
    memory = load_memory()
    return memory.setdefault("profile", {})


def set_profile_item(key: str, value: str) -> None:
    key = normalize_memory_key(key)
    value = value.strip()
    memory = load_memory()
    profile = memory.setdefault("profile", {})
    profile[key] = value
    save_memory(memory)


def append_profile_item(key: str, value: str) -> None:
    key = normalize_memory_key(key)
    value = value.strip()
    memory = load_memory()
    profile = memory.setdefault("profile", {})
    existing = profile.get(key, "")
    if existing:
        profile[key] = f"{existing}, {value}"
    else:
        profile[key] = value
    save_memory(memory)


def extract_profile_entry(text: str) -> tuple[str, str] | None:
    """Extract a profile key/value pair from direct user statements."""
    lowered = text.lower()
    explicit = extract_memory_entry(text)
    if explicit:
        return explicit

    patterns = [
        (r"my name(?: is)? (.+)", "name"),
        (r"my name (.+)", "name"),
        (r"i am from (.+)", "location"),
        (r"i live in (.+)", "location"),
        (r"i work as (.+)", "profession"),
        (r"i am a[n]? (.+)", "profession"),
        (r"i like (.+)", "likes"),
        (r"i love (.+)", "likes"),
        (r"i enjoy (.+)", "likes"),
        (r"i hate (.+)", "dislikes"),
        (r"(?:my full details are|my details are|here are my details|about me[:]?)(.+)", "bio"),
        (r"(?:this is my profile|here is my profile)[:]?(.+)", "bio"),
        (r"(?:learn this about me|learn about me|remember the following about me)[:]?\s*(.+)", "bio"),
        (r"(?:here is my details|here is my detail)[:]?\s*(.+)", "bio"),
    ]

    for pattern, key in patterns:
        match = re.search(pattern, lowered, re.DOTALL)
        if match:
            value = match.group(1).strip().rstrip("?.")
            if value:
                return key, value
    return None


def learn_about_me(text: str) -> tuple[str, str] | None:
    """Store profile information from a user statement."""
    entry = extract_profile_entry(text)
    if not entry:
        return None

    key, value = entry
    if key in {"likes", "dislikes"}:
        append_profile_item(key, value)
    else:
        set_profile_item(key, value)
    return key, value


def get_desk_items() -> list[str]:
    memory = load_memory()
    return memory.get("desk_items", [])


def add_desk_item(item: str) -> None:
    item = item.strip()
    if not item:
        return
    memory = load_memory()
    desk_items = memory.setdefault("desk_items", [])
    desk_items.append(item)
    save_memory(memory)


def get_desk_summary() -> str:
    items = get_desk_items()
    if not items:
        return ""
    unique_items = []
    for item in items:
        if item not in unique_items:
            unique_items.append(item)
    return "; ".join(unique_items)


def remember_visual_objects(description: str) -> None:
    add_desk_item(description)


def get_profile_item(key: str) -> str | None:
    key = normalize_memory_key(key)
    memory = load_memory()
    return memory.get("profile", {}).get(key)


def summarize_user_profile() -> str:
    profile = get_profile_data()
    if not profile:
        return "I don't know anything about you yet. Tell me something about yourself and I will remember it."

    entries = []
    if "name" in profile:
        entries.append(f"Your name is {profile['name']}.")
    if "bio" in profile:
        entries.append(f"About you: {profile['bio']}.")
    for key, value in profile.items():
        if key in {"name", "bio"}:
            continue
        entries.append(f"Your {key} is {value}.")
    desk_summary = get_desk_summary()
    if desk_summary:
        entries.append(f"I have recorded these desk items: {desk_summary}.")

    return " ".join(entries)


def get_personalized_context() -> str:
    profile = get_profile_data()
    if not profile:
        return ""

    lines = [f"{key}: {value}" for key, value in profile.items()]
    desk_summary = get_desk_summary()
    if desk_summary:
        lines.append(f"desk_items: {desk_summary}")
    return "User profile:\n" + "\n".join(lines)


def add_reminder(target_time: str, message: str) -> str:
    memory = load_memory()
    reminders = memory.setdefault("reminders", [])
    reminder_id = uuid.uuid4().hex
    reminders.append(
        {
            "id": reminder_id,
            "time": target_time,
            "message": message,
            "notified": False,
        }
    )
    save_memory(memory)
    return reminder_id


def get_due_reminders(now) -> list[dict]:
    memory = load_memory()
    reminders = memory.get("reminders", [])
    due = []
    for reminder in reminders:
        if reminder.get("notified"):
            continue
        try:
            target = __import__("datetime").datetime.fromisoformat(reminder["time"])
        except Exception:
            continue
        if target <= now:
            due.append(reminder)
    return due


def mark_reminder_triggered(reminder_id: str) -> None:
    memory = load_memory()
    reminders = memory.setdefault("reminders", [])
    for reminder in reminders:
        if reminder.get("id") == reminder_id:
            reminder["notified"] = True
            break
    save_memory(memory)


def normalize_memory_key(key: str) -> str:
    """Normalize keys for consistent storage and lookup."""
    return key.strip().lower().rstrip("?.")


def extract_memory_entry(text: str) -> tuple[str, str] | None:
    """Extract a key/value pair from a memory save command."""
    lowered = text.lower()
    patterns = [
        r"(?:remember|save|store|note)(?: that)? (?:my )?(.+?) (?:is|as|=|:|was) (.+)",
        r"(?:save|store|remember)(?: my)? (.+?) to (.+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, lowered)
        if match:
            key = normalize_memory_key(match.group(1))
            value = match.group(2).strip().rstrip("?.")
            if key and value:
                return key, value
    return None


def remember_memory(text: str) -> tuple[str, str] | None:
    """Store a memory preference from a user command."""
    entry = extract_memory_entry(text)
    if not entry:
        return None

    key, value = entry
    set_preference(key, value)
    return key, value


def recall_memory(text: str) -> tuple[str, str] | None:
    """Recall a stored preference from a user query."""
    lowered = text.lower()
    patterns = [
        r"(?:what is|what's|tell me|do you remember|show me|recall)(?: my)? (.+?)(?:\?|\.|$)",
        r"(?:my )?(.+?)(?:\?|\.|$)",
    ]

    for pattern in patterns:
        match = re.search(pattern, lowered)
        if match:
            key = normalize_memory_key(match.group(1))
            value = get_preference(key)
            if not value:
                value = get_profile_item(key)
            if value:
                return key, value
    return None
