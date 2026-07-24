import importlib
import pytest

@pytest.mark.asyncio
async def test_inventory_basic(tmp_path, monkeypatch):
    db_path = tmp_path / "inv.sqlite"
    monkeypatch.setenv("DATABASE_URL", str(db_path))

    import utils.db as db
    importlib.reload(db)
    await db.init_db()

    from utils.inventory import add_item, get_inventory, remove_item

    # empty
    inv = await get_inventory(1)
    assert inv == []

    await add_item(1, "potion", 3, {"rarity": "common"})
    inv = await get_inventory(1)
    assert len(inv) == 1
    assert inv[0]["item_key"] == "potion"
    assert inv[0]["amount"] == 3

    ok = await remove_item(1, "potion", 1)
    assert ok
    inv = await get_inventory(1)
    assert inv[0]["amount"] == 2

    # remove more than exists
    ok = await remove_item(1, "potion", 5)
    assert not ok

    # remove remaining
    ok = await remove_item(1, "potion", 2)
    assert ok
    inv = await get_inventory(1)
    assert inv == []
