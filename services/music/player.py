import asyncio
import logging
from typing import Optional
from .queue import GuildQueue
from .models import Track

logger = logging.getLogger(__name__)


async def update_vc_status(bot, channel_id: Optional[int], status_text: str):
    """Set or clear the voice channel status text for a voice channel."""
    if not bot or not channel_id:
        return
    status_str = (status_text or "").strip()[:500]
    try:
        import discord
        route = discord.http.Route("PUT", "/channels/{channel_id}/voice-status", channel_id=channel_id)
        await bot.http.request(route, json={"status": status_str})
    except Exception as e:
        logger.debug("Failed to set VC status for channel %s: %s", channel_id, e)


class Player:
    """Player manages playback lifecycle for a guild. This is a stub that supports both a local play loop and voice playback adapters.

    Responsibilities:
    - hold reference to GuildQueue
    - provide start/stop/skip controls
    - optionally run a voice playback loop when a VoiceClient is provided
    """

    def __init__(self, guild_id: int, queue: Optional[GuildQueue] = None):
        self.guild_id = guild_id
        self.queue = queue or GuildQueue(guild_id)
        self.playing = False
        self._task: Optional[asyncio.Task] = None
        self._voice_task: Optional[asyncio.Task] = None
        self.current_track_started_at: Optional[float] = None
        self._restarting_current_track = False
        self._consecutive_playback_failures = 0
        self.autoplay_enabled = False
        from .autoplay import Autoplay
        self.autoplay = Autoplay()
        self.volume = 1.0

    async def _play_loop(self):
        # stub loop: waits and moves through queue without audio
        self.playing = True
        try:
            while self.playing:
                track = self.queue.now_playing() or self.queue.dequeue()
                if not track:
                    # nothing to play
                    await asyncio.sleep(0.5)
                    continue
                # simulate playing by sleeping up to a small time (or duration if set)
                duration = track.duration or 5
                # clamp duration for stub
                await asyncio.sleep(min(duration, 2))
                # after track ends, advance queue
                self.queue.dequeue()
        finally:
            self.playing = False

    def start(self):
        if not self._task or self._task.done():
            self._task = asyncio.create_task(self._play_loop())

    def stop(self):
        self.playing = False
        if self._task and not self._task.done():
            self._task.cancel()

    def is_playing(self) -> bool:
        return self.playing

    def get_queue(self) -> GuildQueue:
        return self.queue

    def start_voice_playback(self, voice_client):
        """Start a voice playback loop using the given discord.VoiceClient. This spawns a background task.

        The actual playback logic is implemented in services.music.voice.play_track_on_voice and is invoked per-track.
        """
        if self._voice_task and not self._voice_task.done():
            if getattr(self, "_current_vc", None) == voice_client:
                return
            self._voice_task.cancel()

        self._current_vc = voice_client
        self._voice_task = asyncio.create_task(self._voice_loop(voice_client))

    def restart_current_track(self, voice_client) -> bool:
        """Restart the active track with its current audio options.

        FFmpeg filters cannot be changed in an already-running process. Stopping
        the source lets the voice loop create a fresh FFmpeg source using the
        updated options, while retaining the queue's current track.
        """
        if not self.queue.now_playing() or not voice_client:
            return False
        try:
            if not (voice_client.is_playing() or voice_client.is_paused()):
                return False
            loop = asyncio.get_running_loop()
            if self.current_track_started_at is not None:
                self.seek_time = max(0, int(loop.time() - self.current_track_started_at))
            else:
                self.seek_time = 0
            self._restarting_current_track = True
            voice_client.stop()
            return True
        except Exception:
            return False

    async def _voice_loop(self, voice_client):
        # lazy import to avoid requiring discord in non-voice environments
        try:
            from .voice import play_track_on_voice
        except Exception:
            # voice module not available
            return

        loop = asyncio.get_running_loop()
        bot_instance = getattr(voice_client, "client", None)
        ch_id = getattr(getattr(voice_client, "channel", None), "id", None)

        try:
            while True:
                if not voice_client or not voice_client.is_connected():
                    logger.info("Voice client disconnected or uninitialized. Exiting voice loop.")
                    break
                track = self.queue.now_playing() or self.queue.dequeue()

                if not track:
                    if ch_id and bot_instance:
                        asyncio.create_task(update_vc_status(bot_instance, ch_id, ""))
                    if self.autoplay_enabled:
                        if self._consecutive_playback_failures >= 3:
                            self.autoplay_enabled = False
                            text_ch = getattr(self, "text_channel", None)
                            if text_ch:
                                await text_ch.send("Autoplay was stopped because several tracks failed to start. Try playing a new song.")
                            continue
                        import logging
                        logger = logging.getLogger(__name__)
                        history = self.queue.get_history()
                        last_track = history[-1] if history else None
                        if last_track:
                            logger.info("Queue ended. Autoplay: recommending similar song to '%s'", last_track.title)
                            recommended = await self.autoplay.recommend(last_track)
                            if recommended:
                                self.queue.enqueue(recommended)
                                continue
                    await asyncio.sleep(0.5)
                    continue

                try:
                    # Update VC channel status with currently playing song
                    if ch_id and bot_instance:
                        asyncio.create_task(update_vc_status(bot_instance, ch_id, f"🎵 Playing: {track.title}"))

                    # Post "Started Playing" embed if not seeking
                    is_seeking = getattr(self, "seeking", False)
                    if not is_seeking:
                        text_ch = getattr(self, "text_channel", None)
                        if text_ch:
                            try:
                                import discord
                                title_str = (track.title or "Unknown Track").strip()
                                url_str = (track.url or "").strip()
                                if title_str.startswith("http://") or title_str.startswith("https://") or title_str == url_str:
                                    desc_content = f"**{title_str}**"
                                else:
                                    safe_title = title_str.replace("[", "\\[").replace("]", "\\]")
                                    desc_content = f"**[{safe_title}]({url_str})**"

                                embed = discord.Embed(
                                    title="Started Playing 🎶",
                                    description=desc_content,
                                    color=discord.Color.blurple()
                                )

                                if track.author:
                                    embed.add_field(name="Uploader/Artist", value=track.author, inline=True)
                                if track.duration:
                                    mins, secs = divmod(track.duration, 60)
                                    hours, mins = divmod(mins, 60)
                                    duration_str = f"{hours:02d}:{mins:02d}:{secs:02d}" if hours else f"{mins:02d}:{secs:02d}"
                                    embed.add_field(name="Duration", value=duration_str, inline=True)
                                requester_str = f"<@{track.requester}>" if track.requester else "Autoplay 📻"
                                embed.add_field(name="Requested By", value=requester_str, inline=True)
                                if track.thumbnail:
                                    embed.set_thumbnail(url=track.thumbnail)
                                owner = getattr(bot_instance, "owner_user", None) if bot_instance else None
                                if owner:
                                    embed.set_footer(text=f"Created by {owner.name} • Owned by {owner.name}", icon_url=owner.avatar.url if owner.avatar else None)
                                else:
                                    embed.set_footer(text="Owned by Bot Owner")
                                from cogs.music import NowPlayingView
                                view = NowPlayingView(bot_instance, voice_client.guild.id, bot_instance.get_cog("MusicCog"))
                                asyncio.create_task(text_ch.send(embed=embed, view=view))
                            except Exception as e:
                                import logging
                                logger = logging.getLogger(__name__)
                                logger.exception("Failed to send Started Playing embed: %s", e)

                                
                    seek_time = getattr(self, "seek_time", 0)
                    self.seek_time = 0
                    self.current_track_started_at = loop.time() - seek_time
                    playback_started_at = loop.time()
                    playback_ok = await play_track_on_voice(
                        voice_client,
                        track,
                        loop=loop,
                        options=getattr(self, "eq_option", "-vn"),
                        seek_time=seek_time,
                        volume=getattr(self, "volume", 1.0),
                    )
                    playback_seconds = loop.time() - playback_started_at
                    if not self._restarting_current_track:
                        # Repeated immediate endings indicate an expired/broken stream. Do not let
                        # autoplay spin forever by repeatedly fetching recommendations in that case.
                        if not playback_ok or (playback_seconds < 3 and (track.duration or 0) > 3):
                            self._consecutive_playback_failures += 1
                            logger.warning("Playback ended unexpectedly after %.1fs for %s (%d consecutive failures).", playback_seconds, track.title, self._consecutive_playback_failures)
                        else:
                            self._consecutive_playback_failures = 0
                except Exception as exc:
                    # If playback fails, log and skip to next
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.exception("Voice playback failed for track %s: %s", track.title, exc)
                    if not self._restarting_current_track:
                        self._consecutive_playback_failures += 1
                    pass
                finally:
                    # Advance the queue after playback finishes (only if we are not seeking)
                    if self._restarting_current_track:
                        self._restarting_current_track = False
                    elif getattr(self, "seeking", False):
                        self.seeking = False
                    else:
                        self.queue.dequeue()
                    self.current_track_started_at = None
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.info("Track playback finished. Current queue size: %d. Autoplay enabled: %s", len(self.queue.get_queue()), self.autoplay_enabled)
        except asyncio.CancelledError:
            return
        finally:
            if ch_id and bot_instance:
                asyncio.create_task(update_vc_status(bot_instance, ch_id, ""))

    def stop_voice_playback(self):
        vc = getattr(self, "_current_vc", None)
        if vc:
            bot_instance = getattr(vc, "client", None)
            ch_id = getattr(getattr(vc, "channel", None), "id", None)
            if bot_instance and ch_id:
                asyncio.create_task(update_vc_status(bot_instance, ch_id, ""))
        if self._voice_task and not self._voice_task.done():
            self._voice_task.cancel()
            self._voice_task = None

