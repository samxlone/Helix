import io
import logging
from typing import Optional
import ast
import operator
import re
import urllib.parse
import aiohttp


from datetime import datetime, timezone, timedelta
import discord
from discord import app_commands, Interaction
from discord.ext import commands, tasks

from utils.economy import get_balance
from utils.leveling import get_level_info, xp_needed_for_next
from utils.db import get_connection
from utils.config_service import get_guild_config

logger = logging.getLogger(__name__)


class StealStickerView(discord.ui.View):
    def __init__(self, ctx, sticker, custom_name: Optional[str] = None):
        super().__init__(timeout=120)
        self.ctx = ctx
        self.sticker = sticker
        self.custom_name = custom_name

    @discord.ui.button(label="Emoji", style=discord.ButtonStyle.success)
    async def btn_emoji(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("❌ Only the command invoker can use these buttons.", ephemeral=True)
            return

        await interaction.response.defer()
        guild = self.ctx.guild
        sticker = self.sticker

        name = self.custom_name or sticker.name
        name = re.sub(r"[^a-zA-Z0-9_]", "", name).strip()
        if len(name) < 2:
            name = f"emoji_{name}"
        name = name[:32]

        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
        sticker_url = getattr(sticker, "url", None) or f"https://cdn.discordapp.com/stickers/{sticker.id}.png"
        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(sticker_url) as resp:
                    if resp.status != 200:
                        await interaction.followup.send("❌ Failed to download sticker asset.", ephemeral=True)
                        return
                    img_bytes = await resp.read()


            new_emoji = await guild.create_custom_emoji(
                name=name,
                image=img_bytes,
                reason=f"Stolen as Emoji by {self.ctx.author}"
            )
            await interaction.edit_original_response(
                content=f"✅ Successfully stole sticker **{sticker.name}** as Custom Emoji {new_emoji} (`:{new_emoji.name}:`)!",
                embed=None,
                view=None
            )
        except discord.HTTPException as e:
            logger.exception("HTTP error stealing sticker as emoji: %s", e)
            await interaction.followup.send(f"❌ Failed to create emoji: {e.text or e}", ephemeral=True)
        except Exception as e:
            logger.exception("Failed to steal sticker as emoji: %s", e)
            await interaction.followup.send(f"❌ Error creating emoji: {e}", ephemeral=True)

    @discord.ui.button(label="Sticker", style=discord.ButtonStyle.primary)
    async def btn_sticker(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("❌ Only the command invoker can use these buttons.", ephemeral=True)
            return

        await interaction.response.defer()
        guild = self.ctx.guild
        sticker = self.sticker

        name = self.custom_name or sticker.name
        name = re.sub(r"[^a-zA-Z0-9_ -]", "", name).strip()
        if len(name) < 2:
            name = f"{name}_sticker"
        name = name[:30]

        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
        sticker_url = getattr(sticker, "url", None) or f"https://cdn.discordapp.com/stickers/{sticker.id}.png"
        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(sticker_url) as resp:
                    if resp.status != 200:
                        await interaction.followup.send("❌ Failed to download sticker asset.", ephemeral=True)
                        return
                    sticker_bytes = await resp.read()


            fmt = getattr(sticker, "format", None)
            fmt_name = str(fmt).lower() if fmt else ""
            filename = f"{name}.png"
            if "lottie" in fmt_name or sticker_url.endswith(".json"):
                filename = f"{name}.json"

            sticker_file = discord.File(fp=io.BytesIO(sticker_bytes), filename=filename)
            emoji_tag = getattr(sticker, "emoji", None) or "⭐"

            new_sticker = await guild.create_sticker(
                name=name,
                description=f"Stolen by {self.ctx.author.display_name}",
                emoji=emoji_tag,
                file=sticker_file,
                reason=f"Stolen by {self.ctx.author}"
            )
            await interaction.edit_original_response(
                content=f"✅ Successfully stole sticker **{new_sticker.name}** as Guild Sticker!",
                embed=None,
                view=None
            )
        except discord.HTTPException as e:
            logger.exception("HTTP error stealing sticker as sticker: %s", e)
            await interaction.followup.send(f"❌ Failed to create sticker: {e.text or e}", ephemeral=True)
        except Exception as e:
            logger.exception("Failed to steal sticker as sticker: %s", e)
            await interaction.followup.send(f"❌ Error creating sticker: {e}", ephemeral=True)


class Utility(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.check_reminders.start()

    def cog_unload(self):
        self.check_reminders.cancel()

    @commands.hybrid_command(name="serverinfo", aliases=["sinfo", "si"])
    @commands.guild_only()
    async def serverinfo(self, ctx: commands.Context):
        """Displays rich information and statistics about the server."""
        guild: discord.Guild = ctx.guild

        total_members = guild.member_count or len(guild.members)
        bot_members = sum(1 for m in guild.members if m.bot)
        human_members = max(0, total_members - bot_members)

        categories = len(guild.categories)
        text_channels = len(guild.text_channels)
        voice_channels = len(guild.voice_channels)
        total_channels = len(guild.channels)

        created_ts = int(guild.created_at.timestamp())
        owner_mention = guild.owner.mention if guild.owner else f"<@{guild.owner_id}>"

        embed = discord.Embed(
            title=f"Server Information — {guild.name}",
            color=discord.Color.blurple()
        )
        if guild.description:
            embed.description = f"*{guild.description}*"

        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        if guild.banner:
            embed.set_image(url=guild.banner.url)

        # 1. Overview Field
        overview = (
            f"• **Server Name:** {guild.name}\n"
            f"• **Server ID:** `{guild.id}`\n"
            f"• **Owner:** {owner_mention}\n"
            f"• **Created At:** <t:{created_ts}:F> (<t:{created_ts}:R>)"
        )
        embed.add_field(name="📋 Overview", value=overview, inline=False)

        # 2. Member & Channel Stats
        members_str = (
            f"• **Total Members:** **{total_members:,}**\n"
            f"• **Humans:** **{human_members:,}** | **Bots:** **{bot_members:,}**"
        )
        embed.add_field(name="👥 Members", value=members_str, inline=True)

        channels_str = (
            f"• **Text Channels:** **{text_channels}**\n"
            f"• **Voice Channels:** **{voice_channels}**\n"
            f"• **Categories:** **{categories}**\n"
            f"• **Total Channels:** **{total_channels}**"
        )
        embed.add_field(name="💬 Channels", value=channels_str, inline=True)

        # 3. Boosts & Security
        booster_role = getattr(guild, "premium_subscriber_role", None)
        booster_role_str = booster_role.mention if booster_role else "None"
        boost_str = (
            f"• **Boost Level:** **Level {guild.premium_tier}**\n"
            f"• **Total Boosts:** **{guild.premium_subscription_count}**\n"
            f"• **Booster Role:** {booster_role_str}"
        )
        embed.add_field(name="🚀 Server Boosts", value=boost_str, inline=True)

        verif_level = str(guild.verification_level).capitalize()
        filter_level = str(guild.explicit_content_filter).replace("_", " ").capitalize()
        security_str = (
            f"• **Verification:** **{verif_level}**\n"
            f"• **Content Filter:** **{filter_level}**"
        )
        embed.add_field(name="🛡️ Security", value=security_str, inline=True)

        # 4. Roles Summary
        roles = [r for r in guild.roles if r != guild.default_role]
        if len(roles) <= 12:
            roles_display = ", ".join(r.mention for r in roles) if roles else "None"
        else:
            top_few = ", ".join(r.mention for r in roles[-8:])
            roles_display = f"{top_few}\n*...and {len(roles) - 8} more roles*"

        embed.add_field(name=f"🎭 Server Roles [{len(guild.roles)}]", value=roles_display, inline=False)

        embed.set_footer(text=f"Requested by {ctx.author.display_name}")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="userinfo", aliases=["user", "whois", "ui"])
    @commands.guild_only()
    async def userinfo(self, ctx: commands.Context, member: Optional[discord.Member] = None):


        """Displays comprehensive user profile information, roles, permissions, and timestamps."""
        target: discord.Member = member or ctx.author

        color = target.color if target.color and target.color.value != 0 else discord.Color.blurple()
        embed = discord.Embed(
            title=f"👤 User Information — {target.display_name}",
            color=color
        )
        embed.set_thumbnail(url=target.display_avatar.url)

        # 1. General Info
        user_type = "Bot 🤖" if target.bot else "User 👤"
        status_map = {
            discord.Status.online: "🟢 Online",
            discord.Status.idle: "🟡 Idle",
            discord.Status.dnd: "🔴 Do Not Disturb",
            discord.Status.offline: "⚫ Offline"
        }
        status_str = status_map.get(getattr(target, "status", None), "⚫ Offline")

        general_desc = (
            f"• **Username:** {target.name}\n"
            f"• **User ID:** `{target.id}`\n"
            f"• **Mention:** {target.mention}\n"
            f"• **Account Type:** {user_type}\n"
            f"• **Status:** {status_str}"
        )
        embed.add_field(name="📋 General Information", value=general_desc, inline=False)

        # 2. Timestamps
        created_ts = int(target.created_at.timestamp())
        joined_ts = int(target.joined_at.timestamp()) if target.joined_at else 0

        embed.add_field(name="📆 Account Created", value=f"<t:{created_ts}:F>\n(<t:{created_ts}:R>)", inline=True)
        if joined_ts:
            embed.add_field(name="📥 Server Joined", value=f"<t:{joined_ts}:F>\n(<t:{joined_ts}:R>)", inline=True)

        # 3. Server Boosting Status
        if getattr(target, "premium_since", None):
            boost_ts = int(target.premium_since.timestamp())
            embed.add_field(name="🚀 Server Booster", value=f"<t:{boost_ts}:F>\n(<t:{boost_ts}:R>)", inline=True)
        else:
            embed.add_field(name="🚀 Server Booster", value="Not boosting this server", inline=True)

        # 4. Top Role & Roles List (excluding @everyone)
        roles = [r for r in target.roles if r != ctx.guild.default_role]
        top_role = target.top_role if target.top_role != ctx.guild.default_role else None
        top_role_str = top_role.mention if top_role else "None"
        embed.add_field(name="👑 Highest Role", value=top_role_str, inline=False)

        roles_mentions = [r.mention for r in roles]
        roles_str = ", ".join(roles_mentions[:15]) if roles_mentions else "None"
        if len(roles_mentions) > 15:
            roles_str += f" ...and {len(roles_mentions) - 15} more roles"
        embed.add_field(name=f"🛡️ Roles ({len(roles)})", value=roles_str, inline=False)

        # 5. Key Permissions
        perms = []
        gp = target.guild_permissions
        if gp.administrator:
            perms.append("Administrator")
        if gp.manage_guild:
            perms.append("Manage Server")
        if gp.manage_roles:
            perms.append("Manage Roles")
        if gp.manage_channels:
            perms.append("Manage Channels")
        if gp.kick_members:
            perms.append("Kick Members")
        if gp.ban_members:
            perms.append("Ban Members")
        if gp.moderate_members:
            perms.append("Timeout Members")
        if gp.manage_messages:
            perms.append("Manage Messages")

        perms_str = ", ".join(f"`{p}`" for p in perms) if perms else "`Default Member Permissions`"
        embed.add_field(name="⚡ Key Permissions", value=perms_str, inline=False)

        owner = self.bot.owner_user if hasattr(self.bot, "owner_user") else None
        if owner:
            embed.set_footer(text=f"Requested by {ctx.author.display_name} • Bot owned by {owner.name}")
        else:
            embed.set_footer(text=f"Requested by {ctx.author.display_name}")

        await ctx.send(embed=embed)


    @commands.hybrid_command(name="avatar", aliases=["av", "pfp"])
    async def avatar(self, ctx: commands.Context, user: Optional[discord.User] = None):
        """Show a user's avatar. Shortcuts: av, pfp."""
        target = user or ctx.author
        avatar = target.display_avatar.with_size(4096)
        embed = discord.Embed(
            title=f"🖼️ {target.display_name}'s Avatar",
            description=f"[Open original image]({avatar.url})",
            color=getattr(target, "color", None) or discord.Color.dark_teal(),
        )
        embed.set_image(url=avatar.url)
        embed.set_footer(text=f"Requested by {ctx.author.display_name}")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="banner", aliases=["bnr", "ubanner"])
    async def banner(self, ctx: commands.Context, user: Optional[discord.User] = None):
        """Show a user's profile banner. Shortcuts: bnr, ubanner."""
        target = user or ctx.author
        try:
            # fetch_user returns the profile banner, which may not exist on cached Member objects.
            profile = await self.bot.fetch_user(target.id)
        except discord.HTTPException:
            await ctx.send("I couldn't retrieve that user's profile.", ephemeral=True)
            return

        if not profile.banner:
            await ctx.send(f"{target.mention} does not have a profile banner set.", ephemeral=True)
            return

        banner = profile.banner.with_size(4096)
        embed = discord.Embed(
            title=f"🖼️ {profile.display_name}'s Banner",
            description=f"[Open original image]({banner.url})",
            color=profile.accent_color or discord.Color.dark_teal(),
        )
        embed.set_image(url=banner.url)
        embed.set_footer(text=f"Requested by {ctx.author.display_name}")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="ping")
    async def ping(self, ctx: commands.Context):
        """Check the bot's response time."""
        latency = round(self.bot.latency * 1000)
        await ctx.send(f"Pong! 🏓 ({latency}ms)")

    @commands.hybrid_command(name="roleinfo", aliases=["rinfo", "ri"])
    @commands.guild_only()
    async def roleinfo(self, ctx: commands.Context, role: discord.Role):
        """Displays detailed information about a server role."""
        created_at = int(role.created_at.timestamp())
        
        perms = []
        if role.permissions.administrator:
            perms.append("Administrator")
        if role.permissions.manage_guild:
            perms.append("Manage Server")
        if role.permissions.manage_channels:
            perms.append("Manage Channels")
        if role.permissions.manage_roles:
            perms.append("Manage Roles")
        if role.permissions.kick_members:
            perms.append("Kick Members")
        if role.permissions.ban_members:
            perms.append("Ban Members")
        if role.permissions.manage_messages:
            perms.append("Manage Messages")
        if role.permissions.mention_everyone:
            perms.append("Mention Everyone")
        if role.permissions.mute_members:
            perms.append("Mute Members")
        if role.permissions.deafen_members:
            perms.append("Deafen Members")
        if role.permissions.move_members:
            perms.append("Move Members")
            
        perms_str = ", ".join(perms) if perms else "None"
        
        embed = discord.Embed(
            title=f"🛡️ Role Info: {role.name}",
            description=f"**ID:** `{role.id}`\n**Mention:** {role.mention}",
            color=role.color if role.color != discord.Color.default() else discord.Color.blurple()
        )
        embed.add_field(name="📅 Created", value=f"<t:{created_at}:F>\n(<t:{created_at}:R>)", inline=True)
        embed.add_field(name="👥 Members", value=f"**{len(role.members)}** members", inline=True)
        embed.add_field(name="📊 Position", value=f"**{role.position}** (from bottom)", inline=True)
        
        rgb = role.color.to_rgb()
        embed.add_field(name="🎨 Color", value=f"Hex: `{str(role.color)}`\nRGB: `{rgb}`", inline=True)
        embed.add_field(name="👁️ Settings", value=f"Hoisted: **{role.hoist}**\nMentionable: **{role.mentionable}**", inline=True)
        embed.add_field(name="🛡️ Key Permissions", value=perms_str, inline=False)
        
        embed.set_footer(text=f"Requested by {ctx.author.display_name}")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="membercount", aliases=["mc"])
    @commands.guild_only()
    async def membercount(self, ctx: commands.Context):
        """Displays total member count, broken down by humans and bots."""
        guild = ctx.guild
        total = guild.member_count
        bots = sum(1 for m in guild.members if m.bot)
        humans = total - bots
        
        embed = discord.Embed(
            title=f"👥 {guild.name} Member Count",
            color=discord.Color.blurple()
        )
        embed.add_field(name="👥 Total Members", value=f"**{total}**", inline=False)
        embed.add_field(name="👤 Humans", value=f"**{humans}**", inline=True)
        embed.add_field(name="🤖 Bots", value=f"**{bots}**", inline=True)
        
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        embed.set_footer(text=f"Requested by {ctx.author.display_name}")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="uptime")
    async def uptime(self, ctx: commands.Context):
        """Displays the bot's current uptime."""
        start_time = getattr(self.bot, "start_time", None)
        if not start_time:
            await ctx.send("Could not determine bot start time.")
            return
            
        now = discord.utils.utcnow()
        delta = now - start_time
        
        days = delta.days
        hours, remainder = divmod(delta.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        time_str = []
        if days > 0:
            time_str.append(f"{days}d")
        if hours > 0:
            time_str.append(f"{hours}h")
        if minutes > 0:
            time_str.append(f"{minutes}m")
        time_str.append(f"{seconds}s")
        
        duration_str = ", ".join(time_str)
        start_ts = int(start_time.timestamp())
        
        embed = discord.Embed(
            title="⏱️ Bot Uptime",
            description=f"Running for **{duration_str}**\n\n**Started at:** <t:{start_ts}:F> (<t:{start_ts}:R>)",
            color=discord.Color.teal()
        )
        embed.set_footer(text=f"Requested by {ctx.author.display_name}")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="weather")
    async def weather(self, ctx: commands.Context, *, location: str):
        """Fetches weather conditions for a specified city/location."""
        await ctx.defer()
        query = location.strip()
        if not query:
            await ctx.send("Please provide a valid location name.")
            return

        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
        encoded_loc = urllib.parse.quote(query)

        # 1. Try wttr.in JSON API first
        url = f"https://wttr.in/{encoded_loc}?format=j1"
        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                    if response.status == 200:
                        data = await response.json(content_type=None)
                        current = data['current_condition'][0]
                        temp_c = current['temp_C']
                        temp_f = current['temp_F']
                        feels_c = current['FeelsLikeC']
                        feels_f = current['FeelsLikeF']
                        desc = current['weatherDesc'][0]['value']
                        humidity = current['humidity']
                        wind_kmh = current['windspeedKmh']

                        nearest = data['nearest_area'][0]
                        area = nearest['areaName'][0]['value']
                        country = nearest['country'][0]['value']

                        temp_int = int(temp_c)
                        color = discord.Color.blue() if temp_int < 10 else (discord.Color.orange() if temp_int > 25 else discord.Color.green())

                        embed = discord.Embed(
                            title=f"🌡️ Weather in {area}, {country}",
                            description=f"**Condition:** {desc}",
                            color=color
                        )
                        embed.add_field(name="Temperature", value=f"{temp_c}°C / {temp_f}°F", inline=True)
                        embed.add_field(name="Feels Like", value=f"{feels_c}°C / {feels_f}°F", inline=True)
                        embed.add_field(name="Humidity", value=f"{humidity}%", inline=True)
                        embed.add_field(name="Wind Speed", value=f"{wind_kmh} km/h", inline=True)
                        embed.set_footer(text=f"Data provided by wttr.in • Requested by {ctx.author.display_name}")
                        await ctx.send(embed=embed)
                        return
        except Exception as e:
            logger.warning("wttr.in failed for location '%s': %s", query, e)

        # 2. Fallback to Open-Meteo Geocoding & Weather API
        try:
            geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={encoded_loc}&count=1&language=en&format=json"
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(geo_url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                    if response.status == 200:
                        geo_data = await response.json()
                        results = geo_data.get("results")
                        if results:
                            place = results[0]
                            lat = place["latitude"]
                            lon = place["longitude"]
                            name = place["name"]
                            country = place.get("country", "")

                            weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
                            async with session.get(weather_url, timeout=aiohttp.ClientTimeout(total=5)) as w_resp:
                                if w_resp.status == 200:
                                    w_data = await w_resp.json()
                                    cw = w_data.get("current_weather", {})
                                    temp_c = cw.get("temperature", 0)
                                    temp_f = round(temp_c * 9/5 + 32, 1)
                                    wind_kmh = cw.get("windspeed", 0)

                                    color = discord.Color.blue() if temp_c < 10 else (discord.Color.orange() if temp_c > 25 else discord.Color.green())
                                    location_title = f"{name}, {country}" if country else name

                                    embed = discord.Embed(
                                        title=f"🌡️ Weather in {location_title}",
                                        color=color
                                    )
                                    embed.add_field(name="Temperature", value=f"{temp_c}°C / {temp_f}°F", inline=True)
                                    embed.add_field(name="Wind Speed", value=f"{wind_kmh} km/h", inline=True)
                                    embed.set_footer(text=f"Data provided by Open-Meteo • Requested by {ctx.author.display_name}")
                                    await ctx.send(embed=embed)
                                    return
        except Exception as e:
            logger.warning("Open-Meteo fallback failed for location '%s': %s", query, e)

        await ctx.send(f"❌ Could not retrieve weather details for `{query}`. Make sure it's a valid city/location name.", ephemeral=True)


    @commands.hybrid_command(name="translate", aliases=["tr"])
    async def translate(self, ctx: commands.Context, text: str, target_language: str = "en"):
        """Translates text to a specified target language (defaults to English)."""
        url = "https://translate.googleapis.com/translate_a/single"
        params = {
            "client": "gtx",
            "sl": "auto",
            "tl": target_language.lower(),
            "dt": "t",
            "q": text
        }
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, params=params) as response:
                    if response.status != 200:
                        await ctx.send("Failed to translate the text. Please try again later.")
                        return
                    data = await response.json()
            except Exception as e:
                logger.exception("Translate command error: %s", e)
                await ctx.send("Failed to reach translation services.")
                return
                
        try:
            translated_parts = []
            for part in data[0]:
                if part[0]:
                    translated_parts.append(part[0])
            translated_text = "".join(translated_parts)
            src_lang = data[2]
            
            embed = discord.Embed(
                title="🔠 Translation Results",
                color=discord.Color.blue()
            )
            embed.add_field(name=f"Original Text ({src_lang.upper()})", value=text[:1024], inline=False)
            embed.add_field(name=f"Translated Text ({target_language.upper()})", value=translated_text[:1024], inline=False)
            embed.set_footer(text=f"Requested by {ctx.author.display_name}")
            await ctx.send(embed=embed)
        except Exception:
            await ctx.send("Could not parse translation response. Verify target language code (e.g., 'es', 'fr', 'en').")

    @commands.hybrid_command(name="poll")
    @commands.guild_only()
    async def poll(self, ctx: commands.Context, question: str, options: Optional[str] = None):
        """Creates a yes/no or multiple-choice poll. Separate options with |."""
        if not options:
            embed = discord.Embed(
                title="🗳️ Simple Poll",
                description=question,
                color=discord.Color.purple()
            )
            embed.set_footer(text=f"Poll by {ctx.author.display_name} • React with 👍 or 👎")
            msg = await ctx.send(embed=embed)
            await msg.add_reaction("👍")
            await msg.add_reaction("👎")
            return
            
        choices = [opt.strip() for opt in options.split("|") if opt.strip()]
        if len(choices) < 2:
            await ctx.send("You must provide at least 2 options for a multi-choice poll.", ephemeral=True)
            return
        if len(choices) > 10:
            await ctx.send("You cannot provide more than 10 options for a poll.", ephemeral=True)
            return
            
        emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
        choices_desc = ""
        for i, choice in enumerate(choices):
            choices_desc += f"{emojis[i]} {choice}\n\n"
            
        embed = discord.Embed(
            title=f"🗳️ {question}",
            description=choices_desc,
            color=discord.Color.purple()
        )
        embed.set_footer(text=f"Poll by {ctx.author.display_name} • React below to vote")
        msg = await ctx.send(embed=embed)
        for i in range(len(choices)):
            await msg.add_reaction(emojis[i])

    def parse_duration(self, duration_str: str) -> int:
        pattern = re.compile(r'(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?')
        match = pattern.match(duration_str.strip().lower())
        if not match or not any(match.groups()):
            return 0
            
        days = int(match.group(1) or 0)
        hours = int(match.group(2) or 0)
        minutes = int(match.group(3) or 0)
        seconds = int(match.group(4) or 0)
        
        return days * 86400 + hours * 3600 + minutes * 60 + seconds

    @commands.hybrid_command(name="remind", aliases=["reminder"])
    async def remind(self, ctx: commands.Context, duration: str, *, message: str):
        """Sets a reminder (e.g. 10m, 2h, 1d) with a custom message."""
        seconds = self.parse_duration(duration)
        if seconds <= 0:
            await ctx.send("Invalid duration format. Use formats like `10m`, `1h30m`, `2d`, or `30s`.", ephemeral=True)
            return
            
        if seconds > 30 * 86400:
            await ctx.send("Reminders cannot be set for more than 30 days.", ephemeral=True)
            return
            
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=seconds)
        expires_at_iso = expires_at.isoformat()
        
        async with get_connection() as conn:
            await conn.execute(
                "INSERT INTO reminders (user_id, channel_id, message, expires_at) VALUES (?, ?, ?, ?)",
                (ctx.author.id, ctx.channel.id, message, expires_at_iso)
            )
            await conn.commit()
            
        embed = discord.Embed(
            title="⏰ Reminder Set",
            description=f"I'll remind you about: **{message}**\n\n**Time:** <t:{int(expires_at.timestamp())}:R> (<t:{int(expires_at.timestamp())}:F>)",
            color=discord.Color.gold()
        )
        await ctx.send(embed=embed)

    @tasks.loop(seconds=10)
    async def check_reminders(self):
        now = datetime.now(timezone.utc).isoformat()
        async with get_connection() as conn:
            cur = await conn.execute("SELECT id, user_id, channel_id, message FROM reminders WHERE expires_at <= ?", (now,))
            expired = await cur.fetchall()
            await cur.close()
            
            for row in expired:
                rem_id, user_id, channel_id, message = row['id'], row['user_id'], row['channel_id'], row['message']
                
                channel = self.bot.get_channel(channel_id)
                if not channel:
                    try:
                        channel = await self.bot.fetch_channel(channel_id)
                    except Exception:
                        pass
                
                if channel:
                    try:
                        await channel.send(f"⏰ <@{user_id}>, you asked to be reminded: **{message}**")
                    except Exception:
                        user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
                        if user:
                            try:
                                await user.send(f"⏰ You asked to be reminded: **{message}** (Sent via DM because channel was inaccessible)")
                            except Exception:
                                pass
                                
                await conn.execute("DELETE FROM reminders WHERE id = ?", (rem_id,))
            if expired:
                await conn.commit()

    @check_reminders.before_loop
    async def before_check_reminders(self):
        await self.bot.wait_until_ready()

    operators = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Pow: operator.pow,
        ast.USub: operator.neg,
        ast.UAdd: lambda x: x
    }

    def safe_eval(self, node):
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return node.value
            raise TypeError("Invalid constant type")
        elif isinstance(node, ast.BinOp):
            left = self.safe_eval(node.left)
            right = self.safe_eval(node.right)
            op = type(node.op)
            if op in self.operators:
                if op == ast.Div and right == 0:
                    raise ZeroDivisionError("Division by zero")
                if op == ast.Pow and (left > 10000 or right > 100):
                    raise ValueError("Numbers too large to calculate power")
                return self.operators[op](left, right)
            raise TypeError(f"Unsupported operator: {node.op}")
        elif isinstance(node, ast.UnaryOp):
            operand = self.safe_eval(node.operand)
            op = type(node.op)
            if op in self.operators:
                return self.operators[op](operand)
            raise TypeError(f"Unsupported unary operator: {node.op}")
        elif isinstance(node, ast.Expression):
            return self.safe_eval(node.body)
        else:
            raise TypeError(f"Unsupported element: {node}")

    @commands.hybrid_command(name="calculator", aliases=["calc", "math"])
    async def calculator(self, ctx: commands.Context, *, expression: str):
        """Safely evaluates a basic mathematical expression."""
        cleaned = expression.replace(" ", "").replace("x", "*")
        try:
            tree = ast.parse(cleaned, mode='eval')
            result = self.safe_eval(tree)
            if isinstance(result, float) and result.is_integer():
                result = int(result)
                
            embed = discord.Embed(
                title="🧮 Calculator",
                color=discord.Color.green()
            )
            embed.add_field(name="Expression", value=f"`{expression}`", inline=False)
            embed.add_field(name="Result", value=f"`{result}`", inline=False)
            await ctx.send(embed=embed)
        except ZeroDivisionError:
            await ctx.send("❌ Error: Division by zero is not allowed.", ephemeral=True)
        except (ValueError, TypeError, SyntaxError) as e:
            await ctx.send(f"❌ Error: Invalid expression. Use basic operations (+, -, *, /, **, parenthesization).", ephemeral=True)
        except Exception:
            await ctx.send("❌ Error: Could not evaluate expression.", ephemeral=True)

    @commands.hybrid_command(name="afk")
    async def afk(self, ctx: commands.Context, *, message: Optional[str] = "AFK"):
        """Marks you as AFK. Sends a status if anyone mentions you."""
        afk_message = message[:200]
        since_iso = datetime.now(timezone.utc).isoformat()
        
        async with get_connection() as conn:
            await conn.execute(
                "INSERT OR REPLACE INTO afk (user_id, message, since) VALUES (?, ?, ?)",
                (ctx.author.id, afk_message, since_iso)
            )
            await conn.commit()
            
        original_nick = ctx.author.display_name
        if not original_nick.startswith("[AFK] "):
            try:
                await ctx.author.edit(nick=f"[AFK] {original_nick[:25]}")
            except Exception:
                pass
                
        await ctx.send(f"💤 {ctx.author.mention}, I have set your AFK status: **{afk_message}**")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
            
        async with get_connection() as conn:
            cur = await conn.execute("SELECT since FROM afk WHERE user_id = ?", (message.author.id,))
            row = await cur.fetchone()
            await cur.close()
            
            if row:
                since_str = row['since']
                since = datetime.fromisoformat(since_str)
                if (datetime.now(timezone.utc) - since).total_seconds() > 3:
                    await conn.execute("DELETE FROM afk WHERE user_id = ?", (message.author.id,))
                    await conn.commit()
                    
                    if message.author.nick and message.author.nick.startswith("[AFK] "):
                        try:
                            await message.author.edit(nick=message.author.nick[6:])
                        except Exception:
                            pass
                            
                    await message.channel.send(f"👋 Welcome back {message.author.mention}! I've removed your AFK status.")
                    
        if message.mentions:
            unique_mentions = list(set(message.mentions))
            for member in unique_mentions:
                if member.id == message.author.id:
                    continue
                    
                async with get_connection() as conn:
                    cur = await conn.execute("SELECT message, since FROM afk WHERE user_id = ?", (member.id,))
                    row = await cur.fetchone()
                    await cur.close()
                    
                    if row:
                        afk_msg, since_str = row['message'], row['since']
                        since_ts = int(datetime.fromisoformat(since_str).timestamp())
                        await message.channel.send(
                            f"💤 **{member.display_name}** is AFK: {afk_msg} (<t:{since_ts}:R>)"
                        )


    @commands.hybrid_command(name="gif", aliases=["searchgif", "search_gif"])
    async def gif(self, ctx: commands.Context, *, query: str):
        """Search Giphy and Tenor for a matching GIF and display one."""
        await ctx.defer()
        from utils.gif_service import search_gifs
        import random
        try:
            gifs = await search_gifs(query)
            if not gifs:
                await ctx.send(f"❌ No GIFs found for `{query}`.")
                return
            selected = random.choice(gifs[:5])
            await ctx.send(selected)
        except Exception as e:
            logger.exception("Failed to run gif command: %s", e)
            await ctx.send("❌ Failed to search for GIF.")


    @commands.hybrid_command(
        name="steal",
        aliases=["stealemoji", "stealsticker", "addemoji", "addsticker", "steal_emoji", "steal_sticker"]
    )
    @commands.guild_only()
    async def steal(self, ctx: commands.Context, *, input_arg: Optional[str] = None):
        """Steal custom emojis or stickers from a message reply or argument and add them to this server."""
        if not ctx.guild:
            return

        # Check user permission (Create & Manage Expressions / Emojis & Stickers, Administrator, or Guild/Bot Owner)
        has_expr_perm = (
            getattr(ctx.author.guild_permissions, "manage_expressions", False)
            or getattr(ctx.author.guild_permissions, "manage_emojis_and_stickers", False)
        )
        is_allowed = (
            has_expr_perm
            or ctx.author.guild_permissions.administrator
            or getattr(ctx.guild, "owner_id", None) == ctx.author.id
        )
        if not is_allowed:
            is_owner = await self.bot.is_owner(ctx.author)
            if is_owner:
                is_allowed = True

        if not is_allowed:
            await ctx.send("❌ You need the **Create & Manage Expressions** (Manage Emojis & Stickers) permission to use this command.", ephemeral=True)
            return


        # Check bot permission
        if ctx.guild.me and not ctx.guild.me.guild_permissions.manage_emojis_and_stickers:
            await ctx.send("❌ I need the 'Manage Emojis and Stickers' permission to add emojis or stickers.", ephemeral=True)
            return

        emoji_pattern = re.compile(r"<(a)?:([a-zA-Z0-9_]{2,32}):(\d+)>")

        target_emojis = []
        target_stickers = []
        custom_name = None

        # 1. Parse input_arg if provided
        if input_arg:
            matches = emoji_pattern.findall(input_arg)
            if matches:
                target_emojis = matches
                cleaned = emoji_pattern.sub("", input_arg).strip()
                if cleaned:
                    custom_name = cleaned.split()[0]
            else:
                custom_name = input_arg.strip().split()[0]

        # 2. If no emojis found in input_arg, check replied message
        if not target_emojis and ctx.message and ctx.message.reference and ctx.message.reference.message_id:
            try:
                ref_msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
                if ref_msg:
                    # Check stickers in referenced message
                    if ref_msg.stickers:
                        target_stickers.extend(ref_msg.stickers)
                    # Check emojis in referenced message content
                    if ref_msg.content:
                        ref_matches = emoji_pattern.findall(ref_msg.content)
                        if ref_matches:
                            target_emojis.extend(ref_matches)
            except Exception as e:
                logger.warning("Could not fetch referenced message: %s", e)

        # 3. Check stickers attached to current command message if still nothing found
        if not target_emojis and not target_stickers and ctx.message and ctx.message.stickers:
            target_stickers.extend(ctx.message.stickers)

        # 4. If nothing found at all, inform user
        if not target_emojis and not target_stickers:
            await ctx.send("❌ No custom emoji or sticker found. Reply to a message with emojis/stickers or pass custom emojis in the command (e.g. `!steal <:emoji:123> [name]`).", ephemeral=True)
            return

        await ctx.defer()

        # Handle Sticker stealing if stickers were found
        if target_stickers:
            sticker = target_stickers[0]
            embed = discord.Embed(
                title="✨ Steal Sticker",
                description="Choose the option to steal as Emoji or Sticker",
                color=discord.Color.blurple()
            )
            sticker_url = getattr(sticker, "url", None) or f"https://cdn.discordapp.com/stickers/{sticker.id}.png"
            embed.set_thumbnail(url=sticker_url)

            view = StealStickerView(ctx, sticker, custom_name)
            await ctx.send(embed=embed, view=view)
            return


        # Handle Emoji stealing if custom emojis were found
        stolen_emojis = []
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
        for is_anim, e_name, e_id in target_emojis[:5]:  # limit up to 5 at once
            name = (custom_name if (custom_name and len(target_emojis) == 1) else e_name)
            name = re.sub(r"[^a-zA-Z0-9_]", "", name).strip()
            if len(name) < 2:
                name = f"emoji_{name}"
            name = name[:32]

            is_animated = bool(is_anim)
            ext_choices = ["gif"] if is_animated else ["png", "gif", "webp"]
            img_bytes = None

            for ext in ext_choices:
                url = f"https://cdn.discordapp.com/emojis/{e_id}.{ext}?size=1024"
                try:
                    async with aiohttp.ClientSession(headers=headers) as session:
                        async with session.get(url) as resp:
                            if resp.status == 200:
                                img_bytes = await resp.read()
                                break
                except Exception as exc:
                    logger.warning("Error fetching emoji url %s: %s", url, exc)


            if not img_bytes:
                await ctx.send(f"❌ Failed to download emoji `:{e_name}:`.", ephemeral=True)
                continue

            try:
                new_emoji = await ctx.guild.create_custom_emoji(
                    name=name,
                    image=img_bytes,
                    reason=f"Stolen by {ctx.author}"
                )
                stolen_emojis.append(f"{new_emoji} (`:{new_emoji.name}:`)")

            except discord.HTTPException as e:
                logger.exception("HTTP error stealing emoji %s: %s", e_name, e)
                await ctx.send(f"❌ Failed to steal emoji `:{e_name}:`: {e.text or e}", ephemeral=True)
            except Exception as e:
                logger.exception("Error stealing emoji %s: %s", e_name, e)
                await ctx.send(f"❌ Error stealing emoji `:{e_name}:`: {e}", ephemeral=True)

        if stolen_emojis:
            await ctx.send(f"✅ Successfully stole emoji(s): {' '.join(stolen_emojis)}")

    @commands.hybrid_command(name="tts", aliases=["speak", "say_tts", "text_to_speech"])
    @commands.guild_only()
    async def tts(self, ctx: commands.Context, *, words: Optional[str] = None):
        """Play Text-to-Speech audio in your voice channel. Usage: !tts say <words> or !tts say <lang> <words>"""
        if not words:
            await ctx.send("❌ Please provide words to speak. Usage: `!tts say <words>` or `!tts say [lang] <words>` (e.g. `!tts say hello world` or `!tts say es Hola amigos`).", ephemeral=True)
            return

        text_to_speak = words.strip()
        if text_to_speak.lower().startswith("say "):
            text_to_speak = text_to_speak[4:].strip()

        if not text_to_speak:
            await ctx.send("❌ Please provide words to speak. Usage: `!tts say <words>`.", ephemeral=True)
            return

        from utils.tts_service import detect_language, play_tts_on_voice
        tokens = text_to_speak.split(maxsplit=1)
        lang = None
        SUPPORTED_LANGS = {"en", "es", "fr", "de", "ru", "ja", "hi", "it", "pt", "zh", "ko", "ar", "tr", "nl", "pl", "sv"}
        if len(tokens) > 1 and tokens[0].lower() in SUPPORTED_LANGS:
            lang = tokens[0].lower()
            text_to_speak = tokens[1].strip()
        else:
            lang = detect_language(text_to_speak)

        # Connect to voice channel if needed
        if not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.send("❌ You must be connected to a voice channel to use TTS.", ephemeral=True)
            return

        channel = ctx.author.voice.channel
        vc = ctx.guild.voice_client
        if not vc or not vc.is_connected():
            try:
                from services.music.voice import connect_to_channel
                vc = await connect_to_channel(channel)
            except Exception as e:
                logger.exception("Failed to connect to voice channel for TTS: %s", e)
                await ctx.send("❌ Failed to connect to your voice channel.", ephemeral=True)
                return

        await ctx.defer()
        display_lang = lang
        if lang == "hi" and any(c.isalpha() and ord(c) < 128 for c in text_to_speak):
            display_lang = "hi (Hinglish)"

        try:
            await ctx.send(f"🗣️ **TTS Speaking:** \"{text_to_speak}\" (Language: `{display_lang}`)")
            await play_tts_on_voice(vc, text_to_speak, lang=lang)


        except Exception as e:
            logger.exception("Failed to play TTS: %s", e)
            await ctx.send("❌ Failed to generate or play TTS audio.", ephemeral=True)

    @commands.hybrid_command(name="help", aliases=["commands", "cmds"])
    async def help(self, ctx: commands.Context, command_name: Optional[str] = None):
        """Displays an interactive menu of all bot commands organized by category."""
        if command_name:
            cmd = self.bot.get_command(command_name.lower())
            if cmd:
                embed = discord.Embed(
                    title=f"📖 Command: {cmd.name}",
                    description=cmd.help or "No detailed description provided.",
                    color=discord.Color.blurple()
                )
                if cmd.aliases:
                    embed.add_field(name="Aliases", value=", ".join(f"`{a}`" for a in cmd.aliases), inline=True)
                embed.add_field(name="Usage", value=f"`!{cmd.name} {cmd.signature}`", inline=False)
                await ctx.send(embed=embed)
                return
            else:
                await ctx.send(f"❌ Command `{command_name}` not found.", ephemeral=True)
                return

        # Check if author is Bot Owner
        is_owner = False
        import os
        owner_id_str = os.getenv("OWNER_ID")
        if owner_id_str and ctx.author.id == int(owner_id_str):
            is_owner = True
        else:
            try:
                is_owner = await self.bot.is_owner(ctx.author)
            except Exception:
                pass

        categories_desc = (
            "Welcome to **Helix**! Use the dropdown menu below to navigate to a command suite of your choice.\n\n"
            "☰ **Command Modules**\n\n"
            "> 🤖 **AI Assistant & Images** (`ai`) — Free Gemini/Groq chat & Flux image generation\n"
            "> 🎵 **Music & Audio** (`music`) — Voice playback, queues, volume & VC speech\n"
            "> 🛠️ **Utility & Tools** (`utility`) — Steal emojis/stickers, GIFs, polls & weather\n"
            "> 🛡️ **Moderation & Security** (`mod`) — Interactive history, mutes, bans & modlogs\n"
            "> 💵 **Economy & Casino** (`economy`) — Balance cards, work, daily, shop & games\n"
            "> ⭐ **Leveling & Chat XP** (`levels`) — Rank cards, chat XP & guild leaderboards\n"
            "> ⚙️ **Server & Settings** (`server`) — Server statistics, role info & member stats\n"
        )

        if is_owner:
            categories_desc += "> 👑 **Owner Commands** (`owner`) — Bot profile, restart, prefixless & eval\n"

        embed = discord.Embed(
            color=discord.Color.from_rgb(88, 101, 242)
        )
        bot_user = getattr(self.bot, "user", None)
        if bot_user and hasattr(bot_user, "display_avatar"):
            embed.set_author(name="Helix Command Center", icon_url=bot_user.display_avatar.url)
        else:
            embed.set_author(name="Helix Command Center")
        embed.description = categories_desc

        embed.add_field(
            name="💡 Quick Tip",
            value="Select a module from the dropdown below to explore detailed commands, or use `!help <command>` for an instant command breakdown.",
            inline=False
        )
        owner = self.bot.owner_user if hasattr(self.bot, "owner_user") else None
        owner_text = f" • Created by {owner.name}" if owner else ""
        embed.set_footer(text=f"Helix Systems{owner_text}")

        view = HelpView(self.bot, is_owner=is_owner)
        await ctx.send(embed=embed, view=view)


