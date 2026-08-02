import sys
import os
from pathlib import Path
from types import SimpleNamespace as SN

repo_root = str(Path(__file__).resolve().parents[1])
if sys.path[0] != repo_root:
    sys.path.insert(0, repo_root)

import pytest
import discord
from cogs.logging import get_action_log_channel


class FakeChannel:
    def __init__(self, name, cid):
        self.name = name
        self.id = cid
        self.mention = f"<#{cid}>"



class FakeGuild:
    def __init__(self, channels):
        self.id = 999
        self.text_channels = channels

    def get_channel(self, cid):
        for c in self.text_channels:
            if c.id == cid:
                return c
        return None


@pytest.mark.asyncio
async def test_get_action_log_channel_matching():
    guild = FakeGuild([
        FakeChannel("ban-unban_log", 1),
        FakeChannel("wick-log", 2),
        FakeChannel("security-log", 3),
        FakeChannel("role-create-log", 4),
        FakeChannel("role-update-log", 5),
        FakeChannel("role-delete-log", 6),
        FakeChannel("channel-create-log", 7),
        FakeChannel("role-add-remove-log", 8),
        FakeChannel("channel-delete-log", 9),
    ])

    ch_ban = await get_action_log_channel(guild, "ban_unban")
    assert ch_ban is not None and ch_ban.name == "ban-unban_log"

    ch_wick = await get_action_log_channel(guild, "wick")
    assert ch_wick is not None and ch_wick.name == "wick-log"

    ch_sec = await get_action_log_channel(guild, "security")
    assert ch_sec is not None and ch_sec.name == "security-log"

    ch_rc = await get_action_log_channel(guild, "role_create")
    assert ch_rc is not None and ch_rc.name == "role-create-log"

    ch_ru = await get_action_log_channel(guild, "role_update")
    assert ch_ru is not None and ch_ru.name == "role-update-log"

    ch_rd = await get_action_log_channel(guild, "role_delete")
    assert ch_rd is not None and ch_rd.name == "role-delete-log"

    ch_cc = await get_action_log_channel(guild, "channel_create")
    assert ch_cc is not None and ch_cc.name == "channel-create-log"

    ch_rar = await get_action_log_channel(guild, "role_add_remove")
    assert ch_rar is not None and ch_rar.name == "role-add-remove-log"

    ch_cd = await get_action_log_channel(guild, "channel_delete")
    assert ch_cd is not None and ch_cd.name == "channel-delete-log"


@pytest.mark.asyncio
async def test_setlog_and_setup_logs_commands(tmp_path, monkeypatch):
    from cogs.logging import AuditLogger

    bot = discord.ext.commands.Bot(command_prefix="!", intents=discord.Intents.default(), help_command=None)
    cog = AuditLogger(bot=bot)
    await bot.add_cog(cog)

    sent = []
    async def fake_send(*args, **kwargs):
        sent.append({"args": args, "kwargs": kwargs})

    chan1 = FakeChannel("custom-ban-channel", 555)
    
    class MockGuild:
        def __init__(self):
            self.id = 888
            self.name = "Logging Test Server"
            self.categories = []
            self.text_channels = [chan1]
            self.default_role = SN(id=1)
            self.me = SN(id=99)

        async def create_category(self, name, overwrites=None, reason=None):
            cat = SN(name=name, channels=[])
            self.categories.append(cat)
            return cat

        async def create_text_channel(self, name, category=None, topic=None, reason=None):
            ch = FakeChannel(name, len(self.text_channels) + 100)
            if category:
                category.channels.append(ch)
            self.text_channels.append(ch)
            return ch

        def get_channel(self, cid):
            for c in self.text_channels:
                if c.id == cid:
                    return c
            return None

    guild = MockGuild()
    ctx = SN(guild=guild, send=fake_send, author=SN(id=1))

    # Test !setlog
    await cog.setlog(ctx, event_type="ban_unban", channel=chan1)
    assert len(sent) == 1
    assert "Log Channel Configured" in sent[0]["kwargs"]["embed"].title

    # Test !logs_config
    sent.clear()
    await cog.logs_config(ctx)
    assert len(sent) == 1
    assert "Action Log Configuration" in sent[0]["kwargs"]["embed"].title

    # Test !setup_logs
    sent.clear()
    await cog.setup_logs(ctx)
    assert len(sent) >= 1
    # Find item with embed
    embed_title = None
    for s in sent:
        emb = s["kwargs"].get("embed")
        if emb:
            embed_title = emb.title
            break
        if len(s["args"]) > 1 and isinstance(s["args"][1], discord.Embed):
            embed_title = s["args"][1].title
            break

    assert embed_title is not None
    assert "Action Log Channels Created & Configured" in embed_title
    assert len(guild.categories) == 1
    assert len(guild.categories[0].channels) == 13


