import importlib
import pytest

@pytest.mark.asyncio
async def test_shop_buy_and_rob(tmp_path, monkeypatch):
    db_path = tmp_path / "shop.sqlite"
    monkeypatch.setenv("DATABASE_URL", str(db_path))

    import utils.db as db
    importlib.reload(db)
    await db.init_db()

    from utils.shop import list_items, get_item, buy_item
    from utils.economy import add_wallet, get_balance, rob

    # seed users
    await add_wallet(1, 500)
    await add_wallet(2, 200)

    items = list_items()
    assert any(i['key']=='potion' for i in items)

    p_price = get_item('potion')['price']
    # buy potion
    ok = await buy_item(1, 'potion', 2)
    assert ok
    w, b = await get_balance(1)
    assert w == 500 - (p_price * 2)

    # attempt buy with insufficient funds
    ok = await buy_item(2, 'sword', 1)
    assert not ok

    # test rob: force success by monkeypatching random.random
    import random
    monkeypatch.setattr(random, 'random', lambda: 0.01)
    success, stolen = await rob(1, 2, chance=0.9)
    # attacker should have gotten some coins and victim lost them
    assert success
    w1, _ = await get_balance(1)
    w2, _ = await get_balance(2)
    assert w1 + w2 == 500 + 200 - (p_price * 2)  # total money conserved

