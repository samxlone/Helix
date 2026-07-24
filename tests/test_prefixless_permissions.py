import importlib
import pytest
from types import SimpleNamespace

class FakeGuild:
    def __init__(self, id=99, name="Test Guild"):
        self.id = id
        self.name = name

class FakeUser:
    def __init__(self, id=1, display_name="TestUser"):
        self.id = id
        self.display_name = display_name
        self.mention = f"<@{id}>"

class FakeContext:
    def __init__(self, author, guild=None):
        self.author = author
        self.guild = guild or FakeGuild()
        self.messages_sent = []

    async def send(self, *args, **kwargs):
        self.messages_sent.append((args, kwargs))
        return SimpleNamespace(id=123)

@pytest.mark.asyncio
async def test_prefixless_permissions_db(tmp_path, monkeypatch):
    # Setup test DB
    db_path = tmp_path / "test_prefixless.sqlite"
    monkeypatch.setenv("DATABASE_URL", str(db_path))

    import utils.db as db
    importlib.reload(db)
    await db.init_db()

    # Verify prefixless_permissions table exists and is empty
    async with db.get_connection() as conn:
        cur = await conn.execute("SELECT COUNT(*) as count FROM prefixless_permissions")
        row = await cur.fetchone()
        assert row["count"] == 0
        await cur.close()

        # Insert a permission manually to test DB structure
        await conn.execute("INSERT INTO prefixless_permissions (guild_id, user_id) VALUES (?, ?)", (99, 12345))
        await conn.commit()

        # Query to verify it was inserted
        cur = await conn.execute("SELECT 1 FROM prefixless_permissions WHERE guild_id = ? AND user_id = ?", (99, 12345))
        row = await cur.fetchone()
        assert row is not None
        await cur.close()

        # Query for non-existent permission
        cur = await conn.execute("SELECT 1 FROM prefixless_permissions WHERE guild_id = ? AND user_id = ?", (99, 99999))
        row = await cur.fetchone()
        assert row is None
        await cur.close()

        # Delete permission
        await conn.execute("DELETE FROM prefixless_permissions WHERE guild_id = ? AND user_id = ?", (99, 12345))
        await conn.commit()

        cur = await conn.execute("SELECT COUNT(*) as count FROM prefixless_permissions")
        row = await cur.fetchone()
        assert row["count"] == 0
        await cur.close()
