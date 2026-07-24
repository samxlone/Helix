import logging
from typing import Optional
from discord import app_commands
from discord.ext import commands
import discord

from utils.economy import get_balance, claim_daily, transfer, do_work, deposit_to_bank, withdraw_from_bank, rob, add_wallet
from utils.inventory import get_inventory
from utils.shop import list_items, buy_item, get_item

logger = logging.getLogger(__name__)


class EconomyCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="balance", aliases=["bal"])
    @commands.guild_only()
    async def balance(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        """Check your or another member's balance"""
        user = member or ctx.author
        w, b = await get_balance(user.id)
        await ctx.send(f"{user.mention} — Wallet: {w} • Bank: {b}")

    @commands.hybrid_command(name="daily")
    @commands.guild_only()
    async def daily(self, ctx: commands.Context):
        """Claim your daily reward"""
        claimed, new_wallet = await claim_daily(ctx.author.id)
        if not claimed:
            await ctx.send("You have already claimed your daily reward. Try later.", ephemeral=True)
            return
        await ctx.send(f"You claimed your daily reward! Wallet now: {new_wallet}")

    @commands.hybrid_command(name="pay")
    @commands.guild_only()
    async def pay(self, ctx: commands.Context, target: discord.Member, amount: int):
        """Pay another member from your wallet"""
        if amount <= 0:
            await ctx.send("Amount must be positive.", ephemeral=True)
            return
        ok = await transfer(ctx.author.id, target.id, amount)
        if not ok:
            await ctx.send("Transfer failed (insufficient funds?).", ephemeral=True)
            return
        await ctx.send(f"Transferred {amount} to {target.mention}.")

    @commands.hybrid_command(name="work")
    @commands.guild_only()
    async def work(self, ctx: commands.Context):
        """Perform work to earn money"""
        ok, new_wallet = await do_work(ctx.author.id)
        if not ok:
            await ctx.send("You are on cooldown for work. Try later.", ephemeral=True)
            return
        await ctx.send(f"You worked and earned money! Wallet now: {new_wallet}")

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
            await ctx.send("❌ Deposit failed (insufficient wallet funds?).", ephemeral=True)
            return
        await ctx.send(f"✅ Deposited {dep_amount} to your bank.")

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
            await ctx.send("❌ Withdraw failed (insufficient bank funds?).", ephemeral=True)
            return
        await ctx.send(f"✅ Withdrew {with_amount} to your wallet.")

    @commands.hybrid_command(name="inventory", aliases=["inv"])
    @commands.guild_only()
    async def inventory(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        """Check your or another member's inventory"""
        user = member or ctx.author
        inv = await get_inventory(user.id)
        if not inv:
            await ctx.send(f"{user.mention} has an empty inventory.")
            return
        lines = [f"{i['item_key']} x{i['amount']}" for i in inv]
        await ctx.send(f"Inventory for {user.mention}:\n" + "\n".join(lines))

    @commands.hybrid_command(name="shop")
    @commands.guild_only()
    async def shop(self, ctx: commands.Context):
        """View the shop items"""
        items = list_items()
        lines = [f"{it['key']}: {it['name']} — {it['price']} coins" for it in items]
        await ctx.send("Shop items:\n" + "\n".join(lines))

    @commands.hybrid_command(name="buy")
    @commands.guild_only()
    async def buy(self, ctx: commands.Context, item_key: str, amount: int = 1):
        """Buy an item from the shop"""
        if amount <= 0:
            await ctx.send("Amount must be positive.", ephemeral=True)
            return
        item = get_item(item_key)
        if not item:
            await ctx.send("No such item in the shop.", ephemeral=True)
            return
        ok = await buy_item(ctx.author.id, item_key, amount)
        if not ok:
            await ctx.send("Purchase failed (insufficient funds?).", ephemeral=True)
            return
        await ctx.send(f"Bought {amount}x {item['name']}.")

    @commands.hybrid_command(name="rob")
    @commands.guild_only()
    async def rob(self, ctx: commands.Context, target: discord.Member):
        """Rob another member's wallet"""
        if ctx.author.id == target.id:
            await ctx.send("You cannot rob yourself.", ephemeral=True)
            return
        success, stolen = await rob(ctx.author.id, target.id)
        if not success:
            await ctx.send("Rob failed or you are on cooldown.", ephemeral=True)
            return
        await ctx.send(f"You robbed {target.mention} and got {stolen} coins!")

    @commands.hybrid_command(name="addmoney", aliases=["addbalance"])
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


async def setup(bot: commands.Bot):
    await bot.add_cog(EconomyCog(bot))
