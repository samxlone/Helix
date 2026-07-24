import aiohttp
import re
from typing import Optional, Tuple
import urllib.parse
import logging

logger = logging.getLogger(__name__)

def clean_song_info(title: str, author: str = None) -> Tuple[str, str]:
    """Clean the YouTube video title and author to extract (artist, song_title)."""
    # Remove emojis and common tags
    clean = re.sub(r'[\u2600-\u27BF]|[\u2000-\u3300]|[\uD83C-\uD83E][\uDC00-\uDFFF]', '', title)
    
    # Remove text in parentheses/brackets like (Official Video), [Lyrics], etc.
    clean = re.sub(r'\([^)]*\)', '', clean)
    clean = re.sub(r'\[[^\]]*\]', '', clean)
    
    # Clean multiple spaces
    clean = " ".join(clean.split())
    
    artist, song = "", clean
    
    # Check if there's a dash separating artist and song
    for sep in (" - ", " – ", " — ", "-"):
        if sep in clean:
            parts = clean.split(sep, 1)
            artist = parts[0].strip()
            song = parts[1].strip()
            break
            
    # If no artist extracted, fallback to track author if provided
    if not artist and author:
        clean_author = re.sub(r'(VEVO|Vevo|Official|Topic|Music|Records|T-Series|TSeries)', '', author, flags=re.I).strip()
        artist = clean_author
        
    return artist, song

async def fetch_lyrics(title: str, author: str = None) -> Optional[str]:
    """Fetch lyrics from lyrics.ovh API."""
    artist, song = clean_song_info(title, author)
    if not artist:
        artist = "Various Artists"
        
    enc_artist = urllib.parse.quote(artist)
    enc_song = urllib.parse.quote(song)
    
    url = f"https://api.lyrics.ovh/v1/{enc_artist}/{enc_song}"
    logger.info("Lyrics: Fetching from %s", url)
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    lyrics = data.get("lyrics")
                    if lyrics:
                        return lyrics.strip()
        except Exception as e:
            logger.warning("Lyrics fetch failed for %s - %s: %s", artist, song, e)
            
    if artist == "Various Artists" and author:
        artist = re.sub(r'(VEVO|Vevo|Official|Topic|Music|Records|T-Series|TSeries)', '', author, flags=re.I).strip()
        url = f"https://api.lyrics.ovh/v1/{urllib.parse.quote(artist)}/{enc_song}"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        lyrics = data.get("lyrics")
                        if lyrics:
                            return lyrics.strip()
            except Exception:
                pass
                
    return None
