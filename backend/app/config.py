"""Configuration management for RedditWatch."""

import os
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class RedditConfig(BaseModel):
    """Reddit API configuration."""

    client_id: str = ""
    client_secret: str = ""
    user_agent: str = "RedditWatch/1.0 (self-hosted market research)"


class OllamaConfig(BaseModel):
    """Ollama LLM configuration."""

    base_url: str = "http://localhost:11434"
    model: str = "llama3.1:8b"
    timeout: int = 120


class ClaudeConfig(BaseModel):
    """Claude API configuration."""

    model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 4096


class OpenAIConfig(BaseModel):
    """OpenAI API configuration."""

    model: str = "gpt-4o-mini"
    max_tokens: int = 4096


class LLMConfig(BaseModel):
    """LLM provider configuration."""

    provider: str = "ollama"
    fallback_chain: list[str] = Field(default_factory=lambda: ["claude", "openai"])
    ollama: OllamaConfig = Field(default_factory=OllamaConfig)
    claude: ClaudeConfig = Field(default_factory=ClaudeConfig)
    openai: OpenAIConfig = Field(default_factory=OpenAIConfig)


class SortModeConfig(BaseModel):
    """A single sort mode configuration."""

    sort: str = "hot"
    t: Optional[str] = None  # Time filter for "top" sort (hour, day, week, month, year, all)


class CollectionConfig(BaseModel):
    """Reddit collection settings."""

    interval_minutes: int = 30
    posts_per_subreddit: int = 25
    include_comments: bool = True
    max_comments_per_post: int = 50
    max_comment_depth: int = 5  # Max depth for nested replies (0 = top-level only)
    sort_by: str = "hot"

    # Multi-sort / deep collection
    sort_modes: list[dict] = Field(default_factory=lambda: [
        {"sort": "hot"},
        {"sort": "new"},
        {"sort": "top", "t": "week"},
        {"sort": "top", "t": "month"},
        {"sort": "top", "t": "year"},
    ])
    max_pages_per_sort: int = 5
    deep_collect_enabled: bool = False
    deep_sort_modes_per_run: int = 3  # How many sort modes per deep run (rotates)
    concurrent_subreddits: int = 1  # Sequential by default to work with rate limiter
    rate_limit_delay: float = 1.0  # Base delay between requests (seconds)
    rate_limit_rpm: float = 8.0  # Global rate limit: requests per minute
    comment_min_score: int = 5  # Only fetch comments for posts above this score
    comments_per_collection: int = 3  # Max comment-fetches per subreddit per run

    # Scheduling
    auto_schedule: bool = False

    # Startup catch-up collection
    collect_on_startup: bool = True       # Auto-collect if data is stale when app starts
    stale_threshold_hours: float = 6.0    # Hours before data is considered stale


class AnalysisConfig(BaseModel):
    """Analysis settings."""

    auto_analyze: bool = True
    batch_size: int = 5
    min_score_threshold: int = 3


class ScoringConfig(BaseModel):
    """Scoring weights for theme calculation."""

    frequency_weight: float = 0.4
    intensity_weight: float = 0.6


class CORSConfig(BaseModel):
    """CORS configuration."""

    allowed_origins: list[str] = Field(default_factory=lambda: ["http://localhost:8000", "http://127.0.0.1:8000"])
    allow_credentials: bool = False
    allow_methods: list[str] = Field(default_factory=lambda: ["*"])
    allow_headers: list[str] = Field(default_factory=lambda: ["*"])


class ServerConfig(BaseModel):
    """Server configuration."""

    host: str = "0.0.0.0"
    port: int = 8000
    cors: CORSConfig = Field(default_factory=CORSConfig)


class Config(BaseModel):
    """Main application configuration."""

    edition: str = Field(default_factory=lambda: os.getenv("EDITION", "oss"))
    reddit: RedditConfig = Field(default_factory=RedditConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    collection: CollectionConfig = Field(default_factory=CollectionConfig)
    analysis: AnalysisConfig = Field(default_factory=AnalysisConfig)
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)

    @property
    def is_cloud(self) -> bool:
        return self.edition == "cloud"


def _substitute_env_vars(value: str) -> str:
    """Substitute ${VAR} patterns with environment variables."""
    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        env_var = value[2:-1]
        return os.getenv(env_var, "")
    return value


def _process_config_dict(d: dict) -> dict:
    """Recursively process config dict to substitute env vars."""
    result = {}
    for key, value in d.items():
        if isinstance(value, dict):
            result[key] = _process_config_dict(value)
        elif isinstance(value, str):
            result[key] = _substitute_env_vars(value)
        else:
            result[key] = value
    return result


def load_config(config_path: Optional[Path] = None) -> Config:
    """
    Load configuration from YAML file and environment variables.

    Priority:
    1. Environment variables (for secrets)
    2. YAML config file
    3. Default values
    """
    # Default config path
    if config_path is None:
        config_path = Path(__file__).parent.parent / "config.yaml"

    # Start with defaults
    config_dict = {}

    # Load YAML if exists
    if config_path.exists():
        with open(config_path) as f:
            yaml_config = yaml.safe_load(f) or {}
            config_dict = _process_config_dict(yaml_config)

    # Override with environment variables
    env_overrides = {
        "reddit": {
            "client_id": os.getenv("REDDIT_CLIENT_ID", ""),
            "client_secret": os.getenv("REDDIT_CLIENT_SECRET", ""),
        }
    }

    # Merge env overrides (only non-empty values)
    for section, values in env_overrides.items():
        if section not in config_dict:
            config_dict[section] = {}
        for key, value in values.items():
            if value:  # Only override if env var is set
                config_dict[section][key] = value

    return Config(**config_dict)


# Global config instance
_config: Optional[Config] = None


def get_config() -> Config:
    """Get the global config instance."""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def reload_config(config_path: Optional[Path] = None) -> Config:
    """Reload configuration from file."""
    global _config
    _config = load_config(config_path)
    return _config
