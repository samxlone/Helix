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


async def remove_warnings_for_target(guild_id: int, target_id: int, count: int = 1) -> int:
    """Remove up to `count` warnings for a user in a guild. If count <= 0, remove all."""
    try:
        async with get_connection() as conn:
            if count <= 0:
                cur = await conn.execute(
                    "DELETE FROM mod_logs WHERE guild_id = ? AND target_id = ? AND action = 'warn'",
                    (guild_id, target_id)
                )
                removed = cur.rowcount
            else:
                cur = await conn.execute(
                    "SELECT id FROM mod_logs WHERE guild_id = ? AND target_id = ? AND action = 'warn' ORDER BY id DESC LIMIT ?",
                    (guild_id, target_id, count)
                )
                rows = await cur.fetchall()
                await cur.close()
                if not rows:
                    return 0

                ids_to_del = [r["id"] for r in rows]
                placeholders = ",".join(["?"] * len(ids_to_del))
                cur = await conn.execute(
                    f"DELETE FROM mod_logs WHERE id IN ({placeholders})",
                    ids_to_del
                )
                removed = cur.rowcount

            await conn.commit()
            return removed
    except Exception:
        logger.exception("Failed to remove warnings for guild %s target %s", guild_id, target_id)
        return 0


async def remove_warning_by_case(guild_id: int, case_id: int) -> bool:
    """Remove a specific warning by case ID."""
    try:
        async with get_connection() as conn:
            cur = await conn.execute(
                "DELETE FROM mod_logs WHERE guild_id = ? AND id = ? AND action = 'warn'",
                (guild_id, case_id)
            )
            await conn.commit()
            return cur.rowcount > 0
    except Exception:
        logger.exception("Failed to remove warning case %s for guild %s", case_id, guild_id)
        return False

