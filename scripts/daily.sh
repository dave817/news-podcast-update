#!/usr/bin/env bash
# Daily entrypoint. Runs the brief headlessly via the Claude Code CLI.
# Works from any install location — no hardcoded paths.
set -uo pipefail

PROJECT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT" || exit 1

# launchd/cron give you a minimal PATH; make the usual tool locations reachable.
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:/usr/bin:/bin:$PATH"

mkdir -p logs
LOG="logs/daily-$(date +%Y%m%d).log"

CLAUDE_BIN="$(command -v claude || true)"
if [ -z "$CLAUDE_BIN" ]; then
  echo "$(date): claude CLI not found in PATH — cannot run" >> "$LOG"
  exit 1
fi

echo "=== daily brief run $(date) ===" >> "$LOG"
"$CLAUDE_BIN" -p "/daily-brief daily" --permission-mode acceptEdits >> "$LOG" 2>&1
echo "=== done $(date) ===" >> "$LOG"
