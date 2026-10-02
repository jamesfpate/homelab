"""Settings from environment variables (set in stacks/music.yaml)."""

import os
from dataclasses import dataclass
from pathlib import Path


def _env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if value is None:
        raise SystemExit(f"missing required env var {name}")
    return value


def _bool(name: str, default: bool) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Config:
    navidrome_url: str
    navidrome_user: str
    navidrome_password: str
    lb_user: str
    lb_token: str
    slskd_url: str
    slskd_api_key: str
    music_root: Path
    library_dir: Path
    inbox_dir: Path
    staging_dir: Path
    slskd_downloads: Path
    state_dir: Path
    dry_run: bool
    inbox_size: int
    played_grace_hours: float
    heard_feedback: str
    fresh_days: int
    fresh_max_releases: int
    fresh_types: tuple[str, ...]
    reddit_limit: int
    reddit_windows: tuple[str, ...]
    ollama_url: str
    ollama_model: str
    ollama_timeout_s: int
    llm_filter: bool
    llm_min_score: int
    lidarr_url: str
    lidarr_api_key: str
    lastfm_api_key: str
    lastfm_seeds: int
    download_timeout_s: int


def load() -> Config:
    music_root = Path(_env("MUSIC_ROOT", "/music"))
    return Config(
        navidrome_url=_env("NAVIDROME_URL").rstrip("/"),
        navidrome_user=_env("NAVIDROME_USER"),
        navidrome_password=_env("NAVIDROME_PASSWORD"),
        lb_user=_env("LB_USER"),
        lb_token=_env("LB_TOKEN"),
        slskd_url=_env("SLSKD_URL", "").rstrip("/"),
        slskd_api_key=_env("SLSKD_API_KEY", ""),
        music_root=music_root,
        library_dir=Path(_env("LIBRARY_DIR", str(music_root / "library"))),
        inbox_dir=Path(_env("INBOX_DIR", str(music_root / "inbox"))),
        staging_dir=Path(_env("STAGING_DIR", str(music_root / ".staging"))),
        slskd_downloads=Path(_env("SLSKD_DOWNLOADS", "/slskd")),
        state_dir=Path(_env("STATE_DIR", "/config")),
        dry_run=_bool("DRY_RUN", True),
        inbox_size=int(_env("INBOX_SIZE", "50")),  # unheard tracks kept in the inbox; ingest never goes past it
        played_grace_hours=float(_env("PLAYED_GRACE_HOURS", "24")),  # time to star after hearing a track
        heard_feedback=_env("HEARD_FEEDBACK", "none").lower(),  # "hate": played-not-starred also tells ListenBrainz you dislike it
        fresh_days=int(_env("FRESH_DAYS", "7")),
        fresh_max_releases=int(_env("FRESH_MAX_RELEASES", "10")),
        fresh_types=tuple(t.strip().lower() for t in _env("FRESH_TYPES", "album,ep,single").split(",")),
        reddit_limit=int(_env("REDDIT_LIMIT", _env("LISTENTOTHIS_LIMIT", "200"))),  # per subreddit
        reddit_windows=tuple(w.strip() for w in _env("REDDIT_WINDOWS", "all,month,week").split(",") if w.strip()),
        ollama_url=_env("OLLAMA_URL", "").rstrip("/"),  # empty = no LLM stage
        ollama_model=_env("OLLAMA_MODEL", "gemma4:26b-a4b-it-qat"),
        ollama_timeout_s=int(_env("OLLAMA_TIMEOUT_S", "300")),
        llm_filter=_bool("LLM_FILTER", False),  # false = shadow mode: score and log, never skip
        llm_min_score=int(_env("LLM_MIN_SCORE", "5")),
        lidarr_url=_env("LIDARR_URL", "").rstrip("/"),  # album stars -> Lidarr (wants)
        lidarr_api_key=_env("LIDARR_API_KEY", ""),
        lastfm_api_key=_env("LASTFM_API_KEY", ""),  # source: similar artists to the ones you starred
        lastfm_seeds=int(_env("LASTFM_SEEDS", "8")),
        download_timeout_s=int(_env("DOWNLOAD_TIMEOUT_MIN", "20")) * 60,
    )
