import logging
import re
import asyncio
from .models import Track
from .resolver import resolve

logger = logging.getLogger(__name__)


def get_video_id(url: str) -> str:
    if not url:
        return None
    match = re.search(r'(?:v=|\/v\/|embed\/|youtu\.be\/|shorts\/)([a-zA-Z0-9_-]{11})', url)
    return match.group(1) if match else None


class Autoplay:
    def __init__(self):
        # Cache of recently played URLs in autoplay session to avoid loops
        self.played_urls = set()

    async def recommend(self, last_track: Track) -> Track:
        if not last_track:
            return None

        self.played_urls.add(last_track.url)
        video_id = get_video_id(last_track.url)
        
        # 1. Try extracting related videos from YouTube Mix playlist (list=RDVIDEO_ID)
        if video_id:
            mix_url = f"https://www.youtube.com/watch?v={video_id}&list=RD{video_id}"
            logger.info("Autoplay: Attempting flat Mix extraction for RD playlist: %s", mix_url)
            try:
                import yt_dlp
                ydl_opts = {
                    "skip_download": True,
                    "quiet": True,
                    "no_warnings": True,
                    "socket_timeout": 5,
                    "ignoreerrors": True,
                    "extract_flat": True,
                    "playlist_items": "2,3,4,5", # Entries 2-5 (excluding the song itself)
                }
                
                # Run yt-dlp in executor to prevent blocking the event loop
                loop = asyncio.get_running_loop()
                def extract():
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        return ydl.extract_info(mix_url, download=False)
                        
                info = await loop.run_in_executor(None, extract)
                entries = info.get("entries") or []
                
                for entry in entries:
                    if not entry or not entry.get("id"):
                        continue
                    candidate_id = entry["id"]
                    candidate_url = f"https://www.youtube.com/watch?v={candidate_id}"
                    
                    if candidate_id == video_id or candidate_url in self.played_urls:
                        continue
                        
                    # Resolve this candidate to a playable Track
                    logger.info("Autoplay: Selected mix recommendation: %s (ID: %s)", entry.get("title"), candidate_id)
                    track = await resolve(candidate_url)
                    if track and track.stream_url:
                        entry_title = entry.get("title")
                        if entry_title and not entry_title.startswith("http"):
                            track.title = entry_title
                        elif track.title and track.title.startswith("http"):
                            track.title = f"YouTube Video ({candidate_id})"
                        clean_t = track.title.replace("📻", "").strip()
                        track.title = f"{clean_t} 📻"
                        return track
            except Exception as e:
                logger.warning("Autoplay: Mix extraction failed, falling back to search: %s", e)


        # 2. Fallback: Search YouTube for similar songs
        clean_title = last_track.title.replace("📻", "").strip()
        search_terms = []
        if last_track.author and last_track.author not in clean_title:
            search_terms.append(last_track.author)
        search_terms.append(clean_title)
        query_str = f"music similar to {' '.join(search_terms)}"
        logger.info("Autoplay Fallback: Searching similar track with query: %s", query_str)

        try:
            track = await resolve(query_str)
            if track and track.stream_url:
                if track.url not in self.played_urls and track.title.lower() != clean_title.lower():
                    track.title = f"{track.title.replace('📻', '').strip()} 📻"
                    return track
        except Exception as e:
            logger.warning("Autoplay Fallback: Failed to recommend: %s", e)

            
        return None


