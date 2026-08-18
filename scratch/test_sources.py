import asyncio
import sys
from services.music.resolver import resolve
from services.music.soundcloud import is_soundcloud_url
from services.music.applemusic import is_applemusic_url


async def main():
    sc_url = "https://soundcloud.com/octobersveryown/drake-gods-plan"
    am_url = "https://music.apple.com/us/album/blinding-lights/1499378108?i=1499378607"

    print("Checking SoundCloud URL detection:", is_soundcloud_url(sc_url))
    print("Checking Apple Music URL detection:", is_applemusic_url(am_url))

    print("\nResolving SoundCloud URL...")
    sc_track = await resolve(sc_url, requester=123)
    if sc_track:
        t = sc_track[0] if isinstance(sc_track, list) else sc_track
        print(f"SoundCloud Track Resolved -> Title: '{t.title}', Author: '{t.author}', Provider: {t.provider}")
    else:
        print("SoundCloud resolution returned None")

    print("\nResolving Apple Music URL...")
    am_track = await resolve(am_url, requester=123)
    if am_track:
        t = am_track[0] if isinstance(am_track, list) else am_track
        print(f"Apple Music Track Resolved -> Title: '{t.title}', Author: '{t.author}', Provider: {t.provider}")
    else:
        print("Apple Music resolution returned None")


if __name__ == "__main__":
    asyncio.run(main())
