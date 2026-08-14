"""Local transcription via faster-whisper (ctranslate2, no torch).

Fallback engine when the Azure transcription deployment is unavailable, or for
offline / zero-cost runs. Emits [mm:ss] markers periodically for quotable timing.

CLI:
    python3 src/transcribe_local.py audio.mp3 [--language zh] [--model small]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from common import env, log

_MODEL_CACHE: dict[str, object] = {}


def _get_model(model_size: str):
    if model_size not in _MODEL_CACHE:
        try:
            from faster_whisper import WhisperModel  # lazy: heavy import
        except ImportError as e:  # not installed by default — it's a big download
            raise RuntimeError(
                "Local transcription needs faster-whisper, which isn't installed.\n"
                "  Install it:   .venv/bin/pip install -r requirements-local-asr.txt\n"
                "  Or skip it:   add Azure keys to .env (see .env.example),\n"
                "                or stick to shows that publish captions (free, instant)."
            ) from e
        log(f"  loading whisper model '{model_size}' (first run downloads it)…")
        _MODEL_CACHE[model_size] = WhisperModel(model_size, device="cpu", compute_type="int8")
    return _MODEL_CACHE[model_size]


def _mmss(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 60:02d}:{s % 60:02d}"


def transcribe_file(path: str | Path, language: str | None = None,
                    model_size: str | None = None) -> str:
    model_size = model_size or env("WHISPER_MODEL", "small")
    model = _get_model(model_size)
    segments, info = model.transcribe(
        str(path), language=language or None, vad_filter=True,
        beam_size=5, condition_on_previous_text=False,
    )
    log(f"  local ASR: lang={info.language} ({info.language_probability:.2f})")
    out: list[str] = []
    next_mark = 0.0
    for seg in segments:
        if seg.start >= next_mark:
            out.append(f"\n[{_mmss(seg.start)}] ")
            next_mark = seg.start + 120  # a timestamp every ~2 min
        out.append(seg.text.strip() + " ")
    return "".join(out).strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("audio")
    ap.add_argument("--language", default=None)
    ap.add_argument("--model", default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    text = transcribe_file(args.audio, args.language, args.model)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        log(f"wrote {args.out} ({len(text)} chars)")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
