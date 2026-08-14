#!/usr/bin/env bash
# Install the daily 8am schedule (macOS launchd, or cron on Linux).
# Usage:  ./scripts/install-schedule.sh [HH] [MM]      default 08:00
#         ./scripts/install-schedule.sh --uninstall
set -euo pipefail

PROJECT="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.dailybrief.run"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
BOLD=$'\033[1m'; DIM=$'\033[2m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; RESET=$'\033[0m'

if [ "${1:-}" = "--uninstall" ]; then
  if [[ "$OSTYPE" == darwin* ]]; then
    launchctl unload "$PLIST" 2>/dev/null || true
    rm -f "$PLIST"
    echo "${GREEN}✓${RESET} schedule removed"
  else
    crontab -l 2>/dev/null | grep -v "$PROJECT/scripts/daily.sh" | crontab - || true
    echo "${GREEN}✓${RESET} cron entry removed"
  fi
  exit 0
fi

HOUR="${1:-8}"; MIN="${2:-0}"
chmod +x "$PROJECT/scripts/daily.sh"

if [[ "$OSTYPE" == darwin* ]]; then
  mkdir -p "$HOME/Library/LaunchAgents"
  cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$PROJECT/scripts/daily.sh</string>
  </array>
  <key>WorkingDirectory</key><string>$PROJECT</string>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key><integer>$HOUR</integer>
    <key>Minute</key><integer>$MIN</integer>
  </dict>
  <key>RunAtLoad</key><false/>
  <key>StandardOutPath</key><string>$PROJECT/logs/launchd.out.log</string>
  <key>StandardErrorPath</key><string>$PROJECT/logs/launchd.err.log</string>
</dict>
</plist>
EOF
  mkdir -p "$PROJECT/logs"
  launchctl unload "$PLIST" 2>/dev/null || true
  launchctl load "$PLIST"
  printf '%s✓%s scheduled daily at %02d:%02d\n' "$GREEN" "$RESET" "$HOUR" "$MIN"
  echo "  ${DIM}test now:  launchctl kickstart -k gui/\$(id -u)/$LABEL${RESET}"
  echo "  ${DIM}remove:    ./scripts/install-schedule.sh --uninstall${RESET}"
else
  LINE="$MIN $HOUR * * * $PROJECT/scripts/daily.sh"
  ( crontab -l 2>/dev/null | grep -v "$PROJECT/scripts/daily.sh"; echo "$LINE" ) | crontab -
  printf '%s✓%s cron entry added for %02d:%02d daily\n' "$GREEN" "$RESET" "$HOUR" "$MIN"
fi

if command -v claude >/dev/null 2>&1; then
cat <<EOF

${YELLOW}${BOLD}One more step — do this or the scheduled run cannot send email${RESET}

Claude Code ignores this project's permission settings until you have opened it
here once and accepted the trust prompt. Until then the unattended run writes
the memos but silently fails to email them.

  ${BOLD}cd "$PROJECT" && claude${RESET}
  → answer ${BOLD}"Yes, proceed"${RESET} to "Do you trust the files in this folder?", then exit.

If a log in logs/ ever contains ${BOLD}"has not been trusted"${RESET}, redo that step.
EOF
else
cat <<EOF

${DIM}Using Codex — no trust prompt needed. The schedule re-enables network access
inside the sandbox automatically (see scripts/daily.sh).${RESET}
EOF
fi

cat <<EOF

Check a run afterwards with:
  tail -f "$PROJECT/logs/daily-\$(date +%Y%m%d).log"
EOF
