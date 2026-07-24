import io
import logging
import re
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Union

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


class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

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
        """Resolve a role mention, ID, or case-insensitive role name in this guild."""
        query = role_query.strip()
        match = re.fullmatch(r"<@&(\d+)>|(\d+)", query)
        if match:
            role = guild.get_role(int(match.group(1) or match.group(2)))
            return role, None if role else "I could not find a role with that ID."

        matches = [role for role in guild.roles if role.name.casefold() == query.casefold()]
        if not matches:
            return None, f"I could not find a role named `{role_query}` in this server."
        if len(matches) > 1:
            return None, "More than one role has that name. Use the role mention or role ID instead."
        return matches[0], None

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

    @commands.hybrid_command(name="ban")
    @commands.guild_only()
    async def ban(self, ctx: commands.Context, target: discord.Member, *, reason: Optional[str] = None, delete_days: Optional[int] = 0):
        """Ban a member from the guild"""
        if not ctx.author.guild_permissions.ban_members:
            await ctx.send("You don't have permission to ban members.", ephemeral=True)
            return

        deny = await self._ensure_can_moderate(ctx, target)
        if deny:
            await ctx.send(deny, ephemeral=True)
            return

        try:
            await target.ban(reason=reason, delete_message_days=delete_days or 0)
            case = await log_action(ctx.guild.id, ctx.author.id, target.id, "ban", reason)
            await ctx.send(f"Banned {target} ({target.id})")
            await self._post_modlog(ctx.guild, case, "Ban", ctx.author, target, reason)
        except Exception as exc:
            logger.exception("Failed to ban: %s", exc)
            await ctx.send(f"Failed to ban {target}", ephemeral=True)

    @commands.hybrid_command(name="unban")
    @commands.guild_only()
    async def unban(self, ctx: commands.Context, user: discord.User, *, reason: Optional[str] = None):
        """Unban a user by user object or ID"""
        if not ctx.author.guild_permissions.ban_members:
            await ctx.send("You don't have permission to unban members.", ephemeral=True)
            return
        try:
            await ctx.guild.unban(user, reason=reason)
            case = await log_action(ctx.guild.id, ctx.author.id, user.id, "unban", reason)
            await ctx.send(f"Unbanned {user} ({user.id})")
            await self._post_modlog(ctx.guild, case, "Unban", ctx.author, user, reason)
        except discord.errors.NotFound as exc:
            if exc.code == 10026:
                await ctx.send("❌ That user is not banned in this server.", ephemeral=True)
            else:
                await ctx.send(f"❌ Failed to unban {user}: User not found.", ephemeral=True)
        except discord.errors.Forbidden:
            await ctx.send("❌ I need the **Ban Members** permission to unban users.", ephemeral=True)
        except Exception as exc:
            logger.exception("Failed to unban: %s", exc)
            await ctx.send(f"❌ Failed to unban {user}.", ephemeral=True)

    @commands.hybrid_command(name="softban")
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

    @commands.hybrid_command(name="hardban")
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

    @commands.hybrid_command(name="timeout")
    @commands.guild_only()
    async def timeout(self, ctx: commands.Context, target: discord.Member, minutes: Optional[int] = 10, *, reason: Optional[str] = None):
        """Mute a member using Discord timeouts"""
        if not ctx.author.guild_permissions.moderate_members:
            await ctx.send("You don't have permission to timeout members.", ephemeral=True)
            return

        deny = await self._ensure_can_moderate(ctx, target)
        if deny:
            await ctx.send(deny, ephemeral=True)
            return

        try:
            until = (datetime.now(timezone.utc) + timedelta(minutes=minutes)) if minutes and minutes > 0 else None
            await target.edit(timed_out_until=until, reason=reason)
            case = await log_action(ctx.guild.id, ctx.author.id, target.id, "timeout", reason or f"timeout {minutes}m")
            await ctx.send(f"Timed out {target} for {minutes} minute(s)")
            await self._post_modlog(ctx.guild, case, "Timeout", ctx.author, target, reason)
        except Exception as exc:
            logger.exception("Failed to timeout: %s", exc)
            await ctx.send(f"Failed to timeout {target}", ephemeral=True)

    @commands.hybrid_command(name="warn")
    @commands.guild_only()
    async def warn(self, ctx: commands.Context, target: discord.Member, *, reason: Optional[str] = "No reason provided"):
        """Warn a member"""
        if not (ctx.author.guild_permissions.kick_members or ctx.author.guild_permissions.manage_messages):
            await ctx.send("You don't have permission to warn members.", ephemeral=True)
            return

        deny = await self._ensure_can_moderate(ctx, target)
        if deny:
            await ctx.send(deny, ephemeral=True)
            return

        try:
            case = await log_action(ctx.guild.id, ctx.author.id, target.id, "warn", reason)
            try:
                await target.send(f"You have been warned in {ctx.guild.name}: {reason}")
            except Exception:
                pass
            await ctx.send(f"Warned {target} ({target.id})")
            await self._post_modlog(ctx.guild, case, "Warn", ctx.author, target, reason)
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

    @commands.hybrid_command(name="purge")
    @commands.guild_only()
    async def purge(self, ctx: commands.Context, limit: int = 10):
        """Bulk delete messages from the current channel (1-100)"""
        if not ctx.author.guild_permissions.manage_messages:
            await ctx.send("You don't have permission to manage messages.", ephemeral=True)
            return
        if limit < 1 or limit > 100:
            await ctx.send("Limit must be between 1 and 100.", ephemeral=True)
            return
        await ctx.defer(ephemeral=True)
        try:
            deleted = await ctx.channel.purge(limit=limit)
            case = await log_action(ctx.guild.id, ctx.author.id, 0, "purge", f"count={len(deleted)}")
            await ctx.send(f"Deleted {len(deleted)} messages.", ephemeral=True)
            await self._post_modlog(ctx.guild, case, "Purge", ctx.author, ctx.channel, f"count={len(deleted)}")
        except Exception as exc:
            logger.exception("Failed to purge messages: %s", exc)
            await ctx.send("Failed to purge messages.", ephemeral=True)

    @commands.hybrid_command(name="giverole", aliases=["role", "addrole"])
    @commands.guild_only()
    async def giverole(self, ctx: commands.Context, target: discord.Member, *, role_name: str):
        """Toggle a role for a member. If they have it, removes it; otherwise adds it."""
        if not ctx.author.guild_permissions.manage_roles:
            await ctx.send("You need the **Manage Roles** permission to modify roles.", ephemeral=True)
            return

        role, error = self._find_role_by_name(ctx.guild, role_name)
        if error:
            await ctx.send(error, ephemeral=True)
            return

        bot_member = ctx.guild.me or ctx.guild.get_member(self.bot.user.id)
        deny = self._role_assignment_error(ctx.guild, ctx.author, bot_member, role)
        if deny:
            await ctx.send(deny, ephemeral=True)
            return

        if role in target.roles:
            try:
                await target.remove_roles(role, reason=f"Removed by {ctx.author} ({ctx.author.id})")
                case = await log_action(ctx.guild.id, ctx.author.id, target.id, "role_remove", role.name)
                await ctx.send(f"Removed role **{role.name}** from {target}.")
                await self._post_modlog(ctx.guild, case, "Role Remove", ctx.author, target, role.name)
            except Exception as exc:
                logger.exception("Failed to remove role: %s", exc)
                await ctx.send("Failed to remove role.", ephemeral=True)
        else:
            try:
                await target.add_roles(role, reason=f"Assigned by {ctx.author} ({ctx.author.id})")
                case = await log_action(ctx.guild.id, ctx.author.id, target.id, "role_add", role.name)
                await ctx.send(f"Added role **{role.name}** to {target}.")
                await self._post_modlog(ctx.guild, case, "Role Add", ctx.author, target, role.name)
            except Exception as exc:
                logger.exception("Failed to add role: %s", exc)
                await ctx.send("Failed to add role.", ephemeral=True)

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
        """Force a member's nickname and lock it so they cannot change it. Use 'reset', 'off', or 'clear' to unlock."""
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

    async def _post_modlog(self, guild: discord.Guild, case_id: int, action: str, moderator: discord.abc.User, target, reason: Optional[str]):
        """Post a mod action embed to the configured mod log channel for the guild, if set."""
        try:
            cfg = await get_guild_config(guild.id)
            ch_id = cfg.get("mod_log_channel") or cfg.get("modlog_channel")
            if not ch_id:
                return
            try:
                ch_id = int(ch_id)
            except Exception:
                return
            channel = guild.get_channel(ch_id) or self.bot.get_channel(ch_id)
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

    @commands.hybrid_command(name="vcmute")
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

    @commands.hybrid_command(name="vcunmute")
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


