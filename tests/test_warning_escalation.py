import sys
import importlib
from pathlib import Path
from types import SimpleNamespace as SN
from datetime import timedelta

repo_root = str(Path(__file__).resolve().parents[1])
if sys.path[0] != repo_root:
    sys.path.insert(0, repo_root)

import pytest
import discord
from discord.ext import commands

import cogs.moderation as mod_module
importlib.reload(mod_module)
Moderation = mod_module.Moderation


class FakeMember:
    def __init__(self, id=888, name="BadUser"):
        self.id = id
        self.name = name
        self.mention = f"<@{id}>"
        self.sent_dms = []
        self.timeouts = []
        self.kicked = False

    async def send(self, *args, **kwargs):
        embed = kwargs.get("embed") or (args[0] if args else None)
        self.sent_dms.append(embed)

    async def timeout(self, duration, reason=None):
        self.timeouts.append((duration, reason))

    async def kick(self, reason=None):
        self.kicked = True


class FakeGuild:
    def __init__(self, id=999, name="Test Guild"):
        self.id = id
        self.name = name
        self.icon = None

    def get_member(self, user_id):
        return None


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
async def test_warn_escalation_system(monkeypatch):
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    cog = Moderation(bot=bot)
    await bot.add_cog(cog)

    guild = FakeGuild()
    perms = SN(kick_members=True, manage_messages=True, manage_guild=True, administrator=True)
    author = SN(id=777, name="AdminUser", guild_permissions=perms)
    target = FakeMember(id=888, name="BadUser")


    # Mock DB logs and config
    stored_logs = []
    fake_config = {"modlog_dm_notifications": True}

    async def fake_log_action(guild_id, moderator_id, target_id, action, reason):
        stored_logs.append({
            "case_id": str(len(stored_logs) + 1),
            "guild_id": guild_id,
            "moderator_id": str(moderator_id),
            "target_id": str(target_id),
            "action": action,
            "reason": reason,
        })
        return len(stored_logs)

    async def fake_fetch_logs_for_target(guild_id, target_id, action=None, limit=1000):
        if action:
            return [l for l in stored_logs if l["target_id"] == str(target_id) and l["action"] == action]
        return [l for l in stored_logs if l["target_id"] == str(target_id)]

    async def fake_get_config(gid):
        return fake_config

    async def fake_set_config(gid, patch):
        fake_config.update(patch)

    async def fake_deny(*a, **k):
        return None

    monkeypatch.setattr(mod_module, "log_action", fake_log_action)
    monkeypatch.setattr(mod_module, "fetch_logs_for_target", fake_fetch_logs_for_target)
    monkeypatch.setattr(mod_module, "get_guild_config", fake_get_config)
    monkeypatch.setattr(mod_module, "set_guild_config", fake_set_config)
    monkeypatch.setattr(cog, "_post_modlog", lambda *a, **k: None)
    monkeypatch.setattr(cog, "_ensure_can_moderate", fake_deny)


    ctx = FakeCtx(author, guild)

    # 1st Warn: No timeout
    await cog.warn(ctx, target, reason="First offense spamming")
    assert len(target.sent_dms) == 1
    assert len(target.timeouts) == 0

    # 2nd Warn: No timeout
    await cog.warn(ctx, target, reason="Second offense")
    assert len(target.sent_dms) == 2
    assert len(target.timeouts) == 0

    # 3rd Warn: 2-Hour Timeout
    await cog.warn(ctx, target, reason="Third offense")
    assert len(target.sent_dms) == 3
    assert len(target.timeouts) == 1
    assert target.timeouts[0][0] == timedelta(hours=2)

    # 4th Warn: 1-Day Timeout
    await cog.warn(ctx, target, reason="Fourth offense")
    assert len(target.timeouts) == 2
    assert target.timeouts[1][0] == timedelta(days=1)

    # 5th Warn: 7-Day Timeout
    await cog.warn(ctx, target, reason="Fifth offense")
    assert len(target.timeouts) == 3
    assert target.timeouts[2][0] == timedelta(days=7)

    # 6th Warn: 14-Day Timeout
    await cog.warn(ctx, target, reason="Sixth offense")
    assert len(target.timeouts) == 4
    assert target.timeouts[3][0] == timedelta(days=14)

    # 7th Warn: 28-Day Timeout
    await cog.warn(ctx, target, reason="Seventh offense")
    assert len(target.timeouts) == 5
    assert target.timeouts[4][0] == timedelta(days=28)

    # 8th Warn: Kick
    await cog.warn(ctx, target, reason="Eighth offense")
    assert target.kicked is True

    # Check DM toggle setting (disable DMs)
    target2 = FakeMember(id=999, name="UserTwo")
    fake_config["modlog_dm_notifications"] = False
    await cog.warn(ctx, target2, reason="Test no DM")
    assert len(target2.sent_dms) == 0
