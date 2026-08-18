import os
import asyncio
import logging

import random
import re
from datetime import datetime, timezone, timedelta
from typing import Optional, List

import discord
from discord.ext import commands, tasks

from utils.db import get_connection
from utils.embed_utils import set_owner_footer

logger = logging.getLogger(__name__)


def parse_time_duration(time_str: str) -> Optional[int]:
    """Parse any time string like 30s, 10m, 3h, 30d, 1h30m, 2d12h into seconds."""
    time_str = time_str.strip().lower()
    if not time_str:
        return None

    # Handle raw digits (treated as minutes)
    if time_str.isdigit():
        return int(time_str) * 60

    unit_map = {
        "s": 1, "sec": 1, "second": 1, "seconds": 1,
        "m": 60, "min": 60, "minute": 60, "minutes": 60,
        "h": 3600, "hr": 3600, "hour": 3600, "hours": 3600,
        "d": 86400, "day": 86400, "days": 86400,
        "w": 604800, "wk": 604800, "week": 604800, "weeks": 604800,
        "mo": 2592000, "month": 2592000, "months": 2592000,
        "y": 31536000, "yr": 31536000, "year": 31536000, "years": 31536000,
    }

    # Find all number + unit segments (e.g. 1d 12h 30m, 3h, 30d)
    pattern = re.compile(r"(\d+)\s*(mo|sec|second|seconds|min|minute|minutes|hr|hour|hours|day|days|wk|week|weeks|month|months|yr|year|years|[smhdw])")
    matches = pattern.findall(time_str)

    if not matches:
        return None

    total_seconds = 0
    for value_str, unit in matches:
        total_seconds += int(value_str) * unit_map.get(unit, 60)

    return total_seconds if total_seconds > 0 else None



class GiveawayButton(discord.ui.Button):
    def __init__(self, giveaway_id: int, entry_count: int = 0, disabled: bool = False):
        super().__init__(
            label=f"Enter ({entry_count})" if entry_count > 0 else "Enter Giveaway",
            emoji="🎉",
            style=discord.ButtonStyle.primary,
            custom_id=f"giveaway_entry:{giveaway_id}",
            disabled=disabled
        )
        self.giveaway_id = giveaway_id

    async def callback(self, interaction: discord.Interaction):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)

        user_id = interaction.user.id
        async with get_connection() as conn:
            # Check if giveaway is still active
            cur = await conn.execute("SELECT prize, ended FROM giveaways WHERE id = ?", (self.giveaway_id,))
            gw = await cur.fetchone()
            await cur.close()

            if not gw:
                await interaction.followup.send("❌ This giveaway no longer exists.", ephemeral=True)
                return
            if gw["ended"] == 1:
                await interaction.followup.send("❌ This giveaway has already ended!", ephemeral=True)
                return

            prize = gw["prize"]

            # Check if already entered
            cur = await conn.execute(
                "SELECT 1 FROM giveaway_entries WHERE giveaway_id = ? AND user_id = ?",
                (self.giveaway_id, user_id)
            )
            exists = await cur.fetchone()
            await cur.close()

            if exists:
                # Leave giveaway
                await conn.execute(
                    "DELETE FROM giveaway_entries WHERE giveaway_id = ? AND user_id = ?",
                    (self.giveaway_id, user_id)
                )
                await conn.commit()
                entered = False
            else:
                # Enter giveaway
                await conn.execute(
                    "INSERT INTO giveaway_entries (giveaway_id, user_id) VALUES (?, ?)",
                    (self.giveaway_id, user_id)
                )
                await conn.commit()
                entered = True

            # Get new total count
            cur = await conn.execute(
                "SELECT COUNT(*) as count FROM giveaway_entries WHERE giveaway_id = ?",
                (self.giveaway_id,)
            )
            count_row = await cur.fetchone()
            await cur.close()
            total_entries = count_row["count"] if count_row else 0

        # Update button label
        self.label = f"Enter ({total_entries})" if total_entries > 0 else "Enter Giveaway"
        try:
            if interaction.message:
                embed = interaction.message.embeds[0] if interaction.message.embeds else None
                if embed:
                    # Update Entries field in embed
                    for idx, field in enumerate(embed.fields):
                        if field.name == "🎟️ Entries":
                            embed.set_field_at(idx, name="🎟️ Entries", value=f"`{total_entries}`", inline=True)
                            break
                await interaction.message.edit(embed=embed, view=self.view)
        except Exception as exc:
            logger.debug("Failed to update giveaway message embed: %s", exc)

        if entered:
            await interaction.followup.send(f"🎉 **Entered!** You have joined the giveaway for **{prize}**! Good luck! 🍀", ephemeral=True)
        else:
            await interaction.followup.send("👋 You have left the giveaway.", ephemeral=True)


