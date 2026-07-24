import logging
import json
from typing import List, Dict, Any
from utils.db import get_connection

logger = logging.getLogger(__name__)


async def add_item(user_id: int, item_key: str, amount: int = 1, metadata: Dict[str, Any] | None = None):
    async with get_connection() as conn:
        # try update
        cur = await conn.execute("SELECT amount FROM inventory WHERE user_id = ? AND item_key = ?", (user_id, item_key))
        row = await cur.fetchone()
        await cur.close()
        if row:
            await conn.execute("UPDATE inventory SET amount = amount + ? WHERE user_id = ? AND item_key = ?", (amount, user_id, item_key))
        else:
            meta_text = None
            if metadata is not None:
                try:
                    meta_text = json.dumps(metadata)
                except Exception:
                    meta_text = None
            await conn.execute("INSERT INTO inventory (user_id, item_key, amount, metadata) VALUES (?, ?, ?, ?)", (user_id, item_key, amount, meta_text))
        await conn.commit()


async def remove_item(user_id: int, item_key: str, amount: int = 1) -> bool:
    async with get_connection() as conn:
        cur = await conn.execute("SELECT amount FROM inventory WHERE user_id = ? AND item_key = ?", (user_id, item_key))
        row = await cur.fetchone()
        await cur.close()
        if not row or int(row["amount"] or 0) < amount:
            return False
        new_amount = int(row["amount"] or 0) - amount
        if new_amount <= 0:
            await conn.execute("DELETE FROM inventory WHERE user_id = ? AND item_key = ?", (user_id, item_key))
        else:
            await conn.execute("UPDATE inventory SET amount = ? WHERE user_id = ? AND item_key = ?", (new_amount, user_id, item_key))
        await conn.commit()
        return True


async def get_inventory(user_id: int) -> List[Dict[str, Any]]:
    out = []
    async with get_connection() as conn:
        cur = await conn.execute("SELECT item_key, amount, metadata FROM inventory WHERE user_id = ?", (user_id,))
        rows = await cur.fetchall()
        await cur.close()
        for r in rows:
            out.append({"item_key": r["item_key"], "amount": int(r["amount"] or 0), "metadata": r["metadata"]})
    return out
