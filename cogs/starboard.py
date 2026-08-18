"""Starboard Cog for celebrating highlighted server messages upon reaching reaction thresholds."""
import logging
from typing import Optional
import discord
from discord.ext import commands

from utils.db import get_connection
from utils.embed_utils import HELIX_COLOR, HELIX_SUCCESS, set_owner_footer

logger = logging.getLogger(__name__)


class StarboardCog(commands.Cog, name="Starboard"):
    """Starboard System: Pin and showcase community favorites that reach star reaction milestones."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _is_staff_or_admin(self, ctx: commands.Context) -> bool:
        if not ctx.guild:
            return False
        if ctx.author.id == ctx.guild.owner_id:
            return True
        perms = getattr(ctx.author, "guild_permissions", None)
        if perms and (perms.manage_channels or perms.manage_messages or perms.administrator):
            return True
        try:
            return await self.bot.is_owner(ctx.author)
        except Exception:
            return False

    async def _get_config(self, guild_id: int):
        async with get_connection() as conn:
            cur = await conn.execute(
                "SELECT * FROM starboard_config WHERE guild_id = ?",
                (guild_id,)
            )
            cfg = await cur.fetchone()
            await cur.close()
            return cfg

    @commands.Cog.listener("on_raw_reaction_add")
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if not payload.guild_id:
            return

        cfg = await self._get_config(payload.guild_id)
        if not cfg or cfg["is_enabled"] == 0 or not cfg["channel_id"]:
            return

        target_emoji = cfg["emoji"] or "⭐"
        if str(payload.emoji) != target_emoji:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        channel = guild.get_channel(payload.channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            return

        # Do not star messages in the starboard channel itself
        if channel.id == cfg["channel_id"]:
            return

        try:
            msg = await channel.fetch_message(payload.message_id)
        except Exception:
            return

        if not msg:
            return

        # Count total reactions for the target emoji
        reaction = discord.utils.get(msg.reactions, emoji=target_emoji)
        star_count = reaction.count if reaction else 0
        threshold = cfg["threshold"] or 3

        if star_count < threshold:
            return

        starboard_ch = guild.get_channel(cfg["channel_id"])
        if not starboard_ch or not isinstance(starboard_ch, discord.TextChannel):
            return

        # Check if already on starboard
        async with get_connection() as conn:
            cur = await conn.execute(
                "SELECT starboard_message_id FROM starboard_messages WHERE guild_id = ? AND original_message_id = ?",
                (guild.id, msg.id)
            )
            existing = await cur.fetchone()
            await cur.close()

            embed = discord.Embed(
                description=msg.content or "*[No text content]*",
                color=discord.Color.gold(),
                timestamp=msg.created_at
            )
            embed.set_author(name=msg.author.display_name, icon_url=msg.author.display_avatar.url if msg.author.display_avatar else None)
            embed.add_field(
                name="Source",
                value=f"[Jump to Message]({msg.jump_url}) • In {channel.mention}",
                inline=False
            )

            # Attachments
            if msg.attachments:
                for att in msg.attachments:
                    if att.content_type and att.content_type.startswith("image/"):
                        embed.set_image(url=att.url)
                        break

            set_owner_footer(embed, self.bot, extra_text=f"ID: {msg.id}")
            header_text = f"{target_emoji} **{star_count}** {channel.mention}"

            if existing:
                try:
                    sb_msg = await starboard_ch.fetch_message(existing["starboard_message_id"])
                    if sb_msg:
                        await sb_msg.edit(content=header_text, embed=embed)
                        await conn.execute(
                            "UPDATE starboard_messages SET star_count = ? WHERE guild_id = ? AND original_message_id = ?",
                            (star_count, guild.id, msg.id)
                        )
                        await conn.commit()
                except Exception as e:
                    logger.debug("Failed to update existing starboard message: %s", e)
            else:
                try:
                    sent = await starboard_ch.send(content=header_text, embed=embed)
                    await conn.execute(
                        "INSERT INTO starboard_messages (guild_id, original_message_id, starboard_message_id, star_count) VALUES (?, ?, ?, ?)",
                        (guild.id, msg.id, sent.id, star_count)
                    )
                    await conn.commit()
                except Exception as e:
                    logger.warning("Failed to post message to starboard in %s: %s", guild.name, e)

    @commands.group(name="starboard", invoke_without_command=True)
    @commands.guild_only()
    async def starboard_group(self, ctx: commands.Context):
        """Configure Starboard to showcase community highlights."""
        if not await self._is_staff_or_admin(ctx):
            await ctx.send("❌ You need `Manage Channels` or `Administrator` permission.", ephemeral=True)
            return

        cfg = await self._get_config(ctx.guild.id)
        if not cfg or not cfg["channel_id"]:
            await ctx.send(
                "⭐ **Starboard is not configured yet!**\n"
                "> Use `!setstarboard #channel` to designate your server's showcase channel.",
                ephemeral=True
            )
            return

        ch = ctx.guild.get_channel(cfg["channel_id"])
        ch_str = ch.mention if ch else f"`ID: {cfg['channel_id']}`"
        status = "🟢 Enabled" if cfg["is_enabled"] == 1 else "🔴 Disabled"

        embed = discord.Embed(
            title=f"⭐ Starboard Settings — {ctx.guild.name}",
            description=(
                f"> • **Status:** {status}\n"
                f"> • **Starboard Channel:** {ch_str}\n"
                f"> • **Reaction Threshold:** `{cfg['threshold'] or 3}` reactions\n"
                f"> • **Trigger Emoji:** {cfg['emoji'] or '⭐'}\n\n"
                f"**Configuration Commands:**\n"
                f"`!setstarboard <#channel>` — Set starboard channel\n"
                f"`!starboard threshold <number>` — Set minimum stars required\n"
                f"`!starboard emoji <emoji>` — Change trigger emoji\n"
                f"`!starboard toggle` — Enable/disable starboard"
            ),
            color=discord.Color.gold()
        )
        set_owner_footer(embed, self.bot)
        await ctx.send(embed=embed)

    @commands.command(name="setstarboard")
    @commands.guild_only()
    async def setstarboard(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        """Set the channel where starboard messages will be showcased."""
        if not await self._is_staff_or_admin(ctx):
            await ctx.send("❌ You need `Manage Channels` permission.", ephemeral=True)
            return

        target_ch = channel or ctx.channel
        async with get_connection() as conn:
            await conn.execute("""
                INSERT INTO starboard_config (guild_id, channel_id, is_enabled)
                VALUES (?, ?, 1)
                ON CONFLICT(guild_id) DO UPDATE SET channel_id = ?, is_enabled = 1
            """, (ctx.guild.id, target_ch.id, target_ch.id))
            await conn.commit()

        embed = discord.Embed(
            title="⭐ Starboard Channel Set",
            description=f"> Starred community messages will now be posted to {target_ch.mention}!",
            color=HELIX_SUCCESS
        )
        set_owner_footer(embed, self.bot)
        await ctx.send(embed=embed)

    @starboard_group.command(name="threshold", aliases=["limit", "min"])
    @commands.guild_only()
    async def starboard_threshold(self, ctx: commands.Context, count: int):
        """Set minimum stars required to appear on Starboard."""
        if not await self._is_staff_or_admin(ctx):
            await ctx.send("❌ You need `Manage Channels` permission.", ephemeral=True)
            return

        if count < 1 or count > 50:
            await ctx.send("❌ Threshold must be between `1` and `50`.", ephemeral=True)
            return

        async with get_connection() as conn:
            await conn.execute("""
                INSERT INTO starboard_config (guild_id, threshold, is_enabled)
                VALUES (?, ?, 1)
                ON CONFLICT(guild_id) DO UPDATE SET threshold = ?
            """, (ctx.guild.id, count, count))
            await conn.commit()

        embed = discord.Embed(
            title="⭐ Starboard Threshold Updated",
            description=f"> Messages now require **`{count}`** star reactions to enter Starboard.",
            color=HELIX_SUCCESS
        )
        set_owner_footer(embed, self.bot)
        await ctx.send(embed=embed)

    @starboard_group.command(name="emoji")
    @commands.guild_only()
    async def starboard_emoji(self, ctx: commands.Context, emoji: str):
        """Set custom reaction emoji for Starboard."""
        if not await self._is_staff_or_admin(ctx):
            await ctx.send("❌ You need `Manage Channels` permission.", ephemeral=True)
            return

        async with get_connection() as conn:
            await conn.execute("""
                INSERT INTO starboard_config (guild_id, emoji, is_enabled)
                VALUES (?, ?, 1)
                ON CONFLICT(guild_id) DO UPDATE SET emoji = ?
            """, (ctx.guild.id, emoji, emoji))
            await conn.commit()

        embed = discord.Embed(
            title="⭐ Starboard Emoji Updated",
            description=f"> Starboard reaction emoji is now set to **{emoji}**.",
            color=HELIX_SUCCESS
        )
        set_owner_footer(embed, self.bot)
        await ctx.send(embed=embed)

    @starboard_group.command(name="toggle")
    @commands.guild_only()
    async def starboard_toggle(self, ctx: commands.Context):
        """Toggle Starboard on or off for the server."""
        if not await self._is_staff_or_admin(ctx):
            await ctx.send("❌ You need `Manage Channels` permission.", ephemeral=True)
            return

        cfg = await self._get_config(ctx.guild.id)
        current = cfg["is_enabled"] if cfg else 0
        new_val = 0 if current == 1 else 1

        async with get_connection() as conn:
            await conn.execute("""
                INSERT INTO starboard_config (guild_id, is_enabled)
                VALUES (?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET is_enabled = ?
            """, (ctx.guild.id, new_val, new_val))
            await conn.commit()

        state_str = "🟢 **ENABLED**" if new_val == 1 else "🔴 **DISABLED**"
        embed = discord.Embed(
            title="⭐ Starboard Toggled",
            description=f"> Starboard is now {state_str}.",
            color=HELIX_SUCCESS if new_val == 1 else HELIX_COLOR
        )
        set_owner_footer(embed, self.bot)
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(StarboardCog(bot))
