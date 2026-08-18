import pytest
import discord
from unittest.mock import AsyncMock, MagicMock, patch
from utils.db import init_db, get_connection
from cogs.autorole import AutoRoleCog
from cogs.welcome import WelcomeCog
from cogs.starboard import StarboardCog
from cogs.utility import Utility
from services.image_card import generate_welcome_card

@pytest.mark.asyncio
async def test_welcome_card_generation():
    buf = generate_welcome_card(
        display_name="CyberKnight",
        username="cyberknight",
        avatar_url=None,
        server_name="Helix Central",
        member_count=1542
    )
    assert buf is not None
    data = buf.getvalue()
    assert len(data) > 1000
    assert data[:8] == b'\x89PNG\r\n\x1a\n'

@pytest.mark.asyncio
async def test_autorole_cog():
    await init_db()
    bot = MagicMock()
    cog = AutoRoleCog(bot)

    guild = MagicMock(spec=discord.Guild)
    guild.id = 999111
    guild.name = "Test Guild"
    guild.owner_id = 12345
    guild.me = MagicMock()
    bot_role = MagicMock(spec=discord.Role)
    guild.me.top_role = bot_role

    target_role = MagicMock(spec=discord.Role)
    target_role.id = 888222
    target_role.name = "Members"
    target_role.mention = "<@&888222>"
    target_role.managed = False
    target_role.is_default = MagicMock(return_value=False)
    target_role.__ge__ = MagicMock(return_value=False)
    target_role.__lt__ = MagicMock(return_value=True)
    bot_role.__gt__ = MagicMock(return_value=True)

    ctx = MagicMock()
    ctx.guild = guild
    ctx.author = MagicMock(id=12345)
    ctx.send = AsyncMock()

    # Add autorole
    await cog.autorole_add.callback(cog, ctx, role=target_role)
    ctx.send.assert_called_once()
    embed = ctx.send.call_args[1]["embed"]
    assert "Auto Role Added" in embed.title

    # Simulate member join
    member = MagicMock(spec=discord.Member)
    member.guild = guild
    member.bot = False
    member.add_roles = AsyncMock()
    guild.get_role = MagicMock(return_value=target_role)

    await cog.on_member_join(member)
    member.add_roles.assert_called_once()

@pytest.mark.asyncio
async def test_welcome_cog_formatting():
    await init_db()
    bot = MagicMock()
    cog = WelcomeCog(bot)

    member = MagicMock(spec=discord.Member)
    member.mention = "<@123>"
    member.name = "Alex"
    member.guild.name = "Apex Realm"
    member.guild.member_count = 500

    template = "Hey {user}, welcome to {server}! #{membercount}"
    result = cog._format_msg(template, member)
    assert result == "Hey <@123>, welcome to Apex Realm! #500"

@pytest.mark.asyncio
async def test_starboard_cog():
    await init_db()
    bot = MagicMock()
    cog = StarboardCog(bot)

    ctx = MagicMock()
    ctx.guild = MagicMock(id=777888)
    ctx.guild.owner_id = 12345
    ctx.author = MagicMock(id=12345)
    ctx.send = AsyncMock()

    ch = MagicMock(spec=discord.TextChannel)
    ch.id = 555666
    ch.mention = "<#555666>"

    await cog.setstarboard.callback(cog, ctx, channel=ch)
    ctx.send.assert_called_once()
    embed = ctx.send.call_args[1]["embed"]
    assert "Starboard Channel Set" in embed.title

@pytest.mark.asyncio
async def test_utility_stats_command():
    bot = MagicMock()
    bot.wait_until_ready = AsyncMock()
    bot.latency = 0.02
    bot.guilds = [MagicMock(member_count=300, channels=[1, 2, 3])]
    bot.get_cog = MagicMock(return_value=None)
    bot.start_time = None

    cog = Utility(bot)
    cog.check_reminders.cancel()

    ctx = MagicMock()
    ctx.send = AsyncMock()

    await cog.stats.callback(cog, ctx)
    ctx.send.assert_called_once()
    embed = ctx.send.call_args[1]["embed"]
    assert "Helix Platform Statistics" in embed.title
