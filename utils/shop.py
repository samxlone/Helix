import logging
from typing import List, Optional, Dict, Any
from utils.economy import get_balance, set_wallet
from utils.inventory import add_item

logger = logging.getLogger(__name__)

# Simple in-memory shop catalog for phase 1. Later this can be DB-backed.
DEFAULT_SHOP = [
    {"key": "potion", "price": 50, "name": "Health Potion", "metadata": {"heal": 50}},
    {"key": "elixir", "price": 300, "name": "Elixir", "metadata": {"heal": 500}},
    {"key": "sword", "price": 1000, "name": "Iron Sword", "metadata": {"attack": 5}},
]


def list_items() -> List[Dict[str, Any]]:
    return DEFAULT_SHOP.copy()


def get_item(key: str) -> Optional[Dict[str, Any]]:
    for it in DEFAULT_SHOP:
        if it["key"] == key:
            return it
    return None


async def buy_item(user_id: int, item_key: str, amount: int = 1) -> bool:
    """Attempt to buy `amount` of item_key for user_id. Returns True on success."""
    if amount <= 0:
        return False
    item = get_item(item_key)
    if not item:
        return False
    total_price = int(item["price"]) * int(amount)
    wallet, bank = await get_balance(user_id)
    if wallet < total_price:
        return False
    # deduct
    new_wallet = wallet - total_price
    await set_wallet(user_id, new_wallet)
    # add to inventory
    await add_item(user_id, item_key, amount, metadata=item.get("metadata"))
    return True
