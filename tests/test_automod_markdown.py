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
        self.sent_messages.append((content, embed))
        return SN(id=555)


class FakeUser:
    def __init__(self, id=202, name="RegularMember", is_admin=False):
        self.id = id
        self.name = name
        self.display_name = name
        self.mention = f"<@{id}>"
        self.bot = False
        self.roles = []
        self.guild_permissions = SN(
            administrator=is_admin,
            manage_guild=is_admin,
            manage_messages=is_admin
        )


class FakeMessage:
    def __init__(self, content, author, channel, guild):
        self.content = content
        self.author = author
        self.channel = channel
        self.guild = guild
        self.deleted = False

    async def delete(self):
        self.deleted = True


class FakeGuild:
    def __init__(self, id=303, name="TestServer"):
        self.id = id
        self.name = name
        self.channels = {}

    def get_channel(self, channel_id):
        return self.channels.get(channel_id)


@pytest.mark.asyncio
async def test_automod_markdown_heading_filter(monkeypatch):
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    cog = Moderation(bot=bot)
    await bot.add_cog(cog)

    guild = FakeGuild()
    log_ch = FakeChannel(id=999, name="mod-log")
    guild.channels[999] = log_ch

    regular_user = FakeUser(id=202, name="UserOne", is_admin=False)
    admin_user = FakeUser(id=303, name="AdminUser", is_admin=True)
    channel = FakeChannel(id=101, name="chat")

    fake_config = {
        "automod_enabled": True,
        "automod_block_markdown": True,
        "automod_log_channel_id": 999,
        "automod_ignored_channels": [],
        "automod_ignored_roles": []
    }

    async def fake_get_config(gid):
        return fake_config

    async def fake_log_action(*args, **kwargs):
        return 1

    monkeypatch.setattr(mod_module, "get_guild_config", fake_get_config)
    monkeypatch.setattr(mod_module, "log_action", fake_log_action)

    # 1. Regular user posts '# Heading 1' -> deleted
    msg1 = FakeMessage("# Heading 1", regular_user, channel, guild)
    await cog.on_message(msg1)
    assert msg1.deleted is True
    assert len(channel.sent_messages) == 1

    # 2. Regular user posts '## Heading 2' -> deleted
    msg2 = FakeMessage("## Subheading\nSome text", regular_user, channel, guild)
    await cog.on_message(msg2)
    assert msg2.deleted is True

    # 3. Regular user posts '### Heading 3' -> deleted
    msg3 = FakeMessage("### H3 Header", regular_user, channel, guild)
    await cog.on_message(msg3)
    assert msg3.deleted is True

    # 4. Regular user posts normal message -> NOT deleted
    msg4 = FakeMessage("Hello everyone!", regular_user, channel, guild)
    await cog.on_message(msg4)
    assert msg4.deleted is False

    # 5. Admin user posts '# Heading' -> NOT deleted (bypass)
    msg_admin = FakeMessage("# Admin Announcement", admin_user, channel, guild)
    await cog.on_message(msg_admin)
    assert msg_admin.deleted is False
