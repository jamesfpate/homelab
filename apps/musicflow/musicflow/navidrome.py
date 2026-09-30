"""Minimal Subsonic API client for Navidrome."""

import hashlib
import secrets
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import requests

from .util import log


@dataclass
class Song:
    id: str
    title: str
    artist: str
    album: str
    path: Path
    starred: bool
    rating: int
    mbid: str
    created: datetime | None
    play_count: int = 0
    played: datetime | None = None


@dataclass
class StarredAlbum:
    id: str
    name: str
    artist: str
    mbid: str


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


class Navidrome:
    def __init__(self, url: str, user: str, password: str):
        self.url, self.user, self.password = url, user, password
        self.http = requests.Session()

    def _call(self, endpoint: str, **params) -> dict:
        salt = secrets.token_hex(6)
        token = hashlib.md5((self.password + salt).encode()).hexdigest()
        params |= {"u": self.user, "t": token, "s": salt, "v": "1.16.1", "c": "musicflow", "f": "json"}
        r = self.http.get(f"{self.url}/rest/{endpoint}", params=params, timeout=60)
        r.raise_for_status()
        body = r.json()["subsonic-response"]
        if body.get("status") != "ok":
            raise RuntimeError(f"navidrome {endpoint}: {body.get('error')}")
        return body

    def all_songs(self) -> list[Song]:
        """Every song, via search3 with an empty query (the method Subsonic clients use for full sync).
        Paths are real file paths because ND_SUBSONIC_DEFAULTREPORTREALPATH=true."""
        songs, offset, page = [], 0, 500
        while True:
            body = self._call("search3", query='""', artistCount=0, albumCount=0, songCount=page, songOffset=offset)
            batch = body.get("searchResult3", {}).get("song", [])
            for s in batch:
                created, played = s.get("created"), s.get("played")
                songs.append(
                    Song(
                        id=s["id"],
                        title=s.get("title", ""),
                        artist=s.get("artist", ""),
                        album=s.get("album", ""),
                        path=Path(s.get("path", "")),
                        starred=bool(s.get("starred")),
                        rating=int(s.get("userRating") or 0),
                        mbid=s.get("musicBrainzId") or "",
                        created=_dt(created),
                        play_count=int(s.get("playCount") or 0),
                        played=_dt(played),
                    )
                )
            if len(batch) < page:
                return songs
            offset += page

    def starred_albums(self) -> list["StarredAlbum"]:
        albums = self._call("getStarred2").get("starred2", {}).get("album", [])
        return [StarredAlbum(a["id"], a.get("name", ""), a.get("artist", ""), a.get("musicBrainzId", "")) for a in albums]

    def album_paths(self, album_id: str) -> list[Path]:
        songs = self._call("getAlbum", id=album_id).get("album", {}).get("song", [])
        return [Path(s["path"]) for s in songs if s.get("path")]

    def star(self, song_id: str) -> None:
        self._call("star", id=song_id)

    def set_rating(self, song_id: str, rating: int) -> None:
        self._call("setRating", id=song_id, rating=rating)

    def scan_and_wait(self, timeout_s: int = 1800) -> None:
        self._call("startScan")
        deadline = time.time() + timeout_s
        time.sleep(5)
        while time.time() < deadline:
            if not self._call("getScanStatus")["scanStatus"].get("scanning"):
                return
            time.sleep(10)
        log.warning("navidrome scan still running after %ss", timeout_s)
