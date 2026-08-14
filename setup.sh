#!/usr/bin/env bash
# One-command setup. Safe to re-run: it never overwrites files you've edited.
set -euo pipefail

cd "$(dirname "$0")"
BOLD=$'\033[1m'; DIM=$'\033[2m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; RESET=$'\033[0m'

echo "${BOLD}Daily Brief — setup${RESET}"
echo

# ── 1. Python ────────────────────────────────────────────────────────────────
if ! command -v python3 >/dev/null 2>&1; then
  echo "${YELLOW}Python 3 is not installed.${RESET}"
  echo "  macOS:  brew install python3"
  echo "  Ubuntu: sudo apt install python3 python3-venv"
  exit 1
fi
PYV=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')
echo "  ${GREEN}✓${RESET} python3 $PYV"

# ── 2. Virtual environment + dependencies ────────────────────────────────────
if [ ! -d .venv ]; then
  echo "  … creating virtual environment (.venv)"
  python3 -m venv .venv
fi
echo "  … installing dependencies"
./.venv/bin/pip install --quiet --upgrade pip
./.venv/bin/pip install --quiet -r requirements.txt
echo "  ${GREEN}✓${RESET} dependencies installed"

# ── 3. Config files (never clobber existing ones) ────────────────────────────
created_env=false
if [ ! -f .env ]; then cp .env.example .env; created_env=true;
  echo "  ${GREEN}✓${RESET} created .env"
else echo "  ${DIM}·${RESET} .env already exists — left alone"; fi

if [ ! -f feeds.yaml ]; then cp feeds.example.yaml feeds.yaml
  echo "  ${GREEN}✓${RESET} created feeds.yaml (2 example sources)"
else echo "  ${DIM}·${RESET} feeds.yaml already exists — left alone"; fi

if [ ! -f persona/profile.md ]; then cp persona/profile.example.md persona/profile.md
  echo "  ${GREEN}✓${RESET} created persona/profile.md"
else echo "  ${DIM}·${RESET} persona/profile.md already exists — left alone"; fi

# ── 4. Optional tools ────────────────────────────────────────────────────────
echo
for tool in ffmpeg yt-dlp; do
  if command -v $tool >/dev/null 2>&1; then
    echo "  ${GREEN}✓${RESET} $tool found"
  else
    echo "  ${YELLOW}!${RESET} $tool not found ${DIM}(needed to transcribe audio: brew install $tool)${RESET}"
  fi
done
if command -v claude >/dev/null 2>&1; then
  echo "  ${GREEN}✓${RESET} claude CLI found"
else
  echo "  ${YELLOW}!${RESET} claude CLI not found — install from https://claude.com/claude-code"
  echo "    ${DIM}(this is what writes the memos)${RESET}"
fi

# ── 5. What to do next ───────────────────────────────────────────────────────
cat <<EOF

${BOLD}Next — 3 things, ~5 minutes${RESET}

  ${BOLD}1. Add your email + app password${RESET}
     Open ${BOLD}.env${RESET} and set SMTP_USER, SMTP_PASS, EMAIL_TO.
     Gmail app password: https://myaccount.google.com/apppasswords
     ${DIM}(needs 2-Step Verification turned on first)${RESET}

  ${BOLD}2. Add the shows you want${RESET}
     ./.venv/bin/python src/add_feed.py "https://youtube.com/@SomeChannel"
     ./.venv/bin/python src/add_feed.py "https://podcasts.apple.com/us/podcast/x/id123"
     ./.venv/bin/python src/add_feed.py --list

  ${BOLD}3. Say who you are${RESET}
     Edit ${BOLD}persona/profile.md${RESET} — this is what makes the brief yours.
     Or start from an example:
       cp persona/examples/solo-founder.md persona/profile.md

${BOLD}Then test it:${RESET}
     ./.venv/bin/python src/check_updates.py     ${DIM}# should list your shows${RESET}
     claude "/daily-brief daily"                 ${DIM}# full run + email${RESET}

${BOLD}Run it every morning at 8am:${RESET}
     ./scripts/install-schedule.sh

EOF
if [ "$created_env" = true ]; then
  echo "${YELLOW}Reminder: .env holds your password. It is git-ignored — never commit it.${RESET}"
  echo
fi
