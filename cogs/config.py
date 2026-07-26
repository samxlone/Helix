import json
import logging
import discord
from discord import app_commands
from config import config as app_config
from discord.ext import commands
from typing import Any, Optional

from utils.config_service import get_guild_config, set_guild_config, reset_guild_config

logger = logging.getLogger(__name__)


class ConfigCog(commands.Cog):
    """Simple guild config management cog.

    Commands:
    /config_view - view merged config (ephemeral)
    /config_set <key> <value> - set a top-level key (value parsed as JSON when possible)
    /config_reset - reset guild config to defaults
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_group(name="config", invoke_without_command=True)
    @commands.guild_only()
    async def config_group(self, ctx: commands.Context):
        """Guild configuration management"""
        await ctx.send_help(ctx.command)

    @config_group.command(name="view")
    @commands.guild_only()
    async def config_view(self, ctx: commands.Context):
        """View merged config for the server"""
        cfg = await get_guild_config(ctx.guild.id)
        pretty = json.dumps(cfg, indent=2, ensure_ascii=False)
        await ctx.send(f"Guild config:\n```json\n{pretty}\n```", ephemeral=True)

    @config_group.command(name="set")
    @commands.guild_only()
    async def config_set(self, ctx: commands.Context, key: str, value: str):
        """Set a configuration key to a value"""
        # permission check: require guild admin
        if not ctx.author.guild_permissions.administrator:
            await ctx.send("You must be a server administrator to change config.", ephemeral=True)
            return

        try:
            parsed: Any
            try:
                parsed = json.loads(value)
            except Exception:
                parsed = value

            await set_guild_config(ctx.guild.id, {key: parsed})
            await ctx.send(f"Set `{key}` = `{parsed}`", ephemeral=True)
        except Exception as exc:
            logger.exception("Failed to set config: %s", exc)
            await ctx.send("Failed to set config.", ephemeral=True)

    @config_group.command(name="reset")
    @commands.guild_only()
    async def config_reset(self, ctx: commands.Context):
        """Reset guild config to defaults"""
        if not ctx.author.guild_permissions.administrator:
            await ctx.send("You must be a server administrator to reset config.", ephemeral=True)
            return

        await reset_guild_config(ctx.guild.id)
        await ctx.send("Guild config reset to defaults.", ephemeral=True)

    @commands.command(name="sync")
    async def sync(self, ctx: commands.Context, guild_id: Optional[str] = None):


        """Sync application commands to this guild (Owner only)."""
        cfg_owner = app_config.get("owner_id")
        is_owner = False
        try:
            if cfg_owner and int(cfg_owner) == ctx.author.id:
                is_owner = True
        except Exception:
            is_owner = False

        try:
            if not is_owner:
                is_owner = await self.bot.is_owner(ctx.author)
        except Exception:
            is_owner = is_owner

        if not is_owner:
            await ctx.send("You are not authorized to run this command.", ephemeral=True)
            return

        await ctx.defer(ephemeral=True)
        try:
            target_guild = None
            if guild_id:
                target_guild = discord.Object(id=int(guild_id))
            elif ctx.guild:
                target_guild = discord.Object(id=ctx.guild.id)
            else:
                await ctx.send("Guild ID must be provided when used in DMs.", ephemeral=True)
                return

            self.bot.tree.copy_global_to(guild=target_guild)
            synced = await self.bot.tree.sync(guild=target_guild)
            await ctx.send(f"Synced {len(synced)} commands to guild id={target_guild.id}", ephemeral=True)
        except Exception as exc:
            logger.exception("Failed to sync commands: %s", exc)
            await ctx.send("Failed to sync commands. Check logs.", ephemeral=True)

    @commands.hybrid_command(name="setprefix")
    @commands.guild_only()
    async def setprefix(self, ctx: commands.Context, new_prefix: str):
        """Set a custom command prefix for this server (Admins/Owners only)"""
        is_admin = ctx.author.guild_permissions.administrator or ctx.guild.owner_id == ctx.author.id
        if not is_admin:
            is_owner = await self.bot.is_owner(ctx.author)
            if is_owner:
                is_admin = True

        if not is_admin:
            await ctx.send("You must be a server administrator or the server owner to change the prefix.", ephemeral=True)
            return

        if len(new_prefix) > 5:
            await ctx.send("Prefix cannot be longer than 5 characters.", ephemeral=True)
            return

        try:
            await set_guild_config(ctx.guild.id, {"prefix": new_prefix})
            await ctx.send(f"The command prefix for this server has been set to: `{new_prefix}`")
        except Exception as e:
            logger.exception("Failed to set prefix: %s", e)
            await ctx.send("Failed to save prefix configuration.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(ConfigCog(bot))
