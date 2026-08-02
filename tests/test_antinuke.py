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
    def __init__(self, id=101, name="mod-log"):
        self.id = id
        self.name = name
        self.mention = f"<#{id}>"
        self.sent_messages = []

    async def send(self, content=None, embed=None):
        self.sent_messages.append((content, embed))


class FakeRole:
    def __init__(self, name="Admin", position=10, id=15):
        self.id = id
        self.name = name
        self.position = position

    def __lt__(self, other):
        return self.position < getattr(other, "position", 999)



class FakeMember:
    def __init__(self, id=1, name="RogueMod", roles=None):
        self.id = id
        self.name = name
        self.display_name = name
        self.mention = f"<@{id}>"
        self.bot = False
        self.roles = roles if roles is not None else [FakeRole(name="Admin", position=10)]
        self.top_role = FakeRole(name="Top", position=50)
        self.guild_permissions = SN(view_audit_log=True)
        self.stripped = False
        self.kicked = False
        self.banned = False

    async def remove_roles(self, *roles, reason=None):
        self.stripped = True
        self.roles = [r for r in self.roles if r not in roles]

    async def kick(self, reason=None):
        self.kicked = True

    async def send(self, embed=None):
        pass



class FakeGuild:
    def __init__(self, id=505, name="DefenseGuild", owner_id=999):
        self.id = id
        self.name = name
        self.owner_id = owner_id
        self.owner = FakeMember(id=owner_id, name="ServerOwner")
        self.me = FakeMember(id=888, name="HelixBot", roles=[SN(name="HelixRole", position=100)])
        self.channels = {}
        self.members = {}

    def get_member(self, user_id):
        return self.members.get(user_id)

    def get_channel(self, channel_id):
        return self.channels.get(channel_id)

    async def ban(self, user, reason=None, delete_message_days=1):
        if isinstance(user, FakeMember):
            user.banned = True


@pytest.mark.asyncio
async def test_antinuke_threshold_and_punishment(monkeypatch):
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default(), help_command=None)
    cog = Moderation(bot=bot)
    await bot.add_cog(cog)

    guild = FakeGuild()
    attacker = FakeMember(id=777, name="Attacker")
    guild.members[777] = attacker
    log_ch = FakeChannel(id=999)
    guild.channels[999] = log_ch

    fake_config = {
        "antinuke_enabled": True,
        "antinuke_punishment": "strip_roles",
        "antinuke_whitelisted_users": [],
        "antinuke_log_channel_id": 999
    }

    async def fake_get_config(gid):
        return fake_config

    async def fake_log_action(*args, **kwargs):
        return 1

    monkeypatch.setattr(mod_module, "get_guild_config", fake_get_config)
    monkeypatch.setattr(mod_module, "log_action", fake_log_action)

    # Trigger 3 channel_delete actions within 10 seconds
    await cog._check_and_trigger_antinuke(guild, "channel_delete", fallback_executor=attacker)
    assert attacker.stripped is False

    await cog._check_and_trigger_antinuke(guild, "channel_delete", fallback_executor=attacker)
    assert attacker.stripped is False

    # 3rd delete triggers Anti-Nuke punishment!
    await cog._check_and_trigger_antinuke(guild, "channel_delete", fallback_executor=attacker)
    assert attacker.stripped is True
    assert len(log_ch.sent_messages) == 1


@pytest.mark.asyncio
async def test_antinuke_permission_abuse_and_webhooks(monkeypatch):
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default(), help_command=None)
    cog = Moderation(bot=bot)
    await bot.add_cog(cog)

    guild = FakeGuild()
    attacker = FakeMember(id=888, name="PermissionAbuser")
    guild.members[888] = attacker

    fake_config = {
        "antinuke_enabled": True,
        "antinuke_punishment": "ban",
        "antinuke_whitelisted_users": []
    }

    async def fake_get_config(gid):
        return fake_config

    async def fake_log_action(*args, **kwargs):
        return 1

    monkeypatch.setattr(mod_module, "get_guild_config", fake_get_config)
    monkeypatch.setattr(mod_module, "log_action", fake_log_action)

    # 3 permission abuse detections trigger ban
    for _ in range(3):
        await cog._check_and_trigger_antinuke(guild, "permission_abuse", fallback_executor=attacker)

    assert attacker.banned is True


@pytest.mark.asyncio
async def test_antinuke_category_whitelisting(monkeypatch):
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default(), help_command=None)
    cog = Moderation(bot=bot)
    await bot.add_cog(cog)

    guild = FakeGuild()
    user_whitelisted = FakeMember(id=555, name="ScopedUser", roles=[FakeRole(name="UserRole", position=5, id=5)])
    guild.members[555] = user_whitelisted

    role_whitelisted = FakeMember(id=666, name="ScopedRoleUser", roles=[FakeRole(name="TrustedRole", position=15, id=15)])
    guild.members[666] = role_whitelisted


    # User 555 is whitelisted for "channel_delete", Role 15 is whitelisted for "role_delete"
    fake_config = {
        "antinuke_enabled": True,
        "antinuke_punishment": "ban",
        "antinuke_whitelisted_users": {"555": ["channel_delete"]},
        "antinuke_whitelisted_roles": {"15": ["role_delete"]}
    }

    async def fake_get_config(gid):
        return fake_config

    monkeypatch.setattr(mod_module, "get_guild_config", fake_get_config)

    # 1. User 555 performs 5 channel deletes -> Immune because of category "channel_delete"
    for _ in range(5):
        await cog._check_and_trigger_antinuke(guild, "channel_delete", fallback_executor=user_whitelisted)
    assert user_whitelisted.banned is False

    # 2. User 555 performs 3 role deletes -> Not whitelisted for role_delete -> Banned!
    for _ in range(3):
        await cog._check_and_trigger_antinuke(guild, "role_delete", fallback_executor=user_whitelisted)
    assert user_whitelisted.banned is True


