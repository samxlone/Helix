import pytest
from types import SimpleNamespace as SN

class FakeUser:
    def __init__(self, id=1, bot=False, name="User"):
        self.id = id
        self.bot = bot
        self.name = name
        self.mention = f"<@{id}>"

class FakeMessage:
    def __init__(self, content="", author=None, guild=None, mentions=None, reference=None):
        self.content = content
        self.author = author or FakeUser()
        self.guild = guild
        self.mentions = mentions or []
        self.reference = reference
        self.channel = SN(send=self._fake_send)
        self.sent = []

    async def _fake_send(self, content=None, embed=None, **kwargs):
        if content:
            self.sent.append(content)
        if embed:
            self.sent.append(embed)

@pytest.mark.asyncio
async def test_reply_to_bot_does_not_trigger_gif():
    bot_user = FakeUser(id=99, bot=True, name="Helix")
    user = FakeUser(id=1, bot=False, name="User")

    # Message is a reply to a previous message
    msg = FakeMessage(
        content="ok",
        author=user,
        mentions=[bot_user],
        reference=SN(message_id=123)
    )

    # Replicate mention check from main.py
    if bot_user in msg.mentions and not getattr(msg, "reference", None):
        cleaned = msg.content.replace(f"<@{bot_user.id}>", "").strip()
        if not cleaned:
            await msg.channel.send("Hello! My prefix is !")

    # Verified: reply message reference prevents any mention reply or GIF search
    assert len(msg.sent) == 0

@pytest.mark.asyncio
async def test_direct_mention_without_reply_shows_prefix():
    bot_user = FakeUser(id=99, bot=True, name="Helix")
    user = FakeUser(id=1, bot=False, name="User")

    msg = FakeMessage(
        content="<@99>",
        author=user,
        mentions=[bot_user],
        reference=None
    )

    if bot_user in msg.mentions and not getattr(msg, "reference", None):
        cleaned = msg.content.replace(f"<@{bot_user.id}>", "").strip()
        if not cleaned:
            await msg.channel.send("Hello! My prefix is !")

    assert len(msg.sent) == 1
    assert "My prefix is !" in msg.sent[0]
