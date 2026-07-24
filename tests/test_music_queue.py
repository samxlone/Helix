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
