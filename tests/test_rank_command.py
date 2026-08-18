import pytest
import importlib
from types import SimpleNamespace as SN
import discord

class FakeUser:
    def __init__(self, id=1, display_name="TestUser"):
        self.id = id
        self.display_name = display_name
        self.display_avatar = SN(url="https://example.com/pfp.png")

class FakeCtx:
    def __init__(self, author):
        self.author = author
        self.guild = SN(id=1)
        self.sent = []

    async def send(self, content=None, embed=None, file=None, **kwargs):
        if embed:
            self.sent.append(embed)
        if file:
            self.sent.append(file)

@pytest.mark.asyncio
async def test_rank_command_flow(tmp_path, monkeypatch):
    db_path = tmp_path / "rank_test.sqlite"
    monkeypatch.setenv("DATABASE_URL", str(db_path))

    import utils.db as db
    importlib.reload(db)
    await db.init_db()

    import utils.leveling as leveling_utils
    importlib.reload(leveling_utils)

    # Award XP to create rank data
    await leveling_utils.award_xp(user_id=101, amount=300)
    await leveling_utils.award_xp(user_id=102, amount=100)

    # Test get_user_rank
    rank101 = await leveling_utils.get_user_rank(101)
    rank102 = await leveling_utils.get_user_rank(102)
    assert rank101 == 1
    assert rank102 == 2

    # Test rank command callback
    import cogs.leveling as leveling_cog
    importlib.reload(leveling_cog)

    bot = SN()
    cog = leveling_cog.LevelingCog(bot=bot)

    user101 = FakeUser(id=101, display_name="User_101")
    ctx = FakeCtx(author=user101)

    await cog.rank.callback(cog, ctx, member=user101)

    assert len(ctx.sent) == 1
    sent_file = ctx.sent[0]
    assert isinstance(sent_file, discord.File)
    assert sent_file.filename == "rank_card.png"

