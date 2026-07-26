import pytest
from utils.ai_limits import check_and_increment_text_limit, check_and_increment_image_limit, get_user_daily_usage, get_today_str
from utils.db import init_db, get_connection

@pytest.mark.asyncio
async def test_ai_daily_limits():
    await init_db()
    test_user_id = 987654321098765432
    today = get_today_str()

    # Clean previous records
    async with get_connection() as conn:
        await conn.execute("DELETE FROM ai_daily_usage WHERE user_id = ?", (test_user_id,))
        await conn.commit()

    # Test text questions limit (up to 10)
    for i in range(1, 11):
        allowed, count = await check_and_increment_text_limit(test_user_id, limit=10)
        assert allowed is True
        assert count == i

    # 11th text question should be rejected
    allowed, count = await check_and_increment_text_limit(test_user_id, limit=10)
    assert allowed is False
    assert count == 10

    # Test image generation limit (up to 2)
    allowed1, count1 = await check_and_increment_image_limit(test_user_id, limit=2)
    assert allowed1 is True
    assert count1 == 1

    allowed2, count2 = await check_and_increment_image_limit(test_user_id, limit=2)
    assert allowed2 is True
    assert count2 == 2

    # 3rd image generation should be rejected
    allowed3, count3 = await check_and_increment_image_limit(test_user_id, limit=2)
    assert allowed3 is False
    assert count3 == 2

    # Check overall user daily usage query
    t_cnt, i_cnt = await get_user_daily_usage(test_user_id)
    assert t_cnt == 10
    assert i_cnt == 2

    # Clean up
    async with get_connection() as conn:
        await conn.execute("DELETE FROM ai_daily_usage WHERE user_id = ?", (test_user_id,))
        await conn.commit()
