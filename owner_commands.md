# 👑 Owner-Only Commands Reference Guide

This document provides a comprehensive reference for all commands restricted to the **Bot Owner** or **Server Owner** (bypassing standard permission checks and enabling execution in DMs).

> [!NOTE]
> All Bot Owner commands work seamlessly in **Direct Messages (DMs)** as well as server channels!

---

## 💻 Bot DM Execution Pipeline
Bot Owners can execute commands directly in the bot's DMs without triggering `NoPrivateMessage` errors. The following commands support full DM execution:
- `eval`, `restart`, `sync`, `presence`, `presence_rotation`
- `global_avatar`, `global_banner`, `server_avatar`, `server_banner`, `server_about`
- `prefixless_grant`, `prefixless_revoke`, `prefixless_list`
- `volume`, `voice_debug`, `help`, `np`

---

## 💵 Economy Commands

### `addmoney` / `addbalance`
- **Description:** Adds or removes coins directly to/from a member's wallet (Server Owner or Bot Owner only).
- **Usage:**
  - `addmoney @User 1000` — Adds 1,000 coins to the user's wallet.
  - `addmoney @User -500` — Subtracts 500 coins from the user's wallet.
- **Prefix-less support:** Yes (e.g. `addmoney @User 500`).

---

## ⭐ Leveling & XP Controls

### `addxp`
- **Description:** Adds a specified amount of XP to a member. Triggers level-up announcements and awards level role rewards if threshold reached.
- **Usage:**
  - `addxp @User 5000` — Awards 5,000 XP to the user.
- **Prefix-less support:** Yes.

### `ignorexp` / `ignore_xp`
- **Description:** Toggles ignoring XP gain for a user, a text channel, or server-wide XP leveling (Admins, Server Owners & Bot Owner).
- **Usage:**
  - `ignorexp @User` — Toggle XP gain for specified member.
  - `ignorexp #channel` — Toggle XP gain in specified text channel.
  - `ignorexp on` / `off` — Toggle server-wide XP leveling system.
  - `ignorexp` (no args) — View current leveling configuration summary embed.
- **Prefix-less support:** Yes.

### `setlevelchannel` / `levelchannel`
- **Description:** Configures a dedicated channel where level-up notifications will be announced (Admins, Server Owners & Bot Owner).
- **Usage:**
  - `setlevelchannel #bot-commands` — Direct level-up messages to `#bot-commands`.
  - `setlevelchannel current` — Set to current channel.
  - `setlevelchannel reset` — Reset to default message channel.
- **Prefix-less support:** Yes.

---

## ⚙️ System & Diagnostic Commands

### `eval` / `evaluate`
- **Description:** Evaluates raw Python code snippets asynchronously in real time (Bot Owner only).
- **Usage:**
  - `eval 2 + 2`
  - `eval return ctx.guild.member_count`
  - ```py
    eval
    import os
    return os.listdir('.')
    ```
- **Prefix-less support:** Yes.

### `restart`
- **Description:** Safely reboots the bot process. Writes confirmation message ID to state, restarts the Python process, and edits the message to `🟢 Bot is online!` upon reconnect.
- **Usage:**
  - `restart`
- **Prefix-less support:** Yes.

### `sync`
- **Description:** Synchronizes application/slash commands with the current server or globally across Discord (works in DMs!).
- **Usage:**
  - `sync` — Syncs to the current guild.
  - `sync global` — Syncs all slash commands globally across Discord.
  - `!sync 123456789` — Syncs to a specific guild ID.
- **Prefix-less support:** Yes.

### `voice_debug`
- **Description:** Runs voice connection diagnostics, checks PyNaCl/Opus loading status, voice client state, and active streams.
- **Usage:**
  - `voice_debug`
- **Prefix-less support:** Yes.

### `presence` / `presence_rotation`
- **Description:** Configures global rich presence (activity, status, text, streaming URL) or sets up an automated activity rotation schedule (Bot Owner only).
- **Usage:**
  - `presence <activity_type> <status> <text> [streaming_url]`
  - `presence_add <activity_type> <status> <text>`
  - `presence_rotation start <seconds>` — Rotates presence every N seconds (min 15s).
  - `presence_rotation stop` / `list` / `clear`
- **Activity Types:** `playing`, `streaming`, `listening`, `watching`
- **Statuses:** `online`, `idle`, `dnd`, `invisible`
- **Examples:**
  - `presence listening online music to relax to`
  - `presence streaming dnd Lofi Beats https://twitch.tv/monstercat`
- **Prefix-less support:** Yes.

---

## 🎵 Music Commands

### `volume` / `vol`
- **Description:** Sets or displays voice playback volume. Regular users are capped at 100%, while Bot Owners have unrestricted volume scaling (e.g. 150%, 500%).
- **Usage:**
  - `volume` — Displays current volume percentage.
  - `volume 150` — Sets volume to 150%.
  - `volume 500` — Boosts volume to 500%.
- **Prefix-less support:** Yes.

---

## ⚙️ Prefix-less Permissions Control

### `prefixless_grant` / `plgrant` / `plallow`
- **Description:** Grants a user permission to run prefix-less commands within a specific server (Bot Owner only).
- **Usage:**
  - `prefixless_grant @User` — Grants permission in the current server.
  - `prefixless_grant @User 123456789` — Grants permission for server ID `123456789`.
- **Prefix-less support:** Yes.

### `prefixless_revoke` / `plrevoke` / `pldeny`
- **Description:** Revokes a user's prefix-less command permission within a server (Bot Owner only).
- **Usage:**
  - `prefixless_revoke @User`
- **Prefix-less support:** Yes.

### `prefixless_list` / `pllist`
- **Description:** Lists all users granted prefix-less command permissions in a server.
- **Usage:**
  - `prefixless_list`
- **Prefix-less support:** Yes.

---

## 🖼️ Bot Profile Customization Commands

### `server_avatar` / `setserveravatar` / `setserverpfp` / `server_pfp`
- **Description:** Sets or resets the bot's server-specific profile picture (avatar PFP) for a specific server (Bot Owner only, works in DMs!).
- **Usage:**
  - `server_avatar <image_url> [guild_id]` — Sets server avatar using an image URL.
  - Attach image with `server_avatar` — Sets server avatar using attached file.
  - `server_avatar reset` — Resets back to global avatar.

### `server_banner` / `setserverbanner`
- **Description:** Sets or resets the bot's server-specific profile banner for a server (Bot Owner only, works in DMs!).
- **Usage:**
  - `server_banner <image_url> [guild_id]` — Sets server banner using an image URL.
  - Attach image with `server_banner` — Sets server banner using attached file.
  - `server_banner reset` — Resets back to default.

### `global_avatar` / `setglobalavatar` / `setbotavatar`
- **Description:** Changes the bot's global account profile picture across all servers (Bot Owner only).
- **Usage:**
  - `global_avatar <image_url>` — Sets global avatar URL.
  - Attach image with `global_avatar` — Sets global avatar attached file.

### `global_banner` / `setglobalbanner` / `setbotbanner`
- **Description:** Changes the bot's global account profile banner across all servers (Bot Owner only).
- **Usage:**
  - `global_banner <image_url>` — Sets global banner URL.

### `server_about` / `setserverabout` / `server_bio` / `setserverbio`
- **Description:** Sets or resets the bot's server-specific "About Me" bio for a server (Bot Owner only, works in DMs!).
- **Usage:**
  - `server_about <text>` — Sets bot's server "About Me" bio.
  - `server_about reset` — Resets bio back to default.
