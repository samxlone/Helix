import os
import logging
from discord.ext import commands
from discord import app_commands

logger = logging.getLogger(__name__)



async def setup_error_handlers(bot: commands.Bot):
    @bot.event
    async def on_command_error(ctx, error):
        if hasattr(ctx, 'author'):
            logger.exception("Command error in %s: %s", ctx.author, error)
        else:
            logger.exception("Command error: %s", error)

        if isinstance(error, commands.CommandNotFound):
            return

        # Owner bypass for NoPrivateMessage (guild_only checks) in DMs
        if isinstance(error, commands.NoPrivateMessage):
            is_owner = False
            try:
                owner_id = os.getenv("OWNER_ID")
                if owner_id and ctx.author.id == int(owner_id):
                    is_owner = True
                else:
                    is_owner = await bot.is_owner(ctx.author)
            except Exception:
                pass

            if is_owner and ctx.command:
                try:
                    await ctx.command.reinvoke(ctx)
                    return
                except Exception as exc:
                    logger.exception("Failed to reinvoke %s for owner in DM: %s", ctx.command.name, exc)

            await ctx.send("❌ This command can only be used inside a server channel.", ephemeral=True)
            return

        if isinstance(error, commands.NotOwner):
            await ctx.send("❌ This command is restricted to the Bot Owner.", ephemeral=True)
            return

        if isinstance(error, commands.MissingPermissions):
            missing = ", ".join(f"`{p}`" for p in error.missing_permissions)
            await ctx.send(f"❌ You lack required permission(s): {missing}", ephemeral=True)
            return

        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"❌ Missing argument: `{error.param.name}`", ephemeral=True)
            return

        # Fallback
        try:
            await ctx.send("An error occurred while running the command.", ephemeral=True)
        except Exception:
            pass


    # App command (slash) error handler
    @bot.tree.error
    async def on_app_command_error(interaction, error):
        logger.exception("App command error: %s", error)
        try:
            if interaction.response.is_done():
                await interaction.followup.send("An internal error occurred.", ephemeral=True)
            else:
                await interaction.response.send_message("An internal error occurred.", ephemeral=True)
        except Exception:
            pass

    return
