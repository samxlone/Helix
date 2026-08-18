import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
import discord
from main import bot
from utils.cog_loader import load_cogs


@pytest.mark.asyncio
async def test_vcmove_and_massmove():
    """Verify vc moveall moves all non-bot members from source to destination."""
    await load_cogs(bot)

    mod_cog = bot.get_cog("Moderation")
    assert mod_cog is not None

    cmd_vcmove = bot.get_command("vcmove")
    cmd_moveall = bot.get_command("moveall")
    assert cmd_vcmove is not None
    assert cmd_moveall == cmd_vcmove

    ctx = MagicMock()
    ctx.guild = MagicMock()
    ctx.guild.id = 12345
    ctx.guild.owner_id = 999
    ctx.guild.me = MagicMock()
    ctx.author = MagicMock()
    ctx.author.id = 999
    ctx.interaction = None

    source_vc = MagicMock(spec=discord.VoiceChannel)
    source_vc.id = 101
    source_vc.name = "Lobby"
    source_vc.mention = "<#101>"

    dest_vc = MagicMock(spec=discord.VoiceChannel)
    dest_vc.id = 102
    dest_vc.name = "Gaming Room"
    dest_vc.mention = "<#102>"
    dest_vc.permissions_for = MagicMock(return_value=MagicMock(connect=True))

    m1 = MagicMock(spec=discord.Member)
    m1.bot = False
    m1.move_to = AsyncMock()

    m2 = MagicMock(spec=discord.Member)
    m2.bot = False
    m2.move_to = AsyncMock()

    bot_member = MagicMock(spec=discord.Member)
    bot_member.bot = True

    source_vc.members = [m1, m2, bot_member]
    ctx.author.voice = MagicMock(channel=source_vc)

    status_msg = MagicMock()
    status_msg.edit = AsyncMock()
    ctx.send = AsyncMock(return_value=status_msg)

    await mod_cog.vc_moveall(ctx, destination=dest_vc, source=source_vc)

    m1.move_to.assert_called_once()
    m2.move_to.assert_called_once()


@pytest.mark.asyncio
async def test_vcmute_and_vcunmute():
    """Verify vc muteall and unmuteall edit member mute states."""
    await load_cogs(bot)

    mod_cog = bot.get_cog("Moderation")
    assert mod_cog is not None

    cmd_massmute = bot.get_command("massmute")
    cmd_massunmute = bot.get_command("massunmute")
    assert cmd_massmute is not None
    assert cmd_massunmute is not None

    ctx = MagicMock()
    ctx.guild = MagicMock()
    ctx.guild.id = 12345
    ctx.guild.owner_id = 999
    ctx.author = MagicMock()
    ctx.author.id = 999
    ctx.interaction = None

    vc = MagicMock(spec=discord.VoiceChannel)
    vc.id = 101
    vc.name = "Team 1"

    m1 = MagicMock(spec=discord.Member)
    m1.bot = False
    m1.voice = MagicMock(mute=False, deaf=False)
    m1.edit = AsyncMock()

    vc.members = [m1]
    ctx.author.voice = MagicMock(channel=vc)

    status_msg = MagicMock()
    status_msg.edit = AsyncMock()
    ctx.send = AsyncMock(return_value=status_msg)

    # Test mass mute
    await mod_cog.vc_muteall(ctx, channel=vc)
    m1.edit.assert_called_with(mute=True, reason=f"VC mass mute by {ctx.author} (999)")

    # Test mass unmute
    m1.voice.mute = True
    await mod_cog.vc_unmuteall(ctx, channel=vc)
    m1.edit.assert_called_with(mute=False, reason=f"VC mass unmute by {ctx.author} (999)")

    # Test mass deafen
    await mod_cog.vc_deafenall(ctx, channel=vc)
    m1.edit.assert_called_with(deafen=True, reason=f"VC mass deafen by {ctx.author} (999)")

    # Test mass undeafen
    m1.voice.deaf = True
    await mod_cog.vc_undeafenall(ctx, channel=vc)
    m1.edit.assert_called_with(deafen=False, reason=f"VC mass undeafen by {ctx.author} (999)")


@pytest.mark.asyncio
async def test_vcmove_multi_word_channel_resolution():
    """Verify that multi-word voice channels with spaces (e.g. 'baithak Sax sux nahi mil raha') resolve cleanly."""
    await load_cogs(bot)
    mod_cog = bot.get_cog("Moderation")

    ctx = MagicMock()
    ctx.guild = MagicMock()
    ctx.guild.id = 12345
    ctx.guild.owner_id = 999
    ctx.guild.me = MagicMock()
    ctx.author = MagicMock(id=999)
    ctx.interaction = None

    vc1 = MagicMock(spec=discord.VoiceChannel)
    vc1.id = 1001
    vc1.name = "baithak"
    vc1.mention = "<#1001>"

    vc2 = MagicMock(spec=discord.VoiceChannel)
    vc2.id = 1002
    vc2.name = "Sax sux nahi mil raha"
    vc2.mention = "<#1002>"
    vc2.permissions_for = MagicMock(return_value=MagicMock(connect=True))

    m1 = MagicMock(spec=discord.Member)
    m1.bot = False
    m1.move_to = AsyncMock()
    vc1.members = [m1]

    ctx.guild.voice_channels = [vc1, vc2]
    ctx.author.voice = MagicMock(channel=vc1)

    status_msg = MagicMock()
    status_msg.edit = AsyncMock()
    ctx.send = AsyncMock(return_value=status_msg)

    # Test 1: User types "baithak Sax sux nahi mil raha"
    await mod_cog.vcmove_direct(ctx, channels="baithak Sax sux nahi mil raha")
    m1.move_to.assert_called_with(vc2, reason=f"Mass move by {ctx.author} (999)")

    # Test 2: User types "Sax sux nahi mil raha" while in vc1
    m1.move_to.reset_mock()
    await mod_cog.vcmove_direct(ctx, channels="Sax sux nahi mil raha")
    m1.move_to.assert_called_with(vc2, reason=f"Mass move by {ctx.author} (999)")

    # Test 3: Slash command context with interaction followup
    slash_ctx = MagicMock()
    slash_ctx.guild = ctx.guild
    slash_ctx.author = ctx.author
    slash_ctx.interaction = MagicMock()
    slash_ctx.interaction.followup = MagicMock()
    slash_ctx.interaction.followup.send = AsyncMock()
    slash_ctx.defer = AsyncMock()

    m1.move_to.reset_mock()
    await mod_cog.vc_moveall(slash_ctx, destination=vc2, source=vc1)
    slash_ctx.interaction.followup.send.assert_called_once()

