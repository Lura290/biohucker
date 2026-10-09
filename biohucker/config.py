import os
from dataclasses import dataclass

from dotenv import load_dotenv

DEFAULT_MODEL = "google/gemma-4-31b-it:free"
DEFAULT_DATABASE_URL = "sqlite:///data/biohucker.db"


@dataclass(frozen=True)
class Settings:
    openrouter_api_key: str | None
    openrouter_model: str
    database_url: str


def load_settings() -> Settings:
    load_dotenv()
    return Settings(
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY") or None,
        openrouter_model=os.getenv("OPENROUTER_MODEL") or DEFAULT_MODEL,
        database_url=os.getenv("DATABASE_URL") or DEFAULT_DATABASE_URL,
    )
