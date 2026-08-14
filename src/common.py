"""Shared helpers: project paths, .env loading, logging, slugs.

Kept dependency-light on purpose so every script imports the same primitives.
"""
from __future__ import annotations

import hashlib
import os
import re
import sys
import unicodedata
from pathlib import Path

# --- Paths -------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
AUDIO = DATA / "audio"
TRANSCRIPTS = DATA / "transcripts"
MEMOS = DATA / "memos"
DB_PATH = DATA / "episodes.sqlite"
FEEDS_YAML = ROOT / "feeds.yaml"
PERSONA = ROOT / "persona" / "profile.md"
MEMO_TEMPLATE = ROOT / "persona" / "memo_template.md"

for _d in (DATA, AUDIO, TRANSCRIPTS, MEMOS):
    _d.mkdir(parents=True, exist_ok=True)


# --- .env loading (no external dependency) -----------------------------------
def load_env(path: Path | None = None) -> dict[str, str]:
    """Parse KEY=VALUE lines from .env into os.environ (does not overwrite existing)."""
    path = path or (ROOT / ".env")
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        values[key] = val
        os.environ.setdefault(key, val)
    return values


def env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


# --- Logging -----------------------------------------------------------------
def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


# --- Identity / filenames ----------------------------------------------------
def slugify(text: str, maxlen: int = 60) -> str:
    """ASCII-ish slug; keeps CJK by transliterating to a short hash suffix when needed."""
    text = (text or "").strip()
    ascii_text = (
        unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    )
    ascii_text = re.sub(r"[^\w\s-]", "", ascii_text).strip().lower()
    ascii_text = re.sub(r"[\s_-]+", "-", ascii_text)
    if len(ascii_text) < 3:  # mostly-CJK title -> fall back to hash
        ascii_text = "ep-" + hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]
    return ascii_text[:maxlen].strip("-") or "untitled"


def episode_id(source_name: str, guid: str) -> str:
    """Stable per-episode id used for dedup and cache filenames."""
    return hashlib.sha1(f"{source_name}::{guid}".encode("utf-8")).hexdigest()[:16]


# Load .env on import so every script has creds available.
load_env()
