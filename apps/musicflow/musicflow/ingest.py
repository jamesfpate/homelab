"""Fill the inbox up to INBOX_SIZE unheard tracks from the sources, skipping anything owned or seen before.

This is the only thing that adds to the inbox, and it never goes past INBOX_SIZE, so nothing unheard ever
has to be dropped. Sources are interleaved so no single one dominates.
"""

from datetime import date
from itertools import chain, zip_longest
from pathlib import Path

from . import youtube
from .config import Config
from .navidrome import Navidrome
from .slskd import Slskd
from .sources import SOURCES, Release, Track
from .util import ensure_tags, is_within, load_json, log, move_into, norm, save_json, track_key


def run(cfg: Config, which: list[str]) -> None:
    nd = Navidrome(cfg.navidrome_url, cfg.navidrome_user, cfg.navidrome_password)
    songs = nd.all_songs()
    unheard = sum(
        1 for s in songs if is_within(s.path, cfg.inbox_dir) and not s.starred and s.rating != 1 and s.play_count == 0
    )
    need = cfg.inbox_size - unheard
    log.info("inbox: %d unheard of %d", unheard, cfg.inbox_size)
    if need <= 0:
        return

    owned_tracks = {track_key(s.artist, s.title) for s in songs}
    owned_albums = {(norm(s.artist), norm(s.album)) for s in songs}
    seen_path = cfg.state_dir / "seen.json"
    seen = set(load_json(seen_path, []))
    batch = date.today().isoformat()

    candidates = []
    for name in which:
        try:
            candidates.append([(name, item) for item in SOURCES[name](cfg)])
        except Exception as e:  # one broken source (e.g. ListenBrainz outage) shouldn't stop the others
            log.warning("source %s failed: %s", name, e)
    queue = [c for c in chain.from_iterable(zip_longest(*candidates)) if c]

    sl = None if cfg.dry_run else Slskd(cfg.slskd_url, cfg.slskd_api_key, cfg.slskd_downloads, cfg.download_timeout_s)
    got = 0
    for name, item in queue:
        if got >= need:
            break
        dest = cfg.inbox_dir / name / batch
        if isinstance(item, Track):
            key = "t:%s|%s" % track_key(item.artist, item.title)
            if key in seen or track_key(item.artist, item.title) in owned_tracks:
                continue
            if cfg.dry_run:
                log.info("[dry-run] would fetch %s - %s (%s)", item.artist, item.title, name)
                got += 1
                continue
            got += _fetch_track(sl, item, dest)
        elif isinstance(item, Release):
            key = f"r:{item.mbid}"
            if key in seen or (norm(item.artist), norm(item.album)) in owned_albums:
                continue
            if cfg.dry_run:
                log.info("[dry-run] would fetch release %s - %s (%s)", item.artist, item.album, name)
                got += 1
                continue
            added = _fetch_release(sl, item, dest / f"{item.artist} - {item.album}", room=need - got)
            if added < 0:  # didn't fit: leave it unseen so it can come back when there's room
                continue
            got += added
        seen.add(key)  # attempted: never re-offered, whether it downloaded, was kept, or was deleted

    log.info("added %d tracks (needed %d)", got, need)
    if not cfg.dry_run:
        save_json(seen_path, sorted(seen))
        nd.scan_and_wait()


def _fetch_track(sl: Slskd, t: Track, dest: Path) -> int:
    hit = sl.best_track(t.artist, t.title)
    files = sl.download(hit[0], [hit[1]]) if hit else []
    if files:
        path = move_into(files[0], dest)
    else:
        path = youtube.download(t.artist, t.title, dest)
        if not path:
            log.info("not found: %s - %s", t.artist, t.title)
            return 0
    ensure_tags(path, t.artist, t.title)
    return 1


def _fetch_release(sl: Slskd, r: Release, dest: Path, room: int) -> int:
    hit = sl.best_folder(r.artist, r.album)
    if not hit:
        log.info("release not found: %s - %s", r.artist, r.album)
        return 0
    if len(hit[1]) > room:  # never overfill; a later run with more room will pick it up
        log.info("no room for %s - %s (%d tracks, %d free)", r.artist, r.album, len(hit[1]), room)
        return -1
    files = sl.download(hit[0], hit[1])
    for f in files:
        move_into(f, dest)
    return len(files)
