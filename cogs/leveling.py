from typing import Optional, Union
import re
import logging
from discord.ext import commands
import discord
from discord import app_commands
from utils.leveling import award_xp, get_level_info, xp_needed_for_next, get_user_rank, get_level_leaderboard
from utils.config_service import get_guild_config, set_guild_config

logger = logging.getLogger(__name__)


class LevelSelect(discord.ui.Select):
    def __init__(self, bot, caller_id: int):
        options = [
            discord.SelectOption(label="Top 10 Levelers", value="10", emoji="🏆", description="View top 10 highest level members"),
            discord.SelectOption(label="Top 30 Levelers", value="30", emoji="🥇", description="View top 30 highest level members"),
            discord.SelectOption(label="Top 50 Levelers", value="50", emoji="🥈", description="View top 50 highest level members"),
            discord.SelectOption(label="Top 100 Levelers", value="100", emoji="🥉", description="View top 100 highest level members"),
        ]
        super().__init__(placeholder="Select level leaderboard range...", min_values=1, max_values=1, options=options)
        self.bot = bot
        self.caller_id = caller_id

    async def callback(self, interaction: discord.Interaction):
        limit = int(self.values[0])
        leaderboard_data = await get_level_leaderboard(limit=limit)
        caller_level, caller_xp = await get_level_info(self.caller_id)
        caller_rank = await get_user_rank(self.caller_id)

        medals = {1: "🥇", 2: "🥈", 3: "🥉"}

        lines = []
        for i, item in enumerate(leaderboard_data, start=1):
            uid = item["user_id"]
            lvl = item["level"]
            xp = item["xp"]
            medal = medals.get(i, f"`#{i}`")
            user_obj = self.bot.get_user(uid)
            user_name = user_obj.display_name if user_obj else f"<@{uid}>"
            lines.append(f"{medal} **{user_name}** — Level **{lvl}** *(XP: {xp:,})*")

        description_text = "\n".join(lines[:limit]) if lines else "No leveling data available yet."
        if len(description_text) > 3900:
            description_text = description_text[:3850] + "\n*...list truncated for length*"

        embed = discord.Embed(
            title=f"⭐ Chat Level Leaderboard (Top {limit})",
            description=description_text,
            color=discord.Color.from_rgb(0, 180, 216)
        )

        embed.add_field(
            name="📌 Your Server Rank",
            value=f"Position: **#{caller_rank:,}** • Level: **{caller_level}** (XP: **{caller_xp:,}**)",
            inline=False
        )
        embed.set_footer(text=f"Requested by {interaction.user.display_name}")
        await interaction.response.edit_message(embed=embed, view=self.view)


class LevelView(discord.ui.View):
    def __init__(self, bot, caller_id: int):
        super().__init__(timeout=180)
        self.add_item(LevelSelect(bot, caller_id=caller_id))


