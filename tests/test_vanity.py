import pytest
from utils.vanity_service import (
    clean_vanity_code,
    check_discord_vanity,
    add_vanity_tracker,
    remove_vanity_tracker,
    get_user_vanity_trackers,
    get_all_vanity_trackers,
)
from utils.db import init_db, get_connection

def test_clean_vanity_code():
    assert clean_vanity_code("https://discord.gg/helix") == "helix"
    assert clean_vanity_code("discord.gg/helix/") == "helix"
    assert clean_vanity_code("  https://discord.com/invite/myvanity  ") == "myvanity"

@pytest.mark.asyncio
async def test_vanity_db_trackers():
    await init_db()
    test_user_id = 777123456789

    # Clean up
    async with get_connection() as conn:
        await conn.execute("DELETE FROM vanity_trackers WHERE user_id = ?", (test_user_id,))
        await conn.commit()

    # Add tracker
    ok, code = await add_vanity_tracker(test_user_id, "https://discord.gg/testhelix")
    assert ok is True
    assert code == "testhelix"

    # Add duplicate tracker
    ok_dup, msg = await add_vanity_tracker(test_user_id, "testhelix")
    assert ok_dup is False

    # Get user trackers
    trackers = await get_user_vanity_trackers(test_user_id)
    assert trackers == ["testhelix"]

    # Get all trackers
    all_t = await get_all_vanity_trackers()
    assert any(t["user_id"] == test_user_id and t["vanity"] == "testhelix" for t in all_t)

    # Remove tracker
    removed = await remove_vanity_tracker(test_user_id, "testhelix")
    assert removed is True

    # Confirm removed
    trackers_after = await get_user_vanity_trackers(test_user_id)
    assert "testhelix" not in trackers_after

@pytest.mark.asyncio
async def test_check_discord_vanity_mock(monkeypatch):
    import aiohttp

    class DummyResponse:
        def __init__(self, status, json_data=None):
            self.status = status
            self._json = json_data or {}
        async def json(self):
            return self._json
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass

    class DummySession:
        def __init__(self, status=404, data=None):
            self.status = status
            self.data = data
        def get(self, url, **kwargs):
            return DummyResponse(self.status, self.data)
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass

    # Test 404 available
    monkeypatch.setattr(aiohttp, "ClientSession", lambda **kwargs: DummySession(404))
    status, data = await check_discord_vanity("freevanity123")
    assert status == "available"

    # Test 200 taken
    monkeypatch.setattr(aiohttp, "ClientSession", lambda **kwargs: DummySession(200, {"guild": {"id": "123", "name": "Helix Guild"}}))
    status_t, data_t = await check_discord_vanity("takenvanity")
    assert status_t == "taken"
    assert data_t["name"] == "Helix Guild"
