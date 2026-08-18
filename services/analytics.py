"""Statbot-style Server & User Activity Analytics Service."""
import logging
import asyncio
from datetime import datetime, date, timedelta
from typing import Dict, List, Any, Optional
from utils.db import get_connection

logger = logging.getLogger(__name__)

# Cache for tracking voice join times: (guild_id, user_id) -> (channel_id, start_timestamp)
_voice_join_times: Dict[tuple, tuple] = {}


async def record_message(guild_id: int, user_id: int, channel_id: int):
    """Record a non-bot message in analytics database."""
    if not guild_id or not user_id or not channel_id:
        return
    today_str = date.today().isoformat()
    try:
        async with get_connection() as conn:
            await conn.execute("""
                INSERT INTO message_analytics (guild_id, user_id, channel_id, message_count, log_date)
                VALUES (?, ?, ?, 1, ?)
                ON CONFLICT(guild_id, user_id, channel_id, log_date)
                DO UPDATE SET message_count = message_count + 1
            """, (guild_id, user_id, channel_id, today_str))
            await conn.commit()
    except Exception as err:
        logger.debug("Failed to record message analytics: %s", err)


def handle_voice_update(member, before, after):
    """Track user voice channel duration."""
    if not member or member.bot or not member.guild:
        return
    guild_id = member.guild.id
    user_id = member.id
    key = (guild_id, user_id)

    try:
        loop = asyncio.get_event_loop()
        now = loop.time() if loop.is_running() else 0
    except Exception:
        now = 0

    # User joined a voice channel
    if not before.channel and after.channel:
        _voice_join_times[key] = (after.channel.id, now)
    # User switched voice channels or left
    elif before.channel and (not after.channel or before.channel.id != after.channel.id):
        join_data = _voice_join_times.pop(key, None)
        if join_data:
            ch_id, join_ts = join_data
            duration = max(0, int(now - join_ts))
            if duration > 0:
                asyncio.create_task(record_voice_seconds(guild_id, user_id, ch_id, duration))
        
        if after.channel:
            _voice_join_times[key] = (after.channel.id, now)


async def record_voice_seconds(guild_id: int, user_id: int, channel_id: int, seconds: int):
    """Record voice activity duration in database."""
    if not guild_id or not user_id or not channel_id or seconds <= 0:
        return
    today_str = date.today().isoformat()
    try:
        async with get_connection() as conn:
            await conn.execute("""
                INSERT INTO voice_analytics (guild_id, user_id, channel_id, voice_seconds, log_date)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(guild_id, user_id, channel_id, log_date)
                DO UPDATE SET voice_seconds = voice_seconds + ?
            """, (guild_id, user_id, channel_id, seconds, today_str, seconds))
            await conn.commit()
    except Exception as err:
        logger.debug("Failed to record voice analytics: %s", err)


async def get_server_analytics(guild_id: int) -> Dict[str, Any]:
    """Fetch Statbot-style Server Analytics (Messages 1d/7d/30d, Voice 1d/7d/30d, Top Members, Top Channels)."""
    today = date.today()
    d1_str = today.isoformat()
    d7_str = (today - timedelta(days=7)).isoformat()
    d30_str = (today - timedelta(days=30)).isoformat()

    async with get_connection() as conn:
        # Message Totals
        cur = await conn.execute("SELECT SUM(message_count) FROM message_analytics WHERE guild_id = ? AND log_date = ?", (guild_id, d1_str))
        row = await cur.fetchone()
        msg_1d = row[0] if (row and row[0]) else 0

        cur = await conn.execute("SELECT SUM(message_count) FROM message_analytics WHERE guild_id = ? AND log_date >= ?", (guild_id, d7_str))
        row = await cur.fetchone()
        msg_7d = row[0] if (row and row[0]) else 0

        cur = await conn.execute("SELECT SUM(message_count) FROM message_analytics WHERE guild_id = ? AND log_date >= ?", (guild_id, d30_str))
        row = await cur.fetchone()
        msg_30d = row[0] if (row and row[0]) else 0

        # Voice Totals (seconds -> hours)
        cur = await conn.execute("SELECT SUM(voice_seconds) FROM voice_analytics WHERE guild_id = ? AND log_date = ?", (guild_id, d1_str))
        row = await cur.fetchone()
        vc_1d_sec = row[0] if (row and row[0]) else 0

        cur = await conn.execute("SELECT SUM(voice_seconds) FROM voice_analytics WHERE guild_id = ? AND log_date >= ?", (guild_id, d7_str))
        row = await cur.fetchone()
        vc_7d_sec = row[0] if (row and row[0]) else 0

        cur = await conn.execute("SELECT SUM(voice_seconds) FROM voice_analytics WHERE guild_id = ? AND log_date >= ?", (guild_id, d30_str))
        row = await cur.fetchone()
        vc_30d_sec = row[0] if (row and row[0]) else 0

        # Top Message Members (Last 7d)
        cur = await conn.execute("""
            SELECT user_id, SUM(message_count) as total
            FROM message_analytics
            WHERE guild_id = ? AND log_date >= ?
            GROUP BY user_id
            ORDER BY total DESC
            LIMIT 5
        """, (guild_id, d7_str))
        top_members = await cur.fetchall()

        # Top Message Channels (Last 7d)
        cur = await conn.execute("""
            SELECT channel_id, SUM(message_count) as total
            FROM message_analytics
            WHERE guild_id = ? AND log_date >= ?
            GROUP BY channel_id
            ORDER BY total DESC
            LIMIT 5
        """, (guild_id, d7_str))
        top_channels = await cur.fetchall()

    return {
        "msg_1d": msg_1d,
        "msg_7d": msg_7d,
        "msg_30d": msg_30d,
        "vc_1d_hrs": round(vc_1d_sec / 3600.0, 2),
        "vc_7d_hrs": round(vc_7d_sec / 3600.0, 2),
        "vc_30d_hrs": round(vc_30d_sec / 3600.0, 2),
        "top_members": top_members,
        "top_channels": top_channels,
    }


