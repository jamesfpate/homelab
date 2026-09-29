"""musicflow CLI.

  python -m musicflow promote                 weekly star/dislike/expire pass over the inbox
  python -m musicflow ingest all|fresh|listentothis
  python -m musicflow sync-loves              ListenBrainz loves for starred library tracks
  python -m musicflow seed FILE.csv [--limit N] [--allow-youtube]

DRY_RUN=true (the default) logs every decision and changes nothing.
"""

import argparse
from pathlib import Path

from . import config, ingest, promote, seed
from .sources import SOURCES
from .util import setup_logging


def main() -> None:
    setup_logging()
    p = argparse.ArgumentParser(prog="musicflow")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("promote")
    sub.add_parser("sync-loves")
    ing = sub.add_parser("ingest")
    ing.add_argument("source", choices=["all", *SOURCES])
    sd = sub.add_parser("seed")
    sd.add_argument("csv", type=Path)
    sd.add_argument("--limit", type=int, default=500)
    sd.add_argument("--allow-youtube", action="store_true")
    args = p.parse_args()

    cfg = config.load()
    if args.cmd == "promote":
        promote.run(cfg)
    elif args.cmd == "sync-loves":
        promote.sync_loves(cfg)
    elif args.cmd == "ingest":
        ingest.run(cfg, list(SOURCES) if args.source == "all" else [args.source])
    elif args.cmd == "seed":
        seed.run(cfg, args.csv, args.limit, args.allow_youtube)


if __name__ == "__main__":
    main()
