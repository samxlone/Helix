import logging
import time
import random
from typing import Tuple, Optional
import json
from datetime import datetime, timedelta, timezone

from utils.db import get_connection

logger = logging.getLogger(__name__)

DAILY_COOLDOWN_SECONDS = 24 * 3600
WORK_COOLDOWN_SECONDS = 60 * 60
ROB_COOLDOWN_SECONDS = 10 * 60  # 10 minutes cooldown for rob


async def _ensure_user(user_id: int):
    async with get_connection() as conn:
        await conn.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        await conn.execute("INSERT OR IGNORE INTO economy (user_id, wallet, bank) VALUES (?, 0, 0)", (user_id,))
        await conn.commit()


async def get_balance(user_id: int) -> Tuple[int, int]:
    await _ensure_user(user_id)
    async with get_connection() as conn:
        cur = await conn.execute("SELECT wallet, bank FROM economy WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        await cur.close()
        if row:
            return int(row["wallet"] or 0), int(row["bank"] or 0)
        return 0, 0


async def add_wallet(user_id: int, amount: int) -> int:
    await _ensure_user(user_id)
    async with get_connection() as conn:
        await conn.execute("UPDATE economy SET wallet = wallet + ? WHERE user_id = ?", (int(amount), user_id))
        await conn.commit()
        w, b = await get_balance(user_id)
        return w


async def set_wallet(user_id: int, amount: int) -> int:
    await _ensure_user(user_id)
    async with get_connection() as conn:
        await conn.execute("UPDATE economy SET wallet = ? WHERE user_id = ?", (int(amount), user_id))
        await conn.commit()
        w, b = await get_balance(user_id)
        return w


async def transfer(from_user: int, to_user: int, amount: int) -> bool:
    if amount <= 0:
        return False
    await _ensure_user(from_user)
    await _ensure_user(to_user)
    async with get_connection() as conn:
        cur = await conn.execute("SELECT wallet FROM economy WHERE user_id = ?", (from_user,))
        row = await cur.fetchone()
        await cur.close()
        if not row or int(row["wallet"] or 0) < amount:
            return False
        await conn.execute("UPDATE economy SET wallet = wallet - ? WHERE user_id = ?", (amount, from_user))
        await conn.execute("UPDATE economy SET wallet = wallet + ? WHERE user_id = ?", (amount, to_user))
        await conn.commit()
        return True


async def _get_cooldown(user_id: int, key: str) -> Optional[datetime]:
    async with get_connection() as conn:
        cur = await conn.execute("SELECT expires_at FROM cooldowns WHERE user_id = ? AND key = ?", (user_id, key))
        row = await cur.fetchone()
        await cur.close()
        if row and row["expires_at"]:
            try:
                return datetime.fromisoformat(row["expires_at"])
            except Exception:
                return None
        return None


async def _set_cooldown(user_id: int, key: str, until: datetime):
    async with get_connection() as conn:
        await conn.execute("INSERT OR REPLACE INTO cooldowns (user_id, key, expires_at) VALUES (?, ?, ?)", (user_id, key, until.isoformat()))
        await conn.commit()


async def claim_daily(user_id: int, amount: int = 500) -> Tuple[bool, int]:
    """Return (claimed, new_wallet_amount)"""
    await _ensure_user(user_id)
    cd = await _get_cooldown(user_id, "daily")
    now = datetime.now(timezone.utc)
    if cd and cd > now:
        return False, 0
    await add_wallet(user_id, amount)
    await _set_cooldown(user_id, "daily", now + timedelta(seconds=DAILY_COOLDOWN_SECONDS))
    w, b = await get_balance(user_id)
    return True, w


async def do_work(user_id: int, amount: int = 100) -> Tuple[bool, int]:
    await _ensure_user(user_id)
    cd = await _get_cooldown(user_id, "work")
    now = datetime.now(timezone.utc)
    if cd and cd > now:
        return False, 0
    await add_wallet(user_id, amount)
    await _set_cooldown(user_id, "work", now + timedelta(seconds=WORK_COOLDOWN_SECONDS))
    w, b = await get_balance(user_id)
    return True, w


async def reset_work_cooldown(user_id: int):
    """Clear work cooldown for a user."""
    async with get_connection() as conn:
        await conn.execute("DELETE FROM cooldowns WHERE user_id = ? AND key = 'work'", (user_id,))
        await conn.commit()



async def deposit_to_bank(user_id: int, amount: int) -> bool:
    """Move from wallet to bank. Returns True on success."""
    if amount <= 0:
        return False
    await _ensure_user(user_id)
    async with get_connection() as conn:
        cur = await conn.execute("SELECT wallet, bank FROM economy WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        await cur.close()
        wallet = int(row["wallet"] or 0)
        if wallet < amount:
            return False
        await conn.execute("UPDATE economy SET wallet = wallet - ?, bank = bank + ? WHERE user_id = ?", (amount, amount, user_id))
        await conn.commit()
        return True


async def withdraw_from_bank(user_id: int, amount: int) -> bool:
    """Move from bank to wallet. Returns True on success."""
    if amount <= 0:
        return False
    await _ensure_user(user_id)
    async with get_connection() as conn:
        cur = await conn.execute("SELECT bank FROM economy WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        await cur.close()
        bank = int(row["bank"] or 0)
        if bank < amount:
            return False
        await conn.execute("UPDATE economy SET bank = bank - ?, wallet = wallet + ? WHERE user_id = ?", (amount, amount, user_id))
        await conn.commit()
        return True


async def rob(attacker_id: int, victim_id: int, *, chance: float = 0.5, min_amount: int = 10) -> Tuple[bool, int]:
    """Attempt to rob victim. Returns (success, stolen_amount). Chance is probability of success.
    A robbery steals between min_amount and up to half of victim's wallet.
    Applies a cooldown (ROB_COOLDOWN_SECONDS) per attacker.
    """
    if attacker_id == victim_id:
        return False, 0
    await _ensure_user(attacker_id)
    await _ensure_user(victim_id)

    # check cooldown
    cd = await _get_cooldown(attacker_id, "rob")
    now = datetime.now(timezone.utc)
    if cd and cd > now:
        return False, 0

    # Check if victim has a Robbery Shield in inventory
    from utils.inventory import remove_item
    has_shield = await remove_item(victim_id, "shield", 1)
    if has_shield:
        await _set_cooldown(attacker_id, "rob", now + timedelta(seconds=ROB_COOLDOWN_SECONDS))
        return False, -1  # -1 indicates blocked by shield

    async with get_connection() as conn:

        cur = await conn.execute("SELECT wallet FROM economy WHERE user_id = ?", (victim_id,))
        row = await cur.fetchone()
        await cur.close()
        victim_wallet = int(row["wallet"] or 0)
        if victim_wallet < min_amount:
            # nothing to steal
            await _set_cooldown(attacker_id, "rob", now + timedelta(seconds=ROB_COOLDOWN_SECONDS))
            return False, 0

        if random.random() > chance:
            # failed robbery
            await _set_cooldown(attacker_id, "rob", now + timedelta(seconds=ROB_COOLDOWN_SECONDS))
            return False, 0

        # compute stolen amount
        max_steal = max(min_amount, victim_wallet // 2)
        stolen = min(victim_wallet, random.randint(min_amount, max_steal))
        # perform transfer
        await conn.execute("UPDATE economy SET wallet = wallet - ? WHERE user_id = ?", (stolen, victim_id))
        await conn.execute("UPDATE economy SET wallet = wallet + ? WHERE user_id = ?", (stolen, attacker_id))
        await conn.commit()
        await _set_cooldown(attacker_id, "rob", now + timedelta(seconds=ROB_COOLDOWN_SECONDS))
        return True, stolen


# expose cooldown helpers for reuse
async def _get_cooldown(user_id: int, key: str) -> Optional[datetime]:
    async with get_connection() as conn:
        cur = await conn.execute("SELECT expires_at FROM cooldowns WHERE user_id = ? AND key = ?", (user_id, key))
        row = await cur.fetchone()
        await cur.close()
        if row and row["expires_at"]:
            try:
                return datetime.fromisoformat(row["expires_at"])
            except Exception:
                return None
        return None


async def _set_cooldown(user_id: int, key: str, until: datetime):
    async with get_connection() as conn:
        await conn.execute("INSERT OR REPLACE INTO cooldowns (user_id, key, expires_at) VALUES (?, ?, ?)", (user_id, key, until.isoformat()))
        await conn.commit()


async def get_networth_leaderboard(limit: int = 100) -> list[dict]:
    """Fetch top users ordered by (wallet + bank) net worth."""
    async with get_connection() as conn:
        cur = await conn.execute(
            "SELECT user_id, wallet, bank, (wallet + bank) AS networth FROM economy ORDER BY networth DESC LIMIT ?",
            (int(limit),)
        )
        rows = await cur.fetchall()
        await cur.close()
        return [
            {
                "user_id": int(r["user_id"]),
                "wallet": int(r["wallet"] or 0),
                "bank": int(r["bank"] or 0),
                "networth": int(r["networth"] or 0),
            }
            for r in rows
        ]


async def get_user_networth_rank(user_id: int) -> tuple[int, int]:
    """Return (rank, networth) for a specific user."""
    await _ensure_user(user_id)
    async with get_connection() as conn:
        cur = await conn.execute(
            """
            SELECT COUNT(*) + 1 AS rank,
                   (SELECT (wallet + bank) FROM economy WHERE user_id = ?) AS user_networth
            FROM economy
            WHERE (wallet + bank) > (SELECT (wallet + bank) FROM economy WHERE user_id = ?)
            """,
            (user_id, user_id)
        )
        row = await cur.fetchone()
        await cur.close()
        if row:
            rank = int(row["rank"] or 1)
            networth = int(row["user_networth"] or 0)
            return rank, networth
        return 1, 0

