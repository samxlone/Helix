import os
import aiosqlite
from pathlib import Path
import logging
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "database.sqlite3"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


async def get_db_path():
    url = os.getenv("DATABASE_URL")
    if url:
        return url
    return str(DB_PATH)


@asynccontextmanager
async def get_connection():
    """Async context manager that yields an aiosqlite connection and ensures it is closed."""
    db_file = await get_db_path()
    conn = await aiosqlite.connect(db_file)
    conn.row_factory = aiosqlite.Row
    try:
        yield conn
    finally:
        await conn.close()


async def init_db():
    db_file = await get_db_path()
    logger.info("Initializing database at %s", db_file)
    # Using aiosqlite for SQLite. If DATABASE_URL points to Postgres later, swap implementation.
    async with get_connection() as conn:
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            guild_id INTEGER PRIMARY KEY,
            data TEXT
        )
        """)
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS mod_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            moderator_id INTEGER NOT NULL,
            target_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            reason TEXT,
            created_at TEXT NOT NULL
        )
        """)
        # Users/economy
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY
        )
        """)
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS economy (
            user_id INTEGER PRIMARY KEY,
            wallet INTEGER DEFAULT 0,
            bank INTEGER DEFAULT 0,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        )
        """)
        # Inventory
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            item_key TEXT NOT NULL,
            amount INTEGER DEFAULT 1,
            metadata TEXT,
            UNIQUE(user_id, item_key)
        )
        """)
        # Leveling
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS xp (
            user_id INTEGER PRIMARY KEY,
            xp INTEGER DEFAULT 0,
            level INTEGER DEFAULT 0,
            last_xp_at TEXT
        )
        """)
        # Cooldowns
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS cooldowns (
            user_id INTEGER NOT NULL,
            key TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            PRIMARY KEY(user_id, key)
        )
        """)
        # Logs/events
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            type TEXT NOT NULL,
            payload TEXT,
            created_at TEXT NOT NULL
        )
        """)
        # Tickets
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            channel_id INTEGER,
            status TEXT DEFAULT 'open',
            created_at TEXT NOT NULL,
            closed_at TEXT
        )
        """)
        # Reaction roles
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS reaction_roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            message_id INTEGER NOT NULL,
            emoji TEXT NOT NULL,
            role_id INTEGER NOT NULL
        )
        """)
        # Reminders table
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            message TEXT NOT NULL,
            expires_at TEXT NOT NULL
        )
        """)
        # AFK table (supports global and server-specific AFK)
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS afk (
            user_id INTEGER NOT NULL,
            guild_id INTEGER NOT NULL DEFAULT 0,
            message TEXT,
            since TEXT NOT NULL,
            scope TEXT DEFAULT 'global',
            PRIMARY KEY(user_id, guild_id)
        )
        """)
        try:
            await conn.execute("ALTER TABLE afk ADD COLUMN guild_id INTEGER NOT NULL DEFAULT 0")
        except Exception:
            pass
        try:
            await conn.execute("ALTER TABLE afk ADD COLUMN scope TEXT DEFAULT 'global'")
        except Exception:
            pass

        # Prefixless permissions table
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS prefixless_permissions (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            PRIMARY KEY(guild_id, user_id)
        )
        """)
        # Forced nicknames table
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS forced_nicknames (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            forced_nick TEXT NOT NULL,
            set_by INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY(guild_id, user_id)
        )

        """)
        # AI Daily Usage Limits table
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS ai_daily_usage (
            user_id INTEGER NOT NULL,
            date_str TEXT NOT NULL,
            text_count INTEGER DEFAULT 0,
            image_count INTEGER DEFAULT 0,
            PRIMARY KEY(user_id, date_str)
        )
        """)
        # Vanity Trackers table
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS vanity_trackers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            vanity TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(user_id, vanity)
        )
        """)
        await conn.commit()





