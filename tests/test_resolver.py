import pytest
import services.music.providers as providers_module
from services.music.resolver import resolve


@pytest.mark.asyncio
async def test_resolve_url_and_search(monkeypatch):
    # monkeypatch YouTubeProvider to avoid yt-dlp dependency in tests
    async def fake_detect(self, url):
        return True

    async def fake_fetch_metadata(self, url):
        return {"title": "Test Video", "duration": 123, "uploader": "Tester", "thumbnail": None, "url": url}

    monkeypatch.setattr(providers_module.YouTubeProvider, 'detect', fake_detect)
    monkeypatch.setattr(providers_module.YouTubeProvider, 'fetch_metadata', fake_fetch_metadata)

    t = await resolve('https://youtube.com/watch?v=abc', requester=10)
    assert t is not None
    assert t.provider == 'youtube' or t.provider == 'url'
    assert t.requester == 10

    t2 = await resolve('Some song name', requester=11)
    assert t2 is not None
    assert t2.provider == 'youtube'
    assert t2.requester == 11


def test_youtube_url_cleaning():
    yt = providers_module.YouTubeProvider()
    
    # Mix / Playlist URL with a video ID
    url1 = "https://www.youtube.com/watch?v=Hng_lW_nr0A&list=RDHng_lW_nr0A&start_radio=1"
    assert yt._clean_url(url1) == "https://www.youtube.com/watch?v=Hng_lW_nr0A&start_radio=1"
    
    # youtu.be link with a list
    url2 = "https://youtu.be/Hng_lW_nr0A?list=RDHng_lW_nr0A&index=1"
    assert yt._clean_url(url2) == "https://youtu.be/Hng_lW_nr0A"
    
    # Pure playlist URL (no video ID)
    url3 = "https://www.youtube.com/playlist?list=PL4fGSI1pDJn5n9Q-7Xp3nQyL01-f2f99f"
    assert yt._clean_url(url3) == url3
    
    # Non-youtube URL
    url4 = "https://example.com/some/path?list=123"
    assert yt._clean_url(url4) == url4

