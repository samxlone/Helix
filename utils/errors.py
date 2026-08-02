import os
import logging
from discord.ext import commands
from discord import app_commands

logger = logging.getLogger(__name__)



async def setup_error_handlers(bot: commands.Bot):
    # Global check to disable DM commands for non-owner users
    async def global_dm_restriction_check(ctx: commands.Context) -> bool:
        if ctx.guild is None:
            is_owner = False
            try:
                owner_id = os.getenv("OWNER_ID")
                if owner_id and ctx.author.id == int(owner_id):
                    is_owner = True
                else:
                    is_owner = await ctx.bot.is_owner(ctx.author)
            except Exception:
                is_owner = False

            if not is_owner:
                raise commands.CheckFailure("Bot commands in DMs are disabled for non-owner users.")
        return True

    if hasattr(bot, "check") and callable(getattr(bot, "check")):
        try:
            bot.check(global_dm_restriction_check)
        except Exception as e:
            logger.warning("Could not add global DM restriction check: %s", e)

    # App command global interaction check to disable DM commands for non-owner users
    async def global_app_cmd_dm_check(interaction) -> bool:
        if interaction.guild is None:
            is_owner = False
            try:
                owner_id = os.getenv("OWNER_ID")
                if owner_id and interaction.user.id == int(owner_id):
                    is_owner = True
                else:
                    is_owner = await bot.is_owner(interaction.user)
            except Exception:
                is_owner = False

            if not is_owner:
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ Bot commands in DMs are disabled for non-owner users. Please use commands inside a server channel.", ephemeral=True)
                return False
        return True

    if hasattr(bot, "tree") and hasattr(bot.tree, "interaction_check"):
        try:
            bot.tree.interaction_check(global_app_cmd_dm_check)
        except Exception as e:
            logger.warning("Could not add global app command DM restriction check: %s", e)

    @bot.event
    async def on_command_error(ctx, error):
        if hasattr(ctx, 'author'):
            logger.exception("Command error in %s: %s", ctx.author, error)
        else:
            logger.exception("Command error: %s", error)

        if isinstance(error, commands.CommandNotFound):
            return

        # Handle CheckFailure for DM restriction
        if isinstance(error, commands.CheckFailure):
            err_msg = str(error)
            if "DM commands are disabled" in err_msg or "restricted to the Bot Owner" in err_msg:
                await ctx.send("❌ Bot commands in DMs are disabled for non-owner users. Please use commands inside a server channel.", ephemeral=True)
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

        if isinstance(error, commands.BotMissingPermissions):
            missing = ", ".join(f"`{p}`" for p in error.missing_permissions)
            await ctx.send(f"❌ I (the bot) lack required permission(s) in this server: {missing}", ephemeral=True)
            return

        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"❌ Missing argument: `{error.param.name}`", ephemeral=True)
            return

        # Unwrap CommandInvokeError if wrapping Forbidden/HTTPException
        original_err = getattr(error, "original", error)
        if isinstance(original_err, commands.BotMissingPermissions):
            missing = ", ".join(f"`{p}`" for p in original_err.missing_permissions)
            await ctx.send(f"❌ I (the bot) lack required permission(s) in this server: {missing}", ephemeral=True)
            return

        # Fallback
        try:
            err_msg = str(original_err) or "An error occurred while running the command."
            await ctx.send(f"❌ Command Error: {err_msg}", ephemeral=True)
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
