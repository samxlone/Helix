"""Voice adapter for playing Track.stream_url into a discord.VoiceClient using FFmpeg.

This module imports discord and uses FFmpegPCMAudio lazily to avoid requiring PyNaCl/ffmpeg at import time.
"""
import asyncio
import logging
import os
import shutil
from typing import Optional

logger = logging.getLogger(__name__)


async def connect_to_channel(channel) -> Optional[object]:
    """Connect to a discord.VoiceChannel and return the VoiceClient.

    `channel` is expected to be a discord.VoiceChannel-like object with .connect() coroutine.
    This function imports discord lazily.
    """
    try:
        # lazy import
        import discord
    except Exception:
        logger.exception("discord library not available for voice connection")
        raise

    # If opus/voice support is not loaded, connecting may fail. Provide early guidance.
    try:
        if not getattr(discord, "opus", None) or not discord.opus.is_loaded():
            logger.warning("Discord Opus not loaded - voice requires PyNaCl/opus. Attempting to connect may fail.")
    except Exception:
        # ignore any issues checking opus
        pass

    if channel is None:
        raise ValueError("channel is required")

    # Connect to the channel
    vc = await channel.connect()
    return vc


async def play_track_on_voice(voice_client, track, *, loop: asyncio.AbstractEventLoop = None, options: str = "-vn", seek_time: int = 0, volume: float = 1.0):
    """Play a Track on a connected discord.VoiceClient.

    This function constructs an FFmpegPCMAudio source from track.stream_url,
    wraps it in a PCMVolumeTransformer, and plays it.
    It returns after playback completes. It does not start any queue logic; the caller should manage the queue.
    """
    if not voice_client:
        raise ValueError("voice_client required")
    if not track or not getattr(track, "stream_url", None):
        raise ValueError("track with stream_url required")

    try:
        import discord
    except Exception:
        logger.exception("discord library not available for playback")
        raise

    # Prepare ffmpeg audio source with reconnect options for HTTP streams
    before_options = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
    if seek_time > 0:
        before_options += f" -ss {seek_time}"
    
    headers = getattr(track, "http_headers", None)
    if headers:
        header_str = "".join(f"{k}: {v}\r\n" for k, v in headers.items())
        escaped_headers = header_str.replace('"', '\\"')
        before_options += f' -headers "{escaped_headers}"'

    try:
        # Determine ffmpeg executable: prefer explicit env var FFMPEG_PATH, else use system PATH lookup
        ffmpeg_exe = None
        env_path = os.getenv("FFMPEG_PATH")
        if env_path:
            ffmpeg_exe = env_path
        else:
            ffmpeg_exe = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")

        ffmpeg_kwargs = {}
        if ffmpeg_exe:
            ffmpeg_kwargs["executable"] = ffmpeg_exe
            logger.info("Using ffmpeg executable: %s", ffmpeg_exe)
        else:
            logger.warning("No ffmpeg executable found on PATH or FFMPEG_PATH. FFmpegPCMAudio will use system PATH.")

        logger.info("Creating FFmpegPCMAudio for track: %s (stream_url: %s)", track.title if hasattr(track, "title") else "unknown", track.stream_url[:50] if track.stream_url else "")
        source = discord.FFmpegPCMAudio(track.stream_url, before_options=before_options, options=options, **ffmpeg_kwargs)
        volume_source = discord.PCMVolumeTransformer(source, volume=volume)
        logger.info("FFmpegPCMAudio and PCMVolumeTransformer created successfully")
    except Exception:
        logger.exception("Failed to create FFmpegPCMAudio/PCMVolumeTransformer for %s", track.stream_url)
        raise

    play_finished = asyncio.Event()
    playback_error = None

    def _after_play(err):
        nonlocal playback_error
        playback_error = err
        if err:
            logger.error("Error in voice playback: %s", err)
        # set event in loop
        try:
            loop_ = loop or asyncio.get_event_loop()
            loop_.call_soon_threadsafe(play_finished.set)
        except Exception:
            try:
                asyncio.get_event_loop().call_soon_threadsafe(play_finished.set)
            except Exception:
                pass

    # Stop any current source
    try:
        if voice_client.is_playing():
            voice_client.stop()
    except Exception:
        # ignore missing attributes in mocks
        pass

    voice_client.play(volume_source, after=_after_play)

    # wait until playback finishes
    await play_finished.wait()

    # cleanup
    try:
        volume_source.cleanup()
    except Exception:
        pass

    return playback_error is None
