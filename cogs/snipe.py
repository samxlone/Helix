"""Snipe and EditSnipe System for Helix.

Captures recently deleted messages, edited messages, and removed reactions
with full support for images/attachments, stickers, authors, timestamps,
and interactive page browsing.
"""
from collections import defaultdict, deque
from datetime import datetime, timezone
import logging
from typing import Optional, List, Dict, Any

import discord
from discord.ext import commands
from discord import app_commands

from utils.embed_utils import HELIX_COLOR, HELIX_INFO, HELIX_WARNING, HELIX_DARK, set_owner_footer

logger = logging.getLogger(__name__)


class SnipePaginationView(discord.ui.View):
    def __init__(self, author_id: int, snipes: list, bot: commands.Bot, timeout: float = 120.0):
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.snipes = snipes
        self.bot = bot
        self.index = 0
        self._update_buttons()

    def _update_buttons(self):
        self.prev_button.disabled = (self.index == 0)
        self.next_button.disabled = (self.index >= len(self.snipes) - 1)
        self.page_indicator.label = f"{self.index + 1} / {len(self.snipes)}"

    def get_embed(self) -> discord.Embed:
        snipe_data = self.snipes[self.index]
        author = snipe_data["author"]
        content = snipe_data["content"]
        deleted_at = snipe_data["deleted_at"]
        attachments = snipe_data.get("attachments", [])
        stickers = snipe_data.get("stickers", [])

        embed = discord.Embed(
            description=content or "*[No text content]*",
            color=HELIX_COLOR,
            timestamp=deleted_at
        )
        embed.set_author(
            name=f"{author.get('name', 'Unknown User')} ({author.get('display_name', 'Unknown')})",
            icon_url=author.get("avatar_url")
        )

        unix_ts = int(deleted_at.timestamp())
        embed.add_field(name="🗑️ Deleted", value=f"<t:{unix_ts}:R> (<t:{unix_ts}:t>)", inline=True)

        if attachments:
            embed.add_field(name="📎 Attachments", value=f"`{len(attachments)}` file(s)", inline=True)
            # If the attachment is an image, set image url
            for att in attachments:
                url = att.get("url") or att.get("proxy_url", "")
                if any(url.lower().endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".gif", ".webp"]):
                    embed.set_image(url=url)
                    break

        if stickers:
            embed.add_field(name="🏷️ Stickers", value=", ".join(f"`{s}`" for s in stickers), inline=True)

        set_owner_footer(embed, self.bot, extra_text=f"Snipe • #{snipe_data.get('channel_name', 'channel')}")
        return embed

    @discord.ui.button(label="◀ Prev", style=discord.ButtonStyle.secondary, custom_id="snipe_prev")
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Only the command invoker can flip pages.", ephemeral=True)
            return
        if self.index > 0:
            self.index -= 1
            self._update_buttons()
            await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @discord.ui.button(label="1 / 1", style=discord.ButtonStyle.primary, disabled=True, custom_id="snipe_page")
    async def page_indicator(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary, custom_id="snipe_next")
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Only the command invoker can flip pages.", ephemeral=True)
            return
        if self.index < len(self.snipes) - 1:
            self.index += 1
            self._update_buttons()
            await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @discord.ui.button(label="🗑️ Clear Cache", style=discord.ButtonStyle.danger, custom_id="snipe_clear")
    async def clear_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Allow caller if moderator or command invoker with manage_messages
        perms = interaction.channel.permissions_for(interaction.user) if interaction.guild else None
        is_mod = perms.manage_messages if perms else False
        if not is_mod and interaction.user.id != interaction.guild.owner_id:
            await interaction.response.send_message("❌ You lack `Manage Messages` permission to clear snipe cache.", ephemeral=True)
            return

        cog = self.bot.get_cog("Snipe")
        if cog and interaction.channel_id in cog.delete_cache:
            cog.delete_cache[interaction.channel_id].clear()

        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content="🗑️ *Snipe cache for this channel has been cleared by a moderator.*", embed=None, view=self)


