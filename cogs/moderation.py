import os
import io
import logging

import re
import random
import asyncio
import collections
from datetime import datetime, timedelta, timezone

from typing import Optional, List, Union, Dict, Tuple

import discord

from discord import app_commands, Interaction
from discord.ext import commands

from utils.modlog import log_action, fetch_logs, fetch_logs_for_target
from utils.config_service import get_guild_config, set_guild_config
from utils.db import get_connection

logger = logging.getLogger(__name__)



def parse_duration(duration_str: str) -> Optional[int]:
    """Parse duration string like 5m, 10s, 2h, 1d into seconds. Returns None if invalid format."""
    if not duration_str:
        return None
    match = re.match(r"^(\d+)([smhd]?)$", duration_str.strip().lower())
    if not match:
        return None
    amount = int(match.group(1))
    unit = match.group(2)
    if unit == "s":
        return amount
    elif unit == "m" or not unit:
        return amount * 60
    elif unit == "h":
        return amount * 3600
    elif unit == "d":
        return amount * 86400
    return None


def make_trigger_metadata(**kwargs):
    """Construct AutoMod trigger metadata across discord.py versions."""
    cls = getattr(discord, "AutoModTriggerMetadata", None) or getattr(discord, "AutoModRuleTrigger", None)
    if cls:
        try:
            return cls(**kwargs)
        except Exception:
            pass
    return kwargs


