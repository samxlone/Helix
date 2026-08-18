"""Secure, self-hosted Discord dashboard for Helix.

The dashboard is loaded automatically as a cog and shares the bot's event loop,
database, guild cache, and permission model. It exposes rich server configuration,
analytics, multi-logging, tickets, leveling, automod, anti-nuke, and moderation audit trails.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import aiohttp
from aiohttp import web
import discord
from discord.ext import commands

from services.analytics import get_server_analytics
from utils.config_service import get_guild_config, set_guild_config
from utils.db import get_connection

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT / "dashboard"
DISCORD_API = "https://discord.com/api/v10"
MANAGE_GUILD = 1 << 5
ADMINISTRATOR = 1 << 3
SESSION_TTL = timedelta(hours=8)

# Allowed per-guild configuration settings that can be updated from the dashboard
ALLOWED_SETTINGS = {
    "prefix", "xp_enabled", "level_channel_id", "ignored_xp_channels",
    "xp_per_message", "xp_cooldown_seconds", "level_rewards", "ai_channel_id",
    "ai_provider", "mod_log_channel", "modlog_dm_notifications",
    "automod_enabled", "automod_block_markdown", "automod_block_invites",
    "automod_block_scam", "automod_log_channel_id", "automod_punishment",
    "automod_ignored_channels", "automod_ignored_roles", "antinuke_enabled",
    "antinuke_strict", "antinuke_recovery", "antinuke_punishment",
    "antinuke_thresholds", "antinuke_whitelisted_users", "antinuke_whitelisted_roles",
    "ban_unban_log_channel_id", "message_log_channel_id", "image_log_channel_id",
    "join_leave_log_channel_id", "role_create_log_channel_id", "role_update_log_channel_id",
    "role_delete_log_channel_id", "role_add_remove_log_channel_id",
    "channel_create_log_channel_id", "channel_delete_log_channel_id", "voice_log_channel_id",
    "ticket_open_category_id", "ticket_closed_category_id", "ticket_staff_role_id",
    "ticket_transcript_channel_id", "ticket_log_channel_id"
}


class DashboardCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.app = web.Application(middlewares=[self._security_headers])
        self.runner: web.AppRunner | None = None
        self.sessions: dict[str, dict[str, Any]] = {}
        self.oauth_states: dict[str, datetime] = {}
        self.cookie_name = "helix_dashboard"
        self._configured = bool(
            os.getenv("DASHBOARD_CLIENT_ID")
            and os.getenv("DASHBOARD_CLIENT_SECRET")
            and os.getenv("DASHBOARD_REDIRECT_URI")
        )
        self._register_routes()

    async def cog_load(self) -> None:
        self.session_secret = os.getenv("DASHBOARD_SESSION_SECRET") or secrets.token_urlsafe(48)
        host = os.getenv("DASHBOARD_HOST", "127.0.0.1")
        port = int(os.getenv("DASHBOARD_PORT", "8080"))
        self.runner = web.AppRunner(self.app, access_log=None)
        await self.runner.setup()
        site = web.TCPSite(self.runner, host, port)
        try:
            await site.start()
        except OSError as exc:
            await self.runner.cleanup()
            self.runner = None
            logger.warning("Dashboard unavailable on %s:%s: %s", host, port, exc)
            return
        logger.info("Helix dashboard listening at http://%s:%s", host, port)
        if not self._configured:
            logger.warning("Dashboard OAuth is not configured; add DASHBOARD_CLIENT_ID, DASHBOARD_CLIENT_SECRET, and DASHBOARD_REDIRECT_URI.")

    def cog_unload(self) -> None:
        if self.runner:
            asyncio.create_task(self.runner.cleanup())

    @web.middleware
    async def _security_headers(self, request: web.Request, handler):
        response = await handler(request)
        response.headers.update({
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Content-Security-Policy": "default-src 'self'; style-src 'self' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; script-src 'self'; img-src 'self' https://cdn.discordapp.com https://media.discordapp.net data:; connect-src 'self'; base-uri 'self'; frame-ancestors 'none'",
        })
        return response

    def _register_routes(self) -> None:
        self.app.router.add_get("/", self.index)
        self.app.router.add_static("/assets", STATIC_DIR, show_index=False)
        self.app.router.add_get("/auth/discord", self.login)
        self.app.router.add_get("/auth/callback", self.callback)
        self.app.router.add_post("/auth/logout", self.logout)
        self.app.router.add_get("/api/health", self.health)
        self.app.router.add_get("/api/me", self.me)
        self.app.router.add_get("/api/guilds", self.guilds)
        self.app.router.add_get("/api/guilds/{guild_id}/overview", self.overview)
        self.app.router.add_get("/api/guilds/{guild_id}/settings", self.settings)
        self.app.router.add_put("/api/guilds/{guild_id}/settings", self.update_settings)
        self.app.router.add_get("/api/guilds/{guild_id}/tickets", self.tickets)
        self.app.router.add_post("/api/guilds/{guild_id}/tickets/config", self.update_ticket_config)
        self.app.router.add_post("/api/guilds/{guild_id}/tickets/panels/deploy", self.deploy_ticket_panel)
        self.app.router.add_put("/api/guilds/{guild_id}/tickets/panels/{panel_id}", self.edit_ticket_panel)
        self.app.router.add_delete("/api/guilds/{guild_id}/tickets/panels/{panel_id}", self.delete_ticket_panel)
        self.app.router.add_post("/api/guilds/{guild_id}/tickets/close/{ticket_id}", self.close_ticket_direct)
        self.app.router.add_get("/api/guilds/{guild_id}/giveaways", self.giveaways)
        self.app.router.add_get("/api/guilds/{guild_id}/economy", self.economy)
        self.app.router.add_get("/api/guilds/{guild_id}/vanity", self.vanity)
        self.app.router.add_get("/api/guilds/{guild_id}/activity", self.activity)
        self.app.router.add_get("/api/guilds/{guild_id}/community", self.community_get)
        self.app.router.add_post("/api/guilds/{guild_id}/community", self.community_post)

    async def index(self, request: web.Request) -> web.FileResponse:
        return web.FileResponse(STATIC_DIR / "index.html")

    async def health(self, request: web.Request) -> web.Response:
        return web.json_response({"ok": True, "bot_ready": self.bot.is_ready(), "oauth_configured": self._configured})

    async def login(self, request: web.Request) -> web.StreamResponse:
        if not self._configured:
            raise web.HTTPServiceUnavailable(text="Dashboard OAuth has not been configured. See DASHBOARD.md.")
        state = secrets.token_urlsafe(32)
        self.oauth_states[state] = datetime.now(timezone.utc) + timedelta(minutes=10)
        params = urlencode({
            "client_id": os.environ["DASHBOARD_CLIENT_ID"],
            "redirect_uri": os.environ["DASHBOARD_REDIRECT_URI"],
            "response_type": "code",
            "scope": "identify guilds",
            "state": state,
            "prompt": "consent",
        })
        raise web.HTTPFound(f"https://discord.com/oauth2/authorize?{params}")

    async def callback(self, request: web.Request) -> web.StreamResponse:
        state = request.query.get("state", "")
        expires = self.oauth_states.pop(state, None)
        code = request.query.get("code")
        if not code or not expires or expires < datetime.now(timezone.utc):
            raise web.HTTPBadRequest(text="The Discord login request expired. Please try again.")

        form = {
            "client_id": os.environ["DASHBOARD_CLIENT_ID"],
            "client_secret": os.environ["DASHBOARD_CLIENT_SECRET"],
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": os.environ["DASHBOARD_REDIRECT_URI"],
        }
        try:
            async with aiohttp.ClientSession() as client:
                async with client.post(f"{DISCORD_API}/oauth2/token", data=form) as response:
                    token_data = await response.json(content_type=None)
                    if response.status != 200:
                        logger.warning("Discord OAuth token exchange failed: %s", response.status)
                        raise web.HTTPUnauthorized(text="Discord login could not be completed.")
                headers = {"Authorization": f"Bearer {token_data['access_token']}"}
                async with client.get(f"{DISCORD_API}/users/@me", headers=headers) as response:
                    user = await response.json(content_type=None)
                    if response.status != 200:
                        raise web.HTTPUnauthorized(text="Discord user information could not be read.")
                async with client.get(f"{DISCORD_API}/users/@me/guilds", headers=headers) as response:
                    guilds = await response.json(content_type=None)
                    if response.status != 200:
                        raise web.HTTPUnauthorized(text="Discord server access could not be read.")
        except aiohttp.ClientError as exc:
            logger.warning("Discord OAuth network error: %s", exc)
            raise web.HTTPBadGateway(text="Discord is temporarily unavailable. Please try again.") from exc

        session_id = secrets.token_urlsafe(48)
        self.sessions[session_id] = {
            "user": {"id": str(user["id"]), "username": user.get("global_name") or user.get("username", "Discord user"), "avatar": user.get("avatar")},
            "guilds": guilds,
            "expires": datetime.now(timezone.utc) + SESSION_TTL,
        }
        response = web.HTTPFound("/")
        secure = os.getenv("DASHBOARD_SECURE_COOKIES", "").lower() in {"1", "true", "yes"}
        response.set_cookie(self.cookie_name, self._sign_session(session_id), httponly=True, secure=secure, samesite="Lax", max_age=int(SESSION_TTL.total_seconds()), path="/")
        raise response

    async def logout(self, request: web.Request) -> web.Response:
        session_id, _ = self._session(request)
        if session_id:
            self.sessions.pop(session_id, None)
        response = web.json_response({"ok": True})
        response.del_cookie(self.cookie_name, path="/")
        return response

    def _sign_session(self, session_id: str) -> str:
        signature = hmac.new(self.session_secret.encode(), session_id.encode(), hashlib.sha256).hexdigest()
        return f"{session_id}.{signature}"

    def _session(self, request: web.Request) -> tuple[str | None, dict[str, Any] | None]:
        raw = request.cookies.get(self.cookie_name, "")
        session_id, _, supplied = raw.partition(".")
        if not session_id or not supplied or not hmac.compare_digest(self._sign_session(session_id), raw):
            return None, None
        session = self.sessions.get(session_id)
        if not session or session["expires"] < datetime.now(timezone.utc):
            self.sessions.pop(session_id, None)
            return None, None
        return session_id, session

    def _require_session(self, request: web.Request) -> dict[str, Any]:
        _, session = self._session(request)
        if not session:
            raise web.HTTPUnauthorized(text="Sign in with Discord to continue.")
        return session

    def _manageable_guilds(self, session: dict[str, Any]) -> list[dict[str, Any]]:
        result = []
        for item in session["guilds"]:
            try:
                permissions = int(item.get("permissions", 0))
            except (ValueError, TypeError):
                permissions = 0
            if not (item.get("owner") or permissions & (MANAGE_GUILD | ADMINISTRATOR)):
                continue
            guild = self.bot.get_guild(int(item["id"]))
            if not guild:
                continue
            result.append({
                "id": str(guild.id), "name": guild.name, "icon": item.get("icon"),
                "member_count": guild.member_count or 0,
                "owner": bool(item.get("owner")), "permissions": str(permissions),
            })
        return sorted(result, key=lambda g: g["name"].lower())

    def _require_guild_access(self, request: web.Request) -> tuple[Any, dict[str, Any]]:
        session = self._require_session(request)
        guild_id = request.match_info["guild_id"]
        guild = next((g for g in self._manageable_guilds(session) if g["id"] == guild_id), None)
        if not guild:
            raise web.HTTPForbidden(text="You need Manage Server or Administrator permission for this server.")
        return self.bot.get_guild(int(guild_id)), session

    async def me(self, request: web.Request) -> web.Response:
        _, session = self._session(request)
        bot_id = str(self.bot.user.id) if self.bot.user else (os.getenv("DASHBOARD_CLIENT_ID") or "")
        invite_url = f"https://discord.com/oauth2/authorize?client_id={bot_id}&permissions=8&scope=bot%20applications.commands" if bot_id else "https://discord.com"
        return web.json_response({
            "authenticated": bool(session),
            "user": session["user"] if session else None,
            "oauth_configured": self._configured,
            "bot": {
                "id": bot_id,
                "name": self.bot.user.name if self.bot.user else "Helix",
                "avatar": str(self.bot.user.display_avatar.url) if self.bot.user else "",
                "guilds_count": len(self.bot.guilds),
                "users_count": sum(g.member_count or 0 for g in self.bot.guilds),
                "invite_url": invite_url
            }
        })

    async def guilds(self, request: web.Request) -> web.Response:
        session = self._require_session(request)
        return web.json_response({"guilds": self._manageable_guilds(session)})

    async def overview(self, request: web.Request) -> web.Response:
        guild, _ = self._require_guild_access(request)
        analytics = await get_server_analytics(guild.id)
        async with get_connection() as conn:
            cursor = await conn.execute("SELECT COUNT(*) FROM mod_logs WHERE guild_id = ? AND created_at >= datetime('now', '-1 day')", (guild.id,))
            actions_today = (await cursor.fetchone())[0] or 0
            await cursor.close()
            cursor = await conn.execute("SELECT COUNT(*) FROM tickets WHERE guild_id = ? AND status = 'open'", (guild.id,))
            open_tickets = (await cursor.fetchone())[0] or 0
            await cursor.close()

        # Format top_channels safely
        raw_top = analytics.get("top_channels", [])
        clean_top = []
        for r in raw_top:
            if isinstance(r, dict):
                clean_top.append({"channel_id": str(r.get("channel_id", "")), "total": int(r.get("total", 0))})
            elif hasattr(r, "__getitem__"):
                clean_top.append({"channel_id": str(r[0]), "total": int(r[1])})

        clean_analytics = {
            "msg_1d": int(analytics.get("msg_1d", 0) or 0),
            "msg_7d": int(analytics.get("msg_7d", 0) or 0),
            "msg_30d": int(analytics.get("msg_30d", 0) or 0),
            "vc_1d_hrs": float(analytics.get("vc_1d_hrs", 0) or 0.0),
            "vc_7d_hrs": float(analytics.get("vc_7d_hrs", 0) or 0.0),
            "vc_30d_hrs": float(analytics.get("vc_30d_hrs", 0) or 0.0),
            "top_channels": clean_top
        }

        return web.json_response({
            "guild": self._guild_data(guild),
            "analytics": clean_analytics,
            "metrics": {
                "members": int(guild.member_count or 0),
                "messages_today": clean_analytics["msg_1d"],
                "mod_actions_today": int(actions_today),
                "open_tickets": int(open_tickets)
            },
        }, dumps=_json)

    async def settings(self, request: web.Request) -> web.Response:
        guild, _ = self._require_guild_access(request)
        cfg = await get_guild_config(guild.id)
        
        # Fetch ticket config safely if table exists
        t_cfg = {}
        try:
            async with get_connection() as conn:
                cur = await conn.execute("SELECT * FROM guild_ticket_config WHERE guild_id = ?", (guild.id,))
                row = await cur.fetchone()
                if row:
                    t_cfg = dict(row)
                await cur.close()
        except Exception:
            pass

        cfg["ticket_config"] = t_cfg

        return web.json_response({
            "guild": self._guild_data(guild),
            "config": cfg,
            "channels": self._channels(guild),
            "categories": self._categories(guild),
            "roles": self._roles(guild)
        }, dumps=_json)

    async def update_settings(self, request: web.Request) -> web.Response:
        guild, _ = self._require_guild_access(request)
        try:
            body = await request.json()
        except Exception as exc:
            raise web.HTTPBadRequest(text="Settings must be JSON.") from exc
        patch = body.get("patch") if isinstance(body, dict) else None
        if not isinstance(patch, dict):
            raise web.HTTPBadRequest(text="Expected a settings patch.")
        unknown = set(patch) - ALLOWED_SETTINGS
        if unknown:
            raise web.HTTPBadRequest(text=f"Unsupported dashboard setting: {', '.join(sorted(unknown))}")
        
        clean = self._validate_patch(patch, guild)
        await set_guild_config(guild.id, clean)
        return web.json_response({"ok": True, "config": await get_guild_config(guild.id)}, dumps=_json)

    async def tickets(self, request: web.Request) -> web.Response:
        guild, _ = self._require_guild_access(request)
        rows = []
        config = {}
        panels = []
        try:
            async with get_connection() as conn:
                cursor = await conn.execute("SELECT id, channel_id, user_id, status, ticket_type, ticket_number, claimed_by, created_at, closed_at FROM tickets WHERE guild_id = ? ORDER BY id DESC LIMIT 50", (guild.id,))
                rows = [dict(row) for row in await cursor.fetchall()]
                await cursor.close()
                cursor = await conn.execute("SELECT open_category_id, closed_category_id, staff_role_id, transcript_channel_id, log_channel_id, next_ticket_number FROM guild_ticket_config WHERE guild_id = ?", (guild.id,))
                config = dict(row) if (row := await cursor.fetchone()) else {}
                await cursor.close()
                cursor = await conn.execute("SELECT id, title, description, message_id, channel_id, options_json, embed_color, created_at FROM ticket_panels WHERE guild_id = ? ORDER BY id DESC", (guild.id,))
                panels = [dict(row) for row in await cursor.fetchall()]
                await cursor.close()
        except Exception as err:
            logger.debug("Failed fetching ticket dashboard data: %s", err)

        return web.json_response({
            "tickets": rows,
            "config": config,
            "panels": panels,
            "channels": self._channels(guild),
            "categories": self._categories(guild),
            "roles": self._roles(guild)
        }, dumps=_json)

    async def update_ticket_config(self, request: web.Request) -> web.Response:
        guild, _ = self._require_guild_access(request)
        body = await request.json()
        open_cat = body.get("open_category_id")
        closed_cat = body.get("closed_category_id")
        staff_role = body.get("staff_role_id")
        trans_chan = body.get("transcript_channel_id")
        log_chan = body.get("log_channel_id")

        async with get_connection() as conn:
            await conn.execute(
                """
                INSERT INTO guild_ticket_config (guild_id, open_category_id, closed_category_id, staff_role_id, transcript_channel_id, log_channel_id, next_ticket_number, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 1, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    open_category_id = excluded.open_category_id,
                    closed_category_id = excluded.closed_category_id,
                    staff_role_id = excluded.staff_role_id,
                    transcript_channel_id = excluded.transcript_channel_id,
                    log_channel_id = excluded.log_channel_id
                """,
                (
                    guild.id,
                    int(open_cat) if open_cat and str(open_cat).isdigit() else None,
                    int(closed_cat) if closed_cat and str(closed_cat).isdigit() else None,
                    int(staff_role) if staff_role and str(staff_role).isdigit() else None,
                    int(trans_chan) if trans_chan and str(trans_chan).isdigit() else None,
                    int(log_chan) if log_chan and str(log_chan).isdigit() else None,
                    datetime.now(timezone.utc).isoformat()
                )
            )
            await conn.commit()
        return web.json_response({"ok": True})

    async def deploy_ticket_panel(self, request: web.Request) -> web.Response:
        guild, _ = self._require_guild_access(request)
        body = await request.json()
        channel_id = body.get("channel_id")
        title = body.get("title") or "Support Center"
        description = body.get("description") or "Select a category below to create a private ticket."
        color_hex = body.get("color_hex") or "#5865F2"
        image_url = body.get("image_url") or None
        options = body.get("options") or []

        if not channel_id:
            raise web.HTTPBadRequest(text="Please select a target channel.")

        channel = guild.get_channel(int(channel_id))
        if not channel or not isinstance(channel, discord.TextChannel):
            raise web.HTTPBadRequest(text="Target channel must be an existing text channel.")

        tickets_cog = self.bot.get_cog("Tickets")
        if not tickets_cog:
            raise web.HTTPServiceUnavailable(text="Tickets Cog is not currently active.")

        panel_id, message_id = await tickets_cog.deploy_panel_direct(
            guild=guild,
            channel=channel,
            title=title,
            description=description,
            options=options,
            color_hex=color_hex,
            image_url=image_url
        )

        return web.json_response({
            "ok": True,
            "panel": {
                "id": panel_id,
                "guild_id": str(guild.id),
                "channel_id": str(channel.id),
                "message_id": str(message_id),
                "title": title,
                "description": description,
                "options_json": json.dumps(options),
                "embed_color": color_hex
            }
        })

    async def edit_ticket_panel(self, request: web.Request) -> web.Response:
        guild, _ = self._require_guild_access(request)
        panel_id = int(request.match_info["panel_id"])
        body = await request.json()
        title = body.get("title") or "Support Center"
        description = body.get("description") or "Select a category below to create a private ticket."
        color_hex = body.get("color_hex") or "#5865F2"
        image_url = body.get("image_url") or None
        options = body.get("options") or []

        tickets_cog = self.bot.get_cog("Tickets")
        if not tickets_cog:
            raise web.HTTPServiceUnavailable(text="Tickets Cog is not active.")

        success = await tickets_cog.edit_panel_direct(
            panel_id=panel_id,
            guild=guild,
            title=title,
            description=description,
            options=options,
            color_hex=color_hex,
            image_url=image_url
        )
        if not success:
            raise web.HTTPNotFound(text="Ticket panel not found.")

        return web.json_response({"ok": True})

    async def delete_ticket_panel(self, request: web.Request) -> web.Response:
        guild, _ = self._require_guild_access(request)
        panel_id = int(request.match_info["panel_id"])
        tickets_cog = self.bot.get_cog("Tickets")
        if tickets_cog:
            await tickets_cog.delete_panel_direct(panel_id=panel_id, guild=guild)

        return web.json_response({"ok": True})

    async def close_ticket_direct(self, request: web.Request) -> web.Response:
        guild, user_info = self._require_guild_access(request)
        ticket_id = int(request.match_info["ticket_id"])
        tickets_cog = self.bot.get_cog("Tickets")
        if not tickets_cog:
            raise web.HTTPServiceUnavailable(text="Tickets Cog is not active.")

        closed_by = user_info.get("username", "Dashboard Admin")
        success = await tickets_cog.close_ticket_by_id(ticket_id=ticket_id, guild=guild, closed_by_name=closed_by)
        return web.json_response({"ok": success})

    async def giveaways(self, request: web.Request) -> web.Response:
        guild, _ = self._require_guild_access(request)
        rows = []
        try:
            async with get_connection() as conn:
                cursor = await conn.execute("SELECT id, channel_id, message_id, host_id, prize, winners_count, end_time, ended, created_at FROM giveaways WHERE guild_id = ? ORDER BY end_time DESC LIMIT 50", (guild.id,))
                rows = [dict(row) for row in await cursor.fetchall()]
                await cursor.close()
        except Exception:
            pass
        return web.json_response({"giveaways": rows}, dumps=_json)

    async def economy(self, request: web.Request) -> web.Response:
        guild, _ = self._require_guild_access(request)
        leaderboard = []
        shop_items = []
        try:
            async with get_connection() as conn:
                cursor = await conn.execute("SELECT user_id, wallet, bank, (wallet + bank) as net_worth FROM economy WHERE guild_id = ? ORDER BY net_worth DESC LIMIT 25", (guild.id,))
                leaderboard = [dict(row) for row in await cursor.fetchall()]
                await cursor.close()
                cursor = await conn.execute("SELECT id, item_id, name, description, price, role_id FROM guild_shop_items WHERE guild_id = ? ORDER BY price ASC", (guild.id,))
                shop_items = [dict(row) for row in await cursor.fetchall()]
                await cursor.close()
        except Exception:
            pass
        return web.json_response({"leaderboard": leaderboard, "shop_items": shop_items}, dumps=_json)

    async def vanity(self, request: web.Request) -> web.Response:
        guild, _ = self._require_guild_access(request)
        vanities = []
        try:
            async with get_connection() as conn:
                cursor = await conn.execute("SELECT vanity as vanity_code, user_id, created_at FROM vanity_trackers ORDER BY created_at DESC LIMIT 50")
                vanities = [dict(row) for row in await cursor.fetchall()]
                await cursor.close()
        except Exception:
            pass
        return web.json_response({"vanities": vanities}, dumps=_json)

    async def activity(self, request: web.Request) -> web.Response:
        guild, _ = self._require_guild_access(request)
        rows = []
        try:
            async with get_connection() as conn:
                cursor = await conn.execute("SELECT id, moderator_id, target_id, action, reason, created_at FROM mod_logs WHERE guild_id = ? ORDER BY id DESC LIMIT 50", (guild.id,))
                rows = [dict(row) for row in await cursor.fetchall()]
                await cursor.close()
        except Exception:
            pass
        return web.json_response({"activity": rows}, dumps=_json)

    async def community_get(self, request: web.Request) -> web.Response:
        guild, _ = self._require_guild_access(request)
        autoroles = []
        welcome_cfg = {}
        starboard_cfg = {}

        try:
            async with get_connection() as conn:
                # Autoroles
                cur = await conn.execute("SELECT role_id, is_bot FROM autoroles WHERE guild_id = ?", (guild.id,))
                autoroles = [dict(r) for r in await cur.fetchall()]
                await cur.close()

                # Welcome config
                cur = await conn.execute("SELECT * FROM welcome_config WHERE guild_id = ?", (guild.id,))
                w_row = await cur.fetchone()
                if w_row:
                    welcome_cfg = dict(w_row)
                await cur.close()

                # Starboard config
                cur = await conn.execute("SELECT * FROM starboard_config WHERE guild_id = ?", (guild.id,))
                s_row = await cur.fetchone()
                if s_row:
                    starboard_cfg = dict(s_row)
                await cur.close()
        except Exception as e:
            logger.warning("Error fetching community config: %s", e)

        return web.json_response({
            "autoroles": autoroles,
            "welcome": welcome_cfg,
            "starboard": starboard_cfg
        }, dumps=_json)

    async def community_post(self, request: web.Request) -> web.Response:
        guild, _ = self._require_guild_access(request)
        body = await request.json()

        welcome_data = body.get("welcome", {})
        starboard_data = body.get("starboard", {})
        human_roles = body.get("human_roles", [])
        bot_roles = body.get("bot_roles", [])

        try:
            async with get_connection() as conn:
                # Save welcome config
                w_ch = welcome_data.get("welcome_channel_id")
                g_ch = welcome_data.get("goodbye_channel_id")
                w_msg = welcome_data.get("welcome_msg")
                g_msg = welcome_data.get("goodbye_msg")
                w_type = welcome_data.get("welcome_type", "card")
                dm_en = 1 if welcome_data.get("dm_enabled") else 0
                is_en = 1 if welcome_data.get("is_enabled", True) else 0

                await conn.execute("""
                    INSERT INTO welcome_config (guild_id, welcome_channel_id, goodbye_channel_id, welcome_msg, goodbye_msg, welcome_type, dm_enabled, is_enabled)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(guild_id) DO UPDATE SET
                        welcome_channel_id = excluded.welcome_channel_id,
                        goodbye_channel_id = excluded.goodbye_channel_id,
                        welcome_msg = excluded.welcome_msg,
                        goodbye_msg = excluded.goodbye_msg,
                        welcome_type = excluded.welcome_type,
                        dm_enabled = excluded.dm_enabled,
                        is_enabled = excluded.is_enabled
                """, (guild.id, int(w_ch) if w_ch else None, int(g_ch) if g_ch else None, w_msg, g_msg, w_type, dm_en, is_en))

                # Save starboard config
                sb_ch = starboard_data.get("channel_id")
                sb_thresh = int(starboard_data.get("threshold", 3))
                sb_emoji = starboard_data.get("emoji", "⭐")
                sb_en = 1 if starboard_data.get("is_enabled", True) else 0

                await conn.execute("""
                    INSERT INTO starboard_config (guild_id, channel_id, threshold, emoji, is_enabled)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(guild_id) DO UPDATE SET
                        channel_id = excluded.channel_id,
                        threshold = excluded.threshold,
                        emoji = excluded.emoji,
                        is_enabled = excluded.is_enabled
                """, (guild.id, int(sb_ch) if sb_ch else None, sb_thresh, sb_emoji, sb_en))

                # Save autoroles
                await conn.execute("DELETE FROM autoroles WHERE guild_id = ?", (guild.id,))
                for rid in human_roles:
                    if str(rid).isdigit():
                        await conn.execute("INSERT OR REPLACE INTO autoroles (guild_id, role_id, is_bot) VALUES (?, ?, 0)", (guild.id, int(rid)))
                for rid in bot_roles:
                    if str(rid).isdigit():
                        await conn.execute("INSERT OR REPLACE INTO autoroles (guild_id, role_id, is_bot) VALUES (?, ?, 1)", (guild.id, int(rid)))

                await conn.commit()
        except Exception as e:
            logger.exception("Error saving community config: %s", e)
            raise web.HTTPBadRequest(text=f"Failed to save settings: {e}")

        return web.json_response({"ok": True})

    def _guild_data(self, guild) -> dict[str, Any]:
        icon = str(guild.icon.url) if guild and getattr(guild, "icon", None) else None
        return {"id": str(guild.id), "name": guild.name, "icon_url": icon, "member_count": guild.member_count or 0}

    def _channels(self, guild) -> list[dict[str, Any]]:
        return [
            {"id": str(channel.id), "name": channel.name, "type": "category" if isinstance(channel, discord.CategoryChannel) else "voice" if isinstance(channel, discord.VoiceChannel) else "text"}
            for channel in sorted(guild.channels, key=lambda ch: (getattr(ch, "position", 0), getattr(ch, "name", "")))
            if not isinstance(channel, discord.CategoryChannel)
        ]

    def _categories(self, guild) -> list[dict[str, Any]]:
        return [{"id": str(cat.id), "name": cat.name} for cat in sorted(guild.categories, key=lambda c: (c.position, c.name))]

    def _roles(self, guild) -> list[dict[str, Any]]:
        return [{"id": str(role.id), "name": role.name, "color": str(role.color)} for role in reversed(guild.roles) if not role.is_default()]

    def _validate_patch(self, patch: dict[str, Any], guild) -> dict[str, Any]:
        clean: dict[str, Any] = {}
        channel_keys = {
            "level_channel_id", "ai_channel_id", "mod_log_channel", "automod_log_channel_id",
            "ban_unban_log_channel_id", "message_log_channel_id", "image_log_channel_id",
            "join_leave_log_channel_id", "role_create_log_channel_id", "role_update_log_channel_id",
            "role_delete_log_channel_id", "role_add_remove_log_channel_id",
            "channel_create_log_channel_id", "channel_delete_log_channel_id", "voice_log_channel_id",
            "ticket_open_category_id", "ticket_closed_category_id", "ticket_transcript_channel_id", "ticket_log_channel_id"
        }
        bool_keys = {
            "xp_enabled", "modlog_dm_notifications", "automod_enabled", "automod_block_markdown",
            "automod_block_invites", "automod_block_scam", "antinuke_enabled", "antinuke_strict", "antinuke_recovery"
        }
        list_keys = {"ignored_xp_channels", "automod_ignored_channels", "automod_ignored_roles", "antinuke_whitelisted_users", "antinuke_whitelisted_roles"}

        for key, value in patch.items():
            if key in bool_keys:
                if not isinstance(value, bool):
                    raise web.HTTPBadRequest(text=f"{key} must be true or false.")
                clean[key] = value
            elif key in channel_keys:
                if value in (None, "", 0):
                    clean[key] = None
                elif str(value).isdigit():
                    clean[key] = int(value)
                else:
                    raise web.HTTPBadRequest(text=f"{key} must reference a channel ID.")
            elif key in list_keys:
                if not isinstance(value, list) or not all(str(item).isdigit() for item in value):
                    raise web.HTTPBadRequest(text=f"{key} must be a list of IDs.")
                clean[key] = [int(item) for item in value]
            elif key == "prefix":
                if not isinstance(value, str) or not value.strip() or len(value.strip()) > 5:
                    raise web.HTTPBadRequest(text="Prefix must be between 1 and 5 characters.")
                clean[key] = value.strip()
            elif key in {"xp_per_message", "xp_cooldown_seconds"}:
                if not isinstance(value, int) or value < 0 or value > 3600:
                    raise web.HTTPBadRequest(text=f"{key} is outside the allowed range.")
                clean[key] = value
            elif key == "ai_provider":
                if value not in {"gemini", "groq", "openai"}:
                    raise web.HTTPBadRequest(text="Unsupported AI provider.")
                clean[key] = value
            elif key == "automod_punishment":
                if value not in {"block", "alert", "timeout", "kick", "ban"}:
                    raise web.HTTPBadRequest(text="Unsupported AutoMod action.")
                clean[key] = value
            elif key == "antinuke_punishment":
                if value not in {"ban", "kick", "strip_roles", "quarantine"}:
                    raise web.HTTPBadRequest(text="Unsupported Anti-Nuke action.")
                clean[key] = value
            elif key in {"level_rewards", "antinuke_thresholds"}:
                if not isinstance(value, dict):
                    raise web.HTTPBadRequest(text=f"{key} must be an object.")
                clean[key] = value
            elif key == "ticket_staff_role_id":
                clean[key] = int(value) if value and str(value).isdigit() else None
            else:
                raise web.HTTPBadRequest(text=f"Invalid setting: {key}")
        return clean


def _json(value: Any) -> str:
    return json.dumps(value, default=str)


async def setup(bot: commands.Bot):
    await bot.add_cog(DashboardCog(bot))
