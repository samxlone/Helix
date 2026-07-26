import re
import logging
import aiohttp
from typing import Tuple, Optional, Dict, Any, List
from datetime import datetime, timezone
from utils.db import get_connection

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def clean_vanity_code(input_str: str) -> str:
    """Strips URLs, discord.gg prefixes, and whitespace from a vanity code."""
    cleaned = input_str.strip()
    cleaned = re.sub(r"^(https?://)?(www\.)?(discord\.gg|discord\.com/invite)/", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip("/")
    return cleaned


async def check_discord_vanity(vanity: str) -> Tuple[str, Optional[Dict[str, Any]]]:
    """Check if a Discord vanity URL/invite code is available.

    Returns (status, data):
    - ("available", None): Vanity is 100% available/untaken (404)
    - ("taken", guild_info): Vanity is occupied by a server (200)
    - ("invalid", None): Invalid vanity code format
    - ("error", {"message": "..."}): Rate limited (429) or HTTP error
    """
    code = clean_vanity_code(vanity)
    if not code or not re.match(r"^[a-zA-Z0-9_-]{2,32}$", code):
        return "invalid", None

    url = f"https://discord.com/api/v10/invites/{code}?with_counts=true"
    try:
        async with aiohttp.ClientSession(headers=HEADERS) as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 404:
                    return "available", None
                elif resp.status == 200:
                    data = await resp.json()
                    guild = data.get("guild", {})
                    guild_info = {
                        "code": code,
                        "guild_id": guild.get("id"),
                        "name": guild.get("name", "Unknown Server"),
                        "description": guild.get("description"),
                        "icon": guild.get("icon"),
                        "approximate_member_count": data.get("approximate_member_count", 0),
                        "approximate_presence_count": data.get("approximate_presence_count", 0),
                    }
                    return "taken", guild_info
                elif resp.status == 429:
                    return "error", {"message": "Rate limited by Discord API. Please try again in a few seconds."}
                else:
                    return "error", {"message": f"Discord returned HTTP status {resp.status}"}
    except Exception as e:
        logger.warning("Failed to check vanity '%s': %s", code, e)
        return "error", {"message": str(e)}


async def add_vanity_tracker(user_id: int, vanity: str) -> Tuple[bool, str]:
    """Add a vanity to track for user_id. Returns (success, message)."""
    code = clean_vanity_code(vanity)
    if not code or not re.match(r"^[a-zA-Z0-9_-]{2,32}$", code):
        return False, "Invalid vanity URL format. Must be 2-32 alphanumeric characters."

    now_iso = datetime.now(timezone.utc).isoformat()
    async with get_connection() as conn:
        try:
            await conn.execute(
                "INSERT INTO vanity_trackers (user_id, vanity, created_at) VALUES (?, ?, ?)",
                (user_id, code, now_iso)
            )
            await conn.commit()
            return True, code
        except Exception:
            return False, f"You are already tracking the vanity `{code}`!"


async def remove_vanity_tracker(user_id: int, vanity: str) -> bool:
    """Remove a vanity tracker for user_id."""
    code = clean_vanity_code(vanity)
    async with get_connection() as conn:
        cur = await conn.execute(
            "DELETE FROM vanity_trackers WHERE user_id = ? AND vanity = ?",
            (user_id, code)
        )
        deleted = cur.rowcount > 0
        await conn.commit()
        return deleted


async def get_user_vanity_trackers(user_id: int) -> List[str]:
    """Get list of tracked vanity codes for user_id."""
    async with get_connection() as conn:
        cur = await conn.execute(
            "SELECT vanity FROM vanity_trackers WHERE user_id = ? ORDER BY id ASC",
            (user_id,)
        )
        rows = await cur.fetchall()
        await cur.close()
        return [row["vanity"] for row in rows]


async def get_all_vanity_trackers() -> List[Dict[str, Any]]:
    """Get all active trackers across all users."""
    async with get_connection() as conn:
        cur = await conn.execute("SELECT id, user_id, vanity, created_at FROM vanity_trackers")
        rows = await cur.fetchall()
        await cur.close()
        return [
            {
                "id": r["id"],
                "user_id": int(r["user_id"]),
                "vanity": r["vanity"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]
