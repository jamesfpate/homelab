"""ListenBrainz: love/hate feedback, MBID lookup, Fresh Releases."""

import requests

from .util import log

API = "https://api.listenbrainz.org/1"


class ListenBrainz:
    def __init__(self, user: str, token: str):
        self.user = user
        self.http = requests.Session()
        self.http.headers["Authorization"] = f"Token {token}"

    def lookup_mbid(self, artist: str, title: str) -> str:
        r = self.http.get(
            f"{API}/metadata/lookup/", params={"artist_name": artist, "recording_name": title}, timeout=30
        )
        if r.status_code != 200:
            return ""
        return (r.json() or {}).get("recording_mbid") or ""

    def feedback(self, mbid: str, score: int) -> bool:
        """score: 1 = love, -1 = hate, 0 = clear. Idempotent on the LB side."""
        if not mbid:
            return False
        r = self.http.post(f"{API}/feedback/recording-feedback", json={"recording_mbid": mbid, "score": score}, timeout=30)
        if r.status_code != 200:
            log.warning("listenbrainz feedback %s for %s failed: %s", score, mbid, r.text[:200])
            return False
        return True

    def fresh_releases(self, days: int) -> list[dict]:
        r = self.http.get(
            f"{API}/user/{self.user}/fresh_releases",
            params={"days": days, "past": "true", "future": "false"},
            timeout=60,
        )
        r.raise_for_status()
        return r.json().get("payload", {}).get("releases", [])
