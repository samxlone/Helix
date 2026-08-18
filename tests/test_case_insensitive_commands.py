import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
import discord
from main import bot, on_message
from utils.cog_loader import load_cogs


@pytest.mark.asyncio
async def test_case_insensitive_command_resolution():
    """Verify that commands resolve properly regardless of uppercase/lowercase casing."""
    assert bot.case_insensitive is True
    await load_cogs(bot)

    # Test resolving commands with different casing
    cmd_lower = bot.get_command("help")
    cmd_upper = bot.get_command("HELP")
    cmd_title = bot.get_command("Help")
    cmd_mixed = bot.get_command("hElP")

    assert cmd_lower is not None
    assert cmd_upper == cmd_lower
    assert cmd_title == cmd_lower
    assert cmd_mixed == cmd_lower


@pytest.mark.asyncio
async def test_case_insensitive_alias_resolution():
    """Verify aliases resolve properly in uppercase and lowercase."""
    assert bot.case_insensitive is True
    await load_cogs(bot)

    cmd_lower = bot.get_command("bal")
    cmd_upper = bot.get_command("BAL")
    cmd_mixed = bot.get_command("bAl")

    assert cmd_lower is not None
    assert cmd_upper == cmd_lower
    assert cmd_mixed == cmd_lower


@pytest.mark.asyncio
async def test_prefixless_capitalization_normalization(monkeypatch):
    """Verify that prefixless messages with capitalized commands (e.g. Join, JOIN, Play song) are normalized properly."""
    await load_cogs(bot)

    mock_msg = MagicMock(spec=discord.Message)
    mock_msg.author = MagicMock()
    mock_msg.author.bot = False
    mock_msg.author.id = 123456789
    mock_msg.guild = MagicMock()
    mock_msg.guild.id = 987654321
    mock_msg.channel = MagicMock()
    mock_msg.channel.id = 111222333
    mock_msg.content = "Join"
    mock_msg.mentions = []

    # Mock process_commands to capture the modified message content
    processed_content = None

    async def mock_process_commands(msg):
        nonlocal processed_content
        processed_content = msg.content

    monkeypatch.setattr(bot, "process_commands", mock_process_commands)
    monkeypatch.setenv("OWNER_ID", "123456789")  # Owner has prefixless permissions

    await on_message(mock_msg)

    assert processed_content == "!join"
