import os
from pathlib import Path
from dotenv import load_dotenv
import yaml
import logging
from typing import Any, Optional
from pydantic import BaseModel, Field, ValidationError

load_dotenv()
logger = logging.getLogger(__name__)

DEFAULTS_FILE = Path(__file__).resolve().parent / "defaults.yaml"


class DatabaseConfig(BaseModel):
    path: Optional[str] = Field(default="data/database.sqlite3")
    url: Optional[str] = None


class BotConfig(BaseModel):
    prefix: str = Field(default="!")
    log_level: str = Field(default="INFO")
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    owner_id: Optional[int] = None


class ConfigManager:
    def __init__(self, defaults_file: Path | None = None):
        self.defaults_file = defaults_file or DEFAULTS_FILE
        self._data: dict[str, Any] = {}
        self._model: Optional[BotConfig] = None

    def _load_defaults(self) -> dict:
        if self.defaults_file.exists():
            try:
                with open(self.defaults_file, "r", encoding="utf-8") as fh:
                    return yaml.safe_load(fh) or {}
            except Exception:
                logger.exception("Failed to load defaults.yaml")
                return {}
        return {}

    def load(self):
        data = self._load_defaults()

        # Overlay environment variables
        prefix = os.getenv("PREFIX", data.get("prefix", "!"))
        log_level = os.getenv("LOG_LEVEL", data.get("log_level", "INFO"))
        db_url = os.getenv("DATABASE_URL")
        db_path = data.get("database", {}).get("path")
        owner_raw = os.getenv("OWNER_ID")

        try:
            owner_id = int(owner_raw) if owner_raw else data.get("owner_id")
        except Exception:
            owner_id = None

        db_config = {"path": db_path, "url": db_url} if (db_path or db_url) else {}

        candidate = {
            "prefix": prefix,
            "log_level": log_level,
            "database": db_config,
            "owner_id": owner_id,
        }

        try:
            self._model = BotConfig(**candidate)
            # use pydantic v2 model_dump instead of deprecated dict()
            try:
                self._data = self._model.model_dump()
            except Exception:
                # fallback for older pydantic versions
                self._data = self._model.dict()
        except ValidationError as exc:
            logger.exception("Configuration validation failed: %s", exc)
            # Fallback to raw values
            self._data = candidate

        return self

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def as_dict(self) -> dict:
        return dict(self._data)


# convenience
config_manager = ConfigManager()
config_manager.load()
