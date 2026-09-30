"""Static dashboard (/config/www/index.html) from the event history: inbox by source, source scorecard, activity."""

import html
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from .config import Config
from .history import connect, source_from_path
from .util import AUDIO_EXTS, log

_OUTCOMES = ("kept", "disliked", "heard", "stale")


def run(cfg: Config, out_dir: Path | None = None) -> Path:
    out_dir = out_dir or cfg.state_dir / "www"
    out_dir.mkdir(parents=True, exist_ok=True)
    with connect(cfg) as con:
        page = render(cfg, con)
    out = out_dir / "index.html"
    out.write_text(page)
    log.info("report written: %s", out)
    return out


def _inbox_now(cfg: Config) -> Counter:
    counts: Counter = Counter()
    if cfg.inbox_dir.exists():
        for f in cfg.inbox_dir.rglob("*"):
            if f.is_file() and f.suffix.lower() in AUDIO_EXTS:
                counts[source_from_path(cfg, f) or "?"] += 1
    return counts


def _scorecard(con: sqlite3.Connection, since: str | None) -> dict[str, Counter]:
    rows = con.execute(
        "select source, action, count(*) n from events where source is not null and (? is null or ts >= ?) "
        "group by source, action", (since, since),
    )
    card: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        card[r["source"]][r["action"]] = r["n"]
    return card


def _last(con: sqlite3.Connection, actions: tuple[str, ...]) -> str | None:
    q = ",".join("?" * len(actions))
    row = con.execute(f"select max(ts) ts from events where action in ({q})", actions).fetchone()
    return row["ts"] if row and row["ts"] else None


