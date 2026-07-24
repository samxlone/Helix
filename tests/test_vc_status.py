import pytest
from types import SimpleNamespace as SN
from services.music.player import update_vc_status

class FakeHTTP:
    def __init__(self):
        self.requests = []

    async def request(self, route, json=None, **kwargs):
        self.requests.append((route, json))

class FakeBot:
    def __init__(self):
        self.http = FakeHTTP()

@pytest.mark.asyncio
async def test_update_vc_status_set_and_clear():
    bot = FakeBot()
    channel_id = 999111

    # 1. Update status to playing song
    await update_vc_status(bot, channel_id, "🎵 Playing: Never Gonna Give You Up")

    assert len(bot.http.requests) == 1
    route, payload = bot.http.requests[0]
    assert route.method == "PUT"
    assert route.url == f"https://discord.com/api/v10/channels/{channel_id}/voice-status"
    assert payload == {"status": "🎵 Playing: Never Gonna Give You Up"}

    # 2. Clear status
    await update_vc_status(bot, channel_id, "")

    assert len(bot.http.requests) == 2
    route_clear, payload_clear = bot.http.requests[1]
    assert route_clear.method == "PUT"
    assert payload_clear == {"status": ""}

@pytest.mark.asyncio
async def test_update_vc_status_handles_none_and_exceptions():
    # Calling with None bot or None channel should not raise
    await update_vc_status(None, 123, "test")
    await update_vc_status(FakeBot(), None, "test")

    # Exception during request should be caught gracefully
    class FailingHTTP:
        async def request(self, route, json=None, **kwargs):
            raise RuntimeError("API Error")

    failing_bot = SN(http=FailingHTTP())
    await update_vc_status(failing_bot, 123, "test")
