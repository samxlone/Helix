"""Simple CLI to manage mod-log channel setting for a guild.

Usage:
  python -m services.modlog_cli show --guild 12345
  python -m services.modlog_cli set --guild 12345 --channel 67890
  python -m services.modlog_cli clear --guild 12345

This uses the same per-guild config service as the bot.
"""
import argparse
import asyncio

from utils.config_service import get_guild_config, set_guild_config


async def do_show(guild_id: int):
    cfg = await get_guild_config(guild_id)
    print(f"Guild {guild_id} config:\n{cfg}")


async def do_set(guild_id: int, channel_id: int):
    await set_guild_config(guild_id, {"mod_log_channel": int(channel_id)})
    print(f"Set mod_log_channel for guild {guild_id} -> {channel_id}")


async def do_clear(guild_id: int):
    await set_guild_config(guild_id, {"mod_log_channel": None})
    print(f"Cleared mod_log_channel for guild {guild_id}")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Manage mod-log channel setting for a guild")
    sub = parser.add_subparsers(dest="cmd", required=True)

    parser_show = sub.add_parser("show")
    parser_show.add_argument("--guild", type=int, required=True)

    parser_set = sub.add_parser("set")
    parser_set.add_argument("--guild", type=int, required=True)
    parser_set.add_argument("--channel", type=int, required=True)

    parser_clear = sub.add_parser("clear")
    parser_clear.add_argument("--guild", type=int, required=True)

    args = parser.parse_args(argv)

    if args.cmd == "show":
        asyncio.run(do_show(args.guild))
    elif args.cmd == "set":
        asyncio.run(do_set(args.guild, args.channel))
    elif args.cmd == "clear":
        asyncio.run(do_clear(args.guild))


if __name__ == "__main__":
    main()
