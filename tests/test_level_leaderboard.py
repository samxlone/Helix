import pytest
import importlib
from types import SimpleNamespace as SN

class FakeInteraction:
    def __init__(self, user):
        self.user = user
        self.response = SN(edit_message=self.edit_message)
        self.edited = []

    async def edit_message(self, embed=None, view=None):
        self.edited.append((embed, view))

class FakeUser:
    def __init__(self, id=1, display_name="TestUser"):
        self.id = id
        self.display_name = display_name
        self.mention = f"<@{id}>"

class FakeCtx:
    def __init__(self, author):
        self.author = author
        self.guild = SN(id=1, icon=None)
        self.sent = []

    async def send(self, content=None, embed=None, view=None, **kwargs):
        if embed:
            self.sent.append(embed)
        if view:
            self.sent.append(view)

@pytest.mark.asyncio
async def test_level_leaderboard_flow(tmp_path, monkeypatch):
    db_path = tmp_path / "level_lb.sqlite"
    monkeypatch.setenv("DATABASE_URL", str(db_path))

    import utils.db as db
    importlib.reload(db)
    await db.init_db()

    import utils.leveling as leveling_utils
    importlib.reload(leveling_utils)

    # Award XP to user 101 and 102
    await leveling_utils.award_xp(user_id=101, amount=1000)
    await leveling_utils.award_xp(user_id=102, amount=500)

    # 1. Test get_level_leaderboard
    lb = await leveling_utils.get_level_leaderboard(limit=10)
    assert len(lb) == 2
    assert lb[0]["user_id"] == 101

    # 2. Test levels command callback
    import cogs.leveling as leveling_cog
    importlib.reload(leveling_cog)

    bot = SN(get_user=lambda uid: FakeUser(id=uid, display_name=f"User_{uid}"))
    cog = leveling_cog.LevelingCog(bot=bot)

    ctx = FakeCtx(author=FakeUser(id=101, display_name="User_101"))
    await cog.levels.callback(cog, ctx)

    assert len(ctx.sent) == 2  # Embed and View
    embed = ctx.sent[0]
    view = ctx.sent[1]

    assert "Level Leaderboard" in embed.title
    assert "User_101" in embed.description
    assert "#1" in embed.fields[0].value  # User 101 is rank #1

    # 3. Test Dropdown Select Callback
    select = view.children[0]
    select._values = ["10"]
    interaction = FakeInteraction(user=FakeUser(id=101))
    await select.callback(interaction)

    assert len(interaction.edited) == 1
    updated_embed, _ = interaction.edited[0]
    assert "Top 10" in updated_embed.title
    assert "User_101" in updated_embed.description
