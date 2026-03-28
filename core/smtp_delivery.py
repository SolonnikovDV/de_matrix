# -*- coding: utf-8 -*-
"""Отправка EmailMessage через SMTP по переменным DE_MATRIX_SMTP_*."""

from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage


def _env_flag(name: str, default: str = "0") -> bool:
    return (os.environ.get(name) or default).strip().lower() in ("1", "true", "yes")


def smtp_send_message(msg: EmailMessage, *, timeout: float = 10) -> None:
    """
    Подключение к SMTP и send_message.

    Переменные окружения:
    - DE_MATRIX_SMTP_HOST (по умолчанию smtp)
    - DE_MATRIX_SMTP_PORT (по умолчанию 1025, внутренний порт Mailpit в Docker)
    - DE_MATRIX_SMTP_SSL=1 — порт 465 и implicit TLS (SMTP_SSL)
    - DE_MATRIX_SMTP_STARTTLS=1 — STARTTLS после подключения (типично порт 587)
    - DE_MATRIX_SMTP_USER / DE_MATRIX_SMTP_PASSWORD — при непустом USER вызывается login()
    """
    host = (os.environ.get("DE_MATRIX_SMTP_HOST") or "smtp").strip()
    port = int((os.environ.get("DE_MATRIX_SMTP_PORT") or "1025").strip())
    use_ssl = _env_flag("DE_MATRIX_SMTP_SSL")
    use_starttls = _env_flag("DE_MATRIX_SMTP_STARTTLS")
    user = (os.environ.get("DE_MATRIX_SMTP_USER") or "").strip()
    password = os.environ.get("DE_MATRIX_SMTP_PASSWORD") or ""

    ctx = ssl.create_default_context()
    if use_ssl and use_starttls:
        raise ValueError("Set only one of DE_MATRIX_SMTP_SSL or DE_MATRIX_SMTP_STARTTLS")

    if use_ssl:
        with smtplib.SMTP_SSL(host, port, timeout=timeout, context=ctx) as smtp:
            if user:
                smtp.login(user, password)
            smtp.send_message(msg)
        return

    with smtplib.SMTP(host, port, timeout=timeout) as smtp:
        if use_starttls:
            smtp.starttls(context=ctx)
        if user:
            smtp.login(user, password)
        smtp.send_message(msg)
