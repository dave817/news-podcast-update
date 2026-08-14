"""Transcribe an audio file via Azure OpenAI gpt-4o-transcribe.

Handles arbitrarily long podcasts by re-encoding to small mono mp3 and splitting
into <25MB time chunks (Azure's per-request limit), transcribing each, and
stitching with approximate [mm:ss] offsets for quotable timestamps.

CLI:
    python3 src/transcribe_azure.py path/to/audio.mp3 [--language zh] [--out file.txt]
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

import requests

from common import env, log

# gpt-4o-transcribe has a per-request context limit (~16k tokens incl. audio +
# output), so chunks must be short — ~5 min is safe. (whisper-1 would allow 25 min,
# but gpt-4o-transcribe errors 'input_too_large' well before that.)
CHUNK_SECONDS = 300           # 5 min @ 64kbps mono ≈ 2.4 MB
BITRATE = "64k"
HTTP_TIMEOUT = 300


def _endpoint() -> tuple[str, str, str]:
    base = env("AZURE_OPENAI_BASE_URL").rstrip("/")
    key = env("AZURE_OPENAI_API_KEY")
    model = env("AZURE_TRANSCRIBE_MODEL", "gpt-4o-transcribe")
    version = env("AZURE_API_VERSION", "2025-03-01-preview")
    if not base or not key:
        raise RuntimeError("AZURE_OPENAI_BASE_URL / AZURE_OPENAI_API_KEY not set in .env")
    # Normalize to the resource root, then use Azure's classic inference path
    # (the /openai/v1 surface 404s transcription deployments on this resource).
    if base.endswith("/openai/v1"):
        base = base[: -len("/openai/v1")]
    url = f"{base}/openai/deployments/{model}/audio/transcriptions?api-version={version}"
    return url, key, model


def _ffprobe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, errors="replace",
    )
    try:
        return float((out.stdout or "0").strip())
    except ValueError:
        return 0.0


def _segment(path: Path, workdir: Path) -> list[Path]:
    """Re-encode to mono 64k mp3 and split into CHUNK_SECONDS pieces."""
    pattern = str(workdir / "chunk_%03d.mp3")
    subprocess.run(
        ["ffmpeg", "-nostdin", "-y", "-i", str(path),
         "-vn", "-ac", "1", "-c:a", "libmp3lame", "-b:a", BITRATE,
         "-f", "segment", "-segment_time", str(CHUNK_SECONDS), pattern],
        capture_output=True, text=True, errors="replace", check=True,
    )
    return sorted(workdir.glob("chunk_*.mp3"))


def _transcribe_chunk(chunk: Path, language: str | None) -> str:
    url, key, model = _endpoint()
    data = {"model": model, "response_format": "text"}
    if language:
        data["language"] = language
    with chunk.open("rb") as fh:
        files = {"file": (chunk.name, fh, "audio/mpeg")}
        r = requests.post(
            url, headers={"api-key": key}, data=data, files=files, timeout=HTTP_TIMEOUT
        )
    if r.status_code >= 400:
        raise RuntimeError(f"Azure transcribe {r.status_code}: {r.text[:300]}")
    ctype = r.headers.get("content-type", "")
    if "application/json" in ctype:
        return (r.json().get("text") or "").strip()
    return r.text.strip()


def _mmss(seconds: int) -> str:
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def transcribe_file(path: str | Path, language: str | None = None) -> str:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    duration = _ffprobe_duration(path)
    parts: list[str] = []
    with tempfile.TemporaryDirectory(prefix="asr_") as tmp:
        chunks = _segment(path, Path(tmp))
        log(f"  ASR: {len(chunks)} chunk(s), ~{int(duration)}s total")
        for i, chunk in enumerate(chunks):
            offset = i * CHUNK_SECONDS
            log(f"    transcribing chunk {i + 1}/{len(chunks)} @ {_mmss(offset)}")
            text = _transcribe_chunk(chunk, language)
            if len(chunks) > 1:
                parts.append(f"[{_mmss(offset)}] {text}")
            else:
                parts.append(text)
    return "\n\n".join(p for p in parts if p).strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("audio")
    ap.add_argument("--language", default=None, help="e.g. zh, en (default: auto-detect)")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    text = transcribe_file(args.audio, args.language)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        log(f"wrote {args.out} ({len(text)} chars)")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
