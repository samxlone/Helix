import asyncio
import html
import logging
import random
from typing import Optional, List, Dict, Tuple
import discord
from discord import app_commands, Interaction
from discord.ext import commands

from utils.economy import get_balance, add_wallet
from utils.embed_utils import set_owner_footer

logger = logging.getLogger(__name__)

# ==============================================================================
# CARD HELPERS (Blackjack & HighLow)
# ==============================================================================
SUITS = ["♠️", "♥️", "♦️", "♣️"]
RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
RANK_VALUES = {
    "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8, "9": 9,
    "10": 10, "J": 11, "Q": 12, "K": 13, "A": 14
}

def draw_card() -> Tuple[str, str, int]:
    rank = random.choice(RANKS)
    suit = random.choice(SUITS)
    return rank, suit, RANK_VALUES[rank]

def get_blackjack_card_value(rank: str) -> int:
    if rank in ("J", "Q", "K"):
        return 10
    if rank == "A":
        return 11
    return int(rank)

def calculate_blackjack_hand(hand: List[Tuple[str, str, int]]) -> int:
    val = sum(get_blackjack_card_value(c[0]) for c in hand)
    aces = sum(1 for c in hand if c[0] == "A")
    while val > 21 and aces:
        val -= 10
        aces -= 1
    return val


# ==============================================================================
# 1. BLACKJACK VIEW
# ==============================================================================
class BlackjackView(discord.ui.View):
    def __init__(self, bot: commands.Bot, user_id: int, bet: int):
        super().__init__(timeout=180)
        self.bot = bot
        self.user_id = user_id
        self.bet = bet
        self.player_hand: List[Tuple[str, str, int]] = [draw_card(), draw_card()]
        self.dealer_hand: List[Tuple[str, str, int]] = [draw_card(), draw_card()]

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item) -> None:
        logger.exception("BlackjackView error on %s: %s", item, error)
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ An error occurred in this Blackjack round.", ephemeral=True)
            else:
                await interaction.followup.send("❌ An error occurred in this Blackjack round.", ephemeral=True)
        except Exception:
            pass

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This Blackjack game belongs to someone else.", ephemeral=True)
            return False
        return True

    def make_embed(self, show_dealer: bool = False, status: str = None) -> discord.Embed:
        embed = discord.Embed(
            title="🃏 Blackjack Table",
            color=discord.Color.dark_green()
        )
        p_val = calculate_blackjack_hand(self.player_hand)
        p_cards = ", ".join(f"`{c[0]}{c[1]}`" for c in self.player_hand)
        embed.add_field(name="👤 Your Hand", value=f"Cards: {p_cards}\nValue: **{p_val}**", inline=True)
        
        if show_dealer:
            d_val = calculate_blackjack_hand(self.dealer_hand)
            d_cards = ", ".join(f"`{c[0]}{c[1]}`" for c in self.dealer_hand)
            embed.add_field(name="🕵️ Dealer Hand", value=f"Cards: {d_cards}\nValue: **{d_val}**", inline=True)
        else:
            d_cards = f"`{self.dealer_hand[0][0]}{self.dealer_hand[0][1]}` and `?`"
            first_val = get_blackjack_card_value(self.dealer_hand[0][0])
            embed.add_field(name="🕵️ Dealer Hand", value=f"Cards: {d_cards}\nValue: **{first_val}**", inline=True)

        embed.add_field(name="💰 Wager", value=f"**${self.bet:,}** coins", inline=False)
        if status:
            embed.description = status
        set_owner_footer(embed, self.bot)
        return embed

    @discord.ui.button(label="Hit 🃏", style=discord.ButtonStyle.primary)
    async def hit(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.player_hand.append(draw_card())
        val = calculate_blackjack_hand(self.player_hand)
        if val > 21:
            self.stop()
            embed = self.make_embed(show_dealer=True, status="💥 **You busted!** The dealer wins. You lost your bet.")
            if not interaction.response.is_done():
                await interaction.response.edit_message(embed=embed, view=None)
        elif val == 21:
            await self.stand_logic(interaction)
        else:
            embed = self.make_embed()
            if not interaction.response.is_done():
                await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Stand 🛑", style=discord.ButtonStyle.secondary)
    async def stand(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.stand_logic(interaction)

    async def stand_logic(self, interaction: discord.Interaction):
        self.stop()
        while calculate_blackjack_hand(self.dealer_hand) < 17:
            self.dealer_hand.append(draw_card())
            
        p_val = calculate_blackjack_hand(self.player_hand)
        d_val = calculate_blackjack_hand(self.dealer_hand)
        
        if d_val > 21:
            payout = int(self.bet * 2)
            await add_wallet(self.user_id, payout)
            embed = self.make_embed(show_dealer=True, status=f"🎉 **Dealer busted ({d_val})!** You won **+${payout:,} coins**!")
        elif p_val > d_val:
            payout = int(self.bet * 2)
            await add_wallet(self.user_id, payout)
            embed = self.make_embed(show_dealer=True, status=f"🎉 **You beat the dealer ({p_val} vs {d_val})!** You won **+${payout:,} coins**!")
        elif p_val == d_val:
            await add_wallet(self.user_id, self.bet)
            embed = self.make_embed(show_dealer=True, status=f"🤝 **Push / Tie ({p_val} each)!** Your bet of **${self.bet:,} coins** was refunded.")
        else:
            embed = self.make_embed(show_dealer=True, status=f"💥 **Dealer won ({d_val} vs {p_val})!** You lost your bet.")
            
        if not interaction.response.is_done():
            await interaction.response.edit_message(embed=embed, view=None)


# ==============================================================================
# 2. TIC-TAC-TOE VIEW (PvP & PvE)
# ==============================================================================
class TicTacToeButton(discord.ui.Button["TicTacToeView"]):
    def __init__(self, x: int, y: int):
        super().__init__(style=discord.ButtonStyle.secondary, label="\u200b", row=y)
        self.x = x
        self.y = y

    async def callback(self, interaction: discord.Interaction):
        assert self.view is not None
        await self.view.process_move(interaction, self.x, self.y)

class TicTacToeView(discord.ui.View):
    def __init__(self, bot: commands.Bot, p1: discord.Member, p2: Optional[discord.Member], bet: int = 0):
        super().__init__(timeout=180)
        self.bot = bot
        self.p1 = p1
        self.p2 = p2  # None means playing against AI
        self.bet = bet
        self.board = [[0, 0, 0], [0, 0, 0], [0, 0, 0]]
        self.current_turn = p1  # p1 is X (1), p2/AI is O (-1)
        self.winner = None

        for y in range(3):
            for x in range(3):
                self.add_item(TicTacToeButton(x, y))

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item) -> None:
        logger.exception("TicTacToeView error on %s: %s", item, error)
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ An error occurred in this TicTacToe match.", ephemeral=True)
            else:
                await interaction.followup.send("❌ An error occurred in this TicTacToe match.", ephemeral=True)
        except Exception:
            pass

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True

    def check_winner(self) -> int:
        for row in self.board:
            if row[0] != 0 and row[0] == row[1] == row[2]:
                return row[0]
        for col in range(3):
            if self.board[0][col] != 0 and self.board[0][col] == self.board[1][col] == self.board[2][col]:
                return self.board[0][col]
        if self.board[0][0] != 0 and self.board[0][0] == self.board[1][1] == self.board[2][2]:
            return self.board[0][0]
        if self.board[0][2] != 0 and self.board[0][2] == self.board[1][1] == self.board[2][0]:
            return self.board[0][2]
        if all(cell != 0 for row in self.board for cell in row):
            return 2  # Tie
        return 0

    def ai_best_move(self) -> Tuple[int, int]:
        empty_cells = [(x, y) for y in range(3) for x in range(3) if self.board[y][x] == 0]
        # 1. Can AI win?
        for x, y in empty_cells:
            self.board[y][x] = -1
            if self.check_winner() == -1:
                self.board[y][x] = 0
                return x, y
            self.board[y][x] = 0
        # 2. Block player
        for x, y in empty_cells:
            self.board[y][x] = 1
            if self.check_winner() == 1:
                self.board[y][x] = 0
                return x, y
            self.board[y][x] = 0
        # 3. Pick center if available
        if (1, 1) in empty_cells:
            return 1, 1
        # 4. Pick random
        return random.choice(empty_cells)

    async def process_move(self, interaction: discord.Interaction, x: int, y: int):
        if self.p2 and interaction.user.id not in (self.p1.id, self.p2.id):
            await interaction.response.send_message("You are not part of this match.", ephemeral=True)
            return
        if not self.p2 and interaction.user.id != self.p1.id:
            await interaction.response.send_message("This solo match is not yours.", ephemeral=True)
            return
        if interaction.user.id != self.current_turn.id:
            await interaction.response.send_message("It is not your turn!", ephemeral=True)
            return

        btn = next(item for item in self.children if isinstance(item, TicTacToeButton) and item.x == x and item.y == y)
        val = 1 if self.current_turn.id == self.p1.id else -1
        self.board[y][x] = val
        btn.label = "❌" if val == 1 else "⭕"
        btn.style = discord.ButtonStyle.danger if val == 1 else discord.ButtonStyle.primary
        btn.disabled = True

        res = self.check_winner()
        if res != 0:
            await self.end_game(interaction, res)
            return

        # AI Turn
        if not self.p2:
            ai_x, ai_y = self.ai_best_move()
            self.board[ai_y][ai_x] = -1
            ai_btn = next(item for item in self.children if isinstance(item, TicTacToeButton) and item.x == ai_x and item.y == ai_y)
            ai_btn.label = "⭕"
            ai_btn.style = discord.ButtonStyle.primary
            ai_btn.disabled = True

            ai_res = self.check_winner()
            if ai_res != 0:
                await self.end_game(interaction, ai_res)
                return

            embed = self.make_embed()
            await interaction.response.edit_message(embed=embed, view=self)
            return

        # PvP Turn switch
        self.current_turn = self.p2 if self.current_turn.id == self.p1.id else self.p1
        embed = self.make_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    async def end_game(self, interaction: discord.Interaction, winner_code: int):
        self.stop()
        for child in self.children:
            child.disabled = True

        embed = discord.Embed(title="⚔️ Tic-Tac-Toe Game Over")
        if winner_code == 1:
            embed.color = discord.Color.green()
            embed.description = f"🎉 **{self.p1.mention} (❌) wins!**"
            if self.bet > 0:
                payout = self.bet * 2 if self.p2 else int(self.bet * 1.8)
                await add_wallet(self.p1.id, payout)
                embed.description += f"\n💰 **Won ${payout:,} coins!**"
        elif winner_code == -1:
            embed.color = discord.Color.red()
            opponent_name = self.p2.mention if self.p2 else "🤖 Helix AI"
            embed.description = f"🎉 **{opponent_name} (⭕) wins!**"
            if self.bet > 0 and self.p2:
                await add_wallet(self.p2.id, self.bet * 2)
                embed.description += f"\n💰 **{self.p2.mention} won ${self.bet * 2:,} coins!**"
        else:
            embed.color = discord.Color.gold()
            embed.description = "🤝 **It's a draw!** Well played by both."
            if self.bet > 0:
                await add_wallet(self.p1.id, self.bet)
                if self.p2:
                    await add_wallet(self.p2.id, self.bet)
                embed.description += "\n💰 Bets refunded."

        set_owner_footer(embed, self.bot)
        await interaction.response.edit_message(embed=embed, view=self)

    def make_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="⚔️ Tic-Tac-Toe Match",
            color=discord.Color.from_rgb(88, 101, 242)
        )
        opp = self.p2.mention if self.p2 else "🤖 Helix AI"
        embed.description = (
            f"**Player 1 (❌)**: {self.p1.mention}\n"
            f"**Player 2 (⭕)**: {opp}\n"
            f"**Current Turn**: {self.current_turn.mention}\n"
        )
        if self.bet > 0:
            embed.description += f"**Wager**: `${self.bet:,}` coins\n"
        set_owner_footer(embed, self.bot)
        return embed


