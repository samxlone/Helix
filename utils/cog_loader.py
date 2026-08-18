import importlib
import pkgutil
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


async def load_cogs(bot, package="cogs"):
    """Dynamically load all cogs from the given package (folder).
    Expects Python files exposing a setup(bot) or a Cog subclass to be loaded as an extension.

    This function is async because discord.py's load_extension may be a coroutine in some versions.
    """
    # determine package path relative to this utils module (repo root / package)
    package_path = Path(__file__).resolve().parents[1] / package
    if not package_path.exists():
        logger.warning("Cogs package folder '%s' does not exist", package_path)
        return

    for finder, name, ispkg in pkgutil.iter_modules([str(package_path)]):
        if name.startswith("_"):
            continue
        module_name = f"{package}.{name}"
        if module_name in getattr(bot, "extensions", {}):
            continue
        try:
            # load_extension may be a coroutine in some discord.py variants; await if needed
            res = bot.load_extension(module_name)
            if hasattr(res, "__await__"):
                await res
            logger.info("Loaded cog: %s", module_name)
        except Exception as exc:
            logger.exception("Failed to load cog %s: %s", module_name, exc)

