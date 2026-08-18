import pytest
from types import SimpleNamespace as SN
import discord
from cogs.games import Games, BlackjackView, TicTacToeView, ConnectFourView, MinesView, HighLowView, TriviaView, TRIVIA_QUESTIONS
from utils.db import init_db
from utils.economy import add_wallet, get_balance


class FakeCtx:
    def __init__(self, author=None, guild=None):
        self.author = author or SN(id=1001, mention="<@1001>", bot=False)
        self.guild = guild or SN(id=10, name="TestGuild")
        self.sent = []

    async def send(self, content=None, embed=None, view=None, ephemeral=False, **kwargs):
        payload = {"content": content, "embed": embed, "view": view, "ephemeral": ephemeral}
        self.sent.append(payload)
        return payload

class FakeInteraction:
    def __init__(self, user):
        self.user = user
        self.response = FakeResponse()
        self.sent = []

class FakeResponse:
    def __init__(self):
        self.is_done = False
        self.messages = []

    async def send_message(self, content=None, embed=None, view=None, ephemeral=False, **kwargs):
        self.is_done = True
        self.messages.append({"content": content, "embed": embed, "view": view, "ephemeral": ephemeral})

    async def edit_message(self, content=None, embed=None, view=None, **kwargs):
        self.is_done = True
        self.messages.append({"content": content, "embed": embed, "view": view})

    async def defer(self, **kwargs):
        self.is_done = True


@pytest.mark.asyncio
async def test_coinflip_and_slots(monkeypatch):
    await init_db()
    bot = SN()
    cog = Games(bot)
    user_id = 2001
    await add_wallet(user_id, 1000)

    ctx = FakeCtx(author=SN(id=user_id, mention="<@2001>", bot=False))
    
    # 1. Coinflip
    await cog.slash_coinflip.callback(cog, ctx, choice="heads", bet=100)
    assert len(ctx.sent) >= 1
    assert ctx.sent[0]["embed"] is not None

    # 2. Slots
    await cog.slash_slots.callback(cog, ctx, bet=50)
    assert len(ctx.sent) >= 2
    assert ctx.sent[1]["embed"] is not None


@pytest.mark.asyncio
async def test_blackjack_and_highlow(monkeypatch):
    await init_db()
    bot = SN()
    cog = Games(bot)
    user_id = 2002
    await add_wallet(user_id, 2000)

    ctx = FakeCtx(author=SN(id=user_id, mention="<@2002>", bot=False))
    
    # Blackjack
    await cog.slash_blackjack.callback(cog, ctx, bet=100)
    assert len(ctx.sent) >= 1
    view = ctx.sent[0]["view"] or None
    assert ctx.sent[0]["embed"] is not None

    # HighLow
    await cog.slash_highlow.callback(cog, ctx, bet=100)
    assert len(ctx.sent) >= 2
    hl_view = ctx.sent[1]["view"]
    assert isinstance(hl_view, HighLowView)
    assert hl_view.bet == 100


@pytest.mark.asyncio
async def test_tictactoe_and_connect4(monkeypatch):
    await init_db()
    bot = SN()
    cog = Games(bot)
    user_id = 2003
    await add_wallet(user_id, 1000)

    ctx = FakeCtx(author=SN(id=user_id, mention="<@2003>", bot=False))

    # TicTacToe vs AI
    await cog.slash_tictactoe.callback(cog, ctx, opponent=None, bet=50)
    assert len(ctx.sent) >= 1
    ttt_view = ctx.sent[0]["view"]
    assert isinstance(ttt_view, TicTacToeView)
    assert len(ttt_view.children) == 9

    # ConnectFour vs AI
    await cog.slash_connect4.callback(cog, ctx, opponent=None, bet=50)
    assert len(ctx.sent) >= 2
    c4_view = ctx.sent[1]["view"]
    assert isinstance(c4_view, ConnectFourView)
    assert len(c4_view.children) == 7


@pytest.mark.asyncio
async def test_mines_and_roulette_and_rps(monkeypatch):
    await init_db()
    bot = SN()
    cog = Games(bot)
    user_id = 2004
    await add_wallet(user_id, 5000)

    ctx = FakeCtx(author=SN(id=user_id, mention="<@2004>", bot=False))

    # Mines
    await cog.slash_mines.callback(cog, ctx, bet=100, mines_count=3)
    assert len(ctx.sent) >= 1
    mines_view = ctx.sent[0]["view"]
    assert isinstance(mines_view, MinesView)
    assert len(mines_view.mines) == 3
    assert len(mines_view.children) == 21  # 20 tiles + 1 cashout

    # Roulette
    await cog.slash_roulette.callback(cog, ctx, bet=100, space="red")
    assert len(ctx.sent) >= 2
    assert ctx.sent[1]["embed"] is not None

    # RPS
    await cog.slash_rps.callback(cog, ctx, choice="rock", bet=50)
    assert len(ctx.sent) >= 3
    assert ctx.sent[2]["embed"] is not None


@pytest.mark.asyncio
async def test_trivia(monkeypatch):
    await init_db()
    bot = SN()
    cog = Games(bot)
    user_id = 2005
    await add_wallet(user_id, 1000)

    ctx = FakeCtx(author=SN(id=user_id, mention="<@2005>", bot=False))
    await cog.slash_trivia.callback(cog, ctx, bet=50)
    assert len(ctx.sent) >= 1
    t_view = ctx.sent[0]["view"]
    assert isinstance(t_view, TriviaView)
    assert len(t_view.children) == 4

