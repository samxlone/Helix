import logging
from typing import Optional
import discord
from discord import app_commands, Interaction
from discord.ext import commands

from services.music.queue import GuildQueue
from services.music.resolver import resolve
from services.music.ui import build_now_playing
from services.music.player import Player
from services.music.voice import connect_to_channel

logger = logging.getLogger(__name__)


def format_track_link(title: str, url: str) -> str:
    title_str = (title or "Unknown Track").strip()
    url_str = (url or "").strip()
    if title_str.startswith("http://") or title_str.startswith("https://") or title_str == url_str:
        return f"**{title_str}**"
    safe_title = title_str.replace("[", "\\[").replace("]", "\\]")
    if url_str:
        return f"**[{safe_title}]({url_str})**"
    return f"**{safe_title}**"


class MusicCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # simple in-memory players map: guild_id -> Player
        self.players: dict[int, Player] = {}
        # store connected VoiceClients per guild
        self.voice_clients: dict[int, object] = {}

    def _ensure_player(self, guild_id: int) -> Player:
        p = self.players.get(guild_id)
        if not p:
            p = Player(guild_id)
            self.players[guild_id] = p
        return p

    async def _connect_to_voice(self, ctx: commands.Context):
        """Helper to check voice client connection state and connect/move to the user's voice channel."""
        vc = self.voice_clients.get(ctx.guild.id)
        if vc and hasattr(vc, "is_connected") and vc.is_connected():
            return vc, None

        # fallback to discord.py's native voice client state tracking
        vc = ctx.guild.voice_client
        if vc and hasattr(vc, "is_connected") and vc.is_connected():
            self.voice_clients[ctx.guild.id] = vc
            return vc, None

        if not ctx.author.voice or not ctx.author.voice.channel:
            return None, "You are not connected to a voice channel."
        channel = ctx.author.voice.channel

        # Basic permission checks for the bot
        bot_member = ctx.guild.me or ctx.guild.get_member(self.bot.user.id)
        try:
            perms = channel.permissions_for(bot_member) if bot_member else None
            if perms and not perms.connect:
                return None, "I don't have permission to connect to that voice channel."
            if perms and not perms.speak:
                return None, "I don't have permission to speak in that voice channel."
        except Exception:
            pass

        try:
            # warn if opus/voice support is missing
            try:
                import discord as _discord
                if not getattr(_discord, "opus", None) or not _discord.opus.is_loaded():
                    logger.warning("Opus not loaded: voice may not work. Ensure PyNaCl is installed and opus is available.")
            except Exception:
                logger.debug("Failed to check discord.opus status")

            vc = await connect_to_channel(channel)
            self.voice_clients[ctx.guild.id] = vc
            player = self._ensure_player(ctx.guild.id)
            player.volume = 1.0  # Reset volume to 100% on connection
            return vc, None
        except Exception as exc:
            logger.exception("Failed to connect to voice channel: %s", exc)
            msg = "Failed to connect to voice channel."
            msg += "\nPossible causes: missing PyNaCl (pip install PyNaCl), ffmpeg not on PATH, or missing Connect/Speak permissions."
            msg += f"\nError: {exc}"
            return None, msg

    @commands.hybrid_command(name="join")
    @commands.guild_only()
    async def join(self, ctx: commands.Context):
        """Join your voice channel"""
        await ctx.defer()
        vc, err_msg = await self._connect_to_voice(ctx)
        if err_msg:
            await ctx.send(err_msg, ephemeral=True)
            return
        await ctx.send(f"Connected to {ctx.author.voice.channel.name}")

    @commands.hybrid_command(name="leave")
    @commands.guild_only()
    async def leave(self, ctx: commands.Context):
        """Leave the voice channel and stop playback"""
        p = self._ensure_player(ctx.guild.id)
        p.volume = 1.0  # Reset volume to 100% on leave
        vc = self.voice_clients.get(ctx.guild.id)

        # Clear queue and stop player loop tasks
        p.queue.clear()
        p.queue.current = None


        if vc:
            try:
                if vc.is_playing() or vc.is_paused():
                    vc.stop()
            except Exception:
                pass

        p.stop_voice_playback()
        p.stop()

        try:
            if vc:
                await vc.disconnect()
                self.voice_clients.pop(ctx.guild.id, None)
            await ctx.send("Disconnected. 👋")
        except Exception:
            await ctx.send("Failed to disconnect.", ephemeral=True)

    @commands.hybrid_command(name="play", aliases=["p"])
    @commands.guild_only()
    async def play(self, ctx: commands.Context, *, query: str):
        """Play a song or add it to the queue (search or URL)"""
        await ctx.defer()
        vc, err = await self._connect_to_voice(ctx)
        if err:
            await ctx.send(err, ephemeral=True)
            return

        p = self._ensure_player(ctx.guild.id)
        p.text_channel = ctx.channel

        track = await resolve(query, ctx.author.id)
        if not track:
            await ctx.send("Could not find or resolve track.", ephemeral=True)
            return

        pos = p.get_queue().enqueue(track)

        # start voice playback
        logger.info("VoiceClient connected for guild %s, starting voice playback", ctx.guild.id)
        p.start_voice_playback(vc)
        await ctx.send(f"Queued: {track.title} (position {pos})")

    @commands.hybrid_command(name="pause")
    @commands.guild_only()
    async def pause(self, ctx: commands.Context):
        """Pause the currently playing audio"""
        vc = self.voice_clients.get(ctx.guild.id)
        if not vc:
            await ctx.send("I am not connected to a voice channel.", ephemeral=True)
            return

        if not vc.is_playing():
            await ctx.send("Nothing is currently playing.", ephemeral=True)
            return

        if vc.is_paused():
            await ctx.send("Audio is already paused.", ephemeral=True)
            return

        try:
            vc.pause()
            await ctx.send("Paused the audio. ⏸️")
        except Exception as exc:
            logger.exception("Failed to pause audio: %s", exc)
            await ctx.send("Failed to pause the audio.", ephemeral=True)

    @commands.hybrid_command(name="resume")
    @commands.guild_only()
    async def resume(self, ctx: commands.Context):
        """Resume the paused audio"""
        vc = self.voice_clients.get(ctx.guild.id)
        if not vc:
            await ctx.send("I am not connected to a voice channel.", ephemeral=True)
            return

        if not vc.is_paused():
            await ctx.send("Audio is not paused.", ephemeral=True)
            return

        try:
            vc.resume()
            await ctx.send("Resumed the audio. ▶️")
        except Exception as exc:
            logger.exception("Failed to resume audio: %s", exc)
            await ctx.send("Failed to resume the audio.", ephemeral=True)

    @commands.hybrid_command(name="nowplaying")
    @commands.guild_only()
    async def nowplaying(self, ctx: commands.Context):
        """Show the currently playing track"""
        p = self._ensure_player(ctx.guild.id)
        q = p.get_queue()
        track = q.now_playing()
        
        if not track:
            await ctx.send("Nothing is currently playing. 🎵", ephemeral=True)
            return

        import discord
        embed = discord.Embed(
            title="Now Playing 🎶",
            description=format_track_link(track.title, track.url),
            color=discord.Color.blurple()
        )
        if track.author:
            embed.add_field(name="Uploader/Artist", value=track.author, inline=True)
        if track.duration:
            mins, secs = divmod(track.duration, 60)
            hours, mins = divmod(mins, 60)
            duration_str = f"{hours:02d}:{mins:02d}:{secs:02d}" if hours else f"{mins:02d}:{secs:02d}"
            embed.add_field(name="Duration", value=duration_str, inline=True)
        if track.provider:
            embed.add_field(name="Source", value=track.provider.capitalize(), inline=True)
        if track.thumbnail:
            embed.set_thumbnail(url=track.thumbnail)
            
        owner = self.bot.owner_user if hasattr(self.bot, "owner_user") else None
        if owner:
            embed.set_footer(text=f"Created by {owner.name} • Owned by {owner.name}", icon_url=owner.avatar.url if owner.avatar else None)
        else:
            embed.set_footer(text="Owned by Bot Owner")
            
        await ctx.send(embed=embed, view=NowPlayingView(self.bot, ctx.guild.id, self))

    @commands.hybrid_command(name="np")
    @commands.guild_only()
    async def np(self, ctx: commands.Context):
        """Shortcut to show the currently playing track"""
        await self.nowplaying(ctx)

    @commands.hybrid_command(name="stop")
    @commands.guild_only()
    async def stop(self, ctx: commands.Context):
        """Stop the player and clear the queue"""
        p = self._ensure_player(ctx.guild.id)
        vc = self.voice_clients.get(ctx.guild.id)
        
        # Clear queue
        p.queue.clear()
        p.queue.current = None
        
        # Stop voice client playing source
        if vc:
            try:
                if vc.is_playing():
                    vc.stop()
            except Exception:
                pass
        
        # Stop the player tasks/loops
        p.stop_voice_playback()
        p.stop()
        
        await ctx.send("Stopped playback and cleared the queue. ⏹️")

    @commands.hybrid_command(name="queue", aliases=["q"])
    @commands.guild_only()
    async def queue(self, ctx: commands.Context):
        """View the current music queue"""
        p = self._ensure_player(ctx.guild.id)
        q = p.get_queue()
        current_track = q.now_playing()
        upcoming = q.get_queue()

        if not current_track and not upcoming:
            await ctx.send("The music queue is currently empty. 🎵")
            return

        def format_time(seconds: int) -> str:
            if seconds is None or seconds < 0:
                return "0:00"
            mins, secs = divmod(int(seconds), 60)
            hours, mins = divmod(mins, 60)
            if hours > 0:
                return f"{hours:02d}:{mins:02d}:{secs:02d}"
            return f"{mins:02d}:{secs:02d}"

        embed = discord.Embed(
            title=f"🎵 Music Queue — {ctx.guild.name}",
            color=discord.Color.dark_teal(),
        )

        # 1. Now Playing track
        if current_track:
            req_mention = f"<@{current_track.requester}>" if current_track.requester else "Unknown"
            duration_str = format_time(current_track.duration)
            embed.description = (
                f"**Now Playing:**\n"
                f"➡ {format_track_link(current_track.title, current_track.url)}\n"
                f"• *Requested by:* {req_mention} | *Duration:* `{duration_str}`\n\n"
                f"**Up Next:**\n"
            )
        else:
            embed.description = "**Now Playing:**\n*Nothing is currently playing.*\n\n**Up Next:**\n"

        # 2. Upcoming tracks
        if upcoming:
            upcoming_lines = []
            for idx, track in enumerate(upcoming[:10], 1):
                req_mention = f"<@{track.requester}>" if track.requester else "Unknown"
                duration_str = format_time(track.duration)
                upcoming_lines.append(
                    f"`{idx:02d}.` {format_track_link(track.title, track.url)}\n"
                    f"     *Requested by:* {req_mention} | *Duration:* `{duration_str}`"
                )
            embed.description += "\n".join(upcoming_lines)

            if len(upcoming) > 10:
                embed.description += f"\n\n*...and {len(upcoming) - 10} more track(s)*"
        else:
            embed.description += "*No upcoming songs in the queue.*"

        # 3. Status/Metadata footer and fields
        loop_status = "Off"
        if q.loop_mode == "song":
            loop_status = "🔂 Single Track"
        elif q.loop_mode == "queue":
            loop_status = "🔁 Entire Queue"

        autoplay_status = "Enabled 📻" if getattr(p, "autoplay_enabled", False) else "Disabled 🔇"

        total_duration = sum((t.duration or 0) for t in upcoming)
        if current_track:
            total_duration += (current_track.duration or 0)
        total_duration_str = format_time(total_duration)

        embed.add_field(name="Tracks in Queue", value=f"`{len(upcoming) + (1 if current_track else 0)}`", inline=True)
        embed.add_field(name="Total Duration", value=f"`{total_duration_str}`", inline=True)
        embed.add_field(name="Loop Mode", value=f"`{loop_status}`", inline=True)
        embed.add_field(name="Autoplay", value=f"`{autoplay_status}`", inline=True)

        owner = self.bot.owner_user if hasattr(self.bot, "owner_user") else None
        owner_text = f" | Created & Owned by {owner.name}" if owner else ""
        embed.set_footer(text=f"Server: {ctx.guild.name}{owner_text}")

        await ctx.send(embed=embed)

    @commands.hybrid_command(name="skip")
    @commands.guild_only()
    async def skip(self, ctx: commands.Context):
        """Skip the current track"""
        p = self._ensure_player(ctx.guild.id)
        vc = self.voice_clients.get(ctx.guild.id)
        
        # Look at the upcoming queue to see what will play next (without advancing yet)
        upcoming = p.get_queue().get_queue()
        nxt = upcoming[0] if upcoming else None
        
        # Stop current playback on the voice client to trigger the next track in the voice loop finally block
        if vc:
            try:
                if vc.is_playing() or vc.is_paused():
                    vc.stop()
            except Exception:
                pass
                
        if not nxt:
            if getattr(p, "autoplay_enabled", False):
                await ctx.send("Skipped current track. Autoplay is fetching a recommended song... ⏭️")
            else:
                await ctx.send("Skipped current track. No more tracks in queue. ⏭️")
            return
        await ctx.send(f"Skipped! Now playing: {nxt.title} ⏭️")

    @commands.hybrid_command(name="autoplay")
    @commands.guild_only()
    async def autoplay(self, ctx: commands.Context, status: str = None):
        """Enable or disable autoplaying similar songs when the queue ends"""
        p = self._ensure_player(ctx.guild.id)
        
        if status:
            status = status.lower()
            if status in ("enable", "enabled", "on", "true", "yes", "1"):
                p.autoplay_enabled = True
            elif status in ("disable", "disabled", "off", "false", "no", "0"):
                p.autoplay_enabled = False
            else:
                await ctx.send("Invalid status. Choose: `on` or `off` (or omit to toggle).", ephemeral=True)
                return
        else:
            p.autoplay_enabled = not p.autoplay_enabled
            
        status_str = "enabled" if p.autoplay_enabled else "disabled"
        await ctx.send(f"Autoplay has been **{status_str}**. 📻")

    @commands.hybrid_command(name="loop")
    @commands.guild_only()
    async def loop(self, ctx: commands.Context, mode: str = None):
        """Set the loop mode: off, song, or queue. If mode is omitted, cycles through them."""
        p = self._ensure_player(ctx.guild.id)
        q = p.get_queue()
        
        valid_modes = ["off", "song", "queue"]
        if mode:
            mode = mode.lower()
            if mode not in valid_modes:
                await ctx.send("Invalid loop mode. Choose from: `off`, `song`, or `queue`.", ephemeral=True)
                return
            q.set_loop(mode)
        else:
            current_mode = q.loop_mode
            next_idx = (valid_modes.index(current_mode) + 1) % len(valid_modes)
            mode = valid_modes[next_idx]
            q.set_loop(mode)
            
        emoji = "🔁" if mode == "queue" else ("🔂" if mode == "song" else "❌")
        await ctx.send(f"Loop mode has been set to **{mode}** {emoji}.")

    @commands.hybrid_command(name="seek")
    @commands.guild_only()
    async def seek(self, ctx: commands.Context, position: str):
        """Seek to a specific timestamp in seconds (e.g. 120 or 120s)"""
        p = self._ensure_player(ctx.guild.id)
        vc = self.voice_clients.get(ctx.guild.id)
        
        if not vc or not vc.is_playing() and not vc.is_paused():
            await ctx.send("Nothing is currently playing.", ephemeral=True)
            return
            
        clean_pos = position.lower().replace("s", "").strip()
        try:
            seconds = int(clean_pos)
        except ValueError:
            await ctx.send("Invalid position format. Use seconds (e.g. `120` or `120s`).", ephemeral=True)
            return
            
        if seconds < 0:
            await ctx.send("Position cannot be negative.", ephemeral=True)
            return
            
        track = p.queue.now_playing()
        if not track:
            await ctx.send("Nothing is currently playing.", ephemeral=True)
            return
            
        if track.duration and seconds > track.duration:
            await ctx.send(f"Position cannot exceed song duration ({track.duration}s).", ephemeral=True)
            return

        p.seeking = True
        p.seek_time = seconds
        vc.stop()
        
        await ctx.send(f"Seeking to **{seconds}s**... 🔍")

    @commands.hybrid_command(name="shuffle")
    @commands.guild_only()
    async def shuffle(self, ctx: commands.Context):
        """Shuffle the upcoming tracks in the queue"""
        p = self._ensure_player(ctx.guild.id)
        q = p.get_queue()
        if not q.upcoming:
            await ctx.send("The queue is currently empty.", ephemeral=True)
            return
        q.shuffle()
        await ctx.send("Shuffled the queue! 🔀")

    @commands.hybrid_command(name="clearqueue", aliases=["clear"])
    @commands.guild_only()
    async def clearqueue(self, ctx: commands.Context):
        """Clear all upcoming tracks from the queue"""
        p = self._ensure_player(ctx.guild.id)
        q = p.get_queue()
        q.clear()
        await ctx.send("Cleared all upcoming tracks from the queue! 🗑️")

    @commands.hybrid_command(name="remove")
    @commands.guild_only()
    async def remove(self, ctx: commands.Context, position: int):
        """Remove a track from the queue by its position (1-based index)"""
        p = self._ensure_player(ctx.guild.id)
        q = p.get_queue()
        
        # position is 1-based, we convert it to 0-based index
        idx = position - 1
        removed = q.remove_at(idx)
        if removed:
            await ctx.send(f"Removed track **{removed.title}** from the queue! ❌")
        else:
            await ctx.send(f"Invalid position. The queue currently has {len(q.upcoming)} tracks.", ephemeral=True)

    @commands.hybrid_command(name="lyrics")
    @commands.guild_only()
    async def lyrics(self, ctx: commands.Context, query: str = None):
        """Get the lyrics for the current song or a search query"""
        await ctx.defer()
        
        from services.music.lyrics import fetch_lyrics, clean_song_info
        
        target_title = None
        target_author = None
        
        if query:
            target_title = query
        else:
            p = self._ensure_player(ctx.guild.id)
            track = p.queue.now_playing()
            if not track:
                await ctx.send("Nothing is currently playing. Provide a search query! E.g. `!lyrics Shape of You`")
                return
            target_title = track.title
            target_author = track.author
            
        lyrics_text = await fetch_lyrics(target_title, target_author)
        if not lyrics_text:
            cleaned_artist, cleaned_song = clean_song_info(target_title, target_author)
            query_name = f"{cleaned_artist} - {cleaned_song}" if cleaned_artist else cleaned_song
            await ctx.send(f"Could not find lyrics for **{query_name}**.")
            return
            
        cleaned_artist, cleaned_song = clean_song_info(target_title, target_author)
        song_display_name = f"{cleaned_artist} - {cleaned_song}" if cleaned_artist else cleaned_song
        
        pages = chunk_text(lyrics_text, 1500)
        view = LyricsView(self.bot, pages, song_display_name) if len(pages) > 1 else None
        
        embed = discord.Embed(
            title=f"Lyrics for {song_display_name} 🎤",
            description=pages[0],
            color=discord.Color.blurple()
        )
        owner = self.bot.owner_user if hasattr(self.bot, "owner_user") else None
        if owner:
            embed.set_footer(text=f"Page 1 of {len(pages)} • Created by {owner.name}" if len(pages) > 1 else f"Created by {owner.name}")
        else:
            embed.set_footer(text=f"Page 1 of {len(pages)}" if len(pages) > 1 else "Owned by Bot Owner")
            
        await ctx.send(embed=embed, view=view)

    async def _is_owner(self, user):
        from config import config as app_config
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

    @commands.hybrid_command(name="volume", aliases=["vol"])
    @commands.guild_only()
    async def volume(self, ctx: commands.Context, volume: Optional[int] = None):
        """Set or show voice volume (Max 100% for regular users, unrestricted for Bot Owner)."""
        player = self._ensure_player(ctx.guild.id)

        if volume is None:
            current_vol = int(player.volume * 100)
            await ctx.send(f"🔊 Current volume is **{current_vol}%**.")
            return

        if volume < 0:
            await ctx.send("❌ Volume must be 0% or higher.", ephemeral=True)
            return

        is_owner = await self._is_owner(ctx.author)
        if volume > 100 and not is_owner:
            await ctx.send("❌ Regular users can set volume up to **100%**. Only the Bot Owner can set unrestricted volume.", ephemeral=True)
            return

        player.volume = volume / 100.0

        # Update dynamically on active voice source if playing
        vc = self.voice_clients.get(ctx.guild.id) or getattr(ctx.guild, "voice_client", None)

        if vc and hasattr(vc, "source") and vc.source:
            if hasattr(vc.source, "volume"):
                vc.source.volume = player.volume

        await ctx.send(f"🔊 Volume set to **{volume}%**.")




