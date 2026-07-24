import os
import importlib
from pathlib import Path

import pytest


@pytest.mark.asyncio
async def test_log_and_fetch(tmp_path, monkeypatch):
    # Use a temporary sqlite file for isolation
    db_path = tmp_path / "testdb.sqlite"
    monkeypatch.setenv("DATABASE_URL", str(db_path))

    # Import db after setting env
    import utils.db as db
    importlib.reload(db)
    await db.init_db()

    from utils.modlog import log_action, fetch_logs, fetch_logs_for_target

    # Log an action
    case_id = await log_action(12345, 111, 222, "warn", "testing warn")
    assert isinstance(case_id, int) and case_id > 0

    # Fetch by guild
    logs = await fetch_logs(12345, limit=10)
    assert any(l["case_id"] == str(case_id) for l in logs)

    # Fetch by target
    t_logs = await fetch_logs_for_target(12345, 222, action="warn", limit=10)
    assert len(t_logs) >= 1
    assert t_logs[0]["action"] == "warn"
