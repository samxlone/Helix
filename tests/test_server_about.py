import pytest
from types import SimpleNamespace as SN

class FakeMe:
    def __init__(self):
        self.bio = None

    async def edit(self, bio=None, **kwargs):
        self.bio = bio

class FakeGuild:
    def __init__(self, id=101, name="TestGuild"):
        self.id = id
        self.name = name
        self.me = FakeMe()

class FakeCtx:
    def __init__(self, author, guild):
        self.author = author
        self.guild = guild
        self.sent = []

    async def send(self, content=None, ephemeral=False, **kwargs):
        if content:
            self.sent.append(content)

@pytest.mark.asyncio
async def test_server_about_owner_command():
    import cogs.debug as debug_cog

    async def fake_is_owner(user):
        return user.id == 1

    bot = SN(owner_user=SN(id=1), is_owner=fake_is_owner)
    cog = debug_cog.DebugCog(bot=bot)

    guild = FakeGuild()
    owner_user = SN(id=1)
    non_owner_user = SN(id=2)

    # 1. Test non-owner denied
    ctx_non_owner = FakeCtx(author=non_owner_user, guild=guild)
    await cog.server_about.callback(cog, ctx_non_owner, text="Bot Bio")
    assert any("not authorized" in s for s in ctx_non_owner.sent)
    assert guild.me.bio is None

    # 2. Test owner update bio
    ctx_owner = FakeCtx(author=owner_user, guild=guild)
    await cog.server_about.callback(cog, ctx_owner, text="Official Helix Bot Bio")
    assert any("Updated bot's server 'About Me' bio" in s for s in ctx_owner.sent)
    assert guild.me.bio == "Official Helix Bot Bio"

    # 3. Test owner reset bio
    ctx_owner.sent.clear()
    await cog.server_about.callback(cog, ctx_owner, text="reset")
    assert any("Reset bot's server 'About Me' bio" in s for s in ctx_owner.sent)
    assert guild.me.bio is None

