"""PNG Image Generator for Statbot-style Server & User Activity Cards using Pillow."""
import io
import urllib.request
from typing import Dict, Any, List, Optional
from PIL import Image, ImageDraw, ImageFont


def _get_font(size: int, bold: bool = False):
    """Load a clean font (Arial/Segoe UI) or fallback to default."""
    try:
        font_name = "arialbd.ttf" if bold else "arial.ttf"
        return ImageFont.truetype(font_name, size)
    except Exception:
        try:
            font_name = "Segoe UI Bold.ttf" if bold else "Segoe UI.ttf"
            return ImageFont.truetype(font_name, size)
        except Exception:
            return ImageFont.load_default()


def _fetch_avatar_image(url: Optional[str], size: int = 70) -> Optional[Image.Image]:
    """Fetch avatar image and convert to round thumbnail."""
    if not url:
        return None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = resp.read()
        img = Image.open(io.BytesIO(data)).convert("RGBA")
        img = img.resize((size, size), Image.Resampling.LANCZOS)

        # Create round mask
        mask = Image.new("L", (size, size), 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((0, 0, size, size), fill=255)

        output = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        output.paste(img, (0, 0), mask)
        return output
    except Exception:
        return None


def generate_server_stat_card(guild_name: str, avatar_url: Optional[str], data: Dict[str, Any]) -> io.BytesIO:
    """Generate a sleek, dark-mode Statbot-style Server Analytics PNG image."""
    W, H = 820, 480
    bg_color = (24, 25, 28)
    card_bg = (38, 40, 45)
    accent_color = (88, 101, 242)
    text_white = (255, 255, 255)
    text_gray = (185, 187, 190)
    border_color = (55, 58, 64)

    img = Image.new("RGBA", (W, H), bg_color)
    draw = ImageDraw.Draw(img)

    # Fonts
    font_title = _get_font(22, bold=True)
    font_sub = _get_font(13)
    font_header = _get_font(14, bold=True)
    font_val = _get_font(24, bold=True)
    font_body = _get_font(13)

    # 1. Top Header Box
    draw.rounded_rectangle([20, 20, 800, 95], radius=10, fill=card_bg, outline=border_color, width=1)

    avatar = _fetch_avatar_image(avatar_url, size=56)
    if avatar:
        img.paste(avatar, (35, 30), avatar)
        text_x = 105
    else:
        text_x = 35

    draw.text((text_x, 32), guild_name[:35], font=font_title, fill=text_white)
    draw.text((text_x, 62), "Server Lookback: Last 7 Days • Timezone: IST", font=font_sub, fill=text_gray)

    # 2. Main Stat Cards Row (3 Cards)
    card_w = 246
    gap = 21
    y_start = 115
    y_height = 140

    # Card A: Lookback Total
    xA = 20
    draw.rounded_rectangle([xA, y_start, xA + card_w, y_start + y_height], radius=8, fill=card_bg, outline=border_color, width=1)
    draw.text((xA + 15, y_start + 15), "Server Lookback ⏱️", font=font_header, fill=accent_color)
    draw.text((xA + 15, y_start + 50), f"{data.get('msg_7d', '0')} msgs", font=font_val, fill=text_white)
    draw.text((xA + 15, y_start + 95), f"Voice: {data.get('vc_7d_hrs', '0')} hours", font=font_sub, fill=text_gray)

    # Card B: Messages Breakdown
    xB = xA + card_w + gap
    draw.rounded_rectangle([xB, y_start, xB + card_w, y_start + y_height], radius=8, fill=card_bg, outline=border_color, width=1)
    draw.text((xB + 15, y_start + 15), "Messages 💬", font=font_header, fill=accent_color)
    draw.text((xB + 15, y_start + 45), f"• 1d : {data.get('msg_1d', '0')} messages", font=font_body, fill=text_white)
    draw.text((xB + 15, y_start + 72), f"• 7d : {data.get('msg_7d', '0')} messages", font=font_body, fill=text_white)
    draw.text((xB + 15, y_start + 99), f"• 30d: {data.get('msg_30d', '0')} messages", font=font_body, fill=text_white)

    # Card C: Voice Activity Breakdown
    xC = xB + card_w + gap
    draw.rounded_rectangle([xC, y_start, xC + card_w, y_start + y_height], radius=8, fill=card_bg, outline=border_color, width=1)
    draw.text((xC + 15, y_start + 15), "Voice Activity 🎧", font=font_header, fill=accent_color)
    draw.text((xC + 15, y_start + 45), f"• 1d : {data.get('vc_1d_hrs', '0')} hours", font=font_body, fill=text_white)
    draw.text((xC + 15, y_start + 72), f"• 7d : {data.get('vc_7d_hrs', '0')} hours", font=font_body, fill=text_white)
    draw.text((xC + 15, y_start + 99), f"• 30d: {data.get('vc_30d_hrs', '0')} hours", font=font_body, fill=text_white)

    # 3. Bottom Leaderboards Row (2 Cards)
    bot_y = 275
    bot_w = 380
    bot_h = 175

    # Top Message Members
    draw.rounded_rectangle([20, bot_y, 20 + bot_w, bot_y + bot_h], radius=8, fill=card_bg, outline=border_color, width=1)
    draw.text((35, bot_y + 15), "Top Message Members 👤", font=font_header, fill=accent_color)

    top_m = data.get("top_members_fmt", [])
    for idx, (m_name, m_cnt) in enumerate(top_m[:4]):
        ly = bot_y + 48 + (idx * 28)
        draw.text((35, ly), f"{idx+1}. {m_name[:18]}", font=font_body, fill=text_white)
        draw.text((290, ly), f"{m_cnt} msgs", font=font_body, fill=text_gray)

    # Top Message Channels
    cx = 420
    draw.rounded_rectangle([cx, bot_y, cx + bot_w, bot_y + bot_h], radius=8, fill=card_bg, outline=border_color, width=1)
    draw.text((cx + 15, bot_y + 15), "Top Message Channels 💬", font=font_header, fill=accent_color)

    top_c = data.get("top_channels_fmt", [])
    for idx, (c_name, c_cnt) in enumerate(top_c[:4]):
        ly = bot_y + 48 + (idx * 28)
        draw.text((cx + 15, ly), f"{idx+1}. #{c_name[:18]}", font=font_body, fill=text_white)
        draw.text((cx + 270, ly), f"{c_cnt} msgs", font=font_body, fill=text_gray)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def generate_user_stat_card(display_name: str, username: str, avatar_url: Optional[str], created_str: str, joined_str: str, data: Dict[str, Any]) -> io.BytesIO:
    """Generate a sleek, dark-mode Statbot-style User Analytics PNG image."""
    W, H = 820, 460
    bg_color = (24, 25, 28)
    card_bg = (38, 40, 45)
    accent_color = (88, 101, 242)
    text_white = (255, 255, 255)
    text_gray = (185, 187, 190)
    border_color = (55, 58, 64)

    img = Image.new("RGBA", (W, H), bg_color)
    draw = ImageDraw.Draw(img)

    font_title = _get_font(20, bold=True)
    font_sub = _get_font(13)
    font_header = _get_font(14, bold=True)
    font_val = _get_font(20, bold=True)
    font_body = _get_font(13)

    # 1. Header Box
    draw.rounded_rectangle([20, 20, 800, 95], radius=10, fill=card_bg, outline=border_color, width=1)

    avatar = _fetch_avatar_image(avatar_url, size=56)
    if avatar:
        img.paste(avatar, (35, 30), avatar)
        tx = 105
    else:
        tx = 35

    draw.text((tx, 32), f"{display_name} (@{username})", font=font_title, fill=text_white)
    draw.text((tx, 62), f"Created On: {created_str} • Joined On: {joined_str}", font=font_sub, fill=text_gray)

    # 2. Main Stat Cards Row (3 Cards)
    card_w = 246
    gap = 21
    y_start = 115
    y_height = 140

    # Card A: Server Ranks
    xA = 20
    draw.rounded_rectangle([xA, y_start, xA + card_w, y_start + y_height], radius=8, fill=card_bg, outline=border_color, width=1)
    draw.text((xA + 15, y_start + 15), "Server Ranks 🏆", font=font_header, fill=accent_color)
    draw.text((xA + 15, y_start + 50), f"Message Rank : {data.get('msg_rank', 'N/A')}", font=font_body, fill=text_white)
    draw.text((xA + 15, y_start + 85), f"Voice Rank   : {data.get('vc_rank', 'N/A')}", font=font_body, fill=text_white)

    # Card B: User Messages
    xB = xA + card_w + gap
    draw.rounded_rectangle([xB, y_start, xB + card_w, y_start + y_height], radius=8, fill=card_bg, outline=border_color, width=1)
    draw.text((xB + 15, y_start + 15), "User Messages 💬", font=font_header, fill=accent_color)
    draw.text((xB + 15, y_start + 45), f"• 1d : {data.get('msg_1d', '0')} messages", font=font_body, fill=text_white)
    draw.text((xB + 15, y_start + 72), f"• 7d : {data.get('msg_7d', '0')} messages", font=font_body, fill=text_white)
    draw.text((xB + 15, y_start + 99), f"• 30d: {data.get('msg_30d', '0')} messages", font=font_body, fill=text_white)

    # Card C: User Voice Activity
    xC = xB + card_w + gap
    draw.rounded_rectangle([xC, y_start, xC + card_w, y_start + y_height], radius=8, fill=card_bg, outline=border_color, width=1)
    draw.text((xC + 15, y_start + 15), "Voice Activity 🎧", font=font_header, fill=accent_color)
    draw.text((xC + 15, y_start + 45), f"• 1d : {data.get('vc_1d_hrs', '0')} hours", font=font_body, fill=text_white)
    draw.text((xC + 15, y_start + 72), f"• 7d : {data.get('vc_7d_hrs', '0')} hours", font=font_body, fill=text_white)
    draw.text((xC + 15, y_start + 99), f"• 30d: {data.get('vc_30d_hrs', '0')} hours", font=font_body, fill=text_white)

    # 3. Bottom Top Channels Box
    bot_y = 275
    draw.rounded_rectangle([20, bot_y, 800, bot_y + 160], radius=8, fill=card_bg, outline=border_color, width=1)
    draw.text((35, bot_y + 15), "Top Channels & Activity 📊", font=font_header, fill=accent_color)

    top_ch = data.get("top_channels_fmt", [])
    for idx, (ch_name, c_cnt) in enumerate(top_ch[:3]):
        ly = bot_y + 48 + (idx * 32)
        draw.text((35, ly), f"{idx+1}. #{ch_name[:30]}", font=font_body, fill=text_white)
        draw.text((650, ly), f"{c_cnt} msgs", font=font_body, fill=text_gray)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf
