"""Helper utilities for standardized, aesthetic Discord embeds and luxury theme palettes."""
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import discord
from discord.ext import commands

# Luxury Crimson Theme Palette
HELIX_COLOR = discord.Color.from_rgb(225, 29, 72)     # #E11D48 (Signature Crimson Luxury)
HELIX_DARK = discord.Color.from_rgb(15, 23, 42)       # #0F172A (Deep Slate Obsidian)
HELIX_SUCCESS = discord.Color.from_rgb(34, 197, 94)   # #22C55E (Emerald Mint)
HELIX_WARNING = discord.Color.from_rgb(245, 158, 11)  # #F59E0B (Warm Amber)
HELIX_DANGER = discord.Color.from_rgb(239, 68, 68)    # #EF4444 (Rose Red)
HELIX_INFO = discord.Color.from_rgb(99, 102, 241)     # #6366F1 (Electric Indigo)
HELIX_MUTED = discord.Color.from_rgb(100, 116, 139)   # #64748B (Slate Muted)


def set_owner_footer(embed: discord.Embed, bot: Optional[commands.Bot] = None, extra_text: str = "") -> discord.Embed:
    """Attach a sleek, minimal branding footer with owner or bot avatar icon."""
    owner = getattr(bot, "owner_user", None) if bot else None
    bot_user = getattr(bot, "user", None) if bot else None
    
    icon_url = None
    if owner and hasattr(owner, "display_avatar") and owner.display_avatar:
        icon_url = owner.display_avatar.url
    elif bot_user and hasattr(bot_user, "display_avatar") and bot_user.display_avatar:
        icon_url = bot_user.display_avatar.url

    footer_text = "Helix Systems"
    if extra_text:
        footer_text = f"{extra_text} • Helix"

    embed.set_footer(text=footer_text, icon_url=icon_url)
    return embed


def helix_embed(
    title: Optional[str] = None,
    description: Optional[str] = None,
    color: Optional[discord.Color] = None,
    bot: Optional[commands.Bot] = None,
    footer_text: str = "",
    thumbnail_url: Optional[str] = None,
    image_url: Optional[str] = None,
    author_name: Optional[str] = None,
    author_icon: Optional[str] = None
) -> discord.Embed:
    """Build a clean, uncluttered, luxury-styled Discord Embed."""
    chosen_color = color or HELIX_COLOR
    embed = discord.Embed(title=title, description=description, color=chosen_color)
    
    if author_name:
        embed.set_author(name=author_name, icon_url=author_icon)
    if thumbnail_url:
        embed.set_thumbnail(url=thumbnail_url)
    if image_url:
        embed.set_image(url=image_url)
        
    set_owner_footer(embed, bot, extra_text=footer_text)
    return embed
