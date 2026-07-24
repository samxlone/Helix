import importlib
import pytest
from types import SimpleNamespace

class FakeResponse:
    def __init__(self):
        self.messages = []

    async def send(self, *args, **kwargs):
        self.messages.append((args, kwargs))

    async def send_message(self, *args, **kwargs):
        await self.send(*args, **kwargs)


class FakeUser:
    def __init__(self, id=1):
        self.id = id
        self.mention = f"<@{id}>"
        self.guild_permissions = SimpleNamespace(kick_members=False, manage_guild=False, administrator=False)


class FakeMember(FakeUser):
    pass


class FakeInteraction:
    def __init__(self, user, guild=None, channel=None):
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
async def test_pay_and_bank_commands(tmp_path, monkeypatch):
    db_path = tmp_path / "eco_cmd.sqlite"
    monkeypatch.setenv("DATABASE_URL", str(db_path))

    import utils.db as db
    importlib.reload(db)
    await db.init_db()

    from cogs.economy import EconomyCog
    from utils.economy import add_wallet, get_balance

    # seed balances
    await add_wallet(1, 1000)
    await add_wallet(2, 100)

    bot = SimpleNamespace(get_channel=lambda x: None)
    cog = EconomyCog(bot=bot)

    # test pay: user 1 pays 200 to user 2
    user1 = FakeUser(id=1)
    member2 = FakeMember(id=2)
    interaction = FakeInteraction(user1)
    cmd = cog.pay
    if hasattr(cmd, 'callback'):
        await cmd.callback(cog, interaction, target=member2, amount=200)
    else:
        await cmd(interaction, member2, 200)

    # check balances
    w1, _ = await get_balance(1)
    w2, _ = await get_balance(2)
    assert w1 == 800
    assert w2 == 300

    # test deposit/withdraw
    cmd_deposit = cog.deposit
    if hasattr(cmd_deposit, 'callback'):
        await cmd_deposit.callback(cog, interaction, amount=300)
    else:
        await cmd_deposit(interaction, 300)

    w1, b1 = await get_balance(1)
    assert b1 == 300

    cmd_withdraw = cog.withdraw
    if hasattr(cmd_withdraw, 'callback'):
        await cmd_withdraw.callback(cog, interaction, amount=100)
    else:
        await cmd_withdraw(interaction, 100)

    w1, b1 = await get_balance(1)
    assert w1 == 600 and b1 == 200

    # test work (should succeed)
    cmd_work = cog.work
    if hasattr(cmd_work, 'callback'):
        await cmd_work.callback(cog, interaction)
    else:
        await cmd_work(interaction)

    # ensure wallet increased
    w1_after, _ = await get_balance(1)
    assert w1_after >= w1

    # test deposit all
    await cmd_deposit.callback(cog, interaction, amount="all")
    w1_after_dep, b1_after_dep = await get_balance(1)
    assert w1_after_dep == 0
    assert b1_after_dep == w1_after + 200

    # test withdraw all
    await cmd_withdraw.callback(cog, interaction, amount="all")
    w1_final, b1_final = await get_balance(1)
    assert b1_final == 0
    assert w1_final == b1_after_dep
