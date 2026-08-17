"""BugTrail configuration — bugtrail.toml + privacy model.

The AI API key is never stored in the config file. It is read from an
environment variable (BUGTRAIL_API_KEY by default) so secrets stay out
of the repository.
"""
from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic import BaseModel, Field

CONFIG_NAME = "bugtrail.toml"
DEFAULT_API_KEY_ENV = "BUGTRAIL_API_KEY"

PRIVACY_SCOPES = ("local", "scoped", "full")


class AIConfig(BaseModel):
    """OpenAI-compatible endpoint. Works with OpenAI, Groq, Ollama, etc."""

    provider: str = "openai-compatible"
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    api_key_env: str = DEFAULT_API_KEY_ENV
    temperature: float = 0.2
    timeout_seconds: float = 60.0


class PrivacyConfig(BaseModel):
    # local = no AI calls at all; scoped = frames + snippets only;
    # full = full files may be shared (opt-in).
    scope: str = "scoped"

    def model_post_init(self, __context) -> None:
        if self.scope not in PRIVACY_SCOPES:
            raise ValueError(f"privacy.scope must be one of {PRIVACY_SCOPES}")


class BugTrailConfig(BaseModel):
    ai: AIConfig = Field(default_factory=AIConfig)
    privacy: PrivacyConfig = Field(default_factory=PrivacyConfig)

    @property
    def ai_enabled(self) -> bool:
        return self.privacy.scope != "local"

    def api_key(self) -> str | None:
        import os

        value = os.environ.get(self.ai.api_key_env)
        return value or None


def default_config() -> BugTrailConfig:
    return BugTrailConfig()


def load_config(repo_root: Path) -> BugTrailConfig:
    path = repo_root / CONFIG_NAME
    if not path.exists():
        return default_config()
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    try:
        ai = AIConfig.model_validate(data.get("ai") or {})
        privacy = PrivacyConfig.model_validate(data.get("privacy") or {})
        return BugTrailConfig(ai=ai, privacy=privacy)
    except Exception as exc:  # pragma: no cover - defensive
        raise ValueError(f"Invalid {CONFIG_NAME}: {exc}") from exc


CONFIG_TEMPLATE = """\
# BugTrail configuration.
# The API key is never stored here — set {api_key_env} in your environment.
# Providers are OpenAI-compatible: OpenAI, Groq (free tier), Ollama (local, $0), ...

[bugtrail]

[ai]
provider = "openai-compatible"
base_url = "https://api.openai.com/v1"
model = "gpt-4o-mini"
api_key_env = "{api_key_env}"

[privacy]
# local  = no AI calls at all (deterministic only)
# scoped = only stack frames + small snippets leave your machine (default)
# full   = full files may be sent to the provider (opt-in)
scope = "scoped"
"""


def write_default_config(repo_root: Path) -> Path:
    path = repo_root / CONFIG_NAME
    if path.exists():
        return path
    path.write_text(
        CONFIG_TEMPLATE.format(api_key_env=DEFAULT_API_KEY_ENV), encoding="utf-8"
    )
    return path
