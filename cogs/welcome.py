"""Welcome and Goodbye Cog for welcoming new members with luxury cards or embeds."""
import io
import logging
from typing import Optional
import discord
from discord.ext import commands

from utils.db import get_connection
from utils.embed_utils import HELIX_COLOR, HELIX_SUCCESS, HELIX_DARK, set_owner_footer
from services.image_card import generate_welcome_card

logger = logging.getLogger(__name__)


class WelcomeCog(commands.Cog, name="Welcome"):
    """Server Welcome & Goodbye System with Luxury Canvas Cards and Embeds."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _is_staff_or_admin(self, ctx: commands.Context) -> bool:
        if not ctx.guild:
            return False
        if ctx.author.id == ctx.guild.owner_id:
            return True
        perms = getattr(ctx.author, "guild_permissions", None)
        if perms and (perms.manage_guild or perms.administrator):
            return True
        try:
            return await self.bot.is_owner(ctx.author)
        except Exception:
            return False

    def _format_msg(self, template: str, member: discord.Member) -> str:
        count = member.guild.member_count if member.guild else 0
        return (
            template.replace("{user}", member.mention)
            .replace("{user.name}", member.name)
            .replace("{user.tag}", str(member))
            .replace("{server}", member.guild.name if member.guild else "Server")
            .replace("{membercount}", f"{count:,}")
        )

    async def _get_config(self, guild_id: int):
        async with get_connection() as conn:
            cur = await conn.execute(
                "SELECT * FROM welcome_config WHERE guild_id = ?",
                (guild_id,)
            )
            cfg = await cur.fetchone()
            await cur.close()
            return cfg

    @commands.Cog.listener("on_member_join")
    async def on_member_join(self, member: discord.Member):
        guild = member.guild
        cfg = await self._get_config(guild.id)
        if not cfg or cfg["is_enabled"] == 0:
            return

        ch_id = cfg["welcome_channel_id"]
        if ch_id:
            ch = guild.get_channel(ch_id)
            if ch and isinstance(ch, discord.TextChannel):
                welcome_type = cfg["welcome_type"] or "card"
                default_msg = "Welcome to **{server}**, {user}! You are member **#{membercount}** 🎉"
                raw_msg = cfg["welcome_msg"] or default_msg
                formatted_text = self._format_msg(raw_msg, member)

                try:
                    if welcome_type == "card":
                        av_url = member.display_avatar.url if member.display_avatar else None
                        card_buf = generate_welcome_card(
                            display_name=member.display_name,
                            username=member.name,
                            avatar_url=av_url,
                            server_name=guild.name,
                            member_count=guild.member_count
                        )
                        file = discord.File(fp=card_buf, filename="welcome.png")
                        await ch.send(content=formatted_text, file=file)
                    elif welcome_type == "embed":
                        embed = discord.Embed(
                            title=f"👋 Welcome to {guild.name}!",
                            description=(
                                f"### Welcome {member.mention}!\n\n"
                                f"> • **Username:** `{member.name}`\n"
                                f"> • **Member Count:** `#{guild.member_count:,}`\n"
                                f"> • **Account Created:** <t:{int(member.created_at.timestamp())}:R>\n\n"
                                f"{formatted_text}"
                            ),
                            color=HELIX_COLOR
                        )
                        if member.display_avatar:
                            embed.set_thumbnail(url=member.display_avatar.url)
                        set_owner_footer(embed, self.bot)
                        await ch.send(embed=embed)
                    else:
                        await ch.send(formatted_text)
                except Exception as e:
                    logger.warning("Error sending welcome message in %s: %s", guild.name, e)

        # DM Welcome if enabled
        if cfg.get("dm_enabled") == 1:
            try:
                dm_embed = discord.Embed(
                    title=f"🎉 Welcome to {guild.name}!",
                    description=(
                        f"Hey {member.name}, welcome to **{guild.name}**!\n\n"
                        f"We are excited to have you with us. Enjoy your stay!"
                    ),
                    color=HELIX_COLOR
                )
                if guild.icon:
                    dm_embed.set_thumbnail(url=guild.icon.url)
                set_owner_footer(dm_embed, self.bot)
                await member.send(embed=dm_embed)
            except Exception:
                pass

    @commands.Cog.listener("on_member_remove")
    async def on_member_remove(self, member: discord.Member):
        guild = member.guild
        cfg = await self._get_config(guild.id)
        if not cfg or cfg["is_enabled"] == 0:
            return

        goodbye_ch_id = cfg["goodbye_channel_id"]
        if goodbye_ch_id:
            ch = guild.get_channel(goodbye_ch_id)
            if ch and isinstance(ch, discord.TextChannel):
                default_bye = "**{user.name}** has left the server. We now have **{membercount}** members."
                raw_bye = cfg["goodbye_msg"] or default_bye
                formatted_bye = self._format_msg(raw_bye, member)
                try:
                    embed = discord.Embed(
                        title="👋 Member Left",
                        description=f"> {formatted_bye}",
                        color=discord.Color.from_rgb(100, 116, 139)
                    )
                    if member.display_avatar:
                        embed.set_thumbnail(url=member.display_avatar.url)
                    set_owner_footer(embed, self.bot)
                    await ch.send(embed=embed)
                except Exception as e:
                    logger.warning("Error sending goodbye message in %s: %s", guild.name, e)

    @commands.command(name="setwelcome")
    @commands.guild_only()
    async def setwelcome(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        """Set or clear the welcome announcements channel."""
        if not await self._is_staff_or_admin(ctx):
            await ctx.send("❌ You need `Manage Server` permission.", ephemeral=True)
            return

        target_ch = channel or ctx.channel
        async with get_connection() as conn:
            await conn.execute("""
                INSERT INTO welcome_config (guild_id, welcome_channel_id, is_enabled)
                VALUES (?, ?, 1)
                ON CONFLICT(guild_id) DO UPDATE SET welcome_channel_id = ?, is_enabled = 1
            """, (ctx.guild.id, target_ch.id, target_ch.id))
            await conn.commit()

        embed = discord.Embed(
            title="👋 Welcome Channel Configured",
            description=f"> New member arrivals will be announced in {target_ch.mention}.",
            color=HELIX_SUCCESS
        )
        embed.add_field(
            name="💡 Customization Commands",
            value=(
                "`!welcomemsg <text>` — Set custom message\n"
                "`!welcometype <card|embed|text>` — Choose visual style\n"
                "`!testwelcome` — Preview current welcome card"
            ),
            inline=False
        )
        set_owner_footer(embed, self.bot)
        await ctx.send(embed=embed)

    @commands.command(name="setgoodbye")
    @commands.guild_only()
    async def setgoodbye(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        """Set or clear the goodbye / leave announcements channel."""
        if not await self._is_staff_or_admin(ctx):
            await ctx.send("❌ You need `Manage Server` permission.", ephemeral=True)
            return

        target_ch = channel or ctx.channel
        async with get_connection() as conn:
            await conn.execute("""
                INSERT INTO welcome_config (guild_id, goodbye_channel_id, is_enabled)
                VALUES (?, ?, 1)
                ON CONFLICT(guild_id) DO UPDATE SET goodbye_channel_id = ?, is_enabled = 1
            """, (ctx.guild.id, target_ch.id, target_ch.id))
            await conn.commit()

        embed = discord.Embed(
            title="👋 Goodbye Channel Configured",
            description=f"> Member departures will be announced in {target_ch.mention}.",
            color=HELIX_SUCCESS
        )
        set_owner_footer(embed, self.bot)
        await ctx.send(embed=embed)

    @commands.command(name="welcomemsg")
    @commands.guild_only()
    async def welcomemsg(self, ctx: commands.Context, *, message: str):
        """Set custom welcome message text. Placeholders: {user}, {user.name}, {server}, {membercount}."""
        if not await self._is_staff_or_admin(ctx):
            await ctx.send("❌ You need `Manage Server` permission.", ephemeral=True)
            return

        async with get_connection() as conn:
            await conn.execute("""
                INSERT INTO welcome_config (guild_id, welcome_msg, is_enabled)
                VALUES (?, ?, 1)
                ON CONFLICT(guild_id) DO UPDATE SET welcome_msg = ?
            """, (ctx.guild.id, message, message))
            await conn.commit()

        embed = discord.Embed(
            title="✏️ Welcome Message Updated",
            description=f"### Live Preview:\n> {self._format_msg(message, ctx.author)}",
            color=HELIX_SUCCESS
        )
        set_owner_footer(embed, self.bot)
        await ctx.send(embed=embed)

    @commands.command(name="welcometype")
    @commands.guild_only()
    async def welcometype(self, ctx: commands.Context, style: str):
        """Set welcome format: card (image), embed (luxury card), or text."""
        if not await self._is_staff_or_admin(ctx):
            await ctx.send("❌ You need `Manage Server` permission.", ephemeral=True)
            return

        style_clean = style.lower().strip()
        if style_clean not in ["card", "embed", "text"]:
            await ctx.send("❌ Please choose a valid style: `card`, `embed`, or `text`.", ephemeral=True)
            return

        async with get_connection() as conn:
            await conn.execute("""
                INSERT INTO welcome_config (guild_id, welcome_type, is_enabled)
                VALUES (?, ?, 1)
                ON CONFLICT(guild_id) DO UPDATE SET welcome_type = ?
            """, (ctx.guild.id, style_clean, style_clean))
            await conn.commit()

        embed = discord.Embed(
            title="🎨 Welcome Style Configured",
            description=f"> Welcome announcements will now render as **`{style_clean.upper()}`**.",
            color=HELIX_SUCCESS
        )
        set_owner_footer(embed, self.bot)
        await ctx.send(embed=embed)

    @commands.command(name="testwelcome")
    @commands.guild_only()
    async def testwelcome(self, ctx: commands.Context):
        """Preview the server's welcome card or embed in the current channel."""
        if not await self._is_staff_or_admin(ctx):
            await ctx.send("❌ You need `Manage Server` permission.", ephemeral=True)
            return

        cfg = await self._get_config(ctx.guild.id)
        style = cfg["welcome_type"] if cfg and cfg["welcome_type"] else "card"
        default_msg = "Welcome to **{server}**, {user}! You are member **#{membercount}** 🎉"
        raw_msg = (cfg["welcome_msg"] if cfg and cfg["welcome_msg"] else default_msg)
        formatted_text = self._format_msg(raw_msg, ctx.author)

        if style == "card":
            av_url = ctx.author.display_avatar.url if ctx.author.display_avatar else None
            card_buf = generate_welcome_card(
                display_name=ctx.author.display_name,
                username=ctx.author.name,
                avatar_url=av_url,
                server_name=ctx.guild.name,
                member_count=ctx.guild.member_count
            )
            file = discord.File(fp=card_buf, filename="welcome_preview.png")
            await ctx.send(content=f"🧪 **[TEST PREVIEW]**\n{formatted_text}", file=file)
        elif style == "embed":
            embed = discord.Embed(
                title=f"👋 Welcome to {ctx.guild.name}!",
                description=(
                    f"### Welcome {ctx.author.mention}!\n\n"
                    f"> • **Username:** `{ctx.author.name}`\n"
                    f"> • **Member Count:** `#{ctx.guild.member_count:,}`\n"
                    f"> • **Account Created:** <t:{int(ctx.author.created_at.timestamp())}:R>\n\n"
                    f"{formatted_text}"
                ),
                color=HELIX_COLOR
            )
            if ctx.author.display_avatar:
                embed.set_thumbnail(url=ctx.author.display_avatar.url)
            set_owner_footer(embed, self.bot, extra_text="Welcome Preview")
            await ctx.send(content="🧪 **[TEST PREVIEW]**", embed=embed)
        else:
            await ctx.send(f"🧪 **[TEST PREVIEW]**\n{formatted_text}")


async def setup(bot: commands.Bot):
    await bot.add_cog(WelcomeCog(bot))