class Moderation(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._vcbomb_tasks: Dict[Tuple[int, int], asyncio.Task] = {}

    def cog_unload(self):
        for task in self._vcbomb_tasks.values():
            task.cancel()
        self._vcbomb_tasks.clear()


    async def _ensure_can_moderate(self, ctx: commands.Context, target: discord.Member) -> Optional[str]:
        # basic checks: cannot moderate yourself or members with higher/equal top role
        if ctx.author.id == target.id:
            return "You cannot moderate yourself."
        # owner bypass
        if ctx.guild.owner_id == ctx.author.id:
            return None
        if ctx.author.top_role <= target.top_role:
            return "You cannot moderate a member with an equal or higher role."
        return None

    @staticmethod
    def _role_assignment_error(guild: discord.Guild, actor: discord.Member, bot_member: discord.Member, role: discord.Role) -> Optional[str]:
        """Return a user-facing reason when a role cannot safely be assigned."""
        if role.is_default():
            return "The @everyone role cannot be assigned."
        if role.managed:
            return "That role is managed by an integration and cannot be assigned manually."
        if actor.id != guild.owner_id and actor.top_role <= role:
            return "You can only assign roles below your highest role."
        if not bot_member or bot_member.top_role <= role:
            return "I can only assign roles below my highest role."
        return None

    @staticmethod
    def _find_role_by_name(guild: discord.Guild, role_query: str) -> tuple[Optional[discord.Role], Optional[str]]:
        """Resolve a role mention, ID, exact case-insensitive role name, or partial role name in this guild."""
        query = role_query.strip()
        if not query:
            return None, "Please specify a valid role name, mention, or ID."

        # 1. Mention or direct ID check
        match = re.search(r"<@&(\d+)>|(\d+)", query)
        if match:
            r_id = int(match.group(1) or match.group(2))
            role = guild.get_role(r_id)
            if role:
                return role, None

        clean_query = query.strip("\"'`").strip()

        # 2. Exact case-insensitive match
        matches = [role for role in guild.roles if role.name.casefold() == clean_query.casefold()]
        if len(matches) == 1:
            return matches[0], None
        if len(matches) > 1:
            return None, f"Multiple roles found matching `{role_query}`. Please use a role mention (<@&id>) or role ID."

        # 3. Partial case-insensitive match fallback (e.g. 'admin' -> 'Administrator', 'Admin 👑')
        partial_matches = [role for role in guild.roles if clean_query.casefold() in role.name.casefold()]
        if len(partial_matches) == 1:
            return partial_matches[0], None
        if len(partial_matches) > 1:
            matching_names = ", ".join(f"**{r.name}**" for r in partial_matches[:5])
            return None, f"Multiple roles matched `{role_query}` ({matching_names}). Please specify the exact role name, mention, or ID."

        return None, f"I could not find a role named `{role_query}` in this server."


    @commands.hybrid_command(name="kick")
    @commands.guild_only()
    async def kick(self, ctx: commands.Context, target: discord.Member, *, reason: Optional[str] = None):
        """Kick a member from the guild"""
        if not ctx.author.guild_permissions.kick_members:
            await ctx.send("You don't have permission to kick members.", ephemeral=True)
            return

        deny = await self._ensure_can_moderate(ctx, target)
        if deny:
            await ctx.send(deny, ephemeral=True)
            return

        try:
            await target.kick(reason=reason)
            case = await log_action(ctx.guild.id, ctx.author.id, target.id, "kick", reason)
            await ctx.send(f"Kicked {target} ({target.id})")
            await self._post_modlog(ctx.guild, case, "Kick", ctx.author, target, reason)
        except Exception as exc:
            logger.exception("Failed to kick: %s", exc)
            await ctx.send(f"Failed to kick {target}", ephemeral=True)

    @commands.hybrid_command(name="ban", aliases=["hackban", "idban"])
    @commands.guild_only()

    async def ban(self, ctx: commands.Context, target: Union[discord.Member, discord.User], *, reason: Optional[str] = None, delete_days: Optional[int] = 0):
        """Ban a member or user (by ID/mention) from the guild even if they are not in the server."""
        if not ctx.author.guild_permissions.ban_members:
            await ctx.send("You don't have permission to ban members.", ephemeral=True)
            return

        # If the target is currently in the guild, run hierarchy checks
        if isinstance(target, discord.Member):
            deny = await self._ensure_can_moderate(ctx, target)
            if deny:
                await ctx.send(deny, ephemeral=True)
                return

        try:
            await ctx.guild.ban(target, reason=reason, delete_message_days=delete_days or 0)
            case = await log_action(ctx.guild.id, ctx.author.id, target.id, "ban", reason)
            await ctx.send(f"✅ Banned {target} (`ID: {target.id}`)")
            await self._post_modlog(ctx.guild, case, "Ban", ctx.author, target, reason)
        except discord.errors.Forbidden:
            await ctx.send("❌ I don't have permission to ban this user.", ephemeral=True)
        except Exception as exc:
            logger.exception("Failed to ban: %s", exc)
            await ctx.send(f"❌ Failed to ban {target}.", ephemeral=True)

    @commands.hybrid_command(name="unban")
    @commands.guild_only()
    async def unban(self, ctx: commands.Context, user: Union[discord.User, discord.Member], *, reason: Optional[str] = None):
        """Unban a user by user object, mention, or ID."""
        if not ctx.author.guild_permissions.ban_members:
            await ctx.send("You don't have permission to unban members.", ephemeral=True)
            return
        try:
            await ctx.guild.unban(user, reason=reason)
            case = await log_action(ctx.guild.id, ctx.author.id, user.id, "unban", reason)
            await ctx.send(f"✅ Unbanned {user} (`ID: {user.id}`)")
            await self._post_modlog(ctx.guild, case, "Unban", ctx.author, user, reason)
        except discord.errors.NotFound as exc:
            if getattr(exc, "code", None) == 10026 or "10026" in str(exc):
                await ctx.send("❌ That user is not banned in this server.", ephemeral=True)
            else:
                await ctx.send(f"❌ Failed to unban {user}: User not found.", ephemeral=True)
        except discord.errors.Forbidden:
            await ctx.send("❌ I need the **Ban Members** permission to unban users.", ephemeral=True)
        except Exception as exc:
            logger.exception("Failed to unban: %s", exc)
            await ctx.send(f"❌ Failed to unban {user}.", ephemeral=True)


    @commands.command(name="softban")
    @commands.guild_only()
    async def softban(self, ctx: commands.Context, target: discord.Member, *, reason: Optional[str] = None, delete_days: Optional[int] = 1):
        """Temporarily ban a member to delete recent messages (ban then unban)"""
        if not ctx.author.guild_permissions.ban_members:
            await ctx.send("You don't have permission to ban members.", ephemeral=True)
            return
        deny = await self._ensure_can_moderate(ctx, target)
        if deny:
            await ctx.send(deny, ephemeral=True)
            return
        try:
            await target.ban(reason=reason, delete_message_days=delete_days or 1)
            await ctx.guild.unban(target, reason="Softban (automatic unban)")
            case = await log_action(ctx.guild.id, ctx.author.id, target.id, "softban", reason)
            await ctx.send(f"Softbanned {target} ({target.id}) — messages removed")
            await self._post_modlog(ctx.guild, case, "Softban", ctx.author, target, reason)
        except Exception as exc:
            logger.exception("Failed to softban: %s", exc)
            await ctx.send(f"Failed to softban {target}", ephemeral=True)

    @commands.command(name="hardban")
    @commands.guild_only()
    async def hardban(self, ctx: commands.Context, target: discord.Member, *, reason: Optional[str] = None, delete_days: Optional[int] = 7):
        """Hard ban a member (ban with maximum message deletion)."""
        if not ctx.author.guild_permissions.ban_members:
            await ctx.send("You don't have permission to ban members.", ephemeral=True)
            return
        deny = await self._ensure_can_moderate(ctx, target)
        if deny:
            await ctx.send(deny, ephemeral=True)
            return
        try:
            await target.ban(reason=reason, delete_message_days=delete_days or 7)
            case = await log_action(ctx.guild.id, ctx.author.id, target.id, "hardban", reason)
            await ctx.send(f"Hardbanned {target} ({target.id})")
            await self._post_modlog(ctx.guild, case, "Hardban", ctx.author, target, reason)
        except Exception as exc:
            logger.exception("Failed to hardban: %s", exc)
            await ctx.send(f"Failed to hardban {target}", ephemeral=True)

    @commands.hybrid_command(name="mute", aliases=["tempmute", "timeout"])
    @commands.guild_only()
    async def mute(self, ctx: commands.Context, target: discord.Member, duration: Optional[str] = "10m", *, reason: Optional[str] = "No reason provided"):
        """Mute or timeout a member in the server with duration and reason."""

        if not (ctx.author.guild_permissions.moderate_members or ctx.author.guild_permissions.manage_roles or ctx.author.guild_permissions.administrator):
            await ctx.send("❌ You don't have permission to mute members.", ephemeral=True)
            return

        deny = await self._ensure_can_moderate(ctx, target)
        if deny:
            await ctx.send(deny, ephemeral=True)
            return

        sec = parse_duration(duration)
        reason_text = reason
        if sec is None:
            reason_text = f"{duration} {reason}".strip() if reason and reason != "No reason provided" else duration
            sec = 600
            duration_desc = "10 minutes"
        else:
            if sec < 60:
                duration_desc = f"{sec} seconds"
            elif sec < 3600:
                duration_desc = f"{sec // 60} minutes"
            elif sec < 86400:
                duration_desc = f"{sec // 3600} hours"
            else:
                duration_desc = f"{sec // 86400} days"

        until = datetime.now(timezone.utc) + timedelta(seconds=sec)

        try:
            await target.edit(timed_out_until=until, reason=f"{reason_text} (by {ctx.author})")
            case = await log_action(ctx.guild.id, ctx.author.id, target.id, "mute", f"Muted for {duration_desc} | Reason: {reason_text}")

            until_ts = int(until.timestamp())
            embed = discord.Embed(
                title="🔇 Member Muted",
                description=f"Successfully muted {target.mention} (`ID: {target.id}`).",
                color=discord.Color.orange(),
                timestamp=datetime.now(timezone.utc)
            )
            embed.add_field(name="Duration", value=f"`{duration_desc}` (until <t:{until_ts}:F>)", inline=False)
            embed.add_field(name="Reason", value=f"> {reason_text}", inline=False)
            embed.set_footer(text=f"Muted by {ctx.author.display_name}")
            await ctx.send(embed=embed)

            await self._post_modlog(ctx.guild, case, "Mute", ctx.author, target, f"Duration: {duration_desc} | Reason: {reason_text}")

            cfg = await get_guild_config(ctx.guild.id)
            if cfg.get("modlog_dm_notifications", True):
                try:
                    dm_embed = discord.Embed(
                        title=f"🔇 Mute Notice — {ctx.guild.name}",
                        description=f"You have been muted in **{ctx.guild.name}** for **{duration_desc}**.",
                        color=discord.Color.orange(),
                        timestamp=datetime.now(timezone.utc)
                    )
                    dm_embed.add_field(name="Mute Expiry", value=f"<t:{until_ts}:F> (<t:{until_ts}:R>)", inline=False)
                    dm_embed.add_field(name="Reason", value=f"> {reason_text}", inline=False)
                    dm_embed.set_footer(text=f"Issued by {ctx.author.name}")
                    await target.send(embed=dm_embed)
                except Exception:
                    pass

        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to mute/timeout that member (role hierarchy issue).", ephemeral=True)
        except Exception as exc:
            logger.exception("Failed to mute member: %s", exc)
            await ctx.send(f"❌ Failed to mute {target.mention}.", ephemeral=True)

    @commands.hybrid_command(name="unmute", aliases=["untimeout"])
    @commands.guild_only()
    async def unmute(self, ctx: commands.Context, target: discord.Member, *, reason: Optional[str] = "No reason provided"):
        """Unmute/untimeout a member in the server."""
        if not (ctx.author.guild_permissions.moderate_members or ctx.author.guild_permissions.manage_roles or ctx.author.guild_permissions.administrator):
            await ctx.send("❌ You don't have permission to unmute members.", ephemeral=True)
            return

        deny = await self._ensure_can_moderate(ctx, target)
        if deny:
            await ctx.send(deny, ephemeral=True)
            return

        try:
            await target.edit(timed_out_until=None, reason=f"{reason} (by {ctx.author})")
            case = await log_action(ctx.guild.id, ctx.author.id, target.id, "unmute", reason)

            embed = discord.Embed(
                title="🔊 Member Unmuted",
                description=f"Successfully unmuted {target.mention} (`ID: {target.id}`).",
                color=discord.Color.green(),
                timestamp=datetime.now(timezone.utc)
            )
            embed.add_field(name="Reason", value=f"> {reason}", inline=False)
            embed.set_footer(text=f"Unmuted by {ctx.author.display_name}")
            await ctx.send(embed=embed)

            await self._post_modlog(ctx.guild, case, "Unmute", ctx.author, target, reason)

            cfg = await get_guild_config(ctx.guild.id)
            if cfg.get("modlog_dm_notifications", True):
                try:
                    dm_embed = discord.Embed(
                        title=f"🔊 Unmute Notice — {ctx.guild.name}",
                        description=f"Your mute/timeout in **{ctx.guild.name}** has been removed.",
                        color=discord.Color.green(),
                        timestamp=datetime.now(timezone.utc)
                    )
                    dm_embed.add_field(name="Reason", value=f"> {reason}", inline=False)
                    dm_embed.set_footer(text=f"Unmuted by {ctx.author.name}")
                    await target.send(embed=dm_embed)
                except Exception:
                    pass

        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to unmute/untimeout that member.", ephemeral=True)
        except Exception as exc:
            logger.exception("Failed to unmute member: %s", exc)
            await ctx.send(f"❌ Failed to unmute {target.mention}.", ephemeral=True)


    async def _process_warn_escalation(self, ctx_or_guild, target: discord.Member, reason: Optional[str] = None, moderator: Optional[discord.User] = None):
        """Log a warning, process automated punishment escalation based on DB warn count, and send DM if enabled."""
        guild = ctx_or_guild if isinstance(ctx_or_guild, discord.Guild) else ctx_or_guild.guild
        mod_user = moderator or (ctx_or_guild.author if hasattr(ctx_or_guild, "author") else (self.bot.user if self.bot else None))
        mod_id = mod_user.id if mod_user else 0
        reason_clean = (reason or "No reason provided. Please follow server rules.").strip()

        # 1. Log warning action to DB
        case = await log_action(guild.id, mod_id, target.id, "warn", reason_clean)

        # 2. Fetch total warning count for user in this guild
        warn_logs = await fetch_logs_for_target(guild.id, target.id, action="warn", limit=1000)
        warn_count = len(warn_logs)

        # 3. Determine escalation tier and upcoming notice
        escalation_action = None
        timeout_duration = None
        upcoming_notice = ""

        if warn_count in (1, 2):
            upcoming_notice = "⚠️ **Warning Notice**: On your 3rd warning, you will receive a **2-Hour Timeout**."
        elif warn_count == 3:
            timeout_duration = timedelta(hours=2)
            escalation_action = "2-Hour Timeout"
            upcoming_notice = "⚠️ **Warning Escalation**: On your 4th warning, you will receive a **1-Day Timeout**."
        elif warn_count == 4:
            timeout_duration = timedelta(days=1)
            escalation_action = "1-Day Timeout"
            upcoming_notice = "⚠️ **Warning Escalation**: On your 5th warning, you will receive a **7-Day Timeout**."
        elif warn_count == 5:
            timeout_duration = timedelta(days=7)
            escalation_action = "7-Day Timeout"
            upcoming_notice = "⚠️ **Warning Escalation**: On your 6th warning, you will receive a **14-Day Timeout**."
        elif warn_count == 6:
            timeout_duration = timedelta(days=14)
            escalation_action = "14-Day Timeout"
            upcoming_notice = "⚠️ **Warning Escalation**: On your 7th warning, you will receive a **28-Day Timeout**."
        elif warn_count == 7:
            timeout_duration = timedelta(days=28)
            escalation_action = "28-Day Timeout"
            upcoming_notice = "🚨 **FINAL WARNING**: On your 8th warning, you will be **KICKED from the server**."
        elif warn_count >= 8:
            escalation_action = "Server Kick"
            upcoming_notice = "🚪 **Server Kick**: You have reached 8 warnings and are being removed from the server."

        # 4. Check DM notification setting for guild (default: True)
        cfg = await get_guild_config(guild.id)
        dms_enabled = cfg.get("modlog_dm_notifications", True)

        # 5. Send DM to member if enabled
        if dms_enabled:
            try:
                dm_embed = discord.Embed(
                    title=f"⚠️ Moderation Notice — {guild.name}",
                    color=discord.Color.red() if warn_count >= 8 else (discord.Color.orange() if timeout_duration else discord.Color.gold()),
                    timestamp=datetime.now(timezone.utc)
                )
                if guild.icon:
                    dm_embed.set_thumbnail(url=guild.icon.url)

                action_title = f"Warning #{warn_count}"
                if escalation_action:
                    action_title += f" ({escalation_action})"

                dm_embed.add_field(name="Action Issued", value=f"`{action_title}`", inline=True)
                dm_embed.add_field(name="Total Warnings", value=f"**{warn_count}** warnings", inline=True)
                dm_embed.add_field(name="Reason", value=f"> {reason_clean}", inline=False)

                if timeout_duration:
                    until_ts = int((datetime.now(timezone.utc) + timeout_duration).timestamp())
                    dm_embed.add_field(name="Timeout Expiry", value=f"<t:{until_ts}:F> (<t:{until_ts}:R>)", inline=False)

                if upcoming_notice:
                    dm_embed.add_field(name="Future Punishment Notice", value=upcoming_notice, inline=False)

                dm_embed.set_footer(text=f"Issued by {mod_user.name if mod_user else 'Server Mod'} • Please follow server rules")
                await target.send(embed=dm_embed)
            except Exception as e:
                logger.warning("Failed to send moderation DM to %s: %s", target.id, e)

        # 6. Apply escalation action in guild
        if timeout_duration and hasattr(target, "timeout"):
            try:
                await target.timeout(timeout_duration, reason=f"Automated Warning Escalation (Warn #{warn_count}): {reason_clean}")
                await log_action(guild.id, self.bot.user.id if self.bot and self.bot.user else 0, target.id, "timeout", f"Auto-escalation for Warn #{warn_count}")
            except Exception as exc:
                logger.warning("Failed to apply auto-timeout escalation to %s: %s", target.id, exc)

        elif warn_count >= 8 and hasattr(target, "kick"):
            try:
                await target.kick(reason=f"Automated Warning Escalation (Warn #{warn_count}): {reason_clean}")
                await log_action(guild.id, self.bot.user.id if self.bot and self.bot.user else 0, target.id, "kick", f"Auto-kick for Warn #{warn_count}")
            except Exception as exc:
                logger.warning("Failed to apply auto-kick escalation to %s: %s", target.id, exc)

        return case, warn_count, escalation_action

    @commands.hybrid_command(name="warn")
    @commands.guild_only()
    async def warn(self, ctx: commands.Context, target: discord.Member, *, reason: Optional[str] = "No reason provided. Please follow server rules."):
        """Warn a member"""
        if not (ctx.author.guild_permissions.kick_members or ctx.author.guild_permissions.manage_messages):
            await ctx.send("You don't have permission to warn members.", ephemeral=True)
            return

        deny = await self._ensure_can_moderate(ctx, target)
        if deny:
            await ctx.send(deny, ephemeral=True)
            return

        try:
            case, warn_count, escalation_action = await self._process_warn_escalation(ctx, target, reason, moderator=ctx.author)

            msg = f"⚠️ Warned {target.mention} (`ID: {target.id}`). **Warning #{warn_count}**."
            if escalation_action:
                msg += f"\n🔨 **Automated Escalation**: Applied **{escalation_action}**."

            await ctx.send(msg)
            await self._post_modlog(ctx.guild, case, "Warn", ctx.author, target, f"Warn #{warn_count} | Reason: {reason}")
        except Exception as exc:
            logger.exception("Failed to warn: %s", exc)
            await ctx.send("Failed to warn member.", ephemeral=True)


    @commands.hybrid_command(name="warns")
    @commands.guild_only()
    async def warns(self, ctx: commands.Context, target: discord.Member, limit: Optional[int] = 10):
        """View recent warnings for a member"""
        if not (ctx.author.guild_permissions.view_audit_log or ctx.author.guild_permissions.manage_guild):
            await ctx.send("You don't have permission to view warns.", ephemeral=True)
            return

        try:
            logs = await fetch_logs_for_target(ctx.guild.id, target.id, action="warn", limit=limit)
            if not logs:
                await ctx.send("No warnings for this user.", ephemeral=True)
                return
            lines = [f"[{l['created_at']}] by={l['moderator_id']} reason={l['reason']}" for l in logs]
            text = "\n".join(lines)
            if len(text) > 1900:
                await ctx.send("Warnings are large, sending as file...")
                bio = io.BytesIO(text.encode("utf-8"))
                bio.seek(0)
                await ctx.send(file=discord.File(fp=bio, filename=f"warns_{target.id}.txt"), ephemeral=True)
            else:
                await ctx.send(f"Warnings for {target}:\n```\n{text}\n```", ephemeral=True)
        except Exception as exc:
            logger.exception("Failed to fetch warns: %s", exc)
            await ctx.send("Failed to fetch warns.", ephemeral=True)

    @commands.hybrid_command(name="lock")
    @commands.guild_only()
    async def lock(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        """Lock a text channel (disables sending messages for @everyone)"""
        if not ctx.author.guild_permissions.manage_channels:
            await ctx.send("You don't have permission to manage channels.", ephemeral=True)
            return
        channel = channel or ctx.channel
        try:
            everyone = ctx.guild.default_role
            await channel.set_permissions(everyone, send_messages=False)
            case = await log_action(ctx.guild.id, ctx.author.id, 0, "lock", f"channel={channel.id}")
            await ctx.send(f"Locked {channel.mention}")
            await self._post_modlog(ctx.guild, case, "Lock", ctx.author, channel, f"channel={channel.id}")
        except Exception as exc:
            logger.exception("Failed to lock channel: %s", exc)
            await ctx.send("Failed to lock channel.", ephemeral=True)

    @commands.hybrid_command(name="unlock")
    @commands.guild_only()
    async def unlock(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        """Unlock a text channel (restores default sending permissions)"""
        if not ctx.author.guild_permissions.manage_channels:
            await ctx.send("You don't have permission to manage channels.", ephemeral=True)
            return
        channel = channel or ctx.channel
        try:
            everyone = ctx.guild.default_role
            await channel.set_permissions(everyone, send_messages=None)
            case = await log_action(ctx.guild.id, ctx.author.id, 0, "unlock", f"channel={channel.id}")
            await ctx.send(f"Unlocked {channel.mention}")
            await self._post_modlog(ctx.guild, case, "Unlock", ctx.author, channel, f"channel={channel.id}")
        except Exception as exc:
            logger.exception("Failed to unlock channel: %s", exc)
            await ctx.send("Failed to unlock channel.", ephemeral=True)

    @commands.hybrid_command(name="hide")
    @commands.guild_only()
    async def hide(
        self,
        ctx: commands.Context,
        channel: Optional[Union[discord.TextChannel, discord.VoiceChannel, discord.StageChannel]] = None,
    ):
        """Hide a text, voice, or stage channel from @everyone."""
        if not ctx.author.guild_permissions.manage_channels:
            await ctx.send("You don't have permission to manage channels.", ephemeral=True)
            return

        channel = channel or ctx.channel
        if not isinstance(channel, (discord.TextChannel, discord.VoiceChannel, discord.StageChannel)):
            await ctx.send("Choose a text, voice, or stage channel to hide.", ephemeral=True)
            return

        try:
            everyone = ctx.guild.default_role
            await channel.set_permissions(everyone, view_channel=False, reason=f"Hidden by {ctx.author} ({ctx.author.id})")
            case = await log_action(ctx.guild.id, ctx.author.id, 0, "hide", f"channel={channel.id}")
            await ctx.send(f"Hidden {channel.mention} from @everyone.")
            await self._post_modlog(ctx.guild, case, "Hide", ctx.author, channel, f"channel={channel.id}")
        except discord.Forbidden:
            await ctx.send("I need the **Manage Channels** permission to hide that channel.", ephemeral=True)
        except Exception as exc:
            logger.exception("Failed to hide channel: %s", exc)
            await ctx.send("Failed to hide channel.", ephemeral=True)

    @commands.hybrid_command(name="unhide")
    @commands.guild_only()
    async def unhide(
        self,
        ctx: commands.Context,
        channel: Optional[Union[discord.TextChannel, discord.VoiceChannel, discord.StageChannel]] = None,
    ):
        """Restore @everyone's normal channel visibility."""
        if not ctx.author.guild_permissions.manage_channels:
            await ctx.send("You don't have permission to manage channels.", ephemeral=True)
            return

        channel = channel or ctx.channel
        if not isinstance(channel, (discord.TextChannel, discord.VoiceChannel, discord.StageChannel)):
            await ctx.send("Choose a text, voice, or stage channel to unhide.", ephemeral=True)
            return

        try:
            everyone = ctx.guild.default_role
            # None removes this channel-specific override and restores its category/default visibility.
            await channel.set_permissions(everyone, view_channel=None, reason=f"Unhidden by {ctx.author} ({ctx.author.id})")
            case = await log_action(ctx.guild.id, ctx.author.id, 0, "unhide", f"channel={channel.id}")
            await ctx.send(f"Unhid {channel.mention}; its normal visibility has been restored.")
            await self._post_modlog(ctx.guild, case, "Unhide", ctx.author, channel, f"channel={channel.id}")
        except discord.Forbidden:
            await ctx.send("I need the **Manage Channels** permission to unhide that channel.", ephemeral=True)
        except Exception as exc:
            logger.exception("Failed to unhide channel: %s", exc)
            await ctx.send("Failed to unhide channel.", ephemeral=True)

    @commands.hybrid_command(name="purge", aliases=["clean", "purgeuser"])
    @commands.guild_only()
    async def purge(
        self,
        ctx: commands.Context,
        arg1: Optional[str] = None,
        arg2: Optional[str] = None
    ):
        """Bulk delete messages from current channel (optionally filtered by user)."""

        if not ctx.author.guild_permissions.manage_messages and not ctx.author.guild_permissions.administrator:
            await ctx.send("❌ You don't have permission to manage messages.", ephemeral=True)
            return

        target_user_id: Optional[int] = None
        target_user_str: Optional[str] = None
        amount: int = 10

        def is_amount(val: Optional[str]) -> bool:
            if not val or not val.isdigit():
                return False
            n = int(val)
            return 1 <= n <= 1000

        async def resolve_user(val: Optional[str]) -> Tuple[Optional[int], Optional[str]]:
            if not val:
                return None, None
            val_clean = val.strip()
            clean_id = val_clean.replace("<@", "").replace(">", "").replace("!", "").replace("&", "")

            # 1. Snowflake User ID (works even if user left the server)
            if clean_id.isdigit():
                uid = int(clean_id)
                mem = ctx.guild.get_member(uid)
                if mem:
                    return mem.id, f"{mem.mention}"
                try:
                    user_fetched = await self.bot.fetch_user(uid)
                    if user_fetched:
                        return user_fetched.id, f"**{user_fetched.name}** (`ID: {uid}`)"
                except Exception:
                    pass
                return uid, f"`ID: {uid}`"

            # 2. Guild members cache lookup by username / display_name
            val_lower = val_clean.lower()
            for m in ctx.guild.members:
                if (m.name and m.name.lower() == val_lower) or \
                   (m.display_name and m.display_name.lower() == val_lower) or \
                   (str(m).lower() == val_lower):
                    return m.id, f"{m.mention}"

            # 3. MemberConverter fallback
            try:
                converter = commands.MemberConverter()
                mem = await converter.convert(ctx, val_clean)
                if mem:
                    return mem.id, f"{mem.mention}"
            except Exception:
                pass

            return None, None

        if is_amount(arg1):
            amount = int(arg1)
            if arg2:
                target_user_id, target_user_str = await resolve_user(arg2)
        elif arg1:
            target_user_id, target_user_str = await resolve_user(arg1)
            if is_amount(arg2):
                amount = int(arg2)
        else:
            amount = 10

        if target_user_id is None and arg1 and not is_amount(arg1):
            await ctx.send(f"❌ Could not find user **`{arg1}`** in this server or Discord. Try passing their User ID.", ephemeral=True)
            return

        if getattr(ctx, "interaction", None) is not None:
            try:
                await ctx.defer(ephemeral=True)
            except Exception:
                pass


        def check_msg(msg: discord.Message) -> bool:
            if target_user_id:
                return msg.author.id == target_user_id
            return True

        try:
            search_limit = min(amount * 15 if target_user_id else amount, 1000)
            deleted = await ctx.channel.purge(limit=search_limit, check=check_msg)

            if target_user_id and len(deleted) > amount:
                deleted = deleted[:amount]

            user_desc = f" sent by {target_user_str}" if target_user_id else ""
            case = await log_action(ctx.guild.id, ctx.author.id, target_user_id or 0, "purge", f"count={len(deleted)}{user_desc}")
            await ctx.send(f"✅ Successfully deleted **{len(deleted)}** message(s){user_desc}.", ephemeral=True)
            await self._post_modlog(ctx.guild, case, "Purge", ctx.author, ctx.channel, f"count={len(deleted)}{user_desc}")
        except discord.errors.Forbidden:
            await ctx.send("❌ I need the **Manage Messages** permission to purge messages in this channel.", ephemeral=True)
        except Exception as exc:
            logger.exception("Failed to purge messages: %s", exc)
            await ctx.send("❌ Failed to purge messages.", ephemeral=True)





    @commands.hybrid_command(name="giverole", aliases=["role", "addrole", "removerole"])
    @commands.guild_only()
    async def giverole(self, ctx: commands.Context, target: Optional[discord.Member] = None, *, role_name: Optional[str] = None):
        """Toggle a role for a member. If they have it, removes it; otherwise adds it."""
        if not ctx.author.guild_permissions.manage_roles and not ctx.author.guild_permissions.administrator:
            is_owner = await self.bot.is_owner(ctx.author)
            if not is_owner:
                await ctx.send("❌ You need the **Manage Roles** permission to modify roles.", ephemeral=True)
                return

        member_target: Optional[discord.Member] = target
        query: Optional[str] = role_name

        if ctx.message and ctx.message.content:
            raw_args = ctx.message.content.strip().split()[1:]
            if raw_args:
                found_member = None
                remaining_tokens = list(raw_args)
                for idx, token in enumerate(raw_args):
                    match = re.search(r"\d+", token)
                    if match:
                        m_id = int(match.group(0))
                        m = ctx.guild.get_member(m_id)
                        if m:
                            found_member = m
                            remaining_tokens.pop(idx)
                            break
                if found_member:
                    member_target = found_member
                    query = " ".join(remaining_tokens).strip()
                elif member_target is None and len(raw_args) >= 2:
                    try:
                        converter = commands.MemberConverter()
                        member_target = await converter.convert(ctx, raw_args[0])
                        query = " ".join(raw_args[1:]).strip()
                    except Exception:
                        pass

        if not member_target:
            await ctx.send("❌ Could not resolve the target member. Usage: `!role @User RoleName` or `!role <User_ID> <Role_Name>`", ephemeral=True)
            return

        if not query:
            await ctx.send("❌ Please specify a role name, mention, or ID. Usage: `!role @User RoleName`", ephemeral=True)
            return

        role, error = self._find_role_by_name(ctx.guild, query)
        if error:
            await ctx.send(f"❌ {error}", ephemeral=True)
            return

        bot_member = ctx.guild.me or ctx.guild.get_member(self.bot.user.id)
        deny = self._role_assignment_error(ctx.guild, ctx.author, bot_member, role)
        if deny:
            await ctx.send(f"❌ {deny}", ephemeral=True)
            return

        if role in member_target.roles:
            try:
                await member_target.remove_roles(role, reason=f"Removed by {ctx.author} ({ctx.author.id})")
                case = await log_action(ctx.guild.id, ctx.author.id, member_target.id, "role_remove", role.name)
                await ctx.send(f"Removed role **{role.name}** from {member_target.mention}.")
                await self._post_modlog(ctx.guild, case, "Role Remove", ctx.author, member_target, role.name)
            except Exception as exc:
                logger.exception("Failed to remove role: %s", exc)
                await ctx.send("❌ Failed to remove role.", ephemeral=True)
        else:
            try:
                await member_target.add_roles(role, reason=f"Assigned by {ctx.author} ({ctx.author.id})")
                case = await log_action(ctx.guild.id, ctx.author.id, member_target.id, "role_add", role.name)
                await ctx.send(f"Added role **{role.name}** to {member_target.mention}.")
                await self._post_modlog(ctx.guild, case, "Role Add", ctx.author, member_target, role.name)
            except Exception as exc:
                logger.exception("Failed to add role: %s", exc)
                await ctx.send("❌ Failed to add role.", ephemeral=True)


    @commands.hybrid_command(name="nick", aliases=["n", "setnick", "setnickname", "nickname"])
    @commands.guild_only()
    async def nick(self, ctx: commands.Context, target: Optional[discord.Member] = None, *, nickname: Optional[str] = None):
        """Change your nickname or another member's nickname (if permitted)."""
        if not ctx.guild:
            return

        member_target: discord.Member = target or ctx.author
        new_nick: Optional[str] = nickname

        if target is None and ctx.message and ctx.message.content:
            content = ctx.message.content.strip()
            words = content.split()[1:]
            if words:
                first = words[0]
                try:
                    converter = commands.MemberConverter()
                    converted = await converter.convert(ctx, first)
                    member_target = converted
                    new_nick = " ".join(words[1:]) if len(words) > 1 else None
                except Exception:
                    member_target = ctx.author
                    new_nick = " ".join(words)


        if member_target.id != ctx.author.id:
            if not ctx.author.guild_permissions.manage_nicknames and not ctx.author.guild_permissions.administrator:
                await ctx.send("❌ You don't have permission to change other members' nicknames.", ephemeral=True)
                return
            deny = await self._ensure_can_moderate(ctx, member_target)
            if deny:
                await ctx.send(deny, ephemeral=True)
                return

        # Check if member_target has an active forced nickname lock
        async with get_connection() as conn:
            cur = await conn.execute(
                "SELECT forced_nick FROM forced_nicknames WHERE guild_id = ? AND user_id = ?",
                (ctx.guild.id, member_target.id)
            )
            row = await cur.fetchone()
            await cur.close()
            if row:
                target_str = "Your" if member_target.id == ctx.author.id else f"{member_target.mention}'s"
                await ctx.send(
                    f"❌ {target_str} nickname is locked by a moderator and cannot be changed.",
                    ephemeral=True
                )
                return

        try:
            await member_target.edit(nick=new_nick)
            case = await log_action(ctx.guild.id, ctx.author.id, member_target.id, "nickname", new_nick or "")
            nick_display = f"**{new_nick}**" if new_nick else "*reset to default*"
            await ctx.send(f"✅ Changed nickname for {member_target.mention} to {nick_display}.")
            await self._post_modlog(ctx.guild, case, "Nickname", ctx.author, member_target, new_nick or "")
        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to change that user's nickname (role hierarchy issue).", ephemeral=True)
        except Exception as exc:
            logger.exception("Failed to change nickname: %s", exc)
            await ctx.send("❌ Failed to change nickname.", ephemeral=True)

    @commands.hybrid_command(name="forcenick", aliases=["fn", "locknick", "force_nick", "locknickname", "force_nickname"])
    @commands.guild_only()
    async def forcenick(self, ctx: commands.Context, target: discord.Member, *, nickname: Optional[str] = None):
        """Force and lock a member's nickname. Use 'reset' to unlock."""
        if not ctx.guild:
            return

        is_allowed = (
            ctx.author.guild_permissions.manage_nicknames
            or ctx.author.guild_permissions.administrator
            or getattr(ctx.guild, "owner_id", None) == ctx.author.id
        )
        if not is_allowed:
            await ctx.send("❌ You need the 'Manage Nicknames' permission to force nicknames.", ephemeral=True)
            return

        deny = await self._ensure_can_moderate(ctx, target)
        if deny:
            await ctx.send(deny, ephemeral=True)
            return

        clean_nick = nickname.strip() if nickname else ""
        if not clean_nick or clean_nick.lower() in ("reset", "off", "clear", "none", "remove", "unlock"):
            async with get_connection() as conn:
                await conn.execute(
                    "DELETE FROM forced_nicknames WHERE guild_id = ? AND user_id = ?",
                    (ctx.guild.id, target.id)
                )
                await conn.commit()

            case = await log_action(ctx.guild.id, ctx.author.id, target.id, "unforcenick", "Unlocked forced nickname")
            await ctx.send(f"🔓 Unlocked nickname for {target.mention}. They can now change their nickname.")
            await self._post_modlog(ctx.guild, case, "Unlock Nickname", ctx.author, target, "Unlocked forced nickname")
            return

        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            await target.edit(nick=clean_nick)
            async with get_connection() as conn:
                await conn.execute(
                    """
                    INSERT OR REPLACE INTO forced_nicknames (guild_id, user_id, forced_nick, set_by, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (ctx.guild.id, target.id, clean_nick, ctx.author.id, now_iso)
                )
                await conn.commit()

            case = await log_action(ctx.guild.id, ctx.author.id, target.id, "forcenick", clean_nick)
            await ctx.send(f"🔒 Forced nickname for {target.mention} to **{clean_nick}**!")
            await self._post_modlog(ctx.guild, case, "Force Nickname", ctx.author, target, clean_nick)
        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to edit that user's nickname (role hierarchy issue).", ephemeral=True)
        except Exception as exc:
            logger.exception("Failed to force nickname: %s", exc)
            await ctx.send("❌ Failed to force nickname.", ephemeral=True)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.nick == after.nick or not getattr(after, "guild", None):
            return
        try:
            async with get_connection() as conn:
                cur = await conn.execute(
                    "SELECT forced_nick FROM forced_nicknames WHERE guild_id = ? AND user_id = ?",
                    (after.guild.id, after.id)
                )
                row = await cur.fetchone()
                await cur.close()
                if row:
                    forced_nick = row["forced_nick"]
                    if after.nick != forced_nick:
                        try:
                            await after.edit(nick=forced_nick, reason="Forced nickname lock active")
                            logger.info("Enforced forced_nick '%s' for user %s in guild %s", forced_nick, after.id, after.guild.id)
                        except Exception as exc:
                            logger.warning("Failed to enforce forced nickname for %s: %s", after.id, exc)
        except Exception as exc:
            logger.exception("Error in on_member_update forced nickname check: %s", exc)


    @commands.hybrid_command(name="slowmode")
    @commands.guild_only()
    async def slowmode(self, ctx: commands.Context, seconds: int = 0):
        """Set channel slowmode in seconds (0 to disable)"""
        if not ctx.author.guild_permissions.manage_channels:
            await ctx.send("You don't have permission to manage channels.", ephemeral=True)
            return
        if seconds < 0 or seconds > 21600:
            await ctx.send("Slowmode must be between 0 and 21600 seconds.", ephemeral=True)
            return
        channel = ctx.channel
        try:
            await channel.edit(rate_limit_per_user=seconds)
            case = await log_action(ctx.guild.id, ctx.author.id, 0, "slowmode", f"{channel.id}={seconds}")
            await ctx.send(f"Set slowmode for {channel.mention} to {seconds} seconds.")
            await self._post_modlog(ctx.guild, case, "Slowmode", ctx.author, channel, f"{channel.id}={seconds}")
        except Exception as exc:
            logger.exception("Failed to set slowmode: %s", exc)
            await ctx.send("Failed to set slowmode.", ephemeral=True)

    @commands.hybrid_group(name="role_manage", aliases=["role_cmd"])
    @commands.guild_only()
    async def role_group(self, ctx: commands.Context):
        """Manage roles in the guild"""
        await ctx.send("Use `/role_manage add` or `/role_manage remove`.")

    @role_group.command(name="add")
    @commands.guild_only()
    async def role_add(self, ctx: commands.Context, target: discord.Member, role: discord.Role):
        """Add a role to a member"""
        if not ctx.author.guild_permissions.manage_roles:
            await ctx.send("You don't have permission to manage roles.", ephemeral=True)
            return
        bot_member = ctx.guild.me or ctx.guild.get_member(self.bot.user.id)
        deny = self._role_assignment_error(ctx.guild, ctx.author, bot_member, role)
        if deny:
            await ctx.send(deny, ephemeral=True)
            return
        try:
            await target.add_roles(role, reason=f"Assigned by {ctx.author}")
            case = await log_action(ctx.guild.id, ctx.author.id, target.id, "role_add", role.name)
            await ctx.send(f"Added role {role.name} to {target}.")
            await self._post_modlog(ctx.guild, case, "Role Add", ctx.author, target, role.name)
        except Exception as exc:
            logger.exception("Failed to add role: %s", exc)
            await ctx.send("Failed to add role.", ephemeral=True)

    @role_group.command(name="remove")
    @commands.guild_only()
    async def role_remove(self, ctx: commands.Context, target: discord.Member, role: discord.Role):
        """Remove a role from a member"""
        if not ctx.author.guild_permissions.manage_roles:
            await ctx.send("You don't have permission to manage roles.", ephemeral=True)
            return
        bot_member = ctx.guild.me or ctx.guild.get_member(self.bot.user.id)
        deny = self._role_assignment_error(ctx.guild, ctx.author, bot_member, role)
        if deny:
            await ctx.send(deny, ephemeral=True)
            return
        try:
            await target.remove_roles(role, reason=f"Removed by {ctx.author}")
            case = await log_action(ctx.guild.id, ctx.author.id, target.id, "role_remove", role.name)
            await ctx.send(f"Removed role {role.name} from {target}.")
            await self._post_modlog(ctx.guild, case, "Role Remove", ctx.author, target, role.name)
        except Exception as exc:
            logger.exception("Failed to remove role: %s", exc)
            await ctx.send("Failed to remove role.", ephemeral=True)

    @commands.hybrid_group(name="modlog")
    @commands.guild_only()
    async def modlog_group(self, ctx: commands.Context):
        """Manage modlog settings"""
        await ctx.send("Use `/modlog set-channel` or `/modlog clear-channel`.")

    @modlog_group.command(name="set-channel")
    @commands.guild_only()
    async def modlog_set_channel(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        """Set or show the mod-log channel for this guild. If channel omitted, shows current setting."""
        if not ctx.author.guild_permissions.manage_guild and not ctx.author.guild_permissions.administrator:
            await ctx.send("You don't have permission to manage the mod-log channel.", ephemeral=True)
            return

        if channel is None:
            cfg = await get_guild_config(ctx.guild.id)
            ch_id = cfg.get("mod_log_channel") or cfg.get("modlog_channel")
            if not ch_id:
                await ctx.send("No mod-log channel is configured for this guild.", ephemeral=True)
                return
            try:
                ch = ctx.guild.get_channel(int(ch_id)) or self.bot.get_channel(int(ch_id))
            except Exception:
                ch = None
            if ch:
                await ctx.send(f"Current mod-log channel: {ch.mention} (ID: {ch.id})", ephemeral=True)
            else:
                await ctx.send(f"Mod-log channel is set to ID {ch_id}, but I cannot find that channel. Consider clearing and re-setting it.", ephemeral=True)
            return

        try:
            await set_guild_config(ctx.guild.id, {"mod_log_channel": int(channel.id)})
            await ctx.send(f"Mod-log channel set to {channel.mention}", ephemeral=True)
            try:
                embed = discord.Embed(title="Mod-log channel configured", description=f"This channel has been set as the mod-log channel for {ctx.guild.name}.", color=discord.Color.green(), timestamp=datetime.now(timezone.utc))
                embed.add_field(name="Configured by", value=f"{ctx.author.mention} ({ctx.author.id})", inline=False)
                await channel.send(embed=embed)
            except Exception:
                pass
        except Exception as exc:
            logger.exception("Failed to set mod-log channel: %s", exc)
            await ctx.send("Failed to set mod-log channel.", ephemeral=True)

    @modlog_group.command(name="clear-channel")
    @commands.guild_only()
    async def modlog_clear_channel(self, ctx: commands.Context):
        """Clear the configured mod-log channel for this guild."""
        if not ctx.author.guild_permissions.manage_guild and not ctx.author.guild_permissions.administrator:
            await ctx.send("You don't have permission to clear the mod-log channel.", ephemeral=True)
            return
        try:
            await set_guild_config(ctx.guild.id, {"mod_log_channel": None})
            await ctx.send("Mod-log channel cleared.", ephemeral=True)
        except Exception as exc:
            logger.exception("Failed to clear mod-log channel: %s", exc)
            await ctx.send("Failed to clear mod-log channel.", ephemeral=True)

    @modlog_group.command(name="dm")
    @commands.guild_only()
    async def modlog_dm(self, ctx: commands.Context, state: Optional[str] = None):
        """Toggle or view Direct Message notifications for moderation actions in this server."""
        if not ctx.author.guild_permissions.manage_guild and not ctx.author.guild_permissions.administrator:
            await ctx.send("You don't have permission to configure moderation DM notifications.", ephemeral=True)
            return

        cfg = await get_guild_config(ctx.guild.id)
        current = cfg.get("modlog_dm_notifications", True)

        if state is None:
            status_str = "🟢 **Enabled**" if current else "🔴 **Disabled**"
            await ctx.send(f"📬 Direct Message moderation alerts are currently {status_str} in **{ctx.guild.name}**.")
            return

        state_clean = state.lower().strip()
        if state_clean in ["on", "enable", "true", "yes", "1"]:
            new_val = True
        elif state_clean in ["off", "disable", "false", "no", "0"]:
            new_val = False
        else:
            await ctx.send("❌ Invalid option. Use `!modlog dm on` or `!modlog dm off`.", ephemeral=True)
            return

        await set_guild_config(ctx.guild.id, {"modlog_dm_notifications": new_val})
        status_str = "🟢 **Enabled**" if new_val else "🔴 **Disabled**"
        await ctx.send(f"✅ Direct Message moderation alerts are now {status_str} for **{ctx.guild.name}**.")


    async def _post_modlog(self, guild: discord.Guild, case_id: int, action: str, moderator: discord.abc.User, target, reason: Optional[str]):
        """Post a mod action embed to the configured mod log channel or specialized event channel."""
        try:
            from cogs.logging import get_action_log_channel

            act_lower = action.lower()
            event_type = "general"
            if any(k in act_lower for k in ["ban", "kick", "unban", "softban", "hardban"]):
                event_type = "ban_unban"
            elif "role" in act_lower:
                event_type = "role_add_remove"
            elif "wick" in act_lower:
                event_type = "wick"
            elif "security" in act_lower or "antinuke" in act_lower:
                event_type = "security"

            channel = await get_action_log_channel(guild, event_type)
            if not channel:
                return


            embed = discord.Embed(
                title=f"Case #{case_id} — {action}",
                color=discord.Color.blurple(),
                timestamp=datetime.now(timezone.utc),
            )
            embed.add_field(name="Moderator", value=f"{moderator.mention} ({moderator.id})", inline=True)

            if isinstance(target, discord.Member) or isinstance(target, discord.User):
                embed.add_field(name="Target", value=f"{getattr(target, 'mention', str(target))} ({getattr(target, 'id', '')})", inline=True)
            elif isinstance(target, discord.abc.GuildChannel):
                embed.add_field(name="Channel", value=f"{getattr(target, 'mention', str(target))} ({getattr(target, 'id', '')})", inline=True)
            else:
                embed.add_field(name="Target", value=str(target), inline=True)

            embed.add_field(name="Reason", value=reason or "No reason provided", inline=False)
            owner = self.bot.owner_user if hasattr(self.bot, "owner_user") else None
            owner_text = f" | Created & Owned by {owner.name}" if owner else ""
            embed.set_footer(text=f"{guild.name}{owner_text}")

            await channel.send(embed=embed)
        except Exception:
            logger.exception("Failed to post mod log embed for guild %s", guild.id)

    @commands.command(name="vcmute")
    @commands.guild_only()
    async def vcmute(self, ctx: commands.Context, target: discord.Member, duration: Optional[str] = None, *, reason: Optional[str] = "No reason provided"):
        """Mute a member in voice channel for a duration (e.g. 5m, 10s, 2h) or indefinitely."""
        if not ctx.author.guild_permissions.mute_members:
            await ctx.send("❌ You don't have permission to mute members in voice channels.", ephemeral=True)
            return
        if not ctx.guild.me.guild_permissions.mute_members:
            await ctx.send("❌ I need the **Mute Members** permission to server-mute users.", ephemeral=True)
            return

        deny = await self._ensure_can_moderate(ctx, target)
        if deny:
            await ctx.send(f"❌ {deny}", ephemeral=True)
            return

        if not target.voice or not target.voice.channel:
            await ctx.send(f"❌ {target.mention} is not connected to any voice channel.", ephemeral=True)
            return

        # Parse duration
        seconds = None
        duration_desc = "indefinite"
        if duration:
            seconds = parse_duration(duration)
            if seconds is None:
                await ctx.send("❌ Invalid duration format. Use e.g. `5s`, `10m`, `2h`, `1d`.", ephemeral=True)
                return
            duration_desc = duration

        try:
            await target.edit(mute=True, reason=reason)
            case = await log_action(ctx.guild.id, ctx.author.id, target.id, "vcmute", f"Duration: {duration_desc} | Reason: {reason}")
            await ctx.send(f"🎙️ Server-muted {target.mention} in VC ({duration_desc}). Reason: {reason}")
            await self._post_modlog(ctx.guild, case, "VC Mute", ctx.author, target, f"Duration: {duration_desc} | Reason: {reason}")

            if seconds:
                self.bot.loop.create_task(self._async_vc_unmute(ctx.guild.id, target.id, seconds, reason=f"Automatic VC unmute after {duration_desc}"))
        except Exception as exc:
            logger.exception("Failed to vcmute: %s", exc)
            await ctx.send(f"❌ Failed to server-mute {target.mention} in voice channel.", ephemeral=True)

    @commands.command(name="vcunmute")
    @commands.guild_only()
    async def vcunmute(self, ctx: commands.Context, target: discord.Member, *, reason: Optional[str] = "No reason provided"):
        """Unmute a server-muted member in voice channel."""
        if not ctx.author.guild_permissions.mute_members:
            await ctx.send("❌ You don't have permission to unmute members in voice channels.", ephemeral=True)
            return
        if not ctx.guild.me.guild_permissions.mute_members:
            await ctx.send("❌ I need the **Mute Members** permission to server-unmute users.", ephemeral=True)
            return

        if not target.voice or not target.voice.channel:
            await ctx.send(f"❌ {target.mention} is not connected to any voice channel.", ephemeral=True)
            return

        try:
            await target.edit(mute=False, reason=reason)
            case = await log_action(ctx.guild.id, ctx.author.id, target.id, "vcunmute", reason)
            await ctx.send(f"🎙️ Server-unmuted {target.mention} in VC. Reason: {reason}")
            await self._post_modlog(ctx.guild, case, "VC Unmute", ctx.author, target, reason)
        except Exception as exc:
            logger.exception("Failed to vcunmute: %s", exc)
            await ctx.send(f"❌ Failed to server-unmute {target.mention} in voice channel.", ephemeral=True)

    async def _async_vc_unmute(self, guild_id: int, member_id: int, delay: float, reason: str):
        await asyncio.sleep(delay)
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return
        member = guild.get_member(member_id)
        if not member:
            return
        if member.voice and member.voice.mute:
            try:
                await member.edit(mute=False, reason=reason)
                case = await log_action(guild_id, self.bot.user.id, member_id, "vcunmute", reason)
                await self._post_modlog(guild, case, "VC Unmute", self.bot.user, member, reason)
            except Exception:
                logger.exception("Failed to auto-vcunmute member %s in guild %s", member_id, guild_id)

    async def _vcbomb_loop(self, guild_id: int, user_id: int):
        """Loop that continuously moves a target user rapidly between available voice channels in the server."""
        try:
            while (guild_id, user_id) in self._vcbomb_tasks:
                guild = self.bot.get_guild(guild_id) if hasattr(self.bot, "get_guild") else None
                if not guild:
                    break


                member = guild.get_member(user_id)
                if not member:
                    try:
                        member = await guild.fetch_member(user_id)
                    except Exception:
                        break

                if member and member.voice and member.voice.channel:
                    current_vc = member.voice.channel
                    # Find all voice channels the user and bot can connect/move to
                    available_vcs = [
                        vc for vc in guild.voice_channels
                        if vc.id != current_vc.id and vc.permissions_for(member).connect and vc.permissions_for(guild.me).move_members
                    ]

                    if not available_vcs:
                        # Fallback to any other voice channel in the guild
                        available_vcs = [vc for vc in guild.voice_channels if vc.id != current_vc.id]

                    if available_vcs:
                        next_vc = random.choice(available_vcs)
                        try:
                            await member.move_to(next_vc, reason="VC Bomb active")
                        except discord.HTTPException as exc:
                            if getattr(exc, "status", None) == 429:
                                await asyncio.sleep(1.5)
                            else:
                                pass
                        except Exception:
                            pass

                # Rapid interval between moves
                await asyncio.sleep(0.35)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.exception("Error in _vcbomb_loop for user %s in guild %s", user_id, guild_id)
        finally:
            self._vcbomb_tasks.pop((guild_id, user_id), None)

    async def _is_bot_owner(self, ctx: commands.Context) -> bool:
        owner_id = os.getenv("OWNER_ID")
        if owner_id and ctx.author.id == int(owner_id):
            return True
        if hasattr(self.bot, "is_owner") and callable(getattr(self.bot, "is_owner")):
            try:
                return await self.bot.is_owner(ctx.author)
            except Exception:
                pass
        return False

    @commands.hybrid_group(name="vcbomb", aliases=["vcb", "bombvc", "vcbombing"], invoke_without_command=True)
    @commands.guild_only()
    async def vcbomb(self, ctx: commands.Context, target: Optional[discord.Member] = None):
        """Bomb a user's voice connection by dragging them continuously between voice channels (Bot Owner only). Shortcuts: vcbomb, vcb."""
        if not await self._is_bot_owner(ctx):
            await ctx.send("❌ This command is restricted to the Bot Owner.", ephemeral=True)
            return

        if not ctx.guild.me.guild_permissions.move_members:
            await ctx.send("❌ I need the **Move Members** permission to VC bomb users.", ephemeral=True)
            return

        if target is None:
            await ctx.send_help(ctx.command)
            return

        key = (ctx.guild.id, target.id)
        if key in self._vcbomb_tasks:
            await ctx.send(f"⚠️ **VC Bomb** is already active on {target.mention}! Use `!vcbomb stop {target.mention}` to stop it.")
            return

        task = self.bot.loop.create_task(self._vcbomb_loop(ctx.guild.id, target.id))
        self._vcbomb_tasks[key] = task

        status_msg = f" currently connected in **{target.voice.channel.name}**." if (target.voice and target.voice.channel) else " (will start dragging as soon as they join a voice channel)."
        await ctx.send(f"💣 **VC Bomb** activated on {target.mention}! Dragging user continuously between voice channels{status_msg}\nUse `!vcbomb stop {target.mention}` or `!stopvcbomb` to end.")

    @vcbomb.command(name="start")
    @commands.guild_only()
    async def vcbomb_start(self, ctx: commands.Context, target: discord.Member):
        """Start VC bombing a user (Bot Owner only)."""
        await self.vcbomb(ctx, target=target)

    @vcbomb.command(name="stop", aliases=["off", "cancel", "end"])
    @commands.guild_only()
    async def vcbomb_stop(self, ctx: commands.Context, target: Optional[discord.Member] = None):
        """Stop VC bombing a user (or stop all active VC bombs in the server if no user specified)."""
        if not await self._is_bot_owner(ctx):
            await ctx.send("❌ This command is restricted to the Bot Owner.", ephemeral=True)
            return

        if target:
            key = (ctx.guild.id, target.id)
            task = self._vcbomb_tasks.pop(key, None)
            if task:
                task.cancel()
                await ctx.send(f"🛑 **VC Bomb** stopped for {target.mention}.")
            else:
                await ctx.send(f"ℹ️ {target.mention} is not currently being VC-bombed.", ephemeral=True)
        else:
            stopped = 0
            keys_to_remove = [k for k in self._vcbomb_tasks.keys() if k[0] == ctx.guild.id]
            for k in keys_to_remove:
                task = self._vcbomb_tasks.pop(k, None)
                if task:
                    task.cancel()
                    stopped += 1
            if stopped > 0:
                await ctx.send(f"🛑 Stopped **{stopped}** active **VC Bomb** task(s) in **{ctx.guild.name}**.")
            else:
                await ctx.send("ℹ️ There are no active VC bomb tasks running in this server.", ephemeral=True)

    @vcbomb.command(name="list")
    @commands.guild_only()
    async def vcbomb_list(self, ctx: commands.Context):
        """List all users currently being VC-bombed in this server (Bot Owner only)."""
        if not await self._is_bot_owner(ctx):
            await ctx.send("❌ This command is restricted to the Bot Owner.", ephemeral=True)
            return

        guild_keys = [k for k in self._vcbomb_tasks.keys() if k[0] == ctx.guild.id]
        if not guild_keys:
            await ctx.send("ℹ️ No users are currently being VC-bombed in this server.", ephemeral=True)
            return

        mentions = []
        for _, uid in guild_keys:
            m = ctx.guild.get_member(uid)
            mentions.append(m.mention if m else f"User ID `{uid}`")

        embed = discord.Embed(
            title=f"💣 Active VC Bombs — {ctx.guild.name}",
            description="\n".join(f"• {m}" for m in mentions),
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="stopvcbomb", aliases=["unvcbomb", "stopvcb"])
    @commands.guild_only()
    async def stopvcbomb(self, ctx: commands.Context, target: Optional[discord.Member] = None):
        """Shortcut command to stop VC bombing a user or all users in the server (Bot Owner only)."""
        await self.vcbomb_stop(ctx, target=target)


    @commands.hybrid_command(name="history", aliases=["modhistory", "crimes"])

    @commands.guild_only()
    async def history(self, ctx: commands.Context, target: discord.User):
        """View moderation history (past crimes) for a member."""
        if not (ctx.author.guild_permissions.view_audit_log or ctx.author.guild_permissions.manage_messages or ctx.author.guild_permissions.kick_members or ctx.author.guild_permissions.ban_members):
            await ctx.send("❌ You don't have permission to view moderation history.", ephemeral=True)
            return
        try:
            all_logs = await fetch_logs_for_target(ctx.guild.id, target.id)
            # Exclude role changes (role_add/role_remove) from the history view
            logs = [l for l in all_logs if not l["action"].startswith("role")]
            if not logs:
                await ctx.send(f"✅ {target.mention} has a clean record! No past crimes logged.")
                return

            view = HistorySelectView(self.bot, target, logs, ctx.guild)
            embed = view.build_embed()
            await ctx.send(embed=embed, view=view)

        except Exception as exc:
            logger.exception("Failed to fetch history: %s", exc)
            await ctx.send("❌ Failed to fetch moderation history.", ephemeral=True)

    @commands.Cog.listener()
    async def on_automod_action(self, execution: discord.AutoModExecution):
        """Fires when Discord's Native AutoMod executes an action (e.g. blocks a message, timeouts a member)."""
        guild = execution.guild
        if not guild:
            return

        cfg = await get_guild_config(guild.id)
        if not cfg.get("automod_enabled", True):
            return

        user_id = execution.user_id
        member = execution.member or guild.get_member(user_id)

        # Check channel whitelist
        ignored_channels = cfg.get("automod_ignored_channels", [])
        if execution.channel_id and execution.channel_id in ignored_channels:
            return

        # Check role whitelist
        ignored_roles = cfg.get("automod_ignored_roles", [])
        if member and hasattr(member, "roles"):
            if any(r.id in ignored_roles for r in member.roles):
                return

        modlog_channel_id = cfg.get("automod_log_channel_id") or cfg.get("modlog_channel_id")
        if not modlog_channel_id:
            return

        channel = guild.get_channel(int(modlog_channel_id))
        if not channel:
            return

        user_text = member.mention if member else f"<@{user_id}>"

        embed = discord.Embed(
            title="🛡️ Native AutoMod Action Triggered",
            color=discord.Color.orange(),
            timestamp=datetime.now(timezone.utc)
        )
        if member and hasattr(member, "display_avatar"):
            embed.set_thumbnail(url=member.display_avatar.url)

        embed.add_field(name="User", value=f"{user_text} (`ID: {user_id}`)", inline=True)
        if execution.channel:
            embed.add_field(name="Channel", value=execution.channel.mention, inline=True)
        if execution.rule_id:
            embed.add_field(name="Rule ID", value=f"`{execution.rule_id}`", inline=True)

        if execution.matched_keyword:
            embed.add_field(name="Matched Keyword", value=f"`{execution.matched_keyword}`", inline=False)
        if execution.matched_content:
            embed.add_field(name="Matched Content", value=f"`{execution.matched_content[:500]}`", inline=False)
        elif execution.content:
            embed.add_field(name="Blocked Message", value=f"```{execution.content[:500]}```", inline=False)

        action_type = str(execution.action.type).split(".")[-1] if execution.action else "Blocked"
        embed.set_footer(text=f"AutoMod Action: {action_type} • Guild: {guild.name}")

        try:
            await channel.send(embed=embed)
        except Exception as e:
            logger.warning("Failed to send automod action log to channel %s: %s", modlog_channel_id, e)

        # Log into SQLite DB
        try:
            await log_action(
                guild_id=guild.id,
                moderator_id=self.bot.user.id if self.bot.user else 0,
                target_id=user_id,
                action="AUTOMOD_BLOCK",
                reason=f"Matched keyword '{execution.matched_keyword or 'filter'}' in channel {execution.channel}"
            )
        except Exception as exc:
            logger.warning("Failed to log automod action into db: %s", exc)

    @commands.hybrid_group(name="automod", invoke_without_command=True)
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def automod(self, ctx: commands.Context):
        """Manage Discord Native AutoMod rules and configuration for this server."""
        await ctx.send_help(ctx.command)


    async def automod_config_impl(self, ctx: commands.Context):
        """View current AutoMod settings for this server."""
        cfg = await get_guild_config(ctx.guild.id)
        enabled = cfg.get("automod_enabled", True)
        log_ch_id = cfg.get("automod_log_channel_id") or cfg.get("modlog_channel_id")
        log_ch_str = f"<#{log_ch_id}>" if log_ch_id else "*Not configured*"
        punishment = cfg.get("automod_punishment", "Block Message")

        ignored_ch_ids = cfg.get("automod_ignored_channels", [])
        ignored_ch_str = ", ".join([f"<#{cid}>" for cid in ignored_ch_ids]) if ignored_ch_ids else "*None*"

        ignored_role_ids = cfg.get("automod_ignored_roles", [])
        ignored_role_str = ", ".join([f"<@&{rid}>" for rid in ignored_role_ids]) if ignored_role_ids else "*None*"

        status_str = "🟢 **Enabled**" if enabled else "🔴 **Disabled**"

        md_enabled = cfg.get("automod_block_markdown", True)
        md_str = "🟢 **Enabled**" if md_enabled else "🔴 **Disabled**"

        scam_enabled = cfg.get("automod_block_scam", True)
        scam_str = "🟢 **Enabled**" if scam_enabled else "🔴 **Disabled**"

        invite_enabled = cfg.get("automod_block_invites", True)
        invite_str = "🟢 **Enabled**" if invite_enabled else "🔴 **Disabled**"

        embed = discord.Embed(
            title=f"⚙️ AutoMod Configuration — {ctx.guild.name}",
            color=discord.Color.blurple()
        )
        embed.add_field(name="AutoMod Status", value=status_str, inline=True)
        embed.add_field(name="Logging Channel", value=log_ch_str, inline=True)
        embed.add_field(name="Default Punishment", value=f"`{punishment}`", inline=True)
        embed.add_field(name="Scam & Phishing Filter", value=scam_str, inline=True)
        embed.add_field(name="Anti-Invite Link Filter", value=invite_str, inline=True)
        embed.add_field(name="Markdown Headers Filter", value=md_str, inline=True)
        embed.add_field(name="Whitelisted Channels", value=ignored_ch_str, inline=False)
        embed.add_field(name="Whitelisted Roles", value=ignored_role_str, inline=False)

        embed.set_footer(text="Use !automod enable/disable, !automod antilink, !automod scamfilter, or !automod markdown to modify settings")
        await ctx.send(embed=embed)


    @automod.command(name="config")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def automod_config(self, ctx: commands.Context):
        await self.automod_config_impl(ctx)

    async def automod_markdown_impl(self, ctx: commands.Context, state: Optional[str] = None):
        """Toggle Discord Markdown Heading filter (# Heading, ## Heading, ### Heading)."""
        cfg = await get_guild_config(ctx.guild.id)
        current = cfg.get("automod_block_markdown", True)

        if state is None:
            status_str = "🟢 **Enabled**" if current else "🔴 **Disabled**"
            await ctx.send(f"📝 AutoMod Discord Markdown Heading filter is currently {status_str} in **{ctx.guild.name}**.")
            return

        state_clean = state.lower().strip()
        if state_clean in ["on", "enable", "true", "yes", "1"]:
            new_val = True
        elif state_clean in ["off", "disable", "false", "no", "0"]:
            new_val = False
        else:
            await ctx.send("❌ Invalid option. Use `!automod markdown on` or `!automod markdown off`.", ephemeral=True)
            return

        await set_guild_config(ctx.guild.id, {"automod_block_markdown": new_val})
        status_str = "🟢 **Enabled**" if new_val else "🔴 **Disabled**"
        await ctx.send(f"✅ AutoMod Discord Markdown Heading filter is now {status_str} for **{ctx.guild.name}**.")

    @automod.command(name="markdown")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def automod_markdown(self, ctx: commands.Context, state: Optional[str] = None):
        await self.automod_markdown_impl(ctx, state)

    @automod.command(name="antilink", aliases=["invitefilter"])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def automod_antilink(self, ctx: commands.Context, state: Optional[str] = None):
        """Toggle real-time Discord server invite link filter (default: on)."""
        cfg = await get_guild_config(ctx.guild.id)
        if not state:
            curr = cfg.get("automod_block_invites", True)
            status_str = "🟢 **Enabled**" if curr else "🔴 **Disabled**"
            await ctx.send(f"🔗 AutoMod Discord Invite Link filter is currently {status_str} in **{ctx.guild.name}**.")
            return

        state_clean = state.lower().strip()
        if state_clean in ["on", "enable", "true", "yes", "1"]:
            new_val = True
        elif state_clean in ["off", "disable", "false", "no", "0"]:
            new_val = False
        else:
            await ctx.send("❌ Invalid option. Use `!automod antilink on` or `!automod antilink off`.", ephemeral=True)
            return

        await set_guild_config(ctx.guild.id, {"automod_block_invites": new_val})
        status_str = "🟢 **Enabled**" if new_val else "🔴 **Disabled**"
        await ctx.send(f"✅ AutoMod Discord Invite Link filter is now {status_str} for **{ctx.guild.name}**.")

    @automod.command(name="scamfilter", aliases=["scamprotection"])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def automod_scamfilter(self, ctx: commands.Context, state: Optional[str] = None):
        """Toggle real-time scam & phishing link filter (default: on)."""
        cfg = await get_guild_config(ctx.guild.id)
        if not state:
            curr = cfg.get("automod_block_scam", True)
            status_str = "🟢 **Enabled**" if curr else "🔴 **Disabled**"
            await ctx.send(f"🔗 AutoMod Scam & Phishing Link filter is currently {status_str} in **{ctx.guild.name}**.")
            return

        state_clean = state.lower().strip()
        if state_clean in ["on", "enable", "true", "yes", "1"]:
            new_val = True
        elif state_clean in ["off", "disable", "false", "no", "0"]:
            new_val = False
        else:
            await ctx.send("❌ Invalid option. Use `!automod scamfilter on` or `!automod scamfilter off`.", ephemeral=True)
            return

        await set_guild_config(ctx.guild.id, {"automod_block_scam": new_val})
        status_str = "🟢 **Enabled**" if new_val else "🔴 **Disabled**"
        await ctx.send(f"✅ AutoMod Scam & Phishing Link filter is now {status_str} for **{ctx.guild.name}**.")

    @automod.group(name="invite", invoke_without_command=True)
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def automod_invite(self, ctx: commands.Context):
        """Manage whitelisted Discord server invite links."""
        await ctx.send_help(ctx.command)

    @automod_invite.command(name="add", aliases=["whitelist", "allow"])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def automod_invite_add(self, ctx: commands.Context, code_or_link: str):
        """Add an invite code or link to the whitelist (allowed invites)."""
        cfg = await get_guild_config(ctx.guild.id)
        invites = cfg.get("automod_whitelisted_invites", [])
        clean_code = code_or_link.split("/")[-1].lower().strip()
        if clean_code not in invites:
            invites.append(clean_code)
            await set_guild_config(ctx.guild.id, {"automod_whitelisted_invites": invites})
        await ctx.send(f"✅ Whitelisted Discord invite code **`{clean_code}`** (`discord.gg/{clean_code}`). Links with this code are now allowed.")

    @automod_invite.command(name="remove", aliases=["unwhitelist", "delete"])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def automod_invite_remove(self, ctx: commands.Context, code_or_link: str):
        """Remove an invite code from the whitelist."""
        cfg = await get_guild_config(ctx.guild.id)
        invites = cfg.get("automod_whitelisted_invites", [])
        clean_code = code_or_link.split("/")[-1].lower().strip()
        if clean_code in invites:
            invites.remove(clean_code)
            await set_guild_config(ctx.guild.id, {"automod_whitelisted_invites": invites})
        await ctx.send(f"✅ Removed **`{clean_code}`** from the whitelisted invite links.")

    @automod_invite.command(name="show", aliases=["list"])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def automod_invite_show(self, ctx: commands.Context):
        """Show all whitelisted Discord invite links for this server."""
        cfg = await get_guild_config(ctx.guild.id)
        invites = cfg.get("automod_whitelisted_invites", [])
        inv_str = ", ".join([f"`discord.gg/{c}`" for c in invites]) if invites else "*No invite links whitelisted*"

        embed = discord.Embed(
            title=f"🌐 Whitelisted Invites — {ctx.guild.name}",
            description=f"**Allowed Server Invites:**\n{inv_str}\n\n*All other Discord invite links will be deleted instantly.*",
            color=discord.Color.blue()
        )
        await ctx.send(embed=embed)



    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """AutoMod listener to detect & delete messages containing Discord Markdown Headings (# Heading, ## Heading, ### Heading)."""
        if not message.guild or message.author.bot:
            return

        # 1. Check if automod & markdown header filter are enabled for guild
        cfg = await get_guild_config(message.guild.id)
        if not cfg.get("automod_enabled", True) or not cfg.get("automod_block_markdown", True):
            return

        # 2. Check if author is a moderator/admin (bypass)
        if hasattr(message.author, "guild_permissions"):
            perms = message.author.guild_permissions
            if perms.administrator or perms.manage_guild or perms.manage_messages:
                return

        # 3. Check channel whitelist
        ignored_channels = cfg.get("automod_ignored_channels", [])
        if message.channel.id in ignored_channels:
            return

        # 4. Check role whitelist
        ignored_roles = cfg.get("automod_ignored_roles", [])
        if hasattr(message.author, "roles"):
            if any(r.id in ignored_roles for r in message.author.roles):
                return

        # 5. Check Scam Links & Invite Protection
        is_scam = False
        is_invite = False
        scam_pattern = r"(?i)\b(?:discord-gifts\.xyz|steamgift\.xyz|nitrofree\.com|free-?nitro|steam-?gift|discord-?nitro|discoord|steamcommunlty|gift-discord)\b"
        invite_match = re.search(r"(?i)(?:discord(?:app)?\.(?:gg|com/invite)|dsc\.gg)/([a-zA-Z0-9-]+)", message.content)

        if cfg.get("automod_block_scam", True) and re.search(scam_pattern, message.content):
            is_scam = True
        elif cfg.get("automod_block_invites", True) and invite_match:
            code = invite_match.group(1).lower()
            full_link = invite_match.group(0).lower()
            whitelisted_invites = [w.lower().strip() for w in cfg.get("automod_whitelisted_invites", [])]
            if not (code in whitelisted_invites or full_link in whitelisted_invites or f"discord.gg/{code}" in whitelisted_invites):
                is_invite = True

        # Check if the user or any of their roles are whitelisted for invite protection
        if is_invite:
            user_wl = cfg.get("antinuke_whitelisted_users", {})
            u_id = str(message.author.id)
            if isinstance(user_wl, list) and message.author.id in user_wl:
                is_invite = False
            elif isinstance(user_wl, dict) and any(c in user_wl.get(u_id, []) for c in ["all", "invite", "antilink"]):
                is_invite = False

            if is_invite and hasattr(message.author, "roles"):
                role_wl = cfg.get("antinuke_whitelisted_roles", {})
                for r in message.author.roles:
                    r_id = str(r.id)
                    if isinstance(role_wl, list) and r.id in role_wl:
                        is_invite = False
                        break
                    elif isinstance(role_wl, dict) and any(c in role_wl.get(r_id, []) for c in ["all", "invite", "antilink"]):
                        is_invite = False
                        break

        if is_scam or is_invite:

            block_type = "Scam / Phishing Link" if is_scam else "Discord Invite Link"
            action_key = "SCAM_LINK_BLOCK" if is_scam else "INVITE_LINK_BLOCK"


            try:
                await message.delete()
                await message.channel.send(
                    f"⚠️ {message.author.mention}, **{block_type}** posting is prohibited in this server! You have been warned.",
                    delete_after=10
                )
            except Exception as e:
                logger.warning("Failed to delete %s message from %s: %s", block_type, message.author.id, e)

            # Issue official WARN in database & trigger escalation
            try:
                await self._process_warn_escalation(
                    message.guild,
                    message.author,
                    reason=f"[AutoMod Filter] Posted prohibited {block_type} in #{message.channel.name}",
                    moderator=self.bot.user if self.bot else None
                )
            except Exception as e:
                logger.warning("Failed to log automod warning for %s: %s", message.author.id, e)


            # Log to ModLog channel
            try:
                modlog_ch_id = cfg.get("automod_log_channel_id") or cfg.get("modlog_channel_id")
                if modlog_ch_id:
                    log_ch = message.guild.get_channel(int(modlog_ch_id))
                    if log_ch:
                        embed = discord.Embed(
                            title=f"🤖 AutoMod Action — {block_type} Blocked",
                            color=discord.Color.red(),
                            timestamp=datetime.now(timezone.utc)
                        )
                        embed.add_field(name="User", value=f"{message.author.mention} (`ID: {message.author.id}`)", inline=True)
                        embed.add_field(name="Channel", value=message.channel.mention, inline=True)
                        embed.add_field(name="Blocked Link", value=f"```{message.content[:500]}```", inline=False)
                        embed.set_footer(text=f"AutoMod Protection • Guild: {message.guild.name}")
                        await log_ch.send(embed=embed)
            except Exception as e:
                logger.warning("Failed to send modlog for automod link block: %s", e)

            return

        # 6. Regex to detect Discord Markdown Headings (# Heading, ## Heading, ### Heading) at line start
        if cfg.get("automod_block_markdown", True) and re.search(r"(?m)^#{1,3}\s+", message.content):
            try:
                await message.delete()
                await message.channel.send(
                    f"⚠️ {message.author.mention}, Discord markdown headings (`#`, `##`, `###`) are not allowed in this server.",
                    delete_after=10
                )
            except Exception as e:
                logger.warning("Failed to delete markdown heading message from %s: %s", message.author.id, e)

            # Log action
            try:
                await log_action(
                    guild_id=message.guild.id,
                    moderator_id=self.bot.user.id if self.bot and self.bot.user else 0,
                    target_id=message.author.id,
                    action="AUTOMOD_MARKDOWN_BLOCK",
                    reason=f"Posted message with markdown headings in #{message.channel.name}"
                )

                modlog_ch_id = cfg.get("automod_log_channel_id") or cfg.get("modlog_channel_id")
                if modlog_ch_id:
                    log_ch = message.guild.get_channel(int(modlog_ch_id))
                    if log_ch:
                        embed = discord.Embed(
                            title="🤖 AutoMod Action — Markdown Heading Blocked",
                            color=discord.Color.red(),
                            timestamp=datetime.now(timezone.utc)
                        )
                        embed.add_field(name="User", value=f"{message.author.mention} (`ID: {message.author.id}`)", inline=True)
                        embed.add_field(name="Channel", value=message.channel.mention, inline=True)
                        embed.add_field(name="Blocked Content", value=f"```{message.content[:500]}```", inline=False)
                        embed.set_footer(text=f"AutoMod Protection • Guild: {message.guild.name}")
                        await log_ch.send(embed=embed)
            except Exception as e:
                logger.warning("Failed to log automod markdown action for %s: %s", message.author.id, e)



    async def automod_enable_impl(self, ctx: commands.Context):
        """Enable AutoMod on this server."""
        await set_guild_config(ctx.guild.id, {"automod_enabled": True})
        embed = discord.Embed(
            title="🟢 AutoMod Enabled",
            description="AutoMod protection is now **active** on this server.",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    @automod.command(name="enable")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def automod_enable(self, ctx: commands.Context):
        await self.automod_enable_impl(ctx)

    async def automod_disable_impl(self, ctx: commands.Context):
        """Disable AutoMod on this server."""
        await set_guild_config(ctx.guild.id, {"automod_enabled": False})
        embed = discord.Embed(
            title="🔴 AutoMod Disabled",
            description="AutoMod protection has been **disabled** for this server.",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)

    @automod.command(name="disable")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def automod_disable(self, ctx: commands.Context):
        await self.automod_disable_impl(ctx)

    @automod.command(name="dm")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def automod_dm(self, ctx: commands.Context, state: Optional[str] = None):
        """Toggle Direct Message notifications for AutoMod & moderation actions."""
        await self.modlog_dm(ctx, state=state)


    async def automod_logging_impl(self, ctx: commands.Context, channel: discord.TextChannel):
        """Set the logging channel for AutoMod events."""
        await set_guild_config(ctx.guild.id, {"automod_log_channel_id": channel.id})
        embed = discord.Embed(
            title="📜 AutoMod Logging Channel Updated",
            description=f"AutoMod enforcement logs will now be sent to {channel.mention}.",
            color=discord.Color.blue()
        )
        await ctx.send(embed=embed)

    @automod.command(name="logging")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def automod_logging(self, ctx: commands.Context, channel: discord.TextChannel):
        await self.automod_logging_impl(ctx, channel)

    async def automod_punishment_impl(self, ctx: commands.Context, action: str):
        """Set default punishment for AutoMod events."""
        action_clean = action.lower().strip()
        valid_actions = {
            "block": "Block Message",
            "alert": "Send Alert to ModLog",
            "timeout_1m": "Timeout 1 Minute",
            "timeout_5m": "Timeout 5 Minutes",
            "timeout_1h": "Timeout 1 Hour",
            "kick": "Kick User",
            "ban": "Ban User"
        }
        if action_clean not in valid_actions:
            valid_keys = ", ".join([f"`{k}`" for k in valid_actions.keys()])
            await ctx.send(f"❌ Invalid punishment action. Valid options: {valid_keys}", ephemeral=True)
            return

        label = valid_actions[action_clean]
        await set_guild_config(ctx.guild.id, {"automod_punishment": label})
        embed = discord.Embed(
            title="🔨 AutoMod Punishment Updated",
            description=f"Default AutoMod punishment set to **{label}**.",
            color=discord.Color.orange()
        )
        await ctx.send(embed=embed)

    @automod.command(name="punishment")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def automod_punishment(self, ctx: commands.Context, *, action: str):
        await self.automod_punishment_impl(ctx, action)

    @automod.group(name="ignore", invoke_without_command=True)
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def automod_ignore(self, ctx: commands.Context):
        """Manage AutoMod whitelist (channels & roles)."""
        await self.automod_ignore_show_impl(ctx)

    async def automod_ignore_channel_impl(self, ctx: commands.Context, channel: discord.TextChannel):
        """Add a channel to the AutoMod whitelist."""
        cfg = await get_guild_config(ctx.guild.id)
        channels = cfg.get("automod_ignored_channels", [])
        if channel.id not in channels:
            channels.append(channel.id)
            await set_guild_config(ctx.guild.id, {"automod_ignored_channels": channels})
        embed = discord.Embed(
            title="🛡️ Channel Whitelisted",
            description=f"{channel.mention} added to AutoMod whitelist.",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    @automod_ignore.command(name="channel")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def automod_ignore_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        await self.automod_ignore_channel_impl(ctx, channel)

    async def automod_ignore_role_impl(self, ctx: commands.Context, role: discord.Role):
        """Add a role to the AutoMod whitelist."""
        cfg = await get_guild_config(ctx.guild.id)
        roles = cfg.get("automod_ignored_roles", [])
        if role.id not in roles:
            roles.append(role.id)
            await set_guild_config(ctx.guild.id, {"automod_ignored_roles": roles})
        embed = discord.Embed(
            title="🛡️ Role Whitelisted",
            description=f"{role.mention} added to AutoMod whitelist.",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    @automod_ignore.command(name="role")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def automod_ignore_role(self, ctx: commands.Context, role: discord.Role):
        await self.automod_ignore_role_impl(ctx, role)

    async def automod_ignore_show_impl(self, ctx: commands.Context):
        """Show whitelisted channels and roles."""
        cfg = await get_guild_config(ctx.guild.id)
        ch_ids = cfg.get("automod_ignored_channels", [])
        role_ids = cfg.get("automod_ignored_roles", [])

        ch_str = ", ".join([f"<#{cid}>" for cid in ch_ids]) if ch_ids else "*None*"
        role_str = ", ".join([f"<@&{rid}>" for rid in role_ids]) if role_ids else "*None*"

        embed = discord.Embed(
            title=f"🛡️ AutoMod Whitelist — {ctx.guild.name}",
            color=discord.Color.blurple()
        )
        embed.add_field(name="Whitelisted Channels", value=ch_str, inline=False)
        embed.add_field(name="Whitelisted Roles", value=role_str, inline=False)
        await ctx.send(embed=embed)

    @automod_ignore.command(name="show")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def automod_ignore_show(self, ctx: commands.Context):
        await self.automod_ignore_show_impl(ctx)

    async def automod_ignore_reset_impl(self, ctx: commands.Context):
        """Reset the AutoMod whitelist."""
        await set_guild_config(ctx.guild.id, {"automod_ignored_channels": [], "automod_ignored_roles": []})
        embed = discord.Embed(
            title="🔄 AutoMod Whitelist Reset",
            description="All whitelisted channels and roles have been cleared.",
            color=discord.Color.orange()
        )
        await ctx.send(embed=embed)

    @automod_ignore.command(name="reset")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def automod_ignore_reset(self, ctx: commands.Context):
        await self.automod_ignore_reset_impl(ctx)

    @automod.group(name="unignore", invoke_without_command=True)
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def automod_unignore(self, ctx: commands.Context):
        """Remove channels or roles from AutoMod whitelist."""
        await ctx.send_help(ctx.command)

    async def automod_unignore_channel_impl(self, ctx: commands.Context, channel: discord.TextChannel):
        """Remove a channel from the AutoMod whitelist."""
        cfg = await get_guild_config(ctx.guild.id)
        channels = cfg.get("automod_ignored_channels", [])
        if channel.id in channels:
            channels.remove(channel.id)
            await set_guild_config(ctx.guild.id, {"automod_ignored_channels": channels})
        embed = discord.Embed(
            title="✅ Channel Removed from Whitelist",
            description=f"{channel.mention} is no longer whitelisted.",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    @automod_unignore.command(name="channel")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def automod_unignore_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        await self.automod_unignore_channel_impl(ctx, channel)

    async def automod_unignore_role_impl(self, ctx: commands.Context, role: discord.Role):
        """Remove a role from the AutoMod whitelist."""
        cfg = await get_guild_config(ctx.guild.id)
        roles = cfg.get("automod_ignored_roles", [])
        if role.id in roles:
            roles.remove(role.id)
            await set_guild_config(ctx.guild.id, {"automod_ignored_roles": roles})
        embed = discord.Embed(
            title="✅ Role Removed from Whitelist",
            description=f"{role.mention} is no longer whitelisted.",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    @automod_unignore.command(name="role")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def automod_unignore_role(self, ctx: commands.Context, role: discord.Role):
        await self.automod_unignore_role_impl(ctx, role)


    async def automod_list_impl(self, ctx: commands.Context):
        """List all active native Discord AutoMod rules in this server."""
        try:
            rules = await ctx.guild.fetch_automod_rules()
        except discord.Forbidden:
            await ctx.send("❌ I (the bot) need the **Manage Server** (`manage_guild`) permission to view Discord AutoMod rules.", ephemeral=True)
            return
        except discord.HTTPException as e:
            await ctx.send(f"❌ Failed to fetch AutoMod rules: {e.text or e}", ephemeral=True)
            return
        except Exception as e:
            logger.exception("Failed to fetch AutoMod rules: %s", e)
            await ctx.send(f"❌ Error fetching AutoMod rules: {e}", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"🛡️ Native AutoMod Rules — {ctx.guild.name}",
            color=discord.Color.blurple()
        )

        if not rules:
            embed.description = "No native AutoMod rules are currently configured for this server.\nUse `!automod blockwords`, `!automod antispam`, or `!automod presets` to create one!"
        else:
            lines = []
            for r in rules:
                status = "🟢 Enabled" if r.enabled else "🔴 Disabled"
                trig = getattr(r, "trigger", getattr(r, "trigger_type", None))
                if trig and hasattr(trig, "type"):
                    trigger_name = str(trig.type).split(".")[-1]
                elif trig is not None:
                    trigger_name = str(trig).split(".")[-1]
                else:
                    trigger_name = "Rule"

                lines.append(f"• **{r.name}** (`ID: {r.id}`)\n  Status: {status} | Trigger: `{trigger_name}`")
            embed.description = f"Configured Rules (**{len(rules)}**):\n\n" + "\n\n".join(lines)


        embed.set_footer(text="Use !automod toggle <rule_id> or !automod delete <rule_id> to manage rules")
        await ctx.send(embed=embed)

    @automod.command(name="list")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def automod_list(self, ctx: commands.Context):
        await self.automod_list_impl(ctx)

    async def automod_blockwords_impl(self, ctx: commands.Context, rule_name: str, words: str):
        """Create a native Discord AutoMod rule to block specific words/phrases (comma-separated)."""
        word_list = [w.strip() for w in words.split(",") if w.strip()]
        if not word_list:
            await ctx.send("❌ Please provide at least one word to block (e.g. `!automod blockwords BadWords filter1, filter2`).", ephemeral=True)
            return

        try:
            rule = await ctx.guild.create_automod_rule(
                name=rule_name[:100],
                event_type=discord.AutoModRuleEventType.message_send,
                trigger_type=discord.AutoModRuleTriggerType.keyword,
                trigger_metadata=make_trigger_metadata(keyword_filter=word_list[:1000]),
                actions=[discord.AutoModRuleAction(type=discord.AutoModRuleActionType.block_message)],
                enabled=True,
                reason=f"Created by {ctx.author}"
            )

            embed = discord.Embed(
                title="✅ Native AutoMod Rule Created!",
                description=f"Rule **{rule.name}** (`ID: {rule.id}`) is active!\nIt will automatically block messages containing **{len(word_list)}** forbidden keywords.",
                color=discord.Color.green()
            )
            await ctx.send(embed=embed)
        except discord.Forbidden:
            await ctx.send("❌ I (the bot) need the **Manage Server** (`manage_guild`) permission to create AutoMod rules.", ephemeral=True)
        except discord.HTTPException as e:
            await ctx.send(f"❌ Failed to create AutoMod rule: {e.text or e}", ephemeral=True)
        except Exception as e:
            logger.exception("Failed to create AutoMod rule: %s", e)
            await ctx.send(f"❌ Error creating AutoMod rule: {e}", ephemeral=True)

    @automod.command(name="blockwords")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def automod_blockwords(self, ctx: commands.Context, rule_name: str, *, words: str):
        await self.automod_blockwords_impl(ctx, rule_name, words)

    async def automod_antispam_impl(self, ctx: commands.Context):
        """Enable Discord's native AutoMod anti-spam rule."""
        try:
            rule = await ctx.guild.create_automod_rule(
                name="Helix Anti-Spam",
                event_type=discord.AutoModRuleEventType.message_send,
                trigger_type=discord.AutoModRuleTriggerType.spam,
                actions=[discord.AutoModRuleAction(type=discord.AutoModRuleActionType.block_message)],
                enabled=True,
                reason=f"Created by {ctx.author}"
            )
            embed = discord.Embed(
                title="✅ Native Anti-Spam Rule Enabled!",
                description=f"Rule **{rule.name}** (`ID: {rule.id}`) is active!\nDiscord will automatically block spam messages from being posted in your server.",
                color=discord.Color.green()
            )
            await ctx.send(embed=embed)
        except discord.Forbidden:
            await ctx.send("❌ I (the bot) need the **Manage Server** (`manage_guild`) permission to enable AutoMod rules.", ephemeral=True)
        except discord.HTTPException as e:
            await ctx.send(f"❌ Failed to enable Anti-Spam: {e.text or e}", ephemeral=True)
        except Exception as e:
            logger.exception("Failed to enable Anti-Spam: %s", e)
            await ctx.send(f"❌ Error enabling Anti-Spam: {e}", ephemeral=True)

    @automod.command(name="antispam")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def automod_antispam(self, ctx: commands.Context):
        await self.automod_antispam_impl(ctx)

    async def automod_antimention_impl(self, ctx: commands.Context, max_mentions: int = 5):
        """Enable Discord's native mention spam filter rule."""
        if max_mentions < 1 or max_mentions > 50:
            await ctx.send("❌ Max mentions must be between 1 and 50.", ephemeral=True)
            return

        try:
            rule = await ctx.guild.create_automod_rule(
                name=f"Helix Mention Filter (Max {max_mentions})",
                event_type=discord.AutoModRuleEventType.message_send,
                trigger_type=discord.AutoModRuleTriggerType.mention_spam,
                trigger_metadata=make_trigger_metadata(mention_total_limit=max_mentions),
                actions=[discord.AutoModRuleAction(type=discord.AutoModRuleActionType.block_message)],
                enabled=True,
                reason=f"Created by {ctx.author}"
            )
            embed = discord.Embed(
                title="✅ Native Mention Filter Enabled!",
                description=f"Rule **{rule.name}** (`ID: {rule.id}`) is active!\nMessages exceeding **{max_mentions} mentions** will automatically be blocked.",
                color=discord.Color.green()
            )
            await ctx.send(embed=embed)
        except discord.Forbidden:
            await ctx.send("❌ I (the bot) need the **Manage Server** (`manage_guild`) permission to enable AutoMod rules.", ephemeral=True)
        except discord.HTTPException as e:
            await ctx.send(f"❌ Failed to enable Mention Filter: {e.text or e}", ephemeral=True)
        except Exception as e:
            logger.exception("Failed to enable Mention Filter: %s", e)
            await ctx.send(f"❌ Error enabling Mention Filter: {e}", ephemeral=True)

    @automod.command(name="antimention")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def automod_antimention(self, ctx: commands.Context, max_mentions: int = 5):
        await self.automod_antimention_impl(ctx, max_mentions)

    async def automod_presets_impl(self, ctx: commands.Context):
        """Enable Discord's native profanity & slurs preset filters."""
        try:
            preset_cls = getattr(discord, "AutoModPresetType", None)
            presets_list = []
            if preset_cls:
                for p_name in ["profanity", "slurs", "sexual_content"]:
                    if hasattr(preset_cls, p_name):
                        presets_list.append(getattr(preset_cls, p_name))

            rule = await ctx.guild.create_automod_rule(
                name="Helix Presets Filter",
                event_type=discord.AutoModRuleEventType.message_send,
                trigger_type=discord.AutoModRuleTriggerType.keyword_preset,
                trigger_metadata=make_trigger_metadata(
                    presets=presets_list if presets_list else [1, 2, 3]
                ),
                actions=[discord.AutoModRuleAction(type=discord.AutoModRuleActionType.block_message)],
                enabled=True,
                reason=f"Created by {ctx.author}"
            )
            embed = discord.Embed(
                title="✅ Native Preset Filters Enabled!",
                description=f"Rule **{rule.name}** (`ID: {rule.id}`) is active!\nProfanity, slurs, and explicit content will be automatically blocked.",
                color=discord.Color.green()
            )
            await ctx.send(embed=embed)
        except discord.Forbidden:
            await ctx.send("❌ I (the bot) need the **Manage Server** (`manage_guild`) permission to enable AutoMod rules.", ephemeral=True)
        except discord.HTTPException as e:
            await ctx.send(f"❌ Failed to enable Preset Filters: {e.text or e}", ephemeral=True)
        except Exception as e:
            logger.exception("Failed to enable Preset Filters: %s", e)
            await ctx.send(f"❌ Error enabling Preset Filters: {e}", ephemeral=True)

    @automod.command(name="presets")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def automod_presets(self, ctx: commands.Context):
        await self.automod_presets_impl(ctx)


    async def automod_delete_impl(self, ctx: commands.Context, rule_id: int):
        """Delete a native Discord AutoMod rule by ID."""
        try:
            rules = await ctx.guild.fetch_automod_rules()
            target_rule = next((r for r in rules if r.id == rule_id), None)
            if not target_rule:
                await ctx.send(f"❌ Rule ID `{rule_id}` not found on this server.", ephemeral=True)
                return
            await target_rule.delete(reason=f"Deleted by {ctx.author}")
            await ctx.send(f"✅ AutoMod rule **{target_rule.name}** (`ID: {rule_id}`) deleted successfully.")
        except discord.HTTPException as e:
            await ctx.send(f"❌ Failed to delete rule: {e.text or e}", ephemeral=True)

    @automod.command(name="delete")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def automod_delete(self, ctx: commands.Context, rule_id: int):
        await self.automod_delete_impl(ctx, rule_id)

    async def automod_toggle_impl(self, ctx: commands.Context, rule_id: int):
        """Enable or disable a native Discord AutoMod rule by ID."""
        try:
            rules = await ctx.guild.fetch_automod_rules()
            target_rule = next((r for r in rules if r.id == rule_id), None)
            if not target_rule:
                await ctx.send(f"❌ Rule ID `{rule_id}` not found on this server.", ephemeral=True)
                return
            new_state = not target_rule.enabled
            await target_rule.edit(enabled=new_state, reason=f"Toggled by {ctx.author}")
            state_text = "🟢 Enabled" if new_state else "🔴 Disabled"
            await ctx.send(f"✅ AutoMod rule **{target_rule.name}** (`ID: {rule_id}`) is now {state_text}.")
        except discord.HTTPException as e:
            await ctx.send(f"❌ Failed to toggle rule: {e.text or e}", ephemeral=True)

    # =========================================================================
    # ANTI-NUKE ENGINE & PROTECTION SUITE
    # =========================================================================

    def _init_antinuke_buffers(self):
        if not hasattr(self, "_antinuke_history"):
            self._antinuke_history = collections.defaultdict(lambda: collections.defaultdict(lambda: collections.defaultdict(list)))

    async def _check_and_trigger_antinuke(self, guild: discord.Guild, action_type: str, fallback_executor: Optional[discord.Member] = None):
        """Core Anti-Nuke rate limiter & protection engine."""
        if not guild:
            return

        cfg = await get_guild_config(guild.id)
        if not cfg.get("antinuke_enabled", True):
            return

        executor = fallback_executor
        try:
            audit_action_map = {
                "channel_delete": getattr(discord.AuditLogAction, "channel_delete", None),
                "channel_create": getattr(discord.AuditLogAction, "channel_create", None),
                "role_delete": getattr(discord.AuditLogAction, "role_delete", None),
                "role_create": getattr(discord.AuditLogAction, "role_create", None),
                "kick": getattr(discord.AuditLogAction, "kick", None),
                "ban": getattr(discord.AuditLogAction, "ban", None),
                "bot_add": getattr(discord.AuditLogAction, "bot_add", None),
                "webhook_spam": getattr(discord.AuditLogAction, "webhook_create", None),
                "emoji_delete": getattr(discord.AuditLogAction, "emoji_delete", None),
                "sticker_delete": getattr(discord.AuditLogAction, "sticker_delete", None),
                "permission_abuse": getattr(discord.AuditLogAction, "role_update", None),
            }
            log_action_enum = audit_action_map.get(action_type)
            if log_action_enum and guild.me and getattr(guild.me.guild_permissions, "view_audit_log", False):
                async for entry in guild.audit_logs(limit=1, action=log_action_enum):
                    if entry.user:
                        executor = entry.user
                    break
        except Exception as exc:
            logger.warning("Failed to fetch audit log for antinuke: %s", exc)

        if not executor:
            return

        # Immunity Checks:
        # 1. Server Owner is immune
        if getattr(guild, "owner_id", None) and executor.id == guild.owner_id:
            return
        # 2. Bot Owner is immune
        is_owner = False
        try:
            is_owner = await self.bot.is_owner(executor)
        except Exception:
            pass
        if is_owner:
            return
        # 3. Bot itself is immune
        if self.bot and self.bot.user and executor.id == self.bot.user.id:
            return
        # 4. Check User Whitelist
        user_wl = cfg.get("antinuke_whitelisted_users", {})
        if isinstance(user_wl, list):
            if executor.id in user_wl:
                return
        elif isinstance(user_wl, dict):
            u_cats = user_wl.get(str(executor.id), [])
            if "all" in u_cats or action_type in u_cats or (action_type == "permission_abuse" and "role_update" in u_cats) or (action_type == "webhook_spam" and "webhook" in u_cats):
                return

        # 5. Check Role Whitelist
        role_wl = cfg.get("antinuke_whitelisted_roles", {})
        if hasattr(executor, "roles"):
            for r in executor.roles:
                r_id = getattr(r, "id", None)
                if r_id is None:
                    continue
                if isinstance(role_wl, list):
                    if r_id in role_wl:
                        return
                elif isinstance(role_wl, dict):
                    r_cats = role_wl.get(str(r_id), [])
                    if "all" in r_cats or action_type in r_cats or (action_type == "permission_abuse" and "role_update" in r_cats) or (action_type == "webhook_spam" and "webhook" in r_cats):
                        return



        # Rate Limiting via Sliding Window
        self._init_antinuke_buffers()

        # Threshold limits (default: 3 actions within 10 seconds)
        thresholds = cfg.get("antinuke_thresholds", {})
        limit_data = thresholds.get(action_type, [3, 10])
        max_count, window_sec = limit_data[0], limit_data[1]

        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=window_sec)

        history = self._antinuke_history[guild.id][executor.id][action_type]
        history = [ts for ts in history if ts > cutoff]
        history.append(now)
        self._antinuke_history[guild.id][executor.id][action_type] = history

        if len(history) >= max_count:
            punishment = cfg.get("antinuke_punishment", "strip_roles")
            await self._punish_nuke_attacker(guild, executor, action_type, len(history), punishment)

    async def _punish_nuke_attacker(self, guild: discord.Guild, attacker: Union[discord.User, discord.Member], action_type: str, count: int, punishment: str):
        """Execute Anti-Nuke punishment and alert Server Owner & ModLog."""
        reason = f"🚨 Anti-Nuke Protection Triggered! Executed {count} {action_type} actions within threshold."
        member = guild.get_member(attacker.id) if isinstance(attacker, discord.User) else attacker

        punishment_applied = "None"
        try:
            if member:
                if punishment in ["strip_roles", "strip"]:
                    bot_top = getattr(guild.me, "top_role", None)
                    roles_to_remove = [r for r in member.roles if getattr(r, "name", "") != "@everyone" and (bot_top is None or r < bot_top)]
                    if roles_to_remove:
                        await member.remove_roles(*roles_to_remove, reason=reason)
                        punishment_applied = f"Stripped {len(roles_to_remove)} roles"
                    else:
                        punishment_applied = "No assignable roles to strip"
                elif punishment == "ban":
                    await guild.ban(member, reason=reason, delete_message_days=1)
                    punishment_applied = "Banned from server"
                elif punishment == "kick":
                    await member.kick(reason=reason)
                    punishment_applied = "Kicked from server"
        except Exception as e:
            logger.exception("Failed to apply antinuke punishment to %s: %s", attacker.id, e)
            punishment_applied = f"Failed ({e})"

        # Log into SQLite DB
        await log_action(
            guild_id=guild.id,
            moderator_id=self.bot.user.id if self.bot and self.bot.user else 0,
            target_id=attacker.id,
            action="ANTINUKE_PUNISH",
            reason=f"Action: {action_type} | Punishment: {punishment_applied}"
        )

        embed = discord.Embed(
            title="🚨 EMERGENCY ANTI-NUKE DETECTED!",
            description=f"Anti-Nuke protection triggered for {attacker.mention} (`ID: {attacker.id}`).",
            color=discord.Color.red(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="Trigger Event", value=f"`{action_type}` ({count} detections)", inline=True)
        embed.add_field(name="Punishment Executed", value=f"`{punishment_applied}`", inline=True)
        embed.set_footer(text=f"Anti-Nuke Engine • {guild.name}")

        cfg = await get_guild_config(guild.id)
        log_ch_id = cfg.get("antinuke_log_channel_id") or cfg.get("automod_log_channel_id") or cfg.get("modlog_channel_id")
        if log_ch_id:
            log_ch = guild.get_channel(int(log_ch_id))
            if log_ch:
                try:
                    await log_ch.send(embed=embed)
                except Exception:
                    pass

        # Send DM to Server Owner
        try:
            if getattr(guild, "owner", None):
                owner_embed = discord.Embed(
                    title=f"🚨 EMERGENCY: Anti-Nuke Triggered in {guild.name}",
                    description=f"User **{attacker}** (`ID: {attacker.id}`) triggered Anti-Nuke by performing mass **{action_type}**.\n\n**Action Taken:** {punishment_applied}",
                    color=discord.Color.red(),
                    timestamp=datetime.now(timezone.utc)
                )
                await guild.owner.send(embed=owner_embed)
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # Anti-Nuke Event Listeners (8/8 Monitored Protections)
    # -------------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        await self._check_and_trigger_antinuke(channel.guild, "channel_delete")

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        await self._check_and_trigger_antinuke(channel.guild, "channel_create")

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        await self._check_and_trigger_antinuke(role.guild, "role_delete")

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        await self._check_and_trigger_antinuke(role.guild, "role_create")

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: Union[discord.User, discord.Member]):
        await self._check_and_trigger_antinuke(guild, "ban")

        try:
            moderator = self.bot.user
            reason = "Banned directly or via Discord UI"
            try:
                async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.ban):
                    if entry.target and entry.target.id == user.id:
                        moderator = entry.user
                        if entry.reason:
                            reason = entry.reason
                        break
            except Exception:
                pass

            case = await log_action(guild.id, moderator.id if moderator else 0, user.id, "ban", reason)
            await self._post_modlog(guild, case, "Ban", moderator or self.bot.user, user, reason)
        except Exception as e:
            logger.warning("Failed to post ban modlog for user %s in %s: %s", user.id, guild.id, e)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        try:
            moderator = self.bot.user
            reason = "Unbanned directly or via Discord UI"
            try:
                async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.unban):
                    if entry.target and entry.target.id == user.id:
                        moderator = entry.user
                        if entry.reason:
                            reason = entry.reason
                        break
            except Exception:
                pass

            case = await log_action(guild.id, moderator.id if moderator else 0, user.id, "unban", reason)
            await self._post_modlog(guild, case, "Unban", moderator or self.bot.user, user, reason)
        except Exception as e:
            logger.warning("Failed to post unban modlog for user %s in %s: %s", user.id, guild.id, e)


    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        await self._check_and_trigger_antinuke(member.guild, "kick")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            await self._check_and_trigger_antinuke(member.guild, "bot_add", fallback_executor=member)

    @commands.Cog.listener()
    async def on_webhooks_update(self, channel: discord.abc.GuildChannel):
        await self._check_and_trigger_antinuke(channel.guild, "webhook_spam")

    @commands.Cog.listener()
    async def on_guild_emojis_update(self, guild: discord.Guild, before: List[discord.Emoji], after: List[discord.Emoji]):
        if len(before) > len(after):
            await self._check_and_trigger_antinuke(guild, "emoji_delete")

    @commands.Cog.listener()
    async def on_guild_stickers_update(self, guild: discord.Guild, before: List[discord.Sticker], after: List[discord.Sticker]):
        if len(before) > len(after):
            await self._check_and_trigger_antinuke(guild, "sticker_delete")

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role):
        dangerous_perms = ["administrator", "manage_guild", "manage_roles", "ban_members", "kick_members"]
        dangerous_added = False
        for p in dangerous_perms:
            was_set = getattr(before.permissions, p, False)
            now_set = getattr(after.permissions, p, False)
            if not was_set and now_set:
                dangerous_added = True
                break

        if dangerous_added:
            await self._check_and_trigger_antinuke(after.guild, "permission_abuse")

    # -------------------------------------------------------------------------
    # Anti-Nuke Commands
    # -------------------------------------------------------------------------

    @commands.hybrid_group(name="antinuke", invoke_without_command=True)
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def antinuke(self, ctx: commands.Context):
        """Anti-Nuke server defense and raid protection settings."""
        await ctx.send_help(ctx.command)

    @antinuke.command(name="config")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def antinuke_config(self, ctx: commands.Context):
        """View Anti-Nuke configuration and whitelist settings."""
        cfg = await get_guild_config(ctx.guild.id)
        enabled = cfg.get("antinuke_enabled", True)
        punishment = cfg.get("antinuke_punishment", "strip_roles")

        user_wl = cfg.get("antinuke_whitelisted_users", {})
        role_wl = cfg.get("antinuke_whitelisted_roles", {})

        u_cnt = len(user_wl) if isinstance(user_wl, (dict, list)) else 0
        r_cnt = len(role_wl) if isinstance(role_wl, (dict, list)) else 0

        status_str = "🟢 **Enabled**" if enabled else "🔴 **Disabled**"

        embed = discord.Embed(
            title=f"🛡️ Anti-Nuke Configuration — {ctx.guild.name}",
            color=discord.Color.blurple()
        )
        embed.add_field(name="Protection Status", value=status_str, inline=True)
        embed.add_field(name="Punishment Mode", value=f"`{punishment}`", inline=True)
        embed.add_field(name="Whitelisted Entries", value=f"👥 **Users:** `{u_cnt}` | 🎭 **Roles:** `{r_cnt}`", inline=True)
        embed.add_field(
            name="Protected Modules (8/8)",
            value=(
                "> • 📺 **Channel Delete**\n"
                "> • ➕ **Channel Create Spam**\n"
                "> • 🎭 **Role Delete**\n"
                "> • ➕ **Role Create Spam**\n"
                "> • 🔗 **Webhook Spam**\n"
                "> • 😃 **Emoji Delete**\n"
                "> • 🏷️ **Sticker Delete**\n"
                "> • ⚠️ **Permission Abuse**"
            ),
            inline=False
        )
        embed.set_footer(text="Use !antinuke whitelist add_user or add_role to manage whitelisted categories")
        await ctx.send(embed=embed)

    @antinuke.command(name="enable")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def antinuke_enable(self, ctx: commands.Context):
        """Enable Anti-Nuke protection for this server."""
        await set_guild_config(ctx.guild.id, {"antinuke_enabled": True})
        await ctx.send("🛡️ **Anti-Nuke Protection** is now 🟢 **Enabled** for this server.")

    @antinuke.command(name="disable")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def antinuke_disable(self, ctx: commands.Context):
        """Disable Anti-Nuke protection for this server."""
        await set_guild_config(ctx.guild.id, {"antinuke_enabled": False})
        await ctx.send("⚠️ **Anti-Nuke Protection** is now 🔴 **Disabled** for this server.")

    @antinuke.command(name="punishment")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def antinuke_punishment(self, ctx: commands.Context, mode: str):
        """Set Anti-Nuke punishment mode (strip_roles, ban, kick)."""
        mode_clean = mode.lower().strip()
        if mode_clean not in ["strip_roles", "strip", "ban", "kick"]:
            await ctx.send("❌ Invalid punishment mode. Choose from: `strip_roles`, `ban`, or `kick`.", ephemeral=True)
            return

        target_mode = "strip_roles" if mode_clean in ["strip_roles", "strip"] else mode_clean
        await set_guild_config(ctx.guild.id, {"antinuke_punishment": target_mode})
        await ctx.send(f"✅ Anti-Nuke punishment mode set to **`{target_mode}`**.")

    @antinuke.group(name="whitelist", invoke_without_command=True)
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def antinuke_whitelist(self, ctx: commands.Context):
        """Manage Anti-Nuke whitelisted users and roles with categories."""
        await ctx.send_help(ctx.command)

    @antinuke_whitelist.command(name="add_user", aliases=["add"])
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def antinuke_whitelist_add_user(self, ctx: commands.Context, user: discord.User, category: Optional[str] = "all"):
        """Add a trusted user to the Anti-Nuke whitelist with a specific category."""
        cfg = await get_guild_config(ctx.guild.id)
        user_wl = cfg.get("antinuke_whitelisted_users", {})
        if isinstance(user_wl, list):
            user_wl = {str(uid): ["all"] for uid in user_wl}

        cat_clean = category.lower().strip() if category else "all"
        u_id = str(user.id)
        existing = user_wl.get(u_id, [])

        if cat_clean == "all":
            existing = ["all"]
        else:
            if "all" in existing:
                existing.remove("all")
            if cat_clean not in existing:
                existing.append(cat_clean)

        user_wl[u_id] = existing
        await set_guild_config(ctx.guild.id, {"antinuke_whitelisted_users": user_wl})
        cats_formatted = ", ".join([f"`{c}`" for c in existing])
        await ctx.send(f"✅ {user.mention} (`ID: {user.id}`) is now whitelisted under category: {cats_formatted}.")

    @antinuke_whitelist.command(name="add_role")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def antinuke_whitelist_add_role(self, ctx: commands.Context, role: discord.Role, category: Optional[str] = "all"):
        """Add a trusted role to the Anti-Nuke whitelist with a specific category."""
        cfg = await get_guild_config(ctx.guild.id)
        role_wl = cfg.get("antinuke_whitelisted_roles", {})
        if isinstance(role_wl, list):
            role_wl = {str(rid): ["all"] for rid in role_wl}

        cat_clean = category.lower().strip() if category else "all"
        r_id = str(role.id)
        existing = role_wl.get(r_id, [])

        if cat_clean == "all":
            existing = ["all"]
        else:
            if "all" in existing:
                existing.remove("all")
            if cat_clean not in existing:
                existing.append(cat_clean)

        role_wl[r_id] = existing
        await set_guild_config(ctx.guild.id, {"antinuke_whitelisted_roles": role_wl})
        cats_formatted = ", ".join([f"`{c}`" for c in existing])
        await ctx.send(f"✅ Role {role.mention} (`ID: {role.id}`) is now whitelisted under category: {cats_formatted}.")

    @antinuke_whitelist.command(name="remove_user", aliases=["remove"])
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def antinuke_whitelist_remove_user(self, ctx: commands.Context, user: discord.User):
        """Remove a user from the Anti-Nuke whitelist."""
        cfg = await get_guild_config(ctx.guild.id)
        user_wl = cfg.get("antinuke_whitelisted_users", {})
        if isinstance(user_wl, list):
            user_wl = {str(uid): ["all"] for uid in user_wl}

        u_id = str(user.id)
        if u_id in user_wl:
            del user_wl[u_id]
            await set_guild_config(ctx.guild.id, {"antinuke_whitelisted_users": user_wl})
        await ctx.send(f"✅ {user.mention} (`ID: {user.id}`) removed from the Anti-Nuke user whitelist.")

    @antinuke_whitelist.command(name="remove_role")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def antinuke_whitelist_remove_role(self, ctx: commands.Context, role: discord.Role):
        """Remove a role from the Anti-Nuke whitelist."""
        cfg = await get_guild_config(ctx.guild.id)
        role_wl = cfg.get("antinuke_whitelisted_roles", {})
        if isinstance(role_wl, list):
            role_wl = {str(rid): ["all"] for rid in role_wl}

        r_id = str(role.id)
        if r_id in role_wl:
            del role_wl[r_id]
            await set_guild_config(ctx.guild.id, {"antinuke_whitelisted_roles": role_wl})
        await ctx.send(f"✅ Role {role.mention} (`ID: {role.id}`) removed from the Anti-Nuke role whitelist.")

    @antinuke_whitelist.command(name="show")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def antinuke_whitelist_show(self, ctx: commands.Context):
        """Show all Anti-Nuke whitelisted users and roles with categories."""
        cfg = await get_guild_config(ctx.guild.id)
        user_wl = cfg.get("antinuke_whitelisted_users", {})
        role_wl = cfg.get("antinuke_whitelisted_roles", {})

        if isinstance(user_wl, list):
            user_wl = {str(uid): ["all"] for uid in user_wl}
        if isinstance(role_wl, list):
            role_wl = {str(rid): ["all"] for rid in role_wl}

        u_lines = []
        for uid, cats in user_wl.items():
            cats_str = ", ".join([f"`{c}`" for c in cats])
            u_lines.append(f"• <@{uid}> (`ID: {uid}`): {cats_str}")

        r_lines = []
        for rid, cats in role_wl.items():
            cats_str = ", ".join([f"`{c}`" for c in cats])
            r_lines.append(f"• <@&{rid}> (`ID: {rid}`): {cats_str}")

        u_str = "\n".join(u_lines) if u_lines else "*No users whitelisted*"
        r_str = "\n".join(r_lines) if r_lines else "*No roles whitelisted*"

        embed = discord.Embed(
            title=f"🛡️ Anti-Nuke Whitelist — {ctx.guild.name}",
            color=discord.Color.blue()
        )
        embed.add_field(name="👤 Whitelisted Users", value=u_str, inline=False)
        embed.add_field(name="🎭 Whitelisted Roles", value=r_str, inline=False)
        embed.set_footer(text="Server Owner & Bot Owner are permanently immune.")
        await ctx.send(embed=embed)





class HistorySelect(discord.ui.Select):
    def __init__(self, bot, target, logs, guild):
        options = [
            discord.SelectOption(label="Vc_Mute", value="vcmute", emoji="🎙️", description="View Voice Mute history (Default)"),
            discord.SelectOption(label="Unmute", value="unmute", emoji="🔊", description="View Unmute history"),
            discord.SelectOption(label="Mute / Timeout", value="mute", emoji="🔇", description="View Text Mute & Timeout history"),
            discord.SelectOption(label="Warns", value="warn", emoji="⚠️", description="View Warning history"),
            discord.SelectOption(label="All History", value="all", emoji="📜", description="View all moderation records"),
        ]
        super().__init__(placeholder="Select history category...", min_values=1, max_values=1, options=options)
        self.bot = bot
        self.target = target
        self.logs = logs
        self.guild = guild

    async def callback(self, interaction: discord.Interaction):
        self.view.current_category = self.values[0]
        self.view.current_page = 0  # Reset to latest record
        self.view.update_buttons()
        embed = self.view.build_embed()
        await interaction.response.edit_message(embed=embed, view=self.view)


class HistorySelectView(discord.ui.View):
    def __init__(self, bot, target, logs, guild):
        super().__init__(timeout=180)
        self.bot = bot
        self.target = target
        self.logs = logs
        self.guild = guild
        self.current_category = "vcmute"  # Default category is Vc_Mute
        self.current_page = 0

        self.select_menu = HistorySelect(bot, target, logs, guild)
        self.add_item(self.select_menu)

        # Icon-only pagination buttons (no text labels)
        self.btn_prev = discord.ui.Button(emoji="◀", style=discord.ButtonStyle.secondary, row=1)
        self.btn_next = discord.ui.Button(emoji="▶", style=discord.ButtonStyle.secondary, row=1)

        self.btn_prev.callback = self.on_prev
        self.btn_next.callback = self.on_next

        self.add_item(self.btn_prev)
        self.add_item(self.btn_next)
        self.update_buttons()

    def get_filtered_records(self):
        cat = self.current_category
        if cat == "vcmute":
            return [l for l in self.logs if l["action"].lower() == "vcmute"]
        elif cat == "mute":
            return [l for l in self.logs if l["action"].lower() in ("mute", "tempmute")]
        elif cat == "unmute":
            return [l for l in self.logs if l["action"].lower() in ("unmute", "vcunmute")]
        elif cat == "warn":
            return [l for l in self.logs if l["action"].lower() == "warn"]
        else:
            return self.logs

    def update_buttons(self):
        records = self.get_filtered_records()
        total = len(records)
        self.btn_prev.disabled = (self.current_page <= 0)
        self.btn_next.disabled = (self.current_page >= total - 1 or total == 0)

    async def on_prev(self, interaction: discord.Interaction):
        if self.current_page > 0:
            self.current_page -= 1
        self.update_buttons()
        embed = self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    async def on_next(self, interaction: discord.Interaction):
        records = self.get_filtered_records()
        if self.current_page < len(records) - 1:
            self.current_page += 1
        self.update_buttons()
        embed = self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    def build_embed(self) -> discord.Embed:
        records = self.get_filtered_records()
        cat_names = {
            "vcmute": "Vc_Mute",
            "mute": "Mute / Timeout",
            "unmute": "Unmute",
            "warn": "Warn",
            "all": "Moderation"
        }
        cat_title = cat_names.get(self.current_category, "Vc_Mute")
        target_name = getattr(self.target, "name", str(self.target))

        embed = discord.Embed(
            title=f"📜 Moderation History — {cat_title} History for {target_name}",
            color=discord.Color.blurple(),
            timestamp=datetime.now(timezone.utc)
        )


        if getattr(self.target, "display_avatar", None):
            embed.set_thumbnail(url=self.target.display_avatar.url)

        counts = {}
        for l in self.logs:
            act = l["action"].upper()
            counts[act] = counts.get(act, 0) + 1

        summary_parts = [f"**{act}**: {cnt}" for act, cnt in counts.items()]
        summary_text = f"**Summary of Records:** {', '.join(summary_parts)}\n\n"

        if not records:
            embed.description = summary_text + f"No `{cat_title}` records found for {getattr(self.target, 'mention', self.target)}."
            embed.set_footer(text=f"Page 0/0 • Record #0 • {self.guild.name}")
            return embed

        embed.description = summary_text
        total = len(records)
        self.current_page = max(0, min(self.current_page, total - 1))
        case_item = records[self.current_page]

        try:
            dt = datetime.fromisoformat(case_item["created_at"])
            date_str = dt.strftime("%A, %d %B, %Y %H:%M")
        except Exception:
            date_str = case_item["created_at"]

        mod_id = case_item["moderator_id"]
        moderator = self.guild.get_member(int(mod_id))
        mod_name = moderator.mention if moderator else f"<@{mod_id}>"
        act_label = case_item["action"].upper()
        reason = case_item["reason"] or "No reason provided"

        field_val = (
            f"**Type**\n`{act_label}`\n\n"
            f"**Reason**\n> {reason}\n\n"
            f"• **By:** {mod_name}\n"
            f"• **Date:** {date_str}"
        )

        embed.add_field(
            name=f"Case #{case_item['case_id']}",
            value=field_val,
            inline=False
        )

        page_num = self.current_page + 1
        record_num = total - self.current_page
        embed.set_footer(text=f"Page {page_num}/{total} • Record #{record_num} • {self.guild.name}")
        return embed


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))




