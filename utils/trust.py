"""Co-Owner & Trusted Admin hierarchy service."""
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from utils.db import get_connection

logger = logging.getLogger(__name__)


async def is_trusted(guild_id: int, user_id: int, bot_owner_id: Optional[int] = None) -> bool:
    """Check if user is a Trusted Admin / Co-Owner or Bot Owner."""
    if not guild_id or not user_id:
        return False
    if bot_owner_id and user_id == bot_owner_id:
        return True

    try:
        async with get_connection() as conn:
            cur = await conn.execute(
                "SELECT 1 FROM trusted_users WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id)
            )
            row = await cur.fetchone()
            return row is not None
    except Exception as err:
        logger.warning("Error checking trusted status for user %s: %s", user_id, err)
        return False


async def add_trusted(guild_id: int, user_id: int, granted_by: int) -> bool:
    """Add user to trusted users / co-owners list."""
    today_str = datetime.utcnow().isoformat()
    try:
        async with get_connection() as conn:
            await conn.execute("""
                INSERT INTO trusted_users (guild_id, user_id, granted_by, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(guild_id, user_id) DO NOTHING
            """, (guild_id, user_id, granted_by, today_str))
            await conn.commit()
            return True
    except Exception as err:
        logger.error("Failed to add trusted user %s: %s", user_id, err)
        return False


async def remove_trusted(guild_id: int, user_id: int) -> bool:
    """Remove user from trusted users / co-owners list."""
    try:
        async with get_connection() as conn:
            await conn.execute(
                "DELETE FROM trusted_users WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id)
            )
            await conn.commit()
            return True
    except Exception as err:
        logger.error("Failed to remove trusted user %s: %s", user_id, err)
        return False


async def get_trusted_users(guild_id: int) -> List[Dict[str, Any]]:
    """List all trusted users / co-owners for a guild."""
    try:
        async with get_connection() as conn:
            cur = await conn.execute(
                "SELECT user_id, granted_by, created_at FROM trusted_users WHERE guild_id = ?",
                (guild_id,)
            )
            rows = await cur.fetchall()
            return [{"user_id": r[0], "granted_by": r[1], "created_at": r[2]} for r in rows]
    except Exception as err:
        logger.error("Failed to get trusted users for guild %s: %s", guild_id, err)
        return []