class LevelingCog(commands.Cog):
    """Handles awarding XP and level-up role rewards."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="levels", aliases=["toplevels", "topxp", "ranks", "levelsboard"])
    @commands.guild_only()
    async def levels(self, ctx: commands.Context):
        """Displays the Chat Level Leaderboard with top members and user rank."""
        leaderboard_data = await get_level_leaderboard(limit=5)
        caller_level, caller_xp = await get_level_info(ctx.author.id)
        caller_rank = await get_user_rank(ctx.author.id)

        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        lines = []
        for i, item in enumerate(leaderboard_data, start=1):
            uid = item["user_id"]
            lvl = item["level"]
            xp = item["xp"]
            medal = medals.get(i, f"`#{i}`")

            user_obj = self.bot.get_user(uid)
            user_name = user_obj.display_name if user_obj else f"<@{uid}>"
            lines.append(f"{medal} **{user_name}** — Level **{lvl}** *(XP: {xp:,})*")

        desc_text = "\n".join(lines) if lines else "No leveling data recorded yet."

        embed = discord.Embed(
            title="⭐ Chat Level Leaderboard",
            description=desc_text,
            color=discord.Color.from_rgb(0, 180, 216)
        )
        if ctx.guild and ctx.guild.icon:
            embed.set_thumbnail(url=ctx.guild.icon.url)

        embed.add_field(
            name="📌 Your Server Rank",
            value=f"Position: **#{caller_rank:,}** • Level: **{caller_level}** (XP: **{caller_xp:,}**)",
            inline=False
        )
        embed.set_footer(text=f"Requested by {ctx.author.display_name} • Select dropdown below for Top 10-100")

        view = LevelView(self.bot, caller_id=ctx.author.id)
        await ctx.send(embed=embed, view=view)


    @commands.hybrid_command(name="rank", aliases=["level", "lvl"])
    @commands.guild_only()
    async def rank(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        """Display the level rank card for yourself or another member."""
        target = member or ctx.author
        level, current_xp = await get_level_info(target.id)
        needed_xp = xp_needed_for_next(level)
        rank_pos = await get_user_rank(target.id)

        pct = min(1.0, max(0.0, current_xp / needed_xp)) if needed_xp > 0 else 0.0
        bar_length = 10
        filled = int(round(pct * bar_length))
        bar = "▰" * filled + "▱" * (bar_length - filled)
        pct_formatted = f"{int(pct * 100)}%"

        def fmt(num: int) -> str:
            if num >= 1_000_000:
                return f"{num / 1_000_000:.1f}M"
            elif num >= 1_000:
                return f"{num / 1_000:.1f}K"
            return f"{num:,}"

        embed = discord.Embed(
            title=f"Level & Rank — {target.display_name}",
            color=discord.Color.from_rgb(0, 180, 216)
        )
        embed.set_thumbnail(url=target.display_avatar.url)

        stats_str = (
            f"**Level:** `{level}`  •  **XP:** `{fmt(current_xp)} / {fmt(needed_xp)}`  •  **Rank:** `#{rank_pos:,}`\n\n"
            f"**Progress:** [{bar}] `{pct_formatted}`"
        )
        embed.description = stats_str
        embed.set_footer(text=f"Requested by {ctx.author.display_name}")

        await ctx.send(embed=embed)

    @commands.Cog.listener("on_message")

    async def on_message(self, message):
        # Ignore bots and DMs
        if message.author.bot:
            return
        if not message.guild:
            return

        # Award a small fixed XP
        try:
            cfg = await get_guild_config(message.guild.id)
            if not cfg.get("xp_enabled", True):
                return

            # Check ignored users
            ignored_users = cfg.get("ignored_xp_users") or []
            if message.author.id in ignored_users:
                return

            # Check ignored channels
            ignored_channels = cfg.get("ignored_xp_channels") or []
            if message.channel.id in ignored_channels:
                return

            leveled, old, new = await award_xp(message.author.id, 10)
            if leveled:
                # Target channel for level-up notifications
                target_channel = message.channel
                level_channel_id = cfg.get("level_channel_id")
                if level_channel_id:
                    ch = message.guild.get_channel(int(level_channel_id))
                    if ch:
                        target_channel = ch

                try:
                    await target_channel.send(f"🎉 Congrats {message.author.mention}, you leveled up to level **{new}**!")
                except Exception:
                    pass

                # check for role reward mapping in guild config
                try:
                    cfg = await get_guild_config(message.guild.id)
                    rewards = cfg.get("level_rewards") or {}
                    role_id = None
                    if isinstance(rewards, dict):
                        role_id = rewards.get(str(new)) or rewards.get(new)
                    if role_id:
                        try:
                            role = message.guild.get_role(int(role_id))
                            if role:
                                await message.author.add_roles(role, reason="Level reward")
                        except Exception:
                            logger.exception("Failed to assign level reward role")
                except Exception:
                    logger.exception("Failed to check level rewards config")
        except Exception:
            logger.exception("Failed to award xp")

    @commands.hybrid_command(name="setlevelchannel", aliases=["levelchannel", "set_level_channel", "level_channel"])
    @commands.guild_only()
    async def setlevelchannel(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None, option: Optional[str] = None):
        """Set or reset the channel where level-up notifications are sent (Admins/Owners only)."""
        is_allowed = (
            ctx.author.guild_permissions.manage_guild
            or ctx.author.guild_permissions.administrator
            or getattr(ctx.guild, "owner_id", None) == ctx.author.id
        )
        if not is_allowed:
            is_owner = await self.bot.is_owner(ctx.author)
            if not is_owner:
                await ctx.send("❌ You need the **Manage Server** or **Administrator** permission to configure level notification channels.", ephemeral=True)
                return

        opt_str = (option or "").lower().strip()
        if not channel and ctx.message and ctx.message.content:
            words = ctx.message.content.strip().split()[1:]
            if words:
                opt_str = words[0].lower().strip()

        if opt_str in ("reset", "off", "clear", "none", "disable", "default"):
            await set_guild_config(ctx.guild.id, {"level_channel_id": None})
            await ctx.send("✅ Level-up notifications reset to default (will be sent in the channel where members chat).")
            return

        if opt_str == "current" or (not channel and not opt_str):
            target_ch = ctx.channel
        else:
            target_ch = channel

        if not target_ch or not hasattr(target_ch, "id"):
            await ctx.send("❌ Please mention a valid text channel or type `reset` to set back to default. Usage: `!setlevelchannel #bot-commands`", ephemeral=True)
            return


        await set_guild_config(ctx.guild.id, {"level_channel_id": target_ch.id})
        await ctx.send(f"✅ Level-up notifications will now be sent to {target_ch.mention}!")

    @commands.hybrid_command(name="ignorexp", aliases=["ignore_xp"])
    @commands.guild_only()
    async def ignorexp(self, ctx: commands.Context, target: Optional[str] = None):
        """Toggle ignoring XP for a member, channel, or server (Admins/Owners only)."""

        is_allowed = (
            ctx.author.guild_permissions.manage_guild
            or ctx.author.guild_permissions.administrator
            or getattr(ctx.guild, "owner_id", None) == ctx.author.id
        )
        if not is_allowed:
            is_owner = await self.bot.is_owner(ctx.author)
            if not is_owner:
                await ctx.send("❌ You need the **Manage Server** or **Administrator** permission to configure ignored XP settings.", ephemeral=True)
                return

        try:
            cfg = await get_guild_config(ctx.guild.id)
            ignored_users = list(cfg.get("ignored_xp_users") or [])
            ignored_channels = list(cfg.get("ignored_xp_channels") or [])

            # If no target passed, show current status
            if not target:
                user_mentions = ", ".join(f"<@{uid}>" for uid in ignored_users) if ignored_users else "*None*"
                channel_mentions = ", ".join(f"<#{cid}>" for cid in ignored_channels) if ignored_channels else "*None*"
                lvl_ch_id = cfg.get("level_channel_id")
                lvl_ch_str = f"<#{lvl_ch_id}>" if lvl_ch_id else "*Default (chat channel)*"
                status_str = "Enabled ✅" if cfg.get("xp_enabled", True) else "Disabled ❌"

                embed = discord.Embed(
                    title=f"⚙️ Leveling Configuration — {ctx.guild.name}",
                    color=discord.Color.blurple()
                )
                embed.add_field(name="XP System Status", value=status_str, inline=True)
                embed.add_field(name="Level Notification Channel", value=lvl_ch_str, inline=True)
                embed.add_field(name=f"Ignored Users ({len(ignored_users)})", value=user_mentions, inline=False)
                embed.add_field(name=f"Ignored Channels ({len(ignored_channels)})", value=channel_mentions, inline=False)
                embed.set_footer(text="Usage: !ignorexp @User | !ignorexp #channel | !ignorexp on/off")
                await ctx.send(embed=embed)
                return

            clean_arg = target.strip()
            lower_arg = clean_arg.lower()

            # String on/off check
            if lower_arg in ("on", "enable", "enabled", "true", "start"):
                await set_guild_config(ctx.guild.id, {"xp_enabled": True})
                await ctx.send("✅ Server XP leveling system is now **enabled**!")
                return
            elif lower_arg in ("off", "disable", "disabled", "false", "stop"):
                await set_guild_config(ctx.guild.id, {"xp_enabled": False})
                await ctx.send("❌ Server XP leveling system is now **disabled**!")
                return

            # 1. Try Channel resolution (mention <#123> or raw channel ID or converter)
            ch_match = re.search(r'<#(\d+)>', clean_arg)
            cid = int(ch_match.group(1)) if ch_match else (int(clean_arg) if clean_arg.isdigit() else None)
            resolved_channel = ctx.guild.get_channel(cid) if (cid and hasattr(ctx.guild, "get_channel")) else None

            if not resolved_channel:
                try:
                    converter = commands.TextChannelConverter()
                    resolved_channel = await converter.convert(ctx, clean_arg)
                except Exception:
                    pass

            if resolved_channel:
                if resolved_channel.id in ignored_channels:
                    ignored_channels.remove(resolved_channel.id)
                    await set_guild_config(ctx.guild.id, {"ignored_xp_channels": ignored_channels})
                    await ctx.send(f"✅ Started counting XP in {resolved_channel.mention} again!")
                else:
                    ignored_channels.append(resolved_channel.id)
                    await set_guild_config(ctx.guild.id, {"ignored_xp_channels": ignored_channels})
                    await ctx.send(f"❌ Stopped counting XP in {resolved_channel.mention}!")
                return

            # 2. Try Member resolution (mention <@123> or raw user ID or converter)
            user_match = re.search(r'<@!?(\d+)>', clean_arg)
            uid = int(user_match.group(1)) if user_match else (int(clean_arg) if clean_arg.isdigit() else None)
            resolved_member = ctx.guild.get_member(uid) if (uid and hasattr(ctx.guild, "get_member")) else None

            if not resolved_member:
                try:
                    converter = commands.MemberConverter()
                    resolved_member = await converter.convert(ctx, clean_arg)
                except Exception:
                    pass

            if resolved_member:
                if resolved_member.id in ignored_users:
                    ignored_users.remove(resolved_member.id)
                    await set_guild_config(ctx.guild.id, {"ignored_xp_users": ignored_users})
                    await ctx.send(f"✅ Started counting XP for {resolved_member.mention} again!")
                else:
                    ignored_users.append(resolved_member.id)
                    await set_guild_config(ctx.guild.id, {"ignored_xp_users": ignored_users})
                    await ctx.send(f"❌ Stopped counting XP for {resolved_member.mention}!")
                return


            await ctx.send("❌ Could not resolve member or channel. Usage: `!ignorexp @User`, `!ignorexp #channel`, or `!ignorexp on/off`.", ephemeral=True)
        except Exception as e:
            logger.exception("Failed to configure ignorexp: %s", e)
            await ctx.send("Failed to configure ignored XP status.", ephemeral=True)



    leveling_group = app_commands.Group(name="leveling", description="Leveling configuration commands")

    @leveling_group.command(name="toggle")
    async def toggle_xp_group(self, interaction: discord.Interaction, enabled: Optional[bool] = None):
        """Enable or disable the XP leveling system on this server."""
        if not interaction.user.guild_permissions.manage_guild and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You don't have permission to manage leveling configuration.", ephemeral=True)
            return
        try:
            cfg = await get_guild_config(interaction.guild.id)
            if enabled is None:
                enabled = not cfg.get("xp_enabled", True)
            await set_guild_config(interaction.guild.id, {"xp_enabled": enabled})
            status = "enabled" if enabled else "disabled"
            await interaction.response.send_message(f"XP leveling system has been **{status}** for this server.")
        except Exception:
            logger.exception("Failed to toggle xp leveling")
            await interaction.response.send_message("Failed to toggle XP leveling system.", ephemeral=True)

    @leveling_group.command(name="set-reward")
    async def set_reward(self, interaction: discord.Interaction, level: int, role: discord.Role):
        if not interaction.user.guild_permissions.manage_guild and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You don't have permission to manage leveling rewards.", ephemeral=True)
            return
        try:
            # store under top-level 'level_rewards' mapping
            await set_guild_config(interaction.guild.id, {"level_rewards": {str(level): int(role.id)}})
            await interaction.response.send_message(f"Set reward for level {level} to role {role.name}.")
        except Exception:
            logger.exception("Failed to set level reward")
            await interaction.response.send_message("Failed to set level reward.", ephemeral=True)

    @leveling_group.command(name="clear-reward")
    async def clear_reward(self, interaction: discord.Interaction, level: int):
        if not interaction.user.guild_permissions.manage_guild and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You don't have permission to manage leveling rewards.", ephemeral=True)
            return
        try:
            # read existing, remove key, write back
            cfg = await get_guild_config(interaction.guild.id)
            existing = cfg.get("level_rewards") or {}
            if str(level) in existing:
                existing.pop(str(level), None)
                await set_guild_config(interaction.guild.id, {"level_rewards": existing})
            await interaction.response.send_message(f"Cleared reward for level {level}.")
        except Exception:
            logger.exception("Failed to clear level reward")
            await interaction.response.send_message("Failed to clear level reward.", ephemeral=True)

    @leveling_group.command(name="set-xp")
    async def set_xp(self, interaction: discord.Interaction, xp_per_message: int):
        """Set XP awarded per message in this guild."""
        if not interaction.user.guild_permissions.manage_guild and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You don't have permission to manage leveling configuration.", ephemeral=True)
            return
        try:
            await set_guild_config(interaction.guild.id, {"xp_per_message": int(xp_per_message)})
            await interaction.response.send_message(f"Set xp per message to {xp_per_message}.")
        except Exception:
            logger.exception("Failed to set xp per message")
            await interaction.response.send_message("Failed to set xp per message.", ephemeral=True)

    @leveling_group.command(name="set-xp-cooldown")
    async def set_xp_cooldown(self, interaction: discord.Interaction, seconds: int):
        """Set per-user cooldown (seconds) between XP awards to prevent spam."""
        if not interaction.user.guild_permissions.manage_guild and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You don't have permission to manage leveling configuration.", ephemeral=True)
            return
        try:
            await set_guild_config(interaction.guild.id, {"xp_cooldown_seconds": int(seconds)})
            await interaction.response.send_message(f"Set xp cooldown to {seconds} seconds.")
        except Exception:
            logger.exception("Failed to set xp cooldown")
            await interaction.response.send_message("Failed to set xp cooldown.", ephemeral=True)

    @commands.hybrid_command(name="togglexp", aliases=["toggle-xp"])
    @commands.guild_only()
    async def togglexp(self, ctx: commands.Context, enabled: Optional[bool] = None):
        """Enable or disable the XP leveling system on this server (Admins/Manage Guild only)"""
        is_allowed = (
            ctx.author.guild_permissions.manage_guild
            or ctx.author.guild_permissions.administrator
            or (getattr(ctx.guild, "owner_id", None) == ctx.author.id)
        )
        if not is_allowed:
            is_owner = await self.bot.is_owner(ctx.author)
            if is_owner:
                is_allowed = True

        if not is_allowed:
            await ctx.send("You don't have permission to manage leveling configuration.", ephemeral=True)
            return

        try:
            cfg = await get_guild_config(ctx.guild.id)
            if enabled is None:
                enabled = not cfg.get("xp_enabled", True)
            await set_guild_config(ctx.guild.id, {"xp_enabled": enabled})
            status = "enabled" if enabled else "disabled"
            await ctx.send(f"XP leveling system is now **{status}** for this server. {'✅' if enabled else '❌'}")
        except Exception as e:
            logger.exception("Failed to toggle XP leveling status: %s", e)
            await ctx.send("Failed to toggle XP leveling system.", ephemeral=True)

    @commands.hybrid_command(name="addxp")
    @commands.guild_only()
    async def addxp(self, ctx: commands.Context, member: discord.Member, amount: int):
        """Add a specified amount of XP to a member (Server/Bot Owner only)"""
        is_allowed = getattr(ctx.guild, "owner_id", None) == ctx.author.id
        if not is_allowed:
            is_owner = await self.bot.is_owner(ctx.author)
            if is_owner:
                is_allowed = True
                
        if not is_allowed:
            await ctx.send("Only the server owner or bot owner can add XP.", ephemeral=True)
            return

        cfg = await get_guild_config(ctx.guild.id)
        if not cfg.get("xp_enabled", True):
            await ctx.send("XP leveling system is currently disabled on this server.", ephemeral=True)
            return
            
        if amount <= 0:
            await ctx.send("Amount of XP must be positive.", ephemeral=True)
            return
            
        try:
            leveled, old, new = await award_xp(member.id, amount)
            await ctx.send(f"Awarded **{amount}** XP to {member.mention}! Current Level: **{new}**")
            
            if leveled:
                try:
                    cfg = await get_guild_config(ctx.guild.id)
                    rewards = cfg.get("level_rewards") or {}
                    role_id = rewards.get(str(new)) or rewards.get(new)
                    if role_id:
                        role = ctx.guild.get_role(int(role_id))
                        if role:
                            await member.add_roles(role, reason="Level reward")
                            await ctx.send(f"🎉 {member.mention} has been awarded the role **{role.name}** for leveling up!")
                except Exception:
                    logger.exception("Failed to assign role reward upon addxp levelup")
        except Exception as e:
            logger.exception("Failed to award xp via addxp command: %s", e)
            await ctx.send("Failed to award XP.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(LevelingCog(bot))

