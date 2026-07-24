import logging
import json
from datetime import datetime, timezone
from typing import Optional, List, Dict

from utils.db import get_connection

logger = logging.getLogger(__name__)


async def log_action(guild_id: int, moderator_id: int, target_id: int, action: str, reason: Optional[str] = None) -> int:
    """Log an action and return the case id (rowid)."""
    created_at = datetime.now(timezone.utc).isoformat()
    try:
        async with get_connection() as conn:
            cur = await conn.execute(
                "INSERT INTO mod_logs (guild_id, moderator_id, target_id, action, reason, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (guild_id, moderator_id, target_id, action, reason or "", created_at),
            )
            await conn.commit()
            case_id = cur.lastrowid
            return case_id
    except Exception:
        logger.exception("Failed to record mod log for guild %s", guild_id)
    return -1


async def fetch_logs(guild_id: int, limit: int = 25) -> List[Dict[str, str]]:
    out = []
    try:
        async with get_connection() as conn:
            cur = await conn.execute(
                "SELECT id, moderator_id, target_id, action, reason, created_at FROM mod_logs WHERE guild_id = ? ORDER BY id DESC LIMIT ?",
                (guild_id, limit),
            )
            rows = await cur.fetchall()
            await cur.close()
            for r in rows:
                out.append({
                    "case_id": str(r["id"]),
                    "moderator_id": str(r["moderator_id"]),
                    "target_id": str(r["target_id"]),
                    "action": r["action"],
                    "reason": r["reason"],
                    "created_at": r["created_at"],
                })
    except Exception:
        logger.exception("Failed to fetch mod logs for guild %s", guild_id)
    return out


async def fetch_logs_for_target(guild_id: int, target_id: int, action: Optional[str] = None, limit: int = 100) -> List[Dict[str, str]]:
    out = []
    try:
        async with get_connection() as conn:
            if action:
                cur = await conn.execute(
                    "SELECT id, moderator_id, target_id, action, reason, created_at FROM mod_logs WHERE guild_id = ? AND target_id = ? AND action = ? ORDER BY id DESC LIMIT ?",
                    (guild_id, target_id, action, limit),
                )
            else:
                cur = await conn.execute(
                    "SELECT id, moderator_id, target_id, action, reason, created_at FROM mod_logs WHERE guild_id = ? AND target_id = ? ORDER BY id DESC LIMIT ?",
                    (guild_id, target_id, limit),
                )
            rows = await cur.fetchall()
            await cur.close()
            for r in rows:
                out.append({
                    "case_id": str(r["id"]),
                    "moderator_id": str(r["moderator_id"]),
                    "target_id": str(r["target_id"]),
                    "action": r["action"],
                    "reason": r["reason"],
                    "created_at": r["created_at"],
                })
    except Exception:
        logger.exception("Failed to fetch mod logs for guild %s target %s", guild_id, target_id)
    return out
