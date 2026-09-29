"""yt-dlp fallback for single tracks Soulseek can't find (lossy; auditioning only)."""

import subprocess
from pathlib import Path

from .util import log


def download(artist: str, title: str, dest_dir: Path) -> Path | None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    template = str(dest_dir / f"{_safe(artist)} - {_safe(title)}.%(ext)s")
    cmd = [
        "yt-dlp",
        f"ytsearch1:{artist} - {title} official audio",
        "--extract-audio",
        "--audio-format", "mp3",
        "--audio-quality", "0",
        "--no-playlist",
        "--match-filter", "duration < 900",
        "--output", template,
        "--quiet", "--no-warnings",
    ]
    try:
        subprocess.run(cmd, check=True, timeout=600)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        log.warning("yt-dlp failed for %s - %s: %s", artist, title, e)
        return None
    out = dest_dir / f"{_safe(artist)} - {_safe(title)}.mp3"
    return out if out.exists() else None


def _safe(text: str) -> str:
    return "".join(c if c not in '/\\:*?"<>|' else "_" for c in text).strip()[:120]
