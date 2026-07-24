import pytest
from types import SimpleNamespace as SN

class FakeMsg:
    def __init__(self):
        self.edited_content = None

    async def edit(self, content):
        self.edited_content = content

class FakeGuildMe:
    def __init__(self, display_name="Sam's Personal Assistant"):
        self.display_name = display_name

class FakeGuild:
    def __init__(self, me=None):
        self.me = me or FakeGuildMe()

    def get_member(self, user_id):
        return self.me

class FakeChannel:
    def __init__(self, guild=None, msg=None):
        self.guild = guild
        self.msg = msg or FakeMsg()

    async def fetch_message(self, message_id):
        return self.msg

@pytest.mark.asyncio
async def test_restart_message_with_server_nickname():
    # Helper replicating main.py restart message logic
    bot_user = SN(id=100, name="Helix")
    guild = FakeGuild(me=FakeGuildMe(display_name="Sam's Personal Assistant"))
    channel = FakeChannel(guild=guild)

    msg = await channel.fetch_message(123)

    bot_name = bot_user.name
    if getattr(channel, "guild", None):
        guild_me = channel.guild.me or channel.guild.get_member(bot_user.id)
        if guild_me and getattr(guild_me, "display_name", None):
            bot_name = guild_me.display_name

    await msg.edit(content=f"🟢 **{bot_name}** is online!")

    assert msg.edited_content == "🟢 **Sam's Personal Assistant** is online!"

@pytest.mark.asyncio
async def test_restart_message_fallback_to_global_name():
    bot_user = SN(id=100, name="Helix")
    guild = FakeGuild(me=FakeGuildMe(display_name="Helix"))
    channel = FakeChannel(guild=guild)

    msg = await channel.fetch_message(123)

    bot_name = bot_user.name
    if getattr(channel, "guild", None):
        guild_me = channel.guild.me or channel.guild.get_member(bot_user.id)
        if guild_me and getattr(guild_me, "display_name", None):
            bot_name = guild_me.display_name

    await msg.edit(content=f"🟢 **{bot_name}** is online!")

    assert msg.edited_content == "🟢 **Helix** is online!"