class NowPlayingView(discord.ui.View):
    def __init__(self, bot, guild_id, cog):
        super().__init__(timeout=120)  # Active for 2 minutes
        self.bot = bot
        self.guild_id = guild_id
        self.cog = cog
        
        # Adjust Autoplay button style based on current state
        p = self.cog._ensure_player(self.guild_id)
        self.autoplay_button.style = discord.ButtonStyle.success if p.autoplay_enabled else discord.ButtonStyle.secondary

    @discord.ui.button(label="Pause", emoji="⏸️", style=discord.ButtonStyle.primary)
    async def pause_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = self.cog.voice_clients.get(self.guild_id)
        if not vc:
            await interaction.response.send_message("I am not connected to a voice channel.", ephemeral=True)
            return
        if vc.is_paused():
            await interaction.response.send_message("Audio is already paused.", ephemeral=True)
            return
        if not vc.is_playing():
            await interaction.response.send_message("Nothing is currently playing.", ephemeral=True)
            return
        try:
            vc.pause()
            await interaction.response.send_message(f"{interaction.user.mention} paused the audio. ⏸️")
        except Exception:
            await interaction.response.send_message("Failed to pause the audio.", ephemeral=True)

    @discord.ui.button(label="Resume", emoji="▶️", style=discord.ButtonStyle.success)
    async def resume_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = self.cog.voice_clients.get(self.guild_id)
        if not vc:
            await interaction.response.send_message("I am not connected to a voice channel.", ephemeral=True)
            return
        if not vc.is_paused():
            await interaction.response.send_message("Audio is not paused.", ephemeral=True)
            return
        try:
            vc.resume()
            await interaction.response.send_message(f"{interaction.user.mention} resumed the audio. ▶️")
        except Exception:
            await interaction.response.send_message("Failed to resume the audio.", ephemeral=True)

    @discord.ui.button(label="Queue", emoji="📋", style=discord.ButtonStyle.secondary)
    async def queue_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        p = self.cog._ensure_player(self.guild_id)
        q = p.get_queue()
        items = q.get_queue()
        if not items:
            await interaction.response.send_message("The queue is currently empty.", ephemeral=True)
            return
            
        lines = []
        for idx, t in enumerate(items[:10], start=1):
            req = f"<@{t.requester}>" if t.requester else "Autoplay 📻"
            lines.append(f"**{idx}.** {t.title} — {req}")
        
        queue_text = "\n".join(lines)
        if len(items) > 10:
            queue_text += f"\n*...and {len(items) - 10} more tracks.*"
            
        embed = discord.Embed(
            title="Current Queue 📋",
            description=queue_text,
            color=discord.Color.blurple()
        )
        owner = self.bot.owner_user if hasattr(self.bot, "owner_user") else None
        if owner:
            embed.set_footer(text=f"Created by {owner.name} • Owned by {owner.name}", icon_url=owner.avatar.url if owner.avatar else None)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Autoplay", emoji="📻", style=discord.ButtonStyle.secondary)
    async def autoplay_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        p = self.cog._ensure_player(self.guild_id)
        p.autoplay_enabled = not p.autoplay_enabled
        status = "enabled" if p.autoplay_enabled else "disabled"
        button.style = discord.ButtonStyle.success if p.autoplay_enabled else discord.ButtonStyle.secondary
        await interaction.response.edit_message(view=self)
        await interaction.followup.send(f"Autoplay has been **{status}** by {interaction.user.mention}. 📻", ephemeral=True)

    @discord.ui.button(label="Equalizer", emoji="🎛️", style=discord.ButtonStyle.danger)
    async def equalizer_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = EqualizerSelectView(self.bot, self.guild_id, self.cog)
        await interaction.response.send_message("Select an Equalizer preset. New preset applies to the next songs played! 🎛️", view=view, ephemeral=True)


