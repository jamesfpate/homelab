"""One-off: pull liked tracks from an Exportify CSV straight into the library (skips the inbox).

  docker exec musicflow python -m musicflow seed /config/liked.csv --limit 500

Soulseek only by default: these are keepers, so lossy YouTube copies aren't worth it.
Albums you want whole go through Lidarr (Usenet) instead.
"""

import csv
import time
from pathlib import Path

from . import youtube
from .config import Config
from .navidrome import Navidrome
from .promote import _beets_import
from .slskd import Slskd
from .util import ensure_tags, log, move_into, track_key


def _read(path: Path) -> list[tuple[str, str, str]]:
    rows = []
    with path.open(newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            artist = (row.get("Artist Name(s)") or row.get("Artist") or "").split(",")[0].strip()
            title = (row.get("Track Name") or row.get("Title") or "").strip()
            added = row.get("Added At") or ""
            if artist and title:
                rows.append((added, artist, title))
    rows.sort(reverse=True)  # newest likes first
    return rows


def run(cfg: Config, csv_path: Path, limit: int, allow_youtube: bool) -> None:
    nd = Navidrome(cfg.navidrome_url, cfg.navidrome_user, cfg.navidrome_password)
    owned = {track_key(s.artist, s.title) for s in nd.all_songs()}
    todo = [(a, t) for _, a, t in _read(csv_path) if track_key(a, t) not in owned][:limit]
    log.info("seed: %d tracks to fetch", len(todo))
    if cfg.dry_run:
        for a, t in todo:
            log.info("[dry-run] would fetch %s - %s", a, t)
        return
    sl = Slskd(cfg.slskd_url, cfg.slskd_api_key, cfg.slskd_downloads, cfg.download_timeout_s)
    staging = cfg.staging_dir / f"seed-{time.strftime('%Y%m%d-%H%M%S')}"
    missing = []
    for artist, title in todo:
        hit = sl.best_track(artist, title)
        files = sl.download(hit[0], [hit[1]]) if hit else []
        path = move_into(files[0], staging) if files else (youtube.download(artist, title, staging) if allow_youtube else None)
        if path:
            ensure_tags(path, artist, title)
        else:
            missing.append(f"{artist} - {title}")
    _beets_import(staging, cfg)
    nd.scan_and_wait()
    if missing:
        out = cfg.state_dir / "seed-missing.txt"
        out.write_text("\n".join(missing) + "\n")
        log.info("seed: %d not found, listed in %s", len(missing), out)
