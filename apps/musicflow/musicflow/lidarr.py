"""Minimal Lidarr API client: look an album up and add it (or search for it) with the root folder's defaults."""

import requests

from .util import log


class Lidarr:
    def __init__(self, url: str, api_key: str):
        self.url = url.rstrip("/") + "/api/v1"
        self.http = requests.Session()
        self.http.headers["X-Api-Key"] = api_key

    def _get(self, path: str, **params):
        r = self.http.get(f"{self.url}{path}", params=params, timeout=60)
        r.raise_for_status()
        return r.json()

    def _send(self, method: str, path: str, body: dict):
        r = self.http.request(method, f"{self.url}{path}", json=body, timeout=120)
        if r.status_code >= 400:
            raise RuntimeError(f"Lidarr {method} {path}: {r.status_code} {r.text[:300]}")
        return r.json() if r.text else None

    def lookup(self, artist: str, album: str, mbid: str = "") -> dict | None:
        """Best match for the album; exact by MusicBrainz release-group id when Navidrome has one."""
        if mbid:
            hits = self._get("/album/lookup", term=f"lidarr:{mbid}")
            if hits:
                return hits[0]
        hits = self._get("/album/lookup", term=f"{artist} {album}")
        for h in hits:
            if h.get("title", "").lower() == album.lower() and h.get("artist", {}).get("artistName", "").lower() == artist.lower():
                return h
        return hits[0] if hits else None

    def defaults(self) -> dict:
        """Root folder plus the profiles it defaults to (Standard/Standard as set up), first ones as fallback."""
        root = self._get("/rootfolder")[0]
        q = self._get("/qualityprofile")
        m = self._get("/metadataprofile")
        return {
            "rootFolderPath": root["path"],
            "qualityProfileId": root.get("defaultQualityProfileId") or next((p["id"] for p in q if p["name"] == "Standard"), q[0]["id"]),
            "metadataProfileId": root.get("defaultMetadataProfileId") or next((p["id"] for p in m if p["name"] == "Standard"), m[0]["id"]),
        }

    def want(self, album: dict, dry_run: bool) -> str:
        """Make sure the album is monitored and searched. Returns 'added', 'searched' or 'dry-run'."""
        title = f"{album['artist']['artistName']} - {album['title']}"
        if dry_run:
            log.info("[dry-run] would %s %s", "search" if album.get("id") else "add", title)
            return "dry-run"
        if album.get("id"):  # already in Lidarr: monitor it and kick off a search
            self._send("PUT", "/album/monitor", {"albumIds": [album["id"]], "monitored": True})
            self._send("POST", "/command", {"name": "AlbumSearch", "albumIds": [album["id"]]})
            log.info("search started: %s", title)
            return "searched"
        d = self.defaults()
        body = dict(album)
        body["monitored"] = True
        body["addOptions"] = {"searchForNewAlbum": True}
        body["artist"] = dict(album["artist"]) | d | {
            "monitored": True,
            "monitorNewItems": "none",
            "addOptions": {"monitor": "none", "searchForMissingAlbums": False},
        }
        self._send("POST", "/album", body)
        log.info("added to Lidarr: %s", title)
        return "added"
