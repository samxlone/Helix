import pytest
from types import SimpleNamespace as SN

class FakePermissions:
    def __init__(self, manage_emojis_and_stickers=True, manage_expressions=True, administrator=False):
        self.manage_emojis_and_stickers = manage_emojis_and_stickers
        self.manage_expressions = manage_expressions
        self.administrator = administrator

class FakeMember:
    def __init__(self, id=1, manage_emojis=True, name="User"):
        self.id = id
        self.display_name = name
        self.mention = f"<@{id}>"
        self.guild_permissions = FakePermissions(manage_emojis_and_stickers=manage_emojis, manage_expressions=manage_emojis)

class FakeGuild:
    def __init__(self, id=55, name="TestGuild"):
        self.id = id
        self.name = name
        self.owner_id = 999
        self.me = FakeMember(id=888, manage_emojis=True, name="Bot")
        self.created_emojis = []
        self.created_stickers = []

    async def create_custom_emoji(self, name, image, reason=None):
        emoji_obj = SN(name=name, id=1001, __str__=lambda self: f"<:{name}:1001>")
        self.created_emojis.append((name, image))
        return emoji_obj

    async def create_sticker(self, name, description, emoji, file, reason=None):
        sticker_obj = SN(name=name, id=2001)
        self.created_stickers.append((name, description, emoji, file))
        return sticker_obj

class FakeChannel:
    def __init__(self, ref_msg=None):
        self.ref_msg = ref_msg

    async def fetch_message(self, msg_id):
        if self.ref_msg and getattr(self.ref_msg, 'id', None) == msg_id:
            return self.ref_msg
        raise ValueError("Message not found")

class FakeMessage:
    def __init__(self, content="", reference=None, stickers=None):
        self.content = content
        self.reference = reference
        self.stickers = stickers or []

class FakeCtx:
    def __init__(self, author, guild, channel=None, message=None):
        self.author = author
        self.guild = guild
        self.channel = channel or FakeChannel()
        self.message = message or FakeMessage()
        self.sent = []
        self.deferred = False

    async def send(self, content=None, ephemeral=False, embed=None, view=None, **kwargs):
        if content:
            self.sent.append(content)
        if embed:
            self.sent.append(embed)
        if view:
            self.sent.append(view)


    async def defer(self, ephemeral=False):
        self.deferred = True

@pytest.mark.asyncio
async def test_steal_emoji_from_argument(monkeypatch):
    import cogs.utility as utility_cog

    async def fake_is_owner(user):
        return user.id == 999

    monkeypatch.setattr(utility_cog.Utility, 'steal', utility_cog.Utility.steal)

    # Mock aiohttp download
    class FakeResponse:
        status = 200
        async def read(self):
            return b"fake_image_bytes"
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass

    class FakeSession:
        def __init__(self, *args, **kwargs):
            pass
        def get(self, url):
            return FakeResponse()
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass


    monkeypatch.setattr("aiohttp.ClientSession", FakeSession)

    async def fake_wait():
        pass

    bot = SN(is_owner=fake_is_owner, wait_until_ready=fake_wait)
    cog = utility_cog.Utility(bot=bot)
    cog.check_reminders.cancel()

    guild = FakeGuild()
    user = FakeMember(id=1, manage_emojis=True)
    ctx = FakeCtx(author=user, guild=guild)

    # Call steal with emoji arg
    await cog.steal.callback(cog, ctx, input_arg="<:cool_cat:123456789> my_cool_cat")

    assert len(guild.created_emojis) == 1
    assert guild.created_emojis[0][0] == "my_cool_cat"
    assert any("Successfully stole emoji" in s for s in ctx.sent)

