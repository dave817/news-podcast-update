"""Load feeds.yaml and normalize feed entries into a common episode dict.

Shared by check_updates.py (daily) and backfill.py (archive) so parsing lives
in one place.
"""
from __future__ import annotations

import calendar
import time
from typing import Iterator

import feedparser
import yaml

from common import FEEDS_YAML

# Browser-like UA on purpose: YouTube's videos.xml endpoint 404s bot-looking
# agents, and it also 404s at random — hence the retry in iter_feed_entries().
UA = {"User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")}
FEED_TRIES = 3

TRANSCRIPT_TYPES = {"application/json", "text/vtt", "application/x-subrip", "text/plain"}


def load_sources() -> list[dict]:
    data = yaml.safe_load(FEEDS_YAML.read_text(encoding="utf-8"))
    return data.get("sources", [])


def _published(entry) -> tuple[str, float]:
    """Return (iso_date, epoch). Falls back to empty/0 when missing."""
    st = entry.get("published_parsed") or entry.get("updated_parsed")
    if st:
        epoch = calendar.timegm(st)
        return time.strftime("%Y-%m-%d", st), epoch
    return "", 0.0


def _enclosure(entry) -> str:
    for enc in entry.get("enclosures", []) or []:
        href = enc.get("href") or enc.get("url")
        if href:
            return href
    for link in entry.get("links", []) or []:
        if link.get("rel") == "enclosure" and link.get("href"):
            return link["href"]
    return ""


def _native_transcript(entry) -> str:
    """Best-effort Podcasting 2.0 <podcast:transcript> detection."""
    pt = entry.get("podcast_transcript")
    if isinstance(pt, dict) and pt.get("url"):
        return pt["url"]
    for link in entry.get("links", []) or []:
        if link.get("type") in TRANSCRIPT_TYPES and "transcript" in (link.get("rel", "") + link.get("href", "")).lower():
            return link.get("href", "")
    return ""


def normalize_entry(source: dict, entry) -> dict:
    is_youtube = source.get("type") == "youtube"
    if is_youtube:
        guid = entry.get("yt_videoid") or entry.get("id") or entry.get("link", "")
    else:
        guid = entry.get("id") or entry.get("guid") or entry.get("link", "")
    iso, epoch = _published(entry)
    return {
        "source": source["name"],
        "lang": source.get("lang", ""),
        "guid": guid,
        "title": entry.get("title", "(untitled)"),
        "url": entry.get("link", ""),
        "audio_url": "" if is_youtube else _enclosure(entry),
        "native_transcript_url": "" if is_youtube else _native_transcript(entry),
        "published": iso,
        "published_epoch": epoch,
        "is_youtube": is_youtube,
    }


def iter_feed_entries(source: dict) -> Iterator[dict]:
    """Yield normalized entries, retrying feeds that transiently return nothing.

    A silent empty feed would look exactly like "no new episodes", so a flaky
    source could go unnoticed for days. Retrying makes that far less likely.
    """
    parsed = None
    for attempt in range(1, FEED_TRIES + 1):
        parsed = feedparser.parse(source["feed_url"], request_headers=UA)
        if parsed.entries:
            break
        if attempt < FEED_TRIES:
            time.sleep(1.5 * attempt)
    for entry in (parsed.entries if parsed else []) or []:
        yield normalize_entry(source, entry)