class HelpSelect(discord.ui.Select):
    def __init__(self, bot, is_owner: bool = False):
        options = [
            discord.SelectOption(label="AI Chatbot", emoji="🤖", description="Ask AI, imagine image gen, daily limits, AI channel"),
            discord.SelectOption(label="Music & Voice", emoji="🎵", description="Play music, TTS, queue, volume, voice status"),
            discord.SelectOption(label="Utility & Fun", emoji="🛠️", description="Steal emojis/stickers, GIFs, polls, weather, calc"),
            discord.SelectOption(label="Moderation & Logs", emoji="🛡️", description="Mute, kick, ban, warn, modlog, history sections"),
            discord.SelectOption(label="Economy & Games", emoji="💵", description="Balance, daily, work, rob, shop, casino games"),
            discord.SelectOption(label="Leveling", emoji="⭐", description="Rank, levels leaderboard, toggle XP"),
            discord.SelectOption(label="Server & Settings", emoji="⚙️", description="Server info, role info, member count"),
        ]

        if is_owner:
            options.append(
                discord.SelectOption(label="Owner Commands", emoji="👑", description="Bot profile, restart, sync, addxp, prefixless, eval")
            )
        super().__init__(placeholder="Choose a command category...", min_values=1, max_values=1, options=options)
        self.bot = bot
        self.is_owner = is_owner

    async def callback(self, interaction: discord.Interaction):
        cat = self.values[0]
        embed = discord.Embed(color=discord.Color.from_rgb(88, 101, 242))
        bot_user = getattr(self.bot, "user", None)
        if bot_user and hasattr(bot_user, "display_avatar"):
            embed.set_author(name=f"Helix Help • {cat}", icon_url=bot_user.display_avatar.url)
        else:
            embed.set_author(name=f"Helix Help • {cat}")


        if cat == "AI Chatbot":
            embed.title = "🤖 AI Assistant & Image Commands"
            embed.add_field(
                name="💬 AI Text Assistant",
                value=(
                    "> `ask <prompt>` (alias `ai`) — Query AI assistant *(Gemini & Groq free models)*\n"
                    "> `clearchat` — Clear AI conversation memory buffer for channel\n"
                    "> `setaiprovider <engine>` — Switch default AI engine *(gemini|groq|openai)*"
                ),
                inline=False
            )
            embed.add_field(
                name="🎨 Image Generation",
                value="> `imagine <prompt>` (alias `draw`) — Generate AI artwork *(Exclusive image output)*",
                inline=False
            )
            embed.add_field(
                name="📊 Quotas & Channels",
                value=(
                    "> `ailimit` (alias `aiusage`) — Check remaining daily questions & images *(10 text / 2 images)*\n"
                    "> `setaichannel <#channel|reset>` — Lock AI chat to a specific channel"
                ),
                inline=False
            )

        elif cat == "Music & Voice":
            embed.title = "🎵 Music & Voice Commands"
            embed.add_field(
                name="🎶 Playback Controls",
                value=(
                    "> `play <query|url>` (alias `p`) — Play a song or YouTube playlist\n"
                    "> `nowplaying` (alias `np`) — Currently playing track info & control buttons\n"
                    "> `skip` — Skip current track *(Autoplay next if empty)*\n"
                    "> `pause` / `resume` / `stop` / `leave` — Control playback & voice connection"
                ),
                inline=False
            )
            embed.add_field(
                name="🎛️ Queue & Sound Settings",
                value=(
                    "> `queue` (alias `q`) — View music queue & loop status\n"
                    "> `volume <percent>` — Adjust playback volume *(0-100%)*\n"
                    "> `autoplay [on|off]` — Toggle automatic song recommendations"
                ),
                inline=False
            )
            embed.add_field(
                name="🗣️ Voice Speech",
                value="> `tts say <words>` — Speak audio in VC *(Supports Hinglish & auto-language)*",
                inline=False
            )

        elif cat == "Utility & Fun":
            embed.title = "🛠️ Utility & Fun Commands"
            embed.add_field(
                name="✨ Media & Stealing",
                value=(
                    "> `steal <emoji|sticker>` — Steal emojis/stickers from replies or inputs\n"
                    "> `gif <query>` — Search & send native GIFs\n"
                    "> `avatar` / `banner` — View user profile avatar or banner"
                ),
                inline=False
            )
            embed.add_field(
                name="📊 Tools & Utilities",
                value=(
                    "> `poll <question> [opt1|opt2]` — Create interactive polls\n"
                    "> `remind <duration> <msg>` — Set a timed reminder *(e.g. 10m, 2h)*\n"
                    "> `calculator <expression>` (alias `calc`) — Safe math calculator\n"
                    "> `weather <location>` — Check weather forecast for a city"
                ),
                inline=False
            )
            embed.add_field(
                name="📡 Vanity Checker & Tracker",
                value=(
                    "> `checkvanity <code` (alias `vanity`) — Check if a Discord vanity is available or taken\n"
                    "> `trackvanity <code` — Receive an instant DM alert when a vanity opens up\n"
                    "> `untrackvanity <code` — Stop tracking a vanity\n"
                    "> `myvanities` (alias `trackedvanities`) — View your active vanity trackers"
                ),
                inline=False
            )


        elif cat == "Moderation & Logs":
            embed.title = "🛡️ Moderation & Logging Commands"
            embed.add_field(
                name="🛡️ Member Moderation",
                value=(
                    "> `mute` / `unmute` / `tempmute` — Text channel mute management\n"
                    "> `vcmute` / `vcunmute` — Voice channel mutes\n"
                    "> `kick` / `ban` / `unban` — Server member moderation\n"
                    "> `forcenick <user> <nick>` (alias `fn`) — Force & lock member nickname"
                ),
                inline=False
            )
            embed.add_field(
                name="🤖 Discord Native AutoMod & Whitelist",
                value=(
                    "> `automod config` — View server AutoMod settings & whitelists\n"
                    "> `automod enable` / `disable` — Toggle AutoMod protection\n"
                    "> `automod ignore channel/role` — Whitelist channel or role\n"
                    "> `automod unignore channel/role` — Remove channel/role whitelist\n"
                    "> `automod ignore show/reset` — View or reset whitelist\n"
                    "> `automod logging <channel>` — Set AutoMod logging channel\n"
                    "> `automod punishment <action>` — Set default punishment action\n"
                    "> `automod list` / `blockwords` / `antispam` / `presets` — Manage rules"
                ),
                inline=False
            )


            embed.add_field(
                name="📜 Logging, Warnings & DM Alerts",
                value=(
                    "> `warn <user> [reason]` — Issue warning (auto-escalates: 3rd=2h, 4th=1d, 5th=7d, 6th=14d, 7th=28d timeout, 8th=Kick)\n"
                    "> `modlog dm [on|off]` — Toggle Direct Message moderation notifications for the server\n"
                    "> `history <user>` — Interactive mod history card with section buttons\n"
                    "> `warns <user>` — View member warning history\n"
                    "> `purge <amount>` (alias `clear`) — Bulk delete channel messages\n"
                    "> `modlog set-channel` — Configure moderation logging channel"
                ),
                inline=False
            )


        elif cat == "Economy & Games":
            embed.title = "💵 Economy & Games Commands"
            embed.add_field(
                name="💳 Balance & Accounts",
                value=(
                    "> `balance` (alias `bal`) — Wallet & bank balance card\n"
                    "> `leaderboard` (alias `lb`, `baltop`) — Economy net worth leaderboard\n"
                    "> `pay <user> <amount>` — Transfer coins to another member"
                ),
                inline=False
            )
            embed.add_field(
                name="💼 Income & Robbing",
                value=(
                    "> `daily` / `work` — Claim daily rewards & work income\n"
                    "> `rob <user>` — Attempt to steal wallet coins\n"
                    "> `deposit` / `withdraw` (alias `dep`, `with`) — Bank account management"
                ),
                inline=False
            )
            embed.add_field(
                name="🛍️ Marketplace & Items",
                value=(
                    "> `shop` — Browse interactive market with category filters\n"
                    "> `buy <item_id> [amount]` — Purchase items from the shop\n"
                    "> `inventory` (alias `inv`) — View owned items & value\n"
                    "> `use <item_id>` — Consume items *(Energy drink work reset, potions, shields)*"
                ),
                inline=False
            )
            embed.add_field(
                name="🎰 Casino Mini-Games",
                value="> `coinflip` / `dice` / `slots` — Casino gambling minigames",
                inline=False
            )


        elif cat == "Leveling":
            embed.title = "⭐ Leveling & Chat XP Commands"
            embed.add_field(
                name="⭐ Rank & Leaderboard",
                value=(
                    "> `rank` (alias `level`, `lvl`) — Rank card with avatar, Level, XP & progress bar\n"
                    "> `levels` (alias `toplevels`, `topxp`) — Chat level leaderboard & range selector"
                ),
                inline=False
            )
            embed.add_field(
                name="⚙️ Leveling Configuration",
                value=(
                    "> `setlevelchannel <#ch|reset>` — Level-up announcement channel\n"
                    "> `ignorexp [target]` — Toggle ignored users/channels or view config\n"
                    "> `togglexp [on|off]` — Enable/disable server XP leveling system"
                ),
                inline=False
            )

        elif cat == "Server & Settings":
            embed.title = "⚙️ Server & Settings Commands"
            embed.add_field(
                name="ℹ️ Server & User Cards",
                value=(
                    "> `serverinfo` (alias `si`) — Server stats, owner, member breakdown & banner\n"
                    "> `userinfo` (alias `ui`) — User profile card, booster status & permissions\n"
                    "> `roleinfo` — Role permissions & member count\n"
                    "> `membercount` — Total server member breakdown"
                ),
                inline=False
            )

        elif cat == "Owner Commands":
            embed.title = "👑 Bot Owner Commands"
            embed.add_field(
                name="👑 Bot Branding & Bio",
                value=(
                    "> `server_avatar` / `server_banner` — Set/reset server bot profile\n"
                    "> `server_about <text|reset>` — Set/reset bot's server 'About Me' bio\n"
                    "> `global_avatar` / `global_banner` — Set/reset bot's global avatar & banner\n"
                    "> `prefixless_grant` / `prefixless_revoke` / `prefixless_list` — Manage prefixless command permissions"
                ),
                inline=False
            )
            embed.add_field(
                name="⚡ Management & Debug",
                value=(
                    "> `addxp <user> <amount>` — Award XP to member\n"
                    "> `ignorexp <user>` — Toggle XP gain for user\n"
                    "> `addmoney` — Add/subtract coins from any wallet\n"
                    "> `volume <percent>` — Set voice volume to any unrestricted %\n"
                    "> `restart` — Reboot bot process with nickname confirmation\n"
                    "> `sync` — Sync slash/app commands globally or to guild\n"
                    "> `presence` / `presence_rotation` — Configure global activity presence\n"
                    "> `voice_debug` / `eval` — System diagnostics & Python code evaluation"
                ),
                inline=False
            )

        owner = self.bot.owner_user if hasattr(self.bot, "owner_user") else None
        owner_text = f" | Created & Owned by {owner.name}" if owner else ""
        embed.set_footer(text=f"Helix Help Panel{owner_text}")
        await interaction.response.edit_message(embed=embed, view=self.view)


class HelpView(discord.ui.View):
    def __init__(self, bot, is_owner: bool = False):
        super().__init__(timeout=180)
        self.add_item(HelpSelect(bot, is_owner=is_owner))



async def setup(bot: commands.Bot):
    if bot.get_command("help"):
        bot.remove_command("help")
    await bot.add_cog(Utility(bot))




