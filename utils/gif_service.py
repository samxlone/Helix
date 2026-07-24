import urllib.request
import re
import random
import logging
import asyncio
from urllib.parse import quote
from typing import List

logger = logging.getLogger(__name__)


async def search_gifs(query: str) -> List[str]:
    """Search Tenor and Giphy keyless via web scraping and return a list of GIF URLs."""
    results = []

    # 1. Search Tenor
    try:
        tenor_url = f"https://tenor.com/search/{quote(query)}-gifs"
        req = urllib.request.Request(
            tenor_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            },
        )
        loop = asyncio.get_event_loop()

        def fetch_tenor():
            with urllib.request.urlopen(req, timeout=5) as response:
                return response.read().decode("utf-8")

        html = await loop.run_in_executor(None, fetch_tenor)
        # Match media tenor links
        tenor_gifs = re.findall(r"https://media\.tenor\.com/[a-zA-Z0-9_\-\/]+\.gif", html)
        results.extend(tenor_gifs)
    except Exception as e:
        logger.warning("Failed to search Tenor: %s", e)

    # 2. Search Giphy
    try:
        giphy_url = f"https://giphy.com/search/{quote(query)}"
        req = urllib.request.Request(
            giphy_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            },
        )
        loop = asyncio.get_event_loop()

        def fetch_giphy():
            with urllib.request.urlopen(req, timeout=5) as response:
                return response.read().decode("utf-8")

        html = await loop.run_in_executor(None, fetch_giphy)
        # Match media giphy links
        giphy_gifs = re.findall(r"https://media\d*\.giphy\.com/media/[a-zA-Z0-9_.\-\/]+/giphy\.gif", html)
        results.extend(giphy_gifs)
    except Exception as e:
        logger.warning("Failed to search Giphy: %s", e)

    # Deduplicate while preserving order roughly
    seen = set()
    unique_results = []
    for r in results:
        if r not in seen:
            seen.add(r)
            unique_results.append(r)

    return unique_results
