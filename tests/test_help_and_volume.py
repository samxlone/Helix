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
async def test_help_command_interactive_panel(monkeypatch):
    import cogs.utility as utility_cog

    async def fake_wait():
        pass

    async def fake_not_owner(u):
        return False

    bot = SN(is_owner=fake_not_owner, wait_until_ready=fake_wait, get_command=lambda n: None)
    cog = utility_cog.Utility(bot=bot)
    cog.check_reminders.cancel()

    # 1. Normal user help panel (6 options, no Owner Commands)
    ctx = FakeCtx(author=SN(id=123))
    await cog.help.callback(cog, ctx, command_name=None)

    assert len(ctx.sent) >= 2
    from cogs.utility import HelpView, HelpSelect
    view = next(s for s in ctx.sent if isinstance(s, HelpView))
    select: HelpSelect = view.children[0]
    option_labels = [opt.label for opt in select.options]
    assert "Owner Commands" not in option_labels
    assert len(option_labels) == 7

    # 2. Owner help panel (8 options, includes Owner Commands)
    monkeypatch.setenv("OWNER_ID", "999")
    ctx_owner = FakeCtx(author=SN(id=999))
    await cog.help.callback(cog, ctx_owner, command_name=None)

    view_owner = next(s for s in ctx_owner.sent if isinstance(s, HelpView))
    select_owner: HelpSelect = view_owner.children[0]
    owner_option_labels = [opt.label for opt in select_owner.options]
    assert "Owner Commands" in owner_option_labels
    assert len(owner_option_labels) == 8


