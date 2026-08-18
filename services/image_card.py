"""PNG Image Generator for Luxury Level Rank Cards, Economy Profile Cards, and Welcome Cards using Pillow."""
import io
import urllib.request
from typing import Optional, Tuple
from PIL import Image, ImageDraw, ImageFont, ImageFilter


def _get_font(size: int, bold: bool = False):
    """Load a clean font or fallback to default."""
    font_candidates = [
        "Segoe UI Bold.ttf" if bold else "Segoe UI.ttf",
        "arialbd.ttf" if bold else "arial.ttf",
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
    ]
    for font_name in font_candidates:
        try:
            return ImageFont.truetype(font_name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _fetch_round_avatar(url: Optional[str], size: int = 90) -> Optional[Image.Image]:
    """Fetch avatar image and convert to round thumbnail with antialiased edges."""
    if not url:
        return None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = resp.read()
        img = Image.open(io.BytesIO(data)).convert("RGBA")
        img = img.resize((size, size), Image.Resampling.LANCZOS)

        # High-res supersampled mask for ultra-smooth circular antialiasing
        scale = 4
        big_size = size * scale
        mask = Image.new("L", (big_size, big_size), 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((0, 0, big_size, big_size), fill=255)
        mask = mask.resize((size, size), Image.Resampling.LANCZOS)

        output = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        output.paste(img, (0, 0), mask)
        return output
    except Exception:
        return None


def generate_rank_card(
    display_name: str,
    username: str,
    avatar_url: Optional[str],
    level: int,
    current_xp: int,
    next_xp: int,
    rank_num: str or int
) -> io.BytesIO:
    """Generate a luxury Crimson-Rose & Obsidian glassmorphism Level Rank Card."""
    W, H = 860, 260
    bg_color = (10, 14, 23)        # Obsidian Midnight
    card_bg = (18, 24, 38)         # Glassmorphism Card
    border_color = (35, 45, 68)    # Subtle Slate Border
    crimson_primary = (225, 29, 72) # #E11D48 (Signature Crimson)
    rose_light = (251, 113, 133)   # #FB7185 (Rose Pink Accent)
    text_white = (248, 250, 252)
    text_gray = (148, 163, 184)
    bar_bg = (28, 36, 54)

    img = Image.new("RGBA", (W, H), bg_color)
    draw = ImageDraw.Draw(img)

    font_title = _get_font(24, bold=True)
    font_sub = _get_font(14)
    font_badge_num = _get_font(22, bold=True)
    font_badge_lbl = _get_font(11, bold=True)
    font_xp = _get_font(13, bold=True)

    # 1. Outer Container Card with Smooth Border
    draw.rounded_rectangle([18, 18, W - 18, H - 18], radius=18, fill=card_bg, outline=border_color, width=1)

    # 2. Luxury Left Accent Bar
    draw.rounded_rectangle([18, 18, 28, H - 18], radius=6, fill=crimson_primary)

    # 3. Avatar Rendering with Crimson Glowing Ring
    av_size = 96
    av_x, av_y = 52, 50
    avatar = _fetch_round_avatar(avatar_url, size=av_size)

    # Glow Ring
    ring_pad = 4
    draw.ellipse(
        [av_x - ring_pad, av_y - ring_pad, av_x + av_size + ring_pad, av_y + av_size + ring_pad],
        outline=crimson_primary,
        width=3
    )

    if avatar:
        img.paste(avatar, (av_x, av_y), avatar)
    else:
        draw.ellipse([av_x, av_y, av_x + av_size, av_y + av_size], fill=(30, 41, 59))

    tx = 175

    # 4. User Information Header
    draw.text((tx, 54), display_name[:20], font=font_title, fill=text_white)
    draw.text((tx, 88), f"@{username[:22]}", font=font_sub, fill=text_gray)

    # 5. Top Right Stats (Rank & Level Badges)
    # Level Badge
    lvl_x = W - 145
    draw.text((lvl_x, 50), "LEVEL", font=font_badge_lbl, fill=rose_light)
    draw.text((lvl_x, 66), f"{level}", font=font_badge_num, fill=text_white)

    # Rank Badge
    rnk_x = lvl_x - 110
    draw.text((rnk_x, 50), "RANK", font=font_badge_lbl, fill=text_gray)
    draw.text((rnk_x, 66), f"#{rank_num}", font=font_badge_num, fill=crimson_primary)

    # 6. XP Progress Bar
    bar_x = tx
    bar_y = 152
    bar_w = W - tx - 52
    bar_h = 22

    # Calculate fill ratio
    pct = max(0.0, min(1.0, current_xp / max(1, next_xp)))
    fill_w = int(bar_w * pct)

    # Bar Background
    draw.rounded_rectangle([bar_x, bar_y, bar_x + bar_w, bar_y + bar_h], radius=11, fill=bar_bg)

    # Filled Gradient-look Progress
    if fill_w > 10:
        draw.rounded_rectangle([bar_x, bar_y, bar_x + fill_w, bar_y + bar_h], radius=11, fill=crimson_primary)

    # XP Text & Percentage Display
    xp_text = f"{current_xp:,} / {next_xp:,} XP"
    pct_text = f"{int(pct * 100)}%"
    draw.text((bar_x + 4, bar_y + 30), xp_text, font=font_xp, fill=text_gray)

    # Right-aligned Percentage
    try:
        pct_bbox = font_xp.getbbox(pct_text)
        pct_w = pct_bbox[2] - pct_bbox[0]
    except Exception:
        pct_w = 40
    draw.text((bar_x + bar_w - pct_w - 4, bar_y + 30), pct_text, font=font_xp, fill=rose_light)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def generate_profile_card(
    display_name: str,
    username: str,
    avatar_url: Optional[str],
    wallet: int,
    bank: int,
    level: int,
    xp: int
) -> io.BytesIO:
    """Generate a VIP Luxury Banking Profile PNG Card."""
    W, H = 860, 340
    bg_color = (10, 14, 23)
    card_bg = (18, 24, 38)
    box_bg = (25, 33, 50)
    border_color = (35, 45, 68)
    crimson_primary = (225, 29, 72)
    emerald_accent = (34, 197, 94)
    amber_accent = (245, 158, 11)
    text_white = (248, 250, 252)
    text_gray = (148, 163, 184)

    img = Image.new("RGBA", (W, H), bg_color)
    draw = ImageDraw.Draw(img)

    font_title = _get_font(24, bold=True)
    font_sub = _get_font(13)
    font_label = _get_font(12, bold=True)
    font_val = _get_font(20, bold=True)

    # 1. Outer Container
    draw.rounded_rectangle([18, 18, W - 18, H - 18], radius=18, fill=card_bg, outline=border_color, width=1)

    # Top Crimson Strip
    draw.rounded_rectangle([18, 18, W - 18, 26], radius=4, fill=crimson_primary)

    # 2. Avatar
    av_size = 84
    avatar = _fetch_round_avatar(avatar_url, size=av_size)
    av_x, av_y = 48, 48
    draw.ellipse([av_x - 3, av_y - 3, av_x + av_size + 3, av_y + av_size + 3], outline=crimson_primary, width=2)
    if avatar:
        img.paste(avatar, (av_x, av_y), avatar)
    else:
        draw.ellipse([av_x, av_y, av_x + av_size, av_y + av_size], fill=(30, 41, 59))

    tx = 155

    # 3. User Header
    draw.text((tx, 54), display_name[:22], font=font_title, fill=text_white)
    draw.text((tx, 88), f"VIP Economy Profile • @{username[:24]}", font=font_sub, fill=text_gray)

    # 4. Stat Boxes Row 1 (Wallet & Bank)
    y_box1 = 155
    box_w = 360
    box_h = 68

    # Wallet Box
    draw.rounded_rectangle([48, y_box1, 48 + box_w, y_box1 + box_h], radius=10, fill=box_bg, outline=border_color, width=1)
    draw.text((64, y_box1 + 12), "WALLET BALANCE 🪙", font=font_label, fill=text_gray)
    draw.text((64, y_box1 + 34), f"${wallet:,}", font=font_val, fill=emerald_accent)

    # Bank Box
    draw.rounded_rectangle([438, y_box1, 438 + box_w, y_box1 + box_h], radius=10, fill=box_bg, outline=border_color, width=1)
    draw.text((454, y_box1 + 12), "BANK VAULT 🏦", font=font_label, fill=text_gray)
    draw.text((454, y_box1 + 34), f"${bank:,}", font=font_val, fill=amber_accent)

    # 5. Stat Boxes Row 2 (Net Worth & Activity)
    y_box2 = 236
    net_worth = wallet + bank

    # Net Worth Box
    draw.rounded_rectangle([48, y_box2, 48 + box_w, y_box2 + box_h], radius=10, fill=box_bg, outline=border_color, width=1)
    draw.text((64, y_box2 + 12), "TOTAL NET WORTH 💎", font=font_label, fill=text_gray)
    draw.text((64, y_box2 + 34), f"${net_worth:,}", font=font_val, fill=text_white)

    # Level & Activity Box
    draw.rounded_rectangle([438, y_box2, 438 + box_w, y_box2 + box_h], radius=10, fill=box_bg, outline=border_color, width=1)
    draw.text((454, y_box2 + 12), "LEVEL & EXPERIENCE ⚡", font=font_label, fill=text_gray)
    draw.text((454, y_box2 + 34), f"Level {level} • {xp:,} XP", font=font_val, fill=text_white)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def generate_welcome_card(
    display_name: str,
    username: str,
    avatar_url: Optional[str],
    server_name: str,
    member_count: int
) -> io.BytesIO:
    """Generate a luxury Obsidian & Crimson Welcome Banner Card."""
    W, H = 880, 280
    bg_color = (10, 14, 23)        # Obsidian Midnight
    card_bg = (18, 24, 38)         # Slate Glass Container
    border_color = (35, 45, 68)    # Border Slate
    crimson_primary = (225, 29, 72) # #E11D48
    rose_light = (251, 113, 133)   # #FB7185
    text_white = (248, 250, 252)
    text_gray = (148, 163, 184)
    badge_bg = (28, 36, 54)

    img = Image.new("RGBA", (W, H), bg_color)
    draw = ImageDraw.Draw(img)

    font_welcome = _get_font(28, bold=True)
    font_server = _get_font(18, bold=True)
    font_user = _get_font(20, bold=True)
    font_count = _get_font(14, bold=True)
    font_sub = _get_font(13)

    # 1. Outer Container Card
    draw.rounded_rectangle([18, 18, W - 18, H - 18], radius=20, fill=card_bg, outline=border_color, width=1)

    # Glowing Crimson Gradient Left Accent Bar
    draw.rounded_rectangle([18, 18, 30, H - 18], radius=6, fill=crimson_primary)

    # 2. Avatar with Antialiased Crimson Ring
    av_size = 110
    avatar = _fetch_round_avatar(avatar_url, size=av_size)
    av_x, av_y = 55, 65

    # Glowing ring
    draw.ellipse([av_x - 4, av_y - 4, av_x + av_size + 4, av_y + av_size + 4], outline=crimson_primary, width=3)
    if avatar:
        img.paste(avatar, (av_x, av_y), avatar)
    else:
        draw.ellipse([av_x, av_y, av_x + av_size, av_y + av_size], fill=(30, 41, 59))

    # 3. Content Text
    tx = 195
    # Welcome Title
    draw.text((tx, 55), "WELCOME TO THE SERVER", font=font_welcome, fill=crimson_primary)
    
    # Server Name
    clean_server = server_name[:32]
    draw.text((tx, 96), f"🏰 {clean_server}", font=font_server, fill=text_white)

    # Member User Info
    draw.text((tx, 134), f"✨ {display_name[:26]} (@{username[:22]})", font=font_user, fill=text_gray)

    # 4. Member Count Badge Box
    badge_w = 280
    badge_h = 42
    bx, by = tx, 178
    draw.rounded_rectangle([bx, by, bx + badge_w, by + badge_h], radius=10, fill=badge_bg, outline=border_color, width=1)
    draw.text((bx + 16, by + 12), f"👥 You are member #{member_count:,}", font=font_count, fill=rose_light)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf
