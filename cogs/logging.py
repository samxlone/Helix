import logging
import re
from datetime import datetime, timezone
from typing import Optional
import discord
from discord.ext import commands

from utils.config_service import get_guild_config, set_guild_config

logger = logging.getLogger(__name__)


async def get_action_log_channel(guild: discord.Guild, event_type: str) -> Optional[discord.TextChannel]:
    """Find the dedicated action log channel based on config or channel name patterns."""
    if not guild:
        return None

    try:
        cfg = await get_guild_config(guild.id)
    except Exception:
        cfg = {}

    # 1. Config Key Mapping
    cfg_key_map = {
        "ban_unban": ["ban_unban_log_channel_id", "ban_log_channel_id", "ban_unban_log", "ban_log"],
        "automod": ["automod_log_channel_id", "wick_log_channel_id", "automod_log"],
        "wick": ["automod_log_channel_id", "wick_log_channel_id"],
        "antinuke": ["antinuke_log_channel_id", "security_log_channel_id", "antinuke_log"],
        "security": ["antinuke_log_channel_id", "security_log_channel_id"],
        "role_create": ["role_create_log_channel_id", "role_create_log"],
        "role_update": ["role_update_log_channel_id", "role_update_log"],
        "role_delete": ["role_delete_log_channel_id", "role_delete_log"],
        "role_add_remove": ["role_add_remove_log_channel_id", "role_add_remove_log", "member_role_log_channel_id"],
        "channel_create": ["channel_create_log_channel_id", "channel_create_log"],
        "channel_delete": ["channel_delete_log_channel_id", "channel_delete_log"],
        "voice": ["voice_log_channel_id", "vc_log_channel_id", "voice_log"],
        "msg_edit": ["message_log_channel_id", "msg_edit_log_channel_id", "message_log"],
        "msg_delete": ["message_log_channel_id", "msg_delete_log_channel_id", "message_log"],
        "message": ["message_log_channel_id", "message_log"],
        "image": ["image_log_channel_id", "image_log"],
        "image_log": ["image_log_channel_id", "image_log"],
        "member_join": ["join_leave_log_channel_id", "member_log_channel_id", "join_log_channel_id"],
        "member_leave": ["join_leave_log_channel_id", "member_log_channel_id", "leave_log_channel_id"],
        "join_leave": ["join_leave_log_channel_id", "member_log_channel_id"],
        "member": ["join_leave_log_channel_id", "member_log_channel_id"],
    }

    keys_to_check = cfg_key_map.get(event_type, [])
    for k in keys_to_check:
        ch_id = cfg.get(k)
        if ch_id:
            try:
                ch = guild.get_channel(int(ch_id))
                if ch:
                    return ch
            except Exception:
                pass

    # 2. Channel Name Patterns Fallback (Exact matches first, then partial)
    name_patterns_map = {
        "ban_unban": ["ban-unban_log", "ban-unban-log", "ban_unban_log", "ban-log", "ban_log", "unban-log", "unban_log", "bans-log"],
        "automod": ["automod-log", "automod_log", "automod-logs", "wick-log", "wick_log"],
        "wick": ["automod-log", "automod_log", "wick-log", "wick_log"],
        "antinuke": ["antinuke-log", "antinuke_log", "antinuke-logs", "security-log", "security_log"],
        "security": ["antinuke-log", "antinuke_log", "security-log", "security_log"],
        "role_create": ["role-create-log", "role_create_log", "role-create-logs", "role-create"],
        "role_update": ["role-update-log", "role_update_log", "role-update-logs", "role-update"],
        "role_delete": ["role-delete-log", "role_delete_log", "role-delete-logs", "role-delete"],
        "role_add_remove": ["role-add-remove-log", "role_add_remove_log", "role-add-remove", "role-changes-log", "member-role-log"],
        "channel_create": ["channel-create-log", "channel_create_log", "channel-create-logs", "channel-create"],
        "channel_delete": ["channel-delete-log", "channel_delete_log", "channel-delete-logs", "channel-delete"],
        "voice": ["voice-log", "voice_log", "vc-log", "vc_log", "voice-logs", "vc-logs"],
        "msg_edit": ["message-log", "message_log", "msg-log", "message-edit-log"],
        "msg_delete": ["message-log", "message_log", "msg-log", "message-delete-log"],
        "message": ["message-log", "message_log", "msg-log"],
        "image": ["image-log", "image_log", "img-log", "image-logs"],
        "image_log": ["image-log", "image_log", "img-log", "image-logs"],
        "member_join": ["join-leave-log", "join_leave_log", "member-log", "join-log"],
        "member_leave": ["join-leave-log", "join_leave_log", "member-log", "leave-log"],
        "join_leave": ["join-leave-log", "join_leave_log", "member-log"],
        "member": ["join-leave-log", "join_leave_log", "member-log"],
    }


    patterns = name_patterns_map.get(event_type, [])
    # First pass: check patterns in order of priority against exact channel names
    for pat in patterns:
        for ch in getattr(guild, "text_channels", []):
            norm_name = ch.name.lower().replace(" ", "-")
            if pat == norm_name:
                return ch

    # Second pass: check patterns in order of priority against partial channel names
    for pat in patterns:
        for ch in getattr(guild, "text_channels", []):
            norm_name = ch.name.lower().replace(" ", "-")
            if pat in norm_name:
                return ch

    # 3. General Modlog Fallback
    ch_id = cfg.get("mod_log_channel") or cfg.get("modlog_channel") or cfg.get("modlog_channel_id")
    if ch_id:
        try:
            ch = guild.get_channel(int(ch_id))
            if ch:
                return ch
        except Exception:
            pass

    for ch in getattr(guild, "text_channels", []):
        if ch.name.lower() in ("mod-log", "modlog", "mod-logs", "logs", "audit-log"):
            return ch

    return None


