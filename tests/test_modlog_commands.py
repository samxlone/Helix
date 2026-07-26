import asyncio
import types
import pytest

from types import SimpleNamespace

import cogs.moderation as mod_cog


class FakeResponse:
    def __init__(self):
        self.messages = []

    async def send(self, *args, **kwargs):
        self.messages.append((args, kwargs))

    # discord.Interaction.response.send_message maps to .send
    async def send_message(self, *args, **kwargs):
        await self.send(*args, **kwargs)


class FakeChannel:
    def __init__(self, id=1234):
        self.id = id
        self.mention = f"<#{id}>"
        self.sent = []

    async def send(self, *args, **kwargs):
        self.sent.append((args, kwargs))


class FakeUser:
    def __init__(self, id=111, manage_guild=True):
        self.id = id
        self.mention = f"<@{id}>"
        self.display_avatar = None
        self.guild_permissions = SimpleNamespace(
            manage_guild=manage_guild,
            administrator=manage_guild,
            view_audit_log=manage_guild,
            manage_messages=manage_guild,
            kick_members=manage_guild,
            ban_members=manage_guild,
            mute_members=manage_guild
        )


class FakeGuild:
    def __init__(self, id=9999, name="TestGuild", channel=None):
        self.id = id
        self.name = name
        self._channel = channel

    def get_channel(self, cid):
        if self._channel and self._channel.id == int(cid):
            return self._channel
        return None

    def get_member(self, uid):
        return None


class FakeInteraction:
    def __init__(self, user, guild, channel):
        self.user = user
        self.author = user
        self.guild = guild
        self.channel = channel
        self.response = FakeResponse()
        self.followup = FakeResponse()

    async def send(self, *args, **kwargs):
        await self.response.send(*args, **kwargs)

    async def defer(self, *args, **kwargs):
        pass


@pytest.mark.asyncio
async def test_modlog_set_channel(monkeypatch):
    fake_channel = FakeChannel(id=5555)
    user = FakeUser(id=111, manage_guild=True)
    guild = FakeGuild(id=42, name="G", channel=fake_channel)
    interaction = FakeInteraction(user, guild, fake_channel)

    recorded = {}

    async def fake_set_guild_config(guild_id, patch):
        recorded['called'] = (guild_id, patch)

    # patch the symbol in the moderation module
    monkeypatch.setattr(mod_cog, 'set_guild_config', fake_set_guild_config)

    cog = mod_cog.Moderation(bot=SimpleNamespace(get_channel=lambda x: fake_channel))

    # call set-channel with provided channel
    cmd = cog.modlog_set_channel
    if hasattr(cmd, 'callback'):
        await cmd.callback(cog, interaction, channel=fake_channel)
    else:
        await cmd(interaction, channel=fake_channel)

    assert 'called' in recorded
    assert recorded['called'][0] == 42
    assert recorded['called'][1] == {'mod_log_channel': 5555}
    # ensure a confirmation embed was attempted to be sent to channel
    assert len(fake_channel.sent) == 1


@pytest.mark.asyncio
async def test_modlog_clear_channel(monkeypatch):
    fake_channel = FakeChannel(id=5555)
    user = FakeUser(id=111, manage_guild=True)
    guild = FakeGuild(id=42, name="G", channel=fake_channel)
    interaction = FakeInteraction(user, guild, fake_channel)

    recorded = {}

    async def fake_set_guild_config(guild_id, patch):
        recorded['called'] = (guild_id, patch)

    monkeypatch.setattr(mod_cog, 'set_guild_config', fake_set_guild_config)

    cog = mod_cog.Moderation(bot=SimpleNamespace(get_channel=lambda x: fake_channel))

    cmd = cog.modlog_clear_channel
    if hasattr(cmd, 'callback'):
        await cmd.callback(cog, interaction)
    else:
        await cmd(interaction)

    assert 'called' in recorded
    assert recorded['called'][0] == 42
    assert recorded['called'][1] == {'mod_log_channel': None}


@pytest.mark.asyncio
async def test_modlog_show_current(monkeypatch):
    fake_channel = FakeChannel(id=5555)
    user = FakeUser(id=111, manage_guild=True)
    guild = FakeGuild(id=42, name="G", channel=fake_channel)
    interaction = FakeInteraction(user, guild, fake_channel)

    async def fake_get_guild_config(gid):
        return {"mod_log_channel": str(5555)}

    monkeypatch.setattr(mod_cog, 'get_guild_config', fake_get_guild_config)

    cog = mod_cog.Moderation(bot=SimpleNamespace(get_channel=lambda x: fake_channel))

    # call without channel to query current setting
    cmd = cog.modlog_set_channel
    if hasattr(cmd, 'callback'):
        await cmd.callback(cog, interaction, channel=None)
    else:
        await cmd(interaction, channel=None)

    # response sends ephemeral message with mention
    assert len(interaction.response.messages) == 1
    args, kwargs = interaction.response.messages[0]
    assert "Current mod-log channel" in args[0]
    assert "<#5555>" in args[0]


def test_parse_duration():
    from cogs.moderation import parse_duration
    assert parse_duration("5s") == 5
    assert parse_duration("10m") == 600
    assert parse_duration("2h") == 7200
    assert parse_duration("1d") == 86400
    assert parse_duration("30") == 1800  # default to minutes
    assert parse_duration("invalid") is None
    assert parse_duration("") is None


@pytest.mark.asyncio
async def test_vcmute_and_history(tmp_path, monkeypatch):
    db_path = tmp_path / "mod_cmd_v2.sqlite"
    monkeypatch.setenv("DATABASE_URL", str(db_path))

    import utils.db as db
    importlib = pytest.importorskip("importlib")
    importlib.reload(db)
    await db.init_db()

    from cogs.moderation import Moderation
    from utils.modlog import log_action

    bot = SimpleNamespace(user=SimpleNamespace(name="Helix", id=999), get_channel=lambda x: None)
    cog = Moderation(bot=bot)

    await log_action(guild_id=42, moderator_id=111, target_id=222, action="warn", reason="spamming")
    await log_action(guild_id=42, moderator_id=111, target_id=222, action="vcmute", reason="loud music")

    fake_user = FakeUser(id=222)
    fake_moderator = FakeUser(id=111, manage_guild=True)
    fake_channel = FakeChannel(id=5555)
    guild = FakeGuild(id=42, name="G", channel=fake_channel)

    async def fake_fetch_user(uid):
        return FakeUser(id=uid)
    bot.fetch_user = fake_fetch_user

    interaction = FakeInteraction(fake_moderator, guild, fake_channel)
    cmd = cog.history
    await cmd.callback(cog, interaction, target=fake_user)

    assert len(interaction.response.messages) == 1
    args, kwargs = interaction.response.messages[0]
    embed = kwargs.get("embed")
    assert embed is not None
    assert "Moderation History" in embed.title
    assert "WARN" in embed.description
    assert "VCMUTE" in embed.description


@pytest.mark.asyncio
async def test_partial_role_matching():
    guild = SimpleNamespace(
        id=1,
        roles=[
            SimpleNamespace(id=10, name="Administrator"),
            SimpleNamespace(id=20, name="Gen Z Baddies"),
        ]
    )
    guild.get_role = lambda rid: next((r for r in guild.roles if r.id == rid), None)

    from cogs.moderation import Moderation
    role, err = Moderation._find_role_by_name(guild, "admin")
    assert err is None
    assert role.name == "Administrator"

    role2, err2 = Moderation._find_role_by_name(guild, "gen z baddie")
    assert err2 is None
    assert role2.name == "Gen Z Baddies"

