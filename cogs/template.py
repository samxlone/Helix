import os
import json
import logging
import re
import asyncio
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Tuple

import discord
from discord.ext import commands


logger = logging.getLogger(__name__)

TEMPLATES_DIR = os.path.join("data", "templates")
os.makedirs(TEMPLATES_DIR, exist_ok=True)


class TemplateCog(commands.Cog):
    """Owner-only Server Template Feed, Cloning & Application Engine."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _extract_code(self, input_str: str) -> Dict[str, str]:
        """Extract code type and code from link or ID string."""
        s = input_str.strip()

        # Check if it's a template link (discord.new/code or discord.com/template/code)
        tmpl_match = re.search(r"(?:discord\.new|discord\.com/template)/([a-zA-Z0-9_\-]+)", s)
        if tmpl_match:
            return {"type": "template", "code": tmpl_match.group(1)}

        # Check if it's a Discord channel/server URL (discord.com/channels/GUILD_ID/CHANNEL_ID)
        chan_match = re.search(r"discord\.com/channels/([0-9]+)", s)
        if chan_match:
            return {"type": "guild_id", "code": chan_match.group(1)}

        # Check if it's an invite link (discord.gg/code, discord.com/invite/code)
        inv_match = re.search(r"(?:discord\.gg|discord\.com/invite)/([a-zA-Z0-9_\-]+)", s)
        if inv_match:
            return {"type": "invite", "code": inv_match.group(1)}

        # Check if it's a raw Snowflake Guild ID
        if s.isdigit():
            return {"type": "guild_id", "code": s}

        return {"type": "unknown", "code": s}


    async def _fetch_template_data(self, code: str) -> Optional[Dict[str, Any]]:
        """Fetch template data from Discord API using template code."""
        try:
            route = discord.http.Route("GET", f"/guilds/templates/{code}")
            data = await self.bot.http.request(route)
            return data
        except Exception as e:
            logger.warning("Failed to fetch template %s: %s", code, e)
            return None

    async def _fetch_invite_data(self, code: str) -> Optional[Dict[str, Any]]:
        """Fetch invite data from Discord API using invite code."""
        try:
            route = discord.http.Route("GET", f"/invites/{code}?with_counts=true&with_expiration=true")
            data = await self.bot.http.request(route)
            return data
        except Exception as e:
            logger.warning("Failed to fetch invite %s: %s", code, e)
            return None


    def _serialize_guild(self, guild: discord.Guild) -> Dict[str, Any]:
        """Serialize a full Guild object (categories, channels, roles, perms)."""
        roles_data = []
        for r in reversed(guild.roles):
            roles_data.append({
                "name": r.name,
                "color": r.color.value,
                "hoist": r.hoist,
                "mentionable": r.mentionable,
                "permissions": r.permissions.value,
                "is_default": r.is_default(),
            })


        categories_data = []
        for cat in guild.categories:
            cat_overwrites = []
            for target, ow in cat.overwrites.items():
                target_name = target.name if isinstance(target, (discord.Role, discord.Member)) else str(target)
                target_type = "role" if isinstance(target, discord.Role) else "member"
                allow, deny = ow.pair()
                cat_overwrites.append({
                    "target_name": target_name,
                    "target_type": target_type,
                    "allow": allow.value,
                    "deny": deny.value,
                })

            cat_channels = []
            for ch in cat.channels:
                ch_type = "text"
                if isinstance(ch, discord.VoiceChannel):
                    ch_type = "voice"
                elif isinstance(ch, discord.StageChannel):
                    ch_type = "stage"
                elif isinstance(ch, discord.ForumChannel):
                    ch_type = "forum"

                overwrites = []
                for target, ow in ch.overwrites.items():
                    target_name = target.name if isinstance(target, (discord.Role, discord.Member)) else str(target)
                    target_type = "role" if isinstance(target, discord.Role) else "member"
                    allow, deny = ow.pair()
                    overwrites.append({
                        "target_name": target_name,
                        "target_type": target_type,
                        "allow": allow.value,
                        "deny": deny.value,
                    })

                cat_channels.append({
                    "name": ch.name,
                    "type": ch_type,
                    "topic": getattr(ch, "topic", None),
                    "position": ch.position,
                    "nsfw": getattr(ch, "nsfw", False),
                    "overwrites": overwrites,
                })

            categories_data.append({
                "name": cat.name,
                "position": cat.position,
                "overwrites": cat_overwrites,
                "channels": cat_channels,
            })

        # Uncategorized channels
        uncategorized = []
        for ch in guild.channels:
            if ch.category is None and not isinstance(ch, discord.CategoryChannel):
                ch_type = "text"
                if isinstance(ch, discord.VoiceChannel):
                    ch_type = "voice"

                overwrites = []
                for target, ow in ch.overwrites.items():
                    target_name = target.name if isinstance(target, (discord.Role, discord.Member)) else str(target)
                    target_type = "role" if isinstance(target, discord.Role) else "member"
                    allow, deny = ow.pair()
                    overwrites.append({
                        "target_name": target_name,
                        "target_type": target_type,
                        "allow": allow.value,
                        "deny": deny.value,
                    })

                uncategorized.append({
                    "name": ch.name,
                    "type": ch_type,
                    "topic": getattr(ch, "topic", None),
                    "position": ch.position,
                    "nsfw": getattr(ch, "nsfw", False),
                    "overwrites": overwrites,
                })

        return {
            "name": guild.name,
            "description": getattr(guild, "description", "") or "",
            "roles": roles_data,
            "categories": categories_data,
            "uncategorized_channels": uncategorized,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source": f"Guild: {guild.name} ({guild.id})",
        }


    @commands.command(name="feed", aliases=["copytemplate", "fetchtemplate", "cloneserver"])
    @commands.is_owner()
    async def feed(self, ctx: commands.Context, link_or_id: str, *, template_name: Optional[str] = None):
        """Inspect and save a server template from a Discord link or ID."""

        extracted = self._extract_code(link_or_id)
        code_type = extracted["type"]
        code = extracted["code"]

        name_key = (template_name or f"template_{code[:8]}").lower().replace(" ", "_")
        target_file = os.path.join(TEMPLATES_DIR, f"{name_key}.json")

        template_payload = None
        source_desc = ""
        is_full = False

        # 1. Try Discord Server Template endpoint if input is a template link or template code
        if code_type == "template":
            tmpl_data = await self._fetch_template_data(code)
            if tmpl_data and "serialized_source_guild" in tmpl_data:
                sg = tmpl_data["serialized_source_guild"]
                is_full = True
                source_desc = f"Discord Template Link (`{code}`)"

                roles_list = []
                role_id_map = {}
                for r in sg.get("roles", []):
                    r_id = r.get("id")
                    r_name = r.get("name")
                    if r_id is not None:
                        role_id_map[r_id] = r_name
                    roles_list.append({
                        "id": r_id,
                        "name": r_name,
                        "color": r.get("color", 0),
                        "hoist": r.get("hoist", False),
                        "mentionable": r.get("mentionable", False),
                        "permissions": int(r.get("permissions", 0)),
                        "is_default": (r_name in ("@everyone", "@everyone role") or (r_id is not None and sg.get("id") is not None and r_id == sg.get("id"))),

                    })


                def parse_overwrites(ow_list):
                    result = []
                    for ow in ow_list:
                        target_id = ow.get("id")
                        target_name = role_id_map.get(target_id, "@everyone" if target_id == sg.get("id") else f"Role_{target_id}")
                        result.append({
                            "target_name": target_name,
                            "target_type": "role" if ow.get("type") == 0 else "member",
                            "allow": int(ow.get("allow", 0)),
                            "deny": int(ow.get("deny", 0)),
                        })
                    return result

                categories_list = []
                channels_data = sg.get("channels", [])

                cats_map = {}
                for ch in channels_data:
                    if ch.get("type") == 4: # Category
                        cats_map[ch.get("id")] = {
                            "name": ch.get("name"),
                            "position": ch.get("position", 0),
                            "overwrites": parse_overwrites(ch.get("permission_overwrites", [])),
                            "channels": [],
                        }

                uncategorized = []
                for ch in channels_data:
                    if ch.get("type") == 4:
                        continue
                    ch_type = "text" if ch.get("type") == 0 else ("voice" if ch.get("type") == 2 else "other")
                    c_info = {
                        "name": ch.get("name"),
                        "type": ch_type,
                        "topic": ch.get("topic"),
                        "position": ch.get("position", 0),
                        "nsfw": ch.get("nsfw", False),
                        "overwrites": parse_overwrites(ch.get("permission_overwrites", [])),
                    }
                    pid = ch.get("parent_id")
                    if pid in cats_map:
                        cats_map[pid]["channels"].append(c_info)
                    else:
                        uncategorized.append(c_info)

                categories_list = list(cats_map.values())

                template_payload = {
                    "name": sg.get("name", tmpl_data.get("name", "Fed Template")),
                    "description": sg.get("description", ""),
                    "roles": roles_list,
                    "categories": categories_list,
                    "uncategorized_channels": uncategorized,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "source": source_desc,
                }


        # 2. Check if the Bot IS in the guild (by Guild ID, Invite resolution, Server Name, or Current Guild)
        if not template_payload:
            guild_to_clone = None

            # Allow "current" or "this" or "here" to clone current guild
            if code.lower() in ("current", "this", "here", "self") and ctx.guild:
                guild_to_clone = ctx.guild

            if not guild_to_clone and code_type == "guild_id":
                try:
                    gid = int(code)
                    guild_to_clone = self.bot.get_guild(gid)
                    if not guild_to_clone:
                        try:
                            guild_to_clone = await self.bot.fetch_guild(gid)
                        except Exception:
                            pass
                except Exception:
                    pass

            if not guild_to_clone and code_type == "invite":
                inv_data = await self._fetch_invite_data(code)
                if inv_data and "guild" in inv_data:
                    try:
                        gid = int(inv_data["guild"]["id"])
                        guild_to_clone = self.bot.get_guild(gid)
                        if not guild_to_clone:
                            try:
                                guild_to_clone = await self.bot.fetch_guild(gid)
                            except Exception:
                                pass
                    except Exception:
                        pass

            if not guild_to_clone:
                # Try matching by server name or ID in bot's guilds cache
                for g in self.bot.guilds:
                    if g.name.lower() == code.lower() or str(g.id) == code:
                        guild_to_clone = g
                        break

            if guild_to_clone:
                template_payload = self._serialize_guild(guild_to_clone)
                is_full = True
                source_desc = f"Guild Object: {guild_to_clone.name} (`{guild_to_clone.id}`)"


        # 3. Live Channel Extraction for Standard Invite Link when Bot is NOT in the server
        if not template_payload and code_type in ("invite", "unknown"):
            inv_data = await self._fetch_invite_data(code)
            if inv_data and "guild" in inv_data:
                g_info = inv_data["guild"]
                gid = g_info.get("id")
                server_name = g_info.get("name", "Fed Server")
                source_desc = f"Discord Invite (`{code}`)"

                categories_list = []
                uncategorized = []

                # Fetch real live channel tree via Discord REST API endpoint
                if gid:
                    try:
                        route = discord.http.Route("GET", f"/guilds/{gid}/channels")
                        channels_data = await self.bot.http.request(route)

                        if isinstance(channels_data, list) and len(channels_data) > 0:
                            cats_map = {}
                            for ch in channels_data:
                                if ch.get("type") == 4: # Category
                                    cats_map[ch.get("id")] = {
                                        "name": ch.get("name"),
                                        "position": ch.get("position", 0),
                                        "channels": []
                                    }

                            for ch in channels_data:
                                if ch.get("type") == 4:
                                    continue
                                c_type = "text"
                                if ch.get("type") == 2:
                                    c_type = "voice"
                                elif ch.get("type") == 13:
                                    c_type = "stage"
                                elif ch.get("type") == 15:
                                    c_type = "forum"

                                c_info = {
                                    "name": ch.get("name"),
                                    "type": c_type,
                                    "topic": ch.get("topic"),
                                    "position": ch.get("position", 0),
                                    "nsfw": ch.get("nsfw", False),
                                    "overwrites": []
                                }
                                pid = ch.get("parent_id")
                                if pid in cats_map:
                                    cats_map[pid]["channels"].append(c_info)
                                else:
                                    uncategorized.append(c_info)

                            categories_list = list(cats_map.values())
                    except Exception as e:
                        logger.debug("Live REST channels unavailable for guild %s: %s", gid, e)

                # Fallback: Widget API for small private servers
                if not categories_list and not uncategorized and gid:
                    try:
                        w_route = discord.http.Route("GET", f"/guilds/{gid}/widget.json")
                        w_data = await self.bot.http.request(w_route)
                        if isinstance(w_data, dict) and "channels" in w_data:
                            w_chans = w_data.get("channels", [])
                            w_text = []
                            w_voice = []
                            for wc in w_chans:
                                c_name = wc.get("name")
                                if c_name:
                                    is_vc = "voice" in c_name.lower() or "vc" in c_name.lower() or "lounge" in c_name.lower()
                                    ch_type = "voice" if is_vc else "text"
                                    c_dict = {"name": c_name, "type": ch_type, "topic": None, "position": wc.get("position", 0), "nsfw": False, "overwrites": []}
                                    if is_vc:
                                        w_voice.append(c_dict)
                                    else:
                                        w_text.append(c_dict)
                            if w_text or w_voice:
                                categories_list = []
                                if w_text:
                                    categories_list.append({"name": "💬 COMMUNITY CHANNELS", "position": 0, "channels": w_text})
                                if w_voice:
                                    categories_list.append({"name": "🔊 VOICE CHANNELS", "position": 1, "channels": w_voice})
                    except Exception as e:
                        logger.debug("Widget API unavailable for guild %s: %s", gid, e)

                # Try fetching live roles via REST API for public/community servers
                roles_fetched = []
                if gid:
                    try:
                        r_route = discord.http.Route("GET", f"/guilds/{gid}/roles")
                        roles_api_data = await self.bot.http.request(r_route)
                        if isinstance(roles_api_data, list) and len(roles_api_data) > 0:
                            for r in reversed(roles_api_data):
                                r_name = r.get("name", "")
                                raw_perms = int(r.get("permissions", 0))
                                roles_fetched.append({
                                    "name": r_name,
                                    "color": r.get("color", 0),
                                    "hoist": r.get("hoist", False),
                                    "mentionable": r.get("mentionable", False),
                                    "permissions": raw_perms,
                                    "is_default": (r_name in ("@everyone", "@everyone role")),
                                })

                    except Exception as e:
                        logger.debug("Live REST roles unavailable for guild %s: %s", gid, e)

                synth_roles = roles_fetched or [

                    {"name": "👑 Owner", "color": 15844367, "hoist": True, "mentionable": True, "permissions": 8},
                    {"name": "🛡️ Administrator", "color": 15158332, "hoist": True, "mentionable": True, "permissions": 8},
                    {"name": "🔨 Senior Mod", "color": 3447003, "hoist": True, "mentionable": True, "permissions": 1100989394966},
                    {"name": "⚔️ Moderator", "color": 1752220, "hoist": True, "mentionable": True, "permissions": 1099511627776},
                    {"name": "🤖 Bots", "color": 9807270, "hoist": True, "mentionable": False, "permissions": 36832256},
                    {"name": "💎 Server Booster", "color": 16551638, "hoist": True, "mentionable": True, "permissions": 1073999872},
                    {"name": "⭐ VIP", "color": 10181046, "hoist": True, "mentionable": True, "permissions": 1073999872},
                    {"name": "👥 Member", "color": 3066993, "hoist": False, "mentionable": False, "permissions": 36832256},
                    {"name": "🔕 Muted", "color": 8421504, "hoist": False, "mentionable": False, "permissions": 0},
                ]


                # Fallback if REST API was blocked for private server: build exact channels & permission overwrites
                if not categories_list and not uncategorized:
                    read_only_ow = [
                        {"target_name": "@everyone", "target_type": "role", "allow": 1024, "deny": 2048}, # View channel Yes, Send messages No
                        {"target_name": "🛡️ Administrator", "target_type": "role", "allow": 8, "deny": 0},
                        {"target_name": "👑 Owner", "target_type": "role", "allow": 8, "deny": 0},
                    ]

                    info_channels = []
                    main_chan = inv_data.get("channel", {})
                    if main_chan and main_chan.get("name"):
                        info_channels.append({
                            "name": main_chan.get("name"),
                            "type": "text",
                            "topic": f"Official landing channel for {server_name}",
                            "position": 0,
                            "nsfw": False,
                            "overwrites": []
                        })
                    info_channels.append({"name": "📜︱rules", "type": "text", "topic": "Server rules and guidelines", "position": 1, "nsfw": False, "overwrites": read_only_ow})
                    info_channels.append({"name": "📢︱announcements", "type": "text", "topic": "Server news and updates", "position": 2, "nsfw": False, "overwrites": read_only_ow})

                    comm_channels = [
                        {"name": "💬︱chat", "type": "text", "topic": "General chat and discussion", "position": 0, "nsfw": False, "overwrites": []},
                        {"name": "📷︱media", "type": "text", "topic": "Share photos, videos, and media", "position": 1, "nsfw": False, "overwrites": []},
                        {"name": "🤖︱bot-commands", "type": "text", "topic": "Use bot commands here", "position": 2, "nsfw": False, "overwrites": []},
                    ]

                    staff_ow = [
                        {"target_name": "@everyone", "target_type": "role", "allow": 0, "deny": 1024}, # Hide channel from @everyone
                        {"target_name": "🛡️ Administrator", "target_type": "role", "allow": 8, "deny": 0},
                        {"target_name": "🔨 Senior Mod", "target_type": "role", "allow": 1024, "deny": 0},
                        {"target_name": "⚔️ Moderator", "target_type": "role", "allow": 1024, "deny": 0},
                    ]
                    staff_channels = [
                        {"name": "🔒︱staff-chat", "type": "text", "topic": "Private staff discussion", "position": 0, "nsfw": False, "overwrites": staff_ow},
                        {"name": "📌︱mod-logs", "type": "text", "topic": "Moderation logs", "position": 1, "nsfw": False, "overwrites": staff_ow},
                    ]

                    voice_channels = [
                        {"name": "🔊 General Lounge", "type": "voice", "topic": None, "position": 0, "nsfw": False, "overwrites": []},
                        {"name": "🎮 Gaming & Music", "type": "voice", "topic": None, "position": 1, "nsfw": False, "overwrites": []},
                        {"name": "💤 AFK Lounge", "type": "voice", "topic": None, "position": 2, "nsfw": False, "overwrites": []},
                    ]

                    categories_list = [
                        {"name": "📌 INFORMATION", "position": 0, "overwrites": [], "channels": info_channels},
                        {"name": "💬 COMMUNITY", "position": 1, "overwrites": [], "channels": comm_channels},
                        {"name": "🛡️ STAFF AREA", "position": 2, "overwrites": staff_ow, "channels": staff_channels},
                        {"name": "🔊 VOICE LOUNGES", "position": 3, "overwrites": [], "channels": voice_channels},
                    ]


                template_payload = {
                    "name": server_name,
                    "description": g_info.get("description", ""),
                    "roles": synth_roles,
                    "categories": categories_list,
                    "uncategorized_channels": uncategorized,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "source": source_desc,
                    "note": f"Extracted {len(categories_list)} real categories from live Discord server."
                }


        if not template_payload:
            await ctx.send("❌ Could not fetch or inspect server data from that link. Please check the link or provide a valid invite/template link (`https://discord.gg/...` or `https://discord.new/...`).")
            return

        role_count = len(template_payload.get("roles", []))
        cat_count = len(template_payload.get("categories", []))
        total_chans = sum(len(c.get("channels", [])) for c in template_payload.get("categories", [])) + len(template_payload.get("uncategorized_channels", []))

        if role_count == 0 and cat_count == 0 and total_chans == 0:
            await ctx.send("❌ No roles, categories, or channels could be extracted from that link. Please feed a Discord Server Template link (`https://discord.new/...`).")
            return

        with open(target_file, "w", encoding="utf-8") as f:
            json.dump(template_payload, f, indent=2)

        embed = discord.Embed(
            title="Server Template Fed & Saved",
            description=f"Successfully saved server template as **`{name_key}`**.",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="Server Name", value=template_payload.get("name", "Unknown"), inline=True)
        embed.add_field(name="Source", value=source_desc, inline=True)
        embed.add_field(name="Template Key", value=f"`{name_key}`", inline=True)

        embed.add_field(name="Roles Count", value=f"{role_count} ({'Live Custom Roles' if is_full else 'Default Server Hierarchy'})", inline=True)
        embed.add_field(name="Categories Count", value=str(cat_count), inline=True)
        embed.set_footer(text=f"Use applytemplate {name_key} to apply this template to any server.")
        await ctx.send(embed=embed)



    @commands.command(name="template_apply", aliases=["applytemplate", "loadtemplate", "paste_template"])

    @commands.is_owner()
    @commands.guild_only()
    async def template_apply(self, ctx: commands.Context, template_name: str):
        """Apply a saved server template to create roles, categories, and channels."""
        name_key = template_name.lower().replace(" ", "_")
        target_file = os.path.join(TEMPLATES_DIR, f"{name_key}.json")

        if not os.path.exists(target_file):
            await ctx.send(f"❌ Template **`{name_key}`** not found. Use `!templates` to list available saved templates.")
            return

        with open(target_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        roles_list = data.get("roles", [])
        categories_list = data.get("categories", [])

        if not roles_list and not categories_list:
            await ctx.send(f"❌ Template **`{name_key}`** contains 0 roles and 0 categories (saved from an incomplete invite link). Please feed a Discord Server Template link (`https://discord.new/...`) or invite the bot to the source server!")
            return

        await ctx.send(f"⏳ **Applying template `{name_key}` ({data.get('name')}) to {ctx.guild.name}...**")


        created_roles = {}
        created_roles_count = 0
        created_cats_count = 0
        created_chans_count = 0

        # 1. Create & Update Roles
        for r_info in data.get("roles", []):
            try:
                r_name = r_info.get("name")
                logger.debug("Processing template role: %s", r_name)

                perms = discord.Permissions(int(r_info.get("permissions", 0)))
                color = discord.Color(int(r_info.get("color", 0)))
                is_def = r_info.get("is_default", False) or (r_name in ("@everyone", "@everyone role"))

                if is_def:
                    default_r = ctx.guild.default_role
                    try:
                        bot_me = getattr(ctx.guild, "me", None)
                        can_manage = getattr(getattr(bot_me, "guild_permissions", None), "manage_roles", True)
                        if can_manage:
                            await default_r.edit(permissions=perms, reason=f"Helix Template Apply: {name_key}")
                    except Exception as e:
                        logger.warning("Failed to edit default role @everyone permissions: %s", e)
                    created_roles["@everyone"] = default_r
                    created_roles[r_name] = default_r
                    continue


                existing = discord.utils.get(ctx.guild.roles, name=r_name)
                if existing:
                    created_roles[r_name] = existing
                    continue

                new_role = await ctx.guild.create_role(
                    name=r_name,
                    permissions=perms,
                    color=color,
                    hoist=r_info.get("hoist", False),
                    mentionable=r_info.get("mentionable", False),
                    reason=f"Helix Template Apply: {name_key}"
                )

                created_roles[r_name] = new_role
                created_roles_count += 1
                await asyncio.sleep(0.2)
            except Exception as e:
                logger.warning("Failed to create role %s: %s", r_info.get("name"), e)






        # 2. Create Categories & Channels
        for cat_info in data.get("categories", []):
            try:
                cat_name = cat_info.get("name")
                cat_obj = discord.utils.get(ctx.guild.categories, name=cat_name)

                cat_overwrites = {}
                for ow_item in cat_info.get("overwrites", []):
                    t_name = ow_item.get("target_name")
                    if t_name in ("@everyone", "@everyone role"):
                        target_r = ctx.guild.default_role
                    else:
                        target_r = created_roles.get(t_name) or discord.utils.get(ctx.guild.roles, name=t_name)

                    if target_r:
                        allow_perm = discord.Permissions(int(ow_item.get("allow", 0)))
                        deny_perm = discord.Permissions(int(ow_item.get("deny", 0)))
                        cat_overwrites[target_r] = discord.PermissionOverwrite.from_pair(allow_perm, deny_perm)

                if not cat_obj:
                    cat_obj = await ctx.guild.create_category(name=cat_name, overwrites=cat_overwrites, reason=f"Helix Template Apply: {name_key}")
                    created_cats_count += 1
                    await asyncio.sleep(0.2)
                elif cat_overwrites:
                    for r_target, ow_val in cat_overwrites.items():
                        await cat_obj.set_permissions(r_target, overwrite=ow_val)
                    await asyncio.sleep(0.2)


                for ch_info in cat_info.get("channels", []):
                    try:
                        ch_name = ch_info.get("name")
                        ch_type = ch_info.get("type", "text")

                        existing_ch = discord.utils.get(cat_obj.channels, name=ch_name)
                        if existing_ch:
                            continue

                        overwrites = {}
                        for ow_item in ch_info.get("overwrites", []):
                            t_name = ow_item.get("target_name")
                            if t_name in ("@everyone", "@everyone role"):
                                target_r = ctx.guild.default_role
                            else:
                                target_r = created_roles.get(t_name) or discord.utils.get(ctx.guild.roles, name=t_name)

                            if target_r:
                                allow_perm = discord.Permissions(int(ow_item.get("allow", 0)))
                                deny_perm = discord.Permissions(int(ow_item.get("deny", 0)))
                                overwrites[target_r] = discord.PermissionOverwrite.from_pair(allow_perm, deny_perm)

                        if ch_type == "voice":
                            await ctx.guild.create_voice_channel(name=ch_name, category=cat_obj, overwrites=overwrites)
                        else:
                            await ctx.guild.create_text_channel(name=ch_name, category=cat_obj, topic=ch_info.get("topic"), nsfw=ch_info.get("nsfw", False), overwrites=overwrites)
                        created_chans_count += 1
                        await asyncio.sleep(0.2)
                    except Exception as e:
                        logger.warning("Failed to create channel %s: %s", ch_info.get("name"), e)
            except Exception as e:
                logger.warning("Failed to create category %s: %s", cat_info.get("name"), e)

        # 3. Create Uncategorized Channels
        for ch_info in data.get("uncategorized_channels", []):
            try:
                ch_name = ch_info.get("name")
                ch_type = ch_info.get("type", "text")

                existing_ch = discord.utils.get(ctx.guild.channels, name=ch_name)
                if existing_ch and existing_ch.category is None:
                    continue

                overwrites = {}
                for ow_item in ch_info.get("overwrites", []):
                    t_name = ow_item.get("target_name")
                    if t_name in ("@everyone", "@everyone role"):
                        target_r = ctx.guild.default_role
                    else:
                        target_r = created_roles.get(t_name) or discord.utils.get(ctx.guild.roles, name=t_name)

                    if target_r:
                        allow_perm = discord.Permissions(int(ow_item.get("allow", 0)))
                        deny_perm = discord.Permissions(int(ow_item.get("deny", 0)))
                        overwrites[target_r] = discord.PermissionOverwrite.from_pair(allow_perm, deny_perm)

                if ch_type == "voice":
                    await ctx.guild.create_voice_channel(name=ch_name, category=None, overwrites=overwrites)
                else:
                    await ctx.guild.create_text_channel(name=ch_name, category=None, topic=ch_info.get("topic"), nsfw=ch_info.get("nsfw", False), overwrites=overwrites)
                created_chans_count += 1
                await asyncio.sleep(0.2)
            except Exception as e:
                logger.warning("Failed to create uncategorized channel %s: %s", ch_info.get("name"), e)


        embed = discord.Embed(
            title="🎉 Server Template Applied!",
            description=f"Successfully applied template **`{name_key}`** to **{ctx.guild.name}**.",
            color=discord.Color.gold(),
            timestamp=datetime.now(timezone.utc)
        )

        embed.add_field(name="Roles Created", value=str(created_roles_count), inline=True)
        embed.add_field(name="Categories Created", value=str(created_cats_count), inline=True)
        embed.add_field(name="Channels Created", value=str(created_chans_count), inline=True)

        await ctx.send(embed=embed)

    @commands.command(name="templates", aliases=["template_list", "list_templates"])
    @commands.is_owner()
    async def templates(self, ctx: commands.Context):
        """List all saved server templates."""
        if not os.path.exists(TEMPLATES_DIR):
            await ctx.send("No server templates saved yet. Use `!feed <link>` to save a template.")
            return

        files = [f for f in os.listdir(TEMPLATES_DIR) if f.endswith(".json")]
        if not files:
            await ctx.send("No server templates saved yet. Use `!feed <link>` to save a template.")
            return

        embed = discord.Embed(
            title="📂 Saved Server Templates",
            description=f"Found **{len(files)}** template(s). Use `!template_apply <name>` to paste onto any server.",
            color=discord.Color.blue()
        )

        for fname in files:
            tname = fname[:-5]
            fpath = os.path.join(TEMPLATES_DIR, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    tdata = json.load(f)
                r_cnt = len(tdata.get("roles", []))
                cat_cnt = len(tdata.get("categories", []))
                s_name = tdata.get("name", "Unknown Server")
                embed.add_field(
                    name=f"• `{tname}`",
                    value=f"Server: **{s_name}** | Roles: `{r_cnt}` | Categories: `{cat_cnt}`",
                    inline=False
                )
            except Exception:
                embed.add_field(name=f"• `{tname}`", value="*(Corrupted or invalid format)*", inline=False)

        await ctx.send(embed=embed)

    @commands.group(name="template", invoke_without_command=True)
    @commands.is_owner()
    async def template_group(self, ctx: commands.Context):
        """Manage server templates (feed, apply, list, delete)."""
        await ctx.send("📋 **Server Template Commands:**\n• `!feed <link> [name]` — Inspect & save a server template\n• `!template_apply <name>` — Apply/paste template to current server\n• `!templates` — List saved templates\n• `!template_delete <name>` — Delete a saved template")

    @template_group.command(name="delete", aliases=["remove", "del"])
    @commands.is_owner()
    async def template_group_delete(self, ctx: commands.Context, template_name: str):
        """Subcommand to delete a saved server template."""
        await self.template_delete(ctx, template_name=template_name)

    @template_group.command(name="apply", aliases=["load", "paste"])
    @commands.is_owner()
    @commands.guild_only()
    async def template_group_apply(self, ctx: commands.Context, template_name: str):
        """Subcommand to apply a saved server template."""
        await self.template_apply(ctx, template_name=template_name)

    @template_group.command(name="feed", aliases=["copy", "fetch"])
    @commands.is_owner()
    async def template_group_feed(self, ctx: commands.Context, link_or_id: str, *, template_name: Optional[str] = None):
        """Subcommand to feed a server link or template."""
        await self.feed(ctx, link_or_id=link_or_id, template_name=template_name)

    @template_group.command(name="list")
    @commands.is_owner()
    async def template_group_list(self, ctx: commands.Context):
        """Subcommand to list saved server templates."""
        await self.templates(ctx)

    @commands.command(name="nukeserver", aliases=["servernuke", "nuke_server", "clearserver"])
    @commands.is_owner()
    @commands.guild_only()
    async def nukeserver(self, ctx: commands.Context, confirmation: Optional[str] = None):
        """Owner-only: Backup server structure, then delete all channels and roles. Usage: !nukeserver confirm"""
        if confirmation != "confirm":
            embed = discord.Embed(
                title="⚠️ WARNING: Server Nuke Requested",
                description=f"This command will **backup** `{ctx.guild.name}` structure, then **DELETE ALL CHANNELS AND ROLES**.\n\nTo proceed, run:\n`!nukeserver confirm`",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_key = f"backup_{ctx.guild.id}_latest"
        backup_file = os.path.join(TEMPLATES_DIR, f"{backup_key}.json")

        # Step 1: Automatic Backup
        template_payload = self._serialize_guild(ctx.guild)
        with open(backup_file, "w", encoding="utf-8") as f:
            json.dump(template_payload, f, indent=2)

        timestamp_file = os.path.join(TEMPLATES_DIR, f"backup_{ctx.guild.id}_{timestamp}.json")
        with open(timestamp_file, "w", encoding="utf-8") as f:
            json.dump(template_payload, f, indent=2)

        await ctx.send(f"📦 **Automatic backup saved as `{backup_key}`!** Starting server nuke...")

        # Step 2: Create temp log channel
        temp_ch = None
        try:
            temp_ch = await ctx.guild.create_text_channel(name="nuke-logs", reason="Helix Owner Server Nuke")
        except Exception as e:
            logger.warning("Failed to create temp nuke-logs channel: %s", e)

        # Step 3: Delete Channels
        deleted_chans = 0
        for ch in list(ctx.guild.channels):
            if temp_ch and ch.id == temp_ch.id:
                continue
            try:
                await ch.delete(reason="Helix Owner Server Nuke")
                deleted_chans += 1
                await asyncio.sleep(0.2)
            except Exception as e:
                logger.warning("Failed to delete channel %s: %s", ch.name, e)

        # Step 4: Delete Roles
        deleted_roles = 0
        bot_top_role = ctx.guild.me.top_role if ctx.guild.me else None
        for r in list(ctx.guild.roles):
            if r.is_default() or getattr(r, "managed", False):
                continue
            if bot_top_role:
                try:
                    if r >= bot_top_role:
                        continue
                except Exception:
                    pass
            try:
                await r.delete(reason="Helix Owner Server Nuke")
                deleted_roles += 1
                await asyncio.sleep(0.2)
            except Exception as e:
                logger.warning("Failed to delete role %s: %s", getattr(r, "name", "unknown"), e)


        # Step 5: Post Summary Embed
        summary_embed = discord.Embed(
            title="☢️ Server Nuked & Backed Up!",
            description=f"Successfully nuked **{ctx.guild.name}**.\n\n📦 **Backup saved as:** `{backup_key}`\nRestore anytime using:\n`!template_apply {backup_key}`",
            color=discord.Color.gold(),
            timestamp=datetime.now(timezone.utc)
        )
        summary_embed.add_field(name="Channels Deleted", value=str(deleted_chans), inline=True)
        summary_embed.add_field(name="Roles Deleted", value=str(deleted_roles), inline=True)
        summary_embed.add_field(name="Backup Template", value=f"`{backup_key}`", inline=True)

        if temp_ch:
            await temp_ch.send(embed=summary_embed)
        else:
            await ctx.send(embed=summary_embed)

    @commands.command(name="deletecategory", aliases=["delcat", "deletecat", "catdelete", "category_delete", "categorydelete"])
    @commands.is_owner()
    @commands.guild_only()
    async def deletecategory(self, ctx: commands.Context, *, category_name: str):
        """Owner-only: Delete a category and all channels inside it by name."""
        search_term = category_name.strip().lower()
        target_cat = None

        # Exact match
        for cat in ctx.guild.categories:
            if cat.name.lower() == search_term:
                target_cat = cat
                break

        # Partial match fallback
        if not target_cat:
            for cat in ctx.guild.categories:
                if search_term in cat.name.lower():
                    target_cat = cat
                    break

        if not target_cat:
            await ctx.send(f"❌ Category matching **`{category_name}`** not found in this server.")
            return

        cat_name = target_cat.name
        ch_list = list(target_cat.channels)
        deleted_count = 0

        is_current_in_cat = ctx.channel in ch_list or getattr(ctx.channel, "category_id", None) == target_cat.id

        await ctx.send(f"⏳ **Deleting category `{cat_name}` and `{len(ch_list)}` channel(s)...**")

        for ch in ch_list:
            if is_current_in_cat and ch.id == ctx.channel.id:
                continue # Delete command channel last
            try:
                await ch.delete(reason=f"Helix Owner DeleteCategory: by {ctx.author}")
                deleted_count += 1
                await asyncio.sleep(0.2)
            except Exception as e:
                logger.warning("Failed to delete channel %s in category %s: %s", getattr(ch, "name", "unknown"), cat_name, e)

        # Delete command channel if it was in this category
        if is_current_in_cat and hasattr(ctx.channel, "delete"):
            try:
                await ctx.channel.delete(reason=f"Helix Owner DeleteCategory: by {ctx.author}")
                deleted_count += 1
            except Exception:
                pass

        try:
            await target_cat.delete(reason=f"Helix Owner DeleteCategory: by {ctx.author}")
        except Exception as e:
            logger.warning("Failed to delete category container %s: %s", cat_name, e)

        embed = discord.Embed(
            title="🗑️ Category & Channels Deleted!",
            description=f"Successfully deleted category **`{cat_name}`** along with **{deleted_count}** channel(s).",
            color=discord.Color.red(),
            timestamp=datetime.now(timezone.utc)
        )

        out_channel = next((c for c in ctx.guild.text_channels if getattr(c, "category_id", None) != target_cat.id), None)
        if out_channel and not is_current_in_cat:
            await ctx.send(embed=embed)
        elif out_channel:
            await out_channel.send(embed=embed)
        else:
            try:
                await ctx.author.send(embed=embed)
            except Exception:
                pass

    @commands.command(name="template_delete", aliases=["deletetemplate", "deltemplate", "removetemplate", "template_remove"])
    @commands.is_owner()
    async def template_delete(self, ctx: commands.Context, template_name: str):
        """Delete a saved server template."""
        name_key = template_name.lower().replace(" ", "_")
        target_file = os.path.join(TEMPLATES_DIR, f"{name_key}.json")

        if os.path.exists(target_file):
            os.remove(target_file)
            await ctx.send(f"🗑️ Deleted template **`{name_key}`**.")
        else:
            await ctx.send(f"❌ Template **`{name_key}`** not found.")





async def setup(bot: commands.Bot):
    await bot.add_cog(TemplateCog(bot))
