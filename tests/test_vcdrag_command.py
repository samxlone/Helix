import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
import discord
from main import bot
from utils.cog_loader import load_cogs


@pytest.mark.asyncio
async def test_vc_drag_and_pull_command():
    """Verify that vc drag, pull, and vcdrag aliases correctly move the member."""
    await load_cogs(bot)

    mod_cog = bot.get_cog("Moderation")
    assert mod_cog is not None

    # Check command resolution for drag and pull
    cmd_drag = bot.get_command("drag")
    cmd_pull = bot.get_command("pull")
    cmd_vcdrag = bot.get_command("vcdrag")
    cmd_vcpull = bot.get_command("vcpull")

    assert cmd_drag is not None
    assert cmd_pull is not None
    assert cmd_pull == cmd_drag
    assert cmd_vcdrag == cmd_drag
    assert cmd_vcpull == cmd_drag

    # Check vc subgroup
    vc_grp = bot.get_command("vc")
    assert vc_grp is not None
    sub_drag = vc_grp.get_command("drag")
    sub_pull = vc_grp.get_command("pull")
    assert sub_drag is not None
    assert sub_pull is not None
    assert sub_pull == sub_drag

    # 1. Setup mock context and channels
    ctx = MagicMock()
    ctx.guild = MagicMock()
    ctx.guild.id = 123456
    ctx.guild.owner_id = 999
    ctx.author = MagicMock()
    ctx.author.id = 111
    ctx.author.top_role = MagicMock()
    ctx.author.top_role.__ge__ = lambda self, other: True

    # Voice channels
    origin_vc = MagicMock(spec=discord.VoiceChannel)
    origin_vc.id = 2001
    origin_vc.name = "General VC"

    dest_vc = MagicMock(spec=discord.VoiceChannel)
    dest_vc.id = 2002
    dest_vc.name = "Music Lounge"
    dest_vc.permissions_for = MagicMock(return_value=MagicMock(connect=True))

    ctx.author.voice = MagicMock()
    ctx.author.voice.channel = dest_vc

    target = MagicMock(spec=discord.Member)
    target.id = 222
    target.mention = "<@222>"
    target.top_role = MagicMock()
    target.top_role.__ge__ = lambda self, other: False
    target.voice = MagicMock()
    target.voice.channel = origin_vc
    target.move_to = AsyncMock()

    ctx.send = AsyncMock()

    # Run vc_drag
    await mod_cog.vc_drag(ctx, target=target)

    # Verify target was moved to destination
    target.move_to.assert_called_once_with(dest_vc, reason=f"VC drag requested by {ctx.author} (111)")
    ctx.send.assert_called_once()


@pytest.mark.asyncio
async def test_vc_disconnect_command():
    """Verify that vdc / vc disconnect correctly disconnects the member."""
    await load_cogs(bot)

    mod_cog = bot.get_cog("Moderation")
    assert mod_cog is not None

    cmd_vdc = bot.get_command("vdc")
    cmd_vcdisconnect = bot.get_command("vcdisconnect")
    cmd_vckick = bot.get_command("vckick")

    assert cmd_vdc is not None
    assert cmd_vcdisconnect == cmd_vdc
    assert cmd_vckick == cmd_vdc

    # Setup mock context
    ctx = MagicMock()
    ctx.guild = MagicMock()
    ctx.guild.id = 123456
    ctx.guild.owner_id = 999
    ctx.author = MagicMock()
    ctx.author.id = 111
    ctx.author.top_role = MagicMock()
    ctx.author.top_role.__ge__ = lambda self, other: True

    origin_vc = MagicMock(spec=discord.VoiceChannel)
    origin_vc.id = 2001
    origin_vc.name = "General VC"

    target = MagicMock(spec=discord.Member)
    target.id = 222
    target.mention = "<@222>"
    target.top_role = MagicMock()
    target.top_role.__ge__ = lambda self, other: False
    target.voice = MagicMock()
    target.voice.channel = origin_vc
    target.move_to = AsyncMock()

    ctx.send = AsyncMock()

    # Run vc_disconnect
    await mod_cog.vc_disconnect(ctx, target=target)

    # Verify target was disconnected (move_to None)
    target.move_to.assert_called_once_with(None, reason=f"Voice disconnect requested by {ctx.author} (111)")
    ctx.send.assert_called_once()


@pytest.mark.asyncio
async def test_vcdrag_direct_string_target():
    """Verify vcdrag_direct resolves string queries including multi-word usernames/nicknames."""
    await load_cogs(bot)
    mod_cog = bot.get_cog("Moderation")

    ctx = MagicMock()
    ctx.guild = MagicMock()
    ctx.guild.id = 123456
    ctx.guild.owner_id = 999
    ctx.author = MagicMock(id=111)
    ctx.author.top_role = MagicMock()
    ctx.author.top_role.__ge__ = lambda self, other: True

    dest_vc = MagicMock(spec=discord.VoiceChannel)
    dest_vc.id = 3001
    dest_vc.name = "My VC"
    dest_vc.permissions_for = MagicMock(return_value=MagicMock(connect=True))
    ctx.author.voice = MagicMock(channel=dest_vc)

    target_member = MagicMock(spec=discord.Member)
    target_member.id = 456789
    target_member.name = "Sax sux kyu nahi mil raha"
    target_member.display_name = "Sax sux kyu nahi mil raha"
    target_member.nick = "Sax sux kyu nahi mil raha"
    target_member.top_role = MagicMock()
    target_member.top_role.__ge__ = lambda self, other: False

    origin_vc = MagicMock(spec=discord.VoiceChannel)
    origin_vc.id = 3002
    origin_vc.name = "Other VC"
    target_member.voice = MagicMock(channel=origin_vc)
    target_member.move_to = AsyncMock()

    ctx.guild.members = [target_member]
    ctx.send = AsyncMock()

    # Call vcdrag_direct with string query
    await mod_cog.vcdrag_direct(ctx, target="Sax sux kyu nahi mil raha")
    target_member.move_to.assert_called_once_with(dest_vc, reason=f"VC drag requested by {ctx.author} (111)")

