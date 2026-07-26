import sys
import importlib
from pathlib import Path
from types import SimpleNamespace as SN

repo_root = str(Path(__file__).resolve().parents[1])
if sys.path[0] != repo_root:
    sys.path.insert(0, repo_root)

import pytest
import discord
from discord.ext import commands

import cogs.moderation as mod_module
importlib.reload(mod_module)
Moderation = mod_module.Moderation


class FakeChannel:
    def __init__(self, id=101, name="general"):
        self.id = id
        self.name = name
        self.mention = f"<#{id}>"


class FakeRole:
    def __init__(self, id=202, name="Admin"):
        self.id = id
        self.name = name
        self.mention = f"<@&{id}>"


class FakeGuild:
    def __init__(self, id=999, name="Test Guild"):
        self.id = id
        self.name = name


class FakeCtx:
    def __init__(self, author, guild):
        self.author = author
        self.guild = guild
        self.sent = []

    async def send(self, *args, **kwargs):
        content = args[0] if args else kwargs.get("embed") or kwargs.get("content")
        self.sent.append(content)
        return SN(id=123)


@pytest.mark.asyncio
async def test_automod_advanced_commands(monkeypatch):
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    cog = Moderation(bot=bot)
    await bot.add_cog(cog)

    guild = FakeGuild()
    author = SN(id=777, name="AdminUser")
    channel = FakeChannel(id=101, name="general")
    role = FakeRole(id=202, name="Moderator")

    # Mock config storage in memory
    fake_config = {}

    async def fake_get_config(gid):
        return fake_config

    async def fake_set_config(gid, patch):
        fake_config.update(patch)

    monkeypatch.setattr(mod_module, "get_guild_config", fake_get_config)
    monkeypatch.setattr(mod_module, "set_guild_config", fake_set_config)

    # 1. Test automod config
    ctx = FakeCtx(author, guild)
    await cog.automod_config_impl(ctx)
    assert len(ctx.sent) == 1
    assert "AutoMod Configuration" in ctx.sent[0].title

    # 2. Test automod enable
    ctx2 = FakeCtx(author, guild)
    await cog.automod_enable_impl(ctx2)
    assert fake_config.get("automod_enabled") is True

    # 3. Test automod disable
    ctx3 = FakeCtx(author, guild)
    await cog.automod_disable_impl(ctx3)
    assert fake_config.get("automod_enabled") is False

    # 4. Test automod logging
    ctx4 = FakeCtx(author, guild)
    await cog.automod_logging_impl(ctx4, channel)
    assert fake_config.get("automod_log_channel_id") == 101

    # 5. Test automod punishment
    ctx5 = FakeCtx(author, guild)
    await cog.automod_punishment_impl(ctx5, "timeout_5m")
    assert fake_config.get("automod_punishment") == "Timeout 5 Minutes"

    # 6. Test automod ignore channel
    ctx6 = FakeCtx(author, guild)
    await cog.automod_ignore_channel_impl(ctx6, channel)
    assert 101 in fake_config.get("automod_ignored_channels", [])

    # 7. Test automod ignore role
    ctx7 = FakeCtx(author, guild)
    await cog.automod_ignore_role_impl(ctx7, role)
    assert 202 in fake_config.get("automod_ignored_roles", [])

    # 8. Test automod ignore show
    ctx8 = FakeCtx(author, guild)
    await cog.automod_ignore_show_impl(ctx8)
    assert len(ctx8.sent) == 1

    # 9. Test automod unignore channel
    ctx9 = FakeCtx(author, guild)
    await cog.automod_unignore_channel_impl(ctx9, channel)
    assert 101 not in fake_config.get("automod_ignored_channels", [])

    # 10. Test automod unignore role
    ctx10 = FakeCtx(author, guild)
    await cog.automod_unignore_role_impl(ctx10, role)
    assert 202 not in fake_config.get("automod_ignored_roles", [])

    # 11. Test automod ignore reset
    ctx11 = FakeCtx(author, guild)
    await cog.automod_ignore_reset_impl(ctx11)
    assert fake_config.get("automod_ignored_channels") == []
    assert fake_config.get("automod_ignored_roles") == []
