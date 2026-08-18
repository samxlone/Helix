import asyncio
import json
import logging
import re
import ssl
import urllib.request
import urllib.parse
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

# Unverified SSL context for Spotify oEmbed / HTML requests
_ssl_context = ssl._create_unverified_context()


def is_spotify_url(url: str) -> bool:
    """Check if the given string is a Spotify URL or URI."""
    if not url:
        return False
    u = url.strip().lower()
    return "spotify.com" in u or u.startswith("spotify:")


async def fetch_spotify_tracks(url: str) -> List[Dict[str, str]]:
    """Fetch Spotify metadata for track/playlist/album URLs.

    Returns a list of dicts:
    [
        {
            "title": "Song Title",
            "artist": "Artist Name",
            "search_query": "Song Title Artist Name",
            "thumbnail": "http://...",
            "duration": 180,
            "playlist_name": "Playlist Name"
        },
        ...
    ]
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _fetch_spotify_tracks_sync, url)


def _fetch_spotify_tracks_sync(spotify_url: str) -> List[Dict[str, str]]:
    url = spotify_url.strip()
    # Normalize URI to HTTPS URL (e.g. spotify:track:123 -> https://open.spotify.com/track/123)
    if url.startswith("spotify:"):
        parts = url.split(":")
        if len(parts) >= 3:
            url = f"https://open.spotify.com/{parts[1]}/{parts[2]}"

    clean_url = url.split("?")[0]
    embed_url = clean_url.replace("open.spotify.com/", "open.spotify.com/embed/")

    playlist_name = None
    thumbnail_url = None

    # 1. Try Spotify oEmbed first for top-level title & thumbnail
    try:
        oembed_endpoint = f"https://open.spotify.com/oembed?url={urllib.parse.quote(url)}"
        req = urllib.request.Request(oembed_endpoint, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, context=_ssl_context, timeout=5) as resp:
            oembed_data = json.loads(resp.read().decode("utf-8"))
            playlist_name = oembed_data.get("title")
            thumbnail_url = oembed_data.get("thumbnail_url")
    except Exception as exc:
        logger.debug("Spotify oEmbed lookup failed for %s: %s", url, exc)

    # 2. Fetch Embed HTML to parse __NEXT_DATA__ JSON script
    tracks = []
    try:
        req_embed = urllib.request.Request(
            embed_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9",
            }
        )
        with urllib.request.urlopen(req_embed, context=_ssl_context, timeout=8) as resp:
            html = resp.read().decode("utf-8")
            match = re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>([^<]+)</script>', html)
            if match:
                data = json.loads(match.group(1))
                entity = data.get("props", {}).get("pageProps", {}).get("state", {}).get("data", {}).get("entity", {})
                
                entity_title = entity.get("name") or entity.get("title")
                if entity_title:
                    playlist_name = entity_title

                raw_tracks = entity.get("trackList", [])
                if not raw_tracks:
                    raw_tracks = entity.get("tracks", {}).get("items", []) or entity.get("items", [])
                if not raw_tracks and entity.get("type") in ("track", "single"):
                    raw_tracks = [entity]

                for t in raw_tracks:
                    title = t.get("title") or t.get("name")
                    if not title:
                        continue
                    
                    subtitle = t.get("subtitle") or t.get("artists") or ""
                    if isinstance(subtitle, list):
                        subtitle_str = ", ".join([a.get("name", "") if isinstance(a, dict) else str(a) for a in subtitle if a])
                    else:
                        subtitle_str = str(subtitle)
                    
                    # Clean up non-breaking spaces or trailing artifacts
                    subtitle_str = subtitle_str.replace("\xa0", " ").strip()
                    title = title.replace("\xa0", " ").strip()
                    
                    search_query = f"{title} {subtitle_str}".strip()
                    duration_ms = t.get("duration") or t.get("duration_ms") or 180000
                    duration = int(duration_ms / 1000) if isinstance(duration_ms, (int, float)) else 180
                    
                    tracks.append({
                        "title": title,
                        "artist": subtitle_str or "Unknown Artist",
                        "search_query": search_query,
                        "thumbnail": thumbnail_url,
                        "duration": duration,
                        "playlist_name": playlist_name or title,
                    })
    except Exception as exc:
        logger.exception("Failed to parse Spotify embed HTML for %s: %s", embed_url, exc)

    # Fallback if embed HTML parsing returned nothing
    if not tracks and playlist_name:
        tracks.append({
            "title": playlist_name,
            "artist": "Spotify",
            "search_query": playlist_name,
            "thumbnail": thumbnail_url,
            "duration": 180,
            "playlist_name": playlist_name,
        })

    return tracks
