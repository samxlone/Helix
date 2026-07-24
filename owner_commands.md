# 👑 Owner-Only Commands Reference Guide

This file lists all commands restricted to the **Bot Owner** or **Server Owner** (bypassing normal server administration controls).

---

## 💵 Economy Commands

### `addmoney` / `addbalance`
- **Description:** Adds or removes coins directly to/from a member's wallet.
- **Usage:**
  - `addmoney @User 1000` — Adds 1,000 coins to the user's wallet.
  - `addmoney @User -500` — Subtracts 500 coins from the user's wallet.
- **Prefix-less support:** Yes (e.g. `addmoney @User 500`).

---

## ⭐ Leveling Commands

### `addxp`
- **Description:** Adds a specified amount of XP to a member. If the XP pushes them past a level threshold, it triggers a level up and awards any configured role rewards.
- **Usage:**
  - `addxp @User 5000` — Awards 5,000 XP to the user.
- **Prefix-less support:** Yes.

### `presence_add` and `presence_rotation`
- **Description:** Builds and runs a global presence rotation. Only the `.env` `OWNER_ID` can use these commands.
- **Commands:**
  - `presence_add <activity_type> <status> <text>` — adds an entry.
  - `presence_rotation start <seconds>` — begins rotation; the minimum duration is 15 seconds.
  - `presence_rotation stop`, `presence_rotation list`, `presence_rotation remove <number>`, `presence_rotation clear`.
- **Example:** `presence_add playing online Music and games!`, then `presence_add watching idle your server`, then `presence_rotation start 60`.

### `ignorexp`
- **Description:** Toggles XP ignored status for a user. If ignored, the bot will not count their messages towards leveling or award them any XP.
- **Usage:**
  - `ignorexp @User` — Stops counting XP for the user (or starts counting it again if they were already ignored).
- **Prefix-less support:** Yes.

---

## ⚙️ System & Diagnostic Commands

### `restart`
- **Description:** Safely restarts the bot. Writes the confirmation message ID to state, restarts the python process, and edits the message to say `🟢 Bot is online!` when it comes back up.
- **Usage:**
  - `restart`
- **Prefix-less support:** Yes.

### `sync`
- **Description:** Forces the bot's application/slash commands to register and sync with the current Discord server or globally.
- **Usage:**
  - `/sync` (or `sync`) — Syncs to the current guild.
  - `!sync [guild_id]` — Syncs to a specific guild ID.
- **Prefix-less support:** Yes.

### `voice_debug`
- **Description:** Runs voice connection diagnostics, checks voice client state, checks if PyNaCl/Opus is loaded, and lists active streams.
- **Usage:**
  - `voice_debug` (or `!voice_debug`)
- **Prefix-less support:** Yes.

### `presence`
- **Description:** Customizes the bot's rich presence (activity, status, text, streaming URL). Only the user whose ID is set in `.env` as `OWNER_ID` can use it. Changes are persisted in the settings database (guild 0) and re-applied automatically whenever the bot restarts.
- **Important:** Discord presence belongs to the bot account and is therefore global. It cannot be different for individual servers, and a server owner cannot be granted a server-only bot-presence permission.
- **Usage:**
  - `presence <activity_type> <status> <text> [streaming_url]`
  - **Activity Types:** `playing`, `streaming`, `listening`, `watching`
  - **Statuses:** `online`, `idle`, `dnd`, `invisible`
- **Examples:**
  - `presence listening online music to relax to`
  - `presence streaming dnd Lofi Beats https://twitch.tv/monstercat`
- **Prefix-less support:** Yes.

---

## 🎵 Music Commands

### `volume` / `vol`
- **Description:** Sets or displays the bot's voice playback volume to any unrestricted percentage (owner-only).
- **Usage:**
  - `volume` — Displays the current volume percentage.
  - `volume 150` — Sets volume to 150%.
  - `volume 5000` — Boosts volume to 5000%.
- **Prefix-less support:** Yes.


---

## ⚙️ Prefix-less Permissions Control

### `prefixless_grant` / `plgrant` / `plallow`
- **Description:** Grants a user permission to run prefix-less commands within a specific server (owner-only). Users granted this permission will still be checked for their normal command permissions (e.g. moderators can run mod commands prefixless, while normal members can only run normal commands prefixless).
- **Usage:**
  - `prefixless_grant @User` — Grants permission in the current server.
  - `prefixless_grant @User 123456789` — Grants permission for server with ID `123456789`.
- **Prefix-less support:** Yes.

### `prefixless_revoke` / `plrevoke` / `pldeny`
- **Description:** Revokes a user's permission to run prefix-less commands within a specific server (owner-only).
- **Usage:**
  - `prefixless_revoke @User` — Revokes permission in the current server.
  - `prefixless_revoke @User 123456789` — Revokes permission for server with ID `123456789`.
- **Prefix-less support:** Yes.

### `prefixless_list` / `pllist`
- **Description:** Lists all users who have prefix-less command permissions in a server.
- **Usage:**
  - `prefixless_list` — Lists users in the current server.
  - `prefixless_list 123456789` — Lists users in server with ID `123456789`.
- **Prefix-less support:** Yes.

---

## 🖼️ Bot Profile Customization Commands

### `server_avatar` / `setserveravatar` / `setserverpfp` / `server_pfp`
- **Description:** Sets or resets the bot's server-specific profile picture (avatar PFP) for a specific server (owner-only).
- **Usage:**
  - `server_avatar <image_url> [guild_id]` — Sets server avatar using an image URL.
  - Attach image with `server_avatar` — Sets server avatar using the attached image file.
  - `server_avatar reset` — Resets server avatar back to the global bot avatar.

### `server_banner` / `setserverbanner`
- **Description:** Sets or resets the bot's server-specific profile banner for a specific server (owner-only).
- **Usage:**
  - `server_banner <image_url> [guild_id]` — Sets server banner using an image URL.
  - Attach image with `server_banner` — Sets server banner using the attached image file.
  - `server_banner reset` — Resets server banner back to default.

### `global_avatar` / `setglobalavatar` / `setbotavatar`
- **Description:** Changes the bot's global account profile picture across all servers (owner-only).
- **Usage:**
  - `global_avatar <image_url>` — Sets global bot avatar using an image URL.
  - Attach image with `global_avatar` — Sets global bot avatar using attached image file.
  - `global_avatar reset` — Resets global avatar back to default.

### `global_banner` / `setglobalbanner` / `setbotbanner`
- **Description:** Changes the bot's global account profile banner across all servers (owner-only).
- **Usage:**
  - `global_banner <image_url>` — Sets global bot banner using an image URL.
  - Attach image with `global_banner` — Sets global bot banner using attached image file.
  - `global_banner reset` — Resets global banner back to default.

### `server_about` / `setserverabout` / `server_bio` / `setserverbio`
- **Description:** Sets or resets the bot's server-specific "About Me" bio for a server (owner-only).
- **Usage:**
  - `server_about <text>` — Sets the bot's server-specific "About Me" bio.
  - `server_about reset` — Resets the bot's server-specific bio back to default.


