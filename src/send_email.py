"""Assemble the day's memos into one email and send via Gmail SMTP.

If SMTP_PASS is empty, writes a combined _digest.md instead and warns (so the
pipeline still produces output before the app password is set up).

Usage:
    python3 src/send_email.py --date 2026-07-09
    python3 src/send_email.py --memos path1.md path2.md
"""
from __future__ import annotations

import argparse
import re
import smtplib
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from common import MEMOS, env, log


# --- tiny markdown -> HTML (headings, bold, lists, hr, paragraphs) -----------
def md_to_html(md: str) -> str:
    html: list[str] = []
    in_list = False
    for line in md.splitlines():
        if line.startswith("- "):
            if not in_list:
                html.append("<ul>")
                in_list = True
            item = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", line[2:])
            html.append(f"<li>{item}</li>")
            continue
        if in_list:
            html.append("</ul>")
            in_list = False
        if line.startswith("### "):
            html.append(f"<h3>{line[4:]}</h3>")
        elif line.startswith("## "):
            html.append(f"<h2>{line[3:]}</h2>")
        elif line.startswith("# "):
            html.append(f"<h1>{line[2:]}</h1>")
        elif line.strip() == "---":
            html.append("<hr>")
        elif line.strip() == "":
            html.append("")
        else:
            para = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", line)
            html.append(f"<p>{para}</p>")
    if in_list:
        html.append("</ul>")
    return "\n".join(html)


def collect_memos(date: str | None, memo_paths: list[str] | None) -> list[Path]:
    if memo_paths:
        return [Path(p) for p in memo_paths if Path(p).exists()]
    folder = MEMOS / date if date else None
    if folder and folder.exists():
        return sorted(p for p in folder.glob("*.md") if not p.name.startswith("_"))
    return []


def build_email(memos: list[Path], date: str, label: str = "",
                footer: Path | None = None) -> tuple[str, str, str]:
    n = len(memos)
    middle = label or date  # wave label takes precedence over the date
    # Title is yours to set — BRIEF_TITLE in .env (any language).
    title = env("BRIEF_TITLE", "Daily Brief")
    episode_word = "episode" if n == 1 else "episodes"
    subject = f"{title} — {middle} — {n} new {episode_word}"
    bodies = [m.read_text(encoding="utf-8") for m in memos]
    combined_md = f"# {title} — {middle}\n\n_{n} new {episode_word}._\n\n---\n\n" + \
        "\n\n---\n\n".join(bodies)
    # Skipped episodes (< 5/10) ride along as a footer and are not counted as memos.
    if footer and footer.exists():
        combined_md += "\n\n---\n\n" + footer.read_text(encoding="utf-8")
    style = (
        "<style>body{font-family:-apple-system,Segoe UI,Roboto,sans-serif;"
        "max-width:720px;margin:0 auto;padding:16px;line-height:1.5;color:#1a1a1a}"
        "h1{font-size:1.5rem}h2{font-size:1.15rem;margin-top:1.4em;border-bottom:1px solid #eee}"
        "h3{font-size:1rem}hr{border:none;border-top:2px solid #ddd;margin:2em 0}"
        "li{margin:.2em 0}strong{color:#000}</style>"
    )
    html = f"<html><head>{style}</head><body>{md_to_html(combined_md)}</body></html>"
    return subject, combined_md, html


def send(subject: str, text: str, html: str) -> bool:
    host, port = env("SMTP_HOST", "smtp.gmail.com"), int(env("SMTP_PORT", "587"))
    user, pw = env("SMTP_USER"), env("SMTP_PASS")
    efrom, eto = env("EMAIL_FROM", user), env("EMAIL_TO")
    if not pw:
        log("  ! SMTP_PASS not set — skipping send (set a Gmail app password in .env)")
        return False
    if not eto:
        log("  ! EMAIL_TO not set — skipping send")
        return False
    msg = MIMEMultipart("alternative")
    msg["Subject"], msg["From"], msg["To"] = subject, efrom, eto
    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))
    with smtplib.SMTP(host, port, timeout=30) as s:
        s.starttls()
        s.login(user, pw)
        s.sendmail(efrom, [eto], msg.as_string())
    log(f"  ✓ emailed '{subject}' -> {eto}")
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None)
    ap.add_argument("--memos", nargs="*", default=None)
    ap.add_argument("--label", default="", help="label for the subject instead of a date, e.g. 'Backfill · Lenny'")
    ap.add_argument("--footer", default=None,
                    help="markdown file appended after the memos (e.g. the skipped-episode list)")
    args = ap.parse_args()

    memos = collect_memos(args.date, args.memos)
    if not memos:
        log("no memos to send — no email (this is normal on quiet days)")
        return 0
    date = args.date or ("" if args.label else "recent")
    footer = Path(args.footer) if args.footer else None
    subject, combined_md, html = build_email(memos, date, args.label, footer)

    # Always persist a combined digest alongside the memos.
    if args.date:
        (MEMOS / args.date / "_digest.md").write_text(combined_md, encoding="utf-8")

    sent = send(subject, combined_md, html)
    if not sent and args.date:
        log(f"  digest saved to {MEMOS / args.date / '_digest.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