async def get_user_analytics(guild_id: int, user_id: int) -> Dict[str, Any]:
    """Fetch Statbot-style User Analytics (Ranks, Messages 1d/7d/30d, Voice 1d/7d/30d, Top Channels)."""
    today = date.today()
    d1_str = today.isoformat()
    d7_str = (today - timedelta(days=7)).isoformat()
    d30_str = (today - timedelta(days=30)).isoformat()

    async with get_connection() as conn:
        # Message Totals
        cur = await conn.execute("SELECT SUM(message_count) FROM message_analytics WHERE guild_id = ? AND user_id = ? AND log_date = ?", (guild_id, user_id, d1_str))
        row = await cur.fetchone()
        msg_1d = row[0] if (row and row[0]) else 0

        cur = await conn.execute("SELECT SUM(message_count) FROM message_analytics WHERE guild_id = ? AND user_id = ? AND log_date >= ?", (guild_id, user_id, d7_str))
        row = await cur.fetchone()
        msg_7d = row[0] if (row and row[0]) else 0

        cur = await conn.execute("SELECT SUM(message_count) FROM message_analytics WHERE guild_id = ? AND user_id = ? AND log_date >= ?", (guild_id, user_id, d30_str))
        row = await cur.fetchone()
        msg_30d = row[0] if (row and row[0]) else 0

        # Voice Totals
        cur = await conn.execute("SELECT SUM(voice_seconds) FROM voice_analytics WHERE guild_id = ? AND user_id = ? AND log_date = ?", (guild_id, user_id, d1_str))
        row = await cur.fetchone()
        vc_1d_sec = row[0] if (row and row[0]) else 0

        cur = await conn.execute("SELECT SUM(voice_seconds) FROM voice_analytics WHERE guild_id = ? AND user_id = ? AND log_date >= ?", (guild_id, user_id, d7_str))
        row = await cur.fetchone()
        vc_7d_sec = row[0] if (row and row[0]) else 0

        cur = await conn.execute("SELECT SUM(voice_seconds) FROM voice_analytics WHERE guild_id = ? AND user_id = ? AND log_date >= ?", (guild_id, user_id, d30_str))
        row = await cur.fetchone()
        vc_30d_sec = row[0] if (row and row[0]) else 0

        # Message Rank
        cur = await conn.execute("""
            SELECT user_id, SUM(message_count) as total
            FROM message_analytics
            WHERE guild_id = ? AND log_date >= ?
            GROUP BY user_id
            ORDER BY total DESC
        """, (guild_id, d7_str))
        all_msg_users = await cur.fetchall()
        msg_rank = next((idx + 1 for idx, r in enumerate(all_msg_users) if r[0] == user_id), "N/A")

        # Voice Rank
        cur = await conn.execute("""
            SELECT user_id, SUM(voice_seconds) as total
            FROM voice_analytics
            WHERE guild_id = ? AND log_date >= ?
            GROUP BY user_id
            ORDER BY total DESC
        """, (guild_id, d7_str))
        all_vc_users = await cur.fetchall()
        vc_rank = next((idx + 1 for idx, r in enumerate(all_vc_users) if r[0] == user_id), "N/A")

        # Top Channels for user
        cur = await conn.execute("""
            SELECT channel_id, SUM(message_count) as total
            FROM message_analytics
            WHERE guild_id = ? AND user_id = ? AND log_date >= ?
            GROUP BY channel_id
            ORDER BY total DESC
            LIMIT 3
        """, (guild_id, user_id, d7_str))
        top_user_channels = await cur.fetchall()

    return {
        "msg_1d": msg_1d,
        "msg_7d": msg_7d,
        "msg_30d": msg_30d,
        "vc_1d_hrs": round(vc_1d_sec / 3600.0, 2),
        "vc_7d_hrs": round(vc_7d_sec / 3600.0, 2),
        "vc_30d_hrs": round(vc_30d_sec / 3600.0, 2),
        "msg_rank": f"#{msg_rank}" if isinstance(msg_rank, int) else msg_rank,
        "vc_rank": f"#{vc_rank}" if isinstance(vc_rank, int) else vc_rank,
        "top_channels": top_user_channels,
    }
