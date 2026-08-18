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
        # Statbot-style Analytics
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS message_analytics (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            message_count INTEGER DEFAULT 1,
            log_date TEXT NOT NULL,
            PRIMARY KEY(guild_id, user_id, channel_id, log_date)
        )
        """)
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS voice_analytics (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            voice_seconds INTEGER DEFAULT 0,
            log_date TEXT NOT NULL,
            PRIMARY KEY(guild_id, user_id, channel_id, log_date)
        )
        """)
        # Co-Owner & Trusted Users
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS trusted_users (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            granted_by INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY(guild_id, user_id)
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
        # Giveaways tables
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS giveaways (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            message_id INTEGER NOT NULL UNIQUE,
            host_id INTEGER NOT NULL,
            prize TEXT NOT NULL,
            winners_count INTEGER NOT NULL DEFAULT 1,
            end_time TEXT NOT NULL,
            ended INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )
        """)
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS giveaway_entries (
            giveaway_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            PRIMARY KEY(giveaway_id, user_id)
        )
        """)
        # Ticket System tables

        await conn.execute("""
        CREATE TABLE IF NOT EXISTS ticket_panels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            message_id INTEGER NOT NULL UNIQUE,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            category_id INTEGER,
            staff_role_id INTEGER,
            log_channel_id INTEGER,
            ticket_counter INTEGER DEFAULT 0,
            options_json TEXT,
            embed_color TEXT,
            created_at TEXT NOT NULL
        )
        """)
        try:
            await conn.execute("ALTER TABLE ticket_panels ADD COLUMN options_json TEXT")
        except Exception:
            pass
        try:
            await conn.execute("ALTER TABLE ticket_panels ADD COLUMN embed_color TEXT")
        except Exception:
            pass
        # Guild Ticket Configuration Table (Per-Guild Sequential Numbering & Routing)
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS guild_ticket_config (
            guild_id INTEGER PRIMARY KEY,
            open_category_id INTEGER,
            closed_category_id INTEGER,
            staff_role_id INTEGER,
            transcript_channel_id INTEGER,
            log_channel_id INTEGER,
            next_ticket_number INTEGER DEFAULT 1,
            created_at TEXT
        )
        """)
        try:
            await conn.execute("ALTER TABLE guild_ticket_config ADD COLUMN open_category_id INTEGER")
        except Exception:
            pass
        try:
            await conn.execute("ALTER TABLE guild_ticket_config ADD COLUMN closed_category_id INTEGER")
        except Exception:
            pass
        try:
            await conn.execute("ALTER TABLE guild_ticket_config ADD COLUMN staff_role_id INTEGER")
        except Exception:
            pass
        try:
            await conn.execute("ALTER TABLE guild_ticket_config ADD COLUMN transcript_channel_id INTEGER")
        except Exception:
            pass
        try:
            await conn.execute("ALTER TABLE guild_ticket_config ADD COLUMN log_channel_id INTEGER")
        except Exception:
            pass
        try:
            await conn.execute("ALTER TABLE guild_ticket_config ADD COLUMN next_ticket_number INTEGER DEFAULT 1")
        except Exception:
            pass

        await conn.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL UNIQUE,
            user_id INTEGER NOT NULL,
            panel_id INTEGER,
            category TEXT,
            ticket_type TEXT,
            ticket_number INTEGER NOT NULL DEFAULT 0,
            status TEXT DEFAULT 'open',
            claimed_by INTEGER,
            close_reason TEXT,
            created_at TEXT NOT NULL,
            closed_at TEXT
        )
        """)
        try:
            await conn.execute("ALTER TABLE tickets ADD COLUMN panel_id INTEGER")
        except Exception:
            pass
        try:
            await conn.execute("ALTER TABLE tickets ADD COLUMN category TEXT")
        except Exception:
            pass
        try:
            await conn.execute("ALTER TABLE tickets ADD COLUMN ticket_type TEXT")
        except Exception:
            pass
        try:
            await conn.execute("ALTER TABLE tickets ADD COLUMN ticket_number INTEGER DEFAULT 0")
        except Exception:
            pass
        try:
            await conn.execute("ALTER TABLE tickets ADD COLUMN claimed_by INTEGER")
        except Exception:
            pass
        try:
            await conn.execute("ALTER TABLE tickets ADD COLUMN close_reason TEXT")
        except Exception:
            pass

        # Auto Roles Table
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS autoroles (
            guild_id INTEGER NOT NULL,
            role_id INTEGER NOT NULL,
            is_bot INTEGER DEFAULT 0,
            PRIMARY KEY(guild_id, role_id)
        )
        """)

        # Welcome & Goodbye Configuration Table
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS welcome_config (
            guild_id INTEGER PRIMARY KEY,
            welcome_channel_id INTEGER,
            goodbye_channel_id INTEGER,
            welcome_msg TEXT,
            goodbye_msg TEXT,
            welcome_type TEXT DEFAULT 'card',
            dm_enabled INTEGER DEFAULT 0,
            is_enabled INTEGER DEFAULT 1
        )
        """)

        # Starboard Configuration & Tracking Tables
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS starboard_config (
            guild_id INTEGER PRIMARY KEY,
            channel_id INTEGER,
            threshold INTEGER DEFAULT 3,
            emoji TEXT DEFAULT '⭐',
            is_enabled INTEGER DEFAULT 1
        )
        """)

        await conn.execute("""
        CREATE TABLE IF NOT EXISTS starboard_messages (
            guild_id INTEGER NOT NULL,
            original_message_id INTEGER NOT NULL,
            starboard_message_id INTEGER NOT NULL,
            star_count INTEGER DEFAULT 0,
            PRIMARY KEY(guild_id, original_message_id)
        )
        """)

        await conn.commit()











