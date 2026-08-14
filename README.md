# Daily Brief

**Give it links to the podcasts and YouTube channels you follow. Every morning it emails
you a short, opinionated memo on each new episode — written for you, not a generic summary.**

You don't have time to listen to 7 shows a week. This listens for you, and only tells you
the parts that matter *given who you are and what you're working on*.

```
   your links  ──▶  new episodes  ──▶  transcript  ──▶  memo written for YOU  ──▶  📧 email
                    (checked daily)     (free)       (Claude Code or Codex)      (8am)
```

Each memo answers: what's the real idea, why it matters to you, what you might be missing,
which plays to steal, and one experiment to try this week. Episodes that don't clear your
bar get one line saying why they were skipped — so you can trust that silence means nothing
was worth your time. **Quiet days send no email at all.**

---

## What you need

| | Needed? | Cost |
|---|---|---|
| **An AI agent — [Claude Code](https://claude.com/claude-code) *or* [Codex CLI](https://developers.openai.com/codex/cli)** | **Required** — it writes the memos. Either one works | Your existing Claude or ChatGPT subscription. No API key, no per-memo charge |
| **An email account** | **Required** — to receive the brief | Free. Gmail needs an "app password" (2 minutes, instructions below) |
| **Python 3.9+** | **Required** | Free |
| `ffmpeg` + `yt-dlp` | Only to transcribe audio | Free — `brew install ffmpeg yt-dlp` |
| **Azure OpenAI key** | **Optional** — faster transcription | ~$0.30–0.40 per audio-hour. **Skip it** and it uses free local transcription instead |

> **Claude Code or Codex?** Both do the same job here. The whole pipeline — finding
> episodes, transcribing, emailing — is plain Python that doesn't care which you use;
> only the memo-writing step calls the agent, and both read the same instructions from
> `AGENTS.md`. `./scripts/daily.sh` detects whichever you have installed.

> **You bring your own keys.** Everything lives in your own `.env` file on your own machine.
> Nothing is shared with anyone, and nothing is sent anywhere except the email you send yourself.

---

## Setup (about 5 minutes)

```bash
git clone https://github.com/dave817/news-podcast-update.git
cd news-podcast-update
./setup.sh
```

`setup.sh` creates the virtual environment, installs dependencies, and makes your
`.env`, `feeds.yaml`, and `persona/profile.md`. Then do these three things.

### 1. Add your email + app password

Open **`.env`** and fill in:

```ini
SMTP_USER=you@gmail.com
SMTP_PASS=xxxx xxxx xxxx xxxx  # ← your 16-char Gmail App Password, NOT your normal password
EMAIL_TO=you@gmail.com         # where the brief gets delivered
BRIEF_TITLE=Daily Brief        # the subject line — any language
```

**Getting a Gmail App Password:**
1. Turn on 2-Step Verification → https://myaccount.google.com/security
2. Create an app password → https://myaccount.google.com/apppasswords
3. Paste the 16-character code into `SMTP_PASS`

Not on Gmail? Outlook, iCloud, Fastmail and Yahoo settings are listed in `.env.example`.

### 2. Add the shows you want — just paste links

```bash
.venv/bin/python src/add_feed.py "https://youtube.com/@SomeChannel"
.venv/bin/python src/add_feed.py "https://podcasts.apple.com/us/podcast/name/id1234567890"
.venv/bin/python src/add_feed.py "https://feeds.example.com/show.rss"
.venv/bin/python src/add_feed.py "Acquired"          # or just the show's name
```

It works out the real feed URL for you. Manage the list with:

```bash
.venv/bin/python src/add_feed.py --list
.venv/bin/python src/add_feed.py --remove "Acquired"
```

Two example shows ship in `feeds.yaml` — delete them once you've added your own.

### 3. Say who you are ← *the step that actually matters*

Edit **`persona/profile.md`**. This file is what turns a generic summary into a brief
written for you: your role, what you're building, what you care about, and — importantly —
**what you don't care about**. It also sets the language the memos are written in.

Start from an example if that's easier:

```bash
cp persona/examples/solo-founder.md persona/profile.md      # solo founder building with AI
cp persona/examples/product-manager.md persona/profile.md   # PM working with a team
```

The same episode scores 9/10 for one profile and 3/10 for another. Be blunt and specific —
vague profiles produce vague memos.

---

## Try it

```bash
.venv/bin/python src/check_updates.py     # should list your shows and any new episodes
./scripts/daily.sh                        # full run: transcribe → write memos → email
```

`daily.sh` picks whichever agent you have. To force one:

```bash
AGENT=codex  ./scripts/daily.sh
AGENT=claude ./scripts/daily.sh
```

## Run it automatically every morning

```bash
./scripts/install-schedule.sh             # 8:00am daily
./scripts/install-schedule.sh 7 30        # or pick a time (7:30am)
./scripts/install-schedule.sh --uninstall # stop it
```

> **Claude Code users — one time only:** run `claude` once inside this folder and answer
> **"Yes, proceed"** to *"Do you trust the files in this folder?"*. Until you do, the
> scheduled run will write memos but **silently fail to email them**. If a log in
> `logs/` ever says `"has not been trusted"`, that's what happened — redo this step.
>
> **Codex users:** nothing extra to do. There's no trust prompt, and `daily.sh` already
> re-enables network access inside Codex's sandbox (without that, the sandbox blocks
> feed fetching and email).

