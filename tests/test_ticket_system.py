import pytest
import asyncio
import json
import random
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone
import discord

from main import bot
from utils.cog_loader import load_cogs
from utils.db import get_connection, init_db
from cogs.tickets import TicketsCog, TicketControlView, TicketPanelBuilderView
from utils.transcript_generator import generate_html_transcript


@pytest.mark.asyncio
async def test_custom_ticket_panel_lifecycle():
    """Verify customizable ticket panel: create panel, add custom options, open ticket with role/cat, close, and reopen."""
    await init_db()
    await load_cogs(bot)

    ticket_cog = bot.get_cog("Tickets")
    assert ticket_cog is not None

    # 1. Setup mock guild & staff
    test_user_id = random.randint(10000000, 99999999)
    guild = MagicMock(spec=discord.Guild)
    guild.id = random.randint(10000000, 99999999)
    guild.name = "Custom Gaming Hub"
    guild.owner_id = 999
    guild.default_role = MagicMock(spec=discord.Role, id=guild.id)
    guild.me = MagicMock(spec=discord.Member, id=1111)

    # Custom category & custom VIP support role
    vip_category = MagicMock(spec=discord.CategoryChannel)
    vip_category.id = 55667788
    vip_category.name = "VIP Tickets"

    closed_category = MagicMock(spec=discord.CategoryChannel)
    closed_category.id = 55667799
    closed_category.name = "Closed Tickets"

    vip_role = MagicMock(spec=discord.Role)
    vip_role.id = 44556677
    vip_role.mention = "<@&44556677>"
    vip_role.name = "VIP Support"

    transcripts_chan = MagicMock(spec=discord.TextChannel)
    transcripts_chan.id = 88776655
    transcripts_chan.name = "ticket-transcripts"
    transcripts_chan.send = AsyncMock()

    def mock_get_channel(cid):
        if cid == vip_category.id:
            return vip_category
        if cid == closed_category.id:
            return closed_category
        if cid == transcripts_chan.id:
            return transcripts_chan
        return None

    def mock_get_role(rid):
        if rid == vip_role.id:
            return vip_role
        return None

    guild.get_channel = mock_get_channel
    guild.get_role = mock_get_role

    user = MagicMock(spec=discord.Member)
    user.id = test_user_id
    user.mention = f"<@{test_user_id}>"
    user.name = "ProPlayer"
    user.display_name = "ProPlayer"
    user.guild = guild

    # Panel Context
    panel_msg_id = random.randint(10000000, 99999999)
    panel_msg = MagicMock(spec=discord.Message, id=panel_msg_id)
    panel_msg.edit = AsyncMock()

    panel_chan = MagicMock(spec=discord.TextChannel)
    panel_chan.id = random.randint(10000000, 99999999)
    panel_chan.send = AsyncMock(return_value=panel_msg)
    panel_chan.fetch_message = AsyncMock(return_value=panel_msg)

    ctx = MagicMock()
    ctx.guild = guild
    ctx.channel = panel_chan
    ctx.author = user
    ctx.author.guild_permissions = MagicMock(administrator=True)
    ctx.send = AsyncMock(return_value=panel_msg)
    ctx.interaction = None

    # Step 1: Run !ticket setup (Dual category setup + transcript channel)
    await ticket_cog.ticket_setup_cmd(
        ctx,
        open_category=vip_category,
        closed_category=closed_category,
        support_role=vip_role,
        transcript_channel=transcripts_chan
    )

    # Step 2: Create Panel
    await ticket_cog.ticket_panel_cmd(ctx, title="Customer Support Center")
    ctx.send.assert_called()

    # Step 3: Add Custom Option with designated VIP category & VIP role
    await ticket_cog.panel_addoption(
        ctx,
        message_id=str(panel_msg_id),
        emoji="💎",
        label="VIP Store Inquiries",
        description="Assistance with VIP perks and store orders",
        category=vip_category,
        staff_role=vip_role,
        name_prefix="ticket"
    )

    # Step 3b: Edit Custom Option label and emoji
    await ticket_cog.panel_editoption(
        ctx,
        message_id=str(panel_msg_id),
        target_label="VIP Store Inquiries",
        emoji="👑",
        new_label="VIP Concierge",
        description="Priority support for VIP members"
    )

    # Verify option stored in DB
    async with get_connection() as conn:
        cur = await conn.execute("SELECT id, options_json FROM ticket_panels WHERE message_id = ?", (panel_msg_id,))
        p_row = await cur.fetchone()
        await cur.close()
        assert p_row is not None
        panel_id = p_row["id"]
        opts = json.loads(p_row["options_json"])
        vip_opt = next((o for o in opts if o.get("label") == "VIP Concierge"), None)
        assert vip_opt is not None
        assert vip_opt["label"] == "VIP Concierge"
        assert vip_opt["emoji"] == "👑"
        assert vip_opt["category_id"] == vip_category.id
        assert vip_opt["role_id"] == vip_role.id

    # Step 4: Open ticket using the custom option (Channel named 🎫・0001)

    ticket_chan = MagicMock(spec=discord.TextChannel)
    ticket_chan.id = random.randint(10000000, 99999999)
    ticket_chan.name = "🎫・0001"
    ticket_chan.mention = f"<#{ticket_chan.id}>"
    ticket_chan.category_id = vip_category.id
    ticket_chan.send = AsyncMock()
    ticket_chan.edit = AsyncMock()
    ticket_chan.set_permissions = AsyncMock()
    ticket_chan.guild = guild

    async def mock_history(*args, **kwargs):
        m = MagicMock(spec=discord.Message)
        m.created_at = datetime.now(timezone.utc)
        m.author = user
        m.content = "I purchased VIP and need help."
        m.clean_content = "I purchased VIP and need help."
        m.attachments = []
        m.embeds = []
        yield m

    ticket_chan.history = mock_history
    guild.create_text_channel = AsyncMock(return_value=ticket_chan)

    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild = guild
    interaction.user = user
    interaction.response = MagicMock(is_done=MagicMock(return_value=False))
    interaction.response.defer = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    interaction.channel = ticket_chan

    await ticket_cog.create_ticket_channel(interaction, panel_id, vip_opt["value"])
    guild.create_text_channel.assert_called_once()
    call_kwargs = guild.create_text_channel.call_args[1]
    assert call_kwargs["name"] == "🎫・0001"
    assert call_kwargs["category"] == vip_category

    # Verify overwrites contain VIP role
    overwrites = call_kwargs["overwrites"]
    assert vip_role in overwrites

    # Step 5: Claim (Renames to mod-name-number), Close (renames to closed-XXXX & moves), Reopen lifecycle
    async with get_connection() as conn:
        cur = await conn.execute("SELECT id FROM tickets WHERE channel_id = ?", (ticket_chan.id,))
        t_row = await cur.fetchone()
        await cur.close()
        ticket_id = t_row["id"]

    staff_user = MagicMock(spec=discord.Member)
    staff_user.id = 888999
    staff_user.mention = "<@888999>"
    staff_user.display_name = "StaffMod"
    staff_user.guild_permissions = MagicMock(administrator=True)

    def mock_get_member(uid):
        if uid == staff_user.id:
            return staff_user
        if uid == user.id:
            return user
        return None
    guild.get_member = mock_get_member

    inter_staff = MagicMock(spec=discord.Interaction)
    inter_staff.guild = guild
    inter_staff.user = staff_user
    inter_staff.channel = ticket_chan
    inter_staff.response = MagicMock(is_done=MagicMock(return_value=False))
    inter_staff.response.defer = AsyncMock()
    inter_staff.response.send_message = AsyncMock()

    # Claim -> Renames to staffmod-0001
    await ticket_cog.claim_ticket(inter_staff, ticket_id)
    async with get_connection() as conn:
        cur = await conn.execute("SELECT claimed_by FROM tickets WHERE id = ?", (ticket_id,))
        t_claimed = await cur.fetchone()
        await cur.close()
        assert t_claimed["claimed_by"] == staff_user.id

    ticket_chan.edit.assert_called_with(name="staffmod-0001", reason="Ticket Claimed")

    # Close -> Renames to closed-0001 and moves to closed_category
    await ticket_cog.process_close_ticket(inter_staff, ticket_id)
    async with get_connection() as conn:
        cur = await conn.execute("SELECT status, closed_at FROM tickets WHERE id = ?", (ticket_id,))
        t_closed = await cur.fetchone()
        await cur.close()
        assert t_closed["status"] == "closed"
        assert t_closed["closed_at"] is not None

    ticket_chan.edit.assert_called_with(name="closed-0001", category=closed_category, reason="Ticket Closed")
    transcripts_chan.send.assert_called()

    # Reopen -> Restores name staffmod-0001 and moves back to vip_category
    await ticket_cog.reopen_ticket(inter_staff, ticket_id)
    async with get_connection() as conn:
        cur = await conn.execute("SELECT status, closed_at FROM tickets WHERE id = ?", (ticket_id,))
        t_reopened = await cur.fetchone()
        await cur.close()
        assert t_reopened["status"] == "open"
        assert t_reopened["closed_at"] is None

    ticket_chan.edit.assert_called_with(name="staffmod-0001", category=vip_category, reason="Ticket Reopened")