def render(cfg: Config, con: sqlite3.Connection) -> str:
    e = html.escape
    now = datetime.now()
    inbox = _inbox_now(cfg)
    all_time = _scorecard(con, None)
    month = _scorecard(con, (now - timedelta(days=30)).isoformat(timespec="seconds"))
    sources = sorted(set(all_time) | set(inbox), key=lambda s: -(all_time[s]["added"] + inbox[s]))
    recent = con.execute("select * from events order by id desc limit 150").fetchall()
    kept = con.execute("select * from events where action='kept' order by id desc limit 200").fetchall()
    wanted = con.execute("select * from events where action='wanted' order by id desc limit 50").fetchall()

    def rate(c: Counter) -> float | None:
        decided = c["kept"] + c["disliked"] + c["heard"]
        return c["kept"] / decided if decided else None

    def pct(x: float | None) -> str:
        return f"{x * 100:.0f}%" if x is not None else "–"

    # Keep rate per source: one measure, one hue, direct-labelled; table below carries the numbers.
    bars = []
    for s in sources:
        c = all_time[s]
        decided = c["kept"] + c["disliked"] + c["heard"]
        r = rate(c)
        w = 0 if r is None else max(2, round(r * 100))
        label = f"{pct(r)} ({c['kept']} of {decided})" if decided else "no decisions yet"
        bars.append(
            f'<div class="row" title="{e(s)}: {e(label)}"><div class="lbl">{e(s)}</div>'
            f'<div class="track"><div class="bar" style="width:{w}%"></div></div><div class="val">{e(label)}</div></div>'
        )

    def score_rows(card: dict[str, Counter]) -> str:
        out = []
        for s in sources:
            c = card.get(s, Counter())
            out.append(
                f"<tr><td>{e(s)}</td><td class=n>{inbox[s]}</td><td class=n>{c['added']}</td><td class=n>{c['kept']}</td>"
                f"<td class=n>{c['disliked']}</td><td class=n>{c['heard']}</td><td class=n>{c['not_found']}</td>"
                f"<td class=n>{pct(rate(c))}</td></tr>"
            )
        return "".join(out)

    def ev_rows(rows) -> str:
        out = []
        for r in rows:
            what = f"{r['artist']} - {r['album']}" if r["action"] == "wanted" else (
                f"{r['artist']} - {r['title']}" if r["title"] else (r["album"] or r["path"] or ""))
            out.append(
                f"<tr><td class=ts>{e(r['ts'].replace('T', ' '))}</td><td><span class='tag {e(r['action'])}'>{e(r['action'])}</span></td>"
                f"<td>{e(r['source'] or '')}</td><td>{e(what)}</td></tr>"
            )
        return "".join(out) or "<tr><td colspan=4 class=muted>nothing yet</td></tr>"

    # Shadow scoring: does the LLM's score predict what gets kept? Decided events joined to their latest score.
    buckets = {"0-3": Counter(), "4-6": Counter(), "7-10": Counter()}
    for r in con.execute(
        "select e.action, s.score from events e join scores s on lower(s.artist)=lower(e.artist) and lower(s.title)=lower(e.title) "
        "where e.action in ('kept','disliked','heard') group by e.id having s.id = max(s.id)"
    ):
        b = "0-3" if r["score"] <= 3 else "4-6" if r["score"] <= 6 else "7-10"
        buckets[b]["decided"] += 1
        if r["action"] == "kept":
            buckets[b]["kept"] += 1
    latest_batch = con.execute("select max(batch) b from scores").fetchone()["b"]
    top = con.execute("select * from scores where batch=? order by score desc, id limit 12", (latest_batch,)).fetchall() if latest_batch else []
    scored_total = con.execute("select count(*) n from scores").fetchone()["n"]
    bucket_rows = "".join(
        f"<tr><td>{k}</td><td class=n>{c['decided']}</td><td class=n>{c['kept']}</td><td class=n>{pct(c['kept'] / c['decided'] if c['decided'] else None)}</td></tr>"
        for k, c in buckets.items()
    )
    top_rows = "".join(
        f"<tr><td class=n>{r['score']}</td><td>{e(r['source'] or '')}</td><td>{e(r['artist'])} - {e(r['title'])}</td><td class=muted>{e(r['reason'] or '')}</td></tr>"
        for r in top
    ) or "<tr><td colspan=4 class=muted>no scores yet</td></tr>"
    llm_section = f"""
<h2>Taste score{' (shadow: logged, not filtering)' if not cfg.llm_filter else ' (filtering below ' + str(cfg.llm_min_score) + ')'}</h2>
<div class="sub" style="margin-bottom:8px">Local LLM score 0–10 per candidate, {scored_total} scored so far. Keep rate by score bucket shows whether the score predicts what you star.</div>
<div class="wrap"><table><tr><th>Score</th><th class=n>Decided</th><th class=n>Kept</th><th class=n>Keep rate</th></tr>{bucket_rows}</table></div>
<h2>Latest batch, highest scored{f' ({e(latest_batch)})' if latest_batch else ''}</h2>
<div class="wrap"><table><tr><th class=n>Score</th><th>Source</th><th>Track</th><th>Why</th></tr>{top_rows}</table></div>""" if cfg.ollama_url else ""

    last_ingest = _last(con, ("added", "not_found"))
    last_promote = _last(con, _OUTCOMES)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Music Inbox</title>
