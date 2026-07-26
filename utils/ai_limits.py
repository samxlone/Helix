from datetime import datetime, timezone
import logging
from typing import Tuple
from utils.db import get_connection

logger = logging.getLogger(__name__)

TEXT_DAILY_LIMIT = 10
IMAGE_DAILY_LIMIT = 2


def get_today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


async def check_and_increment_text_limit(user_id: int, limit: int = TEXT_DAILY_LIMIT) -> Tuple[bool, int]:
    """Check if user is within their daily text question limit. If allowed, increment count and return (True, new_count).

    If limit reached, return (False, current_count).
    """
    today = get_today_str()
    async with get_connection() as conn:
        cursor = await conn.execute(
            "SELECT text_count FROM ai_daily_usage WHERE user_id = ? AND date_str = ?",
            (user_id, today)
        )
        row = await cursor.fetchone()
        current_count = row["text_count"] if row else 0

        if current_count >= limit:
            return False, current_count

        new_count = current_count + 1
        if row:
            await conn.execute(
                "UPDATE ai_daily_usage SET text_count = ? WHERE user_id = ? AND date_str = ?",
                (new_count, user_id, today)
            )
        else:
            await conn.execute(
                "INSERT INTO ai_daily_usage (user_id, date_str, text_count, image_count) VALUES (?, ?, ?, 0)",
                (user_id, today, new_count)
            )
        await conn.commit()
        return True, new_count


async def check_and_increment_image_limit(user_id: int, limit: int = IMAGE_DAILY_LIMIT) -> Tuple[bool, int]:
    """Check if user is within their daily image generation limit. If allowed, increment count and return (True, new_count).

    If limit reached, return (False, current_count).
    """
    today = get_today_str()
    async with get_connection() as conn:
        cursor = await conn.execute(
            "SELECT image_count FROM ai_daily_usage WHERE user_id = ? AND date_str = ?",
            (user_id, today)
        )
        row = await cursor.fetchone()
        current_count = row["image_count"] if row else 0

        if current_count >= limit:
            return False, current_count

        new_count = current_count + 1
        if row:
            await conn.execute(
                "UPDATE ai_daily_usage SET image_count = ? WHERE user_id = ? AND date_str = ?",
                (new_count, user_id, today)
            )
        else:
            await conn.execute(
                "INSERT INTO ai_daily_usage (user_id, date_str, text_count, image_count) VALUES (?, ?, 0, ?)",
                (user_id, today, new_count)
            )
        await conn.commit()
        return True, new_count


async def get_user_daily_usage(user_id: int) -> Tuple[int, int]:
    """Get (text_count, image_count) for user today."""
    today = get_today_str()
    async with get_connection() as conn:
        cursor = await conn.execute(
            "SELECT text_count, image_count FROM ai_daily_usage WHERE user_id = ? AND date_str = ?",
            (user_id, today)
        )
        row = await cursor.fetchone()
        if not row:
            return 0, 0
        return row["text_count"], row["image_count"]
