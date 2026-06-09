"""Persistent memory storage for Arrow."""

import datetime
import json
import os
import re
import sqlite3
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


def _profile_storage_root() -> Path:
    env_path = os.getenv("ARROW_DATA_DIR")
    if env_path:
        candidate = Path(env_path).expanduser()
        return candidate if candidate.suffix in {".db", ".sqlite"} else candidate

    if os.name == "nt":
        local_app = os.getenv("LOCALAPPDATA")
        if local_app:
            return Path(local_app) / "Arrow"
        return Path.home() / "AppData" / "Local" / "Arrow"

    return Path.home() / ".arrow" / "Arrow"


def get_memory_db_path() -> Path:
    env_path = os.getenv("ARROW_DATA_DIR")
    if env_path:
        candidate = Path(env_path).expanduser()
        if candidate.suffix in {".db", ".sqlite"}:
            return candidate
        return candidate / "arrow_memory.sqlite"

    if os.name == "nt":
        local_app = os.getenv("LOCALAPPDATA")
        base = Path(local_app) if local_app else Path.home() / "AppData" / "Local"
        return base / "Arrow" / "arrow_memory.sqlite"

    return Path.home() / ".arrow" / "Arrow" / "arrow_memory.sqlite"


def _ensure_profile_storage() -> Path:
    path = get_memory_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        try:
            os.chmod(path.parent, 0o700)
        except OSError:
            pass
    return path


