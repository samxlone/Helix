import pytest
from types import SimpleNamespace as SN

class FakeCtx:
    def __init__(self):
        self.sent = []
        self.deferred = False

    async def send(self, content=None, embed=None, **kwargs):
        if content:
            self.sent.append(content)
        if embed:
            self.sent.append(embed)

    async def defer(self, ephemeral=False):
        self.deferred = True

@pytest.mark.asyncio
async def test_gif_command_sends_plain_url(monkeypatch):
    import cogs.utility as utility_cog

    async def fake_search_gifs(query):
        return ["https://media.giphy.com/media/fake/giphy.gif"]

    monkeypatch.setattr("utils.gif_service.search_gifs", fake_search_gifs)

    async def fake_wait():
        pass

    bot = SN(is_owner=lambda u: False, wait_until_ready=fake_wait)
    cog = utility_cog.Utility(bot=bot)
    cog.check_reminders.cancel()

    ctx = FakeCtx()
    await cog.gif.callback(cog, ctx, query="hello")

    assert len(ctx.sent) == 1
    assert isinstance(ctx.sent[0], str)
    assert ctx.sent[0] == "https://media.giphy.com/media/fake/giphy.gif"
