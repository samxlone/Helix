import pytest
from types import SimpleNamespace
from types import SimpleNamespace as SN
import importlib

class FakeResponse:
    def __init__(self):
        self.messages = []
    async def send(self, *args, **kwargs):
        self.messages.append((args, kwargs))
    async def send_message(self, *args, **kwargs):
        await self.send(*args, **kwargs)

class FakeChannel:
    def __init__(self, id=123):
        self.id = id
        self.mention = f"<#{id}>"
        self.sent = []
    async def send(self, *args, **kwargs):
        self.sent.append((args, kwargs))

class FakeUser:
    def __init__(self, id=1, manage_guild=True):
        self.id = id
        self.mention = f"<@{id}>"
        self.guild_permissions = SN(manage_guild=manage_guild, administrator=manage_guild)

class FakeGuild:
    def __init__(self, id=42, name="G", channel=None, owner_id=111):
        self.id = id
        self.name = name
        self._channel = channel
        self.owner_id = owner_id
    def get_role(self, rid):
        return None


class FakeInteraction:
    def __init__(self, user, guild):
        self.user = user
        self.guild = guild
        self.response = FakeResponse()

@pytest.mark.asyncio
async def test_set_and_clear_reward(monkeypatch):
    # monkeypatch set_guild_config so we can assert it was called
    import cogs.leveling as leveling_cog

    recorded = {}

    async def fake_set_guild_config(guild_id, patch):
        recorded['called'] = (guild_id, patch)

    async def fake_get_guild_config(gid):
        return {"level_rewards": {"5": 999}}

    monkeypatch.setattr(leveling_cog, 'set_guild_config', fake_set_guild_config)
    monkeypatch.setattr(leveling_cog, 'get_guild_config', fake_get_guild_config)

    bot = SN()
    cog = leveling_cog.LevelingCog(bot=bot)

    user = FakeUser(id=111)
    guild = FakeGuild(id=55, name="TestGuild")
    interaction = FakeInteraction(user, guild)

    # call set_reward
    cmd = cog.set_reward
    if hasattr(cmd, 'callback'):
        await cmd.callback(cog, interaction, level=5, role=SN(id=999, name='R'))
    else:
        await cmd(interaction, 5, SN(id=999, name='R'))

    assert 'called' in recorded
    assert recorded['called'][0] == 55
    assert recorded['called'][1] == {'level_rewards': {'5': 999}}

    # test clear_reward path (monkeypatch set_guild_config used again)
    recorded.clear()
    # Ensure get_guild_config returns mapping that contains the key
    async def fake_get_guild_config2(gid):
        return {'level_rewards': {'5': 999}}
    monkeypatch.setattr(leveling_cog, 'get_guild_config', fake_get_guild_config2)

    cmd2 = cog.clear_reward
    if hasattr(cmd2, 'callback'):
        await cmd2.callback(cog, interaction, level=5)
    else:
        await cmd2(interaction, 5)

    # clear should have called set_guild_config with updated mapping
    assert 'called' in recorded
    assert recorded['called'][0] == 55
    # mapping may be empty dict
    assert isinstance(recorded['called'][1].get('level_rewards'), dict)


@pytest.mark.asyncio
async def test_toggle_xp(monkeypatch):
    import cogs.leveling as leveling_cog

    recorded = {}
    config_store = {"xp_enabled": True}

    async def fake_set_guild_config(guild_id, patch):
        recorded['called'] = (guild_id, patch)
        config_store.update(patch)

    async def fake_get_guild_config(gid):
        return dict(config_store)

    award_called = []

    async def fake_award_xp(user_id, amount):
        award_called.append((user_id, amount))
        return False, 0, 0

    monkeypatch.setattr(leveling_cog, 'set_guild_config', fake_set_guild_config)
    monkeypatch.setattr(leveling_cog, 'get_guild_config', fake_get_guild_config)
    monkeypatch.setattr(leveling_cog, 'award_xp', fake_award_xp)

    async def self_is_owner(u):
        return True

    bot = SN(is_owner=self_is_owner)
    cog = leveling_cog.LevelingCog(bot=bot)


    user = FakeUser(id=111)
    guild = FakeGuild(id=55, name="TestGuild")
    interaction = FakeInteraction(user, guild)

    # Test toggling via app command group (toggle_xp_group)
    cmd = cog.toggle_xp_group
    if hasattr(cmd, 'callback'):
        await cmd.callback(cog, interaction, enabled=False)
    else:
        await cmd(interaction, False)

    assert recorded['called'] == (55, {"xp_enabled": False})
    assert config_store["xp_enabled"] is False

    # Test on_message when disabled
    msg_channel = FakeChannel()
    msg = SN(author=SN(bot=False, id=999, mention="<@999>"), guild=guild, channel=msg_channel)
    await cog.on_message(msg)

    # award_xp should NOT have been called because xp_enabled is False
    assert len(award_called) == 0

    # Test addxp command when disabled
    ctx_sent = []
    class FakeCtx:
        def __init__(self):
            self.author = user
            self.guild = guild
        async def send(self, content, ephemeral=False):
            ctx_sent.append(content)

    ctx = FakeCtx()
    cmd_addxp = cog.addxp
    member = SN(id=222, mention="<@222>")
    if hasattr(cmd_addxp, 'callback'):
        await cmd_addxp.callback(cog, ctx, member, 50)
    else:
        await cmd_addxp(ctx, member, 50)

    assert len(award_called) == 0
    assert any("disabled" in s for s in ctx_sent)

    # Test toggling back on via hybrid command (togglexp)
    cmd_toggle = cog.togglexp
    ctx_sent.clear()
    if hasattr(cmd_toggle, 'callback'):
        await cmd_toggle.callback(cog, ctx, enabled=True)
    else:
        await cmd_toggle(ctx, enabled=True)

    assert config_store["xp_enabled"] is True
    assert any("enabled" in s for s in ctx_sent)

