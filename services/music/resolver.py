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
    # URL-like
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
                    # IMPORTANT: use stream_url from metadata (direct playable stream)
                    # fallback chain: stream_url -> url -> webpage_url -> query
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
        stream_url=None,
        is_live=False,
        is_playlist=False,
    )
    _resolver_cache.set(q, t)
    return t
