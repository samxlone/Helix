import asyncio
import io
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

import discord
from discord.ext import commands

from utils.db import get_connection
from utils.transcript_generator import generate_html_transcript

def set_ticket_footer(embed: discord.Embed, *args, extra_text: str = "", **kwargs) -> discord.Embed:
    """Clean, unbranded footer for ticket panels and ticket channel interactions."""
    txt = extra_text
    for a in args:
        if isinstance(a, str):
            txt = a
    if txt:
        embed.set_footer(text=txt)
    return embed

logger = logging.getLogger(__name__)

# Default ticket categories for the Support Center dropdown
DEFAULT_TICKET_OPTIONS = [
    {
        "value": "support",
        "label": "Support",
        "emoji": "🛠️",
        "description": "General assistance and technical support",
        "category_id": None,
        "role_id": None,
        "name_format": "ticket"
    },
    {
        "value": "billing",
        "label": "Billing",
        "emoji": "💳",
        "description": "Payment issues, store inquiries & donations",
        "category_id": None,
        "role_id": None,
        "name_format": "ticket"
    },
    {
        "value": "partnership",
        "label": "Partnership",
        "emoji": "🤝",
        "description": "Server collaborations and sponsorships",
        "category_id": None,
        "role_id": None,
        "name_format": "ticket"
    },
    {
        "value": "report",
        "label": "Report",
        "emoji": "📢",
        "description": "Report player misconduct or rule breaks",
        "category_id": None,
        "role_id": None,
        "name_format": "ticket"
    }
]


# ==============================================================================
# HELPER: SAFE NON-BLOCKING CHANNEL EDITING
# ==============================================================================

async def safe_edit_channel(
    channel: discord.TextChannel,
    name: Optional[str] = None,
    category: Optional[discord.CategoryChannel] = None,
    reason: str = "Helix Ticket Action",
    timeout: float = 2.0
) -> bool:
    """
    Edits a channel's name and/or category with a strict non-blocking timeout.
    Prevents Discord's 2-renames-per-10-minutes rate limit from stalling ticket operations.
    """
    if not isinstance(channel, discord.TextChannel):
        return False
    kwargs = {}
    if name is not None and channel.name != name:
        kwargs["name"] = name
    if category is not None and channel.category_id != category.id:
        kwargs["category"] = category
    if not kwargs:
        return True
    kwargs["reason"] = reason

    try:
        await asyncio.wait_for(channel.edit(**kwargs), timeout=timeout)
        if category is not None:
            try:
                channel.category_id = category.id
            except Exception:
                pass
        return True
    except asyncio.TimeoutError:
        logger.warning("Channel edit on #%s timed out (%ss) due to Discord rate limits. Queueing background update.", channel.name, timeout)
        asyncio.create_task(_bg_channel_edit(channel, kwargs, category))
        return False
    except discord.HTTPException as e:
        logger.warning("Discord HTTP exception on channel edit #%s: %s", channel.name, e)
        return False
    except Exception as e:
        logger.warning("Unexpected error on channel edit #%s: %s", channel.name, e)
        return False

async def _bg_channel_edit(channel: discord.TextChannel, kwargs: dict, category: Optional[discord.CategoryChannel] = None):
    try:
        await channel.edit(**kwargs)
        if category is not None:
            try:
                channel.category_id = category.id
            except Exception:
                pass
        logger.info("Background channel edit completed successfully on #%s", getattr(channel, 'name', 'unknown'))
    except Exception as e:
        logger.debug("Background channel edit failed on #%s: %s", getattr(channel, 'name', 'unknown'), e)


# ==============================================================================
# 1. UI VIEWS & CONFIRMATION DIALOGS
# ==============================================================================

class CloseConfirmView(discord.ui.View):
    """Interactive confirmation modal/view before closing a ticket."""
    def __init__(self, ticket_id: int, cog: Optional["TicketsCog"] = None):
        super().__init__(timeout=None)
        self.ticket_id = ticket_id
        self.cog = cog

        confirm_btn = discord.ui.Button(
            label="Confirm Close",
            emoji="🔒",
            style=discord.ButtonStyle.danger,
            custom_id=f"ticket_close:confirm:{ticket_id}"
        )
        confirm_btn.callback = self._confirm_callback
        self.add_item(confirm_btn)

        cancel_btn = discord.ui.Button(
            label="Cancel",
            emoji="❌",
            style=discord.ButtonStyle.secondary,
            custom_id=f"ticket_close:cancel:{ticket_id}"
        )
        cancel_btn.callback = self._cancel_callback
        self.add_item(cancel_btn)

    async def _confirm_callback(self, interaction: discord.Interaction):
        if not interaction.response.is_done():
            await interaction.response.defer()
        self.stop()
        cog = self.cog or interaction.client.get_cog("Tickets")
        if cog:
            await cog.process_close_ticket(interaction, self.ticket_id)

    async def _cancel_callback(self, interaction: discord.Interaction):
        self.stop()
        if not interaction.response.is_done():
            await interaction.response.edit_message(content="❌ Ticket close request cancelled.", embed=None, view=None)


class DeleteConfirmView(discord.ui.View):
    """Interactive confirmation before permanently deleting a ticket channel."""
    def __init__(self, ticket_id: int, cog: Optional["TicketsCog"] = None):
        super().__init__(timeout=None)
        self.ticket_id = ticket_id
        self.cog = cog

        confirm_btn = discord.ui.Button(
            label="Delete Ticket",
            emoji="🗑️",
            style=discord.ButtonStyle.danger,
            custom_id=f"ticket_del:confirm:{ticket_id}"
        )
        confirm_btn.callback = self._confirm_callback
        self.add_item(confirm_btn)

        cancel_btn = discord.ui.Button(
            label="Cancel",
            emoji="❌",
            style=discord.ButtonStyle.secondary,
            custom_id=f"ticket_del:cancel:{ticket_id}"
        )
        cancel_btn.callback = self._cancel_callback
        self.add_item(cancel_btn)

    async def _confirm_callback(self, interaction: discord.Interaction):
        if not interaction.response.is_done():
            await interaction.response.defer()
        self.stop()
        cog = self.cog or interaction.client.get_cog("Tickets")
        if cog:
            await cog.process_delete_ticket(interaction, self.ticket_id)

    async def _cancel_callback(self, interaction: discord.Interaction):
        self.stop()
        if not interaction.response.is_done():
            await interaction.response.edit_message(content="❌ Ticket deletion cancelled.", embed=None, view=None)


class DynamicTicketSelect(discord.ui.Select):
    def __init__(self, panel_id: int, options_data: List[Dict[str, Any]]):
        self.panel_id = panel_id
        select_options = []
        for opt in options_data:
            select_options.append(
                discord.SelectOption(
                    label=opt.get("label", "Support")[:100],
                    value=opt.get("value", "support")[:100],
                    emoji=opt.get("emoji") or "📩",
                    description=(opt.get("description") or "Open a ticket")[:100]
                )
            )
        if not select_options:
            select_options.append(
                discord.SelectOption(label="Support", value="support", emoji="🛠️", description="General support")
            )

        super().__init__(
            placeholder="Select a category to open a ticket...",
            min_values=1,
            max_values=1,
            options=select_options,
            custom_id=f"ticket_panel:select:{panel_id}"
        )

    async def callback(self, interaction: discord.Interaction):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)

        category_val = self.values[0]
        cog: Optional[TicketsCog] = interaction.client.get_cog("Tickets")
        if not cog:
            await interaction.followup.send("❌ Ticket system service is currently unavailable.", ephemeral=True)
            return

        await cog.create_ticket_channel(interaction, self.panel_id, category_val)


class TicketPanelView(discord.ui.View):
    def __init__(self, panel_id: int, options_data: Optional[List[Dict[str, Any]]] = None):
        super().__init__(timeout=None)
        self.panel_id = panel_id
        opts = options_data if options_data else DEFAULT_TICKET_OPTIONS
        self.add_item(DynamicTicketSelect(panel_id, opts))

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item) -> None:
        logger.exception("TicketPanelView error: %s", error)
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ An error occurred interacting with the ticket panel.", ephemeral=True)
            else:
                await interaction.followup.send("❌ An error occurred interacting with the ticket panel.", ephemeral=True)
        except Exception:
            pass


class TicketRenameModal(discord.ui.Modal, title="✏️ Rename Ticket Channel"):
    channel_name = discord.ui.TextInput(
        label="New Channel Name",
        placeholder="e.g. priority-billing or user-support",
        required=True,
        max_length=100
    )

    def __init__(self, ticket_id: int, cog: "TicketsCog"):
        super().__init__()
        self.ticket_id = ticket_id
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        clean_name = self.channel_name.value.strip().lower().replace(" ", "-")[:100]
        if not clean_name:
            await interaction.response.send_message("❌ Invalid channel name.", ephemeral=True)
            return

        if isinstance(interaction.channel, discord.TextChannel):
            success = await safe_edit_channel(
                interaction.channel,
                name=clean_name,
                reason=f"Ticket #{self.ticket_id} Renamed by {interaction.user.display_name}"
            )
            if success:
                await interaction.response.send_message(f"✏️ Ticket channel renamed to **#{clean_name}**.")
            else:
                await interaction.response.send_message(f"✏️ Rename queued for **#{clean_name}** *(Discord rate limit: max 2 renames per 10 min)*.")


class TicketControlView(discord.ui.View):
    def __init__(self, ticket_id: int, is_closed: bool = False, claimed_by: Optional[int] = None):
        super().__init__(timeout=None)
        self.ticket_id = ticket_id
        self.is_closed = is_closed
        self.claimed_by = claimed_by
        self._build_buttons()

    def _build_buttons(self):
        self.clear_items()
        if not self.is_closed:
            # Open ticket buttons: [Claim] (if unclaimed), [Close], [Rename] (if claimed), [Transcript]
            if not self.claimed_by:
                claim_btn = discord.ui.Button(
                    label="Claim",
                    emoji="👤",
                    style=discord.ButtonStyle.primary,
                    custom_id=f"ticket_act:claim:{self.ticket_id}"
                )
                claim_btn.callback = self._claim_callback
                self.add_item(claim_btn)

            close_btn = discord.ui.Button(
                label="Close",
                emoji="🔒",
                style=discord.ButtonStyle.danger,
                custom_id=f"ticket_act:close:{self.ticket_id}"
            )
            close_btn.callback = self._close_callback
            self.add_item(close_btn)

            if self.claimed_by:
                rename_btn = discord.ui.Button(
                    label="Rename",
                    emoji="✏️",
                    style=discord.ButtonStyle.secondary,
                    custom_id=f"ticket_act:rename:{self.ticket_id}"
                )
                rename_btn.callback = self._rename_callback
                self.add_item(rename_btn)

            transcript_btn = discord.ui.Button(
                label="Transcript",
                emoji="📜",
                style=discord.ButtonStyle.secondary,
                custom_id=f"ticket_act:transcript:{self.ticket_id}"
            )
            transcript_btn.callback = self._transcript_callback
            self.add_item(transcript_btn)
        else:
            # Closed ticket buttons: [Reopen], [Transcript], [Delete Ticket]
            reopen_btn = discord.ui.Button(
                label="Reopen",
                emoji="🔓",
                style=discord.ButtonStyle.success,
                custom_id=f"ticket_act:reopen:{self.ticket_id}"
            )
            reopen_btn.callback = self._reopen_callback
            self.add_item(reopen_btn)

            transcript_btn = discord.ui.Button(
                label="Transcript",
                emoji="📜",
                style=discord.ButtonStyle.secondary,
                custom_id=f"ticket_act:transcript:{self.ticket_id}"
            )
            transcript_btn.callback = self._transcript_callback
            self.add_item(transcript_btn)

            delete_btn = discord.ui.Button(
                label="Delete Ticket",
                emoji="🗑️",
                style=discord.ButtonStyle.danger,
                custom_id=f"ticket_act:delete:{self.ticket_id}"
            )
            delete_btn.callback = self._delete_callback
            self.add_item(delete_btn)

    async def _close_callback(self, interaction: discord.Interaction):
        cog: Optional[TicketsCog] = interaction.client.get_cog("Tickets")
        if cog:
            await cog.prompt_close_ticket(interaction, self.ticket_id)

    async def _claim_callback(self, interaction: discord.Interaction):
        if not interaction.response.is_done():
            await interaction.response.defer()
        cog: Optional[TicketsCog] = interaction.client.get_cog("Tickets")
        if cog:
            await cog.claim_ticket(interaction, self.ticket_id)

    async def _rename_callback(self, interaction: discord.Interaction):
        cog: Optional[TicketsCog] = interaction.client.get_cog("Tickets")
        if cog:
            modal = TicketRenameModal(self.ticket_id, cog)
            await interaction.response.send_modal(modal)

    async def _transcript_callback(self, interaction: discord.Interaction):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        cog: Optional[TicketsCog] = interaction.client.get_cog("Tickets")
        if cog:
            await cog.send_transcript(interaction, self.ticket_id)

    async def _reopen_callback(self, interaction: discord.Interaction):
        if not interaction.response.is_done():
            await interaction.response.defer()
        cog: Optional[TicketsCog] = interaction.client.get_cog("Tickets")
        if cog:
            await cog.reopen_ticket(interaction, self.ticket_id)

    async def _delete_callback(self, interaction: discord.Interaction):
        cog: Optional[TicketsCog] = interaction.client.get_cog("Tickets")
        if cog:
            await cog.prompt_delete_ticket(interaction, self.ticket_id)

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item) -> None:
        logger.exception("TicketControlView error: %s", error)
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ An error occurred executing this ticket action.", ephemeral=True)
            else:
                await interaction.followup.send("❌ An error occurred executing this ticket action.", ephemeral=True)
        except Exception:
            pass


