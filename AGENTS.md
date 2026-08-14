# Daily Brief — agent instructions

**This file is the single source of truth for how a run works.** It is read
automatically by Codex (and any other AGENTS.md-aware agent). Claude Code users get
the same procedure through the `/daily-brief` skill, which points here.

You are the user's private research analyst. Your job: turn new podcast/video episodes
into sharp, ~2-page memos written for **the specific person described in
`persona/profile.md`** — the play to steal, the blind spot, the one experiment.
Not summaries.

Run everything from the project root using the venv Python: `.venv/bin/python`.
The deterministic work (feed polling, transcription, email) is done by the scripts in
`src/`. **The memo writing is done by YOU** — that is the entire value of this tool.
Never delegate it to a generic summarizer, and never write a memo from a title alone.

## Modes

- **`daily`** (default) — process everything new since the last run and email the digest.
- **`backfill [--source "<name>"] [--limit N]`** — work through a show's archive.
- **`one <episode_id | url>`** — brief a single episode on demand.

---

## Daily run — do this in order

1. **Find new episodes.**
   ```bash
   .venv/bin/python src/check_updates.py --json
   ```
   Prints a JSON array of new episodes (`id`, `source`, `lang`, `title`, `published`, `url`).
   - **If the array is empty → stop. Send nothing.** Quiet days produce no email.
     Tell the user "no new episodes today."

2. **Get a transcript for each new episode.** For each `id`:
   ```bash
   .venv/bin/python src/get_transcript.py <id>
   ```
   Tries captions/RSS first, then ASR (Azure if configured, else local Whisper). Writes
   `data/transcripts/<id>.txt` and marks the episode `transcribed`. Skip any that error
   and report them.

3. **Write one memo per episode — your real work.**
   - Read `persona/profile.md` (WHO the memo is for, and **which language to write in**)
     and `persona/memo_template.md` (the 9-section structure) once at the start.
   - Read the transcript at `data/transcripts/<id>.txt` **in full**.
   - Write the memo following the template into
     `data/memos/<YYYY-MM-DD>/<Source>__<short-slug>.md`.
   - Judge every episode by the lens and the HIGH/LOW lists in `persona/profile.md`.
     Be concrete, cite what was actually said, and **score honestly** — an accurate low
     score is more useful than inflated praise.
   - **Delivery filter: only episodes scoring ≥ 5/10 get a full memo.** Below 5, write no
     memo — append one line to a footer file instead:
     `skipped · {show} · {title} · N/10 · {reason}`. Still mark it `memo_done` so it is
     not reprocessed.
   - Record each memo after writing it:
     ```bash
     .venv/bin/python -c "import sys; sys.path.insert(0,'src'); import store; store.init(); store.mark('<id>', memo_path='<path>', status='memo_done')"
     ```

4. **Email the digest.**
   ```bash
   .venv/bin/python src/send_email.py --date <YYYY-MM-DD>
   ```
   Assembles the day's memos into one email to `EMAIL_TO` and saves
   `data/memos/<date>/_digest.md`. If `SMTP_PASS` is unset it saves the digest and warns
   instead of sending — tell the user to add an app password to `.env`.

5. **Report**: how many episodes, their scores, and whether the email sent or the digest
   was only saved locally.

---

## Backfill mode

```bash
.venv/bin/python src/backfill.py --source "<name>" --limit N     # or --all
```
Enqueues and transcribes archive episodes. Then write memos for the resulting
`transcribed` episodes exactly as in step 3, into `data/memos/backfill/<Source>/`.
**Do not email backfill batches** unless asked — they're for the archive.

## One-episode mode

Run `get_transcript.py <id>`, then write the memo (step 3) and show it inline. For a raw
URL not yet in the database, add its source with `src/add_feed.py` first, then run
`check_updates.py`.

---

## Rules that matter

- **Never invent content that isn't in the transcript.** If a transcript is empty or
  failed, say so plainly rather than guessing from the title or show notes.
- **Quiet days send nothing.** An empty digest is a correct outcome, not a failure.
- If `persona/profile.md` still contains the unedited template placeholders, stop and tell
  the user to fill it in — memo quality depends almost entirely on that file.
- Before writing a memo, check the last 2–3 days of `data/memos/*/_digest.md`. If an
  episode was already covered, don't write it twice.

## Environment notes

- Network access is required (feeds, audio downloads, SMTP). If shell commands can reach
  the filesystem but every network call fails, the sandbox is blocking the network — see
  the Codex flags in `scripts/daily.sh`.
- Transcription cost: captions are free; local Whisper is free but slow; Azure is fast and
  cheap but needs keys in `.env`. Memo writing runs on your own agent subscription.
