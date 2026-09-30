"""Album stars -> Lidarr. Star an album anywhere (Navidrome, Symfonium, Feishin) and Lidarr fetches the whole thing.

Runs every 30 minutes. Each starred album is handed to Lidarr once (recorded as a 'wanted' event); a track star in
the inbox is separate and still follows the promote flow.
"""

from . import history, report
from .config import Config
from .lidarr import Lidarr
from .navidrome import Navidrome
from .util import is_within, log, norm


def run(cfg: Config) -> None:
    if not cfg.lidarr_url:
        log.info("wants: LIDARR_URL not set, nothing to do")
        return
    nd = Navidrome(cfg.navidrome_url, cfg.navidrome_user, cfg.navidrome_password)
    starred = nd.starred_albums()
    done = history.wanted_keys(cfg)
    todo = [a for a in starred if (norm(a.artist), norm(a.name)) not in done]
    log.info("wants: %d starred albums, %d new", len(starred), len(todo))
    if not todo:
        return
    li = Lidarr(cfg.lidarr_url, cfg.lidarr_api_key)
    for a in todo:
        try:
            paths = nd.album_paths(a.id)
            if paths and not any(is_within(p, cfg.inbox_dir) for p in paths):
                log.info("wants: %s - %s is already in the library (%d tracks), skipping", a.artist, a.name, len(paths))
                history.record(cfg, "wanted", source="album star", artist=a.artist, album=a.name, title="owned")
                continue
            hit = li.lookup(a.artist, a.name, a.mbid)
            if not hit:
                log.warning("wants: Lidarr has no match for %s - %s", a.artist, a.name)
                history.record(cfg, "not_found", source="album star", artist=a.artist, album=a.name)
                continue
            outcome = li.want(hit, cfg.dry_run)
        except Exception as e:  # one bad album shouldn't stop the rest
            log.warning("wants: %s - %s failed: %s", a.artist, a.name, e)
            continue
        if outcome != "dry-run":
            history.record(cfg, "wanted", source="album star", artist=hit["artist"]["artistName"], album=hit["title"],
                           title=outcome)
    if not cfg.dry_run:
        report.run(cfg)
