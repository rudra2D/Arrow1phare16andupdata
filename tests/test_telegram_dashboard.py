import sqlite3

from modules.memory import get_dynamic_command_count, initialize_memory_store, vacuum_memory_database
from modules.telegram_bot import build_dashboard_report


def test_build_dashboard_report_includes_phase_summary(monkeypatch, tmp_path):
    monkeypatch.setenv("ARROW_DATA_DIR", str(tmp_path))
    initialize_memory_store()

    report = build_dashboard_report()

    assert "Arrow Smart Dashboard" in report
    assert "Phase 14 orchestration" in report
    assert "Encryption health" in report
    assert "Phase 15 dynamic commands" in report
    assert str(get_dynamic_command_count()) in report


def test_vacuum_memory_database_removes_old_system_logs(monkeypatch, tmp_path):
    monkeypatch.setenv("ARROW_DATA_DIR", str(tmp_path))
    initialize_memory_store()

    db_path = tmp_path / "arrow_memory.sqlite"
    connection = sqlite3.connect(db_path)
    connection.execute(
        "INSERT INTO project_brainstorm_notes (project_id, note_text, note_type, source, created_at) VALUES (?, ?, ?, ?, ?)",
        ("arrow-event-ledger", "old maintenance log", "system", "system", "2000-01-01T00:00:00+00:00"),
    )
    connection.commit()
    connection.close()

    result = vacuum_memory_database(keep_days=0)

    assert result["status"] == "ok"
    assert result["purged_system_logs"] >= 1

    connection = sqlite3.connect(db_path)
    remaining = connection.execute(
        "SELECT COUNT(*) FROM project_brainstorm_notes WHERE note_type IN ('system', 'system_log')"
    ).fetchone()[0]
    connection.close()

    assert remaining == 0
