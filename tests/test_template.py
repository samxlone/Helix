import sys
import os
import json
import importlib
from pathlib import Path
from types import SimpleNamespace as SN

repo_root = str(Path(__file__).resolve().parents[1])
if sys.path[0] != repo_root:
    sys.path.insert(0, repo_root)

import pytest
import discord
from discord.ext import commands

import cogs.template as tmpl_module
importlib.reload(tmpl_module)
TemplateCog = tmpl_module.TemplateCog


class FakeChannel:
    def __init__(self):
        self.sent = []

    async def send(self, content=None, embed=None):
        self.sent.append({"content": content, "embed": embed})


class FakeRole:
    def __init__(self, name, permissions=None, color=None, hoist=False, mentionable=False, id=1):
        self.name = name
        self.permissions = permissions
        self.color = color
        self.hoist = hoist
        self.mentionable = mentionable
        self.id = id

    async def edit(self, permissions=None, **kwargs):
        if permissions is not None:
            self.permissions = permissions

    def __hash__(self):
        return hash((self.name, self.id))

    def __eq__(self, other):
        return isinstance(other, FakeRole) and self.id == other.id and self.name == other.name



class FakeGuild:
    def __init__(self, id=1001, name="Target Guild"):
        self.id = id
        self.name = name
        self.default_role = FakeRole(name="@everyone", id=0)
        self.roles = []
        self.categories = []

    async def create_role(self, name, permissions=None, color=None, hoist=False, mentionable=False, reason=None):
        role = FakeRole(name=name, permissions=permissions, color=color, hoist=hoist, mentionable=mentionable, id=len(self.roles)+1)
        self.roles.append(role)
        return role


    async def create_category(self, name, overwrites=None, reason=None):
        cat = SN(name=name, channels=[], overwrites=overwrites)
        self.categories.append(cat)
        return cat


    async def create_text_channel(self, name, category=None, topic=None, nsfw=False, overwrites=None):
        ch = SN(name=name, category=category, topic=topic, nsfw=nsfw, overwrites=overwrites)
        if category:
            category.channels.append(ch)
        return ch

    async def create_voice_channel(self, name, category=None, overwrites=None):
        ch = SN(name=name, category=category, overwrites=overwrites)
        if category:
            category.channels.append(ch)
        return ch


@pytest.mark.asyncio
async def test_template_feed_and_apply(tmp_path, monkeypatch):
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default(), help_command=None)
    cog = TemplateCog(bot=bot)
    await bot.add_cog(cog)

    # Mock TEMPLATES_DIR to temp directory
    test_tmpl_dir = str(tmp_path / "templates")
    os.makedirs(test_tmpl_dir, exist_ok=True)
    monkeypatch.setattr(tmpl_module, "TEMPLATES_DIR", test_tmpl_dir)

    channel = FakeChannel()
    guild = FakeGuild()
    ctx = SN(guild=guild, channel=channel, send=channel.send, author=SN(id=1))

    # Fake template API response
    async def fake_fetch_template_data(code):
        return {
            "name": "Fed Server",
            "serialized_source_guild": {
                "name": "Source Community",
                "description": "Source test community",
                "roles": [
                    {"name": "@everyone", "permissions": 0},
                    {"name": "Moderator", "color": 255, "permissions": 8, "hoist": True, "mentionable": True}
                ],
                "channels": [
                    {"id": 1, "type": 4, "name": "GENERAL CATEGORY", "position": 0},
                    {"id": 2, "type": 0, "name": "welcome", "parent_id": 1, "topic": "Welcome channel"},
                    {"id": 3, "type": 2, "name": "Lounge VC", "parent_id": 1}
                ]
            }
        }

    monkeypatch.setattr(cog, "_fetch_template_data", fake_fetch_template_data)

    # 1. Run !feed
    await cog.feed(ctx, link_or_id="https://discord.new/samplecode", template_name="my_community")
    assert len(channel.sent) == 1
    assert "Server Template Fed & Saved" in channel.sent[0]["embed"].title

    # Verify JSON file was created
    expected_file = os.path.join(test_tmpl_dir, "my_community.json")
    assert os.path.exists(expected_file)

    # 2. Run !templates
    channel.sent.clear()
    await cog.templates(ctx)
    assert len(channel.sent) == 1
    assert "my_community" in channel.sent[0]["embed"].fields[0].name

    # 3. Run !template_apply
    channel.sent.clear()
    await cog.template_apply(ctx, template_name="my_community")
    assert len(channel.sent) == 2
    assert "Server Template Applied!" in channel.sent[1]["embed"].title
    assert len(guild.roles) == 1
    assert guild.roles[0].name == "Moderator"
    assert len(guild.categories) == 1
    assert guild.categories[0].name == "GENERAL CATEGORY"
    assert len(guild.categories[0].channels) == 2