<style>
  :root {{ --page:#f9f9f7; --surface:#fcfcfb; --ink:#0b0b0b; --ink2:#52514e; --muted:#898781; --grid:#e1e0d9; --line:#c3c2b7;
          --series:#2a78d6; --good:#006300; --serious:#ec835a; --critical:#d03b3b; --warn:#fab219; }}
  @media (prefers-color-scheme: dark) {{ :root {{ --page:#0d0d0d; --surface:#1a1a19; --ink:#fff; --ink2:#c3c2b7; --grid:#2c2c2a; --line:#383835;
          --series:#3987e5; --good:#0ca30c; }} }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; padding:24px 16px 48px; background:var(--page); color:var(--ink); font:15px/1.45 system-ui, sans-serif; }}
  main {{ max-width:1100px; margin:0 auto; }}
  h1 {{ font-size:22px; margin:0 0 4px; }} h2 {{ font-size:16px; margin:32px 0 10px; }}
  .sub {{ color:var(--ink2); font-size:13px; }}
  .tiles {{ display:flex; gap:12px; flex-wrap:wrap; margin:18px 0; }}
  .tile {{ background:var(--surface); border:1px solid var(--grid); border-radius:10px; padding:12px 16px; min-width:150px; }}
  .tile .k {{ font-size:12px; color:var(--ink2); }} .tile .v {{ font-size:26px; font-weight:600; font-variant-numeric:tabular-nums; }}
  .chart {{ background:var(--surface); border:1px solid var(--grid); border-radius:10px; padding:14px 16px; }}
  .row {{ display:grid; grid-template-columns:minmax(120px,180px) 1fr minmax(120px,auto); align-items:center; gap:12px; padding:5px 0; }}
  .lbl {{ color:var(--ink2); font-size:13px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
  .track {{ height:14px; background:var(--grid); border-radius:0 4px 4px 0; }}
  .bar {{ height:100%; background:var(--series); border-radius:0 4px 4px 0; }}
  .val {{ font-size:13px; color:var(--ink2); font-variant-numeric:tabular-nums; }}
  table {{ width:100%; border-collapse:collapse; background:var(--surface); border:1px solid var(--grid); border-radius:10px; font-size:14px; }}
  th, td {{ text-align:left; padding:7px 10px; border-bottom:1px solid var(--grid); vertical-align:top; }}
  th {{ color:var(--ink2); font-weight:500; font-size:12px; }} td.n, th.n {{ text-align:right; font-variant-numeric:tabular-nums; }}
  td.ts {{ color:var(--muted); white-space:nowrap; font-size:13px; }} .muted {{ color:var(--muted); }}
  .tag {{ font-size:12px; padding:1px 7px; border-radius:10px; border:1px solid var(--line); color:var(--ink2); }}
  .tag.kept {{ color:var(--good); border-color:var(--good); }} .tag.disliked {{ color:var(--critical); border-color:var(--critical); }}
  .tag.heard, .tag.stale {{ color:var(--serious); border-color:var(--serious); }} .tag.not_found {{ color:var(--muted); }}
  .tag.wanted {{ color:var(--series); border-color:var(--series); }}
  .wrap {{ overflow-x:auto; }}
</style></head><body><main>
<h1>Music Inbox</h1>
<div class="sub">Updated {e(now.strftime('%Y-%m-%d %H:%M'))} · last ingest {e((last_ingest or 'never').replace('T', ' '))} · last promote {e((last_promote or 'never').replace('T', ' '))}{' · DRY RUN' if cfg.dry_run else ''}</div>
<div class="tiles">
  <div class="tile"><div class="k">In the inbox now</div><div class="v">{sum(inbox.values())}</div></div>
  <div class="tile"><div class="k">Kept, last 30 days</div><div class="v">{sum(c['kept'] for c in month.values())}</div></div>
  <div class="tile"><div class="k">Dropped, last 30 days</div><div class="v">{sum(c['disliked'] + c['heard'] for c in month.values())}</div></div>
  <div class="tile"><div class="k">Kept, all time</div><div class="v">{sum(c['kept'] for c in all_time.values())}</div></div>
</div>
<h2>Keep rate by source</h2>
<div class="sub" style="margin-bottom:8px">Share of decided tracks (kept, disliked or heard-and-dropped) that you starred.</div>
<div class="chart">{''.join(bars) or '<div class=muted>no sources yet</div>'}</div>
<h2>Sources, last 30 days</h2>
<div class="wrap"><table><tr><th>Source</th><th class=n>Inbox now</th><th class=n>Added</th><th class=n>Kept</th><th class=n>Disliked</th><th class=n>Heard, dropped</th><th class=n>Not found</th><th class=n>Keep rate</th></tr>{score_rows(month)}</table></div>
<h2>Sources, all time</h2>
<div class="wrap"><table><tr><th>Source</th><th class=n>Inbox now</th><th class=n>Added</th><th class=n>Kept</th><th class=n>Disliked</th><th class=n>Heard, dropped</th><th class=n>Not found</th><th class=n>Keep rate</th></tr>{score_rows(all_time)}</table></div>
{llm_section}
<h2>Wanted albums (album stars → Lidarr)</h2>
<div class="wrap"><table><tr><th>When</th><th></th><th>Via</th><th>Album</th></tr>{ev_rows(wanted)}</table></div>
<h2>Kept</h2>
<div class="wrap"><table><tr><th>When</th><th></th><th>Source</th><th>Track</th></tr>{ev_rows(kept)}</table></div>
<h2>Recent activity</h2>
<div class="wrap"><table><tr><th>When</th><th>Action</th><th>Source</th><th>Track</th></tr>{ev_rows(recent)}</table></div>
</main></body></html>
"""
