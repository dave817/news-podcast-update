"""Acquire a transcript for one episode, cache it, and update the store.

Priority per episode:
  1. Native transcript (free): YouTube captions (yt-dlp) or Podcasting 2.0 RSS.
  2. ASR fallback: download audio -> Azure gpt-4o-transcribe, else local Whisper.

Usage:
    python3 src/get_transcript.py <episode_id> [--engine auto|azure|local]
    python3 src/get_transcript.py --all-new          # process every 'new' episode
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

import requests

import store
import transcribe_azure
import transcribe_local
from common import AUDIO, TRANSCRIPTS, env, log

# Browser-like UA: some podcast CDNs and transcript hosts reject bot-looking
# agents outright (YouTube's RSS endpoint 404s them — see feeds.py).
UA = {"User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")}


# --- VTT / caption cleaning --------------------------------------------------
_TS = re.compile(r"^\d{2}:\d{2}:\d{2}[.,]\d{3}\s-->")
_INLINE_TAG = re.compile(r"<[^>]+>")


def clean_vtt(vtt: str) -> str:
    lines: list[str] = []
    for raw in vtt.splitlines():
        line = raw.strip()
        if not line or line == "WEBVTT" or line.isdigit() or _TS.match(line):
            continue
        if line.startswith(("Kind:", "Language:", "NOTE")):
            continue
        line = _INLINE_TAG.sub("", line).strip()
        if line and (not lines or lines[-1] != line):  # dedup rolling auto-sub repeats
            lines.append(line)
    return "\n".join(lines).strip()


# --- Acquisition paths -------------------------------------------------------
def youtube_captions(url: str, eid: str, lang: str) -> str | None:
    langs = "en.*,en" if lang == "en" else "zh-Hans,zh-Hant,zh.*,zh,en"
    tmpl = str(AUDIO / f"{eid}.%(ext)s")
    subprocess.run(
        ["yt-dlp", "--skip-download", "--write-subs", "--write-auto-subs",
         "--sub-langs", langs, "--sub-format", "vtt", "--convert-subs", "vtt",
         "-o", tmpl, url],
        capture_output=True, text=True, errors="replace",
    )
    vtts = sorted(AUDIO.glob(f"{eid}*.vtt"))
    if not vtts:
        return None
    text = clean_vtt(vtts[0].read_text(encoding="utf-8", errors="ignore"))
    for v in vtts:
        v.unlink(missing_ok=True)
    return text or None


def youtube_audio(url: str, eid: str) -> Path:
    out = str(AUDIO / f"{eid}.%(ext)s")
    subprocess.run(
        ["yt-dlp", "-x", "--audio-format", "mp3", "--audio-quality", "5",
         "-o", out, url],
        capture_output=True, text=True, errors="replace", check=True,
    )
    files = [p for p in AUDIO.glob(f"{eid}.*") if p.suffix != ".vtt"]
    if not files:
        raise RuntimeError("yt-dlp produced no audio file")
    return files[0]


def download_audio(audio_url: str, eid: str) -> Path:
    ext = Path(audio_url.split("?")[0]).suffix or ".mp3"
    dest = AUDIO / f"{eid}{ext}"
    with requests.get(audio_url, headers=UA, stream=True, timeout=120, allow_redirects=True) as r:
        r.raise_for_status()
        with dest.open("wb") as fh:
            for chunk in r.iter_content(chunk_size=1 << 16):
                fh.write(chunk)
    return dest


def fetch_native_transcript(url: str) -> str | None:
    try:
        r = requests.get(url, headers=UA, timeout=60, allow_redirects=True)
        r.raise_for_status()
    except Exception:  # noqa: BLE001
        return None
    if url.endswith(".vtt") or "WEBVTT" in r.text[:64]:
        return clean_vtt(r.text)
    if url.endswith(".json") or r.headers.get("content-type", "").startswith("application/json"):
        try:
            data = r.json()
            segs = data.get("segments") or data.get("results") or []
            body = " ".join(s.get("body") or s.get("text", "") for s in segs)
            return body.strip() or None
        except Exception:  # noqa: BLE001
            return None
    return r.text.strip() or None


# --- ASR dispatch ------------------------------------------------------------
def asr(audio_path: Path, lang: str, engine: str) -> tuple[str, str]:
    engine = engine or env("TRANSCRIBE_ENGINE", "auto")
    if engine in ("auto", "azure"):
        try:
            text = transcribe_azure.transcribe_file(audio_path, lang or None)
            return text, "azure-asr"
        except Exception as e:  # noqa: BLE001
            if engine == "azure":
                raise
            log(f"  Azure ASR unavailable ({str(e)[:80]}); using local Whisper")
    text = transcribe_local.transcribe_file(audio_path, lang or None)
    return text, "local-asr"


# --- Orchestration -----------------------------------------------------------
def process(eid: str, engine: str = "") -> Path:
    row = store.get(eid)
    if row is None:
        raise SystemExit(f"unknown episode id {eid}")
    if row["transcript_path"] and Path(row["transcript_path"]).exists():
        log(f"  cached: {row['transcript_path']}")
        return Path(row["transcript_path"])

    lang = row["lang"] or ""
    text: str | None = None
    tsource = ""
    log(f"→ {row['source']} | {row['title'][:60]}")

    try:
        if row["native_transcript_url"]:
            text = fetch_native_transcript(row["native_transcript_url"])
            if text:
                tsource = "rss"
        if not text and row["url"] and "youtube.com" in row["url"]:
            text = youtube_captions(row["url"], eid, lang)
            if text:
                tsource = "captions"
        if not text:  # ASR fallback
            if row["audio_url"]:
                audio = download_audio(row["audio_url"], eid)
            else:  # youtube with no captions
                audio = youtube_audio(row["url"], eid)
            text, tsource = asr(audio, lang, engine)
            audio.unlink(missing_ok=True)  # drop large temp audio
    except Exception as e:  # noqa: BLE001
        store.mark(eid, status="error", error=str(e)[:500])
        raise

    if not text or len(text) < 40:
        store.mark(eid, status="error", error="empty transcript")
        raise RuntimeError(f"empty transcript for {eid}")

    dest = TRANSCRIPTS / f"{eid}.txt"
    header = f"# {row['title']}\nSource: {row['source']} | {row['published']} | {row['url']}\n\n"
    dest.write_text(header + text, encoding="utf-8")
    store.mark(eid, transcript_path=str(dest), transcript_source=tsource, status="transcribed")
    log(f"  ✓ {tsource}: {len(text)} chars -> {dest.name}")
    return dest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("episode_id", nargs="?", default=None)
    ap.add_argument("--engine", default="", help="auto|azure|local (default from .env)")
    ap.add_argument("--all-new", action="store_true", help="process every 'new' episode")
    args = ap.parse_args()

    store.init()
    if args.all_new:
        rows = store.by_status("new")
        log(f"processing {len(rows)} new episode(s)")
        for r in rows:
            try:
                process(r["id"], args.engine)
            except Exception as e:  # noqa: BLE001
                log(f"  ! {r['id']} failed: {e}")
        return 0
    if not args.episode_id:
        ap.error("provide an episode_id or --all-new")
    process(args.episode_id, args.engine)
    return 0


if __name__ == "__main__":
    sys.exit(main())
