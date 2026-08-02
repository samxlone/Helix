import os
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv

from utils.logger import setup_logging
from utils.cog_loader import load_cogs
from utils import db as db_utils
from utils import errors as error_utils

load_dotenv()

logger = setup_logging(os.getenv("LOG_LEVEL", "INFO"))

PREFIX = os.getenv("PREFIX", "!")
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.presences = True

async def get_prefix(bot, message: discord.Message):
    default_prefix = os.getenv("PREFIX", "!")
    if not message.guild:
        return commands.when_mentioned_or(default_prefix)(bot, message)
    try:
        from utils.config_service import get_guild_config
        cfg = await get_guild_config(message.guild.id)
        guild_prefix = cfg.get("prefix") or default_prefix
        return commands.when_mentioned_or(guild_prefix)(bot, message)
    except Exception:
        return commands.when_mentioned_or(default_prefix)(bot, message)


bot = commands.Bot(command_prefix=get_prefix, intents=intents, help_command=None)
bot.start_time = discord.utils.utcnow()


import inspect
import re
from typing import Optional

class MockInteraction:
    def __init__(self, message: discord.Message, client):
        self.message = message
        self.client = client
        self.user = message.author
        self.guild = message.guild
        self.channel = message.channel
        self.response = MockResponse(message)
        self.followup = MockFollowup(message)

class MockResponse:
    def __init__(self, message: discord.Message):
        self.message = message
    async def send_message(self, content=None, *args, **kwargs):
        await self.message.channel.send(content)
    async def defer(self, *args, **kwargs):
        pass

class MockFollowup:
    def __init__(self, message: discord.Message):
        self.message = message
    async def send(self, content=None, *args, **kwargs):
        await self.message.channel.send(content)


