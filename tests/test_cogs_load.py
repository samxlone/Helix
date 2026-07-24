import asyncio
import discord
from discord.ext import commands
import importlib
import pytest

@pytest.mark.asyncio
async def test_all_cogs_load(monkeypatch, tmp_path):
    # Setup test DB
    db_path = tmp_path / "cogs_load.sqlite"
    monkeypatch.setenv("DATABASE_URL", str(db_path))

    import utils.db as db
    importlib.reload(db)
    await db.init_db()

    intents = discord.Intents.default()
    bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)
    bot.start_time = discord.utils.utcnow()
    
    from utils.cog_loader import load_cogs
    # This will load all cogs from the cogs/ package.
    # If any CommandRegistrationError or other error occurs, this will raise.
    await load_cogs(bot, package="cogs")
    
    # Verify cogs are loaded
    assert "Utility" in bot.cogs
    assert "Moderation" in bot.cogs
    assert "Example" in bot.cogs
    assert "MusicCog" in bot.cogs
    
    # Unload cogs to stop loop tasks
    for cog_name in list(bot.cogs.keys()):
        await bot.remove_cog(cog_name)
