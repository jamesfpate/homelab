"""Event history in SQLite (/config/musicflow.db): where each inbox track came from and what happened to it.

Actions: added, not_found (ingest); kept, disliked, heard, stale (promote). The report reads this.
"""

import re
import sqlite3
from datetime import datetime
from pathlib import Path

from .config import Config

_SCHEMA = """
create table if not exists events (
  id integer primary key,
  ts text not null,
  action text not null,
  source text,
  artist text,
  title text,
  album text,
  path text,
  batch text
);
create index if not exists events_ts on events (ts);
create index if not exists events_path on events (path);
create table if not exists scores (
  id integer primary key,
  ts text not null,
  batch text,
  source text,
  artist text,
  title text,
  score integer,
  reason text
);
"""
_BATCH = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def connect(cfg: Config) -> sqlite3.Connection:
    con = sqlite3.connect(cfg.state_dir / "musicflow.db")
    con.row_factory = sqlite3.Row
    con.executescript(_SCHEMA)
    return con


def record(cfg: Config, action: str, *, source: str | None = None, artist: str = "", title: str = "",
           album: str = "", path: Path | None = None, batch: str | None = None) -> None:
    if cfg.dry_run:
        return
    if path is not None and source is None:
        source = source_from_path(cfg, path)
    with connect(cfg) as con:
        con.execute(
            "insert into events (ts, action, source, artist, title, album, path, batch) values (?,?,?,?,?,?,?,?)",
            (datetime.now().isoformat(timespec="seconds"), action, source, artist, title, album,
             str(path) if path else None, batch),
        )


def record_scores(cfg: Config, batch: str, rows: list[tuple[str, str, str, int, str]]) -> None:
    """rows: (source, artist, title, score, reason). Logged even in dry-run so shadow scoring can be reviewed."""
    ts = datetime.now().isoformat(timespec="seconds")
    with connect(cfg) as con:
        con.executemany("insert into scores (ts, batch, source, artist, title, score, reason) values (?,?,?,?,?,?,?)",
                        [(ts, batch, *r) for r in rows])


def decided_artists(cfg: Config) -> dict[str, list[str]]:
    """Artists the listener kept / disliked from earlier inbox rounds (most recent first, deduplicated)."""
    out = {"kept": [], "disliked": []}
    with connect(cfg) as con:
        for action in out:
            seen = set()
            for r in con.execute("select artist from events where action=? and artist<>'' order by id desc", (action,)):
                if r["artist"].lower() not in seen:
                    seen.add(r["artist"].lower())
                    out[action].append(r["artist"])
    return out


def source_from_path(cfg: Config, path: Path) -> str | None:
    """inbox/<source>/<YYYY-MM-DD>/... -> <source> (sources may contain '/', e.g. r/indieheads)."""
    try:
        parts = path.resolve().relative_to(cfg.inbox_dir.resolve()).parts
    except ValueError:
        return None
    for i, part in enumerate(parts):
        if _BATCH.match(part):
            return "/".join(parts[:i]) or None
    return None