# ==============================================================================
# 3. CONNECT FOUR VIEW (Interactive 6x7 Grid)
# ==============================================================================
class ConnectFourView(discord.ui.View):
    def __init__(self, bot: commands.Bot, p1: discord.Member, p2: Optional[discord.Member], bet: int = 0):
        super().__init__(timeout=180)
        self.bot = bot
        self.p1 = p1
        self.p2 = p2
        self.bet = bet
        self.rows = 6
        self.cols = 7
        self.board = [[0 for _ in range(self.cols)] for _ in range(self.rows)]
        self.current_turn = p1

        for c in range(self.cols):
            self.add_item(discord.ui.Button(label=str(c + 1), style=discord.ButtonStyle.secondary, custom_id=f"c4_{c}", row=0 if c < 4 else 1))
            self.children[-1].callback = self.make_callback(c)

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item) -> None:
        logger.exception("ConnectFourView error on %s: %s", item, error)
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ An error occurred in this Connect 4 match.", ephemeral=True)
            else:
                await interaction.followup.send("❌ An error occurred in this Connect 4 match.", ephemeral=True)
        except Exception:
            pass

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True

    def make_callback(self, col: int):
        async def callback(interaction: discord.Interaction):
            await self.drop_piece(interaction, col)
        return callback

    def render_board(self) -> str:
        symbols = {0: "⚪", 1: "🔴", -1: "🟡"}
        lines = []
        for r in range(self.rows):
            lines.append("".join(symbols[self.board[r][c]] for c in range(self.cols)))
        lines.append("1️⃣2️⃣3️⃣4️⃣5️⃣6️⃣7️⃣")
        return "\n".join(lines)

    def check_winner(self) -> int:
        # Horizontal
        for r in range(self.rows):
            for c in range(self.cols - 3):
                val = self.board[r][c]
                if val != 0 and val == self.board[r][c+1] == self.board[r][c+2] == self.board[r][c+3]:
                    return val
        # Vertical
        for r in range(self.rows - 3):
            for c in range(self.cols):
                val = self.board[r][c]
                if val != 0 and val == self.board[r+1][c] == self.board[r+2][c] == self.board[r+3][c]:
                    return val
        # Positive Diagonal
        for r in range(3, self.rows):
            for c in range(self.cols - 3):
                val = self.board[r][c]
                if val != 0 and val == self.board[r-1][c+1] == self.board[r-2][c+2] == self.board[r-3][c+3]:
                    return val
        # Negative Diagonal
        for r in range(self.rows - 3):
            for c in range(self.cols - 3):
                val = self.board[r][c]
                if val != 0 and val == self.board[r+1][c+1] == self.board[r+2][c+2] == self.board[r+3][c+3]:
                    return val
        # Full
        if all(self.board[0][c] != 0 for c in range(self.cols)):
            return 2  # Draw
        return 0

    def get_lowest_empty_row(self, col: int) -> int:
        for r in range(self.rows - 1, -1, -1):
            if self.board[r][col] == 0:
                return r
        return -1

    async def drop_piece(self, interaction: discord.Interaction, col: int):
        if self.p2 and interaction.user.id not in (self.p1.id, self.p2.id):
            await interaction.response.send_message("You are not part of this Connect 4 match.", ephemeral=True)
            return
        if not self.p2 and interaction.user.id != self.p1.id:
            await interaction.response.send_message("This match is not yours.", ephemeral=True)
            return
        if interaction.user.id != self.current_turn.id:
            await interaction.response.send_message("It is not your turn!", ephemeral=True)
            return

        row = self.get_lowest_empty_row(col)
        if row == -1:
            await interaction.response.send_message("That column is completely full!", ephemeral=True)
            return

        val = 1 if self.current_turn.id == self.p1.id else -1
        self.board[row][col] = val

        # Check full column
        if self.board[0][col] != 0:
            for child in self.children:
                if child.label == str(col + 1):
                    child.disabled = True

        res = self.check_winner()
        if res != 0:
            await self.end_game(interaction, res)
            return

        # AI Turn
        if not self.p2:
            valid_cols = [c for c in range(self.cols) if self.board[0][c] == 0]
            if valid_cols:
                ai_col = random.choice(valid_cols)
                ai_row = self.get_lowest_empty_row(ai_col)
                self.board[ai_row][ai_col] = -1
                if self.board[0][ai_col] != 0:
                    for child in self.children:
                        if child.label == str(ai_col + 1):
                            child.disabled = True

                ai_res = self.check_winner()
                if ai_res != 0:
                    await self.end_game(interaction, ai_res)
                    return

            embed = self.make_embed()
            await interaction.response.edit_message(embed=embed, view=self)
            return

        # Turn switch
        self.current_turn = self.p2 if self.current_turn.id == self.p1.id else self.p1
        embed = self.make_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    async def end_game(self, interaction: discord.Interaction, winner_code: int):
        self.stop()
        for child in self.children:
            child.disabled = True

        embed = discord.Embed(title="🔴🟡 Connect Four Game Over")
        board_render = self.render_board()
        if winner_code == 1:
            embed.color = discord.Color.red()
            embed.description = f"{board_render}\n\n🎉 **{self.p1.mention} (🔴) wins!**"
            if self.bet > 0:
                payout = self.bet * 2 if self.p2 else int(self.bet * 1.8)
                await add_wallet(self.p1.id, payout)
                embed.description += f"\n💰 **Won ${payout:,} coins!**"
        elif winner_code == -1:
            embed.color = discord.Color.gold()
            opp_name = self.p2.mention if self.p2 else "🤖 Helix AI"
            embed.description = f"{board_render}\n\n🎉 **{opp_name} (🟡) wins!**"
            if self.bet > 0 and self.p2:
                await add_wallet(self.p2.id, self.bet * 2)
                embed.description += f"\n💰 **{self.p2.mention} won ${self.bet * 2:,} coins!**"
        else:
            embed.color = discord.Color.blue()
            embed.description = f"{board_render}\n\n🤝 **Draw! The board is full.**"
            if self.bet > 0:
                await add_wallet(self.p1.id, self.bet)
                if self.p2:
                    await add_wallet(self.p2.id, self.bet)

        set_owner_footer(embed, self.bot)
        await interaction.response.edit_message(embed=embed, view=self)

    def make_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="🔴🟡 Connect Four Match",
            color=discord.Color.from_rgb(88, 101, 242)
        )
        opp = self.p2.mention if self.p2 else "🤖 Helix AI"
        symbol = "🔴" if self.current_turn.id == self.p1.id else "🟡"
        embed.description = (
            f"**Player 1 (🔴)**: {self.p1.mention}\n"
            f"**Player 2 (🟡)**: {opp}\n"
            f"**Turn**: {self.current_turn.mention} ({symbol})\n\n"
            f"{self.render_board()}"
        )
        set_owner_footer(embed, self.bot)
        return embed


