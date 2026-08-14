"""Daily watcher: poll all feeds, record episodes, emit a manifest of NEW ones.

"New" = not previously seen (dedup by source+guid) AND published within
--max-age-days (guards against a cold-start flood of the whole backlog; the
historical archive is the job of backfill.py).

Usage:
    python3 src/check_updates.py                 # human summary + JSON manifest
    python3 src/check_updates.py --json          # JSON manifest only (for the skill)
    python3 src/check_updates.py --max-age-days 45
    python3 src/check_updates.py --source "42章经"
"""
from __future__ import annotations

import argparse
import json
import sys
import time

import store
from common import log
from feeds import iter_feed_entries, load_sources


def check(max_age_days: int, source_filter: str | None) -> list[dict]:
    store.init()
    run_id = store.start_run("daily")
    cutoff = time.time() - max_age_days * 86400
    new_eps: list[dict] = []
    sources = load_sources()
    for src in sources:
        if source_filter and source_filter.lower() not in src["name"].lower():
            continue
        try:
            entries = list(iter_feed_entries(src))
        except Exception as e:  # noqa: BLE001
            log(f"  ! {src['name']}: feed error {e}")
            continue
        fresh = 0
        for ep in entries:
            if ep["published_epoch"] and ep["published_epoch"] < cutoff:
                continue  # too old for the daily window -> backfill's job
            eid, is_new = store.upsert_episode(
                source=ep["source"], guid=ep["guid"], lang=ep["lang"],
                title=ep["title"], url=ep["url"], audio_url=ep["audio_url"],
                native_transcript_url=ep["native_transcript_url"],
                published=ep["published"],
            )
            if is_new:
                fresh += 1
                new_eps.append({"id": eid, **{k: ep[k] for k in
                                ("source", "lang", "title", "published", "url")}})
        log(f"  {src['name']:<22} {len(entries):>3} in feed, {fresh} new")
    store.finish_run(run_id, len(new_eps), f"max_age={max_age_days}d")
    return new_eps


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-age-days", type=int, default=30)
    ap.add_argument("--source", default=None)
    ap.add_argument("--json", action="store_true", help="print only the JSON manifest")
    args = ap.parse_args()

    new_eps = check(args.max_age_days, args.source)
    if not args.json:
        log(f"\n{len(new_eps)} new episode(s) to process")
    print(json.dumps(new_eps, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
