"""Add a source by pasting almost any link — this is the "just give it a link" entry point.

Accepts:
  * Apple Podcasts page   https://podcasts.apple.com/us/podcast/name/id1234567890
  * YouTube channel/video https://youtube.com/@SomeChannel  ·  /channel/UC...  ·  /watch?v=...
  * A direct RSS feed     https://feeds.example.com/show.rss
  * Any podcast homepage  (auto-discovers the RSS link in the page)
  * A plain show name     "Lenny's Podcast"   (searched on Apple Podcasts)

It resolves the real machine-readable feed, checks that it actually parses,
then appends it to feeds.yaml with a sensible name.

Usage:
    python3 src/add_feed.py "https://podcasts.apple.com/us/podcast/x/id123"
    python3 src/add_feed.py "https://youtube.com/@DanKoeTalks"
    python3 src/add_feed.py "Lenny's Podcast"
    python3 src/add_feed.py "<link>" --name "My Nickname" --lang en
    python3 src/add_feed.py --list
    python3 src/add_feed.py --remove "Lenny's Podcast"
"""
from __future__ import annotations

import argparse
import re
import sys
import time

import feedparser
import requests
import yaml

from common import FEEDS_YAML, log

# A browser-like UA matters: YouTube's RSS endpoint 404s bot-looking agents.
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
HEADERS = {"User-Agent": UA}
TIMEOUT = 25
FETCH_TRIES = 3          # YouTube in particular returns transient 404s


def fetch_feed(url: str, tries: int = FETCH_TRIES):
    """Fetch + parse a feed, retrying transient failures (YouTube 404s at random)."""
    last = None
    for attempt in range(1, tries + 1):
        try:
            r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            parsed = feedparser.parse(r.content)
            if parsed.entries:
                return parsed
            last = f"HTTP {r.status_code}, no entries"
        except Exception as e:  # noqa: BLE001
            last = str(e)
        if attempt < tries:
            time.sleep(1.5 * attempt)
    log(f"  … feed did not return episodes after {tries} tries ({last})")
    return None


