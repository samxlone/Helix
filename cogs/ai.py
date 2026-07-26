import os
import re
import logging
from typing import Optional, Dict, List
import discord
from discord.ext import commands

from utils.ai_service import get_ai_response, generate_image_gemini
from utils.config_service import get_guild_config, set_guild_config
from utils.ai_limits import check_and_increment_text_limit, check_and_increment_image_limit, get_user_daily_usage


logger = logging.getLogger(__name__)



class AICog(commands.Cog):
    """AI Chatbot Powered by OpenAI & Google Gemini"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Sliding memory buffer per channel: {channel_id: [{"role": "user", "content": "..."}, ...]}
        self.memory_buffers: Dict[int, List[Dict[str, str]]] = {}

    def _get_history(self, channel_id: int) -> List[Dict[str, str]]:
        return self.memory_buffers.get(channel_id, [])

    def _append_history(self, channel_id: int, user_text: str, assistant_text: str):
        buf = self.memory_buffers.setdefault(channel_id, [])
        buf.append({"role": "user", "content": user_text})
        buf.append({"role": "assistant", "content": assistant_text})
        # Keep last 10 turns (20 messages)
        if len(buf) > 20:
            self.memory_buffers[channel_id] = buf[-20:]

    async def _is_owner(self, user: discord.User) -> bool:
        owner_id_str = os.getenv("OWNER_ID")
        if owner_id_str and user.id == int(owner_id_str):
            return True
        try:
            return await self.bot.is_owner(user)
        except Exception:
            return False

    @commands.Cog.listener("on_message")
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        is_owner = await self._is_owner(message.author)

        # Handle DMs for Bot Owner
        if not message.guild:
            if is_owner:
                prompt = message.content.strip()
                if prompt and not prompt.startswith("!"):
                    async with message.channel.typing():
                        history = self._get_history(message.channel.id)
                        response = await get_ai_response(prompt, history=history)
                        self._append_history(message.channel.id, prompt, response)
                        await message.channel.send(response[:2000])
            return

        # Server message logic
        cfg = await get_guild_config(message.guild.id)
        ai_channel_id = cfg.get("ai_channel_id")
        ai_provider = cfg.get("ai_provider") or "gemini"

        is_bot_mentioned = self.bot.user in message.mentions if self.bot.user else False
        is_reply_to_bot = (
            message.reference
            and message.reference.resolved
            and isinstance(message.reference.resolved, discord.Message)
            and self.bot.user
            and message.reference.resolved.author.id == self.bot.user.id
        )
        is_in_ai_channel = ai_channel_id and message.channel.id == int(ai_channel_id)

        # Scoping rule: For regular users, auto-replies ONLY work in designated AI channel!
        if not is_owner:
            if not is_in_ai_channel:
                if is_bot_mentioned or is_reply_to_bot:
                    if ai_channel_id:
                        await message.channel.send(
                            f"❌ AI Chat is restricted to <#{ai_channel_id}>. Please send your question there!",
                            delete_after=10
                        )
                    else:
                        await message.channel.send(
                            "❌ AI Chat is not active here. Ask an admin to set an AI channel using `!setaichannel #ai-chat`!",
                            delete_after=10
                        )
                return
        else:
            # Bot Owner can interact anywhere, but if not in AI channel and not mentioned/replied/command, skip normal chat
            if not is_in_ai_channel and not is_bot_mentioned and not is_reply_to_bot:
                return

        # Clean prompt text (strip bot mention)
        prompt = message.content
        if self.bot.user:
            prompt = re.sub(f"<@!?{self.bot.user.id}>", "", prompt).strip()

        if not prompt or prompt.startswith("!"):
            return

        # Handle direct image generation triggers in AI channel or mentions (e.g. "imagine ...", "draw ...")
        lower_p = prompt.lower().strip()
        image_triggers = ("imagine ", "draw ", "generate image ", "paint ", "picture of ")
        if lower_p.startswith(image_triggers):
            if not is_owner:
                allowed, curr = await check_and_increment_image_limit(message.author.id)
                if not allowed:
                    await message.reply("❌ **Daily Limit Reached**: You have reached your daily limit of **2 AI image generations per day** (2/2). Please try again tomorrow!")
                    return

            img_prompt = prompt
            for trg in image_triggers:
                if lower_p.startswith(trg):
                    img_prompt = prompt[len(trg):].strip()
                    break
            if img_prompt:
                async with message.channel.typing():
                    import io
                    img_bytes = await generate_image_gemini(img_prompt)
                    if img_bytes:
                        file = discord.File(fp=io.BytesIO(img_bytes), filename="imagine.png")
                        embed = discord.Embed(
                            title=f"🎨 AI Image: {img_prompt[:100]}",
                            color=discord.Color.from_rgb(0, 180, 216)
                        )
                        embed.set_image(url="attachment://imagine.png")
                        embed.set_footer(text=f"Requested by {message.author.display_name} • Powered by Gemini Imagen")
                        await message.reply(embed=embed, file=file)
                    else:
                        await message.reply("❌ Failed to generate image. Please ensure prompt is valid.")
            return

        if not is_owner:
            allowed, curr = await check_and_increment_text_limit(message.author.id)
            if not allowed:
                await message.reply("❌ **Daily Limit Reached**: You have reached your daily limit of **10 AI questions per day** (10/10). Please try again tomorrow!")
                return

        async with message.channel.typing():
            history = self._get_history(message.channel.id)
            response = await get_ai_response(prompt, history=history, provider=ai_provider)
            self._append_history(message.channel.id, prompt, response)

            if len(response) <= 2000:
                await message.reply(response)
            else:
                chunks = [response[i:i+1990] for i in range(0, len(response), 1990)]
                for idx, chunk in enumerate(chunks):
                    if idx == 0:
                        await message.reply(chunk)
                    else:
                        await message.channel.send(chunk)

    @commands.hybrid_command(name="ask")
    @commands.guild_only()
    async def ask(self, ctx: commands.Context, *, prompt: str):
        """Ask the AI a question or prompt (Powered by OpenAI & Gemini)."""
        is_owner = await self._is_owner(ctx.author)
        cfg = await get_guild_config(ctx.guild.id)
        ai_channel_id = cfg.get("ai_channel_id")
        ai_provider = cfg.get("ai_provider") or "openai"

        if not is_owner and ai_channel_id and ctx.channel.id != int(ai_channel_id):
            await ctx.send(f"❌ AI Chat commands are restricted to <#{ai_channel_id}>. Please use the AI channel!", ephemeral=True)
            return

        if not is_owner:
            allowed, curr = await check_and_increment_text_limit(ctx.author.id)
            if not allowed:
                await ctx.send("❌ **Daily Limit Reached**: You have reached your daily limit of **10 AI questions per day** (10/10). Please try again tomorrow!", ephemeral=True)
                return

        await ctx.defer()
        history = self._get_history(ctx.channel.id)
        response = await get_ai_response(prompt, history=history, provider=ai_provider)
        self._append_history(ctx.channel.id, prompt, response)

        if len(response) <= 2000:
            await ctx.send(response)
        else:
            chunks = [response[i:i+1990] for i in range(0, len(response), 1990)]
            for chunk in chunks:
                await ctx.send(chunk)

    @commands.hybrid_command(name="imagine")
    @commands.guild_only()
    async def imagine(self, ctx: commands.Context, *, prompt: str):
        """Generate an AI image from text using Google Gemini Imagen API."""
        import io
        is_owner = await self._is_owner(ctx.author)
        cfg = await get_guild_config(ctx.guild.id)
        ai_channel_id = cfg.get("ai_channel_id")

        if not is_owner and ai_channel_id and ctx.channel.id != int(ai_channel_id):
            await ctx.send(f"❌ AI commands are restricted to <#{ai_channel_id}>. Please use the AI channel!", ephemeral=True)
            return

        if not is_owner:
            allowed, curr = await check_and_increment_image_limit(ctx.author.id)
            if not allowed:
                await ctx.send("❌ **Daily Limit Reached**: You have reached your daily limit of **2 AI image generations per day** (2/2). Please try again tomorrow!", ephemeral=True)
                return

        await ctx.defer()
        img_bytes = await generate_image_gemini(prompt)
        if not img_bytes:
            await ctx.send("❌ Failed to generate image. Please ensure prompt is valid.", ephemeral=True)
            return

        file = discord.File(fp=io.BytesIO(img_bytes), filename="imagine.png")
        embed = discord.Embed(
            title=f"🎨 AI Image: {prompt[:100]}",
            color=discord.Color.from_rgb(0, 180, 216)
        )
        embed.set_image(url="attachment://imagine.png")
        embed.set_footer(text=f"Requested by {ctx.author.display_name} • Powered by Gemini Imagen")
        await ctx.send(embed=embed, file=file)

    @commands.hybrid_command(name="ailimit", aliases=["aiusage", "ailimits"])
    @commands.guild_only()
    async def ailimit(self, ctx: commands.Context):
        """Check your daily AI usage and remaining limits."""
        is_owner = await self._is_owner(ctx.author)
        text_cnt, img_cnt = await get_user_daily_usage(ctx.author.id)

        embed = discord.Embed(
            title=f"🤖 AI Daily Usage & Limits for {ctx.author.display_name}",
            color=discord.Color.blue()
        )
        if is_owner:
            embed.description = "👑 **Bot Owner Status**: You have **unlimited** AI questions and image generations!"
        else:
            embed.add_field(name="💬 Text Questions", value=f"`{text_cnt} / 10` questions used today", inline=False)
            embed.add_field(name="🎨 Image Generations", value=f"`{img_cnt} / 2` images used today", inline=False)
            embed.set_footer(text="Limits reset daily at 00:00 UTC")

        await ctx.send(embed=embed)



    @commands.command(name="setaichannel", aliases=["ai_channel", "setaichat"])
    @commands.guild_only()
    async def setaichannel(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None, option: Optional[str] = None):
        """Set or reset the dedicated AI Chat channel for this server (Admins/Owners only)."""
        is_allowed = (
            ctx.author.guild_permissions.manage_guild
            or ctx.author.guild_permissions.administrator
            or getattr(ctx.guild, "owner_id", None) == ctx.author.id
            or await self._is_owner(ctx.author)
        )
        if not is_allowed:
            await ctx.send("❌ You need the **Manage Server** or **Administrator** permission to set the AI channel.")
            return

        opt_str = (option or "").lower().strip()
        if not channel and ctx.message and ctx.message.content:
            words = ctx.message.content.strip().split()[1:]
            if words:
                opt_str = words[0].lower().strip()

        if opt_str in ("reset", "off", "clear", "none", "disable"):
            await set_guild_config(ctx.guild.id, {"ai_channel_id": None})
            await ctx.send("✅ Dedicated AI chat channel disabled. Auto-replies are turned off.")
            return

        target_ch = channel or ctx.channel
        if not target_ch or not hasattr(target_ch, "id"):
            await ctx.send("❌ Please mention a valid text channel or type `reset`. Usage: `!setaichannel #ai-chat`")
            return

        await set_guild_config(ctx.guild.id, {"ai_channel_id": target_ch.id})
        await ctx.send(f"🤖 Dedicated AI chat channel set to {target_ch.mention}! All chat messages in this channel will get AI responses.")

    @commands.command(name="setaiprovider", aliases=["aiprovider"])
    @commands.guild_only()
    async def setaiprovider(self, ctx: commands.Context, provider: str):
        """Set default AI provider for this server: 'openai' (GPT-4o-mini) or 'gemini' (Gemini 1.5 Flash)."""
        is_allowed = (
            ctx.author.guild_permissions.manage_guild
            or ctx.author.guild_permissions.administrator
            or getattr(ctx.guild, "owner_id", None) == ctx.author.id
            or await self._is_owner(ctx.author)
        )
        if not is_allowed:
            await ctx.send("❌ You need the **Manage Server** or **Administrator** permission to change the AI provider.")
            return

        p_clean = provider.lower().strip()
        if p_clean not in ("openai", "gemini", "gpt"):
            await ctx.send("❌ Invalid provider. Choose `openai` or `gemini`.")
            return

        selected = "openai" if p_clean in ("openai", "gpt") else "gemini"
        await set_guild_config(ctx.guild.id, {"ai_provider": selected})
        display_name = "OpenAI (GPT-4o-mini)" if selected == "openai" else "Google Gemini (Gemini 1.5 Flash)"
        await ctx.send(f"✅ AI Chatbot provider set to **{display_name}**!")

    @commands.hybrid_command(name="clearchat", aliases=["clearai", "resetai"])
    @commands.guild_only()
    async def clearchat(self, ctx: commands.Context):
        """Clear AI conversation memory buffer for this channel."""
        if ctx.channel.id in self.memory_buffers:
            self.memory_buffers.pop(ctx.channel.id, None)
        await ctx.send("🧠 Cleared AI conversation memory buffer for this channel!")


async def setup(bot: commands.Bot):
    await bot.add_cog(AICog(bot))