@pytest.mark.asyncio
async def test_ticket_embed_builder_preview_and_deployment():
    """Verify the interactive Embed Builder can customize properties and deploy a panel to a channel."""
    await init_db()
    ticket_cog = bot.get_cog("Tickets")
    assert ticket_cog is not None

    guild = MagicMock(spec=discord.Guild, id=random.randint(10000000, 99999999), name="Builder Test Guild")
    author_id = random.randint(10000000, 99999999)

    builder = TicketPanelBuilderView(ticket_cog, author_id)
    builder.title = "Custom Complaints & Helpdesk"
    builder.description = "Make a ticket here for complaints or general issues."
    builder.color_hex = "#FF5733"

    preview_embed = builder.render_preview()
    assert "Custom Complaints & Helpdesk" in preview_embed.title
    assert "Make a ticket here for complaints" in preview_embed.description

    # Deploy to mock channel
    target_msg = MagicMock(spec=discord.Message, id=random.randint(10000000, 99999999))
    target_msg.edit = AsyncMock()

    target_chan = MagicMock(spec=discord.TextChannel, id=random.randint(10000000, 99999999))
    target_chan.mention = f"<#{target_chan.id}>"
    target_chan.send = AsyncMock(return_value=target_msg)
    guild.get_channel = MagicMock(return_value=target_chan)

    deploy_inter = MagicMock(spec=discord.Interaction, guild=guild)
    deploy_inter.response = MagicMock(is_done=MagicMock(return_value=False))
    deploy_inter.response.edit_message = AsyncMock()

    await builder.deploy_to_channel(deploy_inter, target_chan)
    target_chan.send.assert_called_once()
    deploy_inter.response.edit_message.assert_called_once()

    # Verify panel stored in DB
    async with get_connection() as conn:
        cur = await conn.execute("SELECT title, description FROM ticket_panels WHERE message_id = ?", (target_msg.id,))
        row = await cur.fetchone()
        await cur.close()
        assert row is not None
        assert row["title"] == "Custom Complaints & Helpdesk"
        assert row["description"] == "Make a ticket here for complaints or general issues."


