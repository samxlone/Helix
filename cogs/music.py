import logging
import math
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


def format_track_link(title: str, url: str = "") -> str:
    """Format track title cleanly in bold without blue hyperlinks or backslash escaping."""
    title_str = (title or "Unknown Track").strip().replace('\\', '')
    return f"**{title_str}**"



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
            vc = await connect_to_channel(channel)
            self.voice_clients[ctx.guild.id] = vc
            player = self._ensure_player(ctx.guild.id)
            return vc, None
        except Exception as exc:
            logger.exception("Failed to connect to voice channel: %s", exc)
            msg = "Failed to connect to voice channel."
            msg += "\nPossible causes: missing PyNaCl (pip install PyNaCl), ffmpeg not on PATH, or missing Connect/Speak permissions."
            msg += f"\nError: {exc}"
            return None, msg



    @commands.command(name="join")
    @commands.guild_only()
    async def join(self, ctx: commands.Context):
        """Join your voice channel"""
        await ctx.defer()
        vc, err_msg = await self._connect_to_voice(ctx)
        if err_msg:
            await ctx.send(err_msg, ephemeral=True)
            return
        await ctx.send(f"Connected to {ctx.author.voice.channel.name}")

    @commands.command(name="leave")
    @commands.guild_only()
    async def leave(self, ctx: commands.Context):

        """Leave the voice channel and stop playback"""
        p = self._ensure_player(ctx.guild.id)
        p.volume = 1.0  # Reset volume to 100% on leave
        p.reset_eq()    # Reset EQ preset back to normal (flat) on leave
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

        res = await resolve(query, ctx.author.id)
        if not res:
            await ctx.send("Could not find or resolve track.", ephemeral=True)
            return

        from services.music.ui import format_time
        was_playing = (vc is not None and vc.is_playing()) or (p.get_queue().current is not None)

        if isinstance(res, list):
            first_pos = None
            for t in res:
                pos = p.get_queue().enqueue(t)
                if first_pos is None:
                    first_pos = pos
            if not was_playing:
                p.suppress_first_track_msg = True
            p.start_voice_playback(vc)

            first_track = res[0] if res else None
            first_title = first_track.title.replace('\\', '') if first_track else "Playlist"
            dur_str = f"( {format_time(first_track.duration)} ) " if (first_track and first_track.duration) else ""

            if not was_playing:
                if len(res) == 1:
                    await ctx.send(f"🎶 **{first_title}** started playing {dur_str}")
                else:
                    await ctx.send(f"🎶 **{first_title}** and **{len(res) - 1}** tracks added to the queue {dur_str}- starting at position **1**")
            else:
                await ctx.send(f"🎶 **{first_title}** and **{len(res) - 1}** tracks added to the queue {dur_str}- starting at position **{first_pos}**")
        else:
            if not was_playing:
                p.suppress_first_track_msg = True
            pos = p.get_queue().enqueue(res)
            p.start_voice_playback(vc)

            clean_title = res.title.replace('\\', '')
            dur_str = f"( {format_time(res.duration)} ) " if res.duration else ""

            if not was_playing:
                await ctx.send(f"🎶 **{clean_title}** started playing {dur_str}")
            else:
                await ctx.send(f"🎶 **{clean_title}** added to the queue {dur_str}- at position **{pos}**")


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

        from utils.embed_utils import HELIX_COLOR, set_owner_footer
        embed = discord.Embed(
            title="Now Playing",
            description=f"### {format_track_link(track.title, track.url)}",
            color=HELIX_COLOR
        )
        
        info_bits = []
        if track.author:
            info_bits.append(f"👤 `{track.author}`")
        if track.duration:
            mins, secs = divmod(track.duration, 60)
            hours, mins = divmod(mins, 60)
            dur_str = f"{hours:02d}:{mins:02d}:{secs:02d}" if hours else f"{mins:02d}:{secs:02d}"
            info_bits.append(f"⏱️ `{dur_str}`")
        if track.provider:
            info_bits.append(f"🎧 `{track.provider.capitalize()}`")

        req_text = f"<@{track.requester}>" if track.requester else "*Autoplay Recommendation*"
        
        meta_desc = f"> {' • '.join(info_bits)}\n> 📻 **Requested By:** {req_text}"
        embed.add_field(name="Track Information", value=meta_desc, inline=False)

        if track.thumbnail:
            embed.set_thumbnail(url=track.thumbnail)
            
        set_owner_footer(embed, self.bot, extra_text="Lossless Audio Engine")
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
        """View the current music queue with interactive pagination buttons"""
        p = self._ensure_player(ctx.guild.id)
        q = p.get_queue()
        current_track = q.now_playing()
        upcoming = q.get_queue()

        if not current_track and not upcoming:
            await ctx.send("The music queue is currently empty. 🎵")
            return

        paginator = QueuePaginatorView(self.bot, ctx.guild.id, self, current_track, upcoming)
        await ctx.send(embed=paginator.make_embed(), view=paginator)


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
        from utils.embed_utils import set_owner_footer
        set_owner_footer(embed, self.bot, extra_text=f"Page 1 of {len(pages)}" if len(pages) > 1 else "")
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

        new_vol_float = volume / 100.0
        player.volume = new_vol_float

        # Update dynamically on active voice source if playing
        vc = self.voice_clients.get(ctx.guild.id) or getattr(ctx.guild, "voice_client", None)
        player.set_volume(new_vol_float, vc)

        if vc and hasattr(vc, "source") and vc.source:
            try:
                if hasattr(vc.source, "volume"):
                    vc.source.volume = new_vol_float
                elif hasattr(vc.source, "original") and hasattr(vc.source.original, "volume"):
                    vc.source.original.volume = new_vol_float
            except Exception as e:
                logger.warning("Could not set volume on voice source: %s", e)

        await ctx.send(f"🔊 Volume set to **{volume}%**.")

    @commands.hybrid_command(name="247", aliases=["stay"])
    @commands.guild_only()
    async def mode_247(self, ctx: commands.Context):
        """Toggle 24/7 Radio Mode (keeps Helix connected to the voice channel 24/7)"""
        p = self._ensure_player(ctx.guild.id)
        p.is_247 = not getattr(p, "is_247", False)
        status = "ENABLED 📻" if p.is_247 else "DISABLED 🔇"

        embed = discord.Embed(
            title=f"📻 24/7 Radio Mode — {status}",
            description=(
                f"24/7 Radio Mode is now **{status}** for **{ctx.guild.name}**.\n\n"
                + ("Helix will remain in your voice channel 24/7!" if p.is_247 else "Helix will leave the voice channel when playback finishes.")
            ),
            color=discord.Color.from_rgb(88, 101, 242) if p.is_247 else discord.Color.dark_grey(),
        )
        from utils.embed_utils import set_owner_footer
        set_owner_footer(embed, self.bot, extra_text=f"💎 HELIX MUSIC ENGINE • {ctx.guild.name}")
        await ctx.send(embed=embed)



    @commands.hybrid_command(name="karaoke")
    @commands.guild_only()
    async def karaoke(self, ctx: commands.Context):
        """Toggle Karaoke / Vocal Remover audio filter for singing along"""
        p = self._ensure_player(ctx.guild.id)
        current_preset = getattr(p, "eq_preset_name", "flat")

        if current_preset == "karaoke":
            p.eq_preset_name = "flat"
            p.eq_option = "-vn"
            msg = "🎤 Karaoke filter **DISABLED**. Restored standard stereo audio."
        else:
            p.eq_preset_name = "karaoke"
            p.eq_option = "-vn -af pan=stereo|c0=c0-c1|c1=c1-c0"
            msg = "🎤 Karaoke filter **ENABLED**. Center vocals muted for singing along!"

        vc = self.voice_clients.get(ctx.guild.id)
        restarted = p.restart_current_track(vc)
        if restarted:
            msg += " Filter applied to current track."
        await ctx.send(msg)





