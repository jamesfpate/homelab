"""Daily inbox pass, from the Navidrome user's stars, ratings and plays.

  starred                    -> ListenBrainz love, beets-tagged into /music/library, re-starred at its new path
  rated 1                    -> ListenBrainz hate, deleted
  heard, not starred         -> deleted once PLAYED_GRACE_HOURS have passed since the last play
  unheard                    -> always kept (ingest only fills up to INBOX_SIZE, so the inbox can't overflow)

"Heard" = Navidrome logged a play (Symfonium submits one after ~half the track), so early skips stay unheard.
Only files under /music/inbox are ever deleted.
"""

import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from .config import Config
from .listenbrainz import ListenBrainz
from .navidrome import Navidrome, Song
from . import history, report
from .util import AUDIO_EXTS, is_within, load_json, log, move_into, prune_empty_dirs, safe_delete, save_json, track_key


def run(cfg: Config) -> None:
    nd = Navidrome(cfg.navidrome_url, cfg.navidrome_user, cfg.navidrome_password)
    lb = ListenBrainz(cfg.lb_user, cfg.lb_token)
    tag = "[dry-run] " if cfg.dry_run else ""
    inbox = [s for s in nd.all_songs() if is_within(s.path, cfg.inbox_dir)]
    log.info("inbox: %d tracks", len(inbox))

    staging = cfg.staging_dir / time.strftime("%Y%m%d-%H%M%S")
    keep: list[Song] = []
    counts = {"kept": 0, "disliked": 0, "heard": 0, "unheard": 0, "grace": 0}
    now = datetime.now(timezone.utc)
    for s in inbox:
        if not s.path.exists():
            continue
        if s.starred:
            log.info("%skeep %s - %s", tag, s.artist, s.title)
            if not cfg.dry_run:
                lb.feedback(s.mbid or lb.lookup_mbid(s.artist, s.title), 1)
                move_into(s.path, staging)
            keep.append(s)
            counts["kept"] += 1
            history.record(cfg, "kept", artist=s.artist, title=s.title, album=s.album, path=s.path)
        elif s.rating == 1:
            if not cfg.dry_run:
                lb.feedback(s.mbid or lb.lookup_mbid(s.artist, s.title), -1)
            safe_delete(s.path, cfg.inbox_dir, cfg.dry_run)
            counts["disliked"] += 1
            history.record(cfg, "disliked", artist=s.artist, title=s.title, album=s.album, path=s.path)
        elif s.play_count > 0:
            last = s.played or now
            if (now - last).total_seconds() >= cfg.played_grace_hours * 3600:
                safe_delete(s.path, cfg.inbox_dir, cfg.dry_run)
                counts["heard"] += 1
                history.record(cfg, "heard", artist=s.artist, title=s.title, album=s.album, path=s.path)
            else:
                counts["grace"] += 1
        else:
            counts["unheard"] += 1

    # Files Navidrome still hasn't indexed after 14 days are unplayable (broken downloads); clear them.
    known = {s.path.resolve() for s in inbox}
    for f in cfg.inbox_dir.rglob("*"):
        if f.is_file() and f.resolve() not in known and _age_days(f) >= 14:
            safe_delete(f, cfg.inbox_dir, cfg.dry_run)
            history.record(cfg, "stale", title=f.name, path=f)

    log.info("result: %s", counts)
    if cfg.dry_run:
        report.run(cfg)
        return
    prune_empty_dirs(cfg.inbox_dir, dry_run=False)
    if keep:
        _beets_import(staging, cfg)
    nd.scan_and_wait()
    if keep:
        _restar(nd, keep, cfg)
    report.run(cfg)


def _age_days(path: Path) -> float:
    return (time.time() - path.stat().st_mtime) / 86400


def _beets_import(staging: Path, cfg: Config) -> None:
    if not staging.exists():
        return
    result = subprocess.run(["beet", "import", "-s", "-q", str(staging)], capture_output=True, text=True)
    if result.returncode != 0:
        log.error("beets import failed: %s", result.stderr[-2000:])
    # Anything beets left behind still goes to the library, untagged, rather than being lost.
    leftovers = [f for f in staging.rglob("*") if f.is_file() and f.suffix.lower() in AUDIO_EXTS]
    for f in leftovers:
        move_into(f, cfg.library_dir / "_unmatched")
    if leftovers:
        log.warning("%d files moved to library/_unmatched (check beets log)", len(leftovers))
    prune_empty_dirs(cfg.staging_dir, dry_run=False)


def _restar(nd: Navidrome, kept: list[Song], cfg: Config) -> None:
    """beets rewrites tags, so Navidrome sees new files and the star is lost; put it back."""
    library = [s for s in nd.all_songs() if is_within(s.path, cfg.library_dir)]
    by_key: dict[tuple[str, str], list[Song]] = {}
    for s in library:
        by_key.setdefault(track_key(s.artist, s.title), []).append(s)
    for k in kept:
        matches = by_key.get(track_key(k.artist, k.title), [])
        if not matches:
            log.warning("could not re-star %s - %s (not found after scan)", k.artist, k.title)
            continue
        newest = max(matches, key=lambda s: s.created.timestamp() if s.created else 0)
        if not newest.starred:
            nd.star(newest.id)


def sync_loves(cfg: Config) -> None:
    """Send a ListenBrainz love for every starred library track not sent before."""
    nd = Navidrome(cfg.navidrome_url, cfg.navidrome_user, cfg.navidrome_password)
    lb = ListenBrainz(cfg.lb_user, cfg.lb_token)
    state_path = cfg.state_dir / "loved.json"
    sent = set(load_json(state_path, []))
    new = 0
    for s in nd.all_songs():
        if not s.starred or is_within(s.path, cfg.inbox_dir):
            continue
        key = "%s|%s" % track_key(s.artist, s.title)
        if key in sent:
            continue
        if cfg.dry_run:
            log.info("[dry-run] love %s - %s", s.artist, s.title)
            continue
        if lb.feedback(s.mbid or lb.lookup_mbid(s.artist, s.title), 1):
            sent.add(key)
            new += 1
    if not cfg.dry_run:
        save_json(state_path, sorted(sent))
    log.info("loves sent: %d", new)