# ==============================================================================
# 4. CASINO MINES VIEW (Interactive Grid & Cashout)
# ==============================================================================
class MineTileButton(discord.ui.Button["MinesView"]):
    def __init__(self, index: int):
        super().__init__(style=discord.ButtonStyle.secondary, label="❓", row=index // 5)
        self.tile_index = index

    async def callback(self, interaction: discord.Interaction):
        assert self.view is not None
        await self.view.click_tile(interaction, self.tile_index)

class MinesView(discord.ui.View):
    def __init__(self, bot: commands.Bot, user_id: int, bet: int, mine_count: int):
        super().__init__(timeout=180)
        self.bot = bot
        self.user_id = user_id
        self.bet = bet
        self.mine_count = mine_count
        self.total_tiles = 20
        self.safe_tiles = self.total_tiles - mine_count
        self.mines = set(random.sample(range(self.total_tiles), mine_count))
        self.uncovered = set()
        self.multiplier = 1.0

        for i in range(self.total_tiles):
            self.add_item(MineTileButton(i))

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item) -> None:
        logger.exception("MinesView error on %s: %s", item, error)
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ An error occurred in this Minefield game.", ephemeral=True)
            else:
                await interaction.followup.send("❌ An error occurred in this Minefield game.", ephemeral=True)
        except Exception:
            pass

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True


    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This Minefield game is not yours.", ephemeral=True)
            return False
        return True

    def calculate_multiplier(self) -> float:
        # Multiplier formula based on safe steps uncovered
        gems = len(self.uncovered)
        if gems == 0:
            return 1.0
        prob = 1.0
        for i in range(gems):
            prob *= (self.safe_tiles - i) / (self.total_tiles - i)
        return round((0.97 / prob), 2)

    @discord.ui.button(label="Cash Out 💰", style=discord.ButtonStyle.success, row=4)
    async def cashout_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.uncovered:
            await interaction.response.send_message("Uncover at least 1 diamond before cashing out!", ephemeral=True)
            return
        self.stop()
        payout = int(self.bet * self.multiplier)
        await add_wallet(self.user_id, payout)

        # Reveal all tiles
        for child in self.children:
            if isinstance(child, MineTileButton):
                child.disabled = True
                if child.tile_index in self.mines:
                    child.label = "💣"
                    child.style = discord.ButtonStyle.danger
                elif child.tile_index in self.uncovered:
                    child.label = "💎"
                    child.style = discord.ButtonStyle.success
                else:
                    child.label = "▫️"

        embed = discord.Embed(
            title="💰 Mines Cashout Successful!",
            description=(
                f"🎉 **You cashed out at {self.multiplier:.2f}x!**\n"
                f"• **Diamonds Uncovered**: `{len(self.uncovered)}`\n"
                f"• **Initial Bet**: `${self.bet:,}`\n"
                f"• **Total Payout**: **+${payout:,} coins**"
            ),
            color=discord.Color.green()
        )
        set_owner_footer(embed, self.bot)
        await interaction.response.edit_message(embed=embed, view=self)

    async def click_tile(self, interaction: discord.Interaction, index: int):
        if index in self.uncovered:
            return
        btn = next(item for item in self.children if isinstance(item, MineTileButton) and item.tile_index == index)

        # Hit a mine!
        if index in self.mines:
            self.stop()
            for child in self.children:
                if isinstance(child, MineTileButton):
                    child.disabled = True
                    if child.tile_index in self.mines:
                        child.label = "💣"
                        child.style = discord.ButtonStyle.danger
                    elif child.tile_index in self.uncovered:
                        child.label = "💎"
                        child.style = discord.ButtonStyle.success
                    else:
                        child.label = "▫️"
                else:
                    child.disabled = True

            embed = discord.Embed(
                title="💥 BOOM! You Hit a Mine!",
                description=f"You uncovered a bomb at tile `{index+1}`. You lost your bet of **${self.bet:,} coins**.",
                color=discord.Color.red()
            )
            set_owner_footer(embed, self.bot)
            await interaction.response.edit_message(embed=embed, view=self)
            return

        # Safe gem!
        self.uncovered.add(index)
        btn.label = "💎"
        btn.style = discord.ButtonStyle.success
        btn.disabled = True
        self.multiplier = self.calculate_multiplier()

        # Check all safe tiles uncovered
        if len(self.uncovered) == self.safe_tiles:
            self.stop()
            payout = int(self.bet * self.multiplier)
            await add_wallet(self.user_id, payout)
            for child in self.children:
                child.disabled = True

            embed = discord.Embed(
                title="👑 ALL DIAMONDS FOUND! JACKPOT!",
                description=f"🎉 Incredible! You cleared the entire minefield at **{self.multiplier:.2f}x**!\n**Payout: +${payout:,} coins!**",
                color=discord.Color.gold()
            )
            set_owner_footer(embed, self.bot)
            await interaction.response.edit_message(embed=embed, view=self)
            return

        embed = self.make_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    def make_embed(self) -> discord.Embed:
        current_val = int(self.bet * self.multiplier)
        embed = discord.Embed(
            title="💣 Minefield & Diamond Hunt",
            description=(
                f"**Mines**: `{self.mine_count}` • **Diamonds**: `{len(self.uncovered)}/{self.safe_tiles}`\n"
                f"**Multiplier**: `⚡ {self.multiplier:.2f}x`\n"
                f"**Current Cashout**: **`${current_val:,}` coins**"
            ),
            color=discord.Color.from_rgb(88, 101, 242)
        )
        set_owner_footer(embed, self.bot)
        return embed