class NowPlayingView(discord.ui.View):
    def __init__(self, bot, guild_id, cog):
        super().__init__(timeout=None)  # Persistent player controls
        self.bot = bot
        self.guild_id = guild_id
        self.cog = cog
        
    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item) -> None:
        logger.exception("NowPlayingView interaction error on %s: %s", item, error)
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Action failed or timed out.", ephemeral=True)
            else:
                await interaction.followup.send("❌ Action failed or timed out.", ephemeral=True)
        except Exception:
            pass

    @discord.ui.button(label="Pause", emoji="⏸️", style=discord.ButtonStyle.primary)
    async def pause_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild or self.bot.get_guild(self.guild_id)
        vc = self.cog.voice_clients.get(self.guild_id) or (guild.voice_client if guild else None)
        if not vc or not vc.is_connected():
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
        except Exception as exc:
            logger.warning("Failed to pause audio: %s", exc)
            await interaction.response.send_message("Failed to pause the audio.", ephemeral=True)

    @discord.ui.button(label="Resume", emoji="▶️", style=discord.ButtonStyle.success)
    async def resume_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild or self.bot.get_guild(self.guild_id)
        vc = self.cog.voice_clients.get(self.guild_id) or (guild.voice_client if guild else None)
        if not vc or not vc.is_connected():
            await interaction.response.send_message("I am not connected to a voice channel.", ephemeral=True)
            return
        if not vc.is_paused():
            await interaction.response.send_message("Audio is not paused.", ephemeral=True)
            return
        try:
            vc.resume()
            await interaction.response.send_message(f"{interaction.user.mention} resumed the audio. ▶️")
        except Exception as exc:
            logger.warning("Failed to resume audio: %s", exc)
            await interaction.response.send_message("Failed to resume the audio.", ephemeral=True)

    @discord.ui.button(label="Queue", emoji="📋", style=discord.ButtonStyle.secondary)
    async def queue_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        p = self.cog._ensure_player(self.guild_id)
        q = p.get_queue()
        current_track = q.now_playing()
        upcoming = q.get_queue()
        if not current_track and not upcoming:
            await interaction.response.send_message("The music queue is currently empty. 🎵", ephemeral=True)
            return

        paginator = QueuePaginatorView(self.bot, self.guild_id, self.cog, current_track, upcoming)
        await interaction.response.send_message(embed=paginator.make_embed(), view=paginator, ephemeral=True)

    @discord.ui.button(label="Autoplay", emoji="📻", style=discord.ButtonStyle.secondary)
    async def autoplay_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        p = self.cog._ensure_player(self.guild_id)
        p.autoplay_enabled = not p.autoplay_enabled
        status = "enabled" if p.autoplay_enabled else "disabled"
        button.style = discord.ButtonStyle.success if p.autoplay_enabled else discord.ButtonStyle.secondary
        try:
            if not interaction.response.is_done():
                await interaction.response.edit_message(view=self)
            await interaction.followup.send(f"Autoplay has been **{status}** by {interaction.user.mention}. 📻", ephemeral=True)
        except Exception as e:
            logger.warning("Autoplay button interaction error: %s", e)

    @discord.ui.button(label="Equalizer", emoji="🎛️", style=discord.ButtonStyle.danger)
    async def equalizer_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = EqualizerSelectView(self.bot, self.guild_id, self.cog)
        await interaction.response.send_message("Select an Equalizer preset below. The filter applies immediately! 🎛️", view=view, ephemeral=True)