@pytest.mark.asyncio
async def test_per_guild_independent_ticket_numbering():
    """Verify that Guild A and Guild B have completely independent sequential counters (#0001, #0002)."""
    await init_db()
    ticket_cog = bot.get_cog("Tickets")
    assert ticket_cog is not None

    guild_a = MagicMock(spec=discord.Guild)
    guild_a.id = random.randint(10000000, 99999999)
    guild_a.default_role = MagicMock(spec=discord.Role, id=guild_a.id)
    guild_a.me = MagicMock(spec=discord.Member, id=9999)
    guild_a.get_channel = MagicMock(return_value=None)
    guild_a.get_role = MagicMock(return_value=None)

    guild_b = MagicMock(spec=discord.Guild)
    guild_b.id = random.randint(10000000, 99999999)
    guild_b.default_role = MagicMock(spec=discord.Role, id=guild_b.id)
    guild_b.me = MagicMock(spec=discord.Member, id=9999)
    guild_b.get_channel = MagicMock(return_value=None)
    guild_b.get_role = MagicMock(return_value=None)

    user_a = MagicMock(spec=discord.Member, id=random.randint(10000000, 99999999))
    user_a.mention = f"<@{user_a.id}>"
    user_b = MagicMock(spec=discord.Member, id=random.randint(10000000, 99999999))
    user_b.mention = f"<@{user_b.id}>"
    user_a2 = MagicMock(spec=discord.Member, id=random.randint(10000000, 99999999))
    user_a2.mention = f"<@{user_a2.id}>"

    # Create panels in Guild A and Guild B with unique random message IDs
    p_msg_a = random.randint(10000000, 99999999)
    p_msg_b = random.randint(10000000, 99999999)
    async with get_connection() as conn:
        cur = await conn.execute(
            "INSERT INTO ticket_panels (guild_id, channel_id, message_id, title, description, created_at) VALUES (?, 10, ?, 'Panel A', 'Desc', '2026-08-15')",
            (guild_a.id, p_msg_a)
        )
        panel_a_id = cur.lastrowid
        cur = await conn.execute(
            "INSERT INTO ticket_panels (guild_id, channel_id, message_id, title, description, created_at) VALUES (?, 20, ?, 'Panel B', 'Desc', '2026-08-15')",
            (guild_b.id, p_msg_b)
        )
        panel_b_id = cur.lastrowid
        await conn.commit()

    # Guild A Ticket 1
    t_chan_a1 = MagicMock(spec=discord.TextChannel, id=random.randint(10000000, 99999999), name="🎫・0001")
    guild_a.create_text_channel = AsyncMock(return_value=t_chan_a1)

    inter_a1 = MagicMock(spec=discord.Interaction, guild=guild_a, user=user_a, channel=t_chan_a1)
    inter_a1.response = MagicMock(is_done=MagicMock(return_value=False), defer=AsyncMock())
    inter_a1.followup = MagicMock(send=AsyncMock())
    await ticket_cog.create_ticket_channel(inter_a1, panel_a_id, "support")
    assert guild_a.create_text_channel.call_args[1]["name"] == "🎫・0001"

    # Guild B Ticket 1 -> Gets #0001 independently!
    t_chan_b1 = MagicMock(spec=discord.TextChannel, id=random.randint(10000000, 99999999), name="🎫・0001")
    guild_b.create_text_channel = AsyncMock(return_value=t_chan_b1)

    inter_b1 = MagicMock(spec=discord.Interaction, guild=guild_b, user=user_b, channel=t_chan_b1)
    inter_b1.response = MagicMock(is_done=MagicMock(return_value=False), defer=AsyncMock())
    inter_b1.followup = MagicMock(send=AsyncMock())
    await ticket_cog.create_ticket_channel(inter_b1, panel_b_id, "support")
    assert guild_b.create_text_channel.call_args[1]["name"] == "🎫・0001"

    # Guild A Ticket 2 -> Gets #0002
    t_chan_a2 = MagicMock(spec=discord.TextChannel, id=random.randint(10000000, 99999999), name="🎫・0002")
    guild_a.create_text_channel = AsyncMock(return_value=t_chan_a2)

    inter_a2 = MagicMock(spec=discord.Interaction, guild=guild_a, user=user_a2, channel=t_chan_a2)
    inter_a2.response = MagicMock(is_done=MagicMock(return_value=False), defer=AsyncMock())
    inter_a2.followup = MagicMock(send=AsyncMock())
    await ticket_cog.create_ticket_channel(inter_a2, panel_a_id, "support")
    assert guild_a.create_text_channel.call_args[1]["name"] == "🎫・0002"