# ==============================================================================
# 5. HIGHLOW CARD VIEW
# ==============================================================================
class HighLowView(discord.ui.View):
    def __init__(self, bot: commands.Bot, user_id: int, bet: int):
        super().__init__(timeout=180)
        self.bot = bot
        self.user_id = user_id
        self.bet = bet
        self.current_card = draw_card()
        self.streak = 0
        self.multiplier = 1.0

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item) -> None:
        logger.exception("HighLowView error on %s: %s", item, error)
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ An error occurred in this Higher or Lower game.", ephemeral=True)
            else:
                await interaction.followup.send("❌ An error occurred in this Higher or Lower game.", ephemeral=True)
        except Exception:
            pass

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This game is not yours.", ephemeral=True)
            return False
        return True

    def make_embed(self, status: str = None) -> discord.Embed:
        cur_winnings = int(self.bet * self.multiplier)
        embed = discord.Embed(
            title="📈 Higher or Lower Card Game",
            description=(
                f"**Current Card**: `{self.current_card[0]}{self.current_card[1]}` (Value: **{self.current_card[2]}**)\n"
                f"**Streak**: `🔥 {self.streak}` • **Multiplier**: `⚡ {self.multiplier:.2f}x`\n"
                f"**Potential Cashout**: **`${cur_winnings:,}` coins**\n\n"
                f"Will the next drawn card be **Higher ⬆️** or **Lower ⬇️**?"
            ),
            color=discord.Color.from_rgb(88, 101, 242)
        )
        if status:
            embed.add_field(name="Result", value=status, inline=False)
        set_owner_footer(embed, self.bot)
        return embed

    async def handle_guess(self, interaction: discord.Interaction, is_higher: bool):
        next_card = draw_card()
        c_val = self.current_card[2]
        n_val = next_card[2]

        # Check win / tie / lose
        if n_val == c_val:
            # Tie: push / no streak change
            self.current_card = next_card
            embed = self.make_embed(status=f"🟰 Drawn `{next_card[0]}{next_card[1]}` (Equal value)! Streak preserved.")
            await interaction.response.edit_message(embed=embed, view=self)
            return

        won = (n_val > c_val) if is_higher else (n_val < c_val)
        if won:
            self.streak += 1
            self.multiplier = round(self.multiplier * 1.45, 2)
            self.current_card = next_card
            embed = self.make_embed(status=f"✅ Correct! Drawn `{next_card[0]}{next_card[1]}`.")
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            self.stop()
            embed = discord.Embed(
                title="💔 Incorrect Guess!",
                description=f"Drawn card was `{next_card[0]}{next_card[1]}` (Value: **{n_val}**).\nYou lost your bet of **${self.bet:,} coins**.",
                color=discord.Color.red()
            )
            set_owner_footer(embed, self.bot)
            await interaction.response.edit_message(embed=embed, view=None)

    @discord.ui.button(label="Higher ⬆️", style=discord.ButtonStyle.primary)
    async def higher_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_guess(interaction, is_higher=True)

    @discord.ui.button(label="Lower ⬇️", style=discord.ButtonStyle.primary)
    async def lower_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_guess(interaction, is_higher=False)

    @discord.ui.button(label="Cash Out 💰", style=discord.ButtonStyle.success)
    async def cashout_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.streak == 0:
            await interaction.response.send_message("Make at least 1 correct guess to cash out!", ephemeral=True)
            return
        self.stop()
        payout = int(self.bet * self.multiplier)
        await add_wallet(self.user_id, payout)
        embed = discord.Embed(
            title="💰 HighLow Cashout Successful!",
            description=f"🎉 Cashed out after **{self.streak}** streak at **{self.multiplier:.2f}x**!\n**Payout: +${payout:,} coins!**",
            color=discord.Color.green()
        )
        set_owner_footer(embed, self.bot)
        await interaction.response.edit_message(embed=embed, view=None)