# --- resolution helpers ------------------------------------------------------
def _itunes_lookup(apple_id: str) -> str:
    r = requests.get("https://itunes.apple.com/lookup", params={"id": apple_id},
                     headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    results = r.json().get("results", [])
    if not results or not results[0].get("feedUrl"):
        raise RuntimeError(f"Apple Podcasts has no RSS feed for id {apple_id}")
    return results[0]["feedUrl"]


def _itunes_search(term: str) -> str:
    r = requests.get("https://itunes.apple.com/search",
                     params={"term": term, "entity": "podcast", "limit": 5},
                     headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    for res in r.json().get("results", []):
        if res.get("feedUrl"):
            log(f"  matched '{res.get('collectionName', term)}' on Apple Podcasts")
            return res["feedUrl"]
    raise RuntimeError(f"no podcast found for '{term}' — try pasting the RSS or Apple link")


def _youtube_channel_id(url: str) -> str:
    """Get a UC... channel id from any YouTube URL (channel, handle, or video)."""
    m = re.search(r"/channel/(UC[\w-]{20,})", url)
    if m:
        return m.group(1)
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    for pattern in (r'"channelId":"(UC[\w-]{20,})"',
                    r'channel/(UC[\w-]{20,})',
                    r'"externalChannelId":"(UC[\w-]{20,})"'):
        m = re.search(pattern, r.text)
        if m:
            return m.group(1)
    raise RuntimeError("could not find the YouTube channel id on that page")


def _discover_rss(url: str) -> str:
    """Find an RSS/Atom feed advertised in a normal web page."""
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    m = re.search(
        r'<link[^>]+type=["\']application/(?:rss|atom)\+xml["\'][^>]*href=["\']([^"\']+)["\']',
        r.text, re.I)
    if not m:
        m = re.search(
            r'<link[^>]+href=["\']([^"\']+)["\'][^>]*type=["\']application/(?:rss|atom)\+xml["\']',
            r.text, re.I)
    if not m:
        raise RuntimeError("no RSS feed found on that page — paste the RSS URL directly")
    href = m.group(1)
    if href.startswith("/"):
        href = re.sub(r"^(https?://[^/]+).*$", r"\1", url) + href
    return href


def resolve(link: str) -> tuple[str, str]:
    """Return (feed_url, source_type) for anything the user pasted."""
    link = link.strip()

    if not link.lower().startswith(("http://", "https://")):
        return _itunes_search(link), "podcast"

    if "podcasts.apple.com" in link:
        m = re.search(r"/id(\d+)", link)
        if not m:
            raise RuntimeError("that Apple Podcasts link has no /id… in it")
        return _itunes_lookup(m.group(1)), "podcast"

    if "youtube.com" in link or "youtu.be" in link:
        if "feeds/videos.xml" in link:
            return link, "youtube"
        cid = _youtube_channel_id(link)
        return f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}", "youtube"

    # Looks like a feed already? Try parsing it before anything cleverer.
    if re.search(r"(\.xml|\.rss|/rss|/feed)(\?|$|/)", link, re.I):
        return link, "podcast"

    parsed = feedparser.parse(link, request_headers=HEADERS)
    if parsed.entries:
        return link, "podcast"

    return _discover_rss(link), "podcast"


# --- feeds.yaml I/O ----------------------------------------------------------
def load_yaml() -> dict:
    if not FEEDS_YAML.exists():
        return {"sources": []}
    return yaml.safe_load(FEEDS_YAML.read_text(encoding="utf-8")) or {"sources": []}


def save_yaml(data: dict) -> None:
    FEEDS_YAML.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def guess_lang(text: str) -> str:
    return "zh" if re.search(r"[一-鿿]", text or "") else "en"


def cmd_add(link: str, name: str | None, lang: str | None, priority: str) -> int:
    log(f"→ resolving {link}")
    feed_url, kind = resolve(link)
    log(f"  feed: {feed_url}")

    parsed = fetch_feed(feed_url)
    entries = (parsed.entries or []) if parsed else []
    if not entries and not name:
        # Transient upstream failures are common (YouTube especially). Only refuse
        # when we also have no name to fall back on.
        log("  ! could not read that feed right now. If the link is right, retry in a")
        log("    minute, or force it with:  --name \"Your Name\" --lang en")
        return 1
    feed_title = (parsed.feed or {}).get("title", "") if parsed and hasattr(parsed, "feed") else ""
    final_name = name or feed_title or link
    first_title = entries[0].get("title", "") if entries else ""
    final_lang = lang or guess_lang(f"{feed_title} {first_title}")

    data = load_yaml()
    sources = data.setdefault("sources", [])
    for s in sources:
        if s.get("feed_url") == feed_url:
            log(f"  already in feeds.yaml as '{s.get('name')}' — nothing to do")
            return 0

    sources.append({"name": final_name, "type": kind, "lang": final_lang,
                    "priority": priority, "feed_url": feed_url})
    save_yaml(data)

    if entries:
        log(f"  ✓ added '{final_name}' ({kind}, {final_lang}) — {len(entries)} episodes in feed")
        log(f"    latest: {entries[0].get('title', '')[:70]}")
    else:
        log(f"  ✓ added '{final_name}' ({kind}, {final_lang}) — unverified, the feed was")
        log("    unreachable just now; it will be picked up on the next daily run")
    log(f"\n{len(sources)} source(s) in feeds.yaml")
    return 0


def cmd_list() -> int:
    sources = load_yaml().get("sources", [])
    if not sources:
        log("no sources yet — add one with:  python3 src/add_feed.py \"<link>\"")
        return 0
    for i, s in enumerate(sources, 1):
        log(f"{i:>2}. {s.get('name', '?')}  [{s.get('type', '?')}/{s.get('lang', '?')}]")
        log(f"    {s.get('feed_url', '')}")
    return 0


def cmd_remove(name: str) -> int:
    data = load_yaml()
    sources = data.get("sources", [])
    keep = [s for s in sources if name.lower() not in (s.get("name", "") or "").lower()]
    if len(keep) == len(sources):
        log(f"no source matching '{name}'")
        return 1
    data["sources"] = keep
    save_yaml(data)
    log(f"  ✓ removed {len(sources) - len(keep)} source(s); {len(keep)} left")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Add a podcast/YouTube source by link or name.")
    ap.add_argument("link", nargs="?", help="Apple/YouTube/RSS link, homepage, or show name")
    ap.add_argument("--name", default=None, help="override the display name")
    ap.add_argument("--lang", default=None, choices=["en", "zh"], help="override detected language")
    ap.add_argument("--priority", default="high", choices=["very_high", "high", "medium", "low"])
    ap.add_argument("--list", action="store_true", help="show current sources")
    ap.add_argument("--remove", metavar="NAME", help="remove a source by (partial) name")
    args = ap.parse_args()

    if args.list:
        return cmd_list()
    if args.remove:
        return cmd_remove(args.remove)
    if not args.link:
        ap.print_help()
        return 1
    try:
        return cmd_add(args.link, args.name, args.lang, args.priority)
    except Exception as e:  # noqa: BLE001
        log(f"  ! {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
