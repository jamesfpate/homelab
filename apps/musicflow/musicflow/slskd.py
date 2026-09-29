"""slskd API: search Soulseek, pick the best track or album folder, download, wait, return local files."""

import re
import time
import uuid
from collections import defaultdict
from pathlib import Path, PurePosixPath

import requests

from .util import AUDIO_EXTS, log, norm

AVOID = {"live", "remix", "instrumental", "karaoke", "acapella", "edit", "sped", "slowed", "cover", "demo"}


def _parts(remote: str) -> list[str]:
    return [p for p in re.split(r"[\\/]", remote) if p]


def _ext(remote: str) -> str:
    return PurePosixPath(_parts(remote)[-1]).suffix.lower()


class Slskd:
    def __init__(self, url: str, api_key: str, downloads_dir: Path, timeout_s: int):
        if not url or not api_key:
            raise SystemExit("SLSKD_URL and SLSKD_API_KEY are required for downloads")
        self.url = f"{url}/api/v0"
        self.downloads_dir = downloads_dir
        self.timeout_s = timeout_s
        self.http = requests.Session()
        self.http.headers["X-API-Key"] = api_key

    # --- search ---------------------------------------------------------------
    def search(self, text: str, wait_s: int = 45) -> list[dict]:
        sid = str(uuid.uuid4())
        r = self.http.post(f"{self.url}/searches", json={"id": sid, "searchText": text, "searchTimeout": 20000}, timeout=30)
        r.raise_for_status()
        deadline = time.time() + wait_s
        while time.time() < deadline:
            time.sleep(3)
            if self.http.get(f"{self.url}/searches/{sid}", timeout=30).json().get("isComplete"):
                break
        responses = self.http.get(f"{self.url}/searches/{sid}/responses", timeout=60).json()
        self.http.delete(f"{self.url}/searches/{sid}", timeout=30)
        return [resp for resp in responses if resp.get("files")]

    @staticmethod
    def _quality(f: dict) -> int:
        ext = _ext(f["filename"])
        if ext == ".flac":
            return 3
        if ext == ".mp3" and (f.get("bitRate") or 0) >= 256:
            return 2
        if ext in {".m4a", ".ogg", ".opus"} and (f.get("bitRate") or 0) >= 192:
            return 1
        return 0

    @staticmethod
    def _peer(resp: dict) -> float:
        return (2.0 if resp.get("hasFreeUploadSlot") else 0.0) + min(resp.get("uploadSpeed", 0) / 5_000_000, 1.0) - min(
            resp.get("queueLength", 0) / 50, 1.0
        )

    def best_track(self, artist: str, title: str) -> tuple[str, dict] | None:
        want_artist, want_title = norm(artist).split(), norm(title).split()
        if not want_title or not want_artist:  # e.g. non-Latin titles normalize to nothing; let YouTube try
            return None
        unwanted = AVOID - set(want_title)
        best, best_score = None, -1.0
        for resp in self.search(f"{artist} {title}"):
            for f in resp["files"]:
                if _ext(f["filename"]) not in AUDIO_EXTS:
                    continue
                name = norm(" ".join(_parts(f["filename"])[-3:]))  # artist/album/file usually in the tail
                words = set(name.split())
                if not all(w in words for w in want_title) or not any(w in words for w in want_artist):
                    continue
                if words & unwanted:
                    continue
                q = self._quality(f)
                if q == 0:
                    continue
                score = q * 10 + self._peer(resp)
                if score > best_score:
                    best, best_score = (resp["username"], f), score
        return best

    def best_folder(self, artist: str, album: str) -> tuple[str, list[dict]] | None:
        want = set(norm(album).split()) | set(norm(artist).split()[:1])
        best, best_score = None, -1.0
        for resp in self.search(f"{artist} {album}"):
            folders: dict[str, list[dict]] = defaultdict(list)
            for f in resp["files"]:
                if _ext(f["filename"]) in AUDIO_EXTS:
                    folders["\\".join(_parts(f["filename"])[:-1])].append(f)
            for folder, files in folders.items():
                words = set(norm(" ".join(_parts(folder)[-2:])).split())
                if not want <= words:
                    continue
                q = min(self._quality(f) for f in files)
                if q == 0:
                    continue
                score = q * 10 + min(len(files), 20) / 4 + self._peer(resp)
                if score > best_score:
                    best, best_score = (resp["username"], files), score
        return best

    # --- download -------------------------------------------------------------
    def download(self, username: str, files: list[dict]) -> list[Path]:
        payload = [{"filename": f["filename"], "size": f["size"]} for f in files]
        self.http.post(f"{self.url}/transfers/downloads/{requests.utils.quote(username)}", json=payload, timeout=60).raise_for_status()
        wanted = {f["filename"] for f in files}
        done: dict[str, bool] = {}
        deadline = time.time() + self.timeout_s
        while time.time() < deadline and len(done) < len(wanted):
            time.sleep(10)
            r = self.http.get(f"{self.url}/transfers/downloads/{requests.utils.quote(username)}", timeout=60)
            if r.status_code != 200:
                continue
            for d in r.json().get("directories", []):
                for t in d.get("files", []):
                    state = t.get("state", "")
                    if t["filename"] in wanted and state.startswith("Completed"):
                        done[t["filename"]] = "Succeeded" in state
        ok = [name for name, success in done.items() if success]
        if len(ok) < len(wanted):
            log.warning("slskd: %d/%d files from %s finished", len(ok), len(wanted), username)
        paths = []
        for remote in ok:
            parts = _parts(remote)
            local = self.downloads_dir / (parts[-2] if len(parts) > 1 else "") / parts[-1]
            if local.exists():
                paths.append(local)
            else:
                log.warning("slskd: finished file not found locally: %s", local)
        return paths
