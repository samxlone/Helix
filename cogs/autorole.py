"""Auto Role Cog for assigning roles to new members and bots upon joining."""
import logging
from typing import Optional, List, Dict
import discord
from discord.ext import commands

from utils.db import get_connection
from utils.embed_utils import HELIX_COLOR, HELIX_SUCCESS, HELIX_DANGER, set_owner_footer

logger = logging.getLogger(__name__)


class AutoRoleCog(commands.Cog, name="AutoRoles"):
    """Assign roles automatically to new members and bots on join."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _is_staff_or_admin(self, ctx: commands.Context) -> bool:
        if not ctx.guild:
            return False
        if ctx.author.id == ctx.guild.owner_id:
            return True
        perms = getattr(ctx.author, "guild_permissions", None)
        if perms and (perms.manage_roles or perms.manage_guild or perms.administrator):
            return True
        try:
            return await self.bot.is_owner(ctx.author)
        except Exception:
            return False

    @commands.Cog.listener("on_member_join")
    async def on_member_join(self, member: discord.Member):
        """Automatically grant configured roles when a new member or bot joins."""
        guild = member.guild
        if not guild.me.guild_permissions.manage_roles:
            return

        try:
            async with get_connection() as conn:
                cur = await conn.execute(
                    "SELECT role_id FROM autoroles WHERE guild_id = ? AND is_bot = ?",
                    (guild.id, 1 if member.bot else 0)
                )
                rows = await cur.fetchall()
                await cur.close()

            if not rows:
                return

            roles_to_add = []
            bot_top_role = guild.me.top_role

            for r in rows:
                role = guild.get_role(r["role_id"])
                if role and role < bot_top_role and not role.managed:
                    roles_to_add.append(role)

            if roles_to_add:
                await member.add_roles(*roles_to_add, reason=f"Helix AutoRole on join ({'Bot' if member.bot else 'Member'})")
                logger.info("Assigned %d autoroles to %s in %s", len(roles_to_add), member, guild.name)
        except Exception as e:
            logger.warning("Error assigning autorole in %s for %s: %s", guild.name, member, e)

    @commands.group(name="autorole", aliases=["autoroles"], invoke_without_command=True)
    @commands.guild_only()
    async def autorole_group(self, ctx: commands.Context):
        """Manage auto roles assigned to new members and bots on join."""
        if not await self._is_staff_or_admin(ctx):
            await ctx.send("❌ You need `Manage Roles` or `Administrator` permission to configure Auto Roles.", ephemeral=True)
            return
        await self._show_autoroles(ctx)

    @autorole_group.command(name="add", aliases=["human"])
    @commands.guild_only()
    async def autorole_add(self, ctx: commands.Context, role: discord.Role):
        """Add an auto role for new human members."""
        if not await self._is_staff_or_admin(ctx):
            await ctx.send("❌ You need `Manage Roles` permission.", ephemeral=True)
            return

        if role >= ctx.guild.me.top_role:
            await ctx.send("❌ I cannot assign this role because it is higher than or equal to my highest role.", ephemeral=True)
            return
        if role.managed or role.is_default():
            await ctx.send("❌ Cannot assign managed or @everyone role.", ephemeral=True)
            return

        async with get_connection() as conn:
            await conn.execute(
                "INSERT OR REPLACE INTO autoroles (guild_id, role_id, is_bot) VALUES (?, ?, 0)",
                (ctx.guild.id, role.id)
            )
            await conn.commit()

        embed = discord.Embed(
            title="👥 Auto Role Added",
            description=f"> Successfully added {role.mention} as an auto role for **Human Members** on join.",
            color=HELIX_SUCCESS
        )
        set_owner_footer(embed, self.bot)
        await ctx.send(embed=embed)

    @autorole_group.command(name="bot", aliases=["bots"])
    @commands.guild_only()
    async def autorole_bot(self, ctx: commands.Context, role: discord.Role):
        """Add an auto role for new bots on join."""
        if not await self._is_staff_or_admin(ctx):
            await ctx.send("❌ You need `Manage Roles` permission.", ephemeral=True)
            return

        if role >= ctx.guild.me.top_role:
            await ctx.send("❌ I cannot assign this role because it is higher than or equal to my highest role.", ephemeral=True)
            return
        if role.managed or role.is_default():
            await ctx.send("❌ Cannot assign managed or @everyone role.", ephemeral=True)
            return

        async with get_connection() as conn:
            await conn.execute(
                "INSERT OR REPLACE INTO autoroles (guild_id, role_id, is_bot) VALUES (?, ?, 1)",
                (ctx.guild.id, role.id)
            )
            await conn.commit()

        embed = discord.Embed(
            title="🤖 Bot Auto Role Added",
            description=f"> Successfully added {role.mention} as an auto role for **Bots** on join.",
            color=HELIX_SUCCESS
        )
        set_owner_footer(embed, self.bot)
        await ctx.send(embed=embed)

    @autorole_group.command(name="remove", aliases=["del", "delete"])
    @commands.guild_only()
    async def autorole_remove(self, ctx: commands.Context, role: discord.Role):
        """Remove an auto role from the server."""
        if not await self._is_staff_or_admin(ctx):
            await ctx.send("❌ You need `Manage Roles` permission.", ephemeral=True)
            return

        async with get_connection() as conn:
            await conn.execute(
                "DELETE FROM autoroles WHERE guild_id = ? AND role_id = ?",
                (ctx.guild.id, role.id)
            )
            await conn.commit()

        embed = discord.Embed(
            title="🗑️ Auto Role Removed",
            description=f"> Removed {role.mention} from server auto roles.",
            color=HELIX_COLOR
        )
        set_owner_footer(embed, self.bot)
        await ctx.send(embed=embed)

    @autorole_group.command(name="show", aliases=["list", "view"])
    @commands.guild_only()
    async def autorole_show_cmd(self, ctx: commands.Context):
        """Show all currently configured auto roles."""
        await self._show_autoroles(ctx)

    async def _show_autoroles(self, ctx: commands.Context):
        async with get_connection() as conn:
            cur = await conn.execute(
                "SELECT role_id, is_bot FROM autoroles WHERE guild_id = ?",
                (ctx.guild.id,)
            )
            rows = await cur.fetchall()
            await cur.close()

        human_roles = []
        bot_roles = []

        for r in rows:
            role = ctx.guild.get_role(r["role_id"])
            role_str = role.mention if role else f"`ID: {r['role_id']}`"
            if r["is_bot"] == 1:
                bot_roles.append(role_str)
            else:
                human_roles.append(role_str)

        embed = discord.Embed(
            title=f"👥 Auto Roles — {ctx.guild.name}",
            description="Roles automatically assigned to new users when joining this server.",
            color=HELIX_COLOR
        )
        
        embed.add_field(
            name="👤 Human Member Roles",
            value="\n".join(f"> • {r}" for r in human_roles) if human_roles else "> *No human autoroles configured.*",
            inline=False
        )
        embed.add_field(
            name="🤖 Bot Roles",
            value="\n".join(f"> • {r}" for r in bot_roles) if bot_roles else "> *No bot autoroles configured.*",
            inline=False
        )
        embed.add_field(
            name="💡 Quick Configuration",
            value="`!autorole add @role` • `!autorole bot @role` • `!autorole remove @role`",
            inline=False
        )
        set_owner_footer(embed, self.bot)
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoRoleCog(bot))
