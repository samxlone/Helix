import pytest
from types import SimpleNamespace as SN
from datetime import datetime, timezone
import utils.db as db_utils

class FakePermissions:
    def __init__(self, manage_nicknames=True, administrator=False):
        self.manage_nicknames = manage_nicknames
        self.administrator = administrator

class FakeRole:
    def __init__(self, position=10):
        self.position = position

    def __le__(self, other):
        return self.position <= getattr(other, "position", 0)

    def __ge__(self, other):
        return self.position >= getattr(other, "position", 0)

class FakeMember:
    def __init__(self, id=1, name="User", nick=None, manage_nicknames=True, role_pos=10, guild=None):
        self.id = id
        self.name = name
        self.display_name = nick or name
        self.nick = nick
        self.mention = f"<@{id}>"
        self.guild = guild
        self.guild_permissions = FakePermissions(manage_nicknames=manage_nicknames)
        self.top_role = FakeRole(position=role_pos)


    async def edit(self, nick=None, reason=None):
        self.nick = nick
        self.display_name = nick or self.name



class FakeGuild:
    def __init__(self, id=99, name="TestGuild"):
        self.id = id
        self.name = name
        self.owner_id = 999
        self.me = FakeMember(id=888, name="Bot", manage_nicknames=True)
        self.me.top_role = SN(position=100)

    def get_member(self, member_id):
        return FakeMember(id=member_id)

class FakeCtx:
    def __init__(self, author, guild):
        self.author = author
        self.guild = guild
        self.sent = []

    async def send(self, content=None, ephemeral=False, **kwargs):
        if content:
            self.sent.append(content)

@pytest.mark.asyncio
async def test_nick_and_forcenick_flow(tmp_path, monkeypatch):
    db_file = tmp_path / "test_db.sqlite3"
    monkeypatch.setenv("DATABASE_URL", str(db_file))
    await db_utils.init_db()

    import cogs.moderation as mod_cog
    bot = SN(is_owner=lambda u: False)
    cog = mod_cog.Moderation(bot=bot)

    guild = FakeGuild()
    mod_user = FakeMember(id=1, name="ModUser", manage_nicknames=True, role_pos=50)
    target_user = FakeMember(id=2, name="TargetUser", manage_nicknames=False, role_pos=10)


    # 1. User changes own nickname via `nick`
    ctx_user = FakeCtx(author=target_user, guild=guild)
    await cog.nick.callback(cog, ctx_user, target=target_user, nickname="NewNick")
    assert target_user.nick == "NewNick"
    assert any("Changed nickname" in s for s in ctx_user.sent)

    # 2. Mod force-nicks target_user via `forcenick` / `fn`
    ctx_mod = FakeCtx(author=mod_user, guild=guild)
    await cog.forcenick.callback(cog, ctx_mod, target=target_user, nickname="LockedNick")
    assert target_user.nick == "LockedNick"
    assert any("Forced nickname" in s for s in ctx_mod.sent)

    # 3. Target user tries to change nickname via `nick` while force-nicked -> BLOCKED
    ctx_user2 = FakeCtx(author=target_user, guild=guild)
    await cog.nick.callback(cog, ctx_user2, target=target_user, nickname="BypassNick")
    assert target_user.nick == "LockedNick"  # Unchanged
    assert any("locked by a moderator" in s for s in ctx_user2.sent)

    # 4. Member update listener reverts unauthorized nickname change
    after_member = FakeMember(id=2, name="TargetUser", nick="BypassDiscordUI", guild=guild)
    await cog.on_member_update(target_user, after_member)
    assert after_member.nick == "LockedNick"


    # 5. Mod unlocks nickname via `forcenick reset` / `fn reset`
    ctx_unlock = FakeCtx(author=mod_user, guild=guild)
    await cog.forcenick.callback(cog, ctx_unlock, target=target_user, nickname="reset")
    assert any("Unlocked nickname" in s for s in ctx_unlock.sent)

    # 6. Target user can now change nickname again
    ctx_user3 = FakeCtx(author=target_user, guild=guild)
    await cog.nick.callback(cog, ctx_user3, target=target_user, nickname="FreedomNick")
    assert target_user.nick == "FreedomNick"

