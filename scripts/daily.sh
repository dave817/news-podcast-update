#!/usr/bin/env bash
# Daily entrypoint. Runs the brief headlessly with whichever agent you have.
# Works from any install location — no hardcoded paths.
#
#   ./scripts/daily.sh                 # auto-detect claude, then codex
#   AGENT=codex  ./scripts/daily.sh    # force Codex
#   AGENT=claude ./scripts/daily.sh    # force Claude Code
set -uo pipefail

PROJECT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT" || exit 1

# launchd/cron give you a minimal PATH; make the usual tool locations reachable.
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:/usr/bin:/bin:$PATH"

mkdir -p logs
LOG="logs/daily-$(date +%Y%m%d).log"

AGENT="${AGENT:-auto}"
if [ "$AGENT" = "auto" ]; then
  if command -v claude >/dev/null 2>&1; then AGENT=claude
  elif command -v codex >/dev/null 2>&1; then AGENT=codex
  else
    {
      echo "=== daily brief run $(date) ==="
      echo "No agent found. Install one of:"
      echo "  Claude Code  https://claude.com/claude-code"
      echo "  Codex CLI    https://developers.openai.com/codex/cli"
    } >> "$LOG"
    exit 1
  fi
fi

echo "=== daily brief run $(date) [agent: $AGENT] ===" >> "$LOG"

case "$AGENT" in
  claude)
    # Needs the workspace trusted once (run `claude` here and accept the prompt),
    # otherwise the project permission allowlist is ignored and email never sends.
    claude -p "/daily-brief daily" --permission-mode acceptEdits >> "$LOG" 2>&1
    ;;

  codex)
    # The automatic sandbox is workspace-write, which DISABLES network access.
    # This pipeline needs the network for feeds, audio downloads and SMTP, so it
    # is re-enabled explicitly below — without that the run quietly finds nothing
    # and sends no email.
    codex exec \
      --full-auto \
      -c sandbox_workspace_write.network_access=true \
      -C "$PROJECT" \
      --skip-git-repo-check \
      "Read AGENTS.md in this directory and carry out the daily run end to end." \
      >> "$LOG" 2>&1
    ;;

  *)
    echo "Unknown AGENT '$AGENT' (expected 'claude' or 'codex')" >> "$LOG"
    exit 1
    ;;
esac

echo "=== done $(date) ===" >> "$LOG"
