from typing import List, Union
from .models import Track
from .providers import YouTubeProvider
from .cache import SimpleCache
import logging

logger = logging.getLogger(__name__)

# small resolver cache for metadata lookups
_resolver_cache = SimpleCache(ttl=3600)


async def resolve(query: str, requester: int = None) -> Union[Track, List[Track], None]:
    """Resolve a query or URL into a Track or list of Tracks.

    Enhanced resolver:
    - If query is a URL, try provider detection (YouTubeProvider currently)
    - If provider recognized, fetch metadata and return a Track constructed from it
    - Otherwise, fallback to search-style Track
    """
    if not query:
        return None
    q = query.strip()
    # Spotify URL / URI Handling
    from .spotify import is_spotify_url, fetch_spotify_tracks
    if is_spotify_url(q):
        try:
            sp_tracks = await fetch_spotify_tracks(q)
            if sp_tracks:
                yt = YouTubeProvider()
                resolved_tracks: List[Track] = []
                
                # Resolve Track 0 immediately so playback starts instantly (< 1 sec)
                first_sp = sp_tracks[0]
                first_search = first_sp.get("search_query") or first_sp.get("title") or "song"
                first_meta = await yt.fetch_metadata(f"ytsearch1:{first_search}")
                
                first_stream = first_meta.get("stream_url") if first_meta else None
                if not first_stream and first_meta:
                    first_stream = first_meta.get("url") or first_meta.get("webpage_url")
                if not first_stream:
                    first_stream = first_search

                first_track = Track(
                    title=first_sp.get("title") or (first_meta.get("title") if first_meta else first_search),
                    author=first_sp.get("artist") or (first_meta.get("uploader") if first_meta else "Unknown"),
                    duration=first_meta.get("duration") if first_meta else first_sp.get("duration"),
                    url=q,
                    thumbnail=first_sp.get("thumbnail") or (first_meta.get("thumbnail") if first_meta else None),
                    requester=requester,
                    provider="spotify",
                    stream_url=first_stream,
                    is_live=False,
                    is_playlist=len(sp_tracks) > 1,
                    http_headers=first_meta.get("http_headers") if first_meta else None,
                )
                resolved_tracks.append(first_track)

                # For remaining tracks, create placeholder Track objects instantly.
                # Stream URLs will be resolved on-demand right before each track plays!
                for sp_item in sp_tracks[1:]:
                    s_title = sp_item.get("title") or "Unknown Title"
                    s_artist = sp_item.get("artist") or "Unknown Artist"
                    s_search = sp_item.get("search_query") or f"{s_title} {s_artist}"
                    
                    t = Track(
                        title=s_title,
                        author=s_artist,
                        duration=sp_item.get("duration"),
                        url=q,
                        thumbnail=sp_item.get("thumbnail"),
                        requester=requester,
                        provider="spotify",
                        stream_url=s_search,  # placeholder search term for on-demand resolution
                        is_live=False,
                        is_playlist=True,
                    )
                    resolved_tracks.append(t)

                if len(resolved_tracks) == 1:
                    return resolved_tracks[0]
                elif len(resolved_tracks) > 1:
                    return resolved_tracks
        except Exception:
            logger.exception("Spotify resolution failed for %s", q)

    # SoundCloud URL Handling
    from .soundcloud import is_soundcloud_url, fetch_soundcloud_tracks
    if is_soundcloud_url(q):
        try:
            sc_tracks = await fetch_soundcloud_tracks(q)
            if sc_tracks:
                yt = YouTubeProvider()
                resolved_tracks: List[Track] = []
                
                # First track
                first_sc = sc_tracks[0]
                first_stream = first_sc.get("stream_url")
                http_hdrs = None
                if not first_stream or not (first_stream.startswith("http://") or first_stream.startswith("https://")):
                    meta = await yt.fetch_metadata(f"ytsearch1:{first_sc.get('search_query')}")
                    if meta:
                        first_stream = meta.get("stream_url") or meta.get("url")
                        http_hdrs = meta.get("http_headers")
                
                first_track = Track(
                    title=first_sc.get("title") or "SoundCloud Track",
                    author=first_sc.get("artist") or "SoundCloud",
                    duration=first_sc.get("duration"),
                    url=q,
                    thumbnail=first_sc.get("thumbnail"),
                    requester=requester,
                    provider="soundcloud",
                    stream_url=first_stream or first_sc.get("search_query"),
                    is_live=False,
                    is_playlist=len(sc_tracks) > 1,
                    http_headers=http_hdrs,
                )
                resolved_tracks.append(first_track)

                # Remaining tracks
                for item in sc_tracks[1:]:
                    t = Track(
                        title=item.get("title") or "SoundCloud Track",
                        author=item.get("artist") or "SoundCloud",
                        duration=item.get("duration"),
                        url=q,
                        thumbnail=item.get("thumbnail"),
                        requester=requester,
                        provider="soundcloud",
                        stream_url=item.get("stream_url") or item.get("search_query"),
                        is_live=False,
                        is_playlist=True,
                    )
                    resolved_tracks.append(t)

                if len(resolved_tracks) == 1:
                    return resolved_tracks[0]
                elif len(resolved_tracks) > 1:
                    return resolved_tracks
        except Exception:
            logger.exception("SoundCloud resolution failed for %s", q)

    # Apple Music URL Handling
    from .applemusic import is_applemusic_url, fetch_applemusic_tracks
    if is_applemusic_url(q):
        try:
            am_tracks = await fetch_applemusic_tracks(q)
            if am_tracks:
                yt = YouTubeProvider()
                resolved_tracks: List[Track] = []

                # Resolve Track 0 immediately
                first_am = am_tracks[0]
                first_search = first_am.get("search_query") or first_am.get("title") or "song"
                first_meta = await yt.fetch_metadata(f"ytsearch1:{first_search}")

                first_stream = first_meta.get("stream_url") if first_meta else None
                if not first_stream and first_meta:
                    first_stream = first_meta.get("url") or first_meta.get("webpage_url")
                if not first_stream:
                    first_stream = first_search

                first_track = Track(
                    title=first_am.get("title") or "Apple Music Track",
                    author=first_am.get("artist") or "Apple Music",
                    duration=first_meta.get("duration") if first_meta else first_am.get("duration"),
                    url=q,
                    thumbnail=first_am.get("thumbnail") or (first_meta.get("thumbnail") if first_meta else None),
                    requester=requester,
                    provider="applemusic",
                    stream_url=first_stream,
                    is_live=False,
                    is_playlist=len(am_tracks) > 1,
                    http_headers=first_meta.get("http_headers") if first_meta else None,
                )
                resolved_tracks.append(first_track)

                # Remaining tracks placeholders
                for am_item in am_tracks[1:]:
                    a_title = am_item.get("title") or "Unknown Title"
                    a_artist = am_item.get("artist") or "Unknown Artist"
                    a_search = am_item.get("search_query") or f"{a_title} {a_artist}"

                    t = Track(
                        title=a_title,
                        author=a_artist,
                        duration=am_item.get("duration"),
                        url=q,
                        thumbnail=am_item.get("thumbnail"),
                        requester=requester,
                        provider="applemusic",
                        stream_url=a_search,
                        is_live=False,
                        is_playlist=True,
                    )
                    resolved_tracks.append(t)

                if len(resolved_tracks) == 1:
                    return resolved_tracks[0]
                elif len(resolved_tracks) > 1:
                    return resolved_tracks
        except Exception:
            logger.exception("Apple Music resolution failed for %s", q)



    # Standard URL-like (YouTube, Direct URLs, etc.)
    if q.startswith("http://") or q.startswith("https://"):
        # Try YouTube detection first
        yt = YouTubeProvider()
        try:
            if await yt.detect(q):
                # fetch metadata (cached inside provider too)
                meta = await yt.fetch_metadata(q)
                if meta:
                    title = meta.get("title") or q
                    duration = meta.get("duration")
                    thumbnail = meta.get("thumbnail")
                    provider_name = yt.name
                    stream_url = meta.get("stream_url") or meta.get("url") or meta.get("webpage_url") or q
                    logger.debug("Resolver: selected stream_url=%s (from meta keys: %s)", stream_url[:80] if stream_url else None, list(meta.keys())[:5])
                    t = Track(
                        title=title,
                        author=meta.get("uploader"),
                        duration=duration,
                        url=q,
                        thumbnail=thumbnail,
                        requester=requester,
                        provider=provider_name,
                        stream_url=stream_url,
                        is_live=meta.get("is_live", False),
                        is_playlist=meta.get("_type") == "playlist",
                        http_headers=meta.get("http_headers"),
                    )
                    return t
        except Exception:
            logger.exception("Provider detection/metadata failed for %s", q)
        # fallback to plain URL Track
        t = Track(
            title=q,
            author=None,
            duration=None,
            url=q,
            thumbnail=None,
            requester=requester,
            provider="url",
            stream_url=q,
            is_live=False,
            is_playlist=False,
        )
        return t


    # treat as search term
    # check resolver cache
    cached = _resolver_cache.get(q)
    if cached:
        return cached

    yt = YouTubeProvider()
    search_query = f"ytsearch1:{q}"
    try:
        meta = await yt.fetch_metadata(search_query)
        if meta:
            title = meta.get("title") or q
            duration = meta.get("duration")
            thumbnail = meta.get("thumbnail")
            provider_name = "youtube"
            stream_url = meta.get("stream_url") or meta.get("url") or meta.get("webpage_url") or q
            t = Track(
                title=title,
                author=meta.get("uploader"),
                duration=duration,
                url=meta.get("url") or q,
                thumbnail=thumbnail,
                requester=requester,
                provider=provider_name,
                stream_url=stream_url,
                is_live=meta.get("is_live", False),
                is_playlist=False,
                http_headers=meta.get("http_headers"),
            )
            _resolver_cache.set(q, t)
            return t
    except Exception:
        logger.exception("YouTube search resolution failed for %s", q)

    t = Track(
        title=q,
        author="Unknown",
        duration=180,
        url=f"search:{q}",
        thumbnail=None,
        requester=requester,
        provider="search",
        stream_url=q,
        is_live=False,

        is_playlist=False,
    )
    _resolver_cache.set(q, t)
    return t
