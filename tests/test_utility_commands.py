import importlib
import pytest
from types import SimpleNamespace
from datetime import datetime, timezone, timedelta


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


@pytest.mark.asyncio
async def test_avatar_and_serveravatar_commands():
    from cogs.utility import Utility
    bot = SimpleNamespace(wait_until_ready=fake_wait)
    cog = Utility(bot=bot)

    global_avatar = SimpleNamespace(with_size=lambda size: SimpleNamespace(url="https://example.com/global_avatar.png"))
    guild_avatar = SimpleNamespace(with_size=lambda size: SimpleNamespace(url="https://example.com/server_avatar.png"))
    
    user = FakeUser(id=1, display_name="Alice")
    user.avatar = global_avatar
    user.display_avatar = global_avatar
    user.guild_avatar = guild_avatar

    guild = SimpleNamespace(
        name="Test Guild",
        icon=SimpleNamespace(with_size=lambda size: SimpleNamespace(url="https://example.com/server_icon.png"))
    )

    ctx = FakeContext(author=user)
    ctx.guild = guild

    # Test global avatar
    await cog.avatar.callback(cog, ctx, user=user)
    assert len(ctx.messages_sent) == 1
    embed = ctx.messages_sent[0][1]['embed']
    assert "Global Avatar" in embed.title
    assert embed.image.url == "https://example.com/global_avatar.png"

    # Test serveravatar for user
    ctx.messages_sent.clear()
    await cog.serveravatar.callback(cog, ctx, member=user)
    assert len(ctx.messages_sent) == 1
    embed = ctx.messages_sent[0][1]['embed']
    assert "Server Avatar" in embed.title
    assert embed.image.url == "https://example.com/server_avatar.png"

    # Test serveravatar for server icon (no user passed)
    ctx.messages_sent.clear()
    await cog.serveravatar.callback(cog, ctx, member=None)
    assert len(ctx.messages_sent) == 1
    embed = ctx.messages_sent[0][1]['embed']
    assert "Server Icon" in embed.title
    assert embed.image.url == "https://example.com/server_icon.png"
    cog.cog_unload()


@pytest.mark.asyncio
async def test_banner_and_serverbanner_commands(monkeypatch):
    from cogs.utility import Utility
    bot = SimpleNamespace(wait_until_ready=fake_wait)
    
    fake_banner = SimpleNamespace(with_size=lambda size: SimpleNamespace(url="https://example.com/user_banner.png"))
    fake_profile = SimpleNamespace(display_name="Alice", banner=fake_banner, accent_color=None)
    
    async def fake_fetch_user(user_id):
        return fake_profile

    bot.fetch_user = fake_fetch_user
    cog = Utility(bot=bot)

    user = FakeUser(id=1, display_name="Alice")
    guild = SimpleNamespace(
        name="Test Guild",
        banner=SimpleNamespace(with_size=lambda size: SimpleNamespace(url="https://example.com/server_banner.png"))
    )

    ctx = FakeContext(author=user)
    ctx.guild = guild

    # Test user banner
    await cog.banner.callback(cog, ctx, user=user)
    assert len(ctx.messages_sent) == 1
    embed = ctx.messages_sent[0][1]['embed']
    assert "Banner" in embed.title
    assert embed.image.url == "https://example.com/user_banner.png"

    # Test serverbanner for server itself
    ctx.messages_sent.clear()
    await cog.serverbanner.callback(cog, ctx, member=None)
    assert len(ctx.messages_sent) == 1
    embed = ctx.messages_sent[0][1]['embed']
    assert "Server Banner" in embed.title
    assert embed.image.url == "https://example.com/server_banner.png"
    cog.cog_unload()


@pytest.mark.asyncio
async def test_server_and_global_afk(tmp_path, monkeypatch):
    # Setup test DB
    db_path = tmp_path / "afk_scope.sqlite"
    monkeypatch.setenv("DATABASE_URL", str(db_path))

    import utils.db as db
    importlib.reload(db)
    await db.init_db()

    from cogs.utility import Utility
    from utils.db import get_connection

    bot = SimpleNamespace(wait_until_ready=fake_wait)
    cog = Utility(bot=bot)

    user = FakeUser(id=10, display_name="Dave")
    async def mock_edit(*args, **kwargs):
        pass
    user.edit = mock_edit
    user.nick = None

    guild1 = SimpleNamespace(id=100, name="Guild Alpha")
    guild2 = SimpleNamespace(id=200, name="Guild Beta")

    # Set Server AFK in Guild Alpha
    ctx1 = FakeContext(author=user)
    ctx1.guild = guild1
    await cog.safk.callback(cog, ctx1, message="In a meeting")
    assert "Server AFK" in ctx1.messages_sent[0][0][0]

    # Verify stored in DB with guild_id=100
    async with get_connection() as conn:
        cur = await conn.execute("SELECT scope, guild_id FROM afk WHERE user_id = 10")
        row = await cur.fetchone()
        assert row['scope'] == "server"
        assert row['guild_id'] == 100

    # Set timestamp in past so total_seconds() > 3
    past_iso = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
    async with get_connection() as conn:
        await conn.execute("UPDATE afk SET since = ? WHERE user_id = 10", (past_iso,))
        await conn.commit()

    # User speaks in Guild Beta -> Server AFK in Guild Alpha should NOT be removed
    msg_beta = SimpleNamespace(
        author=user,
        guild=guild2,
        mentions=[],
        channel=FakeResponse()
    )
    await cog.on_message(msg_beta)
    assert len(msg_beta.channel.messages) == 0

    # User speaks in Guild Alpha -> Server AFK in Guild Alpha IS removed
    msg_alpha = SimpleNamespace(
        author=user,
        guild=guild1,
        mentions=[],
        channel=FakeResponse()
    )
    await cog.on_message(msg_alpha)
    assert len(msg_alpha.channel.messages) == 1
    assert "Server AFK" in msg_alpha.channel.messages[0][0][0]

    # Set Global AFK
    ctx1.messages_sent.clear()
    await cog.gafk.callback(cog, ctx1, message="Sleeping")
    assert "Global AFK" in ctx1.messages_sent[0][0][0]

    async with get_connection() as conn:
        await conn.execute("UPDATE afk SET since = ? WHERE user_id = 10", (past_iso,))
        await conn.commit()

    # User speaks in any guild (Guild Beta) -> Global AFK IS removed
    msg_beta.channel.messages.clear()
    await cog.on_message(msg_beta)
    assert len(msg_beta.channel.messages) == 1
    assert "Global AFK" in msg_beta.channel.messages[0][0][0]
    cog.cog_unload()


