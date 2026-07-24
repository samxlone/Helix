from dataclasses import dataclass
from typing import Optional

@dataclass
class Track:
    title: str
    author: Optional[str]
    duration: Optional[int]  # duration in seconds (None for live)
    url: str                 # original url or identifier
    thumbnail: Optional[str]
    requester: Optional[int]  # user id of requester
    provider: Optional[str]
    stream_url: Optional[str]  # resolved stream url (None in stubs)
    is_live: bool = False
    is_playlist: bool = False
    http_headers: Optional[dict] = None

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "author": self.author,
            "duration": self.duration,
            "url": self.url,
            "thumbnail": self.thumbnail,
            "requester": self.requester,
            "provider": self.provider,
            "stream_url": self.stream_url,
            "is_live": self.is_live,
            "is_playlist": self.is_playlist,
            "http_headers": self.http_headers,
        }
