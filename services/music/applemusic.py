"""Apple Music track & playlist metadata resolver."""
import logging
import re
import json
import urllib.request
import urllib.parse
import asyncio
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)
_executor = ThreadPoolExecutor(max_workers=2)


def is_applemusic_url(url: str) -> bool:
    """Check if the provided URL is an Apple Music link."""
    if not url:
        return False
    u = url.lower()
    return "music.apple.com" in u or "apple.co" in u


def _fetch_applemusic_sync(url: str) -> List[Dict[str, Any]]:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }

    # 1. Try Apple Music oEmbed API
    oembed_url = f"https://music.apple.com/api/oembed?url={urllib.parse.quote(url)}"
    try:
        req = urllib.request.Request(oembed_url, headers=headers)
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                title = data.get("title") or "Apple Music Track"
                author = data.get("author_name") or "Apple Music"
                thumb = data.get("thumbnail_url")
                return [{
                    "title": title,
                    "artist": author,
                    "duration": None,
                    "thumbnail": thumb,
                    "search_query": f"{title} {author}",
                    "url": url,
                }]
    except Exception as err:
        logger.debug("Apple Music oEmbed failed: %s", err)

    # 2. Fallback: Parse Apple Music webpage HTML for meta tags & Schema JSON
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=6) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        tracks = []
        # Search for Schema JSON-LD scripts
        json_matches = re.findall(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, re.DOTALL)
        for match in json_matches:
            try:
                data = json.loads(match.strip())
                if isinstance(data, dict):
                    # Single MusicRecording
                    if data.get("@type") == "MusicRecording":
                        t_name = data.get("name") or "Apple Music Song"
                        by_artist = data.get("byArtist")
                        artist_name = "Apple Music"
                        if isinstance(by_artist, dict):
                            artist_name = by_artist.get("name") or artist_name
                        elif isinstance(by_artist, list) and by_artist:
                            artist_name = by_artist[0].get("name") if isinstance(by_artist[0], dict) else artist_name
                        
                        thumb = data.get("image")
                        if isinstance(thumb, list) and thumb:
                            thumb = thumb[0]

                        tracks.append({
                            "title": t_name,
                            "artist": artist_name,
                            "duration": None,
                            "thumbnail": thumb,
                            "search_query": f"{t_name} {artist_name}",
                            "url": url,
                        })
                    # MusicAlbum / MusicPlaylist
                    elif data.get("@type") in ("MusicAlbum", "MusicPlaylist") or "track" in data:
                        raw_tracks = data.get("track") or data.get("tracks") or []
                        if isinstance(raw_tracks, dict) and "itemListElement" in raw_tracks:
                            raw_tracks = raw_tracks["itemListElement"]
                        
                        for item in raw_tracks:
                            if isinstance(item, dict):
                                item_obj = item.get("item") if "item" in item else item
                                t_name = item_obj.get("name") or "Track"
                                by_artist = item_obj.get("byArtist") or data.get("byArtist")
                                artist_name = "Apple Music"
                                if isinstance(by_artist, dict):
                                    artist_name = by_artist.get("name") or artist_name
                                elif isinstance(by_artist, list) and by_artist:
                                    artist_name = by_artist[0].get("name") if isinstance(by_artist[0], dict) else artist_name

                                tracks.append({
                                    "title": t_name,
                                    "artist": artist_name,
                                    "duration": None,
                                    "thumbnail": data.get("image"),
                                    "search_query": f"{t_name} {artist_name}",
                                    "url": url,
                                })
            except Exception:
                continue

        if tracks:
            return tracks

        # 3. Fallback: OpenGraph Meta Tags
        og_title = re.search(r'<meta[^>]*property=["\']og:title["\'][^>]*content=["\'](.*?)["\']', html)
        og_desc = re.search(r'<meta[^>]*property=["\']og:description["\'][^>]*content=["\'](.*?)["\']', html)
        og_img = re.search(r'<meta[^>]*property=["\']og:image["\'][^>]*content=["\'](.*?)["\']', html)

        if og_title:
            t_str = og_title.group(1)
            a_str = og_desc.group(1) if og_desc else "Apple Music"
            return [{
                "title": t_str,
                "artist": a_str,
                "duration": None,
                "thumbnail": og_img.group(1) if og_img else None,
                "search_query": f"{t_str} {a_str}",
                "url": url,
            }]
    except Exception as err:
        logger.warning("Apple Music HTML extraction failed for %s: %s", url, err)

    return []


async def fetch_applemusic_tracks(url: str) -> List[Dict[str, Any]]:
    """Fetch Apple Music tracks (single song, album, or playlist)."""
    loop = asyncio.get_running_loop()
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(_executor, _fetch_applemusic_sync, url),
            timeout=8.0
        )
    except Exception as err:
        logger.warning("Apple Music resolution timed out or failed for %s: %s", url, err)
        return []