async def invoke_slash_command_as_text(message: discord.Message, words: list) -> bool:
    if not words:
        return False
        
    app_cmd = None
    consumed_words = 0
    
    # 1. Try matching two words (subcommands like "role add")
    if len(words) >= 2:
        two_words_name = f"{words[0]} {words[1]}".lower()
        for cmd in bot.tree.walk_commands():
            if cmd.qualified_name.lower() == two_words_name:
                app_cmd = cmd
                consumed_words = 2
                break
                
    # 2. Try matching one word (leaf commands like "purge")
    if not app_cmd:
        one_word_name = words[0].lower()
        for cmd in bot.tree.walk_commands():
            if cmd.qualified_name.lower() == one_word_name:
                if hasattr(cmd, "callback") and cmd.callback is not None:
                    app_cmd = cmd
                    consumed_words = 1
                    break
                    
    if not app_cmd or not hasattr(app_cmd, "callback") or app_cmd.callback is None:
        return False
        
    callback = app_cmd.callback
    sig = inspect.signature(callback)
    kwargs = {}
    
    interaction = MockInteraction(message, bot)
    args_list = words[consumed_words:]
    
    # Exclude self and interaction (first two params of Cog command callback)
    params = list(sig.parameters.values())[2:]
    
    args_idx = 0
    for param in params:
        if args_idx >= len(args_list):
            if param.default is inspect.Parameter.empty:
                await message.channel.send(f"Missing required argument: `{param.name}`")
                return True
            else:
                kwargs[param.name] = param.default
                continue
                
        arg_str = args_list[args_idx]
        
        # Type conversions
        if param.annotation in (discord.Member, discord.User, Optional[discord.Member], Optional[discord.User]):
            member = None
            match = re.search(r'\d+', arg_str)
            if match:
                member_id = int(match.group(0))
                if message.guild:
                    member = message.guild.get_member(member_id)
                if not member:
                    try:
                        member = await bot.fetch_user(member_id)
                    except Exception:
                        pass
            if not member and message.guild:
                member = discord.utils.find(lambda m: m.name.lower() == arg_str.lower() or (m.nick and m.nick.lower() == arg_str.lower()), message.guild.members)
            if not member and not message.guild:
                member = discord.utils.find(lambda u: u.name.lower() == arg_str.lower(), bot.users)

            if not member and param.default is inspect.Parameter.empty:
                await message.channel.send(f"Could not resolve member: `{arg_str}`")
                return True
            kwargs[param.name] = member
            args_idx += 1
            
        elif param.annotation in (discord.TextChannel, Optional[discord.TextChannel], discord.abc.GuildChannel, Optional[discord.abc.GuildChannel]):
            channel = None
            match = re.search(r'\d+', arg_str)
            if match:
                channel_id = int(match.group(0))
                if message.guild:
                    channel = message.guild.get_channel(channel_id)
                if not channel:
                    channel = bot.get_channel(channel_id)
            if not channel and message.guild:
                cleaned_name = arg_str.lstrip('#').lower()
                channel = discord.utils.find(lambda c: c.name.lower() == cleaned_name, message.guild.text_channels)
            if not channel and param.default is inspect.Parameter.empty:
                await message.channel.send(f"Could not resolve channel: `{arg_str}`")
                return True
            kwargs[param.name] = channel
            args_idx += 1
            
        elif param.annotation in (discord.Role, Optional[discord.Role]):
            role = None
            if message.guild:
                match = re.search(r'\d+', arg_str)
                if match:
                    role_id = int(match.group(0))
                    role = message.guild.get_role(role_id)
                if not role:
                    role = discord.utils.find(lambda r: r.name.lower() == arg_str.lower(), message.guild.roles)
            if not role and param.default is inspect.Parameter.empty:
                await message.channel.send(f"Could not resolve role: `{arg_str}`")
                return True
            kwargs[param.name] = role
            args_idx += 1


        elif param.annotation in (int, Optional[int]):
            try:
                kwargs[param.name] = int(arg_str)
                args_idx += 1
            except ValueError:
                if param.default is inspect.Parameter.empty:
                    await message.channel.send(f"Invalid integer: `{arg_str}`")
                    return True
                else:
                    kwargs[param.name] = param.default
                    
        elif param.annotation in (str, Optional[str]):
            if param == params[-1]:
                kwargs[param.name] = " ".join(args_list[args_idx:])
                args_idx = len(args_list)
            else:
                kwargs[param.name] = arg_str
                args_idx += 1
        else:
            kwargs[param.name] = arg_str
            args_idx += 1
            
    cog_instance = app_cmd.binding
    try:
        await callback(cog_instance, interaction, **kwargs)
        return True
    except Exception as e:
        logger.exception("Failed to execute app command as text: %s", e)
        await message.channel.send(f"Error executing command: {e}")
        return True


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    # Get active prefix dynamically for this guild/message
    prefix = PREFIX
    if message.guild:
        try:
            from utils.config_service import get_guild_config
            cfg = await get_guild_config(message.guild.id)
            prefix = cfg.get("prefix") or PREFIX
        except Exception:
            pass

    # Prefix-less command bypass (Owner or users with DB permission)
    has_prefixless_permission = False
    owner_id_str = os.getenv("OWNER_ID")
    if owner_id_str and message.author.id == int(owner_id_str):
        has_prefixless_permission = True

    if not has_prefixless_permission and message.guild:
        try:
            async with db_utils.get_connection() as conn:
                cur = await conn.execute(
                    "SELECT 1 FROM prefixless_permissions WHERE guild_id = ? AND user_id = ?",
                    (message.guild.id, message.author.id)
                )
                row = await cur.fetchone()
                await cur.close()
                if row:
                    has_prefixless_permission = True
        except Exception:
            logger.exception("Error checking prefixless permissions")

    if has_prefixless_permission:
        try:
            content = message.content.strip()
            words = content.split()
            if words:
                first_word = words[0].lower()
                if not content.startswith(prefix) and not content.startswith("<@"):
                    # Check text/hybrid commands
                    text_cmds = set()
                    for cmd in bot.commands:
                        text_cmds.add(cmd.name.lower())
                        for alias in cmd.aliases:
                            text_cmds.add(alias.lower())
                    
                    if first_word in text_cmds:
                        message.content = f"{prefix}{content}"
                        logger.info("Prefix-less command auto-prefix: %s -> %s for user %s", content, message.content, message.author.id)
                    else:
                        # Try executing as slash command directly
                        executed = await invoke_slash_command_as_text(message, words)
                        if executed:
                            return
        except Exception:
            logger.exception("Error in prefix-less command bypass")

    # If the bot is mentioned directly, reply with info or search for a GIF if query text is present
    # If the bot is mentioned directly with no other text (and not replying to a message), reply with prefix info
    if bot.user in message.mentions and not getattr(message, "reference", None):
        cleaned_content = message.content.replace(f"<@{bot.user.id}>", "").replace(f"<@!{bot.user.id}>", "").strip()
        if not cleaned_content:
            await message.channel.send(f"Hello {message.author.mention}! My prefix is `{prefix}`. You can run prefix commands like `{prefix}play`, or use my slash commands (e.g. `/play`). 🤖")
            return


    await bot.process_commands(message)


