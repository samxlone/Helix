import io
import html
import logging
from datetime import datetime, timezone
from typing import Optional, List
import discord

logger = logging.getLogger(__name__)

async def generate_html_transcript(
    channel: discord.TextChannel,
    category_name: str = "Support",
    creator_name: str = "Unknown",
    claimed_name: str = "Unclaimed",
    created_time: Optional[str] = None
) -> io.BytesIO:
    """Generate a modern self-contained HTML transcript of the ticket channel."""
    messages_html = []
    total_count = 0

    try:
        async for msg in channel.history(limit=1000, oldest_first=True):
            total_count += 1
            author_name = html.escape(msg.author.display_name if hasattr(msg.author, "display_name") else str(msg.author))
            time_str = msg.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
            avatar_url = msg.author.display_avatar.url if hasattr(msg.author, "display_avatar") else "https://cdn.discordapp.com/embed/avatars/0.png"
            bot_tag = '<span class="bot-badge">APP</span>' if msg.author.bot else ''
            
            content_escaped = html.escape(msg.content) if msg.content else ""

            embeds_html = []
            for emb in msg.embeds:
                emb_title = f'<div class="embed-title">{html.escape(emb.title)}</div>' if emb.title else ''
                emb_desc = f'<div class="embed-desc">{html.escape(emb.description)}</div>' if emb.description else ''
                if emb_title or emb_desc:
                    embeds_html.append(f'<div class="embed">{emb_title}{emb_desc}</div>')

            attach_html = []
            for att in msg.attachments:
                attach_html.append(f'<a class="attachment" href="{att.url}" target="_blank">📎 {html.escape(att.filename)}</a>')

            body_items = []
            if content_escaped:
                body_items.append(f'<div class="msg-content">{content_escaped}</div>')
            if embeds_html:
                body_items.extend(embeds_html)
            if attach_html:
                body_items.extend(attach_html)

            if not body_items:
                body_items.append('<div class="msg-content" style="color: #949ba4; font-style: italic;">[Empty message]</div>')

            msg_block = (
                '<div class="message-group">'
                f'<img class="avatar" src="{avatar_url}" alt="{author_name}">'
                '<div class="msg-body">'
                '<div class="msg-header">'
                f'<span class="author-name">{author_name}</span>'
                f'{bot_tag}'
                f'<span class="timestamp">{time_str}</span>'
                '</div>'
                f'{"".join(body_items)}'
                '</div>'
                '</div>'
            )
            messages_html.append(msg_block)
    except Exception as e:
        logger.exception("Failed building HTML transcript messages: %s", e)
        messages_html.append(f'<div style="color: red; padding: 10px;">Error collecting messages: {html.escape(str(e))}</div>')

    c_name = html.escape(channel.name)
    s_name = html.escape(channel.guild.name) if channel.guild else "Discord Server"
    cat_name = html.escape(category_name)
    cr_name = html.escape(creator_name)
    cl_name = html.escape(claimed_name)
    cr_time = html.escape(created_time or "N/A")
    exp_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    msgs_rendered = "".join(messages_html)

    html_out = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Transcript - #{c_name}</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: 'Segoe UI', 'Helvetica Neue', Helvetica, Arial, sans-serif;
            background-color: #1e1f22;
            color: #dbdee1;
            line-height: 1.4;
            padding: 24px;
        }}
        .container {{
            max-width: 900px;
            margin: 0 auto;
            background: #2b2d31;
            border-radius: 12px;
            border: 1px solid #383a40;
            overflow: hidden;
            box-shadow: 0 8px 24px rgba(0,0,0,0.4);
        }}
        .header {{
            background: #111214;
            padding: 24px;
            border-bottom: 2px solid #5865f2;
        }}
        .header-title {{
            font-size: 22px;
            font-weight: 700;
            color: #ffffff;
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        .header-meta {{
            margin-top: 12px;
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 10px;
            font-size: 13px;
            color: #949ba4;
        }}
        .meta-item strong {{
            color: #f2f3f5;
        }}
        .messages {{
            padding: 20px 24px;
            display: flex;
            flex-direction: column;
            gap: 16px;
        }}
        .message-group {{
            display: flex;
            gap: 16px;
            padding: 4px 0;
        }}
        .avatar {{
            width: 42px;
            height: 42px;
            border-radius: 50%;
            background: #5865f2;
            flex-shrink: 0;
            object-fit: cover;
        }}
        .msg-body {{
            flex: 1;
            min-width: 0;
        }}
        .msg-header {{
            display: flex;
            align-items: baseline;
            gap: 8px;
            margin-bottom: 4px;
        }}
        .author-name {{
            font-size: 15px;
            font-weight: 600;
            color: #ffffff;
        }}
        .bot-badge {{
            background: #5865f2;
            color: #ffffff;
            font-size: 10px;
            font-weight: 700;
            padding: 2px 4px;
            border-radius: 4px;
            text-transform: uppercase;
        }}
        .timestamp {{
            font-size: 11px;
            color: #949ba4;
        }}
        .msg-content {{
            font-size: 14px;
            color: #dbdee1;
            white-space: pre-wrap;
            word-break: break-word;
        }}
        .embed {{
            margin-top: 8px;
            border-left: 4px solid #5865f2;
            background: #232428;
            padding: 12px 16px;
            border-radius: 4px 8px 8px 4px;
            max-width: 520px;
        }}
        .embed-title {{
            font-size: 14px;
            font-weight: 700;
            color: #ffffff;
            margin-bottom: 6px;
        }}
        .embed-desc {{
            font-size: 13px;
            color: #dbdee1;
        }}
        .attachment {{
            margin-top: 8px;
            display: inline-block;
            background: #1e1f22;
            padding: 8px 12px;
            border-radius: 6px;
            border: 1px solid #383a40;
            font-size: 13px;
            color: #5865f2;
            text-decoration: none;
        }}
        .attachment:hover {{
            text-decoration: underline;
        }}
        .footer {{
            background: #111214;
            padding: 16px 24px;
            font-size: 12px;
            color: #949ba4;
            text-align: center;
            border-top: 1px solid #383a40;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="header-title">🎫 #{c_name}</div>
            <div class="header-meta">
                <div class="meta-item">Server: <strong>{s_name}</strong></div>
                <div class="meta-item">Category: <strong>{cat_name}</strong></div>
                <div class="meta-item">Creator: <strong>{cr_name}</strong></div>
                <div class="meta-item">Claimed By: <strong>{cl_name}</strong></div>
                <div class="meta-item">Created: <strong>{cr_time}</strong></div>
                <div class="meta-item">Exported: <strong>{exp_time}</strong></div>
            </div>
        </div>
        <div class="messages">
            {msgs_rendered}
        </div>
        <div class="footer">
            Helix Ticket Engine • Total Messages: {total_count} • Generated at {exp_time}
        </div>
    </div>
</body>
</html>
"""
    buf = io.BytesIO(html_out.encode("utf-8"))
    buf.seek(0)
    return buf
