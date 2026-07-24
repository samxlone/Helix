"""UI helpers for building now-playing information.
This module returns plain dicts for easy testing; later it can produce discord.Embed and components.
"""
from .models import Track
from typing import Dict, Any, Optional


def build_now_playing(track: Track) -> Dict[str, Any]:
    if not track:
        return {"title": "Nothing playing"}
    return {
        "title": track.title,
        "author": track.author,
        "duration": track.duration,
        "url": track.url,
        "thumbnail": track.thumbnail,
        "provider": track.provider,
        "is_live": track.is_live,
    }
