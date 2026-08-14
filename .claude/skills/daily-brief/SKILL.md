---
name: daily-brief
description: >-
  Personal podcast/YouTube briefing. Checks the feeds in feeds.yaml for new
  episodes, gets a transcript for each, writes a ~2-page memo per episode
  tailored to the reader profile in persona/profile.md, and emails the digest.
  Use for the daily run, for backfilling archives, or to brief a single episode.
---

# Daily Brief

**Read `AGENTS.md` in the project root and follow it.** It holds the full procedure and
is the single source of truth, shared with Codex and any other agent — so this skill
stays a thin wrapper rather than a second copy that drifts out of sync.

Argument → mode:

| Invocation | Mode in AGENTS.md |
|---|---|
| `/daily-brief` or `/daily-brief daily` | **Daily run** — steps 1–5 |
| `/daily-brief backfill [--source "<name>"] [--limit N]` | **Backfill mode** |
| `/daily-brief one <episode_id \| url>` | **One-episode mode** |

Two things that are easy to get wrong, repeated here on purpose:

- **If `check_updates.py` returns an empty array, stop and send nothing.** Quiet days
  produce no email — that's correct behaviour, not a failure.
- **You write the memos yourself**, reading each transcript in full against
  `persona/profile.md`. That's the whole value; never hand it to a generic summarizer.
