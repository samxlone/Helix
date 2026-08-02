import pytest
from types import SimpleNamespace as SN
import os
import discord
from discord.ext import commands

class FakeUser:
    def __init__(self, id=1, name="OwnerUser"):
        self.id = id
        self.name = name
        self.display_name = name
        self.mention = f"<@{id}>"

class FakeDMChannel:
    def __init__(self):
        self.id = 123
        self.guild = None

    async def send(self, content=None, embed=None, view=None, **kwargs):
        return SimpleNamespace(content=content, embed=embed, view=view)

class FakeMessage:
    def __init__(self, author, content="!global_banner reset"):
        self.author = author
        self.content = content
        self.guild = None
        self.channel = FakeDMChannel()
        self.attachments = []
        self.mentions = []

class FakeCtx:
    def __init__(self, author, command_name="global_banner"):
        self.author = author
        self.guild = None
        self.channel = FakeDMChannel()
        self.sent = []
        self.message = FakeMessage(author)
        self.command = SN(name=command_name, reinvoke=self.fake_reinvoke)

    async def send(self, content=None, embed=None, view=None, **kwargs):
        if content:
            self.sent.append(content)
        if embed:
            self.sent.append(embed)
        if view:
            self.sent.append(view)

    async def fake_reinvoke(self, ctx):
        self.sent.append("REINVOKED_COMMAND_IN_DM")

class FakeBotUser:
    def __init__(self, id=888, name="Bot"):
        self.id = id
        self.name = name

    async def edit(self, **kwargs):
        pass

@pytest.mark.asyncio
async def test_owner_dm_execution_and_bypass(tmp_path, monkeypatch):
    owner = FakeUser(id=999, name="OwnerUser")
    monkeypatch.setenv("OWNER_ID", "999")

    import cogs.debug as debug_cog
    bot = SN(user=FakeBotUser(), guilds=[])
    cog = debug_cog.DebugCog(bot=bot)


    async def fake_is_owner(user):
        return user.id == 999

    monkeypatch.setattr(cog, "_is_owner", fake_is_owner)

    # 1. Test owner calling global_banner in DM
    ctx_dm = FakeCtx(author=owner, command_name="global_banner")
    ctx_dm.guild = None
    await cog.global_banner.callback(cog, ctx_dm, image_url="reset")
    assert any("Reset bot's global banner" in str(s) for s in ctx_dm.sent)

    # 2. Test owner calling global_avatar in DM
    ctx_dm2 = FakeCtx(author=owner, command_name="global_avatar")
    await cog.global_avatar.callback(cog, ctx_dm2, image_url="reset")
    assert any("Reset bot's global avatar" in str(s) for s in ctx_dm2.sent)

    # 3. Test NoPrivateMessage error handler reinvoke bypass in errors.py
    import utils.errors as errors_utils
    error_ctx = FakeCtx(author=owner, command_name="guild_only_cmd")

    # Mock setup error handler test
    class MockBot:
        def __init__(self):
            self.events = {}
            self.tree = SN(error=lambda f: f)
        def event(self, func):
            self.events[func.__name__] = func

        async def is_owner(self, user):
            return user.id == 999

    mock_bot = MockBot()
    await errors_utils.setup_error_handlers(mock_bot)
    on_error = mock_bot.events["on_command_error"]

    err = commands.NoPrivateMessage()
    await on_error(error_ctx, err)
    assert "REINVOKED_COMMAND_IN_DM" in error_ctx.sent

    # 4. Test non-owner DM check failure error message
    non_owner = FakeUser(id=555, name="RegularUser")
    non_owner_ctx = FakeCtx(author=non_owner, command_name="ping")
    dm_err = commands.CheckFailure("Bot commands in DMs are disabled for non-owner users.")
    await on_error(non_owner_ctx, dm_err)
    assert any("Bot commands in DMs are disabled for non-owner users" in str(s) for s in non_owner_ctx.sent)

