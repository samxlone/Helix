import pytest
import importlib
from types import SimpleNamespace as SN

class FakeUser:
    def __init__(self, id=1, name="User", bot=False):
        self.id = id
        self.name = name
        self.display_name = name
        self.mention = f"<@{id}>"
        self.bot = bot
        self.guild_permissions = SN(manage_guild=True, administrator=True)

class FakeChannel:
    def __init__(self, id=100):
        self.id = id
        self.mention = f"<#{id}>"
        self.sent = []

    async def send(self, content=None, embed=None, **kwargs):
        if content:
            self.sent.append(content)

    def typing(self):
        class DummyTyping:
            async def __aenter__(self): pass
            async def __aexit__(self, *args): pass
        return DummyTyping()

class FakeMessage:
    def __init__(self, author, channel, content="Hello", guild=None, mentions=None, reference=None):
        self.author = author
        self.channel = channel
        self.content = content
        self.guild = guild or SN(id=1)
        self.mentions = mentions or []
        self.reference = reference
        self.replied = []

    async def reply(self, content, **kwargs):
        self.replied.append(content)
        self.channel.sent.append(content)

@pytest.mark.asyncio
async def test_ai_service_fallback(monkeypatch):
    import utils.ai_service as ai_service

    async def fake_openai(prompt, history=None, system_prompt=None):
        return None  # Simulate failure

    async def fake_gemini(prompt, history=None, system_prompt=None):
        return "Hello from Gemini!"

    monkeypatch.setattr(ai_service, "call_openai", fake_openai)
    monkeypatch.setattr(ai_service, "call_gemini", fake_gemini)

    res = await ai_service.get_ai_response("Hi", provider="openai")
    assert res == "Hello from Gemini!"

@pytest.mark.asyncio
async def test_ai_cog_channel_scoping_and_owner_exemption(monkeypatch):
    import cogs.ai as ai_cog

    config_store = {"ai_channel_id": 999, "ai_provider": "gemini"}

    async def fake_set_guild_config(guild_id, patch):
        config_store.update(patch)

    async def fake_get_guild_config(gid):
        return dict(config_store)

    async def fake_get_ai_response(prompt, history=None, provider=None, system_prompt=None):
        return "AI Response to: " + prompt

    async def fake_text_limit(uid, limit=10):
        return True, 1

    async def fake_image_limit(uid, limit=2):
        return True, 1

    monkeypatch.setattr(ai_cog, "set_guild_config", fake_set_guild_config)
    monkeypatch.setattr(ai_cog, "get_guild_config", fake_get_guild_config)
    monkeypatch.setattr(ai_cog, "get_ai_response", fake_get_ai_response)
    monkeypatch.setattr(ai_cog, "check_and_increment_text_limit", fake_text_limit)
    monkeypatch.setattr(ai_cog, "check_and_increment_image_limit", fake_image_limit)


    async def self_is_owner(user):
        return user.id == 777

    bot = SN(user=FakeUser(id=99, name="HelixBot", bot=True), is_owner=self_is_owner)
    cog = ai_cog.AICog(bot=bot)

    regular_user = FakeUser(id=101, name="RegularMember")
    owner_user = FakeUser(id=777, name="BotOwner")

    ai_channel = FakeChannel(id=999)
    other_channel = FakeChannel(id=555)
    guild = SN(id=1)

    # 1. Regular user in NON-AI channel mentioned bot -> Gets warning/rejected
    msg_other = FakeMessage(author=regular_user, channel=other_channel, content="<@99> Hello", guild=guild, mentions=[bot.user])
    await cog.on_message(msg_other)
    assert len(other_channel.sent) == 1
    assert "restricted to <#999>" in other_channel.sent[0]

    # 2. Regular user in DESIGNATED AI channel -> Gets AI response
    msg_ai = FakeMessage(author=regular_user, channel=ai_channel, content="Tell me a joke", guild=guild)
    await cog.on_message(msg_ai)
    assert len(ai_channel.sent) == 1
    assert "AI Response to: Tell me a joke" in ai_channel.sent[0]

    # 3. Bot Owner in NON-AI channel mentioned bot -> Exemption granted, gets AI response!
    owner_channel = FakeChannel(id=777)
    msg_owner = FakeMessage(author=owner_user, channel=owner_channel, content="<@99> Explain gravity", guild=guild, mentions=[bot.user])
    await cog.on_message(msg_owner)
    assert len(owner_channel.sent) == 1
    assert "AI Response to: Explain gravity" in owner_channel.sent[0]

    # 4. Test commands: setaichannel & setaiprovider & clearchat
    class FakeCtx:
        def __init__(self, author, channel):
            self.author = author
            self.guild = guild
            self.channel = channel
            self.sent = []
        async def send(self, content=None, embed=None, ephemeral=False):
            if content:
                self.sent.append(content)
        async def defer(self): pass

    ctx = FakeCtx(owner_user, ai_channel)
    await cog.setaiprovider.callback(cog, ctx, provider="openai")
    assert config_store["ai_provider"] == "openai"

    await cog.clearchat.callback(cog, ctx)
    assert len(cog._get_history(ai_channel.id)) == 0

@pytest.mark.asyncio
async def test_imagine_command(monkeypatch):
    import cogs.ai as ai_cog

    async def fake_generate_image(prompt):
        return b"fake_png_bytes"

    async def fake_get_guild_config(gid):
        return {"ai_channel_id": 999}

    async def fake_image_limit(uid, limit=2):
        return True, 1

    monkeypatch.setattr(ai_cog, "generate_image_gemini", fake_generate_image)
    monkeypatch.setattr(ai_cog, "get_guild_config", fake_get_guild_config)
    monkeypatch.setattr(ai_cog, "check_and_increment_image_limit", fake_image_limit)


    class FakeCtx:
        def __init__(self, author, channel):
            self.author = author
            self.guild = SN(id=1)
            self.channel = channel
            self.sent = []
        async def send(self, content=None, embed=None, file=None, ephemeral=False):
            if embed:
                self.sent.append(embed)
            if file:
                self.sent.append(file)
        async def defer(self): pass

    bot = SN(user=FakeUser(id=99, name="HelixBot"), is_owner=lambda u: False)
    cog = ai_cog.AICog(bot=bot)

    ctx = FakeCtx(FakeUser(id=101), FakeChannel(id=999))
    await cog.imagine.callback(cog, ctx, prompt="a cute dragon")

    assert len(ctx.sent) == 2  # Embed and File
    embed = ctx.sent[0]
    assert "a cute dragon" in embed.title

