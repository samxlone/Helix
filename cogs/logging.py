import logging
from datetime import datetime, timezone
from typing import Optional
import discord
from discord.ext import commands

from utils.config_service import get_guild_config

logger = logging.getLogger(__name__)


class AuditLogger(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _get_log_channel(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        if not guild:
            return None
        try:
            cfg = await get_guild_config(guild.id)
            ch_id = cfg.get("mod_log_channel") or cfg.get("modlog_channel")
            if ch_id:
                return guild.get_channel(int(ch_id)) or self.bot.get_channel(int(ch_id))
        except Exception as e:
            logger.warning("AuditLogger: Failed to fetch log channel for guild %s: %s", guild.id, e)
        return None

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.author.bot:
            return
        if before.content == after.content:
            return
            
        channel = await self._get_log_channel(before.guild)
        if not channel:
            return
            
        embed = discord.Embed(
            title="📝 Message Edited",
            description=f"Message sent by {before.author.mention} was edited in {before.channel.mention}.",
            color=discord.Color.orange(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_author(name=str(before.author), icon_url=before.author.avatar.url if before.author.avatar else None)
        
        # Max limit for embed field is 1024 characters
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
            
        channel = await self._get_log_channel(message.guild)
        if not channel:
            return
            
        embed = discord.Embed(
            title="🗑️ Message Deleted",
            description=f"Message sent by {message.author.mention} was deleted in {message.channel.mention}.",
            color=discord.Color.red(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_author(name=str(message.author), icon_url=message.author.avatar.url if message.author.avatar else None)
        
        content = message.content[:1000] or "*(No text content)*"
        embed.add_field(name="Content", value=content, inline=False)
        embed.add_field(name="User ID", value=f"`{message.author.id}`", inline=True)
        
        # Log attachment names if any
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
        channel = await self._get_log_channel(member.guild)
        if not channel:
            return
            
        created_at = int(member.created_at.timestamp())
        embed = discord.Embed(
            title="📥 Member Joined",
            description=f"{member.mention} has joined the server.",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
        embed.add_field(name="Account Created", value=f"<t:{created_at}:F> (<t:{created_at}:R>)", inline=False)
        embed.add_field(name="Member ID", value=f"`{member.id}`", inline=True)
        
        # Premium Security Alert: Account less than 7 days old
        age_days = (datetime.now(timezone.utc) - member.created_at).days
        if age_days < 7:
            embed.add_field(name="🚨 Security Alert", value="**New Account Warning:** This account is less than 7 days old!", inline=False)
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
        channel = await self._get_log_channel(member.guild)
        if not channel:
            return
            
        embed = discord.Embed(
            title="📤 Member Left",
            description=f"{member.mention} has left the server.",
            color=discord.Color.light_grey(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
        embed.add_field(name="Member ID", value=f"`{member.id}`", inline=True)
        
        # Display roles they had
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


async def setup(bot: commands.Bot):
    await bot.add_cog(AuditLogger(bot))
