import pytest
from utils.gif_service import search_gifs

@pytest.mark.asyncio
async def test_search_gifs():
    # Search for a very common term like "dance"
    gifs = await search_gifs("dance")
    assert isinstance(gifs, list)
    # We should have found at least some gifs from either Tenor or Giphy
    assert len(gifs) > 0
    # Check that they are valid URLs
    for url in gifs[:3]:
        assert url.startswith("https://")
        assert ".gif" in url
