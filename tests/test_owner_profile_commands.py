import pytest
from types import SimpleNamespace as SN

class FakeUser:
    def __init__(self, id=1):
        self.id = id
        self.mention = f"<@{id}>"

class FakeMessage:
    def __init__(self, attachments=None):
        self.attachments = attachments or []

class FakeGuild:
    def __init__(self, id=55, name="TestGuild"):
        self.id = id
        self.name = name
        self.edited_me = {}

    @property
    def me(self):
        class FakeMe:
            def __init__(outer_self):
                pass
            async def edit(outer_self, **kwargs):
                self.edited_me = kwargs
        return FakeMe()

class FakeBotUser:
    def __init__(self):
        self.edited_user = {}

    async def edit(self, **kwargs):
        self.edited_user = kwargs

class FakeCtx:
    def __init__(self, author, guild, message=None):
        self.author = author
        self.guild = guild
        self.message = message or FakeMessage()
        self.sent = []

    async def send(self, content=None, ephemeral=False, **kwargs):
        if content:
            self.sent.append(content)

@pytest.mark.asyncio
async def test_owner_server_avatar_and_banner(monkeypatch):
    import cogs.debug as debug_cog

    bot_user = FakeBotUser()
    bot = SN(
        user=bot_user,
        get_guild=lambda gid: FakeGuild(id=gid, name=f"Guild_{gid}")
    )
    cog = debug_cog.DebugCog(bot=bot)

    # Monkeypatch _is_owner
    async def fake_is_owner(user):
        return user.id == 999

    monkeypatch.setattr(cog, '_is_owner', fake_is_owner)

    owner = FakeUser(id=999)
    non_owner = FakeUser(id=111)
    guild = FakeGuild(id=55, name="TestGuild")

    # 1. Non-owner attempt should fail
    ctx_unauth = FakeCtx(author=non_owner, guild=guild)
    await cog.server_avatar.callback(cog, ctx_unauth, image_url="reset")
    assert any("not authorized" in s for s in ctx_unauth.sent)

    # 2. Reset server avatar
    ctx_reset = FakeCtx(author=owner, guild=guild)
    await cog.server_avatar.callback(cog, ctx_reset, image_url="reset")
    assert guild.edited_me.get("avatar") is None
    assert any("Reset bot's server avatar" in s for s in ctx_reset.sent)

    # 3. Reset server banner
    ctx_banner_reset = FakeCtx(author=owner, guild=guild)
    await cog.server_banner.callback(cog, ctx_banner_reset, image_url="reset")
    assert guild.edited_me.get("banner") is None
    assert any("Reset bot's server banner" in s for s in ctx_banner_reset.sent)

    # 4. Reset global avatar & banner
    ctx_global_av = FakeCtx(author=owner, guild=guild)
    await cog.global_avatar.callback(cog, ctx_global_av, image_url="reset")
    assert bot_user.edited_user.get("avatar") is None
    assert any("Reset bot's global avatar" in s for s in ctx_global_av.sent)

    ctx_global_bn = FakeCtx(author=owner, guild=guild)
    await cog.global_banner.callback(cog, ctx_global_bn, image_url="reset")
    assert bot_user.edited_user.get("banner") is None
    assert any("Reset bot's global banner" in s for s in ctx_global_bn.sent)
