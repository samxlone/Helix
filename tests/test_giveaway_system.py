import pytest
import asyncio
import random
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone, timedelta
import discord

from main import bot
from utils.cog_loader import load_cogs
from utils.db import get_connection, init_db
from cogs.giveaway import parse_time_duration, GiveawayView


@pytest.mark.asyncio
async def test_time_duration_parsing():
    """Verify time string parsing converts accurately to seconds."""
    assert parse_time_duration("30s") == 30
    assert parse_time_duration("10m") == 600
    assert parse_time_duration("3h") == 10800
    assert parse_time_duration("30d") == 2592000
    assert parse_time_duration("1h30m") == 5400
    assert parse_time_duration("2d12h") == 216000
    assert parse_time_duration("1mo") == 2592000
    assert parse_time_duration("invalid") is None



@pytest.mark.asyncio
async def test_giveaway_lifecycle():
    """Verify full giveaway workflow: start, enter button, leave button, end, and reroll."""
    await init_db()
    await load_cogs(bot)

    gw_cog = bot.get_cog("Giveaway")
    assert gw_cog is not None

    # 1. Setup mock context
    test_msg_id = random.randint(1000000000, 9999999999)
    ctx = MagicMock()
    ctx.guild = MagicMock()
    ctx.guild.id = 777888
    ctx.guild.name = "Test Community"
    ctx.guild.owner_id = 999
    ctx.channel = MagicMock()
    ctx.channel.id = 555666
    ctx.author = MagicMock()
    ctx.author.id = 999
    ctx.author.mention = "<@999>"
    ctx.interaction = None

    mock_msg = MagicMock(spec=discord.Message)
    mock_msg.id = test_msg_id
    mock_msg.edit = AsyncMock()
    mock_msg.jump_url = f"https://discord.com/channels/777888/555666/{test_msg_id}"
    ctx.send = AsyncMock(return_value=mock_msg)
    ctx.channel.fetch_message = AsyncMock(return_value=mock_msg)
    ctx.guild.get_channel = MagicMock(return_value=ctx.channel)

    # Start giveaway
    await gw_cog.g_start(ctx, duration="1m", winners=1, prize="Discord Nitro")
    ctx.send.assert_called_once()

    # Query DB to get the created giveaway ID
    async with get_connection() as conn:
        cur = await conn.execute("SELECT id FROM giveaways WHERE message_id = ?", (mock_msg.id,))
        row = await cur.fetchone()
        await cur.close()
        assert row is not None
        gw_id = row["id"]

    # 2. Test User 1001 entering the giveaway via Button
    interaction1 = MagicMock(spec=discord.Interaction)
    interaction1.user = MagicMock(id=1001)
    interaction1.response = MagicMock()
    interaction1.response.is_done = MagicMock(return_value=False)
    interaction1.response.defer = AsyncMock()
    interaction1.followup = MagicMock()
    interaction1.followup.send = AsyncMock()
    interaction1.message = mock_msg
    mock_msg.embeds = [discord.Embed(title="Giveaway")]

    view = GiveawayView(gw_id)
    btn = view.children[0]

    # Enter
    await btn.callback(interaction1)
    interaction1.followup.send.assert_called_once()
    assert "Entered!" in str(interaction1.followup.send.call_args)

    # 3. Test User 1002 entering
    interaction2 = MagicMock(spec=discord.Interaction)
    interaction2.user = MagicMock(id=1002)
    interaction2.response = MagicMock()
    interaction2.response.is_done = MagicMock(return_value=False)
    interaction2.response.defer = AsyncMock()
    interaction2.followup = MagicMock()
    interaction2.followup.send = AsyncMock()
    interaction2.message = mock_msg

    await btn.callback(interaction2)

    # Verify 2 entries in database
    async with get_connection() as conn:
        cur = await conn.execute("SELECT COUNT(*) as count FROM giveaway_entries WHERE giveaway_id = ?", (gw_id,))
        count_row = await cur.fetchone()
        await cur.close()
        assert count_row["count"] == 2

    # 4. Test User 1001 leaving
    await btn.callback(interaction1)
    assert "left the giveaway" in str(interaction1.followup.send.call_args)

    # 5. End the giveaway
    winners = await gw_cog._end_giveaway(gw_id)
    assert winners == [1002]  # Only 1002 remained

    # 6. Test Reroll
    ctx.channel.send = AsyncMock()
    await gw_cog.g_reroll(ctx, message_id=str(mock_msg.id))
    ctx.channel.send.assert_called()
    assert "Reroll Results" in str(ctx.channel.send.call_args)