@pytest.mark.asyncio
async def test_standard_invite_feed(tmp_path, monkeypatch):
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default(), help_command=None)
    cog = TemplateCog(bot=bot)
    await bot.add_cog(cog)

    test_tmpl_dir = str(tmp_path / "templates")
    os.makedirs(test_tmpl_dir, exist_ok=True)
    monkeypatch.setattr(tmpl_module, "TEMPLATES_DIR", test_tmpl_dir)

    channel = FakeChannel()
    guild = FakeGuild()
    ctx = SN(guild=guild, channel=channel, send=channel.send, author=SN(id=1))

    async def fake_fetch_invite_data(code):
        return {
            "guild": {"id": "1075480726151110656", "name": "The NXT"},
            "channel": {"name": "announcement"}
        }

    monkeypatch.setattr(cog, "_fetch_invite_data", fake_fetch_invite_data)

    # Run !feed nxtontop nxt
    await cog.feed(ctx, link_or_id="nxtontop", template_name="nxt")
    assert len(channel.sent) == 1
    assert "Server Template Fed & Saved" in channel.sent[0]["embed"].title


    # Apply template
    channel.sent.clear()
    await cog.template_apply(ctx, template_name="nxt")
    assert len(channel.sent) == 2
    assert "Server Template Applied!" in channel.sent[1]["embed"].title
    assert len(guild.roles) == 9
    assert len(guild.categories) == 4




@pytest.mark.asyncio
async def test_nukeserver_with_backup(tmp_path, monkeypatch):
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default(), help_command=None)
    cog = TemplateCog(bot=bot)
    await bot.add_cog(cog)

    test_tmpl_dir = str(tmp_path / "templates")
    os.makedirs(test_tmpl_dir, exist_ok=True)
    monkeypatch.setattr(tmpl_module, "TEMPLATES_DIR", test_tmpl_dir)

    channel = FakeChannel()
    guild = FakeGuild(id=777, name="Nuke Test Guild")
    
    async def fake_del(reason=None):
        pass

    guild.channels = [SN(id=1, name="general", category=None, overwrites={}, position=0, delete=fake_del)]
    guild.roles = [SN(id=1, name="Admin", is_default=lambda: False, managed=False, color=SN(value=0), permissions=SN(value=0), hoist=False, mentionable=False, delete=fake_del)]
    guild.me = SN(top_role=SN(id=99, name="BotRole"))



    ctx = SN(guild=guild, channel=channel, send=channel.send, author=SN(id=1))

    # Test nuke without confirm
    await cog.nukeserver(ctx)
    assert len(channel.sent) == 1
    assert "WARNING" in channel.sent[0]["embed"].title

    # Test nuke with confirm
    channel.sent.clear()
    await cog.nukeserver(ctx, confirmation="confirm")
    assert len(channel.sent) >= 1

    # Verify backup file was generated
    backup_file = os.path.join(test_tmpl_dir, f"backup_777_latest.json")
    assert os.path.exists(backup_file)


