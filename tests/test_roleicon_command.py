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

import cogs.utility as util_module
Utility = util_module.Utility



class FakeRole:
    def __init__(self, id=101, name="Moderator", position=10):
        self.id = id
        self.name = name
        self.position = position
        self.mention = f"<@&{id}>"
        self.display_icon = None

    def __ge__(self, other):
        return self.position >= getattr(other, "position", 0)

    async def edit(self, display_icon=None, reason=None):
        self.display_icon = display_icon


class FakeMember:
    def __init__(self, id=1, name="Suryaa", is_admin=True, top_role_pos=100):
        self.id = id
        self.name = name
        self.display_name = name
        self.mention = f"<@{id}>"
        self.top_role = SN(position=top_role_pos)
        self.guild_permissions = SN(
            manage_roles=is_admin,
            administrator=is_admin
        )


class FakeContext:
    def __init__(self, author, guild):
        self.author = author
        self.guild = guild
        self.sent = []

    async def send(self, content=None, embed=None, ephemeral=False):
        if content:
            self.sent.append(content)
        if embed:
            self.sent.append(embed.title)


@pytest.mark.asyncio
async def test_roleicon_command():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default(), help_command=None)
    cog = Utility(bot=bot)
    await bot.add_cog(cog)


    admin_user = FakeMember(id=1, name="Suryaa", is_admin=True, top_role_pos=100)
    me_bot = FakeMember(id=99, name="HelixBot", is_admin=True, top_role_pos=90)
    target_role = FakeRole(id=202, name="Spokesman", position=10)

    guild = SN(id=555, owner_id=1, me=me_bot)
    ctx = FakeContext(author=admin_user, guild=guild)

    # Test setting unicode emoji icon
    await cog.roleicon.callback(cog, ctx, role=target_role, icon="🕶️")
    assert target_role.display_icon == "🕶️"
    assert any("Role Icon Updated!" in s for s in ctx.sent)

    # Test removing icon
    ctx.sent.clear()
    await cog.roleicon.callback(cog, ctx, role=target_role, icon="remove")
    assert target_role.display_icon is None
    assert any("Role Icon Updated!" in s for s in ctx.sent)
