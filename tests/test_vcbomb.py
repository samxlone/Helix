import importlib
import pytest
import asyncio
from types import SimpleNamespace
import discord

class FakeVC:
    def __init__(self, id, name, user_connect=True):
        self.id = id
        self.name = name
        self._user_connect = user_connect

    def permissions_for(self, entity):
        perms = SimpleNamespace()
        perms.connect = self._user_connect
        perms.move_members = True
        return perms

class FakeRole:
    def __init__(self, position):
        self.position = position

    def __le__(self, other):
        return self.position <= getattr(other, "position", 0)

class FakeUser:
    def __init__(self, id=1, name="TargetUser", pos=10):
        self.id = id
        self.name = name
        self.display_name = name
        self.mention = f"<@{id}>"
        self.top_role = FakeRole(pos)


class FakeContext:
    def __init__(self, author, guild):
        self.author = author
        self.guild = guild
        self.sent = []
        self.command = None

    async def send(self, content=None, embed=None, **kwargs):
        if content:
            self.sent.append(content)
        if embed:
            self.sent.append(embed)

    async def send_help(self, cmd):
        self.sent.append("HELP")


@pytest.mark.asyncio
async def test_vcbomb_start_and_stop(tmp_path, monkeypatch):
    db_path = tmp_path / "vcbomb.sqlite"
    monkeypatch.setenv("DATABASE_URL", str(db_path))

    import utils.db as db
    importlib.reload(db)
    await db.init_db()

    from cogs.moderation import Moderation

    vc1 = FakeVC(id=101, name="Lounge 1")
    vc2 = FakeVC(id=102, name="Lounge 2")

    moved_to = []

    target = FakeUser(id=200, name="Victim")
    async def mock_move_to(vc, reason=None):
        moved_to.append(vc)

    target.move_to = mock_move_to
    target.voice = SimpleNamespace(channel=vc1)

    owner = FakeUser(id=999, name="Owner", pos=100)
    owner.guild_permissions = SimpleNamespace(move_members=True, administrator=True)


    bot_me = SimpleNamespace(
        id=888,
        top_role=SimpleNamespace(position=90),
        guild_permissions=SimpleNamespace(move_members=True)
    )

    guild = SimpleNamespace(
        id=500,
        name="TestGuild",
        owner_id=999,
        me=bot_me,
        voice_channels=[vc1, vc2],
        get_member=lambda uid: target if uid == 200 else None
    )

    bot = SimpleNamespace(
        loop=asyncio.get_event_loop(),
        get_guild=lambda gid: guild if gid == 500 else None
    )
    cog = Moderation(bot=bot)


    monkeypatch.setenv("OWNER_ID", "999")

    # 1. Non-owner rejection test
    regular_user = FakeUser(id=333, name="RegularUser")
    non_owner_ctx = FakeContext(author=regular_user, guild=guild)
    await cog.vcbomb.callback(cog, non_owner_ctx, target=target)
    assert any("restricted to the Bot Owner" in str(s) for s in non_owner_ctx.sent)
    assert (500, 200) not in cog._vcbomb_tasks

    # 2. Owner Start VC Bomb
    ctx = FakeContext(author=owner, guild=guild)
    await cog.vcbomb.callback(cog, ctx, target=target)
    assert any("VC Bomb" in str(s) and "activated" in str(s) for s in ctx.sent)
    assert (500, 200) in cog._vcbomb_tasks

    # Let the vcbomb loop run for a few milliseconds
    await asyncio.sleep(0.8)
    assert len(moved_to) > 0

    # 3. Owner Stop VC Bomb
    ctx.sent.clear()
    await cog.vcbomb_stop.callback(cog, ctx, target=target)
    assert any("VC Bomb" in str(s) and "stopped" in str(s) for s in ctx.sent)
    assert (500, 200) not in cog._vcbomb_tasks

    cog.cog_unload()