# ==============================================================================
# 6. TRIVIA VIEW
# ==============================================================================
TRIVIA_QUESTIONS = [
    {
        "q": "Which video game character is known as the 'Blue Blur'?",
        "options": ["Sonic the Hedgehog", "Mega Man", "Sub-Zero", "Mario"],
        "answer": "Sonic the Hedgehog",
        "category": "Gaming"
    },
    {
        "q": "What is the capital city of Japan?",
        "options": ["Tokyo", "Kyoto", "Osaka", "Nagoya"],
        "answer": "Tokyo",
        "category": "Geography"
    },
    {
        "q": "In Python, which built-in function returns the length of an object?",
        "options": ["len()", "count()", "size()", "length()"],
        "answer": "len()",
        "category": "Science & Tech"
    },
    {
        "q": "What is the highest-grossing anime film of all time worldwide?",
        "options": ["Demon Slayer: Mugen Train", "Spirited Away", "Your Name", "Suzume"],
        "answer": "Demon Slayer: Mugen Train",
        "category": "Anime"
    },
    {
        "q": "What is the speed of light in vacuum approximately?",
        "options": ["300,000 km/s", "150,000 km/s", "1,000,000 km/s", "30,000 km/s"],
        "answer": "300,000 km/s",
        "category": "Science & Tech"
    },
    {
        "q": "Which year was the original iPhone released by Apple?",
        "options": ["2007", "2005", "2008", "2010"],
        "answer": "2007",
        "category": "Tech"
    },
    {
        "q": "Who is known as the father of modern computer science?",
        "options": ["Alan Turing", "Charles Babbage", "Ada Lovelace", "John von Neumann"],
        "answer": "Alan Turing",
        "category": "History"
    },
    {
        "q": "In Minecraft, what ore is required to brew potions?",
        "options": ["Blaze Rod / Nether Wart", "Redstone", "Lapis Lazuli", "Diamond"],
        "answer": "Blaze Rod / Nether Wart",
        "category": "Gaming"
    }
]

class TriviaView(discord.ui.View):
    def __init__(self, bot: commands.Bot, user_id: int, question_data: dict, bet: int = 0):
        super().__init__(timeout=45)
        self.bot = bot
        self.user_id = user_id
        self.q_data = question_data
        self.bet = bet
        self.answered = False

        options = list(question_data["options"])
        random.shuffle(options)
        labels = ["A", "B", "C", "D"]
        for i, opt in enumerate(options):
            btn = discord.ui.Button(label=f"{labels[i]}: {opt}", style=discord.ButtonStyle.primary, row=i // 2)
            btn.callback = self.make_callback(opt)
            self.add_item(btn)

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item) -> None:
        logger.exception("TriviaView error on %s: %s", item, error)
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ An error occurred processing your trivia answer.", ephemeral=True)
            else:
                await interaction.followup.send("❌ An error occurred processing your trivia answer.", ephemeral=True)
        except Exception:
            pass

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This Trivia question is for someone else!", ephemeral=True)
            return False
        return True

    def make_callback(self, choice: str):
        async def callback(interaction: discord.Interaction):
            if self.answered:
                return
            self.answered = True
            self.stop()
            for child in self.children:
                child.disabled = True

            correct = (choice == self.q_data["answer"])
            if correct:
                embed = discord.Embed(
                    title="🎉 Correct Answer!",
                    description=f"**Answer**: `{self.q_data['answer']}`",
                    color=discord.Color.green()
                )
                if self.bet > 0:
                    payout = self.bet * 2
                    await add_wallet(self.user_id, payout)
                    embed.description += f"\n💰 **You won ${payout:,} coins!**"
                else:
                    await add_wallet(self.user_id, 100)
                    embed.description += "\n💰 **+100 bonus coins awarded!**"
            else:
                embed = discord.Embed(
                    title="❌ Incorrect!",
                    description=f"You chose `{choice}`.\nThe correct answer was: **`{self.q_data['answer']}`**.",
                    color=discord.Color.red()
                )
                if self.bet > 0:
                    embed.description += f"\n😔 Lost bet of **${self.bet:,} coins**."

            set_owner_footer(embed, self.bot)
            await interaction.response.edit_message(embed=embed, view=self)
        return callback


