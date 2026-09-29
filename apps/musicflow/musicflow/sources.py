"""Recommendation sources. Each returns plain candidates; ingest.py does the downloading.

To add a source: write a function returning Track or Release items and register it in SOURCES.
"""

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import requests

from .config import Config
from .listenbrainz import ListenBrainz
from .util import log


@dataclass
class Track:
    artist: str
    title: str


@dataclass
class Release:
    artist: str
    album: str
    mbid: str


_TITLE = re.compile(r"^\s*(?P<artist>.+?)\s+(?:--|—|–|-)\s+(?P<title>.+?)\s*(?:\[.*)?$")


def parse_reddit_title(text: str) -> Track | None:
    """r/listentothis enforces 'Artist -- Title [Genre] (Year)'."""
    m = _TITLE.match(text)
    if not m:
        return None
    title = re.sub(r"\s*\(\d{4}\)\s*$", "", m["title"]).strip()
    return Track(m["artist"].strip(), title) if title else None


def exploration(cfg: Config) -> list[Track]:
    """ListenBrainz Weekly Exploration (~50 tracks, regenerated every Monday from your listening)."""
    api = "https://api.listenbrainz.org/1"
    r = requests.get(f"{api}/user/{cfg.lb_user}/playlists/createdfor", params={"count": 25}, timeout=30)
    r.raise_for_status()
    weekly = [p["playlist"] for p in r.json().get("playlists", []) if p["playlist"]["title"].startswith("Weekly Exploration")]
    if not weekly:
        log.info("exploration: no Weekly Exploration yet (ListenBrainz needs more listening history)")
        return []
    latest = max(weekly, key=lambda p: p.get("date", ""))
    mbid = latest["identifier"].rstrip("/").rsplit("/", 1)[-1]
    r = requests.get(f"{api}/playlist/{mbid}", timeout=30)
    r.raise_for_status()
    tracks = [Track(t.get("creator", ""), t.get("title", "")) for t in r.json()["playlist"].get("track", [])]
    log.info("exploration: %s, %d tracks", latest["title"], len(tracks))
    return [t for t in tracks if t.artist and t.title]


def listentothis(cfg: Config) -> list[Track]:
    r = requests.get(
        "https://www.reddit.com/r/listentothis/top/.rss",
        params={"t": "week", "limit": 50},
        headers={"User-Agent": "musicflow/1.0 (homelab music discovery)"},
        timeout=30,
    )
    r.raise_for_status()
    ns = {"a": "http://www.w3.org/2005/Atom"}
    tracks = []
    for entry in ET.fromstring(r.content).findall("a:entry", ns):
        track = parse_reddit_title(entry.findtext("a:title", default="", namespaces=ns))
        if track:
            tracks.append(track)
    log.info("listentothis: %d parsable posts", len(tracks))
    return tracks[: cfg.listentothis_limit]


def fresh(cfg: Config) -> list[Release]:
    lb = ListenBrainz(cfg.lb_user, cfg.lb_token)
    picks = [
        r
        for r in lb.fresh_releases(cfg.fresh_days)
        if (r.get("release_group_primary_type") or "").lower() in cfg.fresh_types
        and not r.get("release_group_secondary_type")  # skip remix/live/compilation
    ]
    picks.sort(key=lambda r: r.get("confidence", 0), reverse=True)
    log.info("fresh releases: %d candidates", len(picks))
    return [Release(r["artist_credit_name"], r["release_name"], r["release_mbid"]) for r in picks[: cfg.fresh_max_releases]]


# Order matters: ingest takes one item from each in turn, starting with the first.
SOURCES = {"exploration": exploration, "fresh": fresh, "listentothis": listentothis}
