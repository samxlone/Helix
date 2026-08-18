import logging
from typing import Optional
from discord import app_commands
from discord.ext import commands
import discord

from utils.economy import (
    get_balance, claim_daily, transfer, do_work, deposit_to_bank,
    withdraw_from_bank, rob, add_wallet, get_networth_leaderboard, get_user_networth_rank, reset_work_cooldown
)
from utils.inventory import get_inventory, remove_item
from utils.shop import list_items, buy_item, get_item


logger = logging.getLogger(__name__)


class LeaderboardSelect(discord.ui.Select):
    def __init__(self, bot, caller_id: int):
        options = [
            discord.SelectOption(label="Top 10 Candidates", value="10", emoji="🏆", description="View top 10 richest server members"),
            discord.SelectOption(label="Top 30 Candidates", value="30", emoji="🥇", description="View top 30 richest server members"),
            discord.SelectOption(label="Top 50 Candidates", value="50", emoji="🥈", description="View top 50 richest server members"),
            discord.SelectOption(label="Top 100 Candidates", value="100", emoji="🥉", description="View top 100 richest server members"),
        ]
        super().__init__(placeholder="Select leaderboard range...", min_values=1, max_values=1, options=options)
        self.bot = bot
        self.caller_id = caller_id

    async def callback(self, interaction: discord.Interaction):
        limit = int(self.values[0])
        leaderboard_data = await get_networth_leaderboard(limit=limit)
        caller_rank, caller_networth = await get_user_networth_rank(self.caller_id)

        medals = {1: "🥇", 2: "🥈", 3: "🥉"}

        lines = []
        for i, item in enumerate(leaderboard_data, start=1):
            uid = item["user_id"]
            nw = item["networth"]
            medal = medals.get(i, f"`#{i}`")
            user_obj = self.bot.get_user(uid)
            user_name = user_obj.display_name if user_obj else f"<@{uid}>"
            lines.append(f"{medal} **{user_name}** — **${nw:,}**")

        description_text = "\n".join(lines[:limit]) if lines else "No economy data available yet."
        if len(description_text) > 3900:
            description_text = description_text[:3850] + "\n*...list truncated for length*"

        embed = discord.Embed(
            title=f"💰 Economy Net Worth Leaderboard (Top {limit})",
            description=description_text,
            color=discord.Color.gold()
        )

        embed.add_field(
            name="📌 Your Server Rank",
            value=f"Position: **#{caller_rank:,}** • Net Worth: **${caller_networth:,}**",
            inline=False
        )
        embed.set_footer(text=f"Requested by {interaction.user.display_name}")
        await interaction.response.edit_message(embed=embed, view=self.view)


class LeaderboardView(discord.ui.View):
    def __init__(self, bot, caller_id: int):
        super().__init__(timeout=180)
        self.add_item(LeaderboardSelect(bot, caller_id=caller_id))


class ShopSelect(discord.ui.Select):
    def __init__(self, caller_id: int):
        options = [
            discord.SelectOption(label="All Categories", value="all", emoji="🌐", description="View all available market items"),
            discord.SelectOption(label="Protection & Shields", value="Protection", emoji="🛡️", description="Robbery shields & bank insurance"),
            discord.SelectOption(label="Boosters & Utilities", value="Boosters", emoji="⚡", description="Energy drinks & XP potions"),
            discord.SelectOption(label="RPG Gear", value="RPG Gear", emoji="⚔️", description="Potions, elixirs & weapons"),
            discord.SelectOption(label="Collectibles & Flex", value="Collectibles", emoji="💎", description="Gems, trophies & crowns"),
        ]
        super().__init__(placeholder="Filter shop by category...", min_values=1, max_values=1, options=options)
        self.caller_id = caller_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.caller_id:
            await interaction.response.send_message("❌ Only the command invoker can use this dropdown.", ephemeral=True)
            return

        cat = self.values[0]
        items = list_items(None if cat == "all" else cat)
        wallet, bank = await get_balance(interaction.user.id)

        embed = discord.Embed(
            title="🛍️ Helix Marketplace",
            color=discord.Color.from_rgb(255, 183, 3)
        )
        embed.set_author(
            name=f"{interaction.user.display_name}'s Market View • Wallet: ${wallet:,} | Bank: ${bank:,}",
            icon_url=interaction.user.display_avatar.url
        )

        categories = {}
        for it in items:
            c = it.get("category", "General")
            categories.setdefault(c, []).append(it)

        for c_name, c_items in categories.items():
            lines = []
            for it in c_items:
                lines.append(
                    f"{it.get('emoji', '📦')} **{it['name']}** (`{it['key']}`) — **${it['price']:,} coins**\n"
                    f"> *{it.get('description', 'No description')}*"
                )
            embed.add_field(name=f"📦 {c_name}", value="\n\n".join(lines), inline=False)

        embed.set_footer(text="Use !buy <item_id> [amount] to purchase an item")
        await interaction.response.edit_message(embed=embed)


