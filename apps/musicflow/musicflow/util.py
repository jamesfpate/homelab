"""Shared helpers: logging, name normalization, safe file operations."""

import json
import logging
import re
import shutil
import unicodedata
from pathlib import Path

log = logging.getLogger("musicflow")

AUDIO_EXTS = {".flac", ".mp3", ".m4a", ".ogg", ".opus", ".wav", ".aiff", ".alac"}

_BRACKETS = re.compile(r"[\(\[].*?[\)\]]")
_FEAT = re.compile(r"\s+(feat\.?|ft\.?|featuring|with)\s+.*$", re.I)
_NON_WORD = re.compile(r"[^a-z0-9]+")


def setup_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def norm(text: str) -> str:
    """Loose key for matching artist/title across sources: no accents, brackets, feat., punctuation."""
    text = re.sub(r"['\u2019`]", "", text or "")  # "Mahler’s" and "Mahler's" -> "mahlers"
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = _BRACKETS.sub(" ", text.lower())
    text = _FEAT.sub("", text)
    text = _NON_WORD.sub(" ", text).strip()
    return re.sub(r"^the ", "", text)


def track_key(artist: str, title: str) -> tuple[str, str]:
    first_artist = re.split(r"\s*(?:,|&|;)\s*", artist or "", maxsplit=1)[0]
    return norm(first_artist), norm(title)


def is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def safe_delete(path: Path, inbox: Path, dry_run: bool) -> None:
    """Delete a file only if it lives under the inbox. The library is never deleted from."""
    if not is_within(path, inbox) or path.resolve() == inbox.resolve():
        raise RuntimeError(f"refusing to delete outside inbox: {path}")
    log.info("%sdelete %s", "[dry-run] " if dry_run else "", path)
    if not dry_run:
        path.unlink(missing_ok=True)


def prune_empty_dirs(root: Path, dry_run: bool) -> None:
    if dry_run or not root.exists():
        return
    for d in sorted((p for p in root.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        if not any(d.iterdir()):
            d.rmdir()


def move_into(src: Path, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    i = 1
    while dest.exists():
        dest = dest_dir / f"{src.stem} ({i}){src.suffix}"
        i += 1
    shutil.move(str(src), dest)
    return dest


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True))
    tmp.replace(path)


def ensure_tags(path: Path, artist: str, title: str) -> None:
    """Fill artist/title tags when a download has none (common for YouTube, some Soulseek files)."""
    import mutagen

    try:
        audio = mutagen.File(path, easy=True)
    except Exception:  # unreadable file: leave it for beets/quarantine
        return
    if audio is None:
        return
    changed = False
    if not audio.get("artist"):
        audio["artist"] = [artist]
        changed = True
    if not audio.get("title"):
        audio["title"] = [title]
        changed = True
    if changed:
        audio.save()
