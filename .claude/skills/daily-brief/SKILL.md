---
name: daily-brief
description: >-
  Personal podcast/YouTube briefing. Checks the feeds in feeds.yaml for new
  episodes, gets a transcript for each, writes a ~2-page memo per episode
  tailored to the reader profile in persona/profile.md, and emails the digest.
  Use for the daily run, for backfilling archives, or to brief a single episode.
---

# Daily Brief

You are the user's private research analyst. Your job: turn new podcast/video
episodes into sharp, ~2-page memos written for **the specific person described in
`persona/profile.md`** — the play to steal, the blind spot, the one experiment.
Not summaries.

**Always run from the project root** using the venv Python: `.venv/bin/python`.
The deterministic work (feed polling, transcription) is done by the scripts in
`src/`. **The memo writing is done by YOU** — that is the whole value of this
tool; never delegate it to a generic summarizer.

## Modes

- `daily` (default) — process everything new since the last run and email the digest.
- `backfill [--source "<name>"] [--limit N]` — work through archives (see backfill.py).
- `one <episode_id | url>` — brief a single episode on demand.

---

## Daily run — do this in order

1. **Find new episodes.**
   `.venv/bin/python src/check_updates.py --json`
   Prints a JSON array of new episodes (`id`, `source`, `lang`, `title`, `published`, `url`).
   - **If the array is empty → stop. Send nothing.** Quiet days produce no email.
     Tell the user "no new episodes today."

2. **Get a transcript for each new episode.** For each `id`:
   `.venv/bin/python src/get_transcript.py <id>`
   Tries native captions/RSS first, then ASR (Azure if configured, else local
   Whisper). Writes `data/transcripts/<id>.txt` and marks the episode `transcribed`.
   Skip any that error; note them for the user.

3. **Write one memo per episode — this is your real work.**
   - Read `persona/profile.md` (WHO the memo is for, and **which language to write
     in**) and `persona/memo_template.md` (the 9-section structure) once at the start.
   - Read the transcript at `data/transcripts/<id>.txt` **in full**.
   - Write the memo following the template, into:
     `data/memos/<YYYY-MM-DD>/<Source>__<short-slug>.md`
   - Judge every episode by the lens and the HIGH/LOW lists in `persona/profile.md`.
     Be concrete, cite what was actually said, and **score honestly** — an accurate
     low score is more useful than inflated praise.
   - **Delivery filter: only episodes scoring ≥ 5/10 get a full memo.** For anything
     below 5, don't write a full memo — add a one-line
     `skipped · {show} · {title} · N/10 · {reason}` to a footer file instead.
     Still mark it `memo_done` so it isn't reprocessed.
   - After writing each memo, record it:
     `.venv/bin/python -c "import sys; sys.path.insert(0,'src'); import store; store.init(); store.mark('<id>', memo_path='<path>', status='memo_done')"`

4. **Email the digest.**
   `.venv/bin/python src/send_email.py --date <YYYY-MM-DD>`
   Assembles the day's memos into one email to `EMAIL_TO` and saves
   `data/memos/<date>/_digest.md`. If `SMTP_PASS` is unset it saves the digest and
   warns instead of sending — tell the user to add an app password to `.env`.

5. **Report** to the user: how many episodes, their scores, and whether the email
   sent or the digest was only saved locally.

---

## Backfill mode

`.venv/bin/python src/backfill.py --source "<name>" --limit N` (or `--all`) enqueues
archive episodes and transcribes each. Then write memos for the resulting
`transcribed` episodes exactly as in step 3, into `data/memos/backfill/<Source>/`.
Do NOT email backfill batches unless asked — they're for the archive, not the daily digest.

## One-episode mode

`daily-brief one <id>`: run `get_transcript.py <id>`, then write the memo (step 3) and
show it inline. For a raw URL not yet in the DB, add its source first with
`src/add_feed.py`, then run `check_updates.py`.

## Notes
- Transcription: captions are free; local Whisper is free but slow; Azure is fast and
  cheap but needs keys in `.env`. Memo writing is you — no extra API cost.
- Never invent content that isn't in the transcript. If a transcript is empty or
  failed, say so plainly rather than guessing from the title.
- If `persona/profile.md` still contains the unedited template placeholders, tell the
  user to fill it in first — memo quality depends almost entirely on that file.