@bot.event
async def on_ready():
    logger.info("Bot connected as %s (id=%s)", bot.user, bot.user.id)

    # 1. Check for pending restart message update immediately on boot
    restart_file = "data/restart_msg.json"
    if os.path.exists(restart_file):
        try:
            with open(restart_file, "r") as f:
                import json
                import time
                restart_data = json.load(f)
            channel_id = restart_data.get("channel_id")
            message_id = restart_data.get("message_id")
            start_ts = restart_data.get("timestamp")

            if channel_id and message_id:
                channel = bot.get_channel(channel_id)
                if not channel:
                    channel = await bot.fetch_channel(channel_id)
                if channel:
                    msg = await channel.fetch_message(message_id)
                    if msg:
                        bot_name = bot.user.name
                        if getattr(channel, "guild", None):
                            guild_me = channel.guild.me or channel.guild.get_member(bot.user.id)
                            if guild_me and getattr(guild_me, "display_name", None):
                                bot_name = guild_me.display_name

                        elapsed_str = ""
                        if start_ts:
                            duration = time.time() - start_ts
                            elapsed_str = f" in **{duration:.2f}s**"

                        await msg.edit(content=f"✅ **{bot_name}** has successfully restarted{elapsed_str}! 🚀")
                        logger.info("Updated restart message in channel %s for bot %s", channel_id, bot_name)

        except Exception as exc:
            logger.warning("Failed to update restart message: %s", exc)
        finally:
            try:
                os.remove(restart_file)
            except Exception:
                pass

    try:
        from utils.presence import load_and_set_presence
        await load_and_set_presence(bot)
    except Exception as e:
        logger.exception("Failed to run load_and_set_presence on ready: %s", e)
    owner_id_str = os.getenv("OWNER_ID")
    if owner_id_str:
        try:
            bot.owner_user = await bot.fetch_user(int(owner_id_str))
            logger.info("Owner user resolved: %s", bot.owner_user)
        except Exception:
            bot.owner_user = None
    try:
        # If DEV_GUILD_ID is set, register commands to that guild for instant availability during development.
        dev_gid = os.getenv("DEV_GUILD_ID")
        if dev_gid:
            try:
                gid = int(dev_gid)
                await bot.tree.sync(guild=discord.Object(id=gid))
                logger.info("Synced application commands to DEV_GUILD_ID=%s", gid)
            except Exception:
                logger.exception("Failed to sync app commands to DEV_GUILD_ID=%s", dev_gid)

        # Always sync global slash command tree across ALL servers
        synced_cmds = await bot.tree.sync()
        logger.info("Synced %s application commands (global)", len(synced_cmds))
    except Exception as exc:
        logger.exception("Failed to sync app commands: %s", exc)


    # Log registered app commands and loaded cogs for debugging
    try:
        cmds = list(bot.tree.walk_commands())
        logger.info("Registered app commands count=%s", len(cmds))
        if cmds:
            logger.info("App commands: %s", ", ".join([c.name for c in cmds]))
    except Exception:
        logger.exception("Failed to list app commands")

    try:
        logger.info("Loaded cogs: %s", ", ".join(bot.cogs.keys()) if bot.cogs else "(none)")
    except Exception:
        logger.exception("Failed to list loaded cogs")



async def main():
    # Initialize DB and error handlers
    try:
        await db_utils.init_db()
    except Exception:
        logger.exception("Database initialization failed")

    await error_utils.setup_error_handlers(bot)

    # Load cogs
    await load_cogs(bot, package="cogs")

    # Run bot
    if not TOKEN:
        logger.error("DISCORD_TOKEN not set in environment")
        return

    await bot.start(TOKEN)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutdown requested by user")
    except Exception:
        logger.exception("Unexpected error in main")
