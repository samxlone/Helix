import random
from typing import List, Optional
from .models import Track


class GuildQueue:
    """Simple in-memory queue for a guild.

    Features:
    - current: Track or None
    - upcoming: list[Track]
    - history: list[Track]
    - loop_mode: 'off' | 'song' | 'queue'
    """

    def __init__(self, guild_id: int):
        self.guild_id = guild_id
        self.current: Optional[Track] = None
        self.upcoming: List[Track] = []
        self.history: List[Track] = []
        self.loop_mode: str = "off"

    def enqueue(self, track: Track) -> int:
        """Append a track to the queue. Returns position (1-based)"""
        self.upcoming.append(track)
        return len(self.upcoming)

    def enqueue_next(self, track: Track) -> int:
        """Insert track to be next."""
        self.upcoming.insert(0, track)
        return 1

    def dequeue(self) -> Optional[Track]:
        """Pop next track respecting loop mode."""
        if not self.current and not self.upcoming:
            return None
        if self.loop_mode == "song" and self.current:
            # replay the same song
            return self.current
        if self.current and self.loop_mode == "queue":
            # push current into history and place at end of upcoming
            self.history.append(self.current)
            if self.current:
                self.upcoming.append(self.current)
        # advance
        if self.current:
            self.history.append(self.current)
        self.current = None
        if not self.upcoming:
            return None
        self.current = self.upcoming.pop(0)
        return self.current

    def skip(self) -> Optional[Track]:
        """Skip current track and get next."""
        return self.dequeue()

    def back(self) -> Optional[Track]:
        """Go back to last track in history if available."""
        if not self.history:
            return None
        prev = self.history.pop()
        if self.current:
            # push current to front of upcoming
            self.upcoming.insert(0, self.current)
        self.current = prev
        return self.current

    def clear(self):
        self.upcoming.clear()

    def shuffle(self):
        random.shuffle(self.upcoming)

    def remove_at(self, index: int) -> Optional[Track]:
        """Remove a track at 0-based index. Returns the removed track or None if out of bounds."""
        if 0 <= index < len(self.upcoming):
            return self.upcoming.pop(index)
        return None

    def set_loop(self, mode: str):
        if mode not in ("off", "song", "queue"):
            raise ValueError("Invalid loop mode")
        self.loop_mode = mode

    def get_queue(self) -> List[Track]:
        return list(self.upcoming)

    def get_history(self) -> List[Track]:
        return list(self.history)

    def now_playing(self) -> Optional[Track]:
        return self.current
