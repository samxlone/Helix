MultiPurposeDiscordBot
=====================

Phase 1 scaffold for a modular Discord bot using discord.py.

What is included:
- Basic logging (utils/logger.py)
- Cog loader (utils/cog_loader.py)
- Async SQLite init (utils/db.py)
- Error handler setup (utils/errors.py)
- Example cog (cogs/example.py)
- Main entrypoint (main.py)

Getting started:
1. Create a virtual environment: python -m venv .venv
2. Activate it and install deps: pip install -r requirements.txt
3. Copy .env -> .env.local and set DISCORD_TOKEN and other values
4. Run: python main.py

Next steps:
- Add more cogs under cogs/
- Add configuration management, migrations, and tests
- Replace SQLite with Postgres for production
