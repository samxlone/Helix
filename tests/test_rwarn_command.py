"""Unit tests for the rwarn (remove warnings) command."""
import pytest
import importlib
from types import SimpleNamespace


class FakeUser:
    def __init__(self, id, display_name="TestUser", name="TestUser", bot=False):
        self.id = id
        self.display_name = display_name
        self.name = name
        self.bot = bot
        self.mention = f"<@{id}>"
        self.top_role = SimpleNamespace(position=1)
        self.guild_permissions = SimpleNamespace(kick_members=True, manage_messages=True, manage_guild=True, administrator=False)

    def __str__(self):
        return f"{self.name}#{self.id}"


class FakeGuild:
    def __init__(self, id=100):
        self.id = id
        self.me = FakeUser(999, "Bot", "Bot", bot=True)
        self.me.top_role = SimpleNamespace(position=10)
        self.owner_id = 999


class FakeCtx:
    def __init__(self, author, guild=None):
        self.author = author
        self.guild = guild or FakeGuild()
        self.sent = []

    async def send(self, content=None, **kwargs):
        if content:
            self.sent.append(content)
        return self


@pytest.mark.asyncio
async def test_rwarn_command_flow(tmp_path, monkeypatch):
    db_path = tmp_path / "rwarn_test.sqlite"
    monkeypatch.setenv("DATABASE_URL", str(db_path))

    import utils.db as db
    importlib.reload(db)
    await db.init_db()

    import utils.modlog as modlog
    importlib.reload(modlog)

    # 1. Log 3 warnings for user 555
    await modlog.log_action(100, 111, 555, "warn", "Warning 1")
    await modlog.log_action(100, 111, 555, "warn", "Warning 2")
    await modlog.log_action(100, 111, 555, "warn", "Warning 3")

    logs_before = await modlog.fetch_logs_for_target(100, 555, action="warn")
    assert len(logs_before) == 3

    # 2. Test remove_warnings_for_target (remove 2)
    removed = await modlog.remove_warnings_for_target(100, 555, count=2)
    assert removed == 2

    logs_after = await modlog.fetch_logs_for_target(100, 555, action="warn")
    assert len(logs_after) == 1

    # 3. Test remove_warnings_for_target (clear all remaining)
    removed_all = await modlog.remove_warnings_for_target(100, 555, count=0)
    assert removed_all == 1

    logs_final = await modlog.fetch_logs_for_target(100, 555, action="warn")
    assert len(logs_final) == 0
