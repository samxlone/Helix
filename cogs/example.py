from datetime import datetime, timezone

import discord
from discord.ext import commands


class Example(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="help")
    async def help(self, ctx: commands.Context):
        """View all command categories available in the bot."""
        prefix = ctx.clean_prefix
        bot_name = self.bot.user.name if self.bot.user else "MyBot"
        embed = discord.Embed(
            title=f"🎵 {bot_name} — Your All-in-One Discord Bot! 🎵",
            description=(
                "*Music, moderation, economy, games, and useful server tools—all in one place.*\n\n"
                f"• **My prefix for this server:** `{prefix}`\n"
                f"• **Play music:** join a voice channel, then use `{prefix}play <song name>`\n"
                "• **Need help with a category?** Choose one from the menu below.\n\n"
                "**Command Categories**\n"
                "🎵 Music & Audio\n"
                "💰 Economy & Leveling\n"
                "🎮 Games & Fun\n"
                "🛡️ Moderation\n"
                "🧰 Utility & Server\n"
                "⚙️ Configuration"
            ),
            color=discord.Color.dark_teal(),
            timestamp=datetime.now(timezone.utc),
        )
        if self.bot.user and self.bot.user.display_avatar:
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)

        embed.set_footer(text=f"{self._owner_text()} • Select a category below")
        await ctx.send(embed=embed, view=HelpDropdownView(self.bot, prefix))

    def _owner_text(self) -> str:
        owner = getattr(self.bot, "owner_user", None)
        return f"Created & owned by {owner.name}" if owner else "Your server companion"


class HelpDropdownView(discord.ui.View):
    def __init__(self, bot, prefix: str):
        super().__init__(timeout=180)
        self.add_item(HelpSelect(bot, prefix))


