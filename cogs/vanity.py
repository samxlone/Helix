import logging
from typing import Optional
import discord
from discord.ext import commands, tasks

from utils.vanity_service import (
    check_discord_vanity,
    clean_vanity_code,
    add_vanity_tracker,
    remove_vanity_tracker,
    get_user_vanity_trackers,
    get_all_vanity_trackers,
)

logger = logging.getLogger(__name__)


class VanityCog(commands.Cog):
    """Check and track Discord vanity URLs for availability alerts."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.check_tracked_vanities_loop.start()

    def cog_unload(self):
        self.check_tracked_vanities_loop.cancel()

    @tasks.loop(seconds=60)
    async def check_tracked_vanities_loop(self):
        """Background worker that periodically checks tracked vanities and DMs users when available."""
        try:
            trackers = await get_all_vanity_trackers()
            if not trackers:
                return

            # Group trackers by vanity code to minimize API calls
            vanity_to_users = {}
            for t in trackers:
                vanity_to_users.setdefault(t["vanity"], []).append(t["user_id"])

            for code, user_ids in vanity_to_users.items():
                status, data = await check_discord_vanity(code)
                if status == "available":
                    # Vanity is available! Notify all tracking users via DM
                    embed = discord.Embed(
                        title="🎉 VANITY ALERT: URL AVAILABLE!",
                        description=(
                            f"The vanity URL **`discord.gg/{code}`** has just become **AVAILABLE**!\n\n"
                            f"🔗 **Claim URL**: `https://discord.gg/{code}`\n\n"
                            f"⚡ *Go claim it on your server before someone else does!*"
                        ),
                        color=discord.Color.green()
                    )
                    embed.set_footer(text="Helix Vanity Tracker • Notification delivered")

                    for uid in user_ids:
                        try:
                            user = self.bot.get_user(uid) or await self.bot.fetch_user(uid)
                            if user:
                                await user.send(embed=embed)
                        except Exception as e:
                            logger.warning("Could not DM user %s for vanity alert %s: %s", uid, code, e)
                        finally:
                            # Remove tracker entry after notification
                            await remove_vanity_tracker(uid, code)
        except Exception as e:
            logger.exception("Error in vanity tracker background loop: %s", e)

    @check_tracked_vanities_loop.before_loop
    async def before_check_loop(self):
        await self.bot.wait_until_ready()

    @commands.hybrid_group(name="vanity", invoke_without_command=True)
    async def vanity_group(self, ctx: commands.Context):
        """Check and track Discord vanity URLs for availability alerts."""
        await ctx.send_help(ctx.command)

    async def _checkvanity_impl(self, ctx: commands.Context, vanity: str):
        code = clean_vanity_code(vanity)
        if not code:
            await ctx.send("❌ Please provide a valid vanity URL or code (e.g. `!checkvanity helix`).", ephemeral=True)
            return

        status, data = await check_discord_vanity(code)

        if status == "available":
            embed = discord.Embed(
                title="🟢 Vanity Available!",
                description=(
                    f"The vanity URL **`discord.gg/{code}`** is **100% AVAILABLE** to claim!\n\n"
                    f"🔗 **Invite Link**: `https://discord.gg/{code}`"
                ),
                color=discord.Color.green()
            )
            embed.set_footer(text=f"Checked by {ctx.author.display_name}")
            await ctx.send(embed=embed)

        elif status == "taken":
            guild_name = data.get("name", "Unknown Server")
            members = data.get("approximate_member_count", 0)
            online = data.get("approximate_presence_count", 0)
            icon_url = f"https://cdn.discordapp.com/icons/{data['guild_id']}/{data['icon']}.png" if data.get("icon") else None

            embed = discord.Embed(
                title="🔴 Vanity Taken",
                description=(
                    f"The vanity URL **`discord.gg/{code}`** is currently **TAKEN** by **{guild_name}**.\n\n"
                    f"👥 **Members**: `{members:,}` | 🟢 **Online**: `{online:,}`\n"
                    f"💡 *Tip: Use `!trackvanity {code}` to get a DM as soon as it becomes available!*"
                ),
                color=discord.Color.red()
            )
            if icon_url:
                embed.set_thumbnail(url=icon_url)
            embed.set_footer(text=f"Checked by {ctx.author.display_name}")
            await ctx.send(embed=embed)

        elif status == "invalid":
            await ctx.send(f"❌ `{code}` is not a valid vanity format. Vanity codes must be 2-32 alphanumeric characters.", ephemeral=True)

        else:
            err_msg = data.get("message") if data else "Unknown error"
            await ctx.send(f"⚠️ Could not check vanity `{code}`: {err_msg}", ephemeral=True)

    @vanity_group.command(name="check")
    async def vanity_check_sub(self, ctx: commands.Context, *, vanity: str):
        await self._checkvanity_impl(ctx, vanity)

    @commands.command(name="checkvanity", aliases=["vanitycheck"])
    async def checkvanity(self, ctx: commands.Context, *, vanity: str):
        """Check if a Discord vanity URL / invite code is available or taken."""
        await self._checkvanity_impl(ctx, vanity)

    async def _trackvanity_impl(self, ctx: commands.Context, vanity: str):
        code = clean_vanity_code(vanity)
        if not code:
            await ctx.send("❌ Please provide a valid vanity URL or code (e.g. `!trackvanity helix`).", ephemeral=True)
            return

        status, data = await check_discord_vanity(code)
        if status == "available":
            embed = discord.Embed(
                title="🎉 Vanity Already Available!",
                description=(
                    f"The vanity URL **`discord.gg/{code}`** is ALREADY **AVAILABLE** right now!\n\n"
                    f"🔗 **Claim Link**: `https://discord.gg/{code}`\n\n"
                    f"Go claim it immediately on your server!"
                ),
                color=discord.Color.green()
            )
            await ctx.send(embed=embed)
            return

        success, msg = await add_vanity_tracker(ctx.author.id, code)
        if not success:
            await ctx.send(f"❌ {msg}", ephemeral=True)
            return

        embed = discord.Embed(
            title="📡 Vanity Tracking Active",
            description=(
                f"Now tracking **`discord.gg/{code}`** for {ctx.author.mention}!\n\n"
                f"🔔 **Notification**: As soon as this vanity becomes available, Helix will send you a **Direct Message**!\n"
                f"📋 View tracked vanities anytime using `!myvanities`."
            ),
            color=discord.Color.blue()
        )
        embed.set_footer(text="Ensure your DMs are open to receive alerts!")
        await ctx.send(embed=embed)

    @vanity_group.command(name="track")
    async def vanity_track_sub(self, ctx: commands.Context, *, vanity: str):
        await self._trackvanity_impl(ctx, vanity)

    @commands.command(name="trackvanity", aliases=["vanitytrack"])
    async def trackvanity(self, ctx: commands.Context, *, vanity: str):
        """Track a vanity URL and receive a DM when it becomes available."""
        await self._trackvanity_impl(ctx, vanity)

    async def _untrackvanity_impl(self, ctx: commands.Context, vanity: str):
        code = clean_vanity_code(vanity)
        removed = await remove_vanity_tracker(ctx.author.id, code)
        if removed:
            await ctx.send(f"✅ Stopped tracking vanity `discord.gg/{code}`.")
        else:
            await ctx.send(f"❌ You were not tracking `discord.gg/{code}`.", ephemeral=True)

    @vanity_group.command(name="untrack")
    async def vanity_untrack_sub(self, ctx: commands.Context, *, vanity: str):
        await self._untrackvanity_impl(ctx, vanity)

    @commands.command(name="untrackvanity", aliases=["vanityuntrack"])
    async def untrackvanity(self, ctx: commands.Context, *, vanity: str):
        """Stop tracking a vanity URL."""
        await self._untrackvanity_impl(ctx, vanity)

    async def _myvanities_impl(self, ctx: commands.Context):
        trackers = await get_user_vanity_trackers(ctx.author.id)

        embed = discord.Embed(
            title=f"📡 Tracked Vanities for {ctx.author.display_name}",
            color=discord.Color.purple()
        )

        if not trackers:
            embed.description = "You are not tracking any vanities currently.\nUse `!trackvanity <code` to start tracking!"
        else:
            lines = [f"• **`discord.gg/{code}`** (`!untrackvanity {code}`)" for code in trackers]
            embed.description = f"Currently tracking **{len(trackers)}** vanity URLs:\n\n" + "\n".join(lines)

        embed.set_footer(text="Helix will DM you immediately when any tracked vanity opens up.")
        await ctx.send(embed=embed)

    @vanity_group.command(name="list")
    async def vanity_list_sub(self, ctx: commands.Context):
        await self._myvanities_impl(ctx)

    @commands.command(name="myvanities", aliases=["trackedvanities", "vanities"])
    async def myvanities(self, ctx: commands.Context):
        """List all vanity URLs you are currently tracking."""
        await self._myvanities_impl(ctx)



async def setup(bot: commands.Bot):
    await bot.add_cog(VanityCog(bot))
