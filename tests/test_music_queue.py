import pytest
from services.music.queue import GuildQueue
from services.music.models import Track


@pytest.mark.asyncio
async def test_enqueue_dequeue_and_history():
    q = GuildQueue(guild_id=1)
    t1 = Track(title="A", author="X", duration=10, url="u1", thumbnail=None, requester=1, provider="test", stream_url=None)
    t2 = Track(title="B", author="Y", duration=20, url="u2", thumbnail=None, requester=2, provider="test", stream_url=None)

    pos1 = q.enqueue(t1)
    assert pos1 == 1
    pos2 = q.enqueue(t2)
    assert pos2 == 2

    # dequeue advances current
    cur = q.dequeue()
    assert cur is not None
    assert q.now_playing() == cur
    # play next
    nxt = q.dequeue()
    assert nxt is not None
    # history should have previous entries
    assert len(q.get_history()) >= 1


@pytest.mark.asyncio
async def test_loop_and_shuffle():
    q = GuildQueue(guild_id=2)
    tracks = [Track(title=str(i), author=None, duration=5, url=f"u{i}", thumbnail=None, requester=None, provider="test", stream_url=None) for i in range(5)]
    for t in tracks:
        q.enqueue(t)
    q.set_loop('song')
    # set current
    q.current = tracks[0]
    cur = q.dequeue()
    # in song loop, dequeue returns same current
    assert cur == tracks[0]
    q.set_loop('off')
    q.shuffle()
    assert len(q.get_queue()) == 5


@pytest.mark.asyncio
async def test_queue_controls():
    q = GuildQueue(guild_id=3)
    t1 = Track(title="A", author="X", duration=10, url="u1", thumbnail=None, requester=1, provider="test", stream_url=None)
    t2 = Track(title="B", author="Y", duration=20, url="u2", thumbnail=None, requester=2, provider="test", stream_url=None)
    t3 = Track(title="C", author="Z", duration=30, url="u3", thumbnail=None, requester=3, provider="test", stream_url=None)

    q.enqueue(t1)
    q.enqueue(t2)
    q.enqueue(t3)
    
    assert len(q.get_queue()) == 3
    
    # test remove_at
    removed = q.remove_at(1) # B (index 1)
    assert removed.title == "B"
    assert len(q.get_queue()) == 2
    assert q.get_queue()[0].title == "A"
    assert q.get_queue()[1].title == "C"
    
    # test clear
    q.clear()
    assert len(q.get_queue()) == 0


@pytest.mark.asyncio
async def test_connect_to_channel_already_connected():
    from services.music.voice import connect_to_channel
    import discord

    class FakeVC:
        def __init__(self, channel):
            self.channel = channel
            self._connected = True

        def is_connected(self):
            return self._connected

        async def move_to(self, target_channel):
            self.channel = target_channel

        async def disconnect(self, force=True):
            self._connected = False

    class FakeChannel:
        def __init__(self, id, guild):
            self.id = id
            self.guild = guild

        async def connect(self):
            if self.guild.voice_client:
                raise discord.ClientException("Already connected to a voice channel.")
            vc = FakeVC(self)
            self.guild.voice_client = vc
            return vc

    class FakeGuild:
        def __init__(self):
            self.voice_client = None

    guild = FakeGuild()
    ch1 = FakeChannel(101, guild)
    ch2 = FakeChannel(102, guild)

    # First connection creates voice client
    vc1 = await connect_to_channel(ch1)
    assert vc1 is not None
    assert guild.voice_client == vc1

    # Second connection to different channel moves voice client seamlessly without raising ClientException
    vc2 = await connect_to_channel(ch2)
    assert vc2 == vc1
    assert vc2.channel.id == 102


@pytest.mark.asyncio
async def test_equalizer_restart_preserves_track_in_queue():
    from services.music.player import Player

    player = Player(guild_id=99)
    track = Track(title="Sunflower", author="Post Malone", duration=162, url="u", thumbnail=None, requester=1, provider="test", stream_url="http://fake.stream")
    player.queue.enqueue(track)

    # First dequeue to set now playing
    active_track = player.queue.dequeue()
    assert active_track.title == "Sunflower"
    assert player.queue.now_playing() == active_track

    # Mock voice client
    class FakeVC:
        def __init__(self):
            self._playing = True

        def is_playing(self):
            return self._playing

        def is_paused(self):
            return False

        def stop(self):
            self._playing = False

    vc = FakeVC()
    restarted = player.restart_current_track(vc)
    assert restarted is True
    assert player._restarting_current_track is True
    assert player.queue.now_playing() == active_track


