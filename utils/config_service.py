import json
import logging
from typing import Any, Dict

from config import config
from utils.db import get_connection

logger = logging.getLogger(__name__)


def _deep_merge(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    """Return a new dict with b merged into a (deep merge)."""
    out = dict(a)
    for k, v in b.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


async def get_guild_config(guild_id: int) -> Dict[str, Any]:
    """Return the merged configuration for a guild.

    Merge order: defaults (config.as_dict()) <- guild DB entry
    """
    base = config.as_dict()
    try:
        async with get_connection() as conn:
            cur = await conn.execute("SELECT data FROM settings WHERE guild_id = ?", (guild_id,))
            row = await cur.fetchone()
            await cur.close()
            if row and row["data"]:
                try:
                    guild_data = json.loads(row["data"]) if isinstance(row["data"], str) else {}
                    merged = _deep_merge(base, guild_data)
                    return merged
                except Exception:
                    logger.exception("Failed to parse guild config JSON for guild %s", guild_id)
                    return base
    except Exception:
        logger.exception("DB error while fetching config for guild %s", guild_id)
    return base


async def set_guild_config(guild_id: int, patch: Dict[str, Any]) -> None:
    """Apply a patch (dict) to the guild config and persist it.

    This loads existing config (if any), deep-merges the patch, and stores the resulting JSON blob.
    """
    try:
        async with get_connection() as conn:
            cur = await conn.execute("SELECT data FROM settings WHERE guild_id = ?", (guild_id,))
            row = await cur.fetchone()
            await cur.close()

            existing = {}
            if row and row["data"]:
                try:
                    existing = json.loads(row["data"]) if isinstance(row["data"], str) else {}
                except Exception:
                    logger.exception("Failed to parse existing config JSON for guild %s", guild_id)
                    existing = {}

            new = _deep_merge(existing, patch)
            data_text = json.dumps(new)

            # Insert or replace
            await conn.execute(
                "INSERT INTO settings (guild_id, data) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET data=excluded.data",
                (guild_id, data_text),
            )
            await conn.commit()
    except Exception:
        logger.exception("DB error while setting config for guild %s", guild_id)


async def reset_guild_config(guild_id: int) -> None:
    try:
        async with get_connection() as conn:
            await conn.execute("DELETE FROM settings WHERE guild_id = ?", (guild_id,))
            await conn.commit()
    except Exception:
        logger.exception("DB error while resetting config for guild %s", guild_id)


async def get_setting(guild_id: int, key: str, default: Any = None) -> Any:
    cfg = await get_guild_config(guild_id)
    return cfg.get(key, default)