class HelpSelect(discord.ui.Select):
    def __init__(self, bot, prefix: str):
        self.bot = bot
        self.prefix = prefix
        options = [
            discord.SelectOption(label="Music & Audio", description="Play, queue, control, and customize music.", emoji="🎵", value="music"),
            discord.SelectOption(label="Economy & Leveling", description="Balance, rewards, work, shop, and XP.", emoji="💰", value="economy"),
            discord.SelectOption(label="Games & Fun", description="Coinflip, slots, blackjack, and more.", emoji="🎮", value="games"),
            discord.SelectOption(label="Moderation", description="Member, role, warning, and channel tools.", emoji="🛡️", value="mod"),
            discord.SelectOption(label="Utility & Server", description="Server information and general utilities.", emoji="🧰", value="utility"),
            discord.SelectOption(label="Configuration", description="Prefix, server settings, and leveling setup.", emoji="⚙️", value="admin"),
        ]
        super().__init__(placeholder="Select a command category…", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        category = self.values[0]
        embed = discord.Embed(color=discord.Color.dark_teal())

        if category == "music":
            embed.title = "🎵 Music & Audio"
            embed.description = (
                f"Start by joining a voice channel, then use `{self.prefix}play <song/link>`.\n\n"
                f"• `{self.prefix}play <song>` — Play music from YouTube (keywords or links).\n"
                f"• `{self.prefix}join` / `{self.prefix}leave` — Connect or disconnect the bot to/from your channel.\n"
                f"• `{self.prefix}pause` / `{self.prefix}resume` — Pause or resume current playback.\n"
                f"• `{self.prefix}stop` — Stop playing music, clear the queue, and leave the channel.\n"
                f"• `{self.prefix}skip` — Skip the current playing song.\n"
                f"• `{self.prefix}queue` (or `q`) — View all songs currently in the server queue.\n"
                f"• `{self.prefix}clearqueue` — Remove all queued tracks.\n"
                f"• `{self.prefix}remove <position>` — Remove a specific track by its queue number.\n"
                f"• `{self.prefix}shuffle` — Randomize the order of the song queue.\n"
                f"• `{self.prefix}nowplaying` (or `np`) — View the details of the active song.\n"
                f"• `{self.prefix}autoplay` — Toggle recommendation autoplay when queue runs dry.\n"
                f"• `{self.prefix}loop` — Toggle looping (Off, Single Track, Entire Queue).\n"
                f"• `{self.prefix}seek <duration>` — Jump to a timestamp (e.g. `1m30s`).\n"
                f"• `{self.prefix}lyrics [song]` — Get lyrics for current or specified song.\n"
                f"• `{self.prefix}volume <%>` (or `vol`) — *(Owner only)* Adjust volume up to `1000%`.\n\n"
                "💡 **Equalizer presets** (like Bass Boost) can be chosen using the buttons on the now playing panel."
            )
        elif category == "economy":
            embed.title = "💰 Economy & Leveling"
            embed.description = (
                "**Economy Commands:**\n"
                f"• `{self.prefix}balance` (or `bal`) — Check your or another user's wallet & bank balance.\n"
                f"• `{self.prefix}daily` — Claim your free daily coins reward.\n"
                f"• `{self.prefix}work` — Earn coins by working a random shift.\n"
                f"• `{self.prefix}pay <member> <amount>` — Send coins from your wallet to a member.\n"
                f"• `{self.prefix}deposit <amount/all>` (or `dep` / `deposite`) — Deposit wallet coins to your bank (protects from robbery). Supports `all`.\n"
                f"• `{self.prefix}withdraw <amount/all>` (or `with`) — Withdraw coins from bank back to wallet. Supports `all`.\n"
                f"• `{self.prefix}inventory` (or `inv`) — View items purchased from the server shop.\n"
                f"• `{self.prefix}shop` — Browse available items in the server shop.\n"
                f"• `{self.prefix}buy <item_key> [amount]` — Buy a specific item from the shop.\n"
                f"• `{self.prefix}rob <member>` — Try stealing coins from another member's wallet.\n"
                f"• `{self.prefix}addmoney <member> <amount>` — *(Owner only)* Add/remove coins from a member's balance.\n\n"
                "**Leveling Commands:**\n"
                f"• `{self.prefix}leveling` — Display your active leveling rank, level, and XP card."
            )
        elif category == "games":
            embed.title = "🎮 Games & Fun"
            embed.description = (
                f"• `{self.prefix}coinflip <heads/tails> <bet>` — Flip a coin to double your bet!\n"
                f"• `{self.prefix}slots <bet>` — Spin the slot machine for a chance at high payouts.\n"
                f"• `{self.prefix}blackjack <bet>` — Challenge the bot to a game of Blackjack.\n\n"
                "⚠️ *Betting uses your active economy wallet balance. Play wisely!*"
            )
        elif category == "mod":
            embed.title = "🛡️ Moderation"
            embed.description = (
                f"• `{self.prefix}kick <member> [reason]` — Kick a member from the server.\n"
                f"• `{self.prefix}ban <member> [reason]` — Ban a member from the server.\n"
                f"• `{self.prefix}unban <user_id>` — Unban a user by their unique ID.\n"
                f"• `{self.prefix}softban <member> [reason]` — Ban and immediately unban a user to clear their recent messages.\n"
                f"• `{self.prefix}hardban <member> [reason]` — Permanently ban and delete 7 days of their messages.\n"
                f"• `{self.prefix}timeout <member> [minutes] [reason]` — Timeout/mute a member.\n"
                f"• `{self.prefix}vcmute <member> [duration] [reason]` — Server-mute a member in voice channels. Duration supports e.g. `5m`, `10s`, `2h` or indefinite. Auto-unmutes after duration.\n"
                f"• `{self.prefix}vcunmute <member> [reason]` — Server-unmute a member in voice channels.\n"
                f"• `{self.prefix}history <user>` (aliases: `modhistory`, `crimes`) — View a member's past moderation history/records.\n"
                f"• `{self.prefix}warn <member> [reason]` — Issue a warning to a member.\n"
                f"• `{self.prefix}warns <member>` — List recent warnings issued to a member.\n"
                f"• `{self.prefix}purge <limit>` — Delete a number of messages from the current channel (1-100).\n"
                f"• `{self.prefix}lock` / `{self.prefix}unlock` — Lock or unlock sending messages in a channel.\n"
                f"• `{self.prefix}hide` / `{self.prefix}unhide` — Hide or unhide a channel from `@everyone`.\n"
                f"• `{self.prefix}slowmode <seconds>` — Set message cooldown for the channel.\n"
                f"• `{self.prefix}role <member> <role_name>` — Toggle role for a user (gives if missing, removes if owned).\n"
                f"• `{self.prefix}role_manage add/remove <member> <role>` — Add or remove a role directly.\n"
                f"• `{self.prefix}nickname <member> [new_name]` — Change a member's nickname.\n"
                f"• `{self.prefix}modlog set-channel/clear-channel` — Set or clear the channel where moderation actions are logged.\n\n"
                "🛡️ *Requires appropriate moderator/administrator permissions to run.*"
            )
        elif category == "utility":
            embed.title = "🧰 Utility & Server"
            embed.description = (
                f"• `{self.prefix}ping` — Check the bot's response latency.\n"
                f"• `{self.prefix}uptime` — View how long the bot has been online.\n"
                f"• `{self.prefix}serverinfo` (or `si`) — Display server owner, creation date, boosts, etc.\n"
                f"• `{self.prefix}userinfo` (or `ui`) — View details about a user's account, joined dates, and roles.\n"
                f"• `{self.prefix}roleinfo <role>` — Display details of a server role (color, permissions, members).\n"
                f"• `{self.prefix}membercount` — View current server member count.\n"
                f"• `{self.prefix}avatar [user]` (or `av` / `pfp`) — View user profile avatar.\n"
                f"• `{self.prefix}banner [user]` (or `bnr`) — View user profile banner image.\n"
                f"• `{self.prefix}gif <query>` (aliases: `searchgif`, `search_gif`) — Search Giphy & Tenor keyless for a matching GIF.\n"
                f"• `{self.prefix}weather <location>` — Get current weather conditions.\n"
                f"• `{self.prefix}translate <text> [lang]` — Translate text (defaults to English).\n"
                f"• `{self.prefix}poll <question> [choices]` — Create a standard thumbs up/down poll or custom multi-choice poll.\n"
                f"• `{self.prefix}remind <duration> <message>` — Set a reminder (e.g. `10m`, `2h`).\n"
                f"• `{self.prefix}calculator <expression>` — Safe math expression evaluator.\n"
                f"• `{self.prefix}afk [message]` — Set your status to AFK (automatically replies when you are mentioned)."
            )
        elif category == "admin":
            embed.title = "⚙️ Configuration"
            embed.description = (
                f"• `{self.prefix}setprefix <new_prefix>` — Change the prefix for this server.\n"
                f"• `{self.prefix}config_view` — View all configuration settings configured for this server.\n"
                f"• `{self.prefix}config_set <key> <value>` — Modify a server setting key (e.g. modlog).\n"
                f"• `{self.prefix}config_reset` — Reset server configurations back to default settings.\n"
                f"• `{self.prefix}set-reward <level> <role>` — Configure a role reward given on reaching a level.\n"
                f"• `{self.prefix}clear-reward <level>` — Remove a role reward configured for a level.\n"
                f"• `{self.prefix}set-xp <amount>` — Configure base XP gained per message.\n"
                f"• `{self.prefix}set-xp-cooldown <seconds>` — Configure cooldown between gaining XP.\n"
                f"• `{self.prefix}prefixless_grant <member>` — *(Owner only)* Grant a user permission to use commands without a prefix.\n"
                f"• `{self.prefix}prefixless_revoke <member>` — *(Owner only)* Revoke prefix-less command permissions.\n"
                f"• `{self.prefix}prefixless_list` — *(Owner only)* List all users with prefix-less permissions."
            )

        owner = getattr(self.bot, "owner_user", None)
        owner_text = f"Created & owned by {owner.name}" if owner else "Your server companion"
        embed.set_footer(text=f"{owner_text} • Select another category below")
        await interaction.response.edit_message(embed=embed, view=self.view)


async def setup(bot):
    await bot.add_cog(Example(bot))
