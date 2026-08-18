"""SoundCloud metadata and track resolver using yt-dlp with HTML meta fallback."""
import logging
import asyncio
import re
import urllib.request
import urllib.parse
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)
_executor = ThreadPoolExecutor(max_workers=2)


def is_soundcloud_url(url: str) -> bool:
    """Check if the provided URL is a SoundCloud link."""
    if not url:
        return False
    u = url.lower()
    return "soundcloud.com" in u or "snd.sc" in u


def _extract_soundcloud_html_fallback(url: str) -> List[Dict[str, Any]]:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=6) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        og_title = re.search(r'<meta[^>]*property=["\']og:title["\'][^>]*content=["\'](.*?)["\']', html)
        og_img = re.search(r'<meta[^>]*property=["\']og:image["\'][^>]*content=["\'](.*?)["\']', html)

        if og_title:
            raw_title = og_title.group(1).strip()
            # SoundCloud titles often look like "Song Title by Artist Name" or "Artist - Song Title"
            artist = "SoundCloud"
            title = raw_title
            if " by " in raw_title:
                parts = raw_title.split(" by ", 1)
                title = parts[0].strip()
                artist = parts[1].strip()
            elif " - " in raw_title:
                parts = raw_title.split(" - ", 1)
                artist = parts[0].strip()
                title = parts[1].strip()

            return [{
                "title": title,
                "artist": artist,
                "duration": None,
                "thumbnail": og_img.group(1) if og_img else None,
                "search_query": f"{title} {artist}",
                "stream_url": f"{title} {artist}",
                "url": url,
            }]
    except Exception as err:
        logger.warning("SoundCloud HTML fallback failed for %s: %s", url, err)

    return []


def _extract_soundcloud_sync(url: str) -> List[Dict[str, Any]]:
    try:
        import yt_dlp as ytdl
    except ImportError:
        return _extract_soundcloud_html_fallback(url)

    opts = {
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
        "format": "bestaudio/best",
        "extract_flat": "in_playlist",
        "socket_timeout": 8,
        "nocheckcertificate": True,
    }

    try:
        with ytdl.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info:
                results = []
                if "entries" in info and info["entries"]:
                    for entry in info["entries"]:
                        if not entry:
                            continue
                        t_title = entry.get("title") or "SoundCloud Track"
                        uploader = entry.get("uploader") or entry.get("artist") or info.get("uploader") or "SoundCloud"
                        results.append({
                            "title": t_title,
                            "artist": uploader,
                            "duration": entry.get("duration"),
                            "thumbnail": entry.get("thumbnail") or info.get("thumbnail"),
                            "search_query": f"{t_title} {uploader}",
                            "stream_url": entry.get("url") if (entry.get("url") and entry.get("url").startswith("http")) else f"{t_title} {uploader}",
                            "url": entry.get("url") or entry.get("webpage_url") or url,
                        })
                    if results:
                        return results
                else:
                    t_title = info.get("title") or "SoundCloud Track"
                    uploader = info.get("uploader") or info.get("artist") or "SoundCloud"
                    return [{
                        "title": t_title,
                        "artist": uploader,
                        "duration": info.get("duration"),
                        "thumbnail": info.get("thumbnail"),
                        "search_query": f"{t_title} {uploader}",
                        "stream_url": info.get("url") if (info.get("url") and info.get("url").startswith("http")) else f"{t_title} {uploader}",
                        "url": info.get("webpage_url") or url,
                    }]
    except Exception as err:
        logger.warning("yt-dlp SoundCloud extraction failed for %s: %s", url, err)

    return _extract_soundcloud_html_fallback(url)


async def fetch_soundcloud_tracks(url: str) -> List[Dict[str, Any]]:
    """Fetch SoundCloud tracks with fallback to HTML metadata parsing."""
    loop = asyncio.get_running_loop()
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(_executor, _extract_soundcloud_sync, url),
            timeout=10.0
        )
    except Exception as err:
        logger.warning("SoundCloud resolution timed out or failed for %s: %s", url, err)
        return _extract_soundcloud_html_fallback(url)
