import logging
from typing import Optional
from .cache import SimpleCache
import asyncio
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse, parse_qs, urlunparse, urlencode

logger = logging.getLogger(__name__)

cache = SimpleCache(ttl=3600)
_executor = ThreadPoolExecutor(max_workers=2)  # limit concurrent yt-dlp threads


class Provider:
    """Base provider interface."""

    name: str = "base"

    async def detect(self, url: str) -> bool:
        return False

    async def fetch_metadata(self, url: str) -> Optional[dict]:
        return None


class YouTubeProvider(Provider):
    name = "youtube"

    def _clean_url(self, url: str) -> str:
        """Clean a YouTube URL to remove playlist parameter if a video ID is present.
        
        This prevents yt-dlp from attempting to parse/fetch metadata for an entire playlist
        when a user only wanted to play a single video.
        """
        if "youtube.com" not in url and "youtu.be" not in url:
            return url
        try:
            parsed = urlparse(url)
            query = parse_qs(parsed.query)
            if "youtube.com" in parsed.netloc:
                if "v" in query:
                    query.pop("list", None)
                    query.pop("index", None)
                    new_query = urlencode(query, doseq=True)
                    parsed = parsed._replace(query=new_query)
                    return urlunparse(parsed)
            elif "youtu.be" in parsed.netloc:
                query.pop("list", None)
                query.pop("index", None)
                new_query = urlencode(query, doseq=True)
                parsed = parsed._replace(query=new_query)
                return urlunparse(parsed)
        except Exception as e:
            logger.debug("Failed to clean YouTube URL %s: %s", url, e)
        return url

    async def detect(self, url: str) -> bool:
        try:
            return "youtube.com" in url or "youtu.be" in url
        except Exception:
            return False

    async def fetch_metadata(self, url: str) -> Optional[dict]:
        """Fetch metadata for a YouTube URL using yt-dlp if available.

        This function runs yt-dlp in a thread pool to avoid blocking the async event loop.
        Results are cached for ttl seconds.
        """
        url = self._clean_url(url)
        cached = cache.get(url)
        if cached:
            return cached
        
        try:
            # lazy import to avoid hard dependency at import time
            import yt_dlp as ytdl
        except Exception:
            # yt-dlp not available; fall back to a lightweight stub
            logger.debug("yt_dlp not available, returning stub metadata for %s", url)
            meta = {"title": url, "duration": 180, "uploader": "yt-stub", "url": url, "stream_url": url}
            cache.set(url, meta)
            return meta

        # Run yt-dlp in thread pool with timeout to avoid blocking event loop
        loop = asyncio.get_event_loop()
        try:
            info = await asyncio.wait_for(
                loop.run_in_executor(_executor, self._extract_info, url, ytdl),
                timeout=15.0  # 15 second timeout for metadata extraction
            )
            if not info:
                return None

            if "entries" in info:
                entries = info.get("entries") or []
                if entries:
                    info = entries[0]
                else:
                    return None

            stream_url = None
            format_id = None
            
            # Try to get the direct stream URL from the selected format
            if "url" in info:
                stream_url = info.get("url")
                format_id = info.get("format_id")
                logger.debug("Got stream URL from info['url']: %s (format: %s)", stream_url[:80] if stream_url else None, format_id)
            
            # fallback: try formats list
            if not stream_url:
                formats = info.get("formats") or []
                if formats:
                    # prefer audio-only formats
                    audio_formats = [f for f in formats if f.get("acodec") and f.get("acodec") != "none"]
                    if not audio_formats:
                        audio_formats = formats

                    def score(f):
                        return (f.get("abr") or f.get("tbr") or f.get("filesize") or 0)

                    if audio_formats:
                        best = max(audio_formats, key=score)
                        stream_url = best.get("url")
                        format_id = best.get("format_id") or best.get("format")
                        logger.debug("Got stream URL from formats list: %s (format: %s)", stream_url[:80] if stream_url else None, format_id)

            # final fallback (use webpage_url for FFmpeg to fetch)
            if not stream_url:
                stream_url = info.get("webpage_url") or url
                logger.warning("Using webpage_url as stream_url fallback: %s", stream_url[:80])

            meta = {
                "title": info.get("title"),
                "duration": info.get("duration"),
                "uploader": info.get("uploader") or info.get("uploader_id"),
                "thumbnail": info.get("thumbnail"),
                "is_live": info.get("is_live", False),
                "url": info.get("webpage_url") or url,
                "stream_url": stream_url,
                "format_id": format_id,
                "http_headers": info.get("http_headers"),
                "raw": info,
            }
            logger.info("YouTube metadata extracted: title=%s, duration=%s, stream_url=%s", info.get("title"), info.get("duration"), stream_url[:80] if stream_url else None)
            cache.set(url, meta)
            return meta
        
        except asyncio.TimeoutError:
            logger.exception("YouTube metadata fetch timed out after 15s for %s", url)
            return None
        except Exception:
            logger.exception("Failed to fetch YouTube metadata for %s", url)
            return None

    @staticmethod
    def _extract_info(url: str, ytdl):
        """Blocking yt-dlp extraction to run in thread pool."""
        ydl_opts = {
            "skip_download": True,
            "quiet": True,
            "no_warnings": True,
            "format": "bestaudio/best",
            "no_playlist": True,
            "socket_timeout": 10,
            "nocheckcertificate": True,
            "geo_bypass": True,
            "extractor_args": {
                "youtube": {
                    "player_client": ["tvhtml5", "android", "ios", "mweb"],

                    "skip": ["dash", "hls"],
                }
            },
            "http_headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9",
            }
        }

        # Attempt 1: Standard YouTube extraction with Android/iOS client spoofing
        try:
            with ytdl.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if info:
                    return info
        except Exception as exc:
            logger.warning("Primary yt-dlp extraction failed for %s: %s", url, exc)

        # Attempt 2: Fallback Android-only client extraction
        try:
            ydl_opts_fallback = dict(ydl_opts)
            ydl_opts_fallback["extractor_args"] = {
                "youtube": {
                    "player_client": ["android"],
                }
            }
            with ytdl.YoutubeDL(ydl_opts_fallback) as ydl:
                info = ydl.extract_info(url, download=False)
                if info:
                    return info
        except Exception as exc:
            logger.warning("Secondary yt-dlp extraction failed for %s: %s", url, exc)

        # Attempt 3: If search query and YouTube is bot-blocked, fallback to SoundCloud search
        if not (url.startswith("http://") or url.startswith("https://")):
            clean_query = url.replace("ytsearch1:", "").replace("ytsearch:", "").strip()
            sc_query = f"scsearch1:{clean_query}"
            logger.info("Attempting SoundCloud fallback search for: %s", sc_query)
            try:
                sc_opts = {
                    "skip_download": True,
                    "quiet": True,
                    "no_warnings": True,
                    "format": "bestaudio/best",
                    "no_playlist": True,
                    "socket_timeout": 10,
                }
                with ytdl.YoutubeDL(sc_opts) as ydl:
                    info = ydl.extract_info(sc_query, download=False)
                    if info:
                        return info
            except Exception as sc_exc:
                logger.warning("SoundCloud fallback extraction failed for %s: %s", sc_query, sc_exc)

        return None


YTDLPProvider = YouTubeProvider
YtDlpProvider = YouTubeProvider