class AuditLogger(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _get_log_channel(self, guild: discord.Guild, event_type: str = "general") -> Optional[discord.TextChannel]:
        return await get_action_log_channel(guild, event_type)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return

        # Check for image attachments or image URLs
        image_urls = []

        if message.attachments:
            for att in message.attachments:
                content_type = getattr(att, "content_type", "") or ""
                if content_type.startswith("image/"):
                    image_urls.append(att.url)
                elif any(att.filename.lower().endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".gif", ".webp")):
                    image_urls.append(att.url)

        if not image_urls and message.content:
            url_match = re.findall(r"(https?://\S+\.(?:png|jpg|jpeg|gif|webp))", message.content, re.IGNORECASE)
            if url_match:
                image_urls.extend(url_match)

        if not image_urls:
            return

        channel = await self._get_log_channel(message.guild, "image")
        if not channel:
            return

        if message.channel.id == channel.id:
            return

        for img_url in image_urls[:3]:
            embed = discord.Embed(
                title="Image Logged",
                description=f"Image uploaded by {message.author.mention} in {message.channel.mention}.\n[Jump to Message]({message.jump_url})",
                color=discord.Color.blue(),
                timestamp=datetime.now(timezone.utc)
            )
            author_avatar = message.author.display_avatar.url if hasattr(message.author, "display_avatar") else (message.author.avatar.url if hasattr(message.author, "avatar") and message.author.avatar else None)
            embed.set_author(name=str(message.author), icon_url=author_avatar)
            embed.set_image(url=img_url)
            embed.add_field(name="User ID", value=f"`{message.author.id}`", inline=True)
            embed.add_field(name="Channel ID", value=f"`{message.channel.id}`", inline=True)
            try:
                await channel.send(embed=embed)
            except Exception:
                pass

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.author.bot:
            return
        if before.content == after.content:
            return

        channel = await self._get_log_channel(before.guild, "msg_edit")
        if not channel:
            return

        embed = discord.Embed(
            title="Message Edited",
            description=f"Message sent by {before.author.mention} was edited in {before.channel.mention}.",
            color=discord.Color.orange(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_author(name=str(before.author), icon_url=before.author.avatar.url if before.author.avatar else None)

        before_content = before.content[:1000] or "*(No text content)*"
        after_content = after.content[:1000] or "*(No text content)*"

        embed.add_field(name="Before", value=before_content, inline=False)
        embed.add_field(name="After", value=after_content, inline=False)
        embed.add_field(name="User ID", value=f"`{before.author.id}`", inline=True)

        owner = self.bot.owner_user if hasattr(self.bot, "owner_user") else None
        if owner:
            embed.set_footer(text=f"Created & Owned by {owner.name}", icon_url=owner.avatar.url if owner.avatar else None)
        else:
            embed.set_footer(text="Owned by Bot Owner")

        try:
            await channel.send(embed=embed)
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.author.bot:
            return

        channel = await self._get_log_channel(message.guild, "msg_delete")
        if not channel:
            return

        embed = discord.Embed(
            title="Message Deleted",
            description=f"Message sent by {message.author.mention} was deleted in {message.channel.mention}.",
            color=discord.Color.red(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_author(name=str(message.author), icon_url=message.author.avatar.url if message.author.avatar else None)

        content = message.content[:1000] or "*(No text content)*"
        embed.add_field(name="Content", value=content, inline=False)
        embed.add_field(name="User ID", value=f"`{message.author.id}`", inline=True)

        if message.attachments:
            files_str = ", ".join(f"`{a.filename}`" for a in message.attachments)
            embed.add_field(name="Attachments", value=files_str, inline=False)

        owner = self.bot.owner_user if hasattr(self.bot, "owner_user") else None
        if owner:
            embed.set_footer(text=f"Created & Owned by {owner.name}", icon_url=owner.avatar.url if owner.avatar else None)
        else:
            embed.set_footer(text="Owned by Bot Owner")

        try:
            await channel.send(embed=embed)
        except Exception:
            pass


    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        channel = await self._get_log_channel(member.guild, "member_join")
        if not channel:
            return

        created_at = int(member.created_at.timestamp())
        embed = discord.Embed(
            title="Member Joined",
            description=f"{member.mention} has joined the server.",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )
        avatar_url = member.display_avatar.url if hasattr(member, "display_avatar") else (member.avatar.url if member.avatar else member.default_avatar.url)
        embed.set_thumbnail(url=avatar_url)
        embed.add_field(name="Account Created", value=f"<t:{created_at}:F> (<t:{created_at}:R>)", inline=False)
        embed.add_field(name="Member ID", value=f"`{member.id}`", inline=True)

        age_days = (datetime.now(timezone.utc) - member.created_at).days
        if age_days < 7:
            embed.add_field(name="Security Alert", value="**New Account Warning:** This account is less than 7 days old!", inline=False)
            embed.color = discord.Color.gold()

        owner = self.bot.owner_user if hasattr(self.bot, "owner_user") else None
        if owner:
            embed.set_footer(text=f"Created & Owned by {owner.name}", icon_url=owner.avatar.url if owner.avatar else None)
        else:
            embed.set_footer(text="Owned by Bot Owner")

        try:
            await channel.send(embed=embed)
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        channel = await self._get_log_channel(member.guild, "member_leave")
        if not channel:
            return

        embed = discord.Embed(
            title="Member Left",
            description=f"{member.mention} has left the server.",
            color=discord.Color.light_grey(),
            timestamp=datetime.now(timezone.utc)
        )
        avatar_url = member.display_avatar.url if hasattr(member, "display_avatar") else (member.avatar.url if member.avatar else member.default_avatar.url)
        embed.set_thumbnail(url=avatar_url)
        embed.add_field(name="Member ID", value=f"`{member.id}`", inline=True)

        roles = [r.mention for r in member.roles if r != member.guild.default_role]
        if roles:
            roles_str = ", ".join(roles[:15])
            if len(roles) > 15:
                roles_str += f" ...and {len(roles) - 15} more"
            embed.add_field(name="Roles Held", value=roles_str, inline=False)

        owner = self.bot.owner_user if hasattr(self.bot, "owner_user") else None
        if owner:
            embed.set_footer(text=f"Created & Owned by {owner.name}", icon_url=owner.avatar.url if owner.avatar else None)
        else:
            embed.set_footer(text="Owned by Bot Owner")

        try:
            await channel.send(embed=embed)
        except Exception:
            pass


    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        channel = await self._get_log_channel(role.guild, "role_create")
        if not channel:
            return

        executor = "Unknown"
        try:
            async for entry in role.guild.audit_logs(limit=5, action=discord.AuditLogAction.role_create):
                if entry.target and entry.target.id == role.id:
                    executor = str(entry.user)
                    break
        except Exception:
            pass

        embed = discord.Embed(
            title="🛡️ Role Created",
            description=f"Role **{role.name}** (`{role.id}`) was created.",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="Role Name", value=role.mention, inline=True)
        embed.add_field(name="Created By", value=executor, inline=True)
        embed.add_field(name="Color", value=f"`#{role.color.value:06X}`", inline=True)
        try:
            await channel.send(embed=embed)
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role):
        channel = await self._get_log_channel(after.guild, "role_update")
        if not channel:
            return

        changes = []
        if before.name != after.name:
            changes.append(f"**Name:** `{before.name}` ➔ `{after.name}`")
        if before.color != after.color:
            changes.append(f"**Color:** `#{before.color.value:06X}` ➔ `#{after.color.value:06X}`")
        if before.permissions != after.permissions:
            changes.append(f"**Permissions Changed**")

        if not changes:
            return

        embed = discord.Embed(
            title="⚙️ Role Updated",
            description=f"Role {after.mention} (`{after.id}`) was updated.",
            color=discord.Color.gold(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="Changes", value="\n".join(changes), inline=False)
        try:
            await channel.send(embed=embed)
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        channel = await self._get_log_channel(role.guild, "role_delete")
        if not channel:
            return

        executor = "Unknown"
        try:
            async for entry in role.guild.audit_logs(limit=5, action=discord.AuditLogAction.role_delete):
                if entry.target and entry.target.id == role.id:
                    executor = str(entry.user)
                    break
        except Exception:
            pass

        embed = discord.Embed(
            title="🗑️ Role Deleted",
            description=f"Role **{role.name}** (`{role.id}`) was deleted.",
            color=discord.Color.red(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="Deleted By", value=executor, inline=True)
        try:
            await channel.send(embed=embed)
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.roles == after.roles:
            return

        channel = await self._get_log_channel(after.guild, "role_add_remove")
        if not channel:
            return

        added_roles = [r for r in after.roles if r not in before.roles]
        removed_roles = [r for r in before.roles if r not in after.roles]

        if not added_roles and not removed_roles:
            return

        executor = "Unknown"
        try:
            async for entry in after.guild.audit_logs(limit=5, action=discord.AuditLogAction.member_role_update):
                if entry.target and entry.target.id == after.id:
                    executor = str(entry.user)
                    break
        except Exception:
            pass

        embed = discord.Embed(
            title="👤 Member Roles Changed",
            description=f"Roles updated for {after.mention} (`ID: {after.id}`).",
            color=discord.Color.purple(),
            timestamp=datetime.now(timezone.utc)
        )
        if added_roles:
            embed.add_field(name="➕ Roles Added", value=", ".join(r.mention for r in added_roles), inline=False)
        if removed_roles:
            embed.add_field(name="➖ Roles Removed", value=", ".join(r.mention for r in removed_roles), inline=False)
        embed.add_field(name="Updated By", value=executor, inline=True)

        try:
            await channel.send(embed=embed)
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        log_ch = await self._get_log_channel(channel.guild, "channel_create")
        if not log_ch:
            return

        executor = "Unknown"
        try:
            async for entry in channel.guild.audit_logs(limit=5, action=discord.AuditLogAction.channel_create):
                if entry.target and entry.target.id == channel.id:
                    executor = str(entry.user)
                    break
        except Exception:
            pass

        embed = discord.Embed(
            title="📺 Channel Created",
            description=f"Channel {channel.mention} (`{channel.id}`) was created.",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="Type", value=str(channel.type).capitalize(), inline=True)
        embed.add_field(name="Created By", value=executor, inline=True)
        try:
            await log_ch.send(embed=embed)
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        log_ch = await self._get_log_channel(channel.guild, "channel_delete")
        if not log_ch:
            return

        executor = "Unknown"
        try:
            async for entry in channel.guild.audit_logs(limit=5, action=discord.AuditLogAction.channel_delete):
                if entry.target and entry.target.id == channel.id:
                    executor = str(entry.user)
                    break
        except Exception:
            pass

        embed = discord.Embed(
            title="🗑️ Channel Deleted",
            description=f"Channel **#{channel.name}** (`{channel.id}`) was deleted.",
            color=discord.Color.red(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="Type", value=str(channel.type).capitalize(), inline=True)
        embed.add_field(name="Deleted By", value=executor, inline=True)
        try:
            await log_ch.send(embed=embed)
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        channel = await self._get_log_channel(member.guild, "voice")
        if not channel:
            return

        embed = discord.Embed(timestamp=datetime.now(timezone.utc))
        embed.set_author(name=str(member), icon_url=member.avatar.url if member.avatar else member.default_avatar.url)

        if before.channel is None and after.channel is not None:
            embed.title = "🔊 Joined Voice Channel"
            embed.description = f"{member.mention} joined {after.channel.mention} (`ID: {after.channel.id}`)."
            embed.color = discord.Color.green()
        elif before.channel is not None and after.channel is None:
            embed.title = "🔇 Left Voice Channel"
            embed.description = f"{member.mention} left {before.channel.mention} (`ID: {before.channel.id}`)."
            embed.color = discord.Color.red()
        elif before.channel is not None and after.channel is not None and before.channel.id != after.channel.id:
            embed.title = "🔄 Switched Voice Channel"
            embed.description = f"{member.mention} moved from {before.channel.mention} to {after.channel.mention}."
            embed.color = discord.Color.blue()
        else:
            changes = []
            if before.self_mute != after.self_mute:
                changes.append(f"**Self Mute:** `{before.self_mute}` ➔ `{after.self_mute}`")
            if before.self_deaf != after.self_deaf:
                changes.append(f"**Self Deafen:** `{before.self_deaf}` ➔ `{after.self_deaf}`")
            if before.mute != after.mute:
                changes.append(f"**Server Mute:** `{before.mute}` ➔ `{after.mute}`")
            if before.deaf != after.deaf:
                changes.append(f"**Server Deafen:** `{before.deaf}` ➔ `{after.deaf}`")

            if not changes:
                return

            embed.title = "🎤 Voice State Updated"
            embed.description = f"Voice state changed for {member.mention} in {after.channel.mention if after.channel else 'VC'}."
            embed.add_field(name="Changes", value="\n".join(changes), inline=False)
            embed.color = discord.Color.gold()

        embed.add_field(name="User ID", value=f"`{member.id}`", inline=True)
        try:
            await channel.send(embed=embed)
        except Exception:
            pass

    @commands.command(name="setup_logs", aliases=["createlogs", "logsetup", "create_log_channels", "setup_log_category"])
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def setup_logs(self, ctx: commands.Context):
        """Automatically create a LOGS category and specialized log channels for every action."""
        await ctx.send(f"⏳ **Setting up specialized log channels for `{ctx.guild.name}`...**")

        cat_name = "Helix Logs"
        category = (
            discord.utils.get(ctx.guild.categories, name="Helix Logs")
            or discord.utils.get(ctx.guild.categories, name="helix logs")
            or discord.utils.get(ctx.guild.categories, name="Helix Logs 📊")
            or discord.utils.get(ctx.guild.categories, name="LOGS")
        )

        if not category:
            try:
                overwrites = {}
                if hasattr(ctx.guild, "default_role") and hasattr(ctx.guild, "me"):
                    try:
                        overwrites = {
                            ctx.guild.default_role: discord.PermissionOverwrite(read_messages=False),
                            ctx.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
                        }
                    except Exception:
                        pass
                category = await ctx.guild.create_category(name=cat_name, overwrites=overwrites, reason="Helix Setup Logs")
            except Exception as e:
                await ctx.send(f"❌ Failed to create category `{cat_name}`: {e}")
                return

        channels_spec = [
            ("ban-unban_log", "ban_unban_log_channel_id", "Bans, unbans, and kicks"),
            ("automod-log", "automod_log_channel_id", "Automod and protection alerts"),
            ("antinuke-log", "antinuke_log_channel_id", "Anti-Nuke and emergency security alerts"),
            ("message-log", "message_log_channel_id", "Message edits and deleted messages"),
            ("image-log", "image_log_channel_id", "Image uploads and image media log"),
            ("join-leave-log", "join_leave_log_channel_id", "Member joins and member leaves"),
            ("role-create-log", "role_create_log_channel_id", "Role creation events"),
            ("role-update-log", "role_update_log_channel_id", "Role modification events"),
            ("role-delete-log", "role_delete_log_channel_id", "Role deletion events"),
            ("role-add-remove-log", "role_add_remove_log_channel_id", "Member role changes"),
            ("channel-create-log", "channel_create_log_channel_id", "Channel creation events"),
            ("channel-delete-log", "channel_delete_log_channel_id", "Channel deletion events"),
            ("voice-log", "voice_log_channel_id", "Voice channel joins, leaves, moves, and mutes"),
        ]

        created_channels = []
        config_update = {}

        for ch_name, cfg_key, desc in channels_spec:
            existing = discord.utils.get(category.channels, name=ch_name) or discord.utils.get(ctx.guild.text_channels, name=ch_name)
            if not existing:
                try:
                    existing = await ctx.guild.create_text_channel(name=ch_name, category=category, topic=desc, reason="Helix Setup Logs")
                except Exception as e:
                    logger.warning("Failed to create log channel %s: %s", ch_name, e)
                    continue

            created_channels.append(existing)
            config_update[cfg_key] = str(existing.id)

        if config_update:
            await set_guild_config(ctx.guild.id, config_update)

        embed = discord.Embed(
            title="Action Log Channels Created & Configured",
            description=f"Successfully created category **{category.name}** and configured **{len(created_channels)}** specialized log channel(s).",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )

        for ch_name, cfg_key, desc in channels_spec:
            ch_obj = discord.utils.get(created_channels, name=ch_name)
            ch_mention = getattr(ch_obj, "mention", f"#{ch_name}") if ch_obj else "Failed"
            embed.add_field(name=f"• #{ch_name}", value=f"{ch_mention} — *{desc}*", inline=False)

        await ctx.send(embed=embed)

    @commands.command(name="setlog", aliases=["logset", "set_log", "bind_log"])
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def setlog(self, ctx: commands.Context, event_type: str, channel: discord.TextChannel):
        """Configure a specific log channel for an action event."""
        ev_norm = event_type.lower().strip().replace("-", "_")

        key_map = {
            "ban": "ban_unban_log_channel_id",
            "unban": "ban_unban_log_channel_id",
            "ban_unban": "ban_unban_log_channel_id",
            "automod": "automod_log_channel_id",
            "wick": "automod_log_channel_id",
            "antinuke": "antinuke_log_channel_id",
            "security": "antinuke_log_channel_id",
            "role_create": "role_create_log_channel_id",
            "role_update": "role_update_log_channel_id",
            "role_delete": "role_delete_log_channel_id",
            "role_add_remove": "role_add_remove_log_channel_id",
            "role_change": "role_add_remove_log_channel_id",
            "channel_create": "channel_create_log_channel_id",
            "channel_delete": "channel_delete_log_channel_id",
            "voice": "voice_log_channel_id",
            "vc": "voice_log_channel_id",
            "message": "message_log_channel_id",
            "msg": "message_log_channel_id",
            "message_log": "message_log_channel_id",
            "image": "image_log_channel_id",
            "image_log": "image_log_channel_id",
            "img": "image_log_channel_id",
            "join": "join_leave_log_channel_id",
            "leave": "join_leave_log_channel_id",
            "join_leave": "join_leave_log_channel_id",
            "member": "join_leave_log_channel_id",
            "member_join": "join_leave_log_channel_id",
            "member_leave": "join_leave_log_channel_id",
        }

        cfg_key = key_map.get(ev_norm)
        if not cfg_key:
            valid_types = "`ban_unban`, `automod`, `antinuke`, `message`, `image`, `join_leave`, `role_create`, `role_update`, `role_delete`, `role_add_remove`, `channel_create`, `channel_delete`, `voice`"
            await ctx.send(f"❌ Invalid event type **`{event_type}`**.\nValid options: {valid_types}")
            return

        await set_guild_config(ctx.guild.id, {cfg_key: str(channel.id)})

        ch_mention = getattr(channel, "mention", f"#{channel.name}")
        embed = discord.Embed(
            title="Log Channel Configured",
            description=f"Action event **`{ev_norm}`** will now be logged to {ch_mention}.",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )

        await ctx.send(embed=embed)

    @commands.command(name="logs_config", aliases=["logconfig", "viewlogs", "listlogs"])
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def logs_config(self, ctx: commands.Context):
        """View configured log channels for this server."""
        events = [
            ("ban_unban", "Bans / Unbans", ["ban_unban_log_channel_id", "ban_log_channel_id"]),
            ("automod", "Automod Alerts", ["automod_log_channel_id", "wick_log_channel_id"]),
            ("antinuke", "Anti-Nuke Alerts", ["antinuke_log_channel_id", "security_log_channel_id"]),
            ("message", "Message Edits / Deletes", ["message_log_channel_id"]),
            ("image", "Image Media Log", ["image_log_channel_id"]),
            ("join_leave", "Member Joins / Leaves", ["join_leave_log_channel_id", "member_log_channel_id"]),
            ("role_create", "Role Creation", ["role_create_log_channel_id"]),
            ("role_update", "Role Modification", ["role_update_log_channel_id"]),
            ("role_delete", "Role Deletion", ["role_delete_log_channel_id"]),
            ("role_add_remove", "Member Role Changes", ["role_add_remove_log_channel_id"]),
            ("channel_create", "Channel Creation", ["channel_create_log_channel_id"]),
            ("channel_delete", "Channel Deletion", ["channel_delete_log_channel_id"]),
            ("voice", "Voice Activity", ["voice_log_channel_id", "vc_log_channel_id"]),
        ]



        embed = discord.Embed(
            title=f"Action Log Configuration for {ctx.guild.name}",
            description="Below are the configured action log channels. Use `!setlog <event> <#channel>` to customize any binding, or `!setup_logs` to auto-create all channels.",
            color=discord.Color.purple()
        )

        for ev_code, ev_title, keys in events:
            ch_found = await get_action_log_channel(ctx.guild, ev_code)
            status = ch_found.mention if ch_found else "*Not configured / Not found*"
            embed.add_field(name=f"• `{ev_code}` ({ev_title})", value=status, inline=False)

        await ctx.send(embed=embed)



async def setup(bot: commands.Bot):
    await bot.add_cog(AuditLogger(bot))



