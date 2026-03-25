#!/usr/bin/env python3
from __future__ import annotations

import os
import smtplib
import sys
from email.message import EmailMessage
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    enabled = os.environ.get("DE_MATRIX_NOTIFICATIONS_ENABLED", "1").strip().lower() in ("1", "true", "yes")
    if not enabled:
        print("[notification-smoke] notifications disabled, skipping")
        return 0

    smtp_host = (os.environ.get("DE_MATRIX_SMTP_HOST") or "smtp").strip()
    smtp_port = int((os.environ.get("DE_MATRIX_SMTP_PORT") or "1025").strip())
    smtp_from = (os.environ.get("DE_MATRIX_SMTP_FROM") or "de-matrix@localhost").strip()
    test_to = (os.environ.get("DE_MATRIX_NOTIFICATION_TEST_EMAIL") or "qa@localhost").strip()

    msg = EmailMessage()
    msg["From"] = smtp_from
    msg["To"] = test_to
    msg["Subject"] = "[de_matrix] notification smoke"
    msg.set_content("notification smoke check")

    with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as smtp:
        smtp.send_message(msg)

    print(f"[notification-smoke] sent to {test_to} via {smtp_host}:{smtp_port}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
