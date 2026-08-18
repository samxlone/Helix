"""PNG Image Generator for Discord Quotes with Left-Avatar Fade and Luxury Typography."""
import io
import urllib.request
from typing import Optional
from PIL import Image, ImageDraw, ImageFont, ImageOps


def _get_font(size: int, font_name: str = "default"):
    """Load a clean font or fallback to default."""
    try:
        if font_name == "serif":
            return ImageFont.truetype("georgia.ttf", size)
        elif font_name == "mono":
            return ImageFont.truetype("consola.ttf", size)
        elif font_name == "impact":
            return ImageFont.truetype("impact.ttf", size)
        else:
            return ImageFont.truetype("arialbd.ttf", size)
    except Exception:
        try:
            return ImageFont.truetype("arial.ttf", size)
        except Exception:
            return ImageFont.load_default()


def _fetch_avatar_image(url: Optional[str], size: int = 400) -> Image.Image:
    """Fetch avatar image or return fallback default dark avatar."""
    if url:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=4) as resp:
                data = resp.read()
            img = Image.open(io.BytesIO(data)).convert("RGBA")
            return img.resize((size, size), Image.Resampling.LANCZOS)
        except Exception:
            pass

    # Fallback solid avatar image
    fallback = Image.new("RGBA", (size, size), (40, 44, 52, 255))
    draw = ImageDraw.Draw(fallback)
    draw.ellipse([size // 4, size // 4, 3 * size // 4, 3 * size // 4], fill=(88, 101, 242, 255))
    return fallback


def generate_quote_card(
    author_name: str,
    author_tag: str,
    avatar_url: Optional[str],
    text: str,
    theme: str = "dark",
    font_style: str = "default"
) -> io.BytesIO:
    """Generate a high-res Discord Quote Image Card with left avatar gradient fade."""
    W, H = 800, 400

    # Theme Palettes
    themes = {
        "dark": ((18, 18, 20), (255, 255, 255), (180, 180, 185)),
        "midnight": ((11, 14, 20), (240, 246, 252), (139, 148, 158)),
        "purple": ((26, 11, 46), (255, 255, 255), (200, 180, 230)),
        "crimson": ((42, 8, 12), (255, 240, 242), (230, 160, 170)),
    }

    bg_color, text_white, text_sub = themes.get(theme.lower(), themes["dark"])

    # Base Canvas
    img = Image.new("RGBA", (W, H), bg_color)

    # 1. Fetch & Paste Avatar on Left
    av_size = 400
    avatar = _fetch_avatar_image(avatar_url, size=av_size)

    # Apply Right Gradient Fade to Avatar
    mask = Image.new("L", (av_size, av_size), 255)
    mask_draw = ImageDraw.Draw(mask)
    fade_start = 140
    for x in range(fade_start, av_size):
        alpha = int(255 * (1 - (x - fade_start) / (av_size - fade_start)))
        mask_draw.line([(x, 0), (x, av_size)], fill=alpha)

    # Composite Avatar onto Canvas
    img.paste(avatar, (0, 0), mask)

    # 2. Setup Typography
    font_quote = _get_font(28, font_style)
    font_attr = _get_font(18, font_style)
    font_handle = _get_font(13, font_style)

    draw = ImageDraw.Draw(img)

    # Clean text input
    quote_text = text.strip() if text.strip() else "[Empty Quote]"

    # Wrap Quote Text (fitting in x=360 to x=760 -> max width 400px)
    words = quote_text.split()
    lines = []
    curr_line = []
    max_line_width = 390

    for w in words:
        curr_line.append(w)
        test_str = " ".join(curr_line)
        bbox = font_quote.getbbox(test_str)
        if (bbox[2] - bbox[0]) > max_line_width:
            curr_line.pop()
            if curr_line:
                lines.append(" ".join(curr_line))
            curr_line = [w]
    if curr_line:
        lines.append(" ".join(curr_line))

    # Cap lines at 6
    if len(lines) > 6:
        lines = lines[:6]
        lines[-1] += "..."

    # Calculate vertical position for vertically centered quote
    line_height = 36
    total_text_h = len(lines) * line_height
    y_start = max(50, (H - total_text_h - 70) // 2)

    # Draw Quote Lines Right-Aligned
    y_curr = y_start
    for line in lines:
        bbox = font_quote.getbbox(line)
        line_w = bbox[2] - bbox[0]
        x_pos = 760 - line_w
        draw.text((x_pos, y_curr), line, font=font_quote, fill=text_white)
        y_curr += line_height

    # Draw Author Attribution at Bottom Right
    attr_str = f"— {author_name}"
    bbox_attr = font_attr.getbbox(attr_str)
    attr_w = bbox_attr[2] - bbox_attr[0]
    draw.text((760 - attr_w, H - 75), attr_str, font=font_attr, fill=text_white)

    handle_str = f"@{author_tag}"
    bbox_handle = font_handle.getbbox(handle_str)
    handle_w = bbox_handle[2] - bbox_handle[0]
    draw.text((760 - handle_w, H - 48), handle_str, font=font_handle, fill=text_sub)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf
