from typing import Optional
from utils.db import get_connection


async def record_play(guild_id: int, track_info: dict) -> None:
    """Record the track play into the events table as a music_play event."""
    try:
        async with get_connection() as conn:
            await conn.execute(
                "INSERT INTO events (guild_id, type, payload, created_at) VALUES (?, ?, ?, datetime('now'))",
                (guild_id, "music_play", str(track_info)),
            )
            await conn.commit()
    except Exception:
        # keep history best-effort
        pass
