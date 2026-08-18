"""Voice adapter for playing Track.stream_url into a discord.VoiceClient using FFmpeg.

This module imports discord and uses FFmpegPCMAudio lazily to avoid requiring PyNaCl/ffmpeg at import time.
"""
import asyncio
import logging
import os
import shutil
from typing import Optional

logger = logging.getLogger(__name__)


def ensure_opus_loaded():
    """Ensure Opus encoder library is loaded for Discord voice playback."""
    try:
        import discord
        if not discord.opus.is_loaded():
            import ctypes.util
            opus_path = ctypes.util.find_library("opus")
            if opus_path:
                try:
                    discord.opus.load_opus(opus_path)
                    logger.info("Loaded Opus library from system find_library: %s", opus_path)
                    return True
                except Exception:
                    pass

            for lib_name in ["libopus.so.0", "libopus.so", "libopus.so.1", "libopus-0.dll", "libopus.dylib"]:
                try:
                    discord.opus.load_opus(lib_name)
                    if discord.opus.is_loaded():
                        logger.info("Successfully loaded Opus library: %s", lib_name)
                        return True
                except Exception:
                    pass
            logger.warning("Could not automatically locate Opus library. Ensure PyNaCl or libopus is installed.")
            return False
        return True
    except Exception as exc:
        logger.warning("Error loading Opus library: %s", exc)
        return False


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

    ensure_opus_loaded()


    if channel is None:
        raise ValueError("channel is required")

    guild = getattr(channel, "guild", None)
    vc = getattr(guild, "voice_client", None) if guild else None

    if vc:
        current_ch = getattr(vc, "channel", None)
        if current_ch and getattr(current_ch, "id", None) == getattr(channel, "id", None):
            return vc
        try:
            if hasattr(vc, "move_to"):
                await vc.move_to(channel)
                return vc
        except Exception as exc:
            logger.warning("Failed to move existing voice client: %s. Disconnecting stale connection.", exc)
            try:
                if hasattr(vc, "disconnect"):
                    await vc.disconnect(force=True)
                await asyncio.sleep(0.5)
            except Exception:
                pass

    try:
        vc = await channel.connect()
        return vc
    except Exception as exc:
        err_str = str(exc)
        if "Already connected" in err_str:
            vc = getattr(guild, "voice_client", None) if guild else None
            if vc:
                current_ch = getattr(vc, "channel", None)
                if current_ch and getattr(current_ch, "id", None) != getattr(channel, "id", None):
                    try:
                        if hasattr(vc, "move_to"):
                            await vc.move_to(channel)
                    except Exception:
                        pass
                return vc
        raise




async def play_track_on_voice(voice_client, track, *, loop: asyncio.AbstractEventLoop = None, options: str = "-vn", seek_time: int = 0, volume: float = 1.0):
    """Play a Track on a connected discord.VoiceClient.

    This function constructs an FFmpegPCMAudio source from track.stream_url,
    wraps it in a PCMVolumeTransformer, and plays it.
    It returns after playback completes. It does not start any queue logic; the caller should manage the queue.
    """
    if not voice_client or not getattr(voice_client, "is_connected", lambda: True)():
        logger.warning("Voice client is not connected to any voice channel.")
        return False
    if not track or not getattr(track, "stream_url", None):
        logger.error("Cannot play track '%s': stream_url is missing or invalid.", getattr(track, "title", "unknown"))
        return False



    try:
        import discord
    except Exception:
        logger.exception("discord library not available for playback")
        raise

    # Prepare ffmpeg audio source with -nostdin and reconnect options for HTTP streams
    before_options = "-nostdin -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"

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
