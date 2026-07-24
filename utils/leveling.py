import logging
from typing import Tuple, Optional
from datetime import datetime, timezone

from utils.db import get_connection

logger = logging.getLogger(__name__)


def xp_needed_for_next(level: int) -> int:
    # Next XP = 5 × Level² + 50 × Level + 100
    return 5 * (level ** 2) + 50 * level + 100


async def get_level_info(user_id: int) -> Tuple[int, int]:
    """Return (level, xp) for user"""
    async with get_connection() as conn:
        cur = await conn.execute("SELECT xp, level FROM xp WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        await cur.close()
        if row:
            return int(row["level"] or 0), int(row["xp"] or 0)
        return 0, 0


async def award_xp(user_id: int, amount: int) -> Tuple[bool, int, int]:
    """Add xp to user. Returns (leveled_up, old_level, new_level)"""
    async with get_connection() as conn:
        # ensure row
        await conn.execute("INSERT OR IGNORE INTO xp (user_id, xp, level, last_xp_at) VALUES (?, 0, 0, NULL)", (user_id,))
        await conn.commit()
        cur = await conn.execute("SELECT xp, level FROM xp WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        await cur.close()
        if not row:
            logger.exception("Failed to load xp row for %s", user_id)
            return False, 0, 0
        xp = int(row["xp"] or 0) + int(amount)
        level = int(row["level"] or 0)
        leveled = False
        old_level = level
        # check level up repeatedly if large xp
        while xp >= xp_needed_for_next(level):
            xp -= xp_needed_for_next(level)
            level += 1
            leveled = True
        await conn.execute("UPDATE xp SET xp = ?, level = ?, last_xp_at = ? WHERE user_id = ?", (xp, level, datetime.now(timezone.utc).isoformat(), user_id))
        await conn.commit()
        return leveled, old_level, level


# cooldown helpers (store per-user keys in cooldowns table)
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