@pytest.mark.asyncio
async def test_steal_animated_emoji(monkeypatch):
    import cogs.utility as utility_cog

    downloaded_urls = []

    class FakeResponse:
        status = 200
        async def read(self):
            return b"fake_gif_bytes"
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass

    class FakeSession:
        def __init__(self, *args, **kwargs):
            pass
        def get(self, url):
            downloaded_urls.append(url)
            return FakeResponse()
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass

    monkeypatch.setattr("aiohttp.ClientSession", FakeSession)

    bot = SN(is_owner=lambda u: False, wait_until_ready=lambda: None)
    cog = utility_cog.Utility(bot=bot)
    cog.check_reminders.cancel()

    guild = FakeGuild()
    user = FakeMember(id=1, manage_emojis=True)
    ctx = FakeCtx(author=user, guild=guild)

    await cog.steal.callback(cog, ctx, input_arg="<a:dance_cat:999>")

    assert len(guild.created_emojis) == 1
    assert guild.created_emojis[0][0] == "dance_cat"
    assert any(".gif" in url for url in downloaded_urls)


@pytest.mark.asyncio
async def test_steal_sticker_from_replied_message(monkeypatch):
    import cogs.utility as utility_cog

    class FakeResponse:
        status = 200
        async def read(self):
            return b"fake_sticker_bytes"
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass

    class FakeSession:
        def __init__(self, *args, **kwargs):
            pass
        def get(self, url):
            return FakeResponse()
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass


    monkeypatch.setattr("aiohttp.ClientSession", FakeSession)

    async def fake_wait():
        pass

    bot = SN(is_owner=lambda u: False, wait_until_ready=fake_wait)
    cog = utility_cog.Utility(bot=bot)
    cog.check_reminders.cancel()

    guild = FakeGuild()
    user = FakeMember(id=1, manage_emojis=True)

    fake_sticker = SN(id=5555, name="super_sticker", url="https://cdn.discordapp.com/stickers/5555.png", format=None, emoji="🔥")
    ref_msg = SN(id=777, content="", stickers=[fake_sticker])
    channel = FakeChannel(ref_msg=ref_msg)

    msg = FakeMessage(content="", reference=SN(message_id=777))
    ctx = FakeCtx(author=user, guild=guild, channel=channel, message=msg)

    await cog.steal.callback(cog, ctx, input_arg=None)

    # 1. Verify StealStickerView was sent
    view = next(s for s in ctx.sent if type(s).__name__ == "StealStickerView")
    assert view is not None


    # Mock interaction for button clicks
    class FakeInteraction:
        def __init__(self, user):
            self.user = user
            self.edited_content = None
            async def fake_defer():
                pass
            self.response = SN(defer=fake_defer)
            async def fake_send(content=None, **kwargs):
                self.edited_content = content
            self.followup = SN(send=fake_send)

        async def edit_original_response(self, content=None, embed=None, view=None):
            self.edited_content = content

    # Test "Sticker" button click
    interaction_sticker = FakeInteraction(user)
    await view.btn_sticker.callback(interaction_sticker)
    assert len(guild.created_stickers) == 1
    assert guild.created_stickers[0][0] == "super_sticker"
    assert "Successfully stole sticker" in interaction_sticker.edited_content

    # Test "Emoji" button click
    interaction_emoji = FakeInteraction(user)
    await view.btn_emoji.callback(interaction_emoji)
    assert len(guild.created_emojis) == 1
    assert guild.created_emojis[0][0] == "super_sticker"
    assert "Successfully stole sticker" in interaction_emoji.edited_content




@pytest.mark.asyncio
async def test_steal_unauthorized(monkeypatch):
    import cogs.utility as utility_cog

    async def fake_is_owner(user):
        return False

    async def fake_wait():
        pass

    bot = SN(is_owner=fake_is_owner, wait_until_ready=fake_wait)
    cog = utility_cog.Utility(bot=bot)
    cog.check_reminders.cancel()

    guild = FakeGuild()
    unauth_user = FakeMember(id=222, manage_emojis=False)
    ctx = FakeCtx(author=unauth_user, guild=guild)

    await cog.steal.callback(cog, ctx, input_arg="<:cat:123456789>")
    assert any("permission" in s for s in ctx.sent)