class EqualizerSelectView(discord.ui.View):
    def __init__(self, bot, guild_id, cog):
        super().__init__(timeout=60)
        self.add_item(EqualizerSelect(bot, guild_id, cog))

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item) -> None:
        logger.exception("EqualizerSelectView interaction error: %s", error)
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Failed to set equalizer preset.", ephemeral=True)
            else:
                await interaction.followup.send("❌ Failed to set equalizer preset.", ephemeral=True)
        except Exception:
            pass


class EqualizerSelect(discord.ui.Select):
    def __init__(self, bot, guild_id, cog):
        self.bot = bot
        self.guild_id = guild_id
        self.cog = cog
        
        options = [
            discord.SelectOption(label="Flat (Off)", description="No audio filters applied.", emoji="❌", value="flat"),
            discord.SelectOption(label="Bass Boost", description="Rich low-frequency bass response.", emoji="🔊", value="bassboost"),
            discord.SelectOption(label="Ultra Bass", description="Heavy sub-bass boost.", emoji="⚡", value="ultrabass"),
            discord.SelectOption(label="Lo-Fi / Chill", description="Warm retro vinyl filter.", emoji="🌌", value="lofi"),
            discord.SelectOption(label="Nightcore", description="Faster tempo & higher pitch.", emoji="⚡", value="nightcore"),
            discord.SelectOption(label="Vaporwave", description="Slower tempo & lower pitch.", emoji="🌊", value="vaporwave"),
            discord.SelectOption(label="8D Audio", description="Dynamic moving surround pan.", emoji="🎧", value="8d"),
            discord.SelectOption(label="Vocal Boost", description="Enhanced vocal clarity.", emoji="🎤", value="vocalboost"),
            discord.SelectOption(label="Clear Treble", description="Crisp high-frequency tones.", emoji="✨", value="treble"),
            discord.SelectOption(label="Rock / Heavy", description="V-shaped equalizer curve.", emoji="🎸", value="rock"),
            discord.SelectOption(label="Pop / Bright", description="Bright pop sound balance.", emoji="🎙️", value="pop"),
            discord.SelectOption(label="Radio / Oldschool", description="Classic telephone radio filter.", emoji="📻", value="radio"),
            discord.SelectOption(label="Karaoke (Vocal Mute)", description="Cancels center vocals for singing along.", emoji="🎤", value="karaoke"),
        ]
        super().__init__(placeholder="Choose an Equalizer preset...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        choice = self.values[0]
        p = self.cog._ensure_player(self.guild_id)
        
        presets = {
            "flat": "-vn",
            "bassboost": "-vn -af equalizer=f=60:width_type=h:width=50:g=8,equalizer=f=100:width_type=h:width=50:g=6",
            "ultrabass": "-vn -af equalizer=f=40:width_type=h:width=40:g=12,equalizer=f=80:width_type=h:width=40:g=8",
            "lofi": "-vn -af lowpass=f=3200,highpass=f=150,volume=1.1",
            "nightcore": "-vn -af asetrate=44100*1.25,aresample=44100,atempo=1.0",
            "vaporwave": "-vn -af asetrate=44100*0.85,aresample=44100,atempo=1.0",
            "8d": "-vn -af aformat=channel_layouts=stereo,apulsator=hz=0.125:amount=0.9",
            "vocalboost": "-vn -af equalizer=f=1000:width_type=h:width=500:g=6,equalizer=f=3000:width_type=h:width=1000:g=5",
            "treble": "-vn -af equalizer=f=4000:width_type=h:width=1000:g=7,equalizer=f=8000:width_type=h:width=2000:g=6",
            "rock": "-vn -af equalizer=f=80:g=6,equalizer=f=250:g=3,equalizer=f=4000:g=4,equalizer=f=10000:g=7",
            "pop": "-vn -af equalizer=f=100:g=4,equalizer=f=1000:g=-1,equalizer=f=10000:g=5",
            "radio": "-vn -af highpass=f=400,lowpass=f=3500",
            "karaoke": "-vn -af pan=stereo|c0=c0-c1|c1=c1-c0",
        }

        p.eq_preset_name = choice
        p.eq_option = presets.get(choice, "-vn")
        vc = self.cog.voice_clients.get(self.guild_id)
        
        preset_title = choice.replace("_", " ").title()
        message = f"🎛️ Equalizer preset applied: **{preset_title}**"

        # Edit message immediately to satisfy Discord's interaction ACK instantly
        try:
            if not interaction.response.is_done():
                await interaction.response.edit_message(content=message, view=None)
            else:
                await interaction.followup.send(message, ephemeral=True)
        except Exception:
            try:
                if not interaction.response.is_done():
                    await interaction.response.defer(ephemeral=True)
                await interaction.followup.send(message, ephemeral=True)
            except Exception:
                pass

        # Restart track filter cleanly
        try:
            p.restart_current_track(vc)
        except Exception as e:
            logger.warning("Error restarting track with EQ preset: %s", e)



class QueuePaginatorView(discord.ui.View):
    def __init__(self, bot, guild_id: int, cog, current_track, upcoming: list, items_per_page: int = 10):
        super().__init__(timeout=None)  # Persistent paginator
        self.bot = bot
        self.guild_id = guild_id
        self.cog = cog
        self.current_track = current_track
        self.upcoming = upcoming
        self.items_per_page = items_per_page
        self.current_page = 0
        
        total_items = len(upcoming)
        self.total_pages = max(1, math.ceil(total_items / items_per_page))
        self.update_buttons()

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item) -> None:
        logger.exception("QueuePaginatorView interaction error: %s", error)
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Failed to change queue page.", ephemeral=True)
            else:
                await interaction.followup.send("❌ Failed to change queue page.", ephemeral=True)
        except Exception:
            pass

    def update_buttons(self):
        self.first_button.disabled = (self.current_page == 0)
        self.prev_button.disabled = (self.current_page == 0)
        self.page_indicator.label = f"Page {self.current_page + 1}/{self.total_pages}"
        self.next_button.disabled = (self.current_page >= self.total_pages - 1)
        self.last_button.disabled = (self.current_page >= self.total_pages - 1)

    def format_time(self, seconds: int) -> str:
        if seconds is None or seconds < 0:
            return "0:00"
        mins, secs = divmod(int(seconds), 60)
        hours, mins = divmod(mins, 60)
        if hours > 0:
            return f"{hours:02d}:{mins:02d}:{secs:02d}"
        return f"{mins:02d}:{secs:02d}"

    def make_embed(self) -> discord.Embed:
        from utils.embed_utils import HELIX_COLOR, set_owner_footer
        guild = self.bot.get_guild(self.guild_id)
        guild_name = guild.name if guild else "Server"

        embed = discord.Embed(
            title="Music Queue",
            color=HELIX_COLOR,
        )

        # 1. Now Playing track
        if self.current_track:
            req_mention = f"<@{self.current_track.requester}>" if self.current_track.requester else "*Autoplay*"
            duration_str = self.format_time(self.current_track.duration)
            embed.description = (
                f"**Now Playing:**\n"
                f"> 🎵 {format_track_link(self.current_track.title, self.current_track.url)} (`{duration_str}`) • {req_mention}\n\n"
                f"**Up Next (Page {self.current_page + 1}/{self.total_pages}):**\n"
            )
        else:
            embed.description = f"**Now Playing:**\n*Nothing is currently playing.*\n\n**Up Next (Page {self.current_page + 1}/{self.total_pages}):**\n"

        # 2. Upcoming tracks for current page
        start_idx = self.current_page * self.items_per_page
        end_idx = start_idx + self.items_per_page
        page_tracks = self.upcoming[start_idx:end_idx]

        if page_tracks:
            upcoming_lines = []
            for i, track in enumerate(page_tracks, start=start_idx + 1):
                req_mention = f"<@{track.requester}>" if track.requester else "*Autoplay*"
                duration_str = self.format_time(track.duration)
                upcoming_lines.append(
                    f"`{i:02d}.` {format_track_link(track.title, track.url)} (`{duration_str}`) • {req_mention}"
                )
            embed.description += "\n".join(upcoming_lines)
        else:
            embed.description += "*No upcoming tracks in queue.*"

        # 3. Status/Metadata footer
        p = self.cog._ensure_player(self.guild_id)
        q = p.get_queue()

        loop_status = "Off"
        if q.loop_mode == "song":
            loop_status = "Song"
        elif q.loop_mode == "queue":
            loop_status = "Queue"

        autoplay_status = "Active" if getattr(p, "autoplay_enabled", False) else "Disabled"

        total_duration = sum((t.duration or 0) for t in self.upcoming)
        if self.current_track:
            total_duration += (self.current_track.duration or 0)
        total_duration_str = self.format_time(total_duration)

        embed.description += (
            f"\n\n> 📊 **Queue:** `{len(self.upcoming) + (1 if self.current_track else 0)} tracks` • "
            f"⏱️ `{total_duration_str}` • "
            f"🔁 **Loop:** `{loop_status}` • "
            f"📻 **Autoplay:** `{autoplay_status}`"
        )

        set_owner_footer(embed, self.bot, extra_text=f"Page {self.current_page + 1} of {self.total_pages}")
        return embed

    @discord.ui.button(label="First", emoji="⏮️", style=discord.ButtonStyle.secondary)
    async def first_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = 0
        self.update_buttons()
        if not interaction.response.is_done():
            await interaction.response.edit_message(embed=self.make_embed(), view=self)

    @discord.ui.button(label="Previous", emoji="◀️", style=discord.ButtonStyle.primary)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
            self.update_buttons()
            if not interaction.response.is_done():
                await interaction.response.edit_message(embed=self.make_embed(), view=self)
        else:
            await interaction.response.send_message("You are already on the first page.", ephemeral=True)

    @discord.ui.button(label="Page 1/1", style=discord.ButtonStyle.secondary, disabled=True)
    async def page_indicator(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass

    @discord.ui.button(label="Next", emoji="▶️", style=discord.ButtonStyle.primary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            self.update_buttons()
            if not interaction.response.is_done():
                await interaction.response.edit_message(embed=self.make_embed(), view=self)
        else:
            await interaction.response.send_message("You are already on the last page.", ephemeral=True)

    @discord.ui.button(label="Last", emoji="⏭️", style=discord.ButtonStyle.secondary)
    async def last_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = self.total_pages - 1
        self.update_buttons()
        if not interaction.response.is_done():
            await interaction.response.edit_message(embed=self.make_embed(), view=self)



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
        from utils.embed_utils import set_owner_footer
        set_owner_footer(embed, self.bot, extra_text=f"Page {self.current_page + 1} of {len(self.pages)}")
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
