# ⚡ Helix — High-Performance Modular Discord Bot

![Python Version](https://img.shields.io/badge/python-3.14%2B-blue.svg)
![Discord.py Version](https://img.shields.io/badge/discord.py-2.4%2B-5865F2.svg)
![Tests](https://img.shields.io/badge/pytest-54%20passed-success.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

**Helix** is a state-of-the-art, feature-rich multi-purpose Discord bot built with Python and `discord.py`. Designed for high performance, visual excellence, and deep customization, Helix combines advanced music playback, OpenAI & Gemini AI chatbot integration, Gemini Imagen image generation, a full economy system, chat leveling, interactive moderation history, asset stealing, and server management tools into a single modular architecture.

---

## 🌟 Key Highlights & Features

- 🎵 **Advanced Audio & Music System**: High-quality voice playback, queue management, voice channel TTS with multi-language & Hinglish auto-detection, autoplay recommendations, and dynamic volume controls.
- 🤖 **AI Chatbot & Image Generation**: Multi-provider AI text engine (OpenAI GPT-4o-mini & Google Gemini 1.5 Flash), Google Gemini Imagen AI image generation (`!imagine`), sliding conversation memory buffer, dedicated AI channel scoping (`!setaichannel #ai-chat`), and Bot Owner exemptions.
- 💳 **Arcane-Style Leveling & Chat XP**: XP earning engine, level-up role rewards, custom dedicated level notification channels (`!setlevelchannel`), multi-target XP toggles (`!ignorexp` for users, channels, or server), Arcane-style rank cards (`!rank`), and interactive level leaderboards (`!levels`).
- 💵 **Rich Economy & Mini-Games**: Wallet & bank accounts, daily rewards, work payouts, wallet robbery (`!rob`), item shop & inventory, casino games (`coinflip`, `slots`, `dice`), and net worth leaderboards (`!baltop`).
- 🛡️ **Interactive Moderation & Modlogs**: Audit log tracking, text/voice mutes, warning system, force nickname locking (`!forcenick`), role management with partial name matching (`admin` -> `Administrator`), and interactive mod history section buttons (`!history`).
- 🏰 **Redesigned Information Cards**: Clean server info cards (`!si`) with full-width server banners, clean profile cards (`!userinfo`) with relative timestamps (`<t:ts:R>`) and key permissions.
- 🎨 **Asset Stealing & Media Tools**: Native custom emoji and sticker stealing from message replies or arguments (`!steal`), Giphy/Tenor GIF search, polls, reminders, and Open-Meteo weather forecasts.
- 👑 **Bot Owner DM Execution & Profile Controls**: Full DM command execution for Bot Owners, custom bot server avatar/banner/bio management (`!server_avatar`, `!server_banner`, `!server_about`), prefixless command grants, and unrestricted volume control.

---

## 📋 Command Reference

### 🎵 Music & Voice
| Command | Aliases | Description |
| :--- | :--- | :--- |
| `!play <query\|url>` | `!p` | Play a track or add it to the music queue |
| `!tts say <words>` | `!speak` | Play Text-to-Speech audio in voice channel |
| `!pause` | — | Pause current music playback |
| `!resume` | — | Resume paused music playback |
| `!skip` | — | Skip current track (fetches Autoplay recommendation if queue empty) |
| `!stop` | `!leave` | Stop playback, clear queue, and disconnect from voice |
| `!queue` | `!q` | Display current music queue and loop settings |
| `!nowplaying` | `!np` | Display currently playing track info and interactive control buttons |
| `!autoplay [on\|off]` | — | Toggle automatic playback of recommended songs |
| `!volume <percent>` | — | Adjust voice volume (0–100% for regular users) |

---

### 🤖 AI Chatbot & Image Generation
| Command | Aliases | Description |
| :--- | :--- | :--- |
| `!ask <prompt>` | `!ai` | Query AI text assistant (Powered by free Gemini 1.5 Flash, Groq Llama 3, & OpenAI) |
| `!imagine <prompt>` | `!draw` | Generate AI images from text (Exclusive output via Gemini Imagen & Pollinations AI) |
| `!ailimit` | `!aiusage`, `!ailimits` | View your daily AI usage & remaining limits (10 questions & 2 images/day) |
| `!setaichannel <#ch\|reset>` | — | Set dedicated AI chat channel for automatic replies (Admins/Owners) |
| `!setaiprovider <gemini\|groq\|openai>` | — | Switch default AI text provider for the server (Admins/Owners) |
| `!clearchat` | — | Clear AI conversation memory buffer for the channel |


---

### ⭐ Leveling & Chat XP
| Command | Aliases | Description |
| :--- | :--- | :--- |
| `!rank [user]` | `!level`, `!lvl` | Display Arcane-style rank card with avatar, Level, XP, Server Rank, and progress bar |
| `!levels` | `!toplevels`, `!topxp`, `!ranks` | Display Chat Level Leaderboard with Top 5 view, user rank summary, and Top 10-100 range dropdown |
| `!setlevelchannel <#ch\|reset>` | `!levelchannel` | Set dedicated level-up announcement channel or reset to default |
| `!ignorexp [target]` | `!ignore_xp` | Toggle ignored users (`@User`), channels (`#channel`), server XP (`on/off`), or view config summary |
| `!togglexp [on\|off]` | `!toggle-xp` | Enable or disable server XP leveling system (Admins/Owners) |

---

### 💵 Economy & Shop
| Command | Aliases | Description |
| :--- | :--- | :--- |
| `!balance [user]` | `!bal` | Display rich balance card with Wallet, Bank, Net Worth, and avatar |
| `!leaderboard` | `!baltop`, `!balancetop`, `!lb`, `!top`, `!rich` | Net Worth Leaderboard with Top 5 view, user rank summary, and Top 10-100 dropdown range selector |
| `!daily` | — | Claim daily coin reward |
| `!work` | — | Work to earn wallet coins |
| `!pay <user> <amount>` | — | Transfer coins to another member |
| `!rob <user>` | — | Attempt to steal wallet coins from another member |
| `!deposit <amount>` | `!dep` | Deposit coins from wallet to bank |
| `!withdraw <amount>` | `!with` | Withdraw coins from bank to wallet |
| `!shop` | — | Browse interactive market items with category dropdown filters |
| `!buy <item_id> [amount]` | — | Purchase items from the market |
| `!inventory` | `!inv` | Display your owned items, quantities, and descriptions |
| `!use <item_id>` | — | Consume items (e.g. `!use coffee` to reset work cooldown, potions, shields) |


---

### 🛡️ Moderation & Security
| Command | Aliases | Description |
| :--- | :--- | :--- |
| `!history <user>` | — | Display user mod history with interactive section buttons (Mutes, Bans, Warnings) |
| `!mute <user> [reason]` | — | Mute member in text channels |
| `!unmute <user>` | — | Unmute member in text channels |
| `!vcmute <user>` | — | Mute member in voice channels |
| `!vcunmute <user>` | — | Unmute member in voice channels |
| `!warn <user> [reason]` | — | Issue warning (auto-escalates: 3rd=2h, 4th=1d, 5th=7d, 6th=14d, 7th=28d timeout, 8th=Kick) |
| `!warns <user>` | — | View member warning history |
| `!modlog dm [on\|off]` | `!automod dm` | Toggle Direct Message moderation notifications for the server |
| `!kick <user> [reason]` | — | Kick member from server |

| `!ban <user> [reason]` | — | Ban member from server |
| `!unban <user_id>` | — | Unban user from server |
| `!purge <amount>` | `!clear` | Bulk delete messages in current channel |
| `!role <user> <role>` | `!giverole` | Assign role (supports partial name matching e.g. `admin` -> `Administrator`) |
| `!removerole <user> <role>` | — | Remove role from member |
| `!nickname <user> <nick>` | — | Change member nickname |
| `!modlog set-channel` | — | Configure server moderation log channel |
| `!automod config` | — | View server AutoMod configuration & whitelists |
| `!automod enable` / `disable` | — | Enable or disable AutoMod protection |
| `!automod ignore channel/role` | — | Whitelist a channel or role from AutoMod |
| `!automod unignore channel/role` | — | Remove channel or role from AutoMod whitelist |
| `!automod ignore show` / `reset` | — | View or reset AutoMod whitelists |
| `!automod logging <channel>` | — | Set dedicated AutoMod event logging channel |
| `!automod punishment <action>` | — | Set default AutoMod punishment (block, alert, timeout, kick, ban) |
| `!automod list` / `blockwords` | — | Manage native AutoMod rules & word filters |


---

### 🛠️ Utility & Fun
| Command | Aliases | Description |
| :--- | :--- | :--- |
| `!steal [emoji\|sticker]` | `!stealemoji`, `!stealsticker` | Steal custom emojis or stickers from message replies or inputs |
| `!gif <query>` | `!searchgif` | Search Giphy & Tenor for standalone GIF URLs |
| `!userinfo [user]` | `!ui`, `!whois` | Display clean profile card with avatar, relative timestamps, top role, and permissions |
| `!serverinfo` | `!si`, `!sinfo` | Display clean server card with server icon thumbnail, member breakdown, and server banner |
| `!avatar [user]` | `!pfp` | Display high-resolution user profile avatar |
| `!banner [user]` | `!userbanner` | Display user profile banner |
| `!poll <question>` | — | Create an interactive poll |
| `!remind <duration> <msg>` | `!reminder` | Set a timed reminder (`10m`, `2h`, `1d`) |
| `!weather <city>` | — | Check weather forecast for any city via Open-Meteo |
| `!calculator <expr>` | `!calc` | Safely evaluate math expressions |
| `!afk [reason]` | — | Set AFK status with auto-reply when mentioned |
| `!checkvanity <code` | `!vanitycheck`, `!vanity` | Check if a Discord vanity URL/code is available or taken |
| `!trackvanity <code` | `!vanitytrack` | Track a vanity URL and receive a DM alert as soon as it becomes available |
| `!untrackvanity <code` | `!vanityuntrack` | Stop tracking a vanity URL |
| `!myvanities` | `!trackedvanities` | Display your active vanity trackers |

---


### 👑 Bot Owner Commands
| Command | Description |
| :--- | :--- |
| `!server_avatar <url\|file\|reset>` | Set or reset bot's server-specific avatar PFP |
| `!server_banner <url\|file\|reset>` | Set or reset bot's server-specific banner image |
| `!server_about <text\|reset>` | Set or reset bot's server 'About Me' bio |
| `!global_avatar <url>` | Set bot's global avatar PFP |
| `!global_banner <url>` | Set bot's global banner image |
| `!prefixless_grant <user>` | Grant prefixless command execution permission |
| `!prefixless_revoke <user>` | Revoke prefixless command execution permission |
| `!addxp <user> <amount>` | Award arbitrary XP to a member |
| `!addmoney <user> <amount>` | Add or subtract coins from any user's wallet |
| `!volume <percent>` | Set voice volume to any unrestricted percentage (up to 500%) |
| `!restart` | Reboot bot process with nickname confirmation safety |
| `!sync` | Synchronize slash/app commands globally or to current guild (works in DMs) |
| `!presence` | Configure global bot status activity presence |
| `!eval <code>` | Evaluate raw Python code snippets (Owner only) |

---

## 🚀 Getting Started

### 1. Prerequisites
- **Python 3.14+** (or Python 3.11+)
- **FFmpeg** (required for voice music & TTS playback)

### 2. Installation
Clone the repository and set up a virtual environment:
```bash
git clone https://github.com/samxlone/Helix.git
cd Helix

python -m venv .venv
# On Windows:
.venv\Scripts\activate
# On Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
```

### 3. Environment Configuration
Create a `.env` file in the root directory:
```env
DISCORD_TOKEN=your_bot_token_here
OWNER_ID=your_discord_user_id
DATABASE_URL=helix.sqlite
DEFAULT_PREFIX=!

# AI Provider Keys
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=AIzaSy...
DEFAULT_AI_PROVIDER=openai
```

### 4. Running the Bot
Launch Helix locally:
```bash
python main.py
```

---

## 🧪 Running Unit Tests

Helix features a comprehensive suite of 54 automated unit tests covering cogs, AI chatbot providers, economy calculations, leveling queries, DM execution pipelines, and UI views.

Run the test suite with `pytest`:
```bash
.venv\Scripts\python.exe -m pytest
```

---

## 🏗️ Architecture & Stack

- **Framework**: `discord.py` (v2.4+) with Hybrid Commands (`!command` & `/command` support).
- **AI Engine**: Multi-provider AI text engine (OpenAI GPT-4o-mini & Google Gemini 1.5 Flash) + Gemini Imagen image generation.
- **Database**: SQLite3 with asynchronous `aiosqlite` connection pooling.
- **Audio Engine**: Native Discord voice gateway integration with FFmpeg & Google TTS.
- **Design System**: Dark-mode Blurple & Teal theme with zero emoji clutter and relative Discord timestamps (`<t:timestamp:R>`).

---

## 📜 License

Distributed under the MIT License. See `LICENSE` for more information.
