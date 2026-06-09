import sqlite3

import modules.memory as memory


def test_memory_vault_uses_profile_scoped_storage(tmp_path, monkeypatch):
    monkeypatch.setenv("ARROW_DATA_DIR", str(tmp_path))

    db_path = memory.get_memory_db_path()
    memory.initialize_memory_store()

    assert db_path.exists()
    assert db_path.parent == tmp_path
    with sqlite3.connect(db_path) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}

    assert "new_projects_vault" in tables
    assert "project_brainstorm_notes" in tables


def test_log_project_idea_records_project_and_notes(tmp_path, monkeypatch):
    monkeypatch.setenv("ARROW_DATA_DIR", str(tmp_path))
    memory.initialize_memory_store()

    entry = memory.log_project_idea(
        project_name="Smart Desk Hub",
        core_logic="Use vision and voice to coordinate desk automation.",
        notes="Prototype the gesture layer first.",
        project_id="smart-desk-hub",
    )

    assert entry["project_id"] == "smart-desk-hub"
    assert entry["project_name"] == "Smart Desk Hub"

    stored = memory.get_project_vault_entry("smart-desk-hub")
    assert stored["core_logic"] == "Use vision and voice to coordinate desk automation."

    notes = memory.list_project_notes("smart-desk-hub")
    assert notes
    assert notes[0]["note_text"] == "Prototype the gesture layer first."


def test_parse_project_logging_request_extracts_metadata():
    parsed = memory.parse_project_logging_request(
        "Arrow, log this idea for the new project Smart Desk Hub. Core logic: use hand gestures and voice commands. "
        "Idea note: prototype a safe mode for desk automation."
    )

    assert parsed["project_name"] == "Smart Desk Hub"
    assert "hand gestures" in parsed["core_logic"]
    assert "prototype a safe mode" in parsed["notes"]
