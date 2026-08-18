import logging
import asyncio
import discord
from utils.config_service import get_guild_config

logger = logging.getLogger(__name__)


async def set_presence(bot, cfg):
    """Apply one presence configuration to the bot."""
    activity_type = cfg.get("presence_activity") or "playing"
    name = cfg.get("presence_name") or "Music and games!"
    status_str = cfg.get("presence_status") or "online"
    url = cfg.get("presence_url") or None

    status = discord.Status.online
    if status_str == "idle":
        status = discord.Status.idle
    elif status_str == "dnd":
        status = discord.Status.dnd
    elif status_str == "invisible":
        status = discord.Status.invisible

    activity = None
    if activity_type == "playing":
        activity = discord.Game(name=name)
    elif activity_type == "streaming":
        activity = discord.Streaming(name=name, url=url or "https://twitch.tv/monstercat")
    elif activity_type == "listening":
        activity = discord.Activity(type=discord.ActivityType.listening, name=name)
    elif activity_type == "watching":
        activity = discord.Activity(type=discord.ActivityType.watching, name=name)

    try:
        if not bot.is_ready():
            await bot.wait_until_ready()
        if getattr(bot, "ws", None) is not None:
            await bot.change_presence(status=status, activity=activity)
            logger.info("Successfully applied presence: status=%s, activity=%s (%s)", status_str, activity_type, name)
    except Exception as e:
        logger.warning("Could not set presence (%s): %s", status_str, e)


async def load_and_set_presence(bot):
    """Retrieve presence settings from global config (guild_id=0) and apply to the bot."""
    try:
        cfg = await get_guild_config(0)
        await set_presence(bot, cfg)
    except Exception as e:
        logger.warning("Failed to load and set presence: %s", e)