# ==============================================================================
# 2. EMBED BUILDER MODALS & VIEW
# ==============================================================================

class PanelTitleModal(discord.ui.Modal, title="Customize Panel Title"):
    def __init__(self, builder_view: "TicketPanelBuilderView"):
        super().__init__()
        self.builder_view = builder_view
        self.title_input = discord.ui.TextInput(
            label="Panel Title",
            default=self.builder_view.title[:45],
            placeholder="e.g. 🎫 Support & Complaints Center",
            max_length=100,
            required=True
        )
        self.add_item(self.title_input)

    async def on_submit(self, interaction: discord.Interaction):
        self.builder_view.title = self.title_input.value.strip()
        embed = self.builder_view.render_preview()
        await interaction.response.edit_message(embed=embed, view=self.builder_view)


class PanelDescModal(discord.ui.Modal, title="Customize Panel Message"):
    def __init__(self, builder_view: "TicketPanelBuilderView"):
        super().__init__()
        self.builder_view = builder_view
        self.desc_input = discord.ui.TextInput(
            label="Panel Description",
            style=discord.TextStyle.paragraph,
            default=self.builder_view.description,
            placeholder="e.g. Make a ticket here for complaints, questions or server inquiries.",
            max_length=2000,
            required=True
        )
        self.add_item(self.desc_input)

    async def on_submit(self, interaction: discord.Interaction):
        self.builder_view.description = self.desc_input.value.strip()
        embed = self.builder_view.render_preview()
        await interaction.response.edit_message(embed=embed, view=self.builder_view)


class PanelColorModal(discord.ui.Modal, title="Customize Embed Color"):
    def __init__(self, builder_view: "TicketPanelBuilderView"):
        super().__init__()
        self.builder_view = builder_view
        self.color_input = discord.ui.TextInput(
            label="Embed Color (HEX code)",
            default=self.builder_view.color_hex,
            placeholder="#5865F2 or 5865F2",
            max_length=10,
            required=True
        )
        self.add_item(self.color_input)

    async def on_submit(self, interaction: discord.Interaction):
        raw_val = self.color_input.value.strip().replace("#", "")
        try:
            _ = int(raw_val, 16)
            self.builder_view.color_hex = f"#{raw_val}"
        except ValueError:
            await interaction.response.send_message("❌ Invalid HEX color code provided. Example: `#5865F2`", ephemeral=True)
            return

        embed = self.builder_view.render_preview()
        await interaction.response.edit_message(embed=embed, view=self.builder_view)


class PanelImageModal(discord.ui.Modal, title="Customize Banner Image"):
    def __init__(self, builder_view: "TicketPanelBuilderView"):
        super().__init__()
        self.builder_view = builder_view
        self.image_input = discord.ui.TextInput(
            label="Banner Image URL (Optional)",
            default=self.builder_view.image_url or "",
            placeholder="https://example.com/banner.png or leave empty to clear",
            max_length=500,
            required=False
        )
        self.add_item(self.image_input)

    async def on_submit(self, interaction: discord.Interaction):
        val = self.image_input.value.strip()
        self.builder_view.image_url = val if val else None
        embed = self.builder_view.render_preview()
        await interaction.response.edit_message(embed=embed, view=self.builder_view)


class PanelAddOptionModal(discord.ui.Modal, title="Add Ticket Category"):
    def __init__(self, builder_view: "TicketPanelBuilderView"):
        super().__init__()
        self.builder_view = builder_view
        self.emoji_input = discord.ui.TextInput(
            label="Category Emoji",
            default="📩",
            max_length=10,
            required=True
        )
        self.label_input = discord.ui.TextInput(
            label="Category Label",
            placeholder="e.g. Complaints or Staff Report",
            max_length=40,
            required=True
        )
        self.desc_input = discord.ui.TextInput(
            label="Category Description",
            placeholder="Brief explanation for this category",
            max_length=100,
            required=False
        )
        self.add_item(self.emoji_input)
        self.add_item(self.label_input)
        self.add_item(self.desc_input)

    async def on_submit(self, interaction: discord.Interaction):
        label = self.label_input.value.strip()
        val_slug = label.lower().replace(" ", "_")[:30]
        new_opt = {
            "value": val_slug,
            "label": label,
            "emoji": self.emoji_input.value.strip() or "📩",
            "description": self.desc_input.value.strip(),
            "category_id": None,
            "role_id": None,
            "name_format": "ticket"
        }
        self.builder_view.options.append(new_opt)
        embed = self.builder_view.render_preview()
        await interaction.response.edit_message(embed=embed, view=self.builder_view)


class PanelRemoveCategorySelect(discord.ui.Select):
    def __init__(self, builder_view: "TicketPanelBuilderView"):
        self.builder_view = builder_view
        select_options = []
        for opt in builder_view.options:
            select_options.append(
                discord.SelectOption(
                    label=opt.get("label", "Support")[:100],
                    value=opt.get("value", "support")[:100],
                    emoji=opt.get("emoji") or "📩",
                    description=opt.get("description", "")[:100]
                )
            )
        super().__init__(
            placeholder="Choose a category to remove...",
            min_values=1,
            max_values=1,
            options=select_options
        )

    async def callback(self, interaction: discord.Interaction):
        val_to_remove = self.values[0]
        self.builder_view.options = [o for o in self.builder_view.options if o.get("value") != val_to_remove]
        self.builder_view.selecting_removal = False
        self.builder_view.setup_builder_items()
        embed = self.builder_view.render_preview()
        await interaction.response.edit_message(embed=embed, view=self.builder_view)


class PanelEditOptionModal(discord.ui.Modal, title="Edit Category"):
    def __init__(self, builder_view: "TicketPanelBuilderView", opt_val: str):
        super().__init__()
        self.builder_view = builder_view
        self.opt_val = opt_val
        self.matched_opt = next((o for o in self.builder_view.options if o.get("value") == opt_val), {})

        self.emoji_input = discord.ui.TextInput(
            label="Category Emoji",
            default=self.matched_opt.get("emoji", "📩"),
            max_length=10,
            required=True
        )
        self.label_input = discord.ui.TextInput(
            label="Category Label",
            default=self.matched_opt.get("label", "Support"),
            max_length=40,
            required=True
        )
        self.desc_input = discord.ui.TextInput(
            label="Category Description",
            default=self.matched_opt.get("description", ""),
            max_length=100,
            required=False
        )
        self.add_item(self.emoji_input)
        self.add_item(self.label_input)
        self.add_item(self.desc_input)

    async def on_submit(self, interaction: discord.Interaction):
        new_label = self.label_input.value.strip()
        new_val = new_label.lower().replace(" ", "_")[:30]
        for opt in self.builder_view.options:
            if opt.get("value") == self.opt_val:
                opt["label"] = new_label
                opt["emoji"] = self.emoji_input.value.strip() or "📩"
                opt["description"] = self.desc_input.value.strip()
                opt["value"] = new_val
                break

        self.builder_view.selecting_edit = False
        self.builder_view.setup_builder_items()
        embed = self.builder_view.render_preview()
        await interaction.response.edit_message(embed=embed, view=self.builder_view)


class PanelEditCategorySelect(discord.ui.Select):
    def __init__(self, builder_view: "TicketPanelBuilderView"):
        self.builder_view = builder_view
        select_options = []
        for opt in builder_view.options:
            select_options.append(
                discord.SelectOption(
                    label=opt.get("label", "Support")[:100],
                    value=opt.get("value", "support")[:100],
                    emoji=opt.get("emoji") or "📩",
                    description=opt.get("description", "")[:100]
                )
            )
        super().__init__(
            placeholder="Choose a category to edit...",
            min_values=1,
            max_values=1,
            options=select_options
        )

    async def callback(self, interaction: discord.Interaction):
        val_to_edit = self.values[0]
        modal = PanelEditOptionModal(self.builder_view, val_to_edit)
        await interaction.response.send_modal(modal)


class PanelDeployChannelSelect(discord.ui.ChannelSelect):
    def __init__(self, builder_view: "TicketPanelBuilderView"):
        self.builder_view = builder_view
        super().__init__(
            channel_types=[discord.ChannelType.text],
            placeholder="Select target channel to deploy this panel...",
            min_values=1,
            max_values=1
        )

    async def callback(self, interaction: discord.Interaction):
        target_channel = self.values[0]
        await self.builder_view.deploy_to_channel(interaction, target_channel)


