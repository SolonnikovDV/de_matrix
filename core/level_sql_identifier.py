# -*- coding: utf-8 -*-
"""
Имя таблицы уровня в PostgreSQL: латиница, snake_case, ≤63 символов.
Перевод подписи ru→en через публичный Google Translate (deep-translator, без API-ключа),
затем опциональный кастомный HTTP, иначе транслит.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

# Простой транслит кириллицы (без внешних зависимостей)
_CYR_TO_LAT = str.maketrans(
    {
        "а": "a",
        "б": "b",
        "в": "v",
        "г": "g",
        "д": "d",
        "е": "e",
        "ё": "e",
        "ж": "zh",
        "з": "z",
        "и": "i",
        "й": "y",
        "к": "k",
        "л": "l",
        "м": "m",
        "н": "n",
        "о": "o",
        "п": "p",
        "р": "r",
        "с": "s",
        "т": "t",
        "у": "u",
        "ф": "f",
        "х": "h",
        "ц": "ts",
        "ч": "ch",
        "ш": "sh",
        "щ": "sch",
        "ъ": "",
        "ы": "y",
        "ь": "",
        "э": "e",
        "ю": "yu",
        "я": "ya",
    }
)


def _transliterate_cyrillic_to_ascii(text: str) -> str:
    low = text.lower()
    return low.translate(_CYR_TO_LAT)


def _slugify_ascii(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", s.lower(), flags=re.I)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "level"


def _has_cyrillic(s: str) -> bool:
    return any("\u0400" <= c <= "\u04ff" for c in s)


def translate_label_google_ru_to_en(label: str) -> Optional[str]:
    """
    Перевод для slug: русский → английский через Google (библиотека deep-translator,
    без ключа Google Cloud; использует публичный веб-интерфейс, возможны лимиты/сбои).
    """
    src = (label or "").strip()
    if not src or not _has_cyrillic(src):
        return None
    try:
        from deep_translator import GoogleTranslator

        out = GoogleTranslator(source="ru", target="en").translate(src)
        return (out or "").strip() or None
    except Exception:
        return None


def translate_label_via_http(label: str, timeout: float = 12.0) -> Optional[str]:
    """
    Опциональный перевод для имён таблиц.
    DE_MATRIX_TRANSLATE_URL — POST JSON, по умолчанию тело: {"text": "<label>", "target": "en"}
    Ответ: JSON с полем "translated" или "text" или "result" (строка).
    DE_MATRIX_TRANSLATE_API_KEY — необязательный заголовок X-API-Key.
    При ошибке сети/формата — None (ниже по цепочке транслит).
    """
    url = (os.environ.get("DE_MATRIX_TRANSLATE_URL") or "").strip()
    if not url:
        return None
    body: Dict[str, Any] = {"text": (label or "").strip(), "target": "en"}
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    key = (os.environ.get("DE_MATRIX_TRANSLATE_API_KEY") or "").strip()
    if key:
        req.add_header("X-API-Key", key)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        out = json.loads(raw)
        if isinstance(out, str) and out.strip():
            return out.strip()
        if isinstance(out, dict):
            for k in ("translated", "text", "result", "translation"):
                v = out.get(k)
                if isinstance(v, str) and v.strip():
                    return v.strip()
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError, TypeError):
        return None
    return None


def sql_table_basename_from_level_title(title: str, slug_hint: str) -> str:
    """
    Короткий латинский идентификатор уровня (без префикса глубины).
    slug_hint — slug из matrix_levels, если уже латиница.
    """
    hint = (slug_hint or "").strip().lower()
    if hint and re.fullmatch(r"[a-z][a-z0-9_]{0,62}", hint):
        base = hint
    else:
        src = (title or "").strip()
        eng = translate_label_google_ru_to_en(src) or translate_label_via_http(src)
        if eng:
            base = _slugify_ascii(eng)
        else:
            base = _slugify_ascii(_transliterate_cyrillic_to_ascii(src))
    if len(base) > 48:
        base = base[:48].rstrip("_")
    return base or "level"


def qualified_sql_table_name(schema: str, depth: int, title: str, slug_hint: str) -> str:
    """Уникальное имя таблицы: l{depth}_{basename}. Итог ≤ 63 символов (лимит PostgreSQL)."""
    base = sql_table_basename_from_level_title(title, slug_hint)
    prefix = f"l{int(depth)}_"
    name = f"{prefix}{base}"
    if len(name) > 63:
        name = name[:63].rstrip("_")
    if not re.fullmatch(r"l\d+_[a-z][a-z0-9_]*", name):
        name = f"l{int(depth)}_level"
        if len(name) > 63:
            name = name[:63]
    return name


def is_safe_dynamic_table_name(schema: str, name: str) -> bool:
    """Защита от подстановки в DDL: только ожидаемый паттерн и схема matrix_struct."""
    if schema != "matrix_struct":
        return False
    return bool(re.fullmatch(r"l\d+_[a-z][a-z0-9_]{0,62}", name))