@pytest.mark.asyncio
async def test_ticket_control_view_and_rename():
    from cogs.tickets import TicketControlView, TicketRenameModal
    
    # 1. Unclaimed view: Has Claim, Close, Transcript; NO Unclaim
    view_unclaimed = TicketControlView(ticket_id=99, is_closed=False, claimed_by=None)
    labels_unclaimed = [item.label for item in view_unclaimed.children if isinstance(item, discord.ui.Button)]
    assert "Claim" in labels_unclaimed
    assert "Close" in labels_unclaimed
    assert "Transcript" in labels_unclaimed
    assert "Unclaim" not in labels_unclaimed
    assert "Rename" not in labels_unclaimed

    # 2. Claimed view: Has Close, Rename, Transcript; NO Claim, NO Unclaim
    view_claimed = TicketControlView(ticket_id=99, is_closed=False, claimed_by=123456)
    labels_claimed = [item.label for item in view_claimed.children if isinstance(item, discord.ui.Button)]
    assert "Close" in labels_claimed
    assert "Rename" in labels_claimed
    assert "Transcript" in labels_claimed
    assert "Claim" not in labels_claimed
    assert "Unclaim" not in labels_claimed

    # 3. Rename Modal submission
    mock_cog = MagicMock()
    modal = TicketRenameModal(ticket_id=99, cog=mock_cog)
    modal.channel_name._value = "billing-query"

    inter = MagicMock(spec=discord.Interaction)
    chan = MagicMock(spec=discord.TextChannel)
    chan.edit = AsyncMock()
    inter.channel = chan
    inter.user = MagicMock(display_name="StaffMod")
    inter.response = MagicMock()
    inter.response.send_message = AsyncMock()

    await modal.on_submit(inter)
    chan.edit.assert_called_once()
    assert chan.edit.call_args[1]["name"] == "billing-query"
    inter.response.send_message.assert_called_once()


