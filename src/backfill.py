"""Backfill archives: enumerate each show's back-catalog, enqueue episodes, and
(optionally) transcribe them. Memo-writing is done afterward by your AI agent
(see AGENTS.md, "Backfill mode"), reading the resulting transcripts.

Podcasts: the RSS feed carries the archive (often the full history).
YouTube:  the RSS caps at 15, so we enumerate the channel with yt-dlp.

Usage:
    python3 src/backfill.py --source "42章经" --limit 10
    python3 src/backfill.py --all --limit 10
    python3 src/backfill.py --source "Dan Koe Talks" --limit 20 --no-transcribe
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from urllib.parse import parse_qs, urlparse

import feedparser

import get_transcript
import store
from common import log
from feeds import UA, load_sources, normalize_entry


def enumerate_youtube(source: dict, limit: int | None) -> list[dict]:
    cid = parse_qs(urlparse(source["feed_url"]).query).get("channel_id", [""])[0]
    if not cid:
        log(f"  ! no channel_id in {source['feed_url']}")
        return []
    url = f"https://www.youtube.com/channel/{cid}/videos"
    args = ["yt-dlp", "--flat-playlist",
            "--print", "%(id)s\t%(title)s\t%(upload_date)s"]
    if limit:
        args += ["--playlist-items", f"1-{limit}"]
    args.append(url)
    out = subprocess.run(args, capture_output=True, text=True, timeout=180)
    eps: list[dict] = []
    for line in (out.stdout or "").splitlines():
        parts = line.split("\t")
        if len(parts) < 1 or not parts[0]:
            continue
        vid = parts[0]
        title = parts[1] if len(parts) > 1 else vid
        up = parts[2] if len(parts) > 2 else ""
        published = f"{up[:4]}-{up[4:6]}-{up[6:8]}" if len(up) == 8 else ""
        eps.append({
            "source": source["name"], "lang": source.get("lang", ""),
            "guid": vid, "title": title,
            "url": f"https://www.youtube.com/watch?v={vid}",
            "audio_url": "", "native_transcript_url": "",
            "published": published, "published_epoch": 0, "is_youtube": True,
        })
    return eps


def enumerate_podcast(source: dict, limit: int | None) -> list[dict]:
    parsed = feedparser.parse(source["feed_url"], request_headers=UA)
    eps = [normalize_entry(source, e) for e in (parsed.entries or [])]
    eps.sort(key=lambda x: x["published_epoch"], reverse=True)  # newest first
    return eps[:limit] if limit else eps


def backfill_source(source: dict, limit: int | None, transcribe: bool, pause: float) -> int:
    log(f"\n=== {source['name']} ===")
    eps = (enumerate_youtube if source.get("type") == "youtube"
           else enumerate_podcast)(source, limit)
    enq = 0
    for ep in eps:
        eid, is_new = store.upsert_episode(
            source=ep["source"], guid=ep["guid"], lang=ep["lang"],
            title=ep["title"], url=ep["url"], audio_url=ep["audio_url"],
            native_transcript_url=ep["native_transcript_url"],
            published=ep["published"],
        )
        if is_new:
            enq += 1
        if not transcribe:
            continue
        row = store.get(eid)
        if row["status"] in ("transcribed", "memo_done", "delivered"):
            continue
        try:
            get_transcript.process(eid)
            time.sleep(pause)
        except Exception as e:  # noqa: BLE001
            log(f"  ! {ep['title'][:40]}: {e}")
    log(f"  enqueued {enq} new; {'transcribed' if transcribe else 'enqueue-only'}")
    return enq


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--source", default=None)
    ap.add_argument("--limit", type=int, default=None, help="max episodes per source")
    ap.add_argument("--no-transcribe", action="store_true",
                    help="only enqueue into the DB; don't transcribe yet")
    ap.add_argument("--pause", type=float, default=1.0, help="seconds between episodes")
    args = ap.parse_args()
    if not args.all and not args.source:
        ap.error("pass --all or --source")

    store.init()
    run_id = store.start_run("backfill")
    total = 0
    # Process highest-priority shows first so the most valuable transcripts land first.
    prio = {"very_high": 0, "high": 1, "medium": 2, "low": 3}
    sources = sorted(load_sources(), key=lambda s: prio.get(s.get("priority", "medium"), 2))
    for src in sources:
        if args.source and args.source.lower() not in src["name"].lower():
            continue
        total += backfill_source(src, args.limit, not args.no_transcribe, args.pause)
    store.finish_run(run_id, total, f"limit={args.limit}")
    log(f"\nbackfill complete: {total} new episode(s) enqueued")
    log("next: have your agent write the memos — Claude Code: /daily-brief backfill;")
    log("      Codex: ask it to follow AGENTS.md backfill mode")
    return 0


if __name__ == "__main__":
    sys.exit(main())
