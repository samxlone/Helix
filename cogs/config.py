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

    @commands.group(name="config", invoke_without_command=True)
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
            if guild_id and guild_id.lower() == "global":
                synced = await self.bot.tree.sync()
                await ctx.send(f"✅ Globally synced {len(synced)} application commands across all servers!", ephemeral=True)
                return

            target_guild = None
            if guild_id and guild_id.isdigit():
                target_guild = discord.Object(id=int(guild_id))
            elif ctx.guild:
                target_guild = discord.Object(id=ctx.guild.id)
            else:
                await ctx.send("Guild ID or 'global' must be provided when used in DMs.", ephemeral=True)
                return

            self.bot.tree.copy_global_to(guild=target_guild)
            synced = await self.bot.tree.sync(guild=target_guild)
            await ctx.send(f"✅ Synced {len(synced)} commands to guild id={target_guild.id}", ephemeral=True)
        except Exception as exc:
            logger.exception("Failed to sync commands: %s", exc)
            await ctx.send(f"❌ Failed to sync commands: {exc}", ephemeral=True)

    @commands.hybrid_command(name="trust")
    @commands.guild_only()
    async def trust_user(self, ctx: commands.Context, member: discord.Member):
        """Grant Co-Owner / Trusted Admin status to a member (Owner / Admin only)."""
        if ctx.author.id != ctx.guild.owner_id:
            cfg_owner = app_config.get("owner_id")
            if not cfg_owner or int(cfg_owner) != ctx.author.id:
                if not await self.bot.is_owner(ctx.author):
                    await ctx.send("❌ Only the Server Owner or Bot Owner can grant Co-Owner / Trusted status.", ephemeral=True)
                    return

        if member.id == ctx.author.id:
            await ctx.send("❌ You are already the owner!", ephemeral=True)
            return

        from utils.trust import add_trusted
        success = await add_trusted(ctx.guild.id, member.id, ctx.author.id)

        if success:
            embed = discord.Embed(
                title="👑 Co-Owner / Trusted Admin Added",
                description=f"Granted **Co-Owner / Trusted Admin** permissions to {member.mention}!\n"
                            f"They now have high-level trust & admin privileges in **{ctx.guild.name}**.",
                color=discord.Color.gold()
            )
            embed.set_footer(text=f"Granted by {ctx.author.display_name}")
            await ctx.send(embed=embed)
        else:
            await ctx.send("❌ Failed to add trusted member.", ephemeral=True)

    @commands.hybrid_command(name="untrust")
    @commands.guild_only()
    async def untrust_user(self, ctx: commands.Context, member: discord.Member):
        """Revoke Co-Owner / Trusted Admin status from a member (Owner / Admin only)."""
        if ctx.author.id != ctx.guild.owner_id:
            cfg_owner = app_config.get("owner_id")
            if not cfg_owner or int(cfg_owner) != ctx.author.id:
                if not await self.bot.is_owner(ctx.author):
                    await ctx.send("❌ Only the Server Owner or Bot Owner can revoke Co-Owner status.", ephemeral=True)
                    return

        from utils.trust import remove_trusted
        success = await remove_trusted(ctx.guild.id, member.id)

        if success:
            await ctx.send(f"🔇 Revoked Trusted Co-Owner status from {member.mention}.")
        else:
            await ctx.send("❌ Failed to remove trusted member.", ephemeral=True)

    @commands.hybrid_command(name="trusted")
    @commands.guild_only()
    async def list_trusted(self, ctx: commands.Context):
        """List all Co-Owners & Trusted Admins for this server."""
        from utils.trust import get_trusted_users

        users = await get_trusted_users(ctx.guild.id)
        
        embed = discord.Embed(
            title=f"👑 Trusted Co-Owners — {ctx.guild.name}",
            color=discord.Color.gold()
        )
        owner_str = ctx.guild.owner.mention if ctx.guild.owner else f"<@{ctx.guild.owner_id}>"
        embed.add_field(name="👑 Guild Owner", value=owner_str, inline=False)

        if users:
            trusted_mentions = []
            for u in users:
                m = ctx.guild.get_member(u["user_id"])
                mention = m.mention if m else f"<@{u['user_id']}>"
                trusted_mentions.append(f"• {mention} (Granted by <@{u['granted_by']}>)")
            embed.add_field(name="🛡️ Co-Owners & Trusted Admins", value="\n".join(trusted_mentions), inline=False)
        else:
            embed.add_field(name="🛡️ Co-Owners & Trusted Admins", value="*No additional trusted co-owners set.*", inline=False)

        await ctx.send(embed=embed)

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
