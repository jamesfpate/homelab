"""Optional local-LLM stage via Ollama: cleaner Reddit title parsing and taste scoring.

Enabled by OLLAMA_URL. Scoring is shadow-only unless LLM_FILTER=true: scores are logged (history.scores) and shown
on the dashboard so the filter can be judged against real keep rates before it changes what gets downloaded.
"""

import json

import requests

from .config import Config
from .util import log

_BATCH = 25

_PARSE_SYSTEM = """You extract music from Reddit post titles. For each input line, return whether it names one
specific track or one specific album, and the artist and the track/album title with tags, years, commentary and
"(Official Video)" style suffixes removed. kind is "track", "album" or "other". Use "other" for discussion
threads, live/tour posts, playlists, articles, interviews, and for anniversaries, reissues, box sets and live
collections of old releases (these are not new recommendations). Reply with JSON only:
{"items": [{"i": <index>, "kind": "track|album|other", "artist": "<artist>", "title": "<track or album title>"}]}"""

_SCORE_SYSTEM = """You rate how well a music recommendation fits one listener's taste. You are given artists the
listener loves, artists they kept from earlier recommendations, artists they disliked, and a list of candidates
(artist, title, where it was recommended). Score each candidate 0-10 for how likely this listener is to want to keep
it: 9-10 clearly their taste, 5-6 plausible, 0-2 clearly not. Judge by musical style, era and scene, not
popularity. Reply with JSON only: {"items": [{"i": <index>, "score": <0-10>, "reason": "<one short clause>"}]}"""


def enabled(cfg: Config) -> bool:
    return bool(cfg.ollama_url)


def _chat(cfg: Config, system: str, user: str) -> dict:
    r = requests.post(
        f"{cfg.ollama_url}/api/chat",
        json={
            "model": cfg.ollama_model,
            "stream": False,
            "think": False,  # gemma reasons for thousands of tokens otherwise and the JSON gets truncated
            "format": "json",
            "options": {"temperature": 0, "num_ctx": 8192},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        },
        timeout=cfg.ollama_timeout_s,
    )
    r.raise_for_status()
    return json.loads(r.json()["message"]["content"])


def _items(data: dict, n: int) -> dict[int, dict]:
    out = {}
    for it in data.get("items", []) if isinstance(data, dict) else []:
        try:
            i = int(it["i"])
        except (KeyError, TypeError, ValueError):
            continue
        if 0 <= i < n:
            out[i] = it
    return out


def parse_titles(cfg: Config, sub: str, titles: list[str]) -> list[dict | None] | None:
    """Per title: {"kind", "artist", "title"}; None entries for unparsed. Returns None if the model call failed."""
    result: list[dict | None] = [None] * len(titles)
    for start in range(0, len(titles), _BATCH):
        chunk = titles[start : start + _BATCH]
        user = f"Subreddit: r/{sub}\n" + "\n".join(f"{i}: {t}" for i, t in enumerate(chunk))
        try:
            items = _items(_chat(cfg, _PARSE_SYSTEM, user), len(chunk))
        except Exception as e:
            log.warning("llm parse failed for r/%s: %s", sub, e)
            return None
        for i, it in items.items():
            kind = str(it.get("kind", "other")).lower()
            artist, title = str(it.get("artist", "")).strip(), str(it.get("title", "")).strip()
            if kind in ("track", "album") and artist and title:
                result[start + i] = {"kind": kind, "artist": artist, "title": title}
    return result


def score(cfg: Config, taste: dict[str, list[str]], cands: list[tuple[str, str, str]]) -> dict[int, tuple[int, str]]:
    """cands: (source, artist, title). Returns index -> (score, reason) for what the model managed to score."""
    out: dict[int, tuple[int, str]] = {}
    profile = (
        f"Loves: {', '.join(taste.get('loved', [])[:80]) or '(none yet)'}\n"
        f"Kept: {', '.join(taste.get('kept', [])[:60]) or '(none yet)'}\n"
        f"Disliked: {', '.join(taste.get('disliked', [])[:60]) or '(none yet)'}\n"
    )
    for start in range(0, len(cands), _BATCH):
        chunk = cands[start : start + _BATCH]
        user = profile + "Candidates:\n" + "\n".join(f"{i}: {a} - {t} (from {s})" for i, (s, a, t) in enumerate(chunk))
        try:
            items = _items(_chat(cfg, _SCORE_SYSTEM, user), len(chunk))
        except Exception as e:
            log.warning("llm scoring failed: %s", e)
            return out
        for i, it in items.items():
            try:
                sc = max(0, min(10, int(round(float(it.get("score"))))))
            except (TypeError, ValueError):
                continue
            out[start + i] = (sc, str(it.get("reason", "")).strip()[:160])
    return out