Check on it:

```bash
tail -f logs/daily-$(date +%Y%m%d).log
```

---

## Everyday commands

```bash
# Add / list / remove sources
.venv/bin/python src/add_feed.py "<link or show name>"
.venv/bin/python src/add_feed.py --list

# See what's new without doing anything else
.venv/bin/python src/check_updates.py

# Full run (usually just let the schedule do this)
./scripts/daily.sh

# One specific episode
claude "/daily-brief one <episode_id>"          # Claude Code
codex exec --full-auto -c sandbox_workspace_write.network_access=true \
  "Read AGENTS.md and run one-episode mode for <episode_id>."   # Codex

# Work through a show's back catalogue
.venv/bin/python src/backfill.py --source "Lenny's Podcast" --limit 10
claude "/daily-brief backfill"                  # or the codex equivalent above

# Re-send a day's digest
.venv/bin/python src/send_email.py --date 2026-08-14
```

---

## How it works

| File | What it does |
|---|---|
| `feeds.yaml` | Your sources (managed by `add_feed.py`) |
| `persona/profile.md` | **Who the memos are written for** — the relevance layer |
| `persona/memo_template.md` | The 9-section memo structure |
| `src/add_feed.py` | Turns any link into a real feed URL |
| `src/check_updates.py` | Daily watcher — finds new episodes, dedupes |
| `src/get_transcript.py` | Captions → RSS transcript → ASR, in that order |
| `src/transcribe_azure.py` / `transcribe_local.py` | Paid-fast / free-slow transcription |
| `src/send_email.py` | Builds and sends the digest |
| `src/backfill.py` | Walks a show's archive |
| `data/` | Your transcripts, memos and episode database — **all local, git-ignored** |
| `AGENTS.md` | **The instructions the agent follows** — read by Codex and, via the skill, Claude Code |
| `.claude/skills/daily-brief/` | Makes it a `/daily-brief` command in Claude Code; defers to `AGENTS.md` |
| `scripts/daily.sh` | Runs the whole thing with whichever agent you have |

Transcription order: existing captions (free) → podcast RSS transcript (free) →
Azure (fast, paid, optional) → local Whisper (free, slower).

---

## Troubleshooting

**No email arrived.**
Quiet days genuinely send nothing — check `logs/` first. If there were memos but no email,
`SMTP_PASS` is usually missing or is a normal password rather than an app password.
Re-send with `.venv/bin/python src/send_email.py --date YYYY-MM-DD`.

**The scheduled run writes memos but never emails.**
*Claude Code:* the workspace isn't trusted — run `claude` in this folder once and accept
the trust prompt (see "Run it automatically" above).
*Codex:* the sandbox is blocking the network. Use `./scripts/daily.sh` rather than calling
`codex exec --full-auto` yourself, since the script adds
`-c sandbox_workspace_write.network_access=true`.

**Codex finds "no new episodes" every single day.**
Same cause: the sandbox has no network, so feed fetching silently returns nothing. Run it
through `./scripts/daily.sh`.

**`add_feed.py` says it can't read the feed.**
YouTube rate-limits its RSS endpoint and returns random 404s. Wait a minute and retry, or
force it: `--name "Show Name" --lang en`.

**Transcription is slow.**
That's local Whisper. Either add Azure keys to `.env`, or use a smaller `WHISPER_MODEL`
(`tiny`/`base`). Shows with captions are near-instant and free either way.

**Memos feel generic.**
`persona/profile.md` is too vague — especially the "score LOW" list. Being explicit about
what you *don't* want is what sharpens the output.

---

## Privacy

Your `.env` (keys), `feeds.yaml` (what you follow), `persona/profile.md` (about you), and
everything in `data/` (transcripts and memos) are **git-ignored**. They stay on your machine.
If you fork this repo and push, none of that goes with it.

## License

MIT — see [LICENSE](LICENSE). Use it, change it, share it.
