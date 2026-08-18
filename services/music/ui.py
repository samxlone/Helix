"""Modern Luxury UI helpers for building music embeds, progress bars, and custom styled components."""
import discord
from typing import Optional, Dict, Any


def build_now_playing(track) -> Dict[str, Any]:
    """Legacy helper returning track dict for testing."""
    if not track:
        return {"title": "Nothing playing"}
    return {
        "title": getattr(track, "title", "Unknown"),
        "author": getattr(track, "author", "Unknown"),
        "duration": getattr(track, "duration", None),
        "url": getattr(track, "url", ""),
        "thumbnail": getattr(track, "thumbnail", None),
        "provider": getattr(track, "provider", "youtube"),
        "is_live": getattr(track, "is_live", False),
    }



# Premium Icon Constants
EMOJI_MUSIC = "🎶"
EMOJI_DISC = "💿"
EMOJI_EQ = "🎛️"
EMOJI_SPARKLES = "✨"
EMOJI_FIRE = "🔥"
EMOJI_DIAMOND = "💎"
EMOJI_USER = "👤"
EMOJI_CLOCK = "⏱️"
EMOJI_STAR = "⭐"
EMOJI_HEADPHONES = "🎧"
EMOJI_REPEAT = "🔁"
EMOJI_AUTOPLAY = "📻"
EMOJI_WAVE = "🌊"


def format_time(seconds: Optional[int]) -> str:
    """Format seconds into HH:MM:SS or MM:SS format."""
    if seconds is None or seconds < 0:
        return "00:00"
    mins, secs = divmod(int(seconds), 60)
    hours, mins = divmod(mins, 60)
    if hours > 0:
        return f"{hours:02d}:{mins:02d}:{secs:02d}"
    return f"{mins:02d}:{secs:02d}"


def render_progress_bar(current_sec: int, total_sec: Optional[int], length: int = 8) -> str:
    """Render a mobile-perfect compact progress bar that fits on a single line on any screen."""
    if not total_sec or total_sec <= 0:
        return "`[LIVE STREAM]` 🔴 ▰▰▰▰▰▰▰▰"

    pct = min(1.0, max(0.0, current_sec / total_sec))
    filled_len = int(pct * length)
    empty_len = max(0, length - filled_len)

    bar = "▰" * filled_len + "▱" * empty_len
    current_str = format_time(current_sec)
    total_str = format_time(total_sec)
    return f"`[{current_str}/{total_str}]` {bar}"


def build_started_playing_embed(track, guild_name: str, bot_instance=None, player_instance=None, current_sec: int = 0) -> discord.Embed:
    """Build a vibrant, mobile-optimized Now Playing embed."""
    title_str = (getattr(track, "title", None) or "Unknown Track").strip()
    url_str = (getattr(track, "url", None) or "").strip()

    if title_str.startswith("http://") or title_str.startswith("https://") or title_str == url_str:
        track_link = f"**{title_str}**"
    else:
        safe_title = title_str.replace("[", "\\[").replace("]", "\\]")
        if url_str:
            track_link = f"**[{safe_title}]({url_str})**"
        else:
            track_link = f"**{safe_title}**"

    artist = getattr(track, "author", None) or "Unknown Artist"
    duration_sec = getattr(track, "duration", None)
    requester_id = getattr(track, "requester", None)
    requester_str = f"<@{requester_id}>" if requester_id else "Autoplay 📻"

    eq_preset = "Flat"
    loop_str = "Off"
    autoplay_str = "Disabled"

    if player_instance:
        raw_eq = getattr(player_instance, "eq_preset_name", "flat")
        eq_preset = raw_eq.replace("_", " ").title() if raw_eq else "Flat"
        q = player_instance.get_queue()
        if q.loop_mode == "song":
            loop_str = "🔂 Song"
        elif q.loop_mode == "queue":
            loop_str = "🔁 Queue"
        if getattr(player_instance, "autoplay_enabled", False):
            autoplay_str = "Enabled 📻"

    progress_bar = render_progress_bar(current_sec, duration_sec)

    description = (
        f"> 🎵 {track_link}\n\n"
        f"👤 **Artist:** `{artist}`\n"
        f"⏱️ **Progress:** {progress_bar}\n"
        f"🎛️ **EQ:** `{eq_preset}` • 🔁 **Loop:** `{loop_str}` • 📻 **Autoplay:** `{autoplay_str}`\n"
        f"👤 **Requested by:** {requester_str}"
    )

    embed = discord.Embed(
        title="🎶 NOW PLAYING",
        description=description,
        color=discord.Color.from_rgb(88, 101, 242),  # Vibrant Cyber Blue
    )

    if getattr(track, "thumbnail", None):
        embed.set_thumbnail(url=track.thumbnail)

    from utils.embed_utils import set_owner_footer
    set_owner_footer(embed, bot_instance, extra_text=f"💎 HELIX MUSIC ENGINE • {guild_name}")



    return embed