class GiveawayView(discord.ui.View):
    def __init__(self, giveaway_id: int, entry_count: int = 0, disabled: bool = False):
        super().__init__(timeout=None)
        self.giveaway_id = giveaway_id
        self.add_item(GiveawayButton(giveaway_id, entry_count=entry_count, disabled=disabled))

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item) -> None:
        logger.exception("GiveawayView interaction error: %s", error)
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ An error occurred processing your entry.", ephemeral=True)
            else:
                await interaction.followup.send("❌ An error occurred processing your entry.", ephemeral=True)
        except Exception:
            pass


class GiveawayCog(commands.Cog, name="Giveaway"):
    """Interactive Button Giveaway System for Discord Servers."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.check_giveaways_loop.start()

    def cog_unload(self):
        self.check_giveaways_loop.cancel()

    async def _is_staff_or_owner(self, ctx: commands.Context) -> bool:
        owner_id = os.getenv("OWNER_ID")
        if owner_id and str(ctx.author.id) == str(owner_id):
            return True
        try:
            if await self.bot.is_owner(ctx.author):
                return True
        except Exception:
            pass
        if ctx.guild:
            if ctx.author.id == ctx.guild.owner_id:
                return True
            perms = getattr(ctx.author, "guild_permissions", None)
            if perms and (perms.manage_guild or perms.administrator):
                return True
        return False

    @tasks.loop(seconds=10.0)
    async def check_giveaways_loop(self):
        """Check active giveaways and end ones whose timer expired."""
        try:
            now_iso = datetime.now(timezone.utc).isoformat()
            async with get_connection() as conn:
                cur = await conn.execute(
                    "SELECT id, guild_id, channel_id, message_id, host_id, prize, winners_count, end_time "
                    "FROM giveaways WHERE ended = 0 AND end_time <= ?",
                    (now_iso,)
                )
                expired_giveaways = await cur.fetchall()
                await cur.close()

                for gw in expired_giveaways:
                    await self._end_giveaway(gw["id"])
        except Exception as e:
            logger.exception("Error in check_giveaways_loop: %s", e)

    @check_giveaways_loop.before_loop
    async def before_check_giveaways(self):
        try:
            await self.bot.wait_until_ready()
        except Exception:
            pass


    async def _end_giveaway(self, giveaway_id: int) -> Optional[List[int]]:
        """End a giveaway, pick winners, edit embed and send celebration announcement."""
        async with get_connection() as conn:
            cur = await conn.execute(
                "SELECT id, guild_id, channel_id, message_id, host_id, prize, winners_count "
                "FROM giveaways WHERE id = ? AND ended = 0",
                (giveaway_id,)
            )
            gw = await cur.fetchone()
            await cur.close()

            if not gw:
                return None

            # Mark as ended
            await conn.execute("UPDATE giveaways SET ended = 1 WHERE id = ?", (giveaway_id,))
            await conn.commit()

            # Get all entrants
            cur = await conn.execute("SELECT user_id FROM giveaway_entries WHERE giveaway_id = ?", (giveaway_id,))
            rows = await cur.fetchall()
            await cur.close()
            entrant_ids = [r["user_id"] for r in rows]

        guild = self.bot.get_guild(gw["guild_id"])
        channel = guild.get_channel(gw["channel_id"]) if guild else None
        message = None
        if channel:
            try:
                message = await channel.fetch_message(gw["message_id"])
            except Exception:
                pass

        winners_count = gw["winners_count"]
        prize = gw["prize"]
        host_id = gw["host_id"]

        # Select random winners
        if entrant_ids:
            num_to_pick = min(winners_count, len(entrant_ids))
            winner_ids = random.sample(entrant_ids, num_to_pick)
        else:
            winner_ids = []

        winner_mentions = [f"<@{uid}>" for uid in winner_ids] if winner_ids else ["*No valid entrants*"]

        from utils.embed_utils import HELIX_COLOR
        # Build Ended Embed
        embed = discord.Embed(
            title="🎉 Giveaway Finished",
            description=(
                f"### 🎁 {prize}\n\n"
                f"> 🏆 **Winner(s):** {', '.join(winner_mentions)}\n"
                f"> 👑 **Hosted By:** <@{host_id}>\n"
                f"> 🎟️ **Total Entries:** `{len(entrant_ids)}`"
            ),
            color=HELIX_COLOR,
            timestamp=datetime.now(timezone.utc)
        )
        set_owner_footer(embed, self.bot, extra_text="Giveaway Ended")

        disabled_view = GiveawayView(giveaway_id, entry_count=len(entrant_ids), disabled=True)

        if message:
            try:
                await message.edit(embed=embed, view=disabled_view)
            except Exception as e:
                logger.warning("Failed to edit giveaway message upon end: %s", e)

        if channel:
            try:
                if winner_ids:
                    await channel.send(
                        f"🎉 Congratulations {', '.join(winner_mentions)}! You won the giveaway for **{prize}**! 🎁\n"
                        f"*(Jump to Giveaway: {message.jump_url if message else 'N/A'})*"
                    )
                else:
                    await channel.send(f"😢 The giveaway for **{prize}** ended with no entrants.")
            except Exception as e:
                logger.warning("Failed to post winner announcement in channel %s: %s", channel.id, e)

        return winner_ids

    # -------------------------------------------------------------------------
    # Giveaway Commands
    # -------------------------------------------------------------------------

    @commands.hybrid_group(name="giveaway", invoke_without_command=True)
    @commands.guild_only()
    async def giveaway_group(self, ctx: commands.Context):
        """Interactive Giveaway System for your server."""
        await ctx.send_help(ctx.command)

    @giveaway_group.command(name="start", aliases=["create"])
    @commands.guild_only()
    async def g_start(self, ctx: commands.Context, duration: str, winners: int, *, prize: str):
        """Start an interactive button giveaway (e.g. `!gstart 10m 1 Discord Nitro`)."""
        if not await self._is_staff_or_owner(ctx):
            await ctx.send("❌ You need **Manage Server** or Administrator permission to start giveaways.", ephemeral=True)
            return

        seconds = parse_time_duration(duration)
        if not seconds or seconds < 5:
            await ctx.send("❌ Invalid duration format! Use e.g. `30s`, `10m`, `2h`, `1d`.", ephemeral=True)
        if winners < 1 or winners > 20:
            await ctx.send("❌ Winners count must be between 1 and 20.", ephemeral=True)
            return

        end_dt = datetime.now(timezone.utc) + timedelta(seconds=seconds)
        end_iso = end_dt.isoformat()
        unix_ts = int(end_dt.timestamp())

        from utils.embed_utils import HELIX_COLOR
        embed = discord.Embed(
            title="🎉 Luxury Server Giveaway",
            description=(
                f"### 🎁 {prize}\n\n"
                f"> ⏳ **Ends:** <t:{unix_ts}:R> (<t:{unix_ts}:D>)\n"
                f"> 👑 **Hosted By:** {ctx.author.mention}\n"
                f"> 🏆 **Winners:** `{winners}`  •  🎟️ **Entries:** `0`\n\n"
                f"*Click the button below to claim your ticket entry!*"
            ),
            color=HELIX_COLOR
        )
        set_owner_footer(embed, self.bot, extra_text="Interactive Giveaway")

        # Post initial message
        msg = await ctx.send(embed=embed)

        # Save to database
        async with get_connection() as conn:
            cur = await conn.execute(
                """
                INSERT INTO giveaways (guild_id, channel_id, message_id, host_id, prize, winners_count, end_time, ended, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)
                """,
                (ctx.guild.id, ctx.channel.id, msg.id, ctx.author.id, prize, winners, end_iso, datetime.now(timezone.utc).isoformat())
            )
            gw_id = cur.lastrowid
            await conn.commit()

        # Attach interactive button view
        view = GiveawayView(gw_id, entry_count=0)
        await msg.edit(view=view)

    @commands.command(name="gstart", aliases=["gcreate"])
    @commands.guild_only()
    async def gstart_prefix(self, ctx: commands.Context, duration: str, winners: int, *, prize: str):
        """Shortcut command to start a giveaway."""
        await self.g_start(ctx, duration=duration, winners=winners, prize=prize)

    @giveaway_group.command(name="end", aliases=["finish"])
    @commands.guild_only()
    async def g_end(self, ctx: commands.Context, message_id: str):
        """End an active giveaway early and pick winners immediately."""
        if not await self._is_staff_or_owner(ctx):
            await ctx.send("❌ You need **Manage Server** permission to end giveaways.", ephemeral=True)
            return

        try:
            m_id = int(message_id.strip())
        except ValueError:
            await ctx.send("❌ Invalid message ID provided.", ephemeral=True)
            return

        async with get_connection() as conn:
            cur = await conn.execute("SELECT id FROM giveaways WHERE message_id = ? AND guild_id = ?", (m_id, ctx.guild.id))
            gw = await cur.fetchone()
            await cur.close()

        if not gw:
            await ctx.send("❌ No giveaway found matching that message ID in this server.", ephemeral=True)
            return

        winners = await self._end_giveaway(gw["id"])
        if winners is not None:
            await ctx.send(f"✅ Giveaway (ID: `{m_id}`) ended successfully!", ephemeral=True)
        else:
            await ctx.send("⚠️ That giveaway was already ended.", ephemeral=True)

    @commands.command(name="gend")
    @commands.guild_only()
    async def gend_prefix(self, ctx: commands.Context, message_id: str):
        """Shortcut command to end an active giveaway early."""
        await self.g_end(ctx, message_id=message_id)

    @giveaway_group.command(name="reroll")
    @commands.guild_only()
    async def g_reroll(self, ctx: commands.Context, message_id: str, winners: Optional[int] = None):
        """Reroll new winner(s) for an ended giveaway."""
        if not await self._is_staff_or_owner(ctx):
            await ctx.send("❌ You need **Manage Server** permission to reroll giveaways.", ephemeral=True)
            return

        try:
            m_id = int(message_id.strip())
        except ValueError:
            await ctx.send("❌ Invalid message ID provided.", ephemeral=True)
            return

        async with get_connection() as conn:
            cur = await conn.execute(
                "SELECT id, channel_id, prize, winners_count, ended FROM giveaways WHERE message_id = ? AND guild_id = ?",
                (m_id, ctx.guild.id)
            )
            gw = await cur.fetchone()
            await cur.close()

            if not gw:
                await ctx.send("❌ No giveaway found matching that message ID.", ephemeral=True)
                return

            cur = await conn.execute("SELECT user_id FROM giveaway_entries WHERE giveaway_id = ?", (gw["id"],))
            rows = await cur.fetchall()
            await cur.close()
            entrant_ids = [r["user_id"] for r in rows]

        if not entrant_ids:
            await ctx.send("❌ Cannot reroll: There were no valid entrants in that giveaway.", ephemeral=True)
            return

        num_winners = winners if (winners and winners > 0) else gw["winners_count"]
        picked_ids = random.sample(entrant_ids, min(num_winners, len(entrant_ids)))
        mentions = [f"<@{uid}>" for uid in picked_ids]

        channel = ctx.guild.get_channel(gw["channel_id"]) or ctx.channel
        await channel.send(
            f"🎲 **Reroll Results**: Congratulations {', '.join(mentions)}! You are the new winner(s) for **{gw['prize']}**! 🎉"
        )
        if ctx.channel.id != channel.id:
            await ctx.send(f"✅ Rerolled **{len(picked_ids)}** new winner(s) in {channel.mention}!", ephemeral=True)

    @commands.command(name="greroll")
    @commands.guild_only()
    async def greroll_prefix(self, ctx: commands.Context, message_id: str, winners: Optional[int] = None):
        """Shortcut command to reroll a giveaway winner."""
        await self.g_reroll(ctx, message_id=message_id, winners=winners)

    @giveaway_group.command(name="list")
    @commands.guild_only()
    async def g_list(self, ctx: commands.Context):
        """List all active giveaways in this server."""
        async with get_connection() as conn:
            cur = await conn.execute(
                "SELECT id, channel_id, message_id, prize, winners_count, end_time "
                "FROM giveaways WHERE guild_id = ? AND ended = 0 ORDER BY id DESC",
                (ctx.guild.id,)
            )
            rows = await cur.fetchall()
            await cur.close()

        if not rows:
            await ctx.send("ℹ️ There are currently no active giveaways running in this server.", ephemeral=True)
            return

        entries = []
        for r in rows:
            try:
                dt = datetime.fromisoformat(r["end_time"])
                ts = int(dt.timestamp())
                entries.append(
                    f"• **{r['prize']}** in <#{r['channel_id']}>\n"
                    f"  Ends: <t:{ts}:R> | Winners: `{r['winners_count']}` | Msg ID: `{r['message_id']}`"
                )
            except Exception:
                entries.append(f"• **{r['prize']}** in <#{r['channel_id']}> (ID: `{r['message_id']}`)")

        embed = discord.Embed(
            title=f"🎉 Active Giveaways — {ctx.guild.name}",
            description="\n\n".join(entries),
            color=discord.Color.blurple()
        )
        set_owner_footer(embed, self.bot)
        await ctx.send(embed=embed)

    @commands.command(name="glist")
    @commands.guild_only()
    async def glist_prefix(self, ctx: commands.Context):
        """Shortcut command to list active giveaways."""
        await self.g_list(ctx)

    @giveaway_group.command(name="delete", aliases=["cancel"])
    @commands.guild_only()
    async def g_delete(self, ctx: commands.Context, message_id: str):
        """Delete/cancel a giveaway from the database."""
        if not await self._is_staff_or_owner(ctx):
            await ctx.send("❌ You need **Manage Server** permission to delete giveaways.", ephemeral=True)
            return

        try:
            m_id = int(message_id.strip())
        except ValueError:
            await ctx.send("❌ Invalid message ID provided.", ephemeral=True)
            return

        async with get_connection() as conn:
            cur = await conn.execute("SELECT id, channel_id FROM giveaways WHERE message_id = ? AND guild_id = ?", (m_id, ctx.guild.id))
            gw = await cur.fetchone()
            await cur.close()

            if not gw:
                await ctx.send("❌ No giveaway found matching that message ID.", ephemeral=True)
                return

            await conn.execute("DELETE FROM giveaway_entries WHERE giveaway_id = ?", (gw["id"],))
            await conn.execute("DELETE FROM giveaways WHERE id = ?", (gw["id"],))
            await conn.commit()

        # Try to delete message if possible
        channel = ctx.guild.get_channel(gw["channel_id"])
        if channel:
            try:
                msg = await channel.fetch_message(m_id)
                await msg.delete()
            except Exception:
                pass

        await ctx.send(f"🗑️ Giveaway (`{m_id}`) cancelled and removed.", ephemeral=True)

    @commands.command(name="gdelete", aliases=["gcancel"])
    @commands.guild_only()
    async def gdelete_prefix(self, ctx: commands.Context, message_id: str):
        """Shortcut command to delete a giveaway."""
        await self.g_delete(ctx, message_id=message_id)


async def setup(bot: commands.Bot):
    cog = GiveawayCog(bot)
    await bot.add_cog(cog)

    # Register persistent views for all active giveaways in database
    try:
        async with get_connection() as conn:
            cur = await conn.execute("SELECT id FROM giveaways WHERE ended = 0")
            rows = await cur.fetchall()
            await cur.close()
            for r in rows:
                bot.add_view(GiveawayView(r["id"]))
    except Exception as e:
        logger.debug("Failed to register persistent giveaway views on boot: %s", e)