@pytest.mark.asyncio
async def test_role_fetching_and_permission_sanitization(tmp_path, monkeypatch):
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default(), help_command=None)
    cog = TemplateCog(bot=bot)
    await bot.add_cog(cog)

    test_tmpl_dir = str(tmp_path / "templates")
    os.makedirs(test_tmpl_dir, exist_ok=True)
    monkeypatch.setattr(tmpl_module, "TEMPLATES_DIR", test_tmpl_dir)

    channel = FakeChannel()
    guild = FakeGuild()
    ctx = SN(guild=guild, channel=channel, send=channel.send, author=SN(id=1))

    # Mock REST API request for roles
    async def fake_http_request(route, *args, **kwargs):
        if "roles" in route.path:
            return [
                {"name": "@everyone", "permissions": "0"},
                {"name": "👑 Owner", "color": 16711680, "hoist": True, "mentionable": True, "permissions": "8"},
                {"name": "🛡️ Admin", "color": 3447003, "hoist": True, "mentionable": True, "permissions": "8"},
                {"name": "🔨 Moderator", "color": 1752220, "hoist": True, "mentionable": True, "permissions": "8"}, # Given 8 by mistake in source
                {"name": "⭐ VIP", "color": 15844367, "hoist": True, "mentionable": False, "permissions": "8"}, # Given 8 by mistake in source
                {"name": "👥 Member", "color": 9807270, "hoist": False, "mentionable": False, "permissions": "8"},
            ]
        elif "channels" in route.path:
            return [{"id": 1, "type": 4, "name": "GENERAL", "position": 0}]
        elif "invites" in route.path:
            return {"guild": {"id": "99999", "name": "Live Server"}}
        return {}

    monkeypatch.setattr(bot.http, "request", fake_http_request)

    # Feed server link
    await cog.feed(ctx, link_or_id="sampleinvite", template_name="live_server")
    assert os.path.exists(os.path.join(test_tmpl_dir, "live_server.json"))

    # Apply template
    channel.sent.clear()
    await cog.template_apply(ctx, template_name="live_server")

    # Verify exact permissions preserved
    created_roles_by_name = {r.name: r for r in guild.roles}
    assert created_roles_by_name["👑 Owner"].permissions.administrator is True
    assert created_roles_by_name["🛡️ Admin"].permissions.administrator is True
    assert created_roles_by_name["🔨 Moderator"].permissions.administrator is True



@pytest.mark.asyncio
async def test_deletecategory_command(tmp_path, monkeypatch):
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default(), help_command=None)
    cog = TemplateCog(bot=bot)
    await bot.add_cog(cog)

    channel = FakeChannel()
    channel.id = 101
    channel.category_id = 999

    async def fake_del(reason=None):
        pass

    ch1 = SN(id=1, name="sub-chan-1", category_id=50, delete=fake_del)
    ch2 = SN(id=2, name="sub-chan-2", category_id=50, delete=fake_del)
    cat_obj = SN(id=50, name="COMMUNITY", channels=[ch1, ch2], delete=fake_del)

    guild = FakeGuild(id=888, name="Cat Test Guild")
    guild.categories = [cat_obj]
    guild.text_channels = [channel]

    ctx = SN(guild=guild, channel=channel, send=channel.send, author=SN(id=1))

    # Test category deletion by name
    await cog.deletecategory(ctx, category_name="COMMUNITY")
    assert len(channel.sent) == 2
    assert "Deleting category" in channel.sent[0]["content"]
    assert "Category & Channels Deleted!" in channel.sent[1]["embed"].title


@pytest.mark.asyncio
async def test_default_role_everyone_permission_apply(tmp_path, monkeypatch):
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default(), help_command=None)
    cog = TemplateCog(bot=bot)
    await bot.add_cog(cog)

    test_tmpl_dir = str(tmp_path / "templates")
    os.makedirs(test_tmpl_dir, exist_ok=True)
    monkeypatch.setattr(tmpl_module, "TEMPLATES_DIR", test_tmpl_dir)

    channel = FakeChannel()
    guild = FakeGuild()
    ctx = SN(guild=guild, channel=channel, send=channel.send, author=SN(id=1))

    # Fake template data with custom @everyone permissions
    async def fake_fetch_template_data(code):
        return {
            "name": "Custom Everyone Perms Server",
            "serialized_source_guild": {
                "name": "Perm Server",
                "description": "Test server with customized @everyone perms",
                "roles": [
                    {"name": "@everyone", "permissions": 1071698694721, "is_default": True},
                    {"name": "VIP", "color": 255, "permissions": 1024, "hoist": False, "mentionable": False}
                ],
                "channels": []
            }
        }

    monkeypatch.setattr(cog, "_fetch_template_data", fake_fetch_template_data)

    await cog.feed(ctx, link_or_id="https://discord.new/customperms", template_name="custom_perms")
    channel.sent.clear()
    await cog.template_apply(ctx, template_name="custom_perms")

    # Assert @everyone default role permissions were edited to match 1071698694721
    assert guild.default_role.permissions.value == 1071698694721

