import asyncio
import logging
from typing import Optional
from .queue import GuildQueue
from .models import Track

logger = logging.getLogger(__name__)


_last_status_cache = {}


async def update_vc_status(bot, channel_id: Optional[int], status_text: str):
    """Set or clear the voice channel status text for a voice channel with rate-limit debounce."""
    if not bot or not channel_id:
        return
    status_str = (status_text or "").strip()[:500]

    # Debounce check: avoid sending duplicate updates or spamming Discord API
    try:
        now = asyncio.get_running_loop().time()
    except Exception:
        now = 0

    last_time, last_val = _last_status_cache.get(channel_id, (0, None))
    if last_val == status_str and (now - last_time < 30.0):
        return



    _last_status_cache[channel_id] = (now, status_str)

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
        self.is_247 = False
        self.eq_preset_name = "flat"
        self.eq_option = "-vn"

    def reset_eq(self):
        """Reset Equalizer preset back to default (flat/off)."""
        self.eq_preset_name = "flat"
        self.eq_option = "-vn"

    def set_volume(self, volume: float, voice_client: Optional[object] = None):
        """Set playback volume (e.g. 0.5 for 50%, 1.0 for 100%) and update live voice source."""
        self.volume = max(0.0, float(volume))
        vc = voice_client or getattr(self, "_current_vc", None)
        if vc and hasattr(vc, "source") and vc.source:
            src = vc.source
            if hasattr(src, "volume"):
                src.volume = self.volume
            elif hasattr(src, "original") and hasattr(src.original, "volume"):
                src.original.volume = self.volume



    async def _ensure_valid_stream_url(self, track, force_refresh: bool = False):
        """Ensure track has a valid direct http/https audio stream URL prior to playback."""
        if not track:
            return
        url = getattr(track, "stream_url", None) or getattr(track, "url", "")
        if force_refresh or not url or not (url.startswith("http://") or url.startswith("https://")):
            try:
                from .providers import YouTubeProvider
                yt = YouTubeProvider()
                query = getattr(track, "url", None) or getattr(track, "title", None) or "song"
                search_term = query if (query.startswith("http://") or query.startswith("https://")) else f"ytsearch1:{query}"

                meta = await yt.fetch_metadata(search_term)
                if meta and meta.get("stream_url") and (meta["stream_url"].startswith("http://") or meta["stream_url"].startswith("https://")):
                    track.stream_url = meta["stream_url"]
                    if meta.get("http_headers"):
                        track.http_headers = meta["http_headers"]
            except Exception as err:
                logger.warning("On-demand stream resolution failed for %s: %s", getattr(track, "title", "track"), err)

        curr_stream = getattr(track, "stream_url", None)
        if curr_stream and not (curr_stream.startswith("http://") or curr_stream.startswith("https://")):
            track.stream_url = None




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
                    self.reset_eq()
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

                    # Post clean notification when advancing to next track if not seeking and not restarting due to EQ filter change
                    is_seeking = getattr(self, "seeking", False)
                    is_filter_change = getattr(self, "_restarting_current_track", False)
                    suppress_first = getattr(self, "suppress_first_track_msg", False)

                    if is_filter_change:
                        self._restarting_current_track = False
                    elif is_seeking:
                        self.seeking = False
                    elif suppress_first:
                        self.suppress_first_track_msg = False
                    else:
                        text_ch = getattr(self, "text_channel", None)
                        if text_ch:
                            try:
                                from .ui import format_time
                                clean_title = getattr(track, "title", "Unknown Track").replace('\\', '')
                                dur = getattr(track, "duration", None)
                                dur_str = f"( {format_time(dur)} ) " if dur else ""
                                
                                is_auto = getattr(track, "requester", None) is None
                                if is_auto:
                                    msg_text = f"📻 **{clean_title}** started playing {dur_str}[Autoplay]"
                                else:
                                    msg_text = f"🎶 **{clean_title}** started playing {dur_str}"
                                
                                async def _send_np(msg_content=msg_text):
                                    try:
                                        await text_ch.send(msg_content)
                                    except Exception as err:
                                        logger.warning("Could not send track advance notice: %s", err)
                                asyncio.create_task(_send_np())
                            except Exception as e:
                                logger.exception("Failed to send track notification: %s", e)

                    # Update active NP embed with new EQ preset badge if available
                    if (is_filter_change or is_seeking) and hasattr(self, "current_np_message") and self.current_np_message:
                        try:
                            from .ui import build_started_playing_embed
                            guild_name = voice_client.guild.name if (voice_client and voice_client.guild) else "Server"
                            cur_sec = getattr(self, "seek_time", 0)
                            updated_embed = build_started_playing_embed(track, guild_name, bot_instance, self, current_sec=cur_sec)
                            asyncio.create_task(self.current_np_message.edit(embed=updated_embed))
                        except Exception:
                            pass

                    seek_time = getattr(self, "seek_time", 0)
                    self.seek_time = 0
                    self.current_track_started_at = loop.time() - seek_time
                    playback_started_at = loop.time()

                    # On-demand stream resolution if stream_url is missing or invalid
                    await self._ensure_valid_stream_url(track)

                    # Start live progress bar updater task
                    self._start_progress_updater(voice_client, track, bot_instance)

                    eq_opt = getattr(self, "eq_option", "-vn")
                    playback_ok = await play_track_on_voice(
                        voice_client,
                        track,
                        loop=loop,
                        options=eq_opt,
                        seek_time=seek_time,
                        volume=getattr(self, "volume", 1.0),
                    )
                    playback_seconds = loop.time() - playback_started_at

                    # Check dynamic restarting state NOW (not stale from top of loop)
                    restarting_now = getattr(self, "_restarting_current_track", False) or getattr(self, "seeking", False)

                    # If playback ended unexpectedly early (<3s), attempt automatic stream refresh & filter fallback before skipping
                    if not playback_ok and not restarting_now:
                        if playback_seconds < 3 and (track.duration or 0) > 3:
                            logger.warning("Playback ended unexpectedly after %.1fs for '%s'. Refreshing stream URL and retrying...", playback_seconds, track.title)
                            await self._ensure_valid_stream_url(track, force_refresh=True)
                            retry_start = loop.time()
                            playback_ok = await play_track_on_voice(
                                voice_client,
                                track,
                                loop=loop,
                                options=eq_opt,
                                seek_time=seek_time,
                                volume=getattr(self, "volume", 1.0),
                            )
                            # If EQ filter caused startup exit, fallback to clean audio (-vn)
                            if not playback_ok and eq_opt != "-vn":
                                logger.warning("Equalizer filter '%s' failed for '%s'. Falling back to clean audio (-vn).", eq_opt, track.title)
                                self.eq_option = "-vn"
                                self.eq_preset_name = "flat"
                                playback_ok = await play_track_on_voice(
                                    voice_client,
                                    track,
                                    loop=loop,
                                    options="-vn",
                                    seek_time=seek_time,
                                    volume=getattr(self, "volume", 1.0),
                                )
                            playback_seconds = loop.time() - retry_start

                    if not restarting_now:
                        if not playback_ok or (playback_seconds < 3 and (track.duration or 0) > 3):
                            self._consecutive_playback_failures += 1
                            logger.warning("Playback ended unexpectedly after %.1fs for %s (%d consecutive failures).", playback_seconds, track.title, self._consecutive_playback_failures)
                        else:
                            self._consecutive_playback_failures = 0

                except Exception as exc:
                    logger.exception("Voice playback failed for track %s: %s", getattr(track, "title", "track"), exc)
                    if not getattr(self, "_restarting_current_track", False) and not getattr(self, "seeking", False):
                        self._consecutive_playback_failures += 1
                finally:
                    if hasattr(self, "_progress_task") and self._progress_task and not self._progress_task.done():
                        self._progress_task.cancel()

                    # Advance the queue ONLY if we are NOT restarting for filter change or seek!
                    is_restarting = getattr(self, "_restarting_current_track", False) or getattr(self, "seeking", False)
                    if not is_restarting:
                        self.queue.dequeue()
                        self.current_track_started_at = None
                        logger.info("Track playback finished. Current queue size: %d. Autoplay enabled: %s", len(self.queue.get_queue()), self.autoplay_enabled)
                    else:
                        logger.info("Track '%s' is being restarted for EQ/seek filter change at %ds; preserving in queue.", getattr(track, "title", "track"), getattr(self, "seek_time", 0))

        except asyncio.CancelledError:
            return
        finally:
            if hasattr(self, "_progress_task") and self._progress_task and not self._progress_task.done():
                self._progress_task.cancel()
            if ch_id and bot_instance:
                asyncio.create_task(update_vc_status(bot_instance, ch_id, ""))

    def _start_progress_updater(self, voice_client, track, bot_instance):
        if hasattr(self, "_progress_task") and self._progress_task and not self._progress_task.done():
            self._progress_task.cancel()

        async def _updater():
            try:
                from .ui import build_started_playing_embed
                loop = asyncio.get_running_loop()
                while voice_client and (voice_client.is_playing() or voice_client.is_paused()):
                    await asyncio.sleep(4)
                    msg = getattr(self, "current_np_message", None)
                    if not msg or not self.current_track_started_at:
                        continue
                    if voice_client.is_paused():
                        continue
                    current_sec = max(0, int(loop.time() - self.current_track_started_at))
                    guild_name = voice_client.guild.name if (voice_client and voice_client.guild) else "Server"
                    updated_embed = build_started_playing_embed(track, guild_name, bot_instance, self, current_sec=current_sec)
                    try:
                        await msg.edit(embed=updated_embed)
                    except Exception:
                        break
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.warning("Progress updater error: %s", e)

        self._progress_task = asyncio.create_task(_updater())


    def stop_voice_playback(self):
        self.reset_eq()
        vc = getattr(self, "_current_vc", None)
        if vc:
            bot_instance = getattr(vc, "client", None)
            ch_id = getattr(getattr(vc, "channel", None), "id", None)
            if bot_instance and ch_id:
                asyncio.create_task(update_vc_status(bot_instance, ch_id, ""))
        if self._voice_task and not self._voice_task.done():
            self._voice_task.cancel()
            self._voice_task = None


