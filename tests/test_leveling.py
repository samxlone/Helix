import importlib
import pytest

@pytest.mark.asyncio
async def test_leveling(tmp_path, monkeypatch):
    db_path = tmp_path / "lvl.sqlite"
    monkeypatch.setenv("DATABASE_URL", str(db_path))

    import utils.db as db
    importlib.reload(db)
    await db.init_db()

    from utils.leveling import award_xp, get_level_info, xp_needed_for_next

    lvl, xp = await get_level_info(1)
    assert lvl == 0 and xp == 0

    # award xp less than next
    needed = xp_needed_for_next(0)
    leveled, old, new = await award_xp(1, needed - 1)
    assert not leveled
    lvl, xp = await get_level_info(1)
    assert lvl == 0

    # award to level up
    leveled, old, new = await award_xp(1, 2)
    assert leveled
    lvl, xp = await get_level_info(1)
    assert lvl == 1
