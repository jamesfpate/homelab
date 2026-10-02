"""Fill the inbox up to INBOX_SIZE unheard tracks from the sources, skipping anything owned or seen before.

This is the only thing that adds to the inbox, and it never goes past INBOX_SIZE, so nothing unheard ever
has to be dropped. Sources are interleaved so no single one dominates.
"""

from datetime import date
from itertools import chain, zip_longest
from pathlib import Path

from . import history, llm, playlists, report, youtube
from .config import Config
from .navidrome import Navidrome
from .slskd import Slskd
from .sources import SOURCES, Release, Track
from .util import ensure_tags, is_within, load_json, log, move_into, norm, save_json, set_comment, track_key


def run(cfg: Config, which: list[str]) -> None:
    nd = Navidrome(cfg.navidrome_url, cfg.navidrome_user, cfg.navidrome_password)
    playlists.write_source_playlists(cfg, cfg.music_root / "playlists")
    songs = nd.all_songs()
    unheard = sum(
        1 for s in songs if is_within(s.path, cfg.inbox_dir) and not s.starred and s.rating != 1 and s.play_count == 0
    )
    need = cfg.inbox_size - unheard
    log.info("inbox: %d unheard of %d", unheard, cfg.inbox_size)
    if need <= 0:
        report.run(cfg)
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
    if llm.enabled(cfg):
        queue = _score(cfg, songs, queue, batch)

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
            try:
                got += _fetch_track(cfg, sl, item, dest, name, batch)
            except Exception as e:  # a bad peer or a slskd hiccup must not end the whole run
                log.warning("fetch failed: %s - %s (%s): %s", item.artist, item.title, name, e)
                history.record(cfg, "not_found", source=name, artist=item.artist, title=item.title, batch=batch)
        elif isinstance(item, Release):
            key = f"r:{item.mbid}" if item.mbid else "r:%s|%s" % (norm(item.artist), norm(item.album))
            if key in seen or (norm(item.artist), norm(item.album)) in owned_albums:
                continue
            if cfg.dry_run:
                log.info("[dry-run] would fetch release %s - %s (%s)", item.artist, item.album, name)
                got += 1
                continue
            try:
                added = _fetch_release(cfg, sl, item, dest / f"{item.artist} - {item.album}", need - got, name, batch)
            except Exception as e:
                log.warning("fetch failed: %s - %s (%s): %s", item.artist, item.album, name, e)
                history.record(cfg, "not_found", source=name, artist=item.artist, album=item.album, batch=batch)
                added = 0
            if added < 0:  # didn't fit: leave it unseen so it can come back when there's room
                continue
            got += added
        seen.add(key)  # attempted: never re-offered, whether it downloaded, was kept, or was deleted

    log.info("added %d tracks (needed %d)", got, need)
    if not cfg.dry_run:
        save_json(seen_path, sorted(seen))
        nd.scan_and_wait()
    report.run(cfg)


def _score(cfg: Config, songs, queue: list, batch: str) -> list:
    """Taste-score the queue with the local LLM. Shadow mode only logs; LLM_FILTER drops low scores and sorts."""
    loved = sorted({s.artist for s in songs if s.starred and s.artist}, key=str.lower)
    taste = {"loved": loved, **history.decided_artists(cfg)}
    cands = [(name, it.artist, it.title if isinstance(it, Track) else it.album) for name, it in queue]
    scores = llm.score(cfg, taste, cands)
    if not scores:
        return queue
    history.record_scores(cfg, batch, [(*cands[i], sc, why) for i, (sc, why) in scores.items()])
    log.info("llm scored %d of %d candidates (%s)", len(scores), len(queue), "filter" if cfg.llm_filter else "shadow")
    if not cfg.llm_filter:
        return queue
    keep = [(i, c) for i, c in enumerate(queue) if scores.get(i, (cfg.llm_min_score, ""))[0] >= cfg.llm_min_score]
    keep.sort(key=lambda ic: -scores.get(ic[0], (cfg.llm_min_score, ""))[0])
    log.info("llm filter kept %d of %d (min score %d)", len(keep), len(queue), cfg.llm_min_score)
    return [c for _, c in keep]


def _fetch_track(cfg: Config, sl: Slskd, t: Track, dest: Path, source: str, batch: str) -> int:
    hit = sl.best_track(t.artist, t.title)
    files = sl.download(hit[0], [hit[1]]) if hit else []
    if files:
        path = move_into(files[0], dest)
    else:
        path = youtube.download(t.artist, t.title, dest)
        if not path:
            log.info("not found: %s - %s", t.artist, t.title)
            history.record(cfg, "not_found", source=source, artist=t.artist, title=t.title, batch=batch)
            return 0
    ensure_tags(path, t.artist, t.title)
    set_comment(path, f"musicflow: {source} {batch}")
    history.record(cfg, "added", source=source, artist=t.artist, title=t.title, path=path, batch=batch)
    return 1


def _fetch_release(cfg: Config, sl: Slskd, r: Release, dest: Path, room: int, source: str, batch: str) -> int:
    hit = sl.best_folder(r.artist, r.album)
    if not hit:
        log.info("release not found: %s - %s", r.artist, r.album)
        history.record(cfg, "not_found", source=source, artist=r.artist, album=r.album, batch=batch)
        return 0
    if len(hit[1]) > room:  # never overfill; a later run with more room will pick it up
        log.info("no room for %s - %s (%d tracks, %d free)", r.artist, r.album, len(hit[1]), room)
        return -1
    files = sl.download(hit[0], hit[1])
    for f in files:
        path = move_into(f, dest)
        set_comment(path, f"musicflow: {source} {batch}")
        history.record(cfg, "added", source=source, artist=r.artist, title=path.stem, album=r.album, path=path, batch=batch)
    return len(files)
