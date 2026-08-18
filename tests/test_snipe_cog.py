import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone
import discord
from main import bot
from utils.cog_loader import load_cogs


@pytest.mark.asyncio
async def test_snipe_events_and_commands():
    """Verify that message delete, edit, reaction remove, and snipe commands function correctly."""
    await load_cogs(bot)
    snipe_cog = bot.get_cog("Snipe")
    assert snipe_cog is not None

    guild = MagicMock(spec=discord.Guild)
    guild.id = 777888
    guild.owner_id = 999

    channel = MagicMock(spec=discord.TextChannel)
    channel.id = 555666
    channel.name = "general"
    channel.guild = guild

    author = MagicMock(spec=discord.Member)
    author.id = 111222
    author.bot = False
    author.name = "TestUser"
    author.display_name = "TestDisplay"
    author.mention = "<@111222>"
    author.display_avatar = MagicMock(url="https://cdn.discordapp.com/avatars/1.png")

    # 1. Test message delete event
    msg = MagicMock(spec=discord.Message)
    msg.id = 999111
    msg.guild = guild
    msg.channel = channel
    msg.author = author
    msg.content = "Secret deleted text message"
    msg.created_at = datetime.now(timezone.utc)
    msg.attachments = []
    msg.stickers = []

    await snipe_cog.on_message_delete(msg)
    assert len(snipe_cog.delete_cache[channel.id]) == 1
    assert snipe_cog.delete_cache[channel.id][0]["content"] == "Secret deleted text message"

    # 2. Test snipe command execution
    ctx = MagicMock()
    ctx.channel = channel
    ctx.guild = guild
    ctx.author = author
    ctx.send = AsyncMock()

    await snipe_cog.snipe_command(ctx, index=1)
    ctx.send.assert_called_once()
    embed_sent = ctx.send.call_args[1]["embed"]
    assert "Secret deleted text message" in embed_sent.description

    # 3. Test edit event and editsnipe command
    msg_after = MagicMock(spec=discord.Message)
    msg_after.id = 999111
    msg_after.guild = guild
    msg_after.channel = channel
    msg_after.author = author
    msg_after.content = "Edited new message"
    msg_after.jump_url = "https://discord.com/channels/1/2/3"

    await snipe_cog.on_message_edit(msg, msg_after)
    assert len(snipe_cog.edit_cache[channel.id]) == 1

    ctx.send.reset_mock()
    await snipe_cog.editsnipe_command(ctx, index=1)
    ctx.send.assert_called_once()
    embed_edit = ctx.send.call_args[1]["embed"]
    assert any(f.name == "⏮️ Before" and f.value == "Secret deleted text message" for f in embed_edit.fields)

    # 4. Test reaction remove event and reactionsnipe command
    raw_payload = MagicMock(spec=discord.RawReactionActionEvent)
    raw_payload.guild_id = guild.id
    raw_payload.channel_id = channel.id
    raw_payload.message_id = 999111
    raw_payload.user_id = author.id
    raw_payload.emoji = "🔥"

    guild.get_member = MagicMock(return_value=author)
    snipe_cog.bot.get_guild = MagicMock(return_value=guild)

    await snipe_cog.on_raw_reaction_remove(raw_payload)
    assert len(snipe_cog.reaction_cache[channel.id]) == 1

    ctx.send.reset_mock()
    await snipe_cog.reactionsnipe_command(ctx, index=1)
    ctx.send.assert_called_once()
    embed_rx = ctx.send.call_args[1]["embed"]
    assert "🔥" in embed_rx.description

    # 5. Test clear snipe
    ctx.send.reset_mock()
    await snipe_cog.clearsnipe_command(ctx)
    assert len(snipe_cog.delete_cache[channel.id]) == 0
    assert len(snipe_cog.edit_cache[channel.id]) == 0
    assert len(snipe_cog.reaction_cache[channel.id]) == 0
    ctx.send.assert_called_once()
