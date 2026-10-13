"""Settings for the whole project.

Every value comes from an environment variable. That is what lets the same
code run on your laptop (.env file), in GitHub Actions (repository secrets)
and on Render (dashboard variables) without changing a single line.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")  # does nothing if the file is missing


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _flag(name: str, default: str = "false") -> bool:
    return _env(name, default).lower() in {"1", "true", "yes"}


def normalise_db_url(url: str) -> str:
    """Neon gives 'postgresql://...'. SQLAlchemy needs the driver name too."""
    if not url:
        return f"sqlite:///{ROOT / 'founderscout.db'}"
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


@dataclass(frozen=True)
class Settings:
    database_url: str
    llm_mode: str              # "fake" or "real"
    gemini_api_key: str
    groq_api_key: str
    model_fast: str            # cheap, many calls: reading posts, choosing links
    model_smart: str           # fewer calls: the research brief and the message
    model_review: str          # a different provider checks the writer's work
    gemini_gap: float
    groq_gap: float
    max_companies: int
    max_posts: int
    fit_threshold: int
    max_pages: int
    max_revisions: int
    page_chars: int
    browser_delay: float
    bot_contact: str
    allow_private_hosts: bool
    admin_password: str
    viewer_password: str
    profile_path: Path


@lru_cache
def get_settings() -> Settings:
    return Settings(
        database_url=normalise_db_url(_env("DATABASE_URL")),
        llm_mode=_env("LLM_MODE", "fake").lower(),
        gemini_api_key=_env("GEMINI_API_KEY"),
        groq_api_key=_env("GROQ_API_KEY"),
        model_fast=_env("MODEL_FAST", "gemini:gemini-3.5-flash-lite"),
        model_smart=_env("MODEL_SMART", "gemini:gemini-3.8-flash"),
        model_review=_env("MODEL_REVIEW", "groq:openai/gpt-oss-120b"),
        gemini_gap=float(_env("GEMINI_GAP", "6")),
        groq_gap=float(_env("GROQ_GAP", "20")),
        max_companies=int(_env("MAX_COMPANIES", "5")),
        max_posts=int(_env("MAX_POSTS", "25")),
        fit_threshold=int(_env("FIT_THRESHOLD", "60")),
        max_pages=int(_env("MAX_PAGES", "4")),
        max_revisions=int(_env("MAX_REVISIONS", "2")),
        page_chars=int(_env("PAGE_CHARS", "6000")),
        browser_delay=float(_env("BROWSER_DELAY", "2")),
        bot_contact=_env("BOT_CONTACT", "https://github.com/YOUR_USERNAME/founderscout"),
        allow_private_hosts=_flag("ALLOW_PRIVATE_HOSTS"),
        admin_password=_env("ADMIN_PASSWORD"),
        viewer_password=_env("VIEWER_PASSWORD"),
        profile_path=Path(_env("PROFILE_PATH", str(ROOT / "my_profile.json"))),
    )


@lru_cache
def load_profile() -> dict:
    """Your own details. The writer and the reviewer both read this file."""
    return json.loads(get_settings().profile_path.read_text(encoding="utf-8"))


def profile_urls(profile: dict) -> list[str]:
    """Every link that belongs to you. The reviewer allows only these."""
    urls = list(profile.get("links", {}).values())
    urls += [p["url"] for p in profile.get("projects", []) if p.get("url")]
    return urls
