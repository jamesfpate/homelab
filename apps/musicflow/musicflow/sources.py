"""Recommendation sources. Each returns plain candidates; ingest.py does the downloading.

To add a source: write a function returning Track or Release items and register it in SOURCES.
"""

import os
import random
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import requests

from . import llm
from .config import Config
from .listenbrainz import ListenBrainz
from .navidrome import Navidrome
from .util import log, norm


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
_LEADING_TAG = re.compile(r"^\s*\[[^\]]*\]\s*")  # [FRESH], [FRESH ALBUM], [Discussion] ... on other subs


def parse_reddit_title(text: str) -> Track | None:
    """r/listentothis enforces 'Artist -- Title [Genre] (Year)'; other subs mostly use 'Artist - Title' after a tag."""
    while (stripped := _LEADING_TAG.sub("", text, count=1)) != text:
        text = stripped
    m = _TITLE.match(text)
    if not m:
        return None
    title = m["title"]
    title = re.sub(r"\s*[\{\|].*$", "", title)  # "{FULL ALBUM}", "| Live on KEXP"
    title = re.sub(r"\.\s+(?=\S+(\s+\S+){3,})", "\u0000", title, count=1).split("\u0000")[0]  # ". then a sentence of commentary"
    title = re.sub(r"\s*\(\d{4}\)\s*$", "", title).strip()
    return Track(m["artist"].strip(), title) if title and "@" not in m["artist"] else None


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


_REDDIT_GAP_S = 10  # anonymous RSS is rate-limited; space the subreddit fetches out and back off on 429
_last_reddit_call = 0.0


def _reddit_rss(sub: str, window: str) -> bytes:
    global _last_reddit_call
    for attempt in range(4):
        time.sleep(max(0.0, _last_reddit_call + _REDDIT_GAP_S - time.monotonic()))
        _last_reddit_call = time.monotonic()
        r = requests.get(
            f"https://www.reddit.com/r/{sub}/top/.rss",
            params={"t": window, "limit": 100},
            headers={"User-Agent": "musicflow/1.0 (homelab music discovery)"},
            timeout=30,
        )
        if r.status_code != 429:
            r.raise_for_status()
            return r.content
        wait = 30 * (attempt + 1)
        log.info("r/%s: rate limited, retrying in %ds", sub, wait)
        time.sleep(wait)
    raise RuntimeError(f"r/{sub}: still rate limited after retries")


def reddit(sub: str):
    """Top posts of the week on r/<sub> whose titles parse as 'Artist - Title'."""

    def source(cfg: Config) -> list[Track | Release]:
        # All-time top first (the sub's canon), then this week's: ingest skips anything already offered, so
        # once the all-time list is used up the weekly posts take over by themselves.
        ns = {"a": "http://www.w3.org/2005/Atom"}
        titles: list[str] = []
        for window in cfg.reddit_windows:
            for e in ET.fromstring(_reddit_rss(sub, window)).findall("a:entry", ns):
                t = e.findtext("a:title", default="", namespaces=ns)
                if t and t not in titles:
                    titles.append(t)
        parsed = llm.parse_titles(cfg, sub, titles) if llm.enabled(cfg) else None
        items: list[Track] = []
        if parsed is None:  # no LLM, or it failed: regex
            items = [t for t in (parse_reddit_title(t) for t in titles) if t]
        else:
            for raw, p in zip(titles, parsed):
                if not p:
                    continue
                # An album post costs one inbox slot like everything else: its best-known song (the LLM names it),
                # or the album title as a track search as a fallback. Whole albums only come from Fresh Releases.
                # Only believe "album" when the post says so; a bare [FRESH] is a single by subreddit convention.
                is_album = p["kind"] == "album" and re.search(r"\b(album|ep|lp|record|mixtape)\b", raw, re.I)
                items.append(Track(p["artist"], p.get("track") or p["title"]) if is_album else Track(p["artist"], p["title"]))
        owned = _owned_artists(cfg)
        kept = [t for t in items if norm(t.artist) not in owned]
        log.info("r/%s: %d of %d posts parsed%s, %d after dropping artists you own", sub, len(items), len(titles),
                 " (llm)" if parsed is not None else "", len(kept))
        return kept[: cfg.reddit_limit]

    source.__name__ = f"reddit_{sub}"
    return source


SUBREDDITS = [s.strip() for s in os.environ.get("SUBREDDITS", "listentothis").split(",") if s.strip()]


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


_owned_cache: dict[int, set[str]] = {}


def _owned_artists(cfg: Config) -> set[str]:
    """Artists already in the library or inbox (normalised); fetched once per run."""
    key = id(cfg)
    if key not in _owned_cache:
        try:
            nd = Navidrome(cfg.navidrome_url, cfg.navidrome_user, cfg.navidrome_password)
            _owned_cache[key] = {norm(s.artist) for s in nd.all_songs() if s.artist}
        except Exception as e:
            log.warning("could not load owned artists: %s", e)
            _owned_cache[key] = set()
    return _owned_cache[key]


def lastfm_candidates(api_key: str, seeds: list[str], owned: set[str], per_seed: int = 10, limit: int = 30) -> list[Track]:
    """Last.fm similar artists for each seed (artists you starred), one top track each, skipping artists you own."""
    api = "https://ws.audioscrobbler.com/2.0/"
    http = requests.Session()
    http.headers["User-Agent"] = "musicflow/1.0 (homelab music discovery)"

    def call(**params):
        r = http.get(api, params={**params, "api_key": api_key, "format": "json"}, timeout=30)
        r.raise_for_status()
        return r.json()

    scored: dict[str, float] = {}
    for seed in seeds:
        for a in call(method="artist.getSimilar", artist=seed, limit=per_seed, autocorrect=1).get("similarartists", {}).get("artist", []):
            name = a.get("name", "")
            if name and norm(name) not in owned:
                scored[name] = max(scored.get(name, 0.0), float(a.get("match", 0)))
    picks = sorted(scored, key=lambda n: -scored[n])[:limit]
    tracks = []
    for name in picks:
        tt = call(method="artist.getTopTracks", artist=name, limit=1, autocorrect=1).get("toptracks", {}).get("track", [])
        if tt:
            tracks.append(Track(name, tt[0]["name"]))
    return tracks


def lastfm(cfg: Config) -> list[Track]:
    if not cfg.lastfm_api_key:
        return []
    nd = Navidrome(cfg.navidrome_url, cfg.navidrome_user, cfg.navidrome_password)
    songs = nd.all_songs()
    starred = sorted({s.artist for s in songs if s.starred and s.artist})
    if not starred:
        log.info("lastfm: no starred artists yet")
        return []
    seeds = random.sample(starred, min(cfg.lastfm_seeds, len(starred)))  # a different slice of your taste each night
    owned = {norm(s.artist) for s in songs if s.artist}
    tracks = lastfm_candidates(cfg.lastfm_api_key, seeds, owned)
    log.info("lastfm: %d seeds -> %d candidate tracks", len(seeds), len(tracks))
    return tracks


# Order matters: ingest takes one item from each in turn, starting with the first.
SOURCES = {"exploration": exploration, "fresh": fresh, "lastfm": lastfm, **{f"r/{sub}": reddit(sub) for sub in SUBREDDITS}}
