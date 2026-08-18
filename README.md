# ⚡ Helix — High-Performance Modular Discord Bot

![Python Version](https://img.shields.io/badge/python-3.14%2B-blue.svg)
![Discord.py Version](https://img.shields.io/badge/discord.py-2.4%2B-5865F2.svg)
![Tests](https://img.shields.io/badge/pytest-116%20passed-success.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

**Helix** is a state-of-the-art, feature-rich multi-purpose Discord bot engineered with Python and `discord.py`. Designed for ultra-high performance, visual excellence, and complete community management, Helix combines advanced audio streaming, OpenAI & Gemini AI chatbot integration, Gemini Imagen AI art generation, an extensive virtual economy with interactive casino games, Arcane-style chat leveling with luxury PNG cards, fortified Anti-Nuke defense, modern dynamic ticket panels, interactive button giveaways, automated role management, custom welcome & goodbye cards, community starboards, voice mass-management tools, server template cloning, asset stealing, and exclusive owner management tools into a single clean modular architecture.

---

## 🌟 Key Highlights & Features

- 🛡️ **Fortified Anti-Nuke Defense Engine**: Real-time sliding-window rate limiting, **Auto-Recovery & Reversion** (automatically recreates deleted channels/roles, auto-revokes abused admin permissions), **Rogue Bot Auto-Kick & Inviter Ban**, **Zero-Tolerance Strict Mode**, **1-Click Emergency Server Lockdown**, and **Verified Whitelisted Admin Access Control**.
- 🎫 **Modern Dynamic Ticket System**: Fully customizable panel builder with interactive dropdowns, designated channel routing, custom support staff roles, custom channel prefixes (`vip-0001`, `app-0002`), in-ticket interactive control buttons (`Close`, `Claim/Unclaim`, `Transcript`, `Reopen`, `Delete`), and formatted transcripts.
- 👥 **Intelligent Auto Roles System**: Automatically grant designated roles to new human members and bots upon joining the server with role hierarchy verification.
- 👋 **Welcome & Goodbye System**: Automated member arrivals and departures with **Luxury Pillow Canvas PNG Cards**, rich embeds, custom text placeholders (`{user}`, `{server}`, `{membercount}`), and optional direct message welcomes.
- ⭐ **Starboard Community Showcase**: Highlight and pin top community messages with customizable star reaction milestones, author avatars, attachments, and message jump links.
- 🎉 **Interactive Button Giveaway System**: Persistent live toggle buttons (`🎉 Enter (count)`), flexible duration parsing (`3h`, `30d`, `1h30m`, `2d12h`, `1mo`), automated background winner picking with fair RNG, and manual reroll tools.
- 🎙️ **Voice Channel Mass Tools**: Mass move (`!vcmove`), pull/drag members (`!vcdrag` / `!pull`), disconnect members (`!vdc`), and bulk mute/unmute/deafen/undeafen all members in voice channels.
- 🎵 **Advanced Audio & Music System**: High-quality voice playback, queue management, volume control, single-line LunaBot-style notifications, equalizer presets, voice channel TTS with multi-language & Hinglish auto-detection, and autoplay recommendations.
- 🤖 **AI Chatbot & Image Generation**: Multi-provider AI text engine (OpenAI GPT-4o-mini & Google Gemini 1.5 Flash), Google Gemini Imagen AI image generation (`!imagine`), sliding conversation memory buffer, dedicated AI channel scoping (`!setaichannel #ai-chat`), and Bot Owner exemptions.
- 💳 **Arcane-Style Leveling & Chat XP**: XP earning engine, level-up role rewards, custom dedicated level notification channels (`!setlevelchannel`), multi-target XP toggles (`!ignorexp` for users, channels, or server), Arcane-style rank cards (`!rank`), and interactive level leaderboards (`!levels`).
- 💵 **Rich Economy & Mini-Games**: Wallet & bank accounts, daily rewards, work payouts, wallet robbery (`!rob`), item shop & inventory, casino games (Blackjack, TicTacToe, Connect 4, Mines, HighLow, Trivia, RPS, Roulette, Slots), and net worth leaderboards (`!baltop`).
- 🏰 **Server Cloning & Template Engine**: Feed Discord template links (`https://discord.new/...`), invite links, or guild IDs to clone categories, text/voice channels, role hierarchies, and exact permission overwrites (including `@everyone` default role permissions).
- 🎨 **Asset Stealing & Media Tools**: Native custom emoji and sticker stealing from message replies or arguments (`!steal`), Giphy/Tenor GIF search, polls, reminders, and Open-Meteo weather forecasts.
- 📊 **Live Telemetry & Platform Stats**: Detailed live metrics (`!stats`, `!telemetry`, `!serverstats`) showcasing server lookbacks, message/voice graphs, memory usage, audio sessions, and gateway latency.
- 👑 **Bot Owner Integration & Control Tools**: Exclusive Bot Owner DM command privileges, voice channel bomb dragging (`!vcbomb`), custom bot server avatar/banner/bio profile management (`!server_avatar`, `!server_banner`, `!server_about`), global presence rotation, prefixless command grants, and unrestricted volume control.

---

## 📋 Command Reference

### 🛡️ Fortified Anti-Nuke System
> 🔒 **Security Notice**: Anti-Nuke configuration commands are restricted to the **Server Owner**, **Bot Owner**, and **Verified Whitelisted Admins**.

| Command | Aliases | Description |
| :--- | :--- | :--- |
| `!antinuke config` | `!antinuke status` | View Anti-Nuke defense status, protected modules, and whitelists |
| `!antinuke enable` | `/antinuke enable` | Arm and enable Anti-Nuke server defense |
| `!antinuke disable` | `/antinuke disable` | Temporarily disable Anti-Nuke server defense |
| `!antinuke strict <on\|off>` | `/antinuke strict` | Toggle Zero-Tolerance Mode (Instant ban on 1st unauthorized action) |
| `!antinuke recovery <on\|off>` | `/antinuke recovery` | Toggle Auto-Recovery & Undo for deleted channels/roles |
| `!antinuke lockdown <on\|off>` | `/antinuke lockdown` | Emergency 1-second serverwide lockdown (locks `@everyone` text/voice) |
| `!antinuke punishment <mode>` | `/antinuke punishment` | Set punishment mode (`ban`, `kick`, `strip_roles`, `quarantine`) |
| `!antinuke threshold <act> <cnt> <sec>` | `/antinuke threshold` | Configure per-action speed thresholds (e.g. `channel_delete 1 10`) |
| `!antinuke whitelist add_user <user> [cat]` | `/antinuke whitelist add_user` | Whitelist a trusted user for specific or `all` categories |
| `!antinuke whitelist add_role <role> [cat]` | `/antinuke whitelist add_role` | Whitelist a trusted role for specific or `all` categories |
| `!antinuke whitelist remove_user <user>` | `/antinuke whitelist remove_user` | Remove a user from the Anti-Nuke whitelist |
| `!antinuke whitelist remove_role <role>` | `/antinuke whitelist remove_role` | Remove a role from the Anti-Nuke whitelist |
| `!antinuke whitelist show` | `/antinuke whitelist show` | Display all currently whitelisted users and roles with categories |

---

### 👥 Auto Roles System
| Command | Aliases | Description |
| :--- | :--- | :--- |
| `!autorole add <@role>` | `!autorole human` | Assign role automatically to new human members on join |
| `!autorole bot <@role>` | `!autorole bots` | Assign role automatically to new bots on join |
| `!autorole remove <@role>` | `!autorole del` | Remove an existing auto role from configuration |
| `!autorole show` | `!autorole list` | Display all currently configured server auto roles |

---

### 👋 Welcome & Goodbye System
| Command | Aliases | Description |
| :--- | :--- | :--- |
| `!setwelcome [#channel]` | `/setwelcome` | Designate the welcome announcements channel |
| `!setgoodbye [#channel]` | `/setgoodbye` | Designate the member departure channel |
| `!welcomemsg <text>` | `/welcomemsg` | Set custom welcome text (`{user}`, `{server}`, `{membercount}`) |
| `!welcometype <card\|embed\|text>` | `/welcometype` | Choose visual presentation style (Luxury Card / Embed / Text) |
| `!testwelcome` | `/testwelcome` | Generate a live preview of the welcome announcement in chat |

---

### ⭐ Starboard Showcase System
| Command | Aliases | Description |
| :--- | :--- | :--- |
| `!setstarboard [#channel]` | `/setstarboard` | Set the channel where starred messages are posted |
| `!starboard threshold <number>` | `!starboard limit` | Set minimum reaction stars required *(default: 3)* |
| `!starboard emoji <emoji>` | — | Set custom reaction emoji for Starboard |
| `!starboard toggle` | — | Toggle Starboard on or off for the server |
| `!starboard` | — | View current Starboard configuration and status |

---

### 🎫 Modern Dynamic Ticket System
| Command | Aliases | Description |
| :--- | :--- | :--- |
| `!ticket panel create [category] [role] [log] [title]` | — | Deploy a dynamic interactive ticket panel embed with dropdown |
| `!ticket panel addoption <panel_msg_id> <emoji> <label> <desc> [category] [role] [prefix]` | — | Add a custom ticket category with specific staff role and prefix |
| `!ticket panel removeoption <panel_msg_id> <label>` | — | Remove a dropdown option from an active ticket panel |
| `!ticket panel setdesc <panel_msg_id> <desc>` | — | Update the description message of a ticket panel |
| `!ticket panel setlog <panel_msg_id> <#log>` | — | Update the transcript logging channel for a ticket panel |
| `!ticket panel listoptions <panel_msg_id>` | — | View all configured ticket categories and routing for a panel |
| `!ticket add <user>` | — | Add a member to the current ticket channel |
| `!ticket remove <user>` | — | Remove a member from the current ticket channel |
| `!ticket rename <name>` | — | Rename the current ticket channel |
| `!ticket close [reason]` | — | Close the current ticket channel |
| `!ticket transcript` | — | Generate and export conversation transcript to channel & logs |

---

### 🎉 Interactive Button Giveaways
| Command | Aliases | Description |
| :--- | :--- | :--- |
| `!giveaway start <duration> <winners> <prize>` | `!gstart` | Start an interactive giveaway with live toggle button (e.g. `!gstart 30d 1 Nitro`) |
| `!giveaway end <message_id>` | `!gend` | Immediately end an active giveaway and pick winners |
| `!giveaway reroll <message_id>` | `!greroll` | Reroll new winners from existing entrants |
| `!giveaway list` | `!glist` | List all active giveaways in the server |

---

### 🎙️ Voice Channel Mass Tools
| Command | Aliases | Description |
| :--- | :--- | :--- |
| `!vcmove <from_vc> <to_vc>` | `/vc move` | Move all connected members from one voice channel to another |
| `!vcdrag <member>` | `!pull <member>`, `/vc drag` | Pull/drag a target member into your current voice channel |
| `!vdc <member>` | `/vc disconnect` | Disconnect a target member from voice channels |
| `!massmute [vc]` | `/vc massmute` | Server mute all members in the specified or current voice channel |
| `!massunmute [vc]` | `/vc massunmute` | Server unmute all members in the specified or current voice channel |
| `!massdeafen [vc]` | `/vc massdeafen` | Server deafen all members in the specified or current voice channel |
| `!massundeafen [vc]` | `/vc massundeafen` | Server undeafen all members in the specified or current voice channel |

---

### 🎵 Music & Audio System
| Command | Aliases | Description |
| :--- | :--- | :--- |
| `!play <query\|url>` | `!p` | Play a track or add it to the music queue |
| `!nowplaying` | `!np` | Show current playing track with interactive persistent controls |
| `!queue` | `!q` | Display current music queue with interactive pagination |
| `!pause` | — | Pause current music playback |
| `!resume` | — | Resume paused music playback |
| `!skip` | — | Skip current track (fetches Autoplay recommendation if queue empty) |
| `!stop` | `!leave` | Stop playback, clear queue, and disconnect from voice |
| `!volume <1-150>` | `!vol` | Adjust voice playback volume |
| `!loop <off\|track\|queue>` | — | Set track or queue looping mode |
| `!autoplay <on\|off>` | — | Toggle automatic related track recommendations |
| `!tts say <words>` | `!speak` | Play Text-to-Speech audio in voice channel |

---

### 🤖 AI Assistant & Image Generation
| Command | Aliases | Description |
| :--- | :--- | :--- |
| `!ask <prompt>` | `!ai` | Query conversational AI assistant *(Gemini & Groq free models)* |
| `!imagine <prompt>` | `!draw` | Generate AI artwork and digital illustration *(Exclusive image output)* |
| `!clearchat` | — | Clear AI conversation memory buffer for the channel |
| `!ailimit` | — | Check remaining daily AI text and image generation quota |
| `!setaiprovider <engine>` | — | Switch default AI engine (`gemini`, `groq`, `openai`) |

---

### 💳 Leveling & Chat XP
| Command | Aliases | Description |
| :--- | :--- | :--- |
| `!rank [user]` | `!level` | View luxury Obsidian & Crimson Glassmorphism level rank card |
| `!levels` | `!lb`, `!top` | View interactive server XP leaderboard with pagination |
| `!setlevelchannel <#ch\|reset>` | — | Designate level-up announcement channel |
| `!togglexp [on\|off]` | — | Enable or disable server XP leveling system |
| `!ignorexp [target]` | — | Toggle ignored users/channels or view config |
| `!addxp <user> <amount>` | — | Add XP directly to a user *(Admin/Owner only)* |

---

### 💵 Economy, Shop & Casino Games
| Command | Aliases | Description |
| :--- | :--- | :--- |
| `!balance [user]` | `!bal` | View wallet and bank vault balances *(or luxury PNG card)* |
| `!daily` | — | Claim daily coin allowance |
| `!work` | — | Complete shifts for variable coin rewards |
| `!pay <user> <amount>` | `!give` | Transfer funds from your wallet to another member |
| `!rob <user>` | — | Attempt to steal coins from another user's wallet |
| `!deposit <amount>` | `!dep` | Deposit coins from wallet to bank |
| `!withdraw <amount>` | `!with` | Withdraw coins from bank to wallet |
| `!shop` | — | Browse server marketplace items |
| `!inventory [user]` | `!inv` | View purchased items and role privileges |
| `!blackjack <bet>` | `!bj` | Play interactive Blackjack against dealer with buttons |
| `!tictactoe <opponent>` | `!ttt` | Play 2-player interactive Tic-Tac-Toe grid |
| `!connect4 <opponent>` | `!c4` | Play 2-player interactive Connect 4 board |
| `!mines <bet>` | — | Interactive risk & reward Minesweeper casino grid |
| `!highlow <bet>` | `!hl` | Guess Higher or Lower with streak multiplier cashouts |
| `!trivia [category]` | — | Multi-choice interactive trivia challenge |
| `!slots <bet>` | — | Classic 3-reel casino slot machine |
| `!roulette <bet> <space>` | — | Casino roulette table betting |
| `!coinflip <bet> <side>` | `!cf` | Double-or-nothing coin flip |

---

### 🛡️ Moderation & Server Administration
| Command | Aliases | Description |
| :--- | :--- | :--- |
| `!ban <user> [reason]` | — | Ban member from the server with audit log entry |
| `!unban <user_id> [reason]` | — | Unban member by ID |
| `!kick <user> [reason]` | — | Kick member from the server |
| `!mute <user> <duration> [reason]` | `!timeout` | Timeout member with flexible duration (`10m`, `2h`, `7d`) |
| `!unmute <user> [reason]` | `!untimeout` | Remove timeout from member |
| `!warn <user> [reason]` | — | Issue formal moderation warning to member |
| `!warns <user>` | `!warnings` | View active warning history for member |
| `!rwarn <user> <id>` | — | Revoke warning by ID |
| `!purge <count>` | `!clear` | Bulk delete messages in channel |
| `!lock [#ch]` / `!unlock [#ch]` | — | Lock or unlock text channel for `@everyone` |
| `!hide [#ch]` / `!unhide [#ch]` | — | Hide or unhide text channel from `@everyone` |
| `!forcenick <user> <name>` | — | Permanently enforce member nickname against unauthorized changes |
| `!unforcenick <user>` | — | Release enforced nickname lock |
| `!modlog set-channel <#ch>` | — | Designate primary moderation audit channel |

---

### 📊 Platform Statistics & Telemetry
| Command | Aliases | Description |
| :--- | :--- | :--- |
| `!stats` | `!botstats`, `/stats` | Live Helix network, community scale, voice sessions & telemetry |
| `!telemetry` | `!cluster`, `!syshealth` | Deep database latency, cache concurrency & gateway health |
| `!serverstats` | `!sstats`, `!dashboard` | Statbot lookback graph, message volume & voice hours PNG card |
| `!serverinfo` | `!si` | Server stats, owner, security level & banner |
| `!userinfo [user]` | `!ui` | User profile card, account age & server permissions |
| `!membercount` | `!mc` | Total server member breakdown (Humans vs Bots) |

### 🎯 Snipe & Message History System
| Command | Aliases | Description |
| :--- | :--- | :--- |
| `!snipe [index]` | `!s`, `/snipe` | Snipe recently deleted messages with attachments, images & stickers |
| `!editsnipe [index]` | `!esnipe`, `/editsnipe` | View before/after diff of recently edited messages in channel |
| `!reactionsnipe [index]` | `!rsnipe`, `/reactionsnipe` | View recently removed reactions with target message jump links |
| `!clearsnipe` | `!csnipe`, `/clearsnipe` | Purge deleted, edited, and reaction snipe caches for channel *(Manage Messages)* |

---

### 👑 Bot Owner & Branding Commands
| Command | Aliases | Description |
| :--- | :--- | :--- |
| `!server_avatar <url>` | — | Set custom server-specific bot profile avatar |
| `!server_banner <url>` | — | Set custom server-specific bot profile banner |
| `!server_about <text>` | — | Set custom server-specific bot 'About Me' bio |
| `!global_avatar <url>` | — | Set global bot profile avatar |
| `!global_banner <url>` | — | Set global bot profile banner |
| `!vcbomb <member>` | `!vcb` | Bomb target between voice channels *(Owner only)* |
| `!prefixless_grant <user>` | — | Grant prefix-free command execution permissions |
| `!prefixless_revoke <user>` | — | Revoke prefix-free command execution permissions |
| `!prefixless_list` | — | List all members with prefix-free permissions |
| `!restart` | — | Reboot bot process with nickname confirmation |
| `!sync` | — | Sync application and slash commands globally or to guild |
| `!eval <code>` | — | Evaluate Python code asynchronously |

---

## 🛠️ Installation & Quickstart

### Prerequisites
- **Python 3.10+** (Tested on Python 3.14)
- **FFmpeg** installed and added to system `PATH`
- **Discord Bot Token** with `Message Content`, `Server Members`, and `Presence` intents enabled in Discord Developer Portal.

### Setup
```bash
# 1. Clone the repository
git clone https://github.com/samxlone/Helix.git
cd Helix

# 2. Create and activate virtual environment
python -m venv .venv
# On Windows:
.venv\Scripts\activate
# On Linux/macOS:
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment variables
# Copy .env.example to .env and fill in tokens
cp .env.example .env

# 5. Launch Helix
python main.py
```

### Running Tests
```bash
python -m pytest tests/
```

---

## 📄 License
This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.