@pytest.mark.asyncio
async def test_persistent_confirm_views_and_interaction_fallback():
    """Verify CloseConfirmView has persistent custom_ids and on_interaction handles callbacks."""
    from cogs.tickets import CloseConfirmView, DeleteConfirmView

    close_view = CloseConfirmView(ticket_id=42)
    custom_ids = [btn.custom_id for btn in close_view.children if isinstance(btn, discord.ui.Button)]
    assert "ticket_close:confirm:42" in custom_ids
    assert "ticket_close:cancel:42" in custom_ids

    del_view = DeleteConfirmView(ticket_id=42)
    del_ids = [btn.custom_id for btn in del_view.children if isinstance(btn, discord.ui.Button)]
    assert "ticket_del:confirm:42" in del_ids
    assert "ticket_del:cancel:42" in del_ids

    ticket_cog = bot.get_cog("Tickets")
    assert ticket_cog is not None

    # Test fallback interaction listener for ticket_close:cancel
    mock_inter = MagicMock(spec=discord.Interaction)
    mock_inter.type = discord.InteractionType.component
    mock_inter.data = {"custom_id": "ticket_close:cancel:42"}
    mock_inter.response = MagicMock()
    mock_inter.response.is_done = MagicMock(return_value=False)
    mock_inter.response.edit_message = AsyncMock()

    await ticket_cog.on_interaction(mock_inter)
    mock_inter.response.edit_message.assert_called_once()


