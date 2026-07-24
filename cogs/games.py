import logging
import random
from typing import Optional, List
import discord
from discord import app_commands, Interaction
from discord.ext import commands

from utils.economy import get_balance, add_wallet

logger = logging.getLogger(__name__)

SUITS = ["♠️", "♥️", "♦️", "♣️"]
RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]

def draw_card() -> str:
    return f"{random.choice(RANKS)}{random.choice(SUITS)}"

def get_card_value(card: str) -> int:
    # Handle 10 which has 2 characters for rank
    rank = card[:-2]
    if rank in ("J", "Q", "K"):
        return 10
    if rank == "A":
        return 11
    return int(rank)

def calculate_hand(hand: List[str]) -> int:
    val = sum(get_card_value(c) for c in hand)
    aces = sum(1 for c in hand if c.startswith("A"))
    while val > 21 and aces:
        val -= 10
        aces -= 1
    return val


class BlackjackView(discord.ui.View):
    def __init__(self, bot: commands.Bot, user_id: int, bet: int):
        super().__init__(timeout=60)
        self.bot = bot
        self.user_id = user_id
        self.bet = bet
        
        # Initialize deck and hands
        self.deck = []
        self.player_hand = [draw_card(), draw_card()]
        self.dealer_hand = [draw_card(), draw_card()]

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This Blackjack game is not yours! Start one with `/blackjack`.", ephemeral=True)
            return False
        return True

    def make_embed(self, show_dealer: bool = False, status: str = None) -> discord.Embed:
        embed = discord.Embed(
            title="🃏 Blackjack Table",
            color=discord.Color.dark_green()
        )
        
        p_val = calculate_hand(self.player_hand)
        p_cards = ", ".join(f"`{c}`" for c in self.player_hand)
        embed.add_field(name="👤 Your Hand", value=f"Cards: {p_cards}\nValue: **{p_val}**", inline=True)
        
        if show_dealer:
            d_val = calculate_hand(self.dealer_hand)
            d_cards = ", ".join(f"`{c}`" for c in self.dealer_hand)
            embed.add_field(name="🕵️ Dealer Hand", value=f"Cards: {d_cards}\nValue: **{d_val}**", inline=True)
        else:
            # Hide the dealer's second card
            d_cards = f"`{self.dealer_hand[0]}` and `?`"
            first_val = get_card_value(self.dealer_hand[0])
            embed.add_field(name="🕵️ Dealer Hand", value=f"Cards: {d_cards}\nValue: **{first_val}**", inline=True)

        embed.add_field(name="💰 Wager", value=f"**${self.bet}** coins", inline=False)
        
        if status:
            embed.description = status
            
        owner = self.bot.owner_user if hasattr(self.bot, "owner_user") else None
        if owner:
            embed.set_footer(text=f"Created & Owned by {owner.name}", icon_url=owner.avatar.url if owner.avatar else None)
        else:
            embed.set_footer(text="Owned by Bot Owner")
            
        return embed

    @discord.ui.button(label="Hit 🃏", style=discord.ButtonStyle.primary)
    async def hit(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.player_hand.append(draw_card())
        val = calculate_hand(self.player_hand)
        
        if val > 21:
            # Bust!
            self.stop()
            embed = self.make_embed(show_dealer=True, status="💥 **You busted!** The dealer wins. You lost your bet.")
            await interaction.response.edit_message(embed=embed, view=None)
        elif val == 21:
            # Stop and play dealer
            await self.stand_logic(interaction)
        else:
            embed = self.make_embed()
            await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Stand 🛑", style=discord.ButtonStyle.secondary)
    async def stand(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.stand_logic(interaction)

    async def stand_logic(self, interaction: discord.Interaction):
        self.stop()
        
        # Dealer plays (must hit until 17 or higher)
        while calculate_hand(self.dealer_hand) < 17:
            self.dealer_hand.append(draw_card())
            
        p_val = calculate_hand(self.player_hand)
        d_val = calculate_hand(self.dealer_hand)
        
        status = ""
        if d_val > 21:
            status = "🎉 **Dealer busted! You win!**"
            await add_wallet(self.user_id, self.bet * 2)
        elif p_val > d_val:
            status = f"🎉 **You win!** **{p_val}** beats **{d_val}**."
            await add_wallet(self.user_id, self.bet * 2)
        elif p_val < d_val:
            status = f"😔 **Dealer wins!** **{d_val}** beats **{p_val}**."
        else:
            status = "🤝 **Push!** It's a draw, your bet has been returned."
            await add_wallet(self.user_id, self.bet)
            
        embed = self.make_embed(show_dealer=True, status=status)
        await interaction.response.edit_message(embed=embed, view=None)


class Games(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="coinflip")
    @commands.guild_only()
    async def coinflip(self, ctx: commands.Context, choice: str, bet: int):
        """Bet on a 50/50 coinflip! choice must be 'heads' or 'tails'"""
        choice = choice.lower().strip()
        if choice not in ("heads", "tails", "head", "tail"):
            await ctx.send("Invalid choice! Choose `heads` or `tails`.", ephemeral=True)
            return
            
        if choice == "head":
            choice = "heads"
        if choice == "tail":
            choice = "tails"
            
        if bet <= 0:
            await ctx.send("Bet must be a positive integer.", ephemeral=True)
            return
            
        w, b = await get_balance(ctx.author.id)
        if w < bet:
            await ctx.send(f"You don't have enough coins in your wallet! Balance: **${w}**", ephemeral=True)
            return
            
        # Subtract bet first
        await add_wallet(ctx.author.id, -bet)
        
        result = random.choice(["heads", "tails"])
        embed = discord.Embed(title="🪙 Coinflip Result", color=discord.Color.gold())
        
        if result == choice:
            await add_wallet(ctx.author.id, bet * 2)
            embed.description = f"The coin landed on **{result}**!\n\n🎉 **You won ${bet} coins!**"
            embed.color = discord.Color.green()
        else:
            embed.description = f"The coin landed on **{result}**!\n\n😔 **You lost ${bet} coins.**"
            embed.color = discord.Color.red()
            
        owner = self.bot.owner_user if hasattr(self.bot, "owner_user") else None
        if owner:
            embed.set_footer(text=f"Created & Owned by {owner.name}", icon_url=owner.avatar.url if owner.avatar else None)
        else:
            embed.set_footer(text="Owned by Bot Owner")
            
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="slots")
    @commands.guild_only()
    async def slots(self, ctx: commands.Context, bet: int):
        """Bet on a premium three-reel slot machine!"""
        if bet <= 0:
            await ctx.send("Bet must be a positive integer.", ephemeral=True)
            return
            
        w, b = await get_balance(ctx.author.id)
        if w < bet:
            await ctx.send(f"You don't have enough coins in your wallet! Balance: **${w}**", ephemeral=True)
            return
            
        await add_wallet(ctx.author.id, -bet)
        
        emojis = ["🍒", "🍋", "🍇", "💎", "⭐"]
        reel = [random.choice(emojis) for _ in range(3)]
        
        # Calculate payout
        payout = 0
        status = ""
        
        if reel[0] == reel[1] == reel[2]:
            if reel[0] == "💎":
                payout = bet * 10
                status = "🎰 **JACKPOT! 10x payout!** 💎"
            else:
                payout = bet * 5
                status = "🎉 **Three of a kind! 5x payout!** 🎉"
        elif reel[0] == reel[1] or reel[1] == reel[2] or reel[0] == reel[2]:
            payout = bet * 2
            status = "✨ **Two of a kind! 2x payout!** ✨"
        else:
            status = "😔 **No match! Better luck next time.**"
            
        if payout > 0:
            await add_wallet(ctx.author.id, payout)
            
        embed = discord.Embed(
            title="🎰 Slot Machine",
            description=f"**[ {reel[0]} | {reel[1]} | {reel[2]} ]**\n\n{status}",
            color=discord.Color.green() if payout > 0 else discord.Color.red()
        )
        
        owner = self.bot.owner_user if hasattr(self.bot, "owner_user") else None
        if owner:
            embed.set_footer(text=f"Created & Owned by {owner.name}", icon_url=owner.avatar.url if owner.avatar else None)
        else:
            embed.set_footer(text="Owned by Bot Owner")
            
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="blackjack", aliases=["bj"])
    @commands.guild_only()
    async def blackjack(self, ctx: commands.Context, bet: int):
        """Play a fully interactive game of Blackjack against the dealer!"""
        if bet <= 0:
            await ctx.send("Bet must be a positive integer.", ephemeral=True)
            return
            
        w, b = await get_balance(ctx.author.id)
        if w < bet:
            await ctx.send(f"You don't have enough coins in your wallet! Balance: **${w}**", ephemeral=True)
            return
            
        await add_wallet(ctx.author.id, -bet)
        
        view = BlackjackView(self.bot, ctx.author.id, bet)
        
        # Check for natural blackjack
        p_val = calculate_hand(view.player_hand)
        if p_val == 21:
            await add_wallet(ctx.author.id, int(bet * 2.5))
            embed = view.make_embed(show_dealer=True, status="🃏 **Natural Blackjack!** You won 2.5x your bet!")
            await ctx.send(embed=embed)
            return
            
        embed = view.make_embed()
        await ctx.send(embed=embed, view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(Games(bot))