class TicketPanelBuilderView(discord.ui.View):
    """Interactive Embed & Category Builder for Discord Ticket Panels."""
    def __init__(self, cog: "TicketsCog", author_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.author_id = author_id

        # State
        self.title: str = "Support Center"
        self.description: str = "Need help or want to submit a complaint?\nSelect a category below to create a private ticket."
        self.color_hex: str = "#5865F2"
        self.image_url: Optional[str] = None
        self.options: List[Dict[str, Any]] = [
            {"value": "support", "label": "Support", "emoji": "🛠️", "description": "General assistance and help"},
            {"value": "complaints", "label": "Complaints", "emoji": "⚠️", "description": "Submit a server or player complaint"},
            {"value": "billing", "label": "Billing", "emoji": "💳", "description": "Purchases, store inquiries & donations"},
            {"value": "partnership", "label": "Partnership", "emoji": "🤝", "description": "Server collaborations and sponsorships"}
        ]
        self.selecting_removal: bool = False
        self.selecting_edit: bool = False
        self.selecting_deploy: bool = False
        self.setup_builder_items()

    def setup_builder_items(self):
        self.clear_items()

        if self.selecting_removal:
            if self.options:
                self.add_item(PanelRemoveCategorySelect(self))
            cancel_btn = discord.ui.Button(label="Done / Back", emoji="🔙", style=discord.ButtonStyle.secondary)
            cancel_btn.callback = self._cancel_subview
            self.add_item(cancel_btn)
            return

        if self.selecting_edit:
            if self.options:
                self.add_item(PanelEditCategorySelect(self))
            cancel_btn = discord.ui.Button(label="Done / Back", emoji="🔙", style=discord.ButtonStyle.secondary)
            cancel_btn.callback = self._cancel_subview
            self.add_item(cancel_btn)
            return

        if self.selecting_deploy:
            self.add_item(PanelDeployChannelSelect(self))
            cancel_btn = discord.ui.Button(label="Cancel Deploy", emoji="🔙", style=discord.ButtonStyle.secondary)
            cancel_btn.callback = self._cancel_subview
            self.add_item(cancel_btn)
            return

        # Main Builder Controls
        btn_title = discord.ui.Button(label="Title", emoji="📝", style=discord.ButtonStyle.secondary)
        btn_title.callback = self._edit_title
        self.add_item(btn_title)

        btn_desc = discord.ui.Button(label="Message", emoji="📄", style=discord.ButtonStyle.secondary)
        btn_desc.callback = self._edit_desc
        self.add_item(btn_desc)

        btn_color = discord.ui.Button(label="Color", emoji="🎨", style=discord.ButtonStyle.secondary)
        btn_color.callback = self._edit_color
        self.add_item(btn_color)

        btn_img = discord.ui.Button(label="Banner", emoji="🖼️", style=discord.ButtonStyle.secondary)
        btn_img.callback = self._edit_image
        self.add_item(btn_img)

        btn_add_cat = discord.ui.Button(label="Add Category", emoji="➕", style=discord.ButtonStyle.primary)
        btn_add_cat.callback = self._add_category
        self.add_item(btn_add_cat)

        if self.options:
            btn_edit_cat = discord.ui.Button(label="Edit Category", emoji="✏️", style=discord.ButtonStyle.secondary)
            btn_edit_cat.callback = self._edit_category_mode
            self.add_item(btn_edit_cat)

            btn_rem_cat = discord.ui.Button(label="Remove Category", emoji="➖", style=discord.ButtonStyle.secondary)
            btn_rem_cat.callback = self._remove_category_mode
            self.add_item(btn_rem_cat)

        btn_deploy = discord.ui.Button(label="Deploy Panel 🚀", emoji="🚀", style=discord.ButtonStyle.success)
        btn_deploy.callback = self._start_deploy
        self.add_item(btn_deploy)

    async def _cancel_subview(self, interaction: discord.Interaction):
        self.selecting_removal = False
        self.selecting_edit = False
        self.selecting_deploy = False
        self.setup_builder_items()
        embed = self.render_preview()
        await interaction.response.edit_message(embed=embed, view=self)

    async def _edit_title(self, interaction: discord.Interaction):
        await interaction.response.send_modal(PanelTitleModal(self))

    async def _edit_desc(self, interaction: discord.Interaction):
        await interaction.response.send_modal(PanelDescModal(self))

    async def _edit_color(self, interaction: discord.Interaction):
        await interaction.response.send_modal(PanelColorModal(self))

    async def _edit_image(self, interaction: discord.Interaction):
        await interaction.response.send_modal(PanelImageModal(self))

    async def _add_category(self, interaction: discord.Interaction):
        await interaction.response.send_modal(PanelAddOptionModal(self))

    async def _edit_category_mode(self, interaction: discord.Interaction):
        self.selecting_edit = True
        self.selecting_removal = False
        self.selecting_deploy = False
        self.setup_builder_items()
        embed = self.render_preview()
        await interaction.response.edit_message(embed=embed, view=self)

    async def _remove_category_mode(self, interaction: discord.Interaction):
        self.selecting_removal = True
        self.selecting_edit = False
        self.selecting_deploy = False
        self.setup_builder_items()
        embed = self.render_preview()
        await interaction.response.edit_message(embed=embed, view=self)

    async def _start_deploy(self, interaction: discord.Interaction):
        self.selecting_deploy = True
        self.selecting_removal = False
        self.selecting_edit = False
        self.setup_builder_items()
        embed = self.render_preview()
        await interaction.response.edit_message(embed=embed, view=self)

    def render_preview(self) -> discord.Embed:
        # Parse Color
        try:
            hex_val = int(self.color_hex.replace("#", ""), 16)
            color = discord.Color(hex_val)
        except Exception:
            color = discord.Color.from_rgb(88, 101, 242)

        embed = discord.Embed(
            title=f"🎫 {self.title}",
            description=self.description,
            color=color
        )

        if self.image_url:
            embed.set_image(url=self.image_url)

        if self.options:
            cat_lines = []
            for opt in self.options:
                em = opt.get("emoji", "📩")
                lbl = opt.get("label", "Support")
                desc = opt.get("description", "")
                cat_lines.append(f"• **{em} {lbl}**" + (f" — *{desc}*" if desc else ""))
            embed.add_field(name="📋 Available Categories", value="\n".join(cat_lines), inline=False)

        set_ticket_footer(embed, self.cog.bot, extra_text="Ticket Embed Builder Preview")
        return embed

    async def deploy_to_channel(self, interaction: discord.Interaction, target_channel: Any):
        guild = interaction.guild
        if not guild:
            return

        chan = guild.get_channel(target_channel.id) if hasattr(target_channel, "id") else target_channel
        if not isinstance(chan, discord.TextChannel):
            await interaction.response.send_message("❌ Selected channel must be a text channel.", ephemeral=True)
            return

        # Render clean final embed without builder preview watermark
        try:
            hex_val = int(self.color_hex.replace("#", ""), 16)
            color = discord.Color(hex_val)
        except Exception:
            color = discord.Color.from_rgb(88, 101, 242)

        final_embed = discord.Embed(
            title=f"🎫 {self.title}",
            description=self.description,
            color=color
        )
        if self.image_url:
            final_embed.set_image(url=self.image_url)

        set_ticket_footer(final_embed, self.cog.bot, extra_text="Select a category below to open a ticket")

        try:
            panel_msg = await chan.send(embed=final_embed)
        except discord.Forbidden:
            await interaction.response.send_message(f"❌ I do not have permission to send messages in {chan.mention}.", ephemeral=True)
            return
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed to deploy panel: {e}", ephemeral=True)
            return

        # Store in DB
        async with get_connection() as conn:
            cur = await conn.execute(
                """
                INSERT INTO ticket_panels (guild_id, channel_id, message_id, title, description, ticket_counter, options_json, embed_color, created_at)
                VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?)
                """,
                (
                    guild.id,
                    chan.id,
                    panel_msg.id,
                    self.title,
                    self.description,
                    json.dumps(self.options),
                    self.color_hex,
                    datetime.now(timezone.utc).isoformat()
                )
            )
            panel_id = cur.lastrowid
            await conn.commit()

        panel_view = TicketPanelView(panel_id, self.options)
        await panel_msg.edit(view=panel_view)

        self.stop()
        await interaction.response.edit_message(
            content=f"✅ **Ticket Panel Successfully Deployed!**\nDeployed to {chan.mention} with message ID `{panel_msg.id}`.",
            embed=None,
            view=None
        )


# ==============================================================================
# 3. MAIN TICKETS COG
# ==============================================================================

class TicketsCog(commands.Cog, name="Tickets"):
    """Modern & Fully Customizable Ticket Tool system for Discord Servers."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _is_staff_or_owner(self, member: discord.Member, staff_role_id: Optional[int] = None) -> bool:
        owner_id = os.getenv("OWNER_ID")
        if owner_id and str(member.id) == str(owner_id):
            return True
        if getattr(member, "guild", None) and member.id == member.guild.owner_id:
            return True
        perms = getattr(member, "guild_permissions", None)
        if perms and (perms.administrator or perms.manage_guild or perms.manage_channels):
            return True
        if staff_role_id and hasattr(member, "roles") and any(r.id == staff_role_id for r in member.roles):
            return True
        return False

    def _render_panel_embed(self, title: str, description: str, options: List[Dict[str, Any]]) -> discord.Embed:
        """Render clean, aesthetic Support Center panel embed with categories."""
        embed = discord.Embed(
            title=f"🎫 {title or 'Support Center'}",
            description=description or "Need help or want to submit a complaint?\nSelect a category below to create a private ticket.",
            color=discord.Color.from_rgb(88, 101, 242)
        )
        set_ticket_footer(embed, self.bot, extra_text="Select a category below to open a ticket")
        return embed

    # -------------------------------------------------------------------------
    # Creation Flow (Clean Numeric Channel Names & Per-Guild Sequential Numbering)
    # -------------------------------------------------------------------------
    async def create_ticket_channel(self, interaction: discord.Interaction, panel_id: int, category_val: str):
        """Create a dedicated private ticket channel with category-specific permissions and per-guild sequential numbering."""
        guild = interaction.guild
        user = interaction.user
        if not guild or not user:
            return

        async with get_connection() as conn:
            # 1. Fetch Guild Configuration
            cur = await conn.execute(
                "SELECT open_category_id, closed_category_id, staff_role_id, transcript_channel_id, log_channel_id, next_ticket_number FROM guild_ticket_config WHERE guild_id = ?",
                (guild.id,)
            )
            g_config = await cur.fetchone()
            await cur.close()

            # 2. Fetch Panel Config
            cur = await conn.execute(
                "SELECT id, title, category_id, staff_role_id, log_channel_id, transcript_channel_id, ticket_counter, options_json FROM ticket_panels WHERE id = ?",
                (panel_id,)
            )
            panel = await cur.fetchone()
            await cur.close()

            if not panel:
                await interaction.followup.send("❌ This ticket panel no longer exists in the database.", ephemeral=True)
                return

            # 3. Check for active open ticket (prevent spam)
            cur = await conn.execute(
                "SELECT channel_id FROM tickets WHERE guild_id = ? AND user_id = ? AND status = 'open'",
                (guild.id, user.id)
            )
            active_ticket = await cur.fetchone()
            await cur.close()

            if active_ticket:
                existing_chan = guild.get_channel(active_ticket["channel_id"])
                if existing_chan:
                    await interaction.followup.send(
                        f"❌ You already have an open ticket in {existing_chan.mention}! Please use or close it before opening another.",
                        ephemeral=True
                    )
                    return

            # 4. Per-Guild Sequential Ticket Numbering
            if not g_config:
                next_num = 1
                await conn.execute(
                    "INSERT INTO guild_ticket_config (guild_id, next_ticket_number, created_at) VALUES (?, 2, ?)",
                    (guild.id, datetime.now(timezone.utc).isoformat())
                )
            else:
                next_num = g_config["next_ticket_number"] or 1
                await conn.execute(
                    "UPDATE guild_ticket_config SET next_ticket_number = ? WHERE guild_id = ?",
                    (next_num + 1, guild.id)
                )
            await conn.commit()

            # Match selected category
            options = []
            if panel["options_json"]:
                try:
                    options = json.loads(panel["options_json"])
                except Exception:
                    options = []

            matched_opt = next((o for o in options if o.get("value") == category_val), None)
            if not matched_opt:
                matched_opt = {
                    "value": category_val,
                    "label": category_val.title(),
                    "emoji": "📩",
                    "category_id": panel["category_id"],
                    "role_id": panel["staff_role_id"],
                    "name_format": "ticket"
                }

        # 5. Resolve Target Open Category and Staff Role
        open_cat_id = matched_opt.get("category_id") or (g_config["open_category_id"] if g_config else None) or panel["category_id"]
        parent_cat = guild.get_channel(open_cat_id) if open_cat_id else None
        if not isinstance(parent_cat, discord.CategoryChannel):
            parent_cat = None

        staff_role_id = matched_opt.get("role_id") or (g_config["staff_role_id"] if g_config else None) or panel["staff_role_id"]
        staff_role = guild.get_role(staff_role_id) if staff_role_id else None

        # 6. Build Overwrite Permissions
        # Privacy guarantee: @everyone cannot view, creator & staff & bot have view & send
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                manage_channels=True,
                manage_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True
            )
        }
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True,
                manage_messages=True
            )

        # Clean Numeric Channel Name: 🎫・0001 (or ticket-0001)
        channel_name = f"🎫・{next_num:04d}"
        category_name = matched_opt.get("label", "Support")

        try:
            ticket_channel = await guild.create_text_channel(
                name=channel_name,
                category=parent_cat,
                overwrites=overwrites,
                topic=f"Ticket #{next_num:04d} | Category: {category_name} | Creator ID: {user.id}"
            )
        except discord.Forbidden:
            await interaction.followup.send("❌ I do not have permission to create channels in that category.", ephemeral=True)
            return
        except Exception as e:
            logger.exception("Failed to create ticket channel: %s", e)
            await interaction.followup.send(f"❌ Failed to create ticket channel: {e}", ephemeral=True)
            return

        # 7. Save ticket to DB
        created_time_iso = datetime.now(timezone.utc).isoformat()
        async with get_connection() as conn:
            cur = await conn.execute(
                """
                INSERT INTO tickets (guild_id, channel_id, user_id, panel_id, category, ticket_type, ticket_number, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?)
                """,
                (guild.id, ticket_channel.id, user.id, panel_id, category_name, category_val, next_num, created_time_iso)
            )
            ticket_id = cur.lastrowid
            await conn.commit()

        # 8. Post Welcome Embed and Controls
        emoji = matched_opt.get("emoji", "🎫")
        embed = discord.Embed(
            title=f"{emoji} {category_name} Ticket",
            description=(
                f"Welcome {user.mention}!\n\n"
                f"• **Category:** `{category_name}`\n"
                f"• **Ticket Number:** `#{next_num:04d}`\n"
                f"• **Support Role:** {staff_role.mention if staff_role else '*Default Staff*'}\n\n"
                f"Please explain your inquiry or complaint clearly.\nA staff member will assist you shortly."
            ),
            color=discord.Color.from_rgb(88, 101, 242)
        )
        set_ticket_footer(embed, self.bot, extra_text=f"Ticket #{next_num:04d}")

        ctrl_view = TicketControlView(ticket_id, is_closed=False)
        staff_ping = staff_role.mention if staff_role else ""
        await ticket_channel.send(content=f"{user.mention} {staff_ping}", embed=embed, view=ctrl_view)

        # 9. Send Notice to Log Channel if set
        log_channel_id = (g_config["log_channel_id"] if g_config else None) or panel["log_channel_id"]
        if log_channel_id:
            log_chan = guild.get_channel(log_channel_id)
            if isinstance(log_chan, discord.TextChannel):
                log_embed = discord.Embed(
                    title="🎫 Ticket Opened",
                    description=(
                        f"• **Ticket:** {ticket_channel.mention} (`#{next_num:04d}`)\n"
                        f"• **Creator:** {user.mention} (`{user.id}`)\n"
                        f"• **Category:** `{category_name}`\n"
                        f"• **Opened At:** <t:{int(datetime.now(timezone.utc).timestamp())}:f>"
                    ),
                    color=discord.Color.green()
                )
                set_ticket_footer(log_embed, self.bot)
                try:
                    await log_chan.send(embed=log_embed)
                except Exception:
                    pass

        await interaction.followup.send(f"✅ Ticket created! Please head over to {ticket_channel.mention}.", ephemeral=True)

    # -------------------------------------------------------------------------
    # Claim / Unclaim (Renaming with Mod Name + Ticket Number)
    # -------------------------------------------------------------------------
    async def claim_ticket(self, interaction: discord.Interaction, ticket_id: int):
        """Claim ticket for support staff member and rename channel to mod name along with ticket number."""
        user = getattr(interaction, "user", getattr(interaction, "author", None))
        if not user:
            return
        async with get_connection() as conn:
            cur = await conn.execute(
                """
                SELECT t.*, p.staff_role_id as p_staff, g.staff_role_id as g_staff, g.log_channel_id, p.log_channel_id as p_log
                FROM tickets t
                LEFT JOIN ticket_panels p ON t.panel_id = p.id
                LEFT JOIN guild_ticket_config g ON t.guild_id = g.guild_id
                WHERE t.id = ?
                """,
                (ticket_id,)
            )
            ticket = await cur.fetchone()
            await cur.close()

            if not ticket:
                if hasattr(interaction, "followup"):
                    await interaction.followup.send("❌ Ticket record not found.", ephemeral=True)
                elif hasattr(interaction, "send"):
                    await interaction.send("❌ Ticket record not found.", ephemeral=True)
                return

            staff_role_id = ticket["g_staff"] or ticket["p_staff"]
            if not await self._is_staff_or_owner(user, staff_role_id):
                if hasattr(interaction, "followup"):
                    await interaction.followup.send("❌ Only support staff or administrators can claim tickets.", ephemeral=True)
                elif hasattr(interaction, "send"):
                    await interaction.send("❌ Only support staff or administrators can claim tickets.", ephemeral=True)
                return

            if ticket["claimed_by"]:
                if ticket["claimed_by"] == user.id:
                    msg = "⚠️ You have already claimed this ticket."
                else:
                    mod_user = interaction.guild.get_member(ticket["claimed_by"])
                    mod_name = mod_user.mention if mod_user else f"<@{ticket['claimed_by']}>"
                    msg = f"⚠️ This ticket is already claimed by {mod_name} and cannot be changed or unclaimed."
                if hasattr(interaction, "followup"):
                    await interaction.followup.send(msg, ephemeral=True)
                elif hasattr(interaction, "send"):
                    await interaction.send(msg, ephemeral=True)
                return

            await conn.execute("UPDATE tickets SET claimed_by = ? WHERE id = ?", (user.id, ticket_id))
            await conn.commit()

        # Rename channel to mod name along with ticket number (e.g. divyam-7719 or oreo-15007)
        clean_mod_name = re.sub(r'[^a-zA-Z0-9_-]', '', user.display_name.lower().replace(' ', '-')).strip('-')[:15] or "mod"
        new_chan_name = f"{clean_mod_name}-{ticket['ticket_number']:04d}"
        if isinstance(interaction.channel, discord.TextChannel):
            await safe_edit_channel(interaction.channel, name=new_chan_name, reason="Ticket Claimed")

        embed = discord.Embed(
            title="👤 Ticket Claimed",
            description=f"This ticket has been claimed by {user.mention}.\nChannel renamed to **#{new_chan_name}**.\n\n*Use the `Rename ✏️` button below if you want to customize the channel name.*",
            color=discord.Color.blue()
        )
        set_ticket_footer(embed, self.bot)

        ctrl_view = TicketControlView(ticket_id, is_closed=(ticket["status"] == "closed"), claimed_by=user.id)
        await interaction.channel.send(embed=embed, view=ctrl_view)

        # Log event
        log_id = ticket["log_channel_id"] or ticket["p_log"]
        if log_id:
            log_chan = interaction.guild.get_channel(log_id)
            if isinstance(log_chan, discord.TextChannel):
                log_embed = discord.Embed(
                    title="👤 Ticket Claimed",
                    description=f"• **Ticket:** {interaction.channel.mention}\n• **Claimed By:** {user.mention}",
                    color=discord.Color.blue()
                )
                set_ticket_footer(log_embed, self.bot)
                try:
                    await log_chan.send(embed=log_embed)
                except Exception:
                    pass

    async def unclaim_ticket(self, interaction: discord.Interaction, ticket_id: int):
        """Unclaim is disabled: tickets cannot be unclaimed once claimed."""
        msg = "❌ Once claimed, tickets remain permanently assigned to the staff member and cannot be unclaimed."
        if hasattr(interaction, "followup"):
            await interaction.followup.send(msg, ephemeral=True)
        elif hasattr(interaction, "send"):
            await interaction.send(msg, ephemeral=True)

    # -------------------------------------------------------------------------
    # Close Flow (Close != Delete; Move to Closed Category; Rename closed-XXXX)
    # -------------------------------------------------------------------------
    async def prompt_close_ticket(self, interaction: discord.Interaction, ticket_id: int):
        """Prompt confirmation before closing a ticket."""
        embed = discord.Embed(
            title="🔒 Close this ticket?",
            description=(
                "Closing this ticket will lock the channel for normal users, generate a transcript, and archive it.\n\n"
                "*Note: Closing does NOT delete the channel. Staff can inspect, reopen, or permanently delete it later.*"
            ),
            color=discord.Color.orange()
        )
        set_ticket_footer(embed, self.bot)
        view = CloseConfirmView(ticket_id, self)
        if isinstance(interaction, discord.Interaction):
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=embed, view=view)
            else:
                await interaction.followup.send(embed=embed, view=view)
        else:
            await interaction.send(embed=embed, view=view)

    async def process_close_ticket(self, interaction: discord.Interaction, ticket_id: int):
        """Lock permissions for normal users, generate transcripts, move to closed category, rename closed-XXXX, and post closed controls."""
        channel = interaction.channel
        guild = interaction.guild
        if not isinstance(channel, discord.TextChannel) or not guild:
            return

        async with get_connection() as conn:
            cur = await conn.execute(
                """
                SELECT t.*, 
                       g.closed_category_id, g.transcript_channel_id as g_trans, g.log_channel_id as g_log,
                       p.log_channel_id as p_log, p.transcript_channel_id as p_trans
                FROM tickets t
                LEFT JOIN ticket_panels p ON t.panel_id = p.id
                LEFT JOIN guild_ticket_config g ON t.guild_id = g.guild_id
                WHERE t.id = ?
                """,
                (ticket_id,)
            )
            ticket = await cur.fetchone()
            await cur.close()

            if not ticket:
                await interaction.followup.send("❌ Ticket record not found.", ephemeral=True)
                return

            if ticket["status"] == "closed":
                await interaction.followup.send("⚠️ This ticket is already closed.", ephemeral=True)
                return

            close_time_iso = datetime.now(timezone.utc).isoformat()
            await conn.execute("UPDATE tickets SET status = 'closed', closed_at = ? WHERE id = ?", (close_time_iso, ticket_id))
            await conn.commit()

        opener = guild.get_member(ticket["user_id"])
        claimed_user = guild.get_member(ticket["claimed_by"]) if ticket["claimed_by"] else None

        # Lock channel permissions for ticket creator (cannot send messages anymore)
        if opener:
            try:
                await channel.set_permissions(opener, send_messages=False, read_message_history=True, view_channel=True)
            except Exception:
                pass

        # Move channel to Closed Category & rename to closed-0001 (matching closed-2657 in screenshot)
        closed_chan_name = f"closed-{ticket['ticket_number']:04d}"
        closed_cat_id = ticket["closed_category_id"]
        closed_cat = guild.get_channel(closed_cat_id) if closed_cat_id else None
        if isinstance(closed_cat, discord.CategoryChannel):
            await safe_edit_channel(channel, name=closed_chan_name, category=closed_cat, reason="Ticket Closed")
        else:
            await safe_edit_channel(channel, name=closed_chan_name, reason="Ticket Closed")

        # Generate HTML transcript
        category_name = ticket["category"] or "Support"
        creator_str = f"{opener.display_name} ({ticket['user_id']})" if opener else f"User {ticket['user_id']}"
        claimed_str = claimed_user.display_name if claimed_user else "Unclaimed"
        
        html_buf = await generate_html_transcript(
            channel=channel,
            category_name=category_name,
            creator_name=creator_str,
            claimed_name=claimed_str,
            created_time=ticket["created_at"]
        )

        # 1. Send Transcript to Configured Transcript Channel (All transcripts in one channel)
        trans_chan_id = ticket["g_trans"] or ticket["p_trans"] or ticket["g_log"] or ticket["p_log"]
        if trans_chan_id:
            trans_chan = guild.get_channel(trans_chan_id)
            if isinstance(trans_chan, discord.TextChannel):
                t_embed = discord.Embed(
                    title="📑 Ticket Closed & Archived",
                    description=(
                        f"• **Ticket:** {channel.name}\n"
                        f"• **User:** {creator_str}\n"
                        f"• **Category:** {category_name}\n"
                        f"• **Claimed By:** {claimed_str}\n"
                        f"• **Closed By:** {interaction.user.mention}\n"
                        f"• **Closed At:** <t:{int(datetime.now(timezone.utc).timestamp())}:F>"
                    ),
                    color=discord.Color.dark_grey()
                )
                set_ticket_footer(t_embed, self.bot)
                try:
                    html_buf.seek(0)
                    discord_file = discord.File(html_buf, filename=f"transcript-{channel.name}.html")
                    await trans_chan.send(embed=t_embed, file=discord_file)
                except Exception as e:
                    logger.debug("Failed sending transcript file to log channel: %s", e)

        # 2. Post Closed Controls Embed inside the ticket channel
        closed_embed = discord.Embed(
            title="🔒 Ticket Closed",
            description=(
                f"Ticket was closed by {interaction.user.mention}.\n\n"
                "Staff members can use the actions below to reopen the ticket or permanently delete the channel."
            ),
            color=discord.Color.red()
        )
        closed_view = TicketControlView(ticket_id, is_closed=True, claimed_by=ticket["claimed_by"])
        await channel.send(embed=closed_embed, view=closed_view)

    async def reopen_ticket(self, interaction: discord.Interaction, ticket_id: int):
        """Reopen a closed ticket: restore creator permissions, move back to Open Category, restore channel name."""
        channel = interaction.channel
        guild = interaction.guild
        if not isinstance(channel, discord.TextChannel) or not guild:
            return

        async with get_connection() as conn:
            cur = await conn.execute(
                """
                SELECT t.*, 
                       g.open_category_id, g.log_channel_id,
                       p.category_id as p_open, p.options_json as p_opts, p.log_channel_id as p_log
                FROM tickets t
                LEFT JOIN ticket_panels p ON t.panel_id = p.id
                LEFT JOIN guild_ticket_config g ON t.guild_id = g.guild_id
                WHERE t.id = ?
                """,
                (ticket_id,)
            )
            ticket = await cur.fetchone()
            await cur.close()

            if not ticket:
                await interaction.followup.send("❌ Ticket record not found.", ephemeral=True)
                return

            if ticket["status"] != "closed":
                await interaction.followup.send("⚠️ This ticket is not closed.", ephemeral=True)
                return

            await conn.execute("UPDATE tickets SET status = 'open', closed_at = NULL WHERE id = ?", (ticket_id,))
            await conn.commit()

        # Restore permissions for creator
        opener = guild.get_member(ticket["user_id"])
        if opener:
            try:
                await channel.set_permissions(opener, send_messages=True, read_message_history=True, view_channel=True, attach_files=True, embed_links=True)
            except Exception:
                pass

        # Restore channel name (mod name if claimed or ticket-0001)
        if ticket["claimed_by"]:
            mod_user = guild.get_member(ticket["claimed_by"])
            clean_mod_name = re.sub(r'[^a-zA-Z0-9_-]', '', mod_user.display_name.lower().replace(' ', '-')).strip('-')[:15] if mod_user else "mod"
            restored_name = f"{clean_mod_name}-{ticket['ticket_number']:04d}"
        else:
            restored_name = f"ticket-{ticket['ticket_number']:04d}"

        # Option-level category check
        opt_cat_id = None
        if ticket["p_opts"]:
            try:
                opts = json.loads(ticket["p_opts"])
                for o in opts:
                    if o.get("value") == ticket["ticket_type"] or o.get("label") == ticket["category"]:
                        if o.get("category_id"):
                            opt_cat_id = int(o["category_id"])
                            break
            except Exception:
                pass

        # Move back to Open Category
        open_cat_id = opt_cat_id or ticket["open_category_id"] or ticket["p_open"]
        open_cat = guild.get_channel(open_cat_id) if open_cat_id else None
        if isinstance(open_cat, discord.CategoryChannel):
            await safe_edit_channel(channel, name=restored_name, category=open_cat, reason="Ticket Reopened")
        else:
            await safe_edit_channel(channel, name=restored_name, reason="Ticket Reopened")

        reopen_embed = discord.Embed(
            title="🔓 Ticket Reopened",
            description=f"Ticket has been reopened by {interaction.user.mention}.\nChannel name restored to **#{restored_name}**.",
            color=discord.Color.green()
        )
        set_ticket_footer(reopen_embed, self.bot)

        ctrl_view = TicketControlView(ticket_id, is_closed=False, claimed_by=ticket["claimed_by"])
        await channel.send(embed=reopen_embed, view=ctrl_view)

        # Log reopen
        log_id = ticket["log_channel_id"] or ticket["p_log"]
        if log_id:
            log_chan = guild.get_channel(log_id)
            if isinstance(log_chan, discord.TextChannel):
                log_embed = discord.Embed(
                    title="🔓 Ticket Reopened",
                    description=f"• **Ticket:** {channel.mention}\n• **Reopened By:** {interaction.user.mention}",
                    color=discord.Color.green()
                )
                set_ticket_footer(log_embed, self.bot)
                try:
                    await log_chan.send(embed=log_embed)
                except Exception:
                    pass

    async def prompt_delete_ticket(self, interaction: discord.Interaction, ticket_id: int):
        """Prompt confirmation before permanently deleting a ticket channel."""
        embed = discord.Embed(
            title="🗑️ Delete this ticket?",
            description="Are you sure you want to permanently delete this ticket channel? This action cannot be undone.",
            color=discord.Color.red()
        )
        set_ticket_footer(embed, self.bot)
        view = DeleteConfirmView(ticket_id, self)
        if isinstance(interaction, discord.Interaction):
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=embed, view=view)
            else:
                await interaction.followup.send(embed=embed, view=view)
        else:
            await interaction.send(embed=embed, view=view)

    async def process_delete_ticket(self, interaction: discord.Interaction, ticket_id: int):
        """Delete ticket channel with 5-second countdown."""
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            return

        embed = discord.Embed(
            title="🗑️ Deleting Ticket Channel",
            description="This channel will be permanently deleted in **5 seconds**...",
            color=discord.Color.dark_red()
        )
        set_ticket_footer(embed, self.bot)
        await channel.send(embed=embed)

        await asyncio.sleep(5)
        try:
            await channel.delete(reason=f"Ticket deleted by {interaction.user} ({interaction.user.id})")
        except Exception as e:
            logger.warning("Failed to delete ticket channel %s: %s", channel.id, e)

    # -------------------------------------------------------------------------
    # Transcripts
    # -------------------------------------------------------------------------
    async def send_transcript(self, interaction: discord.Interaction, ticket_id: int):
        """Generate and upload HTML transcript to current channel."""
        channel = interaction.channel
        guild = interaction.guild
        if not isinstance(channel, discord.TextChannel) or not guild:
            return

        async with get_connection() as conn:
            cur = await conn.execute(
                """
                SELECT t.* FROM tickets t WHERE t.id = ?
                """,
                (ticket_id,)
            )
            ticket = await cur.fetchone()
            await cur.close()

        category_name = ticket["category"] if ticket else "Support"
        creator_name = f"<@{ticket['user_id']}>" if ticket else "Unknown"
        claimed_name = f"<@{ticket['claimed_by']}>" if ticket and ticket["claimed_by"] else "Unclaimed"
        created_time = ticket["created_at"] if ticket else None

        html_buf = await generate_html_transcript(
            channel=channel,
            category_name=category_name,
            creator_name=creator_name,
            claimed_name=claimed_name,
            created_time=created_time
        )
        file = discord.File(html_buf, filename=f"transcript-{channel.name}.html")

        embed = discord.Embed(
            title="📜 Ticket Transcript",
            description=f"Generated HTML transcript for **#{channel.name}**.",
            color=discord.Color.purple(),
            timestamp=datetime.now(timezone.utc)
        )
        set_ticket_footer(embed, self.bot)
        await channel.send(embed=embed, file=file)
        await interaction.followup.send("✅ Transcript generated and sent!", ephemeral=True)

    # -------------------------------------------------------------------------
    # Commands & Configuration
    # -------------------------------------------------------------------------

    @commands.group(name="ticket", invoke_without_command=True)
    @commands.guild_only()
    async def ticket_group(self, ctx: commands.Context):
        """Modern Ticket System management commands."""
        embed = discord.Embed(
            title="🎫 Helix Ticket System",
            description=(
                "**Server Setup & Embed Builder**:\n"
                "• `!ticket builder` — Launch the interactive Embed Builder to design & deploy custom ticket panels\n"
                "• `!ticket setup` — Configure Open/Closed categories, support role & transcript channel\n"
                "• `!ticket config` — View current server ticket configuration & next number\n"
                "• `!ticket panel` — Send the default Support & Complaints ticket dropdown panel\n\n"
                "**Ticket Actions**:\n"
                "• `!ticket close` — Close ticket & lock for users *(Renames to `closed-XXXX` & archives)*\n"
                "• `!ticket reopen` — Reopen a closed ticket *(Restores user access & channel name)*\n"
                "• `!ticket delete` — Permanently delete this ticket channel\n"
                "• `!ticket claim` — Claim ticket *(Assigns staff & renames to `modname-XXXX`)*\n"
                "• `!ticket rename <name>` — Rename ticket channel\n"
                "• `!ticket transcript` — Export an interactive HTML transcript\n"
                "• `!ticket add <@user>` — Add collaborator to this ticket\n"
                "• `!ticket remove <@user>` — Remove collaborator from ticket\n"
            ),
            color=discord.Color.from_rgb(88, 101, 242)
        )
        set_ticket_footer(embed, self.bot)
        await ctx.send(embed=embed)

    @ticket_group.command(name="builder", aliases=["build", "embedbuilder", "panelbuilder"])
    @commands.guild_only()
    async def ticket_builder_cmd(self, ctx: commands.Context):
        """Interactive visual Embed Builder to customize and deploy ticket panels."""
        if not await self._is_staff_or_owner(ctx.author):
            await ctx.send("❌ You need **Manage Server** permission to build ticket panels.", ephemeral=True)
            return

        builder_view = TicketPanelBuilderView(self, ctx.author.id)
        preview_embed = builder_view.render_preview()
        await ctx.send(
            content="🎨 **Ticket Panel Embed Builder**\nUse the buttons below to customize your panel's title, message, color, image, and categories in real-time, then click **Deploy Panel 🚀** to post it to any channel!",
            embed=preview_embed,
            view=builder_view
        )

    @ticket_group.command(name="setup")
    @commands.guild_only()
    async def ticket_setup_cmd(
        self,
        ctx: commands.Context,
        open_category: Optional[discord.CategoryChannel] = None,
        closed_category: Optional[discord.CategoryChannel] = None,
        support_role: Optional[discord.Role] = None,
        transcript_channel: Optional[discord.TextChannel] = None,
        log_channel: Optional[discord.TextChannel] = None
    ):
        """Configure server ticket categories, staff role, and transcript logging channel."""
        if not await self._is_staff_or_owner(ctx.author):
            await ctx.send("❌ You need **Manage Server** permission to configure tickets.", ephemeral=True)
            return

        async with get_connection() as conn:
            cur = await conn.execute("SELECT * FROM guild_ticket_config WHERE guild_id = ?", (ctx.guild.id,))
            exists = await cur.fetchone()
            await cur.close()

            if not exists:
                await conn.execute(
                    """
                    INSERT INTO guild_ticket_config (guild_id, open_category_id, closed_category_id, staff_role_id, transcript_channel_id, log_channel_id, next_ticket_number, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, 1, ?)
                    """,
                    (
                        ctx.guild.id,
                        open_category.id if open_category else None,
                        closed_category.id if closed_category else (open_category.id if open_category else None),
                        support_role.id if support_role else None,
                        transcript_channel.id if transcript_channel else (log_channel.id if log_channel else None),
                        log_channel.id if log_channel else None,
                        datetime.now(timezone.utc).isoformat()
                    )
                )
            else:
                await conn.execute(
                    """
                    UPDATE guild_ticket_config SET
                        open_category_id = COALESCE(?, open_category_id),
                        closed_category_id = COALESCE(?, closed_category_id),
                        staff_role_id = COALESCE(?, staff_role_id),
                        transcript_channel_id = COALESCE(?, transcript_channel_id),
                        log_channel_id = COALESCE(?, log_channel_id)
                    WHERE guild_id = ?
                    """,
                    (
                        open_category.id if open_category else None,
                        closed_category.id if closed_category else None,
                        support_role.id if support_role else None,
                        transcript_channel.id if transcript_channel else None,
                        log_channel.id if log_channel else None,
                        ctx.guild.id
                    )
                )
            await conn.commit()

        embed = discord.Embed(
            title="🎫 Ticket System Setup Complete",
            description=(
                f"Configuration saved for **{ctx.guild.name}**:\n\n"
                f"• **Open Tickets Category**: {open_category.mention if open_category else '*Default / Root*'}\n"
                f"• **Closed Tickets Category**: {closed_category.mention if closed_category else (open_category.mention if open_category else '*Same as Open*')}\n"
                f"• **Support Role**: {support_role.mention if support_role else '*Default Staff*'}\n"
                f"• **Transcripts Channel**: {transcript_channel.mention if transcript_channel else '*None*'}\n"
                f"• **Logs Channel**: {log_channel.mention if log_channel else '*None*'}\n\n"
                f"Run `!ticket panel` or `!ticket builder` in your support channel to deploy your interactive panel!"
            ),
            color=discord.Color.green()
        )
        set_ticket_footer(embed, self.bot)
        await ctx.send(embed=embed)

    @ticket_group.command(name="config")
    @commands.guild_only()
    async def ticket_config_cmd(self, ctx: commands.Context):
        """View current ticket configuration for this server."""
        async with get_connection() as conn:
            cur = await conn.execute("SELECT * FROM guild_ticket_config WHERE guild_id = ?", (ctx.guild.id,))
            cfg = await cur.fetchone()
            await cur.close()

        if not cfg:
            await ctx.send("ℹ️ Ticket system has not been configured for this server yet. Run `!ticket setup` to configure it!", ephemeral=True)
            return

        open_cat = ctx.guild.get_channel(cfg["open_category_id"]) if cfg["open_category_id"] else None
        closed_cat = ctx.guild.get_channel(cfg["closed_category_id"]) if cfg["closed_category_id"] else None
        staff_role = ctx.guild.get_role(cfg["staff_role_id"]) if cfg["staff_role_id"] else None
        trans_chan = ctx.guild.get_channel(cfg["transcript_channel_id"]) if cfg["transcript_channel_id"] else None
        log_chan = ctx.guild.get_channel(cfg["log_channel_id"]) if cfg["log_channel_id"] else None

        embed = discord.Embed(
            title="⚙️ Ticket System Configuration",
            description=(
                f"• **Next Ticket Number**: `#{cfg['next_ticket_number'] or 1:04d}`\n"
                f"• **Open Category**: {open_cat.mention if open_cat else '*Default*'}\n"
                f"• **Closed Category**: {closed_cat.mention if closed_cat else '*Same as Open*'}\n"
                f"• **Support Role**: {staff_role.mention if staff_role else '*Default Staff*'}\n"
                f"• **Transcripts Channel**: {trans_chan.mention if trans_chan else '*Not Configured*'}\n"
                f"• **Logs Channel**: {log_chan.mention if log_chan else '*Not Configured*'}"
            ),
            color=discord.Color.blurple()
        )
        set_ticket_footer(embed, self.bot)
        await ctx.send(embed=embed)

    @ticket_group.command(name="panel")
    @commands.guild_only()
    async def ticket_panel_cmd(
        self,
        ctx: commands.Context,
        category: Optional[discord.CategoryChannel] = None,
        staff_role: Optional[discord.Role] = None,
        log_channel: Optional[discord.TextChannel] = None,
        *,
        title: Optional[str] = "Support Center"
    ):
        """Send the clean Support & Complaints dropdown ticket panel."""
        if not await self._is_staff_or_owner(ctx.author):
            await ctx.send("❌ You need **Manage Server** permission to post ticket panels.", ephemeral=True)
            return

        options = [
            {"value": "support", "label": "Support", "emoji": "🛠️", "description": "General assistance and technical help"},
            {"value": "complaints", "label": "Complaints", "emoji": "⚠️", "description": "Submit a server or player complaint"},
            {"value": "billing", "label": "Billing", "emoji": "💳", "description": "Payment issues, store inquiries & donations"},
            {"value": "partnership", "label": "Partnership", "emoji": "🤝", "description": "Server collaborations and sponsorships"}
        ]

        embed = self._render_panel_embed(
            title=title,
            description="Need help or want to submit a complaint?\nSelect a category below to create a private ticket.",
            options=options
        )
        panel_msg = await ctx.send(embed=embed)

        async with get_connection() as conn:
            cur = await conn.execute(
                """
                INSERT INTO ticket_panels (guild_id, channel_id, message_id, title, description, category_id, staff_role_id, log_channel_id, ticket_counter, options_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
                """,
                (
                    ctx.guild.id,
                    ctx.channel.id,
                    panel_msg.id,
                    title,
                    "Need help or want to submit a complaint?\nSelect a category below to create a private ticket.",
                    category.id if category else None,
                    staff_role.id if staff_role else None,
                    log_channel.id if log_channel else None,
                    json.dumps(options),
                    datetime.now(timezone.utc).isoformat()
                )
            )
            panel_id = cur.lastrowid
            await conn.commit()

        panel_view = TicketPanelView(panel_id, options)
        await panel_msg.edit(view=panel_view)

    @ticket_group.command(name="close")
    @commands.guild_only()
    async def ticket_close(self, ctx: commands.Context):
        """Close the current ticket channel for normal users."""
        async with get_connection() as conn:
            cur = await conn.execute("SELECT id FROM tickets WHERE channel_id = ?", (ctx.channel.id,))
            row = await cur.fetchone()
            await cur.close()

        if not row:
            await ctx.send("❌ This channel is not an active ticket channel.", ephemeral=True)
            return

        mock_inter = ctx.interaction or ctx
        await self.prompt_close_ticket(mock_inter, row["id"])

    @ticket_group.command(name="reopen")
    @commands.guild_only()
    async def ticket_reopen_cmd(self, ctx: commands.Context):
        """Reopen a closed ticket."""
        async with get_connection() as conn:
            cur = await conn.execute("SELECT id FROM tickets WHERE channel_id = ?", (ctx.channel.id,))
            row = await cur.fetchone()
            await cur.close()

        if not row:
            await ctx.send("❌ This channel is not a ticket channel.", ephemeral=True)
            return

        mock_inter = ctx.interaction or ctx
        await self.reopen_ticket(mock_inter, row["id"])

    @ticket_group.command(name="delete")
    @commands.guild_only()
    async def ticket_delete_cmd(self, ctx: commands.Context):
        """Delete the current ticket channel permanently."""
        async with get_connection() as conn:
            cur = await conn.execute("SELECT id FROM tickets WHERE channel_id = ?", (ctx.channel.id,))
            row = await cur.fetchone()
            await cur.close()

        if not row:
            await ctx.send("❌ This channel is not a ticket channel.", ephemeral=True)
            return

        mock_inter = ctx.interaction or ctx
        await self.prompt_delete_ticket(mock_inter, row["id"])

    @ticket_group.command(name="claim")
    @commands.guild_only()
    async def ticket_claim_cmd(self, ctx: commands.Context):
        """Claim the current ticket as support staff."""
        async with get_connection() as conn:
            cur = await conn.execute("SELECT id FROM tickets WHERE channel_id = ?", (ctx.channel.id,))
            row = await cur.fetchone()
            await cur.close()

        if not row:
            await ctx.send("❌ This channel is not a ticket channel.", ephemeral=True)
            return

        mock_inter = ctx.interaction or ctx
        await self.claim_ticket(mock_inter, row["id"])

    @ticket_group.command(name="unclaim")
    @commands.guild_only()
    async def ticket_unclaim_cmd(self, ctx: commands.Context):
        """Unclaim is disabled: tickets cannot be unclaimed once claimed."""
        await ctx.send("❌ Once claimed, tickets remain permanently assigned to the staff member and cannot be unclaimed. You can rename the channel using `!ticket rename <name>`.", ephemeral=True)

    @ticket_group.command(name="transcript")
    @commands.guild_only()
    async def ticket_transcript_cmd(self, ctx: commands.Context):
        """Generate and upload an interactive HTML transcript."""
        async with get_connection() as conn:
            cur = await conn.execute("SELECT id FROM tickets WHERE channel_id = ?", (ctx.channel.id,))
            row = await cur.fetchone()
            await cur.close()

        if not row:
            await ctx.send("❌ This command can only be used inside a ticket channel.", ephemeral=True)
            return

        mock_inter = ctx.interaction or ctx
        await self.send_transcript(mock_inter, row["id"])

    @ticket_group.command(name="add", aliases=["add-user"])
    @commands.guild_only()
    async def ticket_add_user(self, ctx: commands.Context, member: discord.Member):
        """Add a collaborator or member to this ticket channel."""
        async with get_connection() as conn:
            cur = await conn.execute("SELECT id FROM tickets WHERE channel_id = ?", (ctx.channel.id,))
            row = await cur.fetchone()
            await cur.close()

        if not row:
            await ctx.send("❌ This command must be run inside an active ticket channel.", ephemeral=True)
            return

        if isinstance(ctx.channel, discord.TextChannel):
            await ctx.channel.set_permissions(
                member,
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True
            )
            embed = discord.Embed(
                description=f"➕ Added {member.mention} to this ticket channel.",
                color=discord.Color.green()
            )
            set_ticket_footer(embed, self.bot)
            await ctx.send(embed=embed)

    @ticket_group.command(name="remove", aliases=["remove-user"])
    @commands.guild_only()
    async def ticket_remove_user(self, ctx: commands.Context, member: discord.Member):
        """Remove a member from this ticket channel."""
        async with get_connection() as conn:
            cur = await conn.execute("SELECT id FROM tickets WHERE channel_id = ?", (ctx.channel.id,))
            row = await cur.fetchone()
            await cur.close()

        if not row:
            await ctx.send("❌ This command must be run inside an active ticket channel.", ephemeral=True)
            return

        if isinstance(ctx.channel, discord.TextChannel):
            await ctx.channel.set_permissions(member, overwrite=None)
            embed = discord.Embed(
                description=f"➖ Removed {member.mention} from this ticket channel.",
                color=discord.Color.red()
            )
            set_ticket_footer(embed, self.bot)
            await ctx.send(embed=embed)

    @ticket_group.command(name="rename")
    @commands.guild_only()
    async def ticket_rename_cmd(self, ctx: commands.Context, *, new_name: str):
        """Rename the ticket channel."""
        async with get_connection() as conn:
            cur = await conn.execute("SELECT id FROM tickets WHERE channel_id = ?", (ctx.channel.id,))
            row = await cur.fetchone()
            await cur.close()

        if not row:
            await ctx.send("❌ This channel is not a ticket channel.", ephemeral=True)
            return

        if isinstance(ctx.channel, discord.TextChannel):
            clean_name = new_name.strip().lower().replace(" ", "-")[:100]
            success = await safe_edit_channel(ctx.channel, name=clean_name, reason=f"Ticket Renamed by {ctx.author.display_name}")
            if success:
                await ctx.send(f"✏️ Ticket channel renamed to **#{clean_name}**.")
            else:
                await ctx.send(f"✏️ Channel rename queued for **#{clean_name}** *(Discord rate limit: max 2 renames per 10 min)*.")

    # -------------------------------------------------------------------------
    # Panel Customization Subgroup
    # -------------------------------------------------------------------------
    @ticket_group.group(name="panel-config", aliases=["panelconfig", "pconfig"], invoke_without_command=True)
    @commands.guild_only()
    async def panel_subgroup(self, ctx: commands.Context):
        """Customize ticket panel categories and settings."""
        await ctx.send_help(ctx.command)

    @panel_subgroup.command(name="addoption")
    @commands.guild_only()
    async def panel_addoption(
        self,
        ctx: commands.Context,
        message_id: str,
        emoji: str,
        label: str,
        description: str,
        category: Optional[discord.CategoryChannel] = None,
        staff_role: Optional[discord.Role] = None,
        name_prefix: Optional[str] = "ticket"
    ):
        """Add a custom category option to an existing panel."""
        if not await self._is_staff_or_owner(ctx.author):
            await ctx.send("❌ You need **Manage Server** permission to edit ticket panels.", ephemeral=True)
            return

        try:
            m_id = int(message_id.strip())
        except ValueError:
            await ctx.send("❌ Invalid panel message ID provided.", ephemeral=True)
            return

        async with get_connection() as conn:
            cur = await conn.execute(
                "SELECT id, channel_id, title, description, category_id, staff_role_id, options_json FROM ticket_panels WHERE message_id = ? AND guild_id = ?",
                (m_id, ctx.guild.id)
            )
            panel = await cur.fetchone()
            await cur.close()

            if not panel:
                await ctx.send("❌ Ticket panel not found with that message ID in this server.", ephemeral=True)
                return

            options = []
            if panel["options_json"]:
                try:
                    options = json.loads(panel["options_json"])
                except Exception:
                    options = []

            val_slug = label.lower().replace(" ", "_")[:30]
            new_opt = {
                "value": val_slug,
                "label": label,
                "emoji": emoji,
                "description": description,
                "category_id": category.id if category else panel["category_id"],
                "role_id": staff_role.id if staff_role else panel["staff_role_id"],
                "name_format": name_prefix or "ticket"
            }
            options.append(new_opt)

            await conn.execute("UPDATE ticket_panels SET options_json = ? WHERE id = ?", (json.dumps(options), panel["id"]))
            await conn.commit()

        panel_chan = ctx.guild.get_channel(panel["channel_id"])
        if isinstance(panel_chan, discord.TextChannel):
            try:
                msg = await panel_chan.fetch_message(m_id)
                new_embed = self._render_panel_embed(panel["title"], panel["description"], options)
                new_view = TicketPanelView(panel["id"], options)
                await msg.edit(embed=new_embed, view=new_view)
            except Exception as e:
                logger.warning("Failed to edit panel message: %s", e)

        await ctx.send(
            f"✅ Added category option **{emoji} {label}** to panel `{m_id}`!\n"
            f"• **Destination Category**: {category.mention if category else '*Default*'}\n"
            f"• **Support Role**: {staff_role.mention if staff_role else '*Default Staff*'}\n"
            f"• **Channel Prefix**: `{name_prefix}`",
            ephemeral=True
        )

    @panel_subgroup.command(name="removeoption")
    @commands.guild_only()
    async def panel_removeoption(self, ctx: commands.Context, message_id: str, *, label: str):
        """Remove a category option from a panel by its name."""
        if not await self._is_staff_or_owner(ctx.author):
            await ctx.send("❌ You need **Manage Server** permission to edit ticket panels.", ephemeral=True)
            return

        try:
            m_id = int(message_id.strip())
        except ValueError:
            await ctx.send("❌ Invalid message ID.", ephemeral=True)
            return

        async with get_connection() as conn:
            cur = await conn.execute(
                "SELECT id, channel_id, title, description, options_json FROM ticket_panels WHERE message_id = ? AND guild_id = ?",
                (m_id, ctx.guild.id)
            )
            panel = await cur.fetchone()
            await cur.close()

            if not panel:
                await ctx.send("❌ Ticket panel not found.", ephemeral=True)
                return

            options = []
            if panel["options_json"]:
                try:
                    options = json.loads(panel["options_json"])
                except Exception:
                    options = []

            original_len = len(options)
            options = [o for o in options if o.get("label", "").lower() != label.strip().lower() and o.get("value", "").lower() != label.strip().lower()]

            if len(options) == original_len:
                await ctx.send(f"❌ Option matching `{label}` was not found on this panel.", ephemeral=True)
                return

            await conn.execute("UPDATE ticket_panels SET options_json = ? WHERE id = ?", (json.dumps(options), panel["id"]))
            await conn.commit()

        panel_chan = ctx.guild.get_channel(panel["channel_id"])
        if isinstance(panel_chan, discord.TextChannel):
            try:
                msg = await panel_chan.fetch_message(m_id)
                new_embed = self._render_panel_embed(panel["title"], panel["description"], options)
                new_view = TicketPanelView(panel["id"], options)
                await msg.edit(embed=new_embed, view=new_view)
            except Exception as e:
                logger.warning("Failed to edit panel message: %s", e)

        await ctx.send(f"✅ Removed option `{label}` from panel `{m_id}`.", ephemeral=True)

    @panel_subgroup.command(name="editoption")
    @commands.guild_only()
    async def panel_editoption(
        self,
        ctx: commands.Context,
        message_id: str,
        target_label: str,
        emoji: str,
        new_label: str,
        *,
        description: Optional[str] = ""
    ):
        """Edit an existing category option on a deployed panel."""
        if not await self._is_staff_or_owner(ctx.author):
            await ctx.send("❌ You need **Manage Server** permission to edit ticket panels.", ephemeral=True)
            return

        try:
            m_id = int(message_id.strip())
        except ValueError:
            await ctx.send("❌ Invalid message ID.", ephemeral=True)
            return

        async with get_connection() as conn:
            cur = await conn.execute(
                "SELECT id, channel_id, title, description, options_json FROM ticket_panels WHERE message_id = ? AND guild_id = ?",
                (m_id, ctx.guild.id)
            )
            panel = await cur.fetchone()
            await cur.close()

            if not panel:
                await ctx.send("❌ Ticket panel not found with that message ID.", ephemeral=True)
                return

            options = []
            if panel["options_json"]:
                try:
                    options = json.loads(panel["options_json"])
                except Exception:
                    options = []

            found = False
            for opt in options:
                if opt.get("label", "").lower() == target_label.strip().lower() or opt.get("value", "").lower() == target_label.strip().lower():
                    opt["emoji"] = emoji
                    opt["label"] = new_label
                    opt["description"] = description or ""
                    opt["value"] = new_label.lower().replace(" ", "_")[:30]
                    found = True
                    break

            if not found:
                await ctx.send(f"❌ Option matching `{target_label}` was not found on this panel.", ephemeral=True)
                return

            await conn.execute("UPDATE ticket_panels SET options_json = ? WHERE id = ?", (json.dumps(options), panel["id"]))
            await conn.commit()

        panel_chan = ctx.guild.get_channel(panel["channel_id"])
        if isinstance(panel_chan, discord.TextChannel):
            try:
                msg = await panel_chan.fetch_message(m_id)
                new_embed = self._render_panel_embed(panel["title"], panel["description"], options)
                new_view = TicketPanelView(panel["id"], options)
                await msg.edit(embed=new_embed, view=new_view)
            except Exception as e:
                logger.warning("Failed to edit panel message: %s", e)

        await ctx.send(f"✅ Updated category option to **{emoji} {new_label}** on panel `{m_id}`.", ephemeral=True)

    @ticket_group.command(name="deploy")
    @commands.guild_only()
    async def ticket_deploy_cmd(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        """Deploy a ticket support panel directly to a channel."""
        if not await self._is_staff_or_owner(ctx.author):
            await ctx.send("❌ You need **Manage Server** permission to deploy ticket panels.", ephemeral=True)
            return

        target_channel = channel or ctx.channel
        if not isinstance(target_channel, discord.TextChannel):
            await ctx.send("❌ Target channel must be a text channel.", ephemeral=True)
            return

        panel_id, msg_id = await self.deploy_panel_direct(
            guild=ctx.guild,
            channel=target_channel,
            title="Support Center",
            description="Need assistance, have questions, or want to submit a report?\nSelect the appropriate department below to open a private ticket with our team.",
            options=DEFAULT_TICKET_OPTIONS,
            color_hex="#5865F2"
        )
        await ctx.send(f"✅ **Ticket Panel Deployed!**\nPosted to {target_channel.mention} with Panel ID `#{panel_id}` (Message ID `{msg_id}`).", ephemeral=True)

    @ticket_group.command(name="listpanels", aliases=["panels", "list"])
    @commands.guild_only()
    async def ticket_list_panels_cmd(self, ctx: commands.Context):
        """List all active ticket panels deployed in this server."""
        if not await self._is_staff_or_owner(ctx.author):
            await ctx.send("❌ You need **Manage Server** permission to view ticket panels.", ephemeral=True)
            return

        async with get_connection() as conn:
            cur = await conn.execute("SELECT id, channel_id, message_id, title, created_at FROM ticket_panels WHERE guild_id = ? ORDER BY id DESC", (ctx.guild.id,))
            panels = await cur.fetchall()
            await cur.close()

        if not panels:
            await ctx.send("ℹ️ No ticket panels deployed yet. Use `!ticket builder` or `!ticket deploy #channel` to create one!", ephemeral=True)
            return

        lines = []
        for p in panels:
            ch = ctx.guild.get_channel(p["channel_id"])
            ch_mention = ch.mention if ch else f"`#{p['channel_id']}`"
            lines.append(f"• **ID #{p['id']}** — **{p['title']}** in {ch_mention} (Msg: `{p['message_id']}`)")

        embed = discord.Embed(
            title="🎫 Deployed Ticket Panels",
            description="\n".join(lines),
            color=discord.Color.from_rgb(88, 101, 242)
        )
        set_ticket_footer(embed, self.bot)
        await ctx.send(embed=embed)

    @ticket_group.command(name="deletepanel", aliases=["removepanel"])
    @commands.guild_only()
    async def ticket_delete_panel_cmd(self, ctx: commands.Context, panel_or_message_id: int):
        """Delete a ticket panel from both Discord and the database."""
        if not await self._is_staff_or_owner(ctx.author):
            await ctx.send("❌ You need **Manage Server** permission to delete ticket panels.", ephemeral=True)
            return

        success = await self.delete_panel_direct(panel_or_message_id, ctx.guild)
        if success:
            await ctx.send(f"✅ Ticket panel `{panel_or_message_id}` successfully removed.", ephemeral=True)
        else:
            await ctx.send(f"❌ Ticket panel with ID/Message `{panel_or_message_id}` was not found.", ephemeral=True)

    # -------------------------------------------------------------------------
    # Core Direct Operations (Shared by Discord Commands & Web Dashboard)
    # -------------------------------------------------------------------------
    async def deploy_panel_direct(
        self,
        guild: discord.Guild,
        channel: discord.TextChannel,
        title: str,
        description: str,
        options: List[Dict[str, Any]],
        color_hex: str = "#5865F2",
        image_url: Optional[str] = None
    ) -> tuple[int, int]:
        """Direct deploy method callable by both Discord Commands and Web Dashboard."""
        try:
            hex_val = int(color_hex.replace("#", ""), 16)
            color = discord.Color(hex_val)
        except Exception:
            color = discord.Color.from_rgb(88, 101, 242)

        embed = discord.Embed(
            title=f"🎫 {title}",
            description=description,
            color=color
        )
        if image_url:
            embed.set_image(url=image_url)

        set_ticket_footer(embed, self.bot, extra_text="Select a category below to open a ticket")

        panel_msg = await channel.send(embed=embed)

        async with get_connection() as conn:
            cur = await conn.execute(
                """
                INSERT INTO ticket_panels (guild_id, channel_id, message_id, title, description, ticket_counter, options_json, embed_color, created_at)
                VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?)
                """,
                (
                    guild.id,
                    channel.id,
                    panel_msg.id,
                    title,
                    description,
                    json.dumps(options),
                    color_hex,
                    datetime.now(timezone.utc).isoformat()
                )
            )
            panel_id = cur.lastrowid
            await conn.commit()

        panel_view = TicketPanelView(panel_id, options)
        await panel_msg.edit(view=panel_view)
        self.bot.add_view(panel_view)
        return panel_id, panel_msg.id

    async def edit_panel_direct(
        self,
        panel_id: int,
        guild: discord.Guild,
        title: str,
        description: str,
        options: List[Dict[str, Any]],
        color_hex: str = "#5865F2",
        image_url: Optional[str] = None
    ) -> bool:
        """Edit panel title, description, color, options and update Discord message in real-time."""
        async with get_connection() as conn:
            cur = await conn.execute(
                "SELECT id, channel_id, message_id FROM ticket_panels WHERE (id = ? OR message_id = ?) AND guild_id = ?",
                (panel_id, panel_id, guild.id)
            )
            panel = await cur.fetchone()
            await cur.close()

            if not panel:
                return False

            await conn.execute(
                """
                UPDATE ticket_panels
                SET title = ?, description = ?, options_json = ?, embed_color = ?
                WHERE id = ?
                """,
                (title, description, json.dumps(options), color_hex, panel["id"])
            )
            await conn.commit()

        chan = guild.get_channel(panel["channel_id"])
        if isinstance(chan, discord.TextChannel):
            try:
                msg = await chan.fetch_message(panel["message_id"])
                try:
                    hex_val = int(color_hex.replace("#", ""), 16)
                    color = discord.Color(hex_val)
                except Exception:
                    color = discord.Color.from_rgb(88, 101, 242)

                embed = discord.Embed(
                    title=f"🎫 {title}",
                    description=description,
                    color=color
                )
                if image_url:
                    embed.set_image(url=image_url)

                set_ticket_footer(embed, self.bot, extra_text="Select a category below to open a ticket")
                view = TicketPanelView(panel["id"], options)
                await msg.edit(embed=embed, view=view)
                self.bot.add_view(view)
            except Exception as err:
                logger.warning("Failed to edit discord panel message: %s", err)

        return True

    async def delete_panel_direct(self, panel_id: int, guild: discord.Guild) -> bool:
        """Delete panel from database and attempt to delete Discord message."""
        async with get_connection() as conn:
            cur = await conn.execute(
                "SELECT id, channel_id, message_id FROM ticket_panels WHERE (id = ? OR message_id = ?) AND guild_id = ?",
                (panel_id, panel_id, guild.id)
            )
            panel = await cur.fetchone()
            await cur.close()

            if not panel:
                return False

            await conn.execute("DELETE FROM ticket_panels WHERE id = ?", (panel["id"],))
            await conn.commit()

        chan = guild.get_channel(panel["channel_id"])
        if isinstance(chan, discord.TextChannel):
            try:
                msg = await chan.fetch_message(panel["message_id"])
                await msg.delete()
            except Exception:
                pass

        return True

    async def close_ticket_by_id(self, ticket_id: int, guild: discord.Guild, closed_by_name: str = "Dashboard Admin") -> bool:
        """Close an active ticket by ID directly from the Dashboard."""
        async with get_connection() as conn:
            cur = await conn.execute(
                """
                SELECT t.*, g.closed_category_id, g.log_channel_id as g_log, p.log_channel_id as p_log
                FROM tickets t
                LEFT JOIN ticket_panels p ON t.panel_id = p.id
                LEFT JOIN guild_ticket_config g ON t.guild_id = g.guild_id
                WHERE t.id = ? AND t.guild_id = ?
                """,
                (ticket_id, guild.id)
            )
            ticket = await cur.fetchone()
            await cur.close()

            if not ticket or ticket["status"] == "closed":
                return False

            now_iso = datetime.now(timezone.utc).isoformat()
            await conn.execute("UPDATE tickets SET status = 'closed', closed_at = ? WHERE id = ?", (now_iso, ticket_id))
            await conn.commit()

        chan = guild.get_channel(ticket["channel_id"])
        if isinstance(chan, discord.TextChannel):
            try:
                # Lock channel
                creator = guild.get_member(ticket["user_id"])
                if creator:
                    await chan.set_permissions(creator, send_messages=False, read_messages=True, attach_files=False)

                # Move to closed category if set
                closed_cat_id = ticket["closed_category_id"]
                if closed_cat_id:
                    cat = guild.get_channel(closed_cat_id)
                    if isinstance(cat, discord.CategoryChannel):
                        await chan.edit(category=cat, name=f"closed-{ticket['ticket_number']:04d}")
                else:
                    await chan.edit(name=f"closed-{ticket['ticket_number']:04d}")

                embed = discord.Embed(
                    title="🔒 Ticket Closed",
                    description=f"This ticket was closed via the **Web Dashboard** by **{closed_by_name}**.",
                    color=discord.Color.red()
                )
                set_ticket_footer(embed, self.bot)
                ctrl_view = TicketControlView(ticket_id, is_closed=True, claimed_by=ticket["claimed_by"])
                await chan.send(embed=embed, view=ctrl_view)
            except Exception as e:
                logger.warning("Error processing dashboard ticket close: %s", e)

        return True

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        """Resilient fail-safe dispatcher for all ticket buttons and select menus.
        Ensures interactions are ALWAYS acknowledged and executed even across bot restarts,
        view timeouts, or un-registered component states.
        """
        if interaction.type != discord.InteractionType.component:
            return

        custom_id = interaction.data.get("custom_id", "")
        if not custom_id:
            return

        prefixes = ("ticket_act:", "ticket_close:", "ticket_del:", "ticket_panel:")
        if not any(custom_id.startswith(p) for p in prefixes):
            return

        # If a view callback already completed this interaction, exit cleanly
        if interaction.response.is_done():
            return

        parts = custom_id.split(":")
        prefix = parts[0]
        action = parts[1] if len(parts) > 1 else ""
        target_id = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0

        try:
            if prefix == "ticket_close":
                if action == "confirm":
                    try:
                        if not interaction.response.is_done():
                            await interaction.response.defer()
                    except discord.HTTPException as e:
                        if e.code == 40060:
                            return
                        raise
                    await self.process_close_ticket(interaction, target_id)
                elif action == "cancel":
                    if not interaction.response.is_done():
                        await interaction.response.edit_message(content="❌ Ticket close request cancelled.", embed=None, view=None)
            elif prefix == "ticket_del":
                if action == "confirm":
                    try:
                        if not interaction.response.is_done():
                            await interaction.response.defer()
                    except discord.HTTPException as e:
                        if e.code == 40060:
                            return
                        raise
                    await self.process_delete_ticket(interaction, target_id)
                elif action == "cancel":
                    if not interaction.response.is_done():
                        await interaction.response.edit_message(content="❌ Ticket deletion cancelled.", embed=None, view=None)
            elif prefix == "ticket_act":
                if action == "claim":
                    try:
                        if not interaction.response.is_done():
                            await interaction.response.defer()
                    except discord.HTTPException as e:
                        if e.code == 40060:
                            return
                        raise
                    await self.claim_ticket(interaction, target_id)
                elif action == "close":
                    await self.prompt_close_ticket(interaction, target_id)
                elif action == "rename":
                    modal = TicketRenameModal(target_id, self)
                    await interaction.response.send_modal(modal)
                elif action == "transcript":
                    try:
                        if not interaction.response.is_done():
                            await interaction.response.defer(ephemeral=True)
                    except discord.HTTPException as e:
                        if e.code == 40060:
                            return
                        raise
                    await self.send_transcript(interaction, target_id)
                elif action == "reopen":
                    try:
                        if not interaction.response.is_done():
                            await interaction.response.defer()
                    except discord.HTTPException as e:
                        if e.code == 40060:
                            return
                        raise
                    await self.reopen_ticket(interaction, target_id)
                elif action == "delete":
                    await self.prompt_delete_ticket(interaction, target_id)
            elif prefix == "ticket_panel" and action == "select":
                try:
                    if not interaction.response.is_done():
                        await interaction.response.defer(ephemeral=True)
                except discord.HTTPException as e:
                    if e.code == 40060:
                        return
                    raise
                values = interaction.data.get("values", [])
                val = values[0] if values else "support"
                await self.create_ticket_channel(interaction, target_id, val)
        except discord.HTTPException as e:
            if e.code == 40060:
                return
            logger.exception("HTTP error in ticket interaction handler for %s: %s", custom_id, e)
        except Exception as e:
            logger.exception("Error in ticket fallback interaction handler for %s: %s", custom_id, e)
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ An error occurred processing this ticket action.", ephemeral=True)
                else:
                    await interaction.followup.send("❌ An error occurred processing this ticket action.", ephemeral=True)
            except Exception:
                pass




async def setup(bot: commands.Bot):
    cog = TicketsCog(bot)
    await bot.add_cog(cog)

    # Register persistent views for all panels & open tickets
    try:
        async with get_connection() as conn:
            cur = await conn.execute("SELECT id, options_json FROM ticket_panels")
            panels = await cur.fetchall()
            await cur.close()
            for p in panels:
                opts = json.loads(p["options_json"]) if p["options_json"] else None
                bot.add_view(TicketPanelView(p["id"], opts))

            cur = await conn.execute("SELECT id, status, claimed_by FROM tickets WHERE status = 'open'")
            tickets = await cur.fetchall()
            await cur.close()
            for t in tickets:
                bot.add_view(TicketControlView(t["id"], is_closed=False, claimed_by=t["claimed_by"]))
    except Exception as e:
        logger.debug("Failed to register persistent ticket views on boot: %s", e)
