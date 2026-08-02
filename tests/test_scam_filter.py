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

    async def send(self, content=None, embed=None, delete_after=None):
        self.sent_messages.append((content, embed, delete_after))


class FakeMember:
    def __init__(self, id=1, name="Scammer", roles=None):
        self.id = id
        self.name = name
        self.display_name = name
        self.mention = f"<@{id}>"
        self.bot = False
        self.roles = roles or []
        self.guild_permissions = SN(administrator=False, manage_guild=False, manage_messages=False)


class FakeMessage:
    def __init__(self, content, author, guild, channel):
        self.content = content
        self.author = author
        self.guild = guild
        self.channel = channel
        self.deleted = False

    async def delete(self):
        self.deleted = True


class FakeGuild:
    def __init__(self, id=505, name="ScamProtectionGuild"):
        self.id = id
        self.name = name
        self.me = FakeMember(id=888, name="HelixBot")
        self.channels = {}

    def get_channel(self, channel_id):
        return self.channels.get(channel_id)


@pytest.mark.asyncio
async def test_scam_link_instant_delete_and_warn(monkeypatch):
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default(), help_command=None)
    cog = Moderation(bot=bot)
    await bot.add_cog(cog)

    guild = FakeGuild()
    channel = FakeChannel(id=101, name="general")
    guild.channels[101] = channel
    modlog_ch = FakeChannel(id=999, name="modlog")
    guild.channels[999] = modlog_ch

    author = FakeMember(id=777, name="Spammer")
    msg = FakeMessage("Get free nitro at http://discord-gifts.xyz now!", author, guild, channel)

    logged_actions = []

    async def fake_get_config(gid):
        return {
            "automod_enabled": True,
            "automod_block_scam": True,
            "automod_block_invites": True,
            "automod_log_channel_id": 999
        }

    async def fake_process_escalation(g, m, reason=None, moderator=None):
        logged_actions.append(("WARN", m.id, reason))
        return (1, 1, None)

    monkeypatch.setattr(mod_module, "get_guild_config", fake_get_config)
    monkeypatch.setattr(cog, "_process_warn_escalation", fake_process_escalation)



    await cog.on_message(msg)

    # 1. Message deleted instantly
    assert msg.deleted is True

    # 2. Warning issued in DB
    assert len(logged_actions) == 1
    assert logged_actions[0][0] == "WARN"
    assert logged_actions[0][1] == 777

    # 3. Channel warning sent (delete_after=10)
    assert len(channel.sent_messages) == 1
    assert "Scam / Phishing Link" in channel.sent_messages[0][0]


@pytest.mark.asyncio
async def test_discord_invite_instant_delete_and_warn(monkeypatch):
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default(), help_command=None)
    cog = Moderation(bot=bot)
    await bot.add_cog(cog)

    guild = FakeGuild()
    channel = FakeChannel(id=101, name="general")
    guild.channels[101] = channel

    author = FakeMember(id=777, name="Advertiser")
    msg = FakeMessage("Join my server: https://discord.gg/coolserver", author, guild, channel)

    logged_actions = []

    async def fake_get_config(gid):
        return {
            "automod_enabled": True,
            "automod_block_scam": True,
            "automod_block_invites": True
        }

    async def fake_process_escalation(g, m, reason=None, moderator=None):
        logged_actions.append(("WARN", m.id, reason))
        return (1, 1, None)

    monkeypatch.setattr(mod_module, "get_guild_config", fake_get_config)
    monkeypatch.setattr(cog, "_process_warn_escalation", fake_process_escalation)


    await cog.on_message(msg)

    # 1. Message deleted instantly
    assert msg.deleted is True

    # 2. Warning issued in DB
    assert len(logged_actions) == 1
    assert logged_actions[0][0] == "WARN"

    # 3. Channel warning sent
    assert len(channel.sent_messages) == 1
    assert "Discord Invite Link" in channel.sent_messages[0][0]


@pytest.mark.asyncio
async def test_whitelisted_discord_invite_allowed(monkeypatch):
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default(), help_command=None)
    cog = Moderation(bot=bot)
    await bot.add_cog(cog)

    guild = FakeGuild()
    channel = FakeChannel(id=101, name="general")
    guild.channels[101] = channel

    author = FakeMember(id=777, name="OfficialUser")
    msg = FakeMessage("Join our official server: https://discord.gg/helix", author, guild, channel)

    logged_actions = []

    async def fake_get_config(gid):
        return {
            "automod_enabled": True,
            "automod_block_scam": True,
            "automod_block_invites": True,
            "automod_whitelisted_invites": ["helix"]
        }

    async def fake_process_escalation(g, m, reason=None, moderator=None):
        logged_actions.append(("WARN", m.id, reason))
        return (1, 1, None)

    monkeypatch.setattr(mod_module, "get_guild_config", fake_get_config)
    monkeypatch.setattr(cog, "_process_warn_escalation", fake_process_escalation)

    await cog.on_message(msg)

    # 1. Whitelisted invite link NOT deleted!
    assert msg.deleted is False

    # 2. No warnings issued!
    assert len(logged_actions) == 0


@pytest.mark.asyncio
async def test_whitelisted_user_or_role_invite_allowed(monkeypatch):
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default(), help_command=None)
    cog = Moderation(bot=bot)
    await bot.add_cog(cog)

    guild = FakeGuild()
    channel = FakeChannel(id=101, name="general")
    guild.channels[101] = channel

    # 1. Whitelisted User (ID 777)
    author_user_wl = FakeMember(id=777, name="VIPUser")
    msg1 = FakeMessage("Join this server: https://discord.gg/someother", author_user_wl, guild, channel)

    logged_actions = []

    async def fake_get_config(gid):
        return {
            "automod_enabled": True,
            "automod_block_invites": True,
            "antinuke_whitelisted_users": {"777": ["invite"]}
        }

    async def fake_process_escalation(g, m, reason=None, moderator=None):
        logged_actions.append(("WARN", m.id, reason))
        return (1, 1, None)

    monkeypatch.setattr(mod_module, "get_guild_config", fake_get_config)
    monkeypatch.setattr(cog, "_process_warn_escalation", fake_process_escalation)

    await cog.on_message(msg1)

    # Whitelisted user's invite message is NOT deleted!
    assert msg1.deleted is False
    assert len(logged_actions) == 0


