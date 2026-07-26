import importlib
import pytest
from types import SimpleNamespace
from datetime import datetime, timezone

class FakeResponse:
    def __init__(self):
        self.messages = []

    async def send(self, *args, **kwargs):
        self.messages.append((args, kwargs))

    async def send_message(self, *args, **kwargs):
        await self.send(*args, **kwargs)


class FakeUser:
    def __init__(self, id=1, display_name="TestUser"):
        self.id = id
        self.display_name = display_name
        self.mention = f"<@{id}>"


class FakeContext:
    def __init__(self, author, channel_id=10):
        self.author = author
        self.channel = SimpleNamespace(id=channel_id)
        self.messages_sent = []

    async def send(self, *args, **kwargs):
        self.messages_sent.append((args, kwargs))
        # Return a fake message object
        return SimpleNamespace(add_reaction=lambda emoji: None)


async def fake_wait():
    pass


@pytest.mark.asyncio
async def test_calculator(tmp_path, monkeypatch):
    # Setup test DB
    db_path = tmp_path / "util_cmd.sqlite"
    monkeypatch.setenv("DATABASE_URL", str(db_path))

    import utils.db as db
    importlib.reload(db)
    await db.init_db()

    from cogs.utility import Utility
    bot = SimpleNamespace(wait_until_ready=fake_wait)
    cog = Utility(bot=bot)

    user = FakeUser(id=1)
    ctx = FakeContext(author=user)

    # Test basic calculation
    await cog.calculator.callback(cog, ctx, expression="2 + 3 * 4")
    assert len(ctx.messages_sent) == 1
    embed = ctx.messages_sent[0][1]['embed']
    assert embed.fields[1].value == "`14`"

    # Test division by zero
    ctx.messages_sent.clear()
    await cog.calculator.callback(cog, ctx, expression="5 / 0")
    assert "Division by zero" in ctx.messages_sent[0][0][0]

    # Test power check
    ctx.messages_sent.clear()
    await cog.calculator.callback(cog, ctx, expression="2 ** 1000")
    assert "Invalid expression" in ctx.messages_sent[0][0][0]
    cog.cog_unload()


@pytest.mark.asyncio
async def test_parse_duration():
    from cogs.utility import Utility
    bot = SimpleNamespace(wait_until_ready=fake_wait)
    cog = Utility(bot=bot)

    assert cog.parse_duration("10m") == 600
    assert cog.parse_duration("1h30m") == 5400
    assert cog.parse_duration("2d12h") == 216000
    assert cog.parse_duration("45s") == 45
    assert cog.parse_duration("invalid") == 0
    cog.cog_unload()


@pytest.mark.asyncio
async def test_afk_and_reminders(tmp_path, monkeypatch):
    # Setup test DB
    db_path = tmp_path / "util_cmd.sqlite"
    monkeypatch.setenv("DATABASE_URL", str(db_path))

    import utils.db as db
    importlib.reload(db)
    await db.init_db()

    from cogs.utility import Utility
    from utils.db import get_connection

    bot = SimpleNamespace(wait_until_ready=fake_wait)
    cog = Utility(bot=bot)

    # Test afk command
    user = FakeUser(id=1, display_name="Bob")
    # Add a mock edit for nick changes
    async def mock_edit(*args, **kwargs):
        pass
    user.edit = mock_edit
    
    ctx = FakeContext(author=user)
    await cog.afk.callback(cog, ctx, message="Gone to lunch")

    # Check afk record in db
    async with get_connection() as conn:
        cur = await conn.execute("SELECT message FROM afk WHERE user_id = 1")
        row = await cur.fetchone()
        assert row is not None
        assert row['message'] == "Gone to lunch"

    # Test reminder creation
    await cog.remind.callback(cog, ctx, duration="1m", message="Check oven")
    async with get_connection() as conn:
        cur = await conn.execute("SELECT message FROM reminders WHERE user_id = 1")
        row = await cur.fetchone()
        assert row is not None
        assert row['message'] == "Check oven"
    cog.cog_unload()


@pytest.mark.asyncio
async def test_serverinfo_command():
    from cogs.utility import Utility
    bot = SimpleNamespace(wait_until_ready=fake_wait)
    cog = Utility(bot=bot)

    guild = SimpleNamespace(
        id=1075480726151110656,
        name="The NXT ™",
        description="The Biggest Indian Community",
        member_count=100,
        members=[SimpleNamespace(bot=False), SimpleNamespace(bot=True)],
        categories=[1],
        text_channels=[1, 2],
        voice_channels=[3],
        channels=[1, 2, 3],
        created_at=datetime.now(timezone.utc),
        owner=SimpleNamespace(mention="<@123>", id=123),
        owner_id=123,
        icon=SimpleNamespace(url="https://example.com/icon.png"),
        banner=SimpleNamespace(url="https://example.com/banner.png"),
        premium_tier=3,
        premium_subscription_count=144,
        premium_subscriber_role=SimpleNamespace(mention="<@&999>"),
        verification_level="HIGH",
        explicit_content_filter="ALL_MEMBERS",
        roles=[SimpleNamespace(id=1, mention="@everyone"), SimpleNamespace(id=2, mention="<@&11>")],
        default_role=SimpleNamespace(id=1, mention="@everyone")
    )

    ctx = FakeContext(author=FakeUser(id=1))
    ctx.guild = guild

    await cog.serverinfo.callback(cog, ctx)
    assert len(ctx.messages_sent) == 1
    embed = ctx.messages_sent[0][1]['embed']
    assert "Server Information" in embed.title
    assert embed.image.url == "https://example.com/banner.png"
    assert embed.thumbnail.url == "https://example.com/icon.png"
    cog.cog_unload()
