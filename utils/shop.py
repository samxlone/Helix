import logging
from typing import List, Optional, Dict, Any
from utils.economy import get_balance, set_wallet
from utils.inventory import add_item

logger = logging.getLogger(__name__)

DEFAULT_SHOP = [
    # Protection & Shields
    {
        "key": "shield",
        "name": "Robbery Shield",
        "price": 1500,
        "category": "Protection",
        "emoji": "🛡️",
        "description": "Blocks the next robbery attempt against your wallet.",
        "metadata": {"type": "protection", "effect": "shield"}
    },
    {
        "key": "insurance",
        "name": "Bank Insurance",
        "price": 3000,
        "category": "Protection",
        "emoji": "🎟️",
        "description": "Protects your bank balance from unexpected losses.",
        "metadata": {"type": "protection", "effect": "insurance"}
    },
    # Boosters & Utilities
    {
        "key": "coffee",
        "name": "Energy Drink",
        "price": 400,
        "category": "Boosters",
        "emoji": "☕",
        "description": "Instantly resets your !work cooldown so you can work again.",
        "metadata": {"type": "consumable", "effect": "reset_work"}
    },
    {
        "key": "clover",
        "name": "Lucky Clover",
        "price": 1200,
        "category": "Boosters",
        "emoji": "🍀",
        "description": "Increases earnings from work and casino games.",
        "metadata": {"type": "booster", "effect": "luck"}
    },
    {
        "key": "xp_boost",
        "name": "2x XP Potion",
        "price": 800,
        "category": "Boosters",
        "emoji": "🧪",
        "description": "Doubles chat XP earned for 1 hour.",
        "metadata": {"type": "booster", "effect": "xp_multiplier"}
    },
    # RPG Gear
    {
        "key": "potion",
        "name": "Health Potion",
        "price": 100,
        "category": "RPG Gear",
        "emoji": "🍷",
        "description": "Restores 50 HP during RPG activities.",
        "metadata": {"heal": 50}
    },
    {
        "key": "elixir",
        "name": "Mana Elixir",
        "price": 300,
        "category": "RPG Gear",
        "emoji": "🧪",
        "description": "Restores 500 Mana points.",
        "metadata": {"heal": 500}
    },
    {
        "key": "sword",
        "name": "Iron Sword",
        "price": 1000,
        "category": "RPG Gear",
        "emoji": "⚔️",
        "description": "Increases attack power by +5.",
        "metadata": {"attack": 5}
    },
    {
        "key": "bow",
        "name": "Hunter's Bow",
        "price": 2500,
        "category": "RPG Gear",
        "emoji": "🏹",
        "description": "High precision ranged weapon for hunting.",
        "metadata": {"attack": 15}
    },
    # Collectibles & Flex
    {
        "key": "diamond",
        "name": "Diamond Gem",
        "price": 15000,
        "category": "Collectibles",
        "emoji": "💎",
        "description": "Rare gemstone to show off your wealth.",
        "metadata": {"type": "flex"}
    },
    {
        "key": "trophy",
        "name": "Champion Trophy",
        "price": 25000,
        "category": "Collectibles",
        "emoji": "🏆",
        "description": "Hall-of-fame trophy awarded to top flexers.",
        "metadata": {"type": "flex"}
    },
    {
        "key": "crown",
        "name": "Golden Crown",
        "price": 50000,
        "category": "Collectibles",
        "emoji": "👑",
        "description": "The ultimate status symbol reserved for server royalty.",
        "metadata": {"type": "flex"}
    },
]


def list_items(category: Optional[str] = None) -> List[Dict[str, Any]]:
    if not category or category.lower() == "all":
        return DEFAULT_SHOP.copy()
    return [it for it in DEFAULT_SHOP if it.get("category", "").lower() == category.lower()]


def get_item(key: str) -> Optional[Dict[str, Any]]:
    for it in DEFAULT_SHOP:
        if it["key"].lower() == key.lower():
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
    await add_item(user_id, item["key"], amount, metadata=item.get("metadata"))
    return True

