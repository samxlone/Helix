from typing import Optional
import logging
from discord.ext import commands
import discord
from discord import app_commands
from utils.leveling import award_xp
from utils.config_service import get_guild_config, set_guild_config

logger = logging.getLogger(__name__)


class LevelingCog(commands.Cog):
    """Handles awarding XP and level-up role rewards."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

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
            ignored = cfg.get("ignored_xp_users") or []
            if message.author.id in ignored:
                return
                
            leveled, old, new = await award_xp(message.author.id, 10)
            if leveled:
                # announce
                try:
                    await message.channel.send(f"Congrats {message.author.mention}, you leveled up to {new}!")
                except Exception:
                    pass
                # check for role reward mapping in guild config
                try:
                    cfg = await get_guild_config(message.guild.id)
                    rewards = cfg.get("level_rewards") or {}
                    # allow both int and str keys
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

    @commands.hybrid_command(name="ignorexp")
    @commands.guild_only()
    async def ignorexp(self, ctx: commands.Context, member: discord.Member):
        """Toggle ignoring XP accumulation for a member (Server/Bot Owner only)"""
        is_allowed = getattr(ctx.guild, "owner_id", None) == ctx.author.id
        if not is_allowed:
            is_owner = await self.bot.is_owner(ctx.author)
            if is_owner:
                is_allowed = True
                
        if not is_allowed:
            await ctx.send("Only the server owner or bot owner can configure ignored XP users.", ephemeral=True)
            return

            
        try:
            cfg = await get_guild_config(ctx.guild.id)
            ignored = cfg.get("ignored_xp_users") or []
            
            if member.id in ignored:
                ignored.remove(member.id)
                await set_guild_config(ctx.guild.id, {"ignored_xp_users": ignored})
                await ctx.send(f"Started counting XP for {member.mention} again! ✅")
            else:
                ignored.append(member.id)
                await set_guild_config(ctx.guild.id, {"ignored_xp_users": ignored})
                await ctx.send(f"Stopped counting XP for {member.mention}! ❌")
        except Exception as e:
            logger.exception("Failed to toggle ignored XP status: %s", e)
            await ctx.send("Failed to toggle ignored XP status.", ephemeral=True)



async def setup(bot: commands.Bot):
    await bot.add_cog(LevelingCog(bot))
