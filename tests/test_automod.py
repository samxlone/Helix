import sys
import importlib
from pathlib import Path

repo_root = str(Path(__file__).resolve().parents[1])
if sys.path[0] != repo_root:
    sys.path.insert(0, repo_root)

import pytest
from types import SimpleNamespace as SN
import discord
from discord.ext import commands
import cogs.moderation as mod_module
importlib.reload(mod_module)
print("MODULE FILE:", mod_module.__file__)
Moderation = mod_module.Moderation






class FakeRule:
    def __init__(self, id=1, name="TestRule", enabled=True, trigger_type="keyword"):
        self.id = id
        self.name = name
        self.enabled = enabled
        self.trigger_type = trigger_type

    async def delete(self, reason=None):
        pass

    async def edit(self, enabled=None, reason=None):
        if enabled is not None:
            self.enabled = enabled

class FakeGuild:
    def __init__(self):
        self.id = 123
        self.name = "Test Guild"
        self.rules = [FakeRule(1, "BadWords"), FakeRule(2, "AntiSpam")]

    async def fetch_automod_rules(self):
        return self.rules

    async def create_automod_rule(self, name, event_type, trigger_type, actions, enabled=True, trigger_metadata=None, reason=None):
        r = FakeRule(id=99, name=name, enabled=enabled, trigger_type=trigger_type)
        self.rules.append(r)
        return r

class FakeCtx:
    def __init__(self, author, guild):
        self.author = author
        self.guild = guild
        self.sent = []

    async def send(self, content=None, embed=None, ephemeral=False):
        if content:
            self.sent.append(content)
        if embed:
            self.sent.append(embed)

    async def send_help(self, cmd):
        self.sent.append("help")

@pytest.mark.asyncio
async def test_automod_commands():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    cog = Moderation(bot=bot)
    await bot.add_cog(cog)
    guild = FakeGuild()
    author = SN(id=777, name="AdminUser")

    ctx = FakeCtx(author, guild)
    await cog.automod_list_impl(ctx)


    assert len(ctx.sent) == 1
    assert "BadWords" in ctx.sent[0].description

    # 2. Test automod blockwords
    ctx2 = FakeCtx(author, guild)
    await cog.automod_blockwords_impl(ctx2, rule_name="NoBadWords", words="word1, word2")
    assert len(ctx2.sent) == 1
    assert "NoBadWords" in ctx2.sent[0].description

    # 3. Test automod antispam
    ctx3 = FakeCtx(author, guild)
    await cog.automod_antispam_impl(ctx3)
    assert len(ctx3.sent) == 1
    assert "Helix Anti-Spam" in ctx3.sent[0].description

    # 4. Test automod toggle
    ctx4 = FakeCtx(author, guild)
    await cog.automod_toggle_impl(ctx4, rule_id=1)
    assert len(ctx4.sent) == 1
    assert "Disabled" in ctx4.sent[0]

    # 5. Test automod delete
    ctx5 = FakeCtx(author, guild)
    await cog.automod_delete_impl(ctx5, rule_id=1)
    assert len(ctx5.sent) == 1
    assert "deleted successfully" in ctx5.sent[0]










