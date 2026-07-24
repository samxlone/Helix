import importlib
import pytest

@pytest.mark.asyncio
async def test_economy_basic(tmp_path, monkeypatch):
    db_path = tmp_path / "eco.sqlite"
    monkeypatch.setenv("DATABASE_URL", str(db_path))

    import utils.db as db
    importlib.reload(db)
    await db.init_db()

    from utils.economy import get_balance, add_wallet, transfer, claim_daily

    # new user
    w, b = await get_balance(1)
    assert w == 0 and b == 0

    await add_wallet(1, 500)
    w, b = await get_balance(1)
    assert w == 500

    # transfer insufficient
    ok = await transfer(1, 2, 600)
    assert not ok

    # transfer succeed
    ok = await transfer(1, 2, 200)
    assert ok
    w1, _ = await get_balance(1)
    w2, _ = await get_balance(2)
    assert w1 == 300 and w2 == 200

    # daily cooldown: first claim should succeed, second should fail
    ok, _ = await claim_daily(1)
    assert ok
    ok2, _ = await claim_daily(1)
    assert not ok2
