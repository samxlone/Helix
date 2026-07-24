import pytest
from types import SimpleNamespace as SN

class FakeCtx:
    def __init__(self, author=None, guild=None):
        self.author = author or SN(id=1)
        self.guild = guild or SN(id=10, name="TestGuild")
        self.sent = []

    async def send(self, content=None, embed=None, view=None, **kwargs):
        if content:
            self.sent.append(content)
        if embed:
            self.sent.append(embed)
        if view:
            self.sent.append(view)

@pytest.mark.asyncio
async def test_volume_command_permissions_and_reset(monkeypatch):
    import cogs.music as music_cog

    bot = SN()
    cog = music_cog.MusicCog(bot=bot)

    # 1. Regular User sets volume 50% -> OK
    async def fake_is_not_owner(user):
        return False
    monkeypatch.setattr(cog, "_is_owner", fake_is_not_owner)

    ctx_user = FakeCtx()
    await cog.volume.callback(cog, ctx_user, volume=50)
    player = cog._ensure_player(ctx_user.guild.id)
    assert player.volume == 0.5
    assert any("50%" in str(s) for s in ctx_user.sent)

    # 2. Regular User attempts to set volume 200% -> Rejected
    ctx_user_over = FakeCtx()
    await cog.volume.callback(cog, ctx_user_over, volume=200)
    assert player.volume == 0.5  # Unchanged
    assert any("Regular users can set volume up to" in str(s) for s in ctx_user_over.sent)

    # 3. Owner sets volume 5000% -> Allowed
    async def fake_is_owner(user):
        return True
    monkeypatch.setattr(cog, "_is_owner", fake_is_owner)

    ctx_owner = FakeCtx()
    await cog.volume.callback(cog, ctx_owner, volume=5000)
    assert player.volume == 50.0  # 5000 / 100
    assert any("5000%" in str(s) for s in ctx_owner.sent)

    # 4. Leaving VC resets volume to 100% (1.0)
    ctx_leave = FakeCtx()
    await cog.leave.callback(cog, ctx_leave)
    assert player.volume == 1.0


@pytest.mark.asyncio
async def test_help_command_interactive_panel():
    import cogs.utility as utility_cog

    async def fake_wait():
        pass

    bot = SN(is_owner=lambda u: False, wait_until_ready=fake_wait, get_command=lambda n: None)
    cog = utility_cog.Utility(bot=bot)
    cog.check_reminders.cancel()

    ctx = FakeCtx()
    await cog.help.callback(cog, ctx, command_name=None)

    assert len(ctx.sent) >= 2  # embed and view sent
    from cogs.utility import HelpView
    assert any(isinstance(s, HelpView) for s in ctx.sent)