class ShopView(discord.ui.View):
    def __init__(self, caller_id: int):
        super().__init__(timeout=180)
        self.add_item(ShopSelect(caller_id))


class EconomyCog(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="balance", aliases=["bal", "profile", "networth"])
    @commands.guild_only()
    async def balance(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        """Check your or another member's VIP banking profile & balance card."""
        user = member or ctx.author
        w, b = await get_balance(user.id)

        from utils.leveling import get_level_info
        level, xp = await get_level_info(user.id)

        from services.image_card import generate_profile_card

        avatar_url = user.display_avatar.url if hasattr(user, "display_avatar") else None
        username_str = getattr(user, "name", user.display_name)
        buf = generate_profile_card(
            display_name=user.display_name,
            username=username_str,
            avatar_url=avatar_url,
            wallet=w,
            bank=b,
            level=level,
            xp=xp,
        )

        from utils.embed_utils import HELIX_COLOR, set_owner_footer
        file = discord.File(fp=buf, filename="profile_card.png")

        embed = discord.Embed(color=HELIX_COLOR)
        embed.set_image(url="attachment://profile_card.png")
        set_owner_footer(embed, self.bot, extra_text=f"Requested by {ctx.author.display_name}")

        await ctx.send(embed=embed, file=file)

    @commands.hybrid_command(name="daily")
    @commands.guild_only()
    async def daily(self, ctx: commands.Context):
        """Claim your daily reward"""
        claimed, new_wallet = await claim_daily(ctx.author.id)
        if not claimed:
            await ctx.send("⏳ You have already claimed your daily reward today. Come back tomorrow!", ephemeral=True)
            return
        await ctx.send(f"💎 **Daily Reward Claimed!** Added funds to your wallet. Balance: **${new_wallet:,}**")

    @commands.hybrid_command(name="pay")
    @commands.guild_only()
    async def pay(self, ctx: commands.Context, target: discord.Member, amount: int):
        """Pay another member from your wallet"""
        if amount <= 0:
            await ctx.send("❌ Amount must be greater than zero.", ephemeral=True)
            return
        ok = await transfer(ctx.author.id, target.id, amount)
        if not ok:
            await ctx.send("❌ Transfer failed. Check your wallet balance.", ephemeral=True)
            return
        await ctx.send(f"💸 **Payment Sent:** Transferred **${amount:,}** to {target.mention}.")

    @commands.hybrid_command(name="work")
    @commands.guild_only()
    async def work(self, ctx: commands.Context):
        """Perform work to earn money"""
        ok, new_wallet = await do_work(ctx.author.id)
        if not ok:
            await ctx.send("⏳ You are currently on shift cooldown. Try again in a few minutes.", ephemeral=True)
            return
        await ctx.send(f"💼 **Shift Finished!** You completed your work. Wallet Balance: **${new_wallet:,}**")

    @commands.hybrid_command(name="deposit", aliases=["dep", "deposite"])
    @commands.guild_only()
    async def deposit(self, ctx: commands.Context, amount: str):
        """Deposit money from your wallet to your bank (supports 'all' or specific amount)"""
        w, b = await get_balance(ctx.author.id)
        amt_str = str(amount).strip().lower()
        if amt_str == "all":
            dep_amount = w
        else:
            try:
                dep_amount = int(amt_str)
            except ValueError:
                await ctx.send("❌ Invalid amount. Use a positive number or 'all'.", ephemeral=True)
                return

        if dep_amount <= 0:
            await ctx.send("❌ Amount must be positive.", ephemeral=True)
            return

        ok = await deposit_to_bank(ctx.author.id, dep_amount)
        if not ok:
            await ctx.send("❌ Deposit failed (insufficient wallet funds).", ephemeral=True)
            return
        await ctx.send(f"🏦 **Bank Vault Updated:** Deposited **${dep_amount:,}** into your secure account.")

    @commands.hybrid_command(name="withdraw", aliases=["with"])
    @commands.guild_only()
    async def withdraw(self, ctx: commands.Context, amount: str):
        """Withdraw money from your bank to your wallet (supports 'all' or specific amount)"""
        w, b = await get_balance(ctx.author.id)
        amt_str = str(amount).strip().lower()
        if amt_str == "all":
            with_amount = b
        else:
            try:
                with_amount = int(amt_str)
            except ValueError:
                await ctx.send("❌ Invalid amount. Use a positive number or 'all'.", ephemeral=True)
                return

        if with_amount <= 0:
            await ctx.send("❌ Amount must be positive.", ephemeral=True)
            return

        ok = await withdraw_from_bank(ctx.author.id, with_amount)
        if not ok:
            await ctx.send("❌ Withdrawal failed (insufficient bank balance).", ephemeral=True)
            return
        await ctx.send(f"🪙 **Cash Withdrawn:** Withdrew **${with_amount:,}** from your bank vault.")

    @commands.hybrid_command(name="inventory", aliases=["inv"])
    @commands.guild_only()
    async def inventory(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        """Check your or another member's inventory"""
        user = member or ctx.author
        inv = await get_inventory(user.id)

        embed = discord.Embed(
            title=f"🎒 Inventory of {user.display_name}",
            color=discord.Color.from_rgb(0, 180, 216)
        )
        embed.set_thumbnail(url=user.display_avatar.url)

        if not inv:
            embed.description = "Your inventory is currently empty!\nUse `!shop` to browse and purchase items."
            await ctx.send(embed=embed)
            return

        fields_data = []
        total_items = 0
        for i in inv:
            key = i["item_key"]
            amount = i["amount"]
            total_items += amount
            item_info = get_item(key)
            emoji = item_info.get("emoji", "📦") if item_info else "📦"
            name = item_info.get("name", key.capitalize()) if item_info else key.capitalize()
            desc = item_info.get("description", "") if item_info else ""
            price = item_info.get("price", 0) if item_info else 0
            val_text = f" (${price * amount:,} coins)" if price else ""

            fields_data.append(
                f"{emoji} **{name}** (`{key}`) x**{amount}**{val_text}\n"
                f"> *{desc}*"
            )

        embed.description = f"Total Items: **{total_items}**\n\n" + "\n\n".join(fields_data)
        embed.set_footer(text="Use !use <item_id> to consume items or !shop to buy more!")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="shop")
    @commands.guild_only()
    async def shop(self, ctx: commands.Context):
        """View the shop items marketplace with categories and prices"""
        items = list_items()
        wallet, bank = await get_balance(ctx.author.id)

        embed = discord.Embed(
            title="🛍️ Helix Marketplace",
            color=discord.Color.from_rgb(255, 183, 3)
        )
        embed.set_author(
            name=f"{ctx.author.display_name}'s Market View • Wallet: ${wallet:,} | Bank: ${bank:,}",
            icon_url=ctx.author.display_avatar.url
        )

        categories = {}
        for it in items:
            c = it.get("category", "General")
            categories.setdefault(c, []).append(it)

        for c_name, c_items in categories.items():
            lines = []
            for it in c_items:
                lines.append(
                    f"{it.get('emoji', '📦')} **{it['name']}** (`{it['key']}`) — **${it['price']:,} coins**\n"
                    f"> *{it.get('description', 'No description')}*"
                )
            embed.add_field(name=f"📦 {c_name}", value="\n\n".join(lines), inline=False)

        embed.set_footer(text="Use !buy <item_id> [amount] to purchase an item")
        view = ShopView(caller_id=ctx.author.id)
        await ctx.send(embed=embed, view=view)

    @commands.hybrid_command(name="buy")
    @commands.guild_only()
    async def buy(self, ctx: commands.Context, item_key: str, amount: int = 1):
        """Buy an item from the shop"""
        if amount <= 0:
            await ctx.send("❌ Amount must be positive.", ephemeral=True)
            return
        item = get_item(item_key)
        if not item:
            await ctx.send(f"❌ Item `{item_key}` not found in shop. Type `!shop` to view available items.", ephemeral=True)
            return

        total_price = item["price"] * amount
        ok = await buy_item(ctx.author.id, item_key, amount)
        if not ok:
            wallet, bank = await get_balance(ctx.author.id)
            await ctx.send(
                f"❌ Purchase failed! You need **${total_price:,} coins** in your wallet (You currently have **${wallet:,}**).",
                ephemeral=True
            )
            return

        wallet, bank = await get_balance(ctx.author.id)
        embed = discord.Embed(
            title="🛍️ Purchase Successful!",
            description=f"Bought **{amount}x {item.get('emoji', '📦')} {item['name']}** for **${total_price:,} coins**!",
            color=discord.Color.green()
        )
        embed.set_footer(text=f"Remaining Wallet Balance: ${wallet:,} • Check !inventory")
        await ctx.send(embed=embed)

    @commands.command(name="use")
    @commands.guild_only()
    async def use(self, ctx: commands.Context, item_key: str):

        """Use or consume an item from your inventory"""
        key = item_key.lower()
        item = get_item(key)
        if not item:
            await ctx.send(f"❌ Unknown item `{item_key}`. Check `!inventory` for your items.", ephemeral=True)
            return

        if key == "coffee":
            ok = await remove_item(ctx.author.id, key, 1)
            if not ok:
                await ctx.send("❌ You don't have an **Energy Drink** (`coffee`) in your inventory!", ephemeral=True)
                return
            await reset_work_cooldown(ctx.author.id)
            embed = discord.Embed(
                title="☕ Energy Boost!",
                description=f"You drank an **Energy Drink**! Your `!work` cooldown has been **reset**!\nYou can work again immediately using `!work`.",
                color=discord.Color.gold()
            )
            await ctx.send(embed=embed)

        elif key == "shield":
            inv = await get_inventory(ctx.author.id)
            shield_item = next((i for i in inv if i["item_key"] == "shield"), None)
            if not shield_item or shield_item["amount"] <= 0:
                await ctx.send("❌ You don't have a **Robbery Shield** (`shield`) in your inventory!", ephemeral=True)
                return
            embed = discord.Embed(
                title="🛡️ Robbery Shield Active",
                description=f"Your **Robbery Shield** (x{shield_item['amount']}) is active in your inventory!\nIt will automatically block the next robbery attempt against your wallet.",
                color=discord.Color.blue()
            )
            await ctx.send(embed=embed)

        elif key in ("potion", "elixir"):
            ok = await remove_item(ctx.author.id, key, 1)
            if not ok:
                await ctx.send(f"❌ You don't have a **{item['name']}** (`{key}`) in your inventory!", ephemeral=True)
                return
            heal = item.get("metadata", {}).get("heal", 50)
            embed = discord.Embed(
                title=f"{item.get('emoji', '🍷')} Consumed {item['name']}",
                description=f"You consumed a **{item['name']}** and restored **+{heal} HP/Mana**!",
                color=discord.Color.green()
            )
            await ctx.send(embed=embed)
        else:
            await ctx.send(f"ℹ️ **{item['name']}** (`{key}`) is a passive collectible or gear. It stays in your inventory!", ephemeral=True)

    @commands.hybrid_command(name="rob")
    @commands.guild_only()
    async def rob(self, ctx: commands.Context, target: discord.Member):
        """Rob another member's wallet"""
        if ctx.author.id == target.id:
            await ctx.send("❌ You cannot rob yourself.", ephemeral=True)
            return
        if target.bot:
            await ctx.send("❌ You cannot rob a bot.", ephemeral=True)
            return

        success, stolen = await rob(ctx.author.id, target.id)
        if stolen == -1:
            embed = discord.Embed(
                title="🛡️ Robbery Blocked!",
                description=f"{target.mention}'s **Robbery Shield** absorbed your robbery attempt!\nTheir shield was consumed, protecting their wallet.",
                color=discord.Color.blue()
            )
            await ctx.send(embed=embed)
            return

        if not success:
            await ctx.send("❌ Robbery failed or you are on cooldown (10 minutes).", ephemeral=True)
            return

        embed = discord.Embed(
            title="🥷 Successful Robbery!",
            description=f"You robbed {target.mention} and escaped with **${stolen:,} coins**!",
            color=discord.Color.gold()
        )
        await ctx.send(embed=embed)


    @commands.command(name="addmoney", aliases=["addbalance"])
    @commands.guild_only()
    async def addmoney(self, ctx: commands.Context, member: discord.Member, amount: int):

        """Add coins to a member's wallet (Bot/Server Owner only)"""
        is_allowed = ctx.author.id == ctx.guild.owner_id
        if not is_allowed:
            is_owner = await self.bot.is_owner(ctx.author)
            if is_owner:
                is_allowed = True

        if not is_allowed:
            await ctx.send("Only the server owner or bot owner can add money.", ephemeral=True)
            return

        if amount == 0:
            await ctx.send("Amount cannot be zero.", ephemeral=True)
            return

        try:
            new_wallet = await add_wallet(member.id, amount)
            action = "Added" if amount > 0 else "Removed"
            abs_amount = abs(amount)
            await ctx.send(f"💸 {action} **${abs_amount}** coins to {member.mention}'s wallet! New wallet balance: **${new_wallet}**.")
        except Exception as e:
            logger.exception("Failed to add money: %s", e)
            await ctx.send("Failed to modify balance.", ephemeral=True)

    @commands.hybrid_command(name="leaderboard", aliases=["lb", "top", "rich", "baltop", "balancetop", "wealth"])

    @commands.guild_only()
    async def leaderboard(self, ctx: commands.Context):
        """Displays the Economy Net Worth Leaderboard with top candidates and user rank."""
        leaderboard_data = await get_networth_leaderboard(limit=5)
        caller_rank, caller_networth = await get_user_networth_rank(ctx.author.id)

        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        lines = []
        for i, item in enumerate(leaderboard_data, start=1):
            uid = item["user_id"]
            nw = item["networth"]
            wallet = item["wallet"]
            bank = item["bank"]
            medal = medals.get(i, f"`#{i}`")

            user_obj = self.bot.get_user(uid)
            user_name = user_obj.display_name if user_obj else f"<@{uid}>"
            lines.append(f"{medal} **{user_name}** — **${nw:,}** *(Wallet: ${wallet:,} | Bank: ${bank:,})*")

        desc_text = "\n".join(lines) if lines else "No economy data recorded yet."

        embed = discord.Embed(
            title="💰 Economy Net Worth Leaderboard",
            description=desc_text,
            color=discord.Color.gold()
        )
        if ctx.guild and ctx.guild.icon:
            embed.set_thumbnail(url=ctx.guild.icon.url)

        embed.add_field(
            name="📌 Your Server Rank",
            value=f"Position: **#{caller_rank:,}** • Net Worth: **${caller_networth:,}**",
            inline=False
        )
        embed.set_footer(text=f"Requested by {ctx.author.display_name} • Select dropdown below for Top 10-100")

        view = LeaderboardView(self.bot, caller_id=ctx.author.id)
        await ctx.send(embed=embed, view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(EconomyCog(bot))

