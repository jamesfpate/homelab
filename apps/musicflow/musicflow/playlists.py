"""One Navidrome smart playlist per source ("Inbox - r/indieheads"), so the apps show where tracks came from."""

import json
from pathlib import Path

from .config import Config
from .sources import SOURCES
from .util import log

_PREFIX = "Inbox - "


def write_source_playlists(cfg: Config, playlists_dir: Path) -> None:
    """Regenerate the per-source .nsp files; removes ones for sources that no longer exist."""
    playlists_dir.mkdir(parents=True, exist_ok=True)
    wanted = {}
    for name in SOURCES:
        file = playlists_dir / f"{_PREFIX}{name.replace('/', ' ')}.nsp"
        wanted[file] = {
            "name": f"{_PREFIX}{name}",
            "comment": f"Unheard and recent recommendations from {name}. Star to keep, rate 1 to dislike.",
            "all": [{"contains": {"filepath": f"inbox/{name}/"}}],
            "sort": "dateadded",
            "order": "desc",
            "limit": 500,
        }
    for old in playlists_dir.glob(f"{_PREFIX}*.nsp"):
        if old not in wanted and not cfg.dry_run:
            old.unlink()
            log.info("playlist removed: %s", old.name)
    for file, spec in wanted.items():
        text = json.dumps(spec, indent=2) + "\n"
        if file.exists() and file.read_text() == text:
            continue
        if cfg.dry_run:
            log.info("[dry-run] would write playlist %s", file.name)
            continue
        file.write_text(text)
        log.info("playlist written: %s", file.name)
