import pytest
import discord
from unittest.mock import AsyncMock, MagicMock
from cogs.utility import Utility, EmbedStudioModal

@pytest.mark.asyncio
async def test_telemetry_command():
    bot = MagicMock()
    bot.wait_until_ready = AsyncMock()
    bot.latency = 0.015
    bot.guilds = [MagicMock(member_count=500), MagicMock(member_count=250)]
    bot.get_cog = MagicMock(return_value=None)
    bot.start_time = None

    cog = Utility(bot)
    cog.check_reminders.cancel()

    ctx = MagicMock()
    ctx.guild = MagicMock()
    ctx.guild.shard_id = 0
    ctx.send = AsyncMock()

    await cog.telemetry.callback(cog, ctx)
    ctx.send.assert_called_once()
    embed = ctx.send.call_args[1]["embed"]
    assert "High-Performance Cluster Telemetry" in embed.title
    field_names = [f.name for f in embed.fields]
    assert "⚡ Discord Gateway" in field_names
    assert "🗄️ Database Concurrency" in field_names


@pytest.mark.asyncio
async def test_embed_json_command():
    bot = MagicMock()
    bot.wait_until_ready = AsyncMock()
    cog = Utility(bot)
    cog.check_reminders.cancel()

    target_ch = MagicMock(spec=discord.TextChannel)
    target_ch.id = 12345
    target_ch.send = AsyncMock()
    
    ctx = MagicMock()
    ctx.channel = target_ch
    ctx.send = AsyncMock()
    ctx.interaction = None

    json_payload = """
    ```json
    {
      "embed": {
        "title": "Special Announcement",
        "description": "Helix v2.5 PRO is live!",
        "color": 14753096,
        "fields": [
          {"name": "Status", "value": "Operational", "inline": true}
        ]
      }
    }
    ```
    """

    await cog.embed_json.callback(cog, ctx, channel=target_ch, json_payload=json_payload)
    target_ch.send.assert_called_once()
    embed = target_ch.send.call_args[1]["embed"]
    assert embed.title == "Special Announcement"
    assert embed.description == "Helix v2.5 PRO is live!"
    assert len(embed.fields) == 1
    assert embed.fields[0].name == "Status"


@pytest.mark.asyncio
async def test_embed_modal_submit():
    bot = MagicMock()
    target_ch = MagicMock(spec=discord.TextChannel)
    target_ch.send = AsyncMock()
    target_ch.mention = "<#12345>"

    modal = EmbedStudioModal(target_ch, bot)
    modal.embed_title._value = "Modal Title"
    modal.embed_desc._value = "Modal Description"
    modal.embed_color._value = "#10B981"
    modal.embed_author._value = "Staff Mod"
    modal.embed_footer._value = "Helix Footer"

    inter = MagicMock(spec=discord.Interaction)
    inter.response = MagicMock()
    inter.response.send_message = AsyncMock()

    await modal.on_submit(inter)
    target_ch.send.assert_called_once()
    embed = target_ch.send.call_args[1]["embed"]
    assert embed.title == "Modal Title"
    assert embed.description == "Modal Description"
    assert embed.author.name == "Staff Mod"
    assert embed.footer.text == "Helix Footer"
    inter.response.send_message.assert_called_once()
