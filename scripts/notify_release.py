#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import smtplib
import sys
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from storage.db import db_session  # noqa: E402
from storage.models import User, NotificationLog  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Send release notification emails")
    parser.add_argument("--ref", required=True, help="Release ref/tag/SHA")
    parser.add_argument("--title", default="", help="Optional custom release title")
    parser.add_argument("--dry-run", action="store_true", help="Do not send, print recipients only")
    args = parser.parse_args()

    enabled = os.environ.get("DE_MATRIX_NOTIFICATIONS_ENABLED", "1").strip().lower() in ("1", "true", "yes")
    smtp_host = (os.environ.get("DE_MATRIX_SMTP_HOST") or "smtp").strip()
    smtp_port = int((os.environ.get("DE_MATRIX_SMTP_PORT") or "1025").strip())
    smtp_from = (os.environ.get("DE_MATRIX_SMTP_FROM") or "de-matrix@localhost").strip()

    if not enabled:
        print("[notify-release] notifications are disabled")
        return 0

    with db_session() as session:
        users = session.execute(select(User).where(User.is_active == True)).scalars().all()  # noqa: E712
        recipients = sorted({(u.email or "").strip() for u in users if (u.email or "").strip()})

    if not recipients:
        print("[notify-release] no recipients with email")
        return 0

    subject = args.title.strip() or f"[de_matrix] New release deployed: {args.ref}"
    body = (
        "A new release has been deployed.\n\n"
        f"Ref: {args.ref}\n"
        "Open the application to review latest changes."
    )

    print(f"[notify-release] recipients: {', '.join(recipients)}")
    if args.dry_run:
        return 0

    with db_session() as session:
        log = NotificationLog(
            event_type="release",
            status="pending",
            subject=subject,
            body=body,
            recipients=recipients,
            context={"ref": args.ref},
            error="",
            attempts=0,
            created_by="deploy-prod-workflow",
        )
        session.add(log)
        session.flush()
        msg = EmailMessage()
        msg["From"] = smtp_from
        msg["To"] = ", ".join(recipients)
        msg["Subject"] = subject
        msg.set_content(body)
        log.attempts = 1
        log.last_attempt_at = datetime.now(timezone.utc)
        try:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as smtp:
                smtp.send_message(msg)
            log.status = "sent"
            log.sent_at = datetime.now(timezone.utc)
            print("[notify-release] sent")
        except Exception as exc:
            log.status = "failed"
            log.error = str(exc)
            print(f"[notify-release] failed: {exc}")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