@pytest.mark.asyncio
async def test_image_logging():
    from cogs.logging import AuditLogger

    bot = discord.ext.commands.Bot(command_prefix="!", intents=discord.Intents.default(), help_command=None)
    cog = AuditLogger(bot=bot)

    sent = []
    async def fake_send(embed=None, **kwargs):
        sent.append(embed)

    image_log_chan = FakeChannel("image-log", 999)
    image_log_chan.send = fake_send

    class MockGuild:
        def __init__(self):
            self.id = 888
            self.name = "Image Log Guild"
            self.text_channels = [image_log_chan]

    guild = MockGuild()
    user = SN(id=123, mention="<@123>", display_avatar=SN(url="http://avatar.jpg"), bot=False)
    msg_chan = FakeChannel("general", 111)

    attachment = SN(url="http://image.png", content_type="image/png", filename="test.png")
    message = SN(guild=guild, author=user, channel=msg_chan, attachments=[attachment], content="", jump_url="http://discord.com/jump")

    await cog.on_message(message)
    assert len(sent) == 1
    assert sent[0].title == "Image Logged"
    assert "Image uploaded by <@123>" in sent[0].description


@pytest.mark.asyncio
async def test_join_leave_logging():
    from cogs.logging import AuditLogger
    from datetime import datetime, timezone

    bot = discord.ext.commands.Bot(command_prefix="!", intents=discord.Intents.default(), help_command=None)
    cog = AuditLogger(bot=bot)

    sent = []
    async def fake_send(embed=None, **kwargs):
        sent.append(embed)

    join_chan = FakeChannel("join-leave-log", 777)
    join_chan.send = fake_send

    class MockGuild:
        def __init__(self):
            self.id = 888
            self.name = "Join Leave Guild"
            self.text_channels = [join_chan]
            self.default_role = SN(id=1)

    guild = MockGuild()
    member = SN(id=456, mention="<@456>", guild=guild, created_at=datetime.now(timezone.utc), display_avatar=SN(url="http://avatar.jpg"), roles=[])

    # 1. Join
    await cog.on_member_join(member)
    assert len(sent) == 1
    assert sent[0].title == "Member Joined"

    # 2. Leave
    sent.clear()
    await cog.on_member_remove(member)
    assert len(sent) == 1
    assert sent[0].title == "Member Left"





@pytest.mark.asyncio
async def test_voice_logging():
    from cogs.logging import AuditLogger

    bot = discord.ext.commands.Bot(command_prefix="!", intents=discord.Intents.default(), help_command=None)
    cog = AuditLogger(bot=bot)
    await bot.add_cog(cog)

    sent_embeds = []
    log_chan = FakeChannel("voice-log", 777)
    async def fake_send(embed=None):
        sent_embeds.append(embed)
    log_chan.send = fake_send

    guild = FakeGuild([log_chan])
    member = SN(id=123, mention="<@123>", guild=guild, avatar=None, default_avatar=SN(url="http://avatar"))
    
    vc1 = FakeChannel("General VC", 101)
    vc2 = FakeChannel("Gaming VC", 102)

    # 1. Join VC
    b_join = SN(channel=None)
    a_join = SN(channel=vc1, self_mute=False, self_deaf=False, mute=False, deaf=False)
    await cog.on_voice_state_update(member, b_join, a_join)
    assert len(sent_embeds) == 1
    assert "Joined Voice Channel" in sent_embeds[0].title

    # 2. Switch VC
    b_switch = SN(channel=vc1)
    a_switch = SN(channel=vc2, self_mute=False, self_deaf=False, mute=False, deaf=False)
    await cog.on_voice_state_update(member, b_switch, a_switch)
    assert len(sent_embeds) == 2
    assert "Switched Voice Channel" in sent_embeds[1].title

    # 3. Leave VC
    b_leave = SN(channel=vc2)
    a_leave = SN(channel=None)
    await cog.on_voice_state_update(member, b_leave, a_leave)
    assert len(sent_embeds) == 3
    assert "Left Voice Channel" in sent_embeds[2].title





