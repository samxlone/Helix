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
        self.sent_messages = []
        self.purged_count = 0

    async def send(self, content=None, embed=None, ephemeral=False):
        self.sent_messages.append(content)

    async def purge(self, limit=10, check=None):
        # Fake purge that returns fake deleted messages
        msgs = [SN(id=i, author=SN(id=777 if i % 2 == 0 else 888)) for i in range(min(limit, 20))]
        matching = [m for m in msgs if check(m)] if check else msgs
        self.purged_count = len(matching)
        return matching


class FakeMember:
    def __init__(self, id=1, name="AdminUser"):
        self.id = id
        self.name = name
        self.mention = f"<@{id}>"
        self.guild_permissions = SN(manage_messages=True, administrator=True)


class FakeGuild:
    def __init__(self, id=505, name="PurgeGuild"):
        self.id = id
        self.name = name
        self.me = FakeMember(id=888, name="HelixBot")


@pytest.mark.asyncio
async def test_purge_user_filtered(monkeypatch):
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default(), help_command=None)
    cog = Moderation(bot=bot)
    await bot.add_cog(cog)

    guild = FakeGuild()
    channel = FakeChannel()
    author = FakeMember(id=999)
    target_user = FakeMember(id=777, name="khushusaurus")

    async def fake_defer(ephemeral=True):
        pass

    ctx = SN(
        guild=guild,
        channel=channel,
        author=author,
        send=channel.send,
        defer=fake_defer
    )


    async def fake_log_action(guild_id, moderator_id, target_id, action, reason):
        return 1

    async def fake_post_modlog(g, c, a, m, t, r):
        pass

    monkeypatch.setattr(mod_module, "log_action", fake_log_action)
    monkeypatch.setattr(cog, "_post_modlog", fake_post_modlog)

    guild.members = [target_user]

    # Test !purge khushusaurus 10
    await cog.purge(ctx, arg1="khushusaurus", arg2="10")
    assert len(channel.sent_messages) == 1
    assert "deleted" in channel.sent_messages[0].lower()


