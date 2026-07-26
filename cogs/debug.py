import asyncio
from typing import Optional
import importlib
import logging
import subprocess
import shutil
import json
import os
import sys
from discord.ext import commands
import discord
from config import config as app_config

logger = logging.getLogger(__name__)


class DebugCog(commands.Cog):
    """Owner-only debugging and bot management commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._presence_rotation_task = None
        self._presence_rotation_wakeup = asyncio.Event()

    async def cog_load(self):
        self._presence_rotation_task = asyncio.create_task(self._run_presence_rotation())

    def cog_unload(self):
        if self._presence_rotation_task:
            self._presence_rotation_task.cancel()

    def _wake_presence_rotation(self):
        self._presence_rotation_wakeup.set()

    async def _run_presence_rotation(self):
        """Continuously apply the configured global presence rotation."""
        from utils.config_service import get_guild_config, set_guild_config
        from utils.presence import set_presence

        try:
            await self.bot.wait_until_ready()
        except Exception:
            pass

        while True:

            try:
                cfg = await get_guild_config(0)
                entries = cfg.get("presence_rotation") or []
                enabled = cfg.get("presence_rotation_enabled", False)
                interval = cfg.get("presence_rotation_interval", 60)

                if not enabled or not isinstance(entries, list) or not entries:
                    self._presence_rotation_wakeup.clear()
                    await self._presence_rotation_wakeup.wait()
                    continue

                interval = max(15, int(interval))
                index = int(cfg.get("presence_rotation_index", 0)) % len(entries)
                entry = entries[index]
                if not isinstance(entry, dict):
                    await set_guild_config(0, {"presence_rotation_index": (index + 1) % len(entries)})
                    continue

                await set_presence(self.bot, entry)
                await set_guild_config(0, {"presence_rotation_index": (index + 1) % len(entries)})
                self._presence_rotation_wakeup.clear()
                try:
                    await asyncio.wait_for(self._presence_rotation_wakeup.wait(), timeout=interval)
                except asyncio.TimeoutError:
                    pass
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Presence rotation failed; retrying in 15 seconds.")
                await asyncio.sleep(15)

    async def _is_owner(self, user):
        cfg_owner = app_config.get("owner_id")
        try:
            if cfg_owner and int(cfg_owner) == user.id:
                return True
        except Exception:
            pass
        try:
            return await self.bot.is_owner(user)
        except Exception:
            return False

    @staticmethod
    def _is_presence_owner(user: discord.abc.User) -> bool:
        """Return whether the user is the explicit OWNER_ID from .env.

        Presence is global to the bot account, so it must not fall back to
        Discord's application-owner check or any guild-level permission.
        """
        owner_id = os.getenv("OWNER_ID")
        try:
            return bool(owner_id) and int(owner_id) == user.id
        except (TypeError, ValueError):
            logger.warning("OWNER_ID is missing or invalid; global presence changes are disabled.")
            return False

    @commands.command(name="voice_debug")
    async def voice_debug(self, ctx: commands.Context):
        """Run quick voice environment diagnostics (owner-only).

        Reports whether davey and PyNaCl are importable, whether discord.opus is loaded,
        and whether ffmpeg is available on PATH (and its version).
        Usage: !voice_debug
        """
        if not await self._is_owner(ctx.author):
            await ctx.send("You are not authorized to run this command.")
            return

        parts = []

        # Check davey
        try:
            spec = importlib.util.find_spec("davey")
            if spec is None:
                parts.append("davey: NOT INSTALLED")
            else:
                parts.append("davey: installed")
        except Exception as exc:
            parts.append(f"davey: check failed: {exc}")

        # Check PyNaCl (nacl)
        try:
            spec = importlib.util.find_spec("nacl")
            if spec is None:
                parts.append("PyNaCl (nacl): NOT INSTALLED")
            else:
                parts.append("PyNaCl (nacl): installed")
        except Exception as exc:
            parts.append(f"PyNaCl check failed: {exc}")

        # Check discord.opus
        try:
            opus = getattr(discord, "opus", None)
            if opus and getattr(opus, "is_loaded", lambda: False)():
                parts.append("discord.opus: loaded")
            else:
                parts.append("discord.opus: NOT loaded")
        except Exception as exc:
            parts.append(f"discord.opus check failed: {exc}")

        # Check ffmpeg on PATH
        try:
            ff = shutil.which("ffmpeg")
            if ff:
                # try run ffmpeg -version
                try:
                    proc = subprocess.run([ff, "-version"], capture_output=True, text=True, timeout=3)
                    ver = proc.stdout.splitlines()[0] if proc.stdout else proc.stderr.splitlines()[0]
                    parts.append(f"ffmpeg: found at {ff} -> {ver}")
                except Exception as exc:
                    parts.append(f"ffmpeg found at {ff} but version check failed: {exc}")
            else:
                parts.append("ffmpeg: NOT found on PATH")
        except Exception as exc:
            parts.append(f"ffmpeg check failed: {exc}")

        # Compose and send result
        msg = "\n".join(parts)
        if len(msg) > 1900:
            await ctx.send("Diagnostics too long, sending as file.")
            import io
            await ctx.send(file=discord.File(fp=io.StringIO(msg), filename="voice_diagnostics.txt"))
        else:
            await ctx.send(f"```\n{msg}\n```")

    @commands.command(name="restart")
    async def restart(self, ctx: commands.Context):
        """Restart the bot (owner-only)."""
        if not await self._is_owner(ctx.author):
            await ctx.send("You are not authorized to run this command.")
            return

        message = await ctx.send("Restarting the bot... 🔄")
        logger.info("Bot restart requested by owner %s (id=%s)", ctx.author, ctx.author.id)

        # Save message details to update it after reboot
        try:
            os.makedirs("data", exist_ok=True)
            with open("data/restart_msg.json", "w") as f:
                json.dump({"channel_id": message.channel.id, "message_id": message.id}, f)
        except Exception as e:
            logger.warning("Failed to save restart message state: %s", e)

        # Re-execute process immediately
        os.execv(sys.executable, [sys.executable] + sys.argv)

    @commands.command(name="presence")
    @commands.guild_only()
    async def presence(self, ctx: commands.Context, activity_type: str, status: str, *, text: str, streaming_url: str = None):
        """Set custom rich presence (Owner only). Activity: playing, listening, watching, streaming"""
        if not self._is_presence_owner(ctx.author):
            await ctx.send("Only the bot owner configured in `OWNER_ID` can change the global presence.", ephemeral=True)
            return

        activity_type = activity_type.lower().strip()
        status = status.lower().strip()

        if activity_type not in ("playing", "streaming", "listening", "watching"):
            await ctx.send("Invalid activity type. Choose from: `playing`, `streaming`, `listening`, `watching`.", ephemeral=True)
            return

        if status not in ("online", "idle", "dnd", "invisible"):
            await ctx.send("Invalid status. Choose from: `online`, `idle`, `dnd`, `invisible`.", ephemeral=True)
            return

        try:
            from utils.config_service import set_guild_config
            from utils.presence import load_and_set_presence
            
            # Save to global config (guild 0)
            await set_guild_config(0, {
                "presence_activity": activity_type,
                "presence_name": text,
                "presence_status": status,
                "presence_url": streaming_url,
                "presence_rotation_enabled": False,
            })
            self._wake_presence_rotation()
            
            # Apply immediately
            await load_and_set_presence(self.bot)
            await ctx.send(f"✅ Bot presence updated: **{status}** | **{activity_type}** `{text}`")
        except Exception as e:
            logger.exception("Failed to set presence: %s", e)
            await ctx.send("Failed to update bot presence.", ephemeral=True)

    @commands.command(name="presence_add")
    @commands.guild_only()
    async def presence_add(self, ctx: commands.Context, activity_type: str, status: str, *, text: str):
        """Add an entry to the owner-controlled global presence rotation."""
        if not self._is_presence_owner(ctx.author):
            await ctx.send("Only the bot owner configured in `OWNER_ID` can manage global presence rotation.", ephemeral=True)
            return

        activity_type = activity_type.lower().strip()
        status = status.lower().strip()
        if activity_type not in ("playing", "streaming", "listening", "watching"):
            await ctx.send("Invalid activity type. Choose: `playing`, `streaming`, `listening`, `watching`.", ephemeral=True)
            return
        if status not in ("online", "idle", "dnd", "invisible"):
            await ctx.send("Invalid status. Choose: `online`, `idle`, `dnd`, `invisible`.", ephemeral=True)
            return

        from utils.config_service import get_guild_config, set_guild_config
        cfg = await get_guild_config(0)
        entries = list(cfg.get("presence_rotation") or [])
        entries.append({"presence_activity": activity_type, "presence_status": status, "presence_name": text})
        await set_guild_config(0, {"presence_rotation": entries})
        await ctx.send(f"Added rotation presence #{len(entries)}: **{status}** | **{activity_type}** `{text}`")

    @commands.command(name="presence_rotation")
    @commands.guild_only()
    async def presence_rotation(self, ctx: commands.Context, action: str, interval_seconds: int = None):
        """Manage global presence rotation: start, stop, list, clear, or remove <number>."""
        if not self._is_presence_owner(ctx.author):
            await ctx.send("Only the bot owner configured in `OWNER_ID` can manage global presence rotation.", ephemeral=True)
            return

        from utils.config_service import get_guild_config, set_guild_config
        action = action.lower().strip()
        cfg = await get_guild_config(0)
        entries = list(cfg.get("presence_rotation") or [])

        if action == "start":
            if not entries:
                await ctx.send("Add at least one entry first with `presence_add`.", ephemeral=True)
                return
            if interval_seconds is None or interval_seconds < 15:
                await ctx.send("Provide a duration of at least 15 seconds, for example: `presence_rotation start 60`.", ephemeral=True)
                return
            await set_guild_config(0, {"presence_rotation_enabled": True, "presence_rotation_interval": interval_seconds})
            self._wake_presence_rotation()
            await ctx.send(f"Presence rotation started: {len(entries)} entries, changing every {interval_seconds} seconds.")
        elif action == "stop":
            await set_guild_config(0, {"presence_rotation_enabled": False})
            self._wake_presence_rotation()
            await ctx.send("Presence rotation stopped.")
        elif action == "list":
            if not entries:
                await ctx.send("No rotation entries are configured.")
                return
            lines = [f"{i}. {item.get('presence_status', 'online')} | {item.get('presence_activity', 'playing')} | {item.get('presence_name', '')}" for i, item in enumerate(entries, start=1)]
            await ctx.send("**Presence rotation entries:**\n" + "\n".join(lines))
        elif action == "clear":
            await set_guild_config(0, {"presence_rotation": [], "presence_rotation_enabled": False, "presence_rotation_index": 0})
            self._wake_presence_rotation()
            await ctx.send("All presence rotation entries were removed.")
        elif action == "remove":
            if interval_seconds is None or not 1 <= interval_seconds <= len(entries):
                await ctx.send("Provide the entry number to remove, for example: `presence_rotation remove 2`.", ephemeral=True)
                return
            removed = entries.pop(interval_seconds - 1)
            await set_guild_config(0, {"presence_rotation": entries, "presence_rotation_index": 0})
            self._wake_presence_rotation()
            await ctx.send(f"Removed rotation presence: `{removed.get('presence_name', '')}`")
        else:
            await ctx.send("Usage: `presence_rotation start <seconds>`, `stop`, `list`, `remove <number>`, or `clear`.", ephemeral=True)

    async def _resolve_guild(self, ctx: commands.Context, guild_id: Optional[int]) -> Optional[discord.Guild]:
        if guild_id:
            return self.bot.get_guild(guild_id)
        if ctx.guild:
            return ctx.guild
        if self.bot.guilds:
            return self.bot.guilds[0]
        return None

    @commands.command(name="prefixless_grant", aliases=["plgrant", "plallow"])
    async def prefixless_grant(self, ctx: commands.Context, user: discord.User, guild_id: Optional[int] = None):
        """Grant a user permission to use prefix-less commands in a server (owner-only)."""
        if not await self._is_owner(ctx.author):
            await ctx.send("❌ You are not authorized to run this command.", ephemeral=True)
            return

        guild = await self._resolve_guild(ctx, guild_id)
        if not guild:
            await ctx.send("❌ Could not resolve server. Provide a valid server ID.", ephemeral=True)
            return

        from utils.db import get_connection
        async with get_connection() as conn:
            await conn.execute(
                "INSERT OR REPLACE INTO prefixless_permissions (guild_id, user_id) VALUES (?, ?)",
                (guild.id, user.id)
            )
            await conn.commit()

        await ctx.send(f"✅ Granted prefix-less command permission to {user.mention} in **{guild.name}**.")

    @commands.command(name="prefixless_revoke", aliases=["plrevoke", "pldeny"])
    async def prefixless_revoke(self, ctx: commands.Context, user: discord.User, guild_id: Optional[int] = None):
        """Revoke a user's permission to use prefix-less commands in a server (owner-only)."""
        if not await self._is_owner(ctx.author):
            await ctx.send("❌ You are not authorized to run this command.", ephemeral=True)
            return

        guild = await self._resolve_guild(ctx, guild_id)
        if not guild:
            await ctx.send("❌ Could not resolve server. Provide a valid server ID.", ephemeral=True)
            return

        from utils.db import get_connection
        async with get_connection() as conn:
            await conn.execute(
                "DELETE FROM prefixless_permissions WHERE guild_id = ? AND user_id = ?",
                (guild.id, user.id)
            )
            await conn.commit()

        await ctx.send(f"✅ Revoked prefix-less command permission from {user.mention} in **{guild.name}**.")

    @commands.command(name="prefixless_list", aliases=["pllist"])
    async def prefixless_list(self, ctx: commands.Context, guild_id: Optional[int] = None):
        """List all users with prefix-less command permissions in a server (owner-only)."""
        if not await self._is_owner(ctx.author):
            await ctx.send("❌ You are not authorized to run this command.", ephemeral=True)
            return

        guild = await self._resolve_guild(ctx, guild_id)
        if not guild:
            await ctx.send("❌ Could not resolve server. Provide a valid server ID.", ephemeral=True)
            return

        from utils.db import get_connection
        async with get_connection() as conn:
            cur = await conn.execute(
                "SELECT user_id FROM prefixless_permissions WHERE guild_id = ?",
                (guild.id,)
            )
            rows = await cur.fetchall()
            await cur.close()

        if not rows:
            await ctx.send(f"ℹ️ No users have prefix-less command permissions in **{guild.name}**.")
            return

        mentions = []
        for r in rows:
            user_id = r["user_id"]
            mentions.append(f"<@{user_id}> (`{user_id}`)")

        mentions_str = "\n".join(mentions)
        embed = discord.Embed(
            title=f"Prefix-less Permissions: {guild.name}",
            description=mentions_str,
            color=discord.Color.blue()
        )
        await ctx.send(embed=embed)

    async def _fetch_image_bytes(self, ctx: commands.Context, url_or_arg: Optional[str]) -> Optional[bytes]:
        """Retrieve image bytes from message attachment or URL.
        Returns None if reset/clear is specified.
        """
        if url_or_arg and url_or_arg.lower().strip() in ("reset", "clear", "remove", "none", "default"):
            return None

        if ctx.message and ctx.message.attachments:
            attachment = ctx.message.attachments[0]
            return await attachment.read()

        if url_or_arg and (url_or_arg.startswith("http://") or url_or_arg.startswith("https://")):
            async with aiohttp.ClientSession() as session:
                async with session.get(url_or_arg) as resp:
                    if resp.status == 200:
                        return await resp.read()

        return None

    @commands.command(name="server_avatar", aliases=["setserveravatar", "setserverpfp", "server_pfp"])
    async def server_avatar(self, ctx: commands.Context, image_url: Optional[str] = None, guild_id: Optional[int] = None):
        """Set or reset the bot's server-specific avatar PFP (owner-only). Use 'reset' to clear."""
        if not await self._is_owner(ctx.author):
            await ctx.send("❌ You are not authorized to run this command.", ephemeral=True)
            return

        guild = await self._resolve_guild(ctx, guild_id)
        if not guild:
            await ctx.send("❌ Could not resolve server. Provide a valid server ID.", ephemeral=True)
            return

        try:
            is_reset = image_url and image_url.lower().strip() in ("reset", "clear", "remove", "none", "default")
            if not is_reset and not (ctx.message and ctx.message.attachments) and not (image_url and (image_url.startswith("http://") or image_url.startswith("https://"))):
                await ctx.send("❌ Please attach an image or provide a valid image URL (or type `reset` to clear).", ephemeral=True)
                return

            image_bytes = await self._fetch_image_bytes(ctx, image_url)
            bot_member = guild.me or guild.get_member(self.bot.user.id)
            if not bot_member:
                bot_member = await guild.fetch_member(self.bot.user.id)

            await bot_member.edit(avatar=image_bytes)
            if image_bytes is None:
                await ctx.send(f"✅ Reset bot's server avatar to default in **{guild.name}**.")
            else:
                await ctx.send(f"✅ Updated bot's server avatar in **{guild.name}**.")
        except discord.HTTPException as e:
            logger.exception("Failed to set server avatar: %s", e)
            await ctx.send(f"❌ Failed to set server avatar: {e.text or e}", ephemeral=True)
        except Exception as e:
            logger.exception("Failed to set server avatar: %s", e)
            await ctx.send(f"❌ Error updating server avatar: {e}", ephemeral=True)

    @commands.command(name="server_banner", aliases=["setserverbanner"])
    async def server_banner(self, ctx: commands.Context, image_url: Optional[str] = None, guild_id: Optional[int] = None):
        """Set or reset the bot's server-specific banner (owner-only). Use 'reset' to clear."""
        if not await self._is_owner(ctx.author):
            await ctx.send("❌ You are not authorized to run this command.", ephemeral=True)
            return

        guild = await self._resolve_guild(ctx, guild_id)
        if not guild:
            await ctx.send("❌ Could not resolve server. Provide a valid server ID.", ephemeral=True)
            return

        try:
            is_reset = image_url and image_url.lower().strip() in ("reset", "clear", "remove", "none", "default")
            if not is_reset and not (ctx.message and ctx.message.attachments) and not (image_url and (image_url.startswith("http://") or image_url.startswith("https://"))):
                await ctx.send("❌ Please attach an image or provide a valid image URL (or type `reset` to clear).", ephemeral=True)
                return

            image_bytes = await self._fetch_image_bytes(ctx, image_url)
            bot_member = guild.me or guild.get_member(self.bot.user.id)
            if not bot_member:
                bot_member = await guild.fetch_member(self.bot.user.id)

            await bot_member.edit(banner=image_bytes)
            if image_bytes is None:
                await ctx.send(f"✅ Reset bot's server banner in **{guild.name}**.")
            else:
                await ctx.send(f"✅ Updated bot's server banner in **{guild.name}**.")
        except discord.HTTPException as e:
            logger.exception("Failed to set server banner: %s", e)
            await ctx.send(f"❌ Failed to set server banner: {e.text or e}", ephemeral=True)
        except Exception as e:
            logger.exception("Failed to set server banner: %s", e)
            await ctx.send(f"❌ Error updating server banner: {e}", ephemeral=True)

    @commands.command(name="global_avatar", aliases=["setglobalavatar", "setbotavatar"])
    async def global_avatar(self, ctx: commands.Context, image_url: Optional[str] = None):
        """Set or reset the bot's global account avatar across all servers (owner-only). Use 'reset' to clear."""
        if not await self._is_owner(ctx.author):
            await ctx.send("❌ You are not authorized to run this command.", ephemeral=True)
            return

        try:
            is_reset = image_url and image_url.lower().strip() in ("reset", "clear", "remove", "none", "default")
            if not is_reset and not (ctx.message and ctx.message.attachments) and not (image_url and (image_url.startswith("http://") or image_url.startswith("https://"))):
                await ctx.send("❌ Please attach an image or provide a valid image URL (or type `reset` to clear).", ephemeral=True)
                return

            image_bytes = await self._fetch_image_bytes(ctx, image_url)
            await self.bot.user.edit(avatar=image_bytes)
            if image_bytes is None:
                await ctx.send("✅ Reset bot's global avatar to default.")
            else:
                await ctx.send("✅ Updated bot's global avatar across all servers.")
        except discord.HTTPException as e:
            logger.exception("Failed to set global avatar: %s", e)
            await ctx.send(f"❌ Failed to set global avatar: {e.text or e}", ephemeral=True)
        except Exception as e:
            logger.exception("Failed to set global avatar: %s", e)
            await ctx.send(f"❌ Error updating global avatar: {e}", ephemeral=True)

    @commands.command(name="global_banner", aliases=["setglobalbanner", "setbotbanner"])
    async def global_banner(self, ctx: commands.Context, image_url: Optional[str] = None):
        """Set or reset the bot's global account banner across all servers (owner-only). Use 'reset' to clear."""
        if not await self._is_owner(ctx.author):
            await ctx.send("❌ You are not authorized to run this command.", ephemeral=True)
            return

        try:
            is_reset = image_url and image_url.lower().strip() in ("reset", "clear", "remove", "none", "default")
            if not is_reset and not (ctx.message and ctx.message.attachments) and not (image_url and (image_url.startswith("http://") or image_url.startswith("https://"))):
                await ctx.send("❌ Please attach an image or provide a valid image URL (or type `reset` to clear).", ephemeral=True)
                return

            image_bytes = await self._fetch_image_bytes(ctx, image_url)
            await self.bot.user.edit(banner=image_bytes)
            if image_bytes is None:
                await ctx.send("✅ Reset bot's global banner to default.")
            else:
                await ctx.send("✅ Updated bot's global banner across all servers.")
        except discord.HTTPException as e:
            logger.exception("Failed to set global banner: %s", e)
            await ctx.send(f"❌ Failed to set global banner: {e.text or e}", ephemeral=True)
        except Exception as e:
            logger.exception("Failed to set global banner: %s", e)
            await ctx.send(f"❌ Error updating global banner: {e}", ephemeral=True)

    @commands.command(name="server_about", aliases=["setserverabout", "server_bio", "setserverbio"])
    async def server_about(self, ctx: commands.Context, *, text: Optional[str] = None, guild_id: Optional[int] = None):
        """Set or reset the bot's server-specific 'About Me' bio (owner-only). Use 'reset' to clear."""
        if not await self._is_owner(ctx.author):
            await ctx.send("❌ You are not authorized to run this command.", ephemeral=True)
            return

        guild = await self._resolve_guild(ctx, guild_id)
        if not guild:
            await ctx.send("❌ Could not resolve server. Provide a valid server ID.", ephemeral=True)
            return

        if not text:
            await ctx.send("❌ Please provide text for the bot's 'About Me' bio (or type `reset` to clear).", ephemeral=True)
            return

        about_text = text.strip()
        is_reset = about_text.lower() in ("reset", "clear", "remove", "none", "default")
        new_bio = None if is_reset else about_text[:190]

        try:
            bot_member = guild.me or guild.get_member(self.bot.user.id)
            if not bot_member:
                bot_member = await guild.fetch_member(self.bot.user.id)
            await bot_member.edit(bio=new_bio)
            if is_reset:
                await ctx.send(f"✅ Reset bot's server 'About Me' bio in **{guild.name}**.")
            else:
                await ctx.send(f"✅ Updated bot's server 'About Me' bio in **{guild.name}**:\n>>> {new_bio}")
        except discord.HTTPException as e:
            logger.exception("Failed to set server bio: %s", e)
            await ctx.send(f"❌ Failed to set server bio: {e.text or e}", ephemeral=True)
        except Exception as e:
            logger.exception("Failed to set server bio: %s", e)
            await ctx.send(f"❌ Error updating server bio: {e}", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(DebugCog(bot))