class EqualizerSelectView(discord.ui.View):
    def __init__(self, bot, guild_id, cog):
        super().__init__(timeout=60)
        self.add_item(EqualizerSelect(bot, guild_id, cog))


class EqualizerSelect(discord.ui.Select):
    def __init__(self, bot, guild_id, cog):
        self.bot = bot
        self.guild_id = guild_id
        self.cog = cog
        
        options = [
            discord.SelectOption(label="Flat (Off)", description="No audio filters applied.", emoji="❌", value="flat"),
            discord.SelectOption(label="Bass Boost", description="Boosts low-frequency bass sounds.", emoji="🔊", value="bassboost"),
            discord.SelectOption(label="Vocal Boost", description="Highlights mid-range vocal frequencies.", emoji="🎤", value="vocalboost"),
            discord.SelectOption(label="Lo-Fi", description="Applies a lowpass filter for a chill lo-fi vibe.", emoji="🌌", value="lofi")
        ]
        super().__init__(placeholder="Choose an Equalizer preset...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        p = self.cog._ensure_player(self.guild_id)
        choice = self.values[0]
        
        presets = {
            "flat": "-vn",
            "bassboost": "-vn -af equalizer=f=60:width_type=h:w=50:g=10",
            "vocalboost": "-vn -af equalizer=f=1000:width_type=h:w=1000:g=5",
            "lofi": "-vn -af lowpass=f=3000"
        }
        
        p.eq_preset_name = choice
        p.eq_option = presets.get(choice, "-vn")
        vc = self.cog.voice_clients.get(self.guild_id)
        restarted = p.restart_current_track(vc)
        message = f"Equalizer set to **{choice.capitalize()}**!"
        if restarted:
            message += " Applied to the current track now. 🎛️"
        else:
            message += " It will apply when playback starts. 🎛️"
        await interaction.response.send_message(message, ephemeral=True)


class LyricsView(discord.ui.View):
    def __init__(self, bot, pages: list[str], title: str):
        super().__init__(timeout=180)  # Active for 3 minutes
        self.bot = bot
        self.pages = pages
        self.title = title
        self.current_page = 0

    def make_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title=f"Lyrics for {self.title} 🎤",
            description=self.pages[self.current_page],
            color=discord.Color.blurple()
        )
        owner = self.bot.owner_user if hasattr(self.bot, "owner_user") else None
        if owner:
            embed.set_footer(text=f"Page {self.current_page + 1} of {len(self.pages)} • Created by {owner.name}")
        else:
            embed.set_footer(text=f"Page {self.current_page + 1} of {len(self.pages)}")
        return embed

    @discord.ui.button(label="Back", emoji="◀️", style=discord.ButtonStyle.primary)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
            await interaction.response.edit_message(embed=self.make_embed(), view=self)
        else:
            await interaction.response.send_message("You are already on the first page.", ephemeral=True)

    @discord.ui.button(label="Next", emoji="▶️", style=discord.ButtonStyle.primary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < len(self.pages) - 1:
            self.current_page += 1
            await interaction.response.edit_message(embed=self.make_embed(), view=self)
        else:
            await interaction.response.send_message("You are already on the last page.", ephemeral=True)


def chunk_text(text: str, max_chars: int = 1500) -> list[str]:
    lines = text.split("\n")
    chunks = []
    current_chunk = []
    current_len = 0
    for line in lines:
        if current_len + len(line) + 1 > max_chars:
            chunks.append("\n".join(current_chunk))
            current_chunk = [line]
            current_len = len(line)
        else:
            current_chunk.append(line)
            current_len += len(line) + 1
    if current_chunk:
        chunks.append("\n".join(current_chunk))
    return chunks


async def setup(bot: commands.Bot):
    await bot.add_cog(MusicCog(bot))