# ==============================================================================
# 7. MAIN GAMES COG
# ==============================================================================
class Games(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_group(name="game", invoke_without_command=True)
    @commands.guild_only()
    async def game_group(self, ctx: commands.Context):
        """Play interactive multiplayer, card, and casino games."""
        embed = discord.Embed(
            title="🎮 Helix Interactive Game Suite",
            description=(
                "Choose any game below to play with interactive buttons or wagers:\n\n"
                "• **`!tictactoe [@user] [bet]`** (alias `!ttt`) — 3x3 Tic-Tac-Toe vs Player/AI\n"
                "• **`!connect4 [@user] [bet]`** (alias `!c4`) — 4-in-a-row Connect Four\n"
                "• **`!blackjack <bet>`** (alias `!bj`) — Interactive 21 vs Dealer\n"
                "• **`!mines <bet> [mines]`** (alias `!minefield`) — Minefield Diamond Cashout\n"
                "• **`!highlow <bet>`** (alias `!hilow`) — Higher or Lower Card Streaks\n"
                "• **`!slots <bet>`** — 3-Reel Slot Machine with 15x Jackpots\n"
                "• **`!roulette <bet> <space>`** — European Roulette Table\n"
                "• **`!coinflip <heads|tails> <bet>`** (alias `!cf`) — 50/50 Coinflip\n"
                "• **`!rps <choice> [bet]`** — Rock Paper Scissors vs AI\n"
                "• **`!trivia [bet]`** (alias `!quiz`) — 4-Button Trivia Challenge\n"
            ),
            color=discord.Color.from_rgb(88, 101, 242)
        )
        set_owner_footer(embed, self.bot)
        await ctx.send(embed=embed)

    # --------------------------------------------------------------------------
    # Coinflip
    # --------------------------------------------------------------------------
    async def _do_coinflip(self, ctx: commands.Context, choice: str, bet: int):
        choice = choice.lower().strip()
        if choice not in ("heads", "tails", "head", "tail"):
            await ctx.send("❌ Invalid choice! Choose `heads` or `tails`.", ephemeral=True)
            return
        if choice == "head":
            choice = "heads"
        if choice == "tail":
            choice = "tails"
        if bet <= 0:
            await ctx.send("❌ Bet must be a positive integer.", ephemeral=True)
            return

        w, b = await get_balance(ctx.author.id)
        if w < bet:
            await ctx.send(f"❌ You don't have enough coins in your wallet! Balance: **${w:,}**", ephemeral=True)
            return

        await add_wallet(ctx.author.id, -bet)
        result = random.choice(["heads", "tails"])
        embed = discord.Embed(title="🪙 Coinflip Result", color=discord.Color.gold())
        if result == choice:
            await add_wallet(ctx.author.id, bet * 2)
            embed.description = f"The coin landed on **{result}**!\n\n🎉 **You won ${bet:,} coins!**"
            embed.color = discord.Color.green()
        else:
            embed.description = f"The coin landed on **{result}**!\n\n😔 **You lost ${bet:,} coins.**"
            embed.color = discord.Color.red()

        set_owner_footer(embed, self.bot)
        await ctx.send(embed=embed)

    @game_group.command(name="coinflip")
    @commands.guild_only()
    async def slash_coinflip(self, ctx: commands.Context, choice: str, bet: int):
        """Bet on a 50/50 coinflip! Choice: heads or tails."""
        await self._do_coinflip(ctx, choice, bet)

    @commands.command(name="coinflip", aliases=["cf"])
    @commands.guild_only()
    async def prefix_coinflip(self, ctx: commands.Context, choice: str, bet: int):
        """Bet on a 50/50 coinflip! Choice: heads or tails."""
        await self._do_coinflip(ctx, choice, bet)

    # --------------------------------------------------------------------------
    # Slots
    # --------------------------------------------------------------------------
    async def _do_slots(self, ctx: commands.Context, bet: int):
        if bet <= 0:
            await ctx.send("❌ Bet must be a positive integer.", ephemeral=True)
            return
        w, b = await get_balance(ctx.author.id)
        if w < bet:
            await ctx.send(f"❌ You don't have enough coins! Balance: **${w:,}**", ephemeral=True)
            return

        await add_wallet(ctx.author.id, -bet)
        emojis = ["🍒", "🍋", "🍇", "💎", "⭐", "7️⃣"]
        reel = [random.choice(emojis) for _ in range(3)]

        payout = 0
        if reel[0] == reel[1] == reel[2]:
            if reel[0] == "💎" or reel[0] == "7️⃣":
                payout = bet * 15
                status = "🎰 **MEGA JACKPOT! 15x payout!** 💎"
            else:
                payout = bet * 5
                status = "🎉 **Three of a kind! 5x payout!** 🎉"
        elif reel[0] == reel[1] or reel[1] == reel[2] or reel[0] == reel[2]:
            payout = bet * 2
            status = "✨ **Two of a kind! 2x payout!** ✨"
        else:
            status = "😔 **No match! Better luck next spin.**"

        if payout > 0:
            await add_wallet(ctx.author.id, payout)

        embed = discord.Embed(
            title="🎰 Casino Slot Machine",
            description=f"**[ {reel[0]} | {reel[1]} | {reel[2]} ]**\n\n{status}",
            color=discord.Color.green() if payout > 0 else discord.Color.red()
        )
        set_owner_footer(embed, self.bot)
        await ctx.send(embed=embed)

    @game_group.command(name="slots")
    @commands.guild_only()
    async def slash_slots(self, ctx: commands.Context, bet: int):
        """Spin the 3-reel slot machine for huge multipliers."""
        await self._do_slots(ctx, bet)

    @commands.command(name="slots")
    @commands.guild_only()
    async def prefix_slots(self, ctx: commands.Context, bet: int):
        """Spin the 3-reel slot machine for huge multipliers."""
        await self._do_slots(ctx, bet)

    # --------------------------------------------------------------------------
    # Blackjack
    # --------------------------------------------------------------------------
    async def _do_blackjack(self, ctx: commands.Context, bet: int):
        if bet <= 0:
            await ctx.send("❌ Bet must be a positive integer.", ephemeral=True)
            return
        w, b = await get_balance(ctx.author.id)
        if w < bet:
            await ctx.send(f"❌ Insufficient wallet balance! You have: **${w:,}**", ephemeral=True)
            return

        await add_wallet(ctx.author.id, -bet)
        view = BlackjackView(self.bot, ctx.author.id, bet)
        p_val = calculate_blackjack_hand(view.player_hand)
        if p_val == 21:
            payout = int(bet * 2.5)
            await add_wallet(ctx.author.id, payout)
            embed = view.make_embed(show_dealer=True, status=f"🃏 **Natural Blackjack!** Won 2.5x payout (**+${payout:,} coins**)! 🎉")
            await ctx.send(embed=embed)
            return

        embed = view.make_embed()
        await ctx.send(embed=embed, view=view)

    @game_group.command(name="blackjack")
    @commands.guild_only()
    async def slash_blackjack(self, ctx: commands.Context, bet: int):
        """Interactive Blackjack card game against the dealer."""
        await self._do_blackjack(ctx, bet)

    @commands.command(name="blackjack", aliases=["bj"])
    @commands.guild_only()
    async def prefix_blackjack(self, ctx: commands.Context, bet: int):
        """Interactive Blackjack card game against the dealer."""
        await self._do_blackjack(ctx, bet)

    # --------------------------------------------------------------------------
    # Tic-Tac-Toe
    # --------------------------------------------------------------------------
    async def _do_tictactoe(self, ctx: commands.Context, opponent: Optional[discord.Member] = None, bet: Optional[int] = 0):
        bet = bet or 0
        if bet < 0:
            await ctx.send("❌ Bet cannot be negative.", ephemeral=True)
            return

        if opponent and opponent.id == ctx.author.id:
            await ctx.send("❌ You cannot play Tic-Tac-Toe against yourself.", ephemeral=True)
            return

        if opponent and opponent.bot:
            opponent = None  # AI game

        if bet > 0:
            w1, _ = await get_balance(ctx.author.id)
            if w1 < bet:
                await ctx.send(f"❌ You need at least **${bet:,}** coins in your wallet.", ephemeral=True)
                return
            if opponent:
                w2, _ = await get_balance(opponent.id)
                if w2 < bet:
                    await ctx.send(f"❌ {opponent.mention} doesn't have enough coins for this wager.", ephemeral=True)
                    return
                await add_wallet(opponent.id, -bet)
            await add_wallet(ctx.author.id, -bet)

        view = TicTacToeView(self.bot, ctx.author, opponent, bet)
        embed = view.make_embed()
        await ctx.send(embed=embed, view=view)

    @game_group.command(name="tictactoe")
    @commands.guild_only()
    async def slash_tictactoe(self, ctx: commands.Context, opponent: Optional[discord.Member] = None, bet: Optional[int] = 0):
        """Play 3x3 Tic-Tac-Toe against a friend or Helix AI."""
        await self._do_tictactoe(ctx, opponent, bet)

    @commands.command(name="tictactoe", aliases=["ttt"])
    @commands.guild_only()
    async def prefix_tictactoe(self, ctx: commands.Context, opponent: Optional[discord.Member] = None, bet: Optional[int] = 0):
        """Play 3x3 Tic-Tac-Toe against a friend or Helix AI."""
        await self._do_tictactoe(ctx, opponent, bet)

    # --------------------------------------------------------------------------
    # Connect Four
    # --------------------------------------------------------------------------
    async def _do_connect4(self, ctx: commands.Context, opponent: Optional[discord.Member] = None, bet: Optional[int] = 0):
        bet = bet or 0
        if bet < 0:
            await ctx.send("❌ Bet cannot be negative.", ephemeral=True)
            return
        if opponent and opponent.id == ctx.author.id:
            await ctx.send("❌ You cannot challenge yourself.", ephemeral=True)
            return
        if opponent and opponent.bot:
            opponent = None

        if bet > 0:
            w1, _ = await get_balance(ctx.author.id)
            if w1 < bet:
                await ctx.send(f"❌ You need at least **${bet:,}** coins.", ephemeral=True)
                return
            if opponent:
                w2, _ = await get_balance(opponent.id)
                if w2 < bet:
                    await ctx.send(f"❌ {opponent.mention} doesn't have enough coins for this bet.", ephemeral=True)
                    return
                await add_wallet(opponent.id, -bet)
            await add_wallet(ctx.author.id, -bet)

        view = ConnectFourView(self.bot, ctx.author, opponent, bet)
        embed = view.make_embed()
        await ctx.send(embed=embed, view=view)

    @game_group.command(name="connect4")
    @commands.guild_only()
    async def slash_connect4(self, ctx: commands.Context, opponent: Optional[discord.Member] = None, bet: Optional[int] = 0):
        """Play Connect Four 4-in-a-row against a player or AI."""
        await self._do_connect4(ctx, opponent, bet)

    @commands.command(name="connect4", aliases=["c4"])
    @commands.guild_only()
    async def prefix_connect4(self, ctx: commands.Context, opponent: Optional[discord.Member] = None, bet: Optional[int] = 0):
        """Play Connect Four 4-in-a-row against a player or AI."""
        await self._do_connect4(ctx, opponent, bet)

    # --------------------------------------------------------------------------
    # Mines
    # --------------------------------------------------------------------------
    async def _do_mines(self, ctx: commands.Context, bet: int, mines_count: Optional[int] = 3):
        if bet <= 0:
            await ctx.send("❌ Bet must be a positive integer.", ephemeral=True)
            return
        m_count = max(1, min(19, mines_count or 3))

        w, _ = await get_balance(ctx.author.id)
        if w < bet:
            await ctx.send(f"❌ Insufficient balance! You have **${w:,}** coins.", ephemeral=True)
            return

        await add_wallet(ctx.author.id, -bet)
        view = MinesView(self.bot, ctx.author.id, bet, m_count)
        embed = view.make_embed()
        await ctx.send(embed=embed, view=view)

    @game_group.command(name="mines")
    @commands.guild_only()
    async def slash_mines(self, ctx: commands.Context, bet: int, mines_count: Optional[int] = 3):
        """Play interactive Mines: uncover gems & cashout before bombs."""
        await self._do_mines(ctx, bet, mines_count)

    @commands.command(name="mines", aliases=["minefield"])
    @commands.guild_only()
    async def prefix_mines(self, ctx: commands.Context, bet: int, mines_count: Optional[int] = 3):
        """Play interactive Mines: uncover gems & cashout before bombs."""
        await self._do_mines(ctx, bet, mines_count)

    # --------------------------------------------------------------------------
    # Higher or Lower
    # --------------------------------------------------------------------------
    async def _do_highlow(self, ctx: commands.Context, bet: int):
        if bet <= 0:
            await ctx.send("❌ Bet must be a positive integer.", ephemeral=True)
            return
        w, _ = await get_balance(ctx.author.id)
        if w < bet:
            await ctx.send(f"❌ Insufficient wallet balance! You have: **${w:,}**", ephemeral=True)
            return

        await add_wallet(ctx.author.id, -bet)
        view = HighLowView(self.bot, ctx.author.id, bet)
        embed = view.make_embed()
        await ctx.send(embed=embed, view=view)

    @game_group.command(name="highlow")
    @commands.guild_only()
    async def slash_highlow(self, ctx: commands.Context, bet: int):
        """Guess if the next card is higher or lower for streak payouts."""
        await self._do_highlow(ctx, bet)

    @commands.command(name="highlow", aliases=["hilow", "hl"])
    @commands.guild_only()
    async def prefix_highlow(self, ctx: commands.Context, bet: int):
        """Guess if the next card is higher or lower for streak payouts."""
        await self._do_highlow(ctx, bet)

    # --------------------------------------------------------------------------
    # Trivia
    # --------------------------------------------------------------------------
    async def _do_trivia(self, ctx: commands.Context, bet: Optional[int] = 0):
        bet = bet or 0
        if bet < 0:
            await ctx.send("❌ Bet cannot be negative.", ephemeral=True)
            return
        if bet > 0:
            w, _ = await get_balance(ctx.author.id)
            if w < bet:
                await ctx.send(f"❌ Insufficient balance! You have: **${w:,}**", ephemeral=True)
                return
            await add_wallet(ctx.author.id, -bet)

        q_data = random.choice(TRIVIA_QUESTIONS)
        view = TriviaView(self.bot, ctx.author.id, q_data, bet)
        embed = discord.Embed(
            title=f"🧠 Trivia Challenge • {q_data['category']}",
            description=f"**Question**:\n### {q_data['q']}\n\n*Choose an answer below within 25 seconds!*",
            color=discord.Color.from_rgb(88, 101, 242)
        )
        if bet > 0:
            embed.description += f"\n💰 **Wager**: `${bet:,}` coins"
        set_owner_footer(embed, self.bot)
        await ctx.send(embed=embed, view=view)

    @game_group.command(name="trivia")
    @commands.guild_only()
    async def slash_trivia(self, ctx: commands.Context, bet: Optional[int] = 0):
        """Answer interactive trivia questions for coin rewards."""
        await self._do_trivia(ctx, bet)

    @commands.command(name="trivia", aliases=["quiz"])
    @commands.guild_only()
    async def prefix_trivia(self, ctx: commands.Context, bet: Optional[int] = 0):
        """Answer interactive trivia questions for coin rewards."""
        await self._do_trivia(ctx, bet)

    # --------------------------------------------------------------------------
    # Rock Paper Scissors
    # --------------------------------------------------------------------------
    async def _do_rps(self, ctx: commands.Context, choice: str, bet: Optional[int] = 0):
        user_choice = choice.lower().strip()
        valid = {"rock": "🪨 Rock", "paper": "📄 Paper", "scissors": "✂️ Scissors", "scissor": "✂️ Scissors"}
        if user_choice not in valid:
            await ctx.send("❌ Invalid choice! Choose `rock`, `paper`, or `scissors`.", ephemeral=True)
            return
        clean_user = "scissors" if user_choice == "scissor" else user_choice

        bet = bet or 0
        if bet > 0:
            w, _ = await get_balance(ctx.author.id)
            if w < bet:
                await ctx.send(f"❌ Insufficient balance! You have **${w:,}** coins.", ephemeral=True)
                return
            await add_wallet(ctx.author.id, -bet)

        bot_choice = random.choice(["rock", "paper", "scissors"])
        embed = discord.Embed(title="✂️ Rock Paper Scissors")
        
        if clean_user == bot_choice:
            embed.color = discord.Color.gold()
            embed.description = f"You chose {valid[clean_user]}, Helix chose {valid[bot_choice]}.\n\n🤝 **It's a tie!**"
            if bet > 0:
                await add_wallet(ctx.author.id, bet)
                embed.description += "\n💰 Bet refunded."
        elif (clean_user == "rock" and bot_choice == "scissors") or \
             (clean_user == "paper" and bot_choice == "rock") or \
             (clean_user == "scissors" and bot_choice == "paper"):
            embed.color = discord.Color.green()
            embed.description = f"You chose {valid[clean_user]}, Helix chose {valid[bot_choice]}.\n\n🎉 **You win!**"
            if bet > 0:
                await add_wallet(ctx.author.id, bet * 2)
                embed.description += f"\n💰 **Won ${bet * 2:,} coins!**"
        else:
            embed.color = discord.Color.red()
            embed.description = f"You chose {valid[clean_user]}, Helix chose {valid[bot_choice]}.\n\n😔 **Helix wins!**"

        set_owner_footer(embed, self.bot)
        await ctx.send(embed=embed)

    @game_group.command(name="rps")
    @commands.guild_only()
    async def slash_rps(self, ctx: commands.Context, choice: str, bet: Optional[int] = 0):
        """Play Rock Paper Scissors against Helix AI."""
        await self._do_rps(ctx, choice, bet)

    @commands.command(name="rps")
    @commands.guild_only()
    async def prefix_rps(self, ctx: commands.Context, choice: str, bet: Optional[int] = 0):
        """Play Rock Paper Scissors against Helix AI."""
        await self._do_rps(ctx, choice, bet)

    # --------------------------------------------------------------------------
    # Roulette
    # --------------------------------------------------------------------------
    async def _do_roulette(self, ctx: commands.Context, bet: int, space: str):
        if bet <= 0:
            await ctx.send("❌ Bet must be a positive integer.", ephemeral=True)
            return
        w, _ = await get_balance(ctx.author.id)
        if w < bet:
            await ctx.send(f"❌ Insufficient balance! You have **${w:,}** coins.", ephemeral=True)
            return

        space_clean = space.lower().strip()
        red_numbers = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}
        black_numbers = {2, 4, 6, 8, 10, 11, 13, 15, 17, 20, 22, 24, 26, 28, 29, 31, 33, 35}

        # Validate space
        valid_spaces = ["red", "black", "even", "odd", "1-18", "19-36", "1st12", "2nd12", "3rd12"]
        is_num = space_clean.isdigit() and 0 <= int(space_clean) <= 36
        if not is_num and space_clean not in valid_spaces:
            await ctx.send("❌ Invalid space! Choose `red`, `black`, `even`, `odd`, `1-18`, `19-36`, or a number `0-36`.", ephemeral=True)
            return

        await add_wallet(ctx.author.id, -bet)
        landed = random.randint(0, 36)
        landed_color = "🔴 Red" if landed in red_numbers else ("⚫ Black" if landed in black_numbers else "🟢 Green (0)")

        won = False
        multiplier = 0
        if is_num and landed == int(space_clean):
            won = True
            multiplier = 36
        elif space_clean == "red" and landed in red_numbers:
            won = True
            multiplier = 2
        elif space_clean == "black" and landed in black_numbers:
            won = True
            multiplier = 2
        elif space_clean == "even" and landed != 0 and landed % 2 == 0:
            won = True
            multiplier = 2
        elif space_clean == "odd" and landed % 2 == 1:
            won = True
            multiplier = 2
        elif space_clean == "1-18" and 1 <= landed <= 18:
            won = True
            multiplier = 2
        elif space_clean == "19-36" and 19 <= landed <= 36:
            won = True
            multiplier = 2
        elif space_clean == "1st12" and 1 <= landed <= 12:
            won = True
            multiplier = 3
        elif space_clean == "2nd12" and 13 <= landed <= 24:
            won = True
            multiplier = 3
        elif space_clean == "3rd12" and 25 <= landed <= 36:
            won = True
            multiplier = 3

        embed = discord.Embed(title="🎡 Roulette Wheel Spin")
        if won:
            payout = bet * multiplier
            await add_wallet(ctx.author.id, payout)
            embed.color = discord.Color.green()
            embed.description = (
                f"The ball landed on: **{landed} ({landed_color})**!\n\n"
                f"🎉 **You won! Multiplier: {multiplier}x (+${payout:,} coins)!**"
            )
        else:
            embed.color = discord.Color.red()
            embed.description = (
                f"The ball landed on: **{landed} ({landed_color})**.\n\n"
                f"😔 **You lost ${bet:,} coins.**"
            )

        set_owner_footer(embed, self.bot)
        await ctx.send(embed=embed)

    @game_group.command(name="roulette")
    @commands.guild_only()
    async def slash_roulette(self, ctx: commands.Context, bet: int, space: str):
        """Bet on European Roulette: red, black, even, odd, 1-18, 0-36."""
        await self._do_roulette(ctx, bet, space)

    @commands.command(name="roulette")
    @commands.guild_only()
    async def prefix_roulette(self, ctx: commands.Context, bet: int, space: str):
        """Bet on European Roulette: red, black, even, odd, 1-18, 0-36."""
        await self._do_roulette(ctx, bet, space)


async def setup(bot: commands.Bot):
    await bot.add_cog(Games(bot))

