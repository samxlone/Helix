import pytest
from types import SimpleNamespace as SN

class FakeUser:
    def __init__(self, id=1, voice=None):
        self.id = id
        self.mention = f"<@{id}>"
        self.voice = voice

class FakeVoiceChannel:
    def __init__(self, id=101, name="General"):
        self.id = id
        self.name = name

class FakeVoiceClient:
    def __init__(self, is_connected_val=True):
        self._is_connected = is_connected_val
        self.played_sources = []
        self._is_playing = False

    def is_connected(self):
        return self._is_connected

    def is_playing(self):
        return self._is_playing

    def is_paused(self):
        return False

    def stop(self):
        self._is_playing = False

    def play(self, source, after=None):
        self._is_playing = True
        self.played_sources.append(source)
        if after:
            after(None)

class FakeGuild:
    def __init__(self, id=55, name="TestGuild", voice_client=None):
        self.id = id
        self.name = name
        self.voice_client = voice_client

class FakeCtx:
    def __init__(self, author, guild):
        self.author = author
        self.guild = guild
        self.sent = []
        self.deferred = False

    async def send(self, content=None, ephemeral=False, **kwargs):
        if content:
            self.sent.append(content)

    async def defer(self, ephemeral=False):
        self.deferred = True

@pytest.mark.asyncio
async def test_generate_tts_audio(monkeypatch):
    from utils.tts_service import generate_tts_audio

    class FakeResponse:
        status = 200
        async def read(self):
            return b"fake_tts_mp3_data"
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass

    class FakeSession:
        def get(self, url, headers=None):
            return FakeResponse()
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass

    monkeypatch.setattr("aiohttp.ClientSession", FakeSession)

    data = await generate_tts_audio("Hello world", lang="en")
    assert data == b"fake_tts_mp3_data"

@pytest.mark.asyncio
async def test_tts_command_parsing(monkeypatch):
    import cogs.utility as utility_cog

    class FakeFFmpegPCMAudio:
        def __init__(self, *args, **kwargs):
            pass

    class FakePCMVolumeTransformer:
        def __init__(self, source, volume=1.0):
            self.source = source

    monkeypatch.setattr("discord.FFmpegPCMAudio", FakeFFmpegPCMAudio)
    monkeypatch.setattr("discord.PCMVolumeTransformer", FakePCMVolumeTransformer)

    async def fake_gen_tts(text, lang="en"):
        return b"fake_mp3"

    monkeypatch.setattr("utils.tts_service.generate_tts_audio", fake_gen_tts)

    async def fake_wait():
        pass

    bot = SN(is_owner=lambda u: False, wait_until_ready=fake_wait)
    cog = utility_cog.Utility(bot=bot)
    cog.check_reminders.cancel()

    vc = FakeVoiceClient()
    guild = FakeGuild(voice_client=vc)
    voice_state = SN(channel=FakeVoiceChannel())
    user = FakeUser(id=1, voice=voice_state)
    ctx = FakeCtx(author=user, guild=guild)

    # 1. Test !tts say hello world
    await cog.tts.callback(cog, ctx, words="say hello world")
    assert any("TTS Speaking" in s for s in ctx.sent)
    assert any("hello world" in s for s in ctx.sent)

    # 2. Test !tts say es Hola amigos
    ctx.sent.clear()
    await cog.tts.callback(cog, ctx, words="say es Hola amigos")
    assert any("Language: `es`" in s for s in ctx.sent)
    assert any("Hola amigos" in s for s in ctx.sent)

    # 3. Test auto-detection for Russian text
    ctx.sent.clear()
    await cog.tts.callback(cog, ctx, words="say Привет как дела")
    assert any("Language: `ru`" in s for s in ctx.sent)

    # 4. Test auto-detection for Hinglish text
    ctx.sent.clear()
    await cog.tts.callback(cog, ctx, words="say kya kar rahe ho bhai")
    assert any("hi (Hinglish)" in s for s in ctx.sent)

    # 5. Test user not connected to voice
    ctx_no_vc = FakeCtx(author=FakeUser(id=2, voice=None), guild=guild)
    await cog.tts.callback(cog, ctx_no_vc, words="say hello")
    assert any("must be connected" in s for s in ctx_no_vc.sent)


def test_detect_language_function():
    from utils.tts_service import detect_language

    assert detect_language("Привет как дела") == "ru"
    assert detect_language("नमस्ते क्या हाल है") == "hi"
    assert detect_language("kya kar rahe ho bhai sab thik hai") == "hi"
    assert detect_language("bhai kya chal raha hai aaj") == "hi"
    assert detect_language("Hola amigos como estan") == "es"
    assert detect_language("Bonjour comment allez vous") == "fr"
    assert detect_language("Hallo guten tag") == "de"
    assert detect_language("Hello my friend") == "en"


