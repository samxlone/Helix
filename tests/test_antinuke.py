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
        self.overwrites = {}

    async def send(self, content=None, embed=None):
        self.sent_messages.append((content, embed))

    def overwrites_for(self, role):
        return SN(send_messages=True, send_messages_in_threads=True, create_public_threads=True)

    async def set_permissions(self, role, overwrite=None):
        self.overwrites[role] = overwrite


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
        self.quarantined = False

    async def remove_roles(self, *roles, reason=None):
        self.stripped = True
        self.roles = [r for r in self.roles if r not in roles]

    async def kick(self, reason=None):
        self.kicked = True

    async def timeout(self, duration, reason=None):
        self.quarantined = True

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
        self.text_channels = []
        self.default_role = FakeRole(name="@everyone", position=0, id=505)

    def get_member(self, user_id):
        return self.members.get(user_id)

    def get_channel(self, channel_id):
        return self.channels.get(channel_id)

    async def ban(self, user, reason=None, delete_message_days=1):
        if isinstance(user, FakeMember):
            user.banned = True

    async def create_text_channel(self, name, category=None, reason=None):
        ch = FakeChannel(id=random_id(), name=name)
        self.text_channels.append(ch)
        return ch


def random_id():
    import random
    return random.randint(1000, 9999)


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
async def test_antinuke_strict_mode(monkeypatch):
    """Verify strict mode immediately bans on 1st unauthorized action."""
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default(), help_command=None)
    cog = Moderation(bot=bot)
    await bot.add_cog(cog)

    guild = FakeGuild()
    attacker = FakeMember(id=444, name="InstantNuker")
    guild.members[444] = attacker

    fake_config = {
        "antinuke_enabled": True,
        "antinuke_strict": True,
        "antinuke_punishment": "ban",
        "antinuke_whitelisted_users": []
    }

    async def fake_get_config(gid):
        return fake_config

    async def fake_log_action(*args, **kwargs):
        return 1

    monkeypatch.setattr(mod_module, "get_guild_config", fake_get_config)
    monkeypatch.setattr(mod_module, "log_action", fake_log_action)


    # 1st action triggers instant ban because strict mode is ON
    await cog._check_and_trigger_antinuke(guild, "role_delete", fallback_executor=attacker)
    assert attacker.banned is True


@pytest.mark.asyncio
async def test_antinuke_category_whitelisting(monkeypatch):
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default(), help_command=None)
    cog = Moderation(bot=bot)
    await bot.add_cog(cog)

    guild = FakeGuild()
    user_whitelisted = FakeMember(id=555, name="ScopedUser", roles=[FakeRole(name="UserRole", position=5, id=5)])
    guild.members[555] = user_whitelisted

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


@pytest.mark.asyncio
async def test_antinuke_verified_admin_check(monkeypatch):
    """Verify only Server Owner or Whitelisted Admins can edit Anti-Nuke config."""
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default(), help_command=None)
    cog = Moderation(bot=bot)
    await bot.add_cog(cog)

    guild = FakeGuild(owner_id=111)
    owner = FakeMember(id=111, name="Owner")
    whitelisted_admin = FakeMember(id=222, name="WLAdmin")
    unverified_admin = FakeMember(id=333, name="NormalAdmin")

    fake_config = {
        "antinuke_enabled": True,
        "antinuke_whitelisted_users": {"222": ["config"]}
    }

    async def fake_get_config(gid):
        return fake_config

    monkeypatch.setattr(mod_module, "get_guild_config", fake_get_config)

    ctx_owner = SN(guild=guild, author=owner, send=lambda *a, **k: None)
    ctx_wl = SN(guild=guild, author=whitelisted_admin, send=lambda *a, **k: None)
    ctx_unverified = SN(guild=guild, author=unverified_admin, send=lambda *a, **k: None)

    # Owner passes
    assert await cog._is_antinuke_admin(ctx_owner) is True
    # Whitelisted Admin with 'config' category passes
    assert await cog._is_antinuke_admin(ctx_wl) is True
    # Unverified Admin is blocked
    assert await cog._is_antinuke_admin(ctx_unverified) is False