def _connect_memory_db() -> sqlite3.Connection:
    path = _ensure_profile_storage()
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def initialize_memory_store() -> Path:
    """Initialize the local SQLite vault used for project blueprint storage."""
    path = _ensure_profile_storage()
    with _connect_memory_db() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS new_projects_vault (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT UNIQUE NOT NULL,
                project_name TEXT NOT NULL,
                core_logic TEXT,
                status TEXT NOT NULL DEFAULT 'draft',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                notes_count INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS project_brainstorm_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                note_text TEXT NOT NULL,
                note_type TEXT NOT NULL DEFAULT 'idea',
                source TEXT NOT NULL DEFAULT 'voice',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(project_id) REFERENCES new_projects_vault(project_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS dynamic_commands_vault (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                command_id TEXT UNIQUE NOT NULL,
                command_name TEXT NOT NULL,
                intent TEXT NOT NULL,
                logic TEXT NOT NULL,
                encrypted_logic TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'draft',
                version TEXT NOT NULL DEFAULT 'v1',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_run TEXT
            );

            CREATE TABLE IF NOT EXISTS dynamic_command_revisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                command_id TEXT NOT NULL,
                revision_id TEXT UNIQUE NOT NULL,
                version TEXT NOT NULL,
                encrypted_logic TEXT NOT NULL,
                summary TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(command_id) REFERENCES dynamic_commands_vault(command_id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_new_projects_vault_project_id ON new_projects_vault(project_id);
            CREATE INDEX IF NOT EXISTS idx_project_brainstorm_notes_project_id ON project_brainstorm_notes(project_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_dynamic_commands_vault_command_id ON dynamic_commands_vault(command_id);
            CREATE INDEX IF NOT EXISTS idx_dynamic_command_revisions_command_id ON dynamic_command_revisions(command_id, created_at DESC);
            """
        )
    return path


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


def _slugify_project_id(project_name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", project_name.lower()).strip("-")
    return slug or f"project-{uuid.uuid4().hex[:8]}"


def parse_project_logging_request(text: str) -> dict:
    """Parse a natural-language project-idea request into vault-ready fields."""
    cleaned = text.strip()
    project_name = "New Project"

    name_match = re.search(r"(?:for the new project|new project)\s+([^.;\n]+?)(?:\.|;|$)", cleaned, re.IGNORECASE)
    if not name_match:
        name_match = re.search(r"(?:project name|project)\s*[:=]\s*([^.;\n]+)", cleaned, re.IGNORECASE)
    if name_match:
        project_name = name_match.group(1).strip(" .;:-")

    core_logic = ""
    core_match = re.search(
        r"(?:core logic|core concept|concept|logic)\s*[:\-]\s*(.+?)(?=(?:\.\s+(?:idea note|note|notes|brainstorm|summary)\s*[:\-])|$)",
        cleaned,
        re.IGNORECASE | re.DOTALL,
    )
    if core_match:
        core_logic = core_match.group(1).strip().strip(". ")

    notes = ""
    note_match = re.search(
        r"(?:idea note|note|notes|brainstorm(?:ing)? note|human idea)\s*[:\-]\s*(.+)",
        cleaned,
        re.IGNORECASE | re.DOTALL,
    )
    if note_match:
        notes = note_match.group(1).strip().strip(". ")
    elif "core logic" in cleaned.lower():
        notes = re.sub(r"(?i)\bcore logic\s*[:\-].*?", "", cleaned).strip(" .;")
    else:
        notes = cleaned

    return {
        "project_name": project_name,
        "project_id": _slugify_project_id(project_name),
        "core_logic": core_logic or "Captured from voice command.",
        "notes": notes.strip(),
    }


def log_project_idea(project_name: str, core_logic: str = "", notes: str = "", project_id: str | None = None) -> dict:
    """Save a project blueprint into the profile-scoped SQLite vault."""
    parsed = parse_project_logging_request(project_name if not core_logic and not notes else f"new project {project_name}. Core logic: {core_logic}. Note: {notes}")
    if project_name:
        parsed["project_name"] = project_name.strip() or parsed["project_name"]
    if core_logic:
        parsed["core_logic"] = core_logic.strip()
    if notes:
        parsed["notes"] = notes.strip()
    if project_id:
        parsed["project_id"] = project_id.strip()

    initialize_memory_store()
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    with _connect_memory_db() as connection:
        existing = connection.execute(
            "SELECT project_id, project_name, core_logic FROM new_projects_vault WHERE project_id = ?",
            (parsed["project_id"],),
        ).fetchone()

        if existing:
            connection.execute(
                "UPDATE new_projects_vault SET project_name = ?, core_logic = ?, updated_at = ? WHERE project_id = ?",
                (parsed["project_name"], parsed["core_logic"], now, parsed["project_id"]),
            )
        else:
            connection.execute(
                "INSERT INTO new_projects_vault (project_id, project_name, core_logic, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (parsed["project_id"], parsed["project_name"], parsed["core_logic"], now, now),
            )

        if parsed["notes"]:
            connection.execute(
                "INSERT INTO project_brainstorm_notes (project_id, note_text, note_type, source, created_at) VALUES (?, ?, 'idea', 'voice', ?)",
                (parsed["project_id"], parsed["notes"], now),
            )

        connection.execute(
            "UPDATE new_projects_vault SET notes_count = (SELECT COUNT(*) FROM project_brainstorm_notes WHERE project_id = ?) WHERE project_id = ?",
            (parsed["project_id"], parsed["project_id"]),
        )

    return {
        "project_id": parsed["project_id"],
        "project_name": parsed["project_name"],
        "core_logic": parsed["core_logic"],
        "notes": parsed["notes"],
        "created_at": now,
        "db_path": str(get_memory_db_path()),
    }


def get_dynamic_command_count() -> int:
    """Count how many Phase 15 dynamic commands are stored in the vault."""
    initialize_memory_store()
    with _connect_memory_db() as connection:
        row = connection.execute("SELECT COUNT(*) FROM dynamic_commands_vault").fetchone()
    return int(row[0]) if row else 0


def vacuum_memory_database(keep_days: int = 30) -> dict:
    """Vacuum the SQLite memory vault and remove old system logs to reduce bloat."""
    initialize_memory_store()
    path = get_memory_db_path()
    cutoff = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=keep_days)).isoformat()

    with _connect_memory_db() as connection:
        old_log_count = connection.execute(
            "SELECT COUNT(*) FROM project_brainstorm_notes WHERE note_type IN ('system', 'system_log') AND created_at < ?",
            (cutoff,),
        ).fetchone()[0]
        if old_log_count:
            connection.execute(
                "DELETE FROM project_brainstorm_notes WHERE note_type IN ('system', 'system_log') AND created_at < ?",
                (cutoff,),
            )

        old_revision_count = connection.execute(
            "SELECT COUNT(*) FROM dynamic_command_revisions WHERE created_at < ?",
            (cutoff,),
        ).fetchone()[0]
        if old_revision_count:
            connection.execute(
                "DELETE FROM dynamic_command_revisions WHERE created_at < ?",
                (cutoff,),
            )

        connection.commit()

    vacuum_connection = sqlite3.connect(path)
    vacuum_connection.row_factory = sqlite3.Row
    vacuum_connection.execute("PRAGMA busy_timeout = 5000")
    vacuum_warning = None
    try:
        vacuum_connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        vacuum_connection.execute("PRAGMA journal_mode=DELETE")
        vacuum_connection.execute("VACUUM")
        vacuum_connection.execute("PRAGMA journal_mode=WAL")
        vacuum_connection.commit()
    except sqlite3.Error as exc:
        vacuum_warning = str(exc)
        try:
            vacuum_connection.execute("PRAGMA journal_mode=WAL")
            vacuum_connection.commit()
        except sqlite3.Error:
            pass
    finally:
        vacuum_connection.close()

    return {
        "status": "ok",
        "db_path": str(path),
        "keep_days": keep_days,
        "purged_system_logs": int(old_log_count),
        "purged_revisions": int(old_revision_count),
        **({"warning": vacuum_warning} if vacuum_warning else {}),
    }


def get_project_vault_entry(project_id: str) -> dict | None:
    initialize_memory_store()
    with _connect_memory_db() as connection:
        row = connection.execute(
            "SELECT project_id, project_name, core_logic, status, created_at, updated_at, notes_count FROM new_projects_vault WHERE project_id = ?",
            (project_id,),
        ).fetchone()
    return dict(row) if row else None


def list_project_notes(project_id: str) -> list[dict]:
    initialize_memory_store()
    with _connect_memory_db() as connection:
        rows = connection.execute(
            "SELECT id, project_id, note_text, note_type, source, created_at FROM project_brainstorm_notes WHERE project_id = ? ORDER BY created_at DESC",
            (project_id,),
        ).fetchall()
    return [dict(row) for row in rows]


ORCHESTRATOR_PLUGIN = {
    "name": "memory",
    "handler": "orchestrator_event_hook",
    "events": ("*",),
    "priority": 20,
}


def orchestrator_event_hook(event_type: str, payload: dict) -> dict:
    """Persist phase events into the local memory vault for future review."""
    try:
        initialize_memory_store()
        note = f"Phase event {event_type}: {payload}"
        log_project_idea(
            project_name="Arrow Event Ledger",
            core_logic="Record orchestrator broadcasts into the local project-memory vault.",
            notes=note,
            project_id="arrow-event-ledger",
        )
        return {"status": "recorded", "event_type": event_type}
    except Exception as exc:
        return {"status": "skipped", "error": str(exc)}


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
