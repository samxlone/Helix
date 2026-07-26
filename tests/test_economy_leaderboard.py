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
async def test_economy_leaderboard_flow(tmp_path, monkeypatch):
    db_path = tmp_path / "econ_lb.sqlite"
    monkeypatch.setenv("DATABASE_URL", str(db_path))

    import utils.db as db
    importlib.reload(db)
    await db.init_db()

    import utils.economy as econ_utils
    importlib.reload(econ_utils)

    # Set up sample economy balances
    await econ_utils.add_wallet(101, 5000)
    await econ_utils.add_wallet(102, 10000)
    await econ_utils.add_wallet(103, 2000)

    # 1. Test get_networth_leaderboard
    lb = await econ_utils.get_networth_leaderboard(limit=10)
    assert len(lb) == 3
    assert lb[0]["user_id"] == 102
    assert lb[0]["networth"] == 10000

    # 2. Test get_user_networth_rank
    rank103, nw103 = await econ_utils.get_user_networth_rank(103)
    assert rank103 == 3
    assert nw103 == 2000

    # 3. Test Leaderboard Cog Command
    import cogs.economy as economy_cog
    importlib.reload(economy_cog)

    bot = SN(get_user=lambda uid: FakeUser(id=uid, display_name=f"User_{uid}"))
    cog = economy_cog.EconomyCog(bot=bot)

    ctx = FakeCtx(author=FakeUser(id=101, display_name="User_101"))
    await cog.leaderboard.callback(cog, ctx)

    assert len(ctx.sent) == 2  # Embed and View
    embed = ctx.sent[0]
    view = ctx.sent[1]

    assert "Net Worth Leaderboard" in embed.title
    assert "User_102" in embed.description
    assert "#2" in embed.fields[0].value  # User 101 is rank #2

    # 4. Test Dropdown Select Callback
    select = view.children[0]
    select._values = ["10"]
    interaction = FakeInteraction(user=FakeUser(id=101))
    await select.callback(interaction)


    assert len(interaction.edited) == 1
    updated_embed, _ = interaction.edited[0]
    assert "Top 10" in updated_embed.title
    assert "User_102" in updated_embed.description