class Snipe(commands.Cog):
    """Snipe deleted messages, edited messages, and removed reactions."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # channel_id -> deque of dicts (max 20)
        self.delete_cache: Dict[int, deque] = defaultdict(lambda: deque(maxlen=20))
        self.edit_cache: Dict[int, deque] = defaultdict(lambda: deque(maxlen=20))
        self.reaction_cache: Dict[int, deque] = defaultdict(lambda: deque(maxlen=20))

    # -------------------------------------------------------------------------
    # Event Listeners
    # -------------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return

        author_data = {
            "id": message.author.id,
            "name": message.author.name,
            "display_name": message.author.display_name,
            "mention": message.author.mention,
            "avatar_url": message.author.display_avatar.url if message.author.display_avatar else None
        }

        attachments_data = []
        for att in message.attachments:
            attachments_data.append({
                "url": att.url,
                "proxy_url": att.proxy_url,
                "filename": att.filename,
                "size": att.size
            })

        stickers_data = [s.name for s in message.stickers] if hasattr(message, "stickers") else []

        snipe_entry = {
            "id": message.id,
            "channel_id": message.channel.id,
            "channel_name": getattr(message.channel, "name", "channel"),
            "author": author_data,
            "content": message.content,
            "created_at": message.created_at,
            "deleted_at": datetime.now(timezone.utc),
            "attachments": attachments_data,
            "stickers": stickers_data
        }

        # Prepend to front of deque so index 0 is most recent
        self.delete_cache[message.channel.id].appendleft(snipe_entry)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if not before.guild or before.author.bot:
            return
        if before.content == after.content:
            return

        author_data = {
            "id": before.author.id,
            "name": before.author.name,
            "display_name": before.author.display_name,
            "mention": before.author.mention,
            "avatar_url": before.author.display_avatar.url if before.author.display_avatar else None
        }

        edit_entry = {
            "id": before.id,
            "channel_id": before.channel.id,
            "channel_name": getattr(before.channel, "name", "channel"),
            "author": author_data,
            "before": before.content,
            "after": after.content,
            "jump_url": after.jump_url,
            "edited_at": datetime.now(timezone.utc)
        }

        self.edit_cache[before.channel.id].appendleft(edit_entry)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        if not payload.guild_id:
            return

        guild = self.bot.get_guild(payload.guild_id)
        user = guild.get_member(payload.user_id) if guild else None
        if user and user.bot:
            return

        reaction_entry = {
            "user_id": payload.user_id,
            "user_name": user.display_name if user else f"User {payload.user_id}",
            "user_avatar": user.display_avatar.url if (user and user.display_avatar) else None,
            "emoji": str(payload.emoji),
            "message_id": payload.message_id,
            "channel_id": payload.channel_id,
            "removed_at": datetime.now(timezone.utc)
        }

        self.reaction_cache[payload.channel_id].appendleft(reaction_entry)

    # -------------------------------------------------------------------------
    # Commands
    # -------------------------------------------------------------------------

    @commands.command(name="snipe", aliases=["s"])
    @commands.guild_only()
    async def snipe_command(self, ctx: commands.Context, index: int = 1):
        """Snipe recently deleted messages in this channel."""
        snipes = list(self.delete_cache[ctx.channel.id])
        if not snipes:
            await ctx.send("ℹ️ There are no recently deleted messages recorded in this channel.", ephemeral=True)
            return

        if index < 1 or index > len(snipes):
            await ctx.send(f"❌ Invalid index! Choose between `1` and `{len(snipes)}`.", ephemeral=True)
            return

        # If user explicitly requested an index or if single snipe, render directly with pagination view
        view = SnipePaginationView(author_id=ctx.author.id, snipes=snipes, bot=self.bot)
        view.index = index - 1
        view._update_buttons()

        embed = view.get_embed()
        await ctx.send(embed=embed, view=view)

    @commands.command(name="editsnipe", aliases=["esnipe"])
    @commands.guild_only()
    async def editsnipe_command(self, ctx: commands.Context, index: int = 1):
        """Snipe recently edited messages in this channel."""
        edits = list(self.edit_cache[ctx.channel.id])
        if not edits:
            await ctx.send("ℹ️ There are no recently edited messages recorded in this channel.", ephemeral=True)
            return

        if index < 1 or index > len(edits):
            await ctx.send(f"❌ Invalid index! Choose between `1` and `{len(edits)}`.", ephemeral=True)
            return

        entry = edits[index - 1]
        author = entry["author"]
        unix_ts = int(entry["edited_at"].timestamp())

        embed = discord.Embed(
            title="✏️ Message Edit Snipe",
            color=HELIX_INFO,
            timestamp=entry["edited_at"]
        )
        embed.set_author(
            name=f"{author.get('name', 'Unknown User')} ({author.get('display_name', 'Unknown')})",
            icon_url=author.get("avatar_url")
        )

        embed.add_field(name="⏮️ Before", value=entry["before"] or "*[Empty]*", inline=False)
        embed.add_field(name="⏭️ After", value=entry["after"] or "*[Empty]*", inline=False)
        embed.add_field(name="🕒 Edited", value=f"<t:{unix_ts}:R> • [Jump to Message]({entry['jump_url']})", inline=False)

        set_owner_footer(embed, self.bot, extra_text=f"Edit Snipe • #{entry.get('channel_name', 'channel')}")
        await ctx.send(embed=embed)

    @commands.command(name="reactionsnipe", aliases=["rsnipe"])
    @commands.guild_only()
    async def reactionsnipe_command(self, ctx: commands.Context, index: int = 1):
        """Snipe recently removed reactions in this channel."""
        reactions = list(self.reaction_cache[ctx.channel.id])
        if not reactions:
            await ctx.send("ℹ️ There are no recently removed reactions recorded in this channel.", ephemeral=True)
            return

        if index < 1 or index > len(reactions):
            await ctx.send(f"❌ Invalid index! Choose between `1` and `{len(reactions)}`.", ephemeral=True)
            return

        entry = reactions[index - 1]
        unix_ts = int(entry["removed_at"].timestamp())

        embed = discord.Embed(
            title="🎯 Reaction Snipe",
            description=f"**{entry['user_name']}** (<@{entry['user_id']}>) removed reaction {entry['emoji']}",
            color=HELIX_WARNING,
            timestamp=entry["removed_at"]
        )
        if entry.get("user_avatar"):
            embed.set_thumbnail(url=entry["user_avatar"])

        msg_link = f"https://discord.com/channels/{ctx.guild.id}/{ctx.channel.id}/{entry['message_id']}"
        embed.add_field(name="🕒 Removed", value=f"<t:{unix_ts}:R> • [Jump to Target Message]({msg_link})", inline=False)

        set_owner_footer(embed, self.bot, extra_text=f"Reaction Snipe • #{ctx.channel.name}")
        await ctx.send(embed=embed)

    @commands.command(name="clearsnipe", aliases=["csnipe"])
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def clearsnipe_command(self, ctx: commands.Context):
        """Clear all snipe caches for this channel."""
        c_id = ctx.channel.id
        self.delete_cache[c_id].clear()
        self.edit_cache[c_id].clear()
        self.reaction_cache[c_id].clear()

        embed = discord.Embed(
            description="🗑️ Successfully purged all **delete**, **edit**, and **reaction** snipe caches for this channel.",
            color=HELIX_COLOR
        )
        set_owner_footer(embed, self.bot)
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Snipe(bot))
