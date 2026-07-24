"""Music service package scaffold.
This package contains the core music subsystem (player, queue, resolver, providers, etc.).
All implementations are lightweight stubs suitable for unit testing and for incrementally adding real providers/voice later.
"""
from .models import Track
from .queue import GuildQueue
from .resolver import resolve

__all__ = ["Track", "GuildQueue", "resolve"]
